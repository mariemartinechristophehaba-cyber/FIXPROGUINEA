"""Outil d'administration de FixPro.

Remplace l'ensemble des anciens scripts de configuration et de diagnostic.

Commandes disponibles :

    python manage.py init-db      Cree les tables et les metiers de base
    python manage.py check        Verifie la configuration et la connexion
    python manage.py inspect      Affiche le contenu de la base
    python manage.py secret       Genere une SECRET_KEY solide
    python manage.py create-admin Cree un compte administrateur
"""

import getpass
import secrets
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

import db
from config import BASE_DIR, get_config

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


COMMANDS = {
    "init-db": cmd_init_db,
    "check": cmd_check,
    "inspect": cmd_inspect,
    "secret": cmd_secret,
    "create-admin": cmd_create_admin,
}


def main(argv):
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 1
    return COMMANDS[argv[1]](get_config())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
