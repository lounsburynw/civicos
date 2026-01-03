"""
California State Controller API Client

Extracts intergovernmental revenue data from the CA State Controller's
ByTheNumbers portal (bythenumbers.sco.ca.gov).

This is a high-value data source because it provides:
- Federal, state, and county intergovernmental revenue
- FY2024 data already available (more recent than FAC's 18-24 month lag)
- 20+ years of historical data (back to FY2003)
- Structured Socrata API (no PDF parsing required)

API Documentation: https://bythenumbers.sco.ca.gov/
Data Set: Cities Annual Financial Data (rrtv-rsj9)

Usage:
    client = CAStateControllerClient("san-rafael", entity_name="San Rafael")
    revenues = client.get_intergovernmental_revenues(fiscal_year=2024)
    summary = client.get_revenue_summary(fiscal_year=2024)
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from civic_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


class CAStateControllerClient:
    """
    California State Controller API client.

    Accesses the Cities Annual Financial Data via Socrata API.
    Provides intergovernmental revenue data (federal, state, county).

    Features:
    - Search by entity name and fiscal year
    - Filter to intergovernmental revenues
    - Request throttling
    - Schema normalization for civic storage
    """

    # Socrata API endpoint for Cities Annual Financial Data
    BASE_URL = "https://bythenumbers.sco.ca.gov/resource/rrtv-rsj9"

    # Intergovernmental category prefixes to filter for
    INTERGOVERNMENTAL_CATEGORIES = [
        "Intergovernmental – Federal",
        "Intergovernmental – State",
        "Intergovernmental - County",
        "Intergovernmental – Other",
        "Intergovernmental – Federal, County, and Other Taxes In-Lieu",
    ]

    # Map form_table codes to revenue types
    FEDERAL_CODES = [
        "FUNC_COMM_DEV_BLOCK_GRANT",  # CDBG
        "FUNC_OTHER_FED_GRANT",  # Other federal grants
        "AID_CONSTRUCTION_FED",  # Federal construction aid
        "OTHR_INTERGOV_FED",  # Other federal intergovernmental
    ]

    STATE_CODES = [
        "FUNC_GAS_TAX",  # Gas tax apportionments
        "FUNC_PEACE_OFFICER_STA_TRAIN",  # POST reimbursements
        "FUNC_PUB_SAFETY_PROP172",  # Prop 172 public safety
        "FUNC_OTHER_STATE_OTHER",  # Other state grants
        "GENREV_HOME_PROPTAX_RELIEF",  # Homeowners property tax relief
        "GENREV_MANDATED_COST",  # Mandated cost reimbursements
        "GENREV_OTHER_STATE",  # Other state revenues
        "AID_CONSTRUCTION_STATE",  # State construction aid
        "IN_LIEU_TAX",  # In-lieu taxes
        "OTHR_INTERGOV_STATE",  # Other state intergovernmental
    ]

    COUNTY_CODES = [
        "FUNC_OTHER_CO_GRANT",  # County grants
        "INTERGOV_COUNTY",  # County intergovernmental
    ]

    def __init__(
        self,
        jurisdiction_id: str,
        entity_name: Optional[str] = None,
        county: Optional[str] = None,
    ):
        """
        Initialize CA State Controller client.

        Args:
            jurisdiction_id: Civic jurisdiction ID (e.g., "san-rafael")
            entity_name: Entity name in SCO database (e.g., "San Rafael")
            county: Optional county name filter (e.g., "Marin")
        """
        self.jurisdiction_id = jurisdiction_id
        self.entity_name = entity_name
        self.county = county
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.min_request_interval = 0.2  # Socrata is fairly permissive

    @property
    def platform_name(self) -> str:
        return "ca_state_controller"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"ca_state_controller-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "ca_state_controller"

    def health(self) -> HealthStatus:
        """
        Check API availability with a minimal query.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        if not self.entity_name:
            errors.append("No entity_name configured")
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
            # Quick check: fetch 1 record for this entity
            result = self._make_request(params={"$limit": 1, "entity_name": self.entity_name})
            if result is not None:
                is_available = True
                available_count = len(result)
                metadata["api_base"] = self.BASE_URL

        except Exception as e:
            errors.append(f"Health check error: {str(e)}")
            logger.warning(
                "CA State Controller health check failed",
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

        # Check for entity name
        if not self.entity_name:
            errors.append("No entity_name configured - required to filter results")
            config_valid = False

        # Test API connectivity
        try:
            result = self._make_request(params={"$limit": 1}, retries=1)
            if result is not None:
                api_reachable = True
            else:
                errors.append(f"Cannot reach CA State Controller API at {self.BASE_URL}")
        except Exception as e:
            errors.append(f"Cannot reach CA State Controller API: {str(e)}")
            metadata["connection_error"] = str(e)

        # Verify entity exists in database
        if config_valid and api_reachable:
            try:
                entity_check = self._make_request(
                    params={"$limit": 1, "entity_name": self.entity_name}
                )
                if not entity_check:
                    warnings.append(f"Entity '{self.entity_name}' not found in database")
                else:
                    metadata["entity_found"] = True
            except Exception as e:
                warnings.append(f"Could not verify entity existence: {str(e)}")

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
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
        timeout: int = 30,
        format: str = "json",
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Make API request with retries.

        Socrata API returns JSON by default.

        Args:
            params: Query parameters (Socrata SoQL syntax)
            retries: Number of retry attempts
            timeout: Request timeout in seconds
            format: Response format ("json" or "csv")

        Returns:
            List of result dictionaries, or None on failure
        """
        self._throttle_request()

        url = f"{self.BASE_URL}.{format}"

        for attempt in range(retries):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=timeout,
                )

                if response.status_code == 200:
                    if format == "json":
                        return response.json()
                    else:
                        # For CSV, return raw text (caller handles parsing)
                        return [{"raw_csv": response.text}]
                elif response.status_code in [429, 500, 502, 503]:
                    wait_time = 2**attempt
                    logger.warning(
                        "CA State Controller API retryable error",
                        extra={
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
                        "CA State Controller API error",
                        extra={
                            "status_code": response.status_code,
                            "response": response.text[:500],
                        },
                    )
                    return None

            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning(
                    "CA State Controller request failed",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                    },
                )
                if attempt < retries - 1:
                    time.sleep(2**attempt)
                else:
                    return None

        return None

    def get_intergovernmental_revenues(
        self,
        fiscal_year: Optional[int] = None,
        min_year: int = 2003,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Get intergovernmental revenue records for this entity.

        Filters to rows where category contains "Intergovernmental".

        Args:
            fiscal_year: Specific fiscal year, or None for all years >= min_year
            min_year: Minimum fiscal year (default 2003, earliest available)
            limit: Maximum results per request

        Returns:
            List of revenue record dictionaries
        """
        # Build Socrata SoQL query
        params: Dict[str, Any] = {
            "$limit": limit,
            "$order": "fiscal_year DESC",
            "entity_name": self.entity_name,
        }

        # Filter by fiscal year
        if fiscal_year is not None:
            params["fiscal_year"] = str(fiscal_year)
        else:
            params["$where"] = f"fiscal_year >= {min_year}"

        # Filter by county if specified
        if self.county:
            params["county"] = self.county

        result = self._make_request(params=params)

        if result is None:
            logger.warning(
                "Failed to fetch CA State Controller revenues",
                extra={
                    "jurisdiction_id": self.jurisdiction_id,
                    "entity_name": self.entity_name,
                },
            )
            return []

        # Filter to intergovernmental categories
        intergovernmental = []
        for row in result:
            category = row.get("category", "")
            if any(ig in category for ig in self.INTERGOVERNMENTAL_CATEGORIES):
                intergovernmental.append(row)

        logger.info(
            "Fetched CA State Controller intergovernmental revenues",
            extra={
                "total_rows": len(result),
                "intergovernmental_rows": len(intergovernmental),
                "jurisdiction_id": self.jurisdiction_id,
            },
        )

        return intergovernmental

    def get_all_revenues(
        self,
        fiscal_year: Optional[int] = None,
        min_year: int = 2003,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Get all revenue records for this entity.

        Returns all revenue types, not just intergovernmental.
        Useful for understanding full revenue picture.

        Args:
            fiscal_year: Specific fiscal year, or None for all years >= min_year
            min_year: Minimum fiscal year
            limit: Maximum results per request

        Returns:
            List of all revenue record dictionaries
        """
        params: Dict[str, Any] = {
            "$limit": limit,
            "$order": "fiscal_year DESC",
            "entity_name": self.entity_name,
            "type": "Revenues",
        }

        if fiscal_year is not None:
            params["fiscal_year"] = str(fiscal_year)
        else:
            params["$where"] = f"fiscal_year >= {min_year}"

        if self.county:
            params["county"] = self.county

        result = self._make_request(params=params)

        if result is None:
            return []

        return result

    def get_revenue_summary(
        self,
        fiscal_year: int,
    ) -> Dict[str, Any]:
        """
        Get summarized intergovernmental revenue by source.

        Args:
            fiscal_year: Fiscal year to summarize

        Returns:
            Dictionary with federal, state, county totals and details
        """
        revenues = self.get_intergovernmental_revenues(fiscal_year=fiscal_year)

        if not revenues:
            return {
                "fiscal_year": fiscal_year,
                "entity_name": self.entity_name,
                "federal_total_cents": 0,
                "state_total_cents": 0,
                "county_total_cents": 0,
                "undetermined_total_cents": 0,
                "total_intergovernmental_cents": 0,
                "details": [],
            }

        federal_total = 0
        state_total = 0
        county_total = 0
        other_total = 0
        details = []

        for row in revenues:
            form_table = row.get("form_table", "")
            value = row.get("value")
            category = row.get("category", "")
            subcategory_1 = row.get("subcategory_1", "")
            line_description = row.get("line_description", "")

            # Parse value (stored as string in Socrata)
            try:
                amount_cents = int(float(value) * 100) if value else 0
            except (ValueError, TypeError):
                amount_cents = 0

            # Skip zero values
            if amount_cents == 0:
                continue

            # Classify by source - check form_table codes first, then subcategory
            # Check order matters: county codes appear under "Intergovernmental – Federal, County, and Other"
            source = "undetermined"
            if form_table in self.COUNTY_CODES:
                source = "county"
                county_total += amount_cents
            elif form_table in self.FEDERAL_CODES:
                source = "federal"
                federal_total += amount_cents
            elif form_table in self.STATE_CODES:
                source = "state"
                state_total += amount_cents
            # Fallback to subcategory_1 text (more specific than category)
            elif "County" in subcategory_1:
                source = "county"
                county_total += amount_cents
            elif "Federal" in subcategory_1:
                source = "federal"
                federal_total += amount_cents
            elif "State" in subcategory_1 or "State" in category:
                source = "state"
                state_total += amount_cents
            else:
                other_total += amount_cents

            details.append(
                {
                    "form_table": form_table,
                    "category": category,
                    "subcategory_1": subcategory_1,
                    "line_description": line_description,
                    "amount_cents": amount_cents,
                    "source": source,
                }
            )

        # Sort details by amount descending
        details.sort(key=lambda x: x["amount_cents"], reverse=True)

        return {
            "fiscal_year": fiscal_year,
            "entity_name": self.entity_name,
            "federal_total_cents": federal_total,
            "state_total_cents": state_total,
            "county_total_cents": county_total,
            "undetermined_total_cents": other_total,
            "total_intergovernmental_cents": (
                federal_total + state_total + county_total + other_total
            ),
            "details": details,
        }

    def get_multi_year_summary(
        self,
        min_year: int = 2020,
        max_year: int = 2024,
    ) -> List[Dict[str, Any]]:
        """
        Get summarized intergovernmental revenue for multiple years.

        Args:
            min_year: Start fiscal year
            max_year: End fiscal year

        Returns:
            List of annual summaries
        """
        summaries = []

        for year in range(max_year, min_year - 1, -1):
            summary = self.get_revenue_summary(fiscal_year=year)
            if summary["total_intergovernmental_cents"] > 0:
                summaries.append(summary)

        return summaries

    def _normalize_revenue(
        self,
        row: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize CA State Controller revenue to civic storage format.

        Args:
            row: Revenue record from API

        Returns:
            Normalized revenue dict for storage, or None if invalid
        """
        form_table = row.get("form_table", "")
        value = row.get("value")

        try:
            amount_cents = int(float(value) * 100) if value else 0
        except (ValueError, TypeError):
            return None

        if amount_cents == 0:
            return None

        # Classify source - check form_table codes first, then subcategory
        category = row.get("category", "")
        subcategory_1 = row.get("subcategory_1", "")
        if form_table in self.COUNTY_CODES:
            source = "county"
        elif form_table in self.FEDERAL_CODES:
            source = "federal"
        elif form_table in self.STATE_CODES:
            source = "state"
        elif "County" in subcategory_1:
            source = "county"
        elif "Federal" in subcategory_1:
            source = "federal"
        elif "State" in subcategory_1 or "State" in category:
            source = "state"
        else:
            source = "undetermined"

        return {
            # Identifiers
            "row_number": row.get("row_number"),
            "form_table": form_table,

            # Entity info
            "entity_name": row.get("entity_name"),
            "county": row.get("county"),

            # Fiscal context
            "fiscal_year": int(row.get("fiscal_year", 0)),

            # Category hierarchy
            "category": row.get("category"),
            "subcategory_1": row.get("subcategory_1"),
            "subcategory_2": row.get("subcategory_2"),
            "line_description": row.get("line_description"),

            # Financial data
            "amount_cents": amount_cents,
            "source": source,

            # Source tracking
            "data_source": "ca_state_controller",
            "source_url": f"https://bythenumbers.sco.ca.gov/resource/rrtv-rsj9",
        }


def create_san_rafael_sco_client() -> CAStateControllerClient:
    """
    Create CA State Controller client configured for San Rafael.

    Returns:
        Configured CAStateControllerClient
    """
    return CAStateControllerClient(
        jurisdiction_id="san-rafael",
        entity_name="San Rafael",
        county="Marin",
    )
