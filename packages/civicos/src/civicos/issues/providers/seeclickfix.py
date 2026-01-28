"""
SeeClickFix provider implementation.

Fetches and normalizes 311 issues from the SeeClickFix API.

Usage:
    from civicos.issues.providers.seeclickfix import SeeclickfixProvider

    provider = SeeclickfixProvider()
    issues = provider.get_issues("san-rafael")
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from civicos.issues.provider import IssueProvider, NormalizedIssue

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

        # Extract raw category name from SeeClickFix (stored in provider_metadata
        # for traceability; issue_type is set by LLM classifier in _classify_issues)
        request_type_title = ""
        if raw.get("request_type"):
            request_type_title = raw["request_type"].get("title", "")

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
            issue_type="",  # Set by _classify_issues() after batch fetch
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
                "request_type": request_type_title,
                "rating": raw.get("rating", 0),
                "comment_count": raw.get("comment_count", 0),
                "html_url": raw.get("html_url"),
                "acknowledged_at": raw.get("acknowledged_at"),
                "reopened_at": raw.get("reopened_at"),
            },
        )

    @staticmethod
    def _classify_issues(issues: List[NormalizedIssue]) -> List[NormalizedIssue]:
        """
        Classify issue types using LLM batch classification.

        Mutates issue_type on each NormalizedIssue in-place and returns the list.
        Falls back gracefully if the classifier is unavailable.
        """
        if not issues:
            return issues

        try:
            from civicos.issues.classify import classify_issue_types_batch

            batch_input = [
                {
                    "id": issue.external_id,
                    "title": issue.title,
                    "description": issue.description,
                }
                for issue in issues
            ]
            classifications = classify_issue_types_batch(batch_input)

            for issue in issues:
                issue.issue_type = classifications.get(issue.external_id, "other")

            classified = sum(1 for i in issues if i.issue_type != "other")
            logger.info(f"Classified {classified}/{len(issues)} issues ({len(issues) - classified} as 'other')")

        except ImportError:
            logger.warning("Issue classifier not available, issue_type will be empty")
        except Exception as e:
            logger.error(f"Issue classification failed: {e}")

        return issues

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

        issues = [self._normalize_issue(raw) for raw in raw_issues]
        return self._classify_issues(issues)

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
        issue = self._normalize_issue(response)
        self._classify_issues([issue])
        return issue

    def get_all_issues(
        self,
        place_url: str,
        status: Optional[str] = None,
        max_pages: int = 50,
        per_page: int = 100,
        **kwargs,
    ) -> List[NormalizedIssue]:
        """
        Fetch all issues with pagination, classifying as a single batch at the end.

        Args:
            place_url: City identifier (e.g., "san-rafael")
            status: Filter by status
            max_pages: Maximum pages to fetch (default: 50)
            per_page: Results per page (default: 100)
            **kwargs: Additional filters

        Returns:
            List of all NormalizedIssue objects with classified issue_type
        """
        all_issues: List[NormalizedIssue] = []
        page = 1

        while page <= max_pages:
            logger.info(f"Fetching page {page}/{max_pages}...")
            # Fetch raw issues without per-page classification
            params = {
                "place_url": place_url,
                "per_page": min(per_page, 100),
                "page": page,
            }
            if status:
                params["status"] = status
            if kwargs.get("lat") and kwargs.get("lng"):
                params["lat"] = kwargs["lat"]
                params["lng"] = kwargs["lng"]
                if kwargs.get("radius"):
                    params["zoom"] = self._radius_to_zoom(kwargs["radius"])

            response = self._make_request("issues", params)
            if not response:
                logger.info("No more issues to fetch")
                break

            if isinstance(response, list):
                raw_issues = response
            else:
                raw_issues = response.get("issues", [])

            if not raw_issues:
                logger.info("No more issues to fetch")
                break

            issues = [self._normalize_issue(raw) for raw in raw_issues]
            all_issues.extend(issues)
            logger.info(f"  Fetched {len(issues)} issues (total: {len(all_issues)})")

            if len(raw_issues) < per_page:
                logger.info("Reached last page")
                break

            page += 1

        # Classify all issues in one batch (more efficient than per-page)
        if all_issues:
            logger.info(f"Classifying {len(all_issues)} issues...")
            self._classify_issues(all_issues)

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
        from civicos.issues.providers import register_provider
        register_provider("seeclickfix", SeeclickfixProvider)
    except ImportError:
        pass  # Registry not available


_register()
