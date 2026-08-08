# DÉPANNAGE RAPIDE
# Si quelque chose ne fonctionne pas, lisez ceci!

## ❌ "ModuleNotFoundError: No module named 'mysql'"

**Cause:** Les packages ne sont pas installés

**Solution:**
```powershell
# 1. Vérifier que l'environnement virtuel est activé
# Vous devez voir: (.venv) PS C:\...>

# 2. Si ce n'est pas le cas, activez-le:
.\.venv\Scripts\Activate.ps1

# 3. Installez les packages:
pip install -r requirements.txt

# 4. Vérifiez:
pip list
```

---

## ❌ "Can't connect to MySQL server"

**Cause:** MySQL n'est pas lancé ou pas bien configuré

**Solutions:**

**A. Si MySQL n'est pas lancé:**
```powershell
# Sur Windows, cherchez "Services" et démarrez MySQL
# Ou avec Docker:
docker start mysql-fixpro
```

**B. Si MySQL demande un mot de passe different:**
```powershell
# Testez avec le bon mot de passe:
mysql -u root -p

# Puis éditez .env avec les bons identifiants:
FIXPRO_DB_HOST=localhost
FIXPRO_DB_USER=root
FIXPRO_DB_PASS=VOTRE_MOT_DE_PASSE  # ← Changez ceci
FIXPRO_DB_NAME=FixPro
```

**C. Si la base de données n'existe pas:**
```powershell
# Créez-la:
mysql -u root -p -e "CREATE DATABASE FixPro;"

# Puis les tables:
mysql -u root -p FixPro < setup_database.sql
```

---

## ❌ "Port 5000 already in use"

**Cause:** Quelque chose utilise déjà le port 5000

**Solution:**
```powershell
# 1. Trouvez ce qui utilise le port:
Get-NetTCPConnection -LocalPort 5000

# 2. Arrêtez-le (Ctrl+C si c'est Python)
# Ou lancez l'app sur un port différent:
```

Éditez app.py et changez:
```python
# Avant:
app.run(debug=True)

# Après (lancer sur port 8000):
app.run(debug=True, port=8000)
```

---

## ❌ "FileNotFoundError: [Errno 2] No such file or directory"

**Cause:** Le fichier setup_database.sql n'est pas au bon endroit

**Solution:**
```powershell
# Vérifiez que vous êtes dans le bon dossier:
cd "C:\Users\L2616\Desktop\Application Fixpro"

# Vérifiez que le fichier existe:
ls setup_database.sql

# Puis refaites:
mysql -u root -p FixPro < setup_database.sql
```

---

## ❌ "App.py ne démarre pas"

**Solution:** Vérifiez la syntaxe

```powershell
# Testez le fichier Python:
python -m py_compile app.py

# Si pas d'erreur, c'est bon
# Sinon, vous verrez l'erreur

# Sinon, lancez avec plus de détails:
python app.py
# Lisez bien le message d'erreur
```

---

## ✅ COMMANDES UTILES

```powershell
# Activer l'environnement virtuel
.\.venv\Scripts\Activate.ps1

# Quitter l'environnement virtuel
deactivate

# Lister les packages installés
pip list

# Vérifier que MySQL fonctionne
mysql -u root -p -e "SELECT 1"

# Voir les tables de la base de données
mysql -u root -p FixPro -e "SHOW TABLES;"

# Arrêter l'API (Ctrl+C dans le terminal)

# Arrêter MySQL dans Docker
docker stop mysql-fixpro

# Démarrer MySQL dans Docker
docker start mysql-fixpro
```

---

## 🆘 SI VOUS ÊTES VRAIMENT BLOQUÉ

1. Vérifiez que Python est installé:
   ```powershell
   python --version
   ```

2. Vérifiez que MySQL est installé:
   ```powershell
   mysql --version
   ```

3. Lisez les messages d'erreur complètement (ils donnent des indices!)

4. Demandez de l'aide avec le message d'erreur exact
