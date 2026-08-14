# FixPro

Plateforme de mise en relation entre clients et artisans qualifiés en Guinée.

## Architecture

- **Code** : Python 3.12+ / Flask
- **Base de donnees** : SQLite en local, Supabase (PostgreSQL) en production
- **Deploiement** : Vercel (serverless) via le dossier `api/`
- **Tableau de bord admin** : Next.js 14 + TypeScript + Tailwind dans `admin-nextjs/`
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

## Tableau de bord admin (Next.js)

Un nouveau dashboard admin moderne est disponible dans `admin-nextjs/`.

```bash
# Dossier du dashboard
cd admin-nextjs

# Installation
npm install

# Lancer en local
npm run dev
```

Ouvrir <http://localhost:3000/admin>.

L'application Flask redirige automatiquement `/admin/dashboard` vers ce dashboard via la variable `ADMIN_DASHBOARD_URL`.

Pour desactiver la redirection en developpement :

```text
ADMIN_DASHBOARD_URL=http://localhost:3000/admin
```

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
