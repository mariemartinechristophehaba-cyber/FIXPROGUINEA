-- =====================================================================
-- FixPro - Schema de base de donnees (SQLite, developpement local)
-- =====================================================================
-- Equivalent de schema.sql, adapte a la syntaxe SQLite.
-- Applique automatiquement par : python manage.py init-db
-- =====================================================================

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT UNIQUE,
    phone           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'client',
    full_name       TEXT NOT NULL,
    civility        TEXT,
    company_name    TEXT,
    profession      TEXT,
    skills          TEXT,
    mobility        TEXT,
    insurance       TEXT,
    insurance_policy TEXT,
    bank_name       TEXT,
    bank_account    TEXT,
    city            TEXT,
    bio             TEXT,
    latitude        REAL DEFAULT 0,
    longitude       REAL DEFAULT 0,
    hourly_rate     REAL DEFAULT 0,
    is_verified     INTEGER DEFAULT 0,
    photo_url       TEXT,
    quartier        TEXT,
    availability_status TEXT DEFAULT 'hors_ligne',
    estimated_delay TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS service_categories (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT UNIQUE NOT NULL,
    diagnostic_price  REAL DEFAULT 0,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requests (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artisan_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    title              TEXT NOT NULL,
    description        TEXT NOT NULL,
    category           TEXT,
    address            TEXT,
    photo_url          TEXT,
    diagnostic_price   REAL DEFAULT 0,
    budget             REAL DEFAULT 0,
    quote_amount       REAL DEFAULT 0,
    quote_description  TEXT,
    quote_status       TEXT DEFAULT 'none',
    quote_proposed_at  TEXT,
    quote_approved_at  TEXT,
    status             TEXT DEFAULT 'pending',
    created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at         TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    sender_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content      TEXT NOT NULL,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    amount       REAL NOT NULL,
    method       TEXT DEFAULT 'cash',
    status       TEXT DEFAULT 'pending',
    reference    TEXT,
    details      TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    client_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artisan_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating      INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment     TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email          ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role           ON users(role);
CREATE INDEX IF NOT EXISTS idx_requests_client_id   ON requests(client_id);
CREATE INDEX IF NOT EXISTS idx_requests_artisan_id  ON requests(artisan_id);
CREATE INDEX IF NOT EXISTS idx_requests_status      ON requests(status);
CREATE INDEX IF NOT EXISTS idx_messages_request_id  ON messages(request_id);
CREATE INDEX IF NOT EXISTS idx_payments_request_id  ON payments(request_id);

INSERT OR IGNORE INTO service_categories (name, diagnostic_price) VALUES
    ('Plombier',     50000),
    ('Électricien',  45000),
    ('Frigoriste',   65000),
    ('Menuisier',    40000),
    ('Chauffagiste', 55000),
    ('Serrurier',    48000);
