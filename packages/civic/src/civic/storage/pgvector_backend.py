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
from typing import Any, Dict, List, Optional

from .backend import StorageBackend
from .vector import (
    SearchResult,
    VectorStats,
    VectorValidationResult,
)

logger = logging.getLogger(__name__)

# Optional imports - only required if PgVectorBackend is used
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None  # type: ignore
    PSYCOPG2_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None  # type: ignore
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class PgVectorBackend:
    """
    PostgreSQL + pgvector implementation of VectorBackend protocol.

    Production-grade vector search using PostgreSQL's pgvector extension.
    Enables unified relational + vector storage on a single database.

    Requires:
    - PostgreSQL with pgvector extension installed
    - psycopg2: pip install psycopg2-binary
    - sentence-transformers: pip install sentence-transformers

    Usage:
        storage = PostgresBackend("postgresql://...")
        vector = PgVectorBackend(
            connection_string="postgresql://...",
            embedding_model="nomic-ai/nomic-embed-text-v1.5"
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
        embedding_model: str = DEFAULT_MODEL,
        embedding_dimension: int = DEFAULT_DIMENSION,
    ):
        """
        Initialize pgvector backend.

        Args:
            connection_string: PostgreSQL connection URL with pgvector extension
                e.g., "postgresql://user:pass@localhost:5432/civic"
            embedding_model: Model name for embedding generation
            embedding_dimension: Vector dimension for pgvector columns
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PgVectorBackend. "
                "Install with: pip install psycopg2-binary"
            )

        self._conn_string = connection_string
        self._embedding_model = embedding_model
        self._embedding_dimension = embedding_dimension
        self._model: Optional[SentenceTransformer] = None

    def _get_connection(self):
        """Get a database connection."""
        return psycopg2.connect(self._conn_string)

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the embedding model."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers is required for embedding generation. "
                "Install with: pip install sentence-transformers"
            )
        if self._model is None:
            # trust_remote_code=True required for models with custom code (e.g., nomic)
            self._model = SentenceTransformer(self._embedding_model, trust_remote_code=True)
        return self._model

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

    def _ensure_schema(self, conn) -> None:
        """
        Create the vector_embeddings table if it doesn't exist.

        Args:
            conn: Database connection
        """
        cursor = conn.cursor()

        # Create table with vector column
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                id TEXT PRIMARY KEY,
                jurisdiction_id TEXT NOT NULL,
                corpus_type TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector({self._embedding_dimension}),
                meeting_id TEXT,
                meeting_title TEXT,
                meeting_datetime TIMESTAMP,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index on jurisdiction_id and corpus_type for filtering
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_jurisdiction_corpus
            ON {self.TABLE_NAME} (jurisdiction_id, corpus_type)
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

    def _transcript_to_text(self, transcript: Dict[str, Any]) -> str:
        """
        Convert a transcript dict to text for embedding.

        Extracts plain text from transcript structure.
        """
        parts = []

        if transcript.get("video_title"):
            parts.append(f"Title: {transcript['video_title']}")

        # Extract text from transcript structure
        transcript_data = transcript.get("transcript", {})
        if isinstance(transcript_data, dict):
            text = transcript_data.get("text", "")
            if text:
                # Truncate very long transcripts for embedding
                # (full text still stored in metadata)
                max_chars = 8000  # ~2000 tokens for embedding
                if len(text) > max_chars:
                    text = text[:max_chars] + "..."
                parts.append(text)
        elif isinstance(transcript_data, str):
            parts.append(transcript_data[:8000])

        return "\n".join(parts) if parts else ""

    def _municipal_code_to_text(self, section: Dict[str, Any]) -> str:
        """
        Convert a municipal code section to text for embedding.
        """
        parts = []

        if section.get("section_number"):
            parts.append(f"Section {section['section_number']}")

        if section.get("section_name"):
            parts.append(f": {section['section_name']}")

        if section.get("chapter"):
            parts.append(f" (Chapter {section['chapter']})")

        if section.get("content"):
            content = section["content"]
            # Truncate very long sections
            max_chars = 4000  # Municipal code sections are usually structured
            if len(content) > max_chars:
                content = content[:max_chars] + "..."
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
    ) -> int:
        """
        Build vector index from StorageBackend.

        Reads documents from storage, generates embeddings via SentenceTransformer,
        and stores in pgvector-enabled PostgreSQL table.

        Args:
            storage_backend: Source of documents to index
            jurisdiction_id: Target jurisdiction (for legislation, use "state-CA" format)
            corpus_type: Type of documents ("decisions", "chunks", "meetings",
                        "transcripts", "municipal_code", "issues", "legislation")
            batch_size: Number of documents to process at once

        Returns:
            Number of documents successfully indexed
        """
        conn = self._get_connection()

        # Ensure schema exists
        self._ensure_schema(conn)

        cursor = conn.cursor()

        # Get documents from storage based on corpus type
        if corpus_type == "decisions":
            documents = storage_backend.get_decisions(jurisdiction_id)
        elif corpus_type == "chunks":
            documents = storage_backend.get_chunks(jurisdiction_id)
        elif corpus_type == "meetings":
            documents = storage_backend.get_meetings(jurisdiction_id)
        elif corpus_type == "transcripts":
            documents = storage_backend.get_transcripts(jurisdiction_id)
        elif corpus_type == "municipal_code":
            documents = storage_backend.get_municipal_code(jurisdiction_id)
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
                    text = self._transcript_to_text(doc)
                    doc_id = doc.get("video_id") or doc.get("id", f"transcript-{i}-{idx}")
                    meeting_id = doc.get("meeting_id")
                    meeting_title = doc.get("video_title")
                    meeting_datetime = doc.get("meeting_date")
                elif corpus_type == "municipal_code":
                    text = self._municipal_code_to_text(doc)
                    doc_id = f"mc-{doc.get('section_number', f'{i}-{idx}')}"
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

            # Generate embeddings in batch
            embeddings = self.model.encode(texts, show_progress_bar=False)

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
                             meeting_id, meeting_title, meeting_datetime, metadata,
                             updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
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
        """
        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        conn = self._get_connection()
        cursor = conn.cursor()

        # pgvector's <=> operator returns cosine distance (0-2 range)
        # Convert to similarity: 1 - distance
        # Filter by jurisdiction and corpus type
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
        """

        params: List[Any] = [query_embedding.tolist(), jurisdiction_id, corpus_type]

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
