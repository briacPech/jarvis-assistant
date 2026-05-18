"""
Controle media Windows (volume systeme + touches lecture).
Utilise par Jarvis pour Tidal et toute app audio active.
"""

from __future__ import annotations

import ctypes
import re
import sys

_KEYUP = 2
_VK = {
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
    "play_pause": 0xB3,
    "next": 0xB0,
    "prev": 0xB1,
    "return": 0x0D,
    "down": 0x28,
}


def _key_tap(vk: int, repeat: int = 1) -> None:
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    for _ in range(max(1, repeat)):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, _KEYUP, 0)


def volume_up(steps: int = 3) -> None:
    _key_tap(_VK["volume_up"], steps)


def volume_down(steps: int = 3) -> None:
    _key_tap(_VK["volume_down"], steps)


def mute_toggle() -> None:
    _key_tap(_VK["mute"], 1)


def play_pause() -> None:
    _key_tap(_VK["play_pause"], 1)


def send_enter() -> None:
    _key_tap(_VK["return"], 1)


def send_key_down(count: int = 1) -> None:
    _key_tap(_VK["down"], max(1, count))


def _set_foreground(hwnd: int) -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    if fg_thread != target_thread:
        user32.AttachThreadInput(fg_thread, target_thread, True)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    ok = bool(user32.SetForegroundWindow(hwnd))
    if fg_thread != target_thread:
        user32.AttachThreadInput(fg_thread, target_thread, False)
    return ok


def focus_window(title_parts: tuple[str, ...], retries: int = 6, delay: float = 0.3) -> bool:
    """Met au premier plan une fenetre dont le titre contient l'un des motifs."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    needles = tuple(t.lower() for t in title_parts if t)

    for _ in range(max(1, retries)):
        found: list[int] = []

        def _enum(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd) + 1
                buf = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(hwnd, buf, length)
                title = (buf.value or "").lower()
                if any(n in title for n in needles):
                    found.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(_enum), 0)
        if found:
            hwnd = found[0]
            if _set_foreground(hwnd):
                return True
        time.sleep(delay)
    return False


def next_track() -> None:
    _key_tap(_VK["next"], 1)


def previous_track() -> None:
    _key_tap(_VK["prev"], 1)


def set_master_volume_percent(percent: int) -> bool:
    """Regle le volume systeme (0-100). Retourne False si pycaw indisponible."""
    if sys.platform != "win32":
        return False
    pct = max(0, min(100, int(percent)))
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(pct / 100.0, None)
        return True
    except Exception:
        return False


def get_master_volume_percent() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        scalar = volume.GetMasterVolumeLevelScalar()
        return int(round(float(scalar) * 100))
    except Exception:
        return None


def parse_volume_percent(text: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*%?", text)
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))
