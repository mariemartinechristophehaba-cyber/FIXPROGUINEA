# Guide de deploiement Vercel + Supabase

Ce guide est concu pour un utilisateur non technique. Suivez les etapes dans
l'ordre sans en sauter aucune.

## 0. Prerequis

Ayez sous la main :
- Votre compte GitHub avec le projet `FIXPROGUINEA`
- Votre compte Vercel (deja lie a GitHub)
- Votre compte Supabase (deja lie au projet)

## 1. Configurer la base de donnees Supabase

1. Connectez-vous a https://app.supabase.com et ouvrez votre projet FixPro.
2. Dans le menu de gauche, cliquez sur **Database** puis **Tables**.
3. Cliquez sur **SQL Editor** (petit crayon en haut).
4. Ouvrez le fichier `schema.sql` du projet sur votre ordinateur.
5. Copiez-collez tout son contenu dans l'editeur SQL de Supabase.
6. Cliquez sur **Run**. Vous devriez voir un message de succes.
7. Toujours dans Supabase, allez dans **Database > Tables** et verifiez que
   les tables suivantes existent :
   - users
   - service_categories
   - requests
   - messages
   - payments

8. Allez dans **Table editor > service_categories** et verifiez que les 6
   metiers sont presents : Plombier, Electricien, Frigoriste, Menuisier,
   Chauffagiste, Serrurier.

## 2. Recuperer les informations sensibles

Vous avez besoin de 4 valeurs pour Vercel. Les voici ou les trouver.

### 2.1 SUPABASE_URL

Dans Supabase, allez dans **Project Settings > API > Project URL**.
Copiez l'URL ressemblant a :

```
https://votre-projet-id.supabase.co
```

### 2.2 SUPABASE_ANON_KEY

Au meme endroit, copiez la **anon public** key (longue, commence par `eyJ...`).

### 2.3 DATABASE_URL

1. Allez dans **Database > Connect** (ou **Connection Pooling**).
2. Choisissez l'onglet **PSQL** ou **Connection string**.
3. Copiez l'URL commencant par `postgresql://`.

Exemple :

```
postgresql://postgres.votre-projet-id:LE-MOT-DE-PASSE-ICI@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
```

Gardez-la confidentielle.

### 2.4 SECRET_KEY

C'est une cle secrete pour les sessions. Ouvrez un terminal dans le projet et
lancez :

```bash
python manage.py secret
```

Sur votre ordinateur, cela fonctionne apres avoir active l'environnement :

```bash
.venv\Scripts\python.exe manage.py secret
```

Copiez la chaine de 64 caracteres affichee. Elle ne sera utilisee que sur
Vercel, elle ne doit jamais figurer dans le code.

## 3. Configurer Vercel

1. Allez sur https://vercel.com et ouvrez votre projet FixPro.
2. Cliquez sur **Settings > Environment Variables**.
3. Ajoutez les variables suivantes :

| Nom | Valeur |
|---|---|
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `0` |
| `SECRET_KEY` | votre cle de 64 caracteres |
| `DATABASE_URL` | votre URL PostgreSQL de Supabase |
| `SUPABASE_URL` | l'URL du projet Supabase |
| `SUPABASE_ANON_KEY` | l'anon key de Supabase |

4. Cliquez sur **Save**.

## 4. Connecter Vercel a GitHub (verification)

1. Dans Vercel, allez dans **Settings > Git**.
2. Verifiez que le projet est connecte au depot
   `mariemartinechristophehaba-cyber/FIXPROGUINEA`.
3. Assurez-vous que la branche de production est `main`.
4. Activez **Auto-deploy on push** si ce n'est pas fait.

## 5. Declencher le deploiement

1. Sur votre ordinateur, assurez-vous que le code est pousse sur la branche
   `main`.
2. Vercel va automatiquement detecter le push et lancer un deploiement.
3. Vous pouvez suivre la progression dans l'onglet **Deployments**.

Vous pouvez aussi forcer un deploiement en cliquant sur **Deploy** depuis
Vercel.

## 6. Verifier que le site fonctionne

Apres le deploiement, Vercel affiche une URL du type :

```
https://fixpro-xxxx.vercel.app
```

Ouvrez-la et testez :
- La page d'accueil charge (200)
- `/health` retourne `{"status":"ok"}`
- Vous pouvez creer un compte, vous connecter, deposer une demande
- Un artisan peut accepter la demande et proposer un devis

## 7. En cas de probleme

1. Allez dans Vercel, onglet **Deployments**, cliquez sur le deploiement en
   erreur.
2. Lisez les logs, specialement les lignes `ERROR`.
3. Les causes les plus frequentes sont :
   - `SECRET_KEY` manquante ou vide
   - `DATABASE_URL` incorrecte (impossible de joindre Supabase)
   - `psycopg2` manquant (verifiez `requirements.txt`)

## 8. Apres le deploiement

- Ne stockez jamais `SECRET_KEY` ou `DATABASE_URL` dans le code.
- Ne transmettez jamais ces valeurs en clair par WhatsApp ou email.
- Pour partager, utilisez le gestionnaire de secrets integre de Vercel.
