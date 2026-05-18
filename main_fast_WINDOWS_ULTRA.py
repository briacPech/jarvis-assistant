# ========================================
# main_fast_WINDOWS_ULTRA.py
# Version ULTRA pour Windows (robuste)
# ========================================

import console_utf8  # noqa: F401  # UTF-8 console Windows (avant tout print)

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import re
import subprocess
from datetime import datetime
import os
import sys
import uuid
import threading
import queue
import time
from typing import Optional, AsyncIterator
import requests

# ========================================
# Import des modules locaux
# ========================================

try:
    from memory import Memory
    from config import (
        MODEL, FAST_MODEL, API_HOST, API_PORT, DEBUG, TTS_OUTPUT_DIR, TTS_CHUNK_CHARS,
        TTS_SPEAK_MAX_CHARS, TTS_ENGINE,
        API_TIMEOUT, OLLAMA_HOST, OLLAMA_NUM_PREDICT, OLLAMA_NUM_CTX, OLLAMA_KEEP_ALIVE,
        MEMORY_CONTEXT_TURNS, MEMORY_MAX_CHARS, UVICORN_RELOAD,
        FAST_MODEL, WAKE_MODEL, WAKE_MAX_TOKENS, WAKE_NUM_CTX,
        OLLAMA_NUM_GPU, OLLAMA_NUM_THREAD, QUALITY_MODEL, QUALITY_MIN_CHARS,
        ALLOW_HEAVY_MODELS, BLOCKED_MODEL_SUBSTRINGS,
        WEB_SEARCH_ENABLED, WEB_SEARCH_AUTO, WEB_SEARCH_WAKE,
        WEB_SEARCH_MAX_RESULTS, WEB_SEARCH_TIMEOUT,
        CLOUD_COMPLEXITY_THRESHOLD, CLOUD_HEAVY_THRESHOLD,
        CLOUD_MAX_TOKENS, CLOUD_MODEL, CLOUD_MODEL_HEAVY,
        FALLBACK_EARLY_ABORT_ENABLED,
        CONTEXT_SLIM_ENABLED,
        ROUTE_RACE_ENABLED,
        PROMPT_HYDRATION_ENABLED,
        FTS_PREFETCH_ENABLED,
        SKLEARN_ROUTER_ENABLED, LOCAL_COMMAND_REQUIRES_TIDAL,
        BRIEF_RESPONSES_DEFAULT, BRIEF_MAX_TOKENS, BRIEF_TTS_MAX_CHARS,
        REMINDERS_ENABLED, REMINDER_POLL_SEC, WEB_CACHE_TTL_SEC,
        TIDAL_ENABLED, STT_ENGINE,
        JARVIS_SEED_PERSONAL_FACT, JARVIS_PERSONAL_FACT, JARVIS_USER_NAME,
        JARVIS_USER_AVOID, PRE_LLM_PARALLEL, OLLAMA_STREAM_TIMEOUT,
    )
    from router import (
        decide_route,
        Route,
        analyze_query,
        RouterAnalysis,
        is_heavy_task,
        is_simple_chat,
    )
    from context_slimming import slim_messages
    from prompt_loader import get_system_prompt
    from fallback import (
        apply_cloud_fallback_if_needed,
        local_chat_with_early_abort_fallback,
        should_use_early_abort,
        stream_sse_with_early_abort,
    )
    from llm_client import (
        cloud_available,
        cloud_quota_ok,
        ask_cloud,
        is_ollama_failure,
        cloud_status,
        test_groq_connection,
    )
    ROUTING_AVAILABLE = True
    from local_model_policy import (
        coerce_ollama_model,
        evict_non_local_models,
        is_single_local_mode,
        local_ollama_model,
        ollama_keep_alive,
        upgrade_route_for_vram,
    )
except ImportError as e:
    print(f"ERREUR : Modules manquants")
    print(f"   Assure-toi que config.py et memory.py sont dans le meme dossier")
    print(f"   Erreur : {e}")
    ROUTING_AVAILABLE = False
    exit(1)

try:
    from tts import TextToSpeech
    tts_engine = TextToSpeech()
    TTS_ENABLED = True
except ImportError as e:
    tts_engine = None
    TTS_ENABLED = False
    print(f"[TTS] Desactive (module manquant) : {e}")

try:
    from web_search import needs_web_search, search_web, format_web_context, wants_forced_web
    WEB_SEARCH_AVAILABLE = True
except ImportError as e:
    WEB_SEARCH_AVAILABLE = False
    needs_web_search = search_web = format_web_context = wants_forced_web = None  # type: ignore
    print(f"[Web] Desactive (module manquant) : {e}")

try:
    from routeur_jarvis import aiguiller_requete, est_commande_locale

    SKLEARN_ROUTER_AVAILABLE = SKLEARN_ROUTER_ENABLED
except ImportError as e:
    aiguiller_requete = None  # type: ignore
    est_commande_locale = None  # type: ignore
    SKLEARN_ROUTER_AVAILABLE = False
    if SKLEARN_ROUTER_ENABLED:
        print(f"[Routeur] scikit-learn desactive : {e}")

try:
    from commande_locale import try_handle_local_command

    LOCAL_COMMANDS_AVAILABLE = True
except ImportError as e:
    try_handle_local_command = None  # type: ignore
    LOCAL_COMMANDS_AVAILABLE = False
    print(f"[Commandes] locales desactivees : {e}")

try:
    from tidal_actions import try_handle_tidal_command, mentions_tidal

    TIDAL_COMMANDS_AVAILABLE = True
except ImportError as e:
    try_handle_tidal_command = None  # type: ignore
    mentions_tidal = None  # type: ignore
    TIDAL_COMMANDS_AVAILABLE = False
    print(f"[Commandes] tidal/media desactivees : {e}")

# ========================================
# Initialiser FastAPI
# ========================================

try:
    from app.api.routes import router as _edge_api_router

    _EDGE_API_ROUTER = _edge_api_router
except ImportError:
    _EDGE_API_ROUTER = None

app = FastAPI(
    title="Jarvis API (WINDOWS ULTRA)",
    description="Assistant IA local - Version ultra-robuste pour Windows",
    version="3.0"
)

# CORS : accès depuis le Redmi / réseau local (192.168.x.x, 10.x.x.x)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permet l'accès depuis le réseau local
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

if _EDGE_API_ROUTER is not None:
    app.include_router(_EDGE_API_ROUTER, prefix="/api/v2")

_CHAT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis-chat.html")
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_AUDIO_DIR = os.path.join(_BASE_DIR, TTS_OUTPUT_DIR)
os.makedirs(_AUDIO_DIR, exist_ok=True)
app.mount("/audio", StaticFiles(directory=_AUDIO_DIR), name="audio")
_audio_jobs: dict[str, dict] = {}
_audio_done_events: dict[str, threading.Event] = {}
_tts_queue: queue.Queue = queue.Queue()


def _cap_text_for_speech(text: str, max_chars: Optional[int] = None) -> str:
    """Limite le total a lire (decoupe ensuite en morceaux Piper)."""
    text = (text or "").strip()
    if not text:
        return ""
    limit = max_chars if max_chars is not None else TTS_SPEAK_MAX_CHARS
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? ", "\n"):
        idx = cut.rfind(sep)
        if idx > 80:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "..."


