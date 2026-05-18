# scripts/test_routeur_jarvis.py — tests routeur sklearn + gate API

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_classifieur() -> None:
    from routeur_jarvis import aiguiller_requete, entrainer_routeur

    entrainer_routeur()
    cas = [
        ("Active l'éclairage de la chambre", "commande"),
        ("Mets le volume à 30 pour cent", "commande"),
        ("Explique la photosynthèse", "ia"),
        ("Raconte l'histoire de la Bretagne", "ia"),
    ]
    for phrase, attendu in cas:
        got = aiguiller_requete(phrase)
        ok = got == attendu
        mark = "OK" if ok else "FAIL"
        print(f"  [{mark}] {phrase!r} -> {got} (attendu {attendu})")
        if not ok:
            raise AssertionError(f"{phrase!r}: {got} != {attendu}")


def test_commande_locale() -> None:
    from commande_locale import try_handle_local_command
    from tidal_actions import try_handle_tidal_command

    handled, reply, meta = try_handle_local_command("Augmente le volume")
    if not handled or meta.get("local_action") != "volume_up":
        raise AssertionError(f"volume: {handled} {meta} {reply}")
    print(f"  [OK] volume_up : {reply}")

    handled, reply, meta = try_handle_local_command("Mets en pause")
    if not handled or meta.get("local_action") != "pause":
        raise AssertionError(f"pause: {handled} {meta}")
    print(f"  [OK] pause : {reply}")

    handled, reply, meta = try_handle_tidal_command("plus fort")
    if not handled or meta.get("tidal_action") != "volume_up":
        raise AssertionError(f"plus fort: {handled} {meta} {reply}")
    print(f"  [OK] tidal plus fort : {reply}")


def test_gate_sans_llm() -> None:
    os.environ.setdefault("JARVIS_SKLEARN_ROUTER", "true")
    import importlib

    import config

    importlib.reload(config)
    import main_fast_WINDOWS_ULTRA as j

    importlib.reload(j)

    out_skip = j._try_local_command_gate(
        "Monte le volume",
        "test_routeur",
        fast_mode=True,
        model=None,
        max_tokens=None,
        num_ctx=None,
    )
    if out_skip is not None:
        raise AssertionError("sans « tidal », la gate ne doit pas intercepter")
    print("  [OK] sans tidal -> pas de gate")

    phrase = "Tidal, monte le volume"
    out = j._try_local_command_gate(
        phrase, "test_routeur", fast_mode=True, model=None, max_tokens=None, num_ctx=None
    )
    if out is None:
        raise AssertionError("gate aurait du intercepter Tidal monte le volume")
    reply, _model, _p, _c, meta = out
    assert meta.get("intent_gate") == "commande"
    assert meta.get("tidal_keyword")
    assert meta.get("tidal_handled") or "volume" in reply.lower()
    print(f"  [OK] gate tidal volume : {reply[:72]}...")


def test_api_si_disponible() -> None:
    try:
        import requests
    except ImportError:
        print("  [SKIP] requests manquant")
        return

    base = os.getenv("JARVIS_API_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        r = requests.get(f"{base}/health", timeout=2)
        if r.status_code != 200:
            print(f"  [SKIP] API hors ligne ({r.status_code})")
            return
    except Exception as e:
        print(f"  [SKIP] API non joignable : {e}")
        return

    tests = [
        ("Mets le volume à 40 pour cent", "commande"),
        ("Explique brièvement la gravité", "ia"),
    ]
    for msg, kind in tests:
        r = requests.post(
            f"{base}/chat",
            params={
                "message": msg,
                "user_id": "test_routeur",
                "fast": "true",
                "speak": "false",
            },
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()
        gate = data.get("intent_gate")
        tidal = data.get("tidal_handled")
        snippet = (data.get("output") or data.get("response") or "")[:60]
        if kind == "commande":
            ok = (
                gate == "commande"
                or data.get("sklearn_router")
                or tidal
                or "volume" in snippet.lower()
            )
            mark = "OK" if ok else "FAIL"
            print(f"  [{mark}] API commande : gate={gate} tidal={tidal} -> {snippet!r}")
            if not ok:
                raise AssertionError(data)
        else:
            ok = gate != "commande" or not data.get("sklearn_router")
            mark = "OK" if ok else "WARN"
            print(f"  [{mark}] API ia : gate={gate} -> {snippet!r}")


def main() -> int:
    print("=== test_routeur_jarvis ===\n")
    print("1. Classifieur")
    test_classifieur()
    print("\n2. commande_locale (media_control)")
    test_commande_locale()
    print("\n3. Gate _try_local_command_gate (sans HTTP)")
    test_gate_sans_llm()
    print("\n4. API live (si serveur sur :8000)")
    test_api_si_disponible()
    print("\n=== Tous les tests obligatoires OK ===")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"\nECHEC : {e}")
        raise SystemExit(1) from e
