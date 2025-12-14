# Personalization Service Architecture
## Unified User Context for Civic Engagement at Scale

**Version**: 1.0
**Date**: 2025-10-29
**Status**: Implementation Ready
**Strategic Importance**: Foundation for all personalized civic features

---

## Executive Summary

The Personalization Service provides a **centralized abstraction layer** for user context, civic history, and behavioral inference across all platform features. Instead of replicating context collection per-feature (comment drafting, email writing, meeting recommendations), this architecture enables **collect once, reuse everywhere**.

### Core Value Proposition

**Without Personalization Service:**
```
Feature 1 (Comment Drafting):
  User fills out: stakes, years in area, expertise → stored in comment

Feature 2 (Email Drafting):
  User fills out: stakes, years in area, expertise → stored in email

Feature 3 (Meeting Recommendations):
  User fills out: interests, location, expertise → stored in preferences

Result: 3x redundant data entry, inconsistent context, poor UX
```

**With Personalization Service:**
```
User Profile (created once):
  Demographics: stakes, years in area, expertise, neighborhood
  Civic History: comments drafted, events attended, emails sent
  Inferred Interests: housing (5 interactions), transit (2 interactions)

All features pull from unified profile → consistent, rich context
```

---

## Design Principles

### 1. **Separation of Concerns**
- **Profile Storage**: Demographics, preferences, explicit user input
- **Civic History**: Action tracking, behavior log
- **Inference Engine**: Learn interests/priorities from behavior
- **Personalization API**: Unified interface for features to request context

### 2. **Progressive Disclosure**
- Users can engage without profile (anonymous/guest mode)
- Profile completion is optional but incentivized (better AI drafts, recommendations)
- Context collected implicitly through usage (follow housing events → infer housing interest)

### 3. **Privacy-First** ⚠️ CRITICAL UPDATE (2025-10-29)

**⚠️ ARCHITECTURE CHANGE**: Political values are **NEVER** stored centrally in plaintext.

See `docs/PRIVACY_ARCHITECTURE.md` for complete privacy design.

**New Privacy Model:**
- **Civic archetypes** stored in browser localStorage (Tier 1) OR encrypted (Tier 2) OR zero-knowledge (Tier 3)
- User chooses storage model with full disclosure of trade-offs
- Backend CANNOT see political values in Tier 1 (browser-only)
- Backend CANNOT decrypt values in Tier 2 (encrypted sync)
- Backend CANNOT infer values in Tier 3 (zero-knowledge proofs)

**What this changes:**
- ❌ Remove: `user_profiles.civic_interests` (NO centralized political data)
- ❌ Remove: `onboarding_swipes` table (NO swipe tracking)
- ❌ Remove: Inference of political values from behavior
- ✅ Keep: Civic history (public actions like comments submitted)
- ✅ Keep: Demographics (stakes, years in area, jurisdiction)
- ✅ Add: Privacy tier selection during profile creation

**Rationale:**
- Centralized political data creates subpoena/breach/targeting risks
- Foundation values demand maximum user privacy
- Browser-only storage = zero surveillance risk
- Users can opt-in to encrypted sync if desired

### 4. **Reusability**
- **Single Source of Truth**: Profile data lives in one place
- **Feature-Agnostic**: Service doesn't know about comment drafting vs emails
- **Extensible**: Easy to add new context types without breaking existing features

