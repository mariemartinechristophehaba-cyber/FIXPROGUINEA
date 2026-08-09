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
from flask_socketio import SocketIO, emit

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

# Configuration SocketIO pour le chat en temps réel
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


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

            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_requests_client_id ON requests(client_id);
            CREATE INDEX IF NOT EXISTS idx_requests_artisan_id ON requests(artisan_id);
            CREATE INDEX IF NOT EXISTS idx_messages_request_id ON messages(request_id);
            CREATE INDEX IF NOT EXISTS idx_payments_request_id ON payments(request_id);
            """
        
        cursor = conn.cursor()
        cursor.executescript(schema_sql)
        conn.commit()
        logger.info("Base de données initialisée avec succès")
        
        # Créer des données de démonstration si pas d'utilisateurs
        cursor.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()['count'] if not is_postgresql else cursor.fetchone()[0]
        
        if user_count == 0:
            logger.info("Création des données de démonstration...")
            create_demo_data(cursor, is_postgresql)
            conn.commit()
            
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def create_demo_data(cursor, is_postgresql):
    """Crée des données de démonstration pour l'application"""
    try:
        # Créer un admin
        admin_password = generate_password_hash("admin123")
        if is_postgresql:
            cursor.execute("""
                INSERT INTO users (email, password_hash, role, full_name, profession, city, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, ("admin@fixpro.com", admin_password, "admin", "Admin FixPro", "Administrateur", "Conakry", 1))
        else:
            cursor.execute("""
                INSERT INTO users (email, password_hash, role, full_name, profession, city, is_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("admin@fixpro.com", admin_password, "admin", "Admin FixPro", "Administrateur", "Conakry", 1))
        
        # Créer des catégories de services
        categories = [
            ("Plomberie", 5000),
            ("Électricité", 5000),
            ("Maçonnerie", 5000),
            ("Menuiserie", 5000),
            ("Peinture", 3000),
            ("Climatisation", 10000),
            ("Serrurerie", 5000),
            ("Mécanique", 5000)
        ]
        
        for name, price in categories:
            if is_postgresql:
                cursor.execute("""
                    INSERT INTO service_categories (name, diagnostic_price)
                    VALUES (%s, %s)
                """, (name, price))
            else:
                cursor.execute("""
                    INSERT INTO service_categories (name, diagnostic_price)
                    VALUES (?, ?)
                """, (name, price))
        
        logger.info("Données de démonstration créées avec succès")
        
    except Exception as e:
        logger.error(f"Erreur lors de la création des données de démonstration: {e}")


# Décorateurs de sécurité
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter pour accéder à cette page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter pour accéder à cette page.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Accès réservé aux administrateurs.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# Routes principales
@app.route('/')
def index():
    """Page d'accueil"""
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """Page de connexion"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Validation de l'email
        try:
            validate_email(email)
        except EmailNotValidError:
            flash('Format d\'email invalide.', 'danger')
            return render_template('login.html')
        
        if not email or not password:
            flash('Veuillez remplir tous les champs.', 'warning')
            return render_template('login.html')
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['email'] = user['email']
                session['role'] = user['role']
                session['full_name'] = user['full_name']
                
                logger.info(f"Utilisateur connecté: {email}")
                flash('Connexion réussie!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Email ou mot de passe incorrect.', 'danger')
        finally:
            conn.close()
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def register():
    """Page d'inscription"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', 'client')
        phone = request.form.get('phone', '').strip()
        profession = request.form.get('profession', '').strip()
        city = request.form.get('city', '').strip()
        
        # Validation
        try:
            validate_email(email)
        except EmailNotValidError:
            flash('Format d\'email invalide.', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Les mots de passe ne correspondent pas.', 'danger')
            return render_template('register.html')
        
        if len(password) < 8:
            flash('Le mot de passe doit contenir au moins 8 caractères.', 'danger')
            return render_template('register.html')
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                flash('Cet email est déjà utilisé.', 'danger')
                return render_template('register.html')
            
            password_hash = generate_password_hash(password)
            cursor.execute("""
                INSERT INTO users (email, password_hash, role, full_name, phone, profession, city)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (email, password_hash, role, full_name, phone, profession, city))
            conn.commit()
            
            logger.info(f"Nouvel utilisateur inscrit: {email}")
            flash('Inscription réussie! Vous pouvez maintenant vous connecter.', 'success')
            return redirect(url_for('login'))
        finally:
            conn.close()
    
    return render_template('register.html')


@app.route('/logout')
def logout():
    """Déconnexion"""
    session.clear()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    """Tableau de bord utilisateur"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Statistiques de base
        cursor.execute("SELECT COUNT(*) as count FROM requests WHERE client_id = ?", (session['user_id'],))
        my_requests = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM requests WHERE artisan_id = ?", (session['user_id'],))
        assigned_requests = cursor.fetchone()['count']
        
        return render_template('dashboard.html', 
                             my_requests=my_requests,
                             assigned_requests=assigned_requests)
    finally:
        conn.close()


@app.route('/requests')
@login_required
def list_requests():
    """Liste des demandes"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        if session['role'] == 'client':
            cursor.execute("""
                SELECT r.*, u.full_name as artisan_name 
                FROM requests r
                LEFT JOIN users u ON r.artisan_id = u.id
                WHERE r.client_id = ?
                ORDER BY r.created_at DESC
            """, (session['user_id'],))
        else:
            cursor.execute("""
                SELECT r.*, u.full_name as client_name 
                FROM requests r
                LEFT JOIN users u ON r.client_id = u.id
                WHERE r.artisan_id = ? OR r.status = 'pending'
                ORDER BY r.created_at DESC
            """, (session['user_id'],))
        
        requests = cursor.fetchall()
        return render_template('requests.html', requests=requests)
    finally:
        conn.close()


@app.route('/request/<int:request_id>')
@login_required
def view_request(request_id):
    """Voir une demande spécifique"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, 
                   c.full_name as client_name,
                   a.full_name as artisan_name
            FROM requests r
            LEFT JOIN users c ON r.client_id = c.id
            LEFT JOIN users a ON r.artisan_id = a.id
            WHERE r.id = ?
        """, (request_id,))
        request_data = cursor.fetchone()
        
        if not request_data:
            flash('Demande non trouvée.', 'danger')
            return redirect(url_for('list_requests'))
        
        # Vérifier les permissions
        if (request_data['client_id'] != session['user_id'] and 
            request_data['artisan_id'] != session['user_id'] and
            session['role'] != 'admin'):
            flash('Accès non autorisé.', 'danger')
            return redirect(url_for('list_requests'))
        
        # Récupérer les messages
        cursor.execute("""
            SELECT m.*, u.full_name as sender_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.request_id = ?
            ORDER BY m.created_at ASC
        """, (request_id,))
        messages = cursor.fetchall()
        
        return render_template('view_request.html', 
                             request=request_data, 
                             messages=messages)
    finally:
        conn.close()


@app.route('/request/new', methods=['GET', 'POST'])
@login_required
def new_request():
    """Créer une nouvelle demande"""
    if session['role'] != 'client':
        flash('Seuls les clients peuvent créer des demandes.', 'warning')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        address = request.form.get('address', '').strip()
        budget = request.form.get('budget', 0)
        
        if not title or not description:
            flash('Veuillez remplir les champs obligatoires.', 'warning')
            return render_template('new_request.html')
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO requests (client_id, title, description, category, address, budget)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session['user_id'], title, description, category, address, budget))
            conn.commit()
            
            logger.info(f"Nouvelle demande créée par {session['email']}")
            flash('Demande créée avec succès!', 'success')
            return redirect(url_for('list_requests'))
        finally:
            conn.close()
    
    return render_template('new_request.html')


@app.route('/request/<int:request_id>/assign', methods=['POST'])
@login_required
def assign_request(request_id):
    """Assigner une demande à un artisan"""
    if session['role'] != 'artisan':
        flash('Seuls les artisans peuvent assigner des demandes.', 'warning')
        return redirect(url_for('list_requests'))
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE requests 
            SET artisan_id = ?, status = 'assigned'
            WHERE id = ? AND status = 'pending'
        """, (session['user_id'], request_id))
        conn.commit()
        
        logger.info(f"Demande {request_id} assignée à {session['email']}")
        flash('Demande assignée avec succès!', 'success')
    finally:
        conn.close()
    
    return redirect(url_for('list_requests'))


@app.route('/request/<int:request_id>/quote', methods=['POST'])
@login_required
def submit_quote(request_id):
    """Soumettre un devis"""
    if session['role'] != 'artisan':
        flash('Seuls les artisans peuvent soumettre des devis.', 'warning')
        return redirect(url_for('list_requests'))
    
    quote_amount = request.form.get('quote_amount', 0)
    quote_description = request.form.get('quote_description', '').strip()
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE requests 
            SET quote_amount = ?, quote_description = ?, 
                quote_status = 'proposed', quote_proposed_at = ?
            WHERE id = ? AND artisan_id = ?
        """, (quote_amount, quote_description, datetime.now().isoformat(), 
              request_id, session['user_id']))
        conn.commit()
        
        logger.info(f"Devis soumis pour demande {request_id} par {session['email']}")
        flash('Devis soumis avec succès!', 'success')
    finally:
        conn.close()
    
    return redirect(url_for('view_request', request_id=request_id))


@app.route('/request/<int:request_id>/approve', methods=['POST'])
@login_required
def approve_quote(request_id):
    """Approuver un devis"""
    if session['role'] != 'client':
        flash('Seuls les clients peuvent approuver des devis.', 'warning')
        return redirect(url_for('list_requests'))
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE requests 
            SET quote_status = 'approved', quote_approved_at = ?
            WHERE id = ? AND client_id = ?
        """, (datetime.now().isoformat(), request_id, session['user_id']))
        conn.commit()
        
        logger.info(f"Devis approuvé pour demande {request_id} par {session['email']}")
        flash('Devis approuvé avec succès!', 'success')
    finally:
        conn.close()
    
    return redirect(url_for('view_request', request_id=request_id))


