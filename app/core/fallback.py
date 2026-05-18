# app/core/fallback.py — Early-Abort streaming + bascule cloud transparente

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable, Awaitable
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, get_settings

# --- Regex précompilées (fenêtre ~15 tokens / 60 caractères) ---

_EARLY_PREFIXES: tuple[str, ...] = (
    "je suis une",
    "je suis un ",
    "je suis un mod",
    "en tant qu",
    "en tant que",
    "en tant qu'ia",
    "je ne peux pas",
    "je n'ai pas",
    "désolé",
    "desole",
    "désolée",
    "as an ai",
    "as a language",
    "i cannot",
    "i can't",
    "i am an ai",
    "événements passés",
    "evenements passes",
)

_EARLY_RX: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p, re.I), label)
    for p, label in (
        (r"^je suis (?:une? )?(?:ia|intelligence|mod[èe]le)", "early_ia"),
        (r"^en tant qu", "early_en_tant_que"),
        (r"^je ne (?:peux|suis)", "early_ne_peux"),
        (r"^(?:désol|desol)", "early_desole"),
        (r"^as an ai", "early_as_ai"),
        (r"^i (?:cannot|can't)", "early_en_refusal"),
        (r"(?:événements?|informations?) pass[ée]s", "early_passe"),
    )
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def check_early_refusal(
    buffer: str,
    *,
    min_chars: int = 8,
) -> tuple[bool, str]:
    """Détecte un refus dans le préfixe (~15 tokens / 60 caractères)."""
    low = _normalize(buffer)
    if len(low) < min_chars:
        return False, ""

    for prefix in _EARLY_PREFIXES:
        if low.startswith(prefix):
            return True, f"prefix:{prefix[:28]}"

    for rx, label in _EARLY_RX:
        if rx.search(low):
            return True, label

    return False, ""


class StreamEvent(BaseModel):
    """Événement SSE sérialisable."""

    kind: Literal["token", "replace", "done", "error", "meta"] = "token"
    token: str = ""
    text: str = ""
    provider: Literal["ollama", "cloud"] = "ollama"
    early_aborted: bool = False
    matched_pattern: str = ""
    model: str = ""


class CloudChatClient:
    """Client OpenAI-compatible minimal (Groq, etc.)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def available(self) -> bool:
        s = self._settings
        return bool(s.cloud_enabled and s.cloud_api_key.strip())

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
    ) -> str:
        cfg = self._settings
        if not self.available:
            return "ERREUR : Cloud indisponible (CLOUD_ENABLED / clé API)."

        limit = max_tokens or cfg.cloud_max_tokens
        headers = {
            "Authorization": f"Bearer {cfg.cloud_api_key.strip()}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": cfg.cloud_model,
            "messages": messages,
            "max_tokens": limit,
            "temperature": 0.7,
        }
        async with httpx.AsyncClient(
            base_url=cfg.cloud_base_url,
            timeout=httpx.Timeout(cfg.ollama_timeout),
        ) as client:
            r = await client.post(
                "/chat/completions", json=payload, headers=headers
            )
            if r.status_code != 200:
                return f"ERREUR Cloud HTTP {r.status_code}: {r.text[:200]}"
            data = r.json()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            return (msg.get("content") or "").strip()


def _sse_line(event: StreamEvent) -> str:
    payload = event.model_dump(exclude_none=True)
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_with_early_abort(
    ollama_stream: AsyncIterator[str],
    messages: list[dict[str, str]],
    *,
    model: str,
    settings: Settings | None = None,
    cloud_client: CloudChatClient | None = None,
    cloud_complete_fn: Callable[
        [list[dict[str, str]]], Awaitable[str]
    ] | None = None,
) -> AsyncIterator[str]:
    """
    Analyse les ~60 premiers caractères du flux Ollama.
    Refus détecté → Early Abort → réponse cloud complète (événement replace).
    Sinon → relay des tokens sans overhead supplémentaire.
    """
    cfg = settings or get_settings()
    cloud = cloud_client or CloudChatClient(cfg)
    buf = ""
    aborted = False
    pattern = ""
    window = cfg.early_abort_window_chars

    async for delta in ollama_stream:
        if delta.startswith("__HTTP_ERROR__"):
            yield _sse_line(StreamEvent(kind="error", text=delta))
            return

        buf += delta
        yield _sse_line(StreamEvent(kind="token", token=delta))

        if not cfg.early_abort_enabled:
            continue

        if len(buf) >= cfg.early_abort_min_chars:
            hit, pattern = check_early_refusal(
                buf[:window], min_chars=cfg.early_abort_min_chars
            )
            if hit:
                aborted = True
                break

    provider: Literal["ollama", "cloud"] = "ollama"
    final_text = buf

    if aborted and cloud.available:
        if cloud_complete_fn:
            final_text = await cloud_complete_fn(messages)
        else:
            final_text = await cloud.complete(messages)
        if not final_text.startswith("ERREUR"):
            provider = "cloud"
            yield _sse_line(
                StreamEvent(
                    kind="replace",
                    text=final_text,
                    provider="cloud",
                    early_aborted=True,
                    matched_pattern=pattern,
                )
            )

    yield _sse_line(
        StreamEvent(
            kind="done",
            provider=provider,
            model=model if provider == "ollama" else cfg.cloud_model,
            early_aborted=aborted,
            matched_pattern=pattern,
        )
    )
