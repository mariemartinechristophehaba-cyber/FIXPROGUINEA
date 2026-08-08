#!/usr/bin/env python
"""
VÉRIFICATION RAPIDE - Avant de lancer l'application
Vérifie que tous les éléments sont correctement configurés
"""

import os
import sys

print("\n" + "="*60)
print("🔍 VÉRIFICATION DE LA CONFIGURATION FIXPRO")
print("="*60 + "\n")

resultats = []

# ========== CHECK 1: Python ==========
print("1️⃣ Vérification de Python...")
try:
    version = sys.version.split()[0]
    print(f"   ✅ Python {version} trouvé")
    resultats.append(True)
except:
    print("   ❌ Python non trouvé")
    resultats.append(False)

# ========== CHECK 2: Packages ==========
print("2️⃣ Vérification des packages...")
packages_requis = ['flask', 'mysql', 'dotenv']
packages_manquants = []

for package in packages_requis:
    try:
        if package == 'mysql':
            __import__('mysql.connector')
        elif package == 'dotenv':
            __import__('dotenv')
        else:
            __import__(package)
        print(f"   ✅ {package} installé")
    except ImportError:
        print(f"   ❌ {package} MANQUANT")
        packages_manquants.append(package)

if packages_manquants:
    print(f"\n   💡 Pour installer: pip install -r requirements.txt")
    resultats.append(False)
else:
    resultats.append(True)

# ========== CHECK 3: Fichiers ==========
print("3️⃣ Vérification des fichiers...")
fichiers_requis = {
    'app.py': 'API Flask',
    'requirements.txt': 'Dépendances',
    'setup_database.sql': 'Création BD',
    'FixPro test.py': 'Application CLI'
}

for fichier, description in fichiers_requis.items():
    if os.path.exists(fichier):
        print(f"   ✅ {fichier} ({description})")
    else:
        print(f"   ❌ {fichier} MANQUANT")

resultats.append(all(os.path.exists(f) for f in fichiers_requis.keys()))

# ========== CHECK 4: MySQL ==========
print("4️⃣ Vérification de MySQL...")
try:
    import mysql.connector
    conn = mysql.connector.connect(
        host=os.getenv("FIXPRO_DB_HOST", "localhost"),
        user=os.getenv("FIXPRO_DB_USER", "root"),
        password=os.getenv("FIXPRO_DB_PASS", "")
    )
    print(f"   ✅ MySQL connecté")
    
    # Vérifier la base de données
    cursor = conn.cursor()
    cursor.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = 'FixPro'")
    if cursor.fetchone():
        print(f"   ✅ Base de données FixPro existe")
    else:
        print(f"   ⚠️ Base de données FixPro N'EXISTE PAS")
        print(f"      Lancez: mysql -u root -p < setup_database.sql")
    
    conn.close()
    resultats.append(True)
except Exception as e:
    print(f"   ❌ MySQL ERROR: {str(e)[:50]}")
    print(f"      Vérifiez que MySQL est lancé")
    resultats.append(False)

# ========== CHECK 5: Variables d'environnement ==========
print("5️⃣ Vérification des variables d'environnement...")
try:
    from dotenv import load_dotenv
    load_dotenv()
    
    variables = {
        'FIXPRO_DB_HOST': 'localhost',
        'FIXPRO_DB_USER': 'root',
        'FIXPRO_DB_PASS': '(masqué)',
        'FIXPRO_DB_NAME': 'FixPro'
    }
    
    all_set = True
    for var, default in variables.items():
        value = os.getenv(var, default)
        if var == 'FIXPRO_DB_PASS':
            print(f"   ✅ {var} = {value}")
        else:
            print(f"   ✅ {var} = {value}")
    
    resultats.append(all_set)
except:
    print("   ⚠️ Variables d'environnement non configurées")
    resultats.append(False)

# ========== RÉSUMÉ ==========
print("\n" + "="*60)
print("📊 RÉSUMÉ")
print("="*60)

checks = [
    "Python",
    "Packages",
    "Fichiers",
    "MySQL",
    "Variables d'env"
]

for i, (check, result) in enumerate(zip(checks, resultats)):
    status = "✅ OK" if result else "❌ ERREUR"
    print(f"{check:.<40} {status}")

print("="*60)

total_ok = sum(resultats)
total = len(resultats)

if total_ok == total:
    print(f"\n🎉 TOUT EST PRÊT! ({total}/{total})")
    print("\nVous pouvez lancer:")
    print("   - python 'FixPro test.py'  (menu interactif)")
    print("   - python app.py            (API web)")
    sys.exit(0)
else:
    print(f"\n⚠️ PROBLÈMES DÉTECTÉS ({total_ok}/{total})")
    print("\nConsultez DEPANNAGE.md pour les solutions")
    sys.exit(1)
