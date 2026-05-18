# router.py — Fast Router (<10 ms, regex précompilées + sets, sans LLM)

from __future__ import annotations

import asyncio
import re
import time
from enum import Enum
from typing import Final

from pydantic import BaseModel, Field

try:
    from config import (
        CLOUD_COMPLEXITY_THRESHOLD,
        CLOUD_HEAVY_THRESHOLD,
        ROUTER_PEDAGOGICAL_CLOUD_SCORE,
    )
except ImportError:
    CLOUD_COMPLEXITY_THRESHOLD = 5
    CLOUD_HEAVY_THRESHOLD = 8
    ROUTER_PEDAGOGICAL_CLOUD_SCORE = 4


class Route(str, Enum):
    LOCAL_WAKE = "local_wake"
    LOCAL_FAST = "local_fast"
    LOCAL_QUALITY = "local_quality"
    CLOUD = "cloud"
    CLOUD_HEAVY = "cloud_heavy"


class Intent(str, Enum):
    GENERAL = "general"
    PEDAGOGICAL = "pedagogique"
    CULTURAL = "culturel"
    TECHNICAL = "technique"
    COMMAND = "commande"


class RouterAnalysis(BaseModel):
    raw_text: str = ""
    char_count: int = 0
    word_count: int = 0
    complexity_score: int = Field(ge=0)
    intent: Intent = Intent.GENERAL
    matched_signals: list[str] = Field(default_factory=list)
    requires_development: bool = False
    elapsed_ms: float = 0.0
    fts_hit_count: int = 0
    fts_elapsed_ms: float = 0.0


# --- Sets : lookup O(1) sur tokens (avant regex lourdes) ---

_COMMAND_WORDS: Final[frozenset[str]] = frozenset(
    {
        "heure",
        "date",
        "volume",
        "pause",
        "play",
        "stop",
        "musique",
        "météo",
        "meteo",
        "joue",
        "lance",
    }
)

_SIMPLE_GREETINGS: Final[frozenset[str]] = frozenset(
    {"salut", "bonjour", "merci", "ok", "oui", "non", "coucou", "hey", "hello"}
)

_PEDAGOGY_WORDS: Final[frozenset[str]] = frozenset(
    {
        "explique",
        "expliquer",
        "développe",
        "développer",
        "détaill",
        "présente",
        "présenter",
        "décris",
        "décrire",
        "pédagog",
        "enseign",
        "apprendre",
        "vulgaris",
        "leçon",
        "cours",
        "exposé",
        "expose",
        "dissertation",
        "fiche",
        "résumé",
        "resume",
        "synthèse",
        "synthese",
        "compare",
        "comparer",
        "chronologie",
    }
)

_CULTURE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "histoire",
        "historique",
        "antiquité",
        "antiquite",
        "révolution",
        "revolution",
        "guerre",
        "philosoph",
        "civilisation",
        "empire",
        "dynastie",
        "napoléon",
        "napoleon",
        "littérature",
        "litterature",
        "mythologie",
        "biographie",
        "napoléon",
        "louis",
        "rome",
        "grèce",
        "grece",
    }
)

_TECH_WORDS: Final[frozenset[str]] = frozenset(
    {
        "python",
        "typescript",
        "javascript",
        "sql",
        "debug",
        "refactor",
        "api",
        "algorithme",
        "compile",
        "exception",
    }
)

_HEAVY_WORDS: Final[frozenset[str]] = frozenset(
    {
        "rapport",
        "audit",
        "approfondie",
        "approfondi",
        "refactor",
        "thèse",
        "these",
        "dissertation",
    }
)


def _compile_many(
    specs: tuple[tuple[str, int, str], ...],
) -> tuple[tuple[re.Pattern[str], int, str], ...]:
    return tuple((re.compile(p, re.I), w, label) for p, w, label in specs)


_PEDAGOGICAL_RX: Final = _compile_many(
    (
        (r"\b(expos[ée]|dissertation|fiche|r[ée]sum[ée]|synth[èe]se|plan détaillé)\b", 4, "format_long"),
        (r"\b(explique|expliquer|développe|détaill|présente|décris|décrire)\b", 3, "verbe_explicatif"),
        (r"\b(pourquoi|comment|en quoi|à quoi sert|quelles? sont les causes)\b", 2, "question_analytique"),
        (r"\b(qui est|qu'est-ce que|définition de|biographie)\b", 2, "question_identitaire"),
        (r"\b(pédagog|enseign|apprendre|vulgaris|leçon|cours)\b", 3, "pedagogie"),
        (r"\b(compare|comparer|différence entre|similitudes)\b", 3, "comparaison"),
        (r"\b(chronologie|timeline|étape par étape|step by step)\b", 3, "structure_temps"),
    )
)

