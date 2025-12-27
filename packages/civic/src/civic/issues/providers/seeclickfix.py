"""
SeeClickFix provider implementation.

Fetches and normalizes 311 issues from the SeeClickFix API.

Usage:
    from civic.issues.providers.seeclickfix import SeeclickfixProvider

    provider = SeeclickfixProvider()
    issues = provider.get_issues("san-rafael")
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from civic.issues.provider import IssueProvider, NormalizedIssue

logger = logging.getLogger(__name__)


class SeeclickfixProvider:
    """
    SeeClickFix implementation of IssueProvider.

    Fetches operational issues from SeeClickFix's public API and normalizes
    them to the NormalizedIssue format.

    API docs: https://seeclickfix.com/open311/v2/docs
    """

    def __init__(self):
        self.base_url = "https://seeclickfix.com/api/v2"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Civic (civic-issues-provider)",
            "Accept": "application/json",
        })
        self.last_request_time = 0.0
        self.min_request_interval = 0.5  # Respectful rate limiting

    @property
    def provider_name(self) -> str:
        """Provider identifier."""
        return "seeclickfix"

    def _throttle_request(self):
        """Prevent burst requests."""
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval)
        self.last_request_time = time.time()

    def _make_request(
        self, endpoint: str, params: Optional[Dict] = None, retries: int = 3
    ) -> Optional[Any]:
        """Make API request with exponential backoff."""
        self._throttle_request()
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=10)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    wait_time = 2**attempt
                    logger.warning(
                        f"SeeClickFix status {response.status_code}, retrying in {wait_time}s"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"SeeClickFix API error {response.status_code}: {response.text[:200]}"
                    )
                    return None

            except Exception as e:
                logger.error(f"SeeClickFix request failed: {str(e)[:100]}")
                if attempt < retries - 1:
                    time.sleep(2**attempt)
                    continue
                return None

        return None

    def _normalize_issue(self, raw: Dict[str, Any]) -> NormalizedIssue:
        """Convert SeeClickFix API response to NormalizedIssue."""
        # Parse datetime strings
        created_at = None
        if raw.get("created_at"):
            try:
                created_at = datetime.fromisoformat(
                    raw["created_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        updated_at = None
        if raw.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(
                    raw["updated_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        closed_at = None
        if raw.get("closed_at"):
            try:
                closed_at = datetime.fromisoformat(
                    raw["closed_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        # Extract images
        images = []
        if raw.get("media"):
            if raw["media"].get("image_full"):
                images.append(raw["media"]["image_full"])

        # Extract category/issue type
        issue_type = ""
        if raw.get("request_type"):
            issue_type = raw["request_type"].get("title", "")

        # Extract reporter name
        reporter_name = None
        if raw.get("reporter"):
            reporter_name = raw["reporter"].get("name", "Anonymous")
            if reporter_name == "Anonymous":
                reporter_name = None

        return NormalizedIssue(
            provider="seeclickfix",
            external_id=str(raw.get("id", "")),
            title=raw.get("summary", ""),
            description=raw.get("description", ""),
            issue_type=issue_type,
            status=raw.get("status", "open").lower(),
            address=raw.get("address", ""),
            latitude=raw.get("lat"),
            longitude=raw.get("lng"),
            created_at=created_at,
            updated_at=updated_at,
            closed_at=closed_at,
            reporter_name=reporter_name,
            images=images,
            provider_metadata={
                "category_id": raw.get("request_type", {}).get("id"),
                "organization": raw.get("request_type", {}).get("organization", ""),
                "rating": raw.get("rating", 0),
                "comment_count": raw.get("comment_count", 0),
                "html_url": raw.get("html_url"),
                "acknowledged_at": raw.get("acknowledged_at"),
                "reopened_at": raw.get("reopened_at"),
            },
        )

    def get_issues(
        self,
        place_url: str,
        status: Optional[str] = None,
        per_page: int = 100,
        page: int = 1,
        **kwargs,
    ) -> List[NormalizedIssue]:
        """
        Fetch issues from SeeClickFix.

        Args:
            place_url: City identifier (e.g., "san-rafael")
            status: Filter by status ("open", "closed", "acknowledged", None for all)
            per_page: Results per page (default: 100, max: 100)
            page: Page number (default: 1)
            **kwargs: Additional filters (lat, lng, radius, request_types)

        Returns:
            List of NormalizedIssue objects
        """
        params = {
            "place_url": place_url,
            "per_page": min(per_page, 100),
            "page": page,
        }

        if status:
            params["status"] = status

        # Optional geographic filters
        if kwargs.get("lat") and kwargs.get("lng"):
            params["lat"] = kwargs["lat"]
            params["lng"] = kwargs["lng"]
            if kwargs.get("radius"):
                # Convert radius to zoom level
                params["zoom"] = self._radius_to_zoom(kwargs["radius"])

        response = self._make_request("issues", params)

        if not response:
            return []

        # SeeClickFix returns direct array or paginated object
        if isinstance(response, list):
            raw_issues = response
        else:
            raw_issues = response.get("issues", [])

        return [self._normalize_issue(raw) for raw in raw_issues]

    def get_issue(self, issue_id: str) -> Optional[NormalizedIssue]:
        """
        Fetch a single issue by SeeClickFix ID.

        Args:
            issue_id: SeeClickFix issue ID

        Returns:
            NormalizedIssue or None if not found
        """
        response = self._make_request(f"issues/{issue_id}")
        if not response:
            return None
        return self._normalize_issue(response)

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

        Args:
            place_url: City identifier (e.g., "san-rafael")
            status: Filter by status
            max_pages: Maximum pages to fetch (default: 50)
            per_page: Results per page (default: 100)
            **kwargs: Additional filters

        Returns:
            List of all NormalizedIssue objects
        """
        all_issues: List[NormalizedIssue] = []
        page = 1

        while page <= max_pages:
            logger.info(f"Fetching page {page}/{max_pages}...")
            issues = self.get_issues(
                place_url=place_url,
                status=status,
                per_page=per_page,
                page=page,
                **kwargs,
            )

            if not issues:
                logger.info("No more issues to fetch")
                break

            all_issues.extend(issues)
            logger.info(f"  Fetched {len(issues)} issues (total: {len(all_issues)})")

            # Check if we got a full page (more might exist)
            if len(issues) < per_page:
                logger.info("Reached last page")
                break

            page += 1

        return all_issues

    def _radius_to_zoom(self, radius_meters: int) -> int:
        """Convert radius in meters to SeeClickFix zoom level."""
        if radius_meters >= 50000:
            return 10
        elif radius_meters >= 20000:
            return 11
        elif radius_meters >= 10000:
            return 12
        elif radius_meters >= 5000:
            return 13
        elif radius_meters >= 2000:
            return 14
        elif radius_meters >= 1000:
            return 15
        else:
            return 16


# Register provider
def _register():
    """Register this provider with the provider registry."""
    try:
        from civic.issues.providers import register_provider
        register_provider("seeclickfix", SeeclickfixProvider)
    except ImportError:
        pass  # Registry not available


_register()
