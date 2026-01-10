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
        )

    @classmethod
    def from_jurisdiction(cls, jurisdiction_id: str) -> "ExtractionConfig":
        """Load configuration for a jurisdiction from the standard config directory."""
        import os

        # Map jurisdiction_id to config file name
        # e.g., "city-san-rafael" -> "san-rafael.json"
        # e.g., "school-san-rafael" -> "san-rafael-schools.json"
        if jurisdiction_id.startswith("school-"):
            # School districts use "name-schools.json" format
            base_name = jurisdiction_id.replace("school-", "")
            config_name = f"{base_name}-schools"
        else:
            # Cities use "name.json" format
            config_name = jurisdiction_id.replace("city-", "")
        config_dir = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "..", "..",  # Up to project root
            "data", "extraction"
        )
        config_path = os.path.join(config_dir, f"{config_name}.json")
        config_path = os.path.normpath(config_path)

        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"No extraction config found for {jurisdiction_id} at {config_path}"
            )
        return cls.from_file(config_path)


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
