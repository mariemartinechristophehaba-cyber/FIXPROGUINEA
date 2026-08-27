"""Routage d'intention pour l'assistant FixPro.

Classification simple basee sur les mots-cles. L'objectif est d'orienter
la conversation sans empecher le modele de repondre librement.
"""

import re


_INTENT_PATTERNS = {
    "greeting": [r"\bbonjour\b", r"\bsalut\b", r"\bhello\b", r"\bhey\b", r"\bbonsoir\b"],
    "farewell": [r"\bau revoir\b", r"\ba bientot\b", r"\bciao\b", r"\bbye\b"],
    "thanks": [r"\bmerci\b", r"\bthanks\b"],
    "intervention": [r"\bintervention\b", r"\breparer\b", r"\bdepanner\b", r"\bfuite\b", r"\bpanne\b"],
    "follow_up": [r"\bstatut\b", r"\bou en est\b", r"\bmission\b", r"\bdemande\b"],
    "cancel": [r"\bannul\b", r"\bsupprim\b"],
    "price": [r"\bprix\b", r"\btarif\b", r"\bcombien\b", r"\bdevis\b"],
    "help": [r"\baide\b", r"\bcomment\b", r"\bquestion\b"],
}


def detect_intent(text):
    """Retourne l'intention principale detectee et un score."""
    text_lower = (text or "").lower()
    scores = {k: 0 for k in _INTENT_PATTERNS}
    for intent, patterns in _INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                scores[intent] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "general"
    return best
