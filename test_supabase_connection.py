#!/usr/bin/env python
"""
Script de test de connexion Supabase pour FixPro
Ce script vérifie que la configuration PostgreSQL/Supabase fonctionne correctement
"""
import sys
import os
sys.path.insert(0, '.')

# Charger les variables d'environnement depuis .env si disponible
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback si python-dotenv n'est pas installé
    pass

def test_database_connection():
    """Test la connexion à la base de données"""
    print("TEST DE CONNEXION BASE DE DONNEES")
    print("=" * 50)
    
    # Configuration de test
    db_engine = os.getenv("FIXPRO_DB_ENGINE", "sqlite").lower()
    database_url = os.getenv("DATABASE_URL", "")
    
    print(f"Engine configure : {db_engine}")
    print(f"Database URL presente : {'Oui' if database_url else 'Non'}")
    
    # Test avec le code actuel
    try:
        from fixpro_app import get_db_connection, logger
        conn = get_db_connection()
        
        if conn:
            print("[OK] Connexion base de donnees reussie")
            
            # Test de requête simple
            try:
                if database_url or db_engine in ("postgresql", "supabase"):
                    cursor = conn.cursor()
                    cursor.execute("SELECT version()")
                    version = cursor.fetchone()
                    print(f"   Version PostgreSQL : {version[0]}")
                    cursor.close()
                else:
                    result = conn.execute("SELECT sqlite_version()")
                    version = result.fetchone()
                    print(f"   Version SQLite : {version[0]}")
                
                print("[OK] Requete test reussie")
                
            except Exception as e:
                print(f"[FAIL] Erreur lors de la requete test : {e}")
            
            conn.close()
            print("[OK] Connexion fermee correctement")
            return True
        else:
            print("[FAIL] Echec de la connexion")
            return False
            
    except ImportError as e:
        print(f"[FAIL] Erreur d'import : {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Erreur de connexion : {e}")
        return False

def test_schema_creation():
    """Test la création du schéma"""
    print("\nTEST DE CREATION DU SCHEMA")
    print("=" * 50)
    
    try:
        from fixpro_app import init_db, app
        
        # Forcer le mode test
        app.config["TESTING"] = True
        app.config["DEBUG"] = True
        
        init_db()
        print("[OK] Schema initialise avec succes")
        return True
        
    except Exception as e:
        print(f"[FAIL] Erreur lors de l'initialisation du schema : {e}")
        return False

def test_environment_variables():
    """Test que les variables d'environnement sont présentes"""
    print("\nTEST DES VARIABLES D'ENVIRONNEMENT")
    print("=" * 50)
    
    required_vars = [
        "FLASK_ENV",
        "FLASK_DEBUG", 
        "SECRET_KEY",
        "FIXPRO_DB_ENGINE"
    ]
    
    optional_vars = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY", 
        "DATABASE_URL"
    ]
    
    print("Variables requises :")
    all_present = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"   [OK] {var} : definie")
        else:
            print(f"   [FAIL] {var} : MANQUANTE")
            all_present = False
    
    print("\nVariables Supabase (optionnelles) :")
    supabase_present = False
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            masked = value[:10] + "..." if len(value) > 10 else "***"
            print(f"   [OK] {var} : {masked}")
            supabase_present = True
        else:
            print(f"   [WARN] {var} : non definie (OK pour SQLite)")
    
    # Le test passe si les variables requises sont présentes
    # Les variables Supabase sont optionnelles pour le développement
    return all_present

def main():
    """Exécute tous les tests"""
    print("TEST DE CONFIGURATION SUPABASE - FIXPRO")
    print("=" * 50)
    print()
    
    results = []
    
    # Test 1 : Variables d'environnement
    results.append(("Variables d'environnement", test_environment_variables()))
    
    # Test 2 : Connexion base de données
    results.append(("Connexion base de donnees", test_database_connection()))
    
    # Test 3 : Création schéma (optionnel)
    if results[1][1]:  # Si connexion réussie
        results.append(("Creation schema", test_schema_creation()))
    
    # Résumé
    print("\n" + "=" * 50)
    print("RESUME DES TESTS")
    print("=" * 50)
    
    for test_name, result in results:
        status = "[OK] SUCCES" if result else "[FAIL] ECHEC"
        print(f"{status} : {test_name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nTotal : {passed}/{total} tests passes")
    
    # Verifier si Supabase est configure
    db_engine = os.getenv("FIXPRO_DB_ENGINE", "sqlite").lower()
    database_url = os.getenv("DATABASE_URL", "")
    
    if db_engine == "supabase" or database_url:
        if passed == total:
            print("\nConfiguration prete pour Supabase !")
            print("\nProchaines etapes :")
            print("1. Creer un projet sur https://supabase.com")
            print("2. Executer le schema schema_supabase.sql")
            print("3. Configurer les variables d'environnement Render")
            print("4. Deployer sur Render")
            return 0
        else:
            print("\nCertains tests ont echoue. Verifiez la configuration.")
            return 1
    else:
        print("\nMode SQLite actif (developpement local)")
        print("Pour passer a Supabase :")
        print("1. Creer un projet sur https://supabase.com")
        print("2. Copiez .env.supabase.example en .env")
        print("3. Remplissez les variables Supabase")
        print("4. Relancez ce test")
        return 0

if __name__ == "__main__":
    sys.exit(main())