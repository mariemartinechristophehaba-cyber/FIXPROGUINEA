# FixPro - Plateforme de mise en relation Artisan/Client

## 🚀 À propos

FixPro est une plateforme web sécurisée qui met en relation des clients ayant besoin de services à domicile avec des artisans qualifiés. L'application inclut l'authentification, la gestion des profils, un système de demandes, messagerie, et paiement contrôlé.

## ✨ Fonctionnalités

- 🔐 **Sécurité renforcée** : Rate limiting, validation des formulaires, headers HTTP sécurisés
- 👥 **Gestion des utilisateurs** : Inscription client/artisan avec profils détaillés
- 📋 **Système de demandes** : Création et suivi des demandes d'intervention
- 💬 **Messagerie** : Communication entre clients et artisans (polling HTTP sur Vercel, WebSocket en local)
- 💰 **Paiement sécurisé** : Système de devis et paiement contrôlé
- 🛡️ **Production-ready** : Configuration séparée dev/prod, logging complet
- ☁️ **Multi-plateforme** : Support Vercel (serverless) et déploiement traditionnel

## 📋 Prérequis

- Python 3.8+
- Supabase account (pour déploiement Vercel)

## 🛠️ Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/mariemartinechristophehaba-cyber/FIXPROGUINEA.git
cd fixpro
```

### 2. Créer et activer l'environnement virtuel

**Windows PowerShell:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/Mac:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configuration

Créer un fichier `.env` à partir de l'exemple :

```bash
cp .env.example .env
```

Générer un secret key sécurisé :

```python
python -c "import secrets; print(secrets.token_hex(32))"
```

Remplacer le secret key dans votre fichier `.env` avec la valeur générée.

### 5. Lancer l'application

```bash
python app.py
```

L'application sera accessible sur `http://localhost:5000`

## 🚀 Déploiement Vercel

### Prérequis

1. **Compte Supabase** : Créez un projet sur https://supabase.com
2. **Compte Vercel** : Créez un compte sur https://vercel.com avec GitHub

### Étape 1 : Configurer Supabase

1. Créez un nouveau projet Supabase
2. Exécutez le schéma SQL depuis `schema_supabase.sql` dans le SQL Editor de Supabase
3. Copiez les clés depuis le dashboard Supabase :
   - Project URL
   - Anon Key
   - Service Role Key
   - Connection String (DATABASE_URL)

### Étape 2 : Connecter GitHub à Vercel

1. Connectez-vous à Vercel avec GitHub
2. Cliquez sur "Add New..." > "Project"
3. Sélectionnez le repository FIXPROGUINEA
4. Configurez le projet :
   - **Framework Preset**: Python
   - **Root Directory**: `./`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`

### Étape 3 : Variables d'environnement Vercel

Ajoutez ces variables dans les Environment Variables Vercel :

```bash
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=votre_secret_key_ici
FIXPRO_DB_ENGINE=supabase
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_ANON_KEY=votre_cle_anon
SUPABASE_SERVICE_ROLE_KEY=votre_cle_service_role
DATABASE_URL=postgresql://postgres:password@db.votre-projet.supabase.co:5432/postgres
CORS_ORIGINS=https://votre-app.vercel.app
FIXPRO_DEFAULT_COMMISSION=10
FIXPRO_COMMISSION_RATE=0.10
LOG_LEVEL=INFO
```

### Étape 4 : Déployer

Cliquez sur "Deploy" et attendez le build (~2-3 minutes). Vercel déploiera automatiquement à chaque push sur la branche main.

**Note importante** : Sur Vercel, le chat utilise le polling HTTP au lieu des WebSockets (limitation serverless). En local, les WebSockets sont utilisés pour le temps réel.

## 🔒 Sécurité

L'application inclut plusieurs mesures de sécurité :

- **Rate limiting** : Protection contre DoS et brute force
- **Validation des formulaires** : Email et mot de passe stricts
- **Headers HTTP sécurisés** : X-Frame-Options, X-XSS-Protection, etc.
- **Configuration séparée** : Environnements dev/prod/test
- **Logging complet** : Traçabilité des erreurs et événements

Pour le déploiement en production, consultez le guide [DEPLOYMENT_SECURITY.md](DEPLOYMENT_SECURITY.md).

## 🧪 Tests

Lancer les tests de sécurité :

```bash
python quick_test.py
```

Lancer les tests unitaires :

```bash
python -m unittest tests.test_app
```

## 📦 Autres déploiements

### Production avec Gunicorn

```bash
gunicorn -w 4 -b 0.0.0.0:5000 --env FLASK_ENV=production app:app
```

### Docker

```bash
docker build -t fixpro .
docker run -p 5000:5000 --env-file .env.production fixpro
```

### VPS (Ubuntu)

Utilisez les fichiers fournis dans le dossier `deploy/` :
- `deploy/fixpro.service` - Configuration systemd
- `deploy/nginx_fixpro.conf` - Configuration Nginx

### Render (Alternative à Vercel avec WebSocket)

Le fichier `render.yaml` est fourni pour un déploiement sur Render avec support WebSocket natif.

## 📁 Structure du projet

```
fixpro/
├── app.py                    # Point d'entrée (auto-détecte Vercel)
├── fixpro_app.py            # Application principale (avec WebSocket)
├── fixpro_app_vercel.py     # Version Vercel (sans WebSocket)
├── config.py                 # Configuration de l'application
├── requirements.txt         # Dépendances Python
├── vercel.json              # Configuration Vercel
├── .env.example            # Exemple de configuration locale
├── .env.vercel.example     # Exemple configuration Vercel/Supabase
├── .gitignore              # Fichiers ignorés par Git
├── templates/              # Templates HTML
├── static/                 # Fichiers statiques (CSS, JS)
├── api/                    # Point d'entrée Vercel
├── tests/                  # Tests unitaires
├── deploy/                 # Fichiers de déploiement
└── scripts/                # Scripts utilitaires
```

## 📝 Documentation

- [DEPLOYMENT_SECURITY.md](DEPLOYMENT_SECURITY.md) - Guide de déploiement sécurisé
- [VERCEL_GITHUB_SETUP.md](VERCEL_GITHUB_SETUP.md) - Guide détaillé Vercel
- [AUDIT_GITHUB_VERCEL.md](AUDIT_GITHUB_VERCEL.md) - Audit complet GitHub/Vercel
- [CORRECTIONS_EFFECTUEES.md](CORRECTIONS_EFFECTUEES.md) - Rapport des corrections
- [CAHIER_DE_CHARGE_FIXPRO.md](CAHIER_DE_CHARGE_FIXPRO.md) - Cahier des charges

## 🤝 Contribution

Les contributions sont les bienvenues ! Pour proposer des améliorations :

1. Fork le projet
2. Créer une branche (`git checkout -b feature/AmazingFeature`)
3. Commit les changements (`git commit -m 'Add some AmazingFeature'`)
4. Push vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT.

## 👥 Auteurs

- Équipe FixPro
- Marie Martine Christophe Haba

## 🙏 Remerciements

Merci à tous les contributeurs et utilisateurs de FixPro !
