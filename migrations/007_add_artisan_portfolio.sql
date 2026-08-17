-- Ajoute la table de portfolio des artisans.

CREATE TABLE IF NOT EXISTS artisan_portfolio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artisan_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    photo_url       TEXT NOT NULL,
    caption         TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_artisan_portfolio_artisan ON artisan_portfolio(artisan_id);
