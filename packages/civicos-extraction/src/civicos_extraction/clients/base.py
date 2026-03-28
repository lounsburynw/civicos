"""
Base extractor protocol and common types.

Defines the interface that all platform clients should implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any, Protocol, runtime_checkable


@dataclass
class HealthStatus:
    """
    Standardized health check response for data sources.

    Used by dashboards to show unified status of all data sources.
    Each source exposes: available count, last_checked, errors[].
    """

    source_id: str  # "legistar-berkeley", "civicclerk-elcerrito", "proudcity-san-rafael"
    source_type: str  # "legistar", "civicclerk", "proudcity"
    jurisdiction_id: str  # "city-berkeley", "elcerritoca", "san-rafael"

    # Core metrics
    is_available: bool  # Can connect and fetch data
    available_count: int  # Number of items available in last check

    # Timing
    last_checked: datetime  # When health() was called
    check_duration_ms: float  # How long the health check took

    # Error tracking
    errors: List[str] = field(default_factory=list)  # Recent error messages

    # Optional quality metrics
    last_successful: Optional[datetime] = None  # Last successful fetch
    coverage_percent: Optional[float] = None  # Extraction coverage (platform-specific)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Platform-specific stats

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "jurisdiction_id": self.jurisdiction_id,
            "is_available": self.is_available,
            "available_count": self.available_count,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "check_duration_ms": self.check_duration_ms,
            "errors": self.errors,
            "last_successful": (
                self.last_successful.isoformat() if self.last_successful else None
            ),
            "coverage_percent": self.coverage_percent,
            "metadata": self.metadata,
        }


@dataclass
class ValidationResult:
    """
    Result of preflight validation for a data source.

    Used to fail fast before running extraction pipeline.
    Checks config correctness and API accessibility.
    """

    is_valid: bool  # All checks passed, safe to proceed
    config_valid: bool  # Config structure is correct
    api_reachable: bool  # API endpoint is accessible

    # Error tracking
    errors: List[str] = field(default_factory=list)  # Critical errors (fail fast)
    warnings: List[str] = field(default_factory=list)  # Non-blocking issues

    # Timing
    check_duration_ms: float = 0.0

    # Additional context
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "config_valid": self.config_valid,
            "api_reachable": self.api_reachable,
            "errors": self.errors,
            "warnings": self.warnings,
            "check_duration_ms": self.check_duration_ms,
            "metadata": self.metadata,
        }



@dataclass
class BudgetLineItem:
    """
    A single budget line item extracted from a municipal budget document.

    This is the common format for budget data that extractors should produce.
    All amounts are stored in cents to avoid floating-point precision issues.
    """

    fund: str  # "General Fund", "Enterprise - Water", etc.
    department: Optional[str]  # "Police", "Fire", etc.
    program: Optional[str]  # "Homelessness Services", etc.
    line_item: str  # Full line item description
    budgeted_cents: int  # Amount in cents (multiply dollars by 100)
    revised_cents: Optional[int] = None  # Mid-year revisions
    actual_cents: Optional[int] = None  # Actual spend (if available)
    source_page: Optional[int] = None  # Page number in source PDF
    notes: Optional[str] = None  # Special conditions, caveats

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "fund": self.fund,
            "department": self.department,
            "program": self.program,
            "line_item": self.line_item,
            "budgeted_cents": self.budgeted_cents,
            "revised_cents": self.revised_cents,
            "actual_cents": self.actual_cents,
            "source_page": self.source_page,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BudgetLineItem":
        """Create from dictionary."""
        return cls(
            fund=data["fund"],
            department=data.get("department"),
            program=data.get("program"),
            line_item=data["line_item"],
            budgeted_cents=data["budgeted_cents"],
            revised_cents=data.get("revised_cents"),
            actual_cents=data.get("actual_cents"),
            source_page=data.get("source_page"),
            notes=data.get("notes"),
        )


@dataclass
class FinancialConfig:
    """
    Financial data source configuration.

    Minimal configuration for financial data extraction.
    Complex lookups (entity names, UEIs) happen at runtime.
    """

    state: str  # "CA" - state code
    county: Optional[str] = None  # "Marin" - county name
    fiscal_year_start_month: int = 7  # July = 7 (CA standard)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FinancialConfig":
        """Create FinancialConfig from a dictionary."""
        return cls(
            state=data["state"],
            county=data.get("county"),
            fiscal_year_start_month=data.get("fiscal_year_start_month", 7),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {"state": self.state}
        if self.county:
            result["county"] = self.county
        if self.fiscal_year_start_month != 7:
            result["fiscal_year_start_month"] = self.fiscal_year_start_month
        return result

@dataclass
class ExtractionConfig:
    """
    Configuration for a data extraction source.

    Loaded from JSON config files in data/extraction/.
    """

    source_id: str  # "proudcity-san-rafael"
    source_type: str  # "proudcity", "legistar", "civicclerk"
    jurisdiction_id: str  # "city-san-rafael"
    base_url: str  # "https://www.cityofsanrafael.org"
    auto_discover: bool = False  # Whether to auto-discover archives
    archives: Dict[str, str] = field(default_factory=dict)  # meeting_type -> path
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional config
    financial: Optional[FinancialConfig] = None  # Financial data source config
    issue_source: Optional[str] = None  # 311 issue provider: "seeclickfix", etc.

    @classmethod
    def from_file(cls, path: str) -> "ExtractionConfig":
        """Load configuration from a JSON file."""
        import json
        with open(path, "r") as f:
            data = json.load(f)

        # Parse financial config if present
        financial = None
        if "financial" in data:
            financial = FinancialConfig.from_dict(data["financial"])

        return cls(
            source_id=data["source_id"],
            source_type=data["source_type"],
            jurisdiction_id=data["jurisdiction_id"],
            base_url=data["base_url"],
            auto_discover=data.get("auto_discover", False),
            archives=data.get("archives", {}),
            metadata=data.get("metadata", {}),
            financial=financial,
            issue_source=data.get("issue_source"),
        )

    @classmethod
    def from_jurisdiction(cls, jurisdiction_id: str) -> "ExtractionConfig":
        """Load configuration for a jurisdiction from the standard config directory."""
        from civicos_extraction.config import get_config_dir

        # Map jurisdiction_id to config file name
        # e.g., "city-san-rafael" -> "san-rafael.json"
        # e.g., "school-san-rafael" -> "san-rafael-schools.json"
        if jurisdiction_id.startswith("school-"):
            # School districts use "name-schools.json" format
            base_name = jurisdiction_id.replace("school-", "")
            config_name = f"{base_name}-schools"
        elif jurisdiction_id.startswith("county-") or jurisdiction_id.startswith("state-"):
            # Counties and states use full ID: county-marin.json, state-california.json
            config_name = jurisdiction_id
        else:
            # Cities use "name.json" format
            config_name = jurisdiction_id.replace("city-", "")
        config_path = get_config_dir() / f"{config_name}.json"

        if not config_path.exists():
            # Fallback: try full jurisdiction ID as filename (e.g., city-mill-valley.json)
            alt_path = get_config_dir() / f"{jurisdiction_id}.json"
            if alt_path.exists():
                config_path = alt_path
            else:
                raise FileNotFoundError(
                    f"No extraction config found for {jurisdiction_id} at {config_path} or {alt_path}"
                )
        return cls.from_file(str(config_path))


@runtime_checkable
class DataSource(Protocol):
    """
    Protocol for any data source providing civic data.

    All platform clients should implement this interface to enable
    unified health monitoring in the admin dashboard.
    """

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction, e.g. 'legistar-berkeley'."""
        ...

    @property
    def source_type(self) -> str:
        """Type of source: 'legistar', 'civicclerk', 'proudcity'."""
        ...

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Should include:
        - Connection test (ping API or check website)
        - Count available items without full fetch
        - Capture any errors
        - Record check timestamp and duration

        Returns:
            HealthStatus with all required fields populated
        """
        ...

    def validate(self) -> ValidationResult:
        """
        Validate source configuration and API access before running pipeline.

        Preflight check that fails fast with clear error messages for:
        - Missing or invalid config fields
        - Unreachable API endpoints
        - Missing API keys or credentials

        Returns:
            ValidationResult with is_valid, errors, warnings, and timing
        """
        ...


@dataclass
class Meeting:
    """
    Normalized meeting data structure.

    This is the common format that all extractors should produce,
    compatible with civic-app-schema.json.
    """
    id: str
    title: str
    meeting_datetime: datetime
    jurisdiction_id: str
    meeting_type: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    virtual_url: Optional[str] = None
    agenda_url: Optional[str] = None
    minutes_url: Optional[str] = None
    video_url: Optional[str] = None
    source_platform: str = "unknown"
    source_url: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    extraction_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "meeting_datetime": self.meeting_datetime.isoformat() if self.meeting_datetime else None,
            "jurisdiction_id": self.jurisdiction_id,
            "meeting_type": self.meeting_type,
            "status": self.status,
            "location": self.location,
            "virtual_url": self.virtual_url,
            "agenda_url": self.agenda_url,
            "minutes_url": self.minutes_url,
            "video_url": self.video_url,
            "source_platform": self.source_platform,
            "source_url": self.source_url,
            "extraction_version": self.extraction_version,
        }


@runtime_checkable
class Extractor(Protocol):
    """
    Protocol defining the interface for platform extractors.

    All platform clients should implement this interface.
    """

    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Extract events/meetings from the platform.

        Args:
            days_ahead: Number of days into the future to fetch
            days_past: Number of days into the past to fetch

        Returns:
            List of event dictionaries in platform-native format
        """
        ...

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """
        Normalize a platform-native event to the Meeting format.

        Args:
            event: Event dictionary from get_events()

        Returns:
            Normalized Meeting object
        """
        ...


