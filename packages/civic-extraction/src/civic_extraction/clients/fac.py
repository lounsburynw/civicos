"""
Federal Audit Clearinghouse (FAC) API Client

Extracts Single Audit data from the GSA Federal Audit Clearinghouse.
The FAC contains Schedule of Expenditures of Federal Awards (SEFA) data -
audited records of how cities spent federal funds.

This is the authoritative source for federal grant expenditures, unlike
USAspending which shows award amounts (not actual expenditures).

API Documentation: https://www.fac.gov/api/
Requires free API key from: https://api.data.gov/signup/

Usage:
    client = FederalAuditClearinghouseClient("san-rafael", api_key="...")
    audits = client.get_audits()
    expenditures = client.get_federal_expenditures(report_id="...")
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from civic_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


class FederalAuditClearinghouseClient:
    """
    Federal Audit Clearinghouse API client.

    Features:
    - Search audits by entity name, city, state
    - Retrieve federal award expenditures (SEFA data)
    - Request throttling and exponential backoff
    - Schema normalization for civic storage
    """

    # Production API endpoint
    BASE_URL = "https://api.fac.gov"

    # Staging URL for testing (updated daily)
    STAGING_URL = "https://api-staging.fac.gov"

    def __init__(
        self,
        jurisdiction_id: str,
        api_key: Optional[str] = None,
        auditee_name: Optional[str] = None,
        auditee_city: Optional[str] = None,
        auditee_state: str = "CA",
        use_staging: bool = False,
    ):
        """
        Initialize FAC client.

        Args:
            jurisdiction_id: Civic jurisdiction ID (e.g., "san-rafael")
            api_key: Data.gov API key. If not provided, reads from FAC_API_KEY env var.
            auditee_name: Entity name to search (e.g., "City of San Rafael")
            auditee_city: City name to search (e.g., "San Rafael")
            auditee_state: Two-letter state code (default: "CA")
            use_staging: Use staging API instead of production
        """
        self.jurisdiction_id = jurisdiction_id
        self.api_key = api_key or os.environ.get("FAC_GOV_API_KEY") or os.environ.get("FAC_API_KEY")
        self.auditee_name = auditee_name
        self.auditee_city = auditee_city
        self.auditee_state = auditee_state
        self.base_url = self.STAGING_URL if use_staging else self.BASE_URL
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.min_request_interval = 0.5  # Conservative rate limiting

    @property
    def platform_name(self) -> str:
        return "fac"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"fac-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "fac"

    def health(self) -> HealthStatus:
        """
        Check API availability with a minimal query.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        if not self.api_key:
            errors.append("No FAC API key configured (FAC_API_KEY env var)")
            return HealthStatus(
                source_id=self.source_id,
                source_type=self.source_type,
                jurisdiction_id=self.jurisdiction_id,
                is_available=False,
                available_count=0,
                last_checked=datetime.utcnow(),
                check_duration_ms=0.0,
                errors=errors,
            )

        try:
            # Quick check: fetch 1 record from general endpoint
            result = self._make_request("general", params={"limit": 1})
            if result is not None:
                is_available = True
                available_count = 1
                metadata["api_base"] = self.base_url

        except Exception as e:
            errors.append(f"Health check error: {str(e)}")
            logger.warning(
                "FAC health check failed",
                extra={
                    "error": str(e),
                    "jurisdiction_id": self.jurisdiction_id,
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
        Validate configuration and API access.
        """
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        # Check for API key
        if not self.api_key:
            errors.append(
                "No FAC API key configured. Get one free at https://api.data.gov/signup/ "
                "and set FAC_API_KEY environment variable."
            )
            config_valid = False

        # Check for search criteria
        if not self.auditee_name and not self.auditee_city:
            warnings.append(
                "No auditee_name or auditee_city specified - searches may return too many results"
            )

        # Test API connectivity if we have a key
        if self.api_key:
            try:
                result = self._make_request("general", params={"limit": 1}, retries=1)
                if result is not None:
                    api_reachable = True
                else:
                    errors.append(f"Cannot reach FAC API at {self.base_url}")
            except Exception as e:
                errors.append(f"Cannot reach FAC API: {str(e)}")
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
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
        timeout: int = 30,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Make API request with exponential backoff.

        FAC uses PostgREST, so responses are JSON arrays.

        Args:
            endpoint: API endpoint (e.g., "general", "federal_awards")
            params: Query parameters (PostgREST syntax)
            retries: Number of retry attempts
            timeout: Request timeout in seconds

        Returns:
            List of result dictionaries, or None on failure
        """
        if not self.api_key:
            logger.error("No FAC API key configured")
            return None

        self._throttle_request()
        url = f"{self.base_url}/{endpoint}"

        headers = {
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
        }

        for attempt in range(retries):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    wait_time = 2**attempt
                    logger.warning(
                        "FAC API retryable error",
                        extra={
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                            "wait_time": wait_time,
                        },
                    )
                    if attempt < retries - 1:
                        time.sleep(wait_time)
                    continue
                else:
                    logger.warning(
                        "FAC API error",
                        extra={
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "response": response.text[:500],
                        },
                    )
                    return None

            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning(
                    "FAC request failed",
                    extra={
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "error": str(e),
                    },
                )
                if attempt < retries - 1:
                    time.sleep(2**attempt)
                else:
                    return None

        return None

    def get_audits(
        self,
        audit_year: Optional[int] = None,
        min_year: int = 2016,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search for Single Audits by entity.

        Args:
            audit_year: Specific fiscal year (e.g., 2023). If None, fetches all years >= min_year.
            min_year: Minimum audit year to include (default: 2016, when FAC started)
            limit: Maximum results per request

        Returns:
            List of audit dictionaries from the 'general' endpoint
        """
        # Build PostgREST query parameters
        params: Dict[str, Any] = {
            "limit": limit,
            "order": "audit_year.desc",
        }

        # Filter by audit year
        if audit_year is not None:
            params["audit_year"] = f"eq.{audit_year}"
        else:
            params["audit_year"] = f"gte.{min_year}"

        # Filter by state
        if self.auditee_state:
            params["auditee_state"] = f"eq.{self.auditee_state}"

        # Filter by entity name (case-insensitive partial match)
        if self.auditee_name:
            # PostgREST ilike for case-insensitive matching
            params["auditee_name"] = f"ilike.*{self.auditee_name}*"

        # Filter by city (case-insensitive partial match)
        if self.auditee_city:
            params["auditee_city"] = f"ilike.*{self.auditee_city}*"

        result = self._make_request("general", params=params)

        if result is None:
            logger.warning(
                "Failed to fetch FAC audits",
                extra={
                    "jurisdiction_id": self.jurisdiction_id,
                    "auditee_name": self.auditee_name,
                    "auditee_city": self.auditee_city,
                },
            )
            return []

        logger.info(
            "Fetched FAC audits",
            extra={
                "count": len(result),
                "jurisdiction_id": self.jurisdiction_id,
            },
        )

        return result

    def get_federal_awards(
        self,
        report_id: str,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get federal award expenditures (SEFA data) for a specific audit report.

        This is the core data: actual audited expenditures by CFDA/ALN number.

        Args:
            report_id: Unique identifier for the audit report
            limit: Maximum results per request

        Returns:
            List of federal award dictionaries with CFDA numbers and expenditures
        """
        params = {
            "report_id": f"eq.{report_id}",
            "limit": limit,
            "order": "amount_expended.desc",
        }

        result = self._make_request("federal_awards", params=params)

        if result is None:
            logger.warning(
                "Failed to fetch federal awards for report",
                extra={"report_id": report_id},
            )
            return []

        return result

    def get_passthrough(
        self,
        report_id: str,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get pass-through entity information for a specific audit.

        Shows which state/intermediary agencies passed through federal funds.

        Args:
            report_id: Unique identifier for the audit report
            limit: Maximum results per request

        Returns:
            List of pass-through records
        """
        params = {
            "report_id": f"eq.{report_id}",
            "limit": limit,
        }

        result = self._make_request("passthrough", params=params)

        if result is None:
            return []

        return result

    def get_all_expenditures(
        self,
        audit_year: Optional[int] = None,
        min_year: int = 2016,
    ) -> List[Dict[str, Any]]:
        """
        Get all federal expenditures across all audits for this entity.

        Combines audit search with federal award retrieval.

        Args:
            audit_year: Specific fiscal year, or None for all years >= min_year
            min_year: Minimum audit year

        Returns:
            List of normalized expenditure records
        """
        audits = self.get_audits(audit_year=audit_year, min_year=min_year)

        all_expenditures = []

        for audit in audits:
            report_id = audit.get("report_id")
            if not report_id:
                continue

            awards = self.get_federal_awards(report_id)

            for award in awards:
                normalized = self._normalize_expenditure(award, audit)
                if normalized:
                    all_expenditures.append(normalized)

        logger.info(
            "Fetched all FAC expenditures",
            extra={
                "audit_count": len(audits),
                "expenditure_count": len(all_expenditures),
                "jurisdiction_id": self.jurisdiction_id,
            },
        )

        return all_expenditures

    def _normalize_expenditure(
        self,
        award: Dict[str, Any],
        audit: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize FAC federal award to civic storage format.

        The FAC uses "Assistance Listing Number" (ALN) which replaces CFDA numbers.
        ALN = federal_agency_prefix + "." + federal_award_extension

        Args:
            award: Federal award record from FAC API
            audit: Parent audit record (for context like audit year, entity info)

        Returns:
            Normalized expenditure dict for storage, or None if invalid
        """
        # Build ALN (CFDA) number
        prefix = award.get("federal_agency_prefix")
        extension = award.get("federal_award_extension")

        if not prefix:
            return None

        # ALN format: XX.XXX (e.g., "20.205" for Highway Planning and Construction)
        aln = f"{prefix}.{extension}" if extension else prefix

        # Get expenditure amount
        amount_expended = award.get("amount_expended")
        if amount_expended is None:
            return None

        try:
            # FAC stores amounts as integers (dollars)
            amount_cents = int(float(amount_expended) * 100)
        except (ValueError, TypeError):
            return None

        # Build normalized record
        return {
            # Identifiers
            "report_id": audit.get("report_id"),
            "award_reference": award.get("award_reference"),
            "aln_number": aln,  # Assistance Listing Number (replaces CFDA)
            "cfda_number": aln,  # Keep cfda_number for compatibility

            # Entity info (from audit)
            "auditee_name": audit.get("auditee_name"),
            "auditee_uei": audit.get("auditee_uei"),
            "auditee_ein": audit.get("auditee_ein"),

            # Audit context
            "audit_year": audit.get("audit_year"),
            "fy_start_date": audit.get("fy_start_date"),
            "fy_end_date": audit.get("fy_end_date"),

            # Financial data
            "amount_expended_cents": amount_cents,
            "federal_program_total_cents": (
                int(float(award.get("federal_program_total", 0)) * 100)
                if award.get("federal_program_total")
                else None
            ),
            "cluster_total_cents": (
                int(float(award.get("cluster_total", 0)) * 100)
                if award.get("cluster_total")
                else None
            ),

            # Program details
            "federal_program_name": award.get("federal_program_name"),
            "cluster_name": award.get("cluster_name"),
            "is_major": award.get("is_major") == "Y",
            "is_passthrough_award": award.get("is_passthrough_award") == "Y",

            # Agency info
            "federal_agency_prefix": prefix,

            # Source tracking
            "source": "fac",
            "source_url": f"https://app.fac.gov/dissemination/report/pdf/{audit.get('report_id')}" if audit.get("report_id") else None,
        }


def create_san_rafael_fac_client(
    api_key: Optional[str] = None,
) -> FederalAuditClearinghouseClient:
    """
    Create FAC client configured for San Rafael.

    Args:
        api_key: Optional API key (falls back to FAC_API_KEY env var)

    Returns:
        Configured FederalAuditClearinghouseClient
    """
    return FederalAuditClearinghouseClient(
        jurisdiction_id="san-rafael",
        api_key=api_key,
        auditee_name="City of San Rafael",
        auditee_city="San Rafael",
        auditee_state="CA",
    )
