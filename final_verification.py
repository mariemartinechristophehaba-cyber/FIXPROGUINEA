#!/usr/bin/env python
"""
Script de verification finale du deploiement FixPro + Supabase + Render
"""
import sys
import os
sys.path.insert(0, '.')

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
except Exception as e:
    print(f"Avertissement: Erreur chargement .env : {e}")
    pass

def check_production_config():
    """Verifie que la configuration production est correcte"""
    print("VERIFICATION CONFIGURATION PRODUCTION")
    print("=" * 50)
    
    db_engine = os.getenv("FIXPRO_DB_ENGINE", "sqlite").lower()
    database_url = os.getenv("DATABASE_URL", "")
    supabase_url = os.getenv("SUPABASE_URL", "")
    
    print(f"Engine DB : {db_engine}")
    print(f"Database URL : {'Presente' if database_url else 'Manquante'}")
    print(f"Supabase URL : {'Presente' if supabase_url else 'Manquante'}")
    
    if db_engine == "supabase" and database_url:
        print("[OK] Configuration Supabase correcte")
        return True
    elif db_engine == "sqlite":
        print("[WARN] Mode SQLite (developpement local)")
        return True
    else:
        print("[FAIL] Configuration incorrecte")
        return False

def check_required_vars():
    """Verifie que toutes les variables requises sont presentes"""
    print("\nVERIFICATION VARIABLES D'ENVIRONNEMENT")
    print("=" * 50)
    
    required_vars = {
        "FLASK_ENV": "Environnement Flask",
        "FLASK_DEBUG": "Mode debug",
        "SECRET_KEY": "Cle secrete Flask",
        "FIXPRO_DB_ENGINE": "Type de base de donnees"
    }
    
    supabase_vars = {
        "SUPABASE_URL": "URL Supabase",
        "SUPABASE_ANON_KEY": "Cle anon Supabase",
        "DATABASE_URL": "Connection string PostgreSQL"
    }
    
    all_present = True
    
    print("Variables requises :")
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            if var == "SECRET_KEY":
                masked = value[:10] + "..." if len(value) > 10 else "***"
                print(f"   [OK] {var} ({description}) : {masked}")
            else:
                print(f"   [OK] {var} ({description}) : {value}")
        else:
            print(f"   [FAIL] {var} ({description}) : MANQUANTE")
            all_present = False
    
    print("\nVariables Supabase :")
    for var, description in supabase_vars.items():
        value = os.getenv(var)
        if value:
            masked = value[:10] + "..." if len(value) > 10 else "***"
            print(f"   [OK] {var} ({description}) : {masked}")
        else:
            print(f"   [WARN] {var} ({description}) : Manquante")
    
    return all_present

def check_database_connection():
    """Test la connexion a la base de donnees"""
    print("\nVERIFICATION CONNEXION BASE DE DONNEES")
    print("=" * 50)
    
    try:
        from fixpro_app import get_db_connection
        
        conn = get_db_connection()
        if conn:
            print("[OK] Connexion base de donnees reussie")
            
            # Test selon le type de base de donnees
            db_engine = os.getenv("FIXPRO_DB_ENGINE", "sqlite").lower()
            database_url = os.getenv("DATABASE_URL", "")
            
            if database_url or db_engine in ("postgresql", "supabase"):
                cursor = conn.cursor()
                cursor.execute("SELECT version()")
                version = cursor.fetchone()
                print(f"   PostgreSQL : {version[0][:50]}...")
                cursor.close()
            else:
                result = conn.execute("SELECT sqlite_version()")
                version = result.fetchone()
                print(f"   SQLite : {version[0]}")
            
            conn.close()
            print("[OK] Connexion fermee correctement")
            return True
        else:
            print("[FAIL] Echec de la connexion")
            return False
            
    except Exception as e:
        print(f"[FAIL] Erreur de connexion : {e}")
        return False

def check_schema():
    """Verifie que le schema est correct"""
    print("\nVERIFICATION SCHEMA BASE DE DONNEES")
    print("=" * 50)
    
    try:
        from fixpro_app import get_db_connection
        
        conn = get_db_connection()
        
        # Verifier les tables principales
        required_tables = ["users", "requests", "messages", "payments", "service_categories"]
        
        db_engine = os.getenv("FIXPRO_DB_ENGINE", "sqlite").lower()
        database_url = os.getenv("DATABASE_URL", "")
        
        if database_url or db_engine in ("postgresql", "supabase"):
            cursor = conn.cursor()
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
        
        print("Tables presentes :")
        for table in required_tables:
            if table in tables:
                print(f"   [OK] {table}")
            else:
                print(f"   [FAIL] {table} MANQUANTE")
        
        conn.close()
        
        if all(table in tables for table in required_tables):
            print("[OK] Schema correct")
            return True
        else:
            print("[WARN] Schema incomplet (executez schema_supabase.sql)")
            return False
            
    except Exception as e:
        print(f"[FAIL] Erreur verification schema : {e}")
        return False

def check_application_health():
    """Test la sante de l'application"""
    print("\nVERIFICATION SANTE APPLICATION")
    print("=" * 50)
    
    try:
        from fixpro_app import app
        
        with app.test_client() as client:
            response = client.get("/health")
            
            if response.status_code == 200:
                data = response.get_json()
                print(f"[OK] Health check : {data}")
                
                # Verifier les headers de securite
                headers = dict(response.headers)
                security_headers = {
                    "X-Frame-Options": headers.get("X-Frame-Options"),
                    "X-Content-Type-Options": headers.get("X-Content-Type-Options"),
                    "X-XSS-Protection": headers.get("X-XSS-Protection")
                }
                
                print("\nHeaders de securite :")
                for header, value in security_headers.items():
                    if value:
                        print(f"   [OK] {header} : {value}")
                    else:
                        print(f"   [FAIL] {header} : MANQUANT")
                
                return True
            else:
                print(f"[FAIL] Health check status : {response.status_code}")
                return False
                
    except Exception as e:
        print(f"[FAIL] Erreur health check : {e}")
        return False

def main():
    """Execute toutes les verifications"""
    print("VERIFICATION FINALE - FIXPRO + SUPABASE + RENDER")
    print("=" * 50)
    print()
    
    results = []
    
    results.append(("Configuration", check_production_config()))
    results.append(("Variables d'environnement", check_required_vars()))
    results.append(("Connexion base de donnees", check_database_connection()))
    results.append(("Schema", check_schema()))
    results.append(("Sante application", check_application_health()))
    
    # Resume
    print("\n" + "=" * 50)
    print("RESUME DES VERIFICATIONS")
    print("=" * 50)
    
    for test_name, result in results:
        status = "[OK] SUCCES" if result else "[FAIL] ECHEC"
        print(f"{status} : {test_name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nTotal : {passed}/{total} verifications passees")
    
    if passed == total:
        print("\nDEPLOIEMENT REUSSI !")
        print("\nVotre application FixPro est operationnelle sur Supabase.")
        print("\nProchaines etapes :")
        print("1. Verifiez les logs Render")
        print("2. Testez l'inscription/connexion")
        print("3. Testez le chat en temps reel")
        print("4. Surveillez les performances")
        return 0
    else:
        print("\nCERTAINES VERIFICATIONS ONT ECHOUE")
        print("\nActions recommandees :")
        print("1. Verifiez les variables d'environnement Render")
        print("2. Executez schema_supabase.sql dans Supabase")
        print("3. Verifiez les logs Render pour erreurs")
        return 1

if __name__ == "__main__":
    sys.exit(main())