"""
PostgresBackend implementation of StorageBackend protocol.

Production-grade storage for multi-user deployments and municipalities
with existing PostgreSQL infrastructure.
Part of the 4-stage pipeline: discover -> ingest -> store -> index.
"""

import json
import time
from datetime import datetime, date
from io import StringIO
from typing import Any, Dict, List, Optional

from .backend import StorageBackend, StorageStats, StorageValidationResult
from .integrity import compute_transcript_hash, compute_chunk_hash, compute_decision_hash


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

        # Decisions table (SESSION 366)
        # Stores extracted decisions from meeting minutes
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
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Decision indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_jurisdiction
            ON decisions(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_meeting_date
            ON decisions(meeting_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_outcome
            ON decisions(outcome)
        """)

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
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_jurisdiction
            ON chunks(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_meeting
            ON chunks(meeting_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_agenda_item
            ON chunks(agenda_item)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_source_type
            ON chunks(source_type)
        """)

        # Videos table (SESSION 379)
        # Stores YouTube video metadata discovered from meeting pages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                meeting_url TEXT,
                title TEXT,
                date TEXT,
                youtube_url TEXT,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Video indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_videos_jurisdiction
            ON videos(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_videos_discovered
            ON videos(discovered_at DESC)
        """)

        # Transcripts table (SESSION 381)
        # Stores AssemblyAI transcripts with speaker diarization
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                video_id TEXT NOT NULL,
                transcript JSONB NOT NULL,
                text TEXT,
                duration_seconds INTEGER,
                word_count INTEGER,
                speakers_count INTEGER,
                utterances_count INTEGER,
                processing_service TEXT DEFAULT 'assemblyai',
                cost_usd REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Transcript indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transcripts_jurisdiction
            ON transcripts(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transcripts_video
            ON transcripts(video_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transcripts_created
            ON transcripts(created_at DESC)
        """)

        # Issues table (SESSION 385)
        # Stores 311 issues from providers like SeeClickFix, PublicStuff, etc.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                issue_type TEXT,
                status TEXT DEFAULT 'open',
                address TEXT,
                latitude REAL,
                longitude REAL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                closed_at TIMESTAMP,
                reporter_name TEXT,
                images JSONB,
                provider_metadata JSONB,
                stored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                UNIQUE (provider, external_id, valid_from),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Issue indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_jurisdiction
            ON issues(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_provider
            ON issues(provider)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_status
            ON issues(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_type
            ON issues(issue_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_created
            ON issues(created_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_location
            ON issues(latitude, longitude) WHERE latitude IS NOT NULL
        """)

        # ETL Costs table (SESSION 397)
        # Tracks costs for transcription, research, and other ETL pipelines
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS etl_costs (
                id SERIAL PRIMARY KEY,
                pipeline VARCHAR(50) NOT NULL,
                jurisdiction_id VARCHAR(100) NOT NULL,
                run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                items_processed INTEGER,
                cost_usd DECIMAL(10,4),
                duration_seconds INTEGER,
                notes TEXT,
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id)
            )
        """)

        # ETL costs indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_etl_costs_jurisdiction
            ON etl_costs(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_etl_costs_pipeline
            ON etl_costs(pipeline)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_etl_costs_run_date
            ON etl_costs(run_date DESC)
        """)

        # Municipal code table (with temporal versioning)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS municipal_code (
                id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                section_number TEXT NOT NULL,
                section_title TEXT NOT NULL,
                full_text TEXT NOT NULL,
                chapter TEXT NOT NULL,
                chapter_title TEXT,
                title_number TEXT,
                title_name TEXT,
                node_id TEXT,
                ordinance_history TEXT,
                source TEXT DEFAULT 'municode',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Municipal code indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_municipal_code_jurisdiction
            ON municipal_code(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_municipal_code_section
            ON municipal_code(section_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_municipal_code_chapter
            ON municipal_code(chapter)
        """)

        # Legislation table (SESSION 402)
        # Stores state and federal legislation affecting local governance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS legislation (
                id SERIAL PRIMARY KEY,
                bill_id TEXT NOT NULL,
                state TEXT NOT NULL,
                jurisdiction_id TEXT,
                bill_number TEXT,
                bill_name TEXT,
                status TEXT,
                enacted_date DATE,
                summary TEXT,
                leverage_point TEXT,
                full_text TEXT,
                official_url TEXT,
                keywords JSONB,
                topic TEXT,
                local_implementation_required BOOLEAN,
                local_deadline DATE,
                legiscan_id INTEGER,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                UNIQUE (bill_id, state, valid_from),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Legislation indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_legislation_state
            ON legislation(state)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_legislation_topic
            ON legislation(topic)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_legislation_bill_id
            ON legislation(bill_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_legislation_status
            ON legislation(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_legislation_temporal
            ON legislation(state, valid_from, valid_to)
        """)

        # Codified Law table (SESSION 428)
        # Stores enacted statutes (U.S. Code, CA Codes) for what_applies() queries
        # Unlike legislation (bills/proposals), this is compiled, enacted law
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS codified_law (
                id SERIAL PRIMARY KEY,
                citation TEXT NOT NULL,
                title_number INTEGER NOT NULL,
                title_name TEXT,
                section_number TEXT NOT NULL,
                heading TEXT,
                text TEXT,
                jurisdiction_id TEXT NOT NULL,
                status TEXT,
                chapter TEXT,
                subchapter TEXT,
                identifier TEXT NOT NULL,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                UNIQUE (identifier, jurisdiction_id, valid_from),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        # Codified law indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_codified_law_jurisdiction
            ON codified_law(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_codified_law_title
            ON codified_law(title_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_codified_law_citation
            ON codified_law(citation)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_codified_law_status
            ON codified_law(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_codified_law_temporal
            ON codified_law(jurisdiction_id, valid_from, valid_to)
        """)

        # Executive Orders table (SESSION 432)
        # Stores presidential executive orders from Federal Register
        # Separate from codified_law due to different structure (flat vs hierarchical)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executive_orders (
                id SERIAL PRIMARY KEY,
                eo_number INTEGER,
                document_number TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                abstract TEXT,
                full_text TEXT,
                president TEXT NOT NULL,
                president_id TEXT,
                signing_date DATE,
                publication_date DATE,
                html_url TEXT,
                pdf_url TEXT,
                raw_text_url TEXT,
                status TEXT DEFAULT 'active',
                revoked_by_eo INTEGER,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Executive orders indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_executive_orders_eo_number
            ON executive_orders(eo_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_executive_orders_president
            ON executive_orders(president)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_executive_orders_signing_date
            ON executive_orders(signing_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_executive_orders_status
            ON executive_orders(status)
        """)

        # Refresh metadata table (SESSION 423)
        # Tracks last fetch times for incremental pipeline automation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refresh_metadata (
                id SERIAL PRIMARY KEY,
                jurisdiction_id VARCHAR(100) NOT NULL,
                corpus_type VARCHAR(50) NOT NULL,
                source_name VARCHAR(100),
                last_fetch_at TIMESTAMP,
                last_fetch_hash VARCHAR(64),
                items_fetched INTEGER DEFAULT 0,
                items_stored INTEGER DEFAULT 0,
                next_scheduled_at TIMESTAMP,
                fetch_window_days INTEGER DEFAULT 30,
                status VARCHAR(20) DEFAULT 'pending',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(jurisdiction_id, corpus_type, source_name),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id)
            )
        """)

        # Refresh metadata indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_refresh_metadata_jurisdiction
            ON refresh_metadata(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_refresh_metadata_corpus
            ON refresh_metadata(corpus_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_refresh_metadata_status
            ON refresh_metadata(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_refresh_metadata_next_scheduled
            ON refresh_metadata(next_scheduled_at)
            WHERE next_scheduled_at IS NOT NULL
        """)

        # Migration: Add full_text column if not exists (SESSION 418)
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'legislation'
                    AND column_name = 'full_text'
                ) THEN
                    ALTER TABLE legislation
                    ADD COLUMN full_text TEXT;
                END IF;
            END $$;
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
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Insert new versions (close previous versions only for matching IDs)
            for decision in decisions:
                # Support both 'id' and 'decision_id' field names
                decision_id = decision.get('id') or decision.get('decision_id')

                # Close previous version of this specific decision only
                cursor.execute("""
                    UPDATE decisions
                    SET valid_to = %s
                    WHERE jurisdiction_id = %s
                      AND id = %s
                      AND valid_to IS NULL
                """, (as_of.isoformat(), jurisdiction_id, decision_id))

                # Compute content hash for data integrity verification
                content_hash = compute_decision_hash(decision)

                cursor.execute("""
                    INSERT INTO decisions (
                        id, jurisdiction_id, meeting_date, agenda_item,
                        title, summary, outcome, vote_json,
                        staff_recommendation_json, public_input_json,
                        legal_instruments_json, topics, source_documents,
                        extraction_method, extracted_at, valid_from, valid_to, content_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
                """, (
                    decision_id,
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
                    as_of.isoformat(),
                    as_of.isoformat(),
                    content_hash,
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM decisions
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if since:
            query += " AND meeting_date >= %s"
            params.append(since)

        if until:
            query += " AND meeting_date <= %s"
            params.append(until)

        query += " ORDER BY meeting_date DESC"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries, parsing JSON fields
        decisions = []
        for row in rows:
            decision = dict(row)
            # Convert datetime objects to ISO strings
            for key in ['extracted_at', 'valid_from', 'valid_to']:
                if key in decision and decision[key] is not None:
                    if isinstance(decision[key], datetime):
                        decision[key] = decision[key].isoformat()
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
            WHERE jurisdiction_id = %s AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Agenda Item Methods (SESSION 388) ==========

    def store_agenda_items(
        self,
        meeting_id: str,
        agenda_items: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store agenda items with temporal versioning.

        Atomic operation: either all items are stored or none.
        Closes existing items for this meeting and inserts new versions.

        Args:
            meeting_id: Meeting ID these agenda items belong to
            agenda_items: List of agenda item dictionaries from extraction
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of agenda items successfully stored

        Raises:
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Close previous versions for this meeting (set valid_to)
            cursor.execute("""
                UPDATE agenda_items
                SET valid_to = %s
                WHERE meeting_id = %s
                  AND valid_to IS NULL
            """, (as_of.isoformat(), meeting_id))

            # Insert new versions
            for item in agenda_items:
                # Generate ID if not provided
                item_id = item.get('id') or f"{meeting_id}-{item.get('item_number', item.get('item_ref', 'unknown'))}"

                # Handle project_types (array -> first element for project_type column)
                project_types = item.get('project_types', [])
                project_type = project_types[0] if project_types else item.get('project_type')

                cursor.execute("""
                    INSERT INTO agenda_items (
                        id, meeting_id, item_number, title, description,
                        project_type, actionability, impact_level,
                        financial_impact_cents, summary, why_it_matters,
                        participation_guide, extracted_at, valid_from, valid_to, full_data
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
                """, (
                    item_id,
                    meeting_id,
                    item.get('item_number') or item.get('item_ref'),
                    item.get('title'),
                    item.get('description'),
                    project_type,
                    'actionable' if item.get('actionable') else 'informational',
                    item.get('impact_level'),
                    item.get('financial_impact_cents'),
                    item.get('summary'),
                    item.get('why_it_matters') or item.get('actionable_reason'),
                    item.get('participation_guide') or item.get('public_comment_info'),
                    as_of.isoformat(),
                    as_of.isoformat(),
                    json.dumps(item, cls=DateTimeEncoder),
                ))

            conn.commit()
            return len(agenda_items)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_agenda_items(
        self,
        meeting_id: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve agenda items with optional filtering.

        Args:
            meeting_id: Filter by specific meeting ID
            jurisdiction_id: Filter by jurisdiction (requires join with meetings)
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of items to return

        Returns:
            List of agenda item dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query based on filters
        if meeting_id:
            query = """
                SELECT * FROM agenda_items
                WHERE meeting_id = %s
                  AND valid_from <= %s
                  AND (valid_to IS NULL OR valid_to > %s)
                ORDER BY item_number
            """
            params = [meeting_id, as_of.isoformat(), as_of.isoformat()]
        elif jurisdiction_id:
            # Join with meetings to filter by jurisdiction
            query = """
                SELECT a.* FROM agenda_items a
                JOIN meetings m ON a.meeting_id = m.id
                WHERE m.jurisdiction_id = %s
                  AND a.valid_from <= %s
                  AND (a.valid_to IS NULL OR a.valid_to > %s)
                  AND m.valid_to IS NULL
                ORDER BY m.meeting_datetime DESC, a.item_number
            """
            params = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]
        else:
            query = """
                SELECT * FROM agenda_items
                WHERE valid_from <= %s
                  AND (valid_to IS NULL OR valid_to > %s)
                ORDER BY meeting_id, item_number
            """
            params = [as_of.isoformat(), as_of.isoformat()]

        if limit:
            query += f" LIMIT {int(limit)}"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to regular dicts
        items = []
        for row in rows:
            item = dict(row)
            # Parse full_data if present
            if item.get('full_data'):
                try:
                    item['full_data'] = json.loads(item['full_data'])
                except json.JSONDecodeError:
                    pass
            items.append(item)

        return items

    def get_agenda_item_count(self, jurisdiction_id: Optional[str] = None) -> int:
        """
        Get count of current agenda items.

        Args:
            jurisdiction_id: Filter by jurisdiction (optional)

        Returns:
            Number of current (non-expired) agenda items
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        if jurisdiction_id:
            cursor.execute("""
                SELECT COUNT(*) FROM agenda_items a
                JOIN meetings m ON a.meeting_id = m.id
                WHERE m.jurisdiction_id = %s
                  AND a.valid_to IS NULL
                  AND m.valid_to IS NULL
            """, (jurisdiction_id,))
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM agenda_items
                WHERE valid_to IS NULL
            """)

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
            meeting_id: If provided, only close/replace chunks for this meeting.
                       If None, close ALL chunks for jurisdiction (snapshot mode).

        Returns:
            Number of chunks successfully stored

        Raises:
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Close previous versions (set valid_to)
            # If meeting_id provided, only close chunks for that meeting (incremental)
            # Otherwise, close all chunks for jurisdiction (snapshot mode)
            if meeting_id:
                cursor.execute("""
                    UPDATE chunks
                    SET valid_to = %s
                    WHERE jurisdiction_id = %s
                      AND meeting_id = %s
                      AND valid_to IS NULL
                """, (as_of.isoformat(), jurisdiction_id, meeting_id))
            else:
                cursor.execute("""
                    UPDATE chunks
                    SET valid_to = %s
                    WHERE jurisdiction_id = %s
                      AND valid_to IS NULL
                """, (as_of.isoformat(), jurisdiction_id))

            # Insert new versions
            for i, chunk in enumerate(chunks):
                # Generate chunk ID if not present
                chunk_id = chunk.get('id') or f"chunk-{i}"

                # Compute content hash for data integrity verification
                text = chunk.get('text', '')
                content_hash = compute_chunk_hash(text)

                cursor.execute("""
                    INSERT INTO chunks (
                        id, jurisdiction_id, meeting_id, agenda_item,
                        agenda_title, text, page_start, page_end,
                        chunk_index, total_chunks, source_file, source_type,
                        extracted_at, valid_from, valid_to, content_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
                """, (
                    chunk_id,
                    jurisdiction_id,
                    chunk.get('meeting_id'),
                    chunk.get('agenda_item'),
                    chunk.get('agenda_title'),
                    text,
                    chunk.get('page_start'),
                    chunk.get('page_end'),
                    chunk.get('chunk_index', i),
                    chunk.get('total_chunks'),
                    chunk.get('source_file'),
                    chunk.get('source_type', 'agenda_packet'),
                    as_of.isoformat(),
                    as_of.isoformat(),
                    content_hash,
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM chunks
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if meeting_id:
            query += " AND meeting_id = %s"
            params.append(meeting_id)

        if agenda_item:
            query += " AND agenda_item = %s"
            params.append(agenda_item)

        if source_type:
            query += " AND source_type = %s"
            params.append(source_type)

        query += " ORDER BY chunk_index ASC"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        chunks = []
        for row in rows:
            chunk = dict(row)
            # Convert datetime objects to ISO strings
            for key in ['extracted_at', 'valid_from', 'valid_to']:
                if key in chunk and chunk[key] is not None:
                    if isinstance(chunk[key], datetime):
                        chunk[key] = chunk[key].isoformat()
            chunks.append(chunk)

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
            WHERE jurisdiction_id = %s AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Video Methods (SESSION 379) ==========

    def store_videos(
        self,
        jurisdiction_id: str,
        videos: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store YouTube video metadata with temporal versioning.

        Atomic operation: either all videos are stored or none.
        Uses upsert semantics - closes previous versions and inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            videos: List of video dictionaries with id, meeting_url, title, date, youtube_url
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of videos successfully stored

        Raises:
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists
            cursor.execute("""
                INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (%s, %s, %s)
                ON CONFLICT (jurisdiction_id) DO NOTHING
            """, (
                jurisdiction_id,
                jurisdiction_id.replace('-', ' ').title(),
                as_of.isoformat()
            ))

            # Close previous versions for videos being updated
            video_ids = [v.get('id') or v.get('video_id') for v in videos]
            for video_id in video_ids:
                if video_id:
                    cursor.execute("""
                        UPDATE videos
                        SET valid_to = %s
                        WHERE jurisdiction_id = %s
                          AND id = %s
                          AND valid_to IS NULL
                    """, (as_of.isoformat(), jurisdiction_id, video_id))

            # Insert new versions
            for video in videos:
                # Support both 'id' and 'video_id' keys
                video_id = video.get('id') or video.get('video_id')
                if not video_id:
                    continue  # Skip videos without ID

                cursor.execute("""
                    INSERT INTO videos (
                        id, jurisdiction_id, meeting_url, title,
                        date, youtube_url, discovered_at, valid_from, valid_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """, (
                    video_id,
                    jurisdiction_id,
                    video.get('meeting_url'),
                    video.get('title'),
                    video.get('date'),
                    video.get('youtube_url'),
                    as_of.isoformat(),
                    as_of.isoformat(),
                ))

            conn.commit()
            return len([v for v in videos if v.get('id') or v.get('video_id')])

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_videos(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve videos with temporal filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of videos to return

        Returns:
            List of video dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM videos
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
            ORDER BY discovered_at DESC
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        videos = []
        for row in rows:
            video = dict(row)
            # Convert datetime objects to ISO strings
            for key in ['discovered_at', 'valid_from', 'valid_to']:
                if key in video and video[key] is not None:
                    if isinstance(video[key], datetime):
                        video[key] = video[key].isoformat()
            videos.append(video)

        return videos

    def get_video_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current videos for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) videos
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM videos
            WHERE jurisdiction_id = %s AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Transcript Methods (SESSION 381) ==========

    def store_transcripts(
        self,
        jurisdiction_id: str,
        transcripts: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store AssemblyAI transcripts with temporal versioning.

        Atomic operation: either all transcripts are stored or none.
        Uses upsert semantics - closes previous versions and inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            transcripts: List of transcript dictionaries with video_id, utterances, etc.
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of transcripts successfully stored

        Raises:
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists
            cursor.execute("""
                INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (%s, %s, %s)
                ON CONFLICT (jurisdiction_id) DO NOTHING
            """, (
                jurisdiction_id,
                jurisdiction_id.replace('-', ' ').title(),
                as_of.isoformat()
            ))

            # Close previous versions for transcripts being updated
            video_ids = [t.get('video_id') for t in transcripts]
            for video_id in video_ids:
                if video_id:
                    cursor.execute("""
                        UPDATE transcripts
                        SET valid_to = %s
                        WHERE jurisdiction_id = %s
                          AND video_id = %s
                          AND valid_to IS NULL
                    """, (as_of.isoformat(), jurisdiction_id, video_id))

            # Insert new versions
            count = 0
            for transcript in transcripts:
                video_id = transcript.get('video_id')
                if not video_id:
                    continue  # Skip transcripts without video_id

                # Extract text from utterances if not provided
                text = transcript.get('text')
                if not text and transcript.get('utterances'):
                    text = ' '.join(
                        u.get('text', '') for u in transcript['utterances']
                    )

                # Calculate word count if not provided
                word_count = transcript.get('word_count')
                if word_count is None and text:
                    word_count = len(text.split())

                # Generate a unique ID for this transcript version
                import uuid
                transcript_id = str(uuid.uuid4())

                # Compute content hash for data integrity verification
                content_hash = compute_transcript_hash(transcript)

                cursor.execute("""
                    INSERT INTO transcripts (
                        id, jurisdiction_id, video_id, transcript,
                        text, duration_seconds, word_count, speakers_count,
                        utterances_count, processing_service, cost_usd,
                        created_at, valid_from, valid_to, content_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
                """, (
                    transcript_id,
                    jurisdiction_id,
                    video_id,
                    json.dumps(transcript, cls=DateTimeEncoder),
                    text,
                    int(transcript.get('audio_duration_minutes', 0) * 60) if transcript.get('audio_duration_minutes') else None,
                    word_count,
                    transcript.get('speakers_count'),
                    transcript.get('utterances_count'),
                    transcript.get('processing_service', 'assemblyai'),
                    transcript.get('cost_usd'),
                    transcript.get('processed_at', as_of.isoformat()),
                    as_of.isoformat(),
                    content_hash,
                ))
                count += 1

            conn.commit()
            return count

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_transcripts(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve transcripts with temporal filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of transcripts to return

        Returns:
            List of transcript dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM transcripts
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
            ORDER BY created_at DESC
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        transcripts = []
        for row in rows:
            transcript = dict(row)
            # Parse the JSONB transcript field
            if 'transcript' in transcript and isinstance(transcript['transcript'], str):
                transcript['transcript'] = json.loads(transcript['transcript'])
            # Convert datetime objects to ISO strings
            for key in ['created_at', 'valid_from', 'valid_to']:
                if key in transcript and transcript[key] is not None:
                    if isinstance(transcript[key], datetime):
                        transcript[key] = transcript[key].isoformat()
            transcripts.append(transcript)

        return transcripts

    def get_transcript(
        self,
        video_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific transcript by video_id.

        Args:
            video_id: YouTube video ID
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            Transcript dictionary or None if not found
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM transcripts
            WHERE video_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
            ORDER BY created_at DESC
            LIMIT 1
        """, (video_id, as_of.isoformat(), as_of.isoformat()))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        transcript = dict(row)
        # Parse the JSONB transcript field
        if 'transcript' in transcript and isinstance(transcript['transcript'], str):
            transcript['transcript'] = json.loads(transcript['transcript'])
        # Convert datetime objects to ISO strings
        for key in ['created_at', 'valid_from', 'valid_to']:
            if key in transcript and transcript[key] is not None:
                if isinstance(transcript[key], datetime):
                    transcript[key] = transcript[key].isoformat()

        return transcript

    def get_transcript_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current transcripts for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) transcripts
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM transcripts
            WHERE jurisdiction_id = %s AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Municipal Code Methods (SESSION 400) ==========

    def store_municipal_code(
        self,
        jurisdiction_id: str,
        sections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store municipal code sections with temporal versioning.

        Atomic operation: either all sections are stored or none.
        Uses upsert semantics - closes previous versions and inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            sections: List of section dictionaries with section_number, section_title, etc.
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of sections successfully stored

        Raises:
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists
            cursor.execute("""
                INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (%s, %s, %s)
                ON CONFLICT (jurisdiction_id) DO NOTHING
            """, (
                jurisdiction_id,
                jurisdiction_id.replace('-', ' ').title(),
                as_of.isoformat()
            ))

            # Close previous versions for this jurisdiction
            cursor.execute("""
                UPDATE municipal_code
                SET valid_to = %s
                WHERE jurisdiction_id = %s
                  AND valid_to IS NULL
            """, (as_of.isoformat(), jurisdiction_id))

            # Insert new versions
            count = 0
            for section in sections:
                section_number = section.get('section_number')
                if not section_number:
                    continue  # Skip sections without section_number

                # Generate a unique ID for this section version
                import uuid
                section_id = str(uuid.uuid4())

                cursor.execute("""
                    INSERT INTO municipal_code (
                        id, jurisdiction_id, section_number, section_title,
                        full_text, chapter, chapter_title, title_number,
                        title_name, node_id, ordinance_history, source,
                        created_at, valid_from, valid_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """, (
                    section_id,
                    jurisdiction_id,
                    section_number,
                    section.get('section_title', ''),
                    section.get('full_text', ''),
                    section.get('chapter', ''),
                    section.get('chapter_title'),
                    section.get('title_number'),
                    section.get('title_name'),
                    section.get('node_id'),
                    section.get('ordinance_history'),
                    section.get('source', 'municode'),
                    as_of.isoformat(),
                    as_of.isoformat(),
                ))
                count += 1

            conn.commit()
            return count

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_municipal_code(
        self,
        jurisdiction_id: str,
        chapter: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve municipal code sections with temporal filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            chapter: Filter to specific chapter (e.g., "1.04")
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of sections to return

        Returns:
            List of section dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM municipal_code
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if chapter:
            query += " AND chapter = %s"
            params.append(chapter)

        query += " ORDER BY section_number"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        sections = []
        for row in rows:
            section = dict(row)
            # Convert datetime objects to ISO strings
            for key in ['created_at', 'valid_from', 'valid_to']:
                if key in section and section[key] is not None:
                    if isinstance(section[key], datetime):
                        section[key] = section[key].isoformat()
            sections.append(section)

        return sections

    def get_municipal_code_section(
        self,
        jurisdiction_id: str,
        section_number: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific municipal code section by section number.

        Args:
            jurisdiction_id: Target jurisdiction
            section_number: Section identifier (e.g., "1.04.010")
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            Section dictionary or None if not found
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM municipal_code
            WHERE jurisdiction_id = %s
              AND section_number = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
            ORDER BY created_at DESC
            LIMIT 1
        """, (jurisdiction_id, section_number, as_of.isoformat(), as_of.isoformat()))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        section = dict(row)
        # Convert datetime objects to ISO strings
        for key in ['created_at', 'valid_from', 'valid_to']:
            if key in section and section[key] is not None:
                if isinstance(section[key], datetime):
                    section[key] = section[key].isoformat()

        return section

    def get_municipal_code_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current municipal code sections for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) sections
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM municipal_code
            WHERE jurisdiction_id = %s AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Issue Methods (SESSION 385) ==========

    def store_issues(
        self,
        jurisdiction_id: str,
        issues: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store 311 issues with temporal versioning.

        Atomic operation: either all issues are stored or none.
        Uses upsert semantics based on (provider, external_id).

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            issues: List of issue dictionaries (from NormalizedIssue.to_dict())
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of issues successfully stored

        Raises:
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Ensure city_state exists
            cursor.execute("""
                INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (%s, %s, %s)
                ON CONFLICT (jurisdiction_id) DO NOTHING
            """, (
                jurisdiction_id,
                jurisdiction_id.replace('-', ' ').title(),
                as_of.isoformat()
            ))

            # Close previous versions for issues being updated
            # Group by (provider, external_id) to handle updates
            for issue in issues:
                provider = issue.get('provider')
                external_id = issue.get('external_id')
                if provider and external_id:
                    cursor.execute("""
                        UPDATE issues
                        SET valid_to = %s
                        WHERE jurisdiction_id = %s
                          AND provider = %s
                          AND external_id = %s
                          AND valid_to IS NULL
                    """, (as_of.isoformat(), jurisdiction_id, provider, external_id))

            # Insert new versions
            count = 0
            for issue in issues:
                provider = issue.get('provider')
                external_id = issue.get('external_id')
                if not provider or not external_id:
                    continue  # Skip issues without required fields

                # Generate issue ID if not present
                issue_id = issue.get('id') or f"{provider}-{external_id}"

                # Parse datetime strings if needed
                created_at = issue.get('created_at')
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    except ValueError:
                        created_at = None

                updated_at = issue.get('updated_at')
                if isinstance(updated_at, str):
                    try:
                        updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                    except ValueError:
                        updated_at = None

                closed_at = issue.get('closed_at')
                if isinstance(closed_at, str):
                    try:
                        closed_at = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
                    except ValueError:
                        closed_at = None

                cursor.execute("""
                    INSERT INTO issues (
                        id, jurisdiction_id, provider, external_id,
                        title, description, issue_type, status,
                        address, latitude, longitude,
                        created_at, updated_at, closed_at,
                        reporter_name, images, provider_metadata,
                        stored_at, valid_from, valid_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """, (
                    issue_id,
                    jurisdiction_id,
                    provider,
                    external_id,
                    issue.get('title', ''),
                    issue.get('description', ''),
                    issue.get('issue_type'),
                    issue.get('status', 'open'),
                    issue.get('address'),
                    issue.get('latitude'),
                    issue.get('longitude'),
                    created_at.isoformat() if isinstance(created_at, datetime) else created_at,
                    updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at,
                    closed_at.isoformat() if isinstance(closed_at, datetime) else closed_at,
                    issue.get('reporter_name'),
                    json.dumps(issue.get('images', []), cls=DateTimeEncoder),
                    json.dumps(issue.get('provider_metadata', {}), cls=DateTimeEncoder),
                    as_of.isoformat(),
                    as_of.isoformat(),
                ))
                count += 1

            conn.commit()
            return count

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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
        Retrieve 311 issues with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            provider: Filter by provider ("seeclickfix", "publicstuff", etc.)
            status: Filter by status ("open", "closed", "acknowledged")
            issue_type: Filter by issue type
            limit: Maximum number of issues to return

        Returns:
            List of issue dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM issues
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if provider:
            query += " AND provider = %s"
            params.append(provider)

        if status:
            query += " AND status = %s"
            params.append(status)

        if issue_type:
            query += " AND issue_type = %s"
            params.append(issue_type)

        query += " ORDER BY created_at DESC"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        issues = []
        for row in rows:
            issue = dict(row)
            # Parse JSONB fields
            if 'images' in issue and isinstance(issue['images'], str):
                issue['images'] = json.loads(issue['images'])
            if 'provider_metadata' in issue and isinstance(issue['provider_metadata'], str):
                issue['provider_metadata'] = json.loads(issue['provider_metadata'])
            # Convert datetime objects to ISO strings
            for key in ['created_at', 'updated_at', 'closed_at', 'stored_at', 'valid_from', 'valid_to']:
                if key in issue and issue[key] is not None:
                    if isinstance(issue[key], datetime):
                        issue[key] = issue[key].isoformat()
            issues.append(issue)

        return issues

    def get_issue_count(self, jurisdiction_id: str, provider: Optional[str] = None) -> int:
        """
        Get count of current issues for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction
            provider: Optional filter by provider

        Returns:
            Number of current (non-expired) issues
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        if provider:
            cursor.execute("""
                SELECT COUNT(*) FROM issues
                WHERE jurisdiction_id = %s AND provider = %s AND valid_to IS NULL
            """, (jurisdiction_id, provider))
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM issues
                WHERE jurisdiction_id = %s AND valid_to IS NULL
            """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== ETL Cost Methods (SESSION 397) ==========

    def store_etl_cost(
        self,
        pipeline: str,
        jurisdiction_id: str,
        items_processed: int,
        cost_usd: float,
        duration_seconds: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Store ETL cost record for tracking pipeline expenses.

        Args:
            pipeline: Pipeline name (e.g., "transcribe", "research")
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            items_processed: Number of items processed in this run
            cost_usd: Total cost in USD for this run
            duration_seconds: Optional run duration
            notes: Optional notes about the run

        Returns:
            ID of the inserted cost record
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO etl_costs (
                    pipeline, jurisdiction_id, items_processed,
                    cost_usd, duration_seconds, notes
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                pipeline,
                jurisdiction_id,
                items_processed,
                cost_usd,
                duration_seconds,
                notes,
            ))

            cost_id = cursor.fetchone()[0]
            conn.commit()
            return cost_id

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_etl_costs(
        self,
        jurisdiction_id: Optional[str] = None,
        pipeline: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve ETL cost records with optional filtering.

        Args:
            jurisdiction_id: Filter by jurisdiction (optional)
            pipeline: Filter by pipeline name (optional)
            limit: Maximum records to return (default 100)

        Returns:
            List of cost record dictionaries
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            query = "SELECT * FROM etl_costs WHERE 1=1"
            params: List[Any] = []

            if jurisdiction_id:
                query += " AND jurisdiction_id = %s"
                params.append(jurisdiction_id)

            if pipeline:
                query += " AND pipeline = %s"
                params.append(pipeline)

            query += " ORDER BY run_date DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            costs = []
            for row in rows:
                cost = dict(row)
                # Convert datetime to ISO string
                if 'run_date' in cost and cost['run_date'] is not None:
                    if isinstance(cost['run_date'], datetime):
                        cost['run_date'] = cost['run_date'].isoformat()
                # Convert Decimal to float for JSON serialization
                if 'cost_usd' in cost and cost['cost_usd'] is not None:
                    cost['cost_usd'] = float(cost['cost_usd'])
                costs.append(cost)

            return costs

        finally:
            conn.close()

    def get_etl_cost_summary(
        self,
        jurisdiction_id: Optional[str] = None,
        pipeline: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated ETL cost summary.

        Args:
            jurisdiction_id: Filter by jurisdiction (optional)
            pipeline: Filter by pipeline name (optional)

        Returns:
            Dictionary with total_cost_usd, total_items, run_count
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            query = """
                SELECT
                    COALESCE(SUM(cost_usd), 0) as total_cost_usd,
                    COALESCE(SUM(items_processed), 0) as total_items,
                    COUNT(*) as run_count
                FROM etl_costs WHERE 1=1
            """
            params: List[Any] = []

            if jurisdiction_id:
                query += " AND jurisdiction_id = %s"
                params.append(jurisdiction_id)

            if pipeline:
                query += " AND pipeline = %s"
                params.append(pipeline)

            cursor.execute(query, params)
            row = cursor.fetchone()

            return {
                "total_cost_usd": float(row[0]) if row[0] else 0.0,
                "total_items": int(row[1]) if row[1] else 0,
                "run_count": int(row[2]) if row[2] else 0,
            }

        finally:
            conn.close()

    # ========== Refresh Metadata Methods (SESSION 423) ==========

    def get_refresh_metadata(
        self,
        jurisdiction_id: str,
        corpus_type: str,
        source_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get refresh metadata for a corpus.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            corpus_type: Corpus type (e.g., "meetings", "issues", "municipal_code")
            source_name: Optional source name (e.g., "proudcity", "seeclickfix")

        Returns:
            Dictionary with last_fetch_at, items_fetched, etc. or None if not found
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            query = """
                SELECT * FROM refresh_metadata
                WHERE jurisdiction_id = %s AND corpus_type = %s
            """
            params: List[Any] = [jurisdiction_id, corpus_type]

            if source_name:
                query += " AND source_name = %s"
                params.append(source_name)
            else:
                query += " AND source_name IS NULL"

            cursor.execute(query, params)
            row = cursor.fetchone()

            if not row:
                return None

            result = dict(row)
            # Convert datetime fields to ISO strings
            for field in ['last_fetch_at', 'next_scheduled_at', 'created_at', 'updated_at']:
                if field in result and result[field] is not None:
                    if isinstance(result[field], datetime):
                        result[field] = result[field].isoformat()
            return result

        finally:
            conn.close()

    def update_refresh_metadata(
        self,
        jurisdiction_id: str,
        corpus_type: str,
        source_name: Optional[str] = None,
        items_fetched: Optional[int] = None,
        items_stored: Optional[int] = None,
        status: str = "completed",
        error_message: Optional[str] = None,
        fetch_window_days: Optional[int] = None,
        next_scheduled_at: Optional[datetime] = None,
    ) -> int:
        """
        Update or insert refresh metadata after a fetch operation.

        Uses upsert semantics - inserts if not exists, updates if exists.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            corpus_type: Corpus type (e.g., "meetings", "issues", "municipal_code")
            source_name: Optional source name (e.g., "proudcity", "seeclickfix")
            items_fetched: Number of items fetched in this run
            items_stored: Number of items actually stored (after dedup)
            status: Status of the fetch ("pending", "fetching", "completed", "failed")
            error_message: Error message if status is "failed"
            fetch_window_days: Days to look back for incremental fetch
            next_scheduled_at: When the next scheduled fetch should run

        Returns:
            ID of the upserted record
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO refresh_metadata (
                    jurisdiction_id, corpus_type, source_name,
                    last_fetch_at, items_fetched, items_stored,
                    status, error_message, fetch_window_days,
                    next_scheduled_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (jurisdiction_id, corpus_type, source_name)
                DO UPDATE SET
                    last_fetch_at = EXCLUDED.last_fetch_at,
                    items_fetched = COALESCE(EXCLUDED.items_fetched, refresh_metadata.items_fetched),
                    items_stored = COALESCE(EXCLUDED.items_stored, refresh_metadata.items_stored),
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    fetch_window_days = COALESCE(EXCLUDED.fetch_window_days, refresh_metadata.fetch_window_days),
                    next_scheduled_at = COALESCE(EXCLUDED.next_scheduled_at, refresh_metadata.next_scheduled_at),
                    updated_at = EXCLUDED.updated_at
                RETURNING id
            """, (
                jurisdiction_id,
                corpus_type,
                source_name,
                datetime.now(),
                items_fetched,
                items_stored,
                status,
                error_message,
                fetch_window_days,
                next_scheduled_at,
                datetime.now(),
            ))

            record_id = cursor.fetchone()[0]
            conn.commit()
            return record_id

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_refresh_metadata(
        self,
        jurisdiction_id: Optional[str] = None,
        corpus_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List refresh metadata with optional filtering.

        Args:
            jurisdiction_id: Filter by jurisdiction (optional)
            corpus_type: Filter by corpus type (optional)
            status: Filter by status (optional)

        Returns:
            List of refresh metadata dictionaries
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            query = "SELECT * FROM refresh_metadata WHERE 1=1"
            params: List[Any] = []

            if jurisdiction_id:
                query += " AND jurisdiction_id = %s"
                params.append(jurisdiction_id)

            if corpus_type:
                query += " AND corpus_type = %s"
                params.append(corpus_type)

            if status:
                query += " AND status = %s"
                params.append(status)

            query += " ORDER BY updated_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                result = dict(row)
                # Convert datetime fields to ISO strings
                for field in ['last_fetch_at', 'next_scheduled_at', 'created_at', 'updated_at']:
                    if field in result and result[field] is not None:
                        if isinstance(result[field], datetime):
                            result[field] = result[field].isoformat()
                results.append(result)

            return results

        finally:
            conn.close()

    # ========== Legislation Methods (SESSION 402) ==========

    def store_legislation(
        self,
        state: str,
        bills: List[Dict[str, Any]],
        topic: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store state/federal legislation with temporal versioning.

        Atomic operation: either all bills are stored or none.
        Uses upsert semantics based on (bill_id, state).

        Args:
            state: State code (e.g., "CA", "US" for federal)
            bills: List of bill dictionaries with bill_id, bill_name, etc.
            topic: Optional topic to tag all bills with (e.g., "housing")
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of bills successfully stored

        Raises:
            psycopg2.Error: If atomic store operation fails
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Close previous versions for bills being updated
            for bill in bills:
                bill_id = bill.get('bill_id') or bill.get('id')
                if bill_id:
                    cursor.execute("""
                        UPDATE legislation
                        SET valid_to = %s
                        WHERE state = %s
                          AND bill_id = %s
                          AND valid_to IS NULL
                    """, (as_of.isoformat(), state, bill_id))

            # Insert new versions
            count = 0
            for bill in bills:
                bill_id = bill.get('bill_id') or bill.get('id')
                if not bill_id:
                    continue  # Skip bills without ID

                # Parse enacted_date if string
                enacted_date = bill.get('enacted_date') or bill.get('enacted')
                if isinstance(enacted_date, str):
                    try:
                        enacted_date = datetime.strptime(enacted_date, "%Y-%m-%d").date()
                    except ValueError:
                        enacted_date = None

                # Parse local_deadline if string
                local_deadline = bill.get('local_deadline')
                if isinstance(local_deadline, str):
                    try:
                        local_deadline = datetime.strptime(local_deadline, "%Y-%m-%d").date()
                    except ValueError:
                        local_deadline = None

                # Determine topic from argument or bill data
                bill_topic = topic or bill.get('topic')

                # Extract keywords - handle both list and JSON string
                keywords = bill.get('keywords', [])
                if isinstance(keywords, str):
                    try:
                        keywords = json.loads(keywords)
                    except json.JSONDecodeError:
                        keywords = []

                # Build metadata from extra fields
                metadata = {
                    k: v for k, v in bill.items()
                    if k not in [
                        'bill_id', 'id', 'bill', 'bill_name', 'bill_number',
                        'status', 'enacted', 'enacted_date', 'summary',
                        'leverage_point', 'full_text', 'official_url', 'keywords', 'topic',
                        'local_implementation_required', 'local_deadline',
                        'legiscan_id', '_legiscan_id'
                    ]
                }

                cursor.execute("""
                    INSERT INTO legislation (
                        bill_id, state, jurisdiction_id, bill_number,
                        bill_name, status, enacted_date, summary,
                        leverage_point, full_text, official_url, keywords, topic,
                        local_implementation_required, local_deadline,
                        legiscan_id, metadata, created_at, valid_from, valid_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """, (
                    bill_id,
                    state,
                    bill.get('jurisdiction_id'),
                    bill.get('bill_number') or bill_id.upper().replace('-', ' '),
                    bill.get('bill_name') or bill.get('bill'),
                    bill.get('status'),
                    enacted_date,
                    bill.get('summary'),
                    bill.get('leverage_point'),
                    bill.get('full_text'),
                    bill.get('official_url'),
                    json.dumps(keywords) if keywords else None,
                    bill_topic,
                    bill.get('local_implementation_required'),
                    local_deadline,
                    bill.get('legiscan_id') or bill.get('_legiscan_id'),
                    json.dumps(metadata, cls=DateTimeEncoder) if metadata else None,
                    as_of.isoformat(),
                    as_of.isoformat(),
                ))
                count += 1

            conn.commit()
            return count

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_legislation(
        self,
        state: str,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve legislation with optional filtering.

        Args:
            state: State code (e.g., "CA", "US")
            topic: Filter by topic (e.g., "housing")
            status: Filter by status (e.g., "Active", "Enacted")
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of bills to return

        Returns:
            List of bill dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM legislation
            WHERE state = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [state, as_of.isoformat(), as_of.isoformat()]

        if topic:
            query += " AND topic = %s"
            params.append(topic)

        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY enacted_date DESC NULLS LAST, bill_id"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        bills = []
        for row in rows:
            bill = dict(row)
            # Parse JSONB fields
            if 'keywords' in bill and isinstance(bill['keywords'], str):
                try:
                    bill['keywords'] = json.loads(bill['keywords'])
                except json.JSONDecodeError:
                    bill['keywords'] = []
            if 'metadata' in bill and isinstance(bill['metadata'], str):
                try:
                    bill['metadata'] = json.loads(bill['metadata'])
                except json.JSONDecodeError:
                    bill['metadata'] = {}
            # Convert datetime/date objects to ISO strings
            for key in ['enacted_date', 'local_deadline', 'created_at', 'valid_from', 'valid_to']:
                if key in bill and bill[key] is not None:
                    if isinstance(bill[key], (datetime, date)):
                        bill[key] = bill[key].isoformat()
            bills.append(bill)

        return bills

    def get_legislation_by_bill_id(
        self,
        state: str,
        bill_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific legislation by bill_id.

        Args:
            state: State code (e.g., "CA")
            bill_id: Bill identifier (e.g., "ca-sb9")
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            Bill dictionary or None if not found
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM legislation
            WHERE state = %s
              AND bill_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
            ORDER BY created_at DESC
            LIMIT 1
        """, (state, bill_id, as_of.isoformat(), as_of.isoformat()))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        bill = dict(row)
        # Parse JSONB fields
        if 'keywords' in bill and isinstance(bill['keywords'], str):
            try:
                bill['keywords'] = json.loads(bill['keywords'])
            except json.JSONDecodeError:
                bill['keywords'] = []
        if 'metadata' in bill and isinstance(bill['metadata'], str):
            try:
                bill['metadata'] = json.loads(bill['metadata'])
            except json.JSONDecodeError:
                bill['metadata'] = {}
        # Convert datetime/date objects to ISO strings
        for key in ['enacted_date', 'local_deadline', 'created_at', 'valid_from', 'valid_to']:
            if key in bill and bill[key] is not None:
                if isinstance(bill[key], (datetime, date)):
                    bill[key] = bill[key].isoformat()

        return bill

    def get_legislation_count(self, state: str, topic: Optional[str] = None) -> int:
        """
        Get count of current legislation for a state.

        Args:
            state: State code (e.g., "CA")
            topic: Optional filter by topic

        Returns:
            Number of current (non-expired) bills
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        if topic:
            cursor.execute("""
                SELECT COUNT(*) FROM legislation
                WHERE state = %s AND topic = %s AND valid_to IS NULL
            """, (state, topic))
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM legislation
                WHERE state = %s AND valid_to IS NULL
            """, (state,))

        count = cursor.fetchone()[0]
        conn.close()

        return count

    def update_legislation_text(
        self,
        state: str,
        updates: List[Dict[str, Any]],
    ) -> int:
        """
        Update full_text for legislation bills.

        Args:
            state: State code (e.g., "CA")
            updates: List of dicts with 'bill_id' and 'full_text'

        Returns:
            Number of bills updated
        """
        if not updates:
            return 0

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        updated_count = 0
        for update in updates:
            bill_id = update.get("bill_id")
            full_text = update.get("full_text")

            if not bill_id or not full_text:
                continue

            cursor.execute("""
                UPDATE legislation
                SET full_text = %s
                WHERE bill_id = %s AND state = %s AND valid_to IS NULL
            """, (full_text, bill_id, state))

            if cursor.rowcount > 0:
                updated_count += 1

        conn.commit()
        conn.close()

        return updated_count

    # ========== Codified Law Methods (SESSION 428) ==========

    def store_codified_law(
        self,
        jurisdiction_id: str,
        sections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        use_copy: bool = True,
    ) -> int:
        """
        Store codified law sections (U.S. Code, CA Codes) with temporal versioning.

        Uses PostgreSQL COPY for 10x faster bulk inserts.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "federal-US", "state-CA")
            sections: List of section dictionaries from USCodeParser.to_dict()
            as_of: Timestamp for temporal versioning (default: now)
            use_copy: If True (default), use COPY for bulk inserts. Set False for upsert.

        Returns:
            Number of sections successfully stored

        Raises:
            psycopg2.Error: If store operation fails
        """
        as_of = as_of or datetime.now()
        as_of_str = as_of.isoformat()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Filter to sections with identifiers
            valid_sections = [s for s in sections if s.get("identifier")]

            if use_copy:
                # COPY is 10x faster - use for bulk fresh inserts
                # Batch in chunks of 500 to avoid Supabase statement timeout
                batch_size = 500
                for batch_start in range(0, len(valid_sections), batch_size):
                    batch = valid_sections[batch_start:batch_start + batch_size]
                    buffer = StringIO()

                    for section in batch:
                        # Build metadata from extra fields
                        metadata = {
                            k: v for k, v in section.items()
                            if k not in [
                                "citation", "title_number", "title_name", "section_number",
                                "heading", "text", "status", "chapter", "subchapter", "identifier"
                            ]
                        }
                        metadata_json = json.dumps(metadata, cls=DateTimeEncoder) if metadata else None

                        # Build row values
                        row_values = [
                            section.get("citation"),
                            section.get("title_number"),
                            section.get("title_name"),
                            section.get("section_number"),
                            section.get("heading"),
                            section.get("text"),
                            jurisdiction_id,
                            section.get("status"),
                            section.get("chapter"),
                            section.get("subchapter"),
                            section.get("identifier"),
                            metadata_json,
                            as_of_str,  # created_at
                            as_of_str,  # valid_from
                            None,       # valid_to
                        ]

                        # Format for COPY: tab-separated, escape special chars
                        line_parts = []
                        for val in row_values:
                            if val is None:
                                line_parts.append("\\N")
                            else:
                                s = str(val)
                                s = s.replace("\\", "\\\\")
                                s = s.replace("\t", "\\t")
                                s = s.replace("\n", "\\n")
                                s = s.replace("\r", "\\r")
                                line_parts.append(s)
                        buffer.write("\t".join(line_parts) + "\n")

                    buffer.seek(0)
                    cursor.copy_from(
                        buffer,
                        "codified_law",
                        columns=(
                            "citation", "title_number", "title_name", "section_number",
                            "heading", "text", "jurisdiction_id", "status",
                            "chapter", "subchapter", "identifier", "metadata",
                            "created_at", "valid_from", "valid_to"
                        ),
                    )
                    # Commit each batch to avoid timeout
                    conn.commit()
            else:
                # execute_values with temporal versioning for incremental updates
                # First close previous versions
                identifiers = [s.get("identifier") for s in valid_sections]
                if identifiers:
                    for i in range(0, len(identifiers), 1000):
                        chunk = identifiers[i:i + 1000]
                        placeholders = ",".join(["%s"] * len(chunk))
                        cursor.execute(f"""
                            UPDATE codified_law
                            SET valid_to = %s
                            WHERE jurisdiction_id = %s
                              AND identifier IN ({placeholders})
                              AND valid_to IS NULL
                        """, [as_of_str, jurisdiction_id] + chunk)

                # Then insert new versions
                values = []
                for section in valid_sections:
                    metadata = {
                        k: v for k, v in section.items()
                        if k not in [
                            "citation", "title_number", "title_name", "section_number",
                            "heading", "text", "status", "chapter", "subchapter", "identifier"
                        ]
                    }
                    values.append((
                        section.get("citation"),
                        section.get("title_number"),
                        section.get("title_name"),
                        section.get("section_number"),
                        section.get("heading"),
                        section.get("text"),
                        jurisdiction_id,
                        section.get("status"),
                        section.get("chapter"),
                        section.get("subchapter"),
                        section.get("identifier"),
                        json.dumps(metadata, cls=DateTimeEncoder) if metadata else None,
                        as_of_str,
                        as_of_str,
                    ))

                if values:
                    psycopg2.extras.execute_values(
                        cursor,
                        """
                        INSERT INTO codified_law (
                            citation, title_number, title_name, section_number,
                            heading, text, jurisdiction_id, status,
                            chapter, subchapter, identifier, metadata,
                            created_at, valid_from, valid_to
                        ) VALUES %s
                        """,
                        values,
                        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
                        page_size=500,
                    )

            conn.commit()
            return len(valid_sections)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_codified_law(
        self,
        jurisdiction_id: str,
        title_number: Optional[int] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve codified law sections with optional filtering.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "federal-US", "state-CA")
            title_number: Filter by title number (e.g., 42 for Title 42)
            status: Filter by status (None for active, "repealed" for repealed)
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of sections to return

        Returns:
            List of section dictionaries
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM codified_law
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if title_number is not None:
            query += " AND title_number = %s"
            params.append(title_number)

        if status is not None:
            query += " AND status = %s"
            params.append(status)
        else:
            # Default to active sections only (status IS NULL)
            query += " AND status IS NULL"

        query += " ORDER BY title_number, section_number"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        sections = []
        for row in rows:
            section = dict(row)
            # Parse JSONB fields
            if "metadata" in section and isinstance(section["metadata"], str):
                try:
                    section["metadata"] = json.loads(section["metadata"])
                except json.JSONDecodeError:
                    section["metadata"] = {}
            # Convert datetime/date objects to ISO strings
            for key in ["created_at", "valid_from", "valid_to"]:
                if key in section and section[key] is not None:
                    if isinstance(section[key], (datetime, date)):
                        section[key] = section[key].isoformat()
            sections.append(section)

        return sections

    def search_codified_law(
        self,
        jurisdiction_id: str,
        query: str,
        title_number: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search codified law sections by topic/keyword.

        Uses PostgreSQL full-text search for relevance ranking.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "federal-US")
            query: Search query (topic keywords)
            title_number: Optional filter by title number
            limit: Maximum results to return

        Returns:
            List of matching sections with relevance scores
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Use full-text search with ranking
        # plainto_tsquery handles natural language queries
        sql = """
            SELECT
                citation, title_number, title_name, section_number,
                heading, chapter, subchapter, identifier,
                LEFT(text, 500) as text_preview,
                ts_rank(
                    to_tsvector('english', COALESCE(heading, '') || ' ' || COALESCE(text, '')),
                    plainto_tsquery('english', %s)
                ) as relevance
            FROM codified_law
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
              AND status IS NULL
              AND to_tsvector('english', COALESCE(heading, '') || ' ' || COALESCE(text, ''))
                  @@ plainto_tsquery('english', %s)
        """
        params: List[Any] = [query, jurisdiction_id, query]

        if title_number is not None:
            sql += " AND title_number = %s"
            params.append(title_number)

        sql += " ORDER BY relevance DESC LIMIT %s"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_codified_law_count(
        self,
        jurisdiction_id: str,
        title_number: Optional[int] = None,
        include_inactive: bool = False,
    ) -> int:
        """
        Get count of current codified law sections for a jurisdiction.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "federal-US")
            title_number: Optional filter by title number
            include_inactive: Whether to include repealed/omitted sections

        Returns:
            Number of current (non-expired) sections
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*) FROM codified_law
            WHERE jurisdiction_id = %s AND valid_to IS NULL
        """
        params: List[Any] = [jurisdiction_id]

        if title_number is not None:
            query += " AND title_number = %s"
            params.append(title_number)

        if not include_inactive:
            query += " AND status IS NULL"

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Executive Orders Methods (SESSION 432) ==========

    def store_executive_orders(
        self,
        orders: List[Dict[str, Any]],
        use_copy: bool = True,
    ) -> int:
        """
        Store Executive Orders from Federal Register API.

        Uses PostgreSQL COPY for fast bulk inserts with ON CONFLICT handling.

        Args:
            orders: List of order dictionaries with fields:
                - eo_number: Executive Order number (may be None)
                - document_number: FR document number (unique key)
                - title: Order title
                - abstract: Short description
                - full_text: Full text content
                - president: President name
                - president_id: President identifier
                - signing_date: Date signed
                - publication_date: Date published in FR
                - html_url, pdf_url, raw_text_url: Links
            use_copy: If True (default), use COPY for bulk inserts

        Returns:
            Number of orders successfully stored
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Filter to orders with document_number (unique key)
            valid_orders = [o for o in orders if o.get("document_number")]

            if use_copy:
                # COPY for bulk inserts - need to handle duplicates
                # First, get existing document numbers to skip
                doc_numbers = [o.get("document_number") for o in valid_orders]
                placeholders = ",".join(["%s"] * len(doc_numbers))
                cursor.execute(f"""
                    SELECT document_number FROM executive_orders
                    WHERE document_number IN ({placeholders})
                """, doc_numbers)
                existing = {row[0] for row in cursor.fetchall()}

                # Filter out existing orders
                new_orders = [o for o in valid_orders if o.get("document_number") not in existing]

                if not new_orders:
                    conn.close()
                    return 0

                # Batch in chunks of 500
                batch_size = 500
                for batch_start in range(0, len(new_orders), batch_size):
                    batch = new_orders[batch_start:batch_start + batch_size]
                    buffer = StringIO()

                    for order in batch:
                        # Build metadata from extra fields
                        metadata = {
                            k: v for k, v in order.items()
                            if k not in [
                                "eo_number", "document_number", "title", "abstract",
                                "full_text", "president", "president_id", "signing_date",
                                "publication_date", "html_url", "pdf_url", "raw_text_url",
                                "status", "revoked_by_eo"
                            ]
                        }
                        metadata_json = json.dumps(metadata, cls=DateTimeEncoder) if metadata else None

                        # Build row values
                        row_values = [
                            order.get("eo_number"),
                            order.get("document_number"),
                            order.get("title"),
                            order.get("abstract"),
                            order.get("full_text"),
                            order.get("president"),
                            order.get("president_id"),
                            order.get("signing_date"),
                            order.get("publication_date"),
                            order.get("html_url"),
                            order.get("pdf_url"),
                            order.get("raw_text_url"),
                            order.get("status", "active"),
                            order.get("revoked_by_eo"),
                            metadata_json,
                        ]

                        # Format for COPY: tab-separated, escape special chars
                        line_parts = []
                        for val in row_values:
                            if val is None:
                                line_parts.append("\\N")
                            else:
                                s = str(val)
                                s = s.replace("\\", "\\\\")
                                s = s.replace("\t", "\\t")
                                s = s.replace("\n", "\\n")
                                s = s.replace("\r", "\\r")
                                line_parts.append(s)
                        buffer.write("\t".join(line_parts) + "\n")

                    buffer.seek(0)
                    cursor.copy_from(
                        buffer,
                        "executive_orders",
                        columns=(
                            "eo_number", "document_number", "title", "abstract",
                            "full_text", "president", "president_id", "signing_date",
                            "publication_date", "html_url", "pdf_url", "raw_text_url",
                            "status", "revoked_by_eo", "metadata"
                        ),
                    )
                    conn.commit()

                return len(new_orders)
            else:
                # execute_values with ON CONFLICT for upsert
                values = []
                for order in valid_orders:
                    metadata = {
                        k: v for k, v in order.items()
                        if k not in [
                            "eo_number", "document_number", "title", "abstract",
                            "full_text", "president", "president_id", "signing_date",
                            "publication_date", "html_url", "pdf_url", "raw_text_url",
                            "status", "revoked_by_eo"
                        ]
                    }
                    values.append((
                        order.get("eo_number"),
                        order.get("document_number"),
                        order.get("title"),
                        order.get("abstract"),
                        order.get("full_text"),
                        order.get("president"),
                        order.get("president_id"),
                        order.get("signing_date"),
                        order.get("publication_date"),
                        order.get("html_url"),
                        order.get("pdf_url"),
                        order.get("raw_text_url"),
                        order.get("status", "active"),
                        order.get("revoked_by_eo"),
                        json.dumps(metadata, cls=DateTimeEncoder) if metadata else None,
                    ))

                if values:
                    psycopg2.extras.execute_values(
                        cursor,
                        """
                        INSERT INTO executive_orders (
                            eo_number, document_number, title, abstract,
                            full_text, president, president_id, signing_date,
                            publication_date, html_url, pdf_url, raw_text_url,
                            status, revoked_by_eo, metadata
                        ) VALUES %s
                        ON CONFLICT (document_number) DO UPDATE SET
                            eo_number = EXCLUDED.eo_number,
                            title = EXCLUDED.title,
                            abstract = EXCLUDED.abstract,
                            full_text = EXCLUDED.full_text,
                            status = EXCLUDED.status,
                            revoked_by_eo = EXCLUDED.revoked_by_eo,
                            metadata = EXCLUDED.metadata
                        """,
                        values,
                        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        page_size=500,
                    )

                conn.commit()
                return len(valid_orders)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_executive_orders(
        self,
        president: Optional[str] = None,
        eo_number: Optional[int] = None,
        status: Optional[str] = None,
        signing_date_after: Optional[date] = None,
        signing_date_before: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve Executive Orders with optional filtering.

        Args:
            president: Filter by president name
            eo_number: Filter by specific EO number
            status: Filter by status ("active", "revoked", "superseded")
            signing_date_after: Filter orders signed after this date
            signing_date_before: Filter orders signed before this date
            limit: Maximum number of orders to return

        Returns:
            List of order dictionaries
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = "SELECT * FROM executive_orders WHERE 1=1"
        params: List[Any] = []

        if president is not None:
            query += " AND president ILIKE %s"
            params.append(f"%{president}%")

        if eo_number is not None:
            query += " AND eo_number = %s"
            params.append(eo_number)

        if status is not None:
            query += " AND status = %s"
            params.append(status)
        else:
            # Default to active orders
            query += " AND status = 'active'"

        if signing_date_after is not None:
            query += " AND signing_date >= %s"
            params.append(signing_date_after.isoformat() if hasattr(signing_date_after, 'isoformat') else signing_date_after)

        if signing_date_before is not None:
            query += " AND signing_date <= %s"
            params.append(signing_date_before.isoformat() if hasattr(signing_date_before, 'isoformat') else signing_date_before)

        query += " ORDER BY signing_date DESC, eo_number DESC"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        orders = []
        for row in rows:
            order = dict(row)
            # Parse JSONB fields
            if "metadata" in order and isinstance(order["metadata"], str):
                try:
                    order["metadata"] = json.loads(order["metadata"])
                except json.JSONDecodeError:
                    order["metadata"] = {}
            # Convert date objects to ISO strings
            for key in ["signing_date", "publication_date", "created_at"]:
                if key in order and order[key] is not None:
                    if isinstance(order[key], (datetime, date)):
                        order[key] = order[key].isoformat()
            orders.append(order)

        return orders

    def search_executive_orders(
        self,
        query: str,
        president: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search Executive Orders by topic/keyword.

        Uses PostgreSQL full-text search for relevance ranking.

        Args:
            query: Search query (topic keywords)
            president: Optional filter by president
            limit: Maximum results to return

        Returns:
            List of matching orders with relevance scores
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        sql = """
            SELECT
                eo_number, document_number, title, president,
                signing_date, publication_date, html_url, pdf_url,
                LEFT(COALESCE(abstract, full_text, ''), 500) as text_preview,
                ts_rank(
                    to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(abstract, '') || ' ' || COALESCE(full_text, '')),
                    plainto_tsquery('english', %s)
                ) as relevance
            FROM executive_orders
            WHERE status = 'active'
              AND to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(abstract, '') || ' ' || COALESCE(full_text, ''))
                  @@ plainto_tsquery('english', %s)
        """
        params: List[Any] = [query, query]

        if president is not None:
            sql += " AND president ILIKE %s"
            params.append(f"%{president}%")

        sql += " ORDER BY relevance DESC LIMIT %s"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert dates
        orders = []
        for row in rows:
            order = dict(row)
            for key in ["signing_date", "publication_date"]:
                if key in order and order[key] is not None:
                    if isinstance(order[key], (datetime, date)):
                        order[key] = order[key].isoformat()
            orders.append(order)

        return orders

    def get_executive_orders_count(
        self,
        president: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """
        Get count of Executive Orders.

        Args:
            president: Optional filter by president name
            status: Optional filter by status

        Returns:
            Number of matching orders
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        query = "SELECT COUNT(*) FROM executive_orders WHERE 1=1"
        params: List[Any] = []

        if president is not None:
            query += " AND president ILIKE %s"
            params.append(f"%{president}%")

        if status is not None:
            query += " AND status = %s"
            params.append(status)

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()

        return count


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
        'get_operation', 'get_operations',
        # Decision methods (SESSION 366)
        'store_decisions', 'get_decisions', 'get_decision_count',
        # Chunk methods (SESSION 367)
        'store_chunks', 'get_chunks', 'get_chunk_count',
        # Video methods (SESSION 379)
        'store_videos', 'get_videos', 'get_video_count',
        # Transcript methods (SESSION 381)
        'store_transcripts', 'get_transcripts', 'get_transcript', 'get_transcript_count',
        # Issue methods (SESSION 385)
        'store_issues', 'get_issues', 'get_issue_count',
        # ETL cost methods (SESSION 397)
        'store_etl_cost', 'get_etl_costs', 'get_etl_cost_summary',
        # Legislation methods (SESSION 402)
        'store_legislation', 'get_legislation', 'get_legislation_by_bill_id', 'get_legislation_count',
        # Codified law methods (SESSION 428)
        'store_codified_law', 'get_codified_law', 'get_codified_law_count',
        # Executive orders methods (SESSION 432)
        'store_executive_orders', 'get_executive_orders', 'get_executive_orders_count',
    ]
    for method in required_methods:
        assert hasattr(PostgresBackend, method), (
            f"PostgresBackend must implement {method}"
        )


_verify_protocol_compliance()
