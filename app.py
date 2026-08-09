"""Point d'entree pour l'execution locale : python app.py"""

from fixpro_app import app

if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"],
            debug=app.config["DEBUG"])
