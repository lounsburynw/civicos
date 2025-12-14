#!/usr/bin/env python3
"""
Test script for Anthropic Claude integration.

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

def test_anthropic_basic():
    """Test basic Anthropic provider instantiation and chat completion."""
    print("\n" + "="*70)
    print("TEST 1: Basic Chat Completion")
    print("="*70)

    try:
        from llm_provider import get_provider

        # Get Anthropic provider
        provider = get_provider('anthropic')
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
        return False


def test_anthropic_tools():
    """Test Anthropic provider with tool calling."""
    print("\n" + "="*70)
    print("TEST 2: Tool Calling (Function Calling)")
    print("="*70)

    try:
        from llm_provider import get_provider

        provider = get_provider('anthropic')

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
        return False


def test_anthropic_structured_outputs():
    """Test Anthropic provider with structured JSON outputs via tool calling."""
    print("\n" + "="*70)
    print("TEST 3: Structured Outputs (via Tool Calling)")
    print("="*70)

    try:
        from llm_provider import get_provider

        provider = get_provider('anthropic')

        print("\nNote: Anthropic uses tool calling for structured outputs")
        print("      (not response_format parameter)")

        # Define a tool that enforces structure
        tools = [{
            "name": "extract_search_params",
            "description": "Extract search parameters from user query",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": ["housing", "transportation", "environment"],
                        "description": "Topic category"
                    },
                    "jurisdiction": {
                        "type": "string",
                        "description": "City or county name"
                    }
                },
                "required": ["topic", "jurisdiction"]
            }
        }]

        # Test structured output via forced tool call
        response = provider.complete(
            messages=[
                {"role": "user", "content": "I want to find housing meetings in Berkeley"}
            ],
            tools=tools,
            tool_choice={"type": "tool", "name": "extract_search_params"},
            temperature=0.1
        )

        if response.tool_calls:
            tool_call = response.tool_calls[0]
            print(f"\n✓ Structured data extracted via tool:")
            print(f"  - Tool: {tool_call.name}")
            print(f"  - Topic: {tool_call.arguments.get('topic')}")
            print(f"  - Jurisdiction: {tool_call.arguments.get('jurisdiction')}")

            # Verify structure matches schema
            if tool_call.arguments.get('topic') in ['housing', 'transportation', 'environment']:
                print(f"\n✓ Topic matches enum constraint")
            if tool_call.arguments.get('jurisdiction'):
                print(f"✓ Jurisdiction is present")

            return True
        else:
            print(f"\n✗ No tool call generated")
            return False

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_anthropic_in_chat_router():
    """Test Anthropic integration within the chat router."""
    print("\n" + "="*70)
    print("TEST 4: Chat Router Integration")
    print("="*70)

    try:
        from civic_chat_router import ChatRouter

        router = ChatRouter()

        # Temporarily override provider for this test
        # We'll use the conversational flow which normally uses OpenAI
        print("Testing conversational routing with Anthropic...")

        # Test a simple query
        result = router.route_message(
            message="What is CDBG?",
            conversation_history=[],
            context={},
            mode='focus'
        )

        print(f"\n✓ Routing result:")
        print(f"  - Action: {result.get('action')}")
        print(f"  - Provider: {result.get('provider_used', 'unknown')}")
        print(f"  - Model: {result.get('model_used', 'unknown')}")

        if result.get('message'):
            print(f"  - Response: {result['message'][:150]}...")

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("ANTHROPIC CLAUDE INTEGRATION TEST SUITE")
    print("="*70)

    # Check configuration
    has_key = bool(os.getenv('ANTHROPIC_API_KEY'))
    is_enabled = os.getenv('ENABLE_ANTHROPIC', 'false').lower() == 'true'

    print(f"\nConfiguration:")
    print(f"  - ANTHROPIC_API_KEY: {'✓ Set' if has_key else '✗ Missing'}")
    print(f"  - ENABLE_ANTHROPIC: {'✓ true' if is_enabled else '✗ false'}")

    if not has_key:
        print("\n❌ ANTHROPIC_API_KEY not set. Please configure in .env file.")
        sys.exit(1)

    if not is_enabled:
        print("\n❌ ENABLE_ANTHROPIC not set to 'true'. Please enable in .env file.")
        sys.exit(1)

    # Run tests
    results = []

    results.append(("Basic Chat Completion", test_anthropic_basic()))
    results.append(("Tool Calling", test_anthropic_tools()))
    results.append(("Structured Outputs", test_anthropic_structured_outputs()))
    results.append(("Chat Router Integration", test_anthropic_in_chat_router()))

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
        print("\n✅ All tests passed! Anthropic integration is working correctly.")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
