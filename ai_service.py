"""Assistante conversationnelle Lia pour FixPro.

Logique basee sur la comprehension d'intention, du contexte, de l'emotion
et du domaine. Conserve la memoire conversationnelle via `collected`.
"""

import os
import random
import re
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

_DOMAINS = {
    "plomberie": [
        "plomberie", "plombier", "plomb", "plom", "fuite", "fuite d eau",
        "robinet", "evier", "lavabo", "douche", "wc", "toilettes", "tuyau",
        "canalisation", "canalisation bouchee", "sanitaire", "eau", "chasse d eau",
        "pression d eau", "evacuation", "egout", "syphon", "chauffe eau",
        "ballon d eau chaude", "fuite sous", "fuite dans", "wc bouche",
        "bouche", "bouché", "bouchee", "tuyauterie", "tuyaux", "trop plein", "mitigeur",
        "flexible", "siphon", "jacuzzi", "baignoire", "cuvette", "reservoir",
    ],
    "electricite": [
        "electricite", "electrique", "electricien", "elec", "cablage",
        "tableau", "disjoncteur", "disjoncte", "sauter", "saute",
        "prise", "interrupteur", "panne de courant", "plus de courant",
        "courant", "court-circuit", "eclairage", "lumiere", "ampoule",
        "cable", "branchement", "installation electrique", "tableau electrique",
        "terre", "prise electrique", "compteur", "secteur", "ne s allume plus",
        "ne marche plus", "rallonge", "multiprise", "transformateur", "ne fonctionne",
    ],
    "climatisation": [
        "climatisation", "climatiseur", "clim", "conditionneur", "ventilation",
        "climatisateur", "ne refroidit plus", "ne fait plus de froid",
        "ne fait plus froid", "fait du bruit", "ne demarre plus",
        "gaz", "compresseur", "split", "unite exterieure",
    ],
    "refrigeration": [
        "refrigeration", "frigo", "refrigerateur", "congelateur", "froid",
        "conglateur", "congel", "ne refroidit plus", "ne fait plus de froid",
        "ne fait froid", "frigidaire", "congelation", "refrigerateur",
        "chambre froide", "vitreuse", "vitrine refrigeree", "compresseur",
    ],
    "serrurerie": [
        "serrurerie", "serrurier", "serrure", "cle", "cle cassee",
        "cylindre", "ouverture de porte", "verrou", "bloquee", "bloque",
        "portee", "serrur", "porte ne s ouvre plus", "ne tourne plus",
        "perdu", "oublie", "clef", "serrure cassee", "changer serrure",
        "installer serrure", "depanneur", "crochetage", "porte fermee",
    ],
    "chauffagiste": [
        "chauffage", "chauffagiste", "chaudiere", "radiateur", "calefaction",
        "chauffe", "chauffage ne marche plus", "radiateur froid", "chaudiere ne s allume pas",
    ],
    "menuiserie": [
        "menuiserie", "menuisier", "porte", "portes", "porte en bois", "fenetre", "fenetres",
        "fenetre en bois", "gonds", "charniere", "charnieres", "meuble", "armoire", "table",
        "chaise", "placard", "charpente", "bois", "ebeniste", "casser en bois",
        "reparation de meuble", "fabrication de meuble", "vrak", "volige", "encadrement",
        "passe plat", "plinthe", "lambourde", "parquet",
    ],
    "peinture": ["peinture", "peintre", "peindre", "tapisserie", "enduit"],
    "maconnerie": ["maconnerie", "macon", "mur", "dalle", "chape", "beton", "brique"],
    "nettoyage": ["nettoyage", "menage", "nettoyer", "propre"],
}

_ZONES = ["kaloum", "dixinn", "matam", "coleah", "bambeto", "cameroun", "miniere", "hamdallaye", "kobayah", "matoto", "ratoma", "lambanyi"]

_URGENT = ["urgent", "urgence", "tres vite", "rapidement", "immediat", "immediatement", "grave", "inondation", "danger", "panne totale", "critique", "au plus vite"]

_MODERATE = ["modere", "moyen", "assez", "beaucoup", "important", "rapidement", "vite"]

_LOW = ["petit", "peu", "goutte", "leger", "normal", "pas urgent", "non urgent", "tranquille", "pas presse"]

_EMOJIS = {
    "joie": ["\U0001F60A", "\U0001F604"],
    "rire": ["\U0001F602"],
    "tristesse": ["\U0001F622", "\U0001F62D"],
    "colere": ["\U0001F620", "\U0001F621"],
    "inquietude": ["\U0001F61F"],
    "amour": ["\u2764\ufe0f"],
    "merci": ["\U0001F64F"],
}

