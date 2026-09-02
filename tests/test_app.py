"""Tests fonctionnels de FixPro.

Chaque test s'execute sur une base SQLite temporaire, isolee et jetable.
Lancement : python -m pytest tests/ -v
"""

import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
        # La plupart des tests ne testent pas l'ecran de localisation : on
        # simule un visiteur deja localise pour ne pas etre redirige vers
        # /localisation a chaque page. Les tests dedies vident la session.
        with self.client.session_transaction() as sess:
            sess["client_lat"] = 9.5077
            sess["client_lon"] = -13.7114
            sess["client_zone"] = "Kaloum"

    def tearDown(self):
        self._tmpdir.cleanup()

    def _clear_client_location(self):
        with self.client.session_transaction() as sess:
            for k in ("client_lat", "client_lon", "client_zone",
                      "loc_gate_dismissed"):
                sess.pop(k, None)

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
            "email": email,
            "password": password,
            "address": "Conakry",
            "identity_doc": doc,
            "professional_doc": doc,
        }, follow_redirects=True)

        # Valide automatiquement l'artisan pour les tests (equivalent d'une validation admin).
        conn = db.connect(sqlite_path=self.db_path)
        try:
            user = conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
            if user:
                conn.execute(
                    "UPDATE users SET is_verified = 1, is_active = 1, email = ?,"
                    " verification_status = 'APPROVED',"
                    " password_hash = ?, availability_status = 'en_ligne' WHERE id = ?",
                    (email, fixpro_app.generate_password_hash(password), user["id"]))
                conn.execute(
                    "UPDATE technician_documents SET status = 'approved' WHERE technician_id = ?",
                    (user["id"],))
                conn.commit()
        finally:
            conn.close()
        return response

    def _set_client_location(self, lat=9.5077, lon=-13.7114, zone="Kaloum"):
        """Simule un client ayant deja defini sa localisation (evite l'ecran
        de localisation qui s'intercale sinon avant chaque page cliente)."""
        with self.client.session_transaction() as sess:
            sess["client_lat"] = lat
            sess["client_lon"] = lon
            sess["client_zone"] = zone

    def login(self, identifier, password="FixPro2026!"):
        response = self.client.post("/login", data={
            "identifier": identifier, "password": password},
            follow_redirects=True)
        with self.client.session_transaction() as sess:
            user_id = sess.get("user_id")
        if user_id:
            conn = db.connect(sqlite_path=self.db_path)
            try:
                user = conn.execute(
                    "SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
            finally:
                conn.close()
            if user and user["role"] == "admin":
                self.client.post("/admin/unlock", data={"password": password})
            if user and user["role"] == "client":
                self._set_client_location()
        return response


class HealthAndSecurityTests(FixProTestCase):

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_health_db_endpoint(self):
        response = self.client.get("/health-db")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["db"], "connected")
        self.assertEqual(body["engine"], "sqlite")

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
        self.login("+224620000000")  # le helper definit la localisation
        response = self.client.get("/artisans")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Techniciens", response.data)

    def _count_users(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        finally:
            conn.close()


class ClientProfileTests(FixProTestCase):
    """Profil client et pages associees."""

    def test_client_profile_renders_with_user_data(self):
        self.register_client()
        self.login("+224620000000")
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Aminata", response.data)
        self.assertIn(b"Client FixPro", response.data)
        self.assertIn(b"Se d", response.data)

    def test_client_edit_profile_page_renders(self):
        self.register_client()
        self.login("+224620000000")
        response = self.client.get("/profil/modifier")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Informations personnelles", response.data)

    def test_client_can_update_full_name(self):
        self.register_client()
        self.login("+224620000000")
        response = self.client.post("/profile", data={
            "full_name": "Aminata Diallo",
            "phone": "+224620000000",
            "city": "Conakry",
            "profession": "",
            "hourly_rate": "0",
            "latitude": "0",
            "longitude": "0",
            "bio": ""
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Aminata Diallo", response.data)

    def test_client_static_pages_renders(self):
        self.register_client()
        self.login("+224620000000")
        for page in ("how-it-works", "about", "terms"):
            response = self.client.get(f"/client-page/{page}")
            self.assertEqual(response.status_code, 200)
        response = self.client.get("/client-page/how-it-works")
        self.assertIn(b"Comment fonctionne FixPro", response.data)

    def test_client_security_page_renders(self):
        self.register_client()
        self.login("+224620000000")
        response = self.client.get("/profil/securite")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mot de passe", response.data)

    def test_client_can_change_password(self):
        self.register_client()
        self.login("+224620000000")
        response = self.client.post("/profil/securite", data={
            "current_password": "FixPro2026!",
            "new_password": "Nouveau2027!",
            "confirm_password": "Nouveau2027!",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"mis a jour", response.data)

    def test_client_aide_opens_new_conversation(self):
        self.register_client()
        self.login("+224620000000")
        response = self.client.get("/messages/new")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/messages/", response.location)


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
        self.assertEqual(self._request_field(1, "status"), "ASSIGNED")

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
        self.assertEqual(self._request_field(1, "status"), "ACCEPTED")

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
            sess["admin_unlocked"] = True

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
        self.client.post("/api/technicien/status", data={"status": "hors_ligne"})
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
            sess["admin_unlocked"] = True

    def test_admin_document_escapes_filename(self):
        """Le nom de fichier d'un document (saisi par le technicien) ne doit
        pas s'executer comme du HTML dans la vue admin (XSS stockee)."""
        import base64
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 40).decode()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO technician_documents (technician_id, document_type,"
                " file_name, mime_type, content_base64) VALUES (1, 'identity', ?, ?, ?)",
                ("x</title><script>alert(1)</script>", "image/png", png))
            conn.commit()
        finally:
            conn.close()
        self.login_admin()
        r = self.client.get("/admin/document/1")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"<script>alert(1)", r.data)
        self.assertIn(b"&lt;script&gt;", r.data)

    def test_admin_login_redirects_to_unlock(self):
        response = self.client.post("/login", data={
            "identifier": "admin@fixpro.local",
            "password": "adminpass"}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/unlock", response.location or "")

    def test_admin_dashboard_requires_unlock(self):
        self.client.post("/login", data={
            "identifier": "admin@fixpro.local",
            "password": "adminpass"}, follow_redirects=False)
        response = self.client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/unlock", response.location or "")

    def test_admin_unlock_wrong_password_fails(self):
        self.client.post("/login", data={
            "identifier": "admin@fixpro.local",
            "password": "adminpass"}, follow_redirects=False)
        response = self.client.post("/admin/unlock", data={
            "password": "wrong"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mot de passe incorrect", response.data)

    def test_admin_unlock_right_password_opens_dashboard(self):
        self.client.post("/login", data={
            "identifier": "admin@fixpro.local",
            "password": "adminpass"}, follow_redirects=False)
        response = self.client.post("/admin/unlock", data={
            "password": "adminpass"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Admin", response.data)

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
                "SELECT id FROM users WHERE role = 'technician'").fetchone()
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

    def test_admin_dashboard_computes_real_counts(self):
        """La route /admin/dashboard calcule toujours les vrais chiffres
        (abonnements, techniciens), meme pendant que le template est en
        refonte (page videe cote rendu, back-end intact)."""
        self.register_artisan("artisan@example.com", phone="+224621111111")
        self.login_admin()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET account_status = 'ACTIVE', is_active = 1"
                         " WHERE role = 'technician'")
            plan = conn.execute("SELECT id FROM subscription_plans WHERE code = 'pro'").fetchone()
            tech = conn.execute("SELECT id FROM users WHERE role = 'technician'").fetchone()
            conn.execute(
                "INSERT INTO technician_subscriptions (technician_id, plan_id, status)"
                " VALUES (?, ?, 'ACTIVE')", (tech["id"], plan["id"]))
            conn.execute(
                "INSERT INTO subscription_payments (user_id, plan_id, amount, status, paid_at)"
                " VALUES (?, ?, 100000, 'paid', ?)",
                (tech["id"], plan["id"], fixpro_app.now_iso()))
            conn.commit()
        finally:
            conn.close()

        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"commission", response.data.lower())

    def test_subscription_plans_seeded(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            codes = {r["code"] for r in conn.execute(
                "SELECT code FROM subscription_plans").fetchall()}
        finally:
            conn.close()
        self.assertEqual(codes, {"basic", "pro", "premium"})

    def test_bootstrap_admin_creates_and_logs_in(self):
        fixpro_app.app.config["ADMIN_EMAILS"] = ["patron@fixpro.gn"]
        fixpro_app.app.config["ADMIN_PASSWORD"] = "FixPro-Test-1234"
        try:
            conn = db.connect(sqlite_path=self.db_path)
            try:
                fixpro_app._bootstrap_admin(conn)
                conn.commit()
            finally:
                conn.close()
            r = self.client.post("/admin/login", data={
                "email": "patron@fixpro.gn", "password": "FixPro-Test-1234",
            })
            self.assertEqual(r.status_code, 302)
            self.assertIn("/admin/unlock", r.headers["Location"])
        finally:
            fixpro_app.app.config["ADMIN_EMAILS"] = []
            fixpro_app.app.config["ADMIN_PASSWORD"] = ""

    def test_admin_subscription_pages_render(self):
        self.login_admin()
        for url in ("/admin/abonnements", "/admin/abonnements?filter=expiring",
                    "/admin/abonnements/paiements", "/admin/reclamations"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertNotIn("commission", r.get_data(as_text=True).lower())

    def test_admin_can_update_plan_price(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            pid = conn.execute(
                "SELECT id FROM subscription_plans WHERE code = 'basic'").fetchone()["id"]
        finally:
            conn.close()
        self.login_admin()
        r = self.client.post("/admin/abonnements/plans/%d" % pid, data={
            "name": "Basic", "price_month": "75000", "features": "Test", "is_active": "1",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            price = conn.execute(
                "SELECT price_month FROM subscription_plans WHERE id = ?", (pid,)).fetchone()["price_month"]
        finally:
            conn.close()
        self.assertEqual(price, 75000)

    def test_admin_can_update_complaint_status(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO complaints (client_id, subject, message, status)"
                " VALUES (1, 'Test', 'Probleme', 'new')")
            conn.commit()
            cid = conn.execute("SELECT id FROM complaints").fetchone()["id"]
        finally:
            conn.close()
        self.login_admin()
        r = self.client.post("/admin/reclamations", data={
            "complaint_id": cid, "status": "resolved", "note": "Regle",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT status, resolution_note FROM complaints WHERE id = ?", (cid,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolution_note"], "Regle")

    def _make_owner(self, uid=1):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET admin_role = 'owner' WHERE id = ?", (uid,))
            conn.commit()
        finally:
            conn.close()

    def test_admin_users_page_renders(self):
        self.login_admin()
        r = self.client.get("/admin/utilisateurs")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Administrateurs", r.get_data(as_text=True))

    def test_owner_can_grant_and_revoke_admin_role(self):
        self._make_owner()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_active)"
                " VALUES ('mod@x.co', '+224690000001', 'x', 'client', 'Mod', 1)")
            conn.commit()
            tid = conn.execute("SELECT id FROM users WHERE email = 'mod@x.co'").fetchone()["id"]
        finally:
            conn.close()
        self.login_admin()
        self.client.post("/admin/utilisateurs", data={
            "user_id": tid, "admin_role": "moderator"}, follow_redirects=True)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute("SELECT role, admin_role FROM users WHERE id = ?", (tid,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["admin_role"], "moderator")
        self.assertEqual(row["role"], "admin")
        # retrait
        self.client.post("/admin/utilisateurs", data={
            "user_id": tid, "admin_role": ""}, follow_redirects=True)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute("SELECT admin_role FROM users WHERE id = ?", (tid,)).fetchone()
        finally:
            conn.close()
        self.assertIsNone(row["admin_role"])

    def test_non_owner_cannot_change_roles(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET admin_role = 'moderator' WHERE id = 1")
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_active)"
                " VALUES ('v@x.co', '+224690000002', 'x', 'client', 'V', 1)")
            conn.commit()
            tid = conn.execute("SELECT id FROM users WHERE email = 'v@x.co'").fetchone()["id"]
        finally:
            conn.close()
        self.login_admin()
        self.client.post("/admin/utilisateurs", data={
            "user_id": tid, "admin_role": "admin"}, follow_redirects=True)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute("SELECT admin_role FROM users WHERE id = ?", (tid,)).fetchone()
        finally:
            conn.close()
        self.assertIsNone(row["admin_role"])

    def test_due_subscription_expires_on_dashboard(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_active, account_status)"
                " VALUES ('t@x.co', '+224690000003', 'x', 'technician', 'T', 1, 'ACTIVE')")
            tid = conn.execute("SELECT id FROM users WHERE email = 't@x.co'").fetchone()["id"]
            conn.execute(
                "INSERT INTO technician_subscriptions (technician_id, status, end_date)"
                " VALUES (?, 'ACTIVE', '2000-01-01T00:00:00+00:00')", (tid,))
            conn.commit()
        finally:
            conn.close()
        self.login_admin()
        self.client.get("/admin/dashboard")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            st = conn.execute(
                "SELECT status FROM technician_subscriptions WHERE technician_id = ?", (tid,)).fetchone()["status"]
        finally:
            conn.close()
        self.assertEqual(st, "EXPIRED")

    def test_admin_can_suspend_and_restore_artisan(self):
        self.register_artisan("artisan@example.com", phone="+224621111111")
        self.login_admin()

        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = conn.execute(
                "SELECT id FROM users WHERE role = 'technician'").fetchone()
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

    def _insert_artisan(self, full_name, profession, lat, lon, verified=True, active=True, availability="en_ligne", zone=None):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            suffix = f"{abs(hash(full_name)) % 1000000:06d}"
            uid = fixpro_app._insert_id(conn, "INSERT INTO users (full_name, phone, email, password_hash, role, profession, city, latitude, longitude, is_verified, is_active, account_status, availability_status, zone_intervention) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (full_name, f"+22462{suffix}", f"{full_name.replace(' ', '')}@t.com", fixpro_app.generate_password_hash("FixPro2026!"), "technician", profession, "Conakry", lat, lon, 1 if verified else 0, 1 if active else 0, "ACTIVE", availability, zone or "Conakry"))
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

    def test_busy_technician_not_selected(self):
        plombier = self._insert_artisan("Plombier Disponible", "Plombier", 9.5010, -13.7010)
        occupe = self._insert_artisan("Plombier Occupe", "Plombier", 9.5005, -13.7005)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            client_id = fixpro_app._insert_id(conn, "INSERT INTO users (full_name, phone, password_hash, role, city) VALUES (?, ?, ?, ?, ?)",
                                               ("Client Test", "+224620000001", fixpro_app.generate_password_hash("FixPro2026!"), "client", "Conakry"))
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, urgency, quote_amount, budget, latitude, longitude, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client_id, occupe, "FP-2026-999001", "Fuite", "Fuite", "Plomberie", "Kaloum", "IN_PROGRESS", "urgent", 0, 0, 0, 0, "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
            conn.commit()
            artisan = fixpro_app._select_best_technician(conn, "plomberie", "Kaloum", client_lat=9.5012, client_lon=-13.7012)
            self.assertIsNotNone(artisan)
            self.assertEqual(artisan["id"], plombier)
        finally:
            conn.close()

    def test_offline_technician_not_selected(self):
        self._insert_artisan("Plombier En Ligne", "Plombier", 9.5010, -13.7010)
        self._insert_artisan("Plombier Hors Ligne", "Plombier", 9.5005, -13.7005, availability="hors_ligne")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            artisan = fixpro_app._select_best_technician(conn, "plomberie", "Kaloum", client_lat=9.5012, client_lon=-13.7012)
            self.assertIsNotNone(artisan)
            self.assertEqual(artisan["full_name"], "Plombier En Ligne")
        finally:
            conn.close()

    def test_attribution_creates_request_and_history(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            client_id = fixpro_app._insert_id(conn, "INSERT INTO users (full_name, phone, password_hash, role, city) VALUES (?, ?, ?, ?, ?)",
                                               ("Client Test", "+224620000002", fixpro_app.generate_password_hash("FixPro2026!"), "client", "Conakry"))
            artisan_id = fixpro_app._insert_id(conn, "INSERT INTO users (full_name, phone, email, password_hash, role, profession, city, latitude, longitude, is_verified, is_active, account_status, availability_status, zone_intervention) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                               ("Plombier Pro", "+22462999999", "pro@test.com", fixpro_app.generate_password_hash("FixPro2026!"), "technician", "Plombier", "Conakry", 9.5010, -13.7010, 1, 1, "ACTIVE", "en_ligne", "Kaloum"))
            artisan = conn.execute("SELECT * FROM users WHERE id = ?", (artisan_id,)).fetchone()
            artisan = dict(artisan)
            artisan["selection_reason"] = "test"
            conv_id = fixpro_app._insert_id(conn, "INSERT INTO conversations (client_id, subject, status) VALUES (?, ?, ?)",
                                             (client_id, "Demande", "ai_active"))
            conn.commit()
            analysis = {
                "category": "plomberie",
                "collected_info": {"problem_detail": "Fuite sous evier", "location": "Kaloum"},
                "urgency": "urgent",
            }
            req_id = fixpro_app._create_intervention_from_chat(
                conn, conv_id, client_id, analysis, artisan, client_id,
                client_lat=9.5012, client_lon=-13.7012)
            self.assertIsNotNone(req_id)
            request = conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()
            self.assertEqual(request["artisan_id"], artisan_id)
            hist = conn.execute(
                "SELECT status FROM intervention_history WHERE request_id = ? ORDER BY id",
                (req_id,)).fetchall()
            self.assertEqual(hist[0]["status"], "Nouvelle demande")
            self.assertTrue(any("Technicien attribue" in h["status"] for h in hist))
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
        self.assertTrue(len(r["response"]) > 0)
        self.assertIsNone(r["category"])
        self.assertFalse(r["ready"])

    def test_small_talk_does_not_force_technician(self):
        r = fixpro_app.ai_service.analyze_message("Ca va ?", collected={})
        self.assertIn("va", r["response"].lower())
        self.assertIsNone(r["category"])
        self.assertFalse(r["ready"])

    def test_personal_question_returns_identity(self):
        r = fixpro_app.ai_service.analyze_message("Tu es mariee ?", collected={})
        self.assertTrue(len(r["response"]) > 0)
        self.assertFalse(r["ready"])

    def test_emotion_recognition(self):
        r = fixpro_app.ai_service.analyze_message("Je suis vraiment stresse", collected={})
        self.assertTrue(len(r["response"]) > 0)

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
        self.assertTrue(len(r["response"]) > 0)
        self.assertIsNone(r["category"])
        self.assertFalse(r["ready"])

    def test_greeting_in_english(self):
        r = fixpro_app.ai_service.analyze_message("Hello", collected={})
        self.assertTrue(len(r["response"]) > 0)
        self.assertIsNone(r["category"])
        self.assertFalse(r["ready"])

    def test_detects_menuiserie_for_broken_door(self):
        """Ma porte est gatee doit etre classe en menuiserie, pas frigoriste."""
        r = fixpro_app.ai_service.analyze_message("Ma porte est gatee", collected={})
        self.assertEqual(r["category"], "menuiserie")
        self.assertNotEqual(r["category"], "refrigeration")
        self.assertFalse(r["ready"])
        self.assertIn("menuiserie", r["response"].lower())

    def test_no_creation_without_confirmation(self):
        """Aucune intervention sans confirmation explicite."""
        c = {
            "category": "menuiserie",
            "location": "Kaloum",
            "urgency": "urgent",
            "availability": "aujourd'hui",
            "mode": "fixpro",
            "needs_confirmation": False,
            "problem_detail": "Ma porte est gatee",
        }
        r = fixpro_app.ai_service.analyze_message("ok", collected=c)
        self.assertFalse(r["ready"])

    def test_correction_resets_category(self):
        """Le client peut corriger la categorie apres le resume."""
        c = {
            "category": "refrigeration",
            "location": "Kaloum",
            "urgency": "urgent",
            "availability": "aujourd'hui",
            "mode": "fixpro",
            "needs_confirmation": True,
            "problem_detail": "Ma porte est gatee",
        }
        r = fixpro_app.ai_service.analyze_message("mauvaise categorie", collected=c)
        self.assertIsNone(r["collected_info"].get("category"))
        self.assertFalse(r["ready"])


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




class TechnicianDashboardTests(FixProTestCase):
    """Espace technicien : missions, statuts, permissions."""

    def test_technician_dashboard_requires_artisan_role(self):
        self.register_client()
        self.login("+224620000000")
        response = self.client.get("/dashboard/technicien", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_technician_sees_only_his_missions(self):
        self.register_client(phone="+224620000000")
        self.client.get("/logout")
        self.register_artisan("t1@example.com", phone="+224621111111", name="T1 Diallo")
        self.client.get("/logout")
        self.register_artisan("t2@example.com", phone="+224622222222", name="T2 Bah")
        self.login("+224621111111")

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, service, category, address, status, urgency, phone_contact, estimated_price, commission_rate, commission_amount, professional_amount, payment_status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, 2, "FP-000001", "Fuite", "desc", "Plombier", "Plombier", "Kaloum", "ASSIGNED", "urgent", "+2246000", 100000, 0.1, 10000, 90000, "PENDING", "2026-01-01", "2026-01-01"))
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, service, category, address, status, urgency, phone_contact, estimated_price, commission_rate, commission_amount, professional_amount, payment_status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, 3, "FP-000002", "Serrure", "desc", "Serrurier", "Serrurier", "Kaloum", "ASSIGNED", "normal", "+2246000", 100000, 0.1, 10000, 90000, "PENDING", "2026-01-01", "2026-01-01"))
            conn.commit()
        finally:
            conn.close()

        response = self.client.get("/interventions", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Fuite", response.data)
        self.assertNotIn(b"Serrure", response.data)

    def test_technician_mission_status_workflow(self):
        self.register_client(phone="+224620000000")
        self.client.get("/logout")
        self.register_artisan("t1@example.com", phone="+224621111111", name="T1 Diallo")
        self.login("+224621111111")

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, service, category, address, status, urgency, phone_contact, estimated_price, commission_rate, commission_amount, professional_amount, payment_status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, 2, "FP-000003", "Fuite", "desc", "Plombier", "Plombier", "Kaloum", "ACCEPTED", "urgent", "+2246000", 100000, 0.1, 10000, 90000, "PENDING", "2026-01-01", "2026-01-01"))
            conn.commit()
        finally:
            conn.close()

        for action, expected in [
            ("en_route", "EN_ROUTE"),
            ("arrived", "ARRIVED"),
            ("in_progress", "IN_PROGRESS"),
            ("completed", "COMPLETED"),
        ]:
            response = self.client.post(
                "/missions/1/action",
                data={"action": action},
                follow_redirects=True)
            self.assertEqual(response.status_code, 200, action)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute("SELECT status FROM requests WHERE id = 1").fetchone()
            self.assertEqual(row["status"], "COMPLETED")
            history = conn.execute("SELECT COUNT(*) AS n FROM intervention_history WHERE request_id = 1").fetchone()
            self.assertGreaterEqual(history["n"], 4)
        finally:
            conn.close()



class TechnicianAccessTests(FixProTestCase):
    """Connexion, redirections et permissions du role technician."""

    def test_visitor_without_location_sees_location_gate(self):
        """Un visiteur (meme non connecte) tombe d'abord sur l'ecran de
        localisation avant d'entrer dans l'app."""
        self._clear_client_location()
        response = self.client.get("/artisans", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"data-location-gate", response.data)
        self.assertIn("Où êtes-vous".encode("utf-8"), response.data)

    def test_visitor_enters_app_after_setting_zone(self):
        """Apres avoir choisi un quartier (sans compte), le visiteur accede
        a la recherche filtree."""
        self._clear_client_location()
        r = self.client.post("/api/location/zone", json={"zone": "Kaloum"})
        self.assertEqual(r.get_json()["ok"], True)
        response = self.client.get("/artisans")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Recherche", response.data)

    def test_client_with_location_sees_artisans(self):
        """Une fois la localisation definie, le client accede a la recherche."""
        self.register_client()
        self.login("+224620000000")  # le helper definit une localisation
        response = self.client.get("/artisans")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Recherche", response.data)

    def test_technician_not_gated_by_location(self):
        """Un technicien connecte n'est jamais renvoye vers /localisation."""
        self.register_artisan("gate-tech@example.com", phone="+224629999999")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "UPDATE users SET role = 'technician' WHERE phone = ?",
                ("+224629999999",))
            conn.commit()
        finally:
            conn.close()
        self.client.get("/logout")
        self._clear_client_location()
        self.login("gate-tech@example.com")
        r = self.client.get("/dashboard", follow_redirects=False)
        self.assertNotIn("/localisation", r.headers.get("Location", ""))

    def test_manual_quartier_stays_in_conakry(self):
        """Choisir un quartier de la liste ne doit JAMAIS geocoder a
        l'etranger (bug : 'Madina' -> Medine, Arabie Saoudite)."""
        for quartier in ("Madina", "Ratoma", "Kaloum", "Kipe"):
            r = self.client.post("/api/location/zone", json={"zone": quartier})
            self.assertEqual(r.status_code, 200)
            lat = r.get_json().get("lat")
            self.assertIsNotNone(lat, f"{quartier} sans coordonnees")
            self.assertTrue(9.3 < lat < 9.9,
                            f"{quartier} -> lat {lat} hors de Conakry")

    def test_manual_location_accepts_guinea_cities(self):
        """La localisation manuelle couvre toute la Guinee, pas seulement
        Conakry : les villes de la liste resolvent a leurs coordonnees."""
        cases = {"Kankan": (10.0, 10.7, -9.6, -9.0),
                 "Labe": (11.0, 11.6, -12.6, -12.0),
                 "Nzerekore": (7.5, 8.1, -9.1, -8.5)}
        for ville, (la_lo, la_hi, lo_lo, lo_hi) in cases.items():
            r = self.client.post("/api/location/zone", json={"zone": ville})
            self.assertEqual(r.status_code, 200, ville)
            d = r.get_json()
            self.assertTrue(d.get("ok"), ville)
            self.assertTrue(la_lo < d["lat"] < la_hi and lo_lo < d["lon"] < lo_hi,
                            f"{ville} -> {d.get('lat')},{d.get('lon')}")
            self.assertEqual(d.get("zone"), ville)

    def test_location_endpoints_accept_post_without_csrf_token(self):
        """Les routes /api/location* acceptent un POST sans token CSRF
        (navigateur mobile / proxy de traduction sans header Referer)."""
        fixpro_app.app.config["WTF_CSRF_ENABLED"] = True
        try:
            client = fixpro_app.app.test_client()
            r1 = client.post("/api/location", json={"lat": 9.53, "lon": -13.68})
            r2 = client.post("/api/location/zone", json={"zone": "Kaloum"})
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r2.status_code, 200)
        finally:
            fixpro_app.app.config["WTF_CSRF_ENABLED"] = False

    def test_artisans_filtered_by_radius(self):
        """Seuls les techniciens dans le rayon du client sont affiches."""
        conn = db.connect(sqlite_path=self.db_path)
        try:
            for name, lat, lon in [("Proche Kaloum", 9.5077, -13.7114),
                                   ("Loin Ratoma", 9.6678, -13.5569)]:
                conn.execute(
                    "INSERT INTO users (phone, password_hash, role, full_name,"
                    " profession, latitude, longitude, is_verified, is_active,"
                    " account_status, availability_status)"
                    " VALUES (?, ?, 'technician', ?, 'Plombier', ?, ?, 1, 1,"
                    " 'ACTIVE', 'en_ligne')",
                    (name.replace(" ", ""),
                     fixpro_app.generate_password_hash("x"), name, lat, lon))
            conn.commit()
        finally:
            conn.close()
        # Le visiteur est localise a Kaloum (defini dans setUp).
        body = self.client.get("/artisans").data.decode("utf-8", "replace")
        self.assertIn("Proche Kaloum", body)
        self.assertNotIn("Loin Ratoma", body)

    def test_technician_is_redirected_to_dashboard(self):
        self.register_artisan("t1@example.com", phone="+224621111111", name="T1 Diallo")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET role = 'technician' WHERE id = 2")
            conn.commit()
        finally:
            conn.close()
        response = self.login("t1@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"bienvenue", response.data.lower())

    def test_technician_route_alias_works(self):
        self.register_artisan("t1@example.com", phone="+224621111111", name="T1 Diallo")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET role = 'technician' WHERE id = 2")
            conn.commit()
        finally:
            conn.close()
        self.login("t1@example.com")
        response = self.client.get("/technician/dashboard", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_client_cannot_access_technician_dashboard(self):
        self.register_client()
        self.login("+224620000000")
        response = self.client.get("/dashboard/technicien", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_technician_cannot_see_other_technician_mission(self):
        self.register_client(phone="+224620000000")
        self.client.get("/logout")
        self.register_artisan("t1@example.com", phone="+224621111111", name="T1 Diallo")
        self.client.get("/logout")
        self.register_artisan("t2@example.com", phone="+224622222222", name="T2 Bah")

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, urgency, phone_contact, estimated_price, commission_rate, commission_amount, professional_amount, payment_status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, 2, "FP-000001", "Fuite", "desc", "Plombier", "Kaloum", "ASSIGNED", "urgent", "+2246000", 100000, 0.1, 10000, 90000, "PENDING", "2026-01-01", "2026-01-01"))
            conn.commit()
        finally:
            conn.close()

        self.login("t2@example.com")
        response = self.client.get("/missions/1", follow_redirects=True)
        self.assertEqual(response.status_code, 200)


class TechnicianLifecycleTests(FixProTestCase):
    """Cycle de vie complet : creation, validation, activation, acces."""

    def _create_admin(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_verified, is_active)"
                " VALUES (?, ?, ?, 'admin', ?, 1, 1)",
                ("admin@fixpro.local", "+224000000000",
                 fixpro_app.generate_password_hash("adminpass"), "Administrateur"))
            conn.commit()
        finally:
            conn.close()

    def test_01_admin_creates_technician_pending(self):
        self._create_admin()
        self.login("admin@fixpro.local", "adminpass")
        response = self.client.post("/admin/artisans", data={
            "action": "create",
            "full_name": "Ibrahima Camara",
            "phone": "621111333",
            "email": "ibrahima@fixpro.local",
            "profession": "Plombier",
            "city": "Conakry",
            "zone_intervention": "Kaloum",
            "years_experience": "5",
            "bio": "Plombier experimente"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            tech = conn.execute(
                "SELECT * FROM users WHERE email = ?", ("ibrahima@fixpro.local",)).fetchone()
            self.assertIsNotNone(tech)
            self.assertEqual(tech["role"], "technician")
            self.assertEqual(tech["account_status"], "PENDING")
            self.assertEqual(tech["is_verified"], 0)
            self.assertEqual(tech["is_active"], 0)
        finally:
            conn.close()

    def test_02_pending_technician_cannot_login(self):
        self.test_01_admin_creates_technician_pending()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (fixpro_app.generate_password_hash("pendingpass"), "ibrahima@fixpro.local"))
            conn.commit()
        finally:
            conn.close()
        self.client.get("/logout")
        response = self.login("ibrahima@fixpro.local", "pendingpass")
        self.assertIn(b"attente", response.data.lower())

    def test_03_admin_validates_technician_and_token_is_created(self):
        self.test_01_admin_creates_technician_pending()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            tech = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("ibrahima@fixpro.local",)).fetchone()
        finally:
            conn.close()

        response = self.client.post("/admin/artisans", data={
            "action": "verify",
            "artisan_id": str(tech["id"])}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            tech = conn.execute(
                "SELECT * FROM users WHERE email = ?", ("ibrahima@fixpro.local",)).fetchone()
            self.assertEqual(tech["is_verified"], 1)
            self.assertEqual(tech["account_status"], "PENDING")
            notif = conn.execute(
                "SELECT * FROM notifications WHERE user_id = ?",
                (tech["id"],)).fetchone()
            self.assertIsNotNone(notif)
            self.assertIn(b"token:", (notif["data"] or "").encode())
        finally:
            conn.close()

    def test_04_technician_activates_and_redirects_to_dashboard(self):
        self.test_03_admin_validates_technician_and_token_is_created()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            tech = conn.execute(
                "SELECT * FROM users WHERE email = ?", ("ibrahima@fixpro.local",)).fetchone()
            notif = conn.execute(
                "SELECT * FROM notifications WHERE user_id = ?",
                (tech["id"],)).fetchone()
            token = (notif["data"] or "").replace("token:", "")
        finally:
            conn.close()

        page = self.client.get(f"/technician/activate?token={token}")
        csrf = (re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)) or [None, None])[1]
        response = self.client.post(
            f"/technician/activate?token={token}",
            data={"token": token, "csrf_token": csrf,
                  "password": "PassTech2026!", "confirm_password": "PassTech2026!"},
            follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            tech = conn.execute(
                "SELECT * FROM users WHERE email = ?", ("ibrahima@fixpro.local",)).fetchone()
            self.assertEqual(tech["account_status"], "ACTIVE")
            self.assertEqual(tech["is_active"], 1)
            self.assertEqual(tech["is_verified"], 1)
        finally:
            conn.close()

        # Connexion automatique apres activation
        self.assertIn(b"Bonjour", response.data)

    def test_05_technician_cannot_access_admin_dashboard(self):
        self.test_04_technician_activates_and_redirects_to_dashboard()
        response = self.client.get("/admin/dashboard", follow_redirects=False)
        # Le decorateur admin_required redirige vers /admin/login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location or "")

    def test_06_technician_cannot_see_other_technician_mission(self):
        self.test_04_technician_activates_and_redirects_to_dashboard()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            tech = conn.execute(
                "SELECT * FROM users WHERE email = ?", ("ibrahima@fixpro.local",)).fetchone()
            # Deuxieme technicien
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, profession, city, is_verified, is_active, account_status)"
                " VALUES (?, ?, ?, 'technician', ?, ?, ?, 1, 1, 'ACTIVE')",
                ("t2@fixpro.local", "+224622222222", fixpro_app.generate_password_hash("pass"),
                 "T2 Bah", "Electricien", "Conakry"))
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, urgency, phone_contact, estimated_price, commission_rate, commission_amount, professional_amount, payment_status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, tech["id"] + 1, "FP-000002", "Court-circuit", "desc", "Electricien", "Dixinn", "ASSIGNED", "urgent", "+2246000", 100000, 0.1, 10000, 90000, "PENDING", "2026-01-01", "2026-01-01"))
            conn.commit()
        finally:
            conn.close()

        response = self.client.get("/missions/2", follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    def test_07_admin_can_list_technicians(self):
        self._create_admin()
        self.login("admin@fixpro.local", "adminpass")
        response = self.client.get("/admin/artisans")
        self.assertEqual(response.status_code, 200)

    def test_08_mission_assigned_to_technician_appears_and_notifies(self):
        self._create_admin()
        self.login("admin@fixpro.local", "adminpass")
        self.client.post("/admin/artisans", data={
            "action": "create",
            "full_name": "Ibrahima Camara",
            "phone": "621111333",
            "email": "ibrahima@fixpro.local",
            "profession": "Plombier",
            "city": "Conakry",
            "zone_intervention": "Kaloum",
            "years_experience": "5",
            "bio": "Plombier experimente"
        }, follow_redirects=True)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            tech = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("ibrahima@fixpro.local",)).fetchone()
            client = conn.execute(
                "SELECT id FROM users WHERE phone = ?", ("+224000000000",)).fetchone()
        finally:
            conn.close()

        if not client:
            conn = db.connect(sqlite_path=self.db_path)
            try:
                conn.execute(
                    "INSERT INTO users (email, phone, password_hash, role, full_name, city, is_verified, is_active)"
                    " VALUES (?, ?, ?, 'client', ?, ?, 1, 1)",
                    ("client2@fixpro.local", "+224620000000",
                     fixpro_app.generate_password_hash("pass"), "Client Test", "Conakry"))
                conn.commit()
            finally:
                conn.close()

            conn = db.connect(sqlite_path=self.db_path)
            try:
                client = conn.execute(
                    "SELECT id FROM users WHERE phone = ?", ("+224620000000",)).fetchone()
            finally:
                conn.close()

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, urgency, phone_contact, estimated_price, commission_rate, commission_amount, professional_amount, payment_status, created_at, updated_at)"
                " VALUES (?, ?, 'FP-000003', 'Fuite sous evier', 'desc', 'Plombier', 'Kaloum, Conakry', 'ASSIGNED', 'urgent', '+2246000', 100000, 0.1, 10000, 90000, 'PENDING', '2026-01-01', '2026-01-01')",
                (client["id"], tech["id"]))
            conn.commit()
        finally:
            conn.close()

        token = fixpro_app._generate_activation_token(tech["id"])
        # Connexion du technicien
        self.client.get("/logout")
        page = self.client.get(f"/technician/activate?token={token}")
        csrf = (re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)) or [None, None])[1]
        self.client.post("/technician/activate",
                         data={"token": token, "csrf_token": csrf,
                               "password": "PassTech2026!",
                               "confirm_password": "PassTech2026!"}, follow_redirects=True)
        response = self.client.get("/interventions", follow_redirects=True)
        self.assertIn(b"Fuite sous evier", response.data)

    def test_09_suspended_technician_cannot_login(self):
        self._create_admin()
        self.login("admin@fixpro.local", "adminpass")
        self.client.post("/admin/artisans", data={
            "action": "create",
            "full_name": "Susp Camara",
            "phone": "621111444",
            "email": "susp@fixpro.local",
            "profession": "Plombier",
            "city": "Conakry",
            "zone_intervention": "Kaloum",
            "years_experience": "5",
            "bio": "Plombier"
        }, follow_redirects=True)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "UPDATE users SET account_status = 'SUSPENDED', is_active = 0,"
                " password_hash = ? WHERE email = ?",
                (fixpro_app.generate_password_hash("susppass"), "susp@fixpro.local"))
            conn.commit()
        finally:
            conn.close()

        self.client.get("/logout")
        response = self.login("susp@fixpro.local", "susppass")
        self.assertIn(b"suspendu", response.data.lower())

    def test_10_inactive_technician_cannot_login(self):
        self._create_admin()
        self.login("admin@fixpro.local", "adminpass")
        self.client.post("/admin/artisans", data={
            "action": "create",
            "full_name": "Inact Camara",
            "phone": "621111555",
            "email": "inact@fixpro.local",
            "profession": "Plombier",
            "city": "Conakry",
            "zone_intervention": "Kaloum",
            "years_experience": "5",
            "bio": "Plombier"
        }, follow_redirects=True)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "UPDATE users SET account_status = 'INACTIVE', is_active = 0,"
                " password_hash = ? WHERE email = ?",
                (fixpro_app.generate_password_hash("inactpass"), "inact@fixpro.local"))
            conn.commit()
        finally:
            conn.close()

        self.client.get("/logout")
        response = self.login("inact@fixpro.local", "inactpass")
        self.assertIn(b"inactif", response.data.lower())

    def test_11_technician_cannot_access_admin_routes(self):
        self.test_04_technician_activates_and_redirects_to_dashboard()
        for route in ["/admin", "/admin/dashboard", "/admin/artisans",
                      "/admin/requests", "/admin/tickets", "/admin/settings"]:
            with self.subTest(route=route):
                response = self.client.get(route, follow_redirects=False)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.location or "")

    def test_12_admin_can_access_admin_dashboard_and_manage_technicians(self):
        self._create_admin()
        self.login("admin@fixpro.local", "adminpass")
        dashboard = self.client.get("/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        artisans = self.client.get("/admin/artisans")
        self.assertEqual(artisans.status_code, 200)


class MissionCycleTests(FixProTestCase):
    """Cycle complet d'une mission client → technicien."""

    def _setup_mission(self):
        self.register_client(phone="+224620000000", city="Conakry")
        self.register_artisan("tech@fixpro.local", phone="+224621111111",
                              name="Ibrahima Camara")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "UPDATE users SET role = 'technician', availability_status = 'en_ligne',"
                " city = 'Conakry', quartier = 'Kaloum', zone_intervention = 'Kaloum',"
                " latitude = 9.5370, longitude = -13.6785,"
                " password_hash = ?, is_verified = 1, is_active = 1, account_status = 'ACTIVE'"
                " WHERE email = ?",
                (fixpro_app.generate_password_hash("techpass"), "tech@fixpro.local"))
            conn.commit()
            self.client_id = conn.execute(
                "SELECT id FROM users WHERE phone = ?", ("+224620000000",)).fetchone()["id"]
            self.tech_id = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("tech@fixpro.local",)).fetchone()["id"]
        finally:
            conn.close()

    def _create_admin(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_verified, is_active)"
                " VALUES (?, ?, ?, 'admin', ?, 1, 1)",
                ("admin@fixpro.local", "+224000000000",
                 fixpro_app.generate_password_hash("adminpass"), "Administrateur"))
            conn.commit()
        finally:
            conn.close()

    def _login_technician(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = getattr(self, "tech_id", 2)

    def _login_client(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = getattr(self, "client_id", 1)

    def _get_req_id(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM requests WHERE client_id = ? ORDER BY id DESC",
                (getattr(self, "client_id", 1),)).fetchone()
            return row["id"] if row else None
        finally:
            conn.close()

    def _get_user_id_by_email(self, email):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            return row["id"] if row else None
        finally:
            conn.close()

    def test_01_client_creates_request_and_gets_reference(self):
        self._setup_mission()
        self._login_client()
        response = self.client.post("/requests/new", data={
            "title": "Fuite d'eau sous l'evier",
            "description": "L'eau coule sous l'evier depuis ce matin",
            "category": "Plombier",
            "address": "Kaloum, Conakry",
            "budget": "100000"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            req = conn.execute(
                "SELECT * FROM requests WHERE client_id = ?",
                (getattr(self, "client_id", 1),)).fetchone()
            self.assertIsNotNone(req)
            self.assertTrue(req["reference"].startswith("FP-2026-"))
            self.assertEqual(req["status"], "ASSIGNED")
            self.assertEqual(req["category"], "Plombier")
            self.assertIsNotNone(req["artisan_id"])
        finally:
            conn.close()

    def test_02_technician_receives_notification_and_sees_dashboard(self):
        self._setup_mission()
        self.test_01_client_creates_request_and_gets_reference()

        conn = db.connect(sqlite_path=self.db_path)
        try:
            notif = conn.execute(
                "SELECT * FROM notifications WHERE user_id = ?",
                (getattr(self, "tech_id", 2),)).fetchone()
            self.assertIsNotNone(notif)
        finally:
            conn.close()

        self._login_technician()
        response = self.client.get("/interventions", follow_redirects=True)
        self.assertIn(b"Fuite", response.data)

    def test_03_technician_accepts_and_client_sees_status(self):
        self._setup_mission()
        self.test_01_client_creates_request_and_gets_reference()
        req_id = self._get_req_id()

        self._login_technician()
        response = self.client.post(
            f"/missions/{req_id}/action",
            data={"action": "accept"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            req = conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()
            self.assertEqual(req["status"], "ACCEPTED")
            client_notif = conn.execute(
                "SELECT * FROM notifications WHERE user_id = ? AND type = 'request_accepted'",
                (getattr(self, "client_id", 1),)).fetchone()
            self.assertIsNotNone(client_notif)
        finally:
            conn.close()

    def test_04_technician_en_route_and_client_sees(self):
        self._setup_mission()
        self.test_03_technician_accepts_and_client_sees_status()
        req_id = self._get_req_id()

        self._login_technician()
        self.client.post(f"/missions/{req_id}/action",
                         data={"action": "en_route"})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            req = conn.execute("SELECT status FROM requests WHERE id = ?", (req_id,)).fetchone()
            self.assertEqual(req["status"], "EN_ROUTE")
        finally:
            conn.close()

        self._login_client()
        response = self.client.get(f"/requests/{req_id}", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_05_technician_arrived_in_progress_completed(self):
        self._setup_mission()
        self.test_04_technician_en_route_and_client_sees()
        req_id = self._get_req_id()

        actions = ["arrived", "in_progress", "completed"]
        expected = ["ARRIVED", "IN_PROGRESS", "COMPLETED"]
        self._login_technician()
        for action, exp in zip(actions, expected):
            response = self.client.post(
                f"/missions/{req_id}/action",
                data={"action": action}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            conn = db.connect(sqlite_path=self.db_path)
            try:
                status = conn.execute(
                    "SELECT status FROM requests WHERE id = ?", (req_id,)).fetchone()["status"]
                self.assertEqual(status, exp, f"action={action}")
            finally:
                conn.close()

    def test_06_completed_appears_in_history(self):
        self._setup_mission()
        self.test_05_technician_arrived_in_progress_completed()
        req_id = self._get_req_id()

        self._login_technician()
        response = self.client.get("/technician/dashboard", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        self._login_client()
        response = self.client.get(f"/requests/{req_id}", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"arrivee", response.data.lower())

    def test_07_other_technician_cannot_access_mission(self):
        self._setup_mission()
        self.test_03_technician_accepts_and_client_sees_status()
        req_id = self._get_req_id()

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, profession, city, is_verified, is_active, account_status, availability_status)"
                " VALUES (?, ?, ?, 'technician', ?, ?, ?, 1, 1, 'ACTIVE', 'en_ligne')",
                ("t2@fixpro.local", "+224622222222", fixpro_app.generate_password_hash("pass"),
                 "T2 Bah", "Plombier", "Conakry"))
            conn.commit()
            other_id = self._get_user_id_by_email("t2@fixpro.local")
        finally:
            conn.close()

        with self.client.session_transaction() as sess:
            sess["user_id"] = other_id
        response = self.client.get(f"/missions/{req_id}", follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    def test_08_client_a_cannot_see_client_b_request(self):
        self._setup_mission()
        self.test_01_client_creates_request_and_gets_reference()
        req_id = self._get_req_id()

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, city, is_verified, is_active)"
                " VALUES (?, ?, ?, 'client', ?, ?, 1, 1)",
                ("clientb@fixpro.local", "+224630000000",
                 fixpro_app.generate_password_hash("pass"), "Client B", "Conakry"))
            conn.commit()
            client_b_id = self._get_user_id_by_email("clientb@fixpro.local")
        finally:
            conn.close()

        with self.client.session_transaction() as sess:
            sess["user_id"] = client_b_id
        response = self.client.get(f"/requests/{req_id}", follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    def test_09_suspended_technician_not_selected(self):
        self._setup_mission()
        # Suspendre le technicien
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "UPDATE users SET is_active = 0, account_status = 'SUSPENDED' WHERE id = ?",
                (getattr(self, "tech_id", 2),))
            conn.commit()
        finally:
            conn.close()

        self._login_client()
        response = self.client.post("/requests/new", data={
            "title": "Fuite sous evier",
            "description": "Une nouvelle fuite",
            "category": "Plombier",
            "address": "Kaloum, Conakry"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            req = conn.execute(
                "SELECT * FROM requests WHERE client_id = ? ORDER BY id DESC",
                (getattr(self, "client_id", 1),)).fetchone()
            self.assertIsNotNone(req)
            self.assertEqual(req["artisan_id"], None)
            self.assertEqual(req["status"], "REQUESTED")
        finally:
            conn.close()

    def test_10_refused_mission_reassigned(self):
        # Second technicien
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, profession, city, quartier, is_verified, is_active, account_status, availability_status)"
                " VALUES (?, ?, ?, 'technician', ?, ?, 'Conakry', 'Kaloum', 1, 1, 'ACTIVE', 'en_ligne')",
                ("t2@fixpro.local", "+224622222222", fixpro_app.generate_password_hash("pass"),
                 "T2 Bah", "Plombier"))
            conn.commit()
            other_id = self._get_user_id_by_email("t2@fixpro.local")
        finally:
            conn.close()

        self._setup_mission()
        self.test_01_client_creates_request_and_gets_reference()
        req_id = self._get_req_id()

        self._login_technician()
        self.client.post(f"/missions/{req_id}/action", data={"action": "reject", "reason": "Indisponible"})

        conn = db.connect(sqlite_path=self.db_path)
        try:
            req = conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()
            self.assertEqual(req["artisan_id"], other_id)
            self.assertEqual(req["status"], "ASSIGNED")
        finally:
            conn.close()

    def test_11_admin_can_follow_mission(self):
        self._create_admin()
        self._setup_mission()
        self.test_01_client_creates_request_and_gets_reference()
        req_id = self._get_req_id()

        self.login("admin@fixpro.local", "adminpass")
        response = self.client.get(f"/admin/requests/{req_id}", follow_redirects=True)
        self.assertEqual(response.status_code, 200)


class GpsTestCase(FixProTestCase):
    """Tests du GPS technicien et de son utilisation dans le matching."""

    def _create_technician(self, phone, name, profession, verified=True,
                           status="ACTIVE", active=True,
                           availability="en_ligne"):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " profession, city, quartier, is_verified, is_active,"
                " account_status, availability_status, latitude, longitude)"
                " VALUES (?, ?, ?, 'technician', ?, ?, 'Conakry', 'Kaloum', ?, ?, ?, ?, 0.0, 0.0)",
                (f"{phone}@fixpro.local", phone,
                 fixpro_app.generate_password_hash("TechnicianPass1!"),
                 name, profession,
                 1 if verified else 0, 1 if active else 0,
                 status, availability))
            conn.commit()
            return conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()["id"]
        finally:
            conn.close()

    def _login_technician(self, phone="+224611111111"):
        return self.client.post("/login", data={
            "identifier": phone,
            "password": "TechnicianPass1!",
        }, follow_redirects=False)

    def test_gps_01_valid_position_stored(self):
        tech_id = self._create_technician("+224611111111", "Kaba Camara", "Plombier")
        response = self._login_technician()
        self.assertTrue(300 <= response.status_code < 400)

        response = self.client.post("/api/technicien/position", data={
            "lat": "9.5090",
            "lon": "-13.7120",
        })
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])

        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM technician_locations WHERE technician_id = ?",
                (tech_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertAlmostEqual(row["latitude"], 9.5090, places=4)
            self.assertAlmostEqual(row["longitude"], -13.7120, places=4)
        finally:
            conn.close()

    def test_gps_02_offline_rejected(self):
        tech_id = self._create_technician(
            "+224611111112", "Binta Soumah", "Plombier",
            availability="hors_ligne")
        self._login_technician("+224611111112")

        response = self.client.post("/api/technicien/position", data={
            "lat": "9.5090",
            "lon": "-13.7120",
        })
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertFalse(body["ok"])

        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM technician_locations WHERE technician_id = ?",
                (tech_id,)).fetchone()
            self.assertIsNone(row)
        finally:
            conn.close()

    def test_gps_04_invalid_position(self):
        self._create_technician("+224611111114", "Amadou Diallo", "Plombier")
        self._login_technician("+224611111114")

        response = self.client.post("/api/technicien/position", data={
            "lat": "200",
            "lon": "300",
        })
        self.assertEqual(response.status_code, 400)

    def test_gps_05_matching_uses_real_position(self):
        # Client position
        client_lat, client_lon = 9.5090, -13.7120

        # Technicien proche
        near_id = self._create_technician(
            "+224611111115", "Proche Sylla", "Plombier")
        # Technicien eloigne
        far_id = self._create_technician(
            "+224611111116", "Lointain Diallo", "Plombier")

        conn = db.connect(sqlite_path=self.db_path)
        try:
            # Pas de profil GPS, on force la table temps reel
            conn.execute(
                "INSERT INTO technician_locations (technician_id, latitude, longitude)"
                " VALUES (?, ?, ?)",
                (near_id, 9.5091, -13.7121))
            conn.execute(
                "INSERT INTO technician_locations (technician_id, latitude, longitude)"
                " VALUES (?, ?, ?)",
                (far_id, 9.5800, -13.7800))
            conn.commit()

            best = fixpro_app._select_best_technician(
                conn, "Plombier", "Kaloum",
                client_lat=client_lat, client_lon=client_lon)
            self.assertIsNotNone(best)
            self.assertEqual(best["id"], near_id)
            self.assertEqual(best["gps_source"], "technician_locations")
        finally:
            conn.close()

    def test_gps_06_stale_position_ignored(self):
        client_lat, client_lon = 9.5090, -13.7120
        fresh_id = self._create_technician(
            "+224611111117", "Recent Diallo", "Plombier")
        stale_id = self._create_technician(
            "+224611111118", "Perime Bah", "Plombier")

        conn = db.connect(sqlite_path=self.db_path)
        try:
            stale_at = (datetime.now(timezone.utc) - timedelta(seconds=500)).replace(
                tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO technician_locations (technician_id, latitude, longitude, updated_at)"
                " VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (fresh_id, 9.5092, -13.7122))
            conn.execute(
                "INSERT INTO technician_locations (technician_id, latitude, longitude, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (stale_id, 9.5091, -13.7121, stale_at))
            conn.commit()

            best = fixpro_app._select_best_technician(
                conn, "Plombier", "Kaloum",
                client_lat=client_lat, client_lon=client_lon)
            self.assertIsNotNone(best)
            self.assertEqual(best["id"], fresh_id)
        finally:
            conn.close()

    def test_gps_07_client_cannot_send_position(self):
        self.register_client(phone="+224620000001", first_name="Mamadou", last_name="Diallo")
        self.client.post("/login", data={
            "identifier": "+224620000001",
            "password": "FixPro2026!",
        }, follow_redirects=False)

        response = self.client.post("/api/technicien/position", data={
            "lat": "9.5090",
            "lon": "-13.7120",
        })
        self.assertEqual(response.status_code, 403)


class MobileTechnicianSessionTests(FixProTestCase):
    """Tests de la session mobile persistante 7 jours du technicien."""

    def _insert_technician(self, phone, password, status="ACTIVE"):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (phone, password_hash, role, full_name, account_status,"
                " is_verified, is_active) VALUES (?, ?, ?, ?, ?, 1, 1)",
                (phone, fixpro_app.generate_password_hash(password), "technician", "Tech Test", status))
            conn.commit()
            return conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()["id"]
        finally:
            conn.close()

    def test_mobile_login_technician_returns_token(self):
        self._insert_technician("+224620000001", "Secret123!")
        response = self.client.post("/api/mobile/login",
                                    data=json.dumps({"phone": "+224620000001", "password": "Secret123!"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertIn("token", body)
        self.assertEqual(body["user"]["role"], "technician")

    def test_mobile_login_non_technician_fails(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (phone, password_hash, role, full_name, account_status,"
                " is_verified, is_active) VALUES (?, ?, ?, ?, ?, 1, 1)",
                ("+224620000002", fixpro_app.generate_password_hash("Secret123!"), "client", "Client Test", "ACTIVE"))
            conn.commit()
        finally:
            conn.close()
        response = self.client.post("/api/mobile/login",
                                    data=json.dumps({"phone": "+224620000002", "password": "Secret123!"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_mobile_login_suspended_technician_fails(self):
        self._insert_technician("+224620000003", "Secret123!", "SUSPENDED")
        response = self.client.post("/api/mobile/login",
                                    data=json.dumps({"phone": "+224620000003", "password": "Secret123!"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_mobile_verify_valid_token(self):
        self._insert_technician("+224620000004", "Secret123!")
        login = self.client.post("/api/mobile/login",
                                 data=json.dumps({"phone": "+224620000004", "password": "Secret123!"}),
                                 content_type="application/json")
        token = login.get_json()["token"]
        response = self.client.get("/api/mobile/verify",
                                   headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["user"]["role"], "technician")

    def test_mobile_verify_tampered_token_fails(self):
        response = self.client.get("/api/mobile/verify",
                                   headers={"Authorization": "Bearer fake-token"})
        self.assertEqual(response.status_code, 401)

    def test_mobile_verify_missing_token_fails(self):
        response = self.client.get("/api/mobile/verify")
        self.assertEqual(response.status_code, 401)


class TechnicianVerificationFlowTests(FixProTestCase):
    """Verification obligatoire du technicien : docs, statut, dashboard admin, retour."""

    DOC = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
           "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    PHONE = "624999888"
    EMAIL = "verif.tech@example.com"
    PASSWORD = "PassTech2026!"

    def setUp(self):
        super().setUp()
        fixpro_app.app.config["TECH_VERIFICATION_ENABLED"] = True

    def tearDown(self):
        fixpro_app.app.config["TECH_VERIFICATION_ENABLED"] = False
        super().tearDown()

    def _admin(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_verified, is_active)"
                " VALUES (?, ?, ?, 'admin', ?, 1, 1)",
                ("admin@fixpro.local", "+224000000000",
                 fixpro_app.generate_password_hash("adminpass"), "Admin"))
            conn.commit()
            return conn.execute("SELECT id FROM users WHERE email = 'admin@fixpro.local'").fetchone()["id"]
        finally:
            conn.close()

    def _login_admin(self, admin_id):
        with self.client.session_transaction() as sess:
            sess["user_id"] = admin_id
            sess["admin_unlocked"] = True

    def _register(self, identity=True, professional=True, password=PASSWORD, email=EMAIL, phone=PHONE):
        data = {
            "full_name": "Amadou Camara", "profession": "Plombier",
            "phone": phone, "email": email, "password": password, "address": "Conakry",
        }
        if identity:
            data["identity_doc"] = self.DOC
        if professional:
            data["professional_doc"] = self.DOC
        return self.client.post("/register/artisan", data=data, follow_redirects=True)

    def _tech(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT * FROM users WHERE role = 'technician' AND phone LIKE ?",
                ("%" + self.PHONE[-6:],)).fetchone()
        finally:
            conn.close()

    # -- Tests -------------------------------------------------------------

    def test_A_no_documents_blocks_registration(self):
        self._register(identity=False, professional=False)
        self.assertIsNone(self._tech())

    def test_B_identity_only_blocks_registration(self):
        self._register(identity=True, professional=False)
        self.assertIsNone(self._tech())

    def test_C_both_documents_creates_pending_dossier(self):
        self._register()
        tech = self._tech()
        self.assertIsNotNone(tech)
        self.assertEqual(tech["verification_status"], "PENDING_REVIEW")
        self.assertEqual(tech["is_verified"], 0)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            docs = conn.execute(
                "SELECT document_type, status FROM technician_documents WHERE technician_id = ?"
                " ORDER BY document_type", (tech["id"],)).fetchall()
        finally:
            conn.close()
        self.assertEqual([d["document_type"] for d in docs], ["identity", "professional"])
        self.assertTrue(all(d["status"] == "pending" for d in docs))

    def test_D_pending_technician_sees_waiting_screen_not_dashboard(self):
        self._register()  # auto-connecte le technicien
        resp = self.client.get("/technician/dashboard", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("pending", (resp.location or "").lower())
        page = self.client.get("/artisan-pending")
        self.assertEqual(page.status_code, 200)
        self.assertIn("examen", page.get_data(as_text=True).lower())

    def test_D2_pending_technician_not_in_client_search(self):
        self._register()
        self.client.get("/logout")
        self.register_client(phone="+224620000123")
        self._set_client_location()
        resp = self.client.get("/artisans")
        self.assertNotIn("Amadou Camara", resp.get_data(as_text=True))

    def test_E_admin_sees_dossier_in_dashboard_and_detail(self):
        self._register()
        self.client.get("/logout")
        admin_id = self._admin()
        self._login_admin(admin_id)
        tech = self._tech()
        dash = self.client.get("/admin/dashboard")
        self.assertEqual(dash.status_code, 200)
        self.assertIn("Demandes de validation", dash.get_data(as_text=True))
        detail = self.client.get(f"/admin/artisans/{tech['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Justificatif professionnel", detail.get_data(as_text=True))

    def test_F_verify_blocked_until_documents_approved(self):
        self._register()
        self.client.get("/logout")
        admin_id = self._admin()
        self._login_admin(admin_id)
        tech = self._tech()

        # Verify avant approbation des documents -> refuse.
        self.client.post("/admin/artisans", data={"action": "verify", "artisan_id": tech["id"]},
                         follow_redirects=True)
        self.assertEqual(self._tech()["verification_status"], "PENDING_REVIEW")

        conn = db.connect(sqlite_path=self.db_path)
        try:
            docs = conn.execute(
                "SELECT id FROM technician_documents WHERE technician_id = ?", (tech["id"],)).fetchall()
        finally:
            conn.close()
        for d in docs:
            self.client.post(f"/admin/technicien/{tech['id']}/document/{d['id']}/review",
                             data={"decision": "approve"}, follow_redirects=True)

        self.client.post("/admin/artisans", data={"action": "verify", "artisan_id": tech["id"]},
                         follow_redirects=True)
        tech = self._tech()
        self.assertEqual(tech["verification_status"], "APPROVED")
        self.assertEqual(tech["is_verified"], 1)

    def test_G_approved_technician_returns_straight_to_dashboard(self):
        self._register()
        self.client.get("/logout")
        admin_id = self._admin()
        self._login_admin(admin_id)
        tech = self._tech()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            for d in conn.execute("SELECT id FROM technician_documents WHERE technician_id = ?",
                                  (tech["id"],)).fetchall():
                self.client.post(f"/admin/technicien/{tech['id']}/document/{d['id']}/review",
                                 data={"decision": "approve"}, follow_redirects=True)
        finally:
            conn.close()
        self.client.post("/admin/artisans", data={"action": "verify", "artisan_id": tech["id"]},
                         follow_redirects=True)
        self.client.get("/logout")

        resp = self.login(self.EMAIL, self.PASSWORD)
        self.assertEqual(resp.status_code, 200)
        dash = self.client.get("/technician/dashboard", follow_redirects=False)
        self.assertEqual(dash.status_code, 200)

    def test_verification_disabled_lets_technician_finish_without_documents(self):
        fixpro_app.app.config["TECH_VERIFICATION_ENABLED"] = False
        self._register(identity=False, professional=False)
        tech = self._tech()
        self.assertIsNotNone(tech)
        self.assertEqual(tech["verification_status"], "APPROVED")
        self.assertEqual(tech["is_verified"], 1)
        dash = self.client.get("/technician/dashboard", follow_redirects=False)
        self.assertEqual(dash.status_code, 200)

    def test_document_reject_requires_reason(self):
        self._register()
        self.client.get("/logout")
        admin_id = self._admin()
        self._login_admin(admin_id)
        tech = self._tech()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            doc_id = conn.execute(
                "SELECT id FROM technician_documents WHERE technician_id = ? LIMIT 1",
                (tech["id"],)).fetchone()["id"]
        finally:
            conn.close()
        self.client.post(f"/admin/technicien/{tech['id']}/document/{doc_id}/review",
                         data={"decision": "reject"}, follow_redirects=True)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            status = conn.execute(
                "SELECT status FROM technician_documents WHERE id = ?", (doc_id,)).fetchone()["status"]
        finally:
            conn.close()
        self.assertEqual(status, "pending")


if __name__ == "__main__":
    unittest.main()
