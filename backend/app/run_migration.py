"""
Run database migration to add concept map columns
"""

from app.db import init_db

if __name__ == "__main__":
    print("=" * 70)
    print("  Database Migration: Concept Maps")
    print("=" * 70)
    
    print("\n🔄 Running migrations...")
    init_db()
    
    print("\n" + "=" * 70)
    print("  ✅ Migration Complete!")
    print("=" * 70)
    print("\n💡 You can now view the database in DB Browser for SQLite")
    print("   Database location: data/app.db")
