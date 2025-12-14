#!/usr/bin/env python3
"""
Test script to debug navigation issue with DeepSeek Chat.

Reproduces the issue where:
1. "Show me housing meetings in Berkeley" → correct
2. "Show transportations meeting in the Bay Area" → returns same as #1 (WRONG)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# Ensure OPENROUTER_API_KEY is set
if not os.getenv('OPENROUTER_API_KEY'):
    print("❌ OPENROUTER_API_KEY not set. Please set it in .env")
    sys.exit(1)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from civic_chat_router import get_router

def test_navigation_queries():
    """Test two sequential navigation queries to see if second one works."""
    router = get_router()

    print("=" * 80)
    print("Test 1: Housing in Berkeley")
    print("=" * 80)

    # First query
    result1 = router.route_message(
        message="Show me housing meetings in Berkeley",
        conversation_history=[],
        context={},
        mode='navigation'
    )

    print(f"\nAction: {result1['action']}")
    print(f"Parameters: {result1.get('parameters', {})}")
    print(f"Provider: {result1.get('provider_used', 'unknown')}")
    print(f"Model: {result1.get('model_used', 'unknown')}")

    # Build conversation history for second query
    conversation_history = [
        {"role": "user", "content": "Show me housing meetings in Berkeley"},
        {
            "role": "assistant",
            "content": result1.get('reasoning', ''),
            "function_call": {
                "name": result1['action'],
                "arguments": str(result1.get('parameters', {}))
            }
        }
    ]

    print("\n" + "=" * 80)
    print("Test 2: Transportation in Bay Area (with conversation history)")
    print("=" * 80)

    # Second query with history
    result2 = router.route_message(
        message="Show transportations meeting in the Bay Area",
        conversation_history=conversation_history,
        context={},
        mode='navigation'
    )

    print(f"\nAction: {result2['action']}")
    print(f"Parameters: {result2.get('parameters', {})}")
    print(f"Provider: {result2.get('provider_used', 'unknown')}")
    print(f"Model: {result2.get('model_used', 'unknown')}")

    # Check if parameters are different
    params1 = result1.get('parameters', {})
    params2 = result2.get('parameters', {})

    print("\n" + "=" * 80)
    print("Analysis")
    print("=" * 80)

    if params1 == params2:
        print("❌ BUG CONFIRMED: Both queries returned identical parameters!")
        print(f"   Query 1: {params1}")
        print(f"   Query 2: {params2}")
        return False
    else:
        print("✅ Queries returned different parameters (expected behavior)")
        print(f"   Query 1: {params1}")
        print(f"   Query 2: {params2}")
        return True

if __name__ == '__main__':
    success = test_navigation_queries()
    sys.exit(0 if success else 1)