_INTENT_KEYWORDS = {
    "greeting": ["bonjour", "salut", "hello", "coucou", "bonsoir", "bon matin", "bonne nuit", "yo", "hi", "hey", "bonjourr", "salutt"],
    "farewell": ["au revoir", "a bientot", "bonne nuit", "a demain", "bonne journee", "ciao", "bye", "bye bye", "a plus"],
    "thanks": ["merci", "thank", "thanks", "thx", "mercie", "mercit", "remercie"],
    "apology": ["desole", "desolee", "excuse", "excusee", "pardon", "navre"],
    "small_talk": ["ca va", "comment vas-tu", "comment ca va", "how are you", "quoi de neuf", "ca roule", "tu vas bien", "comment allez-vous"],
    "personal_ai": ["tu es", "es-tu", "etes-vous", "as-tu", "as tu", "tu as", "qui es-tu", "qui es tu", "qui etes-vous", "tu travailles", "tu manges", "tu dors", "tu maries", "te maries", "famille", "enfants", "mari", "femme", "amoureux", "petit ami", "celibataire", "robot", "ia", "intelligence artificielle"],
    "fixpro_question": ["fixpro", "comment fonctionne", "technicien", "plombier", "electricien", "frigoriste", "serrurier", "compte", "inscription", "prix", "tarif", "devis", "localisation", "geolocalisation", "gps", "disponible"],
    "general_question": ["c'est quoi", "qu'est-ce que", "quest ce que", "qui a", "pourquoi", "comment", "what is", "who is", "why", "where", "definir", "definition"],
    "emotion": ["triste", "stress", "enerve", "enervee", "heureux", "content", "inquiet", "inquiete", "frustr", "frustre", "frustree", "joyeux", "malheureux"],
    "technical_problem": ["probleme", "panne", "fuite", "ne fonctionne", "ne marche", "cassé", "cassée", "bruit", "froid", "chaud", "clim", "evier", "robinet", "prise"],
    "request_technician": ["technicien", "artisan", "intervention", "besoin d un", "besoin d une", "reparer", "repare", "depanner", "urgence", "demande"],
    "price_question": ["prix", "tarif", "combien", "coute", "devis", "estimation", "montant"],
    "status_question": ["statut", "etat", "ou en est", "mission", "intervention", "numero", "reference", "demande"],
    "confirmation": ["ok", "d'accord", "dac", "entendu", "bien recu", "parfait", "ca marche", "oui", "yes", "c'est bon", "c est bon", "confirme", "valide"],
    "correction": ["mauvaise", "pas la bonne", "pas bonne", "ce n est pas", "c est pas", "pas ca", "pas cela", "changer", "modifier", "corriger", "annuler", "recommencer", "reprendre"],
    "out_of_scope": [],
}

_FIXPRO_INFO = {
    "fr": (
        "FixPro met en relation des clients avec des techniciens verifies a Conakry : "
        "plombiers, electriciens, frigoristes, serruriers, menuisiers... "
        "Vous decrivez votre probleme, nous trouvons le professionnel adapte."
    ),
    "en": (
        "FixPro connects customers with verified technicians in Conakry: "
        "plumbers, electricians, refrigeration technicians, locksmiths, carpenters... "
        "Describe your issue and we find the right professional."
    ),
}


_GEMINI_SYSTEM_PROMPT = (
    "Tu es Lia, l'assistante conversationnelle de FixPro, une plateforme de "
    "mise en relation avec des techniciens verifies a Conakry. "
    "Tu comprens les fautes d'orthographe, les phrases incompletes et le "
    "francais familiar. Reponds a la question de l'utilisateur de maniere "
    "naturelle, chaleureuse, claire, utile et concise. "
    "Si la question est generale, reponds normalement. Si elle evoque un "
    "probleme technique, identifie le domaine et oriente doucement vers FixPro "
    "sans insister. Garde tes reponses en dessous de 120 mots."
)


def _call_gemini(message, lang="fr"):
    """Appelle Google Gemini pour repondre aux questions generales."""
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return None
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-1.5-flash:generateContent?key={api_key}")
    system = _GEMINI_SYSTEM_PROMPT
    if lang == "en":
        system = system.replace("Reponds", "Answer").replace("l'utilisateur", "the user")
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": message}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 300,
        },
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        return parts[0].get("text", "").strip()
    except Exception:
        return None


