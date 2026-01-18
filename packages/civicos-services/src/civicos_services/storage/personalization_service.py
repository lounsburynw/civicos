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

    ⚠️  PRIVACY WARNING (2025-10-29):
    The civic_interests field is DEPRECATED and should NOT be used for storing
    political preferences. Political data now lives in browser localStorage as
    archetypes (Tier 1: Browser-Only Privacy).

    DO NOT store political values, civic interests, or swipe decisions in the database.
    These expose users to government subpoenas, data breaches, and political targeting.

    See: docs/PRIVACY_ARCHITECTURE.md for complete privacy design.
    Migration 007 removes civic_interests from the database schema.
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
            # Format to match SQLite's CURRENT_TIMESTAMP format (YYYY-MM-DD HH:MM:SS)
            # Note: SQLite CURRENT_TIMESTAMP uses UTC, caller should pass UTC datetime
            params.append(since.strftime('%Y-%m-%d %H:%M:%S'))

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
