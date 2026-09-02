"""FixPro - plateforme de mise en relation entre clients et artisans.

Application Flask unique, compatible :
  - execution locale sur SQLite
  - deploiement serverless sur Vercel avec une base Supabase (PostgreSQL)

Les acces a la base passent tous par le module `db`, ce qui permet
d'ecrire les requetes une seule fois pour les deux moteurs.
"""

import base64
import csv
import io
import json
import math
import re
import requests
import urllib.parse
import urllib.request
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from functools import wraps

from authlib.integrations.flask_client import OAuth
from abc import ABC, abstractmethod
from email_validator import EmailNotValidError, validate_email
from flask import (Flask, flash, g, jsonify, make_response, redirect,
                   render_template, request, session, url_for)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import ai_service
import db
import storage
from config import BASE_DIR, get_config, setup_logging
from dotenv import dotenv_values

config = get_config()
ADMIN_DEMO = False
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.from_object(config)
# Cache navigateur/CDN pour les fichiers de /static (CSS, JS, images).
# N'affecte que les reponses servies par Flask pour /static : aucune page
# dynamique n'est mise en cache.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(days=30)
_dotenv = dotenv_values(BASE_DIR / ".env")
if _dotenv.get("DEV_ROLE"):
    app.config["DEV_ROLE"] = _dotenv.get("DEV_ROLE").lower()

logger = setup_logging(app)
csrf = CSRFProtect(app)

# CORS autorise le dashboard Next.js. En dev, localhost. En prod, domaine FixPro.
_admin_dashboard = app.config.get("ADMIN_DASHBOARD_URL", "http://localhost:3000").rstrip("/")
_cors_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3006",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3006",
    _admin_dashboard,
]
if app.config.get("FLASK_ENV", "development") != "development":
    _cors_origins = [_admin_dashboard]
CORS(app, resources={r"/api/admin/*": {"origins": _cors_origins}})


@app.template_filter('dt_hm')
def _format_dt_hm(value):
    """Affiche l'heure HH:MM d'un timestamp ISO."""
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%H:%M')
    s = str(value)
    if 'T' in s:
        return s[11:16]
    if len(s) >= 16:
        return s[11:16]
    return s


@app.template_filter('date_long_fr')
def _format_date_long_fr(value):
    """Affiche une date au format '30 sept. 2026'."""
    if not value:
        return ''
    mois = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.',
            'août', 'sept.', 'oct.', 'nov.', 'déc.']
    try:
        if hasattr(value, 'year'):
            dt = value
        else:
            dt = datetime.strptime(str(value).replace('T', ' ')[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        try:
            dt = datetime.strptime(str(value)[:10], '%Y-%m-%d')
        except (ValueError, TypeError):
            return str(value)
    return "%d %s %d" % (dt.day, mois[dt.month - 1], dt.year)


@app.template_filter('time_ago')
def _format_time_ago(value):
    """Duree relative en francais : 'Il y a 2 h', 'Il y a 3 j'..."""
    if not value:
        return ''
    try:
        if hasattr(value, 'year'):
            dt = value
        else:
            s = str(value).replace('T', ' ')[:19]
            dt = datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return str(value)
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "A l'instant"
    if secs < 3600:
        return "Il y a %d min" % (secs // 60)
    if secs < 86400:
        return "Il y a %d h" % (secs // 3600)
    if secs < 2592000:
        return "Il y a %d j" % (secs // 86400)
    if secs < 31536000:
        return "Il y a %d mois" % (secs // 2592000)
    return "Il y a %d an%s" % (secs // 31536000, 's' if secs // 31536000 > 1 else '')


@app.template_filter('gnf')
def _format_gnf(value):
    """Formate un entier en 'GNF 1 234 567'."""
    try:
        n = int(value or 0)
    except (ValueError, TypeError):
        n = 0
    return "GNF " + format(n, ',').replace(',', ' ')


_ratelimit_storage = app.config.get("RATELIMIT_STORAGE_URI", "memory://")
if (_ratelimit_storage == "memory://"
        and app.config.get("FLASK_ENV") == "production"):
    logger.warning(
        "Rate limiting en memoire : inefficace en serverless. "
        "Definissez RATELIMIT_STORAGE_URI (Redis/Upstash) en production.")

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["400 per day", "100 per hour"],
    storage_uri=_ratelimit_storage,
)

# Coordonnees approximatives des quartiers/zones de Conakry utilisees
# pour la geolocalisation des artisans a l'inscription.
_ARTISAN_GEOCODE = {
    "conakry": (9.6412, -13.5784),
    "kaloum": (9.5077, -13.7114),
    "dixinn": (9.5700, -13.6778),
    "matam": (9.6472, -13.6333),
    "matam centre": (9.6472, -13.6333),
    "nongo": (9.6200, -13.5800),
    "tombo": (9.4289, -13.5833),
    "cite chemin de fer": (9.5186, -13.7075),
    "bambeto": (9.6500, -13.5333),
    "enco": (9.6500, -13.5500),
    "encoville": (9.6500, -13.5500),
    "kaporo": (9.6678, -13.5569),
    "sonfonia": (9.6400, -13.5100),
    "yimbaya": (9.6400, -13.5000),
    "mambeto": (9.6400, -13.5300),
    "kagbaneh": (9.6300, -13.5400),
    "taouyah": (9.6100, -13.6000),
}

# Quartiers proposes au client sur l'ecran de localisation (choix manuel).
# Coordonnees approximatives FIGEES ici : ne jamais geocoder ces noms via un
# service externe (ex : "Madina" -> Medine, Arabie Saoudite). Ordre = du
# centre-ville vers la peripherie.
_CONAKRY_QUARTIERS = {
    "Kaloum": (9.5092, -13.7122),
    "Almamya": (9.5122, -13.7062),
    "Sandervalia": (9.5140, -13.7100),
    "Coronthie": (9.5050, -13.7150),
    "Boulbinet": (9.5020, -13.7080),
    "Tombo": (9.4289, -13.5833),
    "Dixinn": (9.5450, -13.6780),
    "Camayenne": (9.5350, -13.6850),
    "Belle-Vue": (9.5400, -13.6720),
    "Landreah": (9.5520, -13.6670),
    "Matam": (9.5300, -13.6500),
    "Bonfi": (9.5350, -13.6600),
    "Madina": (9.5380, -13.6670),
    "Coleah": (9.5450, -13.6550),
    "Hamdallaye": (9.5750, -13.6350),
    "Ratoma": (9.6150, -13.6100),
    "Taouyah": (9.6050, -13.6120),
    "Kipe": (9.6200, -13.6100),
    "Nongo": (9.6350, -13.6000),
    "Kaporo": (9.6500, -13.5900),
    "Lambanyi": (9.6400, -13.6000),
    "Sonfonia": (9.6600, -13.5750),
    "Kobaya": (9.6550, -13.5850),
    "Matoto": (9.5850, -13.6150),
    "Gbessia": (9.5750, -13.6050),
    "Yimbaya": (9.6000, -13.5900),
    "Dabompa": (9.6150, -13.5600),
    "Tanene": (9.6300, -13.5600),
    "Kissosso": (9.6100, -13.5750),
    "Simbaya": (9.6050, -13.5600),
    "Bambeto": (9.6150, -13.6150),
    "Cosa": (9.6050, -13.6200),
    "Enta": (9.5900, -13.6000),
    "Wanindara": (9.6400, -13.6150),
    "Sangoyah": (9.5900, -13.6200),
}


def _nearest_zone(lat, lon, max_km=15.0):
    """Retourne le quartier connu le plus proche d'une position GPS.

    Si aucun quartier connu n'est dans le rayon (15 km par defaut),
    la position est hors de Conakry : on ne retombe pas sur un quartier
    fixe de Conakry.
    """
    if not _is_valid_coordinate(lat, lon):
        return None
    best_name, best_d = None, float("inf")
    for name, (zlat, zlon) in _ARTISAN_GEOCODE.items():
        d = _haversine(lat, lon, zlat, zlon)
        if d < best_d:
            best_d = d
            best_name = name
    return best_name.capitalize() if (best_name and best_d <= max_km) else None


def _zone_coordinate(zone_name):
    """Retourne les coordonnees (lat, lon) d'un quartier connu par son nom."""
    if not zone_name:
        return None
    key = zone_name.strip().lower()
    return _ARTISAN_GEOCODE.get(key)


_NOMINATIM_CACHE = {}
_NOMINATIM_CACHE_MAX = 512


def _nominatim_request(url):
    """Appelle Nominatim avec un User-Agent identifiable.

    Les reponses sont mises en cache en memoire : les memes coordonnees ou
    requetes reviennent souvent et l'usage intensif de Nominatim est contraire
    a ses conditions d'utilisation.
    """
    if url in _NOMINATIM_CACHE:
        return _NOMINATIM_CACHE[url]

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FixPro/1.0 (contact@fixproguinea.vercel.app)",
            "Accept-Language": "fr",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Erreur Nominatim : %s", e)
        return None

    if len(_NOMINATIM_CACHE) >= _NOMINATIM_CACHE_MAX:
        _NOMINATIM_CACHE.clear()
    _NOMINATIM_CACHE[url] = data
    return data


def _extract_place_name(data):
    """Extrait un libelle lisible (ville, quartier) depuis une reponse Nominatim."""
    if not data or not isinstance(data, dict):
        return None
    addr = data.get("address") or {}
    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("suburb") or addr.get("hamlet") or addr.get("county")
    country = addr.get("country")
    if city and country:
        return f"{city}, {country}"
    return city or data.get("display_name")


def _reverse_geocode(lat, lon):
    """Retourne le nom d'un lieu a partir de coordonnees GPS."""
    if not _is_valid_coordinate(lat, lon):
        return None
    params = urllib.parse.urlencode({
        "lat": lat,
        "lon": lon,
        "format": "json",
        "addressdetails": 1,
        "accept-language": "fr",
        "zoom": 18,
    })
    data = _nominatim_request(f"https://nominatim.openstreetmap.org/reverse?{params}")
    return _extract_place_name(data)


def _geocode_query(query):
    """Geocode un nom de lieu. Retourne (lat, lon, nom) ou (None, None, None)."""
    if not query or not query.strip():
        return None, None, None
    params = urllib.parse.urlencode({
        "q": query.strip(),
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
        "accept-language": "fr",
    })
    data = _nominatim_request(f"https://nominatim.openstreetmap.org/search?{params}")
    if not data or not isinstance(data, list) or not data:
        return None, None, None
    result = data[0]
    try:
        lat = float(result.get("lat"))
        lon = float(result.get("lon"))
    except (TypeError, ValueError):
        return None, None, None
    return lat, lon, _extract_place_name(result)


def _split_zones(zones_str):
    """Decoupe une liste de zones en noms propres uniques."""
    if not zones_str:
        return []
    raw = re.split(r"[,;/]", str(zones_str))
    seen = set()
    zones = []
    for z in raw:
        z = z.strip()
        if z and z.lower() not in seen:
            seen.add(z.lower())
            zones.append(z)
    return zones


oauth = OAuth(app)


@app.before_request
def check_artisan_verification():
    """Redirige les artisans non verifies vers la page d'attente."""
    if not app.config.get("TECH_VERIFICATION_ENABLED"):
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None
    public_endpoints = {
        "artisan_pending", "technician_verification", "technician_documents_resubmit",
        "logout", "static", "login", "register",
        "register_artisan", "client_signup", "google_signup", "google_callback",
        "complete_profile", "contact_artisan", "health", "health-db", "index", "contact",
        "lia", "api_lia_chat",
    }
    if request.endpoint in public_endpoints or request.endpoint is None:
        return None
    if getattr(g, "_artisan_verification_done", False):
        return g._artisan_verification_result
    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT role, is_verified FROM users WHERE id = ?", (user_id,)).fetchone()
        if user and _is_technician(user) and not user["is_verified"]:
            result = redirect(url_for("artisan_pending"))
        else:
            result = None
    finally:
        conn.close()
    g._artisan_verification_done = True
    g._artisan_verification_result = result
    return result


_google_client_cache = []


def _get_google_client():
    """Enregistre le client Google OAuth si les identifiants sont presents.

    Le client est memorise apres le premier appel : `oauth.register` refait
    sinon un appel reseau vers la metadata OpenID de Google a chaque fois.
    """
    if _google_client_cache:
        return _google_client_cache[0]

    client_id = app.config.get("GOOGLE_CLIENT_ID")
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = app.config.get("GOOGLE_REDIRECT_URI")

    if not client_id or not client_secret or not redirect_uri:
        return None

    try:
        client = oauth.register(
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

    _google_client_cache.append(client)
    return client


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _geocode_zone(city, quartier):
    """Retourne (latitude, longitude) approximative d'une zone artisan.

    Cherche d'abord le quartier, puis la ville. Si aucun trouve,
    renvoie (None, None) pour ne pas inventer de fausses coordonnees.
    """
    key = (quartier or "").strip().lower()
    if key and key in _ARTISAN_GEOCODE:
        return _ARTISAN_GEOCODE[key]

    city_key = (city or "").strip().lower()
    if city_key and city_key in _ARTISAN_GEOCODE:
        return _ARTISAN_GEOCODE[city_key]

    return None, None


def _is_valid_coordinate(lat, lon):
    """Exclut les coordonnees non renseignees (0, 0) par defaut."""
    if lat is None or lon is None:
        return False
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    return not (abs(lat) < 0.01 and abs(lon) < 0.01)


def get_db_connection():
    """Ouvre une connexion vers la base configuree pour cet environnement."""
    return db.connect(
        database_url=app.config.get("DATABASE_URL", ""),
        sqlite_path=app.config.get("SQLITE_PATH", "fixpro.db"),
    )


# ---------------------------------------------------------------------------
# Securite et helpers
# ---------------------------------------------------------------------------

# Sources externes reellement utilisees par les gabarits (polices Google,
# Leaflet via unpkg, Chart.js via jsDelivr, tuiles OpenStreetMap en images).
_CSP = "; ".join([
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    "form-action 'self'",
    "img-src 'self' data: https:",
    "font-src 'self' https://fonts.gstatic.com data:",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
    "connect-src 'self'",
])


@app.after_request
def add_security_headers(response):
    """Ajoute les en-tetes de securite recommandes a chaque reponse."""
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # X-XSS-Protection est obsolete et peut introduire des failles : desactive.
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers.setdefault("Content-Security-Policy", _CSP)
    if not app.config.get("DEBUG"):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains")
    return response


def _bearer_token_user():
    """Utilisateur associe a un token mobile Bearer valide, sinon None.

    Permet aux endpoints de l'application mobile de s'authentifier sans cookie
    de session : la requete n'est donc pas rejouable par un site tiers (CSRF).
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        user, reason = _verify_mobile_token(auth.split(" ", 1)[1].strip())
    except Exception:
        return None
    return user if not reason else None


def _safe_next_url(url):
    """Retourne une URL de redirection locale ou vide pour eviter les open redirects."""
    if not url:
        return ""
    if url.startswith('/') and not url.startswith('//'):
        return url
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ('http', 'https') and parsed.netloc == request.host:
            return url
    except Exception:
        pass
    return ""


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id") and not get_current_user():
            if request.headers.get("Authorization", "").startswith("Bearer "):
                return jsonify({"error": "Session expiree ou invalide."}), 401
            flash("Veuillez vous connecter pour acceder a cette page.", "error")
            next_login = (url_for("admin_login")
                          if request.endpoint and request.endpoint.startswith("admin")
                          else url_for("login", next=_safe_next_url(request.full_path)))
            return redirect(next_login)
        return view_func(*args, **kwargs)

    return wrapper


def admin_required(view_func):
    """Verifie que l'utilisateur connecte possede le role admin et a déverrouillé sa session."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or user["role"] != "admin":
            flash("Acces reserve aux administrateurs.", "error")
            return redirect(url_for("admin_login"))
        if (request.endpoint and request.endpoint not in ("admin_unlock", "admin_logout")
                and not session.get("admin_unlocked")):
            return redirect(url_for("admin_unlock"))
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
    if hasattr(g, "_current_user"):
        return g._current_user
    user = None
    user_id = session.get("user_id")
    if user_id:
        conn = get_db_connection()
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        finally:
            conn.close()
    if user is None:
        user = _bearer_token_user()
    g._current_user = user
    return user


PAYMENT_METHODS = {
    "orange_money": "Orange Money",
    "mtn_mobile_money": "MTN Mobile Money",
    "card": "Carte bancaire",
    "cash": "Espèces en main propre",
    "mobile_money": "Mobile Money",
}


def payment_method_label(method):
    return PAYMENT_METHODS.get(method, (method or "").replace("_", " ").title())


# Statuts officiels du cycle de mission.
MISSION_STATUS_REQUESTED = "REQUESTED"
MISSION_STATUS_ASSIGNED = "ASSIGNED"
MISSION_STATUS_ACCEPTED = "ACCEPTED"
MISSION_STATUS_EN_ROUTE = "EN_ROUTE"
MISSION_STATUS_ARRIVED = "ARRIVED"
MISSION_STATUS_IN_PROGRESS = "IN_PROGRESS"
MISSION_STATUS_COMPLETED = "COMPLETED"
MISSION_STATUS_REFUSED = "REFUSED"
MISSION_STATUS_CANCELLED = "CANCELLED"
MISSION_STATUS_REASSIGNMENT_REQUIRED = "REASSIGNMENT_REQUIRED"

# Alias legacy pour compatibilite (la DB et les templates peuvent encore
# contenir les anciens libelles en minuscules).
_MISSION_STATUS_ALIASES = {
    "pending": MISSION_STATUS_REQUESTED,
    "assigned": MISSION_STATUS_ASSIGNED,
    "accepted": MISSION_STATUS_ACCEPTED,
    "en_route": MISSION_STATUS_EN_ROUTE,
    "arrived": MISSION_STATUS_ARRIVED,
    "in_progress": MISSION_STATUS_IN_PROGRESS,
    "completed": MISSION_STATUS_COMPLETED,
    "rejected": MISSION_STATUS_REFUSED,
    "refused": MISSION_STATUS_REFUSED,
    "cancelled": MISSION_STATUS_CANCELLED,
    "reassignment_required": MISSION_STATUS_REASSIGNMENT_REQUIRED,
}

# Libelles lisibles pour l'affichage dans l'historique.
_MISSION_STATUS_LABELS = {
    MISSION_STATUS_REQUESTED: "Nouvelle demande",
    MISSION_STATUS_ASSIGNED: "Technicien attribue",
    MISSION_STATUS_ACCEPTED: "Mission acceptee",
    MISSION_STATUS_EN_ROUTE: "En route",
    MISSION_STATUS_ARRIVED: "Arrivee",
    MISSION_STATUS_IN_PROGRESS: "Intervention en cours",
    MISSION_STATUS_COMPLETED: "Terminee",
    MISSION_STATUS_REFUSED: "Mission refusee",
    MISSION_STATUS_CANCELLED: "Mission annulee",
    MISSION_STATUS_REASSIGNMENT_REQUIRED: "Reattribution requise",
}

# Transitions autorisees pour les demandes.
# cle = statut actuel, valeur = ensemble de statuts cibles permis.
REQUEST_TRANSITIONS = {
    MISSION_STATUS_REQUESTED: {MISSION_STATUS_ASSIGNED, MISSION_STATUS_CANCELLED},
    MISSION_STATUS_ASSIGNED: {MISSION_STATUS_ACCEPTED, MISSION_STATUS_REFUSED, MISSION_STATUS_CANCELLED},
    MISSION_STATUS_ACCEPTED: {MISSION_STATUS_EN_ROUTE, "quote_proposed", MISSION_STATUS_CANCELLED},
    MISSION_STATUS_EN_ROUTE: {MISSION_STATUS_ARRIVED, MISSION_STATUS_CANCELLED},
    MISSION_STATUS_ARRIVED: {MISSION_STATUS_IN_PROGRESS, MISSION_STATUS_CANCELLED},
    MISSION_STATUS_IN_PROGRESS: {MISSION_STATUS_COMPLETED, MISSION_STATUS_CANCELLED},
    MISSION_STATUS_REFUSED: {MISSION_STATUS_REASSIGNMENT_REQUIRED, MISSION_STATUS_ASSIGNED, MISSION_STATUS_CANCELLED},
    MISSION_STATUS_REASSIGNMENT_REQUIRED: {MISSION_STATUS_ASSIGNED, MISSION_STATUS_CANCELLED},
    MISSION_STATUS_COMPLETED: set(),
    MISSION_STATUS_CANCELLED: set(),
    # Flux de devis conserve (hors cycle mission principal)
    "quote_proposed": {"quote_accepted", "quote_rejected", "cancelled"},
    "quote_accepted": {MISSION_STATUS_ARRIVED, MISSION_STATUS_IN_PROGRESS, MISSION_STATUS_CANCELLED},
    "quote_rejected": {"quote_proposed", MISSION_STATUS_CANCELLED},
}


def _normalize_status(status):
    """Convertit un ancien libelle de statut en libelle officiel."""
    if not status:
        return None
    key = str(status).strip().lower()
    return _MISSION_STATUS_ALIASES.get(key, status)


def can_transition_request(current_status, new_status):
    """Verifie qu'un changement de statut de demande est autorise."""
    current = _normalize_status(current_status)
    new = _normalize_status(new_status)
    if not current or not new:
        return False
    allowed = REQUEST_TRANSITIONS.get(current, set())
    return new in allowed


def _now_minus(seconds=300):
    """Retourne un timestamp ISO pour le seuil de fraicheur d'une position.

    Format 'YYYY-MM-DD HH:MM:SS' afin d'etre comparable avec CURRENT_TIMESTAMP
    de SQLite et de PostgreSQL ( TEXT ).
    """
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).replace(
        tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _match_technicians(conn, category, location=None, client_lat=None, client_lon=None,
                       limit=10, require_gps=False, exclude_artisan_id=None):
    """Retourne les techniciens eligibles classes pour une demande.

    Criteres : role=technician, verifie, actif, ACTIVE, en_ligne,
    sans mission en cours, metier compatible, position GPS recente.
    """
    profession = _domain_to_profession(category) if category else None
    if not profession:
        return []

    # Coordonnees client
    if _is_valid_coordinate(client_lat, client_lon):
        lat, lon = float(client_lat), float(client_lon)
    else:
        lat, lon = _geocode_zone("Conakry", location or "Conakry")
        if not _is_valid_coordinate(lat, lon):
            lat, lon = _geocode_query(location or "Conakry")[:2] if location else (None, None)
    client_pos = (lat, lon) if _is_valid_coordinate(lat, lon) else None

    freshness = _now_minus(300)

    # Localisation GPS recente des techniciens
    locations = {
        row["technician_id"]: (float(row["latitude"]), float(row["longitude"]), row["updated_at"])
        for row in conn.execute(
            "SELECT technician_id, latitude, longitude, updated_at FROM technician_locations"
            " WHERE updated_at > ?",
            (freshness,)).fetchall()
        if _is_valid_coordinate(row["latitude"], row["longitude"])
    }
    if require_gps and not locations:
        return []

    # Techniciens occupes par une mission non terminee
    busy_sql = (
        "SELECT artisan_id FROM requests"
        " WHERE artisan_id IS NOT NULL"
        " AND status NOT IN ('COMPLETED','CANCELLED','REFUSED','REASSIGNMENT_REQUIRED','REQUESTED')"
        " GROUP BY artisan_id HAVING COUNT(*) > 0")
    busy_ids = {r["artisan_id"] for r in conn.execute(busy_sql).fetchall()}
    if exclude_artisan_id:
        busy_ids.add(exclude_artisan_id)

    sql = """
        SELECT u.id, u.full_name, u.profession, u.city, u.quartier,
               u.latitude, u.longitude,
               u.zone_intervention, u.mobility, u.years_experience, u.is_verified,
               COALESCE(rating_data.avg_rating, 0) AS avg_rating,
               COALESCE(rating_data.review_count, 0) AS review_count,
               COALESCE(completed_count.c, 0) AS completed_count
        FROM users u
        LEFT JOIN (
            SELECT artisan_id, AVG(rating) AS avg_rating, COUNT(*) AS review_count
            FROM reviews GROUP BY artisan_id
        ) rating_data ON rating_data.artisan_id = u.id
        LEFT JOIN (
            SELECT artisan_id, COUNT(*) AS c
            FROM requests WHERE LOWER(status) = 'completed' GROUP BY artisan_id
        ) completed_count ON completed_count.artisan_id = u.id
        WHERE u.role = 'technician'
          AND u.is_verified = 1
          AND u.is_active = 1
          AND u.account_status = 'ACTIVE'
          AND LOWER(u.availability_status) = 'en_ligne'
          AND LOWER(REPLACE(REPLACE(u.profession, 'é', 'e'), 'É', 'E')) = ?
    """
    rows = conn.execute(sql, (profession,)).fetchall()

    location_norm = (location or "").lower()

    def in_zone(a):
        zones = " ".join([
            (a.get("zone_intervention") or ""),
            (a.get("quartier") or ""),
            (a.get("city") or ""),
        ]).lower()
        return bool(location_norm) and (location_norm in zones or (a.get("mobility") or "").lower() == 'toute_conakry')

    candidates = []
    for a in rows:
        if a["id"] in busy_ids:
            continue
        tech_pos = locations.get(a["id"])
        if require_gps and not tech_pos:
            continue
        distance = None
        if client_pos and tech_pos:
            distance = _haversine(client_pos[0], client_pos[1], tech_pos[0], tech_pos[1])
        elif client_pos and _is_valid_coordinate(a.get("latitude"), a.get("longitude")):
            # Secours uniquement si le GPS temps reel manque
            distance = _haversine(client_pos[0], client_pos[1], float(a["latitude"]), float(a["longitude"]))

        score = 0
        if tech_pos:
            score += 80  # GPS recent
        if in_zone(a):
            score += 25
        if a["is_verified"]:
            score += 30
        score += float(a["avg_rating"]) * 20
        score += (a["completed_count"] or 0) * 2
        score += (a["years_experience"] or 0)
        if distance is not None:
            score -= distance * 2
        else:
            score -= 25  # penalite si pas de distance fiable

        artisan = dict(a)
        artisan["distance_km"] = round(distance, 1) if distance is not None else None
        artisan["selection_score"] = score
        artisan["gps_source"] = "technician_locations" if tech_pos else "profile"
        candidates.append(artisan)

    candidates.sort(key=lambda a: (-a["selection_score"], a["distance_km"] or 9999, a["full_name"]))
    return candidates[:limit]


def _select_best_technician(conn, category, location, client_lat=None, client_lon=None,
                            exclude_artisan_id=None, require_gps=None):
    """Selectionne le meilleur technicien."""
    if require_gps is None:
        require_gps = app.config.get("GPS_REQUIRED", False)
    candidates = _match_technicians(conn, category, location=location,
                                    client_lat=client_lat, client_lon=client_lon,
                                    limit=1, require_gps=require_gps,
                                    exclude_artisan_id=exclude_artisan_id)
    if not candidates:
        return None
    best = candidates[0]
    parts = [best["profession"]]
    if best["distance_km"] is not None:
        parts.append(f"a {best['distance_km']} km")
    parts.append("GPS " + ("temps reel" if best["gps_source"] == "technician_locations" else "profil"))
    if best["is_verified"]:
        parts.append("verifie")
    best["selection_reason"] = "; ".join(parts)
    return best


class PaymentProvider(ABC):
    """Abstraction pour les fournisseurs de paiement.

    Permet d'integrer Orange Money, MTN, ou un mock sans melanger
    la logique metier avec l'implementation du fournisseur.
    """

    @abstractmethod
    def process(self, amount, method, reference, metadata):
        """Initie un paiement et retourne un statut controle."""

    @abstractmethod
    def confirm(self, reference, payload):
        """Verifie la confirmation cote fournisseur."""

    @abstractmethod
    def refund(self, reference, amount):
        """Initie un remboursement."""


class MockPaymentProvider(PaymentProvider):
    """Fournisseur factice pour les environnements de test."""

    def process(self, amount, method, reference, metadata):
        return {
            "ok": True,
            "status": "pending",
            "provider_reference": f"MOCK-{reference}",
            "message": "Paiement en attente de confirmation (test).",
        }

    def confirm(self, reference, payload):
        return {
            "ok": True,
            "status": "success",
            "provider_reference": f"MOCK-{reference}",
        }

    def refund(self, reference, amount):
        return {
            "ok": True,
            "status": "refunded",
            "provider_reference": f"MOCK-{reference}",
        }


def get_payment_provider():
    """Retourne le fournisseur de paiement actuel."""
    if app.config.get("FLASK_ENV") == "testing" or app.config.get("PAYMENT_PROVIDER") == "mock":
        return MockPaymentProvider()
    # TODO : instancier OrangeMoneyProvider lorsque credentials configures.
    return MockPaymentProvider()


def create_notification(user_id, title, body, notif_type="info", data=None, conn=None):
    """Cree une notification in-app pour un utilisateur.

    Si une connexion est fournie, l'insertion fait partie de la transaction
    courante et n'est ni validee ni fermee ici.
    """
    own = conn is None
    if own:
        conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO notifications (user_id, title, body, type, data)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, title, body, notif_type, data or ""))
        if own:
            conn.commit()
    except Exception as exc:
        logger.warning("Notification non creee : user_id=%s - %s", user_id, exc)
    finally:
        if own:
            conn.close()


def create_admin_notification(conn, title, body, notif_type="admin_alert", data=None):
    """Cree une notification pour tous les administrateurs."""
    try:
        admins = conn.execute(
            "SELECT id FROM users WHERE role = 'admin' AND is_active = 1").fetchall()
        for admin in admins:
            conn.execute(
                "INSERT INTO notifications (user_id, title, body, type, data)"
                " VALUES (?, ?, ?, ?, ?)",
                (admin["id"], title, body, notif_type, data or ""))
        conn.commit()
    except Exception as exc:
        logger.warning("Notification admin non creee : %s", exc)


def _log_intervention_history(conn, request_id, old_status, new_status, actor, note="", label=None):
    """Enregistre un evenement dans l'historique de la mission."""
    try:
        status_label = label if label is not None else new_status
        conn.execute(
            "INSERT INTO intervention_history"
            " (request_id, old_status, status, new_status, actor, note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request_id, old_status, status_label,
             new_status, actor, note or "", now_iso()))
        conn.commit()
    except Exception as exc:
        logger.warning("Historique mission non enregistre : request_id=%s - %s", request_id, exc)


@app.context_processor
def inject_layout_context():
    """Expose l'utilisateur connecte et les compteurs admin a tous les gabarits."""
    try:
        connected = get_current_user()
    except Exception:
        connected = None

    stats = {}
    if connected and connected.get("role") == "admin":
        if ADMIN_DEMO:
            stats = {"pending_artisans": 1, "open_requests": 4, "pending_requests": 6, "open_tickets": 2, "open_messages": 3}
        else:
            conn = get_db_connection()
            try:
                rows = conn.execute(
                    "SELECT 'pending_artisans' AS key, COUNT(*) AS n FROM users WHERE role = 'technician' AND is_verified = 0"
                    " UNION ALL"
                    " SELECT 'open_requests', COUNT(*) FROM requests WHERE LOWER(status) NOT IN ('completed', 'cancelled')"
                    " UNION ALL"
                    " SELECT 'pending_requests', COUNT(*) FROM requests WHERE LOWER(status) IN ('requested', 'nouvelle demande', 'pending')"
                    " UNION ALL"
                    " SELECT 'open_tickets', COUNT(*) FROM admin_tickets WHERE status = 'open'"
                    " UNION ALL"
                    " SELECT 'open_messages', COUNT(*) FROM conversations c"
                    " JOIN conversation_messages m ON m.conversation_id = c.id"
                    " WHERE c.status = 'open' AND m.sender_role = 'client' AND m.is_read = 0").fetchall()
                stats = {r["key"]: r["n"] for r in rows}
            finally:
                conn.close()

    return {"nav_user": connected, "admin_stats": stats}


def can_access_request(user, req):
    """Determine si un utilisateur a le droit de consulter une intervention."""
    if not user or not req:
        return False
    if user["role"] == "admin":
        return True
    return user["id"] in (req["client_id"], req["artisan_id"])


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
    conn = get_db_connection()
    try:
        artisans = conn.execute("""
            SELECT u.id, u.full_name, u.profession, u.photo_url, u.is_verified,
                   u.availability_status,
                   u.city, u.zone_intervention, u.quartier,
                   u.latitude, u.longitude, u.hourly_rate,
                   COALESCE(AVG(r.rating), 0) AS avg_rating,
                   COUNT(DISTINCT r.id) AS review_count
            FROM users u
            LEFT JOIN reviews r ON r.artisan_id = u.id
            WHERE u.profession IS NOT NULL AND u.profession != ''
            GROUP BY u.id, u.full_name, u.profession, u.photo_url, u.is_verified, u.availability_status,
                     u.city, u.zone_intervention, u.quartier, u.latitude, u.longitude, u.hourly_rate
            ORDER BY avg_rating DESC, review_count DESC
        """).fetchall()
        user = get_current_user()
        unread_count = 0
        if user:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                    (user["id"],)).fetchone()
                unread_count = row["n"]
            except Exception:
                conn.rollback()
                unread_count = 0
        counts = {}
        for row in conn.execute(
            "SELECT profession, COUNT(*) AS n FROM users WHERE profession IS NOT NULL AND profession != '' GROUP BY profession").fetchall():
            counts[row["profession"]] = row["n"]
        canonical = [
            ("Plomberie", ["Plombier", "Plomberie"]),
            ("Électricité", ["Électricien", "Electricien", "Electricite"]),
            ("Frigoriste", ["Frigoriste"]),
            ("Menuiserie", ["Menuisier", "Menuiserie"]),
            ("Peinture", ["Peintre", "Peinture"]),
            ("Maçonnerie", ["Maçon", "Maçonnerie"]),
        ]
        popular = []
        for label, keys in canonical:
            n = sum(counts.get(k, 0) for k in keys)
            href_key = next((k for k in keys if counts.get(k, 0)), keys[0])
            popular.append({"label": label, "count": n, "category": href_key})

        artisans = [dict(a) for a in artisans]

        # Un technicien connecte va directement sur son tableau de bord
        if user and _is_technician(user):
            response = make_response(redirect(url_for("artisan_dashboard")))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response

        client_lat = _to_float(user.get("latitude")) if user else None
        client_lon = _to_float(user.get("longitude")) if user else None
        if client_lat is None or client_lon is None:
            client_lat = _to_float(session.get("client_lat"))
            client_lon = _to_float(session.get("client_lon"))
        client_in_conakry = _is_valid_coordinate(client_lat, client_lon) and _nearest_zone(client_lat, client_lon, max_km=50.0) is not None
        if client_in_conakry:
            for a in artisans:
                a_lat = _to_float(a.get("latitude"))
                a_lon = _to_float(a.get("longitude"))
                a["distance"] = _haversine(client_lat, client_lon, a_lat, a_lon) if _is_valid_coordinate(a_lat, a_lon) else None
            artisans.sort(key=lambda a: a.get("distance") if a.get("distance") is not None else 999)
        artisans = artisans[:4]
    finally:
        conn.close()
    response = make_response(render_template("index.html", artisans=artisans, unread_count=unread_count,
                           loc_permission=session.get("loc_permission", "prompt"),
                           client_zone=session.get("client_zone"),
                           category_counts=counts,
                           popular=popular))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def _persist_client_location(lat=None, lon=None, zone=None):
    """Enregistre la localisation du client dans son profil (s'il est connecte).

    Permet a la position de survivre a la session : aux visites suivantes,
    l'app connait deja son secteur sans rien redemander.
    """
    user_id = session.get("user_id")
    if not user_id:
        return
    sets, params = [], []
    if _is_valid_coordinate(lat, lon):
        sets += ["latitude = ?", "longitude = ?"]
        params += [float(lat), float(lon)]
    if zone:
        sets.append("quartier = ?")
        params.append(zone)
    if not sets:
        return
    params.append(user_id)
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET " + ", ".join(sets) + " WHERE id = ?", params)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("Localisation non enregistree dans le profil: %s", exc)
    finally:
        conn.close()


@app.route("/api/location", methods=["POST"])
@limiter.limit("30 per hour")
def set_location():
    """Enregistre la position GPS du client en session (et dans son profil)."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        lat = _to_float(data.get("lat"))
        lon = _to_float(data.get("lon"))
        accuracy = _to_float(data.get("accuracy"), 0.0)
        if lat == 0.0 or lon == 0.0:
            return jsonify({"ok": False, "error": "Coordonnees invalides"}), 400
        session["client_lat"] = lat
        session["client_lon"] = lon
        session["client_loc_accuracy"] = accuracy
        session["client_loc_at"] = datetime.now(timezone.utc).isoformat()
        session["loc_permission"] = "granted"
        session.pop("loc_gate_dismissed", None)
        zone = _nearest_zone(lat, lon)
        if not zone:
            zone = _reverse_geocode(lat, lon) or "Ma position"
        session["client_zone"] = zone
        _persist_client_location(lat, lon, zone if zone != "Ma position" else None)
        return jsonify({"ok": True, "zone": zone, "lat": lat, "lon": lon, "accuracy": accuracy})
    except Exception as e:
        logger.warning("Erreur enregistrement position: %s", e)
        return jsonify({"ok": False, "error": "Position non enregistree."}), 500


@app.route("/api/location/zone", methods=["POST"])
@limiter.limit("30 per hour")
def set_location_zone():
    """Enregistre une localisation manuelle saisie par l'utilisateur."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        zone = (data.get("zone") or "").strip()
        if not zone:
            return jsonify({"ok": False, "error": "Zone vide"}), 400
        session["loc_permission"] = "manual"

        # 1. Quartier de la liste FixPro : coordonnees figees, aucun geocodage
        #    externe (sinon "Madina" -> Medine, Arabie Saoudite).
        coords = None
        for name, xy in _CONAKRY_QUARTIERS.items():
            if name.lower() == zone.lower():
                coords, zone = xy, name
                break
        # 2. Zone connue de _ARTISAN_GEOCODE.
        if not coords:
            coords = _zone_coordinate(zone)
        # 3. Dernier recours : geocodage borne a Conakry (rejette les
        #    homonymes a l'etranger).
        if not coords:
            lat, lon, place = _geocode_query(zone + ", Conakry, Guinee")
            if (lat is not None and lon is not None
                    and _nearest_zone(lat, lon, max_km=60.0)):
                coords = (lat, lon)
                if place:
                    zone = place
        session["client_zone"] = zone
        session.pop("loc_gate_dismissed", None)
        if coords:
            session["client_lat"] = coords[0]
            session["client_lon"] = coords[1]
        else:
            session.pop("client_lat", None)
            session.pop("client_lon", None)
        _persist_client_location(
            coords[0] if coords else None,
            coords[1] if coords else None,
            zone)
        return jsonify({"ok": True, "zone": zone, "lat": session.get("client_lat"), "lon": session.get("client_lon")})
    except Exception as e:
        logger.warning("Erreur enregistrement zone manuelle: %s", e)
        return jsonify({"ok": False, "error": "Zone non enregistree."}), 500


@app.route("/api/location/denied", methods=["POST"])
def set_location_denied():
    """Marque la permission GPS comme refusee."""
    session["loc_permission"] = "denied"
    return jsonify({"ok": True})


# Appelees en fetch depuis l'ecran de localisation, souvent depuis un
# navigateur mobile (ou via un proxy de traduction) qui n'envoie pas le
# header Referer -> la verification stricte de Flask-WTF les rejetait
# ("The referrer header is missing"). Definir sa propre position n'est pas
# une cible d'attaque CSRF : on exempte.
csrf.exempt(set_location)
csrf.exempt(set_location_zone)
csrf.exempt(set_location_denied)


@app.route("/localisation")
def location_gate():
    """Ecran plein ecran demandant la position du client a l'entree de l'app."""
    nxt = request.args.get("next") or ""
    # Chemin interne uniquement : commence par "/", pas "//" ni "/\" (open
    # redirect), et ne contient que des caracteres d'URL sans danger.
    if (not nxt.startswith("/") or nxt.startswith(("//", "/\\"))
            or not re.match(r"^/[A-Za-z0-9/_.\-?=&%]*$", nxt)):
        nxt = url_for("artisans_page")
    return render_template("location_gate.html",
                           quartiers=_CONAKRY_QUARTIERS, next=nxt)


# ---------------------------------------------------------------------------
# LOCALISATION CLIENT - FIGE (2026-08-31). Couvert par tests/test_app.py
# (test_visitor_without_location_sees_location_gate, ..._enters_app_after...,
#  test_technician_not_gated_by_location, test_artisans_filtered_by_radius).
# Ne pas modifier sans mettre a jour ces tests.
# ---------------------------------------------------------------------------

# Pages sur lesquelles la localisation est requise avant d'entrer dans l'app.
_LOCATION_GATED_ENDPOINTS = {
    "index", "artisans_page", "categories", "requests_list",
    "request_new", "dashboard",
}


@app.before_request
def require_client_location():
    """Ecran de localisation a l'entree de l'app.

    Le client n'a PAS besoin d'etre connecte : un visiteur qui arrive tombe
    directement sur l'ecran, autorise sa position (stockee en session), puis
    entre dans l'app. Seuls les techniciens et admins connectes sont exemptes.
    """
    if request.method != "GET" or request.endpoint not in _LOCATION_GATED_ENDPOINTS:
        return None
    user = get_current_user()
    if user and user["role"] in ("technician", "artisan", "admin"):
        return None
    if (session.get("client_lat") or session.get("client_zone")
            or session.get("loc_gate_dismissed")):
        return None
    if user and _is_valid_coordinate(user.get("latitude"), user.get("longitude")):
        return None
    return redirect(url_for("location_gate", next=request.path))


@app.route("/home")
@login_required
def home():
    """Application accueil connecte."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        artisans = conn.execute("""
            SELECT u.id, u.full_name, u.profession, u.photo_url, u.is_verified,
                   u.availability_status,
                   u.city, u.zone_intervention, u.quartier,
                   u.latitude, u.longitude, u.hourly_rate,
                   COALESCE(AVG(r.rating), 0) AS avg_rating,
                   COUNT(DISTINCT r.id) AS review_count
            FROM users u
            LEFT JOIN reviews r ON r.artisan_id = u.id
            WHERE u.profession IS NOT NULL AND u.profession != ''
            GROUP BY u.id, u.full_name, u.profession, u.photo_url, u.is_verified, u.availability_status,
                     u.city, u.zone_intervention, u.quartier, u.latitude, u.longitude, u.hourly_rate
            ORDER BY avg_rating DESC, review_count DESC
        """).fetchall()
        unread_count = 0
        if user:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                    (user["id"],)).fetchone()
                unread_count = row["n"]
            except Exception:
                conn.rollback()
                unread_count = 0
        counts = {}
        for row in conn.execute(
            "SELECT profession, COUNT(*) AS n FROM users WHERE profession IS NOT NULL AND profession != '' GROUP BY profession").fetchall():
            counts[row["profession"]] = row["n"]
        canonical = [
            ("Plomberie", ["Plombier", "Plomberie"]),
            ("Électricité", ["Électricien", "Electricien", "Electricite"]),
            ("Frigoriste", ["Frigoriste"]),
            ("Menuiserie", ["Menuisier", "Menuiserie"]),
            ("Peinture", ["Peintre", "Peinture"]),
            ("Maçonnerie", ["Maçon", "Maçonnerie"]),
        ]
        popular = []
        for label, keys in canonical:
            n = sum(counts.get(k, 0) for k in keys)
            href_key = next((k for k in keys if counts.get(k, 0)), keys[0])
            popular.append({"label": label, "count": n, "category": href_key})

        artisans = [dict(a) for a in artisans]
        client_lat = _to_float(user.get("latitude")) if user else None
        client_lon = _to_float(user.get("longitude")) if user else None
        if client_lat is None or client_lon is None:
            client_lat = _to_float(session.get("client_lat"))
            client_lon = _to_float(session.get("client_lon"))
        client_in_conakry = _is_valid_coordinate(client_lat, client_lon) and _nearest_zone(client_lat, client_lon, max_km=50.0) is not None
        if client_in_conakry:
            for a in artisans:
                a_lat = _to_float(a.get("latitude"))
                a_lon = _to_float(a.get("longitude"))
                a["distance"] = _haversine(client_lat, client_lon, a_lat, a_lon) if _is_valid_coordinate(a_lat, a_lon) else None
            artisans.sort(key=lambda a: a.get("distance") if a.get("distance") is not None else 999)
        artisans = artisans[:4]
    finally:
        conn.close()
    return render_template("home.html", user=user, artisans=artisans, unread_count=unread_count,
                           loc_permission=session.get("loc_permission", "prompt"),
                           client_zone=session.get("client_zone"),
                           category_counts=counts,
                           popular=popular)


@app.route("/categories")
def categories():
    conn = get_db_connection()
    try:
        categories = conn.execute(
            "SELECT name, diagnostic_price FROM service_categories ORDER BY name").fetchall()
        rows = conn.execute(
            "SELECT sc.name,"
            " (SELECT COUNT(*) FROM users u"
            " WHERE u.profession IS NOT NULL AND u.profession != ''"
            " AND (u.profession = sc.name OR u.skills LIKE '%' || sc.name || '%')) AS n"
            " FROM service_categories sc ORDER BY sc.name").fetchall()
        counts = {r["name"]: r["n"] for r in rows}
    finally:
        conn.close()
    return render_template("categories.html", categories=categories, counts=counts)


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
            engine = "postgresql" if conn.is_postgres else "sqlite"
            return jsonify({
                "status": "ok",
                "db": "connected",
                "engine": engine,
                "timestamp": now_iso(),
            })
        finally:
            conn.close()
    except Exception as exc:
        logger.exception("Echec de la connexion a la base de donnees")
        payload = {"status": "error", "db": "disconnected"}
        if app.config.get("DEBUG"):
            payload["error"] = str(exc)
        return jsonify(payload), 500


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

def _validate_password_strength(password):
    """Verifie la force d'un mot de passe."""
    if len(password) < 8:
        return "Le mot de passe doit contenir au moins 8 caracteres."
    if not re.search(r"[A-Z]", password):
        return "Le mot de passe doit contenir au moins une majuscule."
    if not re.search(r"[a-z]", password):
        return "Le mot de passe doit contenir au moins une minuscule."
    if not re.search(r"[0-9]", password):
        return "Le mot de passe doit contenir au moins un chiffre."
    return None


def _phone_with_prefix(phone):
    """Ajoute le prefixe guineen si absent."""
    phone = (phone or "").strip().replace(" ", "")
    if phone and not phone.startswith("+"):
        phone = f"+224{phone}"
    return phone


def _parse_base64_file(data_uri):
    """Extrait le mime, le nom et le contenu binaire depuis un data URI base64.

    Valide le type MIME, la taille et les magic bytes du fichier decode.
    """
    if not data_uri or not data_uri.startswith("data:"):
        return None, None, None
    try:
        meta, encoded = data_uri.split(",", 1)
        mime = meta.split(";")[0].replace("data:", "").lower()
        allowed = ("image/jpeg", "image/jpg", "image/png", "application/pdf")
        if mime not in allowed:
            return None, None, None

        # Limite approximative : base64 est ~33% plus gros que binaire
        if len(encoded) > 3 * 1024 * 1024:
            return None, None, None

        # Verification des magic bytes pour eviter les fichiers deguises
        raw = base64.b64decode(encoded)
        if not raw:
            return None, None, None
        magic = raw[:8]
        if mime in ("image/jpeg", "image/jpg") and not magic.startswith(b"\xff\xd8"):
            return None, None, None
        if mime == "image/png" and not magic.startswith(b"\x89PNG\r\n\x1a\n"):
            return None, None, None
        if mime == "application/pdf" and not magic.startswith(b"%PDF"):
            return None, None, None

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
    if role not in ("client", "artisan", "technician"):
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

        pwd_error = _validate_password_strength(password)
        if pwd_error:
            flash(pwd_error, "error")
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

    if role in ("artisan", "technician"):
        return redirect(url_for("register_artisan", role="technician"))

    return render_template("choose_account.html")


# --- Verification des techniciens -------------------------------------------

VERIF_PENDING = "PENDING_REVIEW"
VERIF_APPROVED = "APPROVED"
VERIF_REJECTED = "REJECTED"
VERIF_REVISION = "REVISION_REQUIRED"
VERIF_BLOCKING = (VERIF_PENDING, VERIF_REJECTED, VERIF_REVISION)

DOC_IDENTITY = "identity"
DOC_PROFESSIONAL = "professional"
REQUIRED_DOC_TYPES = (DOC_IDENTITY, DOC_PROFESSIONAL)


def _verification_enabled():
    """Vrai si la verification des documents technicien est active (voir config)."""
    return bool(app.config.get("TECH_VERIFICATION_ENABLED"))


def _store_technician_document(conn, store, tech_id, doc_type, data_uri, fallback_name):
    """Televerse un document de verification et enregistre ses metadonnees.

    Retourne None en cas de succes, un message d'erreur sinon.
    """
    if not data_uri:
        return "Document manquant."
    mime, ext, encoded = _parse_base64_file(data_uri)
    if not encoded:
        return "Format de document non valide (JPG, PNG ou PDF, 3 Mo max)."
    try:
        stored = store.upload(doc_type, data_uri)
    except ValueError as exc:
        return str(exc)
    file_size = (len(encoded) * 3) // 4
    conn.execute(
        "INSERT INTO technician_documents (technician_id, document_type, file_name,"
        " original_file_name, mime_type, file_size, content_base64, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (tech_id, doc_type, f"{fallback_name}{ext}", f"{fallback_name}{ext}",
         mime or "application/octet-stream", file_size, stored))
    return None


def _notify_admins_new_technician(conn, tech_id, full_name, profession, city):
    """Previent tous les admins qu'un dossier technicien attend une verification."""
    try:
        admins = conn.execute("SELECT id FROM users WHERE role = 'admin'").fetchall()
        for admin in admins:
            create_notification(
                admin["id"],
                "Nouvelle demande de technicien",
                f"{full_name} ({profession or 'metier non precise'}, {city or 'ville non precisee'})"
                " a termine son dossier et attend une verification.",
                "info",
                f"technician:{tech_id}",
                conn=conn)
    except Exception:  # pragma: no cover - la notification ne doit jamais bloquer
        logger.exception("Echec notification admins pour le technicien %s", tech_id)


def _technician_documents_by_type(conn, tech_id):
    """Retourne {document_type: derniere ligne} pour un technicien."""
    rows = conn.execute(
        "SELECT * FROM technician_documents WHERE technician_id = ? ORDER BY id",
        (tech_id,)).fetchall()
    latest = {}
    for row in rows:
        latest[row["document_type"]] = row
    return latest


def _technician_docs_all_approved(conn, tech_id):
    """Vrai si les deux documents obligatoires existent et sont approuves."""
    docs = _technician_documents_by_type(conn, tech_id)
    return all(
        docs.get(t) and (docs[t]["status"] or "").lower() == "approved"
        for t in REQUIRED_DOC_TYPES)


def _technician_has_documents(conn, tech_id):
    """Vrai si le technicien a soumis au moins un document de verification."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM technician_documents WHERE technician_id = ?",
        (tech_id,)).fetchone()
    return bool(row and row["n"])


@app.route("/register/artisan", methods=["GET", "POST"])
@app.route("/inscription/technicien", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register_artisan():
    """Formulaire d'inscription technicien sur une seule page."""
    conn = get_db_connection()
    try:
        categories = conn.execute(
            "SELECT id, name FROM service_categories ORDER BY name").fetchall()
        all_services = conn.execute(
            "SELECT id, category_id, name FROM services WHERE is_active = 1 ORDER BY name").fetchall()
    finally:
        conn.close()

    role = (request.args.get("role") or request.form.get("role") or "technician").lower()
    if role not in ("artisan", "technician"):
        role = "technician"

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = _phone_with_prefix(request.form.get("phone", "").strip())
        profession = request.form.get("profession", "").strip()
        specialite = request.form.get("specialite", "").strip()
        experience = int(request.form.get("experience") or 0)
        bio = request.form.get("bio", "").strip()
        address = request.form.get("address", "").strip()
        rayon = request.form.get("rayon", "").strip()
        email = request.form.get("email", "").strip().lower()
        account_password = request.form.get("password", "")
        identity_doc = request.form.get("identity_doc", "").strip()
        professional_doc = request.form.get("professional_doc", "").strip()
        photo = request.form.get("photo", "").strip()
        portfolio_raw = request.form.get("portfolio", "").strip()
        hourly_rate = _to_float(request.form.get("hourly_rate", 0))
        availability = request.form.get("availability", "").strip()
        available_days = request.form.getlist("available_days")

        if availability == "certains_jours" and not available_days:
            flash("Veuillez selectionner au moins un jour de disponibilite.", "error")
            return redirect(url_for("register_artisan"))

        if availability == "toujours":
            availability_status = "en_ligne"
            available_days_str = "Lundi,Mardi,Mercredi,Jeudi,Vendredi,Samedi,Dimanche"
        elif availability == "certains_jours":
            availability_status = "certains_jours"
            available_days_str = ",".join(available_days)
        else:
            availability_status = "hors_ligne"
            available_days_str = ""

        if not full_name or not phone or not profession or not address:
            flash("Veuillez remplir tous les champs obligatoires.", "error")
            return redirect(url_for("register_artisan"))

        verif_on = _verification_enabled()

        if not email:
            flash("Veuillez renseigner votre adresse e-mail.", "error")
            return redirect(url_for("register_artisan"))
        pwd_error = _validate_password_strength(account_password)
        if pwd_error:
            flash(pwd_error, "error")
            return redirect(url_for("register_artisan"))
        # Documents obligatoires uniquement si la verification est active (garde serveur).
        if verif_on:
            if not identity_doc:
                flash("Veuillez importer votre piece d'identite pour continuer.", "error")
                return redirect(url_for("register_artisan"))
            if not professional_doc:
                flash("Votre justificatif professionnel est obligatoire.", "error")
                return redirect(url_for("register_artisan"))

        conn = get_db_connection()
        try:
            if conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone():
                flash("Ce numéro de téléphone est déjà utilisé.", "error")
                return redirect(url_for("register_artisan"))
            if email and conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                flash("Cette adresse e-mail est déjà utilisée.", "error")
                return redirect(url_for("register_artisan"))

            lat, lon = _geocode_zone(address, "")

            store = storage.get_storage()
            photo_url = photo
            if photo:
                try:
                    photo_url = store.upload("photo", photo)
                except ValueError as exc:
                    flash(f"Photo invalide : {exc}", "error")
                    return redirect(url_for("register_artisan"))

            conn.execute(
                "INSERT INTO users (phone, email, password_hash, role, full_name, profession,"
                " skills, years_experience, bio, city, zone_intervention, latitude, longitude,"
                " hourly_rate, is_verified, is_active, account_status, verification_status,"
                " photo_url, availability_status, available_days)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (phone, email or None, generate_password_hash(account_password), role,
                 full_name, profession, specialite, experience, bio, address,
                 rayon, lat, lon, hourly_rate,
                 0 if verif_on else 1, 1, 'ACTIVE',
                 VERIF_PENDING if verif_on else VERIF_APPROVED,
                 photo_url, availability_status, available_days_str))
            conn.commit()

            artisan = conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
            artisan_id = artisan["id"]

            for doc_type, data_uri, name in (
                (DOC_IDENTITY, identity_doc, "piece-identite"),
                (DOC_PROFESSIONAL, professional_doc, "justificatif-pro"),
            ):
                if not data_uri:
                    continue
                err = _store_technician_document(conn, store, artisan_id, doc_type, data_uri, name)
                if err:
                    conn.rollback()
                    conn.execute("DELETE FROM users WHERE id = ?", (artisan_id,))
                    conn.commit()
                    flash(f"Document invalide : {err}", "error")
                    return redirect(url_for("register_artisan"))

            services_ids = request.form.getlist("services")
            try:
                _save_artisan_services(conn, artisan_id, services_ids)
            except ValueError as exc:
                conn.rollback()
                flash(f"Services invalides : {exc}", "error")
                return redirect(url_for("register_artisan"))

            if verif_on:
                _notify_admins_new_technician(conn, artisan_id, full_name, profession, address)
            conn.commit()
        finally:
            conn.close()

        if verif_on:
            flash("Votre dossier est enregistré. Il est en cours de vérification par FixPro.", "success")
        else:
            flash("Bienvenue dans FixPro.", "success")
        session["user_id"] = artisan_id
        session.permanent = True
        if request.form.get("after_submit") == "home":
            return redirect(url_for("index"))
        if verif_on:
            return redirect(url_for("artisan_pending"))
        return redirect(url_for("artisan_dashboard"))

    return render_template("register_artisan.html", categories=categories,
                           all_services=all_services,
                           require_docs=_verification_enabled())


def _send_admin_notification(subject, body):
    """Envoie un email a l'admin si la configuration SMTP est presente."""
    host = app.config.get("SMTP_HOST", "")
    port = app.config.get("SMTP_PORT", 587)
    user = app.config.get("SMTP_USER", "")
    password = app.config.get("SMTP_PASSWORD", "")
    to = app.config.get("ADMIN_EMAIL", "")
    if not all([host, user, password, to]):
        logger.info("Notification admin (pas d'email configure) : %s", subject)
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to], msg.as_bytes())
        logger.info("Notification admin envoyee a %s", to)
    except Exception as exc:  # pragma: no cover
        logger.exception("Echec envoi notification admin : %s", exc)


