# Jarvis Assistant — IA Personnelle Locale

Assistant personnel conversationnel en français pour **Windows** : chat web, voix (« Salut Jarvis »), mémoire, recherche web, TTS local (Piper) et LLM local via [Ollama](https://ollama.com).

## 🚨 Le Problème
* **Confidentialité et Dépendance au Cloud :** Les assistants vocaux grand public (Siri, Alexa) envoient l'intégralité des conversations sur des serveurs distants, posant des problèmes de souveraineté des données.
* **Coût et Latence :** L'utilisation constante d'API cloud payantes (ex: OpenAI) pour un assistant vocal 24/7 est coûteuse.
* **Manque de personnalisation et de contexte :** Les assistants standards ont une mémoire très limitée et ne connaissent pas véritablement l'utilisateur.

## 💡 La Solution
Développement de **Jarvis**, une IA personnelle 100% autonome et hybride, conçue pour tourner sur du matériel modeste (carte graphique 4Go) :
* **Intelligence Hybride (Routage Local/Cloud) :** Analyse instantanée de la complexité de la requête. Utilisation d'Ollama (modèle local ultra-rapide Qwen) pour les tâches simples, et bascule vers une API Cloud (Groq) pour les requêtes complexes.
* **Mémoire Long-Terme & RAG :** Historique persistant (SQLite) et base de données vectorielle (ChromaDB) pour stocker des faits, créer des rappels, et retrouver le contexte pertinent. L'IA apprend à connaître l'utilisateur.
* **100% Vocal & Mains-Libres :** Détection de mot d'éveil ("Salut Jarvis" via openWakeWord), reconnaissance vocale et synthèse vocale locale (Piper TTS).
* **Connectivité Web & Système :** Pilotage en direct du volume Windows, intégration de commandes musicales (Tidal API), et capacité de rechercher des informations fraîches sur internet (DuckDuckGo).
* **Architecture Client/Serveur :** Backend robuste (FastAPI) pilotable via une interface web locale (PC ou smartphone sur le même réseau).

## 🎯 Mon Rôle
**Ingénieur IA & Développeur Backend (Python) :**
- Conception complète de l'architecture logicielle hybride.
- Développement du backend en Python (FastAPI, Uvicorn).
- Intégration et optimisation des modèles d'Intelligence Artificielle locaux (Ollama) et cloud (Groq).
- Mise en place du RAG (Retrieval-Augmented Generation) avec ChromaDB et SQLite pour la mémoire.

---

## 🚀 Démarrage rapide

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

## 📚 Documentation
- [DESCRIPTION.md](DESCRIPTION.md) — présentation métier et architecture
- [MANUEL_UTILISATEUR.md](MANUEL_UTILISATEUR.md) — guide utilisateur

## ⚙️ Prérequis
- Windows 10/11
- Ollama avec les modèles configurés dans `.env` (ex. `qwen2.5:3b-instruct-q4_K_M`)
- Voix Piper : placer les modèles dans `piper_models/` (voir config `JARVIS_PIPER_VOICE`)

## 📄 Licence
Usage personnel.
