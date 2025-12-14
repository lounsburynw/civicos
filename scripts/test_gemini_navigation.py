#!/usr/bin/env python3
"""
Test Gemini's navigation mode structured outputs.

Validates that Gemini correctly parses navigation queries into structured operations.
"""

import os
import sys
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from civic_chat_router import ChatRouter

def test_query(router, query):
    """Test a single navigation query"""
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    try:
        result = router.handle_navigation_mode(
            message=query,
            context={'user_city': 'Oakland'},
            conversation_history=[]
        )

        print(f"\nAction: {result.get('action')}")
        print(f"Provider: {result.get('provider_used')}")
        print(f"Model: {result.get('model_used')}")

        if 'parameters' in result:
            print(f"\nParameters:")
            for key, value in result['parameters'].items():
                print(f"  {key}: {value}")

        if 'usage' in result:
            print(f"\nTokens: {result['usage'].get('total_tokens', 0)}")

        # Check for expected behavior
        if query == "Find housing meetings in Berkeley":
            expected_topic = result.get('parameters', {}).get('topic')
            expected_jurisdiction = result.get('parameters', {}).get('jurisdiction')
            search_query = result.get('parameters', {}).get('query')

            print(f"\n{'='*60}")
            print("VALIDATION:")
            print(f"{'='*60}")

            if expected_topic == 'housing':
                print("✓ Topic correctly set to 'housing'")
            else:
                print(f"✗ Topic incorrect: '{expected_topic}' (expected 'housing')")

            if expected_jurisdiction == 'city-berkeley':
                print("✓ Jurisdiction correctly set to 'city-berkeley'")
            else:
                print(f"✗ Jurisdiction incorrect: '{expected_jurisdiction}' (expected 'city-berkeley')")

            if not search_query or search_query is None:
                print("✓ searchQuery correctly empty (not literal text search)")
            else:
                print(f"✗ searchQuery should be empty but got: '{search_query}'")
                print("  This means it's doing a LITERAL text search instead of topic filter!")

        return result

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("=" * 60)
    print("Gemini Navigation Mode Diagnostic")
    print("=" * 60)

    # Check environment
    if not os.getenv('GOOGLE_API_KEY'):
        print("\n✗ GOOGLE_API_KEY not found in .env")
        print("  Get one from: https://aistudio.google.com/app/apikey")
        sys.exit(1)

    print("\n✓ GOOGLE_API_KEY found")

    # Initialize router
    print("\nInitializing ChatRouter...")
    router = ChatRouter()
    print("✓ Router initialized")

    # Test queries
    test_queries = [
        "Find housing meetings in Berkeley",
        "Show me transportation events in Oakland",
        "What meetings are happening about climate change?"
    ]

    for query in test_queries:
        test_query(router, query)

    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)


if __name__ == '__main__':
    main()
