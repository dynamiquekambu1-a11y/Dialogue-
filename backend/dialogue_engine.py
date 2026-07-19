"""
Moteur du générateur de dialogues audio — VERSION GRATUITE V2.

- Écriture du dialogue : Google Gemini API
- Synthèse vocale : edge-tts
- Tendance vocale : ROGER=Strict/Rapide, ALINE=Paniquée/Chaleureuse
"""

import asyncio
import io
import json
import os
import re
import uuid
from pathlib import Path

import edge_tts
import google.generativeai as genai
from pydub import AudioSegment

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
GEMINI_MODEL = "gemini-2.5-flash"

# Groq — fallback automatique quand Gemini atteint son quota (429).
_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

DOSSIER_AUDIO = Path("audio_generes")
DOSSIER_AUDIO.mkdir(exist_ok=True)

# ---------------------------------------------------------
# VOIX SIGNATURES — fixes, identité sonore de l'application.
# VERSION 2.0 : ROGER STRICT, ALINE EXPRESSIVE
# ---------------------------------------------------------

VOIX_ALINE = "fr-FR-DeniseNeural" # Femme : chaleureuse, peut paniquer
VOIX_ROGER = "fr-FR-HenriNeural" # Homme : Strict, grave, rapide

VOIX_FEMME = [VOIX_ALINE]
VOIX_HOMME = [VOIX_ROGER]
VOIX_NEUTRE = [VOIX_ALINE, VOIX_ROGER]

MOTS_CLES_FEMME = {"elle", "femme", "fille", "elle1", "elle2", "sarah"}
MOTS_CLES_HOMME = {"lui", "homme", "garçon", "garcon", "lui1", "lui2", "alex", "frere"}

DEBIT_PAROLE_MOTS_PAR_MIN = 150

GENRES = {
    "love": "romantique, avec de la tension et de l'émotion",
    "drama": "dramatique, intense, avec un conflit émotionnel fort",
    "comedy": "comique, rythmé, avec des répliques punchy",
    "horror": "angoissant, tendu, avec une montée de suspense",
    "business": "professionnel, incisif, enjeu de négociation",
}

CIBLES_LOVE = {
    "pour_elle": (
        "Dialogue romantique et rêveur, façon scène de film. Elle commence sur "
        "la défensive : réponses courtes, fermées. Lui est charmant, confiant et "
        "audacieux — il insiste avec assurance. "
        "Termine sur le moment précis où sa garde tombe."
    ),
    "pour_lui": (
        "Dialogue de drague courte et percutante. Elle teste, lui répond avec "
        "assurance à chaque tentative de le décourager, jusqu'à ce qu'elle "
        "craque. Ton confiant, drôle, jamais lourd."
    ),
    "mixte": (
        "Dialogue romantique équilibré entre tension et humour. Elle commence "
        "fermée et distante, lui est déterminé et persévère avec charme."
    ),
}

_GARDE_FOU_LOVE = (
    " Important : son insistance à lui reste toujours charmante et légère — "
    "jamais lourde, jamais irrespectueuse."
)

# ---------------------------------------------------------
# 1. GÉNÉRATION DU DIALOGUE PAR L'IA
# ---------------------------------------------------------

def _construire_prompt(genre: str, duree_secondes: int,
                        nb_personnages: int, cible: str) -> tuple[str, str]:
    nb_mots_cible = int((duree_secondes / 60) * DEBIT_PAROLE_MOTS_PAR_MIN)

    consigne_cible = ""
    if genre == "love":
        consigne_cible = (
            "\n\nConsigne de ciblage : "
            + CIBLES_LOVE.get(cible, CIBLES_LOVE["mixte"])
            + _GARDE_FOU_LOVE
        )

    if genre == "love" and nb_personnages == 2:
        noms = ["Elle", "Lui"]
    else:
        noms = [f"Personnage{i+1}" for i in range(nb_personnages)]

    prompt_systeme = f"""Tu es scénariste, spécialisé dans l'écriture de dialogues courts pour les réseaux sociaux.

Règles impératives :
- Ton du dialogue : {GENRES[genre]}
- Personnages exacts à utiliser : {', '.join(noms)}
- Longueur cible : environ {nb_mots_cible} mots au total (~{duree_secondes}s à l'oral)
- Phrases courtes, rythme dynamique
- Accroche immédiate dès la première réplique
- Chute marquante à la fin{consigne_cible}

Pour CHAQUE réplique, indique aussi :
- "genre" : "femme", "homme" ou "neutre"
- "ton" : une courte indication de jeu. Ex: "paniquée", "strict", "sûr de lui", "chuchote"

Ajoute aussi une clé "legende_suggeree".

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, de la forme :
{{
  "dialogue": [
    {{"personnage": "Elle", "genre": "femme", "ligne": "...", "ton": "chuchote, paniquée"}},
    {{"personnage": "Lui", "genre": "homme", "ligne": "...", "ton": "strict"}}
  ],
  "legende_suggeree": "..."
}}
"""
    return prompt_systeme, "Écris le dialogue maintenant."

