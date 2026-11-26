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

# Prix de claude-opus-5-5, en dollars pour 1 million de tokens
PRIX = {
    "input": 4.00,         # ce que tu envoies (historique, consigne, images...)
    "output": 20.00,       # ce que Claude écrit (réflexion comprise)
    "cache_read": 0.20,    # partie de l'historique relue depuis le cache (20x moins cher)
    "cache_write": 5.00,   # mise en cache d'un nouveau morceau d'historique
}


# =====================================================================
# 1. LES PERSONNALITÉS : consigne + couleurs de la page
# =====================================================================
PERSONNALITES = {
    "💌 Amoureux": {
        "emoji": "💌", "nom": "Amoureux", "couleur": "#d6336c", "fonce": "#a61e4d", "fond": "#fff0f5",
        "slogan": "Tendre, attentionné, un brin poète.",
        "system": "Tu es follement amoureux de la personne avec qui tu parles. Tu es tendre, attentionné, un peu poète, tu lui fais des compliments et tu t'intéresses à tout ce qu'elle te raconte. Tu restes toujours respectueux et bienveillant.",
    },
    "🎓 Prof patient": {
        "emoji": "🎓", "nom": "Prof patient", "couleur": "#1c7ed6", "fonce": "#1864ab", "fond": "#eef6ff",
        "slogan": "Explique simplement, avec des exemples.",
        "system": "Tu es un professeur patient et pédagogue. Tu expliques simplement, avec des exemples concrets, et tu vérifies que ton élève a bien compris.",
    },
    "🏴‍☠️ Pirate": {
        "emoji": "🏴‍☠️", "nom": "Pirate", "couleur": "#e8590c", "fonce": "#a63f05", "fond": "#fff4e6",
        "slogan": "Des histoires de mer, moussaillon !",
        "system": "Tu es un vieux pirate des Caraïbes. Tu parles comme un pirate, tu racontes tes aventures en mer et tu appelles ton interlocuteur 'moussaillon'.",
    },
    "🤖 Assistant normal": {
        "emoji": "🤖", "nom": "Assistant", "couleur": "#0ca678", "fonce": "#087f5b", "fond": "#ebfbf5",
        "slogan": "Clair, utile et concis.",
        "system": "Tu es un assistant utile, clair et concis.",
    },
}


def injecter_style(p):
    """Ajoute du CSS à la page, avec les couleurs de la personnalité choisie."""
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;800&display=swap');
.stApp, .stApp p, .stApp li, .stApp textarea, .stApp input {{ font-family: 'Nunito', sans-serif; }}
#MainMenu, footer {{ visibility: hidden; }}

/* Le bandeau en haut */
.hero {{
  display: flex; align-items: center; gap: 18px;
  padding: 22px 26px; margin-bottom: 18px; border-radius: 22px;
  background: linear-gradient(135deg, {p["couleur"]}, {p["fonce"]});
  color: #fff; box-shadow: 0 10px 30px -12px {p["couleur"]};
}}
.hero-emoji {{ font-size: 46px; line-height: 1; }}
.hero-nom {{ font-size: 28px; font-weight: 800; line-height: 1.1; }}
.hero-slogan {{ opacity: .9; font-size: 16px; }}

/* Les bulles de messages */
[data-testid="stChatMessage"] {{
  border-radius: 18px; padding: 14px 16px; margin-bottom: 10px;
  background: #fff; border: 1px solid #eee5e9;
}}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
  background: {p["fond"]}; border-color: transparent;
}}

/* La barre latérale */
[data-testid="stSidebar"] {{ background: {p["fond"]}; }}
[data-testid="stSidebar"] .stButton button {{
  width: 100%; justify-content: flex-start; text-align: left; border-radius: 12px;
}}
[data-testid="stBaseButton-primary"] {{ background: {p["couleur"]}; border-color: {p["couleur"]}; }}
[data-testid="stBaseButton-primary"]:hover {{ background: {p["fonce"]}; border-color: {p["fonce"]}; }}

