#!/usr/bin/env python3
"""
Test that navigation mode correctly uses the jurisdiction reference list
for cities beyond the hard-coded examples.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from civic_chat_router import ChatRouter

def test_query(router, query, expected_jurisdiction):
    """Test a single navigation query"""
    print(f"\nQuery: {query}")
    print(f"Expected: {expected_jurisdiction}")

    try:
        result = router.handle_navigation_mode(
            message=query,
            context={'user_city': 'Oakland'},
            conversation_history=[]
        )

        actual_jurisdiction = result.get('parameters', {}).get('jurisdiction')

        if actual_jurisdiction == expected_jurisdiction:
            print(f"✓ Correct: {actual_jurisdiction}")
            return True
        else:
            print(f"✗ Wrong: got '{actual_jurisdiction}', expected '{expected_jurisdiction}'")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    print("=" * 70)
    print("Jurisdiction Reference Test")
    print("Testing cities from reference list (not just hard-coded examples)")
    print("=" * 70)

    router = ChatRouter()

    # Test cases: mix of well-known cities and cities from actual reference
    test_cases = [
        # Well-known cities (from examples)
        ("Find housing meetings in Berkeley", "city-berkeley"),
        ("Show transportation events in Oakland", "city-oakland"),

        # Cities from actual reference list (not in examples)
        ("What's happening in Antioch?", "city-antioch"),
        ("Find meetings in Concord", "city-concord"),
        ("Show me Richmond events", "city-richmond"),
        ("Housing meetings in Napa", "city-napa"),
        ("Santa Rosa transportation meetings", "city-santa-rosa"),
        ("What about Pleasant Hill?", "city-pleasant-hill"),

        # Special district
        ("BART meetings", "bart"),
        ("Sonoma County events", "county-sonoma"),
    ]

    passed = 0
    failed = 0

    for query, expected_jurisdiction in test_cases:
        if test_query(router, query, expected_jurisdiction):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    if failed == 0:
        print("\n✓ All tests passed! Jurisdiction reference is working correctly.")
    else:
        print(f"\n✗ {failed} test(s) failed. LLM may not be using the reference list.")

    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