@runtime_checkable
class BudgetExtractor(Protocol):
    """
    Protocol defining the interface for budget extractors.

    Budget extractors fetch and normalize municipal budget data from
    various sources (PDFs, APIs, scraped documents).
    """

    def extract_budget(
        self,
        fiscal_year: str,
    ) -> List[BudgetLineItem]:
        """
        Extract budget line items for a fiscal year.

        Args:
            fiscal_year: Fiscal year to extract (e.g., "2025-2026")

        Returns:
            List of BudgetLineItem objects
        """
        ...

    def normalize_line_item(self, raw: Dict[str, Any]) -> BudgetLineItem:
        """
        Normalize a raw budget entry to BudgetLineItem format.

        Args:
            raw: Raw budget data from source

        Returns:
            Normalized BudgetLineItem object
        """
        ...


# ========== Election Extractor Protocol ==========


class ContestCandidate(Dict[str, Any]):
    """
    Type documentation for the candidate dict within a contest.

    All election mapper functions (civera_results_to_contest, ca_sos_race_to_contest)
    must produce candidates matching this shape. Consumers like
    derive_officials_from_contests() depend on these fields.

    Required fields:
        id: str             — Unique candidate ID (e.g., "marin-cand-123-jane-doe")
        name: str           — Display name (e.g., "Jane Doe")
        is_winner: bool     — Whether this candidate won the contest

    Optional fields:
        party: str | None   — Party affiliation (e.g., "Dem", "Rep")
        incumbent: bool     — Whether the candidate is an incumbent
        votes_received: int | None — Total votes received
        vote_percentage: float | None — Percentage of votes
        source: str         — Data source (e.g., "civera_election_stats", "ca_sos_results")
    """
    pass


