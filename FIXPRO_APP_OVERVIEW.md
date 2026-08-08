# FixPro - Vue d'ensemble du projet

## 1) Objectif du projet

FixPro est une application backend minimale pour mettre en relation des artisans et des clients.
Elle propose deux modes principaux :

- une API web via `app.py`
- un menu en ligne de commande via `FixPro test.py`

Ce dépôt n'inclut pas de front-end web complet. Le cœur du projet est une API REST et du code métier Python.

---

## 2) Fichiers principaux et leurs rôles

### `app.py`

C'est le serveur principal.

Rôles :
- expose des routes HTTP pour une API JSON
- se connecte à MySQL via `mysql.connector`
- gère l'inscription des artisans et clients
- gère la recherche d'artisans par métier et distance
- gère l'enregistrement des interventions

Routes disponibles :
- `/` : page d'accueil JSON de l'API
- `/health` : endpoint de santé du service
- `/api/artisans/register` : création d'un artisan
- `/api/clients/register` : création d'un client
- `/api/artisans/search` : recherche d'artisans proches
- `/api/interventions/register` : création d'une intervention

### `FixPro test.py`

C'est le menu CLI complet.

Rôles :
- connexion à MySQL
- classes métier : `Artisan`, `Client`, `Intervention`, `Evaluation`, `Paiement`, `Notification`
- interface texte pour inscrire des utilisateurs
- recherche géographique des artisans
- gestion des interventions, évaluations, paiements et notifications

Ce fichier est conçu pour une utilisation interactive dans le terminal.

### `test.py`

C'est un script d'inscription plus simple.

Rôles :
- proposer un formulaire interactif basique
- insérer un artisan dans la base MySQL

Ce fichier est moins complet que `FixPro test.py` et sert plutôt de script de test rapide.

### `LANCER.bat`

C'est le script de démarrage Windows.

Rôles :
- active l'environnement virtuel
- exécute `check.py` pour vérifier la configuration
- propose 3 options :
  1. menu interactif (`FixPro test.py`)
  2. API web (`app.py`)
  3. tests API (`test_api.py`)

### `README.md`

Rôle : expliquer comment lancer le projet localement et les prérequis.

### `DEPANNAGE.md`

Rôle : fournir des solutions aux erreurs courantes.

### `.env` / `.env.example`

Rôle : stocker la configuration MySQL et d'autres variables d'environnement.

Clés importantes :
- `FIXPRO_DB_HOST`
- `FIXPRO_DB_USER`
- `FIXPRO_DB_PASS`
- `FIXPRO_DB_NAME`
- `SECRET_KEY`

### `requirements.txt`

Rôle : liste des dépendances Python nécessaires.

Contenu :
- `flask`
- `mysql-connector-python`
- `gunicorn`
- `python-dotenv`

### `setup_database.sql`

Rôle : créer la base de données et les tables MySQL.

Tables créées :
- `artisans`
- `clients`
- `interventions`
- `transactions`
- `evaluations`
- `paiements`
- `notifications`

---

## 3) Pourquoi le lien local est `127.0.0.1:5000` et pas `localhost:3000`

### `127.0.0.1` vs `localhost`

- `127.0.0.1` est l'adresse IP locale (loopback)
- `localhost` est un nom de domaine local qui pointe généralement vers `127.0.0.1`

Sur une machine locale, ces deux adresses sont interchangeables.

### Pourquoi pas le port `3000` ?

Parce que `app.py` lance Flask avec :

```python
app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), ...)
```

Donc :
- si la variable `PORT` n'est pas définie, Flask utilise `5000`
- `3000` n'est pas configuré dans ce projet

Le port `3000` est souvent utilisé par des applications JavaScript (React, Angular), mais ici le backend est en Python/Flask.

### Pourquoi `0.0.0.0` ?

Dans `app.run(host='0.0.0.0', ...)`, `0.0.0.0` signifie "écouter toutes les interfaces réseau".
Cela permet à l'application d'accepter des requêtes depuis `127.0.0.1`, `localhost`, et potentiellement d'autres IP locales.

