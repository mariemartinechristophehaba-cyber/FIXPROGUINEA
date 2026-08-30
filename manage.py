"""Outil d'administration de FixPro.

Remplace l'ensemble des anciens scripts de configuration et de diagnostic.

Commandes disponibles :

    python manage.py init-db      Cree les tables et les metiers de base
    python manage.py check        Verifie la configuration et la connexion
    python manage.py inspect      Affiche le contenu de la base
    python manage.py secret       Genere une SECRET_KEY solide
    python manage.py create-admin Cree un compte administrateur
    python manage.py seed         Insere des donnees de demonstration
    python manage.py purge-guests Supprime les comptes visiteurs anonymes inactifs
"""

import getpass
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash

import db
from config import BASE_DIR, get_config
from fixpro_app import _geocode_zone, _is_valid_coordinate

TABLES = ("users", "service_categories", "requests", "messages", "payments", "intervention_photos", "intervention_history", "settings")


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
    # Whitelist strict des tables valides pour eviter toute injection.
    if table not in TABLES:
        return False
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


def cmd_upgrade_db(config):
    """Applique les migrations incrementelles sans detruire les donnees."""
    conn = _connect(config)
    try:
        cols = conn.table_columns("requests")
        user_cols = conn.table_columns("users")
        if "account_status" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN account_status TEXT DEFAULT 'ACTIVE'")
            conn.execute("UPDATE users SET account_status = 'SUSPENDED' WHERE is_active = 0")
            conn.execute("UPDATE users SET account_status = 'ACTIVE' WHERE is_active = 1")
            conn.commit()
            print("Colonne account_status ajoutee a 'users'.")

        if "reference" not in cols:
            conn.execute("ALTER TABLE requests ADD COLUMN reference TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_reference ON requests(reference)")
            conn.execute("ALTER TABLE requests ADD COLUMN service TEXT")
            conn.execute("ALTER TABLE requests ADD COLUMN requested_date TEXT")
            conn.execute("ALTER TABLE requests ADD COLUMN requested_time TEXT")
            conn.execute("ALTER TABLE requests ADD COLUMN estimated_price REAL DEFAULT 0")
            conn.execute("ALTER TABLE requests ADD COLUMN final_price REAL DEFAULT 0")
            conn.execute("ALTER TABLE requests ADD COLUMN commission_rate REAL DEFAULT 10")
            conn.execute("ALTER TABLE requests ADD COLUMN commission_amount REAL DEFAULT 0")
            conn.execute("ALTER TABLE requests ADD COLUMN professional_amount REAL DEFAULT 0")
            conn.execute("ALTER TABLE requests ADD COLUMN payment_status TEXT DEFAULT 'pending'")
            conn.execute("ALTER TABLE requests ADD COLUMN completed_at TEXT")
            conn.execute("ALTER TABLE requests ADD COLUMN latitude REAL DEFAULT 0")
            conn.execute("ALTER TABLE requests ADD COLUMN longitude REAL DEFAULT 0")
            conn.commit()
            print("Colonnes d'intervention ajoutees a 'requests'.")
        else:
            print("Colonnes d'intervention deja presentes.")

        tables = [t for t in TABLES if t not in ("users", "service_categories", "requests", "messages", "payments")]
        for table in tables:
            if _table_exists(conn, table):
                print(f"Table {table} deja presente.")
                continue
            if table == "intervention_photos":
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS intervention_photos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
                        photo_url TEXT NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            elif table == "intervention_history":
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS intervention_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
                        status TEXT NOT NULL,
                        actor TEXT,
                        note TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            elif table == "settings":
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                             ("FIXPRO_COMMISSION_RATE", "0.10"))
            conn.commit()
            print(f"Table {table} creee.")
    finally:
        conn.close()
    print("Migration terminee.")
    return 0


def cmd_purge_guests(config):
    """Supprime les comptes visiteurs anonymes crees il y a plus de 7 jours
    et qui n'ont jamais envoye de message, ainsi que leurs conversations vides.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    conn = _connect(config)
    try:
        stale = conn.execute(
            "SELECT u.id FROM users u"
            " WHERE u.role = 'client' AND u.full_name = 'Visiteur'"
            " AND u.phone LIKE 'guest-%'"
            " AND COALESCE(u.created_at, '') < ?"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM conversation_messages m"
            "   WHERE m.sender_id = u.id AND m.sender_role = 'client')",
            (cutoff,)).fetchall()
        ids = [row["id"] for row in stale]
        if not ids:
            print("Aucun compte visiteur inactif a supprimer.")
            return 0
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            "DELETE FROM conversations WHERE client_id IN (%s)" % placeholders, ids)
        conn.execute(
            "DELETE FROM users WHERE id IN (%s)" % placeholders, ids)
        conn.commit()
        print("%d compte(s) visiteur supprime(s)." % len(ids))
    finally:
        conn.close()
    return 0


COMMANDS = {
    "init-db": cmd_init_db,
    "check": cmd_check,
    "upgrade-db": cmd_upgrade_db,
    "inspect": cmd_inspect,
    "secret": cmd_secret,
    "create-admin": cmd_create_admin,
    "seed": cmd_seed,
    "geocode-artisans": cmd_geocode_artisans,
    "purge-guests": cmd_purge_guests,
}


def main(argv):
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 1
    return COMMANDS[argv[1]](get_config())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
