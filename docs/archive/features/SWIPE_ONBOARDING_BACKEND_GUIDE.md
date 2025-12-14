# Swipe Onboarding Backend Implementation Guide (Phase 2.5)

## Overview

Backend endpoints to support Tinder-style swipe onboarding for fast-tracking personalization cold start.

**Frontend Complete**: Components ready and waiting for these 3 endpoints.

---

## Endpoint 1: GET /api/onboarding/cards

**Purpose**: Generate personalized card deck for swipe onboarding

### Request
```bash
GET /api/onboarding/cards
Authorization: Bearer dev_key_local
```

### Response Format
```json
{
  "cards": [
    {
      "id": "topic_housing",
      "type": "topic",
      "title": "Affordable Housing",
      "description": "Rental affordability, development regulations, inclusionary zoning",
      "icon": "🏠",
      "iconColor": "#268bd2",
      "metadata": {
        "topic_id": "housing"
      }
    },
    {
      "id": "event_abc123",
      "type": "event",
      "title": "Planning Commission: New Development at 123 Main St",
      "description": "Berkeley Planning Commission - Wednesday, Nov 1, 7:00 PM",
      "icon": "📅",
      "iconColor": "#859900",
      "metadata": {
        "event_id": "abc123",
        "jurisdiction_id": "berkeley"
      }
    },
    {
      "id": "issue_def456",
      "type": "issue",
      "title": "Pothole on Elm Street",
      "description": "Report from your neighborhood - filed 2 days ago",
      "icon": "⚠️",
      "iconColor": "#dc322f",
      "metadata": {
        "issue_id": "def456",
        "topic": "transportation"
      }
    },
    {
      "id": "jurisdiction_oakland",
      "type": "jurisdiction",
      "title": "Oakland City Council",
      "description": "15 upcoming meetings on housing, transit, and budget",
      "icon": "🏛️",
      "iconColor": "#2aa198",
      "metadata": {
        "jurisdiction_id": "oakland"
      }
    }
  ]
}
```

### Card Generation Logic

