
    commentaire = input("Commentaire (optionnel): ").strip()
    if not commentaire:
        commentaire = "Pas de commentaire"
    
    evaluation = Evaluation(int(intervention_id), int(artisan_id), int(client_id), note, commentaire)
    if evaluation.sauvegarder(curseur, connexion):
        evaluation.afficher_evaluation()
        
        # Notification pour l'artisan
        notif = Notification(int(artisan_id), "artisan", 
                           f"Nouvelle évaluation: {'⭐' * note}", 
                           f"Le client a laissé un avis: {commentaire}")
        notif.sauvegarder(curseur, connexion)


def effectuer_paiement(curseur, connexion):
    """Effectuer un paiement pour une intervention"""
    print("\n" + "=" * 50)
    print("Paiement d'une Intervention")
    print("=" * 50)
    
    intervention_id = input("ID de l'intervention: ").strip()
    montant = float(input("Montant à payer (GNF): ").strip())
    
    print("\nChoisir la méthode de paiement:")
    print("1 - Virement bancaire")
    print("2 - Espèces")
    print("3 - Mobile Money (Orange Money, MTN Money)")
    
    choix_paiement = input("Tape 1, 2 ou 3: ").strip()
    methodes = {"1": "virement", "2": "especes", "3": "mobile_money"}
    methode = methodes.get(choix_paiement, "invalide")
    
    if methode == "invalide":
        print("✗ Méthode de paiement invalide!")
        return
    
    paiement = Paiement(int(intervention_id), montant, methode)
    if paiement.effectuer_paiement(curseur, connexion):
        paiement.afficher_details()
        
        # Récupérer l'ID de l'artisan pour la notification
        curseur.execute("SELECT artisan_id FROM interventions WHERE id = %s", (int(intervention_id),))
        resultat = curseur.fetchone()
        if resultat:
            artisan_id = resultat[0]
            notif = Notification(artisan_id, "artisan", 
                               "Paiement reçu", 
                               f"Paiement de {montant} GNF reçu par {methode}")
            notif.sauvegarder(curseur, connexion)


def voir_notifications(curseur):
    """Afficher les notifications de l'utilisateur"""
    print("\n" + "=" * 50)
    print("Mes Notifications")
    print("=" * 50)
    
    utilisateur_id = input("Ton ID: ").strip()
    type_utilisateur = input("Tu es (artisan/client): ").strip().lower()
    
    requete = """SELECT id, titre, message, lue, DATE_FORMAT(date_notification, '%d/%m/%Y %H:%i') 
                 FROM notifications WHERE utilisateur_id = %s AND type_utilisateur = %s 
                 ORDER BY date_notification DESC"""
    curseur.execute(requete, (int(utilisateur_id), type_utilisateur))
    notifications = curseur.fetchall()
    
    if notifications:
        print(f"\n✓ Tu as {len(notifications)} notification(s):")
        print("-" * 50)
        for notif_id, titre, message, lue, date in notifications:
            statut = "✓ [LUE]" if lue else "🔔 [NOUVELLE]"
            print(f"{statut} {titre}")
            print(f"   {message}")
            print(f"   📅 {date}\n")
            
            # Marquer comme lue
            if not lue:
                curseur.execute("UPDATE notifications SET lue = TRUE WHERE id = %s", (notif_id,))
    else:
        print(f"✗ Aucune notification pour le moment")


def voir_avis_artisan(curseur):
    """Voir les avis et la note moyenne d'un artisan"""
    print("\n" + "=" * 50)
    print("Avis d'un Artisan")
    print("=" * 50)
    
    artisan_id = input("ID de l'artisan: ").strip()
    
    # Obtenir les infos de l'artisan
    curseur.execute("SELECT nom, prenom, metier, zone FROM artisans WHERE id = %s", (int(artisan_id),))
    artisan = curseur.fetchone()
    
    if not artisan:
        print("✗ Artisan non trouvé!")
        return
    
    nom, prenom, metier, zone = artisan
    moyenne, nombre = obtenir_moyenne_evaluations(int(artisan_id), curseur)
    
    print(f"\n=== {nom} {prenom} ===")
    print(f"Métier: {metier}")
    print(f"Zone: {zone}")
    print(f"Note moyenne: {'⭐' * int(moyenne)} ({moyenne}/5) - {nombre} avis")
    print("-" * 50)
    
    # Afficher tous les avis
    requete = """SELECT note, commentaire, DATE_FORMAT(date_evaluation, '%d/%m/%Y') 
                 FROM evaluations WHERE artisan_id = %s 
                 ORDER BY date_evaluation DESC"""
    curseur.execute(requete, (int(artisan_id),))
    evaluations = curseur.fetchall()
    
    if evaluations:
        for note, commentaire, date in evaluations:
            print(f"\n{'⭐' * note} ({note}/5) - {date}")
            print(f"  \"{commentaire}\"")
    else:
        print("\nPas d'avis pour le moment")


