"""Tests fonctionnels de FixPro.

Chaque test s'execute sur une base SQLite temporaire, isolee et jetable.
Lancement : python -m pytest tests/ -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["FLASK_ENV"] = "testing"
os.environ["FLASK_DEBUG"] = "0"
os.environ["SECRET_KEY"] = "cle-de-test-non-secrete"
os.environ["DATABASE_URL"] = ""

import db  # noqa: E402
import fixpro_app  # noqa: E402


class FixProTestCase(unittest.TestCase):
    """Socle commun : base temporaire + client HTTP."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "test.db")

        fixpro_app.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SQLITE_PATH=self.db_path,
            DATABASE_URL="",
        )
        fixpro_app.limiter.enabled = False

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.executescript(
                (ROOT / "schema_sqlite.sql").read_text(encoding="utf-8"))
            conn.commit()
        finally:
            conn.close()

        self.client = fixpro_app.app.test_client()

    def tearDown(self):
        self._tmpdir.cleanup()

    # -- utilitaires ----------------------------------------------------

    def register(self, email, password="motdepasse123", role="client",
                 name="Utilisateur Test"):
        return self.client.post("/register", data={
            "email": email, "password": password, "role": role,
            "full_name": name, "phone": "+224620000000", "city": "Conakry",
        }, follow_redirects=True)

    def login(self, email, password="motdepasse123"):
        return self.client.post("/login", data={
            "email": email, "password": password}, follow_redirects=True)


