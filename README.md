# FixPro - Plateforme de mise en relation Artisan/Client

## 🚀 À propos

FixPro est une plateforme web sécurisée qui met en relation des clients ayant besoin de services à domicile avec des artisans qualifiés. L'application inclut l'authentification, la gestion des profils, un système de demandes, chat en temps réel, et paiement contrôlé.

## ✨ Fonctionnalités

- 🔐 **Sécurité renforcée** : Rate limiting, validation des formulaires, headers HTTP sécurisés
- 👥 **Gestion des utilisateurs** : Inscription client/artisan avec profils détaillés
- 📋 **Système de demandes** : Création et suivi des demandes d'intervention
- 💬 **Chat en temps réel** : Communication entre clients et artisans via WebSocket
- 💰 **Paiement sécurisé** : Système de devis et paiement contrôlé
- 🛡️ **Production-ready** : Configuration séparée dev/prod, logging complet

## 📋 Prérequis

- Python 3.8+
- MySQL (optionnel - SQLite utilisé par défaut)

## 🛠️ Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/votre-username/fixpro.git
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

## 📦 Déploiement

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

### PaaS (Render, Railway)

Le fichier `Procfile` est fourni pour les déploiements PaaS.

## 📁 Structure du projet

```
fixpro/
├── app.py                    # Point d'entrée
├── config.py                 # Configuration de l'application
├── fixpro_app.py            # Application principale
├── requirements.txt         # Dépendances Python
├── .env.example            # Exemple de configuration
├── .gitignore              # Fichiers ignorés par Git
├── templates/              # Templates HTML
├── static/                 # Fichiers statiques (CSS, JS)
├── tests/                  # Tests unitaires
├── deploy/                 # Fichiers de déploiement
└── scripts/                # Scripts utilitaires
```

## 📝 Documentation

- [DEPLOYMENT_SECURITY.md](DEPLOYMENT_SECURITY.md) - Guide de déploiement sécurisé
- [CORRECTIONS_EFFECTUEES.md](CORRECTIONS_EFFECTUEES.md) - Rapport des corrections de sécurité
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
