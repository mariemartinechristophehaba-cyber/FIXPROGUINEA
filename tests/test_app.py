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

        # Les tests ne doivent jamais appeler Nominatim (reseau) : on simule
        # l'absence de reponse -> les routes retombent sur les tables locales.
        # Un test qui veut exercer le geocodage inverse patche _reverse_geocode.
        _orig_nominatim = fixpro_app._nominatim_request
        fixpro_app._nominatim_request = lambda url: None
        self.addCleanup(setattr, fixpro_app, "_nominatim_request", _orig_nominatim)
        try:
            fixpro_app._NOMINATIM_CACHE.clear()
        except Exception:
            pass

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
        """L'inscription technicien n'existe plus dans l'app. Les tests qui ont
        encore besoin d'un technicien en base (messagerie, admin) le creent
        directement, deja valide."""
        conn = db.connect(sqlite_path=self.db_path)
        try:
            existing = conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO users (email, phone, password_hash, role, full_name,"
                    " profession, city, is_verified, is_active, verification_status,"
                    " availability_status)"
                    " VALUES (?, ?, ?, 'technician', ?, 'Plombier', 'Conakry', 1, 1,"
                    " 'APPROVED', 'en_ligne')",
                    (email, phone, fixpro_app.generate_password_hash(password), name))
                conn.commit()
        finally:
            conn.close()

        class _Resp:
            status_code = 200
            data = b""
        return _Resp()

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


