"""Configuration du fournisseur et du modele IA.

Les cles API restent cote serveur. Le module ne les expose jamais
au client web ou mobile.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def get_ai_config():
    """Retourne la configuration IA depuis les variables d'environnement."""
    return {
        "provider": os.getenv("AI_PROVIDER", "gemini").strip().lower(),
        "model": os.getenv("AI_MODEL", "gemini-1.5-flash").strip(),
        "api_key": os.getenv("AI_API_KEY", os.getenv("GOOGLE_API_KEY", "")).strip(),
        "timeout": int(os.getenv("AI_TIMEOUT", "30")),
        "max_output_tokens": int(os.getenv("AI_MAX_TOKENS", "500")),
        "temperature": float(os.getenv("AI_TEMPERATURE", "0.7")),
    }