def _finalize_artisan_registration(wizard):
    """Inscrit l'artisan et ses documents, puis redirige vers l'attente."""
    required = ["first_name", "last_name", "phone", "email", "identity_doc",
                "profession", "city", "quartier", "diploma_doc"]
    for field in required:
        if not wizard.get(field):
            flash("Certaines informations sont manquantes. Veuillez recommencer.", "error")
            return redirect(url_for("register_artisan"))

    conn = get_db_connection()
    try:
        if conn.execute("SELECT id FROM users WHERE phone = ?", (wizard["phone"],)).fetchone():
            flash("Ce numero de telephone est deja utilise.", "error")
            return redirect(url_for("register_artisan"))

        full_name = f"{wizard['civility']} {wizard['first_name']} {wizard['last_name']}".strip()
        # Mot de passe temporaire aleatoire ; l'artisan le recoit par email si SMTP configure.
        temp_password = secrets.token_urlsafe(12)
        password = temp_password
        latitude, longitude = _geocode_zone(wizard["city"], wizard["quartier"])

        conn.execute(
            "INSERT INTO users (email, phone, password_hash, role, full_name, civility,"
            " profession, skills, city, quartier, zone_intervention, mobility,"
            " years_experience, bio, hourly_rate, latitude, longitude, is_verified, is_active)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (wizard["email"], wizard["phone"], generate_password_hash(password),
             "technician", full_name, wizard["civility"], wizard["profession"],
             wizard["skills"], wizard["city"], wizard["quartier"],
             wizard["zone_intervention"], wizard["mobility"],
             wizard["years_experience"], wizard["bio"], 0, latitude, longitude, 1, 1))
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
        logger.exception("Echec de l'inscription artisan : %s", exc)
        flash("Une erreur est survenue lors de l'inscription. Veuillez reessayer ou contacter le support.", "error")
        return redirect(url_for("register_artisan"))
    finally:
        conn.close()

    session.pop("artisan_wizard", None)
    _send_admin_notification(
        f"[FixPro] Nouvelle inscription artisan : {full_name}",
        f"Un nouvel artisan s'est inscrit sur FixPro.\n\n"
        f"Nom : {full_name}\n"
        f"Metier : {wizard.get('profession', 'Non precise')}\n"
        f"Telephone : {wizard.get('phone', '')}\n"
        f"Ville : {wizard.get('city', '')}\n"
        f"Quartier : {wizard.get('quartier', '')}\n\n"
        f"Connectez-vous au tableau de bord pour valider son inscription.")
    flash("Votre demande d'inscription a bien ete recue. L'equipe FixPro va verifier vos informations.", "success")
    return redirect(url_for("artisan_pending"))


@app.route("/artisan-pending")
def artisan_pending():
    """Page de suivi de la verification du dossier technicien."""
    user = get_current_user()
    if not user or not _is_technician(user):
        return redirect(url_for("login"))
    if (user.get("verification_status") or "").upper() == VERIF_APPROVED or user.get("is_verified"):
        return redirect(url_for("artisan_dashboard"))
    return _render_technician_verification(user)


def _render_technician_verification(user):
    status = (user.get("verification_status") or "PENDING_REVIEW").upper()
    conn = get_db_connection()
    try:
        docs = _technician_documents_by_type(conn, user["id"])
    finally:
        conn.close()
    doc_rows = []
    for dtype in REQUIRED_DOC_TYPES:
        row = docs.get(dtype)
        doc_rows.append({
            "type": dtype,
            "label": _DOC_LABELS[dtype],
            "status": ((row["status"] if row else "missing") or "pending").lower(),
            "rejection_reason": row["rejection_reason"] if row else None,
        })
    checklist = {
        "phone": bool(user.get("phone")),
        "email": bool(user.get("email")),
        "identity": docs.get(DOC_IDENTITY) is not None,
        "professional": docs.get(DOC_PROFESSIONAL) is not None,
    }
    return render_template("technician_verification_status.html",
                           user=user, status=status, documents=doc_rows,
                           checklist=checklist,
                           can_resubmit=status in (VERIF_REJECTED, VERIF_REVISION))


