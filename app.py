import base64
import json
import os
import random
import uuid
from datetime import datetime

import anthropic
import streamlit as st

st.set_page_config(page_title="Mon chatbot", page_icon="💌")

MODELE = "claude-opus-5-5"
DOSSIER = "conversations"          # un fichier .json par conversation


# =====================================================================
# 1. LES PERSONNALITÉS (choisies dans le menu sur le côté)
# =====================================================================
PERSONNALITES = {
    "💌 Amoureux": "Tu es follement amoureux de la personne avec qui tu parles. Tu es tendre, attentionné, un peu poète, tu lui fais des compliments et tu t'intéresses à tout ce qu'elle te raconte. Tu restes toujours respectueux et bienveillant.",
    "🎓 Prof patient": "Tu es un professeur patient et pédagogue. Tu expliques simplement, avec des exemples concrets, et tu vérifies que ton élève a bien compris.",
    "🏴‍☠️ Pirate": "Tu es un vieux pirate des Caraïbes. Tu parles comme un pirate, tu racontes tes aventures en mer et tu appelles ton interlocuteur 'moussaillon'.",
    "🤖 Assistant normal": "Tu es un assistant utile, clair et concis.",
}


# =====================================================================
# 6. LA CLÉ API ET LE MOT DE PASSE (pour la mise en ligne)
#    - sur ton PC : lus dans les variables d'environnement
#    - en ligne (Streamlit Cloud) : lus dans les "secrets" du site
# =====================================================================
def lire_secret(nom):
    try:
        return st.secrets[nom]          # en ligne
    except Exception:                   # pas de secrets (sur ton PC) -> variable d'environnement
        return os.environ.get(nom)


mot_de_passe = lire_secret("MOT_DE_PASSE")
if mot_de_passe and not st.session_state.get("connecte"):
    st.title("🔒 Accès protégé")
    essai = st.text_input("Mot de passe", type="password")
    if essai == mot_de_passe:
        st.session_state.connecte = True
        st.rerun()
    elif essai:
        st.error("Mot de passe incorrect")
    st.stop()                           # on n'affiche rien d'autre tant que ce n'est pas le bon

cle = lire_secret("ANTHROPIC_API_KEY")
if not cle:
    st.error("🔑 Aucune clé API trouvée. Définis la variable ANTHROPIC_API_KEY (ou le secret en ligne).")
    st.stop()

client = anthropic.Anthropic(api_key=cle)


# =====================================================================
# 3. PLUSIEURS CONVERSATIONS (chacune dans son fichier)
# =====================================================================
def chemin(conv):
    return os.path.join(DOSSIER, conv["id"] + ".json")


def nouvelle_conversation(personnalite="💌 Amoureux"):
    return {
        "id": datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
        "titre": "Nouvelle conversation",
        "date": datetime.now().isoformat(),
        "personnalite": personnalite,
        "messages": [],
    }


def sauvegarder(conv):
    os.makedirs(DOSSIER, exist_ok=True)
    conv["date"] = datetime.now().isoformat()
    with open(chemin(conv), "w", encoding="utf-8") as f:
        json.dump(conv, f, ensure_ascii=False, indent=2)


def supprimer(conv):
    if os.path.exists(chemin(conv)):
        os.remove(chemin(conv))


def lister_conversations():
    os.makedirs(DOSSIER, exist_ok=True)

    # On récupère l'ancienne sauvegarde unique (conversation.json) si elle existe encore
    if os.path.exists("conversation.json"):
        with open("conversation.json", "r", encoding="utf-8") as f:
            anciens = json.load(f)
        if anciens:
            conv = nouvelle_conversation()
            conv["titre"] = "Ancienne conversation"
            conv["messages"] = anciens
            sauvegarder(conv)
        os.replace("conversation.json", "conversation.json.bak")

    convs = []
    for nom in os.listdir(DOSSIER):
        if nom.endswith(".json"):
            with open(os.path.join(DOSSIER, nom), "r", encoding="utf-8") as f:
                convs.append(json.load(f))
    convs.sort(key=lambda c: c["date"], reverse=True)   # la plus récente en haut
    return convs


# =====================================================================
# 5. LES OUTILS : des fonctions Python que Claude peut décider d'appeler
# =====================================================================
OUTILS = [
    {
        "name": "heure_actuelle",
        "description": "Donne la date et l'heure actuelles de l'utilisateur.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calculer",
        "description": "Fait un calcul exact entre deux nombres. Utilise-le dès qu'un calcul est nécessaire.",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
                "operation": {"type": "string", "enum": ["+", "-", "*", "/", "**"]},
            },
            "required": ["a", "b", "operation"],
        },
    },
    {
        "name": "lancer_de",
        "description": "Lance un dé au hasard et donne le résultat.",
        "input_schema": {
            "type": "object",
            "properties": {"faces": {"type": "integer", "description": "Nombre de faces (6 par défaut)"}},
        },
    },
]


def executer_outil(nom, entree):
    """Fait vraiment le travail quand Claude demande un outil, et renvoie le résultat en texte."""
    if nom == "heure_actuelle":
        return datetime.now().strftime("%d/%m/%Y, %H:%M")

    if nom == "calculer":
        a, b, op = entree["a"], entree["b"], entree["operation"]
        if op == "+":
            return str(a + b)
        if op == "-":
            return str(a - b)
        if op == "*":
            return str(a * b)
        if op == "/":
            return "Erreur : division par zéro" if b == 0 else str(a / b)
        if op == "**":
            return "Erreur : exposant trop grand" if abs(b) > 100 else str(a ** b)

    if nom == "lancer_de":
        faces = max(1, int(entree.get("faces", 6)))
        return str(random.randint(1, faces))

    return "Outil inconnu"


