"""Helper : lecture TIDAL via CDP (prioritaire) ou touches clavier."""
import sys

from config import TIDAL_CDP_ENABLED

from tidal_launch import start_playback_after_open


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "search"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    desktop = sys.argv[3].lower() in ("1", "true", "desktop") if len(sys.argv) > 3 else True

    if TIDAL_CDP_ENABLED:
        try:
            from tidal_cdp import (
                cdp_playback_available,
                play_album_id,
                play_search_query,
                play_track_id,
            )

            if cdp_playback_available():
                ok, _msg = False, ""
                if mode == "track" and arg:
                    ok, _msg = play_track_id(arg)
                elif mode == "album" and arg:
                    ok, _msg = play_album_id(arg)
                elif mode == "search" and arg:
                    ok, _msg = play_search_query(arg)
                if ok:
                    return 0
        except Exception as e:
            print(f"[Tidal helper] CDP: {e}", flush=True)

    start_playback_after_open(desktop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