class ContestDict(Dict[str, Any]):
    """
    Type documentation for the normalized contest dict.

    This is the output contract for all election mapper functions.
    Any new election data source must produce dicts matching this shape
    from its mapper function, then pass them to store_election_contests().

    Required fields:
        id: str             — Unique contest ID (e.g., "marin-contest-123")
        title: str          — Contest title (e.g., "U.S. House of Representatives District 2")
        contest_type: str   — One of the ContestType enum values:
                              federal_president, federal_senate, federal_house,
                              state_governor, state_legislature, state_proposition,
                              local_mayor, local_council, local_school_board,
                              local_measure, judicial, other

    Optional fields:
        district_name: str | None — Geographic scope (e.g., "City of San Rafael")
        number_elected: int       — Seats available (default 1; 0 for measures)
        candidates: list          — List of ContestCandidate dicts (for races)
        ballot_measure: dict | None — Ballot measure info (for propositions/measures)
        raw_data: dict            — Full enriched raw response, must include:
                                    "mapped_candidates": list — same as candidates,
                                    persisted in JSONB for downstream consumers
    """
    pass


@runtime_checkable
class ElectionExtractor(Protocol):
    """
    Protocol for election data source clients.

    Election clients fetch election results (contests, candidates, measures)
    from government APIs or websites and normalize them to ContestDict format.

    Unlike meeting extractors, election clients vary widely in their internal
    APIs (GraphQL, REST, web scraping), so this protocol defines the common
    surface: identity, health, and validation. The output contract is the
    ContestDict shape produced by each client's mapper function.

    Adding a new election source:
        1. Create a client class implementing this protocol
        2. Write a mapper function that produces ContestDict dicts
        3. Write an extract_*_to_storage() function that calls the mapper
           and stores via storage.store_election_contests()
        4. Register the source type in clients/factory.py
        5. Add source config to data/extraction/{jurisdiction}.json

    Existing implementations:
        - CiveraElectionStatsClient (GraphQL — county registrar results)
        - CASOSResultsClient (REST — CA Secretary of State)
        - MarinRegistrarResultsClient (extends Civera for Marin County)
    """

    @property
    def platform_name(self) -> str:
        """Platform identifier (e.g., 'civera_election_stats', 'ca_sos_results')."""
        ...

    @property
    def source_id(self) -> str:
        """Unique source identifier (e.g., 'civera-marin', 'ca-sos-general')."""
        ...

    @property
    def source_type(self) -> str:
        """Source type for factory dispatch (e.g., 'civera_election_stats')."""
        ...

    def health(self) -> HealthStatus:
        """Check API availability."""
        ...

    def validate(self) -> ValidationResult:
        """Validate configuration and API access."""
        ...


