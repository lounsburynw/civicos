# Personalization Service: Implementation Guide
## Quick Start for Development

**Date**: 2025-10-29
**Status**: Ready to Implement
**Estimated Timeline**: 3-4 weeks (1 backend developer)

---

## Executive Summary

This guide provides a **step-by-step implementation plan** for deploying the PersonalizationService architecture. The service provides centralized user profiles, civic history tracking, and behavioral inference to power all personalized features (comment drafting, email writing, meeting recommendations, etc.).

**Key Deliverable**: A robust, reusable personalization layer that avoids per-feature context duplication.

---

## Prerequisites

Before starting implementation:

- [x] Read `PERSONALIZATION_SERVICE_ARCHITECTURE.md` (complete architecture)
- [x] Read `COMMENT_DRAFTING_ARCHITECTURE.md` Part 16 (migration strategy)
- [x] Review `API_DOCUMENTATION.md` v1.2 (new endpoints)
- [ ] Set up local development environment with test database
- [ ] Verify Python dependencies: `sqlite3`, `flask`, `openai`

---

## Phase 1: Database Schema (Days 1-2)

### Step 1.1: Run Migration Script

```bash
cd /Users/nicolaslounsbury/projects/civic

# Backup existing database
cp data/civic_participation.db data/civic_participation.db.backup_$(date +%Y%m%d)

# Run migration
sqlite3 data/civic_participation.db < migrations/006_personalization_service.sql

# Verify tables created
sqlite3 data/civic_participation.db "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"

# Expected output should include:
# - user_profiles
# - civic_history
# - inferred_interests
```

### Step 1.2: Verify Schema

```bash
# Check user_profiles structure
sqlite3 data/civic_participation.db ".schema user_profiles"

# Check civic_history structure
sqlite3 data/civic_participation.db ".schema civic_history"

# Check inferred_interests structure
sqlite3 data/civic_participation.db ".schema inferred_interests"

# Verify indexes
sqlite3 data/civic_participation.db "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND tbl_name IN ('user_profiles', 'civic_history', 'inferred_interests');"
```

### Step 1.3: Test with Sample Data

```bash
# Insert test user profile
sqlite3 data/civic_participation.db <<EOF
INSERT INTO user_profiles (user_id, jurisdiction_id, display_name, stakes, years_in_area, civic_interests)
VALUES (
    'test_user_001',
    'city-berkeley',
    'Test User',
    '["homeowner", "parent"]',
    15,
    '["housing", "transportation"]'
);

SELECT * FROM user_profiles WHERE user_id = 'test_user_001';
EOF

# Clean up test data
sqlite3 data/civic_participation.db "DELETE FROM user_profiles WHERE user_id = 'test_user_001';"
```

**Expected outcome**: Tables created, indexes verified, sample insert/query works.

---

## Phase 2: PersonalizationService Class (Days 3-5)

### Step 2.1: Create Service File

```bash
touch src/personalization_service.py
```

### Step 2.2: Implement Core Methods

File: `src/personalization_service.py`

