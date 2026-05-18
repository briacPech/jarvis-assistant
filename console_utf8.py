# console_utf8.py — console Windows en UTF-8 (print / logs accentués)

from __future__ import annotations

import io
import sys


def enable_console_utf8() -> None:
    """Force stdout/stderr en UTF-8 sous Windows."""
    if sys.platform != "win32":
        return
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "buffer"):
            continue
        try:
            if getattr(stream, "encoding", "").lower().replace("-", "") == "utf8":
                continue
        except Exception:
            pass
        setattr(
            sys,
            name,
            io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace"),
        )


enable_console_utf8()
