"""Abstraction des fournisseurs de modeles de langage.

Permet de changer de modele/fournisseur sans reecrire le reste
de l'application.
"""

import json
import logging
import os

import requests

from .config import get_ai_config

logger = logging.getLogger("fixpro")


class BaseProvider:
    """Interface commune pour tous les fournisseurs IA."""

    def generate(self, system_prompt, messages):
        """Genere une reponse a partir d'un system prompt et d'un historique.

        messages : liste de dict {'role': 'user'|'model', 'content': str}
        Retourne un dict {'text': str, 'error': str|None, 'provider': str}
        """
        raise NotImplementedError


class MockProvider(BaseProvider):
    """Fournisseur factice pour les tests, evite les appels reseau."""

    def __init__(self, config=None):
        self.config = config or {}

    def generate(self, system_prompt, messages):
        last = messages[-1]["content"] if messages else ""
        text = "Bien recu. Je vais vous aider."
        if "bonjour" in last.lower():
            text = "Bonjour ! Je suis Lia, l'assistante FixPro. Comment puis-je vous aider ?"
        elif "frigo" in last.lower():
            text = "Cela semble etre un probleme de refrigeration. Pouvez-vous me donner plus de details ?"
        elif "?" in last:
            text = "C'est une bonne question. Je vais essayer de vous repondre clairement."
        return {"text": text, "error": None, "provider": "mock"}


class GeminiProvider(BaseProvider):
    """Fournisseur Google Gemini (modele generative-language)."""

    def __init__(self, config):
        self.config = config

    def generate(self, system_prompt, messages):
        key = self.config["api_key"]
        model = self.config["model"]
        if not key:
            return {"text": "", "error": "Cle API manquante", "provider": "gemini"}

        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={key}")

        contents = []
        for m in messages:
            role = "model" if m["role"] in ("assistant", "model") else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": self.config["temperature"],
                "maxOutputTokens": self.config["max_output_tokens"],
            },
        }

        try:
            response = requests.post(url, json=payload, timeout=self.config["timeout"])
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return {"text": "", "error": "Reponse vide du modele", "provider": "gemini"}
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return {"text": "", "error": "Reponse vide du modele", "provider": "gemini"}
            return {
                "text": parts[0].get("text", "").strip(),
                "error": None,
                "provider": "gemini",
            }
        except requests.exceptions.Timeout:
            logger.warning("Timeout de l'appel a Gemini")
            return {"text": "", "error": "Le modele est trop lent", "provider": "gemini"}
        except requests.exceptions.HTTPError as e:
            logger.warning("Erreur HTTP Gemini: %s", e)
            return {"text": "", "error": "Erreur du modele IA", "provider": "gemini"}
        except Exception as e:
            logger.warning("Exception Gemini: %s", e)
            return {"text": "", "error": "Erreur inattendue", "provider": "gemini"}


def get_provider():
    """Retourne le fournisseur adapte a la configuration."""
    config = get_ai_config()
    provider = config["provider"]
    if os.getenv("FLASK_ENV", "").lower() == "testing" or os.getenv("AI_MOCK") == "1":
        return MockProvider(config)
    if provider == "gemini":
        return GeminiProvider(config)
    raise ValueError(f"Fournisseur IA non supporte: {provider}")
