# app/core/ollama_client.py — client Ollama async (httpx) + anti-refus

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings, get_settings

REFUSAL_FRAGMENTS: tuple[str, ...] = (
    "désolé",
    "desole",
    "en tant que",
    "intelligence artificielle",
    "modèle de langage",
    "je ne peux pas",
    "impossible de",
    "mes limites",
    "as an ai",
    "as a language model",
    "i cannot",
)


class OllamaClient:
    """Appels asynchrones à Ollama — streaming et options anti-refus."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._settings.ollama_host.rstrip("/"),
            timeout=httpx.Timeout(self._settings.ollama_timeout),
        )
        self._token_bias_cache: dict[str, list[list[float | int]]] = {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> OllamaClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def _resolve_token_ids(self, model: str, phrase: str) -> list[int]:
        try:
            r = await self._client.post(
                "/api/tokenize",
                json={"model": model, "content": phrase},
            )
            if r.status_code != 200:
                return []
            data = r.json()
            ids = data.get("tokens") or data.get("ids") or []
            return [int(x) for x in ids if isinstance(x, (int, float))]
        except Exception:
            return []

    async def build_logit_bias(self, model: str) -> list[list[float | int]]:
        if model in self._token_bias_cache:
            return self._token_bias_cache[model]
        seen: set[int] = set()
        pairs: list[list[float | int]] = []
        for frag in REFUSAL_FRAGMENTS:
            for tid in await self._resolve_token_ids(model, frag):
                if tid not in seen:
                    seen.add(tid)
                    pairs.append([tid, -4.0])
        self._token_bias_cache[model] = pairs
        return pairs

    def build_options(
        self,
        *,
        model: str,
        num_predict: int | None = None,
        num_ctx: int | None = None,
        temperature: float = 0.6,
        apply_refusal_bias: bool = True,
    ) -> dict[str, Any]:
        cfg = self._settings
        opts: dict[str, Any] = {
            "num_predict": num_predict or cfg.ollama_num_predict,
            "num_ctx": num_ctx or cfg.ollama_num_ctx,
            "temperature": temperature,
        }
        if not apply_refusal_bias or not cfg.refusal_bias_enabled:
            return opts

        opts["repeat_penalty"] = max(
            float(opts.get("repeat_penalty", 1.0)),
            cfg.refusal_repeat_penalty,
        )
        opts["frequency_penalty"] = max(
            float(opts.get("frequency_penalty", 0.0)),
            cfg.refusal_frequency_penalty,
        )
        opts["presence_penalty"] = max(
            float(opts.get("presence_penalty", 0.0)),
            cfg.refusal_presence_penalty,
        )
        return opts

    async def build_options_async(
        self,
        *,
        model: str,
        num_predict: int | None = None,
        num_ctx: int | None = None,
        temperature: float = 0.6,
    ) -> dict[str, Any]:
        opts = self.build_options(
            model=model,
            num_predict=num_predict,
            num_ctx=num_ctx,
            temperature=temperature,
        )
        if self._settings.refusal_bias_enabled:
            bias = await self.build_logit_bias(model)
            if bias:
                opts["logit_bias"] = bias
        return opts

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        num_predict: int | None = None,
        num_ctx: int | None = None,
    ) -> str:
        options = await self.build_options_async(
            model=model, num_predict=num_predict, num_ctx=num_ctx
        )
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": "5m",
            "options": options,
        }
        r = await self._client.post("/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        return ((data.get("message") or {}).get("content") or "").strip()

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        num_predict: int | None = None,
        num_ctx: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield des deltas texte depuis /api/chat stream=true."""
        options = await self.build_options_async(
            model=model, num_predict=num_predict, num_ctx=num_ctx
        )
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": "5m",
            "options": options,
        }
        async with self._client.stream("POST", "/api/chat", json=payload) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode(errors="replace")[:120]
                yield f"__HTTP_ERROR__:{resp.status_code}:{body}"
                return
            async for raw_line in resp.aiter_lines():
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("done"):
                    break
                part = (chunk.get("message") or {}).get("content") or ""
                if part:
                    yield part
