"""
v2 Query Interface — Pydantic models.

Two-level result structure:
  - Stable envelope: type, ref, title, date, summary, relevance
  - Type-specific details dict: answers common follow-ups without civic.context call

Every response includes ResponseMeta with schema_version, timing, corpus status.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


SCHEMA_VERSION = "2025.1"


# === Enums ===

class CorpusName(str, Enum):
    """Domain vocabulary for corpus types (not table names)."""
    decisions = "decisions"
    testimony = "testimony"
    testimony_public = "testimony:public"
    testimony_council = "testimony:council"
    testimony_staff = "testimony:staff"
    legislation = "legislation"
    issues = "issues"
    budget = "budget"
    meetings = "meetings"
    rules = "rules"
    orders = "orders"
    municipal_code = "municipal_code"
    packets = "packets"
    congressional_votes = "congressional_votes"
    federal_awards = "federal_awards"


class SearchMode(str, Enum):
    search = "search"          # Find matching items (default)
    aggregate = "aggregate"    # Counts/statistics per corpus
    trend = "trend"            # Temporal patterns (time-bucketed counts)
    diff = "diff"              # What's new since a snapshot date (EXCEPT)
    intersect = "intersect"    # Items appearing across multiple corpora (INTERSECT)


class SearchDepth(str, Enum):
    minimal = "minimal"      # IDs + titles
    standard = "standard"    # + summaries
    deep = "deep"            # + inline details


class UpcomingType(str, Enum):
    meetings = "meetings"
    hearings = "hearings"
    comment_periods = "comment_periods"
    legislation = "legislation"
    elections = "elections"


class ExploreWhat(str, Enum):
    jurisdictions = "jurisdictions"
    corpora = "corpora"
    actions = "actions"
    capabilities = "capabilities"
    schema_version = "schema_version"
    # corpus_schema:{name} is handled dynamically


class CorpusStatus(str, Enum):
    ok = "ok"
    timeout = "timeout"
    error = "error"
    empty = "empty"


# === Result Models ===

class CivicResult(BaseModel):
    """Two-level result: stable envelope + type-specific details."""
    type: str = Field(..., description="Corpus type (e.g., 'decision', 'legislation')")
    ref: str = Field(..., description="Opaque reference for civic.context/civic.act")
    title: str
    date: Optional[str] = Field(None, description="ISO date string")
    summary: Optional[str] = None
    relevance: Optional[float] = Field(None, ge=0.0, le=1.0)
    jurisdiction: Optional[str] = Field(None, description="Source jurisdiction ID (set in cross-jurisdiction queries)")
    details: Dict[str, Any] = Field(default_factory=dict, description="Type-specific essential metadata")


class ResponseMeta(BaseModel):
    """Metadata included in every v2 response."""
    schema_version: str = SCHEMA_VERSION
    query_time_ms: int = 0
    corpora_searched: List[str] = Field(default_factory=list)
    corpus_counts: Dict[str, int] = Field(default_factory=dict)
    corpus_times_ms: Dict[str, int] = Field(default_factory=dict)
    corpus_status: Dict[str, str] = Field(default_factory=dict)
    total_results: int = 0
    cursor: Optional[str] = None


# === Request Models ===

class SearchRequest(BaseModel):
    """civic.search request."""
    query: str = Field(..., description="Natural language search query")
    corpus: List[str] = Field(..., description="Corpus types to search", min_length=1)
    jurisdiction: Optional[str] = None
    since: Optional[str] = Field(None, description="Date range start (ISO)")
    until: Optional[str] = Field(None, description="Date range end (ISO)")
    location: Optional[str] = Field(None, description="Geographic filter")
    limit: int = Field(10, ge=1, le=100, description="Max results across all corpora")
    depth: SearchDepth = SearchDepth.standard
    mode: "SearchMode" = Field(SearchMode.search, description="search (items), aggregate (counts), trend (temporal), diff (new since snapshot), intersect (cross-corpus)")
    cursor: Optional[str] = Field(None, description="Opaque pagination cursor from previous response")
    snapshot_date: Optional[str] = Field(None, description="ISO date for diff mode — returns items newer than this date")
    intersect_corpus: Optional[List[str]] = Field(None, description="For intersect mode — secondary corpora to join against")
    include_parents: bool = Field(False, description="Include parent jurisdictions (county, state, federal)")
    include_siblings: bool = Field(False, description="Include sibling jurisdictions (cities sharing same parent county)")
    also_include: Optional[List[str]] = Field(
        None,
        description="Additional jurisdiction IDs to include (cross-county, explicit comparisons)",
    )

    @field_validator("snapshot_date")
    @classmethod
    def validate_snapshot_date(cls, v):
        if v is not None:
            from datetime import date
            try:
                date.fromisoformat(v[:10])
            except (ValueError, TypeError):
                raise ValueError(f"snapshot_date must be ISO format (YYYY-MM-DD), got: {v!r}")
        return v


class UpcomingRequest(BaseModel):
    """civic.upcoming request."""
    types: List[str] = Field(
        default=["meetings"],
        description="Event types: meetings, hearings, comment_periods, legislation, elections",
    )
    jurisdiction: Optional[str] = None
    days: int = Field(14, ge=1, le=365)
    actionable_only: bool = False


class ContextRequest(BaseModel):
    """civic.context request — item context (ref) or civic jargon lookup (concept)."""
    ref: Optional[str] = Field(None, description="Opaque ref from a search/upcoming result")
    concept: Optional[str] = Field(None, description="Civic term to look up (e.g., 'conditional use permit')")
    depth: str = Field("standard", description="minimal, standard, or deep")
    sections: Optional[List[str]] = Field(None, description="Sections to include (omit for all)")

    @model_validator(mode="after")
    def ref_or_concept(self):
        if not self.ref and not self.concept:
            raise ValueError("Either 'ref' or 'concept' must be provided")
        if self.ref and self.concept:
            raise ValueError("Provide 'ref' or 'concept', not both")
        return self


class ActRequest(BaseModel):
    """civic.act request."""
    action: str = Field(..., description="Action name: prepare_comment, comment_template, etc.")
    ref: Optional[str] = Field(None, description="Item reference for context-dependent actions")
    # Action-specific params passed as extra fields
    params: Dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters")


class ExploreRequest(BaseModel):
    """civic.explore request."""
    what: str = Field(..., description="What to explore: jurisdictions, corpora, corpus_schema:{name}, actions, capabilities, schema_version")
    jurisdiction: Optional[str] = None


# === Response Models ===

class AggregateEntry(BaseModel):
    """One corpus's aggregate stats."""
    corpus: str
    count: int = 0
    earliest: Optional[str] = None
    latest: Optional[str] = None


