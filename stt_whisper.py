# stt_whisper.py — transcription locale (faster-whisper)

from __future__ import annotations

import os
import threading
from typing import Optional

_model = None
_model_lock = threading.Lock()
_model_name_loaded: Optional[str] = None


def whisper_available() -> bool:
    try:
        from faster_whisper import WhisperModel  # noqa: F401

        return True
    except ImportError:
        return False


def _get_model(model_name: str):
    global _model, _model_name_loaded
    with _model_lock:
        if _model is not None and _model_name_loaded == model_name:
            return _model
        from faster_whisper import WhisperModel

        device = os.getenv("JARVIS_WHISPER_DEVICE", "cpu")
        compute = os.getenv("JARVIS_WHISPER_COMPUTE", "int8")
        _model = WhisperModel(model_name, device=device, compute_type=compute)
        _model_name_loaded = model_name
        print(f"[STT] Whisper charge : {model_name} ({device}/{compute})")
        return _model


def transcribe_wav_path(wav_path: str, model_name: str = "small") -> tuple[Optional[str], Optional[str]]:
    """Transcrit un fichier wav 16 kHz mono."""
    if not os.path.isfile(wav_path) or os.path.getsize(wav_path) < 100:
        return None, "fichier wav vide"
    if not whisper_available():
        return None, "faster-whisper manquant (pip install faster-whisper)"

    try:
        model = _get_model(model_name)
        lang = os.getenv("JARVIS_WHISPER_LANG", "fr")
        segments, _info = model.transcribe(
            wav_path,
            language=lang if lang != "auto" else None,
            beam_size=1,
            best_of=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        parts = [s.text.strip() for s in segments if s.text.strip()]
        text = " ".join(parts).strip()
        if not text:
            return None, "pas compris — parle plus fort ou plus pres"
        return text, None
    except Exception as e:
        return None, str(e)
