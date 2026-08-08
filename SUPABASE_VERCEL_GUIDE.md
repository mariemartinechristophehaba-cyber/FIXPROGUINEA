# Guide de Configuration Supabase pour Vercel - FixPro

## 🎯 Objectif

Ce guide vous explique comment configurer Supabase pour le déploiement de FixPro sur Vercel. Supabase est OBLIGATOIRE pour Vercel car la plateforme serverless ne supporte pas les fichiers persistants comme SQLite.

## 📋 Prérequis

- Compte Supabase (gratuit sur https://supabase.com)
- Compte Vercel (gratuit sur https://vercel.com)
- Repository GitHub FIXPROGUINEA connecté à Vercel

---

## 🚀 ÉTAPE 1 : Créer un Projet Supabase

### 1.1 Inscription

1. Allez sur https://supabase.com
2. Cliquez sur "Start your project"
3. Connectez-vous avec GitHub (recommandé)

### 1.2 Créer le Projet

1. Cliquez sur "New Project"
2. Remplissez les informations :
   - **Name**: `fixpro-prod` (ou votre choix)
   - **Database Password**: Générez un mot de passe fort et sauvegardez-le !
   - **Region**: Choisissez la région la plus proche de vos utilisateurs (ex: West Africa)
   - **Pricing Plan**: Free (suffisant pour commencer)

3. Cliquez sur "Create new project"
4. Attendez ~2 minutes pendant que Supabase initialise votre projet

---

## 🔧 ÉTAPE 2 : Exécuter le Schéma de Base de Données

### 2.1 Accéder au SQL Editor

1. Dans le dashboard Supabase, cliquez sur "SQL Editor" dans la barre latérale
2. Cliquez sur "New query"

### 2.2 Exécuter le Schéma

1. Copiez le contenu du fichier `schema_supabase.sql` depuis votre repository
2. Collez-le dans le SQL Editor
3. Cliquez sur "Run" (ou `Ctrl+Enter`)
4. Vérifiez qu'il n'y a pas d'erreurs dans les résultats

Le schéma crée les tables suivantes :
- `users` - Utilisateurs (clients et artisans)
- `requests` - Demandes d'intervention
- `messages` - Messages de chat
- `payments` - Paiements
- `service_categories` - Catégories de services
- `artisans` - Artisans
- `clients` - Clients

---

## 🔑 ÉTAPE 3 : Récupérer les Clés API

### 3.1 Accéder aux Settings

1. Dans le dashboard Supabase, cliquez sur "Settings" (icône ⚙️)
2. Cliquez sur "API"

### 3.2 Copier les Clés Nécessaires

Vous aurez besoin de ces 4 clés pour Vercel :

#### 1. Project URL
```
https://votre-projet-id.supabase.co
```
- Copiez depuis "Project URL"
- Exemple: `https://abcxyz.supabase.co`

#### 2. Anon Key
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```
- Copiez depuis "anon public"
- C'est la clé publique pour les accès client

#### 3. Service Role Key
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```
- Copiez depuis "service_role" (SECRET!)
- ⚠️ NE JAMAIS PARTAGER CETTE CLÉ
- Utilisée uniquement côté serveur

#### 4. Database URL
```
postgresql://postgres.votre-projet-id:[YOUR-PASSWORD]@db.votre-projet-id.supabase.co:5432/postgres
```
- Copiez depuis "Connection string"
- Remplacez `[YOUR-PASSWORD]` par votre mot de passe de base de données
- Format: `postgresql://postgres.votre-projet-id:password@db.votre-projet-id.supabase.co:5432/postgres`

---

## ⚙️ ÉTAPE 4 : Configurer les Variables Vercel

### 4.1 Accéder aux Settings Vercel

1. Allez sur votre dashboard Vercel
2. Sélectionnez votre projet FixPro
3. Cliquez sur "Settings" > "Environment Variables"

### 4.2 Ajouter les Variables

Ajoutez chaque variable avec sa valeur correspondante :

| Variable | Valeur | Notes |
|----------|--------|-------|
| `FLASK_ENV` | `production` | Environnement de production |
| `FLASK_DEBUG` | `0` | Mode debug désactivé |
| `SECRET_KEY` | *générer* | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FIXPRO_DB_ENGINE` | `supabase` | Utiliser Supabase |
| `SUPABASE_URL` | *votre URL* | Ex: `https://abcxyz.supabase.co` |
| `SUPABASE_ANON_KEY` | *votre clé anon* | Clé publique Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | *votre clé service* | ⚠️ Clé secrète côté serveur |
| `DATABASE_URL` | *votre connection string* | Connection string PostgreSQL |
| `CORS_ORIGINS` | *votre domaine Vercel* | Ex: `https://fixpro-app.vercel.app` |
| `FIXPRO_DEFAULT_COMMISSION` | `10` | Commission par défaut |
| `FIXPRO_COMMISSION_RATE` | `0.10` | Taux de commission (10%) |
| `LOG_LEVEL` | `INFO` | Niveau de logging |

### 4.3 Important pour CORS

Après le premier déploiement Vercel :
1. Notez l'URL de votre application (ex: `https://fixpro-app.vercel.app`)
2. Revenez dans les Environment Variables Vercel
3. Mettez à jour `CORS_ORIGINS` avec cette URL exacte
4. Redéployez l'application

---

## 🚀 ÉTAPE 5 : Déployer sur Vercel

### 5.1 Premier Déploiement

1. Dans Vercel, cliquez sur "Deployments"
2. Cliquez sur "Redeploy" si le projet est déjà importé
3. Attendez le build (~2-3 minutes)
4. Vérifiez qu'il n'y a pas d'erreurs dans les logs

### 5.2 Vérifier le Déploiement

1. Cliquez sur l'URL fournie par Vercel
2. Testez l'inscription d'un nouvel utilisateur
3. Vérifiez que l'utilisateur apparaît dans Supabase :
   - Allez dans Supabase > Table Editor
   - Ouvrez la table `users`
   - Vérifiez que le nouvel utilisateur est là

---

## 🔍 ÉTAPE 6 : Vérifications et Tests

### 6.1 Tester la Connexion Base de Données

```bash
# Dans votre terminal local
python test_supabase_connection.py
```

Si vous n'avez pas ce fichier, créez-le temporairement :

```python
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

try:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    print("✅ Connexion Supabase réussie!")
    conn.close()
except Exception as e:
    print(f"❌ Erreur de connexion: {e}")
```

### 6.2 Tester l'Application

1. **Inscription**: Créez un compte client
2. **Connexion**: Connectez-vous avec ce compte
3. **Profil**: Modifiez votre profil
4. **Demande**: Créez une demande d'intervention
5. **Vérification**: Allez dans Supabase > Table Editor > `requests` pour vérifier

---

## 🛡️ ÉTAPE 7 : Sécurité Supplémentaire

### 7.1 Restreindre les Accès Supabase

1. Allez dans Supabase > Authentication > Policies
2. Créez des Row Level Security (RLS) policies :
   - Les utilisateurs ne peuvent voir que leurs propres données
   - Les clients ne peuvent voir que leurs demandes
   - Les artisans ne peuvent voir que les demandes qui leur sont assignées

### 7.2 Activer l'Authentification 2FA

1. Allez dans Supabase > Settings > Authentication
2. Activez "Enable 2FA" pour votre compte admin

### 7.3 Configurer les Backups

Supabase Free inclut des backups automatiques quotidiens. Pour plus de sécurité :
1. Allez dans Supabase > Settings > Database
2. Vérifiez que "Daily backups" est activé

---

## 📊 ÉTAPE 8 : Monitoring

### 8.1 Surveiller les Logs Vercel

1. Allez dans Vercel > Deployments
2. Cliquez sur le déploiement actuel
3. Onglet "Function Logs" pour voir les erreurs

### 8.2 Surveiller les Logs Supabase

1. Allez dans Supabase > Logs
2. Filtrez par "database" ou "api"
3. Surveillez les requêtes lentes ou les erreurs

### 8.3 Métriques d'Utilisation

1. Supabase Dashboard > Usage Metrics
2. Vérifiez :
   - Database size (limite: 500MB sur Free)
   - Bandwidth (limite: 2GB/mois sur Free)
   - API requests (limite: 50k/mois sur Free)

---

## 🚨 Dépannage

### Erreur: "Connection refused"

**Cause**: Mauvais DATABASE_URL ou mot de passe incorrect

**Solution**:
1. Vérifiez que le mot de passe dans DATABASE_URL correspond à celui de Supabase
2. Vérifiez que l'URL est correcte (pas d'espaces ou caractères spéciaux)
3. Régénérez le mot de passe dans Supabase si nécessaire

### Erreur: "Table does not exist"

**Cause**: Le schéma n'a pas été exécuté

**Solution**:
1. Allez dans Supabase > SQL Editor
2. Réexécutez le schéma `schema_supabase.sql`
3. Vérifiez que toutes les tables sont créées dans Table Editor

### Erreur: "CORS error"

**Cause**: CORS_ORIGINS mal configuré

**Solution**:
1. Vérifiez que CORS_ORIGINS contient votre domaine Vercel exact
2. Pas de wildcard (*) en production
3. Redéployez après modification

### Erreur: "Module not found"

**Cause**: requirements.txt incomplet

**Solution**:
1. Vérifiez que `requirements.txt` contient toutes les dépendances
2. Redéployez sur Vercel

---

## ✅ Checklist Finale

Avant de considérer le déploiement comme terminé :

- [ ] Projet Supabase créé
- [ ] Schéma SQL exécuté sans erreurs
- [ ] Clés API copiées correctement
- [ ] Variables d'environnement Vercel configurées
- [ ] SECRET_KEY généré et unique
- [ ] CORS_ORIGINS configuré avec le domaine Vercel
- [ ] Premier déploiement réussi
- [ ] Inscription testée
- [ ] Données vérifiées dans Supabase
- [ ] Logs surveillés
- [ ] Backups activés

---

## 🎉 Conclusion

Votre application FixPro est maintenant configurée pour Vercel avec Supabase !

**Prochaines étapes** :
1. Surveillez les premiers jours d'utilisation
2. Configurez des alertes pour les erreurs
3. Planifiez une migration vers les plans payants si vous dépassez les limites Free

**Support** :
- Documentation Supabase: https://supabase.com/docs
- Documentation Vercel: https://vercel.com/docs
- Issues GitHub: https://github.com/mariemartinechristophehaba-cyber/FIXPROGUINEA/issues
