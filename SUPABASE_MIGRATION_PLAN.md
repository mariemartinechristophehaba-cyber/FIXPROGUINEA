# PLAN DE MIGRATION SUPABASE - FIXPRO

## 🎯 OBJECTIF
Migrer l'application FixPro de SQLite/MySQL vers Supabase (PostgreSQL) et déployer sur Render.

## 📋 PRÉREQUIS

### Comptes nécessaires
- [ ] Compte Supabase (https://supabase.com)
- [ ] Compte Render (https://render.com)
- [ ] Compte GitHub (déjà configuré)

## 🔧 ÉTAPES DE MIGRATION

### ÉTAPE 1 : Configuration Supabase

1. **Créer un projet Supabase**
   - Aller sur https://supabase.com
   - Cliquer sur "New Project"
   - Nom : `fixpro-production`
   - Database Password : (générer un mot de passe fort)
   - Region : choisir la région la plus proche (ex: Eu West)
   - Wait for provisioning (~2 minutes)

2. **Récupérer les clés API**
   - Settings > API
   - Copier les informations suivantes :
     - `Project URL` (https://xxx.supabase.co)
     - `anon public` key
     - `service_role` key (garder secrète)
     - Database connection string

3. **Configurer la base de données**
   - SQL Editor > New Query
   - Exécuter le schéma FixPro (adapter pour PostgreSQL)

### ÉTAPE 2 : Adaptation du code Python

1. **Modifier requirements.txt**
   - Remplacer `mysql-connector-python` par `psycopg2-binary`
   - Ajouter `supabase` (optionnel pour features avancées)

2. **Modifier config.py**
   - Ajouter configuration Supabase
   - Adapter la connexion PostgreSQL

3. **Modifier fixpro_app.py**
   - Adapter la connexion base de données
   - Changer les requêtes SQL si nécessaire (MySQL → PostgreSQL)

### ÉTAPE 3 : Configuration Variables d'Environnement

**Variables Supabase à ajouter :**
```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DATABASE_URL=postgresql://postgres:xxx@xxx.supabase.co:5432/postgres
```

### ÉTAPE 4 : Déploiement Render

1. **Connecter GitHub à Render**
   - Sign up/Login sur Render
   - "New +" > "Web Service"
   - Connect repository GitHub

2. **Configuration du service**
   - Name : `fixpro-app`
   - Region : choisir région proche de Supabase
   - Branch : `main`
   - Runtime : `Python 3`
   - Build Command : `pip install -r requirements.txt`
   - Start Command : `gunicorn app:app`

3. **Variables d'environnement**
   - Ajouter toutes les variables Supabase
   - Ajouter `FLASK_ENV=production`
   - Ajouter `SECRET_KEY` (générer nouveau)

4. **Déployer**
   - Cliquer sur "Create Web Service"
   - Attendre le déploiement (~5 minutes)

### ÉTAPE 5 : Tests et Validation

1. **Tester la connexion**
   - Vérifier les logs Render
   - Tester l'endpoint `/health`
   - Tester l'inscription/connexion

2. **Tester WebSocket**
   - Vérifier que Flask-SocketIO fonctionne
   - Tester le chat en temps réel

3. **Audit de sécurité**
   - Vérifier que les clés API ne sont pas exposées
   - Valider les variables d'environnement
   - Tester les headers de sécurité

## 🔐 SÉCURITÉ

### Clés API à protéger
- ❌ **JAMAIS** commit de `SUPABASE_SERVICE_ROLE_KEY`
- ✅ Utiliser `SUPABASE_ANON_KEY` pour le frontend
- ✅ Garder `DATABASE_URL` dans variables d'environnement

### Variables d'environnement Render
- Render fournit un environnement sécurisé pour les variables
- Les variables ne sont jamais exposées dans le code

## 📊 MONITORING

### Render Dashboard
- Logs en temps réel
- Métriques de performance
- Alertes automatiques

### Supabase Dashboard
- Statistiques base de données
- Monitoring des requêtes
- Backup automatique

## 🚨 DÉPANNAGE

### Problèmes courants
1. **Erreur de connexion PostgreSQL**
   - Vérifier `DATABASE_URL`
   - Vérifier que l'IP est autorisée dans Supabase

2. **WebSocket ne fonctionne pas**
   - Render nécessite configuration spécifique pour WebSocket
   - Utiliser Render's native WebSocket support

3. **Variables d'environnement non chargées**
   - Vérifier les noms exacts dans Render
   - Redéployer après modification

## 📝 CHECKLIST FINALE

- [ ] Projet Supabase créé
- [ ] Clés API récupérées
- [ ] Schéma base de données importé
- [ ] Code Python adapté pour PostgreSQL
- [ ] requirements.txt mis à jour
- [ ] Variables d'environnement configurées
- [ ] Application déployée sur Render
- [ Tests fonctionnels passés
- [ ] WebSocket testé
- [ ] Monitoring configuré

## 🎯 LIVRABLES

1. Application FixPro fonctionnelle sur Render
2. Base de données Supabase connectée
3. WebSocket opérationnel
4. Monitoring actif
5. Documentation complète