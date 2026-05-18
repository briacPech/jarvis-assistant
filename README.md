# Jarvis Assistant

Assistant personnel conversationnel en français pour **Windows** : chat web, voix (« Salut Jarvis »), mémoire, recherche web, TTS local (Piper) et LLM local via [Ollama](https://ollama.com).

## Démarrage rapide

1. Installer [Ollama](https://ollama.com) et Python 3.10+
2. Copier `.env.example` vers `.env` et adapter
3. Créer l’environnement et les dépendances :

```bat
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
pip install -r requirements-stt.txt
pip install -r requirements-wake.txt
```

4. Double-cliquer sur **`Lancer_Jarvis.bat`** ou ouvrir [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

## Documentation

- [DESCRIPTION.md](DESCRIPTION.md) — présentation métier et architecture
- [MANUEL_UTILISATEUR.md](MANUEL_UTILISATEUR.md) — guide utilisateur

## Prérequis

- Windows 10/11
- Ollama avec les modèles configurés dans `.env` (ex. `qwen2.5:3b-instruct-q4_K_M`)
- Voix Piper : placer les modèles dans `piper_models/` (voir config `JARVIS_PIPER_VOICE`)

## Licence

Usage personnel — voir le dépôt pour les détails si une licence est ajoutée.