def _generer_via_gemini(prompt_systeme: str, message: str) -> dict:
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=prompt_systeme,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.9,
        },
    )
    response = model.generate_content(message)
    return json.loads(response.text)

def _generer_via_groq(prompt_systeme: str, message: str) -> dict:
    from openai import OpenAI as GroqClient
    client = GroqClient(
        api_key=_GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    reponse = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": prompt_systeme},
            {"role": "user", "content": message},
        ],
        temperature=0.9,
        response_format={"type": "json_object"},
    )
    texte = reponse.choices[0].message.content
    texte = texte.replace("```json", "").replace("```", "").strip()
    return json.loads(texte)

def generer_dialogue_ia(genre: str, duree_secondes: int, nb_personnages: int,
                         cible: str = "mixte") -> dict:
    if genre not in GENRES:
        raise ValueError(f"Genre inconnu. Choix possibles : {list(GENRES.keys())}")

    prompt_systeme, message = _construire_prompt(genre, duree_secondes, nb_personnages, cible)

    try:
        return _generer_via_gemini(prompt_systeme, message)
    except Exception as e:
        if "429" in str(e) and _GROQ_API_KEY:
            pass
        else:
            raise
    return _generer_via_groq(prompt_systeme, message)

# ---------------------------------------------------------
# 2. PARSING D'UN SCRIPT ÉCRIT MANUELLEMENT
# ---------------------------------------------------------

LIGNE_DIALOGUE_REGEX = re.compile(
    r"^\s*(?P<perso>[^():\n]{1,30}?)\s*(\((?P<ton>[^)]*)\))?\s*:\s*(?P<ligne>.+?)\s*$"
)

def _deviner_genre(nom_personnage: str) -> str:
    nom = nom_personnage.strip().lower()
    if nom in MOTS_CLES_FEMME:
        return "femme"
    if nom in MOTS_CLES_HOMME:
        return "homme"
    return "neutre"

def parser_script_manuel(texte: str) -> list[dict]:
    dialogue = []
    for ligne_brute in texte.splitlines():
        if not ligne_brute.strip():
            continue
        match = LIGNE_DIALOGUE_REGEX.match(ligne_brute)
        if not match:
            continue

        perso = match.group("perso").strip()
        if any(c in perso for c in "🎬🎥🎞️") or len(perso) == 0:
            continue

        ton = (match.group("ton") or "").strip()
        ligne_texte = match.group("ligne").strip()
        ligne_texte = ligne_texte.strip("«»\"“” ").strip()

        if not ligne_texte:
            continue

        dialogue.append({
            "personnage": perso,
            "genre": _deviner_genre(perso),
            "ligne": ligne_texte,
            "ton": ton,
        })

    return dialogue

# ---------------------------------------------------------
# 3. ATTRIBUTION DES VOIX
# ---------------------------------------------------------

def attribuer_voix(dialogue: list[dict]) -> dict:
    compteurs = {"femme": 0, "homme": 0, "neutre": 0}
    banques = {"femme": VOIX_FEMME, "homme": VOIX_HOMME, "neutre": VOIX_NEUTRE}
    mapping = {}

    for replique in dialogue:
        perso = replique["personnage"]
        genre = replique.get("genre", "neutre")
        if genre not in banques:
            genre = "neutre"

        if perso not in mapping:
            banque = banques[genre]
            index = compteurs[genre] % len(banque)
            mapping[perso] = banque[index]
            compteurs[genre] += 1

    return mapping

# ---------------------------------------------------------
# 4. TON -> PROSODIE V2 : STRICT + PANIQUE
# ---------------------------------------------------------

_MOTS_CHUCHOTE = {"chuchote", "murmure", "bas", "doucement", "à voix basse", "souffle"}
_MOTS_CRIE = {"crie", "hurle", "fort", "colère", "énervé", "en colère"}

_MOTS_CONFIANT = {
    "sûr de lui", "confiant", "dominant", "assuré", "posé", "déterminé",
    "ferme", "autoritaire", "strict", "sec", "direct"
}

_MOTS_RIT = {"rit", "amusé", "joyeux", "en riant", "éclate de rire"}
_MOTS_TRISTE = {"triste", "pleure", "déçu", "abattu"}
_MOTS_PANIQUE = {"paniquée", "peur", "stressée", "affolée", "urgent"}

