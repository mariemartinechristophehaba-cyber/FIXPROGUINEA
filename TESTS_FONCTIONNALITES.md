# 🧪 GUIDE DE TEST DES FONCTIONNALITÉS

## 🎯 Démarrer

```powershell
# Activer l'environnement virtuel
.\.venv\Scripts\Activate.ps1

# Lancer l'application
python "FixPro test.py"
```

---

## 📋 LES 8 FONCTIONNALITÉS À TESTER

### ✅ TEST 1: Inscription d'un Artisan

**Menu → Option 1**

Remplissez les informations:
```
Nom complet: Diallo
Prénom: Mamadou
Téléphone: +224 627 31 60 69
Métier: 1 (Plombier)
Quartier: Kaloum
Latitude: 9.5412
Longitude: -13.7531
Tarif horaire: 15000
```

**✅ Résultat attendu:** `✓ Artisan inscrit avec succès!`

**Ce que ça teste:**
- Connexion à MySQL
- Insertion de données
- Validation des champs

---

### ✅ TEST 2: Inscription d'un Client

**Menu → Option 2**

Remplissez:
```
Nom complet: Sow Ahmed
Téléphone: +224 600 12 34 56
Latitude: 9.5415
Longitude: -13.7535
```

**✅ Résultat attendu:** `✓ Client inscrit avec succès!`

---

### ✅ TEST 3: Recherche d'Artisan par Géolocalisation

**Menu → Option 3**

```
Votre latitude: 9.5415
Votre longitude: -13.7535
Métier: 1 (Plombier)
Distance max (km): 10
```

**✅ Résultat attendu:**
```
✓ 1 artisan(s) trouvé(s):
1. Diallo Mamadou
   Téléphone: +224 627 31 60 69
   Distance: X.XX km
```

**Ce que ça teste:**
- Calcul de distance (formule Haversine)
- Recherche par métier
- Tri par proximité

**💡 Astuce:** Si la distance affichée n'est pas correcte, c'est un problème de calcul GPS

---

### ✅ TEST 4: Enregistrer une Intervention

**Prérequis:**
- Avoir un artisan inscrit (ID: 1)
- Avoir un client inscrit (ID: 1)

**Menu → Option 4**

```
ID artisan: 1
ID client: 1
Tarif intervention: 50000
```

**✅ Résultat attendu:**
```
=== Détails de l'Intervention ===
Tarif intervention: 50000 GNF
Commission FixPro (10%): 5000.00 GNF
Montant artisan: 45000.00 GNF
```

**Ce que ça teste:**
- Calcul automatique de commission (10%)
- Enregistrement en base de données

---

### ✅ TEST 5: Évaluer une Intervention

**Prérequis:**
- Avoir une intervention enregistrée (ID: 1)

**Menu → Option 5**

```
ID intervention: 1
ID artisan: 1
ID client: 1
Note (1-5): 5
Commentaire: Très bon travail!
```

**✅ Résultat attendu:**
```
✓ Évaluation enregistrée avec succès!
=== Évaluation ===
Note: ⭐⭐⭐⭐⭐ (5/5)
Commentaire: Très bon travail!
```

**Ce que ça teste:**
- Validation des notes (1-5)
- Stockage des avis
- Système de notation

---

### ✅ TEST 6: Effectuer un Paiement

**Prérequis:**
- Avoir une intervention enregistrée (ID: 1)

**Menu → Option 6**

```
ID intervention: 1
Montant à payer: 50000
Méthode: 1 (Virement bancaire)
```

**✅ Résultat attendu:**
```
✓ Paiement de 50000 GNF effectué avec succès!
=== Détails du Paiement ===
Montant: 50000 GNF
Méthode: virement
Statut: effectué
```

**Ce que ça teste:**
- Validation des montants
- Enregistrement des paiements
- Mise à jour du statut de l'intervention

---

### ✅ TEST 7: Voir les Notifications

**Menu → Option 7**

```
Ton ID: 1
Tu es (artisan/client): artisan
```

**✅ Résultat attendu:**
```
✓ Tu as 3 notification(s):
--------------------------------------------------
🔔 [NOUVELLE] Nouvelle intervention
   Une nouvelle intervention a été enregistrée (Montant: 50000 GNF)
   📅 28/05/2026 14:30
```

**Ce que ça teste:**
- Notifications automatiques
- Historique des événements

---

### ✅ TEST 8: Voir les Avis d'un Artisan

**Menu → Option 8**

```
ID artisan: 1
```

**✅ Résultat attendu:**
```
=== Diallo Mamadou ===
Métier: Plombier
Zone: Kaloum
Note moyenne: ⭐⭐⭐⭐⭐ (5.0/5) - 1 avis
--------------------------------------------------

⭐⭐⭐⭐⭐ (5/5) - 28/05/2026
  "Très bon travail!"
```

**Ce que ça teste:**
- Calcul de moyenne
- Affichage des avis

---

## 🔄 ORDRE RECOMMANDÉ POUR TESTER

1. ✅ Inscription artisan (Option 1)
2. ✅ Inscription client (Option 2)
3. ✅ Recherche artisan (Option 3) - Vérifiez qu'il est trouvé
4. ✅ Enregistrer intervention (Option 4) - Noter les IDs
5. ✅ Évaluer intervention (Option 5) - Avec la même intervention
6. ✅ Effectuer paiement (Option 6)
7. ✅ Voir notifications (Option 7)
8. ✅ Voir avis artisan (Option 8)

---

## 🐛 SI QUELQUE CHOSE NE FONCTIONNE PAS

### ❌ "ID artisan/client invalide"
**Solution:** Utilisez les IDs des enregistrements créés (habituellement 1, 2, 3...)

### ❌ "Distance = 0"
**Utilisez les mêmes coordonnées GPS que l'artisan pour tester la proximité**

### ❌ "Pas de notifications"
**Les notifications sont créées automatiquement lors des interventions**

### ❌ "Erreur de base de données"
**Vérifiez:**
```powershell
mysql -u root -p FixPro -e "SHOW TABLES;"
```

---

## 📊 VÉRIFIER LES DONNÉES EN BASE

```powershell
# Voir tous les artisans
mysql -u root -p FixPro -e "SELECT * FROM artisans;"

# Voir tous les clients
mysql -u root -p FixPro -e "SELECT * FROM clients;"

# Voir les interventions
mysql -u root -p FixPro -e "SELECT * FROM interventions;"

# Voir les évaluations
mysql -u root -p FixPro -e "SELECT * FROM evaluations;"

# Voir les paiements
mysql -u root -p FixPro -e "SELECT * FROM paiements;"

# Voir les notifications
mysql -u root -p FixPro -e "SELECT * FROM notifications;"
```

Mot de passe: `root`

---

## 🎉 BRAVO!

Si tous les tests passent, votre application fonctionne correctement!

**Prochaines étapes:**
1. Déployer sur Render ou Railway (voir deploy/)
2. Ajouter une interface web (HTML/CSS/JavaScript)
3. Ajouter des fonctionnalités supplémentaires
4. Tester en production

