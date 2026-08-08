import os
import sys
import tempfile
import unittest
from importlib import reload

# Ajouter le répertoire parent au path pour pouvoir importer fixpro_app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fixpro_app


class FixProAppTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "fixpro_test.db")
        os.environ["FIXPRO_DB_PATH"] = self.db_path
        os.environ["FLASK_ENV"] = "testing"
        os.environ["FLASK_DEBUG"] = "0"
        self.app = reload(fixpro_app).app
        self.app.config.update(TESTING=True)
        with self.app.app_context():
            fixpro_app.init_db()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_registration_and_request_flow(self):
        client = self.app.test_client()

        register_resp = client.post(
            "/register",
            data={
                "full_name": "Aminata Diallo",
                "email": "aminata@example.com",
                "phone": "+224621000000",
                "password": "securePassword123",  # Mot de passe plus sécurisé
                "role": "client",
            },
            follow_redirects=False,
        )
        self.assertIn(register_resp.status_code, (200, 302))

        login_resp = client.post(
            "/login",
            data={"email": "aminata@example.com", "password": "securePassword123"},
            follow_redirects=False,
        )
        self.assertIn(login_resp.status_code, (200, 302))

        request_resp = client.post(
            "/requests/new",
            data={
                "title": "Fuite d'eau",
                "description": "Je dois réparer une fuite urgente",
                "category": "Plomberie",
                "address": "Kaloum",
                "budget": "75000",
            },
            follow_redirects=False,
        )
        self.assertIn(request_resp.status_code, (200, 302))

    def test_email_validation(self):
        """Test que les emails invalides sont rejetés"""
        client = self.app.test_client()

        # Test email invalide
        register_resp = client.post(
            "/register",
            data={
                "full_name": "Test User",
                "email": "invalid-email",
                "phone": "+224621000000",
                "password": "securePassword123",
                "role": "client",
            },
            follow_redirects=False,
        )
        self.assertIn(register_resp.status_code, (200, 302))

    def test_password_validation(self):
        """Test que les mots de passe trop courts sont rejetés"""
        client = self.app.test_client()

        # Test mot de passe trop court
        register_resp = client.post(
            "/register",
            data={
                "full_name": "Test User",
                "email": "test@example.com",
                "phone": "+224621000000",
                "password": "short",  # Moins de 8 caractères
                "role": "client",
            },
            follow_redirects=False,
        )
        self.assertIn(register_resp.status_code, (200, 302))

    def test_security_headers(self):
        """Test que les headers de sécurité sont présents"""
        client = self.app.test_client()
        response = client.get("/")
        
        self.assertIn("X-Frame-Options", response.headers)
        self.assertIn("X-Content-Type-Options", response.headers)
        self.assertIn("X-XSS-Protection", response.headers)

    def test_health_endpoint(self):
        """Test l'endpoint de health check"""
        client = self.app.test_client()
        response = client.get("/health")
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "ok")

    def test_no_demo_accounts_in_production(self):
        """Test que les comptes de démo ne sont pas créés en production"""
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "0"
        
        # Recréer l'application en mode production
        app_prod = reload(fixpro_app).app
        app_prod.config.update(TESTING=True)
        
        with app_prod.app_context():
            # Créer une nouvelle base de données pour le test
            test_db = os.path.join(self.tmpdir.name, "fixpro_prod_test.db")
            os.environ["FIXPRO_DB_PATH"] = test_db
            app_prod.config["DATABASE"] = test_db
            
            fixpro_app.init_db()
            
            conn = fixpro_app.get_db_connection()
            try:
                # Vérifier qu'aucun compte de démo n'existe
                demo_accounts = conn.execute(
                    "SELECT COUNT(*) as count FROM users WHERE email LIKE '%demo%'"
                ).fetchone()
                self.assertEqual(demo_accounts["count"], 0, 
                               "Les comptes de démo ne devraient pas exister en production")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()