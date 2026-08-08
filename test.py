"""print("Bienvenue sur FixPro !")

Nom = "Mamadou"
Metier = "Plombier"

print("Artisan : " + Nom)
print("Metier : " + Metier)
# Les informations d'un artisans 
nom = "Mamadou Diallo"
telephone = "+224 627 31 60 69"
Metier = "Plombier"
Zone = "Kaloum"
disponible = True

#Afficher les infos 
print("=== FixPro - Fiche Artisan ===")
print("Nom : " + nom)
print("telephone : " + telephone)
print("Metier : " + Metier)
print("Zone : " + Zone)

#Vérifier si disponible
if disponible == True:
    print("Statut : Disponible")
else:
    print(" Statut : Occupé")"""
"""mprint("=== FixPro - Inscription Artisan ===")
nom = input("ton nom complet :")
telephone = input("Ton numéro de telephone :")

print("Choisis ton metier :")
print("1 - Plombier")
print("2 - Electricien")
print("3 - Frigoriste")

choix = input("Tape 1 , 2 ou 3 : ")

if choix == "1":
    metier = "Plombier" 
elif choix == "2":
    metier = "Electricien"
elif choix == "3":
    metier = "Frigoriste"
else:
    metier = "Metier inconnu"
zone = input("Ton quatier (ex: Kaloum, Ratoma...) : ")

print("")
print("=== Récupitulatif de ton inscription ===")
print("Nom : " + nom)
print("Téléphone : " + telephone)
print("Métier : " + metier)
print("Zone :" + zone)
print("Statut :Inscrit sur FixPro ! ")"""
  
# Connexion à MySQL
import mysql.connector
from mysql.connector import Error

print("=== FixPro - Inscription Artisan ===")

nom = input("Ton nom : ").strip()
prenom = input("Ton prénom : ").strip()
telephone = input("Ton numéro de téléphone : ").strip()

print("Choisis ton métier :")
print("1 - Plombier")
print("2 - Electricien")
print("3 - Frigoriste")

choix = input("Tape 1, 2 ou 3 : ").strip()
if choix == "1":
    metier = "Plombier"
elif choix == "2":
    metier = "Electricien"
elif choix == "3":
    metier = "Frigoriste"
else:
    metier = "Métier inconnu"

zone = input("Ton quartier (ex: Kaloum, Ratoma, Flamadina) : ").strip()
latitude = input("Latitude (ex: 9.5412) : ").strip()
longitude = input("Longitude (ex: -13.7531) : ").strip()
tarif_horaire = input("Tarif horaire (ex: 50000) : ").strip()

try:
    connexion = mysql.connector.connect(
        host="localhost",
        user="root",
        password="ton_mot_de_pass",
        database="FixPro"
    )
    curseur = connexion.cursor()

    requete = """
    INSERT INTO artisans (nom, prenom, telephone, metier, zone, latitude, longitude, tarif_horaire)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    valeurs = (
        nom,
        prenom,
        telephone,
        metier,
        zone,
        float(latitude),
        float(longitude),
        float(tarif_horaire),
    )

    curseur.execute(requete, valeurs)
    connexion.commit()
    print("\n=== Artisan enregistré dans FixPro ! ===")
    print(f"Nom : {nom}")
    print(f"Prénom : {prenom}")
    print(f"Téléphone : {telephone}")
    print(f"Métier : {metier}")
    print(f"Zone : {zone}")
    print(f"Tarif horaire : {tarif_horaire}")
    print("Statut : Inscrit et sauvegardé dans la base de données !")

except Error as err:
    print("\nErreur MySQL :", err)

finally:
    if 'curseur' in locals():
        curseur.close()
    if 'connexion' in locals() and connexion.is_connected():
        connexion.close()
