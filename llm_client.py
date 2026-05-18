# llm_client.py — Groq (OpenAI-compatible) + quota journalier



from __future__ import annotations



import os

import sqlite3

from datetime import date

from pathlib import Path

from typing import Any



import requests



_ROOT = Path(__file__).resolve().parent

_ENV_PATH = _ROOT / ".env"

_DB_PATH = "jarvis_memory.db"

_CLOUD_DB_INIT = False





def _parse_env_file() -> dict[str, str]:

    """Lit h:\\assistant\\.env directement (evite cache config / mauvais cwd)."""

    out: dict[str, str] = {}

    if not _ENV_PATH.is_file():

        return out

    for line in _ENV_PATH.read_text(encoding="utf-8-sig").splitlines():

        s = line.strip()

        if not s or s.startswith("#") or "=" not in s:

            continue

        key, _, val = s.partition("=")

        out[key.strip()] = val.strip().strip('"').strip("'")

    return out





def _sanitize_api_key(raw: str) -> str:

    k = (raw or "").strip()

    if k.count("gsk_") > 1:

        second = k.find("gsk_", 4)

        if second > 0:

            k = k[:second].strip()

    return k





def _get_cloud_settings() -> dict[str, Any]:

    env = _parse_env_file()

    raw_key = env.get("CLOUD_API_KEY", "") or env.get("GROQ_API_KEY", "")

    key = _sanitize_api_key(raw_key)

    src = "CLOUD_API_KEY" if env.get("CLOUD_API_KEY", "").strip() else ""

    if not src and env.get("GROQ_API_KEY", "").strip():

        src = "GROQ_API_KEY"

    return {

        "enabled": env.get("CLOUD_ENABLED", "false").lower() == "true",

        "api_key": key,

        "env_var_used": src or None,

        "base_url": env.get(

            "CLOUD_BASE_URL", "https://api.groq.com/openai/v1"

        ).rstrip("/"),

        "model": env.get("CLOUD_MODEL", "llama-3.1-8b-instant"),

        "model_heavy": env.get(

            "CLOUD_MODEL_HEAVY", "deepseek-r1-distill-llama-70b"

        ),

        "max_tokens": int(env.get("CLOUD_MAX_TOKENS", "768")),

        "daily_limit": int(env.get("CLOUD_DAILY_LIMIT", "30")),

        "env_path": str(_ENV_PATH),

    }





def _db_path() -> str:

    try:

        import config as cfg



        return cfg.DB_PATH

    except ImportError:

        return _DB_PATH





def _init_cloud_db() -> None:

    global _CLOUD_DB_INIT

    if _CLOUD_DB_INIT:

        return

    conn = sqlite3.connect(_db_path())

    conn.execute(

        """

        CREATE TABLE IF NOT EXISTS cloud_usage (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            day TEXT NOT NULL,

            model TEXT NOT NULL,

            route TEXT,

            tokens_in INTEGER DEFAULT 0,

            tokens_out INTEGER DEFAULT 0,

            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP

        )

        """

    )

    conn.commit()

    conn.close()

    _CLOUD_DB_INIT = True





def cloud_available() -> bool:

    s = _get_cloud_settings()

    return s["enabled"] and bool(s["api_key"])





def cloud_usage_today() -> int:

    _init_cloud_db()

    today = date.today().isoformat()

    conn = sqlite3.connect(_db_path())

    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM cloud_usage WHERE day = ?", (today,))

    n = cur.fetchone()[0]

    conn.close()

    return n





def cloud_quota_ok() -> bool:

    if not cloud_available():

        return False

    return cloud_usage_today() < _get_cloud_settings()["daily_limit"]





def log_cloud_call(

    model: str,

    route: str,

    tokens_in: int = 0,

    tokens_out: int = 0,

) -> None:

    _init_cloud_db()

    conn = sqlite3.connect(_db_path())

    conn.execute(

        """

        INSERT INTO cloud_usage (day, model, route, tokens_in, tokens_out)

        VALUES (?, ?, ?, ?, ?)

        """,

        (date.today().isoformat(), model, route, tokens_in, tokens_out),

    )

    conn.commit()

    conn.close()





