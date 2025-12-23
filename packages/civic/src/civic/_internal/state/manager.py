"""
Unified City State Manager

Provides temporal versioning for civic data with SQLite backend.
Designed for standalone use or as part of the larger Civic Platform.

Key Features:
- Temporal versioning: Query state at any point in time
- Atomic updates: No partial state corruption
- Zero external dependencies (SQLite is stdlib)
- Clean separation from extraction logic

Usage:
    from civic_state import StateManager

    state_mgr = StateManager()  # Uses get_state_db_path()
    state_mgr.update_meetings("city-berkeley", meetings_list, as_of=datetime.now())
    state = state_mgr.get_city_state("city-berkeley")
    historical = state_mgr.get_city_state("city-berkeley", as_of=datetime(2024, 10, 6))
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import logging

from civic.paths import get_state_db_path

logger = logging.getLogger(__name__)


class StateManager:
    """
    Unified interface for city state management.

    Provides:
    - Single source of truth for all city data
    - Temporal versioning (query state at any point in time)
    - Atomic updates (no partial state corruption)
    - Clean separation from extraction logic
    """

    def __init__(self, db_path: str = None):
        """
        Initialize state manager.

        Args:
            db_path: Path to SQLite database (will be created if doesn't exist).
                     Defaults to get_state_db_path() which respects CIVIC_DATA_ROOT.
        """
        self.db_path = db_path or get_state_db_path()
        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self):
        """Create database schema if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # City states table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS city_states (
                jurisdiction_id TEXT PRIMARY KEY,
                jurisdiction_name TEXT NOT NULL,
                as_of TIMESTAMP NOT NULL,
                active_residents INTEGER DEFAULT 0,
                pending_comments INTEGER DEFAULT 0,
                coordination_threads INTEGER DEFAULT 0,
                completeness_score REAL DEFAULT 0.0,
                data_sources TEXT,  -- JSON array
                extraction_version TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Meetings table (with temporal versioning)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                title TEXT NOT NULL,
                meeting_datetime TIMESTAMP NOT NULL,
                meeting_type TEXT,
                status TEXT,
                location TEXT,
                virtual_url TEXT,
                agenda_url TEXT,
                minutes_url TEXT,
                video_url TEXT,
                comment_deadline TIMESTAMP,
                source_platform TEXT NOT NULL,
                source_url TEXT,
                last_verified TIMESTAMP,
                data_quality_score REAL,

                -- Temporal versioning
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,  -- NULL = current version

                -- Full meeting data (JSON blob for now, can normalize later)
                full_data TEXT,  -- JSON

                PRIMARY KEY (id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Agenda items table (with legislative enrichment)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agenda_items (
                id TEXT NOT NULL,
                meeting_id TEXT NOT NULL,
                item_number TEXT,
                title TEXT NOT NULL,
                description TEXT,
                project_type TEXT,
                actionability TEXT,
                impact_level TEXT,
                financial_impact_cents INTEGER,

                -- AI Analysis
                summary TEXT,
                why_it_matters TEXT,
                participation_guide TEXT,

                -- Community metrics
                comment_count INTEGER DEFAULT 0,
                following_count INTEGER DEFAULT 0,

                -- Legislative context (JSON arrays of IDs)
                relevant_bills TEXT,  -- JSON array
                federal_programs TEXT,  -- JSON array
                matched_complaints TEXT,  -- JSON array

                -- Timestamps
                extracted_at TIMESTAMP,
                enriched_at TIMESTAMP,

                -- Temporal versioning
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,

                -- Full item data
                full_data TEXT,  -- JSON

                PRIMARY KEY (id, valid_from),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meetings_jurisdiction ON meetings(jurisdiction_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meetings_datetime ON meetings(meeting_datetime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meetings_temporal ON meetings(jurisdiction_id, valid_from, valid_to)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meetings_current ON meetings(valid_to) WHERE valid_to IS NULL")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agenda_items_meeting ON agenda_items(meeting_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agenda_items_type ON agenda_items(project_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agenda_items_temporal ON agenda_items(valid_from, valid_to)")

        # Issues table (SeeClickFix complaints)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id TEXT PRIMARY KEY,
                jurisdiction_id TEXT NOT NULL,
                source TEXT NOT NULL,  -- seeclickfix, native
                source_id TEXT,
                title TEXT NOT NULL,
                description TEXT,
                issue_type TEXT,
                address TEXT,
                latitude REAL,
                longitude REAL,
                status TEXT DEFAULT 'open',
                closed_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Matching to agenda items
                matched_meetings TEXT,  -- JSON array
                matched_agenda_items TEXT,  -- JSON array
                match_score REAL,
                match_reason TEXT,

                -- Community metrics
                follower_count INTEGER DEFAULT 0,
                coordination_thread_id TEXT,

                -- Temporal versioning
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,

                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_jurisdiction ON issues(jurisdiction_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_type ON issues(issue_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_address ON issues(address)")

        # Initiatives table (user-spawned initiatives)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS initiatives (
                id TEXT PRIMARY KEY,
                jurisdiction_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                creator_id TEXT NOT NULL DEFAULT 'anonymous',
                location TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Community metrics
                supporter_count INTEGER DEFAULT 0,
                voice_count INTEGER DEFAULT 0,

                -- Linking to agenda items
                matched_agenda_items TEXT,  -- JSON array of item IDs

                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_jurisdiction ON initiatives(jurisdiction_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_topic ON initiatives(topic)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_status ON initiatives(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_creator ON initiatives(creator_id)")

        # Voices table (user voices on items)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                item_type TEXT NOT NULL,  -- 'initiative', 'agenda_item', 'decision'
                item_id TEXT NOT NULL,
                stance TEXT NOT NULL,  -- 'support', 'oppose', 'question'
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Constraints
                CHECK (item_type IN ('initiative', 'agenda_item', 'decision')),
                CHECK (stance IN ('support', 'oppose', 'question'))
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_voices_item ON voices(item_type, item_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_voices_user ON voices(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_voices_stance ON voices(stance)")

        # Subscriptions table (user follows on items)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                item_type TEXT NOT NULL,  -- 'meeting', 'initiative', 'topic', 'decision'
                item_id TEXT NOT NULL,
                notification_prefs TEXT,  -- JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Constraints
                CHECK (item_type IN ('meeting', 'initiative', 'topic', 'decision')),
                UNIQUE (user_id, item_type, item_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_item ON subscriptions(item_type, item_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id)")

        # Outcomes table (recorded outcomes of decisions/items)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                id TEXT PRIMARY KEY,
                item_type TEXT NOT NULL,  -- 'initiative', 'agenda_item', 'decision'
                item_id TEXT NOT NULL,
                outcome TEXT NOT NULL,  -- 'passed', 'failed', 'continued', 'modified'
                notes TEXT,
                vote_breakdown TEXT,  -- JSON (e.g., {"yes": 4, "no": 1, "abstain": 0})
                recorded_by TEXT NOT NULL DEFAULT 'anonymous',  -- user_id or 'system'
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Constraints
                CHECK (item_type IN ('initiative', 'agenda_item', 'decision')),
                CHECK (outcome IN ('passed', 'failed', 'continued', 'modified'))
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_item ON outcomes(item_type, item_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_outcome ON outcomes(outcome)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_recorded_at ON outcomes(recorded_at)")

        conn.commit()
        conn.close()

        logger.info(f"State database initialized at {self.db_path}")

    def update_meetings(
        self,
        jurisdiction_id: str,
        meetings: List[Dict[str, Any]],
        as_of: Optional[datetime] = None
    ) -> int:
        """
        Update meeting data with temporal versioning.

        This closes previous versions and inserts new versions atomically.

        Args:
            jurisdiction_id: City identifier (e.g., "city-berkeley")
            meetings: List of meeting dictionaries
            as_of: Timestamp of extraction (default: now)

        Returns:
            Number of meetings updated
        """
        as_of = as_of or datetime.now()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists
            cursor.execute("""
                INSERT OR IGNORE INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (?, ?, ?)
            """, (jurisdiction_id, jurisdiction_id.replace('-', ' ').title(), as_of))

            # Close previous versions (set valid_to)
            # Use isoformat() for consistent string comparison with valid_from
            cursor.execute("""
                UPDATE meetings
                SET valid_to = ?
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
            """, (as_of.isoformat(), jurisdiction_id))

            # Get meeting IDs being updated to close their agenda_items
            meeting_ids = [m.get('id') for m in meetings if m.get('id')]
            if meeting_ids:
                placeholders = ','.join('?' * len(meeting_ids))
                cursor.execute(f"""
                    UPDATE agenda_items
                    SET valid_to = ?
                    WHERE meeting_id IN ({placeholders})
                      AND valid_to IS NULL
                """, [as_of.isoformat()] + meeting_ids)

            # Insert new versions
            for meeting in meetings:
                meeting_id = meeting.get('id')
                cursor.execute("""
                    INSERT INTO meetings (
                        id, jurisdiction_id, title, meeting_datetime,
                        meeting_type, status, location, virtual_url,
                        agenda_url, minutes_url, video_url, comment_deadline,
                        source_platform, source_url, last_verified,
                        data_quality_score, valid_from, valid_to, full_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """, (
                    meeting_id,
                    jurisdiction_id,
                    meeting.get('title'),
                    meeting.get('meeting_datetime'),
                    meeting.get('meeting_type'),
                    meeting.get('status'),
                    meeting.get('location'),
                    meeting.get('virtual_url'),
                    meeting.get('agenda_url'),
                    meeting.get('minutes_url'),
                    meeting.get('video_url'),
                    meeting.get('comment_deadline'),
                    meeting.get('source_platform', 'unknown'),
                    meeting.get('source_url'),
                    as_of.isoformat(),
                    meeting.get('data_quality_score', 0.0),
                    as_of.isoformat(),
                    json.dumps(meeting)
                ))

                # Hybrid sync: also insert agenda_items into relational table
                # JSON blob (full_data) remains source of truth for flexibility
                # Relational table enables queries and FK relationships
                agenda_items = meeting.get('agenda_items', [])
                for item in agenda_items:
                    item_id = item.get('id')
                    if not item_id:
                        # Generate ID if not provided
                        item_id = f"{meeting_id}-item-{agenda_items.index(item)}"
                    cursor.execute("""
                        INSERT INTO agenda_items (
                            id, meeting_id, item_number, title, description,
                            project_type, actionability, impact_level,
                            summary, why_it_matters,
                            valid_from, valid_to, full_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """, (
                        item_id,
                        meeting_id,
                        item.get('item_number'),
                        item.get('title', 'Untitled'),
                        item.get('description'),
                        item.get('project_type') or item.get('topic'),
                        item.get('actionability'),
                        item.get('impact_level'),
                        item.get('summary'),
                        item.get('why_it_matters'),
                        as_of.isoformat(),
                        json.dumps(item)
                    ))

            # Update city_state timestamp
            cursor.execute("""
                UPDATE city_states
                SET as_of = ?, updated_at = ?
                WHERE jurisdiction_id = ?
            """, (as_of, datetime.now(), jurisdiction_id))

            conn.commit()
            logger.info(f"Updated {len(meetings)} meetings for {jurisdiction_id} as of {as_of}")
            return len(meetings)

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update meetings: {e}")
            raise
        finally:
            conn.close()

    def get_city_state(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get complete city state at specific time.

        Args:
            jurisdiction_id: City identifier
            as_of: Point in time (default: current)

        Returns:
            Dictionary with complete city state
        """
        as_of = as_of or datetime.now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get city metadata
        cursor.execute("""
            SELECT * FROM city_states WHERE jurisdiction_id = ?
        """, (jurisdiction_id,))
        city_row = cursor.fetchone()

        if not city_row:
            conn.close()
            return {
                "error": f"No data for {jurisdiction_id}",
                "jurisdiction_id": jurisdiction_id
            }

        # Get current meetings (temporal query)
        cursor.execute("""
            SELECT * FROM meetings
            WHERE jurisdiction_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to > ?)
            ORDER BY meeting_datetime
        """, (jurisdiction_id, as_of.isoformat(), as_of.isoformat()))

        meetings = [dict(row) for row in cursor.fetchall()]

        # Parse full_data JSON
        for meeting in meetings:
            if meeting.get('full_data'):
                try:
                    meeting['full_data'] = json.loads(meeting['full_data'])
                except (json.JSONDecodeError, TypeError):
                    meeting['full_data'] = {}

        # Get agenda items for these meetings
        meeting_ids = [m['id'] for m in meetings]
        agenda_items = []
        if meeting_ids:
            placeholders = ','.join('?' * len(meeting_ids))
            cursor.execute(f"""
                SELECT * FROM agenda_items
                WHERE meeting_id IN ({placeholders})
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR valid_to > ?)
            """, meeting_ids + [as_of.isoformat(), as_of.isoformat()])

            agenda_items = [dict(row) for row in cursor.fetchall()]

            # Parse JSON fields
            for item in agenda_items:
                if item.get('full_data'):
                    try:
                        item['full_data'] = json.loads(item['full_data'])
                    except (json.JSONDecodeError, TypeError):
                        item['full_data'] = {}

            # Attach agenda_items to their parent meetings for easy access
            # This enables consumers to use meeting['agenda_items'] directly
            items_by_meeting = {}
            for item in agenda_items:
                mid = item.get('meeting_id')
                if mid not in items_by_meeting:
                    items_by_meeting[mid] = []
                items_by_meeting[mid].append(item)

            for meeting in meetings:
                meeting['agenda_items'] = items_by_meeting.get(meeting['id'], [])
        else:
            # No meeting_ids, ensure meetings still have empty agenda_items
            for meeting in meetings:
                meeting['agenda_items'] = []

        conn.close()

        return {
            "jurisdiction_id": jurisdiction_id,
            "jurisdiction_name": city_row['jurisdiction_name'],
            "as_of": as_of.isoformat(),
            "meetings": meetings,
            "agenda_items": agenda_items,
            "active_residents": city_row['active_residents'],
            "pending_comments": city_row['pending_comments'],
            "completeness_score": city_row['completeness_score'],
            "last_updated": city_row['updated_at']
        }

    def query_meetings(
        self,
        jurisdiction_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        project_type: Optional[str] = None,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Query meetings with filters.

        Args:
            jurisdiction_id: City identifier
            date_from: Start date filter
            date_to: End date filter
            project_type: Filter by agenda item type
            as_of: Point in time for temporal query (default: current)

        Returns:
            List of meeting dictionaries
        """
        as_of = as_of or datetime.now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build query
        query = """
            SELECT * FROM meetings
            WHERE jurisdiction_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to > ?)
        """
        params = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if date_from:
            query += " AND meeting_datetime >= ?"
            params.append(date_from.isoformat())

        if date_to:
            query += " AND meeting_datetime <= ?"
            params.append(date_to.isoformat())

        query += " ORDER BY meeting_datetime"

        cursor.execute(query, params)
        meetings = [dict(row) for row in cursor.fetchall()]

        # Parse full_data
        for meeting in meetings:
            if meeting.get('full_data'):
                try:
                    meeting['full_data'] = json.loads(meeting['full_data'])
                except (json.JSONDecodeError, TypeError):
                    meeting['full_data'] = {}

        # Filter by project_type if specified (requires checking agenda items)
        if project_type:
            meeting_ids = [m['id'] for m in meetings]
            if meeting_ids:
                placeholders = ','.join('?' * len(meeting_ids))
                cursor.execute(f"""
                    SELECT DISTINCT meeting_id FROM agenda_items
                    WHERE meeting_id IN ({placeholders})
                      AND project_type = ?
                      AND valid_from <= ?
                      AND (valid_to IS NULL OR valid_to > ?)
                """, meeting_ids + [project_type, as_of.isoformat(), as_of.isoformat()])

                filtered_ids = {row['meeting_id'] for row in cursor.fetchall()}
                meetings = [m for m in meetings if m['id'] in filtered_ids]

        conn.close()
        return meetings

    def get_stats(self, jurisdiction_id: str) -> Dict[str, Any]:
        """
        Get statistics about city state data.

        Args:
            jurisdiction_id: City identifier

        Returns:
            Statistics dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Count current meetings
        cursor.execute("""
            SELECT COUNT(*) FROM meetings
            WHERE jurisdiction_id = ? AND valid_to IS NULL
        """, (jurisdiction_id,))
        current_meetings = cursor.fetchone()[0]

        # Count historical versions
        cursor.execute("""
            SELECT COUNT(*) FROM meetings
            WHERE jurisdiction_id = ? AND valid_to IS NOT NULL
        """, (jurisdiction_id,))
        historical_versions = cursor.fetchone()[0]

        # Count agenda items
        cursor.execute("""
            SELECT COUNT(*) FROM agenda_items
            WHERE valid_to IS NULL
              AND meeting_id IN (
                  SELECT id FROM meetings
                  WHERE jurisdiction_id = ? AND valid_to IS NULL
              )
        """, (jurisdiction_id,))
        current_agenda_items = cursor.fetchone()[0]

        # Date range
        cursor.execute("""
            SELECT MIN(meeting_datetime), MAX(meeting_datetime)
            FROM meetings
            WHERE jurisdiction_id = ? AND valid_to IS NULL
        """, (jurisdiction_id,))
        date_range = cursor.fetchone()

        conn.close()

        return {
            "jurisdiction_id": jurisdiction_id,
            "current_meetings": current_meetings,
            "historical_versions": historical_versions,
            "current_agenda_items": current_agenda_items,
            "date_range": {
                "earliest": date_range[0],
                "latest": date_range[1]
            }
        }

    def query_issues(
        self,
        jurisdiction_id: str,
        status: Optional[str] = None,
        issue_type: Optional[str] = None,
        street: Optional[str] = None,
        limit: int = 100,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Query operational issues with filters.

        Args:
            jurisdiction_id: City identifier
            status: Filter by status (open, closed)
            issue_type: Filter by type (pothole, graffiti, etc.)
            street: Filter by street name (partial match)
            limit: Max results (default 100)
            as_of: Point in time for temporal query (default: current)

        Returns:
            List of issue dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query current issues (valid_to IS NULL means current version)
        query = """
            SELECT * FROM issues
            WHERE jurisdiction_id = ?
              AND valid_to IS NULL
        """
        params = [jurisdiction_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        if issue_type:
            query += " AND issue_type = ?"
            params.append(issue_type)

        if street:
            query += " AND address LIKE ?"
            params.append(f"%{street}%")

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        issues = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return issues

    def import_seeclickfix_json(
        self,
        json_path: str,
        jurisdiction_id: str
    ) -> int:
        """
        Import SeeClickFix complaints from JSON file.

        Args:
            json_path: Path to JSON file
            jurisdiction_id: City identifier

        Returns:
            Number of issues imported
        """
        with open(json_path, 'r') as f:
            data = json.load(f)

        issues = data if isinstance(data, list) else data.get('issues', [])

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Ensure city_state exists
        cursor.execute("""
            INSERT OR IGNORE INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
            VALUES (?, ?, ?)
        """, (jurisdiction_id, jurisdiction_id.replace('city-', '').replace('-', ' ').title(), datetime.now()))

        count = 0
        for issue in issues:
            issue_id = f"scf-{issue.get('id', count)}"

            # Extract issue type from nested structure or direct field
            issue_type = None
            if isinstance(issue.get('request_type'), dict):
                issue_type = issue['request_type'].get('title')
            elif issue.get('category'):
                issue_type = issue['category']
            elif issue.get('issue_type'):
                issue_type = issue['issue_type']

            # Extract location data (can be nested or flat)
            location = issue.get('location', {})
            if isinstance(location, dict):
                address = location.get('address')
                lat = location.get('lat')
                lng = location.get('lng')
            else:
                address = issue.get('address')
                lat = issue.get('lat')
                lng = issue.get('lng')

            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO issues (
                        id, jurisdiction_id, source, source_id, title,
                        description, issue_type, address, latitude, longitude,
                        status, created_at, valid_from
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    issue_id,
                    jurisdiction_id,
                    'seeclickfix',
                    str(issue.get('id')),
                    issue.get('summary') or issue.get('title', 'Unknown Issue'),
                    issue.get('description'),
                    issue_type,
                    address,
                    lat,
                    lng,
                    issue.get('status', 'open'),
                    issue.get('created_at')
                ))
                count += 1
            except Exception as e:
                logger.warning(f"Failed to import issue {issue_id}: {e}")

        conn.commit()
        conn.close()

        logger.info(f"Imported {count} SeeClickFix issues for {jurisdiction_id}")
        return count

    def get_issue_stats(self, jurisdiction_id: str) -> Dict[str, Any]:
        """
        Get statistics about issues for a jurisdiction.

        Args:
            jurisdiction_id: City identifier

        Returns:
            Statistics dictionary with counts by type, status, top streets
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Total count
        cursor.execute("""
            SELECT COUNT(*) as total FROM issues
            WHERE jurisdiction_id = ? AND valid_to IS NULL
        """, (jurisdiction_id,))
        total = cursor.fetchone()['total']

        # By status
        cursor.execute("""
            SELECT status, COUNT(*) as count FROM issues
            WHERE jurisdiction_id = ? AND valid_to IS NULL
            GROUP BY status
        """, (jurisdiction_id,))
        by_status = {row['status']: row['count'] for row in cursor.fetchall()}

        # By type (top 10)
        cursor.execute("""
            SELECT issue_type, COUNT(*) as count FROM issues
            WHERE jurisdiction_id = ? AND valid_to IS NULL AND issue_type IS NOT NULL
            GROUP BY issue_type
            ORDER BY count DESC
            LIMIT 10
        """, (jurisdiction_id,))
        by_type = [(row['issue_type'], row['count']) for row in cursor.fetchall()]

        conn.close()

        return {
            "jurisdiction_id": jurisdiction_id,
            "total_issues": total,
            "by_status": by_status,
            "top_types": by_type
        }

    def list_jurisdictions(self) -> List[Dict[str, Any]]:
        """
        List all jurisdictions in the database.

        Returns:
            List of jurisdiction dictionaries with id, name, and stats
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT jurisdiction_id, jurisdiction_name, as_of, updated_at,
                   active_residents, completeness_score
            FROM city_states
            ORDER BY jurisdiction_name
        """)

        jurisdictions = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jurisdictions

    def create_initiative(
        self,
        initiative_id: str,
        jurisdiction_id: str,
        topic: str,
        title: str,
        description: str,
        creator_id: str = "anonymous",
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new initiative.

        Args:
            initiative_id: Unique initiative ID
            jurisdiction_id: City identifier
            topic: Topic category (e.g., "traffic safety")
            title: Initiative title
            description: Full description
            creator_id: ID of the creator
            location: Optional location

        Returns:
            Created initiative dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now()

        # Ensure city_state exists
        cursor.execute("""
            INSERT OR IGNORE INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
            VALUES (?, ?, ?)
        """, (jurisdiction_id, jurisdiction_id.replace('-', ' ').title(), now))

        try:
            cursor.execute("""
                INSERT INTO initiatives (
                    id, jurisdiction_id, topic, title, description,
                    creator_id, location, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """, (
                initiative_id,
                jurisdiction_id,
                topic,
                title,
                description,
                creator_id,
                location,
                now.isoformat(),
                now.isoformat(),
            ))

            conn.commit()
            logger.info(f"Created initiative {initiative_id} for {jurisdiction_id}")

            return {
                "id": initiative_id,
                "jurisdiction_id": jurisdiction_id,
                "topic": topic,
                "title": title,
                "description": description,
                "creator_id": creator_id,
                "location": location,
                "status": "active",
                "created_at": now.isoformat(),
            }

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create initiative: {e}")
            raise
        finally:
            conn.close()

    def get_initiative(self, initiative_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an initiative by ID.

        Args:
            initiative_id: Initiative ID

        Returns:
            Initiative dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM initiatives WHERE id = ?
        """, (initiative_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def query_initiatives(
        self,
        jurisdiction_id: str,
        topic: Optional[str] = None,
        status: str = "active",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query initiatives with filters.

        Args:
            jurisdiction_id: City identifier
            topic: Optional topic filter
            status: Status filter (default: active)
            limit: Max results (default 100)

        Returns:
            List of initiative dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT * FROM initiatives
            WHERE jurisdiction_id = ?
        """
        params = [jurisdiction_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        if topic:
            query += " AND topic = ?"
            params.append(topic)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        initiatives = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return initiatives

    # ─────────── VOICES ───────────

    def create_voice(
        self,
        voice_id: str,
        item_type: str,
        item_id: str,
        stance: str,
        comment: str,
        user_id: str = "anonymous"
    ) -> Dict[str, Any]:
        """
        Create a new voice (comment/stance on an item).

        Args:
            voice_id: Unique voice ID
            item_type: Type of item ('initiative', 'agenda_item', 'decision')
            item_id: ID of the item being commented on
            stance: User's stance ('support', 'oppose', 'question')
            comment: User's comment
            user_id: ID of the user

        Returns:
            Created voice dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now()

        try:
            cursor.execute("""
                INSERT INTO voices (
                    id, user_id, item_type, item_id, stance, comment, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                voice_id,
                user_id,
                item_type,
                item_id,
                stance,
                comment,
                now.isoformat(),
            ))

            # Update voice_count on initiative if applicable
            if item_type == "initiative":
                cursor.execute("""
                    UPDATE initiatives
                    SET voice_count = voice_count + 1,
                        updated_at = ?
                    WHERE id = ?
                """, (now.isoformat(), item_id))

            conn.commit()
            logger.info(f"Created voice {voice_id} on {item_type}:{item_id}")

            return {
                "id": voice_id,
                "user_id": user_id,
                "item_type": item_type,
                "item_id": item_id,
                "stance": stance,
                "comment": comment,
                "created_at": now.isoformat(),
            }

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create voice: {e}")
            raise
        finally:
            conn.close()

    def get_voice(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a voice by ID.

        Args:
            voice_id: Voice ID

        Returns:
            Voice dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM voices WHERE id = ?
        """, (voice_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def query_voices(
        self,
        item_type: str,
        item_id: str,
        stance: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query voices for an item.

        Args:
            item_type: Type of item ('initiative', 'agenda_item', 'decision')
            item_id: ID of the item
            stance: Optional stance filter
            limit: Max results (default 100)

        Returns:
            List of voice dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT * FROM voices
            WHERE item_type = ? AND item_id = ?
        """
        params = [item_type, item_id]

        if stance:
            query += " AND stance = ?"
            params.append(stance)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        voices = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return voices

    def count_voices(
        self,
        item_type: str,
        item_id: str
    ) -> Dict[str, int]:
        """
        Count voices by stance for an item.

        Args:
            item_type: Type of item
            item_id: ID of the item

        Returns:
            Dictionary with counts by stance
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT stance, COUNT(*) as count
            FROM voices
            WHERE item_type = ? AND item_id = ?
            GROUP BY stance
        """, (item_type, item_id))

        counts = {"support": 0, "oppose": 0, "question": 0, "total": 0}
        for row in cursor.fetchall():
            counts[row[0]] = row[1]
            counts["total"] += row[1]

        conn.close()
        return counts

    # ─────────── SUBSCRIPTIONS ───────────

    def create_subscription(
        self,
        subscription_id: str,
        item_type: str,
        item_id: str,
        user_id: str = "anonymous",
        notification_prefs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new subscription (follow an item).

        Args:
            subscription_id: Unique subscription ID
            item_type: Type of item ('meeting', 'initiative', 'topic', 'decision')
            item_id: ID of the item being followed
            user_id: ID of the user
            notification_prefs: Optional notification preferences

        Returns:
            Created subscription dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now()

        try:
            cursor.execute("""
                INSERT INTO subscriptions (
                    id, user_id, item_type, item_id, notification_prefs, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                subscription_id,
                user_id,
                item_type,
                item_id,
                json.dumps(notification_prefs) if notification_prefs else None,
                now.isoformat(),
            ))

            # Update following_count on initiative if applicable
            if item_type == "initiative":
                cursor.execute("""
                    UPDATE initiatives
                    SET supporter_count = supporter_count + 1,
                        updated_at = ?
                    WHERE id = ?
                """, (now.isoformat(), item_id))

            conn.commit()
            logger.info(f"Created subscription {subscription_id} for {item_type}:{item_id}")

            return {
                "id": subscription_id,
                "user_id": user_id,
                "item_type": item_type,
                "item_id": item_id,
                "notification_prefs": notification_prefs,
                "created_at": now.isoformat(),
            }

        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                # Already subscribed, return existing subscription
                return self.get_subscription_by_user_item(user_id, item_type, item_id)
            logger.error(f"Failed to create subscription: {e}")
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create subscription: {e}")
            raise
        finally:
            conn.close()

    def get_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a subscription by ID.

        Args:
            subscription_id: Subscription ID

        Returns:
            Subscription dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM subscriptions WHERE id = ?
        """, (subscription_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            if result.get("notification_prefs"):
                try:
                    result["notification_prefs"] = json.loads(result["notification_prefs"])
                except (json.JSONDecodeError, TypeError):
                    result["notification_prefs"] = {}
            return result
        return None

    def get_subscription_by_user_item(
        self,
        user_id: str,
        item_type: str,
        item_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a subscription by user and item.

        Args:
            user_id: User ID
            item_type: Type of item
            item_id: ID of the item

        Returns:
            Subscription dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM subscriptions
            WHERE user_id = ? AND item_type = ? AND item_id = ?
        """, (user_id, item_type, item_id))

        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            if result.get("notification_prefs"):
                try:
                    result["notification_prefs"] = json.loads(result["notification_prefs"])
                except (json.JSONDecodeError, TypeError):
                    result["notification_prefs"] = {}
            return result
        return None

    def query_subscriptions(
        self,
        user_id: Optional[str] = None,
        item_type: Optional[str] = None,
        item_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query subscriptions with filters.

        Args:
            user_id: Optional user ID filter
            item_type: Optional item type filter
            item_id: Optional item ID filter
            limit: Max results (default 100)

        Returns:
            List of subscription dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM subscriptions WHERE 1=1"
        params = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if item_type:
            query += " AND item_type = ?"
            params.append(item_type)

        if item_id:
            query += " AND item_id = ?"
            params.append(item_id)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        subscriptions = []
        for row in cursor.fetchall():
            sub = dict(row)
            if sub.get("notification_prefs"):
                try:
                    sub["notification_prefs"] = json.loads(sub["notification_prefs"])
                except (json.JSONDecodeError, TypeError):
                    sub["notification_prefs"] = {}
            subscriptions.append(sub)

        conn.close()
        return subscriptions

    def count_subscriptions(
        self,
        item_type: str,
        item_id: str
    ) -> int:
        """
        Count subscriptions for an item.

        Args:
            item_type: Type of item
            item_id: ID of the item

        Returns:
            Number of subscriptions
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM subscriptions
            WHERE item_type = ? AND item_id = ?
        """, (item_type, item_id))

        count = cursor.fetchone()[0]
        conn.close()
        return count

    def delete_subscription(
        self,
        subscription_id: str
    ) -> bool:
        """
        Delete a subscription (unfollow).

        Args:
            subscription_id: Subscription ID

        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get subscription details first for counter update
        cursor.execute("""
            SELECT item_type, item_id FROM subscriptions WHERE id = ?
        """, (subscription_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return False

        item_type, item_id = row

        try:
            cursor.execute("""
                DELETE FROM subscriptions WHERE id = ?
            """, (subscription_id,))

            # Update supporter_count on initiative if applicable
            if item_type == "initiative":
                cursor.execute("""
                    UPDATE initiatives
                    SET supporter_count = MAX(0, supporter_count - 1),
                        updated_at = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), item_id))

            conn.commit()
            logger.info(f"Deleted subscription {subscription_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete subscription: {e}")
            raise
        finally:
            conn.close()

    # ─────────── OUTCOMES ───────────

    def create_outcome(
        self,
        outcome_id: str,
        item_type: str,
        item_id: str,
        outcome: str,
        notes: Optional[str] = None,
        vote_breakdown: Optional[Dict[str, int]] = None,
        recorded_by: str = "anonymous"
    ) -> Dict[str, Any]:
        """
        Record an outcome for an item.

        Args:
            outcome_id: Unique outcome ID
            item_type: Type of item ('initiative', 'agenda_item', 'decision')
            item_id: ID of the item
            outcome: Outcome result ('passed', 'failed', 'continued', 'modified')
            notes: Optional notes about the outcome
            vote_breakdown: Optional vote breakdown (e.g., {"yes": 4, "no": 1})
            recorded_by: ID of the recorder (user_id or 'system')

        Returns:
            Created outcome dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now()

        try:
            cursor.execute("""
                INSERT INTO outcomes (
                    id, item_type, item_id, outcome, notes,
                    vote_breakdown, recorded_by, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                outcome_id,
                item_type,
                item_id,
                outcome,
                notes,
                json.dumps(vote_breakdown) if vote_breakdown else None,
                recorded_by,
                now.isoformat(),
            ))

            # Update initiative status if applicable
            if item_type == "initiative":
                new_status = "succeeded" if outcome == "passed" else (
                    "failed" if outcome == "failed" else "active"
                )
                cursor.execute("""
                    UPDATE initiatives
                    SET status = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (new_status, now.isoformat(), item_id))

            conn.commit()
            logger.info(f"Recorded outcome {outcome_id} for {item_type}:{item_id}")

            return {
                "id": outcome_id,
                "item_type": item_type,
                "item_id": item_id,
                "outcome": outcome,
                "notes": notes,
                "vote_breakdown": vote_breakdown,
                "recorded_by": recorded_by,
                "recorded_at": now.isoformat(),
            }

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to record outcome: {e}")
            raise
        finally:
            conn.close()

    def get_outcome(self, outcome_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an outcome by ID.

        Args:
            outcome_id: Outcome ID

        Returns:
            Outcome dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM outcomes WHERE id = ?
        """, (outcome_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            if result.get("vote_breakdown"):
                try:
                    result["vote_breakdown"] = json.loads(result["vote_breakdown"])
                except (json.JSONDecodeError, TypeError):
                    result["vote_breakdown"] = {}
            return result
        return None

    def get_outcome_for_item(
        self,
        item_type: str,
        item_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent outcome for an item.

        Args:
            item_type: Type of item
            item_id: ID of the item

        Returns:
            Outcome dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM outcomes
            WHERE item_type = ? AND item_id = ?
            ORDER BY recorded_at DESC
            LIMIT 1
        """, (item_type, item_id))

        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            if result.get("vote_breakdown"):
                try:
                    result["vote_breakdown"] = json.loads(result["vote_breakdown"])
                except (json.JSONDecodeError, TypeError):
                    result["vote_breakdown"] = {}
            return result
        return None

    def query_outcomes(
        self,
        item_type: Optional[str] = None,
        outcome: Optional[str] = None,
        recorded_by: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query outcomes with filters.

        Args:
            item_type: Optional item type filter
            outcome: Optional outcome filter
            recorded_by: Optional recorder filter
            limit: Max results (default 100)

        Returns:
            List of outcome dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM outcomes WHERE 1=1"
        params = []

        if item_type:
            query += " AND item_type = ?"
            params.append(item_type)

        if outcome:
            query += " AND outcome = ?"
            params.append(outcome)

        if recorded_by:
            query += " AND recorded_by = ?"
            params.append(recorded_by)

        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        outcomes = []
        for row in cursor.fetchall():
            result = dict(row)
            if result.get("vote_breakdown"):
                try:
                    result["vote_breakdown"] = json.loads(result["vote_breakdown"])
                except (json.JSONDecodeError, TypeError):
                    result["vote_breakdown"] = {}
            outcomes.append(result)

        conn.close()
        return outcomes

    def get_outcome_stats(self) -> Dict[str, Any]:
        """
        Get statistics about outcomes.

        Returns:
            Statistics dictionary with counts by outcome type
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total count
        cursor.execute("SELECT COUNT(*) FROM outcomes")
        total = cursor.fetchone()[0]

        # By outcome
        cursor.execute("""
            SELECT outcome, COUNT(*) as count
            FROM outcomes
            GROUP BY outcome
        """)
        by_outcome = {row[0]: row[1] for row in cursor.fetchall()}

        # By item_type
        cursor.execute("""
            SELECT item_type, COUNT(*) as count
            FROM outcomes
            GROUP BY item_type
        """)
        by_item_type = {row[0]: row[1] for row in cursor.fetchall()}

        conn.close()

        return {
            "total": total,
            "by_outcome": by_outcome,
            "by_item_type": by_item_type
        }
