import os
import re
import threading
import wave
from pathlib import Path

from config import (
    TTS_ENGINE,
    TTS_LENGTH_SCALE,
    TTS_OUTPUT_DIR,
    TTS_PIPER_DIR,
    TTS_PIPER_VOICE,
    TTS_VOICE,
)

Path(TTS_OUTPUT_DIR).mkdir(exist_ok=True)
_tts_lock = threading.Lock()


def sanitize_for_tts(text: str) -> str:
    """
    Retire le Markdown et symboles que Piper lit à voix haute
    (ex. « astérisque » pour *).
    """
    t = (text or "").strip()
    if not t:
        return ""

    t = re.sub(r"<!--.*?-->", "", t, flags=re.DOTALL)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"\*(.+?)\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"_(.+?)_", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = t.replace("*", "").replace("_", " ")
    t = re.sub(r"^\s*[-•*]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^---+\s*$", "", t, flags=re.MULTILINE)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _split_sentences(text: str, max_chars: int) -> list[str]:
    text = sanitize_for_tts(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    buf = ""
    for piece in text.replace("\n", " ").split(". "):
        piece = piece.strip()
        if not piece:
            continue
        if not piece.endswith("."):
            piece += "."
        candidate = f"{buf} {piece}".strip() if buf else piece
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                parts.append(buf)
            if len(piece) <= max_chars:
                buf = piece
            else:
                while len(piece) > max_chars:
                    parts.append(piece[:max_chars].rstrip())
                    piece = piece[max_chars:].lstrip()
                buf = piece
    if buf:
        parts.append(buf)
    return parts or [text[:max_chars]]


class _PiperBackend:
    def __init__(self, voice_id: str, models_dir: str, length_scale: float):
        self.voice_id = voice_id
        self.models_dir = Path(models_dir)
        self.length_scale = length_scale
        self._voice = None
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def _model_paths(self) -> tuple[Path, Path]:
        base = self.models_dir / self.voice_id
        return base.with_suffix(".onnx"), Path(str(base) + ".onnx.json")

    def _ensure_model(self):
        model_path, config_path = self._model_paths()
        if model_path.is_file() and config_path.is_file():
            return model_path, config_path
        try:
            from piper.download_voices import download_voice

            print(f"[TTS] Telechargement voix Piper : {self.voice_id} (~60 Mo, une fois)...")
            download_voice(self.voice_id, self.models_dir)
        except Exception as e:
            raise RuntimeError(f"Impossible de telecharger la voix Piper '{self.voice_id}': {e}") from e
        if not model_path.is_file():
            raise FileNotFoundError(f"Modele introuvable : {model_path}")
        return model_path, config_path

    def _get_voice(self):
        if self._voice is not None:
            return self._voice
        from piper import PiperVoice
        from piper.config import SynthesisConfig

        model_path, config_path = self._ensure_model()
        self._voice = PiperVoice.load(str(model_path), config_path=str(config_path))
        self._syn_config = SynthesisConfig(length_scale=self.length_scale)
        return self._voice

    def synthesize(self, text: str, output_file: str) -> bool:
        voice = self._get_voice()
        with wave.open(output_file, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=self._syn_config)
        return os.path.exists(output_file) and os.path.getsize(output_file) > 0


class _SapiBackend:
    def __init__(self, voice_name: str, rate: int = 175):
        self.voice_name = voice_name
        self.rate = rate
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", 1.0)
        wanted = (self.voice_name or "").lower()
        if wanted:
            for v in engine.getProperty("voices"):
                vid = (getattr(v, "id", "") or "").lower()
                vname = (getattr(v, "name", "") or "").lower()
                if wanted in vid or wanted in vname:
                    engine.setProperty("voice", v.id)
                    break
        self._engine = engine
        return engine

    def synthesize(self, text: str, output_file: str) -> bool:
        engine = self._get_engine()
        try:
            try:
                engine.stop()
            except Exception:
                pass
            engine.save_to_file(text, output_file)
            engine.runAndWait()
            ok = os.path.exists(output_file) and os.path.getsize(output_file) > 0
        finally:
            if os.name == "nt":
                self._engine = None
        return ok


class TextToSpeech:
    def __init__(
        self,
        voice: str = None,
        output_dir: str = TTS_OUTPUT_DIR,
        engine: str = TTS_ENGINE,
    ):
        self.output_dir = output_dir
        self.engine = (engine or "piper").lower()
        Path(self.output_dir).mkdir(exist_ok=True)

        if self.engine == "sapi":
            self.voice = voice or TTS_VOICE
            self._backend = _SapiBackend(self.voice)
        else:
            self.voice = voice or TTS_PIPER_VOICE
            self._backend = _PiperBackend(
                self.voice,
                TTS_PIPER_DIR,
                TTS_LENGTH_SCALE,
            )

    def text_to_speech(self, text: str, output_file: str = None) -> str:
        text = sanitize_for_tts(text)
        if not text:
            return None

        if not output_file:
            file_count = len(os.listdir(self.output_dir))
            output_file = f"output_{file_count:04d}.wav"

        output_file = os.path.join(self.output_dir, os.path.basename(output_file))

        with _tts_lock:
            try:
                if self._backend.synthesize(text, output_file):
                    return output_file
                return None
            except Exception as e:
                print(f"[TTS] Erreur ({self.engine}) : {e}")
                return None
