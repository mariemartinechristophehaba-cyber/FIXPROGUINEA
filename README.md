# FixPro

Plateforme de mise en relation entre clients et artisans qualifiés en Guinée.

## Architecture

- **Code** : Python 3.12+ / Flask
- **Base de donnees** : SQLite en local, Supabase (PostgreSQL) en production
- **Deploiement** : Vercel (serverless) via le dossier `api/`
- **Tableau de bord admin** : pages Flask (`/admin/*`) + API `/api/admin/*` — nouveau dashboard en cours
- **CI/CD** : GitHub Actions (tests + deploiement automatique)
- **Mobile** : application Flutter dans `mobile/`

## Démarrage rapide (local)

```bash
# 1. Creez l'environnement Python
python -m venv .venv
. .venv/bin/activate  # Windows : .venv\Scripts\activate

# 2. Installez les dependances
pip install -r requirements.txt

# 3. Configurez l'environnement
cp .env.example .env
# Remplacez SECRET_KEY par une cle solide : python manage.py secret

# 4. Initialisez la base de donnees locale
python manage.py init-db

# 5. Lancez l'application
python app.py
```

Le site est alors accessible sur http://127.0.0.1:5000.

## Tableau de bord admin

L'ancien dashboard (`admin-nextjs/`) a ete retire ; un nouveau est en cours.

En attendant, l'administration reste accessible via les pages Flask
(`/admin/login`, `/admin/dashboard`, `/admin/artisans`, ...) et l'API JSON
`/api/admin/*` (protegee par l'en-tete `X-API-Key`).

Si `ADMIN_DASHBOARD_URL` pointe vers un dashboard externe, `/admin/dashboard`
y redirige automatiquement ; sinon les pages Flask sont servies.

## Commandes d'administration

```bash
python manage.py init-db      # Cree les tables et les metiers de base
python manage.py check        # Verifie la connexion a la base
python manage.py inspect      # Affiche le contenu des tables
python manage.py secret       # Genere une SECRET_KEY aleatoire
python manage.py create-admin # Cree un compte administrateur
```

## Tests

```bash
python -m pytest tests/ -v
```

## Deploiement Vercel

Voir le guide detaille dans `DEPLOYMENT.md` (a completer avec les etapes
Supabase et Vercel).

## Structure du projet

```text
.
├── api/index.py        Point d'entree Vercel
├── app.py              Point d'entree local
├── fixpro_app.py       Application Flask (routes, metier)
├── db.py               Couche d'acces unifiee SQLite/PostgreSQL
├── config.py           Configuration par environnement
├── manage.py           Outil d'administration
├── schema.sql          Schema PostgreSQL (Supabase)
├── schema_sqlite.sql   Schema SQLite (local)
├── templates/          Pages HTML Jinja2
├── static/             CSS, images, JS
├── tests/              Tests pytest
└── mobile/             Application Flutter (branche mobile)
```

## Auteur

Projet FIXPROGUINEA.
