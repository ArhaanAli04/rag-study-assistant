import sqlite3
import os

# Path to your database (adjust if needed)
DB_PATH = "data/app.db"

def add_doc_version_column():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "doc_version" in columns:
        print("❌ doc_version column already exists")
    else:
        cursor.execute("ALTER TABLE users ADD COLUMN doc_version INTEGER DEFAULT 0")
        conn.commit()
        print("✅ Added doc_version column successfully!")
    
    conn.close()

if __name__ == "__main__":
    add_doc_version_column()
