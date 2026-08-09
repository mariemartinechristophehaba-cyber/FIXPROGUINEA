"""Configuration de l'application FixPro.

Toute la configuration provient de variables d'environnement, afin que le
meme code fonctionne en local, sur Vercel et en test sans modification.
"""

import logging
import os
import secrets
import sys
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

    # Journalisation
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    # Securite des sessions
    SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = 3600


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


def get_config():
    """Retourne la configuration correspondant a FLASK_ENV.

    En production, SECRET_KEY doit imperativement etre fournie : une cle
    generee au demarrage serait differente sur chaque instance Vercel, ce
    qui deconnecterait les utilisateurs en permanence.
    """
    env = os.getenv("FLASK_ENV", "development").lower()

    if env == "production":
        config = ProductionConfig()
        if not config.SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY est obligatoire en production. "
                "Definissez-la dans les variables d'environnement Vercel.")
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
