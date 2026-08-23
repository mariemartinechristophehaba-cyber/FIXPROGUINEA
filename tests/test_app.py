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
            BYPASS_AUTH=False,
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

    def register_client(self, phone="+224620000000", password="FixPro2026!",
                        first_name="Aminata", last_name="Sow", city="Conakry"):
        return self.client.post("/register?role=client", data={
            "role": "client",
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "city": city,
            "password": password,
        }, follow_redirects=True)

    def register_artisan(self, email, phone="+224621111111", password="FixPro2026!",
                         name="Mamadou Bah", last_name=None):
        doc = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

        self.client.get("/register/artisan")

        response = self.client.post("/register/artisan", data={
            "full_name": name,
            "profession": "Plombier",
            "phone": phone,
            "address": "Conakry",
            "identity_doc": doc,
        }, follow_redirects=True)

        # Valide automatiquement l'artisan pour les tests.
        conn = db.connect(sqlite_path=self.db_path)
        try:
            user = conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
            if user:
                conn.execute(
                    "UPDATE users SET is_verified = 1, is_active = 1, email = ?,"
                    " password_hash = ? WHERE id = ?",
                    (email, fixpro_app.generate_password_hash(password), user["id"]))
                conn.commit()
        finally:
            conn.close()
        return response

    def login(self, identifier, password="FixPro2026!"):
        return self.client.post("/login", data={
            "identifier": identifier, "password": password},
            follow_redirects=True)


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
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


