# scripts/preflight.py — vérifie l'environnement avant test Jarvis

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    errors: list[str] = []
    print("=== Jarvis preflight ===\n")

    try:
        import httpx  # noqa: F401
        print("[OK] httpx")
    except ImportError:
        errors.append("pip install httpx")
        print("[FAIL] httpx manquant")

    try:
        import pydantic  # noqa: F401
        print(f"[OK] pydantic {pydantic.__version__}")
    except ImportError:
        errors.append("pip install 'pydantic>=2.5'")
        print("[FAIL] pydantic manquant")

    try:
        import main_fast_WINDOWS_ULTRA  # noqa: F401
        print("[OK] main_fast_WINDOWS_ULTRA")
    except Exception as e:
        errors.append(f"import main_fast: {e}")
        print(f"[FAIL] main_fast_WINDOWS_ULTRA : {e}")

    try:
        from jarvis_bridge import edge_available, edge_error

        if edge_available():
            print("[OK] app/ (jarvis_bridge)")
        else:
            print(f"[WARN] app/ partiel : {edge_error()}")
    except Exception as e:
        print(f"[WARN] jarvis_bridge : {e}")

    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        import requests

        r = requests.get(f"{host.rstrip('/')}/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m.get("name") for m in r.json().get("models", [])]
            print(f"[OK] Ollama ({len(models)} modele(s))")
            need = os.getenv("JARVIS_MODEL", "qwen2.5:1.5b-instruct-q4_K_M")
            if need.split(":")[0] not in str(models):
                print(f"[WARN] Modele {need} peut-etre absent — ollama pull si besoin")
        else:
            errors.append(f"Ollama HTTP {r.status_code}")
            print(f"[FAIL] Ollama HTTP {r.status_code}")
    except Exception as e:
        errors.append(f"Ollama inaccessible : {e}")
        print(f"[FAIL] Ollama : {e}")
        print("       Lance : ollama serve")

    if errors:
        print("\n--- Actions ---")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nPret pour start_jarvis_api.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
