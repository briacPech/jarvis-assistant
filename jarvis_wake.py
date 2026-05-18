"""
Agent vocal Jarvis — sans compte, 100% local (openWakeWord).

Usage :
  Terminal 1 : python main_fast_WINDOWS_ULTRA.py
  Terminal 2 : python jarvis_wake.py

Dis « hey jarvis » ou « salut jarvis » (meme prononciation),
puis ta question juste apres le bip.
"""

import console_utf8  # noqa: F401  # UTF-8 console Windows

from __future__ import annotations

import os
import sys
import time
import tempfile
import threading

import numpy as np
import requests

from config import (
    API_TIMEOUT,
    JARVIS_API_URL,
    WAKE_MODEL,
    OLLAMA_HOST,
    WAKE_MAX_TOKENS,
    WAKE_NUM_CTX,
    WAKE_LISTEN_SECONDS,
    WAKE_COOLDOWN_SEC,
)

SAMPLE_RATE = 16000
CHUNK = 1280
API = JARVIS_API_URL.rstrip("/")
_session = requests.Session()
_busy = threading.Lock()
_wake_muted_until = 0.0


def _log(msg: str):
    print(f"[Wake] {msg}", flush=True)


def _warmup():
    try:
        _session.get(f"{API}/health", timeout=3)
    except Exception:
        pass
    try:
        from local_model_policy import local_ollama_model, ollama_keep_alive

        name = local_ollama_model()
        _session.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": name,
                "prompt": " ",
                "stream": False,
                "keep_alive": ollama_keep_alive(),
                "options": {"num_predict": 1, "num_ctx": 512},
            },
            timeout=60,
        )
        _log(f"Ollama prechauffe : {name} (wake via API /chat fast)")
    except Exception as e:
        _log(f"Prechauffage : {e}")


def _beep():
    try:
        import winsound
        winsound.Beep(880, 100)
    except Exception:
        pass


def _play_wav(path: str, blocking: bool = True):
    try:
        import winsound
        if blocking and os.name == "nt":
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_SYNC)
        else:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
    except Exception:
        if os.name == "nt":
            os.startfile(path)


def _wait_audio_job(job_id: str, timeout_sec: float = 120) -> list:
    if not job_id:
        return []
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = _session.get(f"{API}/tts/job/{job_id}", timeout=5)
            if r.status_code == 200:
                data = r.json()
                paths = data.get("audio_paths") or []
                if paths:
                    return paths
                path = data.get("audio_path")
                if path:
                    return [path]
                url = data.get("audio_url")
                if url:
                    return [url]
            elif r.status_code in (404, 500):
                return []
        except Exception:
            pass
        time.sleep(0.25)
    return []


def _play_api_audio(data: dict | None):
    if not data:
        return
    paths = data.get("audio_paths") or []
    if not paths and data.get("audio_path"):
        paths = [data["audio_path"]]
    job_id = data.get("audio_job_id")
    if not paths and job_id:
        paths = _wait_audio_job(job_id)
    if not paths:
        _log("Pas d audio (TTS en cours ou echoue)")
        return
    for i, item in enumerate(paths):
        url = f"{API}{item}" if item.startswith("/") else item
        try:
            r = _session.get(url, timeout=30)
            if r.status_code != 200:
                continue
            tmp = os.path.join(tempfile.gettempdir(), f"jarvis_wake_{i}.wav")
            with open(tmp, "wb") as f:
                f.write(r.content)
            _play_wav(tmp, blocking=True)
        except Exception as e:
            _log(f"Audio : {e}")


def _record_seconds(seconds: float) -> bytes:
    import sounddevice as sd
    frames = int(seconds * SAMPLE_RATE)
    rec = sd.rec(frames, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return rec.tobytes()


def _listen_command_vad(max_sec: float = 9.0, silence_sec: float = 1.3) -> str | None:
    """Ecoute jusqu'au silence (evite 6 s fixes qui chevauchent la reponse)."""
    try:
        import speech_recognition as sr
        import sounddevice as sd
    except ImportError:
        _log("pip install SpeechRecognition sounddevice")
        return None

    _log("Parle...")
    block = CHUNK
    blocks: list[bytes] = []
    silent_blocks = 0
    need_silent = max(1, int(silence_sec * SAMPLE_RATE / block))
    max_blocks = max(need_silent + 1, int(max_sec * SAMPLE_RATE / block))
    heard = False

    def _level(chunk: bytes) -> float:
        a = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if a.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(a * a)))

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=block,
        ) as stream:
            for _ in range(max_blocks):
                chunk, _ = stream.read(block)
                blocks.append(bytes(chunk))
                lv = _level(chunk)
                if lv > 350:
                    heard = True
                    silent_blocks = 0
                elif heard:
                    silent_blocks += 1
                    if silent_blocks >= need_silent:
                        break
        if not heard:
            return None
        raw = b"".join(blocks)
        audio = sr.AudioData(raw, SAMPLE_RATE, 2)
        r = sr.Recognizer()
        return r.recognize_google(audio, language="fr-FR").strip()
    except sr.UnknownValueError:
        _log("Pas compris")
        return None
    except Exception as e:
        _log(f"STT micro : {e} — essai court")
        try:
            raw = _record_seconds(min(WAKE_LISTEN_SECONDS, max_sec))
            audio = sr.AudioData(raw, SAMPLE_RATE, 2)
            r = sr.Recognizer()
            return r.recognize_google(audio, language="fr-FR").strip()
        except sr.UnknownValueError:
            _log("Pas compris")
            return None
        except Exception as e2:
            _log(f"STT : {e2}")
            return None


