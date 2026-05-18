# requirements.txt
# ========================================
# Dépendances Jarvis Assistant
# ========================================

# Framework Web API
fastapi==0.104.1
uvicorn[standard]==0.24.0

# Utilitaires
requests==2.31.0
httpx==0.27.2
python-multipart==0.0.6
pydantic>=2.5.0

# Text-to-Speech (Piper = voix naturelle ; pyttsx3 = repli voix Windows)
piper-tts==1.4.2
pyttsx3>=2.90

# Optionnel : Vector Database pour recherche avancée
# chromadb==0.4.0

# Optionnel : Speech-to-Text
# SpeechRecognition==3.10.0

# Agent vocal (sans compte) : pip install -r requirements-wake.txt

# Note: SQLite3 est inclus dans Python, pas besoin de l'installer

# Pour installer toutes les dépendances :
# pip install -r requirements.txt