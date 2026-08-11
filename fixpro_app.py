"""FixPro - plateforme de mise en relation entre clients et artisans.

Application Flask unique, compatible :
  - execution locale sur SQLite
  - deploiement serverless sur Vercel avec une base Supabase (PostgreSQL)

Les acces a la base passent tous par le module `db`, ce qui permet
d'ecrire les requetes une seule fois pour les deux moteurs.
"""

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
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
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


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    role = request.form.get("role") if request.method == "POST" else request.args.get("role", "client")
    role = (role or "client").lower()
    if role not in ("client", "artisan"):
        role = "client"

    if request.method == "POST":
        password = request.form.get("password", "")

        if role == "client":
            # Inscription simplifiee pour le client : nom, prenom, telephone, ville.
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            full_name = f"{first_name} {last_name}".strip()
            phone = request.form.get("phone", "").strip()
            city = request.form.get("city", "").strip()

            if not first_name or not last_name or not phone or not city or not password:
                flash("Veuillez remplir tous les champs obligatoires.", "error")
                return redirect(url_for("register", role=role))
        else:
            # Inscription artisan simplifiee.
            civility = request.form.get("civility", "").strip()
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            full_name_legacy = request.form.get("full_name", "").strip()
            if first_name and last_name:
                full_name = f"{civility} {first_name} {last_name}".strip()
            else:
                full_name = full_name_legacy
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            city = request.form.get("city", "").strip()

            # Ajoute le prefixe guineen si absent.
            if phone and not phone.startswith("+"):
                phone = f"+224 {phone}"

            if not full_name or not email or not phone or not city:
                flash("Veuillez remplir tous les champs obligatoires.", "error")
                return redirect(url_for("register", role=role))

            try:
                validate_email(email, check_deliverability=False)
            except EmailNotValidError:
                flash("Format d'email invalide.", "error")
                return redirect(url_for("register", role=role))

            # Mot de passe genere automatiquement depuis le numero.
            if not password:
                password = phone.replace(" ", "").replace("+", "")

        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "error")
            return redirect(url_for("register", role=role))

        conn = get_db_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
            if existing:
                flash("Ce numéro de téléphone est déjà utilisé.", "error")
                return redirect(url_for("register", role=role))

            hourly_rate = _to_float(request.form.get("hourly_rate")) if role == "artisan" else 0
            email = request.form.get("email", "").strip().lower() if role == "artisan" else None

            try:
                if role == "artisan":
                    skills = ", ".join(request.form.getlist("skills"))
                    conn.execute(
                        "INSERT INTO users (email, phone, password_hash, role, full_name, civility,"
                        " company_name, profession, skills, mobility, insurance, insurance_policy,"
                        " bank_name, bank_account, city, bio, hourly_rate)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (email, phone, generate_password_hash(password), role,
                         full_name,
                         request.form.get("civility", "").strip(),
                         request.form.get("company_name", "").strip(),
                         request.form.get("profession", "").strip(),
                         skills,
                         request.form.get("mobility", "").strip(),
                         request.form.get("insurance", "").strip(),
                         request.form.get("insurance_policy", "").strip(),
                         request.form.get("bank_name", "").strip(),
                         request.form.get("bank_account", "").strip(),
                         city,
                         request.form.get("bio", "").strip(),
                         hourly_rate),
                    )
                else:
                    conn.execute(
                        "INSERT INTO users (email, phone, password_hash, role, full_name,"
                        " profession, city, bio, hourly_rate)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (email, phone, generate_password_hash(password), role, full_name,
                         request.form.get("profession", "").strip(),
                         city,
                         request.form.get("bio", "").strip(),
                         hourly_rate),
                    )
                conn.commit()
            except Exception as exc:  # pragma: no cover - aide au debug en production
                flash(f"Erreur lors de l'inscription : {exc}", "error")
                return redirect(url_for("register", role=role))

            # Recupere le compte nouvellement cree pour le connecter directement.
            new_user = conn.execute(
                "SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
            session.clear()
            session["user_id"] = new_user["id"]
            session.permanent = True
            flash("Bienvenue dans FixPro.", "success")

            if role == "client":
                return redirect(url_for("artisans_page"))
            # Les artisans passent en attente de validation manuelle.
            return redirect(url_for("artisan_pending"))
        finally:
            conn.close()

    if role == "artisan":
        title = "Créer un compte artisan"
        subtitle = "Recevez des demandes d'intervention et proposez vos devis."
        button_label = "S'inscrire en tant qu'artisan"
    else:
        title = "Créer un compte client"
        subtitle = "Trouvez un artisan en 30 secondes."
        button_label = "S'inscrire en 30 secondes"

    return render_template("register.html", role=role, title=title,
                           subtitle=subtitle, button_label=button_label)


@app.route("/artisan-pending")
def artisan_pending():
    """Page d'attente affichee aux artisans non valides."""
    return render_template("pending.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    """Tableau de bord admin avec les principales statistiques."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_artisans"))
    conn = get_db_connection()
    try:
        clients = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'client'").fetchone()["n"]
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'artisan' AND is_verified = 0").fetchone()["n"]
        verified = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'artisan' AND is_verified = 1").fetchone()["n"]
        requests = conn.execute(
            "SELECT COUNT(*) AS n FROM requests").fetchone()["n"]
        return render_template("admin_dashboard.html", stats={
            "clients": clients,
            "pending_artisans": pending,
            "verified_artisans": verified,
            "requests": requests,
        })
    finally:
        conn.close()


