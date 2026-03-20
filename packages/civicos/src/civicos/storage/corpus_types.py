"""
Centralized corpus type definitions.

This module provides a single source of truth for all corpus types used
across the Civic platform. It handles naming inconsistencies between
different subsystems and provides registry-based corpus management.

Architecture:
    - CorpusType enum: Canonical corpus identifiers
    - CORPUS_REGISTRY: Metadata for each corpus (storage method, text extraction, etc.)
    - Helper functions: get_corpus_types(), get_storage_method(), etc.

Usage:
    from civicos.storage.corpus_types import CorpusType, CORPUS_REGISTRY, get_all_corpus_types

    # Get all corpus types for a context
    city_types = get_corpus_types_for_jurisdiction("city")
    state_types = get_corpus_types_for_jurisdiction("state")

    # Get storage method name
    method = CORPUS_REGISTRY[CorpusType.CHUNKS].storage_method  # "get_chunks"
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Any


class CorpusType(str, Enum):
    """
    Canonical corpus type identifiers.

    These are the authoritative names used internally. Different subsystems
    may use variations (e.g., "decision" vs "decisions") but should map to these.
    """
    # City/jurisdiction-level corpora
    CHUNKS = "chunks"           # Agenda packet chunks (aka "pdf" in unified search)
    DECISIONS = "decisions"     # Council decisions (aka "decision" singular)
    MEETINGS = "meetings"       # Meeting metadata
    TRANSCRIPTS = "transcripts" # Meeting transcripts (aka "transcript" singular)
    MUNICIPAL_CODE = "municipal_code"  # Local municipal code sections
    ISSUES = "issues"           # Community issues (aka "issue" singular)
    ELECTIONS = "elections"     # Elections, contests, ballot measures

    # Budget corpora
    BUDGET = "budget_items"       # Municipal budget line items

    # State/federal-level corpora
    LEGISLATION = "legislation"   # Bills (pending/historical) - parameterized by state
    PROGRAMS = "programs"         # Federal programs (grants, etc.)
    STATE_PROGRAMS = "state_programs"  # State pass-through grants (per-jurisdiction)
    CODIFIED_LAW = "codified_law" # Statutes (U.S. Code, CA Codes, etc.) - parameterized by jurisdiction
    EXECUTIVE_ORDERS = "executive_orders"  # Presidential executive orders (SESSION 432)
    FEDERAL_RULES = "federal_rules"        # Federal rulemaking (proposed rules, final rules, notices)
    FEDERAL_AWARDS = "federal_awards"      # Federal awards/grants from USAspending.gov
    CONGRESSIONAL_VOTES = "congressional_votes"  # Per-member roll call vote positions
    CONGRESSIONAL_HEARINGS = "congressional_hearings"  # Committee hearings from Congress.gov

    def __str__(self) -> str:
        return self.value


@dataclass
class CorpusConfig:
    """Configuration for a corpus type."""

    # Display name for UI
    display_name: str

    # Storage backend method to get documents (e.g., "get_chunks", "get_decisions")
    storage_method: str

    # Storage backend method to get count (e.g., "get_chunk_count")
    count_method: Optional[str]

    # Function to extract text from a document for embedding
    # Signature: (doc: Dict) -> str
    text_extractor: str  # Method name on pgvector_backend

    # Jurisdiction type this corpus applies to
    jurisdiction_type: str  # "city", "state", or "both"

    # SQL table name in postgres_backend (e.g., "decisions", "chunks")
    # None if this corpus is vector-only with no SQL backing
    sql_table: Optional[str] = None

    # Vector collection suffix (appended to jurisdiction_id, e.g., "decisions" -> "{jurisdiction}_decisions")
    # None if this corpus is SQL-only with no vector embedding
    vector_collection_suffix: Optional[str] = None

    # Aliases used in other subsystems (for mapping)
    aliases: tuple = ()

    # Whether this corpus has meeting context (meeting_id, meeting_title, etc.)
    has_meeting_context: bool = False

    @property
    def has_sql_source(self) -> bool:
        """True if this corpus is backed by a SQL table."""
        return self.sql_table is not None

    @property
    def has_vector_index(self) -> bool:
        """True if this corpus has vector embeddings."""
        return self.vector_collection_suffix is not None


# Registry of all corpus types with their configurations
CORPUS_REGISTRY: Dict[CorpusType, CorpusConfig] = {
    CorpusType.CHUNKS: CorpusConfig(
        display_name="Agenda Chunks",
        storage_method="get_chunks",
        count_method="get_chunk_count",
        text_extractor="_chunk_to_text",
        jurisdiction_type="city",
        sql_table="chunks",
        vector_collection_suffix="chunks",
        aliases=("pdf", "chunk"),
        has_meeting_context=True,
    ),
    CorpusType.DECISIONS: CorpusConfig(
        display_name="Decisions",
        storage_method="get_decisions",
        count_method="get_decision_count",
        text_extractor="_decision_to_text",
        jurisdiction_type="city",
        sql_table="decisions",
        vector_collection_suffix="decisions",
        aliases=("decision",),
        has_meeting_context=True,
    ),
    CorpusType.MEETINGS: CorpusConfig(
        display_name="Meetings",
        storage_method="get_meetings",
        count_method=None,  # Uses len(get_meetings())
        text_extractor="_meeting_to_text",
        jurisdiction_type="city",
        sql_table="meetings",
        vector_collection_suffix=None,  # Meetings are SQL-only, not vectorized
        aliases=("meeting",),
        has_meeting_context=True,
    ),
    CorpusType.TRANSCRIPTS: CorpusConfig(
        display_name="Transcripts",
        storage_method="get_transcripts",
        count_method="get_transcript_count",
        text_extractor="_transcript_to_text",
        jurisdiction_type="city",
        sql_table="transcripts",
        vector_collection_suffix="transcripts",
        aliases=("transcript",),
        has_meeting_context=True,
    ),
    CorpusType.MUNICIPAL_CODE: CorpusConfig(
        display_name="Municipal Code",
        storage_method="get_municipal_code",
        count_method="get_municipal_code_count",
        text_extractor="_municipal_code_to_text",
        jurisdiction_type="city",
        sql_table=None,  # Vector-only corpus
        vector_collection_suffix="municipal_code",
        aliases=(),
        has_meeting_context=False,
    ),
    CorpusType.ISSUES: CorpusConfig(
        display_name="Community Issues",
        storage_method="get_issues",
        count_method="get_issue_count",
        text_extractor="_issue_to_text",
        jurisdiction_type="city",
        sql_table="issues",
        vector_collection_suffix="issues",
        aliases=("issue",),
        has_meeting_context=False,
    ),
    CorpusType.ELECTIONS: CorpusConfig(
        display_name="Elections",
        storage_method="get_elections",
        count_method="get_election_count",
        text_extractor="_election_to_text",
        jurisdiction_type="both",  # Elections span federal/state/local
        sql_table=None,  # Vector-only corpus
        vector_collection_suffix="elections",
        aliases=("election", "ballot", "vote"),
        has_meeting_context=False,
    ),
    CorpusType.BUDGET: CorpusConfig(
        display_name="Budget Items",
        storage_method="get_budget_items",
        count_method="get_budget_items_count",
        text_extractor="_budget_item_to_text",
        jurisdiction_type="city",
        sql_table="budget_items",
        vector_collection_suffix="budget_items",
        aliases=("budget",),
        has_meeting_context=False,
    ),
    CorpusType.LEGISLATION: CorpusConfig(
        display_name="Legislation",
        storage_method="get_legislation",
        count_method="get_legislation_count",
        text_extractor="_legislation_to_text",
        jurisdiction_type="state",
        sql_table=None,  # Vector-only corpus
        vector_collection_suffix="legislation",
        aliases=(),
        has_meeting_context=False,
    ),
    CorpusType.PROGRAMS: CorpusConfig(
        display_name="Federal Programs",
        storage_method="get_programs",
        count_method="get_program_count",
        text_extractor="_program_to_text",
        jurisdiction_type="both",  # Can be queried from any jurisdiction
        sql_table=None,  # Vector-only corpus (federal + county)
        vector_collection_suffix="federal_programs",  # Also has county_programs
        aliases=("program",),
        has_meeting_context=False,
    ),
    CorpusType.STATE_PROGRAMS: CorpusConfig(
        display_name="State Programs",
        storage_method="get_state_passthrough_funds",
        count_method="get_state_passthrough_count",
        text_extractor="_state_program_to_text",
        jurisdiction_type="city",  # Per-jurisdiction (different grants per city)
        sql_table="state_passthrough_funds",
        vector_collection_suffix="state_programs",
        aliases=("state_program", "state_grant", "state_grants"),
        has_meeting_context=False,
    ),
    CorpusType.CODIFIED_LAW: CorpusConfig(
        display_name="Codified Law",
        storage_method="get_codified_law",
        count_method="get_codified_law_count",
        text_extractor="_codified_law_to_text",
        jurisdiction_type="both",  # Federal (U.S. Code) or state (CA Codes, etc.)
        sql_table=None,  # Vector-only corpus
        vector_collection_suffix="codified_law",
        aliases=("statutes", "code", "us_code", "state_code"),
        has_meeting_context=False,
    ),
    CorpusType.EXECUTIVE_ORDERS: CorpusConfig(
        display_name="Executive Orders",
        storage_method="get_executive_orders",
        count_method="get_executive_orders_count",
        text_extractor="_executive_order_to_text",
        jurisdiction_type="both",  # Federal orders, queryable from any jurisdiction
        sql_table=None,  # Vector-only corpus
        vector_collection_suffix="executive_orders",
        aliases=("eo", "executive_order"),
        has_meeting_context=False,
    ),
    CorpusType.FEDERAL_RULES: CorpusConfig(
        display_name="Federal Rules",
        storage_method="get_federal_rules",
        count_method="get_federal_rules_count",
        text_extractor="_federal_rule_to_text",
        jurisdiction_type="both",  # Federal rules, queryable from any jurisdiction
        sql_table="federal_rules",
        vector_collection_suffix="federal_rules",
        aliases=("federal_rule", "rulemaking", "nprm"),
        has_meeting_context=False,
    ),
    CorpusType.FEDERAL_AWARDS: CorpusConfig(
        display_name="Federal Awards",
        storage_method="get_federal_awards",
        count_method="get_federal_awards_count",
        text_extractor="_federal_award_to_text",
        jurisdiction_type="city",  # Per-jurisdiction awards from USAspending
        sql_table="federal_awards",
        vector_collection_suffix="federal_awards",
        aliases=("federal_award", "grant", "grants", "award"),
        has_meeting_context=False,
    ),
    CorpusType.CONGRESSIONAL_VOTES: CorpusConfig(
        display_name="Congressional Votes",
        storage_method="get_congressional_votes",
        count_method="get_congressional_votes_count",
        text_extractor=None,  # Not vectorized — structured data, queried by filters
        jurisdiction_type="shared",  # Not per-jurisdiction, global
        sql_table="congressional_votes",
        vector_collection_suffix=None,  # No vectors — structured queries only
        aliases=("congressional_vote", "roll_call", "roll_calls", "voting_record"),
        has_meeting_context=False,
    ),
    CorpusType.CONGRESSIONAL_HEARINGS: CorpusConfig(
        display_name="Congressional Hearings",
        storage_method="get_congressional_hearings",
        count_method="get_congressional_hearings_count",
        text_extractor=None,  # Not vectorized — structured event data
        jurisdiction_type="shared",  # Not per-jurisdiction, global
        sql_table="congressional_hearings",
        vector_collection_suffix=None,
        aliases=("congressional_hearing", "committee_hearing", "committee_meeting"),
        has_meeting_context=False,
    ),
}


# Alias mapping for backward compatibility
_ALIAS_MAP: Dict[str, CorpusType] = {}
for corpus_type, config in CORPUS_REGISTRY.items():
    _ALIAS_MAP[corpus_type.value] = corpus_type
    for alias in config.aliases:
        _ALIAS_MAP[alias] = corpus_type


def resolve_corpus_type(name: str) -> CorpusType:
    """
    Resolve a corpus type name (including aliases) to canonical CorpusType.

    Args:
        name: Corpus type name or alias (e.g., "chunks", "pdf", "decision")

    Returns:
        Canonical CorpusType enum value

    Raises:
        ValueError: If name is not a valid corpus type or alias
    """
    normalized = name.lower().strip()
    if normalized in _ALIAS_MAP:
        return _ALIAS_MAP[normalized]
    raise ValueError(
        f"Unknown corpus type: '{name}'. "
        f"Valid types: {sorted(_ALIAS_MAP.keys())}"
    )


def get_corpus_types_for_jurisdiction(jurisdiction_type: str) -> List[CorpusType]:
    """
    Get corpus types applicable to a jurisdiction type.

    Args:
        jurisdiction_type: "city" or "state"

    Returns:
        List of applicable CorpusType values
    """
    result = []
    for corpus_type, config in CORPUS_REGISTRY.items():
        if config.jurisdiction_type == jurisdiction_type or config.jurisdiction_type == "both":
            result.append(corpus_type)
    return result


def get_city_corpus_types() -> List[CorpusType]:
    """Get corpus types for city-level jurisdictions."""
    return get_corpus_types_for_jurisdiction("city")


def get_state_corpus_types() -> List[CorpusType]:
    """Get corpus types for state-level jurisdictions."""
    return get_corpus_types_for_jurisdiction("state")


def get_all_corpus_types() -> List[CorpusType]:
    """Get all corpus types."""
    return list(CORPUS_REGISTRY.keys())


def get_corpus_type_names(jurisdiction_type: Optional[str] = None) -> List[str]:
    """
    Get corpus type names as strings.

    Args:
        jurisdiction_type: Optional filter ("city" or "state")

    Returns:
        List of corpus type name strings
    """
    if jurisdiction_type:
        types = get_corpus_types_for_jurisdiction(jurisdiction_type)
    else:
        types = get_all_corpus_types()
    return [t.value for t in types]


def infer_jurisdiction_type(jurisdiction_id: str) -> str:
    """
    Infer jurisdiction type from jurisdiction ID.

    Args:
        jurisdiction_id: e.g., "city-san-rafael" or "state-CA"

    Returns:
        "city" or "state"
    """
    if jurisdiction_id.startswith("state-"):
        return "state"
    return "city"


# For backward compatibility with unified.py's CORPUS_TYPES frozenset
# Maps unified search names to canonical names
UNIFIED_SEARCH_ALIASES = {
    "decision": CorpusType.DECISIONS,
    "pdf": CorpusType.CHUNKS,
    "transcript": CorpusType.TRANSCRIPTS,
    "issue": CorpusType.ISSUES,
    "municipal_code": CorpusType.MUNICIPAL_CODE,
    "budget": CorpusType.BUDGET,
    "budget_items": CorpusType.BUDGET,
    "legislation": CorpusType.LEGISLATION,
    "programs": CorpusType.PROGRAMS,
    "state_programs": CorpusType.STATE_PROGRAMS,
    "codified_law": CorpusType.CODIFIED_LAW,
    "statutes": CorpusType.CODIFIED_LAW,
    "executive_orders": CorpusType.EXECUTIVE_ORDERS,
    "eo": CorpusType.EXECUTIVE_ORDERS,
    "federal_rules": CorpusType.FEDERAL_RULES,
    "rulemaking": CorpusType.FEDERAL_RULES,
}


# Backward-compatible frozenset of valid search corpus type names (for unified.py)
# Uses the aliases that unified search expects (singular forms like "decision", "pdf", etc.)
UNIFIED_CORPUS_TYPES = frozenset({
    "decision",
    "pdf",
    "transcript",
    "issue",
    "municipal_code",
    "budget",
    "legislation",
    "programs",
    "state_programs",
})


def get_sql_backed_types() -> List[CorpusType]:
    """Get corpus types that have SQL table backing."""
    return [ct for ct, cfg in CORPUS_REGISTRY.items() if cfg.has_sql_source]


def get_vector_indexed_types() -> List[CorpusType]:
    """Get corpus types that have vector embeddings."""
    return [ct for ct, cfg in CORPUS_REGISTRY.items() if cfg.has_vector_index]


def get_corpus_metadata(corpus_type: CorpusType) -> Dict[str, Any]:
    """
    Get metadata dict for a corpus type, suitable for API responses.

    Args:
        corpus_type: The corpus type to get metadata for

    Returns:
        Dict with display_name, sql_table, vector_collection_suffix, etc.
    """
    config = CORPUS_REGISTRY[corpus_type]
    return {
        "name": corpus_type.value,
        "display_name": config.display_name,
        "sql_table": config.sql_table,
        "vector_collection_suffix": config.vector_collection_suffix,
        "has_sql_source": config.has_sql_source,
        "has_vector_index": config.has_vector_index,
        "jurisdiction_type": config.jurisdiction_type,
        "has_meeting_context": config.has_meeting_context,
        "aliases": list(config.aliases),
    }


def get_all_corpus_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Get metadata for all corpus types.

    Returns:
        Dict mapping corpus type name to metadata dict
    """
    return {ct.value: get_corpus_metadata(ct) for ct in CorpusType}
