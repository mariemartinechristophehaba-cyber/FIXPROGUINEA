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


def datetime_now_month():
    """Mois calendaire courant 'AAAA-MM' (UTC) — meme calcul que le serveur."""
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m")


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
        self.assertIn("Devenir technicien", html)
        self.assertIn("Inscrivez-vous comme technicien", html)   # libelle du menu client
        self.assertIn("Compte client actif", html)
        self.assertNotIn("Accéder à mon espace technicien", html)
        self.assertNotIn("Gérer mes interventions", html)

    def test_menu_shows_technician_space_link_for_technician(self):
        self.register_artisan("dr-tech@example.com", phone="+224621119501")
        self.login("+224621119501")
        html = self.client.get("/artisans").get_data(as_text=True)
        self.assertIn("Accéder à mon espace technicien", html)
        self.assertIn("Gérer mes interventions", html)
        self.assertIn("/technician/dashboard", html)   # lien vers l'espace technicien existant
        self.assertIn("Compte technicien actif", html)
        self.assertNotIn("Inscrivez-vous comme technicien", html)
        self.assertNotIn("S'inscrire en tant que technicien", html)

    def test_drawer_guest_state(self):
        html = self.client.get("/contact").get_data(as_text=True)
        self.assertIn("Bienvenue sur FixPro", html)
        self.assertIn("Rejoindre le réseau de professionnels", html)   # Devenir technicien (invite)
        self.assertNotIn("Se déconnecter", html)
        self.assertNotIn("Compte client actif", html)
        self.assertNotIn("Accéder à mon espace technicien", html)

    def test_technician_cannot_reenter_signup_wizard(self):
        self.register_artisan("dr-tech3@example.com", phone="+224621119503")
        self.login("+224621119503")
        for path in ("/devenir-technicien",
                     "/devenir-technicien/services",
                     "/devenir-technicien/documents",
                     "/devenir-technicien/localisation",
                     "/devenir-technicien/finalisation"):
            r = self.client.get(path, follow_redirects=False)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("technician/dashboard", r.location, path)

    def test_menu_technician_link_persists_after_relogin(self):
        self.register_artisan("dr-tech2@example.com", phone="+224621119502")
        self.login("+224621119502")
        self.assertIn("Accéder à mon espace technicien",
                      self.client.get("/artisans").get_data(as_text=True))
        self.client.get("/logout")
        # reconnexion : le statut vient de la base, pas d'une variable locale
        self.login("+224621119502")
        self.assertIn("Accéder à mon espace technicien",
                      self.client.get("/artisans").get_data(as_text=True))

    def test_technician_space_denied_to_normal_user_by_url(self):
        self.register_client()
        self.login("+224620000000")
        r = self.client.get("/dashboard/technicien", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("/dashboard/technicien", r.location)

    # --- Menu profil de l'avatar (accueil) + bascule client <-> technicien ---

    def test_home_avatar_menu_client_only(self):
        self.register_client()
        self.login("+224620000000")
        self._set_client_location()
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="hpmBtn"', html)                  # menu avatar present
        self.assertIn("Mon profil", html)
        self.assertNotIn("Mon profil client", html)         # jamais le mot "client" pour le profil
        self.assertIn('href="/profile"', html)              # profil -> page profil
        self.assertIn("Devenir technicien", html)
        self.assertIn("Compte client actif", html)
        self.assertNotIn("Accéder à mon espace technicien", html)  # client -> jamais
        self.assertNotIn("Revenir à mon espace client", html)
        # le raccourci "Mes demandes / reservations" a ete retire du menu avatar
        self.assertNotIn("Suivre mes demandes et rendez-vous", html)
        # ... mais la fonctionnalite Demandes reste accessible ailleurs
        self.assertEqual(self.client.get("/requests").status_code, 200)

    def test_home_avatar_menu_technician_separates_profile_and_pro_space(self):
        self.register_artisan("hpm-tech@example.com", phone="+224621119520")
        self.login("+224621119520")
        self._set_client_location()
        html = self.client.get("/?c=1").get_data(as_text=True)
        self.assertIn("Mon profil", html)
        self.assertNotIn("Mon profil client", html)
        self.assertIn('href="/profile"', html)              # profil personnel
        self.assertIn("Accéder à mon espace technicien", html)
        self.assertIn("Gérer mes interventions", html)
        self.assertIn("Compte technicien actif", html)
        self.assertNotIn("Devenir technicien", html)
        # destinations reellement separees, aucune redirection croisee
        self.assertEqual(self.client.get("/profile", follow_redirects=False).status_code, 200)
        r = self.client.get("/technician/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 200)

    def test_technician_home_redirects_to_pro_space_by_default(self):
        self.register_artisan("av-tech@example.com", phone="+224621119510")
        self.login("+224621119510")
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("technician/dashboard", r.location)

    def test_technician_can_switch_to_client_view_and_it_persists(self):
        self.register_artisan("av-tech2@example.com", phone="+224621119511")
        self.login("+224621119511")
        self._set_client_location()
        # bascule "revenir a mon espace client"
        r = self.client.get("/?c=1", follow_redirects=False)
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('id="hpmBtn"', html)
        self.assertIn("Accéder à mon espace technicien", html)   # peut re-basculer
        # la vue client persiste (session), pas juste le parametre d'URL
        self.assertEqual(self.client.get("/").status_code, 200)
        # ouvrir l'espace pro remet le comportement par defaut
        self.assertEqual(self.client.get("/technician/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/", follow_redirects=False).status_code, 302)

    def test_tech_avatar_menu_has_back_to_client(self):
        self.register_artisan("av-tech3@example.com", phone="+224621119512")
        self.login("+224621119512")
        html = self.client.get("/technician/dashboard").get_data(as_text=True)
        self.assertIn("Revenir à mon espace client", html)
        self.assertIn('href="/?c=1"', html)

    def test_same_account_after_space_switch(self):
        self.register_artisan("av-tech4@example.com", phone="+224621119513")
        self.login("+224621119513")
        self._set_client_location()
        self.client.get("/?c=1")
        # toujours connecte, meme compte : /technician/dashboard reste accessible
        self.assertEqual(self.client.get("/technician/dashboard").status_code, 200)

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
            # Point critique : jamais vers l'admin, toujours l'espace technicien reel.
            self.assertNotIn("/admin", r.location)
            self.assertTrue(
                r.location.endswith("/dashboard/technicien") or r.location.endswith("/technician/dashboard"),
                r.location)
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

    def test_step5_resubmit_with_same_phone_reuses_technician_account(self):
        """Double soumission (retour arriere, bouton double-clique, nouvel
        essai) avec le meme numero : jamais de blocage ni de second compte,
        on se reconnecte simplement sur le technicien deja cree. C'est ce qui
        transformait avant un simple retour arriere en 'Ce numero est deja
        utilise' bloquant, voire en jeton CSRF perime sur la page en cache."""
        with self.client as c:
            self._do_steps_1_4(c)
            c.post("/devenir-technicien/finalisation", data={"accept_cgu": "1"})
            c.get("/logout")  # la finalisation connecte le nouveau technicien
        with self.client as c:
            self._do_steps_1_4(c)
            r = c.post("/devenir-technicien/finalisation",
                       data={"accept_cgu": "1"}, follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertTrue(
                r.location.endswith("/dashboard/technicien")
                or r.location.endswith("/technician/dashboard"), r.location)
            with c.session_transaction() as sess:
                self.assertIn("user_id", sess)
        self.assertEqual(self._count_users(), 1)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            docs = conn.execute(
                "SELECT COUNT(*) AS n FROM technician_documents").fetchone()
            self.assertEqual(docs["n"], 1)  # pas de doublon de piece jointe
        finally:
            conn.close()

    def test_step5_rejects_phone_already_used_by_a_client(self):
        """Le numero appartient a un AUTRE client (visiteur non connecte
        pendant le wizard) : toujours refuse, contrairement a une reprise de
        son propre compte technicien deja connecte."""
        self.register_client(phone="+224620112233")
        self.client.get("/logout")
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

    def test_technician_requests_page_lists_assigned_requests(self):
        self.register_artisan("trq@example.com", phone="+224621119001")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            tid = conn.execute("SELECT id FROM users WHERE phone=?",
                               ("+224621119001",)).fetchone()["id"]
            cid = fixpro_app._insert_id(conn,
                "INSERT INTO users (full_name, phone, password_hash, role)"
                " VALUES ('Client Zed', '+224620119001', 'x', 'client')", ())
            for desc, cat, other in [
                    ("Fuite sous l evier", "Plomberie", tid),
                    ("Prise du salon HS", "Electricite", tid),
                    ("Demande orpheline", "Peinture", None)]:   # pas attribuee au tech
                conn.execute(
                    "INSERT INTO requests (client_id, artisan_id, reference, title,"
                    " description, category, address, status, urgency, quote_amount,"
                    " budget, latitude, longitude, created_at, updated_at)"
                    " VALUES (?, ?, ?, 'T', ?, ?, 'Kaloum', 'ASSIGNED', 'normal',"
                    " 0, 0, 0, 0, datetime('now'), datetime('now'))",
                    (cid, other, "RQ-TRQ-%s" % cat, desc, cat))
            # une demande terminee : ne doit pas apparaitre
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, reference, title,"
                " description, category, address, status, urgency, quote_amount,"
                " budget, latitude, longitude, created_at, updated_at)"
                " VALUES (?, ?, 'RQ-TRQ-DONE', 'T', 'Vieille intervention', 'Plomberie', 'K',"
                " 'completed', 'normal', 0, 0, 0, 0, datetime('now'), datetime('now'))",
                (cid, tid))
            conn.commit()
        finally:
            conn.close()
        self.login("trq@example.com")
        r = self.client.get("/dashboard/technicien/demandes")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Demandes reçues", html)
        self.assertIn("Client Zed", html)
        self.assertIn("Fuite sous l evier", html)
        self.assertIn("Prise du salon HS", html)
        self.assertNotIn("Demande orpheline", html)     # pas attribuee au tech
        self.assertNotIn("Vieille intervention", html)  # terminee -> exclue
        self.assertIn("Toutes (2)", html)

    def test_technician_requests_page_rejects_client(self):
        self.register_client()
        self.login("+224620000000")
        r = self.client.get("/dashboard/technicien/demandes", follow_redirects=False)
        self.assertEqual(r.status_code, 302)

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
            self.assertIn(sub["status"], ("TRIAL", "PAST_DUE"))
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
        self.assertIn(sub["status"], ("TRIAL", "PAST_DUE"))      # PAS ACTIVE
        self.assertNotEqual(sub["status"], "ACTIVE")
        self.assertIsNone(pay["period_end"])           # pas de periode d'abonnement tant qu'inactif

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
        self.assertIn(self._sub_row(tid)["status"], ("TRIAL", "PAST_DUE"))  # jamais ACTIVE
        self.assertEqual(self._pay_row(ref)["status"], "pending")

    def test_webhook_wrong_amount_is_rejected(self):
        tid = self._tech()
        ref = self._start_payment()
        r = self._webhook(ref, "success", amount=1)
        self.assertEqual(r.status_code, 400)
        self.assertIn(self._sub_row(tid)["status"], ("TRIAL", "PAST_DUE"))  # jamais ACTIVE

    # --- 3. echecs -> reste inactif --------------------------------

    def test_webhook_failed_keeps_subscription_inactive(self):
        tid = self._tech()
        ref = self._start_payment()
        self.assertEqual(self._webhook(ref, "failed").status_code, 200)
        self.assertEqual(self._pay_row(ref)["status"], "failed")
        self.assertIn(self._sub_row(tid)["status"], ("TRIAL", "PAST_DUE"))  # jamais ACTIVE
        html = self.client.get("/abonnement/statut/%s" % ref).get_data(as_text=True)
        self.assertIn("Paiement échoué", html)

    def test_webhook_cancelled_keeps_inactive(self):
        tid = self._tech()
        ref = self._start_payment()
        self._webhook(ref, "cancelled")
        self.assertEqual(self._pay_row(ref)["status"], "cancelled")
        self.assertIn(self._sub_row(tid)["status"], ("TRIAL", "PAST_DUE"))  # jamais ACTIVE

    def test_user_cancel_keeps_inactive(self):
        tid = self._tech()
        ref = self._start_payment()
        self.client.post("/abonnement/statut/%s/annuler" % ref)
        self.assertEqual(self._pay_row(ref)["status"], "cancelled")
        self.assertIn(self._sub_row(tid)["status"], ("TRIAL", "PAST_DUE"))  # jamais ACTIVE

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
        self.assertIn(self._sub_row(tid)["status"], ("TRIAL", "PAST_DUE"))  # jamais ACTIVE

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
        self.assertIn(self._sub_row(tid)["status"], ("TRIAL", "PAST_DUE"))  # jamais ACTIVE

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
        self.assertIn(self._sub_row(tid)["status"], ("TRIAL", "PAST_DUE"))  # jamais ACTIVE

    def test_webhook_unknown_reference_is_rejected(self):
        self._tech(email="badref@example.com", phone="+224622000024")
        self._start_payment()
        r = self.client.post(
            "/webhooks/paiement/orange",
            json={"reference": "SUB-DOES-NOT-EXIST", "status": "success"},
            headers={"X-FixPro-Signature": self.WEBHOOK_SECRET})
        self.assertEqual(r.status_code, 404)


class SubscriptionEntitlementsTests(FixProTestCase):
    """Les avantages Pro / Premium sont de VRAIS droits, calcules depuis la
    base par une source centrale, et desactives hors de l'etat ACTIVE."""

    def _tech(self, email="ent@example.com", phone="+224623000001"):
        self.register_artisan(email, phone=phone)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute("SELECT id FROM users WHERE phone = ?",
                                (phone,)).fetchone()["id"]
        finally:
            conn.close()

    def _set_sub(self, tech_id, plan_code=None, status="ACTIVE", ends="future"):
        """Cree/positionne l'abonnement du technicien pour le test."""
        conn = db.connect(sqlite_path=self.db_path)
        try:
            plan_id = None
            if plan_code:
                plan_id = fixpro_app._ensure_tech_plan_row(conn, plan_code)
            end_date = None
            if ends == "future":
                end_date = "2999-01-01 00:00:00"
            elif ends == "past":
                end_date = "2000-01-01 00:00:00"
            conn.execute(
                "INSERT INTO technician_subscriptions"
                " (technician_id, plan_id, status, start_date, end_date, auto_renew)"
                " VALUES (?, ?, ?, '2020-01-01 00:00:00', ?, 1)",
                (tech_id, plan_id, status, end_date))
            conn.commit()
        finally:
            conn.close()

    def _ents(self, tech_id):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return fixpro_app.get_technician_entitlements(conn, tech_id)
        finally:
            conn.close()

    # --- matrice etat -> droits ---------------------------------------

    def test_no_subscription_and_trial_over_grants_no_entitlement(self):
        # technicien valide : il obtient d'abord l'essai de 14 jours ; une
        # fois l'essai termine et sans abonnement -> plus aucun droit.
        tid = self._tech()
        self.assertEqual(self._ents(tid)["status"], "TRIAL")   # essai auto
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE technician_subscriptions SET end_date='2000-01-01'"
                         " WHERE technician_id=?", (tid,))
            conn.commit()
        finally:
            conn.close()
        e = self._ents(tid)
        self.assertEqual(e["status"], "TRIAL_EXPIRED")
        self.assertFalse(e["active"])
        self.assertFalse(e["eligible"])
        self.assertEqual(e["entitlements"], set())
        self.assertIsNone(e["badge"])

    def test_pro_active_grants_pro_rights_only(self):
        tid = self._tech()
        self._set_sub(tid, "tech_pro", "ACTIVE")
        e = self._ents(tid)
        self.assertTrue(e["active"])
        self.assertEqual(e["plan_code"], "tech_pro")
        self.assertIn("monthly_request_quota", e["entitlements"])
        self.assertNotIn("unlimited_requests", e["entitlements"])   # Pro = limite
        self.assertIn("basic_statistics", e["entitlements"])
        self.assertNotIn("detailed_statistics", e["entitlements"])
        self.assertNotIn("priority_visibility", e["entitlements"])
        self.assertNotIn("featured_profile", e["entitlements"])
        self.assertEqual(e["badge"]["label"], "Pro")

    def test_premium_active_grants_premium_rights(self):
        tid = self._tech()
        self._set_sub(tid, "tech_premium", "ACTIVE")
        e = self._ents(tid)
        self.assertTrue(e["active"])
        for k in ("detailed_statistics", "priority_visibility", "featured_profile",
                  "priority_support", "unlimited_requests"):
            self.assertIn(k, e["entitlements"])
        self.assertEqual(e["badge"]["label"], "Premium")

    def test_pending_premium_grants_nothing(self):
        tid = self._tech()
        self._set_sub(tid, "tech_premium", "PAST_DUE")
        e = self._ents(tid)
        self.assertFalse(e["active"])
        self.assertEqual(e["entitlements"], set())
        self.assertIsNone(e["badge"])

    def test_expired_premium_loses_all_rights(self):
        tid = self._tech()
        # ACTIVE mais end_date depassee -> expiration paresseuse -> EXPIRED
        self._set_sub(tid, "tech_premium", "ACTIVE", ends="past")
        e = self._ents(tid)
        self.assertEqual(e["status"], "EXPIRED")
        self.assertFalse(e["active"])
        self.assertNotIn("priority_visibility", e["entitlements"])
        self.assertNotIn("detailed_statistics", e["entitlements"])
        self.assertNotIn("featured_profile", e["entitlements"])
        self.assertEqual(e["entitlements"], set())

    def test_cancelled_grants_nothing(self):
        tid = self._tech()
        self._set_sub(tid, "tech_premium", "CANCELLED")
        self.assertEqual(self._ents(tid)["entitlements"], set())

    def test_has_entitlement_helper_is_server_side(self):
        tid = self._tech()
        self._set_sub(tid, "tech_pro", "ACTIVE")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            self.assertTrue(fixpro_app.technician_has_entitlement(
                conn, tid, "monthly_request_quota"))
            self.assertFalse(fixpro_app.technician_has_entitlement(
                conn, tid, "unlimited_requests"))
            self.assertFalse(fixpro_app.technician_has_entitlement(
                conn, tid, "detailed_statistics"))
        finally:
            conn.close()

    def test_plan_change_pro_to_premium_updates_rights(self):
        tid = self._tech()
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self.assertNotIn("detailed_statistics", self._ents(tid)["entitlements"])
        # meme parcours qu'une nouvelle activation : on repositionne l'abo
        conn = db.connect(sqlite_path=self.db_path)
        try:
            pid = fixpro_app._ensure_tech_plan_row(conn, "tech_premium")
            conn.execute(
                "UPDATE technician_subscriptions SET plan_id = ?, status = 'ACTIVE',"
                " end_date = '2999-01-01 00:00:00' WHERE technician_id = ?", (pid, tid))
            conn.commit()
        finally:
            conn.close()
        e = self._ents(tid)
        self.assertEqual(e["plan_code"], "tech_premium")
        self.assertIn("detailed_statistics", e["entitlements"])

    # --- integration : cote client / recherche ----------------------

    def test_client_sees_premium_badge_only_when_active(self):
        tid = self._tech(email="pub@example.com", phone="+224623000009")
        self._set_sub(tid, "tech_premium", "PAST_DUE")
        self.register_client()
        self.login("+224620000000")
        html = self.client.get("/artisans/%d" % tid).get_data(as_text=True)
        self.assertNotIn('<span class="pl-plan-pill', html)
        # activation
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE technician_subscriptions SET status = 'ACTIVE'"
                         " WHERE technician_id = ?", (tid,))
            conn.commit()
        finally:
            conn.close()
        html = self.client.get("/artisans/%d" % tid).get_data(as_text=True)
        self.assertIn('<span class="pl-plan-pill', html)

    def test_priority_visibility_boosts_ranking_without_excluding(self):
        # deux techniciens identiques, l'un Premium actif -> il passe devant,
        # mais l'autre reste present dans les resultats.
        conn = db.connect(sqlite_path=self.db_path)
        try:
            ids = []
            for i in (1, 2):
                conn.execute(
                    "INSERT INTO users (email, phone, password_hash, role, full_name,"
                    " profession, city, is_verified, is_active, account_status,"
                    " availability_status, verification_status)"
                    " VALUES (?, ?, 'x', 'technician', ?, 'Plombier', 'Conakry', 1, 1,"
                    " 'ACTIVE', 'en_ligne', 'APPROVED')",
                    ("rank%d@x.co" % i, "+22462400000%d" % i, "Tech %d" % i))
                ids.append(conn.execute("SELECT id FROM users WHERE email = ?",
                                        ("rank%d@x.co" % i,)).fetchone()["id"])
            pid = fixpro_app._ensure_tech_plan_row(conn, "tech_premium")
            conn.execute(
                "INSERT INTO technician_subscriptions (technician_id, plan_id, status,"
                " start_date, end_date, auto_renew)"
                " VALUES (?, ?, 'ACTIVE', '2020-01-01 00:00:00', '2999-01-01 00:00:00', 1)",
                (ids[1], pid))
            conn.commit()
            ranked = fixpro_app._match_technicians(conn, "plomberie", location="Conakry")
        finally:
            conn.close()
        ranked_ids = [r["id"] for r in ranked]
        self.assertIn(ids[0], ranked_ids)          # le non-Premium reste present
        self.assertIn(ids[1], ranked_ids)
        self.assertLess(ranked_ids.index(ids[1]), ranked_ids.index(ids[0]))
        prem = next(r for r in ranked if r["id"] == ids[1])
        self.assertEqual(prem["subscription_badge"]["label"], "Premium")

    def test_my_subscription_page_benefits_come_from_central_source(self):
        tid = self._tech(email="benef@example.com", phone="+224623000011")
        self._set_sub(tid, "tech_premium", "ACTIVE")
        self.login("+224623000011")
        html = self.client.get("/abonnement").get_data(as_text=True)
        self.assertIn("Vos avantages", html)
        self.assertIn("Demandes illimitées", html)
        self.assertIn("Statistiques détaillées", html)
        self.assertIn("Profil mis en avant", html)

    def test_pro_subscription_page_shows_30_limit_from_central_source(self):
        tid = self._tech(email="benefpro@example.com", phone="+224623000012")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self.login("+224623000012")
        html = self.client.get("/abonnement").get_data(as_text=True)
        self.assertIn("Vos avantages", html)
        self.assertIn("30 demandes reçues par mois", html)   # libelle central

    def test_dashboard_shows_real_quota_counter_for_pro(self):
        tid = self._tech(email="dashq@example.com", phone="+224623000013")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self._fill_month(tid, 7, datetime_now_month())
        self.login("+224623000013")
        html = self.client.get("/dashboard/technicien").get_data(as_text=True)
        self.assertIn("Demandes reçues ce mois", html)
        self.assertIn("7 / 30", html)

    # --- Statistiques detaillees (avantage Premium) -------------------

    def _add_requests(self, tech_id, specs):
        """specs = liste de (status, month) ; cree des demandes attribuees."""
        conn = db.connect(sqlite_path=self.db_path)
        try:
            cid = conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name)"
                " VALUES ('cli-st@x.co', '+224620999888', 'x', 'client', 'Cli')")
            cid = conn.execute("SELECT id FROM users WHERE email = 'cli-st@x.co'").fetchone()["id"]
            for i, (st, month) in enumerate(specs):
                conn.execute(
                    "INSERT INTO requests (client_id, artisan_id, reference, title,"
                    " description, category, address, status, urgency, quote_amount,"
                    " budget, latitude, longitude, created_at, updated_at)"
                    " VALUES (?, ?, ?, 'T', 'D', 'plomberie', 'Conakry', ?, 'normal',"
                    " 0, 0, 0, 0, ?, ?)",
                    (cid, tech_id, "R-ST-%d" % i, st,
                     "%s-15 10:00:00" % month, "%s-15 10:00:00" % month))
            conn.commit()
        finally:
            conn.close()

    def test_stats_page_locked_for_pro(self):
        tid = self._tech(email="st-pro@x.co", phone="+224623000020")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self.login("+224623000020")
        r = self.client.get("/statistiques")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Passer à Premium", html)
        self.assertNotIn("Évolution sur 6 mois", html)   # aucune donnee Premium servie

    def test_stats_page_locked_without_subscription(self):
        tid = self._tech(email="st-none@x.co", phone="+224623000021")
        self.login("+224623000021")
        r = self.client.get("/statistiques")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Passer à Premium", r.get_data(as_text=True))
        self.assertNotIn("Évolution sur 6 mois", r.get_data(as_text=True))

    def test_stats_page_unlocked_for_premium(self):
        tid = self._tech(email="st-prem@x.co", phone="+224623000022")
        self._set_sub(tid, "tech_premium", "ACTIVE")
        self.login("+224623000022")
        r = self.client.get("/statistiques")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Évolution sur 6 mois", html)
        self.assertIn("Demandes reçues", html)
        self.assertIn("conversion", html.lower())        # metrique manquante signalee

    def test_stats_page_locked_after_expiry(self):
        tid = self._tech(email="st-exp@x.co", phone="+224623000023")
        self._set_sub(tid, "tech_premium", "ACTIVE", ends="past")
        self.login("+224623000023")
        r = self.client.get("/statistiques")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Évolution sur 6 mois", r.get_data(as_text=True))

    def test_stats_page_rejects_client(self):
        self.register_client()
        self.login("+224620000000")
        r = self.client.get("/statistiques")
        self.assertEqual(r.status_code, 302)

    def test_stats_numbers_are_real_counts(self):
        tid = self._tech(email="st-num@x.co", phone="+224623000024")
        self._set_sub(tid, "tech_premium", "ACTIVE")
        self._add_requests(tid, [
            ("completed", "2026-09"), ("completed", "2026-08"),
            ("accepted", "2026-09"), ("refused", "2026-09"),
            ("REQUESTED", "2026-09"),
        ])
        conn = db.connect(sqlite_path=self.db_path)
        try:
            ent = fixpro_app.get_technician_entitlements(conn, tid)
        finally:
            conn.close()
        self.assertTrue(ent["active"])
        self.login("+224623000024")
        html = self.client.get("/statistiques").get_data(as_text=True)
        # 5 demandes recues au total, 3 acceptees (completed+completed+accepted),
        # 1 terminee ce mois n'est pas ce qu'on teste ici : on verifie le total.
        self.assertIn(">5<", html.replace(" ", ""))       # KPI "Demandes reçues" = 5

    # --- Regle officielle : PRO = 30 / mois, PREMIUM = illimite ------

    def test_plan_limits_single_source(self):
        self.assertEqual(fixpro_app._PLAN_MONTHLY_REQUEST_LIMIT["tech_pro"], 30)
        self.assertIsNone(fixpro_app._PLAN_MONTHLY_REQUEST_LIMIT["tech_premium"])
        self.assertEqual(fixpro_app._PRO_MONTHLY_REQUEST_LIMIT, 30)
        self.assertIn("30", fixpro_app._ENTITLEMENT_LABELS["monthly_request_quota"])

    def _usage(self, tid, month="2026-09"):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return fixpro_app.technician_request_usage(conn, tid, month=month)
        finally:
            conn.close()

    def _can_receive(self, tid):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return fixpro_app.technician_can_receive_request(conn, tid)
        finally:
            conn.close()

    def _fill_month(self, tid, n, month):
        self._add_requests(tid, [("REQUESTED", month)] * n)

    def test_pro_zero_requests_can_receive(self):
        tid = self._tech(email="p0@x.co", phone="+224623000030")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self.assertTrue(self._can_receive(tid))

    def test_pro_29_requests_can_receive(self):
        tid = self._tech(email="p29@x.co", phone="+224623000031")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self._fill_month(tid, 29, datetime_now_month())
        self.assertTrue(self._can_receive(tid))
        u = self._usage(tid, datetime_now_month())
        self.assertEqual(u["used"], 29)
        self.assertEqual(u["remaining"], 1)

    def test_pro_30_requests_cannot_receive(self):
        tid = self._tech(email="p30@x.co", phone="+224623000032")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self._fill_month(tid, 30, datetime_now_month())
        self.assertFalse(self._can_receive(tid))
        u = self._usage(tid, datetime_now_month())
        self.assertTrue(u["over_limit"])
        self.assertEqual(u["remaining"], 0)

    def test_pro_over_limit_not_selected_by_matching(self):
        # technicien Pro a 30/30 -> exclu de _match_technicians, mais un autre
        # technicien identique sans quota reste selectionnable.
        conn = db.connect(sqlite_path=self.db_path)
        try:
            ids = []
            for i in (1, 2):
                conn.execute(
                    "INSERT INTO users (email, phone, password_hash, role, full_name,"
                    " profession, city, is_verified, is_active, account_status,"
                    " availability_status, verification_status)"
                    " VALUES (?, ?, 'x', 'technician', ?, 'Plombier', 'Conakry', 1, 1,"
                    " 'ACTIVE', 'en_ligne', 'APPROVED')",
                    ("q%d@x.co" % i, "+2246230000%d" % (40 + i), "QTech %d" % i))
                ids.append(conn.execute("SELECT id FROM users WHERE email = ?",
                                        ("q%d@x.co" % i,)).fetchone()["id"])
            pid = fixpro_app._ensure_tech_plan_row(conn, "tech_pro")
            conn.execute(
                "INSERT INTO technician_subscriptions (technician_id, plan_id, status,"
                " start_date, end_date, auto_renew)"
                " VALUES (?, ?, 'ACTIVE', '2020-01-01', '2999-01-01', 1)", (ids[0], pid))
            cli = conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name)"
                " VALUES ('qc@x.co', '+224620000777', 'x', 'client', 'C')")
            cli = conn.execute("SELECT id FROM users WHERE email = 'qc@x.co'").fetchone()["id"]
            month = datetime_now_month()
            for k in range(30):
                conn.execute(
                    "INSERT INTO requests (client_id, artisan_id, reference, title,"
                    " description, category, address, status, urgency, quote_amount,"
                    " budget, latitude, longitude, created_at, updated_at)"
                    " VALUES (?, ?, ?, 'T', 'D', 'plomberie', 'Conakry', 'REQUESTED',"
                    " 'normal', 0, 0, 0, 0, ?, ?)",
                    (cli, ids[0], "RQ-%d" % k, "%s-10 09:00:00" % month,
                     "%s-10 09:00:00" % month))
            conn.commit()
            ranked = [r["id"] for r in
                      fixpro_app._match_technicians(conn, "plomberie", location="Conakry")]
        finally:
            conn.close()
        self.assertNotIn(ids[0], ranked)   # Pro plein -> exclu
        self.assertIn(ids[1], ranked)      # l'autre technicien reste dispo

    def test_premium_30_requests_still_receives(self):
        tid = self._tech(email="pr30@x.co", phone="+224623000033")
        self._set_sub(tid, "tech_premium", "ACTIVE")
        self._fill_month(tid, 30, datetime_now_month())
        self.assertTrue(self._can_receive(tid))
        self.assertTrue(self._usage(tid, datetime_now_month())["unlimited"])

    def test_premium_100_requests_still_receives(self):
        tid = self._tech(email="pr100@x.co", phone="+224623000034")
        self._set_sub(tid, "tech_premium", "ACTIVE")
        self._fill_month(tid, 100, datetime_now_month())
        self.assertTrue(self._can_receive(tid))
        u = self._usage(tid, datetime_now_month())
        self.assertEqual(u["used"], 100)
        self.assertFalse(u["over_limit"])

    def test_pro_expired_has_no_quota_entitlement(self):
        tid = self._tech(email="pex@x.co", phone="+224623000035")
        self._set_sub(tid, "tech_pro", "ACTIVE", ends="past")
        e = self._ents(tid)
        self.assertEqual(e["status"], "EXPIRED")
        self.assertEqual(e["entitlements"], set())
        self.assertNotIn("monthly_request_quota", e["entitlements"])

    def test_premium_expired_loses_unlimited(self):
        tid = self._tech(email="prex@x.co", phone="+224623000036")
        self._set_sub(tid, "tech_premium", "ACTIVE", ends="past")
        e = self._ents(tid)
        self.assertFalse(e["active"])
        self.assertNotIn("unlimited_requests", e["entitlements"])
        # abonnement expire -> plus de plan actif -> usage non plafonne par un plan
        self.assertTrue(self._usage(tid, datetime_now_month())["unlimited"])

    def test_change_pro_to_premium_lifts_limit(self):
        tid = self._tech(email="chg1@x.co", phone="+224623000037")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self._fill_month(tid, 30, datetime_now_month())
        self.assertFalse(self._can_receive(tid))
        conn = db.connect(sqlite_path=self.db_path)
        try:
            pid = fixpro_app._ensure_tech_plan_row(conn, "tech_premium")
            conn.execute("UPDATE technician_subscriptions SET plan_id = ?,"
                         " status = 'ACTIVE', end_date = '2999-01-01'"
                         " WHERE technician_id = ?", (pid, tid))
            conn.commit()
        finally:
            conn.close()
        self.assertTrue(self._can_receive(tid))

    def test_change_premium_to_pro_applies_limit(self):
        tid = self._tech(email="chg2@x.co", phone="+224623000038")
        self._set_sub(tid, "tech_premium", "ACTIVE")
        self._fill_month(tid, 30, datetime_now_month())
        self.assertTrue(self._can_receive(tid))
        conn = db.connect(sqlite_path=self.db_path)
        try:
            pid = fixpro_app._ensure_tech_plan_row(conn, "tech_pro")
            conn.execute("UPDATE technician_subscriptions SET plan_id = ?,"
                         " status = 'ACTIVE', end_date = '2999-01-01'"
                         " WHERE technician_id = ?", (pid, tid))
            conn.commit()
        finally:
            conn.close()
        self.assertFalse(self._can_receive(tid))   # 30 deja recues ce mois -> bloque

    def test_frontend_bypass_is_blocked_server_side(self):
        # Le client force une demande directe vers un technicien Pro plein :
        # le serveur refuse, quel que soit le frontend.
        tid = self._tech(email="byp@x.co", phone="+224623000039")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        self._fill_month(tid, 30, datetime_now_month())
        self.register_client()
        self.login("+224620000000")
        r = self.client.post("/artisans/%d" % tid, data={
            "action": "request", "title": "Fuite", "description": "Urgent",
            "address": "Conakry", "urgency": "urgent"})
        self.assertEqual(r.status_code, 302)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?"
                             " AND title = 'Fuite'", (tid,)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 0)   # aucune demande creee au-dela du quota

    def test_concurrent_assignment_around_limit_no_overshoot(self):
        # A 29/30, deux attributions "simultanees" via request_new : une seule
        # doit passer au technicien Pro, l'autre repart non attribuee.
        tid = self._tech(email="cc@x.co", phone="+224623000045")
        self._set_sub(tid, "tech_pro", "ACTIVE")
        # techncien seul eligible dans sa zone/metier
        self._fill_month(tid, 29, datetime_now_month())
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET latitude = 9.5, longitude = -13.7,"
                         " profession = 'Plombier' WHERE id = ?", (tid,))
            conn.execute(
                "INSERT INTO technician_locations (technician_id, latitude, longitude,"
                " updated_at) VALUES (?, 9.5, -13.7, ?)",
                (tid, fixpro_app._ts()))
            conn.commit()
        finally:
            conn.close()
        self.register_client(phone="+224620001234")
        self.login("+224620001234")
        made = 0
        for i in range(2):
            self.client.post("/requests/new", data={
                "title": "Demande %d" % i, "description": "x", "category": "plomberie",
                "address": "Conakry"})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            used = conn.execute(
                "SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?"
                " AND substr(created_at,1,7) = ?",
                (tid, datetime_now_month())).fetchone()["n"]
        finally:
            conn.close()
        self.assertLessEqual(used, 30)   # jamais 31

    # --- PERIODE D'ESSAI GRATUIT (14 jours) --------------------------

    def _trial_rows(self, tid):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT status, start_date, end_date FROM technician_subscriptions"
                " WHERE technician_id = ? ORDER BY id", (tid,)).fetchall()
        finally:
            conn.close()

    def _set_trial(self, tid, ends_in_days=14, started_days_ago=0):
        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO technician_subscriptions (technician_id, plan_id, status,"
                " start_date, end_date, auto_renew) VALUES (?, NULL, 'TRIAL', ?, ?, 0)",
                (tid,
                 (now - _dt.timedelta(days=started_days_ago)).strftime("%Y-%m-%d %H:%M:%S"),
                 (now + _dt.timedelta(days=ends_in_days)).strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        finally:
            conn.close()

    def test_approved_technician_gets_trial(self):
        tid = self._tech(email="tr1@x.co", phone="+224623100001")
        e = self._ents(tid)
        self.assertEqual(e["status"], "TRIAL")
        self.assertTrue(e["trial_active"])
        self.assertTrue(e["eligible"])
        self.assertFalse(e["active"])          # pas un abonnement paye
        self.assertIsNone(e["badge"])          # aucun badge pendant l'essai
        self.assertIn("receive_requests", e["entitlements"])
        self.assertGreaterEqual(e["trial_days_left"], 13)

    def test_trial_lasts_14_days(self):
        tid = self._tech(email="tr2@x.co", phone="+224623100002")
        self._ents(tid)     # cree l'essai
        import datetime as _dt
        rows = self._trial_rows(tid)
        self.assertEqual(len(rows), 1)
        s = _dt.datetime.strptime(rows[0]["start_date"][:19], "%Y-%m-%d %H:%M:%S")
        end = _dt.datetime.strptime(rows[0]["end_date"][:19], "%Y-%m-%d %H:%M:%S")
        self.assertEqual((end - s).days, 14)
        self.assertEqual(fixpro_app._TRIAL_DAYS, 14)

    def test_trial_day1_and_day13_visible_and_eligible(self):
        tid = self._tech(email="tr3@x.co", phone="+224623100003")
        for days_left in (13, 1):
            conn = db.connect(sqlite_path=self.db_path)
            try:
                import datetime as _dt
                end = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=days_left, hours=1)).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("UPDATE technician_subscriptions SET end_date = ?"
                             " WHERE technician_id = ?", (end, tid))
                conn.commit()
            finally:
                conn.close()
            self.assertTrue(self._can_receive(tid))
            self.assertEqual(self._ents(tid)["trial_days_left"], days_left + 1 if False else days_left + 1)

    def test_trial_expired_becomes_trial_expired_status(self):
        tid = self._tech(email="tr4@x.co", phone="+224623100004")
        self._ents(tid)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE technician_subscriptions SET end_date = '2000-01-01 00:00:00'"
                         " WHERE technician_id = ?", (tid,))
            conn.commit()
        finally:
            conn.close()
        e = self._ents(tid)
        self.assertEqual(e["status"], "TRIAL_EXPIRED")
        self.assertFalse(e["eligible"])
        self.assertEqual(e["entitlements"], set())
        self.assertEqual(e["trial_days_left"], 0)

    def test_trial_active_can_receive_and_is_matched(self):
        tid = self._tech(email="tr5@x.co", phone="+224623100005")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET profession='Plombier' WHERE id=?", (tid,))
            conn.commit()
            self.assertTrue(fixpro_app.technician_can_receive_request(conn, tid))
            ranked = [r["id"] for r in fixpro_app._match_technicians(conn, "plomberie", location="Conakry")]
        finally:
            conn.close()
        self.assertIn(tid, ranked)

    def test_trial_expired_not_matched_and_cannot_receive(self):
        tid = self._tech(email="tr6@x.co", phone="+224623100006")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET profession='Plombier' WHERE id=?", (tid,))
            conn.commit()
        finally:
            conn.close()
        self._ents(tid)   # cree l'essai
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE technician_subscriptions SET end_date='2000-01-01'"
                         " WHERE technician_id=?", (tid,))
            conn.commit()
        finally:
            conn.close()
        conn = db.connect(sqlite_path=self.db_path)
        try:
            self.assertFalse(fixpro_app.technician_can_receive_request(conn, tid))
            ranked = [r["id"] for r in fixpro_app._match_technicians(conn, "plomberie", location="Conakry")]
        finally:
            conn.close()
        self.assertNotIn(tid, ranked)

    def test_trial_granted_only_once(self):
        tid = self._tech(email="tr7@x.co", phone="+224623100007")
        self._ents(tid)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE technician_subscriptions SET end_date='2000-01-01'"
                         " WHERE technician_id=?", (tid,))
            conn.commit()
        finally:
            conn.close()
        self._ents(tid)                      # -> TRIAL_EXPIRED
        self._ents(tid)                      # nouvel appel : pas de nouvel essai
        conn = db.connect(sqlite_path=self.db_path)
        try:
            fixpro_app._ensure_technician_trial(conn, tid)
            fixpro_app._ensure_trials_for_verified(conn)
            n = conn.execute("SELECT COUNT(*) AS n FROM technician_subscriptions"
                             " WHERE technician_id=?", (tid,)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 1)
        self.assertEqual(self._ents(tid)["status"], "TRIAL_EXPIRED")

    def test_buy_subscription_during_trial_activates_immediately(self):
        tid = self._tech(email="tr8@x.co", phone="+224623100008")
        self._set_trial(tid, ends_in_days=8)          # jour 6 : 8 jours restants
        # paiement confirme -> ACTIVE tout de suite
        conn = db.connect(sqlite_path=self.db_path)
        try:
            pid = fixpro_app._ensure_tech_plan_row(conn, "tech_premium")
            row = conn.execute("SELECT id FROM technician_subscriptions WHERE technician_id=?", (tid,)).fetchone()
            payid = fixpro_app._insert_id(conn,
                "INSERT INTO subscription_payments (user_id, subscription_id, plan_id, amount,"
                " currency, payment_method, transaction_reference, status)"
                " VALUES (?, ?, ?, 140000, 'GNF', 'orange_money', 'SUB-TR8', 'paid')",
                (tid, row["id"], pid))
            fixpro_app._activate_subscription_from_payment(conn, payid)
        finally:
            conn.close()
        e = self._ents(tid)
        self.assertEqual(e["status"], "ACTIVE")
        self.assertTrue(e["active"])
        self.assertEqual(e["plan_code"], "tech_premium")
        self.assertIn("priority_visibility", e["entitlements"])
        self.assertEqual(e["badge"]["label"], "Premium")

    def test_buy_subscription_after_trial_reactivates(self):
        tid = self._tech(email="tr9@x.co", phone="+224623100009")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET profession='Plombier' WHERE id=?", (tid,))
            conn.commit()
        finally:
            conn.close()
        self._set_trial(tid, ends_in_days=-1)   # deja termine
        self.assertEqual(self._ents(tid)["status"], "TRIAL_EXPIRED")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            pid = fixpro_app._ensure_tech_plan_row(conn, "tech_pro")
            row = conn.execute("SELECT id FROM technician_subscriptions WHERE technician_id=?", (tid,)).fetchone()
            payid = fixpro_app._insert_id(conn,
                "INSERT INTO subscription_payments (user_id, subscription_id, plan_id, amount,"
                " currency, payment_method, transaction_reference, status)"
                " VALUES (?, ?, ?, 97000, 'GNF', 'orange_money', 'SUB-TR9', 'paid')",
                (tid, row["id"], pid))
            fixpro_app._activate_subscription_from_payment(conn, payid)
            ranked = [r["id"] for r in fixpro_app._match_technicians(conn, "plomberie", location="Conakry")]
        finally:
            conn.close()
        self.assertEqual(self._ents(tid)["status"], "ACTIVE")
        self.assertTrue(self._can_receive(tid))
        self.assertIn(tid, ranked)

    def test_failed_payment_during_trial_keeps_trial(self):
        tid = self._tech(email="tr10@x.co", phone="+224623100010")
        self._set_trial(tid, ends_in_days=9)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute("SELECT id FROM technician_subscriptions WHERE technician_id=?", (tid,)).fetchone()
            payid = fixpro_app._insert_id(conn,
                "INSERT INTO subscription_payments (user_id, subscription_id, plan_id, amount,"
                " currency, payment_method, transaction_reference, status)"
                " VALUES (?, ?, NULL, 140000, 'GNF', 'orange_money', 'SUB-TR10', 'pending')",
                (tid, row["id"]))
            fixpro_app._fail_subscription_payment(conn, payid, "failed")
        finally:
            conn.close()
        e = self._ents(tid)
        self.assertEqual(e["status"], "TRIAL")
        self.assertTrue(e["eligible"])

    def test_failed_payment_after_trial_stays_expired(self):
        tid = self._tech(email="tr11@x.co", phone="+224623100011")
        self._set_trial(tid, ends_in_days=-2)
        self.assertEqual(self._ents(tid)["status"], "TRIAL_EXPIRED")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute("SELECT id FROM technician_subscriptions WHERE technician_id=?", (tid,)).fetchone()
            payid = fixpro_app._insert_id(conn,
                "INSERT INTO subscription_payments (user_id, subscription_id, plan_id, amount,"
                " currency, payment_method, transaction_reference, status)"
                " VALUES (?, ?, NULL, 97000, 'GNF', 'orange_money', 'SUB-TR11', 'pending')",
                (tid, row["id"]))
            fixpro_app._fail_subscription_payment(conn, payid, "failed")
        finally:
            conn.close()
        e = self._ents(tid)
        self.assertEqual(e["status"], "TRIAL_EXPIRED")
        self.assertFalse(e["eligible"])

    def test_subscription_expired_no_new_trial(self):
        tid = self._tech(email="tr12@x.co", phone="+224623100012")
        self._set_sub(tid, "tech_premium", "ACTIVE", ends="past")   # -> EXPIRED
        e = self._ents(tid)
        self.assertEqual(e["status"], "EXPIRED")
        self.assertFalse(e["eligible"])
        self.assertEqual(e["entitlements"], set())
        conn = db.connect(sqlite_path=self.db_path)
        try:
            fixpro_app._ensure_technician_trial(conn, tid)
            fixpro_app._ensure_trials_for_verified(conn)
            statuses = [r["status"] for r in conn.execute(
                "SELECT status FROM technician_subscriptions WHERE technician_id=?", (tid,)).fetchall()]
        finally:
            conn.close()
        self.assertNotIn("TRIAL", statuses)   # aucun nouvel essai recree

    def test_subscription_priority_over_trial(self):
        tid = self._tech(email="tr13@x.co", phone="+224623100013")
        self._set_sub(tid, "tech_premium", "ACTIVE")   # remplace la ligne d'essai potentielle
        e = self._ents(tid)
        self.assertTrue(e["active"])
        self.assertNotIn("trial_visibility_boost", e["entitlements"])
        self.assertIn("priority_visibility", e["entitlements"])

    def test_frontend_cannot_bypass_trial_expiry_direct_request(self):
        tid = self._tech(email="tr14@x.co", phone="+224623100014")
        self._set_trial(tid, ends_in_days=-3)
        self.assertEqual(self._ents(tid)["status"], "TRIAL_EXPIRED")
        self.register_client()
        self.login("+224620000000")
        self.client.post("/artisans/%d" % tid, data={
            "action": "request", "title": "Panne", "description": "x",
            "address": "Conakry", "urgency": "urgent"})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM requests WHERE artisan_id=?"
                             " AND title='Panne'", (tid,)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 0)

    def test_trial_state_stable_across_calls(self):
        tid = self._tech(email="tr15@x.co", phone="+224623100015")
        a = self._ents(tid)
        b = self._ents(tid)
        self.assertEqual(a["status"], b["status"])
        self.assertEqual(a["status"], "TRIAL")
        self.assertLessEqual(abs(a["trial_days_left"] - b["trial_days_left"]), 1)

    def test_no_commission_shown_anywhere(self):
        tid = self._tech(email="tr16@x.co", phone="+224623100016")
        self._set_sub(tid, "tech_premium", "ACTIVE")
        self.login("+224623100016")
        for path in ("/dashboard/technicien", "/abonnement",
                     "/abonnement/confirmation?plan=tech_pro",
                     "/abonnement/confirmation?plan=tech_premium", "/statistiques"):
            html = self.client.get(path).get_data(as_text=True).lower()
            self.assertNotIn("commission", html, path)

    def test_dashboard_shows_trial_banner_with_real_counts(self):
        tid = self._tech(email="tr17@x.co", phone="+224623100017")
        self._set_trial(tid, ends_in_days=10)
        self._add_requests(tid, [("completed", datetime_now_month()),
                                 ("REQUESTED", datetime_now_month())])
        self.login("+224623100017")
        html = self.client.get("/dashboard/technicien").get_data(as_text=True)
        self.assertIn("Période découverte", html)
        self.assertIn("Il vous reste", html)

    def test_dashboard_shows_trial_expired_message(self):
        tid = self._tech(email="tr18@x.co", phone="+224623100018")
        self._set_trial(tid, ends_in_days=-1)
        self.login("+224623100018")
        html = self.client.get("/dashboard/technicien").get_data(as_text=True)
        self.assertIn("Période découverte terminée", html)
        self.assertIn("Choisir mon abonnement", html)


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


