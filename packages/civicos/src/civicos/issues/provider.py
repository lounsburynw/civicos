"""
IssueProvider protocol and NormalizedIssue dataclass.

Defines the interface for 311 issue providers (SeeClickFix, PublicStuff, CitySourced, etc.)
with a provider-agnostic issue representation.

Usage:
    class SeeclickfixProvider:
        def get_issues(self, jurisdiction: str, **filters) -> List[NormalizedIssue]:
            ...

        @property
        def provider_name(self) -> str:
            return "seeclickfix"
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class NormalizedIssue:
    """
    Provider-agnostic representation of a 311 issue.

    This dataclass provides a common format for issues from any 311 provider,
    enabling consistent storage, querying, and display across different sources.

    Attributes:
        jurisdiction_id: CivicOS jurisdiction (e.g., "city-san-rafael")
        provider: Source provider name ("seeclickfix", "publicstuff", etc.)
        external_id: Provider's unique issue ID
        title: Issue summary/title
        description: Full issue description
        issue_type: Normalized category (pothole, graffiti, illegal_dumping, etc.)
        status: Normalized status ("open", "closed", "acknowledged")
        address: Location address
        latitude: Geographic latitude
        longitude: Geographic longitude
        created_at: When the issue was reported
        updated_at: When the issue was last updated
        closed_at: When the issue was resolved (if applicable)
        reporter_name: Name of the reporter (if available)
        images: List of image URLs
        provider_metadata: Passthrough for provider-specific fields
    """

    jurisdiction_id: str
    provider: str
    external_id: str
    title: str
    description: str = ""
    issue_type: str = ""
    status: str = "open"
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    reporter_name: Optional[str] = None
    images: List[str] = field(default_factory=list)
    provider_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Generate namespaced ID for federation support.

        Format: issue:{jurisdiction}:{provider}:{external_id}
        Example: issue:city-san-rafael:seeclickfix:12345678
        """
        return f"issue:{self.jurisdiction_id}:{self.provider}:{self.external_id}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        result = asdict(self)
        result["id"] = self.id
        # Convert datetime objects to ISO strings
        for key in ["created_at", "updated_at", "closed_at"]:
            if result[key] is not None and isinstance(result[key], datetime):
                result[key] = result[key].isoformat()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NormalizedIssue":
        """Create from dictionary, parsing datetime strings."""
        # Remove 'id' if present (it's derived)
        data = {k: v for k, v in data.items() if k != "id"}

        # Parse datetime strings
        for key in ["created_at", "updated_at", "closed_at"]:
            if data.get(key) and isinstance(data[key], str):
                try:
                    data[key] = datetime.fromisoformat(data[key].replace("Z", "+00:00"))
                except ValueError:
                    data[key] = None

        return cls(**data)


@runtime_checkable
class IssueProvider(Protocol):
    """
    Protocol for 311 issue providers.

    Implementations provide a consistent interface for fetching issues
    from different 311 platforms (SeeClickFix, PublicStuff, CitySourced, etc.).

    Usage:
        class SeeclickfixProvider:
            def get_issues(self, place_url: str, ...) -> List[NormalizedIssue]:
                # Fetch and normalize issues from SeeClickFix API
                ...

            def get_issue(self, issue_id: str) -> Optional[NormalizedIssue]:
                # Fetch single issue by provider's ID
                ...

            @property
            def provider_name(self) -> str:
                return "seeclickfix"
    """

    @property
    def provider_name(self) -> str:
        """Provider identifier: 'seeclickfix', 'publicstuff', 'citysourced', etc."""
        ...

    def get_issues(
        self,
        place_url: str,
        status: Optional[str] = None,
        per_page: int = 100,
        page: int = 1,
        **kwargs,
    ) -> List[NormalizedIssue]:
        """
        Fetch issues from the provider.

        Args:
            place_url: Location identifier (e.g., "san-rafael")
            status: Filter by status ("open", "closed", "acknowledged", None for all)
            per_page: Results per page (default: 100)
            page: Page number (default: 1)
            **kwargs: Provider-specific filters

        Returns:
            List of NormalizedIssue objects
        """
        ...

    def get_issue(self, issue_id: str) -> Optional[NormalizedIssue]:
        """
        Fetch a single issue by the provider's ID.

        Args:
            issue_id: Provider's issue ID

        Returns:
            NormalizedIssue or None if not found
        """
        ...

    def get_all_issues(
        self,
        place_url: str,
        status: Optional[str] = None,
        max_pages: int = 50,
        per_page: int = 100,
        **kwargs,
    ) -> List[NormalizedIssue]:
        """
        Fetch all issues with pagination.

        Default implementation paginates through get_issues().
        Providers may override for more efficient bulk fetching.

        Args:
            place_url: Location identifier
            status: Filter by status
            max_pages: Maximum pages to fetch
            per_page: Results per page
            **kwargs: Provider-specific filters

        Returns:
            List of all NormalizedIssue objects
        """
        ...
