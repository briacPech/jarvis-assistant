# prompt_hydration.py — squelette Markdown pédagogique (complétion guidée)

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from router import RouterAnalysis

try:
    from router import Intent
except ImportError:

    class Intent:  # type: ignore
        PEDAGOGICAL = "pedagogique"
        CULTURAL = "culturel"
        GENERAL = "general"


_EXPOSE_RX = re.compile(
    r"\b(expos[ée]|vulgaris|explique|développe|détaill|présent|dissertation|"
    r"synth[èe]se|chronologie|fiche|leçon|cours|pourquoi|comment|qu['']est-ce)\b",
    re.I,
)

_SKELETON_PEDAGOGICAL = """\
Complète UNIQUEMENT les sections ci-dessous en Markdown (garde tous les titres tels quels).

# {title}

## En bref
<!-- 2 à 3 phrases accessibles -->

## Points clés
-
-
-

## Développement
<!-- Corps structuré, paragraphes courts -->

## Exemple concret
<!-- Un cas ou une analogie -->

## À retenir
<!-- 3 puces maximum -->

---
**Consigne utilisateur :** {question}
"""

_SKELETON_CULTURAL = """\
Complète UNIQUEMENT les sections ci-dessous en Markdown (garde tous les titres tels quels).

# {title}

## Contexte
<!-- Cadre historique / culturel bref -->

## Faits essentiels
-
-
-

## Analyse
<!-- Liens de cause à effet, nuances -->

## Chronologie ou repères
<!-- Dates ou étapes si pertinent -->

## Sources implicites
<!-- Pas d'invention : rester factuel -->

---
**Question :** {question}
"""


def _guess_title(question: str) -> str:
    q = (question or "").strip()
    q = re.sub(
        r"^(explique|développe|présente|fais un exposé sur|parle-moi de)\s+",
        "",
        q,
        flags=re.I,
    )
    q = q.rstrip("?.! ").strip()
    if len(q) < 4:
        return "Sujet demandé"
    return q[0].upper() + q[1:][:120]


def should_hydrate_prompt(
    analysis: "RouterAnalysis | None",
    user_text: str = "",
) -> bool:
    if analysis is None:
        return bool(_EXPOSE_RX.search(user_text or ""))
    intent = getattr(analysis, "intent", None)
    intent_val = intent.value if hasattr(intent, "value") else str(intent)
    if intent_val in (Intent.PEDAGOGICAL, Intent.CULTURAL):
        return True
    if getattr(analysis, "requires_development", False) and _EXPOSE_RX.search(
        user_text
    ):
        return True
    return False


def hydrate_user_prompt(
    user_text: str,
    analysis: "RouterAnalysis | None" = None,
) -> tuple[str, bool]:
    """
    Enrobe la requête dans un squelette Markdown si intention exposé/vulgarisation.
    Retourne (texte_hydraté, a_été_hydraté).
    """
    raw = (user_text or "").strip()
    if not raw or not should_hydrate_prompt(analysis, raw):
        return raw, False

    title = _guess_title(raw)
    intent = getattr(analysis, "intent", None) if analysis else None
    intent_val = intent.value if hasattr(intent, "value") else str(intent or "")

    if intent_val == Intent.CULTURAL:
        skeleton = _SKELETON_CULTURAL
    else:
        skeleton = _SKELETON_PEDAGOGICAL

    hydrated = skeleton.format(title=title, question=raw)
    return hydrated, True
