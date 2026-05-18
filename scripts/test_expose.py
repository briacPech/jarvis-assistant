# scripts/test_expose.py — test route qualite + hydratation

from __future__ import annotations

import os
import requests

API = os.getenv("JARVIS_API_URL", "http://127.0.0.1:8000").rstrip("/")


def main() -> int:
    msg = "Fais un expose court sur la Revolution francaise (5 phrases max)."
    r = requests.post(
        f"{API}/chat",
        params={
            "message": msg,
            "speak": "false",
            "fast": "false",
            "web": "false",
            "cloud": "false",
        },
        timeout=300,
    )
    print("status", r.status_code)
    if r.status_code != 200:
        print(r.text[:400])
        return 1
    d = r.json()
    print("route", d.get("route"), "model", d.get("model"), "score", d.get("complexity_score"))
    text = (d.get("response") or "")[:600]
    print("response:", text)
    low = text.lower()
    if any(x in low for x in ("en tant que", "je ne peux pas", "événements passés")):
        print("WARN: refus detecte dans la reponse")
    return 0 if text.strip() else 1


if __name__ == "__main__":
    raise SystemExit(main())
