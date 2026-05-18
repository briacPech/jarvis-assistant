# prompt_loader.py — chargement des prompts système par route

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from router import Route

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.getenv(
    "JARVIS_PROMPTS_DIR",
    os.path.join(_BASE_DIR, "prompts"),
)

_PROMPT_FILES = {
    "base": "system_base.txt",
    "fast": "system_fast.txt",
    "quality": "system_quality.txt",
    "cloud": "system_cloud.txt",
}


@lru_cache(maxsize=8)
def _read_prompt_file(filename: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompt introuvable : {path}")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def get_system_prompt(
    route: "Route | str | None" = None,
    *,
    fast_mode: bool = False,
) -> str:
    """
    Retourne le prompt système adapté à la route de routage.
    fast_mode force system_fast (wake / réponses courtes).
    """
    if fast_mode:
        return _read_prompt_file(_PROMPT_FILES["fast"])

    from router import Route

    if route is None:
        return _read_prompt_file(_PROMPT_FILES["base"])

    if isinstance(route, str):
        try:
            route = Route(route)
        except ValueError:
            return _read_prompt_file(_PROMPT_FILES["base"])

    if route == Route.LOCAL_WAKE:
        return _read_prompt_file(_PROMPT_FILES["fast"])
    if route == Route.LOCAL_QUALITY:
        return _read_prompt_file(_PROMPT_FILES["quality"])
    if route in (Route.CLOUD, Route.CLOUD_HEAVY):
        return _read_prompt_file(_PROMPT_FILES["cloud"])
    if route == Route.LOCAL_FAST:
        return _read_prompt_file(_PROMPT_FILES["base"])
    return _read_prompt_file(_PROMPT_FILES["base"])


def reload_prompts() -> None:
    """Vide le cache après modification des fichiers prompts."""
    _read_prompt_file.cache_clear()
