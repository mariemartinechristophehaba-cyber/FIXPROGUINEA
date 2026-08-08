import os
import secrets
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler


class Config:
    """Configuration de base de l'application"""
    
    # Secret Key - Génère une clé si non définie
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    
    # Environnement
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
    
    # Base de données
    FIXPRO_DB_ENGINE = os.getenv("FIXPRO_DB_ENGINE", "sqlite").lower()
    FIXPRO_DB_PATH = os.getenv("FIXPRO_DB_PATH", str(Path(__file__).resolve().parent / "fixpro.db"))
    FIXPRO_DB_HOST = os.getenv("FIXPRO_DB_HOST", "localhost")
    FIXPRO_DB_USER = os.getenv("FIXPRO_DB_USER", "root")
    FIXPRO_DB_PASS = os.getenv("FIXPRO_DB_PASS", "")
    FIXPRO_DB_NAME = os.getenv("FIXPRO_DB_NAME", "FixPro")
    
    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    
    # Serveur
    PORT = int(os.getenv("PORT", 5000))
    HOST = os.getenv("HOST", "0.0.0.0")
    
    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else "*"
    
    # Commission
    FIXPRO_DEFAULT_COMMISSION = int(os.getenv("FIXPRO_DEFAULT_COMMISSION", "10"))
    FIXPRO_COMMISSION_RATE = float(os.getenv("FIXPRO_COMMISSION_RATE", "0.10"))
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if DEBUG else "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/fixpro.log")
    
    # Sécurité
    SESSION_COOKIE_SECURE = not DEBUG
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 heure


class DevelopmentConfig(Config):
    """Configuration de développement"""
    DEBUG = True
    TESTING = False
    CORS_ORIGINS = "*"


class ProductionConfig(Config):
    """Configuration de production"""
    DEBUG = False
    TESTING = False
    
    # En production, CORS doit être restreint
    if os.getenv("CORS_ORIGINS") == "*":
        CORS_ORIGINS = []  # Force la configuration explicite en production


class TestingConfig(Config):
    """Configuration de tests"""
    DEBUG = True
    TESTING = True
    FIXPRO_DB_PATH = ":memory:"  # Base de données en mémoire pour les tests
    CORS_ORIGINS = "*"


def get_config():
    """Retourne la configuration appropriée selon l'environnement"""
    env = os.getenv("FLASK_ENV", "development").lower()
    
    if env == "production":
        return ProductionConfig()
    elif env == "testing":
        return TestingConfig()
    else:
        return DevelopmentConfig()


def setup_logging(app):
    """Configure le logging pour l'application"""
    log_level = getattr(logging, app.config["LOG_LEVEL"].upper(), logging.INFO)
    
    # Créer le répertoire de logs si nécessaire
    log_file = app.config["LOG_FILE"]
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Configuration du logging
    handler = RotatingFileHandler(
        log_file,
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    
    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)
    
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    app.logger.addHandler(console_handler)
    
    app.logger.info('FixPro startup')
    
    return app.logger