class HealthAndSecurityTests(FixProTestCase):

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_security_headers_present(self):
        headers = self.client.get("/").headers
        self.assertEqual(headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("Referrer-Policy", headers)

    def test_landing_page_is_public(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_unknown_page_returns_404(self):
        self.assertEqual(self.client.get("/page-inexistante").status_code, 404)

    def test_protected_page_redirects_anonymous_user(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


class RegistrationTests(FixProTestCase):

    def test_registration_then_login_succeeds(self):
        self.register("client@example.com")
        response = self.login("client@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_invalid_email_is_rejected(self):
        self.register("pas-un-email")
        self.assertEqual(self._count_users(), 0)

    def test_short_password_is_rejected(self):
        self.register("court@example.com", password="1234")
        self.assertEqual(self._count_users(), 0)

    def test_duplicate_email_is_rejected(self):
        self.register("double@example.com")
        self.register("double@example.com", name="Autre Personne")
        self.assertEqual(self._count_users(), 1)

    def test_password_is_never_stored_in_clear_text(self):
        self.register("secret@example.com", password="motdepasse123")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE email = ?",
                ("secret@example.com",)).fetchone()
        finally:
            conn.close()
        self.assertNotIn("motdepasse123", row["password_hash"])

    def test_wrong_password_does_not_authenticate(self):
        self.register("client@example.com")
        self.login("client@example.com", password="mauvaisMotDePasse")
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def _count_users(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        finally:
            conn.close()


class RequestWorkflowTests(FixProTestCase):
    """Parcours metier complet : demande, devis, paiement."""

    def setUp(self):
        super().setUp()
        self.register("client@example.com", role="client", name="Aminata Sow")
        self.client.get("/logout")
        self.register("artisan@example.com", role="artisan", name="Mamadou Bah")
        self.client.get("/logout")

    def test_client_can_create_request(self):
        self.login("client@example.com")
        response = self.client.post("/requests/new", data={
            "title": "Fuite d'eau", "description": "Fuite sous l'evier",
            "category": "Plombier", "address": "Kaloum", "budget": "75000",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._request_field(1, "status"), "pending")

    def test_diagnostic_price_comes_from_category(self):
        self.login("client@example.com")
        self._create_request()
        self.assertEqual(self._request_field(1, "diagnostic_price"), 50000)

    def test_full_workflow_from_request_to_payment(self):
        self.login("client@example.com")
        self._create_request()
        self.client.get("/logout")

        # L'artisan prend la demande en charge puis propose un devis.
        self.login("artisan@example.com")
        self.client.post("/requests/1/accept")
        self.assertEqual(self._request_field(1, "status"), "assigned")

        self.client.post("/requests/1/quote", data={
            "quote_amount": "250000",
            "quote_description": "Remplacement du siphon"})
        self.assertEqual(self._request_field(1, "quote_status"), "pending")
        self.client.get("/logout")

        # Le client accepte le devis, ce qui ouvre le paiement.
        self.login("client@example.com")
        self.client.post("/requests/1/quote/accept")
        self.assertEqual(self._request_field(1, "quote_status"), "accepted")
        self.assertEqual(self.client.get("/requests/1/payment").status_code, 200)

        self.client.post("/requests/1/payment/process", data={
            "amount": "250000", "method": "orange_money", "reference": "OM123"})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            payment = conn.execute("SELECT * FROM payments").fetchone()
        finally:
            conn.close()
        self.assertEqual(payment["amount"], 250000)
        self.assertEqual(payment["method"], "orange_money")

    def test_artisan_can_open_a_pending_request(self):
        """Sans cet acces, aucun artisan ne pourrait accepter une demande."""
        self.login("client@example.com")
        self._create_request()
        self.client.get("/logout")

        self.login("artisan@example.com")
        self.assertEqual(self.client.get("/requests/1").status_code, 200)

    def test_artisan_loses_access_once_request_is_taken_by_another(self):
        self.login("client@example.com")
        self._create_request()
        self.client.get("/logout")

        self.login("artisan@example.com")
        self.client.post("/requests/1/accept")
        self.client.get("/logout")

        self.register("autre.artisan@example.com", role="artisan",
                      name="Autre Artisan")
        self.login("autre.artisan@example.com")
        self.assertEqual(self.client.get("/requests/1").status_code, 302)

    def test_client_cannot_propose_quote(self):
        self.login("client@example.com")
        self._create_request()
        self.client.post("/requests/1/quote", data={
            "quote_amount": "1000", "quote_description": "Tentative"})
        self.assertEqual(self._request_field(1, "quote_status"), "none")

    def test_payment_blocked_until_quote_accepted(self):
        self.login("client@example.com")
        self._create_request()
        response = self.client.get("/requests/1/payment")
        self.assertEqual(response.status_code, 302)

    def test_third_party_cannot_read_someone_elses_request(self):
        self.login("client@example.com")
        self._create_request()
        self.client.get("/logout")

        self.register("intrus@example.com", role="client", name="Intrus")
        self.login("intrus@example.com")
        response = self.client.get("/requests/1")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/requests", response.headers["Location"])

    def _create_request(self):
        return self.client.post("/requests/new", data={
            "title": "Fuite d'eau", "description": "Fuite sous l'evier",
            "category": "Plombier", "address": "Kaloum", "budget": "75000",
        }, follow_redirects=True)

    def _request_field(self, request_id, field):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        finally:
            conn.close()
        return row[field] if row else None


class MessagingTests(FixProTestCase):
    """La messagerie doit empecher les echanges hors plateforme."""

    def test_phone_number_is_blocked(self):
        self.assertTrue(fixpro_app.is_prohibited_message(
            "Appelle moi au 622 33 44 55"))

    def test_external_platform_mention_is_blocked(self):
        self.assertTrue(fixpro_app.is_prohibited_message(
            "On continue sur WhatsApp"))

    def test_normal_message_is_allowed(self):
        self.assertFalse(fixpro_app.is_prohibited_message(
            "Bonjour, quand pouvez-vous passer pour la fuite ?"))


class DatabaseLayerTests(unittest.TestCase):
    """La traduction SQLite -> PostgreSQL doit etre fiable."""

    def test_placeholders_are_translated(self):
        self.assertEqual(
            db._translate("SELECT * FROM users WHERE id = ?", True),
            "SELECT * FROM users WHERE id = %s")

    def test_percent_is_escaped_when_parameters_are_present(self):
        self.assertEqual(
            db._translate("SELECT * FROM users WHERE email LIKE '%demo%'", True),
            "SELECT * FROM users WHERE email LIKE '%%demo%%'")

    def test_percent_is_left_alone_without_parameters(self):
        self.assertEqual(
            db._translate("SELECT * FROM users WHERE email LIKE '%demo%'", False),
            "SELECT * FROM users WHERE email LIKE '%demo%'")

    def test_question_mark_inside_a_string_is_preserved(self):
        self.assertEqual(
            db._translate("SELECT 'Ca va ?' WHERE id = ?", False),
            "SELECT 'Ca va ?' WHERE id = %s")

    def test_postgres_urls_are_recognised(self):
        self.assertTrue(db.is_postgres_url("postgresql://user@host/db"))
        self.assertTrue(db.is_postgres_url("postgres://user@host/db"))
        self.assertFalse(db.is_postgres_url(""))
        self.assertFalse(db.is_postgres_url("fixpro.db"))


class ConfigurationTests(unittest.TestCase):

    def test_secret_key_is_mandatory_in_production(self):
        import importlib

        import config

        saved = dict(os.environ)
        try:
            os.environ["FLASK_ENV"] = "production"
            os.environ["SECRET_KEY"] = ""
            importlib.reload(config)
            with self.assertRaises(RuntimeError):
                config.get_config()
        finally:
            os.environ.clear()
            os.environ.update(saved)
            importlib.reload(config)


if __name__ == "__main__":
    unittest.main()
