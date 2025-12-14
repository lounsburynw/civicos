#!/usr/bin/env python3
"""Test Groq Responses API in chat router."""

import sys
import os
sys.path.insert(0, 'src')

from dotenv import load_dotenv
load_dotenv()

from civic_chat_router import ChatRouter

router = ChatRouter()

# Test navigation mode
result = router.route_message(
    message="Find housing meetings in Berkeley",
    conversation_history=[],
    context={},
    mode='navigation'
)

print(f"Action: {result.get('action')}")
print(f"Provider: {result.get('provider_used')}")
print(f"Model: {result.get('model_used')}")
print(f"Mode: {result.get('mode')}")
print(f"Mode changed: {result.get('mode_changed')}")
print(f"Mode reason: {result.get('mode_reason')}")

if result.get('parameters'):
    print(f"Parameters: {result['parameters']}")

if result.get('error'):
    print(f"\n✗ Error: {result['error']}")
else:
    print(f"\n✓ Success!")
