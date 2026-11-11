"""Temporary compatibility module (Day 13, Checkpoint 2 → deleted in Checkpoint 3).

The models moved to app.db.models and the engine to app.db.session; this re-export keeps every
importer working for one commit. The startup ALTERs below are replaced by Alembic in Checkpoint 4.
"""
import sqlite3

from app.db.base import Base
from app.db.models import ConceptMap, ConceptMapNode, Document, FailedQuery, Message, Session, User
from app.db.session import SessionLocal, engine

__all__ = [
    "Base", "ConceptMap", "ConceptMapNode", "Document", "FailedQuery", "Message", "Session", "User",
    "SessionLocal", "engine", "init_db", "refresh_metadata",
]


def _sqlite_path() -> str | None:
    if engine.dialect.name != "sqlite":
        return None
    return engine.url.database


def migrate_concept_maps():
    """Migrate concept_maps table to add new columns"""
    db_path = _sqlite_path()
    if db_path is None:
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if concept_maps table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='concept_maps'")
        if not cursor.fetchone():
            return  # Table doesn't exist yet

        # Get current columns
        cursor.execute("PRAGMA table_info(concept_maps)")
        columns = [col[1] for col in cursor.fetchall()]

        # Add missing columns
        migrations = {
            'source_document_count': "ALTER TABLE concept_maps ADD COLUMN source_document_count INTEGER DEFAULT 0",
            'source_web_count': "ALTER TABLE concept_maps ADD COLUMN source_web_count INTEGER DEFAULT 0",
            'confidence_score': "ALTER TABLE concept_maps ADD COLUMN confidence_score REAL DEFAULT 0.0",
            'edges_json': "ALTER TABLE concept_maps ADD COLUMN edges_json TEXT"
        }

        for column_name, sql in migrations.items():
            if column_name not in columns:
                print(f"🔧 Adding '{column_name}' column to concept_maps...")
                cursor.execute(sql)
                conn.commit()
                print(f"✅ Added '{column_name}' column")

    except Exception as e:
        print(f"❌ Concept maps migration error: {e}")
        conn.rollback()
    finally:
        conn.close()


def migrate_database():
    """Apply database migrations"""
    db_path = _sqlite_path()
    if db_path is None:
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            return  # Table doesn't exist yet

        # Get current columns
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        # Add missing columns
        if 'name' not in columns:
            print("🔧 Adding 'name' column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN name VARCHAR")
            conn.commit()
            print("✅ Added 'name' column")

        if 'created_at' not in columns:
            print("🔧 Adding 'created_at' column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN created_at DATETIME")
            # Set current timestamp for existing users
            cursor.execute("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
            conn.commit()
            print("✅ Added 'created_at' column")

    except Exception as e:
        print(f"❌ Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

    # ✅ Run concept maps migration
    migrate_concept_maps()

def init_db():
    Base.metadata.create_all(bind=engine)
    # Then apply migrations to existing tables
    migrate_database()

def refresh_metadata():
    """Force SQLAlchemy to reload table metadata from database"""
    Base.metadata.clear()
    Base.metadata.reflect(bind=engine)