# ========== Shared Contest Type Classification ==========

VALID_CONTEST_TYPES = frozenset({
    "federal_president", "federal_senate", "federal_house",
    "state_governor", "state_legislature", "state_proposition",
    "local_mayor", "local_council", "local_school_board",
    "local_measure", "judicial", "other",
})

# In-memory cache: title → contest_type. Persists for the process lifetime,
# which covers a single Modal function invocation or local ingestion run.
_classification_cache: Dict[str, str] = {}


def classify_contest_type(title: str, is_ballot_measure: bool = False) -> str:
    """
    Classify a contest type from its title.

    Uses LLM (gpt-4o-mini) for robust classification at ingestion time,
    with an in-memory cache so each unique title is only classified once.
    Falls back to keyword matching if OPENAI_API_KEY is not set or the
    API call fails.

    Args:
        title: Contest title (e.g., "U.S. House of Representatives District 2")
        is_ballot_measure: If True, classify as proposition/measure

    Returns:
        Contest type string (e.g., "federal_house", "state_legislature")
    """
    cache_key = f"{title}|{is_ballot_measure}"
    if cache_key in _classification_cache:
        return _classification_cache[cache_key]

    # Try LLM classification first
    result = _classify_contest_type_llm(title, is_ballot_measure)
    if result is None:
        result = _classify_contest_type_keywords(title, is_ballot_measure)

    _classification_cache[cache_key] = result
    return result


