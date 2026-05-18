# routeur_jarvis.py — aiguillage ia vs commande locale (TF-IDF + Naive Bayes, <1 ms)

from __future__ import annotations

import os
import pickle

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_BASE_DIR, "routeur_jarvis.pkl")
META_PATH = os.path.join(_BASE_DIR, "routeur_jarvis.meta")
# Incrémenter pour forcer un ré-entraînement après changement de DONNEES_ENTRAINEMENT
ROUTER_TRAINING_VERSION = 3

# Phrases d'entraînement — enrichir selon tes usages Redmi / wake
DONNEES_ENTRAINEMENT: list[tuple[str, str]] = [
    # IA (Ollama / cloud)
    ("Explique-moi la théorie de la relativité", "ia"),
    ("Raconte-moi l'histoire de la Bretagne", "ia"),
    ("Donne-moi une recette de cuisine avec du poulet", "ia"),
    ("Génère un script Python pour trier une liste", "ia"),
    ("Que penses-tu de l'intelligence artificielle ?", "ia"),
    ("Résume-moi ce livre en trois points", "ia"),
    ("Quelle est la capitale du Portugal", "ia"),
    ("Aide-moi à rédiger un mail professionnel", "ia"),
    ("Traduis en anglais : bonjour comment vas-tu", "ia"),
    ("Pourquoi le ciel est bleu", "ia"),
    ("Explique la photosynthèse", "ia"),
    ("Explique-moi comment fonctionne le wifi", "ia"),
    ("Qu'est-ce que la photosynthèse", "ia"),
    # Commandes locales (PC / média / domotique)
    ("Allume la lumière du salon", "commande"),
    ("Lance Spotify et mets de la musique", "commande"),
    ("Ouvre l'application Cursor", "commande"),
    ("Éteins l'ordinateur dans dix minutes", "commande"),
    ("Mets le volume du PC à 50 pour cent", "commande"),
    ("Active l'éclairage de la chambre", "commande"),
    ("Coupe le son", "commande"),
    ("Mets en pause la musique", "commande"),
    ("Passe au morceau suivant", "commande"),
    ("Lance la musique sur Spotify", "commande"),
    ("Monte le volume", "commande"),
    ("Monte le son", "commande"),
    ("Plus fort", "commande"),
    ("Baisse le volume", "commande"),
    ("Pause", "commande"),
    ("Morceau suivant", "commande"),
    ("Joue Daft Punk", "commande"),
    ("Lance de la musique", "commande"),
    ("Quelle heure est-il", "commande"),
    ("Parle-moi du festival Les Plages Musicales à Damgan", "ia"),
    ("Raconte le festival Les Plages Musicales dans le Morbihan", "ia"),
]

_modele_routeur: Pipeline | None = None


def entrainer_routeur() -> Pipeline:
    phrases = [x[0] for x in DONNEES_ENTRAINEMENT]
    categories = [x[1] for x in DONNEES_ENTRAINEMENT]
    modele: Pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(lowercase=True)),
            ("clf", MultinomialNB()),
        ]
    )
    modele.fit(phrases, categories)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(modele, f)
    with open(META_PATH, "w", encoding="utf-8") as f:
        f.write(str(ROUTER_TRAINING_VERSION))
    print("[Routeur] Modele scikit-learn entraîne ->", MODEL_PATH)
    return modele


def _routeur_meta_ok() -> bool:
    if not os.path.exists(META_PATH):
        return False
    try:
        with open(META_PATH, encoding="utf-8") as f:
            return int(f.read().strip()) == ROUTER_TRAINING_VERSION
    except (OSError, ValueError):
        return False


def charger_routeur() -> Pipeline:
    global _modele_routeur
    if _modele_routeur is not None:
        return _modele_routeur
    if not os.path.exists(MODEL_PATH) or not _routeur_meta_ok():
        _modele_routeur = entrainer_routeur()
    else:
        with open(MODEL_PATH, "rb") as f:
            _modele_routeur = pickle.load(f)
    return _modele_routeur


def aiguiller_requete(texte: str) -> str:
    """Retourne 'ia' ou 'commande' (typiquement <1 ms sur CPU)."""
    texte = (texte or "").strip()
    if not texte:
        return "ia"
    modele = charger_routeur()
    return str(modele.predict([texte])[0])


def est_commande_locale(texte: str) -> bool:
    return aiguiller_requete(texte) == "commande"


if __name__ == "__main__":
    tests = [
        "Active l'éclairage de la chambre",
        "Explique la photosynthèse",
        "Mets le volume à 30 pour cent",
    ]
    for t in tests:
        cible = aiguiller_requete(t)
        print(f"'{t}' -> {cible.upper()}")
