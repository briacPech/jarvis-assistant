import os
import subprocess
import tempfile
import time

try:
    from config import STT_ENGINE, STT_WHISPER_MODEL, STT_WHISPER_FALLBACK
except ImportError:
    STT_ENGINE = os.getenv("JARVIS_STT_ENGINE", "google")
    STT_WHISPER_MODEL = os.getenv("JARVIS_WHISPER_MODEL", "base")
    STT_WHISPER_FALLBACK = os.getenv("JARVIS_STT_WHISPER_FALLBACK", "true").lower() == "true"


def stt_engine_label() -> str:
    """Moteur STT prioritaire (affichage /status)."""
    eng = (STT_ENGINE or "google").lower()
    if eng in ("google", "whisper"):
        return eng
    return "google+whisper" if STT_WHISPER_FALLBACK else "google"


def stt_health_info() -> dict:
    """Diagnostic STT pour /status."""
    ffmpeg = _ffmpeg_exe()
    info = {
        "engine": stt_engine_label(),
        "configured": STT_ENGINE,
        "whisper_fallback": STT_WHISPER_FALLBACK,
        "ffmpeg": ffmpeg,
        "ffmpeg_ok": bool(ffmpeg and (ffmpeg == "ffmpeg" or os.path.isfile(ffmpeg))),
    }
    try:
        import speech_recognition  # noqa: F401

        info["google_stt"] = True
    except ImportError:
        info["google_stt"] = False
    try:
        from stt_whisper import whisper_available

        info["whisper_available"] = whisper_available()
        info["whisper_model"] = STT_WHISPER_MODEL
    except ImportError:
        info["whisper_available"] = False
    info["ok"] = info["ffmpeg_ok"] and (
        info.get("whisper_available") or info.get("google_stt")
    )
    return info


def _ffmpeg_exe():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    return "ffmpeg"


def _convert_to_wav(src_path: str, wav_path: str):
    ffmpeg = _ffmpeg_exe()
    cmd = [
        ffmpeg, "-y", "-i", src_path,
        "-ar", "16000", "-ac", "1", "-vn", wav_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err[-400:] if err else f"ffmpeg code {proc.returncode}")
    if not os.path.isfile(wav_path) or os.path.getsize(wav_path) < 100:
        raise RuntimeError("fichier wav vide apres conversion")


def _transcribe_google(wav_path: str) -> tuple[str | None, str | None]:
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio = recognizer.record(source)
    text = recognizer.recognize_google(audio, language="fr-FR")
    return (text.strip() if text else None), None


def _transcribe_whisper(wav_path: str) -> tuple[str | None, str | None]:
    from stt_whisper import transcribe_wav_path

    return transcribe_wav_path(wav_path, model_name=STT_WHISPER_MODEL)


def _google_errors(e: Exception) -> tuple[str | None, str | None]:
    import speech_recognition as sr

    if isinstance(e, sr.UnknownValueError):
        return None, "pas compris — parle plus fort ou plus pres"
    if isinstance(e, sr.RequestError):
        return None, "Google STT indisponible (Internet requis)"
    return None, str(e)


def _try_google(wav_path: str) -> tuple[str | None, str | None, bool]:
    """Retourne (texte, erreur, ok_reseau). ok_reseau=False => essayer whisper."""
    try:
        return *_transcribe_google(wav_path), True
    except Exception as e:
        import speech_recognition as sr

        text, err = _google_errors(e)
        network_fail = isinstance(e, sr.RequestError)
        return text, err, not network_fail


def _try_whisper(wav_path: str) -> tuple[str | None, str | None]:
    if not STT_WHISPER_FALLBACK:
        return None, None
    try:
        from stt_whisper import whisper_available

        if not whisper_available():
            return None, None
    except ImportError:
        return None, None
    t0 = time.perf_counter()
    text, err = _transcribe_whisper(wav_path)
    if text:
        print(f"[STT] Whisper fallback OK en {time.perf_counter() - t0:.1f}s")
    return text, err


def transcribe_audio_bytes(data: bytes, filename: str = "voice.webm"):
    """Transcrit webm/wav du micro. Retourne (texte, erreur)."""
    if not data or len(data) < 100:
        return None, "audio vide ou trop court"

    ext = os.path.splitext(filename or "")[1].lower() or ".webm"
    tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    wav_path = tmp_in.name + ".wav"
    try:
        tmp_in.write(data)
        tmp_in.close()

        if ext == ".wav":
            wav_path = tmp_in.name
        else:
            try:
                _convert_to_wav(tmp_in.name, wav_path)
            except FileNotFoundError:
                return None, "ffmpeg manquant : pip install imageio-ffmpeg"
            except Exception as e:
                return None, f"conversion webm : {e}"

        engine = (STT_ENGINE or "google").lower()
        t0 = time.perf_counter()

        if engine == "whisper":
            text, err = _transcribe_whisper(wav_path)
            print(f"[STT] whisper {time.perf_counter() - t0:.1f}s")
            return text, err

        # google ou auto : Google d'abord (quelques secondes)
        text, err, _ = _try_google(wav_path)
        if text:
            print(f"[STT] google {time.perf_counter() - t0:.1f}s")
            return text, None
        if err and "pas compris" in (err or ""):
            return None, err

        if engine == "google":
            return text, err

        # auto : whisper seulement si Google a echoue (reseau / vide)
        text_w, err_w = _try_whisper(wav_path)
        if text_w:
            return text_w, None
        return text, err or err_w
    finally:
        for p in {tmp_in.name, tmp_in.name + ".wav"}:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