/* La carte de consommation */
.conso {{ background: #fff; border-radius: 16px; padding: 14px 16px; box-shadow: 0 2px 10px rgba(0,0,0,.05); }}
.conso-ligne {{ display: flex; justify-content: space-between; gap: 8px; font-size: 14px; color: #6b5f65; }}
.conso-gros {{ font-size: 26px; font-weight: 800; color: {p["couleur"]}; line-height: 1.2; }}
.conso-sep {{ border-top: 1px solid #f0e8ec; margin: 10px 0; }}
.conso-note {{ font-size: 12px; color: #9a8f95; margin-top: 8px; }}
</style>
""", unsafe_allow_html=True)


# =====================================================================
# 6. LA CLÉ API ET LE MOT DE PASSE (pour la mise en ligne)
# =====================================================================
def lire_secret(nom):
    try:
        return st.secrets[nom]          # en ligne
    except Exception:                   # pas de secrets (sur ton PC) -> variable d'environnement
        return os.environ.get(nom)


mot_de_passe = lire_secret("MOT_DE_PASSE")
if mot_de_passe and not st.session_state.get("connecte"):
    injecter_style(PERSONNALITES["💌 Amoureux"])
    st.markdown('<div class="hero"><div class="hero-emoji">🔒</div><div><div class="hero-nom">Accès protégé</div>'
                '<div class="hero-slogan">Entre le mot de passe pour discuter.</div></div></div>', unsafe_allow_html=True)
    essai = st.text_input("Mot de passe", type="password")
    if essai == mot_de_passe:
        st.session_state.connecte = True
        st.rerun()
    elif essai:
        st.error("Mot de passe incorrect")
    st.stop()

cle = lire_secret("ANTHROPIC_API_KEY")
if not cle:
    st.error("🔑 Aucune clé API trouvée. Définis la variable ANTHROPIC_API_KEY (ou le secret en ligne).")
    st.stop()

client = anthropic.Anthropic(api_key=cle)


# =====================================================================
# 7. TOKENS ET COÛT
# =====================================================================
def usage_vide():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


def ajouter_usage(total, usage_api):
    """Ajoute les tokens d'une réponse de l'API (message.usage) à un compteur."""
    total["input"] += usage_api.input_tokens or 0
    total["output"] += usage_api.output_tokens or 0
    total["cache_read"] += usage_api.cache_read_input_tokens or 0
    total["cache_write"] += usage_api.cache_creation_input_tokens or 0


def nb_tokens(u):
    return sum(u.values())


def cout(u):
    """Coût en dollars : tokens x prix, divisé par 1 million."""
    return sum(u[k] * PRIX[k] for k in PRIX) / 1_000_000


def fmt_tokens(n):
    return f"{n:,}".replace(",", " ")


def fmt_cout(c):
    return f"{c:.4f}".replace(".", ",") + " $"


def afficher_conso(zone, conv):
    """Remplit la carte de consommation de la barre latérale."""
    u_conv = conv.get("usage", usage_vide())
    u_tout = usage_vide()
    for c in lister_conversations():
        if c["id"] != conv["id"]:
            for k in u_tout:
                u_tout[k] += c.get("usage", {}).get(k, 0)
    for k in u_tout:
        u_tout[k] += u_conv[k]

    zone.markdown(f"""
<div class="conso">
  <div class="conso-ligne"><span>Cette conversation</span><span>{fmt_tokens(nb_tokens(u_conv))} tokens</span></div>
  <div class="conso-gros">{fmt_cout(cout(u_conv))}</div>
  <div class="conso-ligne"><span>↑ envoyés {fmt_tokens(u_conv["input"] + u_conv["cache_read"] + u_conv["cache_write"])}</span><span>↓ écrits {fmt_tokens(u_conv["output"])}</span></div>
  <div class="conso-sep"></div>
  <div class="conso-ligne"><span>Toutes les conversations</span><span>{fmt_tokens(nb_tokens(u_tout))} tokens</span></div>
  <div class="conso-gros" style="font-size:20px">{fmt_cout(cout(u_tout))}</div>
  <div class="conso-note">Estimation d'après les prix de {MODELE}. Le montant exact est dans la console Anthropic.</div>
</div>
""", unsafe_allow_html=True)


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
        "usage": usage_vide(),
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
# LA RÉPONSE DE CLAUDE (streaming + outils + comptage des tokens)
# =====================================================================
def repondre(conv, zone_conso):
    # On n'envoie que "role" et "content" (pas nos infos de tokens, que l'API refuserait)
    messages = [{"role": m["role"], "content": m["content"]} for m in conv["messages"]]
    perso = PERSONNALITES.get(conv["personnalite"], PERSONNALITES["🤖 Assistant normal"])
    textes = []
    usage_message = usage_vide()      # les tokens de CETTE réponse (parfois plusieurs appels avec les outils)

    while True:   # on boucle tant que Claude veut utiliser des outils
        zone = st.empty()
        texte = ""
        with client.messages.stream(
            model=MODELE,
            max_tokens=16000,
            system=perso["system"],
            messages=messages,
            tools=OUTILS,
            cache_control={"type": "ephemeral"},   # met l'historique en cache : les tours suivants coûtent moins cher
        ) as stream:
            for morceau in stream.text_stream:
                texte += morceau
                zone.markdown(texte + "▌")          # le ▌ fait un petit curseur pendant l'écriture
            message = stream.get_final_message()
        zone.markdown(texte)
        if texte:
            textes.append(texte)

        # 7. On compte les tokens de cet appel, et on met la carte à jour tout de suite
        ajouter_usage(usage_message, message.usage)
        ajouter_usage(conv["usage"], message.usage)
        afficher_conso(zone_conso, conv)

        if message.stop_reason == "refusal":
            textes.append("_(Claude a préféré ne pas répondre à ce message.)_")
            break
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

    return "\n\n".join(textes) or "(pas de réponse)", usage_message


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


def legende_usage(u):
    st.caption(f"🪙 {fmt_tokens(nb_tokens(u))} tokens · {fmt_cout(cout(u))}")


# =====================================================================
# LA PAGE
# =====================================================================
if "conv" not in st.session_state:
    convs = lister_conversations()
    st.session_state.conv = convs[0] if convs else nouvelle_conversation()
conv = st.session_state.conv
conv.setdefault("usage", usage_vide())          # les anciennes conversations n'avaient pas de compteur

# ---------- Barre latérale ----------
with st.sidebar:
    noms = list(PERSONNALITES)
    index = noms.index(conv["personnalite"]) if conv["personnalite"] in noms else 0
    choix = st.selectbox("🎭 Personnalité", noms, index=index, key="perso-" + conv["id"])
    if choix != conv["personnalite"]:
        conv["personnalite"] = choix
        if conv["messages"]:
            sauvegarder(conv)

    st.subheader("🪙 Consommation")
    zone_conso = st.empty()

    st.subheader("💬 Conversations")
    if st.button("➕ Nouvelle conversation"):
        st.session_state.conv = nouvelle_conversation(conv["personnalite"])
        st.rerun()

    for c in lister_conversations():
        actuelle = c["id"] == conv["id"]
        if st.button(c["titre"], key="conv-" + c["id"], type="primary" if actuelle else "secondary"):
            st.session_state.conv = c
            st.rerun()

    if st.button("🗑️ Supprimer cette conversation"):
        supprimer(conv)
        st.session_state.conv = nouvelle_conversation(conv["personnalite"])
        st.rerun()

perso = PERSONNALITES.get(conv["personnalite"], PERSONNALITES["🤖 Assistant normal"])
injecter_style(perso)
afficher_conso(zone_conso, conv)

# ---------- Zone principale ----------
st.markdown(f"""
<div class="hero">
  <div class="hero-emoji">{perso["emoji"]}</div>
  <div><div class="hero-nom">{perso["nom"]}</div><div class="hero-slogan">{perso["slogan"]}</div></div>
</div>
""", unsafe_allow_html=True)

if not conv["messages"]:
    st.caption("Écris ton premier message en bas de la page. Tu peux aussi joindre une image 📎")

for msg in conv["messages"]:
    avatar = perso["emoji"] if msg["role"] == "assistant" else None
    with st.chat_message(msg["role"], avatar=avatar):
        afficher_contenu(msg["content"])
        if "usage" in msg:
            legende_usage(msg["usage"])

# 4. accept_file : on peut joindre des images au message
saisie = st.chat_input(
    "Écris ton message...",
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

    with st.chat_message("assistant", avatar=perso["emoji"]):
        # 2. GESTION DES ERREURS : on "essaie" (try), et si ça rate on affiche un message clair (except)
        try:
            reponse, usage_message = repondre(conv, zone_conso)
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
            legende_usage(usage_message)
            conv["messages"].append({"role": "assistant", "content": reponse, "usage": usage_message})
            sauvegarder(conv)
            st.rerun()                          # pour mettre à jour la liste des conversations
