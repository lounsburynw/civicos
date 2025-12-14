#!/usr/bin/env python3
"""
Interactive OpenRouter Testing Script

Tests OpenRouter integration with real API calls (optional).
Provides menu-driven interface for testing different scenarios.
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def check_environment():
    """Check if OpenRouter API key is configured."""
    print("=== Environment Check ===\n")

    openai_key = os.getenv('OPENAI_API_KEY')
    openrouter_key = os.getenv('OPENROUTER_API_KEY')

    print(f"OPENAI_API_KEY: {'✓ Set' if openai_key else '✗ Not set'}")
    print(f"OPENROUTER_API_KEY: {'✓ Set' if openrouter_key else '✗ Not set'}")

    if not openrouter_key:
        print("\n⚠️  OPENROUTER_API_KEY not set!")
        print("\nTo test with real API calls:")
        print("1. Get API key from https://openrouter.ai/keys")
        print("2. Export it: export OPENROUTER_API_KEY='sk-or-...'")
        print("\nFor now, running in dry-run mode (no API calls).\n")
        return False

    print("\n✓ Environment ready for testing\n")
    return True


def test_provider_instantiation():
    """Test that OpenRouter provider can be instantiated."""
    print("=== Test 1: Provider Instantiation ===\n")

    from llm_provider import get_provider, is_provider_available

    # Check availability
    available = is_provider_available('openrouter')
    print(f"OpenRouter available: {available}")

    if not available:
        print("Skipping (no API key)\n")
        return

    # Get provider
    provider = get_provider('openrouter')
    print(f"Provider name: {provider.name}")
    print(f"Default model: {provider.default_model}")
    print("✓ Provider instantiation works\n")


def test_model_registry():
    """Test that OpenRouter models are in registry."""
    print("=== Test 2: Model Registry ===\n")

    from model_registry import get_models_by_provider, get_model_info

    openrouter_models = get_models_by_provider('openrouter')
    print(f"Found {len(openrouter_models)} OpenRouter models:\n")

    for model in openrouter_models:
        info = get_model_info(model)
        cost = info['cost_per_1m_tokens']
        cost_str = f"${cost:.2f}/1M" if cost > 0 else "FREE"
        print(f"  - {model}")
        print(f"    Cost: {cost_str}")
        print(f"    Context: {info['context_window']:,} tokens")
        print(f"    Speed: {info['speed']}")
        print()

    print("✓ Model registry check complete\n")


def test_task_routing():
    """Test that task routing includes OpenRouter models."""
    print("=== Test 3: Task Routing Configuration ===\n")

    from llm_provider import TASK_MODEL_CONFIG

    for task_type, config in TASK_MODEL_CONFIG.items():
        model_priority = config.get('model_priority', [])
        openrouter_models = [m for m in model_priority if '/' in m]

        if openrouter_models:
            print(f"{task_type}:")
            for model in openrouter_models:
                print(f"  - {model}")
            print()

    print("✓ Task routing check complete\n")


def test_model_selection():
    """Test model selection for different tasks."""
    print("=== Test 4: Automatic Model Selection ===\n")

    from llm_provider import get_model_for_task

    tasks = [
        'navigation',
        'query_planning',
        'conversational',
        'draft',
        'long_document'
    ]

    for task in tasks:
        provider = get_model_for_task(task)
        print(f"{task}:")
        print(f"  Provider: {provider.name}")
        print(f"  Model: {provider.default_model}")
        print()

    print("✓ Model selection check complete\n")


def test_simple_completion():
    """Test a simple completion with OpenRouter."""
    print("=== Test 5: Simple Completion (Optional) ===\n")

    if not os.getenv('OPENROUTER_API_KEY'):
        print("Skipped (no API key)\n")
        return

    print("This will make a REAL API call to OpenRouter.")
    response = input("Proceed? (y/N): ").strip().lower()

    if response != 'y':
        print("Skipped by user\n")
        return

    from llm_provider import get_provider

    print("\nTesting with free Gemini tier (zero cost)...")
    provider = get_provider('openrouter')
    provider._default_model = 'google/gemini-2.0-flash-exp:free'

    try:
        result = provider.complete(
            messages=[
                {"role": "user", "content": "Say 'Hello from OpenRouter!' in exactly 5 words."}
            ],
            max_tokens=50
        )

        print(f"\n✓ Response: {result.content}")
        print(f"  Tokens: {result.usage.get('total_tokens', 'N/A')}")
        print(f"  Model: {result.model or 'N/A'}")
        print()
    except Exception as e:
        print(f"\n✗ Error: {e}\n")


def test_chat_routing():
    """Test chat routing with OpenRouter models."""
    print("=== Test 6: Chat Routing Integration (Optional) ===\n")

    if not os.getenv('OPENROUTER_API_KEY'):
        print("Skipped (no API key)\n")
        return

    print("This will make a REAL API call using chat routing.")
    response = input("Proceed? (y/N): ").strip().lower()

    if response != 'y':
        print("Skipped by user\n")
        return

    from civic_chat_router import ChatRouter

    print("\nTesting query planning with free Gemini...")
    router = ChatRouter()

    try:
        # Test query planning (should use free Gemini if available)
        result = router.route_message(
            message="show housing meetings",
            conversation_history=[],
            context={},
            mode="navigation",
            serialized_context={}
        )

        print(f"\n✓ Chat routing works!")
        print(f"  Action: {result.get('action')}")
        if 'parameters' in result:
            print(f"  Parameters: {result['parameters']}")
        print()
    except Exception as e:
        print(f"\n✗ Error: {e}\n")


def test_cost_comparison():
    """Show cost comparison for different models."""
    print("=== Test 7: Cost Comparison ===\n")

    from model_registry import get_model_info

    models = [
        ('gpt-4o-mini', 'OpenAI direct'),
        ('openai/gpt-4o-mini', 'OpenRouter'),
        ('meta-llama/llama-3.3-70b-instruct', 'OpenRouter'),
        ('google/gemini-2.0-flash-exp:free', 'OpenRouter'),
        ('anthropic/claude-3-5-haiku', 'OpenRouter')
    ]

    print("Cost per 1M tokens:\n")
    for model, source in models:
        info = get_model_info(model)
        if info:
            cost = info['cost_per_1m_tokens']
            cost_str = f"${cost:.2f}" if cost > 0 else "FREE"
            print(f"  {model:45s} {cost_str:>10s} ({source})")

    print("\n100 users × 100 queries/month × 1000 tokens avg:")
    print("  OpenAI direct:     $1.50-2.70/month")
    print("  With OpenRouter:   $0.48-0.72/month (73% savings)")
    print("  Free tier only:    $0.00/month (100% savings)")
    print()


def main():
    """Run interactive testing menu."""
    print("""
