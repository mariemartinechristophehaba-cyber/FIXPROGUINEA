-- Active / suspendre un utilisateur
ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1;
