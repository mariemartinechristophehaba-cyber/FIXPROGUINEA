-- Ajoute les champs urgence et telephone de contact pour les demandes.

ALTER TABLE requests ADD COLUMN IF NOT EXISTS urgency TEXT DEFAULT 'cette_semaine';
ALTER TABLE requests ADD COLUMN IF NOT EXISTS phone_contact TEXT;
