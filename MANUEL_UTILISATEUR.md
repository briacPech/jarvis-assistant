# Jarvis — Manuel utilisateur

Guide d’utilisation de l’assistant personnel **Jarvis** sur Windows.

---

## 1. C’est quoi ?

Jarvis est un assistant que vous pouvez interroger **par écrit** ou **à la voix**. Il répond en français, se souvient de certaines informations sur vous, peut chercher sur le web (météo, actualités…) et, si vous l’activez, lire ses réponses à haute voix.

Tout fonctionne **sur votre PC** : vos conversations ne partent pas sur Internet sauf pour la recherche web, la reconnaissance vocale (Google) ou le mode cloud optionnel.

---

## 2. Démarrer Jarvis

### Démarrage simple (recommandé)

1. Double-cliquez sur **`Lancer_Jarvis.bat`** à la racine du dossier du projet.
2. Le script :
   - démarre **Ollama** si nécessaire ;
   - lance l’**API Jarvis** (port 8000) ;
   - active le **mode vocal** (« Salut Jarvis ») ;
   - ouvre le **chat** dans votre navigateur : [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

3. Attendez le message **« Jarvis est prêt »** dans la fenêtre noire.

### Arrêter Jarvis

Double-cliquez sur **`Arreter_Jarvis.bat`**.

> Ollama reste parfois actif en arrière-plan. Fermez-le manuellement depuis la barre des tâches si vous voulez libérer la mémoire GPU.

### Démarrage manuel (dépannage)

| Action | Fichier / commande |
|--------|-------------------|
| API seule | `start_jarvis_api.bat` |
| Mode vocal seul | `start_jarvis_wake.bat` (API doit déjà tourner) |

---

## 3. Interface web — Chat

Ouvrez [http://127.0.0.1:8000/](http://127.0.0.1:8000/) (ou l’IP de votre PC depuis un téléphone sur le même Wi‑Fi).

### Envoyer un message

1. Tapez votre question dans le champ en bas.
2. Cliquez **Envoyer** ou appuyez sur **Entrée**.

### Options utiles

| Option | Effet |
|--------|--------|
| **Voix** | Jarvis lit la réponse (haut-parleurs) |
| **Discussion** | Enchaîne plusieurs échanges sans tout répéter |
| **Micro serveur** | Enregistre via le PC (recommandé, plus stable) |
| **Recherche web** | Actualités, météo, infos récentes |
| **Réponses courtes** | 1–2 phrases (idéal à la voix) |
| **Réponse progressive** | Le texte s’affiche mot à mot pendant la génération |

### Micro (🎤)

1. Cochez **Micro serveur** (recommandé).
2. Cliquez sur **🎤**, parlez, recliquez pour arrêter.
3. Le texte transcrit est envoyé ; la réponse peut être lue si **Voix** est coché.

### Modèle et performance

- **Modèle Ollama** : choisissez dans la liste (évitez les très gros modèles sur un PC 4 Go VRAM).
- **Mode rapide** : règle tokens et contexte pour des réponses plus courtes et plus rapides.
- **Sauver réglages** : mémorise vos choix dans le navigateur.

### Depuis un téléphone (même maison)

1. Sur le PC, notez l’adresse IP locale (ex. `192.168.1.42`).
2. Dans le chat, section en bas : saisissez `http://192.168.1.42:8000` puis **Sauver API**.
3. Ouvrez cette adresse sur le téléphone (même Wi‑Fi).

### Page de statut

Lien **Statut** en bas de page, ou : [http://127.0.0.1:8000/status/ui](http://127.0.0.1:8000/status/ui) — vérifie Ollama, mémoire, web, cloud.

---

## 4. Mode vocal « Salut Jarvis »

Sans toucher au clavier :

1. Lancez Jarvis avec **`Lancer_Jarvis.bat`** (le mode vocal démarre automatiquement).
2. Dites **« Salut Jarvis »** ou **« Hey Jarvis »** (prononciation proche de l’anglais).
3. Un **bip** confirme l’écoute : posez votre question tout de suite.
4. Jarvis répond par la **voix** (et enregistre l’échange en mémoire).

**Conseils :**

- Parlez clairement, micro à ~30 cm.
- Évitez la musique forte pendant l’écoute.
- Après chaque réponse, attendez ~2 secondes avant de redire « Salut Jarvis ».

---

## 5. Mémoire et rappels

### Ce que Jarvis retient

- Votre **prénom** et le **ton** souhaité (configuré au premier lancement).
- Les **faits** que vous lui demandez de retenir.

**Exemples de phrases :**

- « Retiens que j’aime le jazz. »
- « Rappelle-moi ce que tu sais sur moi. »
- « Oublie le fait sur le jazz. » *(selon implémentation — sinon via l’API mémoire)*

### Rappels

Vous pouvez demander par exemple :

- « Rappelle-moi dans 10 minutes de sortir les pâtes. »
- « Demain à 9 h, rappelle-moi d’appeler le médecin. »

Une **notification Windows** ou un message vocal peut vous prévenir à l’heure dite (si les rappels sont activés dans la configuration).

---

## 6. Recherche web

Quand **Recherche web** est cochée, Jarvis peut consulter **DuckDuckGo** pour :

- la météo ;
- l’actualité ;
- des prix, horaires, résultats sportifs, etc.

Sans Internet, ces questions seront moins précises.

---

## 7. Musique et volume (optionnel)

Si **Tidal** est configuré dans le fichier `.env` :

- Vous pouvez demander de **lancer**, **mettre en pause** ou **changer le volume** de la musique.
- Certaines commandes exigent le mot **« tidal »** dans la phrase (ex. « tidal, mets en pause »).

Sans Tidal, le volume Windows peut parfois être réglé par commande vocale simple (selon configuration).

---

## 8. Cloud Groq (optionnel)

Si un administrateur a activé `CLOUD_ENABLED=true` et renseigné une clé API :

- Jarvis envoie automatiquement les **questions difficiles** au cloud (quota journalier limité).
- Utile pour les explications longues ou le raisonnement complexe.

Vous n’avez rien à cocher : le routage est automatique. Le statut cloud est visible sur `/status/ui`.

---

## 9. Problèmes fréquents

| Symptôme | Piste de solution |
|----------|-------------------|
| Page inaccessible | Vérifiez que `Lancer_Jarvis.bat` est lancé ; testez [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) |
| Réponses très lentes | Utilisez **Mode rapide** ; réduisez **Max tokens** ; fermez les gros modèles Ollama |
| Pas de voix | Cochez **Voix** ; vérifiez le volume Windows ; relancez l’API |
| Micro ne marche pas | Cochez **Micro serveur** ; autorisez le micro dans Windows |
| « Salut Jarvis » ne réagit pas | Vérifiez que la fenêtre **Jarvis Wake** tourne ; parlez plus près du micro |
| Port 8000 occupé | Fermez l’autre programme ou changez `JARVIS_PORT` dans `.env` |
| Erreur Ollama | Lancez `ollama serve` ; installez le modèle indiqué dans `.env` |

### Réinitialiser la mémoire

Réservé aux utilisateurs avancés : endpoint `DELETE /memory/clear` (documentation API) — **efface tout l’historique**.

---

## 10. Fichiers importants (utilisateur)

| Fichier | Rôle |
|---------|------|
| `Lancer_Jarvis.bat` | Tout démarrer |
| `Arreter_Jarvis.bat` | Tout arrêter |
| `.env` | Votre prénom, modèles, clés API (ne pas partager) |
| `jarvis_memory.db` | Historique et faits mémorisés |

---

## 11. Bonnes pratiques

1. **Premier lancement** : attendez 30–60 s (chargement du modèle Ollama).
2. **Usage vocal** : activez **Réponses courtes** + **Voix**.
3. **Confidentialité** : ne exposez pas le port 8000 sur Internet sans protection.
4. **Sauvegardes** : copiez `jarvis_memory.db` pour garder votre historique.

---

## 12. Aide rapide — exemples de phrases

| Vous dites… | Jarvis… |
|-------------|---------|
| « Quelle heure est-il ? » | Donne l’heure (commande locale rapide) |
| « Quel temps fait-il à Paris ? » | Cherche sur le web si activé |
| « Explique-moi les trous noirs simplement » | Réponse détaillée (éventuellement cloud) |
| « Retiens que mon chien s’appelle Max » | Enregistre un fait |
| « Rappelle-moi dans 5 minutes de regarder le four » | Programme un rappel |
| « Salut Jarvis » *(puis)* « Raconte une blague » | Mode vocal mains libres |

---

*Pour la présentation technique et l’architecture, voir [DESCRIPTION.md](DESCRIPTION.md).*
