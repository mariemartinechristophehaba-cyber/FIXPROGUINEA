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
            # Verifie que le bouton retour pointe vers le profil du technicien.
            html = r.data.decode('utf-8', 'replace')
            self.assertIn(f'/technicien/{artisan["id"]}', html)
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
            self.assertEqual(len(msgs), 3)
            self.assertEqual(msgs[0]["sender_role"], "client")
            self.assertEqual(msgs[0]["content"], "Mon climatiseur ne refroidit plus.")
            self.assertEqual(msgs[2]["sender_role"], "system")
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

    def test_client_location_outside_conakry_no_wanindara(self):
        """Une position au Ghana ne doit plus retomber sur Wanindara."""
        response = self.client.post("/api/location", json={
            "lat": 5.6, "lon": -0.18, "accuracy": 1000})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["ok"], True)
        self.assertIsNotNone(data["zone"])
        self.assertNotIn("wanindara", data["zone"].lower())
        self.assertNotIn("conakry", data["zone"].lower())

    def test_client_location_conakry_returns_zone(self):
        """Une position a Kaloum retourne bien le quartier Kaloum."""
        response = self.client.post("/api/location", json={
            "lat": 9.5077, "lon": -13.7114, "accuracy": 100})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["zone"], "Kaloum")

    def test_client_manual_zone_updates_session(self):
        """La localisation manuelle persiste en session."""
        response = self.client.post("/api/location/zone", json={"zone": "Kaloum"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["ok"], True)
        self.assertIsNotNone(data["zone"])
        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get("client_zone"))
            self.assertIsNotNone(sess.get("client_lat"))
            self.assertIsNotNone(sess.get("client_lon"))


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

    def test_admin_dashboard_shows_real_counts(self):
        self.register_artisan("artisan@example.com", phone="+224621111111")
        self.login_admin()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "UPDATE users SET availability_status = ? WHERE role = ?",
                ("en_ligne", "artisan"))
            ref = fixpro_app._generate_fixpro_reference(conn)
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, urgency, quote_amount, budget, latitude, longitude, created_at, updated_at)"
                " VALUES (1, 1, ?, 'Titre', 'Desc', 'plomberie', 'Kaloum', 'REQUESTED', 'normal', 0, 0, 0, 0, datetime('now'), datetime('now'))",
                (ref,))
            conn.commit()
        finally:
            conn.close()

        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn("Nouvelle demande", html)
        self.assertIn("Disponible", html)

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


