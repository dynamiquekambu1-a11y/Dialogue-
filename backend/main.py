"""
API du générateur de dialogues audio.
Lance avec : uvicorn main:app --reload --port 8000
"""

from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import dialogue_engine as engine
import quota as quota_module

app = FastAPI(title="Générateur de dialogues audio")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ---------------------------------------------------------
# SCHÉMAS
# ---------------------------------------------------------

class RequeteGeneration(BaseModel):
    mode: Literal["ia", "manuel"]
    genre: Optional[str] = "love"
    duree_secondes: Optional[int] = 30
    nb_personnages: Optional[int] = 2
    cible: Optional[str] = "mixte"          # pour_elle / pour_lui / mixte (genre "love")
    script_manuel: Optional[str] = None      # requis si mode == "manuel"


class RepliqueDialogue(BaseModel):
    personnage: str
    genre: Literal["femme", "homme", "neutre"] = "neutre"
    ligne: str
    ton: Optional[str] = ""


class RequeteAudio(BaseModel):
    dialogue: list[RepliqueDialogue]
    format_sortie: Literal["mp3", "wav"] = "mp3"


# ---------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------

@app.post("/api/generer-dialogue")
def generer_dialogue(requete: RequeteGeneration, request: Request):
    """
    Génère le texte du dialogue (mode IA) ou parse un script collé (mode manuel).
    Ne fait PAS encore de synthèse vocale : le dialogue est renvoyé pour
    relecture/édition côté frontend avant de lancer l'audio.

    Le quota gratuit (2/semaine) ne s'applique qu'au mode IA — coller son
    propre script reste illimité, puisque ça ne consomme pas de génération IA.
    """
    if requete.mode == "ia":
        if requete.nb_personnages < 2 or requete.nb_personnages > 4:
            raise HTTPException(400, "Le nombre de personnages doit être entre 2 et 4.")

        if quota_module.cle_admin_valide(request):
            etat_quota = {"restant": None, "premium": True}
        else:
            identifiant = quota_module.obtenir_identifiant(request)
            try:
                etat_quota = quota_module.verifier_et_consommer_quota(identifiant)
            except ValueError as e:
                raise HTTPException(429, str(e))

        try:
            resultat = engine.generer_dialogue_ia(
                genre=requete.genre,
                duree_secondes=requete.duree_secondes,
                nb_personnages=requete.nb_personnages,
                cible=requete.cible,
            )
        except Exception as e:
            raise HTTPException(500, f"Erreur de génération IA : {e}")

        resultat["quota_restant"] = etat_quota["restant"]
        return resultat

    else:  # mode == "manuel"
        if not requete.script_manuel or not requete.script_manuel.strip():
            raise HTTPException(400, "Le script manuel est vide.")
        dialogue = engine.parser_script_manuel(requete.script_manuel)
        if not dialogue:
            raise HTTPException(
                400,
                "Aucune réplique reconnue. Format attendu : "
                "Personnage (ton optionnel) : « réplique »",
            )
        return {"dialogue": dialogue, "legende_suggeree": None}


@app.post("/api/generer-audio")
async def generer_audio(requete: RequeteAudio):
    """
    Prend un dialogue structuré (éventuellement édité par l'utilisateur)
    et produit le fichier audio final.
    """
    dialogue = [r.dict() for r in requete.dialogue]
    if not dialogue:
        raise HTTPException(400, "Dialogue vide.")

    try:
        nom_fichier = await engine.exporter_audio(dialogue, format_sortie=requete.format_sortie)
    except Exception as e:
        raise HTTPException(500, f"Erreur de synthèse vocale : {e}")

    return {"fichier": nom_fichier, "url_telechargement": f"/api/telecharger/{nom_fichier}"}


@app.get("/api/quota")
def obtenir_quota(request: Request):
    """Consulte le quota restant sans le consommer — pour affichage côté frontend."""
    if quota_module.cle_admin_valide(request):
        return {"restant": None, "limite": None, "premium": True}
    identifiant = quota_module.obtenir_identifiant(request)
    return quota_module.consulter_quota(identifiant)


@app.get("/api/telecharger/{nom_fichier}")
def telecharger(nom_fichier: str):
    chemin = engine.DOSSIER_AUDIO / nom_fichier
    if not chemin.exists():
        raise HTTPException(404, "Fichier introuvable.")
    return FileResponse(chemin, media_type="audio/mpeg", filename=nom_fichier)


# Sert le frontend statique (doit être monté APRÈS les routes /api/*)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