def _strip_wake_prefix(text: str) -> str:
    t = text.strip()
    for prefix in (
        "salut jarvis",
        "hey jarvis",
        "ok jarvis",
        "dis jarvis",
        "jarvis",
    ):
        low = t.lower()
        if low.startswith(prefix):
            t = t[len(prefix):].strip(" ,.?!")
            break
    return t.strip()


def _wake_use_web(message: str) -> bool:
    try:
        from config import WEB_SEARCH_WAKE, WEB_SEARCH_ENABLED

        if not WEB_SEARCH_ENABLED or not WEB_SEARCH_WAKE:
            return False
        from web_search import needs_web_search, wants_forced_web

        return wants_forced_web(message) or needs_web_search(message)
    except ImportError:
        return False


def _ask_jarvis(message: str) -> dict | None:
    t0 = time.perf_counter()
    params = {
        "message": message,
        "user_id": "wake",
        "model": WAKE_MODEL,
        "max_tokens": WAKE_MAX_TOKENS,
        "num_ctx": WAKE_NUM_CTX,
        "speak": "true",
        "fast": "true",
    }
    if _wake_use_web(message):
        params["web"] = "true"
    try:
        r = _session.post(
            f"{API}/chat",
            params=params,
            timeout=max(45, API_TIMEOUT + 15),
        )
        data = r.json()
        _log(f"Reponse en {time.perf_counter() - t0:.1f}s")
        return data
    except Exception as e:
        _log(f"API : {e}")
        return None


def _handle_wake():
    global _wake_muted_until
    if not _busy.acquire(blocking=False):
        return
    try:
        _wake_muted_until = time.time() + 90
        _beep()
        time.sleep(0.25)
        text = _listen_command_vad()
        if not text:
            _wake_muted_until = time.time() + 1.5
            return
        text = _strip_wake_prefix(text)
        if not text:
            _wake_muted_until = time.time() + 1.5
            return
        _log(f"Toi : {text}")
        _wake_muted_until = time.time() + 120
        data = _ask_jarvis(text)
        if not data:
            _wake_muted_until = time.time() + 2
            return
        reply = (data.get("response") or "").strip()
        if reply:
            short = reply[:100] + ("..." if len(reply) > 100 else "")
            _log(f"Jarvis : {short}")
        _play_api_audio(data)
        _wake_muted_until = time.time() + 2
    finally:
        _busy.release()


def _stream_openwakeword():
    import sounddevice as sd
    from openwakeword.model import Model

    oww = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    _log("Ecoute active — dis « hey jarvis » ou « salut jarvis » puis ta question")
    _log("(100% local, aucun compte requis)")

    cooldown = 0.0

    def callback(indata, frames, time_info, status):
        nonlocal cooldown
        if status:
            return
        audio = np.frombuffer(bytes(indata), dtype=np.int16)
        if audio.size < CHUNK:
            return
        preds = oww.predict(audio)
        if time.time() < _wake_muted_until:
            return
        if any(s > 0.5 for s in preds.values()) and time.time() >= cooldown:
            cooldown = time.time() + WAKE_COOLDOWN_SEC + 12
            threading.Thread(target=_handle_wake, daemon=True).start()

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=CHUNK,
        callback=callback,
    ):
        while True:
            time.sleep(0.1)


def main():
    _log("Agent vocal Jarvis (openWakeWord, sans compte)")
    _log(f"API {API} | modele wake {WAKE_MODEL}")

    try:
        if _session.get(f"{API}/health", timeout=5).status_code != 200:
            raise RuntimeError()
    except Exception:
        _log("Lance d'abord : python main_fast_WINDOWS_ULTRA.py")
        sys.exit(1)

    threading.Thread(target=_warmup, daemon=True).start()

    try:
        _stream_openwakeword()
    except Exception as e:
        _log(f"Erreur : {e}")
        _log("Installe : pip install -r requirements-wake.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()
