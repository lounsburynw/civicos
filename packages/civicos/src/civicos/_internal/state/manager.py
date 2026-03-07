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

from civicos.paths import get_state_db_path

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
                     Defaults to get_state_db_path() which respects CIVICOS_DATA_ROOT.
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

