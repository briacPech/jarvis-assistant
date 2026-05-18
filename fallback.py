# fallback.py — refus post-génération + Early-Abort streaming (~15 tokens)

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Iterator, Optional

import requests
from pydantic import BaseModel, Field

try:
    from config import (
        FALLBACK_EARLY_ABORT_CHARS,
        FALLBACK_EARLY_ABORT_ENABLED,
        FALLBACK_EARLY_ABORT_MIN_CHARS,
        FALLBACK_MIN_ANSWER_CHARS,
        FALLBACK_MIN_RATIO,
        ROUTER_PEDAGOGICAL_CLOUD_SCORE,
    )
except ImportError:
    FALLBACK_EARLY_ABORT_ENABLED = True
    FALLBACK_EARLY_ABORT_MIN_CHARS = 8
    FALLBACK_EARLY_ABORT_CHARS = 72
    FALLBACK_MIN_ANSWER_CHARS = 80
    FALLBACK_MIN_RATIO = 0.15
    ROUTER_PEDAGOGICAL_CLOUD_SCORE = 4


class FallbackDecision(BaseModel):
    should_fallback: bool = False
    reason: str = ""
    matched_pattern: str = ""


@dataclass
class StreamFallbackResult:
    text: str = ""
    provider: str = "ollama"
    cloud_model: str | None = None
    early_aborted: bool = False
    post_fallback: bool = False
    matched_pattern: str = ""
    decision: FallbackDecision = field(default_factory=FallbackDecision)


# --- Refus complets (post-génération) ---

_REFUSAL_SPECS: tuple[tuple[str, str], ...] = (
    (r"en tant que (mod[èe]le|ia|intelligence artificielle|ai)", "refus_ia"),
    (r"je ne peux pas (?:vous )?(?:informer|fournir|donner|répondre|aider)", "refus_ne_peux_pas"),
    (r"je n['']?(?:ai|ai pas) (?:pas )?(?:la capacité|les informations|accès)", "refus_capacite"),
    (r"je n['']?ai pas d['']?opinion", "refus_opinion"),
    (r"(?:événements?|informations?) pass[ée]s?", "refus_passe"),
    (r"au-delà de (?:ma|mes) (?:capacit[ée]s|connaissances)", "refus_limite"),
    (r"en tant qu['']?assistant(?: virtuel)?", "refus_assistant"),
    (r"my (?:training|knowledge) (?:cutoff|only)", "refus_en_training"),
    (r"i (?:cannot|can't) (?:provide|discuss|answer)", "refus_en_cannot"),
    (r"as an ai (?:language )?model", "refus_en_ai_model"),
    (r"i don['']t have (?:access|opinions)", "refus_en_access"),
    (r"(?:historical|past) events? (?:are|is) (?:beyond|outside)", "refus_en_past"),
    (r"politique(?:s)? de (?:contenu|sécurité)", "refus_politique"),
    (r"conform[ée]ment (?:à|aux) (?:directives|politiques)", "refus_directives"),
    (r"je suis (?:un |une )?(?:mod[èe]le|ia) (?:et|qui)", "refus_identite"),
    (r"désol[ée], mais je ne peux pas", "refus_desole"),
    (r"il est important de noter que je ne peux pas", "refus_important_noter"),
)

REFUSAL_PATTERNS: tuple[tuple[str, str], ...] = _REFUSAL_SPECS

_REFUSAL_RX: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p, re.I), label) for p, label in _REFUSAL_SPECS
)

# --- Early-Abort : premiers tokens en streaming ---

_EARLY_PREFIXES: tuple[str, ...] = (
    "je suis une",
    "je suis un ",
    "je suis un mod",
    "en tant que",
    "en tant qu'",
    "je ne peux pas",
    "je ne peux ",
    "je n'ai pas",
    "je n ai pas",
    "je ne suis pas",
    "désolé",
    "desole",
    "désolée",
    "malheureusement je",
    "il est important de noter",
    "i am an ai",
    "as an ai",
    "i cannot",
    "i can't",
    "i'm an ai",
    "as a language model",
)

