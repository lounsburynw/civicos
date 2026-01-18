"""
California Grants Portal API Client

Extracts state grant opportunities from grants.ca.gov via the data.ca.gov CKAN API.
Free API, no key required. Data updates daily at 8:45pm PT.

Usage:
    client = CaliforniaGrantsClient("san-rafael")
    grants = client.get_grants()
    # Returns list of grant dicts ready for store_state_passthrough_funds()
"""

import logging
import requests
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from civicos_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


class CaliforniaGrantsClient:
    """
    California Grants Portal client for state grant data.

    Uses the data.ca.gov CKAN API to access grant opportunity data.
    The portal contains competitive and first-come grants/loans from July 2020 onward.

    Features:
    - Request throttling to avoid rate limits
    - Exponential backoff on errors
    - Pagination handling via CKAN datastore API
    - Schema normalization for civic storage (state_passthrough_funds)
    """

    # CKAN datastore API endpoint
    BASE_URL = "https://data.ca.gov/api/3/action"
    RESOURCE_ID = "111c8c88-21f6-453c-ae2c-b4785a0624f5"

    # Grant categories relevant to local governments
    # From grants.ca.gov/glossary/
    LOCAL_GOVT_CATEGORIES = [
        "Environment & Water",
        "Health & Human Services",
        "Housing",
        "Parks & Recreation",
        "Transportation",
        "Disaster Prevention & Relief",
        "Employment, Labor & Training",
    ]

    def __init__(
        self,
        jurisdiction_id: str,
        city_name: Optional[str] = None,
        county: Optional[str] = None,
    ):
        """
        Initialize California Grants client.

        Args:
            jurisdiction_id: Civic jurisdiction ID (e.g., "san-rafael")
            city_name: City name for filtering (e.g., "San Rafael")
            county: County name for filtering (e.g., "Marin")
        """
        self.jurisdiction_id = jurisdiction_id
        self.city_name = city_name
        self.county = county
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.min_request_interval = 0.25  # CKAN API is reasonably fast

    @property
    def platform_name(self) -> str:
        return "cagrants"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"cagrants-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "cagrants"

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Performs a lightweight check by querying record count.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            # Quick availability check: get total record count
            result = self._make_request(
                "datastore_search",
                params={
                    "resource_id": self.RESOURCE_ID,
                    "limit": 0,  # Just get metadata
                },
                retries=1,
            )
            if result and result.get("success"):
                is_available = True
                available_count = result.get("result", {}).get("total", 0)
                metadata["ckan_api"] = "data.ca.gov"
                metadata["resource_id"] = self.RESOURCE_ID

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

        # No required config for this client - jurisdiction_id is sufficient
        # But warn if no filters specified
        if not self.city_name and not self.county:
            warnings.append(
                "No city_name or county specified - will return all CA grants. "
                "Filter by eligible geography may be unreliable."
            )

        # Check API reachability
        try:
            result = self._make_request(
                "datastore_search",
                params={
                    "resource_id": self.RESOURCE_ID,
                    "limit": 1,
                },
                retries=1,
            )
            if result and result.get("success"):
                api_reachable = True
                metadata["total_grants"] = result.get("result", {}).get("total", 0)
            else:
                errors.append(f"Cannot reach CA Grants API at {self.BASE_URL}")
        except Exception as e:
            errors.append(f"Cannot reach CA Grants API: {str(e)}")
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
        action: str,
        params: Optional[Dict] = None,
        retries: int = 3,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """Make CKAN API request with exponential backoff."""
        self._throttle_request()
        url = f"{self.BASE_URL}/{action}"

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=timeout)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    wait_time = 2 ** attempt
                    logger.warning(
                        "Retryable HTTP error",
                        extra={
                            "url": url,
                            "action": action,
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
                            "action": action,
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
                        "action": action,
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

    def get_grants(
        self,
        status: Optional[str] = None,
        categories: Optional[List[str]] = None,
        applicant_types: Optional[List[str]] = None,
        limit: int = 100,
        max_records: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch grant opportunities from California Grants Portal.

        Args:
            status: Filter by status ("Active", "Forecasted", "Closed")
            categories: Filter by grant categories
            applicant_types: Filter by eligible applicant types
                            (e.g., "Public Agency", "Nonprofit")
            limit: Records per API request (max 32000 per CKAN)
            max_records: Maximum total records to fetch

        Returns:
            List of normalized grant dictionaries for store_state_passthrough_funds()
        """
        all_grants = []
        offset = 0

        # Build SQL-like filter if needed
        # Note: CA Grants API uses lowercase status values (active, forecasted, closed)
        filters = {}
        if status:
            filters["Status"] = status.lower()

        while offset < max_records:
            params: Dict[str, Any] = {
                "resource_id": self.RESOURCE_ID,
                "limit": min(limit, max_records - offset),
                "offset": offset,
            }

            if filters:
                import json
                params["filters"] = json.dumps(filters)

            result = self._make_request("datastore_search", params=params)

            if result is None or not result.get("success"):
                logger.warning(
                    "Failed to fetch grants page",
                    extra={
                        "offset": offset,
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    },
                )
                break

            records = result.get("result", {}).get("records", [])
            if not records:
                break

            for raw_grant in records:
                # Apply post-fetch filters
                if categories:
                    grant_categories = raw_grant.get("Categories", "")
                    if not any(cat in grant_categories for cat in categories):
                        continue

                if applicant_types:
                    grant_applicants = raw_grant.get("ApplicantType", "")
                    if not any(at in grant_applicants for at in applicant_types):
                        continue

                normalized = self._normalize_grant(raw_grant)
                if normalized:
                    all_grants.append(normalized)

            offset += len(records)
            total = result.get("result", {}).get("total", 0)
            if offset >= total:
                break

        logger.info(
            f"Fetched CA grants",
            extra={
                "count": len(all_grants),
                "jurisdiction_id": self.jurisdiction_id,
                "platform": self.platform_name,
            },
        )

        return all_grants

    def get_grants_for_local_government(
        self,
        status: Optional[str] = "Active",
        limit: int = 100,
        max_records: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch grants available to local government entities.

        Filters for grants where Public Agency is an eligible applicant type.

        Args:
            status: Filter by status (default "Active")
            limit: Records per API request
            max_records: Maximum total records to fetch

        Returns:
            List of normalized grant dictionaries
        """
        return self.get_grants(
            status=status,
            applicant_types=["Public Agency"],
            limit=limit,
            max_records=max_records,
        )

    def _normalize_grant(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize CA Grants Portal response to civic storage format.

        Maps to state_passthrough_funds schema:
        - passthrough_id: Unique identifier for this passthrough record
        - state_agency: California agency administering the grant
        - state_program_name: Name of the grant program
        - state_grant_id: CA's grant identifier
        - local_amount_cents: Amount available (we can't know city-specific)
        - federal_amount_cents: If from federal source
        - period_start/period_end: Application or award period
        - state_fiscal_year: Derived from dates
        - source_url: Link to grant details

        Note: grants.ca.gov tracks grant OPPORTUNITIES, not specific awards.
        The amounts represent total available funding, not city allocations.
        We store these as reference for what's available.

        Args:
            raw: Raw grant from API response

        Returns:
            Normalized grant dict for store_state_passthrough_funds(), or None if invalid
        """
        # Extract grant ID - prefer GrantID, fallback to PortalID
        grant_id = raw.get("GrantID") or raw.get("PortalID")
        if not grant_id:
            return None

        # Generate unique passthrough_id
        portal_id = raw.get("PortalID", "")
        passthrough_id = f"ca-{portal_id}" if portal_id else f"ca-{grant_id}"

        # Extract agency from AgencyDept field
        state_agency = raw.get("AgencyDept", "Unknown CA Agency")

        # Amount - EstAvailFunds is often a string like "$30,000,000"
        amount_str = raw.get("EstAvailFunds", "")
        amount_cents = self._parse_amount(amount_str)

        # Determine funding source
        funding_source = raw.get("FundingSource", "")
        federal_amount_cents = None
        if "Federal" in funding_source or "federal" in funding_source:
            # If federal funding, record as federal amount
            federal_amount_cents = amount_cents

        # Parse dates
        period_start = self._parse_date(raw.get("OpenDate"))
        period_end = self._parse_date(raw.get("ApplicationDeadline"))

        # Extract fiscal year from dates
        state_fiscal_year = None
        if period_start:
            try:
                year = datetime.fromisoformat(period_start).year
                month = datetime.fromisoformat(period_start).month
                # CA fiscal year runs July 1 - June 30
                state_fiscal_year = year if month >= 7 else year - 1
            except (ValueError, TypeError):
                pass

        # Build normalized grant
        grant = {
            "passthrough_id": passthrough_id,
            "state_agency": state_agency,
            "state_program_name": raw.get("Title", ""),
            "state_grant_id": str(grant_id),
            "local_amount_cents": amount_cents or 0,
            "federal_amount_cents": federal_amount_cents,
            "federal_cfda_number": None,  # CA portal doesn't include CFDA
            "federal_award_id": None,  # Not linked to federal award
            "allocation_percentage": None,  # Unknown for opportunity listings
            "period_start": period_start,
            "period_end": period_end,
            "state_fiscal_year": state_fiscal_year,
            "source_url": raw.get("GrantURL") or raw.get("AgencyURL"),
            "notes": raw.get("Purpose") or raw.get("Description"),
            "metadata": {
                "portal_id": portal_id,
                "status": raw.get("Status"),
                "type": raw.get("Type"),
                "categories": raw.get("Categories"),
                "applicant_types": raw.get("ApplicantType"),
                "eligible_geography": raw.get("Geography"),
                "matching_required": raw.get("MatchingFunds"),
                "matching_notes": raw.get("MatchingFundsNotes"),
                "funding_source": funding_source,
                "funding_method": raw.get("FundingMethod"),
                "est_awards": raw.get("EstAwards"),
                "est_amount_per_award": raw.get("EstAmounts"),
                "award_period": raw.get("AwardPeriod"),
                "loi_required": raw.get("LOI"),
                "contact_info": raw.get("ContactInfo"),
                "last_updated": raw.get("LastUpdated"),
            },
        }

        return grant

    def _parse_amount(self, amount_str: str) -> Optional[int]:
        """
        Parse dollar amount string to cents.

        Handles formats like:
        - "$30,000,000"
        - "$1.5 million"
        - "30000000"
        - "$100,000 - $500,000" (takes lower bound)
        """
        if not amount_str:
            return None

        # Handle ranges - take lower bound
        if " - " in amount_str:
            amount_str = amount_str.split(" - ")[0]

        # Remove currency symbols and commas
        amount_str = amount_str.replace("$", "").replace(",", "").strip()

        # Handle "million" notation
        if "million" in amount_str.lower():
            amount_str = amount_str.lower().replace("million", "").strip()
            try:
                return int(float(amount_str) * 1_000_000 * 100)
            except (ValueError, TypeError):
                return None

        # Handle "billion" notation
        if "billion" in amount_str.lower():
            amount_str = amount_str.lower().replace("billion", "").strip()
            try:
                return int(float(amount_str) * 1_000_000_000 * 100)
            except (ValueError, TypeError):
                return None

        try:
            return int(float(amount_str) * 100)
        except (ValueError, TypeError):
            return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        """
        Parse date string to ISO format (YYYY-MM-DD).

        Handles various formats from the API.
        """
        if not date_str:
            return None

        # Already ISO format
        if len(date_str) >= 10 and date_str[4] == "-":
            return date_str[:10]

        # Try common formats
        formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%m/%d/%Y %H:%M:%S",
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str.strip(), fmt)
                return parsed.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue

        return None

    def get_grants_by_agency(
        self,
        agency_name: str,
        status: Optional[str] = None,
        limit: int = 100,
        max_records: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch grants from a specific California agency.

        Args:
            agency_name: Agency name to filter (e.g., "California Department of Housing")
            status: Filter by status ("Active", "Forecasted", "Closed")
            limit: Records per API request
            max_records: Maximum total records to fetch

        Returns:
            List of normalized grant dictionaries
        """
        all_grants = []
        offset = 0

        while offset < max_records:
            params: Dict[str, Any] = {
                "resource_id": self.RESOURCE_ID,
                "limit": min(limit, max_records - offset),
                "offset": offset,
            }

            # Use SQL query for case-insensitive agency search
            sql = f'SELECT * FROM "{self.RESOURCE_ID}" WHERE "AgencyDept" ILIKE \'%{agency_name}%\''
            if status:
                sql += f' AND "Status" = \'{status}\''
            sql += f" LIMIT {limit} OFFSET {offset}"

            result = self._make_request(
                "datastore_search_sql",
                params={"sql": sql},
            )

            if result is None or not result.get("success"):
                # Fallback to basic search if SQL fails
                logger.info("SQL search failed, falling back to basic search")
                break

            records = result.get("result", {}).get("records", [])
            if not records:
                break

            for raw_grant in records:
                normalized = self._normalize_grant(raw_grant)
                if normalized:
                    all_grants.append(normalized)

            offset += len(records)

        return all_grants

    def get_housing_grants(
        self,
        status: Optional[str] = "Active",
        limit: int = 100,
        max_records: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch housing-related grants (LEAP, HHAP, SB2, etc.).

        Key housing programs:
        - LEAP: Local Early Action Planning grants
        - HHAP: Homeless Housing, Assistance and Prevention
        - SB2: Building Homes and Jobs Act (SB 2)
        - CDBG: Community Development Block Grants (federal passthrough)
        - HOME: HOME Investment Partnerships (federal passthrough)

        Args:
            status: Filter by status (default "Active")
            limit: Records per API request
            max_records: Maximum total records to fetch

        Returns:
            List of normalized grant dictionaries
        """
        return self.get_grants(
            status=status,
            categories=["Housing"],
            applicant_types=["Public Agency"],
            limit=limit,
            max_records=max_records,
        )
