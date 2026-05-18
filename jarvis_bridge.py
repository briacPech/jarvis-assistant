# jarvis_bridge.py — pont legacy (main_fast) ↔ app/ (edge)

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from router import Route, RouterAnalysis

_EDGE_OK = False
_EDGE_ERR = ""

try:
    from app.core.prompts import get_system_prompt as edge_get_system_prompt
    from app.core.router import hydrate_prompt as edge_hydrate_prompt
    from app.core.ollama_client import OllamaClient

    _EDGE_OK = True
except Exception as exc:
    _EDGE_ERR = str(exc)

_USE_APP_PROMPTS = os.getenv("JARVIS_USE_APP_PROMPTS", "true").lower() == "true"


def edge_available() -> bool:
    return _EDGE_OK


def edge_error() -> str:
    return _EDGE_ERR


def _route_to_variant(route: Any, *, fast_mode: bool) -> str:
    if fast_mode:
        return "fast"
    if route is None:
        return "base"
    val = route.value if hasattr(route, "value") else str(route)
    mapping = {
        "local_wake": "fast",
        "local_fast": "base",
        "local_quality": "quality",
        "cloud": "cloud",
        "cloud_heavy": "cloud",
    }
    return mapping.get(val, "base")


def get_system_prompt_for_route(
    route: "Route | None",
    *,
    fast_mode: bool = False,
    legacy_fn: Any = None,
) -> str:
    if _EDGE_OK and _USE_APP_PROMPTS:
        variant = _route_to_variant(route, fast_mode=fast_mode)
        return edge_get_system_prompt(variant)  # type: ignore[arg-type]
    if legacy_fn:
        return legacy_fn(route, fast_mode=fast_mode)
    return ""


def hydrate_user_message(
    user_text: str,
    analysis: "RouterAnalysis | None" = None,
    *,
    fast_mode: bool = False,
) -> tuple[str, bool]:
    if fast_mode:
        return user_text.strip(), False
    if _EDGE_OK:
        from app.config import get_settings

        cfg = get_settings()
        text, ok = edge_hydrate_prompt(
            user_text, enabled=cfg.prompt_hydration_enabled
        )
        if ok:
            return text, True
    try:
        from prompt_hydration import hydrate_user_prompt

        return hydrate_user_prompt(user_text, analysis)
    except ImportError:
        return user_text.strip(), False


def merge_ollama_options(
    opts: dict[str, Any],
    *,
    model: str | None,
) -> dict[str, Any]:
    if not model:
        return opts
    if _EDGE_OK:
        try:
            from app.config import get_settings

            client = OllamaClient(get_settings())
            merged = client.build_options(
                model=model.strip(),
                num_predict=int(opts.get("num_predict", 512)),
                num_ctx=int(opts.get("num_ctx", 1536)),
                temperature=float(opts.get("temperature", 0.6)),
            )
            if "num_gpu" in opts:
                merged["num_gpu"] = opts["num_gpu"]
            if "num_thread" in opts:
                merged["num_thread"] = opts["num_thread"]
            return merged
        except Exception:
            pass
    try:
        from ollama_refusal_opts import merge_anti_refusal_options

        return merge_anti_refusal_options(opts, model=model)
    except ImportError:
        return opts