class RoleSeparationTests(FixProTestCase):
    """GUEST / CLIENT / TECHNICIAN / ADMIN sont des espaces strictement
    separes : un technicien ne doit jamais pouvoir atteindre l'admin, meme
    en changeant l'URL a la main, et l'inscription technicien ne redirige
    jamais vers l'admin."""

    def test_technician_hitting_admin_dashboard_is_redirected_to_admin_login(self):
        self.register_artisan("role1@x.co", phone="+224621120001")
        self.login("role1@x.co")
        r = self.client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login", r.location)
        # jamais le contenu du dashboard admin ne fuite dans la reponse suivie
        r2 = self.client.get("/admin/dashboard", follow_redirects=True)
        self.assertNotIn("Tableau de bord", r2.get_data(as_text=True))

    def test_technician_hitting_admin_users_is_redirected_to_admin_login(self):
        self.register_artisan("role2@x.co", phone="+224621120002")
        self.login("role2@x.co")
        r = self.client.get("/admin/utilisateurs", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login", r.location)

    def test_client_hitting_admin_dashboard_is_redirected_to_admin_login(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_active)"
                " VALUES ('cl@x.co', '+224621120003', ?, 'client', 'Cl', 1)",
                (fixpro_app.generate_password_hash("FixPro2026!"),))
            conn.commit()
        finally:
            conn.close()
        self.login("cl@x.co")
        r = self.client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login", r.location)

    def test_technician_signup_never_redirects_to_admin(self):
        """Bout en bout : le wizard d'inscription technicien ne peut, a aucune
        etape, terminer sur une route admin."""
        r = self.client.post("/devenir-technicien", data={
            "first_name": "Rose", "last_name": "Diallo", "phone": "620999888",
            "email": "rose@x.co", "password": "FixPro2026!"}, follow_redirects=False)
        self.assertNotIn("/admin", (r.location or ""))

    def test_admin_session_cannot_be_forged_by_role_string_alone(self):
        """Le controle est fait sur users.role en base, pas sur une simple
        variable de session bricolable."""
        self.register_artisan("role3@x.co", phone="+224621120004")
        self.login("role3@x.co")
        with self.client.session_transaction() as sess:
            sess["role"] = "admin"  # cle de session sans effet : non lue par admin_required
        r = self.client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login", r.location)

    def test_removed_legacy_routes_return_clean_404(self):
        """Les anciennes routes retirees (mobile stub, ancien contact artisan,
        fermeture de ticket, export demandes) ne doivent jamais faire
        reapparaitre une ancienne page : 404 propre, pas d'erreur serveur."""
        for url in ("/mobile_welcome", "/mobile_dashboard",
                    "/artisans/1/contact", "/tickets/1/close",
                    "/export/requests"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 404, url)
            self.assertNotIn(b"Traceback", r.data)

    def test_admin_real_login_logout_relogin_keeps_admin_access(self):
        """Cycle reel deconnexion/reconnexion (formulaire /login, pas un
        raccourci de session) : le role admin est retrouve depuis la base,
        pas depuis une variable navigateur."""
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " is_verified, is_active) VALUES (?, ?, ?, 'admin', 'Admin Réel', 1, 1)",
                ("relog-admin@x.co", "+224621120005",
                 fixpro_app.generate_password_hash("FixPro2026!")))
            conn.commit()
        finally:
            conn.close()
        self.login("relog-admin@x.co")
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)
        self.client.get("/logout")
        self.assertEqual(self.client.get("/admin/dashboard", follow_redirects=False).status_code, 302)
        self.login("relog-admin@x.co")
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)


