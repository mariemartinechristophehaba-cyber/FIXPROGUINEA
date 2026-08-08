# GUIDE DE CONNEXION GITHUB À VERCEL - FIXPRO

## 🚀 ÉTAPE 1: CRÉER UN COMPTE VERCEL

### 1.1 Inscription
1. Allez sur https://vercel.com
2. Cliquez sur "Sign Up"
3. Choisissez "Continue with GitHub" (recommandé)
4. Autorisez Vercel à accéder à votre compte GitHub

## 🔗 ÉTAPE 2: CONNECTER VOTRE REPOSITORY GITHUB

### 2.1 Importer le projet
1. Connectez-vous à votre dashboard Vercel
2. Cliquez sur "Add New..." > "Project"
3. Vous verrez la liste de vos repositories GitHub
4. Trouvez et sélectionnez votre repository FixPro

### 2.2 Configuration du projet
**Project Name:** `fixpro-app` (ou le nom de votre choix)

**Framework Preset:** Python

**Root Directory:** `./` (laisser par défaut)

**Build Command:**
```
pip install -r requirements.txt
```

**Start Command:**
```
gunicorn app:app
```

## ⚙️ ÉTAPE 3: CONFIGURER LES VARIABLES D'ENVIRONNEMENT

### 3.1 Ajouter les variables
Dans la section "Environment Variables", ajoutez:

| Variable | Valeur |
|----------|--------|
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `0` |
| `SECRET_KEY` | (générer avec `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `FIXPRO_DB_ENGINE` | `sqlite` (ou `supabase` si configuré) |
| `FIXPRO_DB_PATH` | `fixpro.db` |
| `PORT` | `5000` |
| `HOST` | `0.0.0.0` |
| `CORS_ORIGINS` | `*` (ou votre domaine Vercel) |
| `FIXPRO_DEFAULT_COMMISSION` | `10` |
| `FIXPRO_COMMISSION_RATE` | `0.10` |
| `LOG_LEVEL` | `INFO` |

### 3.2 Variables Supabase (si applicable)
Si vous utilisez Supabase, ajoutez également:
| Variable | Valeur |
|----------|--------|
| `SUPABASE_URL` | (votre URL Supabase) |
| `SUPABASE_ANON_KEY` | (votre clé anon) |
| `SUPABASE_SERVICE_ROLE_KEY` | (votre clé service_role) |
| `DATABASE_URL` | (votre connection string PostgreSQL) |

## 🚀 ÉTAPE 4: DÉPLOYER

### 4.1 Premier déploiement
1. Cliquez sur "Deploy"
2. Attendez que le build se termine (~2-3 minutes)
3. Vercel vous donnera une URL comme: `https://fixpro-app.vercel.app`

### 4.2 Vérifier le déploiement
1. Cliquez sur l'URL fournie
2. Vérifiez que l'application fonctionne
3. Testez les fonctionnalités principales

## 🔄 ÉTAPE 5: CONFIGURER LES DÉPLOIEMENTS AUTOMATIQUES

### 5.1 Activer les déploiements automatiques
Vercel déploie automatiquement quand vous:
- Pushez vers la branche `main`
- Pushez vers d'autres branches connectées

### 5.2 Configuration des branches
1. Allez dans Settings > Git
2. Configurez les branches à déployer automatiquement
3. Par défaut: `main` en production

## 📋 ÉTAPE 6: OPTIMISATIONS POUR PYTHON/FLASK

### 6.1 Créer un fichier vercel.json (optionnel)
Créez un fichier `vercel.json` à la racine:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app.py"
    }
  ]
}
```

### 6.2 Adapter l'application pour Vercel
Vercel utilise des variables d'environnement spécifiques:
- `PORT` est fourni automatiquement par Vercel
- Le serveur doit écouter sur `0.0.0.0`

## 🔍 ÉTAPE 7: MONITORING

### 7.1 Dashboard Vercel
- Logs en temps réel
- Métriques de performance
- Analytics des visiteurs
- Erreurs et warnings

### 7.2 Domaine personnalisé (optionnel)
1. Allez dans Settings > Domains
2. Ajoutez votre domaine personnalisé
3. Configurez les DNS selon les instructions Vercel

## 🚨 DÉPANNAGE

### Erreur: "Module not found"
**Solution:** Vérifiez que `requirements.txt` contient toutes les dépendances

### Erreur: "Port already in use"
**Solution:** Utilisez le port fourni par Vercel via la variable d'environnement `PORT`

### Erreur: "Database connection failed"
**Solution:** Vérifiez les variables d'environnement de la base de données

### Application ne démarre pas
**Solution:** Vérifiez les logs Vercel dans l'onglet "Deployments"

## ✅ CHECKLIST FINALE

- [ ] Compte Vercel créé avec GitHub
- [ ] Repository GitHub importé dans Vercel
- [ ] Configuration du build correcte
- [ ] Variables d'environnement configurées
- [ ] Premier déploiement réussi
- [ ] Application accessible via l'URL Vercel
- [ ] Déploiements automatiques activés
- [ ] Monitoring vérifié

## 🎯 RÉSULTAT FINAL

Votre application FixPro sera:
- ✅ Déployée automatiquement à chaque push GitHub
- ✅ Accessible via une URL Vercel
- ✅ Monitoring actif
- ✅ Mises à jour automatiques
- ✅ HTTPS gratuit
- ✅ CDN global

**Coût:** $0 (Free tier suffisant pour commencer)