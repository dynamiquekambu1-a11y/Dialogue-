"""
Suivi du quota gratuit : 2 générations IA par semaine, par visiteur.

Stockage local SQLite — suffisant pour démarrer, mais NON persistant sur
un hébergement gratuit qui redémarre (voir DEPLOIEMENT.md). À terme,
remplacer par une base hébergée (Supabase, Neon...) pour un vrai suivi
fiable des utilisateurs payants.

Identification actuelle : par adresse IP. C'est une limite volontaire du
MVP — un même foyer/réseau partage un quota, et un utilisateur motivé peut
la contourner (VPN, etc). Le vrai verrou viendra du compte utilisateur au
moment de brancher l'authentification + le paiement.
"""

import os
import sqlite3
import time
from pathlib import Path

from fastapi import Request

DB_PATH = Path("usage.db")
QUOTA_GRATUIT_PAR_SEMAINE = 2
SEMAINE_EN_SECONDES = 7 * 24 * 60 * 60

# Clé secrète qui débloque un accès illimité (toi, pour tester).
# Définie via une variable d'environnement, jamais écrite en dur dans le code.
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


def _connexion() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS utilisation (
            identifiant TEXT PRIMARY KEY,
            debut_fenetre INTEGER NOT NULL,
            compteur INTEGER NOT NULL
        )
    """)
    return conn


def obtenir_identifiant(request: Request) -> str:
    """
    Identifie le visiteur par IP, en tenant compte des en-têtes de proxy
    (Hugging Face / Render placent la vraie IP dans X-Forwarded-For).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "inconnu"


def cle_admin_valide(request: Request) -> bool:
    """
    Vérifie si la requête contient la clé admin (envoyée via l'en-tête
    X-Admin-Key par le frontend). Si ADMIN_KEY n'est pas configurée côté
    serveur, cette vérification est toujours fausse — personne n'est admin
    par défaut.
    """
    if not ADMIN_KEY:
        return False
    cle_recue = request.headers.get("x-admin-key", "")
    return cle_recue == ADMIN_KEY


def est_premium(identifiant: str) -> bool:
    """
    Point d'extension pour le mode payant.
    À brancher plus tard sur un vrai système d'abonnement (Stripe, etc.) :
    par exemple vérifier ici si l'identifiant/le compte a un abonnement actif.
    Retourne False pour l'instant — personne n'est premium.
    """
    return False


def consulter_quota(identifiant: str) -> dict:
    """Lit l'état du quota SANS le consommer (pour affichage côté frontend)."""
    if est_premium(identifiant):
        return {"restant": None, "limite": None, "premium": True}

    maintenant = int(time.time())
    conn = _connexion()
    try:
        cur = conn.execute(
            "SELECT debut_fenetre, compteur FROM utilisation WHERE identifiant = ?",
            (identifiant,),
        )
        ligne = cur.fetchone()

        if ligne is None or (maintenant - ligne[0]) >= SEMAINE_EN_SECONDES:
            return {
                "restant": QUOTA_GRATUIT_PAR_SEMAINE,
                "limite": QUOTA_GRATUIT_PAR_SEMAINE,
                "premium": False,
            }

        _, compteur = ligne
        return {
            "restant": max(0, QUOTA_GRATUIT_PAR_SEMAINE - compteur),
            "limite": QUOTA_GRATUIT_PAR_SEMAINE,
            "premium": False,
        }
    finally:
        conn.close()


def verifier_et_consommer_quota(identifiant: str) -> dict:
    """
    Vérifie si le visiteur peut lancer une génération IA, et consomme un
    crédit si oui. Lève ValueError si le quota est déjà atteint.
    """
    if est_premium(identifiant):
        return {"restant": None, "premium": True}

    maintenant = int(time.time())
    conn = _connexion()
    try:
        cur = conn.execute(
            "SELECT debut_fenetre, compteur FROM utilisation WHERE identifiant = ?",
            (identifiant,),
        )
        ligne = cur.fetchone()

        if ligne is None or (maintenant - ligne[0]) >= SEMAINE_EN_SECONDES:
            debut_fenetre = maintenant
            compteur = 0
        else:
            debut_fenetre, compteur = ligne

        if compteur >= QUOTA_GRATUIT_PAR_SEMAINE:
            prochaine_reinitialisation = debut_fenetre + SEMAINE_EN_SECONDES
            jours_restants = max(1, int((prochaine_reinitialisation - maintenant) / 86400) + 1)
            raise ValueError(
                f"Quota gratuit atteint ({QUOTA_GRATUIT_PAR_SEMAINE} générations/semaine). "
                f"Réinitialisation dans environ {jours_restants} jour(s). "
                f"Le mode premium arrive bientôt pour générer sans limite."
            )

        compteur += 1
        conn.execute(
            "INSERT INTO utilisation (identifiant, debut_fenetre, compteur) VALUES (?, ?, ?) "
            "ON CONFLICT(identifiant) DO UPDATE SET debut_fenetre = excluded.debut_fenetre, "
            "compteur = excluded.compteur",
            (identifiant, debut_fenetre, compteur),
        )
        conn.commit()

        return {"restant": QUOTA_GRATUIT_PAR_SEMAINE - compteur, "premium": False}
    finally:
        conn.close()
