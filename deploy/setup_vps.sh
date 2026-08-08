#!/bin/bash
# Script d'installation rapide pour VPS Ubuntu (à exécuter en tant que root ou via sudo)
# Ce script : installe Python, pip, git, nginx, certbot; crée un utilisateur 'fixpro', clone le repo,
# créé un venv, installe les dépendances, configure systemd et Nginx.

set -e
PROJECT_USER=fixpro
PROJECT_DIR=/home/$PROJECT_USER/fixpro
REPO_URL="REPLACE_WITH_YOUR_GIT_REPO"
SERVICE_FILE=/etc/systemd/system/fixpro.service
NGINX_CONF=/etc/nginx/sites-available/fixpro
DOMAIN=your.domain.com

echo "== Mise à jour du système =="
apt update && apt upgrade -y

echo "== Installer dépendances =="
apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx

# Créer utilisateur projet
if ! id -u $PROJECT_USER > /dev/null 2>&1; then
  adduser --disabled-password --gecos "" $PROJECT_USER
fi

# Cloner ou mettre à jour le repo
if [ -d "$PROJECT_DIR" ]; then
  echo "Repo existe déjà, pull..."
  su - $PROJECT_USER -c "cd $PROJECT_DIR && git pull"
else
  su - $PROJECT_USER -c "git clone $REPO_URL $PROJECT_DIR"
fi

# Créer venv et installer dépendances
su - $PROJECT_USER -c "cd $PROJECT_DIR && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"

# Copier le service systemd fourni (assume présent dans deploy/fixpro.service)
cp $PROJECT_DIR/deploy/fixpro.service $SERVICE_FILE
sed -i "s|/home/youruser/fixpro|$PROJECT_DIR|g" $SERVICE_FILE
sed -i "s|/home/youruser/fixpro/.venv/bin|$PROJECT_DIR/.venv/bin|g" $SERVICE_FILE

systemctl daemon-reload
systemctl enable fixpro.service
systemctl start fixpro.service

# Configurer Nginx
cat > $NGINX_CONF <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -sf $NGINX_CONF /etc/nginx/sites-enabled/fixpro
nginx -t && systemctl reload nginx

# Obtenir certificat Let's Encrypt (Certbot)
certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m admin@${DOMAIN}

echo "== Déploiement terminé. Vérifie les logs systemd: sudo journalctl -u fixpro -f"