# ========== SCRIPT PRINCIPAL ==========
if __name__ == "__main__":
    menu_principal()
 



import mysql.connector
import math
import os

print("=" * 50)
print("Bienvenue sur FixPro!")
print("Plateforme de mise en relation artisans-clients")
print("=" * 50)

# ========== CONNEXION À MYSQL ==========
# Lire les paramètres depuis les variables d'environnement pour la sécurité
DB_HOST = os.getenv("FIXPRO_DB_HOST", "localhost")
DB_USER = os.getenv("FIXPRO_DB_USER", "root")
DB_PASS = os.getenv("FIXPRO_DB_PASS", "")
DB_NAME = os.getenv("FIXPRO_DB_NAME", "FixPro")

try:
    connexion = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    curseur = connexion.cursor()
    print(f"✓ Connexion à la base de données {DB_NAME}@{DB_HOST} réussie!\n")
except mysql.connector.Error as err:
    print(f"✗ Erreur de connexion: {err}")
    print("Vérifie les variables d'environnement: FIXPRO_DB_HOST, FIXPRO_DB_USER, FIXPRO_DB_PASS, FIXPRO_DB_NAME")
    exit(1)

# ========== CLASSES ==========
class Artisan:
    """Classe pour gérer les artisans FixPro"""
    def __init__(self, nom, prenom, telephone, metier, zone, latitude, longitude, tarif_horaire):
        self.nom = nom
        self.prenom = prenom
        self.telephone = telephone
        self.metier = metier
        self.zone = zone
        self.latitude = latitude
        self.longitude = longitude
        self.tarif_horaire = tarif_horaire
        self.taux_commission = 10  # 10% de commission FixPro

    def afficher_profil(self):
        print(f"\n=== FixPro - Profil Artisan ===")
        print(f"Nom: {self.nom} {self.prenom}")
        print(f"Téléphone: {self.telephone}")
        print(f"Métier: {self.metier}")
        print(f"Zone: {self.zone}")
        print(f"Localisation: ({self.latitude}, {self.longitude})")
        print(f"Tarif horaire: {self.tarif_horaire} GNF")

    def sauvegarder(self, curseur, connexion):
        """Sauvegarder l'artisan dans la base de données"""
        requete = """INSERT INTO artisans (nom, prenom, telephone, metier, zone, latitude, longitude, tarif_horaire, taux_commission) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        valeurs = (self.nom, self.prenom, self.telephone, self.metier, self.zone, 
                   self.latitude, self.longitude, self.tarif_horaire, self.taux_commission)
        try:
            curseur.execute(requete, valeurs)
            connexion.commit()
            print(f"✓ Artisan {self.nom} {self.prenom} inscrit avec succès!")
        except mysql.connector.Error as err:
            print(f"✗ Erreur lors de l'inscription: {err}")
            connexion.rollback()


class Client:
    """Classe pour gérer les clients FixPro"""
    def __init__(self, nom, telephone, latitude, longitude):
        self.nom = nom
        self.telephone = telephone
        self.latitude = latitude
        self.longitude = longitude

    def sauvegarder(self, curseur, connexion):
        """Sauvegarder le client dans la base de données"""
        requete = "INSERT INTO clients (nom, telephone, latitude, longitude) VALUES (%s, %s, %s, %s)"
        valeurs = (self.nom, self.telephone, self.latitude, self.longitude)
        try:
            curseur.execute(requete, valeurs)
            connexion.commit()
            print(f"✓ Client {self.nom} inscrit avec succès!")
        except mysql.connector.Error as err:
            print(f"✗ Erreur lors de l'inscription: {err}")
            connexion.rollback()


class Intervention:
    """Classe pour gérer les interventions et les commissions"""
    def __init__(self, artisan_id, client_id, tarif_intervention):
        self.artisan_id = artisan_id
        self.client_id = client_id
        self.tarif_intervention = tarif_intervention
        self.taux_commission_fixpro = 0.10  # 10%
        self.commission_fixpro = self.calculer_commission()

    def calculer_commission(self):
        """Calculer la commission FixPro (10%)"""
        return self.tarif_intervention * self.taux_commission_fixpro

    def afficher_details(self):
        print(f"\n=== Détails de l'Intervention ===")
        print(f"Tarif intervention: {self.tarif_intervention} GNF")
        print(f"Commission FixPro (10%): {self.commission_fixpro:.2f} GNF")
        print(f"Montant artisan: {self.tarif_intervention - self.commission_fixpro:.2f} GNF")

    def sauvegarder(self, curseur, connexion):
        """Sauvegarder l'intervention dans la base de données"""
        requete = """INSERT INTO interventions (artisan_id, client_id, tarif_intervention, commission_fixpro, statut) 
                     VALUES (%s, %s, %s, %s, %s)"""
        valeurs = (self.artisan_id, self.client_id, self.tarif_intervention, self.commission_fixpro, "en attente")
        try:
            curseur.execute(requete, valeurs)
            connexion.commit()
            intervention_id = curseur.lastrowid
            print(f"✓ Intervention enregistrée avec succès! (ID: {intervention_id})")
            return intervention_id
        except mysql.connector.Error as err:
            print(f"✗ Erreur lors de l'enregistrement: {err}")
            connexion.rollback()
            return None


