import sqlite3
import os

db_path = 'src/data/app.db'

if not os.path.exists(db_path):
    print(f"❌ Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check current columns
cursor.execute("PRAGMA table_info(messages)")
columns = [col[1] for col in cursor.fetchall()]
print(f"Current columns: {columns}")

# Add feedback columns if they don't exist
if 'feedback' not in columns:
    print("Adding 'feedback' column...")
    cursor.execute("ALTER TABLE messages ADD COLUMN feedback VARCHAR")
    print("✓ Added 'feedback' column")
else:
    print("✓ 'feedback' column already exists")

if 'feedback_comment' not in columns:
    print("Adding 'feedback_comment' column...")
    cursor.execute("ALTER TABLE messages ADD COLUMN feedback_comment TEXT")
    print("✓ Added 'feedback_comment' column")
else:
    print("✓ 'feedback_comment' column already exists")

conn.commit()

# Verify
cursor.execute("PRAGMA table_info(messages)")
columns_after = [col[1] for col in cursor.fetchall()]
print(f"\n✅ Final columns: {columns_after}")

if 'feedback' in columns_after and 'feedback_comment' in columns_after:
    print("✅ SUCCESS! All columns present!")
else:
    print("❌ FAILED! Columns still missing!")

conn.close()
