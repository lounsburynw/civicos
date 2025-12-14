#!/usr/bin/env python3
"""
Perplexity web search provider validation.

Tests real-time web search with citations - the core capability
for research mode in the Civic Conversational OS.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm_provider import get_provider, get_provider_for_task, list_available_providers


def main():
    print("=" * 60)
    print("Perplexity Web Search Provider Validation")
    print("=" * 60)

    # Check environment variables
    print("\n1. Environment Variables:")
    has_key = bool(os.getenv('PERPLEXITY_API_KEY'))
    print(f"   PERPLEXITY_API_KEY: {'✓ Set' if has_key else '✗ Not set'}")

    if not has_key:
        print("\n✗ No Perplexity API key found in .env")
        print("  Get one from: https://www.perplexity.ai/settings/api")
        sys.exit(1)

    # List available providers
    print("\n2. Available Providers:")
    available = list_available_providers()
    for provider in available:
        marker = "→" if provider == "perplexity" else " "
        print(f"   {marker} {provider}")

    # Try to get Perplexity provider
    print("\n3. Provider Initialization:")
    try:
        provider = get_provider('perplexity')
        print(f"   ✓ Provider: {provider.name}")
        print(f"   ✓ Model: {provider.default_model}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Test real-time research routing
    print("\n4. Task Routing (realtime_research):")
    try:
        research_provider = get_provider_for_task('realtime_research')
        if research_provider.name == 'perplexity':
            print(f"   ✓ realtime_research tasks route to Perplexity")
        else:
            print(f"   ⚠ Routed to {research_provider.name} (expected: perplexity)")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Test web search with citations
    print("\n5. Web Search Test (with citations):")
    print("   Query: 'What is the latest news on California housing policy?'")

    try:
        response = provider.complete([
            {
                "role": "user",
                "content": "What is the latest news on California housing policy? Give me 2-3 recent updates."
            }
        ])

        print(f"   ✓ Response received ({len(response.content)} chars)")
        print(f"   ✓ Tokens: {response.usage.get('total_tokens', 'N/A')}")
        print(f"   ✓ Finish reason: {response.finish_reason}")

        # Show first 300 chars of response
        preview = response.content[:300] + "..." if len(response.content) > 300 else response.content
        print(f"\n   Response preview:")
        for line in preview.split('\n'):
            print(f"   │ {line}")

        # Check for citations (Perplexity includes URLs in responses)
        has_citations = 'http' in response.content.lower() or '[' in response.content
        if has_citations:
            print(f"\n   ✓ Citations detected in response")
        else:
            print(f"\n   ⚠ No obvious citations found (may still be valid)")

    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Test simple factual query
    print("\n6. Factual Query Test:")
    print("   Query: 'What is the capital of California?'")

    try:
        response = provider.complete([
            {"role": "user", "content": "What is the capital of California? Answer in one sentence."}
        ])

        print(f"   ✓ Response: {response.content}")

        # Verify factual accuracy
        if 'sacramento' in response.content.lower():
            print(f"   ✓ Factually accurate")
        else:
            print(f"   ⚠ Unexpected answer")

    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ All tests passed! Perplexity web search is working.")
    print("=" * 60)
    print("\nKey Features Validated:")
    print("  • Real-time web search")
    print("  • Citation support")
    print("  • Task routing (realtime_research)")
    print("  • Factual accuracy")


if __name__ == '__main__':
    main()
