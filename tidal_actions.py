"""
Detection des commandes musique / volume et execution (Tidal + media Windows).
"""

from __future__ import annotations

import re

from config import TIDAL_CDP_ENABLED, TIDAL_ENABLED

from tidal_launch import open_album, open_search, open_track, resolve_direct_media, spawn_playback_helper

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

# Import optionnel API Tidal
try:
    from tidal_client import is_configured as tidal_api_ready
    from tidal_client import search_top_hit
except ImportError:
    tidal_api_ready = lambda: False  # type: ignore
    search_top_hit = None  # type: ignore


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


# Titres / artistes frequents (STT ou phrases naturelles)
_KNOWN_QUERIES = (
    (re.compile(r"daft\s*punk", re.I), "Daft Punk"),
    (re.compile(r"\bdiscovery\b", re.I), "Daft Punk Discovery"),
    (re.compile(r"one\s+more\s+time", re.I), "Daft Punk One More Time"),
    (re.compile(
        r"harder\s*,?\s*better\s*,?\s*faster\s*,?\s*stronger", re.I
    ), "Daft Punk Harder Better Faster Stronger"),
)


def _infer_search_query(text: str) -> str | None:
    """Extrait une requete Tidal depuis une phrase naturelle."""
    raw = (text or "").strip()
    if not raw:
        return None
    for rx, q in _KNOWN_QUERIES:
        if rx.search(raw):
            return q
    m = re.search(
        r"(?:playlist|album|artiste|groupe|musique|morceaux?|chansons?)"
        r"(?:\s+(?:de|du|des|avec|pour))?\s+(.+?)(?:[.!?]|$)",
        raw,
        re.I,
    )
    if m:
        q = m.group(1).strip(" '\"")
        if len(q) > 2:
            return q[:80]
    m = re.search(
        r"(?:écoute|ecoute|joue|mets|met|lance|passe|ouvre|crée|cree)\s+(.+?)(?:[.!?]|$)",
        raw,
        re.I,
    )
    if m:
        q = m.group(1).strip(" '\"")
        q = re.sub(
            r"^(?:moi\s+)?(?:une\s+)?(?:playlist\s+)?(?:avec\s+)?(?:des\s+)?",
            "",
            q,
            flags=re.I,
        ).strip()
        if len(q) > 2 and not re.match(r"^(sur\s+)?tidal\b", q, re.I):
            return q[:80]
    return None


