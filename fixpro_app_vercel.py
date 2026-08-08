import os
import math
import re
import sqlite3
import logging
from datetime import datetime
from functools import wraps
from pathlib import Path
from email_validator import validate_email, EmailNotValidError

import psycopg2
from psycopg2 import pool
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

# Import de la configuration
from config import get_config, setup_logging

# Charger la configuration
config = get_config()
app = Flask(__name__)
app.config.from_object(config)

# Configuration de la base de données
app.config["DATABASE"] = config.FIXPRO_DB_PATH

# Configuration du logging
logger = setup_logging(app)

# Configuration du rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


def get_db_connection():
    """Établit une connexion à la base de données avec gestion d'erreurs améliorée"""
    db_engine = app.config.get("FIXPRO_DB_ENGINE", "sqlite").lower()
    
    # Priorité : Supabase/PostgreSQL > MySQL > SQLite
    # Utiliser DATABASE_URL si disponible (Supabase)
    database_url = app.config.get("DATABASE_URL", "")
    
    if database_url and db_engine in ("postgresql", "supabase"):
        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = False
            logger.info("Connexion PostgreSQL/Supabase établie avec succès")
            return conn
        except psycopg2.Error as err:
            logger.error(f"Erreur de connexion PostgreSQL: {err}")
            logger.info("Fallback vers SQLite")
        except Exception as err:
            logger.error(f"Erreur inattendue lors de la connexion PostgreSQL: {err}")
            logger.info("Fallback vers SQLite")

    if db_engine == "mysql":
        try:
            import mysql.connector
            conn = mysql.connector.connect(
                host=app.config.get("FIXPRO_DB_HOST", "localhost"),
                user=app.config.get("FIXPRO_DB_USER", "root"),
                password=app.config.get("FIXPRO_DB_PASS", ""),
                database=app.config.get("FIXPRO_DB_NAME", "FixPro"),
                autocommit=False,
            )
            conn.row_factory = None
            logger.info("Connexion MySQL établie avec succès")
            return conn
        except Exception as err:
            logger.error(f"Erreur de connexion MySQL: {err}")
            logger.info("Fallback vers SQLite")

    try:
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        logger.info("Connexion SQLite établie avec succès")
        return conn
    except sqlite3.Error as err:
        logger.error(f"Erreur de connexion SQLite: {err}")
        raise


