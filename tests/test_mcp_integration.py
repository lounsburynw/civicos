#!/usr/bin/env python3
"""
Test MCP Integration - Verifies the complete conversation pipeline
Tests: Frontend → API → Conversation Service → MCP Tools → Response
"""

import json
import requests
import time
import sys
from pathlib import Path

# API Configuration
API_BASE_URL = "http://localhost:5001"
API_KEY = "test-web-key-2024"

def test_health_check():
    """Test API health and MCP status"""
    print("1. Testing API health check...")
    
    response = requests.get(
        f"{API_BASE_URL}/api/health",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    
    assert response.status_code == 200, f"Health check failed: {response.status_code}"
    data = response.json()
    
    print(f"   ✅ API Status: {data['status']}")
    print(f"   ✅ MCP Enabled: {data['mcp_enabled']}")
    print(f"   ✅ Service: {data['service']}")
    
    return data['mcp_enabled']

def test_mcp_tools_listing():
    """Test MCP tools endpoint"""
    print("\n2. Testing MCP tools listing...")
    
    response = requests.get(
        f"{API_BASE_URL}/api/mcp-tools",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    
    assert response.status_code == 200, f"MCP tools listing failed: {response.status_code}"
    data = response.json()
    
    print(f"   ✅ Found {len(data['tools'])} MCP tools:")
    for tool in data['tools']:
        print(f"      - {tool['name']}: {tool['description']}")
    
    return data['tools']

def test_basic_conversation():
    """Test basic conversation flow"""
    print("\n3. Testing basic conversation...")
    
    response = requests.post(
        f"{API_BASE_URL}/api/conversation",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "message": "Hello, I'm interested in local civic issues",
            "user_id": "test-user-001",
            "email": "test@example.com",
            "city": "San Rafael",
            "state": "California"
        }
    )
    
    assert response.status_code == 200, f"Conversation failed: {response.status_code} - {response.text}"
    data = response.json()
    
    print(f"   ✅ Response received:")
    print(f"      Message: {data['message']['content'][:100]}...")
    print(f"      Actions: {len(data.get('actions', []))} suggested")
    print(f"      Conversation ID: {data['conversation_id']}")
    
    return data['conversation_id']

def test_mcp_comment_drafting(conversation_id):
    """Test MCP comment drafting capability"""
    print("\n4. Testing MCP comment drafting...")
    
    response = requests.post(
        f"{API_BASE_URL}/api/conversation",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "message": "I want to draft a comment supporting the new housing development on Lincoln Avenue",
            "user_id": "test-user-001",
            "conversation_id": conversation_id
        }
    )
    
    assert response.status_code == 200, f"Comment drafting failed: {response.status_code}"
    data = response.json()
    
    message_content = data['message']['content']
    
    # Check if MCP tool was used
    metadata = data['message'].get('metadata', {})
    mcp_tool_used = metadata.get('mcp_tool_used')
    
    print(f"   ✅ Comment draft response received")
    if mcp_tool_used:
        print(f"   ✅ MCP Tool Used: {mcp_tool_used}")
    print(f"      Response preview: {message_content[:150]}...")
    
    return mcp_tool_used == "compose_public_comment"

def test_mcp_guidelines_request(conversation_id):
    """Test MCP guidelines retrieval"""
    print("\n5. Testing MCP guidelines retrieval...")
    
    response = requests.post(
        f"{API_BASE_URL}/api/conversation",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "message": "How do I submit public comments? What are the guidelines?",
            "user_id": "test-user-001",
            "conversation_id": conversation_id
        }
    )
    
    assert response.status_code == 200, f"Guidelines request failed: {response.status_code}"
    data = response.json()
    
    message_content = data['message']['content']
    metadata = data['message'].get('metadata', {})
    mcp_tool_used = metadata.get('mcp_tool_used')
    
    print(f"   ✅ Guidelines response received")
    if mcp_tool_used:
        print(f"   ✅ MCP Tool Used: {mcp_tool_used}")
    
    # Check if guidelines are in response
    has_guidelines = "email submission" in message_content.lower() or "public comment" in message_content.lower()
    print(f"   ✅ Contains guidelines: {has_guidelines}")
    
    return mcp_tool_used == "get_comment_guidelines"

