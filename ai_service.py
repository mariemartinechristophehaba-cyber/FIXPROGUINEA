"""Service assistant FixPro.

Version rule-based sans dependance a une API payante.
L'architecture permet de brancher un modele IA externe via la variable
AI_PROVIDER plus tard.
"""

import re
import os


_DOMAINS = {
    "plomberie": ["fuite", "robinet", "evier", "lavabo", "toilettes", "wc", "canalisation", "chasse d eau", "tuyauterie", "sanitaire"],
    "electricite": ["panne electrique", "prise", "interrupteur", "tableau electrique", "disjoncteur", "cablage", "installation electrique", "eclairage", "courant"],
    "climatisation": ["climatiseur", "climatisation", "froid", "ac", "appareil qui ne refroidit", "refrigerateur", "congelateur"],
    "menuiserie": ["porte", "fenetre", "meuble", "placard", "menuiserie"],
    "maconnerie": ["mur", "dalle", "chape", "beton", "brique"],
    "peinture": ["peinture", "peindre", "tapisserie"],
}

_URGENT = ["urgent", "urgence", "maintenant", "immediatement", "tres rapidement", "panne importante", "fuite importante", "danger"]

_GREETINGS = ["bonjour", "salut", "hello", "hey", "coucou"]

_FAQ = {
    "vous faites quoi": "FixPro vous permet de trouver des professionnels verifies pour vos besoins en plomberie, electricite, climatisation et autres services techniques.",
    "comment trouver un plombier": "Indiquez simplement votre besoin et votre localisation si necessaire. FixPro vous orientera vers les professionnels correspondant a votre demande.",
    "comment trouver un electricien": "Indiquez simplement votre besoin et votre localisation si necessaire. FixPro vous orientera vers les professionnels correspondant a votre demande.",
    "comment trouver un frigoriste": "Indiquez simplement votre besoin et votre localisation si necessaire. FixPro vous orientera vers les professionnels correspondant a votre demande.",
    "comment ca marche": "Decrivez votre besoin, notre equipe analyse votre demande et vous met en relation avec le professionnel adapte.",
    "prix": "Je vais transmettre votre demande a un professionnel qui pourra vous proposer un devis adapte.",
    "combien ca coute": "Le prix depend de la nature de l intervention. Un professionnel vous contactera pour evaluer et chiffrer la prestation.",
    "disponibilite": "Je vais verifier la disponibilite des professionnels pour votre demande.",
    "technicien": "Je vais transmettre votre demande au bon technicien apres avoir recolte les informations necessaires.",
}


def _detect_domain(text):
    text = text.lower()
    scores = {k: sum(1 for w in v if w in text) for k, v in _DOMAINS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return None
    return best


def _detect_urgency(text):
    text = text.lower()
    return any(u in text for u in _URGENT)


def _is_greeting(text):
    text = text.lower().strip("!?:.,")
    return any(text == g for g in _GREETINGS) or text in _GREETINGS


def _faq_response(text):
    text = text.lower()
    for key, value in _FAQ.items():
        if key in text:
            return value
    return None


def _needs_human(text, history=None):
    """Determine si la demande necessite une intervention humaine."""
    text = text.lower()
    if any(k in text for k in ["plainte", "remboursement", "paiement", "technicien selectionne", "annuler", "changement"]):
        return True
    if history and len(history) >= 4:
        return True
    return False


def _build_response(intent, category, urgency, content, history):
    if _is_greeting(content):
        return "Bonjour, bienvenue sur FixPro. Decrivez votre besoin, je vais vous aider a l'identifier et a le transmettre au bon professionnel."

    faq = _faq_response(content)
    if faq:
        return faq

    if category:
        if urgency:
            base = (f"J'ai compris, il s'agit d'une demande urgente en {category}. "
                    "Pouvez-vous me preciser votre zone d'intervention ?")
        else:
            base = (f"J'ai compris, il s'agit d'une demande de {category}. "
                    "Pouvez-vous me preciser votre zone d'intervention ?")
        return base

    return "Merci pour votre message. Pouvez-vous me preciser votre besoin et votre localisation afin que je vous oriente vers le bon professionnel ?"


def analyze_message(content, history=None, context=None):
    """Analyse un message client et retourne une reponse IA."""
    history = history or []
    category = _detect_domain(content)
    urgency = _detect_urgency(content)
    needs_human = _needs_human(content, history)
    response = _build_response("inquiry", category, urgency, content, history)
    needs_technician = category is not None

    return {
        "response": response,
        "intent": "intervention" if category else "inquiry",
        "category": category,
        "urgency": "urgent" if urgency else "normal",
        "needs_human": needs_human,
        "needs_technician": needs_technician,
        "confidence": 0.8 if category else 0.4,
    }
