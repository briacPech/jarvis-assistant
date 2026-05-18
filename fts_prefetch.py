# fts_prefetch.py — SQLite FTS5 prefetch (<2 ms) avant ChromaDB

from __future__ import annotations

import re
import sqlite3
import time
from typing import Any

try:
    from config import DB_PATH, FTS_PREFETCH_ENABLED, FTS_PREFETCH_LIMIT
except ImportError:
    DB_PATH = "jarvis_memory.db"
    FTS_PREFETCH_ENABLED = True
    FTS_PREFETCH_LIMIT = 3

_WORD_RX = re.compile(r"[\w\u00c0-\u024f]{3,}", re.UNICODE)
_fts_ready: dict[str, bool] = {}


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_fts_schema(db_path: str = DB_PATH) -> None:
    """Crée la table FTS5 et indexe l'historique existant."""
    if db_path in _fts_ready:
        return
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
            user_message,
            jarvis_response,
            user_id UNINDEXED,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    cur.execute("SELECT COUNT(*) FROM conversations_fts")
    if cur.fetchone()[0] == 0:
        cur.execute(
            """
            INSERT INTO conversations_fts(rowid, user_message, jarvis_response, user_id)
            SELECT id, user_message, jarvis_response, user_id FROM conversations
            """
        )
    conn.commit()
    conn.close()
    _fts_ready[db_path] = True


def index_conversation(
    conv_id: int,
    user_msg: str,
    jarvis_msg: str,
    user_id: str = "default",
    *,
    db_path: str = DB_PATH,
) -> None:
    if not FTS_PREFETCH_ENABLED:
        return
    ensure_fts_schema(db_path)
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO conversations_fts(
            rowid, user_message, jarvis_response, user_id
        )
        VALUES (?, ?, ?, ?)
        """,
        (conv_id, user_msg or "", jarvis_msg or "", user_id),
    )
    conn.commit()
    conn.close()


def _build_match_query(text: str) -> str | None:
    words = _WORD_RX.findall((text or "").lower())
    if not words:
        return None
    seen: set[str] = set()
    terms: list[str] = []
    for w in words[:8]:
        if w in seen:
            continue
        seen.add(w)
        terms.append(f'"{w}"' if len(w) < 4 else w)
    if not terms:
        return None
    return " OR ".join(terms)


def _snippet(text: str, max_words: int = 40) -> str:
    words = (text or "").split()
    if len(words) <= max_words:
        return (text or "").strip()
    return " ".join(words[:max_words]).strip() + "…"


def prefetch_micro_context(
    query: str,
    user_id: str = "default",
    *,
    limit: int | None = None,
    db_path: str = DB_PATH,
) -> tuple[list[dict[str, Any]], float]:
    """
    Recherche FTS5 ultra-rapide dans l'historique.
    Retourne (hits, elapsed_ms).
    """
    if not FTS_PREFETCH_ENABLED:
        return [], 0.0
    match = _build_match_query(query)
    if not match:
        return [], 0.0

    t0 = time.perf_counter()
    try:
        ensure_fts_schema(db_path)
        cap = limit if limit is not None else FTS_PREFETCH_LIMIT
        conn = _connect(db_path)
        rows = conn.execute(
            """
            SELECT
                user_message,
                jarvis_response,
                bm25(conversations_fts) AS rank
            FROM conversations_fts
            WHERE conversations_fts MATCH ?
              AND user_id = ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, user_id, cap),
        ).fetchall()
        conn.close()
    except sqlite3.OperationalError:
        return [], (time.perf_counter() - t0) * 1000.0

    hits: list[dict[str, Any]] = []
    for row in rows:
        u = _snippet(row["user_message"] or "")
        j = _snippet(row["jarvis_response"] or "")
        if u or j:
            hits.append({"user": u, "jarvis": j})
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return hits, elapsed_ms


def format_fts_context(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return ""
    lines = ["Extraits locaux (FTS5, historique) :"]
    for i, h in enumerate(hits, 1):
        if h.get("user"):
            lines.append(f"{i}. Q: {h['user']}")
        if h.get("jarvis"):
            lines.append(f"   R: {h['jarvis']}")
    return "\n".join(lines)