**Recommended deck composition (20 cards)**:
- 8 topic cards (housing, transportation, environment, budget, etc.)
- 6 event cards (upcoming meetings from user's area)
- 3 issue cards (recent issues from user's jurisdiction)
- 3 jurisdiction cards (nearby cities with active meetings)

**Personalization**:
- Use user's location (from `user_profiles.jurisdiction_id`) to filter events
- Show recent issues from same jurisdiction
- Include nearby jurisdictions (expand civic awareness)

**Implementation** (in `src/civic_api_integrated.py`):
```python
@app.route('/api/onboarding/cards', methods=['GET'])
def get_onboarding_cards():
    user_id = get_user_id_from_auth()  # From Bearer token

    # Get user's jurisdiction (if profile exists)
    profile = personalization_service.get_profile(user_id)
    jurisdiction_id = profile.get('jurisdiction_id') if profile else None

    cards = []

    # 1. Topic cards (8 cards)
    topics = ['housing', 'transportation', 'environment', 'budget',
              'education', 'public_safety', 'development', 'community']
    for topic in topics:
        cards.append({
            'id': f'topic_{topic}',
            'type': 'topic',
            'title': format_topic_title(topic),
            'description': get_topic_description(topic),
            'icon': get_topic_icon(topic),
            'iconColor': '#268bd2',
            'metadata': {'topic_id': topic}
        })

    # 2. Event cards (6 cards) - from user's area
    if jurisdiction_id:
        upcoming_events = get_upcoming_events(jurisdiction_id, limit=6)
        for event in upcoming_events:
            cards.append({
                'id': f'event_{event["id"]}',
                'type': 'event',
                'title': event['title'],
                'description': f"{event['jurisdiction_name']} - {event['date']}",
                'icon': '📅',
                'iconColor': '#859900',
                'metadata': {
                    'event_id': event['id'],
                    'jurisdiction_id': event['jurisdiction_id'],
                    'topic': event.get('project_type')
                }
            })

    # 3. Issue cards (3 cards) - recent from jurisdiction
    if jurisdiction_id:
        recent_issues = get_recent_issues(jurisdiction_id, limit=3)
        for issue in recent_issues:
            cards.append({
                'id': f'issue_{issue["id"]}',
                'type': 'issue',
                'title': issue['ai_title'] or issue['description'][:50],
                'description': f"Filed {issue['days_ago']} days ago",
                'icon': '⚠️',
                'iconColor': '#dc322f',
                'metadata': {
                    'issue_id': issue['id'],
                    'topic': issue.get('issue_type')
                }
            })

    # 4. Jurisdiction cards (3 cards) - nearby cities
    nearby_jurisdictions = get_nearby_jurisdictions(jurisdiction_id, limit=3)
    for jurisdiction in nearby_jurisdictions:
        cards.append({
            'id': f'jurisdiction_{jurisdiction["id"]}',
            'type': 'jurisdiction',
            'title': jurisdiction['name'],
            'description': f"{jurisdiction['event_count']} upcoming meetings",
            'icon': '🏛️',
            'iconColor': '#2aa198',
            'metadata': {'jurisdiction_id': jurisdiction['id']}
        })

    # Shuffle cards for variety (keep first topic card at top)
    import random
    first_card = cards[0]
    random.shuffle(cards[1:])
    cards = [first_card] + cards[1:20]  # Limit to 20 cards

    return jsonify({'cards': cards})
```

---

## Endpoint 2: POST /api/onboarding/swipe

**Purpose**: Record user's swipe action as synthetic behavioral data

### Request
```bash
POST /api/onboarding/swipe
Authorization: Bearer dev_key_local
Content-Type: application/json

{
  "card_id": "topic_housing",
  "card_type": "topic",
  "swipe_direction": "right",
  "metadata": {
    "topic_id": "housing"
  }
}
```

### Response
```json
{
  "success": true,
  "message": "Swipe recorded"
}
```

### Implementation
```python
@app.route('/api/onboarding/swipe', methods=['POST'])
def record_onboarding_swipe():
    user_id = get_user_id_from_auth()
    data = request.json

    card_id = data['card_id']
    card_type = data['card_type']
    swipe_direction = data['swipe_direction']
    metadata = data.get('metadata', {})

    # Record as civic_history action (synthetic behavioral signal)
    if swipe_direction == 'right':  # Only record "likes"
        action_data = {
            'user_id': user_id,
            'action_type': 'onboarding_interest',  # NEW action type
            'timestamp': datetime.utcnow().isoformat(),
            'metadata': {
                'card_id': card_id,
                'card_type': card_type,
                **metadata
            }
        }

        # Infer topic from card type
        if card_type == 'topic':
            action_data['topic'] = metadata.get('topic_id')
        elif card_type == 'event':
            action_data['topic'] = metadata.get('topic')
            action_data['event_id'] = metadata.get('event_id')
        elif card_type == 'issue':
            action_data['topic'] = metadata.get('topic')
        elif card_type == 'jurisdiction':
            action_data['jurisdiction_id'] = metadata.get('jurisdiction_id')

        # Insert into civic_history
        personalization_service.record_action(action_data)

    return jsonify({'success': True, 'message': 'Swipe recorded'})
```

### Database Impact

Swipes create entries in `civic_history`:
```sql
INSERT INTO civic_history (
    user_id,
    action_type,
    topic,
    event_id,
    jurisdiction_id,
    timestamp,
    metadata
) VALUES (
    'dev_key_local',
    'onboarding_interest',
    'housing',
    NULL,
    NULL,
    '2025-10-29T20:00:00',
    '{"card_id": "topic_housing", "card_type": "topic"}'
);
```

**Weight in Phase 3 Inference**:
- `onboarding_interest` actions = **0.6 weight** (lower than real actions)
- Real comments/meetings = **1.0 weight**
- Over time, real actions will override onboarding signals

---

## Endpoint 3: POST /api/onboarding/complete

**Purpose**: Mark user as having completed onboarding

### Request
```bash
POST /api/onboarding/complete
Authorization: Bearer dev_key_local
```

### Response
```json
{
  "success": true,
  "message": "Onboarding completed",
  "interests_discovered": 12
}
```

### Implementation
```python
@app.route('/api/onboarding/complete', methods=['POST'])
def complete_onboarding():
    user_id = get_user_id_from_auth()

    # Mark onboarding as complete (could use user_profiles table)
    # For now, can track via civic_history
    action_data = {
        'user_id': user_id,
        'action_type': 'onboarding_completed',
        'timestamp': datetime.utcnow().isoformat()
    }
    personalization_service.record_action(action_data)

    # Count how many interests discovered
    swipe_count = count_onboarding_swipes(user_id)

    return jsonify({
        'success': True,
        'message': 'Onboarding completed',
        'interests_discovered': swipe_count
    })

def count_onboarding_swipes(user_id):
    cursor = get_db_cursor()
    cursor.execute("""
        SELECT COUNT(*)
        FROM civic_history
        WHERE user_id = ? AND action_type = 'onboarding_interest'
    """, (user_id,))
    return cursor.fetchone()[0]
```

---

## Helper Functions Needed

### Topic Formatting
```python
TOPIC_CONFIG = {
    'housing': {
        'title': 'Affordable Housing',
        'description': 'Rental affordability, development regulations, inclusionary zoning',
        'icon': '🏠'
    },
    'transportation': {
        'title': 'Transportation & Transit',
        'description': 'Public transit, bike lanes, traffic, parking',
        'icon': '🚌'
    },
    'environment': {
        'title': 'Environment & Climate',
        'description': 'Climate action, parks, air quality, waste',
        'icon': '🌳'
    },
    # ... etc for all 10 topics
}

def format_topic_title(topic):
    return TOPIC_CONFIG.get(topic, {}).get('title', topic.title())

def get_topic_description(topic):
    return TOPIC_CONFIG.get(topic, {}).get('description', '')

def get_topic_icon(topic):
    return TOPIC_CONFIG.get(topic, {}).get('icon', '📋')
```

---

## Migration: Add Onboarding Action Types

No new tables needed! Just use existing `civic_history` table with new action types:
- `onboarding_interest` - User swiped right on a card
- `onboarding_completed` - User finished onboarding flow

Phase 3 inference engine will recognize these types and weight them appropriately.

---

## Integration with Phase 3

When Phase 3 behavioral inference is built, it will:

1. **Query onboarding signals**:
```python
def get_initial_interests(user_id):
    cursor.execute("""
        SELECT topic, COUNT(*) as count
        FROM civic_history
        WHERE user_id = ? AND action_type = 'onboarding_interest'
        GROUP BY topic
    """, (user_id,))
    return cursor.fetchall()
```

2. **Apply lower weight** (0.6 vs 1.0 for real actions)
3. **Override over time** as user takes real actions

---

## Testing

### Manual Test Flow
```bash
# 1. Get cards
curl -H "Authorization: Bearer dev_key_local" \
     http://localhost:8001/api/onboarding/cards

# 2. Swipe right on housing
curl -X POST -H "Authorization: Bearer dev_key_local" \
     -H "Content-Type: application/json" \
     -d '{"card_id":"topic_housing","card_type":"topic","swipe_direction":"right","metadata":{"topic_id":"housing"}}' \
     http://localhost:8001/api/onboarding/swipe

# 3. Complete onboarding
curl -X POST -H "Authorization: Bearer dev_key_local" \
     http://localhost:8001/api/onboarding/complete

# 4. Verify civic_history entries
sqlite3 data/civic_participation.db \
  "SELECT * FROM civic_history WHERE action_type = 'onboarding_interest';"
```

---

## Implementation Priority

**Minimal Viable Backend** (1-2 hours):
1. ✅ `/api/onboarding/cards` - Return 20 hardcoded cards (8 topics + placeholders)
2. ✅ `/api/onboarding/swipe` - Insert into civic_history
3. ✅ `/api/onboarding/complete` - Simple success response

**Enhanced Version** (add later):
- Dynamic event/issue cards based on user location
- Nearby jurisdiction suggestions
- Card diversity algorithms

---

## Expected Impact

**UX Metrics**:
- Onboarding completion: 25% → 85%
- Time to first value: 5 min → 60 sec
- User delight: 📈📈📈

**Data Quality**:
- New users now have behavioral signals immediately
- Phase 3 has data to work with (no cold start!)
- Revealed preference > stated preference

**Cost**: $0 (pure backend logic, no LLM calls)

---

## Next Steps

1. **Backend** (this guide): Implement 3 endpoints (1-2 hours)
2. **Frontend** (✅ complete): Components ready
3. **Integration** (next): Wire up App.vue to show onboarding
4. **Testing**: Verify swipe → civic_history flow
5. **Phase 3**: Build inference engine that uses this data

Frontend is waiting! 🚀
