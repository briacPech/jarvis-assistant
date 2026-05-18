# app/api/routes.py — pipeline chat async (routeur → Ollama → early-abort)

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.core.fallback import CloudChatClient, stream_with_early_abort
from app.core.ollama_client import OllamaClient
from app.core.prompts import get_system_prompt
from app.core.router import route_request
from app.schemas import ChatRequest, ChatResponse, RouteMeta

router = APIRouter(tags=["chat"])

_ollama: OllamaClient | None = None
_cloud: CloudChatClient | None = None


def _get_ollama() -> OllamaClient:
    global _ollama
    if _ollama is None:
        _ollama = OllamaClient()
    return _ollama


def _get_cloud() -> CloudChatClient:
    global _cloud
    if _cloud is None:
        _cloud = CloudChatClient()
    return _cloud


def _build_messages(
    system: str,
    user_prompt: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Pipeline synchrone :
    1. Routage + hydratation
    2. Prompt système
    3. Ollama (ou cloud direct)
    """
    settings = get_settings()
    decision = route_request(
        request.message,
        settings=settings,
        fast_mode=request.fast_mode,
        force_cloud=request.force_cloud,
    )

    system = get_system_prompt(decision.system_variant)
    messages = _build_messages(system, decision.user_prompt)
    num_predict = request.max_tokens or settings.ollama_num_predict
    num_ctx = request.num_ctx or settings.ollama_num_ctx

    ollama = _get_ollama()
    cloud = _get_cloud()

    if decision.use_cloud:
        text = await cloud.complete(messages, max_tokens=num_predict)
        provider = "cloud"
        model = settings.cloud_model
    else:
        text = await ollama.chat(
            model=decision.ollama_model,
            messages=messages,
            num_predict=num_predict,
            num_ctx=num_ctx,
        )
        provider = "ollama"
        model = decision.ollama_model

    route_meta = RouteMeta(
        target_model=decision.target_model,
        score_complexite=decision.score_complexite,
        intentions=decision.intentions,
        hydrated=decision.hydrated,
        system_variant=decision.system_variant,
        elapsed_ms=decision.elapsed_ms,
    )

    return ChatResponse(
        message=request.message,
        response=text,
        provider=provider,  # type: ignore[arg-type]
        model=model,
        route=route_meta,
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest) -> StreamingResponse:
    """
    Pipeline streaming :
    1. Réception
    2. Routage rapide + hydratation
    3. Ollama stream + options anti-refus
    4. Fallback early-abort → cloud si refus détecté
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message vide")

    settings = get_settings()
    decision = route_request(
        request.message,
        settings=settings,
        fast_mode=request.fast_mode,
        force_cloud=request.force_cloud,
    )

    system = get_system_prompt(decision.system_variant)
    messages = _build_messages(system, decision.user_prompt)
    num_predict = request.max_tokens or settings.ollama_num_predict
    num_ctx = request.num_ctx or settings.ollama_num_ctx

    ollama = _get_ollama()
    cloud = _get_cloud()

    async def _cloud_direct() -> AsyncIterator[str]:
        from app.core.fallback import StreamEvent, _sse_line

        text = await cloud.complete(messages, max_tokens=num_predict)
        yield _sse_line(
            StreamEvent(kind="replace", text=text, provider="cloud", model=settings.cloud_model)
        )
        yield _sse_line(
            StreamEvent(kind="done", provider="cloud", model=settings.cloud_model)
        )

    if decision.use_cloud:
        return StreamingResponse(_cloud_direct(), media_type="text/event-stream")

    async def _pipeline() -> AsyncIterator[str]:
        raw_stream = ollama.chat_stream(
            model=decision.ollama_model,
            messages=messages,
            num_predict=num_predict,
            num_ctx=num_ctx,
        )
        async for line in stream_with_early_abort(
            raw_stream,
            messages,
            model=decision.ollama_model,
            settings=settings,
            cloud_client=cloud,
        ):
            yield line

    return StreamingResponse(_pipeline(), media_type="text/event-stream")
