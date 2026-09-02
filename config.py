"""Configuration de l'application FixPro.

Toute la configuration provient de variables d'environnement, afin que le
meme code fonctionne en local, sur Vercel et en test sans modification.
"""

import logging
import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Charge le fichier .env en developpement local. En production (Vercel), les
# variables sont fournies par la plateforme et aucun fichier .env n'existe.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass


def _bool(name, default=False):
    return os.getenv(name, "1" if default else "0").strip().lower() in (
        "1", "true", "yes", "on")


class Config:
    """Configuration commune a tous les environnements."""

    FLASK_ENV = os.getenv("FLASK_ENV", "development").lower()
    DEBUG = _bool("FLASK_DEBUG")
    TESTING = False

    # Tableau de bord admin Next.js. Si defini, /admin redirige vers cette URL.
    ADMIN_DASHBOARD_URL = os.getenv("ADMIN_DASHBOARD_URL", "http://localhost:3000/admin").strip().rstrip("/")

    # Cle API pour le dashboard Next.js (V1 : auth simple par cle partagee).
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()

    # Notifications email (optionnel).
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()

    # Base de donnees : PostgreSQL/Supabase si DATABASE_URL est defini,
    # sinon fichier SQLite local.
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
    SQLITE_PATH = os.getenv("FIXPRO_DB_PATH", str(BASE_DIR / "fixpro.db"))

    # Supabase (utilise par le client mobile et les outils d'administration)
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()

    # Serveur (utilise uniquement en execution locale)
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5000"))

    # Commission preleve par la plateforme sur chaque intervention
    FIXPRO_COMMISSION_RATE = float(os.getenv("FIXPRO_COMMISSION_RATE", "0.10"))

    # Rayon (km) autour du client dans lequel un technicien est considere
    # comme "de son secteur". Au-dela, il n'est pas affiche dans la recherche.
    # Rayon "proche" pour l'affichage des techniciens geolocalises. Au-dela,
    # un elargissement progressif evite les listes vides (couverture nationale).
    LOCAL_RADIUS_KM = float(os.getenv("LOCAL_RADIUS_KM", "15"))

    # Verification obligatoire des documents du technicien (piece d'identite +
    # justificatif professionnel) avant acces au tableau de bord.
    # OFF pendant les tests : l'inscription se termine sans documents et le
    # technicien est valide automatiquement. Mettre TECH_VERIFICATION_ENABLED=true
    # (variable d'environnement) pour reactiver le controle complet.
    TECH_VERIFICATION_ENABLED = os.getenv(
        "TECH_VERIFICATION_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")

    # Google OAuth (optionnel, pour le bouton "Continuer avec Google")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    GOOGLE_REDIRECT_URI = os.getenv(
        "GOOGLE_REDIRECT_URI", "").strip()

    # Cle API Google Gemini (optionnel, pour l'assistant conversationnel avance)
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()

    # Liste d'emails administrateurs autorises (separes par des virgules).
    # La connexion admin passe par Google OAuth. Le mot de passe ci-dessous
    # sert de secours si Google OAuth n'est pas configure (developpement).
    ADMIN_EMAILS = [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin" if FLASK_ENV == "development" else "").strip()

    # Si True, l'attribution refuse les techniciens sans GPS recent.
    GPS_REQUIRED = _bool("GPS_REQUIRED")

    # Journalisation
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    # Stockage du compteur de rate limiting. "memory://" ne fonctionne pas en
    # serverless (Vercel) : chaque invocation repart d'un process vide, donc les
    # limites ne s'appliquent jamais. Fournir alors une URL Redis / Upstash.
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://").strip()

    # Taille maximale d'une requete (8 Mo) : les documents envoyes sont des
    # data URI base64 plafonnes a ~3 Mo cote _parse_base64_file. Empeche un
    # POST geant de saturer la memoire de la fonction serverless.
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(8 * 1024 * 1024)))

    # Securite des sessions
    SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    WTF_CSRF_TIME_LIMIT = 86400


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # autorise le HTTP en local


class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False


_PLACEHOLDER_MARKERS = ("remplacez", "change_me", "changeme", "votre-",
                        "your-", "example", "placeholder", "a_generer",
                        "generee")


def _is_placeholder(value):
    """Detecte une valeur d'exemple laissee dans la configuration."""
    v = (value or "").strip().lower()
    return not v or any(marker in v for marker in _PLACEHOLDER_MARKERS)


def get_config():
    """Retourne la configuration correspondant a FLASK_ENV ou a Vercel.

    En production, plusieurs variables sont obligatoires et validees ici :
    - SECRET_KEY : une cle generee au demarrage differerait sur chaque
      instance Vercel et deconnecterait les utilisateurs en permanence ;
    - DATABASE_URL : le systeme de fichiers Vercel est en lecture seule, un
      repli sur SQLite ferait planter l'application.
    """
    env = os.getenv("FLASK_ENV", "development").lower()
    vercel_env = os.getenv("VERCEL_ENV", "").lower()

    is_production = (env == "production" or vercel_env == "production" or
                     os.getenv("VERCEL") == "1")

    if is_production:
        config = ProductionConfig()

        # Erreurs bloquantes : l'application ne peut objectivement pas
        # fonctionner sans ces valeurs.
        errors = []
        if not config.SECRET_KEY:
            errors.append(
                "SECRET_KEY est obligatoire (python manage.py secret).")
        if not config.DATABASE_URL.startswith(("postgres://", "postgresql://")):
            errors.append(
                "DATABASE_URL doit pointer vers PostgreSQL/Supabase "
                "(le systeme de fichiers Vercel est en lecture seule).")
        if errors:
            raise RuntimeError(
                "Configuration de production invalide :\n  - "
                + "\n  - ".join(errors))

        # Avertissements non bloquants : valeurs qui ressemblent a des
        # exemples laisses en place. On journalise sans empecher le demarrage
        # pour eviter toute coupure sur un faux positif.
        import logging as _logging
        _log = _logging.getLogger("fixpro")
        for name in ("SECRET_KEY", "ADMIN_API_KEY", "ADMIN_PASSWORD"):
            value = getattr(config, name, "")
            if value and _is_placeholder(value):
                _log.warning(
                    "%s ressemble a une valeur d'exemple : remplacez-la par "
                    "un secret fort.", name)
        return config

    if env == "testing":
        config = TestingConfig()
    else:
        config = DevelopmentConfig()

    if not config.SECRET_KEY:
        config.SECRET_KEY = secrets.token_hex(32)
    return config


def setup_logging(app):
    """Envoie les journaux vers la sortie standard.

    Les plateformes serverless (Vercel) disposent d'un systeme de fichiers
    en lecture seule : ecrire dans un fichier ferait echouer l'application.
    La sortie standard est collectee automatiquement par Vercel.
    """
    level = getattr(logging, app.config["LOG_LEVEL"], logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"))

    logger = logging.getLogger("fixpro")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(level)

    return logger
