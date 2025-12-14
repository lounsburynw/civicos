#!/bin/bash
# Simple test for archetype integration

EVENT_ID="8c43007e-52ab-497e-8ae9-8e15f974b36c"

echo "==============================================="
echo "TEST 1: Comment WITHOUT archetypes (generic)"
echo "==============================================="
echo ""

curl -s -X POST \
  -H "Authorization: Bearer dev_key_local" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "http://localhost:8001/api/events/${EVENT_ID}/draft-comment" | jq -r '.draft // .error'

echo ""
echo ""
echo "==========================================================================="
echo "TEST 2: Comment WITH archetypes (Green New Dealer + Regional + Labor)"
echo "==========================================================================="
echo ""

curl -s -X POST \
  -H "Authorization: Bearer dev_key_local" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "test-user-1",
    "archetypes": [
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
  }' \
  "http://localhost:8001/api/events/${EVENT_ID}/draft-comment" | jq -r '.draft // .error'