def init_db():
    """Initialise la base de données avec le schéma approprié selon le type"""
    conn = get_db_connection()
    try:
        db_engine = app.config.get("FIXPRO_DB_ENGINE", "sqlite").lower()
        database_url = app.config.get("DATABASE_URL", "")
        
        # Déterminer si on utilise PostgreSQL/Supabase
        is_postgresql = database_url or db_engine in ("postgresql", "supabase")
        
        if is_postgresql:
            # Schéma PostgreSQL/Supabase
            schema_sql = """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT,
                profession TEXT,
                city TEXT,
                bio TEXT,
                latitude REAL DEFAULT 0,
                longitude REAL DEFAULT 0,
                hourly_rate REAL DEFAULT 0,
                is_verified INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                client_id INTEGER NOT NULL,
                artisan_id INTEGER,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT,
                address TEXT,
                photo_url TEXT,
                diagnostic_price REAL DEFAULT 0,
                budget REAL DEFAULT 0,
                quote_amount REAL DEFAULT 0,
                quote_description TEXT,
                quote_status TEXT DEFAULT 'none',
                quote_proposed_at TEXT,
                quote_approved_at TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS service_categories (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                diagnostic_price REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                request_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                request_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                method TEXT DEFAULT 'cash',
                status TEXT DEFAULT 'pending',
                reference TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS artisans (
                id SERIAL PRIMARY KEY,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                telephone TEXT NOT NULL UNIQUE,
                metier TEXT NOT NULL,
                zone TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                tarif_horaire REAL NOT NULL,
                taux_commission INTEGER DEFAULT 10,
                date_inscription TEXT DEFAULT CURRENT_TIMESTAMP,
                statut TEXT DEFAULT 'actif'
            );

            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                nom TEXT NOT NULL,
                telephone TEXT NOT NULL UNIQUE,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                date_inscription TEXT DEFAULT CURRENT_TIMESTAMP,
                statut TEXT DEFAULT 'actif'
            );
            
            -- Index pour optimiser les performances
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_requests_client_id ON requests(client_id);
            CREATE INDEX IF NOT EXISTS idx_requests_artisan_id ON requests(artisan_id);
            CREATE INDEX IF NOT EXISTS idx_messages_request_id ON messages(request_id);
            CREATE INDEX IF NOT EXISTS idx_payments_request_id ON payments(request_id);
            """
        else:
            # Schéma SQLite (original)
            schema_sql = """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT,
                profession TEXT,
                city TEXT,
                bio TEXT,
                latitude REAL DEFAULT 0,
                longitude REAL DEFAULT 0,
                hourly_rate REAL DEFAULT 0,
                is_verified INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                artisan_id INTEGER,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT,
                address TEXT,
                photo_url TEXT,
                diagnostic_price REAL DEFAULT 0,
                budget REAL DEFAULT 0,
                quote_amount REAL DEFAULT 0,
                quote_description TEXT,
                quote_status TEXT DEFAULT 'none',
                quote_proposed_at TEXT,
                quote_approved_at TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS service_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                diagnostic_price REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                method TEXT DEFAULT 'cash',
                status TEXT DEFAULT 'pending',
                reference TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS artisans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                telephone TEXT NOT NULL UNIQUE,
                metier TEXT NOT NULL,
                zone TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                tarif_horaire REAL NOT NULL,
                taux_commission INTEGER DEFAULT 10,
                date_inscription TEXT DEFAULT CURRENT_TIMESTAMP,
                statut TEXT DEFAULT 'actif'
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                telephone TEXT NOT NULL UNIQUE,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                date_inscription TEXT DEFAULT CURRENT_TIMESTAMP,
                statut TEXT DEFAULT 'actif'
            );
            """
        
        # Exécuter le schéma
        if is_postgresql:
            cursor = conn.cursor()
            cursor.execute(schema_sql)
        else:
            conn.executescript(schema_sql)
        
        conn.commit()
        logger.info(f"Schéma base de données initialisé ({'PostgreSQL' if is_postgresql else 'SQLite'})")

        # NE PLUS CRÉER DE COMPTES DE DÉMONSTRATION EN PRODUCTION
        # Les comptes de démonstration ne sont créés qu'en mode développement
        if app.config.get("DEBUG"):
            try:
                # Vérifier si des utilisateurs existent déjà
                if is_postgresql:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM users LIMIT 1")
                    has_users = cursor.fetchone()
                else:
                    has_users = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
                
                if not has_users:
                    logger.warning("Création des comptes de démonstration (mode développement uniquement)")
                    
                    if is_postgresql:
                        # PostgreSQL style
                        cursor.execute(
                            """
                            INSERT INTO users (email, password_hash, role, full_name, phone, profession, city, bio, latitude, longitude, hourly_rate, is_verified)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                "demo.artisan@fixpro.app",
                                generate_password_hash("FixPro2026!"),
                                "artisan",
                                "Mamadou Bah",
                                "+224621111111",
                                "Plombier",
                                "Conakry",
                                "Artisan certifié, disponible rapidement.",
                                9.5412,
                                -13.7531,
                                50000,
                                1,
                            ),
                        )
                        cursor.execute(
                            """
                            INSERT INTO users (email, password_hash, role, full_name, phone, profession, city, bio, latitude, longitude, hourly_rate, is_verified)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                "demo.client@fixpro.app",
                                generate_password_hash("FixPro2026!"),
                                "client",
                                "Aminata Sow",
                                "+224622222222",
                                "",
                                "Conakry",
                                "Client de démonstration.",
                                9.5418,
                                -13.7540,
                                0,
                                1,
                            ),
                        )
                    else:
                        # SQLite style
                        conn.execute(
                            """
                            INSERT INTO users (email, password_hash, role, full_name, phone, profession, city, bio, latitude, longitude, hourly_rate, is_verified)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                "demo.artisan@fixpro.app",
                                generate_password_hash("FixPro2026!"),
                                "artisan",
                                "Mamadou Bah",
                                "+224621111111",
                                "Plombier",
                                "Conakry",
                                "Artisan certifié, disponible rapidement.",
                                9.5412,
                                -13.7531,
                                50000,
                                1,
                            ),
                        )
                        conn.execute(
                            """
                            INSERT INTO users (email, password_hash, role, full_name, phone, profession, city, bio, latitude, longitude, hourly_rate, is_verified)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                "demo.client@fixpro.app",
                                generate_password_hash("FixPro2026!"),
                                "client",
                                "Aminata Sow",
                                "+224622222222",
                                "",
                                "Conakry",
                                "Client de démonstration.",
                                9.5418,
                                -13.7540,
                                0,
                                1,
                            ),
                        )
                    
                    conn.commit()
                    logger.info("Comptes de démonstration créés avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de la création des comptes de démonstration: {e}")
                # Ne pas échouer l'initialisation si les comptes demo échouent

        existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(requests)").fetchall()]
        if "photo_url" not in existing_columns:
            conn.execute("ALTER TABLE requests ADD COLUMN photo_url TEXT")
        if "diagnostic_price" not in existing_columns:
            conn.execute("ALTER TABLE requests ADD COLUMN diagnostic_price REAL DEFAULT 0")
        if "quote_amount" not in existing_columns:
            conn.execute("ALTER TABLE requests ADD COLUMN quote_amount REAL DEFAULT 0")
        if "quote_description" not in existing_columns:
            conn.execute("ALTER TABLE requests ADD COLUMN quote_description TEXT")
        if "quote_status" not in existing_columns:
            conn.execute("ALTER TABLE requests ADD COLUMN quote_status TEXT DEFAULT 'none'")
        if "quote_proposed_at" not in existing_columns:
            conn.execute("ALTER TABLE requests ADD COLUMN quote_proposed_at TEXT")
        if "quote_approved_at" not in existing_columns:
            conn.execute("ALTER TABLE requests ADD COLUMN quote_approved_at TEXT")

        payment_columns = [row[1] for row in conn.execute("PRAGMA table_info(payments)").fetchall()]
        if "details" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN details TEXT")
        if "updated_at" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP")

        categories = conn.execute("SELECT 1 FROM service_categories LIMIT 1").fetchone()
        if not categories:
            conn.executemany(
                "INSERT INTO service_categories (name, diagnostic_price) VALUES (?, ?)",
                [
                    ("Plombier", 50000),
                    ("Électricien", 45000),
                    ("Frigoriste", 65000),
                    ("Menuisier", 40000),
                    ("Chauffagiste", 55000),
                    ("Serrurier", 48000),
                ],
            )
            conn.commit()
    finally:
        conn.close()


