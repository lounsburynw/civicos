"""
USAspending.gov API Client

Extracts federal awards (grants, contracts, loans, direct payments) from USAspending.gov.
Free API, no key required.

Usage:
    client = USAspendingClient("san-rafael")
    awards = client.get_awards()
    # Returns list of award dicts ready for store_federal_awards()
"""

import logging
import requests
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from civic_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


class USAspendingClient:
    """
    USAspending.gov API client for federal award data.

    Features:
    - Request throttling to avoid rate limits
    - Exponential backoff on errors
    - Pagination handling
    - Schema normalization for civic storage
    """

    # Award type codes for grants, direct payments, and other assistance
    # Contracts: A, B, C, D
    # Grants: 02, 03, 04, 05
    # Direct payments: 06, 10
    # Loans: 07, 08
    # Insurance: 09
    # Other: 11, -1
    GRANT_TYPE_CODES = ["02", "03", "04", "05"]
    DIRECT_PAYMENT_CODES = ["06", "10"]
    ALL_ASSISTANCE_CODES = ["02", "03", "04", "05", "06", "10", "07", "08", "09", "11", "-1"]
    CONTRACT_CODES = ["A", "B", "C", "D"]

    def __init__(
        self,
        jurisdiction_id: str,
        recipient_name: Optional[str] = None,
        recipient_uei: Optional[str] = None,
        zip_codes: Optional[List[str]] = None,
    ):
        """
        Initialize USAspending client.

        Args:
            jurisdiction_id: Civic jurisdiction ID (e.g., "san-rafael")
            recipient_name: Organization name to search (e.g., "City of San Rafael")
            recipient_uei: Unique Entity Identifier for precise matching (e.g., "MC7TGCCKLED5")
            zip_codes: List of zip codes for place of performance filter

        Note:
            recipient_uei is preferred over recipient_name for accuracy.
            Name searches can match unrelated entities (schools, businesses).
        """
        self.jurisdiction_id = jurisdiction_id
        self.recipient_name = recipient_name
        self.recipient_uei = recipient_uei
        self.zip_codes = zip_codes
        self.base_url = "https://api.usaspending.gov/api/v2"
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.min_request_interval = 0.5  # API seems to allow ~2 req/sec

    @property
    def platform_name(self) -> str:
        return "usaspending"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"usaspending-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "usaspending"

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Performs a lightweight check by querying a single award.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            # Quick availability check: query 1 award
            result = self._make_request(
                "search/spending_by_award",
                method="POST",
                json_data={
                    "filters": {
                        "award_type_codes": self.GRANT_TYPE_CODES,
                        "time_period": [{"start_date": "2020-01-01", "end_date": "2025-12-31"}],
                    },
                    "fields": ["Award ID"],
                    "limit": 1,
                    "page": 1,
                },
                retries=1,
            )
            if result and "results" in result:
                is_available = True
                available_count = 1  # Just indicates API is up
                metadata["api_version"] = "v2"

        except Exception as e:
            errors.append(f"Health check error: {str(e)}")
            logger.warning(
                "Health check failed",
                extra={
                    "error": str(e),
                    "jurisdiction_id": self.jurisdiction_id,
                    "platform": self.platform_name,
                },
            )

        check_duration_ms = (time.time() - start_time) * 1000

        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=datetime.utcnow(),
            check_duration_ms=round(check_duration_ms, 2),
            errors=errors,
            last_successful=datetime.utcnow() if is_available else None,
            metadata=metadata,
        )

    def validate(self) -> ValidationResult:
        """
        Validate source configuration and API access.

        Returns:
            ValidationResult with is_valid, errors, warnings, and timing
        """
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        # Check required config - we need some way to filter
        if not self.recipient_name and not self.zip_codes:
            warnings.append(
                "No recipient_name or zip_codes specified - may return large result set"
            )

        # Check API reachability
        try:
            result = self._make_request(
                "search/spending_by_award",
                method="POST",
                json_data={
                    "filters": {
                        "award_type_codes": ["02"],
                        "time_period": [{"start_date": "2024-01-01", "end_date": "2024-12-31"}],
                    },
                    "fields": ["Award ID"],
                    "limit": 1,
                    "page": 1,
                },
                retries=1,
            )
            if result is not None:
                api_reachable = True
            else:
                errors.append(f"Cannot reach USAspending API at {self.base_url}")
        except Exception as e:
            errors.append(f"Cannot reach USAspending API: {str(e)}")
            metadata["connection_error"] = str(e)

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=round(check_duration_ms, 2),
            metadata=metadata,
        )

    def _throttle_request(self):
        """Prevent burst requests."""
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval)
        self.last_request_time = time.time()

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        retries: int = 3,
        timeout: int = 30,
    ) -> Optional[Any]:
        """Make API request with exponential backoff."""
        self._throttle_request()
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries):
            try:
                if method == "POST":
                    response = self.session.post(
                        url,
                        json=json_data,
                        timeout=timeout,
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    response = self.session.get(url, params=params, timeout=timeout)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    wait_time = 2 ** attempt
                    logger.warning(
                        "Retryable HTTP error",
                        extra={
                            "url": url,
                            "endpoint": endpoint,
                            "attempt": attempt + 1,
                            "max_retries": retries,
                            "status_code": response.status_code,
                            "wait_time": wait_time,
                            "jurisdiction_id": self.jurisdiction_id,
                            "platform": self.platform_name,
                        },
                    )
                    if attempt < retries - 1:
                        time.sleep(wait_time)
                    continue
                else:
                    logger.warning(
                        "Non-retryable HTTP error",
                        extra={
                            "url": url,
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "response_text": response.text[:500],
                            "jurisdiction_id": self.jurisdiction_id,
                            "platform": self.platform_name,
                        },
                    )
                    return None

            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning(
                    "Request failed",
                    extra={
                        "url": url,
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "max_retries": retries,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    },
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None

        return None

    def get_awards(
        self,
        award_type_codes: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch federal awards for the jurisdiction.

        Args:
            award_type_codes: Types of awards (default: all assistance types).
                              Must be from same group (grants, direct_payments, or loans).
                              If None, queries all groups separately and combines.
            start_date: Filter start date (YYYY-MM-DD), default 5 years ago
            end_date: Filter end date (YYYY-MM-DD), default today
            limit: Results per page (max 100)
            max_pages: Maximum pages to fetch per group

        Returns:
            List of normalized award dictionaries for store_federal_awards()
        """
        # Default date range: last 5 years
        if start_date is None:
            start_date = datetime.now().replace(year=datetime.now().year - 5).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # If specific codes provided, use them directly
        if award_type_codes is not None:
            return self._fetch_awards_for_codes(
                award_type_codes, start_date, end_date, limit, max_pages
            )

        # Otherwise, query each group separately (API requires same group)
        # Groups: grants, other_financial_assistance (direct payments), loans
        all_awards = []
        groups = [
            (self.GRANT_TYPE_CODES, "grants"),
            (self.DIRECT_PAYMENT_CODES, "direct_payments"),
        ]

        for codes, group_name in groups:
            awards = self._fetch_awards_for_codes(
                codes, start_date, end_date, limit, max_pages
            )
            logger.info(
                f"Fetched {group_name}",
                extra={
                    "count": len(awards),
                    "group": group_name,
                    "jurisdiction_id": self.jurisdiction_id,
                    "platform": self.platform_name,
                },
            )
            all_awards.extend(awards)

        return all_awards

    def _fetch_awards_for_codes(
        self,
        award_type_codes: List[str],
        start_date: str,
        end_date: str,
        limit: int,
        max_pages: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch awards for a specific set of award type codes.

        The USAspending API requires award_type_codes from the same group
        (grants, direct_payments, loans, contracts, etc).

        Args:
            award_type_codes: Award type codes (must be from same group)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            limit: Results per page
            max_pages: Maximum pages to fetch

        Returns:
            List of normalized award dictionaries
        """
        # Build filters
        filters: Dict[str, Any] = {
            "award_type_codes": award_type_codes,
            "time_period": [{"start_date": start_date, "end_date": end_date}],
        }

        # Add recipient filter - prefer UEI for precise matching
        if self.recipient_uei:
            filters["recipient_search_text"] = [self.recipient_uei]
        elif self.recipient_name:
            filters["recipient_search_text"] = [self.recipient_name]

        # Add place of performance filter if zip codes specified
        if self.zip_codes:
            filters["place_of_performance_locations"] = [
                {"country": "USA", "zip": zip_code}
                for zip_code in self.zip_codes
            ]

        # Fields to request - map to our schema
        fields = [
            "Award ID",
            "Award Amount",
            "Award Type",
            "Recipient Name",
            "Recipient DUNS Number",  # Legacy, but may be populated
            "CFDA Number",
            "Start Date",
            "End Date",
            "Period of Performance Start Date",
            "Period of Performance Current End Date",
            "Awarding Agency",
            "Funding Agency",
            "Description",
            "generated_internal_id",
        ]

        all_awards = []
        page = 1

        while page <= max_pages:
            result = self._make_request(
                "search/spending_by_award",
                method="POST",
                json_data={
                    "filters": filters,
                    "fields": fields,
                    "limit": limit,
                    "page": page,
                    "sort": "Award Amount",
                    "order": "desc",
                },
            )

            if result is None:
                logger.warning(
                    "Failed to fetch awards page",
                    extra={
                        "page": page,
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    },
                )
                break

            results = result.get("results", [])
            if not results:
                break

            for raw_award in results:
                normalized = self._normalize_award(raw_award)
                if normalized:
                    all_awards.append(normalized)

            # Check for more pages
            page_meta = result.get("page_metadata", {})
            if not page_meta.get("hasNext", False):
                break

            page += 1

        return all_awards

    def _normalize_award(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize USAspending API response to civic storage format.

        Args:
            raw: Raw award from API response

        Returns:
            Normalized award dict for store_federal_awards(), or None if invalid
        """
        # Extract award ID - prefer generated_internal_id, fallback to Award ID
        award_id = raw.get("generated_internal_id") or raw.get("Award ID")
        if not award_id:
            return None

        # Amount - convert from dollars to cents
        amount_dollars = raw.get("Award Amount")
        if amount_dollars is None:
            return None
        try:
            amount_cents = int(float(amount_dollars) * 100)
        except (ValueError, TypeError):
            return None

        if amount_cents < 0:
            return None

        # Period dates - prefer Period of Performance, fallback to Start/End
        period_start = (
            raw.get("Period of Performance Start Date")
            or raw.get("Start Date")
        )
        period_end = (
            raw.get("Period of Performance Current End Date")
            or raw.get("End Date")
        )

        # Build normalized award
        award = {
            "award_id": str(award_id),
            "cfda_number": raw.get("CFDA Number"),
            "recipient_uei": None,  # USAspending uses DUNS, UEI is newer
            "recipient_name": raw.get("Recipient Name"),
            "amount_cents": amount_cents,
            "period_start": period_start,
            "period_end": period_end,
            "program_name": raw.get("Description"),
            "awarding_agency": raw.get("Awarding Agency"),
            "funding_agency": raw.get("Funding Agency"),
            "award_type": raw.get("Award Type"),
        }

        # Add DUNS to metadata if present
        duns = raw.get("Recipient DUNS Number")
        if duns:
            award["recipient_duns"] = duns

        return award

    def get_awards_by_cfda(
        self,
        cfda_numbers: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch awards filtered by CFDA/Assistance Listing numbers.

        Args:
            cfda_numbers: List of CFDA numbers (e.g., ["20.205", "14.218"])
            start_date: Filter start date (YYYY-MM-DD)
            end_date: Filter end date (YYYY-MM-DD)
            limit: Results per page
            max_pages: Maximum pages to fetch

        Returns:
            List of normalized award dictionaries
        """
        # Default date range
        if start_date is None:
            start_date = datetime.now().replace(year=datetime.now().year - 5).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        filters: Dict[str, Any] = {
            "award_type_codes": self.ALL_ASSISTANCE_CODES,
            "time_period": [{"start_date": start_date, "end_date": end_date}],
            "program_numbers": cfda_numbers,
        }

        # Add recipient filter - prefer UEI for precise matching
        if self.recipient_uei:
            filters["recipient_search_text"] = [self.recipient_uei]
        elif self.recipient_name:
            filters["recipient_search_text"] = [self.recipient_name]

        fields = [
            "Award ID",
            "Award Amount",
            "Award Type",
            "Recipient Name",
            "Recipient DUNS Number",
            "CFDA Number",
            "Start Date",
            "End Date",
            "Period of Performance Start Date",
            "Period of Performance Current End Date",
            "Awarding Agency",
            "Funding Agency",
            "Description",
            "generated_internal_id",
        ]

        all_awards = []
        page = 1

        while page <= max_pages:
            result = self._make_request(
                "search/spending_by_award",
                method="POST",
                json_data={
                    "filters": filters,
                    "fields": fields,
                    "limit": limit,
                    "page": page,
                    "sort": "Award Amount",
                    "order": "desc",
                },
            )

            if result is None:
                break

            results = result.get("results", [])
            if not results:
                break

            for raw_award in results:
                normalized = self._normalize_award(raw_award)
                if normalized:
                    all_awards.append(normalized)

            page_meta = result.get("page_metadata", {})
            if not page_meta.get("hasNext", False):
                break

            page += 1

        return all_awards


def create_san_rafael_usaspending_client() -> USAspendingClient:
    """
    Create USAspending client configured for City of San Rafael.

    Uses the city's UEI (MC7TGCCKLED5) for precise matching,
    avoiding false positives from schools and businesses.

    Returns:
        Configured USAspendingClient
    """
    return USAspendingClient(
        jurisdiction_id="san-rafael",
        recipient_name="CITY OF SAN RAFAEL",  # Fallback for name display
        recipient_uei="MC7TGCCKLED5",  # Precise matching
    )