_NORMALIZE_PUNCT = str.maketrans("'-.,;:!?", " " * 8)
_NORMALIZE_ACCENTS = str.maketrans("éèêàùçôî", "eeeaucoi")


def _normalize(text):
    text = (text or "").lower()
    text = text.replace("’", "'")
    text = text.translate(_NORMALIZE_PUNCT)
    text = text.translate(_NORMALIZE_ACCENTS)
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text, words):
    nt = _normalize(text)
    return any(w in nt for w in words)


def _is_greeting(text):
    nt = _normalize(text)
    words = nt.split()
    if not nt or len(words) <= 2:
        return True
    return any(g in words for g in _INTENT_KEYWORDS["greeting"])


def _is_emoji_only(text):
    stripped = text.strip()
    return stripped and all(ord(c) > 127 for c in stripped)


def _detect_language(text):
    text = _normalize(text)
    words = set(text.split())
    en_words = {"hello", "hi", "how", "what", "who", "why", "where", "thank", "please", "you", "your", "my", "need", "help", "well"}
    fr_words = {"bonjour", "salut", "merci", "comment", "quoi", "qui", "pourquoi", "besoin", "aide", "mon", "votre", "est", "le", "la", "ca", "va", "vas", "vous"}
    en = len(words & en_words)
    fr = len(words & fr_words)
    if en > fr:
        return "en"
    return "fr"


def _detect_emotion(text):
    text = _normalize(text)
    emojis = text
    if any(e in emojis for e in ["\U0001F622", "\U0001F62D", "\U0001F61F", "\U0001F614"]):
        return "tristesse"
    if any(e in emojis for e in ["\U0001F620", "\U0001F621", "\U0001F480", "\U0001F624"]):
        return "colere"
    if any(e in emojis for e in ["\U0001F602", "\U0001F923", "\U0001F606"]):
        return "joie"
    if any(e in emojis for e in ["\U0001F60A", "\U0001F604", "\u2764\ufe0f", "\U0001F618"]):
        return "amour"
    if any(e in emojis for e in ["\U0001F64F", "\U0001F64C"]):
        return "remerciement"
    if "stress" in text or "triste" in text or "malheureux" in text or "inquiet" in text or "inquiete" in text:
        return "tristesse"
    if any(w in text for w in ["enerve", "enervee", "colere", "furieux", "furieuse", "rage", "frustre", "frustree"]):
        return "colere"
    if any(w in text for w in ["heureux", "contente", "content", "joyeux", "super", "genial", "excellent", "cool"]):
        return "joie"
    return None


def _detect_intent(content, history=None):
    nt = _normalize(content)
    words = set(nt.split())
    scores = {k: 0 for k in _INTENT_KEYWORDS}

    for intent, kws in _INTENT_KEYWORDS.items():
        for w in kws:
            if " " in w:
                if w in nt:
                    scores[intent] += 1
            else:
                if w in words:
                    scores[intent] += 1

    # detection emotion par emoji ou mots
    emotion = _detect_emotion(content)
    if emotion:
        scores["emotion"] += 2

    # personal ai
    personal_starts = ["tu es", "es tu", "as tu", "as-tu", "qui es", "qui etes", "parles-tu", "parles tu", "travailles tu", "manges tu", "dors tu", "te maries"]
    if any(nt.startswith(s) for s in personal_starts) or "marie" in nt or "famille" in nt or "enfants" in nt:
        scores["personal_ai"] += 3

    # general question
    question_starts = ["c est quoi", "qu est ce que", "quest ce que", "qui a", "pourquoi", "comment", "what is", "who is", "why", "where", "definition"]
    if any(nt.startswith(s) for s in question_starts) or ("quoi" in nt and "c est" in nt):
        if not scores.get("fixpro_question") and not scores.get("personal_ai"):
            scores["general_question"] += 2

    # fixpro question
    if "fixpro" in nt or "technicien" in nt or "prix" in nt or "tarif" in nt or "compte" in nt:
        scores["fixpro_question"] += 2

    # technical problem
    dom = _detect_domain(content)
    if dom:
        scores["technical_problem"] += 4

    # correction
    if any(w in nt for w in ["mauvaise", "pas la bonne", "ce n est pas", "c est pas", "changer", "modifier", "corriger", "annuler", "recommencer"]):
        scores["correction"] += 4

    # request technician explicitly
    if any(w in nt for w in ["veux un technicien", "besoin d un technicien", "appeler un professionnel", "intervention", "reparer", "depanner"]):
        scores["request_technician"] += 3

    # small talk often short
    if len(nt.split()) <= 4 and any(w in nt for w in ["ca va", "vas tu", "vas-tu", "how are", "ca roule"]):
        scores["small_talk"] += 2

    # greeting usually short
    if len(words) <= 3:
        for g in ["bonjour", "salut", "hello", "coucou", "bonsoir", "hi", "hey", "yo"]:
            if g in words:
                scores["greeting"] += 2

    if _is_emoji_only(content):
        return "emotion", emotion

    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        return "out_of_scope", emotion
    return best, emotion


