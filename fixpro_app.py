"""FixPro - plateforme de mise en relation entre clients et artisans.

Application Flask unique, compatible :
  - execution locale sur SQLite
  - deploiement serverless sur Vercel avec une base Supabase (PostgreSQL)

Les acces a la base passent tous par le module `db`, ce qui permet
d'ecrire les requetes une seule fois pour les deux moteurs.
"""

import csv
import io
import math
import re
from datetime import datetime, timezone
from functools import wraps

from authlib.integrations.flask_client import OAuth
from email_validator import EmailNotValidError, validate_email
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session, url_for)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

import db
from config import get_config, setup_logging

config = get_config()
app = Flask(__name__, static_folder="api/static", static_url_path="/static")
app.config.from_object(config)

logger = setup_logging(app)
csrf = CSRFProtect(app)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["400 per day", "100 per hour"],
    storage_uri="memory://",
)

oauth = OAuth(app)


@app.before_request
def check_artisan_verification():
    """Redirige les artisans non verifies vers la page d'attente."""
    if app.config.get("BYPASS_AUTH"):
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None
    public_endpoints = {
        "artisan_pending", "logout", "static", "login", "register",
        "client_signup", "google_signup", "google_callback",
        "complete_profile", "health", "index", "contact",
    }
    if request.endpoint in public_endpoints or request.endpoint is None:
        return None
    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT role, is_verified FROM users WHERE id = ?", (user_id,)).fetchone()
        if user and user["role"] == "artisan" and not user["is_verified"]:
            return redirect(url_for("artisan_pending"))
    finally:
        conn.close()
    return None


def _get_google_client():
    """Enregistre le client Google OAuth si les identifiants sont presents."""
    client_id = app.config.get("GOOGLE_CLIENT_ID")
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = app.config.get("GOOGLE_REDIRECT_URI")

    if not client_id or not client_secret or not redirect_uri:
        return None

    try:
        return oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={
                "scope": "openid email profile",
                "redirect_uri": redirect_uri,
            },
        )
    except Exception:
        return None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_db_connection():
    """Ouvre une connexion vers la base configuree pour cet environnement."""
    return db.connect(
        database_url=app.config.get("DATABASE_URL", ""),
        sqlite_path=app.config.get("SQLITE_PATH", "fixpro.db"),
    )


# ---------------------------------------------------------------------------
# Securite et helpers
# ---------------------------------------------------------------------------

@app.after_request
def add_security_headers(response):
    """Ajoute les en-tetes de securite recommandes a chaque reponse."""
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not app.config.get("DEBUG"):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains")
    return response


def _ensure_dev_user(role="client"):
    """Cree ou recupere un compte de test pour le developpement."""
    email = f"dev.{role}@fixpro.local"
    phone = f"+224999{role[:1].upper()}0000"
    full_name = f"Utilisateur Test {role.title()}"

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? OR phone = ?",
            (email, phone)).fetchone()
        if user:
            return user

        profession = "Plombier" if role == "artisan" else None
        hourly_rate = 50000 if role == "artisan" else 0
        conn.execute(
            "INSERT INTO users (email, phone, password_hash, role, full_name,"
            " profession, city, hourly_rate)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (email, phone, generate_password_hash("dev"), role, full_name,
             profession, "Conakry", hourly_rate),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    finally:
        conn.close()


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if app.config.get("BYPASS_AUTH"):
                role = app.config.get("DEV_ROLE", "client")
                dev_user = _ensure_dev_user(role)
                session["user_id"] = dev_user["id"]
                session.permanent = True
            else:
                flash("Veuillez vous connecter pour accéder à cette page.", "error")
                return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


def admin_required(view_func):
    """Verifie que l'utilisateur connecte possede le role admin."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or user["role"] != "admin":
            flash("Acces reserve aux administrateurs.", "error")
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)
    return wrapper


def log_admin_action(admin_id, admin_email, action, target_type=None, target_id=None, details=None):
    """Enregistre une action sensible dans admin_logs."""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO admin_logs (admin_id, admin_email, action, target_type, target_id, details)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (admin_id, admin_email, action, target_type, target_id, details))
        conn.commit()
    finally:
        conn.close()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        if app.config.get("BYPASS_AUTH"):
            role = app.config.get("DEV_ROLE", "client")
            dev_user = _ensure_dev_user(role)
            session["user_id"] = dev_user["id"]
            session.permanent = True
            return dev_user
        return None
    conn = get_db_connection()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
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
    return PAYMENT_METHODS.get(method, (method or "").replace("_", " ").title())


@app.context_processor
def inject_layout_context():
    """Expose l'utilisateur connecte et les compteurs admin a tous les gabarits."""
    try:
        connected = get_current_user()
    except Exception:
        connected = None

    stats = {}
    if connected and connected.get("role") == "admin":
        conn = get_db_connection()
        try:
            stats["pending_artisans"] = conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role = 'artisan' AND is_verified = 0").fetchone()["n"]
            stats["open_requests"] = conn.execute(
                "SELECT COUNT(*) AS n FROM requests"
                " WHERE status NOT IN ('completed', 'cancelled')").fetchone()["n"]
            stats["open_tickets"] = conn.execute(
                "SELECT COUNT(*) AS n FROM admin_tickets WHERE status = 'open'").fetchone()["n"]
        finally:
            conn.close()

    return {"nav_user": connected, "admin_stats": stats}


def can_access_request(user, req):
    """Determine si un utilisateur a le droit de consulter une intervention.

    Le client et l'artisan attribue y ont acces. Une demande encore ouverte
    reste visible par tous les artisans, sans quoi aucun d'eux ne pourrait
    la consulter pour decider de la prendre en charge.
    """
    if not user or not req:
        return False
    if user["role"] == "admin":
        return True
    if user["id"] in (req["client_id"], req["artisan_id"]):
        return True
    return user["role"] == "artisan" and req["status"] == "pending"


_PHONE_PATTERN = re.compile(r"(?:\d[\s\-\.\(\)]?){8,}")
_FORBIDDEN_PHRASES = (
    "whatsapp", "appelle-moi", "appelle moi", "appelez-moi",
    "contacte-moi", "contacte moi", "contactez-moi",
    "coordonnées", "téléphone", "tel:", "wa.me", "telegram", "sms", "signal",
)


def is_prohibited_message(content):
    """Detecte les tentatives de contact en dehors de la plateforme.

    Le modele economique repose sur la commission prelevee par FixPro :
    l'echange de numeros de telephone est donc bloque dans la messagerie.
    """
    content = content or ""
    if _PHONE_PATTERN.search(content):
        return True
    normalized = re.sub(r"\s+", " ", content.lower())
    return any(phrase in normalized for phrase in _FORBIDDEN_PHRASES)


