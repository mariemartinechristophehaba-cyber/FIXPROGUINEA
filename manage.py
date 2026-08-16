"""Outil d'administration de FixPro.

Remplace l'ensemble des anciens scripts de configuration et de diagnostic.

Commandes disponibles :

    python manage.py init-db      Cree les tables et les metiers de base
    python manage.py check        Verifie la configuration et la connexion
    python manage.py inspect      Affiche le contenu de la base
    python manage.py secret       Genere une SECRET_KEY solide
    python manage.py create-admin Cree un compte administrateur
    python manage.py seed         Insere des donnees de demonstration
"""

import getpass
import secrets
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

import db
from config import BASE_DIR, get_config
from fixpro_app import _geocode_zone

TABLES = ("users", "service_categories", "requests", "messages", "payments")


def _connect(config):
    return db.connect(database_url=config.DATABASE_URL,
                      sqlite_path=config.SQLITE_PATH)


def _target(config):
    if db.is_postgres_url(config.DATABASE_URL):
        return "PostgreSQL / Supabase"
    return "SQLite (%s)" % config.SQLITE_PATH


def cmd_init_db(config):
    """Applique le schema correspondant au moteur de base configure."""
    is_postgres = db.is_postgres_url(config.DATABASE_URL)
    schema_file = "schema.sql" if is_postgres else "schema_sqlite.sql"
    script = (Path(BASE_DIR) / schema_file).read_text(encoding="utf-8")

    print("Cible : %s" % _target(config))
    print("Schema : %s" % schema_file)

    conn = _connect(config)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()
    print("Base de donnees initialisee avec succes.")
    return 0


def cmd_check(config):
    """Verifie que la configuration permet de joindre la base de donnees."""
    print("Environnement : %s" % config.FLASK_ENV)
    print("Cible         : %s" % _target(config))
    print("SECRET_KEY    : %s" % ("definie" if config.SECRET_KEY else "ABSENTE"))

    if config.FLASK_ENV == "production" and not db.is_postgres_url(
            config.DATABASE_URL):
        print("ERREUR : en production, DATABASE_URL doit pointer vers Supabase.")
        return 1

    try:
        conn = _connect(config)
    except Exception as exc:
        print("ERREUR de connexion : %s" % exc)
        return 1

    try:
        missing = [t for t in TABLES if not _table_exists(conn, t)]
        if missing:
            print("Tables manquantes : %s" % ", ".join(missing))
            print("Lancez : python manage.py init-db")
            return 1
        print("Connexion reussie, les %d tables sont presentes." % len(TABLES))
    finally:
        conn.close()
    return 0


def _table_exists(conn, table):
    try:
        conn.execute('SELECT 1 FROM "%s" LIMIT 1' % table).fetchone()
        return True
    except Exception:
        conn.rollback()
        return False


def cmd_inspect(config):
    """Affiche le nombre d'enregistrements de chaque table."""
    conn = _connect(config)
    try:
        print("Cible : %s\n" % _target(config))
        for table in TABLES:
            if not _table_exists(conn, table):
                print("%-20s (table absente)" % table)
                continue
            row = conn.execute(
                'SELECT COUNT(*) AS n FROM "%s"' % table).fetchone()
            print("%-20s %5d enregistrement(s)" % (table, row["n"]))
    finally:
        conn.close()
    return 0


def cmd_secret(_config):
    """Genere une cle secrete adaptee a un usage en production."""
    print(secrets.token_hex(32))
    return 0


def cmd_create_admin(config):
    """Cree un compte administrateur avec un mot de passe saisi a la main."""
    email = input("Email de l'administrateur : ").strip().lower()
    full_name = input("Nom complet : ").strip()
    password = getpass.getpass("Mot de passe (8 caracteres minimum) : ")

    if not email or not full_name:
        print("ERREUR : email et nom complet sont obligatoires.")
        return 1
    if len(password) < 8:
        print("ERREUR : le mot de passe doit contenir au moins 8 caracteres.")
        return 1

    conn = _connect(config)
    try:
        if conn.execute("SELECT id FROM users WHERE email = ?",
                        (email,)).fetchone():
            print("ERREUR : cet email est deja utilise.")
            return 1
        conn.execute(
            "INSERT INTO users (email, password_hash, role, full_name,"
            " is_verified) VALUES (?, ?, 'admin', ?, 1)",
            (email, generate_password_hash(password), full_name))
        conn.commit()
    finally:
        conn.close()
    print("Compte administrateur cree.")
    return 0