@app.route("/admin/artisans", methods=["GET", "POST"])
@limiter.limit("60 per hour", methods=["POST"])
def admin_artisans():
    """Interface admin pour valider ou refuser les artisans."""
    if not session.get("admin_logged_in"):
        if request.method == "POST" and request.form.get("admin_password"):
            if request.form.get("admin_password") == app.config.get("ADMIN_PASSWORD"):
                session["admin_logged_in"] = True
                return redirect(url_for("admin_dashboard"))
            else:
                flash("Mot de passe incorrect.", "error")
                return redirect(url_for("admin_artisans"))
        else:
            return render_template("admin_login.html")

    conn = get_db_connection()
    try:
        if request.method == "POST" and request.form.get("action"):
            artisan_id = request.form.get("artisan_id")
            action = request.form.get("action")
            if action == "verify":
                conn.execute(
                    "UPDATE users SET is_verified = 1 WHERE id = ?", (artisan_id,))
                conn.commit()
                flash("Artisan validé.", "success")
            elif action == "reject":
                conn.execute("DELETE FROM users WHERE id = ?", (artisan_id,))
                conn.commit()
                flash("Artisan refusé.", "success")
            return redirect(url_for("admin_artisans"))

        artisans = conn.execute(
            "SELECT * FROM users WHERE role = 'artisan' AND is_verified = 0"
            " ORDER BY created_at DESC").fetchall()
        verified = conn.execute(
            "SELECT * FROM users WHERE role = 'artisan' AND is_verified = 1"
            " ORDER BY created_at DESC").fetchall()
        return render_template("admin_artisans.html", artisans=artisans,
                               verified=verified)
    finally:
        conn.close()


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_artisans"))


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
    conn = get_db_connection()
    try:
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

        # Artisans a proximite (tous les artisans verifies pour l'instant)
        artisans = conn.execute(
            "SELECT id, full_name, profession, city, hourly_rate, is_verified"
            " FROM users WHERE role = 'artisan' AND is_verified = 1"
            " ORDER BY full_name LIMIT 5").fetchall()

        # Statistiques
        rows = conn.execute(
            "SELECT status FROM requests WHERE client_id = ?",
            (user["id"],)).fetchall()
        paid = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments p"
            " JOIN requests r ON r.id = p.request_id"
            " WHERE p.status = 'completed' AND r.client_id = ?",
            (user["id"],)).fetchone()

        # Active requests (pending, assigned, in_progress)
        active_requests = sum(1 for r in rows if r["status"] in ("pending", "assigned", "in_progress"))

        # Average rating given by client (if reviews table missing, default 0)
        try:
            avg = conn.execute(
                "SELECT COALESCE(AVG(rating), 0) AS m FROM reviews WHERE client_id = ?",
                (user["id"],)).fetchone()
            avg_rating = round(float(avg["m"]) if avg and avg["m"] is not None else 0, 1)
        except Exception:
            avg_rating = 0.0

        stats = {
            "active_requests": active_requests,
            "completed": sum(1 for r in rows if r["status"] == "completed"),
            "total_spent": float(paid["total"] or 0),
            "month_spent": 0.0,
            "avg_rating": avg_rating,
        }
    except Exception as exc:
        import traceback
        traceback.print_exc()
        flash(f"Erreur dashboard : {exc}", "error")
        return render_template("dashboard_client.html", user=user,
                               stats={"active_requests": 0, "completed": 0, "total_spent": 0.0, "month_spent": 0.0, "avg_rating": 0.0},
                               categories=categories if 'categories' in locals() else [],
                               artisan_counts=artisan_counts if 'artisan_counts' in locals() else {},
                               artisans=artisans if 'artisans' in locals() else [])
    finally:
        conn.close()

    return render_template("dashboard_client.html", user=user, stats=stats,
                           categories=categories,
                           artisan_counts=artisan_counts,
                           artisans=artisans)


@app.route("/mobile_dashboard")
@login_required
def mobile_dashboard():
    return render_template("mobile_dashboard.html", user=get_current_user())


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
        if amount <= 0:
            flash("Le montant doit être positif.", "error")
            return redirect(url_for("payment_page", request_id=request_id))
        if method not in PAYMENT_METHODS:
            flash("Moyen de paiement inconnu.", "error")
            return redirect(url_for("payment_page", request_id=request_id))

        conn.execute(
            "INSERT INTO payments (request_id, amount, method, status,"
            " reference, details) VALUES (?, ?, ?, 'pending', ?, ?)",
            (request_id, amount, method,
             request.form.get("reference", "").strip(),
             "Paiement %s" % payment_method_label(method)))
        conn.commit()
        flash("Paiement enregistré. En attente de confirmation.", "success")
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


if __name__ == "__main__":
    logger.info("Démarrage de FixPro (environnement: %s)",
                app.config.get("FLASK_ENV"))
    app.run(host=app.config["HOST"], port=app.config["PORT"],
            debug=app.config["DEBUG"])
