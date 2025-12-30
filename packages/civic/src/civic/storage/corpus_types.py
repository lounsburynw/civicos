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
    from civic.storage.corpus_types import CorpusType, CORPUS_REGISTRY, get_all_corpus_types

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

    # State/federal-level corpora
    LEGISLATION = "legislation" # State and federal bills
    PROGRAMS = "programs"       # Federal programs (grants, etc.)

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

    # Aliases used in other subsystems (for mapping)
    aliases: tuple = ()

    # Whether this corpus has meeting context (meeting_id, meeting_title, etc.)
    has_meeting_context: bool = False


# Registry of all corpus types with their configurations
CORPUS_REGISTRY: Dict[CorpusType, CorpusConfig] = {
    CorpusType.CHUNKS: CorpusConfig(
        display_name="Agenda Chunks",
        storage_method="get_chunks",
        count_method="get_chunk_count",
        text_extractor="_chunk_to_text",
        jurisdiction_type="city",
        aliases=("pdf", "chunk"),
        has_meeting_context=True,
    ),
    CorpusType.DECISIONS: CorpusConfig(
        display_name="Decisions",
        storage_method="get_decisions",
        count_method="get_decision_count",
        text_extractor="_decision_to_text",
        jurisdiction_type="city",
        aliases=("decision",),
        has_meeting_context=True,
    ),
    CorpusType.MEETINGS: CorpusConfig(
        display_name="Meetings",
        storage_method="get_meetings",
        count_method=None,  # Uses len(get_meetings())
        text_extractor="_meeting_to_text",
        jurisdiction_type="city",
        aliases=("meeting",),
        has_meeting_context=True,
    ),
    CorpusType.TRANSCRIPTS: CorpusConfig(
        display_name="Transcripts",
        storage_method="get_transcripts",
        count_method="get_transcript_count",
        text_extractor="_transcript_to_text",
        jurisdiction_type="city",
        aliases=("transcript",),
        has_meeting_context=True,
    ),
    CorpusType.MUNICIPAL_CODE: CorpusConfig(
        display_name="Municipal Code",
        storage_method="get_municipal_code",
        count_method="get_municipal_code_count",
        text_extractor="_municipal_code_to_text",
        jurisdiction_type="city",
        aliases=(),
        has_meeting_context=False,
    ),
    CorpusType.ISSUES: CorpusConfig(
        display_name="Community Issues",
        storage_method="get_issues",
        count_method="get_issue_count",
        text_extractor="_issue_to_text",
        jurisdiction_type="city",
        aliases=("issue",),
        has_meeting_context=False,
    ),
    CorpusType.LEGISLATION: CorpusConfig(
        display_name="Legislation",
        storage_method="get_legislation",
        count_method="get_legislation_count",
        text_extractor="_legislation_to_text",
        jurisdiction_type="state",
        aliases=(),
        has_meeting_context=False,
    ),
    CorpusType.PROGRAMS: CorpusConfig(
        display_name="Federal Programs",
        storage_method="get_programs",
        count_method="get_program_count",
        text_extractor="_program_to_text",
        jurisdiction_type="both",  # Can be queried from any jurisdiction
        aliases=("program",),
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
    "legislation": CorpusType.LEGISLATION,
    "programs": CorpusType.PROGRAMS,
}
