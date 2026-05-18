# app/schemas.py — modèles API (Pydantic v2)

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32_000)
    user_id: str = Field(default="default", max_length=128)
    fast_mode: bool = Field(default=False)
    force_cloud: bool | None = Field(default=None)
    max_tokens: int | None = Field(default=None, ge=32, le=8192)
    num_ctx: int | None = Field(default=None, ge=512, le=131072)


class RouteMeta(BaseModel):
    target_model: Literal["fast", "quality", "cloud", "wake"]
    score_complexite: int = Field(ge=0, le=100)
    intentions: list[str] = Field(default_factory=list)
    hydrated: bool = False
    system_variant: Literal["base", "fast", "quality", "cloud"] = "base"
    elapsed_ms: float = 0.0


class ChatResponse(BaseModel):
    message: str
    response: str
    provider: Literal["ollama", "groq", "cloud"] = "ollama"
    model: str = ""
    route: RouteMeta