class Evaluation:
    """Classe pour gérer les évaluations des artisans"""
    def __init__(self, intervention_id, artisan_id, client_id, note, commentaire):
        self.intervention_id = intervention_id
        self.artisan_id = artisan_id
        self.client_id = client_id
        self.note = note  # 1 à 5 étoiles
        self.commentaire = commentaire

    def valider_note(self):
        """Vérifier que la note est entre 1 et 5"""
        if 1 <= self.note <= 5:
            return True
        return False

    def afficher_evaluation(self):
        print(f"\n=== Évaluation ===")
        print(f"Note: {'⭐' * self.note} ({self.note}/5)")
        print(f"Commentaire: {self.commentaire}")

    def sauvegarder(self, curseur, connexion):
        """Sauvegarder l'évaluation"""
        if not self.valider_note():
            print("✗ La note doit être entre 1 et 5!")
            return False
        
        requete = """INSERT INTO evaluations (intervention_id, artisan_id, client_id, note, commentaire) 
                     VALUES (%s, %s, %s, %s, %s)"""
        valeurs = (self.intervention_id, self.artisan_id, self.client_id, self.note, self.commentaire)
        try:
            curseur.execute(requete, valeurs)
            connexion.commit()
            print(f"✓ Évaluation enregistrée avec succès!")
            return True
        except mysql.connector.Error as err:
            print(f"✗ Erreur lors de l'enregistrement: {err}")
            connexion.rollback()
            return False


class Paiement:
    """Classe pour gérer les paiements"""
    def __init__(self, intervention_id, montant, methode_paiement):
        self.intervention_id = intervention_id
        self.montant = montant
        self.methode_paiement = methode_paiement  # "virement", "especes", "mobile_money"
        self.statut = "en attente"

    def valider_paiement(self):
        """Vérifier les informations du paiement"""
        methodes_valides = ["virement", "especes", "mobile_money"]
        if self.methode_paiement not in methodes_valides:
            print(f"✗ Méthode de paiement invalide! Utilisez: {', '.join(methodes_valides)}")
            return False
        if self.montant <= 0:
            print("✗ Le montant doit être supérieur à 0!")
            return False
        return True

    def afficher_details(self):
        print(f"\n=== Détails du Paiement ===")
        print(f"Montant: {self.montant} GNF")
        print(f"Méthode: {self.methode_paiement}")
        print(f"Statut: {self.statut}")

    def effectuer_paiement(self, curseur, connexion):
        """Effectuer le paiement et mettre à jour le statut"""
        if not self.valider_paiement():
            return False
        
        try:
            # Enregistrer le paiement
            requete = """INSERT INTO paiements (intervention_id, montant, methode_paiement, statut) 
                         VALUES (%s, %s, %s, %s)"""
            valeurs = (self.intervention_id, self.montant, self.methode_paiement, "effectué")
            curseur.execute(requete, valeurs)
            
            # Mettre à jour le statut de l'intervention
            requete_update = "UPDATE interventions SET statut = %s WHERE id = %s"
            curseur.execute(requete_update, ("payée", self.intervention_id))
            
            connexion.commit()
            self.statut = "effectué"
            print(f"✓ Paiement de {self.montant} GNF effectué avec succès!")
            return True
        except mysql.connector.Error as err:
            print(f"✗ Erreur lors du paiement: {err}")
            connexion.rollback()
            return False