def _detect_domain(text):
    text = _normalize(text)
    best, best_score = None, 0
    for domain, words in _DOMAINS.items():
        score = sum(1 for w in words if w in text)
        if score > best_score:
            best_score = score
            best = domain
    return best


def _detect_urgency(text):
    text = _normalize(text)
    if any(u in text for u in _URGENT):
        return "urgent"
    if any(m in text for m in _MODERATE):
        return "modere"
    if any(l in text for l in _LOW):
        return "normal"
    return None


def _extract_location(text):
    text = _normalize(text)
    for z in _ZONES:
        if z in text:
            return z.capitalize()
    if "conakry" in text:
        return "Conakry"
    return None


def _extract_availability(text):
    text = _normalize(text)
    for kw in ["aujourd hui", "maintenant", "tout de suite", "immediatement", "aujourd hui"]:
        if kw in text:
            return "aujourd'hui"
    for kw in ["demain"]:
        if kw in text:
            return "demain"
    for kw in ["cette semaine", "semaine prochaine"]:
        if kw in text:
            return "cette semaine"
    return None


def _pick_response(responses):
    return random.choice(responses)


def _greeting_response(lang="fr"):
    if lang == "en":
        return _pick_response([
            "Hello \U0001F60A Welcome to FixPro! How can I help you today?",
            "Hi there \U0001F60A I'm Lia, your FixPro assistant. How are you doing?",
            "Hello \U0001F60A Nice to meet you at FixPro. What can I do for you?",
        ])
    return _pick_response([
        "Bonjour \U0001F60A Bienvenue chez FixPro ! Comment puis-je vous aider ?",
        "Salut \U0001F60A Je suis Lia, l'assistante de FixPro. Comment allez-vous ?",
        "Bonjour \U0001F60A Heureuse de vous accueillir chez FixPro. Que puis-je faire pour vous ?",
    ])


def _farewell_response(lang="fr"):
    if lang == "en":
        return _pick_response([
            "Goodbye \U0001F60A Take care!",
            "See you soon \U0001F60A Have a great day!",
        ])
    return _pick_response([
        "Au revoir \U0001F60A Prenez soin de vous !",
        "A bientot \U0001F60A Passez une excellente journee !",
        "Bonne journee \U0001F60A N'hesitez pas a revenir si besoin.",
    ])


def _thanks_response(lang="fr"):
    if lang == "en":
        return _pick_response([
            "You're welcome \U0001F64F Happy to help!",
            "My pleasure \U0001F60A",
        ])
    return _pick_response([
        "Avec plaisir \U0001F64F",
        "Je vous en prie \U0001F60A",
        "C'est avec plaisir \U0001F60A",
    ])


def _apology_response(lang="fr"):
    if lang == "en":
        return _pick_response([
            "No problem at all \U0001F60A",
            "Don't worry \U0001F60A",
        ])
    return _pick_response([
        "Aucun souci \U0001F60A",
        "Vous ne me derangez pas du tout \U0001F60A",
        "Pas de probleme \U0001F60A",
    ])


def _small_talk_response(lang="fr"):
    if lang == "en":
        return _pick_response([
            "I'm doing well, thank you \U0001F60A How about you?",
            "Great \U0001F60A Ready to help. What's new with you?",
        ])
    return _pick_response([
        "Je vais bien, merci \U0001F60A Et vous, comment ca va ?",
        "Tres bien \U0001F60A Et de votre cote, tout va bien ?",
        "Ca roule \U0001F602 Et vous, ca va ?",
    ])


