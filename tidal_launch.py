"""
Ouverture et lecture via l'application TIDAL Windows (pas le navigateur).
"""

from __future__ import annotations

import os
import re
import shlex
import sys
import time
from urllib.parse import quote_plus

import subprocess

from config import TIDAL_PLAY_WAIT_SEC, TIDAL_PREFER_DESKTOP

from media_control import focus_window, play_pause, send_enter, send_key_down

# Morceaux connus (lecture auto plus fiable que la page recherche)
_DIRECT_TRACKS: dict[str, str] = {
    "daft punk one more time": "1883659",
    "one more time": "1883659",
    "daft punk harder better faster stronger": "1883650",
    "harder better faster stronger": "1883650",
    "daft punk discovery": "album:59727856",
    "daft punk": "1883659",
}

_TIDAL_EXE: str | None = None


def _find_tidal_exe() -> str | None:
    global _TIDAL_EXE
    if _TIDAL_EXE is not None:
        return _TIDAL_EXE or None
    if sys.platform != "win32":
        _TIDAL_EXE = ""
        return None
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\tidal\shell\open\command",
        )
        cmd, _ = winreg.QueryValueEx(key, None)
        winreg.CloseKey(key)
        parts = shlex.split(cmd, posix=False)
        if parts and os.path.isfile(parts[0]):
            _TIDAL_EXE = parts[0]
            return _TIDAL_EXE
    except OSError:
        pass
    local = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "TIDAL",
    )
    if os.path.isdir(local):
        for root, _dirs, files in os.walk(local):
            if "TIDAL.exe" in files:
                _TIDAL_EXE = os.path.join(root, "TIDAL.exe")
                return _TIDAL_EXE
    _TIDAL_EXE = ""
    return None


def browse_search_url(query: str) -> str:
    q = quote_plus((query or "").strip())
    return f"https://tidal.com/browse/search?q={q}"


def browse_track_url(track_id: str) -> str:
    return f"https://tidal.com/browse/track/{track_id}"


def browse_album_url(album_id: str) -> str:
    return f"https://tidal.com/browse/album/{album_id}"


def resolve_direct_media(query: str) -> tuple[str, str] | None:
    """Retourne (type, id) avec type in track|album."""
    key = re.sub(r"\s+", " ", (query or "").strip().lower())
    raw = _DIRECT_TRACKS.get(key)
    if not raw:
        return None
    if raw.startswith("album:"):
        return "album", raw.split(":", 1)[1]
    return "track", raw


def open_in_desktop_app(target_url: str) -> bool:
    """Ouvre une URL Tidal dans l'exe desktop (pas le navigateur par defaut)."""
    exe = _find_tidal_exe()
    if not exe:
        return False
    try:
        subprocess.Popen(
            [exe, target_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True
    except OSError:
        return False


def open_search(query: str) -> tuple[str, bool]:
    """
    Ouvre une recherche. Retourne (url_utilisee, via_app_desktop).
    """
    url = browse_search_url(query)
    if TIDAL_PREFER_DESKTOP and open_in_desktop_app(url):
        return url, True
    if sys.platform == "win32":
        try:
            os.startfile(f"tidal://{url}")  # noqa: S606
            return url, True
        except OSError:
            pass
    import webbrowser

    webbrowser.open(url)
    return url, False


def _open_browse_url(url: str) -> tuple[str, bool]:
    if TIDAL_PREFER_DESKTOP and open_in_desktop_app(url):
        return url, True
    if sys.platform == "win32":
        try:
            os.startfile(url)  # noqa: S606
            return url, True
        except OSError:
            pass
    import webbrowser

    webbrowser.open(url)
    return url, False


def open_track(track_id: str) -> tuple[str, bool]:
    return _open_browse_url(browse_track_url(str(track_id)))


def open_album(album_id: str) -> tuple[str, bool]:
    return _open_browse_url(browse_album_url(str(album_id)))


def spawn_playback_helper(
    desktop: bool,
    *,
    mode: str = "search",
    media_id: str = "",
    query: str = "",
) -> None:
    """Lance la lecture (CDP + repli clavier) dans un sous-processus."""
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tidal_playback_helper.py")
    flag = "1" if desktop else "0"
    arg = media_id or query
    try:
        subprocess.Popen(
            [sys.executable, helper, mode, arg, flag],
            cwd=os.path.dirname(helper),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    except OSError:
        start_playback_after_open(desktop)


def open_query(query: str) -> tuple[str, bool, str]:
    """
    Ouvre morceau direct ou recherche.
    Retourne (url, desktop, mode) mode in ('track','search').
    """
    q = (query or "").strip()
    direct = resolve_direct_media(q)
    if direct:
        kind, mid = direct
        if kind == "album":
            url, desktop = open_album(mid)
            return url, desktop, "album"
        url, desktop = open_track(mid)
        return url, desktop, "track"
    url, desktop = open_search(q)
    return url, desktop, "search"


def start_playback_after_open(desktop: bool) -> None:
    """
    Apres ouverture : focus fenetre Tidal, selectionner 1er resultat, lecture.
    """
    wait = max(2.0, float(TIDAL_PLAY_WAIT_SEC))
    time.sleep(wait)

    titles = ("TIDAL", "Tidal") if desktop else ("TIDAL", "Tidal", "Chrome", "Edge", "Firefox")
    focused = focus_window(titles, retries=10, delay=0.4)

    if focused:
        time.sleep(0.5)
        send_enter()
        time.sleep(0.25)
        send_key_down(1)
        time.sleep(0.2)
        send_enter()
        time.sleep(0.6)

    for _ in range(4):
        play_pause()
        time.sleep(0.4)
