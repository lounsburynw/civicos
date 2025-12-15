"""
Issue storage and retrieval with SQLite.

Phase 1: Basic CRUD + event matching
Phase 2: Clustering queries + community formation
Phase 3: AI-generated titles and summaries
"""

import sqlite3
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path
from openai import OpenAI

from ..interfaces.participation_mechanism import ParticipationMechanism

DB_PATH = Path("data/civic_participation.db")

def generate_ai_title_and_summary(description: str, issue_type: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Generate AI title, summary, and short name from issue description.

    Args:
        description: Full issue description
        issue_type: Optional issue type for context

    Returns:
        Tuple of (ai_title, ai_summary, short_name_keyword)
    """
    try:
        from config import config
        openai_config = config.get_openai_config()
        client = OpenAI(api_key=openai_config['api_key'])

        issue_type_context = f" (Category: {issue_type})" if issue_type else ""

        prompt = f"""You are analyzing a civic issue report{issue_type_context}.

Issue Description:
{description}

Generate:
1. A concise, clear title (5-10 words max) that captures the core issue
2. A bullet-point summary (2-4 bullets) capturing:
   • The core problem in plain language
   • Location/context if mentioned
   • What help or action is needed
   • Any time-sensitive details
3. A short keyword identifier (1-2 words, max 12 chars, uppercase, no spaces):
   • Use the most distinctive aspect (e.g., "EVICTION", "POTHOLE", "NOISE")
   • Must be memorable and specific to this issue type
   • Examples: "EVICTION", "SIDEWALK", "TRANSIT", "PARKING"

Keep bullets brief (under 20 words each). Focus on critical facts only.

Format your response as JSON:
{{
  "title": "Your title here",
  "summary": "• First key point\\n• Second key point\\n• Third key point",
  "short_name": "KEYWORD"
}}"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes civic issues clearly and concisely."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return result.get("title", ""), result.get("summary", ""), result.get("short_name", "ISSUE")

    except Exception as e:
        print(f"[AI Generation] Error generating title/summary: {e}")
        # Fallback: Use first 50 chars as title, full description as summary, generic short_name
        fallback_title = description[:50] + "..." if len(description) > 50 else description
        return fallback_title, description, "ISSUE"

class IssueStorage:
    """CRUD interface for issues"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def create_issue(
        self,
        user_id: str,
        description: str,
        jurisdiction_id: str,
        issue_type: Optional[str] = None,
        location: Optional[Dict] = None
    ) -> str:
        """
        Create new issue with AI-generated title and summary.

        Args:
            user_id: User filing issue
            description: Issue text (max 2000 chars)
            jurisdiction_id: City/county identifier
            issue_type: Category (housing, transportation, etc.)
            location: {"address": str, "latitude": float, "longitude": float}

        Returns:
            issue_id (uuid)
        """
        import uuid
        issue_id = str(uuid.uuid4())

        # Generate AI title, summary, and short_name keyword
        ai_title, ai_summary, short_name_keyword = generate_ai_title_and_summary(description, issue_type)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get next number for this keyword prefix
            cursor.execute("""
                SELECT COALESCE(MAX(short_name_number), 0) + 1
                FROM issues
                WHERE short_name_keyword = ?
            """, (short_name_keyword,))
            short_name_number = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO issues (
                    id, user_id, description, jurisdiction_id, issue_type,
                    address, latitude, longitude, status,
                    ai_title, ai_summary, ai_generated_at,
                    short_name_keyword, short_name_number,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, CURRENT_TIMESTAMP, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                issue_id,
                user_id,
                description[:2000],  # Enforce limit
                jurisdiction_id,
                issue_type,
                location.get("address") if location else None,
                location.get("latitude") if location else None,
                location.get("longitude") if location else None,
                ai_title,
                ai_summary,
                short_name_keyword,
                short_name_number
            ))

            # Track as civic action (disabled - table not in production)
            # TODO: Re-enable when civic_actions tracking is implemented
            # cursor.execute("""
            #     INSERT INTO civic_actions (
            #         id, user_id, event_type, opportunity_id, jurisdiction_id,
            #         timestamp, completion_status, metadata
            #     ) VALUES (?, ?, 'complaint_submit', ?, ?, CURRENT_TIMESTAMP, 'completed', ?)
            # """, (
            #     str(uuid.uuid4()),
            #     user_id,
            #     issue_id,
            #     jurisdiction_id,
            #     json.dumps({"issue_type": issue_type})
            # ))

            # Create initial timeline entry
            cursor.execute("""
                INSERT INTO issue_timeline (
                    entry_id, issue_id, event_type, description, source
                ) VALUES (?, ?, 'filed', 'Issue filed', 'user')
            """, (str(uuid.uuid4()), issue_id))

            conn.commit()

        return issue_id

    def get_issue(self, issue_id: str) -> Optional[Dict]:
        """Retrieve issue by ID with all related data"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM issues WHERE id = ?", (issue_id,))
            row = cursor.fetchone()

            if not row:
                return None

            issue = dict(row)

            # Load matched events (sort automatic matches first, manual links last)
            cursor.execute("""
                SELECT event_id, match_score, match_reason
                FROM issue_event_matches
                WHERE issue_id = ?
                ORDER BY
                    CASE WHEN match_score IS NULL THEN 1 ELSE 0 END,
                    match_score DESC
            """, (issue_id,))
            issue["matched_events"] = [
                {
                    "event_id": r[0],
                    "match_score": r[1],
                    "match_reason": r[2]
                }
                for r in cursor.fetchall()
            ]

            # Find similar issues (for related_complaints field)
            if issue.get('issue_type'):
                similar = self.find_similar_issues(
                    issue['jurisdiction_id'],
                    issue['issue_type']
                )
                # Exclude the current issue from related list
                issue["related_complaints"] = [
                    c['id'] for c in similar if c['id'] != issue['id']
                ]
            else:
                issue["related_complaints"] = []

            # Discussion group ID (Phase 2 feature - not yet implemented)
            issue["discussion_group_id"] = None

            return issue

    def link_to_event(
        self,
        issue_id: str,
        event_id: str,
        match_score: Optional[float] = None,
        match_reason: Optional[str] = None
    ) -> None:
        """
        Link issue to event.

        Args:
            issue_id: Issue ID
            event_id: Event ID
            match_score: Match confidence (0-100). None for manual links.
            match_reason: Reason for match. None for manual links.
        """
        import uuid
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            match_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT OR REPLACE INTO issue_event_matches
                (match_id, issue_id, event_id, match_score, match_reason)
                VALUES (?, ?, ?, ?, ?)
            """, (match_id, issue_id, event_id, match_score, match_reason))

            # Note: We no longer auto-update status to 'matched'
            # Connection status is computed from matched_events.length > 0
            # Issue status is purely lifecycle: open | closed (with optional closed_reason)

            # Create timeline entry (different for manual vs automatic)
            if match_score is None:
                # Manual link
                description = "Manually linked to event"
                event_type = 'linked'
                source = 'user'
            else:
                # Automatic match
                description = f"Matched to event ({int(match_score)}% match)"
                event_type = 'matched'
                source = 'system'

            cursor.execute("""
                INSERT INTO issue_timeline (
                    entry_id, issue_id, event_type, description, source, metadata
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), issue_id, event_type, description, source, json.dumps({"event_id": event_id, "match_score": match_score})))

            conn.commit()

    def get_user_complaints(self, user_id: str) -> List[Dict]:
        """
        Retrieve all issues for a user with matched events.

        Args:
            user_id: User identifier

        Returns:
            List of issues with matched_events included
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all issues for user
            cursor.execute("""
                SELECT * FROM issues
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))

            issues = []
            for row in cursor.fetchall():
                issue = dict(row)

                # Load matched events for this issue (sort automatic matches first, manual links last)
                cursor.execute("""
                    SELECT event_id, match_score, match_reason
                    FROM issue_event_matches
                    WHERE issue_id = ?
                    ORDER BY
                        CASE WHEN match_score IS NULL THEN 1 ELSE 0 END,
                        match_score DESC
                """, (issue['id'],))

                issue["matched_events"] = [
                    {
                        "event_id": r[0],
                        "match_score": r[1],
                        "match_reason": r[2]
                    }
                    for r in cursor.fetchall()
                ]

                # Find similar issues (for related_complaints field)
                if issue.get('issue_type'):
                    similar = self.find_similar_issues(
                        issue['jurisdiction_id'],
                        issue['issue_type']
                    )
                    # Exclude the current issue AND issues from the same user
                    # "Neighbors" should be OTHER USERS with similar issues
                    issue["related_complaints"] = [
                        c['id'] for c in similar
                        if c['id'] != issue['id'] and c['user_id'] != issue['user_id']
                    ]
                else:
                    issue["related_complaints"] = []

                # Discussion group ID (Phase 2 feature - not yet implemented)
                issue["discussion_group_id"] = None

                issues.append(issue)

            return issues

    def find_similar_issues(
        self,
        jurisdiction_id: str,
        issue_type: str,
        location: Optional[Dict] = None,
        radius_km: float = 5.0
    ) -> List[Dict]:
        """
        Find similar issues for clustering.

        Phase 1: Basic issue_type + jurisdiction matching
        Phase 2: Add geographic clustering with Haversine distance
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Phase 1: Simple query
            # Note: Only open issues appear in similar issues (closed issues are excluded)
            cursor.execute("""
                SELECT * FROM issues
                WHERE jurisdiction_id = ?
                  AND issue_type = ?
                  AND status = 'open'
                  AND created_at >= datetime('now', '-30 days')
                ORDER BY created_at DESC
                LIMIT 20
            """, (jurisdiction_id, issue_type))

            return [dict(row) for row in cursor.fetchall()]

    def update_status(
        self,
        issue_id: str,
        new_status: str,
        note: Optional[str] = None,
        closed_reason: Optional[str] = None
    ) -> None:
        """
        Update issue lifecycle status and create timeline entry.

        Args:
            issue_id: Issue ID
            new_status: 'open' or 'closed'
            note: Optional note about the status change
            closed_reason: Required if new_status='closed', one of:
                'resolved', 'duplicate', 'not-actionable', 'abandoned'
        """
        import uuid

        # Validate closed_reason for closed status
        if new_status == 'closed':
            if not closed_reason:
                raise ValueError("closed_reason is required when status is 'closed'")
            if closed_reason not in ['resolved', 'duplicate', 'not-actionable', 'abandoned']:
                raise ValueError(f"Invalid closed_reason: {closed_reason}")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if new_status == 'closed':
                # Set closed fields
                cursor.execute("""
                    UPDATE issues
                    SET status = ?,
                        closed_reason = ?,
                        closed_at = CURRENT_TIMESTAMP,
                        closed_note = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_status, closed_reason, note, issue_id))
            else:
                # Reopening: clear closed fields
                cursor.execute("""
                    UPDATE issues
                    SET status = ?,
                        closed_reason = NULL,
                        closed_at = NULL,
                        closed_note = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_status, issue_id))

            # Create timeline entry for status change
            if new_status == 'closed':
                # Always show closure reason, append note if provided
                description = f"Issue closed as {closed_reason}"
                if note:
                    description += f"\n{note}"
            else:
                # Reopening
                description = "Issue reopened"
                if note:
                    description += f"\n{note}"

            cursor.execute("""
                INSERT INTO issue_timeline (
                    entry_id, issue_id, event_type, description, source
                ) VALUES (?, ?, 'status_change', ?, 'user')
            """, (str(uuid.uuid4()), issue_id, description))

            conn.commit()

    def create_timeline_entry(
        self,
        issue_id: str,
        event_type: str,
        description: str,
        source: str = 'system',
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Create a timeline entry for a issue.

        Args:
            issue_id: Issue ID
            event_type: 'filed', 'matched', 'linked', 'status_change', 'response', 'action_taken'
            description: Human-readable description
            source: 'user', 'system', or 'admin'
            metadata: Optional JSON metadata

        Returns:
            entry_id (uuid)
        """
        import uuid
        entry_id = str(uuid.uuid4())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO issue_timeline (
                    entry_id, issue_id, event_type, description, source, metadata
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                entry_id,
                issue_id,
                event_type,
                description,
                source,
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()

        return entry_id

    def add_timeline_entry(
        self,
        issue_id: str,
        event_type: str,
        description: str,
        source: str = 'system',
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Add an entry to issue timeline.

        Args:
            issue_id: ID of issue
            event_type: Type of event (filed, matched, linked, status_change, response, action_taken)
            description: Human-readable description
            source: Source of entry (user, system, admin)
            metadata: Optional JSON metadata

        Returns:
            entry_id (uuid)
        """
        import uuid
        entry_id = str(uuid.uuid4())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO issue_timeline (
                    entry_id, issue_id, event_type, description, source, metadata, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                entry_id,
                issue_id,
                event_type,
                description,
                source,
                json.dumps(metadata) if metadata else None
            ))

        return entry_id

    def get_issue_timeline(self, issue_id: str) -> List[Dict]:
        """
        Retrieve timeline for a issue.

        Returns:
            List of timeline entries ordered by timestamp

        Note:
            Excludes 'filed', 'matched', and 'linked' events as these represent
            discovery/navigation, not government responses. Only returns events
            that represent government engagement (status_change, response, action_taken).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    entry_id,
                    issue_id,
                    timestamp,
                    event_type,
                    description,
                    source,
                    metadata
                FROM issue_timeline
                WHERE issue_id = ?
                    AND event_type NOT IN ('filed', 'matched', 'linked')
                ORDER BY timestamp ASC
            """, (issue_id,))

            entries = []
            for row in cursor.fetchall():
                entry = dict(row)
                # Parse metadata JSON if present
                if entry.get('metadata'):
                    entry['metadata'] = json.loads(entry['metadata'])
                entries.append(entry)

            return entries

    def get_issue_status_history(self, issue_id: str) -> List[Dict]:
        """
        Retrieve status history for an issue (filed + status changes only).

        This is distinct from get_issue_timeline which filters for government
        responses. Status history shows the user's issue lifecycle.

        Returns:
            List of timeline entries (filed, status_change) ordered by timestamp
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    entry_id,
                    issue_id,
                    timestamp,
                    event_type,
                    description,
                    source,
                    metadata
                FROM issue_timeline
                WHERE issue_id = ?
                    AND event_type IN ('filed', 'status_change')
                ORDER BY timestamp ASC
            """, (issue_id,))

            entries = []
            for row in cursor.fetchall():
                entry = dict(row)
                # Parse metadata JSON if present
                if entry.get('metadata'):
                    entry['metadata'] = json.loads(entry['metadata'])
                entries.append(entry)

            return entries


