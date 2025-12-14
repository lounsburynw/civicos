#!/usr/bin/env python3
"""
Quick test script for Anthropic/Claude provider validation.
"""

import os
import sys

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm_provider import get_provider, list_available_providers

def main():
    print("=" * 60)
    print("Anthropic/Claude Provider Validation")
    print("=" * 60)

    # Check environment variables
    print("\n1. Environment Variables:")
    print(f"   ANTHROPIC_API_KEY: {'✓ Set' if os.getenv('ANTHROPIC_API_KEY') else '✗ Not set'}")
    print(f"   ENABLE_ANTHROPIC: {os.getenv('ENABLE_ANTHROPIC', 'false')}")

    # List available providers
    print("\n2. Available Providers:")
    available = list_available_providers()
    for provider in available:
        marker = "→" if provider == "anthropic" else " "
        print(f"   {marker} {provider}")

    # Try to get Anthropic provider
    print("\n3. Provider Initialization:")
    try:
        provider = get_provider('anthropic')
        print(f"   ✓ Provider: {provider.name}")
        print(f"   ✓ Model: {provider.default_model}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        sys.exit(1)

    # Try a simple completion
    print("\n4. Completion Test:")
    try:
        response = provider.complete([
            {"role": "user", "content": "Say 'Hello from Claude!' and nothing else."}
        ])

        print(f"   ✓ Response: {response.content}")
        print(f"   ✓ Tokens: {response.usage.get('total_tokens', 'N/A')}")
        print(f"   ✓ Finish reason: {response.finish_reason}")

    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ All tests passed! Anthropic provider is working.")
    print("=" * 60)

if __name__ == '__main__':
    main()
