"""
Civic Diagnostics - Schema-aware data status and pipeline health utilities.

This module provides schema-aware utilities for:
- Data status reporting (corpus counts, gaps, coverage)
- Vector index coverage analysis
- Pipeline health monitoring

It encapsulates schema knowledge to prevent ad-hoc SQL queries from using
incorrect column names (e.g., "meeting_date" vs "meeting_datetime").

Usage:
    from civicos.diagnostics import DataStatus, VectorCoverage

    # Get data status for a jurisdiction
    status = DataStatus(storage, vectors, "city-san-rafael")
    print(status.summary())
    print(status.gaps())

    # Get vector coverage
    coverage = VectorCoverage(storage, vectors, "city-san-rafael")
    print(coverage.by_corpus())
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .storage.backend import StorageBackend, StorageStats
from .storage.corpus_types import (
    CORPUS_REGISTRY,
    CorpusConfig,
    CorpusType,
    get_city_corpus_types,
    get_vector_indexed_types,
)
from .storage.vector import VectorBackend, VectorStats


# ============================================================================
# Schema Reference (authoritative column names)
# ============================================================================
# This documents the correct column names to prevent schema confusion.
# Always reference CORPUS_REGISTRY for programmatic access to schema info.

SCHEMA_REFERENCE = {
    "meetings": {
        "id_col": "id",
        "date_col": "meeting_datetime",  # NOT "meeting_date"
        "type_col": "meeting_type",
        "temporal": ["valid_from", "valid_to", "deleted_at"],
    },
    "decisions": {
        "id_col": "id",
        "date_col": "meeting_date",  # Note: decisions uses "meeting_date" (text)
        "link_col": "meeting_id",  # Links to meetings.id (optional)
        "temporal": ["valid_from", "valid_to", "deleted_at"],
    },
    "chunks": {
        "id_col": "id",
        "link_col": "meeting_id",  # NOT "content_id"
        "temporal": ["valid_from", "valid_to", "deleted_at"],
    },
    "transcripts": {
        "id_col": "id",
        "link_col": "video_id",  # Links to video URL
        "temporal": ["valid_from", "valid_to", "deleted_at"],
    },
    "issues": {
        "id_col": "id",
        "date_col": "created_at",
        "temporal": ["valid_from", "valid_to", "deleted_at"],
    },
    # Note: Vector embeddings are in "vector_embeddings" table (pgvector)
    # or ChromaDB collections (local dev). NOT "embeddings" table.
    "vector_embeddings": {
        "id_col": "id",
        "link_col": "content_id",  # Generic link to source document
        "corpus_col": "corpus_type",
    },
}


@dataclass
class CorpusCount:
    """Count information for a single corpus type."""

    corpus_type: str
    display_name: str
    storage_count: int
    vector_count: int
    gap: int  # storage_count - vector_count
    coverage_percent: Optional[float]
    has_sql_source: bool
    has_vector_index: bool
    last_indexed: Optional[datetime] = None


@dataclass
class DataStatusReport:
    """Complete data status report for a jurisdiction."""

    jurisdiction_id: str
    timestamp: datetime
    corpus_counts: Dict[str, CorpusCount]
    total_storage_docs: int
    total_vector_docs: int
    total_gap: int
    overall_coverage_percent: Optional[float]
    storage_stats: Optional[StorageStats] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "timestamp": self.timestamp.isoformat(),
            "corpus_counts": {
                k: {
                    "corpus_type": v.corpus_type,
                    "display_name": v.display_name,
                    "storage_count": v.storage_count,
                    "vector_count": v.vector_count,
                    "gap": v.gap,
                    "coverage_percent": v.coverage_percent,
                    "has_sql_source": v.has_sql_source,
                    "has_vector_index": v.has_vector_index,
                    "last_indexed": v.last_indexed.isoformat() if v.last_indexed else None,
                }
                for k, v in self.corpus_counts.items()
            },
            "total_storage_docs": self.total_storage_docs,
            "total_vector_docs": self.total_vector_docs,
            "total_gap": self.total_gap,
            "overall_coverage_percent": self.overall_coverage_percent,
            "storage_stats": self.storage_stats.to_dict() if self.storage_stats else None,
        }


class DataStatus:
    """
    Schema-aware data status utility.

    Provides corpus counts, gaps, and coverage metrics using the authoritative
    CORPUS_REGISTRY for schema information.
    """

    def __init__(
        self,
        storage: StorageBackend,
        vectors: VectorBackend,
        jurisdiction_id: str,
    ):
        """
        Initialize data status utility.

        Args:
            storage: Storage backend (Postgres or SQLite)
            vectors: Vector backend (pgvector or ChromaDB)
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
        """
        self._storage = storage
        self._vectors = vectors
        self._jurisdiction_id = jurisdiction_id

    def summary(self) -> DataStatusReport:
        """
        Get complete data status summary.

        Returns:
            DataStatusReport with counts for all corpus types
        """
        corpus_counts: Dict[str, CorpusCount] = {}
        total_storage = 0
        total_vector = 0

        # Get storage stats
        try:
            storage_stats = self._storage.get_stats(self._jurisdiction_id)
        except Exception:
            storage_stats = None

        # Check each corpus type
        for corpus_type in get_city_corpus_types():
            config = CORPUS_REGISTRY[corpus_type]

            # Get storage count
            storage_count = self._get_storage_count(corpus_type, config)

            # Get vector count (if indexed)
            vector_count = 0
            last_indexed = None
            if config.has_vector_index:
                try:
                    vector_stats = self._vectors.get_stats(
                        self._jurisdiction_id,
                        corpus_type.value,
                        self._storage,
                    )
                    vector_count = vector_stats.document_count
                    last_indexed = vector_stats.last_indexed
                except Exception:
                    pass

            # Calculate gap and coverage
            gap = storage_count - vector_count if config.has_vector_index else 0
            coverage = None
            if config.has_vector_index and storage_count > 0:
                coverage = (vector_count / storage_count) * 100

            corpus_counts[corpus_type.value] = CorpusCount(
                corpus_type=corpus_type.value,
                display_name=config.display_name,
                storage_count=storage_count,
                vector_count=vector_count,
                gap=gap,
                coverage_percent=coverage,
                has_sql_source=config.has_sql_source,
                has_vector_index=config.has_vector_index,
                last_indexed=last_indexed,
            )

            total_storage += storage_count
            if config.has_vector_index:
                total_vector += vector_count

        # Calculate overall coverage
        overall_coverage = None
        total_gap = 0
        vectorized_storage = sum(
            c.storage_count for c in corpus_counts.values() if c.has_vector_index
        )
        if vectorized_storage > 0:
            overall_coverage = (total_vector / vectorized_storage) * 100
            total_gap = vectorized_storage - total_vector

        return DataStatusReport(
            jurisdiction_id=self._jurisdiction_id,
            timestamp=datetime.now(),
            corpus_counts=corpus_counts,
            total_storage_docs=total_storage,
            total_vector_docs=total_vector,
            total_gap=total_gap,
            overall_coverage_percent=overall_coverage,
            storage_stats=storage_stats,
        )

    def gaps(self) -> Dict[str, Dict[str, int]]:
        """
        Get gap analysis by corpus.

        Returns:
            Dict mapping corpus_type to {storage: N, indexed: M, gap: N-M}
        """
        result = {}
        for corpus_type in get_city_corpus_types():
            config = CORPUS_REGISTRY[corpus_type]
            if not config.has_vector_index:
                continue

            storage_count = self._get_storage_count(corpus_type, config)
            vector_count = 0
            try:
                vector_stats = self._vectors.get_stats(
                    self._jurisdiction_id,
                    corpus_type.value,
                    self._storage,
                )
                vector_count = vector_stats.document_count
            except Exception:
                pass

            gap = storage_count - vector_count
            if gap != 0:  # Only include non-zero gaps
                result[corpus_type.value] = {
                    "storage": storage_count,
                    "indexed": vector_count,
                    "gap": gap,
                }

        return result

    def _get_storage_count(
        self,
        corpus_type: CorpusType,
        config: CorpusConfig,
    ) -> int:
        """Get storage count for a corpus type using the registered method."""
        try:
            if config.count_method:
                method = getattr(self._storage, config.count_method, None)
                if method:
                    return method(self._jurisdiction_id)
            elif corpus_type == CorpusType.MEETINGS:
                # Meetings uses len(get_meetings())
                meetings = self._storage.get_meetings(self._jurisdiction_id)
                return len(meetings) if meetings else 0
        except Exception:
            pass
        return 0


class VectorCoverage:
    """
    Vector index coverage analyzer.

    Provides detailed coverage analysis for vector embeddings.
    """

    def __init__(
        self,
        storage: StorageBackend,
        vectors: VectorBackend,
        jurisdiction_id: str,
    ):
        """
        Initialize vector coverage analyzer.

        Args:
            storage: Storage backend
            vectors: Vector backend
            jurisdiction_id: Target jurisdiction
        """
        self._storage = storage
        self._vectors = vectors
        self._jurisdiction_id = jurisdiction_id

    def by_corpus(self) -> List[Dict[str, Any]]:
        """
        Get vector coverage by corpus type.

        Returns:
            List of coverage info dicts, sorted by coverage percent (ascending)
        """
        results = []
        for corpus_type in get_vector_indexed_types():
            config = CORPUS_REGISTRY[corpus_type]

            # Skip non-city corpora for city jurisdictions
            if config.jurisdiction_type == "state" and self._jurisdiction_id.startswith("city-"):
                continue

            try:
                stats = self._vectors.get_stats(
                    self._jurisdiction_id,
                    corpus_type.value,
                    self._storage,
                )
                results.append({
                    "corpus_type": corpus_type.value,
                    "display_name": config.display_name,
                    "storage_count": stats.storage_document_count or 0,
                    "vector_count": stats.document_count,
                    "coverage_percent": stats.coverage_percent,
                    "last_indexed": stats.last_indexed,
                    "status": self._get_status(stats.coverage_percent),
                })
            except Exception:
                results.append({
                    "corpus_type": corpus_type.value,
                    "display_name": config.display_name,
                    "storage_count": 0,
                    "vector_count": 0,
                    "coverage_percent": None,
                    "last_indexed": None,
                    "status": "unknown",
                })

        # Sort by coverage (None/unknown at end, then ascending)
        results.sort(key=lambda x: (
            x["coverage_percent"] is None,
            x["coverage_percent"] or 0,
        ))

        return results

    def total(self) -> Dict[str, Any]:
        """
        Get total vector coverage summary.

        Returns:
            Dict with total counts and overall coverage
        """
        by_corpus = self.by_corpus()
        total_storage = sum(c["storage_count"] for c in by_corpus)
        total_vector = sum(c["vector_count"] for c in by_corpus)
        coverage = (total_vector / total_storage * 100) if total_storage > 0 else None

        return {
            "jurisdiction_id": self._jurisdiction_id,
            "total_storage": total_storage,
            "total_vector": total_vector,
            "total_gap": total_storage - total_vector,
            "coverage_percent": coverage,
            "corpus_count": len(by_corpus),
        }

    @staticmethod
    def _get_status(coverage: Optional[float]) -> str:
        """Get status indicator based on coverage percent."""
        if coverage is None:
            return "unknown"
        if coverage >= 99:
            return "complete"
        if coverage >= 90:
            return "good"
        if coverage >= 50:
            return "partial"
        return "low"


def format_data_status(report: DataStatusReport, no_color: bool = False) -> str:
    """
    Format data status report for terminal display.

    Args:
        report: DataStatusReport to format
        no_color: If True, disable ANSI colors

    Returns:
        Formatted string for terminal output
    """
    lines = []

    # Header
    lines.append(f"Data Status: {report.jurisdiction_id}")
    lines.append("")

    # Table header
    lines.append(f"{'Corpus':<20} {'Storage':>10} {'Indexed':>10} {'Gap':>8} {'Coverage':>10}")
    lines.append("-" * 62)

    # Corpus rows
    for corpus_type, count in sorted(report.corpus_counts.items()):
        if not count.has_vector_index:
            # SQL-only corpus
            lines.append(f"{count.display_name:<20} {count.storage_count:>10} {'n/a':>10} {'n/a':>8} {'n/a':>10}")
        else:
            gap_str = str(count.gap) if count.gap != 0 else "0"
            coverage_str = f"{count.coverage_percent:.0f}%" if count.coverage_percent is not None else "?"
            status = ""
            if count.gap > 0:
                status = " (!)"
            elif count.coverage_percent and count.coverage_percent >= 99:
                status = " (ok)"
            lines.append(f"{count.display_name:<20} {count.storage_count:>10} {count.vector_count:>10} {gap_str:>8} {coverage_str:>10}{status}")

    # Summary
    lines.append("-" * 62)
    overall = f"{report.overall_coverage_percent:.1f}%" if report.overall_coverage_percent else "?"
    lines.append(f"{'Total':<20} {report.total_storage_docs:>10} {report.total_vector_docs:>10} {report.total_gap:>8} {overall:>10}")

    return "\n".join(lines)


def format_vector_coverage(coverage_list: List[Dict[str, Any]], no_color: bool = False) -> str:
    """
    Format vector coverage for terminal display.

    Args:
        coverage_list: List from VectorCoverage.by_corpus()
        no_color: If True, disable ANSI colors

    Returns:
        Formatted string for terminal output
    """
    lines = []

    # Header
    lines.append(f"{'Corpus':<20} {'Docs':>8} {'Indexed':>10} {'Coverage':>10} {'Status':>10}")
    lines.append("-" * 62)

    for item in coverage_list:
        coverage_str = f"{item['coverage_percent']:.0f}%" if item['coverage_percent'] is not None else "?"
        lines.append(
            f"{item['display_name']:<20} {item['storage_count']:>8} {item['vector_count']:>10} "
            f"{coverage_str:>10} {item['status']:>10}"
        )

    return "\n".join(lines)
