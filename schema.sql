-- =====================================================================
-- FixPro - Schema de base de donnees (PostgreSQL / Supabase)
-- =====================================================================
-- A executer une seule fois dans l'editeur SQL de Supabase.
-- Ce script est idempotent : il peut etre relance sans risque.
-- =====================================================================

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
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
    is_active       INTEGER DEFAULT 1,
    photo_url       TEXT,
    quartier        TEXT,
    zone_intervention TEXT,
    years_experience  INTEGER DEFAULT 0,
    availability_status TEXT DEFAULT 'hors_ligne',
    estimated_delay TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS service_categories (
    id                SERIAL PRIMARY KEY,
    name              TEXT UNIQUE NOT NULL,
    diagnostic_price  REAL DEFAULT 0,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requests (
    id                 SERIAL PRIMARY KEY,
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
    id           SERIAL PRIMARY KEY,
    request_id   INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    sender_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content      TEXT NOT NULL,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id                 SERIAL PRIMARY KEY,
    request_id         INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    amount             REAL NOT NULL,
    commission_amount  REAL DEFAULT 0,
    paid_to_artisan_at TEXT,
    method             TEXT DEFAULT 'cash',
    status             TEXT DEFAULT 'pending',
    reference          TEXT,
    details            TEXT,
    created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at         TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    id          SERIAL PRIMARY KEY,
    request_id  INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    client_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artisan_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating      INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment     TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_tickets (
    id          SERIAL PRIMARY KEY,
    client_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artisan_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    subject     TEXT,
    message     TEXT NOT NULL,
    status      TEXT DEFAULT 'open',
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_messages (
    id          SERIAL PRIMARY KEY,
    ticket_id   INTEGER NOT NULL REFERENCES admin_tickets(id) ON DELETE CASCADE,
    sender_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS technician_locations (
    technician_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS technician_documents (
    id              SERIAL PRIMARY KEY,
    technician_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_type   TEXT NOT NULL,
    file_name       TEXT,
    mime_type       TEXT,
    file_size       INTEGER,
    content_base64  TEXT,
    status          TEXT DEFAULT 'pending',
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_technician_documents_technician ON technician_documents(technician_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id              SERIAL PRIMARY KEY,
    admin_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    admin_email     TEXT,
    action          TEXT NOT NULL,
    target_type     TEXT,
    target_id       INTEGER,
    details         TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at        ON admin_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_messages_ticket        ON admin_messages(ticket_id);
CREATE INDEX IF NOT EXISTS idx_technician_locations_updated ON technician_locations(updated_at);
CREATE INDEX IF NOT EXISTS idx_users_email                  ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role           ON users(role);
CREATE INDEX IF NOT EXISTS idx_requests_client_id   ON requests(client_id);
CREATE INDEX IF NOT EXISTS idx_requests_artisan_id  ON requests(artisan_id);
CREATE INDEX IF NOT EXISTS idx_requests_status      ON requests(status);
CREATE INDEX IF NOT EXISTS idx_messages_request_id  ON messages(request_id);
CREATE INDEX IF NOT EXISTS idx_payments_request_id  ON payments(request_id);

-- Metiers proposes par la plateforme, avec le prix du diagnostic (GNF).
INSERT INTO service_categories (name, diagnostic_price) VALUES
    ('Plombier',     50000),
    ('Électricien',  45000),
    ('Frigoriste',   65000),
    ('Menuisier',    40000),
    ('Chauffagiste', 55000),
    ('Serrurier',    48000)
ON CONFLICT (name) DO NOTHING;
