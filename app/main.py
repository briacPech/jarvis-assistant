# app/main.py — point d'entrée FastAPI (architecture modulaire)

import console_utf8  # noqa: F401  # UTF-8 console Windows

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    yield
    from app.api.routes import _ollama

    if _ollama is not None:
        await _ollama.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Jarvis Edge API",
        version="2.0.0",
        description="Pipeline async optimisée GTX 1650 (routeur, Ollama, early-abort)",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )
    app.include_router(router, prefix="/api")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
