"""
UnifiedSearch: Cross-corpus semantic search for civic data.

This module provides unified search across all 7 corpus types:
- decisions: City council decisions/agenda items
- pdf: PDF chunks from agenda packets/staff reports
- transcript: Video transcript chunks from meeting recordings
- issue: SeeClickFix community issue reports
- municipal_code: Municipal code sections
- legislation: State legislation (laws/bills)
- programs: Federal and county funding/service programs

Results are returned as UnifiedSearchResult objects, ranked by relevance.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

from civicos._internal.meetings.embeddings import CivicEmbeddings
from civicos.history import UnifiedSearchResult
from civicos.storage.corpus_types import UNIFIED_CORPUS_TYPES

if TYPE_CHECKING:
    from civicos.storage.vector import VectorBackend

logger = logging.getLogger(__name__)


# Valid corpus types - imported from centralized registry for consistency
CORPUS_TYPES = UNIFIED_CORPUS_TYPES


@dataclass
class CorpusInfo:
    """Information about an available corpus."""
    name: str
    document_count: int
    available: bool


class UnifiedSearch:
    """
    Unified search interface across multiple civic data corpora.

    Provides semantic search that queries decisions, PDF chunks, transcripts,
    issues, and municipal code, returning results in a unified format.

    Example:
        >>> search = UnifiedSearch("city-san-rafael")
        >>> results = search.search_all("homeless shelter funding", top_k=10)
        >>> for r in results:
        ...     print(f"[{r.source_type}] {r.score:.2f}: {r.text[:50]}")

        >>> # Search specific corpora only
        >>> results = search.search_all(
        ...     "parking",
        ...     corpus_types=["decision", "issue"],
        ...     top_k=5
        ... )

        >>> # Check available corpora
        >>> corpora = search.get_available_corpora()
        >>> for name, info in corpora.items():
        ...     print(f"{name}: {info.document_count} documents")
    """

    def __init__(
        self,
        jurisdiction_id: str,
        persist_directory: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize UnifiedSearch for a jurisdiction.

        Uses pgvector (production) when DATABASE_URL is set, otherwise
        falls back to ChromaDB via CivicEmbeddings (local development).

        Args:
            jurisdiction_id: The jurisdiction ID (e.g., "city-san-rafael")
            persist_directory: Optional path to ChromaDB persistence directory.
                             If None, uses default from CivicEmbeddings.
        """
        self.jurisdiction_id = jurisdiction_id

        # Try pgvector first (production path)
        self._vector_backend: Optional["VectorBackend"] = None
        try:
            from civicos.storage import get_vector_backend
            self._vector_backend = get_vector_backend()
            if self._vector_backend is not None:
                logger.debug(f"UnifiedSearch: using pgvector for {jurisdiction_id}")
        except Exception:
            pass

        # ChromaDB fallback (local development)
        persist_dir = str(persist_directory) if persist_directory else None
        self._embeddings = CivicEmbeddings(
            jurisdiction_id=jurisdiction_id,
            persist_directory=persist_dir,
        )
        # Cache corpus availability on first check
        self._corpora_cache: Optional[Dict[str, CorpusInfo]] = None

    def _search_with_pgvector(
        self,
        query: str,
        corpus_type: str,
        source_type: str,
        top_k: int = 10,
    ) -> Optional[List[UnifiedSearchResult]]:
        """
        Search using pgvector backend if available.

        Args:
            query: Search query
            corpus_type: The corpus type for pgvector (e.g., "chunks", "issues")
            source_type: The source type for UnifiedSearchResult (e.g., "pdf", "issue")
            top_k: Maximum results

        Returns:
            List of results if pgvector search succeeded, None to fall back to ChromaDB
        """
        if self._vector_backend is None:
            return None

        try:
            results = self._vector_backend.search(
                query, self.jurisdiction_id, corpus_type, top_k=top_k
            )
            if results:
                return [
                    UnifiedSearchResult.from_vector_result(r, source_type)
                    for r in results
                ]
            # Empty results - still successful, don't fall back
            return []
        except Exception as e:
            logger.debug(f"pgvector search failed for {corpus_type}: {e}")
            return None

    def search_all(
        self,
        query: str,
        top_k: int = 20,
        corpus_types: Optional[List[str]] = None,
    ) -> List[UnifiedSearchResult]:
        """
        Search across all (or specified) corpora for relevant content.

        Queries each available corpus, merges results by relevance score,
        and returns unified results.

        Args:
            query: Search query text
            top_k: Maximum number of results to return
            corpus_types: Optional list of corpus types to search.
                         Valid types: "decision", "pdf", "transcript",
                         "issue", "municipal_code", "legislation".
                         If None, searches all available corpora.

        Returns:
            List of UnifiedSearchResult objects, sorted by score (highest first)

        Raises:
            ValueError: If an invalid corpus type is specified
        """
        # Validate corpus_types
        if corpus_types is not None:
            invalid = set(corpus_types) - CORPUS_TYPES
            if invalid:
                raise ValueError(
                    f"Invalid corpus types: {invalid}. "
                    f"Valid types: {sorted(CORPUS_TYPES)}"
                )
            search_corpora = set(corpus_types)
        else:
            search_corpora = CORPUS_TYPES

        # Get available corpora
        available = self.get_available_corpora()

        # Calculate per-corpus top_k (fetch more than needed for merging)
        # Increase multiplier when searching fewer corpora
        n_corpora = sum(
            1 for ct in search_corpora
            if ct in available and available[ct].available
        )
        if n_corpora == 0:
            return []

        per_corpus_k = max(top_k, (top_k // n_corpora) + 5)

        # Collect results from each corpus
        all_results: List[UnifiedSearchResult] = []

        # Search decisions (pgvector first, ChromaDB fallback)
        if "decision" in search_corpora and available.get("decision", CorpusInfo("decision", 0, False)).available:
            pgvector_results = self._search_with_pgvector(query, "decisions", "decision", per_corpus_k)
            if pgvector_results is not None:
                all_results.extend(pgvector_results)
            else:
                results = self._embeddings.search_decisions(query, top_k=per_corpus_k)
                for r in results:
                    all_results.append(
                        UnifiedSearchResult.from_embeddings_result(r, "decision")
                    )

        # Search PDF chunks (pgvector first, ChromaDB fallback)
        if "pdf" in search_corpora and available.get("pdf", CorpusInfo("pdf", 0, False)).available:
            pgvector_results = self._search_with_pgvector(query, "chunks", "pdf", per_corpus_k)
            if pgvector_results is not None:
                all_results.extend(pgvector_results)
            else:
                results = self._embeddings.search_chunks(query, top_k=per_corpus_k)
                for r in results:
                    all_results.append(
                        UnifiedSearchResult.from_embeddings_result(r, "pdf")
                    )

        # Search transcripts (pgvector first, ChromaDB fallback)
        if "transcript" in search_corpora and available.get("transcript", CorpusInfo("transcript", 0, False)).available:
            pgvector_results = self._search_with_pgvector(query, "transcripts", "transcript", per_corpus_k)
            if pgvector_results is not None:
                all_results.extend(pgvector_results)
            else:
                results = self._embeddings.search_transcripts(query, top_k=per_corpus_k)
                for r in results:
                    all_results.append(
                        UnifiedSearchResult.from_embeddings_result(r, "transcript")
                    )

        # Search issues (pgvector first, ChromaDB fallback)
        if "issue" in search_corpora and available.get("issue", CorpusInfo("issue", 0, False)).available:
            pgvector_results = self._search_with_pgvector(query, "issues", "issue", per_corpus_k)
            if pgvector_results is not None:
                all_results.extend(pgvector_results)
            else:
                results = self._embeddings.search_issues(query, top_k=per_corpus_k)
                for r in results:
                    all_results.append(
                        UnifiedSearchResult.from_embeddings_result(r, "issue")
                    )

        # Search municipal code (pgvector first, ChromaDB fallback)
        if "municipal_code" in search_corpora and available.get("municipal_code", CorpusInfo("municipal_code", 0, False)).available:
            pgvector_results = self._search_with_pgvector(query, "municipal_code", "municipal_code", per_corpus_k)
            if pgvector_results is not None:
                all_results.extend(pgvector_results)
            else:
                results = self._embeddings.search_municipal_code(query, top_k=per_corpus_k)
                for r in results:
                    all_results.append(
                        UnifiedSearchResult.from_embeddings_result(r, "municipal_code")
                    )

        # Search legislation (state bills only)
        if "legislation" in search_corpora:
            leg_available = available.get("legislation", CorpusInfo("legislation", 0, False)).available
            if leg_available:
                if self._embeddings.has_legislation():
                    results = self._embeddings.search_legislation(query, top_k=per_corpus_k)
                    for r in results:
                        actual_source_type = r.metadata.get("source_type", "state_legislation")
                        all_results.append(
                            UnifiedSearchResult.from_embeddings_result(r, actual_source_type)
                        )

        # Search programs (federal + county funding/service programs)
        if "programs" in search_corpora:
            prog_available = available.get("programs", CorpusInfo("programs", 0, False)).available
            if prog_available:
                # Search federal programs
                if self._embeddings.has_federal_programs():
                    results = self._embeddings.search_federal_programs(query, top_k=per_corpus_k)
                    for r in results:
                        actual_source_type = r.metadata.get("source_type", "federal_program")
                        all_results.append(
                            UnifiedSearchResult.from_embeddings_result(r, actual_source_type)
                        )

                # Search county programs
                if self._embeddings.has_county_programs():
                    results = self._embeddings.search_county_programs(query, top_k=per_corpus_k)
                    for r in results:
                        actual_source_type = r.metadata.get("source_type", "county_program")
                        all_results.append(
                            UnifiedSearchResult.from_embeddings_result(r, actual_source_type)
                        )

        # Sort by score (highest first) and limit
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:top_k]

    def search_corpus(
        self,
        corpus_type: str,
        query: str,
        top_k: int = 10,
        **filters,
    ) -> List[UnifiedSearchResult]:
        """
        Search a specific corpus with optional filters.

        Args:
            corpus_type: The corpus to search ("decision", "pdf", "transcript",
                        "issue", "municipal_code", "legislation", "programs")
            query: Search query text
            top_k: Maximum number of results
            **filters: Corpus-specific filters:
                - decisions: since_ts, until_ts, where
                - transcripts: speaker_role, public_comment_only, where
                - issues: status, issue_type, where
                - legislation: topic, where
                - programs: topic, county, where
                - pdf/municipal_code: where

        Returns:
            List of UnifiedSearchResult objects

        Raises:
            ValueError: If corpus_type is invalid or corpus is unavailable
        """
        if corpus_type not in CORPUS_TYPES:
            raise ValueError(
                f"Invalid corpus type: {corpus_type}. "
                f"Valid types: {sorted(CORPUS_TYPES)}"
            )

        available = self.get_available_corpora()
        if corpus_type not in available or not available[corpus_type].available:
            raise ValueError(
                f"Corpus '{corpus_type}' is not available for {self.jurisdiction_id}"
            )

        results: List[UnifiedSearchResult] = []

        # For unfiltered queries, try pgvector first
        # ChromaDB filters (where, since_ts, etc.) not supported by pgvector
        has_filters = any(filters.get(k) for k in filters)

        if corpus_type == "decision":
            if not has_filters:
                pgvector_results = self._search_with_pgvector(query, "decisions", "decision", top_k)
                if pgvector_results is not None:
                    return pgvector_results
            raw = self._embeddings.search_decisions(
                query,
                top_k=top_k,
                where=filters.get("where"),
                since_ts=filters.get("since_ts"),
                until_ts=filters.get("until_ts"),
            )
            for r in raw:
                results.append(
                    UnifiedSearchResult.from_embeddings_result(r, "decision")
                )

        elif corpus_type == "pdf":
            if not has_filters:
                pgvector_results = self._search_with_pgvector(query, "chunks", "pdf", top_k)
                if pgvector_results is not None:
                    return pgvector_results
            raw = self._embeddings.search_chunks(
                query,
                top_k=top_k,
                where=filters.get("where"),
            )
            for r in raw:
                results.append(
                    UnifiedSearchResult.from_embeddings_result(r, "pdf")
                )

        elif corpus_type == "transcript":
            if not has_filters:
                pgvector_results = self._search_with_pgvector(query, "transcripts", "transcript", top_k)
                if pgvector_results is not None:
                    return pgvector_results
            raw = self._embeddings.search_transcripts(
                query,
                top_k=top_k,
                where=filters.get("where"),
                speaker_role=filters.get("speaker_role"),
                public_comment_only=filters.get("public_comment_only", False),
            )
            for r in raw:
                results.append(
                    UnifiedSearchResult.from_embeddings_result(r, "transcript")
                )

        elif corpus_type == "issue":
            if not has_filters:
                pgvector_results = self._search_with_pgvector(query, "issues", "issue", top_k)
                if pgvector_results is not None:
                    return pgvector_results
            raw = self._embeddings.search_issues(
                query,
                top_k=top_k,
                where=filters.get("where"),
                status=filters.get("status"),
                issue_type=filters.get("issue_type"),
            )
            for r in raw:
                results.append(
                    UnifiedSearchResult.from_embeddings_result(r, "issue")
                )

        elif corpus_type == "municipal_code":
            if not has_filters:
                pgvector_results = self._search_with_pgvector(query, "municipal_code", "municipal_code", top_k)
                if pgvector_results is not None:
                    return pgvector_results
            raw = self._embeddings.search_municipal_code(
                query,
                top_k=top_k,
                where=filters.get("where"),
            )
            for r in raw:
                results.append(
                    UnifiedSearchResult.from_embeddings_result(r, "municipal_code")
                )

        elif corpus_type == "legislation":
            # Search state legislation only
            if self._embeddings.has_legislation():
                raw = self._embeddings.search_legislation(
                    query,
                    top_k=top_k,
                    where=filters.get("where"),
                    topic=filters.get("topic"),
                )
                for r in raw:
                    actual_source_type = r.metadata.get("source_type", "state_legislation")
                    results.append(
                        UnifiedSearchResult.from_embeddings_result(r, actual_source_type)
                    )

        elif corpus_type == "programs":
            # Search federal programs and county programs
            if self._embeddings.has_federal_programs():
                raw = self._embeddings.search_federal_programs(
                    query,
                    top_k=top_k,
                    where=filters.get("where"),
                    topic=filters.get("topic"),
                )
                for r in raw:
                    actual_source_type = r.metadata.get("source_type", "federal_program")
                    results.append(
                        UnifiedSearchResult.from_embeddings_result(r, actual_source_type)
                    )

            if self._embeddings.has_county_programs():
                raw = self._embeddings.search_county_programs(
                    query,
                    top_k=top_k,
                    where=filters.get("where"),
                    topic=filters.get("topic"),
                    county=filters.get("county"),
                )
                for r in raw:
                    actual_source_type = r.metadata.get("source_type", "county_program")
                    results.append(
                        UnifiedSearchResult.from_embeddings_result(r, actual_source_type)
                    )

            # Sort combined results by score and limit
            results.sort(key=lambda r: r.score, reverse=True)
            results = results[:top_k]

        return results

    def get_available_corpora(self, refresh: bool = False) -> Dict[str, CorpusInfo]:
        """
        Get information about available corpora for this jurisdiction.

        Returns a dictionary mapping corpus type to CorpusInfo with
        document count and availability.

        Args:
            refresh: If True, bypass cache and re-check corpus availability

        Returns:
            Dict mapping corpus type to CorpusInfo

        Example:
            >>> corpora = search.get_available_corpora()
            >>> corpora["decision"].available  # True if decisions indexed
            >>> corpora["decision"].document_count  # Number of decisions
        """
        if self._corpora_cache is not None and not refresh:
            return self._corpora_cache

        corpora: Dict[str, CorpusInfo] = {}

        # For each corpus, try pgvector first, fall back to ChromaDB
        # pgvector corpus types: decisions, chunks, transcripts, issues, municipal_code, meetings

        # Check decisions
        count = self._get_pgvector_count("decisions")
        if count == 0:
            count = self._get_collection_count(self._embeddings.decisions_collection_name)
        corpora["decision"] = CorpusInfo("decision", count, count > 0)

        # Check PDF chunks
        count = self._get_pgvector_count("chunks")
        if count == 0:
            count = self._get_collection_count(self._embeddings.chunks_collection_name)
        corpora["pdf"] = CorpusInfo("pdf", count, count > 0)

        # Check transcripts
        count = self._get_pgvector_count("transcripts")
        if count == 0:
            count = self._get_collection_count(self._embeddings.transcripts_collection_name)
        corpora["transcript"] = CorpusInfo("transcript", count, count > 0)

        # Check issues
        count = self._get_pgvector_count("issues")
        if count == 0:
            count = self._get_collection_count(self._embeddings.issues_collection_name)
        corpora["issue"] = CorpusInfo("issue", count, count > 0)

        # Check municipal code
        count = self._get_pgvector_count("municipal_code")
        if count == 0:
            count = self._get_collection_count(self._embeddings.municipal_code_collection_name)
        corpora["municipal_code"] = CorpusInfo("municipal_code", count, count > 0)

        # Check legislation (state bills only) - ChromaDB only for now
        legislation_count = self._get_collection_count(
            self._embeddings.legislation_collection_name
        )
        corpora["legislation"] = CorpusInfo("legislation", legislation_count, legislation_count > 0)

        # Check programs (federal + county programs combined) - ChromaDB only for now
        federal_count = self._get_collection_count(
            self._embeddings.federal_programs_collection_name
        )
        county_programs_count = self._get_collection_count(
            self._embeddings.county_programs_collection_name
        )
        total_programs = federal_count + county_programs_count
        corpora["programs"] = CorpusInfo("programs", total_programs, total_programs > 0)

        self._corpora_cache = corpora
        return corpora

    def _get_collection_count(self, collection_name: str) -> int:
        """Get document count for a ChromaDB collection, returning 0 if it doesn't exist."""
        try:
            collection = self._embeddings._client.get_collection(collection_name)
            return collection.count()
        except Exception:
            return 0

    def _get_pgvector_count(self, corpus_type: str) -> int:
        """Get document count for a pgvector corpus, returning 0 if unavailable."""
        if self._vector_backend is None:
            return 0
        try:
            return self._vector_backend.count(self.jurisdiction_id, corpus_type)
        except Exception:
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about all corpora for this jurisdiction.

        Returns:
            Dict with jurisdiction_id, model info, and per-corpus stats
        """
        corpora = self.get_available_corpora(refresh=True)

        return {
            "jurisdiction_id": self.jurisdiction_id,
            "model": self._embeddings.model_name,
            "embedding_dimension": self._embeddings.embedding_dimension,
            "corpora": {
                name: {
                    "available": info.available,
                    "document_count": info.document_count,
                }
                for name, info in corpora.items()
            },
            "total_documents": sum(
                info.document_count for info in corpora.values()
            ),
            "available_corpora": [
                name for name, info in corpora.items() if info.available
            ],
        }
