# Regles de collaboration pour les agents IA

Ce fichier s'adresse a Claude Code, Cursor, Devin AI et tout autre assistant
code. Il doit etre respecte afin de garantir la coherence du projet FixPro.

## 1. Langue et style

- Code, commentaires et messages de commit en francais, comme le projet.
- Pas d'emojis dans le code ni dans les fichiers de configuration.
- Noms des fonctions et variables : snake_case en francais ou en anglais
technique (`get_db_connection`, `request_item`), mais coherent.

## 2. Architecture imposee

- Le backend est une application **Flask Python 3.12+**.
- L'acces aux donnees doit TOUJOURS passer par `db.py`.
- N'ecrivez JAMAIS directement `sqlite3.connect(...)` ou
`psycopg2.connect(...)` dans les routes. Utilisez `get_db_connection()` de
`fixpro_app.py` ou `db.connect(...)`.
- Les requetes SQL doivent utiliser le placeholder `?`. `db.py` se charge
de le traduire en `%s` pour PostgreSQL.
- Toute nouvelle fonctionnalite est testee dans `tests/test_app.py`.

## 3. Environnements

| Variable | Local | Production |
|---|---|---|
| `FLASK_ENV` | `development` | `production` |
| `DATABASE_URL` | vide | PSQL string Supabase |
| `SECRET_KEY` | generee auto | obligatoire, fixe |
| `FIXPRO_DB_PATH` | `fixpro.db` | ignore |

- En production, `SECRET_KEY` est OBLIGATOIRE. Ne pas la generer
automagiquement.
- Le filesystem de Vercel est en lecture seule : PAS d'ecriture de fichiers
(logs, uploads, SQLite).

## 4. Securite non negociable

- CSRF active par `flask_wtf.csrf.CSRFProtect`. Tout formulaire POST doit
contenir `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- Mots de passes haches avec `werkzeug.security.generate_password_hash`.
- Aucun secret, mot de passe ou cle API dans le code source.
- Les `.env*` locaux ne doivent jamais etre commites (voir `.gitignore`).

## 5. Workflow

1. Avant toute modification destructive, creer une branche archive.
2. Lancer `python -m pytest tests/ -q` avant de valider.
3. Faire des commits atomiques avec un message en francais.
4. Pousser sur `main` uniquement via pull request ou CI reussie.

## 6. Pile technologique autorisee

- Backend : Flask, Flask-WTF, Flask-Limiter, Werkzeug, psycopg2-binary
- Base : SQLite (local), Supabase PostgreSQL (production)
- Deploiement : Vercel
- Mobile : Flutter (dossier `mobile/`)
- Pas de Render, pas de Docker, pas de VPS. Vercel + Supabase uniquement.
