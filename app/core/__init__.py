# app.core — routeur, prompts, Ollama, fallback

from app.core.fallback import stream_with_early_abort
from app.core.ollama_client import OllamaClient
from app.core.prompts import (
    SYSTEM_BASE,
    SYSTEM_CLOUD,
    SYSTEM_FAST,
    SYSTEM_QUALITY,
    get_system_prompt,
)
from app.core.router import RouteDecision, route_request

__all__ = [
    "OllamaClient",
    "RouteDecision",
    "route_request",
    "stream_with_early_abort",
    "SYSTEM_BASE",
    "SYSTEM_FAST",
    "SYSTEM_QUALITY",
    "SYSTEM_CLOUD",
    "get_system_prompt",
]
