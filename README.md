# Réplique — Générateur de dialogues audio (version 100% gratuite)

Site web complet : formulaire (genre, durée, personnages, ou script collé) →
dialogue généré/parsé → synthèse vocale par personnage → fichier audio téléchargeable.

**Coût de cette version : 0 €.** Aucune carte bancaire requise.

- **Écriture du dialogue** : API Gemini de Google (plan gratuit)
- **Voix** : edge-tts (voix Microsoft Edge, gratuites et illimitées)

## Structure

```
dialogue-app/
├── backend/
│   ├── main.py              # API FastAPI (sert aussi le frontend)
│   ├── dialogue_engine.py   # génération IA, parsing, voix, synthèse, fusion audio
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── style.css
    └── script.js
```

## Installation

Prérequis : Python 3.10+, ffmpeg installé sur le système.

### 1. Récupérer une clé API Gemini (gratuite)

1. Aller sur **https://aistudio.google.com/apikey**
2. Se connecter avec un compte Google
3. Cliquer sur "Create API key" — aucune carte bancaire demandée
4. Copier la clé générée

### 2. Installer les dépendances

```bash
cd dialogue-app/backend
pip install -r requirements.txt --break-system-packages
```

### 3. Configurer la clé

```bash
export GEMINI_API_KEY="ta-cle-gemini"
```

edge-tts ne nécessite aucune clé ni inscription.

## Lancement

```bash
cd dialogue-app/backend
uvicorn main:app --reload --port 8000
```

Puis ouvrir **http://localhost:8000** dans le navigateur.

## Fonctionnement

1. **Mode IA** : Gemini écrit le dialogue en JSON structuré, avec un champ
   `ton` par réplique (ex: "chuchote, paniquée").
2. **Mode script manuel** : coller un texte au format
   `Personnage (ton) : « réplique »` → parsé automatiquement.
3. **Aperçu éditable** avant de lancer la synthèse vocale.
4. **Attribution des voix** : chaque personnage reçoit une voix française
   edge-tts distincte selon son genre déclaré (femme/homme/neutre).
5. **Génération audio** : chaque réplique est synthétisée séparément, puis
   fusionnée avec une courte pause entre les répliques.
6. **Téléchargement** : fichier MP3 ou WAV prêt pour CapCut, TikTok, etc.

## Différence importante par rapport à la version OpenAI

edge-tts n'a pas d'équivalent au paramètre `instructions` de l'API OpenAI
(qui permettait de vraiment "jouer" une émotion). À la place, le `ton` de
chaque réplique est traduit en réglages de **débit / volume / hauteur de
voix** (ex: "chuchote" → volume plus bas et débit ralenti). C'est une
approximation : le rendu est correct mais moins expressif qu'avec une vraie
instruction d'acting. Si le budget le permet un jour, c'est le point le
plus rentable à améliorer en repassant sur `gpt-4o-mini-tts` ou une API
comme ElevenLabs.

## Ton accès illimité pour tester (clé admin)

Pour tester le site sans être limité à 2 générations/semaine :

1. Sur Render, dans l'onglet **"Environment"**, ajoute une variable
   `ADMIN_KEY` avec une valeur secrète de ton choix (ex: un mot de passe
   que toi seul connais).
2. Visite ton site **une seule fois** avec cette adresse :
   `https://ton-site.onrender.com/?admin=TA_VALEUR_SECRETE`
3. Le navigateur mémorise cette clé automatiquement (dans son stockage
   local) — toutes tes visites suivantes depuis ce même navigateur seront
   illimitées, sans avoir à retaper l'adresse spéciale.
4. Si `ADMIN_KEY` n'est pas définie côté serveur, cette fonctionnalité est
   désactivée par défaut — personne (même avec la bonne URL) ne peut
   contourner le quota sans que tu l'aies explicitement configuré.

**Important** : ne partage jamais l'adresse avec `?admin=...` publiquement
— quiconque l'utilise devient illimité lui aussi.

## Quota gratuit (2 générations IA / semaine)

Le mode "L'IA écrit le dialogue" est limité à **2 générations par semaine
par visiteur** (identifié par adresse IP). Le mode "Coller mon script"
reste illimité, puisqu'il ne consomme aucune génération IA.

- Géré par `backend/quota.py`, stockage dans `backend/usage.db` (SQLite).
- Le frontend affiche le quota restant et désactive le bouton une fois
  atteint (`GET /api/quota` pour consulter sans consommer).
- `est_premium()` dans `quota.py` retourne toujours `False` pour l'instant
  — c'est le point d'extension prévu pour brancher un vrai mode payant
  (ex: Stripe Checkout + table `abonnements` vérifiée ici) sans toucher
  au reste du code.
- **Limite à connaître** : l'identification par IP est un choix de MVP.
  Un réseau partagé (foyer, entreprise) partage le même quota, et la base
  SQLite n'est pas persistante sur un hébergement gratuit qui redémarre
  (voir section suivante). Pour un vrai lancement payant, il faudra un
  vrai compte utilisateur (email ou OAuth) plutôt qu'une IP.

## Limites connues du plan gratuit

- **Gemini** : quotas quotidiens (le nombre exact varie selon le modèle et
  change régulièrement côté Google) — largement suffisant pour développer
  et tester, à surveiller si le site devient public. Vérifiable en direct
  sur `aistudio.google.com`.
- **edge-tts** : non officiel (réutilise le service vocal de Microsoft
  Edge). Fonctionne de façon fiable en pratique, mais sans garantie
  contractuelle de disponibilité à long terme.
- Pas encore de quota gratuit/premium appliqué côté serveur (juste visuel
  sur le frontend).
- Pas de nettoyage automatique des fichiers dans `backend/audio_generes/`.

## Migration future vers la version payante (OpenAI)

Le code est structuré pour que la bascule soit rapide plus tard : il suffit
de remplacer les fonctions `generer_dialogue_ia` (Gemini → GPT-4o) et
`_generer_audio_ligne` (edge-tts → TTS OpenAI) dans `dialogue_engine.py`.
Le reste de l'application (parsing, attribution des voix, API, frontend)
n'a pas besoin de changer.
