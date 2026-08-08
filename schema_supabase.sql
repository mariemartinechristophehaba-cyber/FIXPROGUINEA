-- Schéma FixPro adapté pour PostgreSQL/Supabase
-- Utiliser ce script dans l'éditeur SQL Supabase

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT,
    profession TEXT,
    city TEXT,
    bio TEXT,
    latitude REAL DEFAULT 0,
    longitude REAL DEFAULT 0,
    hourly_rate REAL DEFAULT 0,
    is_verified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requests (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL,
    artisan_id INTEGER,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT,
    address TEXT,
    photo_url TEXT,
    diagnostic_price REAL DEFAULT 0,
    budget REAL DEFAULT 0,
    quote_amount REAL DEFAULT 0,
    quote_description TEXT,
    quote_status TEXT DEFAULT 'none',
    quote_proposed_at TEXT,
    quote_approved_at TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS service_categories (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    diagnostic_price REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    method TEXT DEFAULT 'cash',
    status TEXT DEFAULT 'pending',
    reference TEXT,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS artisans (
    id SERIAL PRIMARY KEY,
    nom TEXT NOT NULL,
    prenom TEXT NOT NULL,
    telephone TEXT NOT NULL UNIQUE,
    metier TEXT NOT NULL,
    zone TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    tarif_horaire REAL NOT NULL,
    taux_commission INTEGER DEFAULT 10,
    date_inscription TEXT DEFAULT CURRENT_TIMESTAMP,
    statut TEXT DEFAULT 'actif'
);

CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    nom TEXT NOT NULL,
    telephone TEXT NOT NULL UNIQUE,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    date_inscription TEXT DEFAULT CURRENT_TIMESTAMP,
    statut TEXT DEFAULT 'actif'
);

-- Index pour optimiser les performances
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_requests_client_id ON requests(client_id);
CREATE INDEX IF NOT EXISTS idx_requests_artisan_id ON requests(artisan_id);
CREATE INDEX IF NOT EXISTS idx_messages_request_id ON messages(request_id);
CREATE INDEX IF NOT EXISTS idx_payments_request_id ON payments(request_id);