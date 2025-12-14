import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import engine, init_db, Base, Session
from sqlalchemy import inspect, text

def check_column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def add_topic_column():
    """Add topic column to sessions table if it doesn't exist"""
    
    print("🔍 Checking database schema...")
    
    # Check if topic column exists
    if check_column_exists('sessions', 'topic'):
        print("✅ 'topic' column already exists in 'sessions' table")
        return True
    
    print("⚠️  'topic' column not found. Adding it now...")
    
    try:
        with engine.connect() as conn:
            # Add the topic column with default value
            conn.execute(text(
                "ALTER TABLE sessions ADD COLUMN topic VARCHAR DEFAULT 'General'"
            ))
            conn.commit()
            print("✅ Successfully added 'topic' column to sessions table")
            return True
    except Exception as e:
        print(f"❌ Error adding column: {e}")
        print("\nIf the column already exists, you can ignore this error.")
        return False

def verify_schema():
    """Verify the complete schema"""
    inspector = inspect(engine)
    
    print("\n📋 Current 'sessions' table schema:")
    print("-" * 50)
    for col in inspector.get_columns('sessions'):
        nullable = "NULL" if col['nullable'] else "NOT NULL"
        default = f"DEFAULT {col['default']}" if col.get('default') else ""
        print(f"  • {col['name']:<15} {str(col['type']):<15} {nullable} {default}")
    print("-" * 50)

if __name__ == "__main__":
    print("🚀 Starting database migration...\n")
    
    # Ensure tables exist
    init_db()
    
    # Add topic column
    success = add_topic_column()
    
    # Verify schema
    verify_schema()
    
    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n⚠️  Migration completed with warnings. Check messages above.")
