# context_slimming.py — réduction du prompt pour GPU limité (GTX 1650)



from __future__ import annotations



from typing import Any



try:

    from config import CONTEXT_SLIM_MAX_TOKENS, CONTEXT_SLIM_ENABLED

except ImportError:

    CONTEXT_SLIM_MAX_TOKENS = 1024

    CONTEXT_SLIM_ENABLED = True



_CHARS_PER_TOKEN = 4





def estimate_tokens(text: str) -> int:

    """Estimation légère (~4 caractères / token, français inclus)."""

    t = (text or "").strip()

    if not t:

        return 0

    return max(1, (len(t) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)





def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:

    total = 0

    for m in messages:

        role = m.get("role") or ""

        content = m.get("content") or ""

        total += estimate_tokens(str(content)) + 4

        if role:

            total += 2

    return total





def _truncate_to_tokens(text: str, max_tokens: int) -> str:

    if max_tokens <= 0:

        return ""

    cap = max_tokens * _CHARS_PER_TOKEN

    t = (text or "").strip()

    if len(t) <= cap:

        return t

    cut = t[:cap].rsplit(" ", 1)[0].strip() or t[:cap]

    return cut + "…"





def _compress_history_block(messages: list[dict[str, Any]]) -> str | None:

    """Texte condensé des tours retirés (à injecter dans system, pas dans user)."""

    parts: list[str] = []

    for m in messages:

        role = m.get("role")

        content = (m.get("content") or "").strip()

        if not content or role == "system":

            continue

        label = "Utilisateur" if role == "user" else "Assistant"

        snippet = content[:120] + ("…" if len(content) > 120 else "")

        parts.append(f"{label}: {snippet}")

    if not parts:

        return None

    body = "Contexte condensé (tours précédents) :\n" + "\n".join(parts[-6:])

    return body[:800]





def _append_condensed_to_system(

    messages: list[dict[str, Any]],

    condensed: str,

) -> None:

    """Ajoute l'historique condensé au prompt system (jamais au dernier user)."""

    block = (condensed or "").strip()

    if not block:

        return

    for m in messages:

        if (m.get("role") or "") == "system":

            prev = (m.get("content") or "").rstrip()

            m["content"] = f"{prev}\n\n{block}" if prev else block

            return

    messages.insert(0, {"role": "system", "content": block})





def slim_messages(

    messages: list[dict[str, Any]],

    *,

    max_tokens: int | None = None,

    enabled: bool | None = None,

) -> tuple[list[dict[str, Any]], dict[str, Any]]:

    """

    Tronque ou condense l'historique si le contexte dépasse max_tokens (défaut 1024).

    Conserve le system prompt et le dernier message utilisateur intacts (contenu brut).

    L'historique retiré est fusionné dans system, pas injecté comme faux tour user/assistant.

    """

    limit = max_tokens if max_tokens is not None else CONTEXT_SLIM_MAX_TOKENS

    use = CONTEXT_SLIM_ENABLED if enabled is None else enabled

    meta: dict[str, Any] = {

        "slimmed": False,

        "tokens_before": estimate_messages_tokens(messages),

        "tokens_after": 0,

        "max_tokens": limit,

    }

    if not use or not messages:

        meta["tokens_after"] = meta["tokens_before"]

        return messages, meta



    if meta["tokens_before"] <= limit:

        meta["tokens_after"] = meta["tokens_before"]

        return messages, meta



    meta["slimmed"] = True

    system_msgs = [m for m in messages if (m.get("role") or "") == "system"]

    rest = [m for m in messages if (m.get("role") or "") != "system"]

    if not rest:

        meta["tokens_after"] = meta["tokens_before"]

        return messages, meta



    last = rest[-1]

    history = rest[:-1]



    slimmed: list[dict[str, Any]] = list(system_msgs)

    budget = limit - estimate_messages_tokens(system_msgs + [last])



    kept: list[dict[str, Any]] = []

    for m in reversed(history):

        need = estimate_messages_tokens([m])

        if need <= budget:

            kept.insert(0, m)

            budget -= need

        else:

            break



    dropped = history[: len(history) - len(kept)]

    if dropped:

        condensed = _compress_history_block(dropped)

        if condensed:

            _append_condensed_to_system(slimmed, condensed)

            budget -= estimate_tokens(condensed)



    for m in kept:

        slimmed.append(m)

    slimmed.append(last)



    if estimate_messages_tokens(slimmed) > limit:

        non_system = [m for m in slimmed if m.get("role") != "system"]

        if len(non_system) > 1:

            last_msg = non_system[-1]

            system_part = [m for m in slimmed if m.get("role") == "system"]

            middle = non_system[:-1]

            condensed = _compress_history_block(middle)

            slimmed = system_part + [last_msg]

            if condensed:

                _append_condensed_to_system(slimmed, condensed)

            elif middle:

                _append_condensed_to_system(

                    slimmed,

                    "[Historique tronqué pour VRAM limitée]",

                )



    if estimate_messages_tokens(slimmed) > limit:

        for m in slimmed:

            if m.get("role") in ("user", "assistant") and m is not slimmed[-1]:

                m["content"] = _truncate_to_tokens(

                    str(m.get("content") or ""),

                    max(32, limit // max(1, len(slimmed))),

                )



    meta["tokens_after"] = estimate_messages_tokens(slimmed)

    meta["dropped_turns"] = len(dropped)

    return slimmed, meta


