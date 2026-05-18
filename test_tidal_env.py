"""Test rapide configuration .env + TIDAL (ne pas committer)."""
import json
import sys

from config import (
    TIDAL_CLIENT_ID,
    TIDAL_CLIENT_SECRET,
    TIDAL_COUNTRY_CODE,
    TIDAL_ENABLED,
    TIDAL_REDIRECT_URI,
)
from tidal_actions import try_handle_tidal_command
from tidal_client import get_access_token, search_top_hit, status


def main() -> int:
    print("=== .env charge ===")
    print("TIDAL_ENABLED:", TIDAL_ENABLED)
    print("TIDAL_CLIENT_ID:", (TIDAL_CLIENT_ID[:6] + "...") if TIDAL_CLIENT_ID else "(vide)")
    print("TIDAL_CLIENT_SECRET:", "(ok)" if TIDAL_CLIENT_SECRET else "(vide)")
    print("TIDAL_COUNTRY_CODE:", TIDAL_COUNTRY_CODE)
    print("TIDAL_REDIRECT_URI:", TIDAL_REDIRECT_URI)
    print()

    st = status()
    print("=== tidal_client.status ===")
    print(json.dumps(st, indent=2))

    tok, err = get_access_token()
    print("token:", "OK" if tok else "ECHEC")
    if err:
        print("token_err:", err)
    if not tok:
        return 1

    hit, serr = search_top_hit("Daft Punk")
    print("\n=== recherche (Daft Punk) ===")
    if hit:
        print("title:", hit.get("title"))
        print("artist:", hit.get("artist"))
        print("url:", hit.get("url"))
    else:
        print("search_err:", serr)
        return 1

    print("\n=== commandes (sans API HTTP) ===")
    for msg in ("monte le volume", "joue Daft Punk sur tidal", "pause"):
        h, r, m = try_handle_tidal_command(msg)
        print(f"  {msg!r} -> handled={h} action={m.get('tidal_action')} reply={r!r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