class Notification:
    """Classe pour gérer les notifications"""
    def __init__(self, utilisateur_id, type_utilisateur, titre, message):
        self.utilisateur_id = utilisateur_id
        self.type_utilisateur = type_utilisateur  # "artisan" ou "client"
        self.titre = titre
        self.message = message
        self.lue = False

    def afficher_notification(self):
        statut = "✓ [LUE]" if self.lue else "🔔 [NOUVELLE]"
        print(f"\n{statut} {self.titre}")
        print(f"   {self.message}")

    def sauvegarder(self, curseur, connexion):
        """Sauvegarder la notification"""
        requete = """INSERT INTO notifications (utilisateur_id, type_utilisateur, titre, message, lue) 
                     VALUES (%s, %s, %s, %s, %s)"""
        valeurs = (self.utilisateur_id, self.type_utilisateur, self.titre, self.message, self.lue)
        try:
            curseur.execute(requete, valeurs)
            connexion.commit()
            return True
        except mysql.connector.Error as err:
            print(f"✗ Erreur lors de l'enregistrement: {err}")
            return False


def obtenir_moyenne_evaluations(artisan_id, curseur):
    """Obtenir la note moyenne et le nombre d'évaluations d'un artisan"""
    requete = "SELECT AVG(note), COUNT(*) FROM evaluations WHERE artisan_id = %s"
    curseur.execute(requete, (artisan_id,))
    resultat = curseur.fetchone()
    
    if resultat[1] == 0:
        return 0, 0
    return round(resultat[0], 1), resultat[1]


# ========== FONCTIONS DE GÉOLOCALISATION ==========
def calculer_distance(lat1, lon1, lat2, lon2):
    """Calculer la distance entre deux points GPS (formule de Haversine) en km"""
    R = 6371  # Rayon de la Terre en km
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    distance = R * c
    return distance


def trouver_artisans_proches(client_lat, client_lon, metier, curseur, distance_max=10):
    """Trouver les artisans les plus proches d'un client pour un métier donné"""
    requete = "SELECT id, nom, prenom, telephone, latitude, longitude FROM artisans WHERE metier = %s"
    curseur.execute(requete, (metier,))
    artisans = curseur.fetchall()
    
    artisans_proches = []
    for artisan in artisans:
        artisan_id, nom, prenom, telephone, lat, lon = artisan
        distance = calculer_distance(client_lat, client_lon, lat, lon)
        
        if distance <= distance_max:
            artisans_proches.append({
                'id': artisan_id,
                'nom': nom,
                'prenom': prenom,
                'telephone': telephone,
                'distance': round(distance, 2)
            })
    
    # Trier par distance croissante
    artisans_proches.sort(key=lambda x: x['distance'])
    return artisans_proches


# ========== MENU PRINCIPAL ==========
def menu_principal():
    while True:
        print("\n" + "=" * 50)
        print("MENU FixPro")
        print("=" * 50)
        print("1 - Inscription Artisan")
        print("2 - Inscription Client")
        print("3 - Chercher un artisan (géolocalisation)")
        print("4 - Enregistrer une intervention")
        print("5 - Évaluer une intervention")
        print("6 - Effectuer un paiement")
        print("7 - Voir les notifications")
        print("8 - Voir les avis d'un artisan")
        print("9 - Quitter")
        print("=" * 50)
        
        choix = input("Choisis une option (1-9): ").strip()
        
        if choix == "1":
            inscription_artisan(curseur, connexion)
        elif choix == "2":
            inscription_client(curseur, connexion)
        elif choix == "3":
            chercher_artisan(curseur)
        elif choix == "4":
            enregistrer_intervention(curseur, connexion)
        elif choix == "5":
            evaluer_intervention(curseur, connexion)
        elif choix == "6":
            effectuer_paiement(curseur, connexion)
        elif choix == "7":
            voir_notifications(curseur)
        elif choix == "8":
            voir_avis_artisan(curseur)
        elif choix == "9":
            print("\n✓ Merci d'avoir utilisé FixPro! Au revoir!")
            connexion.close()
            break
        else:
            print("✗ Option invalide, réessaye!")


