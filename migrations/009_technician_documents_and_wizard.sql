-- Inscription professionnelle des techniciens : documents et champs supplementaires
ALTER TABLE users ADD COLUMN zone_intervention TEXT;
ALTER TABLE users ADD COLUMN years_experience INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS technician_documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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