def _tts_sync_timeout_sec(text: str) -> float:
    """Delai sync : assez long pour N morceaux Piper."""
    capped = _cap_text_for_speech(text)
    n_chunks = max(1, (len(capped) + TTS_CHUNK_CHARS - 1) // TTS_CHUNK_CHARS)
    return min(600.0, 50.0 + n_chunks * 14.0)


def _split_text_for_tts(text: str) -> list[str]:
    from tts import _split_sentences

    return _split_sentences((text or "").strip(), TTS_CHUNK_CHARS)


def _trim_context(context: str) -> str:
    if not context or len(context) <= MEMORY_MAX_CHARS:
        return context
    return context[-MEMORY_MAX_CHARS:].lstrip()


def _client_base_url(request: Request) -> str:
    host = request.url.hostname or "127.0.0.1"
    if host in ("0.0.0.0", "[::]", "::"):
        host = "127.0.0.1"
    port = request.url.port
    if port:
        return f"{request.url.scheme}://{host}:{port}"
    return f"{request.url.scheme}://{host}"


def _run_tts_job(job_id: str, text: str, base_url: str):
    chunks = _split_text_for_tts(text)
    if not chunks or not tts_engine:
        _audio_jobs[job_id] = {"status": "error", "audio_url": None, "audio_path": None, "audio_paths": []}
        evt = _audio_done_events.pop(job_id, None)
        if evt:
            evt.set()
        return

    rel_paths: list[str] = []
    n_chunks = len(chunks)
    for i, chunk in enumerate(chunks):
        filename = f"reply_{job_id}_{i:02d}.wav" if n_chunks > 1 else f"reply_{job_id}.wav"
        path = tts_engine.text_to_speech(chunk, output_file=filename)
        if path:
            rel_paths.append(f"/audio/{os.path.basename(path)}")
            first = rel_paths[0]
            done = i + 1 >= n_chunks
            _audio_jobs[job_id] = {
                "status": "ready" if done else "partial",
                "audio_url": f"{base_url}{first}",
                "audio_path": first,
                "audio_paths": list(rel_paths),
                "parts": len(rel_paths),
                "parts_total": n_chunks,
                "parts_ready": len(rel_paths),
            }
        else:
            print(f"[TTS] Echec morceau {i + 1}/{n_chunks} job {job_id}")

    if rel_paths:
        print(f"[TTS] Pret : {len(rel_paths)} partie(s) job {job_id}")
    else:
        _audio_jobs[job_id] = {"status": "error", "audio_url": None, "audio_path": None, "audio_paths": []}
        print(f"[TTS] Echec job {job_id}")
    evt = _audio_done_events.pop(job_id, None)
    if evt:
        evt.set()


def _tts_worker_loop():
    if os.name == "nt":
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass
    while True:
        item = _tts_queue.get()
        if item is None:
            break
        job_id, text, base_url = item
        try:
            _run_tts_job(job_id, text, base_url)
        except Exception as e:
            _audio_jobs[job_id] = {"status": "error", "audio_url": None, "audio_path": None}
            print(f"[TTS] Erreur job {job_id} : {e}")
            evt = _audio_done_events.pop(job_id, None)
            if evt:
                evt.set()
        finally:
            _tts_queue.task_done()


def _attach_audio_async(
    request: Request,
    payload: dict,
    text: str,
    speak: bool,
    tts_max_chars: Optional[int] = None,
):
    """Audio en arriere-plan : le texte part tout de suite (pas d'attente TTS)."""
    if not speak or not TTS_ENABLED:
        return
    job_id = uuid.uuid4().hex[:12]
    base = _client_base_url(request)
    spoken = _cap_text_for_speech(text, tts_max_chars)
    parts_total = max(1, (len(spoken) + TTS_CHUNK_CHARS - 1) // TTS_CHUNK_CHARS)
    _audio_jobs[job_id] = {
        "status": "pending",
        "audio_url": None,
        "audio_path": None,
        "parts_total": parts_total,
        "parts_ready": 0,
    }
    _tts_queue.put((job_id, spoken, base))
    payload["audio_job_id"] = job_id
    payload["audio_parts_total"] = parts_total
    if len((text or "").strip()) > len(spoken):
        payload["audio_truncated"] = True


def _attach_audio_sync(
    request: Request,
    payload: dict,
    text: str,
    speak: bool,
    tts_max_chars: Optional[int] = None,
):
    """Audio bloquant (agent vocal uniquement)."""
    if not speak or not TTS_ENABLED:
        return
    job_id = uuid.uuid4().hex[:12]
    base = _client_base_url(request)
    spoken = _cap_text_for_speech(text, tts_max_chars)
    done = threading.Event()
    _audio_done_events[job_id] = done
    _audio_jobs[job_id] = {"status": "pending", "audio_url": None, "audio_path": None}
    _tts_queue.put((job_id, spoken, base))
    tts_timeout = _tts_sync_timeout_sec(spoken)
    if not done.wait(timeout=tts_timeout):
        print(f"[TTS] Timeout job {job_id} apres {tts_timeout:.0f}s")
        payload["audio_error"] = True
        return
    job = _audio_jobs.get(job_id, {})
    if job.get("status") == "ready" and job.get("audio_path"):
        paths = job.get("audio_paths") or [job["audio_path"]]
        payload["audio_path"] = job["audio_path"]
        payload["audio_url"] = job.get("audio_url")
        payload["audio_paths"] = paths
        payload["audio_parts"] = len(paths)
        if len((text or "").strip()) > len(spoken):
            payload["audio_truncated"] = True
    else:
        payload["audio_error"] = True


def _ollama_options(
    predict: int,
    ctx: int,
    num_gpu: int | None = None,
    model: str | None = None,
) -> dict:
    opts = {
        "num_predict": predict,
        "num_ctx": ctx,
        "temperature": 0.6,
    }
    gpu = OLLAMA_NUM_GPU if num_gpu is None else num_gpu
    if gpu is not None:
        opts["num_gpu"] = gpu
    if OLLAMA_NUM_THREAD > 0:
        opts["num_thread"] = OLLAMA_NUM_THREAD
    use_model = (model or MODEL or FAST_MODEL).strip()
    try:
        from jarvis_bridge import merge_ollama_options

        return merge_ollama_options(opts, model=use_model or None)
    except ImportError:
        pass
    try:
        from ollama_refusal_opts import merge_anti_refusal_options

        return merge_anti_refusal_options(opts, model=use_model or None)
    except ImportError:
        return opts


@app.get("/tts/job/{job_id}")
def get_audio_job(job_id: str):
    job = _audio_jobs.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"status": "not_found"})
    if job["status"] in ("pending", "partial"):
        paths = job.get("audio_paths") or []
        body: dict = {
            "status": job["status"],
            "parts_total": job.get("parts_total"),
            "parts_ready": job.get("parts_ready", len(paths)),
        }
        if paths:
            body["audio_paths"] = paths
            body["audio_path"] = paths[0]
            body["audio_url"] = job.get("audio_url")
        return JSONResponse(status_code=202, content=body)
    if job["status"] == "ready" and (job.get("audio_path") or job.get("audio_url")):
        paths = job.get("audio_paths") or []
        if not paths and job.get("audio_path"):
            paths = [job["audio_path"]]
        return {
            "status": "ready",
            "audio_url": job.get("audio_url"),
            "audio_path": job.get("audio_path"),
            "audio_paths": paths,
            "parts": len(paths),
        }
    return JSONResponse(status_code=500, content={"status": "error"})


@app.get("/stt/health")
def stt_health():
    """Diagnostic micro serveur."""
    try:
        from stt import stt_health_info

        return stt_health_info()
    except ImportError as e:
        return {"ok": False, "error": str(e)}


@app.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """Transcription micro (webm Chrome -> wav -> Google STT)."""
    try:
        from stt import transcribe_audio_bytes
    except ImportError:
        return JSONResponse(
            status_code=501,
            content={"error": "Module STT manquant", "hint": "pip install -r requirements-stt.txt"},
        )
    data = await audio.read()
    text, err = transcribe_audio_bytes(data, audio.filename or "voice.webm")
    if text:
        return {"text": text}
    if err and err.startswith("pas compris"):
        return JSONResponse(status_code=200, content={"text": "", "error": err})
    return JSONResponse(
        status_code=501,
        content={
            "error": err or "Transcription impossible",
            "hint": "pip install -r requirements-stt.txt puis stop_jarvis_api.bat + start_jarvis_api.bat",
        },
    )


@app.get("/")
def chat_ui():
    """Interface web Jarvis Chat."""
    return FileResponse(
        _CHAT_HTML,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ========================================
# Initialiser la mÃ©moire
# ========================================

print("Initialisation memoire...")
memory = Memory()


def _seed_personal_memory() -> None:
    """Fait de style Briac / pote — une fois en base, reutilise a chaque chat."""
    if not JARVIS_SEED_PERSONAL_FACT:
        return
    marker = "tutoie-moi"
    if memory.ensure_personal_fact(
        JARVIS_PERSONAL_FACT,
        user_id="default",
        marker=marker,
    ):
        print(f"[Memoire] Profil personnel enregistre ({JARVIS_USER_NAME})")


_seed_personal_memory()
print("Memoire prete")
if REMINDERS_ENABLED:
    try:
        from reminders_service import start_reminder_loop

        start_reminder_loop(memory, poll_sec=REMINDER_POLL_SEC)
    except Exception as e:
        print(f"[Rappels] non demarres : {e}")
if TTS_ENABLED:
    print(f"TTS active ({TTS_ENGINE}, voix: {tts_engine.voice}, dossier: {TTS_OUTPUT_DIR})")
    threading.Thread(target=_tts_worker_loop, daemon=True, name="jarvis-tts").start()
else:
    print("TTS desactive")


def _warmup_ollama():
    """Precharge UNIQUEMENT le modele local 3B (VRAM GTX 1650)."""
    if is_single_local_mode():
        evict_non_local_models()
    name = (
        local_ollama_model()
        if is_single_local_mode()
        else (MODEL or FAST_MODEL).strip()
    )
    if not name:
        return
    try:
        requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": name,
                "prompt": " ",
                "stream": False,
                "keep_alive": ollama_keep_alive(),
                "options": _ollama_options(
                    1, min(OLLAMA_NUM_CTX, 2048), model=name
                ),
            },
            timeout=90,
        )
        print(
            f"[Ollama] Modele precharge : {name} "
            f"(keep_alive={ollama_keep_alive()})"
        )
    except Exception as e:
        print(f"[Ollama] Prechargement {name} : {e}")


threading.Thread(target=_warmup_ollama, daemon=True).start()

# ========================================
# Fonction Ollama - ULTRA robuste pour Windows
# ========================================

def _clamp_int(value: Optional[int], default: int, min_v: int, max_v: int) -> int:
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_v, min(max_v, n))


