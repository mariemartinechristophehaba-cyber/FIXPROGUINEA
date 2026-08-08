# 📚 GUIDE COMPLET - COMMENT TESTER FIXPRO

## ❌ ERREUR COMMUNE
Beaucoup de gens lancent directement `python "FixPro test.py"` et ça échoue. POURQUOI?
- Parce que MySQL n'est pas installé ou pas connecté ❌
- Parce que les packages Python ne sont pas installés ❌

## ✅ ÉTAPES À SUIVRE (DANS L'ORDRE!)

### 📋 ÉTAPE 1: Installer MySQL (Une seule fois)

**Sur Windows, deux options:**

**Option A: Installer MySQL officiellement**
1. Allez sur: https://dev.mysql.com/downloads/mysql/
2. Téléchargez "MySQL Community Server" (latest)
3. Suivez l'installateur (noter votre mot de passe!)
4. MySQL démarre automatiquement

**Option B: Utiliser Docker (Plus facile!)**
```powershell
# Installer Docker Desktop: https://www.docker.com/products/docker-desktop

# Lancer MySQL dans Docker
docker run -d -p 3306:3306 --name mysql-fixpro -e MYSQL_ROOT_PASSWORD=root mysql:8.0
```

✅ Vérifier que MySQL fonctionne:
```powershell
mysql -u root -p
# Entrez le mot de passe: root
# Si ça fonctionne, vous voyez: mysql>
# Tapez: EXIT
```

---

### 📦 ÉTAPE 2: Créer l'environnement Python

Ouvrez **PowerShell** et allez dans le dossier de l'application:

```powershell
cd "C:\Users\L2616\Desktop\Application Fixpro"
```

Créez un environnement virtuel (ce qui isolera vos packages):

```powershell
python -m venv .venv
```

Activez-le:

```powershell
.\.venv\Scripts\Activate.ps1
```

✅ Vous verrez: `(.venv) PS C:\...>`

---

### 📥 ÉTAPE 3: Installer les packages Python

Toujours dans le PowerShell activé:

```powershell
pip install -r requirements.txt
```

Ça va télécharger:
- `flask` → pour créer l'API web
- `mysql-connector-python` → pour parler à MySQL
- `gunicorn` → pour déployer l'app
- `python-dotenv` → pour les variables secrètes

✅ À la fin, vous verrez: `Successfully installed...`

---

### 🗄️ ÉTAPE 4: Créer la base de données

Créez d'abord la base de données vide:

```powershell
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS FixPro;"
# Mot de passe: root
```

Puis créez les tables:

```powershell
mysql -u root -p FixPro < setup_database.sql
# Mot de passe: root
```

✅ Vérifier que ça a marché:

```powershell
mysql -u root -p -e "USE FixPro; SHOW TABLES;"
# Mot de passe: root
# Vous devez voir: artisans, clients, interventions, etc.
```

---

### 🔑 ÉTAPE 5: Créer le fichier .env

Créez un fichier `.env` dans votre dossier:

```powershell
# Windows: créer le fichier vide
echo "" > .env
```

Puis éditez-le (Bloc-notes ou VS Code) et mettez ceci dedans:

```
FIXPRO_DB_HOST=localhost
FIXPRO_DB_USER=root
FIXPRO_DB_PASS=root
FIXPRO_DB_NAME=FixPro
FIXPRO_DEFAULT_COMMISSION=10
```

---

## 🧪 TESTER L'APPLICATION

### ✅ TEST 1: Tester le script CLI (Menu interactif)

```powershell
python "FixPro test.py"
```

Vous verrez un menu:
```
==================================================
MENU FixPro
==================================================
1 - Inscription Artisan
2 - Inscription Client
3 - Chercher un artisan (géolocalisation)
...
```

**Test simple:**
1. Appuyez sur `1` pour inscrire un artisan
2. Remplissez les champs
3. Vous devez voir: `✓ Artisan inscrit avec succès!`

---

### ✅ TEST 2: Tester l'API Flask

**Terminal 1: Démarrer l'API**
```powershell
python app.py
```

Vous verrez:
```
* Running on http://127.0.0.1:5000
* WARNING: This is a development server...
```

**Terminal 2: Tester l'API**

Ouvrez un **NOUVEAU PowerShell** et lancez:

```powershell
# Test simple: vérifier que l'API répond
curl http://localhost:5000/health

# Vous devez voir: {"status":"ok"}
```

---

## 🐛 SI QUELQUE CHOSE NE FONCTIONNE PAS

### Erreur: "Can't connect to MySQL"
```
✗ Erreur de connexion: No address associated with hostname
```
**Solution:** MySQL n'est pas lancé. 
- Allez dans Services Windows (Win+R → services.msc)
- Cherchez "MySQL"
- Clic droit → Démarrer

### Erreur: "No module named 'flask'"
```
ModuleNotFoundError: No module named 'flask'
```
**Solution:** L'environnement virtuel n'est pas activé.
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Erreur: "Port already in use"
```
OSError: [Errno 48] Address already in use
```
**Solution:** Quelque chose utilise déjà le port 5000.
```powershell
# Arrêtez l'ancienne instance (Ctrl+C) ou:
Get-Process -Id (Get-NetTCPConnection -LocalPort 5000).OwningProcess | Stop-Process
```

---

## 📊 STRUCTURE DE VOTRE APPLICATION

```
Application Fixpro/
├── .env                    ← Variables secrètes (à créer)
├── .venv/                  ← Environnement virtuel (créé)
├── app.py                  ← API Flask (web)
├── FixPro test.py          ← Menu interactif (CLI)
├── requirements.txt        ← Packages à installer
├── setup_database.sql      ← Création base de données
├── test.py                 ← Test simple
├── Dockerfile              ← Pour Docker
└── deploy/                 ← Fichiers de déploiement
```

---

## 🎯 PROCHAINES ÉTAPES

Une fois que ça fonctionne localement:

1. **Tester plus de fonctionnalités** (paiements, évaluations, etc.)
2. **Faire des tests automatiques** (fichier `test_api.py`)
3. **Déployer sur Render ou Railway** (voir deploy/)
4. **Ajouter une interface web** (HTML/CSS/JavaScript)

---

## 💡 RÉSUMÉ EN IMAGES MENTALES

**Votre app = Restaurant**
- `MySQL` = La cuisine (où les données sont stockées)
- `Python` = Le cuisinier (qui prépare les données)
- `Flask` = Le serveur (qui reçoit les commandes des clients)
- `.env` = Les recettes secrètes (connexion BD)
- `requirements.txt` = Les ingrédients (packages nécessaires)

**Pour que le restaurant fonctionne:**
1. ✅ Installer la cuisine (MySQL)
2. ✅ Embaucher le cuisinier (Python)
3. ✅ Acheter les ingrédients (pip install)
4. ✅ Écrire les recettes (.env)
5. ✅ Ouvrir le restaurant (python app.py)
6. ✅ Prendre des commandes (requêtes web)

---

**BESOIN D'AIDE? Contactez-moi!**
