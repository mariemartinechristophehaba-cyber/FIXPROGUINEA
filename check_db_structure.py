import sqlite3

conn = sqlite3.connect('fixpro.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables in database:", tables)

# Get structure and row count for each table
for table in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"\n{table}: {count} rows")
    
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    print("Columns:", [col[1] for col in columns])

conn.close()