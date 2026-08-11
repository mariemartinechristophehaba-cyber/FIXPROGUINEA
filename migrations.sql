-- Migrations pour ajouter les champs artisan a la table users
-- A executer dans Supabase SQL Editor si la table users existe deja

ALTER TABLE users ADD COLUMN IF NOT EXISTS civility TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS company_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS skills TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mobility TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS insurance TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS insurance_policy TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS bank_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS bank_account TEXT;

CREATE TABLE IF NOT EXISTS reviews (
    id          SERIAL PRIMARY KEY,
    request_id  INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    client_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artisan_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating      INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment     TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);