_EARLY_RX: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p, re.I), label)
    for p, label in (
        (r"^je suis (?:une? )?(?:ia|intelligence|mod[èe]le)", "early_ia"),
        (r"^en tant que", "early_en_tant_que"),
        (r"^je ne (?:peux|suis)", "early_ne_peux"),
        (r"^(?:désol|desol)", "early_desole"),
        (r"^as an ai", "early_as_ai"),
        (r"^i (?:cannot|can't|am not)", "early_en_refusal"),
        (r"(?:événements?|informations?) pass[ée]s", "early_passe"),
        (r"pas (?:la capacité|les informations|accès)", "early_capacite"),
    )
)

_SHORT_OK_RX: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"^(?:oui|non|ok|d'accord|bien sûr|merci)\.?$",
        r"^\d{1,2}[:h]\d{0,2}",
    )
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def check_early_refusal(buffer: str) -> tuple[bool, str]:
    """
    Détecte un refus dans les ~15 premiers tokens (buffer court).
    Retourne (True, label) si coupure recommandée.
    """
    low = _normalize(buffer)
    if len(low) < FALLBACK_EARLY_ABORT_MIN_CHARS:
        return False, ""

    for prefix in _EARLY_PREFIXES:
        if low.startswith(prefix):
            return True, f"prefix:{prefix[:24]}"

    for rx, label in _EARLY_RX:
        if rx.search(low):
            return True, label

    return False, ""


def is_absurd_refusal(response: str) -> tuple[bool, str]:
    low = _normalize(response)
    if not low:
        return True, "empty"

    for rx, label in _REFUSAL_RX:
        if rx.search(low):
            return True, label

    if len(low) < 120 and re.search(
        r"je ne (?:peux|suis pas en mesure)|i (?:cannot|can't)|unable to",
        low,
        re.I,
    ):
        return True, "short_refusal"

    return False, ""


def is_too_short_for_request(
    response: str,
    user_text: str,
    *,
    requires_development: bool = False,
    complexity_score: int = 0,
) -> bool:
    ans = (response or "").strip()
    if not ans:
        return True

    low_ans = _normalize(ans)
    for rx in _SHORT_OK_RX:
        if rx.search(low_ans):
            return False

    q_len = max(len((user_text or "").strip()), 1)
    a_len = len(ans)

    if requires_development or complexity_score >= ROUTER_PEDAGOGICAL_CLOUD_SCORE:
        min_chars = max(FALLBACK_MIN_ANSWER_CHARS, int(q_len * FALLBACK_MIN_RATIO))
        if a_len < min_chars:
            return True

    if q_len >= 120 and a_len < 60:
        return True

    return False


def evaluate_fallback(
    local_response: str,
    user_text: str,
    *,
    requires_development: bool = False,
    complexity_score: int = 0,
    route_was_local: bool = True,
) -> FallbackDecision:
    if not route_was_local:
        return FallbackDecision(should_fallback=False, reason="already_cloud")

    refused, label = is_absurd_refusal(local_response)
    if refused:
        return FallbackDecision(
            should_fallback=True,
            reason="absurd_refusal",
            matched_pattern=label,
        )

    if is_too_short_for_request(
        local_response,
        user_text,
        requires_development=requires_development,
        complexity_score=complexity_score,
    ):
        return FallbackDecision(
            should_fallback=True,
            reason="too_short",
            matched_pattern="length",
        )

    return FallbackDecision(should_fallback=False)


def should_use_early_abort(*, fast_mode: bool, route_was_cloud: bool) -> bool:
    return (
        FALLBACK_EARLY_ABORT_ENABLED
        and not fast_mode
        and not route_was_cloud
    )


