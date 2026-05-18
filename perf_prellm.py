# perf_prellm.py — web + FTS en parallèle avant le LLM

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from router import RouterAnalysis


@dataclass
class PreLlmBundle:
    web_context: str = ""
    web_sources: list[dict] = field(default_factory=list)
    web_error: Optional[str] = None
    fts_hits: list[Any] = field(default_factory=list)
    fts_ms: float = 0.0
    fts_ctx_str: str = ""


def needs_semantic_recall(
    user_text: str, analysis: "RouterAnalysis | None" = None
) -> bool:
    try:
        from memory_recall import is_memory_recall_request

        if is_memory_recall_request(user_text):
            return False
    except ImportError:
        pass
    t = (user_text or "").strip()
    if not t:
        return False
    if re.search(
        r"\b(retiens|souviens|rappelle|mémoire|memoire|prefere|préfère|"
        r"la derniere fois|la dernière fois|tu te souviens)\b",
        t,
        re.I,
    ):
        return True
    if analysis is not None and analysis.complexity_score >= 3:
        return True
    return len(t) > 80


def gather_pre_llm(
    user_text: str,
    user_id: str,
    *,
    fast_mode: bool,
    use_web: bool,
    skip_fts: bool,
    fetch_web_fn: Callable[..., tuple[str, list, Optional[str]]],
    web_slim: bool,
) -> PreLlmBundle:
    """Lance web et FTS en parallèle (max 2 workers)."""
    out = PreLlmBundle()
    do_web = use_web
    do_fts = not fast_mode and not skip_fts

    if not do_web and not do_fts:
        return out

    def _web() -> tuple[str, list, Optional[str]]:
        return fetch_web_fn(user_text, slim=web_slim)

    def _fts() -> tuple[list, float, str]:
        try:
            from fts_prefetch import format_fts_context, prefetch_micro_context

            hits, ms = prefetch_micro_context(user_text, user_id)
            return hits, ms, format_fts_context(hits)
        except ImportError:
            return [], 0.0, ""

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_web = pool.submit(_web) if do_web else None
        f_fts = pool.submit(_fts) if do_fts else None
        if f_web is not None:
            out.web_context, out.web_sources, out.web_error = f_web.result()
        if f_fts is not None:
            out.fts_hits, out.fts_ms, out.fts_ctx_str = f_fts.result()
    return out
