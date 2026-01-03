"""
SQLiteBackend implementation of StorageBackend protocol.

Wraps civic-services StateManager to provide protocol-compliant storage.
Part of the 4-stage pipeline: discover -> ingest -> store -> index.
"""

import json
import sqlite3
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from civic.paths import get_state_db_path
from .backend import StorageBackend, StorageStats, StorageValidationResult


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


class SQLiteBackend:
    """
    SQLite implementation of StorageBackend protocol.

    Provides local file-based storage for development and single-server deployments.
    Uses temporal versioning for point-in-time queries.

    Usage:
        backend = SQLiteBackend()  # Uses get_state_db_path()

        # Validate before use
        result = backend.validate()
        if not result.is_valid:
            raise RuntimeError(result.errors)

        # Store meetings
        count = backend.store_meetings(
            jurisdiction_id="city-san-rafael",
            meetings=normalized_meetings
        )

        # Retrieve for indexing
        meetings = backend.get_meetings("city-san-rafael")
    """

    def __init__(self, db_path: str = None):
        """
        Initialize SQLite storage backend.

        Args:
            db_path: Path to SQLite database file (created if doesn't exist).
                     Defaults to get_state_db_path() which respects CIVIC_DATA_ROOT.
        """
        self._db_path = db_path or get_state_db_path()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure database directory exists."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @property
    def backend_type(self) -> str:
        """Type identifier: 'sqlite'."""
        return "sqlite"

    def validate(self) -> StorageValidationResult:
        """
        Validate storage backend connectivity and schema.

        Returns:
            StorageValidationResult with validation status
        """
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        connected = False
        schema_valid = False

        try:
            # Test connection
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            connected = True

            # Check schema - verify required tables exist
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}

            required_tables = {"city_states", "meetings", "agenda_items"}
            missing = required_tables - tables

            if missing:
                # Schema doesn't exist - need to initialize
                warnings.append(
                    f"Missing tables: {missing}. Schema will be created on first write."
                )
                schema_valid = False
            else:
                # Verify column structure
                cursor.execute("PRAGMA table_info(meetings)")
                columns = {row[1] for row in cursor.fetchall()}
                required_columns = {
                    "id", "jurisdiction_id", "title", "meeting_datetime",
                    "valid_from", "valid_to", "full_data"
                }
                missing_cols = required_columns - columns
                if missing_cols:
                    errors.append(f"Missing columns in meetings table: {missing_cols}")
                    schema_valid = False
                else:
                    schema_valid = True

            conn.close()

        except sqlite3.Error as e:
            errors.append(f"SQLite error: {str(e)}")
        except Exception as e:
            errors.append(f"Unexpected error: {str(e)}")

        duration_ms = (time.time() - start_time) * 1000
        is_valid = connected and (schema_valid or len(errors) == 0)

        return StorageValidationResult(
            is_valid=is_valid,
            connected=connected,
            schema_valid=schema_valid,
            errors=errors,
            warnings=warnings,
            check_duration_ms=duration_ms,
        )

    def _ensure_schema(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """Create database schema if it doesn't exist."""
        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self._db_path)
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
                data_sources TEXT,
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
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                full_data TEXT,
                PRIMARY KEY (id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Agenda items table
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
                summary TEXT,
                why_it_matters TEXT,
                participation_guide TEXT,
                comment_count INTEGER DEFAULT 0,
                following_count INTEGER DEFAULT 0,
                relevant_bills TEXT,
                federal_programs TEXT,
                matched_complaints TEXT,
                extracted_at TIMESTAMP,
                enriched_at TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                full_data TEXT,
                PRIMARY KEY (id, valid_from),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Decisions table (SESSION 366, enhanced SESSION 438)
        # Stores extracted decisions from meeting minutes
        # SESSION 438: Added financial_impact_cents for budget tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                meeting_date TEXT NOT NULL,
                agenda_item TEXT,
                title TEXT NOT NULL,
                summary TEXT,
                outcome TEXT,
                vote_json TEXT,
                staff_recommendation_json TEXT,
                public_input_json TEXT,
                legal_instruments_json TEXT,
                topics TEXT,
                source_documents TEXT,
                extraction_method TEXT,
                financial_impact_cents INTEGER,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Decision indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_decisions_jurisdiction "
            "ON decisions(jurisdiction_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_decisions_meeting_date "
            "ON decisions(meeting_date)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_decisions_outcome "
            "ON decisions(outcome)"
        )

        # Chunks table (SESSION 367)
        # Stores PDF chunks from agenda packets for RAG retrieval
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                meeting_id TEXT,
                agenda_item TEXT,
                agenda_title TEXT,
                text TEXT NOT NULL,
                page_start INTEGER,
                page_end INTEGER,
                chunk_index INTEGER NOT NULL,
                total_chunks INTEGER,
                source_file TEXT,
                source_type TEXT DEFAULT 'agenda_packet',
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Chunk indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_jurisdiction "
            "ON chunks(jurisdiction_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_meeting "
            "ON chunks(meeting_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_agenda_item "
            "ON chunks(agenda_item)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_source_type "
            "ON chunks(source_type)"
        )

        # Create indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_meetings_jurisdiction "
            "ON meetings(jurisdiction_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_meetings_datetime "
            "ON meetings(meeting_datetime)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_meetings_temporal "
            "ON meetings(jurisdiction_id, valid_from, valid_to)"
        )

        # Operations table for tracking long-running tasks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY,
                jurisdiction_id TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                result_json TEXT,
                error TEXT,
                duration_seconds REAL,
                current_step TEXT,
                progress_percent REAL DEFAULT 0,
                items_processed INTEGER DEFAULT 0,
                items_total INTEGER DEFAULT 0,
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (status IN ('pending', 'running', 'completed', 'failed'))
            )
        """)

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_operations_jurisdiction "
            "ON operations(jurisdiction_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_operations_status "
            "ON operations(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_operations_started "
            "ON operations(started_at DESC)"
        )

        # Federal awards table (SESSION 440)
        # Stores federal grants, contracts, loans from USAspending.gov
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS federal_awards (
                award_id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                cfda_number TEXT,
                recipient_uei TEXT,
                recipient_name TEXT,
                amount_cents INTEGER CHECK(amount_cents >= 0),
                period_start TEXT,
                period_end TEXT,
                program_name TEXT,
                awarding_agency TEXT,
                funding_agency TEXT,
                award_type TEXT,
                metadata TEXT,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (award_id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_federal_awards_jurisdiction "
            "ON federal_awards(jurisdiction_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_federal_awards_cfda "
            "ON federal_awards(cfda_number)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_federal_awards_temporal "
            "ON federal_awards(jurisdiction_id, valid_from, valid_to)"
        )

        # State passthrough funds table (SESSION 442)
        # Tracks federal funds that flow through state agencies to local governments
        # Example: HUD → California HCD → San Rafael (CDBG allocation)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_passthrough_funds (
                passthrough_id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                federal_award_id TEXT,
                federal_cfda_number TEXT,
                federal_program_name TEXT,
                federal_amount_cents INTEGER,
                state_agency TEXT NOT NULL,
                state_program_name TEXT,
                state_grant_id TEXT,
                local_amount_cents INTEGER CHECK(local_amount_cents >= 0),
                allocation_percentage REAL CHECK(allocation_percentage IS NULL OR (allocation_percentage >= 0 AND allocation_percentage <= 100)),
                period_start TEXT,
                period_end TEXT,
                federal_fiscal_year INTEGER,
                state_fiscal_year INTEGER,
                source_url TEXT,
                notes TEXT,
                metadata TEXT,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (passthrough_id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_state_passthrough_jurisdiction "
            "ON state_passthrough_funds(jurisdiction_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_state_passthrough_state_agency "
            "ON state_passthrough_funds(jurisdiction_id, state_agency)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_state_passthrough_federal_cfda "
            "ON state_passthrough_funds(federal_cfda_number)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_state_passthrough_temporal "
            "ON state_passthrough_funds(jurisdiction_id, valid_from, valid_to)"
        )

        conn.commit()
        if should_close:
            conn.close()

    def store_meetings(
        self,
        jurisdiction_id: str,
        meetings: List[Any],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store meetings with temporal versioning.

        Atomic operation: either all meetings are stored or none.
        Updates existing meetings if IDs match, inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            meetings: List of meeting objects or dictionaries
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of meetings successfully stored

        Raises:
            sqlite3.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists
            cursor.execute("""
                INSERT OR IGNORE INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (?, ?, ?)
            """, (
                jurisdiction_id,
                jurisdiction_id.replace('-', ' ').title(),
                as_of.isoformat()
            ))

            # Close previous versions (set valid_to)
            cursor.execute("""
                UPDATE meetings
                SET valid_to = ?
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
            """, (as_of.isoformat(), jurisdiction_id))

            # Insert new versions
            for meeting in meetings:
                # Handle both dict and object access
                if hasattr(meeting, "__dict__"):
                    meeting_dict = meeting.__dict__
                elif hasattr(meeting, "to_dict"):
                    meeting_dict = meeting.to_dict()
                else:
                    meeting_dict = meeting

                # Convert datetime fields to ISO strings for SQLite
                meeting_dt = meeting_dict.get('meeting_datetime')
                if isinstance(meeting_dt, datetime):
                    meeting_dt = meeting_dt.isoformat()
                elif isinstance(meeting_dt, date):
                    meeting_dt = meeting_dt.isoformat()

                comment_dl = meeting_dict.get('comment_deadline')
                if isinstance(comment_dl, datetime):
                    comment_dl = comment_dl.isoformat()
                elif isinstance(comment_dl, date):
                    comment_dl = comment_dl.isoformat()

                cursor.execute("""
                    INSERT INTO meetings (
                        id, jurisdiction_id, title, meeting_datetime,
                        meeting_type, status, location, virtual_url,
                        agenda_url, minutes_url, video_url, comment_deadline,
                        source_platform, source_url, last_verified,
                        data_quality_score, valid_from, valid_to, full_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """, (
                    meeting_dict.get('id'),
                    jurisdiction_id,
                    meeting_dict.get('title'),
                    meeting_dt,
                    meeting_dict.get('meeting_type'),
                    meeting_dict.get('status'),
                    meeting_dict.get('location'),
                    meeting_dict.get('virtual_url'),
                    meeting_dict.get('agenda_url'),
                    meeting_dict.get('minutes_url'),
                    meeting_dict.get('video_url'),
                    comment_dl,
                    meeting_dict.get('source_platform', 'unknown'),
                    meeting_dict.get('source_url'),
                    as_of.isoformat(),
                    meeting_dict.get('data_quality_score', 0.0),
                    as_of.isoformat(),
                    json.dumps(meeting_dict, cls=DateTimeEncoder)
                ))

            # Update city_state timestamp
            cursor.execute("""
                UPDATE city_states
                SET as_of = ?, updated_at = ?
                WHERE jurisdiction_id = ?
            """, (as_of.isoformat(), datetime.now().isoformat(), jurisdiction_id))

            conn.commit()
            return len(meetings)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_meetings(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve meetings with optional temporal query.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            since: Filter meetings after this datetime
            until: Filter meetings before this datetime
            limit: Maximum number of meetings to return

        Returns:
            List of meeting dictionaries ready for indexing
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        # Build query with temporal filtering
        query = """
            SELECT * FROM meetings
            WHERE jurisdiction_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to > ?)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if since:
            query += " AND meeting_datetime >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND meeting_datetime <= ?"
            params.append(until.isoformat())

        query += " ORDER BY meeting_datetime"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries, parsing full_data JSON
        meetings = []
        for row in rows:
            meeting = dict(row)
            if meeting.get('full_data'):
                try:
                    meeting['full_data'] = json.loads(meeting['full_data'])
                except json.JSONDecodeError:
                    pass
            meetings.append(meeting)

        return meetings

    def get_stats(self, jurisdiction_id: str) -> StorageStats:
        """
        Get storage statistics for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            StorageStats with counts and temporal info
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        # Count current meetings
        cursor.execute("""
            SELECT COUNT(*) FROM meetings
            WHERE jurisdiction_id = ? AND valid_to IS NULL
        """, (jurisdiction_id,))
        meeting_count = cursor.fetchone()[0]

        # Count agenda items
        cursor.execute("""
            SELECT COUNT(*) FROM agenda_items
            WHERE valid_to IS NULL
              AND meeting_id IN (
                  SELECT id FROM meetings
                  WHERE jurisdiction_id = ? AND valid_to IS NULL
              )
        """, (jurisdiction_id,))
        agenda_item_count = cursor.fetchone()[0]

        # Date range and last updated
        cursor.execute("""
            SELECT MIN(meeting_datetime), MAX(meeting_datetime), MAX(valid_from)
            FROM meetings
            WHERE jurisdiction_id = ? AND valid_to IS NULL
        """, (jurisdiction_id,))
        result = cursor.fetchone()
        earliest = result[0]
        latest = result[1]
        last_updated_str = result[2]

        conn.close()

        # Parse datetime strings
        earliest_dt = None
        latest_dt = None
        last_updated_dt = None

        if earliest:
            try:
                earliest_dt = datetime.fromisoformat(earliest)
            except (ValueError, TypeError):
                pass
        if latest:
            try:
                latest_dt = datetime.fromisoformat(latest)
            except (ValueError, TypeError):
                pass
        if last_updated_str:
            try:
                last_updated_dt = datetime.fromisoformat(last_updated_str)
            except (ValueError, TypeError):
                pass

        # Get database file size (SQLite-specific)
        size_bytes = None
        db_file = Path(self._db_path)
        if db_file.exists():
            try:
                size_bytes = db_file.stat().st_size
            except OSError:
                pass  # Permission error, file gone, etc.

        return StorageStats(
            jurisdiction_id=jurisdiction_id,
            meeting_count=meeting_count,
            agenda_item_count=agenda_item_count,
            earliest_meeting=earliest_dt,
            latest_meeting=latest_dt,
            last_updated=last_updated_dt,
            size_bytes=size_bytes,
            metadata={"backend_type": self.backend_type},
        )

    def delete_meetings(
        self,
        jurisdiction_id: str,
        meeting_ids: Optional[List[str]] = None,
    ) -> int:
        """
        Delete meetings (soft delete with temporal versioning).

        If meeting_ids is None, deletes all meetings for jurisdiction.
        This is a soft delete - data can be recovered via temporal queries.

        Args:
            jurisdiction_id: Target jurisdiction
            meeting_ids: Specific meetings to delete (None = all)

        Returns:
            Number of meetings deleted
        """
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            if meeting_ids is None:
                # Soft delete all meetings for jurisdiction
                cursor.execute("""
                    UPDATE meetings
                    SET valid_to = ?
                    WHERE jurisdiction_id = ?
                      AND valid_to IS NULL
                """, (now, jurisdiction_id))
            else:
                # Soft delete specific meetings
                placeholders = ','.join('?' * len(meeting_ids))
                cursor.execute(f"""
                    UPDATE meetings
                    SET valid_to = ?
                    WHERE jurisdiction_id = ?
                      AND id IN ({placeholders})
                      AND valid_to IS NULL
                """, [now, jurisdiction_id] + meeting_ids)

            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ========== Decision Methods (SESSION 366) ==========

    def store_decisions(
        self,
        jurisdiction_id: str,
        decisions: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store decisions with temporal versioning.

        Atomic operation: either all decisions are stored or none.
        Updates existing decisions if IDs match, inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            decisions: List of decision dictionaries from JSON or extraction
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of decisions successfully stored

        Raises:
            sqlite3.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Close previous versions (set valid_to)
            cursor.execute("""
                UPDATE decisions
                SET valid_to = ?
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
            """, (as_of.isoformat(), jurisdiction_id))

            # Insert new versions
            for decision in decisions:
                cursor.execute("""
                    INSERT INTO decisions (
                        id, jurisdiction_id, meeting_date, agenda_item,
                        title, summary, outcome, vote_json,
                        staff_recommendation_json, public_input_json,
                        legal_instruments_json, topics, source_documents,
                        extraction_method, financial_impact_cents,
                        extracted_at, valid_from, valid_to
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """, (
                    decision.get('decision_id'),
                    jurisdiction_id,
                    decision.get('meeting_date'),
                    decision.get('agenda_item'),
                    decision.get('title'),
                    decision.get('summary'),
                    decision.get('outcome'),
                    json.dumps(decision.get('vote')) if decision.get('vote') else None,
                    json.dumps(decision.get('staff_recommendation')) if decision.get('staff_recommendation') else None,
                    json.dumps(decision.get('public_input')) if decision.get('public_input') else None,
                    json.dumps(decision.get('legal_instruments')) if decision.get('legal_instruments') else None,
                    json.dumps(decision.get('topics')) if decision.get('topics') else None,
                    json.dumps(decision.get('source_documents')) if decision.get('source_documents') else None,
                    decision.get('extraction_method'),
                    decision.get('financial_impact_cents'),
                    as_of.isoformat(),
                    as_of.isoformat(),
                ))

            conn.commit()
            return len(decisions)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_decisions(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve decisions with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            since: Filter decisions on/after this date (YYYY-MM-DD)
            until: Filter decisions on/before this date (YYYY-MM-DD)
            limit: Maximum number of decisions to return

        Returns:
            List of decision dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        # Build query with temporal filtering
        query = """
            SELECT * FROM decisions
            WHERE jurisdiction_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to > ?)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if since:
            query += " AND meeting_date >= ?"
            params.append(since)

        if until:
            query += " AND meeting_date <= ?"
            params.append(until)

        query += " ORDER BY meeting_date DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries, parsing JSON fields
        decisions = []
        for row in rows:
            decision = dict(row)
            # Parse JSON fields back to Python objects
            for json_field in ['vote_json', 'staff_recommendation_json', 'public_input_json',
                               'legal_instruments_json', 'topics', 'source_documents']:
                if decision.get(json_field):
                    try:
                        decision[json_field] = json.loads(decision[json_field])
                    except json.JSONDecodeError:
                        pass
            decisions.append(decision)

        return decisions

    def get_decision_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current decisions for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) decisions
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM decisions
            WHERE jurisdiction_id = ? AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Chunk Methods (SESSION 367) ==========

    def store_chunks(
        self,
        jurisdiction_id: str,
        chunks: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        meeting_id: Optional[str] = None,
    ) -> int:
        """
        Store PDF chunks with temporal versioning.

        Atomic operation: either all chunks are stored or none.
        Updates existing chunks if IDs match, inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            chunks: List of chunk dictionaries with text, agenda_item, etc.
            as_of: Timestamp for temporal versioning (default: now)
            meeting_id: Optional meeting ID to associate chunks with

        Returns:
            Number of chunks successfully stored

        Raises:
            sqlite3.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Close previous versions (set valid_to)
            cursor.execute("""
                UPDATE chunks
                SET valid_to = ?
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
            """, (as_of.isoformat(), jurisdiction_id))

            # Insert new versions
            for i, chunk in enumerate(chunks):
                # Generate chunk ID if not present
                chunk_id = chunk.get('id') or f"chunk-{i}"

                cursor.execute("""
                    INSERT INTO chunks (
                        id, jurisdiction_id, meeting_id, agenda_item,
                        agenda_title, text, page_start, page_end,
                        chunk_index, total_chunks, source_file, source_type,
                        extracted_at, valid_from, valid_to
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """, (
                    chunk_id,
                    jurisdiction_id,
                    chunk.get('meeting_id'),
                    chunk.get('agenda_item'),
                    chunk.get('agenda_title'),
                    chunk.get('text', ''),
                    chunk.get('page_start'),
                    chunk.get('page_end'),
                    chunk.get('chunk_index', i),
                    chunk.get('total_chunks'),
                    chunk.get('source_file'),
                    chunk.get('source_type', 'agenda_packet'),
                    as_of.isoformat(),
                    as_of.isoformat(),
                ))

            conn.commit()
            return len(chunks)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_chunks(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        meeting_id: Optional[str] = None,
        agenda_item: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            meeting_id: Filter by meeting ID
            agenda_item: Filter by agenda item
            source_type: Filter by source type (agenda_packet, staff_report)
            limit: Maximum number of chunks to return

        Returns:
            List of chunk dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        # Build query with temporal filtering
        query = """
            SELECT * FROM chunks
            WHERE jurisdiction_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to > ?)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if meeting_id:
            query += " AND meeting_id = ?"
            params.append(meeting_id)

        if agenda_item:
            query += " AND agenda_item = ?"
            params.append(agenda_item)

        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)

        query += " ORDER BY chunk_index ASC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        chunks = []
        for row in rows:
            chunks.append(dict(row))

        return chunks

    def get_chunk_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current chunks for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) chunks
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM chunks
            WHERE jurisdiction_id = ? AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Operation Tracking Methods ==========

    def create_operation(
        self,
        operation_id: str,
        jurisdiction_id: str,
        name: str,
    ) -> Dict[str, Any]:
        """
        Create a new operation record with 'pending' status.

        Args:
            operation_id: Unique operation ID (UUID)
            jurisdiction_id: City identifier (e.g., "city-san-rafael")
            name: Operation name (fetch_meetings, discover_videos, etc.)

        Returns:
            Dict with operation record
        """
        started_at = datetime.now()

        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO operations (
                    id, jurisdiction_id, name, status, started_at,
                    progress_percent, items_processed, items_total
                ) VALUES (?, ?, ?, 'pending', ?, 0, 0, 0)
            """, (operation_id, jurisdiction_id, name, started_at.isoformat()))

            conn.commit()
        finally:
            conn.close()

        return {
            "id": operation_id,
            "jurisdiction_id": jurisdiction_id,
            "name": name,
            "status": "pending",
            "started_at": started_at.isoformat(),
            "progress_percent": 0,
            "items_processed": 0,
            "items_total": 0
        }

    def update_operation_status(
        self,
        operation_id: str,
        status: str,
        current_step: Optional[str] = None,
        progress_percent: Optional[float] = None,
        items_processed: Optional[int] = None,
        items_total: Optional[int] = None,
    ) -> bool:
        """
        Update operation progress.

        Args:
            operation_id: Operation ID
            status: New status ('pending', 'running', 'completed', 'failed')
            current_step: Description of current step
            progress_percent: Progress percentage (0-100)
            items_processed: Number of items processed so far
            items_total: Total items to process

        Returns:
            True if update succeeded, False if operation not found
        """
        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Build dynamic update
            updates = ["status = ?"]
            params: List[Any] = [status]

            if current_step is not None:
                updates.append("current_step = ?")
                params.append(current_step)

            if progress_percent is not None:
                updates.append("progress_percent = ?")
                params.append(progress_percent)

            if items_processed is not None:
                updates.append("items_processed = ?")
                params.append(items_processed)

            if items_total is not None:
                updates.append("items_total = ?")
                params.append(items_total)

            params.append(operation_id)

            cursor.execute(f"""
                UPDATE operations
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)

            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            conn.close()

    def complete_operation(
        self,
        operation_id: str,
        result: Dict[str, Any],
        error: Optional[str] = None,
    ) -> bool:
        """
        Mark operation as completed (success or failure).

        Args:
            operation_id: Operation ID
            result: Result dictionary to store as JSON
            error: Error message if failed (triggers 'failed' status)

        Returns:
            True if update succeeded, False if operation not found
        """
        import json

        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            completed_at = datetime.now()
            status = 'failed' if error else 'completed'

            # Calculate duration
            cursor.execute(
                "SELECT started_at FROM operations WHERE id = ?",
                (operation_id,)
            )
            row = cursor.fetchone()
            duration_seconds = None
            if row and row[0]:
                try:
                    started = datetime.fromisoformat(row[0])
                    duration_seconds = (completed_at - started).total_seconds()
                except Exception:
                    pass

            cursor.execute("""
                UPDATE operations
                SET status = ?,
                    completed_at = ?,
                    result_json = ?,
                    error = ?,
                    duration_seconds = ?,
                    progress_percent = 100
                WHERE id = ?
            """, (
                status, completed_at.isoformat(), json.dumps(result),
                error, duration_seconds, operation_id
            ))

            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            conn.close()

    def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get operation by ID.

        Args:
            operation_id: Operation ID

        Returns:
            Operation dict with parsed result field, or None if not found
        """
        import json

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM operations WHERE id = ?", (operation_id,))
            row = cursor.fetchone()

            if not row:
                return None

            result = dict(row)

            # Parse result_json
            if result.get('result_json'):
                try:
                    result['result'] = json.loads(result['result_json'])
                except Exception:
                    result['result'] = None
            else:
                result['result'] = None

            return result
        finally:
            conn.close()

    def get_operations(
        self,
        jurisdiction_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Query operations with optional filters.

        Args:
            jurisdiction_id: Filter by jurisdiction (None = all)
            status: Filter by status (None = all)
            limit: Max results (default 20)

        Returns:
            List of operation dicts, most recent first (by started_at)
        """
        import json

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            query = "SELECT * FROM operations WHERE 1=1"
            params: List[Any] = []

            if jurisdiction_id:
                query += " AND jurisdiction_id = ?"
                params.append(jurisdiction_id)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                op = dict(row)

                # Parse result_json
                if op.get('result_json'):
                    try:
                        op['result'] = json.loads(op['result_json'])
                    except Exception:
                        op['result'] = None
                else:
                    op['result'] = None
                results.append(op)

            return results
        finally:
            conn.close()

    # ========== Issue Methods (SESSION 385) ==========
    # Note: Issues are primarily stored in Postgres for production.
    # SQLite implementation is a stub for protocol compliance.

    def store_issues(
        self,
        jurisdiction_id: str,
        issues: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store 311 issues (stub for SQLite - issues use Postgres in production).

        Args:
            jurisdiction_id: Target jurisdiction
            issues: List of issue dictionaries
            as_of: Timestamp for versioning

        Returns:
            Number of issues stored (0 for SQLite stub)
        """
        # SQLite implementation is a stub - issues are stored in Postgres
        return 0

    def get_issues(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        issue_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve 311 issues (stub for SQLite - issues use Postgres in production).

        Returns:
            Empty list (SQLite stub)
        """
        return []

    def get_issue_count(self, jurisdiction_id: str, provider: Optional[str] = None) -> int:
        """
        Get issue count (stub for SQLite - issues use Postgres in production).

        Returns:
            0 (SQLite stub)
        """
        return 0

    # ========== Municipal Code Methods (Stubs) ==========

    def store_municipal_code(
        self,
        jurisdiction_id: str,
        sections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store municipal code sections (stub for SQLite - uses Postgres in production).

        Returns:
            0 (SQLite stub)
        """
        return 0

    def get_municipal_code(
        self,
        jurisdiction_id: str,
        chapter: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get municipal code sections (stub for SQLite - uses Postgres in production).

        Returns:
            Empty list (SQLite stub)
        """
        return []

    def get_municipal_code_section(
        self,
        jurisdiction_id: str,
        section_number: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific municipal code section (stub for SQLite - uses Postgres in production).

        Returns:
            None (SQLite stub)
        """
        return None

    def get_municipal_code_count(self, jurisdiction_id: str) -> int:
        """
        Get municipal code count (stub for SQLite - uses Postgres in production).

        Returns:
            0 (SQLite stub)
        """
        return 0

    # ========== Video Methods (SESSION 410 - Protocol Compliance) ==========

    def store_videos(
        self,
        jurisdiction_id: str,
        videos: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store videos (stub for SQLite - uses Postgres in production).

        Returns:
            0 (SQLite stub)
        """
        return 0

    def get_videos(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get videos (stub for SQLite - uses Postgres in production).

        Returns:
            Empty list (SQLite stub)
        """
        return []

    def get_video_count(self, jurisdiction_id: str) -> int:
        """
        Get video count (stub for SQLite - uses Postgres in production).

        Returns:
            0 (SQLite stub)
        """
        return 0

    # ========== Transcript Methods (SESSION 410 - Protocol Compliance) ==========

    def store_transcripts(
        self,
        jurisdiction_id: str,
        transcripts: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store transcripts (stub for SQLite - uses Postgres in production).

        Returns:
            0 (SQLite stub)
        """
        return 0

    def get_transcripts(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get transcripts (stub for SQLite - uses Postgres in production).

        Returns:
            Empty list (SQLite stub)
        """
        return []

    def get_transcript(
        self,
        video_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific transcript (stub for SQLite - uses Postgres in production).

        Returns:
            None (SQLite stub)
        """
        return None

    def get_transcript_count(self, jurisdiction_id: str) -> int:
        """
        Get transcript count (stub for SQLite - uses Postgres in production).

        Returns:
            0 (SQLite stub)
        """
        return 0

    # ========== ETL Cost Methods (Postgres-only) ==========

    def store_etl_cost(
        self,
        pipeline: str,
        jurisdiction_id: str,
        items_processed: int,
        cost_usd: float,
        duration_seconds: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        """Store ETL cost (stub for SQLite - uses Postgres in production)."""
        return 0

    def get_etl_costs(
        self,
        jurisdiction_id: Optional[str] = None,
        pipeline: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get ETL costs (stub for SQLite - uses Postgres in production)."""
        return []

    def get_etl_cost_summary(
        self,
        jurisdiction_id: Optional[str] = None,
        pipeline: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get ETL cost summary (stub for SQLite - uses Postgres in production)."""
        return {"total_cost_usd": 0.0, "total_items": 0, "run_count": 0}

    # ========== Legislation Methods (Postgres-only) ==========

    def store_legislation(
        self,
        state: str,
        bills: List[Dict[str, Any]],
        topic: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store legislation (stub for SQLite - uses Postgres in production)."""
        return 0

    def get_legislation(
        self,
        state: str,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get legislation (stub for SQLite - uses Postgres in production)."""
        return []

    def get_legislation_by_bill_id(
        self,
        state: str,
        bill_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get legislation by bill_id (stub for SQLite - uses Postgres in production)."""
        return None

    def get_legislation_count(self, state: str, topic: Optional[str] = None) -> int:
        """Get legislation count (stub for SQLite - uses Postgres in production)."""
        return 0

    def update_legislation_text(
        self,
        state: str,
        updates: List[Dict[str, Any]],
    ) -> int:
        """Update legislation text (stub for SQLite - uses Postgres in production)."""
        return 0

    # ========== Codified Law Methods (Postgres-only) ==========

    def store_codified_law(
        self,
        jurisdiction_id: str,
        sections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        use_copy: bool = True,
    ) -> int:
        """Store codified law (stub for SQLite - uses Postgres in production)."""
        return 0

    def get_codified_law(
        self,
        jurisdiction_id: str,
        title_number: Optional[int] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get codified law (stub for SQLite - uses Postgres in production)."""
        return []

    def search_codified_law(
        self,
        jurisdiction_id: str,
        query: str,
        title_number: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search codified law (stub for SQLite - uses Postgres in production)."""
        return []

    def get_codified_law_count(
        self,
        jurisdiction_id: str,
        title_number: Optional[int] = None,
        include_inactive: bool = False,
    ) -> int:
        """Get codified law count (stub for SQLite - uses Postgres in production)."""
        return 0

    # ========== Executive Orders Methods (Postgres-only) ==========

    def store_executive_orders(
        self,
        orders: List[Dict[str, Any]],
        use_copy: bool = True,
    ) -> int:
        """Store executive orders (stub for SQLite - uses Postgres in production)."""
        return 0

    def get_executive_orders(
        self,
        president: Optional[str] = None,
        eo_number: Optional[int] = None,
        status: Optional[str] = None,
        signing_date_after: Optional[Any] = None,
        signing_date_before: Optional[Any] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get executive orders (stub for SQLite - uses Postgres in production)."""
        return []

    def search_executive_orders(
        self,
        query: str,
        president: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search executive orders (stub for SQLite - uses Postgres in production)."""
        return []

    def get_executive_orders_count(
        self,
        president: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Get executive orders count (stub for SQLite - uses Postgres in production)."""
        return 0

    # ========== Budget Items Methods (Stubs - Uses Postgres in Production) ==========

    def store_budget_items(
        self,
        jurisdiction_id: str,
        items: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        use_copy: bool = True,
    ) -> int:
        """Store budget items (stub for SQLite - uses Postgres in production)."""
        return len(items)

    def get_budget_items(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
        fund: Optional[str] = None,
        department: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get budget items (stub for SQLite - uses Postgres in production)."""
        return []

    def get_budget_summary(
        self,
        jurisdiction_id: str,
        fiscal_year: str,
        group_by: str = "department",
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get budget summary (stub for SQLite - uses Postgres in production)."""
        return []

    def get_budget_items_count(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
    ) -> int:
        """Get budget items count (stub for SQLite - uses Postgres in production)."""
        return 0

    # ========== Federal Awards Methods (SESSION 439/440) ==========

    def store_federal_awards(
        self,
        jurisdiction_id: str,
        awards: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store federal awards with temporal versioning.

        Atomic operation: either all awards are stored or none.
        Updates existing awards if IDs match, inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "san-rafael")
            awards: List of award dictionaries from USAspendingClient
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of awards successfully stored
        """
        if not awards:
            return 0

        as_of = as_of or datetime.now()

        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists
            cursor.execute("""
                INSERT OR IGNORE INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (?, ?, ?)
            """, (
                jurisdiction_id,
                jurisdiction_id.replace('-', ' ').title(),
                as_of.isoformat()
            ))

            # Get award IDs we're updating
            award_ids = [a.get("award_id") for a in awards if a.get("award_id")]

            # Close previous versions for these award_ids
            placeholders = ",".join("?" for _ in award_ids)
            if award_ids:
                cursor.execute(f"""
                    UPDATE federal_awards
                    SET valid_to = ?
                    WHERE jurisdiction_id = ?
                      AND award_id IN ({placeholders})
                      AND valid_to IS NULL
                """, [as_of.isoformat(), jurisdiction_id] + award_ids)

            # Insert new versions
            for award in awards:
                award_id = award.get("award_id")
                if not award_id:
                    continue

                # Build metadata from any extra fields
                metadata = {}
                if "recipient_duns" in award:
                    metadata["recipient_duns"] = award["recipient_duns"]

                cursor.execute("""
                    INSERT INTO federal_awards (
                        award_id, jurisdiction_id, cfda_number, recipient_uei,
                        recipient_name, amount_cents, period_start, period_end,
                        program_name, awarding_agency, funding_agency, award_type,
                        metadata, valid_from, valid_to
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """, (
                    award_id,
                    jurisdiction_id,
                    award.get("cfda_number"),
                    award.get("recipient_uei"),
                    award.get("recipient_name"),
                    award.get("amount_cents"),
                    award.get("period_start"),
                    award.get("period_end"),
                    award.get("program_name"),
                    award.get("awarding_agency"),
                    award.get("funding_agency"),
                    award.get("award_type"),
                    json.dumps(metadata) if metadata else None,
                    as_of.isoformat(),
                ))

            # Update city_state timestamp
            cursor.execute("""
                UPDATE city_states
                SET as_of = ?, updated_at = ?
                WHERE jurisdiction_id = ?
            """, (as_of.isoformat(), datetime.now().isoformat(), jurisdiction_id))

            conn.commit()
            return len(awards)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_federal_awards(
        self,
        jurisdiction_id: str,
        cfda_number: Optional[str] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get federal awards with optional filtering and point-in-time queries.

        Args:
            jurisdiction_id: Target jurisdiction
            cfda_number: Filter by CFDA/Assistance Listing number
            period_start: Filter by period starting on or after this date
            period_end: Filter by period ending on or before this date
            as_of: Point-in-time query (default: current data)
            limit: Maximum number of results

        Returns:
            List of award dictionaries
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Build query
            query = """
                SELECT award_id, jurisdiction_id, cfda_number, recipient_uei,
                       recipient_name, amount_cents, period_start, period_end,
                       program_name, awarding_agency, funding_agency, award_type,
                       metadata, valid_from, valid_to
                FROM federal_awards
                WHERE jurisdiction_id = ?
            """
            params: List[Any] = [jurisdiction_id]

            # Point-in-time filter
            if as_of:
                query += " AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
                as_of_str = as_of.isoformat()
                params.extend([as_of_str, as_of_str])
            else:
                query += " AND valid_to IS NULL"

            # Optional filters
            if cfda_number:
                query += " AND cfda_number = ?"
                params.append(cfda_number)

            if period_start:
                query += " AND period_start >= ?"
                params.append(period_start)

            if period_end:
                query += " AND period_end <= ?"
                params.append(period_end)

            # Order and limit
            query += " ORDER BY amount_cents DESC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            awards = []
            for row in rows:
                award = {
                    "award_id": row["award_id"],
                    "jurisdiction_id": row["jurisdiction_id"],
                    "cfda_number": row["cfda_number"],
                    "recipient_uei": row["recipient_uei"],
                    "recipient_name": row["recipient_name"],
                    "amount_cents": row["amount_cents"],
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "program_name": row["program_name"],
                    "awarding_agency": row["awarding_agency"],
                    "funding_agency": row["funding_agency"],
                    "award_type": row["award_type"],
                }
                # Parse metadata if present
                if row["metadata"]:
                    try:
                        award["metadata"] = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        pass
                awards.append(award)

            return awards

        finally:
            conn.close()

    def get_federal_awards_count(self, jurisdiction_id: str) -> int:
        """Get count of current (non-expired) federal awards."""
        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*)
                FROM federal_awards
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
            """, (jurisdiction_id,))
            return cursor.fetchone()[0]
        finally:
            conn.close()

    # =======================================================================
    # STATE PASS-THROUGH FUNDING
    # =======================================================================

    def store_state_passthrough_funds(
        self,
        jurisdiction_id: str,
        passthroughs: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store state pass-through funding records with temporal versioning.

        Atomic operation: either all records are stored or none.
        Updates existing records if IDs match, inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "san-rafael")
            passthroughs: List of passthrough dictionaries
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of records successfully stored
        """
        if not passthroughs:
            return 0

        as_of = as_of or datetime.now()

        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists
            cursor.execute("""
                INSERT OR IGNORE INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (?, ?, ?)
            """, (
                jurisdiction_id,
                jurisdiction_id.replace('-', ' ').title(),
                as_of.isoformat()
            ))

            # Get passthrough IDs we're updating
            passthrough_ids = [p.get("passthrough_id") for p in passthroughs if p.get("passthrough_id")]

            # Close previous versions for these passthrough_ids
            placeholders = ",".join("?" for _ in passthrough_ids)
            if passthrough_ids:
                cursor.execute(f"""
                    UPDATE state_passthrough_funds
                    SET valid_to = ?
                    WHERE jurisdiction_id = ?
                      AND passthrough_id IN ({placeholders})
                      AND valid_to IS NULL
                """, [as_of.isoformat(), jurisdiction_id] + passthrough_ids)

            # Insert new versions
            for p in passthroughs:
                passthrough_id = p.get("passthrough_id")
                if not passthrough_id:
                    continue

                # Build metadata from any extra fields
                metadata = {
                    k: v for k, v in p.items()
                    if k not in [
                        "passthrough_id", "federal_award_id", "federal_cfda_number",
                        "federal_program_name", "federal_amount_cents", "state_agency",
                        "state_program_name", "state_grant_id", "local_amount_cents",
                        "allocation_percentage", "period_start", "period_end",
                        "federal_fiscal_year", "state_fiscal_year", "source_url", "notes"
                    ]
                }

                cursor.execute("""
                    INSERT INTO state_passthrough_funds (
                        passthrough_id, jurisdiction_id, federal_award_id,
                        federal_cfda_number, federal_program_name, federal_amount_cents,
                        state_agency, state_program_name, state_grant_id,
                        local_amount_cents, allocation_percentage,
                        period_start, period_end,
                        federal_fiscal_year, state_fiscal_year,
                        source_url, notes, metadata, valid_from, valid_to
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """, (
                    passthrough_id,
                    jurisdiction_id,
                    p.get("federal_award_id"),
                    p.get("federal_cfda_number"),
                    p.get("federal_program_name"),
                    p.get("federal_amount_cents"),
                    p.get("state_agency"),
                    p.get("state_program_name"),
                    p.get("state_grant_id"),
                    p.get("local_amount_cents"),
                    p.get("allocation_percentage"),
                    p.get("period_start"),
                    p.get("period_end"),
                    p.get("federal_fiscal_year"),
                    p.get("state_fiscal_year"),
                    p.get("source_url"),
                    p.get("notes"),
                    json.dumps(metadata) if metadata else None,
                    as_of.isoformat(),
                ))

            # Update city_state timestamp
            cursor.execute("""
                UPDATE city_states
                SET as_of = ?, updated_at = ?
                WHERE jurisdiction_id = ?
            """, (as_of.isoformat(), datetime.now().isoformat(), jurisdiction_id))

            conn.commit()
            return len(passthroughs)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_state_passthrough_funds(
        self,
        jurisdiction_id: str,
        state_agency: Optional[str] = None,
        federal_cfda_number: Optional[str] = None,
        federal_award_id: Optional[str] = None,
        federal_fiscal_year: Optional[int] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get state pass-through funds with optional filtering and point-in-time queries.

        Args:
            jurisdiction_id: Target jurisdiction
            state_agency: Filter by state agency (e.g., "HCD", "Caltrans")
            federal_cfda_number: Filter by federal CFDA number
            federal_award_id: Filter by linked federal award
            federal_fiscal_year: Filter by federal fiscal year
            as_of: Point-in-time query (default: current data)
            limit: Maximum number of results

        Returns:
            List of passthrough dictionaries
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Build query
            query = """
                SELECT passthrough_id, jurisdiction_id, federal_award_id,
                       federal_cfda_number, federal_program_name, federal_amount_cents,
                       state_agency, state_program_name, state_grant_id,
                       local_amount_cents, allocation_percentage,
                       period_start, period_end,
                       federal_fiscal_year, state_fiscal_year,
                       source_url, notes, metadata, valid_from, valid_to
                FROM state_passthrough_funds
                WHERE jurisdiction_id = ?
            """
            params: List[Any] = [jurisdiction_id]

            # Point-in-time filter
            if as_of:
                query += " AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
                as_of_str = as_of.isoformat()
                params.extend([as_of_str, as_of_str])
            else:
                query += " AND valid_to IS NULL"

            # Optional filters
            if state_agency:
                query += " AND state_agency = ?"
                params.append(state_agency)

            if federal_cfda_number:
                query += " AND federal_cfda_number = ?"
                params.append(federal_cfda_number)

            if federal_award_id:
                query += " AND federal_award_id = ?"
                params.append(federal_award_id)

            if federal_fiscal_year:
                query += " AND federal_fiscal_year = ?"
                params.append(federal_fiscal_year)

            # Order and limit
            query += " ORDER BY local_amount_cents DESC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            passthroughs = []
            for row in rows:
                p = {
                    "passthrough_id": row["passthrough_id"],
                    "jurisdiction_id": row["jurisdiction_id"],
                    "federal_award_id": row["federal_award_id"],
                    "federal_cfda_number": row["federal_cfda_number"],
                    "federal_program_name": row["federal_program_name"],
                    "federal_amount_cents": row["federal_amount_cents"],
                    "state_agency": row["state_agency"],
                    "state_program_name": row["state_program_name"],
                    "state_grant_id": row["state_grant_id"],
                    "local_amount_cents": row["local_amount_cents"],
                    "allocation_percentage": row["allocation_percentage"],
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "federal_fiscal_year": row["federal_fiscal_year"],
                    "state_fiscal_year": row["state_fiscal_year"],
                    "source_url": row["source_url"],
                    "notes": row["notes"],
                }
                # Parse metadata if present
                if row["metadata"]:
                    try:
                        p["metadata"] = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        pass
                passthroughs.append(p)

            return passthroughs

        finally:
            conn.close()

    def get_state_passthrough_count(self, jurisdiction_id: str) -> int:
        """Get count of current (non-expired) state pass-through records."""
        conn = sqlite3.connect(self._db_path)
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*)
                FROM state_passthrough_funds
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
            """, (jurisdiction_id,))
            return cursor.fetchone()[0]
        finally:
            conn.close()


# Verify protocol compliance at import time
# StorageBackend is @runtime_checkable, so isinstance() works
def _verify_protocol_compliance() -> None:
    """Verify SQLiteBackend implements StorageBackend protocol."""
    _test_instance = SQLiteBackend(":memory:")
    assert isinstance(_test_instance, StorageBackend), (
        "SQLiteBackend must implement StorageBackend protocol"
    )

_verify_protocol_compliance()
