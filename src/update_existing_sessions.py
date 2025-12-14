import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import SessionLocal, Session

def update_existing_sessions():
    """Set topic='General' for all existing sessions that have NULL topic"""
    db = SessionLocal()
    
    try:
        # Find sessions with NULL topic
        sessions = db.query(Session).filter(
            (Session.topic == None) | (Session.topic == "")
        ).all()
        
        if not sessions:
            print("✅ All sessions already have topics assigned")
            return
        
        print(f"📝 Found {len(sessions)} sessions without topics")
        
        # Update them
        for session in sessions:
            session.topic = "General"
        
        db.commit()
        print(f"✅ Updated {len(sessions)} sessions with default topic 'General'")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Updating existing sessions...\n")
    update_existing_sessions()
