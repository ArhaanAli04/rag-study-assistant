"""
Test script for Concept Map API endpoints
Tests all CRUD operations
"""

import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test10@example.com"
TEST_PASSWORD = "testpass10"

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def print_section(title):
    """Print a section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_success(message):
    """Print success message"""
    print(f"{GREEN}✅ {message}{RESET}")


def print_error(message):
    """Print error message"""
    print(f"{RED}❌ {message}{RESET}")


def print_info(message):
    """Print info message"""
    print(f"{BLUE}ℹ️  {message}{RESET}")


def print_warning(message):
    """Print warning message"""
    print(f"{YELLOW}⚠️  {message}{RESET}")


def login():
    """Login and get access token"""
    print_section("Authentication")
    
    # Try to login
    response = requests.post(
        f"{BASE_URL}/login",
        data={
            "username": TEST_EMAIL,
            "password": TEST_PASSWORD
        }
    )
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        print_success(f"Logged in as {TEST_EMAIL}")
        return token
    else:
        print_error(f"Login failed: {response.status_code}")
        print_info("Make sure the server is running and user exists")
        return None


def test_generate_concept_map(token):
    """Test generating a concept map"""
    print_section("Test 1: Generate Concept Map")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "topic": "Neural Networks",
        "use_documents": False,
        "use_web": True,
        "max_concepts": 12,
        "max_edges": 15
    }
    
    print_info(f"Generating concept map for: '{payload['topic']}'")
    print_info("This may take 10-20 seconds...")
    
    response = requests.post(
        f"{BASE_URL}/api/concepts/generate",
        headers=headers,
        json=payload
    )
    
    if response.status_code == 200:
        data = response.json()
        print_success("Concept map generated successfully!")
        print(f"\n📊 Results:")
        print(f"   Map ID: {data['map_id']}")
        print(f"   Topic: {data['topic']}")
        print(f"   Nodes: {len(data['nodes'])}")
        print(f"   Edges: {len(data['edges'])}")
        print(f"   Sources: {data['sources']['total']} ({data['sources']['web']} web, {data['sources']['documents']} docs)")
        
        # Show first 3 concepts
        print(f"\n🔵 Top 3 Concepts:")
        for i, node in enumerate(data['nodes'][:3], 1):
            print(f"\n{i}. {node['label']}")
            print(f"   {node['definition'][:80]}...")
        
        return data['map_id']
    else:
        print_error(f"Failed to generate: {response.status_code}")
        print(response.text)
        return None


def test_list_concept_maps(token):
    """Test listing concept maps"""
    print_section("Test 2: List Concept Maps")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/api/concepts/maps",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print_success(f"Retrieved {data['total']} concept maps")
        
        if data['maps']:
            print("\n📋 Your Concept Maps:")
            for i, map_item in enumerate(data['maps'], 1):
                print(f"\n{i}. {map_item['topic']} (ID: {map_item['id']})")
                print(f"   Created: {map_item['created_at']}")
                print(f"   Nodes: {map_item['node_count']}, Edges: {map_item['edge_count']}")
                print(f"   Sources: {map_item['sources']['web']} web, {map_item['sources']['documents']} docs")
                print(f"   Confidence: {map_item['confidence']:.1f}%")
        else:
            print_info("No concept maps found")
    else:
        print_error(f"Failed to list: {response.status_code}")


def test_get_concept_map(token, map_id):
    """Test getting a specific concept map"""
    print_section(f"Test 3: Get Concept Map (ID: {map_id})")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/api/concepts/maps/{map_id}",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print_success("Concept map retrieved successfully!")
        print(f"\n📊 Map Details:")
        print(f"   Topic: {data['topic']}")
        print(f"   Nodes: {len(data['nodes'])}")
        print(f"   Edges: {len(data['edges'])}")
        print(f"   Created: {data['created_at']}")
        
        # Show sample edge
        if data['edges']:
            edge = data['edges'][0]
            print(f"\n🔗 Sample Relationship:")
            print(f"   {edge['from']} --[{edge['label']}]--> {edge['to']}")
    else:
        print_error(f"Failed to get map: {response.status_code}")


def test_get_statistics(token):
    """Test getting statistics"""
    print_section("Test 4: Get Statistics")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/api/concepts/statistics",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print_success("Statistics retrieved successfully!")
        print(f"\n📊 Your Statistics:")
        print(f"   Total Maps: {data['total_maps']}")
        print(f"   Total Nodes: {data['total_nodes']}")
        print(f"   Total Edges: {data['total_edges']}")
        print(f"   Total Sources: {data['total_sources']['total']}")
        print(f"   Average Confidence: {data['average_confidence']:.1f}%")
        print(f"\n📚 Source Breakdown:")
        print(f"   Web Only: {data['maps_per_source_type']['web_only']}")
        print(f"   Documents Only: {data['maps_per_source_type']['documents_only']}")
        print(f"   Hybrid: {data['maps_per_source_type']['hybrid']}")
    else:
        print_error(f"Failed to get statistics: {response.status_code}")


def test_delete_concept_map(token, map_id):
    """Test deleting a concept map"""
    print_section(f"Test 5: Delete Concept Map (ID: {map_id})")
    
    # Ask for confirmation
    print_warning(f"This will delete concept map {map_id}")
    confirm = input("Continue? (y/n): ")
    
    if confirm.lower() != 'y':
        print_info("Skipped deletion")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.delete(
        f"{BASE_URL}/api/concepts/maps/{map_id}",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print_success(data['message'])
    else:
        print_error(f"Failed to delete: {response.status_code}")


def main():
    """Run all tests"""
    print("=" * 70)
    print("  Concept Map API Test Suite")
    print("=" * 70)
    
    print_info(f"Testing API at: {BASE_URL}")
    print_info("Make sure the server is running!")
    
    # Step 1: Login
    token = login()
    if not token:
        print_error("Cannot proceed without authentication")
        return
    
    # Step 2: Generate a concept map
    map_id = test_generate_concept_map(token)
    
    # Wait a bit
    time.sleep(1)
    
    # Step 3: List all maps
    test_list_concept_maps(token)
    
    # Step 4: Get specific map (if we created one)
    if map_id:
        time.sleep(1)
        test_get_concept_map(token, map_id)
    
    # Step 5: Get statistics
    time.sleep(1)
    test_get_statistics(token)
    
    # Step 6: Delete map (optional)
    if map_id:
        time.sleep(1)
        test_delete_concept_map(token, map_id)
    
    print("\n" + "=" * 70)
    print("  ✅ All Tests Complete!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
