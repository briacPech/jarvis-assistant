# config.py
# ========================================
# Configuration Jarvis
# ========================================

import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    # override=True : le .env prime sur les variables des .bat (souvent obsolete)
    load_dotenv(os.path.join(_BASE_DIR, ".env"), override=True)
except ImportError:
    pass

# ========================================
# Configuration Modèle IA
# ========================================

# Chat : 1.5B (legacy / cloud) | seul local VRAM : 3B | wake : cloud ou 3B
MODEL = os.getenv("JARVIS_MODEL", "qwen2.5:1.5b-instruct-q4_K_M")
FAST_MODEL = os.getenv("JARVIS_FAST_MODEL", "qwen2.5:1.5b-instruct-q4_K_M")
QUALITY_MODEL = os.getenv("JARVIS_QUALITY_MODEL", "qwen2.5:3b-instruct-q4_K_M")
WAKE_MODEL = os.getenv("JARVIS_WAKE_MODEL", "qwen2.5:0.5b")
# Un seul modele Ollama en VRAM (3B) — fast/wake/1.5B -> cloud si CLOUD_ENABLED
SINGLE_LOCAL_MODEL = os.getenv("JARVIS_SINGLE_LOCAL_MODEL", "true").lower() == "true"
LOCAL_OLLAMA_MODEL = os.getenv("JARVIS_LOCAL_MODEL", "").strip() or QUALITY_MODEL
QUALITY_MIN_CHARS = int(os.getenv("JARVIS_QUALITY_MIN_CHARS", "200"))
# Modeles lourds ignores si le client envoie un nom explicite (ex. gemma 4b)
ALLOW_HEAVY_MODELS = os.getenv("JARVIS_ALLOW_HEAVY", "false").lower() == "true"
_BLOCKED = os.getenv(
    "JARVIS_BLOCKED_MODELS",
    "gemma,mistral,qwen3.5:9b,qwen3.5:27b,llama3.1:70b,deepseek",
)
BLOCKED_MODEL_SUBSTRINGS = tuple(
    s.strip().lower() for s in _BLOCKED.split(",") if s.strip()
)
API_TIMEOUT = int(os.getenv("JARVIS_TIMEOUT", "90"))
OLLAMA_STREAM_TIMEOUT = int(
    os.getenv("JARVIS_STREAM_TIMEOUT", str(max(API_TIMEOUT, 120)))
)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_NUM_PREDICT = int(os.getenv("JARVIS_MAX_TOKENS", "512"))
OLLAMA_NUM_CTX = int(os.getenv("JARVIS_NUM_CTX", "1536"))
# Couches GPU : vide = auto Ollama | 0 = CPU seul | 1+ = couches sur GPU
# Eviter 99 (trop pour la VRAM) — provoque "memory layout cannot be allocated"
_ollama_num_gpu = os.getenv("OLLAMA_NUM_GPU", "").strip()
OLLAMA_NUM_GPU: int | None = int(_ollama_num_gpu) if _ollama_num_gpu != "" else None
OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "0"))
# 5m : compromis VRAM / pas de dechargement trop rapide entre messages
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "5m")
MEMORY_CONTEXT_TURNS = int(os.getenv("JARVIS_MEMORY_TURNS", "4"))
MEMORY_MAX_CHARS = int(os.getenv("JARVIS_MEMORY_MAX_CHARS", "2000"))
MEMORY_SUMMARY_INTERVAL = int(os.getenv("JARVIS_MEMORY_SUMMARY_EVERY", "15"))
MEMORY_SUMMARY_WINDOW = int(os.getenv("JARVIS_MEMORY_SUMMARY_WINDOW", "15"))
EMBED_MODEL = os.getenv("JARVIS_EMBED_MODEL", "nomic-embed-text")
CHROMA_PATH = os.getenv(
    "JARVIS_CHROMA_PATH",
    os.path.join(_BASE_DIR, "data", "chroma"),
)
# Contexte prompt (GTX 1650 / petits modèles)
CONTEXT_SLIM_MAX_TOKENS = int(os.getenv("JARVIS_CONTEXT_SLIM_TOKENS", "1024"))
CONTEXT_SLIM_ENABLED = os.getenv("JARVIS_CONTEXT_SLIM", "true").lower() == "true"
# RAG Chroma : segments courts injectés dans le system prompt
RAG_MICRO_CHUNK_WORDS = int(os.getenv("JARVIS_RAG_MAX_WORDS", "150"))
# Routeur binaire ia / commande locale (scikit-learn, TF-IDF + Naive Bayes)
SKLEARN_ROUTER_ENABLED = (
    os.getenv("JARVIS_SKLEARN_ROUTER", "true").lower() == "true"
)
# Commandes volume / pause / lecture : uniquement si « tidal » est dans la phrase
LOCAL_COMMAND_REQUIRES_TIDAL = (
    os.getenv("JARVIS_LOCAL_REQUIRES_TIDAL", "true").lower() == "true"
)
# Routeur incertain : course async entre deux modèles locaux (stream)
ROUTE_RACE_ENABLED = os.getenv("JARVIS_ROUTE_RACE", "false").lower() == "true"
ROUTE_UNCERTAIN_BAND = int(os.getenv("JARVIS_ROUTE_UNCERTAIN_BAND", "1"))
# Anti-refus Ollama (frequency / presence / logit_bias si supporté)
OLLAMA_REFUSAL_BIAS_ENABLED = (
    os.getenv("JARVIS_REFUSAL_BIAS", "true").lower() == "true"
)
OLLAMA_REFUSAL_REPEAT_PENALTY = float(os.getenv("JARVIS_REFUSAL_REPEAT", "1.14"))
OLLAMA_REFUSAL_FREQUENCY_PENALTY = float(
    os.getenv("JARVIS_REFUSAL_FREQUENCY", "0.45")
)
OLLAMA_REFUSAL_PRESENCE_PENALTY = float(
    os.getenv("JARVIS_REFUSAL_PRESENCE", "0.35")
)
OLLAMA_REFUSAL_LOGIT_BIAS = (
    os.getenv("JARVIS_REFUSAL_LOGIT_BIAS", "true").lower() == "true"
)
OLLAMA_REFUSAL_LOGIT_BIAS_STRENGTH = float(
    os.getenv("JARVIS_REFUSAL_LOGIT_STRENGTH", "-4.0")
)
# FTS5 prefetch historique (avant Chroma)
FTS_PREFETCH_ENABLED = os.getenv("JARVIS_FTS_PREFETCH", "true").lower() == "true"
FTS_PREFETCH_LIMIT = int(os.getenv("JARVIS_FTS_PREFETCH_LIMIT", "3"))
# Squelette Markdown pour exposés / vulgarisation
PROMPT_HYDRATION_ENABLED = (
    os.getenv("JARVIS_PROMPT_HYDRATION", "true").lower() == "true"
)
UVICORN_RELOAD = os.getenv("JARVIS_RELOAD", "false").lower() == "true"