def list_ollama_models():
    """Liste les modeles Ollama installes (nom + taille)."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        r.raise_for_status()
        out = []
        for m in r.json().get("models", []):
            size_bytes = m.get("size") or 0
            size_mb = round(size_bytes / (1024 * 1024))
            if size_mb >= 1024:
                size_label = f"{size_mb / 1024:.1f} Go"
            else:
                size_label = f"{size_mb} Mo"
            details = m.get("details") or {}
            out.append({
                "name": m.get("name", ""),
                "size_mb": size_mb,
                "size_label": size_label,
                "parameter_size": details.get("parameter_size", ""),
            })
        return sorted(out, key=lambda x: x["name"])
    except Exception as e:
        if DEBUG:
            print(f"[Ollama] Liste modeles impossible : {e}")
        return [{"name": MODEL, "size_mb": 0, "size_label": "?", "parameter_size": ""}]


# Prompts systeme : prompts/system_*.txt (voir prompt_loader.py)


def _should_use_web(user_text: str, web: Optional[bool]) -> bool:
    if not WEB_SEARCH_ENABLED or not WEB_SEARCH_AVAILABLE:
        return False
    if ROUTING_AVAILABLE and is_simple_chat(user_text):
        return False
    if web is True:
        return True
    if web is False:
        return False
    if wants_forced_web and wants_forced_web(user_text):
        return True
    return WEB_SEARCH_AUTO and needs_web_search(user_text)


def _fetch_web_context(
    user_text: str, *, slim: bool = False
) -> tuple[str, list[dict], Optional[str]]:
    max_r = min(3, WEB_SEARCH_MAX_RESULTS) if slim else WEB_SEARCH_MAX_RESULTS
    results, err = search_web(
        user_text,
        max_results=max_r,
        timeout_sec=WEB_SEARCH_TIMEOUT,
    )
    ctx = format_web_context(results, max_snippet=220 if slim else 500)
    return ctx, results, err


def _is_blocked_model(name: str) -> bool:
    low = (name or "").lower()
    return any(b in low for b in BLOCKED_MODEL_SUBSTRINGS)


def _pick_chat_model(
    user_text: str,
    fast_mode: bool,
    model_override: Optional[str],
) -> str:
    if is_single_local_mode():
        return local_ollama_model()
    if fast_mode:
        return WAKE_MODEL
    if len((user_text or "").strip()) >= QUALITY_MIN_CHARS:
        return QUALITY_MODEL
    return (MODEL or FAST_MODEL).strip() or FAST_MODEL


def _resolve_chat_model(
    user_text: str,
    fast_mode: bool,
    model_override: Optional[str],
) -> str:
    """Routage auto sauf si modele explicite autorise (pas gemma par accident)."""
    raw = (model_override or "").strip()
    if not raw or raw.lower() in ("auto", "default"):
        return _pick_chat_model(user_text, fast_mode, None)
    if not ALLOW_HEAVY_MODELS and _is_blocked_model(raw):
        picked = _pick_chat_model(user_text, fast_mode, None)
        print(
            f"[Ollama] Modele client '{raw}' ignore (trop lourd) -> {picked}"
        )
        return picked
    return coerce_ollama_model(raw)


def _semantic_memory_snippet(
    user_id: str,
    user_text: str,
    analysis: Optional["RouterAnalysis"] = None,
) -> str:
    try:
        from memory_summary import embed_text
        from vector_memory import is_enabled, recall, limit_words
        from perf_prellm import needs_semantic_recall

        if not is_enabled() or not needs_semantic_recall(user_text, analysis):
            return ""
        emb = embed_text(user_text)
        if not emb:
            return ""
        hits = recall(emb, user_id=user_id, k=3)
        if not hits:
            return ""
        return "Souvenirs proches :\n" + "\n".join(
            f"- {limit_words(h)}" for h in hits
        )
    except Exception:
        return ""


def _fts_prefetch_snippet(user_id: str, user_text: str) -> str:
    if not FTS_PREFETCH_ENABLED:
        return ""
    try:
        from fts_prefetch import format_fts_context, prefetch_micro_context

        hits, ms = prefetch_micro_context(user_text, user_id)
        if DEBUG and hits:
            print(f"[FTS5] {len(hits)} extraits en {ms:.2f} ms")
        return format_fts_context(hits)
    except Exception:
        return ""


def _build_chat_messages(
    user_id: str,
    user_text: str,
    fast_mode: bool = False,
    web_context: str = "",
    route: Optional["Route"] = None,
    analysis: Optional["RouterAnalysis"] = None,
    fts_context: str = "",
    brief: bool = False,
) -> list:
    simple_chat = (
        not fast_mode
        and analysis is not None
        and ROUTING_AVAILABLE
        and is_simple_chat(user_text, analysis)
    )
    facts = memory.get_facts_for_prompt(user_id, limit=8 if simple_chat else 15)
    summaries = memory.get_session_summaries(user_id, limit=1 if simple_chat else 2)
    fts_snippet = fts_context or (
        ""
        if fast_mode or simple_chat
        else _fts_prefetch_snippet(user_id, user_text)
    )
    semantic = (
        ""
        if fast_mode or simple_chat
        else _semantic_memory_snippet(user_id, user_text, analysis)
    )
    try:
        from jarvis_bridge import get_system_prompt_for_route

        system = get_system_prompt_for_route(
            route,
            fast_mode=fast_mode,
            legacy_fn=get_system_prompt,
        )
    except ImportError:
        system = get_system_prompt(route, fast_mode=fast_mode)
    if brief or fast_mode or simple_chat:
        system += (
            "\n\nReponds en 1 ou 2 phrases maximum, en francais, sans listes longues."
        )
    if web_context:
        system += (
            "\n\nTu as recu des extraits web ci-dessous : "
            "appuie-toi dessus pour les faits actuels, cite la source, "
            "ne invente pas ce qui n'y figure pas."
        )
    if summaries:
        system += "\n\nResumes de sessions precedentes :\n" + "\n---\n".join(
            summaries
        )
    if fts_snippet:
        system += "\n\n" + fts_snippet
    if semantic:
        system += "\n\n" + semantic
    if facts:
        system += "\n\nFaits memorises :\n" + "\n".join(f"- {f}" for f in facts)
    if JARVIS_USER_AVOID:
        system += (
            f"\n\nNe jamais confondre l'utilisateur avec : {JARVIS_USER_AVOID}."
        )
    if web_context:
        system += "\n\n" + web_context

    messages = [{"role": "system", "content": system}]
    if fast_mode:
        turns, cap = 3, 350
    elif simple_chat:
        turns, cap = 1, 200
    else:
        turns, cap = MEMORY_CONTEXT_TURNS, 800
    history = memory.get_conversation_history(user_id, limit=turns)
    for entry in reversed(history):
        u = (entry.get("user") or "").strip()
        a = (entry.get("jarvis") or "").strip()
        if u:
            messages.append({"role": "user", "content": u[:cap]})
        if a:
            messages.append({"role": "assistant", "content": a[:cap]})
    final_user = user_text
    if PROMPT_HYDRATION_ENABLED and not fast_mode and not simple_chat:
        try:
            from jarvis_bridge import hydrate_user_message

            final_user, hydrated = hydrate_user_message(
                user_text, analysis, fast_mode=fast_mode
            )
            if hydrated and DEBUG:
                print("[Hydration] Squelette pedagogique applique")
        except ImportError:
            try:
                from prompt_hydration import hydrate_user_prompt

                final_user, hydrated = hydrate_user_prompt(user_text, analysis)
            except ImportError:
                pass
    messages.append({"role": "user", "content": final_user})
    if CONTEXT_SLIM_ENABLED:
        messages, slim_meta = slim_messages(messages)
        if slim_meta.get("slimmed") and DEBUG:
            print(
                f"[ContextSlim] {slim_meta['tokens_before']} -> "
                f"{slim_meta['tokens_after']} tokens "
                f"(max {slim_meta['max_tokens']})"
            )
    return messages


def _clean_ollama_text(answer: str) -> str:
    import re
    answer = (answer or "").strip()
    answer = re.sub(r'\x1b\[[0-9;]*[mKHJA-Z]', '', answer)
    answer = re.sub(r'\033\[[0-9;]*[mKHJA-Z]', '', answer)
    answer = answer.replace('\r\n', '\n').replace('\r', '\n')
    return '\n'.join(line.strip() for line in answer.split('\n') if line.strip())


def ask_ollama_chat(
    messages: list,
    model: str = MODEL,
    max_tokens: Optional[int] = None,
    num_ctx: Optional[int] = None,
) -> str:
    """Appelle Ollama /api/chat avec historique et systeme."""
    try:
        predict = _clamp_int(max_tokens, OLLAMA_NUM_PREDICT, 32, 8192)
        ctx = _clamp_int(num_ctx, OLLAMA_NUM_CTX, 512, 131072)
        use_model = (model or MODEL).strip() or MODEL

        if DEBUG:
            print(f"[Ollama] chat model={use_model} msgs={len(messages)} max_tokens={predict}")

        payload = {
            "model": use_model,
            "messages": messages,
            "stream": False,
            "keep_alive": ollama_keep_alive(),
            "options": _ollama_options(predict, ctx, model=use_model),
        }

        t0 = time.perf_counter()
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=API_TIMEOUT)
        if r.status_code != 200 and "num_gpu" in (r.text or "").lower():
            print("[Ollama] Echec GPU — nouvel essai en CPU (num_gpu=0)")
            payload["options"] = _ollama_options(
                predict, ctx, num_gpu=0, model=use_model
            )
            r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=API_TIMEOUT)
        print(f"[Perf] Ollama {use_model} : {time.perf_counter() - t0:.1f}s")
        if r.status_code != 200:
            return f"Erreur Ollama HTTP {r.status_code}: {r.text[:200]}"

        data = r.json()
        answer = _clean_ollama_text((data.get("message") or {}).get("content", ""))
        return answer if answer else "Reponse vide ou invalide"

    except requests.exceptions.ConnectionError:
        return "ERREUR : Ollama inaccessible. Lance 'ollama serve' ou verifie OLLAMA_HOST."
    except requests.exceptions.Timeout:
        return f"ERREUR : Ollama timeout ({API_TIMEOUT}s)"
    except Exception as e:
        return f"ERREUR : {str(e)}"


def _is_explicit_local_model(model_override: Optional[str]) -> bool:
    raw = (model_override or "").strip()
    if not raw or raw.lower() in ("auto", "default"):
        return False
    if not ALLOW_HEAVY_MODELS and _is_blocked_model(raw):
        return False
    return True


def _generate_chat_response(
    messages: list,
    user_text: str,
    *,
    fast_mode: bool,
    model_override: Optional[str],
    max_tokens: Optional[int],
    num_ctx: Optional[int],
    web_used: bool,
    force_cloud: Optional[bool] = None,
    pre_route: Optional["Route"] = None,
    pre_analysis: Optional["RouterAnalysis"] = None,
) -> tuple[str, str, dict]:
    """Route local/cloud, generation, fallback Groq si Ollama echoue."""
    if fast_mode:
        predict = _clamp_int(max_tokens, WAKE_MAX_TOKENS, 32, 512)
        ctx = _clamp_int(num_ctx, WAKE_NUM_CTX, 512, 8192)
    else:
        predict = _clamp_int(max_tokens, OLLAMA_NUM_PREDICT, 32, 8192)
        ctx = _clamp_int(num_ctx, OLLAMA_NUM_CTX, 512, 131072)

    meta: dict = {
        "route": "local_fast",
        "complexity_score": 0,
        "provider": "ollama",
        "cloud_available": ROUTING_AVAILABLE and cloud_available(),
    }

    if not ROUTING_AVAILABLE:
        use_model = _resolve_chat_model(user_text, fast_mode, model_override)
        text = ask_ollama_chat(
            messages, model=use_model, max_tokens=predict, num_ctx=ctx
        )
        meta["model"] = use_model
        return text, use_model, meta

    explicit_local = _is_explicit_local_model(model_override)
    if pre_route is not None and pre_analysis is not None:
        route, score, analysis = pre_route, pre_analysis.complexity_score, pre_analysis
    else:
        route, score, analysis = decide_route(
            user_text,
            fast_mode=fast_mode,
            web_used=web_used,
            cloud_enabled=cloud_available(),
            cloud_quota_ok=cloud_quota_ok(),
            force_cloud=force_cloud,
            explicit_local=explicit_local,
        )
    meta["route"] = route.value
    meta["complexity_score"] = score
    meta["intent"] = analysis.intent.value
    meta["requires_development"] = analysis.requires_development

    simple_chat = is_simple_chat(user_text, analysis)
    route = upgrade_route_for_vram(
        route,
        score,
        cloud_enabled=cloud_available(),
        cloud_quota_ok=cloud_quota_ok(),
        is_heavy_fn=is_heavy_task,
        text=user_text,
        analysis=analysis,
    )
    meta["route"] = route.value
    if simple_chat:
        meta["simple_chat"] = True
        predict = min(predict, WAKE_MAX_TOKENS, BRIEF_MAX_TOKENS)
        ctx = min(ctx, WAKE_NUM_CTX)
    if is_single_local_mode() and route not in (Route.CLOUD, Route.CLOUD_HEAVY):
        meta["single_local_model"] = local_ollama_model()

    if route in (Route.CLOUD, Route.CLOUD_HEAVY):
        heavy = route == Route.CLOUD_HEAVY
        print(f"[Route] cloud ({'heavy' if heavy else 'std'}) score={score}")
        text, cloud_model = ask_cloud(
            messages,
            heavy=heavy,
            max_tokens=min(predict, CLOUD_MAX_TOKENS) if not fast_mode else predict,
            route_label=route.value,
        )
        if is_ollama_failure(text):
            print(f"[Fallback] Groq echoue -> Ollama local (3B unique)")
            use_model = local_ollama_model()
            text = ask_ollama_chat(
                messages, model=use_model, max_tokens=predict, num_ctx=ctx
            )
            meta["route"] = "cloud_failed_local"
            meta["provider"] = "ollama"
            meta["model"] = use_model
            return text, use_model, meta
        meta["provider"] = "groq"
        meta["model"] = cloud_model or (CLOUD_MODEL_HEAVY if heavy else CLOUD_MODEL)
        return text, meta["model"], meta

    if explicit_local:
        use_model = coerce_ollama_model((model_override or "").strip())
    elif is_single_local_mode():
        use_model = local_ollama_model()
    elif route == Route.LOCAL_WAKE:
        use_model = WAKE_MODEL
    elif route == Route.LOCAL_QUALITY:
        use_model = QUALITY_MODEL
    else:
        use_model = _resolve_chat_model(user_text, fast_mode, None)

    print(f"[Route] {route.value} score={score} intent={analysis.intent.value} -> {use_model}")

    use_stream_abort = (
        not simple_chat
        and FALLBACK_EARLY_ABORT_ENABLED
        and should_use_early_abort(fast_mode=fast_mode, route_was_cloud=False)
        and cloud_available()
    )
    if use_stream_abort:
        try:
            stream_result = local_chat_with_early_abort_fallback(
                host=OLLAMA_HOST,
                model=use_model,
                messages=messages,
                options=_ollama_options(predict, ctx, model=use_model),
                keep_alive=ollama_keep_alive(),
                timeout=API_TIMEOUT,
                clean_fn=_clean_ollama_text,
                user_text=user_text,
                requires_development=analysis.requires_development,
                complexity_score=score,
                cloud_available_fn=cloud_available,
                cloud_quota_ok_fn=cloud_quota_ok,
                ask_cloud_fn=ask_cloud,
                heavy=score >= CLOUD_HEAVY_THRESHOLD,
                max_tokens=min(predict, CLOUD_MAX_TOKENS),
                use_early_abort=True,
            )
        except requests.Timeout:
            stream_result = None
            text = f"ERREUR : Ollama timeout ({API_TIMEOUT}s)"
            print(f"[Ollama] timeout {API_TIMEOUT}s -> fallback cloud si dispo")
        except requests.RequestException as e:
            stream_result = None
            text = f"ERREUR : Ollama ({e.__class__.__name__})"
            print(f"[Ollama] {e.__class__.__name__} -> fallback cloud si dispo")
        else:
            text = stream_result.text
        if stream_result is not None and stream_result.early_aborted:
            print(
                f"[Early-Abort] Refus detecte ({stream_result.matched_pattern})"
                + (" -> Groq" if stream_result.post_fallback else " (cloud indisponible)")
            )
        if stream_result is not None and stream_result.post_fallback:
            meta["route"] = "cloud_early_abort"
            meta["provider"] = "groq"
            meta["model"] = stream_result.cloud_model or CLOUD_MODEL
            meta["fallback_reason"] = stream_result.decision.reason
            return text, meta["model"], meta
    else:
        text = ask_ollama_chat(
            messages, model=use_model, max_tokens=predict, num_ctx=ctx
        )

    if not fast_mode and not is_ollama_failure(text):
        text, fb_decision, fb_model = apply_cloud_fallback_if_needed(
            text,
            user_text,
            messages,
            requires_development=analysis.requires_development,
            complexity_score=score,
            route_was_local=True,
            cloud_available_fn=cloud_available,
            cloud_quota_ok_fn=cloud_quota_ok,
            ask_cloud_fn=ask_cloud,
            heavy=score >= CLOUD_HEAVY_THRESHOLD,
            max_tokens=min(predict, CLOUD_MAX_TOKENS),
        )
        if fb_decision.should_fallback and not is_ollama_failure(text):
            print(
                f"[Fallback] Refus/court local -> Groq ({fb_decision.reason}"
                f"{':' + fb_decision.matched_pattern if fb_decision.matched_pattern else ''})"
            )
            meta["route"] = "cloud_refusal_fallback"
            meta["provider"] = "groq"
            meta["model"] = fb_model
            meta["fallback_reason"] = fb_decision.reason
            return text, meta["model"], meta

    if (
        not fast_mode
        and is_ollama_failure(text)
        and cloud_available()
        and cloud_quota_ok()
    ):
        print(f"[Fallback] Ollama -> Groq (score={score})")
        heavy = score >= CLOUD_HEAVY_THRESHOLD
        text, cloud_model = ask_cloud(
            messages,
            heavy=heavy,
            max_tokens=min(predict, CLOUD_MAX_TOKENS),
            route_label="cloud_fallback",
        )
        meta["route"] = "cloud_fallback"
        meta["provider"] = "groq"
        meta["model"] = cloud_model or CLOUD_MODEL
        return text, meta["model"], meta

    meta["model"] = use_model
    return text, use_model, meta


def _assistant_meta_for_mode(
    fast_mode: bool,
    model: Optional[str],
    max_tokens: Optional[int],
    num_ctx: Optional[int],
) -> tuple[str, int, int, dict]:
    if fast_mode:
        use_model = (model or WAKE_MODEL).strip() or WAKE_MODEL
        predict = _clamp_int(max_tokens, WAKE_MAX_TOKENS, 32, 512)
        ctx = _clamp_int(num_ctx, WAKE_NUM_CTX, 512, 8192)
    else:
        use_model = (model or MODEL).strip() or MODEL
        predict = _clamp_int(max_tokens, OLLAMA_NUM_PREDICT, 32, 8192)
        ctx = _clamp_int(num_ctx, OLLAMA_NUM_CTX, 512, 131072)
    web_meta: dict = {"web_used": False, "web_sources": [], "web_error": None}
    return use_model, predict, ctx, web_meta


def _try_media_handlers(user_text: str) -> tuple[bool, str, dict]:
    """Volume / pause / lecture Tidal — sans LLM."""
    if TIDAL_COMMANDS_AVAILABLE and try_handle_tidal_command:
        handled, reply, meta = try_handle_tidal_command(user_text)
        if handled and reply:
            meta["tidal_handled"] = True
            return True, reply, meta
    return False, "", {}


def _phrase_triggers_local_command(user_text: str) -> bool:
    """Gate : commandes PC/media seulement si « tidal » est prononce."""
    raw = (user_text or "").strip()
    if not raw or not TIDAL_COMMANDS_AVAILABLE or not mentions_tidal:
        return False
    if LOCAL_COMMAND_REQUIRES_TIDAL:
        return mentions_tidal(raw)
    if mentions_tidal(raw):
        return True
    try:
        from tidal_actions import is_media_command

        return is_media_command(raw)
    except ImportError:
        return False


def _try_local_command_gate(
    user_text: str,
    user_id: str,
    fast_mode: bool,
    model: Optional[str],
    max_tokens: Optional[int],
    num_ctx: Optional[int],
) -> tuple[str, str, int, int, dict] | None:
    """Commandes Tidal (volume, pause, lecture) sans LLM si « tidal » dans la phrase."""
    if not _phrase_triggers_local_command(user_text):
        return None

    use_model, predict, ctx, web_meta = _assistant_meta_for_mode(
        fast_mode, model, max_tokens, num_ctx
    )
    web_meta["intent_gate"] = "commande"
    web_meta["tidal_keyword"] = True
    web_meta["sklearn_router"] = False

    handled, local_reply, action_meta = _try_media_handlers(user_text)
    if handled and local_reply:
        web_meta.update(action_meta)
        action = action_meta.get("tidal_action") or action_meta.get("local_action")
        print(f"[Routeur] tidal -> {action} | {local_reply[:80]}")
        from memory_summary import summarize_transcript

        memory.add_conversation(
            user_msg=user_text,
            jarvis_msg=local_reply,
            user_id=user_id,
            summarize_fn=summarize_transcript,
        )
        return local_reply, use_model, predict, ctx, web_meta

    reply = (
        "J'ai entendu Tidal, mais je n'ai pas reconnu la commande. "
        "Essaie : « Tidal, monte le volume », « Tidal, pause », "
        "« Tidal, joue Daft Punk »."
    )
    print(f"[Routeur] tidal non gere : {user_text[:80]}")
    from memory_summary import summarize_transcript

    memory.add_conversation(
        user_msg=user_text,
        jarvis_msg=reply,
        user_id=user_id,
        summarize_fn=summarize_transcript,
    )
    return reply, use_model, predict, ctx, web_meta


def _run_assistant(
    user_text: str,
    user_id: str,
    model: Optional[str],
    max_tokens: Optional[int],
    num_ctx: Optional[int],
    fast_mode: bool = False,
    web: Optional[bool] = None,
    force_cloud: Optional[bool] = None,
    brief: bool = False,
) -> tuple[str, str, int, int, dict]:
    """Genere une reponse et la sauvegarde en memoire."""
    use_brief = brief or BRIEF_RESPONSES_DEFAULT or fast_mode

    if REMINDERS_ENABLED:
        try:
            from reminders_service import try_handle_reminder

            rh, rreply = try_handle_reminder(
                user_text,
                user_id,
                add_reminder_fn=memory.add_reminder,
                get_reminders_fn=memory.get_reminders,
            )
            if rh and rreply:
                use_model, predict, ctx, web_meta = _assistant_meta_for_mode(
                    fast_mode, model, max_tokens, num_ctx
                )
                web_meta["reminder_handled"] = True
                from memory_summary import summarize_transcript

                memory.add_conversation(
                    user_msg=user_text,
                    jarvis_msg=rreply,
                    user_id=user_id,
                    summarize_fn=summarize_transcript,
                )
                return rreply, use_model, predict, ctx, web_meta
        except ImportError:
            pass

    gated = _try_local_command_gate(
        user_text, user_id, fast_mode, model, max_tokens, num_ctx
    )
    if gated is not None:
        return gated

    try:
        from memory_recall import is_memory_recall_request, reply_from_stored_facts

        if is_memory_recall_request(user_text):
            mem_reply = reply_from_stored_facts(
                memory.get_facts_for_prompt(user_id, limit=12)
            )
            if mem_reply is not None:
                use_model, predict, ctx, web_meta = _assistant_meta_for_mode(
                    fast_mode, model, max_tokens, num_ctx
                )
                web_meta["memory_recall"] = True
                web_meta["route"] = "memory_facts"
                web_meta["provider"] = "memory"
                print("[Route] memory_recall (faits SQLite, sans LLM)")
                from memory_summary import summarize_transcript

                memory.add_conversation(
                    user_msg=user_text,
                    jarvis_msg=mem_reply,
                    user_id=user_id,
                    summarize_fn=summarize_transcript,
                )
                return mem_reply, use_model, predict, ctx, web_meta
    except ImportError:
        pass

    use_model, predict, ctx, web_meta = _assistant_meta_for_mode(
        fast_mode, model, max_tokens, num_ctx
    )
    web_meta["brief"] = use_brief
    if use_brief:
        cap = BRIEF_MAX_TOKENS
        if max_tokens is not None:
            predict = min(predict, _clamp_int(max_tokens, cap, 32, cap))
        else:
            predict = min(predict, cap)
    use_web = _should_use_web(user_text, web)
    skip_fts = ROUTING_AVAILABLE and is_simple_chat(user_text)
    web_context = ""
    fts_hits: list = []
    fts_ms = 0.0
    fts_ctx_str = ""
    t0_ctx = time.perf_counter()
    slim_web = not (
        ROUTING_AVAILABLE and cloud_available() and cloud_quota_ok()
    )
    do_fts = FTS_PREFETCH_ENABLED and not fast_mode and not skip_fts
    if PRE_LLM_PARALLEL and (use_web or do_fts):
        from perf_prellm import gather_pre_llm

        bundle = gather_pre_llm(
            user_text,
            user_id,
            fast_mode=fast_mode,
            use_web=use_web,
            skip_fts=skip_fts,
            fetch_web_fn=_fetch_web_context,
            web_slim=slim_web,
        )
        web_context = bundle.web_context
        web_meta["web_used"] = bool(bundle.web_sources)
        web_meta["web_sources"] = bundle.web_sources
        web_meta["web_error"] = bundle.web_error
        fts_hits, fts_ms, fts_ctx_str = (
            bundle.fts_hits,
            bundle.fts_ms,
            bundle.fts_ctx_str,
        )
    else:
        if use_web:
            web_context, sources, web_err = _fetch_web_context(
                user_text, slim=slim_web
            )
            web_meta["web_used"] = bool(sources)
            web_meta["web_sources"] = sources
            web_meta["web_error"] = web_err
        if do_fts:
            try:
                from fts_prefetch import format_fts_context, prefetch_micro_context

                fts_hits, fts_ms = prefetch_micro_context(user_text, user_id)
                fts_ctx_str = format_fts_context(fts_hits)
            except ImportError:
                pass
    if DEBUG and (web_meta.get("web_used") or fts_hits):
        print(
            f"[Perf] pre-LLM {time.perf_counter() - t0_ctx:.2f}s "
            f"web={len(web_meta.get('web_sources') or [])} fts={len(fts_hits)}"
        )

    _fact_msg = (user_text or "").strip()
    if _fact_msg and (
        not fast_mode
        or len(_fact_msg) > 20
        or re.search(r"\bretiens\b|\bsouviens\b|\bmémoire\b", _fact_msg, re.I)
    ):
        memory.try_extract_fact(user_text, user_id)

    web_used = bool(web_meta.get("web_used"))

    chat_route: Optional[Route] = None
    chat_analysis: Optional[RouterAnalysis] = None
    if ROUTING_AVAILABLE:
        chat_analysis = analyze_query(
            user_text,
            web_used=web_used,
            fts_hints=fts_hits,
            fts_elapsed_ms=fts_ms,
        )
        chat_route, _sc, chat_analysis = decide_route(
            user_text,
            fast_mode=fast_mode,
            web_used=web_used,
            cloud_enabled=cloud_available(),
            cloud_quota_ok=cloud_quota_ok(),
            force_cloud=force_cloud,
            explicit_local=_is_explicit_local_model(model),
            analysis=chat_analysis,
        )
        chat_route = upgrade_route_for_vram(
            chat_route,
            chat_analysis.complexity_score,
            cloud_enabled=cloud_available(),
            cloud_quota_ok=cloud_quota_ok(),
            is_heavy_fn=is_heavy_task,
            text=user_text,
            analysis=chat_analysis,
        )

    messages = _build_chat_messages(
        user_id,
        user_text,
        fast_mode=fast_mode,
        web_context=web_context,
        route=chat_route,
        analysis=chat_analysis,
        fts_context=fts_ctx_str,
        brief=use_brief,
    )
    if DEBUG:
        print(f"[Memoire] {len(messages)-2} echanges + {len(memory.get_facts(user_id))} faits")

    response, use_model, route_meta = _generate_chat_response(
        messages,
        user_text,
        fast_mode=fast_mode,
        model_override=model,
        max_tokens=max_tokens,
        num_ctx=num_ctx,
        web_used=web_used,
        force_cloud=force_cloud,
        pre_route=chat_route,
        pre_analysis=chat_analysis,
    )
    web_meta.update(route_meta)
    from memory_summary import summarize_transcript

    memory.add_conversation(
        user_msg=user_text,
        jarvis_msg=response,
        user_id=user_id,
        summarize_fn=summarize_transcript,
    )
    return response, use_model, predict, ctx, web_meta


# ========================================
# Endpoints de base
# ========================================

@app.get("/api")
def root():
    """Statut API (JSON)"""
    return {
        "name": "Jarvis API (WINDOWS ULTRA)",
        "status": "EN LIGNE",
        "model": MODEL,
        "max_tokens": OLLAMA_NUM_PREDICT,
        "num_ctx": OLLAMA_NUM_CTX,
        "memory": "ACTIVEE",
        "web_search": WEB_SEARCH_ENABLED and WEB_SEARCH_AVAILABLE,
        "cloud": cloud_status() if ROUTING_AVAILABLE else {"enabled": False},
        "version": "3.1 - Hybride local + Groq",
        "docs": "http://localhost:8000/docs"
    }


@app.get("/models")
def get_models():
    """Modeles Ollama disponibles (pour le select HTML)."""
    return {
        "default_model": MODEL,
        "models": list_ollama_models(),
    }


@app.get("/settings")
def get_settings():
    """Parametres par defaut du serveur."""
    return {
        "default_model": MODEL,
        "fast_model": FAST_MODEL,
        "wake_model": WAKE_MODEL,
        "quality_model": QUALITY_MODEL,
        "default_max_tokens": OLLAMA_NUM_PREDICT,
        "default_num_ctx": OLLAMA_NUM_CTX,
        "max_tokens_options": [128, 256, 512, 1024, 2048, 4096, 8192],
        "num_ctx_options": [1024, 2048, 4096, 8192, 16384],
        "web_search_enabled": WEB_SEARCH_ENABLED and WEB_SEARCH_AVAILABLE,
        "web_search_auto": WEB_SEARCH_AUTO,
        "web_search_wake": WEB_SEARCH_WAKE,
        "web_cache_ttl_sec": WEB_CACHE_TTL_SEC,
        "stt_engine": STT_ENGINE,
        "brief_default": BRIEF_RESPONSES_DEFAULT,
        "reminders_enabled": REMINDERS_ENABLED,
        "cloud": cloud_status() if ROUTING_AVAILABLE else {"enabled": False},
        "cloud_complexity_threshold": CLOUD_COMPLEXITY_THRESHOLD,
    }


@app.get("/web/search")
def web_search_endpoint(q: str, max_results: Optional[int] = None):
    """Test recherche DuckDuckGo (diagnostic)."""
    if not WEB_SEARCH_AVAILABLE:
        return JSONResponse(
            status_code=501,
            content={"error": "web_search indisponible", "hint": "pip install ddgs"},
        )
    n = max_results or WEB_SEARCH_MAX_RESULTS
    results, err = search_web(q, max_results=n, timeout_sec=WEB_SEARCH_TIMEOUT)
    return {
        "query": q,
        "count": len(results),
        "results": results,
        "error": err,
    }


@app.get("/web/health")
def web_health():
    """Etat module recherche web."""
    ok = WEB_SEARCH_ENABLED and WEB_SEARCH_AVAILABLE
    err = None
    if ok:
        try:
            results, err = search_web("test jarvis", max_results=1, timeout_sec=8.0)
            ok = bool(results) or err is None
        except Exception as e:
            ok = False
            err = str(e)
    return {
        "enabled": WEB_SEARCH_ENABLED,
        "available": WEB_SEARCH_AVAILABLE,
        "auto": WEB_SEARCH_AUTO,
        "ok": ok,
        "error": err,
    }


@app.get("/cloud/status")
def get_cloud_status():
    """Etat Groq / quota (sans exposer la cle API)."""
    if not ROUTING_AVAILABLE:
        return {"enabled": False, "error": "routing modules unavailable"}
    return cloud_status()


@app.get("/cloud/test")
def get_cloud_test():
    """Test Groq en direct avec la cle du fichier .env (diagnostic 401)."""
    if not ROUTING_AVAILABLE:
        return {"ok": False, "error": "routing modules unavailable"}
    return test_groq_connection()


def _get_lan_ip() -> str | None:
    try:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


@app.get("/health")
def health():
    """Health check"""
    lan = _get_lan_ip()
    out: dict = {
        "status": "OK",
        "timestamp": datetime.now().isoformat(),
        "cors": "allow_origins=* (LAN OK)",
    }
    if lan:
        out["lan_url"] = f"http://{lan}:{API_PORT}/"
    return out


@app.get("/status")
def system_status():
    """Tableau de bord : services Jarvis."""
    stt = {}
    try:
        from stt import stt_health_info

        stt = stt_health_info()
    except Exception as e:
        stt = {"ok": False, "error": str(e)}

    web = {
        "enabled": WEB_SEARCH_ENABLED and WEB_SEARCH_AVAILABLE,
        "auto": WEB_SEARCH_AUTO,
        "cache_ttl_sec": WEB_CACHE_TTL_SEC,
    }
    if WEB_SEARCH_AVAILABLE:
        try:
            _, err = search_web("test", max_results=1, timeout_sec=6.0)
            web["ok"] = err is None
            web["error"] = err
        except Exception as e:
            web["ok"] = False
            web["error"] = str(e)

    ollama_ok = False
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        ollama_ok = r.status_code == 200
    except Exception:
        pass

    reminders_pending = 0
    try:
        reminders_pending = len(memory.get_reminders("default"))
    except Exception:
        pass

    return {
        "timestamp": datetime.now().isoformat(),
        "api": {"ok": True, "port": API_PORT, "lan": _get_lan_ip()},
        "ollama": {"ok": ollama_ok, "host": OLLAMA_HOST, "model": MODEL},
        "stt": stt,
        "web": web,
        "web_cache_ttl_sec": WEB_CACHE_TTL_SEC,
        "tidal": {"enabled": TIDAL_ENABLED},
        "tts": {"enabled": TTS_ENABLED, "engine": TTS_ENGINE},
        "reminders": {
            "enabled": REMINDERS_ENABLED,
            "pending": reminders_pending,
        },
        "cloud": cloud_status() if ROUTING_AVAILABLE else {"enabled": False},
        "local_commands": {"requires_tidal_keyword": LOCAL_COMMAND_REQUIRES_TIDAL},
    }


_STATUS_HTML = os.path.join(_BASE_DIR, "status.html")


@app.get("/status/ui")
def status_ui():
    if os.path.isfile(_STATUS_HTML):
        return FileResponse(_STATUS_HTML, media_type="text/html; charset=utf-8")
    return JSONResponse(status_code=404, content={"error": "status.html manquant"})


# ========================================
# Endpoint principal : Commande
# ========================================

@app.get("/command")
def command(
    request: Request,
    text: str,
    user_id: str = "default",
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    num_ctx: Optional[int] = None,
    speak: bool = True,
    web: Optional[bool] = None,
    cloud: Optional[bool] = None,
    brief: bool = False,
):
    """
    Endpoint principal pour envoyer une commande/question.
    Utilise automatiquement la mÃ©moire pour le contexte.
    """

    # Validation
    if not text or len(text.strip()) == 0:
        return JSONResponse(
            status_code=400,
            content={"error": "âŒ Le texte ne peut pas Ãªtre vide"}
        )

    print(f"\nCOMMANDE : {text}")

    response, use_model, predict, ctx, web_meta = _run_assistant(
        text, user_id, model, max_tokens, num_ctx, web=web, force_cloud=cloud,
        brief=brief,
    )

    payload = {
        "input": text,
        "output": response,
        "user_id": user_id,
        "model": use_model,
        "route": web_meta.get("route"),
        "provider": web_meta.get("provider"),
        "max_tokens": predict,
        "num_ctx": ctx,
        "timestamp": datetime.now().isoformat(),
        **web_meta,
    }
    tts_cap = BRIEF_TTS_MAX_CHARS if web_meta.get("brief") else None
    _attach_audio_sync(request, payload, response, speak, tts_max_chars=tts_cap)
    return payload


# ========================================
# Endpoint POST : Chat
# ========================================

@app.post("/chat")
def chat(
    request: Request,
    message: str,
    user_id: str = "default",
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    num_ctx: Optional[int] = None,
    speak: bool = True,
    fast: bool = False,
    web: Optional[bool] = None,
    cloud: Optional[bool] = None,
    brief: bool = False,
):
    """
    Endpoint POST pour les conversations.
    Alternative Ã  /command (GET).
    """

    # Validation
    if not message or len(message.strip()) == 0:
        return JSONResponse(
            status_code=400,
            content={"error": "âŒ Le message ne peut pas Ãªtre vide"}
        )

    print(f"\nMESSAGE : {message}")

    try:
        response, use_model, predict, ctx, web_meta = _run_assistant(
            message,
            user_id,
            model,
            max_tokens,
            num_ctx,
            fast_mode=fast,
            web=web,
            force_cloud=cloud,
            brief=brief,
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "error": str(exc),
                "response": f"Erreur serveur : {exc}",
                "message": message,
            },
        )

    payload = {
        "message": message,
        "response": response,
        "user_id": user_id,
        "model": use_model,
        "route": web_meta.get("route"),
        "provider": web_meta.get("provider"),
        "complexity_score": web_meta.get("complexity_score"),
        "max_tokens": predict,
        "num_ctx": ctx,
        "fast": fast,
        **web_meta,
    }
    if speak:
        tts_cap = BRIEF_TTS_MAX_CHARS if web_meta.get("brief") else None
        _attach_audio_async(request, payload, response, speak, tts_max_chars=tts_cap)
    return payload


def _persist_stream_turn(message: str, final: str, user_id: str) -> None:
    try:
        from memory_summary import summarize_transcript

        memory.try_extract_fact(message, user_id)
        memory.add_conversation(
            user_msg=message,
            jarvis_msg=final,
            user_id=user_id,
            summarize_fn=summarize_transcript,
        )
    except Exception as exc:
        print(f"[Stream] memoire : {exc}")


async def _stream_chat_persist_and_tts(
    inner: AsyncIterator[str],
    *,
    request: Request,
    user_id: str,
    message: str,
    speak: bool,
    tts_cap: Optional[int],
    web_meta: dict,
) -> AsyncIterator[str]:
    """Enregistre la reponse finale + lance TTS async ; enrichit l'evenement done."""
    import json as _json

    full = ""
    skip_persist = bool(web_meta.get("memory_recall"))
    try:
        async for line in inner:
            chunk = line if isinstance(line, str) else ""
            stripped = chunk.strip()
            persist_final = ""
            if stripped.startswith("data:"):
                raw = stripped[5:].strip()
                try:
                    ev = _json.loads(raw)
                    tok = ev.get("token")
                    if tok:
                        full += tok
                    rep = ev.get("replace")
                    if rep is not None:
                        full = rep
                    if ev.get("done"):
                        final = (ev.get("response") or full or "").strip()
                        persist_final = final
                        ev["response"] = final
                        for key in (
                            "route",
                            "provider",
                            "complexity_score",
                            "web_used",
                            "web_sources",
                            "memory_recall",
                        ):
                            if key in web_meta:
                                ev[key] = web_meta[key]
                        if speak and final:
                            audio_extra: dict = {}
                            _attach_audio_async(
                                request,
                                audio_extra,
                                final,
                                True,
                                tts_max_chars=tts_cap,
                            )
                            ev.update(audio_extra)
                        chunk = f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
                except _json.JSONDecodeError:
                    pass
            yield chunk
            if persist_final and not skip_persist:
                threading.Thread(
                    target=_persist_stream_turn,
                    args=(message, persist_final, user_id),
                    daemon=True,
                ).start()
    except Exception as exc:
        print(f"[Stream] Erreur wrapper : {exc}")
        err = f"Erreur stream : {exc}"
        yield f'data: {_json.dumps({"replace": err, "done": True, "error": True}, ensure_ascii=False)}\n\n'


