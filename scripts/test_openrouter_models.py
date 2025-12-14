#!/usr/bin/env python3
"""
Test specific OpenRouter models interactively.

Tests the new models (Kimi K2, DeepSeek R1, DeepSeek Chat) with real API calls.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_model(model_name, test_prompt="Explain civic engagement in exactly 2 sentences."):
    """Test a specific model with a prompt."""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print(f"{'='*60}\n")

    from llm_provider import get_model

    try:
        # Get provider for this model
        provider = get_model(model_name)
        print(f"Provider: {provider.name}")
        print(f"Model: {provider.default_model}")
        print(f"\nPrompt: {test_prompt}")
        print(f"\nGenerating response...")

        # Make API call
        result = provider.complete(
            messages=[
                {"role": "user", "content": test_prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )

        print(f"\n{'─'*60}")
        print(f"Response:")
        print(f"{'─'*60}")
        print(result.content)
        print(f"{'─'*60}")

        usage = result.usage
        print(f"\nTokens: {usage.get('total_tokens', 'N/A')}")
        print(f"  Input: {usage.get('prompt_tokens', 'N/A')}")
        print(f"  Output: {usage.get('completion_tokens', 'N/A')}")

        # Estimate cost
        from model_registry import get_model_info
        info = get_model_info(model_name)
        total_tokens = usage.get('total_tokens', 0)
        cost = (total_tokens / 1_000_000) * info['cost_per_1m_tokens']
        print(f"\nEstimated cost: ${cost:.6f}")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Interactive model testing."""
    print("""
╔════════════════════════════════════════════════════════════╗
║     OpenRouter Model Testing - Interactive Mode            ║
╚════════════════════════════════════════════════════════════╝
""")

    # Check API key
    if not os.getenv('OPENROUTER_API_KEY'):
        print("❌ OPENROUTER_API_KEY not set!")
        print("\nPlease set it in your .env file or export it:")
        print("  export OPENROUTER_API_KEY='sk-or-...'")
        return 1

    print("✓ OPENROUTER_API_KEY is set\n")

    models = [
        ('moonshotai/kimi-k2-thinking', 'Kimi K2 Thinking ($2.00/1M)'),
        ('deepseek/deepseek-r1', 'DeepSeek R1 ($0.55/1M)'),
        ('deepseek/deepseek-chat', 'DeepSeek Chat ($0.27/1M)'),
        ('google/gemini-2.0-flash-exp:free', 'Gemini Free (FREE)'),
    ]

    while True:
        print("\n=== Select Model to Test ===\n")
        for i, (model, desc) in enumerate(models, 1):
            print(f"  {i}. {desc}")
        print("\n  0. Test all models")
        print("  c. Custom model name")
        print("  q. Quit")

        choice = input("\nSelect (1-4, 0, c, or q): ").strip().lower()

        if choice == 'q':
            print("\nExiting. Happy testing!")
            break

        if choice == '0':
            # Test all models
            prompt = input("\nEnter test prompt (or press Enter for default): ").strip()
            if not prompt:
                prompt = "Explain civic engagement in exactly 2 sentences."

            print(f"\nTesting all models with prompt: {prompt}")
            for model, desc in models:
                test_model(model, prompt)
                input("\nPress Enter to continue to next model...")
            continue

        if choice == 'c':
            # Custom model
            custom_model = input("Enter OpenRouter model name (e.g., anthropic/claude-3.5-sonnet): ").strip()
            if custom_model:
                test_model(custom_model)
            continue

        # Test specific model
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                model, desc = models[idx]

                # Get custom prompt
                prompt = input("\nEnter test prompt (or press Enter for default): ").strip()
                if not prompt:
                    prompt = "Explain civic engagement in exactly 2 sentences."

                test_model(model, prompt)
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Invalid choice. Try again.")


if __name__ == '__main__':
    sys.exit(main() or 0)