### 5. **Performance**
- Profile data cached per-session (avoid DB hits)
- Civic history queries optimized with indexes
- Inference computed asynchronously (doesn't block requests)

---

## Part 1: User Profile Data Model

### 1.1 Core Profile Schema

```typescript
interface UserProfile {
  // Identity
  userId: string                  // Primary key, unique identifier
  displayName?: string            // Optional display name for community
  avatarUrl?: string              // DiceBear avatar or uploaded image

  // Demographics (Civic Context)
  stakes: string[]                // ["homeowner", "parent", "renter", "business_owner", "senior"]
  yearsInArea?: number            // 0-100, years of residency
  district?: string               // Electoral district (e.g., "District 3")
  neighborhood?: string           // Neighborhood name (e.g., "Rockridge")
  jurisdictionId: string          // Primary city/county (e.g., "city-berkeley")
  expertise?: string              // Professional background (e.g., "Urban planner")

  // Civic Interests ⚠️ PRIVACY UPDATE: Removed from backend (see PRIVACY_ARCHITECTURE.md)
  // civicInterests: string[]     // NOW stored in browser localStorage as "archetypes"
  topicsFollowing: string[]       // State bill topics user follows (public)

  // Preferences
  notificationPreferences: {
    email: boolean
    sms: boolean
    frequency: 'realtime' | 'daily' | 'weekly'
  }

  privacySettings: {
    profileVisibility: 'public' | 'connections' | 'private'
    showCivicHistory: boolean
    allowBehavioralInference: boolean
  }

  // Metadata
  createdAt: string               // ISO timestamp
  updatedAt: string               // ISO timestamp
  lastActiveAt: string            // ISO timestamp of last action
  profileCompleteness: number     // 0-100%, calculated
}
```

### 1.2 Profile Completeness Score

**Purpose**: Incentivize users to fill out profile for better personalization.

```typescript
function calculateCompleteness(profile: UserProfile): number {
  const fields = [
    { field: 'displayName', weight: 5 },
    { field: 'stakes', weight: 15, isArray: true },
    { field: 'yearsInArea', weight: 10 },
    { field: 'district', weight: 10 },
    { field: 'neighborhood', weight: 10 },
    { field: 'expertise', weight: 15 },
    { field: 'civicInterests', weight: 20, isArray: true },
    { field: 'avatarUrl', weight: 5 },
    { field: 'notificationPreferences', weight: 10, isObject: true }
  ]

  let score = 0
  for (const { field, weight, isArray, isObject } of fields) {
    const value = profile[field]
    if (isArray && value?.length > 0) score += weight
    else if (isObject && value && Object.keys(value).length > 0) score += weight
    else if (value) score += weight
  }

  return score
}
```

**Display to user:**
```
Profile: 65% Complete
✓ Stakes: Homeowner, Parent
✓ Neighborhood: Rockridge
✓ Years in Area: 15
✗ Add expertise to improve AI comment quality
✗ Select civic interests for better meeting recommendations
```

---

## Part 2: Civic History Data Model

### 2.1 Action Tracking Schema

```typescript
interface CivicAction {
  id: string                      // Action UUID
  userId: string                  // User who took action
  actionType: ActionType          // Type of civic engagement
  entityType: string              // 'event', 'issue', 'bill', 'official'
  entityId: string                // ID of entity acted upon

  // Context
  metadata: Record<string, any>   // Action-specific data (flexible)
  jurisdictionId?: string         // Where action occurred
  topic?: string                  // housing, transportation, etc.

  // Timestamps
  createdAt: string               // When action occurred
}

type ActionType =
  // Content creation
  | 'comment_drafted'
  | 'email_sent'
  | 'issue_filed'
  | 'petition_signed'

  // Meeting engagement
  | 'meeting_attended'
  | 'meeting_viewed'
  | 'agenda_item_clicked'

  // Social coordination
  | 'discussion_message_sent'
  | 'issue_followed'
  | 'user_followed'

  // Legislative tracking
  | 'bill_viewed'
  | 'program_viewed'

  // Discovery
  | 'event_clicked'
  | 'search_performed'
```

### 2.2 Metadata Examples by Action Type

**comment_drafted:**
```json
{
  "eventId": "event-berkeley-planning-2025-11-15",
  "agendaItemId": "item-7.2",
  "position": "oppose",
  "topic": "housing",
  "submissionFormat": "written",
  "aiGenerated": true
}
```

**meeting_attended:**
```json
{
  "eventId": "event-berkeley-planning-2025-11-15",
  "attendanceType": "in_person",
  "spokePublicly": true,
  "durationMinutes": 120
}
```

**issue_filed:**
```json
{
  "issueId": "issue-abc123",
  "issueType": "infrastructure",
  "jurisdictionId": "city-oakland",
  "location": { "lat": 37.8, "lng": -122.2 }
}
```

### 2.3 Civic Impact Metrics

Derived from civic history:

```typescript
interface CivicImpactMetrics {
  userId: string

  // Engagement level
  totalActions: number
  actionsLast30Days: number
  engagementTier: 'observer' | 'participant' | 'organizer' | 'leader'

  // Content creation
  commentsDrafted: number
  issuesFiled: number
  emailsSent: number

  // Meeting participation
  meetingsAttended: number
  meetingsViewed: number
  publicCommentsMade: number

  // Social coordination
  issuesFollowing: number
  discussionsJoined: number

  // Topic expertise
  topicBreakdown: {
    housing: number
    transportation: number
    environment: number
    // ... other topics
  }

  // Impact outcomes (if tracked)
  issuesResolved: number
  decisionsInfluenced: number

  // Streaks
  currentStreak: number           // Days with at least 1 action
  longestStreak: number
}
```

---

## Part 3: Personalization Service API

### 3.1 Service Interface

```python
# src/personalization_service.py

class PersonalizationService:
    """
    Unified API for user context, civic history, and behavioral inference.

    All civic features should use this service instead of direct DB access
    for user context retrieval.
    """

    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.cache = {}  # In-memory cache for session

    # ===== PROFILE MANAGEMENT =====

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """
        Get full user profile with demographics and preferences.

        Returns None if user doesn't exist (guest/anonymous).
        Results cached per-session.
        """

    def create_user_profile(self, user_id: str, profile_data: dict) -> UserProfile:
        """
        Create new user profile.

        Validates required fields, sets defaults, calculates completeness.
        """

    def update_user_profile(self, user_id: str, updates: dict) -> UserProfile:
        """
        Update existing profile fields.

        Recalculates completeness score after update.
        """

    def get_profile_completeness(self, user_id: str) -> dict:
        """
        Get profile completeness with suggestions for improvement.

        Returns:
        {
            "score": 65,
            "missing_fields": [
                {"field": "expertise", "benefit": "Improves AI comment quality"},
                {"field": "civicInterests", "benefit": "Better meeting recommendations"}
            ]
        }
        """

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
        Triggers async inference update if needed.
        """

    def get_civic_history(
        self,
        user_id: str,
        action_types: List[str] = None,
        since: datetime = None,
        limit: int = 100
    ) -> List[CivicAction]:
        """
        Get user's civic action history with optional filtering.
        """

    def get_civic_metrics(self, user_id: str) -> CivicImpactMetrics:
        """
        Get aggregated civic engagement metrics.

        Computed from civic_history table with optimized queries.
        Cached for 1 hour.
        """

    # ===== BEHAVIORAL INFERENCE =====

    def infer_civic_interests(self, user_id: str) -> Dict[str, float]:
        """
        Infer topic interests from user's action history.

        Returns topic → confidence score (0-1):
        {
            "housing": 0.85,
            "transportation": 0.42,
            "environment": 0.15
        }

        Algorithm:
        - Weight actions by recency (exponential decay)
        - Weight by action type (attended > viewed > clicked)
        - Normalize to 0-1 scale
        """

    def infer_jurisdiction_affinity(self, user_id: str) -> List[str]:
        """
        Infer which jurisdictions user is most engaged with.

        Returns list of jurisdiction_ids sorted by engagement.
        """

    def infer_expertise(self, user_id: str) -> Optional[str]:
        """
        Infer professional expertise from comment quality and topics.

        Uses heuristics:
        - If 80%+ of comments on single topic → likely expertise
        - If comments are long and technical → likely professional
        - If user is always first to comment → likely insider/activist

        Returns None if insufficient data.
        """

    # ===== CONTEXT FOR AI GENERATION =====

    def get_context_for_ai(
        self,
        user_id: str,
        context_type: str = 'full',
        include_inferred: bool = True
    ) -> dict:
        """
        Get unified context for AI prompt construction.

        context_type:
        - 'demographics': Just stakes, years, expertise (for comment drafting)
        - 'interests': Civic interests + inferred topics (for recommendations)
        - 'history': Recent civic actions (for personalized suggestions)
        - 'full': All of the above

        include_inferred: Whether to include inferred interests/expertise

        Returns structured dict ready for AI prompt insertion.
        """

    # ===== ACTION PERSONALIZATION =====

    def personalize_actions(
        self,
        user_id: str,
        available_actions: List[dict]
    ) -> List[dict]:
        """
        Rank and filter actions based on user context.

        Uses:
        - Civic interests (show housing actions to housing enthusiasts)
        - Past behavior (show meeting attendance to frequent attendees)
        - Jurisdiction affinity (prioritize user's city)

        Returns sorted list with 'relevance_score' added.
        """

    def recommend_events(
        self,
        user_id: str,
        all_events: List[dict],
        limit: int = 10
    ) -> List[dict]:
        """
        Recommend most relevant civic events for user.

        Scoring factors:
        - Topic match with interests (40%)
        - Jurisdiction match (30%)
        - Event type (meeting vs hearing) preference (15%)
        - Recency and urgency (15%)

        Returns sorted events with 'recommendation_score'.
        """
```

### 3.2 Service Initialization

```python
# src/civic_api_integrated.py

class CivicAPIServer:
    def __init__(self, api_key):
        self.api_key = api_key
        self.db_path = "data/civic_participation.db"

        # Initialize personalization service
        self.personalization = PersonalizationService(self.db_path)

        # Initialize other services
        self.complaint_storage = ComplaintStorage(self.db_path)
        self.community_storage = CommunityStorage(self.db_path)
```

---

## Part 4: Context Discovery (Behavioral Inference)

### 4.1 Interest Inference Algorithm

**Goal**: Learn user's civic interests from their actions without explicit input.

```python
def infer_civic_interests(self, user_id: str) -> Dict[str, float]:
    """
    Infer topic interests with weighted scoring.
    """
    # Get recent history (last 90 days)
    actions = self.get_civic_history(
        user_id,
        since=datetime.now() - timedelta(days=90)
    )

    # Topic scores
    topic_scores = defaultdict(float)

    # Action type weights
    weights = {
        'comment_drafted': 10,      # High signal
        'issue_filed': 10,
        'email_sent': 8,
        'meeting_attended': 8,
        'issue_followed': 5,
        'bill_viewed': 4,
        'event_clicked': 2,          # Low signal
        'meeting_viewed': 2
    }

    # Time decay (recent actions weighted higher)
    now = datetime.now()

    for action in actions:
        topic = action.get('metadata', {}).get('topic')
        if not topic:
            continue

        # Base weight from action type
        base_weight = weights.get(action['actionType'], 1)

        # Time decay (exponential, half-life = 30 days)
        days_ago = (now - datetime.fromisoformat(action['createdAt'])).days
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
```

**Example Output:**
```json
{
  "housing": 0.92,        // Very engaged
  "transportation": 0.45, // Moderately engaged
  "environment": 0.12     // Minimal engagement
}
```

### 4.2 Expertise Inference

```python
def infer_expertise(self, user_id: str) -> Optional[str]:
    """
    Infer professional expertise from behavior patterns.
    """
    actions = self.get_civic_history(user_id, limit=100)

    # Count comments by topic
    topic_comments = defaultdict(int)
    for action in actions:
        if action['actionType'] == 'comment_drafted':
            topic = action.get('metadata', {}).get('topic')
            if topic:
                topic_comments[topic] += 1

    # Check for topic dominance (80%+ on single topic)
    total_comments = sum(topic_comments.values())
    if total_comments >= 5:  # Minimum threshold
        for topic, count in topic_comments.items():
            if count / total_comments >= 0.8:
                # Likely professional in this domain
                expertise_map = {
                    'housing': 'Housing/Urban Planning',
                    'transportation': 'Transportation/Traffic Engineering',
                    'environment': 'Environmental Science/Policy',
                    'education': 'Education/Teaching'
                }
                return expertise_map.get(topic)

    return None
```

### 4.3 Jurisdiction Affinity

```python
def infer_jurisdiction_affinity(self, user_id: str) -> List[str]:
    """
    Determine which jurisdictions user is most engaged with.
    """
    actions = self.get_civic_history(user_id, limit=200)

    # Count actions by jurisdiction
    jurisdiction_scores = defaultdict(int)

    weights = {
        'comment_drafted': 5,
        'issue_filed': 5,
        'meeting_attended': 4,
        'event_clicked': 1
    }

    for action in actions:
        jurisdiction = action.get('metadata', {}).get('jurisdictionId')
        if jurisdiction:
            weight = weights.get(action['actionType'], 1)
            jurisdiction_scores[jurisdiction] += weight

    # Sort by score
    sorted_jurisdictions = sorted(
        jurisdiction_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return [jur_id for jur_id, score in sorted_jurisdictions]
```

---

## Part 5: Integration with Existing Features

### 5.1 Comment Drafting (Refactored)

**Before (Session 37-38):**
```python
@app.route('/api/events/<event_id>/draft-comment', methods=['POST'])
def handle_draft_comment(event_id):
    data = request.json

    # User passes personalContext every time
    personal_context = data.get('personalContext', {})
    position = data.get('position')
    key_concern = data.get('keyConcern')

    # Use context to generate comment
    draft = generate_comment(event_id, position, key_concern, personal_context)
```

**After (With Personalization Service):**
```python
@app.route('/api/events/<event_id>/draft-comment', methods=['POST'])
def handle_draft_comment(event_id):
    data = request.json
    user_id = get_user_id_from_token()  # Extract from Bearer token

    # Get position and concern from request (still required)
    position = data.get('position')
    key_concern = data.get('keyConcern')

    # Get context from personalization service
    context = self.personalization.get_context_for_ai(
        user_id,
        context_type='demographics'
    )

    # Generate comment with unified context
    draft = generate_comment(event_id, position, key_concern, context)

    # Track action for future inference
    self.personalization.track_action(
        user_id,
        action_type='comment_drafted',
        entity_type='event',
        entity_id=event_id,
        metadata={
            'position': position,
            'topic': event.get('project_type'),
            'aiGenerated': True
        }
    )
```

**Backward Compatibility:**
```python
# Support legacy clients that still pass personalContext
if 'personalContext' in data:
    context = data['personalContext']
else:
    context = self.personalization.get_context_for_ai(user_id, 'demographics')
```

### 5.2 Meeting Recommendations (New Feature)

```python
@app.route('/api/users/<user_id>/recommended-events', methods=['GET'])
def get_recommended_events(user_id):
    """
    Personalized event recommendations based on user profile + behavior.
    """
    # Get all upcoming events
    all_events = load_all_events()

    # Personalize with service
    recommended = self.personalization.recommend_events(
        user_id,
        all_events,
        limit=10
    )

    return jsonify({
        'recommended_events': recommended,
        'personalization_factors': {
            'interests': self.personalization.infer_civic_interests(user_id),
            'jurisdictions': self.personalization.infer_jurisdiction_affinity(user_id)
        }
    })
```

### 5.3 Email Drafting (Future Feature)

```python
@app.route('/api/officials/<official_id>/draft-email', methods=['POST'])
def draft_email_to_official(official_id):
    """
    Draft email to elected official using unified context.
    """
    data = request.json
    user_id = get_user_id_from_token()
    topic = data.get('topic')
    concern = data.get('concern')

    # Reuse same context as comment drafting
    context = self.personalization.get_context_for_ai(
        user_id,
        context_type='full'  # Include civic history for credibility
    )

    # Generate email
    draft = generate_official_email(official_id, topic, concern, context)

    # Track action
    self.personalization.track_action(
        user_id,
        action_type='email_sent',
        entity_type='official',
        entity_id=official_id,
        metadata={'topic': topic}
    )

    return jsonify({'draft': draft})
```

---

## Part 6: Database Schema

### 6.1 User Profiles Table

```sql
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY,

    -- Identity
    display_name TEXT,
    avatar_url TEXT,

    -- Demographics (Civic Context)
    stakes TEXT,                    -- JSON array: ["homeowner", "parent"]
    years_in_area INTEGER,
    district TEXT,
    neighborhood TEXT,
    jurisdiction_id TEXT NOT NULL,  -- Primary city/county
    expertise TEXT,

    -- Civic Interests (Explicit)
    civic_interests TEXT,           -- JSON array: ["housing", "transportation"]
    topics_following TEXT,          -- JSON array: state bill topics

    -- Preferences
    notification_preferences TEXT,  -- JSON object
    privacy_settings TEXT,          -- JSON object

    -- Metadata
    profile_completeness INTEGER DEFAULT 0,  -- 0-100
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP

    -- NOTE: jurisdiction_id validated against CITY_CONFIGS in application layer
    -- No foreign key constraint - jurisdictions stored in Python config, not database
);

CREATE INDEX idx_user_profiles_jurisdiction ON user_profiles(jurisdiction_id);
CREATE INDEX idx_user_profiles_completeness ON user_profiles(profile_completeness);
```

### 6.2 Civic History Table

```sql
CREATE TABLE civic_history (
    action_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,

    -- Action classification
    action_type TEXT NOT NULL,      -- 'comment_drafted', 'meeting_attended', etc.
    entity_type TEXT NOT NULL,      -- 'event', 'issue', 'bill', 'official'
    entity_id TEXT NOT NULL,

    -- Context
    metadata TEXT,                  -- JSON object with action-specific data
    jurisdiction_id TEXT,
    topic TEXT,                     -- housing, transportation, etc.

    -- Timestamp
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_civic_history_user ON civic_history(user_id, created_at DESC);
CREATE INDEX idx_civic_history_action_type ON civic_history(action_type);
CREATE INDEX idx_civic_history_topic ON civic_history(topic);
CREATE INDEX idx_civic_history_jurisdiction ON civic_history(jurisdiction_id);
```

### 6.3 Inferred Interests Cache Table

```sql
CREATE TABLE inferred_interests (
    user_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    confidence_score REAL NOT NULL,  -- 0.0 to 1.0

    -- Metadata
    last_computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actions_analyzed INTEGER,        -- How many actions went into this inference

    PRIMARY KEY (user_id, topic),
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_inferred_interests_confidence ON inferred_interests(user_id, confidence_score DESC);
```

**Purpose**: Cache inference results to avoid recomputing on every request.

**Update Strategy**: Recompute when:
- User takes new action AND cache is >24 hours old
- User explicitly requests refresh
- Admin triggers batch recomputation (nightly job)

---

## Part 7: Migration Path

### 7.1 Database Migration

**Migration Script: `migrations/006_personalization_service.sql`**

```sql
-- Create user_profiles table
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    stakes TEXT,
    years_in_area INTEGER,
    district TEXT,
    neighborhood TEXT,
    jurisdiction_id TEXT NOT NULL,
    expertise TEXT,
    civic_interests TEXT,
    topics_following TEXT,
    notification_preferences TEXT,
    privacy_settings TEXT,
    profile_completeness INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_profiles_jurisdiction ON user_profiles(jurisdiction_id);
CREATE INDEX idx_user_profiles_completeness ON user_profiles(profile_completeness);

-- Create civic_history table
CREATE TABLE civic_history (
    action_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    metadata TEXT,
    jurisdiction_id TEXT,
    topic TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_civic_history_user ON civic_history(user_id, created_at DESC);
CREATE INDEX idx_civic_history_action_type ON civic_history(action_type);
CREATE INDEX idx_civic_history_topic ON civic_history(topic);
CREATE INDEX idx_civic_history_jurisdiction ON civic_history(jurisdiction_id);

-- Create inferred_interests cache table
CREATE TABLE inferred_interests (
    user_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    last_computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actions_analyzed INTEGER,
    PRIMARY KEY (user_id, topic),
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_inferred_interests_confidence ON inferred_interests(user_id, confidence_score DESC);

-- Migrate existing comment personalContext to user_profiles
-- (Run after migration if you have existing comment data)
INSERT OR IGNORE INTO user_profiles (user_id, jurisdiction_id, stakes, years_in_area, district, neighborhood, expertise)
SELECT DISTINCT
    user_id,
    'city-berkeley' as jurisdiction_id,  -- Default, update manually
    json_extract(personal_context, '$.stakes') as stakes,
    json_extract(personal_context, '$.yearsInArea') as years_in_area,
    json_extract(personal_context, '$.district') as district,
    json_extract(personal_context, '$.neighborhood') as neighborhood,
    json_extract(personal_context, '$.expertise') as expertise
FROM comments
WHERE user_id IS NOT NULL AND personal_context IS NOT NULL;
```

### 7.2 Code Migration Checklist

**Phase 1: Add Service Infrastructure (Week 1)**
- [ ] Create `src/personalization_service.py` with base class
- [ ] Implement profile CRUD methods
- [ ] Implement civic history tracking
- [ ] Write unit tests for service methods
- [ ] Run database migration

**Phase 2: Integrate with API (Week 1)**
- [ ] Update `civic_api_integrated.py` to initialize PersonalizationService
- [ ] Add user authentication/token → user_id extraction
- [ ] Add profile endpoints (GET/POST/PATCH /api/users/:id/profile)
- [ ] Add civic history endpoint (GET /api/users/:id/history)
- [ ] Test new endpoints

**Phase 3: Refactor Comment Drafting (Week 2)**
- [ ] Update `/api/events/:id/draft-comment` to use service
- [ ] Add backward compatibility for legacy clients
- [ ] Track comment drafting actions to civic_history
- [ ] Update frontend to use profile-based context
- [ ] Test end-to-end flow

**Phase 4: Behavioral Inference (Week 2)**
- [ ] Implement interest inference algorithm
- [ ] Implement expertise inference
- [ ] Implement jurisdiction affinity
- [ ] Add inference cache table updates
- [ ] Test inference accuracy with sample data

**Phase 5: Action Personalization (Week 3)**
- [ ] Implement `personalize_actions()` ranking
- [ ] Implement `recommend_events()` scoring
- [ ] Add personalization to event list endpoint
- [ ] Update frontend to show personalized recommendations
- [ ] A/B test personalized vs non-personalized

---

## Part 8: API Endpoints (New)

**Authentication**: All endpoints require Bearer token. User ID extracted from token.

### POST /api/user/profile

Create or update user profile.

**Request:**
```json
{
  "displayName": "Jane Doe",
  "stakes": ["homeowner", "parent"],
  "yearsInArea": 15,
  "district": "District 3",
  "neighborhood": "Rockridge",
  "jurisdictionId": "city-berkeley",
  "expertise": "Urban planning",
  "civicInterests": ["housing", "transportation"],
  "notificationPreferences": {
    "email": true,
    "sms": false,
    "frequency": "weekly"
  },
  "privacySettings": {
    "profileVisibility": "public",
    "showCivicHistory": true,
    "allowBehavioralInference": true
  }
}
```

**Response:**
```json
{
  "userId": "user-abc123",
  "profileCompleteness": 85,
  "createdAt": "2025-10-29T10:00:00Z",
  "updatedAt": "2025-10-29T10:00:00Z"
}
```

### GET /api/user/profile

Get user profile with completeness suggestions.

**Response:**
```json
{
  "profile": {
    "userId": "user-abc123",
    "displayName": "Jane Doe",
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "neighborhood": "Rockridge",
    "civicInterests": ["housing"],
    "profileCompleteness": 65
  },
  "suggestions": [
    {
      "field": "expertise",
      "benefit": "Improves AI comment quality by 40%"
    },
    {
      "field": "civicInterests",
      "benefit": "Get 2x more relevant meeting recommendations"
    }
  ]
}
```

### GET /api/user/civic-history

Get user's civic action history.

**Query Params:**
- `action_types`: Comma-separated list of action types
- `since`: ISO timestamp (default: 90 days ago)
- `limit`: Number of results (default: 100)

**Response:**
```json
{
  "actions": [
    {
      "actionId": "action-123",
      "actionType": "comment_drafted",
      "entityType": "event",
      "entityId": "event-berkeley-planning-2025-11-15",
      "metadata": {
        "position": "oppose",
        "topic": "housing"
      },
      "createdAt": "2025-10-28T14:30:00Z"
    }
  ],
  "metadata": {
    "total_actions": 47,
    "date_range": {
      "start": "2025-07-30T00:00:00Z",
      "end": "2025-10-29T00:00:00Z"
    }
  }
}
```

### GET /api/user/civic-metrics

Get aggregated civic impact metrics.

**Response:**
```json
{
  "engagementTier": "participant",
  "totalActions": 47,
  "actionsLast30Days": 12,
  "commentsDrafted": 8,
  "issuesFiled": 3,
  "meetingsAttended": 2,
  "topicBreakdown": {
    "housing": 28,
    "transportation": 12,
    "environment": 7
  },
  "currentStreak": 5,
  "longestStreak": 12
}
```

### GET /api/user/inferred-interests

Get inferred civic interests from behavior.

**Response:**
```json
{
  "interests": {
    "housing": 0.92,
    "transportation": 0.45,
    "environment": 0.12
  },
  "inferredExpertise": "Housing/Urban Planning",
  "jurisdictionAffinity": ["city-berkeley", "city-oakland"],
  "confidence": "high",
  "actionsAnalyzed": 47,
  "lastComputedAt": "2025-10-29T08:00:00Z"
}
```

---

## Part 9: Privacy & Ethics

### 9.1 Privacy Principles

**1. User Control**
- Profile visibility settings (public, connections-only, private)
- Option to disable behavioral inference
- Opt-out of civic history tracking
- Data export and deletion on request

**2. Transparency**
- Show users what data is collected
- Explain how inference works ("We noticed you've engaged with 5 housing events")
- Display confidence scores ("85% confident you're interested in housing")
- Allow users to correct inferences

**3. Anonymization**
- Civic history can be anonymized for privacy-conscious users
- Aggregated stats don't reveal individual identities
- No third-party data sharing without explicit consent

### 9.2 Ethical Inference

**Avoid Bias:**
- Don't assume demographics from behavior (e.g., housing interest ≠ homeowner)
- Don't reinforce filter bubbles (show diverse topics even if not inferred interest)
- Don't penalize infrequent users (engagement tier is descriptive, not prescriptive)

**Bias Mitigation:**
- Always show at least 20% content outside inferred interests
- Randomize recommendations to expose users to new topics
- Don't use inference for gatekeeping (all users can access all features)

---

## Part 10: Performance Considerations

### 10.1 Caching Strategy

**Profile Data:**
- Cache in-memory per session (avoid DB hits)
- Invalidate on profile update
- TTL: Session duration

**Inferred Interests:**
- Cache in `inferred_interests` table
- Recompute asynchronously when stale (>24 hours)
- Don't block requests on inference computation

**Civic Metrics:**
- Cache for 1 hour
- Compute on-demand with optimized queries
- Use materialized view if queries become slow

### 10.2 Query Optimization

**Civic History Queries:**
```sql
-- Optimized query for topic breakdown
SELECT
    json_extract(metadata, '$.topic') as topic,
    COUNT(*) as count
FROM civic_history
WHERE user_id = ? AND created_at > datetime('now', '-90 days')
GROUP BY topic
ORDER BY count DESC;

-- Use indexes:
CREATE INDEX idx_civic_history_user_date ON civic_history(user_id, created_at DESC);
```

**Profile Completeness:**
```sql
-- Compute only on profile update, store in user_profiles.profile_completeness
-- Avoid recomputing on every read
```

---

## Part 11: Testing Strategy

### 11.1 Unit Tests

```python
# tests/test_personalization_service.py

def test_profile_creation():
    service = PersonalizationService(':memory:')
    profile = service.create_user_profile('test_user', {
        'stakes': ['homeowner'],
        'jurisdictionId': 'city-berkeley'
    })
    assert profile['profileCompleteness'] > 0

def test_interest_inference():
    service = PersonalizationService(':memory:')

    # Simulate user actions
    for i in range(10):
        service.track_action('test_user', 'event_clicked', 'event', f'event-{i}',
                            metadata={'topic': 'housing'})

    interests = service.infer_civic_interests('test_user')
    assert 'housing' in interests
    assert interests['housing'] > 0.5

def test_context_for_ai():
    service = PersonalizationService(':memory:')
    service.create_user_profile('test_user', {
        'stakes': ['homeowner', 'parent'],
        'yearsInArea': 15,
        'expertise': 'Urban planner'
    })

    context = service.get_context_for_ai('test_user', 'demographics')
    assert 'stakes' in context
    assert len(context['stakes']) == 2
```

### 11.2 Integration Tests

```python
def test_comment_drafting_with_profile():
    # Create profile
    create_profile_response = client.post('/api/users/test_user/profile', json={
        'stakes': ['homeowner'],
        'yearsInArea': 10,
        'jurisdictionId': 'city-berkeley'
    })

    # Draft comment without passing personalContext
    draft_response = client.post('/api/events/event-123/draft-comment', json={
        'position': 'oppose',
        'keyConcern': 'Traffic concerns'
    }, headers={'Authorization': 'Bearer test_token'})

    # Should use profile context
    assert draft_response.status_code == 200
    assert 'homeowner' in draft_response.json['draft'].lower()
```

---

## Part 12: Documentation Updates Required

### Update COMMENT_DRAFTING_ARCHITECTURE.md
- Part 2.1: Reference user_profiles table
- Part 9.1: Change endpoint to accept user_id instead of personalContext
- Add migration section

### Update ACTION_ORIENTATION_STRATEGY.md
- Part 6: Action Quality Tiers - integrate with civic_history tracking
- Add personalization of action recommendations

### Update API_DOCUMENTATION.md
- Add new user profile endpoints
- Update comment drafting endpoint spec
- Add civic history endpoints

### Update CLAUDE.md
- Add PersonalizationService to architecture overview
- Update files list with new service
- Update development workflow

### Create PERSONALIZATION_UX_GUIDE.md
- Profile onboarding flow
- Profile completeness incentives
- Inference transparency UI
- Privacy settings interface

---

## Part 13: Implementation Roadmap

### Week 1: Foundation (Service + Database)
**Mon-Tue: Database Schema**
- [ ] Write migration script `006_personalization_service.sql`
- [ ] Test migration on development database
- [ ] Verify indexes created correctly

**Wed-Fri: PersonalizationService Class**
- [ ] Create `src/personalization_service.py`
- [ ] Implement profile CRUD methods
- [ ] Implement civic history tracking
- [ ] Write unit tests (80% coverage target)

### Week 2: API Integration + Refactoring
**Mon-Tue: API Endpoints**
- [ ] Add profile endpoints to `civic_api_integrated.py`
- [ ] Add civic history endpoints
- [ ] Add user authentication extraction (Bearer token → user_id)
- [ ] Test with Postman/curl

**Wed-Thu: Comment Drafting Refactor**
- [ ] Update `/api/events/:id/draft-comment` to use PersonalizationService
- [ ] Add backward compatibility for legacy clients
- [ ] Track comment actions to civic_history
- [ ] Test end-to-end flow

**Fri: Documentation**
- [ ] Update API_DOCUMENTATION.md with new endpoints
- [ ] Update COMMENT_DRAFTING_ARCHITECTURE.md
- [ ] Write integration test suite

### Week 3: Inference + Personalization
**Mon-Tue: Behavioral Inference**
- [ ] Implement interest inference algorithm
- [ ] Implement expertise inference
- [ ] Implement jurisdiction affinity
- [ ] Test with sample user data

**Wed-Thu: Action Personalization**
- [ ] Implement `recommend_events()` scoring
- [ ] Implement `personalize_actions()` ranking
- [ ] Add personalization to event list endpoint
- [ ] Create `/api/users/:id/recommended-events` endpoint

**Fri: Testing + Optimization**
- [ ] Profile query performance testing
- [ ] Add caching for inferred interests
- [ ] Load testing with 1000 sample users
- [ ] Document performance characteristics

### Week 4: Frontend Integration
**Mon-Tue: Profile UI**
- [ ] Create `UserProfileForm.vue` component
- [ ] Add profile completeness indicator
- [ ] Add profile settings page
- [ ] Integrate with Pinia user store

**Wed-Thu: Comment Drafting Update**
- [ ] Update `CommentDraftArtifact.vue` to use profile
- [ ] Remove embedded personalContext form
- [ ] Add "Update Profile" link if incomplete
- [ ] Test UX flow

**Fri: QA + Launch Prep**
- [ ] Full E2E testing
- [ ] Privacy policy review
- [ ] Performance validation
- [ ] Deployment checklist

---

## Success Metrics

### Technical Metrics
- **Profile Adoption**: 60%+ of active users create profiles within 30 days
- **Profile Completeness**: Average completeness >50%
- **API Performance**: Profile queries <50ms p95
- **Inference Accuracy**: 70%+ users confirm inferred interests are correct

### UX Metrics
- **Context Reuse**: 80%+ of comment drafts use profile context (vs manual entry)
- **Recommendation CTR**: 25%+ click-through on personalized event recommendations
- **Engagement Lift**: 30%+ increase in civic actions for users with profiles

### Business Metrics
- **Time to Action**: 40% reduction in time from signup to first civic action
- **Retention**: 2x retention for users with complete profiles vs incomplete
- **NPS**: +20 point NPS increase with personalization vs without

---

## Appendix A: Example User Journeys

### Journey 1: New User → First Comment

**Step 1: Sign Up**
```
User creates account → user_id generated
Profile created with defaults:
- jurisdictionId: inferred from IP
- profileCompleteness: 20% (just user_id + jurisdiction)
```

**Step 2: Browse Events**
```
User clicks 3 housing events → Actions tracked:
- civic_history: 3 x 'event_clicked' with topic='housing'
```

**Step 3: Draft First Comment**
```
User clicks "Draft Comment" on housing event
→ Profile incomplete, show quick form:
  "Complete your profile for better AI comments"
  [ ] Homeowner [ ] Renter [ ] Parent
  Years in area: [___]

User fills out → Profile updated
→ AI generates comment using profile context
→ civic_history: 'comment_drafted' tracked
```

**Result:**
- Profile completeness: 60%
- Inferred interest in housing: 1.0 (high confidence)
- Next time: profile pre-filled, faster drafting

### Journey 2: Active User → Personalized Recommendations

**User Background:**
- 47 civic actions over 3 months
- 28 housing interactions, 12 transportation, 7 environment
- Attended 2 meetings, drafted 8 comments, filed 3 issues

**Personalization Applied:**
```
GET /api/users/jane_doe/recommended-events

Response:
[
  {
    "eventId": "event-123",
    "title": "Housing Element Update",
    "recommendationScore": 0.92,
    "matchReasons": [
      "Housing (your top interest - 28 interactions)",
      "Berkeley (your primary jurisdiction)",
      "Meeting (you've attended 2 similar meetings)"
    ]
  },
  {
    "eventId": "event-456",
    "title": "Transit-Oriented Development",
    "recommendationScore": 0.67,
    "matchReasons": [
      "Housing + Transportation (both your interests)",
      "Oakland (adjacent jurisdiction - you've engaged there 5x)"
    ]
  }
]
```

**Result:**
- User sees most relevant events first
- Click-through rate 3x higher than non-personalized
- Time to civic action reduced by 50%

---

## Appendix B: Privacy Scenario Examples

### Scenario 1: Privacy-Conscious User

**User Settings:**
```json
{
  "privacySettings": {
    "profileVisibility": "private",
    "showCivicHistory": false,
    "allowBehavioralInference": false
  }
}
```

**Implications:**
- Profile not visible to other users
- Civic history not shown in public timeline
- No interest inference (must select manually)
- Can still use all features, just without personalization

### Scenario 2: Public Advocate

**User Settings:**
```json
{
  "privacySettings": {
    "profileVisibility": "public",
    "showCivicHistory": true,
    "allowBehavioralInference": true
  }
}
```

**Implications:**
- Profile visible to community
- Civic history shows "47 actions, 8 comments, 2 meetings attended"
- Inference enabled for best personalization
- Can showcase civic impact publicly

---

## Appendix C: Algorithm Tuning

### Interest Inference Weight Calibration

**Default Weights:**
```python
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
```

**Tuning Process:**
1. Collect ground truth: Survey users about actual interests
2. Compare inferred interests to self-reported
3. Adjust weights to maximize correlation
4. Iterate until >70% accuracy

**A/B Testing:**
- Variant A: Current weights
- Variant B: Adjusted weights
- Metric: User confirmation rate of inferred interests

---

## Conclusion

The Personalization Service provides a **robust, extensible foundation** for all future civic features requiring user context. By centralizing profile management, civic history tracking, and behavioral inference, we avoid technical debt from per-feature context collection and create a scalable architecture for personalized civic engagement.

**Next Steps:**
1. Review this document with team
2. Approve database schema
3. Begin Week 1 implementation (service + database)
4. Update dependent documentation (COMMENT_DRAFTING, API_DOCS, etc.)

**Document Status**: Ready for Implementation
**Estimated Effort**: 3-4 weeks (1 backend developer)
**Dependencies**: None (incremental addition, no breaking changes)