def calculate_distance(lat1, lon1, lat2, lon2):
    """Distance orthodromique en kilometres entre deux points GPS."""
    radius = 6371
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = math.radians(lon2) - math.radians(lon1)
    a = (math.sin(delta_lat / 2) ** 2
         + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    return radius * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Pages publiques
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/mobile_welcome")
def mobile_welcome():
    return render_template("mobile_welcome.html")


@app.route("/health")
def health_check():
    """Point de controle utilise par Vercel et la supervision."""
    return jsonify({"status": "ok", "timestamp": now_iso()})


@app.route("/health-db")
def health_db():
    """Verifie que la connexion a la base de donnees fonctionne."""
    try:
        conn = get_db_connection()
        try:
            conn.execute("SELECT 1").fetchone()
            return jsonify({"status": "ok", "db": "connected",
                            "timestamp": now_iso()})
        finally:
            conn.close()
    except Exception as exc:
        logger.exception("Echec de la connexion a la base de donnees")
        return jsonify({"status": "error", "db": "disconnected",
                        "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

def _phone_with_prefix(phone):
    """Ajoute le prefixe guineen si absent."""
    phone = (phone or "").strip().replace(" ", "")
    if phone and not phone.startswith("+"):
        phone = f"+224{phone}"
    return phone


def _parse_base64_file(data_uri):
    """Extrait le mime, le nom et le contenu binaire depuis un data URI base64."""
    if not data_uri or not data_uri.startswith("data:"):
        return None, None, None
    try:
        meta, encoded = data_uri.split(",", 1)
        mime = meta.split(";")[0].replace("data:", "")
        ext = ".jpg"
        if "png" in mime:
            ext = ".png"
        elif "pdf" in mime:
            ext = ".pdf"
        return mime, ext, encoded
    except Exception:
        return None, None, None


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    role = request.form.get("role") if request.method == "POST" else request.args.get("role", "client")
    role = (role or "client").lower()
    if role not in ("client", "artisan"):
        role = "client"

    if role == "client" and request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        full_name = f"{first_name} {last_name}".strip()
        phone = _phone_with_prefix(request.form.get("phone", "").strip())
        city = request.form.get("city", "").strip()
        password = request.form.get("password", "")

        if not first_name or not last_name or not phone or not city or not password:
            flash("Veuillez remplir tous les champs obligatoires.", "error")
            return redirect(url_for("register", role=role))

        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caracteres.", "error")
            return redirect(url_for("register", role=role))

        conn = get_db_connection()
        try:
            if conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone():
                flash("Ce numero de telephone est deja utilise.", "error")
                return redirect(url_for("register", role=role))

            email = request.form.get("email", "").strip().lower() or None
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " profession, city, bio, hourly_rate)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (email,
                 phone, generate_password_hash(password), role, full_name,
                 request.form.get("profession", "").strip(),
                 city,
                 request.form.get("bio", "").strip(),
                 0))
            conn.commit()
            new_user = conn.execute(
                "SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
            session.clear()
            session["user_id"] = new_user["id"]
            session.permanent = True
            flash("Bienvenue dans FixPro.", "success")
            return redirect(url_for("artisans_page"))
        finally:
            conn.close()

    if role == "artisan":
        return redirect(url_for("register_artisan"))

    return render_template("register.html", role="client")


@app.route("/register/artisan", methods=["GET", "POST"])
@app.route("/register/artisan/<int:step>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register_artisan(step=1):
    """Parcours d'inscription professionnel en 5 etapes."""
    if step < 1 or step > 5:
        return redirect(url_for("register_artisan", step=1))

    wizard = session.setdefault("artisan_wizard", {})
    categories = []
    conn = get_db_connection()
    try:
        categories = conn.execute(
            "SELECT name FROM service_categories ORDER BY name").fetchall()
    finally:
        conn.close()

    if request.method == "POST":
        action = request.form.get("wizard_action", "next")

        if step == 1:
            wizard["civility"] = request.form.get("civility", "").strip()
            wizard["first_name"] = request.form.get("first_name", "").strip()
            wizard["last_name"] = request.form.get("last_name", "").strip()
            wizard["phone"] = _phone_with_prefix(request.form.get("phone", "").strip())
            wizard["email"] = request.form.get("email", "").strip().lower()
            wizard["identity_doc_type"] = request.form.get("identity_doc_type", "").strip()
            wizard["identity_doc"] = request.form.get("identity_doc", "").strip()
            wizard["identity_doc_name"] = request.form.get("identity_doc_name", "").strip()

            if not all([wizard["first_name"], wizard["last_name"], wizard["phone"],
                        wizard["email"], wizard["identity_doc_type"], wizard["identity_doc"]]):
                flash("Veuillez remplir tous les champs et ajouter la piece d'identite.", "error")
                return redirect(url_for("register_artisan", step=1))
            try:
                validate_email(wizard["email"], check_deliverability=False)
            except EmailNotValidError:
                flash("Format d'email invalide.", "error")
                return redirect(url_for("register_artisan", step=1))

        elif step == 2:
            wizard["profession"] = request.form.get("profession", "").strip()
            wizard["skills"] = ", ".join(request.form.getlist("skills"))
            wizard["years_experience"] = _to_int(request.form.get("years_experience", "0"))
            wizard["bio"] = request.form.get("bio", "").strip()

            if not wizard["profession"]:
                flash("Veuillez choisir un metier.", "error")
                return redirect(url_for("register_artisan", step=2))

        elif step == 3:
            wizard["city"] = request.form.get("city", "").strip()
            wizard["quartier"] = request.form.get("quartier", "").strip()
            wizard["zone_intervention"] = request.form.get("zone_intervention", "").strip()
            wizard["mobility"] = request.form.get("mobility", "").strip()

            if not all([wizard["city"], wizard["quartier"], wizard["zone_intervention"]]):
                flash("Veuillez remplir la localisation et la zone d'intervention.", "error")
                return redirect(url_for("register_artisan", step=3))

        elif step == 4:
            wizard["diploma_doc"] = request.form.get("diploma_doc", "").strip()
            wizard["diploma_doc_name"] = request.form.get("diploma_doc_name", "").strip()

            if not wizard["diploma_doc"]:
                flash("Veuillez ajouter votre diplome ou attestation professionnelle.", "error")
                return redirect(url_for("register_artisan", step=4))

        elif step == 5 and action == "submit":
            return _finalize_artisan_registration(wizard)

        session["artisan_wizard"] = wizard

        if action == "prev" and step > 1:
            return redirect(url_for("register_artisan", step=step - 1))
        if step < 5:
            return redirect(url_for("register_artisan", step=step + 1))
        return redirect(url_for("register_artisan", step=step))

    return render_template("register_artisan.html", step=step, wizard=wizard,
                           categories=categories, total_steps=5)


def _finalize_artisan_registration(wizard):
    """Inscrit l'artisan et ses documents, puis redirige vers l'attente."""
    required = ["first_name", "last_name", "phone", "email", "identity_doc",
                "profession", "city", "quartier", "diploma_doc"]
    for field in required:
        if not wizard.get(field):
            flash("Certaines informations sont manquantes. Veuillez recommencer.", "error")
            return redirect(url_for("register_artisan", step=1))

    conn = get_db_connection()
    try:
        if conn.execute("SELECT id FROM users WHERE phone = ?", (wizard["phone"],)).fetchone():
            flash("Ce numero de telephone est deja utilise.", "error")
            return redirect(url_for("register_artisan", step=1))

        full_name = f"{wizard['civility']} {wizard['first_name']} {wizard['last_name']}".strip()
        password = wizard["phone"].replace("+", "").replace(" ", "")

        conn.execute(
            "INSERT INTO users (email, phone, password_hash, role, full_name, civility,"
            " profession, skills, city, quartier, zone_intervention, mobility,"
            " years_experience, bio, hourly_rate, is_verified, is_active)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (wizard["email"], wizard["phone"], generate_password_hash(password),
             "artisan", full_name, wizard["civility"], wizard["profession"],
             wizard["skills"], wizard["city"], wizard["quartier"],
             wizard["zone_intervention"], wizard["mobility"],
             wizard["years_experience"], wizard["bio"], 0, 0, 1))
        conn.commit()

        artisan = conn.execute(
            "SELECT id FROM users WHERE phone = ?", (wizard["phone"],)).fetchone()
        artisan_id = artisan["id"]

        for doc_type, field, name_field in [
            ("identity", "identity_doc", "identity_doc_name"),
            ("diploma", "diploma_doc", "diploma_doc_name"),
        ]:
            mime, ext, encoded = _parse_base64_file(wizard.get(field, ""))
            if encoded:
                file_name = (wizard.get(name_field, "") or f"{doc_type}{ext}").strip()
                conn.execute(
                    "INSERT INTO technician_documents (technician_id, document_type,"
                    " file_name, mime_type, content_base64)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (artisan_id, doc_type, file_name, mime, encoded))
        conn.commit()
    except Exception as exc:  # pragma: no cover - aide au debug en production
        flash(f"Erreur lors de l'inscription : {exc}", "error")
        return redirect(url_for("register_artisan", step=1))
    finally:
        conn.close()

    session.pop("artisan_wizard", None)
    flash("Votre demande d'inscription a bien ete recue. L'equipe FixPro va verifier vos informations.", "success")
    return redirect(url_for("artisan_pending"))


@app.route("/artisan-pending")
def artisan_pending():
    """Page d'attente affichee aux artisans non valides."""
    return render_template("pending.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Ecran d'accueil admin : redirige si deja connecte."""
    if session.get("user_id"):
        user = get_current_user()
        if user and user["role"] == "admin":
            return redirect(app.config.get("ADMIN_DASHBOARD_URL", url_for("admin_dashboard")))

    fallback_enabled = bool(app.config.get("ADMIN_PASSWORD"))
    if request.method == "POST" and fallback_enabled:
        admin_password = request.form.get("admin_password", "").strip()
        if admin_password == app.config.get("ADMIN_PASSWORD"):
            conn = get_db_connection()
            try:
                admin = conn.execute(
                    "SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
                if not admin:
                    conn.execute(
                        "INSERT INTO users (email, phone, password_hash, role,"
                        " full_name, is_verified, is_active)"
                        " VALUES (?, ?, ?, 'admin', ?, 1, 1)",
                        ("admin@fixpro.local", "+224000000000",
                         generate_password_hash("unused"), "Administrateur"))
                    conn.commit()
                    admin = conn.execute(
                        "SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
                session["user_id"] = admin["id"]
                session.permanent = True
                flash("Bienvenue dans l'administration FixPro.", "success")
                return redirect(app.config.get("ADMIN_DASHBOARD_URL", url_for("admin_dashboard")))
            finally:
                conn.close()
        else:
            flash("Mot de passe incorrect.", "error")

    return render_template("admin_login.html",
                           google_configured=bool(_get_google_client()),
                           fallback_enabled=fallback_enabled)


@app.route("/admin/login/google")
def admin_google_login():
    """Redirige vers Google pour authentifier un administrateur."""
    google_client = _get_google_client()
    if not google_client:
        flash("La connexion Google n'est pas configuree.", "error")
        return redirect(url_for("admin_login"))
    session["oauth_admin"] = True
    redirect_uri = app.config.get("GOOGLE_REDIRECT_URI")
    return google_client.authorize_redirect(redirect_uri)


@app.route("/admin/login/google/callback")
def admin_google_callback():
    """Google retourne ici : on valide l'email contre la whitelist."""
    google_client = _get_google_client()
    if not google_client:
        flash("La connexion Google n'est pas configuree.", "error")
        return redirect(url_for("admin_login"))

    try:
        token = google_client.authorize_access_token()
        userinfo = token.get("userinfo") or google_client.get(
            "https://openidconnect.googleapis.com/v1/userinfo").json()
    except Exception as exc:
        logger.error("Erreur Google OAuth admin : %s", exc)
        flash("La connexion avec Google a echoue.", "error")
        return redirect(url_for("admin_login"))

    email = (userinfo.get("email") or "").strip().lower()
    full_name = userinfo.get("name", "").strip()
    authorized = [e.lower() for e in app.config.get("ADMIN_EMAILS", [])]

    if not email:
        flash("Google n'a pas transmis d'email.", "error")
        return redirect(url_for("admin_login"))

    if email not in authorized:
        flash("Cet email n'est pas autorise a acceder a l'administration.", "error")
        return redirect(url_for("index"))

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, is_verified, is_active)"
                " VALUES (?, ?, ?, 'admin', ?, 1, 1)",
                (email, "+224000000000", generate_password_hash("google_oauth"), full_name))
            conn.commit()
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        flash("Bienvenue dans l'administration FixPro.", "success")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin")
def admin_root():
    """Redirige vers le tableau de bord Next.js."""
    return redirect(app.config.get("ADMIN_DASHBOARD_URL", "http://localhost:3000/admin"))


@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    """Tableau de bord admin : redirige vers le dashboard Next.js."""
    return redirect(app.config.get("ADMIN_DASHBOARD_URL", "http://localhost:3000/admin"))
    try:
        this_month = datetime.now(timezone.utc).strftime("%Y-%m")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        clients_total = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'client'").fetchone()["n"]
        clients_month = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'client'"
            " AND created_at LIKE ?", (this_month + "%",)).fetchone()["n"]

        artisans_total = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'artisan'"
            " AND is_verified = 1 AND is_active = 1").fetchone()["n"]
        artisans_month = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'artisan'"
            " AND is_verified = 1 AND is_active = 1"
            " AND created_at LIKE ?", (this_month + "%",)).fetchone()["n"]

        pending_artisans = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'artisan'"
            " AND is_verified = 0").fetchone()["n"]

        completed_payments = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total,"
            " COALESCE(SUM(commission_amount), 0) AS commission"
            " FROM payments WHERE status = 'completed'").fetchone()

        open_requests = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE status NOT IN ('completed', 'cancelled')").fetchone()["n"]
        open_tickets = conn.execute(
            "SELECT COUNT(*) AS n FROM admin_tickets WHERE status = 'open'").fetchone()["n"]

        today_revenue = conn.execute(
            "SELECT COALESCE(SUM(commission_amount), 0) AS commission"
            " FROM payments WHERE status = 'completed' AND created_at LIKE ?",
            (today + "%",)).fetchone()["commission"]
        today_signups = conn.execute(
            "SELECT COUNT(*) AS n FROM users"
            " WHERE role IN ('client', 'artisan') AND created_at LIKE ?",
            (today + "%",)).fetchone()["n"]
        today_signups_breakdown = conn.execute(
            "SELECT role, COUNT(*) AS n FROM users"
            " WHERE role IN ('client', 'artisan') AND created_at LIKE ?"
            " GROUP BY role", (today + "%",)).fetchall()

        recent_payments = conn.execute(
            "SELECT p.*, u.full_name AS client_name, a.full_name AS artisan_name"
            " FROM payments p"
            " JOIN requests r ON r.id = p.request_id"
            " JOIN users u ON u.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            " ORDER BY p.created_at DESC LIMIT 10").fetchall()

        pending_artisans_list = conn.execute(
            "SELECT u.*, (SELECT COUNT(*) FROM technician_documents WHERE technician_id = u.id) AS doc_count"
            " FROM users u"
            " WHERE u.role = 'artisan' AND u.is_verified = 0"
            " ORDER BY u.created_at DESC LIMIT 5").fetchall()

        recent_logs = conn.execute(
            "SELECT l.*, u.full_name AS admin_name"
            " FROM admin_logs l"
            " LEFT JOIN users u ON u.id = l.admin_id"
            " ORDER BY l.created_at DESC LIMIT 10").fetchall()

        stats = {
            "clients_total": clients_total,
            "clients_month": clients_month,
            "artisans_total": artisans_total,
            "artisans_month": artisans_month,
            "pending_artisans": pending_artisans,
            "completed_total": completed_payments["total"],
            "commission_total": completed_payments["commission"],
            "open_requests": open_requests,
            "open_tickets": open_tickets,
            "today_revenue": today_revenue,
            "today_signups": today_signups,
            "today_signups_breakdown": today_signups_breakdown,
        }
    finally:
        conn.close()
    return render_template("admin_dashboard.html", user=user, stats=stats,
                           recent_payments=recent_payments, recent_logs=recent_logs,
                           pending_artisans_list=pending_artisans_list)


@app.route("/admin/artisans", methods=["GET", "POST"])
@login_required
@admin_required
@limiter.limit("60 per hour", methods=["POST"])
def admin_artisans():
    """Gestion des techniciens avec validation, suspension, reactivation."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        if request.method == "POST" and request.form.get("action"):
            artisan_id = request.form.get("artisan_id")
            action = request.form.get("action")
            reason = (request.form.get("reason") or "").strip()

            if action == "verify":
                conn.execute(
                    "UPDATE users SET is_verified = 1 WHERE id = ? AND role = 'artisan'",
                    (artisan_id,))
                conn.commit()
                log_admin_action(user["id"], user["email"], "verify", "user", artisan_id,
                                 reason or "Validation du profil artisan")
                flash("Technicien valide.", "success")
            elif action == "reject":
                conn.execute(
                    "DELETE FROM users WHERE id = ? AND role = 'artisan' AND is_verified = 0",
                    (artisan_id,))
                conn.commit()
                log_admin_action(user["id"], user["email"], "reject", "user", artisan_id,
                                 reason or "Refus de l'inscription")
                flash("Inscription refusee.", "success")
            elif action == "suspend":
                conn.execute(
                    "UPDATE users SET is_active = 0 WHERE id = ? AND role = 'artisan'",
                    (artisan_id,))
                conn.commit()
                log_admin_action(user["id"], user["email"], "suspend", "user", artisan_id,
                                 reason or "Suspension du compte")
                flash("Technicien suspendu.", "success")
            elif action == "restore":
                conn.execute(
                    "UPDATE users SET is_active = 1 WHERE id = ? AND role = 'artisan'",
                    (artisan_id,))
                conn.commit()
                log_admin_action(user["id"], user["email"], "restore", "user", artisan_id,
                                 reason or "Reactivation du compte")
                flash("Technicien reactive.", "success")
            return redirect(url_for("admin_artisans"))

        q = request.args.get("q", "").strip()
        status_filter = request.args.get("status", "").strip()
        city_filter = request.args.get("city", "").strip()
        profession_filter = request.args.get("profession", "").strip()

        where_parts = ["u.role = 'artisan'"]
        params = []
        if q:
            where_parts.append("(u.full_name LIKE ? OR u.phone LIKE ? OR u.email LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if status_filter == "pending":
            where_parts.append("u.is_verified = 0")
        elif status_filter == "active":
            where_parts.append("u.is_verified = 1 AND u.is_active = 1")
        elif status_filter == "suspended":
            where_parts.append("u.is_active = 0")
        if city_filter:
            where_parts.append("u.city = ?")
            params.append(city_filter)
        if profession_filter:
            where_parts.append("u.profession = ?")
            params.append(profession_filter)

        where_clause = " WHERE " + " AND ".join(where_parts)
        artisans = conn.execute(
            "SELECT u.*,"
            " (SELECT COUNT(*) FROM requests WHERE artisan_id = u.id AND status = 'completed') AS completed,"
            " (SELECT COALESCE(AVG(rating), 0) FROM reviews WHERE artisan_id = u.id) AS avg_rating,"
            " (SELECT COUNT(*) FROM technician_documents WHERE technician_id = u.id) AS doc_count"
            " FROM users u"
            + where_clause +
            " ORDER BY u.is_verified ASC, u.is_active DESC, u.created_at DESC",
            tuple(params)).fetchall()

        cities = conn.execute(
            "SELECT DISTINCT city FROM users WHERE role = 'artisan' AND city IS NOT NULL"
            " ORDER BY city").fetchall()
        professions = conn.execute(
            "SELECT DISTINCT profession FROM users WHERE role = 'artisan' AND profession IS NOT NULL"
            " ORDER BY profession").fetchall()
    finally:
        conn.close()
    return render_template("admin_artisans.html", user=user, artisans=artisans,
                           cities=cities, professions=professions,
                           q=q, status_filter=status_filter,
                           city_filter=city_filter, profession_filter=profession_filter)


@app.route("/admin/artisans/<int:artisan_id>")
@login_required
@admin_required
def admin_artisan_detail(artisan_id):
    """Dossier detaille d'un technicien avec documents."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        artisan = conn.execute(
            "SELECT * FROM users WHERE id = ? AND role = 'artisan'", (artisan_id,)).fetchone()
        if not artisan:
            flash("Technicien introuvable.", "error")
            return redirect(url_for("admin_artisans"))

        documents = conn.execute(
            "SELECT * FROM technician_documents WHERE technician_id = ?",
            (artisan_id,)).fetchall()
    finally:
        conn.close()
    return render_template("admin_artisan_detail.html", user=user,
                           artisan=artisan, documents=documents)


