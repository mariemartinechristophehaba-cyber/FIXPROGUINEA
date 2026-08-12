-- Tickets de contact client -> FixPro/Admin
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
