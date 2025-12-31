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
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .backend import StorageBackend
from .vector import (
    SearchResult,
    VectorStats,
    VectorValidationResult,
)

if TYPE_CHECKING:
    from civic._internal.embeddings.provider import EmbeddingProvider

logger = logging.getLogger(__name__)

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
        from civic._internal.embeddings import get_embedding_provider
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
        "CIVIC_EMBEDDING_MODEL",
        "nomic-ai/nomic-embed-text-v1.5"
    )

    # Default embedding dimension for nomic-embed-text-v1.5
    DEFAULT_DIMENSION = 768

    # Table name for vector storage
    TABLE_NAME = "vector_embeddings"

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
            from civic._internal.embeddings.provider import get_embedding_provider
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

        Args:
            conn: Database connection
            allow_dimension_change: If True, drop and recreate table if dimension differs
        """
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

        # Create IVFFlat index for fast similarity search
        # Only create if there are enough rows (IVFFlat needs training data)
        cursor.execute(f"""
            SELECT COUNT(*) FROM {self.TABLE_NAME}
        """)
        count = cursor.fetchone()[0]

        if count >= 100:
            # Create IVFFlat index with appropriate list count
            # Rule of thumb: lists = sqrt(n) for n < 1M, or n/1000 for larger
            lists = max(10, min(100, int(count ** 0.5)))
            try:
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_embedding
                    ON {self.TABLE_NAME} USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = {lists})
                """)
            except Exception as e:
                # Index may already exist or fail for other reasons
                logger.warning(f"Could not create IVFFlat index: {e}")

        conn.commit()

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
        """
        parts = []

        if decision.get("title"):
            parts.append(f"Title: {decision['title']}")

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
    ) -> int:
        """
        Build vector index from StorageBackend.

        Reads documents from storage, generates embeddings via configured provider,
        and stores in pgvector-enabled PostgreSQL table.

        Args:
            storage_backend: Source of documents to index
            jurisdiction_id: Target jurisdiction (for legislation, use "state-CA" format)
            corpus_type: Type of documents ("decisions", "chunks", "meetings",
                        "transcripts", "municipal_code", "issues", "legislation")
            batch_size: Number of documents to process at once
            allow_dimension_change: If True, recreate table if embedding dimension differs
            offset: Skip first N documents (for splitting across jobs)
            limit: Process at most N documents (for splitting across jobs)
            transcript_chunker: Callable that accepts list of transcripts and returns
                              list of chunk dicts. Required when corpus_type="transcripts".
                              Use civic._internal.meetings.transcript.expand_transcripts_to_chunks.
            legal_chunker: Callable that accepts list of municipal code sections and returns
                          list of chunk dicts. Required when corpus_type="municipal_code".
                          Use civic._internal.legal.embeddings.chunker.expand_municipal_code_to_chunks.

        Returns:
            Number of documents successfully indexed
        """
        conn = self._get_connection()

        # Ensure schema exists (may recreate if dimension changed and allowed)
        self._ensure_schema(conn, allow_dimension_change=allow_dimension_change)

        cursor = conn.cursor()

        # Get documents from storage based on corpus type
        if corpus_type == "decisions":
            documents = storage_backend.get_decisions(jurisdiction_id)
        elif corpus_type == "chunks":
            documents = storage_backend.get_chunks(jurisdiction_id)
        elif corpus_type == "meetings":
            documents = storage_backend.get_meetings(jurisdiction_id)
        elif corpus_type == "transcripts":
            # Expand transcripts to chunks for semantic search
            if transcript_chunker is None:
                raise ValueError(
                    "transcript_chunker is required when corpus_type='transcripts'. "
                    "Use civic._internal.meetings.transcript.expand_transcripts_to_chunks"
                )
            raw_transcripts = storage_backend.get_transcripts(jurisdiction_id)
            documents = transcript_chunker(raw_transcripts)
        elif corpus_type == "municipal_code":
            # Expand municipal code sections to chunks for semantic search
            if legal_chunker is None:
                raise ValueError(
                    "legal_chunker is required when corpus_type='municipal_code'. "
                    "Use civic._internal.legal.embeddings.chunker.expand_municipal_code_to_chunks"
                )
            raw_sections = storage_backend.get_municipal_code(jurisdiction_id)
            documents = legal_chunker(raw_sections)
        elif corpus_type == "issues":
            documents = storage_backend.get_issues(jurisdiction_id)
        elif corpus_type == "legislation":
            # Legislation uses state code, not jurisdiction_id
            # Convention: pass "state-CA" as jurisdiction_id -> extracts "CA"
            if jurisdiction_id.startswith("state-"):
                state_code = jurisdiction_id.split("-", 1)[1].upper()
            else:
                state_code = jurisdiction_id.upper()
            documents = storage_backend.get_legislation(state=state_code)
        else:
            raise ValueError(f"Unknown corpus_type: {corpus_type}")

        if not documents:
            logger.warning(
                f"No {corpus_type} found in storage for {jurisdiction_id}"
            )
            conn.close()
            return 0

        # Apply offset/limit for splitting across jobs
        total_docs = len(documents)
        if offset > 0 or limit is not None:
            end_idx = (offset + limit) if limit else total_docs
            documents = documents[offset:end_idx]
            logger.info(f"  Processing docs {offset}-{min(end_idx, total_docs)} of {total_docs}")

        if not documents:
            logger.info(f"  No documents in range (offset={offset}, limit={limit})")
            conn.close()
            return 0

        indexed_count = 0

        # Process in batches
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
                    # doc is already a chunk from _expand_transcripts_to_chunks
                    text = doc.get("text", "")
                    doc_id = doc.get("id", f"transcript-{i}-{idx}")
                    meeting_id = doc.get("video_id")  # Use video_id as meeting reference
                    meeting_title = None  # Will be in metadata
                    meeting_datetime = None  # Not available at chunk level
                elif corpus_type == "municipal_code":
                    # doc is already a chunk from expand_municipal_code_to_chunks
                    text = doc.get("text", "")
                    doc_id = doc.get("id", f"mc-{i}-{idx}")
                    meeting_id = None  # Not meeting-related
                    meeting_title = doc.get("section_name")
                    meeting_datetime = None
                elif corpus_type == "issues":
                    text = self._issue_to_text(doc)
                    doc_id = doc.get("issue_id") or doc.get("id", f"issue-{i}-{idx}")
                    meeting_id = None  # Not meeting-related
                    meeting_title = doc.get("summary") or doc.get("issue_type")
                    meeting_datetime = doc.get("created_at")
                elif corpus_type == "legislation":
                    text = self._legislation_to_text(doc)
                    doc_id = doc.get("bill_id") or doc.get("id", f"bill-{i}-{idx}")
                    meeting_id = None  # Not meeting-related
                    meeting_title = doc.get("bill_name") or doc.get("bill_number")
                    meeting_datetime = doc.get("enacted_date")

                if not text.strip():
                    continue

                texts.append(text)
                doc_data.append({
                    "id": doc_id,
                    "content": text,
                    "meeting_id": meeting_id,
                    "meeting_title": meeting_title,
                    "meeting_datetime": meeting_datetime,
                    "metadata": {k: v for k, v in doc.items()
                                 if k not in ["id", "decision_id", "text", "content",
                                             "meeting_id", "meeting_title", "meeting_date",
                                             "meeting_datetime"]}
                })

            if not texts:
                continue

            # Generate embeddings in batch using configured provider
            embeddings = self._embedding_provider.encode(texts, batch_size=batch_size)

            # Reconnect before insert (cloud DBs may timeout during embedding)
            try:
                conn.close()
            except Exception:
                pass  # Connection may already be closed
            conn = self._get_connection()
            cursor = conn.cursor()

            # Insert into database
            for j, (embedding, data) in enumerate(zip(embeddings, doc_data)):
                try:
                    # Parse meeting_datetime if it's a string
                    meeting_dt = data["meeting_datetime"]
                    if isinstance(meeting_dt, str):
                        try:
                            meeting_dt = datetime.fromisoformat(
                                meeting_dt.replace("Z", "+00:00")
                            )
                        except ValueError:
                            meeting_dt = None

                    # Upsert (insert or update on conflict)
                    cursor.execute(f"""
                        INSERT INTO {self.TABLE_NAME}
                            (id, jurisdiction_id, corpus_type, content, embedding,
                             embedding_model, meeting_id, meeting_title, meeting_datetime,
                             metadata, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            embedding_model = EXCLUDED.embedding_model,
                            meeting_id = EXCLUDED.meeting_id,
                            meeting_title = EXCLUDED.meeting_title,
                            meeting_datetime = EXCLUDED.meeting_datetime,
                            metadata = EXCLUDED.metadata,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        data["id"],
                        jurisdiction_id,
                        corpus_type,
                        data["content"],
                        embedding.tolist(),
                        self._embedding_model,  # Track which model created this embedding
                        data["meeting_id"],
                        data["meeting_title"],
                        meeting_dt,
                        json.dumps(data["metadata"]),
                    ))
                    indexed_count += 1

                except Exception as e:
                    logger.error(f"Failed to index document {data['id']}: {e}")
                    conn.rollback()
                    continue

            conn.commit()

        conn.close()
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

        Returns:
            List of SearchResult ordered by similarity score (highest first)

        Raises:
            ValueError: If indexed vectors were created with a different model
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Configure ivfflat probes for approximate search
        # Higher probes = better recall at cost of speed
        # With lists=12, probes=10 ensures good coverage
        cursor.execute("SET ivfflat.probes = 10")

        # Validate model compatibility - vectors from different models can't be compared
        cursor.execute(f"""
            SELECT DISTINCT embedding_model FROM {self.TABLE_NAME}
            WHERE jurisdiction_id = %s AND corpus_type = %s
        """, (jurisdiction_id, corpus_type))
        indexed_models = {row[0] for row in cursor.fetchall()}

        current_model = self._embedding_model
        if indexed_models and indexed_models != {'unknown'} and current_model not in indexed_models:
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
              AND (embedding_model = %s OR embedding_model = 'unknown')
        """

        params: List[Any] = [query_embedding.tolist(), jurisdiction_id, corpus_type, current_model]

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
                # Legislation uses state code format (e.g., "state-CA" -> "CA")
                if jurisdiction_id.startswith("state-"):
                    state_code = jurisdiction_id.split("-", 1)[1].upper()
                else:
                    state_code = jurisdiction_id.upper()
                storage_count = storage_backend.get_legislation_count(state_code)

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
