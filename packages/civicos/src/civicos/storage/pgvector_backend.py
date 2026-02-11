"""
PgVectorBackend - PostgreSQL + pgvector implementation of VectorBackend protocol.

Production-grade vector search for multi-user deployments using PostgreSQL's
pgvector extension. This enables unified storage (StorageBackend + VectorBackend)
on the same PostgreSQL instance.

Part of the 4-stage pipeline: discover -> ingest -> store -> index.

Migration path from ChromaDB:
1. Deploy with PostgresBackend + ChromaDB (current)
2. Install pgvector extension on Postgres
3. Switch to PgVectorBackend
4. Remove ChromaDB dependency
"""

import json
import logging
import os
import time
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .backend import StorageBackend
from .vector import (
    SearchResult,
    VectorStats,
    VectorValidationResult,
)

if TYPE_CHECKING:
    from civicos._internal.embeddings.provider import EmbeddingProvider

logger = logging.getLogger(__name__)


def _serialize_metadata(metadata: Dict[str, Any]) -> str:
    """Serialize metadata dict to JSON, handling datetime objects."""
    def default_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return json.dumps(metadata, default=default_serializer)


# Default window sizes for windowed indexing (raw documents per window).
# Chunked types use smaller windows because each raw doc expands to many chunks.
_DEFAULT_WINDOW_SIZES = {
    "transcripts": 5,        # ~880 chunks per window (5 raw × ~176 chunks each)
    "legislation": 50,       # Bills expand to many chunks
    "codified_law": 100,     # Variable expansion
    "executive_orders": 100, # Variable expansion
    "municipal_code": 500,   # 1-3 chunks each
}
_DEFAULT_WINDOW_SIZE = 1000  # Non-chunked types: direct storage rows


# Optional imports - only required if PgVectorBackend is used
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None  # type: ignore
    PSYCOPG2_AVAILABLE = False