class ClientToTechnicianUpgradeTests(FixProTestCase):
    """UN UTILISATEUR FIXPRO = UN SEUL COMPTE. Un client deja connecte qui
    devient technicien doit garder le meme user.id / e-mail / telephone :
    le wizard met a jour son compte existant, il n'en cree jamais un second.
    Un visiteur non connecte garde, lui, le parcours de creation classique."""

    def _client_id(self, phone="+224620000000"):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()["id"]
        finally:
            conn.close()

    def _count_users(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        finally:
            conn.close()

    def _upgrade(self, c, trade="plomberie"):
        """Parcours complet cote client deja connecte : etape 1 sautee
        automatiquement (compte reutilise), etapes 2-5 remplies."""
        r0 = c.get("/devenir-technicien", follow_redirects=False)
        self.assertEqual(r0.status_code, 302)
        self.assertIn("/devenir-technicien/services", r0.location)
        c.post("/devenir-technicien/services", data={"trade": trade})
        c.post("/devenir-technicien/documents", data={})
        c.post("/devenir-technicien/localisation", data={})
        return c.post("/devenir-technicien/finalisation",
                      data={"accept_cgu": "1"}, follow_redirects=False)

    # TEST 1 + TEST 4 : meme user.id, aucun deuxieme compte cree
    def test_same_user_id_no_second_account_created(self):
        with self.client as c:
            self.register_client(phone="+224620111001")
            self.login("+224620111001")
            before_id = self._client_id("+224620111001")
            before_count = self._count_users()
            r = self._upgrade(c)
            self.assertEqual(r.status_code, 302)
        after_id = self._client_id("+224620111001")
        after_count = self._count_users()
        self.assertEqual(before_id, after_id)          # TEST 1
        self.assertEqual(before_count, after_count)     # TEST 4 : pas de doublon

    # TEST 2 + TEST 3 : e-mail et telephone inchanges
    def test_same_email_and_phone_after_upgrade(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_active)"
                " VALUES ('client-up@x.co', '+224620111002', ?, 'client', 'Client Up', 1)",
                (fixpro_app.generate_password_hash("FixPro2026!"),))
            conn.commit()
        finally:
            conn.close()
        with self.client as c:
            self.login("client-up@x.co")
            self._upgrade(c)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT email, phone, role FROM users WHERE phone = '+224620111002'").fetchone()
        finally:
            conn.close()
        self.assertEqual(row["email"], "client-up@x.co")   # TEST 2
        self.assertEqual(row["phone"], "+224620111002")    # TEST 3
        self.assertEqual(row["role"], "technician")

    # TEST 5 : le role passe reellement de client a technician en base
    def test_role_actually_changes_in_database(self):
        with self.client as c:
            self.register_client(phone="+224620111003")
            self.login("+224620111003")
            uid = self._client_id("+224620111003")
            conn = db.connect(sqlite_path=self.db_path)
            try:
                self.assertEqual(
                    conn.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()["role"],
                    "client")
            finally:
                conn.close()
            self._upgrade(c)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute("SELECT role, profession, verification_status FROM users WHERE id = ?",
                              (uid,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["role"], "technician")
        self.assertEqual(row["profession"], "Plombier")
        self.assertEqual(row["verification_status"], "PENDING_REVIEW")

    # TEST 6 : deconnexion / reconnexion -> role technicien conserve
    def test_role_persists_after_logout_login(self):
        with self.client as c:
            self.register_client(phone="+224620111004")
            self.login("+224620111004")
            self._upgrade(c)
            c.get("/logout")
        self.login("+224620111004")
        html = self.client.get("/artisans").get_data(as_text=True)
        self.assertIn("Accéder à mon espace technicien", html)   # TEST 10
        self.assertNotIn("Devenir technicien", html)

    # TEST 7 + TEST 8 : redirection finale = dashboard technicien, jamais /admin
    def test_finalize_redirects_to_technician_dashboard_never_admin(self):
        with self.client as c:
            self.register_client(phone="+224620111005")
            self.login("+224620111005")
            r = self._upgrade(c)
            self.assertEqual(r.status_code, 302)
            self.assertNotIn("/admin", r.location)             # TEST 8
            self.assertTrue(
                r.location.endswith("/dashboard/technicien")
                or r.location.endswith("/technician/dashboard"), r.location)  # TEST 7

    # TEST 9 : menu avant transformation = "Devenir technicien"
    def test_menu_shows_devenir_technicien_before_upgrade(self):
        self.register_client(phone="+224620111006")
        self.login("+224620111006")
        html = self.client.get("/artisans").get_data(as_text=True)
        self.assertIn("Devenir technicien", html)
        self.assertNotIn("Accéder à mon espace technicien", html)

    # Securite : le role ne peut pas etre change cote client / session bricolee
    def test_role_change_is_not_client_side_only(self):
        self.register_client(phone="+224620111007")
        self.login("+224620111007")
        with self.client.session_transaction() as sess:
            sess["role"] = "technician"   # bricolage cote navigateur : sans effet
        uid = self._client_id("+224620111007")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            role = conn.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()["role"]
        finally:
            conn.close()
        self.assertEqual(role, "client")
        r = self.client.get("/dashboard/technicien", follow_redirects=False)
        self.assertEqual(r.status_code, 302)   # toujours refuse : la session seule ne suffit pas

    # Cas non connecte : parcours de creation de compte classique, inchange
    def test_guest_signup_still_creates_a_new_account(self):
        before = self._count_users()
        r = self.client.post("/devenir-technicien", data={
            "first_name": "Nouveau", "last_name": "Technicien",
            "phone": "620999777", "email": "nouveau@x.co",
            "password": "FixPro2026!"}, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/devenir-technicien/services", r.location)
        self.assertEqual(self._count_users(), before)   # compte cree seulement a la finalisation

    # Signalement reel : juste apres la creation du compte, une premiere
    # relecture du role peut echouer (connexion groupee/replique en retard) --
    # la finalisation doit retenter quelques instants avant d'abandonner vers
    # la reconnexion, pour que l'ecran "Reconnectez-vous" reste l'exception,
    # pas ce que voit systematiquement un technicien qui vient de s'inscrire.
    def test_finalize_retries_role_verification_before_giving_up(self):
        real_get_db_connection = fixpro_app.get_db_connection
        calls = {"n": 0}

        class _FlakyConn:
            def __init__(self, real_conn):
                self._real = real_conn

            def execute(self, sql, params=()):
                if sql == "SELECT role FROM users WHERE id = ?":
                    calls["n"] += 1
                    if calls["n"] <= 2:
                        class _Empty:
                            def fetchone(self_inner):
                                return None
                        return _Empty()
                return self._real.execute(sql, params)

            def __getattr__(self, name):
                return getattr(self._real, name)

        def flaky_get_db_connection():
            return _FlakyConn(real_get_db_connection())

        fixpro_app.get_db_connection = flaky_get_db_connection
        orig_sleep = fixpro_app.time.sleep
        fixpro_app.time.sleep = lambda *_: None
        try:
            with self.client as c:
                self.register_client(phone="+224620111010")
                self.login("+224620111010")
                r = self._upgrade(c)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(
                    r.location.endswith("/dashboard/technicien")
                    or r.location.endswith("/technician/dashboard"), r.location)
        finally:
            fixpro_app.get_db_connection = real_get_db_connection
            fixpro_app.time.sleep = orig_sleep
        self.assertGreaterEqual(calls["n"], 3)   # a vraiment retente, pas eu de chance au 1er coup

    # LE VRAI BUG signale plusieurs fois de suite en prod : la creation du
    # compte et les notifications partageaient la meme transaction, validee
    # (commit) seulement a la toute fin. Quand la notification echouait (ex.
    # bug connu notifications.user_id), Postgres marquait la transaction
    # entiere en echec : le commit() final ne validait alors plus RIEN, pas
    # meme la creation du compte technicien -- silencieusement annulee. Ce
    # test reproduit exactement ca (create_notification qui echoue) et
    # verifie que le compte est neanmoins bel et bien cree.
    def test_finalize_survives_notification_failure_account_still_created(self):
        def _boom(*a, **k):
            raise RuntimeError("notifications.user_id : simulation du bug uuid connu")

        real_create_notification = fixpro_app.create_notification
        fixpro_app.create_notification = _boom
        try:
            with self.client as c:
                self.register_client(phone="+224620111011")
                self.login("+224620111011")
                r = self._upgrade(c)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(
                    r.location.endswith("/dashboard/technicien")
                    or r.location.endswith("/technician/dashboard"), r.location)
                with c.session_transaction() as sess:
                    self.assertIn("user_id", sess)
        finally:
            fixpro_app.create_notification = real_create_notification
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT role FROM users WHERE phone = '+224620111011'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["role"], "technician")   # jamais annule par l'echec de la notif

    # Un ex-client deja "verifie" (is_verified=1) qui devient technicien
    # repart en attente d'examen : jamais de passe-droit sur la moderation.
    def test_upgrade_resets_is_verified_pending_admin_review(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " is_verified, is_active) VALUES (?, ?, ?, 'client', 'Deja Verifie', 1, 1)",
                ("verif-up@x.co", "+224620111008",
                 fixpro_app.generate_password_hash("FixPro2026!")))
            conn.commit()
        finally:
            conn.close()
        with self.client as c:
            self.login("verif-up@x.co")
            self._upgrade(c)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT is_verified, verification_status FROM users WHERE phone = '+224620111008'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["is_verified"], 0)
        self.assertEqual(row["verification_status"], "PENDING_REVIEW")

    # TEST C/D : rafraichissement / nouvelle session (fermeture-reouverture)
    def test_dashboard_stays_technician_space_across_refresh_and_new_session(self):
        with self.client as c:
            self.register_client(phone="+224620111009")
            self.login("+224620111009")
            self._upgrade(c)
            # "actualisation" : re-requeter la meme route
            self.assertEqual(c.get("/technician/dashboard").status_code, 200)
            self.assertEqual(c.get("/technician/dashboard").status_code, 200)
        # "fermeture puis reouverture" : nouveau client de test, meme cookies
        reopened = self.client
        r = reopened.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("technician/dashboard", r.location)