class Issue(ParticipationMechanism):
    """
    Issue focal point implementing ParticipationMechanism interface.

    Enables unified handling alongside CivicEvent.

    Note: Issue status is purely lifecycle-based (open | closed with closed_reason).
    Connection status (has_matches) is computed from matched_events.length > 0.
    """

    def __init__(self, complaint_data: Dict):
        self.data = complaint_data
        self.storage = IssueStorage()

    def get_id(self) -> str:
        return self.data["id"]

    def get_type(self) -> str:
        return "Issue"

    def get_actions(self) -> List[Dict]:
        """
        Actions available for issue.

        Phase 1: View matched events
        Phase 2: Join discussion, escalate to proposal
        """
        actions = []

        # If matched to events, show "View Meeting" actions
        for event_ref in self.data.get("matched_events", []):
            actions.append({
                "action_type": "link",
                "action_label": f"View Meeting (Match: {event_ref['match_score']:.0f}%)",
                "action_target": f"/events/{event_ref['event_id']}",
                "mcp_tool": "view_event_details"
            })

        # If no matches, show "Track Issue" action
        if not self.data.get("matched_events"):
            actions.append({
                "action_type": "button",
                "action_label": "Track This Issue",
                "action_target": "track_complaint",
                "mcp_tool": "track_issue"
            })

        return actions

    def get_context(self) -> Dict:
        """Multi-dimensional context for issue"""
        # Parse created_at timestamp (SQLite returns strings without timezone)
        created_at_str = self.data["created_at"]
        # Handle both with and without microseconds
        if '.' in created_at_str:
            created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S.%f")
        else:
            created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")

        days_open = max(0, (datetime.now() - created_at).days)

        return {
            "complaint_context": {
                "issue_type": self.data.get("issue_type"),
                "status": self.data.get("status"),
                "days_open": days_open
            },
            "community_context": {
                "related_complaints": len(self.data.get("related_complaints", [])),
                "organizing_potential": "high" if len(self.data.get("related_complaints", [])) >= 3 else "low"
            },
            "matched_events_count": len(self.data.get("matched_events", []))
        }

    def get_lifecycle_status(self) -> str:
        return self.data.get("status", "open")

    def get_participation_threshold(self) -> str:
        # Complaints are low-barrier entry point
        return "low"