```python
import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from collections import defaultdict
import math

class PersonalizationService:
    """
    Unified API for user context, civic history, and behavioral inference.

    All civic features should use this service instead of direct DB access.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.cache = {}  # In-memory cache for session

    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ===== PROFILE MANAGEMENT =====

    def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """
        Get full user profile with demographics and preferences.

        Returns None if user doesn't exist.
        Results cached per-session.
        """
        # Check cache first
        if user_id in self.cache:
            return self.cache[user_id]

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM user_profiles WHERE user_id = ?
        """, (user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Convert to dict and parse JSON fields
        profile = dict(row)
        profile['stakes'] = json.loads(profile['stakes']) if profile['stakes'] else []
        profile['civic_interests'] = json.loads(profile['civic_interests']) if profile['civic_interests'] else []
        profile['topics_following'] = json.loads(profile['topics_following']) if profile['topics_following'] else []
        profile['notification_preferences'] = json.loads(profile['notification_preferences']) if profile['notification_preferences'] else {}
        profile['privacy_settings'] = json.loads(profile['privacy_settings']) if profile['privacy_settings'] else {}

        # Cache result
        self.cache[user_id] = profile
        return profile

    def create_user_profile(self, user_id: str, profile_data: dict) -> Dict:
        """
        Create new user profile.

        Validates required fields, sets defaults, calculates completeness.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Required fields
        if 'jurisdictionId' not in profile_data:
            raise ValueError("jurisdictionId is required")

        # Parse and serialize JSON fields
        stakes = json.dumps(profile_data.get('stakes', []))
        civic_interests = json.dumps(profile_data.get('civicInterests', []))
        topics_following = json.dumps(profile_data.get('topicsFollowing', []))
        notification_preferences = json.dumps(profile_data.get('notificationPreferences', {}))
        privacy_settings = json.dumps(profile_data.get('privacySettings', {
            'profileVisibility': 'public',
            'showCivicHistory': True,
            'allowBehavioralInference': True
        }))

        # Calculate completeness
        completeness = self._calculate_completeness(profile_data)

        cursor.execute("""
            INSERT INTO user_profiles (
                user_id, display_name, avatar_url, stakes, years_in_area,
                district, neighborhood, jurisdiction_id, expertise,
                civic_interests, topics_following, notification_preferences,
                privacy_settings, profile_completeness
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            profile_data.get('displayName'),
            profile_data.get('avatarUrl'),
            stakes,
            profile_data.get('yearsInArea'),
            profile_data.get('district'),
            profile_data.get('neighborhood'),
            profile_data['jurisdictionId'],
            profile_data.get('expertise'),
            civic_interests,
            topics_following,
            notification_preferences,
            privacy_settings,
            completeness
        ))

        conn.commit()
        conn.close()

        # Invalidate cache
        if user_id in self.cache:
            del self.cache[user_id]

        return self.get_user_profile(user_id)

    def _calculate_completeness(self, profile_data: dict) -> int:
        """Calculate profile completeness score (0-100)"""
        fields = [
            ('displayName', 5),
            ('stakes', 15),
            ('yearsInArea', 10),
            ('district', 10),
            ('neighborhood', 10),
            ('expertise', 15),
            ('civicInterests', 20),
            ('avatarUrl', 5),
            ('notificationPreferences', 10)
        ]

        score = 0
        for field, weight in fields:
            value = profile_data.get(field)
            if isinstance(value, list) and len(value) > 0:
                score += weight
            elif isinstance(value, dict) and len(value) > 0:
                score += weight
            elif value:
                score += weight

        return score

    # ===== CIVIC HISTORY =====

    def track_action(
        self,
        user_id: str,
        action_type: str,
        entity_type: str,
        entity_id: str,
        metadata: dict = None
    ) -> str:
        """
        Record a civic action to user's history.

        Returns action_id.
        """
        action_id = str(uuid.uuid4())

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO civic_history (
                action_id, user_id, action_type, entity_type, entity_id,
                metadata, jurisdiction_id, topic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            action_id,
            user_id,
            action_type,
            entity_type,
            entity_id,
            json.dumps(metadata) if metadata else None,
            metadata.get('jurisdictionId') if metadata else None,
            metadata.get('topic') if metadata else None
        ))

        conn.commit()
        conn.close()

        return action_id

    def get_civic_history(
        self,
        user_id: str,
        action_types: List[str] = None,
        since: datetime = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get user's civic action history with optional filtering"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM civic_history WHERE user_id = ?"
        params = [user_id]

        if action_types:
            placeholders = ','.join(['?'] * len(action_types))
            query += f" AND action_type IN ({placeholders})"
            params.extend(action_types)

        if since:
            query += " AND created_at > ?"
            params.append(since.isoformat())

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        actions = []
        for row in rows:
            action = dict(row)
            action['metadata'] = json.loads(action['metadata']) if action['metadata'] else {}
            actions.append(action)

        return actions

    # ===== BEHAVIORAL INFERENCE =====

    def infer_civic_interests(self, user_id: str) -> Dict[str, float]:
        """
        Infer topic interests from user's action history.

        Returns topic → confidence score (0-1).
        """
        # Get recent history (last 90 days)
        since = datetime.now() - timedelta(days=90)
        actions = self.get_civic_history(user_id, since=since, limit=500)

        if not actions:
            return {}

        # Action type weights
        weights = {
            'comment_drafted': 10,
            'issue_filed': 10,
            'email_sent': 8,
            'meeting_attended': 8,
            'issue_followed': 5,
            'bill_viewed': 4,
            'event_clicked': 2,
            'meeting_viewed': 2
        }

        # Topic scores
        topic_scores = defaultdict(float)
        now = datetime.now()

        for action in actions:
            topic = action.get('metadata', {}).get('topic')
            if not topic:
                continue

            # Base weight from action type
            base_weight = weights.get(action['action_type'], 1)

            # Time decay (exponential, half-life = 30 days)
            created_at = datetime.fromisoformat(action['created_at'])
            days_ago = (now - created_at).days
            time_factor = math.exp(-days_ago / 30)

            # Final score
            topic_scores[topic] += base_weight * time_factor

        # Normalize to 0-1 scale
        if topic_scores:
            max_score = max(topic_scores.values())
            topic_scores = {
                topic: score / max_score
                for topic, score in topic_scores.items()
            }

        # Filter topics with score < 0.1 (noise)
        topic_scores = {
            topic: score
            for topic, score in topic_scores.items()
            if score >= 0.1
        }

        return dict(topic_scores)

    # ===== CONTEXT FOR AI GENERATION =====

    def get_context_for_ai(
        self,
        user_id: str,
        context_type: str = 'full'
    ) -> dict:
        """
        Get unified context for AI prompt construction.

        context_type:
        - 'demographics': Just stakes, years, expertise (for comment drafting)
        - 'interests': Civic interests + inferred topics
        - 'history': Recent civic actions
        - 'full': All of the above
        """
        profile = self.get_user_profile(user_id)

        if not profile:
            return {}

        context = {}

        if context_type in ('demographics', 'full'):
            context['stakes'] = profile.get('stakes', [])
            context['yearsInArea'] = profile.get('years_in_area')
            context['district'] = profile.get('district')
            context['neighborhood'] = profile.get('neighborhood')
            context['expertise'] = profile.get('expertise')

        if context_type in ('interests', 'full'):
            context['civicInterests'] = profile.get('civic_interests', [])
            context['inferredInterests'] = self.infer_civic_interests(user_id)

        if context_type in ('history', 'full'):
            recent_actions = self.get_civic_history(user_id, limit=10)
            context['recentActions'] = [
                {
                    'type': a['action_type'],
                    'topic': a.get('metadata', {}).get('topic'),
                    'date': a['created_at']
                }
                for a in recent_actions
            ]

        return context
```