def _looks_like_music_request(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    triggers = (
        "tidal", "musique", "playlist", "album", "chanson", "morceau",
        "daft punk", "écoute", "ecoute", "son ", "volume",
        "joue", "mets ", "met ", "lance", "pause", "suivant",
        "discovery", "one more time", "harder better",
    )
    return any(k in t for k in triggers)


def _use_tidal_cdp() -> bool:
    if not TIDAL_CDP_ENABLED:
        return False
    try:
        from tidal_cdp import cdp_playback_available

        return cdp_playback_available()
    except ImportError:
        return False


def _play_on_tidal(query: str, meta: dict) -> tuple[bool, str, dict]:
    """Ouvre Tidal et demarre la lecture (CDP prioritaire, sinon touches clavier)."""
    q = (query or "").strip()
    if not q:
        return False, "", meta

    use_cdp = _use_tidal_cdp()
    meta["tidal_cdp"] = use_cdp

    if tidal_api_ready() and search_top_hit:
        hit, err = search_top_hit(q)
        if hit and hit.get("id") and hit.get("type") == "tracks":
            tid = str(hit["id"])
            meta["tidal_track"] = hit
            if use_cdp:
                meta["tidal_action"] = "cdp_track"
                spawn_playback_helper(True, mode="track", media_id=tid)
            else:
                url, desktop = open_track(tid)
                meta["tidal_url"] = url
                meta["tidal_desktop"] = desktop
                meta["tidal_action"] = "play_track"
                spawn_playback_helper(desktop, mode="track", media_id=tid)
            title = hit.get("title", q)
            artist = hit.get("artist") or ""
            msg = f"Je lance {title}"
            if artist:
                msg += f" de {artist}"
            msg += " sur Tidal."
            return True, msg, meta
        if err:
            meta["tidal_error"] = err

    direct = resolve_direct_media(q)
    if direct:
        kind, mid = direct
        if use_cdp:
            meta["tidal_action"] = f"cdp_{kind}"
            spawn_playback_helper(True, mode=kind, media_id=mid)
            if kind == "album":
                return True, f"Je lance l'album « {q} » sur Tidal.", meta
            return True, f"Je lance « {q} » sur Tidal.", meta
        if kind == "album":
            url, desktop = open_album(mid)
            meta["tidal_action"] = "play_album"
        else:
            url, desktop = open_track(mid)
            meta["tidal_action"] = "play_track"
        meta["tidal_url"] = url
        meta["tidal_desktop"] = desktop
        spawn_playback_helper(desktop, mode=kind, media_id=mid)
        return True, f"Je lance « {q} » dans l'application Tidal.", meta

    if use_cdp:
        meta["tidal_action"] = "cdp_search"
        spawn_playback_helper(True, mode="search", query=q)
        return True, f"Je lance « {q} » sur Tidal.", meta

    url, desktop = open_search(q)
    meta["tidal_action"] = "open_search"
    meta["tidal_url"] = url
    meta["tidal_desktop"] = desktop
    spawn_playback_helper(desktop, mode="search", query=q)
    return True, f"Je lance la recherche « {q} » dans l'application Tidal.", meta


def _match_play_query(text: str) -> str | None:
    t = _norm(text)
    play_verbs = r"(?:mets?|met|joue|lance|passe|ecoute|écoute)"
    patterns = (
        rf"^(?:jarvis[, ]+)?{play_verbs}\s+(?:moi\s+)?(?:sur\s+)?tidal\s+(.+)$",
        rf"^(?:jarvis[, ]+)?{play_verbs}\s+(.+?)\s+sur\s+tidal$",
        r"^tidal\s+(?:mets?|joue|lance)\s+(.+)$",
        rf"{play_verbs}\s+(?:la\s+)?(?:musique|chanson|morceau)\s+(.+)$",
        rf"{play_verbs}\s+(.+?)\s+(?:sur\s+)?(?:tidal|musique)$",
        # « joue Daft Punk » sans dire tidal
        rf"^(?:jarvis[, ]+)?{play_verbs}\s+(?:moi\s+)?(.+)$",
    )
    skip_q = re.compile(
        r"\b(pause|stop|volume|son|suivant|suivante|precedent|précédent|retour)\b",
        re.I,
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            q = m.group(1).strip(" .,!?:;")
            if q and len(q) > 1 and not skip_q.search(q):
                return q
    return None


def _is_media_command(text: str) -> bool:
    t = _norm(text)
    keys = (
        "volume", "son", "mute", "muet", "coupe le son", "remets le son",
        "play", "pause", "lecture", "suivant", "precedent", "précédent",
        "plus fort", "moins fort",
        "tidal", "musique", "joue", "mets ", "met ", "lance ", "ecoute",
    )
    return any(k in t for k in keys)


def is_media_command(text: str) -> bool:
    """Heuristique rapide : volume, pause, lecture (sans passer par le LLM)."""
    return _is_media_command(text)


def mentions_tidal(text: str) -> bool:
    """Mot-clé wake / STT : la phrase parle de Tidal."""
    return bool(re.search(r"\btidal\b", (text or ""), re.IGNORECASE))


def try_handle_tidal_command(text: str) -> tuple[bool, str, dict]:
    """
    Retourne (handled, response_courte, meta).
    """
    raw = (text or "").strip()
    if not raw:
        return False, "", {}

    t = _norm(raw)
    meta: dict = {"tidal_action": None}

    # --- Volume ---
    if re.search(r"\b(coupe|coupe le|mute|muet)\b.*\b(son|volume|audio)\b", t) or t in (
        "coupe le son", "mute", "muet",
    ):
        mute_toggle()
        meta["tidal_action"] = "mute"
        return True, "Son coupe.", meta

    if re.search(r"\b(remets|reactive|réactive)\b.*\b(son|volume)\b", t):
        mute_toggle()
        meta["tidal_action"] = "unmute"
        return True, "Son reactive.", meta

    pct = parse_volume_percent(raw)
    if pct is not None and re.search(r"\b(volume|son)\b", t):
        if set_master_volume_percent(pct):
            meta["tidal_action"] = f"volume_set_{pct}"
            return True, f"Volume regle a {pct} pour cent.", meta
        steps = max(1, abs(pct - (get_master_volume_percent() or 50)) // 5)
        if pct > 50:
            volume_up(steps)
        else:
            volume_down(steps)
        meta["tidal_action"] = "volume_approx"
        return True, f"Volume ajuste vers {pct} pour cent.", meta

    if re.search(r"\b(volume|son)\b", t) or "plus fort" in t or "moins fort" in t:
        if re.search(r"\b(monte|augmente|plus fort|hausse|monter)\b", t):
            volume_up(4)
            meta["tidal_action"] = "volume_up"
            cur = get_master_volume_percent()
            msg = "Volume monte."
            if cur is not None:
                msg += f" Environ {cur} pour cent."
            return True, msg, meta

        if re.search(r"\b(baisse|diminue|moins fort|descend|descends)\b", t):
            volume_down(4)
            meta["tidal_action"] = "volume_down"
            cur = get_master_volume_percent()
            msg = "Volume baisse."
            if cur is not None:
                msg += f" Environ {cur} pour cent."
            return True, msg, meta

    # --- Transport ---
    if re.search(r"\b(pause|mets en pause|met en pause)\b", t) and not _match_play_query(raw):
        play_pause()
        meta["tidal_action"] = "pause"
        return True, "Pause.", meta

    if t in ("play tidal", "lecture tidal") or (
        re.search(r"\b(reprends|continue|relance)\b", t) and not _match_play_query(raw)
    ):
        play_pause()
        meta["tidal_action"] = "play"
        return True, "Lecture.", meta

    if re.search(r"\b(morceau|piste|track|chanson)?\s*suivant", t) or "suivante" in t:
        next_track()
        meta["tidal_action"] = "next"
        return True, "Morceau suivant.", meta

    if re.search(r"\b(pr[eé]c[eé]dent|retour arri[eè]re)\b", t):
        previous_track()
        meta["tidal_action"] = "prev"
        return True, "Morceau precedent.", meta

    # --- Lecture / playlist / phrase naturelle ---
    query = _match_play_query(raw) or _infer_search_query(raw)
    if query and TIDAL_ENABLED:
        handled, msg, meta = _play_on_tidal(query, meta)
        if handled:
            return True, msg, meta

    if _looks_like_music_request(raw) and TIDAL_ENABLED:
        inferred = _infer_search_query(raw)
        if inferred:
            handled, msg, meta = _play_on_tidal(inferred, meta)
            if handled:
                return True, msg, meta

    if not _is_media_command(raw):
        return False, "", {}

    return False, "", {}


def try_handle_tidal_command_fast(text: str) -> tuple[bool, str, dict]:
    """Raccourci pour le mode wake : uniquement commandes courtes media."""
    return try_handle_tidal_command(text)
