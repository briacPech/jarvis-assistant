# app/config.py — configuration centralisée (Pydantic v2)

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Paramètres runtime (env > défauts)."""

    ollama_host: str = Field(default="http://127.0.0.1:11434")
    model_fast: str = Field(default="qwen2.5:1.5b-instruct-q4_K_M")
    model_quality: str = Field(default="qwen2.5:3b-instruct-q4_K_M")
    model_wake: str = Field(default="qwen2.5:0.5b")

    ollama_num_ctx: int = Field(default=1536, ge=512, le=131072)
    ollama_num_predict: int = Field(default=512, ge=32, le=8192)
    ollama_keep_alive: str = Field(default="5m")
    single_local_model: bool = Field(default=True)
    local_ollama_model: str = Field(default="qwen2.5:3b-instruct-q4_K_M")
    ollama_timeout: float = Field(default=120.0)

    refusal_bias_enabled: bool = Field(default=True)
    refusal_frequency_penalty: float = Field(default=0.45, ge=0.0, le=2.0)
    refusal_presence_penalty: float = Field(default=0.35, ge=0.0, le=2.0)
    refusal_repeat_penalty: float = Field(default=1.14, ge=1.0, le=2.0)

    complexity_cloud_threshold: int = Field(default=75, ge=0, le=100)
    complexity_quality_threshold: int = Field(default=60, ge=0, le=100)

    cloud_enabled: bool = Field(default=False)
    cloud_base_url: str = Field(default="https://api.groq.com/openai/v1")
    cloud_api_key: str = Field(default="")
    cloud_model: str = Field(default="llama-3.1-8b-instant")
    cloud_max_tokens: int = Field(default=768, ge=32, le=8192)

    early_abort_enabled: bool = Field(default=True)
    early_abort_min_chars: int = Field(default=8, ge=4, le=32)
    early_abort_window_chars: int = Field(default=60, ge=20, le=200)

    prompt_hydration_enabled: bool = Field(default=True)

    @classmethod
    def from_env(cls) -> Settings:
        def _bool(key: str, default: str) -> bool:
            return os.getenv(key, default).lower() == "true"

        return cls(
            ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
            model_fast=os.getenv(
                "JARVIS_FAST_MODEL", "qwen2.5:1.5b-instruct-q4_K_M"
            ),
            model_quality=os.getenv(
                "JARVIS_QUALITY_MODEL", "qwen2.5:3b-instruct-q4_K_M"
            ),
            model_wake=os.getenv("JARVIS_WAKE_MODEL", "qwen2.5:0.5b"),
            ollama_num_ctx=int(os.getenv("JARVIS_NUM_CTX", "1536")),
            ollama_num_predict=int(os.getenv("JARVIS_MAX_TOKENS", "512")),
            ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "5m"),
            single_local_model=os.getenv(
                "JARVIS_SINGLE_LOCAL_MODEL", "true"
            ).lower()
            == "true",
            local_ollama_model=os.getenv("JARVIS_LOCAL_MODEL", "").strip()
            or os.getenv("JARVIS_QUALITY_MODEL", "qwen2.5:3b-instruct-q4_K_M"),
            ollama_timeout=float(os.getenv("JARVIS_TIMEOUT", "30")),
            refusal_bias_enabled=_bool("JARVIS_REFUSAL_BIAS", "true"),
            refusal_frequency_penalty=float(
                os.getenv("JARVIS_REFUSAL_FREQUENCY", "0.45")
            ),
            refusal_presence_penalty=float(
                os.getenv("JARVIS_REFUSAL_PRESENCE", "0.35")
            ),
            refusal_repeat_penalty=float(
                os.getenv("JARVIS_REFUSAL_REPEAT", "1.14")
            ),
            complexity_cloud_threshold=int(
                os.getenv("JARVIS_COMPLEXITY_CLOUD", "75")
            ),
            complexity_quality_threshold=int(
                os.getenv("JARVIS_COMPLEXITY_QUALITY", "60")
            ),
            cloud_enabled=_bool("CLOUD_ENABLED", "false"),
            cloud_base_url=os.getenv(
                "CLOUD_BASE_URL", "https://api.groq.com/openai/v1"
            ).rstrip("/"),
            cloud_api_key=os.getenv("CLOUD_API_KEY", "")
            or os.getenv("GROQ_API_KEY", ""),
            cloud_model=os.getenv("CLOUD_MODEL", "llama-3.1-8b-instant"),
            cloud_max_tokens=int(os.getenv("CLOUD_MAX_TOKENS", "768")),
            early_abort_enabled=_bool("FALLBACK_EARLY_ABORT_ENABLED", "true"),
            early_abort_min_chars=int(
                os.getenv("FALLBACK_EARLY_ABORT_MIN_CHARS", "8")
            ),
            early_abort_window_chars=int(
                os.getenv("FALLBACK_EARLY_ABORT_CHARS", "60")
            ),
            prompt_hydration_enabled=_bool("JARVIS_PROMPT_HYDRATION", "true"),
        )


TargetModel = Literal["fast", "quality", "cloud", "wake"]


@lru_cache
def get_settings() -> Settings:
    try:
        from dotenv import load_dotenv

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(base, ".env"), override=True)
    except ImportError:
        pass
    return Settings.from_env()
