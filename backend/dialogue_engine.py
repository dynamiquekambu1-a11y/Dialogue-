"""
Moteur du générateur de dialogues audio — VERSION GRATUITE.

- Écriture du dialogue : Google Gemini API (plan gratuit, sans carte bancaire)
- Synthèse vocale : edge-tts (voix Microsoft Edge, gratuit et illimité)

Gère : génération IA du script, parsing d'un script manuel,
attribution des voix par genre, synthèse vocale, fusion audio.
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
GEMINI_MODEL = "gemini-2.5-flash"  # modèle rapide du plan gratuit ; ajustable si besoin

DOSSIER_AUDIO = Path("audio_generes")
DOSSIER_AUDIO.mkdir(exist_ok=True)

# ---------------------------------------------------------
# VOIX — voix françaises edge-tts, réparties par genre perçu
# ---------------------------------------------------------

VOIX_FEMME = ["fr-FR-DeniseNeural", "fr-FR-EloiseNeural", "fr-CA-SylvieNeural"]
VOIX_HOMME = ["fr-FR-HenriNeural", "fr-CA-JeanNeural", "fr-BE-GerardNeural"]
VOIX_NEUTRE = ["fr-FR-DeniseNeural", "fr-FR-HenriNeural"]

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
# 1. GÉNÉRATION DU DIALOGUE PAR L'IA (Gemini)
# ---------------------------------------------------------

def generer_dialogue_ia(genre: str, duree_secondes: int, nb_personnages: int,
                         cible: str = "mixte") -> dict:
    """
    Génère un dialogue via Gemini.
    Retourne {"dialogue": [...], "legende_suggeree": "..."}
    Chaque réplique : {"personnage", "genre" (homme/femme/neutre), "ligne", "ton"}
    """
    if genre not in GENRES:
        raise ValueError(f"Genre inconnu. Choix possibles : {list(GENRES.keys())}")

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
    {{"personnage": "Lui", "genre": "homme", "ligne": "...", "ton": "avec un sourire"}}
  ],
  "legende_suggeree": "..."
}}
"""

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=prompt_systeme,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.9,
        },
    )
    response = model.generate_content("Écris le dialogue maintenant.")
    return json.loads(response.text)


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

_MOTS_CHUCHOTE = {"chuchote", "murmure", "bas", "doucement", "à voix basse"}
_MOTS_CRIE = {"crie", "hurle", "fort", "colère", "énervé", "en colère"}
_MOTS_CONFIANT = {
    "sûr de lui", "sourire en coin", "confiant", "dominant", "assuré",
    "arrogant", "posé", "déterminé", "ferme", "autoritaire", "calme et sûr",
}
_MOTS_RIT = {"rit", "amusé", "joyeux", "en riant", "éclate de rire"}
_MOTS_TRISTE = {"triste", "pleure", "déçu", "abattu"}


def _ton_vers_prosodie(ton: str) -> tuple[str, str, str]:
    """Retourne (rate, volume, pitch) au format attendu par edge-tts, ex: ('+10%', '-20%', '+5Hz').

    L'ordre des tests compte : "confiant" est vérifié avant "rit", pour qu'une
    indication comme "sourire en coin" (smirk assuré) ne soit pas confondue
    avec "rit" (rire léger) — les deux appellent des voix très différentes.
    """
    ton_lower = (ton or "").lower()

    if any(m in ton_lower for m in _MOTS_CHUCHOTE):
        return "-10%", "-30%", "+0Hz"
    if any(m in ton_lower for m in _MOTS_CRIE):
        return "+10%", "+20%", "+20Hz"
    if any(m in ton_lower for m in _MOTS_CONFIANT):
        # Débit ralenti et légèrement posé, voix plus grave, volume ferme :
        # rendu direct et assuré plutôt que "lu" ou hésitant.
        return "-8%", "+8%", "-10Hz"
    if any(m in ton_lower for m in _MOTS_RIT):
        return "+5%", "+0%", "+15Hz"
    if any(m in ton_lower for m in _MOTS_TRISTE):
        return "-10%", "+0%", "-15Hz"
    return "+0%", "+0%", "+0Hz"


# ---------------------------------------------------------
# 5. SYNTHÈSE VOCALE (edge-tts) + FUSION AUDIO
# ---------------------------------------------------------

async def _generer_audio_ligne(texte: str, voix: str, ton: str = "") -> AudioSegment:
    rate, volume, pitch = _ton_vers_prosodie(ton)
    communicate = edge_tts.Communicate(texte, voix, rate=rate, volume=volume, pitch=pitch)

    audio_bytes = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])

    return AudioSegment.from_file(io.BytesIO(bytes(audio_bytes)), format="mp3")


async def generer_audio_dialogue(dialogue: list[dict], mapping_voix: dict,
                                  pause_entre_repliques_ms: int = 350) -> AudioSegment:
    audio_final = AudioSegment.empty()
    pause = AudioSegment.silent(duration=pause_entre_repliques_ms)

    for i, replique in enumerate(dialogue):
        voix = mapping_voix[replique["personnage"]]
        segment = await _generer_audio_ligne(replique["ligne"], voix, replique.get("ton", ""))
        audio_final += segment
        if i < len(dialogue) - 1:
            audio_final += pause

    return audio_final


async def exporter_audio(dialogue: list[dict], format_sortie: str = "mp3") -> str:
    """
    Pipeline complet à partir d'un dialogue déjà structuré (issu de l'IA ou du parsing manuel).
    Retourne le nom du fichier généré (dans DOSSIER_AUDIO).
    """
    mapping_voix = attribuer_voix(dialogue)
    audio_final = await generer_audio_dialogue(dialogue, mapping_voix)

    nom_fichier = f"{uuid.uuid4().hex}.{format_sortie}"
    chemin = DOSSIER_AUDIO / nom_fichier
    audio_final.export(chemin, format=format_sortie)

    return nom_fichier