def _personal_ai_response(content, lang="fr"):
    nt = _normalize(content)
    if "marie" in nt or "mari" in nt or "amoureux" in nt or "femme" in nt or "petit ami" in nt or "celibataire" in nt:
        if lang == "en":
            return "No \U0001F60A I don't have a personal or romantic life. I'm Lia, the AI assistant of FixPro."
        return "Non \U0001F60A Je n'ai pas de vie sentimentale ni de famille. Je suis Lia, l'assistante IA de FixPro."
    if "dors" in nt or "sommeil" in nt:
        if lang == "en":
            return "I don't sleep \U0001F604 I'm available whenever FixPro needs me."
        return "Non \U0001F604 Je ne dors jamais. Je suis la quand FixPro a besoin de moi."
    if "mange" in nt or "bois" in nt or "nourriture" in nt:
        if lang == "en":
            return "I don't eat or drink \U0001F60A I'm just an AI, but I can still chat with you."
        return "Non \U0001F60A Je ne mange ni ne bois. Je suis une IA, mais je peux quand meme discuter avec vous."
    if "vie" in nt or "ville" in nt or "habite" in nt:
        if lang == "en":
            return "I don't live anywhere \U0001F60A I'm a virtual assistant. My home is FixPro."
        return "Je n'habite nulle part \U0001F60A Je suis une assistante virtuelle, mon espace de travail, c'est FixPro."
    if "vraie personne" in nt or "robot" in nt or "ia" in nt or "intelligence artificielle" in nt or "reelle" in nt:
        if lang == "en":
            return "I'm not a real person \U0001F60A I'm Lia, an AI assistant made to help you with FixPro."
        return "Non \U0001F60A Je ne suis pas une vraie personne. Je suis Lia, une assistante IA creee pour vous aider avec FixPro."
    if "create" in nt or "creat" in nt or "fabrique" in nt or "invente" in nt or "developpe" in nt:
        if lang == "en":
            return "I was created by the FixPro team \U0001F60A They built me to help you find verified technicians."
        return "J'ai ete creee par l'equipe de FixPro \U0001F60A pour vous aider a trouver des techniciens verifies."
    if lang == "en":
        return "I don't have a human life \U0001F60A I'm Lia, the AI assistant of FixPro. But I'm here to help you!"
    return "Je n'ai pas de vie humaine \U0001F60A Je suis Lia, l'assistante IA de FixPro. Mais je suis la pour vous aider !"


def _emotion_response(emotion, lang="fr"):
    if emotion == "tristesse":
        if lang == "en":
            return "I'm sorry to hear that \U0001F61F I'm here if you want to talk or if you need help with something."
        return "Je suis desolee d'entendre cela \U0001F61F Je suis la si vous voulez en parler ou si vous avez besoin d'aide."
    if emotion == "colere":
        if lang == "en":
            return "I understand it's frustrating \U0001F620 I'm here to help you find a solution."
        return "Je comprends que ce soit frustrant \U0001F620 Je suis la pour vous aider a trouver une solution."
    if emotion == "joie":
        if lang == "en":
            return "Great \U0001F602 Happy to hear that!"
        return "Super \U0001F602 Je suis contente de l'entendre !"
    if emotion == "amour":
        if lang == "en":
            return "Thank you \u2764\ufe0f That's very kind."
        return "Merci \u2764\ufe0f C'est tres gentil."
    if emotion == "remerciement":
        if lang == "en":
            return "You're very welcome \U0001F64F"
        return "Avec plaisir \U0001F64F"
    if lang == "en":
        return "I understand \U0001F60A I'm here for you."
    return "Je comprends \U0001F60A Je suis la pour vous."


def _general_response(content, lang="fr"):
    nt = _normalize(content)
    if "internet" in nt:
        if lang == "en":
            return "Internet is a global network connecting computers worldwide. \U0001F60A Do you need help with something at home?"
        return "Internet est un reseau mondial qui connecte des ordinateurs partout dans le monde. \U0001F60A Si vous avez besoin d'un technicien, FixPro peut vous aider."
    if "facebook" in nt or "whatsapp" in nt:
        if lang == "en":
            return "It's a well-known platform for communication and social networking. \U0001F60A Is there a home repair I can help you with?"
        return "C'est une plateforme tres connue pour communiquer et partager. \U0001F60A Vous avez un probleme a la maison a regler ?"
    if "climatisation" in nt and ("quoi" in nt or "defin" in nt or "what" in nt):
        if lang == "en":
            return "Air conditioning is a system that cools indoor air. \U0001F60A If yours isn't working, I can help you find a technician."
        return "La climatisation est un systeme qui rafraichit l'air interieur. \U0001F60A Si la votre ne marche plus, je peux vous aider a trouver un technicien."
    gemini = _call_gemini(content, lang=lang)
    if gemini:
        return gemini
    if lang == "en":
        return "Good question \U0001F60A I can answer general things, and I'm here if you need help with FixPro."
    return "Bonne question \U0001F60A Je peux repondre a des choses generales, et je suis la si vous avez besoin d'aide avec FixPro."


