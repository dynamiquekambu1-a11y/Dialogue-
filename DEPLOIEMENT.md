# Déployer le site sans machine locale (gratuit)

Tu n'as pas besoin d'ordinateur : tout se fait depuis le navigateur, via
Hugging Face Spaces. Deux façons de procéder — commence par la Voie A,
plus simple.

## Voie A — Upload direct dans le Space (recommandé pour démarrer)

### 1. Créer le Space

1. Va sur **huggingface.co**, crée un compte gratuit (aucune carte
   bancaire).
2. Clique sur ton profil → **"New Space"**.
3. Donne-lui un nom (ex: `replique-dialogues`).
4. Dans **"Space SDK"**, choisis **Docker**.
5. Visibilité : Public ou Private, comme tu veux.
6. Valide. Hugging Face crée automatiquement un `README.md` avec le bloc
   de configuration nécessaire tout en haut (title, sdk: docker, etc.) —
   tu n'as rien à écrire toi-même pour ça.

### 2. Uploader les fichiers du projet

1. Dans ton nouveau Space, va dans l'onglet **"Files"**.
2. Clique sur **"Add file" → "Upload files"**.
3. Glisse-dépose l'intégralité du dossier `dialogue-app/` (le navigateur
   garde l'arborescence des sous-dossiers `backend/` et `frontend/`).
4. Assure-toi que le `Dockerfile` et le `.dockerignore` se retrouvent bien
   **à la racine** du Space (pas dans un sous-dossier).
5. Le `README.md` du projet peut remplacer le contenu du README généré
   par Hugging Face — garde juste le bloc `---title: ... ---` tout en
   haut, colle le reste de notre README en dessous.

### 3. Ajouter ta clé Gemini en secret

1. Dans le Space → **Settings** → **"Variables and secrets"**.
2. Ajoute un secret nommé `GEMINI_API_KEY` avec ta clé (récupérée sur
   `aistudio.google.com/apikey`).
3. Ne mets jamais la clé directement dans un fichier uploadé.

### 4. Attendre le déploiement

Va dans l'onglet **"Logs"** pour suivre la construction de l'image Docker
(quelques minutes). Une fois terminé, ton site est en ligne à :

```
https://[ton-nom-utilisateur]-replique-dialogues.hf.space
```

**Pour toute future modification** : reviens dans "Files", uploade les
fichiers changés, le Space se reconstruit automatiquement.

---

## Voie B — Garder GitHub comme source principale (optionnel, plus tard)

Si tu veux que GitHub reste la version de référence et que le Space se
mette à jour tout seul à chaque modification, il faut une **GitHub
Action** dédiée (il n'existe pas de bouton "connecter" automatique côté
Hugging Face). Le principe :

1. Le code vit sur GitHub.
2. Un token Hugging Face (avec droit d'écriture) est stocké comme secret
   GitHub (`HF_TOKEN`).
3. Un fichier `.github/workflows/sync-to-hub.yml` copie automatiquement
   le contenu du repo GitHub vers le Space à chaque `push`.

C'est plus propre à terme mais demande de manipuler les secrets GitHub et
un fichier YAML — pas nécessaire pour tester. Dis-moi quand tu veux
passer à cette étape, je te prépare le fichier `sync-to-hub.yml` exact et
le pas-à-pas pour créer le token.

---

## À savoir sur cet hébergement gratuit

- Le stockage n'est **pas persistant** : les fichiers audio générés et le
  fichier `usage.db` (quota) peuvent disparaître si le Space redémarre ou
  si tu re-uploades des fichiers. Suffisant pour tester, à corriger avant
  une vraie mise en production (stockage/BDD externe).
- Un Space gratuit peut se mettre en veille après une période
  d'inactivité et prendre quelques secondes à se "réveiller" — normal.
- Alternative de secours si Hugging Face ne convient pas : **Render.com**,
  chemin très similaire (dépôt GitHub → Dockerfile → déploiement gratuit).