@app.route("/admin/document/<int:doc_id>")
@login_required
@admin_required
def admin_document(doc_id):
    """Affiche un document en base64 (reserve aux admins)."""
    conn = get_db_connection()
    try:
        doc = conn.execute(
            "SELECT * FROM technician_documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            return "Document introuvable.", 404
        if not doc["content_base64"]:
            return "Contenu vide.", 404
    finally:
        conn.close()

    mime = doc["mime_type"] or "image/jpeg"
    data = doc["content_base64"]
    if not data.startswith("data:"):
        data = f"data:{mime};base64,{data}"

    return f"""<!doctype html>
<html lang="fr">
<head><meta charset="utf-8"><title>Document {doc['file_name']}</title></head>
<body style="margin:0;background:#000;display:grid;place-items:center;height:100vh;">
  <img src="{data}" style="max-width:100%;max-height:100vh;" alt="Document" />
  <a href="{url_for('admin_artisan_detail', artisan_id=doc['technician_id'])}" style="position:fixed;top:16px;left:16px;color:#fff;text-decoration:none;font-weight:700;">&larr; Retour</a>
</body>
</html>"""


@app.route("/admin/clients", methods=["GET", "POST"])
@login_required
@admin_required
@limiter.limit("60 per hour", methods=["POST"])
def admin_clients():
    """Liste des clients avec possibilite de suspension."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        if request.method == "POST" and request.form.get("action"):
            client_id = request.form.get("client_id")
            action = request.form.get("action")
            if action == "suspend":
                conn.execute(
                    "UPDATE users SET is_active = 0 WHERE id = ? AND role = 'client'",
                    (client_id,))
                conn.commit()
                log_admin_action(user["id"], user["email"], "suspend_client", "user", client_id)
                flash("Client suspendu.", "success")
            elif action == "restore":
                conn.execute(
                    "UPDATE users SET is_active = 1 WHERE id = ? AND role = 'client'",
                    (client_id,))
                conn.commit()
                log_admin_action(user["id"], user["email"], "restore_client", "user", client_id)
                flash("Client reactive.", "success")
            return redirect(url_for("admin_clients"))

        q = request.args.get("q", "").strip()
        status_filter = request.args.get("status", "").strip()

        where_parts = ["u.role = 'client'"]
        params = []
        if q:
            where_parts.append("(u.full_name LIKE ? OR u.phone LIKE ? OR u.email LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if status_filter == "active":
            where_parts.append("u.is_active = 1")
        elif status_filter == "suspended":
            where_parts.append("u.is_active = 0")

        where_clause = " WHERE " + " AND ".join(where_parts)

        clients = conn.execute(
            "SELECT u.*,"
            " (SELECT COUNT(*) FROM requests WHERE client_id = u.id) AS request_count"
            " FROM users u"
            + where_clause +
            " ORDER BY u.created_at DESC", tuple(params)).fetchall()
    finally:
        conn.close()
    return render_template("admin_clients.html", user=user, clients=clients,
                           q=q, status_filter=status_filter)


@app.route("/admin/requests")
@login_required
@admin_required
def admin_requests():
    """Liste des demandes en cours et historique avec filtres."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        status_filter = request.args.get("status", "").strip()
        q = request.args.get("q", "").strip()

        where_parts = []
        params = []
        if status_filter:
            where_parts.append("r.status = ?")
            params.append(status_filter)
        if q:
            where_parts.append("(r.title LIKE ? OR c.full_name LIKE ? OR a.full_name LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        requests_list = conn.execute(
            "SELECT r.*, c.full_name AS client_name, c.phone AS client_phone,"
            " a.full_name AS artisan_name, a.phone AS artisan_phone"
            " FROM requests r"
            " LEFT JOIN users c ON c.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            + where_clause +
            " ORDER BY r.updated_at DESC", tuple(params)).fetchall()
    finally:
        conn.close()
    return render_template("admin_requests.html", user=user, requests=requests_list,
                           status_filter=status_filter, q=q)


@app.route("/admin/tickets", methods=["GET", "POST"])
@login_required
@admin_required
@limiter.limit("60 per hour", methods=["POST"])
def admin_tickets():
    """Signalements / tickets admin."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        if request.method == "POST" and request.form.get("action"):
            ticket_id = request.form.get("ticket_id")
            action = request.form.get("action")
            if action == "close":
                conn.execute(
                    "UPDATE admin_tickets SET status = 'closed',"
                    " updated_at = CURRENT_TIMESTAMP WHERE id = ?", (ticket_id,))
                conn.commit()
                log_admin_action(user["id"], user["email"], "close_ticket", "admin_ticket", ticket_id)
                flash("Signalement marque comme traite.", "success")
            elif action == "open":
                conn.execute(
                    "UPDATE admin_tickets SET status = 'open',"
                    " updated_at = CURRENT_TIMESTAMP WHERE id = ?", (ticket_id,))
                conn.commit()
                log_admin_action(user["id"], user["email"], "open_ticket", "admin_ticket", ticket_id)
                flash("Signalement rouvert.", "success")
            return redirect(url_for("admin_tickets"))

        tickets = conn.execute(
            "SELECT t.*, c.full_name AS client_name, a.full_name AS artisan_name"
            " FROM admin_tickets t"
            " JOIN users c ON c.id = t.client_id"
            " LEFT JOIN users a ON a.id = t.artisan_id"
            " ORDER BY t.status ASC, t.created_at DESC").fetchall()
    finally:
        conn.close()
    return render_template("admin_tickets.html", user=user, tickets=tickets)


@app.route("/admin/payments", methods=["GET", "POST"])
@login_required
@admin_required
@limiter.limit("60 per hour", methods=["POST"])
def admin_payments():
    """Transactions et commissions avec filtres."""
    user = get_current_user()
    rate = app.config.get("FIXPRO_COMMISSION_RATE", 0.10)
    conn = get_db_connection()
    try:
        status_filter = request.args.get("status", "")
        method_filter = request.args.get("method", "")

        where_parts = []
        params = []
        if status_filter:
            where_parts.append("p.status = ?")
            params.append(status_filter)
        if method_filter:
            where_parts.append("p.method = ?")
            params.append(method_filter)

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        payments = conn.execute(
            "SELECT p.*, u.full_name AS client_name, a.full_name AS artisan_name, r.title"
            " FROM payments p"
            " JOIN requests r ON r.id = p.request_id"
            " JOIN users u ON u.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            + where_clause +
            " ORDER BY p.created_at DESC", tuple(params)).fetchall()
    finally:
        conn.close()
    return render_template("admin_payments.html", user=user, payments=payments,
                           payment_method_label=payment_method_label,
                           commission_rate=rate, status_filter=status_filter,
                           method_filter=method_filter)


@app.route("/admin/payments/<int:payment_id>")
@login_required
@admin_required
def admin_payment_detail(payment_id):
    """Vue detaillee d'une transaction."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        payment = conn.execute(
            "SELECT p.*, u.full_name AS client_name, a.full_name AS artisan_name,"
            " r.title, r.budget, r.status AS request_status"
            " FROM payments p"
            " JOIN requests r ON r.id = p.request_id"
            " JOIN users u ON u.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            " WHERE p.id = ?", (payment_id,)).fetchone()
        if not payment:
            flash("Transaction introuvable.", "error")
            return redirect(url_for("admin_payments"))
    finally:
        conn.close()
    return render_template("admin_payment_detail.html", user=user, payment=payment,
                           payment_method_label=payment_method_label)


@app.route("/admin/payments/<int:payment_id>/pay", methods=["POST"])
@login_required
@admin_required
@limiter.limit("60 per hour", methods=["POST"])
def admin_payment_pay(payment_id):
    """Marque un paiement comme verse au technicien."""
    user = get_current_user()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE payments SET paid_to_artisan_at = ? WHERE id = ?",
            (now, payment_id))
        conn.commit()
        log_admin_action(user["id"], user["email"], "mark_paid_to_artisan",
                         "payment", payment_id, "Verse au technicien le " + now)
        flash("Paiement marque comme verse au technicien.", "success")
    finally:
        conn.close()
    return redirect(url_for("admin_payment_detail", payment_id=payment_id))


