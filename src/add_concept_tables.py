"""
Migration Script: Add Concept Map Tables
Run this once to add concept_maps table to your database
"""

import sqlite3
import os
from datetime import datetime


# Database path
DATA_DIR = "data"
DB_PATH = f"{DATA_DIR}/app.db"


def add_concept_map_tables():
    """Add concept_maps table to the database"""
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        print("   Please run your FastAPI app first to create the database")
        return
    
    print("🔧 Starting migration: Add concept map tables...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='concept_maps'
        """)
        
        if cursor.fetchone():
            print("ℹ️  Table 'concept_maps' already exists. Skipping creation.")
            conn.close()
            return
        
        # Create concept_maps table
        print("📝 Creating 'concept_maps' table...")
        cursor.execute("""
            CREATE TABLE concept_maps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR NOT NULL,
                topic VARCHAR NOT NULL,
                map_data TEXT NOT NULL,
                sources TEXT,
                node_count INTEGER DEFAULT 0,
                edge_count INTEGER DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME
            )
        """)
        
        # Create index on user_id for faster queries
        print("📝 Creating index on user_id...")
        cursor.execute("""
            CREATE INDEX idx_concept_maps_user_id 
            ON concept_maps(user_id)
        """)
        
        # Create index on created_at for sorting
        print("📝 Creating index on created_at...")
        cursor.execute("""
            CREATE INDEX idx_concept_maps_created_at 
            ON concept_maps(created_at)
        """)
        
        # Optional: Create concept_map_nodes table for advanced querying
        print("📝 Creating 'concept_map_nodes' table (optional)...")
        cursor.execute("""
            CREATE TABLE concept_map_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                map_id INTEGER NOT NULL,
                node_id VARCHAR NOT NULL,
                label VARCHAR NOT NULL,
                definition TEXT,
                source_type VARCHAR,
                sources_json TEXT,
                FOREIGN KEY (map_id) REFERENCES concept_maps(id) ON DELETE CASCADE
            )
        """)
        
        # Create index on map_id
        cursor.execute("""
            CREATE INDEX idx_concept_map_nodes_map_id 
            ON concept_map_nodes(map_id)
        """)
        
        conn.commit()
        print("✅ Migration completed successfully!")
        print("\n📊 Created tables:")
        print("   - concept_maps (main table)")
        print("   - concept_map_nodes (optional, for advanced queries)")
        print("\n🎯 You can now use concept map features in your app!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    
    finally:
        conn.close()


def verify_tables():
    """Verify tables were created correctly"""
    
    print("\n🔍 Verifying table creation...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check concept_maps table structure
        cursor.execute("PRAGMA table_info(concept_maps)")
        columns = cursor.fetchall()
        
        print("\n✅ concept_maps table structure:")
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")
        
        # Check concept_map_nodes table structure
        cursor.execute("PRAGMA table_info(concept_map_nodes)")
        columns = cursor.fetchall()
        
        print("\n✅ concept_map_nodes table structure:")
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")
        
        # Check indexes
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name='concept_maps'
        """)
        indexes = cursor.fetchall()
        
        print("\n✅ Indexes created:")
        for idx in indexes:
            print(f"   - {idx[0]}")
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
    
    finally:
        conn.close()


def rollback_migration():
    """Rollback: Drop concept map tables (use if you need to start over)"""
    
    print("⚠️  Rolling back migration: Dropping concept map tables...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("DROP TABLE IF EXISTS concept_map_nodes")
        cursor.execute("DROP TABLE IF EXISTS concept_maps")
        conn.commit()
        print("✅ Tables dropped successfully")
        
    except Exception as e:
        print(f"❌ Rollback failed: {e}")
        conn.rollback()
    
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  Concept Map Tables Migration")
    print("=" * 60)
    
    # Run migration
    add_concept_map_tables()
    
    # Verify creation
    verify_tables()
    
    print("\n" + "=" * 60)
    print("  Migration Complete!")
    print("=" * 60)
    
    # Uncomment below to rollback (drops tables)
    # print("\n⚠️  To rollback, uncomment the rollback line in the script")
    # rollback_migration()
