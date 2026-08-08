Déployer sur Render (PaaS)

1. Crée un compte sur https://render.com et crée un nouveau "Web Service" en connectant ton dépôt Git.
2. Branche la branche souhaitée (ex: main).
3. Build Command: `pip install -r requirements.txt`
   Start Command: `gunicorn -w 4 -b 0.0.0.0:$PORT app:app`
4. Dans Settings -> Environment, ajoute les variables d'environnement:
   - `FIXPRO_DB_HOST` (hostname MySQL)
   - `FIXPRO_DB_USER`
   - `FIXPRO_DB_PASS`
   - `FIXPRO_DB_NAME`
   - `FIXPRO_COMMISSION_RATE` (ex: 0.10)
5. Pour la base de données, crée un service MySQL add-on dans Render ou utilise un MySQL managé externe. Puis exécute `setup_database.sql` sur cette base.
6. Déploie; Render détectera le `Procfile` et lancera `gunicorn`.

Notes:
- Assure-toi que le réseau/firewall entre ton app et la base autorise la connexion.
- Pour SSL, Render fournit TLS automatiquement.