init_db()


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Veuillez vous connecter pour accéder à cette page.", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


PAYMENT_METHODS = {
    "orange_money": "Orange Money",
    "mtn_mobile_money": "MTN Mobile Money",
    "card": "Carte bancaire",
    "cash": "Espèces en main propre",
    "mobile_money": "Mobile Money",
}


def payment_method_label(method):
    return PAYMENT_METHODS.get(method, method.replace("_", " ").title())


def mask_payment_info(method, info):
    digits = re.sub(r"\D", "", info or "")
    if method == "card" and len(digits) >= 4:
        return "Carte • **** **** **** " + digits[-4:]
    if method in ("orange_money", "mtn_mobile_money") and len(digits) >= 4:
        return f"{payment_method_label(method)} • ...{digits[-4:]}"
    return info


def can_access_request(user, req):
    if not user or not req:
        return False
    if user["role"] == "admin":
        return True
    return user["id"] in (req["client_id"], req["artisan_id"])


def is_prohibited_message(content):
    content = content or ""
    normalized = re.sub(r"\s+", " ", content.lower())
    phone_pattern = re.compile(r"(?:\d[\s\-\.\(\)]?){8,}")
    forbidden_phrases = [
        "whatsapp",
        "appelle-moi",
        "contacte-moi directement",
        "contacte moi directement",
        "contactez-moi",
        "appelez-moi",
        "appelle moi",
        "contacte-moi",
        "directement",
        "coordonnées",
        "téléphone",
        "tel:",
        "wa.me",
        "telegram",
        "sms",
        "signal",
    ]

    if phone_pattern.search(content):
        return True

    for phrase in forbidden_phrases:
        if phrase in normalized:
            return True

    return False


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/mobile_welcome")
def mobile_welcome():
    return render_template("mobile_welcome.html")


