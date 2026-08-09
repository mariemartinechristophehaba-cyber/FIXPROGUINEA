"""
Point d'entrée pour Vercel
Export l'application Flask pour le déploiement serverless
"""

from fixpro_app import app

# Export l'application pour Vercel
app_handler = app