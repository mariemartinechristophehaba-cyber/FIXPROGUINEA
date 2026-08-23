"""Assistant conversationnel FixPro.

Logique rule-basee avec un ton humain et professionnel.
"""

_DOMAINS = {
    "electricite": ["electricite", "electrique", "cablage", "tableau", "disjoncteur", "prise", "interrupteur", "panne de courant", "court-circuit", "eclairage"],
    "plomberie": ["plomberie", "plombier", "fuite", "robinet", "evier", "lavabo", "douche", "wc", "toilettes", "tuyau", "canalisation", "sanitaire"],
    "climatisation": ["climatisation", "climatiseur", "clim", "air", "conditionneur", "ventilation"],
    "refrigeration": ["refrigeration", "frigo", "refrigerateur", "congelateur", "froid"],
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
    text = (text or "").lower()
    for c in "'’-":
        text = text.replace(c, " ")
    return text


def _is_greeting(text):
    words = text.split()
    greetings = ("bonjour", "salut", "hello", "coucou", "bonsoir", "bonne", "bonne", "soir", "matin")
    return not text or any(g in words for g in greetings) or len(words) <= 2


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

    loc = _extract_location(content)
    if loc:
        info["location"] = loc

    urg = _detect_urgency(content)
    if urg:
        info["urgency"] = urg

    av = _extract_availability(content)
    if av:
        info["availability"] = av

    # Conserve la vraie description du probleme, pas une reponse courte
    prob = content.strip()
    words = prob.split()
    has_keyword = bool(dom or loc or urg or av)
    if len(prob) > 5 and len(words) >= 3 and not _is_greeting(prob) and not has_keyword:
        info["problem_detail"] = prob
    elif not info.get("problem_detail") and len(prob) > 5 and not _is_greeting(prob):
        info["problem_detail"] = prob

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
    words = last.split()
    greetings = ("bonjour", "salut", "hello", "coucou", "bonsoir", "bonne", "soir", "matin")
    is_greeting = not last or any(g in words for g in greetings) or len(words) <= 2

    if is_greeting and not info.get("category"):
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

    detail = info.get("problem_detail") or "votre demande"
    return ("Merci pour toutes ces informations.\n\n"
            f"J'ai bien compris : {detail}.\n"
            f"Je recherche maintenant le meilleur professionnel en {info['category']} disponible près de {info['location']}. "
            "Je reviens vers vous dans quelques instants.")


def analyze_message(content, collected=None):
    collected = _update_collected(collected or {}, content)
    response = _build_response(collected, content)

    missing = _has_missing(collected)
    ready = all(k not in missing for k in ["category", "location", "urgency", "availability"])

    return {
        "response": response,
        "category": collected.get("category"),
        "urgency": collected.get("urgency"),
        "collected_info": collected,
        "ready": ready,
        "needs_human": False,
        "needs_technician": ready,
    }
