"""
Test script to verify concept map tables work correctly
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from concept_models import ConceptMap, ConceptMapNode
from datetime import datetime
import json

# Database setup
DATABASE_URL = "sqlite:///data/app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


def test_create_concept_map():
    """Test creating a concept map"""
    
    db = SessionLocal()
    
    try:
        # Sample map data
        map_data = {
            "nodes": [
                {"id": "1", "label": "Machine Learning", "definition": "AI subset"},
                {"id": "2", "label": "Neural Networks", "definition": "Computational model"}
            ],
            "edges": [
                {"from": "1", "to": "2", "label": "uses"}
            ]
        }
        
        sources_data = {
            "documents": ["ML_Course.pdf", "Notes.txt"],
            "web": ["wikipedia.org/ml", "arxiv.org/paper123"]
        }
        
        # Create concept map
        concept_map = ConceptMap(
            user_id="test_user_123",
            topic="Machine Learning Basics",
            map_data=json.dumps(map_data),
            sources=json.dumps(sources_data),
            node_count=2,
            edge_count=1,
            created_at=datetime.utcnow()
        )
        
        db.add(concept_map)
        db.commit()
        db.refresh(concept_map)
        
        print("✅ Created concept map:")
        print(f"   ID: {concept_map.id}")
        print(f"   Topic: {concept_map.topic}")
        print(f"   Nodes: {concept_map.node_count}")
        print(f"   Created: {concept_map.created_at}")
        
        # Retrieve it back
        retrieved = db.query(ConceptMap).filter(ConceptMap.id == concept_map.id).first()
        print(f"\n✅ Retrieved concept map: {retrieved.topic}")
        
        # Parse JSON
        parsed_data = json.loads(retrieved.map_data)
        print(f"   Nodes in data: {len(parsed_data['nodes'])}")
        print(f"   Edges in data: {len(parsed_data['edges'])}")
        
        return concept_map.id
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        return None
    
    finally:
        db.close()


def test_query_user_maps():
    """Test querying maps by user"""
    
    db = SessionLocal()
    
    try:
        maps = db.query(ConceptMap).filter(
            ConceptMap.user_id == "test_user_123"
        ).order_by(ConceptMap.created_at.desc()).all()
        
        print(f"\n✅ Found {len(maps)} maps for user 'test_user_123':")
        for m in maps:
            print(f"   - {m.topic} ({m.node_count} nodes)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        db.close()


def test_delete_concept_map(map_id):
    """Test deleting a concept map"""
    
    db = SessionLocal()
    
    try:
        concept_map = db.query(ConceptMap).filter(ConceptMap.id == map_id).first()
        
        if concept_map:
            db.delete(concept_map)
            db.commit()
            print(f"\n✅ Deleted concept map: {concept_map.topic}")
        else:
            print(f"\n❌ Map with ID {map_id} not found")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  Testing Concept Map Tables")
    print("=" * 60)
    
    # Test 1: Create
    map_id = test_create_concept_map()
    
    # Test 2: Query
    if map_id:
        test_query_user_maps()
        
        # Test 3: Delete
        test_delete_concept_map(map_id)
        
        # Verify deletion
        test_query_user_maps()
    
    print("\n" + "=" * 60)
    print("  Testing Complete!")
    print("=" * 60)
