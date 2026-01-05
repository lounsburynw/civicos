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
from civic._internal.jurisdiction import normalize_jurisdiction


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

        # Budget items table (SESSION 434)
        # Stores municipal/county budget line items for financial queries
        # Amounts in cents to avoid floating-point precision issues
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS budget_items (
                id SERIAL PRIMARY KEY,
                item_id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                fiscal_year TEXT NOT NULL,
                fund TEXT,
                department TEXT,
                program TEXT,
                line_item TEXT NOT NULL,
                budgeted_cents BIGINT NOT NULL,
                revised_cents BIGINT,
                actual_cents BIGINT,
                source_url TEXT,
                source_page INTEGER,
                notes TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                UNIQUE (item_id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from),
                CHECK (budgeted_cents >= 0),
                CHECK (revised_cents IS NULL OR revised_cents >= 0),
                CHECK (actual_cents IS NULL OR actual_cents >= 0)
            )
        """)

        # Budget items indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_items_jurisdiction
            ON budget_items(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_items_fiscal_year
            ON budget_items(jurisdiction_id, fiscal_year)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_items_department
            ON budget_items(jurisdiction_id, department)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_items_fund
            ON budget_items(jurisdiction_id, fund)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_items_temporal
            ON budget_items(jurisdiction_id, valid_from, valid_to)
        """)

        # Federal Awards table (SESSION 439)
        # Stores federal grants and awards for intergovernmental funding tracking
        # Data source: USAspending.gov API
        # Amounts in cents to avoid floating-point precision issues
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS federal_awards (
                id SERIAL PRIMARY KEY,
                award_id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                cfda_number TEXT,
                recipient_uei TEXT,
                recipient_name TEXT,
                amount_cents BIGINT NOT NULL,
                period_start DATE,
                period_end DATE,
                program_name TEXT,
                awarding_agency TEXT,
                funding_agency TEXT,
                award_type TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                UNIQUE (award_id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from),
                CHECK (amount_cents >= 0)
            )
        """)

        # Federal awards indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_federal_awards_jurisdiction
            ON federal_awards(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_federal_awards_cfda
            ON federal_awards(jurisdiction_id, cfda_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_federal_awards_recipient
            ON federal_awards(recipient_uei)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_federal_awards_period
            ON federal_awards(jurisdiction_id, period_start, period_end)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_federal_awards_temporal
            ON federal_awards(jurisdiction_id, valid_from, valid_to)
        """)

        # State Passthrough Funding table (SESSION 442)
        # Tracks federal funds that flow through state agencies to local governments
        # Example: HUD → California HCD → San Rafael (CDBG allocation)
        # Links to federal_awards via federal_award_id
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_passthrough_funds (
                id SERIAL PRIMARY KEY,
                passthrough_id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                federal_award_id TEXT,
                federal_cfda_number TEXT,
                federal_program_name TEXT,
                federal_amount_cents BIGINT,
                state_agency TEXT NOT NULL,
                state_program_name TEXT,
                state_grant_id TEXT,
                local_amount_cents BIGINT NOT NULL,
                allocation_percentage DECIMAL(5,2),
                period_start DATE,
                period_end DATE,
                federal_fiscal_year INTEGER,
                state_fiscal_year INTEGER,
                source_url TEXT,
                notes TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                UNIQUE (passthrough_id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from),
                CHECK (local_amount_cents >= 0),
                CHECK (allocation_percentage IS NULL OR (allocation_percentage >= 0 AND allocation_percentage <= 100))
            )
        """)

        # State passthrough indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_state_passthrough_jurisdiction
            ON state_passthrough_funds(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_state_passthrough_state_agency
            ON state_passthrough_funds(jurisdiction_id, state_agency)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_state_passthrough_federal_cfda
            ON state_passthrough_funds(jurisdiction_id, federal_cfda_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_state_passthrough_federal_award
            ON state_passthrough_funds(federal_award_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_state_passthrough_temporal
            ON state_passthrough_funds(jurisdiction_id, valid_from, valid_to)
        """)

        # Budget Funding Source Links table (SESSION 444)
        # Links city budget line items to their federal/state funding sources
        # Enables "trace this dollar to source" queries
        # Supports AI-suggested matches with human confirmation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS budget_funding_source_links (
                id SERIAL PRIMARY KEY,
                link_id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                budget_item_id TEXT NOT NULL,
                federal_award_id TEXT,
                federal_cfda_number TEXT,
                passthrough_id TEXT,
                state_grant_id TEXT,
                match_type TEXT NOT NULL,
                match_confidence DECIMAL(3,2) NOT NULL,
                match_source TEXT,
                match_notes TEXT,
                budget_cents BIGINT,
                federal_cents BIGINT,
                local_cents BIGINT,
                reconciliation_status TEXT,
                variance_cents BIGINT,
                variance_percentage DECIMAL(5,2),
                confirmed_by TEXT,
                confirmed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                UNIQUE (link_id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from),
                CHECK (match_confidence >= 0 AND match_confidence <= 1)
            )
        """)

        # Budget funding source links indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_funding_links_jurisdiction
            ON budget_funding_source_links(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_funding_links_budget_item
            ON budget_funding_source_links(budget_item_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_funding_links_federal_cfda
            ON budget_funding_source_links(federal_cfda_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_funding_links_passthrough
            ON budget_funding_source_links(passthrough_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_funding_links_match_type
            ON budget_funding_source_links(match_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_funding_links_confidence
            ON budget_funding_source_links(match_confidence DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_budget_funding_links_temporal
            ON budget_funding_source_links(jurisdiction_id, valid_from, valid_to)
        """)

        # Federal Audit Expenditures table (SESSION 449)
        # Stores Schedule of Expenditures of Federal Awards (SEFA) data from
        # Single Audits filed with the Federal Audit Clearinghouse (FAC).
        # This is audited expenditure data - the authoritative source for
        # "how much did the city actually spend from federal grant X?"
        # Unlike federal_awards (which stores award amounts), this stores
        # actual expenditures reported in annual audits.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS federal_audit_expenditures (
                id SERIAL PRIMARY KEY,
                report_id TEXT NOT NULL,
                award_reference TEXT,
                jurisdiction_id TEXT NOT NULL,
                cfda_number TEXT NOT NULL,
                auditee_uei TEXT,
                auditee_ein TEXT,
                audit_year INTEGER NOT NULL,
                fy_start_date DATE,
                fy_end_date DATE,
                amount_expended_cents BIGINT NOT NULL,
                federal_program_total_cents BIGINT,
                cluster_total_cents BIGINT,
                federal_program_name TEXT,
                cluster_name TEXT,
                is_major BOOLEAN DEFAULT FALSE,
                is_passthrough BOOLEAN DEFAULT FALSE,
                federal_agency_prefix TEXT,
                source_url TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                UNIQUE (report_id, award_reference, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from),
                CHECK (amount_expended_cents >= 0)
            )
        """)

        # Federal audit expenditures indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_expenditures_jurisdiction
            ON federal_audit_expenditures(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_expenditures_cfda
            ON federal_audit_expenditures(jurisdiction_id, cfda_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_expenditures_year
            ON federal_audit_expenditures(jurisdiction_id, audit_year DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_expenditures_report
            ON federal_audit_expenditures(report_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_expenditures_temporal
            ON federal_audit_expenditures(jurisdiction_id, valid_from, valid_to)
        """)

        # Elections table (SESSION 460)
        # Stores elections, contests, and ballot measures for whats_next()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS elections (
                id TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                name TEXT NOT NULL,
                election_date TEXT NOT NULL,
                election_type TEXT NOT NULL,
                source TEXT NOT NULL,
                source_url TEXT,
                raw_data JSONB,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_elections_jurisdiction
            ON elections(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_elections_date
            ON elections(election_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_elections_type
            ON elections(election_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_elections_temporal
            ON elections(jurisdiction_id, valid_from, valid_to)
        """)

        # Election deadlines table (SESSION 460)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS election_deadlines (
                id TEXT NOT NULL,
                election_id TEXT NOT NULL,
                deadline_type TEXT NOT NULL,
                deadline_date TEXT NOT NULL,
                description TEXT,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, election_id, valid_from),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_election_deadlines_election
            ON election_deadlines(election_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_election_deadlines_date
            ON election_deadlines(deadline_date)
        """)

        # Election contests table (SESSION 460)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS election_contests (
                id TEXT NOT NULL,
                election_id TEXT NOT NULL,
                title TEXT NOT NULL,
                contest_type TEXT NOT NULL,
                district_name TEXT,
                raw_data JSONB,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, election_id, valid_from),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_election_contests_election
            ON election_contests(election_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_election_contests_type
            ON election_contests(contest_type)
        """)

        # Elected officials table (SESSION 460)
        # Links elections to decisions via voting records
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS elected_officials (
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                seat TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                term_start TEXT NOT NULL,
                term_end TEXT,
                name_variations JSONB,
                candidate_id TEXT,
                valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                PRIMARY KEY (id, jurisdiction_id, valid_from),
                FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
                CHECK (valid_to IS NULL OR valid_to > valid_from)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_officials_jurisdiction
            ON elected_officials(jurisdiction_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_officials_current
            ON elected_officials(term_end) WHERE term_end IS NULL
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_officials_temporal
            ON elected_officials(jurisdiction_id, valid_from, valid_to)
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
        Store meetings with temporal versioning (upsert pattern).

        Uses upsert semantics: for each meeting in the input list:
        - If meeting.id exists and data unchanged: update last_verified timestamp
        - If meeting.id exists and data changed: close old version, insert new
        - If meeting.id is new: insert as new record
        - If meeting lacks id: skip (not counted in return value)

        Meetings NOT in the input list are preserved (not closed).

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            meetings: List of meeting objects or dictionaries with 'id' field
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of meetings successfully stored or updated (excludes skipped)

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

            # Use upsert pattern: only close/update meetings that changed
            # This preserves historical meetings not in the current scrape window
            stored_count = 0
            for meeting in meetings:
                # Handle both dict and object access
                if hasattr(meeting, "__dict__"):
                    meeting_dict = meeting.__dict__
                elif hasattr(meeting, "to_dict"):
                    meeting_dict = meeting.to_dict()
                else:
                    meeting_dict = meeting

                meeting_id = meeting_dict.get('id')
                if not meeting_id:
                    continue  # Skip meetings without ID

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

                # Check if meeting exists (current version)
                cursor.execute("""
                    SELECT title, meeting_datetime, agenda_url, minutes_url,
                           status, location, virtual_url, video_url
                    FROM meetings
                    WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL
                """, (meeting_id, jurisdiction_id))
                existing = cursor.fetchone()

                if existing:
                    # Compare key fields to detect changes
                    (ex_title, ex_dt, ex_agenda, ex_minutes,
                     ex_status, ex_location, ex_virtual, ex_video) = existing

                    # Normalize datetime for comparison
                    ex_dt_str = ex_dt.isoformat() if isinstance(ex_dt, datetime) else str(ex_dt) if ex_dt else None

                    has_changes = (
                        meeting_dict.get('title') != ex_title or
                        meeting_dt != ex_dt_str or
                        meeting_dict.get('agenda_url') != ex_agenda or
                        meeting_dict.get('minutes_url') != ex_minutes or
                        meeting_dict.get('status') != ex_status or
                        meeting_dict.get('location') != ex_location or
                        meeting_dict.get('virtual_url') != ex_virtual or
                        meeting_dict.get('video_url') != ex_video
                    )

                    if not has_changes:
                        # Update last_verified timestamp only
                        cursor.execute("""
                            UPDATE meetings
                            SET last_verified = %s
                            WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL
                        """, (as_of.isoformat(), meeting_id, jurisdiction_id))
                        stored_count += 1
                        continue

                    # Close the old version (data changed)
                    cursor.execute("""
                        UPDATE meetings
                        SET valid_to = %s
                        WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL
                    """, (as_of.isoformat(), meeting_id, jurisdiction_id))

                # Insert new version (either new meeting or updated version)
                cursor.execute("""
                    INSERT INTO meetings (
                        id, jurisdiction_id, title, meeting_datetime,
                        meeting_type, status, location, virtual_url,
                        agenda_url, minutes_url, video_url, comment_deadline,
                        source_platform, source_url, last_verified,
                        data_quality_score, valid_from, valid_to, full_data
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
                """, (
                    meeting_id,
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
                stored_count += 1

            # Update city_state timestamp
            cursor.execute("""
                UPDATE city_states
                SET as_of = %s, updated_at = %s
                WHERE jurisdiction_id = %s
            """, (as_of.isoformat(), datetime.now().isoformat(), jurisdiction_id))

            conn.commit()
            return stored_count

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
                        extraction_method, financial_impact_cents,
                        extracted_at, valid_from, valid_to, content_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
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
                    decision.get('financial_impact_cents'),
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

    # ========== Budget Items Methods (Municipal/County Budget Line Items) ==========

    def store_budget_items(
        self,
        jurisdiction_id: str,
        items: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        use_copy: bool = True,
    ) -> int:
        """
        Store budget line items with temporal versioning.

        Uses PostgreSQL COPY for 10x faster bulk inserts.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            items: List of budget item dictionaries
            as_of: Timestamp for temporal versioning (default: now)
            use_copy: If True (default), use COPY for bulk inserts. Set False for upsert.

        Returns:
            Number of items successfully stored

        Raises:
            psycopg2.Error: If store operation fails
        """
        # Normalize jurisdiction to canonical form (e.g., "san-rafael" -> "city-san-rafael")
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        as_of_str = as_of.isoformat()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Filter to items with identifiers and positive budgets
            valid_items = [
                item for item in items
                if item.get("id") and item.get("budgeted_cents", 0) >= 0
            ]

            if use_copy:
                # COPY is 10x faster - use for bulk fresh inserts
                batch_size = 500
                for batch_start in range(0, len(valid_items), batch_size):
                    batch = valid_items[batch_start:batch_start + batch_size]
                    buffer = StringIO()

                    for item in batch:
                        # Build metadata from extra fields
                        metadata = {
                            k: v for k, v in item.items()
                            if k not in [
                                "id", "fiscal_year", "fund", "department",
                                "program", "line_item", "budgeted_cents",
                                "revised_cents", "actual_cents", "source_url",
                                "source_page", "notes"
                            ]
                        }
                        metadata_json = json.dumps(metadata, cls=DateTimeEncoder) if metadata else None

                        # Build row values
                        row_values = [
                            item.get("id"),
                            jurisdiction_id,
                            item.get("fiscal_year"),
                            item.get("fund"),
                            item.get("department"),
                            item.get("program"),
                            item.get("line_item"),
                            item.get("budgeted_cents"),
                            item.get("revised_cents"),
                            item.get("actual_cents"),
                            item.get("source_url"),
                            item.get("source_page"),
                            item.get("notes"),
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
                        "budget_items",
                        columns=(
                            "item_id", "jurisdiction_id", "fiscal_year", "fund",
                            "department", "program", "line_item", "budgeted_cents",
                            "revised_cents", "actual_cents", "source_url",
                            "source_page", "notes", "metadata",
                            "created_at", "valid_from", "valid_to"
                        ),
                    )
                    # Commit each batch to avoid timeout
                    conn.commit()
            else:
                # execute_values with temporal versioning for incremental updates
                # First close previous versions
                item_ids = [item.get("id") for item in valid_items if item.get("id")]
                if item_ids:
                    for i in range(0, len(item_ids), 1000):
                        chunk = item_ids[i:i + 1000]
                        placeholders = ",".join(["%s"] * len(chunk))
                        cursor.execute(f"""
                            UPDATE budget_items
                            SET valid_to = %s
                            WHERE jurisdiction_id = %s
                              AND item_id IN ({placeholders})
                              AND valid_to IS NULL
                        """, [as_of_str, jurisdiction_id] + chunk)

                # Then insert new versions
                values = []
                for item in valid_items:
                    metadata = {
                        k: v for k, v in item.items()
                        if k not in [
                            "id", "fiscal_year", "fund", "department",
                            "program", "line_item", "budgeted_cents",
                            "revised_cents", "actual_cents", "source_url",
                            "source_page", "notes"
                        ]
                    }
                    values.append((
                        item.get("id"),
                        jurisdiction_id,
                        item.get("fiscal_year"),
                        item.get("fund"),
                        item.get("department"),
                        item.get("program"),
                        item.get("line_item"),
                        item.get("budgeted_cents"),
                        item.get("revised_cents"),
                        item.get("actual_cents"),
                        item.get("source_url"),
                        item.get("source_page"),
                        item.get("notes"),
                        json.dumps(metadata, cls=DateTimeEncoder) if metadata else None,
                        as_of_str,
                        as_of_str,
                    ))

                if values:
                    psycopg2.extras.execute_values(
                        cursor,
                        """
                        INSERT INTO budget_items (
                            item_id, jurisdiction_id, fiscal_year, fund,
                            department, program, line_item, budgeted_cents,
                            revised_cents, actual_cents, source_url,
                            source_page, notes, metadata,
                            created_at, valid_from, valid_to
                        ) VALUES %s
                        """,
                        values,
                        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
                        page_size=500,
                    )

            conn.commit()
            return len(valid_items)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_budget_items(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
        fund: Optional[str] = None,
        department: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve budget items with optional filtering.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            fiscal_year: Filter by fiscal year (e.g., "2025-2026")
            fund: Filter by fund (e.g., "General Fund")
            department: Filter by department (e.g., "Police")
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of items to return

        Returns:
            List of budget item dictionaries
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM budget_items
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if fiscal_year is not None:
            query += " AND fiscal_year = %s"
            params.append(fiscal_year)

        if fund is not None:
            query += " AND fund = %s"
            params.append(fund)

        if department is not None:
            query += " AND department = %s"
            params.append(department)

        query += " ORDER BY department, fund, line_item"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries
        items = []
        for row in rows:
            item = dict(row)
            # Parse JSONB fields
            if "metadata" in item and isinstance(item["metadata"], str):
                try:
                    item["metadata"] = json.loads(item["metadata"])
                except json.JSONDecodeError:
                    item["metadata"] = {}
            # Convert datetime/date objects to ISO strings
            for key in ["created_at", "valid_from", "valid_to"]:
                if key in item and item[key] is not None:
                    if isinstance(item[key], (datetime, date)):
                        item[key] = item[key].isoformat()
            items.append(item)

        return items

    def get_budget_summary(
        self,
        jurisdiction_id: str,
        fiscal_year: str,
        group_by: str = "department",
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated budget summary grouped by department, fund, or program.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            fiscal_year: Fiscal year (e.g., "2025-2026")
            group_by: Grouping field ("department", "fund", or "program")
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            List of summary dictionaries with group name and totals
        """
        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Validate group_by to prevent SQL injection
        valid_groups = {"department", "fund", "program"}
        if group_by not in valid_groups:
            group_by = "department"

        query = f"""
            SELECT
                {group_by},
                SUM(budgeted_cents) as budgeted_cents,
                SUM(revised_cents) as revised_cents,
                SUM(actual_cents) as actual_cents,
                COUNT(*) as item_count
            FROM budget_items
            WHERE jurisdiction_id = %s
              AND fiscal_year = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
            GROUP BY {group_by}
            ORDER BY budgeted_cents DESC
        """
        params = [jurisdiction_id, fiscal_year, as_of.isoformat(), as_of.isoformat()]

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_budget_items_count(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
    ) -> int:
        """
        Get count of budget items for a jurisdiction.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            fiscal_year: Optional filter by fiscal year

        Returns:
            Number of current (non-expired) budget items
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*) FROM budget_items
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
        """
        params: List[Any] = [jurisdiction_id]

        if fiscal_year is not None:
            query += " AND fiscal_year = %s"
            params.append(fiscal_year)

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ========== Federal Awards Methods (SESSION 439) ==========

    def store_federal_awards(
        self,
        jurisdiction_id: str,
        awards: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store federal awards/grants with temporal versioning.

        Uses PostgreSQL COPY for bulk inserts.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            awards: List of award dictionaries
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of awards successfully stored

        Raises:
            psycopg2.Error: If store operation fails
        """
        # Normalize jurisdiction to canonical form (e.g., "san-rafael" -> "city-san-rafael")
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        as_of_str = as_of.isoformat()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Filter to valid awards with identifiers and positive amounts
            valid_awards = [
                award for award in awards
                if award.get("award_id") and award.get("amount_cents", 0) >= 0
            ]

            # Close previous versions for these award_ids
            award_ids = [award.get("award_id") for award in valid_awards if award.get("award_id")]
            if award_ids:
                for i in range(0, len(award_ids), 1000):
                    chunk = award_ids[i:i + 1000]
                    placeholders = ",".join(["%s"] * len(chunk))
                    cursor.execute(f"""
                        UPDATE federal_awards
                        SET valid_to = %s
                        WHERE jurisdiction_id = %s
                          AND award_id IN ({placeholders})
                          AND valid_to IS NULL
                    """, [as_of_str, jurisdiction_id] + chunk)

            # Insert new versions using execute_values for efficiency
            values = []
            for award in valid_awards:
                # Build metadata from extra fields
                metadata = {
                    k: v for k, v in award.items()
                    if k not in [
                        "award_id", "cfda_number", "recipient_uei", "recipient_name",
                        "amount_cents", "period_start", "period_end", "program_name",
                        "awarding_agency", "funding_agency", "award_type"
                    ]
                }
                values.append((
                    award.get("award_id"),
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
                    json.dumps(metadata, cls=DateTimeEncoder) if metadata else None,
                    as_of_str,
                    as_of_str,
                ))

            if values:
                psycopg2.extras.execute_values(
                    cursor,
                    """
                    INSERT INTO federal_awards (
                        award_id, jurisdiction_id, cfda_number, recipient_uei,
                        recipient_name, amount_cents, period_start, period_end,
                        program_name, awarding_agency, funding_agency, award_type,
                        metadata, created_at, valid_from, valid_to
                    ) VALUES %s
                    """,
                    values,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
                    page_size=500,
                )

            conn.commit()
            return len(valid_awards)

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
        Retrieve federal awards with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            cfda_number: Filter by CFDA number (e.g., "20.205" for highway grants)
            period_start: Filter awards with period_start on/after this date (YYYY-MM-DD)
            period_end: Filter awards with period_end on/before this date (YYYY-MM-DD)
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of awards to return

        Returns:
            List of award dictionaries
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM federal_awards
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if cfda_number is not None:
            query += " AND cfda_number = %s"
            params.append(cfda_number)

        if period_start is not None:
            query += " AND period_start >= %s"
            params.append(period_start)

        if period_end is not None:
            query += " AND period_end <= %s"
            params.append(period_end)

        query += " ORDER BY amount_cents DESC"

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries with parsed metadata
        awards = []
        for row in rows:
            award = dict(row)
            # Convert datetime objects to ISO strings
            for key in ['created_at', 'valid_from', 'valid_to', 'period_start', 'period_end']:
                if key in award and award[key] is not None:
                    if isinstance(award[key], (datetime, date)):
                        award[key] = award[key].isoformat()
            awards.append(award)

        return awards

    def get_federal_awards_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current federal awards for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) awards
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM federal_awards
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # =======================================================================
    # FEDERAL AUDIT EXPENDITURES (SESSION 449)
    # =======================================================================

    def store_federal_audit_expenditures(
        self,
        jurisdiction_id: str,
        expenditures: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store federal audit expenditures (SEFA data) with temporal versioning.

        SEFA = Schedule of Expenditures of Federal Awards, from Single Audits
        filed with the Federal Audit Clearinghouse. This is audited data showing
        actual expenditures, not just award amounts.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            expenditures: List of expenditure dicts from FAC client
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of records successfully stored

        Raises:
            psycopg2.Error: If store operation fails
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        as_of_str = as_of.isoformat()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Filter to valid expenditures with identifiers
            valid_expenditures = [
                e for e in expenditures
                if e.get("report_id") and e.get("cfda_number")
            ]

            # Close previous versions for these report_id + award_reference combos
            for exp in valid_expenditures:
                report_id = exp.get("report_id")
                award_ref = exp.get("award_reference")
                if report_id:
                    if award_ref:
                        cursor.execute("""
                            UPDATE federal_audit_expenditures
                            SET valid_to = %s
                            WHERE jurisdiction_id = %s
                              AND report_id = %s
                              AND award_reference = %s
                              AND valid_to IS NULL
                        """, [as_of_str, jurisdiction_id, report_id, award_ref])
                    else:
                        cursor.execute("""
                            UPDATE federal_audit_expenditures
                            SET valid_to = %s
                            WHERE jurisdiction_id = %s
                              AND report_id = %s
                              AND award_reference IS NULL
                              AND valid_to IS NULL
                        """, [as_of_str, jurisdiction_id, report_id])

            # Insert new versions using execute_values for efficiency
            values = []
            for e in valid_expenditures:
                # Build metadata from extra fields
                metadata = {
                    k: v for k, v in e.items()
                    if k not in [
                        "report_id", "award_reference", "cfda_number", "aln_number",
                        "auditee_uei", "auditee_ein", "auditee_name",
                        "audit_year", "fy_start_date", "fy_end_date",
                        "amount_expended_cents", "federal_program_total_cents",
                        "cluster_total_cents", "federal_program_name", "cluster_name",
                        "is_major", "is_passthrough", "is_passthrough_award",
                        "federal_agency_prefix", "source_url", "source",
                    ]
                }
                values.append((
                    e.get("report_id"),
                    e.get("award_reference"),
                    jurisdiction_id,
                    e.get("cfda_number") or e.get("aln_number"),
                    e.get("auditee_uei"),
                    e.get("auditee_ein"),
                    e.get("audit_year"),
                    e.get("fy_start_date"),
                    e.get("fy_end_date"),
                    e.get("amount_expended_cents", 0),
                    e.get("federal_program_total_cents"),
                    e.get("cluster_total_cents"),
                    e.get("federal_program_name"),
                    e.get("cluster_name"),
                    e.get("is_major", False),
                    e.get("is_passthrough") or e.get("is_passthrough_award", False),
                    e.get("federal_agency_prefix"),
                    e.get("source_url"),
                    json.dumps(metadata, cls=DateTimeEncoder) if metadata else None,
                    as_of_str,
                    as_of_str,
                ))

            if values:
                psycopg2.extras.execute_values(
                    cursor,
                    """
                    INSERT INTO federal_audit_expenditures (
                        report_id, award_reference, jurisdiction_id, cfda_number,
                        auditee_uei, auditee_ein, audit_year, fy_start_date, fy_end_date,
                        amount_expended_cents, federal_program_total_cents,
                        cluster_total_cents, federal_program_name, cluster_name,
                        is_major, is_passthrough, federal_agency_prefix, source_url,
                        metadata, created_at, valid_from, valid_to
                    ) VALUES %s
                    """,
                    values,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
                    page_size=500,
                )

            conn.commit()
            return len(valid_expenditures)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_federal_audit_expenditures(
        self,
        jurisdiction_id: str,
        cfda_number: Optional[str] = None,
        audit_year: Optional[int] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve federal audit expenditures with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            cfda_number: Filter by CFDA/ALN number (e.g., "20.205")
            audit_year: Filter by audit fiscal year
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of records to return

        Returns:
            List of expenditure dictionaries
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM federal_audit_expenditures
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if cfda_number is not None:
            query += " AND cfda_number = %s"
            params.append(cfda_number)

        if audit_year is not None:
            query += " AND audit_year = %s"
            params.append(audit_year)

        query += " ORDER BY audit_year DESC, amount_expended_cents DESC"

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries with proper serialization
        expenditures = []
        for row in rows:
            exp = dict(row)
            # Convert datetime objects to ISO strings
            for key in ['created_at', 'valid_from', 'valid_to', 'fy_start_date', 'fy_end_date']:
                if key in exp and exp[key] is not None:
                    if isinstance(exp[key], (datetime, date)):
                        exp[key] = exp[key].isoformat()
            expenditures.append(exp)

        return expenditures

    def get_federal_audit_expenditures_by_year(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Get federal audit expenditures grouped by audit year.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            Dict mapping audit_year -> list of expenditures
        """
        expenditures = self.get_federal_audit_expenditures(
            jurisdiction_id=jurisdiction_id,
            as_of=as_of,
        )

        by_year: Dict[int, List[Dict[str, Any]]] = {}
        for exp in expenditures:
            year = exp.get("audit_year")
            if year:
                if year not in by_year:
                    by_year[year] = []
                by_year[year].append(exp)

        return by_year

    def get_federal_audit_expenditures_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current federal audit expenditures for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) expenditure records
        """
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM federal_audit_expenditures
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

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

        Uses PostgreSQL execute_values for bulk inserts.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            passthroughs: List of passthrough dictionaries
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of records successfully stored

        Raises:
            psycopg2.Error: If store operation fails
        """
        # Normalize jurisdiction to canonical form (e.g., "san-rafael" -> "city-san-rafael")
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        as_of_str = as_of.isoformat()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Filter to valid passthroughs with identifiers and positive amounts
            valid_passthroughs = [
                p for p in passthroughs
                if p.get("passthrough_id") and p.get("local_amount_cents", 0) >= 0
            ]

            # Close previous versions for these passthrough_ids
            passthrough_ids = [p.get("passthrough_id") for p in valid_passthroughs if p.get("passthrough_id")]
            if passthrough_ids:
                for i in range(0, len(passthrough_ids), 1000):
                    chunk = passthrough_ids[i:i + 1000]
                    placeholders = ",".join(["%s"] * len(chunk))
                    cursor.execute(f"""
                        UPDATE state_passthrough_funds
                        SET valid_to = %s
                        WHERE jurisdiction_id = %s
                          AND passthrough_id IN ({placeholders})
                          AND valid_to IS NULL
                    """, [as_of_str, jurisdiction_id] + chunk)

            # Insert new versions using execute_values for efficiency
            values = []
            for p in valid_passthroughs:
                # Build metadata from extra fields
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
                values.append((
                    p.get("passthrough_id"),
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
                    json.dumps(metadata, cls=DateTimeEncoder) if metadata else None,
                    as_of_str,
                    as_of_str,
                ))

            if values:
                psycopg2.extras.execute_values(
                    cursor,
                    """
                    INSERT INTO state_passthrough_funds (
                        passthrough_id, jurisdiction_id, federal_award_id,
                        federal_cfda_number, federal_program_name, federal_amount_cents,
                        state_agency, state_program_name, state_grant_id,
                        local_amount_cents, allocation_percentage,
                        period_start, period_end,
                        federal_fiscal_year, state_fiscal_year,
                        source_url, notes, metadata, created_at, valid_from, valid_to
                    ) VALUES %s
                    """,
                    values,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
                    page_size=500,
                )

            conn.commit()
            return len(valid_passthroughs)

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
        Retrieve state pass-through funding records with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            state_agency: Filter by state agency (e.g., "HCD", "Caltrans")
            federal_cfda_number: Filter by federal CFDA number
            federal_award_id: Filter by linked federal award
            federal_fiscal_year: Filter by federal fiscal year
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of records to return

        Returns:
            List of passthrough dictionaries
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM state_passthrough_funds
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if state_agency is not None:
            query += " AND state_agency = %s"
            params.append(state_agency)

        if federal_cfda_number is not None:
            query += " AND federal_cfda_number = %s"
            params.append(federal_cfda_number)

        if federal_award_id is not None:
            query += " AND federal_award_id = %s"
            params.append(federal_award_id)

        if federal_fiscal_year is not None:
            query += " AND federal_fiscal_year = %s"
            params.append(federal_fiscal_year)

        query += " ORDER BY local_amount_cents DESC"

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to dictionaries with parsed metadata
        passthroughs = []
        for row in rows:
            p = dict(row)
            # Convert datetime objects to ISO strings
            for key in ['created_at', 'valid_from', 'valid_to', 'period_start', 'period_end']:
                if key in p and p[key] is not None:
                    if isinstance(p[key], (datetime, date)):
                        p[key] = p[key].isoformat()
            # Convert Decimal to float for allocation_percentage
            if 'allocation_percentage' in p and p['allocation_percentage'] is not None:
                p['allocation_percentage'] = float(p['allocation_percentage'])
            passthroughs.append(p)

        return passthroughs

    def get_state_passthrough_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current state pass-through records for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) passthrough records
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM state_passthrough_funds
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
        """, (jurisdiction_id,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # =======================================================================
    # BUDGET FUNDING SOURCE LINKS (SESSION 444)
    # Connect budget items to their federal/state funding sources
    # =======================================================================

    def store_budget_funding_links(
        self,
        jurisdiction_id: str,
        links: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store links between budget items and their funding sources.

        Uses PostgreSQL execute_values for bulk inserts.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            links: List of link dictionaries
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of links successfully stored

        Raises:
            psycopg2.Error: If store operation fails
        """
        # Normalize jurisdiction to canonical form (e.g., "san-rafael" -> "city-san-rafael")
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        as_of_str = as_of.isoformat()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Filter to valid links with required fields
            valid_links = [
                link for link in links
                if link.get("link_id") and link.get("budget_item_id") and link.get("match_type")
            ]

            # Close previous versions for these link_ids
            link_ids = [link.get("link_id") for link in valid_links if link.get("link_id")]
            if link_ids:
                for i in range(0, len(link_ids), 1000):
                    chunk = link_ids[i:i + 1000]
                    placeholders = ",".join(["%s"] * len(chunk))
                    cursor.execute(f"""
                        UPDATE budget_funding_source_links
                        SET valid_to = %s
                        WHERE jurisdiction_id = %s
                          AND link_id IN ({placeholders})
                          AND valid_to IS NULL
                    """, [as_of_str, jurisdiction_id] + chunk)

            # Insert new versions using execute_values for efficiency
            values = []
            for link in valid_links:
                values.append((
                    link.get("link_id"),
                    jurisdiction_id,
                    link.get("budget_item_id"),
                    link.get("federal_award_id"),
                    link.get("federal_cfda_number"),
                    link.get("passthrough_id"),
                    link.get("state_grant_id"),
                    link.get("match_type"),
                    link.get("match_confidence", 0.0),
                    link.get("match_source"),
                    link.get("match_notes"),
                    link.get("budget_cents"),
                    link.get("federal_cents"),
                    link.get("local_cents"),
                    link.get("reconciliation_status"),
                    link.get("variance_cents"),
                    link.get("variance_percentage"),
                    link.get("confirmed_by"),
                    link.get("confirmed_at"),
                    as_of_str,
                    as_of_str,
                ))

            if values:
                psycopg2.extras.execute_values(
                    cursor,
                    """
                    INSERT INTO budget_funding_source_links (
                        link_id, jurisdiction_id, budget_item_id,
                        federal_award_id, federal_cfda_number, passthrough_id, state_grant_id,
                        match_type, match_confidence, match_source, match_notes,
                        budget_cents, federal_cents, local_cents,
                        reconciliation_status, variance_cents, variance_percentage,
                        confirmed_by, confirmed_at,
                        created_at, valid_from, valid_to
                    ) VALUES %s
                    """,
                    values,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
                    page_size=500,
                )

            conn.commit()
            return len(valid_links)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_budget_funding_links(
        self,
        jurisdiction_id: str,
        budget_item_id: Optional[str] = None,
        federal_cfda_number: Optional[str] = None,
        match_type: Optional[str] = None,
        confirmed_only: bool = False,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve budget funding links with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            budget_item_id: Filter by specific budget item
            federal_cfda_number: Filter by CFDA number
            match_type: Filter by match type
            confirmed_only: If True, only return confirmed links
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of links to return

        Returns:
            List of link dictionaries
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        as_of = as_of or datetime.now()
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT * FROM budget_funding_source_links
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if budget_item_id is not None:
            query += " AND budget_item_id = %s"
            params.append(budget_item_id)

        if federal_cfda_number is not None:
            query += " AND federal_cfda_number = %s"
            params.append(federal_cfda_number)

        if match_type is not None:
            query += " AND match_type = %s"
            params.append(match_type)

        if confirmed_only:
            query += " AND confirmed_at IS NOT NULL"

        query += " ORDER BY match_confidence DESC, created_at DESC"

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        links = cursor.fetchall()
        conn.close()

        return [dict(link) for link in links]

    def get_budget_funding_links_count(
        self,
        jurisdiction_id: str,
        confirmed_only: bool = False,
    ) -> int:
        """
        Get count of current budget funding links for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction
            confirmed_only: If True, only count confirmed links

        Returns:
            Number of current (non-expired) links
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*) FROM budget_funding_source_links
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
        """
        params: List[Any] = [jurisdiction_id]

        if confirmed_only:
            query += " AND confirmed_at IS NOT NULL"

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()

        return count

    def confirm_budget_funding_link(
        self,
        jurisdiction_id: str,
        link_id: str,
        confirmed_by: str,
    ) -> bool:
        """
        Confirm an AI-suggested budget funding link.

        Updates the link's confirmed_by and confirmed_at fields.

        Args:
            jurisdiction_id: Target jurisdiction
            link_id: ID of the link to confirm
            confirmed_by: User/system confirming the link

        Returns:
            True if link was confirmed, False if link not found
        """
        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE budget_funding_source_links
                SET confirmed_by = %s,
                    confirmed_at = CURRENT_TIMESTAMP
                WHERE jurisdiction_id = %s
                  AND link_id = %s
                  AND valid_to IS NULL
                  AND confirmed_at IS NULL
            """, (confirmed_by, jurisdiction_id, link_id))

            rows_updated = cursor.rowcount
            conn.commit()
            return rows_updated > 0

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ========== Election Methods (SESSION 460) ==========

    def store_elections(
        self,
        jurisdiction_id: str,
        elections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store elections with temporal versioning.

        Atomic operation: either all elections are stored or none.
        Uses upsert semantics based on election id.
        """
        if not elections:
            return 0

        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)
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

            # Get election IDs we're updating
            election_ids = [e.get("id") for e in elections if e.get("id")]

            # Close previous versions for these election_ids
            if election_ids:
                cursor.execute("""
                    UPDATE elections
                    SET valid_to = %s
                    WHERE jurisdiction_id = %s
                      AND id = ANY(%s)
                      AND valid_to IS NULL
                """, (as_of.isoformat(), jurisdiction_id, election_ids))

            # Insert new versions
            for election in elections:
                election_id = election.get("id")
                if not election_id:
                    continue

                raw_data = election.get("raw_data")
                if raw_data and not isinstance(raw_data, str):
                    raw_data = json.dumps(raw_data, cls=DateTimeEncoder)

                cursor.execute("""
                    INSERT INTO elections (
                        id, jurisdiction_id, name, election_date, election_type,
                        source, source_url, raw_data, valid_from, valid_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """, (
                    election_id,
                    jurisdiction_id,
                    election.get("name"),
                    election.get("election_date"),
                    election.get("election_type"),
                    election.get("source", "unknown"),
                    election.get("source_url"),
                    raw_data,
                    as_of.isoformat(),
                ))

            conn.commit()
            return len(elections)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_elections(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        include_past: bool = False,
        election_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve elections with optional filtering.
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build query with temporal filtering
        query = """
            SELECT id, jurisdiction_id, name, election_date, election_type,
                   source, source_url, raw_data, valid_from, valid_to
            FROM elections
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if not include_past:
            today = date.today().isoformat()
            query += " AND election_date >= %s"
            params.append(today)

        if election_type is not None:
            query += " AND election_type = %s"
            params.append(election_type)

        query += " ORDER BY election_date ASC"

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_election_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current (future) elections for a jurisdiction.
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        today = date.today().isoformat()
        cursor.execute("""
            SELECT COUNT(*) FROM elections
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
              AND election_date >= %s
        """, (jurisdiction_id, today))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    # ========== Election Deadline Methods ==========

    def store_election_deadlines(
        self,
        election_id: str,
        deadlines: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store election deadlines with temporal versioning.
        """
        if not deadlines:
            return 0

        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Close previous versions for this election
            cursor.execute("""
                UPDATE election_deadlines
                SET valid_to = %s
                WHERE election_id = %s
                  AND valid_to IS NULL
            """, (as_of.isoformat(), election_id))

            # Insert new versions
            for i, deadline in enumerate(deadlines):
                deadline_id = f"{election_id}-{deadline.get('deadline_type', i)}"

                cursor.execute("""
                    INSERT INTO election_deadlines (
                        id, election_id, deadline_type, deadline_date,
                        description, valid_from, valid_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, NULL)
                """, (
                    deadline_id,
                    election_id,
                    deadline.get("deadline_type"),
                    deadline.get("deadline_date"),
                    deadline.get("description"),
                    as_of.isoformat(),
                ))

            conn.commit()
            return len(deadlines)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_election_deadlines(
        self,
        election_id: str,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve deadlines for an election.
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT id, election_id, deadline_type, deadline_date, description
            FROM election_deadlines
            WHERE election_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
            ORDER BY deadline_date ASC
        """, (election_id, as_of.isoformat(), as_of.isoformat()))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ========== Election Contest Methods ==========

    def store_election_contests(
        self,
        election_id: str,
        contests: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store election contests with temporal versioning.
        """
        if not contests:
            return 0

        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor()

        try:
            # Get contest IDs we're updating
            contest_ids = [c.get("id") for c in contests if c.get("id")]

            # Close previous versions for these contest_ids
            if contest_ids:
                cursor.execute("""
                    UPDATE election_contests
                    SET valid_to = %s
                    WHERE election_id = %s
                      AND id = ANY(%s)
                      AND valid_to IS NULL
                """, (as_of.isoformat(), election_id, contest_ids))

            # Insert new versions
            for contest in contests:
                contest_id = contest.get("id")
                if not contest_id:
                    continue

                raw_data = contest.get("raw_data")
                if raw_data and not isinstance(raw_data, str):
                    raw_data = json.dumps(raw_data, cls=DateTimeEncoder)

                cursor.execute("""
                    INSERT INTO election_contests (
                        id, election_id, title, contest_type, district_name,
                        raw_data, valid_from, valid_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                """, (
                    contest_id,
                    election_id,
                    contest.get("title"),
                    contest.get("contest_type"),
                    contest.get("district_name"),
                    raw_data,
                    as_of.isoformat(),
                ))

            conn.commit()
            return len(contests)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_election_contests(
        self,
        election_id: str,
        contest_type: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve contests for an election.
        """
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = """
            SELECT id, election_id, title, contest_type, district_name, raw_data
            FROM election_contests
            WHERE election_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [election_id, as_of.isoformat(), as_of.isoformat()]

        if contest_type is not None:
            query += " AND contest_type = %s"
            params.append(contest_type)

        query += " ORDER BY title ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ========== Elected Officials Methods ==========

    def store_elected_officials(
        self,
        jurisdiction_id: str,
        officials: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store elected officials with temporal versioning.
        """
        if not officials:
            return 0

        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)
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

            # Get official IDs we're updating
            official_ids = [o.get("id") for o in officials if o.get("id")]

            # Close previous versions for these official_ids
            if official_ids:
                cursor.execute("""
                    UPDATE elected_officials
                    SET valid_to = %s
                    WHERE jurisdiction_id = %s
                      AND id = ANY(%s)
                      AND valid_to IS NULL
                """, (as_of.isoformat(), jurisdiction_id, official_ids))

            # Insert new versions
            for official in officials:
                official_id = official.get("id")
                if not official_id:
                    continue

                # Handle name_variations - store as JSON array
                name_variations = official.get("name_variations", [])
                if isinstance(name_variations, list):
                    name_variations_json = json.dumps(name_variations)
                else:
                    name_variations_json = name_variations

                cursor.execute("""
                    INSERT INTO elected_officials (
                        id, name, seat, jurisdiction_id, term_start, term_end,
                        name_variations, candidate_id, valid_from, valid_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """, (
                    official_id,
                    official.get("name"),
                    official.get("seat"),
                    jurisdiction_id,
                    official.get("term_start"),
                    official.get("term_end"),
                    name_variations_json,
                    official.get("candidate_id"),
                    as_of.isoformat(),
                ))

            conn.commit()
            return len(officials)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_elected_officials(
        self,
        jurisdiction_id: str,
        current_only: bool = True,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve elected officials.
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)
        as_of = as_of or datetime.now()

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = """
            SELECT id, name, seat, jurisdiction_id, term_start, term_end,
                   name_variations, candidate_id
            FROM elected_officials
            WHERE jurisdiction_id = %s
              AND valid_from <= %s
              AND (valid_to IS NULL OR valid_to > %s)
        """
        params: List[Any] = [jurisdiction_id, as_of.isoformat(), as_of.isoformat()]

        if current_only:
            query += " AND term_end IS NULL"

        query += " ORDER BY name ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_official_by_name(
        self,
        jurisdiction_id: str,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Find official by name (fuzzy match on name_variations).
        """
        # Normalize jurisdiction to canonical form
        jurisdiction_id = normalize_jurisdiction(jurisdiction_id)

        conn = self._get_connection()
        self._ensure_schema(conn)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # First try exact name match or partial match
        cursor.execute("""
            SELECT id, name, seat, jurisdiction_id, term_start, term_end,
                   name_variations, candidate_id
            FROM elected_officials
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
              AND (name = %s OR name ILIKE %s OR name ILIKE %s)
            LIMIT 1
        """, (
            jurisdiction_id,
            name,
            f"%{name}%",
            f"{name}%",
        ))

        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

        # If not found, search in name_variations JSONB
        cursor.execute("""
            SELECT id, name, seat, jurisdiction_id, term_start, term_end,
                   name_variations, candidate_id
            FROM elected_officials
            WHERE jurisdiction_id = %s
              AND valid_to IS NULL
              AND name_variations::text ILIKE %s
            LIMIT 1
        """, (jurisdiction_id, f"%{name}%"))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None


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
        # Budget items methods (SESSION 434)
        'store_budget_items', 'get_budget_items', 'get_budget_summary', 'get_budget_items_count',
        # Federal awards methods (SESSION 439)
        'store_federal_awards', 'get_federal_awards', 'get_federal_awards_count',
        # State passthrough methods (SESSION 442)
        'store_state_passthrough_funds', 'get_state_passthrough_funds', 'get_state_passthrough_count',
        # Budget funding source links methods (SESSION 444)
        'store_budget_funding_links', 'get_budget_funding_links', 'get_budget_funding_links_count',
        'confirm_budget_funding_link',
        # Election methods (SESSION 460)
        'store_elections', 'get_elections', 'get_election_count',
        'store_election_deadlines', 'get_election_deadlines',
        'store_election_contests', 'get_election_contests',
        'store_elected_officials', 'get_elected_officials', 'get_official_by_name',
    ]
    for method in required_methods:
        assert hasattr(PostgresBackend, method), (
            f"PostgresBackend must implement {method}"
        )


_verify_protocol_compliance()
