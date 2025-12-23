"""
Embedding generation for meeting corpus using SentenceTransformer.

Uses local SentenceTransformer models to generate embeddings for RAG
without requiring external API calls (meeting foundation cost constraints).

Follows jurisdiction-first organization from docs/critical/VECTOR_RAG_SCHEMA.md:
- Collections: {jurisdiction_id}_decisions, {jurisdiction_id}_chunks
- Directory: data/pilot/vectors/{jurisdiction_id}/

Usage:
    from civic._internal.meetings.embeddings import CivicEmbeddings

    embedder = CivicEmbeddings("city-san-rafael")
    collection = embedder.build_index("data/pilot/rag_corpus/city-san-rafael")

    # Query
    results = embedder.search("homeless shelter funding")

    # Legacy alias for backward compatibility
    from civic._internal.meetings.embeddings import MerrydaleEmbeddings
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

from civic._internal.jurisdiction import normalize_jurisdiction
from civic.paths import get_vectors_dir, get_state_db_path


def _chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks for embedding.

    Preserves complete words and maintains overlap for context continuity.
    Used for municipal code sections that exceed embedding model limits.

    Args:
        text: Text to chunk
        max_chars: Maximum characters per chunk (default 1500 ≈ 375 tokens)
        overlap: Characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        # Find end position
        end = start + max_chars

        if end >= len(text):
            # Last chunk
            chunks.append(text[start:])
            break

        # Try to break at a paragraph boundary
        para_break = text.rfind("\n\n", start, end)
        if para_break > start + max_chars // 2:
            end = para_break

        # Try to break at a sentence boundary
        elif text.rfind(". ", start, end) > start + max_chars // 2:
            end = text.rfind(". ", start, end) + 1

        # Try to break at a word boundary
        elif text.rfind(" ", start, end) > start + max_chars // 2:
            end = text.rfind(" ", start, end)

        chunks.append(text[start:end])

        # Move start with overlap
        start = end - overlap
        if start >= len(text):
            break

    return chunks


try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None


@dataclass
class SearchResult:
    """A search result from the vector store."""
    document_id: str
    text: str
    score: float
    metadata: Dict[str, Any]


def load_video_meeting_map(manifest_path: Union[str, Path]) -> Dict[str, str]:
    """
    Load video ID to meeting date mapping from a manifest file.

    Args:
        manifest_path: Path to manifest JSON file (e.g., san_rafael_12month_manifest.json)

    Returns:
        Dict mapping video_id (str) to meeting_date (ISO format str)

    Example:
        >>> mapping = load_video_meeting_map("data/pilot/san_rafael_12month_manifest.json")
        >>> mapping["MpxrGRb16HQ"]
        '2024-10-06'
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    video_map: Dict[str, str] = {}

    # Process both 'meetings' and 'already_processed' arrays
    for meeting in manifest.get("meetings", []):
        if "youtube_id" in meeting and "date" in meeting:
            video_map[meeting["youtube_id"]] = meeting["date"]

    for meeting in manifest.get("already_processed", []):
        if "youtube_id" in meeting and "date" in meeting:
            video_map[meeting["youtube_id"]] = meeting["date"]

    return video_map


