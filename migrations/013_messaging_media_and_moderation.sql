-- =====================================================================
-- 013 — Messagerie riche client <-> technicien
-- =====================================================================
-- Raison :
--   Le bouton "Message" du profil technicien ouvre un chat 1-a-1. Cette
--   migration ajoute le support des pieces jointes (photo / document), des
--   messages vocaux, des statuts de message (recu / lu) et de la moderation
--   par conversation (mute, blocage, signalement, suppression cote client).
--
-- Idempotent (IF NOT EXISTS partout). A executer dans l'editeur SQL Supabase.
-- Le meme schema est aussi applique automatiquement au demarrage par
-- _migrate_messaging() dans fixpro_app.py.
-- =====================================================================

-- Colonnes des messages : type + piece jointe + duree vocal + accuse de reception
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS message_type    TEXT DEFAULT 'text';
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS attachment_url  TEXT;
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS attachment_name TEXT;
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS duration_ms     INTEGER;
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS is_delivered    INTEGER DEFAULT 0;

-- Preferences par conversation : notifications coupees + suppression cote client
CREATE TABLE IF NOT EXISTS conversation_prefs (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    muted           INTEGER NOT NULL DEFAULT 0,
    deleted_at      TIMESTAMP,
    PRIMARY KEY (user_id, conversation_id)
);

-- Blocages entre utilisateurs (empeche messages ET appels)
CREATE TABLE IF NOT EXISTS user_blocks (
    blocker_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (blocker_id, blocked_id)
);

-- Signalements de conversation / d'utilisateur (revue cote admin)
CREATE TABLE IF NOT EXISTS conversation_reports (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    reporter_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reported_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reason          TEXT NOT NULL DEFAULT '',
    details         TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'new',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_reports_status ON conversation_reports(status);