@app.route("/api/mobile/register", methods=["POST"])
@limiter.limit("10 per hour")
def api_mobile_register():
    """Inscription artisan depuis l'application mobile (JSON)."""
    data = request.get_json(silent=True) or {}
    required = ["first_name", "last_name", "phone", "password", "profession", "city", "quartier", "email"]
    if _verification_enabled():
        required += ["identity_doc", "diploma_doc"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": "Champs manquants", "missing": missing}), 400

    password = data["password"].strip()
    if len(password) < 6:
        return jsonify({"error": "Le mot de passe doit faire au moins 6 caracteres."}), 400

    phone = _phone_with_prefix(data["phone"])
    if not phone or len(phone.replace("+", "").replace(" ", "")) < 8:
        return jsonify({"error": "Numero de telephone invalide"}), 400

    conn = get_db_connection()
    try:
        if conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone():
            return jsonify({"error": "Ce numero est deja inscrit"}), 409
    finally:
        conn.close()

    wizard = {
        "civility": data.get("civility", "").strip(),
        "first_name": data["first_name"].strip(),
        "last_name": data["last_name"].strip(),
        "phone": phone,
        "password": password,
        "email": data.get("email", "").strip(),
        "profession": data["profession"].strip(),
        "skills": data.get("skills", "").strip(),
        "years_experience": _to_int(data.get("years_experience", 0)),
        "bio": data.get("bio", "").strip(),
        "city": data["city"].strip(),
        "quartier": data["quartier"].strip(),
        "zone_intervention": data.get("zone_intervention", "").strip(),
        "mobility": data.get("mobility", "").strip(),
        "identity_doc": data.get("identity_doc", "").strip(),
        "identity_doc_name": data.get("identity_doc_name", "identite").strip(),
        "diploma_doc": data.get("diploma_doc", "").strip(),
        "diploma_doc_name": data.get("diploma_doc_name", "diplome").strip(),
    }

    _finalize_artisan_registration_json(wizard)
    return jsonify({"ok": True, "message": "Inscription confirmee."}), 201


csrf.exempt(api_mobile_register)


@app.route("/api/mobile/login", methods=["POST"])
@limiter.limit("20 per hour")
def api_mobile_login():
    """Connexion technicien depuis l'application mobile (JSON + token 7 jours)."""
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "").strip()
    password = data.get("password", "")

    if not phone or not password:
        return jsonify({"error": "Identifiants manquants"}), 400

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE phone = ? AND role = 'technician'",
            (phone,)).fetchone()
    finally:
        conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Identifiants incorrects"}), 401

    if user["account_status"] != "ACTIVE":
        return jsonify({"error": "Votre compte FixPro est actuellement suspendu. Veuillez contacter l'administration."}), 403

    token = _generate_mobile_token(user)
    return jsonify({
        "ok": True,
        "token": token,
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "role": user["role"],
            "account_status": user["account_status"],
        }
    }), 200