class TrendBucket(BaseModel):
    """One time bucket in a trend."""
    period: str  # e.g. "2025-06" (year-month)
    count: int = 0
    corpus: str = ""


class SearchResponse(BaseModel):
    """civic.search response. Shape depends on mode:
    - search: results list (flat, ranked by RRF)
    - aggregate: aggregates list (results empty)
    - trend: trends list (results empty)

    For cross-jurisdiction queries (include_parents/include_siblings),
    jurisdiction_results groups results by source jurisdiction while
    results still contains the flat ranked list.
    """
    results: List[CivicResult] = Field(default_factory=list)
    jurisdiction_results: Optional[Dict[str, List[CivicResult]]] = Field(
        None, description="Results grouped by jurisdiction (set in cross-jurisdiction queries)"
    )
    aggregates: Optional[List[AggregateEntry]] = None
    trends: Optional[List[TrendBucket]] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class UpcomingResponse(BaseModel):
    """civic.upcoming response."""
    results: List[CivicResult] = Field(default_factory=list)
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class ContextResponse(BaseModel):
    """civic.context response — wraps existing ContextBundle."""
    context: Optional[Dict[str, Any]] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class ActResponse(BaseModel):
    """civic.act response."""
    result: Dict[str, Any] = Field(default_factory=dict)
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class ExploreResponse(BaseModel):
    """civic.explore response."""
    data: Any = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


# === Internal Planning Models ===

class CorpusQuery(BaseModel):
    """A single corpus query within a plan."""
    corpus: str
    method: str  # CivicOS method name
    params: Dict[str, Any] = Field(default_factory=dict)
    per_corpus_limit: int = 5
    offset: int = 0  # For cursor-based pagination


class QueryPlan(BaseModel):
    """Plan for executing a multi-corpus search."""
    corpus_queries: List[CorpusQuery] = Field(default_factory=list)
    timeout_ms: int = 10000