### Step 2.3: Write Unit Tests

File: `tests/test_personalization_service.py`

```python
import unittest
import os
import tempfile
from src.personalization_service import PersonalizationService

class TestPersonalizationService(unittest.TestCase):

    def setUp(self):
        # Create temporary database
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.service = PersonalizationService(self.db_path)

        # Run migration
        with open('migrations/006_personalization_service.sql', 'r') as f:
            sql = f.read()
            conn = self.service._get_connection()
            conn.executescript(sql)
            conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_profile(self):
        profile = self.service.create_user_profile('test_user', {
            'jurisdictionId': 'city-berkeley',
            'stakes': ['homeowner'],
            'yearsInArea': 15
        })

        self.assertEqual(profile['user_id'], 'test_user')
        self.assertEqual(profile['jurisdiction_id'], 'city-berkeley')
        self.assertGreater(profile['profile_completeness'], 0)

    def test_track_action(self):
        # Create profile first
        self.service.create_user_profile('test_user', {
            'jurisdictionId': 'city-berkeley'
        })

        # Track action
        action_id = self.service.track_action(
            'test_user',
            'event_clicked',
            'event',
            'event-123',
            {'topic': 'housing'}
        )

        self.assertIsNotNone(action_id)

        # Retrieve history
        history = self.service.get_civic_history('test_user')
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['action_type'], 'event_clicked')

    def test_infer_interests(self):
        # Create profile
        self.service.create_user_profile('test_user', {
            'jurisdictionId': 'city-berkeley'
        })

        # Track multiple housing actions
        for i in range(10):
            self.service.track_action(
                'test_user',
                'event_clicked',
                'event',
                f'event-{i}',
                {'topic': 'housing'}
            )

        # Infer interests
        interests = self.service.infer_civic_interests('test_user')

        self.assertIn('housing', interests)
        self.assertGreater(interests['housing'], 0.5)

if __name__ == '__main__':
    unittest.main()
```

**Run tests:**
```bash
python -m pytest tests/test_personalization_service.py -v
```

**Expected outcome**: PersonalizationService class implemented with 80%+ test coverage.

---

## Phase 3: API Integration (Days 6-8)

### Step 3.0: Implement Authentication

Before implementing endpoints, add user authentication to extract user_id from Bearer tokens.

File: `src/civic_api_integrated.py` (add method to CivicAPIServer class)

```python
def get_user_id_from_token(self) -> Optional[str]:
    """
    Extract user_id from Bearer token in Authorization header.

    For MVP: Token IS the user_id (simple mapping)
    For Production: Use JWT with user_id in payload

    Returns None if token is missing or invalid.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header.split(' ')[1]

    # MVP Implementation: token is the user_id
    # This works for development and simple authentication
    return token

    # Production Implementation (optional - uncomment when ready):
    # import jwt
    # try:
    #     payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
    #     return payload.get('user_id')
    # except jwt.InvalidTokenError:
    #     return None
```