def _classify_contest_type_llm(title: str, is_ballot_measure: bool) -> Optional[str]:
    """Classify using LLM structured output. Returns None if unavailable."""
    import os

    if not os.environ.get("OPENAI_API_KEY"):
        return None

    try:
        from openai import OpenAI

        client = OpenAI()
        types_list = ", ".join(sorted(VALID_CONTEST_TYPES))

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You classify US election contest titles into exactly one category.\n"
                        f"Valid categories: {types_list}\n\n"
                        "Key distinctions:\n"
                        "- federal_senate = US Senate only (\"United States Senator\")\n"
                        "- state_legislature = state-level legislators (\"State Senator\", \"State Senate\", "
                        "\"State Assembly\", \"State Representative\", \"State House\")\n"
                        "- state_governor = governor race (including governor/lieutenant governor tickets), "
                        "not standalone lieutenant governor or other state executives\n"
                        "- other = state executive offices (lieutenant governor, secretary of state, "
                        "attorney general, controller, treasurer, insurance commissioner, "
                        "board of equalization) and anything else that doesn't fit\n\n"
                        "Respond with ONLY the category name, nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Contest title: {title}\n"
                        f"Is ballot measure: {is_ballot_measure}\n"
                        "Category:"
                    ),
                },
            ],
            temperature=0,
            max_tokens=30,
        )

        result = response.choices[0].message.content.strip().lower()
        if result in VALID_CONTEST_TYPES:
            return result

        # LLM returned something unexpected — fall through to keywords
        return None

    except Exception:
        return None


def _classify_contest_type_keywords(title: str, is_ballot_measure: bool) -> str:
    """Keyword-based fallback when LLM is unavailable."""
    if is_ballot_measure:
        title_lower = title.lower()
        if "state" in title_lower or "proposition" in title_lower:
            return "state_proposition"
        return "local_measure"

    title_lower = title.lower()

    # Federal — check "united states" prefix before state-level keywords
    if "president" in title_lower:
        return "federal_president"
    if "united states senator" in title_lower or "u.s. senator" in title_lower:
        return "federal_senate"
    if "representative" in title_lower or "congress" in title_lower or "u.s. house" in title_lower:
        return "federal_house"
    if ("senator" in title_lower or "senate" in title_lower) and "state" not in title_lower:
        return "federal_senate"

    # State
    if "governor" in title_lower:
        return "state_governor"
    if "assembly" in title_lower or "state senator" in title_lower or "state senate" in title_lower:
        return "state_legislature"

    # Local
    if "mayor" in title_lower:
        return "local_mayor"
    if "council" in title_lower or "supervisor" in title_lower:
        return "local_council"
    if "school" in title_lower:
        return "local_school_board"
    if "judge" in title_lower or "justice" in title_lower:
        return "judicial"

    return "other"


class BaseExtractor(ABC):
    """
    Abstract base class for platform extractors.

    Provides common functionality like throttling, retries, and error handling.
    """

    def __init__(self, jurisdiction_id: str):
        """
        Initialize the extractor.

        Args:
            jurisdiction_id: Identifier for the jurisdiction (e.g., "city-berkeley")
        """
        self.jurisdiction_id = jurisdiction_id

    @abstractmethod
    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """Extract events from the platform."""
        pass

    @abstractmethod
    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """Normalize event to Meeting format."""
        pass

    def get_meetings(
        self,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Meeting]:
        """
        Get normalized meetings.

        Convenience method that extracts and normalizes in one call.

        Args:
            days_ahead: Days into future
            days_past: Days into past

        Returns:
            List of normalized Meeting objects
        """
        events = self.get_events(days_ahead=days_ahead, days_past=days_past)
        return [self.normalize_event(e) for e in events]

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform name (e.g., 'legistar', 'civicclerk')."""
        pass
