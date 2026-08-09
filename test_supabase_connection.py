"""
Script de test de connexion Supabase
Teste la connexion avec les informations du fichier .env
"""

import os
import psycopg2
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

def test_supabase_connection():
    """Teste la connexion à Supabase"""
    
    print("=== TEST DE CONNEXION SUPABASE ===\n")
    
    database_url = os.getenv('DATABASE_URL')
    supabase_url = os.getenv('SUPABASE_URL')
    
    print(f"DATABASE_URL: {'***CONFIGURÉ***' if database_url else 'MANQUANT'}")
    print(f"SUPABASE_URL: {supabase_url if supabase_url else 'MANQUANT'}")
    print()
    
    if not database_url:
        print("❌ DATABASE_URL non trouvé dans le fichier .env")
        print("Veuillez configurer le fichier .env avec vos informations Supabase")
        return False
    
    try:
        print("Tentative de connexion à Supabase...")
        conn = psycopg2.connect(database_url)
        print("✅ Connexion réussie à Supabase!")
        
        # Test simple query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"📊 Version PostgreSQL: {version[0]}")
        
        # Vérifier les tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        print(f"📋 Tables trouvées: {tables}")
        
        cursor.close()
        conn.close()
        
        print("\n✅ CONNEXION SUPABASE CONFIRMÉE")
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Erreur de connexion: {e}")
        print("\nVérifiez vos informations dans le fichier .env:")
        print("- DATABASE_URL doit être au format: postgresql://postgres:password@db.xxx.supabase.co:5432/postgres")
        print("- Le mot de passe doit être correct")
        print("- Votre IP doit être autorisée dans les paramètres Supabase")
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        return False

if __name__ == "__main__":
    test_supabase_connection()