class CivicEmbeddings:
    """
    Local embedding generator for civic meeting corpus using SentenceTransformer.

    This class generates embeddings for decisions, chunks, and other
    meeting documents without requiring external API calls.

    Follows jurisdiction-first organization (see docs/critical/VECTOR_RAG_SCHEMA.md):
    - Collections named: {jurisdiction_id}_decisions, {jurisdiction_id}_chunks
    - Storage directory: data/pilot/vectors/{jurisdiction_id}/

    Features:
    - Local embedding model (nomic-ai/nomic-embed-text-v1.5) - 8192 token context, high quality
    - Persistent ChromaDB storage per jurisdiction
    - Semantic search over decisions and chunks
    - Topic classification via embedding similarity
    - No API costs (foundation cost constraint compliant)

    Usage:
        embedder = CivicEmbeddings("city-san-rafael")
        collection = embedder.build_index("data/pilot/rag_corpus/city-san-rafael")
        results = embedder.search("what happened with the homeless shelter?")

        # Topic classification
        topics = embedder.classify_topics("Affordable housing development near transit")
        # Returns: [("housing", 0.72), ("transportation", 0.45), ...]
    """

    # Default embedding model - high quality with 8192 token context
    # Alternatives: all-MiniLM-L6-v2 (smaller/faster), all-mpnet-base-v2 (PyTorch)
    DEFAULT_MODEL = "nomic-ai/nomic-embed-text-v1.5"

    # Canonical topic configurations for semantic classification
    # Each topic has: description (for embedding), bias (additive adjustment)
    # Bias is added to cosine similarity: positive boosts, negative penalizes.
    # Range: [-1.0, 1.0]. With threshold=0.35, bias of +0.05 means topic needs
    # only 0.30 raw similarity to qualify; -0.10 means it needs 0.45.
    TOPIC_CONFIG = {
        "housing": {
            "description": (
                "Housing development, affordable housing, residential units, apartments, "
                "zoning for housing, rental properties, home ownership, housing crisis, "
                "housing affordability, single-family homes, multi-family housing, ADUs, "
                "accessory dwelling units, residential density"
            ),
            "bias": 0.0,  # Core civic topic, no adjustment
        },
        "homelessness": {
            "description": (
                "Homeless services, emergency shelters, homeless encampments, unsheltered "
                "individuals, homeless crisis declaration, supportive housing, homeless "
                "outreach, transitional housing, homeless population, unhoused residents"
            ),
            "bias": 0.05,  # Boost for San Rafael pilot focus
        },
        "transportation": {
            "description": (
                "Public transit, bus routes, bicycle infrastructure, bike lanes, "
                "pedestrian safety, traffic management, highways, roads, parking, "
                "transportation planning, transit-oriented development, mobility"
            ),
            "bias": 0.0,
        },
        "environment": {
            "description": (
                "Environmental protection, climate change, sustainability, renewable energy, "
                "emissions reduction, pollution control, green infrastructure, conservation, "
                "environmental impact, climate action plan, carbon neutrality"
            ),
            "bias": 0.0,
        },
        "public_safety": {
            "description": (
                "Police services, fire department, emergency services, public safety, "
                "crime prevention, law enforcement, fire protection, emergency response, "
                "disaster preparedness, community safety"
            ),
            "bias": 0.0,
        },
        "budget": {
            "description": (
                "City budget, fiscal planning, financial appropriations, funding allocation, "
                "revenue, expenditures, budget approval, fiscal year, tax revenue, "
                "financial impact, budget amendments"
            ),
            "bias": -0.05,  # Penalize: often co-occurs, avoid over-tagging
        },
        "land_use": {
            "description": (
                "Zoning regulations, land use planning, general plan, development permits, "
                "urban planning, zoning changes, land use designations, planning commission, "
                "development standards, building codes"
            ),
            "bias": 0.0,
        },
        "development": {
            "description": (
                "Commercial development, real estate projects, construction, building "
                "permits, development agreements, mixed-use development, redevelopment, "
                "economic development, property development"
            ),
            "bias": -0.03,  # Slight penalty: overlaps with housing/land_use
        },
        "community": {
            "description": (
                "Community services, parks and recreation, community programs, public "
                "facilities, community engagement, neighborhood services, public events, "
                "community centers, youth programs, senior services"
            ),
            "bias": -0.05,  # Penalize: broad category
        },
        "governance": {
            "description": (
                "City council, municipal governance, city administration, ordinances, "
                "resolutions, city charter, council meetings, public hearings, "
                "government operations, policy decisions"
            ),
            "bias": -0.10,  # Strong penalty: most items are governance procedurally
        },
    }

    # Backward compatibility: expose descriptions dict
    @property
    def TOPIC_DESCRIPTIONS(self) -> Dict[str, str]:
        """Get topic descriptions (for backward compatibility)."""
        return {topic: cfg["description"] for topic, cfg in self.TOPIC_CONFIG.items()}

    def __init__(
        self,
        jurisdiction_id: str = "city-san-rafael",
        model_name: str = DEFAULT_MODEL,
        persist_directory: Optional[str] = None,
        collection_suffix: str = "",
    ):
        """
        Initialize the embedding generator for a specific jurisdiction.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")
            model_name: SentenceTransformer model to use
            persist_directory: Path to store ChromaDB data. If None, uses
                              data/pilot/vectors/{jurisdiction_id}/
            collection_suffix: Optional suffix for collection names to enable
                              test isolation (e.g., "_worker0" for pytest-xdist)
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb is required. Install with: pip install chromadb"
            )
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers is required. Install with: pip install sentence-transformers"
            )

        # Normalize jurisdiction ID for consistent collection naming
        self.jurisdiction_id = normalize_jurisdiction(jurisdiction_id)
        self.model_name = model_name
        self.collection_suffix = collection_suffix

        # Collection names follow schema: {jurisdiction_id}_decisions[_suffix]
        self.decisions_collection_name = f"{self.jurisdiction_id}_decisions{collection_suffix}"
        self.chunks_collection_name = f"{self.jurisdiction_id}_chunks{collection_suffix}"
        self.transcripts_collection_name = f"{self.jurisdiction_id}_transcripts{collection_suffix}"
        self.issues_collection_name = f"{self.jurisdiction_id}_issues{collection_suffix}"
        self.municipal_code_collection_name = f"{self.jurisdiction_id}_municipal_code{collection_suffix}"
        self.legislation_collection_name = f"{self.jurisdiction_id}_legislation{collection_suffix}"
        self.federal_programs_collection_name = f"{self.jurisdiction_id}_federal_programs{collection_suffix}"
        self.county_programs_collection_name = f"{self.jurisdiction_id}_county_programs{collection_suffix}"

        # Persist directory follows schema: data/pilot/vectors/{jurisdiction_id}/
        if persist_directory is None:
            persist_directory = get_vectors_dir(self.jurisdiction_id)
        self.persist_directory = persist_directory

        # Initialize model (lazy loading on first use)
        self._model: Optional[SentenceTransformer] = None

        # Initialize ChromaDB client
        os.makedirs(persist_directory, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the embedding model."""
        if self._model is None:
            # trust_remote_code=True required for models with custom code (e.g., nomic)
            self._model = SentenceTransformer(self.model_name, trust_remote_code=True)
        return self._model

    @property
    def embedding_dimension(self) -> int:
        """Get the embedding dimension for the current model."""
        return self.model.get_sentence_embedding_dimension()

    def classify_topics(
        self,
        text: str,
        threshold: float = 0.35,
        top_k: Optional[int] = None,
        apply_bias: bool = True,
    ) -> List[tuple]:
        """
        Classify text into civic topics using embedding similarity.

        Computes cosine similarity between the input text and canonical
        topic descriptions to determine which topics are relevant.

        Args:
            text: Input text to classify (e.g., agenda item title/description)
            threshold: Minimum similarity score to include a topic (0.0-1.0).
                      Default 0.35 balances precision/recall for civic text.
            top_k: If set, return only the top-k highest scoring topics
                  regardless of threshold.
            apply_bias: If True (default), apply per-topic bias adjustments
                       from TOPIC_CONFIG. Set False for raw similarity scores.

        Returns:
            List of (topic_name, similarity_score) tuples, sorted by score descending.
            Topics below threshold are excluded unless top_k forces inclusion.

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> topics = embedder.classify_topics(
            ...     "Approve funding for homeless shelter at 350 Merrydale Road"
            ... )
            >>> topics
            [('homelessness', 0.68), ('housing', 0.42), ('budget', 0.38)]
        """
        import numpy as np

        # Get topic embeddings (cached after first call)
        if not hasattr(self, '_topic_embeddings'):
            self._topic_embeddings = {
                topic: self.model.encode(cfg["description"])
                for topic, cfg in self.TOPIC_CONFIG.items()
            }

        # Embed input text
        text_embedding = self.model.encode(text)

        # Compute similarity to each topic
        scores = []
        for topic, topic_embedding in self._topic_embeddings.items():
            # Cosine similarity
            dot_product = np.dot(text_embedding, topic_embedding)
            norm1 = np.linalg.norm(text_embedding)
            norm2 = np.linalg.norm(topic_embedding)
            raw_similarity = dot_product / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0.0

            # Apply bias adjustment if enabled
            if apply_bias:
                bias = self.TOPIC_CONFIG[topic].get("bias", 0.0)
                adjusted_score = raw_similarity + bias
            else:
                adjusted_score = raw_similarity

            scores.append((topic, float(adjusted_score)))

        # Sort by similarity descending
        scores.sort(key=lambda x: x[1], reverse=True)

        # Apply top_k filter if specified
        if top_k is not None:
            scores = scores[:top_k]

        # Apply threshold filter
        scores = [(topic, score) for topic, score in scores if score >= threshold]

        return scores

    def get_topic_names(
        self,
        text: str,
        threshold: float = 0.35,
        top_k: Optional[int] = None,
    ) -> List[str]:
        """
        Get list of topic names for text classification.

        Convenience wrapper around classify_topics() that returns just
        the topic names without scores.

        Args:
            text: Input text to classify
            threshold: Minimum similarity score (default 0.35)
            top_k: Maximum number of topics to return

        Returns:
            List of topic names, sorted by relevance

        Example:
            >>> embedder.get_topic_names("New bike lane on 4th Street")
            ['transportation']
        """
        scored = self.classify_topics(text, threshold=threshold, top_k=top_k)
        return [topic for topic, _ in scored]

    def find_similar_issue_types(
        self,
        query_topic: str,
        issue_types: List[str],
        threshold: float = 0.3,
        top_k: Optional[int] = None,
    ) -> List[tuple]:
        """
        Find issue types semantically similar to a query topic.

        Uses embedding similarity to match a user's natural language query
        (e.g., "traffic problems") to actual issue type names in the database
        (e.g., "pothole", "traffic_signal", "street_damage").

        This enables whos_with_me() to find related issues even when the user
        doesn't know the exact issue type names.

        Args:
            query_topic: Natural language topic query (e.g., "traffic safety")
            issue_types: List of issue type names from the database
            threshold: Minimum similarity score to include (0.0-1.0).
                      Default 0.3 is lower than topic classification since
                      issue type names are often short/technical.
            top_k: If set, return only the top-k most similar types

        Returns:
            List of (issue_type, similarity_score) tuples, sorted by score descending.
            Only types meeting threshold are included (unless top_k forces it).

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> types = ["pothole", "graffiti", "traffic_signal", "sidewalk"]
            >>> embedder.find_similar_issue_types("traffic problems", types)
            [('traffic_signal', 0.67), ('pothole', 0.45), ('sidewalk', 0.38)]
        """
        import numpy as np

        if not issue_types:
            return []

        # Embed query topic
        query_embedding = self.model.encode(query_topic)

        # Embed each issue type (add context for short names)
        # Prefix with "civic issue: " to provide embedding context
        scores = []
        for issue_type in issue_types:
            # Expand issue type name for better embedding
            # e.g., "pothole" -> "civic issue: pothole"
            type_text = f"civic issue: {issue_type.replace('_', ' ')}"
            type_embedding = self.model.encode(type_text)

            # Cosine similarity
            dot_product = np.dot(query_embedding, type_embedding)
            norm1 = np.linalg.norm(query_embedding)
            norm2 = np.linalg.norm(type_embedding)
            similarity = dot_product / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0.0

            scores.append((issue_type, float(similarity)))

        # Sort by similarity descending
        scores.sort(key=lambda x: x[1], reverse=True)

        # Apply top_k filter if specified
        if top_k is not None:
            scores = scores[:top_k]

        # Apply threshold filter
        scores = [(issue_type, score) for issue_type, score in scores if score >= threshold]

        return scores

    def build_decisions_index(
        self,
        corpus_dir: Union[str, Path],
        decisions_file: Optional[str] = None,
    ) -> Any:  # Returns chromadb.Collection
        """
        Build vector index for decisions from the corpus.

        Args:
            corpus_dir: Path to the corpus directory
            decisions_file: Name of the decisions JSON file. If None, tries
                           {jurisdiction_id}_decisions.json then nov17_decisions.json

        Returns:
            ChromaDB collection with embedded decisions
        """
        corpus_path = Path(corpus_dir)

        # Try to find decisions file
        if decisions_file is None:
            # Try jurisdiction-based naming first, then legacy
            candidates = [
                f"{self.jurisdiction_id}_decisions.json",
                "nov17_decisions.json",  # Legacy for backward compatibility
            ]
            for candidate in candidates:
                if (corpus_path / candidate).exists():
                    decisions_file = candidate
                    break
            if decisions_file is None:
                raise FileNotFoundError(
                    f"No decisions file found in {corpus_path}. "
                    f"Tried: {candidates}"
                )

        decisions_path = corpus_path / decisions_file

        if not decisions_path.exists():
            raise FileNotFoundError(f"Decisions file not found: {decisions_path}")

        with open(decisions_path) as f:
            decisions = json.load(f)

        # Create collection (delete existing if present)
        try:
            self._client.delete_collection(self.decisions_collection_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=self.decisions_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "description": f"{self.jurisdiction_id} decisions for RAG",
                "jurisdiction_id": self.jurisdiction_id,
                "embedding_model": self.model_name,
                "embedding_dimension": self.embedding_dimension,
                "created_at": datetime.now().isoformat(),
                "source": str(decisions_path),
            }
        )

        # Generate embeddings for each decision
        texts = []
        ids = []
        metadatas = []

        for decision in decisions:
            # Build rich text representation for embedding
            text = self._decision_to_text(decision)
            texts.append(text)

            # Use decision_id as document ID
            doc_id = decision.get("decision_id", f"decision-{len(ids)}")
            ids.append(doc_id)

            # Create metadata (ChromaDB has type restrictions - only str, int, float, bool)
            metadata = self._decision_to_metadata(decision)
            metadatas.append(metadata)

        # Generate embeddings in batch
        embeddings = self.model.encode(texts, show_progress_bar=False)

        # Add to collection
        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )

        return collection

    def has_decisions(self) -> bool:
        """Check if decisions collection exists and has documents."""
        try:
            collection = self._client.get_collection(self.decisions_collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def build_chunks_index(
        self,
        corpus_dir: Union[str, Path],
        chunks_file: Optional[str] = None,
    ) -> Any:  # Returns chromadb.Collection
        """
        Build vector index for text chunks from the corpus.

        Args:
            corpus_dir: Path to the corpus directory
            chunks_file: Name of the chunks JSON file. If None, tries
                        {jurisdiction_id}_chunks.json then nov17_chunks.json

        Returns:
            ChromaDB collection with embedded chunks
        """
        corpus_path = Path(corpus_dir)

        # Try to find chunks file
        if chunks_file is None:
            candidates = [
                f"{self.jurisdiction_id}_chunks.json",
                "nov17_chunks.json",  # Legacy for backward compatibility
            ]
            for candidate in candidates:
                if (corpus_path / candidate).exists():
                    chunks_file = candidate
                    break
            if chunks_file is None:
                raise FileNotFoundError(
                    f"No chunks file found in {corpus_path}. "
                    f"Tried: {candidates}"
                )

        chunks_path = corpus_path / chunks_file

        if not chunks_path.exists():
            raise FileNotFoundError(f"Chunks file not found: {chunks_path}")

        with open(chunks_path) as f:
            chunks = json.load(f)

        # Create collection (delete existing if present)
        try:
            self._client.delete_collection(self.chunks_collection_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=self.chunks_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "description": f"{self.jurisdiction_id} text chunks for RAG",
                "jurisdiction_id": self.jurisdiction_id,
                "embedding_model": self.model_name,
                "embedding_dimension": self.embedding_dimension,
                "created_at": datetime.now().isoformat(),
                "source": str(chunks_path),
            }
        )

        # Process chunks in batches for memory efficiency
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]

            texts = [chunk.get("text", "") for chunk in batch]
            ids = [f"chunk-{i + j}" for j in range(len(batch))]
            metadatas = [self._chunk_to_metadata(chunk) for chunk in batch]

            embeddings = self.model.encode(texts, show_progress_bar=False)

            collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
            )

        return collection

    def has_chunks(self) -> bool:
        """Check if chunks collection exists and has documents."""
        try:
            collection = self._client.get_collection(self.chunks_collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def build_transcripts_index(
        self,
        testimony_dir: Union[str, Path],
        use_speaker_detection: bool = True,
        detect_agenda_items: bool = True,
        video_meeting_map: Optional[Dict[str, str]] = None,
    ) -> Any:  # Returns chromadb.Collection
        """
        Build vector index for video transcript chunks.

        Args:
            testimony_dir: Path to directory containing testimony JSON files
            use_speaker_detection: Whether to run speaker role detection (slower but more metadata)
            detect_agenda_items: Whether to detect agenda item boundaries in transcripts
            video_meeting_map: Optional dict mapping video_id to meeting_date (ISO format)
                               If not provided, meeting_date won't be set in metadata.

        Returns:
            ChromaDB collection with embedded transcript chunks
        """
        from civic._internal.meetings.transcript import TranscriptChunker

        testimony_path = Path(testimony_dir)
        if not testimony_path.exists():
            raise FileNotFoundError(f"Testimony directory not found: {testimony_path}")

        # Find all testimony files
        testimony_files = list(testimony_path.glob("testimony_*.json"))
        if not testimony_files:
            raise FileNotFoundError(f"No testimony files found in {testimony_path}")

        # Create collection (delete existing if present)
        try:
            self._client.delete_collection(self.transcripts_collection_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=self.transcripts_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "description": f"{self.jurisdiction_id} video transcripts for RAG",
                "jurisdiction_id": self.jurisdiction_id,
                "embedding_model": self.model_name,
                "embedding_dimension": self.embedding_dimension,
                "created_at": datetime.now().isoformat(),
                "source": str(testimony_path),
            }
        )

        # Process each testimony file
        chunker = TranscriptChunker(
            max_chunk_size=1500,
            min_chunk_size=200,
            chunk_overlap=1,
        )

        total_chunks = 0
        for testimony_file in testimony_files:
            # Load testimony data
            with open(testimony_file) as f:
                testimony_data = json.load(f)

            video_id = testimony_data.get("video_id", testimony_file.stem.replace("testimony_", ""))

            # Lookup meeting_date from map if provided
            meeting_date = None
            if video_meeting_map:
                meeting_date = video_meeting_map.get(video_id)

            # Generate chunks with speaker detection and agenda item detection
            chunks = chunker.chunk_file(
                testimony_file,
                detect_speaker_roles=use_speaker_detection,
                detect_agenda_items=detect_agenda_items,
                llm_provider=None,  # Use default
            )

            if not chunks:
                continue

            # Process in batches for efficiency
            batch_size = 50
            chunk_list = list(chunks)

            for i in range(0, len(chunk_list), batch_size):
                batch = chunk_list[i:i + batch_size]

                texts = [chunk.to_embedding_text() for chunk in batch]
                ids = [f"transcript-{video_id}-{chunk.chunk_index}" for chunk in batch]
                metadatas = [
                    self._transcript_chunk_to_metadata(chunk, video_id, meeting_date)
                    for chunk in batch
                ]

                embeddings = self.model.encode(texts, show_progress_bar=False)

                collection.add(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings.tolist(),
                    metadatas=metadatas,
                )

            total_chunks += len(chunk_list)

        return collection

    def _transcript_chunk_to_metadata(
        self, chunk, video_id: str, meeting_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert a TranscriptChunk to ChromaDB-compatible metadata.

        Args:
            chunk: TranscriptChunk object
            video_id: YouTube video ID
            meeting_date: Optional meeting date in ISO format (YYYY-MM-DD)

        Returns:
            Dict of metadata suitable for ChromaDB (flat types only)
        """
        metadata = {
            "source_type": "transcript",
            "video_id": video_id,
            "speaker": chunk.speaker,
            "start_ms": chunk.start_ms,
            "end_ms": chunk.end_ms,
            "start_timestamp": chunk.start_timestamp,
            "end_timestamp": chunk.end_timestamp,
            "chunk_index": chunk.chunk_index,
            "utterance_count": chunk.utterance_count,
        }

        # Add meeting date if provided (enables decision-transcript linking)
        if meeting_date:
            metadata["meeting_date"] = meeting_date

        # Add speaker role metadata if available
        chunk_meta = chunk.metadata or {}
        if chunk_meta.get("speaker_role"):
            metadata["speaker_role"] = str(chunk_meta["speaker_role"])
        if chunk_meta.get("speaker_name"):
            metadata["speaker_name"] = str(chunk_meta["speaker_name"])[:100]
        if chunk_meta.get("role_confidence"):
            metadata["role_confidence"] = float(chunk_meta["role_confidence"])

        # Public comment metadata
        if chunk_meta.get("is_public_comment"):
            metadata["is_public_comment"] = True
            if chunk_meta.get("public_comment_section_id") is not None:
                metadata["public_comment_section_id"] = int(chunk_meta["public_comment_section_id"])

        # Agenda item metadata (enables decision-transcript linking)
        if chunk_meta.get("agenda_item"):
            metadata["agenda_item"] = str(chunk_meta["agenda_item"])
        elif chunk_meta.get("agenda_items"):
            # If chunk spans multiple items, use first one as primary
            metadata["agenda_item"] = str(chunk_meta["agenda_items"][0])
            # Also store all items as comma-separated string for multi-item queries
            metadata["agenda_items"] = ",".join(str(x) for x in chunk_meta["agenda_items"])

        return metadata

    def search_transcripts(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[Dict] = None,
        speaker_role: Optional[str] = None,
        public_comment_only: bool = False,
    ) -> List[SearchResult]:
        """
        Search for similar transcript chunks.

        Args:
            query: Search query text
            top_k: Number of results to return
            where: Optional ChromaDB filter (e.g., {"video_id": "1E_H3H4zafw"})
            speaker_role: Filter by speaker role (e.g., "council", "staff", "public")
            public_comment_only: If True, only return public comment chunks

        Returns:
            List of SearchResult objects
        """
        try:
            collection = self._client.get_collection(self.transcripts_collection_name)
        except Exception:
            # Collection doesn't exist
            return []

        # Build filter
        effective_where = where.copy() if where else None

        filters = []
        if speaker_role:
            filters.append({"speaker_role": speaker_role})
        if public_comment_only:
            filters.append({"is_public_comment": True})

        if filters:
            if effective_where:
                filters.insert(0, effective_where)
            if len(filters) == 1:
                effective_where = filters[0]
            else:
                effective_where = {"$and": filters}

        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        # Search
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=effective_where,
        )

        return self._results_to_search_results(results)

    def has_transcripts(self) -> bool:
        """Check if transcripts collection exists and has documents."""
        try:
            collection = self._client.get_collection(self.transcripts_collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def build_issues_index(
        self,
        db_path: Union[str, Path] = None,
    ) -> Any:  # Returns chromadb.Collection
        """
        Build vector index for SeeClickFix issues from SQLite database.

        Args:
            db_path: Path to the civic_state SQLite database.
                     Defaults to get_state_db_path() which respects CIVIC_DATA_ROOT.

        Returns:
            ChromaDB collection with embedded issues
        """
        import sqlite3

        db_path = Path(db_path or get_state_db_path())
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        # Query issues from SQLite
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, jurisdiction_id, source, source_id, title, description,
                   issue_type, address, latitude, longitude, status,
                   created_at, updated_at
            FROM issues
            WHERE jurisdiction_id = ?
        """, (self.jurisdiction_id,))

        issues = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if not issues:
            raise ValueError(
                f"No issues found for jurisdiction {self.jurisdiction_id}"
            )

        # Create collection (delete existing if present)
        try:
            self._client.delete_collection(self.issues_collection_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=self.issues_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "description": f"{self.jurisdiction_id} SeeClickFix issues for RAG",
                "jurisdiction_id": self.jurisdiction_id,
                "embedding_model": self.model_name,
                "embedding_dimension": self.embedding_dimension,
                "created_at": datetime.now().isoformat(),
                "source": "seeclickfix.com API",
            }
        )

        # Process issues in batches for memory efficiency
        batch_size = 100
        for i in range(0, len(issues), batch_size):
            batch = issues[i:i + batch_size]

            texts = [self._issue_to_text(issue) for issue in batch]
            ids = [self._issue_to_id(issue) for issue in batch]
            metadatas = [self._issue_to_metadata(issue) for issue in batch]

            embeddings = self.model.encode(texts, show_progress_bar=False)

            collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
            )

        return collection

    def search_issues(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[Dict] = None,
        status: Optional[str] = None,
        issue_type: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search for similar issues using semantic search.

        Args:
            query: Search query text
            top_k: Number of results to return
            where: Optional ChromaDB filter
            status: Filter by issue status (open, acknowledged, closed)
            issue_type: Filter by issue type category

        Returns:
            List of SearchResult objects
        """
        try:
            collection = self._client.get_collection(self.issues_collection_name)
        except Exception:
            # Collection doesn't exist
            return []

        # Build filter
        effective_where = where.copy() if where else None

        filters = []
        if status:
            filters.append({"status": status})
        if issue_type:
            filters.append({"issue_type": issue_type})

        if filters:
            if effective_where:
                filters.insert(0, effective_where)
            if len(filters) == 1:
                effective_where = filters[0]
            else:
                effective_where = {"$and": filters}

        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        # Search
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=effective_where,
        )

        return self._results_to_search_results(results)

    def has_issues(self) -> bool:
        """Check if issues collection exists and has documents."""
        try:
            collection = self._client.get_collection(self.issues_collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def build_municipal_code_index(
        self,
        title_ids: Optional[List[str]] = None,
    ) -> Any:  # Returns chromadb.Collection
        """
        Build vector index for municipal code from Municode API.

        Fetches municipal code sections via the Municode API and indexes them
        in ChromaDB for semantic search.

        Args:
            title_ids: Optional list of title node IDs to fetch.
                      If None, fetches all titles.

        Returns:
            ChromaDB collection with embedded municipal code sections
        """
        from civic._internal.legal.corpus.municipal import MunicipalCodeCorpus

        corpus = MunicipalCodeCorpus(self.jurisdiction_id)

        try:
            # Fetch documents from Municode API
            documents = list(corpus.to_documents(title_ids))
        finally:
            corpus.close()

        if not documents:
            raise ValueError(
                f"No municipal code sections found for {self.jurisdiction_id}"
            )

        # Chunk long documents for embedding BEFORE collection creation
        # Municipal code sections can be very long (>20K chars), but we need
        # chunks under ~1500 chars for efficient embedding with nomic-embed-text-v1.5
        chunked_docs = []
        for doc in documents:
            text = doc["text"]
            chunks = _chunk_text(text, max_chars=1500, overlap=200)

            for chunk_idx, chunk in enumerate(chunks):
                chunk_id = doc["id"] if len(chunks) == 1 else f"{doc['id']}-chunk-{chunk_idx}"
                chunk_metadata = doc["metadata"].copy()
                chunk_metadata["chunk_index"] = chunk_idx
                chunk_metadata["total_chunks"] = len(chunks)
                chunk_metadata["parent_section"] = doc["id"]

                chunked_docs.append({
                    "id": chunk_id,
                    "text": chunk,
                    "metadata": chunk_metadata,
                })

        # Create collection (delete existing if present)
        try:
            self._client.delete_collection(self.municipal_code_collection_name)
        except Exception:
            pass

        # Get metadata from corpus
        corpus = MunicipalCodeCorpus(self.jurisdiction_id)
        try:
            meta = corpus.get_metadata()
        finally:
            corpus.close()

        collection = self._client.create_collection(
            name=self.municipal_code_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "description": f"{self.jurisdiction_id} municipal code for RAG",
                "jurisdiction_id": self.jurisdiction_id,
                "embedding_model": self.model_name,
                "embedding_dimension": self.embedding_dimension,
                "created_at": datetime.now().isoformat(),
                "source": "municode.com API",
                "publish_date": meta.get("publish_date", ""),
                "total_sections": len(documents),
                "total_chunks": len(chunked_docs),
            }
        )

        # Process in batches for memory efficiency
        batch_size = 50
        for i in range(0, len(chunked_docs), batch_size):
            batch = chunked_docs[i:i + batch_size]

            texts = [doc["text"] for doc in batch]
            ids = [doc["id"] for doc in batch]
            metadatas = [doc["metadata"] for doc in batch]

            embeddings = self.model.encode(texts, show_progress_bar=False)

            collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
            )

        return collection

    def search_municipal_code(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[Dict] = None,
        chapter: Optional[str] = None,
        title_number: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search municipal code using semantic search.

        Args:
            query: Search query text
            top_k: Number of results to return
            where: Optional ChromaDB filter
            chapter: Filter by chapter (e.g., "1.04")
            title_number: Filter by title number (e.g., "1")

        Returns:
            List of SearchResult objects
        """
        try:
            collection = self._client.get_collection(
                self.municipal_code_collection_name
            )
        except Exception:
            # Collection doesn't exist
            return []

        # Build filter
        effective_where = where.copy() if where else None

        filters = []
        if chapter:
            filters.append({"chapter": chapter})
        if title_number:
            filters.append({"title_number": title_number})

        if filters:
            if effective_where:
                filters.insert(0, effective_where)
            if len(filters) == 1:
                effective_where = filters[0]
            else:
                effective_where = {"$and": filters}

        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        # Search
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=effective_where,
        )

        return self._results_to_search_results(results)

    def has_municipal_code(self) -> bool:
        """Check if municipal code collection exists and has documents."""
        try:
            collection = self._client.get_collection(
                self.municipal_code_collection_name
            )
            return collection.count() > 0
        except Exception:
            return False

    def build_legislation_index(
        self,
        state: str = "california",
        topics: Optional[List[str]] = None,
        legislation_path: str = "data/legislation/state",
    ) -> Any:  # Returns chromadb.Collection
        """
        Build vector index for state legislation from JSON files.

        Loads state bills from legislation JSON files and indexes them
        in ChromaDB for semantic search. This enables queries like
        "affordable housing funding" to find relevant bills beyond keyword matching.

        Args:
            state: State identifier (e.g., "california")
            topics: Optional list of topics to index. If None, indexes all:
                   ["housing", "transportation", "environment", "education", "budget"]
            legislation_path: Path to legislation directory (contains state subdirs)

        Returns:
            ChromaDB collection with embedded legislation

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> collection = embedder.build_legislation_index()
            >>> # Collection contains ~26 state bills across 5 topics
        """
        if topics is None:
            topics = ["housing", "transportation", "environment", "education", "budget"]

        base_path = Path(legislation_path)
        documents = []
        total_bills = 0

        for topic in topics:
            file_path = base_path / state / f"{topic}.json"
            if not file_path.exists():
                continue

            with open(file_path, 'r') as f:
                data = json.load(f)

            state_legislation = data.get("state_legislation", {})
            for bill_id, bill_info in state_legislation.items():
                # Build searchable text combining bill info
                text_parts = [
                    f"Bill: {bill_info.get('bill', bill_id)}",
                    f"Summary: {bill_info.get('summary', '')}",
                    f"Leverage Point: {bill_info.get('leverage_point', '')}",
                ]
                if bill_info.get('keywords'):
                    text_parts.append(f"Keywords: {', '.join(bill_info['keywords'])}")

                text = "\n".join(text_parts)

                # Build metadata, filtering out None values (ChromaDB requires non-null)
                metadata = {
                    "bill_id": bill_id,
                    "bill_name": bill_info.get("bill") or "",
                    "topic": topic,
                    "status": bill_info.get("status") or "",
                    "enacted": bill_info.get("enacted") or "",
                    "local_deadline": bill_info.get("local_deadline") or "",
                    "local_implementation_required": bool(bill_info.get("local_implementation_required", False)),
                    "official_url": bill_info.get("official_url") or "",
                    "source_type": "state_legislation",
                    "state": state,
                }

                documents.append({
                    "id": bill_id,
                    "text": text,
                    "metadata": metadata,
                })
                total_bills += 1

        if not documents:
            raise ValueError(
                f"No legislation found in {legislation_path}/{state} for topics={topics}"
            )

        # Create collection (delete existing if present)
        try:
            self._client.delete_collection(self.legislation_collection_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=self.legislation_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "description": f"{self.jurisdiction_id} legislation for RAG",
                "jurisdiction_id": self.jurisdiction_id,
                "embedding_model": self.model_name,
                "embedding_dimension": self.embedding_dimension,
                "created_at": datetime.now().isoformat(),
                "source": "legislation JSON files",
                "state": state,
                "topics": ",".join(topics),
                "total_bills": total_bills,
            }
        )

        # Process in batches for memory efficiency
        batch_size = 50
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            texts = [doc["text"] for doc in batch]
            ids = [doc["id"] for doc in batch]
            metadatas = [doc["metadata"] for doc in batch]

            embeddings = self.model.encode(texts, show_progress_bar=False)

            collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
            )

        return collection

    def search_legislation(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[Dict] = None,
        topic: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search legislation using semantic search.

        Args:
            query: Search query text (e.g., "affordable housing funding")
            top_k: Number of results to return
            where: Optional ChromaDB filter
            topic: Filter by topic (e.g., "housing", "transportation")
            status: Filter by status (e.g., "Active")

        Returns:
            List of SearchResult objects

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> results = embedder.search_legislation("affordable housing streamlined approval")
            >>> for r in results:
            ...     print(f"{r.metadata['bill_id']}: {r.score:.3f}")
            ca-sb35: 0.782
            ca-ab2011: 0.756
        """
        try:
            collection = self._client.get_collection(
                self.legislation_collection_name
            )
        except Exception:
            # Collection doesn't exist
            return []

        # Build filter
        effective_where = where.copy() if where else None

        filters = []
        if topic:
            filters.append({"topic": topic})
        if status:
            filters.append({"status": status})

        if filters:
            if effective_where:
                filters.insert(0, effective_where)
            if len(filters) == 1:
                effective_where = filters[0]
            else:
                effective_where = {"$and": filters}

        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        # Search
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=effective_where,
        )

        return self._results_to_search_results(results)

    def has_legislation(self) -> bool:
        """Check if legislation collection exists and has documents."""
        try:
            collection = self._client.get_collection(
                self.legislation_collection_name
            )
            return collection.count() > 0
        except Exception:
            return False

    def build_federal_programs_index(
        self,
        topics: Optional[List[str]] = None,
        federal_programs_path: str = "data/funding/federal",
    ) -> Any:  # Returns chromadb.Collection
        """
        Build vector index for federal programs from JSON files.

        Loads federal grant programs from JSON files and indexes them
        in ChromaDB for semantic search. This enables queries like
        "housing assistance grants" to find relevant federal programs.

        Args:
            topics: Optional list of topics to index. If None, indexes all:
                   ["housing", "transportation", "environment", "education", "budget"]
            federal_programs_path: Path to federal programs JSON files

        Returns:
            ChromaDB collection with embedded federal programs

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> collection = embedder.build_federal_programs_index()
            >>> # Collection contains ~10 federal programs across 5 topics
        """
        if topics is None:
            topics = ["housing", "transportation", "environment", "education", "budget"]

        programs_path = Path(federal_programs_path)
        documents = []
        total_programs = 0

        for topic in topics:
            file_path = programs_path / f"{topic}.json"
            if not file_path.exists():
                continue

            with open(file_path, 'r') as f:
                data = json.load(f)

            programs = data.get("programs", {})
            for program_id, program_info in programs.items():
                # Build searchable text combining program info
                text_parts = [
                    f"Program: {program_info.get('program_name', program_id)}",
                    f"Agency: {program_info.get('administering_agency', '')}",
                    f"Description: {program_info.get('description', '')}",
                    f"Leverage Point: {program_info.get('leverage_point', '')}",
                ]

                # Include eligible activities if present
                eligible_activities = program_info.get('eligible_activities', [])
                if eligible_activities:
                    text_parts.append(f"Eligible Activities: {', '.join(str(a) for a in eligible_activities)}")

                # Include resident input opportunities if present
                resident_input = program_info.get('resident_input_opportunities', [])
                if resident_input:
                    text_parts.append(f"Resident Input Opportunities: {', '.join(str(r) for r in resident_input)}")

                if program_info.get('keywords'):
                    text_parts.append(f"Keywords: {', '.join(program_info['keywords'])}")

                text = "\n".join(text_parts)

                # Build metadata, filtering out None values (ChromaDB requires non-null)
                metadata = {
                    "program_id": program_id,
                    "program_name": program_info.get("program_name") or "",
                    "topic": topic,
                    "administering_agency": program_info.get("administering_agency") or "",
                    "local_compliance_required": bool(program_info.get("local_compliance_required", False)),
                    "annual_reporting": bool(program_info.get("annual_reporting", False)),
                    "official_url": program_info.get("official_url") or "",
                    "source_type": "federal_program",
                    "jurisdiction": "federal",
                }

                documents.append({
                    "id": f"federal-{program_id}",
                    "text": text,
                    "metadata": metadata,
                })
                total_programs += 1

        if not documents:
            raise ValueError(
                f"No federal programs found in {federal_programs_path} for topics={topics}"
            )

        # Create collection (delete existing if present)
        try:
            self._client.delete_collection(self.federal_programs_collection_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=self.federal_programs_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "description": f"{self.jurisdiction_id} federal programs for RAG",
                "jurisdiction_id": self.jurisdiction_id,
                "embedding_model": self.model_name,
                "embedding_dimension": self.embedding_dimension,
                "created_at": datetime.now().isoformat(),
                "source": "federal_programs JSON files",
                "topics": ",".join(topics),
                "total_programs": total_programs,
            }
        )

        # Process in batches for memory efficiency
        batch_size = 50
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            texts = [doc["text"] for doc in batch]
            ids = [doc["id"] for doc in batch]
            metadatas = [doc["metadata"] for doc in batch]

            embeddings = self.model.encode(texts, show_progress_bar=False)

            collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
            )

        return collection

    def search_federal_programs(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[Dict] = None,
        topic: Optional[str] = None,
        agency: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search federal programs using semantic search.

        Args:
            query: Search query text (e.g., "affordable housing grants")
            top_k: Number of results to return
            where: Optional ChromaDB filter
            topic: Filter by topic (e.g., "housing", "transportation")
            agency: Filter by administering agency (e.g., "HUD")

        Returns:
            List of SearchResult objects

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> results = embedder.search_federal_programs("community development housing")
            >>> for r in results:
            ...     print(f"{r.metadata['program_id']}: {r.score:.3f}")
            federal-cdbg: 0.812
            federal-home_investment_partnerships_program: 0.756
        """
        try:
            collection = self._client.get_collection(
                self.federal_programs_collection_name
            )
        except Exception:
            # Collection doesn't exist
            return []

        # Build filter
        effective_where = where.copy() if where else None

        filters = []
        if topic:
            filters.append({"topic": topic})
        if agency:
            filters.append({"administering_agency": agency})

        if filters:
            if effective_where:
                filters.insert(0, effective_where)
            if len(filters) == 1:
                effective_where = filters[0]
            else:
                effective_where = {"$and": filters}

        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        # Search
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=effective_where,
        )

        return self._results_to_search_results(results)

    def has_federal_programs(self) -> bool:
        """Check if federal programs collection exists and has documents."""
        try:
            collection = self._client.get_collection(
                self.federal_programs_collection_name
            )
            return collection.count() > 0
        except Exception:
            return False

    def build_county_programs_index(
        self,
        county_name: str = "marin",
        topic: str = "housing",
        county_programs_path: str = "data/funding/county",
    ) -> Any:  # Returns chromadb.Collection
        """
        Build vector index for county programs from JSON files.

        Loads county programs from JSON files and indexes them
        in ChromaDB for semantic search. This enables queries like
        "section 8 voucher" or "BMR homeownership" to find relevant
        county programs.

        Args:
            county_name: County name (e.g., "marin")
            topic: Program topic (e.g., "housing", "homelessness")
            county_programs_path: Base path to county programs JSON files

        Returns:
            ChromaDB collection with embedded county programs

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> collection = embedder.build_county_programs_index("marin", "housing")
            >>> # Collection contains Marin Housing Authority programs
        """
        # Determine filename based on topic
        filename = f"{topic}_programs.json"
        programs_path = Path(county_programs_path) / county_name / filename

        if not programs_path.exists():
            raise ValueError(
                f"County programs file not found: {programs_path}"
            )

        with open(programs_path, 'r') as f:
            data = json.load(f)

        documents = []
        programs = data.get("programs", {})

        for program_id, program_info in programs.items():
            # Build searchable text combining program info
            text_parts = [
                f"Program: {program_info.get('program_name', program_id)}",
                f"Agency: {program_info.get('administering_agency', '')}",
                f"Description: {program_info.get('description', '')}",
                f"Leverage Point: {program_info.get('leverage_point', '')}",
            ]

            # Include eligible activities if present
            eligible_activities = program_info.get('eligible_activities', [])
            if eligible_activities:
                text_parts.append(f"Eligible Activities: {', '.join(str(a) for a in eligible_activities)}")

            # Include resident input opportunities if present
            resident_input = program_info.get('resident_input_opportunities', [])
            if resident_input:
                text_parts.append(f"Resident Input Opportunities: {', '.join(str(r) for r in resident_input)}")

            if program_info.get('keywords'):
                text_parts.append(f"Keywords: {', '.join(program_info['keywords'])}")

            # Include eligibility requirements if present
            eligibility = program_info.get('eligibility_requirements', {})
            if eligibility:
                if isinstance(eligibility, dict):
                    eligibility_text = ", ".join(f"{k}: {v}" for k, v in eligibility.items() if not isinstance(v, dict))
                    if eligibility_text:
                        text_parts.append(f"Eligibility: {eligibility_text}")

            text = "\n".join(text_parts)

            # Build metadata, filtering out None values (ChromaDB requires non-null)
            metadata = {
                "program_id": program_id,
                "program_name": program_info.get("program_name") or "",
                "topic": topic,
                "county": county_name,
                "administering_agency": program_info.get("administering_agency") or "",
                "local_compliance_required": bool(program_info.get("local_compliance_required", False)),
                "annual_reporting": bool(program_info.get("annual_reporting", False)),
                "official_url": program_info.get("official_url") or "",
                "source_type": "county_program",
                "jurisdiction": f"county-{county_name}",
            }

            documents.append({
                "id": f"county-{county_name}-{topic}-{program_id}",
                "text": text,
                "metadata": metadata,
            })

        if not documents:
            raise ValueError(
                f"No county programs found in {programs_path}"
            )

        # Get or create collection (supports multiple topics)
        try:
            collection = self._client.get_collection(self.county_programs_collection_name)
        except Exception:
            collection = self._client.create_collection(
                name=self.county_programs_collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "description": f"{self.jurisdiction_id} county programs for RAG",
                    "jurisdiction_id": self.jurisdiction_id,
                    "embedding_model": self.model_name,
                    "embedding_dimension": self.embedding_dimension,
                    "created_at": datetime.now().isoformat(),
                    "source": "county_programs JSON files",
                }
            )

        # Process in batches for memory efficiency
        batch_size = 50
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            texts = [doc["text"] for doc in batch]
            ids = [doc["id"] for doc in batch]
            metadatas = [doc["metadata"] for doc in batch]

            embeddings = self.model.encode(texts, show_progress_bar=False)

            collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
            )

        return collection

    def build_county_housing_index(
        self,
        county_name: str = "marin",
        county_housing_path: str = "data/funding/county",
    ) -> Any:
        """
        DEPRECATED: Use build_county_programs_index(county_name, topic="housing") instead.

        Backward-compatible wrapper for building county housing program index.
        """
        return self.build_county_programs_index(
            county_name=county_name,
            topic="housing",
            county_programs_path=county_housing_path,
        )

    def search_county_programs(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[Dict] = None,
        topic: Optional[str] = None,
        county: Optional[str] = None,
        agency: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search county programs using semantic search.

        Args:
            query: Search query text (e.g., "section 8 rental assistance")
            top_k: Number of results to return
            where: Optional ChromaDB filter
            topic: Filter by topic (e.g., "housing", "homelessness")
            county: Filter by county (e.g., "marin")
            agency: Filter by administering agency (e.g., "Marin Housing Authority")

        Returns:
            List of SearchResult objects

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> results = embedder.search_county_programs("first time homebuyer", topic="housing")
            >>> for r in results:
            ...     print(f"{r.metadata['program_id']}: {r.score:.3f}")
            county-marin-housing-below_market_rate_homeownership: 0.812
            county-marin-housing-hcv_homeownership: 0.756
        """
        try:
            collection = self._client.get_collection(
                self.county_programs_collection_name
            )
        except Exception:
            # Collection doesn't exist
            return []

        # Build filter
        effective_where = where.copy() if where else None

        filters = []
        if topic:
            filters.append({"topic": topic})
        if county:
            filters.append({"county": county})
        if agency:
            filters.append({"administering_agency": agency})

        if filters:
            if effective_where:
                filters.insert(0, effective_where)
            if len(filters) == 1:
                effective_where = filters[0]
            else:
                effective_where = {"$and": filters}

        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        # Search
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=effective_where,
        )

        return self._results_to_search_results(results)

    def search_county_housing(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[Dict] = None,
        county: Optional[str] = None,
        agency: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        DEPRECATED: Use search_county_programs(query, topic="housing") instead.

        Backward-compatible wrapper for searching county housing programs.
        """
        return self.search_county_programs(
            query=query,
            top_k=top_k,
            where=where,
            topic="housing",
            county=county,
            agency=agency,
        )

    def has_county_programs(self) -> bool:
        """Check if county programs collection exists and has documents."""
        try:
            collection = self._client.get_collection(
                self.county_programs_collection_name
            )
            return collection.count() > 0
        except Exception:
            return False

    def has_county_housing(self) -> bool:
        """
        DEPRECATED: Use has_county_programs() instead.

        Backward-compatible wrapper for checking county housing programs.
        """
        return self.has_county_programs()

    def build_index(
        self,
        corpus_dir: Union[str, Path],
    ) -> Dict[str, Any]:
        """
        Build all vector indexes for the Merrydale corpus.

        Args:
            corpus_dir: Path to the corpus directory

        Returns:
            Dict with 'decisions' and 'chunks' collection references
        """
        corpus_path = Path(corpus_dir)

        result = {}

        # Build decisions index if any decisions file exists
        # Check jurisdiction-based naming first, then legacy
        decisions_candidates = [
            f"{self.jurisdiction_id}_decisions.json",
            "nov17_decisions.json",  # Legacy for backward compatibility
        ]
        for candidate in decisions_candidates:
            if (corpus_path / candidate).exists():
                result["decisions"] = self.build_decisions_index(corpus_dir)
                break

        # Build chunks index if any chunks file exists
        # Check jurisdiction-based naming first, then legacy
        chunks_candidates = [
            f"{self.jurisdiction_id}_chunks.json",
            "nov17_chunks.json",  # Legacy for backward compatibility
        ]
        for candidate in chunks_candidates:
            if (corpus_path / candidate).exists():
                result["chunks"] = self.build_chunks_index(corpus_dir)
                break

        return result

    def search_decisions(
        self,
        query: str,
        top_k: int = 5,
        where: Optional[Dict] = None,
        since_ts: Optional[int] = None,
        until_ts: Optional[int] = None,
    ) -> List[SearchResult]:
        """
        Search for similar decisions.

        Args:
            query: Search query text
            top_k: Number of results to return
            where: Optional ChromaDB filter (e.g., {"agenda_item": "6.a"})
            since_ts: Optional Unix timestamp for minimum meeting date
            until_ts: Optional Unix timestamp for maximum meeting date

        Returns:
            List of SearchResult objects
        """
        collection = self._client.get_collection(self.decisions_collection_name)

        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        # Build where clause with date range filtering
        # ChromaDB requires each operator in separate expressions combined with $and
        effective_where = where.copy() if where else None
        if since_ts is not None or until_ts is not None:
            date_filters = []
            if since_ts is not None:
                date_filters.append({"meeting_date_ts": {"$gte": since_ts}})
            if until_ts is not None:
                date_filters.append({"meeting_date_ts": {"$lte": until_ts}})

            if effective_where is None:
                if len(date_filters) == 1:
                    effective_where = date_filters[0]
                else:
                    effective_where = {"$and": date_filters}
            else:
                # Combine with existing filter using $and
                effective_where = {"$and": [effective_where] + date_filters}

        # Search
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=effective_where,
        )

        return self._results_to_search_results(results)

    def search_chunks(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[Dict] = None,
    ) -> List[SearchResult]:
        """
        Search for similar text chunks.

        Args:
            query: Search query text
            top_k: Number of results to return
            where: Optional ChromaDB filter (e.g., {"agenda_item": "6.a"})

        Returns:
            List of SearchResult objects
        """
        collection = self._client.get_collection(self.chunks_collection_name)

        # Generate query embedding
        query_embedding = self.model.encode([query])[0]

        # Search
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=where,
        )

        return self._results_to_search_results(results)

    def search(
        self,
        query: str,
        collection_name: str = "decisions",
        top_k: int = 5,
        where: Optional[Dict] = None,
    ) -> List[SearchResult]:
        """
        Search either decisions or chunks collection.

        Args:
            query: Search query text
            collection_name: "decisions" or "chunks"
            top_k: Number of results to return
            where: Optional ChromaDB filter

        Returns:
            List of SearchResult objects
        """
        if collection_name == "decisions":
            return self.search_decisions(query, top_k, where)
        elif collection_name == "chunks":
            return self.search_chunks(query, top_k, where)
        elif collection_name == "transcripts":
            return self.search_transcripts(query, top_k, where)
        else:
            raise ValueError(f"Unknown collection: {collection_name}")

    def search_hybrid_pdf_video(
        self,
        query: str,
        top_k: int = 10,
        agenda_item: Optional[str] = None,
        interleave: bool = True,
    ) -> List[SearchResult]:
        """
        Search both PDF chunks and video transcripts for complete context.

        Combines results from agenda packet/staff report chunks (PDF source)
        and meeting transcript chunks (video source) to provide a complete
        picture of both the official documentation and the actual discussion.

        Args:
            query: Search query text
            top_k: Total number of results to return (split between sources)
            agenda_item: Optional agenda item filter (e.g., "6.a") to get
                        related content from both sources
            interleave: If True (default), interleave PDF and transcript results
                       by score. If False, group by source type.

        Returns:
            List of SearchResult objects with 'source_type' in metadata
            ("pdf" for chunks, "transcript" for transcripts)

        Example:
            >>> embedder = CivicEmbeddings("city-san-rafael")
            >>> results = embedder.search_hybrid_pdf_video("homeless shelter funding")
            >>> for r in results:
            ...     if r.metadata.get("source_type") == "pdf":
            ...         print(f"PDF p{r.metadata['page_start']}: {r.text[:100]}")
            ...     else:
            ...         print(f"Video @{r.metadata['start_timestamp']}: {r.text[:100]}")
        """
        # Determine how many results to fetch from each source
        # Fetch more than needed to allow for filtering and interleaving
        per_source_k = max(top_k, 5)

        # Build filter for agenda item if specified
        where_filter = {"agenda_item": agenda_item} if agenda_item else None

        # Search PDF chunks
        pdf_results = []
        try:
            chunk_results = self.search_chunks(query, top_k=per_source_k, where=where_filter)
            for r in chunk_results:
                # Add source_type to metadata
                r.metadata["source_type"] = "pdf"
            pdf_results = chunk_results
        except Exception:
            # Chunks collection may not exist
            pass

        # Search video transcripts
        transcript_results = []
        try:
            if self.has_transcripts():
                trans_results = self.search_transcripts(
                    query, top_k=per_source_k, where=where_filter
                )
                for r in trans_results:
                    # source_type already set by build_transcripts_index
                    if "source_type" not in r.metadata:
                        r.metadata["source_type"] = "transcript"
                transcript_results = trans_results
        except Exception:
            # Transcripts collection may not exist
            pass

        # Combine results
        if interleave:
            # Interleave by score (highest first)
            all_results = pdf_results + transcript_results
            all_results.sort(key=lambda r: r.score, reverse=True)
        else:
            # Group by source: PDFs first, then transcripts
            all_results = pdf_results + transcript_results

        # Limit to requested top_k
        return all_results[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        stats = {
            "jurisdiction_id": self.jurisdiction_id,
            "model": self.model_name,
            "embedding_dimension": self.embedding_dimension,
            "persist_directory": self.persist_directory,
            "collections": {},
        }

        for collection_name in [
            self.decisions_collection_name,
            self.chunks_collection_name,
            self.transcripts_collection_name,
        ]:
            try:
                collection = self._client.get_collection(collection_name)
                stats["collections"][collection_name] = {
                    "count": collection.count(),
                    "metadata": collection.metadata,
                }
            except Exception:
                stats["collections"][collection_name] = None

        return stats

    def _decision_to_text(self, decision: Dict) -> str:
        """
        Convert a decision to text for embedding.

        Creates a rich text representation combining:
        - Title
        - Summary
        - Topics
        - Staff recommendation (if any)
        - Public input summary (if any)
        """
        parts = []

        # Title and summary
        if decision.get("title"):
            parts.append(f"Title: {decision['title']}")
        if decision.get("summary"):
            parts.append(f"Summary: {decision['summary']}")

        # Meeting context
        if decision.get("meeting_date"):
            parts.append(f"Meeting Date: {decision['meeting_date']}")
        if decision.get("agenda_item"):
            parts.append(f"Agenda Item: {decision['agenda_item']}")

        # Topics
        topics = decision.get("topics", [])
        if topics:
            parts.append(f"Topics: {', '.join(topics)}")

        # Outcome
        if decision.get("outcome"):
            parts.append(f"Outcome: {decision['outcome']}")

        # Vote
        vote = decision.get("vote", {})
        if vote.get("vote_count"):
            parts.append(f"Vote: {vote['vote_count']}")

        # Staff recommendation
        staff_rec = decision.get("staff_recommendation")
        if staff_rec:
            if staff_rec.get("department"):
                parts.append(f"Department: {staff_rec['department']}")
            if staff_rec.get("financial_impact"):
                parts.append(f"Financial Impact: {staff_rec['financial_impact']}")
            if staff_rec.get("recommendation"):
                # Truncate long recommendations
                rec = staff_rec['recommendation'][:500]
                parts.append(f"Recommendation: {rec}")

        # Public input
        public_input = decision.get("public_input")
        if public_input and public_input.get("speaker_count"):
            parts.append(f"Public Speakers: {public_input['speaker_count']}")

        # Legal instruments
        instruments = decision.get("legal_instruments", [])
        if instruments:
            instrument_types = [li.get("type", "") for li in instruments]
            parts.append(f"Legal Instruments: {', '.join(instrument_types)}")

        return " | ".join(parts)

    def _decision_to_metadata(self, decision: Dict) -> Dict[str, Any]:
        """Convert a decision to ChromaDB-compatible metadata."""
        meeting_date_str = str(decision.get("meeting_date", ""))
        metadata = {
            "decision_id": str(decision.get("decision_id", "")),
            "meeting_date": meeting_date_str,
            "agenda_item": str(decision.get("agenda_item", "")),
            "title": str(decision.get("title", ""))[:500],  # ChromaDB string limit
            "outcome": str(decision.get("outcome", "")),
        }

        # Add numeric timestamp for date range filtering (ChromaDB $gte/$lte require numeric types)
        if meeting_date_str:
            try:
                dt = datetime.fromisoformat(meeting_date_str)
                metadata["meeting_date_ts"] = int(dt.timestamp())
            except ValueError:
                pass  # Skip if date parsing fails

        # Topics as comma-separated string
        topics = decision.get("topics", [])
        if topics:
            metadata["topics"] = ",".join(topics)

        # Vote info
        vote = decision.get("vote", {})
        if vote.get("passed") is not None:
            metadata["vote_passed"] = vote["passed"]
        if vote.get("unanimous") is not None:
            metadata["vote_unanimous"] = vote["unanimous"]
        if vote.get("vote_count"):
            metadata["vote_count"] = str(vote["vote_count"])

        # Staff recommendation
        staff_rec = decision.get("staff_recommendation")
        if staff_rec:
            if staff_rec.get("department"):
                metadata["department"] = str(staff_rec["department"])
            if staff_rec.get("financial_impact"):
                metadata["financial_impact"] = str(staff_rec["financial_impact"])

        # Public input
        public_input = decision.get("public_input")
        if public_input and public_input.get("speaker_count"):
            metadata["speaker_count"] = int(public_input["speaker_count"])

        return metadata

    def _chunk_to_metadata(self, chunk: Dict) -> Dict[str, Any]:
        """Convert a chunk to ChromaDB-compatible metadata."""
        return {
            "agenda_item": str(chunk.get("agenda_item", "")),
            "agenda_title": str(chunk.get("agenda_title", ""))[:200],
            "page_start": int(chunk.get("page_start", 0)),
            "page_end": int(chunk.get("page_end", 0)),
            "chunk_index": int(chunk.get("chunk_index", 0)),
            "total_chunks": int(chunk.get("total_chunks", 0)),
        }

    def _issue_to_id(self, issue: Dict) -> str:
        """
        Generate ChromaDB document ID for an issue.

        Format: {jurisdiction_id}-scf-{source_id}
        Example: city-san-rafael-scf-20575290
        """
        source_id = issue.get("source_id", issue.get("id", "unknown"))
        # Extract numeric ID if it's in format "scf-12345"
        if isinstance(source_id, str) and source_id.startswith("scf-"):
            source_id = source_id[4:]
        return f"{self.jurisdiction_id}-scf-{source_id}"

    def _issue_to_text(self, issue: Dict) -> str:
        """
        Convert an issue to text for embedding.

        Creates a searchable text representation combining:
        - Issue type (category)
        - Title
        - Description
        - Location (address)
        - Status
        """
        parts = []

        if issue.get("issue_type"):
            parts.append(f"Issue Type: {issue['issue_type']}")
        if issue.get("title"):
            parts.append(f"Title: {issue['title']}")
        if issue.get("description"):
            # Truncate long descriptions
            desc = issue["description"][:1000]
            parts.append(f"Description: {desc}")
        if issue.get("address"):
            parts.append(f"Location: {issue['address']}")
        if issue.get("status"):
            parts.append(f"Status: {issue['status']}")

        return " | ".join(parts)

    def _issue_to_metadata(self, issue: Dict) -> Dict[str, Any]:
        """Convert an issue to ChromaDB-compatible metadata."""
        source_id = issue.get("source_id", issue.get("id", ""))
        # Extract numeric ID if it's in format "scf-12345"
        if isinstance(source_id, str) and source_id.startswith("scf-"):
            source_id = source_id[4:]

        metadata = {
            "issue_id": f"{self.jurisdiction_id}-scf-{source_id}",
            "source_id": str(source_id),
            "issue_type": str(issue.get("issue_type", ""))[:200],
            "address": str(issue.get("address", ""))[:200],
            "status": str(issue.get("status", "open")),
        }

        # Add coordinates for geo filtering
        if issue.get("latitude") is not None:
            metadata["latitude"] = float(issue["latitude"])
        if issue.get("longitude") is not None:
            metadata["longitude"] = float(issue["longitude"])

        # Add dates as strings (ChromaDB doesn't support datetime)
        if issue.get("created_at"):
            created_at = issue["created_at"]
            if hasattr(created_at, "isoformat"):
                created_at = created_at.isoformat()
            metadata["created_at"] = str(created_at)[:10]  # Just date part
        if issue.get("updated_at"):
            updated_at = issue["updated_at"]
            if hasattr(updated_at, "isoformat"):
                updated_at = updated_at.isoformat()
            metadata["updated_at"] = str(updated_at)[:10]  # Just date part

        return metadata

    def _results_to_search_results(self, results: Dict) -> List[SearchResult]:
        """Convert ChromaDB results to SearchResult objects."""
        search_results = []

        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # ChromaDB returns cosine distance, convert to similarity
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1 - distance  # cosine similarity

                search_results.append(SearchResult(
                    document_id=doc_id,
                    text=results["documents"][0][i] if results["documents"] else "",
                    score=score,
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                ))

        return search_results


def build_civic_index(
    jurisdiction_id: str,
    corpus_dir: Union[str, Path],
    persist_directory: Optional[str] = None,
    model_name: str = CivicEmbeddings.DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Convenience function to build vector index for a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")
        corpus_dir: Path to corpus directory
        persist_directory: Path for ChromaDB storage (optional, defaults to
                          data/pilot/vectors/{jurisdiction_id}/)
        model_name: SentenceTransformer model name

    Returns:
        Dict with collection statistics
    """
    embedder = CivicEmbeddings(
        jurisdiction_id=jurisdiction_id,
        model_name=model_name,
        persist_directory=persist_directory,
    )

    collections = embedder.build_index(corpus_dir)

    return {
        "jurisdiction_id": jurisdiction_id,
        "collections": list(collections.keys()),
        "stats": embedder.get_stats(),
    }


def search_civic(
    jurisdiction_id: str,
    query: str,
    collection: str = "decisions",
    top_k: int = 5,
    persist_directory: Optional[str] = None,
) -> List[Dict]:
    """
    Convenience function to search a jurisdiction's corpus.

    Args:
        jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")
        query: Search query
        collection: "decisions" or "chunks"
        top_k: Number of results
        persist_directory: Path to ChromaDB storage (optional)

    Returns:
        List of search results as dicts
    """
    embedder = CivicEmbeddings(
        jurisdiction_id=jurisdiction_id,
        persist_directory=persist_directory,
    )
    results = embedder.search(query, collection, top_k)

    return [
        {
            "document_id": r.document_id,
            "text": r.text,
            "score": r.score,
            "metadata": r.metadata,
        }
        for r in results
    ]


# ============================================================================
# Backward Compatibility Aliases
# ============================================================================
# These aliases maintain compatibility with code using the old Merrydale names.
# They can be removed after all consumers have migrated to CivicEmbeddings.

class MerrydaleEmbeddings(CivicEmbeddings):
    """
    DEPRECATED: Use CivicEmbeddings instead.

    This class is a backward-compatible alias for CivicEmbeddings with
    Merrydale-specific defaults. It will be removed in a future version.

    Migration:
        # Old code
        embedder = MerrydaleEmbeddings()

        # New code
        embedder = CivicEmbeddings("city-san-rafael")
    """

    def __init__(
        self,
        model_name: str = CivicEmbeddings.DEFAULT_MODEL,
        persist_directory: str = "data/pilot/vectors/city-san-rafael",
        collection_suffix: str = "",
    ):
        """
        Initialize with Merrydale-compatible defaults.

        Note: persist_directory defaults to the new standard path.
        """
        import warnings
        warnings.warn(
            "MerrydaleEmbeddings is deprecated. Use CivicEmbeddings('city-san-rafael') instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(
            jurisdiction_id="city-san-rafael",
            model_name=model_name,
            persist_directory=persist_directory,
            collection_suffix=collection_suffix,
        )


def build_merrydale_index(
    corpus_dir: Union[str, Path],
    persist_directory: str = "data/pilot/vectors/city-san-rafael",
    model_name: str = CivicEmbeddings.DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    DEPRECATED: Use build_civic_index instead.

    Convenience function to build Merrydale vector index.
    """
    import warnings
    warnings.warn(
        "build_merrydale_index is deprecated. Use build_civic_index('city-san-rafael', ...) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return build_civic_index(
        jurisdiction_id="city-san-rafael",
        corpus_dir=corpus_dir,
        persist_directory=persist_directory,
        model_name=model_name,
    )


def search_merrydale(
    query: str,
    collection: str = "decisions",
    top_k: int = 5,
    persist_directory: str = "data/pilot/vectors/city-san-rafael",
) -> List[Dict]:
    """
    DEPRECATED: Use search_civic instead.

    Convenience function to search the Merrydale corpus.
    """
    import warnings
    warnings.warn(
        "search_merrydale is deprecated. Use search_civic('city-san-rafael', ...) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return search_civic(
        jurisdiction_id="city-san-rafael",
        query=query,
        collection=collection,
        top_k=top_k,
        persist_directory=persist_directory,
    )
