#!/usr/bin/env python3
"""Test Groq Responses API mode detection."""

import sys
import os
sys.path.insert(0, 'src')

from dotenv import load_dotenv
load_dotenv()

from llm_provider import get_provider

provider = get_provider('groq-responses')
print(f"Provider: {provider.name}\n")

# Simulate mode detection query
response = provider.complete(
    messages=[{
        'role': 'user',
        'content': 'Based on the user message "Find housing meetings in Berkeley", determine the best chat mode as: navigation - brief reason'
    }],
    temperature=0.1,
    max_tokens=50
)

print(f"Content: '{response.content}'")
print(f"Length: {len(response.content)}")
print(f"Usage: {response.usage}")

# Check format
if " - " in response.content:
    parts = response.content.split(' - ', 1)
    print(f"\n✓ Valid format!")
    print(f"  Mode: {parts[0]}")
    print(f"  Reason: {parts[1]}")
else:
    print(f"\n✗ Invalid format (missing ' - ')")
