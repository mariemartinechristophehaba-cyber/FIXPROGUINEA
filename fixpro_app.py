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
import hashlib
import json
import os
import math
import re
import requests
import tempfile
import urllib.parse
import urllib.request
import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from authlib.integrations.flask_client import OAuth
from abc import ABC, abstractmethod
from email_validator import EmailNotValidError, validate_email
from flask import (Flask, flash, g, get_flashed_messages, has_request_context,
                   jsonify, make_response, redirect, render_template, request,
                   session, url_for)
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
# 1 h : assez pour accelerer la navigation d'une meme session, assez court
# pour qu'une mise a jour de style/manifest se propage vite (pas de blocage
# sur un ancien fichier en cache).
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(hours=1)

# --- Donnees de DEMONSTRATION du tableau de bord admin (temporaire) ---------
# Tant que la base n'est pas peuplee, le tableau de bord affiche des chiffres
# fictifs coherents (voir _ADMIN_DASHBOARD_DEMO) pour ressembler a la maquette.
# Passer ADMIN_DASHBOARD_DEMO=0 (variable d'environnement Vercel) pour revenir
# immediatement aux vraies donnees de la base. Ces valeurs ne remplacent JAMAIS
# les vraies donnees cote API/back-office.
app.config["ADMIN_DASHBOARD_DEMO"] = (
    os.environ.get("ADMIN_DASHBOARD_DEMO", "1").strip().lower()
    not in ("0", "false", "no", "off", ""))

# Idem pour le tableau de bord CLIENT (voir _CLIENT_DASHBOARD_DEMO).
# CLIENT_DASHBOARD_DEMO=0 -> vraies donnees du client (demandes, paiements...).
app.config["CLIENT_DASHBOARD_DEMO"] = (
    os.environ.get("CLIENT_DASHBOARD_DEMO", "1").strip().lower()
    not in ("0", "false", "no", "off", ""))

# Idem pour la page admin "Utilisateurs" (voir _admin_users_demo_all).
# ADMIN_USERS_DEMO=0 -> vraie table users.
app.config["ADMIN_USERS_DEMO"] = (
    os.environ.get("ADMIN_USERS_DEMO", "1").strip().lower()
    not in ("0", "false", "no", "off", ""))

# Idem pour la page admin "Techniciens" (voir _admin_techs_demo_all).
app.config["ADMIN_TECHNICIANS_DEMO"] = (
    os.environ.get("ADMIN_TECHNICIANS_DEMO", "1").strip().lower()
    not in ("0", "false", "no", "off", ""))

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


@app.template_filter('day_label')
def _format_day_label(value):
    """Etiquette de separateur de jour : 'Aujourd'hui', 'Hier' ou 'JJ/MM/AAAA'."""
    if not value:
        return ''
    s = str(value)
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00')).date()
    except ValueError:
        try:
            d = datetime.strptime(s[:10], '%Y-%m-%d').date()
        except ValueError:
            return s[:10]
    today = datetime.now(timezone.utc).date()
    if d == today:
        return "Aujourd'hui"
    if (today - d).days == 1:
        return "Hier"
    return d.strftime('%d/%m/%Y')


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


@app.template_filter('date_month_fr')
def _format_date_month_fr(value):
    """Affiche une date au format '28 Avril 2024'."""
    if not value:
        return ''
    mois = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
            'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
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
    "conakry": (9.5350, -13.6800),
    "kaloum": (9.5077, -13.7114),
    "dixinn": (9.5700, -13.6778),
    "matam": (9.5310, -13.6520),
    "matam centre": (9.5310, -13.6520),
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

# Principales villes / prefectures de Guinee (hors Conakry) : la localisation
# n'est PAS limitee a Conakry. Coordonnees figees pour un fonctionnement hors
# ligne ; le geocodage Nominatim (borne a la Guinee) prend le relais pour le
# reste.
_GUINEA_CITIES = {
    "Kindia": (10.0560, -12.8650),
    "Coyah": (9.7080, -13.3830),
    "Dubreka": (9.7900, -13.5180),
    "Forecariah": (9.4310, -13.0880),
    "Boffa": (10.1830, -14.0330),
    "Boke": (10.9400, -14.3000),
    "Kamsar": (10.6500, -14.6100),
    "Fria": (10.3670, -13.5830),
    "Telimele": (10.9020, -13.0310),
    "Gaoual": (11.7500, -13.2000),
    "Koundara": (12.4830, -13.3000),
    "Labe": (11.3180, -12.2830),
    "Pita": (11.0830, -12.4000),
    "Dalaba": (10.6850, -12.2480),
    "Mamou": (10.3760, -12.0910),
    "Tougue": (11.4430, -11.6660),
    "Lelouma": (11.2190, -12.6340),
    "Mali": (12.0880, -12.3090),
    "Faranah": (10.0400, -10.7440),
    "Dabola": (10.7490, -11.1080),
    "Dinguiraye": (11.2980, -10.7260),
    "Kissidougou": (9.1850, -10.1000),
    "Kankan": (10.3850, -9.3060),
    "Kouroussa": (10.6480, -9.8870),
    "Siguiri": (11.4170, -9.1670),
    "Mandiana": (10.6330, -8.6830),
    "Kerouane": (9.2670, -9.0170),
    "Nzerekore": (7.7560, -8.8180),
    "Macenta": (8.5450, -9.4720),
    "Gueckedou": (8.5640, -10.1300),
    "Beyla": (8.6880, -8.6420),
    "Lola": (7.8000, -8.5170),
    "Yomou": (7.5690, -9.2590),
}

# Boite englobante approximative de la Republique de Guinee.
_GUINEA_BOUNDS = (7.0, 12.85, -15.25, -7.50)  # lat_min, lat_max, lon_min, lon_max


def _in_guinea(lat, lon):
    """Vrai si les coordonnees tombent en Guinee (rejette les homonymes a
    l'etranger renvoyes par le geocodeur)."""
    if not _is_valid_coordinate(lat, lon):
        return False
    la_min, la_max, lo_min, lo_max = _GUINEA_BOUNDS
    return la_min <= lat <= la_max and lo_min <= lon <= lo_max


# Boite englobante de l'agglomeration de Conakry : sert a savoir si un
# client geolocalise est "en ville" (tri strict par distance) ou non.
_CONAKRY_BOUNDS = (9.38, 9.80, -13.78, -13.46)


def _in_conakry(lat, lon):
    if not _is_valid_coordinate(lat, lon):
        return False
    la1, la2, lo1, lo2 = _CONAKRY_BOUNDS
    lat, lon = float(lat), float(lon)
    return la1 <= lat <= la2 and lo1 <= lon <= lo2


_ALL_PLACES_CACHE = None


def _all_places():
    """Table combinee {nom: (lat, lon)} : quartiers de Conakry + villes/
    prefectures de Guinee. Coordonnees verifiees."""
    global _ALL_PLACES_CACHE
    if _ALL_PLACES_CACHE is None:
        d = {}
        for name, xy in _GUINEA_CITIES.items():
            d[name] = xy
        for name, xy in _CONAKRY_QUARTIERS.items():
            d[name] = xy
        _ALL_PLACES_CACHE = d
    return _ALL_PLACES_CACHE


def _nearest_place(lat, lon, max_km=5.0):
    """Nom du quartier / de la ville connue le plus proche (repli hors ligne
    du geocodage inverse). Rien si aucun lieu connu dans le rayon."""
    if not _is_valid_coordinate(lat, lon):
        return None
    best, best_d = None, float("inf")
    for name, (zlat, zlon) in _all_places().items():
        d = _haversine(lat, lon, zlat, zlon)
        if d < best_d:
            best, best_d = name, d
    return best if (best and best_d <= max_km) else None


def _zone_coordinate(zone_name):
    """Coordonnees (lat, lon) d'un lieu connu par son nom. Tables verifiees
    (_all_places) d'abord, table historique _ARTISAN_GEOCODE en complement."""
    if not zone_name:
        return None
    key = str(zone_name).strip().lower()
    if not key:
        return None
    for name, xy in _all_places().items():
        if name.lower() == key:
            return xy
    return _ARTISAN_GEOCODE.get(key)


_NOMINATIM_CACHE = {}
_NOMINATIM_CACHE_MAX = 512
_NOMINATIM_HOST = "https://nominatim.openstreetmap.org/"
_NOMINATIM_MAX_BYTES = 262144  # 256 Ko : une reponse legitime est bien plus petite


def _nominatim_request(url):
    """Appelle Nominatim (host verrouille), lecture bornee, resultats caches.

    Ne suit aucune redirection hors du domaine, ne lit pas plus de 256 Ko,
    et n'echoue jamais bruyamment : renvoie None des qu'un doute existe.
    """
    if not isinstance(url, str) or not url.startswith(_NOMINATIM_HOST):
        return None
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
            if getattr(resp, "status", 200) != 200:
                return None
            if not resp.geturl().startswith(_NOMINATIM_HOST):
                return None
            raw = resp.read(_NOMINATIM_MAX_BYTES + 1)
        if len(raw) > _NOMINATIM_MAX_BYTES:
            logger.warning("Reponse Nominatim trop volumineuse, ignoree.")
            return None
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        logger.warning("Erreur Nominatim : %s", e)
        return None

    if len(_NOMINATIM_CACHE) >= _NOMINATIM_CACHE_MAX:
        _NOMINATIM_CACHE.clear()
    _NOMINATIM_CACHE[url] = data
    return data


def _same_origin_ok():
    """Endpoints exemptes de CSRF : on tolere l'absence d'en-tete Origin
    (navigateur mobile / proxy de traduction) mais on rejette un Origin
    explicitement etranger."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    try:
        host = urllib.parse.urlparse(origin).netloc.lower()
    except Exception:
        return False
    return bool(host) and host == (request.host or "").lower()


def _extract_place_name(data):
    """Libelle precis d'une reponse Nominatim : 'Quartier, Ville' quand
    possible, sinon 'Village, Prefecture', sinon la region."""
    if not data or not isinstance(data, dict):
        return None
    addr = data.get("address") or {}
    local = (addr.get("neighbourhood") or addr.get("suburb") or addr.get("quarter")
             or addr.get("city_district") or addr.get("residential")
             or addr.get("village") or addr.get("hamlet"))
    city = (addr.get("city") or addr.get("town") or addr.get("municipality")
            or addr.get("county"))
    region = addr.get("state") or addr.get("region") or addr.get("state_district")
    parts = []
    if local:
        parts.append(local)
    if city and city != local:
        parts.append(city)
    if not parts and region:
        parts.append(region)
    if parts:
        return ", ".join(parts[:2])
    dn = data.get("display_name")
    if dn:
        bits = [b.strip() for b in dn.split(",") if b.strip()]
        bits = [b for b in bits if b.lower() not in ("guinee", "guinea", "guinee-conakry")]
        if bits:
            return ", ".join(bits[:2])
    return None


def _reverse_geocode(lat, lon):
    """Retourne le nom d'un lieu a partir de coordonnees GPS."""
    if not _is_valid_coordinate(lat, lon):
        return None
    params = urllib.parse.urlencode({
        "lat": round(float(lat), 3),
        "lon": round(float(lon), 3),
        "format": "json",
        "addressdetails": 1,
        "accept-language": "fr",
        "zoom": 16,
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


_static_version_cache = {}


def _static_asset_version(rel_path):
    """Empreinte courte du contenu d'un fichier statique, pour le cache-busting
    (?v=...). Mise en cache par processus : recalculee a chaque deploiement."""
    if rel_path in _static_version_cache:
        return _static_version_cache[rel_path]
    tag = "1"
    try:
        with open(os.path.join(app.static_folder, rel_path), "rb") as fh:
            tag = hashlib.md5(fh.read()).hexdigest()[:10]
    except OSError:
        pass
    _static_version_cache[rel_path] = tag
    return tag


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
    for raw in (quartier, city):
        hit = _zone_coordinate(raw)
        if hit:
            return hit
    return None, None


def _is_valid_coordinate(lat, lon):
    """Coordonnees exploitables : finies, dans les bornes terrestres, et pas
    le (0, 0) par defaut. Rejette NaN / Infini / hors [-90,90]x[-180,180]."""
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return not (abs(lat) < 0.01 and abs(lon) < 0.01)


def _open_raw_connection():
    return db.connect(
        database_url=app.config.get("DATABASE_URL", ""),
        sqlite_path=app.config.get("SQLITE_PATH", "fixpro.db"),
    )


class _RequestConnection:
    """Proxy renvoye pendant une requete HTTP.

    Toutes les operations sont deleguees a une unique connexion reelle
    partagee sur toute la requete : ouvrir une connexion PostgreSQL coute
    ~50-200 ms (handshake TLS), et l'ancien code en ouvrait 2 a 4 par page.
    `close()` est neutralise ; la vraie fermeture a lieu dans
    `teardown_request`. `commit()` / `rollback()` restent effectifs, donc le
    comportement transactionnel du code appelant est inchange.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw):
        object.__setattr__(self, "_raw", raw)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_raw"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_raw"), name, value)

    def close(self):
        # Fermee une seule fois, en fin de requete (teardown_request).
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        raw = object.__getattribute__(self, "_raw")
        if exc_type is None:
            raw.commit()
        else:
            raw.rollback()
        return False


def get_db_connection():
    """Connexion vers la base configuree pour cet environnement.

    Dans une requete HTTP : une seule connexion reelle est ouverte puis
    reutilisee (voir `_RequestConnection`). Hors requete (scripts, tests,
    taches) : une connexion dediee, a fermer par l'appelant.
    """
    if not has_request_context():
        return _open_raw_connection()
    proxy = getattr(g, "_db_proxy", None)
    if proxy is None:
        raw = _open_raw_connection()
        g._db_raw = raw
        proxy = _RequestConnection(raw)
        g._db_proxy = proxy
    return proxy


@app.teardown_request
def _close_request_connection(exc):
    """Ferme l'unique connexion de la requete (rollback de tout residu)."""
    raw = g.pop("_db_raw", None)
    g.pop("_db_proxy", None)
    if raw is None:
        return
    try:
        # Le code applicatif valide explicitement chaque ecriture ; ici on ne
        # fait que jeter ce qui n'a pas ete valide, comme le faisait la
        # fermeture d'une connexion par appel.
        raw.rollback()
    except Exception:
        pass
    try:
        raw.close()
    except Exception:
        pass


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
    "unitrade": "Unitrade",
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

    # L'essai de 14 jours demarre des que le technicien est approuve : on
    # materialise ceux qui n'ont pas encore de ligne, puis on fait expirer
    # les essais arrives a terme. Ainsi la recherche reflete l'etat reel.
    _ensure_trials_for_verified(conn)
    _expire_due_trials(conn)
    try:
        _expire_due_subscriptions(conn)
    except Exception:
        pass

    sql = """
        SELECT u.id, u.full_name, u.profession, u.city, u.quartier,
               u.latitude, u.longitude,
               u.zone_intervention, u.mobility, u.years_experience, u.is_verified,
               COALESCE(rating_data.avg_rating, 0) AS avg_rating,
               COALESCE(rating_data.review_count, 0) AS review_count,
               COALESCE(completed_count.c, 0) AS completed_count,
               sub_plan.plan_code AS plan_code,
               trial_state.in_trial AS in_trial
        FROM users u
        LEFT JOIN (
            SELECT artisan_id, AVG(rating) AS avg_rating, COUNT(*) AS review_count
            FROM reviews GROUP BY artisan_id
        ) rating_data ON rating_data.artisan_id = u.id
        LEFT JOIN (
            SELECT artisan_id, COUNT(*) AS c
            FROM requests WHERE LOWER(status) = 'completed' GROUP BY artisan_id
        ) completed_count ON completed_count.artisan_id = u.id
        LEFT JOIN (
            SELECT s.technician_id, p.code AS plan_code
            FROM technician_subscriptions s
            JOIN subscription_plans p ON p.id = s.plan_id
            WHERE s.status = 'ACTIVE'
              AND (s.end_date IS NULL OR s.end_date > CURRENT_TIMESTAMP)
        ) sub_plan ON sub_plan.technician_id = u.id
        LEFT JOIN (
            SELECT technician_id, 1 AS in_trial
            FROM technician_subscriptions
            WHERE status = 'TRIAL'
              AND (end_date IS NULL OR end_date > CURRENT_TIMESTAMP)
        ) trial_state ON trial_state.technician_id = u.id
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
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    for a in rows:
        if a["id"] in busy_ids:
            continue
        tech_pos = locations.get(a["id"])
        if require_gps and not tech_pos:
            continue

        # ELIGIBILITE (regle produit) : un technicien n'est propose aux
        # nouvelles demandes que s'il a un abonnement ACTIVE **ou** un essai
        # de 14 jours en cours. Essai termine sans abonnement / abonnement
        # expire -> ecarte (le compte et l'historique restent intacts).
        if not (a.get("plan_code") or a.get("in_trial")):
            continue

        # Quota mensuel du plan ACTIF (regle produit : PRO = 30 / mois,
        # PREMIUM = illimite). Un technicien Pro ayant deja recu 30 demandes
        # ce mois-ci est ecarte de la selection ; c'est un critere EN PLUS
        # des autres (dispo, proximite, note...), il n'en remplace aucun.
        # `plan_code` ne vaut que pour un abonnement ACTIVE non expire
        # (cf. LEFT JOIN sub_plan) -> aucun impact sur les non-abonnes.
        plan_limit = _PLAN_MONTHLY_REQUEST_LIMIT.get(a.get("plan_code"))
        if plan_limit is not None:
            urow = conn.execute(
                "SELECT COUNT(*) AS n FROM requests"
                " WHERE artisan_id = ? AND substr(created_at, 1, 7) = ?",
                (a["id"], current_month)).fetchone()
            if (urow["n"] if urow else 0) >= plan_limit:
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

        # Bonus de visibilite - controle et raisonnable : il n'ecrase ni la
        # note ni la proximite, il departage a criteres comparables. N'exclut
        # personne. Priorite : Premium > Pro > essai decouverte.
        plan_code = a.get("plan_code")
        if "priority_visibility" in _PLAN_ENTITLEMENTS.get(plan_code, ()):
            score += 35          # Premium actif
        elif "search_visibility" in _PLAN_ENTITLEMENTS.get(plan_code, ()):
            score += 12          # Pro actif
        elif a.get("in_trial"):
            score += 18          # periode decouverte : coup de pouce temporaire

        artisan = dict(a)
        artisan["distance_km"] = round(distance, 1) if distance is not None else None
        artisan["selection_score"] = score
        artisan["gps_source"] = "technician_locations" if tech_pos else "profile"
        artisan["subscription_badge"] = get_subscription_badge(a.get("plan_code"))
        artisan["is_featured"] = "featured_profile" in _PLAN_ENTITLEMENTS.get(a.get("plan_code"), ())
        artisan["is_trial"] = bool(a.get("in_trial")) and not a.get("plan_code")
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

    def verify(self, reference, payload=None):
        """Interroge le fournisseur sur l'etat reel d'une transaction.

        A implementer par chaque fournisseur reel d'apres sa doc officielle.
        Par defaut : ne se prononce pas (statut 'pending')."""
        return {"ok": True, "status": "pending"}

    def handle_webhook(self, payload, headers=None):
        """Traite une notification signee du fournisseur.

        A implementer par chaque fournisseur reel : (1) verifier
        l'authenticite, (2) la reference, (3) le montant, (4) la devise,
        (5) l'existence de la tentative, (6) qu'elle n'est pas finalisee,
        puis renvoyer l'issue normalisee. Non disponible sans API."""
        raise NotImplementedError


class _UnconfiguredProvider(PaymentProvider):
    """Base commune des fournisseurs reels PAS ENCORE branches.

    Tant que les identifiants et la documentation officielle de l'API ne
    sont pas disponibles, ces fournisseurs :
      - acceptent d'ouvrir une TENTATIVE (statut 'pending' / NOT_CONFIGURED) ;
      - ne pretendent JAMAIS avoir encaisse un paiement (jamais 'success').
    La confirmation ne peut venir que d'un webhook signe ou d'un admin.
    Chaque fournisseur reel devra implementer process(), verify() et
    handle_webhook() d'apres sa documentation officielle.
    """

    code = "generic"
    label = "Fournisseur"

    def _configured(self):
        return bool(app.config.get("PAYMENT_%s_ENABLED" % self.code.upper()))

    def process(self, amount, method, reference, metadata):
        return {
            "ok": True,
            "status": "pending",
            "configured": self._configured(),
            "provider": self.code,
            "provider_reference": None,
            "message": ("%s : API non encore configuree, tentative en attente "
                        "de confirmation reelle." % self.label),
        }

    def verify(self, reference, payload=None):
        # Aucune API : on ne peut rien affirmer -> on reste 'pending'.
        return {"ok": True, "status": "pending", "configured": self._configured()}

    def handle_webhook(self, payload, headers=None):
        # A implementer par chaque fournisseur reel selon sa doc officielle.
        raise NotImplementedError(
            "%s.handle_webhook non implemente (API non branchee)" % type(self).__name__)

    def confirm(self, reference, payload):
        return {"ok": False, "status": "pending", "configured": self._configured()}

    def refund(self, reference, amount):
        return {"ok": False, "status": "not_configured", "provider": self.code}


class OrangeMoneyProvider(_UnconfiguredProvider):
    code = "orange_money"
    label = "Orange Money"


class MTNMobileMoneyProvider(_UnconfiguredProvider):
    code = "mtn_mobile_money"
    label = "MTN Mobile Money"


class UnitradeProvider(_UnconfiguredProvider):
    code = "unitrade"
    label = "Unitrade"


class CardProvider(_UnconfiguredProvider):
    code = "card"
    label = "Carte bancaire"


class MockPaymentProvider(PaymentProvider):
    """Fournisseur factice reserve AUX TESTS AUTOMATISES uniquement.

    Il n'est jamais instancie en production : get_payment_provider() ne le
    retourne que si la config declare explicitement l'environnement de test
    (FLASK_ENV='testing' ou PAYMENT_PROVIDER='mock'). Meme dans ce cas il
    renvoie 'pending' par defaut ; la confirmation passe par le webhook.
    """

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


_REAL_PAYMENT_PROVIDERS = {
    "orange_money": OrangeMoneyProvider,
    "mtn_mobile_money": MTNMobileMoneyProvider,
    "unitrade": UnitradeProvider,
    "card": CardProvider,
}


def _use_mock_payment_provider():
    """Le mock n'est autorise QUE si la config le declare explicitement."""
    return (app.config.get("TESTING") is True
            or app.config.get("FLASK_ENV") == "testing"
            or app.config.get("PAYMENT_PROVIDER") == "mock")


def get_payment_provider(payment_method=None):
    """Retourne le fournisseur de paiement pour un moyen donne.

    En production, chaque moyen route vers sa propre implementation
    (Orange Money / MTN / Unitrade / carte). Aucune de ces implementations
    n'encaisse reellement tant que l'API officielle n'est pas branchee :
    elles restent en 'pending' / NOT_CONFIGURED. Le mock n'est jamais
    retourne sauf en environnement de test declare.
    """
    if _use_mock_payment_provider():
        return MockPaymentProvider()
    cls = _REAL_PAYMENT_PROVIDERS.get(payment_method)
    if cls is not None:
        return cls()
    return _UnconfiguredProvider()


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
        logger.error("Notification non creee (badge bloque a 0 ?) : user_id=%s - %s", user_id, exc)
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

    messages_unread = 0
    if connected and connected.get("role") != "admin":
        _my_role = "artisan" if connected.get("role") in ("artisan", "technician") else "client"
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM conversation_messages m"
                " JOIN conversations c ON c.id = m.conversation_id"
                " WHERE (c.client_id = ? OR c.artisan_id = ?)"
                " AND m.is_read = 0 AND m.sender_role <> ? AND m.sender_role <> 'system'",
                (connected["id"], connected["id"], _my_role)).fetchone()
            messages_unread = (row["n"] if row else 0) or 0
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    notif_unread = 0
    if connected and connected.get("role") != "admin":
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                (connected["id"],)).fetchone()
            notif_unread = (row["n"] if row else 0) or 0
        except Exception:
            conn.rollback()
        finally:
            conn.close()

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

    return {"nav_user": connected, "admin_stats": stats,
            "messages_unread": messages_unread, "notif_unread": notif_unread}


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


# ---------------------------------------------------------------------------
# Pages publiques
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    _u = get_current_user()
    if _u and _is_technician(_u):
        return redirect(url_for("artisan_dashboard"))
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

        client_lat = _to_float(user.get("latitude")) if user else None
        client_lon = _to_float(user.get("longitude")) if user else None
        if client_lat is None or client_lon is None:
            client_lat = _to_float(session.get("client_lat"))
            client_lon = _to_float(session.get("client_lon"))
        client_in_conakry = _in_conakry(client_lat, client_lon)
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
        params.append(str(zone)[:80])
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


