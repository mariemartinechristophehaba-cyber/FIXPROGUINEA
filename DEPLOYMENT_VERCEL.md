# GUIDE DE DÉPLOIEMENT VERCEL - FIXPRO

## 🚀 ÉTAPES RAPIDES POUR CONNECTER GITHUB À VERCEL

### 1. CRÉER UN COMPTE VERCEL
1. Allez sur https://vercel.com
2. Cliquez sur "Sign Up" 
3. Sélectionnez "Continue with GitHub"
4. Autorisez l'accès à votre compte GitHub

### 2. IMPORTER VOTRE PROJET
1. Connectez-vous à Vercel
2. Cliquez sur "Add New..." > "Project"
3. Sélectionnez votre repository FixPro depuis la liste GitHub
4. Cliquez sur "Import"

### 3. CONFIGURER LE PROJET
**Project Name:** `fixpro-app`

**Framework Preset:** Python

**Root Directory:** `./`

**Build Command:**
```
pip install -r requirements.txt
```

**Start Command:**
```
gunicorn app:app
```

### 4. VARIABLES D'ENVIRONNEMENT
Cliquez sur "Environment Variables" et ajoutez:

```
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=votre_clé_secrete_ici
FIXPRO_DB_ENGINE=sqlite
FIXPRO_DB_PATH=fixpro.db
PORT=5000
HOST=0.0.0.0
CORS_ORIGINS=*
FIXPRO_DEFAULT_COMMISSION=10
FIXPRO_COMMISSION_RATE=0.10
LOG_LEVEL=INFO
```

### 5. DÉPLOYER
1. Cliquez sur "Deploy"
2. Attendez le build (~2-3 minutes)
3. Votre application sera accessible via: `https://fixpro-app.vercel.app`

## 🔄 AUTOMATISATION

Une fois connecté, Vercel déploiera automatiquement:
- À chaque push sur la branche `main`
- À chaque création de Pull Request
- À chaque push sur les branches configurées

## 📁 FICHIERS DE CONFIGURATION CRÉÉS

✅ `vercel.json` - Configuration Vercel
✅ `api/index.py` - Point d'entrée pour Vercel
✅ `.vercelignore` - Fichiers ignorés au déploiement
✅ `VERCEL_GITHUB_SETUP.md` - Guide détaillé

## 🎯 PROCHAINES ÉTAPES

1. Connectez votre compte GitHub à Vercel
2. Importez le projet FixPro
3. Configurez les variables d'environnement
4. Déployez et testez

Une fois déployé, Vercel synchronisera automatiquement toutes les modifications de votre repository GitHub!