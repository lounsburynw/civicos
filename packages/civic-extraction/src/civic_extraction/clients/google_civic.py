"""
Google Civic Information API Client

Fetches election data, voter information, and elected officials from Google's Civic Information API.
Requires a Google API key with Civic Information API enabled.

Usage:
    client = GoogleCivicClient("san-rafael", api_key="...")
    elections = client.get_elections()
    voter_info = client.get_voter_info("1100 4th St, San Rafael, CA 94901")
    officials = client.get_representatives("San Rafael, CA")
"""

import logging
import os
import requests
import time
from datetime import datetime, date
from typing import Dict, List, Optional, Any

from civic_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


class GoogleCivicClient:
    """
    Google Civic Information API client for election and representative data.

    Features:
    - Request throttling (5 req/sec to stay under 25k/day limit)
    - Exponential backoff on errors
    - Schema mapping to civic election models
    - Supports elections, voter info, and representatives endpoints
    """

    BASE_URL = "https://civicinfo.googleapis.com/civicinfo/v2"

    def __init__(
        self,
        jurisdiction_id: str,
        api_key: Optional[str] = None,
    ):
        """
        Initialize Google Civic client.

        Args:
            jurisdiction_id: Civic jurisdiction ID (e.g., "san-rafael")
            api_key: Google API key with Civic Information API enabled.
                     Falls back to GOOGLE_CIVIC_API_KEY or GOOGLE_API_KEY env vars.
        """
        self.jurisdiction_id = jurisdiction_id
        self.api_key = (
            api_key
            or os.environ.get("GOOGLE_CIVIC_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.min_request_interval = 0.2  # 5 req/sec, conservative for 25k/day limit

    @property
    def platform_name(self) -> str:
        return "google_civic"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"google_civic-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "google_civic"

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Performs a lightweight check by querying elections list.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        if not self.api_key:
            errors.append("No API key configured (GOOGLE_CIVIC_API_KEY or GOOGLE_API_KEY)")
            return HealthStatus(
                source_id=self.source_id,
                source_type=self.source_type,
                jurisdiction_id=self.jurisdiction_id,
                is_available=False,
                available_count=0,
                last_checked=datetime.utcnow(),
                check_duration_ms=0,
                errors=errors,
                last_successful=None,
                metadata={},
            )

        try:
            result = self._make_request("elections", retries=1)
            if result and "elections" in result:
                is_available = True
                available_count = len(result.get("elections", []))
                metadata["api_version"] = "v2"
                metadata["election_count"] = available_count

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

        # Check API key is present
        if not self.api_key:
            errors.append(
                "No API key configured. Set GOOGLE_CIVIC_API_KEY or GOOGLE_API_KEY env var."
            )
            config_valid = False
        elif len(self.api_key) < 20:
            errors.append("API key appears invalid (too short)")
            config_valid = False

        # Check API reachability (if key present)
        if config_valid:
            try:
                result = self._make_request("elections", retries=1)
                if result is not None:
                    api_reachable = True
                    metadata["election_count"] = len(result.get("elections", []))
                else:
                    errors.append("Cannot reach Google Civic API - no response")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400:
                    errors.append(f"Invalid API key or Civic Information API not enabled: {e}")
                elif e.response.status_code == 403:
                    errors.append(f"API key forbidden - check quota or enable Civic Information API: {e}")
                else:
                    errors.append(f"Cannot reach Google Civic API: {e}")
                metadata["http_status"] = e.response.status_code
            except Exception as e:
                errors.append(f"Cannot reach Google Civic API: {str(e)}")
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
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """Make API request with exponential backoff."""
        self._throttle_request()
        url = f"{self.BASE_URL}/{endpoint}"

        # Add API key to params
        request_params = {"key": self.api_key}
        if params:
            request_params.update(params)

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=request_params, timeout=timeout)

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
                    # Non-retryable error (400, 403, 404, etc.)
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
                    # Raise for validation to catch specific errors
                    response.raise_for_status()

            except requests.HTTPError:
                raise  # Re-raise HTTP errors for validation
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

    # ==================== Elections API ====================

    def get_elections(self) -> List[Dict[str, Any]]:
        """
        Fetch list of available elections from Google Civic API.

        Returns:
            List of election dictionaries with id, name, electionDay, ocdDivisionId
        """
        result = self._make_request("elections")
        if not result:
            return []

        elections = result.get("elections", [])
        return [self._normalize_election(e) for e in elections]

    def _normalize_election(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize election from API response."""
        election_day = raw.get("electionDay", "")
        try:
            election_date = datetime.strptime(election_day, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            election_date = None

        return {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "election_date": election_date,
            "election_day_raw": election_day,
            "ocd_division_id": raw.get("ocdDivisionId"),
            "source": "google_civic",
            "raw_data": raw,
        }

    # ==================== Voter Info API ====================

    def get_voter_info(
        self,
        address: str,
        election_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch voter information for an address.

        This includes polling locations, contests (races), and ballot measures
        for a specific election.

        Args:
            address: Street address (e.g., "1100 4th St, San Rafael, CA 94901")
            election_id: Google election ID. If None, uses the next election.

        Returns:
            Voter info dict with election, pollingLocations, contests, etc.
            Returns None if no election data available for the address.
        """
        params: Dict[str, Any] = {"address": address}
        if election_id:
            params["electionId"] = election_id

        try:
            result = self._make_request("voterinfo", params=params)
        except requests.HTTPError as e:
            if e.response.status_code == 400:
                # Address not found or no election data
                logger.info(
                    "No voter info available for address",
                    extra={
                        "address": address,
                        "election_id": election_id,
                        "jurisdiction_id": self.jurisdiction_id,
                    },
                )
                return None
            raise

        if not result:
            return None

        return self._normalize_voter_info(result)

    def _normalize_voter_info(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize voter info response."""
        # Extract election
        election = raw.get("election", {})
        election_day = election.get("electionDay", "")
        try:
            election_date = datetime.strptime(election_day, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            election_date = None

        # Extract polling locations
        polling_locations = []
        for loc in raw.get("pollingLocations", []):
            addr = loc.get("address", {})
            polling_locations.append({
                "id": f"poll-{addr.get('locationName', '')}-{addr.get('city', '')}".replace(" ", "-").lower(),
                "name": addr.get("locationName", ""),
                "address": addr.get("line1", ""),
                "city": addr.get("city", ""),
                "state": addr.get("state", ""),
                "zip_code": addr.get("zip", ""),
                "hours": loc.get("pollingHours"),
                "is_early_voting": False,
                "is_dropbox": False,
            })

        # Extract early voting sites
        for loc in raw.get("earlyVoteSites", []):
            addr = loc.get("address", {})
            polling_locations.append({
                "id": f"early-{addr.get('locationName', '')}-{addr.get('city', '')}".replace(" ", "-").lower(),
                "name": addr.get("locationName", ""),
                "address": addr.get("line1", ""),
                "city": addr.get("city", ""),
                "state": addr.get("state", ""),
                "zip_code": addr.get("zip", ""),
                "hours": loc.get("pollingHours"),
                "is_early_voting": True,
                "is_dropbox": False,
            })

        # Extract drop-off locations
        for loc in raw.get("dropOffLocations", []):
            addr = loc.get("address", {})
            polling_locations.append({
                "id": f"drop-{addr.get('locationName', '')}-{addr.get('city', '')}".replace(" ", "-").lower(),
                "name": addr.get("locationName", ""),
                "address": addr.get("line1", ""),
                "city": addr.get("city", ""),
                "state": addr.get("state", ""),
                "zip_code": addr.get("zip", ""),
                "hours": loc.get("pollingHours"),
                "is_early_voting": False,
                "is_dropbox": True,
            })

        # Extract contests
        contests = []
        for c in raw.get("contests", []):
            contest = {
                "id": f"contest-{c.get('office', c.get('referendumTitle', 'unknown'))}-{election_day}".replace(" ", "-").lower(),
                "title": c.get("office") or c.get("referendumTitle", "Unknown"),
                "contest_type": self._map_contest_type(c),
                "district_name": c.get("district", {}).get("name"),
                "candidates": [],
                "ballot_measure": None,
                "number_elected": c.get("numberElected", 1),
            }

            # Candidates
            for cand in c.get("candidates", []):
                contest["candidates"].append({
                    "id": f"cand-{cand.get('name', 'unknown')}-{election_day}".replace(" ", "-").lower(),
                    "name": cand.get("name", "Unknown"),
                    "party": cand.get("party"),
                    "incumbent": False,  # API doesn't provide this
                    "website": cand.get("candidateUrl"),
                    "source": "google_civic",
                })

            # Ballot measure (referendum)
            if c.get("type") == "Referendum":
                contest["ballot_measure"] = {
                    "id": f"measure-{c.get('referendumTitle', 'unknown')}-{election_day}".replace(" ", "-").lower(),
                    "title": c.get("referendumTitle", ""),
                    "description": c.get("referendumText", ""),
                    "measure_type": "referendum",
                    "full_text_url": c.get("referendumUrl"),
                    "arguments_for": [],
                    "arguments_against": [],
                    "source": "google_civic",
                }

            contests.append(contest)

        return {
            "election": {
                "id": election.get("id"),
                "name": election.get("name"),
                "election_date": election_date,
            },
            "normalized_address": raw.get("normalizedInput"),
            "polling_locations": polling_locations,
            "contests": contests,
            "state": raw.get("state", [{}])[0] if raw.get("state") else {},
            "source": "google_civic",
            "raw_data": raw,
        }

    def _map_contest_type(self, contest: Dict[str, Any]) -> str:
        """Map Google contest to ContestType value."""
        office = contest.get("office", "").lower()
        contest_type = contest.get("type", "")
        level = contest.get("level", [""])[0] if contest.get("level") else ""

        if contest_type == "Referendum":
            # Try to determine local vs state measure
            if "local" in level:
                return "local_measure"
            return "state_proposition"

        # Federal
        if "president" in office:
            return "federal_president"
        if "senate" in office and level == "country":
            return "federal_senate"
        if "representative" in office or "congress" in office:
            return "federal_house"

        # State
        if "governor" in office:
            return "state_governor"
        if level == "administrativeArea1":
            return "state_legislature"

        # Local
        if "mayor" in office:
            return "local_mayor"
        if "council" in office or "supervisor" in office:
            return "local_council"
        if "school" in office:
            return "local_school_board"

        # Judicial
        if "judge" in office or "justice" in office or "court" in office:
            return "judicial"

        return "other"

    # ==================== Representatives API ====================

    def get_representatives(
        self,
        address: Optional[str] = None,
        ocd_division_id: Optional[str] = None,
        levels: Optional[List[str]] = None,
        roles: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch elected officials (representatives) for an address or division.

        Args:
            address: Street address or locality (e.g., "San Rafael, CA")
            ocd_division_id: OCD division ID (e.g., "ocd-division/country:us/state:ca/place:san_rafael")
            levels: Filter by level: country, administrativeArea1 (state), administrativeArea2 (county), locality
            roles: Filter by role: headOfState, headOfGovernment, legislatorUpperBody, legislatorLowerBody, etc.

        Returns:
            Representatives dict with offices and officials
        """
        if not address and not ocd_division_id:
            raise ValueError("Either address or ocd_division_id required")

        params: Dict[str, Any] = {}
        if address:
            params["address"] = address
        if levels:
            params["levels"] = levels
        if roles:
            params["roles"] = roles

        # Use different endpoint based on whether we have address or division
        if ocd_division_id:
            endpoint = f"representatives/{ocd_division_id}"
        else:
            endpoint = "representatives"

        try:
            result = self._make_request(endpoint, params=params)
        except requests.HTTPError as e:
            if e.response.status_code in [400, 404]:
                logger.info(
                    "No representatives found for query",
                    extra={
                        "address": address,
                        "ocd_division_id": ocd_division_id,
                        "jurisdiction_id": self.jurisdiction_id,
                        "status_code": e.response.status_code,
                    },
                )
                return None
            raise

        if not result:
            return None

        return self._normalize_representatives(result)

    def _normalize_representatives(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize representatives response."""
        # Build list of officials with their offices
        officials = []
        offices = raw.get("offices", [])
        raw_officials = raw.get("officials", [])

        for office in offices:
            office_name = office.get("name", "")
            levels = office.get("levels", [])
            roles = office.get("roles", [])
            division_id = office.get("divisionId", "")

            # Get officials for this office
            for idx in office.get("officialIndices", []):
                if idx < len(raw_officials):
                    official = raw_officials[idx]
                    officials.append({
                        "id": f"official-{official.get('name', 'unknown')}-{office_name}".replace(" ", "-").lower(),
                        "name": official.get("name", "Unknown"),
                        "seat": office_name,
                        "party": official.get("party"),
                        "phones": official.get("phones", []),
                        "emails": official.get("emails", []),
                        "urls": official.get("urls", []),
                        "photo_url": official.get("photoUrl"),
                        "channels": official.get("channels", []),  # Social media
                        "levels": levels,
                        "roles": roles,
                        "division_id": division_id,
                        "source": "google_civic",
                    })

        return {
            "normalized_address": raw.get("normalizedInput"),
            "divisions": raw.get("divisions", {}),
            "officials": officials,
            "source": "google_civic",
            "raw_data": raw,
        }

    # ==================== High-Level Methods ====================

    def get_election_details(
        self,
        address: str,
        election_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive election details for an address.

        Combines voter info (contests, polling locations) with representative data
        to provide a complete picture of what's on the ballot.

        Args:
            address: Street address (e.g., "1100 4th St, San Rafael, CA 94901")
            election_id: Specific election ID, or None for next election

        Returns:
            Combined election details or None if not available
        """
        voter_info = self.get_voter_info(address, election_id)
        if not voter_info:
            return None

        # Optionally enrich with representative data
        # (representatives are current officials, useful for context)
        representatives = self.get_representatives(address)

        return {
            "election": voter_info.get("election"),
            "address": voter_info.get("normalized_address"),
            "polling_locations": voter_info.get("polling_locations", []),
            "contests": voter_info.get("contests", []),
            "state_info": voter_info.get("state", {}),
            "current_representatives": representatives.get("officials", []) if representatives else [],
            "source": "google_civic",
        }


def create_san_rafael_civic_client(api_key: Optional[str] = None) -> GoogleCivicClient:
    """
    Create Google Civic client configured for City of San Rafael.

    Args:
        api_key: Google API key. If None, uses environment variable.

    Returns:
        Configured GoogleCivicClient
    """
    return GoogleCivicClient(
        jurisdiction_id="san-rafael",
        api_key=api_key,
    )
