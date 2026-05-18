# app/core/router.py — routeur heuristique <5 ms (regex + sets)

from __future__ import annotations

import re
import time
from enum import Enum
from typing import Final, Literal

from pydantic import BaseModel, Field

from app.config import Settings, TargetModel, get_settings

# --- Intentions thématiques ---


class ThemeIntent(str, Enum):
    CULTURE = "culture"
    HISTOIRE = "histoire"
    EXPOSE = "expose"
    SCIENCE = "science"
    PHILOSOPHIE = "philosophie"


# --- Sets O(1) ---

_CULTURE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "culture",
        "civilisation",
        "art",
        "musée",
        "patrimoine",
        "tradition",
        "littérature",
        "cinéma",
        "peinture",
    }
)

_HISTOIRE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "histoire",
        "historique",
        "guerre",
        "révolution",
        "empire",
        "siècle",
        "antiquité",
        "médiéval",
        "napoléon",
        "dynastie",
    }
)

_EXPOSE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "exposé",
        "expose",
        "dissertation",
        "synthèse",
        "synthese",
        "développe",
        "developpe",
        "détaill",
        "detaille",
        "vulgaris",
        "présent",
        "present",
        "raconte",
        "explique",
        "fiche",
    }
)

_SCIENCE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "science",
        "physique",
        "chimie",
        "biologie",
        "mathématiques",
        "astronomie",
        "quantique",
        "atome",
        "génétique",
    }
)

_PHILO_WORDS: Final[frozenset[str]] = frozenset(
    {
        "philosophie",
        "philosophe",
        "éthique",
        "morale",
        "métaphysique",
        "existentialisme",
        "platon",
        "socrate",
        "kant",
    }
)

_STRUCTURE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "expose",
        "exposé",
        "synthese",
        "synthèse",
        "detaille",
        "détaillé",
        "pourquoi",
        "comment",
        "raconte",
        "moi",
        "chronologie",
        "compare",
        "analyse",
    }
)

# --- Regex précompilées ---

_RX_EXPOSE: Final[re.Pattern[str]] = re.compile(
    r"\b(expos[ée]|dissertation|synth[èe]se|développ|developp|"
    r"vulgaris|fais un exposé|parle[- ]moi de)\b",
    re.I,
)
_RX_WHY: Final[re.Pattern[str]] = re.compile(
    r"\b(pourquoi|comment|qu['']est[- ]ce que)\b", re.I
)
_RX_LONG: Final[re.Pattern[str]] = re.compile(r".{280,}", re.S)

_HYDRATION_SKELETON: Final[str] = """\
Complète UNIQUEMENT les sections Markdown ci-dessous (garde tous les titres).

# {title}

## Introduction
<!-- 2–3 phrases -->

## Développement
<!-- Corps structuré -->

## Points clés
-
-
-

## Conclusion
<!-- Synthèse -->

---
**Question utilisateur :** {question}
"""


def _tokenize(low: str) -> frozenset[str]:
    return frozenset(re.findall(r"[\w\u00c0-\u024f']+", low, flags=re.UNICODE))


def _set_hits(words: frozenset[str], vocab: frozenset[str]) -> int:
    return len(words & vocab)


def _detect_intentions(words: frozenset[str], low: str) -> list[ThemeIntent]:
    found: list[ThemeIntent] = []
    if words & _CULTURE_WORDS:
        found.append(ThemeIntent.CULTURE)
    if words & _HISTOIRE_WORDS or _RX_EXPOSE.search(low):
        found.append(ThemeIntent.HISTOIRE)
    if words & _EXPOSE_WORDS or _RX_EXPOSE.search(low):
        found.append(ThemeIntent.EXPOSE)
    if words & _SCIENCE_WORDS:
        found.append(ThemeIntent.SCIENCE)
    if words & _PHILO_WORDS:
        found.append(ThemeIntent.PHILOSOPHIE)
    return found


def _score_complexite(raw: str, words: frozenset[str], intents: list[ThemeIntent]) -> int:
    """Score 0–100 : longueur + structure + thématiques."""
    score = 0
    n = len(raw)

    if n >= 80:
        score += 8
    if n >= 180:
        score += 12
    if n >= 350:
        score += 10
    if _RX_LONG.search(raw):
        score += 15

    score += min(20, _set_hits(words, _STRUCTURE_WORDS) * 6)
    if _RX_WHY.search(raw):
        score += 8
    if _RX_EXPOSE.search(raw):
        score += 18

    if ThemeIntent.EXPOSE in intents:
        score += 15
    if ThemeIntent.HISTOIRE in intents:
        score += 8
    if ThemeIntent.CULTURE in intents:
        score += 6
    if ThemeIntent.PHILOSOPHIE in intents:
        score += 8
    if ThemeIntent.SCIENCE in intents:
        score += 6

    return min(100, score)


