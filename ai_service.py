"""Assistant conversationnel FixPro.

Logique rule-basee avec un ton humain et professionnel.
"""

import json

_DOMAINS = {
    "electricite": ["electricite", "electrique", "cablage", "tableau", "disjoncteur", "prise", "interrupteur", "panne de courant", "court-circuit", "eclairage"],
    "plomberie": ["plomberie", "plombier", "fuite", "robinet", "evier", "lavabo", "douche", "wc", "toilettes", "tuyau", "canalisation", "sanitaire"],
    "climatisation": ["climatisation", "climatiseur", "clim", "refrigeration", "frigo", "froid", "ventilation"],
    "menuiserie": ["menuiserie", "menuisier", "porte", "fenetre", "meuble", "placard", "charpente"],
    "peinture": ["peinture", "peintre", "peindre", "tapisserie", "enduit"],
    "maconnerie": ["maconnerie", "macon", "mur", "dalle", "chape", "beton", "brique"],
    "nettoyage": ["nettoyage", "menage", "nettoyer", "propre"],
}

_ZONES = ["kaloum", "dixinn", "matam", "coleah", "bambeto", "cameroun", "miniere", "hamdallaye", "kobayah", "matoto", "ratoma", "lambanyi"]

_URGENT = ["urgent", "urgence", "tres vite", "rapidement", "immediat", "immediatement", "grave", "inondation", "danger", "panne totale"]

_MODERATE = ["modere", "moyen", "assez", "beaucoup", "important"]

_LOW = ["petit", "peu", "goutte", "leger", "normal", "pas urgent", "non urgent"]


def _normalize(text):
    return (text or "").lower().replace("'", " ").replace("-", " ")


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
    for kw in ["aujourd hui", "maintenant", "tout de suite", "immediatement"]:
        if kw in text:
            return "aujourd'hui"
    for kw in ["demain"]:
        if kw in text:
            return "demain"
    for kw in ["cette semaine", "semaine prochaine"]:
        if kw in text:
            return "cette semaine"
    return None


def _update_collected(collected, content):
    info = dict(collected) if collected else {}
    if "history" not in info:
        info["history"] = []
    info["history"].append(content)
    if len(info["history"]) > 8:
        info["history"] = info["history"][-8:]

    dom = _detect_domain(content)
    if dom:
        info["category"] = dom

    prob = content.strip()
    if len(prob) > 5:
        info["problem_detail"] = prob

    loc = _extract_location(content)
    if loc:
        info["location"] = loc

    urg = _detect_urgency(content)
    if urg:
        info["urgency"] = urg

    av = _extract_availability(content)
    if av:
        info["availability"] = av

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


def _build_response(info, last_message):
    last = (last_message or "").strip().lower()

    if not last or last in ("bonjour", "salut", "hello", "coucou", "bonsoir"):
        return ("Bonjour et bienvenue chez FixPro.\n\n"
                "Je suis l'assistant qui vous accompagne. Décrivez-moi simplement votre problème, "
                "et je m'occupe de trouver la bonne solution pour vous.")

    missing = _has_missing(info)

    if "category" in missing:
        if info.get("problem_detail"):
            return ("Merci pour ces précisions.\n\n"
                    "Pour m'orienter au mieux, pouvez-vous me confirmer le type de service dont vous avez besoin ? "
                    "Plomberie, électricité, climatisation, menuiserie, peinture... ?")
        return ("Je vais vous aider.\n\n"
                "De quel type de problème s'agit-il ? Plomberie, électricité, climatisation, menuiserie... ?")

    if "location" in missing:
        return (f"D'accord, il s'agit d'une demande en {info['category']}.\n\n"
                "Dans quel quartier de Conakry vous trouvez-vous ?")

    if "urgency" in missing:
        return ("Merci.\n\n"
                "L'intervention est-elle urgente, assez rapide, ou peut-elle attendre un peu ?")

    if "availability" in missing:
        return ("Parfait.\n\n"
                "Quand seriez-vous disponible pour recevoir le professionnel ? Aujourd'hui, demain ou plus tard ?")

    return ("Merci pour toutes ces informations.\n\n"
            f"J'ai bien compris : {info['problem_detail']}.\n"
            f"Je recherche maintenant le meilleur {info['category']} disponible près de {info['location']}. "
            "Je reviens vers vous dans quelques instants.")


def analyze_message(content, collected=None):
    collected = _update_collected(collected or {}, content)
    response = _build_response(collected, content)

    ready = all(k not in _has_missing(collected) for k in ["category", "location", "urgency", "availability"])

    return {
        "response": response,
        "category": collected.get("category"),
        "urgency": collected.get("urgency"),
        "collected_info": collected,
        "ready": ready,
        "needs_human": False,
        "needs_technician": ready,
    }
