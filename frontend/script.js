
const etat = {
  mode: "ia",
  genre: "love",
  cible: "mixte",
  duree: 60,
  nbPersonnages: 2,
  format: "mp3",
  dialogue: [],
  legende: null,
};

// ---------- Clé admin (accès illimité pour toi, le créateur du site) ----------
// Visite ton site une fois avec ?admin=TA_CLE dans l'adresse, elle est ensuite
// mémorisée dans ce navigateur — plus besoin de la remettre à chaque visite.

const parametresURL = new URLSearchParams(window.location.search);
const cleAdminDansURL = parametresURL.get("admin");
if (cleAdminDansURL) {
  localStorage.setItem("cle_admin", cleAdminDansURL);
}
const cleAdmin = localStorage.getItem("cle_admin") || "";

function enTetesAvecAdmin(enTetesSupplementaires = {}) {
  const enTetes = { ...enTetesSupplementaires };
  if (cleAdmin) enTetes["X-Admin-Key"] = cleAdmin;
  return enTetes;
}

// ---------- Sélecteurs ----------
const panelPreview = document.getElementById("panel-preview");
const panelAudio = document.getElementById("panel-audio");
const chargement = document.getElementById("chargement");
const chargementTexte = document.getElementById("chargement-texte");
const erreurBox = document.getElementById("erreur");
const cibleGroup = document.getElementById("cible-group");

// ---------- Utilitaires UI ----------

function afficherErreur(message) {
  erreurBox.textContent = message;
  erreurBox.classList.remove("hidden");
  setTimeout(() => erreurBox.classList.add("hidden"), 6000);
}

function afficherChargement(texte) {
  chargementTexte.textContent = texte;
  chargement.classList.remove("hidden");
}

function masquerChargement() {
  chargement.classList.add("hidden");
}

function activerChip(groupe, attribut, valeur) {
  document.querySelectorAll(`#${groupe} .chip`).forEach((btn) => {
    btn.classList.toggle("active", btn.dataset[attribut] === String(valeur));
  });
}

// ---------- Quota ----------

const quotaInfo = document.getElementById("quota-info");
const btnGenererIA = document.getElementById("btn-generer-ia");

function afficherQuota(data) {
  if (data.premium) {
    quotaInfo.textContent = "Compte premium — générations illimitées.";
    quotaInfo.classList.remove("quota-epuise");
    btnGenererIA.disabled = false;
    return;
  }

  quotaInfo.textContent = `${data.restant} / ${data.limite} générations gratuites restantes cette semaine.`;

  if (data.restant <= 0) {
    quotaInfo.textContent += " Quota atteint — le mode premium arrive bientôt.";
    quotaInfo.classList.add("quota-epuise");
    btnGenererIA.disabled = true;
  } else {
    quotaInfo.classList.remove("quota-epuise");
    btnGenererIA.disabled = false;
  }
}

async function chargerQuota() {
  try {
    const reponse = await fetch("/api/quota", { headers: enTetesAvecAdmin() });
    const data = await reponse.json();
    afficherQuota(data);
  } catch (err) {
    // Silencieux : l'affichage du quota n'est pas bloquant pour l'usage du site
    console.warn("Impossible de charger le quota :", err);
  }
}

chargerQuota();

// ---------- Toggle de mode ----------

document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    etat.mode = btn.dataset.mode;
    document.querySelectorAll(".mode-btn").forEach((b) => {
      b.classList.toggle("active", b === btn);
      b.setAttribute("aria-selected", b === btn ? "true" : "false");
    });
    document.getElementById("mode-ia").classList.toggle("hidden", etat.mode !== "ia");
    document.getElementById("mode-manuel").classList.toggle("hidden", etat.mode !== "manuel");
  });
});

// ---------- Chips genre ----------

document.querySelectorAll("#genre-chips .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    etat.genre = btn.dataset.genre;
    activerChip("genre-chips", "genre", etat.genre);
    cibleGroup.classList.toggle("hidden", etat.genre !== "love");
  });
});

document.querySelectorAll("#cible-chips .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    etat.cible = btn.dataset.cible;
    activerChip("cible-chips", "cible", etat.cible);
  });
});

document.querySelectorAll("#duree-chips .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    etat.duree = parseInt(btn.dataset.duree, 10);
    activerChip("duree-chips", "duree", etat.duree);
  });
});

document.querySelectorAll("#perso-chips .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    etat.nbPersonnages = parseInt(btn.dataset.nb, 10);
    activerChip("perso-chips", "nb", etat.nbPersonnages);
  });
});