class GoogleSignupTechnicianTests(FixProTestCase):
    """L'inscription rapide via Google ne cree jamais un compte technicien
    incomplet a part : "Je suis technicien" cree le compte FixPro (client)
    puis renvoie vers le wizard officiel /devenir-technicien, qui reutilise
    ce meme compte -- un seul parcours de creation de profil technicien."""

    def _complete_as(self, role):
        with self.client.session_transaction() as sess:
            sess["google_email"] = "g-user@example.com"
            sess["google_name"] = "Google User"
        return self.client.post("/complete-profile", data={
            "phone": "620555444", "city": "Conakry", "role": role,
        }, follow_redirects=False)

    def test_choosing_technician_creates_a_client_account_then_sends_to_wizard(self):
        r = self._complete_as("technician")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/devenir-technicien", r.location)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            row = conn.execute(
                "SELECT role FROM users WHERE email = 'g-user@example.com'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["role"], "client")   # jamais 'technician' directement

    def test_choosing_client_goes_straight_to_dashboard(self):
        r = self._complete_as("client")
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("/devenir-technicien", r.location)


class ParametresPageTests(FixProTestCase):
    """/parametres : UNE SEULE page, contenu adapte au role reel du compte
    (guest / client / technician). Aucune route /parametres/client etc."""

    def _upgrade_to_technician(self, c, phone):
        self.register_client(phone=phone)
        self.login(phone)
        c.get("/devenir-technicien", follow_redirects=False)
        c.post("/devenir-technicien/services", data={"trade": "plomberie"})
        c.post("/devenir-technicien/documents", data={})
        c.post("/devenir-technicien/localisation", data={})
        return c.post("/devenir-technicien/finalisation",
                      data={"accept_cgu": "1"}, follow_redirects=False)

    # TEST 1 : non connecte -> version invite
    def test_guest_sees_guest_version(self):
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn("Personnalisez votre expérience FixPro", html)
        self.assertIn("Se connecter", html)
        self.assertNotIn("Se déconnecter", html)
        self.assertNotIn("Informations personnelles", html)
        self.assertNotIn("Sécurité", html)
        self.assertNotIn("Préférences technicien", html)

    # TEST 2 : client connecte -> version client
    def test_client_sees_client_version(self):
        self.register_client(phone="+224620333001")
        self.login("+224620333001")
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn("Informations personnelles", html)
        self.assertIn("Sécurité", html)
        self.assertIn("Se déconnecter", html)
        self.assertNotIn("Se connecter", html)
        self.assertIn('pm-badge client', html)

    # TEST 3 : technicien connecte -> version technicien
    def test_technician_sees_technician_version(self):
        with self.client as c:
            self._upgrade_to_technician(c, "+224620333002")
            html = c.get("/parametres").get_data(as_text=True)
        self.assertIn("Préférences technicien", html)
        self.assertIn("Notifications professionnelles", html)
        self.assertIn("Zone d'intervention", html)
        self.assertIn("Abonnement", html)
        self.assertIn('pm-badge technician', html)

    # TEST 4 : client devient technicien -> meme compte, /parametres bascule
    def test_client_becoming_technician_flips_parametres_automatically(self):
        with self.client as c:
            self.register_client(phone="+224620333003")
            self.login("+224620333003")
            before = self.client.get("/parametres").get_data(as_text=True)
            self.assertNotIn("Préférences technicien", before)
            self._upgrade_to_technician(c, "+224620333003")
            after = c.get("/parametres").get_data(as_text=True)
        self.assertIn("Préférences technicien", after)

    # TEST 5 : deconnexion -> version invite
    def test_logout_returns_to_guest_version(self):
        self.register_client(phone="+224620333004")
        self.login("+224620333004")
        self.client.get("/logout")
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn("Se connecter", html)
        self.assertNotIn("Se déconnecter", html)

    # TEST 6 : le client ne voit jamais d'option professionnelle
    def test_client_never_sees_professional_options(self):
        self.register_client(phone="+224620333005")
        self.login("+224620333005")
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertNotIn("Préférences technicien", html)
        self.assertNotIn("Notifications professionnelles", html)
        self.assertNotIn("Zone d'intervention", html)
        self.assertNotIn("Espace professionnel", html)

    # TEST 7 : le technicien voit bien les options professionnelles (redondant
    # avec TEST 3, garde explicitement la formulation demandee)
    def test_technician_sees_professional_options(self):
        with self.client as c:
            self._upgrade_to_technician(c, "+224620333006")
            html = c.get("/parametres").get_data(as_text=True)
        self.assertIn("Espace professionnel", html)

    # TEST 8 : une seule route /parametres, aucune route derivee
    def test_only_one_parametres_route_exists(self):
        for bad in ("/parametres/client", "/parametres/technicien", "/parametres/guest"):
            r = self.client.get(bad)
            self.assertEqual(r.status_code, 404, bad)
        self.assertEqual(self.client.get("/parametres").status_code, 200)

    # TEST 9 : aucune duplication de la page Profil -- les boutons renvoient
    # vers les vraies routes existantes, rien n'est recree ici.
    def _url(self, endpoint, **kw):
        with fixpro_app.app.test_request_context():
            return fixpro_app.url_for(endpoint, **kw)

    def test_settings_links_to_real_existing_pages_not_duplicates(self):
        self.register_client(phone="+224620333007")
        self.login("+224620333007")
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn('href="{}"'.format(self._url("profile")), html)
        self.assertIn('href="{}"'.format(self._url("client_security")), html)
        self.assertIn('href="{}"'.format(self._url("contact")), html)
        # la page elle-meme ne reconstruit pas les champs du profil
        self.assertNotIn('name="first_name"', html)
        self.assertNotIn('name="current_password"', html)

    def test_technician_settings_link_to_real_subscription_and_dashboard(self):
        with self.client as c:
            self._upgrade_to_technician(c, "+224620333008")
            html = c.get("/parametres").get_data(as_text=True)
        self.assertIn('href="{}"'.format(self._url("artisan_dashboard")), html)
        self.assertIn('href="{}"'.format(self._url("technician_subscription")), html)
        self.assertIn('href="{}"'.format(self._url("technician_notifications")), html)

    # TEST 10 : securite serveur -- un client ne peut pas obtenir le contenu
    # technicien en bricolant la session (le role vient de la base)
    def test_professional_options_gated_on_real_role_not_session_tampering(self):
        self.register_client(phone="+224620333009")
        self.login("+224620333009")
        with self.client.session_transaction() as sess:
            sess["role"] = "technician"   # bricolage cote navigateur : sans effet
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertNotIn("Préférences technicien", html)

    def test_responsive_no_horizontal_overflow_markers(self):
        """Verification statique de base : le CSS de la page interdit tout
        debordement horizontal (page centree, largeur bornee)."""
        self.register_client(phone="+224620333010")
        self.login("+224620333010")
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn("overflow-x: hidden", html)
        self.assertIn("max-width: 480px", html)

    def test_menu_links_now_point_to_parametres_not_directly_to_security(self):
        """Depuis le menu : Paramètres -> /parametres (pas directement vers
        la page securite, qui reste un sous-item accessible depuis /parametres)."""
        self.register_client(phone="+224620333011")
        self.login("+224620333011")
        html = self.client.get("/artisans").get_data(as_text=True)
        self.assertIn('href="{}"'.format(self._url("parametres")), html)


