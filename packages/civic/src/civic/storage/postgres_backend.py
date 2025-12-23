"""
PostgresBackend implementation of StorageBackend protocol.

Production-grade storage for multi-user deployments and municipalities
with existing PostgreSQL infrastructure.
Part of the 4-stage pipeline: discover -> ingest -> store -> index.
"""

import json
import time
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from .backend import StorageBackend, StorageStats, StorageValidationResult


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)

# Optional import - psycopg2 only required if PostgresBackend is used
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None  # type: ignore
    PSYCOPG2_AVAILABLE = False


class PostgresBackend:
    """
    PostgreSQL implementation of StorageBackend protocol.

    Provides production-grade storage for multi-user deployments.
    Uses temporal versioning for point-in-time queries.

    Requires psycopg2: pip install psycopg2-binary

    Usage:
        backend = PostgresBackend("postgresql://user:pass@localhost:5432/civic")

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

    def __init__(self, connection_string: str):
        """
        Initialize PostgreSQL storage backend.

        Args:
            connection_string: PostgreSQL connection URL
                e.g., "postgresql://user:pass@localhost:5432/civic"
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PostgresBackend. "
                "Install with: pip install psycopg2-binary"
            )
        self._conn_string = connection_string

    def _get_connection(self):
        """Get a database connection with dict cursor factory."""
        conn = psycopg2.connect(self._conn_string)
        return conn

    @property
    def backend_type(self) -> str:
        """Type identifier: 'postgres'."""
        return "postgres"

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
            conn = self._get_connection()
            cursor = conn.cursor()
            connected = True

            # Check schema - verify required tables exist
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
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
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'meetings' AND table_schema = 'public'
                """)
                columns = {row[0] for row in cursor.fetchall()}
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

        except Exception as e:
            if "psycopg2" in str(type(e).__module__):
                errors.append(f"PostgreSQL error: {str(e)}")
            else:
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

    def _ensure_schema(self, conn) -> None:
        """Create database schema if it doesn't exist."""
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

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_meetings_jurisdiction
            ON meetings(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_meetings_datetime
            ON meetings(meeting_datetime)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_meetings_temporal
            ON meetings(jurisdiction_id, valid_from, valid_to)
        """)

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

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_operations_jurisdiction
            ON operations(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_operations_status
            ON operations(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_operations_started
            ON operations(started_at DESC)
        """)

        conn.commit()

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
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists (ON CONFLICT DO NOTHING for Postgres)
            cursor.execute("""
                INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (%s, %s, %s)
                ON CONFLICT (jurisdiction_id) DO NOTHING
            """, (
                jurisdiction_id,
                jurisdiction_id.replace('-', ' ').title(),
                as_of.isoformat()
            ))

            # Close previous versions (set valid_to)
            cursor.execute("""
                UPDATE meetings
                SET valid_to = %s
                WHERE jurisdiction_id = %s
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

                # Convert datetime fields to ISO strings for consistency
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
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
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
                SET as_of = %s, updated_at = %s
                WHERE jurisdiction_id = %s
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
        # Use RealDictCursor for dict-like row access
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM meetings
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if since:
            query += " AND meeting_datetime >= %s"
            params.append(since.isoformat())

        if until:
            query += " AND meeting_datetime <= %s"
            params.append(until.isoformat())

        query += " ORDER BY meeting_datetime"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries, parsing full_data JSON
        meetings = []
        for row in rows:
            meeting = dict(row)
            # Convert datetime objects to strings for consistency
            for key in ['meeting_datetime', 'comment_deadline', 'last_verified',
                        'valid_from', 'valid_to', 'created_at', 'updated_at']:
                if key in meeting and meeting[key] is not None:
                    if isinstance(meeting[key], datetime):
                        meeting[key] = meeting[key].isoformat()
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
            WHERE jurisdiction_id = %s AND valid_to IS NULL
        """, (jurisdiction_id,))
        meeting_count = cursor.fetchone()[0]

        # Count agenda items
        cursor.execute("""
            SELECT COUNT(*) FROM agenda_items
            WHERE valid_to IS NULL
              AND meeting_id IN (
                  SELECT id FROM meetings
                  WHERE jurisdiction_id = %s AND valid_to IS NULL
              )
        """, (jurisdiction_id,))
        agenda_item_count = cursor.fetchone()[0]

        # Date range and last updated
        cursor.execute("""
            SELECT MIN(meeting_datetime), MAX(meeting_datetime), MAX(valid_from)
            FROM meetings
            WHERE jurisdiction_id = %s AND valid_to IS NULL
        """, (jurisdiction_id,))
        result = cursor.fetchone()
        earliest = result[0]
        latest = result[1]
        last_updated = result[2]

        # Get database size (Postgres-specific)
        cursor.execute("""
            SELECT pg_database_size(current_database())
        """)
        size_bytes = cursor.fetchone()[0]

        conn.close()

        # Parse datetime values (Postgres returns datetime objects)
        earliest_dt = earliest if isinstance(earliest, datetime) else None
        latest_dt = latest if isinstance(latest, datetime) else None
        last_updated_dt = last_updated if isinstance(last_updated, datetime) else None

        # Handle string datetime values (if timezone aware)
        if earliest and not earliest_dt:
            try:
                earliest_dt = datetime.fromisoformat(str(earliest))
            except (ValueError, TypeError):
                pass
        if latest and not latest_dt:
            try:
                latest_dt = datetime.fromisoformat(str(latest))
            except (ValueError, TypeError):
                pass
        if last_updated and not last_updated_dt:
            try:
                last_updated_dt = datetime.fromisoformat(str(last_updated))
            except (ValueError, TypeError):
                pass

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
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            if meeting_ids is None:
                # Soft delete all meetings for jurisdiction
                cursor.execute("""
                    UPDATE meetings
                    SET valid_to = %s
                    WHERE jurisdiction_id = %s
                      AND valid_to IS NULL
                """, (now, jurisdiction_id))
            else:
                # Soft delete specific meetings using ANY array
                cursor.execute("""
                    UPDATE meetings
                    SET valid_to = %s
                    WHERE jurisdiction_id = %s
                      AND id = ANY(%s)
                      AND valid_to IS NULL
                """, (now, jurisdiction_id, meeting_ids))

            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO operations (
                    id, jurisdiction_id, name, status, started_at,
                    progress_percent, items_processed, items_total
                ) VALUES (%s, %s, %s, 'pending', %s, 0, 0, 0)
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
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Build dynamic update
            updates = ["status = %s"]
            params: List[Any] = [status]

            if current_step is not None:
                updates.append("current_step = %s")
                params.append(current_step)

            if progress_percent is not None:
                updates.append("progress_percent = %s")
                params.append(progress_percent)

            if items_processed is not None:
                updates.append("items_processed = %s")
                params.append(items_processed)

            if items_total is not None:
                updates.append("items_total = %s")
                params.append(items_total)

            params.append(operation_id)

            cursor.execute(f"""
                UPDATE operations
                SET {', '.join(updates)}
                WHERE id = %s
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
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            completed_at = datetime.now()
            status = 'failed' if error else 'completed'

            # Calculate duration
            cursor.execute(
                "SELECT started_at FROM operations WHERE id = %s",
                (operation_id,)
            )
            row = cursor.fetchone()
            duration_seconds = None
            if row and row[0]:
                try:
                    started = row[0]
                    if isinstance(started, str):
                        started = datetime.fromisoformat(started)
                    duration_seconds = (completed_at - started).total_seconds()
                except Exception:
                    pass

            cursor.execute("""
                UPDATE operations
                SET status = %s,
                    completed_at = %s,
                    result_json = %s,
                    error = %s,
                    duration_seconds = %s,
                    progress_percent = 100
                WHERE id = %s
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
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            cursor.execute("SELECT * FROM operations WHERE id = %s", (operation_id,))
            row = cursor.fetchone()

            if not row:
                return None

            result = dict(row)

            # Convert datetime objects to ISO strings
            for key in ['started_at', 'completed_at']:
                if key in result and result[key] is not None:
                    if isinstance(result[key], datetime):
                        result[key] = result[key].isoformat()

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
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            query = "SELECT * FROM operations WHERE 1=1"
            params: List[Any] = []

            if jurisdiction_id:
                query += " AND jurisdiction_id = %s"
                params.append(jurisdiction_id)

            if status:
                query += " AND status = %s"
                params.append(status)

            query += " ORDER BY started_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                op = dict(row)

                # Convert datetime objects to ISO strings
                for key in ['started_at', 'completed_at']:
                    if key in op and op[key] is not None:
                        if isinstance(op[key], datetime):
                            op[key] = op[key].isoformat()

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


# Verify protocol compliance at import time (only if psycopg2 available)
# StorageBackend is @runtime_checkable, so isinstance() works
def _verify_protocol_compliance() -> None:
    """Verify PostgresBackend implements StorageBackend protocol."""
    if not PSYCOPG2_AVAILABLE:
        return  # Skip verification if psycopg2 not installed
    # Can't instantiate without a connection, but we can check class attributes
    # The actual isinstance check happens in tests with a real instance
    required_methods = [
        'backend_type', 'validate', 'store_meetings',
        'get_meetings', 'get_stats', 'delete_meetings',
        # Operation tracking methods
        'create_operation', 'update_operation_status', 'complete_operation',
        'get_operation', 'get_operations'
    ]
    for method in required_methods:
        assert hasattr(PostgresBackend, method), (
            f"PostgresBackend must implement {method}"
        )


_verify_protocol_compliance()
