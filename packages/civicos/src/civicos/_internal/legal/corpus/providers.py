"""
CorpusProvider implementations for non-legal corpus types.

Each provider wraps an extraction client and implements the CorpusProvider protocol
(check_for_update, get_fingerprint, fetch_and_store). Clients are passed in as
constructor args — no cross-package imports needed.

Usage:
    from civicos_extraction.clients.proudcity import ProudCityClient
    from civicos._internal.legal.corpus.providers import MeetingCorpusProvider

    client = ProudCityClient(base_url="...", jurisdiction_id="city-san-rafael")
    provider = MeetingCorpusProvider(client, "city-san-rafael")
    result = runner.refresh_corpus(provider)
"""

import logging
from typing import Optional

from .refresh import ChangeSignal, ChangeStatus

logger = logging.getLogger(__name__)


class MeetingCorpusProvider:
    """CorpusProvider for meetings (ProudCity, Granicus, etc.).

    Wraps any client with a get_meetings(days_ahead, days_past) method that
    returns Meeting objects (with .to_dict() or .__dict__).

    Change detection: ProudCity/Granicus have no lightweight "has changed?"
    endpoint, so check_for_update returns UNKNOWN. The YAML interval policy
    is the primary gate; storage handles dedup via temporal versioning.
    """

    corpus_type = "meetings"

    def __init__(
        self,
        client,
        jurisdiction_id: str,
        days_past: int = 30,
        days_ahead: int = 90,
        source_name: str = "proudcity",
    ):
        self.client = client
        self.jurisdiction_id = jurisdiction_id
        self.days_past = days_past
        self.days_ahead = days_ahead
        self.source_name = source_name
        self.last_store_result = None  # MeetingStoreResult for reactive pipelines

    def check_for_update(self, last_fingerprint: Optional[str] = None) -> ChangeSignal:
        """No lightweight change check available — return UNKNOWN to trigger fetch."""
        return ChangeSignal(
            status=ChangeStatus.UNKNOWN,
            message="ProudCity/Granicus has no lightweight change endpoint",
        )

    def get_fingerprint(self) -> str:
        """No stable fingerprint available without a full fetch."""
        return ""

    def fetch_and_store(self, storage) -> int:
        """Fetch meetings from client and store via backend.

        Mirrors the logic in modal_ingest.py:fetch_meetings() —
        client.get_meetings() → convert to dicts → storage.store_meetings().
        """
        meetings = self.client.get_meetings(
            days_ahead=self.days_ahead,
            days_past=self.days_past,
        )

        if not meetings:
            return 0

        # Convert Meeting objects to dicts for storage
        meeting_dicts = []
        for m in meetings:
            if hasattr(m, "to_dict"):
                meeting_dicts.append(m.to_dict())
            elif hasattr(m, "__dict__"):
                meeting_dicts.append(m.__dict__)
            else:
                meeting_dicts.append(m)

        logger.info(
            f"[MEETINGS] {self.jurisdiction_id}: fetched {len(meeting_dicts)} meetings"
        )

        result = storage.store_meetings(self.jurisdiction_id, meeting_dicts)
        self.last_store_result = result  # Preserve for reactive pipeline access
        stored = int(result)

        if hasattr(result, "new_meeting_ids") and result.new_meeting_ids:
            logger.info(f"  New meetings: {result.new_meeting_ids}")
        if hasattr(result, "minutes_appeared") and result.minutes_appeared:
            logger.info(f"  Minutes appeared: {result.minutes_appeared}")

        return stored