def inscription_artisan(curseur, connexion):
    """Formulaire d'inscription pour un artisan"""
    print("\n" + "=" * 50)
    print("Formulaire d'Inscription Artisan FixPro")
    print("=" * 50)
    
    nom = input("Ton nom complet: ").strip()
    prenom = input("Ton prénom: ").strip()
    telephone = input("Ton numéro de téléphone: ").strip()
    
    print("\nChoisis ton métier:")
    print("1 - Plombier")
    print("2 - Electricien")
    print("3 - Frigoriste")
    
    choix_metier = input("Tape 1, 2 ou 3: ").strip()
    metiers = {"1": "Plombier", "2": "Electricien", "3": "Frigoriste"}
    metier = metiers.get(choix_metier, "Métier inconnu")
    
    zone = input("Ton quartier (ex: Kaloum, Ratoma, Flamadina): ").strip()
    latitude = float(input("Ton latitude (ex: 9.5412): ").strip())
    longitude = float(input("Ton longitude (ex: -13.7531): ").strip())
    tarif_horaire = float(input("Ton tarif horaire (GNF): ").strip())
    
    artisan = Artisan(nom, prenom, telephone, metier, zone, latitude, longitude, tarif_horaire)
    artisan.sauvegarder(curseur, connexion)
    artisan.afficher_profil()


def inscription_client(curseur, connexion):
    """Formulaire d'inscription pour un client"""
    print("\n" + "=" * 50)
    print("Formulaire d'Inscription Client FixPro")
    print("=" * 50)
    
    nom = input("Ton nom complet: ").strip()
    telephone = input("Ton numéro de téléphone: ").strip()
    latitude = float(input("Ta latitude (ex: 9.5412): ").strip())
    longitude = float(input("Ta longitude (ex: -13.7531): ").strip())
    
    client = Client(nom, telephone, latitude, longitude)
    client.sauvegarder(curseur, connexion)


def chercher_artisan(curseur):
    """Rechercher un artisan proche avec géolocalisation"""
    print("\n" + "=" * 50)
    print("Recherche d'Artisan par Géolocalisation")
    print("=" * 50)
    
    client_lat = float(input("Ta latitude: ").strip())
    client_lon = float(input("Ta longitude: ").strip())
    
    print("\nChoisis le métier recherché:")
    print("1 - Plombier")
    print("2 - Electricien")
    print("3 - Frigoriste")
    
    choix_metier = input("Tape 1, 2 ou 3: ").strip()
    metiers = {"1": "Plombier", "2": "Electricien", "3": "Frigoriste"}
    metier = metiers.get(choix_metier, "Métier inconnu")
    
    distance_max = float(input("Distance maximale en km (défaut 10): ").strip() or "10")
    
    artisans = trouver_artisans_proches(client_lat, client_lon, metier, curseur, distance_max)
    
    if artisans:
        print(f"\n✓ {len(artisans)} artisan(s) trouvé(s):")
        print("-" * 50)
        for i, artisan in enumerate(artisans, 1):
            print(f"{i}. {artisan['nom']} {artisan['prenom']}")
            print(f"   Téléphone: {artisan['telephone']}")
            print(f"   Distance: {artisan['distance']} km")
            print()
    else:
        print(f"✗ Aucun artisan trouvé dans un rayon de {distance_max} km")


def enregistrer_intervention(curseur, connexion):
    """Enregistrer une intervention et calculer la commission"""
    print("\n" + "=" * 50)
    print("Enregistrement d'une Intervention")
    print("=" * 50)
    
    artisan_id = input("ID de l'artisan: ").strip()
    client_id = input("ID du client: ").strip()
    tarif_intervention = float(input("Tarif de l'intervention (GNF): ").strip())
    
    intervention = Intervention(int(artisan_id), int(client_id), tarif_intervention)
    intervention.afficher_details()
    
    confirmation = input("\nConfirmer l'enregistrement? (O/N): ").strip().upper()
    if confirmation == "O":
        intervention_id = intervention.sauvegarder(curseur, connexion)
        
        if intervention_id:
            # Créer une notification pour l'artisan
            notif = Notification(int(artisan_id), "artisan", 
                               "Nouvelle intervention", 
                               f"Une nouvelle intervention a été enregistrée (Montant: {tarif_intervention} GNF)")
            notif.sauvegarder(curseur, connexion)


def evaluer_intervention(curseur, connexion):
    """Évaluer un artisan après une intervention"""
    print("\n" + "=" * 50)
    print("Évaluation d'une Intervention")
    print("=" * 50)
    
    intervention_id = input("ID de l'intervention: ").strip()
    artisan_id = input("ID de l'artisan: ").strip()
    client_id = input("ID du client: ").strip()
    
    print("\nNote l'artisan (1-5 étoiles):")
    while True:
        try:
            note = int(input("Tape 1, 2, 3, 4 ou 5: ").strip())
            if 1 <= note <= 5:
                break
            print("✗ La note doit être entre 1 et 5!")
        except ValueError:
            print("✗ Entrée invalide!")
    