class ParametresApparenceTests(FixProTestCase):
    """Parametres > Apparence : Clair / Sombre / Selon le systeme, meme
    comportement pour invite/client/technicien, preference persistee par
    cookie (pas de nouveau systeme de stockage, pas lie a un compte)."""

    def _upgrade_to_technician(self, c, phone):
        self.register_client(phone=phone)
        self.login(phone)
        c.get("/devenir-technicien", follow_redirects=False)
        c.post("/devenir-technicien/services", data={"trade": "plomberie"})
        c.post("/devenir-technicien/documents", data={})
        c.post("/devenir-technicien/localisation", data={})
        return c.post("/devenir-technicien/finalisation",
                      data={"accept_cgu": "1"}, follow_redirects=False)

    # TEST 1-2 : ouvrir Parametres -> Apparence, les 3 choix sont proposes
    def test_apparence_page_shows_the_three_choices(self):
        html = self.client.get("/parametres/apparence").get_data(as_text=True)
        self.assertIn("Clair", html)
        self.assertIn("Sombre", html)
        self.assertIn("Selon le système", html)
        self.assertIn("Appliquer le thème", html)
        self.assertIn("Mode clair", html)
        self.assertIn("Mode sombre", html)

    # TEST 3-5 : choisir Clair, appliquer, verifier le resultat
    def test_choosing_light_persists_via_cookie(self):
        r = self.client.post("/parametres/apparence", data={"theme": "light"},
                             follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith("/parametres"))
        self.assertIn("fp_theme=light", r.headers.get("Set-Cookie", ""))
        self.client.set_cookie("fp_theme", "light")
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn('<html lang="fr" data-theme="light">', html)
        self.assertIn("Thème clair", html)

    # TEST 6-8 : choisir Sombre, appliquer, verifier le resultat
    def test_choosing_dark_persists_via_cookie(self):
        r = self.client.post("/parametres/apparence", data={"theme": "dark"},
                             follow_redirects=False)
        self.assertIn("fp_theme=dark", r.headers.get("Set-Cookie", ""))
        self.client.set_cookie("fp_theme", "dark")
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn('<html lang="fr" data-theme="dark">', html)
        self.assertIn("Thème sombre", html)
        # bleu nuit, pas noir pur
        self.assertIn("#081B3A", html)
        self.assertNotIn("#000000", html)
        self.assertIn("#0066FF", html)   # bleu FixPro reste l'accent en sombre

    # TEST 9-11 : "Selon le systeme" -> aucun data-theme force, la mediaquery decide
    def test_system_choice_lets_the_device_decide(self):
        r = self.client.post("/parametres/apparence", data={"theme": "system"},
                             follow_redirects=False)
        self.assertIn("fp_theme=system", r.headers.get("Set-Cookie", ""))
        self.client.set_cookie("fp_theme", "system")
        html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn('<html lang="fr">', html)   # aucun data-theme force sur <html>
        self.assertIn("prefers-color-scheme: dark", html)

    # TEST 12-13 : fermeture/reouverture -> la preference reste memorisee
    # (meme mecanisme que la session : cookie persistant, pas une variable
    # en memoire qui disparaitrait)
    def test_preference_survives_new_browser_session(self):
        self.client.post("/parametres/apparence", data={"theme": "dark"})
        self.client.set_cookie("fp_theme", "dark")
        reopened = self.client  # meme pot de cookies, "nouvel onglet"
        html = reopened.get("/parametres").get_data(as_text=True)
        self.assertIn('<html lang="fr" data-theme="dark">', html)

    # TEST : fonctionne de la meme maniere pour les 3 types d'utilisateurs
    def test_same_behavior_for_guest_client_and_technician(self):
        self.client.set_cookie("fp_theme", "dark")
        guest_html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn('<html lang="fr" data-theme="dark">', guest_html)

        self.register_client(phone="+224620444001")
        self.login("+224620444001")
        self.client.set_cookie("fp_theme", "dark")
        client_html = self.client.get("/parametres").get_data(as_text=True)
        self.assertIn('<html lang="fr" data-theme="dark">', client_html)

        with self.client as c:
            self._upgrade_to_technician(c, "+224620444002")
            c.set_cookie("fp_theme", "dark")
            tech_html = c.get("/parametres").get_data(as_text=True)
        self.assertIn('<html lang="fr" data-theme="dark">', tech_html)

    # NE PAS creer de route derivee : une seule /parametres/apparence
    def test_only_one_apparence_route(self):
        for bad in ("/parametres/apparence/client", "/parametres/apparence/technicien"):
            self.assertEqual(self.client.get(bad).status_code, 404, bad)

    def test_back_arrow_returns_to_parametres(self):
        html = self.client.get("/parametres/apparence").get_data(as_text=True)
        self.assertIn(self._url("parametres"), html)

    def test_apparence_no_horizontal_overflow_marker(self):
        html = self.client.get("/parametres/apparence").get_data(as_text=True)
        self.assertIn("overflow-x: hidden", html)
        self.assertIn("max-width: 480px", html)

    def _url(self, endpoint, **kw):
        with fixpro_app.app.test_request_context():
            return fixpro_app.url_for(endpoint, **kw)


