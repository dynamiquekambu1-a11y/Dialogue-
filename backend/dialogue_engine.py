"""
Moteur du générateur de dialogues audio.

- Écriture du dialogue : Google Gemini (fallback Groq)
- Synthèse vocale GRATUIT : edge-tts (Microsoft Edge, illimité)
- Synthèse vocale PREMIUM : ElevenLabs (qualité cinéma)
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
import httpx
from pydub import AudioSegment

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
GEMINI_MODEL = "gemini-3.5-flash"

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# ---------------------------------------------------------
# ELEVENLABS — voix premium
# ---------------------------------------------------------
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ROGER = "2AGrjHJgmTgUqzy68M9W"   # voix masculine premium
ELEVENLABS_VOICE_ALINE = "i6ke7jvmGEVUyV4zjSaT"   # voix féminine premium
ELEVENLABS_MODEL = "eleven_multilingual_v2"

DOSSIER_AUDIO = Path("audio_generes")
DOSSIER_AUDIO.mkdir(exist_ok=True)

# ---------------------------------------------------------
# VOIX SIGNATURES
#
# GRATUIT  → edge-tts (Denise + Remy)
# PREMIUM  → ElevenLabs (Aline + Roger IDs ci-dessus)
# ---------------------------------------------------------

VOIX_ALINE = "fr-FR-DeniseNeural"
VOIX_ROGER = "fr-FR-RemyMultilingualNeural"

VOIX_FEMME  = [VOIX_ALINE]
VOIX_HOMME  = [VOIX_ROGER]
VOIX_NEUTRE = [VOIX_ALINE, VOIX_ROGER]

MOTS_CLES_FEMME = {"elle", "femme", "fille", "elle1", "elle2"}
MOTS_CLES_HOMME = {"lui", "homme", "garçon", "garcon", "lui1", "lui2"}

DEBIT_PAROLE_MOTS_PAR_MIN = 150

DOSSIER_AUDIO = Path("audio_generes")
DOSSIER_AUDIO.mkdir(exist_ok=True)

# ---------------------------------------------------------
# VOIX SIGNATURES — fixes, jamais changeantes.
# C'est l'identité sonore de l'application.
#
#   ALINE — fr-FR-DeniseNeural
#     Voix féminine : naturelle, chaleureuse, légèrement intense.
#     Elle reste Aline quel que soit le personnage féminin.
#
#   ROGER — fr-FR-HenriNeural
#     Voix masculine : autoritaire, ancrée, grave.
#     Réglages "Capitaine Calme" appliqués par dessus pour le rendu séducteur.
#     Il reste Roger quel que soit le personnage masculin.
# ---------------------------------------------------------

VOIX_ALINE = "fr-FR-DeniseNeural"   # signature féminine
VOIX_ROGER = "fr-FR-HenriNeural"    # signature masculine

# Compatibilité avec le reste du code (attribuer_voix utilise des listes)
VOIX_FEMME  = [VOIX_ALINE]
VOIX_HOMME  = [VOIX_ROGER]
VOIX_NEUTRE = [VOIX_ALINE, VOIX_ROGER]

MOTS_CLES_FEMME = {"elle", "femme", "fille", "elle1", "elle2"}
MOTS_CLES_HOMME = {"lui", "homme", "garçon", "garcon", "lui1", "lui2"}

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
        "la défensive : réponses courtes, fermées, elle essaie de garder ses "
        "distances ou de le repousser poliment. Lui est charmant, confiant et "
        "audacieux — il ne se laisse pas décourager par ses réponses fermées "
        "et insiste avec assurance jusqu'à faire craquer sa résistance. "
        "Termine sur le moment précis où sa garde tombe (un silence qui en "
        "dit long, une réplique qui la trahit malgré elle) — une chute "
        "mémorable, citable en légende TikTok."
    ),
    "pour_lui": (
        "Dialogue de drague courte et percutante, répliques brèves façon "
        "battle de charme. Elle envoie des réponses fermées ou des piques "
        "pour le tester et le repousser ; lui ne recule jamais et répond avec "
        "assurance à chaque tentative de le décourager, jusqu'à ce qu'elle "
        "craque. Punchlines directement réutilisables comme réponse à un "
        "commentaire ou légende TikTok. Ton confiant, drôle, jamais lourd."
    ),
    "mixte": (
        "Dialogue romantique équilibré entre tension et humour. Elle commence "
        "fermée et distante, lui est déterminé et persévère avec charme, "
        "jusqu'à ce que sa résistance cède. Termine sur une réplique finale "
        "marquante, accessible à un public large."
    ),
}

# Garde-fou commun à toutes les cibles "love" : la persévérance doit rester
# charmante, jamais insistante au point d'être malaisante ou irrespectueuse.
_GARDE_FOU_LOVE = (
    " Important : son insistance à lui reste toujours charmante et légère — "
    "jamais lourde, jamais irrespectueuse, jamais au point de la mettre mal "
    "à l'aise. Elle garde le contrôle de la situation à tout moment ; c'est "
    "son propre trouble qui la fait craquer, pas une pression extérieure."
)


# ---------------------------------------------------------
# 1. GÉNÉRATION DU DIALOGUE PAR L'IA (Gemini avec fallback Groq)
# ---------------------------------------------------------

def _construire_prompt(genre: str, duree_secondes: int,
                        nb_personnages: int, cible: str) -> tuple[str, str]:
    """Construit le prompt système et le message utilisateur. Réutilisé par Gemini et Groq."""
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

    prompt_systeme = f"""Tu es scénariste, spécialisé dans l'écriture de dialogues courts pour les réseaux sociaux (TikTok, Reels, Shorts).

