import os
import logging

# Import de l'application principale
from fixpro_app import app, socketio, logger

if __name__ == "__main__":
    logger.info(f"Démarrage de FixPro via app.py")
    logger.info(f"Environnement: {app.config.get('FLASK_ENV', 'development')}")
    logger.info(f"Debug: {app.config.get('DEBUG', False)}")
    
    # Démarrage avec SocketIO pour le chat en temps réel
    socketio.run(
        app, 
        host=app.config.get("HOST", "0.0.0.0"), 
        port=app.config.get("PORT", 5000), 
        debug=app.config.get("DEBUG", False)
    )
