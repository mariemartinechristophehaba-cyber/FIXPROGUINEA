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
    is_active       INTEGER DEFAULT 1,
    photo_url       TEXT,
    quartier        TEXT,
    zone_intervention TEXT,
    years_experience  INTEGER DEFAULT 0,
    availability_status TEXT DEFAULT 'hors_ligne',
    available_days    TEXT,
    account_status    TEXT DEFAULT 'ACTIVE',
    verification_status TEXT,
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
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    sender_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content      TEXT NOT NULL,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id        INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    amount            REAL NOT NULL,
    commission_amount REAL DEFAULT 0,
    paid_to_artisan_at TEXT,
    method            TEXT DEFAULT 'cash',
    status            TEXT DEFAULT 'pending',
    reference         TEXT,
    details           TEXT,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at        TEXT DEFAULT CURRENT_TIMESTAMP
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

CREATE TABLE IF NOT EXISTS admin_tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artisan_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    subject     TEXT,
    message     TEXT NOT NULL,
    status      TEXT DEFAULT 'open',
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    technician_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_type   TEXT NOT NULL,
    file_name       TEXT,
    mime_type       TEXT,
    file_size       INTEGER,
    content_base64  TEXT,
    status          TEXT DEFAULT 'pending',
    original_file_name TEXT,
    rejection_reason TEXT,
    reviewed_at     TEXT,
    reviewed_by     INTEGER,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_technician_documents_technician ON technician_documents(technician_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    admin_email     TEXT,
    action          TEXT NOT NULL,
    target_type     TEXT,
    target_id       INTEGER,
    details         TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intervention_photos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id   INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    photo_url    TEXT NOT NULL,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intervention_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    status      TEXT NOT NULL,
    old_status  TEXT,
    new_status  TEXT,
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
CREATE INDEX IF NOT EXISTS idx_reviews_artisan_id   ON reviews(artisan_id);
CREATE INDEX IF NOT EXISTS idx_users_role_verified_active ON users(role, is_verified, is_active);
CREATE INDEX IF NOT EXISTS idx_users_profession     ON users(profession);
CREATE INDEX IF NOT EXISTS idx_users_city           ON users(city);
CREATE INDEX IF NOT EXISTS idx_requests_status_artisan ON requests(status, artisan_id);

CREATE TABLE IF NOT EXISTS artisan_portfolio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artisan_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    photo_url       TEXT NOT NULL,
    caption         TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_artisan_portfolio_artisan ON artisan_portfolio(artisan_id);

INSERT OR IGNORE INTO service_categories (name, diagnostic_price) VALUES
    ('Plombier',     50000),
    ('Électricien',  45000),
    ('Frigoriste',   65000),
    ('Menuisier',    40000),
    ('Chauffagiste', 55000),
    ('Serrurier',    48000);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    body        TEXT,
    type        TEXT DEFAULT 'info',
    is_read     INTEGER DEFAULT 0,
    data        TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(user_id, is_read);

-- Services lies a un domaine professionnel
CREATE TABLE IF NOT EXISTS services (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- Seed services par domaine
INSERT OR IGNORE INTO service_categories (name, diagnostic_price) VALUES
    ('Peintre',    40000),
    ('Autre',      30000);

INSERT OR IGNORE INTO services (category_id, name) VALUES
    ((SELECT id FROM service_categories WHERE name = 'Plombier'), 'Reparation de fuite d''eau'),
    ((SELECT id FROM service_categories WHERE name = 'Plombier'), 'Reparation de robinet'),
    ((SELECT id FROM service_categories WHERE name = 'Plombier'), 'Installation sanitaire'),
    ((SELECT id FROM service_categories WHERE name = 'Plombier'), 'Debouchage'),
    ((SELECT id FROM service_categories WHERE name = 'Plombier'), 'Reparation WC'),
    ((SELECT id FROM service_categories WHERE name = 'Plombier'), 'Installation de tuyauterie'),
    ((SELECT id FROM service_categories WHERE name = 'Électricien'), 'Depannage electrique'),
    ((SELECT id FROM service_categories WHERE name = 'Électricien'), 'Installation electrique'),
    ((SELECT id FROM service_categories WHERE name = 'Électricien'), 'Installation d''eclairage'),
    ((SELECT id FROM service_categories WHERE name = 'Électricien'), 'Reparation de tableau electrique'),
    ((SELECT id FROM service_categories WHERE name = 'Électricien'), 'Installation de prises'),
    ((SELECT id FROM service_categories WHERE name = 'Électricien'), 'Diagnostic electrique'),
    ((SELECT id FROM service_categories WHERE name = 'Frigoriste'), 'Installation de climatisation'),
    ((SELECT id FROM service_categories WHERE name = 'Frigoriste'), 'Entretien de climatisation'),
    ((SELECT id FROM service_categories WHERE name = 'Frigoriste'), 'Depannage de climatisation'),
    ((SELECT id FROM service_categories WHERE name = 'Frigoriste'), 'Reparation de refrigerateur'),
    ((SELECT id FROM service_categories WHERE name = 'Frigoriste'), 'Reparation de congelateur'),
    ((SELECT id FROM service_categories WHERE name = 'Frigoriste'), 'Maintenance systeme frigorifique'),
    ((SELECT id FROM service_categories WHERE name = 'Menuisier'), 'Reparation de porte'),
    ((SELECT id FROM service_categories WHERE name = 'Menuisier'), 'Installation de porte'),
    ((SELECT id FROM service_categories WHERE name = 'Menuisier'), 'Reparation de fenetre'),
    ((SELECT id FROM service_categories WHERE name = 'Menuisier'), 'Fabrication de meuble'),
    ((SELECT id FROM service_categories WHERE name = 'Menuisier'), 'Installation de placard'),
    ((SELECT id FROM service_categories WHERE name = 'Menuisier'), 'Travaux de menuiserie'),
    ((SELECT id FROM service_categories WHERE name = 'Chauffagiste'), 'Reparation de chaudiere'),
    ((SELECT id FROM service_categories WHERE name = 'Chauffagiste'), 'Entretien de chaudiere'),
    ((SELECT id FROM service_categories WHERE name = 'Chauffagiste'), 'Installation de chauffage'),
    ((SELECT id FROM service_categories WHERE name = 'Chauffagiste'), 'Depannage chauffage'),
    ((SELECT id FROM service_categories WHERE name = 'Serrurier'), 'Ouverture de porte'),
    ((SELECT id FROM service_categories WHERE name = 'Serrurier'), 'Changement de serrure'),
    ((SELECT id FROM service_categories WHERE name = 'Serrurier'), 'Reparation de serrure'),
    ((SELECT id FROM service_categories WHERE name = 'Serrurier'), 'Installation de verrous'),
    ((SELECT id FROM service_categories WHERE name = 'Serrurier'), 'Depannage serrurerie');


-- Conversations et messages client <-> admin
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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
    collected_info   TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_client ON conversations(client_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender_role     TEXT NOT NULL,
    content         TEXT NOT NULL,
    is_read         INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_conv ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_unread ON conversation_messages(conversation_id, is_read);

-- Contacts clients anonymes depuis les fiches techniciens
CREATE TABLE IF NOT EXISTS client_contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    artisan_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    phone           TEXT NOT NULL,
    status          TEXT DEFAULT 'nouveau',
    source          TEXT DEFAULT 'profil_artisan',
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_client_contacts_artisan ON client_contacts(artisan_id);
CREATE INDEX IF NOT EXISTS idx_client_contacts_phone ON client_contacts(phone);

-- Historique des evenements sur un contact
CREATE TABLE IF NOT EXISTS client_contact_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER NOT NULL REFERENCES client_contacts(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    details     TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================================
-- Abonnements techniciens (modele economique FixPro : abonnement mensuel,
-- PAS de commission par intervention)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS subscription_plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    price_month INTEGER NOT NULL DEFAULT 0,
    currency    TEXT NOT NULL DEFAULT 'GNF',
    features    TEXT DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS technician_subscriptions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    technician_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id       INTEGER REFERENCES subscription_plans(id) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'TRIAL',
    start_date    TEXT DEFAULT CURRENT_TIMESTAMP,
    end_date      TEXT,
    auto_renew    INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tech_subs_technician ON technician_subscriptions(technician_id);
CREATE INDEX IF NOT EXISTS idx_tech_subs_status ON technician_subscriptions(status);

CREATE TABLE IF NOT EXISTS subscription_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id INTEGER REFERENCES technician_subscriptions(id) ON DELETE SET NULL,
    plan_id         INTEGER REFERENCES subscription_plans(id) ON DELETE SET NULL,
    amount          INTEGER NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'GNF',
    payment_method  TEXT DEFAULT 'orange_money',
    transaction_reference TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    paid_at         TEXT,
    period_start    TEXT,
    period_end      TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sub_payments_user ON subscription_payments(user_id);
CREATE INDEX IF NOT EXISTS idx_sub_payments_status ON subscription_payments(status);

CREATE TABLE IF NOT EXISTS complaints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    technician_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    request_id      INTEGER REFERENCES requests(id) ON DELETE SET NULL,
    subject         TEXT NOT NULL,
    message         TEXT DEFAULT '',
    priority        TEXT NOT NULL DEFAULT 'normal',
    status          TEXT NOT NULL DEFAULT 'new',
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TEXT,
    resolved_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);

INSERT INTO subscription_plans (code, name, price_month, sort_order, features)
SELECT 'basic', 'Basic', 50000, 1, 'Profil verifie
Apparait dans la recherche
Messagerie avec les clients'
WHERE NOT EXISTS (SELECT 1 FROM subscription_plans WHERE code = 'basic');
INSERT INTO subscription_plans (code, name, price_month, sort_order, features)
SELECT 'pro', 'Pro', 100000, 2, 'Tout Basic
Mise en avant dans la recherche
Statistiques detaillees
Support prioritaire'
WHERE NOT EXISTS (SELECT 1 FROM subscription_plans WHERE code = 'pro');
INSERT INTO subscription_plans (code, name, price_month, sort_order, features)
SELECT 'premium', 'Premium', 200000, 3, 'Tout Pro
Badge Premium
En tete des resultats
Accompagnement dedie'
WHERE NOT EXISTS (SELECT 1 FROM subscription_plans WHERE code = 'premium');
