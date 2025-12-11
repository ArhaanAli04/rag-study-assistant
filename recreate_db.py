import sys
import os

# Remove any cached imports
if 'db' in sys.modules:
    del sys.modules['db']
if 'src.db' in sys.modules:
    del sys.modules['src.db']

# Add src to path
sys.path.insert(0, 'src')

# Delete old database
if os.path.exists('data/app.db'):
    os.remove('data/app.db')
    print("✓ Deleted old database")

# Import fresh modules
from db import Base, engine, Message
import sqlite3

# Create tables
Base.metadata.create_all(bind=engine)
print("✓ Created tables")

# Verify Message class has feedback columns
print(f"✓ Message columns in Python: {[c.name for c in Message.__table__.columns]}")

# Verify database has feedback columns
conn = sqlite3.connect('data/app.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(messages)")
columns = cursor.fetchall()
conn.close()

print(f"✓ Database columns: {[col[1] for col in columns]}")

if any('feedback' in col[1] for col in columns):
    print("✅ SUCCESS! Feedback columns exist in database!")
else:
    print("❌ FAILED! Feedback columns missing!")