def test_conversation_context_persistence(conversation_id):
    """Test that conversation context persists across messages"""
    print("\n6. Testing conversation context persistence...")
    
    # Send a message with specific topic
    response1 = requests.post(
        f"{API_BASE_URL}/api/conversation",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "message": "I'm concerned about traffic on 4th Street",
            "user_id": "test-user-001",
            "conversation_id": conversation_id
        }
    )
    
    assert response1.status_code == 200
    
    # Get conversation context
    context_response = requests.get(
        f"{API_BASE_URL}/api/conversation-context?conversation_id={conversation_id}",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    
    assert context_response.status_code == 200
    context = context_response.json()
    
    print(f"   ✅ Context persisted:")
    print(f"      Current topic: {context.get('current_topic', 'N/A')}")
    print(f"      Issues mentioned: {context.get('civic_issues_mentioned', [])}")
    print(f"      Message count: {context.get('message_count', 0)}")
    
    return context.get('current_topic') == 'transportation'

def test_user_experience_progression():
    """Test user experience level progression"""
    print("\n7. Testing user experience progression...")
    
    user_id = "test-user-progression"
    
    # Create new user
    response1 = requests.post(
        f"{API_BASE_URL}/api/conversation",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "message": "Hello",
            "user_id": user_id
        }
    )
    
    assert response1.status_code == 200
    data1 = response1.json()
    
    initial_level = data1.get('user_experience', 'new')
    print(f"   ✅ Initial experience level: {initial_level}")
    
    # Send multiple messages to trigger progression
    for i in range(5):
        requests.post(
            f"{API_BASE_URL}/api/conversation",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "message": f"Tell me about civic issue {i}",
                "user_id": user_id,
                "conversation_id": data1['conversation_id']
            }
        )
    
    # Check user profile
    profile_response = requests.get(
        f"{API_BASE_URL}/api/user-profile?user_id={user_id}",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    
    if profile_response.status_code == 200:
        profile = profile_response.json()
        final_level = profile.get('experience_level', 'new')
        interactions = profile.get('civic_profile', {}).get('interactions', 0)
        
        print(f"   ✅ After {interactions} interactions:")
        print(f"      Experience level: {final_level}")
        
        return interactions > 0
    
    return False

def test_error_handling():
    """Test error handling and fallback mechanisms"""
    print("\n8. Testing error handling...")
    
    # Test missing message
    response = requests.post(
        f"{API_BASE_URL}/api/conversation",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={"user_id": "test-user"}
    )
    
    assert response.status_code == 400, "Should return 400 for missing message"
    print("   ✅ Handles missing message correctly")
    
    # Test unauthorized access
    response = requests.post(
        f"{API_BASE_URL}/api/conversation",
        headers={"Content-Type": "application/json"},
        json={"message": "test"}
    )
    
    assert response.status_code == 401, "Should return 401 for missing auth"
    print("   ✅ Handles unauthorized access correctly")
    
    return True

def run_integration_tests():
    """Run all integration tests"""
    print("=" * 60)
    print("MCP INTEGRATION TEST SUITE")
    print("=" * 60)
    
    try:
        # Track test results
        results = {}
        
        # Run tests
        results['health'] = test_health_check()
        results['tools'] = len(test_mcp_tools_listing()) > 0
        
        conversation_id = test_basic_conversation()
        results['conversation'] = bool(conversation_id)
        
        results['comment_drafting'] = test_mcp_comment_drafting(conversation_id)
        results['guidelines'] = test_mcp_guidelines_request(conversation_id)
        results['context'] = test_conversation_context_persistence(conversation_id)
        results['progression'] = test_user_experience_progression()
        results['error_handling'] = test_error_handling()
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(results)
        passed_tests = sum(1 for v in results.values() if v)
        
        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{test_name.ljust(20)}: {status}")
        
        print(f"\nTotal: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("\n🎉 ALL TESTS PASSED! MCP integration is working correctly.")
        else:
            print(f"\n⚠️  {total_tests - passed_tests} tests failed. Check the logs above.")
        
        return passed_tests == total_tests
        
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        return False

if __name__ == "__main__":
    # Check if API server is running
    print("Checking if API server is running...")
    try:
        response = requests.get(f"{API_BASE_URL}/api/health", timeout=2)
        print("✅ API server is running\n")
    except:
        print("❌ API server is not running!")
        print(f"Please start the server first: python src/civic_api_conversation.py")
        sys.exit(1)
    
    # Run tests
    success = run_integration_tests()
    sys.exit(0 if success else 1)