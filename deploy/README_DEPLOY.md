Déploiement et lancement

Docker (recommandé pour production locale / serveur):

```bash
# depuis le dossier deploy/
docker compose up -d --build
# vérifiez les logs
docker compose logs -f web
```

Systemd (sur Linux remote):

1. Copier `fixpro.service.example` vers `/etc/systemd/system/fixpro.service` et adapter `WorkingDirectory` et `Environment`.
2. Recharger systemd et activer le service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fixpro
sudo journalctl -u fixpro -f
```

Lancement local (développement):

```powershell
# Windows: lancer directement
C:/Path/To/python.exe app.py
```

Notes:
- `gunicorn` n'est pas pris en charge sur Windows; utilisez la méthode Docker ou systemd sur Linux pour gunicorn.
- Fichier Docker et `docker-compose.yml` existent dans `deploy/`.
