"""
Script pour configurer Supabase directement dans le fichier .env
"""

import os
from pathlib import Path

def configure_supabase():
    """Configure Supabase dans le fichier .env"""
    
    print("=== CONFIGURATION SUPABASE ===\n")
    
    # Clé secrète par défaut
    secret_key = "CHANGEZ_CECI_PAR_UNE_CLE_ALÉATOIRE_LONGUE_ET_COMPLEXE"
    print(f"SECRET_KEY par défaut: {secret_key}")
    
    # Configuration par défaut (placeholders)
    env_content = """# Configuration Supabase pour FixPro
# IMPORTANT: Remplacez les valeurs ci-dessous par vos vraies clés Supabase

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=CHANGEZ_CECI_PAR_UNE_CLE_ALÉATOIRE_LONGUE_ET_COMPLEXE

# Base de données
FIXPRO_DB_ENGINE=supabase
FIXPRO_DB_PATH=fixpro.db

# Configuration Supabase
# Remplacez ces valeurs par vos vraies clés Supabase
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# Database Connection String (PostgreSQL)
# Remplacez par votre vraie connection string
DATABASE_URL=postgresql://postgres:your-password@db.your-project-id.supabase.co:5432/postgres

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
    
    env_file = Path(".env")
    
    try:
        with open(env_file, 'w') as f:
            f.write(env_content)
        print(f"\n✅ Fichier .env créé avec succès")
        print(f"📍 Chemin: {env_file.absolute()}")
        print("\n⚠️  IMPORTANT: Modifiez le fichier .env et remplacez les valeurs placeholder par vos vraies clés Supabase")
        print("\nUne fois configuré, testez la connexion avec: python test_supabase_connection.py")
        return env_file
    except Exception as e:
        print(f"❌ Erreur lors de la création du fichier .env: {e}")
        return None

if __name__ == "__main__":
    configure_supabase()