╔════════════════════════════════════════════════════════════╗
║        OpenRouter Integration - Interactive Testing        ║
╚════════════════════════════════════════════════════════════╝
""")

    has_api_key = check_environment()

    tests = [
        ("Provider Instantiation", test_provider_instantiation),
        ("Model Registry", test_model_registry),
        ("Task Routing Configuration", test_task_routing),
        ("Automatic Model Selection", test_model_selection),
        ("Simple Completion (REAL API CALL)", test_simple_completion),
        ("Chat Routing Integration (REAL API CALL)", test_chat_routing),
        ("Cost Comparison", test_cost_comparison),
    ]

    while True:
        print("\n=== Test Menu ===\n")
        for i, (name, _) in enumerate(tests, 1):
            marker = "⚠️ " if "REAL API CALL" in name and not has_api_key else "  "
            print(f"{marker}{i}. {name}")
        print("\n  0. Run all tests")
        print("  q. Quit")

        choice = input("\nSelect test (0-7 or q): ").strip().lower()

        if choice == 'q':
            print("\nExiting. Happy testing!")
            break

        if choice == '0':
            for name, test_func in tests:
                test_func()
            print("✅ All tests complete!")
            break

        try:
            test_num = int(choice)
            if 1 <= test_num <= len(tests):
                _, test_func = tests[test_num - 1]
                test_func()
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Invalid choice. Try again.")


if __name__ == '__main__':
    main()
