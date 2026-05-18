# memory_recall.py — reponses rapides depuis les faits SQLite (sans LLM lourd)

from __future__ import annotations

import re

try:
    from config import JARVIS_USER_NAME
except ImportError:
    JARVIS_USER_NAME = "Briac"

_RECALL_RX = re.compile(
    r"\b("
    r"rappelle[- ]?moi|souviens[- ]?toi|rappel sur moi|"
    r"ce que tu sais sur moi|qu['']est[- ]ce que tu sais sur moi|"
    r"qu['']est[- ]ce que tu retiens|mes infos|ma mémoire|ma memoire|"
    r"tu te souviens|tu sais quoi sur moi|infos sur moi"
    r")\b",
    re.IGNORECASE,
)


def is_memory_recall_request(text: str) -> bool:
    return bool(_RECALL_RX.search((text or "").strip()))


def reply_from_stored_facts(facts: list[str], *, user_name: str | None = None) -> str | None:
    """Construit une reponse lisible a partir des faits deja en base."""
    clean = [f.strip() for f in (facts or []) if (f or "").strip()]
    name = (user_name or JARVIS_USER_NAME or "").strip() or "toi"
    if not clean:
        return (
            f"Je n'ai encore rien de note sur toi, {name}. "
            "Dis par exemple : « retiens que j'aime le café »."
        )
    lines = [f"Voici ce que je retiens sur toi, {name} :", ""]
    for f in clean[:12]:
        lines.append(f"• {f}")
    lines.append("")
    lines.append("Si quelque chose manque, dis « retiens que… » et je l'ajoute.")
    return "\n".join(lines)
