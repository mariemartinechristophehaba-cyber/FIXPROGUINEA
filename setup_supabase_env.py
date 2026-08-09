"""
Script pour configurer Supabase - Génère un fichier .env avec vos clés
"""

import os
import secrets
from pathlib import Path

def setup_supabase_env():
    """Guide l'utilisateur pour configurer Supabase"""
    
    try:
        print("=== CONFIGURATION SUPABASE POUR FIXPRO ===\n")
        
        print("Vous avez besoin des informations suivantes de votre dashboard Supabase:")
        print("1. Project URL (https://xxx.supabase.co)")
        print("2. anon public key")
        print("3. service_role key")
        print("4. Database password")
        print("5. Database connection string")
        print()
        
        # Générer une clé secrète
        secret_key = secrets.token_hex(32)
        print(f"SECRET_KEY généré: {secret_key}")
        print()
        
        print("Création du fichier template...")
        
        env_content = f"""# Configuration Supabase pour FixPro
# IMPORTANT: Remplacez les valeurs placeholder par vos vraies clés Supabase

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY={secret_key}

# Base de données
FIXPRO_DB_ENGINE=supabase
FIXPRO_DB_PATH=fixpro.db

# Configuration Supabase
# Obtenez ces valeurs depuis votre dashboard Supabase > Settings > API
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# Database Connection String (PostgreSQL)
# Format: postgresql://postgres:[password]@db.[project-id].supabase.co:5432/postgres
DATABASE_URL=postgresql://postgres:your-password@db.your-project-id.supabase.co:5432/postgres

# Serveur
PORT=5000
HOST=0.0.0.0

# Configuration CORS (séparer par des virgules)
CORS_ORIGINS=*

# Commission FixPro
FIXPRO_DEFAULT_COMMISSION=10
FIXPRO_COMMISSION_RATE=0.10

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/fixpro.log
"""
        
        temp_file = Path("env_supabase_template.txt")
        
        with open(temp_file, 'w') as f:
            f.write(env_content)
        
        print(f"✅ Template créé dans {temp_file}")
        print("\nÉtapes suivantes:")
        print("1. Copiez le contenu de env_supabase_template.txt")
        print("2. Remplacez les valeurs placeholder par vos vraies clés Supabase")
        print("3. Créez ou modifiez votre fichier .env avec ces valeurs")
        print("4. Lancez la migration avec: python migrate_to_supabase.py")
        return temp_file
        
    except Exception as e:
        print(f"Erreur: {e}")
        return None

if __name__ == "__main__":
    setup_supabase_env()