@app.route("/mobile_dashboard")
@login_required
def mobile_dashboard():
    user = get_current_user() or {"full_name": "Aminata Sow"}
    return render_template("mobile_dashboard.html", user=user)


@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    # Minimal dashboard data for client view
    stats = {
        "contracts": 3,
        "completed": 24,
        "rating": 4.7,
        "total_spent": 3540000,
        "month_spent": 420000,
    }
    return render_template("dashboard_client.html", user=user, stats=stats)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "client")
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        profession = request.form.get("profession", "").strip()
        city = request.form.get("city", "").strip()
        bio = request.form.get("bio", "").strip()

        # Validation améliorée
        if not email or not password or not full_name:
            flash("Veuillez remplir tous les champs obligatoires.", "error")
            return redirect(url_for("register"))

        # Validation de l'email
        try:
            validate_email(email)
        except EmailNotValidError:
            flash("Format d'email invalide.", "error")
            return redirect(url_for("register"))

        # Validation du mot de passe (minimum 8 caractères)
        if len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
            return redirect(url_for("register"))

        conn = get_db_connection()
        try:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                flash("Cet email est déjà utilisé.", "error")
                return redirect(url_for("register"))

            conn.execute(
                """
                INSERT INTO users (email, password_hash, role, full_name, phone, profession, city, bio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email, generate_password_hash(password), role, full_name, phone, profession, city, bio),
            )
            conn.commit()
            flash("Compte créé avec succès. Vous pouvez vous connecter.", "success")
            return redirect(url_for("login"))
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Validation de l'email
        try:
            validate_email(email)
        except EmailNotValidError:
            flash("Format d'email invalide.", "error")
            return redirect(url_for("login"))

        conn = get_db_connection()
        try:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                flash("Bienvenue dans FixPro.", "success")
                return redirect(url_for("dashboard"))
            flash("Identifiants incorrects.", "error")
        finally:
            conn.close()

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "success")
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = get_current_user()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        profession = request.form.get("profession", "").strip()
        city = request.form.get("city", "").strip()
        bio = request.form.get("bio", "").strip()
        hourly_rate = float(request.form.get("hourly_rate") or 0)
        latitude = float(request.form.get("latitude") or 0)
        longitude = float(request.form.get("longitude") or 0)

        conn = get_db_connection()
        try:
            conn.execute(
                """
                UPDATE users
                SET full_name = ?, phone = ?, profession = ?, city = ?, bio = ?, hourly_rate = ?, latitude = ?, longitude = ?
                WHERE id = ?
                """,
                (full_name, phone, profession, city, bio, hourly_rate, latitude, longitude, user["id"]),
            )
            conn.commit()
            flash("Profil mis à jour.", "success")
        finally:
            conn.close()
        return redirect(url_for("profile"))

    return render_template("profile.html", user=user)


@app.route("/artisans")
@login_required
def artisans_page():
    user = get_current_user()
    conn = get_db_connection()
    try:
        artisans = conn.execute(
            "SELECT id, full_name AS nom, profession AS metier, city, hourly_rate, latitude, longitude FROM users WHERE role = 'artisan' ORDER BY full_name"
        ).fetchall()
        active_requests = {}
        if user["role"] == "client":
            rows = conn.execute(
                "SELECT id, artisan_id FROM requests WHERE client_id = ? AND artisan_id IS NOT NULL AND status NOT IN ('pending') ORDER BY updated_at DESC",
                (user["id"],),
            ).fetchall()
            active_requests = {row["artisan_id"]: row["id"] for row in rows}
    finally:
        conn.close()
    return render_template("artisans.html", artisans=artisans, user=user, active_requests=active_requests)


@app.route("/artisans/<int:artisan_id>/contact")
@login_required
def artisan_contact(artisan_id):
    user = get_current_user()
    if user["role"] != "client":
        flash("Cette action est réservée aux clients.", "error")
        return redirect(url_for("artisans_page"))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT id FROM requests WHERE client_id = ? AND artisan_id = ? AND status IN ('assigned', 'quote_proposed', 'quote_accepted') ORDER BY updated_at DESC LIMIT 1",
            (user["id"], artisan_id),
        ).fetchone()
    finally:
        conn.close()

    if req:
        return redirect(url_for("request_detail", request_id=req["id"]))

    flash("Aucun contrat actif avec ce technicien. Créez d'abord une demande pour démarrer une conversation.", "info")
    return redirect(url_for("request_new"))


@app.route("/conversations")
@login_required
def conversations():
    user = get_current_user()
    conn = get_db_connection()
    try:
        if user["role"] == "artisan":
            rows = conn.execute(
                "SELECT r.*, u.full_name AS client_name FROM requests r JOIN users u ON u.id = r.client_id WHERE r.artisan_id = ? ORDER BY r.updated_at DESC",
                (user["id"],),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT r.*, u.full_name AS artisan_name FROM requests r LEFT JOIN users u ON u.id = r.artisan_id WHERE r.client_id = ? ORDER BY r.updated_at DESC",
                (user["id"],),
            ).fetchall()
        conversations = []
        for row in rows:
            last_message = conn.execute(
                "SELECT content, sender_id, created_at FROM messages WHERE request_id = ? ORDER BY created_at DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            conversations.append(
                {
                    "request": row,
                    "last_message": last_message,
                }
            )
    finally:
        conn.close()
    return render_template("conversations.html", conversations=conversations, user=user)


@app.route("/requests")
@login_required
def requests_list():
    user = get_current_user()
    conn = get_db_connection()
    try:
        if user["role"] == "artisan":
            rows = conn.execute(
                "SELECT * FROM requests WHERE artisan_id = ? OR status = 'pending' ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM requests WHERE client_id = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall()
    finally:
        conn.close()
    return render_template("requests.html", requests=rows, user=user)


@app.route("/requests/new", methods=["GET", "POST"])
@login_required
def request_new():
    user = get_current_user()
    conn = get_db_connection()
    try:
        categories = conn.execute("SELECT * FROM service_categories ORDER BY name").fetchall()
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "").strip()
            address = request.form.get("address", "").strip()
            photo_url = request.form.get("photo_url", "").strip()
            budget = float(request.form.get("budget") or 0)

            if not title or not description:
                flash("Le titre et la description sont obligatoires.", "error")
                return redirect(url_for("request_new"))

            category_row = conn.execute(
                "SELECT diagnostic_price FROM service_categories WHERE name = ?",
                (category,),
            ).fetchone()
            diagnostic_price = float(category_row["diagnostic_price"]) if category_row else 0

            conn.execute(
                """
                INSERT INTO requests (client_id, title, description, category, address, photo_url, diagnostic_price, budget, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user["id"], title, description, category, address, photo_url, diagnostic_price, budget, "pending"),
            )
            conn.commit()
            flash("Demande d'intervention créée. Un artisan pourra maintenant la prendre en charge.", "success")
            return redirect(url_for("requests_list"))
    finally:
        conn.close()

    return render_template("request_form.html", categories=categories)


