# Guide de Déploiement Sécurisé - FixPro

## 🔐 Configuration de Production

### 1. Variables d'Environnement Obligatoires

Avant tout déploiement en production, vous devez configurer les variables d'environnement suivantes :

```bash
# Copier le fichier de configuration exemple
cp config_production.example .env.production

# Éditer le fichier avec des valeurs uniques et sécurisées
nano .env.production
```

### 2. Sécurisation du Secret Key

Générez un secret key fort et unique :

```python
import secrets
print(secrets.token_hex(32))
```

Remplacez `SECRET_KEY` dans `.env.production` avec la valeur générée.

### 3. Configuration CORS

En production, ne JAMAIS utiliser `CORS_ORIGINS=*`. Configurez explicitement vos domaines :

```bash
CORS_ORIGINS=https://votre-domaine.com,https://www.votre-domaine.com
```

### 4. Base de Données

Pour la production, utilisez MySQL plutôt que SQLite :

```bash
FIXPRO_DB_ENGINE=mysql
FIXPRO_DB_HOST=votre-host-mysql
FIXPRO_DB_USER=fixpro_user
FIXPRO_DB_PASS=mot_de_passe_tres_complex
FIXPRO_DB_NAME=FixPro
```

## 🚀 Déploiement

### Installation des Dépendances

```bash
pip install -r requirements.txt
```

### Configuration de l'Environnement

```bash
export FLASK_ENV=production
export FLASK_DEBUG=0
```

Ou utilisez le fichier `.env.production` :

```bash
python-dotenv -f .env.production run python app.py
```

### Avec Gunicorn (Recommandé)

```bash
gunicorn -w 4 -b 0.0.0.0:5000 --env FLASK_ENV=production app:app
```

### Avec Docker

```bash
docker build -t fixpro .
docker run -p 5000:5000 --env-file .env.production fixpro
```

## 🛡️ Sécurité HTTPS

### Configuration Nginx avec SSL

```nginx
server {
    listen 443 ssl http2;
    server_name votre-domaine.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Avec Certbot (Let's Encrypt)

```bash
sudo certbot --nginx -d votre-domaine.com
```

## 📊 Monitoring et Logging

Les logs sont stockés dans `logs/fixpro.log` avec rotation automatique.

### Configuration Logrotate

Créez `/etc/logrotate.d/fixpro` :

```
/path/to/fixpro/logs/fixpro.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
}
```

## 🔍 Vérifications de Sécurité

### Avant le Déploiement

1. ✅ Vérifier que `.env.production` n'est pas versionné
2. ✅ Vérifier que le secret key est unique et fort
3. ✅ Vérifier que CORS est restreint
4. ✅ Vérifier que FLASK_DEBUG=0
5. ✅ Vérifier que HTTPS est configuré
6. ✅ Vérifier que les headers de sécurité sont actifs

### Test de Sécurité

```bash
# Test des headers de sécurité
curl -I https://votre-domaine.com

# Vérifier la présence des headers :
# X-Frame-Options: SAMEORIGIN
# X-Content-Type-Options: nosniff
# X-XSS-Protection: 1; mode=block
# Strict-Transport-Security: max-age=31536000
```

## 🚨 Actions en Cas de Problème

### Si le Secret Key Est Compromis

1. Générer immédiatement un nouveau secret key
2. Mettre à jour `.env.production`
3. Redémarrer l'application
4. Invalider toutes les sessions existantes

### Si une Attaque Est Détectée

1. Consulter les logs dans `logs/fixpro.log`
2. Bloquer l'IP attaquante via le firewall
3. Augmenter les limites de rate limiting
4. Notifier les administrateurs

## 📞 Support

Pour toute question de sécurité, contactez l'équipe technique.