def is_ollama_failure(answer: str) -> bool:

    a = (answer or "").strip()

    if not a:

        return True

    if a.startswith("ERREUR"):

        return True

    if a.lower().startswith("erreur ollama"):

        return True

    if "Reponse vide" in a or "réponse vide" in a.lower():

        return True

    return False





def test_groq_connection() -> dict[str, Any]:

    """Test live Groq avec la cle lue depuis .env (diagnostic)."""

    s = _get_cloud_settings()

    key = s["api_key"]

    out: dict[str, Any] = {

        "env_path": s["env_path"],

        "env_var_used": s["env_var_used"],

        "key_length": len(key),

        "key_looks_valid": key.startswith("gsk_") and key.count("gsk_") == 1,

        "enabled": s["enabled"],

    }

    if not s["enabled"]:

        out.update({"ok": False, "error": "CLOUD_ENABLED=false"})

        return out

    if not key:

        out.update({"ok": False, "error": "CLOUD_API_KEY vide dans .env"})

        return out

    try:

        r = requests.post(

            f"{s['base_url']}/chat/completions",

            headers={

                "Authorization": f"Bearer {key}",

                "Content-Type": "application/json",

            },

            json={

                "model": s["model"],

                "messages": [{"role": "user", "content": "Reponds: OK"}],

                "max_tokens": 8,

            },

            timeout=30,

        )

        out["http_status"] = r.status_code

        out["ok"] = r.status_code == 200

        if r.status_code != 200:

            out["error"] = r.text[:300]

        return out

    except Exception as e:

        return {**out, "ok": False, "error": str(e)}





def ask_cloud(

    messages: list[dict[str, str]],

    *,

    heavy: bool = False,

    max_tokens: int | None = None,

    route_label: str = "cloud",

) -> tuple[str, str]:

    """Appel Groq. Cle toujours lue depuis le fichier .env du projet."""

    s = _get_cloud_settings()

    if not s["enabled"]:

        return "ERREUR : Cloud desactive (CLOUD_ENABLED=false dans .env).", ""

    api_key = s["api_key"]

    if not api_key:

        return "ERREUR : CLOUD_API_KEY manquant dans .env.", ""



    if not cloud_quota_ok():

        return (

            f"ERREUR : Quota cloud journalier atteint ({s['daily_limit']} appels).",

            "",

        )



    model = s["model_heavy"] if heavy else s["model"]

    limit = max_tokens if max_tokens is not None else s["max_tokens"]

    url = f"{s['base_url']}/chat/completions"



    try:

        r = requests.post(

            url,

            headers={

                "Authorization": f"Bearer {api_key}",

                "Content-Type": "application/json",

            },

            json={

                "model": model,

                "messages": messages,

                "max_tokens": limit,

                "temperature": 0.3,

            },

            timeout=90,

        )

        if r.status_code != 200:

            hint = ""

            if r.status_code == 401:

                hint = (

                    f" Cle lue depuis {_ENV_PATH} (len={len(api_key)}). "

                    "Test: GET /cloud/test — ou regenere la cle sur console.groq.com."

                )

            return f"ERREUR : Groq HTTP {r.status_code}: {r.text[:200]}{hint}", model



        data = r.json()

        choice = (data.get("choices") or [{}])[0]

        content = (choice.get("message") or {}).get("content", "")

        usage = data.get("usage") or {}

        log_cloud_call(

            model,

            route_label,

            int(usage.get("prompt_tokens") or 0),

            int(usage.get("completion_tokens") or 0),

        )

        text = (content or "").strip()

        if not text:

            return "ERREUR : Groq a renvoye une reponse vide.", model

        return text, model

    except requests.exceptions.Timeout:

        return "ERREUR : Groq timeout.", model

    except Exception as e:

        return f"ERREUR : Groq {e}", model





def cloud_status() -> dict[str, Any]:

    s = _get_cloud_settings()

    key = s["api_key"]

    return {

        "enabled": s["enabled"],

        "configured": bool(key),

        "available": cloud_available(),

        "env_path": s["env_path"],

        "env_var_used": s["env_var_used"],

        "key_length": len(key),

        "key_looks_valid": key.startswith("gsk_") and key.count("gsk_") == 1,

        "model": s["model"],

        "model_heavy": s["model_heavy"],

        "daily_limit": s["daily_limit"],

        "used_today": cloud_usage_today(),

        "quota_ok": cloud_quota_ok(),

    }


