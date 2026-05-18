"""
Controle lecture TIDAL via Chrome DevTools Protocol (app Electron).
Inspire de tidal-cli : navigation SPA + clic sur le bouton Play.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any
from urllib.parse import quote_plus

import requests

from config import DEBUG, TIDAL_CDP_PORT, TIDAL_CDP_RELAUNCH, TIDAL_CDP_TIMEOUT

from tidal_launch import _find_tidal_exe, browse_album_url, browse_track_url

_CDP_SESSION: requests.Session | None = None


def _session() -> requests.Session:
    global _CDP_SESSION
    if _CDP_SESSION is None:
        _CDP_SESSION = requests.Session()
    return _CDP_SESSION


def _log(msg: str) -> None:
    if DEBUG:
        print(f"[Tidal CDP] {msg}")


def is_cdp_available(port: int | None = None) -> bool:
    port = port or TIDAL_CDP_PORT
    try:
        r = _session().get(f"http://127.0.0.1:{port}/json/version", timeout=2)
        if r.status_code != 200:
            return False
        text = r.text.lower()
        return "tidal" in text or "electron" in text
    except requests.RequestException:
        return False


def is_tidal_process_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq TIDAL.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return "TIDAL.exe" in (r.stdout or "")
    except OSError:
        return False


def _kill_tidal() -> None:
    if sys.platform != "win32":
        return
    subprocess.run(
        ["taskkill", "/IM", "TIDAL.exe", "/F"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    time.sleep(2)


def _launch_tidal_with_cdp(port: int | None = None, start_url: str | None = None) -> bool:
    port = port or TIDAL_CDP_PORT
    exe = _find_tidal_exe()
    if not exe:
        return False
    args = [
        exe,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
    ]
    if start_url:
        args.append(start_url)
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            cwd=os.path.dirname(exe),
        )
        return True
    except OSError:
        return False


def ensure_tidal_cdp(start_url: str | None = None) -> bool:
    """Demarre TIDAL avec port debug CDP si necessaire."""
    port = TIDAL_CDP_PORT
    if is_cdp_available(port):
        return True

    if is_tidal_process_running() and TIDAL_CDP_RELAUNCH:
        _log("Relance TIDAL avec CDP (une seule fois au demarrage)...")
        _kill_tidal()

    if not _launch_tidal_with_cdp(port, start_url):
        return False

    deadline = time.time() + 25
    while time.time() < deadline:
        if is_cdp_available(port):
            time.sleep(1.5)
            return True
        time.sleep(0.5)
    return False


def _get_targets(port: int) -> list[dict]:
    r = _session().get(f"http://127.0.0.1:{port}/json", timeout=5)
    r.raise_for_status()
    return r.json()


def _find_main_target(port: int) -> dict:
    targets = _get_targets(port)
    for t in targets:
        if t.get("type") == "page" and "desktop.tidal.com" in (t.get("url") or ""):
            return t
    for t in targets:
        url = (t.get("url") or "").lower()
        if t.get("type") == "page" and "tidal" in url:
            return t
    raise RuntimeError(
        "Page TIDAL introuvable via CDP. Lance TIDAL avec --remote-debugging-port="
        f"{port}"
    )


def evaluate(port: int, expression: str, timeout: float | None = None) -> Any:
    try:
        import websocket
    except ImportError as e:
        raise RuntimeError("pip install websocket-client") from e

    target = _find_main_target(port)
    ws_url = target["webSocketDebuggerUrl"]
    wait = timeout or float(TIDAL_CDP_TIMEOUT)
    ws = websocket.create_connection(ws_url, timeout=wait)
    try:
        ws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": False,
                    },
                }
            )
        )
        deadline = time.time() + wait
        while time.time() < deadline:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("id") != 1:
                continue
            if msg.get("result", {}).get("exceptionDetails"):
                ex = msg["result"]["exceptionDetails"]
                raise RuntimeError(
                    ex.get("exception", {}).get("description") or ex.get("text") or "JS error"
                )
            return msg.get("result", {}).get("result", {}).get("value")
    finally:
        ws.close()


def _spa_navigate(port: int, spa_path: str) -> None:
    path = spa_path if spa_path.startswith("/") else f"/{spa_path}"
    evaluate(
        port,
        f"""(() => {{
  const link = document.querySelector('a[href="{path}"]');
  if (link) {{ link.click(); return 'link'; }}
  window.history.pushState({{}}, '', '{path}');
  window.dispatchEvent(new PopStateEvent('popstate'));
  return 'pushState';
}})()""",
    )
    time.sleep(3.0)


def _wait_for_tracks(port: int, timeout: float = 12) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = evaluate(
            port,
            "document.querySelectorAll('a[href*=\"/track/\"]').length",
        )
        if isinstance(count, (int, float)) and count > 0:
            return int(count)
        time.sleep(0.5)
    return 0


def _click_inline_play(port: int) -> bool:
    return (
        evaluate(
            port,
            """(() => {
  const isPlay = (l) => l === 'Play' || l === 'Lire';
  const playBtns = [...document.querySelectorAll('button[aria-label]')]
    .filter(b => isPlay(b.getAttribute('aria-label')));
  const inline = playBtns.filter(b => {
    const r = b.getBoundingClientRect();
    return r.width <= 24 && r.width > 0;
  });
  if (inline.length > 0) { inline[0].click(); return true; }
  return false;
})()""",
        )
        is True
    )


def _click_hero_play(port: int) -> bool:
    return (
        evaluate(
            port,
            """(() => {
  const isPlay = (l) => l === 'Play' || l === 'Lire';
  const playBtns = [...document.querySelectorAll('button[aria-label]')]
    .filter(b => isPlay(b.getAttribute('aria-label')));
  const hero = playBtns.find(b => {
    const r = b.getBoundingClientRect();
    return r.width >= 32 && r.width <= 48;
  });
  if (hero) { hero.click(); return true; }
  return false;
})()""",
        )
        is True
    )


def _click_transport_play(port: int) -> bool:
    return (
        evaluate(
            port,
            """(() => {
  const isPlay = (l) => l === 'Play' || l === 'Lire';
  const isShuffle = (l) => l === 'Shuffle' || l === 'Aléatoire' || l === 'Aleatoire';
  const btns = [...document.querySelectorAll('button[aria-label]')];
  const shuffleIdx = btns.findIndex(b => isShuffle(b.getAttribute('aria-label')));
  const start = shuffleIdx >= 0 ? shuffleIdx : 0;
  for (let i = start; i < Math.min(btns.length, start + 8); i++) {
    if (isPlay(btns[i]?.getAttribute('aria-label'))) {
      btns[i].click();
      return true;
    }
  }
  return false;
})()""",
        )
        is True
    )


def _click_main_track_play(port: int) -> bool:
    """Barre du bas : gros bouton Lire sur la page morceau."""
    return (
        evaluate(
            port,
            """(() => {
  const isPlay = (l) => l === 'Play' || l === 'Lire';
  const btns = [...document.querySelectorAll('button[aria-label]')]
    .filter(b => isPlay(b.getAttribute('aria-label')));
  const big = btns.find(b => {
    const r = b.getBoundingClientRect();
    return r.width >= 28 && r.height >= 28;
  });
  if (big) { big.click(); return true; }
  if (btns.length) { btns[0].click(); return true; }
  return false;
})()""",
        )
        is True
    )


def _is_playing(port: int) -> bool:
    val = evaluate(
        port,
        """(() => {
  const labels = [...document.querySelectorAll('button[aria-label]')]
    .map(b => b.getAttribute('aria-label'));
  return labels.some(l => l === 'Pause' || l === 'Mettre en pause' || l === 'En lecture');
})()""",
    )
    return bool(val)


def play_spa(
    spa_path: str,
    *,
    kind: str = "track",
    start_url: str | None = None,
) -> tuple[bool, str]:
    """
    Navigue dans l'app et clique Play.
    Retourne (ok, message).
    """
    if not ensure_tidal_cdp(start_url=start_url):
        return False, "Impossible d'activer le mode debug TIDAL."

    port = TIDAL_CDP_PORT
    try:
        _spa_navigate(port, spa_path)
        if _wait_for_tracks(port) == 0 and kind != "track":
            return False, "Page chargee mais aucun morceau visible."

        clicked = False
        if kind == "track":
            clicked = (
                _click_main_track_play(port)
                or _click_inline_play(port)
                or _click_transport_play(port)
            )
        else:
            clicked = (
                _click_hero_play(port)
                or _click_inline_play(port)
                or _click_transport_play(port)
            )

        if not clicked:
            clicked = _click_main_track_play(port)

        time.sleep(1.5)
        if _is_playing(port):
            return True, "Lecture demarree."

        if clicked:
            return True, "Play envoye (verifie dans TIDAL)."

        return False, "Bouton Play introuvable dans TIDAL."
    except Exception as e:
        return False, str(e)


def play_track_id(track_id: str) -> tuple[bool, str]:
    url = browse_track_url(str(track_id))
    return play_spa(f"/track/{track_id}", kind="track", start_url=url)


def play_album_id(album_id: str) -> tuple[bool, str]:
    url = browse_album_url(str(album_id))
    return play_spa(f"/album/{album_id}", kind="album", start_url=url)


def play_search_query(query: str) -> tuple[bool, str]:
    q = quote_plus((query or "").strip())
    url = f"https://tidal.com/browse/search?q={q}"
    if not ensure_tidal_cdp(start_url=url):
        return False, "CDP TIDAL indisponible."
    port = TIDAL_CDP_PORT
    try:
        time.sleep(3.5)
        if _wait_for_tracks(port, timeout=14) == 0:
            return False, "Aucun resultat de recherche."
        if _click_inline_play(port):
            time.sleep(1.2)
            if _is_playing(port):
                return True, "Lecture demarree."
            return True, "Play envoye sur le premier resultat."
        return False, "Play introuvable sur les resultats."
    except Exception as e:
        return False, str(e)


def cdp_playback_available() -> bool:
    return sys.platform == "win32" and bool(_find_tidal_exe())
