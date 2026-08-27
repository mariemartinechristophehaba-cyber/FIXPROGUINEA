"""Tests du module ai de FixPro."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["FLASK_ENV"] = "testing"
os.environ["FLASK_DEBUG"] = "0"
os.environ["SECRET_KEY"] = "cle-de-test-non-secrete"
os.environ["DATABASE_URL"] = ""

import db
from ai import Assistant
from ai import knowledge, prompts, router, tools


class AIProviderTests(unittest.TestCase):
    """Tests des fournisseurs IA."""

    def test_mock_provider_answers(self):
        from ai.providers import MockProvider
        p = MockProvider()
        r = p.generate("Tu es un assistant.", [{"role": "user", "content": "Bonjour"}])
        self.assertIsNone(r["error"])
        self.assertTrue(len(r["text"]) > 0)


class AIRouterTests(unittest.TestCase):
    """Tests du routeur d'intention."""

    def test_greeting_intent(self):
        self.assertEqual(router.detect_intent("Bonjour"), "greeting")

    def test_intervention_intent(self):
        self.assertEqual(router.detect_intent("J'ai une fuite"), "intervention")

    def test_cancel_intent(self):
        self.assertEqual(router.detect_intent("Je veux annuler"), "cancel")

    def test_follow_up_intent(self):
        self.assertEqual(router.detect_intent("Ou en est ma mission"), "follow_up")


class AIKnowledgeTests(unittest.TestCase):
    """Tests de la base de connaissances."""

    def test_knowledge_has_presentation(self):
        text = knowledge.get_knowledge("presentation")
        self.assertIn("FixPro", text)


class AIToolsTests(unittest.TestCase):
    """Tests des outils backend."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "test_ai.db")

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.executescript(
                (ROOT / "schema_sqlite.sql").read_text(encoding="utf-8"))
            conn.commit()
        finally:
            conn.close()

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_verified, is_active, account_status) "
                "VALUES (?, ?, ?, ?, ?, 1, 1, 'ACTIVE')",
                ("client@test.gn", "+224620000001", "hash", "client", "Client Test"))
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, profession, is_verified, is_active, account_status) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, 1, 'ACTIVE')",
                ("tech@test.gn", "+224620000002", "hash", "technician", "Tech Test", "Plombier"))
            conn.commit()
        finally:
            conn.close()

        os.environ["FIXPRO_DB_PATH"] = self.db_path

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_active_request_empty(self):
        from ai.tools import get_active_request
        r = get_active_request(1)
        self.assertIsNone(r)

    def test_create_support_ticket(self):
        from ai.tools import create_support_ticket
        ticket_id = create_support_ticket(1, "Sujet", "Message")
        self.assertIsNotNone(ticket_id)


class AIAssistantTests(unittest.TestCase):
    """Tests de l'assistant conversationnel."""

    def test_greeting_response(self):
        a = Assistant(role="client")
        r = a.respond("Bonjour")
        self.assertIn("Bonjour", r["response"])

    def test_familiar_language_understood(self):
        a = Assistant(role="client")
        r = a.respond("komen tu tapel")
        self.assertTrue(len(r["response"]) > 0)
        self.assertEqual(r["error"], None)

    def test_error_message_when_provider_fails(self):
        from ai.providers import BaseProvider

        class FailingProvider(BaseProvider):
            def generate(self, system_prompt, messages):
                return {"text": "", "error": "boom", "provider": "fail"}

        a = Assistant(role="client")
        a.provider = FailingProvider()
        r = a.respond("Bonjour")
        self.assertIn("probleme", r["response"].lower())


if __name__ == "__main__":
    unittest.main()
