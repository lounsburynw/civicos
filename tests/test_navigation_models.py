#!/usr/bin/env python3
"""
Test script to compare navigation performance across different models.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from civic_chat_router import get_router
from llm_provider import get_model
import json

def test_model(model_name: str):
    """Test a specific model with two sequential queries."""
    print(f"\n{'=' * 80}")
    print(f"Testing: {model_name}")
    print('=' * 80)

    try:
        # Override the model temporarily
        from llm_provider import TASK_MODEL_CONFIG
        original_priority = TASK_MODEL_CONFIG['navigation']['model_priority']
        TASK_MODEL_CONFIG['navigation']['model_priority'] = [model_name]

        router = get_router()

        # First query
        result1 = router.route_message(
            message="Show me housing meetings in Berkeley",
            conversation_history=[],
            context={},
            mode='navigation'
        )

        params1 = result1.get('parameters', {})
        print(f"\nQuery 1: 'Show me housing meetings in Berkeley'")
        print(f"  → jurisdiction: {params1.get('jurisdiction')}")
        print(f"  → topic: {params1.get('topic')}")

        # Build conversation history
        conversation_history = [
            {"role": "user", "content": "Show me housing meetings in Berkeley"},
            {
                "role": "assistant",
                "content": result1.get('reasoning', ''),
                "function_call": {
                    "name": result1['action'],
                    "arguments": json.dumps(params1)
                }
            }
        ]

        # Second query
        result2 = router.route_message(
            message="Show transportation meetings in the Bay Area",
            conversation_history=conversation_history,
            context={},
            mode='navigation'
        )

        params2 = result2.get('parameters', {})
        print(f"\nQuery 2: 'Show transportation meetings in the Bay Area'")
        print(f"  → jurisdiction: {params2.get('jurisdiction')}")
        print(f"  → topic: {params2.get('topic')}")

        # Check if correct
        expected_jurisdiction = 'all'
        expected_topic = 'transportation'

        if params2.get('jurisdiction') == expected_jurisdiction and params2.get('topic') == expected_topic:
            print(f"\n✅ PASS: Correctly parsed second query")
            return True
        else:
            print(f"\n❌ FAIL: Incorrect parameters")
            print(f"   Expected: jurisdiction='all', topic='transportation'")
            print(f"   Got: jurisdiction='{params2.get('jurisdiction')}', topic='{params2.get('topic')}'")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False
    finally:
        # Restore original priority
        TASK_MODEL_CONFIG['navigation']['model_priority'] = original_priority

if __name__ == '__main__':
    models_to_test = [
        'deepseek/deepseek-chat',
        'gpt-4o-mini',
        'meta-llama/llama-3.3-70b-instruct',
        'gemini-2.0-flash-exp'
    ]

    results = {}
    for model in models_to_test:
        results[model] = test_model(model)

    print(f"\n{'=' * 80}")
    print("Summary")
    print('=' * 80)
    for model, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {model}")