_CULTURAL_RX: Final = _compile_many(
    (
        (r"\b(histoire|historique|antiquité|moyen [âa]ge|r[ée]volution|guerre mondiale)\b", 3, "histoire"),
        (r"\b(philosoph|culture g[ée]n[ée]rale|civilisation|empire|dynastie)\b", 3, "culture"),
        (r"\b(Napol[ée]on|Louis XIV|R[ée]volution française|Gr[èe]ce antique|Rome)\b", 2, "ref_historique"),
        (r"\b(science|physique|chimie|biologie|astronomie|g[ée]ographie)\b", 2, "sciences"),
        (r"\b(litt[ée]rature|art|musique classique|peinture|cin[ée]ma)\b", 2, "arts"),
        (r"\b(religion|mythologie|l[ée]gende)\b", 2, "humanites"),
    )
)

_TECHNICAL_RX: Final = _compile_many(
    (
        (r"\b(code|python|typescript|javascript|sql|api|debug|refactor)\b", 2, "tech"),
        (r"\b(analyse|analyser|architecture|algorithme)\b", 2, "analyse_tech"),
        (r"\b(erreur|stack trace|exception|compile)\b", 2, "debug"),
    )
)

_COMPLEX_RX: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\b(raisonne|raisonnement|argumente|démontre)\b",
        r"\b(stratégie|plan détaillé|plusieurs aspects)\b",
    )
)

_HEAVY_RX: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\b(rapport complet|analyse approfondie|revue de code|audit)\b",
        r"\b(plusieurs pages|très long|document entier|thèse)\b",
        r"\b(architecture complète|refactor complet)\b",
    )
)

_SIMPLE_RX: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p, re.I)
    for p in (
        r"^(salut|bonjour|merci|ok|oui|non|coucou)\b",
        r"\b(heure|date|volume|pause|play|stop|musique|météo)\b",
        r"\b(joue|lance|monte le volume|baisse le volume)\b",
    )
)

_DEVELOPMENT_RX: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\b(expos[ée]|dissertation|développe|en détail|plusieurs paragraphes)\b",
        r"\b(explique.{0,20}détail|pourquoi.{5,})\b",
    )
)

_LENGTH_TIERS: Final[tuple[tuple[int, int], ...]] = ((800, 3), (400, 2), (200, 1))
_WORD_TIERS: Final[tuple[tuple[int, int], ...]] = ((120, 2), (60, 1))


