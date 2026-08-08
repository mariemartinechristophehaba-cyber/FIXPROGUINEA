"""
Point d'entrée pour Vercel
Adapter pour le déploiement serverless
"""

from fixpro_app import app

# Export l'application pour Vercel
app_handler = app

# Pour le développement local
if __name__ == "__main__":
    from fixpro_app import socketio, logger
    logger.info("Démarrage local de FixPro")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)