@app.route("/tickets/new", methods=["POST"])
@login_required
def ticket_new():
    """Cree un ticket client -> FixPro pour le technicien consulte."""
    user = get_current_user()
    if user["role"] != "client":
        flash("Action reservee aux clients.", "error")
        return redirect(url_for("artisans_page"))

    artisan_id = request.form.get("artisan_id")
    conn = get_db_connection()
    try:
        artisan = conn.execute(
            "SELECT full_name, profession FROM users"
            " WHERE id = ? AND role = 'artisan'", (artisan_id,)).fetchone()
        if not artisan:
            flash("Technicien introuvable.", "error")
            return redirect(url_for("artisans_page"))

        existing = conn.execute(
            "SELECT id FROM admin_tickets"
            " WHERE client_id = ? AND artisan_id = ? AND status = 'open'"
            " ORDER BY created_at DESC LIMIT 1",
            (user["id"], artisan_id)).fetchone()
        if existing:
            return redirect(url_for("ticket_detail", ticket_id=existing["id"]))

        result = conn.execute(
            "INSERT INTO admin_tickets (client_id, artisan_id, subject, message, status)"
            " VALUES (?, ?, ?, ?, 'open')",
            (user["id"], artisan_id,
             f"Concerne {artisan['full_name']}",
             f"Conversation demarree pour le technicien {artisan['full_name']} ({artisan['profession']})."))
        conn.commit()
        ticket_id = result.lastrowid

        # Message d'accueil de FixPro
        fixpro = conn.execute(
            "SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        sender_id = fixpro["id"] if fixpro else user["id"]
        conn.execute(
            "INSERT INTO admin_messages (ticket_id, sender_id, content)"
            " VALUES (?, ?, ?)",
            (ticket_id, sender_id,
             "Bienvenue sur FixPro ! Comment puis-je vous aider ?"))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


def build_assistant_reply(message):
    """Genere une reponse automatique simple, professionnelle et humaine."""
    text = message.lower()
    if any(w in text for w in ("bonjour", "salut", "hello", "bonsoir", "coucou")):
        return ("Bonjour, je suis votre assistante FixPro. Je transmets votre demande a notre equipe."
                " Que puis-je faire pour vous aujourd'hui ?")
    if any(w in text for w in ("prix", "tarif", "combien", "coute", "cout")):
        return ("Le prix d'une intervention depend du devis etabli par le technicien apres diagnostic."
                " Souhaitez-vous que je vous aide a planifier une visite pour obtenir un devis detaille ?")
    if any(w in text for w in ("horaire", "heure", "quand", "date", "disponible", "rdv", "rendez-vous")):
        return ("Vous pouvez indiquer la date et l'heure qui vous conviennent."
                " Le technicien confirmera son creneau des reception de votre demande.")
    if any(w in text for w in ("annuler", "supprimer", "arreter", "annulation")):
        return ("Une demande peut etre annulee tant que l'intervention n'a pas debute."
                " Confirmez votre souhait d'annulation et notre equipe traitera votre demande rapidement.")
    if any(w in text for w in ("contact", "appeler", "telephone", "joindre", "appelle")):
        return ("Vous etes bien en contact avec l'equipe FixPro."
                " Un conseiller prendra le relais des qu'il sera disponible.")
    if any(w in text for w in ("payement", "payer", "paiement", "orange money", "carte", "bancaire")):
        return ("Vous pouvez regler votre intervention par Orange Money, MTN Mobile Money ou carte bancaire directement dans l'application."
                " Le paiement securise est gere par l'equipe FixPro.")
    if any(w in text for w in ("technicien", "artisan", "reparateur", "plombier", "electricien")):
        return ("Votre technicien sera informe de votre message."
                " En attendant, notre equipe peut repondre a toutes vos questions.")
    return "Merci pour votre message. Notre equipe FixPro vous repondra dans les plus brefs delais."


@app.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def ticket_detail(ticket_id):
    """Conversation client <-> FixPro autour d'un ticket."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        ticket = conn.execute(
            "SELECT t.*, c.full_name AS client_name, a.full_name AS artisan_name"
            " FROM admin_tickets t"
            " JOIN users c ON c.id = t.client_id"
            " LEFT JOIN users a ON a.id = t.artisan_id"
            " WHERE t.id = ?", (ticket_id,)).fetchone()
        if not ticket:
            flash("Conversation introuvable.", "error")
            return redirect(url_for("artisans_page"))

        if user["role"] != "admin" and ticket["client_id"] != user["id"]:
            flash("Acces refuse.", "error")
            return redirect(url_for("artisans_page"))

        if request.method == "POST" and request.form.get("content"):
            content = request.form.get("content", "").strip()
            if not content:
                flash("Veuillez ecrire un message.", "error")
            else:
                conn.execute(
                    "INSERT INTO admin_messages (ticket_id, sender_id, content)"
                    " VALUES (?, ?, ?)",
                    (ticket_id, user["id"], content))
                conn.execute(
                    "UPDATE admin_tickets SET updated_at = CURRENT_TIMESTAMP"
                    " WHERE id = ?", (ticket_id,))
                conn.commit()

                # Reponse automatique de l'assistante FixPro
                if user["role"] == "client":
                    reply = build_assistant_reply(content)
                    if reply:
                        fixpro = conn.execute(
                            "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
                        ).fetchone()
                        sender_id = fixpro["id"] if fixpro else user["id"]
                        conn.execute(
                            "INSERT INTO admin_messages (ticket_id, sender_id, content)"
                            " VALUES (?, ?, ?)",
                            (ticket_id, sender_id, reply))
                        conn.execute(
                            "UPDATE admin_tickets SET updated_at = CURRENT_TIMESTAMP"
                            " WHERE id = ?", (ticket_id,))
                        conn.commit()

                return redirect(url_for("ticket_detail", ticket_id=ticket_id))

        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name, u.role AS sender_role"
            " FROM admin_messages m"
            " JOIN users u ON u.id = m.sender_id"
            " WHERE m.ticket_id = ?"
            " ORDER BY m.created_at ASC",
            (ticket_id,)).fetchall()
    finally:
        conn.close()
    return render_template("ticket_detail.html", user=user, ticket=ticket,
                           messages=messages)


@app.route("/admin/logout")
@login_required
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/client-signup", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def client_signup():
    """Inscription rapide client avec email et mot de passe."""
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        full_name = f"{first_name} {last_name}".strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        password = request.form.get("password", "")

        if not first_name or not last_name or not email or not phone or not city or not password:
            flash("Veuillez remplir tous les champs obligatoires.", "error")
            return redirect(url_for("client_signup"))

        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError:
            flash("Format d'email invalide.", "error")
            return redirect(url_for("client_signup"))

        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "error")
            return redirect(url_for("client_signup"))

        conn = get_db_connection()
        try:
            existing_email = conn.execute(
                "SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing_email:
                flash("Cet email est déjà utilisé.", "error")
                return redirect(url_for("client_signup"))

            existing_phone = conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
            if existing_phone:
                flash("Ce numéro de téléphone est déjà utilisé.", "error")
                return redirect(url_for("client_signup"))

            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, city)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (email, phone, generate_password_hash(password), "client",
                 full_name, city),
            )
            conn.commit()

            new_user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            session.clear()
            session["user_id"] = new_user["id"]
            session.permanent = True
            flash("Bienvenue dans FixPro.", "success")
            return redirect(url_for("dashboard"))
        finally:
            conn.close()

    return render_template("client_signup.html")


@app.route("/google-signup")
def google_signup():
    """Redirige vers Google pour l'authentification."""
    google_client = _get_google_client()
    if not google_client:
        flash("La connexion Google n'est pas encore configurée.", "error")
        return redirect(url_for("client_signup"))

    redirect_uri = app.config.get("GOOGLE_REDIRECT_URI")
    return google_client.authorize_redirect(redirect_uri)


@app.route("/google-signup/callback")
def google_callback():
    """Recupere les informations Google et cree/connecte le client."""
    google_client = _get_google_client()
    if not google_client:
        flash("La connexion Google n'est pas encore configurée.", "error")
        return redirect(url_for("client_signup"))

    try:
        token = google_client.authorize_access_token()
        userinfo = token.get("userinfo") or google_client.get(
            "https://openidconnect.googleapis.com/v1/userinfo").json()
    except Exception as exc:
        logger.error("Erreur Google OAuth : %s", exc)
        flash("La connexion avec Google a échoué.", "error")
        return redirect(url_for("client_signup"))

    email = (userinfo.get("email") or "").strip().lower()
    full_name = userinfo.get("name", "").strip()

    if not email:
        flash("Google n'a pas transmis d'email.", "error")
        return redirect(url_for("client_signup"))

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            flash("Bienvenue dans FixPro.", "success")
            return redirect(url_for("dashboard"))

        # Nouvel utilisateur : stocke les donnees en session en attendant
        # le telephone et la ville.
        session["google_email"] = email
        session["google_name"] = full_name
        return redirect(url_for("complete_profile"))
    finally:
        conn.close()


@app.route("/complete-profile", methods=["GET", "POST"])
def complete_profile():
    """Demande le telephone et la ville apres une inscription Google."""
    email = session.get("google_email")
    full_name = session.get("google_name")

    if not email or not full_name:
        flash("Session invalide. Veuillez recommencer.", "error")
        return redirect(url_for("client_signup"))

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()

        if not phone or not city:
            flash("Veuillez remplir tous les champs.", "error")
            return redirect(url_for("complete_profile"))

        conn = get_db_connection()
        try:
            existing_phone = conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
            if existing_phone:
                flash("Ce numéro de téléphone est déjà utilisé.", "error")
                return redirect(url_for("complete_profile"))

            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, city)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (email, phone, generate_password_hash("google_oauth"),
                 "client", full_name, city),
            )
            conn.commit()

            new_user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            session.clear()
            session["user_id"] = new_user["id"]
            session.permanent = True
            flash("Bienvenue dans FixPro.", "success")
            return redirect(url_for("dashboard"))
        finally:
            conn.close()

    return render_template("complete_profile.html", email=email,
                           full_name=full_name)


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()
        try:
            # L'identifiant peut etre un telephone (client) ou un email (artisan).
            if "@" in identifier:
                user = conn.execute(
                    "SELECT * FROM users WHERE email = ?", (identifier.lower(),)).fetchone()
            else:
                user = conn.execute(
                    "SELECT * FROM users WHERE phone = ?", (identifier,)).fetchone()
        finally:
            conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            flash("Bienvenue dans FixPro.", "success")

            if user["role"] == "client":
                return redirect(url_for("artisans_page"))
            return redirect(url_for("requests_list"))

        # Message identique pour ne pas reveler quel identifiant existe.
        flash("Identifiants incorrects.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Espace connecte
# ---------------------------------------------------------------------------

@app.route("/dashboard")
def dashboard():
    user = get_current_user()
    if user is None:
        user = {"id": 0, "full_name": "Visiteur", "role": "client", "city": "Conakry"}
    try:
        conn = get_db_connection()
        # Categories de services
        categories = conn.execute(
            "SELECT name, diagnostic_price FROM service_categories"
            " ORDER BY name").fetchall()

        # Nombre d'artisans par categorie (estimation)
        artisan_counts = {}
        for c in categories:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM users"
                " WHERE role = 'artisan' AND profession LIKE ?",
                (f"%{c['name']}%",)).fetchone()["n"]
            artisan_counts[c["name"]] = count

        # Tous les artisans verifies avec notes et avis (fallback si reviews non prete)
        try:
            artisans = conn.execute("""
                SELECT u.id, u.full_name, u.profession, u.city, u.quartier,
                       u.hourly_rate, u.is_verified, u.photo_url,
                       u.availability_status, u.estimated_delay,
                       COALESCE((SELECT AVG(rating) FROM reviews WHERE artisan_id = u.id), 0) AS avg_rating,
                       COALESCE((SELECT COUNT(*) FROM reviews WHERE artisan_id = u.id), 0) AS review_count
                FROM users u
                WHERE u.role = 'artisan' AND u.is_verified = 1
                ORDER BY u.full_name
            """).fetchall()
        except Exception:
            artisans = conn.execute(
                "SELECT id, full_name, profession, city, quartier, hourly_rate, is_verified,"
                " photo_url, availability_status, estimated_delay"
                " FROM users WHERE role = 'artisan' AND is_verified = 1"
                " ORDER BY full_name").fetchall()

        # Unread messages count
        try:
            unread = conn.execute(
                "SELECT COUNT(*) AS n FROM messages"
                " WHERE sender_id != ? AND request_id IN"
                " (SELECT id FROM requests WHERE client_id = ?)",
                (user["id"], user["id"])).fetchone()
            unread_count = unread["n"] if unread else 0
        except Exception:
            unread_count = 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        flash(f"Erreur dashboard : {exc}", "error")
        return render_template("dashboard_client.html", user=user,
                               categories=categories if 'categories' in locals() else [],
                               artisans=artisans if 'artisans' in locals() else [],
                               unread_count=0)
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    return render_template("dashboard_client.html", user=user,
                           categories=categories,
                           artisans=artisans,
                           unread_count=unread_count)