@app.post("/chat/stream")
async def chat_stream(
    request: Request,
    message: str,
    user_id: str = "default",
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    num_ctx: Optional[int] = None,
    speak: bool = True,
    fast: bool = False,
    web: Optional[bool] = None,
    cloud: Optional[bool] = None,
    brief: bool = False,
):
    """
    SSE : tokens Ollama + early-abort -> remplacement cloud si refus detecte.
    Events : {"token": "..."} | {"replace": "..."} | {"done": true, "provider": "..."}
    """
    if not message or not message.strip():
        return JSONResponse(status_code=400, content={"error": "Message vide"})

    use_brief = brief or BRIEF_RESPONSES_DEFAULT or fast
    tts_cap = BRIEF_TTS_MAX_CHARS if use_brief else None
    web_meta: dict = {"web_used": False, "brief": use_brief}
    _fact_msg = (message or "").strip()
    if _fact_msg and (
        not fast
        or len(_fact_msg) > 20
        or re.search(r"\bretiens\b|\bsouviens\b|\bmémoire\b", _fact_msg, re.I)
    ):
        memory.try_extract_fact(message, user_id)

    try:
        from memory_recall import is_memory_recall_request, reply_from_stored_facts

        if is_memory_recall_request(message):
            mem_reply = reply_from_stored_facts(
                memory.get_facts_for_prompt(user_id, limit=12)
            )
            if mem_reply is not None:
                import json as _json

                web_meta["memory_recall"] = True
                web_meta["route"] = "memory_facts"
                web_meta["provider"] = "memory"
                print("[Route] memory_recall stream (faits SQLite)")

                async def _mem_stream():
                    yield f'data: {_json.dumps({"replace": mem_reply, "provider": "memory"}, ensure_ascii=False)}\n\n'
                    yield f'data: {_json.dumps({"done": True, "provider": "memory", "response": mem_reply}, ensure_ascii=False)}\n\n'

                return StreamingResponse(
                    _stream_chat_persist_and_tts(
                        _mem_stream(),
                        request=request,
                        user_id=user_id,
                        message=message,
                        speak=speak,
                        tts_cap=tts_cap,
                        web_meta=web_meta,
                    ),
                    media_type="text/event-stream",
                )
    except ImportError:
        pass

    predict = _clamp_int(max_tokens, OLLAMA_NUM_PREDICT, 32, 8192)
    ctx = _clamp_int(num_ctx, OLLAMA_NUM_CTX, 512, 131072)
    use_web = _should_use_web(message, web)
    skip_fts = ROUTING_AVAILABLE and is_simple_chat(message)
    web_context = ""
    fts_hits: list = []
    fts_ms = 0.0
    fts_ctx_str = ""
    slim_web = not (
        ROUTING_AVAILABLE and cloud_available() and cloud_quota_ok()
    )
    do_fts = FTS_PREFETCH_ENABLED and not skip_fts
    if PRE_LLM_PARALLEL and (use_web or do_fts):
        from perf_prellm import gather_pre_llm

        bundle = gather_pre_llm(
            message,
            user_id,
            fast_mode=False,
            use_web=use_web,
            skip_fts=skip_fts,
            fetch_web_fn=_fetch_web_context,
            web_slim=slim_web,
        )
        web_context = bundle.web_context
        web_meta["web_used"] = bool(bundle.web_sources)
        web_meta["web_sources"] = bundle.web_sources
        web_meta["web_error"] = bundle.web_error
        fts_hits, fts_ms, fts_ctx_str = (
            bundle.fts_hits,
            bundle.fts_ms,
            bundle.fts_ctx_str,
        )
    else:
        if use_web:
            web_context, sources, web_err = _fetch_web_context(
                message, slim=slim_web
            )
            web_meta["web_used"] = bool(sources)
            web_meta["web_sources"] = sources
            web_meta["web_error"] = web_err
        if do_fts:
            try:
                from fts_prefetch import format_fts_context, prefetch_micro_context

                fts_hits, fts_ms = prefetch_micro_context(message, user_id)
                fts_ctx_str = format_fts_context(fts_hits)
            except ImportError:
                pass

    web_used = bool(web_meta.get("web_used"))

    chat_route: Optional[Route] = None
    chat_analysis: Optional[RouterAnalysis] = None
    score = 0
    if ROUTING_AVAILABLE:
        chat_analysis = analyze_query(
            message,
            web_used=web_used,
            fts_hints=fts_hits,
            fts_elapsed_ms=fts_ms,
        )
        chat_route, score, chat_analysis = decide_route(
            message,
            web_used=web_used,
            cloud_enabled=cloud_available(),
            cloud_quota_ok=cloud_quota_ok(),
            force_cloud=cloud,
            explicit_local=_is_explicit_local_model(model),
            analysis=chat_analysis,
        )
        chat_route = upgrade_route_for_vram(
            chat_route,
            score,
            cloud_enabled=cloud_available(),
            cloud_quota_ok=cloud_quota_ok(),
            is_heavy_fn=is_heavy_task,
            text=message,
            analysis=chat_analysis,
        )

    simple_stream = (
        ROUTING_AVAILABLE
        and chat_analysis is not None
        and is_simple_chat(message, chat_analysis)
        and chat_route not in (Route.CLOUD, Route.CLOUD_HEAVY)
    )
    if simple_stream:
        predict = min(predict, WAKE_MAX_TOKENS, BRIEF_MAX_TOKENS)
        ctx = min(ctx, WAKE_NUM_CTX)
        web_meta["simple_chat"] = True
        web_meta["route"] = chat_route.value if chat_route else "local_fast"
        web_meta["complexity_score"] = score
        use_model = (
            local_ollama_model()
            if is_single_local_mode()
            else _resolve_chat_model(message, False, model)
        )
        messages = _build_chat_messages(
            user_id,
            message,
            fast_mode=fast,
            web_context=web_context,
            route=chat_route,
            analysis=chat_analysis,
            fts_context=fts_ctx_str,
            brief=True,
        )
        text = ask_ollama_chat(
            messages, model=use_model, max_tokens=predict, num_ctx=ctx
        )
        import json as _json

        async def _simple_once():
            yield f'data: {_json.dumps({"replace": text, "provider": "ollama"}, ensure_ascii=False)}\n\n'
            yield f'data: {_json.dumps({"done": True, "provider": "ollama", "model": use_model, "simple_chat": True}, ensure_ascii=False)}\n\n'

        print(f"[Route] simple_chat score={score} -> {use_model}")
        return StreamingResponse(
            _stream_chat_persist_and_tts(
                _simple_once(),
                request=request,
                user_id=user_id,
                message=message,
                speak=speak,
                tts_cap=tts_cap or BRIEF_TTS_MAX_CHARS,
                web_meta=web_meta,
            ),
            media_type="text/event-stream",
        )

    if ROUTING_AVAILABLE and chat_route in (Route.CLOUD, Route.CLOUD_HEAVY):
        heavy = chat_route == Route.CLOUD_HEAVY
        web_meta["route"] = chat_route.value if chat_route else "cloud"
        web_meta["provider"] = "groq"
        web_meta["complexity_score"] = score
        messages = _build_chat_messages(
            user_id,
            message,
            fast_mode=fast,
            web_context=web_context,
            route=chat_route,
            analysis=chat_analysis,
            fts_context=fts_ctx_str,
            brief=use_brief,
        )
        text, cloud_model = ask_cloud(
            messages,
            heavy=heavy,
            max_tokens=min(predict, CLOUD_MAX_TOKENS),
            route_label="stream_cloud_direct",
        )
        import json as _json

        async def _cloud_once():
            yield f'data: {_json.dumps({"replace": text, "provider": "groq"}, ensure_ascii=False)}\n\n'
            yield f'data: {_json.dumps({"done": True, "provider": "groq", "model": cloud_model}, ensure_ascii=False)}\n\n'

        return StreamingResponse(
            _stream_chat_persist_and_tts(
                _cloud_once(),
                request=request,
                user_id=user_id,
                message=message,
                speak=speak,
                tts_cap=tts_cap,
                web_meta=web_meta,
            ),
            media_type="text/event-stream",
        )

    if is_single_local_mode() and (
        not ROUTING_AVAILABLE
        or chat_route not in (Route.CLOUD, Route.CLOUD_HEAVY)
    ):
        use_model = local_ollama_model()
    elif ROUTING_AVAILABLE and chat_route == Route.LOCAL_QUALITY:
        use_model = (
            local_ollama_model()
            if is_single_local_mode()
            else QUALITY_MODEL
        )
    else:
        use_model = _resolve_chat_model(message, False, model)
    if chat_route is not None:
        web_meta["route"] = chat_route.value
    web_meta["complexity_score"] = score
    messages = _build_chat_messages(
        user_id,
        message,
        fast_mode=fast,
        web_context=web_context,
        route=chat_route,
        analysis=chat_analysis,
        fts_context=fts_ctx_str,
        brief=use_brief,
    )
    req_dev = chat_analysis.requires_development if chat_analysis else False
    stream_kwargs = dict(
        host=OLLAMA_HOST,
        model=use_model,
        messages=messages,
        options=_ollama_options(predict, ctx, model=use_model),
        keep_alive=ollama_keep_alive(),
        timeout=OLLAMA_STREAM_TIMEOUT,
        user_text=message,
        requires_development=req_dev,
        complexity_score=score,
        cloud_available_fn=cloud_available,
        cloud_quota_ok_fn=cloud_quota_ok,
        ask_cloud_fn=ask_cloud,
        heavy=score >= CLOUD_HEAVY_THRESHOLD,
        max_tokens=min(predict, CLOUD_MAX_TOKENS),
    )

    if ROUTE_RACE_ENABLED and chat_route is not None:
        from route_race import stream_sse_with_route_race

        gen = stream_sse_with_route_race(
            route=chat_route,
            score=score,
            on_early_abort_stream=stream_sse_with_early_abort,
            **stream_kwargs,
        )
    else:
        gen = stream_sse_with_early_abort(**stream_kwargs)
    return StreamingResponse(
        _stream_chat_persist_and_tts(
            gen,
            request=request,
            user_id=user_id,
            message=message,
            speak=speak,
            tts_cap=tts_cap,
            web_meta=web_meta,
        ),
        media_type="text/event-stream",
    )