def _fixpro_question_response(content, lang="fr"):
    nt = _normalize(content)
    if any(w in nt for w in ["prix", "tarif", "devis", "cout"]):
        if lang == "en":
            return "Each technician sets their own prices and rates. FixPro shows you the details before you confirm. \U0001F60A"
        return "Chaque technicien fixe ses propres tarifs. FixPro vous montre les details avant de confirmer. \U0001F60A"
    if "compte" in nt or "inscription" in nt or "connect" in nt or "login" in nt:
        if lang == "en":
            return "You can create a client account directly on FixPro. Technicians register and go through a verification process. \U0001F60A"
        return "Vous pouvez creer un compte client directement sur FixPro. Les techniciens s'inscrivent puis sont verifies. \U0001F60A"
    if "comment" in nt or "fonctionne" in nt or "comment ca marche" in nt:
        if lang == "en":
            return _FIXPRO_INFO["en"] + " \U0001F60A"
        return _FIXPRO_INFO["fr"] + " \U0001F60A"
    if lang == "en":
        return "FixPro connects you with verified technicians in Conakry. \U0001F60A How can I help you?"
    return _FIXPRO_INFO["fr"] + " \U0001F60A"


def _out_of_scope_response(content, lang="fr"):
    gemini = _call_gemini(content, lang=lang)
    if gemini:
        return gemini
    if lang == "en":
        return "I don't have an answer for everything, but I'm here if you need help with FixPro \U0001F60A"
    return "Je ne peux pas repondre a tout, mais je suis la si vous avez besoin d'aide avec FixPro \U0001F60A"


def _confirmation_response(lang="fr"):
    if lang == "en":
        return "Perfect \U0001F44C Let me know if you need anything else."
    return "Parfait \U0001F44C N'hesitez pas si vous avez besoin d'autre chose."


def _price_question_response(lang="fr"):
    if lang == "en":
        return "The final price depends on the technician's diagnosis and estimate. FixPro shows you the estimate before you confirm. \U0001F60A"
    return "Le prix final depend du diagnostic et du devis du technicien. FixPro vous montre l'estimation avant de confirmer. \U0001F60A"


def _status_question_response(lang="fr"):
    if lang == "en":
        return "I don't have the live status of your request at the moment. I'll let you know as soon as I have an update."
    return "Je n'ai pas encore le suivi en direct de votre demande. Je vous tiens informe des que j'ai une mise a jour."


def _update_collected(collected, content):
    info = dict(collected) if collected else {}
    if "history" not in info:
        info["history"] = []
    info["history"].append(content)
    if len(info["history"]) > 8:
        info["history"] = info["history"][-8:]

    lang = _detect_language(content)
    info["language"] = lang

    old_category = info.get("category")
    old_location = info.get("location")
    old_urgency = info.get("urgency")
    old_availability = info.get("availability")
    old_problem = info.get("problem_detail")

    dom = _detect_domain(content)
    if dom:
        info["category"] = dom
        info.setdefault("mode", "fixpro")

    loc = _extract_location(content)
    if loc:
        info["location"] = loc

    urg = _detect_urgency(content)
    if urg:
        info["urgency"] = urg

    av = _extract_availability(content)
    if av:
        info["availability"] = av

    # Si une information change pendant une demande de confirmation,
    # on revient a l'etape de resume pour reconfirmer.
    if info.get("needs_confirmation"):
        if (info.get("category") != old_category or
            info.get("location") != old_location or
            info.get("urgency") != old_urgency or
            info.get("availability") != old_availability):
            info["needs_confirmation"] = False

    intent, emotion = _detect_intent(content, info.get("history"))
    info["last_intent"] = intent
    info["last_emotion"] = emotion
    if not info.get("mode"):
        info["mode"] = "fixpro" if (dom or intent == "request_technician") else "chat"
    elif info.get("mode") == "chat" and (dom or intent == "request_technician"):
        info["mode"] = "fixpro"
    elif (info.get("mode") == "fixpro" and
          not info.get("needs_confirmation") and
          content and content.strip() and
          intent in ("greeting", "farewell", "thanks", "apology", "small_talk",
                     "personal_ai", "general_question", "fixpro_question",
                     "price_question", "status_question")):
        # L'utilisateur change de sujet, on sort du flux technique
        info["mode"] = "chat"
        info.pop("category", None)
        info.pop("location", None)
        info.pop("urgency", None)
        info.pop("availability", None)
        info.pop("problem_detail", None)
        info.pop("needs_confirmation", None)

    # memorise le prenom si le client le donne
    nt = _normalize(content)
    m = re.search(r"\b(je m appelle|mon prenom est|moi c est|je suis)\b ([a-zA-Z\-]+)", nt)
    if m:
        info["client_name"] = m.group(2).capitalize()

    # Conserve la vraie description du probleme, pas une reponse courte
    prob = content.strip()
    words = prob.split()
    has_keyword = bool(dom or loc or urg or av)
    if len(prob) > 5 and len(words) >= 3 and not _is_greeting(prob) and not has_keyword:
        info["problem_detail"] = prob
    elif not info.get("problem_detail") and len(prob) > 5 and not _is_greeting(prob) and not _contains_any(prob, _INTENT_KEYWORDS["personal_ai"] + _INTENT_KEYWORDS["small_talk"] + _INTENT_KEYWORDS["farewell"]):
        info["problem_detail"] = prob

    if info.get("needs_confirmation") and info.get("problem_detail") != old_problem:
        info["needs_confirmation"] = False

    return info