@app.route("/api/mobile/verify", methods=["GET"])
@limiter.limit("60 per hour")
def api_mobile_verify():
    """Verifie un token mobile et retourne le compte s'il est valide."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Token manquant"}), 401

    token = auth.split(" ", 1)[1].strip()
    user, reason = _verify_mobile_token(token)

    if reason == "expired":
        return jsonify({"error": "Session expiree", "reason": "expired"}), 401
    if reason:
        return jsonify({"error": "Token invalide", "reason": reason}), 401

    return jsonify({
        "ok": True,
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "role": user["role"],
            "account_status": user["account_status"],
        }
    }), 200


csrf.exempt(api_mobile_login)
csrf.exempt(api_mobile_verify)


def _finalize_artisan_registration_json(wizard):
    """Version API JSON de l'inscription d'un technicien depuis l'application mobile.

    Le compte est cree actif pour acceder directement au tableau de bord.
    """
    full_name = f"{wizard['civility']} {wizard['first_name']} {wizard['last_name']}".strip()
    latitude, longitude = _geocode_zone(wizard["city"], wizard["quartier"])

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO users (email, phone, password_hash, role, full_name, civility,"
            " profession, skills, city, quartier, zone_intervention, mobility,"
            " years_experience, bio, hourly_rate, latitude, longitude, account_status,"
            " is_verified, is_active, verification_status,"
            " availability_status, available_days)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (wizard["email"], wizard["phone"], generate_password_hash(wizard["password"]),
             "technician", full_name, wizard["civility"], wizard["profession"],
             wizard["skills"], wizard["city"], wizard["quartier"],
             wizard["zone_intervention"], wizard["mobility"],
             wizard["years_experience"], wizard["bio"], 0, latitude, longitude,
             "ACTIVE",
             0 if _verification_enabled() else 1, 1,
             VERIF_PENDING if _verification_enabled() else VERIF_APPROVED,
             wizard.get("availability_status") or "hors_ligne",
             wizard.get("available_days") or ""))

        artisan = conn.execute(
            "SELECT id FROM users WHERE phone = ?", (wizard["phone"],)).fetchone()
        artisan_id = artisan["id"]

        for doc_type, field, name_field in [
            (DOC_IDENTITY, "identity_doc", "identity_doc_name"),
            (DOC_PROFESSIONAL, "diploma_doc", "diploma_doc_name"),
        ]:
            mime, ext, encoded = _parse_base64_file(wizard.get(field, ""))
            if encoded:
                file_name = (wizard.get(name_field, "") or f"{doc_type}{ext}").strip()
                conn.execute(
                    "INSERT INTO technician_documents (technician_id, document_type,"
                    " file_name, original_file_name, mime_type, file_size, content_base64, status)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
                    (artisan_id, doc_type, file_name, file_name, mime,
                     (len(encoded) * 3) // 4, encoded))

        admins = conn.execute("SELECT id FROM users WHERE role = 'admin'").fetchall()
        for admin in admins:
            create_notification(
                admin["id"],
                "Nouvelle inscription technicien",
                f"{full_name} ({wizard['profession']}, {wizard['city']}) demande a rejoindre FixPro.",
                "info",
                f"technician:{artisan_id}",
                conn=conn)

        conn.commit()
    finally:
        conn.close()

    _send_admin_notification(
        f"[FixPro] Nouvelle inscription technicien : {full_name}",
        f"Un nouveau technicien s'est inscrit depuis l'application mobile.\n\n"
        f"Nom : {full_name}\n"
        f"Metier : {wizard.get('profession', 'Non precise')}\n"
        f"Telephone : {wizard.get('phone', '')}\n"
        f"Ville : {wizard.get('city', '')}\n"
        f"Quartier : {wizard.get('quartier', '')}\n\n"
        f"Connectez-vous au tableau de bord pour valider son inscription.")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Ecran de connexion dedie a l'administration."""
    if session.get("user_id"):
        user = get_current_user()
        if user and user["role"] == "admin":
            if session.get("admin_unlocked"):
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("admin_unlock"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        conn = get_db_connection()
        try:
            admin = conn.execute(
                "SELECT * FROM users WHERE email = ? AND role = 'admin'",
                (email,)).fetchone()
        finally:
            conn.close()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["user_id"] = admin["id"]
            session["admin_unlocked"] = False
            session.permanent = True
            return redirect(url_for("admin_unlock"))
        flash("Email ou mot de passe incorrect.", "error")

    return render_template("admin_login.html")


@app.route("/admin/unlock", methods=["GET", "POST"])
@admin_required
def admin_unlock():
    """Verrou secondaire du tableau de bord administrateur."""
    if request.method == "POST":
        password = request.form.get("password", "")
        user = get_current_user()
        if user and check_password_hash(user["password_hash"], password):
            session["admin_unlocked"] = True
            flash("Tableau de bord deverrouille.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Mot de passe incorrect.", "error")
    return render_template("admin_unlock.html")


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

    # Le flux doit avoir demarre via /admin/login/google (anti-rejeu).
    if not session.pop("oauth_admin", False):
        flash("Session de connexion invalide. Reessayez.", "error")
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
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin")
@login_required
@admin_required
def admin_root():
    """Racine admin redirige vers le tableau de bord Flask."""
    return redirect(url_for("admin_dashboard"))


def _mock_admin_dashboard_data():
    """Donnees fictives pour visualiser le dashboard admin."""
    return {
        "stats": {
            "pending_requests": 6,
            "pending_requests_delta": 2,
            "available_artisans": 8,
            "interventions_in_progress": 4,
            "interventions_delta": 1,
            "today_commission": 25000,
            "today_commission_delta": 12,
        },
        "financial": {
            "today_paid": 250000,
            "today_commission": 25000,
            "today_paid_to_artisans": 225000,
        },
        "pending_requests": [
            {"id": 1048, "reference": "#1048", "client_name": "Mamadou Diallo", "client_phone": "623 45 67 89", "service": "Depannage climatisation", "category": "Climatisation", "city": "Cocody", "quartier": "Riviera 3", "requested_date": "Aujourd'hui", "requested_time": "14:00"},
            {"id": 1049, "reference": "#1049", "client_name": "Fatou Camara", "client_phone": "628 11 22 33", "service": "Plomberie", "category": "Plomberie", "city": "Riviera", "quartier": "Riviera 2", "requested_date": "Aujourd'hui", "requested_time": "15:30"},
            {"id": 1050, "reference": "#1050", "client_name": "Ibrahima Sylla", "client_phone": "620 98 76 54", "service": "Electricite", "category": "Electricite", "city": "Angre", "quartier": "7eme tranche", "requested_date": "Aujourd'hui", "requested_time": "17:00"},
            {"id": 1051, "reference": "#1051", "client_name": "Aissatou Diallo", "client_phone": "621 33 22 11", "service": "Climatisation", "category": "Climatisation", "city": "Marcory", "quartier": "Kipe Centre", "requested_date": "Demain", "requested_time": "09:00"},
            {"id": 1052, "reference": "#1052", "client_name": "Mariam Conde", "client_phone": "622 77 88 99", "service": "Plomberie", "category": "Plomberie", "city": "Plateau", "quartier": "Centre", "requested_date": "Demain", "requested_time": "10:30"},
            {"id": 1053, "reference": "#1053", "client_name": "Karim Bah", "client_phone": "625 55 44 33", "service": "Electricite", "category": "Electricite", "city": "Deux-Plateaux", "quartier": "Centre", "requested_date": "Demain", "requested_time": "14:00"},
        ],
        "in_progress": [
            {"id": 1039, "reference": "#1039", "client_name": "Aissata K.", "artisan_name": "Ousmane Sylla", "service": "Depannage climatisation", "status_label": "En cours"},
            {"id": 1040, "reference": "#1040", "client_name": "Karim B.", "artisan_name": "Fatoumata Camara", "service": "Installation electrique", "status_label": "Diagnostic"},
            {"id": 1041, "reference": "#1041", "client_name": "Mariam C.", "artisan_name": "Ibrahim Sory", "service": "Reparation plomberie", "status_label": "En cours"},
            {"id": 1042, "reference": "#1042", "client_name": "Mamadou D.", "artisan_name": "Kadiatou Barry", "service": "Entretien climatisation", "status_label": "En cours"},
        ],
        "available_artisans": [
            {"id": 1, "full_name": "Ousmane Sylla", "profession": "Frigoriste", "avg_rating": 4.9, "interventions": 89, "distance": "1,8"},
            {"id": 2, "full_name": "Kadiatou Barry", "profession": "Frigoriste", "avg_rating": 4.8, "interventions": 64, "distance": "2,4"},
            {"id": 3, "full_name": "Fatoumata Camara", "profession": "Electricienne", "avg_rating": 4.7, "interventions": 52, "distance": "2,7"},
            {"id": 4, "full_name": "Ibrahim Sory", "profession": "Plombier", "avg_rating": 4.9, "interventions": 71, "distance": "3,0"},
            {"id": 5, "full_name": "Lamine Camara", "profession": "Serrurier", "avg_rating": 4.8, "interventions": 43, "distance": "3,6"},
            {"id": 6, "full_name": "Mamadou Diallo", "profession": "Chauffagiste", "avg_rating": 4.6, "interventions": 38, "distance": "3,9"},
        ],
        "recent_activities": [
            {"title": "Nouvelle demande", "meta": "Mamadou Diallo a envoye une demande de depannage climatisation.", "time": "Il y a 5 min", "color": "#ef4444", "icon": "file_plus"},
            {"title": "Intervention acceptee", "meta": "Ousmane Sylla a accepte l'intervention #1039.", "time": "Il y a 12 min", "color": "#10b981", "icon": "user_check"},
            {"title": "Paiement recu", "meta": "Paiement de 50 000 GNF recu pour l'intervention #1038.", "time": "Il y a 20 min", "color": "#8b5cf6", "icon": "credit_card"},
            {"title": "Intervention terminee", "meta": "Ibrahim Sory a termine l'intervention #1037.", "time": "Il y a 35 min", "color": "#10b981", "icon": "check_circle"},
            {"title": "Avis laisse", "meta": "Aissata K. a laisse un avis 5 etoiles.", "time": "Il y a 1 h", "color": "#f59e0b", "icon": "star"},
            {"title": "Intervention en cours", "meta": "Mission #1036 en cours d'intervention.", "time": "Il y a 1 h 30", "color": "#f59e0b", "icon": "clock"},
        ],
    }


def _period_bounds(period):
    """(debut_iso, libelle, debut_periode_precedente_iso) pour le selecteur."""
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.isoformat(), "Aujourd'hui", (start - timedelta(days=1)).isoformat()
    if period == "7d":
        start = now - timedelta(days=7)
        return start.isoformat(), "7 derniers jours", (start - timedelta(days=7)).isoformat()
    if period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start.isoformat(), "Cette annee", start.replace(year=start.year - 1).isoformat()
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev = (start - timedelta(seconds=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start.isoformat(), "Ce mois", prev.isoformat()
    start = now - timedelta(days=30)
    return start.isoformat(), "30 derniers jours", (start - timedelta(days=30)).isoformat()


def _pct_delta(current, previous):
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def _safe_url(endpoint, **kw):
    """url_for tolerant : renvoie '#' si la route n'existe pas encore."""
    try:
        return url_for(endpoint, **kw)
    except Exception:
        return "#"


def _admin_sidebar_badges(conn, admin_id):
    def one(sql, params=()):
        row = conn.execute(sql, params).fetchone()
        return row["n"] if row else 0
    return {
        "validations": one(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'technician' AND verification_status = ?",
            (VERIF_PENDING,)),
        "notifications": one(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0", (admin_id,)),
        "reclamations": one(
            "SELECT COUNT(*) AS n FROM complaints WHERE status IN ('new', 'in_progress')"),
        "messages": one(
            "SELECT COUNT(*) AS n FROM conversations WHERE status IN ('needs_human', 'admin_active')"),
    }


_INTERVENTION_ACTIVE = (
    "assigned", "accepted", "en_route", "on_the_way", "arrived", "in_progress")


@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    """Tableau de bord admin : abonnements, paiements, activite, alertes."""
    user = get_current_user()
    period = request.args.get("period", "month")
    start_iso, period_label, prev_start_iso = _period_bounds(period)
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    soon = (now + timedelta(days=7)).isoformat()

    conn = get_db_connection()
    try:
        def scalar(sql, params=()):
            row = conn.execute(sql, params).fetchone()
            if not row:
                return 0
            return list(row.values())[0]

        tech_actifs = scalar(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'technician'"
            " AND is_active = 1 AND account_status = 'ACTIVE'")
        tech_actifs_prev = scalar(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'technician'"
            " AND is_active = 1 AND account_status = 'ACTIVE' AND created_at < ?", (start_iso,))
        abos_actifs = scalar(
            "SELECT COUNT(*) AS n FROM technician_subscriptions WHERE status = 'ACTIVE'")
        abos_expires = scalar(
            "SELECT COUNT(*) AS n FROM technician_subscriptions WHERE status = 'EXPIRED'")
        paiements_mois = int(scalar(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM subscription_payments"
            " WHERE status = 'paid' AND paid_at >= ?", (month_start,)) or 0)
        paiements_mois_prev = int(scalar(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM subscription_payments"
            " WHERE status = 'paid' AND paid_at >= ? AND paid_at < ?",
            (prev_start_iso, start_iso)) or 0)
        nouveaux_clients = scalar(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'client' AND created_at >= ?", (start_iso,))
        nouveaux_clients_prev = scalar(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'client'"
            " AND created_at >= ? AND created_at < ?", (prev_start_iso, start_iso))
        interventions_cours = scalar(
            "SELECT COUNT(*) AS n FROM requests WHERE LOWER(status) IN (%s)"
            % ",".join("?" for _ in _INTERVENTION_ACTIVE), _INTERVENTION_ACTIVE)

        kpis = [
            {"label": "Techniciens actifs", "value": tech_actifs,
             "delta": _pct_delta(tech_actifs, tech_actifs_prev), "icon": "users", "tone": "blue",
             "href": _safe_url("admin_artisans")},
            {"label": "Abonnements actifs", "value": abos_actifs, "delta": None,
             "icon": "shield_check", "tone": "green", "href": _safe_url("admin_subscriptions")},
            {"label": "Abonnements expires", "value": abos_expires, "delta": None,
             "icon": "clock", "tone": "orange", "sub": "A renouveler",
             "href": _safe_url("admin_subscriptions", filter="expired")},
            {"label": "Paiements ce mois", "value": paiements_mois,
             "delta": _pct_delta(paiements_mois, paiements_mois_prev), "icon": "wallet",
             "tone": "violet", "money": True, "href": _safe_url("admin_subscription_payments")},
            {"label": "Nouveaux clients", "value": nouveaux_clients,
             "delta": _pct_delta(nouveaux_clients, nouveaux_clients_prev), "icon": "user_plus",
             "tone": "blue", "href": _safe_url("admin_clients")},
            {"label": "Interventions en cours", "value": interventions_cours, "delta": None,
             "icon": "wrench", "tone": "red", "href": _safe_url("admin_requests")},
        ]

        rev_rows = conn.execute(
            "SELECT SUBSTR(paid_at, 1, 10) AS jour, COALESCE(SUM(amount), 0) AS montant"
            " FROM subscription_payments WHERE status = 'paid' AND paid_at >= ?"
            " GROUP BY SUBSTR(paid_at, 1, 10) ORDER BY jour", (start_iso,)).fetchall()
        revenue_series = [{"date": r["jour"], "amount": int(r["montant"] or 0)} for r in rev_rows]
        revenue_total = sum(p["amount"] for p in revenue_series)
        revenue_prev = int(scalar(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM subscription_payments"
            " WHERE status = 'paid' AND paid_at >= ? AND paid_at < ?",
            (prev_start_iso, start_iso)) or 0)

        plan_rows = conn.execute(
            "SELECT p.name, p.code, COUNT(s.id) AS n FROM subscription_plans p"
            " LEFT JOIN technician_subscriptions s ON s.plan_id = p.id AND s.status = 'ACTIVE'"
            " WHERE p.is_active = 1 GROUP BY p.id ORDER BY p.sort_order").fetchall()
        repartition = [{"name": r["name"], "code": r["code"], "count": r["n"]} for r in plan_rows]
        repartition_total = sum(r["count"] for r in repartition)

        def sub_count(where, params=()):
            return scalar("SELECT COUNT(*) AS n FROM technician_subscriptions WHERE " + where, params)
        s_actifs = sub_count("status = 'ACTIVE'")
        s_expirant = sub_count("status = 'ACTIVE' AND end_date IS NOT NULL AND end_date <= ?", (soon,))
        s_expires = sub_count("status = 'EXPIRED'")
        s_impayes = sub_count("status = 'PAST_DUE'")
        s_total = (s_actifs + s_expires + s_impayes + sub_count("status = 'SUSPENDED'")
                   + sub_count("status IN ('TRIAL', 'CANCELLED')"))
        statut_abos = [
            {"label": "Actifs", "count": s_actifs, "tone": "green"},
            {"label": "Expirant bientot (7 jours)", "count": s_expirant, "tone": "orange"},
            {"label": "Expires", "count": s_expires, "tone": "red"},
            {"label": "Impayes", "count": s_impayes, "tone": "violet"},
        ]
        for s in statut_abos:
            s["pct"] = round(s["count"] / s_total * 100) if s_total else 0

        derniers_paiements = conn.execute(
            "SELECT sp.amount, sp.status, sp.paid_at, sp.created_at, sp.payment_method,"
            " u.full_name AS tech_name, pl.name AS plan_name"
            " FROM subscription_payments sp"
            " LEFT JOIN users u ON u.id = sp.user_id"
            " LEFT JOIN subscription_plans pl ON pl.id = sp.plan_id"
            " ORDER BY COALESCE(sp.paid_at, sp.created_at) DESC LIMIT 5").fetchall()

        interventions_recentes = conn.execute(
            "SELECT r.id, r.title, r.category, r.status, r.address, r.created_at,"
            " c.full_name AS client_name, a.full_name AS tech_name FROM requests r"
            " LEFT JOIN users c ON c.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            " ORDER BY r.created_at DESC LIMIT 5").fetchall()

        demandes_validation = conn.execute(
            "SELECT id, full_name, profession, city, quartier, photo_url, created_at"
            " FROM users WHERE role = 'technician' AND verification_status = ?"
            " ORDER BY created_at DESC LIMIT 6", (VERIF_PENDING,)).fetchall()

        alertes = [
            {"label": "Paiements echoues", "count": scalar(
                "SELECT COUNT(*) AS n FROM subscription_payments WHERE status = 'failed'"),
             "tone": "red", "sub": "Necessitent une action",
             "href": _safe_url("admin_subscription_payments", filter="failed")},
            {"label": "Abonnements expires", "count": s_expires, "tone": "orange",
             "sub": "Necessitent une action", "href": _safe_url("admin_subscriptions", filter="expired")},
            {"label": "Abonnements expirant bientot", "count": s_expirant, "tone": "amber",
             "sub": "Dans les 7 prochains jours", "href": _safe_url("admin_subscriptions", filter="expiring")},
            {"label": "Techniciens en attente", "count": scalar(
                "SELECT COUNT(*) AS n FROM users WHERE role = 'technician' AND verification_status = ?",
                (VERIF_PENDING,)),
             "tone": "blue", "sub": "Demandes a valider", "href": _safe_url("admin_artisans", filter="pending")},
            {"label": "Reclamations ouvertes", "count": scalar(
                "SELECT COUNT(*) AS n FROM complaints WHERE status IN ('new', 'in_progress')"),
             "tone": "violet", "sub": "En attente de traitement", "href": _safe_url("admin_complaints")},
        ]

        badges = _admin_sidebar_badges(conn, user["id"])
    finally:
        conn.close()

    return render_template(
        "admin_dashboard.html",
        user=user, active="dashboard", badges=badges,
        period=period, period_label=period_label, today=today,
        kpis=kpis,
        revenue_series=revenue_series, revenue_total=revenue_total,
        revenue_delta=_pct_delta(revenue_total, revenue_prev),
        repartition=repartition, repartition_total=repartition_total,
        statut_abos=statut_abos, statut_total=s_total,
        derniers_paiements=derniers_paiements,
        interventions_recentes=interventions_recentes,
        demandes_validation=demandes_validation,
        alertes=alertes,
    )
# ===========================================================================
# Dashboard admin v2 - pages abonnements / paiements / reclamations
# ===========================================================================

_PLAN_PRICE_MAX = 5_000_000


@app.route("/admin/abonnements")
@login_required
@admin_required
def admin_subscriptions():
    """Liste des abonnements techniciens + gestion des plans."""
    user = get_current_user()
    flt = request.args.get("filter", "")
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(days=7)).isoformat()

    where, params = "1 = 1", []
    if flt == "active":
        where = "s.status = 'ACTIVE'"
    elif flt == "expired":
        where = "s.status = 'EXPIRED'"
    elif flt == "expiring":
        where, params = "s.status = 'ACTIVE' AND s.end_date IS NOT NULL AND s.end_date <= ?", [soon]
    elif flt == "past_due":
        where = "s.status = 'PAST_DUE'"
    elif flt == "suspended":
        where = "s.status = 'SUSPENDED'"

    conn = get_db_connection()
    try:
        subs = conn.execute(
            "SELECT s.id, s.status, s.start_date, s.end_date, s.auto_renew,"
            " u.id AS tech_id, u.full_name AS tech_name, u.phone AS tech_phone, u.profession,"
            " p.name AS plan_name, p.price_month"
            " FROM technician_subscriptions s"
            " JOIN users u ON u.id = s.technician_id"
            " LEFT JOIN subscription_plans p ON p.id = s.plan_id"
            " WHERE " + where +
            " ORDER BY (s.end_date IS NULL), s.end_date ASC, s.created_at DESC LIMIT 300",
            params).fetchall()
        plans = conn.execute(
            "SELECT p.*,"
            " (SELECT COUNT(*) FROM technician_subscriptions s"
            "  WHERE s.plan_id = p.id AND s.status = 'ACTIVE') AS subscribers"
            " FROM subscription_plans p ORDER BY p.sort_order").fetchall()

        def cnt(w, pr=()):
            return conn.execute(
                "SELECT COUNT(*) AS n FROM technician_subscriptions WHERE " + w, pr).fetchone()["n"]
        counts = {
            "all": cnt("1 = 1"),
            "active": cnt("status = 'ACTIVE'"),
            "expiring": cnt("status = 'ACTIVE' AND end_date IS NOT NULL AND end_date <= ?", (soon,)),
            "expired": cnt("status = 'EXPIRED'"),
            "past_due": cnt("status = 'PAST_DUE'"),
        }
        badges = _admin_sidebar_badges(conn, user["id"])
    finally:
        conn.close()
    return render_template("admin_subscriptions.html", user=user, badges=badges,
                           subs=subs, plans=plans, counts=counts, filter=flt)


@app.route("/admin/abonnements/plans/<int:plan_id>", methods=["POST"])
@login_required
@admin_required
@limiter.limit("60 per hour", methods=["POST"])
def admin_update_plan(plan_id):
    """Modification d'un plan d'abonnement (prix, fonctionnalites, activation)."""
    user = get_current_user()
    name = (request.form.get("name") or "").strip()
    price = _to_int(request.form.get("price_month"), -1)
    features = (request.form.get("features") or "").strip()
    is_active = 1 if request.form.get("is_active") else 0
    if not name or price < 0 or price > _PLAN_PRICE_MAX:
        flash("Nom et prix valides obligatoires.", "error")
        return redirect(url_for("admin_subscriptions"))
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE subscription_plans SET name = ?, price_month = ?, features = ?,"
            " is_active = ?, updated_at = ? WHERE id = ?",
            (name, price, features, is_active, now_iso(), plan_id))
        conn.commit()
        log_admin_action(user["id"], user.get("email"), "update_plan",
                         "subscription_plan", plan_id, "%s : %s GNF" % (name, price))
        flash("Plan mis a jour.", "success")
    finally:
        conn.close()
    return redirect(url_for("admin_subscriptions"))


@app.route("/admin/abonnements/paiements")
@login_required
@admin_required
def admin_subscription_payments():
    """Historique des paiements d'abonnement."""
    user = get_current_user()
    flt = request.args.get("filter", "")
    where, params = "1 = 1", []
    if flt in ("paid", "pending", "failed", "refunded"):
        where, params = "sp.status = ?", [flt]
    conn = get_db_connection()
    try:
        pays = conn.execute(
            "SELECT sp.id, sp.amount, sp.status, sp.paid_at, sp.created_at,"
            " sp.payment_method, sp.transaction_reference,"
            " u.full_name AS tech_name, u.phone AS tech_phone, p.name AS plan_name"
            " FROM subscription_payments sp"
            " LEFT JOIN users u ON u.id = sp.user_id"
            " LEFT JOIN subscription_plans p ON p.id = sp.plan_id"
            " WHERE " + where +
            " ORDER BY COALESCE(sp.paid_at, sp.created_at) DESC LIMIT 300", params).fetchall()

        def one(sql, pr=()):
            return conn.execute(sql, pr).fetchone()["n"]
        totals = {
            "collected": int(conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS n FROM subscription_payments"
                " WHERE status = 'paid'").fetchone()["n"] or 0),
            "all": one("SELECT COUNT(*) AS n FROM subscription_payments"),
            "paid": one("SELECT COUNT(*) AS n FROM subscription_payments WHERE status = 'paid'"),
            "pending": one("SELECT COUNT(*) AS n FROM subscription_payments WHERE status = 'pending'"),
            "failed": one("SELECT COUNT(*) AS n FROM subscription_payments WHERE status = 'failed'"),
        }
        badges = _admin_sidebar_badges(conn, user["id"])
    finally:
        conn.close()
    return render_template("admin_subscription_payments.html", user=user, badges=badges,
                           pays=pays, totals=totals, filter=flt)


_COMPLAINT_STATUSES = ("new", "in_progress", "resolved", "closed")


@app.route("/admin/reclamations", methods=["GET", "POST"])
@login_required
@admin_required
@limiter.limit("60 per hour", methods=["POST"])
def admin_complaints():
    """Suivi et traitement des reclamations."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        if request.method == "POST":
            cid = request.form.get("complaint_id")
            new_status = request.form.get("status")
            note = (request.form.get("note") or "").strip()
            if new_status in _COMPLAINT_STATUSES and cid:
                done = new_status in ("resolved", "closed")
                conn.execute(
                    "UPDATE complaints SET status = ?, resolution_note = ?,"
                    " resolved_at = ?, resolved_by = ? WHERE id = ?",
                    (new_status, note or None, now_iso() if done else None,
                     user["id"] if done else None, cid))
                conn.commit()
                log_admin_action(user["id"], user.get("email"), "update_complaint",
                                 "complaint", cid, new_status)
                flash("Reclamation mise a jour.", "success")
            return redirect(url_for("admin_complaints", filter=request.args.get("filter", "")))

        flt = request.args.get("filter", "")
        where = "1 = 1"
        if flt in _COMPLAINT_STATUSES:
            where = "c.status = '%s'" % flt
        rows = conn.execute(
            "SELECT c.*, cl.full_name AS client_name, cl.phone AS client_phone,"
            " t.full_name AS tech_name"
            " FROM complaints c"
            " LEFT JOIN users cl ON cl.id = c.client_id"
            " LEFT JOIN users t ON t.id = c.technician_id"
            " WHERE " + where + " ORDER BY c.created_at DESC LIMIT 300").fetchall()
        counts = {"all": conn.execute("SELECT COUNT(*) AS n FROM complaints").fetchone()["n"]}
        for s in _COMPLAINT_STATUSES:
            counts[s] = conn.execute(
                "SELECT COUNT(*) AS n FROM complaints WHERE status = ?", (s,)).fetchone()["n"]
        badges = _admin_sidebar_badges(conn, user["id"])
    finally:
        conn.close()
    return render_template("admin_complaints.html", user=user, badges=badges,
                           complaints=rows, counts=counts, filter=flt)


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

            def _set_status(status, is_active):
                conn.execute(
                    "UPDATE users SET account_status = ?, is_active = ? WHERE id = ?",
                    (status, 1 if is_active else 0, artisan_id))
                conn.commit()

            if action == "create":
                full_name = (request.form.get("full_name") or "").strip()
                phone = _phone_with_prefix((request.form.get("phone") or "").strip())
                email = (request.form.get("email") or "").strip().lower() or None
                profession = (request.form.get("profession") or "").strip()
                city = (request.form.get("city") or "").strip()
                zone = (request.form.get("zone_intervention") or "").strip()
                bio = (request.form.get("bio") or "").strip()
                years = request.form.get("years_experience") or "0"

                if not full_name or not phone or not profession or not city:
                    flash("Nom, telephone, metier et ville sont obligatoires.", "error")
                    return redirect(url_for("admin_artisans"))

                if conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone():
                    flash("Ce numero de telephone est deja utilise.", "error")
                    return redirect(url_for("admin_artisans"))

                temp_password = secrets.token_urlsafe(16)
                conn.execute(
                    "INSERT INTO users (email, phone, password_hash, role, full_name, profession,"
                    " city, zone_intervention, bio, years_experience, is_verified, is_active,"
                    " account_status, verification_status)"
                    " VALUES (?, ?, ?, 'technician', ?, ?, ?, ?, ?, ?, 0, 0, 'PENDING', ?)",
                    (email, phone, generate_password_hash(temp_password), full_name,
                     profession, city, zone, bio, int(years or 0), VERIF_PENDING))
                conn.commit()
                new_id = conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()["id"]
                log_admin_action(user["id"], user["email"], "create_technician", "user", new_id,
                                 f"Creation du technicien {full_name}")
                flash("Technicien cree. Il est en attente de validation.", "success")
                return redirect(url_for("admin_artisans"))

            artisan = conn.execute(
                "SELECT id, role, full_name, email, account_status, verification_status"
                " FROM users WHERE id = ? AND role IN ('artisan','technician')",
                (artisan_id,)).fetchone()
            if not artisan:
                flash("Technicien introuvable.", "error")
                return redirect(url_for("admin_artisans"))

            if action == "verify":
                if (artisan["role"] == "technician"
                        and _technician_has_documents(conn, artisan_id)
                        and not _technician_docs_all_approved(conn, artisan_id)):
                    flash("Validez d'abord la pièce d'identité et le justificatif professionnel.", "error")
                    return redirect(url_for("admin_artisan_detail", artisan_id=artisan_id))
                already_active = (artisan["account_status"] or "").upper() == "ACTIVE"
                if artisan["role"] == "technician" and not already_active:
                    _set_status("PENDING", 0)
                    token = _generate_activation_token(artisan["id"])
                    create_notification(
                        artisan["id"],
                        "Votre compte FixPro a ete valide",
                        "Vous pouvez maintenant activer votre compte et acceder a votre espace technicien.",
                        "info",
                        f"token:{token}",
                        conn=conn)
                else:
                    _set_status("ACTIVE", 1)
                    create_notification(
                        artisan["id"],
                        "Profil vérifié",
                        "Félicitations, votre profil FixPro est vérifié. Vous pouvez recevoir des demandes.",
                        "success",
                        conn=conn)
                conn.execute(
                    "UPDATE users SET is_verified = 1, verification_status = ? WHERE id = ?",
                    (VERIF_APPROVED, artisan_id))
                conn.commit()
                log_admin_action(user["id"], user["email"], "verify", "user", artisan_id,
                                 reason or "Validation du dossier technicien")
                flash("Technicien valide.", "success")
            elif action in ("reject_dossier", "revision_required"):
                if not reason:
                    flash("Merci d'indiquer le motif.", "error")
                    return redirect(url_for("admin_artisan_detail", artisan_id=artisan_id))
                new_status = VERIF_REJECTED if action == "reject_dossier" else VERIF_REVISION
                conn.execute(
                    "UPDATE users SET is_verified = 0, verification_status = ? WHERE id = ?",
                    (new_status, artisan_id))
                create_notification(
                    artisan["id"],
                    "Dossier à corriger" if new_status == VERIF_REVISION else "Dossier refusé",
                    f"Motif : {reason}",
                    "error",
                    conn=conn)
                conn.commit()
                log_admin_action(user["id"], user["email"], action, "user", artisan_id, reason)
                flash("Décision enregistrée.", "success")
            elif action == "approve":
                _set_status("ACTIVE", 1)
                conn.execute("UPDATE users SET is_verified = 1 WHERE id = ?", (artisan_id,))
                create_notification(
                    artisan["id"],
                    "Compte approuve",
                    "Votre compte FixPro a ete approuve. Vous pouvez maintenant vous connecter.",
                    "success",
                    conn=conn)
                conn.commit()
                log_admin_action(user["id"], user["email"], "approve", "user", artisan_id,
                                 reason or "Approbation du compte technicien")
                flash("Compte approuve et active.", "success")
            elif action == "reject":
                _set_status("DELETED", 0)
                log_admin_action(user["id"], user["email"], "reject", "user", artisan_id,
                                 reason or "Refus de l'inscription")
                flash("Inscription refusee.", "success")
            elif action == "active":
                _set_status("ACTIVE", 1)
                log_admin_action(user["id"], user["email"], "active", "user", artisan_id,
                                 reason or "Compte reactive")
                flash("Technicien actif.", "success")
            elif action == "pause":
                _set_status("PAUSED", 1)
                log_admin_action(user["id"], user["email"], "pause", "user", artisan_id,
                                 reason or "Compte mis en pause")
                flash("Technicien mis en pause.", "success")
            elif action == "suspend":
                _set_status("SUSPENDED", 0)
                log_admin_action(user["id"], user["email"], "suspend", "user", artisan_id,
                                 reason or "Suspension du compte")
                flash("Technicien suspendu.", "success")
            elif action == "delete":
                _set_status("DELETED", 0)
                log_admin_action(user["id"], user["email"], "delete", "user", artisan_id,
                                 reason or "Compte supprime")
                flash("Technicien supprime.", "success")
            return redirect(url_for("admin_artisans"))

        q = request.args.get("q", "").strip()
        status_filter = request.args.get("status", "").strip()
        city_filter = request.args.get("city", "").strip()
        profession_filter = request.args.get("profession", "").strip()

        where_parts = ["u.role IN ('artisan','technician')"]
        params = []
        if q:
            where_parts.append("(u.full_name LIKE ? OR u.phone LIKE ? OR u.email LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if status_filter == "pending":
            where_parts.append("u.is_verified = 0")
        elif status_filter:
            where_parts.append("u.account_status = ?")
            params.append(status_filter.upper())
        if city_filter:
            where_parts.append("u.city = ?")
            params.append(city_filter)
        if profession_filter:
            where_parts.append("u.profession = ?")
            params.append(profession_filter)

        where_clause = " WHERE " + " AND ".join(where_parts)
        artisans = conn.execute(
            "SELECT u.*,"
            " COUNT(DISTINCT req_completed.id) AS completed,"
            " COALESCE(AVG(r.rating), 0) AS avg_rating,"
            " COUNT(DISTINCT r.id) AS review_count,"
            " COUNT(DISTINCT d.id) AS doc_count"
            " FROM users u"
            " LEFT JOIN requests req_completed ON req_completed.artisan_id = u.id AND req_completed.status = 'completed'"
            " LEFT JOIN reviews r ON r.artisan_id = u.id"
            " LEFT JOIN technician_documents d ON d.technician_id = u.id"
            + where_clause +
            " GROUP BY u.id"
            " ORDER BY u.is_verified ASC, u.is_active DESC, u.created_at DESC",
            tuple(params)).fetchall()

        cities = conn.execute(
            "SELECT DISTINCT city FROM users WHERE role IN ('artisan','technician') AND city IS NOT NULL"
            " ORDER BY city").fetchall()
        professions = conn.execute(
            "SELECT DISTINCT profession FROM users WHERE role IN ('artisan','technician') AND profession IS NOT NULL"
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
            "SELECT * FROM users WHERE id = ? AND role IN ('artisan','technician')", (artisan_id,)).fetchone()
        if not artisan:
            flash("Technicien introuvable.", "error")
            return redirect(url_for("admin_artisans"))

        documents = conn.execute(
            "SELECT * FROM technician_documents WHERE technician_id = ? ORDER BY document_type, id",
            (artisan_id,)).fetchall()
        service_names = conn.execute(
            "SELECT s.name FROM artisan_services a JOIN services s ON s.id = a.service_id"
            " WHERE a.artisan_id = ? ORDER BY s.name", (artisan_id,)).fetchall()
        history = conn.execute(
            "SELECT * FROM admin_logs WHERE target_type = 'user' AND target_id = ?"
            " AND action IN ('verify','doc_approve','doc_reject','reject_dossier','revision_required','create_technician')"
            " ORDER BY id DESC LIMIT 30", (artisan_id,)).fetchall()
        docs_all_approved = _technician_docs_all_approved(conn, artisan_id)
    finally:
        conn.close()
    return render_template("admin_artisan_detail.html", user=user,
                           artisan=artisan, documents=documents,
                           service_names=[r["name"] for r in service_names],
                           history=history, docs_all_approved=docs_all_approved,
                           doc_labels=_DOC_LABELS)


@app.route("/admin/technicien/<int:tech_id>/document/<int:doc_id>/review", methods=["POST"])
@login_required
@admin_required
@limiter.limit("120 per hour", methods=["POST"])
def admin_technician_document_review(tech_id, doc_id):
    """Accepte ou refuse un document de verification d'un technicien."""
    admin = get_current_user()
    decision = (request.form.get("decision") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    if decision not in ("approve", "reject"):
        flash("Action invalide.", "error")
        return redirect(url_for("admin_artisan_detail", artisan_id=tech_id))
    if decision == "reject" and not reason:
        flash("Merci d'indiquer le motif du refus.", "error")
        return redirect(url_for("admin_artisan_detail", artisan_id=tech_id))

    conn = get_db_connection()
    try:
        doc = conn.execute(
            "SELECT * FROM technician_documents WHERE id = ? AND technician_id = ?",
            (doc_id, tech_id)).fetchone()
        if not doc:
            flash("Document introuvable.", "error")
            return redirect(url_for("admin_artisan_detail", artisan_id=tech_id))

        new_status = "approved" if decision == "approve" else "rejected"
        conn.execute(
            "UPDATE technician_documents SET status = ?, reviewed_at = ?, reviewed_by = ?,"
            " rejection_reason = ? WHERE id = ?",
            (new_status, now_iso(), admin["id"],
             reason if decision == "reject" else None, doc_id))
        if decision == "reject":
            conn.execute(
                "UPDATE users SET verification_status = ?, is_verified = 0 WHERE id = ?",
                (VERIF_REVISION, tech_id))
            create_notification(
                tech_id,
                "Document à corriger",
                f"Votre {_DOC_LABELS.get(doc['document_type'], 'document')} a été refusé. Motif : {reason}",
                "error", conn=conn)
        conn.commit()
        log_admin_action(admin["id"], admin["email"],
                         "doc_approve" if decision == "approve" else "doc_reject",
                         "user", tech_id,
                         f"{_DOC_LABELS.get(doc['document_type'], doc['document_type'])}"
                         + (f" — {reason}" if reason else ""))
    finally:
        conn.close()

    flash("Document mis à jour.", "success")
    return redirect(url_for("admin_artisan_detail", artisan_id=tech_id))


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

    import html as _html
    mime = (doc["mime_type"] or "image/jpeg").strip()
    if mime not in ("image/jpeg", "image/jpg", "image/png", "application/pdf"):
        mime = "image/jpeg"
    data = doc["content_base64"] or ""
    if not data.startswith("data:"):
        data = f"data:{mime};base64,{data}"
    elif not data.startswith(("data:image/", "data:application/pdf")):
        return "Document invalide.", 400

    # file_name est saisi par le technicien : il doit etre echappe.
    name = _html.escape(doc["file_name"] or "document")
    back = url_for('admin_artisan_detail', artisan_id=doc['technician_id'])
    body = "<img src=\"%s\" style=\"max-width:100%%;max-height:100vh;\" alt=\"Document\" />" % data
    if mime == "application/pdf":
        body = "<iframe src=\"%s\" style=\"width:100vw;height:100vh;border:0;\"></iframe>" % data
    return f"""<!doctype html>
<html lang="fr">
<head><meta charset="utf-8"><title>Document {name}</title></head>
<body style="margin:0;background:#000;display:grid;place-items:center;height:100vh;">
  {body}
  <a href="{back}" style="position:fixed;top:16px;left:16px;color:#fff;text-decoration:none;font-weight:700;">&larr; Retour</a>
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
            " COUNT(DISTINCT r.id) AS request_count"
            " FROM users u"
            " LEFT JOIN requests r ON r.client_id = u.id"
            + where_clause +
            " GROUP BY u.id"
            " ORDER BY u.created_at DESC", tuple(params)).fetchall()
    finally:
        conn.close()
    return render_template("admin_clients.html", user=user, clients=clients,
                           q=q, status_filter=status_filter)


@app.route("/admin/contacts", methods=["GET"])
@login_required
@admin_required
def admin_contacts():
    """Liste de tous les contacts clients provenant des fiches techniciens."""
    user = get_current_user()
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    conn = get_db_connection()
    try:
        where_parts = ["1=1"]
        params = []
        if q:
            where_parts.append("(c.first_name LIKE ? OR c.last_name LIKE ? OR c.phone LIKE ? OR a.full_name LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like, like])
        if status_filter:
            where_parts.append("c.status = ?")
            params.append(status_filter)
        where_clause = " WHERE " + " AND ".join(where_parts)
        contacts = conn.execute(
            "SELECT c.*, a.full_name AS artisan_name, a.profession AS artisan_profession,"
            " cl.full_name AS client_full_name"
            " FROM client_contacts c"
            " LEFT JOIN users a ON a.id = c.artisan_id"
            " LEFT JOIN users cl ON cl.id = c.client_user_id"
            + where_clause +
            " ORDER BY c.created_at DESC", tuple(params)).fetchall()
    finally:
        conn.close()
    return render_template("admin_contacts.html", user=user, contacts=contacts,
                           q=q, status_filter=status_filter)


@app.route("/admin/contacts/<int:contact_id>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_contact_detail(contact_id):
    """Detail d'un contact client : informations, statut et historique."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        contact = conn.execute(
            "SELECT c.*, a.full_name AS artisan_name, a.profession AS artisan_profession,"
            " cl.full_name AS client_full_name"
            " FROM client_contacts c"
            " LEFT JOIN users a ON a.id = c.artisan_id"
            " LEFT JOIN users cl ON cl.id = c.client_user_id"
            " WHERE c.id = ?", (contact_id,)).fetchone()
        if not contact:
            flash("Contact introuvable.", "error")
            return redirect(url_for("admin_contacts"))

        if request.method == "POST":
            new_status = request.form.get("status")
            note = (request.form.get("note") or "").strip()
            if new_status in ("nouveau", "contacte", "intervention_demandee",
                              "intervention_confirmee", "intervention_terminee", "cloture"):
                conn.execute(
                    "UPDATE client_contacts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (new_status, contact_id))
                conn.execute(
                    "INSERT INTO client_contact_events (contact_id, event_type, details)"
                    " VALUES (?, ?, ?)",
                    (contact_id, "status_change",
                     f"Statut admin : {contact['status']} -> {new_status}{' — ' + note if note else ''}"))
                conn.commit()
                log_admin_action(user["id"], user["email"], "update_contact_status", "client_contacts", contact_id)
                flash("Statut mis à jour.", "success")
            else:
                flash("Statut invalide.", "error")
            return redirect(url_for("admin_contact_detail", contact_id=contact_id))

        events = conn.execute(
            "SELECT * FROM client_contact_events"
            " WHERE contact_id = ? ORDER BY created_at DESC",
            (contact_id,)).fetchall()
    finally:
        conn.close()
    return render_template("admin_contact_detail.html",
                           user=user, contact=contact, events=events)


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
            where_parts.append("LOWER(r.status) = LOWER(?)")
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


@app.route("/admin/requests/<int:request_id>")
@login_required
@admin_required
def admin_request_detail(request_id):
    """Dossier complet d'une intervention."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT r.*, c.full_name AS client_name, c.phone AS client_phone, c.city AS client_city, c.quartier AS client_quartier,"
            " a.full_name AS artisan_name, a.phone AS artisan_phone, a.profession AS artisan_profession"
            " FROM requests r"
            " LEFT JOIN users c ON c.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            " WHERE r.id = ?", (request_id,)).fetchone()
        if not req:
            flash("Intervention introuvable.", "error")
            return redirect(url_for("admin_requests"))

        history = conn.execute(
            "SELECT * FROM intervention_history WHERE request_id = ? ORDER BY created_at DESC",
            (request_id,)).fetchall()

        photos = conn.execute(
            "SELECT photo_url FROM intervention_photos WHERE request_id = ?",
            (request_id,)).fetchall()

        payments = conn.execute(
            "SELECT * FROM payments WHERE request_id = ?",
            (request_id,)).fetchall()

    finally:
        conn.close()
    return render_template("admin_request_detail.html", user=user, req=req,
                           history=history, photos=photos, payments=payments,
                           payment_method_label=payment_method_label)


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
            " WHERE id = ? AND role = 'technician'", (artisan_id,)).fetchone()
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

        ticket_id = _insert_id(
            conn,
            "INSERT INTO admin_tickets (client_id, artisan_id, subject, message, status)"
            " VALUES (?, ?, ?, ?, 'open')",
            (user["id"], artisan_id,
             f"Concerne {artisan['full_name']}",
             f"Conversation demarree pour le technicien {artisan['full_name']} ({artisan['profession']})."))

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


_LIA_SYSTEM_PROMPT = (
    "Tu es Lia, l'assistante conversationnelle de FixPro, une plateforme qui met "
    "en relation des clients avec des techniciens verifies a Conakry (plomberie, "
    "electricite, serrurerie, climatisation, menuiserie, etc.). "
    "Tu comprends les fautes d'orthographe, les phrases incompletes et le francais "
    "familiar. Tu reponds en francais, de maniere naturelle, chaleureuse, claire, "
    "utile et concise. Pour les questions generales, reponds normalement comme un "
    "assistant intelligent. Si l'utilisateur decrit un probleme technique, identifie "
    "la categorie, pose les bonnes questions pour preciser, et propose de creer une "
    "intervention. Garde tes reponses courtes (moins de 120 mots)."
)


def _rule_based_reply(text):
    """Reponses predefinies quand Gemini n'est pas configure ou en echec."""
    text = text.lower()
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


def _call_gemini(message, api_key):
    """Appelle l'API Google Gemini pour generer une reponse."""
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-1.5-flash:generateContent?key={api_key}")
    payload = {
        "systemInstruction": {"parts": [{"text": _LIA_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": message}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 300,
        },
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        return parts[0].get("text", "").strip()
    except Exception as e:
        logger.warning("Appel Gemini echoue: %s", e)
        return None


def build_assistant_reply(message):
    """Genere une reponse intelligente via Gemini si configure, sinon regles."""
    api_key = app.config.get("GOOGLE_API_KEY")
    if api_key:
        gemini_reply = _call_gemini(message, api_key)
        if gemini_reply:
            return gemini_reply
    return _rule_based_reply(message)


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
@app.route("/inscription/client", methods=["GET", "POST"])
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

        pwd_error = _validate_password_strength(password)
        if pwd_error:
            flash(pwd_error, "error")
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
            return redirect(url_for("accueil"))
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

    session["google_next_url"] = _safe_next_url(
        request.args.get("next") or request.referrer or "")
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
    next_url = _safe_next_url(session.pop("google_next_url", ""))
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            session["google_next_url"] = next_url
            flash("Bienvenue dans FixPro.", "success")
            return redirect(next_url or url_for("dashboard"))

        # Nouvel utilisateur : stocke les donnees en session en attendant
        # le telephone et la ville.
        session["google_email"] = email
        session["google_name"] = full_name
        session["google_picture"] = userinfo.get("picture", "")
        session["google_next_url"] = next_url
        return redirect(url_for("complete_profile"))
    finally:
        conn.close()


@app.route("/complete-profile", methods=["GET", "POST"])
def complete_profile():
    """Finalise le profil apres une inscription Google : role, telephone, ville."""
    email = session.get("google_email")
    full_name = session.get("google_name")
    picture_url = session.get("google_picture") or ""

    if not email or not full_name:
        flash("Session invalide. Veuillez recommencer.", "error")
        return redirect(url_for("client_signup"))

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        quartier = request.form.get("quartier", "").strip()
        role = request.form.get("role", "client").strip()

        if role not in ("client", "technician"):
            flash("Veuillez choisir un type de compte.", "error")
            return redirect(url_for("complete_profile"))

        if not phone or not city:
            flash("Veuillez remplir tous les champs.", "error")
            return redirect(url_for("complete_profile"))

        is_verified = 1 if role == "client" else 0

        conn = get_db_connection()
        try:
            existing_phone = conn.execute(
                "SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
            if existing_phone:
                flash("Ce numéro de téléphone est déjà utilisé.", "error")
                return redirect(url_for("complete_profile"))

            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name, city, quartier, is_verified, photo_url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (email, phone, generate_password_hash("google_oauth"),
                 role, full_name, city, quartier, is_verified, picture_url or None),
            )
            conn.commit()

            new_user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            next_url = _safe_next_url(session.pop("google_next_url", ""))
            session.clear()
            session["user_id"] = new_user["id"]
            session.permanent = True
            flash("Bienvenue dans FixPro.", "success")
            return redirect(next_url or url_for("dashboard"))
        finally:
            conn.close()

    return render_template("complete_profile.html", email=email,
                           full_name=full_name, picture_url=picture_url)


def _can_login(user):
    """Verifie que le compte est actif et autorise la connexion."""
    account_status = (user.get("account_status") or "ACTIVE").upper()
    is_active = user.get("is_active", 1)

    if is_active == 0 and account_status == "SUSPENDED":
        flash("Votre compte FixPro est actuellement suspendu. Veuillez contacter l'administration.", "error")
        return False
    if account_status == "PENDING":
        flash("Votre compte est en attente d'activation. Veuillez consulter votre email ou contacter l'administration.", "error")
        return False
    if account_status in ("INACTIVE", "DELETED"):
        flash("Votre compte est inactif. Veuillez contacter l'administration.", "error")
        return False
    if is_active == 0:
        flash("Votre compte est desactive. Veuillez contacter l'administration.", "error")
        return False
    return True


_ACTIVATION_MAX_AGE = 7 * 24 * 60 * 60  # 7 jours
_activation_serializer = URLSafeTimedSerializer(
    app.config.get("SECRET_KEY") or "fallback-secret",
    salt="technician-activation")


def _generate_activation_token(user_id):
    """Genere un jeton d'activation securise pour un technicien."""
    return _activation_serializer.dumps({"user_id": user_id})


def _verify_activation_token(token):
    """Verifie un jeton d'activation et retourne l'identifiant utilisateur."""
    if not token:
        return None
    try:
        data = _activation_serializer.loads(token, max_age=_ACTIVATION_MAX_AGE)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None


_MOBILE_TOKEN_MAX_AGE = 7 * 24 * 60 * 60  # 7 jours
_mobile_serializer = URLSafeTimedSerializer(
    app.config.get("SECRET_KEY") or "fallback-secret",
    salt="technician-mobile")


def _generate_mobile_token(user):
    """Genere un token mobile de 7 jours pour un technicien."""
    return _mobile_serializer.dumps({
        "user_id": user["id"],
        "role": user["role"],
        "account_status": user.get("account_status", ""),
    })


def _verify_mobile_token(token):
    """Verifie un token mobile et retourne (user, error_reason)."""
    if not token:
        return None, "missing"
    try:
        data = _mobile_serializer.loads(token, max_age=_MOBILE_TOKEN_MAX_AGE)
    except SignatureExpired:
        return None, "expired"
    except BadSignature:
        return None, "invalid"

    conn = get_db_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (data.get("user_id"),)).fetchone()
    finally:
        conn.close()

    if not user:
        return None, "user_missing"
    if user["role"] != "technician":
        return None, "not_technician"
    if user["account_status"] != "ACTIVE":
        return None, "suspended"
    return user, None


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def login():
    next_url = _safe_next_url(
        request.args.get("next") or request.form.get("next") or "")
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
            if not _can_login(user):
                return render_template("login.html", next_url=next_url)

            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            flash("Bienvenue dans FixPro.", "success")

            if next_url:
                return redirect(next_url)
            if user["role"] == "client":
                return redirect(url_for("artisans_page"))
            if _is_technician(user):
                return redirect(url_for("artisan_dashboard"))
            if user["role"] == "admin":
                session["admin_unlocked"] = False
                return redirect(url_for("admin_unlock"))
            return redirect(url_for("requests_list"))

        # Message identique pour ne pas reveler quel identifiant existe.
        flash("Identifiants incorrects.", "error")

    return render_template("login.html", next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "success")
    return redirect(url_for("index"))


@app.route("/technician/activate", methods=["GET", "POST"])
def technician_activate():
    """Page d'activation du compte technicien (definition du mot de passe)."""
    token = request.args.get("token") or request.form.get("token", "")
    user_id = _verify_activation_token(token)

    if not user_id:
        flash("Lien d'activation invalide ou expire.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE id = ? AND role IN ('artisan','technician')",
            (user_id,)).fetchone()
    finally:
        conn.close()

    if not user:
        flash("Compte technicien introuvable.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not password or len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caracteres.", "error")
            return render_template("technician_activate.html", token=token, user=user)
        if password != confirm:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template("technician_activate.html", token=token, user=user)

        conn = get_db_connection()
        try:
            conn.execute(
                "UPDATE users SET password_hash = ?, account_status = 'ACTIVE',"
                " is_active = 1, is_verified = 1, verification_status = 'APPROVED' WHERE id = ?",
                (generate_password_hash(password), user_id))
            conn.commit()
        finally:
            conn.close()

        flash("Votre compte est active. Bienvenue sur FixPro.", "success")
        session.clear()
        session["user_id"] = user_id
        session.permanent = True
        return redirect(url_for("artisan_dashboard"))

    return render_template("technician_activate.html", token=token, user=user)


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
                " WHERE role = 'technician' AND profession LIKE ?",
                (f"%{c['name']}%",)).fetchone()["n"]
            artisan_counts[c["name"]] = count

        # Tous les artisans verifies avec notes et avis (fallback si reviews non prete)
        try:
            artisans = conn.execute("""
                SELECT u.id, u.full_name, u.profession, u.city, u.quartier,
                       u.hourly_rate, u.is_verified, u.photo_url,
                       u.availability_status, u.estimated_delay,
                       COALESCE(AVG(r.rating), 0) AS avg_rating,
                       COUNT(DISTINCT r.id) AS review_count
                FROM users u
                LEFT JOIN reviews r ON r.artisan_id = u.id
                WHERE u.role = 'technician' AND u.is_verified = 1
                GROUP BY u.id
                ORDER BY u.full_name
            """).fetchall()
        except Exception:
            artisans = conn.execute(
                "SELECT id, full_name, profession, city, quartier, hourly_rate, is_verified,"
                " photo_url, availability_status, estimated_delay"
                " FROM users WHERE role = 'technician' AND is_verified = 1"
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
        logger.exception("Erreur dashboard client: %s", exc)
        flash("Une erreur est survenue lors du chargement du tableau de bord.", "error")
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


_DOC_LABELS = {
    DOC_IDENTITY: "Pièce d'identité",
    DOC_PROFESSIONAL: "Justificatif professionnel",
}


@app.route("/technician/verification")
@app.route("/technicien/verification")
@login_required
def technician_verification():
    """Alias vers l'ecran de suivi de la verification."""
    return redirect(url_for("artisan_pending"))


@app.route("/technician/verification/resubmit", methods=["POST"])
@app.route("/technicien/verification/resoumettre", methods=["POST"])
@login_required
def technician_documents_resubmit():
    """Remplace un document refuse et repasse le dossier en attente de verification."""
    user = get_current_user()
    if not _is_technician(user):
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    try:
        store = storage.get_storage()
        replaced = 0
        for dtype in REQUIRED_DOC_TYPES:
            data_uri = (request.form.get(f"{dtype}_doc") or "").strip()
            if not data_uri:
                continue
            conn.execute(
                "DELETE FROM technician_documents WHERE technician_id = ? AND document_type = ?",
                (user["id"], dtype))
            err = _store_technician_document(conn, store, user["id"], dtype, data_uri,
                                             f"{dtype}-resoumis")
            if err:
                conn.rollback()
                flash(f"Document invalide : {err}", "error")
                return redirect(url_for("technician_verification"))
            replaced += 1

        if not replaced:
            flash("Aucun document fourni.", "error")
            return redirect(url_for("technician_verification"))

        conn.execute(
            "UPDATE users SET verification_status = ?, is_verified = 0 WHERE id = ?",
            (VERIF_PENDING, user["id"]))
        _notify_admins_new_technician(conn, user["id"], user.get("full_name"),
                                      user.get("profession"), user.get("city"))
        conn.commit()
    finally:
        conn.close()

    flash("Vos documents ont été renvoyés. Votre dossier est de nouveau en cours de vérification.", "success")
    return redirect(url_for("technician_verification"))


@app.route("/dashboard/technicien")
@app.route("/technician/dashboard")
@login_required
def artisan_dashboard():
    """Tableau de bord professionnel du technicien."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    # Dossier de verification non finalise : ecran d'attente plutot que le tableau de bord.
    if _verification_enabled() and (
            (user.get("verification_status") or "").upper() in VERIF_BLOCKING
            or not user.get("is_verified")):
        return redirect(url_for("artisan_pending"))

    active_statuses = (MISSION_STATUS_ASSIGNED, MISSION_STATUS_ACCEPTED,
                       MISSION_STATUS_EN_ROUTE, MISSION_STATUS_ARRIVED,
                       MISSION_STATUS_IN_PROGRESS, "quote_proposed", "quote_accepted")

    conn = get_db_connection()
    try:
        nouvelles = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND status = ?",
            (user["id"], MISSION_STATUS_ASSIGNED)).fetchone()["n"]

        assignees = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND status IN (?, ?, ?, ?, ?, ?, ?)",
            (user["id"],) + active_statuses).fetchone()["n"]

        urgentes = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND status IN (?, ?, ?, ?, ?, ?, ?) AND urgency = 'urgent'",
            (user["id"],) + active_statuses).fetchone()["n"]

        a_venir = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND status IN (?, ?, ?, ?, ?, ?, ?) AND urgency != 'urgent'",
            (user["id"],) + active_statuses).fetchone()["n"]

        terminees = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND status = ?",
            (user["id"], MISSION_STATUS_COMPLETED)).fetchone()["n"]

        revenus = conn.execute(
            "SELECT COALESCE(SUM(amount - commission_amount), 0) AS total"
            " FROM payments"
            " WHERE request_id IN (SELECT id FROM requests WHERE artisan_id = ?) AND status = 'success'",
            (user["id"],)).fetchone()["total"]

        note = conn.execute(
            "SELECT COALESCE(AVG(rating), 0) AS avg, COUNT(*) AS cnt FROM reviews"
            " WHERE artisan_id = ?", (user["id"],)).fetchone()

        active_mission = conn.execute("""
            SELECT r.id, r.reference, r.title, r.category, r.address, r.urgency, r.status,
                   r.description, r.latitude, r.longitude, r.requested_time, r.estimated_price,
                   u.full_name AS client_name, u.phone AS client_phone
            FROM requests r
            JOIN users u ON u.id = r.client_id
            WHERE r.artisan_id = ? AND r.status IN (?, ?, ?, ?, ?, ?, ?)
            ORDER BY
                CASE r.urgency WHEN 'urgent' THEN 0 WHEN 'haute' THEN 1 WHEN 'modere' THEN 2 ELSE 3 END,
                r.updated_at DESC
            LIMIT 1
        """, (user["id"],) + active_statuses).fetchone()

        missions = conn.execute("""
            SELECT r.id, r.reference, r.title, r.category, r.address, r.urgency, r.status,
                   r.created_at, r.estimated_price, u.full_name AS client_name
            FROM requests r
            JOIN users u ON u.id = r.client_id
            WHERE r.artisan_id = ?
            ORDER BY
                CASE r.urgency WHEN 'urgent' THEN 0 WHEN 'haute' THEN 1 WHEN 'modere' THEN 2 ELSE 3 END,
                r.updated_at DESC
            LIMIT 20
        """, (user["id"],)).fetchall()

        missions_historique = conn.execute("""
            SELECT r.id, r.reference, r.title, r.category, r.address, r.urgency, r.status,
                   r.created_at, u.full_name AS client_name
            FROM requests r
            JOIN users u ON u.id = r.client_id
            WHERE r.artisan_id = ? AND status IN (?, ?, ?)
            ORDER BY r.updated_at DESC
            LIMIT 20
        """, (user["id"], MISSION_STATUS_COMPLETED, MISSION_STATUS_REFUSED, MISSION_STATUS_CANCELLED)).fetchall()

        avis = conn.execute(
            "SELECT r.rating, r.comment, r.created_at, u.full_name"
            " FROM reviews r"
            " JOIN users u ON u.id = r.client_id"
            " WHERE r.artisan_id = ? ORDER BY r.created_at DESC LIMIT 5",
            (user["id"],)).fetchall()

        contacts = conn.execute(
            "SELECT id, first_name, last_name, phone, status, created_at"
            " FROM client_contacts WHERE artisan_id = ?"
            " ORDER BY created_at DESC LIMIT 20",
            (user["id"],)).fetchall()

        new_contact_count = 0
        try:
            new_contact_count = conn.execute(
                "SELECT COUNT(*) AS n FROM client_contacts"
                " WHERE artisan_id = ? AND status = 'nouveau'",
                (user["id"],)).fetchone()["n"]
        except Exception:
            new_contact_count = 0

        unread_count = 0
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                (user["id"],)).fetchone()
            unread_count = row["n"]
        except Exception:
            conn.rollback()
            unread_count = 0

        services_disponibles = _services_for_category(conn, user["profession"] or "")
        artisan_services_ids = _artisan_service_ids(conn, user["id"])

        # Abonnement en cours du technicien (le plus recent).
        subscription = None
        try:
            subscription = conn.execute(
                "SELECT s.status, s.end_date, s.auto_renew,"
                " p.name AS plan_name, p.code AS plan_code, p.price_month, p.currency"
                " FROM technician_subscriptions s"
                " LEFT JOIN subscription_plans p ON p.id = s.plan_id"
                " WHERE s.technician_id = ?"
                " ORDER BY s.created_at DESC LIMIT 1",
                (user["id"],)).fetchone()
        except Exception:
            conn.rollback()
            subscription = None

        # Repartition des notes (1 a 5 etoiles).
        rating_breakdown = {i: 0 for i in range(1, 6)}
        try:
            for r in conn.execute(
                    "SELECT rating, COUNT(*) AS n FROM reviews"
                    " WHERE artisan_id = ? GROUP BY rating", (user["id"],)).fetchall():
                rating_breakdown[int(r["rating"])] = r["n"]
        except Exception:
            conn.rollback()

        realisations_count = 0
        try:
            realisations_count = conn.execute(
                "SELECT COUNT(*) AS n FROM artisan_portfolio WHERE artisan_id = ?",
                (user["id"],)).fetchone()["n"]
        except Exception:
            conn.rollback()
            realisations_count = 0

    finally:
        conn.close()

    html = render_template(
        "dashboard_artisan.html", user=user,
        stats={"nouvelles": nouvelles, "assignees": assignees,
               "urgentes": urgentes, "a_venir": a_venir,
               "terminees": terminees, "revenus": revenus,
               "note_avg": note["avg"], "note_count": note["cnt"]},
        active_mission=active_mission, missions=missions,
        historique=missions_historique, avis=avis,
        unread_count=unread_count,
        contacts=contacts,
        new_contact_count=new_contact_count,
        services_disponibles=services_disponibles,
        artisan_services_ids=artisan_services_ids,
        subscription=subscription,
        rating_breakdown=rating_breakdown,
        realisations_count=realisations_count,
        services_count=len(artisan_services_ids or []))
    response = make_response(html)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route("/dashboard/technicien/contact/<int:contact_id>/status", methods=["POST"])
@login_required
def technician_contact_status(contact_id):
    """Met a jour le statut d'un contact client par le technicien."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    new_status = request.form.get("status", "").strip()
    if new_status not in ("contacte", "intervention_demandee", "intervention_confirmee",
                          "intervention_terminee", "cloture"):
        flash("Statut invalide.", "error")
        return redirect(url_for("artisan_dashboard"))

    conn = get_db_connection()
    try:
        contact = conn.execute(
            "SELECT id, artisan_id, status FROM client_contacts WHERE id = ?",
            (contact_id,)).fetchone()
        if not contact or contact["artisan_id"] != user["id"]:
            flash("Contact introuvable ou non autorise.", "error")
            return redirect(url_for("artisan_dashboard"))

        conn.execute(
            "UPDATE client_contacts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, contact_id))
        conn.execute(
            "INSERT INTO client_contact_events (contact_id, event_type, details)"
            " VALUES (?, ?, ?)",
            (contact_id, "status_change",
             f"Statut technicien : {contact['status']} -> {new_status}"))
        conn.commit()
        flash("Statut mis a jour.", "success")
    finally:
        conn.close()
    return redirect(url_for("artisan_dashboard"))


@app.route("/dashboard/technicien/contacts/json")
@login_required
def artisan_dashboard_contacts_json():
    """API JSON : retourne les contacts du technicien connecte."""
    user = get_current_user()
    if not _is_technician(user):
        return jsonify({"ok": False, "error": "Reserve aux techniciens"}), 403
    conn = get_db_connection()
    try:
        contacts = conn.execute(
            "SELECT id, first_name, last_name, phone, status, created_at"
            " FROM client_contacts WHERE artisan_id = ?"
            " ORDER BY created_at DESC LIMIT 20",
            (user["id"],)).fetchall()
        new_count = conn.execute(
            "SELECT COUNT(*) AS n FROM client_contacts"
            " WHERE artisan_id = ? AND status = 'nouveau'",
            (user["id"],)).fetchone()["n"]
        unread_notif = conn.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
            (user["id"],)).fetchone()["n"]
    finally:
        conn.close()
    return jsonify({
        "ok": True,
        "contacts": [dict(c) for c in contacts],
        "new_count": new_count,
        "unread_notif": unread_notif
    })


@app.route("/dashboard/technicien/services", methods=["POST"])
@login_required
def update_artisan_services():
    """Mise a jour des services du technicien connecte."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))
    services_ids = request.form.getlist("services")
    conn = get_db_connection()
    try:
        _save_artisan_services(conn, user["id"], services_ids)
        conn.commit()
        flash("Services mis a jour.", "success")
    except ValueError as exc:
        flash(f"Erreur : {exc}", "error")
    finally:
        conn.close()
    return redirect(url_for("artisan_dashboard"))


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

    if user.get("role") == "artisan":
        conn = get_db_connection()
        try:
            unread_count = 0
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                    (user["id"],)).fetchone()
                unread_count = row["n"]
            except Exception:
                unread_count = 0
        finally:
            conn.close()
        return render_template("profile.html", user=user, unread_count=unread_count)

    conn = get_db_connection()
    try:
        # Demandes récentes
        demandes = conn.execute(
            "SELECT r.*, u.full_name AS artisan_name FROM requests r"
            " LEFT JOIN users u ON u.id = r.artisan_id"
            " WHERE r.client_id = ? AND LOWER(r.status) IN ('requested', 'pending')"
            " ORDER BY r.updated_at DESC LIMIT 5",
            (user["id"],)).fetchall()
        reservations = conn.execute(
            "SELECT r.*, u.full_name AS artisan_name FROM requests r"
            " LEFT JOIN users u ON u.id = r.artisan_id"
            " WHERE r.client_id = ? AND LOWER(r.status) IN ('assigned', 'in_progress', 'on_the_way')"
            " ORDER BY r.updated_at DESC LIMIT 5",
            (user["id"],)).fetchall()
        interventions = conn.execute(
            "SELECT r.*, u.full_name AS artisan_name FROM requests r"
            " LEFT JOIN users u ON u.id = r.artisan_id"
            " WHERE r.client_id = ? AND LOWER(r.status) = 'completed'"
            " ORDER BY r.updated_at DESC LIMIT 5",
            (user["id"],)).fetchall()
        avis = conn.execute(
            "SELECT r.id, r.rating, r.comment, r.created_at, u.full_name AS artisan_name"
            " FROM reviews r LEFT JOIN users u ON u.id = r.artisan_id"
            " WHERE r.client_id = ? ORDER BY r.created_at DESC LIMIT 5",
            (user["id"],)).fetchall()
        unread_count = 0
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                (user["id"],)).fetchone()
            unread_count = row["n"]
        except Exception:
            unread_count = 0

        messages_unread = 0
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM conversation_messages cm"
                " JOIN conversations c ON c.id = cm.conversation_id"
                " WHERE c.client_id = ? AND cm.sender_role = 'admin' AND cm.is_read = 0",
                (user["id"],)).fetchone()
            messages_unread = row["n"]
        except Exception:
            messages_unread = 0
    finally:
        conn.close()

    recent = list(demandes) + list(reservations) + list(interventions)
    recent.sort(key=lambda r: r["updated_at"] or r["created_at"], reverse=True)
    recent = recent[:1]

    counts = {
        "demandes": len(demandes),
        "reservations": len(reservations),
        "interventions": len(interventions),
        "avis": len(avis),
    }

    client_zone = session.get("client_zone") or user.get("city") or user.get("quartier")
    return render_template("client_profile.html", user=user,
                           demandes=demandes, reservations=reservations,
                           interventions=interventions, avis=avis, recent=recent,
                           counts=counts, client_zone=client_zone,
                           unread_count=unread_count, messages_unread=messages_unread)


@app.route("/profil/modifier", methods=["GET"])
@login_required
def edit_profile():
    """Page de modification du profil client."""
    user = get_current_user()
    return render_template("client_profile.html", user=user,
                           client_zone=user.get("city") or user.get("quartier") or "Conakry",
                           counts={"reservations": 0, "demandes": 0}, unread_count=0,
                           messages_unread=0)


@app.route("/client-page/<page>")
@login_required
def client_static(page):
    """Pages statiques du compte client."""
    pages = {
        "how-it-works": (
            "Comment fonctionne FixPro ?",
            "<ol><li>Décrivez votre problème.</li>"
            "<li>FixPro recherche les professionnels adaptés.</li>"
            "<li>Les professionnels proches et disponibles sont privilégiés.</li>"
            "<li>FixPro organise l'intervention.</li>"
            "<li>Le client suit l'évolution de l'intervention.</li>"
            "<li>L'intervention est terminée.</li>"
            "<li>Le client peut laisser un avis.</li></ol>"
        ),
        "about": (
            "À propos de FixPro",
            "<p>FixPro est une plateforme qui met en relation des clients avec des professionnels qualifiés pour leurs besoins d'intervention.</p>"
        ),
        "terms": (
            "Conditions & confidentialité",
            "<p>Les conditions d'utilisation et la politique de confidentialité de FixPro seront prochainement disponibles ici.</p>"
        ),
    }
    title, content = pages.get(page, ("FixPro", "<p>Page en cours de construction.</p>"))
    return render_template("client_static.html", page=page, title=title, content=content)


@app.route("/profil/securite", methods=["GET", "POST"])
@login_required
def client_security():
    """Gestion de la securite du compte client."""
    user = get_current_user()
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if new != confirm:
            flash("Les nouveaux mots de passe ne correspondent pas.", "error")
            return redirect(url_for("client_security"))
        pwd_error = _validate_password_strength(new)
        if pwd_error:
            flash(pwd_error, "error")
            return redirect(url_for("client_security"))
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
            if not row or not check_password_hash(row["password_hash"], current):
                flash("Mot de passe actuel incorrect.", "error")
                return redirect(url_for("client_security"))
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new), user["id"]))
            conn.commit()
            flash("Mot de passe mis a jour.", "success")
        finally:
            conn.close()
        return redirect(url_for("client_security"))
    return render_template("client_security.html", user=user)


def _insert_id(conn, sql, params):
    """Insere une ligne et retourne son id, compatible SQLite et PostgreSQL."""
    if conn.is_postgres:
        return conn.execute(sql + " RETURNING id", params).fetchone()["id"]
    return conn.execute(sql, params).lastrowid


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


import math


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _services_for_category(conn, category_name):
    """Liste les services actifs d'un domaine professionnel."""
    return conn.execute(
        "SELECT s.id, s.name"
        " FROM services s JOIN service_categories c ON c.id = s.category_id"
        " WHERE c.name = ? AND s.is_active = 1"
        " ORDER BY s.name",
        (category_name,)).fetchall()


def _artisan_service_ids(conn, artisan_id):
    """Identifiants des services associes a un artisan."""
    rows = conn.execute(
        "SELECT service_id FROM artisan_services WHERE artisan_id = ?",
        (artisan_id,)).fetchall()
    return {r["service_id"] for r in rows}


def _save_artisan_services(conn, artisan_id, service_ids):
    """Remplace les services d'un artisan apres validation du domaine."""
    service_ids = [int(s) for s in (service_ids or []) if s]
    if not service_ids:
        conn.execute("DELETE FROM artisan_services WHERE artisan_id = ?", (artisan_id,))
        return
    artisan = conn.execute(
        "SELECT profession FROM users WHERE id = ? AND role = 'technician'",
        (artisan_id,)).fetchone()
    if not artisan or not artisan["profession"]:
        raise ValueError("Domaine professionnel non defini.")
    allowed = {r["id"] for r in _services_for_category(conn, artisan["profession"])}
    invalid = [s for s in service_ids if s not in allowed]
    if invalid:
        raise ValueError("Certains services n'appartiennent pas au domaine du technicien.")
    conn.execute("DELETE FROM artisan_services WHERE artisan_id = ?", (artisan_id,))
    for sid in service_ids:
        conn.execute(
            "INSERT INTO artisan_services (artisan_id, service_id) VALUES (?, ?)",
            (artisan_id, sid))


def _enrich_artisan(row, client_lat, client_lon):
    artisan = dict(row)
    artisan["full_name"] = artisan.get("nom") or artisan.get("full_name", "")
    artisan["profession"] = artisan.get("metier") or artisan.get("profession", "Technicien")
    artisan["gradient"] = _avatar_gradient(artisan["full_name"])
    artisan_lat = _to_float(artisan.get("latitude"))
    artisan_lon = _to_float(artisan.get("longitude"))
    if _is_valid_coordinate(client_lat, client_lon) and _is_valid_coordinate(artisan_lat, artisan_lon):
        artisan["distance"] = _haversine(client_lat, client_lon, artisan_lat, artisan_lon)
    else:
        artisan["distance"] = None
    completed = artisan.get("completed")
    review_count = artisan.get("review_count")
    avg_rating = artisan.get("avg_rating")
    artisan["completed"] = completed if completed is not None else _completed_count(artisan["id"])
    if avg_rating is not None and review_count:
        artisan["rating"] = round(avg_rating, 1)
    else:
        artisan["rating"] = _artisan_rating(artisan["id"]) if review_count is None else None
    return artisan


def _completed_count(artisan_id):
    conn = get_db_connection()
    try:
        r = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ? AND status = 'completed'",
            (artisan_id,)).fetchone()
        return r["n"] if r else 0
    finally:
        conn.close()


def _artisan_rating(artisan_id):
    conn = get_db_connection()
    try:
        r = conn.execute(
            "SELECT AVG(rating) AS avg, COUNT(*) AS n FROM reviews WHERE artisan_id = ?",
            (artisan_id,)).fetchone()
        if r and r["n"]:
            return round(r["avg"], 1)
        return None
    finally:
        conn.close()


def _avatar_gradient(full_name):
    h = sum(ord(c) for c in (full_name or "")) % 3
    return [
        "linear-gradient(155deg,#2C4066,#13203B)",
        "linear-gradient(155deg,#3F7A5A,#164430)",
        "linear-gradient(155deg,#8A5A0B,#4A3103)",
    ][h]


@app.route("/accueil")
@app.route("/artisans")
def artisans_page():
    user = get_current_user()
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    zone = request.args.get("location", request.args.get("zone", "")).strip()

    sql = (
        "SELECT u.id, u.full_name AS nom, u.profession AS metier, u.city,"
        " u.hourly_rate, u.latitude, u.longitude, u.photo_url, u.is_verified,"
        " u.availability_status,"
        " COALESCE(AVG(r.rating), 0) AS avg_rating,"
        " COUNT(DISTINCT r.id) AS review_count,"
        " COUNT(DISTINCT req_completed.id) AS completed"
        " FROM users u"
        " LEFT JOIN reviews r ON r.artisan_id = u.id"
        " LEFT JOIN requests req_completed ON req_completed.artisan_id = u.id AND req_completed.status = 'completed'"
        " WHERE u.profession IS NOT NULL AND u.profession != ''"
        " AND u.role IN ('artisan','technician') AND u.is_verified = 1 AND u.is_active = 1"
        " AND u.account_status != 'DELETED'")
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
        sql += " AND (u.city LIKE ? OR u.quartier LIKE ? OR u.zone_intervention LIKE ?)"
        like = f"%{zone}%"
        params.extend([like, like, like])

    sql += (
        " GROUP BY u.id, u.full_name, u.profession, u.city, u.hourly_rate,"
        " u.latitude, u.longitude, u.photo_url, u.is_verified, u.availability_status"
        " ORDER BY u.full_name")

    client_lat = _to_float(user.get("latitude")) if user else None
    client_lon = _to_float(user.get("longitude")) if user else None

    conn = get_db_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
        artisans = [_enrich_artisan(row, client_lat, client_lon) for row in rows]
        active_requests = {}
        if user and user["role"] == "client":
            rows_req = conn.execute(
                "SELECT id, artisan_id FROM requests WHERE client_id = ?"
                " AND artisan_id IS NOT NULL AND status != 'pending'"
                " ORDER BY updated_at DESC", (user["id"],)).fetchall()
            active_requests = {r["artisan_id"]: r["id"] for r in rows_req}
        categories = conn.execute(
            "SELECT id, name FROM service_categories ORDER BY name").fetchall()
        unread_count = 0
        if user:
            try:
                unread_row = conn.execute(
                    "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                    (user["id"],)).fetchone()
                unread_count = unread_row["n"] if unread_row else 0
            except Exception:
                conn.rollback()
                unread_count = 0
    finally:
        conn.close()

    # Localisation du client : parametres URL > profil > session.
    if request.args.get("lat") and request.args.get("lon"):
        client_lat = _to_float(request.args.get("lat"))
        client_lon = _to_float(request.args.get("lon"))
    if not _is_valid_coordinate(client_lat, client_lon):
        client_lat = _to_float(session.get("client_lat"))
        client_lon = _to_float(session.get("client_lon"))

    radius_km = app.config.get("LOCAL_RADIUS_KM", 10.0)
    location_active = _is_valid_coordinate(client_lat, client_lon)

    if location_active:
        # On ne garde QUE les techniciens du secteur du client (rayon
        # LOCAL_RADIUS_KM), tries du plus proche au plus loin. Un client
        # hors de Conakry n'aura donc aucun technicien affiche.
        for a in artisans:
            a_lat = _to_float(a.get("latitude"))
            a_lon = _to_float(a.get("longitude"))
            a["distance"] = (_haversine(client_lat, client_lon, a_lat, a_lon)
                             if _is_valid_coordinate(a_lat, a_lon) else None)
        artisans = sorted(
            [a for a in artisans
             if a.get("distance") is not None and a["distance"] <= radius_km],
            key=lambda a: a["distance"])

    client_zone = (session.get("client_zone")
                   or _nearest_zone(client_lat, client_lon)
                   or (user.get("city") if user else None))
    return render_template("artisans.html", artisans=artisans, user=user,
                           active_requests=active_requests, categories=categories,
                           category_filter=category,
                           client_zone=client_zone, unread_count=unread_count,
                           query=query, zone=zone,
                           location_active=location_active, radius_km=radius_km)


@app.route("/api/techniciens", methods=["GET"])
def api_techniciens():
    """Liste publique des techniciens actifs et verifies au format JSON."""
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    zone = request.args.get("location", request.args.get("zone", "")).strip()

    try:
        sql = (
            "SELECT u.id, u.full_name, u.profession, u.city,"
            " u.hourly_rate, u.latitude, u.longitude, u.photo_url,"
            " u.years_experience, u.bio, u.is_verified, u.availability_status,"
            " COALESCE(AVG(r.rating), 0) AS avg_rating,"
            " COUNT(DISTINCT r.id) AS review_count,"
            " COUNT(DISTINCT req_completed.id) AS completed"
            " FROM users u"
            " LEFT JOIN reviews r ON r.artisan_id = u.id"
            " LEFT JOIN requests req_completed ON req_completed.artisan_id = u.id"
            " AND req_completed.status = 'completed'"
            " WHERE u.profession IS NOT NULL AND u.profession != ''")
        params = []

        if query:
            sql += (
                " AND (u.full_name LIKE ? OR u.profession LIKE ? OR u.city LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like])

        if category:
            sql += " AND u.profession LIKE ?"
            params.append(f"%{category}%")

        if zone:
            sql += (
                " AND (u.city LIKE ? OR u.quartier LIKE ?"
                " OR u.zone_intervention LIKE ?)")
            like = f"%{zone}%"
            params.extend([like, like, like])

        sql += (
            " GROUP BY u.id, u.full_name, u.profession, u.city, u.hourly_rate,"
            " u.latitude, u.longitude, u.photo_url, u.years_experience, u.bio, u.is_verified, u.availability_status"
            " ORDER BY u.full_name")

        client_lat = _to_float(request.args.get("lat"))
        client_lon = _to_float(request.args.get("lon"))

        conn = get_db_connection()
        try:
            rows = conn.execute(sql, params).fetchall()
            artisans = [_enrich_artisan(row, client_lat, client_lon) for row in rows]
        finally:
            conn.close()

        client_in_conakry = (
            _is_valid_coordinate(client_lat, client_lon)
            and _nearest_zone(client_lat, client_lon, max_km=50.0) is not None)
        if client_in_conakry:
            for a in artisans:
                a_lat = _to_float(a.get("latitude"))
                a_lon = _to_float(a.get("longitude"))
                if _is_valid_coordinate(a_lat, a_lon):
                    a["distance"] = _haversine(
                        client_lat, client_lon, a_lat, a_lon)
                else:
                    a["distance"] = None
            artisans = sorted(artisans, key=lambda a: a.get("distance") or 999)

        limit = _to_int(request.args.get("limit", 50), default=50)
        artisans = artisans[:limit]

        technicians = []
        for a in artisans:
            distance = a.get("distance")
            technicians.append({
                "full_name": a.get("full_name") or "",
                "profession": a.get("profession") or "Technicien",
                "rating": float(a.get("rating") or 0),
                "distance_km": float(distance) if distance is not None else 0,
                "hourly_rate": int(a.get("hourly_rate") or 0),
                "review_count": int(a.get("review_count") or 0),
                "interventions": int(a.get("completed") or 0),
                "experience_years": int(a.get("years_experience") or 0),
                "bio": (a.get("bio") or "").strip(),
            })

        return jsonify({"technicians": technicians}), 200
    except Exception as exc:
        logger.exception("Erreur API artisans: %s", exc)
        return jsonify({"error": "Impossible de charger les artisans."}), 500


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
@app.route("/technicien/<int:artisan_id>", methods=["GET", "POST"])
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
            "SELECT * FROM users WHERE id = ? AND role IN ('artisan','technician')"
            " AND is_verified = 1 AND is_active = 1 AND account_status != 'DELETED'",
            (artisan_id,)).fetchone()
        if not artisan:
            flash("Technicien introuvable.", "error")
            return redirect(url_for("artisans_page"))

        artisan = dict(artisan)
        artisan["gradient"] = _avatar_gradient(artisan["full_name"])

        # Services reels du technicien
        artisan_services = conn.execute(
            "SELECT s.name"
            " FROM services s"
            " JOIN artisan_services a ON a.service_id = s.id"
            " WHERE a.artisan_id = ? AND s.is_active = 1"
            " ORDER BY s.name",
            (artisan_id,)).fetchall()

        # Si le technicien n'a pas encore selectionne ses services, on affiche
        # les services standards de SON metier (jamais ceux d'un autre metier).
        services_are_standard = False
        if not artisan_services:
            _prof_key = {
                "plombier": "%lombier%", "plomberie": "%lombier%",
                "électricien": "%lectricien%", "electricien": "%lectricien%",
                "electricite": "%lectricien%", "électricité": "%lectricien%",
                "frigoriste": "%rigoriste%", "froid": "%rigoriste%",
                "climatisation": "%rigoriste%",
                "menuisier": "%enuisier%", "menuiserie": "%enuisier%",
                "peintre": "%eintre%", "peinture": "%eintre%",
                "chauffagiste": "%hauffagiste%",
                "serrurier": "%errurier%", "serrurerie": "%errurier%",
            }.get((artisan.get("profession") or "").strip().lower())
            if _prof_key:
                artisan_services = conn.execute(
                    "SELECT DISTINCT s.name FROM services s"
                    " JOIN service_categories sc ON sc.id = s.category_id"
                    " WHERE s.is_active = 1 AND lower(sc.name) LIKE ?"
                    " ORDER BY s.name",
                    (_prof_key,)).fetchall()
                services_are_standard = bool(artisan_services)

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

        review_bars_raw = conn.execute(
            "SELECT rating, COUNT(*) AS n FROM reviews WHERE artisan_id = ? GROUP BY rating",
            (artisan_id,)).fetchall()
        review_counts = {1:0,2:0,3:0,4:0,5:0}
        for row in review_bars_raw:
            review_counts[row["rating"]] = row["n"]
        total = review_stats["count"] or 1
        review_bars = {k: round(v / total * 100, 1) for k, v in review_counts.items()}
        review_bars_count = review_counts

        # Taux de satisfaction
        if review_stats["count"]:
            positive = conn.execute(
                "SELECT COUNT(*) AS n FROM reviews WHERE artisan_id = ? AND rating >= 4",
                (artisan_id,)).fetchone()["n"]
            satisfaction_rate = round(positive / review_stats["count"] * 100)
        else:
            satisfaction_rate = 0

        # Interventions realisees (status completed)
        completed = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND status = 'completed'",
            (artisan_id,)).fetchone()["n"]

        # Documents verifies du technicien
        documents = conn.execute(
            "SELECT document_type, status"
            " FROM technician_documents"
            " WHERE technician_id = ?",
            (artisan_id,)).fetchall()
        verified_docs = {d["document_type"]: d["status"] for d in documents}

        # Distance approximative (position temps reel si disponible, sinon profil)
        distance = None
        client_lat = _to_float(user.get("latitude")) if user else _to_float(session.get("client_lat"))
        client_lon = _to_float(user.get("longitude")) if user else _to_float(session.get("client_lon"))

        artisan_position = None
        if artisan.get("availability_status") == "en_ligne":
            loc = conn.execute(
                "SELECT latitude, longitude, updated_at FROM technician_locations"
                " WHERE technician_id = ? ORDER BY updated_at DESC LIMIT 1",
                (artisan_id,)).fetchone()
            if loc:
                try:
                    updated = datetime.fromisoformat(
                        str(loc["updated_at"]).replace("Z", "+00:00"))
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - updated).total_seconds() <= 180:
                        artisan_position = (
                            float(loc["latitude"]),
                            float(loc["longitude"]),
                            loc["updated_at"])
                except (TypeError, ValueError):
                    pass

        artisan_lat = _to_float(artisan.get("latitude"))
        artisan_lon = _to_float(artisan.get("longitude"))
        if artisan_position:
            artisan_lat, artisan_lon = artisan_position[0], artisan_position[1]
        if (_is_valid_coordinate(client_lat, client_lon)
                and _is_valid_coordinate(artisan_lat, artisan_lon)):
            distance = _haversine(client_lat, client_lon, artisan_lat, artisan_lon)

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

                conv = conn.execute(
                    "SELECT id FROM conversations WHERE client_id = ? AND artisan_id = ?",
                    (user["id"], artisan_id)).fetchone()
                if not conv:
                    conv_id = _insert_id(
                        conn,
                        "INSERT INTO conversations (client_id, artisan_id, subject)"
                        " VALUES (?, ?, ?)",
                        (user["id"], artisan_id, artisan["full_name"]))
                    conn.execute(
                        "INSERT INTO conversation_messages"
                        " (conversation_id, sender_id, sender_role, content)"
                        " VALUES (?, ?, ?, ?)",
                        (conv_id, user["id"], "client",
                         f"Conversation demarree pour {artisan['full_name']}."))
                    conn.commit()
                else:
                    conv_id = conv["id"]

                conn.execute(
                    "INSERT INTO conversation_messages"
                    " (conversation_id, sender_id, sender_role, content)"
                    " VALUES (?, ?, ?, ?)",
                    (conv_id, user["id"], "client", content))
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), conv_id))
                conn.commit()

                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"ok": True})
                return redirect(url_for("client_conversation", conversation_id=conv_id))

            if action == "request":
                title = (request.form.get("title") or "").strip()
                description = (request.form.get("description") or "").strip()
                address = (request.form.get("address") or "").strip()
                date_time = (request.form.get("date_time") or "").strip()
                urgency = (request.form.get("urgency") or "").strip()
                phone_contact = (request.form.get("phone_contact") or "").strip()
                if not title or not description:
                    flash("Veuillez remplir le service et la description.", "error")
                    return redirect(url_for("artisan_detail", artisan_id=artisan_id))
                if urgency not in ("urgent", "cette_semaine", "pas_presse"):
                    urgency = "cette_semaine"
                full_desc = description
                if date_time:
                    full_desc += f"\n\nDate/heure souhaitée : {date_time}"

                lat, lon = _geocode_zone("Conakry", address)
                if not _is_valid_coordinate(lat, lon):
                    lat, lon = _geocode_query(address)[:2]
                lat = float(lat) if _is_valid_coordinate(lat) else 0.0
                lon = float(lon) if _is_valid_coordinate(lon) else 0.0

                ref = _generate_fixpro_reference(conn)
                request_id = _insert_id(
                    conn,
                    "INSERT INTO requests"
                    " (client_id, artisan_id, reference, title, description, category, address, latitude, longitude, status, urgency, phone_contact, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                    (user["id"], artisan_id, ref, title, full_desc,
                     artisan["profession"] or "Autre", address, lat, lon,
                     MISSION_STATUS_ASSIGNED, urgency, phone_contact))
                _log_intervention_history(conn, request_id, MISSION_STATUS_REQUESTED, MISSION_STATUS_ASSIGNED,
                                         f"Client {user['full_name']}",
                                         f"Demande directe assignee au technicien {artisan['full_name']}",
                                         label="Technicien attribue")
                create_notification(
                    artisan_id, "Nouvelle demande",
                    f"Nouvelle demande : {title} - {address or 'Conakry'}",
                    "new_request", f"request_id:{request_id}",
                    conn=conn)
                conn.commit()
                flash("Demande d'intervention creee. Le technicien en sera informe.", "success")
                return redirect(url_for("request_detail", request_id=request_id))

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

        # Date d'inscription lisible
        member_since = (str(artisan["created_at"])[:7] if artisan["created_at"]
                        else "Date inconnue")

        # Photos de realisations (table ignoree si non migree)
        try:
            portfolio = conn.execute(
                "SELECT id, photo_url, caption FROM artisan_portfolio"
                " WHERE artisan_id = ? ORDER BY created_at DESC LIMIT 6",
                (artisan_id,)).fetchall()
        except Exception:
            portfolio = []

        # Zones d'intervention
        zones = _split_zones(
            artisan.get("zone_intervention")
            or artisan.get("quartier")
            or artisan.get("city"))
        zone_center = None
        for z in zones:
            zone_center = _zone_coordinate(z)
            if zone_center:
                break
    finally:
        conn.close()

    client_zone = session.get("client_zone") or (user.get("city") if user else None)

    # Une seule fiche technicien, dynamique, identique pour tous les metiers.
    # Toutes les donnees (services, realisations, avis, stats) sont filtrees
    # par artisan_id : aucune donnee d'un autre technicien n'apparait.
    return render_template("artisan_detail.html",
                           user=user,
                           client_zone=client_zone,
                           artisan=artisan,
                           reviews=reviews,
                           review_stats=review_stats,
                           completed=completed,
                           distance=distance,
                           can_review=can_review,
                           ticket_id=ticket_id,
                           verified_docs=verified_docs,
                           member_since=member_since,
                           portfolio=portfolio,
                           review_bars=review_bars,
                           review_bars_count=review_bars_count,
                           satisfaction_rate=satisfaction_rate,
                           artisan_services=artisan_services,
                           services_are_standard=services_are_standard,
                           artisan_position=artisan_position,
                           zone_center=zone_center,
                           zones=zones)