# SocketIO events pour le chat en temps réel
@socketio.on('join')
def on_join(data):
    """Rejoindre une room de chat"""
    request_id = data['request_id']
    room = f"request_{request_id}"
    join_room(room)
    emit('status', {'msg': f"{session['full_name']} a rejoint le chat"}, room=room)


@socketio.on('send_message')
def on_send_message(data):
    """Envoyer un message dans le chat"""
    request_id = data['request_id']
    content = data['content']
    
    if not content.strip():
        return
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (request_id, sender_id, content)
            VALUES (?, ?, ?)
        """, (request_id, session['user_id'], content))
        conn.commit()
        
        # Envoyer le message à tous les participants
        room = f"request_{request_id}"
        emit('message', {
            'sender_name': session['full_name'],
            'content': content,
            'created_at': datetime.now().isoformat()
        }, room=room)
        
        logger.info(f"Message envoyé dans demande {request_id} par {session['email']}")
    finally:
        conn.close()


# Routes API pour l'intégration
@app.route('/api/categories')
def get_categories():
    """API pour récupérer les catégories de services"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM service_categories ORDER BY name")
        categories = cursor.fetchall()
        return jsonify([dict(cat) for cat in categories])
    finally:
        conn.close()


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })


# Gestion des erreurs
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(error):
    logger.error(f"Erreur serveur: {error}")
    return render_template('500.html'), 500


# Initialisation de l'application
with app.app_context():
    init_db()


if __name__ == "__main__":
    logger.info("Démarrage de FixPro")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)