# ========================================
# Cloud (Groq — API OpenAI-compatible)
# ========================================

CLOUD_ENABLED = os.getenv("CLOUD_ENABLED", "false").lower() == "true"
CLOUD_BASE_URL = os.getenv(
    "CLOUD_BASE_URL", "https://api.groq.com/openai/v1"
).rstrip("/")
def _sanitize_cloud_api_key(raw: str) -> str:
    k = (raw or "").strip()
    if k.count("gsk_") > 1:
        second = k.find("gsk_", 4)
        if second > 0:
            print(
                "[Cloud] CLOUD_API_KEY dupliquee dans .env — utilisation de la premiere cle uniquement"
            )
            k = k[:second].strip()
    return k


# Jarvis : CLOUD_API_KEY | alias officiel Groq : GROQ_API_KEY (meme valeur gsk_...)
_raw_cloud_key = os.getenv("CLOUD_API_KEY", "").strip() or os.getenv("GROQ_API_KEY", "").strip()
CLOUD_API_KEY = _sanitize_cloud_api_key(_raw_cloud_key)
CLOUD_MODEL = os.getenv("CLOUD_MODEL", "llama-3.1-8b-instant")
CLOUD_MODEL_HEAVY = os.getenv(
    "CLOUD_MODEL_HEAVY", "deepseek-r1-distill-llama-70b"
)
CLOUD_MAX_TOKENS = int(os.getenv("CLOUD_MAX_TOKENS", "768"))
CLOUD_DAILY_LIMIT = int(os.getenv("CLOUD_DAILY_LIMIT", "30"))
CLOUD_COMPLEXITY_THRESHOLD = int(os.getenv("CLOUD_COMPLEXITY_THRESHOLD", "5"))
CLOUD_HEAVY_THRESHOLD = int(os.getenv("CLOUD_HEAVY_THRESHOLD", "8"))
# Score minimal (avec intention pédagogique/culturelle) pour préférer le cloud
ROUTER_PEDAGOGICAL_CLOUD_SCORE = int(
    os.getenv("ROUTER_PEDAGOGICAL_CLOUD_SCORE", "4")
)
# Fallback : réponse locale jugée trop courte
FALLBACK_MIN_ANSWER_CHARS = int(os.getenv("FALLBACK_MIN_ANSWER_CHARS", "80"))
FALLBACK_MIN_RATIO = float(os.getenv("FALLBACK_MIN_RATIO", "0.15"))
# Early-Abort streaming : couper Ollama dès refus dans le préfixe (~15 tokens)
FALLBACK_EARLY_ABORT_ENABLED = (
    os.getenv("FALLBACK_EARLY_ABORT_ENABLED", "true").lower() == "true"
)
FALLBACK_EARLY_ABORT_MIN_CHARS = int(os.getenv("FALLBACK_EARLY_ABORT_MIN_CHARS", "8"))
FALLBACK_EARLY_ABORT_CHARS = int(os.getenv("FALLBACK_EARLY_ABORT_CHARS", "72"))

