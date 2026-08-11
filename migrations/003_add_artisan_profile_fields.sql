-- Colonnes manquantes pour les fiches technicien
ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS quartier TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS availability_status TEXT DEFAULT 'hors_ligne';
ALTER TABLE users ADD COLUMN IF NOT EXISTS estimated_delay TEXT;
