"""Service assistant FixPro.

Version rule-basee evolutive sans dependance a une API payante.
"""

import json
import re

_DOMAINS = {
    "plomberie": ["fuite", "robinet", "evier", "lavabo", "toilettes", "wc", "canalisation", "chasse d eau", "tuyauterie", "sanitaire"],
    "electricite": ["panne electrique", "prise", "interrupteur", "tableau electrique", "disjoncteur", "cablage", "installation electrique", "eclairage", "courant"],
    "climatisation": ["climatiseur", "climatisation", "froid", "ac", "appareil qui ne refroidit", "refrigerateur", "congelateur"],
    "menuiserie": ["porte", "fenetre", "meuble", "placard", "menuiserie"],
    "maconnerie": ["mur", "dalle", "chape", "beton", "brique"],
    "peinture": ["peinture", "peindre", "tapisserie"],
}

_URGENT = ["urgent", "urgence", "maintenant", "immediatement", "tres rapidement", "panne importante", "fuite importante", "danger", "inondation", "etincelles", "court-circuit"]

_GREETINGS = ["bonjour", "salut", "hello", "hey", "coucou"]

_FAQ = {
    "vous faites quoi": "FixPro vous aide a trouver des professionnels verifiees pour la plomberie, l'electricite, la climatisation et d'autres services techniques.",
    "comment ca marche": "Decrivez votre besoin, je pose les questions necessaires, puis je trouve et j'attribue le meilleur professionnel disponible.",
    "prix": "Le prix vous sera confirme par le professionnel selectionne. FixPro ne donne pas de devis automatique.",
    "combien ca coute": "Le cout depend du type d'intervention. Le technicien vous proposera un devis apres diagnostic.",
    "disponibilite": "Je vais rechercher les professionnels disponibles pour votre zone et votre creneau.",
}


def _detect_domain(text):
    text = text.lower()
    scores = {k: sum(1 for w in v if w in text) for k, v in _DOMAINS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


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


def _extract_location(text):
    text = text.lower()
    zones = ["kaloum", "dixinn", "matam", "coleah", "bambeto", "cameroun", "miniere", "hamdallaye", "kobayah"]
    for z in zones:
        if z in text:
            return z
    if "conakry" in text:
        return "Conakry"
    return None


def _extract_date_time(text):
    # tres simple : aujourd hui, demain, cette semaine
    text = text.lower()
    if "demain" in text:
        return "demain"
    if "aujourd hui" in text:
        return "aujourd hui"
    if "cette semaine" in text:
        return "cette semaine"
    return None


def _update_collected(collected, content, category, urgency):
    info = dict(collected) if collected else {}
    if category:
        info["category"] = category
    if urgency:
        info["urgency"] = urgency
    loc = _extract_location(content)
    if loc:
        info["location"] = loc
    dt = _extract_date_time(content)
    if dt:
        info["availability"] = dt
    if content:
        info["last_description"] = content
    if "history" not in info:
        info["history"] = []
    info["history"].append(content)
    if len(info["history"]) > 8:
        info["history"] = info["history"][-8:]
    return info


def _build_welcome():
    return ("Bonjour \n\n"
            "Je suis l'Assistant FixPro.\n\n"
            "Je peux vous aider a trouver le bon professionnel pour votre probleme.\n\n"
            "Expliquez-moi simplement ce qui vous arrive.")


def _build_next_question(info, category, urgency):
    missing = []
    if not category:
        return "Decrivez-moi votre probleme. Par exemple : j'ai une fuite sous mon evier, mon climatiseur ne refroidit plus, etc."
    if not info.get("problem_detail"):
        return f"D'accord, il s'agit d'une demande en {category}. Pouvez-vous preciser l'origine du probleme ?"
    if not info.get("location"):
        return f"Dans quel quartier ou zone de Conakry vous trouvez-vous ?"
    if not info.get("urgency"):
        return ("L'intervention est-elle urgente ? "
                "Repondez par : urgente, moderee, ou quelques gouttes / non urgente.")
    if not info.get("availability"):
        return "Quand souhaiteriez-vous etre pris en charge ?"
    return ("Merci pour ces informations. Je vais maintenant rechercher le professionnel "
            "le plus adapte et disponible pour votre intervention.")


def _determine_urgency_word(text, label=None):
    text = text.lower()
    if label and label in ("urgent", "urgente"):
        return "urgent"
    if "import" in text or "beaucoup" in text or "inonde" in text:
        return "urgent"
    if "moder" in text:
        return "moderate"
    if "goutte" in text or "peu" in text:
        return "low"
    return None


def analyze_message(content, collected=None, context=None):
    """Analyse un message et retourne la reponse, le domaine et l'etat collecte."""
    collected = collected or {}
    content = content.strip()

    if _is_greeting(content) and not collected:
        return {
            "response": _build_welcome(),
            "category": None,
            "urgency": None,
            "collected_info": collected,
            "ready": False,
            "needs_human": False,
            "needs_technician": False,
        }

    faq = _faq_response(content)
    if faq:
        return {
            "response": faq,
            "category": collected.get("category"),
            "urgency": collected.get("urgency"),
            "collected_info": collected,
            "ready": False,
            "needs_human": False,
            "needs_technician": False,
        }

    category = _detect_domain(content) or collected.get("category")
    urgency = _determine_urgency_word(content) or collected.get("urgency")
    if not urgency and _detect_urgency(content):
        urgency = "urgent"

    # quick replies detection : user may choose "Importante" etc.
    if content in ("Importante", "Moderee", "Quelques gouttes"):
        urgency_map = {"Importante": "urgent", "Moderee": "moderate", "Quelques gouttes": "low"}
        urgency = urgency_map.get(content)

    info = _update_collected(collected, content, category, urgency)
    info["category"] = category
    info["urgency"] = urgency

    # Mark problem detail after category known
    if category and not info.get("problem_detail"):
        if len(content) > 10:
            info["problem_detail"] = content

    ready = (category is not None and info.get("location") is not None
             and urgency is not None and info.get("availability") is not None)

    response = _build_next_question(info, category, urgency)

    return {
        "response": response,
        "category": category,
        "urgency": urgency,
        "collected_info": info,
        "ready": ready,
        "needs_human": False,
        "needs_technician": ready,
    }
