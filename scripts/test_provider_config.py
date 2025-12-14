#!/usr/bin/env python3
"""
Test config-based provider routing.

Validates that the refactored TASK_PROVIDER_CONFIG approach works correctly.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from llm_provider import get_provider_for_task, is_provider_available, TASK_PROVIDER_CONFIG


def main():
    print("=" * 70)
    print("Config-Based Provider Routing Test")
    print("=" * 70)

    # Test 1: Check available providers
    print("\n1. Available Providers:")
    providers_to_check = ['openai', 'google', 'groq', 'groq-responses', 'anthropic', 'perplexity', 'ollama']
    for provider in providers_to_check:
        available = is_provider_available(provider)
        status = "✓ Available" if available else "✗ Not configured"
        print(f"   {provider:<20} {status}")

    # Test 2: Check config structure
    print("\n2. Task Provider Configuration:")
    for task_type, config in TASK_PROVIDER_CONFIG.items():
        priority_str = ' → '.join(config['priority'])
        print(f"   {task_type:<20} {priority_str}")
        print(f"   {'':20} (Reason: {config['reason']})")

    # Test 3: Test provider routing
    print("\n3. Provider Routing Tests:")
    test_tasks = ['navigation', 'explain', 'research', 'draft', 'long_document', 'conversational']

    for task in test_tasks:
        try:
            provider = get_provider_for_task(task)
            print(f"   {task:<20} → {provider.name}/{provider.default_model}")
        except Exception as e:
            print(f"   {task:<20} → ERROR: {e}")

    # Test 4: Model override notation
    print("\n4. Model Override Tests:")
    print("   Testing 'long_document' with google:gemini-1.5-pro-latest notation")
    try:
        provider = get_provider_for_task('long_document')
        expected_model = 'gemini-1.5-pro-latest'
        if provider.name == 'google' and provider.default_model == expected_model:
            print(f"   ✓ Model override working: {provider.default_model}")
        else:
            print(f"   ✗ Model override failed: got {provider.name}/{provider.default_model}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    print("\n" + "=" * 70)
    print("✓ Config-based routing tests complete!")
    print("=" * 70)


if __name__ == '__main__':
    main()
