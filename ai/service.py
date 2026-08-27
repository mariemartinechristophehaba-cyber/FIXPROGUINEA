"""Orchestration de l'assistant FixPro."""

import logging

from . import prompts, providers, router, tools

logger = logging.getLogger("fixpro")


class Assistant:
    """Assistant conversationnel de FixPro."""

    def __init__(self, role="client"):
        self.provider = providers.get_provider()
        self.role = role
        self.system_prompt = prompts.build_system_prompt(role)

    def respond(self, message, context=None):
        """Genere une reponse a un message donne.

        context : dict avec 'history' (liste de messages), 'user_id', 'role', etc.
        Retourne un dict {'response', 'intent', 'error', 'collected', 'ready'}
        """
        context = context or {}
        history = context.get("history", [])
        intent = router.detect_intent(message)

        messages = []
        for h in history[-6:]:
            messages.append({"role": "user", "content": h.get("user", "")})
            if h.get("assistant"):
                messages.append({"role": "assistant", "content": h["assistant"]})
        messages.append({"role": "user", "content": message})

        # Contexte supplementaire (mission, compte)
        context_text = self._build_context_text(context)
        if context_text:
            messages.insert(0, {"role": "user", "content": context_text})

        result = self.provider.generate(self.system_prompt, messages)
        if result.get("error"):
            logger.warning("Erreur IA: %s", result["error"])
            return {
                "response": (
                    "Je rencontre momentanement un probleme. "
                    "Reessayez dans quelques instants."
                ),
                "intent": intent,
                "error": result["error"],
                "collected": {},
                "ready": False,
            }

        return {
            "response": result["text"],
            "intent": intent,
            "error": None,
            "collected": {},
            "ready": False,
        }

    def _build_context_text(self, context):
        """Construit un texte de contexte securise pour le modele."""
        parts = []
        user_id = context.get("user_id")
        if user_id:
            user = tools.get_current_user_context(user_id)
            if user:
                parts.append(f"Utilisateur : {user.get('full_name')} ({user.get('role')}).")

        active = None
        if context.get("active_request"):
            active = tools.get_request_status(context["active_request"])
        elif user_id:
            active = tools.get_active_request(user_id)

        if active:
            parts.append(
                f"Demande active : {active.get('reference')} - {active.get('status')} - {active.get('title')}."
            )

        return "\n".join(parts) if parts else ""
