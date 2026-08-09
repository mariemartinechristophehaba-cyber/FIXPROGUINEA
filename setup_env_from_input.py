"""
Script pour configurer le fichier .env avec les informations Supabase fournies
Utilisation: python setup_env_from_input.py "SUPABASE_URL" "ANON_KEY" "SERVICE_ROLE_KEY" "DATABASE_URL"
"""

import sys
from pathlib import Path

def setup_env_from_args():
    """Configure le fichier .env avec les arguments de ligne de commande"""
    
    if len(sys.argv) < 5:
        print("Usage: python setup_env_from_input.py \"SUPABASE_URL\" \"ANON_KEY\" \"SERVICE_ROLE_KEY\" \"DATABASE_URL\"")
        print("Exemple: python setup_env_from_input.py \"https://xxx.supabase.co\" \"eyJ...\" \"eyJ...\" \"postgresql://...\"")
        return False
    
    supabase_url = sys.argv[1]
    anon_key = sys.argv[2]
    service_role_key = sys.argv[3]
    database_url = sys.argv[4]
    
    print("=== CONFIGURATION SUPABASE ===\n")
    print(f"SUPABASE_URL: {supabase_url}")
    print(f"ANON_KEY: {anon_key[:20]}...")
    print(f"SERVICE_ROLE_KEY: {service_role_key[:20]}...")
    print(f"DATABASE_URL: {database_url[:30]}...")
    
    env_content = f"""# Configuration Supabase pour FixPro
# Généré automatiquement

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=CHANGEZ_CECI_PAR_UNE_CLE_ALÉATOIRE_LONGUE_ET_COMPLEXE

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
    
    env_file = Path(".env")
    
    try:
        with open(env_file, 'w') as f:
            f.write(env_content)
        print(f"\n✅ Fichier .env créé avec succès")
        print(f"📍 Chemin: {env_file.absolute()}")
        print("\nProchaine étape: Testez la connexion avec: python test_supabase_connection.py")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la création du fichier .env: {e}")
        return False

if __name__ == "__main__":
    setup_env_from_args()