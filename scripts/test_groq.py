#!/usr/bin/env python3
"""
Test script for Groq Llama integration.

Tests basic functionality, tool calling, and structured outputs.
"""

import os
import sys
from dotenv import load_dotenv

# Add src directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'src'))

# Load environment variables
load_dotenv()

def test_groq_basic():
    """Test basic Groq provider instantiation and chat completion."""
    print("\n" + "="*70)
    print("TEST 1: Basic Chat Completion")
    print("="*70)

    try:
        from llm_provider import get_provider

        # Get Groq provider
        provider = get_provider('groq')
        print(f"✓ Provider instantiated: {provider.name}")
        print(f"✓ Default model: {provider.default_model}")

        # Test basic completion
        response = provider.complete(
            messages=[
                {"role": "user", "content": "What is CDBG in one sentence?"}
            ],
            temperature=0.1
        )

        print(f"\n✓ Response received ({response.usage.get('total_tokens', 0)} tokens):")
        print(f"  {response.content[:200]}...")
        print(f"\n✓ Provider metadata:")
        print(f"  - Name: {getattr(response, 'provider_name', provider.name)}")
        print(f"  - Model: {getattr(response, 'model', provider.default_model)}")

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_groq_tools():
    """Test Groq provider with tool calling."""
    print("\n" + "="*70)
    print("TEST 2: Tool Calling (Function Calling)")
    print("="*70)

    try:
        from llm_provider import get_provider

        provider = get_provider('groq')

        # Define a simple tool
        tools = [{
            "name": "search_events",
            "description": "Search for civic meetings",
            "parameters": {
                "type": "object",
                "properties": {
                    "jurisdiction": {"type": "string"},
                    "topic": {"type": "string"}
                }
            }
        }]

        # Test tool calling
        response = provider.complete(
            messages=[
                {"role": "user", "content": "Show me housing meetings in Berkeley"}
            ],
            tools=tools,
            temperature=0.1
        )

        if response.tool_calls:
            tool_call = response.tool_calls[0]
            print(f"\n✓ Tool called: {tool_call.name}")
            print(f"✓ Arguments: {tool_call.arguments}")
        else:
            print(f"\n✗ No tool call generated")
            print(f"  Response: {response.content}")
            return False

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_groq_speed():
    """Test Groq's inference speed (key advantage over OpenAI)."""
    print("\n" + "="*70)
    print("TEST 3: Inference Speed Test")
    print("="*70)

    try:
        import time
        from llm_provider import get_provider

        provider = get_provider('groq')

        print("\nGenerating 200 tokens to measure speed...")

        start = time.time()
        response = provider.complete(
            messages=[
                {"role": "user", "content": "Explain the Community Development Block Grant program in 3 paragraphs."}
            ],
            max_tokens=200,
            temperature=0.7
        )
        elapsed = time.time() - start

        tokens = response.usage.get('completion_tokens', 0)
        tokens_per_sec = tokens / elapsed if elapsed > 0 else 0

        print(f"\n✓ Generated {tokens} tokens in {elapsed:.2f} seconds")
        print(f"✓ Speed: {tokens_per_sec:.1f} tokens/second")

        if tokens_per_sec > 100:
            print(f"✓ Fast inference confirmed! (Groq typically: 200-400 tokens/sec)")
        else:
            print(f"⚠️  Slower than expected (network latency?)")

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_groq_in_chat_router():
    """Test Groq integration within the chat router."""
    print("\n" + "="*70)
    print("TEST 4: Chat Router Integration")
    print("="*70)

    try:
        from civic_chat_router import ChatRouter

        router = ChatRouter()

        print("Testing navigation routing with Groq...")
        print("(Note: Navigation mode auto-selects cheapest provider)")

        # Test a simple navigation query
        result = router.route_message(
            message="Find housing meetings in Berkeley",
            conversation_history=[],
            context={},
            mode='navigation'
        )

        print(f"\n✓ Routing result:")
        print(f"  - Action: {result.get('action')}")
        print(f"  - Provider: {result.get('provider_used', 'unknown')}")
        print(f"  - Model: {result.get('model_used', 'unknown')}")

        if result.get('parameters'):
            print(f"  - Parameters: {result['parameters']}")

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("GROQ LLAMA INTEGRATION TEST SUITE")
    print("="*70)

    # Check configuration
    has_key = bool(os.getenv('GROQ_API_KEY'))

    print(f"\nConfiguration:")
    print(f"  - GROQ_API_KEY: {'✓ Set' if has_key else '✗ Missing'}")

    if not has_key:
        print("\n❌ GROQ_API_KEY not set. Please configure in .env file.")
        print("\n   Get your free API key at: https://console.groq.com")
        print("   Then add to .env:")
        print("   GROQ_API_KEY=gsk_...")
        sys.exit(1)

    # Run tests
    results = []

    results.append(("Basic Chat Completion", test_groq_basic()))
    results.append(("Tool Calling", test_groq_tools()))
    results.append(("Inference Speed", test_groq_speed()))
    results.append(("Chat Router Integration", test_groq_in_chat_router()))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed! Groq integration is working correctly.")
        print("\n💡 Key benefits:")
        print("   - 90% cheaper than OpenAI ($0.05-0.27 per 1M tokens)")
        print("   - 5-10x faster inference (200-400 tokens/sec)")
        print("   - Open-source models (Llama 3.3 70B)")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
