-- ========== SCRIPT DE CRÉATION DE LA BASE DE DONNÉES FIXPRO ==========

-- Utiliser la base de données FixPro
USE FixPro;

-- ========== TABLE ARTISANS ==========
CREATE TABLE IF NOT EXISTS artisans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(100) NOT NULL,
    prenom VARCHAR(100) NOT NULL,
    telephone VARCHAR(20) NOT NULL UNIQUE,
    metier VARCHAR(50) NOT NULL,
    zone VARCHAR(100) NOT NULL,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    tarif_horaire DECIMAL(10, 2) NOT NULL,
    taux_commission INT DEFAULT 10,
    date_inscription TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    statut VARCHAR(20) DEFAULT 'actif'
);

-- ========== TABLE CLIENTS ==========
CREATE TABLE IF NOT EXISTS clients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(100) NOT NULL,
    telephone VARCHAR(20) NOT NULL UNIQUE,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    date_inscription TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    statut VARCHAR(20) DEFAULT 'actif'
);

-- ========== TABLE INTERVENTIONS ==========
CREATE TABLE IF NOT EXISTS interventions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    artisan_id INT NOT NULL,
    client_id INT NOT NULL,
    tarif_intervention DECIMAL(10, 2) NOT NULL,
    commission_fixpro DECIMAL(10, 2) NOT NULL,
    montant_artisan DECIMAL(10, 2) GENERATED ALWAYS AS (tarif_intervention - commission_fixpro) STORED,
    statut VARCHAR(50) DEFAULT 'en attente',
    date_intervention TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_completion TIMESTAMP NULL,
    FOREIGN KEY (artisan_id) REFERENCES artisans(id) ON DELETE CASCADE,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

-- ========== TABLE TRANSACTIONS (SUIVI DES COMMISSIONS) ==========
CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    intervention_id INT NOT NULL,
    montant_commission DECIMAL(10, 2) NOT NULL,
    statut VARCHAR(50) DEFAULT 'en attente',
    date_transaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_paiement TIMESTAMP NULL,
    FOREIGN KEY (intervention_id) REFERENCES interventions(id) ON DELETE CASCADE
);

-- ========== TABLE ÉVALUATIONS ==========
CREATE TABLE IF NOT EXISTS evaluations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    intervention_id INT NOT NULL,
    artisan_id INT NOT NULL,
    client_id INT NOT NULL,
    note INT NOT NULL CHECK (note >= 1 AND note <= 5),
    commentaire TEXT,
    date_evaluation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (intervention_id) REFERENCES interventions(id) ON DELETE CASCADE,
    FOREIGN KEY (artisan_id) REFERENCES artisans(id) ON DELETE CASCADE,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

-- ========== TABLE PAIEMENTS ==========
CREATE TABLE IF NOT EXISTS paiements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    intervention_id INT NOT NULL,
    montant DECIMAL(10, 2) NOT NULL,
    methode_paiement VARCHAR(50) NOT NULL,
    statut VARCHAR(50) DEFAULT 'en attente',
    date_paiement TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reference_paiement VARCHAR(100),
    FOREIGN KEY (intervention_id) REFERENCES interventions(id) ON DELETE CASCADE
);

-- ========== TABLE NOTIFICATIONS ==========
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utilisateur_id INT NOT NULL,
    type_utilisateur VARCHAR(50) NOT NULL,
    titre VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    lue BOOLEAN DEFAULT FALSE,
    date_notification TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_utilisateur (utilisateur_id, type_utilisateur)
);

-- ========== INDEXES POUR OPTIMISATION ==========
CREATE INDEX idx_artisan_metier ON artisans(metier);
CREATE INDEX idx_artisan_zone ON artisans(zone);
CREATE INDEX idx_intervention_artisan ON interventions(artisan_id);
CREATE INDEX idx_intervention_client ON interventions(client_id);
CREATE INDEX idx_intervention_statut ON interventions(statut);
CREATE INDEX idx_evaluation_artisan ON evaluations(artisan_id);
CREATE INDEX idx_paiement_intervention ON paiements(intervention_id);
CREATE INDEX idx_paiement_statut ON paiements(statut);
CREATE INDEX idx_notification_utilisateur ON notifications(utilisateur_id);

-- ========== EXEMPLES DE DONNÉES (OPTIONNEL) ==========
-- Insérer des artisans d'exemple
INSERT INTO artisans (nom, prenom, telephone, metier, zone, latitude, longitude, tarif_horaire, taux_commission)
VALUES 
('Diallo', 'Mamadou', '+224627316069', 'Plombier', 'Kaloum', 9.5412, -13.7531, 50000, 10),
('Bah', 'Saïdou', '+224623456789', 'Electricien', 'Ratoma', 9.5420, -13.7450, 45000, 10),
('Camara', 'Mohamed', '+224621112222', 'Frigoriste', 'Flamadina', 9.5380, -13.7600, 55000, 10);

-- Insérer des clients d'exemple
INSERT INTO clients (nom, telephone, latitude, longitude)
VALUES 
('Sylla', '+224625555555', 9.5415, -13.7535),
('Toure', '+224626666666', 9.5418, -13.7455),
('Kone', '+224627777777', 9.5385, -13.7595);

-- ========== FIN DU SCRIPT ==========