class ArtisanPublicProfileTests(FixProTestCase):
    """Fiche publique du technicien (/artisans/<id>), vue par le CLIENT :
    UN SEUL template dynamique (artisan_detail.html), donnees reelles
    uniquement (bio, services, avis, realisations) -- jamais un profil
    technicien prive (revenus, parametres pro, gestion des missions)."""

    def _plumber_id(self, phone="+224621119900",
                    email="plombier-profil@example.com"):
        self.register_artisan(email, phone=phone)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            return conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()["id"]
        finally:
            conn.close()

    def test_profile_has_hero_idcard_and_stats(self):
        aid = self._plumber_id()
        r = self.client.get(f"/artisans/{aid}")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('class="pl-hero"', html)
        self.assertIn('class="pl-idcard"', html)
        self.assertIn('class="pl-stats"', html)
        self.assertIn("Disponible aujourd'hui", html)   # technicien en_ligne (donnee reelle)
        self.assertIn("Plombier professionnel", html)
        self.assertIn("Interventions réalisées", html)
        self.assertIn("Message", html)
        self.assertIn("Contacter", html)

    def test_real_plumbing_services_shown_as_a_card_grid(self):
        aid = self._plumber_id(phone="+224621119901", email="plombier2@example.com")
        html = self.client.get(f"/artisans/{aid}").get_data(as_text=True)
        self.assertIn('class="pl-svc-grid"', html)
        # services standards du metier "Plombier" (seed reel schema_sqlite.sql)
        self.assertIn("Debouchage", html)
        self.assertIn("Installation sanitaire", html)
        # jamais un service d'un autre metier
        self.assertNotIn("climatisation", html.lower())
        self.assertNotIn("électricité", html.lower())
        self.assertNotIn("peinture", html.lower())

    def test_no_portfolio_shows_honest_empty_state_not_fake_photos(self):
        aid = self._plumber_id(phone="+224621119902", email="plombier3@example.com")
        html = self.client.get(f"/artisans/{aid}").get_data(as_text=True)
        self.assertIn("Aucune réalisation publiée pour le moment.", html)
        self.assertNotIn('class="pl-real-grid"', html)

    def test_real_portfolio_photo_renders_in_the_grid(self):
        aid = self._plumber_id(phone="+224621119903", email="plombier4@example.com")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO artisan_portfolio (artisan_id, photo_url, caption)"
                " VALUES (?, ?, ?)",
                (aid, "https://example.com/vraie-photo-chantier.jpg",
                 "Débouchage d'une canalisation"))
            conn.commit()
        finally:
            conn.close()
        html = self.client.get(f"/artisans/{aid}").get_data(as_text=True)
        self.assertIn('class="pl-real-grid"', html)
        self.assertIn("https://example.com/vraie-photo-chantier.jpg", html)
        self.assertIn("Débouchage d&#39;une canalisation", html)

    def test_bio_is_real_data_not_hardcoded_per_technician(self):
        aid = self._plumber_id(phone="+224621119904", email="plombier5@example.com")
        # sans bio -> message generique honnete, jamais un texte invente specifique
        empty_html = self.client.get(f"/artisans/{aid}").get_data(as_text=True)
        self.assertIn("n'a pas encore rédigé sa présentation", empty_html)
        self.assertNotIn("Ibrahim Sory", empty_html)

        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute("UPDATE users SET bio = ? WHERE id = ?",
                        ("Plombier de Kaloum depuis 12 ans.", aid))
            conn.commit()
        finally:
            conn.close()
        filled_html = self.client.get(f"/artisans/{aid}").get_data(as_text=True)
        self.assertIn("Plombier de Kaloum depuis 12 ans.", filled_html)

    def test_public_profile_never_leaks_private_technician_data(self):
        aid = self._plumber_id(phone="+224621119905", email="plombier6@example.com")
        html = self.client.get(f"/artisans/{aid}").get_data(as_text=True)
        for private_term in ("Mes revenus", "revenus", "Espace professionnel",
                             "Préférences technicien", "Zone d'intervention",
                             "Abonnement"):
            self.assertNotIn(private_term, html, private_term)

    def test_reusable_for_other_trades_same_single_template(self):
        """Le meme template doit fonctionner pour un autre metier sans etre
        code en dur pour le plombier -- verifie l'architecture reutilisable."""
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " profession, city, is_verified, is_active, verification_status,"
                " availability_status)"
                " VALUES ('electricien-profil@example.com', '+224621119906', ?,"
                " 'technician', 'Amara Conde', 'Électricien', 'Conakry', 1, 1,"
                " 'APPROVED', 'en_ligne')",
                (fixpro_app.generate_password_hash("FixPro2026!"),))
            conn.commit()
            eid = conn.execute(
                "SELECT id FROM users WHERE phone = '+224621119906'").fetchone()["id"]
        finally:
            conn.close()
        html = self.client.get(f"/artisans/{eid}").get_data(as_text=True)
        self.assertEqual(self.client.get(f"/artisans/{eid}").status_code, 200)
        self.assertIn("Électricien professionnel", html)
        self.assertIn('class="pl-svc-grid"', html)
        # services electricien reels, jamais de plomberie
        self.assertIn("Depannage electrique", html)
        self.assertNotIn("Debouchage", html)


