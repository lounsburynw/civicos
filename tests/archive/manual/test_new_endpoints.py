#!/usr/bin/env python3
"""
Test script for new Phase 1 endpoints:
- GET /api/jurisdictions
- GET /api/complaints?user_id={user}
"""

import os
import sys
import time
import requests
import json
from pathlib import Path

# Set API key for testing
os.environ['CIVICOS_WEB_KEY'] = 'test-key-12345'
API_KEY = 'test-key-12345'
BASE_URL = 'http://localhost:8001'

def test_jurisdictions_endpoint():
    """Test GET /api/jurisdictions"""
    print("\n" + "="*60)
    print("TEST 1: GET /api/jurisdictions")
    print("="*60)

    url = f"{BASE_URL}/api/jurisdictions"
    headers = {'Authorization': f'Bearer {API_KEY}'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SUCCESS - Retrieved jurisdictions data")
            print(f"\nMetadata:")
            print(f"  - Total Jurisdictions: {data['metadata']['total_jurisdictions']}")
            print(f"  - Total Events: {data['metadata']['total_events']}")
            print(f"  - Total Issues: {data['metadata']['total_issues']}")

            print(f"\nSample Jurisdictions (top 3):")
            for j in data['jurisdictions'][:3]:
                print(f"  - {j['name']} ({j['type']})")
                print(f"    • ID: {j['id']}")
                print(f"    • Events: {j['event_count']}")
                print(f"    • Issues: {j['issue_count']}")
                print(f"    • CDBG: {j['cdbg_allocation'] or 'N/A'}")

            # Validation
            assert data['metadata']['total_jurisdictions'] > 0, "Should have jurisdictions"
            assert len(data['jurisdictions']) > 0, "Should have jurisdiction list"
            assert all('id' in j for j in data['jurisdictions']), "All should have IDs"

            return True
        else:
            print(f"❌ FAILED - Status {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_complaints_endpoint_empty():
    """Test GET /api/complaints?user_id={user} with no complaints"""
    print("\n" + "="*60)
    print("TEST 2: GET /api/complaints?user_id={user} (empty)")
    print("="*60)

    url = f"{BASE_URL}/api/complaints?user_id=test_user_new"
    headers = {'Authorization': f'Bearer {API_KEY}'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SUCCESS - Retrieved complaints (should be empty for new user)")
            print(f"\nMetadata:")
            print(f"  - Total Complaints: {data['metadata']['total_complaints']}")
            print(f"  - Matched Count: {data['metadata']['matched_count']}")
            print(f"  - Open Count: {data['metadata']['open_count']}")

            # Validation
            assert data['metadata']['total_complaints'] == 0, "New user should have 0 complaints"
            assert len(data['complaints']) == 0, "Complaints list should be empty"

            return True
        else:
            print(f"❌ FAILED - Status {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_complaints_endpoint_with_data():
    """Test GET /api/complaints after creating a complaint via conversation"""
    print("\n" + "="*60)
    print("TEST 3: GET /api/complaints?user_id={user} (with data)")
    print("="*60)

    # First, create a complaint via conversation endpoint
    print("\nStep 1: Creating complaint via POST /api/conversation")
    conversation_url = f"{BASE_URL}/api/conversation"
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        "message": "There is a huge pothole on Main Street that needs fixing",
        "user_id": "test_user_with_complaint",
        "city": "Berkeley"
    }

    try:
        conv_response = requests.post(conversation_url, headers=headers, json=payload, timeout=30)
        print(f"Conversation Status: {conv_response.status_code}")

        if conv_response.status_code != 200:
            print(f"❌ Could not create complaint via conversation")
            print(f"Response: {conv_response.text}")
            return False

        conv_data = conv_response.json()
        print(f"✅ Complaint created (type: {conv_data.get('type', 'unknown')})")

        # Now fetch complaints for this user
        print("\nStep 2: Fetching complaints for user")
        complaints_url = f"{BASE_URL}/api/complaints?user_id=test_user_with_complaint"
        complaints_response = requests.get(complaints_url, headers={'Authorization': f'Bearer {API_KEY}'}, timeout=10)

        print(f"Complaints Status: {complaints_response.status_code}")

        if complaints_response.status_code == 200:
            data = complaints_response.json()
            print(f"\n✅ SUCCESS - Retrieved user complaints")
            print(f"\nMetadata:")
            print(f"  - Total Complaints: {data['metadata']['total_complaints']}")
            print(f"  - Matched Count: {data['metadata']['matched_count']}")
            print(f"  - Open Count: {data['metadata']['open_count']}")

            if data['complaints']:
                print(f"\nFirst Complaint:")
                c = data['complaints'][0]
                print(f"  - ID: {c['id']}")
                print(f"  - Description: {c['description'][:50]}...")
                print(f"  - Issue Type: {c['issue_type']}")
                print(f"  - Status: {c['status']}")
                print(f"  - Matched Events: {len(c['matched_events'])}")
                print(f"  - Related Complaints: {len(c['related_complaints'])}")

            # Validation
            assert data['metadata']['total_complaints'] >= 1, "Should have at least 1 complaint"
            assert len(data['complaints']) >= 1, "Should have complaint in list"
            assert all('id' in c for c in data['complaints']), "All should have IDs"
            assert all('matched_events' in c for c in data['complaints']), "All should have matched_events"

            return True
        else:
            print(f"❌ FAILED - Status {complaints_response.status_code}")
            print(f"Response: {complaints_response.text}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n🚀 Testing Phase 1 Backend Endpoints")
    print(f"API Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY}")

    # Wait for API to be ready
    print("\nWaiting for API server to be ready...")
    time.sleep(2)

    results = []

    # Run tests
    results.append(("GET /api/jurisdictions", test_jurisdictions_endpoint()))
    results.append(("GET /api/complaints (empty)", test_complaints_endpoint_empty()))
    results.append(("GET /api/complaints (with data)", test_complaints_endpoint_with_data()))

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} - {test_name}")

    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total_tests - total_passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
