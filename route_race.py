# route_race.py — double appel stream léger quand le routeur est incertain

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, AsyncIterator, Callable

import requests

from fallback import check_early_refusal, iter_ollama_chat_stream

try:
    from config import (
        CLOUD_COMPLEXITY_THRESHOLD,
        FAST_MODEL,
        MODEL,
        QUALITY_MODEL,
        ROUTE_RACE_ENABLED,
        ROUTE_UNCERTAIN_BAND,
    )
    from local_model_policy import is_single_local_mode, local_ollama_model
except ImportError:
    CLOUD_COMPLEXITY_THRESHOLD = 5
    FAST_MODEL = MODEL = "qwen2.5:1.5b-instruct-q4_K_M"
    QUALITY_MODEL = "qwen2.5:3b-instruct-q4_K_M"
    ROUTE_RACE_ENABLED = True
    ROUTE_UNCERTAIN_BAND = 1

    def is_single_local_mode() -> bool:
        return False

    def local_ollama_model() -> str:
        return QUALITY_MODEL


def is_route_uncertain(
    score: int,
    route: Any,
    *,
    cloud_enabled: bool = False,
    cloud_quota_ok: bool = True,
    band: int | None = None,
) -> bool:
    """
    Vrai si le score est proche d'un seuil de bascule (fast/quality/cloud).
    """
    if is_single_local_mode():
        return False
    if route is None:
        return False
    b = band if band is not None else ROUTE_UNCERTAIN_BAND
    route_val = route.value if hasattr(route, "value") else str(route)

    if route_val == "local_fast" and score in (2, 3):
        return True
    if route_val == "local_quality" and score in (2, 3, 4):
        return True

    if cloud_enabled and cloud_quota_ok:
        low = CLOUD_COMPLEXITY_THRESHOLD - b
        high = CLOUD_COMPLEXITY_THRESHOLD + b
        if low <= score <= high and route_val in (
            "local_quality",
            "local_fast",
            "cloud",
        ):
            return True

    return False


def _race_models_for_route(route: Any) -> tuple[str, str]:
    """Paire de modèles — désactivée en mode un seul modèle local."""
    local = local_ollama_model()
    return local, local


def _valid_stream_delta(delta: str) -> bool:
    if not delta or delta.startswith("__HTTP_ERROR__"):
        return False
    return bool(delta.strip())


async def stream_sse_with_route_race(
    *,
    host: str,
    messages: list[dict[str, str]],
    options: dict[str, Any],
    keep_alive: str,
    timeout: int,
    route: Any,
    score: int,
    cloud_available_fn: Callable[[], bool],
    cloud_quota_ok_fn: Callable[[], bool],
    on_early_abort_stream: Callable[..., AsyncIterator[str]],
    **early_abort_kwargs: Any,
) -> AsyncIterator[str]:
    """
    Lance deux streams Ollama en parallèle ; relaie le premier flux valide.
    Ne bloque pas la boucle FastAPI (threads + asyncio.Queue).
    """
    if not ROUTE_RACE_ENABLED or not is_route_uncertain(
        score,
        route,
        cloud_enabled=cloud_available_fn(),
        cloud_quota_ok=cloud_quota_ok_fn(),
    ):
        async for chunk in on_early_abort_stream(
            host=host,
            messages=messages,
            options=options,
            keep_alive=keep_alive,
            timeout=timeout,
            cloud_available_fn=cloud_available_fn,
            cloud_quota_ok_fn=cloud_quota_ok_fn,
            **early_abort_kwargs,
        ):
            yield chunk
        return

    model_a, model_b = _race_models_for_route(route)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, str, str | None]] = asyncio.Queue()
    stop = threading.Event()
    started: dict[str, bool] = {"winner": False}
    winner_holder: dict[str, str | None] = {"name": None}

    def _feed(model: str) -> None:
        try:
            for delta in iter_ollama_chat_stream(
                host=host,
                model=model,
                messages=messages,
                options=options,
                keep_alive=keep_alive,
                timeout=timeout,
            ):
                if stop.is_set() and winner_holder["name"] != model:
                    break
                fut = asyncio.run_coroutine_threadsafe(
                    queue.put(("delta", model, delta)), loop
                )
                try:
                    fut.result(timeout=2.0)
                except Exception:
                    break
        except requests.Timeout:
            print(f"[RouteRace] timeout {model} ({timeout}s)")
        except requests.RequestException as exc:
            print(f"[RouteRace] {model} : {exc}")
        finally:
            asyncio.run_coroutine_threadsafe(
                queue.put(("done", model, None)), loop
            )

    threading.Thread(target=_feed, args=(model_a,), daemon=True, name="race-a").start()
    threading.Thread(target=_feed, args=(model_b,), daemon=True, name="race-b").start()

    yield f'data: {json.dumps({"race": True, "models": [model_a, model_b]}, ensure_ascii=False)}\n\n'

    buf = ""
    aborted = False
    pattern = ""
    active: str | None = None
    pending_done: set[str] = set()

    while True:
        if active and len(pending_done) >= 2:
            break
        try:
            kind, model, delta = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            stop.set()
            msg = (
                buf.strip()
                or f"Delai depasse ({timeout}s). Question plus courte ou desactive le stream."
            )
            yield f'data: {json.dumps({"replace": msg, "provider": "ollama"}, ensure_ascii=False)}\n\n'
            yield f'data: {json.dumps({"done": True, "provider": "ollama", "timeout": True, "response": msg}, ensure_ascii=False)}\n\n'
            return

        if kind == "done":
            pending_done.add(model)
            if active and model == active:
                break
            if not active and len(pending_done) >= 2:
                break
            continue

        if active and model != active:
            continue

        if not active:
            if not _valid_stream_delta(delta or ""):
                continue
            active = model
            winner_holder["name"] = model
            stop.set()
            if not started["winner"]:
                started["winner"] = True
                yield f'data: {json.dumps({"race_winner": model}, ensure_ascii=False)}\n\n'

        if delta.startswith("__HTTP_ERROR__"):
            if not active:
                continue
            yield f'data: {json.dumps({"error": delta}, ensure_ascii=False)}\n\n'
            stop.set()
            return

        buf += delta
        yield f'data: {json.dumps({"token": delta}, ensure_ascii=False)}\n\n'

        if len(buf) >= 8:
            hit, pattern = check_early_refusal(buf)
            if hit:
                aborted = True
                break

    stop.set()
    provider = "ollama"
    yield f'data: {json.dumps({"done": True, "provider": provider, "model": active or model_a, "early_aborted": aborted, "race": True}, ensure_ascii=False)}\n\n'