Mais pour accéder à l'application depuis ton navigateur local, tu utilises toujours `http://127.0.0.1:5000` ou `http://localhost:5000`.

---

## 4) Que représente `/health` ?

`/health` est un endpoint de vérification rapide.

Il retourne :

```json
{"status": "ok"}
```

Ce que cela signifie :
- le serveur Flask tourne
- il a traité la requête

Ce n'est pas une vérification de la base de données ni une page utilisateur.
C'est un simple check de disponibilité.

---

## 5) Que doit afficher `/` ?

Après correction, `/` retourne un JSON de documentation :

```json
{
  "service": "FixPro API",
  "status": "running",
  "endpoints": [
    "/health",
    "/api/artisans/register",
    "/api/clients/register",
    "/api/artisans/search?lat=...&lon=...&metier=...",
    "/api/interventions/register"
  ]
}
```

Ce n'est pas une page web riche, c'est un endpoint d'information.
Il sert à savoir rapidement que l'API est active et quelles routes sont disponibles.

---

## 6) Flux de fonctionnement de l'application

### API Flask (`app.py`)

1. Le serveur reçoit une requête HTTP.
2. Flask trouve la route correspondante.
3. Si la route a besoin de MySQL, `get_db_connection()` crée une connexion.
4. La requête SQL est exécutée.
5. Flask renvoie un JSON de réponse.

### Menu CLI (`FixPro test.py`)

1. L'utilisateur choisit une option dans le menu.
2. Le script lit des inputs clavier.
3. Il crée des objets Python métier.
4. Il exécute des requêtes SQL via `mysql.connector`.
5. Il affiche des résultats dans le terminal.

---

## 7) État actuel et limites du projet

### Ce qui fonctionne
- API backend simple
- insertion d'artisans, clients, interventions
- recherche d'artisans par métier et distance
- menu CLI pour gérer des cas d'usage basiques

### Ce qui manque / ce qui peut être amélioré
- pas d'authentification
- pas de front-end web complet
- `health` ne vérifie pas MySQL
- logique CLI et logique API sont séparées
- pas de tests unitaires solides pour le backend
- pas de validation forte sur tous les champs

---

## 8) Commandes utiles

### Activer l'environnement virtuel
```powershell
cd "C:\Users\L2616\Desktop\Application Fixpro"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Installer les dépendances
```powershell
pip install -r requirements.txt
```

### Démarrer l'API
```powershell
python app.py
```

### Tester la santé de l'API
```powershell
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5000/health').read().decode())"
```

### Démarrer le menu CLI
```powershell
python "FixPro test.py"
```

### Préparer la base MySQL
```powershell
mysql -u root -p FixPro < setup_database.sql
```

---

## 9) Ce que je te recommande comme nouveau dev

1. Comprends le rôle de `app.py` comme API backend.
2. Comprends que `FixPro test.py` est un outil CLI séparé.
3. Ne cherche pas un site web complet dans ce projet : il n'y en a pas encore.
4. Vérifie ton `.env` et la connexion MySQL avant de lancer l'app.
5. Utilise `/health` pour confirmer que le serveur répond.
6. Utilise `/` pour voir les endpoints.

---

## 10) Notes importantes

- `localhost:5000` et `127.0.0.1:5000` sont les mêmes pour ton navigateur local.
- Le port `3000` n'est pas utilisé ici.
- `5000` est le port choisi par Flask par défaut.
- `200 OK` et `{"status":"ok"}` signifient que le serveur est en ligne.
- `404 Not Found` sur `/` signifiait qu'il n'y avait pas de route d'accueil, j'ai corrigé cela.

---

## 11) Si tu veux que je fasse la suite

Je peux aussi :
- ajouter une vraie page d'accueil HTML
- ajouter des tests API automatiques
- relier `FixPro test.py` et `app.py` pour partager le même code métier
- rendre `/health` plus complet en vérifiant MySQL
- documenter tous les endpoints API avec des exemples de requêtes