def cmd_seed(config):
    """Insere des donnees de demonstration dans la base."""
    import datetime as dt

    conn = _connect(config)
    try:
        # Nettoie les anciennes donnees de demo
        conn.execute("DELETE FROM payments")
        conn.execute("DELETE FROM requests")
        conn.execute("DELETE FROM technician_documents")
        conn.execute("DELETE FROM users WHERE role IN ('client', 'artisan')")
        conn.commit()

        # Client de demonstration
        conn.execute(
            "INSERT INTO users (email, phone, password_hash, role, full_name,"
            " city, quartier, is_verified, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('client@demo.fixpro', '+224620000001', generate_password_hash('client001'),
             'client', 'Amadou Diallo', 'Conakry', 'Kaloum', 1, 1))

        # Trois artisans de demonstration
        artisans = [
            ('Mamadou Bah', '+224620000002', 'Plomberie', 'Conakry', 'Kaloum'),
            ('Fatou Camara', '+224620000003', 'Electricite', 'Conakry', 'Dixinn'),
            ('Ibrahim Sylla', '+224620000004', 'Menuiserie', 'Conakry', 'Matam'),
        ]
        for name, phone, profession, city, quartier in artisans:
            lat, lon = _geocode_zone(city, quartier)
            conn.execute(
                "INSERT INTO users (email, phone, password_hash, role, full_name,"
                " profession, city, quartier, latitude, longitude, is_verified, is_active)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f'demo-{phone}@fixpro.app', phone, generate_password_hash(phone.replace('+', '')),
                 'artisan', name, profession, city, quartier, lat, lon, 1, 1))

        # Recupere les IDs
        client = conn.execute("SELECT id FROM users WHERE role = 'client'").fetchone()
        artisan_rows = conn.execute("SELECT id, profession FROM users WHERE role = 'artisan'").fetchall()

        # Quatre demandes de demonstration
        requests = [
            ('Fuite sous evier', 'La cuisine coule depuis ce matin.', 'Plomberie', 'Kaloum', 150000, 'pending', None),
            ('Luminaire a installer', 'Installation de lustres dans le salon.', 'Electricite', 'Dixinn', 225000, 'assigned', artisan_rows[1]["id"]),
            ('Porte cassee', 'La porte d entree ne ferme plus.', 'Menuiserie', 'Matam', 320000, 'completed', artisan_rows[2]["id"]),
            ('Climatisation en panne', 'Unite exterieure ne demarre pas.', 'Froid', 'Coleah', 180000, 'pending', None),
        ]
        today = dt.datetime.now().strftime('%Y-%m-%d')
        for title, description, category, address, amount, status, artisan_id in requests:
            conn.execute(
                "INSERT INTO requests (client_id, artisan_id, title, description, category,"
                " address, status, quote_amount, budget, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client["id"], artisan_id, title, description, category, address, status,
                 amount, amount, f'{today} 10:00:00', f'{today} 10:00:00'))

        # Un paiement complet
        req = conn.execute(
            "SELECT id, quote_amount FROM requests WHERE artisan_id = ? AND status = 'completed'",
            (2,)).fetchone()
        if req:
            conn.execute(
                "INSERT INTO payments (request_id, amount, commission_amount, method, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (req["id"], req["quote_amount"], int(req["quote_amount"] * 0.10), 'orange_money', 'completed', f'{today} 10:00:00'))

        conn.commit()
    finally:
        conn.close()
    print("Donnees de demonstration inserees.")
    return 0


def cmd_geocode_artisans(config):
    """Re-geocode les coordonnees des artisans existants a partir de leur quartier."""
    conn = _connect(config)
    try:
        rows = conn.execute(
            "SELECT id, city, quartier, latitude, longitude"
            " FROM users WHERE role = 'artisan'").fetchall()
        updated = 0
        for row in rows:
            if _is_valid_coordinate(row["latitude"], row["longitude"]):
                continue
            lat, lon = _geocode_zone(row["city"], row["quartier"])
            if _is_valid_coordinate(lat, lon):
                conn.execute(
                    "UPDATE users SET latitude = ?, longitude = ? WHERE id = ?",
                    (lat, lon, row["id"]))
                updated += 1
        conn.commit()
        print("%d artisan(s) mis a jour avec des coordonnees." % updated)
    finally:
        conn.close()
    return 0


def _is_valid_coordinate(lat, lon):
    if lat is None or lon is None:
        return False
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    return not (abs(lat) < 0.01 and abs(lon) < 0.01)


COMMANDS = {
    "init-db": cmd_init_db,
    "check": cmd_check,
    "inspect": cmd_inspect,
    "secret": cmd_secret,
    "create-admin": cmd_create_admin,
    "seed": cmd_seed,
    "geocode-artisans": cmd_geocode_artisans,
}


def main(argv):
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 1
    return COMMANDS[argv[1]](get_config())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