@app.route("/requests/<int:request_id>", methods=["GET", "POST"])
@login_required
def request_detail(request_id):
    user = get_current_user()
    conn = get_db_connection()
    try:
        req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req:
            flash("Demande introuvable.", "error")
            return redirect(url_for("requests_list"))

        if not can_access_request(user, req):
            flash("Vous n'êtes pas autorisé à voir cette intervention.", "error")
            return redirect(url_for("requests_list"))

        client = conn.execute("SELECT * FROM users WHERE id = ?", (req["client_id"],)).fetchone()
        artisan = conn.execute("SELECT * FROM users WHERE id = ?", (req["artisan_id"],)).fetchone() if req["artisan_id"] else None
        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name FROM messages m JOIN users u ON u.id = m.sender_id WHERE m.request_id = ? ORDER BY m.created_at ASC",
            (request_id,),
        ).fetchall()
        payments = conn.execute("SELECT * FROM payments WHERE request_id = ? ORDER BY created_at DESC", (request_id,)).fetchall()

        if request.method == "POST" and request.form.get("message"):
            content = request.form.get("message", "").strip()
            if content:
                if is_prohibited_message(content):
                    flash(
                        "Message bloqué : vous ne pouvez pas partager de coordonnées personnelles ou demander un contact en dehors de la plateforme.",
                        "error",
                    )
                    return redirect(url_for("request_detail", request_id=request_id))

                conn.execute(
                    "INSERT INTO messages (request_id, sender_id, content) VALUES (?, ?, ?)",
                    (request_id, user["id"], content),
                )
                conn.commit()
                flash("Message envoyé.", "success")
                return redirect(url_for("request_detail", request_id=request_id))

    finally:
        conn.close()

    return render_template(
        "request_detail.html",
        request_item=req,
        client=client,
        artisan=artisan,
        messages=messages,
        payments=payments,
        user=user,
        payment_method_label=payment_method_label,
    )


