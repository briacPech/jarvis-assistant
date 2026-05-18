# scripts/test_chat.py — test rapide POST /chat (serveur doit tourner)

from __future__ import annotations

import os
import sys

import requests

API = os.getenv("JARVIS_API_URL", "http://127.0.0.1:8000").rstrip("/")


def main() -> int:
    print(f"API: {API}\n")

    try:
        h = requests.get(f"{API}/health", timeout=5)
        print(f"GET /health -> {h.status_code} {h.json()}")
    except Exception as e:
        print(f"ERREUR: serveur inaccessible ({e})")
        print("Lance start_jarvis_api.bat d'abord.")
        return 1

    msg = "Quelle heure est-il ? Reponds en une phrase."
    r = requests.post(
        f"{API}/chat",
        params={
            "message": msg,
            "user_id": "test",
            "speak": "false",
            "fast": "false",
            "web": "false",
        },
        timeout=180,
    )
    print(f"POST /chat -> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:500])
        return 1
    data = r.json()
    print("route:", data.get("route"), "provider:", data.get("provider"))
    print("model:", data.get("model"))
    print("response:", (data.get("response") or "")[:400])
    if not (data.get("response") or "").strip():
        print("FAIL: reponse vide")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