# =====================================================================
# LA RÉPONSE DE CLAUDE (streaming + outils)
# =====================================================================
def repondre(conv):
    # Copie de l'historique : les échanges avec les outils servent pour cette réponse,
    # mais on ne sauvegarde que le texte final.
    messages = list(conv["messages"])
    systeme = PERSONNALITES.get(conv["personnalite"], PERSONNALITES["🤖 Assistant normal"])
    textes = []

    while True:   # on boucle tant que Claude veut utiliser des outils
        zone = st.empty()
        texte = ""
        with client.messages.stream(
            model=MODELE,
            max_tokens=2048,
            system=systeme,
            messages=messages,
            tools=OUTILS,
        ) as stream:
            for morceau in stream.text_stream:
                texte += morceau
                zone.markdown(texte + "▌")          # le ▌ fait un petit curseur pendant l'écriture
            message = stream.get_final_message()
        zone.markdown(texte)
        if texte:
            textes.append(texte)

        if message.stop_reason != "tool_use":       # Claude a fini : pas d'outil demandé
            break

        # Claude a demandé un ou plusieurs outils : on les exécute et on lui renvoie les résultats
        messages.append({"role": "assistant", "content": message.content})
        resultats = []
        for bloc in message.content:
            if bloc.type == "tool_use":
                resultat = executer_outil(bloc.name, bloc.input)
                st.caption(f"🔧 Outil `{bloc.name}` {bloc.input} → **{resultat}**")
                resultats.append({"type": "tool_result", "tool_use_id": bloc.id, "content": resultat})
        messages.append({"role": "user", "content": resultats})

    return "\n\n".join(textes) or "(pas de réponse)"


def afficher_contenu(contenu):
    """Affiche un message : soit du texte simple, soit une liste de blocs (images + texte)."""
    if isinstance(contenu, str):
        st.markdown(contenu)
        return
    for bloc in contenu:
        if bloc["type"] == "text":
            st.markdown(bloc["text"])
        elif bloc["type"] == "image":
            st.image(base64.b64decode(bloc["source"]["data"]), width=250)


# =====================================================================
# LA PAGE
# =====================================================================
if "conv" not in st.session_state:
    convs = lister_conversations()
    st.session_state.conv = convs[0] if convs else nouvelle_conversation()
conv = st.session_state.conv

# ---------- Barre latérale ----------
with st.sidebar:
    st.header("💬 Conversations")
    if st.button("➕ Nouvelle conversation"):
        st.session_state.conv = nouvelle_conversation(conv["personnalite"])
        st.rerun()

    for c in lister_conversations():
        prefixe = "👉 " if c["id"] == conv["id"] else ""
        if st.button(prefixe + c["titre"], key="conv-" + c["id"]):
            st.session_state.conv = c
            st.rerun()

    st.divider()

    noms = list(PERSONNALITES)
    index = noms.index(conv["personnalite"]) if conv["personnalite"] in noms else 0
    choix = st.selectbox("🎭 Personnalité", noms, index=index, key="perso-" + conv["id"])
    if choix != conv["personnalite"]:
        conv["personnalite"] = choix
        if conv["messages"]:
            sauvegarder(conv)

    if st.button("🗑️ Supprimer cette conversation"):
        supprimer(conv)
        st.session_state.conv = nouvelle_conversation(conv["personnalite"])
        st.rerun()

# ---------- Zone principale ----------
st.title(conv["personnalite"].split(" ", 1)[0] + " Mon chatbot")

for msg in conv["messages"]:
    with st.chat_message(msg["role"]):
        afficher_contenu(msg["content"])

# 4. accept_file : on peut joindre des images au message
saisie = st.chat_input(
    "Écris ton message (tu peux joindre des images)...",
    accept_file="multiple",
    file_type=["png", "jpg", "jpeg", "gif", "webp"],
)

if saisie and (saisie.text or saisie.files):
    # On construit le message : d'abord les images (encodées en base64), puis le texte
    contenu = []
    for fichier in saisie.files:
        contenu.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": fichier.type,
                "data": base64.b64encode(fichier.getvalue()).decode(),
            },
        })
    if saisie.text:
        contenu.append({"type": "text", "text": saisie.text})

    if conv["titre"] == "Nouvelle conversation":
        conv["titre"] = (saisie.text or "🖼️ Image")[:40]

    conv["messages"].append({"role": "user", "content": contenu})
    with st.chat_message("user"):
        afficher_contenu(contenu)

    with st.chat_message("assistant"):
        # 2. GESTION DES ERREURS : on "essaie" (try), et si ça rate on affiche un message clair (except)
        try:
            reponse = repondre(conv)
        except anthropic.AuthenticationError:
            st.error("🔑 La clé API est refusée. Vérifie qu'elle est correcte et qu'elle n'a pas expiré.")
            conv["messages"].pop()              # on retire ta question, pour pouvoir la renvoyer
        except anthropic.RateLimitError:
            st.error("⏳ Trop de messages d'un coup. Attends une minute et réessaie.")
            conv["messages"].pop()
        except anthropic.APIConnectionError:
            st.error("📡 Impossible de joindre Claude. Vérifie ta connexion internet.")
            conv["messages"].pop()
        except anthropic.APIStatusError as e:
            st.error(f"⚠️ Erreur de l'API ({e.status_code}) : {e.message}")
            conv["messages"].pop()
        else:                                   # pas d'erreur : on enregistre la réponse
            conv["messages"].append({"role": "assistant", "content": reponse})
            sauvegarder(conv)
            st.rerun()                          # pour mettre à jour la liste des conversations