# ===========================================================================
# LOCALISATION CLIENT - audit securite 2026-09-03.
# Regles (couvertes par tests/test_app.py, classe GeolocationTests) :
#  - toute coordonnee est validee : finie, dans [-90,90]x[-180,180], en Guinee
#    (_is_valid_coordinate + _in_guinea) ; NaN/Infini/hors-bornes -> 400.
#  - le libelle manuel est borne (<=80) et filtre (_ZONE_NAME_RE).
#  - endpoints exemptes de CSRF : _same_origin_ok() rejette un Origin etranger.
#  - _nominatim_request : host verrouille, lecture <=256 Ko, jamais d'exception.
#  - le lieu vient du geocodage inverse (tous quartiers/prefectures de Guinee) ;
#    les tables locales ne servent que de repli hors ligne.
# Ne pas relacher ces controles sans mettre a jour les tests.
# ===========================================================================
@app.route("/api/location", methods=["POST"])
@limiter.limit("30 per hour")
def set_location():
    """Enregistre la position GPS du client en session (et dans son profil)."""
    if not _same_origin_ok():
        return jsonify({"ok": False, "error": "Origine refusee"}), 403
    try:
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "Payload invalide"}), 400
        lat = _to_float(data.get("lat"), None)
        lon = _to_float(data.get("lon"), None)
        if not _is_valid_coordinate(lat, lon) or not _in_guinea(lat, lon):
            return jsonify({"ok": False, "error": "Coordonnees hors zone de service"}), 400
        lat, lon = round(float(lat), 6), round(float(lon), 6)
        accuracy = max(0.0, min(_to_float(data.get("accuracy"), 0.0), 100000.0))
        session["client_lat"] = lat
        session["client_lon"] = lon
        session["client_loc_accuracy"] = accuracy
        session["client_loc_at"] = _ts()
        session["loc_permission"] = "granted"
        session.pop("loc_gate_dismissed", None)
        # Le lieu exact vient du geocodage inverse (couvre tous les
        # quartiers / prefectures / regions de Guinee). Les tables locales
        # ne servent que de repli si le reseau echoue.
        zone = _reverse_geocode(lat, lon)
        if not zone:
            zone = (_nearest_place(lat, lon, max_km=4.0)
                    or _nearest_place(lat, lon, max_km=45.0)
                    or "Ma position")
        session["client_zone"] = zone
        _persist_client_location(lat, lon, zone if zone != "Ma position" else None)
        return jsonify({"ok": True, "zone": zone, "lat": lat, "lon": lon, "accuracy": accuracy})
    except Exception as e:
        logger.warning("Erreur enregistrement position: %s", e)
        return jsonify({"ok": False, "error": "Position non enregistree."}), 500


_ZONE_NAME_RE = re.compile(r"\A[\w .,'\-]{2,60}\Z", re.UNICODE)


@app.route("/api/location/zone", methods=["POST"])
@limiter.limit("30 per hour")
def set_location_zone():
    """Enregistre une localisation manuelle saisie par l'utilisateur."""
    if not _same_origin_ok():
        return jsonify({"ok": False, "error": "Origine refusee"}), 403
    try:
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "Payload invalide"}), 400
        raw_zone = str(data.get("zone") or "")
        zone = " ".join(raw_zone.split())
        if len(raw_zone) > 80 or not zone or not _ZONE_NAME_RE.match(zone):
            return jsonify({"ok": False, "error": "Zone invalide"}), 400
        session["loc_permission"] = "manual"

        # 1. Quartier de Conakry ou ville de Guinee de la liste FixPro :
        #    coordonnees figees, aucun geocodage externe (sinon "Madina"
        #    -> Medine, Arabie Saoudite).
        coords = None
        for table in (_CONAKRY_QUARTIERS, _GUINEA_CITIES):
            for name, xy in table.items():
                if name.lower() == zone.lower():
                    coords, zone = xy, name
                    break
            if coords:
                break
        # 2. Zone connue de _ARTISAN_GEOCODE.
        if not coords:
            coords = _zone_coordinate(zone)
        # 3. Dernier recours : geocodage borne a la Guinee (tout le pays,
        #    pas seulement Conakry ; rejette les homonymes a l'etranger).
        if not coords:
            lat, lon, place = _geocode_query(zone + ", Guinee")
            if _in_guinea(lat, lon):
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
@limiter.limit("60 per hour")
def set_location_denied():
    """Marque la permission GPS comme refusee."""
    if not _same_origin_ok():
        return jsonify({"ok": False}), 403
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
    if (len(nxt) > 512 or not nxt.startswith("/")
            or nxt.startswith(("//", "/\\"))
            or not re.match(r"\A/[A-Za-z0-9/_.\-?=&%]*\Z", nxt)):
        nxt = url_for("artisans_page")
    return render_template("location_gate.html",
                           quartiers=_CONAKRY_QUARTIERS,
                           cities=sorted(_GUINEA_CITIES), next=nxt)


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
        client_in_conakry = _in_conakry(client_lat, client_lon)
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


# users.profession est un champ libre : selon le formulaire d'inscription utilise,
# le meme metier peut y etre enregistre sous plusieurs orthographes/accents/casse
# (ex. "Plombier", "Plomberie", "plombier"). Le gabarit categories.html affiche un
# jeu fixe de 8 categories : on y associe toutes les variantes reellement vues en
# base pour que le compte de techniciens ne soit pas bloque a 0. Meme principe que
# le regroupement "canonical" utilise dans index()/home().
_CATEGORY_PROFESSION_ALIASES = {
    "Électricité": ("électricien", "electricien", "electricite", "électricité"),
    "Plomberie": ("plombier", "plomberie"),
    "Climatisation": ("climatisation", "climatiseur", "clim"),
    "Réfrigération": ("frigoriste", "réfrigération", "refrigeration", "froid"),
    "Menuiserie": ("menuisier", "menuiserie"),
    "Peinture": ("peintre", "peinture"),
    "Maçonnerie": ("maçon", "maçonnerie", "macon", "maconnerie"),
    "Nettoyage": ("nettoyage", "menage", "ménage"),
}


@app.route("/categories")
def categories():
    conn = get_db_connection()
    try:
        categories = conn.execute(
            "SELECT name, diagnostic_price FROM service_categories ORDER BY name").fetchall()
        profession_counts = {}
        for row in conn.execute(
                "SELECT profession, COUNT(*) AS n FROM users"
                " WHERE profession IS NOT NULL AND profession != ''"
                " GROUP BY profession").fetchall():
            key = (row["profession"] or "").strip().lower()
            profession_counts[key] = profession_counts.get(key, 0) + row["n"]

        counts = {
            label: sum(profession_counts.get(alias, 0) for alias in aliases)
            for label, aliases in _CATEGORY_PROFESSION_ALIASES.items()
        }
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


def _parse_base64_file(data_uri, max_bytes=3 * 1024 * 1024):
    """Extrait le mime, le nom et le contenu binaire depuis un data URI base64.

    Valide le type MIME, la taille et les magic bytes du fichier decode.
    ``max_bytes`` borne la taille du contenu base64 (par defaut ~2,25 Mo
    binaire ; ~5 Mo binaire pour les documents d'inscription technicien).
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
        if len(encoded) > max_bytes:
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
    if role in ("artisan", "technician", "technicien", "pro", "professionnel"):
        return redirect(url_for("devenir_technicien"))
    if role != "client":
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

    return render_template("choose_account.html")


# Champs obligatoires de l'etape 1 (profil) du wizard d'inscription technicien.
_TECH_SIGNUP_STEP1_FIELDS = ("first_name", "last_name", "phone", "email", "password")

# Etape 2 : metier principal (slug -> libelle). Un technicien = UN SEUL
# metier principal (enregistre plus tard dans users.profession, une seule
# valeur texte -- aucune migration necessaire).
_TECH_TRADES = [
    ("plomberie", "Plomberie"),
    ("electricite", "Électricité"),
    ("climatisation", "Climatisation / Réfrigération"),
    ("peinture", "Peinture"),
    ("menuiserie", "Menuiserie"),
    ("maconnerie", "Maçonnerie"),
    ("depannage", "Dépannage général"),
    ("nettoyage", "Nettoyage"),
]
_TECH_TRADE_SLUGS = {s for s, _ in _TECH_TRADES}
# Libelle "profession" (users.profession) pour chaque metier principal.
_TECH_TRADE_PROFESSION = {
    "plomberie": "Plombier", "electricite": "Électricien",
    "climatisation": "Frigoriste", "peinture": "Peintre",
    "menuiserie": "Menuisier", "maconnerie": "Maçon",
    "depannage": "Dépannage général", "nettoyage": "Nettoyage",
}


def _signup_doc_dir():
    """Dossier temporaire ou sont stockees les pieces jointes du wizard
    d'inscription technicien, en attendant la creation du compte (etape 5)."""
    d = os.path.join(tempfile.gettempdir(), "fixpro_signup_docs")
    os.makedirs(d, exist_ok=True)
    return d


def _signup_doc_stash(token, kind, data_uri):
    """Ecrit une piece jointe (data-URI) dans un fichier temporaire."""
    if not data_uri:
        return
    path = os.path.join(_signup_doc_dir(), f"{token}_{kind}")
    with open(path, "w", encoding="ascii") as fh:
        fh.write(data_uri)


def _signup_doc_pop(token, kind):
    """Relit puis supprime une piece jointe temporaire. None si absente."""
    path = os.path.join(_signup_doc_dir(), f"{token}_{kind}")
    try:
        with open(path, "r", encoding="ascii") as fh:
            data = fh.read()
    except OSError:
        return None
    try:
        os.remove(path)
    except OSError:
        pass
    return data or None


@app.route("/devenir-technicien", methods=["GET", "POST"])
@limiter.limit("15 per hour", methods=["POST"])
def devenir_technicien():
    """Wizard d'inscription technicien -- etape 1 sur 5 : le profil
    (identite, telephone, e-mail, mot de passe). Public. Au POST valide,
    memorise l'etape 1 en session et passe a l'etape 2 (Services)."""
    data = dict(session.get("tech_signup", {}))
    errors = {}

    if request.method == "POST":
        data = {
            "first_name": request.form.get("first_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "password": request.form.get("password", ""),
        }
        for f in ("first_name", "last_name", "phone", "email"):
            if not data[f]:
                errors[f] = "Ce champ est obligatoire."
        if data["email"] and "@" not in data["email"]:
            errors["email"] = "Adresse e-mail invalide."
        if not data["password"]:
            errors["password"] = "Ce champ est obligatoire."
        else:
            pwd_error = _validate_password_strength(data["password"])
            if pwd_error:
                errors["password"] = pwd_error

        if not errors:
            session["tech_signup"] = {k: data[k] for k in
                                      ("first_name", "last_name", "phone", "email")}
            # Le mot de passe est stocke HACHE (jamais en clair) pour creer
            # le compte a l'etape 5 sans le redemander.
            session["tech_signup"]["pwd_hash"] = generate_password_hash(data["password"])
            session.modified = True
            return redirect(url_for("technician_signup_trade"))

    return render_template(
        "technician_signup.html",
        nav_user=get_current_user(),
        data=data,
        errors=errors,
    )


@app.route("/devenir-technicien/services", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def technician_signup_trade():
    """Wizard d'inscription technicien -- etape 2 sur 5 : le METIER PRINCIPAL
    (selection unique, exclusive). Un technicien = un seul metier. L'etape 1
    doit avoir ete remplie. Au POST valide, memorise le metier et passe a
    l'etape 3 (Documents)."""
    if not session.get("tech_signup"):
        return redirect(url_for("devenir_technicien"))

    selected = session.get("tech_signup_trade")
    error = None

    if request.method == "POST":
        chosen = request.form.get("trade", "")
        if chosen in _TECH_TRADE_SLUGS:
            selected = chosen
        else:
            selected = None
        if not selected:
            error = "Sélectionnez votre métier principal."
        else:
            session["tech_signup_trade"] = selected
            session.modified = True
            return redirect(url_for("technician_signup_documents"))

    return render_template(
        "technician_signup_services.html",
        nav_user=get_current_user(),
        trades=_TECH_TRADES,
        selected=selected,
        error=error,
    )


@app.route("/devenir-technicien/documents", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def technician_signup_documents():
    """Wizard d'inscription technicien -- etape 3 sur 5 : les documents
    (piece d'identite obligatoire, diplome facultatif). Les etapes 1 et 2
    doivent avoir ete remplies. Les fichiers sont envoyes en data-URI
    base64 et valides (type + taille + magic bytes) via _parse_base64_file.
    Les etapes 4 et 5 (Localisation, Finalisation) sont en cours de
    conception : "Continuer" memorise l'etat des documents puis affiche un
    message d'attente."""
    if not session.get("tech_signup"):
        return redirect(url_for("devenir_technicien"))
    if not session.get("tech_signup_trade"):
        return redirect(url_for("technician_signup_trade"))

    docs = dict(session.get("tech_signup_docs", {}))
    errors = {}

    if request.method == "POST":
        identity = request.form.get("identity_doc", "")
        diploma = request.form.get("diploma_doc", "")

        _MAX_DOC = 7 * 1024 * 1024  # base64 -> ~5 Mo binaire
        # Phase de test : les documents sont optionnels. On valide seulement
        # le format quand un fichier est effectivement fourni.
        ext = None
        if identity:
            _, ext, _ = _parse_base64_file(identity, _MAX_DOC)
            if not ext:
                errors["identity"] = "Fichier invalide (JPG, PNG ou PDF, 5 Mo max)."

        dip_ext = None
        if diploma:
            _, dip_ext, _ = _parse_base64_file(diploma, _MAX_DOC)
            if not dip_ext:
                errors["diploma"] = "Fichier invalide (JPG, PNG ou PDF, 5 Mo max)."

        if not errors:
            # Le contenu des fichiers est mis de cote dans un fichier temp
            # (trop volumineux pour le cookie de session) ; ils seront
            # persistes en base a l'etape 5 (creation du compte).
            token = session.get("tech_signup_doc_token") or secrets.token_hex(12)
            if ext:
                _signup_doc_stash(token, "identity", identity)
            if dip_ext:
                _signup_doc_stash(token, "diploma", diploma)
            session["tech_signup_doc_token"] = token
            session["tech_signup_docs"] = {"identity": ext, "diploma": dip_ext,
                                           "done": True}
            session.modified = True
            return redirect(url_for("technician_signup_location"))

    return render_template(
        "technician_signup_documents.html",
        nav_user=get_current_user(),
        docs=docs,
        errors=errors,
    )


@app.route("/devenir-technicien/localisation", methods=["GET", "POST"])
@limiter.limit("30 per hour", methods=["POST"])
def technician_signup_location():
    """Wizard d'inscription technicien -- etape 4 sur 5 : la zone
    d'intervention. La position vient de la geolocalisation reelle du
    navigateur (navigator.geolocation cote client). Le serveur valide les
    coordonnees et fait le geocodage inverse (Nominatim). Elle sera
    enregistree dans users.latitude / users.longitude a la finalisation
    (aucune migration -- colonnes deja presentes). Au POST valide, passe a
    l'etape 5 (Finalisation)."""
    if not session.get("tech_signup"):
        return redirect(url_for("devenir_technicien"))
    if not session.get("tech_signup_trade"):
        return redirect(url_for("technician_signup_trade"))
    if not session.get("tech_signup_docs"):
        return redirect(url_for("technician_signup_documents"))

    loc = dict(session.get("tech_signup_location", {}))
    error = None

    if request.method == "POST":
        lat = request.form.get("latitude", "")
        lon = request.form.get("longitude", "")
        if not lat and not lon:
            # Phase de test : la localisation est optionnelle.
            session["tech_signup_location"] = {"lat": None, "lon": None,
                                               "zone": None, "done": True}
            session.modified = True
            return redirect(url_for("technician_signup_finalize"))
        if not _is_valid_coordinate(lat, lon):
            error = "Position invalide. Réessayez d'autoriser la localisation."
        else:
            lat, lon = round(float(lat), 6), round(float(lon), 6)
            zone = _reverse_geocode(lat, lon)
            session["tech_signup_location"] = {"lat": lat, "lon": lon, "zone": zone}
            session.modified = True
            return redirect(url_for("technician_signup_finalize"))

    return render_template(
        "technician_signup_location.html",
        nav_user=get_current_user(),
        loc=loc,
        error=error,
        teaser=False,
    )


def _clear_tech_signup_session():
    """Nettoie toutes les cles du wizard d'inscription technicien."""
    token = session.get("tech_signup_doc_token")
    if token:
        for kind in ("identity", "diploma"):
            _signup_doc_pop(token, kind)
    for k in ("tech_signup", "tech_signup_trade", "tech_signup_docs",
              "tech_signup_doc_token", "tech_signup_location"):
        session.pop(k, None)


@app.route("/devenir-technicien/finalisation", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def technician_signup_finalize():
    """Wizard d'inscription technicien -- etape 5 sur 5 : recapitulatif et
    creation du compte. Les etapes 1 a 4 doivent avoir ete remplies. Au POST
    (case CGU cochee), cree le compte technicien (users.role='technician',
    profession = metier principal, latitude/longitude = position),
    enregistre les documents dans technician_documents (statut 'pending',
    dossier a verifier par l'admin), connecte le nouvel utilisateur et le
    redirige vers son tableau de bord. Aucune migration SQL."""
    ts = session.get("tech_signup") or {}
    trade = session.get("tech_signup_trade")
    docs = session.get("tech_signup_docs") or {}
    loc = session.get("tech_signup_location") or {}

    if not ts.get("pwd_hash"):
        return redirect(url_for("devenir_technicien"))
    if not trade:
        return redirect(url_for("technician_signup_trade"))
    if not docs:
        return redirect(url_for("technician_signup_documents"))
    if not loc:
        return redirect(url_for("technician_signup_location"))
    has_location = _is_valid_coordinate(loc.get("lat"), loc.get("lon"))

    full_name = f"{ts.get('first_name', '')} {ts.get('last_name', '')}".strip()
    phone = _phone_with_prefix(ts.get("phone", ""))
    email = (ts.get("email") or "").strip().lower() or None
    zone_label = (loc.get("zone") or "").strip()
    recap = {
        "full_name": full_name,
        "email": email or "—",
        "phone": phone,
        "trade": dict(_TECH_TRADES).get(trade, trade),
        "identity": bool(docs.get("identity")),
        "diploma": bool(docs.get("diploma")),
        "zone": zone_label or ("Position enregistrée" if has_location
                               else "Non renseignée"),
    }
    error = None

    if request.method == "POST":
        if not request.form.get("accept_cgu"):
            error = "Vous devez accepter les conditions d'utilisation pour créer votre compte."
        else:
            new_id = None
            conn = get_db_connection()
            try:
                if conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone():
                    error = "Ce numéro de téléphone est déjà utilisé."
                elif email and conn.execute(
                        "SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                    error = "Cette adresse e-mail est déjà utilisée."
                else:
                    profession = _TECH_TRADE_PROFESSION.get(trade, trade.capitalize())
                    new_id = _insert_id(
                        conn,
                        "INSERT INTO users (full_name, phone, email, password_hash,"
                        " role, profession, city, zone_intervention, latitude, longitude,"
                        " is_verified, is_active, account_status, availability_status,"
                        " verification_status)"
                        " VALUES (?, ?, ?, ?, 'technician', ?, ?, ?, ?, ?,"
                        " 0, 1, 'ACTIVE', 'hors_ligne', ?)",
                        (full_name, phone, email, ts["pwd_hash"], profession,
                         zone_label or None, zone_label or None,
                         float(loc["lat"]) if has_location else None,
                         float(loc["lon"]) if has_location else None,
                         VERIF_PENDING))

                    token = session.get("tech_signup_doc_token")
                    for kind, dtype in (("identity", DOC_IDENTITY),
                                        ("diploma", DOC_PROFESSIONAL)):
                        data_uri = _signup_doc_pop(token, kind) if token else None
                        if not data_uri:
                            continue
                        mime, ext, encoded = _parse_base64_file(data_uri, 7 * 1024 * 1024)
                        if not ext:
                            continue
                        conn.execute(
                            "INSERT INTO technician_documents (technician_id,"
                            " document_type, file_name, mime_type, file_size,"
                            " content_base64, status)"
                            " VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                            (new_id, dtype, f"{kind}{ext}",
                             mime or "application/octet-stream",
                             len(encoded) if encoded else 0, encoded))
                    conn.commit()
            finally:
                conn.close()

            if new_id and not error:
                _clear_tech_signup_session()
                session.clear()
                session["user_id"] = new_id
                session.permanent = True
                flash("Votre compte technicien a été créé. Votre dossier est"
                      " en cours de vérification.", "success")
                return redirect(url_for("artisan_dashboard"))

    return render_template(
        "technician_signup_finalize.html",
        nav_user=get_current_user(),
        recap=recap,
        error=error,
    )


@app.route("/devenir-technicien/localisation/lieu")
@limiter.limit("60 per hour")
def technician_signup_location_reverse():
    """Geocodage inverse pour l'etape 4 (appele en AJAX par la page apres
    que le navigateur a fourni les coordonnees). Renvoie un libelle de zone
    lisible, jamais l'adresse exacte."""
    lat = request.args.get("lat", "")
    lon = request.args.get("lon", "")
    if not _is_valid_coordinate(lat, lon):
        return jsonify({"ok": False}), 400
    zone = _reverse_geocode(lat, lon)
    return jsonify({"ok": True, "zone": zone or ""})


# --- Verification des techniciens -------------------------------------------

VERIF_PENDING = "PENDING_REVIEW"
VERIF_APPROVED = "APPROVED"
VERIF_REJECTED = "REJECTED"
VERIF_REVISION = "REVISION_REQUIRED"

DOC_IDENTITY = "identity"
DOC_PROFESSIONAL = "professional"
REQUIRED_DOC_TYPES = (DOC_IDENTITY, DOC_PROFESSIONAL)


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


@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per 5 minutes", methods=["POST"])
def admin_login():
    """Ecran de connexion dedie a l'administration."""
    if session.get("user_id"):
        user = get_current_user()
        if user and user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))

    email = ""
    error = ""
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
            session.permanent = True
            return redirect(url_for("admin_dashboard"))
        error = "Email ou mot de passe incorrect."

    # On consomme les messages flash (OAuth, etc.) mais on n'affiche PAS le
    # rappel generique "connectez-vous" a l'ouverture normale : seule une vraie
    # erreur doit apparaitre dans l'encart rouge.
    _flashed = get_flashed_messages()
    if not error:
        for _msg in _flashed:
            low = (_msg or "").lower()
            if "connecter pour" in low or "connectez-vous" in low or "reserve aux" in low:
                continue
            error = _msg

    # Visuel du panneau gauche. Pour changer la photo : remplacer simplement
    # static/img/admin-login-hero.jpg (meme nom, meme emplacement). Le suffixe ?v=
    # est calcule sur la date du fichier -> le navigateur recharge la nouvelle
    # image automatiquement, jamais de cache perime.
    hero = url_for("static", filename="img/admin-login-hero.jpg",
                   v=_static_asset_version("img/admin-login-hero.jpg"))

    security_code_url = (url_for("admin_google_login")
                         if _get_google_client() else url_for("admin_forgot_password"))

    resp = make_response(render_template(
        "admin_login.html", email=email, error=error, hero_image=hero,
        security_code_url=security_code_url, year=datetime.now(timezone.utc).year))
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.route("/admin/mot-de-passe-oublie")
def admin_forgot_password():
    """Rappel : les acces admin sont provisionnes manuellement (pas de reset self-service)."""
    emails = app.config.get("ADMIN_EMAILS") or []
    support = emails[0] if emails else "support@fixpro.gn"
    return render_template("admin_forgot_password.html", support_email=support)


@app.route("/admin/unlock", methods=["GET", "POST"])
@login_required
def admin_unlock():
    """Etape de deverrouillage retiree : redirige directement vers l'espace admin."""
    user = get_current_user()
    if user and user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("admin_login"))


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
    """Racine de l'espace admin : redirige vers le tableau de bord."""
    return redirect(url_for("admin_dashboard"))


_ADM_STATUS_DONE = ("completed", "termine", "terminee", "done")
_ADM_STATUS_PROG = ("in_progress", "on_the_way", "en_route", "assigned", "accepted",
                    "quote_accepted", "intervention")
_ADM_STATUS_WAIT = ("pending", "requested", "nouvelle demande", "quote_proposed",
                    "quote_sent", "en attente", "new")
_ADM_STATUS_CANC = ("cancelled", "canceled", "annulee", "annule", "refused", "rejected",
                    "expired")

_ADM_MONTHS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                  "août", "septembre", "octobre", "novembre", "décembre"]
_ADM_DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _adm_status_bucket(status):
    s = (status or "").strip().lower()
    if s in _ADM_STATUS_DONE:
        return "done"
    if s in _ADM_STATUS_CANC:
        return "canc"
    if s in _ADM_STATUS_WAIT:
        return "wait"
    if s in _ADM_STATUS_PROG:
        return "prog"
    return "wait"


def _fmt_int(value):
    """Entier avec separateur de milliers a la francaise (espace insecable fine)."""
    try:
        return "{:,}".format(int(value or 0)).replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _adm_pct(part, total):
    return int(round(part / total * 100)) if total else 0


def _adm_trend(cur, prev):
    if prev and prev > 0:
        return int(round((cur - prev) / prev * 100))
    if cur > 0:
        return 100
    return None


