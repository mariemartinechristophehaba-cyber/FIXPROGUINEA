-- Geolocalisation temps reel des techniciens
CREATE TABLE IF NOT EXISTS technician_locations (
    technician_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_technician_locations_updated ON technician_locations(updated_at);
