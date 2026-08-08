import os
import logging

# Détecter l'environnement
is_vercel = os.getenv('VERCEL') or os.getenv('VERCEL_ENV')

if is_vercel:
    # Version pour Vercel (sans WebSocket)
    from fixpro_app_vercel import app, logger
else:
    # Version locale (avec WebSocket)
    from fixpro_app import app, socketio, logger

if __name__ == "__main__":
    logger.info(f"Démarrage de FixPro via app.py")
    logger.info(f"Environnement: {app.config.get('FLASK_ENV', 'development')}")
    logger.info(f"Debug: {app.config.get('DEBUG', False)}")
    logger.info(f"Vercel: {is_vercel}")
    
    if is_vercel:
        # Version Vercel sans WebSocket
        app.run(
            host=app.config.get("HOST", "0.0.0.0"),
            port=app.config.get("PORT", 5000),
            debug=app.config.get("DEBUG", False)
        )
    else:
        # Version locale avec WebSocket
        socketio.run(
            app, 
            host=app.config.get("HOST", "0.0.0.0"), 
            port=app.config.get("PORT", 5000), 
            debug=app.config.get("DEBUG", False)
        )
