"""
Script de migration SQLite vers Supabase pour FixPro
Migre toutes les données de la base SQLite locale vers Supabase
"""

import sqlite3
import psycopg2
import os
from dotenv import load_dotenv
import logging

# Charger les variables d'environnement
load_dotenv()

# Configuration logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_sqlite_connection():
    """Connecte à la base SQLite locale"""
    try:
        conn = sqlite3.connect('fixpro.db')
        conn.row_factory = sqlite3.Row
        logger.info("Connexion SQLite établie")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Erreur de connexion SQLite: {e}")
        raise

def get_supabase_connection():
    """Connecte à Supabase via PostgreSQL"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        logger.error("DATABASE_URL non trouvé dans les variables d'environnement")
        raise ValueError("DATABASE_URL manquant")
    
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        logger.info("Connexion Supabase établie")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Erreur de connexion Supabase: {e}")
        raise

def migrate_table(sqlite_conn, pg_conn, table_name):
    """Migre une table spécifique de SQLite vers PostgreSQL"""
    logger.info(f"Migration de la table {table_name}...")
    
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    try:
        # Récupérer les données de SQLite
        sqlite_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            logger.info(f"Table {table_name} vide, rien à migrer")
            return
        
        # Récupérer les colonnes
        columns = [description[0] for description in sqlite_cursor.description]
        
        # Préparer l'insertion PostgreSQL
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)
        insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
        
        # Insérer les données
        for row in rows:
            # Convertir la row sqlite en dictionnaire
            row_dict = dict(row)
            values = [row_dict[col] for col in columns]
            
            pg_cursor.execute(insert_query, values)
        
        pg_conn.commit()
        logger.info(f"✅ Table {table_name} migrée avec succès ({len(rows)} lignes)")
        
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"❌ Erreur lors de la migration de {table_name}: {e}")
        raise

def main():
    """Fonction principale de migration"""
    logger.info("=== DÉBUT DE LA MIGRATION SQLITE VERS SUPABASE ===")
    
    try:
        # Connexions
        sqlite_conn = get_sqlite_connection()
        pg_conn = get_supabase_connection()
        
        # Tables à migrer (exclure sqlite_sequence)
        tables_to_migrate = [
            'users',
            'requests', 
            'service_categories',
            'messages',
            'payments',
            'artisans',
            'clients'
        ]
        
        # Migration de chaque table
        for table in tables_to_migrate:
            try:
                migrate_table(sqlite_conn, pg_conn, table)
            except Exception as e:
                logger.error(f"Échec de la migration de {table}: {e}")
                continue
        
        logger.info("=== MIGRATION TERMINÉE AVEC SUCCÈS ===")
        
    except Exception as e:
        logger.error(f"Erreur critique lors de la migration: {e}")
    finally:
        # Fermer les connexions
        if 'sqlite_conn' in locals():
            sqlite_conn.close()
        if 'pg_conn' in locals():
            pg_conn.close()

if __name__ == "__main__":
    main()