#!/usr/bin/env python3
"""
Inspect the exact messages being sent to models to debug DeepSeek issue.
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from unittest.mock import patch

# Load .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from civic_chat_router import get_router
from llm_provider import get_model

def inspect_model_request(model_name: str):
    """Inspect the exact request being sent to a model."""
    print(f"\n{'=' * 80}")
    print(f"Inspecting: {model_name}")
    print('=' * 80)

    # Override model priority
    from llm_provider import TASK_MODEL_CONFIG
    original_priority = TASK_MODEL_CONFIG['navigation']['model_priority']
    TASK_MODEL_CONFIG['navigation']['model_priority'] = [model_name]

    try:
        router = get_router()

        # First query
        result1 = router.route_message(
            message="Show me housing meetings in Berkeley",
            conversation_history=[],
            context={},
            mode='navigation'
        )

        params1 = result1.get('parameters', {})

        # Build conversation history with function_call
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

        print("\nConversation history being sent:")
        print(json.dumps(conversation_history, indent=2))

        # Patch the provider's complete method to see what messages are sent
        captured_messages = []

        def capture_complete(original_complete):
            def wrapper(messages, **kwargs):
                captured_messages.append({
                    'messages': messages,
                    'tools': kwargs.get('tools'),
                    'model': kwargs.get('model')
                })
                return original_complete(messages, **kwargs)
            return wrapper

        # Get the provider for this model
        from llm_provider import get_model
        provider = get_model(model_name)

        with patch.object(provider, 'complete', side_effect=capture_complete(provider.complete)):
            # Second query
            result2 = router.route_message(
                message="Show transportation meetings in the Bay Area",
                conversation_history=conversation_history,
                context={},
                mode='navigation'
            )

        print("\nMessages sent to API:")
        if captured_messages:
            api_messages = captured_messages[0]['messages']
            for i, msg in enumerate(api_messages):
                print(f"\nMessage {i}:")
                print(f"  role: {msg.get('role')}")
                if 'content' in msg:
                    content_preview = str(msg['content'])[:100]
                    print(f"  content: {content_preview}...")
                if 'function_call' in msg:
                    print(f"  function_call: {msg['function_call']}")
                if 'tool_calls' in msg:
                    print(f"  tool_calls: {msg['tool_calls']}")

        params2 = result2.get('parameters', {})
        print(f"\nResult:")
        print(f"  Query 1 params: {params1}")
        print(f"  Query 2 params: {params2}")

        if params2.get('topic') == 'transportation' and params2.get('jurisdiction') == 'all':
            print("  ✅ CORRECT")
            return True
        else:
            print("  ❌ WRONG - returned same as query 1")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        TASK_MODEL_CONFIG['navigation']['model_priority'] = original_priority


if __name__ == '__main__':
    models = [
        'deepseek/deepseek-chat',
        'gpt-4o-mini'
    ]

    for model in models:
        inspect_model_request(model)