# ========================================
# Endpoints MÃ©moire : Historique
# ========================================

@app.get("/memory/history")
def get_history(
    user_id: str = "default",
    limit: int = 10
):
    """RÃ©cupÃ¨re l'historique de conversation"""

    history = memory.get_conversation_history(user_id, limit)

    return {
        "user_id": user_id,
        "count": len(history),
        "history": history
    }


# ========================================
# Endpoints MÃ©moire : Faits
# ========================================

@app.get("/memory/facts")
def get_facts(user_id: str = "default"):
    """RÃ©cupÃ¨re les faits mÃ©morisÃ©s"""

    facts = memory.get_facts(user_id)

    return {
        "user_id": user_id,
        "count": len(facts),
        "facts": facts
    }


@app.post("/memory/add-fact")
def add_fact(
    fact: str,
    user_id: str = "default"
):
    """Ajoute un fait Ã  mÃ©moriser"""

    if not fact:
        return JSONResponse(
            status_code=400,
            content={"error": "âŒ Fait vide"}
        )

    memory.add_fact(fact, user_id)

    return {
        "status": "âœ… Fait ajoutÃ©",
        "fact": fact,
        "user_id": user_id
    }


# ========================================
# Endpoints MÃ©moire : Rappels
# ========================================

@app.get("/memory/reminders")
def get_reminders(user_id: str = "default"):
    """RÃ©cupÃ¨re les rappels en attente"""

    reminders = memory.get_reminders(user_id)

    return {
        "user_id": user_id,
        "count": len(reminders),
        "reminders": reminders
    }


