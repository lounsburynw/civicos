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

    @classmethod
    def from_file(cls, path: str) -> "ExtractionConfig":
        """Load configuration from a JSON file."""
        import json
        with open(path, "r") as f:
            data = json.load(f)
        return cls(
            source_id=data["source_id"],
            source_type=data["source_type"],
            jurisdiction_id=data["jurisdiction_id"],
            base_url=data["base_url"],
            auto_discover=data.get("auto_discover", False),
            archives=data.get("archives", {}),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_jurisdiction(cls, jurisdiction_id: str) -> "ExtractionConfig":
        """Load configuration for a jurisdiction from the standard config directory."""
        import os

        # Map jurisdiction_id to config file name
        # e.g., "city-san-rafael" -> "san-rafael.json"
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