def iter_ollama_chat_stream(
    *,
    host: str,
    model: str,
    messages: list[dict[str, str]],
    options: dict[str, Any],
    keep_alive: str,
    timeout: int,
) -> Iterator[str]:
    """Yield des deltas texte depuis Ollama /api/chat stream=true."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": keep_alive,
        "options": options,
    }
    connect_sec = min(30, max(10, timeout // 4))
    read_timeout = timeout
    try:
        with requests.post(
            f"{host.rstrip('/')}/api/chat",
            json=payload,
            stream=True,
            timeout=(connect_sec, read_timeout),
        ) as resp:
            if resp.status_code != 200:
                yield f"__HTTP_ERROR__:{resp.status_code}:{resp.text[:120]}"
                return
            for raw_line in resp.iter_lines(decode_unicode=True):
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
    except requests.Timeout:
        return
    except requests.RequestException as exc:
        yield f"__HTTP_ERROR__:{exc.__class__.__name__}:{exc}"
        return


def stream_ollama_with_early_abort(
    *,
    host: str,
    model: str,
    messages: list[dict[str, str]],
    options: dict[str, Any],
    keep_alive: str,
    timeout: int,
    clean_fn: Callable[[str], str],
    max_abort_chars: int | None = None,
) -> tuple[str, bool, str]:
    """
    Stream Ollama ; coupe dès refus détecté dans le préfixe.
    Retourne (texte_partiel, aborted, pattern).
    """
    # Fenêtre d'analyse = premiers ~15 tokens ; la génération continue si pas de refus.
    window = max_abort_chars or FALLBACK_EARLY_ABORT_CHARS
    buf = ""
    aborted = False
    pattern = ""

    try:
        stream = iter_ollama_chat_stream(
            host=host,
            model=model,
            messages=messages,
            options=options,
            keep_alive=keep_alive,
            timeout=timeout,
        )
        for delta in stream:
            if delta.startswith("__HTTP_ERROR__:"):
                return delta, False, "http_error"
            buf += delta
            if len(buf) <= window and len(buf) >= FALLBACK_EARLY_ABORT_MIN_CHARS:
                hit, pattern = check_early_refusal(buf)
                if hit:
                    aborted = True
                    break
    except requests.Timeout:
        msg = f"ERREUR : Ollama timeout ({timeout}s)"
        return clean_fn(buf) if buf.strip() else msg, False, "timeout"
    except requests.RequestException as e:
        msg = f"ERREUR : Ollama ({e.__class__.__name__})"
        return clean_fn(buf) if buf.strip() else msg, False, "request_error"

    return clean_fn(buf), aborted, pattern


async def async_stream_ollama_with_early_abort(
    **kwargs: Any,
) -> tuple[str, bool, str]:
    import asyncio

    return await asyncio.to_thread(stream_ollama_with_early_abort, **kwargs)


def apply_cloud_fallback_if_needed(
    local_response: str,
    user_text: str,
    messages: list[dict[str, str]],
    *,
    requires_development: bool = False,
    complexity_score: int = 0,
    route_was_local: bool = True,
    cloud_available_fn: Callable[[], bool],
    cloud_quota_ok_fn: Callable[[], bool],
    ask_cloud_fn: Callable[..., tuple[str, str]],
    heavy: bool = False,
    max_tokens: int = 768,
) -> tuple[str, FallbackDecision, Optional[str]]:
    decision = evaluate_fallback(
        local_response,
        user_text,
        requires_development=requires_development,
        complexity_score=complexity_score,
        route_was_local=route_was_local,
    )

    if not decision.should_fallback:
        return local_response, decision, None

    if not cloud_available_fn() or not cloud_quota_ok_fn():
        return local_response, FallbackDecision(
            should_fallback=False,
            reason="cloud_unavailable",
            matched_pattern=decision.matched_pattern,
        ), None

    text, cloud_model = ask_cloud_fn(
        messages,
        heavy=heavy,
        max_tokens=max_tokens,
        route_label=f"refusal_fallback_{decision.reason}",
    )
    if (text or "").strip().startswith("ERREUR"):
        return local_response, FallbackDecision(
            should_fallback=False,
            reason="cloud_failed",
            matched_pattern=decision.matched_pattern,
        ), None
    return text, decision, cloud_model


def local_chat_with_early_abort_fallback(
    *,
    host: str,
    model: str,
    messages: list[dict[str, str]],
    options: dict[str, Any],
    keep_alive: str,
    timeout: int,
    clean_fn: Callable[[str], str],
    user_text: str,
    requires_development: bool,
    complexity_score: int,
    cloud_available_fn: Callable[[], bool],
    cloud_quota_ok_fn: Callable[[], bool],
    ask_cloud_fn: Callable[..., tuple[str, str]],
    heavy: bool = False,
    max_tokens: int = 768,
    use_early_abort: bool = True,
) -> StreamFallbackResult:
    """
    Pipeline local : stream + early-abort -> cloud silencieux si refus détecté.
    Sinon vérifie refus / longueur en fin de génération.
    """
    result = StreamFallbackResult(provider="ollama")

    if use_early_abort and should_use_early_abort(fast_mode=False, route_was_cloud=False):
        partial, aborted, pattern = stream_ollama_with_early_abort(
            host=host,
            model=model,
            messages=messages,
            options=options,
            keep_alive=keep_alive,
            timeout=timeout,
            clean_fn=clean_fn,
        )
        result.text = partial
        result.early_aborted = aborted
        result.matched_pattern = pattern

        if aborted and cloud_available_fn() and cloud_quota_ok_fn():
            text, cloud_model = ask_cloud_fn(
                messages,
                heavy=heavy,
                max_tokens=max_tokens,
                route_label=f"early_abort_{pattern or 'refusal'}",
            )
            if not (text or "").strip().startswith("ERREUR"):
                result.text = text
                result.provider = "groq"
                result.cloud_model = cloud_model
                result.post_fallback = True
                result.decision = FallbackDecision(
                    should_fallback=True,
                    reason="early_abort",
                    matched_pattern=pattern,
                )
                return result

        if aborted and not result.post_fallback:
            return result

        post = evaluate_fallback(
            partial,
            user_text,
            requires_development=requires_development,
            complexity_score=complexity_score,
        )
        if post.should_fallback:
            text, decision, cloud_model = apply_cloud_fallback_if_needed(
                partial,
                user_text,
                messages,
                requires_development=requires_development,
                complexity_score=complexity_score,
                cloud_available_fn=cloud_available_fn,
                cloud_quota_ok_fn=cloud_quota_ok_fn,
                ask_cloud_fn=ask_cloud_fn,
                heavy=heavy,
                max_tokens=max_tokens,
            )
            result.text = text
            result.decision = decision
            if decision.should_fallback and cloud_model:
                result.provider = "groq"
                result.post_fallback = True
            return result

        result.decision = post
        return result

    # Pas d'early-abort : l'appelant fournit déjà la réponse complète via ask_ollama_chat
    return result


async def async_local_chat_with_early_abort_fallback(
    **kwargs: Any,
) -> StreamFallbackResult:
    import asyncio

    return await asyncio.to_thread(local_chat_with_early_abort_fallback, **kwargs)


async def stream_sse_with_early_abort(
    *,
    host: str,
    model: str,
    messages: list[dict[str, str]],
    options: dict[str, Any],
    keep_alive: str,
    timeout: int,
    user_text: str,
    requires_development: bool,
    complexity_score: int,
    cloud_available_fn: Callable[[], bool],
    cloud_quota_ok_fn: Callable[[], bool],
    ask_cloud_fn: Callable[..., tuple[str, str]],
    heavy: bool = False,
    max_tokens: int = 768,
) -> AsyncIterator[str]:
    """
    Générateur SSE : tokens Ollama jusqu'à early-abort, puis bascule cloud (chunks entiers).
    Format : data: {"token": "..."}\n\n  |  data: {"done": true, "provider": "..."}\n\n
    """
    buf = ""
    aborted = False
    pattern = ""
    timed_out = False

    try:
        try:
            for delta in iter_ollama_chat_stream(
                host=host,
                model=model,
                messages=messages,
                options=options,
                keep_alive=keep_alive,
                timeout=timeout,
            ):
                if delta.startswith("__HTTP_ERROR__:"):
                    yield f'data: {json.dumps({"error": delta}, ensure_ascii=False)}\n\n'
                    return
                buf += delta
                yield f'data: {json.dumps({"token": delta}, ensure_ascii=False)}\n\n'

                if len(buf) >= FALLBACK_EARLY_ABORT_MIN_CHARS:
                    hit, pattern = check_early_refusal(buf)
                    if hit:
                        aborted = True
                        break
        except requests.Timeout:
            timed_out = True
            print(f"[Stream] Ollama timeout ({timeout}s) apres {len(buf)} car.")
        except requests.RequestException as exc:
            yield f'data: {json.dumps({"error": str(exc)}, ensure_ascii=False)}\n\n'
            yield f'data: {json.dumps({"done": True, "provider": "ollama", "error": True, "response": buf}, ensure_ascii=False)}\n\n'
            return
    except Exception as exc:
        print(f"[Stream] Erreur inattendue : {exc}")
        final_err = buf.strip() or f"Erreur stream : {exc}"
        yield f'data: {json.dumps({"replace": final_err, "provider": "ollama"}, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({"done": True, "provider": "ollama", "error": True, "response": final_err}, ensure_ascii=False)}\n\n'
        return

    provider = "ollama"
    final = buf

    if timed_out:
        if not final.strip():
            if cloud_available_fn() and cloud_quota_ok_fn():
                text, _ = ask_cloud_fn(
                    messages,
                    heavy=heavy,
                    max_tokens=max_tokens,
                    route_label="stream_timeout_cloud",
                )
                if not (text or "").strip().startswith("ERREUR"):
                    final = text
                    provider = "groq"
                    yield f'data: {json.dumps({"replace": final, "provider": provider}, ensure_ascii=False)}\n\n'
                    yield f'data: {json.dumps({"done": True, "provider": provider, "timeout": True, "response": final}, ensure_ascii=False)}\n\n'
                    return
            final = (
                f"Ollama a mis trop de temps ({timeout}s). "
                "Reessaie une question plus courte, ou desactive « Reponse progressive »."
            )
        yield f'data: {json.dumps({"replace": final, "provider": provider}, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({"done": True, "provider": provider, "timeout": True, "response": final}, ensure_ascii=False)}\n\n'
        return

    if aborted and cloud_available_fn() and cloud_quota_ok_fn():
        text, _ = ask_cloud_fn(
            messages,
            heavy=heavy,
            max_tokens=max_tokens,
            route_label=f"early_abort_sse_{pattern}",
        )
        if not (text or "").strip().startswith("ERREUR"):
            final = text
            provider = "groq"
            yield f'data: {json.dumps({"replace": final, "provider": provider}, ensure_ascii=False)}\n\n'
    elif not aborted:
        post = evaluate_fallback(
            buf,
            user_text,
            requires_development=requires_development,
            complexity_score=complexity_score,
        )
        if post.should_fallback and cloud_available_fn() and cloud_quota_ok_fn():
            text, _, _ = apply_cloud_fallback_if_needed(
                buf,
                user_text,
                messages,
                requires_development=requires_development,
                complexity_score=complexity_score,
                cloud_available_fn=cloud_available_fn,
                cloud_quota_ok_fn=cloud_quota_ok_fn,
                ask_cloud_fn=ask_cloud_fn,
                heavy=heavy,
                max_tokens=max_tokens,
            )
            if text != buf:
                final = text
                provider = "groq"
                yield f'data: {json.dumps({"replace": final, "provider": provider}, ensure_ascii=False)}\n\n'

    yield f'data: {json.dumps({"done": True, "provider": provider, "early_aborted": aborted, "response": final}, ensure_ascii=False)}\n\n'