**Why MVP uses token as user_id**:
- Simple to test and develop with
- No JWT library dependency
- Sufficient for foundation-funded civic infrastructure (not a SaaS product)
- Easy upgrade path to JWT when needed

**Testing authentication**:
```bash
# Set token to a test user_id
export TOKEN="user-abc123"

# Make authenticated request
curl http://localhost:8001/api/user/profile \
  -H "Authorization: Bearer $TOKEN"
```

### Step 3.1: Initialize Service in API Server

File: `src/civic_api_integrated.py` (modify existing)

```python
from personalization_service import PersonalizationService

class CivicAPIServer:
    def __init__(self, api_key):
        self.api_key = api_key
        self.db_path = "data/civic_participation.db"

        # Initialize personalization service
        self.personalization = PersonalizationService(self.db_path)

        # ... existing initializations ...
```

### Step 3.2: Add Profile Endpoints

Add to `civic_api_integrated.py`:

```python
@app.route('/api/user/profile', methods=['GET', 'POST'])
def handle_user_profile():
    """Handle user profile operations. User ID extracted from Bearer token."""
    if not self.authenticate_request():
        return jsonify({'error': 'Unauthorized'}), 401

    # Extract user_id from Bearer token
    user_id = self.get_user_id_from_token()
    if not user_id:
        return jsonify({'error': 'Invalid token'}), 401

    if request.method == 'GET':
        profile = self.personalization.get_user_profile(user_id)
        if not profile:
            return jsonify({'error': 'Profile not found'}), 404
        return jsonify({'profile': profile})

    elif request.method == 'POST':
        data = request.json
        try:
            profile = self.personalization.create_user_profile(user_id, data)
            return jsonify({
                'userId': profile['user_id'],
                'profileCompleteness': profile['profile_completeness'],
                'createdAt': profile['created_at']
            })
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

@app.route('/api/user/civic-history', methods=['GET'])
def get_civic_history():
    """Get civic history for authenticated user."""
    if not self.authenticate_request():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = self.get_user_id_from_token()
    if not user_id:
        return jsonify({'error': 'Invalid token'}), 401

    # Parse query params
    action_types = request.args.get('action_types', '').split(',') if request.args.get('action_types') else None
    limit = int(request.args.get('limit', 100))

    history = self.personalization.get_civic_history(user_id, action_types=action_types, limit=limit)

    return jsonify({
        'actions': history,
        'metadata': {'total_actions': len(history)}
    })

@app.route('/api/user/inferred-interests', methods=['GET'])
def get_inferred_interests():
    """Get behavioral inference for authenticated user."""
    if not self.authenticate_request():
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = self.get_user_id_from_token()
    if not user_id:
        return jsonify({'error': 'Invalid token'}), 401

    interests = self.personalization.infer_civic_interests(user_id)

    return jsonify({
        'interests': interests,
        'confidence': 'high' if interests else 'low'
    })
```

### Step 3.3: Test Endpoints

```bash
# Start API server
python src/civic_api_integrated.py

# In another terminal, test endpoints
# Token IS the user_id for MVP (simple authentication)
export TOKEN="test-user-123"

# Create profile (user_id extracted from token)
curl -X POST http://localhost:8001/api/user/profile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jurisdictionId": "city-berkeley",
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "civicInterests": ["housing"]
  }'

# Get profile (user_id extracted from token)
curl http://localhost:8001/api/user/profile \
  -H "Authorization: Bearer $TOKEN"

# Get civic history (user_id extracted from token)
curl http://localhost:8001/api/user/civic-history \
  -H "Authorization: Bearer $TOKEN"
```

**Expected outcome**: All profile endpoints working, returning correct data.

---

## Phase 4: Refactor Comment Drafting (Days 9-10)

### Step 4.1: Update Draft Comment Endpoint

Modify `handle_draft_comment()` in `civic_api_integrated.py`:

```python
@app.route('/api/events/<event_id>/draft-comment', methods=['POST'])
def handle_draft_comment(event_id):
    if not self.authenticate_request():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    user_id = self.get_user_id_from_token()  # Extract from Bearer token

    # Backward compatibility: accept personalContext OR use profile
    if 'personalContext' in data:
        context = data['personalContext']
        context_source = 'request_override'
    else:
        context = self.personalization.get_context_for_ai(user_id, 'demographics')
        context_source = 'user_profile'

    # Generate comment (existing logic)
    draft = self.generate_comment_draft(
        event_id,
        data.get('position'),
        data.get('keyConcern'),
        context
    )

    # Track action
    self.personalization.track_action(
        user_id,
        action_type='comment_drafted',
        entity_type='event',
        entity_id=event_id,
        metadata={
            'position': data.get('position'),
            'topic': event.get('project_type'),  # Extract from event
            'aiGenerated': True
        }
    )

    return jsonify({
        'draft': draft,
        'metadata': {'context_source': context_source}
    })
```

