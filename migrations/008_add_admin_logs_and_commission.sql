-- Panneau administrateur : logs et commission
CREATE TABLE IF NOT EXISTS admin_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,
    target_type     TEXT,
    target_id       INTEGER,
    details         TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at ON admin_logs(created_at DESC);

ALTER TABLE payments ADD COLUMN commission_amount REAL DEFAULT 0;