@app.route("/mobile_dashboard")
@login_required
def mobile_dashboard():
    return render_template("mobile_dashboard.html", user=get_current_user())


@app.route("/payments")
@login_required
def payments():
    user = get_current_user()
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT p.id, p.amount, p.status, p.method, p.reference, p.details,"
            " p.created_at, r.title"
            " FROM payments p JOIN requests r ON r.id = p.request_id"
            " WHERE r.client_id = ? ORDER BY p.created_at DESC",
            (user["id"],)).fetchall()
        stats = conn.execute(
            "SELECT"
            " COALESCE(SUM(CASE WHEN p.status = 'completed' THEN p.amount ELSE 0 END), 0) as total_paid,"
            " COALESCE(SUM(CASE WHEN p.status = 'pending' THEN p.amount ELSE 0 END), 0) as total_pending,"
            " COUNT(*) as count"
            " FROM payments p JOIN requests r ON r.id = p.request_id"
            " WHERE r.client_id = ?",
            (user["id"],)).fetchone()
    finally:
        conn.close()
    return render_template("payments.html", user=user, payments=rows, stats=stats,
                           payment_method_label=payment_method_label)


@app.route("/reviews")
@login_required
def reviews():
    user = get_current_user()
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT r.id, r.rating, r.comment, r.created_at, u.full_name AS artisan_name"
            " FROM reviews r JOIN users u ON u.id = r.artisan_id"
            " WHERE r.client_id = ? ORDER BY r.created_at DESC",
            (user["id"],)).fetchall()
    finally:
        conn.close()
    return render_template("reviews.html", user=user, reviews=rows)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = get_current_user()
    if request.method == "POST":
        conn = get_db_connection()
        try:
            conn.execute(
                "UPDATE users SET full_name = ?, phone = ?, profession = ?,"
                " city = ?, bio = ?, hourly_rate = ?, latitude = ?, longitude = ?"
                " WHERE id = ?",
                (request.form.get("full_name", "").strip(),
                 request.form.get("phone", "").strip(),
                 request.form.get("profession", "").strip(),
                 request.form.get("city", "").strip(),
                 request.form.get("bio", "").strip(),
                 _to_float(request.form.get("hourly_rate")),
                 _to_float(request.form.get("latitude")),
                 _to_float(request.form.get("longitude")),
                 user["id"]),
            )
            conn.commit()
            flash("Profil mis à jour.", "success")
        finally:
            conn.close()
        return redirect(url_for("profile"))

    return render_template("profile.html", user=user)


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@app.route("/artisans")
@login_required
def artisans_page():
    user = get_current_user()
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    zone = request.args.get("zone", "").strip()

    sql = (
        "SELECT id, full_name AS nom, profession AS metier, city,"
        " hourly_rate, latitude, longitude FROM users"
        " WHERE role = 'artisan'")
    params = []

    if query:
        sql += (
            " AND (full_name LIKE ? OR profession LIKE ? OR city LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like, like])

    if category:
        sql += " AND profession LIKE ?"
        params.append(f"%{category}%")

    if zone:
        sql += " AND city LIKE ?"
        params.append(f"%{zone}%")

    sql += " ORDER BY full_name"

    conn = get_db_connection()
    try:
        artisans = conn.execute(sql, params).fetchall()
        active_requests = {}
        if user["role"] == "client":
            rows = conn.execute(
                "SELECT id, artisan_id FROM requests WHERE client_id = ?"
                " AND artisan_id IS NOT NULL AND status != 'pending'"
                " ORDER BY updated_at DESC", (user["id"],)).fetchall()
            active_requests = {r["artisan_id"]: r["id"] for r in rows}
    finally:
        conn.close()
    return render_template("artisans.html", artisans=artisans, user=user,
                           active_requests=active_requests,
                           query=query, category=category, zone=zone)


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
            "SELECT id FROM requests WHERE client_id = ? AND artisan_id = ?"
            " AND status IN ('assigned', 'quote_proposed', 'quote_accepted')"
            " ORDER BY updated_at DESC LIMIT 1",
            (user["id"], artisan_id)).fetchone()
    finally:
        conn.close()

    if req:
        return redirect(url_for("request_detail", request_id=req["id"]))

    flash("Aucun contrat actif avec ce technicien. Créez d'abord une demande "
          "pour démarrer une conversation.", "info")
    return redirect(url_for("request_new"))


