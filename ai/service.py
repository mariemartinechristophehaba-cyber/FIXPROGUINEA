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

        context : dict avec 'history', 'user_id', 'role', 'conversation_id',
                              'active_request', etc.
        Retourne un dict {'response', 'intent', 'error', 'action', 'data'}
        """
        context = context or {}
        intent = router.detect_intent(message)

        # Soins specifiques pour les actions FixPro
        action_result = self._handle_action_intent(intent, message, context)
        if action_result:
            return action_result

        # Conversation generale avec historique et contexte
        history = context.get("history", [])
        conversation_id = context.get("conversation_id")
        if conversation_id and not history:
            history = tools.get_conversation_history(conversation_id)

        messages = self._build_messages(message, history, context)
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
                "action": None,
                "data": None,
            }

        return {
            "response": result["text"],
            "intent": intent,
            "error": None,
            "action": None,
            "data": None,
        }

    def _handle_action_intent(self, intent, message, context):
        """Gere les intentions qui necessitent un outil FixPro."""
        user_id = context.get("user_id")

        if intent == "follow_up" and user_id:
            return self._handle_follow_up(user_id)

        if intent == "cancel" and user_id:
            return self._handle_cancel(user_id, message, context)

        return None

    def _handle_follow_up(self, user_id):
        """Retourne le statut de la demande active du client."""
        active = tools.get_active_request(user_id)
        if not active:
            return {
                "response": "Je ne trouve pas de demande en cours. Souhaitez-vous en creer une ?",
                "intent": "follow_up",
                "error": None,
                "action": None,
                "data": None,
            }
        full = tools.get_request_full(active["id"])
        if full:
            tech = full.get("technician_name") or "non attribue"
            text = (f"Votre demande {full.get('reference')} est en statut "
                    f"{full.get('status')}. Technicien : {tech}.")
        else:
            text = f"Votre demande {active.get('reference')} est en statut {active.get('status')}."
        return {
            "response": text,
            "intent": "follow_up",
            "error": None,
            "action": None,
            "data": active,
        }

    def _handle_cancel(self, user_id, message, context):
        """Gere une demande d'annulation."""
        active = tools.get_active_request(user_id)
        if not active:
            return {
                "response": "Je ne trouve pas de demande en cours a annuler.",
                "intent": "cancel",
                "error": None,
                "action": None,
                "data": None,
            }

        # Confirmation implicite si le message contient 'oui' ou 'confirme'
        confirmed = any(w in message.lower() for w in ("oui", "confirme", "valide", "yes"))
        if not confirmed:
            return {
                "response": (f"Je peux annuler votre demande {active['reference']}. "
                             "Confirmez-vous ? (Oui / Non)"),
                "intent": "cancel",
                "error": None,
                "action": "awaiting_confirmation",
                "data": {"request_id": active["id"]},
            }

        ok, reason = tools.cancel_request(active["id"], user_id)
        if ok:
            return {
                "response": f"Votre demande {active['reference']} a ete annulee.",
                "intent": "cancel",
                "error": None,
                "action": "cancelled",
                "data": {"request_id": active["id"]},
            }
        return {
            "response": reason,
            "intent": "cancel",
            "error": None,
            "action": None,
            "data": None,
        }

    def _build_messages(self, message, history, context):
        """Construit la liste de messages pour le fournisseur."""
        messages = []

        # Contexte utilisateur et mission
        context_text = self._build_context_text(context)
        if context_text:
            messages.append({"role": "user", "content": context_text})

        # Historique recent
        for h in history[-6:]:
            if h.get("role") == "user" or h.get("user"):
                messages.append({"role": "user", "content": h.get("content") or h.get("user", "")})
            elif h.get("role") == "assistant" or h.get("assistant"):
                messages.append({"role": "assistant", "content": h.get("content") or h.get("assistant", "")})

        messages.append({"role": "user", "content": message})
        return messages

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
