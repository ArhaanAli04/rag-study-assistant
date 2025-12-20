import sqlite3
import os

# Path to your database
DB_PATH = "src/data/app.db"

# Check if database exists
if not os.path.exists(DB_PATH):
    print("❌ Database not found. It will be created on first run.")
    exit(0)

# Connect to database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("🔄 Starting database migration...")

try:
    # Check existing columns
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"✅ Current columns: {columns}")
    
    # Add profile_picture if not exists
    if 'profile_picture' not in columns:
        print("➕ Adding profile_picture column...")
        cursor.execute("ALTER TABLE users ADD COLUMN profile_picture TEXT")
        print("✅ Added profile_picture")
    else:
        print("⏭️  profile_picture already exists")
    
    # Add oauth_provider if not exists
    if 'oauth_provider' not in columns:
        print("➕ Adding oauth_provider column...")
        cursor.execute("ALTER TABLE users ADD COLUMN oauth_provider TEXT")
        print("✅ Added oauth_provider")
    else:
        print("⏭️  oauth_provider already exists")
    
    # Make hashed_password nullable by updating existing users
    # (SQLite doesn't support ALTER COLUMN, but NULL is default)
    print("✅ hashed_password is already nullable by default in SQLite")
    
    # Add username if not exists
    if 'username' not in columns:
        print("➕ Adding username column...")
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
        print("✅ Added username")
    else:
        print("⏭️  username already exists")
    
    # Add name if not exists
    if 'name' not in columns:
        print("➕ Adding name column...")
        cursor.execute("ALTER TABLE users ADD COLUMN name TEXT")
        print("✅ Added name")
    else:
        print("⏭️  name already exists")
    
    # Commit changes
    conn.commit()
    print("\n🎉 Migration completed successfully!")
    
    # Show updated schema
    cursor.execute("PRAGMA table_info(users)")
    columns = cursor.fetchall()
    print("\n📋 Updated User table schema:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]}) {'NOT NULL' if col[3] else 'NULL'}")

except sqlite3.Error as e:
    print(f"❌ Migration failed: {e}")
    conn.rollback()

finally:
    conn.close()
    print("\n✅ Database connection closed")
