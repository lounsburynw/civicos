#!/usr/bin/env python3
"""
Test script for model picker functionality (Session 88)
Tests that model_override parameter is properly passed and used.
"""

import json
import requests

API_URL = "http://localhost:8001"
API_KEY = "dev_key_local"

def test_auto_mode():
    """Test auto mode (no override)"""
    print("=" * 60)
    print("TEST 1: Auto Mode (no override)")
    print("=" * 60)

    response = requests.post(
        f"{API_URL}/api/chat/route",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "message": "Show me housing meetings in Berkeley",
            "mode": "navigation"
        }
    )

    result = response.json()
    print(f"✓ Status: {response.status_code}")
    print(f"✓ Action: {result.get('action')}")
    print(f"✓ Provider: {result.get('provider_used')}")
    print(f"✓ Model: {result.get('model_used')}")
    print(f"✓ Reasoning: {result.get('reasoning', '')[:100]}...")
    print()

    return result

def test_manual_override():
    """Test manual model override"""
    print("=" * 60)
    print("TEST 2: Manual Override (claude-sonnet-4)")
    print("=" * 60)

    response = requests.post(
        f"{API_URL}/api/chat/route",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "message": "Show me housing meetings in Berkeley",
            "mode": "navigation",
            "model_override": "claude-sonnet-4"
        }
    )

    result = response.json()
    print(f"✓ Status: {response.status_code}")
    print(f"✓ Action: {result.get('action')}")
    print(f"✓ Provider: {result.get('provider_used')}")
    print(f"✓ Model: {result.get('model_used')}")
    print(f"✓ Expected: claude-sonnet-4 (or versioned variant)")
    print(f"✓ Match: {'claude-sonnet-4' in result.get('model_used', '')}")
    print(f"✓ Reasoning: {result.get('reasoning', '')[:100]}...")
    print()

    return result

def test_different_override():
    """Test different model override"""
    print("=" * 60)
    print("TEST 3: Manual Override (gpt-4o)")
    print("=" * 60)

    response = requests.post(
        f"{API_URL}/api/chat/route",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "message": "Show me housing meetings in Berkeley",
            "mode": "navigation",
            "model_override": "gpt-4o"
        }
    )

    result = response.json()
    print(f"✓ Status: {response.status_code}")
    print(f"✓ Action: {result.get('action')}")
    print(f"✓ Provider: {result.get('provider_used')}")
    print(f"✓ Model: {result.get('model_used')}")
    print(f"✓ Expected: gpt-4o")
    print(f"✓ Match: {result.get('model_used') == 'gpt-4o'}")
    print(f"✓ Reasoning: {result.get('reasoning', '')[:100]}...")
    print()

    return result

if __name__ == "__main__":
    print("\nModel Picker Integration Tests (Session 88)")
    print("=" * 60)
    print()

    try:
        result1 = test_auto_mode()
        result2 = test_manual_override()
        result3 = test_different_override()

        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"✓ Auto mode: {result1.get('model_used')}")
        print(f"✓ Claude override: {result2.get('model_used')} (expected: claude-sonnet-4)")
        print(f"✓ GPT-4o override: {result3.get('model_used')} (expected: gpt-4o)")
        print()

        # Verify overrides worked
        claude_match = 'claude-sonnet-4' in result2.get('model_used', '')
        gpt_match = result3.get('model_used') == 'gpt-4o'

        if claude_match and gpt_match:
            print("✅ ALL TESTS PASSED!")
        else:
            print("❌ Some tests failed - model override not working correctly")
            if not claude_match:
                print(f"   Claude: expected 'claude-sonnet-4', got '{result2.get('model_used')}'")
            if not gpt_match:
                print(f"   GPT-4o: expected 'gpt-4o', got '{result3.get('model_used')}'")

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API server")
        print("   Make sure the server is running on http://localhost:8001")
        print("   Run: python src/civic_api_integrated.py")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