class PgVectorBackend:
    """
    PostgreSQL + pgvector implementation of VectorBackend protocol.

    Production-grade vector search using PostgreSQL's pgvector extension.
    Enables unified relational + vector storage on a single database.

    Requires:
    - PostgreSQL with pgvector extension installed
    - psycopg2: pip install psycopg2-binary
    - Embedding provider: fastembed (recommended), sentence-transformers, or openai

    Usage:
        storage = PostgresBackend("postgresql://...")
        vector = PgVectorBackend(
            connection_string="postgresql://...",
        )

        # Or with explicit provider for remote/API embeddings:
        from civicos._internal.embeddings import get_embedding_provider
        provider = get_embedding_provider("openai")
        vector = PgVectorBackend(
            connection_string="postgresql://...",
            embedding_provider=provider,
        )

        # Validate before use
        result = vector.validate()
        if not result.is_valid:
            raise RuntimeError(result.errors)

        # Index from storage (not memory!)
        count = vector.index_from_storage(storage, "city-san-rafael", "meetings")

        # Search
        results = vector.search("housing", "city-san-rafael")
    """

    # Default embedding model - matches CivicEmbeddings for consistency
    DEFAULT_MODEL = os.environ.get(
        "CIVICOS_EMBEDDING_MODEL",
        "nomic-ai/nomic-embed-text-v1.5"
    )

    # Default embedding dimension for nomic-embed-text-v1.5
    DEFAULT_DIMENSION = 768

    # Table name for vector storage
    TABLE_NAME = "vector_embeddings"

    # Class-level: track which connection strings have had schema verified.
    # Survives across multiple PgVectorBackend instances in the same process.
    _schemas_verified: set = set()

    def __init__(
        self,
        connection_string: str,
        embedding_model: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
        embedding_provider: Optional["EmbeddingProvider"] = None,
        provider_type: Optional[str] = None,
    ):
        """
        Initialize pgvector backend.

        Args:
            connection_string: PostgreSQL connection URL with pgvector extension
                e.g., "postgresql://user:pass@localhost:5432/civic"
            embedding_model: Model name for embedding generation (deprecated, use provider)
            embedding_dimension: Vector dimension for pgvector columns (auto-detected from provider)
            embedding_provider: Pre-configured EmbeddingProvider instance
            provider_type: Provider type string ('fastembed', 'local', 'openai') for lazy init
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PgVectorBackend. "
                "Install with: pip install psycopg2-binary"
            )

        self._conn_string = connection_string
        self._schema_ensured = connection_string in self._schemas_verified
        self._provider = embedding_provider
        self._provider_type = provider_type

        # Model/dimension config (used for lazy provider init or overrides)
        self._embedding_model_override = embedding_model
        self._embedding_dimension_override = embedding_dimension

    def _get_connection(self):
        """Get a database connection."""
        return psycopg2.connect(self._conn_string)

    @property
    def _embedding_provider(self) -> "EmbeddingProvider":
        """Lazy-load the embedding provider."""
        if self._provider is None:
            from civicos._internal.embeddings.provider import get_embedding_provider
            self._provider = get_embedding_provider(
                provider_type=self._provider_type,
                model_name=self._embedding_model_override,
            )
        return self._provider

    @property
    def _embedding_model(self) -> str:
        """Get embedding model name from provider."""
        return self._embedding_provider.model_name

    @property
    def _embedding_dimension(self) -> int:
        """Get embedding dimension from provider."""
        if self._embedding_dimension_override:
            return self._embedding_dimension_override
        return self._embedding_provider.embedding_dimension

    @property
    def backend_type(self) -> str:
        """Type identifier: 'pgvector'."""
        return "pgvector"

    @property
    def embedding_model(self) -> str:
        """
        Embedding model identifier.

        Returns the model name used for generating embeddings.
        """
        return self._embedding_model

    @property
    def embedding_dimension(self) -> int:
        """
        Embedding vector dimension.

        Returns the dimension of embedding vectors produced by the model.
        """
        return self._embedding_dimension

    @property
    def provider_type(self) -> str:
        """
        Embedding provider type identifier.

        Returns the type of embedding provider being used (e.g., 'fastembed', 'local', 'openai').
        """
        provider = self._embedding_provider
        if hasattr(provider, '__class__'):
            class_name = provider.__class__.__name__
            if 'FastEmbed' in class_name:
                return 'fastembed'
            elif 'SentenceTransformer' in class_name:
                return 'local'
            elif 'OpenAI' in class_name:
                return 'openai'
        return self._provider_type or 'fastembed'

    def _ensure_schema(self, conn, allow_dimension_change: bool = False) -> None:
        """
        Create the vector_embeddings table if it doesn't exist.

        Includes embedding_model tracking for data integrity - vectors from
        different models cannot be compared even if dimensions match.

        Runs at most once per connection string across all PgVectorBackend
        instances in the same process. This prevents 40 parallel vector workers
        from all running schema checks simultaneously.

        Args:
            conn: Database connection
            allow_dimension_change: If True, drop and recreate table if dimension differs
        """
        if self._schema_ensured and not allow_dimension_change:
            return
        cursor = conn.cursor()

        # Check if table exists and verify dimension compatibility
        cursor.execute(f"""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = '{self.TABLE_NAME}'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if table_exists:
            # Check current embedding dimension from pgvector column type
            cursor.execute(f"""
                SELECT atttypmod FROM pg_attribute
                WHERE attrelid = '{self.TABLE_NAME}'::regclass
                AND attname = 'embedding'
            """)
            result = cursor.fetchone()
            if result and result[0] > 0:
                current_dim = result[0]
                if current_dim != self._embedding_dimension:
                    if allow_dimension_change:
                        logger.warning(
                            f"Dimension change: table has {current_dim} dims, "
                            f"provider needs {self._embedding_dimension}. Recreating table."
                        )
                        cursor.execute(f"DROP TABLE {self.TABLE_NAME}")
                        conn.commit()
                        table_exists = False
                    else:
                        raise ValueError(
                            f"Dimension mismatch: table has {current_dim} dims, "
                            f"but provider produces {self._embedding_dimension} dims. "
                            f"Use --reindex to drop and recreate with new dimensions."
                        )

        if not table_exists:
            # Create table with vector column and model tracking
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                    id TEXT PRIMARY KEY,
                    jurisdiction_id TEXT NOT NULL,
                    corpus_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({self._embedding_dimension}),
                    embedding_model TEXT NOT NULL DEFAULT 'unknown',
                    meeting_id TEXT,
                    meeting_title TEXT,
                    meeting_datetime TIMESTAMP,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            # Migration: Add embedding_model column if missing (for existing tables)
            cursor.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = '{self.TABLE_NAME}'
                        AND column_name = 'embedding_model'
                    ) THEN
                        ALTER TABLE {self.TABLE_NAME}
                        ADD COLUMN embedding_model TEXT NOT NULL DEFAULT 'unknown';
                    END IF;
                END $$;
            """)

        # Create index on jurisdiction_id and corpus_type for filtering
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_jurisdiction_corpus
            ON {self.TABLE_NAME} (jurisdiction_id, corpus_type)
        """)

        # Create index on embedding_model for model validation queries
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_model
            ON {self.TABLE_NAME} (embedding_model)
        """)

        # Create HNSW index for fast similarity search
        # HNSW is preferred over IVFFlat because:
        # - Self-maintaining: new inserts are automatically indexed
        # - No retraining needed as data grows (critical for incremental ingestion)
        # - Better recall at equivalent speed
        # - No periodic rebuilds needed when adding cities
        try:
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_embedding_hnsw
                ON {self.TABLE_NAME} USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)
        except Exception as e:
            # Index may already exist or fail for other reasons
            logger.warning(f"Could not create HNSW index: {e}")

        conn.commit()
        self._schema_ensured = True
        PgVectorBackend._schemas_verified.add(self._conn_string)

    def validate(self) -> VectorValidationResult:
        """
        Validate vector backend connectivity.

        Checks:
        - PostgreSQL connection
        - pgvector extension installed
        - Required tables exist (or can be created)

        Returns:
            VectorValidationResult with validation status
        """
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        connected = False
        index_exists = False

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            connected = True

            # Check if pgvector extension is installed
            cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM pg_extension WHERE extname = 'vector'
                )
            """)
            has_pgvector = cursor.fetchone()[0]

            if not has_pgvector:
                # Try to create it (requires superuser or extension owner)
                try:
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    conn.commit()
                    logger.info("Created pgvector extension")
                except Exception as e:
                    errors.append(
                        f"pgvector extension not installed and cannot create: {e}. "
                        "Ask your database administrator to run: CREATE EXTENSION vector"
                    )
                    conn.rollback()

            # Check if table exists
            cursor.execute(f"""
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{self.TABLE_NAME}'
                )
            """)
            table_exists = cursor.fetchone()[0]

            if not table_exists:
                # Create the schema
                try:
                    self._ensure_schema(conn)
                    warnings.append(
                        f"Created {self.TABLE_NAME} table. Ready for indexing."
                    )
                    index_exists = True
                except Exception as e:
                    errors.append(f"Failed to create schema: {e}")
            else:
                index_exists = True
                # Verify column structure
                cursor.execute(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = '{self.TABLE_NAME}' AND table_schema = 'public'
                """)
                columns = {row[0] for row in cursor.fetchall()}
                required_columns = {
                    "id", "jurisdiction_id", "corpus_type", "content",
                    "embedding", "meeting_id", "meeting_title", "meeting_datetime",
                    "metadata", "created_at"
                }
                missing_cols = required_columns - columns
                if missing_cols:
                    errors.append(
                        f"Missing columns in {self.TABLE_NAME}: {missing_cols}"
                    )

            conn.close()

        except Exception as e:
            if psycopg2 and isinstance(e, psycopg2.Error):
                errors.append(f"PostgreSQL error: {str(e)}")
            else:
                errors.append(f"Connection error: {str(e)}")

        duration_ms = (time.time() - start_time) * 1000
        is_valid = connected and len(errors) == 0

        return VectorValidationResult(
            is_valid=is_valid,
            connected=connected,
            index_exists=index_exists,
            errors=errors,
            warnings=warnings,
            check_duration_ms=duration_ms,
        )

    def _decision_to_text(self, decision: Dict[str, Any]) -> str:
        """
        Convert a decision dict to text for embedding.

        Matches the format used by CivicEmbeddings for consistency.
        Prepends item_type so semantic search can distinguish actions from presentations.
        """
        parts = []

        item_type = decision.get("item_type", "action")
        if decision.get("title"):
            parts.append(f"[{item_type}] {decision['title']}")

        if decision.get("description"):
            parts.append(f"Description: {decision['description']}")

        if decision.get("outcome"):
            parts.append(f"Outcome: {decision['outcome']}")

        if decision.get("topics"):
            topics = decision["topics"]
            if isinstance(topics, list):
                parts.append(f"Topics: {', '.join(topics)}")

        return "\n".join(parts) if parts else str(decision)

    def _municipal_code_to_text(self, section: Dict[str, Any]) -> str:
        """
        Convert a municipal code section to text representation.

        Note: For vector indexing, use expand_municipal_code_to_chunks() instead,
        which properly chunks long sections using LegalChunker. This method is
        retained for display/summary purposes and the text_extractor interface.
        """
        parts = []

        if section.get("section_number"):
            parts.append(f"Section {section['section_number']}")

        if section.get("section_name"):
            parts.append(f": {section['section_name']}")

        if section.get("chapter"):
            parts.append(f" (Chapter {section['chapter']})")

        # Use full_text (DB schema) with fallback to content for compatibility
        content = section.get("full_text") or section.get("content")
        if content:
            parts.append(f"\n{content}")

        return "".join(parts) if parts else ""

    def _issue_to_text(self, issue: Dict[str, Any]) -> str:
        """
        Convert a 311 issue to text for embedding.
        """
        parts = []

        if issue.get("issue_type"):
            parts.append(f"Type: {issue['issue_type']}")

        if issue.get("summary"):
            parts.append(f"Summary: {issue['summary']}")

        if issue.get("description"):
            parts.append(f"Description: {issue['description']}")

        if issue.get("address"):
            parts.append(f"Location: {issue['address']}")

        if issue.get("status"):
            parts.append(f"Status: {issue['status']}")

        return "\n".join(parts) if parts else ""

    def _program_to_text(self, program: Dict[str, Any]) -> str:
        """
        Convert a federal program dict to text for embedding.
        """
        parts = []

        if program.get("program_name"):
            parts.append(f"Program: {program['program_name']}")

        if program.get("administering_agency"):
            parts.append(f"Agency: {program['administering_agency']}")

        if program.get("description"):
            parts.append(f"Description: {program['description']}")

        if program.get("eligible_activities"):
            activities = program["eligible_activities"]
            if isinstance(activities, list):
                parts.append(f"Eligible Activities: {', '.join(str(a) for a in activities)}")
            elif isinstance(activities, str):
                parts.append(f"Eligible Activities: {activities}")

        if program.get("topic"):
            parts.append(f"Topic: {program['topic']}")

        if program.get("cfda_number"):
            parts.append(f"CFDA Number: {program['cfda_number']}")

        if program.get("keywords"):
            keywords = program["keywords"]
            if isinstance(keywords, list):
                parts.append(f"Keywords: {', '.join(str(k) for k in keywords)}")

        return "\n".join(parts) if parts else ""

    def _state_program_to_text(self, grant: Dict[str, Any]) -> str:
        """
        Convert a state passthrough grant dict to text for embedding.

        State programs use a different schema from federal programs, with fields
        like state_program_name, state_agency, notes, and rich metadata JSONB.
        """
        import json

        parts = []

        if grant.get("state_program_name"):
            parts.append(f"Program: {grant['state_program_name']}")

        if grant.get("state_agency"):
            parts.append(f"Agency: {grant['state_agency']}")

        if grant.get("notes"):
            parts.append(f"Description: {grant['notes']}")

        # Extract from metadata JSONB (rich grant details from grants.ca.gov)
        metadata = grant.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        if metadata.get("categories"):
            cats = metadata["categories"]
            if isinstance(cats, list):
                parts.append(f"Categories: {', '.join(str(c) for c in cats)}")
            elif isinstance(cats, str):
                parts.append(f"Categories: {cats}")

        if metadata.get("eligible_geography"):
            parts.append(f"Geography: {metadata['eligible_geography']}")

        if metadata.get("matching_funds"):
            parts.append(f"Matching: {metadata['matching_funds']}")

        if metadata.get("status"):
            parts.append(f"Status: {metadata['status']}")

        if metadata.get("description"):
            # Full description from metadata if notes was brief
            parts.append(f"Details: {metadata['description']}")

        if grant.get("federal_cfda_number"):
            parts.append(f"CFDA Number: {grant['federal_cfda_number']}")

        # Include application period if available
        period_start = grant.get("period_start")
        period_end = grant.get("period_end")
        if period_start and period_end:
            parts.append(f"Application Period: {period_start} to {period_end}")

        return "\n".join(parts) if parts else ""

    def _legislation_to_text(self, bill: Dict[str, Any]) -> str:
        """
        Convert a legislation bill to text for embedding.

        Combines bill number, name, summary, and leverage point into
        searchable text representation.
        """
        parts = []

        if bill.get("bill_number"):
            parts.append(f"Bill: {bill['bill_number']}")

        if bill.get("bill_name"):
            parts.append(f"Title: {bill['bill_name']}")

        if bill.get("summary"):
            parts.append(f"Summary: {bill['summary']}")

        if bill.get("leverage_point"):
            parts.append(f"Local Impact: {bill['leverage_point']}")

        if bill.get("status"):
            parts.append(f"Status: {bill['status']}")

        # Include keywords for better semantic matching
        keywords = bill.get("keywords")
        if keywords:
            if isinstance(keywords, list):
                parts.append(f"Topics: {', '.join(keywords)}")
            elif isinstance(keywords, str):
                parts.append(f"Topics: {keywords}")

        return "\n".join(parts) if parts else ""

    def _budget_item_to_text(self, item: Dict[str, Any]) -> str:
        """
        Convert a budget item to text for embedding.

        Combines department, fund, program, line_item, and notes into
        searchable text representation. Does NOT include amounts in
        embedding text (amounts go in metadata for filtering/display).
        """
        parts = []

        if item.get("department"):
            parts.append(f"Department: {item['department']}")

        if item.get("fund"):
            parts.append(f"Fund: {item['fund']}")

        if item.get("program"):
            parts.append(f"Program: {item['program']}")

        if item.get("line_item"):
            parts.append(f"Line Item: {item['line_item']}")

        if item.get("notes"):
            parts.append(f"Notes: {item['notes']}")

        if item.get("fiscal_year"):
            parts.append(f"Fiscal Year: {item['fiscal_year']}")

        return "\n".join(parts) if parts else ""

    def _agenda_item_to_text(self, item: Dict[str, Any]) -> str:
        """
        Convert an agenda item to text for embedding.

        Combines title, description, summary, and why_it_matters for
        semantic search queries like "what happened about budget?"
        """
        parts = []

        if item.get("title"):
            parts.append(f"Title: {item['title']}")

        if item.get("description"):
            parts.append(f"Description: {item['description']}")

        if item.get("summary"):
            parts.append(f"Summary: {item['summary']}")

        if item.get("why_it_matters"):
            parts.append(f"Why It Matters: {item['why_it_matters']}")

        if item.get("project_type"):
            parts.append(f"Type: {item['project_type']}")

        if item.get("actionability"):
            parts.append(f"Actionability: {item['actionability']}")

        return "\n".join(parts) if parts else ""

    def _election_to_text(self, election: Dict[str, Any]) -> str:
        """
        Convert an election dict to text for embedding.

        Combines election name, type, date, and contest details for
        semantic search queries like "what's on the ballot about housing?"
        """
        parts = []

        if election.get("name"):
            parts.append(f"Election: {election['name']}")

        if election.get("election_type"):
            parts.append(f"Type: {election['election_type']}")

        if election.get("election_date"):
            parts.append(f"Date: {election['election_date']}")

        # Include contest/ballot measure info from raw_data if available
        raw_data = election.get("raw_data")
        if raw_data:
            if isinstance(raw_data, str):
                import json
                try:
                    raw_data = json.loads(raw_data)
                except json.JSONDecodeError:
                    raw_data = None

            if isinstance(raw_data, dict):
                # Contest titles
                contests = raw_data.get("contests", [])
                if contests:
                    contest_titles = [c.get("title") for c in contests if c.get("title")]
                    if contest_titles:
                        parts.append(f"Contests: {', '.join(contest_titles)}")

                # Ballot measure descriptions (key for semantic search)
                measures = raw_data.get("ballot_measures", [])
                if measures:
                    for measure in measures[:5]:  # Limit to first 5
                        title = measure.get("title", "")
                        desc = measure.get("description", "")
                        if title or desc:
                            parts.append(f"Ballot Measure: {title} - {desc}"[:500])

        return "\n".join(parts) if parts else str(election)

    def _fetch_window(
        self,
        storage_backend: StorageBackend,
        jurisdiction_id: str,
        corpus_type: str,
        window_offset: int,
        window_limit: int,
        transcript_chunker: Optional[callable],
        legal_chunker: Optional[callable],
    ) -> tuple:
        """
        Fetch one window of documents from storage, expanding chunked types.

        Returns:
            (documents, raw_count) where raw_count is the number of storage rows
            fetched (before expansion). For non-chunked types, raw_count == len(documents).
        """
        if corpus_type == "decisions":
            docs = storage_backend.get_decisions(jurisdiction_id, limit=window_limit, offset=window_offset)
            return docs, len(docs)
        elif corpus_type == "chunks":
            docs = storage_backend.get_chunks(jurisdiction_id, limit=window_limit, offset=window_offset)
            return docs, len(docs)
        elif corpus_type == "meetings":
            docs = storage_backend.get_meetings(jurisdiction_id, limit=window_limit, offset=window_offset)
            return docs, len(docs)
        elif corpus_type == "transcripts":
            raw = storage_backend.get_transcripts(jurisdiction_id, limit=window_limit, offset=window_offset)
            if not raw:
                return [], 0
            docs = transcript_chunker(raw)
            return docs, len(raw)
        elif corpus_type == "municipal_code":
            raw = storage_backend.get_municipal_code(jurisdiction_id, limit=window_limit, offset=window_offset)
            if not raw:
                return [], 0
            docs = legal_chunker(raw)
            return docs, len(raw)
        elif corpus_type == "issues":
            docs = storage_backend.get_issues(jurisdiction_id, limit=window_limit, offset=window_offset)
            return docs, len(docs)
        elif corpus_type == "legislation":
            state_code = jurisdiction_id.split("-")[-1].upper() if "-" in jurisdiction_id else jurisdiction_id.upper()
            raw = storage_backend.get_legislation(state=state_code, limit=window_limit, offset=window_offset)
            if not raw:
                return [], 0
            docs = legal_chunker(raw)
            return docs, len(raw)
        elif corpus_type == "codified_law":
            raw = storage_backend.get_codified_law(jurisdiction_id, limit=window_limit, offset=window_offset)
            if not raw:
                return [], 0
            docs = legal_chunker(raw)
            return docs, len(raw)
        elif corpus_type == "executive_orders":
            raw = storage_backend.get_executive_orders(limit=window_limit, offset=window_offset)
            if not raw:
                return [], 0
            docs = legal_chunker(raw)
            return docs, len(raw)
        elif corpus_type == "elections":
            docs = storage_backend.get_elections(jurisdiction_id, include_past=True, limit=window_limit, offset=window_offset)
            return docs, len(docs)
        elif corpus_type == "agenda_items":
            docs = storage_backend.get_agenda_items(jurisdiction_id=jurisdiction_id, limit=window_limit, offset=window_offset)
            return docs, len(docs)
        elif corpus_type == "programs":
            # Programs are global and small — fetch all on first window only
            if window_offset > 0:
                return [], 0
            docs = storage_backend.get_programs()
            return docs, len(docs)
        elif corpus_type == "state_programs":
            docs = storage_backend.get_state_passthrough_funds(jurisdiction_id, limit=window_limit, offset=window_offset)
            return docs, len(docs)
        elif corpus_type == "budget_items":
            docs = storage_backend.get_budget_items(jurisdiction_id, limit=window_limit, offset=window_offset)
            return docs, len(docs)
        else:
            raise ValueError(f"Unknown corpus_type: {corpus_type}")

    def _process_window(
        self,
        documents: List[Dict[str, Any]],
        corpus_type: str,
        jurisdiction_id: str,
        batch_size: int,
        use_copy: bool,
        video_to_meeting: Dict[str, str],
        meeting_metadata: Dict[str, tuple],
        video_metadata: Dict[str, tuple],
    ) -> int:
        """
        Embed and insert one window of documents into pgvector.

        Processes documents in batch_size chunks, generating embeddings and
        inserting via COPY or upsert. Manages its own DB connections (reconnects
        before each insert to handle cloud DB timeouts during embedding).

        Returns:
            Number of documents successfully indexed in this window.
        """
        indexed_count = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            # Prepare texts for embedding
            texts = []
            doc_data = []

            for idx, doc in enumerate(batch):
                # Generate text representation based on corpus type
                if corpus_type == "decisions":
                    text = self._decision_to_text(doc)
                    doc_id = doc.get("decision_id") or doc.get("id", f"decision-{i}-{idx}")
                    meeting_id = doc.get("meeting_id")
                    meeting_title = doc.get("meeting_title")
                    meeting_datetime = doc.get("meeting_date")
                elif corpus_type == "chunks":
                    text = doc.get("text", doc.get("content", ""))
                    doc_id = doc.get("chunk_id") or doc.get("id", f"chunk-{i}-{idx}")
                    meeting_id = doc.get("meeting_id")
                    meeting_title = doc.get("meeting_title")
                    meeting_datetime = doc.get("meeting_date")
                elif corpus_type == "meetings":
                    text = f"Title: {doc.get('title', '')}\n{doc.get('description', '')}"
                    doc_id = doc.get("meeting_id") or doc.get("id", f"meeting-{i}-{idx}")
                    meeting_id = doc_id
                    meeting_title = doc.get("title")
                    meeting_datetime = doc.get("meeting_datetime")
                elif corpus_type == "transcripts":
                    # doc is already a chunk from transcript_chunker
                    text = doc.get("text", "")
                    doc_id = doc.get("id", f"transcript-{i}-{idx}")
                    video_id = doc.get("video_id")
                    meeting_id = video_to_meeting.get(video_id, video_id) if video_to_meeting else video_id
                    if meeting_id in meeting_metadata:
                        meeting_datetime, meeting_title = meeting_metadata[meeting_id]
                    elif video_id in video_metadata:
                        meeting_datetime, meeting_title = video_metadata[video_id]
                    else:
                        meeting_datetime = None
                        meeting_title = None
                elif corpus_type == "municipal_code":
                    text = doc.get("text", "")
                    doc_id = doc.get("id", f"mc-{i}-{idx}")
                    meeting_id = None
                    meeting_title = doc.get("section_name")
                    meeting_datetime = None
                elif corpus_type == "issues":
                    text = self._issue_to_text(doc)
                    doc_id = doc.get("issue_id") or doc.get("id", f"issue-{i}-{idx}")
                    meeting_id = None
                    meeting_title = doc.get("summary") or doc.get("issue_type")
                    meeting_datetime = doc.get("created_at")
                elif corpus_type == "legislation":
                    text = doc.get("text", "")
                    doc_id = doc.get("id", f"leg-{i}-{idx}")
                    meeting_id = None
                    meeting_title = doc.get("bill_name") or doc.get("bill_number")
                    meeting_datetime = None
                elif corpus_type == "codified_law":
                    text = doc.get("text", "")
                    doc_id = doc.get("id", f"cl-{i}-{idx}")
                    meeting_id = None
                    meeting_title = doc.get("citation") or doc.get("heading")
                    meeting_datetime = None
                elif corpus_type == "executive_orders":
                    text = doc.get("text", "")
                    doc_id = doc.get("id", f"eo-{i}-{idx}")
                    meeting_id = None
                    meeting_title = doc.get("title") or f"EO {doc.get('eo_number')}"
                    meeting_datetime = doc.get("signing_date")
                elif corpus_type == "elections":
                    text = self._election_to_text(doc)
                    doc_id = doc.get("id", f"election-{i}-{idx}")
                    meeting_id = None
                    meeting_title = doc.get("name")
                    meeting_datetime = None
                elif corpus_type == "agenda_items":
                    text = self._agenda_item_to_text(doc)
                    doc_id = doc.get("id", f"agenda-{i}-{idx}")
                    meeting_id = doc.get("meeting_id")
                    meeting_title = doc.get("title")
                    meeting_datetime = None
                elif corpus_type == "programs":
                    text = self._program_to_text(doc)
                    doc_id = doc.get("program_id") or doc.get("id", f"program-{i}-{idx}")
                    meeting_id = None
                    meeting_title = doc.get("program_name")
                    meeting_datetime = None
                elif corpus_type == "state_programs":
                    text = self._state_program_to_text(doc)
                    doc_id = doc.get("passthrough_id") or doc.get("id", f"state-program-{i}-{idx}")
                    meeting_id = None
                    meeting_title = doc.get("state_program_name")
                    meeting_datetime = None
                elif corpus_type == "budget_items":
                    text = self._budget_item_to_text(doc)
                    doc_id = doc.get("item_id") or doc.get("id", f"budget-{i}-{idx}")
                    meeting_id = None
                    meeting_title = f"{doc.get('department', '')} - {doc.get('line_item', '')}"
                    meeting_datetime = None

                if not text.strip():
                    continue

                texts.append(text)
                metadata = {k: v for k, v in doc.items()
                            if k not in ["id", "decision_id", "text", "content",
                                        "meeting_id", "meeting_title", "meeting_date",
                                        "meeting_datetime"]}
                # Inject meeting_date into metadata for transcript search filtering
                if meeting_datetime is not None and "meeting_date" not in metadata:
                    if hasattr(meeting_datetime, 'strftime'):
                        metadata["meeting_date"] = meeting_datetime.strftime("%Y-%m-%d")
                    else:
                        metadata["meeting_date"] = str(meeting_datetime)[:10]
                doc_data.append({
                    "id": doc_id,
                    "content": text,
                    "meeting_id": meeting_id,
                    "meeting_title": meeting_title,
                    "meeting_datetime": meeting_datetime,
                    "metadata": metadata,
                })

            if not texts:
                continue

            # Generate embeddings in batch using configured provider
            embeddings = self._embedding_provider.encode(texts, batch_size=batch_size)

            # Open connection for insert (cloud DBs may timeout during embedding)
            conn = self._get_connection()
            cursor = conn.cursor()

            # Prepare bulk insert data (deduplicate by ID to avoid issues)
            insert_values = []
            seen_ids = set()
            now = datetime.utcnow()
            for embedding, data in zip(embeddings, doc_data):
                if data["id"] in seen_ids:
                    continue  # Skip duplicate IDs within same batch
                seen_ids.add(data["id"])
                # Parse meeting_datetime if it's a string
                meeting_dt = data["meeting_datetime"]
                if isinstance(meeting_dt, str):
                    try:
                        meeting_dt = datetime.fromisoformat(
                            meeting_dt.replace("Z", "+00:00")
                        )
                    except ValueError:
                        meeting_dt = None

                insert_values.append((
                    data["id"],
                    jurisdiction_id,
                    corpus_type,
                    data["content"],
                    embedding.tolist(),
                    self._embedding_model,
                    data["meeting_id"],
                    data["meeting_title"],
                    meeting_dt,
                    _serialize_metadata(data["metadata"]),
                    now,  # created_at
                    now,  # updated_at
                ))

            # Bulk insert using COPY (10x faster) or execute_values (supports upsert)
            try:
                if use_copy:
                    buffer = StringIO()
                    for row in insert_values:
                        line_parts = []
                        for val in row:
                            if val is None:
                                line_parts.append("\\N")
                            elif isinstance(val, list):
                                line_parts.append("[" + ",".join(str(x) for x in val) + "]")
                            elif isinstance(val, datetime):
                                line_parts.append(val.isoformat())
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
                        self.TABLE_NAME,
                        columns=(
                            "id", "jurisdiction_id", "corpus_type", "content", "embedding",
                            "embedding_model", "meeting_id", "meeting_title", "meeting_datetime",
                            "metadata", "created_at", "updated_at"
                        ),
                    )
                else:
                    from psycopg2.extras import execute_values
                    upsert_values = [row[:-2] for row in insert_values]
                    execute_values(
                        cursor,
                        f"""
                        INSERT INTO {self.TABLE_NAME}
                            (id, jurisdiction_id, corpus_type, content, embedding,
                             embedding_model, meeting_id, meeting_title, meeting_datetime,
                             metadata, updated_at)
                        VALUES %s
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            embedding_model = EXCLUDED.embedding_model,
                            meeting_id = EXCLUDED.meeting_id,
                            meeting_title = EXCLUDED.meeting_title,
                            meeting_datetime = EXCLUDED.meeting_datetime,
                            metadata = EXCLUDED.metadata,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        upsert_values,
                        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
                        page_size=500,
                    )
                indexed_count += len(insert_values)
                conn.commit()
            except Exception as e:
                logger.error(f"Bulk insert failed: {e}")
                conn.rollback()
            finally:
                conn.close()

        return indexed_count

    def index_from_storage(
        self,
        storage_backend: StorageBackend,
        jurisdiction_id: str,
        corpus_type: str = "decisions",
        batch_size: int = 100,
        allow_dimension_change: bool = False,
        offset: int = 0,
        limit: Optional[int] = None,
        transcript_chunker: Optional[callable] = None,
        legal_chunker: Optional[callable] = None,
        use_copy: bool = False,
        window_size: int = 0,
    ) -> int:
        """
        Build vector index from StorageBackend using windowed processing.

        Processes documents in windows to bound memory usage regardless of corpus
        size. Each window fetches a batch of documents from storage (via SQL
        OFFSET/LIMIT), generates embeddings, and inserts into pgvector.

        Args:
            storage_backend: Source of documents to index
            jurisdiction_id: Target jurisdiction (for legislation, use "state-CA" format)
            corpus_type: Type of documents ("decisions", "chunks", "meetings",
                        "transcripts", "municipal_code", "issues", "legislation",
                        "agenda_items", "elections")
            batch_size: Number of documents to embed at once within each window
            allow_dimension_change: If True, recreate table if embedding dimension differs
            offset: Skip first N documents (for splitting across jobs)
            limit: Process at most N documents (for splitting across jobs)
            use_copy: If True, use PostgreSQL COPY for bulk inserts (10x faster).
                     Only safe when existing vectors have been deleted first (no duplicates).
            transcript_chunker: Callable that accepts list of transcripts and returns
                              list of chunk dicts. Required when corpus_type="transcripts".
            legal_chunker: Callable that accepts list of documents and returns
                          list of chunk dicts. Required for chunked legal corpus types.
            window_size: Number of raw documents to fetch per window. 0 = auto-select
                        based on corpus type. Chunked types use smaller windows since
                        each raw doc expands to many chunks in memory.

        Returns:
            Number of documents successfully indexed
        """
        # Validate chunker requirements upfront
        if corpus_type == "transcripts" and transcript_chunker is None:
            raise ValueError(
                "transcript_chunker is required when corpus_type='transcripts'. "
                "Use civic._internal.meetings.transcript.expand_transcripts_to_chunks"
            )
        if corpus_type in ("municipal_code", "legislation", "codified_law", "executive_orders") and legal_chunker is None:
            raise ValueError(
                f"legal_chunker is required when corpus_type='{corpus_type}'"
            )

        # Auto-select window size based on corpus type
        if window_size <= 0:
            window_size = _DEFAULT_WINDOW_SIZES.get(corpus_type, _DEFAULT_WINDOW_SIZE)

        # Ensure schema exists (may recreate if dimension changed and allowed)
        conn = self._get_connection()
        self._ensure_schema(conn, allow_dimension_change=allow_dimension_change)
        conn.close()

        # Build metadata lookups once for transcripts (small data, reused across windows)
        video_to_meeting: Dict[str, str] = {}
        meeting_metadata: Dict[str, tuple] = {}
        video_metadata: Dict[str, tuple] = {}
        if corpus_type == "transcripts":
            video_to_meeting = storage_backend.get_video_meeting_mapping(jurisdiction_id) or {}
            if video_to_meeting:
                logger.info(f"  Built video->meeting lookup: {len(video_to_meeting)} mappings")

            try:
                all_meetings = storage_backend.get_meetings(jurisdiction_id)
                for m in all_meetings:
                    mid = m.get("id") or m.get("meeting_id")
                    mdt = m.get("meeting_datetime")
                    mtitle = m.get("title")
                    if mid and mdt:
                        meeting_metadata[mid] = (mdt, mtitle)
                logger.info(f"  Built meeting metadata lookup: {len(meeting_metadata)} meetings")
            except Exception as e:
                logger.debug(f"  Could not load meeting metadata: {e}")

            try:
                all_videos = storage_backend.get_videos(jurisdiction_id)
                for v in all_videos:
                    vid = v.get("id")
                    vdate = v.get("date")
                    vtitle = v.get("title")
                    if vid and vdate:
                        video_metadata[vid] = (vdate, vtitle)
                logger.info(f"  Built video metadata fallback: {len(video_metadata)} videos")
            except Exception as e:
                logger.debug(f"  Could not load video metadata: {e}")

        # Window loop: fetch, embed, insert in bounded-memory windows
        indexed_count = 0
        window_offset = offset
        raw_docs_fetched = 0

        logger.info(f"  Windowed indexing: window_size={window_size}, offset={offset}, limit={limit}")

        while True:
            # Calculate how many raw docs to fetch this window
            fetch_limit = window_size
            if limit is not None:
                remaining = limit - raw_docs_fetched
                if remaining <= 0:
                    break
                fetch_limit = min(window_size, remaining)

            # Fetch one window of documents (expanded for chunked types)
            documents, raw_count = self._fetch_window(
                storage_backend, jurisdiction_id, corpus_type,
                window_offset, fetch_limit,
                transcript_chunker, legal_chunker,
            )

            if not documents:
                if raw_docs_fetched == 0:
                    logger.warning(f"No {corpus_type} found in storage for {jurisdiction_id}")
                break

            logger.info(
                f"  Window at offset={window_offset}: {raw_count} raw docs -> "
                f"{len(documents)} documents to embed"
            )

            # Process this window (embed + insert in batch_size chunks)
            window_indexed = self._process_window(
                documents, corpus_type, jurisdiction_id,
                batch_size, use_copy,
                video_to_meeting, meeting_metadata, video_metadata,
            )
            indexed_count += window_indexed

            # Advance offset
            window_offset += raw_count
            raw_docs_fetched += raw_count

            # If we got fewer raw docs than requested, we've exhausted the source
            if raw_count < fetch_limit:
                break

        logger.info(
            f"Indexed {indexed_count} {corpus_type} for {jurisdiction_id}"
        )
        return indexed_count

    def search(
        self,
        query: str,
        jurisdiction_id: str,
        corpus_type: str = "decisions",
        top_k: int = 5,
        min_score: Optional[float] = None,
        meeting_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search for similar documents using pgvector similarity search.

        Uses PostgreSQL's <=> operator for cosine distance search.
        Cosine distance is converted to similarity: 1 - distance.

        Args:
            query: Search query text
            jurisdiction_id: Target jurisdiction
            corpus_type: Type of documents to search
            top_k: Maximum number of results
            min_score: Minimum similarity score threshold (0-1)
            meeting_id: Optional meeting ID to filter results to a specific meeting

        Returns:
            List of SearchResult ordered by similarity score (highest first)

        Raises:
            ValueError: If indexed vectors were created with a different model
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # HNSW search uses ef_search to control recall/speed tradeoff
        # Default (40) is good for most queries; increase for higher recall
        cursor.execute("SET hnsw.ef_search = 40")

        # Validate model compatibility - vectors from different models can't be compared
        cursor.execute(f"""
            SELECT DISTINCT embedding_model FROM {self.TABLE_NAME}
            WHERE jurisdiction_id = %s AND corpus_type = %s
        """, (jurisdiction_id, corpus_type))
        indexed_models = {row[0] for row in cursor.fetchall()}

        current_model = self._embedding_model

        # Normalize model names for comparison (e.g., "nomic-ai/nomic-embed-text-v1.5" -> "nomic-embed-text-v1.5")
        def normalize_model_name(name: str) -> str:
            return name.split('/')[-1] if '/' in name else name

        normalized_current = normalize_model_name(current_model)
        normalized_indexed = {normalize_model_name(m) for m in indexed_models}

        if indexed_models and indexed_models != {'unknown'} and normalized_current not in normalized_indexed:
            conn.close()
            raise ValueError(
                f"Model mismatch: index contains vectors from {indexed_models}, "
                f"but query would use '{current_model}'. "
                f"Vectors from different models cannot be compared. "
                f"Reindex with --reindex to rebuild with the current model."
            )

        # Generate query embedding using configured provider
        query_embedding = self._embedding_provider.encode([query])[0]

        # pgvector's <=> operator returns cosine distance (0-2 range)
        # Convert to similarity: 1 - distance
        # Filter by jurisdiction, corpus type, and matching model
        # Match both full model name (nomic-ai/nomic-embed-text-v1.5) and
        # normalized name (nomic-embed-text-v1.5) for compatibility with older indexes
        sql = f"""
            SELECT
                id,
                content,
                1 - (embedding <=> %s::vector) as similarity,
                meeting_id,
                meeting_title,
                meeting_datetime,
                metadata
            FROM {self.TABLE_NAME}
            WHERE jurisdiction_id = %s
              AND corpus_type = %s
              AND (embedding_model = %s OR embedding_model = %s OR embedding_model = 'unknown')
        """

        params: List[Any] = [query_embedding.tolist(), jurisdiction_id, corpus_type, current_model, normalized_current]

        if meeting_id is not None:
            sql += " AND meeting_id = %s"
            params.append(meeting_id)

        if min_score is not None:
            # cosine distance < 1 - min_score means similarity > min_score
            sql += " AND (embedding <=> %s::vector) < %s"
            params.extend([query_embedding.tolist(), 1 - min_score])

        sql += f"""
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params.extend([query_embedding.tolist(), top_k])

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            doc_id, content, similarity, meeting_id, meeting_title, meeting_dt, metadata_raw = row

            # Parse metadata - psycopg2 may return dict or JSON string
            if isinstance(metadata_raw, dict):
                metadata = metadata_raw
            elif metadata_raw:
                metadata = json.loads(metadata_raw)
            else:
                metadata = {}

            results.append(SearchResult(
                id=doc_id,
                content=content,
                score=float(similarity),
                jurisdiction_id=jurisdiction_id,
                corpus_type=corpus_type,
                meeting_id=meeting_id,
                meeting_title=meeting_title,
                meeting_datetime=meeting_dt,
                metadata=metadata,
            ))

        return results

    def count(
        self,
        jurisdiction_id: str,
        corpus_type: str = "decisions",
    ) -> int:
        """
        Count documents in the vector index.

        Args:
            jurisdiction_id: Target jurisdiction
            corpus_type: Type of documents to count

        Returns:
            Number of documents indexed
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT COUNT(*)
            FROM {self.TABLE_NAME}
            WHERE jurisdiction_id = %s AND corpus_type = %s
        """, (jurisdiction_id, corpus_type))

        row = cursor.fetchone()
        count = row[0] if row else 0
        conn.close()

        return count

    def get_stats(
        self,
        jurisdiction_id: str,
        corpus_type: str = "decisions",
        storage_backend: Optional[StorageBackend] = None,
    ) -> VectorStats:
        """
        Get vector index statistics.

        If storage_backend provided, includes coverage metrics.

        Args:
            jurisdiction_id: Target jurisdiction
            corpus_type: Type of documents
            storage_backend: Optional, for coverage calculation

        Returns:
            VectorStats with counts and coverage info
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Count indexed documents
        cursor.execute(f"""
            SELECT COUNT(*), MAX(updated_at)
            FROM {self.TABLE_NAME}
            WHERE jurisdiction_id = %s AND corpus_type = %s
        """, (jurisdiction_id, corpus_type))

        row = cursor.fetchone()
        doc_count = row[0] if row else 0
        last_indexed = row[1] if row else None

        conn.close()

        # Get storage count for coverage calculation
        storage_count = None
        if storage_backend:
            if corpus_type == "decisions":
                storage_count = storage_backend.get_decision_count(jurisdiction_id)
            elif corpus_type == "chunks":
                storage_count = storage_backend.get_chunk_count(jurisdiction_id)
            elif corpus_type == "meetings":
                meetings = storage_backend.get_meetings(jurisdiction_id)
                storage_count = len(meetings) if meetings else 0
            elif corpus_type == "transcripts":
                storage_count = storage_backend.get_transcript_count(jurisdiction_id)
            elif corpus_type == "municipal_code":
                storage_count = storage_backend.get_municipal_code_count(jurisdiction_id)
            elif corpus_type == "issues":
                storage_count = storage_backend.get_issue_count(jurisdiction_id)
            elif corpus_type == "legislation":
                # Legislation uses state code format (e.g., "legislation-CA" or "state-CA" -> "CA")
                state_code = jurisdiction_id.split("-")[-1].upper() if "-" in jurisdiction_id else jurisdiction_id.upper()
                storage_count = storage_backend.get_legislation_count(state_code)
            elif corpus_type == "codified_law":
                # Codified law uses jurisdiction_id directly (e.g., "federal-US", "state-CA", "federal-CFR")
                storage_count = storage_backend.get_codified_law_count(jurisdiction_id)
            elif corpus_type == "executive_orders":
                # Executive orders are all federal, no jurisdiction filter
                storage_count = storage_backend.get_executive_orders_count()
            elif corpus_type == "agenda_items":
                storage_count = storage_backend.get_agenda_item_count(jurisdiction_id)

        return VectorStats(
            jurisdiction_id=jurisdiction_id,
            corpus_type=corpus_type,
            document_count=doc_count,
            embedding_model=self._embedding_model,
            embedding_dimension=self._embedding_dimension,
            last_indexed=last_indexed,
            storage_document_count=storage_count,
            metadata={
                "backend_type": "pgvector",
                "table_name": self.TABLE_NAME,
            },
        )

    def delete_index(
        self,
        jurisdiction_id: str,
        corpus_type: Optional[str] = None,
    ) -> int:
        """
        Delete vector index (remove rows from pgvector table).

        If corpus_type is None, deletes all indices for jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction
            corpus_type: Specific corpus to delete (None = all)

        Returns:
            Number of documents deleted from index
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if corpus_type:
            cursor.execute(f"""
                DELETE FROM {self.TABLE_NAME}
                WHERE jurisdiction_id = %s AND corpus_type = %s
            """, (jurisdiction_id, corpus_type))
        else:
            cursor.execute(f"""
                DELETE FROM {self.TABLE_NAME}
                WHERE jurisdiction_id = %s
            """, (jurisdiction_id,))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        logger.info(
            f"Deleted {deleted} vectors for {jurisdiction_id}"
            + (f" ({corpus_type})" if corpus_type else "")
        )
        return deleted

    def encode_texts(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[Any]:
        """
        Generate embeddings for a list of texts.

        Public interface for embedding generation, used by parallel indexing workers.

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts to process at once

        Returns:
            List of embedding vectors (numpy arrays)
        """
        return self._embedding_provider.encode(texts, batch_size=batch_size)

    def bulk_insert_embeddings(
        self,
        records: List[Dict[str, Any]],
        jurisdiction_id: str,
        corpus_type: str,
        use_copy: bool = True,
    ) -> Dict[str, int]:
        """
        Bulk insert pre-computed embeddings into pgvector.

        Public interface for parallel indexing workers. Each record should contain:
        - id: Unique document identifier
        - content: Text content that was embedded
        - embedding: The embedding vector (list of floats)
        - meeting_id: Optional meeting reference
        - meeting_title: Optional display title
        - meeting_datetime: Optional datetime
        - metadata: Optional dict of additional metadata

        Args:
            records: List of embedding records to insert
            jurisdiction_id: Target jurisdiction
            corpus_type: Corpus type for these embeddings
            use_copy: If True, use PostgreSQL COPY for speed (requires no duplicates)

        Returns:
            Dict with 'success' and 'failed' counts
        """
        from io import StringIO
        from datetime import datetime

        if not records:
            return {"success": 0, "failed": 0}

        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow()

        if use_copy:
            buffer = StringIO()
            for record in records:
                # Escape content for COPY format
                content = record.get("content", "")
                content_escaped = (
                    content.replace("\\", "\\\\")
                    .replace("\t", "\\t")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                )

                # Format embedding as pgvector string
                embedding = record.get("embedding", [])
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

                # Handle metadata
                metadata = record.get("metadata", {})
                if not isinstance(metadata, str):
                    metadata = _serialize_metadata(metadata)
                metadata_escaped = (
                    metadata.replace("\\", "\\\\")
                    .replace("\t", "\\t")
                    .replace("\n", "\\n")
                )

                # Handle meeting_title
                meeting_title = record.get("meeting_title")
                if meeting_title:
                    meeting_title_escaped = (
                        meeting_title.replace("\\", "\\\\")
                        .replace("\t", "\\t")
                        .replace("\n", "\\n")
                    )
                else:
                    meeting_title_escaped = "\\N"

                # Handle meeting_datetime
                meeting_datetime = record.get("meeting_datetime")
                if meeting_datetime:
                    if hasattr(meeting_datetime, 'isoformat'):
                        meeting_datetime_str = meeting_datetime.isoformat()
                    else:
                        meeting_datetime_str = str(meeting_datetime)
                else:
                    meeting_datetime_str = "\\N"

                row = [
                    record.get("id", ""),
                    jurisdiction_id,
                    corpus_type,
                    content_escaped,
                    embedding_str,
                    self._embedding_model,
                    record.get("meeting_id") or "\\N",
                    meeting_title_escaped,
                    meeting_datetime_str,
                    metadata_escaped,
                    now.isoformat(),
                    now.isoformat(),
                ]
                buffer.write("\t".join(str(v) for v in row) + "\n")

            buffer.seek(0)

            try:
                cursor.copy_from(
                    buffer,
                    self.TABLE_NAME,
                    columns=(
                        "id", "jurisdiction_id", "corpus_type", "content", "embedding",
                        "embedding_model", "meeting_id", "meeting_title", "meeting_datetime",
                        "metadata", "created_at", "updated_at"
                    ),
                )
                conn.commit()
                conn.close()
                return {"success": len(records), "failed": 0}
            except Exception as e:
                conn.rollback()
                conn.close()
                logger.error(f"Bulk insert failed: {e}")
                return {"success": 0, "failed": len(records), "error": str(e)}
        else:
            # Use execute_values with upsert for incremental mode
            from psycopg2.extras import execute_values

            insert_values = []
            for record in records:
                metadata = record.get("metadata", {})
                if not isinstance(metadata, str):
                    metadata = _serialize_metadata(metadata)

                meeting_datetime = record.get("meeting_datetime")
                if isinstance(meeting_datetime, str):
                    try:
                        meeting_datetime = datetime.fromisoformat(
                            meeting_datetime.replace("Z", "+00:00")
                        )
                    except ValueError:
                        meeting_datetime = None

                insert_values.append((
                    record.get("id", ""),
                    jurisdiction_id,
                    corpus_type,
                    record.get("content", ""),
                    record.get("embedding", []),
                    self._embedding_model,
                    record.get("meeting_id"),
                    record.get("meeting_title"),
                    meeting_datetime,
                    metadata,
                ))

            try:
                execute_values(
                    cursor,
                    f"""
                    INSERT INTO {self.TABLE_NAME}
                        (id, jurisdiction_id, corpus_type, content, embedding,
                         embedding_model, meeting_id, meeting_title, meeting_datetime,
                         metadata, updated_at)
                    VALUES %s
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        embedding_model = EXCLUDED.embedding_model,
                        meeting_id = EXCLUDED.meeting_id,
                        meeting_title = EXCLUDED.meeting_title,
                        meeting_datetime = EXCLUDED.meeting_datetime,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    insert_values,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
                    page_size=500,
                )
                conn.commit()
                conn.close()
                return {"success": len(records), "failed": 0}
            except Exception as e:
                conn.rollback()
                conn.close()
                logger.error(f"Bulk insert failed: {e}")
                return {"success": 0, "failed": len(records), "error": str(e)}