@app.route("/artisans/<int:artisan_id>", methods=["GET", "POST"])
def artisan_detail(artisan_id):
    user = get_current_user()

    if request.method == "POST" and not user:
        return redirect(url_for("login"))

    if request.method == "POST" and user["role"] != "client":
        flash("Cette action est reservee aux clients.", "error")
        return redirect(url_for("artisans_page"))

    conn = get_db_connection()
    try:
        artisan = conn.execute(
            "SELECT * FROM users WHERE id = ? AND role = 'artisan'",
            (artisan_id,)).fetchone()
        if not artisan:
            flash("Technicien introuvable.", "error")
            return redirect(url_for("artisans_page"))

        # Avis
        reviews = conn.execute(
            "SELECT r.id, r.rating, r.comment, r.created_at, u.full_name AS client_name"
            " FROM reviews r JOIN users u ON u.id = r.client_id"
            " WHERE r.artisan_id = ? ORDER BY r.created_at DESC",
            (artisan_id,)).fetchall()
        review_stats = conn.execute(
            "SELECT COALESCE(AVG(rating), 0) AS avg_rating, COUNT(*) AS count"
            " FROM reviews WHERE artisan_id = ?",
            (artisan_id,)).fetchone()

        # Interventions realisees (status completed)
        completed = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND status = 'completed'",
            (artisan_id,)).fetchone()["n"]

        # Distance approximative
        distance = None
        client_lat = float(user["latitude"]) if user and user.get("latitude") else session.get("client_lat")
        client_lon = float(user["longitude"]) if user and user.get("longitude") else session.get("client_lon")
        if client_lat and client_lon and artisan["latitude"] and artisan["longitude"]:
            distance = calculate_distance(
                client_lat, client_lon,
                float(artisan["latitude"]), float(artisan["longitude"]))

        # Conversation client - FixPro pour ce technicien
        chat_messages = []
        ticket_id = None
        if user:
            ticket = conn.execute(
                "SELECT id FROM admin_tickets"
                " WHERE client_id = ? AND artisan_id = ?"
                " ORDER BY created_at DESC LIMIT 1",
                (user["id"], artisan_id)).fetchone()
            if ticket:
                ticket_id = ticket["id"]
                chat_messages = conn.execute(
                    "SELECT m.*, u.full_name AS sender_name"
                    " FROM admin_messages m JOIN users u ON u.id = m.sender_id"
                    " WHERE m.ticket_id = ? ORDER BY m.created_at ASC",
                    (ticket_id,)).fetchall()

        # Le client peut-il laisser un avis ?
        can_review = False
        review_request_id = None
        if user:
            req = conn.execute(
                "SELECT id FROM requests"
                " WHERE client_id = ? AND artisan_id = ? AND status = 'completed'"
                " AND id NOT IN (SELECT request_id FROM reviews WHERE client_id = ?)"
                " ORDER BY updated_at DESC LIMIT 1",
                (user["id"], artisan_id, user["id"])).fetchone()
            if req:
                can_review = True
                review_request_id = req["id"]

        if request.method == "POST":
            action = request.form.get("action")

            if action == "chat":
                content = (request.form.get("content") or "").strip()
                if not content:
                    return redirect(url_for("artisan_detail", artisan_id=artisan_id))

                # Cree le ticket s'il n'existe pas encore
                if not ticket_id:
                    result = conn.execute(
                        "INSERT INTO admin_tickets (client_id, artisan_id, subject, message, status)"
                        " VALUES (?, ?, ?, ?, 'open')",
                        (user["id"], artisan_id,
                         f"Concerne {artisan['full_name']}",
                         f"Conversation demarree pour {artisan['full_name']}."))
                    conn.commit()
                    ticket_id = result.lastrowid

                    # Message d'accueil de FixPro
                    fixpro = conn.execute(
                        "SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
                    sender_id = fixpro["id"] if fixpro else user["id"]
                    conn.execute(
                        "INSERT INTO admin_messages (ticket_id, sender_id, content)"
                        " VALUES (?, ?, ?)",
                        (ticket_id, sender_id,
                         f"Bienvenue sur FixPro. Comment puis-je vous aider avec {artisan['full_name']} ?"))
                    conn.commit()

                conn.execute(
                    "INSERT INTO admin_messages (ticket_id, sender_id, content)"
                    " VALUES (?, ?, ?)",
                    (ticket_id, user["id"], content))
                conn.execute(
                    "UPDATE admin_tickets SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (ticket_id,))
                conn.commit()

                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"ok": True})
                return redirect(url_for("artisan_detail", artisan_id=artisan_id))

            if action == "request":
                title = (request.form.get("title") or "").strip()
                description = (request.form.get("description") or "").strip()
                address = (request.form.get("address") or "").strip()
                date_time = (request.form.get("date_time") or "").strip()
                if not title or not description:
                    flash("Veuillez remplir le service et la description.", "error")
                    return redirect(url_for("artisan_detail", artisan_id=artisan_id))
                full_desc = description
                if date_time:
                    full_desc += f"\n\nDate/heure souhaitée : {date_time}"
                if address:
                    full_desc += f"\n\nAdresse : {address}"
                result = conn.execute(
                    "INSERT INTO requests"
                    " (client_id, artisan_id, title, description, category, address, status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, 'pending', datetime('now'), datetime('now'))",
                    (user["id"], artisan_id, title, full_desc,
                     artisan["profession"] or "Autre", address))
                conn.commit()
                flash("Demande d'intervention créée. Le technicien en sera informé.", "success")
                return redirect(url_for("request_detail", request_id=result.lastrowid))

            if action == "review" and can_review:
                rating = request.form.get("rating")
                comment = (request.form.get("comment") or "").strip()
                try:
                    rating_int = int(rating)
                    if not 1 <= rating_int <= 5:
                        raise ValueError
                except (TypeError, ValueError):
                    flash("Veuillez sélectionner une note entre 1 et 5.", "error")
                    return redirect(url_for("artisan_detail", artisan_id=artisan_id))
                conn.execute(
                    "INSERT INTO reviews (request_id, client_id, artisan_id, rating, comment)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (review_request_id, user["id"], artisan_id, rating_int, comment))
                conn.commit()
                flash("Avis enregistré. Merci pour votre retour.", "success")
                return redirect(url_for("artisan_detail", artisan_id=artisan_id))
    finally:
        conn.close()

    return render_template("artisan_detail.html",
                           user=user,
                           artisan=artisan,
                           reviews=reviews,
                           review_stats=review_stats,
                           completed=completed,
                           distance=distance,
                           can_review=can_review,
                           ticket_id=ticket_id)


@app.route("/artisans/<int:artisan_id>/location", methods=["POST"])
def artisan_location(artisan_id):
    """Recoit la position GPS du client et la stocke en session."""
    try:
        data = request.get_json(silent=True) or {}
        lat = data.get("lat")
        lon = data.get("lon")
        if lat is not None and lon is not None:
            session["client_lat"] = float(lat)
            session["client_lon"] = float(lon)
            return jsonify({"ok": True, "redirect": url_for("artisan_detail", artisan_id=artisan_id)})
    except (TypeError, ValueError):
        pass
    return jsonify({"ok": False}), 400


@app.route("/conversations")
@login_required
def conversations():
    user = get_current_user()
    conn = get_db_connection()
    try:
        if user["role"] == "artisan":
            rows = conn.execute(
                "SELECT r.*, u.full_name AS client_name FROM requests r"
                " JOIN users u ON u.id = r.client_id"
                " WHERE r.artisan_id = ? ORDER BY r.updated_at DESC",
                (user["id"],)).fetchall()
        else:
            rows = conn.execute(
                "SELECT r.*, u.full_name AS artisan_name FROM requests r"
                " LEFT JOIN users u ON u.id = r.artisan_id"
                " WHERE r.client_id = ? ORDER BY r.updated_at DESC",
                (user["id"],)).fetchall()

        threads = [
            {
                "request": row,
                "last_message": conn.execute(
                    "SELECT content, sender_id, created_at FROM messages"
                    " WHERE request_id = ? ORDER BY created_at DESC LIMIT 1",
                    (row["id"],)).fetchone(),
            }
            for row in rows
        ]
    finally:
        conn.close()
    return render_template("conversations.html", conversations=threads, user=user)


@app.route("/notifications")
@login_required
def notifications():
    """Liste les notifications du client (provisoire, sans table dediee)."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, status, updated_at FROM requests"
            " WHERE client_id = ? ORDER BY updated_at DESC LIMIT 10",
            (user["id"],)).fetchall()
    finally:
        conn.close()
    return render_template("notifications.html", user=user, notifications=rows)


# ---------------------------------------------------------------------------
# Demandes d'intervention
# ---------------------------------------------------------------------------

@app.route("/requests")
@login_required
def requests_list():
    user = get_current_user()
    conn = get_db_connection()
    try:
        if user["role"] == "artisan":
            rows = conn.execute(
                "SELECT * FROM requests WHERE artisan_id = ? OR status = 'pending'"
                " ORDER BY created_at DESC", (user["id"],)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM requests WHERE client_id = ?"
                " ORDER BY created_at DESC", (user["id"],)).fetchall()
    finally:
        conn.close()
    return render_template("requests.html", requests=rows, user=user)


@app.route("/export/requests")
@login_required
def export_requests():
    """Exporte les demandes du client en CSV."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, category, status, budget, created_at"
            " FROM requests WHERE client_id = ? ORDER BY created_at DESC",
            (user["id"],)).fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Titre", "Categorie", "Statut", "Budget", "Date"])
    for row in rows:
        writer.writerow([row["id"], row["title"], row["category"],
                         row["status"], row["budget"], row["created_at"]])

    response = app.make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=demandes_fixpro.csv"
    return response