class ClientRegistrationTests(FixProTestCase):

    def test_client_register_then_login_with_phone_succeeds(self):
        self.register_client()
        response = self.login("+224620000000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/artisans").status_code, 200)

    def test_client_inscription_requires_all_fields(self):
        self.client.post("/register?role=client", data={
            "role": "client", "first_name": "Aminata", "last_name": "",
            "phone": "+224620000000", "city": "Conakry", "password": "mdp123"})
        self.assertEqual(self._count_users(), 0)

    def test_short_password_is_rejected(self):
        self.register_client(password="12345")
        self.assertEqual(self._count_users(), 0)

    def test_duplicate_phone_is_rejected(self):
        self.register_client(phone="+224620000000")
        self.register_client(phone="+224620000000", first_name="Fatou")
        self.assertEqual(self._count_users(), 1)

    def test_password_is_never_stored_in_clear_text(self):
        self.register_client(phone="+224620000001")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE phone = ?",
                ("+224620000001",)).fetchone()
        finally:
            conn.close()
        self.assertNotIn("FixPro2026!", row["password_hash"])

    def test_client_is_redirected_to_artisans_after_login(self):
        self.register_client()
        response = self.login("+224620000000")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Techniciens", response.data)

    def _count_users(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        finally:
            conn.close()


class ArtisanRegistrationTests(FixProTestCase):

    def test_artisan_register_then_login_with_email_succeeds(self):
        self.register_artisan("artisan@example.com")
        response = self.login("artisan@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/requests").status_code, 200)

    def test_artisan_invalid_email_is_rejected(self):
        self.client.post("/register?role=artisan", data={
            "role": "artisan", "full_name": "Mamadou Bah",
            "email": "pas-un-email", "phone": "+224621111111",
            "profession": "Plombier", "city": "Conakry", "password": "mdp123"})
        self.assertEqual(self._count_users(), 0)

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
        self.register_client(phone="+224620000000")
        self.client.get("/logout")
        self.register_artisan("artisan@example.com", phone="+224621111111")
        self.client.get("/logout")

    def test_client_can_create_request(self):
        self.login("+224620000000")
        response = self.client.post("/requests/new", data={
            "title": "Fuite d'eau", "description": "Fuite sous l'evier",
            "category": "Plombier", "address": "Kaloum", "budget": "75000",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        # La demande est maintenant automatiquement assignee a un artisan
        self.assertEqual(self._request_field(1, "status"), "assigned")

    def test_diagnostic_price_comes_from_category(self):
        self.login("+224620000000")
        self._create_request()
        self.assertEqual(self._request_field(1, "diagnostic_price"), 50000)

    def test_full_workflow_from_request_to_payment(self):
        self.login("+224620000000")
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
        self.login("+224620000000")
        self.client.post("/requests/1/quote/accept")
        self.assertEqual(self._request_field(1, "quote_status"), "accepted")
        self.assertEqual(self.client.get("/requests/1/payment").status_code, 200)

        self.client.post("/requests/1/payment/process", data={
            "amount": "250000", "method": "orange_money",
            "reference": "OM123", "payment_info": "622 000 000"})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            payment = conn.execute("SELECT * FROM payments").fetchone()
        finally:
            conn.close()
        self.assertEqual(payment["amount"], 250000)
        self.assertEqual(payment["method"], "orange_money")
        self.assertEqual(payment["details"], "622 000 000")

    def test_payment_by_card_masks_pan(self):
        self.login("+224620000000")
        self._create_request()
        self.client.get("/logout")

        self.login("artisan@example.com")
        self.client.post("/requests/1/accept")
        self.client.post("/requests/1/quote", data={
            "quote_amount": "150000",
            "quote_description": "Reparation robinet"})
        self.client.get("/logout")

        self.login("+224620000000")
        self.client.post("/requests/1/quote/accept")
        self.client.post("/requests/1/payment/process", data={
            "amount": "150000", "method": "card", "payment_info": "4242424242424242"})

        conn = db.connect(sqlite_path=self.db_path)
        try:
            payment = conn.execute("SELECT * FROM payments").fetchone()
        finally:
            conn.close()
        self.assertEqual(payment["method"], "card")
        self.assertIn("4242", payment["details"])
        self.assertNotIn("4242424242424242", payment["details"])

    def test_payments_page_shows_history_and_totals(self):
        self.login("+224620000000")
        self._create_request()
        self.client.get("/logout")

        self.login("artisan@example.com")
        self.client.post("/requests/1/accept")
        self.client.post("/requests/1/quote", data={
            "quote_amount": "100000",
            "quote_description": "Changement joint"})
        self.client.get("/logout")

        self.login("+224620000000")
        self.client.post("/requests/1/quote/accept")
        self.client.post("/requests/1/payment/process", data={
            "amount": "100000", "method": "mtn_mobile_money",
            "payment_info": "630 111 111"})

        response = self.client.get("/payments")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"100 000", response.data)
        self.assertIn(b"MTN Mobile Money", response.data)

    def test_artisan_can_open_a_pending_request(self):
        self.login("+224620000000")
        self._create_request()
        self.client.get("/logout")

        self.login("artisan@example.com")
        self.assertEqual(self.client.get("/requests/1").status_code, 200)

    def test_artisan_loses_access_once_request_is_taken_by_another(self):
        self.login("+224620000000")
        self._create_request()
        self.client.get("/logout")

        self.login("artisan@example.com")
        self.client.post("/requests/1/accept")
        self.client.get("/logout")

        self.register_artisan("autre@example.com", phone="+224622222222",
                              name="Autre Artisan")
        self.login("autre@example.com")
        self.assertEqual(self.client.get("/requests/1").status_code, 302)

    def test_client_cannot_propose_quote(self):
        self.login("+224620000000")
        self._create_request()
        self.client.post("/requests/1/quote", data={
            "quote_amount": "1000", "quote_description": "Tentative"})
        self.assertEqual(self._request_field(1, "quote_status"), "none")

    def test_payment_blocked_until_quote_accepted(self):
        self.login("+224620000000")
        self._create_request()
        response = self.client.get("/requests/1/payment")
        self.assertEqual(response.status_code, 302)

    def test_third_party_cannot_read_someone_elses_request(self):
        self.login("+224620000000")
        self._create_request()
        self.client.get("/logout")

        self.register_client(phone="+224623333333", first_name="Intrus")
        self.login("+224623333333")
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
    """La messagerie client <-> admin."""

    def setUp(self):
        super().setUp()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " is_verified, is_active) VALUES (?, ?, ?, 'admin', ?, 1, 1)",
                ("admin@fixpro.local", "+224000000000",
                 fixpro_app.generate_password_hash("adminpass"), "Administrateur"))
            conn.commit()
        finally:
            conn.close()

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1

    def test_phone_number_is_blocked(self):
        self.assertTrue(fixpro_app.is_prohibited_message(
            "Appelle moi au 622 33 44 55"))

    def test_external_platform_mention_is_blocked(self):
        self.assertTrue(fixpro_app.is_prohibited_message(
            "On continue sur WhatsApp"))

    def test_normal_message_is_allowed(self):
        self.assertFalse(fixpro_app.is_prohibited_message(
            "Bonjour, quand pouvez-vous passer pour la fuite ?"))

    def test_client_conversation_persists(self):
        self.register_client(phone="+224610000000")
        self.login("+224610000000")
        r = self.client.post("/messages/new", data={
            "subject": "Probleme clim",
            "content": "Mon climatiseur ne refroidit plus."
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conv = conn.execute("SELECT * FROM conversations WHERE client_id = 2").fetchone()
            self.assertIsNotNone(conv)
            msg = conn.execute("SELECT * FROM conversation_messages WHERE conversation_id = ?", (conv["id"],)).fetchone()
            self.assertEqual(msg["content"], "Mon climatiseur ne refroidit plus.")
            self.assertEqual(msg["sender_role"], "client")
        finally:
            conn.close()

    def test_admin_can_reply_and_client_reads(self):
        self.register_client(phone="+224610000000")
        self.login("+224610000000")
        r = self.client.post("/messages/new", data={
            "subject": "Probleme",
            "content": "Bonjour, j'ai besoin d'aide."
        }, follow_redirects=True)
        conv_id = int(r.request.path.split("/")[-1])

        self.client.get("/logout")
        self._login_admin()
        r = self.client.post(f"/admin/messages/{conv_id}", data={
            "content": "Bonjour, nous vous repondrons rapidement."
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            msgs = conn.execute(
                "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY id",
                (conv_id,)).fetchall()
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[1]["sender_role"], "admin")
            self.assertEqual(msgs[1]["content"], "Bonjour, nous vous repondrons rapidement.")
            notif = conn.execute(
                "SELECT * FROM notifications WHERE user_id = 2").fetchone()
            self.assertIsNotNone(notif)
        finally:
            conn.close()

    def test_other_client_cannot_read_conversation(self):
        self.register_client(phone="+224610000000")
        self.login("+224610000000")
        r = self.client.post("/messages/new", data={
            "content": "Message prive"
        }, follow_redirects=True)
        conv_id = int(r.request.path.split("/")[-1])

        self.client.get("/logout")
        self.register_client(phone="+224610000001")
        self.login("+224610000001")
        r = self.client.get(f"/messages/{conv_id}")
        self.assertEqual(r.status_code, 302)

    def test_guest_can_message_artisan(self):
        self.register_artisan("artisan@example.com", phone="+224621111111")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = conn.execute(
                "SELECT id FROM users WHERE phone = ?", ("+224621111111",)).fetchone()
        finally:
            conn.close()
        self.client.get("/logout")
        r = self.client.get(f"/messages/artisan/{artisan['id']}", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conv = conn.execute(
                "SELECT * FROM conversations WHERE artisan_id = ?",
                (artisan["id"],)).fetchone()
            self.assertIsNotNone(conv)
            msgs = conn.execute(
                "SELECT * FROM conversation_messages WHERE conversation_id = ?",
                (conv["id"],)).fetchall()
            self.assertEqual(len(msgs), 0)
            user = conn.execute(
                "SELECT role, full_name FROM users WHERE id = ?",
                (conv["client_id"],)).fetchone()
            self.assertEqual(user["role"], "client")
            self.assertEqual(user["full_name"], "Visiteur")
        finally:
            conn.close()

    def test_guest_conversation_persists_after_refresh(self):
        self.register_artisan("artisan@example.com", phone="+224621111111")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = conn.execute(
                "SELECT id FROM users WHERE phone = ?", ("+224621111111",)).fetchone()
        finally:
            conn.close()
        self.client.get("/logout")
        r1 = self.client.get(f"/messages/artisan/{artisan['id']}", follow_redirects=True)
        self.assertEqual(r1.status_code, 200)
        conv_id = int(r1.request.path.split("/")[-1])

        r2 = self.client.get(f"/messages/{conv_id}")
        self.assertEqual(r2.status_code, 200)

        r3 = self.client.post(f"/messages/{conv_id}", data={
            "content": "Mon climatiseur ne refroidit plus."}, follow_redirects=True)
        self.assertEqual(r3.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            msgs = conn.execute(
                "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY id",
                (conv_id,)).fetchall()
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["sender_role"], "client")
            self.assertEqual(msgs[0]["content"], "Mon climatiseur ne refroidit plus.")
        finally:
            conn.close()


class GeolocationTests(FixProTestCase):
    """Geolocalisation temps reel des techniciens."""

    def setUp(self):
        super().setUp()
        self.register_artisan("artisan@example.com", phone="+224621111111")
        self.client.get("/logout")

    def test_artisan_can_update_availability_status(self):
        self.login("artisan@example.com")
        response = self.client.post("/api/technicien/status", data={
            "status": "en_ligne"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ok"], True)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT availability_status FROM users WHERE phone = ?",
                ("+224621111111",)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["availability_status"], "en_ligne")

    def test_position_stored_only_when_artisan_is_online(self):
        self.login("artisan@example.com")
        self.client.post("/api/technicien/status", data={"status": "en_ligne"})
        response = self.client.post("/api/technicien/position", data={
            "lat": "9.5", "lon": "-13.7"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ok"], True)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM technician_locations").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row["latitude"], 9.5)
        self.assertAlmostEqual(row["longitude"], -13.7)

    def test_position_ignored_when_artisan_is_offline(self):
        self.login("artisan@example.com")
        response = self.client.post("/api/technicien/position", data={
            "lat": "9.5", "lon": "-13.7"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ok"], False)

    def test_client_can_read_artisan_position(self):
        # Artisan en ligne avec position.
        self.login("artisan@example.com")
        self.client.post("/api/technicien/status", data={"status": "en_ligne"})
        self.client.post("/api/technicien/position", data={
            "lat": "9.5", "lon": "-13.7"})
        self.client.get("/logout")

        # Client consulte le profil.
        self.register_client(phone="+224620000000")
        response = self.client.get("/artisans/1")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/technicien/1/position")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertAlmostEqual(data["latitude"], 9.5)
        self.assertAlmostEqual(data["longitude"], -13.7)

    def test_client_cannot_read_expired_position(self):
        self.login("artisan@example.com")
        self.client.post("/api/technicien/status", data={"status": "en_ligne"})
        self.client.get("/logout")

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO technician_locations"
                " (technician_id, latitude, longitude, updated_at)"
                " VALUES (?, ?, ?, datetime('now', '-4 minutes'))",
                (1, 9.5, -13.7))
            conn.commit()
        finally:
            conn.close()

        response = self.client.get("/api/technicien/1/position")
        self.assertEqual(response.status_code, 404)


class AdminPanelTests(FixProTestCase):
    """Panneau administrateur : acces, actions et logs."""

    def setUp(self):
        super().setUp()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " is_verified, is_active) VALUES (?, ?, ?, 'admin', ?, 1, 1)",
                ("admin@fixpro.local", "+224000000000",
                 fixpro_app.generate_password_hash("adminpass"), "Administrateur"))
            conn.commit()
        finally:
            conn.close()

    def login_admin(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1

    def test_non_admin_cannot_access_dashboard(self):
        self.register_client(phone="+224620000000")
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location)

    def test_admin_logs_contain_email(self):
        self.register_artisan("artisan@example.com", phone="+224621111111")
        self.login_admin()

        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = conn.execute(
                "SELECT id FROM users WHERE role = 'artisan'").fetchone()
            artisan_id = artisan["id"]
        finally:
            conn.close()

        self.client.post("/admin/artisans", data={
            "action": "suspend", "artisan_id": str(artisan_id)}, follow_redirects=True)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            log = conn.execute(
                "SELECT admin_email FROM admin_logs WHERE action = 'suspend'").fetchone()
        finally:
            conn.close()
        self.assertEqual(log["admin_email"], "admin@fixpro.local")

    def test_admin_dashboard_renders(self):
        self.login_admin()
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("FixPro".encode(), response.data)
        self.assertIn("Admin".encode(), response.data)

    def test_admin_can_suspend_and_restore_artisan(self):
        self.register_artisan("artisan@example.com", phone="+224621111111")
        self.login_admin()

        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = conn.execute(
                "SELECT id FROM users WHERE role = 'artisan'").fetchone()
            artisan_id = artisan["id"]
        finally:
            conn.close()

        response = self.client.post("/admin/artisans", data={
            "action": "suspend", "artisan_id": str(artisan_id)}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            updated = conn.execute(
                "SELECT is_active FROM users WHERE id = ?", (artisan_id,)).fetchone()
            self.assertEqual(updated["is_active"], 0)
            log = conn.execute("SELECT * FROM admin_logs WHERE action = 'suspend'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(log)

    def test_admin_can_close_ticket(self):
        self.login_admin()
        self.register_client(phone="+224620000000")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO admin_tickets (client_id, message, status)"
                " VALUES (?, ?, 'open')", (1, "Probleme signale"))
            conn.commit()
        finally:
            conn.close()

        response = self.client.post("/admin/tickets", data={
            "action": "close", "ticket_id": "1"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)


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
