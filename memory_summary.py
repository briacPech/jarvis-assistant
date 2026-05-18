# memory_summary.py — resume periodique des conversations (Ollama + Chroma)

from __future__ import annotations

import requests

from config import (
    EMBED_MODEL,
    FAST_MODEL,
    OLLAMA_HOST,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_GPU,
    OLLAMA_NUM_THREAD,
)
from local_model_policy import local_ollama_model, ollama_keep_alive


def _ollama_options(predict: int, ctx: int, model: str | None = None) -> dict:
    opts: dict = {"num_predict": predict, "num_ctx": ctx}
    if OLLAMA_NUM_GPU is not None:
        opts["num_gpu"] = OLLAMA_NUM_GPU
    if OLLAMA_NUM_THREAD > 0:
        opts["num_thread"] = OLLAMA_NUM_THREAD
    try:
        from ollama_refusal_opts import merge_anti_refusal_options

        use_model = (model or local_ollama_model()).strip()
        return merge_anti_refusal_options(opts, model=use_model or None)
    except ImportError:
        return opts


def embed_text(text: str) -> list[float] | None:
    prompt = (text or "").strip()[:2000]
    if not prompt:
        return None
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": prompt},
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[Embed] HTTP {r.status_code} : {r.text[:120]}")
            return None
        return r.json().get("embedding")
    except Exception as e:
        print(f"[Embed] {e}")
        return None


def summarize_transcript(transcript: str, model: str | None = None) -> str:
    """Resume un bloc de dialogue en faits durables (francais, concis)."""
    use_model = (model or local_ollama_model()).strip()
    system = (
        "Tu resumes une conversation utilisateur / assistant. "
        "Extrais uniquement : preferences, projets, decisions, infos personnelles utiles. "
        "Format : 5 a 8 puces courtes en francais. Pas de salutations. "
        "Ignore le bavardage sans valeur."
    )
    user = f"Conversation a resumer :\n\n{transcript[:12000]}"
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": use_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "keep_alive": ollama_keep_alive(),
                "options": _ollama_options(
                    384, min(OLLAMA_NUM_CTX, 4096), model=use_model
                ),
            },
            timeout=120,
        )
        if r.status_code != 200:
            print(f"[Resume] Ollama HTTP {r.status_code}")
            return ""
        content = (r.json().get("message") or {}).get("content", "")
        return (content or "").strip()
    except Exception as e:
        print(f"[Resume] {e}")
        return ""


def store_summary_vector(summary: str, user_id: str, summary_id: int) -> None:
    try:
        from vector_memory import is_enabled, remember

        if not is_enabled():
            return
        emb = embed_text(summary)
        if emb:
            remember(
                summary,
                emb,
                user_id=user_id,
                kind="summary",
                meta={"summary_id": summary_id},
            )
    except ImportError:
        pass
