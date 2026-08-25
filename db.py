"""Couche d'acces aux donnees unifiee pour FixPro.

Ce module permet au reste de l'application d'ecrire ses requetes SQL une
seule fois, avec la syntaxe SQLite (placeholders `?`), et de fonctionner
indifferemment sur :

  - SQLite   : utilise en developpement local (fichier fixpro.db)
  - PostgreSQL / Supabase : utilise en production (variable DATABASE_URL)

La traduction des placeholders et la conversion des lignes en
dictionnaires sont prises en charge ici, de facon transparente.
"""

import re
import sqlite3

try:  # psycopg2 n'est pas necessaire pour un usage purement local
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover
    psycopg2 = None


class DatabaseError(RuntimeError):
    """Erreur de configuration ou de connexion a la base de donnees."""


def is_postgres_url(url):
    """Indique si l'URL fournie designe une base PostgreSQL/Supabase."""
    return bool(url) and url.startswith(("postgres://", "postgresql://"))


_SQL_LITERAL = re.compile(r"'(?:[^']|'')*'")


def _translate(sql, has_params):
    """Convertit une requete ecrite pour SQLite vers la syntaxe PostgreSQL.

    Les placeholders `?` deviennent `%s`. Lorsque des parametres sont
    fournis, psycopg2 interprete `%` comme un marqueur de format : les
    pourcentages litteraux (clauses LIKE par exemple) sont donc doubles.
    Les chaines SQL entre guillemets simples sont preservees telles
    quelles, a l'exception de ce doublement des `%`.
    """
    out = []
    last = 0
    for match in _SQL_LITERAL.finditer(sql):
        out.append(_translate_fragment(sql[last:match.start()], has_params))
        literal = match.group(0)
        out.append(literal.replace("%", "%%") if has_params else literal)
        last = match.end()
    out.append(_translate_fragment(sql[last:], has_params))
    return "".join(out)


def _translate_fragment(fragment, has_params):
    if has_params:
        fragment = fragment.replace("%", "%%")
    return fragment.replace("?", "%s")


class Result:
    """Resultat d'une requete, expose des lignes sous forme de dictionnaires."""

    def __init__(self, cursor, is_postgres):
        self._cursor = cursor
        self._is_postgres = is_postgres

    def fetchone(self):
        row = self._cursor.fetchone()
        return self._convert(row)

    def fetchall(self):
        return [self._convert(row) for row in self._cursor.fetchall()]

    def _convert(self, row):
        if row is None:
            return None
        return dict(row)

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)


class Connection:
    """Connexion unifiee exposant une API commune aux deux moteurs."""

    def __init__(self, raw, is_postgres):
        self._raw = raw
        self.is_postgres = is_postgres

    def execute(self, sql, params=()):
        params = tuple(params) if params else ()
        if self.is_postgres:
            cursor = self._raw.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(_translate(sql, bool(params)), params)
        else:
            cursor = self._raw.execute(sql, params)
        return Result(cursor, self.is_postgres)

    def executemany(self, sql, seq_of_params):
        seq_of_params = [tuple(p) for p in seq_of_params]
        if self.is_postgres:
            cursor = self._raw.cursor()
            cursor.executemany(_translate(sql, True), seq_of_params)
        else:
            cursor = self._raw.executemany(sql, seq_of_params)
        return Result(cursor, self.is_postgres)

    def executescript(self, script):
        """Execute un script SQL compose de plusieurs instructions."""
        if self.is_postgres:
            cursor = self._raw.cursor()
            cursor.execute(script)
        else:
            self._raw.executescript(script)

    def table_columns(self, table):
        """Retourne la liste des colonnes d'une table, pour les deux moteurs."""
        if self.is_postgres:
            rows = self.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ?",
                (table,),
            ).fetchall()
            return [row["column_name"] for row in rows]
        return [row[1] for row in self._raw.execute(
            'PRAGMA table_info("%s")' % table).fetchall()]

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self.is_postgres:
            try:
                self._raw.rollback()
            except Exception:
                pass
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


def connect(database_url="", sqlite_path="fixpro.db"):
    """Ouvre une connexion : PostgreSQL si DATABASE_URL est defini, SQLite sinon."""
    if is_postgres_url(database_url):
        if psycopg2 is None:
            raise DatabaseError(
                "psycopg2 est requis pour se connecter a PostgreSQL. "
                "Installez-le avec : pip install psycopg2-binary")
        raw = psycopg2.connect(database_url, connect_timeout=10)
        raw.autocommit = False
        return Connection(raw, is_postgres=True)

    raw = sqlite3.connect(sqlite_path)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return Connection(raw, is_postgres=False)