# ========================================
# Configuration Serveur API
# ========================================

API_HOST = os.getenv("JARVIS_HOST", "0.0.0.0")
API_PORT = int(os.getenv("JARVIS_PORT", "8000"))

# ========================================
# Mode vocal "Salut Jarvis" (agent wake)
# ========================================

JARVIS_API_URL = os.getenv("JARVIS_API_URL", f"http://127.0.0.1:{API_PORT}")
WAKE_MAX_TOKENS = int(os.getenv("JARVIS_WAKE_MAX_TOKENS", "128"))
WAKE_NUM_CTX = int(os.getenv("JARVIS_WAKE_NUM_CTX", "2048"))
WAKE_LISTEN_SECONDS = float(os.getenv("JARVIS_WAKE_LISTEN_SEC", "6"))
WAKE_COOLDOWN_SEC = float(os.getenv("JARVIS_WAKE_COOLDOWN", "2"))

# ========================================
# Configuration Mémoire
# ========================================

DB_PATH = os.getenv("JARVIS_DB", "jarvis_memory.db")

# Profil unique (assistant personnel — une seule personne)
JARVIS_USER_NAME = os.getenv("JARVIS_USER_NAME", "Briac").strip() or "Briac"
JARVIS_USER_ROLE = os.getenv("JARVIS_USER_ROLE", "ton pote").strip() or "ton pote"
JARVIS_USER_AVOID = os.getenv("JARVIS_USER_AVOID", "").strip()
# Au premier demarrage, enregistre le fait de style en memoire (idempotent)
JARVIS_SEED_PERSONAL_FACT = (
    os.getenv("JARVIS_SEED_PERSONAL_FACT", "true").lower() == "true"
)
_default_personal_fact = (
    f"Je m'appelle {JARVIS_USER_NAME}, tutoie-moi, parle-moi comme à "
    f"{JARVIS_USER_ROLE} un peu blagueur mais utile, réponses courtes mais pas froides"
)
JARVIS_PERSONAL_FACT = os.getenv("JARVIS_PERSONAL_FACT", _default_personal_fact).strip()

# ========================================
# Configuration TTS (Text-to-Speech)
# ========================================

# piper = voix neurale locale (recommande) | sapi = pyttsx3 / voix Windows
TTS_ENGINE = os.getenv("JARVIS_TTS_ENGINE", "piper").lower()
TTS_PIPER_VOICE = os.getenv("JARVIS_PIPER_VOICE", "fr_FR-siwis-medium")
TTS_PIPER_DIR = os.getenv("JARVIS_PIPER_DIR", "piper_models")
TTS_LENGTH_SCALE = float(os.getenv("JARVIS_TTS_SPEED", "0.92"))
TTS_VOICE = os.getenv("JARVIS_VOICE", "hortense")
_TTS_OUT = os.getenv("JARVIS_AUDIO_DIR", "audio_output")
TTS_OUTPUT_DIR = _TTS_OUT if os.path.isabs(_TTS_OUT) else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), _TTS_OUT
)
# Morceau Piper par fichier WAV ; la reponse entiere est decoupee en N morceaux
TTS_CHUNK_CHARS = int(os.getenv("JARVIS_TTS_CHUNK_CHARS", "450"))
# Plafond total lu a voix haute (0 = illimite) — pas confondre avec TTS_CHUNK_CHARS
TTS_SPEAK_MAX_CHARS = int(os.getenv("JARVIS_TTS_SPEAK_MAX", "12000"))
# Alias legacy : si seul JARVIS_TTS_MAX_CHARS est defini, il sert de plafond total
_legacy_tts_max = os.getenv("JARVIS_TTS_MAX_CHARS", "").strip()
if _legacy_tts_max:
    TTS_SPEAK_MAX_CHARS = int(_legacy_tts_max)

# ========================================
# Recherche web (DuckDuckGo)
# ========================================

WEB_SEARCH_ENABLED = os.getenv("JARVIS_WEB_SEARCH", "true").lower() == "true"
WEB_SEARCH_AUTO = os.getenv("JARVIS_WEB_AUTO", "true").lower() == "true"
# Mode wake : autoriser la recherche web (actualités, météo, etc.)
WEB_SEARCH_WAKE = os.getenv("JARVIS_WEB_WAKE", "true").lower() == "true"
WEB_SEARCH_MAX_RESULTS = int(os.getenv("JARVIS_WEB_MAX_RESULTS", "5"))
WEB_SEARCH_TIMEOUT = float(os.getenv("JARVIS_WEB_TIMEOUT", "6"))
WEB_CACHE_TTL_SEC = int(os.getenv("JARVIS_WEB_CACHE_TTL", "3600"))
PRE_LLM_PARALLEL = os.getenv("JARVIS_PRE_LLM_PARALLEL", "true").lower() == "true"