document.querySelectorAll("#format-chips .chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    etat.format = btn.dataset.format;
    activerChip("format-chips", "format", etat.format);
  });
});

// ---------- Étape 1 : générer / parser le dialogue ----------

async function genererDialogueIA() {
  afficherChargement("Écriture du dialogue en cours…");
  try {
    const reponse = await fetch("/api/generer-dialogue", {
      method: "POST",
      headers: enTetesAvecAdmin({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        mode: "ia",
        genre: etat.genre,
        duree_secondes: etat.duree,
        nb_personnages: etat.nbPersonnages,
        cible: etat.cible,
      }),
    });

    if (reponse.status === 429) {
      const erreur = await reponse.json();
      afficherErreur(erreur.detail);
      chargerQuota(); // resynchronise l'affichage (désactive le bouton)
      return;
    }
    if (!reponse.ok) throw new Error((await reponse.json()).detail || "Erreur serveur");

    const data = await reponse.json();
    etat.dialogue = data.dialogue;
    etat.legende = data.legende_suggeree;
    afficherApercu();

    chargerQuota(); // resynchronise l'affichage avec l'état réel côté serveur
  } catch (err) {
    afficherErreur(err.message);
  } finally {
    masquerChargement();
  }
}

async function analyserScriptManuel() {
  const texte = document.getElementById("script-manuel").value;
  if (!texte.trim()) {
    afficherErreur("Colle d'abord ton script.");
    return;
  }
  afficherChargement("Analyse du script…");
  try {
    const reponse = await fetch("/api/generer-dialogue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "manuel", script_manuel: texte }),
    });
    if (!reponse.ok) throw new Error((await reponse.json()).detail || "Erreur serveur");
    const data = await reponse.json();
    etat.dialogue = data.dialogue;
    etat.legende = data.legende_suggeree;
    afficherApercu();
  } catch (err) {
    afficherErreur(err.message);
  } finally {
    masquerChargement();
  }
}

document.getElementById("btn-generer-ia").addEventListener("click", genererDialogueIA);
document.getElementById("btn-generer-manuel").addEventListener("click", analyserScriptManuel);

// ---------- Étape 2 : aperçu éditable ----------

function afficherApercu() {
  const conteneur = document.getElementById("dialogue-liste");
  conteneur.innerHTML = "";

  const legendeBox = document.getElementById("legende-suggeree");
  if (etat.legende) {
    document.getElementById("legende-texte").textContent = etat.legende;
    legendeBox.classList.remove("hidden");
  } else {
    legendeBox.classList.add("hidden");
  }

  etat.dialogue.forEach((replique, i) => {
    const bloc = document.createElement("div");
    bloc.className = "replique";
    bloc.innerHTML = `
      <div class="replique-header">
        <span class="pastille-genre ${replique.genre}"></span>
        <span class="replique-nom">${replique.personnage}</span>
      </div>
      <input type="text" class="ligne-input" value="${replique.ligne.replace(/"/g, "&quot;")}">
      <input type="text" class="ton-input" placeholder="ton (ex: chuchote, paniquée)" value="${(replique.ton || "").replace(/"/g, "&quot;")}">
    `;
    bloc.querySelector(".ligne-input").addEventListener("input", (e) => {
      etat.dialogue[i].ligne = e.target.value;
    });
    bloc.querySelector(".ton-input").addEventListener("input", (e) => {
      etat.dialogue[i].ton = e.target.value;
    });
    conteneur.appendChild(bloc);
  });

  panelPreview.classList.remove("hidden");
  panelPreview.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- Étape 3 : générer l'audio ----------

document.getElementById("btn-generer-audio").addEventListener("click", async () => {
  afficherChargement("Synthèse des voix en cours… (peut prendre 30–60 s)");
  try {
    const reponse = await fetch("/api/generer-audio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dialogue: etat.dialogue,
        format_sortie: etat.format,
      }),
    });
    if (!reponse.ok) throw new Error((await reponse.json()).detail || "Erreur serveur");
    const data = await reponse.json();

    const lecteur = document.getElementById("lecteur-audio");
    lecteur.src = data.url_telechargement;

    const lien = document.getElementById("lien-telechargement");
    lien.href = data.url_telechargement;
    lien.setAttribute("download", data.fichier);

    panelAudio.classList.remove("hidden");
    panelAudio.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    afficherErreur(err.message);
  } finally {
    masquerChargement();
  }
});
