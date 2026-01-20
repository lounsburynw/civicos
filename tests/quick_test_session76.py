#!/usr/bin/env python
"""
Quick Interactive Test - Pure Function-Calling Architecture (Session 76)

Tests key scenarios to verify the refactor is working correctly.
"""

import requests
import json
import os

API_URL = "http://localhost:8001/api/chat/route"
API_KEY = os.getenv("CIVICOS_WEB_KEY", "dev_key_local")

def test_query(message, mode="navigation", description=""):
    """Test a single query and display results."""
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"{'='*70}")
    print(f"Query: \"{message}\"")
    print(f"Mode: {mode}")

    try:
        response = requests.post(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}"
            },
            json={
                "message": message,
                "context": {"user_city": "Berkeley"},
                "mode": mode
            },
            timeout=15
        )
        response.raise_for_status()
        result = response.json()

        # Display key results
        print(f"\n✅ Response received:")
        print(f"   Action: {result.get('action')}")
        print(f"   Mode: {result.get('mode')} (changed: {result.get('mode_changed', False)})")

        if result.get('parameters'):
            print(f"   Parameters:")
            for key, value in result['parameters'].items():
                print(f"      {key}: {value}")

        if result.get('message'):
            print(f"   Message: {result['message'][:100]}...")

        if result.get('usage'):
            usage = result['usage']
            print(f"   Tokens: {usage.get('total_tokens', 'N/A')} (prompt: {usage.get('prompt_tokens')}, completion: {usage.get('completion_tokens')})")

        # Check for deprecated operations array
        if 'operations' in result:
            print(f"\n⚠️  WARNING: Found deprecated 'operations' array! Pure function-calling should not use this.")

        # Check for function calls
        if result.get('action') not in ['respond']:
            print(f"\n✅ Function call detected (pure function-calling working!)")

        return result

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        return None
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return None

def main():
    print("\n" + "="*70)
    print("PURE FUNCTION-CALLING ARCHITECTURE - QUICK TEST")
    print("Session 76")
    print("="*70)

    # Test 1: Simple navigation query
    test_query(
        "Show me housing meetings in Berkeley",
        mode="navigation",
        description="Simple Navigation Query (search_events)"
    )

    # Test 2: Definition query
    test_query(
        "What is CDBG?",
        mode="focus",
        description="Definition Query (search_web or conversational)"
    )

    # Test 3: Legislative context
    test_query(
        "Show me housing bills",
        mode="navigation",
        description="Legislative Context (view_legislative_context)"
    )

    # Test 4: Complaint filing
    test_query(
        "Report a pothole on Main Street",
        mode="navigation",
        description="Complaint Filing (file_complaint)"
    )

    # Test 5: My complaints
    test_query(
        "Show my complaints",
        mode="navigation",
        description="View My Complaints (view_my_complaints)"
    )

    # Test 6: OR query (tests multiple function calls)
    print("\n" + "="*70)
    print("SPECIAL TEST: OR Query (Multiple Function Calls)")
    print("="*70)
    print("This is the key differentiator of pure function-calling!")
    print("LLM should call search_events() TWICE in a single response.")

    test_query(
        "Find housing in Berkeley OR transportation in Oakland",
        mode="navigation",
        description="OR Query - Tests Multiple Function Calls"
    )

    print("\n" + "="*70)
    print("TESTING COMPLETE")
    print("="*70)
    print("\n✅ All tests completed!")
    print("\nKey Checks:")
    print("  1. No 'operations' array in responses")
    print("  2. All queries return function calls (not structured outputs)")
    print("  3. Mode detection works (but doesn't change routing)")
    print("  4. OR queries trigger multiple function calls")
    print("\nFor full test suite, run:")
    print("  python tests/test_pure_function_calling.py")
    print("\nFor manual testing in UI:")
    print("  Frontend: http://localhost:5173")
    print("  See: TEST_QUERIES_SESSION_76.md for comprehensive query list")

if __name__ == "__main__":
    main()