Règles impératives :
- Ton du dialogue : {GENRES[genre]}
- Personnages exacts à utiliser : {', '.join(noms)}
- Longueur cible : environ {nb_mots_cible} mots au total (~{duree_secondes}s à l'oral)
- Phrases courtes, rythme dynamique
- Accroche immédiate dès la première réplique
- Chute marquante à la fin{consigne_cible}

Pour CHAQUE réplique, indique aussi :
- "genre" : "femme", "homme" ou "neutre" selon le personnage qui parle
- "ton" : une courte indication de jeu qui décrit COMMENT c'est dit, ne doit jamais être lu à voix haute. Pour un personnage masculin confiant, dominant ou séducteur, utilise de préférence des mots comme "sûr de lui", "posé", "ferme", "assuré" ou "dominant" plutôt que "avec un sourire" — ça change vraiment le rendu vocal.

Ajoute aussi une clé "legende_suggeree" : une phrase courte et accrocheuse (tirée ou inspirée de la chute du dialogue) utilisable comme légende TikTok.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, de la forme :
{{
  "dialogue": [
    {{"personnage": "Elle", "genre": "femme", "ligne": "...", "ton": "chuchote, paniquée"}},
    {{"personnage": "Lui", "genre": "homme", "ligne": "...", "ton": "sûr de lui"}}
  ],
  "legende_suggeree": "..."
}}
"""
    return prompt_systeme, "Écris le dialogue maintenant."


def _generer_via_gemini(prompt_systeme: str, message: str) -> dict:
    """Génère un dialogue via Gemini."""
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
    """Génère un dialogue via Groq (fallback quand Gemini est à court de quota)."""
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
    """
    Génère un dialogue via Gemini. Si Gemini dépasse son quota (erreur 429),
    bascule automatiquement sur Groq — invisible pour l'utilisateur.
    """
    if genre not in GENRES:
        raise ValueError(f"Genre inconnu. Choix possibles : {list(GENRES.keys())}")

    prompt_systeme, message = _construire_prompt(genre, duree_secondes, nb_personnages, cible)

    # Tentative 1 : Gemini
    try:
        return _generer_via_gemini(prompt_systeme, message)
    except Exception as e:
        # Si c'est un quota Gemini (429) ET que Groq est configuré → on bascule
        if "429" in str(e) and _GROQ_API_KEY:
            pass  # on continue vers Groq
        else:
            raise  # autre erreur → on la remonte normalement

    # Tentative 2 : Groq (fallback automatique)
    return _generer_via_groq(prompt_systeme, message)


# ---------------------------------------------------------
# 2. PARSING D'UN SCRIPT ÉCRIT MANUELLEMENT PAR L'UTILISATEUR
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
    """
    Parse un script collé par l'utilisateur, au format :
        Elle (chuchote, paniquée) : « Attends... »
        Lui (avec un sourire) : « Non. »

    Les lignes qui ne correspondent pas au format (ex: "🎬 Scène : ...")
    sont ignorées automatiquement (considérées comme indications de mise en scène).
    """
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
# 3. ATTRIBUTION DES VOIX (par personnage unique, selon le genre)
# ---------------------------------------------------------

def attribuer_voix(dialogue: list[dict]) -> dict:
    """
    Associe une voix distincte à chaque personnage unique, piochée dans la
    banque de voix correspondant à son genre déclaré (femme/homme/neutre).
    """
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
# 4. TON -> PROSODIE (edge-tts n'a pas d'"instructions" comme OpenAI,
#    on approxime donc l'émotion via débit/volume/hauteur de voix)
# ---------------------------------------------------------

_MOTS_CHUCHOTE = {"chuchote", "murmure", "bas", "doucement", "à voix basse", "souffle"}
_MOTS_CRIE = {"crie", "hurle", "fort", "colère", "énervé", "en colère"}

# "La Voix du Capitaine Calme" : bas, posé, stable, intentionnel.
# Chaque mot a du poids. On ne convainc pas — on constate.
_MOTS_CONFIANT = {
    "sûr de lui", "sourire en coin", "confiant", "dominant", "assuré",
    "arrogant", "posé", "déterminé", "ferme", "autoritaire", "calme et sûr",
    "séducteur", "séduisant", "regard direct", "imperturbable", "tranquille",
    "murmure séducteur", "voix grave", "calme absolu",
}

_MOTS_RIT = {"rit", "amusé", "joyeux", "en riant", "éclate de rire"}
_MOTS_TRISTE = {"triste", "pleure", "déçu", "abattu"}


def _ton_vers_prosodie(ton: str, genre: str = "neutre") -> tuple[str, str, str]:
    ton_lower = (ton or "").lower()

    if any(m in ton_lower for m in _MOTS_CHUCHOTE):
        if genre == "homme":
            return "-10%", "-10%", "-12Hz"
        return "-15%", "-35%", "+0Hz"

    if any(m in ton_lower for m in _MOTS_CRIE):
        if genre == "homme":
            return "+5%", "+15%", "-5Hz"
        return "+15%", "+25%", "+20Hz"

    if any(m in ton_lower for m in _MOTS_CONFIANT):
        if genre == "homme":
            return "-5%", "+8%", "-12Hz"
        else:
            return "-10%", "+8%", "-8Hz"

    if any(m in ton_lower for m in _MOTS_RIT):
        if genre == "homme":
            return "+0%", "+5%", "-10Hz"
        return "+5%", "+0%", "+15Hz"

    if any(m in ton_lower for m in _MOTS_TRISTE):
        if genre == "homme":
            return "-5%", "-5%", "-12Hz"
        return "-10%", "+0%", "-15Hz"

    # Défaut homme : grave et direct, débit normal
    if genre == "homme":
        return "+0%", "+5%", "-10Hz"

    return "+0%", "+0%", "+0Hz"


# ---------------------------------------------------------
# 5. SYNTHÈSE VOCALE — GRATUIT (edge-tts) + PREMIUM (ElevenLabs)
# ---------------------------------------------------------

async def _synthese_edge_tts(texte: str, voix: str, ton: str,
                              genre: str) -> AudioSegment:
    """Synthèse gratuite via edge-tts."""
    rate, volume, pitch = _ton_vers_prosodie(ton, genre)
    communicate = edge_tts.Communicate(texte, voix, rate=rate, volume=volume, pitch=pitch)
    audio_bytes = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])
    return AudioSegment.from_file(io.BytesIO(bytes(audio_bytes)), format="mp3")


async def _synthese_elevenlabs(texte: str, voice_id: str, genre: str) -> AudioSegment:
    """Synthèse premium via ElevenLabs — qualité cinéma."""
    # Réglages de stabilité/similarité adaptés au Capitaine Calme
    stability     = 0.75 if genre == "homme" else 0.60
    similarity    = 0.85
    style         = 0.35 if genre == "homme" else 0.25  # légère expressivité

    payload = {
        "text": texte,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
            "style": style,
            "use_speaker_boost": True,
        },
    }
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()

    return AudioSegment.from_file(io.BytesIO(response.content), format="mp3")


async def _generer_audio_ligne(texte: str, voix_edge: str, ton: str = "",
                                genre: str = "neutre",
                                premium: bool = False) -> AudioSegment:
    if premium and ELEVENLABS_API_KEY:
        voice_id = ELEVENLABS_VOICE_ROGER if genre == "homme" else ELEVENLABS_VOICE_ALINE
        return await _synthese_elevenlabs(texte, voice_id, genre)
    else:
        return await _synthese_edge_tts(texte, voix_edge, ton, genre)


async def generer_audio_dialogue(dialogue: list[dict], mapping_voix: dict,
                                  pause_base_ms: int = 350,
                                  premium: bool = False) -> AudioSegment:
    audio_final = AudioSegment.empty()

    for i, replique in enumerate(dialogue):
        voix = mapping_voix[replique["personnage"]]
        genre = replique.get("genre", "neutre")
        segment = await _generer_audio_ligne(
            replique["ligne"], voix, replique.get("ton", ""), genre, premium
        )
        audio_final += segment

        if i < len(dialogue) - 1:
            pause_ms = pause_base_ms + 200 if genre == "homme" else pause_base_ms
            audio_final += AudioSegment.silent(duration=pause_ms)

    return audio_final


async def exporter_audio(dialogue: list[dict], format_sortie: str = "mp3",
                          premium: bool = False) -> str:
    mapping_voix = attribuer_voix(dialogue)
    audio_final = await generer_audio_dialogue(dialogue, mapping_voix,
                                                premium=premium)
    nom_fichier = f"{uuid.uuid4().hex}.{format_sortie}"
    chemin = DOSSIER_AUDIO / nom_fichier
    audio_final.export(chemin, format=format_sortie)
    return nom_fichier