class CommunityStorage:
    """
    Storage operations for Phase 2: Following system and coordination threads.

    Task 2: Following system (follows + coordination_threads)
    Task 3: In-app messaging (thread_messages)
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def create_follow(
        self,
        user_id: str,
        focal_type: str,
        focal_id: str,
        jurisdiction_id: Optional[str] = None
    ) -> Dict:
        """
        Create follow entry and auto-create coordination thread if needed.

        Args:
            user_id: User creating the follow
            focal_type: 'issue' or 'event'
            focal_id: ID of issue or event
            jurisdiction_id: Jurisdiction (optional)

        Returns:
            Dict with follower_count, thread_id, your_following=True
        """
        import uuid

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create follow entry (UNIQUE constraint prevents duplicates)
            follow_id = str(uuid.uuid4())
            try:
                cursor.execute("""
                    INSERT INTO follows (follow_id, user_id, focal_type, focal_id, jurisdiction_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (follow_id, user_id, focal_type, focal_id, jurisdiction_id))
            except sqlite3.IntegrityError:
                # Already following - just return current info
                pass

            # Get or create coordination thread
            thread_id = self._get_or_create_thread(cursor, focal_type, focal_id)

            # Get follower count
            cursor.execute("""
                SELECT COUNT(*) FROM follows
                WHERE focal_type = ? AND focal_id = ?
            """, (focal_type, focal_id))
            follower_count = cursor.fetchone()[0]

            conn.commit()

        return {
            "follower_count": follower_count,
            "thread_id": thread_id,
            "your_following": True
        }

    def get_follow_info(
        self,
        focal_type: str,
        focal_id: str,
        user_id: Optional[str] = None
    ) -> Dict:
        """
        Get follow info for a focal point.

        Args:
            focal_type: 'issue' or 'event'
            focal_id: ID of issue or event
            user_id: Optional user ID to check if they're following

        Returns:
            Dict with follower_count, thread_id, your_following
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get follower count
            cursor.execute("""
                SELECT COUNT(*) FROM follows
                WHERE focal_type = ? AND focal_id = ?
            """, (focal_type, focal_id))
            follower_count = cursor.fetchone()[0]

            # Get thread ID (may not exist yet)
            cursor.execute("""
                SELECT thread_id FROM coordination_threads
                WHERE focal_type = ? AND focal_id = ?
            """, (focal_type, focal_id))
            thread_row = cursor.fetchone()
            thread_id = thread_row[0] if thread_row else None

            # Check if user is following
            your_following = False
            if user_id:
                cursor.execute("""
                    SELECT COUNT(*) FROM follows
                    WHERE focal_type = ? AND focal_id = ? AND user_id = ?
                """, (focal_type, focal_id, user_id))
                your_following = cursor.fetchone()[0] > 0

        return {
            "follower_count": follower_count,
            "thread_id": thread_id,
            "your_following": your_following
        }

    def delete_follow(
        self,
        user_id: str,
        focal_type: str,
        focal_id: str
    ) -> Dict:
        """
        Remove follow entry (unfollow).

        Returns:
            Dict with updated follower_count
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Delete follow entry
            cursor.execute("""
                DELETE FROM follows
                WHERE user_id = ? AND focal_type = ? AND focal_id = ?
            """, (user_id, focal_type, focal_id))

            # Get updated follower count
            cursor.execute("""
                SELECT COUNT(*) FROM follows
                WHERE focal_type = ? AND focal_id = ?
            """, (focal_type, focal_id))
            follower_count = cursor.fetchone()[0]

            conn.commit()

        return {
            "follower_count": follower_count,
            "your_following": False
        }

    def _get_or_create_thread(
        self,
        cursor: sqlite3.Cursor,
        focal_type: str,
        focal_id: str
    ) -> str:
        """
        Get existing thread or create new one for focal point.

        Args:
            cursor: SQLite cursor (must be in transaction)
            focal_type: 'issue' or 'event'
            focal_id: ID of issue or event

        Returns:
            thread_id
        """
        import uuid

        # Check if thread exists
        cursor.execute("""
            SELECT thread_id FROM coordination_threads
            WHERE focal_type = ? AND focal_id = ?
        """, (focal_type, focal_id))
        row = cursor.fetchone()

        if row:
            return row[0]

        # Create new thread
        thread_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO coordination_threads (thread_id, focal_type, focal_id)
            VALUES (?, ?, ?)
        """, (thread_id, focal_type, focal_id))

        return thread_id

    def get_followers(
        self,
        focal_type: str,
        focal_id: str
    ) -> List[Dict]:
        """
        Get list of users following a focal point.

        Returns:
            List of follower dicts with user_id, created_at
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT user_id, created_at
                FROM follows
                WHERE focal_type = ? AND focal_id = ?
                ORDER BY created_at ASC
            """, (focal_type, focal_id))

            return [dict(row) for row in cursor.fetchall()]

    def get_user_follows(self, user_id: str) -> List[Dict]:
        """
        Get all things a user is following (issues and events).

        Args:
            user_id: User ID

        Returns:
            List of follow dicts with focal_type, focal_id, jurisdiction_id, created_at
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT focal_type, focal_id, jurisdiction_id, created_at
                FROM follows
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))

            return [dict(row) for row in cursor.fetchall()]

    # Task 3: Thread Messaging Methods

    def create_message(
        self,
        thread_id: str,
        user_id: str,
        content: str,
        parent_message_id: Optional[str] = None
    ) -> Dict:
        """
        Create a new message in a coordination thread.

        Args:
            thread_id: Coordination thread ID
            user_id: User sending message
            content: Message text (max 1000 chars)
            parent_message_id: Optional ID of parent message for nested replies

        Returns:
            Dict with message_id, thread_id, user_id, content, created_at, parent_message_id, reply_count
        """
        import uuid

        # Enforce content length limit
        content = content[:1000]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Create message
            message_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO thread_messages (message_id, thread_id, user_id, content, parent_message_id)
                VALUES (?, ?, ?, ?, ?)
            """, (message_id, thread_id, user_id, content, parent_message_id))

            # Note: reply_count is updated automatically by database trigger

            # Update thread last_message_at
            cursor.execute("""
                UPDATE coordination_threads
                SET last_message_at = CURRENT_TIMESTAMP
                WHERE thread_id = ?
            """, (thread_id,))

            # Retrieve the created message
            cursor.execute("""
                SELECT message_id, thread_id, user_id, content, created_at, parent_message_id, reply_count
                FROM thread_messages
                WHERE message_id = ?
            """, (message_id,))

            conn.commit()

            return dict(cursor.fetchone())

    def get_thread_messages(
        self,
        thread_id: str,
        before: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get messages for a thread with timestamp-based pagination.

        Args:
            thread_id: Coordination thread ID
            before: ISO timestamp cursor (get messages before this time)
            limit: Max messages to return (default 50, max 100)

        Returns:
            List of message dicts ordered by created_at ASC (for nested rendering)
        """
        limit = min(limit, 100)  # Cap at 100

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if before:
                cursor.execute("""
                    SELECT message_id, thread_id, user_id, content, created_at, parent_message_id, reply_count
                    FROM thread_messages
                    WHERE thread_id = ? AND created_at < ?
                    ORDER BY created_at ASC
                    LIMIT ?
                """, (thread_id, before, limit))
            else:
                cursor.execute("""
                    SELECT message_id, thread_id, user_id, content, created_at, parent_message_id, reply_count
                    FROM thread_messages
                    WHERE thread_id = ?
                    ORDER BY created_at ASC
                    LIMIT ?
                """, (thread_id, limit))

            return [dict(row) for row in cursor.fetchall()]

    def get_thread_messages_nested(
        self,
        thread_id: str,
        before: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get messages for a thread with nested structure (replies as children).

        Args:
            thread_id: Coordination thread ID
            before: ISO timestamp cursor (get messages before this time)
            limit: Max messages to return (default 50, max 100)

        Returns:
            List of top-level message dicts with 'replies' field containing nested replies
        """
        # Get all messages (flat list)
        all_messages = self.get_thread_messages(thread_id, before, limit)

        # Build nested structure
        message_map = {}
        root_messages = []

        # First pass: create message map
        for msg in all_messages:
            msg['replies'] = []  # Initialize replies array
            message_map[msg['message_id']] = msg

        # Second pass: build tree structure
        for msg in all_messages:
            if msg['parent_message_id']:
                # This is a reply - add to parent's replies array
                parent = message_map.get(msg['parent_message_id'])
                if parent:
                    parent['replies'].append(msg)
            else:
                # This is a top-level message
                root_messages.append(msg)

        return root_messages

    def get_thread_participants(
        self,
        thread_id: str
    ) -> List[Dict]:
        """
        Get list of users participating in a thread (followers of the focal point).

        Args:
            thread_id: Coordination thread ID

        Returns:
            List of user dicts with user_id, joined_at
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get focal point from thread
            cursor.execute("""
                SELECT focal_type, focal_id
                FROM coordination_threads
                WHERE thread_id = ?
            """, (thread_id,))
            thread_row = cursor.fetchone()

            if not thread_row:
                return []

            focal_type = thread_row['focal_type']
            focal_id = thread_row['focal_id']

            # Get all followers (participants)
            cursor.execute("""
                SELECT user_id, created_at as joined_at
                FROM follows
                WHERE focal_type = ? AND focal_id = ?
                ORDER BY created_at ASC
            """, (focal_type, focal_id))

            return [dict(row) for row in cursor.fetchall()]

    def mark_thread_seen(
        self,
        user_id: str,
        focal_type: str,
        focal_id: str
    ) -> None:
        """
        Update last_seen_at timestamp for user's follow entry.

        Used to track unread messages.

        Args:
            user_id: User ID
            focal_type: 'issue' or 'event'
            focal_id: ID of issue or event
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE follows
                SET last_seen_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND focal_type = ? AND focal_id = ?
            """, (user_id, focal_type, focal_id))
            conn.commit()

    def get_unread_count(
        self,
        user_id: str,
        focal_type: str,
        focal_id: str
    ) -> int:
        """
        Get count of unread messages for a user in a thread.

        Args:
            user_id: User ID
            focal_type: 'issue' or 'event'
            focal_id: ID of issue or event

        Returns:
            Number of unread messages (0 if not following)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get user's last_seen_at timestamp
            cursor.execute("""
                SELECT last_seen_at
                FROM follows
                WHERE user_id = ? AND focal_type = ? AND focal_id = ?
            """, (user_id, focal_type, focal_id))
            follow_row = cursor.fetchone()

            if not follow_row:
                return 0  # Not following

            last_seen_at = follow_row[0]

            # Get thread_id
            cursor.execute("""
                SELECT thread_id
                FROM coordination_threads
                WHERE focal_type = ? AND focal_id = ?
            """, (focal_type, focal_id))
            thread_row = cursor.fetchone()

            if not thread_row:
                return 0  # No thread yet

            thread_id = thread_row[0]

            # Count messages since last_seen_at
            cursor.execute("""
                SELECT COUNT(*)
                FROM thread_messages
                WHERE thread_id = ? AND created_at > ?
            """, (thread_id, last_seen_at))

            return cursor.fetchone()[0]

    def get_all_threads(
        self,
        jurisdiction_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get all active coordination threads with metadata.

        Args:
            jurisdiction_id: Optional filter by jurisdiction
            limit: Max threads to return (default 50, max 100)

        Returns:
            List of thread dicts with focal_point info, participant_count, message_count, last_message_at
        """
        limit = min(limit, 100)  # Cap at 100

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build query with optional jurisdiction filter
            if jurisdiction_id:
                query = """
                    SELECT
                        ct.thread_id,
                        ct.focal_type,
                        ct.focal_id,
                        ct.created_at,
                        ct.last_message_at,
                        COUNT(DISTINCT f.user_id) as participant_count,
                        COUNT(DISTINCT tm.message_id) as message_count
                    FROM coordination_threads ct
                    LEFT JOIN follows f ON ct.focal_type = f.focal_type AND ct.focal_id = f.focal_id
                    LEFT JOIN thread_messages tm ON ct.thread_id = tm.thread_id
                    WHERE f.jurisdiction_id = ? OR f.jurisdiction_id IS NULL
                    GROUP BY ct.thread_id
                    ORDER BY ct.last_message_at DESC NULLS LAST, ct.created_at DESC
                    LIMIT ?
                """
                cursor.execute(query, (jurisdiction_id, limit))
            else:
                query = """
                    SELECT
                        ct.thread_id,
                        ct.focal_type,
                        ct.focal_id,
                        ct.created_at,
                        ct.last_message_at,
                        COUNT(DISTINCT f.user_id) as participant_count,
                        COUNT(DISTINCT tm.message_id) as message_count
                    FROM coordination_threads ct
                    LEFT JOIN follows f ON ct.focal_type = f.focal_type AND ct.focal_id = f.focal_id
                    LEFT JOIN thread_messages tm ON ct.thread_id = tm.thread_id
                    GROUP BY ct.thread_id
                    ORDER BY ct.last_message_at DESC NULLS LAST, ct.created_at DESC
                    LIMIT ?
                """
                cursor.execute(query, (limit,))

            return [dict(row) for row in cursor.fetchall()]

    def get_thread_info(
        self,
        thread_id: str
    ) -> Optional[Dict]:
        """
        Get thread metadata including focal point info, participants, and message count.

        Args:
            thread_id: Thread ID

        Returns:
            Dict with thread_id, focal_type, focal_id, participant_count, message_count, created_at, last_message_at
            None if thread doesn't exist
        """
        print(f"[CommunityStorage] Looking up thread info for ID: {thread_id}")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # First check if thread exists at all
            cursor.execute("""
                SELECT thread_id, focal_type, focal_id, created_at, last_message_at
                FROM coordination_threads
                WHERE thread_id = ?
            """, (thread_id,))
            thread_row = cursor.fetchone()
            print(f"[CommunityStorage] Raw thread row: {dict(thread_row) if thread_row else None}")

            cursor.execute("""
                SELECT
                    ct.thread_id,
                    ct.focal_type,
                    ct.focal_id,
                    ct.created_at,
                    ct.last_message_at,
                    COUNT(DISTINCT f.user_id) as participant_count,
                    COUNT(DISTINCT tm.message_id) as message_count
                FROM coordination_threads ct
                LEFT JOIN follows f ON ct.focal_type = f.focal_type AND ct.focal_id = f.focal_id
                LEFT JOIN thread_messages tm ON ct.thread_id = tm.thread_id
                WHERE ct.thread_id = ?
                GROUP BY ct.thread_id
            """, (thread_id,))

            row = cursor.fetchone()
            result = dict(row) if row else None
            print(f"[CommunityStorage] Query result: {result}")
            return result

    def get_threads_for_focal_point(self, focal_type: str, focal_id: str) -> List[Dict]:
        """
        Get all threads for a specific focal point.

        Args:
            focal_type: 'issue' or 'event'
            focal_id: ID of issue or event

        Returns:
            List of thread dicts with metadata
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
                SELECT
                    ct.thread_id,
                    ct.focal_type,
                    ct.focal_id,
                    ct.created_at,
                    ct.last_message_at,
                    COUNT(DISTINCT f.user_id) as participant_count,
                    COUNT(DISTINCT tm.message_id) as message_count
                FROM coordination_threads ct
                LEFT JOIN follows f ON ct.focal_type = f.focal_type AND ct.focal_id = f.focal_id
                LEFT JOIN thread_messages tm ON ct.thread_id = tm.thread_id
                WHERE ct.focal_type = ? AND ct.focal_id = ?
                GROUP BY ct.thread_id
            """

            cursor.execute(query, (focal_type, focal_id))
            return [dict(row) for row in cursor.fetchall()]

    def get_related_issues_for_event(self, event_id: str) -> List[Dict]:
        """
        Get all issues that are linked to an event (via issue_event_matches).

        Args:
            event_id: ID of the event

        Returns:
            List of issue dicts with: issue_id, description_preview,
            status, created_at, user_id
        """
        complaint_storage = IssueStorage()

        with sqlite3.connect(complaint_storage.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Query issue_event_matches table
            cursor.execute("""
                SELECT c.id as issue_id, c.description, c.status, c.created_at, c.user_id
                FROM issues c
                JOIN issue_event_matches cte ON c.id = cte.issue_id
                WHERE cte.event_id = ?
                ORDER BY c.created_at DESC
            """, (event_id,))

            issues = []
            for row in cursor.fetchall():
                issue = dict(row)
                # Truncate description to 80 chars
                desc = issue['description']
                issue['description_preview'] = desc[:80] + ('...' if len(desc) > 80 else '')
                issues.append(issue)

            return issues