class DevenirTechnicienTests(FixProTestCase):
    """Page publique 'Devenir technicien' + collecte des candidatures."""

    def test_page_renders_for_visitor(self):
        r = self.client.get("/devenir-technicien")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Devenez technicien", r.get_data(as_text=True))

    def test_register_role_technicien_redirects_here(self):
        r = self.client.get("/register?role=technicien", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/devenir-technicien", r.location)

    def test_submitting_form_stores_a_lead(self):
        r = self.client.post("/devenir-technicien", data={
            "first_name": "Ibrahim", "last_name": "Sory", "phone": "620112233",
            "profession": "Plomberie", "city": "Ratoma", "note": "5 ans d'experience",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("enregistr", r.get_data(as_text=True).lower())
        conn = db.connect(sqlite_path=self.db_path)
        try:
            lead = conn.execute("SELECT * FROM technician_leads").fetchone()
        finally:
            conn.close()
        self.assertEqual(lead["last_name"], "Sory")
        self.assertEqual(lead["phone"], "+224620112233")
        self.assertEqual(lead["status"], "nouveau")

    def test_form_rejects_missing_fields(self):
        self.client.post("/devenir-technicien", data={"first_name": "X"},
                         follow_redirects=True)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM technician_leads").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 0)

    def test_drawer_shows_link_on_client_page(self):
        self.register_client()
        self.login("+224620000000")
        r = self.client.get("/artisans")
        html = r.get_data(as_text=True)
        self.assertIn("/devenir-technicien", html)
        self.assertIn("S'inscrire en tant que technicien", html)


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

    def _make_artisan_id(self, phone="+224621111111"):
        self.register_artisan("artisan@example.com", phone=phone)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()["id"]
        finally:
            conn.close()

    def test_guest_can_message_artisan_without_registering(self):
        artisan_id = self._make_artisan_id("+224621111112")
        self.client.get("/logout")
        r = self.client.get(f"/messages/technicien/{artisan_id}", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        # Pas redirige vers la connexion : un compte visiteur a ete cree a la volee.
        self.assertNotIn("connecter pour acceder", r.data.decode("utf-8", "replace"))
        conv_id = int(r.request.path.split("/")[-1])
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conv = conn.execute(
                "SELECT client_id, artisan_id, status FROM conversations WHERE id = ?",
                (conv_id,)).fetchone()
            self.assertEqual(conv["artisan_id"], artisan_id)
            self.assertEqual(conv["status"], "direct")
            guest = conn.execute(
                "SELECT role, full_name FROM users WHERE id = ?", (conv["client_id"],)).fetchone()
            self.assertEqual(guest["role"], "client")
            self.assertEqual(guest["full_name"], "Visiteur")
        finally:
            conn.close()
        # meme session -> meme conversation, pas un nouveau visiteur a chaque fois
        r2 = self.client.get(f"/messages/technicien/{artisan_id}", follow_redirects=True)
        self.assertEqual(int(r2.request.path.split("/")[-1]), conv_id)

    def test_profile_message_opens_direct_conversation_no_ai(self):
        artisan_id = self._make_artisan_id()
        self.client.get("/logout")
        self.register_client(phone="+224610000010")
        self.login("+224610000010")

        r = self.client.get(f"/messages/technicien/{artisan_id}", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        conv_id = int(r.request.path.split("/")[-1])

        self.client.post(f"/messages/{conv_id}",
                         data={"content": "Bonjour, etes-vous disponible"})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conv = conn.execute(
                "SELECT client_id, artisan_id, status FROM conversations WHERE id = ?",
                (conv_id,)).fetchone()
            self.assertEqual(conv["artisan_id"], artisan_id)
            self.assertEqual(conv["status"], "direct")
            msgs = conn.execute(
                "SELECT sender_role FROM conversation_messages WHERE conversation_id = ?",
                (conv_id,)).fetchall()
            self.assertEqual([m["sender_role"] for m in msgs], ["client"])
        finally:
            conn.close()

    def test_technician_and_client_exchange_direct_messages(self):
        artisan_id = self._make_artisan_id()
        self.client.get("/logout")
        self.register_client(phone="+224610000011")
        self.login("+224610000011")
        r = self.client.get(f"/messages/technicien/{artisan_id}", follow_redirects=True)
        conv_id = int(r.request.path.split("/")[-1])
        self.client.post(f"/messages/{conv_id}", data={"content": "un souci electrique"})

        self.client.get("/logout")
        self.login("+224621111111")
        r2 = self.client.get(f"/messages/{conv_id}")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("un souci electrique", r2.data.decode("utf-8", "replace"))
        self.client.post(f"/messages/{conv_id}", data={"content": "je passe cet apres-midi"})

        conn = db.connect(sqlite_path=self.db_path)
        try:
            msgs = conn.execute(
                "SELECT sender_role FROM conversation_messages"
                " WHERE conversation_id = ? ORDER BY id", (conv_id,)).fetchall()
            self.assertEqual([m["sender_role"] for m in msgs], ["client", "artisan"])
        finally:
            conn.close()

        self.client.get("/logout")
        self.login("+224610000011")
        r3 = self.client.get(f"/messages/{conv_id}")
        self.assertIn("cet apres-midi", r3.data.decode("utf-8", "replace"))

    def _open_direct(self, client_phone="+224610000012"):
        artisan_id = self._make_artisan_id()
        self.client.get("/logout")
        self.register_client(phone=client_phone)
        self.login(client_phone)
        r = self.client.get(f"/messages/technicien/{artisan_id}", follow_redirects=True)
        return artisan_id, int(r.request.path.split("/")[-1])

    def test_message_content_collapses_excessive_blank_lines(self):
        _, conv_id = self._open_direct("+224610000020")
        content = "Bonjour" + ("\n" * 40) + "fin"
        self.client.post(f"/messages/{conv_id}", data={"content": content})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            m = conn.execute(
                "SELECT content FROM conversation_messages"
                " WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conv_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(m["content"], "Bonjour\n\nfin")

    def test_text_bubble_html_has_no_stray_whitespace(self):
        """La bulle utilise white-space:pre-wrap : tout espace/saut de ligne
        du TEMPLATE (pas du contenu) s'y afficherait comme un vrai blanc visible
        et gonflerait la bulle. Non-regression du bug 'bulle geante'."""
        artisan_id, conv_id = self._open_direct("+224610000021")
        self.client.post(f"/messages/{conv_id}", data={"content": "Bonjour"})
        r = self.client.get(f"/messages/{conv_id}")
        html = r.data.decode("utf-8", "replace")
        i = html.index('<div class="c-bubble')
        i = html.index('>', i) + 1
        j = html.index('<div class="c-meta">', i)
        self.assertEqual(html[i:j], "Bonjour")

    def test_image_message_is_stored_with_attachment(self):
        _, conv_id = self._open_direct()
        px = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
              "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        r = self.client.post(f"/messages/{conv_id}",
                             data={"content": "voici la photo", "message_type": "image",
                                   "attachment": px, "attachment_name": "p.png"},
                             headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(r.status_code, 200)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            m = conn.execute(
                "SELECT message_type, attachment_url, content FROM conversation_messages"
                " WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conv_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(m["message_type"], "image")
        self.assertTrue(m["attachment_url"])

    def test_voice_message_stored(self):
        _, conv_id = self._open_direct("+224610000013")
        audio = "data:audio/webm;base64,QQ=="
        r = self.client.post(f"/messages/{conv_id}",
                             data={"message_type": "audio", "attachment": audio,
                                   "attachment_name": "v.webm", "duration_ms": "3200"},
                             headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(r.status_code, 200)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            m = conn.execute(
                "SELECT message_type, duration_ms FROM conversation_messages"
                " WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conv_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(m["message_type"], "audio")
        self.assertEqual(m["duration_ms"], 3200)

    def test_block_prevents_sending(self):
        artisan_id, conv_id = self._open_direct("+224610000014")
        r = self.client.post(f"/messages/{conv_id}/block", data={"action": "block"})
        self.assertTrue(r.get_json()["blocked"])
        r2 = self.client.post(f"/messages/{conv_id}", data={"content": "hello"},
                              headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(r2.status_code, 403)
        self.client.post(f"/messages/{conv_id}/block", data={"action": "unblock"})
        r3 = self.client.post(f"/messages/{conv_id}", data={"content": "hello again"},
                              headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(r3.status_code, 200)

    def test_mute_report_and_delete(self):
        _, conv_id = self._open_direct("+224610000015")
        r = self.client.post(f"/messages/{conv_id}/prefs", data={"muted": "1"})
        self.assertTrue(r.get_json()["muted"])
        r = self.client.post(f"/messages/{conv_id}/report",
                             data={"reason": "spam", "details": "pub"})
        self.assertTrue(r.get_json()["ok"])
        r = self.client.post(f"/messages/{conv_id}/delete", data={})
        self.assertTrue(r.get_json()["ok"])
        lst = self.client.get("/messages")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            rep = conn.execute("SELECT reason FROM conversation_reports").fetchone()
            pref = conn.execute(
                "SELECT deleted_at FROM conversation_prefs WHERE conversation_id = ?",
                (conv_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(rep["reason"], "spam")
        self.assertIsNotNone(pref["deleted_at"])


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

    def test_admin_login_grants_immediate_dashboard_access(self):
        """L'etape de deverrouillage a ete retiree : la connexion admin donne
        un acces direct au tableau de bord, sans second mot de passe."""
        response = self.client.post("/login", data={
            "identifier": "admin@fixpro.local",
            "password": "adminpass"}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/dashboard", response.location or "")

        dashboard = self.client.get("/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200)

    def test_admin_unlock_route_redirects_to_dashboard(self):
        """/admin/unlock (ancienne etape) redirige sans redemander de mot de passe."""
        self.client.post("/login", data={
            "identifier": "admin@fixpro.local",
            "password": "adminpass"}, follow_redirects=False)
        response = self.client.get("/admin/unlock", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/dashboard", response.location or "")

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
            self.assertIn("/admin/dashboard", r.headers["Location"])
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

    def test_admin_technician_leads_page_and_status_update(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO technician_leads (first_name, last_name, phone,"
                " profession, city) VALUES ('Ada', 'Balde', '+224620000009',"
                " 'Électricité', 'Kaloum')")
            conn.commit()
            lid = conn.execute("SELECT id FROM technician_leads").fetchone()["id"]
        finally:
            conn.close()
        self.login_admin()
        r = self.client.get("/admin/candidatures-techniciens")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Balde", r.get_data(as_text=True))
        self.client.post("/admin/candidatures-techniciens", data={
            "lead_id": lid, "status": "valide"}, follow_redirects=True)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            st = conn.execute(
                "SELECT status FROM technician_leads WHERE id = ?", (lid,)).fetchone()["status"]
        finally:
            conn.close()
        self.assertEqual(st, "valide")

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