@app.route("/artisans/<int:artisan_id>/contacter", methods=["GET", "POST"])
def contact_artisan(artisan_id):
    """Page de contact client -> enregistrement en base + notification."""
    conn = get_db_connection()
    try:
        artisan = conn.execute(
            "SELECT id, full_name, profession, phone, photo_url, is_verified"
            " FROM users WHERE id = ? AND role IN ('artisan','technician')"
            " AND is_active = 1 AND account_status != 'DELETED'",
            (artisan_id,)).fetchone()
    finally:
        conn.close()
    if not artisan:
        flash("Technicien introuvable.", "error")
        return redirect(url_for("artisans_page"))

    artisan = dict(artisan)
    user = get_current_user()
    client_user_id = user["id"] if user and user.get("role") == "client" else None

    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        phone = (request.form.get("phone") or "").replace(" ", "")
        country = (request.form.get("country") or "+224").strip()

        if not first_name or not last_name:
            flash("Veuillez renseigner votre prénom et votre nom.", "error")
            return redirect(url_for("contact_artisan", artisan_id=artisan_id))
        if not phone or not phone.isdigit() or len(phone) < 8:
            flash("Veuillez saisir un numéro de téléphone valide.", "error")
            return redirect(url_for("contact_artisan", artisan_id=artisan_id))

        full_phone = f"{country} {phone}"

        conn = get_db_connection()
        try:
            # Recherche d'un contact existant pour ce client et ce technicien
            existing = conn.execute(
                "SELECT id FROM client_contacts"
                " WHERE artisan_id = ? AND REPLACE(phone, ' ', '') = ?",
                (artisan_id, full_phone.replace(" ", ""))).fetchone()

            if existing:
                contact_id = existing["id"]
                conn.execute(
                    "UPDATE client_contacts SET updated_at = CURRENT_TIMESTAMP,"
                    " first_name = ?, last_name = ?, phone = ?, client_user_id = COALESCE(client_user_id, ?)"
                    " WHERE id = ?",
                    (first_name, last_name, full_phone, client_user_id, contact_id))
            else:
                result = conn.execute(
                    "INSERT INTO client_contacts"
                    " (client_user_id, artisan_id, first_name, last_name, phone, status, source)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (client_user_id, artisan_id, first_name, last_name,
                     full_phone, "nouveau", "profil_artisan"))
                contact_id = result.lastrowid

            conn.execute(
                "INSERT INTO client_contact_events (contact_id, event_type, details)"
                " VALUES (?, ?, ?)",
                (contact_id, "creation", f"Contact depuis le profil de {artisan['full_name']}"))

            create_notification(
                artisan_id, "Nouveau contact",
                f"{first_name} {last_name} ({full_phone}) vous a contacté depuis votre profil.",
                "new_contact", f"contact_id:{contact_id}", conn=conn)

            conn.commit()
        finally:
            conn.close()

        flash("Votre demande de contact a bien été envoyée. Le technicien vous rappellera.", "success")
        return redirect(url_for("artisan_detail", artisan_id=artisan_id))

    return render_template("contact_artisan.html",
                           artisan=artisan,
                           back_url=request.referrer or url_for("artisan_detail", artisan_id=artisan_id))


