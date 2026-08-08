# Cahier de charge - FixPro

## 1. Vision globale

FixPro est une plateforme web qui met en relation des clients ayant besoin d’un service à domicile et des artisans qualifiés. L’objectif est de permettre à un client de publier une demande, de trouver rapidement un artisan fiable, de suivre l’intervention, puis de donner une évaluation.

L’application doit être simple, moderne, rapide, fiable et facile à utiliser pour un utilisateur non technique.

---

## 2. Problème à résoudre

Aujourd’hui, beaucoup de clients ont du mal à :
- trouver un artisan fiable rapidement,
- comparer plusieurs prestataires,
- suivre une demande de service,
- communiquer clairement avec l’artisan,
- payer et valider l’intervention de manière sécurisée.

FixPro vise à centraliser tout ce processus dans une seule application.

---

## 3. Objectif principal

Créer une application web complète qui permette :
1. aux clients de demander un service,
2. aux artisans de répondre à ces demandes,
3. aux utilisateurs de communiquer et de valider les interventions,
4. aux administrateurs de superviser le fonctionnement de la plateforme.

---

## 4. Utilisateurs cibles

### 4.1 Client
Un client veut :
- publier une demande de service,
- voir des artisans disponibles,
- choisir un artisan,
- suivre l’avancement,
- payer et laisser un avis.

### 4.2 Artisan
Un artisan veut :
- créer son profil,
- montrer ses compétences,
- recevoir des demandes,
- proposer un prix ou une disponibilité,
- gérer ses interventions.

### 4.3 Administrateur
Un administrateur veut :
- valider les comptes,
- superviser les demandes,
- gérer les utilisateurs,
- modérer les contenus et les paiements.

---

## 5. Vision produit

FixPro doit devenir une application de confiance, simple à utiliser, pensée pour le marché local, avec :
- une interface moderne et claire,
- un parcours utilisateur fluide,
- une logique métier solide,
- une architecture fiable pour évoluer ensuite vers une version mobile ou SaaS.

---

## 6. Fonctionnalités principales

### 6.1 Inscription et connexion
- inscription client,
- inscription artisan,
- connexion avec email/mot de passe,
- récupération de mot de passe,
- gestion du profil utilisateur.

### 6.2 Gestion des profils
- profil client avec coordonnées et préférences,
- profil artisan avec spécialité, expérience, localisation, photo, tarif,
- possibilité de modifier ses informations.

### 6.3 Demandes de service
- un client peut créer une demande,
- il précise la catégorie de service, la localisation, le budget, la date et les détails,
- la demande peut être visible par les artisans concernés.

### 6.4 Recherche d’artisans
- recherche par métier,
- recherche par ville ou localisation,
- filtres par disponibilité, note, tarif,
- affichage du profil de l’artisan.

### 6.5 Réservation et prise en charge
- un artisan peut accepter une demande,
- un client peut valider le choix,
- l’état de la demande évolue : en attente, acceptée, en cours, terminée, annulée.

### 6.6 Messagerie interne
- chat simple entre client et artisan,
- messages liés à une demande,
- historique des conversations.

### 6.7 Paiement
- paiement sécurisé pour une intervention,
- gestion des montants,
- suivi des transactions,
- statut payé / en attente / échoué.

### 6.8 Évaluation et avis
- un client peut noter l’artisan,
- un artisan peut noter le client,
- affichage des notes et commentaires.

### 6.9 Administration
- tableau de bord admin,
- gestion des utilisateurs,
- gestion des demandes,
- gestion des paiements et des signalements.

---

## 7. Fonctionnalités MVP (priorité 1)

Pour démarrer proprement, l’application doit d’abord couvrir le cœur du besoin.

### MVP obligatoire
- inscription / connexion,
- profils client et artisan,
- création de demande,
- recherche d’artisans,
- acceptation d’une demande,
- suivi de l’état d’une intervention,
- chat simple,
- page d’administration minimale.

### MVP à éviter au début
- paiement avancé en plusieurs étapes,
- notifications push,
- système de géolocalisation complexe,
- fonctionnalités trop riches non essentielles.

