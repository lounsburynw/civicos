"""
Test Pure Function-Calling Architecture (Session 76)

Tests the refactored chat routing that uses function calling for all modes.

Run:
    python tests/test_pure_function_calling.py

Prerequisites:
    - Backend API server running on http://localhost:8001
    - OPENAI_API_KEY configured in environment
"""

import requests
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

API_URL = "http://localhost:8001/api/chat/route"
API_KEY = os.getenv("CIVIC_WEB_KEY", "dev_key_local")

def route_message(message: str, conversation_id: str = None, mode: str = "navigation") -> dict:
    """Send a message to the chat routing endpoint."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "message": message,
        "conversation_id": conversation_id,
        "context": {"user_city": "Berkeley"},
        "mode": mode
    }

    response = requests.post(API_URL, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def test_simple_search():
    """Test 1: Simple search query - 'show housing meetings'"""
    print("\n" + "="*60)
    print("Test 1: Simple search query")
    print("="*60)

    result = route_message("show housing meetings in Berkeley")

    assert result['action'] == 'search_events', f"Expected search_events, got {result['action']}"
    assert result['parameters']['topic'] == 'housing', "Expected housing topic"
    assert 'berkeley' in result['parameters']['jurisdiction'].lower(), "Expected Berkeley jurisdiction"
    assert result['mode'] == 'navigation', "Expected navigation mode"

    print("✅ PASS: Simple search works")
    print(f"   Action: {result['action']}")
    print(f"   Parameters: {json.dumps(result['parameters'], indent=2)}")
    print(f"   Mode: {result['mode']}")
    print(f"   Tokens: {result.get('usage', {}).get('total_tokens', 'N/A')}")

def test_definition_query():
    """Test 2: Definition query - 'what is CDBG?'"""
    print("\n" + "="*60)
    print("Test 2: Definition query (search_web)")
    print("="*60)

    result = route_message("what is CDBG?", mode="focus")

    # Should either use search_web or provide conversational answer
    assert result['action'] in ['search_web', 'respond'], f"Expected search_web or respond, got {result['action']}"
    assert result['mode'] == 'focus', "Expected focus mode"

    print("✅ PASS: Definition query works")
    print(f"   Action: {result['action']}")
    if result['action'] == 'search_web':
        print(f"   Query: {result['parameters']['query']}")
    print(f"   Mode: {result['mode']}")

def test_navigation_query():
    """Test 3: Navigation query - opens event artifact"""
    print("\n" + "="*60)
    print("Test 3: Navigation query")
    print("="*60)

    result = route_message("show transportation meetings")

    assert result['action'] == 'search_events', f"Expected search_events, got {result['action']}"
    assert result['parameters']['topic'] == 'transportation', "Expected transportation topic"

    print("✅ PASS: Navigation query works")
    print(f"   Action: {result['action']}")
    print(f"   Topic: {result['parameters']['topic']}")

def test_complaint_filing():
    """Test 4: Complaint filing - 'report a pothole'"""
    print("\n" + "="*60)
    print("Test 4: Complaint filing")
    print("="*60)

    result = route_message("report a pothole on Main Street")

    assert result['action'] == 'file_complaint', f"Expected file_complaint, got {result['action']}"

    print("✅ PASS: Complaint filing works")
    print(f"   Action: {result['action']}")
    print(f"   Parameters: {json.dumps(result.get('parameters', {}), indent=2)}")

def test_follow_up_context():
    """Test 5: Follow-up query with context preservation"""
    print("\n" + "="*60)
    print("Test 5: Follow-up query with context")
    print("="*60)

    # First query
    result1 = route_message("find housing meetings in Berkeley")
    conversation_id = result1.get('conversation_id')

    # Follow-up changing location
    result2 = route_message("what about Oakland?", conversation_id=conversation_id)

    assert result2['action'] == 'search_events', "Expected search_events"
    assert 'oakland' in result2['parameters']['jurisdiction'].lower(), "Expected Oakland jurisdiction"
    # Should preserve housing topic from first query
    assert result2['parameters']['topic'] == 'housing', "Expected housing topic preserved"

    print("✅ PASS: Follow-up context works")
    print(f"   First query: Berkeley housing")
    print(f"   Second query: {result2['parameters']['jurisdiction']} {result2['parameters']['topic']}")
    print(f"   Context preserved: ✓")

def test_mode_detection():
    """Test 6: Mode detection works correctly"""
    print("\n" + "="*60)
    print("Test 6: Mode detection")
    print("="*60)

    # Navigation mode query
    nav_result = route_message("find meetings", mode="focus")  # Start in focus
    assert nav_result['mode'] == 'navigation', "Should detect navigation mode"
    assert nav_result['mode_changed'] == True, "Should indicate mode changed"

    # Focus mode query
    focus_result = route_message("what does this mean?", mode="navigation")  # Start in navigation
    assert focus_result['mode'] == 'focus', "Should detect focus mode"
    assert focus_result['mode_changed'] == True, "Should indicate mode changed"

    print("✅ PASS: Mode detection works")
    print(f"   Navigation mode: correctly detected")
    print(f"   Focus mode: correctly detected")

def test_all_modes_use_function_calling():
    """Test 7: All modes use function calling (no structured outputs)"""
    print("\n" + "="*60)
    print("Test 7: All modes use function calling")
    print("="*60)

    modes = ['navigation', 'focus', 'compare']

    for mode in modes:
        result = route_message("show housing meetings", mode=mode)

        # All should return function calls, not operations array
        assert 'action' in result, f"Missing 'action' in {mode} mode"
        assert 'operations' not in result, f"Found deprecated 'operations' in {mode} mode"
        assert result['action'] == 'search_events', f"Expected search_events in {mode} mode"

        print(f"   ✓ {mode.capitalize()} mode uses function calling")

    print("✅ PASS: All modes use function calling")

def run_all_tests():
    """Run all test cases."""
    print("\n" + "="*60)
    print("PURE FUNCTION-CALLING ARCHITECTURE - TEST SUITE")
    print("Session 76")
    print("="*60)

    tests = [
        ("Simple Search", test_simple_search),
        ("Definition Query", test_definition_query),
        ("Navigation Query", test_navigation_query),
        ("Complaint Filing", test_complaint_filing),
        ("Follow-up Context", test_follow_up_context),
        ("Mode Detection", test_mode_detection),
        ("All Modes Use Function Calling", test_all_modes_use_function_calling),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ FAIL: {name}")
            print(f"   Error: {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    print(f"✅ Passed: {passed}/{len(tests)}")
    print(f"❌ Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n🎉 All tests passed! Pure function-calling architecture is working.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check errors above.")
        return 1

if __name__ == "__main__":
    try:
        exit_code = run_all_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
