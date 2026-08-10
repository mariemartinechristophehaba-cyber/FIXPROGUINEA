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