@app.route("/requests/new", methods=["GET", "POST"])
@login_required
def request_new():
    user = get_current_user()
    conn = get_db_connection()
    try:
        categories = conn.execute(
            "SELECT * FROM service_categories ORDER BY name").fetchall()

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "").strip()

            if not title or not description:
                flash("Le titre et la description sont obligatoires.", "error")
                return redirect(url_for("request_new"))

            category_row = conn.execute(
                "SELECT diagnostic_price FROM service_categories WHERE name = ?",
                (category,)).fetchone()

            conn.execute(
                "INSERT INTO requests (client_id, title, description, category,"
                " address, photo_url, diagnostic_price, budget, status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
                (user["id"], title, description, category,
                 request.form.get("address", "").strip(),
                 request.form.get("photo_url", "").strip(),
                 float(category_row["diagnostic_price"]) if category_row else 0,
                 _to_float(request.form.get("budget"))),
            )
            conn.commit()
            flash("Demande d'intervention créée. Un artisan pourra maintenant "
                  "la prendre en charge.", "success")
            return redirect(url_for("requests_list"))
    finally:
        conn.close()

    return render_template("request_form.html", categories=categories, user=user)


@app.route("/requests/<int:request_id>", methods=["GET", "POST"])
@login_required
def request_detail(request_id):
    user = get_current_user()
    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req:
            flash("Demande introuvable.", "error")
            return redirect(url_for("requests_list"))

        if not can_access_request(user, req):
            flash("Vous n'êtes pas autorisé à voir cette intervention.", "error")
            return redirect(url_for("requests_list"))

        if request.method == "POST":
            content = request.form.get("message", "").strip()
            if content:
                if is_prohibited_message(content):
                    flash("Message bloqué : vous ne pouvez pas partager de "
                          "coordonnées personnelles ou demander un contact en "
                          "dehors de la plateforme.", "error")
                else:
                    conn.execute(
                        "INSERT INTO messages (request_id, sender_id, content)"
                        " VALUES (?, ?, ?)", (request_id, user["id"], content))
                    conn.commit()
                    flash("Message envoyé.", "success")
            return redirect(url_for("request_detail", request_id=request_id))

        client = conn.execute(
            "SELECT * FROM users WHERE id = ?", (req["client_id"],)).fetchone()
        artisan = conn.execute(
            "SELECT * FROM users WHERE id = ?", (req["artisan_id"],)
        ).fetchone() if req["artisan_id"] else None
        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name FROM messages m"
            " JOIN users u ON u.id = m.sender_id"
            " WHERE m.request_id = ? ORDER BY m.created_at ASC",
            (request_id,)).fetchall()
        payments = conn.execute(
            "SELECT * FROM payments WHERE request_id = ?"
            " ORDER BY created_at DESC", (request_id,)).fetchall()
    finally:
        conn.close()

    return render_template("request_detail.html", request_item=req,
                           client=client, artisan=artisan, messages=messages,
                           payments=payments, user=user,
                           payment_method_label=payment_method_label)


@app.route("/requests/<int:request_id>/accept", methods=["POST"])
@login_required
def accept_request(request_id):
    user = get_current_user()
    if user["role"] != "artisan":
        flash("Seuls les artisans peuvent accepter une demande.", "error")
        return redirect(url_for("requests_list"))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["status"] != "pending":
            flash("Cette demande n'est plus disponible.", "error")
            return redirect(url_for("requests_list"))

        conn.execute(
            "UPDATE requests SET artisan_id = ?, status = 'assigned',"
            " updated_at = ? WHERE id = ? AND status = 'pending'",
            (user["id"], now_iso(), request_id))
        conn.commit()
        flash("Demande attribuée. Proposez un devis afin que le client puisse "
              "l'accepter.", "success")
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
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["artisan_id"] != user["id"]:
            flash("Accès refusé.", "error")
            return redirect(url_for("requests_list"))
        if req["status"] not in ("assigned", "quote_rejected", "quote_proposed"):
            flash("Impossible de proposer un devis pour cette demande.", "error")
            return redirect(url_for("request_detail", request_id=request_id))

        amount = _to_float(request.form.get("quote_amount"))
        description = request.form.get("quote_description", "").strip()
        if amount <= 0 or not description:
            flash("Le devis doit inclure un montant valide et une description.",
                  "error")
            return redirect(url_for("request_detail", request_id=request_id))

        conn.execute(
            "UPDATE requests SET quote_amount = ?, quote_description = ?,"
            " quote_status = 'pending', quote_proposed_at = ?,"
            " status = 'quote_proposed', updated_at = ? WHERE id = ?",
            (amount, description, now_iso(), now_iso(), request_id))
        conn.commit()
        flash("Devis proposé. Le client doit maintenant l'accepter.", "success")
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


def _decide_quote(request_id, accept):
    user = get_current_user()
    if user["role"] != "client":
        flash("Seul le client peut répondre au devis.", "error")
        return redirect(url_for("requests_list"))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["client_id"] != user["id"]:
            flash("Accès refusé.", "error")
            return redirect(url_for("requests_list"))
        if req["quote_status"] != "pending":
            flash("Aucun devis en attente.", "error")
            return redirect(url_for("request_detail", request_id=request_id))

        if accept:
            conn.execute(
                "UPDATE requests SET quote_status = 'accepted',"
                " status = 'quote_accepted', quote_approved_at = ?,"
                " updated_at = ? WHERE id = ?",
                (now_iso(), now_iso(), request_id))
            flash("Devis accepté. L'intervention est maintenant validée.",
                  "success")
        else:
            conn.execute(
                "UPDATE requests SET quote_status = 'rejected',"
                " status = 'quote_rejected', updated_at = ? WHERE id = ?",
                (now_iso(), request_id))
            flash("Devis rejeté. L'artisan peut en proposer un nouveau.",
                  "success")
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