def _adm_ago(dt_str):
    """Libelle 'Il y a N min/h/j' a partir d'une date ISO/texte."""
    if not dt_str:
        return ""
    try:
        base = datetime.strptime(str(dt_str)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            base = datetime.strptime(str(dt_str)[:10], "%Y-%m-%d")
        except ValueError:
            return ""
    delta = datetime.now(timezone.utc).replace(tzinfo=None) - base
    secs = int(delta.total_seconds())
    if secs < 60:
        return "À l'instant"
    if secs < 3600:
        return "Il y a %d min" % (secs // 60)
    if secs < 86400:
        return "Il y a %d heure%s" % (secs // 3600, "s" if secs // 3600 > 1 else "")
    days = secs // 86400
    return "Il y a %d jour%s" % (days, "s" if days > 1 else "")


# ---------------------------------------------------------------------------
# Donnees de DEMONSTRATION du tableau de bord (fausses donnees coherentes).
# Activees via app.config["ADMIN_DASHBOARD_DEMO"] (ADMIN_DASHBOARD_DEMO=0 pour
# revenir aux vraies donnees). NE PAS confondre avec les vraies donnees API.
# ---------------------------------------------------------------------------
_ADMIN_DASHBOARD_DEMO = {
    "kpis": {
        "users": {"value": 12548, "delta": 12},
        "techs": {"value": 1892, "delta": 8},
        "missions": {"value": 3421, "delta": 18},
        "revenue": {"value": 24560, "delta": 25},
    },
    "chart": {
        "days": [25, 26, 27, 28, 29, 30, 31],
        "month": 8,  # aout
        "created": [78, 86, 110, 102, 118, 142, 156],
        "done": [26, 38, 61, 54, 67, 89, 121],
    },
    "status": {"total": 3421, "done": 1890, "prog": 820, "wait": 431, "canc": 280},
    "notifications": [
        {"kind": "message", "text": "5 nouveaux messages", "ago": "Il y a 10 min"},
        {"kind": "tech", "text": "3 nouveaux techniciens", "ago": "Il y a 25 min"},
        {"kind": "mission", "text": "12 nouvelles missions", "ago": "Il y a 1 heure"},
        {"kind": "report", "text": "1 signalement", "ago": "Il y a 2 heures"},
    ],
    "notif_count": 5,
    "last_missions": [
        ("#FP-3241", "Aminata Diallo", "Plomberie", "done", "01/09/2026"),
        ("#FP-3240", "Mamadou Keita", "Électricité", "prog", "01/09/2026"),
        ("#FP-3239", "Sarah Camara", "Climatisation", "wait", "01/09/2026"),
        ("#FP-3238", "Ibrahima Sylla", "Menuiserie", "done", "31/08/2026"),
        ("#FP-3237", "Fatoumata Barry", "Peinture", "canc", "31/08/2026"),
    ],
    "top_techs": [
        ("Moussa Bah", "Plombier", "4.9"),
        ("Aïssatou Diallo", "Électricienne", "4.8"),
        ("Karim Soumah", "Frigoriste", "4.7"),
        ("Lansana Camara", "Menuisier", "4.7"),
        ("Mariama Kourouma", "Peintre", "4.6"),
    ],
    "recent_messages": [
        ("Aminata Diallo", "Bonjour, le problème est résolu merci !", "14:25"),
        ("Mamadou Keita", "Quand pouvez-vous arriver ?", "13:40"),
        ("Sarah Camara", "D'accord, je vous attends.", "12:18"),
        ("Ibrahima Sylla", "Le technicien est en route.", "11:05"),
        ("Fatoumata Barry", "Merci pour votre réactivité !", "10:22"),
    ],
}

_ADM_STATUS_LABELS = {"done": "Terminée", "prog": "En cours",
                      "wait": "En attente", "canc": "Annulée"}


def _admin_dashboard_demo_context():
    """Construit le contexte du template a partir de _ADMIN_DASHBOARD_DEMO."""
    d = _ADMIN_DASHBOARD_DEMO
    k = d["kpis"]
    kpis = {
        "users": {"value": _fmt_int(k["users"]["value"]), "delta": k["users"]["delta"]},
        "techs": {"value": _fmt_int(k["techs"]["value"]), "delta": k["techs"]["delta"]},
        "missions": {"value": _fmt_int(k["missions"]["value"]), "delta": k["missions"]["delta"]},
        "revenue": {"value": _fmt_int(k["revenue"]["value"]), "delta": k["revenue"]["delta"]},
    }
    c = d["chart"]
    mon = _ADM_MONTHS_FR[c["month"]][:4].capitalize()
    chart = {
        "labels": ["%d %s" % (day, mon) for day in c["days"]],
        "created": list(c["created"]),
        "done": list(c["done"]),
    }
    s = d["status"]
    total = s["total"] or 1
    status = {
        "total": _fmt_int(s["total"]),
        "done": s["done"], "prog": s["prog"], "wait": s["wait"], "canc": s["canc"],
        "done_pct": _adm_pct(s["done"], total),
        "prog_pct": _adm_pct(s["prog"], total),
        "wait_pct": _adm_pct(s["wait"], total),
        "canc_pct": _adm_pct(s["canc"], total),
    }
    last_missions = [
        {"code": code, "client": client, "service": svc, "pill": pill,
         "status_label": _ADM_STATUS_LABELS[pill], "date": date}
        for code, client, svc, pill, date in d["last_missions"]
    ]
    top_techs = [{"name": n, "job": j, "rating": r} for n, j, r in d["top_techs"]]
    recent_messages = [
        {"name": n, "preview": (txt[:52] + "…") if len(txt) > 52 else txt, "time": t}
        for n, txt, t in d["recent_messages"]
    ]
    return {
        "kpis": kpis, "chart": chart, "status": status,
        "notifications": [dict(x) for x in d["notifications"]],
        "header_notifs": [dict(x) for x in d["notifications"]],
        "notif_count": d["notif_count"],
        "last_missions": last_missions, "top_techs": top_techs,
        "recent_messages": recent_messages,
    }


# ---------------------------------------------------------------------------
# Donnees de DEMONSTRATION du tableau de bord CLIENT (fausses donnees
# coherentes, cf. maquette). Activees par app.config["CLIENT_DASHBOARD_DEMO"]
# (CLIENT_DASHBOARD_DEMO=0 -> vraies donnees du client). Ne remplacent JAMAIS
# les vraies donnees en production.
# ---------------------------------------------------------------------------
_CLIENT_DASHBOARD_DEMO = {
    "stats": {
        "requests": {"value": 12, "delta": "+3", "note": "ce mois", "trend": "up"},
        "done": {"value": 8, "delta": "+2", "note": "ce mois", "trend": "up"},
        "progress": {"value": 2, "delta": "stable", "note": "", "trend": "flat"},
        "spent": {"value": 1250000, "delta": "+15%", "note": "ce mois", "trend": "up"},
    },
    "address": "Kaloum, Conakry",
    "technician": {
        "name": "Moussa Bah", "job": "Plombier", "rating": "4.9",
        "reviews": 128, "phone": "+224620112233",
    },
    "requests": [
        ("#FP-3241", "Plomberie", "Moussa Bah", "done", "01/09/2026"),
        ("#FP-3240", "Électricité", "Aïssatou Diallo", "prog", "29/08/2026"),
        ("#FP-3239", "Climatisation", "Karim Soumah", "wait", "25/08/2026"),
        ("#FP-3238", "Menuiserie", "Lansana Camara", "done", "20/08/2026"),
        ("#FP-3237", "Peinture", "Mariama Kourouma", "canc", "18/08/2026"),
    ],
    "notifications": [
        ("success", "Votre demande #FP-3241 est terminée", "Il y a 10 min"),
        ("tech", "Le technicien arrive bientôt", "Il y a 25 min"),
        ("pay", "Votre paiement a été confirmé", "Il y a 1 heure"),
        ("msg", "Nouveau message de Moussa Bah", "Il y a 2 heures"),
    ],
}

_CLIENT_STATUS_LABELS = {"done": "Terminée", "prog": "En cours",
                         "wait": "En attente", "canc": "Annulée"}

# Services affiches dans la carte "Nos services" (nom + cle d'icone CSS).
_CLIENT_SERVICES = [
    ("Plomberie", "plumb"), ("Électricité", "elec"), ("Climatisation", "clim"),
    ("Menuiserie", "wood"), ("Peinture", "paint"), ("Nettoyage", "clean"),
]


def _client_dashboard_demo_context():
    """Construit le contexte du template a partir de _CLIENT_DASHBOARD_DEMO."""
    d = _CLIENT_DASHBOARD_DEMO
    s = d["stats"]

    def _stat(key, suffix=""):
        v = s[key]
        return {"value": _fmt_int(v["value"]).replace(" ", " ") + suffix,
                "delta": v["delta"], "note": v["note"], "trend": v["trend"]}

    stats = {
        "requests": _stat("requests"), "done": _stat("done"),
        "progress": _stat("progress"), "spent": _stat("spent", " GNF"),
    }
    recent_requests = [
        {"code": c, "service": sv, "tech": t, "pill": p,
         "status_label": _CLIENT_STATUS_LABELS[p], "date": dt}
        for c, sv, t, p, dt in d["requests"]
    ]
    notifications = [{"kind": k, "text": tx, "ago": ag}
                     for k, tx, ag in d["notifications"]]
    return {
        "stats": stats,
        "recent_requests": recent_requests,
        "notifications": notifications,
        "my_tech": dict(d["technician"]),
        "my_address": d["address"],
        "unread_count": len(notifications),
        "demo_identity": {"full_name": "Aminata Diallo", "first_name": "Aminata"},
    }


@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    """Tableau de bord admin : KPI, activite des missions, statuts, listes.

    Affiche des donnees de DEMONSTRATION tant que app.config['ADMIN_DASHBOARD_DEMO']
    est actif (ADMIN_DASHBOARD_DEMO=0 pour repasser aux vraies donnees de la base)."""
    user = get_current_user()
    now = datetime.now(timezone.utc)
    month_prefix = now.strftime("%Y-%m")
    prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    first_name = (user.get("full_name") or "Admin").split(" ")[0] if user else "Admin"
    today_label = "%s %d %s %d" % (
        _ADM_DAYS_FR[now.weekday()].capitalize(), now.day,
        _ADM_MONTHS_FR[now.month].capitalize(), now.year)
    base_ctx = {
        "admin_user": user, "admin_first_name": first_name, "current_year": now.year,
        "today_label": today_label, "demo_mode": bool(app.config.get("ADMIN_DASHBOARD_DEMO")),
    }

    if app.config.get("ADMIN_DASHBOARD_DEMO"):
        base_ctx.update(_admin_dashboard_demo_context())
        return render_template("admin_dashboard.html", **base_ctx)

    conn = get_db_connection()
    try:
        def _n(sql, params=()):
            try:
                row = conn.execute(sql, params).fetchone()
                return int((row["n"] if row else 0) or 0)
            except Exception:
                conn.rollback()
                return 0

        # --- KPI ---
        users_total = _n("SELECT COUNT(*) AS n FROM users WHERE role = 'client'")
        users_prev = _n("SELECT COUNT(*) AS n FROM users WHERE role = 'client'"
                        " AND substr(created_at, 1, 7) <= ?", (prev_month,))
        techs_total = _n("SELECT COUNT(*) AS n FROM users WHERE role = 'technician'")
        techs_prev = _n("SELECT COUNT(*) AS n FROM users WHERE role = 'technician'"
                        " AND substr(created_at, 1, 7) <= ?", (prev_month,))
        missions_total = _n("SELECT COUNT(*) AS n FROM requests")
        missions_prev = _n("SELECT COUNT(*) AS n FROM requests"
                           " WHERE substr(created_at, 1, 7) <= ?", (prev_month,))
        revenue_month = _n("SELECT COALESCE(SUM(amount), 0) AS n FROM subscription_payments"
                           " WHERE LOWER(status) IN ('paid', 'completed', 'succeeded')"
                           " AND substr(COALESCE(paid_at, created_at), 1, 7) = ?", (month_prefix,))
        revenue_prev = _n("SELECT COALESCE(SUM(amount), 0) AS n FROM subscription_payments"
                          " WHERE LOWER(status) IN ('paid', 'completed', 'succeeded')"
                          " AND substr(COALESCE(paid_at, created_at), 1, 7) = ?", (prev_month,))

        kpis = {
            "users": {"value": _fmt_int(users_total), "delta": _adm_trend(users_total, users_prev)},
            "techs": {"value": _fmt_int(techs_total), "delta": _adm_trend(techs_total, techs_prev)},
            "missions": {"value": _fmt_int(missions_total), "delta": _adm_trend(missions_total, missions_prev)},
            "revenue": {"value": _fmt_int(revenue_month), "delta": _adm_trend(revenue_month, revenue_prev)},
        }

        # --- Activite des missions : 7 derniers jours ---
        labels, created, done = [], [], []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            labels.append("%d %s" % ((now - timedelta(days=i)).day,
                                     _ADM_MONTHS_FR[(now - timedelta(days=i)).month][:4].capitalize()))
            created.append(_n("SELECT COUNT(*) AS n FROM requests WHERE substr(created_at, 1, 10) = ?", (day,)))
            done.append(_n("SELECT COUNT(*) AS n FROM requests WHERE LOWER(status) = 'completed'"
                           " AND substr(COALESCE(completed_at, updated_at, created_at), 1, 10) = ?", (day,)))
        chart = {"labels": labels, "created": created, "done": done}

        # --- Statut des missions (ce mois) ---
        buckets = {"done": 0, "prog": 0, "wait": 0, "canc": 0}
        try:
            for r in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM requests"
                    " WHERE substr(created_at, 1, 7) = ? GROUP BY status", (month_prefix,)).fetchall():
                buckets[_adm_status_bucket(r["status"])] += int(r["n"] or 0)
        except Exception:
            conn.rollback()
        s_total = sum(buckets.values())
        status = {
            "total": _fmt_int(s_total),
            "done": buckets["done"], "prog": buckets["prog"],
            "wait": buckets["wait"], "canc": buckets["canc"],
            "done_pct": _adm_pct(buckets["done"], s_total),
            "prog_pct": _adm_pct(buckets["prog"], s_total),
            "wait_pct": _adm_pct(buckets["wait"], s_total),
            "canc_pct": _adm_pct(buckets["canc"], s_total),
        }

        # --- Nouvelles notifications (agrege 24h) ---
        d1 = (now - timedelta(days=1)).isoformat()
        n_msg = _n("SELECT COUNT(*) AS n FROM conversation_messages WHERE created_at >= ?", (d1,))
        n_tech = _n("SELECT COUNT(*) AS n FROM users WHERE role = 'technician' AND created_at >= ?", (d1,))
        n_miss = _n("SELECT COUNT(*) AS n FROM requests WHERE created_at >= ?", (d1,))
        n_rep = _n("SELECT COUNT(*) AS n FROM conversation_reports WHERE created_at >= ? AND LOWER(status) IN ('open', 'pending', 'new')", (d1,))
        notifications = []
        if n_msg:
            notifications.append({"kind": "message", "text": "%d nouveau%s message%s" % (n_msg, "x" if n_msg > 1 else "", "s" if n_msg > 1 else ""), "ago": "Dernières 24 h"})
        if n_tech:
            notifications.append({"kind": "tech", "text": "%d nouveau%s technicien%s" % (n_tech, "x" if n_tech > 1 else "", "s" if n_tech > 1 else ""), "ago": "Dernières 24 h"})
        if n_miss:
            notifications.append({"kind": "mission", "text": "%d nouvelle%s mission%s" % (n_miss, "s" if n_miss > 1 else "", "s" if n_miss > 1 else ""), "ago": "Dernières 24 h"})
        if n_rep:
            notifications.append({"kind": "report", "text": "%d signalement%s" % (n_rep, "s" if n_rep > 1 else ""), "ago": "Dernières 24 h"})

        # --- En-tete : dernieres notifications reelles ---
        header_notifs = []
        try:
            for r in conn.execute(
                    "SELECT title, type, created_at FROM notifications"
                    " ORDER BY created_at DESC LIMIT 5").fetchall():
                t = (r["type"] or "").lower()
                kind = "mission" if "request" in t or "mission" in t else \
                       "tech" if "tech" in t or "artisan" in t else \
                       "report" if "report" in t or "signal" in t else "message"
                header_notifs.append({"kind": kind, "text": r["title"] or "Notification",
                                      "ago": _adm_ago(r["created_at"])})
        except Exception:
            conn.rollback()
        notif_count = n_msg + n_tech + n_miss + n_rep

        # --- Dernieres missions ---
        last_missions = []
        try:
            for r in conn.execute(
                    "SELECT r.id, r.reference, r.service, r.category, r.status, r.created_at,"
                    " c.full_name AS client_name"
                    " FROM requests r LEFT JOIN users c ON c.id = r.client_id"
                    " ORDER BY r.created_at DESC LIMIT 6").fetchall():
                b = _adm_status_bucket(r["status"])
                iso = str(r["created_at"] or "")[:10]
                parts = iso.split("-")
                date_fr = "/".join(reversed(parts)) if len(parts) == 3 else iso
                last_missions.append({
                    "code": r["reference"] or ("#FP-%04d" % r["id"]),
                    "client": r["client_name"] or "Client",
                    "service": (r["service"] or r["category"] or "—").capitalize(),
                    "pill": b,
                    "status_label": {"done": "Terminée", "prog": "En cours",
                                     "wait": "En attente", "canc": "Annulée"}[b],
                    "date": date_fr,
                })
        except Exception:
            conn.rollback()

        # --- Techniciens les mieux notes ---
        top_techs = []
        try:
            for r in conn.execute(
                    "SELECT u.full_name, u.profession, ROUND(AVG(rv.rating), 1) AS note, COUNT(rv.id) AS c"
                    " FROM users u JOIN reviews rv ON rv.artisan_id = u.id"
                    " WHERE u.role = 'technician'"
                    " GROUP BY u.id HAVING c > 0"
                    " ORDER BY note DESC, c DESC LIMIT 5").fetchall():
                top_techs.append({"name": r["full_name"] or "Technicien",
                                  "job": (r["profession"] or "Technicien").capitalize(),
                                  "rating": ("%.1f" % (r["note"] or 0))})
        except Exception:
            conn.rollback()

        # --- Messages recents ---
        recent_messages = []
        try:
            for r in conn.execute(
                    "SELECT m.content, m.created_at, u.full_name"
                    " FROM conversation_messages m LEFT JOIN users u ON u.id = m.sender_id"
                    " WHERE m.sender_role <> 'system'"
                    " ORDER BY m.created_at DESC LIMIT 5").fetchall():
                txt = (r["content"] or "").strip().replace("\n", " ")
                recent_messages.append({
                    "name": r["full_name"] or "Utilisateur",
                    "preview": (txt[:52] + "…") if len(txt) > 52 else (txt or "—"),
                    "time": str(r["created_at"] or "")[11:16] or "—",
                })
        except Exception:
            conn.rollback()
    finally:
        conn.close()

    base_ctx.update(
        notif_count=notif_count, header_notifs=header_notifs,
        kpis=kpis, chart=chart, status=status, notifications=notifications,
        last_missions=last_missions, top_techs=top_techs, recent_messages=recent_messages)
    return render_template("admin_dashboard.html", **base_ctx)


# ===========================================================================
# ADMIN - Page "Utilisateurs" (liste, filtres, pagination, export, profil).
# Donnees de DEMONSTRATION deterministes tant que app.config["ADMIN_USERS_DEMO"]
# est actif (ADMIN_USERS_DEMO=0 -> vraie table `users`). Les faux comptes ne
# sont JAMAIS ecrits en base : creation / blocage vivent en session.
# ===========================================================================
_ADMIN_USERS_DEMO_TOTAL = 12548
_ADMIN_USERS_ZONES = ["Kaloum", "Dixinn", "Ratoma", "Matam", "Matoto"]
_ADMIN_USERS_FIRST = [
    "Aminata", "Mamadou", "Sarah", "Ibrahima", "Fatoumata", "Moussa", "Karim",
    "Mariama", "Lansana", "Sira", "Alpha", "Kadiatou", "Ousmane", "Hawa",
    "Sékou", "Aïcha", "Boubacar", "Nènè", "Thierno", "Fanta", "Mohamed",
    "Djénabou", "Amadou", "Rougui",
]
_ADMIN_USERS_LAST = [
    "Diallo", "Baldé", "Barry", "Camara", "Bah", "Sow", "Keita", "Touré",
    "Condé", "Soumah", "Sylla", "Cissé", "Kourouma", "Doumbouya", "Sacko",
    "Kaba", "Traoré", "Fofana", "Bangoura", "Sangaré", "Dramé", "Kanté",
]
_ADMIN_USERS_KPIS = {
    "total": {"value": 12548, "delta": 12},
    "active": {"value": 10842, "delta": 8},
    "new": {"value": 426, "delta": 15},
    "blocked": {"value": 37, "delta": -4},
}
_ADMIN_USERS_STATUS_LABELS = {"active": "Actif", "inactive": "Inactif", "blocked": "Bloqué"}


_ADMIN_ACCENTS = str.maketrans("àâäéèêëïîôöùûüç", "aaaeeeeiioouuuc")


def _strip_accents(s):
    return (s or "").translate(_ADMIN_ACCENTS)


def _admin_user_demo_row(i):
    """Un utilisateur de demo deterministe pour l'index 0-based i."""
    fn = _ADMIN_USERS_FIRST[i % len(_ADMIN_USERS_FIRST)]
    ln = _ADMIN_USERS_LAST[(i // len(_ADMIN_USERS_FIRST)) % len(_ADMIN_USERS_LAST)]
    n = i + 1
    if n % 339 == 0:
        status = "blocked"
    elif n % 15 in (3, 10):
        status = "inactive"
    else:
        status = "active"
    slug = "%s.%s" % (_strip_accents(fn).lower(), _strip_accents(ln).lower())
    email = "%s%s@email.com" % (slug, "" if i < len(_ADMIN_USERS_FIRST) * len(_ADMIN_USERS_LAST) else i)
    month = (i % 9) + 1  # janv. -> sept. 2026 (pas de date future)
    day = (i % 27) + 1
    return {
        "code": "#FP-%04d" % (1000 + n),
        "name": "%s %s" % (fn, ln),
        "email": email,
        "phone": "+224 6%02d %02d %02d %02d" % (20 + i % 8, i % 100, (i * 3) % 100, (i * 7) % 100),
        "zone": _ADMIN_USERS_ZONES[i % len(_ADMIN_USERS_ZONES)],
        "requests": (2 + i * 7) % 30,
        "status": status,
        "joined": "%02d/%02d/2026" % (day, month),
        "photo": None,
    }


# Les 10 premieres lignes = celles de la maquette (source de verite visuelle).
_ADMIN_USERS_DEMO_HEAD = [
    ("Aminata Diallo", "aminata.diallo@email.com", "Kaloum", 12, "active", "01/08/2026"),
    ("Mamadou Keita", "mamadou.keita@email.com", "Dixinn", 8, "active", "28/07/2026"),
    ("Sarah Camara", "sarah.camara@email.com", "Ratoma", 5, "active", "25/07/2026"),
    ("Ibrahima Sylla", "ibrahima.sylla@email.com", "Matam", 3, "inactive", "19/07/2026"),
    ("Fatoumata Barry", "fatoumata.barry@email.com", "Dixinn", 15, "active", "12/07/2026"),
    ("Moussa Bah", "moussa.bah@email.com", "Kaloum", 6, "blocked", "05/07/2026"),
    ("Karim Soumah", "karim.soumah@email.com", "Ratoma", 9, "active", "02/07/2026"),
    ("Mariama Kourouma", "mariama.kourouma@email.com", "Matam", 4, "active", "28/06/2026"),
    ("Lansana Camara", "lansana.camara@email.com", "Kaloum", 7, "inactive", "21/06/2026"),
    ("Sira Condé", "sira.conde@email.com", "Matoto", 2, "active", "15/06/2026"),
]


def _admin_users_demo_all():
    """Liste complete des utilisateurs de demo (12 548), tetes de maquette + suite
    deterministe, puis les comptes ajoutes en session, avec surcharges de statut."""
    rows = []
    for idx, (name, email, zone, reqs, status, joined) in enumerate(_ADMIN_USERS_DEMO_HEAD):
        rows.append({
            "code": "#FP-%04d" % (1001 + idx), "name": name, "email": email,
            "phone": "+224 620 00 00 %02d" % (idx + 1), "zone": zone,
            "requests": reqs, "status": status, "joined": joined, "photo": None,
        })
    for i in range(len(_ADMIN_USERS_DEMO_HEAD), _ADMIN_USERS_DEMO_TOTAL):
        rows.append(_admin_user_demo_row(i))

    extras = session.get("admin_users_extra") or []
    rows = list(extras) + rows

    overrides = session.get("admin_users_status") or {}
    if overrides:
        for r in rows:
            if r["code"] in overrides:
                r["status"] = overrides[r["code"]]
    return rows


def _admin_users_filter(rows, q, status, zone, joined=""):
    q = (q or "").strip().lower()
    if q:
        rows = [r for r in rows if q in r["name"].lower() or q in r["email"].lower()
                or q in r["phone"].lower() or q in r["code"].lower()]
    if status in ("active", "inactive", "blocked"):
        rows = [r for r in rows if r["status"] == status]
    if zone in _ADMIN_USERS_ZONES:
        rows = [r for r in rows if r["zone"] == zone]
    if joined in ("30", "90", "2026"):
        today = datetime.now(timezone.utc).date()

        def _keep(r):
            try:
                d, m, y = (int(x) for x in str(r["joined"]).split("/"))
                dt = date(y, m, d)
            except (ValueError, TypeError):
                return False
            if joined == "2026":
                return y == 2026
            return 0 <= (today - dt).days <= int(joined)
        rows = [r for r in rows if _keep(r)]
    return rows


def _admin_users_query_args():
    q = (request.args.get("q") or "").strip()[:80]
    status = request.args.get("status") or ""
    zone = request.args.get("zone") or ""
    joined = request.args.get("joined") or ""
    try:
        per_page = int(request.args.get("per_page") or 10)
    except (TypeError, ValueError):
        per_page = 10
    per_page = per_page if per_page in (10, 25, 50, 100) else 10
    try:
        page = max(1, int(request.args.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    return q, status, zone, joined, per_page, page


@app.route("/admin/utilisateurs")
@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    """Page admin de gestion des utilisateurs (liste + filtres + pagination)."""
    user = get_current_user()
    now = datetime.now(timezone.utc)
    q, status, zone, joined, per_page, page = _admin_users_query_args()
    demo = bool(app.config.get("ADMIN_USERS_DEMO"))

    if demo:
        all_rows = _admin_users_demo_all()
        kpis = {
            k: {"value": _fmt_int(v["value"]), "delta": v["delta"]}
            for k, v in _ADMIN_USERS_KPIS.items()
        }
        headline_total = _ADMIN_USERS_KPIS["total"]["value"]
    else:
        all_rows = _admin_users_real_rows()
        n_total = len(all_rows)
        n_active = sum(1 for r in all_rows if r["status"] == "active")
        n_blocked = sum(1 for r in all_rows if r["status"] == "blocked")
        month_prefix = now.strftime("%Y-%m")
        n_new = sum(1 for r in all_rows if _admin_user_joined_month(r["joined"]) == month_prefix)
        kpis = {
            "total": {"value": _fmt_int(n_total), "delta": None},
            "active": {"value": _fmt_int(n_active), "delta": None},
            "new": {"value": _fmt_int(n_new), "delta": None},
            "blocked": {"value": _fmt_int(n_blocked), "delta": None},
        }
        headline_total = n_total

    rows = _admin_users_filter(all_rows, q, status, zone, joined)
    total_filtered = len(rows)
    pages = max(1, -(-total_filtered // per_page))
    page = min(page, pages)
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]

    def _page_url(p):
        args = {"page": p, "per_page": per_page}
        if q:
            args["q"] = q
        if status:
            args["status"] = status
        if zone:
            args["zone"] = zone
        if joined:
            args["joined"] = joined
        return url_for("admin_users", **args)

    window = [p for p in range(max(1, page - 2), min(pages, page + 2) + 1)]

    base_ctx = {
        "admin_user": user, "current_year": now.year,
        "notif_count": 0, "header_notifs": [],
        "kpis": kpis, "users": page_rows,
        "status_labels": _ADMIN_USERS_STATUS_LABELS,
        "zones": _ADMIN_USERS_ZONES,
        "f_q": q, "f_status": status, "f_zone": zone, "f_joined": joined,
        "per_page": per_page, "page": page, "pages": pages,
        "page_window": window, "total_filtered": total_filtered,
        "headline_total": _fmt_int(headline_total),
        "range_from": (start + 1) if page_rows else 0,
        "range_to": start + len(page_rows),
        "prev_url": _page_url(page - 1) if page > 1 else None,
        "next_url": _page_url(page + 1) if page < pages else None,
        "first_url": _page_url(1), "last_url": _page_url(pages),
        "page_url_tpl": _page_url("__P__"),
        "demo_mode": demo,
    }
    resp = make_response(render_template("admin_users.html", **base_ctx))
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _admin_user_joined_month(joined):
    # "dd/mm/yyyy" -> "yyyy-mm"
    try:
        d, m, y = str(joined).split("/")
        return "%s-%s" % (y, m)
    except ValueError:
        return ""


def _admin_users_real_rows():
    """Vraie table users (role client) mappee au format de la page."""
    conn = get_db_connection()
    out = []
    try:
        cur = conn.execute(
            "SELECT id, full_name, email, phone, city, quartier, account_status,"
            " is_active, created_at FROM users WHERE role = 'client' ORDER BY created_at DESC")
        for r in cur.fetchall():
            st = (r["account_status"] or "").lower()
            if "block" in st or "suspend" in st or (r["is_active"] == 0):
                status = "blocked" if "block" in st or "suspend" in st else "inactive"
            else:
                status = "active"
            reqs = 0
            try:
                reqs = int(conn.execute(
                    "SELECT COUNT(*) AS n FROM requests WHERE client_id = ?", (r["id"],)
                ).fetchone()["n"] or 0)
            except Exception:
                conn.rollback()
            joined = ""
            raw = str(r["created_at"] or "")[:10]
            if len(raw) == 10 and raw[4] == "-":
                joined = "%s/%s/%s" % (raw[8:10], raw[5:7], raw[0:4])
            out.append({
                "code": "#FP-%04d" % (1000 + int(r["id"])),
                "name": r["full_name"] or "Utilisateur",
                "email": r["email"] or "—",
                "phone": r["phone"] or "—",
                "zone": r["quartier"] or r["city"] or "—",
                "requests": reqs, "status": status, "joined": joined,
                "photo": None, "uid": int(r["id"]),
            })
    except Exception:
        conn.rollback()
    finally:
        conn.close()
    return out


@app.route("/admin/utilisateurs/export")
@login_required
@admin_required
def admin_users_export():
    """Export CSV des utilisateurs filtres (demo ou reels)."""
    q, status, zone, joined, per_page, page = _admin_users_query_args()
    rows = (_admin_users_demo_all() if app.config.get("ADMIN_USERS_DEMO")
            else _admin_users_real_rows())
    rows = _admin_users_filter(rows, q, status, zone, joined)

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Identifiant", "Nom", "E-mail", "Telephone", "Localisation",
                "Demandes", "Statut", "Inscription"])
    for r in rows:
        w.writerow([r["code"], r["name"], r["email"], r["phone"], r["zone"],
                    r["requests"], _ADMIN_USERS_STATUS_LABELS.get(r["status"], r["status"]),
                    r["joined"]])
    out = make_response("﻿" + buf.getvalue())
    out.headers["Content-Type"] = "text/csv; charset=utf-8"
    out.headers["Content-Disposition"] = (
        "attachment; filename=fixpro-utilisateurs-%s.csv"
        % datetime.now().strftime("%Y%m%d"))
    return out


@app.route("/admin/utilisateurs/creer", methods=["POST"])
@login_required
@admin_required
def admin_users_create():
    """Ajoute un utilisateur a la liste de DEMO (session, jamais en base)."""
    if not app.config.get("ADMIN_USERS_DEMO"):
        flash("La creation directe est desactivee hors mode demonstration.", "error")
        return redirect(url_for("admin_users"))
    first = (request.form.get("first_name") or "").strip()[:40]
    last = (request.form.get("last_name") or "").strip()[:40]
    email = (request.form.get("email") or "").strip()[:120]
    phone = (request.form.get("phone") or "").strip()[:30]
    zone = request.form.get("zone") or ""
    status = request.form.get("status") or "active"
    if not first or not last or "@" not in email:
        flash("Prénom, nom et e-mail valide sont obligatoires.", "error")
        return redirect(url_for("admin_users"))
    if zone not in _ADMIN_USERS_ZONES:
        zone = _ADMIN_USERS_ZONES[0]
    if status not in _ADMIN_USERS_STATUS_LABELS:
        status = "active"
    extras = session.get("admin_users_extra") or []
    new_code = "#FP-%04d" % (9000 + len(extras) + 1)
    extras.insert(0, {
        "code": new_code, "name": "%s %s" % (first, last), "email": email,
        "phone": phone or "—", "zone": zone, "requests": 0, "status": status,
        "joined": datetime.now().strftime("%d/%m/2026"), "photo": None,
    })
    session["admin_users_extra"] = extras[:50]
    session.modified = True
    flash("Utilisateur « %s %s » créé (données de démonstration)." % (first, last), "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/utilisateurs/<code>/statut", methods=["POST"])
@login_required
@admin_required
def admin_users_set_status(code):
    """Bloque / débloque / (dés)active un utilisateur (surcharge en session en demo)."""
    code = ("#" + code) if not code.startswith("#") else code
    new_status = request.form.get("status") or "blocked"
    if new_status not in _ADMIN_USERS_STATUS_LABELS:
        new_status = "blocked"
    if app.config.get("ADMIN_USERS_DEMO"):
        ov = session.get("admin_users_status") or {}
        ov[code] = new_status
        session["admin_users_status"] = ov
        session.modified = True
    else:
        try:
            uid = int(code.lstrip("#FP-").lstrip("0") or "0") - 1000
            conn = get_db_connection()
            conn.execute("UPDATE users SET account_status = ? WHERE id = ?",
                         (new_status, uid))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("admin_users_set_status: %s", exc)
    flash("Statut mis à jour : %s." % _ADMIN_USERS_STATUS_LABELS[new_status], "success")
    ref = request.form.get("next") or url_for("admin_users")
    return redirect(ref)


@app.route("/admin/utilisateurs/<code>")
@login_required
@admin_required
def admin_user_detail(code):
    """Fiche détaillée d'un utilisateur."""
    user = get_current_user()
    now = datetime.now(timezone.utc)
    code = ("#" + code) if not code.startswith("#") else code
    rows = (_admin_users_demo_all() if app.config.get("ADMIN_USERS_DEMO")
            else _admin_users_real_rows())
    target = next((r for r in rows if r["code"] == code), None)
    if not target:
        flash("Utilisateur introuvable.", "error")
        return redirect(url_for("admin_users"))

    total = target["requests"]
    done = int(round(total * 0.62))
    prog = max(0, min(total - done, 1 + total % 3))
    wait = max(0, total - done - prog)
    seed = sum(ord(c) for c in target["code"])
    services = ["Plomberie", "Électricité", "Climatisation", "Menuiserie", "Peinture"]
    techs = ["Moussa Bah", "Aïssatou Diallo", "Karim Soumah", "Lansana Camara", "Mariama Kourouma"]
    pills = ["done", "done", "prog", "wait", "canc"]
    labels = {"done": "Terminée", "prog": "En cours", "wait": "En attente", "canc": "Annulée"}
    history = []
    for k in range(min(total, 6)):
        p = pills[(seed + k) % len(pills)]
        history.append({
            "code": "#FP-%d" % (3200 - seed % 60 - k),
            "service": services[(seed + k) % len(services)],
            "tech": techs[(seed + k) % len(techs)],
            "pill": p, "status_label": labels[p],
            "date": "%02d/%02d/2026" % (1 + (seed + k) % 27, 1 + (seed + k) % 9),
        })

    ctx = {
        "admin_user": user, "current_year": now.year,
        "notif_count": 0, "header_notifs": [],
        "u": target,
        "status_labels": _ADMIN_USERS_STATUS_LABELS,
        "stats": {"total": total, "done": done, "prog": prog, "wait": wait},
        "history": history,
        "demo_mode": bool(app.config.get("ADMIN_USERS_DEMO")),
    }
    resp = make_response(render_template("admin_user_detail.html", **ctx))
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ===========================================================================
# ADMIN - Page "Techniciens" (liste, filtres, pagination, export, fiche).
# Meme patron que /admin/utilisateurs. ADMIN_TECHNICIANS_DEMO=0 -> vraie table
# `users` (role technician). Ajouts / changements de statut vivent en session.
# ===========================================================================
_ADMIN_TECHS_DEMO_TOTAL = 1892
_ADMIN_TECHS_SPECIALTIES = [
    "Plombier", "Électricien", "Frigoriste", "Menuisier", "Peintre",
    "Climaticien", "Nettoyage", "Maçon", "Jardinier",
]
_ADMIN_TECHS_AVAIL_LABELS = {
    "available": "Disponible", "busy": "En intervention", "offline": "Indisponible",
}
_ADMIN_TECHS_STATUS_LABELS = {
    "active": "Actif", "pending": "En attente", "suspended": "Suspendu", "blocked": "Bloqué",
}
_ADMIN_TECHS_KPIS = {
    "total": {"value": 1892, "delta": 8, "note": "ce mois"},
    "available": {"value": 1246, "delta": 12, "note": "ce mois"},
    "busy": {"value": 428, "delta": 6, "note": "aujourd'hui"},
    "pending": {"value": 218, "delta": 15, "note": "ce mois"},
}

# Les 10 premieres lignes = celles de la maquette (source de verite visuelle).
_ADMIN_TECHS_DEMO_HEAD = [
    ("Moussa Bah", "Plombier", "Kaloum", "4.9", 128, "available", "active", "01/08/2026"),
    ("Aïssatou Diallo", "Électricienne", "Dixinn", "4.8", 114, "busy", "active", "28/07/2026"),
    ("Karim Soumah", "Frigoriste", "Ratoma", "4.7", 96, "available", "active", "25/07/2026"),
    ("Lansana Camara", "Menuisier", "Matam", "4.7", 87, "offline", "pending", "20/07/2026"),
    ("Mariama Kourouma", "Peintre", "Dixinn", "4.6", 75, "available", "active", "18/07/2026"),
    ("Alpha Diallo", "Climaticien", "Kaloum", "4.5", 62, "busy", "active", "15/07/2026"),
    ("Fatoumata Sylla", "Nettoyage", "Ratoma", "4.4", 48, "available", "active", "12/07/2026"),
    ("Ibrahima Bah", "Maçon", "Matam", "4.3", 39, "offline", "suspended", "10/07/2026"),
    ("Saran Keita", "Jardinier", "Kaloum", "4.2", 27, "available", "active", "05/07/2026"),
    ("Mamadou Kaba", "Menuisier", "Ratoma", "4.1", 22, "busy", "blocked", "01/07/2026"),
]


def _admin_tech_demo_row(i):
    """Un technicien de demo deterministe pour l'index 0-based i."""
    fn = _ADMIN_USERS_FIRST[i % len(_ADMIN_USERS_FIRST)]
    ln = _ADMIN_USERS_LAST[(i // len(_ADMIN_USERS_FIRST)) % len(_ADMIN_USERS_LAST)]
    n = i + 1
    avail = ("available", "available", "available", "available", "available",
             "available", "busy", "busy", "offline")[i % 9]
    if n % 9 == 4:
        status = "pending"
    elif n % 53 == 7:
        status = "suspended"
    elif n % 331 == 3:
        status = "blocked"
    else:
        status = "active"
    rating = round(3.6 + ((i * 7) % 14) / 10.0, 1)
    month = (i % 9) + 1
    day = (i % 27) + 1
    return {
        "code": "#TC-%04d" % (1000 + n),
        "name": "%s %s" % (fn, ln),
        "specialty": _ADMIN_TECHS_SPECIALTIES[(i * 5 + 2) % len(_ADMIN_TECHS_SPECIALTIES)],
        "phone": "+224 610 %02d %02d %02d" % (i % 100, (i * 3) % 100, (i * 7) % 100),
        "zone": _ADMIN_USERS_ZONES[i % len(_ADMIN_USERS_ZONES)],
        "rating": "%.1f" % rating,
        "missions": (i * 13) % 160,
        "availability": avail,
        "status": status,
        "joined": "%02d/%02d/2026" % (day, month),
        "photo": None,
    }


def _admin_techs_demo_all():
    rows = []
    for idx, (name, spec, zone, rating, miss, avail, status, joined) in enumerate(_ADMIN_TECHS_DEMO_HEAD):
        rows.append({
            "code": "#TC-%04d" % (1001 + idx), "name": name, "specialty": spec,
            "phone": "+224 620 10 00 %02d" % (idx + 1), "zone": zone,
            "rating": rating, "missions": miss, "availability": avail,
            "status": status, "joined": joined, "photo": None,
        })
    for i in range(len(_ADMIN_TECHS_DEMO_HEAD), _ADMIN_TECHS_DEMO_TOTAL):
        rows.append(_admin_tech_demo_row(i))

    extras = session.get("admin_techs_extra") or []
    rows = list(extras) + rows

    overrides = session.get("admin_techs_status") or {}
    if overrides:
        for r in rows:
            if r["code"] in overrides:
                r["status"] = overrides[r["code"]]
    return rows


def _admin_techs_real_rows():
    """Vraie table users (role technician) mappee au format de la page."""
    conn = get_db_connection()
    out = []
    try:
        cur = conn.execute(
            "SELECT id, full_name, phone, profession, city, quartier, account_status,"
            " verification_status, availability_status, is_active, created_at"
            " FROM users WHERE role = 'technician' ORDER BY created_at DESC")
        for r in cur.fetchall():
            vs = (r["verification_status"] or "").upper()
            st = (r["account_status"] or "").lower()
            if "block" in st:
                status = "blocked"
            elif "suspend" in st:
                status = "suspended"
            elif vs in ("PENDING_REVIEW", "PENDING", "") and not r["is_active"]:
                status = "pending"
            elif vs in ("PENDING_REVIEW", "PENDING"):
                status = "pending"
            else:
                status = "active"
            av = (r["availability_status"] or "").lower()
            availability = ("busy" if "route" in av or "mission" in av or "busy" in av
                            or "occup" in av else
                            "offline" if "indispo" in av or "offline" in av or "off" in av
                            else "available")
            rating, missions = 0.0, 0
            try:
                rr = conn.execute(
                    "SELECT COALESCE(AVG(rating),0) AS a, COUNT(*) AS n FROM reviews"
                    " WHERE artisan_id = ?", (r["id"],)).fetchone()
                rating = float(rr["a"] or 0)
                missions = int(conn.execute(
                    "SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?"
                    " AND LOWER(status) = 'completed'", (r["id"],)).fetchone()["n"] or 0)
            except Exception:
                conn.rollback()
            raw = str(r["created_at"] or "")[:10]
            joined = ("%s/%s/%s" % (raw[8:10], raw[5:7], raw[0:4])
                      if len(raw) == 10 and raw[4] == "-" else "")
            out.append({
                "code": "#TC-%04d" % (1000 + int(r["id"])),
                "name": r["full_name"] or "Technicien",
                "specialty": r["profession"] or "—",
                "phone": r["phone"] or "—",
                "zone": r["quartier"] or r["city"] or "—",
                "rating": "%.1f" % rating if rating else "—",
                "missions": missions, "availability": availability,
                "status": status, "joined": joined, "photo": None, "uid": int(r["id"]),
            })
    except Exception:
        conn.rollback()
    finally:
        conn.close()
    return out


def _admin_techs_filter(rows, q, specialty, status, availability, zone, note):
    q = (q or "").strip().lower()
    if q:
        rows = [r for r in rows if q in r["name"].lower() or q in r["phone"].lower()
                or q in r["code"].lower() or q in (r["specialty"] or "").lower()]
    if specialty:
        rows = [r for r in rows if (r["specialty"] or "").lower().startswith(specialty.lower()[:6])]
    if status in _ADMIN_TECHS_STATUS_LABELS:
        rows = [r for r in rows if r["status"] == status]
    if availability in _ADMIN_TECHS_AVAIL_LABELS:
        rows = [r for r in rows if r["availability"] == availability]
    if zone in _ADMIN_USERS_ZONES:
        rows = [r for r in rows if r["zone"] == zone]
    if note in ("4.5", "4.0", "3.5"):
        try:
            mn = float(note)
            rows = [r for r in rows if r["rating"] not in ("", "—") and float(r["rating"]) >= mn]
        except ValueError:
            pass
    return rows


def _admin_techs_query_args():
    return {
        "q": (request.args.get("q") or "").strip()[:80],
        "specialty": request.args.get("specialty") or "",
        "status": request.args.get("status") or "",
        "availability": request.args.get("availability") or "",
        "zone": request.args.get("zone") or "",
        "note": request.args.get("note") or "",
    }


@app.route("/admin/techniciens")
@app.route("/admin/technicians")
@login_required
@admin_required
def admin_technicians():
    """Page admin de gestion des techniciens (liste + filtres + pagination)."""
    user = get_current_user()
    now = datetime.now(timezone.utc)
    fa = _admin_techs_query_args()
    try:
        per_page = int(request.args.get("per_page") or 10)
    except (TypeError, ValueError):
        per_page = 10
    per_page = per_page if per_page in (10, 25, 50, 100) else 10
    try:
        page = max(1, int(request.args.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    demo = bool(app.config.get("ADMIN_TECHNICIANS_DEMO"))

    if demo:
        all_rows = _admin_techs_demo_all()
        kpis = {k: {"value": _fmt_int(v["value"]), "delta": v["delta"], "note": v["note"]}
                for k, v in _ADMIN_TECHS_KPIS.items()}
        headline_total = _ADMIN_TECHS_KPIS["total"]["value"]
    else:
        all_rows = _admin_techs_real_rows()
        n_total = len(all_rows)
        n_avail = sum(1 for r in all_rows if r["availability"] == "available")
        n_busy = sum(1 for r in all_rows if r["availability"] == "busy")
        n_pending = sum(1 for r in all_rows if r["status"] == "pending")
        kpis = {
            "total": {"value": _fmt_int(n_total), "delta": None, "note": ""},
            "available": {"value": _fmt_int(n_avail), "delta": None, "note": ""},
            "busy": {"value": _fmt_int(n_busy), "delta": None, "note": ""},
            "pending": {"value": _fmt_int(n_pending), "delta": None, "note": ""},
        }
        headline_total = n_total

    rows = _admin_techs_filter(all_rows, fa["q"], fa["specialty"], fa["status"],
                               fa["availability"], fa["zone"], fa["note"])
    total_filtered = len(rows)
    pages = max(1, -(-total_filtered // per_page))
    page = min(page, pages)
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]

    def _page_url(p):
        args = {"page": p, "per_page": per_page}
        args.update({k: v for k, v in fa.items() if v})
        return url_for("admin_technicians", **args)

    window = list(range(max(1, page - 2), min(pages, page + 2) + 1))

    ctx = {
        "admin_user": user, "current_year": now.year,
        "notif_count": 0, "header_notifs": [],
        "kpis": kpis, "techs": page_rows,
        "avail_labels": _ADMIN_TECHS_AVAIL_LABELS,
        "status_labels": _ADMIN_TECHS_STATUS_LABELS,
        "specialties": _ADMIN_TECHS_SPECIALTIES, "zones": _ADMIN_USERS_ZONES,
        "f": fa, "per_page": per_page, "page": page, "pages": pages,
        "page_window": window, "total_filtered": total_filtered,
        "headline_total": _fmt_int(headline_total),
        "prev_url": _page_url(page - 1) if page > 1 else None,
        "next_url": _page_url(page + 1) if page < pages else None,
        "page_url_tpl": _page_url("__P__"),
        "demo_mode": demo,
    }
    resp = make_response(render_template("admin_technicians.html", **ctx))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/admin/techniciens/export")
@login_required
@admin_required
def admin_technicians_export():
    fa = _admin_techs_query_args()
    rows = (_admin_techs_demo_all() if app.config.get("ADMIN_TECHNICIANS_DEMO")
            else _admin_techs_real_rows())
    rows = _admin_techs_filter(rows, fa["q"], fa["specialty"], fa["status"],
                               fa["availability"], fa["zone"], fa["note"])
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Identifiant", "Nom", "Specialite", "Telephone", "Zone", "Note",
                "Missions", "Disponibilite", "Statut", "Inscription"])
    for r in rows:
        w.writerow([r["code"], r["name"], r["specialty"], r["phone"], r["zone"],
                    r["rating"], r["missions"],
                    _ADMIN_TECHS_AVAIL_LABELS.get(r["availability"], r["availability"]),
                    _ADMIN_TECHS_STATUS_LABELS.get(r["status"], r["status"]), r["joined"]])
    out = make_response("﻿" + buf.getvalue())
    out.headers["Content-Type"] = "text/csv; charset=utf-8"
    out.headers["Content-Disposition"] = (
        "attachment; filename=fixpro-techniciens-%s.csv" % datetime.now().strftime("%Y%m%d"))
    return out


@app.route("/admin/techniciens/creer", methods=["POST"])
@login_required
@admin_required
def admin_technicians_create():
    if not app.config.get("ADMIN_TECHNICIANS_DEMO"):
        flash("La creation directe est desactivee hors mode demonstration.", "error")
        return redirect(url_for("admin_technicians"))
    first = (request.form.get("first_name") or "").strip()[:40]
    last = (request.form.get("last_name") or "").strip()[:40]
    phone = (request.form.get("phone") or "").strip()[:30]
    specialty = request.form.get("specialty") or ""
    zone = request.form.get("zone") or ""
    status = request.form.get("status") or "pending"
    if not first or not last or not phone:
        flash("Prénom, nom et téléphone sont obligatoires.", "error")
        return redirect(url_for("admin_technicians"))
    if specialty not in _ADMIN_TECHS_SPECIALTIES:
        specialty = _ADMIN_TECHS_SPECIALTIES[0]
    if zone not in _ADMIN_USERS_ZONES:
        zone = _ADMIN_USERS_ZONES[0]
    if status not in _ADMIN_TECHS_STATUS_LABELS:
        status = "pending"
    extras = session.get("admin_techs_extra") or []
    extras.insert(0, {
        "code": "#TC-%04d" % (9000 + len(extras) + 1),
        "name": "%s %s" % (first, last), "specialty": specialty,
        "phone": phone, "zone": zone, "rating": "—", "missions": 0,
        "availability": "offline", "status": status,
        "joined": datetime.now().strftime("%d/%m/2026"), "photo": None,
    })
    session["admin_techs_extra"] = extras[:50]
    session.modified = True
    flash("Technicien « %s %s » créé (données de démonstration)." % (first, last), "success")
    return redirect(url_for("admin_technicians"))


@app.route("/admin/techniciens/<code>/statut", methods=["POST"])
@login_required
@admin_required
def admin_technician_set_status(code):
    code = ("#" + code) if not code.startswith("#") else code
    new_status = request.form.get("status") or "suspended"
    if new_status not in _ADMIN_TECHS_STATUS_LABELS:
        new_status = "suspended"
    if app.config.get("ADMIN_TECHNICIANS_DEMO"):
        ov = session.get("admin_techs_status") or {}
        ov[code] = new_status
        session["admin_techs_status"] = ov
        session.modified = True
    else:
        try:
            uid = int(code.split("-")[-1].lstrip("0") or "0") - 1000
            conn = get_db_connection()
            conn.execute("UPDATE users SET account_status = ? WHERE id = ?", (new_status, uid))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("admin_technician_set_status: %s", exc)
    flash("Statut mis à jour : %s." % _ADMIN_TECHS_STATUS_LABELS[new_status], "success")
    return redirect(request.form.get("next") or url_for("admin_technicians"))


@app.route("/admin/techniciens/<code>")
@login_required
@admin_required
def admin_technician_detail(code):
    user = get_current_user()
    now = datetime.now(timezone.utc)
    code = ("#" + code) if not code.startswith("#") else code
    rows = (_admin_techs_demo_all() if app.config.get("ADMIN_TECHNICIANS_DEMO")
            else _admin_techs_real_rows())
    t = next((r for r in rows if r["code"] == code), None)
    if not t:
        flash("Technicien introuvable.", "error")
        return redirect(url_for("admin_technicians"))

    missions = t["missions"]
    done = int(round(missions * 0.88))
    prog = 1 if t["availability"] == "busy" else 0
    seed = sum(ord(c) for c in t["code"])
    clients = ["Aminata Diallo", "Mamadou Keita", "Sarah Camara", "Ibrahima Sylla",
               "Fatoumata Barry", "Karim Soumah"]
    pills = ["done", "done", "done", "prog", "canc"]
    labels = {"done": "Terminée", "prog": "En cours", "wait": "En attente", "canc": "Annulée"}
    history = []
    for k in range(min(missions, 6)):
        p = pills[(seed + k) % len(pills)]
        history.append({
            "code": "#FP-%d" % (3300 - seed % 80 - k),
            "client": clients[(seed + k) % len(clients)],
            "service": t["specialty"],
            "pill": p, "status_label": labels[p],
            "date": "%02d/%02d/2026" % (1 + (seed + k) % 27, 1 + (seed + k) % 9),
        })

    ctx = {
        "admin_user": user, "current_year": now.year,
        "notif_count": 0, "header_notifs": [],
        "t": t, "avail_labels": _ADMIN_TECHS_AVAIL_LABELS,
        "status_labels": _ADMIN_TECHS_STATUS_LABELS,
        "stats": {"missions": missions, "done": done, "prog": prog,
                  "rating": t["rating"]},
        "history": history,
        "demo_mode": bool(app.config.get("ADMIN_TECHNICIANS_DEMO")),
    }
    resp = make_response(render_template("admin_technician_detail.html", **ctx))
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _ts(value=None):
    """Horodatage 'YYYY-MM-DDTHH:MM:SS' sans fuseau ni microsecondes.

    Format accepte a la fois par PostgreSQL (cast vers timestamp) et par la
    comparaison lexicographique SQLite sur les colonnes TEXT."""
    if value is None:
        value = datetime.now(timezone.utc)
    if hasattr(value, "isoformat"):
        return value.replace(tzinfo=None, microsecond=0).isoformat()
    return str(value).replace(" ", "T")[:19]


def _expire_due_subscriptions(conn):
    """Passe les abonnements ACTIVE dont end_date est depassee en EXPIRED.

    Appele a l'ouverture du tableau de bord / de la page abonnements
    (pas de vrai cron en serverless)."""
    now_iso_ = _ts()
    try:
        conn.execute(
            "UPDATE technician_subscriptions SET status = 'EXPIRED'"
            " WHERE status = 'ACTIVE' AND end_date IS NOT NULL AND end_date < ?",
            (now_iso_,))
        conn.commit()
    except Exception as exc:
        logger.warning("Expiration abonnements impossible: %s", exc)
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
    back = url_for('admin_root')
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
            return redirect(url_for("index"))
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


_MOBILE_TOKEN_MAX_AGE = 7 * 24 * 60 * 60  # 7 jours
_mobile_serializer = URLSafeTimedSerializer(
    app.config.get("SECRET_KEY") or "fallback-secret",
    salt="technician-mobile")


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
            if _is_technician(user):
                return redirect(url_for("artisan_dashboard"))
            if user["role"] == "client":
                return redirect(url_for("artisans_page"))
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("requests_list"))

        # Message identique pour ne pas reveler quel identifiant existe.
        flash("Identifiants incorrects.", "error")

    return render_template("login.html", next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Espace connecte
# ---------------------------------------------------------------------------

def _client_dashboard_real_context(user):
    """Vrai contexte du tableau de bord client (demandes, paiements, technicien...)."""
    uid = user["id"] if user else 0
    now = datetime.now(timezone.utc)
    month_prefix = now.strftime("%Y-%m")
    empty = {
        "stats": {
            "requests": {"value": "0", "delta": "", "note": "", "trend": "flat"},
            "done": {"value": "0", "delta": "", "note": "", "trend": "flat"},
            "progress": {"value": "0", "delta": "", "note": "", "trend": "flat"},
            "spent": {"value": "0 GNF", "delta": "", "note": "", "trend": "flat"},
        },
        "recent_requests": [], "notifications": [], "my_tech": None,
        "my_address": None, "unread_count": 0,
    }
    if not uid:
        return empty

    conn = get_db_connection()
    try:
        def _n(sql, params=()):
            try:
                row = conn.execute(sql, params).fetchone()
                return int((row["n"] if row else 0) or 0)
            except Exception:
                conn.rollback()
                return 0

        total = _n("SELECT COUNT(*) AS n FROM requests WHERE client_id = ?", (uid,))
        month_new = _n("SELECT COUNT(*) AS n FROM requests WHERE client_id = ?"
                       " AND substr(created_at, 1, 7) = ?", (uid, month_prefix))
        buckets = {"done": 0, "prog": 0, "wait": 0, "canc": 0}
        try:
            for r in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM requests WHERE client_id = ?"
                    " GROUP BY status", (uid,)).fetchall():
                buckets[_adm_status_bucket(r["status"])] += int(r["n"] or 0)
        except Exception:
            conn.rollback()
        spent = _n("SELECT COALESCE(SUM(p.amount), 0) AS n FROM payments p"
                   " JOIN requests r ON r.id = p.request_id"
                   " WHERE r.client_id = ? AND LOWER(p.status) IN"
                   " ('paid', 'completed', 'succeeded')", (uid,))

        def _delta(cur):
            return ("+%d" % cur) if cur else "stable"

        stats = {
            "requests": {"value": _fmt_int(total), "delta": _delta(month_new),
                         "note": "ce mois" if month_new else "", "trend": "up" if month_new else "flat"},
            "done": {"value": _fmt_int(buckets["done"]), "delta": "", "note": "", "trend": "flat"},
            "progress": {"value": _fmt_int(buckets["prog"]), "delta": "stable" if not buckets["prog"] else "",
                         "note": "", "trend": "flat"},
            "spent": {"value": _fmt_int(spent) + " GNF", "delta": "", "note": "", "trend": "flat"},
        }

        recent_requests = []
        try:
            rows = conn.execute(
                "SELECT r.reference, r.service, r.category, r.status, r.created_at,"
                " u.full_name AS tech FROM requests r"
                " LEFT JOIN users u ON u.id = r.artisan_id"
                " WHERE r.client_id = ? ORDER BY r.created_at DESC LIMIT 5", (uid,)).fetchall()
        except Exception:
            conn.rollback()
            rows = []
        for r in rows:
            pill = _adm_status_bucket(r["status"])
            ref = r["reference"] or ""
            recent_requests.append({
                "code": ("#" + ref) if ref and not str(ref).startswith("#") else (ref or "—"),
                "service": r["service"] or r["category"] or "Service",
                "tech": r["tech"] or "—", "pill": pill,
                "status_label": _CLIENT_STATUS_LABELS[pill],
                "date": str(r["created_at"] or "")[:10],
            })

        my_tech = None
        try:
            t = conn.execute(
                "SELECT u.full_name, u.profession, u.phone, u.photo_url,"
                " COALESCE(AVG(rv.rating), 0) AS rating, COUNT(rv.id) AS reviews"
                " FROM requests r JOIN users u ON u.id = r.artisan_id"
                " LEFT JOIN reviews rv ON rv.artisan_id = u.id"
                " WHERE r.client_id = ? AND r.artisan_id IS NOT NULL"
                " GROUP BY u.id ORDER BY MAX(r.created_at) DESC LIMIT 1", (uid,)).fetchone()
            if t:
                my_tech = {
                    "name": t["full_name"] or "Technicien",
                    "job": t["profession"] or "Technicien",
                    "rating": "%.1f" % (t["rating"] or 0) if t["rating"] else "—",
                    "reviews": int(t["reviews"] or 0), "phone": t["phone"] or "",
                    "photo_url": t["photo_url"] or "",
                }
        except Exception:
            conn.rollback()

        notifications = []
        try:
            for row in conn.execute(
                    "SELECT title, type, created_at FROM notifications"
                    " WHERE user_id = ? ORDER BY created_at DESC LIMIT 4", (uid,)).fetchall():
                notifications.append({
                    "kind": _client_notif_kind(row["type"]),
                    "text": row["title"] or "Notification",
                    "ago": _adm_ago(row["created_at"]),
                })
        except Exception:
            conn.rollback()
        unread_count = _n("SELECT COUNT(*) AS n FROM notifications"
                          " WHERE user_id = ? AND is_read = 0", (uid,))

        return {
            "stats": stats, "recent_requests": recent_requests,
            "notifications": notifications, "my_tech": my_tech,
            "my_address": (user.get("quartier") or user.get("city")) if user else None,
            "unread_count": unread_count,
        }
    except Exception as exc:
        logger.exception("Erreur dashboard client: %s", exc)
        return empty
    finally:
        conn.close()


def _client_notif_kind(raw):
    s = (raw or "").lower()
    if "pay" in s:
        return "pay"
    if "message" in s or "chat" in s:
        return "msg"
    if "complete" in s or "termin" in s or "done" in s:
        return "success"
    return "tech"


@app.route("/dashboard")
def dashboard():
    user = get_current_user()
    if user and _is_technician(user):
        return redirect(url_for("artisan_dashboard"))

    now = datetime.now(timezone.utc)
    raw_name = (user.get("full_name") if user else None) or ""
    first_name = raw_name.split(" ")[0].strip()
    today_label = "%s %d %s %d" % (
        _ADM_DAYS_FR[now.weekday()].capitalize(), now.day,
        _ADM_MONTHS_FR[now.month].capitalize(), now.year)
    hero = url_for("static", filename="img/admin-login-hero.jpg",
                   v=_static_asset_version("img/admin-login-hero.jpg"))

    base_ctx = {
        "user": user, "client_first_name": first_name,
        "today_label": today_label, "hero_img": hero,
        "current_year": now.year, "services": _CLIENT_SERVICES,
        "demo_mode": bool(app.config.get("CLIENT_DASHBOARD_DEMO")),
    }
    # Adresse : geoloc de session (systeme FixPro) puis profil.
    zone = (session.get("client_zone")
            or ((user.get("quartier") or user.get("city")) if user else None))

    if app.config.get("CLIENT_DASHBOARD_DEMO"):
        ctx = _client_dashboard_demo_context()
        ident = ctx.pop("demo_identity", {})
        if not first_name:
            base_ctx["client_first_name"] = ident.get("first_name", "")
        base_ctx["display_name"] = (user.get("full_name") if user and user.get("full_name")
                                    else ident.get("full_name", "Mon compte"))
    else:
        ctx = _client_dashboard_real_context(user)
        base_ctx["display_name"] = (user.get("full_name")
                                    if user and user.get("full_name") else "Mon compte")
    if zone:
        ctx["my_address"] = zone
    base_ctx.update(ctx)

    resp = make_response(render_template("dashboard_client.html", **base_ctx))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/mobile_dashboard")
@login_required
def mobile_dashboard():
    return render_template("mobile_dashboard.html", user=get_current_user())


# ---------------------------------------------------------------------------
# Espace technicien
# ---------------------------------------------------------------------------

@app.route("/dashboard/technicien")
@app.route("/technician/dashboard")
@login_required
def artisan_dashboard():
    """Accueil de l'espace technicien : etat du compte, indicateurs du mois,
    prochaines demandes, profil et abonnement."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    now = datetime.now(timezone.utc)
    month_prefix = now.strftime("%Y-%m")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")

    conn = get_db_connection()
    try:
        def _scalar(sql, params=()):
            try:
                row = conn.execute(sql, params).fetchone()
                return (row["n"] if row else 0) or 0
            except Exception:
                conn.rollback()
                return 0

        demandes_semaine = _scalar(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND substr(created_at, 1, 10) >= ?",
            (user["id"], week_start))
        interventions_mois = _scalar(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND LOWER(status) = 'completed'"
            " AND substr(COALESCE(completed_at, updated_at, created_at), 1, 7) = ?",
            (user["id"], month_prefix))
        revenus_mois = _scalar(
            "SELECT COALESCE(SUM(COALESCE(professional_amount, final_price,"
            " quote_amount, 0)), 0) AS n FROM requests"
            " WHERE artisan_id = ? AND LOWER(status) = 'completed'"
            " AND substr(COALESCE(completed_at, updated_at, created_at), 1, 7) = ?",
            (user["id"], month_prefix))

        note_avg, reviews_count = 0, 0
        try:
            note_row = conn.execute(
                "SELECT ROUND(AVG(rating), 1) AS avg, COUNT(*) AS n FROM reviews"
                " WHERE artisan_id = ?", (user["id"],)).fetchone()
            if note_row and note_row["n"]:
                note_avg = note_row["avg"] or 0
                reviews_count = note_row["n"]
        except Exception:
            conn.rollback()

        upcoming = []
        try:
            upcoming = conn.execute(
                "SELECT r.id, r.title, r.category, r.service, r.status, r.address,"
                " r.requested_date, r.urgency, r.created_at,"
                " c.full_name AS client_name"
                " FROM requests r LEFT JOIN users c ON c.id = r.client_id"
                " WHERE r.artisan_id = ?"
                " AND LOWER(r.status) NOT IN ('completed', 'cancelled', 'refused', 'rejected')"
                " ORDER BY COALESCE(r.requested_date, r.created_at) ASC LIMIT 4",
                (user["id"],)).fetchall()
        except Exception:
            conn.rollback()

        sub = None
        try:
            sub = conn.execute(
                "SELECT s.status, s.end_date, s.auto_renew,"
                " p.name AS plan_name, p.price_month, p.currency"
                " FROM technician_subscriptions s"
                " LEFT JOIN subscription_plans p ON p.id = s.plan_id"
                " WHERE s.technician_id = ? ORDER BY s.created_at DESC LIMIT 1",
                (user["id"],)).fetchone()
        except Exception:
            conn.rollback()

        entitlements = get_technician_entitlements(conn, user["id"])
        request_usage = technician_request_usage(conn, user["id"])
    finally:
        conn.close()

    kpis = {
        "demandes": int(demandes_semaine),
        "interventions": int(interventions_mois),
        "revenus": int(revenus_mois),
        "note": note_avg,
        "reviews_count": int(reviews_count),
    }

    fields = {
        "photo": bool((user.get("photo_url") or "").strip()),
        "bio": bool((user.get("bio") or "").strip()),
        "profession": bool((user.get("profession") or "").strip()),
        "zone": bool((user.get("zone_intervention") or user.get("city") or "").strip()),
        "experience": bool(user.get("years_experience")),
    }
    profile_pct = int(round(sum(fields.values()) / len(fields) * 100))

    verifie = (user.get("verification_status") or "").upper() in (
        "APPROVED", "APPROUVE", "APPROUVÉ", "VERIFIED", "ACTIVE")

    # La carte "abonnement" du dashboard n'affiche un plan que pour un vrai
    # abonnement (ACTIVE / EXPIRED / PAST_DUE / CANCELLED). L'essai (TRIAL /
    # TRIAL_EXPIRED) est presente par un bloc dedie pilote par `entitlements`.
    subscription_view = None
    if sub and (sub["status"] or "").upper() not in ("TRIAL", "TRIAL_EXPIRED", ""):
        keys = sub.keys()
        price = sub["price_month"] if "price_month" in keys else None
        status = (sub["status"] or "").upper()
        subscription_view = {
            "plan_name": sub["plan_name"] or "Abonnement FixPro",
            "price_month": int(price) if price else None,
            "currency": (sub["currency"] if "currency" in keys and sub["currency"] else "GNF"),
            "active": entitlements["active"],
            "status_label": {"ACTIVE": "Actif", "PAST_DUE": "En attente",
                             "EXPIRED": "Expiré", "CANCELLED": "Annulé"}.get(status, sub["status"] or "—"),
            "end_date_label": _format_date_month_fr(sub["end_date"]) if sub["end_date"] else None,
            "badge": entitlements["badge"],
        }

    # Chiffres reels de la periode (essai comme abonnement).
    trial_stats = {
        "demandes": int(demandes_semaine),
        "interventions": int(interventions_mois),
        "avis": int(reviews_count),
    }

    return render_template(
        "dashboard_technicien.html", user=user, kpis=kpis,
        upcoming=[dict(r) for r in upcoming], profile_pct=profile_pct,
        verifie=verifie, subscription=subscription_view,
        entitlements=entitlements, request_usage=request_usage,
        trial_stats=trial_stats,
        availability=(user.get("availability_status") or "hors_ligne"))


@app.route("/api/technicien/status", methods=["POST"])
@login_required
def api_technicien_status():
    """Met a jour la disponibilite du technicien (toggle de l'accueil)."""
    user = get_current_user()
    if not _is_technician(user):
        return jsonify({"ok": False}), 403
    status = (request.form.get("status") or "").strip()
    if status not in ("en_ligne", "occupe", "hors_ligne"):
        return jsonify({"ok": False, "error": "statut invalide"}), 400
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET availability_status = ? WHERE id = ?",
                     (status, user["id"]))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "status": status})


csrf.exempt(api_technicien_status)


# Statuts (minuscule) consideres comme "demande acceptee" / "refusee" par le
# technicien. Sert au calcul du taux d'acceptation.
_REQ_ACCEPTED_STATES = ("accepted", "en_route", "on_the_way", "arrived",
                        "in_progress", "completed")
_REQ_REFUSED_STATES = ("refused", "rejected", "reassignment_required")


@app.route("/dashboard/technicien/statistiques")
@app.route("/statistiques")
@login_required
def technician_stats():
    """Statistiques detaillees (avantage Premium 'detailed_statistics').

    Controle SERVEUR : abonnement ACTIVE + droit detailed_statistics.
    Pro / sans abonnement -> page verrouillee proposant Premium (200),
    aucune donnee detaillee n'est calculee ni renvoyee.
    Toutes les metriques proviennent de donnees reelles (requests, reviews).
    Une metrique non calculable de facon fiable est marquee indisponible,
    jamais remplacee par un faux chiffre.
    """
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est réservé aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    try:
        ent = get_technician_entitlements(conn, user["id"])
        allowed = "detailed_statistics" in ent["entitlements"]

        if not allowed:
            return render_template(
                "technician_stats.html", user=user, allowed=False,
                entitlements=ent, stats=None,
                availability=(user.get("availability_status") or "hors_ligne"))

        tid = user["id"]

        def _one(sql, params=()):
            try:
                r = conn.execute(sql, params).fetchone()
                return (r["n"] if r else 0) or 0
            except Exception:
                conn.rollback()
                return 0

        acc_in = ",".join("'%s'" % s for s in _REQ_ACCEPTED_STATES)
        ref_in = ",".join("'%s'" % s for s in _REQ_REFUSED_STATES)

        recues = _one("SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?", (tid,))
        acceptees = _one(
            "SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?"
            " AND LOWER(status) IN (%s)" % acc_in, (tid,))
        refusees = _one(
            "SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?"
            " AND LOWER(status) IN (%s)" % ref_in, (tid,))
        terminees = _one(
            "SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?"
            " AND LOWER(status) = 'completed'", (tid,))
        revenus = _one(
            "SELECT COALESCE(SUM(COALESCE(professional_amount, final_price,"
            " quote_amount, 0)), 0) AS n FROM requests WHERE artisan_id = ?"
            " AND LOWER(status) = 'completed'", (tid,))

        traitees = acceptees + refusees
        taux_acceptation = round(acceptees * 100 / traitees) if traitees else None
        taux_completion = round(terminees * 100 / acceptees) if acceptees else None

        note_avg, avis_n = None, 0
        try:
            nr = conn.execute(
                "SELECT ROUND(AVG(rating), 1) AS a, COUNT(*) AS n FROM reviews"
                " WHERE artisan_id = ?", (tid,)).fetchone()
            if nr and nr["n"]:
                note_avg, avis_n = nr["a"], nr["n"]
        except Exception:
            conn.rollback()

        # Evolution : 6 derniers mois (demandes recues + interventions terminees).
        months = []
        now = datetime.now(timezone.utc)
        for i in range(5, -1, -1):
            y = now.year
            m = now.month - i
            while m <= 0:
                m += 12
                y -= 1
            key = "%04d-%02d" % (y, m)
            recv = _one(
                "SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?"
                " AND substr(created_at, 1, 7) = ?", (tid, key))
            done = _one(
                "SELECT COUNT(*) AS n FROM requests WHERE artisan_id = ?"
                " AND LOWER(status) = 'completed'"
                " AND substr(COALESCE(completed_at, updated_at, created_at), 1, 7) = ?",
                (tid, key))
            months.append({
                "label": ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil",
                          "Août", "Sep", "Oct", "Nov", "Déc"][m - 1],
                "received": recv, "completed": done,
            })
        months_max = max([mo["received"] for mo in months] + [1])

        recent = []
        try:
            recent = conn.execute(
                "SELECT r.title, r.status, r.created_at, r.category"
                " FROM requests r WHERE r.artisan_id = ?"
                " ORDER BY r.created_at DESC LIMIT 8", (tid,)).fetchall()
        except Exception:
            conn.rollback()

        stats = {
            "recues": recues,
            "acceptees": acceptees,
            "refusees": refusees,
            "terminees": terminees,
            "revenus": int(revenus),
            "taux_acceptation": taux_acceptation,
            "taux_completion": taux_completion,
            "note_avg": note_avg,
            "avis_n": avis_n,
            "months": months,
            "months_max": months_max,
            "recent": [dict(r) for r in recent],
            # Metrique non suivie en base : aucune table de vues de profil.
            "conversion_available": False,
        }
    finally:
        conn.close()

    return render_template(
        "technician_stats.html", user=user, allowed=True,
        entitlements=ent, stats=stats,
        availability=(user.get("availability_status") or "hors_ligne"))


_REQUEST_CATEGORY_KEYS = {
    "plomb": "plomberie", "fuite": "plomberie", "chauffe-eau": "plomberie",
    "electr": "electricite", "élect": "electricite", "prise": "electricite",
    "clim": "climatisation", "frigo": "climatisation", "froid": "climatisation",
    "menuis": "menuiserie", "bois": "menuiserie", "porte": "menuiserie",
    "peint": "peinture",
    "macon": "maconnerie", "maçon": "maconnerie", "mur": "maconnerie",
    "electromenager": "electromenager", "électroménager": "electromenager",
    "machine": "electromenager", "lave": "electromenager",
    "serrur": "serrurerie",
}


def _request_category_key(*values):
    """Normalise categorie/service d'une demande en une cle d'icone connue."""
    blob = " ".join(str(v or "") for v in values).lower()
    for needle, key in _REQUEST_CATEGORY_KEYS.items():
        if needle in blob:
            return key
    return "autre"


@app.route("/dashboard/technicien/demandes")
@app.route("/demandes-recues")
@login_required
def technician_requests():
    """Demandes recues par le technicien : liste des demandes clients qui lui
    sont attribuees et encore ouvertes (a traiter). Filtres Toutes /
    Aujourd'hui / Cette semaine. Donnees reelles uniquement."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est réservé aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    flt = (request.args.get("f") or "all").lower()
    if flt not in ("all", "today", "week"):
        flt = "all"

    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT r.id, r.title, r.description, r.category, r.service, r.status,"
            " r.address, r.latitude, r.longitude, r.created_at, r.urgency,"
            " r.phone_contact, c.full_name AS client_name, c.phone AS client_phone"
            " FROM requests r JOIN users c ON c.id = r.client_id"
            " WHERE r.artisan_id = ?"
            "   AND LOWER(r.status) NOT IN"
            "       ('completed', 'cancelled', 'refused', 'rejected', 'reassignment_required')"
            " ORDER BY r.created_at DESC LIMIT 80",
            (user["id"],)).fetchall()
        entitlements = get_technician_entitlements(conn, user["id"])
        unread_count = 0
        try:
            unread_count = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                (user["id"],)).fetchone()["n"]
        except Exception:
            conn.rollback()
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    tlat, tlon = _to_float(user.get("latitude")), _to_float(user.get("longitude"))

    items, n_today, n_week = [], 0, 0
    for r in rows:
        created_s = str(r["created_at"] or "")[:19].replace("T", " ")
        cd = created_s[:10]
        is_today = bool(cd) and cd == today
        is_week = bool(cd) and cd >= week_start
        if is_today:
            n_today += 1
        if is_week:
            n_week += 1

        mins = None
        try:
            ct = datetime.strptime(created_s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            mins = (now - ct).total_seconds() / 60
        except (ValueError, TypeError):
            pass

        if flt == "today" and not is_today:
            continue
        if flt == "week" and not is_week:
            continue

        d = dict(r)
        d["ago"] = _format_time_ago(r["created_at"])
        if mins is not None and mins < 60:
            d["bucket"], d["bucket_label"] = "new", "Nouvelle"
        elif is_today:
            d["bucket"], d["bucket_label"] = "today", "Aujourd'hui"
        else:
            d["bucket"], d["bucket_label"] = "week", "Cette semaine"
        d["distance_km"] = None
        if tlat and tlon and _is_valid_coordinate(r["latitude"], r["longitude"]):
            d["distance_km"] = round(
                _haversine(tlat, tlon, float(r["latitude"]), float(r["longitude"])), 1)
        d["cat_key"] = _request_category_key(r["category"], r["service"], r["title"])
        d["cat_label"] = (r["service"] or r["category"] or "Intervention").strip()
        d["call_phone"] = (r["phone_contact"] or r["client_phone"] or "").strip()
        d["summary"] = (r["description"] or r["title"] or "").strip().split("\n")[0]
        items.append(d)

    counts = {"all": len(rows), "today": n_today, "week": n_week}
    return render_template(
        "technician_requests.html", user=user, items=items, counts=counts,
        active_filter=flt, entitlements=entitlements, unread_count=unread_count,
        availability=(user.get("availability_status") or "hors_ligne"))


# --- Abonnement technicien -------------------------------------------------

_TECH_PLANS = [
    {
        "code": "tech_pro", "name": "Pro", "icon": "star", "popular": False, "accent": "blue",
        "desc": "Idéal pour développer votre activité",
        "price_ref_month": 100000, "price_month": 97000,
        "price_ref_year": 1200000, "price_year": 931200,
        "features": [
            ("Jusqu'à 30 demandes reçues par mois", True),
            ("Visibilité dans les recherches", True),
            ("Badge profil vérifié", True),
            ("Statistiques de base", True),
            ("Support en temps réel", True),
        ],
    },
    {
        "code": "tech_premium", "name": "Premium", "icon": "crown", "popular": True, "accent": "amber",
        "desc": "Pour les professionnels les plus actifs",
        "price_ref_month": 200000, "price_month": 140000,
        "price_ref_year": 2400000, "price_year": 1344000,
        "features": [
            ("Toutes les fonctionnalités Pro", True),
            ("Demandes illimitées", True),
            ("Visibilité prioritaire", True),
            ("Mise en avant de votre profil", True),
            ("Statistiques détaillées", True),
            ("Support client prioritaire", True),
            ("Plus d'opportunités d'interventions", True),
        ],
    },
]

_SUB_PAYMENT_METHODS = [
    {"code": "orange_money", "label": "Orange Money", "brand": "orange",
     "desc": "Payez facilement et en toute sécurité avec Orange Money"},
    {"code": "mtn_mobile_money", "label": "MTN Mobile Money", "brand": "mtn",
     "desc": "Payez facilement et en toute sécurité avec MTN Mobile Money"},
    {"code": "unitrade", "label": "Unitrade", "brand": "unitrade",
     "desc": "Payez avec votre compte Unitrade"},
    {"code": "card", "label": "Carte bancaire", "brand": "card",
     "desc": "Visa, Mastercard ou autres cartes"},
]
_SUB_PAYMENT_CODES = {m["code"] for m in _SUB_PAYMENT_METHODS}

# Arguments de vente de l'abonnement (identiques quel que soit le plan).
_SUB_VALUE_PROPS = [
    ("Plus de visibilité", "Soyez vu en premier"),
    ("Plus de clients", "Recevez plus de demandes"),
    ("Plus de revenus", "Développez votre activité"),
]

# ---------------------------------------------------------------------------
# Machine a etats des paiements d'abonnement.
#
# REGLE ABSOLUE : un abonnement ne devient ACTIVE que lorsqu'un paiement
# passe a l'etat PAYMENT_CONFIRMED, et cette transition ne peut venir QUE
# d'une source serveur fiable :
#   - le webhook prestataire signe  (payment_webhook)
#   - une confirmation manuelle admin (admin_subscription_payment_update)
# Le clic "Payer" cree seulement une TENTATIVE (PENDING) : il n'active rien.
# ---------------------------------------------------------------------------

# Valeur stockee en base (compat admin historique)  <->  etat logique expose.
_PAY_STATE = {
    "pending": "PENDING",
    "processing": "PROCESSING",
    "paid": "PAYMENT_CONFIRMED",
    "failed": "PAYMENT_FAILED",
    "cancelled": "PAYMENT_CANCELLED",
    "expired": "PAYMENT_EXPIRED",
}
_PAY_OPEN = ("pending", "processing")            # en attente de confirmation
_PAY_FINAL = ("paid", "failed", "cancelled", "expired")
_PAY_ATTEMPT_TTL_MIN = 30                        # au-dela : PAYMENT_EXPIRED
_SUB_METHOD_LABEL = {m["code"]: m["label"] for m in _SUB_PAYMENT_METHODS}


def _sub_payment_by_ref(conn, ref, user_id=None):
    sql = "SELECT * FROM subscription_payments WHERE transaction_reference = ?"
    params = [ref]
    if user_id is not None:
        sql += " AND user_id = ?"
        params.append(user_id)
    return conn.execute(sql + " ORDER BY id DESC LIMIT 1", params).fetchone()


def _sub_payment_expire_stale(conn, payment):
    """Passe une tentative ouverte trop ancienne en 'expired'.
    Renvoie le statut (base, minuscule) eventuellement mis a jour."""
    st = (payment["status"] or "").lower()
    if st not in _PAY_OPEN:
        return st
    try:
        created = datetime.strptime(
            str(payment["created_at"]).replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
        created = created.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return st
    if datetime.now(timezone.utc) - created > timedelta(minutes=_PAY_ATTEMPT_TTL_MIN):
        conn.execute("UPDATE subscription_payments SET status = 'expired' WHERE id = ?",
                     (payment["id"],))
        conn.commit()
        return "expired"
    return st


def _activate_subscription_from_payment(conn, payment_id):
    """SEUL point d'activation d'un abonnement technicien.
    Transactionnel + idempotent. Refuse d'agir si le paiement n'est pas
    a l'etat 'paid'. N'active jamais deux fois le meme paiement."""
    pay = conn.execute("SELECT * FROM subscription_payments WHERE id = ?",
                       (payment_id,)).fetchone()
    if not pay or (pay["status"] or "").lower() != "paid":
        return False

    now = datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%d %H:%M:%S")
    end_s = (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    sub = None
    if pay["subscription_id"]:
        sub = conn.execute("SELECT * FROM technician_subscriptions WHERE id = ?",
                           (pay["subscription_id"],)).fetchone()
    if sub is None:
        sub = conn.execute(
            "SELECT * FROM technician_subscriptions WHERE technician_id = ?"
            " ORDER BY created_at DESC LIMIT 1", (pay["user_id"],)).fetchone()

    # Idempotence : ce paiement a deja active cet abonnement -> ne rien refaire.
    if (pay["paid_at"] and sub and (sub["status"] or "").upper() == "ACTIVE"
            and sub["plan_id"] == pay["plan_id"]):
        return True

    if sub:
        conn.execute(
            "UPDATE technician_subscriptions SET plan_id = ?, status = 'ACTIVE',"
            " start_date = ?, end_date = ?, auto_renew = 1, updated_at = CURRENT_TIMESTAMP"
            " WHERE id = ?",
            (pay["plan_id"], now_s, end_s, sub["id"]))
        sub_id = sub["id"]
    else:
        sub_id = _insert_id(
            conn,
            "INSERT INTO technician_subscriptions"
            " (technician_id, plan_id, status, start_date, end_date, auto_renew)"
            " VALUES (?, ?, 'ACTIVE', ?, ?, 1)",
            (pay["user_id"], pay["plan_id"], now_s, end_s))

    conn.execute(
        "UPDATE subscription_payments SET paid_at = ?, subscription_id = ?,"
        " period_start = ?, period_end = ? WHERE id = ?",
        (now_s, sub_id, now_s, end_s, payment_id))
    conn.commit()

    try:
        create_notification(
            pay["user_id"], "Abonnement activé",
            "Votre paiement a été confirmé. Votre abonnement est actif jusqu'au %s."
            % _format_date_month_fr(end_s),
            "success", data="abonnement", conn=conn)
        conn.commit()
    except Exception:
        conn.rollback()
    return True


def _fail_subscription_payment(conn, payment_id, new_status="failed"):
    """Passe une tentative OUVERTE en echec / annulee / expiree.
    Ne touche jamais un paiement deja confirme. L'abonnement reste inactif."""
    if new_status not in ("failed", "cancelled", "expired"):
        return False
    row = conn.execute("SELECT status FROM subscription_payments WHERE id = ?",
                       (payment_id,)).fetchone()
    if not row or (row["status"] or "").lower() not in _PAY_OPEN:
        return False
    conn.execute("UPDATE subscription_payments SET status = ? WHERE id = ?",
                 (new_status, payment_id))
    conn.commit()
    return True


def _tech_plan_by_code(code):
    for p in _TECH_PLANS:
        if p["code"] == code:
            return p
    return None


def _tech_plan_amount(plan, period):
    """Montant a payer selon la periode ('month' ou 'year')."""
    if period == "year":
        return int(plan["price_year"])
    return int(plan["price_month"])


def _tech_plan_discount_pct(plan, period="month"):
    """Remise affichee (prix barre -> prix actuel) pour une periode donnee."""
    if period == "year":
        ref, now = plan.get("price_ref_year", 0), plan.get("price_year", 0)
    else:
        ref, now = plan.get("price_ref_month", 0), plan.get("price_month", 0)
    if ref <= 0 or now <= 0 or now >= ref:
        return 0
    return int(round((1 - now / ref) * 100))


def _tech_plan_year_savings_pct(plan):
    """Economie de l'engagement annuel par rapport a 12 mensualites."""
    full = plan.get("price_month", 0) * 12
    year = plan.get("price_year", 0)
    if full <= 0 or year <= 0 or year >= full:
        return 0
    return int(round((1 - year / full) * 100))


def _ensure_tech_plan_row(conn, code):
    """Cree/actualise la ligne subscription_plans correspondant a un plan technicien."""
    plan = _tech_plan_by_code(code)
    if not plan:
        return None
    feats = "\n".join(label for label, included in plan["features"] if included)
    row = conn.execute("SELECT id FROM subscription_plans WHERE code = ?", (code,)).fetchone()
    if row:
        conn.execute(
            "UPDATE subscription_plans SET name = ?, price_month = ?, features = ?, is_active = 1"
            " WHERE id = ?",
            (plan["name"], plan["price_month"], feats, row["id"]))
        return row["id"]
    order = {"tech_pro": 11, "tech_premium": 12}.get(code, 13)
    conn.execute(
        "INSERT INTO subscription_plans (code, name, price_month, features, is_active, sort_order)"
        " VALUES (?, ?, ?, ?, 1, ?)",
        (code, plan["name"], plan["price_month"], feats, order))
    got = conn.execute("SELECT id FROM subscription_plans WHERE code = ?", (code,)).fetchone()
    return got["id"] if got else None


# ---------------------------------------------------------------------------
# SOURCE CENTRALE DES DROITS D'ABONNEMENT (entitlements).
#
# Une seule definition, utilisee a la fois par le backend (controle d'acces,
# classement des recherches) et par l'UI (page "Mon abonnement", dashboard,
# fiche client). On ne met JAMAIS de `if plan == "premium"` ailleurs :
# on appelle get_technician_entitlements() / technician_has_entitlement().
#
# Un droit n'est accorde QUE si l'abonnement du technicien est ACTIVE et que
# le droit appartient au plan actif. PENDING / PAST_DUE / EXPIRED / CANCELLED
# / FAILED -> aucun droit. (Le fait d'avoir choisi Premium ne donne rien :
# le paiement doit etre confirme et l'abonnement passe a ACTIVE.)
# ---------------------------------------------------------------------------

# REGLE PRODUIT OFFICIELLE (2026-09-09) : nombre de demandes recues / mois.
#   PRO     -> 30 maximum
#   PREMIUM -> illimite (None)
# SOURCE DE VERITE UNIQUE. Le libelle affiche ("Jusqu'a 30 demandes...") et
# le controle serveur (technician_request_usage) en decoulent tous les deux.
_PRO_MONTHLY_REQUEST_LIMIT = 30
_PLAN_MONTHLY_REQUEST_LIMIT = {
    "tech_pro": _PRO_MONTHLY_REQUEST_LIMIT,
    "tech_premium": None,          # None = illimite
}

# ---------------------------------------------------------------------------
# PERIODE D'ESSAI GRATUIT (14 jours) - REGLE PRODUIT OFFICIELLE 2026-09-09.
#
#   TECHNICIEN APPROUVE  ->  14 jours d'essai (visible + recoit des demandes)
#   FIN DES 14 JOURS     ->  abonnement requis pour continuer
#
# Le trial reutilise la table technician_subscriptions (AUCUNE table en plus,
# AUCUNE migration) :
#   status = 'TRIAL'          -> essai en cours   (plan_id NULL)
#   status = 'TRIAL_EXPIRED'  -> essai termine    (plan_id NULL)
#   status = 'ACTIVE'         -> abonnement paye  (prend le relais)
#
# UNE SEULE FOIS : l'essai n'est cree que si le technicien n'a AUCUNE ligne
# technician_subscriptions. Une fois cree, il passe TRIAL -> TRIAL_EXPIRED
# (ou -> ACTIVE si paiement), jamais de nouveau TRIAL.
# ---------------------------------------------------------------------------
_TRIAL_DAYS = 14

# Droits accordes pendant l'essai (decouverte intensive). Pas de quota.
_TRIAL_ENTITLEMENTS = {
    "receive_requests",
    "unlimited_requests",       # pas de plafond pendant la decouverte
    "search_visibility",
    "verified_badge",
    "basic_statistics",
    "realtime_support",
    "trial_visibility_boost",   # coup de pouce de visibilite temporaire
}

# Droits communs a tout plan actif (Pro inclut deja "toutes les fonctions Pro"
# et Premium "toutes les fonctionnalites Pro").
_PLAN_ENTITLEMENTS = {
    "tech_pro": {
        "receive_requests",       # apparait dans la recherche client
        "monthly_request_quota",  # "Jusqu'a 30 demandes recues / mois"
        "search_visibility",      # "Visibilite dans les recherches"
        "verified_badge",         # "Badge profil verifie"
        "basic_statistics",       # "Statistiques de base"
        "realtime_support",       # "Support en temps reel"
    },
    "tech_premium": {
        "receive_requests",
        "unlimited_requests",     # "Demandes illimitees"
        "search_visibility",
        "verified_badge",
        "basic_statistics",
        "realtime_support",
        "priority_visibility",    # "Visibilite prioritaire" (bonus de classement)
        "featured_profile",       # "Mise en avant de votre profil"
        "detailed_statistics",    # "Statistiques detaillees"
        "priority_support",       # "Support client prioritaire"
        "more_opportunities",     # "Plus d'opportunites d'interventions"
    },
}

# HISTORIQUE - NON UTILISE. FixPro fonctionne uniquement par ABONNEMENT :
# aucune commission n'est prelevee ni affichee comme avantage d'un plan.
# Ce dict est conserve sans etre lu par la couche entitlements (audit requis
# avant suppression : d'autres modules "payments"/"admin_commissions" heritent
# encore de l'ancien modele client-paie-par-intervention).
_PLAN_COMMISSION_DISCOUNT = {"tech_pro": 10, "tech_premium": 20}  # deprecated

# Libelles affichables des droits (UI = meme source que le backend).
_ENTITLEMENT_LABELS = {
    "receive_requests": "Recevez les demandes des clients de votre zone",
    "monthly_request_quota": "Jusqu'à %d demandes reçues par mois" % _PRO_MONTHLY_REQUEST_LIMIT,
    "unlimited_requests": "Demandes illimitées",
    "search_visibility": "Visibilité dans les recherches",
    "verified_badge": "Badge profil vérifié",
    "basic_statistics": "Statistiques de base",
    "realtime_support": "Support en temps réel",
    "priority_visibility": "Visibilité prioritaire dans les recherches",
    "featured_profile": "Profil mis en avant",
    "detailed_statistics": "Statistiques détaillées",
    "priority_support": "Support client prioritaire",
    "more_opportunities": "Plus d'opportunités d'interventions",
    "trial_visibility_boost": "Visibilité renforcée pendant la découverte",
}

# Badge affiche (profil, dashboard, fiche client) selon le plan actif.
_PLAN_BADGE = {
    "tech_pro": {"label": "Pro", "icon": "star", "accent": "blue"},
    "tech_premium": {"label": "Premium", "icon": "crown", "accent": "amber"},
}


def get_subscription_badge(plan_code):
    """Badge d'un plan (ou None). Pur mapping, aucun acces base.
    Aucun badge pendant l'essai : le badge Pro/Premium n'apparait que si le
    technicien a REELLEMENT souscrit et que l'abonnement est ACTIVE."""
    return _PLAN_BADGE.get(plan_code)


def _technician_is_approved(conn, technician_id):
    """Technicien "valide" = is_verified = 1 (drapeau pose par l'admin a la
    validation du dossier, en meme temps que verification_status='APPROVED').
    C'est aussi la porte d'entree de _match_technicians -> coherent."""
    row = conn.execute(
        "SELECT is_verified FROM users"
        " WHERE id = ? AND role = 'technician'", (technician_id,)).fetchone()
    return bool(row) and int(row["is_verified"] or 0) == 1


def _ensure_technician_trial(conn, technician_id):
    """Demarre l'essai de 14 jours UNE SEULE FOIS.

    Conditions : technicien valide (is_verified=1) ET aucune ligne
    technician_subscriptions. Idempotent : si une ligne existe deja (TRIAL,
    TRIAL_EXPIRED, ACTIVE, EXPIRED, ...), on ne touche a rien -> pas de
    second essai possible. Dates serveur.
    """
    try:
        if not _technician_is_approved(conn, technician_id):
            return
        existing = conn.execute(
            "SELECT 1 FROM technician_subscriptions WHERE technician_id = ? LIMIT 1",
            (technician_id,)).fetchone()
        if existing:
            return
        now = datetime.now(timezone.utc)
        conn.execute(
            "INSERT INTO technician_subscriptions"
            " (technician_id, plan_id, status, start_date, end_date, auto_renew)"
            " VALUES (?, NULL, 'TRIAL', ?, ?, 0)",
            (technician_id,
             now.strftime("%Y-%m-%d %H:%M:%S"),
             (now + timedelta(days=_TRIAL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("Creation essai technicien %s impossible: %s", technician_id, exc)


def _ensure_trials_for_verified(conn):
    """Demarre l'essai de tous les techniciens approuves qui n'en ont pas
    encore (un seul INSERT ... SELECT, idempotent via NOT EXISTS). Appele
    en tete de _match_technicians pour que la recherche voie l'essai des
    profils fraichement valides."""
    try:
        now = datetime.now(timezone.utc)
        conn.execute(
            "INSERT INTO technician_subscriptions"
            " (technician_id, plan_id, status, start_date, end_date, auto_renew)"
            " SELECT u.id, NULL, 'TRIAL', ?, ?, 0 FROM users u"
            " WHERE u.role = 'technician' AND u.is_verified = 1"
            "   AND NOT EXISTS (SELECT 1 FROM technician_subscriptions t"
            "                   WHERE t.technician_id = u.id)",
            (now.strftime("%Y-%m-%d %H:%M:%S"),
             (now + timedelta(days=_TRIAL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("Creation essais en lot impossible: %s", exc)


def _expire_due_trials(conn):
    """TRIAL dont end_date est depassee -> TRIAL_EXPIRED.
    (Pas de vrai cron en serverless : appele a l'ouverture du dashboard et
    dans le calcul des droits.)"""
    try:
        conn.execute(
            "UPDATE technician_subscriptions SET status = 'TRIAL_EXPIRED',"
            " updated_at = CURRENT_TIMESTAMP"
            " WHERE status = 'TRIAL' AND end_date IS NOT NULL AND end_date < ?",
            (_ts(),))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("Expiration essais impossible: %s", exc)


def _trial_days_left(end_date):
    """Jours entiers restants avant end_date (>= 0, jamais negatif)."""
    if not end_date:
        return 0
    try:
        end = datetime.strptime(str(end_date).replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
        end = end.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return 0
    delta = end - datetime.now(timezone.utc)
    if delta.total_seconds() <= 0:
        return 0
    # arrondi au jour superieur : il reste "1 jour" tant qu'il reste des heures
    return max(0, int(-(-delta.total_seconds() // 86400)))


def get_technician_entitlements(conn, technician_id):
    """Contexte complet des droits d'un technicien, calcule depuis la base.

    SOURCE UNIQUE DE VERITE. Enchaine : demarrage de l'essai si besoin ->
    expiration paresseuse des abonnements -> expiration paresseuse des essais
    -> lecture de la derniere ligne technician_subscriptions.

    Priorite (cf. regle produit) :
        abonnement ACTIVE  >  essai en cours  >  rien
    Un abonnement ACTIVE prend toujours le pas sur l'essai.

    Renvoie un dict :
      has_subscription : une ligne technician_subscriptions existe (essai inclus)
      active           : abonnement PAYE et ACTIVE (non expire)
      trial_active     : essai en cours (TRIAL, non expire)
      eligible         : peut recevoir des demandes / etre montre aux clients
                         = active OR trial_active
      status           : ACTIVE / TRIAL / TRIAL_EXPIRED / EXPIRED / PAST_DUE / ...
      plan_code        : plan actif ('tech_pro'/'tech_premium') ou None
      plan_name        : nom du plan actif ou None
      end_date         : echeance de l'abonnement actif ou None
      trial_end        : fin de l'essai en cours ou None
      trial_days_left  : jours entiers restants d'essai (>= 0)
      entitlements     : set() des droits reellement accordes
      badge            : {label, icon, accent} ou None (JAMAIS pendant l'essai)
    """
    _ensure_technician_trial(conn, technician_id)
    try:
        _expire_due_subscriptions(conn)
    except Exception:
        pass
    try:
        _expire_due_trials(conn)
    except Exception:
        pass

    row = None
    try:
        row = conn.execute(
            "SELECT s.status, s.end_date, p.code AS plan_code, p.name AS plan_name"
            " FROM technician_subscriptions s"
            " LEFT JOIN subscription_plans p ON p.id = s.plan_id"
            " WHERE s.technician_id = ?"
            " ORDER BY s.created_at DESC, s.id DESC LIMIT 1",
            (technician_id,)).fetchone()
    except Exception:
        conn.rollback()

    status = (row["status"] or "").upper() if row and row["status"] else None
    plan_code = row["plan_code"] if row else None

    sub_active = status == "ACTIVE" and plan_code in _PLAN_ENTITLEMENTS
    trial_active = status == "TRIAL"        # les TRIAL perimes ont deja bascule

    if sub_active:
        ents = set(_PLAN_ENTITLEMENTS[plan_code])
    elif trial_active:
        ents = set(_TRIAL_ENTITLEMENTS)
    else:
        ents = set()

    trial_end = row["end_date"] if (row and trial_active) else None

    return {
        "has_subscription": bool(row),
        "active": sub_active,
        "trial_active": trial_active,
        "eligible": sub_active or trial_active,
        "status": status,
        "plan_code": plan_code if sub_active else None,
        "plan_name": (row["plan_name"] if row else None) if sub_active else None,
        "end_date": row["end_date"] if (row and sub_active) else None,
        "trial_end": trial_end,
        "trial_days_left": _trial_days_left(trial_end) if trial_active else 0,
        "entitlements": ents,
        "badge": get_subscription_badge(plan_code) if sub_active else None,
    }


def technician_has_entitlement(conn, technician_id, key):
    """True si le technicien beneficie du droit `key` (abonnement ACTIVE ou
    essai en cours). A utiliser cote serveur avant toute fonctionnalite reservee."""
    return key in get_technician_entitlements(conn, technician_id)["entitlements"]


def entitlement_labels(entitlements):
    """Libelles UI d'un ensemble de droits, dans l'ordre de reference."""
    return [(_ENTITLEMENT_LABELS[k], k) for k in _ENTITLEMENT_LABELS if k in entitlements]


# ---------------------------------------------------------------------------
# QUOTA MENSUEL DE DEMANDES (moteur serveur).
#
# Une "demande recue" dans FixPro = une ligne `requests` attribuee au
# technicien (colonne artisan_id), quel que soit le statut ensuite. C'est
# l'evenement d'attribution (request_new / demande directe / chat Lia) qui
# compte, sur le mois calendaire courant (substr(created_at, 1, 7)).
#
# La limite vient de _PLAN_MONTHLY_REQUEST_LIMIT (defini plus haut, source
# unique) : PRO = 30, PREMIUM = None (illimite). Elle ne s'applique qu'a un
# abonnement ACTIVE.
# ---------------------------------------------------------------------------


def technician_request_usage(conn, technician_id, month=None):
    """Consommation mensuelle de demandes du technicien (calcul serveur).

    Renvoie {month, used, limit, unlimited, remaining, plan_code, over_limit}.
    `limit` vient du plan ACTIF uniquement (aucun plan actif -> illimite,
    on n'invente pas de plafond pour les non-abonnes).
    """
    ent = get_technician_entitlements(conn, technician_id)
    plan_code = ent["plan_code"]
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    used = 0
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM requests"
            " WHERE artisan_id = ? AND substr(created_at, 1, 7) = ?",
            (technician_id, month)).fetchone()
        used = (row["n"] if row else 0) or 0
    except Exception:
        conn.rollback()
    limit = _PLAN_MONTHLY_REQUEST_LIMIT.get(plan_code) if ent["active"] else None
    unlimited = limit is None
    return {
        "month": month,
        "used": int(used),
        "limit": limit,
        "unlimited": unlimited,
        "remaining": None if unlimited else max(0, limit - int(used)),
        "plan_code": plan_code,
        "over_limit": (not unlimited) and int(used) >= limit,
    }


def technician_can_receive_request(conn, technician_id):
    """MOTEUR CENTRAL D'ELIGIBILITE - regle serveur unique.

    Ordre de priorite (regle produit) :
      1. abonnement ACTIVE  -> droits du plan (quota Pro applique)
      2. essai en cours     -> illimite pendant la decouverte
      3. sinon (essai termine sans abonnement, abonnement expire, ...)
         -> FALSE : plus de nouvelles demandes.
    """
    ent = get_technician_entitlements(conn, technician_id)
    if not ent["eligible"]:
        return False
    if ent["active"]:
        return not technician_request_usage(conn, technician_id)["over_limit"]
    return True   # essai : aucun plafond


@app.route("/abonnement")
@app.route("/dashboard/technicien/abonnement")
@login_required
def technician_subscription():
    """Page Abonnement du technicien : formules et engagement."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    current_code = None
    current_active = False
    current_sub = None
    unread_count = 0
    conn = get_db_connection()
    try:
        try:
            current = conn.execute(
                "SELECT s.status, s.end_date, p.code AS plan_code, p.name AS plan_name"
                " FROM technician_subscriptions s"
                " LEFT JOIN subscription_plans p ON p.id = s.plan_id"
                " WHERE s.technician_id = ?"
                " ORDER BY s.created_at DESC LIMIT 1",
                (user["id"],)).fetchone()
            if current:
                status = (current["status"] or "").upper()
                current_code = current["plan_code"]
                current_active = status in ("ACTIVE", "TRIAL")
                current_sub = {
                    "plan_name": current["plan_name"] or "Abonnement FixPro",
                    "plan_code": current["plan_code"],
                    "active": current_active,
                    "status_label": {"ACTIVE": "Actif", "TRIAL": "Essai",
                                     "PAST_DUE": "En attente de paiement", "EXPIRED": "Expiré",
                                     "CANCELLED": "Annulé"}.get(status, current["status"] or "—"),
                    "end_date_label": _format_date_month_fr(current["end_date"]) if current["end_date"] else None,
                }
        except Exception:
            conn.rollback()
        try:
            unread_count = conn.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
                (user["id"],)).fetchone()["n"]
        except Exception:
            conn.rollback()
            unread_count = 0
        # Tentative de paiement encore ouverte -> proposer de la reprendre.
        pending_payment = None
        try:
            op = conn.execute(
                "SELECT transaction_reference FROM subscription_payments"
                " WHERE user_id = ? AND status IN ('pending', 'processing')"
                " ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
            if op:
                pending_payment = op["transaction_reference"]
        except Exception:
            conn.rollback()
    finally:
        conn.close()

    plans = []
    for p in _TECH_PLANS:
        pv = dict(p)
        pv["discount_month"] = _tech_plan_discount_pct(p, "month")
        pv["discount_year"] = _tech_plan_discount_pct(p, "year")
        pv["year_savings"] = _tech_plan_year_savings_pct(p)
        pv["price_month_year"] = round(p["price_year"] / 12) if p.get("price_year") else 0
        pv["is_current"] = (p["code"] == current_code and current_active)
        plans.append(pv)
    max_year_savings = max((pv["year_savings"] for pv in plans), default=0)

    faq = [
        ("Comment fonctionne l'abonnement ?",
         "L'abonnement vous donne accès aux demandes des clients de votre zone. "
         "Il se renouvelle automatiquement à chaque échéance, sauf annulation de votre part."),
        ("Puis-je changer de plan ?",
         "Oui, à tout moment. Le nouveau plan prend effet à la prochaine échéance et le "
         "montant est ajusté au prorata."),
        ("Que se passe-t-il à la fin de mon abonnement ?",
         "Sans renouvellement, votre profil reste visible mais vous ne recevez plus de "
         "nouvelles demandes tant qu'un abonnement n'est pas actif."),
        ("Comment effectuer le paiement ?",
         "Par Orange Money, MTN Mobile Money ou carte bancaire. Votre abonnement "
         "n'est activé qu'une fois le paiement réellement confirmé par le moyen choisi."),
    ]

    conn2 = get_db_connection()
    try:
        entitlements = get_technician_entitlements(conn2, user["id"])
    finally:
        conn2.close()
    my_benefits = entitlement_labels(entitlements["entitlements"])

    return render_template("technician_subscription.html", user=user,
                           plans=plans, unread_count=unread_count,
                           max_year_savings=max_year_savings,
                           availability=(user.get("availability_status") or "hors_ligne"),
                           current_code=current_code, current_active=current_active,
                           current_sub=current_sub, faq=faq,
                           pending_payment=pending_payment,
                           entitlements=entitlements, my_benefits=my_benefits)


@app.route("/dashboard/technicien/abonnement/paiement", methods=["GET", "POST"])
@app.route("/abonnement/paiement", methods=["GET", "POST"])
@app.route("/abonnement/confirmation", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", methods=["POST"])
def technician_subscription_checkout():
    """Procedez au paiement : etape 2 du parcours (Confirmation -> Paiement
    -> Activation). Recapitulatif dynamique du plan choisi + choix du moyen
    de paiement. Fonctionne pour n'importe quel plan de _TECH_PLANS (donnees
    passees au gabarit, rien en dur). Le POST cree/reutilise une tentative
    PENDING et redirige vers "Paiement en cours" (aucune activation ici)."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    code = (request.values.get("plan") or "").strip()
    period = (request.values.get("period") or "month").strip()
    if period not in ("month", "year"):
        period = "month"
    plan = _tech_plan_by_code(code)
    if not plan:
        flash("Formule inconnue.", "error")
        return redirect(url_for("technician_subscription"))

    amount = _tech_plan_amount(plan, period)

    if request.method == "POST":
        method = (request.form.get("payment_method") or "").strip()
        if method not in _SUB_PAYMENT_CODES:
            flash("Choisissez un moyen de paiement.", "error")
            return redirect(url_for("technician_subscription_checkout", plan=code, period=period))
        payer_phone = (request.form.get("payer_phone") or "").strip()

        conn = get_db_connection()
        try:
            plan_id = _ensure_tech_plan_row(conn, code)
            # L'essai a pu ne jamais etre materialise (technicien qui va droit
            # au paiement) : on le cree ici pour ne pas le perdre si le
            # paiement echoue avant la fin des 14 jours.
            _ensure_technician_trial(conn, user["id"])

            # 1 ligne technician_subscriptions par technicien. Le clic "Payer"
            # n'active RIEN et NE TOUCHE PAS l'etat courant : un essai en cours
            # (TRIAL) reste un essai, un essai termine (TRIAL_EXPIRED) reste
            # termine, tant que le paiement n'est pas confirme. Seul
            # _activate_subscription_from_payment fera passer la ligne a ACTIVE.
            existing = conn.execute(
                "SELECT id, status FROM technician_subscriptions WHERE technician_id = ?"
                " ORDER BY created_at DESC LIMIT 1", (user["id"],)).fetchone()
            if existing:
                st = (existing["status"] or "").upper()
                if st in ("EXPIRED", "CANCELLED", "PAST_DUE"):
                    # ancien abonnement termine : on marque l'intention de payer
                    conn.execute(
                        "UPDATE technician_subscriptions SET status = 'PAST_DUE',"
                        " updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (existing["id"],))
                sub_id = existing["id"]
            else:
                sub_id = _insert_id(
                    conn,
                    "INSERT INTO technician_subscriptions"
                    " (technician_id, plan_id, status, auto_renew) VALUES (?, ?, 'PAST_DUE', 1)",
                    (user["id"], plan_id))

            # Anti double-clic / double-tentative : on reutilise la tentative
            # ouverte identique (meme plan, meme methode, meme montant).
            open_pay = conn.execute(
                "SELECT * FROM subscription_payments"
                " WHERE user_id = ? AND status IN ('pending', 'processing')"
                " ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
            if (open_pay and open_pay["plan_id"] == plan_id
                    and open_pay["payment_method"] == method
                    and int(open_pay["amount"] or 0) == int(amount)):
                ref = open_pay["transaction_reference"]
            else:
                if open_pay:            # tentative differente en cours -> on l'abandonne
                    conn.execute(
                        "UPDATE subscription_payments SET status = 'cancelled' WHERE id = ?",
                        (open_pay["id"],))
                now = datetime.now(timezone.utc)
                ref = "SUB-%s-%s-%s-%s" % (
                    code.upper(), period[:1].upper(),
                    now.strftime("%Y%m%d%H%M%S"), secrets.token_hex(3).upper())
                # Lancement de la tentative aupres du fournisseur. Aucun
                # fournisseur reel n'est configure : le mock renvoie 'pending',
                # le paiement N'EST JAMAIS considere comme reussi ici.
                res = get_payment_provider(method).process(int(amount), method, ref, {
                    "technician_id": user["id"], "plan": code, "phone": payer_phone,
                })
                # Un fournisseur non configure reste HONNETEMENT en 'pending' :
                # on ne marque 'failed' que sur un echec explicite du fournisseur.
                init_status = "pending"
                if res.get("status") == "failed":
                    init_status = "failed"
                elif res.get("status") == "processing":
                    init_status = "processing"
                conn.execute(
                    "INSERT INTO subscription_payments"
                    " (user_id, subscription_id, plan_id, amount, currency, payment_method,"
                    "  transaction_reference, status) VALUES (?, ?, ?, ?, 'GNF', ?, ?, ?)",
                    (user["id"], sub_id, plan_id, int(amount), method, ref, init_status))
            conn.commit()
        finally:
            conn.close()

        return redirect(url_for("subscription_payment_status", ref=ref))

    unread_count = 0
    conn = get_db_connection()
    try:
        unread_count = conn.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
            (user["id"],)).fetchone()["n"]
    except Exception:
        conn.rollback()
    finally:
        conn.close()

    year = period == "year"
    pv = {
        "code": plan["code"],
        "name": plan["name"],
        "desc": plan.get("desc") or "",
        "popular": bool(plan.get("popular")),
        "accent": plan.get("accent", "blue"),
        "icon": plan.get("icon", "star"),
        "price_now": int(plan["price_year"] if year else plan["price_month"]),
        "price_ref": int(plan.get("price_ref_year" if year else "price_ref_month") or 0),
        "discount": _tech_plan_discount_pct(plan, period),
        "unit": "an" if year else "mois",
        "duration": "1 an" if year else "1 mois",
        "tagline": "Plus de visibilité. Plus de clients. Plus de revenus.",
        "subtagline": "Développez votre activité avec FixPro.",
        "props": _SUB_VALUE_PROPS,
    }

    return render_template("technician_subscription_checkout.html", user=user,
                           plan=pv, period=period, amount=int(amount),
                           methods=_SUB_PAYMENT_METHODS, unread_count=unread_count,
                           availability=(user.get("availability_status") or "hors_ligne"))


@app.route("/abonnement/paiement/statut/<ref>")
@app.route("/abonnement/statut/<ref>")
@login_required
def subscription_payment_status(ref):
    """Page unique pilotee par l'etat reel du paiement (lu en base) :
    Paiement en cours / Abonnement active / Paiement echoue / annule / expire.
    Ne decide RIEN : elle affiche le statut serveur."""
    user = get_current_user()
    if not _is_technician(user):
        flash("Cet espace est reserve aux techniciens.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    try:
        pay = _sub_payment_by_ref(conn, ref, user["id"])
        if not pay:
            flash("Paiement introuvable.", "error")
            return redirect(url_for("technician_subscription"))
        status = _sub_payment_expire_stale(conn, pay)
        plan_name, plan_code = "Abonnement", None
        prow = conn.execute("SELECT name, code FROM subscription_plans WHERE id = ?",
                            (pay["plan_id"],)).fetchone()
        if prow:
            plan_name, plan_code = prow["name"], prow["code"]
        sub = None
        if pay["subscription_id"]:
            sub = conn.execute(
                "SELECT status, start_date, end_date FROM technician_subscriptions"
                " WHERE id = ?", (pay["subscription_id"],)).fetchone()
    finally:
        conn.close()

    view = {
        "ref": ref,
        "state": _PAY_STATE.get(status, "PENDING"),
        "plan_name": plan_name,
        "plan_code": plan_code,
        "amount": int(pay["amount"] or 0),
        "method": pay["payment_method"],
        "method_label": _SUB_METHOD_LABEL.get(pay["payment_method"], pay["payment_method"]),
        "created_label": _format_time_ago(pay["created_at"]),
        "confirmed_label": _format_date_month_fr(pay["paid_at"]) if pay["paid_at"] else None,
        "start_label": _format_date_month_fr(sub["start_date"]) if sub and sub["start_date"] else None,
        "end_label": _format_date_month_fr(sub["end_date"]) if sub and sub["end_date"] else None,
        "sub_active": bool(sub and (sub["status"] or "").upper() == "ACTIVE"),
    }
    return render_template("subscription_payment_status.html", user=user, v=view,
                           availability=(user.get("availability_status") or "hors_ligne"))


@app.route("/api/abonnement/statut/<ref>")
@login_required
def api_subscription_payment_status(ref):
    """Statut REEL de la tentative de paiement, lu en base (source unique
    de verite). Le frontend interroge cet endpoint mais ne decide de rien."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        pay = _sub_payment_by_ref(conn, ref, user["id"])
        if not pay:
            return jsonify({"ok": False}), 404
        status = _sub_payment_expire_stale(conn, pay)
    finally:
        conn.close()
    return jsonify({
        "ok": True,
        "state": _PAY_STATE.get(status, "PENDING"),
        "final": status in _PAY_FINAL,
        "confirmed": status == "paid",
    })


@app.route("/abonnement/statut/<ref>/annuler", methods=["POST"])
@login_required
@limiter.limit("30 per hour", methods=["POST"])
def subscription_payment_cancel(ref):
    """Le technicien abandonne sa tentative de paiement en cours.
    L'abonnement reste inactif."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        pay = _sub_payment_by_ref(conn, ref, user["id"])
        if pay:
            _fail_subscription_payment(conn, pay["id"], "cancelled")
    finally:
        conn.close()
    return redirect(url_for("subscription_payment_status", ref=ref))


@app.route("/webhooks/paiement/<provider>", methods=["POST"])
@limiter.limit("240 per hour")
def payment_webhook(provider):
    """Confirmation de paiement par un prestataire (Orange Money, MTN, carte).

    ⚠️ AUCUN prestataire reel n'est branche aujourd'hui : cet endpoint est
    le point d'integration pret a l'emploi. Il exige un secret partage
    (PAYMENT_WEBHOOK_SECRET) et n'active un abonnement QUE sur une
    confirmation explicite du prestataire. Idempotent."""
    secret = app.config.get("PAYMENT_WEBHOOK_SECRET", "")
    given = (request.headers.get("X-FixPro-Signature")
             or request.args.get("token") or "")
    if not secret or not secrets.compare_digest(str(secret), str(given)):
        return jsonify({"ok": False, "error": "signature"}), 403

    data = request.get_json(silent=True) or request.form
    ref = (data.get("reference") or data.get("transaction_reference") or "").strip()
    outcome = (data.get("status") or data.get("state") or "").strip().lower()
    logger.info("webhook paiement provider=%s ref=%s outcome=%s", provider, ref, outcome)
    if not ref:
        return jsonify({"ok": False, "error": "reference_manquante"}), 400

    conn = get_db_connection()
    try:
        pay = _sub_payment_by_ref(conn, ref)
        if not pay:
            return jsonify({"ok": False, "error": "reference_inconnue"}), 404
        cur = (pay["status"] or "").lower()
        if cur == "paid":
            return jsonify({"ok": True, "already": True})       # idempotent
        if cur not in _PAY_OPEN:
            return jsonify({"ok": True, "ignored": cur})

        amt = data.get("amount")
        if amt is not None:
            try:
                if int(float(amt)) != int(pay["amount"] or 0):
                    return jsonify({"ok": False, "error": "montant_incoherent"}), 400
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "montant_invalide"}), 400

        cur_dev = (data.get("currency") or data.get("devise") or "").strip().upper()
        if cur_dev and cur_dev != (pay["currency"] or "GNF").upper():
            return jsonify({"ok": False, "error": "devise_incoherente"}), 400

        if outcome in ("success", "confirmed", "paid", "ok", "completed"):
            conn.execute(
                "UPDATE subscription_payments SET status = 'paid' WHERE id = ?", (pay["id"],))
            conn.commit()
            _activate_subscription_from_payment(conn, pay["id"])
        elif outcome in ("failed", "error", "declined", "rejected"):
            _fail_subscription_payment(conn, pay["id"], "failed")
        elif outcome in ("cancelled", "canceled"):
            _fail_subscription_payment(conn, pay["id"], "cancelled")
        elif outcome in ("expired", "timeout"):
            _fail_subscription_payment(conn, pay["id"], "expired")
        else:
            return jsonify({"ok": False, "error": "statut_inconnu"}), 400
    finally:
        conn.close()
    return jsonify({"ok": True})


csrf.exempt(payment_webhook)


_DOC_LABELS = {
    DOC_IDENTITY: "Pièce d'identité",
    DOC_PROFESSIONAL: "Justificatif professionnel",
}


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
            if _is_technician(user):
                conn.execute(
                    "UPDATE users SET full_name = ?, phone = ?, profession = ?,"
                    " city = ?, zone_intervention = ?, years_experience = ?,"
                    " skills = ?, bio = ? WHERE id = ?",
                    (request.form.get("full_name", "").strip(),
                     request.form.get("phone", "").strip(),
                     request.form.get("profession", "").strip(),
                     request.form.get("city", "").strip(),
                     request.form.get("zone_intervention", "").strip(),
                     _to_int(request.form.get("years_experience")),
                     request.form.get("skills", "").strip(),
                     request.form.get("bio", "").strip(),
                     user["id"]),
                )
            else:
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


def _haversine(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return float("inf")
    if not all(math.isfinite(v) for v in (lat1, lon1, lat2, lon2)):
        return float("inf")
    R = 6371
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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

    radius_km = app.config.get("LOCAL_RADIUS_KM", 15.0)
    location_active = _is_valid_coordinate(client_lat, client_lon)
    client_zone = (session.get("client_zone")
                   or _nearest_place(client_lat, client_lon, max_km=8.0)
                   or (user.get("city") if user else None))

    if location_active or client_zone:
        # Couverture nationale : techniciens proches (GPS <= rayon) d'abord,
        # puis ceux de la meme zone (ville/quartier), avec elargissement
        # progressif pour ne jamais laisser une liste vide.
        # Le libelle de zone peut etre "Quartier, Ville" : on teste chaque
        # partie separement contre la ville / le quartier du technicien.
        zparts = [p.strip().lower() for p in re.split(r"[,/]", client_zone or "")
                  if len(p.strip()) >= 3]
        for a in artisans:
            a_lat = _to_float(a.get("latitude"))
            a_lon = _to_float(a.get("longitude"))
            a["distance"] = (_haversine(client_lat, client_lon, a_lat, a_lon)
                             if location_active and _is_valid_coordinate(a_lat, a_lon)
                             else None)
            haystack = " ".join(str(a.get(k) or "") for k in
                                ("city", "quartier", "zone_intervention")).lower()
            a["_zone_match"] = any(zp in haystack for zp in zparts)

        def _keep(a, r):
            return (a["distance"] is not None and a["distance"] <= r) or a["_zone_match"]

        kept = [a for a in artisans if _keep(a, radius_km)]
        # Aucun technicien a proximite : on elargit (jamais de page vide).
        for mult in (3, 8, 25):
            if kept:
                break
            kept = [a for a in artisans if _keep(a, radius_km * mult)]
        if not kept:
            kept = list(artisans)

        artisans = sorted(kept, key=lambda a: (
            0 if (a["distance"] is not None and a["distance"] <= radius_km)
            else (1 if a["_zone_match"] else 2),
            a["distance"] if a["distance"] is not None else 9e9,
        ))
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

        client_in_conakry = _in_conakry(client_lat, client_lon)
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

        # Badge d'abonnement REEL (Premium / Pro) : uniquement si ACTIVE.
        # Meme source centrale que le reste de l'app.
        _ent = get_technician_entitlements(conn, artisan_id)
        artisan["subscription_badge"] = _ent["badge"]     # None pendant l'essai
        artisan["is_featured"] = "featured_profile" in _ent["entitlements"]
        artisan["is_new"] = _ent["trial_active"] and not _ent["badge"]

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
        ticket_id = None
        if user:
            ticket = conn.execute(
                "SELECT id FROM admin_tickets"
                " WHERE client_id = ? AND artisan_id = ?"
                " ORDER BY created_at DESC LIMIT 1",
                (user["id"], artisan_id)).fetchone()
            if ticket:
                ticket_id = ticket["id"]

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

                # Eligibilite serveur (essai en cours OU abonnement actif, et
                # quota Pro non atteint). Vaut aussi pour une demande directe.
                if not technician_can_receive_request(conn, artisan_id):
                    flash("Ce technicien ne reçoit pas de nouvelles demandes "
                          "actuellement. Choisissez un autre technicien.", "error")
                    return redirect(url_for("artisan_detail", artisan_id=artisan_id))

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
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("client_tickets"))


def _notif_target(notif):
    """Deduit (icone, lien) pour une notification a partir de son type,
    de son champ `data` ('cle:valeur') et de son titre. Le lien renvoie
    toujours vers une fonctionnalite reelle du technicien."""
    def _f(key):
        try:
            return (notif[key] or "")
        except (KeyError, IndexError, TypeError):
            return ""
    typ = _f("type").lower()
    title = _f("title").lower()
    body = _f("body").lower()
    data = _f("data")
    kind, _, val = data.partition(":")

    if kind == "request_id" and val.isdigit():
        href = url_for("request_detail", request_id=int(val))
    elif typ == "new_request" or "demande" in title or "mission" in title:
        href = url_for("conversations")
    elif "message" in title or "reponse" in title or "réponse" in title:
        href = url_for("client_messages")
    elif "appel" in title or "contact" in title or kind == "contact_id":
        href = url_for("conversations")
    elif "avis" in title or "evaluation" in body or "évaluation" in body:
        href = url_for("profile")
    elif "abonnement" in title or typ in ("subscription", "abonnement"):
        href = url_for("technician_subscription")
    elif "intervention" in title:
        href = url_for("conversations")
    elif "document" in title or "dossier" in title or typ == "error":
        href = url_for("profile")
    elif typ == "success":
        href = url_for("artisan_dashboard")
    else:
        href = url_for("notifications")

    if "demande" in title or "mission" in title or typ == "new_request":
        icon = "wrench"
    elif "appel" in title or "contact" in title:
        icon = "phone"
    elif "message" in title or "reponse" in title or "réponse" in title:
        icon = "chat"
    elif "avis" in title or "evaluation" in body or "évaluation" in body:
        icon = "star"
    elif "abonnement" in title:
        icon = "card"
    elif "intervention" in title:
        icon = "calendar"
    elif typ == "error" or "document" in title or "dossier" in title or "important" in title:
        icon = "alert"
    elif typ == "success":
        icon = "check"
    else:
        icon = "info"
    return icon, href


@app.route("/notifications")
@login_required
def notifications():
    """Liste complete des notifications in-app de l'utilisateur connecte."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        try:
            rows = conn.execute(
                "SELECT * FROM notifications"
                " WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 50",
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
    items = []
    for r in rows:
        icon, href = _notif_target(r)
        d = dict(r)
        d["href"] = href
        d["icon"] = icon
        d["ago"] = _format_time_ago(r["created_at"])
        items.append(d)
    return render_template("notifications.html", user=user,
                           notifications=items, unread=unread)


@app.route("/api/notifications")
@login_required
def api_notifications():
    """Notifications recentes du technicien pour le panneau de la cloche.
    Un utilisateur ne recoit QUE ses propres notifications (filtre serveur)."""
    user = get_current_user()
    conn = get_db_connection()
    rows, unread = [], 0
    try:
        rows = conn.execute(
            "SELECT id, title, body, type, is_read, data, created_at"
            " FROM notifications WHERE user_id = ?"
            " ORDER BY created_at DESC, id DESC LIMIT 8", (user["id"],)).fetchall()
        unread = conn.execute(
            "SELECT COUNT(*) AS n FROM notifications"
            " WHERE user_id = ? AND is_read = 0", (user["id"],)).fetchone()["n"]
    except Exception:
        conn.rollback()
    finally:
        conn.close()
    items = []
    for r in rows:
        icon, href = _notif_target(r)
        items.append({
            "id": r["id"],
            "title": r["title"] or "Notification",
            "body": r["body"] or "",
            "is_read": bool(r["is_read"]),
            "ago": _format_time_ago(r["created_at"]),
            "icon": icon,
            "href": href,
        })
    return jsonify({"ok": True, "unread": unread or 0, "items": items})


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


@app.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_notifications_read():
    """Marque comme lues toutes les notifications non lues de l'utilisateur."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE notifications SET is_read = 1"
            " WHERE user_id = ? AND is_read = 0", (user["id"],))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "unread": 0})


# ---------------------------------------------------------------------------
# Demandes d'intervention
# ---------------------------------------------------------------------------

@app.route("/requests")
@login_required
def requests_list():
    user = get_current_user()
    conn = get_db_connection()
    try:
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
            # Garde anti-course : le quota mensuel a pu etre atteint entre la
            # selection et l'attribution. On revalide sur la meme connexion
            # juste avant l'INSERT ; si c'est plein, la demande part non
            # attribuee (REQUESTED) au lieu de depasser la limite du plan.
            if best and not technician_can_receive_request(conn, best["id"]):
                best = None
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


_SCHEMA_VERSION = "2026-09-10-notifications"


def _migrate_db():
    """Applique les migrations legeres au demarrage.

    En serverless, chaque cold start relance ce module : sans garde, on
    rejouait tout le balayage DDL (dizaines d'aller-retours vers Supabase)
    a chaque requete -> 15-35 s de latence. On note la version de schema
    dans `settings` et on saute tout si elle est deja a jour.
    """
    try:
        conn = get_db_connection()
        try:
            try:
                _row = conn.execute(
                    "SELECT value FROM settings WHERE key = 'schema_version'").fetchone()
                if _row and _row["value"] == _SCHEMA_VERSION:
                    conn.close()
                    return
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass

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

        try:
            _migrate_messaging(conn)
            conn.commit()
        except Exception as e:
            logger.warning("Migration messagerie impossible: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass

        try:
            _migrate_notifications(conn)
            conn.commit()
        except Exception as e:
            logger.warning("Migration notifications impossible: %s", e)
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

        # --- Marqueur : schema a jour, on sautera tout au prochain boot -----
        try:
            conn.execute("DELETE FROM settings WHERE key = 'schema_version'")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('schema_version', ?)",
                (_SCHEMA_VERSION,))
            conn.commit()
        except Exception as e:
            logger.warning("Marqueur schema_version non ecrit: %s", e)
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
    # tout admin sans role admin defini devient 'owner' (retro-compat)
    conn.execute("UPDATE users SET admin_role = 'owner'"
                 " WHERE role = 'admin' AND (admin_role IS NULL OR admin_role = '')")

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


def _migrate_messaging(conn):
    """Colonnes et tables pour la messagerie riche client <-> technicien.

    Pieces jointes, messages vocaux, statuts de message, mute/blocage/
    signalement par conversation. Compatible SQLite et PostgreSQL.
    """
    pk = "SERIAL PRIMARY KEY" if conn.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = "TIMESTAMP" if conn.is_postgres else "TEXT"

    msg_cols = conn.table_columns("conversation_messages")
    for col, ddl in (
        ("message_type", "message_type TEXT DEFAULT 'text'"),
        ("attachment_url", "attachment_url TEXT"),
        ("attachment_name", "attachment_name TEXT"),
        ("duration_ms", "duration_ms INTEGER"),
        ("is_delivered", "is_delivered INTEGER DEFAULT 0"),
    ):
        if col not in msg_cols:
            try:
                conn.execute(f"ALTER TABLE conversation_messages ADD COLUMN {ddl}")
                conn.commit()
            except Exception:
                conn.rollback()

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS conversation_prefs ("
        f" user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        f" conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,"
        f" muted INTEGER NOT NULL DEFAULT 0,"
        f" deleted_at {ts},"
        f" PRIMARY KEY (user_id, conversation_id))")

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS user_blocks ("
        f" blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        f" blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        f" created_at {ts} DEFAULT CURRENT_TIMESTAMP,"
        f" PRIMARY KEY (blocker_id, blocked_id))")

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS conversation_reports ("
        f" id {pk},"
        f" conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,"
        f" reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
        f" reported_id INTEGER REFERENCES users(id) ON DELETE SET NULL,"
        f" reason TEXT NOT NULL DEFAULT '', details TEXT DEFAULT '',"
        f" status TEXT NOT NULL DEFAULT 'new',"
        f" created_at {ts} DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_reports_status ON conversation_reports(status)")
    conn.commit()


def _migrate_notifications(conn):
    """Table des notifications in-app.

    Absente de schema.sql : sur une base PostgreSQL creee sans cette table
    (ou avec une definition incompatible), chaque INSERT echouait en silence
    et le badge restait bloque a 0. Compatible SQLite et PostgreSQL.
    """
    pk = "SERIAL PRIMARY KEY" if conn.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = "TIMESTAMP" if conn.is_postgres else "TEXT"

    conn.execute(
        f"CREATE TABLE IF NOT EXISTS notifications ("
        f" id {pk},"
        f" user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        f" title TEXT NOT NULL,"
        f" body TEXT,"
        f" type TEXT DEFAULT 'info',"
        f" is_read INTEGER DEFAULT 0,"
        f" data TEXT,"
        f" created_at {ts} DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read)")
    conn.commit()


_DEFAULT_PLANS = [
    ("basic", "Basic", 50000, 1,
     "Profil verifie\nApparait dans la recherche\nMessagerie avec les clients"),
    ("pro", "Pro", 100000, 2,
     "Tout Basic\nMise en avant dans la recherche\nStatistiques detaillees\nSupport prioritaire"),
    ("premium", "Premium", 200000, 3,
     "Tout Pro\nBadge Premium\nEn tete des resultats\nAccompagnement dedie"),
]


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
    viewer_tech = _is_technician(user)
    my_role = "artisan" if viewer_tech else "client"
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT c.id, c.subject, c.status, c.created_at, c.updated_at,"
            " c.client_id, c.artisan_id,"
            " (SELECT content FROM conversation_messages WHERE conversation_id = c.id"
            "  AND sender_role != 'system' ORDER BY created_at DESC, id DESC LIMIT 1) AS last_message,"
            " (SELECT message_type FROM conversation_messages WHERE conversation_id = c.id"
            "  AND sender_role != 'system' ORDER BY created_at DESC, id DESC LIMIT 1) AS last_type,"
            " (SELECT created_at FROM conversation_messages WHERE conversation_id = c.id"
            "  AND sender_role != 'system' ORDER BY created_at DESC, id DESC LIMIT 1) AS last_at,"
            " cl.full_name AS client_name, cl.photo_url AS client_photo,"
            " ar.full_name AS artisan_name, ar.photo_url AS artisan_photo,"
            " ar.profession AS artisan_profession,"
            " COALESCE(unread.n, 0) AS unread"
            " FROM conversations c"
            " LEFT JOIN users cl ON cl.id = c.client_id"
            " LEFT JOIN users ar ON ar.id = c.artisan_id"
            " LEFT JOIN ("
            "   SELECT conversation_id, COUNT(*) AS n"
            "   FROM conversation_messages"
            "   WHERE sender_role <> ? AND is_read = 0"
            "   GROUP BY conversation_id"
            " ) unread ON unread.conversation_id = c.id"
            " LEFT JOIN conversation_prefs p ON p.conversation_id = c.id AND p.user_id = ?"
            " WHERE (c.client_id = ? OR c.artisan_id = ?) AND p.deleted_at IS NULL"
            " ORDER BY c.updated_at DESC",
            (my_role, user["id"], user["id"], user["id"])).fetchall()
    finally:
        conn.close()
    _type_label = {"image": "\U0001F4F7 Photo", "audio": "\U0001F3A4 Message vocal",
                   "file": "\U0001F4C4 Document"}
    conversations = []
    for c in (dict(r) for r in rows):
        if viewer_tech and c["artisan_id"] == user["id"]:
            c["peer_name"] = c["client_name"] or "Client"
            c["peer_photo"] = c["client_photo"]
            c["peer_sub"] = "Client"
        else:
            c["peer_name"] = c["artisan_name"] or c["subject"] or "FixPro"
            c["peer_photo"] = c["artisan_photo"]
            c["peer_sub"] = c["artisan_profession"] or ("Technicien" if c["artisan_id"] else "Assistance FixPro")
        if not (c.get("last_message") or "").strip() and c.get("last_type") in _type_label:
            c["last_message"] = _type_label[c["last_type"]]
        conversations.append(c)
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


_MSG_MEDIA_TYPES = ("image", "file", "audio")
_ATTACH_MAX = {"image": 8 * 1024 * 1024, "file": 15 * 1024 * 1024, "audio": 12 * 1024 * 1024}


def _block_state(conn, a_id, b_id):
    """Retourne (i_blocked_them, they_blocked_me) entre deux utilisateurs."""
    rows = conn.execute(
        "SELECT blocker_id, blocked_id FROM user_blocks"
        " WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)",
        (a_id, b_id, b_id, a_id)).fetchall()
    mine = any(r["blocker_id"] == a_id for r in rows)
    theirs = any(r["blocker_id"] == b_id for r in rows)
    return mine, theirs


def _conv_muted(conn, user_id, conversation_id):
    row = conn.execute(
        "SELECT muted FROM conversation_prefs WHERE user_id = ? AND conversation_id = ?",
        (user_id, conversation_id)).fetchone()
    return bool(row and row["muted"])


def _msg_payload(m):
    return {
        "id": m["id"],
        "content": m["content"],
        "sender_role": m["sender_role"],
        "created_at": m["created_at"],
        "sender_name": m.get("sender_name") if hasattr(m, "get") else None,
        "message_type": (m.get("message_type") if hasattr(m, "get") else None) or "text",
        "attachment_url": m.get("attachment_url") if hasattr(m, "get") else None,
        "attachment_name": m.get("attachment_name") if hasattr(m, "get") else None,
        "duration_ms": m.get("duration_ms") if hasattr(m, "get") else None,
        "is_read": bool(m["is_read"]),
        "is_delivered": bool((m.get("is_delivered") if hasattr(m, "get") else 0) or m["is_read"]),
    }


@app.route("/messages/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def client_conversation(conversation_id):
    """Conversation client <-> technicien (ou assistant FixPro)."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        is_participant = conv and (
            conv["client_id"] == user["id"] or conv.get("artisan_id") == user["id"])
        if not conv or not is_participant:
            flash("Conversation introuvable.", "error")
            return redirect(url_for("client_messages"))
        # Conversation directe client <-> technicien (bouton "Message" du profil).
        viewer_is_tech = _is_technician(user) and conv.get("artisan_id") == user["id"]
        is_direct = bool(conv.get("artisan_id")) and conv["status"] == "direct"
        me_role = "artisan" if viewer_is_tech else "client"
        other_id = None
        if is_direct:
            other_id = conv["client_id"] if viewer_is_tech else conv.get("artisan_id")
        blocked_by_me, blocked_by_them = (False, False)
        if other_id:
            blocked_by_me, blocked_by_them = _block_state(conn, user["id"], other_id)

        if request.method == "POST":
            status = conv["status"]
            ready = False
            is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            content = (request.form.get("content") or "").strip()
            # Empeche un contenu truffe de sauts de ligne (clavier/voix Android,
            # copier-coller) de gonfler artificiellement la hauteur de la bulle.
            content = re.sub(r'\n{3,}', '\n\n', content)
            mtype = (request.form.get("message_type") or "text").strip()
            attachment = request.form.get("attachment") or ""
            attachment_name = (request.form.get("attachment_name") or "").strip()[:180]
            try:
                duration_ms = int(request.form.get("duration_ms") or 0) or None
            except (TypeError, ValueError):
                duration_ms = None

            if is_direct and (blocked_by_me or blocked_by_them):
                msg = ("Vous avez bloque cet utilisateur." if blocked_by_me
                       else "Vous ne pouvez plus envoyer de message dans cette conversation.")
                if is_xhr:
                    return jsonify({"ok": False, "error": msg, "blocked": True}), 403
                flash(msg, "error")
                return redirect(url_for("client_conversation", conversation_id=conversation_id))

            attach_url = None
            if mtype in _MSG_MEDIA_TYPES and attachment.startswith("data:"):
                try:
                    attach_url = storage.get_storage().upload(
                        attachment_name or mtype, attachment,
                        max_size=_ATTACH_MAX.get(mtype, 8 * 1024 * 1024))
                except Exception as e:
                    logger.warning("Upload piece jointe messagerie impossible: %s", e)
                    err = "Fichier non accepte ou trop volumineux."
                    if is_xhr:
                        return jsonify({"ok": False, "error": err}), 400
                    flash(err, "error")
                    return redirect(url_for("client_conversation", conversation_id=conversation_id))
            else:
                mtype = "text"

            if mtype == "text" and not content:
                if is_xhr:
                    return jsonify({"ok": False, "error": "Message vide."}), 400
                flash("Le message ne peut pas etre vide.", "error")
            else:
                new_id = _insert_id(
                    conn,
                    "INSERT INTO conversation_messages"
                    " (conversation_id, sender_id, sender_role, content,"
                    "  message_type, attachment_url, attachment_name, duration_ms)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (conversation_id, user["id"], me_role,
                     content or ("" if mtype != "text" else content),
                     mtype, attach_url, attachment_name or None, duration_ms))

                if is_direct:
                    other_role = "artisan" if me_role == "client" else "client"
                    conn.execute(
                        "UPDATE conversation_messages SET is_read = 1"
                        " WHERE conversation_id = ? AND sender_role = ?",
                        (conversation_id, other_role))
                    conn.execute(
                        "UPDATE conversations SET updated_at = ? WHERE id = ?",
                        (datetime.now(timezone.utc).isoformat(), conversation_id))
                    # Un nouveau message fait reapparaitre la conversation.
                    conn.execute(
                        "UPDATE conversation_prefs SET deleted_at = NULL"
                        " WHERE conversation_id = ?", (conversation_id,))
                elif conv["status"] != "admin_active":
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
                if is_xhr:
                    if is_direct:
                        rows = conn.execute(
                            "SELECT m.*, u.full_name AS sender_name"
                            " FROM conversation_messages m JOIN users u ON u.id = m.sender_id"
                            " WHERE m.id = ?", (new_id,)).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT m.*, u.full_name AS sender_name"
                            " FROM conversation_messages m JOIN users u ON u.id = m.sender_id"
                            " WHERE m.conversation_id = ? AND m.sender_role != 'system'"
                            " AND m.id >= ?"
                            " ORDER BY m.id ASC",
                            (conversation_id, new_id)).fetchall()
                    return jsonify({
                        "ok": True,
                        "messages": [_msg_payload(r) for r in rows],
                        "status": status,
                        "ready": ready,
                    })
                return redirect(url_for("client_conversation", conversation_id=conversation_id))

        is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        messages = conn.execute(
            "SELECT m.*, u.full_name AS sender_name"
            " FROM conversation_messages m"
            " JOIN users u ON u.id = m.sender_id"
            " WHERE m.conversation_id = ? AND m.sender_role != 'system'"
            " ORDER BY m.created_at ASC, m.id ASC",
            (conversation_id,)).fetchall()

        # Accuse de reception : l'autre partie a recu les messages (app ouverte).
        other_roles = ["admin"]
        if is_direct:
            other_roles.append("artisan" if me_role == "client" else "client")
        ph = ",".join("?" * len(other_roles))
        conn.execute(
            "UPDATE conversation_messages SET is_delivered = 1"
            " WHERE conversation_id = ? AND sender_role IN (%s) AND is_delivered = 0" % ph,
            (conversation_id, *other_roles))
        if not is_xhr:
            # Ouverture reelle de la conversation -> messages marques comme lus.
            conn.execute(
                "UPDATE conversation_messages SET is_read = 1"
                " WHERE conversation_id = ? AND sender_role IN (%s)" % ph,
                (conversation_id, *other_roles))
        conn.commit()

        if is_xhr:
            return jsonify({
                "ok": True,
                "me_role": me_role,
                "blocked_by_me": blocked_by_me,
                "blocked_by_them": blocked_by_them,
                "muted": _conv_muted(conn, user["id"], conversation_id),
                "messages": [_msg_payload(m) for m in messages],
            })
        artisan = None
        if conv.get("artisan_id"):
            artisan = conn.execute(
                "SELECT id, full_name, profession, photo_url FROM users WHERE id = ?",
                (conv["artisan_id"],)).fetchone()
        counterpart = None
        if other_id:
            counterpart = conn.execute(
                "SELECT id, full_name, profession, photo_url, is_verified,"
                " availability_status, phone, role FROM users WHERE id = ?",
                (other_id,)).fetchone()
        muted = _conv_muted(conn, user["id"], conversation_id)
    finally:
        conn.close()
    return render_template("client_conversation.html", conversation=conv, messages=messages,
                           user=user, artisan=artisan, counterpart=counterpart,
                           is_direct=is_direct, me_role=me_role, muted=muted,
                           blocked_by_me=blocked_by_me, blocked_by_them=blocked_by_them)


def _get_or_create_guest_user(conn):
    """Cree ou recupere un utilisateur visiteur anonyme (messagerie sans inscription)."""
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


@app.route("/messages/technicien/<int:artisan_id>", methods=["GET"])
@limiter.limit("15 per hour")
def client_message_artisan(artisan_id):
    """Ouvre (ou cree) la conversation directe entre le client et CE technicien.

    Cible du bouton "Message" sur le profil technicien : jamais l'assistant IA,
    jamais l'administration -- un dialogue 1-a-1 avec le technicien affiche.
    Accessible sans inscription : un compte visiteur anonyme est cree a la
    volee (limite en debit pour empecher un robot de gonfler la table users).
    """
    conn = get_db_connection()
    try:
        artisan = conn.execute(
            "SELECT id, full_name FROM users WHERE id = ?"
            " AND role IN ('artisan', 'technician')",
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
        if user["id"] == artisan_id:
            flash("Vous ne pouvez pas vous ecrire a vous-meme.", "error")
            return redirect(url_for("artisan_detail", artisan_id=artisan_id))

        now_iso = datetime.now(timezone.utc).isoformat()
        conv = conn.execute(
            "SELECT id, status FROM conversations"
            " WHERE client_id = ? AND artisan_id = ?",
            (user["id"], artisan_id)).fetchone()
        if not conv:
            conv_id = _insert_id(
                conn,
                "INSERT INTO conversations (client_id, artisan_id, subject, status, updated_at)"
                " VALUES (?, ?, ?, 'direct', ?)",
                (user["id"], artisan_id, artisan["full_name"], now_iso))
        else:
            conv_id = conv["id"]
            if conv["status"] != "direct":
                conn.execute(
                    "UPDATE conversations SET status = 'direct', updated_at = ?"
                    " WHERE id = ?", (now_iso, conv_id))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("client_conversation", conversation_id=conv_id))


def _conv_guard(conn, conversation_id, user):
    """Retourne (conv, other_id) si l'utilisateur participe, sinon (None, None)."""
    conv = conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    if not conv:
        return None, None
    if conv["client_id"] != user["id"] and conv.get("artisan_id") != user["id"]:
        return None, None
    other = conv["artisan_id"] if conv["client_id"] == user["id"] else conv["client_id"]
    return conv, other


@app.route("/messages/<int:conversation_id>/prefs", methods=["POST"])
@login_required
def conversation_prefs(conversation_id):
    """Active/desactive les notifications (mute) de cette conversation."""
    user = get_current_user()
    muted = 1 if (request.form.get("muted") in ("1", "true", "on")) else 0
    conn = get_db_connection()
    try:
        conv, _ = _conv_guard(conn, conversation_id, user)
        if not conv:
            return jsonify({"ok": False, "error": "Conversation introuvable."}), 404
        existing = conn.execute(
            "SELECT 1 FROM conversation_prefs WHERE user_id = ? AND conversation_id = ?",
            (user["id"], conversation_id)).fetchone()
        if existing:
            conn.execute(
                "UPDATE conversation_prefs SET muted = ? WHERE user_id = ? AND conversation_id = ?",
                (muted, user["id"], conversation_id))
        else:
            conn.execute(
                "INSERT INTO conversation_prefs (user_id, conversation_id, muted) VALUES (?, ?, ?)",
                (user["id"], conversation_id, muted))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "muted": bool(muted)})


@app.route("/messages/<int:conversation_id>/block", methods=["POST"])
@login_required
def conversation_block(conversation_id):
    """Bloque ou debloque l'autre participant de la conversation."""
    user = get_current_user()
    action = request.form.get("action") or "block"
    conn = get_db_connection()
    try:
        conv, other_id = _conv_guard(conn, conversation_id, user)
        if not conv or not other_id:
            return jsonify({"ok": False, "error": "Conversation introuvable."}), 404
        if action == "unblock":
            conn.execute(
                "DELETE FROM user_blocks WHERE blocker_id = ? AND blocked_id = ?",
                (user["id"], other_id))
            blocked = False
        else:
            exists = conn.execute(
                "SELECT 1 FROM user_blocks WHERE blocker_id = ? AND blocked_id = ?",
                (user["id"], other_id)).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO user_blocks (blocker_id, blocked_id) VALUES (?, ?)",
                    (user["id"], other_id))
            blocked = True
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "blocked": blocked})


@app.route("/messages/<int:conversation_id>/report", methods=["POST"])
@login_required
def conversation_report(conversation_id):
    """Signale la conversation ou l'autre participant a l'administration."""
    user = get_current_user()
    reason = (request.form.get("reason") or "autre").strip()[:80]
    details = (request.form.get("details") or "").strip()[:2000]
    conn = get_db_connection()
    try:
        conv, other_id = _conv_guard(conn, conversation_id, user)
        if not conv:
            return jsonify({"ok": False, "error": "Conversation introuvable."}), 404
        conn.execute(
            "INSERT INTO conversation_reports"
            " (conversation_id, reporter_id, reported_id, reason, details)"
            " VALUES (?, ?, ?, ?, ?)",
            (conversation_id, user["id"], other_id, reason, details))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/messages/<int:conversation_id>/delete", methods=["POST"])
@login_required
def conversation_delete(conversation_id):
    """Masque la conversation pour cet utilisateur (suppression cote client)."""
    user = get_current_user()
    conn = get_db_connection()
    try:
        conv, _ = _conv_guard(conn, conversation_id, user)
        if not conv:
            return jsonify({"ok": False, "error": "Conversation introuvable."}), 404
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = conn.execute(
            "SELECT 1 FROM conversation_prefs WHERE user_id = ? AND conversation_id = ?",
            (user["id"], conversation_id)).fetchone()
        if existing:
            conn.execute(
                "UPDATE conversation_prefs SET deleted_at = ? WHERE user_id = ? AND conversation_id = ?",
                (now_iso, user["id"], conversation_id))
        else:
            conn.execute(
                "INSERT INTO conversation_prefs (user_id, conversation_id, deleted_at) VALUES (?, ?, ?)",
                (user["id"], conversation_id, now_iso))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "redirect": url_for("client_messages")})


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


def _migrations_enabled():
    """En production, le balayage DDL ne tourne PAS a chaque cold start
    serverless (15-70 s de latence). Le schema Supabase est applique a la
    main ou via un deploiement avec RUN_MIGRATIONS=1. En dev/test, toujours."""
    if app.config.get("FLASK_ENV") != "production":
        return True
    return str(os.getenv("RUN_MIGRATIONS", "")).strip() in ("1", "true", "yes")


def _ensure_settings_and_migrations():
    """Charge les settings (et migrations si activees) au premier appel."""
    global _settings_loaded
    if _settings_loaded:
        return
    _settings_loaded = True
    try:
        _load_settings()
        if _migrations_enabled():
            _migrate_db()
        else:
            # Le balayage DDL est saute en prod, mais le compte admin doit
            # rester synchronise avec ADMIN_EMAILS / ADMIN_PASSWORD (peu couteux).
            try:
                _c = get_db_connection()
                try:
                    _bootstrap_admin(_c)
                    _c.commit()
                finally:
                    _c.close()
            except Exception as e:
                logger.warning("Bootstrap admin ignore: %s", e)
    except Exception as e:
        logger.warning("Parametres ou migrations indisponibles: %s", e)


app.before_request(_ensure_settings_and_migrations)


if __name__ == "__main__":
    logger.info("Démarrage de FixPro (environnement: %s)",
                app.config.get("FLASK_ENV"))
    app.run(host=app.config["HOST"], port=app.config["PORT"],
            debug=app.config["DEBUG"])
