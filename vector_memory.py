# vector_memory.py — souvenirs semantiques (Chroma, optionnel)

from __future__ import annotations

import hashlib
import os
from typing import Any

try:
    from config import RAG_MICRO_CHUNK_WORDS
except ImportError:
    RAG_MICRO_CHUNK_WORDS = 150

_client = None
_collection = None
_enabled: bool | None = None


def _init():
    global _client, _collection, _enabled
    if _enabled is not None:
        return
    try:
        import chromadb
        from chromadb.config import Settings

        from config import CHROMA_PATH

        os.makedirs(CHROMA_PATH, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name="memories",
            metadata={"hnsw:space": "cosine"},
        )
        _enabled = True
    except Exception as e:
        print(f"[Chroma] Desactive : {e}")
        _enabled = False


def is_enabled() -> bool:
    _init()
    return bool(_enabled)


def _word_count(text: str) -> int:
    return len((text or "").split())


def limit_words(text: str, max_words: int | None = None) -> str:
    """Tronque à max_words (défaut RAG_MICRO_CHUNK_WORDS)."""
    cap = max_words if max_words is not None else RAG_MICRO_CHUNK_WORDS
    words = (text or "").split()
    if len(words) <= cap:
        return (text or "").strip()
    return " ".join(words[:cap]).strip() + "…"


def micro_chunk_text(text: str, max_words: int | None = None) -> list[str]:
    """Découpe un texte long en segments ≤ max_words (micro-chunks RAG)."""
    cap = max_words if max_words is not None else RAG_MICRO_CHUNK_WORDS
    words = (text or "").split()
    if not words:
        return []
    if len(words) <= cap:
        return [(text or "").strip()]
    chunks: list[str] = []
    for i in range(0, len(words), cap):
        part = " ".join(words[i : i + cap]).strip()
        if part:
            chunks.append(part)
    return chunks


def remember(
    text: str,
    embedding: list[float],
    *,
    user_id: str = "default",
    kind: str = "summary",
    meta: dict[str, Any] | None = None,
) -> bool:
    _init()
    if not _enabled or not _collection or not text.strip():
        return False
    m = meta or {}
    metadatas = {"user_id": user_id, "kind": kind, **m}
    doc = limit_words(text.strip())
    if not doc:
        return False
    raw_id = f"{user_id}:{kind}:{doc[:80]}:{m.get('ts', '')}"
    doc_id = hashlib.sha256(raw_id.encode()).hexdigest()[:24]
    try:
        _collection.upsert(
            ids=[doc_id],
            documents=[doc],
            embeddings=[embedding],
            metadatas=[metadatas],
        )
        return True
    except Exception as e:
        print(f"[Chroma] upsert : {e}")
        return False


def recall(
    query_embedding: list[float],
    *,
    user_id: str = "default",
    k: int = 3,
) -> list[str]:
    _init()
    if not _enabled or not _collection:
        return []
    try:
        res = _collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where={"user_id": user_id},
        )
        docs = res.get("documents") or [[]]
        seen: set[str] = set()
        out: list[str] = []
        for d in docs[0]:
            if not d:
                continue
            micro = limit_words(d)
            if micro and micro not in seen:
                seen.add(micro)
                out.append(micro)
        return out
    except Exception as e:
        print(f"[Chroma] recall : {e}")
        return []