@app.post("/memory/add-reminder")
def add_reminder(
    reminder: str,
    user_id: str = "default",
    due_date: Optional[str] = None
):
    """Ajoute un rappel"""

    if not reminder:
        return JSONResponse(
            status_code=400,
            content={"error": "âŒ Rappel vide"}
        )

    memory.add_reminder(
        reminder=reminder,
        user_id=user_id,
        due_date=due_date
    )

    return {
        "status": "âœ… Rappel ajoutÃ©",
        "reminder": reminder,
        "due_date": due_date,
        "user_id": user_id
    }


# ========================================
# Endpoints MÃ©moire : Statistiques
# ========================================

@app.get("/memory/stats")
def get_stats(user_id: str = "default"):
    """Obtient les statistiques mÃ©moire"""

    stats = memory.get_stats(user_id)

    return {
        "user_id": user_id,
        **stats
    }


@app.delete("/memory/clear")
def clear_memory(
    user_id: str = "default",
    confirm: bool = False
):
    """âš ï¸ Efface TOUTE la mÃ©moire d'un utilisateur"""

    if not confirm:
        return {
            "warning": "âš ï¸ DANGER - Action irrÃ©versible",
            "message": "Ajoute ?confirm=true pour confirmer l'effacement"
        }

    memory.clear_all(user_id)

    return {
        "status": "ðŸ§¹ MÃ©moire effacÃ©e",
        "user_id": user_id
    }


