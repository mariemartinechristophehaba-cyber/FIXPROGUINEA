Déployer sur Railway

1. Crée un projet sur https://railway.app et connecte ton repo Git.
2. Ajoute un service "Web" pointant sur la branche principale.
3. Dans "Environment", ajoute les variables d'environnement listées dans `.env.example`.
4. Ajoute un plugin MySQL via Railway pour créer une base de données managée, récupère les credentials et mets-les en variables d'environnement.
5. Configuration du build: `pip install -r requirements.txt`
   Start command: `gunicorn -w 4 -b 0.0.0.0:$PORT app:app`
6. Exécute `setup_database.sql` sur la base Railway (via mysql client ou Workbench).

Railway fournit automatiquement un domaine HTTPS pour l'application.
