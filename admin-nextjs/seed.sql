-- Donnees de test pour FixPro Admin

INSERT INTO techniciens (nom, prenom, metier, zone, telephone, email, note, statut, created_at) VALUES
('Bah', 'Mamadou', 'Plomberie', 'Kaloum', '+224 620 00 00 01', 'mamadou@fixpro.test', 4.8, 'verified', now()),
('Diallo', 'Amadou', 'Electricite', 'Dixinn', '+224 620 00 00 02', 'amadou@fixpro.test', 4.2, 'pending', now()),
('Camara', 'Fatou', 'Froid', 'Matam', '+224 620 00 00 03', 'fatou@fixpro.test', 4.5, 'verified', now()),
('Sylla', 'Ibrahim', 'Menuiserie', 'Coleah', '+224 620 00 00 04', 'ibrahim@fixpro.test', 3.9, 'rejected', now());

INSERT INTO demandes (client_nom, client_tel, metier, zone, description, statut, montant, paiement_statut, technicien_id, created_at) VALUES
('Amadou Diallo', '+224 620 00 00 11', 'Plomberie', 'Kaloum', 'Fuite sous evier', 'new', 150000, 'unpaid', NULL, now()),
('Fatou Camara', '+224 620 00 00 12', 'Electricite', 'Dixinn', 'Installation luminaire', 'assigned', 225000, 'unpaid', 1, now()),
('Mamadou Barry', '+224 620 00 00 13', 'Froid', 'Matam', 'Climatisation en panne', 'done', 180000, 'paid', 3, now()),
('Aminata Sow', '+224 620 00 00 14', 'Menuiserie', 'Coleah', 'Porte cassee', 'new', 320000, 'unpaid', NULL, now());