def _ton_vers_prosodie(ton: str, genre: str = "neutre") -> tuple[str, str, str]:
    """Retourne (rate, volume, pitch) pour edge-tts."""
    ton_lower = (ton or "").lower()

    # 1. CHUCHOTE
    if any(m in ton_lower for m in _MOTS_CHUCHOTE):
        if genre == "homme":
            return "-5%", "-10%", "-8Hz" # Strict même en chuchotant
        return "-20%", "-30%", "+5Hz" # Femme chuchotée et rapide

    # 2. PANIQUE - NOUVEAU POUR ALINE
    if any(m in ton_lower for m in _MOTS_PANIQUE):
        if genre == "femme":
            # Rapide, aigu, volume monte
            return "+25%", "+10%", "+20Hz"
        return "+10%", "+15%", "+5Hz"

    # 3. CRIE
    if any(m in ton_lower for m in _MOTS_CRIE):
        if genre == "homme":
            return "+15%", "+25%", "-2Hz" # Ordre sec
        return "+20%", "+30%", "+25Hz"

    # 4. STRICT/CONFIANT - NOUVEAU POUR ROGER
    if any(m in ton_lower for m in _MOTS_CONFIANT):
        if genre == "homme":
            # STRICT ET RAPIDE: +18% vitesse, grave, +10 volume
            return "+18%", "+10%", "-12Hz"
        else:
            return "-5%", "+5%", "-5Hz"

    # 5. RIT
    if any(m in ton_lower for m in _MOTS_RIT):
        if genre == "homme":
            return "+5%", "+5%", "-5Hz"
        return "+10%", "+5%", "+15Hz"

    # 6. TRISTE
    if any(m in ton_lower for m in _MOTS_TRISTE):
        if genre == "homme":
            return "-5%", "-5%", "-8Hz"
        return "-15%", "-5%", "-15Hz"

    # DÉFAUT
    if genre == "homme":
        # Par défaut Roger est strict et rapide
        return "+12%", "+8%", "-10Hz"

    if genre == "femme":
        # Par défaut Aline est normale
        return "+0%", "+0%", "+0Hz"

    return "+0%", "+0%", "+0Hz"

# ---------------------------------------------------------
# 5. EFFET "VOIX STRICTE" - SEC SANS REVERB
# ---------------------------------------------------------

def _appliquer_voix_stricte(segment: AudioSegment) -> AudioSegment:
    """
    Effet "Voix Stricte" pour ROGER:
    - +3dB pour l’autorité
    - High-pass pour enlever le "brouillon" et rester net
    - Aucune reverb
    """
    segment = segment + 3
    segment = segment.high_pass_filter(120)
    segment = segment.compress_dynamic_range(threshold=-20.0, ratio=4.0)
    return segment

# ---------------------------------------------------------
# 6. SYNTHÈSE VOCALE + FUSION AUDIO
# ---------------------------------------------------------

async def _generer_audio_ligne(texte: str, voix: str, ton: str = "",
                               genre: str = "neutre") -> AudioSegment:
    rate, volume, pitch = _ton_vers_prosodie(ton, genre)
    communicate = edge_tts.Communicate(texte, voix, rate=rate, volume=volume, pitch=pitch)

    audio_bytes = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])

    segment = AudioSegment.from_file(io.BytesIO(bytes(audio_bytes)), format="mp3")

    # Appliquer l'effet "voix stricte" uniquement sur la voix masculine
    if genre == "homme":
        segment = _appliquer_voix_stricte(segment)

    return segment

async def generer_audio_dialogue(dialogue: list[dict], mapping_voix: dict,
                                  pause_base_ms: int = 400) -> AudioSegment:
    audio_final = AudioSegment.empty()

    for i, replique in enumerate(dialogue):
        voix = mapping_voix[replique["personnage"]]
        genre = replique.get("genre", "neutre")
        segment = await _generer_audio_ligne(
            replique["ligne"], voix, replique.get("ton", ""), genre
        )
        audio_final += segment

        if i < len(dialogue) - 1:
            # PAUSE COURTE APRÈS L'HOMME STRICT
            if genre == "homme":
                pause_ms = pause_base_ms - 150 # ~250ms
            else:
                pause_ms = pause_base_ms # ~400ms
            audio_final += AudioSegment.silent(duration=pause_ms)

    return audio_final

async def exporter_audio(dialogue: list[dict], format_sortie: str = "mp3") -> str:
    mapping_voix = attribuer_voix(dialogue)
    audio_final = await generer_audio_dialogue(dialogue, mapping_voix)

    nom_fichier = f"{uuid.uuid4().hex}.{format_sortie}"
    chemin = DOSSIER_AUDIO / nom_fichier
    audio_final.export(chemin, format=format_sortie)

    return nom_fichier
