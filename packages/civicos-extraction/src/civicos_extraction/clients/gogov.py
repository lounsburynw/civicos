"""
GOGov CRM API Client

Extracts 311/service request data from GOGov-powered platforms (FixItMarin, etc.)
using the unofficial `gogov` PyPI package.

Requires staff credentials:
  GOGOV_EMAIL, GOGOV_PASSWORD, GOGOV_SITE (e.g., "marincountyca")

These can be set in .env or passed directly. The city_id is looked up from the
GOGov API if not provided.

Usage:
    client = GoGovClient(
        email="staff@marincounty.gov",
        password="...",
        site="marincountyca",
    )
    issues = client.get_issues(max_results=100)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GoGovClient:
    """GOGov CRM API client for 311 issue extraction.

    Wraps the `gogov` PyPI package (unofficial API client for api.govoutreach.com).
    Requires authenticated access — see module docstring.
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        site: Optional[str] = None,
        city_id: Optional[str] = None,
        jurisdiction_id: str = "",
    ):
        self.email = email or os.environ.get("GOGOV_EMAIL", "")
        self.password = password or os.environ.get("GOGOV_PASSWORD", "")
        self.site = site or os.environ.get("GOGOV_SITE", "")
        self.city_id = city_id or os.environ.get("GOGOV_CITY_ID", "")
        self.jurisdiction_id = jurisdiction_id
        self._client = None

    def _get_client(self):
        """Lazy-initialize the gogov client."""
        if self._client is not None:
            return self._client

        if not self.email or not self.password or not self.site:
            raise RuntimeError(
                "GOGov credentials required. Set GOGOV_EMAIL, GOGOV_PASSWORD, "
                "and GOGOV_SITE in .env or pass them to GoGovClient()."
            )

        try:
            from gogov import Client
        except ImportError:
            raise ImportError(
                "gogov package required. Install with: pip install gogov"
            )

        self._client = Client(
            email=self.email,
            password=self.password,
            site=self.site,
            city_id=self.city_id,
            wait=5,
        )
        return self._client

    def get_topics(self) -> List[Dict[str, Any]]:
        """Get all issue topics/categories."""
        client = self._get_client()
        result = client.get_topics()
        return result.get("data", [])

    def get_issues(self, max_results: Optional[int] = 500) -> List[Dict[str, Any]]:
        """Fetch issues from GOGov, normalized to CivicOS format.

        Returns a list of dicts matching the issues table schema:
        id, jurisdiction_id, provider, external_id, title, description,
        status, latitude, longitude, created_at, updated_at, category.
        """
        client = self._get_client()
        if max_results:
            client.search_limit = max_results

        raw_results = client.search()
        logger.info(f"GOGov returned {len(raw_results)} raw issues")

        issues = []
        for r in raw_results:
            issue = self._normalize_issue(r)
            if issue:
                issues.append(issue)

        return issues

    def _normalize_issue(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a GOGov issue to CivicOS schema."""
        case_id = raw.get("caseId") or raw.get("displayId")
        if not case_id:
            return None

        # Location — both present or both null (no partial coordinates)
        location_point = raw.get("locationPoint", {})
        lat = location_point.get("lat")
        lon = location_point.get("lon")
        if lat is None or lon is None:
            lat = None
            lon = None

        # Dates — normalize to ISO 8601 if parseable
        from datetime import datetime as _dt
        def _normalize_date(val):
            if not val:
                return None
            try:
                return _dt.fromisoformat(val).isoformat()
            except (ValueError, TypeError):
                return val  # Store raw if unparseable

        created = _normalize_date(raw.get("dateEntered"))
        updated = _normalize_date(raw.get("dateLastUpdated"))
        closed = _normalize_date(raw.get("dateClosed"))

        # Status mapping
        status_raw = (raw.get("status") or "").lower()
        if "close" in status_raw or closed:
            status = "closed"
        elif "acknowledge" in status_raw:
            status = "acknowledged"
        else:
            status = "open"

        return {
            "id": f"gogov-{self.jurisdiction_id}-{case_id}",
            "jurisdiction_id": self.jurisdiction_id,
            "provider": "gogov",
            "external_id": str(case_id),
            "title": raw.get("description", "")[:200] or f"Case {case_id}",
            "description": raw.get("description", ""),
            "status": status,
            "latitude": lat,
            "longitude": lon,
            "location": raw.get("location", ""),
            "created_at": created,
            "updated_at": updated or created,
            "closed_at": closed,
            "category": str(raw.get("classificationId", "")),
            "priority": raw.get("priority"),
            "provider_metadata": {
                "case_type": raw.get("caseType"),
                "how_entered": raw.get("howEntered"),
                "department_id": raw.get("departmentId"),
            },
        }

    def close(self):
        """Log out from the GOGov API."""
        if self._client:
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None