def _has_missing(info):
    missing = []
    if not info.get("category"):
        missing.append("category")
    if not info.get("location"):
        missing.append("location")
    if not info.get("urgency"):
        missing.append("urgency")
    if not info.get("availability"):
        missing.append("availability")
    return missing


def _build_technical_response(info, last_message, lang="fr"):
    name = info.get("client_name", "")
    name_part = f" {name}" if name else ""

    missing = _has_missing(info)

    if info.get("last_intent") == "correction" and info.get("category"):
        info["category"] = None
        info["needs_confirmation"] = False
        missing = _has_missing(info)

    if "category" in missing:
        if info.get("problem_detail"):
            if lang == "en":
                return f"Thanks{name_part}.\n\nCan you confirm the type of service? Plumbing, electricity, air conditioning, refrigeration, locksmith..."
            return f"Merci{name_part}.\n\nPour m'orienter, pouvez-vous confirmer le type de service ? Plomberie, electricite, climatisation, refrigeration, serrurerie..."
        if lang == "en":
            return f"How can I help you{name_part}? What type of problem is it? Plumbing, electricity, air conditioning, locksmith..."
        return f"Je vais vous aider{name_part}.\n\nDe quel type de probleme s'agit-il ? Plomberie, electricite, climatisation, serrurerie..."

    if "location" in missing:
        if lang == "en":
            return f"Okay, it's a {info['category']} request.\n\nWhich district of Conakry are you in?"
        return f"D'accord, il s'agit d'une demande en {info['category']}.\n\nDans quel quartier de Conakry vous trouvez-vous ?"

    if "urgency" in missing:
        if lang == "en":
            return f"Thanks{name_part}.\n\nIs the intervention urgent, quite fast, or can it wait?"
        return f"Merci{name_part}.\n\nL'intervention est-elle urgente, assez rapide, ou peut-elle attendre un peu ?"

    if "availability" in missing:
        if lang == "en":
            return f"Great{name_part}.\n\nWhen would you be available? Today, tomorrow or later?"
        return f"Parfait{name_part}.\n\nQuand seriez-vous disponible pour recevoir le professionnel ? Aujourd'hui, demain ou plus tard ?"

    detail = info.get("problem_detail") or "votre demande"
    cat = info.get("category", "")
    loc = info.get("location", "")
    urg = info.get("urgency", "")
    av = info.get("availability", "")

    if not info.get("needs_confirmation"):
        info["needs_confirmation"] = True
        if lang == "en":
            return (f"Thank you for all the details{name_part}.\n\n"
                    f"Summary of your request:\n"
                    f"Problem: {detail}\n"
                    f"Trade: {cat}\n"
                    f"Location: {loc}\n"
                    f"Urgency: {urg}\n"
                    f"Availability: {av}\n\n"
                    "Is this correct? (Yes / No)")
        return (f"Merci pour toutes ces informations{name_part}.\n\n"
                f"Resume de votre demande :\n"
                f"Probleme : {detail}\n"
                f"Metier : {cat}\n"
                f"Lieu : {loc}\n"
                f"Urgence : {urg}\n"
                f"Disponibilite : {av}\n\n"
                "Est-ce correct ? (Oui / Non)")

    if info.get("last_intent") == "confirmation":
        if lang == "en":
            return f"Perfect{name_part}. I am creating your FixPro request now."
        return f"Parfait{name_part}. Je cree votre demande FixPro maintenant."

    info["needs_confirmation"] = False
    if lang == "en":
        return f"No problem{name_part}. What would you like to change?"
    return f"Pas de souci{name_part}. Que souhaitez-vous modifier ?"