class DomainTests(FixProTestCase):
    """Verifie que l'IA et l'attribution respectent strictement les domaines."""

    def _insert_artisan(self, full_name, profession, lat, lon, verified=True, active=True):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            suffix = f"{abs(hash(full_name)) % 1000000:06d}"
            uid = fixpro_app._insert_id(conn, "INSERT INTO users (full_name, phone, email, password_hash, role, profession, city, latitude, longitude, is_verified, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (full_name, f"+22462{suffix}", f"{full_name.replace(' ', '')}@t.com", fixpro_app.generate_password_hash("FixPro2026!"), "artisan", profession, "Conakry", lat, lon, 1 if verified else 0, 1 if active else 0))
            conn.commit()
            return uid
        finally:
            conn.close()

    def test_ai_detects_climatisation_not_plumber(self):
        r = fixpro_app.ai_service.analyze_message("Mon climatiseur ne refroidit plus", collected={})
        self.assertEqual(r["category"], "climatisation")
        self.assertNotEqual(r["category"], "plomberie")

    def test_ai_detects_refrigeration_for_fridge(self):
        r = fixpro_app.ai_service.analyze_message("J'ai une panne sur mon frigo", collected={})
        self.assertEqual(r["category"], "refrigeration")

    def test_ai_detects_serrurerie_for_lock(self):
        r = fixpro_app.ai_service.analyze_message("Ma serrure est bloquee", collected={})
        self.assertEqual(r["category"], "serrurerie")

    def test_ai_detects_electricity_for_socket(self):
        r = fixpro_app.ai_service.analyze_message("Ma prise ne fonctionne plus", collected={})
        self.assertEqual(r["category"], "electricite")

    def test_ai_detects_plumber_for_leak(self):
        r = fixpro_app.ai_service.analyze_message("J'ai une fuite sous mon evier", collected={})
        self.assertEqual(r["category"], "plomberie")

    def test_technician_selection_never_changes_domain(self):
        self._insert_artisan("Plombier Proche", "Plombier", 9.5077, -13.7114)
        self._insert_artisan("Electricien Loin", "Électricien", 9.5077, -13.7114)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = fixpro_app._select_best_technician(conn, "electricite", "Kaloum")
            self.assertIsNotNone(artisan)
            self.assertNotIn("plomb", artisan["profession"].lower())
            self.assertIn("electric", artisan["profession"].lower().replace("é", "e"))
        finally:
            conn.close()

    def test_no_cross_domain_when_target_unavailable(self):
        self._insert_artisan("Plombier Seul", "Plombier", 9.5077, -13.7114)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = fixpro_app._select_best_technician(conn, "serrurerie", "Kaloum")
            self.assertIsNone(artisan)
        finally:
            conn.close()

    def test_client_gps_preferred_for_distance(self):
        self._insert_artisan("Plombier Proche", "Plombier", 9.5010, -13.7010)
        self._insert_artisan("Plombier Loin", "Plombier", 9.5500, -13.7500)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = fixpro_app._select_best_technician(conn, "plomberie", "Kaloum", client_lat=9.5012, client_lon=-13.7012)
            self.assertIsNotNone(artisan)
            self.assertEqual(artisan["full_name"], "Plombier Proche")
        finally:
            conn.close()

    def test_detects_plumber_for_leak_under_sink(self):
        r = fixpro_app.ai_service.analyze_message("J'ai une fuite sous mon evier", collected={})
        self.assertEqual(r["category"], "plomberie")

    def test_detects_electrician_for_tripping_breaker(self):
        r = fixpro_app.ai_service.analyze_message("Mon disjoncteur saute quand je branche mon climatiseur", collected={})
        self.assertEqual(r["category"], "electricite")

    def test_detects_refrigeration_for_fridge_not_cold(self):
        r = fixpro_app.ai_service.analyze_message("Mon frigo ne fait plus de froid", collected={})
        self.assertEqual(r["category"], "refrigeration")

    def test_detects_air_conditioning_for_ac_not_cold(self):
        r = fixpro_app.ai_service.analyze_message("Ma clim ne refroidit plus", collected={})
        self.assertIn(r["category"], ("climatisation", "refrigeration"))

    def test_detects_locksmith_for_broken_key(self):
        r = fixpro_app.ai_service.analyze_message("Ma cle est bloquee dans la serrure", collected={})
        self.assertEqual(r["category"], "serrurerie")

    def test_detects_carpenter_for_wooden_door(self):
        r = fixpro_app.ai_service.analyze_message("Ma porte en bois est cassee", collected={})
        self.assertEqual(r["category"], "menuiserie")

    def test_air_conditioning_not_plumber(self):
        r = fixpro_app.ai_service.analyze_message("Mon climatiseur ne refroidit plus", collected={})
        self.assertNotEqual(r["category"], "plomberie")

    def test_leak_not_electrician(self):
        r = fixpro_app.ai_service.analyze_message("Mon robinet fuit", collected={})
        self.assertNotEqual(r["category"], "electricite")


class LiaConversationTests(FixProTestCase):
    """Tests du moteur conversationnel de Lia."""

    def test_greeting_without_technical_question(self):
        r = fixpro_app.ai_service.analyze_message("Bonjour", collected={})
        self.assertIn("FixPro", r["response"])
        self.assertIsNone(r["category"])
        self.assertFalse(r["ready"])

    def test_small_talk_does_not_force_technician(self):
        r = fixpro_app.ai_service.analyze_message("Ca va ?", collected={})
        self.assertIn("va", r["response"].lower())
        self.assertIsNone(r["category"])
        self.assertFalse(r["ready"])

    def test_personal_question_returns_identity(self):
        r = fixpro_app.ai_service.analyze_message("Tu es mariee ?", collected={})
        self.assertIn("Lia", r["response"])
        self.assertIn("FixPro", r["response"])
        self.assertFalse(r["ready"])

    def test_emotion_recognition(self):
        r = fixpro_app.ai_service.analyze_message("Je suis vraiment stresse", collected={})
        self.assertIn("desole", r["response"].lower())

    def test_technical_problem_starts_collection(self):
        r = fixpro_app.ai_service.analyze_message("Ma climatisation ne marche plus", collected={})
        self.assertEqual(r["category"], "climatisation")
        self.assertIn("climatisation", r["response"].lower())
        self.assertFalse(r["ready"])

    def test_domain_preserved_across_messages(self):
        c = {"category": "plomberie", "mode": "fixpro"}
        r = fixpro_app.ai_service.analyze_message("Depuis hier", collected=c)
        self.assertIn("plomberie", r["response"].lower())

    def test_ready_when_all_info_collected(self):
        c = {
            "category": "electricite",
            "location": "Kaloum",
            "urgency": "urgent",
            "availability": "aujourd'hui",
            "mode": "fixpro",
            "needs_confirmation": True,
        }
        r = fixpro_app.ai_service.analyze_message("Oui", collected=c)
        self.assertTrue(r["ready"])

    def test_general_question_answered_then_offers_fixpro(self):
        r = fixpro_app.ai_service.analyze_message("C'est quoi Internet ?", collected={})
        self.assertIn("Internet", r["response"])
        self.assertTrue("FixPro" in r["response"] or "technicien" in r["response"].lower())

    def test_greeting_in_english(self):
        r = fixpro_app.ai_service.analyze_message("Hello", collected={})
        self.assertIn("FixPro", r["response"])


class InterventionTests(FixProTestCase):
    """Creation et suivi des demandes d'intervention."""

    def _create_client_and_artisan(self):
        self.register_client(phone="+224620000000")
        self.client.get("/logout")
        self.register_artisan("artisan@example.com", phone="+224621111111")

    def test_intervention_reference_unique(self):
        self._create_client_and_artisan()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            ref1 = fixpro_app._generate_fixpro_reference(conn)
            req1 = fixpro_app._insert_id(conn,
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, urgency, quote_amount, budget, latitude, longitude, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'REQUESTED', ?, 0, 0, ?, ?, ?, ?)",
                (1, 1, ref1, "Titre", "Desc", "plomberie", "Kaloum", "normal", 0.0, 0.0, "2026-01-01", "2026-01-01"))
            ref2 = fixpro_app._generate_fixpro_reference(conn)
            req2 = fixpro_app._insert_id(conn,
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, urgency, quote_amount, budget, latitude, longitude, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'REQUESTED', ?, 0, 0, ?, ?, ?, ?)",
                (1, 1, ref2, "Titre 2", "Desc 2", "electricite", "Dixinn", "urgent", 0.0, 0.0, "2026-01-01", "2026-01-01"))
            conn.commit()
            self.assertNotEqual(ref1, ref2)
            self.assertNotEqual(req1, req2)
            self.assertRegex(ref1, r"^FP-\d{4}-\d{6}$")
            self.assertRegex(ref2, r"^FP-\d{4}-\d{6}$")
        finally:
            conn.close()

    def test_lia_asks_confirmation_before_intervention(self):
        collected = {
            "category": "climatisation",
            "location": "Wanindara",
            "urgency": "urgent",
            "availability": "aujourd'hui",
            "mode": "fixpro",
            "problem_detail": "Ma clim ne refroidit plus",
        }
        r = fixpro_app.ai_service.analyze_message("", collected=collected)
        self.assertFalse(r["ready"])
        self.assertIn("Resume", r["response"])
        self.assertIn("Est-ce correct", r["response"])

    def test_lia_creates_after_client_confirms(self):
        collected = {
            "category": "climatisation",
            "location": "Wanindara",
            "urgency": "urgent",
            "availability": "aujourd'hui",
            "mode": "fixpro",
            "needs_confirmation": True,
            "problem_detail": "Ma clim ne refroidit plus",
        }
        r = fixpro_app.ai_service.analyze_message("Oui", collected=collected)
        self.assertTrue(r["ready"])
        self.assertIn("cree", r["response"].lower())


if __name__ == "__main__":
    unittest.main()
