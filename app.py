import base64
import json
import math
import os
import random
import re
import unicodedata
import uuid
from collections import Counter
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

/* La petite carte de consommation + jauge */
.conso {{ background: #fff; border-radius: 12px; padding: 10px 12px; margin-bottom: 4px; box-shadow: 0 1px 6px rgba(0,0,0,.05); }}
.conso-ligne {{ display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 13px; color: #6b5f65; }}
.conso-gros {{ font-size: 18px; font-weight: 800; color: {p["couleur"]}; }}
.conso-petit {{ font-size: 12px; color: #9a8f95; }}
.jauge {{ height: 6px; background: #f0e8ec; border-radius: 999px; overflow: hidden; margin: 6px 0; }}
.jauge-rempli {{ height: 100%; border-radius: 999px; min-width: 4px; }}
.jauge-alerte {{ font-size: 12px; font-weight: 800; color: #e03131; }}
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


# =====================================================================
# 8. LE COMPTEUR QUI SURVIT AUX REDÉMARRAGES
#    - en ligne : rangé dans une base de données Supabase
#    - sur ton PC (sans Supabase) : rangé dans le fichier reglages.json
# =====================================================================
FICHIER_REGLAGES = "reglages.json"
TABLE = "chatbot_reglages"

url_supabase = lire_secret("SUPABASE_URL")
cle_supabase = lire_secret("SUPABASE_KEY")
base = None
if url_supabase and cle_supabase:
    from supabase import create_client
    # On garde seulement "https://xxxx.supabase.co" : la bibliothèque ajoute elle-même /rest/v1
    url_supabase = url_supabase.strip().rstrip("/").removesuffix("/rest/v1").rstrip("/")
    base = create_client(url_supabase, cle_supabase)


def lire_reglage(cle, defaut):
    """Lit une valeur enregistrée (le budget, le total...)."""
    try:
        if base:
            lignes = base.table(TABLE).select("valeur").eq("cle", cle).execute().data
            return lignes[0]["valeur"] if lignes else defaut
        if os.path.exists(FICHIER_REGLAGES):
            with open(FICHIER_REGLAGES, "r", encoding="utf-8") as f:
                return json.load(f).get(cle, defaut)
    except Exception as e:
        st.toast(f"⚠️ Impossible de lire le compteur : {e}")
    return defaut


def ecrire_reglage(cle, valeur):
    """Enregistre une valeur (elle remplace l'ancienne)."""
    try:
        if base:
            base.table(TABLE).upsert({"cle": cle, "valeur": valeur}).execute()
            return
        tout = {}
        if os.path.exists(FICHIER_REGLAGES):
            with open(FICHIER_REGLAGES, "r", encoding="utf-8") as f:
                tout = json.load(f)
        tout[cle] = valeur
        with open(FICHIER_REGLAGES, "w", encoding="utf-8") as f:
            json.dump(tout, f)
    except Exception as e:
        st.toast(f"⚠️ Impossible d'enregistrer le compteur : {e}")


def ajouter_au_total(usage_api):
    """Relit le total enregistré, y ajoute les tokens de cet appel, et le réenregistre."""
    total = lire_reglage("total", usage_vide())
    ajouter_usage(total, usage_api)
    ecrire_reglage("total", total)
    st.session_state.total = total


def afficher_conso(zone, conv):
    """Remplit la petite carte : total dépensé, jauge du budget, et coût de cette conversation."""
    total = st.session_state.get("total", usage_vide())
    budget = st.session_state.get("budget", 5.0)
    depense = cout(total)
    u_conv = conv.get("usage", usage_vide())

    pourcent = depense / budget * 100 if budget else 0
    if pourcent < 60:
        couleur = "#2f9e44"      # vert : tranquille
    elif pourcent < 85:
        couleur = "#f08c00"      # orange : attention
    else:
        couleur = "#e03131"      # rouge : presque au bout
    alerte = '<div class="jauge-alerte">⚠️ Budget dépassé</div>' if pourcent >= 100 else ""

    zone.markdown(f"""
<div class="conso" title="Estimation d'après les prix de {MODELE}. Le montant exact est dans la console Anthropic.">
  <div class="conso-ligne"><span class="conso-gros">🪙 {fmt_cout(depense)}</span><span>sur {budget:.2f} $ · <b>{pourcent:.1f} %</b></span></div>
  <div class="jauge"><div class="jauge-rempli" style="width:{min(pourcent, 100)}%; background:{couleur}"></div></div>
  <div class="conso-petit">Cette conversation : {fmt_cout(cout(u_conv))} · {fmt_tokens(nb_tokens(u_conv))} tokens</div>
  {alerte}
</div>
""", unsafe_allow_html=True)


# =====================================================================
# 3. PLUSIEURS CONVERSATIONS
#    - en ligne : dans la table chatbot_conversations de Supabase (survit aux redémarrages)
#    - sur ton PC (sans Supabase) : un fichier .json par conversation dans conversations/
# =====================================================================
TABLE_CONVERSATIONS = "chatbot_conversations"


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
    conv["date"] = datetime.now().isoformat()
    if base:
        try:
            base.table(TABLE_CONVERSATIONS).upsert(
                {"id": conv["id"], "donnees": conv, "date": conv["date"]}
            ).execute()
        except Exception as e:
            st.toast(f"⚠️ Impossible d'enregistrer la conversation : {e}")
        return
    os.makedirs(DOSSIER, exist_ok=True)
    with open(chemin(conv), "w", encoding="utf-8") as f:
        json.dump(conv, f, ensure_ascii=False, indent=2)


def supprimer(conv):
    if base:
        try:
            base.table(TABLE_CONVERSATIONS).delete().eq("id", conv["id"]).execute()
        except Exception as e:
            st.toast(f"⚠️ Impossible de supprimer la conversation : {e}")
        return
    if os.path.exists(chemin(conv)):
        os.remove(chemin(conv))


def lister_conversations():
    if base:
        try:
            lignes = base.table(TABLE_CONVERSATIONS).select("donnees").order("date", desc=True).execute().data
            return [ligne["donnees"] for ligne in lignes]
        except Exception as e:
            st.toast(f"⚠️ Impossible de lire les conversations : {e}")
            return []

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


# =====================================================================
# 9. LE RAG : faire répondre Claude à partir de TES documents
#    Étape 1 : lire les fichiers du dossier documents/
#    Étape 2 : les découper en petits passages
#    Étape 3 : quand Claude cherche, trouver les passages qui contiennent les mêmes mots
#    Étape 4 : les lui donner, il répond en s'appuyant dessus et cite la source
# =====================================================================
DOSSIER_DOCS = "documents"
EXTENSIONS = (".pdf", ".txt", ".md")

# Petits mots trop fréquents pour aider à trouver quelque chose
MOTS_VIDES = set("""le la les un une des de du et en au aux ce cet cette ces dans est sont il elle on
pour par pas plus que qui quoi sur se sa son ses ou mais avec comme tout tous nous vous ils elles leur
leurs ne lui me te je tu mon ma mes ton ta tes est-ce quel quelle quels quelles comment combien""".split())


def mots(texte):
    """Transforme un texte en liste de mots simples : minuscules, sans accents, sans petits mots."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")   # retire les accents
    return [m for m in re.findall(r"[a-z0-9]+", texte) if len(m) > 1 and m not in MOTS_VIDES]


def extraire_texte(nom, octets):
    """Étape 1 : récupère le texte d'un fichier PDF, TXT ou MD (à partir de son contenu brut)."""
    if nom.lower().endswith(".pdf"):
        from io import BytesIO
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(octets)).pages)
    return octets.decode("utf-8", errors="ignore")


# Les documents viennent de deux endroits :
#  - "dossier" : le dossier documents/ (envoyé sur GitHub, toujours présent)
#  - "base"    : les documents ajoutés depuis la page, rangés dans Supabase (seulement leur texte)
TABLE_DOCUMENTS = "chatbot_documents"


def ajouter_document(nom, octets):
    nom = os.path.basename(nom)
    if base:
        try:
            base.table(TABLE_DOCUMENTS).upsert({
                "nom": nom, "texte": extraire_texte(nom, octets), "date": datetime.now().isoformat(),
            }).execute()
        except Exception as e:
            st.toast(f"⚠️ Impossible d'enregistrer le document : {e}")
        return
    os.makedirs(DOSSIER_DOCS, exist_ok=True)
    with open(os.path.join(DOSSIER_DOCS, nom), "wb") as f:
        f.write(octets)


def supprimer_document(nom):
    try:
        base.table(TABLE_DOCUMENTS).delete().eq("nom", nom).execute()
    except Exception as e:
        st.toast(f"⚠️ Impossible de supprimer le document : {e}")


def texte_document(nom, origine):
    if origine == "base":
        return base.table(TABLE_DOCUMENTS).select("texte").eq("nom", nom).execute().data[0]["texte"]
    with open(os.path.join(DOSSIER_DOCS, nom), "rb") as f:
        return extraire_texte(nom, f.read())


def decouper(texte, taille=1000, chevauchement=200):
    """Étape 2 : coupe le texte en passages d'environ 1000 caractères.
    Les passages se chevauchent un peu, pour ne pas couper une idée en deux."""
    texte = texte.strip()
    passages, debut = [], 0
    while debut < len(texte):
        fin = min(debut + taille, len(texte))
        if fin < len(texte):                     # on essaie de couper à la fin d'une ligne ou d'une phrase
            coupure = max(texte.rfind("\n", debut, fin), texte.rfind(". ", debut, fin))
            if coupure > debut + taille // 2:
                fin = coupure + 1
        passages.append(texte[debut:fin].strip())
        if fin >= len(texte):
            break
        debut = max(fin - chevauchement, debut + 1)
    return [p for p in passages if p]


def signature_documents():
    """La liste des documents : (nom, version, origine). La version (une date) sert à savoir si quelque chose a changé."""
    docs = []
    if os.path.isdir(DOSSIER_DOCS):
        for nom in os.listdir(DOSSIER_DOCS):
            if nom.lower().endswith(EXTENSIONS):
                docs.append((nom, str(os.path.getmtime(os.path.join(DOSSIER_DOCS, nom))), "dossier"))
    if base:
        try:
            for ligne in base.table(TABLE_DOCUMENTS).select("nom, date").execute().data:
                docs.append((ligne["nom"], ligne["date"], "base"))
        except Exception as e:
            st.toast(f"⚠️ Impossible de lire la liste des documents : {e}")
    return tuple(sorted(docs))


@st.cache_data   # Streamlit garde le résultat en mémoire : on ne relit les documents que s'ils changent
def construire_index(signature):
    passages = []
    for nom, _, origine in signature:
        for numero, texte in enumerate(decouper(texte_document(nom, origine)), 1):
            passages.append({"source": nom, "numero": numero, "texte": texte, "mots": mots(texte)})
    return passages


def chercher(requete, passages, nb_resultats=4):
    """Étape 3 : donne une note à chaque passage (méthode BM25) et renvoie les meilleurs.
    Un passage gagne des points s'il contient les mots de la recherche, surtout les mots RARES
    (un mot présent partout, comme "chatbot", compte moins qu'un mot précis, comme "supabase")."""
    mots_requete = mots(requete)
    if not mots_requete or not passages:
        return []
    nb_passages = len(passages)
    longueur_moyenne = sum(len(p["mots"]) for p in passages) / nb_passages
    nb_passages_avec = Counter(m for p in passages for m in set(p["mots"]))   # dans combien de passages est chaque mot
    k1, b = 1.5, 0.75                                                        # réglages classiques de BM25

    notes = []
    for p in passages:
        compte = Counter(p["mots"])
        note = 0
        for m in mots_requete:
            if m in compte:
                rarete = math.log(1 + (nb_passages - nb_passages_avec[m] + 0.5) / (nb_passages_avec[m] + 0.5))
                frequence = compte[m] * (k1 + 1) / (compte[m] + k1 * (1 - b + b * len(p["mots"]) / longueur_moyenne))
                note += rarete * frequence
        if note > 0:
            notes.append((note, p))
    notes.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in notes[:nb_resultats]]


OUTIL_RECHERCHE = {
    "name": "chercher_documents",
    "description": "Cherche dans les documents de l'utilisateur (cours, notes, fiches...) et renvoie les passages "
                   "les plus pertinents avec leur source. Utilise des mots-clés précis ; tu peux faire plusieurs "
                   "recherches avec des mots différents si la première ne suffit pas.",
    "input_schema": {
        "type": "object",
        "properties": {"requete": {"type": "string", "description": "Les mots-clés à chercher"}},
        "required": ["requete"],
    },
}


def consigne_rag(noms_fichiers):
    return ("\n\nL'utilisateur a mis ces documents à ta disposition : " + ", ".join(noms_fichiers) + ". "
            "Quand une question peut concerner ces documents, utilise l'outil chercher_documents avant de répondre. "
            "Appuie-toi sur les passages trouvés et cite la source entre crochets, par exemple [cours.pdf, passage 3]. "
            "Si la réponse n'est pas dans les documents, dis-le clairement au lieu d'inventer.")


def executer_outil(nom, entree):
    """Fait vraiment le travail quand Claude demande un outil, et renvoie le résultat en texte."""
    if nom == "chercher_documents":
        # Étape 4 : on renvoie à Claude les passages trouvés, avec leur source
        trouves = chercher(entree.get("requete", ""), construire_index(signature_documents()))
        if not trouves:
            return "Aucun passage trouvé dans les documents pour cette recherche."
        return "\n\n".join(f"[{p['source']}, passage {p['numero']}]\n{p['texte']}" for p in trouves)

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

    # 9. S'il y a des documents : on ajoute l'outil de recherche et on prévient Claude
    systeme, outils = perso["system"], OUTILS
    documents = [nom for nom, _, _ in signature_documents()]
    if documents:
        systeme += consigne_rag(documents)
        outils = OUTILS + [OUTIL_RECHERCHE]

    while True:   # on boucle tant que Claude veut utiliser des outils
        zone = st.empty()
        texte = ""
        with client.messages.stream(
            model=MODELE,
            max_tokens=16000,
            system=systeme,
            messages=messages,
            tools=outils,
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
        ajouter_au_total(message.usage)
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
                if bloc.name == "chercher_documents":     # le résultat est long : on n'affiche que les sources
                    sources = sorted(set(re.findall(r"^\[(.+?), passage \d+\]$", resultat, re.M)))
                    st.caption(f"🔎 Recherche « {bloc.input.get('requete', '')} » → {', '.join(sources) or 'rien trouvé'}")
                else:
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

# Au début de la visite : on lit le total et le budget enregistrés
if "total" not in st.session_state:
    total = lire_reglage("total", None)
    if total is None:                           # première fois : on repart de la somme des conversations
        total = usage_vide()
        for c in lister_conversations():
            for k in total:
                total[k] += c.get("usage", {}).get(k, 0)
        ecrire_reglage("total", total)
    st.session_state.total = total
if "budget" not in st.session_state:
    st.session_state.budget = float(lire_reglage("budget", 5.0))
    st.session_state.budget_enregistre = st.session_state.budget

# ---------- Barre latérale ----------
with st.sidebar:
    noms = list(PERSONNALITES)
    index = noms.index(conv["personnalite"]) if conv["personnalite"] in noms else 0
    choix = st.selectbox("🎭 Personnalité", noms, index=index, key="perso-" + conv["id"])
    if choix != conv["personnalite"]:
        conv["personnalite"] = choix
        if conv["messages"]:
            sauvegarder(conv)

    zone_conso = st.empty()                     # la petite carte + jauge (remplie plus bas)

    with st.expander("🎯 Changer le budget"):
        budget = st.number_input("Budget ($)", min_value=0.5, step=0.5, key="budget")
        if budget != st.session_state.budget_enregistre:
            ecrire_reglage("budget", budget)
            st.session_state.budget_enregistre = budget

    # 9. Les documents pour le RAG
    docs = signature_documents()
    with st.expander(f"📚 Mes documents ({len(docs)})"):
        for nom, _, origine in docs:
            if origine == "base":                          # ajouté depuis la page : on peut le retirer
                col_nom, col_suppr = st.columns([5, 1])
                col_nom.caption("📄 " + nom)
                if col_suppr.button("✕", key="suppr-doc-" + nom, help="Retirer ce document"):
                    supprimer_document(nom)
                    st.rerun()
            else:
                st.caption("📄 " + nom)
        nouveaux = st.file_uploader("Ajouter des documents", type=["pdf", "txt", "md"],
                                    accept_multiple_files=True, key=f"upload-{st.session_state.get('nb_envois', 0)}")
        if nouveaux:
            for fichier in nouveaux:
                ajouter_document(fichier.name, fichier.getvalue())
            st.session_state.nb_envois = st.session_state.get("nb_envois", 0) + 1   # vide la zone d'envoi
            st.rerun()

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