def _build_response(info, last_message):
    lang = info.get("language", "fr")
    intent = info.get("last_intent")
    emotion = info.get("last_emotion")
    mode = info.get("mode", "chat")

    # Si une demande technique est en attente de confirmation, on reste dans le flux technique.
    if mode == "fixpro" and info.get("needs_confirmation") and not _has_missing(info):
        return _build_technical_response(info, last_message, lang)

    # Si on est en mode technique et le dernier message est une vraie demande technique,
    # on garde le flux technique sauf si c'est une emotion marquante sans technique.
    if mode == "fixpro":
        if intent not in ("greeting", "farewell", "thanks", "apology", "small_talk", "personal_ai", "general_question", "price_question", "status_question", "confirmation"):
            if emotion and intent in ("emotion", "out_of_scope"):
                pass
            else:
                return _build_technical_response(info, last_message, lang)

    # En mode conversation libre, on donne la priorite a Gemini pour repondre
    # de maniere naturelle a n'importe quelle question.
    if mode != "fixpro" and os.getenv("GOOGLE_API_KEY"):
        gemini = _call_gemini(last_message or "", lang=lang)
        if gemini:
            return gemini

    # Reponses conversationnelles
    if intent == "greeting":
        return _greeting_response(lang)
    if intent == "farewell":
        return _farewell_response(lang)
    if intent == "thanks":
        return _thanks_response(lang)
    if intent == "apology":
        return _apology_response(lang)
    if intent == "small_talk":
        return _small_talk_response(lang)
    if intent == "personal_ai":
        return _personal_ai_response(last_message or "", lang)
    if intent == "emotion":
        return _emotion_response(emotion, lang)
    if intent == "fixpro_question":
        return _fixpro_question_response(last_message or "", lang)
    if intent == "general_question":
        return _general_response(last_message or "", lang)
    if intent == "price_question":
        return _price_question_response(lang)
    if intent == "status_question":
        return _status_question_response(lang)
    if intent == "confirmation":
        return _confirmation_response(lang)
    if intent == "correction":
        info["needs_confirmation"] = False
        if lang == "en":
            return "No problem. Tell me the right trade: plumbing, electricity, air conditioning, locksmith, carpentry..."
        return "Pas de souci. Dites-moi simplement le bon metier : plomberie, electricite, climatisation, serrurerie, menuiserie..."

    # Par defaut, si un domaine est connu, on reprend le flux technique
    if info.get("category"):
        return _build_technical_response(info, last_message, lang)

    return _out_of_scope_response(last_message or "", lang)


def analyze_message(content, collected=None):
    """Analyse un message et retourne une reponse conversationnelle.

    Cette fonction conserve le moteur de collecte technique historique
    et utilise les reponses reglees pour eviter les erreurs du fournisseur IA.
    """
    collected = _update_collected(collected or {}, content)
    action = None
    data = None

    # Si une collecte technique est en cours, on garde le moteur historique
    # pour guider l'utilisateur, recuperer les informations manquantes et
    # gerer les confirmations/corrections.
    response = _build_response(collected, content)

    missing = _has_missing(collected)
    complete = (collected.get("mode") == "fixpro" and all(k not in missing for k in ["category", "location", "urgency", "availability"]))
    ready = False
    if complete and collected.get("needs_confirmation") and collected.get("last_intent") == "confirmation":
        ready = True
        collected["needs_confirmation"] = False

    return {
        "response": response,
        "category": collected.get("category"),
        "urgency": collected.get("urgency"),
        "collected_info": collected,
        "ready": ready,
        "needs_human": False,
        "needs_technician": ready,
        "action": action,
        "data": data,
    }


def _is_ready_to_confirm(collected):
    """Indique si toutes les informations techniques sont collectees."""
    if collected.get("mode") != "fixpro":
        return False
    missing = _has_missing(collected)
    return all(k not in missing for k in ["category", "location", "urgency", "availability"])