class IssueCorpusProvider:
    """CorpusProvider for SeeClickFix 311 issues.

    Wraps a SeeClickFix client and handles pagination + normalization.

    Change detection: SeeClickFix has no "has changed?" endpoint.
    Returns UNKNOWN; interval policy is the primary gate.
    """

    corpus_type = "issues"

    def __init__(
        self,
        client,
        jurisdiction_id: str,
        place_url: Optional[str] = None,
        max_pages: int = 50,
        per_page: int = 100,
        source_name: str = "seeclickfix",
    ):
        self.client = client
        self.jurisdiction_id = jurisdiction_id
        self.source_name = source_name
        self.max_pages = max_pages
        self.per_page = per_page

        # Derive place_url from jurisdiction if not provided
        if place_url:
            self.place_url = place_url
        else:
            self.place_url = jurisdiction_id
            for prefix in ("city-", "county-", "town-"):
                if self.place_url.startswith(prefix):
                    self.place_url = self.place_url[len(prefix):]
                    break

    def check_for_update(self, last_fingerprint: Optional[str] = None) -> ChangeSignal:
        """No lightweight change check — return UNKNOWN to trigger fetch."""
        return ChangeSignal(
            status=ChangeStatus.UNKNOWN,
            message="SeeClickFix has no lightweight change endpoint",
        )

    def get_fingerprint(self) -> str:
        return ""

    def fetch_and_store(self, storage) -> int:
        """Paginate through SeeClickFix issues, normalize, and store.

        Mirrors modal_ingest.py:fetch_issues() — paginate → normalize → store.
        """
        all_issues = []
        current_page = 1

        while current_page <= self.max_pages:
            result = self.client.get_issues(
                place_url=self.place_url,
                per_page=self.per_page,
                page=current_page,
                status=None,  # All statuses
            )

            issues = result.get("issues", [])
            metadata = result.get("metadata", {})

            if metadata.get("error"):
                logger.warning(f"[ISSUES] API error on page {current_page}: {metadata['error']}")
                break

            if not issues:
                break

            # Normalize for storage (matches modal_ingest.py logic)
            for issue in issues:
                issue["provider"] = issue.pop("source", "seeclickfix")
                if "external_id" in issue:
                    issue["external_id"] = str(issue["external_id"])
                if "location" in issue and isinstance(issue["location"], dict):
                    loc = issue.pop("location")
                    issue["address"] = loc.get("address")
                    issue["latitude"] = loc.get("lat")
                    issue["longitude"] = loc.get("lng")

            all_issues.extend(issues)

            if not metadata.get("has_more", False):
                break

            current_page += 1

        if not all_issues:
            return 0

        logger.info(
            f"[ISSUES] {self.jurisdiction_id}: fetched {len(all_issues)} issues "
            f"across {current_page} pages"
        )

        stored = storage.store_issues(self.jurisdiction_id, all_issues)
        return stored


class LegislationCorpusProvider:
    """CorpusProvider for legislation (LegiScan master list sync).

    Wraps a LegiScan client (or raw API key) for master list fetching.

    Change detection: LegiScan master list is 1 API call. We could fingerprint
    on bill count, but legislation changes frequently enough that the weekly
    interval is the real gate. Returns UNKNOWN to always fetch when due.
    """

    corpus_type = "legislation"

    def __init__(
        self,
        client,
        jurisdiction_id: str,
        state_code: str,
        source_name: str = "legiscan",
    ):
        self.client = client
        self.jurisdiction_id = jurisdiction_id
        self.source_name = source_name
        self.state_code = state_code

    def check_for_update(self, last_fingerprint: Optional[str] = None) -> ChangeSignal:
        """Legislation changes frequently — return UNKNOWN when interval is due."""
        return ChangeSignal(
            status=ChangeStatus.UNKNOWN,
            message="Legislation sync always fetches when interval is due",
        )

    def get_fingerprint(self) -> str:
        return ""

    def fetch_and_store(self, storage) -> int:
        """Fetch master list from LegiScan and store via backend.

        Mirrors modal_ingest.py:sync_legislation() —
        getMasterList → normalize → store_legislation() in batches.
        """
        bills_raw = self.client.get_master_list(state=self.state_code)

        if not bills_raw:
            return 0

        # Transform to storage format
        bills_for_storage = []
        for bill in bills_raw:
            bill_number = bill.get("number", "")
            normalized_id = (
                f"{self.state_code.lower()}-{bill_number.lower().replace(' ', '')}"
            )
            bills_for_storage.append({
                "bill_id": normalized_id,
                "bill_number": bill_number,
                "bill_name": bill.get("title", ""),
                "summary": bill.get("description", ""),
                "status": str(bill.get("status", "")),
                "official_url": bill.get("url", ""),
                "legiscan_id": bill.get("bill_id"),
                "last_action": bill.get("last_action", ""),
                "last_action_date": bill.get("last_action_date"),
                "status_date": bill.get("status_date"),
            })

        logger.info(
            f"[LEGISLATION] {self.jurisdiction_id}: fetched {len(bills_for_storage)} bills"
        )

        # Store in batches (matches modal_ingest.py pattern)
        batch_size = 500
        total_stored = 0
        for i in range(0, len(bills_for_storage), batch_size):
            batch = bills_for_storage[i : i + batch_size]
            stored = storage.store_legislation(state=self.state_code, bills=batch)
            total_stored += stored

        return total_stored