@app.route("/requests/<int:request_id>/payment")
@login_required
def payment_page(request_id):
    user = get_current_user()
    if user["role"] != "client":
        flash("Seuls les clients peuvent accéder à la page de paiement.", "error")
        return redirect(url_for("request_detail", request_id=request_id))

    conn = get_db_connection()
    try:
        req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["client_id"] != user["id"]:
            flash("Vous n'avez pas accès à cette page de paiement.", "error")
            return redirect(url_for("requests_list"))
        if req["quote_status"] != "accepted":
            flash("Le paiement n'est disponible que lorsque le devis a été accepté.", "error")
            return redirect(url_for("request_detail", request_id=request_id))
        artisan = conn.execute("SELECT id, full_name AS nom FROM users WHERE id = ?", (req["artisan_id"],)).fetchone() if req["artisan_id"] else None
        payments = conn.execute("SELECT * FROM payments WHERE request_id = ? ORDER BY created_at DESC", (request_id,)).fetchall()
    finally:
        conn.close()

    return render_template(
        "payment_page.html",
        request_item=req,
        artisan=artisan,
        payments=payments,
        user=user,
        payment_method_label=payment_method_label,
    )


@app.route("/requests/<int:request_id>/accept", methods=["POST"])
@login_required
def accept_request(request_id):
    user = get_current_user()
    if user["role"] != "artisan":
        flash("Seuls les artisans peuvent accepter une demande.", "error")
        return redirect(url_for("requests_list"))

    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE requests SET artisan_id = ?, status = 'assigned', updated_at = ? WHERE id = ?",
            (user["id"], datetime.utcnow().isoformat(), request_id),
        )
        conn.commit()
        flash("Demande attribuée. Proposez un devis complémentaire afin que le client puisse l'accepter.", "success")
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


@app.route("/requests/<int:request_id>/quote", methods=["POST"])
@login_required
def propose_quote(request_id):
    user = get_current_user()
    if user["role"] != "artisan":
        flash("Seuls les artisans peuvent proposer un devis.", "error")
        return redirect(url_for("requests_list"))

    conn = get_db_connection()
    try:
        req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["artisan_id"] != user["id"]:
            flash("Accès refusé.", "error")
            return redirect(url_for("requests_list"))
        if req["status"] not in ("assigned", "quote_rejected", "quote_proposed"):
            flash("Impossible de proposer un devis pour cette demande.", "error")
            return redirect(url_for("request_detail", request_id=request_id))

        amount = float(request.form.get("quote_amount") or 0)
        description = request.form.get("quote_description", "").strip()
        if amount <= 0 or not description:
            flash("Le devis doit inclure un montant valide et une description.", "error")
            return redirect(url_for("request_detail", request_id=request_id))

        conn.execute(
            "UPDATE requests SET quote_amount = ?, quote_description = ?, quote_status = 'pending', quote_proposed_at = ?, status = 'quote_proposed', updated_at = ? WHERE id = ?",
            (amount, description, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), request_id),
        )
        conn.commit()
        flash("Devis proposé. Le client doit maintenant l'accepter pour valider l'intervention.", "success")
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


@app.route("/requests/<int:request_id>/quote/accept", methods=["POST"])
@login_required
def accept_quote(request_id):
    user = get_current_user()
    if user["role"] != "client":
        flash("Seul le client peut accepter le devis.", "error")
        return redirect(url_for("requests_list"))

    conn = get_db_connection()
    try:
        req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["client_id"] != user["id"]:
            flash("Accès refusé.", "error")
            return redirect(url_for("requests_list"))
        if req["quote_status"] != "pending":
            flash("Aucun devis en attente à accepter.", "error")
            return redirect(url_for("request_detail", request_id=request_id))

        conn.execute(
            "UPDATE requests SET quote_status = 'accepted', status = 'quote_accepted', quote_approved_at = ?, updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), request_id),
        )
        conn.commit()
        flash("Devis accepté. L'intervention est maintenant validée.", "success")
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


