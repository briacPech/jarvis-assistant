# local_model_policy.py — un seul modèle Ollama en VRAM + keep_alive 5m

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import requests

try:
    from config import (
        CLOUD_HEAVY_THRESHOLD,
        FAST_MODEL,
        MODEL,
        OLLAMA_HOST,
        QUALITY_MODEL,
        SINGLE_LOCAL_MODEL,
        WAKE_MODEL,
    )
except ImportError:
    OLLAMA_HOST = "http://127.0.0.1:11434"
    QUALITY_MODEL = "qwen2.5:3b-instruct-q4_K_M"
    FAST_MODEL = MODEL = "qwen2.5:1.5b-instruct-q4_K_M"
    WAKE_MODEL = "qwen2.5:0.5b"
    SINGLE_LOCAL_MODEL = True
    CLOUD_HEAVY_THRESHOLD = 8

if TYPE_CHECKING:
    from router import Route

# Forcé pour toutes les requêtes Ollama locales (évite déchargement trop agressif)
OLLAMA_KEEP_ALIVE_LOCAL: str = "5m"


def ollama_keep_alive() -> str:
    """Keep-alive unique pour les appels Ollama chat / generate."""
    return OLLAMA_KEEP_ALIVE_LOCAL


def local_ollama_model() -> str:
    """Seul poids autorisé en VRAM (défaut : 3B qualité)."""
    custom = os.getenv("JARVIS_LOCAL_MODEL", "").strip()
    return custom or QUALITY_MODEL


def is_single_local_mode() -> bool:
    return SINGLE_LOCAL_MODEL


def models_to_evict() -> list[str]:
    """Modèles à décharger au démarrage (keep_alive=0)."""
    keep = local_ollama_model().strip()
    seen: set[str] = set()
    out: list[str] = []
    for name in (FAST_MODEL, MODEL, WAKE_MODEL, QUALITY_MODEL):
        n = (name or "").strip()
        if not n or n == keep or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def unload_ollama_model(name: str, *, host: str | None = None) -> bool:
    """Décharge un modèle de la VRAM (keep_alive=0)."""
    n = (name or "").strip()
    if not n:
        return False
    base = (host or OLLAMA_HOST).rstrip("/")
    try:
        r = requests.post(
            f"{base}/api/generate",
            json={"model": n, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=15,
        )
        return r.status_code == 200
    except Exception:
        return False


def evict_non_local_models(*, host: str | None = None) -> None:
    if not is_single_local_mode():
        return
    for name in models_to_evict():
        if unload_ollama_model(name, host=host):
            print(f"[VRAM] Modele decharge : {name}")


def coerce_ollama_model(requested: str | None) -> str:
    """Redirige tout appel local vers le modèle unique 3B."""
    if not is_single_local_mode():
        return (requested or local_ollama_model()).strip()
    local = local_ollama_model()
    req = (requested or "").strip()
    if not req or req == local:
        return local
    print(f"[VRAM] Un seul modele local — '{req}' -> {local}")
    return local


def upgrade_route_for_vram(
    route: Any,
    score: int,
    *,
    cloud_enabled: bool,
    cloud_quota_ok: bool,
    is_heavy_fn: Any,
    text: str,
    analysis: Any = None,
) -> Any:
    """
    Politique VRAM : seul LOCAL_QUALITY reste en Ollama ;
    fast / wake / cloud léger -> cloud si dispo, sinon 3B local.
    Salutations courtes : restent LOCAL_FAST (tokens limites).
    """
    from router import Route, is_simple_chat

    if not is_single_local_mode():
        return route

    if route in (Route.CLOUD, Route.CLOUD_HEAVY):
        return route

    if route == Route.LOCAL_QUALITY:
        return route

    if route == Route.LOCAL_FAST and is_simple_chat(text, analysis):
        return route

    if cloud_enabled and cloud_quota_ok:
        if is_heavy_fn(text, score):
            return Route.CLOUD_HEAVY
        return Route.CLOUD

    return Route.LOCAL_QUALITY
