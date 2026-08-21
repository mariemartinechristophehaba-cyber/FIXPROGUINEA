-- Migrations idempotentes pour le Dashboard Admin FixPro
-- Executer dans Supabase SQL Editor

ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status TEXT DEFAULT 'ACTIVE';

ALTER TABLE requests ADD COLUMN IF NOT EXISTS reference TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_reference ON requests(reference);
ALTER TABLE requests ADD COLUMN IF NOT EXISTS service TEXT;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS requested_date TEXT;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS requested_time TEXT;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS latitude REAL DEFAULT 0;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS longitude REAL DEFAULT 0;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS estimated_price REAL DEFAULT 0;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS final_price REAL DEFAULT 0;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS commission_rate REAL DEFAULT 10;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS commission_amount REAL DEFAULT 0;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS professional_amount REAL DEFAULT 0;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'PENDING';
ALTER TABLE requests ADD COLUMN IF NOT EXISTS completed_at TEXT;

CREATE TABLE IF NOT EXISTS intervention_photos (
    id           SERIAL PRIMARY KEY,
    request_id   INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    photo_url    TEXT NOT NULL,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intervention_history (
    id          SERIAL PRIMARY KEY,
    request_id  INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    status      TEXT NOT NULL,
    actor       TEXT,
    note        TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
