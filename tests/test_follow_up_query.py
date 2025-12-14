#!/usr/bin/env python
"""Test follow-up query with conversation history (Session 76 bugfix)"""

import requests
import json

API_URL = "http://localhost:8001/api/chat/route"
API_KEY = "dev_key_local"

# Test 1: First query
print("="*70)
print("Test 1: Initial query (no conversation history)")
print("="*70)

response1 = requests.post(
    API_URL,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    },
    json={
        "message": "Show me housing meetings in Berkeley",
        "context": {"user_city": "Berkeley"},
        "mode": "navigation"
    },
    timeout=15
)

result1 = response1.json()
print(f"Query: Show me housing meetings in Berkeley")
print(f"Result: {result1.get('action')}")
print(f"Jurisdiction: {result1.get('parameters', {}).get('jurisdiction')}")
print(f"Topic: {result1.get('parameters', {}).get('topic')}")
print(f"Status: {'✅ SUCCESS' if result1.get('action') == 'search_events' else '❌ FAILED'}")
print()

# Build conversation history for follow-up
conversation_id = result1.get('conversation_id', 'test-conv-123')
conversation_history = [
    {
        "role": "user",
        "content": "Show me housing meetings in Berkeley"
    },
    {
        "role": "assistant",
        "content": "Found 2 events in Berkeley.",
        "function_call": {
            "name": "search_events",
            "arguments": json.dumps({
                "jurisdiction": "city-berkeley",
                "topic": "housing"
            })
        }
    }
]

# Test 2: Follow-up query with conversation history
print("="*70)
print("Test 2: Follow-up query (WITH conversation history)")
print("="*70)
print("This tests the Anthropic provider fix for multiple system messages")
print()

response2 = requests.post(
    API_URL,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    },
    json={
        "message": "Find transportation meetings",
        "context": {"user_city": "Berkeley"},
        "mode": "navigation",
        "conversation_id": conversation_id,
        "conversation_history": conversation_history
    },
    timeout=15
)

result2 = response2.json()
print(f"Query: Find transportation meetings")
print(f"Result: {result2.get('action')}")

if 'error' in result2:
    print(f"❌ ERROR: {result2.get('error')}")
    print(f"Full response: {json.dumps(result2, indent=2)}")
else:
    print(f"Jurisdiction: {result2.get('parameters', {}).get('jurisdiction')}")
    print(f"Topic: {result2.get('parameters', {}).get('topic')}")
    print(f"Status: {'✅ SUCCESS' if result2.get('action') == 'search_events' else '❌ FAILED'}")

print()
print("="*70)
print("FIX VERIFICATION")
print("="*70)
print("Bug: Anthropic provider only kept last system message")
print("Fix: Now concatenates all system messages with \\n\\n separator")
print(f"Test 1 (no history): {'✅ PASS' if result1.get('action') == 'search_events' else '❌ FAIL'}")
print(f"Test 2 (with history): {'✅ PASS' if result2.get('action') == 'search_events' and 'error' not in result2 else '❌ FAIL'}")
