# commande_locale.py — commandes PC (volume / touches média) sans LLM

from __future__ import annotations

import re
import unicodedata

from media_control import (
    get_master_volume_percent,
    mute_toggle,
    next_track,
    parse_volume_percent,
    play_pause,
    previous_track,
    set_master_volume_percent,
    volume_down,
    volume_up,
)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def executer_commande_locale(texte_commande: str) -> str:
    """API simple : exécute si possible, sinon message d'échec."""
    handled, reply, _meta = try_handle_local_command(texte_commande)
    if handled:
        return reply
    return "Commande non configurée, mais je l'ai interceptée."


def try_handle_local_command(text: str) -> tuple[bool, str, dict]:
    """
    Retourne (handled, réponse_courte, meta).
    Utilise media_control (touches VK / pycaw), pas de subprocess PowerShell.
    """
    raw = (text or "").strip()
    if not raw:
        return False, "", {}

    t = _norm(raw)
    meta: dict = {"local_action": None}

    # --- Volume précis (ex. « mets le volume à 50 pour cent ») ---
    pct = parse_volume_percent(raw)
    if pct is not None and re.search(r"\b(volume|son)\b", t):
        if set_master_volume_percent(pct):
            meta["local_action"] = f"volume_set_{pct}"
            return True, f"Volume réglé à {pct} pour cent.", meta
        volume_up(4) if pct > 50 else volume_down(4)
        meta["local_action"] = "volume_approx"
        return True, f"Volume ajusté vers {pct} pour cent.", meta

    # --- Volume relatif ---
    if re.search(r"\b(volume|son)\b", t) or "plus fort" in t or "moins fort" in t:
        if re.search(
            r"\b(augmente?|monte|hausse|plus fort|monter|augmenter)\b", t
        ):
            volume_up(4)
            meta["local_action"] = "volume_up"
            cur = get_master_volume_percent()
            msg = "Volume augmenté."
            if cur is not None:
                msg += f" Environ {cur} pour cent."
            return True, msg, meta

        if re.search(
            r"\b(diminue?|baisse|descend|moins fort|diminuer)\b", t
        ):
            volume_down(4)
            meta["local_action"] = "volume_down"
            cur = get_master_volume_percent()
            msg = "Volume diminué."
            if cur is not None:
                msg += f" Environ {cur} pour cent."
            return True, msg, meta

        if re.search(r"\b(coupe|coupe le|mute|muet)\b", t):
            mute_toggle()
            meta["local_action"] = "mute"
            return True, "Son coupé.", meta

        if re.search(r"\b(remets|reactive)\b.*\b(son|volume)\b", t):
            mute_toggle()
            meta["local_action"] = "unmute"
            return True, "Son réactivé.", meta

    # --- Transport média (Spotify, YouTube, Tidal, etc.) ---
    if re.search(r"\b(pause|stop)\b", t) and not re.search(
        r"\b(ordinateur|pc|windows|jarvis)\b", t
    ):
        play_pause()
        meta["local_action"] = "pause"
        return True, "Pause.", meta

    if re.search(r"\b(reprend|continue|relance|lecture)\b", t):
        play_pause()
        meta["local_action"] = "play"
        return True, "Lecture.", meta

    if re.search(r"\b(suivant|suivante)\b", t):
        next_track()
        meta["local_action"] = "next"
        return True, "Morceau suivant.", meta

    if re.search(r"\b(precedent|précédent|retour)\b", t):
        previous_track()
        meta["local_action"] = "prev"
        return True, "Morceau précédent.", meta

    return False, "", {}

