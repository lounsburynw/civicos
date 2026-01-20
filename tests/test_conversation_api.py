#!/usr/bin/env python3
"""
Test suite for Civic Conversation API endpoint
Tests AI integration, fallback responses, security, and civic context
"""

import json
import requests
import os
import sys
from datetime import datetime
from pathlib import Path

# Import config for proper API endpoint
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from config import CivicConfig

# Test configuration - use config system
config = CivicConfig()
API_BASE = config.get_api_endpoint()
API_KEY = os.getenv("CIVICOS_WEB_KEY", "civic_web_key")

def test_conversation_endpoint():
    """Test the conversation API endpoint"""
    print("\n🧪 Testing Civic Conversation API")
    print("=" * 50)
    
    # Test cases
    test_cases = [
        {
            "name": "Basic greeting",
            "payload": {
                "message": "Hello!",
                "city": "San Rafael",
                "state": "California"
            },
            "expected_fields": ["response", "conversation_id", "timestamp"]
        },
        {
            "name": "Civic question",
            "payload": {
                "message": "How can I participate in local government?",
                "city": "San Rafael",
                "state": "California",
                "interests": ["housing", "transportation"]
            },
            "expected_fields": ["response", "conversation_id", "timestamp"]
        },
        {
            "name": "Meeting inquiry",
            "payload": {
                "message": "When is the next planning meeting?",
                "city": "San Rafael",
                "state": "California",
                "county": "Marin County"
            },
            "expected_fields": ["response", "conversation_id", "timestamp"]
        },
        {
            "name": "Context preservation",
            "payload": {
                "message": "Tell me more about that",
                "conversation_id": None,  # Will be filled from previous response
                "city": "San Rafael"
            },
            "expected_fields": ["response", "conversation_id", "timestamp"]
        },
        {
            "name": "Input validation - XSS attempt",
            "payload": {
                "message": "<script>alert('xss')</script>What meetings are coming up?",
                "city": "San Rafael"
            },
            "expected_fields": ["response", "conversation_id", "timestamp"],
            "should_sanitize": True
        },
        {
            "name": "Empty message",
            "payload": {
                "message": "",
                "city": "San Rafael"
            },
            "expected_error": True,
            "expected_status": 400
        },
        {
            "name": "Missing authentication",
            "payload": {
                "message": "Hello"
            },
            "skip_auth": True,
            "expected_error": True,
            "expected_status": 401
        }
    ]
    
    conversation_id = None
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n📝 Test {i}: {test['name']}")
        
        # Build request
        headers = {
            "Content-Type": "application/json"
        }
        
        if not test.get("skip_auth"):
            headers["Authorization"] = f"Bearer {API_KEY}"
        
        # Use conversation_id from previous test if needed
        if test["payload"].get("conversation_id") is None and "conversation_id" in test["payload"]:
            test["payload"]["conversation_id"] = conversation_id
        
        try:
            # Make request
            response = requests.post(
                f"{API_BASE}/api/conversation",
                json=test["payload"],
                headers=headers,
                timeout=15
            )
            
            # Check status code
            if test.get("expected_error"):
                if response.status_code == test.get("expected_status", 400):
                    print(f"   ✅ Got expected error status: {response.status_code}")
                    passed += 1
                else:
                    print(f"   ❌ Expected status {test.get('expected_status', 400)}, got {response.status_code}")
                    failed += 1
                continue
            
            if response.status_code != 200:
                print(f"   ❌ Failed with status {response.status_code}")
                print(f"      Response: {response.text[:200]}")
                failed += 1
                continue
            
            # Parse response
            data = response.json()
            
            # Check required fields
            missing_fields = []
            for field in test["expected_fields"]:
                if field not in data:
                    missing_fields.append(field)
            
            if missing_fields:
                print(f"   ❌ Missing fields: {missing_fields}")
                failed += 1
                continue
            
            # Store conversation_id for context test
            if data.get("conversation_id"):
                conversation_id = data["conversation_id"]
            
            # Validate response content
            if not data.get("response"):
                print(f"   ❌ Empty response content")
                failed += 1
                continue
            
            # Check for XSS in response
            if test.get("should_sanitize") and "<script>" in data["response"]:
                print(f"   ❌ Response contains unsanitized script tags")
                failed += 1
                continue
            
            print(f"   ✅ Success!")
            print(f"      Conversation ID: {data.get('conversation_id', 'N/A')[:8]}...")
            print(f"      Response preview: {data['response'][:100]}...")
            passed += 1
            
        except requests.RequestException as e:
            print(f"   ❌ Request failed: {e}")
            failed += 1
        except json.JSONDecodeError as e:
            print(f"   ❌ Invalid JSON response: {e}")
            failed += 1
        except Exception as e:
            print(f"   ❌ Unexpected error: {e}")
            failed += 1
    
    # Summary
    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{len(test_cases)} tests passed")
    
    if failed == 0:
        print("🎉 All conversation API tests passed!")
        return True
    else:
        print(f"⚠️  {failed} tests failed")
        return False

def test_api_status():
    """Check if conversation API is properly registered"""
    print("\n🔍 Checking API Status")
    
    try:
        response = requests.get(
            f"{API_BASE}/api/status",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if conversation endpoint is listed
            authenticated_endpoints = data.get("endpoints", {}).get("authenticated", [])
            has_conversation = any("conversation" in endpoint.lower() for endpoint in authenticated_endpoints)
            
            if has_conversation:
                print("   ✅ Conversation endpoint registered")
            else:
                print("   ⚠️  Conversation endpoint not found in status")
            
            # Check OpenAI integration status
            integration = data.get("integration_status", {})
            if integration.get("openai_available"):
                print("   ✅ OpenAI integration available")
            else:
                print("   ⚠️  OpenAI not configured (using fallback)")
            
            return True
        else:
            print(f"   ❌ Status check failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Could not check status: {e}")
        return False

def main():
    """Run all conversation API tests"""
    print("🚀 Civic Conversation API Test Suite")
    print(f"   Target: {API_BASE}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check if server is running
    try:
        response = requests.get(f"{API_BASE}/health", timeout=2)
        if response.status_code != 200:
            print("\n❌ API server not responding. Start it with:")
            print("   python src/civic_api_integrated.py")
            sys.exit(1)
    except requests.RequestException:
        print("\n❌ Cannot connect to API server at", API_BASE)
        print("   Start the server with: python src/civic_api_integrated.py")
        sys.exit(1)
    
    # Run tests
    status_ok = test_api_status()
    conversation_ok = test_conversation_endpoint()
    
    # Final summary
    print("\n" + "=" * 50)
    if status_ok and conversation_ok:
        print("✅ All tests passed! Conversation API is ready.")
        sys.exit(0)
    else:
        print("⚠️  Some tests failed. Review the output above.")
        sys.exit(1)

if __name__ == "__main__":
    main()