---

## 8. Architecture technique recommandée

### Stack recommandée pour le MVP
- Backend : Python avec Flask
- Templates : Jinja2
- Base de données : SQLite pour le développement, puis PostgreSQL en production
- Authentification : Flask-Login
- Validation : Flask-WTF / forms
- Style : HTML, CSS, Bootstrap
- Optionnel pour le chat : Flask-SocketIO

### Structure logique du projet
- app.py : point d’entrée principal
- templates/ : pages HTML
- static/ : CSS, JS, images
- models/ : logique métier et structure des données
- routes/ : gestion des endpoints
- services/ : logique métier complexe
- tests/ : tests unitaires et fonctionnels

---

## 9. Modèle de données principal

### Tables principales
- users
- clients
- artisans
- requests
- messages
- payments
- reviews
- admin_logs

### Relations attendues
- un utilisateur peut être client, artisan ou administrateur,
- un client peut créer plusieurs demandes,
- une demande peut être associée à un artisan,
- un artisan peut recevoir plusieurs demandes,
- un chat est lié à une demande,
- un paiement est lié à une demande.

---

## 10. Règles métier essentielles

- un client ne peut publier qu’une demande à la fois dans certaines catégories,
- un artisan ne peut accepter qu’une demande à la fois si la disponibilité ne le permet pas,
- une demande doit pouvoir évoluer dans un état clair,
- un paiement doit être lié à une intervention validée,
- les avis doivent être associés à une intervention terminée.

---

## 11. Expérience utilisateur attendue

L’application doit être :
- intuitive,
- rapide,
- claire visuellement,
- adaptée à un usage mobile et bureau,
- pensée pour une prise en main facile par un utilisateur novice.

---

## 12. Critères de succès

La solution sera considérée comme réussie si :
- un client peut créer une demande sans aide,
- un artisan peut créer un profil et répondre à une demande,
- une demande peut aller de l’état “créée” à “terminée”,
- la communication est fluide,
- les administrateurs peuvent superviser l’activité,
- l’application fonctionne correctement sur un environnement local puis en production.

---

## 13. Plan de développement par phases

### Phase 1 - Fondation
- installer et nettoyer l’environnement,
- définir la structure du projet,
- mettre en place la base de données,
- créer l’authentification de base,
- créer les pages d’inscription et de connexion.

### Phase 2 - Core produit
- profils client/artisan,
- création de demandes,
- recherche d’artisans,
- acceptation de demandes.

### Phase 3 - Expérience utilisateur
- chat,
- suivi des interventions,
- notifications simples,
- amélioration de l’interface.

### Phase 4 - Fiabilité et production
- tests,
- sécurité,
- logs,
- déploiement,
- sauvegardes et configuration d’environnement.

---

## 14. Recommandation pour avancer avec Cursor

Comme vous êtes novice, il est préférable de travailler par petites tâches, une par une.

### Méthode recommandée
1. définir une fonctionnalité simple,
2. demander à Cursor de l’implémenter en une seule étape,
3. tester immédiatement,
4. corriger les erreurs avant de passer à la suivante.

### Exemples de demandes à faire à Cursor
- “Ajoute la page d’inscription client et le formulaire associé.”
- “Crée la route pour enregistrer une demande de service.”
- “Ajoute la page de profil artisan.”
- “Implémente la recherche d’artisans par spécialité.”

### Règle d’or
Ne pas vouloir tout construire d’un coup. Il faut avancer par blocs simples et stables.

---

## 15. Résumé simple de la vision

FixPro doit devenir une plateforme web fiable permettant à un client de trouver un artisan rapidement, de suivre une intervention et de faire confiance à la plateforme.

Le but n’est pas de faire une application parfaite dès le départ, mais une vraie application fonctionnelle, claire, évolutive et prête à être améliorée ensuite.

---

## 16. Prochaine étape recommandée

La première version à construire doit contenir :
- inscription/connexion,
- profil utilisateur,
- création de demande,
- recherche d’artisan,
- état d’une demande.

C’est ce cœur de produit qu’il faut mettre en place en premier.
