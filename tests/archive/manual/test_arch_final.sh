#!/bin/bash
EVENT_ID="d56bb7e6-bb4f-4e08-9b8f-c113437f4add"

echo "==============================================="
echo "TEST 1: Comment WITHOUT archetypes (generic)"
echo "==============================================="
echo ""

RESULT1=$(curl -s -X POST \
  -H "Authorization: Bearer dev_key_local" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "http://localhost:8001/api/events/${EVENT_ID}/draft-comment")

echo "$RESULT1" | jq -r '.draft'

echo ""
echo ""
echo "==========================================================================="
echo "TEST 2: Comment WITH archetypes (Green New Dealer + Regional + Labor)"
echo "==========================================================================="
echo ""

RESULT2=$(curl -s -X POST \
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
  "http://localhost:8001/api/events/${EVENT_ID}/draft-comment")

echo "$RESULT2" | jq -r '.draft'

echo ""
echo "==============================================="
echo "VERIFICATION"
echo "==============================================="

# Count keyword occurrences
PERSONALIZED=$(echo "$RESULT2" | jq -r '.draft' | tr 'A-Z' 'a-z')

CLIMATE_COUNT=$(echo "$PERSONALIZED" | grep -oE "(climate|green|sustainable|environmental)" | wc -l | tr -d ' ')
REGIONAL_COUNT=$(echo "$PERSONALIZED" | grep -oE "(regional|metropolitan|coordin)" | wc -l | tr -d ' ')
LABOR_COUNT=$(echo "$PERSONALIZED" | grep -oE "(worker|labor|delivery|riders|employment)" | wc -l | tr -d ' ')

echo "Climate/Green keywords: $CLIMATE_COUNT mentions"
echo "Regional keywords: $REGIONAL_COUNT mentions"
echo "Labor/Worker keywords: $LABOR_COUNT mentions"

if [ "$CLIMATE_COUNT" -gt 0 ] || [ "$REGIONAL_COUNT" -gt 0 ] || [ "$LABOR_COUNT" -gt 0 ]; then
  echo ""
  echo "✅ SUCCESS: Personalized comment reflects user archetypes!"
else
  echo ""
  echo "⚠️  WARNING: Personalized comment may not reflect archetypes"
fi