### Step 4.2: Test End-to-End Flow

```bash
# 1. Create user profile
# Token will be the user_id (dev_key_local → user_id)
export TOKEN="test-user-789"

curl -X POST http://localhost:8001/api/user/profile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jurisdictionId": "city-berkeley",
    "stakes": ["homeowner"],
    "yearsInArea": 10,
    "neighborhood": "Rockridge"
  }'

# 2. Draft comment WITHOUT personalContext (should use profile)
curl -X POST http://localhost:8001/api/events/event-123/draft-comment \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "position": "oppose",
    "keyConcern": "Traffic concerns during school hours"
  }'

# 3. Verify action was tracked (user_id extracted from token)
curl http://localhost:8001/api/user/civic-history \
  -H "Authorization: Bearer $TOKEN"
```

**Expected outcome**: Comment generated using profile context, action tracked in civic_history.

---

## Phase 5: Documentation & Deployment (Days 11-12)

### Step 5.1: Update Frontend (if applicable)

- Remove embedded `PersonalContextForm` from comment drafting UI
- Add profile completeness indicator
- Add "Update Profile" link

### Step 5.2: Write Migration Guide

Document in `docs/next_session_prompt.md`:
- Personalization service deployed
- Comment drafting refactored
- Next features to build (email drafting, recommendations)

### Step 5.3: Deploy to Production

```bash
# Run migration on production database
sqlite3 /path/to/production/civic_participation.db < migrations/006_personalization_service.sql

# Restart API server
pkill -f civic_api_integrated.py
nohup python src/civic_api_integrated.py > logs/api.log 2>&1 &
```

---

## Success Criteria

✅ **Technical**:
- [ ] All tables created with correct schema
- [ ] PersonalizationService passes unit tests (80%+ coverage)
- [ ] All API endpoints return correct data
- [ ] Comment drafting uses profile context
- [ ] Actions tracked to civic_history automatically

✅ **Functional**:
- [ ] User can create profile once, reuse for all comments
- [ ] Behavioral inference returns sensible topic scores
- [ ] Profile completeness calculated correctly
- [ ] Backward compatibility maintained (legacy clients with personalContext still work)

✅ **Performance**:
- [ ] Profile queries <50ms p95
- [ ] Inference computation doesn't block requests
- [ ] No N+1 query problems

---

## Troubleshooting

### Issue: Migration fails with "table already exists"

**Solution**: Tables might exist from incomplete previous migration.

```bash
sqlite3 data/civic_participation.db "DROP TABLE IF EXISTS user_profiles;"
sqlite3 data/civic_participation.db "DROP TABLE IF EXISTS civic_history;"
sqlite3 data/civic_participation.db "DROP TABLE IF EXISTS inferred_interests;"
# Then re-run migration
```

### Issue: Profile queries returning None for existing users

**Cause**: User doesn't have profile yet (need to create).

**Solution**: Add profile creation flow to frontend or use backward compatibility mode.

### Issue: Inference returns empty dict

**Cause**: User has no tracked actions yet.

**Solution**: This is expected for new users. Inference will populate as user engages.

---

## Next Steps After Implementation

**Week 4+**: Build on PersonalizationService foundation

1. **Email Drafting** (reuse same context)
2. **Meeting Recommendations** (use inferred interests)
3. **Action Personalization** (rank actions by user history)
4. **Profile UX** (profile completeness gamification)

See `PERSONALIZATION_SERVICE_ARCHITECTURE.md` Part 5 for integration examples.

---

## Support & Resources

**Primary Docs**:
- `PERSONALIZATION_SERVICE_ARCHITECTURE.md` - Complete architecture
- `API_DOCUMENTATION.md` - v1.2 endpoint specs
- `COMMENT_DRAFTING_ARCHITECTURE.md` - Migration guide

**Code Examples**:
- `src/personalization_service.py` - Service implementation (create this)
- `tests/test_personalization_service.py` - Unit tests (create this)
- `migrations/006_personalization_service.sql` - Database schema

**Questions?** Review implementation roadmap in PERSONALIZATION_SERVICE_ARCHITECTURE.md Part 13.
