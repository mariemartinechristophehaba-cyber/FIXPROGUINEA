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
    account_status    TEXT DEFAULT 'ACTIVE',
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
    reference          TEXT UNIQUE,
    service            TEXT,
    requested_date     TEXT,
    requested_time     TEXT,
    latitude           REAL DEFAULT 0,
    longitude          REAL DEFAULT 0,
    estimated_price    REAL DEFAULT 0,
    final_price        REAL DEFAULT 0,
    commission_rate    REAL DEFAULT 10,
    commission_amount  REAL DEFAULT 0,
    professional_amount REAL DEFAULT 0,
    payment_status     TEXT DEFAULT 'PENDING',
    completed_at       TEXT,
    status             TEXT DEFAULT 'REQUESTED',
    urgency            TEXT DEFAULT 'cette_semaine',
    phone_contact      TEXT,
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

CREATE TABLE IF NOT EXISTS artisan_portfolio (
    id              SERIAL PRIMARY KEY,
    artisan_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    photo_url       TEXT NOT NULL,
    caption         TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_artisan_portfolio_artisan ON artisan_portfolio(artisan_id);

-- Metiers proposes par la plateforme, avec le prix du diagnostic (GNF).
INSERT INTO service_categories (name, diagnostic_price) VALUES
    ('Plombier',     50000),
    ('Électricien',  45000),
    ('Frigoriste',   65000),
    ('Menuisier',    40000),
    ('Chauffagiste', 55000),
    ('Serrurier',    48000)
ON CONFLICT (name) DO NOTHING;

-- Migrations idempotentes pour les evolutions du schema
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


-- Services lies a un domaine professionnel
CREATE TABLE IF NOT EXISTS services (
    id              SERIAL PRIMARY KEY,
    category_id     INTEGER NOT NULL REFERENCES service_categories(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category_id, name)
);

CREATE INDEX IF NOT EXISTS idx_services_category ON services(category_id);

-- Association techniciens <-> services
CREATE TABLE IF NOT EXISTS artisan_services (
    artisan_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    service_id      INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    PRIMARY KEY (artisan_id, service_id)
);

INSERT INTO services (category_id, name)
SELECT c.id, s.name
FROM service_categories c
CROSS JOIN LATERAL (VALUES
    ('Plombier', 'Reparation de fuite d''eau'),
    ('Plombier', 'Reparation de robinet'),
    ('Plombier', 'Installation sanitaire'),
    ('Plombier', 'Debouchage'),
    ('Plombier', 'Reparation WC'),
    ('Plombier', 'Installation de tuyauterie'),
    ('Électricien', 'Depannage electrique'),
    ('Électricien', 'Installation electrique'),
    ('Électricien', 'Installation d''eclairage'),
    ('Électricien', 'Reparation de tableau electrique'),
    ('Électricien', 'Installation de prises'),
    ('Électricien', 'Diagnostic electrique'),
    ('Frigoriste', 'Installation de climatisation'),
    ('Frigoriste', 'Entretien de climatisation'),
    ('Frigoriste', 'Depannage de climatisation'),
    ('Frigoriste', 'Reparation de refrigerateur'),
    ('Frigoriste', 'Reparation de congelateur'),
    ('Frigoriste', 'Maintenance systeme frigorifique'),
    ('Menuisier', 'Reparation de porte'),
    ('Menuisier', 'Installation de porte'),
    ('Menuisier', 'Reparation de fenetre'),
    ('Menuisier', 'Fabrication de meuble'),
    ('Menuisier', 'Installation de placard'),
    ('Menuisier', 'Travaux de menuiserie'),
    ('Chauffagiste', 'Reparation de chaudiere'),
    ('Chauffagiste', 'Entretien de chaudiere'),
    ('Chauffagiste', 'Installation de chauffage'),
    ('Chauffagiste', 'Depannage chauffage'),
    ('Serrurier', 'Ouverture de porte'),
    ('Serrurier', 'Changement de serrure'),
    ('Serrurier', 'Reparation de serrure'),
    ('Serrurier', 'Installation de verrous'),
    ('Serrurier', 'Depannage serrurerie')
) AS s(category_name, name)
WHERE c.name = s.category_name
ON CONFLICT (category_id, name) DO NOTHING;


-- Conversations et messages client <-> admin
CREATE TABLE IF NOT EXISTS conversations (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artisan_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    request_id      INTEGER REFERENCES requests(id) ON DELETE SET NULL,
    subject         TEXT,
    status          TEXT DEFAULT 'open',
    ai_active       INTEGER DEFAULT 1,
    ai_category     TEXT,
    urgency         TEXT,
    needs_human     INTEGER DEFAULT 0,
    needs_technician INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Migrations idempotentes pour les conversations
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS artisan_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ai_active INTEGER DEFAULT 1;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ai_category TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS urgency TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS needs_human INTEGER DEFAULT 0;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS needs_technician INTEGER DEFAULT 0;

-- Migrations idempotentes pour les conversations
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ai_active INTEGER DEFAULT 1;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ai_category TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS urgency TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS needs_human INTEGER DEFAULT 0;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS needs_technician INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_conversations_client ON conversations(client_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender_role     TEXT NOT NULL,
    content         TEXT NOT NULL,
    is_read         INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_conv ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_unread ON conversation_messages(conversation_id, is_read);
