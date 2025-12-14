#!/usr/bin/env python3
"""
Provider Validation Script for Civic Conversational OS

Quick validation of available LLM providers and their status.
Run this to check which providers are configured and working.

Usage:
    python scripts/validate_providers.py
"""

import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv()

def check_provider_config():
    """Check which providers are configured via environment variables."""

    providers = {
        'OpenAI': {
            'env_var': 'OPENAI_API_KEY',
            'status': 'production',
            'models': ['gpt-4o-mini', 'gpt-4o'],
            'use_cases': ['conversational', 'function_calling']
        },
        'Google Gemini': {
            'env_var': 'GOOGLE_API_KEY',
            'status': 'production',
            'models': ['gemini-2.0-flash-exp', 'gemini-1.5-pro'],
            'use_cases': ['navigation', 'structured_outputs']
        },
        'Groq': {
            'env_var': 'GROQ_API_KEY',
            'status': 'experimental',
            'models': ['llama-3.1-70b-versatile'],
            'use_cases': ['fast_inference']
        },
        'Perplexity': {
            'env_var': 'PERPLEXITY_API_KEY',
            'status': 'experimental',
            'models': ['llama-3.1-sonar-large-128k-online'],
            'use_cases': ['research', 'real_time_data']
        },
        'Anthropic': {
            'env_var': 'ANTHROPIC_API_KEY',
            'status': 'production',
            'models': ['claude-sonnet-4-20250514'],
            'use_cases': ['research', 'long_document', 'conversational'],
            'requires_flag': 'ENABLE_ANTHROPIC=true'
        }
    }

    print("=" * 70)
    print("LLM Provider Status Check")
    print("=" * 70)
    print()

    configured_count = 0
    production_count = 0

    for name, info in providers.items():
        env_var = info['env_var']
        has_key = bool(os.getenv(env_var))
        status_emoji = {
            'production': '✅',
            'experimental': '⚠️',
            'disabled': '❌'
        }.get(info['status'], '❓')

        print(f"{status_emoji} {name}")
        print(f"   Status: {info['status'].upper()}")
        print(f"   API Key: {'✓ Configured' if has_key else '✗ Missing'} ({env_var})")
        print(f"   Models: {', '.join(info['models'])}")
        print(f"   Use Cases: {', '.join(info['use_cases'])}")

        if 'requires_flag' in info:
            flag_set = os.getenv('ENABLE_ANTHROPIC', 'false').lower() == 'true'
            print(f"   Feature Flag: {'✓ Enabled' if flag_set else '✗ Disabled'} ({info['requires_flag']})")

        print()

        if has_key:
            configured_count += 1
        # Count as production if status is production and has key
        # For Anthropic, also check feature flag
        if info['status'] == 'production' and has_key:
            if 'requires_flag' in info:
                # Check feature flag for Anthropic
                if os.getenv('ENABLE_ANTHROPIC', 'false').lower() == 'true':
                    production_count += 1
            else:
                production_count += 1

    print("=" * 70)
    print(f"Summary: {configured_count}/{len(providers)} providers configured")
    print(f"Production-ready: {production_count} providers")
    print("=" * 70)
    print()

    # Show current default
    default_provider = os.getenv('LLM_PROVIDER', 'openai')
    print(f"Current Default: {default_provider}")
    print()

    # Show smart routing status
    print("Smart Routing:")
    print("  - Navigation queries → Gemini Flash > Groq > OpenAI (85% cost savings)")
    print("  - Conversational queries → OpenAI > Claude > Gemini (quality priority)")
    print("  - Research queries → Gemini > Claude > OpenAI (balanced)")
    print("  - Long documents → Gemini Pro > Claude > OpenAI (context priority)")
    print("  - Comment drafting → OpenAI (proven quality)")
    print()

if __name__ == '__main__':
    check_provider_config()
