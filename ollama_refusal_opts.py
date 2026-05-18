# ollama_refusal_opts.py — pénalités / logit bias anti-refus (Ollama local)

from __future__ import annotations

import threading
from typing import Any

import requests

try:
    from config import (
        OLLAMA_HOST,
        OLLAMA_REFUSAL_BIAS_ENABLED,
        OLLAMA_REFUSAL_FREQUENCY_PENALTY,
        OLLAMA_REFUSAL_LOGIT_BIAS,
        OLLAMA_REFUSAL_LOGIT_BIAS_STRENGTH,
        OLLAMA_REFUSAL_PRESENCE_PENALTY,
        OLLAMA_REFUSAL_REPEAT_PENALTY,
    )
except ImportError:
    OLLAMA_HOST = "http://127.0.0.1:11434"
    OLLAMA_REFUSAL_BIAS_ENABLED = True
    OLLAMA_REFUSAL_FREQUENCY_PENALTY = 0.45
    OLLAMA_REFUSAL_PRESENCE_PENALTY = 0.35
    OLLAMA_REFUSAL_REPEAT_PENALTY = 1.14
    OLLAMA_REFUSAL_LOGIT_BIAS = True
    OLLAMA_REFUSAL_LOGIT_BIAS_STRENGTH = -4.0

# Fragments de refus à décourager (alignement)
REFUSAL_FRAGMENTS: tuple[str, ...] = (
    "désolé",
    "desole",
    "désolée",
    "je suis désolé",
    "en tant qu",
    "en tant que",
    "intelligence artificielle",
    " modèle de langage",
    "modèle ia",
    "je ne peux pas",
    "je ne peux pas vous",
    "il m'est impossible",
    "impossible de",
    "ma limite",
    "mes limites",
    "au-delà de mes",
    "je n'ai pas accès",
    "je n ai pas accès",
    "conformément aux",
    "politique de contenu",
    "as an ai",
    "as a language model",
    "i cannot",
    "i can't provide",
)

_token_cache: dict[str, list[list[float | int]]] = {}
_cache_lock = threading.Lock()
_logit_bias_supported: bool | None = None


def _resolve_token_ids(model: str, phrase: str, host: str) -> list[int]:
    """Tente /api/tokenize ; sinon heuristique vide."""
    try:
        r = requests.post(
            f"{host.rstrip('/')}/api/tokenize",
            json={"model": model, "content": phrase},
            timeout=4,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        ids = data.get("tokens") or data.get("ids") or []
        return [int(x) for x in ids if isinstance(x, (int, float))]
    except Exception:
        return []


def build_logit_bias(
    model: str,
    *,
    host: str | None = None,
    strength: float | None = None,
) -> list[list[float | int]]:
    """
    Biais négatifs sur les tokens des fragments de refus.
    Format llama.cpp : [[token_id, bias], ...]
    """
    if not OLLAMA_REFUSAL_LOGIT_BIAS:
        return []
    use_host = host or OLLAMA_HOST
    bias_val = strength if strength is not None else OLLAMA_REFUSAL_LOGIT_BIAS_STRENGTH
    cache_key = f"{model}:{bias_val}"
    with _cache_lock:
        if cache_key in _token_cache:
            return _token_cache[cache_key]

    seen: set[int] = set()
    pairs: list[list[float | int]] = []
    for frag in REFUSAL_FRAGMENTS:
        for tid in _resolve_token_ids(model, frag, use_host):
            if tid in seen:
                continue
            seen.add(tid)
            pairs.append([tid, bias_val])

    with _cache_lock:
        _token_cache[cache_key] = pairs
    return pairs


def merge_anti_refusal_options(
    opts: dict[str, Any],
    *,
    model: str | None = None,
    host: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """
    Fusionne repeat / frequency / presence penalty + logit_bias optionnel.
    """
    use = OLLAMA_REFUSAL_BIAS_ENABLED if enabled is None else enabled
    if not use:
        return dict(opts)

    out = dict(opts)
    out["repeat_penalty"] = max(
        float(out.get("repeat_penalty", 1.0)),
        OLLAMA_REFUSAL_REPEAT_PENALTY,
    )
    out["frequency_penalty"] = max(
        float(out.get("frequency_penalty", 0.0)),
        OLLAMA_REFUSAL_FREQUENCY_PENALTY,
    )
    out["presence_penalty"] = max(
        float(out.get("presence_penalty", 0.0)),
        OLLAMA_REFUSAL_PRESENCE_PENALTY,
    )

    if model and OLLAMA_REFUSAL_LOGIT_BIAS:
        bias = build_logit_bias(model, host=host)
        if bias:
            out["logit_bias"] = bias
    return out


def probe_logit_bias_support(model: str, host: str | None = None) -> bool:
    """Teste une fois si Ollama accepte logit_bias dans options."""
    global _logit_bias_supported
    if _logit_bias_supported is not None:
        return _logit_bias_supported
    use_host = host or OLLAMA_HOST
    bias = build_logit_bias(model, host=use_host)
    if not bias:
        _logit_bias_supported = False
        return False
    try:
        r = requests.post(
            f"{use_host.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
                "options": {
                    "num_predict": 1,
                    "logit_bias": bias[:4],
                },
            },
            timeout=15,
        )
        _logit_bias_supported = r.status_code == 200
    except Exception:
        _logit_bias_supported = False
    return _logit_bias_supported
