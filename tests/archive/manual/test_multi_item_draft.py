#!/usr/bin/env python3
"""Test script for multi-item comment drafting"""

import requests
import json

# Test event with 3 agenda items
event_id = "42c562a4-7e0b-48e9-aa7a-08f9c90f6fed"
api_url = f"http://localhost:8001/api/events/{event_id}/draft-comment"

# Test payload with 2 agenda items selected
payload = {
    "userId": "test_user",
    "agendaItemIds": ["1", "2"],  # Select items 1 and 2
    "personalContext": {
        "stakes": ["homeowner"],
        "yearsInArea": 10
    },
    "position": "support"
}

headers = {
    "Authorization": "Bearer dev_key_local",
    "Content-Type": "application/json"
}

print("=" * 80)
print("Testing multi-item comment draft")
print("=" * 80)
print(f"\nEvent ID: {event_id}")
print(f"Selected items: {payload['agendaItemIds']}")
print("\nMaking API request...")
print("=" * 80)

response = requests.post(api_url, json=payload, headers=headers)

print(f"\nStatus Code: {response.status_code}")
print("=" * 80)

if response.status_code == 200:
    result = response.json()
    print("\n✅ SUCCESS!")
    print(f"\nWord Count: {result.get('word_count')}")
    print(f"Speaking Time: {result.get('estimated_speaking_time')}")
    print(f"\nGenerated Draft:\n")
    print(result.get('draft', 'No draft returned'))

    if 'structured_summary' in result:
        print(f"\n\nStructured Summary:")
        print(json.dumps(result['structured_summary'], indent=2))
else:
    print(f"\n❌ ERROR: {response.status_code}")
    print(response.text)
