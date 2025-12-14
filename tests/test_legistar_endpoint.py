#!/usr/bin/env python3
"""
Test script to verify Legistar endpoint integration
"""

import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import requests
import json
import os

def test_legistar_endpoint():
    """Test the Legistar API endpoint"""

    # Test configuration
    base_url = "http://localhost:8001"
    api_key = os.getenv('CIVIC_WEB_KEY')

    if not api_key:
        print("❌ CIVIC_WEB_KEY not set")
        return False

    print(f"🔑 Using API key: {api_key[:10]}...")

    # Headers
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    # Test 1: Status endpoint (should work)
    print("\n📊 Testing /api/status...")
    try:
        response = requests.get(f"{base_url}/api/status", headers=headers, timeout=5)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status endpoint works - Version: {data.get('version')}")
        else:
            print(f"❌ Status failed: {response.text[:100]}")
            return False
    except Exception as e:
        print(f"❌ Status endpoint failed: {e}")
        return False

    # Test 2: Oakland Legistar endpoint
    print("\n🏛️  Testing /api/legistar/oakland/events...")
    try:
        response = requests.get(f"{base_url}/api/legistar/oakland/events", headers=headers, timeout=15)
        print(f"Oakland Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Oakland endpoint works!")
            print(f"   City: {data.get('city', 'N/A')}")
            print(f"   Total Events: {data.get('total_events', 0)}")
            print(f"   Data Source: {data.get('data_source', 'N/A')}")

            events = data.get('events', [])
            if events:
                print(f"\n📅 Sample events:")
                for i, opp in enumerate(events[:2]):
                    print(f"   {i+1}. {opp.get('title', 'N/A')[:60]}...")
                    print(f"      Date: {opp.get('date', 'N/A')[:19]}")
                    print(f"      Municipality: {opp.get('municipality', 'N/A')}")
            return True
        else:
            print(f"❌ Oakland failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            return False

    except Exception as e:
        print(f"❌ Oakland endpoint failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 LEGISTAR ENDPOINT INTEGRATION TEST")
    print("=" * 50)

    success = test_legistar_endpoint()

    print("\n" + "=" * 50)
    if success:
        print("✅ ALL TESTS PASSED - Legistar integration working!")
    else:
        print("❌ TESTS FAILED - Check server and configuration")