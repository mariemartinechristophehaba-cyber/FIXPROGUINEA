# GUIDE DE CONFIGURATION SUPABASE - FIXPRO

## 🚀 ÉTAPE 1 : CRÉER UN PROJET SUPABASE

### 1.1 Inscription
1. Allez sur https://supabase.com
2. Cliquez sur "Start your project"
3. Inscription avec GitHub (recommandé) ou email

### 1.2 Créer le projet
1. Cliquez sur "New Project"
2. Remplissez les informations :
   - **Name** : `fixpro-production`
   - **Database Password** : (générer un mot de passe fort, notez-le !)
   - **Region** : Choisissez la région la plus proche de vos utilisateurs
     - Pour la Guinée/Afrique de l'Ouest : "Eu West (Paris)" ou "US East"
   - **Pricing Plan** : Free (pour commencer)
3. Cliquez sur "Create new project"
4. Attendez ~2 minutes que le projet soit provisionné

## 🔑 ÉTAPE 2 : RÉCUPÉRER LES CLÉS API

### 2.1 Accéder aux paramètres API
1. Dans votre dashboard Supabase
2. Cliquez sur "Settings" (icône engrenage) > "API"

### 2.2 Copier les informations suivantes

**Project URL** :
```
https://xxxxxxxxxxxxx.supabase.co
```

**Project API Keys** :
- `anon public` : Clé publique pour le frontend
- `service_role` : Clé admin (garder secrète !)

**Database Connection String** :
```
postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxx.supabase.co:5432/postgres
```

## 🗄️ ÉTAPE 3 : CONFIGURER LA BASE DE DONNÉES

### 3.1 Exécuter le schéma
1. Dans Supabase, cliquez sur "SQL Editor" (icône SQL)
2. Cliquez sur "New Query"
3. Copiez le contenu du fichier `schema_supabase.sql`
4. Collez dans l'éditeur
5. Cliquez sur "Run" (ou Ctrl+Enter)

### 3.2 Vérifier les tables
1. Cliquez sur "Table Editor" dans le menu
2. Vous devriez voir les tables :
   - users
   - requests
   - service_categories
   - messages
   - payments
   - artisans
   - clients

## 🔧 ÉTAPE 4 : CONFIGURER RENDR

### 4.1 Créer un compte Render
1. Allez sur https://render.com
2. Sign up avec GitHub (recommandé)

### 4.2 Créer un nouveau Web Service
1. Cliquez "New +" > "Web Service"
2. Connectez votre repository GitHub
3. Sélectionnez `FIXPROGUINEA`

### 4.3 Configuration du service
**Name** : `fixpro-app`

**Region** : Choisissez la même région que Supabase si possible

**Branch** : `main`

**Runtime** : `Python 3`

**Build Command** :
```
pip install -r requirements.txt
```

**Start Command** :
```
gunicorn app:app
```

### 4.4 Variables d'environnement
Cliquez "Advanced" > "Add Environment Variable" et ajoutez :

| Variable | Valeur |
|----------|--------|
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `0` |
| `SECRET_KEY` | (générer avec `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `FIXPRO_DB_ENGINE` | `supabase` |
| `SUPABASE_URL` | (votre Project URL) |
| `SUPABASE_ANON_KEY` | (votre anon key) |
| `SUPABASE_SERVICE_ROLE_KEY` | (votre service_role key) |
| `DATABASE_URL` | (votre Database Connection String) |
| `CORS_ORIGINS` | `https://fixpro-app.onrender.com` |
| `FIXPRO_DEFAULT_COMMISSION` | `10` |
| `FIXPRO_COMMISSION_RATE` | `0.10` |
| `LOG_LEVEL` | `INFO` |

### 4.5 Déployer
Cliquez sur "Create Web Service" et attendre le déploiement (~5 minutes)

## 🔍 ÉTAPE 5 : AUDIT DE SÉCURITÉ

### 5.1 Vérifier les clés API
- ✅ `SUPABASE_SERVICE_ROLE_KEY` ne doit JAMAIS être exposée
- ✅ `DATABASE_URL` ne doit contenir que des variables d'environnement
- ✅ `SECRET_KEY` doit être unique et fort

### 5.2 Tester la connexion
1. Une fois déployé, allez sur l'URL Render
2. Testez : `https://votre-app.onrender.com/health`
3. Devrait retourner : `{"status": "ok", "environment": "production", "debug": false}`

### 5.3 Vérifier les headers de sécurité
```bash
curl -I https://votre-app.onrender.com/
```
Devrait contenir :
- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`

## 📊 ÉTAPE 6 : MONITORING

### 6.1 Dashboard Render
- Logs en temps réel
- Métriques de performance
- Alertes automatiques

### 6.2 Dashboard Supabase
- Statistiques base de données
- Monitoring des requêtes
- Backup automatique

## 🚨 DÉPANNAGE

### Erreur de connexion PostgreSQL
**Symptôme** : "could not connect to server"
**Solution** :
1. Vérifiez `DATABASE_URL` dans Render
2. Vérifiez que le mot de passe est correct
3. Vérifiez que votre IP est autorisée dans Supabase Settings > Database

### WebSocket ne fonctionne pas
**Symptôme** : Chat ne fonctionne pas
**Solution** :
1. Render supporte WebSocket nativement
2. Vérifiez que Flask-SocketIO est dans requirements.txt
3. Vérifiez les logs Render pour erreurs

### Variables d'environnement non chargées
**Symptôme** : Erreur "missing environment variable"
**Solution** :
1. Vérifiez les noms exacts dans Render
2. Redéployez après modification des variables
3. Vérifiez les logs Render

## ✅ CHECKLIST FINALE

- [ ] Projet Supabase créé
- [ ] Schéma base de données importé
- [ ] Clés API récupérées et notées
- [ ] Compte Render créé
- [ ] Repository GitHub connecté
- [ ] Variables d'environnement configurées
- [ ] Application déployée
- [ ] Health check fonctionne
- [ ] Headers de sécurité vérifiés
- [ ] WebSocket testé
- [ ] Monitoring actif

## 🎯 RÉSULTAT FINAL

Votre application FixPro sera :
- ✅ Hébergée sur Render (gratuit pour commencer)
- ✅ Base de données Supabase PostgreSQL (gratuit pour commencer)
- ✅ WebSocket fonctionnel
- ✅ Sécurisée avec headers HTTP
- ✅ Monitoring actif
- ✅ Backup automatique

**Coût mensuel estimé** : $0 (free tiers suffisant pour le démarrage)