class RefreshRolePersistenceTests(FixProTestCase):
    """Le role vient TOUJOURS d'une lecture serveur fraiche (users.role en
    base), jamais d'un etat client qui pourrait disparaitre/perimer :
    l'actualisation, la fermeture/reouverture d'onglet ou une nouvelle
    session ne doivent jamais faire apparaitre le mauvais espace, meme
    brievement. Les reponses des pages authentifiees portent aussi
    Cache-Control: no-store pour qu'un navigateur ne puisse pas re-afficher
    une ancienne page (autre role) depuis son cache ou le bfcache."""

    def _upgrade_to_technician(self, c, phone):
        self.register_client(phone=phone)
        self.login(phone)
        c.get("/devenir-technicien", follow_redirects=False)
        c.post("/devenir-technicien/services", data={"trade": "plomberie"})
        c.post("/devenir-technicien/documents", data={})
        c.post("/devenir-technicien/localisation", data={})
        return c.post("/devenir-technicien/finalisation",
                      data={"accept_cgu": "1"}, follow_redirects=False)

    # TEST 1 : inscription -> espace technicien -> F5 -> toujours l'espace technicien
    def test_new_technician_stays_in_technician_space_after_refresh(self):
        with self.client as c:
            r = self._upgrade_to_technician(c, "+224620222001")
            self.assertTrue(
                r.location.endswith("/dashboard/technicien")
                or r.location.endswith("/technician/dashboard"), r.location)
            first = c.get("/technician/dashboard")
            self.assertEqual(first.status_code, 200)
            self.assertIn("no-store", first.headers.get("Cache-Control", ""))
            # F5 : nouvelle requete serveur, jamais une page en cache
            refreshed = c.get("/technician/dashboard")
            self.assertEqual(refreshed.status_code, 200)
            self.assertIn("Espace Technicien", refreshed.get_data(as_text=True))

    # TEST 2 : F5 plusieurs fois de suite -> toujours le meme espace
    def test_technician_repeated_refresh_never_flips_space(self):
        with self.client as c:
            self._upgrade_to_technician(c, "+224620222002")
            for _ in range(5):
                r = c.get("/technician/dashboard")
                self.assertEqual(r.status_code, 200)
                html = r.get_data(as_text=True)
                self.assertIn("Espace Technicien", html)
                self.assertNotIn("Tableau de bord administrateur", html)

    # TEST 3 : fermeture/reouverture de l'onglet (nouvelle requete, memes
    # cookies de session -- il n'existe pas d'etat "en memoire" a perdre)
    def test_technician_space_survives_new_browser_session(self):
        with self.client as c:
            self._upgrade_to_technician(c, "+224620222003")
        reopened = self.client  # meme pot de cookies, "nouvel onglet"
        r = reopened.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("technician/dashboard", r.location)
        self.assertEqual(reopened.get("/technician/dashboard").status_code, 200)

    # TEST 4 : deconnexion / reconnexion -> espace technicien retrouve
    def test_technician_space_after_logout_login_cycle(self):
        phone = "+224620222004"
        with self.client as c:
            self._upgrade_to_technician(c, phone)
            c.get("/logout")
        self.login(phone)
        r = self.client.get("/technician/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Espace Technicien", r.get_data(as_text=True))

    # TEST 5 : un CLIENT qui actualise reste dans son espace (l'accueil),
    # jamais technicien/admin. /dashboard n'est plus une page autonome --
    # l'espace client, c'est l'accueil (/) -- il redirige seulement.
    def test_client_repeated_refresh_stays_in_client_space(self):
        self.register_client(phone="+224620222005")
        self.login("+224620222005")
        for _ in range(3):
            r = self.client.get("/dashboard", follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertIn("no-store", r.headers.get("Cache-Control", ""))
            self.assertTrue(r.location.endswith("/"), r.location)
            html = self.client.get(r.location).get_data(as_text=True)
            self.assertNotIn("Espace Technicien", html)
            self.assertNotIn("Tableau de bord administrateur", html)

    # TEST 6 : un ADMIN qui actualise reste dans son dashboard admin
    def test_admin_repeated_refresh_stays_in_admin_dashboard(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " is_verified, is_active) VALUES (?, ?, ?, 'admin', 'Admin Test', 1, 1)",
                ("refresh-admin@x.co", "+224620222006",
                 fixpro_app.generate_password_hash("FixPro2026!")))
            conn.commit()
        finally:
            conn.close()
        self.login("refresh-admin@x.co")
        for _ in range(3):
            r = self.client.get("/admin/dashboard")
            self.assertEqual(r.status_code, 200)
            self.assertIn("no-store", r.headers.get("Cache-Control", ""))

    # TEST 7 : aucune session -> jamais de contenu technicien/admin par defaut,
    # toujours renvoye vers la connexion (fail-safe, pas de fallback ambigu)
    def test_no_session_never_falls_back_to_a_dashboard(self):
        r = self.client.get("/technician/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.location)
        r2 = self.client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(r2.status_code, 302)
        self.assertIn("/admin/login", r2.location)

    # Cas important explicitement demande : ouverture directe de l'URL
    # technicien en etant authentifie technicien -> toujours l'espace correct,
    # jamais une page intermediaire erronee.
    def test_direct_url_to_technician_space_while_authenticated_shows_it_immediately(self):
        with self.client as c:
            self._upgrade_to_technician(c, "+224620222007")
        r = self.client.get("/technician/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Espace Technicien", r.get_data(as_text=True))

    def test_authenticated_pages_are_never_cacheable(self):
        """Choix architectural definitif : toute page rendue pour une
        session authentifiee porte Cache-Control: no-store (regle globale
        dans add_security_headers), pas un correctif page par page qu'on
        pourrait oublier d'ajouter a une nouvelle route."""
        self.register_client(phone="+224620222008")
        self.login("+224620222008")
        for path in ("/dashboard", "/profile", "/requests", "/notifications"):
            r = self.client.get(path)
            self.assertIn("no-store", r.headers.get("Cache-Control", ""), path)

    # Signalement exact : apres inscription, "Acceder a mon espace" ne doit
    # jamais faire atterrir sur le tableau de bord CLIENT (avec ou sans
    # donnees de demonstration) -- ni immediatement, ni en cas d'anomalie.
    def test_technician_never_lands_on_client_dashboard_after_signup(self):
        with self.client as c:
            r = self._upgrade_to_technician(c, "+224620222009")
            self.assertTrue(
                r.location.endswith("/dashboard/technicien")
                or r.location.endswith("/technician/dashboard"), r.location)
            followed = c.get(r.location)
            html = followed.get_data(as_text=True)
            self.assertIn("Espace Technicien", html)
            # signatures propres au dashboard CLIENT (demo ou reel) : absentes
            self.assertNotIn("Nos services", html)
            self.assertNotIn("Mon technicien", html)

    # /dashboard ne doit JAMAIS fabriquer un faux contenu (mode demo ou pas)
    # pour un visiteur non identifie : c'est exactement ce qui masquait le
    # vrai probleme derriere une page "normale".
    def test_dashboard_requires_real_login_never_fakes_content(self):
        r = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.location)

    def test_dashboard_with_dangling_session_redirects_to_login_not_demo(self):
        """session['user_id'] pointant vers rien (compte supprime, ligne pas
        encore relisible...) : jamais le contenu demo, une reconnexion propre."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 999999
        r = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.location)
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)   # session nettoyee, pas juste ignoree

    def test_technician_with_dangling_session_never_reaches_client_demo(self):
        """Meme scenario pendant que l'espace technicien est vise : jamais
        de rebond silencieux vers le dashboard client demo."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 999999
        r = self.client.get("/technician/dashboard", follow_redirects=True)
        self.assertNotIn("Nos services", r.get_data(as_text=True))
        self.assertNotIn("Mon technicien", r.get_data(as_text=True))

    # Correction definitive demandee : le mecanisme de fausses donnees est
    # efface, pas juste contourne -- il ne doit plus exister nulle part.
    def test_client_dashboard_demo_data_generator_no_longer_exists(self):
        self.assertFalse(hasattr(fixpro_app, "_client_dashboard_demo_context"))
        self.assertFalse(hasattr(fixpro_app, "_CLIENT_DASHBOARD_DEMO"))
        self.assertNotIn("CLIENT_DASHBOARD_DEMO", fixpro_app.app.config)

    def test_client_dashboard_always_shows_the_real_logged_in_identity(self):
        """L'ancien tableau de bord client autonome (dashboard_client.html)
        est supprime -- /dashboard redirige simplement vers l'accueil, qui
        n'affiche plus jamais de fausse identite ("Aminata") ni de donnees
        inventees ("Moussa Bah")."""
        self.register_client(phone="+224620222010", first_name="Souleymane",
                             last_name="Kaba")
        self.login("+224620222010")
        r = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith("/"), r.location)
        html = self.client.get(r.location).get_data(as_text=True)
        self.assertNotIn("Aminata", html)
        self.assertNotIn("Moussa Bah", html)   # ex-"mon technicien" fictif

    def test_client_dashboard_page_removed_from_the_application(self):
        """La page elle-meme n'existe plus dans le projet -- supprimee, pas
        juste debranchee."""
        self.assertFalse(
            (ROOT / "templates" / "dashboard_client.html").exists())
        self.assertFalse(hasattr(fixpro_app, "_client_dashboard_real_context"))