@app.route("/requests/<int:request_id>/quote/reject", methods=["POST"])
@login_required
def reject_quote(request_id):
    user = get_current_user()
    if user["role"] != "client":
        flash("Seul le client peut rejeter le devis.", "error")
        return redirect(url_for("requests_list"))

    conn = get_db_connection()
    try:
        req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["client_id"] != user["id"]:
            flash("Accès refusé.", "error")
            return redirect(url_for("requests_list"))
        if req["quote_status"] != "pending":
            flash("Aucun devis en attente à rejeter.", "error")
            return redirect(url_for("request_detail", request_id=request_id))

        conn.execute(
            "UPDATE requests SET quote_status = 'rejected', status = 'quote_rejected', updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), request_id),
        )
        conn.commit()
        flash("Devis rejeté. L'artisan peut proposer un nouveau devis.", "success")
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


@app.route("/requests/<int:request_id>/complete", methods=["POST"])
@login_required
def complete_request(request_id):
    user = get_current_user()
    conn = get_db_connection()
    try:
        req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req:
            flash("Demande introuvable.", "error")
            return redirect(url_for("requests_list"))

        if user["role"] == "artisan" and req["artisan_id"] == user["id"]:
            conn.execute(
                "UPDATE requests SET status = 'completed', updated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), request_id),
            )
            conn.commit()
            flash("Intervention marquée comme terminée.", "success")
        elif user["role"] == "client" and req["client_id"] == user["id"]:
            conn.execute(
                "UPDATE requests SET status = 'completed', updated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), request_id),
            )
            conn.commit()
            flash("Intervention marquée comme terminée.", "success")
        else:
            flash("Action non autorisée.", "error")
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


@app.route("/requests/<int:request_id>/payment/process", methods=["POST"])
@login_required
def process_payment(request_id):
    user = get_current_user()
    if user["role"] != "client":
        flash("Seuls les clients peuvent effectuer des paiements.", "error")
        return redirect(url_for("request_detail", request_id=request_id))

    conn = get_db_connection()
    try:
        req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["client_id"] != user["id"]:
            flash("Accès refusé.", "error")
            return redirect(url_for("request_detail", request_id=request_id))

        amount = float(request.form.get("amount") or 0)
        method = request.form.get("method", "cash")
        reference = request.form.get("reference", "").strip()

        if amount <= 0:
            flash("Le montant doit être positif.", "error")
            return redirect(url_for("payment_page", request_id=request_id))

        conn.execute(
            """
            INSERT INTO payments (request_id, amount, method, status, reference, details)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (request_id, amount, method, reference, f"Paiement {payment_method_label(method)}"),
        )
        conn.commit()
        flash("Paiement enregistré. En attente de confirmation.", "success")
    finally:
        conn.close()
    return redirect(url_for("payment_page", request_id=request_id))


@app.route("/api/messages/<int:request_id>")
@login_required
def api_messages(request_id):
    """API endpoint pour polling des messages (alternative à WebSocket pour Vercel)"""
    user = get_current_user()
    conn = get_db_connection()
    try:
        req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or not can_access_request(user, req):
            return jsonify({"error": "Unauthorized"}), 403

        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name FROM messages m JOIN users u ON u.id = m.sender_id WHERE m.request_id = ? ORDER BY m.created_at ASC",
            (request_id,),
        ).fetchall()
        
        return jsonify({
            "messages": [
                {
                    "id": m["id"],
                    "content": m["content"],
                    "sender_id": m["sender_id"],
                    "sender_name": m["sender_name"],
                    "created_at": m["created_at"],
                    "is_own": m["sender_id"] == user["id"]
                }
                for m in messages
            ]
        })
    finally:
        conn.close()


@app.route("/health")
def health_check():
    """Health check endpoint pour Vercel"""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    logger.info(f"Démarrage de FixPro (version Vercel sans WebSocket)")
    logger.info(f"Environnement: {app.config.get('FLASK_ENV', 'development')}")
    logger.info(f"Debug: {app.config.get('DEBUG', False)}")
    
    app.run(
        host=app.config.get("HOST", "0.0.0.0"),
        port=app.config.get("PORT", 5000),
        debug=app.config.get("DEBUG", False)
    )