@app.route("/requests/<int:request_id>/quote/accept", methods=["POST"])
@login_required
def accept_quote(request_id):
    return _decide_quote(request_id, accept=True)


@app.route("/requests/<int:request_id>/quote/reject", methods=["POST"])
@login_required
def reject_quote(request_id):
    return _decide_quote(request_id, accept=False)


@app.route("/requests/<int:request_id>/complete", methods=["POST"])
@login_required
def complete_request(request_id):
    user = get_current_user()
    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req:
            flash("Demande introuvable.", "error")
            return redirect(url_for("requests_list"))

        if user["id"] not in (req["client_id"], req["artisan_id"]):
            flash("Action non autorisée.", "error")
        else:
            conn.execute(
                "UPDATE requests SET status = 'completed', updated_at = ?"
                " WHERE id = ?", (now_iso(), request_id))
            conn.commit()
            flash("Intervention marquée comme terminée.", "success")
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


# ---------------------------------------------------------------------------
# Paiements
# ---------------------------------------------------------------------------

@app.route("/requests/<int:request_id>/payment")
@login_required
def payment_page(request_id):
    user = get_current_user()
    if user["role"] != "client":
        flash("Seuls les clients peuvent accéder à la page de paiement.", "error")
        return redirect(url_for("request_detail", request_id=request_id))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["client_id"] != user["id"]:
            flash("Vous n'avez pas accès à cette page de paiement.", "error")
            return redirect(url_for("requests_list"))
        if req["quote_status"] != "accepted":
            flash("Le paiement n'est disponible qu'une fois le devis accepté.",
                  "error")
            return redirect(url_for("request_detail", request_id=request_id))

        artisan = conn.execute(
            "SELECT id, full_name AS nom FROM users WHERE id = ?",
            (req["artisan_id"],)).fetchone() if req["artisan_id"] else None
        payments = conn.execute(
            "SELECT * FROM payments WHERE request_id = ?"
            " ORDER BY created_at DESC", (request_id,)).fetchall()
    finally:
        conn.close()

    return render_template("payment_page.html", request_item=req,
                           artisan=artisan, payments=payments, user=user,
                           payment_method_label=payment_method_label)


@app.route("/requests/<int:request_id>/payment/process", methods=["POST"])
@login_required
def process_payment(request_id):
    user = get_current_user()
    if user["role"] != "client":
        flash("Seuls les clients peuvent effectuer des paiements.", "error")
        return redirect(url_for("request_detail", request_id=request_id))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["client_id"] != user["id"]:
            flash("Accès refusé.", "error")
            return redirect(url_for("request_detail", request_id=request_id))

        amount = _to_float(request.form.get("amount"))
        method = request.form.get("method", "cash")
        payment_info = (request.form.get("payment_info") or "").strip()

        if amount <= 0:
            flash("Le montant doit être positif.", "error")
            return redirect(url_for("payment_page", request_id=request_id))
        if method not in PAYMENT_METHODS:
            flash("Moyen de paiement inconnu.", "error")
            return redirect(url_for("payment_page", request_id=request_id))

        reference = (request.form.get("reference") or "").strip()
        if not reference:
            reference = "FP-%s-%s" % (request_id, now_iso()[:19].replace("T", " ").replace(":", "").replace("-", ""))

        details = payment_info
        if method == "card" and payment_info:
            details = "Carte terminant par %s" % payment_info[-4:] if payment_info.isdigit() and len(payment_info) >= 4 else payment_info

        conn.execute(
            "INSERT INTO payments (request_id, amount, method, status,"
            " reference, details) VALUES (?, ?, ?, 'pending', ?, ?)",
            (request_id, amount, method, reference, details))
        conn.commit()
        flash("Paiement de %s GNF enregistré par %s. En attente de confirmation." %
              ("{:,}".format(int(amount)).replace(",", " "), payment_method_label(method)),
              "success")
    finally:
        conn.close()
    return redirect(url_for("payment_page", request_id=request_id))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/categories")
def api_categories():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, diagnostic_price FROM service_categories"
            " ORDER BY name").fetchall()
    finally:
        conn.close()
    return jsonify({"categories": rows})


@app.route("/api/messages/<int:request_id>")
@login_required
def api_messages(request_id):
    """Messages d'une intervention, interroges periodiquement par le client.

    Remplace les WebSockets, incompatibles avec l'execution serverless.
    """
    user = get_current_user()
    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or not can_access_request(user, req):
            return jsonify({"error": "Accès refusé"}), 403

        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name FROM messages m"
            " JOIN users u ON u.id = m.sender_id"
            " WHERE m.request_id = ? ORDER BY m.created_at ASC",
            (request_id,)).fetchall()
    finally:
        conn.close()

    return jsonify({"messages": [
        {
            "id": m["id"],
            "content": m["content"],
            "sender_id": m["sender_id"],
            "sender_name": m["sender_name"],
            "created_at": m["created_at"],
            "is_own": m["sender_id"] == user["id"],
        }
        for m in messages
    ]})


@app.route("/api/technicien/status", methods=["POST"])
@login_required
def api_technicien_status():
    """Met a jour le statut de disponibilite de l'artisan."""
    user = get_current_user()
    if not user or user["role"] != "artisan":
        return jsonify({"error": "Reserve aux techniciens."}), 403

    status = (request.form.get("status") or "").strip()
    if status not in ("en_ligne", "occupe", "hors_ligne"):
        return jsonify({"error": "Statut inconnu."}), 400

    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE users SET availability_status = ? WHERE id = ?",
            (status, user["id"]))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "status": status})


@app.route("/api/technicien/position", methods=["POST"])
@login_required
def api_technicien_position():
    """Recoit et stocke la position GPS en temps reel du technicien."""
    user = get_current_user()
    if not user or user["role"] != "artisan":
        return jsonify({"error": "Reserve aux techniciens."}), 403

    try:
        lat = float(request.form.get("lat") or "")
        lon = float(request.form.get("lon") or "")
    except (TypeError, ValueError):
        return jsonify({"error": "Coordonnees invalides."}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"error": "Coordonnees hors limites."}), 400

    conn = get_db_connection()
    try:
        artisan = conn.execute(
            "SELECT availability_status FROM users WHERE id = ?",
            (user["id"],)).fetchone()
        if not artisan or artisan["availability_status"] != "en_ligne":
            return jsonify({"ok": False,
                            "reason": "Statut non en ligne, position ignoree."}), 200

        conn.execute(
            "INSERT INTO technician_locations (technician_id, latitude, longitude)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT (technician_id) DO UPDATE SET"
            " latitude = excluded.latitude, longitude = excluded.longitude,"
            " updated_at = CURRENT_TIMESTAMP",
            (user["id"], lat, lon))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/technicien/<int:technician_id>/position")
def api_technicien_position_read(technician_id):
    """Renvoie la derniere position connue si le technicien est en ligne."""
    freshness = 180  # 3 minutes
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT l.latitude, l.longitude, l.updated_at, u.availability_status"
            " FROM technician_locations l"
            " JOIN users u ON u.id = l.technician_id"
            " WHERE l.technician_id = ?",
            (technician_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({"error": "Aucune position connue."}), 404

    if row["availability_status"] != "en_ligne":
        return jsonify({"error": "Technicien hors ligne."}), 404

    try:
        updated = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        updated = None

    if updated and (datetime.now(timezone.utc) - updated).total_seconds() > freshness:
        return jsonify({"error": "Position perimee."}), 404

    return jsonify({
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "updated_at": row["updated_at"],
    })


# ---------------------------------------------------------------------------
# Pages d'erreur
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    import sys, traceback
    exc_info = sys.exc_info()
    if exc_info[0]:
        message = "".join(traceback.format_exception(*exc_info))
    else:
        message = str(error)
    logger.exception("Erreur interne: %s", error)
    return render_template("500.html", message=message), 500


def _load_settings():
    """Charge les parametres stockes en base pour ecraser les variables d'environnement."""
    conn = get_db_connection()
    try:
        for row in conn.execute("SELECT key, value FROM settings").fetchall():
            if row["key"] == "FIXPRO_COMMISSION_RATE" and row["value"]:
                try:
                    app.config["FIXPRO_COMMISSION_RATE"] = float(row["value"])
                except ValueError:
                    pass
    finally:
        conn.close()


@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
@admin_required
@limiter.limit("60 per hour", methods=["POST"])
def admin_settings():
    """Parametres systeme modifiables par les admins."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        if request.method == "POST":
            new_rate = _to_float(request.form.get("commission_rate"), 0.10)
            if new_rate < 0 or new_rate > 1:
                flash("Le taux de commission doit etre entre 0 et 1.", "error")
            else:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    ("FIXPRO_COMMISSION_RATE", str(new_rate)))
                conn.commit()
                app.config["FIXPRO_COMMISSION_RATE"] = new_rate
                log_admin_action(user["id"], user["email"], "update_commission_rate",
                                 "settings", 0, f"Nouveau taux {new_rate}")
                flash("Taux de commission mis a jour.", "success")

        rate = app.config.get("FIXPRO_COMMISSION_RATE", 0.10)
    finally:
        conn.close()
    return render_template("admin_settings.html", user=user, commission_rate=rate)


if __name__ == "__main__":
    _load_settings()
    logger.info("Démarrage de FixPro (environnement: %s)",
                app.config.get("FLASK_ENV"))
    app.run(host=app.config["HOST"], port=app.config["PORT"],
            debug=app.config["DEBUG"])
