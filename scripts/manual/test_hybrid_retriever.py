"""
Test script for ConceptMapRetriever
Web-search focused for concept map generation
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from hybrid_retriever import ConceptMapRetriever


def test_web_search():
    """Test web search for various topics"""
    print("\n" + "=" * 70)
    print("  Test: Web Search for Concept Maps")
    print("=" * 70)
    
    retriever = ConceptMapRetriever()
    
    # Test multiple topics
    topics = [
        "Transformer Architecture",
        "Neural Networks",
        "Reinforcement Learning"
    ]
    
    for topic in topics:
        print(f"\n{'─' * 70}")
        print(f"📚 Topic: {topic}")
        print('─' * 70)
        
        result = retriever.retrieve_for_concept_map(
            topic=topic,
            user_id="test_user",
            use_documents=False,
            use_web=True,
            max_results=8
        )
        
        print(f"\n📊 Results:")
        print(f"   Total: {result['sources']['total']}")
        print(f"   Web: {result['sources']['web']}")
        print(f"   Confidence: {result['confidence']:.1f}%")
        
        if result['web_results']:
            print(f"\n🌐 Top 3 Web Results:")
            for i, r in enumerate(result['web_results'][:3], 1):
                metadata = r.get('metadata', {})
                title = metadata.get('title', 'Unknown')
                url = metadata.get('url', 'N/A')
                text_preview = r.get('text', '')[:120]
                
                print(f"\n{i}. {title}")
                print(f"   URL: {url}")
                print(f"   Preview: {text_preview}...")


def test_formatted_context():
    """Test formatted context for LLM"""
    print("\n" + "=" * 70)
    print("  Test: Formatted Context for LLM")
    print("=" * 70)
    
    retriever = ConceptMapRetriever()
    
    topic = "Machine Learning Algorithms"
    
    result = retriever.retrieve_for_concept_map(
        topic=topic,
        user_id="test_user",
        use_documents=False,
        use_web=True,
        max_results=6
    )
    
    print(f"\n📄 Formatted Context for: '{topic}'")
    print("=" * 70)
    
    context = retriever.format_context_for_llm(result)
    
    # Show first 1000 characters
    if len(context) > 1000:
        print(context[:1000] + "\n... (truncated)")
    else:
        print(context)
    
    print(f"\n📏 Total context length: {len(context)} characters")


def test_edge_cases():
    """Test edge cases"""
    print("\n" + "=" * 70)
    print("  Test: Edge Cases")
    print("=" * 70)
    
    retriever = ConceptMapRetriever()
    
    # Test 1: Very specific technical term
    print("\n🧪 Test 1: Specific technical term")
    result = retriever.retrieve_for_concept_map(
        topic="BERT Tokenization",
        user_id="test_user"
    )
    print(f"   Results: {result['sources']['total']}")
    
    # Test 2: Broad topic
    print("\n🧪 Test 2: Broad topic")
    result = retriever.retrieve_for_concept_map(
        topic="Artificial Intelligence",
        user_id="test_user"
    )
    print(f"   Results: {result['sources']['total']}")
    
    # Test 3: Misspelled term
    print("\n🧪 Test 3: Potential misspelling")
    result = retriever.retrieve_for_concept_map(
        topic="Convolutional Netowrks",  # Intentional typo
        user_id="test_user"
    )
    print(f"   Results: {result['sources']['total']}")


if __name__ == "__main__":
    print("=" * 70)
    print("  ConceptMapRetriever Test Suite (Web-Only)")
    print("=" * 70)
    print("\n📝 Configuration:")
    print("   • Documents: Disabled (web-only mode)")
    print("   • Web Search: Enabled (Tavily)")
    print("   • Use Case: Concept map generation")
    
    try:
        test_web_search()
        test_formatted_context()
        test_edge_cases()
        
        print("\n" + "=" * 70)
        print("  ✅ All Tests Complete!")
        print("=" * 70)
        print("\n🎯 Next Step: Proceed to Phase 3 (Concept Extraction)")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
