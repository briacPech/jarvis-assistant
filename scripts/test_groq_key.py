"""Test rapide cle Groq depuis .env (sans exposer la cle complete)."""
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
env_path = ROOT / ".env"


def read_key() -> str:
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if s.startswith("CLOUD_API_KEY="):
            return s.split("=", 1)[1].strip().strip('"').strip("'")
        if s.startswith("GROQ_API_KEY="):
            return s.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main():
    k = read_key()
    print("env_file", env_path)
    print("key_len", len(k))
    print("key_valid_shape", k.startswith("gsk_") and k.count("gsk_") == 1)
    if not k:
        print("ERREUR: pas de CLOUD_API_KEY dans .env")
        return
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": "Reponds: OK"}],
            "max_tokens": 8,
        },
        timeout=30,
    )
    print("groq_http", r.status_code)
    print(r.text[:200])


if __name__ == "__main__":
    main()