def _services_for_profession(profession):
    """Retourne la liste des services associes a un metier."""
    profession = (profession or "").lower()
    if profession in ("plombier", "plomberie"):
        return ["Fuite d'eau", "Débouchage canalisation", "Installation sanitaire",
                "Chauffe-eau", "Robinetterie", "Recherche de fuite",
                "Réparation fuite", "Inspection caméra"]
    if profession in ("electricien", "électricien", "electricite", "électricité"):
        return ["Installation électrique", "Dépannage électrique", "Éclairage",
                "Mise aux normes", "Maintenance électrique", "Diagnostic électrique",
                "Tableau électrique", "Prises et interrupteurs"]
    if profession == "frigoriste":
        return ["Installation climatisation", "Dépannage climatisation", "Entretien climatisation",
                "Réfrigérateur", "Diagnostic froid", "Maintenance frigorifique",
                "Chambre froide", "Recharge climatisation"]
    if profession in ("chauffagiste", "chauffage"):
        return ["Installation chauffage", "Dépannage chauffage", "Entretien chaudière",
                "Réparation chaudière", "Chauffe-eau", "Diagnostic chauffage"]
    return ["Installation", "Dépannage", "Maintenance", "Diagnostic", "Réparation"]


def _generate_intervention_reference(conn):
    """Genere une reference unique FP-AAAA-XXXXXX."""
    year = datetime.now().year
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM requests WHERE reference LIKE ?",
        (f"FP-{year}-%",)).fetchone()["n"] + 1
    while True:
        ref = f"FP-{year}-{count:06d}"
        if not conn.execute("SELECT 1 FROM requests WHERE reference = ?",
                            (ref,)).fetchone():
            return ref
        count += 1


def _generate_fixpro_reference(conn):
    """Genere une reference unique FP-YYYY-XXXXXX."""
    year = datetime.now(timezone.utc).year
    count = conn.execute("SELECT COUNT(*) AS n FROM requests").fetchone()["n"] + 1
    while True:
        ref = f"FP-{year}-{count:06d}"
        if not conn.execute("SELECT 1 FROM requests WHERE reference = ?",
                            (ref,)).fetchone():
            return ref
        count += 1


@app.route("/demande/<int:artisan_id>", methods=["GET", "POST"])
@login_required
def demande(artisan_id):
    """Formulaire de demande d'intervention pour un technicien."""
    user = get_current_user()
    if user["role"] != "client":
        flash("Cette action est reservee aux clients.", "error")
        return redirect(url_for("artisans_page"))

    conn = get_db_connection()
    try:
        artisan = conn.execute(
            "SELECT * FROM users WHERE id = ? AND role IN ('artisan','technician')",
            (artisan_id,)).fetchone()
        if not artisan:
            flash("Technicien introuvable.", "error")
            return redirect(url_for("artisans_page"))

        services = _services_for_profession(artisan.get("profession") or "Autre")

        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            description = (request.form.get("description") or "").strip()
            service = (request.form.get("service") or "").strip()
            address = (request.form.get("address") or "").strip()
            requested_date = (request.form.get("requested_date") or "").strip()
            requested_time = (request.form.get("requested_time") or "").strip()
            urgency = (request.form.get("urgency") or "cette_semaine").strip()
            if urgency not in ("urgent", "cette_semaine", "pas_presse"):
                urgency = "cette_semaine"
            estimated_price = _to_float(request.form.get("estimated_price"), 0)
            phone_contact = (user.get("phone") or "").strip()
            latitude = float(user.get("latitude") or 0)
            longitude = float(user.get("longitude") or 0)

            if not title or not description:
                flash("Veuillez remplir le titre et la description.", "error")
                return redirect(url_for("demande", artisan_id=artisan_id))

            commission_rate = app.config.get("FIXPRO_COMMISSION_RATE", 0.10)
            commission_amount = estimated_price * commission_rate
            professional_amount = estimated_price - commission_amount
            reference = _generate_intervention_reference(conn)

            request_id = _insert_id(
                conn,
                "INSERT INTO requests"
                " (client_id, artisan_id, reference, title, description, service, category, address,"
                " latitude, longitude, requested_date, requested_time, status, urgency, phone_contact,"
                " estimated_price, commission_rate, commission_amount, professional_amount, payment_status,"
                " created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'REQUESTED', ?, ?, ?, ?, ?, ?, ?, 'PENDING', datetime('now'), datetime('now'))",
                (user["id"], artisan_id, reference, title, description, service,
                 artisan["profession"] or "Autre", address, latitude, longitude,
                 requested_date, requested_time, urgency, phone_contact,
                 estimated_price, commission_rate, commission_amount, professional_amount))
            conn.execute(
                "INSERT INTO intervention_history (request_id, status, actor, note, created_at)"
                " VALUES (?, ?, ?, ?, datetime('now'))",
                (request_id, "REQUESTED", user["full_name"], "Demande creee par le client"))
            conn.commit()
            flash(f"Demande {reference} creee. FixPro l'analyse et revient vers vous.", "success")
            return redirect(url_for("request_detail", request_id=request_id))
    finally:
        conn.close()

    return render_template("request_form.html", artisan=artisan, user=user, services=services)


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
        if _is_technician(user):
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


@app.route("/tickets")
@login_required
def client_tickets():
    """Liste des tickets de support du client connecte."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        tickets = conn.execute(
            "SELECT t.*, a.full_name AS artisan_name"
            " FROM admin_tickets t"
            " LEFT JOIN users a ON a.id = t.artisan_id"
            " WHERE t.client_id = ? ORDER BY t.updated_at DESC",
            (user["id"],)).fetchall()
    finally:
        conn.close()
    return render_template("tickets.html", tickets=tickets, user=user)


@app.route("/admin/tickets")
@login_required
@admin_required
def admin_tickets_list():
    """Dashboard admin : liste de tous les tickets de support."""
    conn = get_db_connection()
    try:
        tickets = conn.execute(
            "SELECT t.*, c.full_name AS client_name,"
            " last.content AS last_message, last.created_at AS last_message_at"
            " FROM admin_tickets t"
            " JOIN users c ON c.id = t.client_id"
            " LEFT JOIN ("
            "   SELECT m.ticket_id, m.content, m.created_at"
            "   FROM admin_messages m"
            "   WHERE m.id IN (SELECT MAX(id) FROM admin_messages GROUP BY ticket_id)"
            " ) last ON last.ticket_id = t.id"
            " ORDER BY t.updated_at DESC").fetchall()
    finally:
        conn.close()
    return render_template("admin_tickets.html", tickets=tickets)


@app.route("/tickets/<int:ticket_id>/close", methods=["POST"])
@login_required
def ticket_close(ticket_id):
    """Client ou admin ferme un ticket de support."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        ticket = conn.execute(
            "SELECT * FROM admin_tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not ticket:
            flash("Ticket introuvable.", "error")
            return redirect(url_for("client_tickets"))
        if user["role"] != "admin" and ticket["client_id"] != user["id"]:
            flash("Acces refuse.", "error")
            return redirect(url_for("client_tickets"))
        conn.execute("UPDATE admin_tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
        conn.commit()
        flash("Ticket marque comme resolu.", "success")
    finally:
        conn.close()
    if user["role"] == "admin":
        return redirect(url_for("admin_tickets_list"))
    return redirect(url_for("client_tickets"))


@app.route("/notifications")
@login_required
def notifications():
    """Liste les notifications in-app de l'utilisateur."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        try:
            rows = conn.execute(
                "SELECT * FROM notifications"
                " WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
                (user["id"],)).fetchall()
            unread = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications"
                " WHERE user_id = ? AND is_read = 0",
                (user["id"],)).fetchone()["n"]
        except Exception:
            rows = []
            unread = 0
    finally:
        conn.close()
    return render_template("notifications.html", user=user, notifications=rows, unread=unread)


@app.route("/notifications/<int:notif_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notif_id):
    user = get_current_user()
    conn = get_db_connection()
    try:
        notif = conn.execute("SELECT * FROM notifications WHERE id = ?", (notif_id,)).fetchone()
        if notif and (user["role"] == "admin" or notif["user_id"] == user["id"]):
            conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
            conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Demandes d'intervention
# ---------------------------------------------------------------------------

@app.route("/interventions")
@login_required
def technician_interventions():
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT r.*, u.full_name AS client_name"
            " FROM requests r"
            " LEFT JOIN users u ON u.id = r.client_id"
            " WHERE r.artisan_id = ?"
            " ORDER BY r.created_at DESC", (user["id"],)).fetchall()
    finally:
        conn.close()
    progress_statuses = ('in_progress', 'IN_PROGRESS', 'quote_accepted', 'en_route', 'EN_ROUTE',
                         'arrived', 'ARRIVED', 'assigned', 'ASSIGNED', 'accepted', 'ACCEPTED')
    completed_statuses = ('completed', 'COMPLETED')
    cancelled_statuses = ('cancelled', 'CANCELLED', 'rejected', 'REJECTED', 'refused', 'REFUSED')
    progress_count = sum(1 for r in rows if r.get("status") in progress_statuses)
    completed_count = sum(1 for r in rows if r.get("status") in completed_statuses)
    cancelled_count = sum(1 for r in rows if r.get("status") in cancelled_statuses)
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    return render_template("technician_interventions.html", requests=rows, user=user,
                           progress_count=progress_count, completed_count=completed_count,
                           cancelled_count=cancelled_count,
                           today_str=today.isoformat(), yesterday_str=yesterday.isoformat())


@app.route("/requests")
@login_required
def requests_list():
    user = get_current_user()
    conn = get_db_connection()
    try:
        if _is_technician(user):
            rows = conn.execute(
                "SELECT r.*, u.full_name AS client_name"
                " FROM requests r"
                " LEFT JOIN users u ON u.id = r.client_id"
                " WHERE LOWER(r.status) IN ('pending', 'requested', 'nouvelle demande')"
                " AND (r.artisan_id IS NULL OR r.artisan_id = ?)"
                " ORDER BY r.created_at DESC", (user["id"],)).fetchall()
            urgent_count = sum(1 for r in rows if r.get("urgency") == "urgent")
            today_count = sum(1 for r in rows if r.get("created_at") and str(r.get("created_at")).startswith(datetime.now().strftime("%Y-%m-%d")))
            return render_template("technician_requests.html", requests=rows, user=user,
                                   urgent_count=urgent_count, today_count=today_count)
        else:
            rows = conn.execute(
                "SELECT r.*, u.full_name AS artisan_name, u.photo_url AS artisan_photo,"
                " u.profession AS artisan_profession,"
                " rev.rating AS client_rating,"
                " (SELECT ROUND(AVG(rating), 1) FROM reviews WHERE artisan_id = r.artisan_id) AS artisan_rating"
                " FROM requests r"
                " LEFT JOIN users u ON u.id = r.artisan_id"
                " LEFT JOIN reviews rev ON rev.request_id = r.id AND rev.client_id = ?"
                " WHERE r.client_id = ?"
                " ORDER BY r.created_at DESC", (user["id"], user["id"])).fetchall()
        unread_count = 0
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                (user["id"],)).fetchone()
            unread_count = row["n"] if row else 0
        except Exception:
            unread_count = 0
    finally:
        conn.close()
    return render_template("requests.html", requests=rows, user=user, unread_count=unread_count)


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
    """Redirige vers la recherche en GET ; traite l'ancienne creation en POST."""
    if request.method == "GET":
        return redirect(url_for("artisans_page"))
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

            # Geocodage de l'adresse de la demande
            request_address = request.form.get("address", "").strip()
            client_lat = user.get("latitude") or session.get("client_lat")
            client_lon = user.get("longitude") or session.get("client_lon")
            if not _is_valid_coordinate(client_lat, client_lon) and request_address:
                client_lat, client_lon = _geocode_zone("Conakry", request_address)
                if not _is_valid_coordinate(client_lat, client_lon):
                    client_lat, client_lon = _geocode_query(request_address)[:2]
            client_lat = float(client_lat) if _is_valid_coordinate(client_lat, client_lon) else 0.0
            client_lon = float(client_lon) if _is_valid_coordinate(client_lat, client_lon) else 0.0

            # Selection du meilleur technicien disponible et proche
            best = _select_best_technician(conn, category, request_address,
                                           client_lat=client_lat,
                                           client_lon=client_lon)
            ref = _generate_fixpro_reference(conn)
            status = MISSION_STATUS_REQUESTED if not best else MISSION_STATUS_ASSIGNED
            artisan_id = best["id"] if best else None
            artisan_name = best["full_name"] if best else None

            new_request_id = _insert_id(
                conn,
                "INSERT INTO requests (client_id, artisan_id, reference, title, description, category,"
                " address, photo_url, diagnostic_price, budget, status, latitude, longitude, urgency)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user["id"], artisan_id, ref, title, description, category,
                 request_address,
                 request.form.get("photo_url", "").strip(),
                 float(category_row["diagnostic_price"]) if category_row else 0,
                 _to_float(request.form.get("budget")),
                 status, client_lat, client_lon,
                 request.form.get("urgency", "normal").strip()))

            _log_intervention_history(
                conn, new_request_id, None, status,
                f"Client {user['full_name']}",
                f"Demande creee ; reference {ref}",
                label="Nouvelle demande")

            create_notification(
                user["id"], "Demande enregistree",
                f"Votre demande '{title}' a ete enregistree.",
                "request_created", f"request_id:{new_request_id}",
                conn=conn)

            if best:
                create_notification(
                    best["id"], "Nouvelle demande",
                    f"Nouvelle demande : {title} - {request_address or 'Conakry'}",
                    "new_request", f"request_id:{new_request_id}",
                    conn=conn)
                _log_intervention_history(
                    conn, new_request_id, MISSION_STATUS_REQUESTED, MISSION_STATUS_ASSIGNED,
                    "Systeme",
                    f"Technicien attribue : {artisan_name} ({best.get('selection_reason', '')})",
                    label="Technicien attribue")
                flash("Demande creee et assignee au meilleur technicien disponible.", "success")
            else:
                create_admin_notification(
                    conn, "Nouvelle mission non attribuee",
                    f"Mission {ref} - {category} - {request_address or 'Conakry'} : aucun technicien disponible",
                    "no_technician",
                    f"request_id:{new_request_id}")
                flash("Demande d'intervention creee. Nous recherchons un technicien disponible.", "success")
            conn.commit()
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
            action = request.form.get("action", "")
            if action == "cancel" and user["role"] == "client":
                old_status = req["status"]
                new_status = MISSION_STATUS_CANCELLED
                if can_transition_request(old_status, new_status):
                    conn.execute(
                        "UPDATE requests SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (new_status, request_id))
                    _log_intervention_history(
                        conn, request_id, old_status, new_status,
                        user["full_name"], "Intervention annulee par le client",
                        label="Intervention annulee")
                    _notify_client(conn, request_id, "Intervention annulee",
                                   "Vous avez annule l'intervention.",
                                   "request_cancelled")
                    conn.commit()
                    flash("Intervention annulee.", "success")
                else:
                    flash("Cette intervention ne peut plus etre annulee.", "error")
                return redirect(url_for("request_detail", request_id=request_id))

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
        if artisan:
            artisan = dict(artisan)
            artisan["gradient"] = _avatar_gradient(artisan["full_name"])
        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name FROM messages m"
            " JOIN users u ON u.id = m.sender_id"
            " WHERE m.request_id = ? ORDER BY m.created_at ASC",
            (request_id,)).fetchall()
        payments = conn.execute(
            "SELECT * FROM payments WHERE request_id = ?"
            " ORDER BY created_at DESC", (request_id,)).fetchall()
        ticket_id = None
        if user and user["role"] == "client" and artisan:
            ticket = conn.execute(
                "SELECT id FROM admin_tickets"
                " WHERE client_id = ? AND artisan_id = ? LIMIT 1",
                (user["id"], artisan["id"])).fetchone()
            if ticket:
                ticket_id = ticket["id"]
    finally:
        conn.close()

    return render_template("request_detail.html", request_item=req,
                           client=client, artisan=artisan, messages=messages,
                           payments=payments, user=user,
                           ticket_id=ticket_id,
                           payment_method_label=payment_method_label)