def _tokenize(low: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-zàâäéèêëïîôùûüç0-9']+", low))


def _set_hits(words: frozenset[str], vocab: frozenset[str]) -> int:
    return len(words & vocab)


def _apply_rx(
    low: str,
    patterns: tuple[tuple[re.Pattern[str], int, str], ...],
    signals: list[str],
) -> int:
    score = 0
    for rx, weight, label in patterns:
        if rx.search(low):
            score += weight
            signals.append(label)
    return score


def _score_length(text: str) -> int:
    s = 0
    n = len(text)
    w = len(text.split())
    for threshold, pts in _LENGTH_TIERS:
        if n >= threshold:
            s += pts
            break
    for threshold, pts in _WORD_TIERS:
        if w >= threshold:
            s += pts
            break
    return s


def detect_intent(text: str, signals: list[str], words: frozenset[str] | None = None) -> Intent:
    low = (text or "").strip().lower()
    if not low:
        return Intent.GENERAL

    w = words if words is not None else _tokenize(low)

    if w & _COMMAND_WORDS:
        signals.append("commande_set")
        return Intent.COMMAND

    first = low.split(None, 1)[0] if low else ""
    if first in _SIMPLE_GREETINGS and len(w) <= 4:
        signals.append("simple")
        return Intent.COMMAND

    for rx in _SIMPLE_RX:
        if rx.search(low):
            if w & _COMMAND_WORDS:
                signals.append("commande")
                return Intent.COMMAND
            signals.append("simple")
            return Intent.COMMAND

    if w & _PEDAGOGY_WORDS or _apply_rx(low, _PEDAGOGICAL_RX, signals):
        return Intent.PEDAGOGICAL
    if w & _CULTURE_WORDS or _apply_rx(low, _CULTURAL_RX, signals):
        return Intent.CULTURAL
    if w & _TECH_WORDS or _apply_rx(low, _TECHNICAL_RX, signals):
        return Intent.TECHNICAL
    return Intent.GENERAL


def requires_development(text: str) -> bool:
    low = (text or "").lower()
    if len(low) >= 250:
        return True
    return any(rx.search(low) for rx in _DEVELOPMENT_RX)


_SIMPLE_GREETING_RX: Final[re.Pattern[str]] = re.compile(
    r"^(?:salut|bonjour|bonsoir|merci|ok|oui|non|coucou|hey|hello|hi|bjr|cc)\b",
    re.I,
)


def _strip_wake_name(text: str) -> str:
    """Enleve « jarvis » pour detecter salutations courtes (« bonjour jarvis »)."""
    t = (text or "").strip()
    t = re.sub(r"^(?:jarvis[,!\s]+|(?:dis\s+)?jarvis\s+)", "", t, flags=re.I).strip()
    t = re.sub(r"[,!\s]+jarvis\s*$", "", t, flags=re.I).strip()
    return t or (text or "").strip()


def is_simple_chat(text: str, analysis: RouterAnalysis | None = None) -> bool:
    """
    Salutation / acquiescement court (score 0, intent commande).
    Chemin rapide : peu de tokens, pas de web ni streaming early-abort.
    """
    raw = (text or "").strip()
    if not raw or len(raw) > 48:
        return False
    core = _strip_wake_name(raw)
    ana = analysis or analyze_query(raw)
    if ana.intent != Intent.COMMAND or ana.complexity_score > 0:
        return False
    low = core.lower()
    words = re.findall(r"[a-zàâäéèêëïîôùûüç0-9']+", low)
    if len(words) > 5:
        return False
    if low in _SIMPLE_GREETINGS:
        return True
    return bool(_SIMPLE_GREETING_RX.match(low))


def analyze_query(
    text: str,
    *,
    web_used: bool = False,
    fts_hints: list | None = None,
    fts_elapsed_ms: float = 0.0,
) -> RouterAnalysis:
    """Analyse synchrone — typiquement <1 ms sur requête courte."""
    t0 = time.perf_counter()
    raw = (text or "").strip()
    low = raw.lower()
    words = _tokenize(low)
    signals: list[str] = []
    score = _score_length(raw)

    if web_used:
        score += 2
        signals.append("web_context")

    fts_n = len(fts_hints or [])
    if fts_n:
        score += min(2, fts_n)
        signals.append(f"fts_prefetch:{fts_n}")

    score += _set_hits(words, _PEDAGOGY_WORDS)
    score += _set_hits(words, _CULTURE_WORDS)
    score += _set_hits(words, _TECH_WORDS)
    score += _apply_rx(low, _PEDAGOGICAL_RX, signals)
    score += _apply_rx(low, _CULTURAL_RX, signals)
    score += _apply_rx(low, _TECHNICAL_RX, signals)

    for rx in _COMPLEX_RX:
        if rx.search(low):
            score += 2
            signals.append("complex")

    if _set_hits(words, _HEAVY_WORDS):
        score += 3
        signals.append("heavy_set")
    for rx in _HEAVY_RX:
        if rx.search(low):
            score += 3
            signals.append("heavy")

    for rx in _SIMPLE_RX:
        if rx.search(low):
            score -= 2
            signals.append("simple_penalty")

    intent = detect_intent(raw, signals, words)

    if intent == Intent.PEDAGOGICAL:
        score += 2
        signals.append("intent_pedagogique")
    elif intent == Intent.CULTURAL:
        score += 2
        signals.append("intent_culturel")
    elif intent == Intent.TECHNICAL:
        score += 1

    score = max(0, score)
    elapsed = (time.perf_counter() - t0) * 1000.0

    return RouterAnalysis(
        raw_text=raw,
        char_count=len(raw),
        word_count=len(raw.split()),
        complexity_score=score,
        intent=intent,
        matched_signals=signals,
        requires_development=requires_development(raw),
        elapsed_ms=round(elapsed, 3),
        fts_hit_count=fts_n,
        fts_elapsed_ms=round(fts_elapsed_ms, 3),
    )


async def analyze_query_async(
    text: str,
    *,
    web_used: bool = False,
) -> RouterAnalysis:
    """API async — calcul CPU léger in-process (pas de thread)."""
    return analyze_query(text, web_used=web_used)


def score_complexity(text: str, *, web_used: bool = False) -> int:
    return analyze_query(text, web_used=web_used).complexity_score


def is_heavy_task(text: str, score: int) -> bool:
    low = (text or "").lower()
    if score >= CLOUD_HEAVY_THRESHOLD:
        return True
    words = _tokenize(low)
    if words & _HEAVY_WORDS:
        return True
    return any(rx.search(low) for rx in _HEAVY_RX)


def decide_route(
    text: str,
    *,
    fast_mode: bool = False,
    web_used: bool = False,
    cloud_enabled: bool = False,
    cloud_quota_ok: bool = True,
    force_cloud: bool | None = None,
    explicit_local: bool = False,
    analysis: RouterAnalysis | None = None,
) -> tuple[Route, int, RouterAnalysis]:
    ana = analysis or analyze_query(text, web_used=web_used)
    score = ana.complexity_score

    if fast_mode:
        return Route.LOCAL_WAKE, score, ana

    if is_simple_chat(text, ana):
        signals = list(ana.matched_signals)
        signals.append("simple_chat")
        ana = ana.model_copy(update={"matched_signals": signals})
        return Route.LOCAL_FAST, score, ana

    # Web = prompt lourd : Groq si dispo (evite timeout Ollama 3B + 5 extraits)
    if web_used and cloud_enabled and cloud_quota_ok:
        signals = list(ana.matched_signals)
        signals.append("web_prefer_cloud")
        ana = ana.model_copy(update={"matched_signals": signals})
        if is_heavy_task(text, score):
            return Route.CLOUD_HEAVY, score, ana
        return Route.CLOUD, score, ana

    if explicit_local:
        if score >= 3 or ana.intent in (Intent.PEDAGOGICAL, Intent.CULTURAL):
            return Route.LOCAL_QUALITY, score, ana
        return Route.LOCAL_FAST, score, ana

    if force_cloud is False:
        cloud_enabled = False
    elif force_cloud is True:
        if cloud_enabled and cloud_quota_ok:
            if is_heavy_task(text, score):
                return Route.CLOUD_HEAVY, score, ana
            return Route.CLOUD, score, ana
        if score >= 3 or ana.intent in (Intent.PEDAGOGICAL, Intent.CULTURAL):
            return Route.LOCAL_QUALITY, score, ana
        return Route.LOCAL_FAST, score, ana

    if ana.intent in (Intent.PEDAGOGICAL, Intent.CULTURAL):
        use_cloud = cloud_enabled and cloud_quota_ok and (
            score >= CLOUD_COMPLEXITY_THRESHOLD
            or score >= ROUTER_PEDAGOGICAL_CLOUD_SCORE
            or (ana.requires_development and score >= 3)
        )
        if use_cloud:
            if is_heavy_task(text, score):
                return Route.CLOUD_HEAVY, score, ana
            return Route.CLOUD, score, ana
        return Route.LOCAL_QUALITY, score, ana

    if cloud_enabled and cloud_quota_ok and score >= CLOUD_COMPLEXITY_THRESHOLD:
        if is_heavy_task(text, score):
            return Route.CLOUD_HEAVY, score, ana
        return Route.CLOUD, score, ana

    if score >= 3 or ana.requires_development:
        return Route.LOCAL_QUALITY, score, ana

    return Route.LOCAL_FAST, score, ana


async def decide_route_async(
    text: str,
    *,
    fast_mode: bool = False,
    web_used: bool = False,
    cloud_enabled: bool = False,
    cloud_quota_ok: bool = True,
    force_cloud: bool | None = None,
    explicit_local: bool = False,
    analysis: RouterAnalysis | None = None,
) -> tuple[Route, int, RouterAnalysis]:
    return decide_route(
        text,
        fast_mode=fast_mode,
        web_used=web_used,
        cloud_enabled=cloud_enabled,
        cloud_quota_ok=cloud_quota_ok,
        force_cloud=force_cloud,
        explicit_local=explicit_local,
        analysis=analysis,
    )


def route_model_hint(route: Route) -> str:
    """Indication légère pour le choix de modèle (utilisé par l'API)."""
    if route == Route.LOCAL_WAKE:
        return "wake"
    if route == Route.LOCAL_QUALITY:
        return "quality"
    if route in (Route.CLOUD, Route.CLOUD_HEAVY):
        return "cloud"
    return "fast"