def _guess_title(question: str) -> str:
    q = question.strip()
    q = re.sub(
        r"^(explique|développe|présente|fais un exposé sur|parle-moi de)\s+",
        "",
        q,
        flags=re.I,
    )
    q = q.rstrip("?.! ").strip()
    return (q[0].upper() + q[1:][:120]) if len(q) >= 4 else "Sujet demandé"


def hydrate_prompt(user_text: str, *, enabled: bool = True) -> tuple[str, bool]:
    """Encapsule la requête dans un squelette Markdown si exposé / synthèse."""
    if not enabled:
        return user_text.strip(), False
    low = user_text.lower()
    if not (_RX_EXPOSE.search(low) or _set_hits(_tokenize(low), _EXPOSE_WORDS)):
        return user_text.strip(), False
    title = _guess_title(user_text)
    return _HYDRATION_SKELETON.format(title=title, question=user_text.strip()), True


def _pick_target(
    score: int,
    intents: list[ThemeIntent],
    raw: str,
    *,
    settings: Settings,
    fast_mode: bool,
    force_cloud: bool | None,
) -> TargetModel:
    if fast_mode:
        return "wake"

    low = raw.lower()
    is_expose = ThemeIntent.EXPOSE in intents or bool(_RX_EXPOSE.search(low))

    if force_cloud is True and settings.cloud_enabled and settings.cloud_api_key:
        return "cloud"
    if force_cloud is False:
        if is_expose or score > settings.complexity_quality_threshold:
            return "quality"
        return "fast"

    if is_expose or score > settings.complexity_cloud_threshold:
        if settings.cloud_enabled and settings.cloud_api_key:
            return "cloud"
        return "quality"

    if score > settings.complexity_quality_threshold:
        return "quality"

    return "fast"


def _system_variant(target: TargetModel) -> Literal["base", "fast", "quality", "cloud"]:
    if target == "wake":
        return "fast"
    if target == "quality":
        return "quality"
    if target == "cloud":
        return "cloud"
    return "base"


def _resolve_ollama_model(target: TargetModel, settings: Settings) -> str:
    if target == "wake":
        return settings.model_wake
    if target == "quality":
        return settings.model_quality
    return settings.model_fast


class RouteDecision(BaseModel):
    """Résultat du routage (<5 ms typique)."""

    raw_text: str = ""
    score_complexite: int = Field(ge=0, le=100, default=0)
    intentions: list[str] = Field(default_factory=list)
    target_model: TargetModel = "fast"
    ollama_model: str = ""
    system_variant: Literal["base", "fast", "quality", "cloud"] = "base"
    user_prompt: str = ""
    hydrated: bool = False
    use_cloud: bool = False
    elapsed_ms: float = 0.0


def route_request(
    text: str,
    *,
    settings: Settings | None = None,
    fast_mode: bool = False,
    force_cloud: bool | None = None,
) -> RouteDecision:
    """
    Routeur principal : score, intention, hydratation, cible fast/quality/cloud.
    """
    t0 = time.perf_counter()
    cfg = settings or get_settings()
    raw = (text or "").strip()
    low = raw.lower()
    words = _tokenize(low)

    intents = _detect_intentions(words, low)
    score = _score_complexite(raw, words, intents)
    target = _pick_target(
        score,
        intents,
        raw,
        settings=cfg,
        fast_mode=fast_mode,
        force_cloud=force_cloud,
    )

    user_prompt, hydrated = hydrate_prompt(
        raw, enabled=cfg.prompt_hydration_enabled and not fast_mode
    )
    if ThemeIntent.EXPOSE in intents and not hydrated and not fast_mode:
        user_prompt, hydrated = hydrate_prompt(raw, enabled=True)

    elapsed = (time.perf_counter() - t0) * 1000.0

    return RouteDecision(
        raw_text=raw,
        score_complexite=score,
        intentions=[i.value for i in intents],
        target_model=target,
        ollama_model=_resolve_ollama_model(target, cfg),
        system_variant=_system_variant(target),
        user_prompt=user_prompt,
        hydrated=hydrated,
        use_cloud=target == "cloud",
        elapsed_ms=round(elapsed, 3),
    )
