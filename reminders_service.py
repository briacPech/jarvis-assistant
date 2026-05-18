# reminders_service.py — rappels vocaux + notifications Windows

from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

_REMINDER_PATTERNS = (
    re.compile(
        r"(?:rappelle[- ]?moi|un rappel|me rappeler)\s+"
        r"(?:dans|pour dans)\s+(\d+)\s*(minute|minutes|min|heure|heures|h)\b"
        r"(?:\s+(?:de|pour|que))?\s*(.+)?$",
        re.I,
    ),
    re.compile(
        r"(?:rappelle[- ]?moi|un rappel)\s+(?:de|pour|que)\s+(.+?)\s+"
        r"(?:dans|pour dans)\s+(\d+)\s*(minute|minutes|min|heure|heures|h)\b",
        re.I,
    ),
    re.compile(
        r"(?:rappelle[- ]?moi|un rappel)\s+(?:à|a)\s+(\d{1,2})[h:](\d{2})?\s*(?:de|pour|que)?\s*(.+)?$",
        re.I,
    ),
)

_LIST_RE = re.compile(
    r"(?:quels sont mes rappels|liste mes rappels|mes rappels)\b",
    re.I,
)


def _parse_duration(amount: int, unit: str) -> timedelta:
    u = unit.lower()
    if u.startswith("h"):
        return timedelta(hours=amount)
    return timedelta(minutes=amount)


def _parse_reminder(text: str) -> Optional[tuple[str, datetime]]:
    raw = (text or "").strip()
    if not raw:
        return None

    m = _REMINDER_PATTERNS[0].search(raw)
    if m:
        delta = _parse_duration(int(m.group(1)), m.group(2))
        label = (m.group(3) or "Rappel").strip(" .,!?:;")
        return label, datetime.now() + delta

    m = _REMINDER_PATTERNS[1].search(raw)
    if m:
        label = m.group(1).strip(" .,!?:;")
        delta = _parse_duration(int(m.group(2)), m.group(3))
        return label, datetime.now() + delta

    m = _REMINDER_PATTERNS[2].search(raw)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        label = (m.group(3) or "Rappel").strip(" .,!?:;")
        due = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= datetime.now():
            due += timedelta(days=1)
        return label, due

    return None


def notify_windows(title: str, body: str) -> bool:
    if __import__("os").name != "nt":
        print(f"[Rappel] {title}: {body}")
        return False
    try:
        from plyer import notification

        notification.notify(
            title=title[:64],
            message=body[:256],
            app_name="Jarvis",
            timeout=12,
        )
        return True
    except Exception:
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
        print(f"[Rappel] {title}: {body}")
        return False


def try_handle_reminder(
    text: str,
    user_id: str,
    *,
    add_reminder_fn: Callable[..., None],
    get_reminders_fn: Callable[[str], list],
) -> tuple[bool, str]:
    """Crée ou liste des rappels sans passer par le LLM."""
    raw = (text or "").strip()
    if not raw:
        return False, ""

    if _LIST_RE.search(raw):
        items = get_reminders_fn(user_id)
        if not items:
            return True, "Tu n'as aucun rappel en attente."
        lines = []
        for it in items[:8]:
            due = it.get("due_date") or "?"
            lines.append(f"- {it.get('reminder', '?')} ({due})")
        return True, "Rappels :\n" + "\n".join(lines)

    parsed = _parse_reminder(raw)
    if not parsed:
        return False, ""

    label, due = parsed
    due_iso = due.strftime("%Y-%m-%d %H:%M:%S")
    add_reminder_fn(label, user_id=user_id, due_date=due_iso)
    when = due.strftime("%H:%M")
    return True, f"D'accord, je te rappelle « {label} » vers {when}."


_loop_started = False
_loop_lock = threading.Lock()


def start_reminder_loop(
    memory,
    *,
    poll_sec: float = 20.0,
) -> None:
    """Thread daemon : notifications pour rappels échus."""
    global _loop_started
    with _loop_lock:
        if _loop_started:
            return
        _loop_started = True

    def _tick():
        while True:
            try:
                due_items = memory.pop_due_reminders()
                for it in due_items:
                    rid = it.get("id")
                    label = it.get("reminder") or "Rappel"
                    notify_windows("Jarvis — rappel", label)
                    if rid:
                        memory.mark_reminder_done(rid)
            except Exception as e:
                print(f"[Rappels] boucle : {e}")
            threading.Event().wait(poll_sec)

    threading.Thread(target=_tick, daemon=True, name="jarvis-reminders").start()
    print("[Rappels] Surveillance active")
