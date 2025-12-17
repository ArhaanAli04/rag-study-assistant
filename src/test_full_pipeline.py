"""
Test full pipeline: Retrieval → Extraction
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from hybrid_retriever import ConceptMapRetriever
from concept_extractor import ConceptExtractor


def test_full_pipeline():
    """Test complete pipeline from retrieval to concept extraction"""
    print("=" * 70)
    print("  Full Pipeline Test: Retrieval → Extraction")
    print("=" * 70)
    
    # Initialize components
    retriever = ConceptMapRetriever()
    extractor = ConceptExtractor()
    
    # Test topic
    topic = "Transformer Architecture"
    
    print(f"\n📚 Topic: {topic}")
    print("─" * 70)
    
    # Step 1: Retrieve context
    print("\n🔍 Step 1: Retrieving context...")
    retrieval_result = retriever.retrieve_for_concept_map(
        topic=topic,
        user_id="test_user",
        use_documents=False,
        use_web=True,
        max_results=8
    )
    
    print(f"✅ Retrieved {retrieval_result['sources']['total']} results")
    print(f"   Confidence: {retrieval_result['confidence']:.1f}%")
    
    # Step 2: Extract concepts
    print("\n🧠 Step 2: Extracting concepts...")
    concept_map = extractor.extract_concepts_from_hybrid_sources(
        topic=topic,
        retrieval_result=retrieval_result,
        max_concepts=12,
        max_edges=15
    )
    
    # Display results
    if concept_map:
        print("\n" + extractor.format_concept_map_summary(concept_map))
    else:
        print("\n❌ Concept extraction failed")


if __name__ == "__main__":
    try:
        test_full_pipeline()
        
        print("\n" + "=" * 70)
        print("  ✅ Pipeline Test Complete!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