# ========================================
# Endpoints ModÃ¨le
# ========================================

@app.post("/switch-model")
def switch_model(model: str):
    """Change le modÃ¨le IA utilisÃ©"""

    global MODEL
    
    old_model = MODEL
    MODEL = model

    return {
        "status": "âœ… ModÃ¨le changÃ©",
        "old_model": old_model,
        "new_model": MODEL
    }


# ========================================
# Lancement du serveur
# ========================================

if __name__ == "__main__":

    import uvicorn

    print("\n" + "="*60)
    print("JARVIS API - WINDOWS ULTRA (v3.0)")
    print("="*60)
    print(f"Modele IA        : {MODEL}")
    if ROUTING_AVAILABLE:
        cs = cloud_status()
        print(
            f"Cloud Groq       : {'actif' if cs.get('available') else 'off'} "
            f"({cs.get('used_today', 0)}/{cs.get('daily_limit', 0)} aujourd'hui)"
        )
    if is_single_local_mode():
        print(
            f"VRAM (1 modele)  : {local_ollama_model()} local | "
            f"reste -> cloud | keep_alive={ollama_keep_alive()}"
        )
    print(f"Serveur          : http://127.0.0.1:{API_PORT}")
    print(f"Chat web         : http://127.0.0.1:{API_PORT}/")
    print(f"Documentation    : http://127.0.0.1:{API_PORT}/docs")
    print(f"Memoire          : ACTIVEE")
    try:
        from jarvis_bridge import edge_available, edge_error

        if edge_available():
            print("Edge app/       : ACTIVE (prompts RAM + anti-refus)")
        else:
            print(f"Edge app/       : legacy seul ({edge_error()})")
    except ImportError:
        print("Edge app/       : non branche")
    try:
        import socket

        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.connect(("8.8.8.8", 80))
        _lan_ip = _s.getsockname()[0]
        _s.close()
        print(f"Redmi / LAN      : http://{_lan_ip}:{API_PORT}/")
        print(f"  (dans le chat : API = http://{_lan_ip}:{API_PORT})")
    except Exception:
        print("Redmi / LAN      : utilise ipconfig pour l'IP Wi-Fi du PC")
    print("="*60 + "\n")

    # Objet app direct : evite un second import (double "Initialisation memoire")
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        reload=UVICORN_RELOAD,
        log_level="info" if DEBUG else "warning",
    )