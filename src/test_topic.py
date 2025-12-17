"""
Fix concept_maps table schema
Make old columns nullable since we're using new structure
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import sqlite3

DATA_DIR = "data"
db_path = f"{DATA_DIR}/app.db"

def fix_schema():
    """Fix the concept_maps table schema"""
    print("=" * 70)
    print("  Fixing Concept Maps Schema")
    print("=" * 70)
    
    if not os.path.exists(db_path):
        print("❌ Database not found!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("\n🔍 Checking current schema...")
        
        # Get current schema
        cursor.execute("PRAGMA table_info(concept_maps)")
        columns = cursor.fetchall()
        
        print("\n📋 Current columns:")
        for col in columns:
            print(f"   {col[1]} ({col[2]}) - {'NOT NULL' if col[3] else 'NULLABLE'}")
        
        # SQLite doesn't support ALTER COLUMN directly
        # We need to recreate the table
        
        print("\n🔄 Recreating table with correct schema...")
        
        # Step 1: Rename old table
        cursor.execute("ALTER TABLE concept_maps RENAME TO concept_maps_old")
        
        # Step 2: Create new table with correct schema
        cursor.execute("""
            CREATE TABLE concept_maps (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                topic VARCHAR NOT NULL,
                map_data TEXT,
                sources TEXT,
                node_count INTEGER DEFAULT 0,
                edge_count INTEGER DEFAULT 0,
                source_document_count INTEGER DEFAULT 0,
                source_web_count INTEGER DEFAULT 0,
                edges_json TEXT,
                confidence_score REAL DEFAULT 0.0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users (id)
            )
        """)
        
        # Step 3: Copy data from old table (if any exists)
        cursor.execute("""
            INSERT INTO concept_maps 
            SELECT * FROM concept_maps_old
        """)
        
        # Step 4: Drop old table
        cursor.execute("DROP TABLE concept_maps_old")
        
        conn.commit()
        
        print("✅ Schema fixed successfully!")
        
        # Show new schema
        print("\n📋 New schema:")
        cursor.execute("PRAGMA table_info(concept_maps)")
        columns = cursor.fetchall()
        for col in columns:
            nullable = "NULLABLE" if not col[3] else "NOT NULL"
            print(f"   {col[1]} ({col[2]}) - {nullable}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
    
    print("\n" + "=" * 70)
    print("  ✅ Fix Complete!")
    print("=" * 70)

if __name__ == "__main__":
    fix_schema()
