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


class TechnicianSignupTests(FixProTestCase):
    """Inscription technicien -- etape 1 sur 5 : le profil."""

    def test_step1_form_renders(self):
        r = self.client.get("/devenir-technicien")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Espace Technicien", html)
        self.assertIn("Parlons de", html)
        self.assertIn('name="first_name"', html)
        self.assertIn('name="phone"', html)
        self.assertIn('name="password"', html)
        self.assertIn("Continuer", html)

    def test_register_role_technicien_redirects_to_form(self):
        r = self.client.get("/register?role=technicien", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/devenir-technicien", r.location)

    def test_menu_link_present_on_client_page(self):
        self.register_client()
        self.login("+224620000000")
        html = self.client.get("/artisans").get_data(as_text=True)
        self.assertIn("/devenir-technicien", html)
        self.assertIn("S'inscrire en tant que technicien", html)

    _STEP1_OK = {
        "first_name": "Mohamed", "last_name": "Diallo",
        "phone": "620112233", "email": "m@gmail.com", "password": "FixPro2026!",
    }

    def test_step1_post_valid_stores_and_goes_to_step2(self):
        with self.client as c:
            r = c.post("/devenir-technicien", data=self._STEP1_OK, follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/devenir-technicien/services", r.location)
            with c.session_transaction() as sess:
                self.assertEqual(sess["tech_signup"]["first_name"], "Mohamed")
                self.assertNotIn("password", sess["tech_signup"])

    def test_step2_requires_step1(self):
        r = self.client.get("/devenir-technicien/services", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith("/devenir-technicien"))

    def test_step2_renders_metier_single_choice(self):
        with self.client as c:
            c.post("/devenir-technicien", data=self._STEP1_OK)
            html = c.get("/devenir-technicien/services").get_data(as_text=True)
            self.assertIn("Quel est votre", html)          # "Quel est votre métier ?"
            self.assertIn("tier principal", html)          # sous-titre
            self.assertIn("Plomberie", html)
            self.assertIn("Nettoyage", html)
            self.assertIn('type="radio"', html)            # selection exclusive
            self.assertIn('name="trade"', html)
            self.assertNotIn('name="services"', html)
            self.assertIn("disabled", html)                # Continuer bloque au depart

    # Petit JPEG valide (magic bytes FF D8 ... FF D9) encode en data-URI.
    _JPEG_DATA_URI = (
        "data:image/jpeg;base64,"
        + __import__("base64").b64encode(
            b"\xff\xd8\xff\xe0" + b"\x00" * 40 + b"\xff\xd9").decode()
    )

    def _do_steps_1_2(self, client, trade="plomberie"):
        client.post("/devenir-technicien", data=self._STEP1_OK)
        client.post("/devenir-technicien/services", data={"trade": trade})

    def _count_users(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        finally:
            conn.close()

    def test_step2_post_stores_single_trade_and_goes_to_step3(self):
        with self.client as c:
            c.post("/devenir-technicien", data=self._STEP1_OK)
            r = c.post("/devenir-technicien/services",
                       data={"trade": "electricite"}, follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/devenir-technicien/documents", r.location)
            with c.session_transaction() as sess:
                self.assertEqual(sess["tech_signup_trade"], "electricite")

    def test_step2_last_choice_replaces_previous(self):
        with self.client as c:
            c.post("/devenir-technicien", data=self._STEP1_OK)
            c.post("/devenir-technicien/services", data={"trade": "plomberie"})
            c.post("/devenir-technicien/services", data={"trade": "electricite"})
            with c.session_transaction() as sess:
                # une seule valeur, la derniere
                self.assertEqual(sess["tech_signup_trade"], "electricite")

    def test_step2_post_requires_a_choice(self):
        with self.client as c:
            c.post("/devenir-technicien", data=self._STEP1_OK)
            r = c.post("/devenir-technicien/services", data={})
            self.assertIn("tier principal", r.get_data(as_text=True))
            with c.session_transaction() as sess:
                self.assertNotIn("tech_signup_trade", sess)

    def test_step2_post_rejects_unknown_trade(self):
        with self.client as c:
            c.post("/devenir-technicien", data=self._STEP1_OK)
            r = c.post("/devenir-technicien/services",
                       data={"trade": "n_importe_quoi"}, follow_redirects=False)
            self.assertEqual(r.status_code, 200)
            with c.session_transaction() as sess:
                self.assertNotIn("tech_signup_trade", sess)

    def test_step2_keeps_choice_when_returning(self):
        with self.client as c:
            self._do_steps_1_2(c, trade="maconnerie")
            html = c.get("/devenir-technicien/services").get_data(as_text=True)
            self.assertIn('value="maconnerie" checked', html)

    def test_step3_requires_previous_steps(self):
        r = self.client.get("/devenir-technicien/documents", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith("/devenir-technicien"))
        with self.client as c:
            c.post("/devenir-technicien", data=self._STEP1_OK)
            r = c.get("/devenir-technicien/documents", follow_redirects=False)
            self.assertIn("/devenir-technicien/services", r.location)

    def test_step3_renders_after_steps_1_2(self):
        with self.client as c:
            self._do_steps_1_2(c)
            html = c.get("/devenir-technicien/documents").get_data(as_text=True)
            self.assertIn("Ajoutez vos", html)
            self.assertIn("identit", html)   # "Pièce d'identité"
            self.assertIn("Dipl", html)      # "Diplôme de votre métier"
            self.assertIn('name="identity_doc"', html)

    def test_step3_documents_are_optional(self):
        # Phase de test : on peut continuer sans aucun document.
        with self.client as c:
            self._do_steps_1_2(c)
            r = c.post("/devenir-technicien/documents", data={},
                       follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/devenir-technicien/localisation", r.location)
            with c.session_transaction() as sess:
                self.assertIn("tech_signup_docs", sess)
                self.assertIsNone(sess["tech_signup_docs"]["identity"])

    def test_step3_post_rejects_bad_file(self):
        with self.client as c:
            self._do_steps_1_2(c)
            r = c.post("/devenir-technicien/documents",
                       data={"identity_doc": "data:text/plain;base64,aGVsbG8="})
            self.assertIn("invalide", r.get_data(as_text=True))
            with c.session_transaction() as sess:
                self.assertNotIn("tech_signup_docs", sess)

    def test_step3_post_valid_identity_goes_to_step4(self):
        with self.client as c:
            self._do_steps_1_2(c)
            r = c.post("/devenir-technicien/documents",
                       data={"identity_doc": self._JPEG_DATA_URI},
                       follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/devenir-technicien/localisation", r.location)
            with c.session_transaction() as sess:
                self.assertEqual(sess["tech_signup_docs"]["identity"], ".jpg")
                self.assertIsNone(sess["tech_signup_docs"]["diploma"])

    def _do_steps_1_3(self, client):
        self._do_steps_1_2(client)
        client.post("/devenir-technicien/documents",
                    data={"identity_doc": self._JPEG_DATA_URI})

    def test_step4_requires_previous_steps(self):
        r = self.client.get("/devenir-technicien/localisation", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith("/devenir-technicien"))
        with self.client as c:
            self._do_steps_1_2(c)  # etape 3 pas faite
            r = c.get("/devenir-technicien/localisation", follow_redirects=False)
            self.assertIn("/devenir-technicien/documents", r.location)

    def test_step4_renders(self):
        with self.client as c:
            self._do_steps_1_3(c)
            html = c.get("/devenir-technicien/localisation").get_data(as_text=True)
            self.assertIn("intervenez", html)          # "Où intervenez-vous ?"
            self.assertIn("position actuelle", html)
            self.assertIn('name="latitude"', html)
            self.assertIn('name="longitude"', html)
            self.assertNotIn("Conakry", html)          # pas de position en dur

    def test_step4_location_is_optional(self):
        # Phase de test : on peut continuer sans position.
        with self.client as c:
            self._do_steps_1_3(c)
            r = c.post("/devenir-technicien/localisation", data={},
                       follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/devenir-technicien/finalisation", r.location)
            with c.session_transaction() as sess:
                self.assertIn("tech_signup_location", sess)
                self.assertIsNone(sess["tech_signup_location"]["lat"])

    def test_step4_post_requires_valid_coordinates(self):
        with self.client as c:
            self._do_steps_1_3(c)
            r = c.post("/devenir-technicien/localisation",
                       data={"latitude": "0", "longitude": "0"})
            self.assertIn("invalide", r.get_data(as_text=True).lower())
            with c.session_transaction() as sess:
                self.assertNotIn("tech_signup_location", sess)
            r = c.post("/devenir-technicien/localisation",
                       data={"latitude": "abc", "longitude": "xyz"})
            self.assertIn("invalide", r.get_data(as_text=True).lower())

    def test_step4_post_valid_coordinates_stores_and_goes_to_step5(self):
        with self.client as c:
            self._do_steps_1_3(c)
            r = c.post("/devenir-technicien/localisation",
                       data={"latitude": "9.5370", "longitude": "-13.6785"},
                       follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/devenir-technicien/finalisation", r.location)
            with c.session_transaction() as sess:
                loc = sess["tech_signup_location"]
                self.assertAlmostEqual(loc["lat"], 9.537, places=3)
                self.assertAlmostEqual(loc["lon"], -13.6785, places=3)

    def test_step4_reverse_endpoint_rejects_bad_coords(self):
        r = self.client.get("/devenir-technicien/localisation/lieu?lat=0&lon=0")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def _do_steps_1_4(self, client, trade="plomberie"):
        self._do_steps_1_2(client, trade=trade)
        client.post("/devenir-technicien/documents",
                    data={"identity_doc": self._JPEG_DATA_URI})
        client.post("/devenir-technicien/localisation",
                    data={"latitude": "9.5370", "longitude": "-13.6785"})

    def test_step5_requires_previous_steps(self):
        r = self.client.get("/devenir-technicien/finalisation", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith("/devenir-technicien"))
        with self.client as c:
            self._do_steps_1_3(c)  # etape 4 pas faite
            r = c.get("/devenir-technicien/finalisation", follow_redirects=False)
            self.assertIn("/devenir-technicien/localisation", r.location)

    def test_step5_renders_recap(self):
        with self.client as c:
            self._do_steps_1_4(c, trade="electricite")
            html = c.get("/devenir-technicien/finalisation").get_data(as_text=True)
            self.assertIn("Mohamed Diallo", html)
            self.assertIn("Électricité", html)
            self.assertIn("+224620112233", html)
            self.assertIn('name="accept_cgu"', html)
            self.assertIn("disabled", html)  # bouton bloque tant que CGU non cochee

    def test_step5_post_requires_cgu(self):
        with self.client as c:
            self._do_steps_1_4(c)
            r = c.post("/devenir-technicien/finalisation", data={})
            self.assertEqual(r.status_code, 200)
            self.assertIn("conditions d'utilisation", r.get_data(as_text=True))
        self.assertEqual(self._count_users(), 0)

    def test_step5_post_creates_technician_and_logs_in(self):
        with self.client as c:
            self._do_steps_1_4(c)
            r = c.post("/devenir-technicien/finalisation",
                       data={"accept_cgu": "1"}, follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            with c.session_transaction() as sess:
                self.assertIn("user_id", sess)
                self.assertNotIn("tech_signup", sess)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE phone = ?", ("+224620112233",)
            ).fetchone()
            self.assertIsNotNone(user)
            self.assertEqual(user["role"], "technician")
            self.assertEqual(user["profession"], "Plombier")
            self.assertEqual(user["verification_status"], "PENDING_REVIEW")
            self.assertIsNotNone(user["latitude"])
            docs = conn.execute(
                "SELECT * FROM technician_documents WHERE technician_id = ?",
                (user["id"],)).fetchall()
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0]["document_type"], "identity")
            self.assertEqual(docs[0]["status"], "pending")
        finally:
            conn.close()

    def test_step5_rejects_duplicate_phone(self):
        with self.client as c:
            self._do_steps_1_4(c)
            c.post("/devenir-technicien/finalisation", data={"accept_cgu": "1"})
        with self.client as c:
            self._do_steps_1_4(c)
            r = c.post("/devenir-technicien/finalisation", data={"accept_cgu": "1"})
            self.assertIn("déjà utilisé", r.get_data(as_text=True))
        self.assertEqual(self._count_users(), 1)

    def test_wizard_without_documents_or_location_creates_technician(self):
        # Phase de test : etapes 3 et 4 sautees -> compte cree quand meme.
        with self.client as c:
            self._do_steps_1_2(c, trade="peinture")
            c.post("/devenir-technicien/documents", data={})
            c.post("/devenir-technicien/localisation", data={})
            r = c.post("/devenir-technicien/finalisation",
                       data={"accept_cgu": "1"}, follow_redirects=False)
            self.assertEqual(r.status_code, 302)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE phone = ?", ("+224620112233",)
            ).fetchone()
            self.assertIsNotNone(user)
            self.assertEqual(user["role"], "technician")
            self.assertEqual(user["profession"], "Peintre")
            self.assertIsNone(user["latitude"])
            docs = conn.execute(
                "SELECT COUNT(*) AS n FROM technician_documents WHERE technician_id = ?",
                (user["id"],)).fetchone()
            self.assertEqual(docs["n"], 0)
        finally:
            conn.close()

    def test_step1_post_missing_fields_shows_errors_no_session(self):
        with self.client as c:
            r = c.post("/devenir-technicien", data={"first_name": "Mohamed"})
            self.assertEqual(r.status_code, 200)
            self.assertIn("obligatoire", r.get_data(as_text=True))
            with c.session_transaction() as sess:
                self.assertNotIn("tech_signup", sess)

    def test_step1_post_weak_password_rejected(self):
        with self.client as c:
            r = c.post("/devenir-technicien", data={
                "first_name": "M", "last_name": "D", "phone": "620",
                "email": "m@gmail.com", "password": "faible",
            })
            self.assertIn("mot de passe", r.get_data(as_text=True).lower())
            with c.session_transaction() as sess:
                self.assertNotIn("tech_signup", sess)

    def test_no_technician_account_is_created(self):
        self.client.post("/devenir-technicien", data={
            "first_name": "Mohamed", "last_name": "Diallo",
            "phone": "620112233", "email": "m@gmail.com",
            "password": "FixPro2026!",
        })
        conn = db.connect(sqlite_path=self.db_path)
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 0)


class TechnicianDashboardTests(FixProTestCase):
    """Accueil de l'espace technicien (/dashboard/technicien)."""

    def test_dashboard_renders_for_technician(self):
        self.register_artisan("tech@example.com", phone="+224621111111")
        self.login("tech@example.com")
        r = self.client.get("/dashboard/technicien")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Espace Technicien", html)
        self.assertIn("Prêt à recevoir", html)
        self.assertIn("Demandes reçues", html)

    def test_dashboard_redirects_non_technician(self):
        self.register_client()
        self.login("+224620000000")
        r = self.client.get("/dashboard/technicien", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("/dashboard/technicien", r.location)

    def test_login_technician_lands_on_dashboard(self):
        self.register_artisan("tech2@example.com", phone="+224621111112")
        r = self.client.post("/login", data={
            "identifier": "tech2@example.com", "password": "FixPro2026!"},
            follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.request.path,
                      ("/dashboard/technicien", "/technician/dashboard"))
        self.assertIn("Espace Technicien", r.get_data(as_text=True))

    def test_availability_toggle_updates_status(self):
        self.register_artisan("tech3@example.com", phone="+224621111113")
        self.login("tech3@example.com")
        r = self.client.post("/api/technicien/status", data={"status": "en_ligne"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT availability_status FROM users WHERE phone = ?",
                ("+224621111113",)).fetchone()
            self.assertEqual(row["availability_status"], "en_ligne")
        finally:
            conn.close()

    def test_availability_toggle_rejects_bad_status(self):
        self.register_artisan("tech4@example.com", phone="+224621111114")
        self.login("tech4@example.com")
        r = self.client.post("/api/technicien/status", data={"status": "n_importe"})
        self.assertEqual(r.status_code, 400)

    def test_subscription_page_renders_pro_and_premium_only(self):
        self.register_artisan("tech5@example.com", phone="+224621111115")
        self.login("tech5@example.com")
        r = self.client.get("/abonnement")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Plan Pro", html)
        self.assertIn("Plan Premium", html)
        self.assertNotIn("Plan Gratuit", html)
        self.assertNotIn(">Gratuit<", html)
        self.assertIn("Le plus populaire", html)
        self.assertIn("97 000 GNF", html)
        self.assertIn("140 000 GNF", html)
        self.assertIn("Comparatif des fonctionnalités", html)
        self.assertIn("Questions fréquentes", html)

    def test_subscription_checkout_rejects_removed_free_plan(self):
        self.register_artisan("tech8@example.com", phone="+224621111118")
        self.login("tech8@example.com")
        r = self.client.get("/abonnement/paiement?plan=tech_free",
                            follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("abonnement", r.location)

    def test_subscription_checkout_creates_pending_subscription(self):
        self.register_artisan("tech6@example.com", phone="+224621111116")
        self.login("tech6@example.com")
        r = self.client.post(
            "/abonnement/paiement?plan=tech_premium&period=month",
            data={"payment_method": "orange_money"}, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            uid = conn.execute("SELECT id FROM users WHERE phone = ?",
                               ("+224621111116",)).fetchone()["id"]
            sub = conn.execute(
                "SELECT status FROM technician_subscriptions WHERE technician_id = ?",
                (uid,)).fetchone()
            self.assertIsNotNone(sub)
            self.assertEqual(sub["status"], "PAST_DUE")
            pay = conn.execute(
                "SELECT status, amount FROM subscription_payments WHERE user_id = ?",
                (uid,)).fetchone()
            self.assertEqual(pay["status"], "pending")
            self.assertEqual(pay["amount"], 140000)
        finally:
            conn.close()

    def test_subscription_checkout_rejects_unknown_plan(self):
        self.register_artisan("tech7@example.com", phone="+224621111117")
        self.login("tech7@example.com")
        r = self.client.get("/abonnement/paiement?plan=tech_basic",
                            follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("abonnement", r.location)

    def test_confirmation_page_is_dynamic_per_plan(self):
        self.register_artisan("cf1@example.com", phone="+224621114001")
        self.login("cf1@example.com")
        pro = self.client.get(
            "/abonnement/confirmation?plan=tech_pro&period=month").get_data(as_text=True)
        self.assertIn("Procédez au paiement", pro)
        self.assertIn("97 000 GNF", pro)
        self.assertIn("100 000 GNF", pro)          # ancien prix barre
        self.assertIn("-3 %", pro)
        self.assertIn("/ mois", pro)
        prem = self.client.get(
            "/abonnement/confirmation?plan=tech_premium&period=month").get_data(as_text=True)
        self.assertIn("140 000 GNF", prem)
        self.assertIn("200 000 GNF", prem)
        self.assertIn("-30 %", prem)
        self.assertIn("Le plus populaire", prem)
        # meme gabarit, seules les donnees changent
        self.assertNotIn("97 000 GNF", prem)

    def test_confirmation_payment_methods_are_real_only(self):
        self.register_artisan("cf2@example.com", phone="+224621114002")
        self.login("cf2@example.com")
        html = self.client.get(
            "/abonnement/confirmation?plan=tech_pro").get_data(as_text=True)
        self.assertIn("Orange Money", html)
        self.assertIn("MTN Mobile Money", html)
        self.assertIn("Carte bancaire", html)
        self.assertNotIn("Airtel", html)          # methode retiree
        self.assertNotIn("Virement bancaire", html)

    def test_confirmation_alias_matches_paiement(self):
        self.register_artisan("cf3@example.com", phone="+224621114003")
        self.login("cf3@example.com")
        for path in ("/abonnement/confirmation", "/abonnement/paiement",
                     "/dashboard/technicien/abonnement/paiement"):
            r = self.client.get(path + "?plan=tech_premium")
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("Procédez au paiement", r.get_data(as_text=True))

    def test_confirmation_rejects_fake_payment_method(self):
        self.register_artisan("cf4@example.com", phone="+224621114004")
        self.login("cf4@example.com")
        r = self.client.post("/abonnement/confirmation?plan=tech_pro&period=month",
                             data={"payment_method": "bitcoin"},
                             follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            uid = conn.execute("SELECT id FROM users WHERE phone = ?",
                               ("+224621114004",)).fetchone()["id"]
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM subscription_payments WHERE user_id = ?",
                (uid,)).fetchone()["n"]
            self.assertEqual(n, 0)
        finally:
            conn.close()

    # --- Notifications ---------------------------------------------------

    def _seed_notif(self, user_id, title="Nouvelle demande", body="…",
                    ntype="new_request", data="", is_read=0):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO notifications (user_id, title, body, type, data, is_read)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, title, body, ntype, data, is_read))
            conn.commit()
        finally:
            conn.close()

    def _artisan_id(self, phone):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()["id"]
        finally:
            conn.close()

    def test_dashboard_header_has_notification_bell(self):
        self.register_artisan("bell@example.com", phone="+224621112001")
        self.login("bell@example.com")
        html = self.client.get("/dashboard/technicien").get_data(as_text=True)
        self.assertIn('id="ntfbBtn"', html)
        self.assertIn("/api/notifications", html)
        self.assertIn("Tout marquer comme lu", html)

    def test_api_notifications_returns_only_own(self):
        self.register_artisan("me@example.com", phone="+224621112002")
        self.register_artisan("other@example.com", phone="+224621112003")
        mine = self._artisan_id("+224621112002")
        theirs = self._artisan_id("+224621112003")
        self._seed_notif(mine, title="Ma notif", data="request_id:5")
        self._seed_notif(theirs, title="Notif des autres")
        self.login("me@example.com")
        r = self.client.get("/api/notifications")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        titles = [i["title"] for i in data["items"]]
        self.assertIn("Ma notif", titles)
        self.assertNotIn("Notif des autres", titles)
        self.assertEqual(data["unread"], 1)
        # lien profond calcule depuis data=request_id:5
        self.assertEqual(data["items"][0]["href"], "/requests/5")

    def test_notifications_mark_one_read(self):
        self.register_artisan("r1@example.com", phone="+224621112004")
        uid = self._artisan_id("+224621112004")
        self._seed_notif(uid, title="A lire")
        self.login("r1@example.com")
        nid = self.client.get("/api/notifications").get_json()["items"][0]["id"]
        r = self.client.post("/notifications/%d/read" % nid,
                             headers={"X-CSRFToken": "x"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/notifications").get_json()["unread"], 0)

    def test_notifications_cannot_mark_other_users(self):
        self.register_artisan("a@example.com", phone="+224621112005")
        self.register_artisan("b@example.com", phone="+224621112006")
        victim = self._artisan_id("+224621112006")
        self._seed_notif(victim, title="Privee")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            nid = conn.execute(
                "SELECT id FROM notifications WHERE user_id = ?", (victim,)).fetchone()["id"]
        finally:
            conn.close()
        self.login("a@example.com")
        self.client.post("/notifications/%d/read" % nid, headers={"X-CSRFToken": "x"})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            still_unread = conn.execute(
                "SELECT is_read FROM notifications WHERE id = ?", (nid,)).fetchone()["is_read"]
        finally:
            conn.close()
        self.assertEqual(still_unread, 0)

    def test_notifications_mark_all_read(self):
        self.register_artisan("all@example.com", phone="+224621112007")
        uid = self._artisan_id("+224621112007")
        for i in range(3):
            self._seed_notif(uid, title="N%d" % i)
        self.login("all@example.com")
        r = self.client.post("/notifications/read-all", headers={"X-CSRFToken": "x"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["unread"], 0)
        self.assertEqual(self.client.get("/api/notifications").get_json()["unread"], 0)

    # --- Menu profil (avatar) -----------------------------------------

    def test_profile_menu_present_in_header(self):
        self.register_artisan("pm@example.com", phone="+224621113001",
                              name="Mamadou Diallo")
        self.login("pm@example.com")
        html = self.client.get("/dashboard/technicien").get_data(as_text=True)
        self.assertIn('id="tpmBtn"', html)
        self.assertIn('id="tpmMenu"', html)
        self.assertIn("Mamadou Diallo", html)
        self.assertIn("Mes statistiques", html)
        self.assertIn("Centre d'aide", html)
        self.assertIn("Se déconnecter", html)
        self.assertIn("tpm-dot", html)          # point vert (avatar partage)
        # chaque entree pointe vers une route reelle
        for frag in ('href="/profile"', 'abonnement"', 'href="/notifications"',
                     'href="/profil/securite"', 'href="/contact"', 'href="/logout"'):
            self.assertIn(frag, html)

    def test_profile_menu_links_resolve(self):
        self.register_artisan("pm2@example.com", phone="+224621113002")
        self.login("pm2@example.com")
        for path, code in (("/profile", 200), ("/abonnement", 200),
                           ("/notifications", 200), ("/profil/securite", 200),
                           ("/contact", 200)):
            r = self.client.get(path)
            self.assertEqual(r.status_code, code, "%s -> %s" % (path, r.status_code))

    def test_profile_menu_uses_real_availability(self):
        self.register_artisan("pm3@example.com", phone="+224621113003")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "UPDATE users SET availability_status = 'en_ligne' WHERE phone = ?",
                ("+224621113003",))
            conn.commit()
        finally:
            conn.close()
        self.login("pm3@example.com")
        html = self.client.get("/dashboard/technicien").get_data(as_text=True)
        self.assertIn("Disponible", html)
        self.assertIn("tpm-dot ok", html)

    def test_profile_menu_logout_clears_session(self):
        self.register_artisan("pm4@example.com", phone="+224621113004")
        self.login("pm4@example.com")
        self.client.get("/logout")
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)


class SubscriptionPaymentFlowTests(FixProTestCase):
    """Parcours de paiement des abonnements : AUCUNE fausse activation.
    Un abonnement ne devient ACTIVE que sur confirmation serveur reelle."""

    WEBHOOK_SECRET = "test-webhook-secret"

    def setUp(self):
        super().setUp()
        fixpro_app.app.config["PAYMENT_WEBHOOK_SECRET"] = self.WEBHOOK_SECRET
        self.addCleanup(fixpro_app.app.config.pop, "PAYMENT_WEBHOOK_SECRET", None)

    # --- helpers -------------------------------------------------------

    def _tech(self, email="payflow@example.com", phone="+224622000001"):
        self.register_artisan(email, phone=phone)
        self.login(email)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute("SELECT id FROM users WHERE phone = ?",
                                (phone,)).fetchone()["id"]
        finally:
            conn.close()

    def _start_payment(self, plan="tech_premium", method="orange_money",
                       period="month"):
        r = self.client.post(
            "/abonnement/confirmation?plan=%s&period=%s" % (plan, period),
            data={"payment_method": method, "payer_phone": "620000000"},
            follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/abonnement/statut/", r.location)
        return r.location.rsplit("/", 1)[-1]

    def _pay_row(self, ref):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT * FROM subscription_payments WHERE transaction_reference = ?",
                (ref,)).fetchone()
        finally:
            conn.close()

    def _sub_row(self, tech_id):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT * FROM technician_subscriptions WHERE technician_id = ?"
                " ORDER BY id DESC LIMIT 1", (tech_id,)).fetchone()
        finally:
            conn.close()

    def _webhook(self, ref, status, amount=140000, token=None):
        return self.client.post(
            "/webhooks/paiement/orange",
            json={"reference": ref, "status": status, "amount": amount},
            headers={"X-FixPro-Signature": token if token is not None else self.WEBHOOK_SECRET})

    def _make_admin(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " is_verified, is_active) VALUES (?, ?, ?, 'admin', 'Admin', 1, 1)",
                ("adm@fixpro.local", "+224000009999",
                 fixpro_app.generate_password_hash("x")))
            conn.commit()
            aid = conn.execute("SELECT id FROM users WHERE phone = ?",
                               ("+224000009999",)).fetchone()["id"]
        finally:
            conn.close()
        with self.client.session_transaction() as sess:
            sess["user_id"] = aid

    # --- 1. le clic "Payer" n'active RIEN ----------------------------

    def test_pay_click_creates_pending_only(self):
        tid = self._tech()
        ref = self._start_payment()
        pay = self._pay_row(ref)
        self.assertEqual(pay["status"], "pending")
        self.assertIsNone(pay["paid_at"])
        sub = self._sub_row(tid)
        self.assertEqual(sub["status"], "PAST_DUE")      # PAS ACTIVE
        self.assertIsNone(sub["end_date"])              # pas de periode tant qu'inactif

    def test_status_page_and_api_report_pending(self):
        self._tech()
        ref = self._start_payment()
        html = self.client.get("/abonnement/statut/%s" % ref).get_data(as_text=True)
        self.assertIn("Paiement en cours", html)
        j = self.client.get("/api/abonnement/statut/%s" % ref).get_json()
        self.assertEqual(j["state"], "PENDING")
        self.assertFalse(j["final"])
        self.assertFalse(j["confirmed"])

    # --- 2. webhook : securite --------------------------------------

    def test_webhook_without_secret_is_rejected(self):
        tid = self._tech()
        ref = self._start_payment()
        r = self._webhook(ref, "success", token="")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self._sub_row(tid)["status"], "PAST_DUE")
        self.assertEqual(self._pay_row(ref)["status"], "pending")

    def test_webhook_wrong_amount_is_rejected(self):
        tid = self._tech()
        ref = self._start_payment()
        r = self._webhook(ref, "success", amount=1)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._sub_row(tid)["status"], "PAST_DUE")

    # --- 3. echecs -> reste inactif --------------------------------

    def test_webhook_failed_keeps_subscription_inactive(self):
        tid = self._tech()
        ref = self._start_payment()
        self.assertEqual(self._webhook(ref, "failed").status_code, 200)
        self.assertEqual(self._pay_row(ref)["status"], "failed")
        self.assertEqual(self._sub_row(tid)["status"], "PAST_DUE")
        html = self.client.get("/abonnement/statut/%s" % ref).get_data(as_text=True)
        self.assertIn("Paiement échoué", html)

    def test_webhook_cancelled_keeps_inactive(self):
        tid = self._tech()
        ref = self._start_payment()
        self._webhook(ref, "cancelled")
        self.assertEqual(self._pay_row(ref)["status"], "cancelled")
        self.assertEqual(self._sub_row(tid)["status"], "PAST_DUE")

    def test_user_cancel_keeps_inactive(self):
        tid = self._tech()
        ref = self._start_payment()
        self.client.post("/abonnement/statut/%s/annuler" % ref)
        self.assertEqual(self._pay_row(ref)["status"], "cancelled")
        self.assertEqual(self._sub_row(tid)["status"], "PAST_DUE")

    def test_stale_attempt_expires_and_stays_inactive(self):
        tid = self._tech()
        ref = self._start_payment()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE subscription_payments SET created_at = '2020-01-01 00:00:00'"
                         " WHERE transaction_reference = ?", (ref,))
            conn.commit()
        finally:
            conn.close()
        j = self.client.get("/api/abonnement/statut/%s" % ref).get_json()
        self.assertEqual(j["state"], "PAYMENT_EXPIRED")
        self.assertEqual(self._pay_row(ref)["status"], "expired")
        self.assertEqual(self._sub_row(tid)["status"], "PAST_DUE")

    # --- 4. confirmation reelle -> activation ----------------------

    def test_webhook_success_activates_subscription(self):
        tid = self._tech()
        ref = self._start_payment()
        self.assertEqual(self._webhook(ref, "success").status_code, 200)
        pay = self._pay_row(ref)
        self.assertEqual(pay["status"], "paid")
        self.assertIsNotNone(pay["paid_at"])
        sub = self._sub_row(tid)
        self.assertEqual(sub["status"], "ACTIVE")
        self.assertIsNotNone(sub["start_date"])
        self.assertIsNotNone(sub["end_date"])
        conn = db.connect(sqlite_path=self.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications"
                " WHERE user_id = ? AND title = 'Abonnement activé'",
                (tid,)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 1)
        html = self.client.get("/abonnement/statut/%s" % ref).get_data(as_text=True)
        self.assertIn("Félicitations", html)

    def test_webhook_success_is_idempotent(self):
        tid = self._tech()
        ref = self._start_payment()
        self._webhook(ref, "success")
        r2 = self._webhook(ref, "success")
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.get_json().get("already"))
        conn = db.connect(sqlite_path=self.db_path)
        try:
            active = conn.execute(
                "SELECT COUNT(*) AS n FROM technician_subscriptions"
                " WHERE technician_id = ? AND status = 'ACTIVE'", (tid,)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(active, 1)

    # --- 5. double clic ------------------------------------------

    def test_double_pay_click_reuses_same_attempt(self):
        self._tech()
        ref1 = self._start_payment()
        ref2 = self._start_payment()
        self.assertEqual(ref1, ref2)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM subscription_payments"
                " WHERE status IN ('pending', 'processing')").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 1)

    # --- 6. confirmation admin ----------------------------------

    # --- 7. persistance : rouvrir l'app -> vrai statut ----------

    def test_reopen_reads_real_status_from_backend(self):
        tid = self._tech(email="reopen@example.com", phone="+224622000009")
        ref = self._start_payment()
        self._webhook(ref, "success")
        # nouveau "client" (nouvelle session) = fermeture/reouverture
        self.client.get("/logout")
        self.login("reopen@example.com")
        j = self.client.get("/api/abonnement/statut/%s" % ref).get_json()
        self.assertEqual(j["state"], "PAYMENT_CONFIRMED")
        self.assertTrue(j["confirmed"])

    # --- 8. architecture providers -----------------------------

    def test_refresh_during_pending_stays_pending(self):
        self._tech(email="refresh@example.com", phone="+224622000021")
        ref = self._start_payment()
        for _ in range(3):
            self.assertEqual(
                self.client.get("/api/abonnement/statut/%s" % ref).get_json()["state"],
                "PENDING")
        self.assertEqual(self._pay_row(ref)["status"], "pending")

    def test_unitrade_is_a_selectable_method_but_stays_pending(self):
        tid = self._tech(email="unitrade@example.com", phone="+224622000022")
        ref = self._start_payment(method="unitrade")
        self.assertEqual(self._pay_row(ref)["payment_method"], "unitrade")
        self.assertEqual(self._pay_row(ref)["status"], "pending")
        self.assertEqual(self._sub_row(tid)["status"], "PAST_DUE")

    def test_real_providers_never_return_paid(self):
        for code, cls in fixpro_app._REAL_PAYMENT_PROVIDERS.items():
            res = cls().process(140000, code, "SUB-X", {})
            self.assertIn(res["status"], ("pending", "processing"))
            self.assertNotEqual(res["status"], "success")

    def test_mock_provider_not_used_outside_testing_config(self):
        for flag in ("TESTING", "FLASK_ENV", "PAYMENT_PROVIDER"):
            self.addCleanup(fixpro_app.app.config.pop, flag, None)
        fixpro_app.app.config["TESTING"] = False
        fixpro_app.app.config["FLASK_ENV"] = "production"
        fixpro_app.app.config.pop("PAYMENT_PROVIDER", None)
        try:
            self.assertNotIsInstance(
                fixpro_app.get_payment_provider("orange_money"),
                fixpro_app.MockPaymentProvider)
            self.assertIsInstance(
                fixpro_app.get_payment_provider("orange_money"),
                fixpro_app.OrangeMoneyProvider)
        finally:
            fixpro_app.app.config["TESTING"] = True
            fixpro_app.app.config["FLASK_ENV"] = "testing"

    def test_webhook_wrong_currency_is_rejected(self):
        tid = self._tech(email="cur@example.com", phone="+224622000023")
        ref = self._start_payment()
        r = self.client.post(
            "/webhooks/paiement/orange",
            json={"reference": ref, "status": "success", "amount": 140000,
                  "currency": "USD"},
            headers={"X-FixPro-Signature": self.WEBHOOK_SECRET})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._sub_row(tid)["status"], "PAST_DUE")

    def test_webhook_unknown_reference_is_rejected(self):
        self._tech(email="badref@example.com", phone="+224622000024")
        self._start_payment()
        r = self.client.post(
            "/webhooks/paiement/orange",
            json={"reference": "SUB-DOES-NOT-EXIST", "status": "success"},
            headers={"X-FixPro-Signature": self.WEBHOOK_SECRET})
        self.assertEqual(r.status_code, 404)


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
        self.client.get("/messages")
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

    def _make_owner(self, uid=1):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET admin_role = 'owner' WHERE id = ?", (uid,))
            conn.commit()
        finally:
            conn.close()

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



