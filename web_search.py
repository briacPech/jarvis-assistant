# web_search.py — recherche web pour enrichir les reponses Jarvis

import hashlib
import re
import time
from datetime import datetime
from typing import Optional

try:
    from config import WEB_CACHE_TTL_SEC
except ImportError:
    WEB_CACHE_TTL_SEC = int(__import__("os").getenv("JARVIS_WEB_CACHE_TTL", "3600"))

_cache: dict[str, tuple[float, list[dict], Optional[str]]] = {}

_WEB_HINTS = re.compile(
    r"\b("
    r"météo|meteo|actualité|actualite|actu|aujourd'hui|aujourdhui|maintenant|"
    r"en ce moment|dernière|derniere|dernier|news|prix|cotation|bourse|"
    r"qui a gagné|qui a gagne|score|match|résultat|resultat|"
    r"recherche sur|cherche sur|sur internet|sur le web|sur le net|"
    r"va sur le web|surfe|surf|navigue|google|duckduckgo|wikipédia|wikipedia|"
    r"quelle heure|fuseau|événement|evenement|festival|concert|programmation|"
    r"sortie de|mise à jour|mise a jour|update|"
    r"taux de change|euro|dollar|bitcoin|crypto|"
    r"infos sur|information sur|renseigne[- ]moi|dis[- ]moi ce qu|"
    r"parle[- ]moi de|qu'est[- ]ce que|c'est quoi|qui est|qui sont|"
    r"où se trouve|ou se trouve|combien coûte|combien coute|"
    r"billetterie|horaires|programme|line[- ]?up"
    r")\b",
    re.IGNORECASE,
)

_RECENT_YEAR = re.compile(r"\b(202[4-9]|2030)\b")

_FACTUAL = re.compile(
    r"\b(c'est quoi|qui est|qui sont|où est|ou est|ou se trouve|combien coûte|combien coute)\b",
    re.IGNORECASE,
)

_EXPLICIT_WEB = re.compile(
    r"(?:^|\b)("
    r"web\s*:|cherche\s+(?:sur\s+)?(?:le\s+)?(?:web|internet|google)|"
    r"(?:va|surfe|navigue)\s+(?:sur\s+)?(?:le\s+)?(?:web|internet)|"
    r"recherche\s+(?:web|internet)|infos?\s+sur\s+le\s+web"
    r")",
    re.IGNORECASE,
)

def wants_forced_web(text: str) -> bool:
    """Préfixe web: ou ordre explicite de chercher sur Internet."""
    return bool(_EXPLICIT_WEB.search((text or "").strip()))


def needs_web_search(text: str) -> bool:
    """Heuristique : la question a-t-elle besoin d'infos recentes ou externes ?"""
    t = (text or "").strip()
    if not t:
        return False
    try:
        from router import is_simple_chat

        if is_simple_chat(t):
            return False
    except ImportError:
        pass
    if wants_forced_web(t):
        return True
    if len(t) < 8:
        return False
    if _WEB_HINTS.search(t):
        return True
    if _RECENT_YEAR.search(t) and re.search(
        r"\b(quand|date|sorti|élu|elu|élection|election|film|série|serie|concert)\b",
        t,
        re.IGNORECASE,
    ):
        return True
    if _FACTUAL.search(t) and len(t) > 24:
        return True
    return False


def prepare_search_query(text: str) -> str:
    """Nettoie la phrase utilisateur pour DuckDuckGo."""
    q = (text or "").strip()
    q = re.sub(r"^web\s*:\s*", "", q, flags=re.I).strip()
    q = re.sub(
        r"^(?:jarvis[, ]+)?(?:cherche|recherche|surfe|va)\s+(?:sur\s+)?(?:le\s+)?(?:web|internet|google)\s+",
        "",
        q,
        flags=re.I,
    ).strip()
    return q or (text or "").strip()


def _cache_key(query: str, max_results: int) -> str:
    raw = f"{prepare_search_query(query)}|{max_results}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def search_web(query: str, max_results: int = 5, timeout_sec: float = 12.0) -> tuple[list[dict], Optional[str]]:
    """
    Recherche DuckDuckGo. Retourne (liste de {title, snippet, url}, erreur).
    Cache memoire (TTL configurable, defaut 1 h).
    """
    q = prepare_search_query(query)
    if not q:
        return [], "requete vide"

    key = _cache_key(q, max_results)
    now = time.time()
    if key in _cache:
        ts, results, err = _cache[key]
        if now - ts < WEB_CACHE_TTL_SEC:
            return list(results), err

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS(timeout=timeout_sec) as ddgs:
            raw = list(ddgs.text(q, max_results=max_results, region="fr-fr"))
    except ImportError:
        return [], "module duckduckgo-search manquant (pip install duckduckgo-search)"
    except Exception as e:
        return [], str(e)

    out = []
    for hit in raw:
        title = (hit.get("title") or "").strip()
        snippet = (hit.get("body") or hit.get("snippet") or "").strip()
        url = (hit.get("href") or hit.get("link") or "").strip()
        if title or snippet:
            out.append({"title": title, "snippet": snippet, "url": url})
    _cache[key] = (now, out, None)
    if len(_cache) > 200:
        oldest = min(_cache.keys(), key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)
    return out, None


def format_web_context(results: list[dict], max_snippet: int = 500) -> str:
    if not results:
        return ""
    cap = max(80, int(max_snippet))
    lines = [
        f"Resultats web ({datetime.now().strftime('%Y-%m-%d %H:%M')}, sources externes) :",
        "Utilise uniquement ces extraits pour les faits recents. Cite la source (titre ou URL).",
        "Si les extraits ne suffisent pas, dis-le clairement.",
        "",
    ]
    for i, r in enumerate(results, 1):
        title = r.get("title") or "Sans titre"
        snippet = (r.get("snippet") or "")[:cap]
        url = r.get("url") or ""
        lines.append(f"[{i}] {title}")
        if snippet:
            lines.append(f"    {snippet}")
        if url:
            lines.append(f"    {url}")
        lines.append("")
    return "\n".join(lines).strip()
