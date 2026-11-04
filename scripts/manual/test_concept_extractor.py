"""
Test script for ConceptExtractor
Tests concept extraction from sample text
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from concept_extractor import ConceptExtractor


def test_basic_extraction():
    """Test basic concept extraction"""
    print("\n" + "=" * 70)
    print("  Test 1: Basic Concept Extraction")
    print("=" * 70)
    
    extractor = ConceptExtractor()
    
    topic = "Machine Learning"
    context = """
    Machine Learning is a branch of artificial intelligence that enables systems to learn from data.
    
    Supervised learning uses labeled data to train models. The model learns to map inputs to outputs
    based on example input-output pairs. Common supervised learning algorithms include linear regression,
    decision trees, and neural networks.
    
    Unsupervised learning works with unlabeled data to find patterns. Clustering is a common unsupervised
    learning technique that groups similar data points together. K-means is a popular clustering algorithm.
    
    Neural networks are computing systems inspired by biological neural networks. They consist of layers
    of interconnected nodes. Deep learning uses neural networks with many layers.
    
    Training a model involves feeding it data and adjusting its parameters to minimize error. The model's
    performance is evaluated using metrics like accuracy, precision, and recall.
    """
    
    concept_map = extractor.extract_concepts_from_context(
        topic=topic,
        context=context,
        max_concepts=10,
        max_edges=12
    )
    
    if concept_map:
        print(extractor.format_concept_map_summary(concept_map))
        
        # Show JSON structure
        print("\n📄 JSON Structure Sample:")
        print("─" * 70)
        import json
        print(json.dumps(concept_map, indent=2)[:800] + "...")
    else:
        print("❌ Extraction failed")


def test_with_empty_context():
    """Test with empty or minimal context"""
    print("\n" + "=" * 70)
    print("  Test 2: Empty Context Handling")
    print("=" * 70)
    
    extractor = ConceptExtractor()
    
    # Test with empty string
    concept_map = extractor.extract_concepts_from_context(
        topic="Test Topic",
        context="",
        max_concepts=5,
        max_edges=5
    )
    
    if concept_map:
        print(f"✅ Handled empty context")
        print(f"   Nodes: {len(concept_map.get('nodes', []))}")
        print(f"   Error message: {concept_map.get('metadata', {}).get('error', 'None')}")
    else:
        print("❌ Failed to handle empty context")


def test_different_topics():
    """Test extraction for various topics"""
    print("\n" + "=" * 70)
    print("  Test 3: Multiple Topics")
    print("=" * 70)
    
    extractor = ConceptExtractor()
    
    test_cases = [
        {
            "topic": "Photosynthesis",
            "context": """
            Photosynthesis is the process by which plants convert light energy into chemical energy.
            Chlorophyll is the green pigment in plants that absorbs light. Plants use carbon dioxide
            from the air and water from soil. Through photosynthesis, plants produce glucose and oxygen.
            The process occurs in chloroplasts within plant cells.
            """
        },
        {
            "topic": "Web Development",
            "context": """
            Web development involves creating websites and web applications. HTML provides the structure
            of web pages. CSS styles the appearance of HTML elements. JavaScript adds interactivity.
            The frontend is what users see, while the backend handles server-side logic and databases.
            """
        }
    ]
    
    for test_case in test_cases:
        print(f"\n{'─' * 70}")
        print(f"📚 Topic: {test_case['topic']}")
        print('─' * 70)
        
        concept_map = extractor.extract_concepts_from_context(
            topic=test_case['topic'],
            context=test_case['context'],
            max_concepts=6,
            max_edges=8
        )
        
        if concept_map:
            metadata = concept_map.get('metadata', {})
            print(f"✅ Extracted {metadata.get('node_count', 0)} nodes, {metadata.get('edge_count', 0)} edges")
            
            # Show concepts
            nodes = concept_map.get('nodes', [])[:3]
            if nodes:
                print(f"\nTop concepts:")
                for node in nodes:
                    print(f"  -  {node.get('label', 'Unknown')}")
        else:
            print("❌ Extraction failed")


if __name__ == "__main__":
    print("=" * 70)
    print("  ConceptExtractor Test Suite")
    print("=" * 70)
    
    # Check API key
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        print(f"✅ GEMINI_API_KEY found: {api_key[:8]}...")
    else:
        print("❌ GEMINI_API_KEY not found")
        print("   Set it in .env file")
        exit(1)
    
    try:
        test_basic_extraction()
        test_with_empty_context()
        test_different_topics()
        
        print("\n" + "=" * 70)
        print("  ✅ All Tests Complete!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
