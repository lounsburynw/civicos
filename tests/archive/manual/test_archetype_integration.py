#!/usr/bin/env python3
"""
Test archetype integration in comment drafting endpoint.

Session 41: Verify that archetypes are properly passed from frontend
and used to personalize AI-generated comments.
"""

import requests
import json

# Test data
event_id = "oakland-2024-08-06-city-council"  # E-bike event from Session 40
archetypes = [
    {
        "id": "green_new_dealer",
        "name": "Green New Dealer",
        "score": 0.525,
        "description": "Climate action through government jobs programs and public investment"
    },
    {
        "id": "regional_thinker",
        "name": "Regional Thinker",
        "score": 0.515,
        "description": "Regional coordination, metropolitan perspective, systems thinking"
    },
    {
        "id": "labor_organizer",
        "name": "Labor Organizer",
        "score": 0.510,
        "description": "Worker rights, living wages, unions, labor standards"
    }
]

# Test 1: Generic comment (no archetypes)
print("=" * 80)
print("TEST 1: Generic comment (no archetypes)")
print("=" * 80)

response_generic = requests.post(
    "http://localhost:8001/api/events/oakland-2024-08-06-city-council/draft-comment",
    headers={
        "Authorization": "Bearer dev_key_local",
        "Content-Type": "application/json"
    },
    json={
        "agendaItemId": "6.3"  # E-bike agenda item
    }
)

if response_generic.status_code == 200:
    result = response_generic.json()
    print(f"\n✅ Generic comment generated ({result['word_count']} words):\n")
    print(result['draft'])
else:
    print(f"❌ Error: {response_generic.status_code} - {response_generic.text}")

print("\n")

# Test 2: Personalized comment (with archetypes)
print("=" * 80)
print("TEST 2: Personalized comment (Green New Dealer + Regional Thinker + Labor Organizer)")
print("=" * 80)

response_personalized = requests.post(
    "http://localhost:8001/api/events/oakland-2024-08-06-city-council/draft-comment",
    headers={
        "Authorization": "Bearer dev_key_local",
        "Content-Type": "application/json"
    },
    json={
        "userId": "test-user-1",
        "archetypes": archetypes,
        "agendaItemId": "6.3"  # E-bike agenda item
    }
)

if response_personalized.status_code == 200:
    result = response_personalized.json()
    print(f"\n✅ Personalized comment generated ({result['word_count']} words):\n")
    print(result['draft'])
else:
    print(f"❌ Error: {response_personalized.status_code} - {response_personalized.text}")

print("\n")

# Verify differences
print("=" * 80)
print("VERIFICATION")
print("=" * 80)

if response_generic.status_code == 200 and response_personalized.status_code == 200:
    generic_text = response_generic.json()['draft'].lower()
    personalized_text = response_personalized.json()['draft'].lower()

    # Check for climate/green framing
    climate_keywords = ['climate', 'green', 'sustainable', 'environmental', 'emissions', 'carbon']
    climate_mentions = sum(1 for keyword in climate_keywords if keyword in personalized_text)

    # Check for regional coordination
    regional_keywords = ['regional', 'metropolitan', 'coordin', 'systems']
    regional_mentions = sum(1 for keyword in regional_keywords if keyword in personalized_text)

    # Check for labor/worker framing
    labor_keywords = ['worker', 'labor', 'delivery', 'riders', 'gig', 'employment']
    labor_mentions = sum(1 for keyword in labor_keywords if keyword in personalized_text)

    print(f"\n📊 Archetype alignment check:")
    print(f"   Climate/Green keywords: {climate_mentions} mentions")
    print(f"   Regional coordination keywords: {regional_mentions} mentions")
    print(f"   Labor/worker keywords: {labor_mentions} mentions")

    if climate_mentions > 0 or regional_mentions > 0 or labor_mentions > 0:
        print("\n✅ SUCCESS: Personalized comment reflects user archetypes!")
    else:
        print("\n⚠️  WARNING: Personalized comment may not reflect archetypes")