# STT : google (rapide, Internet) | auto (google puis whisper si echec) | whisper (local, lent CPU)
STT_ENGINE = os.getenv("JARVIS_STT_ENGINE", "google").strip().lower()
STT_WHISPER_MODEL = os.getenv("JARVIS_WHISPER_MODEL", "base").strip()
STT_WHISPER_FALLBACK = os.getenv("JARVIS_STT_WHISPER_FALLBACK", "true").lower() == "true"

# Reponses courtes (1-2 phrases) + TTS limite
BRIEF_RESPONSES_DEFAULT = (
    os.getenv("JARVIS_BRIEF_DEFAULT", "false").lower() == "true"
)
BRIEF_MAX_TOKENS = int(os.getenv("JARVIS_BRIEF_MAX_TOKENS", "180"))
BRIEF_TTS_MAX_CHARS = int(os.getenv("JARVIS_BRIEF_TTS_CHARS", "320"))

# Rappels vocaux + notifications
REMINDERS_ENABLED = os.getenv("JARVIS_REMINDERS", "true").lower() == "true"
REMINDER_POLL_SEC = float(os.getenv("JARVIS_REMINDER_POLL", "20"))

# ========================================
# TIDAL (API officielle — credentials dans .env)
# ========================================

TIDAL_CLIENT_ID = os.getenv("TIDAL_CLIENT_ID", "").strip()
TIDAL_CLIENT_SECRET = os.getenv("TIDAL_CLIENT_SECRET", "").strip()
TIDAL_COUNTRY_CODE = os.getenv("TIDAL_COUNTRY_CODE", "FR").strip().upper() or "FR"
TIDAL_ENABLED = os.getenv("TIDAL_ENABLED", "false").lower() == "true"
TIDAL_AUTH_URL = "https://auth.tidal.com/v1/oauth2/token"
TIDAL_API_BASE = "https://openapi.tidal.com/v2"
TIDAL_REDIRECT_URI = os.getenv(
    "TIDAL_REDIRECT_URI", f"http://127.0.0.1:{API_PORT}/tidal/callback"
)
TIDAL_TOKEN_CACHE_PATH = os.path.join(_BASE_DIR, "tidal_token_cache.json")
TIDAL_PREFER_DESKTOP = os.getenv("TIDAL_PREFER_DESKTOP", "true").lower() == "true"
TIDAL_PLAY_WAIT_SEC = float(os.getenv("TIDAL_PLAY_WAIT_SEC", "4.5"))
TIDAL_CDP_ENABLED = os.getenv("TIDAL_CDP_ENABLED", "true").lower() == "true"
TIDAL_CDP_PORT = int(os.getenv("TIDAL_CDP_PORT", "9222"))
TIDAL_CDP_RELAUNCH = os.getenv("TIDAL_CDP_RELAUNCH", "true").lower() == "true"
TIDAL_CDP_TIMEOUT = float(os.getenv("TIDAL_CDP_TIMEOUT", "20"))

if TIDAL_ENABLED and TIDAL_CLIENT_ID and not TIDAL_CLIENT_SECRET:
    print(
        "[Tidal] TIDAL_CLIENT_SECRET vide dans .env — enregistre le fichier "
        "(Ctrl+S) et mets le secret entre guillemets si il contient des ="
    )

# ========================================
# Configuration Debug
# ========================================

DEBUG = os.getenv("JARVIS_DEBUG", "False").lower() == "true"

# ========================================
# Affiche la configuration au démarrage
# ========================================

if CLOUD_ENABLED and CLOUD_API_KEY and CLOUD_API_KEY.count("gsk_") > 1:
    print("[Cloud] Attention : cle API suspecte (doublon) — verifie CLOUD_API_KEY dans .env")

if DEBUG:
    print("⚙️  Configuration Jarvis chargée")
    print(f"  🧠 Modèle : {MODEL}")
    print(f"  🌐 API : {API_HOST}:{API_PORT}")
    print(f"  💾 Base de données : {DB_PATH}")
    print(f"  🎤 TTS : {TTS_ENGINE} / {TTS_PIPER_VOICE if TTS_ENGINE == 'piper' else TTS_VOICE}")
    print(f"  🎵 Tidal : {'actif' if TIDAL_ENABLED and TIDAL_CLIENT_ID else 'desactive'}")
    print(f"  👤 Utilisateur : {JARVIS_USER_NAME} ({JARVIS_USER_ROLE})")
    print(f"  🐛 Debug : {DEBUG}")