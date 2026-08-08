"""
TEST SIMPLE DE L'API FIXPRO
Lance ceci pour vérifier que l'API fonctionne
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"

def print_test(titre):
    """Afficher un titre de test"""
    print("\n" + "="*60)
    print(f"🧪 TEST: {titre}")
    print("="*60)

def test_health():
    """Test 1: Vérifier que l'API répond"""
    print_test("L'API est-elle vivante?")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"✅ Code réponse: {response.status_code}")
        print(f"✅ Réponse: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ ERREUR: {e}")
        print("   L'API Flask n'est pas lancée!")
        print("   Lancez: python app.py")
        return False

def test_register_artisan():
    """Test 2: Inscrire un artisan"""
    print_test("Inscrire un artisan")
    
    artisan = {
        "nom": "Diallo",
        "prenom": "Mamadou",
        "telephone": "+224 627 31 60 69",
        "metier": "Plombier",
        "zone": "Kaloum",
        "latitude": 9.5412,
        "longitude": -13.7531,
        "tarif_horaire": 15000
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/artisans/register", json=artisan)
        print(f"✅ Code réponse: {response.status_code}")
        data = response.json()
        print(f"✅ Réponse: {json.dumps(data, indent=2)}")
        
        if response.status_code == 201 and 'id' in data:
            print(f"✅ Artisan créé avec ID: {data['id']}")
            return data['id']
        else:
            print("❌ L'artisan n'a pas été créé correctement")
            return None
    except Exception as e:
        print(f"❌ ERREUR: {e}")
        return None

def test_invalid_artisan():
    """Test 3: Tester les validations (données manquantes)"""
    print_test("Validation des données")
    
    artisan_invalide = {
        "nom": "Dupont",
        # Manque des champs obligatoires!
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/artisans/register", json=artisan_invalide)
        print(f"✅ Code réponse: {response.status_code}")
        data = response.json()
        print(f"✅ Réponse: {json.dumps(data, indent=2)}")
        
        if response.status_code == 400:
            print("✅ Validation fonctionne! Les données manquantes sont détectées")
            return True
        else:
            print("⚠️ La validation devrait retourner une erreur 400")
            return False
    except Exception as e:
        print(f"❌ ERREUR: {e}")
        return False

def main():
    """Lancer tous les tests"""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  🧪 TESTS DE L'API FIXPRO 🧪".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    
    print("\n📝 Avant de lancer ce test:")
    print("   1. Assurez-vous que MySQL fonctionne")
    print("   2. Lancez: python app.py (dans un autre terminal)")
    print("   3. Attendez 2 secondes...")
    
    time.sleep(2)
    
    # Lancer les tests
    resultats = []
    
    resultats.append(("API répond", test_health()))
    if not resultats[-1][1]:
        print("\n❌ Impossible de continuer. Lancez d'abord: python app.py")
        return
    
    resultats.append(("Inscrire artisan", test_register_artisan() is not None))
    resultats.append(("Validation données", test_invalid_artisan()))
    
    # Résumé
    print("\n\n" + "="*60)
    print("📊 RÉSUMÉ DES TESTS")
    print("="*60)
    
    reussis = sum(1 for _, result in resultats if result)
    total = len(resultats)
    
    for titre, result in resultats:
        status = "✅ RÉUSSI" if result else "❌ ÉCHOUÉ"
        print(f"{titre:.<40} {status}")
    
    print("="*60)
    print(f"Score: {reussis}/{total}")
    
    if reussis == total:
        print("✅ TOUS LES TESTS SONT PASSÉS!")
    else:
        print("⚠️ Certains tests ont échoué. Voir les détails ci-dessus.")

if __name__ == "__main__":
    main()
