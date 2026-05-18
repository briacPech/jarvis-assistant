# scripts/test_context_slimming.py

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from context_slimming import slim_messages


def main() -> int:
    history = []
    for i in range(8):
        history.append({"role": "user", "content": f"Question ancienne numero {i} " * 20})
        history.append(
            {
                "role": "assistant",
                "content": f"Reponse longue numero {i} " * 25,
            }
        )
    messages = [{"role": "system", "content": "Tu es Jarvis."}]
    messages.extend(history)
    pure = "Quelle est la capitale de l'Espagne ?"
    messages.append({"role": "user", "content": pure})

    slimmed, meta = slim_messages(messages, max_tokens=200, enabled=True)
    assert meta["slimmed"], "devrait condenser"

    last_users = [m for m in slimmed if m["role"] == "user"]
    assert last_users[-1]["content"] == pure, "dernier user doit rester intact"

    for m in slimmed:
        if m["role"] == "assistant":
            assert "Contexte condensé" not in (m.get("content") or ""), (
                "condensé ne doit pas être en assistant"
            )

    system = next(m for m in slimmed if m["role"] == "system")
    assert "Contexte condensé" in system["content"], (
        "condensé doit être dans system"
    )

    print("[OK] contexte condensé dans system uniquement")
    print(f"     tokens {meta['tokens_before']} -> {meta['tokens_after']}")
    print(f"     dernier user : {pure!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