@app.route("/requests/<int:request_id>/accept", methods=["POST"])
@login_required
def accept_request(request_id):
    user = get_current_user()
    if not _is_technician(user) or not user.get("is_verified"):
        flash("Seuls les techniciens verifies peuvent accepter une mission.", "error")
        return redirect(url_for("requests_list"))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["artisan_id"] != user["id"]:
            flash("Cette mission ne vous est pas assignee.", "error")
            return redirect(url_for("requests_list"))
        if req["status"] != MISSION_STATUS_ASSIGNED:
            flash("Cette mission n'est pas en attente d'acceptation.", "error")
            return redirect(url_for("requests_list"))

        conn.execute(
            "UPDATE requests SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (MISSION_STATUS_ACCEPTED, now_iso(), request_id, MISSION_STATUS_ASSIGNED))
        _log_intervention_history(
            conn, request_id, MISSION_STATUS_ASSIGNED, MISSION_STATUS_ACCEPTED,
            user["full_name"], f"Technicien {user['full_name']} a accepte la mission")
        create_notification(
            req["client_id"], "Technicien trouve",
            "Un technicien a accepte votre mission.",
            "request_accepted", f"request_id:{request_id}",
            conn=conn)
        conn.commit()
        flash("Mission acceptee. Vous pouvez maintenant demarrer l'intervention.", "success")
    finally:
        conn.close()
    return redirect(url_for("request_detail", request_id=request_id))


@app.route("/requests/<int:request_id>/quote", methods=["POST"])
@login_required
def propose_quote(request_id):
    user = get_current_user()
    if not _is_technician(user) or not user.get("is_verified"):
        flash("Seuls les artisans verifies peuvent proposer un devis.", "error")
        return redirect(url_for("requests_list"))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req or req["artisan_id"] != user["id"]:
            flash("Accès refusé.", "error")
            return redirect(url_for("requests_list"))
        if not can_transition_request(req["status"], "quote_proposed"):
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
        elif not can_transition_request(req["status"], "completed"):
            flash("Cette intervention ne peut pas etre marquee comme terminee.", "error")
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

        rate = app.config.get("FIXPRO_COMMISSION_RATE", 0.10)
        commission = amount * rate

        provider = get_payment_provider()
        result = provider.process(amount, method, reference, {
            "request_id": request_id,
            "client_id": user["id"],
            "details": details,
        })

        # Le statut vient du fournisseur. En l'absence de provider reel,
        # le mock renvoie 'pending' : le paiement n'est jamais considere
        # comme reussi sans confirmation explicite.
        conn.execute(
            "INSERT INTO payments (request_id, amount, commission_amount, method, status,"
            " reference, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request_id, amount, commission, method, result["status"], reference, details))
        conn.commit()

        if result.get("ok"):
            flash("Paiement de %s GNF enregistre par %s. Statut : %s." %
                  ("{:,}".format(int(amount)).replace(",", " "),
                   payment_method_label(method),
                   result["status"].replace("_", " ").title()),
                  "success")
        else:
            flash("Paiement refuse : %s" % result.get("message", ""), "error")
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
    if not user or not _is_technician(user):
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

csrf.exempt(api_technicien_status)


@app.route("/api/technicien/position", methods=["POST"])
@login_required
def api_technicien_position():
    """Recoit et stocke la position GPS en temps reel du technicien."""
    user = get_current_user()
    if not user or not _is_technician(user):
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
            "SELECT availability_status, is_active, is_verified, account_status"
            " FROM users WHERE id = ?",
            (user["id"],)).fetchone()
        if not artisan or artisan["is_active"] != 1 or artisan["is_verified"] != 1 \
                or artisan["account_status"] != "ACTIVE":
            return jsonify({"ok": False,
                            "reason": "Compte technicien inactif ou non verifie."}), 200
        if artisan["availability_status"] != "en_ligne":
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

csrf.exempt(api_technicien_position)


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


@app.route("/api/technicien/profile")
@login_required
def api_technicien_profile():
    """Renvoie les informations du technicien connecte (JSON pour le mobile)."""
    user = get_current_user()
    if not user or not _is_technician(user):
        return jsonify({"error": "Reserve aux techniciens."}), 403
    return jsonify({
        "id": user["id"],
        "full_name": user["full_name"],
        "profession": user.get("profession"),
        "phone": user.get("phone"),
        "availability_status": user.get("availability_status"),
        "is_active": user.get("is_active"),
        "is_verified": user.get("is_verified"),
        "account_status": user.get("account_status"),
    })

csrf.exempt(api_technicien_profile)


# ---------------------------------------------------------------------------
# Pages d'erreur
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    import sys, traceback
    logger.exception("Erreur interne: %s", error)
    # La trace complete n'est exposee qu'en mode debug : en production elle
    # divulguerait le code source, les requetes SQL et la logique interne.
    message = None
    if app.config.get("DEBUG"):
        exc_info = sys.exc_info()
        if exc_info[0]:
            message = "".join(traceback.format_exception(*exc_info))
        else:
            message = str(error)
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


def _migrate_db():
    """Applique les migrations legeres au demarrage."""
    try:
        conn = get_db_connection()
        try:
            is_pg = db.is_postgres_url(app.config.get("DATABASE_URL"))
            cols = conn.table_columns('conversations')
            if 'artisan_id' not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN artisan_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
            if 'request_id' not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN request_id INTEGER REFERENCES requests(id) ON DELETE SET NULL")
            if 'ai_active' not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN ai_active INTEGER DEFAULT 1")
            if 'ai_category' not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN ai_category TEXT")
            if 'urgency' not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN urgency TEXT")
            if 'needs_human' not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN needs_human INTEGER DEFAULT 0")
            if 'needs_technician' not in cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN needs_technician INTEGER DEFAULT 0")
            if 'collected_info' not in cols:
                if is_pg:
                    conn.execute("ALTER TABLE conversations ADD COLUMN collected_info JSONB DEFAULT '{}'")
                else:
                    conn.execute("ALTER TABLE conversations ADD COLUMN collected_info TEXT DEFAULT '{}'")

            if 'available_days' not in conn.table_columns('users'):
                conn.execute("ALTER TABLE users ADD COLUMN available_days TEXT")

            conn.commit()
            if is_pg:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS lia_logs ("
                    " id SERIAL PRIMARY KEY,"
                    " session_id TEXT,"
                    " client_id INTEGER,"
                    " client_name TEXT,"
                    " message TEXT NOT NULL,"
                    " reply TEXT,"
                    " status TEXT DEFAULT 'open',"
                    " admin_id INTEGER,"
                    " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                    " updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    ")")
            else:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS lia_logs ("
                    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " session_id TEXT,"
                    " client_id INTEGER,"
                    " client_name TEXT,"
                    " message TEXT NOT NULL,"
                    " reply TEXT,"
                    " status TEXT DEFAULT 'open',"
                    " admin_id INTEGER,"
                    " created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
                    " updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
                    ")")
            # Extension intervention_history pour l'historique des statuts.
            # Chaque ALTER est isole : sur PostgreSQL, une erreur (colonne deja
            # presente) abandonne la transaction, il faut donc rollback sinon
            # toutes les instructions suivantes echouent en cascade.
            try:
                conn.execute("ALTER TABLE intervention_history ADD COLUMN old_status TEXT")
                conn.commit()
            except Exception:
                conn.rollback()
            try:
                conn.execute("ALTER TABLE intervention_history ADD COLUMN new_status TEXT")
                conn.commit()
            except Exception:
                conn.rollback()
            # Jours de disponibilite du technicien
            try:
                conn.execute("ALTER TABLE users ADD COLUMN available_days TEXT")
                conn.commit()
            except Exception:
                conn.rollback()
            # Verification des techniciens : statut de dossier + metadonnees documents
            try:
                conn.execute("ALTER TABLE users ADD COLUMN verification_status TEXT")
                conn.commit()
            except Exception:
                conn.rollback()
            for _col, _type in (
                ("original_file_name", "TEXT"),
                ("reviewed_at", "TEXT"),
                ("reviewed_by", "INTEGER"),
                ("rejection_reason", "TEXT"),
            ):
                try:
                    conn.execute(f"ALTER TABLE technician_documents ADD COLUMN {_col} {_type}")
                    conn.commit()
                except Exception:
                    conn.rollback()
            # Backfill du statut de verification pour les comptes existants
            try:
                conn.execute(
                    "UPDATE users SET verification_status = 'APPROVED'"
                    " WHERE role = 'technician' AND is_verified = 1"
                    " AND (verification_status IS NULL OR verification_status = '')")
                conn.execute(
                    "UPDATE users SET verification_status = 'PENDING_REVIEW'"
                    " WHERE role = 'technician' AND (is_verified = 0 OR is_verified IS NULL)"
                    " AND (verification_status IS NULL OR verification_status = '')"
                    " AND (account_status IS NULL OR account_status NOT IN ('DELETED', 'SUSPENDED'))")
                conn.commit()
            except Exception:
                conn.rollback()
            # Normalisation des roles et statuts legacy
            try:
                conn.execute("UPDATE users SET role = 'technician' WHERE role = 'artisan'")
                conn.execute(
                    "UPDATE users SET account_status = 'ACTIVE' WHERE account_status IS NULL OR account_status = ''")
                _verif_guard = (
                    " AND (verification_status IS NULL OR verification_status = 'APPROVED')"
                    if app.config.get("TECH_VERIFICATION_ENABLED") else "")
                conn.execute(
                    "UPDATE users SET is_verified = 1, is_active = 1, account_status = 'ACTIVE'"
                    " WHERE role = 'technician' AND (account_status IS NULL OR account_status != 'DELETED')"
                    + _verif_guard)
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('pending','requested')",
                    (MISSION_STATUS_REQUESTED,))
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('assigned')",
                    (MISSION_STATUS_ASSIGNED,))
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('accepted')",
                    (MISSION_STATUS_ACCEPTED,))
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('en_route')",
                    (MISSION_STATUS_EN_ROUTE,))
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('arrived')",
                    (MISSION_STATUS_ARRIVED,))
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('in_progress')",
                    (MISSION_STATUS_IN_PROGRESS,))
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('completed')",
                    (MISSION_STATUS_COMPLETED,))
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('rejected','refused')",
                    (MISSION_STATUS_REFUSED,))
                conn.execute(
                    "UPDATE requests SET status = ? WHERE LOWER(status) IN ('cancelled')",
                    (MISSION_STATUS_CANCELLED,))
                conn.commit()
            except Exception:
                conn.rollback()
            # Table des contacts clients anonymes provenant des fiches techniciens
            if is_pg:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS client_contacts ("
                    " id SERIAL PRIMARY KEY,"
                    " client_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
                    " artisan_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
                    " first_name TEXT NOT NULL,"
                    " last_name TEXT NOT NULL,"
                    " phone TEXT NOT NULL,"
                    " status TEXT DEFAULT 'nouveau',"
                    " source TEXT DEFAULT 'profil_artisan',"
                    " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                    " updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    ")")
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS client_contact_events ("
                    " id SERIAL PRIMARY KEY,"
                    " contact_id INTEGER NOT NULL REFERENCES client_contacts(id) ON DELETE CASCADE,"
                    " event_type TEXT NOT NULL,"
                    " details TEXT,"
                    " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    ")")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_client_contacts_artisan ON client_contacts(artisan_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_client_contacts_phone ON client_contacts(phone)")
            else:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS client_contacts ("
                    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " client_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
                    " artisan_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
                    " first_name TEXT NOT NULL,"
                    " last_name TEXT NOT NULL,"
                    " phone TEXT NOT NULL,"
                    " status TEXT DEFAULT 'nouveau',"
                    " source TEXT DEFAULT 'profil_artisan',"
                    " created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
                    " updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
                    ")")
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS client_contact_events ("
                    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " contact_id INTEGER NOT NULL REFERENCES client_contacts(id) ON DELETE CASCADE,"
                    " event_type TEXT NOT NULL,"
                    " details TEXT,"
                    " created_at TEXT DEFAULT CURRENT_TIMESTAMP"
                    ")")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_client_contacts_artisan ON client_contacts(artisan_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_client_contacts_phone ON client_contacts(phone)")

            conn.commit()
        except Exception as e:
            logger.warning("Migration conversations impossible: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass

        # --- Abonnements techniciens (dashboard admin v2) -------------------
        try:
            _migrate_subscriptions(conn)
            conn.commit()
        except Exception as e:
            logger.warning("Migration abonnements impossible: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass

        # --- Compte administrateur (a partir des variables d'env) -----------
        try:
            _bootstrap_admin(conn)
            conn.commit()
        except Exception as e:
            logger.warning("Bootstrap admin impossible: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Connexion DB indisponible pour migration: %s", e)


def _bootstrap_admin(conn):
    """Cree / met a jour le compte administrateur a partir des variables
    d'environnement ADMIN_EMAILS (1er email) et ADMIN_PASSWORD.

    Les variables font foi : changer ADMIN_PASSWORD dans l'hebergeur puis
    redeployer met a jour le mot de passe au demarrage suivant.
    """
    emails = app.config.get("ADMIN_EMAILS") or []
    password = (app.config.get("ADMIN_PASSWORD") or "").strip()
    if not emails or not password:
        return

    email = emails[0].strip().lower()
    pw_hash = generate_password_hash(password)
    has_role_col = "admin_role" in conn.table_columns("users")

    existing = conn.execute(
        "SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE users SET password_hash = ?, role = 'admin', is_active = 1,"
            " is_verified = 1 WHERE id = ?", (pw_hash, existing["id"]))
        if has_role_col:
            conn.execute(
                "UPDATE users SET admin_role = COALESCE(admin_role, 'owner') WHERE id = ?",
                (existing["id"],))
        logger.info("Compte admin mis a jour : %s", email)
        return

    phone = "+000" + "".join(ch for ch in email if ch.isdigit())[:8] or "+000000000"
    cols = "email, phone, password_hash, role, full_name, is_verified, is_active"
    vals = [email, phone, pw_hash, "admin", "Administrateur", 1, 1]
    if has_role_col:
        cols += ", admin_role"
        vals.append("owner")
    placeholders = ", ".join("?" for _ in vals)
    conn.execute(
        "INSERT INTO users (%s) VALUES (%s)" % (cols, placeholders), tuple(vals))
    logger.info("Compte admin cree : %s", email)


def _migrate_subscriptions(conn):
    """Cree les tables d'abonnement et seme les 3 plans par defaut.

    Compatible SQLite (dev/test) et PostgreSQL (prod).
    """
    pk = "SERIAL PRIMARY KEY" if conn.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = "TIMESTAMP" if conn.is_postgres else "TEXT"

    if "admin_role" not in conn.table_columns("users"):
        conn.execute("ALTER TABLE users ADD COLUMN admin_role TEXT")
        conn.execute("UPDATE users SET admin_role = 'owner' WHERE role = 'admin'")

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS subscription_plans ("
        f" id {pk}, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,"
        f" price_month INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'GNF',"
        f" features TEXT DEFAULT '', is_active INTEGER NOT NULL DEFAULT 1,"
        f" sort_order INTEGER NOT NULL DEFAULT 0,"
        f" created_at {ts} DEFAULT CURRENT_TIMESTAMP, updated_at {ts} DEFAULT CURRENT_TIMESTAMP)")

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS technician_subscriptions ("
        f" id {pk},"
        f" technician_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        f" plan_id INTEGER REFERENCES subscription_plans(id) ON DELETE SET NULL,"
        f" status TEXT NOT NULL DEFAULT 'TRIAL',"
        f" start_date {ts} DEFAULT CURRENT_TIMESTAMP, end_date {ts},"
        f" auto_renew INTEGER NOT NULL DEFAULT 1,"
        f" created_at {ts} DEFAULT CURRENT_TIMESTAMP, updated_at {ts} DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tech_subs_technician ON technician_subscriptions(technician_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tech_subs_status ON technician_subscriptions(status)")

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS subscription_payments ("
        f" id {pk},"
        f" user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        f" subscription_id INTEGER REFERENCES technician_subscriptions(id) ON DELETE SET NULL,"
        f" plan_id INTEGER REFERENCES subscription_plans(id) ON DELETE SET NULL,"
        f" amount INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'GNF',"
        f" payment_method TEXT DEFAULT 'orange_money', transaction_reference TEXT,"
        f" status TEXT NOT NULL DEFAULT 'pending', paid_at {ts},"
        f" period_start {ts}, period_end {ts},"
        f" created_at {ts} DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_payments_user ON subscription_payments(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_payments_status ON subscription_payments(status)")

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS complaints ("
        f" id {pk},"
        f" client_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
        f" technician_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
        f" request_id INTEGER REFERENCES requests(id) ON DELETE SET NULL,"
        f" subject TEXT NOT NULL, message TEXT DEFAULT '',"
        f" priority TEXT NOT NULL DEFAULT 'normal', status TEXT NOT NULL DEFAULT 'new',"
        f" created_at {ts} DEFAULT CURRENT_TIMESTAMP, resolved_at {ts},"
        f" resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL, resolution_note TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status)")

    for code, name, price, order, features in _DEFAULT_PLANS:
        exists = conn.execute(
            "SELECT 1 FROM subscription_plans WHERE code = ?", (code,)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO subscription_plans (code, name, price_month, sort_order, features)"
                " VALUES (?, ?, ?, ?, ?)",
                (code, name, price, order, features))


_DEFAULT_PLANS = [
    ("basic", "Basic", 50000, 1,
     "Profil verifie\nApparait dans la recherche\nMessagerie avec les clients"),
    ("pro", "Pro", 100000, 2,
     "Tout Basic\nMise en avant dans la recherche\nStatistiques detaillees\nSupport prioritaire"),
    ("premium", "Premium", 200000, 3,
     "Tout Pro\nBadge Premium\nEn tete des resultats\nAccompagnement dedie"),
]


@app.route("/admin/commissions")
@login_required
@admin_required
def admin_commissions():
    """Suivi des commissions FixPro."""
    user = get_current_user()
    rate = app.config.get("FIXPRO_COMMISSION_RATE", 0.10)
    conn = get_db_connection()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        total = conn.execute("SELECT COALESCE(SUM(commission_amount), 0) AS s FROM payments WHERE status = 'completed'").fetchone()["s"]
        today_sum = conn.execute(
            "SELECT COALESCE(SUM(commission_amount), 0) AS s FROM payments WHERE status = 'completed' AND created_at LIKE ?",
            (today + "%",)).fetchone()["s"]
        week_sum = conn.execute(
            "SELECT COALESCE(SUM(commission_amount), 0) AS s FROM payments WHERE status = 'completed' AND created_at >= ?",
            ((datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()["s"]
        month_sum = conn.execute(
            "SELECT COALESCE(SUM(commission_amount), 0) AS s FROM payments WHERE status = 'completed' AND created_at LIKE ?",
            (month + "%",)).fetchone()["s"]
        commissions = conn.execute(
            "SELECT p.*, u.full_name AS client_name, a.full_name AS artisan_name, r.reference"
            " FROM payments p"
            " JOIN requests r ON r.id = p.request_id"
            " JOIN users u ON u.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            " WHERE p.status = 'completed'"
            " ORDER BY p.created_at DESC").fetchall()
    finally:
        conn.close()
    return render_template("admin_commissions.html", user=user, rate=rate,
                           total=total, today=today_sum, week=week_sum, month=month_sum,
                           commissions=commissions)


@app.route("/admin/avis")
@login_required
@admin_required
def admin_reviews():
    """Gestion des avis clients."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        reviews = conn.execute(
            "SELECT r.*, c.full_name AS client_name, a.full_name AS artisan_name, req.reference"
            " FROM reviews r"
            " JOIN users c ON c.id = r.client_id"
            " JOIN users a ON a.id = r.artisan_id"
            " LEFT JOIN requests req ON req.id = r.request_id"
            " ORDER BY r.created_at DESC").fetchall()
    finally:
        conn.close()
    return render_template("admin_reviews.html", user=user, reviews=reviews)


@app.route("/admin/activite")
@login_required
@admin_required
def admin_activity():
    """Journal d'activite des administrateurs."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        logs = conn.execute(
            "SELECT * FROM admin_logs ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    return render_template("admin_activity.html", user=user, logs=logs)


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


# ---------------------------------------------------------------------------
# API interne pour le dashboard admin Next.js
# ---------------------------------------------------------------------------

_SENSITIVE_USER_KEYS = ("password_hash", "reset_token", "activation_token")


def _public_user(row, extra_keys=()):
    """Convertit une ligne utilisateur en dict sans les champs sensibles.

    Evite de divulguer les hachages de mot de passe (et autres secrets) dans
    les reponses JSON de l'API admin.
    """
    if row is None:
        return None
    clean = dict(row)
    for key in _SENSITIVE_USER_KEYS + tuple(extra_keys):
        clean.pop(key, None)
    return clean


def _require_api_key():
    """Verifie la cle API partagee entre Flask et le dashboard Next.js.

    La cle vide n'est jamais acceptee, meme en developpement.
    """
    key = app.config.get("ADMIN_API_KEY", "")
    if not key:
        return jsonify({"error": "ADMIN_API_KEY non configuree"}), 401
    header = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(str(header), str(key)):
        return jsonify({"error": "Non autorise"}), 401
    return None


@app.route("/api/admin/stats")
@limiter.limit("100 per hour")
def api_admin_stats():
    """KPI du dashboard admin."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stats = {
            "techniciens": conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'technician'").fetchone()["n"],
            "clients": conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'client'").fetchone()["n"],
            "demandes_mois": conn.execute(
                "SELECT COUNT(*) AS n FROM requests WHERE created_at LIKE ?",
                (datetime.now(timezone.utc).strftime("%Y-%m") + "%",)).fetchone()["n"],
            "revenus": int(conn.execute(
                "SELECT COALESCE(SUM(commission_amount), 0) AS commission"
                " FROM payments WHERE status = 'completed' AND created_at LIKE ?",
                (today + "%",)).fetchone()["commission"]),
            "avis_moyen": conn.execute(
                "SELECT COALESCE(AVG(rating), 0) AS avg FROM reviews").fetchone()["avg"],
            "pending_artisans": conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role = 'technician' AND is_verified = 0").fetchone()["n"],
            "open_requests": conn.execute(
                "SELECT COUNT(*) AS n FROM requests WHERE status NOT IN ('completed', 'cancelled')").fetchone()["n"],
        }
        return jsonify(stats)
    finally:
        conn.close()


@app.route("/api/admin/techniciens")
@limiter.limit("100 per hour")
def api_admin_techniciens():
    """Liste des techniciens pour le dashboard admin."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT u.*,"
            " COUNT(DISTINCT d.id) AS doc_count,"
            " COUNT(DISTINCT req_completed.id) AS completed,"
            " COALESCE(AVG(r.rating), 0) AS avg_rating,"
            " COUNT(DISTINCT r.id) AS review_count"
            " FROM users u"
            " LEFT JOIN technician_documents d ON d.technician_id = u.id"
            " LEFT JOIN requests req_completed ON req_completed.artisan_id = u.id AND req_completed.status = 'completed'"
            " LEFT JOIN reviews r ON r.artisan_id = u.id"
            " WHERE u.role = 'technician'"
            " GROUP BY u.id"
            " ORDER BY u.is_verified ASC, u.is_active DESC, u.created_at DESC").fetchall()
        return jsonify([_public_user(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/admin/techniciens", methods=["POST"])
@limiter.limit("100 per hour")
def api_admin_create_technicien():
    """Creation d'un technicien depuis le dashboard admin."""
    auth = _require_api_key()
    if auth:
        return auth
    data = request.get_json(silent=True, force=True) or {}
    full_name = data.get("full_name", "").strip()
    phone = _phone_with_prefix(data.get("phone", "").strip())
    email = data.get("email", "").strip() or None
    profession = data.get("profession", "").strip()
    password = data.get("password", "").strip()
    address = data.get("address", "").strip()
    photo = data.get("photo", "").strip()
    identity_doc = data.get("identity_doc", "").strip()

    if not full_name or not phone or not profession or not password:
        return jsonify({"error": "Tous les champs sont obligatoires."}), 400

    conn = get_db_connection()
    try:
        if conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone():
            return jsonify({"error": "Ce numero de telephone est deja utilise."}), 409

        lat, lon = _geocode_zone(address, "") if address else (0.0, 0.0)
        store = storage.get_storage()
        photo_url = photo
        if photo:
            try:
                photo_url = store.upload("photo", photo)
            except ValueError as exc:
                return jsonify({"error": f"Photo invalide : {exc}"}), 400

        conn.execute(
            "INSERT INTO users (full_name, phone, email, password_hash, role, profession,"
            " city, latitude, longitude, is_verified, is_active, availability_status, photo_url)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (full_name, phone, email, generate_password_hash(password),
             "artisan", profession, address, lat, lon, 1, 1, "hors_ligne", photo_url))
        conn.commit()

        artisan = conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
        artisan_id = artisan["id"]

        if identity_doc:
            try:
                id_url = store.upload("identite", identity_doc)
                mime, ext, _ = _parse_base64_file(identity_doc)
                conn.execute(
                    "INSERT INTO technician_documents (technician_id, document_type,"
                    " file_name, mime_type, content_base64)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (artisan_id, "identity", f"identite{ext}", mime or "application/octet-stream", id_url))
                conn.commit()
            except ValueError as exc:
                return jsonify({"error": f"Document invalide : {exc}"}), 400

        user = conn.execute(
            "SELECT u.*,"
            " COUNT(DISTINCT d.id) AS doc_count, 0 AS completed, 0 AS avg_rating, 0 AS review_count"
            " FROM users u"
            " LEFT JOIN technician_documents d ON d.technician_id = u.id"
            " WHERE u.phone = ?"
            " GROUP BY u.id", (phone,)).fetchone()
        return jsonify(_public_user(user))
    finally:
        conn.close()


@app.route("/api/admin/clients")
@limiter.limit("100 per hour")
def api_admin_clients():
    """Liste des clients pour le dashboard admin."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT u.id, u.full_name, u.phone, u.email,"
            " u.created_at, u.latitude, u.longitude,"
            " COUNT(DISTINCT r.id) AS request_count,"
            " MAX(r.created_at) AS last_request"
            " FROM users u"
            " LEFT JOIN requests r ON r.client_id = u.id"
            " WHERE u.role = 'client'"
            " GROUP BY u.id"
            " ORDER BY u.created_at DESC").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/admin/categories")
@limiter.limit("100 per hour")
def api_admin_categories():
    """Liste des categories/metiers avec statistiques admin."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        requests_by_cat = conn.execute(
            "SELECT LOWER(category) AS name, COUNT(*) AS request_count,"
            " COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed"
            " FROM requests"
            " WHERE category IS NOT NULL"
            " GROUP BY LOWER(category)").fetchall()
        artisans_by_prof = conn.execute(
            "SELECT LOWER(profession) AS name, COUNT(*) AS artisan_count"
            " FROM users"
            " WHERE role = 'technician' AND profession IS NOT NULL"
            " GROUP BY LOWER(profession)").fetchall()
        by_name = {}
        for r in requests_by_cat:
            by_name[r['name']] = {
                'name': r['name'],
                'request_count': r['request_count'],
                'completed_count': r['completed'],
            }
        for a in artisans_by_prof:
            name = a['name']
            if name in by_name:
                by_name[name]['artisan_count'] = a['artisan_count']
            else:
                by_name[name] = {
                    'name': name,
                    'request_count': 0,
                    'completed_count': 0,
                    'artisan_count': a['artisan_count'],
                }
        result = sorted(by_name.values(), key=lambda x: x['request_count'], reverse=True)
        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/admin/demandes")
@limiter.limit("100 per hour")
def api_admin_demandes():
    """Liste des demandes pour le dashboard admin."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT r.*, c.full_name AS client_name, c.phone AS client_phone,"
            " a.full_name AS artisan_name, a.phone AS artisan_phone, a.profession AS artisan_profession,"
            " a.latitude AS artisan_lat, a.longitude AS artisan_lon"
            " FROM requests r"
            " LEFT JOIN users c ON c.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            " ORDER BY r.updated_at DESC").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/admin/paiements")
@limiter.limit("100 per hour")
def api_admin_paiements():
    """Liste des paiements pour le dashboard admin."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT p.*,"
            " c.full_name AS client_name,"
            " a.full_name AS artisan_name,"
            " r.title AS request_title"
            " FROM payments p"
            " LEFT JOIN requests r ON r.id = p.request_id"
            " LEFT JOIN users c ON c.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            " ORDER BY p.created_at DESC").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/admin/lia-logs")
@limiter.limit("100 per hour")
def api_admin_lia_logs():
    """Historique des conversations avec Lia pour le dashboard admin."""
    auth = _require_api_key()
    if auth:
        return auth
    status = request.args.get("status", "all")
    search = request.args.get("q", "").strip().lower()
    conn = get_db_connection()
    try:
        where = "1=1"
        params = []
        if status in ("open", "handling", "closed"):
            where += " AND status = ?"
            params.append(status)
        rows = conn.execute(
            "SELECT id, session_id, client_id, client_name, message, reply, status, created_at"
            " FROM lia_logs WHERE " + where + " ORDER BY created_at DESC", params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if search and not (
                search in (d.get("client_name") or "").lower()
                or search in (d.get("message") or "").lower()
                or search in (d.get("reply") or "").lower()):
                continue
            result.append(d)
        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/admin/lia-logs/<int:log_id>/take", methods=["POST"])
@limiter.limit("100 per hour")
def api_admin_take_lia_log(log_id):
    """Marque une conversation Lia comme prise en main."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE lia_logs SET status = 'handling', updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), log_id))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/admin/lia-logs/<int:log_id>/close", methods=["POST"])
@limiter.limit("100 per hour")
def api_admin_close_lia_log(log_id):
    """Ferme une conversation Lia."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE lia_logs SET status = 'closed', updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), log_id))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/admin/lia-logs/<int:log_id>/messages")
@limiter.limit("100 per hour")
def api_admin_lia_log_messages(log_id):
    """Retourne les messages complets d'une conversation Lia."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        log = conn.execute("SELECT session_id FROM lia_logs WHERE id = ?", (log_id,)).fetchone()
        if not log:
            return jsonify({"error": "Log introuvable."}), 404
        session_id = log["session_id"] or ""
        if not session_id.startswith("conv-"):
            return jsonify({"messages": []})
        try:
            conversation_id = int(session_id.split("-", 1)[1])
        except ValueError:
            return jsonify({"messages": []})
        rows = conn.execute(
            "SELECT sender_role, content, created_at"
            " FROM conversation_messages"
            " WHERE conversation_id = ?"
            " ORDER BY created_at ASC",
            (conversation_id,)).fetchall()
        return jsonify({"messages": [dict(r) for r in rows]})
    finally:
        conn.close()


@app.route("/api/admin/lia-logs/<int:log_id>/reply", methods=["POST"])
@limiter.limit("100 per hour")
def api_admin_reply_lia_log(log_id):
    """Repond a une conversation Lia en tant qu'administrateur."""
    auth = _require_api_key()
    if auth:
        return auth
    data = request.get_json(silent=True, force=True) or {}
    content = (data.get("message") or "").strip()
    if not content:
        return jsonify({"error": "Message vide."}), 400
    conn = get_db_connection()
    try:
        log = conn.execute("SELECT session_id FROM lia_logs WHERE id = ?", (log_id,)).fetchone()
        if not log:
            return jsonify({"error": "Log introuvable."}), 404
        session_id = log["session_id"] or ""
        if not session_id.startswith("conv-"):
            return jsonify({"error": "Cette conversation n'est pas associee a un client."}), 400
        try:
            conversation_id = int(session_id.split("-", 1)[1])
        except ValueError:
            return jsonify({"error": "Conversation invalide."}), 400
        conv = conn.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not conv:
            return jsonify({"error": "Conversation introuvable."}), 404
        fixpro_user = conn.execute(
            "SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        admin_id = fixpro_user["id"] if fixpro_user else 0
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO conversation_messages"
            " (conversation_id, sender_id, sender_role, content) VALUES (?, ?, ?, ?)",
            (conversation_id, admin_id, "admin", content))
        conn.execute(
            "UPDATE conversations SET status = 'admin_active', updated_at = ? WHERE id = ?",
            (now, conversation_id))
        conn.execute(
            "UPDATE lia_logs SET status = 'handling', updated_at = ? WHERE session_id = ?",
            (now, session_id))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()

csrf.exempt(api_admin_lia_logs)
csrf.exempt(api_admin_take_lia_log)
csrf.exempt(api_admin_close_lia_log)
csrf.exempt(api_admin_lia_log_messages)
csrf.exempt(api_admin_reply_lia_log)


@app.route("/api/admin/parametres")
@limiter.limit("100 per hour")
def api_admin_parametres():
    """Configuration affichable du panel admin."""
    auth = _require_api_key()
    if auth:
        return auth
    return jsonify({
        "commission_rate": app.config.get("FIXPRO_COMMISSION_RATE", 0.10),
        "admin_dashboard_url": app.config.get("ADMIN_DASHBOARD_URL", ""),
        "log_level": app.config.get("LOG_LEVEL", "INFO"),
        "environment": app.config.get("FLASK_ENV", "development"),
        "database_url": "configure" if app.config.get("DATABASE_URL") else "sqlite",
        "smtp_host": app.config.get("SMTP_HOST", ""),
        "admin_email": app.config.get("ADMIN_EMAIL", ""),
    })


@app.route("/api/admin/dashboard")
@limiter.limit("100 per hour")
def api_admin_dashboard():
    """Vue consolidée du tableau de bord admin."""
    auth = _require_api_key()
    if auth:
        return auth

    now = datetime.now(timezone.utc)
    mois_debut = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    trente_jours = (now - timedelta(days=30)).isoformat()
    sept_jours = (now - timedelta(days=7)).isoformat()

    _PROFESSION_LABEL = {
        "plombier": "Plomberie",
        "electricien": "Électricité",
        "frigoriste": "Frigoriste",
        "menuisier": "Menuiserie",
        "chauffagiste": "Chauffagiste",
        "serrurier": "Serrurier",
        "peintre": "Peinture",
        "maçon": "Maçonnerie",
        "macon": "Maçonnerie",
    }

    def _status_index(status):
        if status in ("completed",):
            return 3
        if status in ("in_progress", "on_the_way"):
            return 2
        if status in ("assigned", "quote_proposed", "quote_accepted", "pending"):
            return 1
        return 0

    def _label(cat):
        return _PROFESSION_LABEL.get(cat.lower(), cat.capitalize()) if cat else "Autre"

    conn = get_db_connection()
    try:
        interventions_mois = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE created_at >= ?",
            (mois_debut,)).fetchone()["n"]

        revenu_gnf = int(conn.execute(
            "SELECT COALESCE(SUM(commission_amount), 0) AS s FROM payments"
            " WHERE status = 'completed' AND created_at >= ?",
            (mois_debut,)).fetchone()["s"])

        total_techniciens = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'technician'").fetchone()["n"]
        actifs_techniciens = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'technician' AND is_active = 1").fetchone()["n"]

        total_termine = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE status = 'completed'").fetchone()["n"]
        total_non_cancel = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE status != 'cancelled'").fetchone()["n"]
        taux_resolution = round((total_termine / total_non_cancel) * 100, 0) if total_non_cancel else 0

        rows_cat = conn.execute(
            "SELECT category, COUNT(*) AS n FROM requests"
            " WHERE created_at >= ? GROUP BY category",
            (trente_jours,)).fetchall()
        categories = [
            {"name": _label(r["category"]), "count": r["n"]}
            for r in rows_cat
        ]

        rows_req = conn.execute(
            "SELECT r.id, r.reference, r.title, r.category, r.status, r.latitude, r.longitude,"
            " c.full_name AS client_name, a.full_name AS artisan_name, a.profession AS artisan_profession,"
            " a.latitude AS artisan_lat, a.longitude AS artisan_lon"
            " FROM requests r"
            " JOIN users c ON c.id = r.client_id"
            " LEFT JOIN users a ON a.id = r.artisan_id"
            " ORDER BY r.updated_at DESC LIMIT 6").fetchall()
        interventions = []
        for r in rows_req:
            client_lat = _to_float(r["latitude"])
            client_lon = _to_float(r["longitude"])
            art_lat = _to_float(r["artisan_lat"])
            art_lon = _to_float(r["artisan_lon"])
            if _is_valid_coordinate(client_lat, client_lon) and _is_valid_coordinate(art_lat, art_lon):
                dist = round(_haversine(client_lat, client_lon, art_lat, art_lon), 1)
                dist_label = f"{dist} km"
            else:
                dist_label = "—"
            cat_prof = _domain_to_profession(r["category"]) or ""
            art_prof = _domain_to_profession(r["artisan_profession"]) or ""
            mismatch = bool(cat_prof and art_prof and cat_prof != art_prof)
            interventions.append({
                "code": r["reference"] or f"FP-{r['id']:06d}",
                "client": r["client_name"],
                "pb": r["title"],
                "cat": _label(r["category"]),
                "tech": r["artisan_name"] or "Non assigne",
                "techCat": r["artisan_profession"] or "",
                "status": _status_index(r["status"]),
                "dist": dist_label,
                "mismatch": mismatch,
            })

        rows_alert = conn.execute(
            "SELECT r.id, a.full_name AS artisan_name, a.profession AS artisan_profession, r.category"
            " FROM requests r"
            " JOIN users a ON a.id = r.artisan_id"
            " WHERE r.created_at >= ?",
            (sept_jours,)).fetchall()
        alert_map = {}
        for r in rows_alert:
            cat = _domain_to_profession(r["category"]) or ""
            art_prof = (r["artisan_profession"] or "").lower()
            if cat and art_prof and cat != art_prof:
                name = r["artisan_name"]
                if name not in alert_map:
                    alert_map[name] = {"cat": r["artisan_profession"], "count": 0, "categories": set()}
                alert_map[name]["count"] += 1
                alert_map[name]["categories"].add(_label(r["category"]))

        alert = None
        if alert_map:
            name, info = next(iter(alert_map.items()))
            cats = " et ".join(info["categories"])
            alert = {
                "name": name,
                "cat": info["cat"],
                "count": info["count"],
                "categories": cats,
            }

        rows_tech = conn.execute(
            "SELECT full_name, profession, availability_status FROM users"
            " WHERE role = 'technician' ORDER BY availability_status = 'en_ligne' DESC, full_name").fetchall()
        technicians = [
            {"name": t["full_name"], "cat": t["profession"], "online": t["availability_status"] == "en_ligne"}
            for t in rows_tech
        ]

        user = get_current_user()

        return jsonify({
            "kpis": {
                "interventions_ce_mois": interventions_mois,
                "revenu_commissions_gnf": revenu_gnf,
                "revenu_commissions_usd": round(revenu_gnf / 8730, 0),
                "techniciens_actifs": actifs_techniciens,
                "techniciens_total": total_techniciens,
                "taux_resolution": int(taux_resolution),
            },
            "categories": categories,
            "interventions": interventions,
            "technicians": technicians,
            "alert": alert,
            "admin": (user and user.get("full_name")) or "Mamadou Bah",
        })
    finally:
        conn.close()


@app.route("/api/admin/techniciens/<int:artisan_id>/verify", methods=["POST"])
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_verify_artisan(artisan_id):
    """Valider un technicien."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET is_verified = 1 WHERE id = ? AND role = 'technician'", (artisan_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/techniciens/<int:artisan_id>/reject", methods=["POST"])
@limiter.limit("60 per hour", methods=["POST"])
def api_admin_reject_artisan(artisan_id):
    """Refuser/supprimer un technicien."""
    auth = _require_api_key()
    if auth:
        return auth
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ? AND role = 'technician' AND is_verified = 0", (artisan_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


csrf.exempt(api_admin_stats)
csrf.exempt(api_admin_techniciens)
csrf.exempt(api_admin_create_technicien)
csrf.exempt(api_admin_demandes)
csrf.exempt(api_admin_clients)
csrf.exempt(api_admin_categories)
csrf.exempt(api_admin_paiements)
csrf.exempt(api_admin_parametres)
csrf.exempt(api_admin_verify_artisan)
csrf.exempt(api_admin_reject_artisan)


# ---------------------------------------------------------------------------
# Messagerie client <-> administration
# ---------------------------------------------------------------------------

@app.route("/messages")
def client_messages():
    """Liste des conversations du client ou technicien connecte."""
    user = get_current_user()
    if not user:
        return redirect(url_for("lia"))
    conn = get_db_connection()
    try:
        conversations = conn.execute(
            "SELECT c.id, c.subject, c.status, c.created_at, c.updated_at,"
            " (SELECT content FROM conversation_messages WHERE conversation_id = c.id"
            " ORDER BY created_at DESC LIMIT 1) AS last_message,"
            " COALESCE(unread.n, 0) AS unread"
            " FROM conversations c"
            " LEFT JOIN ("
            "   SELECT conversation_id, COUNT(*) AS n"
            "   FROM conversation_messages"
            "   WHERE sender_role != 'client' AND is_read = 0"
            "   GROUP BY conversation_id"
            " ) unread ON unread.conversation_id = c.id"
            " WHERE c.client_id = ? OR c.artisan_id = ?"
            " ORDER BY c.updated_at DESC",
            (user["id"], user["id"])).fetchall()
    finally:
        conn.close()
    unread_count = sum(c.get("unread", 0) or 0 for c in conversations)
    return render_template("client_messages.html", conversations=conversations, user=user,
                           unread_count=unread_count)


@app.route("/messages/new", methods=["GET", "POST"])
@login_required
def client_message_new():
    """Nouvelle conversation client/technicien."""
    user = get_current_user()
    if user["role"] not in ("client", "admin", "artisan", "technician"):
        flash("Cet espace est reserve aux utilisateurs connectes.", "error")
        return redirect(url_for("index"))
    if request.method == "GET":
        subject = "Nouvelle conversation"
        conn = get_db_connection()
        try:
            if _is_technician(user):
                conv_id = _insert_id(
                    conn,
                    "INSERT INTO conversations (client_id, artisan_id, subject) VALUES (?, ?, ?)",
                    (user["id"], user["id"], subject))
            else:
                conv_id = _insert_id(
                    conn,
                    "INSERT INTO conversations (client_id, subject) VALUES (?, ?)",
                    (user["id"], subject))
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for("client_conversation", conversation_id=conv_id))
    if request.method == "POST":
        subject = (request.form.get("subject") or "").strip()
        content = (request.form.get("content") or "").strip()
        if not content:
            flash("Le message ne peut pas etre vide.", "error")
            return redirect(url_for("client_message_new"))
        conn = get_db_connection()
        try:
            if _is_technician(user):
                conv_id = _insert_id(
                    conn,
                    "INSERT INTO conversations (client_id, artisan_id, subject) VALUES (?, ?, ?)",
                    (user["id"], user["id"], subject))
                sender_role = "client"
            else:
                conv_id = _insert_id(
                    conn,
                    "INSERT INTO conversations (client_id, subject) VALUES (?, ?)",
                    (user["id"], subject))
                sender_role = "client"
            conn.execute(
                "INSERT INTO conversation_messages"
                " (conversation_id, sender_id, sender_role, content) VALUES (?, ?, ?, ?)",
                (conv_id, user["id"], sender_role, content))
            try:
                conn.execute(
                    "INSERT INTO lia_logs"
                    " (session_id, client_id, client_name, message, reply, status)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (f"conv-{conv_id}", user["id"], user.get("full_name") or "Client",
                     content, None, "open"))
            except Exception as e:
                logger.warning("Enregistrement message Lia impossible: %s", e)
            conn.commit()
            flash("Votre message a ete envoye a FixPro.", "success")
        finally:
            conn.close()
        return redirect(url_for("client_conversation", conversation_id=conv_id))
    return render_template("client_message_new.html", user=user)


@app.route("/lia", methods=["GET"])
def lia():
    """Page publique de discussion avec l'assistante FixPro."""
    if not session.get("lia_session"):
        session["lia_session"] = secrets.token_urlsafe(16)
    return render_template("lia.html", nav_user=get_current_user())


@app.route("/api/lia/chat", methods=["POST"])
@limiter.limit("100 per minute")
def api_lia_chat():
    """API de chat avec l'assistante FixPro."""
    data = request.get_json(silent=True, force=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Message vide."}), 400
    collected = session.get("lia_collected", {})
    result = ai_service.analyze_message(message, collected)
    session["lia_collected"] = result.get("collected_info", {})
    reply = result.get("response", "Desole, je n'ai pas compris.")
    user = get_current_user()
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO lia_logs (session_id, client_id, client_name, message, reply)"
            " VALUES (?, ?, ?, ?, ?)",
            (session.get("lia_session") or "anonymous",
             user["id"] if user else None,
             (user["full_name"] if user else session.get("lia_name")) or "Visiteur",
             message, reply))
        conn.commit()
    except Exception as e:
        logger.warning("Enregistrement Lia impossible: %s", e)
    finally:
        conn.close()
    return jsonify({"reply": reply})

csrf.exempt(api_lia_chat)



_CATEGORY_PROFESSION = {
    "plomberie": "plombier",
    "electricite": "electricien",
    "climatisation": "frigoriste",
    "refrigeration": "frigoriste",
    "serrurerie": "serrurier",
    "chauffagiste": "chauffagiste",
    "menuiserie": "menuisier",
    "peinture": "peintre",
    "maconnerie": "macon",
    "nettoyage": "nettoyage",
}


def _domain_to_profession(category):
    """Convertit le domaine detecte par l'IA en profession reelle."""
    if not category:
        return None
    return _CATEGORY_PROFESSION.get(category.lower(), category).lower()


def _create_intervention_from_chat(conn, conversation_id, client_id, analysis, artisan, sender_id, client_lat=None, client_lon=None):
    """Cree une intervention a partir d'une conversation."""
    ref = _generate_fixpro_reference(conn)
    info = analysis["collected_info"]
    title = (info.get("problem_detail") or _CATEGORY_PROFESSION.get(analysis.get("category"), analysis.get("category")) or "Demande FixPro").strip()
    description = info.get("problem_detail") or title
    category = _domain_to_profession(analysis["category"]) or "Autre"
    address = info.get("location") or "Conakry"
    urgency = analysis["urgency"] or "normal"
    lat = float(client_lat) if _is_valid_coordinate(client_lat, client_lon) else 0.0
    lon = float(client_lon) if _is_valid_coordinate(client_lat, client_lon) else 0.0
    now = datetime.now(timezone.utc).isoformat()
    artisan_id = artisan["id"]
    reason = artisan.get("selection_reason", "selection automatique")
    req_id = _insert_id(
        conn,
        "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, urgency, quote_amount, budget, latitude, longitude, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)",
        (client_id, artisan_id, ref, title, description, category, address,
         MISSION_STATUS_ASSIGNED, urgency, lat, lon, now, now))
    _log_intervention_history(conn, req_id, None, MISSION_STATUS_REQUESTED,
                             "Assistant FixPro", "Demande creee depuis la conversation",
                             label="Nouvelle demande")
    _log_intervention_history(conn, req_id, MISSION_STATUS_REQUESTED, MISSION_STATUS_ASSIGNED,
                             "Systeme", f"Technicien {artisan['full_name']} attribue — {reason}",
                             label="Technicien attribue")
    conn.execute(
        "INSERT INTO notifications (user_id, title, body, type, data)"
        " VALUES (?, ?, ?, ?, ?)",
        (artisan_id, "Nouvelle mission FixPro",
         f"{title} - {address} ({urgency})",
         "new_request", f"request_id:{req_id}"))
    conn.execute(
        "UPDATE conversations SET request_id = ?, status = 'converted_to_intervention' WHERE id = ?",
        (req_id, conversation_id))
    conn.execute(
        "INSERT INTO conversation_messages"
        " (conversation_id, sender_id, sender_role, content) VALUES (?, ?, ?, ?)",
        (conversation_id, sender_id, "ai",
         f"Votre intervention {ref} a ete creee. "
         f"Notre equipe l'a transmise au technicien selectionne. "
         "Vous serez tenu informe de son evolution."))
    return req_id


def _get_collected_from_messages(conn, conversation_id):
    """Recupere l'etat collecte depuis un message systeme."""
    row = conn.execute(
        "SELECT content FROM conversation_messages"
        " WHERE conversation_id = ? AND sender_role = 'system'"
        " ORDER BY id DESC LIMIT 1",
        (conversation_id,)).fetchone()
    if not row or not row["content"]:
        return {}
    try:
        return json.loads(row["content"])
    except Exception:
        return {}


def _save_collected_in_messages(conn, conversation_id, sender_id, collected):
    """Stocke l'etat collecte dans un message systeme pour eviter la colonne collected_info."""
    if collected is None:
        collected = {}
    payload = json.dumps(collected, ensure_ascii=False)
    conn.execute(
        "DELETE FROM conversation_messages"
        " WHERE conversation_id = ? AND sender_role = 'system'",
        (conversation_id,))
    conn.execute(
        "INSERT INTO conversation_messages"
        " (conversation_id, sender_id, sender_role, content)"
        " VALUES (?, ?, ?, ?)",
        (conversation_id, sender_id, "system", payload))


@app.route("/messages/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def client_conversation(conversation_id):
    """Conversation client."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not conv or conv["client_id"] != user["id"]:
            flash("Conversation introuvable.", "error")
            return redirect(url_for("client_messages"))
        if request.method == "POST":
            status = conv["status"]
            ready = False
            content = (request.form.get("content") or "").strip()
            if not content:
                flash("Le message ne peut pas etre vide.", "error")
            else:
                conn.execute(
                    "INSERT INTO conversation_messages"
                    " (conversation_id, sender_id, sender_role, content)"
                    " VALUES (?, ?, ?, ?)",
                    (conversation_id, user["id"], "client", content))

                if conv["status"] != "admin_active":
                    collected = _get_collected_from_messages(conn, conversation_id)
                    if not collected.get("location") and session.get("client_zone"):
                        collected["location"] = session["client_zone"]
                    analysis = ai_service.analyze_message(content, collected=collected)

                    fixpro_user = conn.execute(
                        "SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
                    ai_sender = fixpro_user["id"] if fixpro_user else user["id"]

                    conn.execute(
                        "INSERT INTO conversation_messages"
                        " (conversation_id, sender_id, sender_role, content)"
                        " VALUES (?, ?, ?, ?)",
                        (conversation_id, ai_sender, "ai", analysis["response"]))

                    try:
                        conn.execute(
                            "INSERT INTO lia_logs"
                            " (session_id, client_id, client_name, message, reply, status)"
                            " VALUES (?, ?, ?, ?, ?, ?)",
                            (f"conv-{conversation_id}", user["id"], user.get("full_name") or "Client",
                             content, analysis["response"], "open"))
                    except Exception as e:
                        logger.warning("Enregistrement conversation Lia impossible: %s", e)

                    extra_messages = []
                    status = "ai_active"
                    ready = analysis.get("ready", False)
                    if analysis["ready"]:
                        client_lat = _to_float(user.get("latitude")) or _to_float(session.get("client_lat"))
                        client_lon = _to_float(user.get("longitude")) or _to_float(session.get("client_lon"))
                        artisan = _select_best_technician(
                            conn, analysis["category"], analysis["collected_info"].get("location"),
                            client_lat=client_lat, client_lon=client_lon)
                        if artisan:
                            req_id = _create_intervention_from_chat(
                                conn, conversation_id, user["id"],
                                analysis, artisan, fixpro_user["id"] if fixpro_user else user["id"],
                                client_lat=client_lat, client_lon=client_lon)
                            ref_row = conn.execute(
                                "SELECT reference FROM requests WHERE id = ?", (req_id,)).fetchone()
                            ref = ref_row["reference"] if ref_row else f"FP-{datetime.now(timezone.utc).year}-{req_id:06d}"
                            extra_messages.append(
                                (conversation_id, ai_sender, "ai",
                                 f"C'est bon. J'ai cree l'intervention {ref}. "
                                 f"Le technicien {artisan['full_name']} ({artisan['profession']}) "
                                 "sera informe de votre demande. "
                                 "Si ce n'est pas la bonne categorie, repondez 'mauvaise categorie'."))
                            status = "converted_to_intervention"
                        else:
                            extra_messages.append(
                                (conversation_id, ai_sender, "ai",
                                 "J'ai bien enregistre votre demande. Je n'ai pas trouve de professionnel disponible immediatement. "
                                 "Notre equipe suivra votre dossier."))
                            status = "pending_assignment"

                    for m in extra_messages:
                        conn.execute(
                            "INSERT INTO conversation_messages"
                            " (conversation_id, sender_id, sender_role, content)"
                            " VALUES (?, ?, ?, ?)", m)

                    _save_collected_in_messages(conn, conversation_id, user["id"], analysis["collected_info"])

                    conn.execute(
                        "UPDATE conversations SET"
                        " updated_at = ?, status = ?, ai_category = ?,"
                        " urgency = ?, needs_human = ?, needs_technician = ?"
                        " WHERE id = ?",
                        (datetime.now(timezone.utc).isoformat(),
                         status, _domain_to_profession(analysis["category"]) or analysis["category"], analysis["urgency"],
                         1 if analysis["needs_human"] else 0,
                         1 if analysis["needs_technician"] else 0,
                         conversation_id))
                else:
                    conn.execute(
                        "UPDATE conversations SET updated_at = ? WHERE id = ?",
                        (datetime.now(timezone.utc).isoformat(), conversation_id))
                conn.commit()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    latest = conn.execute(
                        "SELECT m.*, u.full_name AS sender_name"
                        " FROM conversation_messages m"
                        " JOIN users u ON u.id = m.sender_id"
                        " WHERE m.conversation_id = ? AND m.sender_role != 'system'"
                        " AND m.id >= (SELECT COALESCE(MAX(id), 0) - 4 FROM conversation_messages WHERE conversation_id = ? AND sender_role != 'system')"
                        " ORDER BY m.id ASC",
                        (conversation_id, conversation_id)).fetchall()
                    return jsonify({
                        "ok": True,
                        "messages": [
                            {"id": m["id"], "content": m["content"], "sender_role": m["sender_role"], "created_at": m["created_at"], "sender_name": m["sender_name"]}
                            for m in latest
                        ],
                        "status": status,
                        "ready": ready,
                    })
        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name"
            " FROM conversation_messages m"
            " JOIN users u ON u.id = m.sender_id"
            " WHERE m.conversation_id = ? AND m.sender_role != 'system'"
            " ORDER BY m.created_at ASC",
            (conversation_id,)).fetchall()
        conn.execute(
            "UPDATE conversation_messages SET is_read = 1"
            " WHERE conversation_id = ? AND sender_role = 'admin'",
            (conversation_id,))
        conn.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                "ok": True,
                "conversation": dict(conv),
                "messages": [
                    {"id": m["id"], "content": m["content"], "sender_role": m["sender_role"],
                     "created_at": m["created_at"], "sender_name": m["sender_name"]}
                    for m in messages
                ]
            })
        artisan = None
        if conv.get("artisan_id"):
            artisan = conn.execute(
                "SELECT id, full_name, profession, photo_url FROM users WHERE id = ?",
                (conv["artisan_id"],)).fetchone()
    finally:
        conn.close()
    return render_template("client_conversation.html", conversation=conv, messages=messages, user=user, artisan=artisan)


def _get_or_create_guest_user(conn):
    """Cree ou recupere un utilisateur visiteur anonyme."""
    guest_id = session.get("guest_user_id")
    if guest_id:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (guest_id,)).fetchone()
        if user:
            session["user_id"] = user["id"]
            return user
    guest_phone = f"guest-{secrets.token_hex(8)}"
    user_id = _insert_id(
        conn,
        "INSERT INTO users (email, phone, password_hash, role, full_name, city)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (None, guest_phone, generate_password_hash(secrets.token_urlsafe(16)),
         "client", "Visiteur", "Conakry"))
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    session["guest_user_id"] = user_id
    session["user_id"] = user_id
    session.permanent = True
    return user


@app.route("/messages/artisan/<int:artisan_id>", methods=["GET"])
@limiter.limit("15 per hour")
def client_message_artisan(artisan_id):
    """Ouvre directement la messagerie FixPro sans inscription.

    Cette route cree un compte visiteur anonyme et une conversation : elle est
    donc limitee en debit pour empecher un robot de gonfler la table users.
    """
    conn = get_db_connection()
    try:
        artisan = conn.execute(
            "SELECT id, full_name, profession FROM users WHERE id = ? AND role IN ('artisan','technician')",
            (artisan_id,)).fetchone()
        if not artisan:
            flash("Technicien introuvable.", "error")
            return redirect(url_for("artisans_page"))

        user = get_current_user()
        if not user:
            user = _get_or_create_guest_user(conn)

        if user["role"] != "client":
            flash("Cet espace est reserve aux clients.", "error")
            return redirect(url_for("artisans_page"))

        conv = conn.execute(
            "SELECT id FROM conversations WHERE client_id = ? AND artisan_id = ?",
            (user["id"], artisan_id)).fetchone()
        if not conv:
            conv_id = _insert_id(
                conn,
                "INSERT INTO conversations (client_id, artisan_id, subject, status)"
                " VALUES (?, ?, ?, ?)",
                (user["id"], artisan_id, artisan["full_name"], 'ai_active'))
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), conv_id))
            conn.commit()
        else:
            conv_id = conv["id"]
    finally:
        conn.close()
    return redirect(url_for("client_conversation", conversation_id=conv_id))


@app.route("/admin/messages")
@login_required
@admin_required
def admin_messages():
    """Liste des conversations cote admin."""
    conn = get_db_connection()
    try:
        conversations = conn.execute(
            "SELECT c.id, c.subject, c.status, c.created_at, c.updated_at,"
            " u.full_name AS client_name,"
            " (SELECT content FROM conversation_messages WHERE conversation_id = c.id"
            " ORDER BY created_at DESC LIMIT 1) AS last_message,"
            " COALESCE(unread.n, 0) AS unread"
            " FROM conversations c"
            " JOIN users u ON u.id = c.client_id"
            " LEFT JOIN ("
            "   SELECT conversation_id, COUNT(*) AS n"
            "   FROM conversation_messages"
            "   WHERE sender_role = 'client' AND is_read = 0"
            "   GROUP BY conversation_id"
            " ) unread ON unread.conversation_id = c.id"
            " ORDER BY c.updated_at DESC").fetchall()
    finally:
        conn.close()
    return render_template("admin_messages.html", conversations=conversations, user=get_current_user())


@app.route("/admin/messages/<int:conversation_id>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_conversation(conversation_id):
    """Conversation admin avec reponse."""
    conn = get_db_connection()
    try:
        conv = conn.execute(
            "SELECT c.*, u.full_name AS client_name"
            " FROM conversations c"
            " JOIN users u ON u.id = c.client_id"
            " WHERE c.id = ?", (conversation_id,)).fetchone()
        if not conv:
            flash("Conversation introuvable.", "error")
            return redirect(url_for("admin_messages"))
        if request.method == "POST":
            action = request.form.get("action")
            user = get_current_user()
            if action == "takeover":
                conn.execute(
                    "UPDATE conversations SET status = 'admin_active', updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), conversation_id))
                conn.execute(
                    "INSERT INTO conversation_messages"
                    " (conversation_id, sender_id, sender_role, content) VALUES (?, ?, ?, ?)",
                    (conversation_id, user["id"], "admin", "Conversation prise en charge par un administrateur."))
                conn.commit()
                flash("Conversation prise en main.", "success")
            elif action == "create_intervention":
                artisan_id = request.form.get("artisan_id")
                artisan_id = int(artisan_id) if artisan_id else conv.get("artisan_id")
                client_id = conv["client_id"]
                client = conn.execute("SELECT * FROM users WHERE id = ?", (client_id,)).fetchone()
                ref = _generate_fixpro_reference(conn)
                title = (request.form.get("title") or conv.get("subject") or "Demande FixPro").strip()
                description = request.form.get("description") or "Demande issue de la conversation FixPro."
                category = request.form.get("category") or conv.get("ai_category") or "Autre"
                address = request.form.get("address") or (client["quartier"] if client else "Conakry")
                req_id = _insert_id(
                    conn,
                    "INSERT INTO requests (client_id, artisan_id, reference, title, description, category, address, status, quote_amount, budget, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, 0, datetime('now'), datetime('now'))",
                    (client_id, artisan_id, ref, title, description, category, address))
                conn.execute(
                    "UPDATE conversations SET status = 'converted_to_intervention', request_id = ?, updated_at = ? WHERE id = ?",
                    (req_id, datetime.now(timezone.utc).isoformat(), conversation_id))
                conn.commit()
                flash(f"Intervention {ref} creee.", "success")
            elif action == "close":
                conn.execute(
                    "UPDATE conversations SET status = 'closed', updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), conversation_id))
                conn.commit()
            else:
                content = (request.form.get("content") or "").strip()
                if not content:
                    flash("Le message ne peut pas etre vide.", "error")
                else:
                    conn.execute(
                        "INSERT INTO conversation_messages"
                        " (conversation_id, sender_id, sender_role, content) VALUES (?, ?, ?, ?)",
                        (conversation_id, user["id"], "admin", content))
                    conn.execute(
                        "UPDATE conversations SET updated_at = ? WHERE id = ?",
                        (datetime.now(timezone.utc).isoformat(), conversation_id))
                    try:
                        conn.execute(
                            "INSERT INTO notifications (user_id, title, body) VALUES (?, ?, ?)",
                            (conv["client_id"], "Nouvelle reponse FixPro", "L'administrateur a repondu a votre message."))
                    except Exception:
                        logger.warning("Notification admin non creee")
                    conn.commit()
                    flash("Reponse envoyee.", "success")
        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name"
            " FROM conversation_messages m"
            " JOIN users u ON u.id = m.sender_id"
            " WHERE m.conversation_id = ? AND m.sender_role != 'system'"
            " ORDER BY m.created_at ASC",
            (conversation_id,)).fetchall()
        conn.execute(
            "UPDATE conversation_messages SET is_read = 1"
            " WHERE conversation_id = ? AND sender_role = 'client'",
            (conversation_id,))
        conn.commit()
    finally:
        conn.close()
    return render_template("admin_conversation.html", conversation=conv, messages=messages, user=get_current_user())


@app.route("/missions/<int:request_id>")
@login_required
def artisan_mission(request_id):
    """Fiche detaillee d'une mission pour le technicien."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT r.*, u.full_name AS client_name, u.phone AS client_phone,"
            " u.email AS client_email FROM requests r"
            " JOIN users u ON u.id = r.client_id"
            " WHERE r.id = ?",
            (request_id,)).fetchone()
        if not req:
            flash("Mission introuvable.", "error")
            return redirect(url_for("artisan_dashboard"))

        if req["artisan_id"] != user["id"]:
            flash("Cette mission n'est pas accessible.", "error")
            return redirect(url_for("artisan_dashboard"))

        photos = conn.execute(
            "SELECT * FROM intervention_photos WHERE request_id = ? ORDER BY created_at DESC",
            (request_id,)).fetchall()

        history = conn.execute(
            "SELECT * FROM intervention_history WHERE request_id = ? ORDER BY created_at DESC",
            (request_id,)).fetchall()

        # Distance reelle depuis la derniere position GPS du technicien
        distance = None
        loc = conn.execute(
            "SELECT latitude, longitude, updated_at FROM technician_locations"
            " WHERE technician_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user["id"],)).fetchone()
        tech_pos = None
        if loc:
            try:
                updated = datetime.fromisoformat(str(loc["updated_at"]).replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - updated).total_seconds() <= 300:
                    tech_pos = (float(loc["latitude"]), float(loc["longitude"]))
            except (TypeError, ValueError):
                pass
        if (tech_pos
                and _is_valid_coordinate(req["latitude"], req["longitude"])):
            distance = _haversine(tech_pos[0], tech_pos[1],
                                  float(req["latitude"]), float(req["longitude"]))

    finally:
        conn.close()

    return render_template("artisan_mission.html", user=user, req=req,
                           photos=photos, history=history, distance=distance)


@app.route("/missions/<int:request_id>/action", methods=["POST"])
@login_required
def artisan_mission_action(request_id):
    """Actions principales d'une mission : statut, note, photo."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    action = (request.form.get("action") or "").strip().lower()
    if not action:
        flash("Aucune action specifiee.", "error")
        return redirect(url_for("artisan_mission", request_id=request_id))

    conn = get_db_connection()
    try:
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not req:
            flash("Mission introuvable.", "error")
            return redirect(url_for("artisan_dashboard"))

        if req["artisan_id"] and req["artisan_id"] != user["id"]:
            flash("Action non autorisee.", "error")
            return redirect(url_for("artisan_dashboard"))

        if action == "accept":
            if (req["status"] == MISSION_STATUS_ASSIGNED
                    and req["artisan_id"] == user["id"]
                    and can_transition_request(req["status"], MISSION_STATUS_ACCEPTED)):
                conn.execute(
                    "UPDATE requests SET status = ?, updated_at = ?"
                    " WHERE id = ? AND artisan_id = ? AND status = ?",
                    (MISSION_STATUS_ACCEPTED, now_iso(), request_id, user["id"], MISSION_STATUS_ASSIGNED))
                _log_intervention_history(
                    conn, request_id, MISSION_STATUS_ASSIGNED, MISSION_STATUS_ACCEPTED,
                    user["full_name"], "Le technicien a accepte la mission",
                    label="Mission acceptee")
                _notify_client(conn, request_id, "Mission acceptee",
                               "Votre technicien a accepte la mission.", "request_accepted")
                flash("Mission acceptee.", "success")
            else:
                flash("Cette mission ne peut plus etre acceptee.", "error")

        elif action == "reject":
            if (req["artisan_id"] == user["id"]
                    and can_transition_request(req["status"], MISSION_STATUS_REFUSED)):
                reason = (request.form.get("reason") or "").strip()
                conn.execute(
                    "UPDATE requests SET artisan_id = NULL, status = ?, updated_at = ?"
                    " WHERE id = ? AND artisan_id = ?",
                    (MISSION_STATUS_REFUSED, now_iso(), request_id, user["id"]))
                _log_intervention_history(
                    conn, request_id, MISSION_STATUS_ASSIGNED, MISSION_STATUS_REFUSED,
                    user["full_name"],
                    f"Refusee par le technicien. Raison : {reason or 'non precisee'}",
                    label="Mission refusee")

                # Recherche d'un autre technicien compatible
                new_artisan = _select_best_technician(
                    conn, req["category"], req["address"],
                    client_lat=req["latitude"], client_lon=req["longitude"],
                    exclude_artisan_id=user["id"])
                if new_artisan and new_artisan["id"] != user["id"]:
                    conn.execute(
                        "UPDATE requests SET artisan_id = ?, status = ?, updated_at = ? WHERE id = ?",
                        (new_artisan["id"], MISSION_STATUS_ASSIGNED, now_iso(), request_id))
                    _log_intervention_history(
                        conn, request_id, MISSION_STATUS_REFUSED, MISSION_STATUS_ASSIGNED,
                        "Systeme",
                        f"Nouveau technicien attribue : {new_artisan['full_name']} ({new_artisan.get('selection_reason', '')})",
                        label="Technicien attribue")
                    conn.execute(
                        "INSERT INTO notifications (user_id, title, body, type, data)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (new_artisan["id"], "Nouvelle mission FixPro",
                         f"{req['title']} - {req['address']} ({req['urgency']})",
                         "new_request", f"request_id:{request_id}"))
                else:
                    conn.execute(
                        "UPDATE requests SET status = ?, updated_at = ? WHERE id = ?",
                        (MISSION_STATUS_REASSIGNMENT_REQUIRED, now_iso(), request_id))
                    _log_intervention_history(
                        conn, request_id, MISSION_STATUS_REFUSED, MISSION_STATUS_REASSIGNMENT_REQUIRED,
                        "Systeme", "Aucun autre technicien disponible pour le moment",
                        label="Reattribution requise")
                    create_admin_notification(
                        conn, "Reattribution requise",
                        f"Mission {req['reference']} - {req['category']} : aucun remplacant disponible",
                        "reassignment_required",
                        f"request_id:{request_id}")
                _notify_client(conn, request_id, "Mission en reattribution",
                               "Votre demande est en cours de reattribution.", "request_reassigned")
                flash("Mission refusee. Elle sera reattribuee.", "success")
            else:
                flash("Cette mission ne peut plus etre refusee.", "error")

        elif action in ("en_route", "arrived", "in_progress", "completed"):
            new_status = _normalize_status(action) or action.upper()
            if can_transition_request(req["status"], new_status):
                conn.execute(
                    "UPDATE requests SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, now_iso(), request_id))
                label = _MISSION_STATUS_LABELS.get(new_status, new_status)
                _log_intervention_history(
                    conn, request_id, req["status"], new_status,
                    user["full_name"],
                    f"Statut mis a jour : {label}",
                    label=label)
                _notify_client(conn, request_id, "Mise a jour de la mission",
                               f"Statut de votre mission : {new_status.replace('_', ' ').capitalize()}",
                               f"request_{new_status.lower()}")
                flash("Statut mis a jour.", "success")
            else:
                flash("Changement de statut non autorise.", "error")

        elif action == "add_note":
            note = (request.form.get("note") or "").strip()
            if note:
                conn.execute(
                    "INSERT INTO intervention_history (request_id, status, actor, note, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (request_id, "Note technicien", user["full_name"], note, now_iso()))
                flash("Note enregistree.", "success")
            else:
                flash("La note est vide.", "error")

        elif action == "add_photo":
            photo_data = (request.form.get("photo_data") or "").strip()
            if photo_data:
                try:
                    photo_url = storage.get_storage().upload(f"mission_{request_id}", photo_data)
                    conn.execute(
                        "INSERT INTO intervention_photos (request_id, photo_url, created_at)"
                        " VALUES (?, ?, ?)",
                        (request_id, photo_url, now_iso()))
                    conn.execute(
                        "INSERT INTO intervention_history (request_id, status, actor, note, created_at)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (request_id, "Photo ajoutee", user["full_name"], "Photo ajoutee a la mission", now_iso()))
                    flash("Photo enregistree.", "success")
                except ValueError as exc:
                    flash(f"Erreur photo : {exc}", "error")
            else:
                flash("Aucune photo recue.", "error")

        else:
            flash("Action inconnue.", "error")

        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("artisan_mission", request_id=request_id))


def _notify_client(conn, request_id, title, body, kind):
    """Cree une notification pour le client d'une mission."""
    row = conn.execute(
        "SELECT client_id FROM requests WHERE id = ?", (request_id,)).fetchone()
    if row:
        conn.execute(
            "INSERT INTO notifications (user_id, title, body, type, data)"
            " VALUES (?, ?, ?, ?, ?)",
            (row["client_id"], title, body, kind, f"request_id:{request_id}"))


def _is_technician(user):
    """Verifie si l'utilisateur est un technicien (artisan ou technician)."""
    return bool(user and user.get("role") in ("artisan", "technician"))


_settings_loaded = False
def _ensure_settings_and_migrations():
    """Charge les settings et migrations une seule fois au premier appel."""
    global _settings_loaded
    if _settings_loaded:
        return
    _settings_loaded = True
    try:
        _load_settings()
        _migrate_db()
    except Exception as e:
        logger.warning("Parametres ou migrations indisponibles: %s", e)


app.before_request(_ensure_settings_and_migrations)


if __name__ == "__main__":
    logger.info("Démarrage de FixPro (environnement: %s)",
                app.config.get("FLASK_ENV"))
    app.run(host=app.config["HOST"], port=app.config["PORT"],
            debug=app.config["DEBUG"])