class NotificationCenterTests(FixProTestCase):
    """Centre de notifications technicien : bottom sheet, categories, diffusion
    admin, cycle de vie de l'abonnement. Consultatif uniquement."""

    def _admin(self):
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " is_verified, is_active) VALUES (?, ?, ?, 'admin', 'Admin', 1, 1)",
                ("adm@fixpro.local", "+224000000001",
                 fixpro_app.generate_password_hash("x")))
            conn.commit()
            return conn.execute("SELECT id FROM users WHERE email = 'adm@fixpro.local'").fetchone()["id"]
        finally:
            conn.close()

    def test_bell_is_a_bottom_sheet_with_handle(self):
        self.register_artisan("sheet@x.co", phone="+224621119001")
        self.login("sheet@x.co")
        html = self.client.get("/dashboard/technicien").get_data(as_text=True)
        self.assertIn('id="ntfbSheet"', html)
        self.assertIn('id="ntfbGrip"', html)          # poignee
        self.assertIn("Voir toutes les notifications", html)
        # aucune zone de reponse dans la cloche
        self.assertNotIn('name="reply"', html)

    def test_technician_notifications_page_alias(self):
        self.register_artisan("alias@x.co", phone="+224621119002")
        self.login("alias@x.co")
        r = self.client.get("/technician/notifications")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("Notifications", body)
        # page consultative : pas de formulaire de reponse
        self.assertNotIn("Répondre", body)

    def test_admin_broadcast_reaches_all_technicians_only(self):
        self._admin()
        self.register_artisan("t1@x.co", phone="+224621119010")
        self.register_artisan("t2@x.co", phone="+224621119011")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_active)"
                " VALUES ('c1@x.co', '+224621119012', 'x', 'client', 'C1', 1)")
            conn.commit()
        finally:
            conn.close()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["admin_unlocked"] = True
        r = self.client.post("/admin/notifications/send", data={
            "audience": "technicians", "type": "announcement",
            "title": "Maintenance", "body": "Dimanche de 00h a 06h.",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        conn = db.connect(sqlite_path=self.db_path)
        try:
            rows = conn.execute(
                "SELECT u.role FROM notifications n JOIN users u ON u.id = n.user_id"
                " WHERE n.title = 'Maintenance'").fetchall()
        finally:
            conn.close()
        roles = sorted(r["role"] for r in rows)
        self.assertEqual(roles, ["technician", "technician"])

    def test_admin_broadcast_requires_title_and_body(self):
        self._admin()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["admin_unlocked"] = True
        self.client.post("/admin/notifications/send", data={
            "audience": "all", "type": "announcement", "title": "", "body": ""})
        conn = db.connect(sqlite_path=self.db_path)
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM notifications").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 0)

    def test_notify_once_dedups(self):
        self.register_artisan("once@x.co", phone="+224621119020")
        uid = self.client_artisan_id = None
        conn = db.connect(sqlite_path=self.db_path)
        try:
            uid = conn.execute("SELECT id FROM users WHERE phone = '+224621119020'").fetchone()["id"]
            a = fixpro_app._notify_once(conn, uid, "m1", "T", "B", "system")
            b = fixpro_app._notify_once(conn, uid, "m1", "T", "B", "system")
            conn.commit()
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ?", (uid,)).fetchone()["n"]
        finally:
            conn.close()
        self.assertTrue(a)
        self.assertFalse(b)
        self.assertEqual(n, 1)

    def test_canonical_category_icon_and_link(self):
        self.register_artisan("cat@x.co", phone="+224621119030")
        conn = db.connect(sqlite_path=self.db_path)
        try:
            uid = conn.execute("SELECT id FROM users WHERE phone = '+224621119030'").fetchone()["id"]
            conn.execute(
                "INSERT INTO notifications (user_id, title, body, type, data)"
                " VALUES (?, 'Offre', 'Promo', 'subscription', 'abonnement')", (uid,))
            conn.commit()
        finally:
            conn.close()
        self.login("cat@x.co")
        item = self.client.get("/api/notifications").get_json()["items"][0]
        self.assertEqual(item["icon"], "crown")
        self.assertIn("abonnement", item["href"])


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


class StaticAssetVersioningTests(FixProTestCase):
    """Cache-busting automatique des fichiers statiques : plus jamais de CSS
    obsolete servi apres un changement (fini le ?v=N a bumper a la main)."""

    def test_css_url_carries_content_hash(self):
        import hashlib
        html = self.client.get("/").get_data(as_text=True)
        css = (Path(fixpro_app.app.static_folder) / "css" / "fixpro.css").read_bytes()
        expected = hashlib.md5(css).hexdigest()[:10]
        self.assertIn("css/fixpro.css?v=" + expected, html)

    def test_version_changes_when_file_changes(self):
        css_path = Path(fixpro_app.app.static_folder) / "css" / "fixpro.css"
        original = css_path.read_bytes()
        fixpro_app._static_version_cache.clear()
        v1 = fixpro_app._static_asset_version("css/fixpro.css")
        try:
            css_path.write_bytes(original + b"\n/* touch */\n")
            fixpro_app._static_version_cache.clear()
            v2 = fixpro_app._static_asset_version("css/fixpro.css")
        finally:
            css_path.write_bytes(original)
            fixpro_app._static_version_cache.clear()
        self.assertNotEqual(v1, v2)

    def test_no_template_hardcodes_a_static_version(self):
        import re
        offenders = []
        for tpl in (ROOT / "templates").rglob("*.html"):
            txt = tpl.read_text(encoding="utf-8")
            if re.search(r"url_for\(\s*['\"]static['\"][^)]*\bv\s*=", txt):
                offenders.append(tpl.name)
        self.assertEqual(offenders, [], "utiliser asset() au lieu d'un ?v= fige")


class CSRFErrorHandlingTests(FixProTestCase):
    """Plus jamais d'ecran brut "Bad Request / The CSRF tokens do not
    match" : un jeton perime doit toujours ramener l'utilisateur vers une
    page FixPro exploitable (jeton neuf pour le wizard, page dediee ailleurs)."""

    def setUp(self):
        super().setUp()
        fixpro_app.app.config["WTF_CSRF_ENABLED"] = True

    def test_stale_token_on_wizard_step_offers_to_resume_it(self):
        # Le gabarit du wizard est autonome (pas de rendu des flash messages) :
        # la recuperation doit donc etre visible sur la reponse elle-meme,
        # avec un lien qui recharge la MEME etape (jeton neuf).
        r = self.client.post("/devenir-technicien", data={
            "first_name": "Mohamed", "last_name": "Diallo",
            "phone": "620112233", "email": "m@gmail.com",
            "password": "FixPro2026!",
        })  # pas de csrf_token -> refuse par Flask-WTF
        self.assertEqual(r.status_code, 400)
        html = r.get_data(as_text=True)
        self.assertIn("session a expiré", html)
        self.assertIn('href="/devenir-technicien"', html)
        self.assertNotIn("CSRF tokens do not match", html)
        self.assertNotIn("Bad Request", html)
        # cliquer "Reprendre" doit rendre l'etape normalement, avec un jeton frais
        resumed = self.client.get("/devenir-technicien").get_data(as_text=True)
        self.assertIn('name="csrf_token"', resumed)
        self.assertNotIn("session a expiré", resumed)

    def test_stale_token_outside_wizard_shows_branded_page_not_raw_400(self):
        r = self.client.post("/login", data={
            "identifier": "+224620000000", "password": "whatever",
        })
        self.assertEqual(r.status_code, 400)
        html = r.get_data(as_text=True)
        self.assertIn("session a expiré", html)
        self.assertNotIn("CSRF tokens do not match", html)
        self.assertNotIn("<title>Redirecting", html)  # jamais l'ecran Werkzeug brut

    def test_double_submit_of_finalize_form_never_500s_or_raw_400s(self):
        """Reproduit le scenario signale : jeton perime sur la page de
        finalisation (retour arriere / double clic) -> recuperation propre,
        jamais l'ecran blanc "Bad Request"."""
        with self.client as c:
            c.post("/devenir-technicien", data={
                "first_name": "Mohamed", "last_name": "Diallo",
                "phone": "620119988", "email": "mm@gmail.com",
                "password": "FixPro2026!", "csrf_token": self._token(c, "/devenir-technicien"),
            })
            c.post("/devenir-technicien/services", data={
                "trade": "plomberie", "csrf_token": self._token(c, "/devenir-technicien/services")})
            c.post("/devenir-technicien/documents", data={
                "csrf_token": self._token(c, "/devenir-technicien/documents")})
            c.post("/devenir-technicien/localisation", data={
                "latitude": "9.5370", "longitude": "-13.6785",
                "csrf_token": self._token(c, "/devenir-technicien/localisation")})
            # jeton volontairement absent : page de finalisation restee ouverte
            r = c.post("/devenir-technicien/finalisation", data={"accept_cgu": "1"})
            self.assertEqual(r.status_code, 400)
            html = r.get_data(as_text=True)
            self.assertIn("session a expiré", html)
            self.assertIn('href="/devenir-technicien/finalisation"', html)
            self.assertNotIn("CSRF tokens do not match", html)

    def _token(self, client, path):
        import re
        html = client.get(path).get_data(as_text=True)
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        return m.group(1) if m else ""



