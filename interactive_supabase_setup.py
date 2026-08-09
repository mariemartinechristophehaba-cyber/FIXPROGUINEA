"""
Script interactif pour configurer Supabase avec vos vraies clés
"""

import os
import secrets
from pathlib import Path

def interactive_setup():
    """Guide interactif pour configurer Supabase"""
    
    print("=== CONFIGURATION INTERACTIVE SUPABASE ===\n")
    
    print("Veuillez entrer vos informations Supabase:")
    print("(Appuyez sur Entrée pour annuler)\n")
    
    # Collecter les informations
    supabase_url = input("SUPABASE_URL (ex: https://xxx.supabase.co): ").strip()
    if not supabase_url:
        print("❌ Configuration annulée")
        return None
    
    anon_key = input("SUPABASE_ANON_KEY: ").strip()
    if not anon_key:
        print("❌ Configuration annulée")
        return None
    
    service_role_key = input("SUPABASE_SERVICE_ROLE_KEY: ").strip()
    if not service_role_key:
        print("❌ Configuration annulée")
        return None
    
    database_url = input("DATABASE_URL (ex: postgresql://postgres:password@db.xxx.supabase.co:5432/postgres): ").strip()
    if not database_url:
        print("❌ Configuration annulée")
        return None
    
    # Générer une clé secrète
    secret_key = secrets.token_hex(32)
    
    print(f"\n✅ Informations collectées avec succès")
    print(f"SECRET_KEY généré: {secret_key}")
    
    # Créer le contenu .env
    env_content = f"""# Configuration Supabase pour FixPro
# Généré automatiquement par interactive_supabase_setup.py

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY={secret_key}

# Base de données
FIXPRO_DB_ENGINE=supabase
FIXPRO_DB_PATH=fixpro.db

# Configuration Supabase
SUPABASE_URL={supabase_url}
SUPABASE_ANON_KEY={anon_key}
SUPABASE_SERVICE_ROLE_KEY={service_role_key}

# Database Connection String (PostgreSQL)
DATABASE_URL={database_url}

# Serveur
PORT=5000
HOST=0.0.0.0

# Configuration CORS
CORS_ORIGINS=*

# Commission FixPro
FIXPRO_DEFAULT_COMMISSION=10
FIXPRO_COMMISSION_RATE=0.10

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/fixpro.log
"""
    
    # Écrire dans le fichier .env
    env_file = Path(".env")
    try:
        with open(env_file, 'w') as f:
            f.write(env_content)
        print(f"\n✅ Fichier .env créé avec succès")
        print(f"📍 Chemin: {env_file.absolute()}")
        print("\nProchaine étape: Lancez la migration avec: python migrate_to_supabase.py")
        return env_file
    except Exception as e:
        print(f"❌ Erreur lors de la création du fichier .env: {e}")
        print("\nVoici le contenu à copier manuellement:")
        print("=" * 50)
        print(env_content)
        print("=" * 50)
        return None

if __name__ == "__main__":
    interactive_setup()