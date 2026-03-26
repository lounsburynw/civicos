"""
CA Secretary of State Election Results API Client.

Queries api.sos.ca.gov for statewide race results, district races, ballot
measures, and county-level breakdowns.  No authentication required.

Key limitation: the API only serves the current/most-recent election.  There
is no historical access — data is overwritten when a new election is loaded.
Use ``reportType`` to distinguish preliminary ("R") vs certified final ("U").

Usage:
    client = CASOSResultsClient()
    races = client.get_statewide_race("president")
    measures = client.get_ballot_measures()
    county = client.get_county_breakdown("us-rep", county="marin", district=2)
    status = client.get_reporting_status()
"""

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from civicos_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


# ==================== Vote Parsing ====================


def _parse_votes(value: Optional[str]) -> Optional[int]:
    """Parse a vote count string to int.

    Candidate votes are comma-formatted ("2,909,979"), ballot measure votes
    are not ("7453339").  Both forms are handled.
    """
    if value is None:
        return None
    cleaned = str(value).replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _parse_percent(value: Optional[str]) -> Optional[float]:
    """Parse a percentage string ("52.5") to float."""
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    """Parse a generic string integer ("58") to int."""
    if value is None:
        return None
    cleaned = str(value).replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


# ==================== Contest-Type Mapping ====================


# Statewide race endpoint slug → ContestType value
_STATEWIDE_CONTEST_TYPES: Dict[str, str] = {
    "president": "federal_president",
    "us-senate": "federal_senate",
    "governor": "state_governor",
    "lieutenant-governor": "state_legislature",
    "secretary-of-state": "state_legislature",
    "controller": "state_legislature",
    "treasurer": "state_legislature",
    "attorney-general": "state_legislature",
    "insurance-commissioner": "state_legislature",
    "superintendent-of-public-instruction": "state_legislature",
}

# District race endpoint prefix → ContestType value
_DISTRICT_CONTEST_TYPES: Dict[str, str] = {
    "us-rep": "federal_house",
    "state-senate": "state_legislature",
    "state-assembly": "state_legislature",
    "board-of-equalization": "state_legislature",
}


def _map_contest_type_from_endpoint(endpoint: str) -> str:
    """Infer ContestType from the API endpoint path."""
    # Strip leading /returns/
    path = endpoint.lstrip("/")
    if path.startswith("returns/"):
        path = path[len("returns/"):]

    # Ballot measures
    if path.startswith("ballot-measures"):
        return "state_proposition"

    # Statewide
    for slug, ctype in _STATEWIDE_CONTEST_TYPES.items():
        if path.startswith(slug):
            return ctype

    # District
    for prefix, ctype in _DISTRICT_CONTEST_TYPES.items():
        if path.startswith(prefix):
            return ctype

    return "other"


def _slugify(text: str) -> str:
    """Convert text to a URL/ID-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


# ==================== Statewide Race Endpoints ====================


STATEWIDE_RACES: List[str] = [
    "president",
    "us-senate",
    "governor",
    "lieutenant-governor",
    "secretary-of-state",
    "controller",
    "treasurer",
    "attorney-general",
    "insurance-commissioner",
    "superintendent-of-public-instruction",
]


# ==================== Client ====================


class CASOSResultsClient:
    """
    REST client for the CA Secretary of State election results API.

    Base URL: https://api.sos.ca.gov
    Auth: None required.
    Output: JSON by default.

    The API only serves the current/most-recent election — no historical
    access.  Store ``reportType`` to track result finality.
    """

    BASE_URL = "https://api.sos.ca.gov"

    def __init__(
        self,
        jurisdiction_id: str = "state-california",
        base_url: Optional[str] = None,
        request_delay: float = 0.3,
        timeout: int = 30,
    ):
        self.jurisdiction_id = jurisdiction_id
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.request_delay = request_delay
        self.timeout = timeout
        self._session: Optional[Any] = None
        self._last_request_time = 0.0

    @property
    def platform_name(self) -> str:
        return "ca_sos_results"

    @property
    def source_id(self) -> str:
        return f"ca_sos_results-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "ca_sos_results"

    # ---- HTTP plumbing ----

    def _get_session(self):
        import requests as req

        if self._session is None:
            self._session = req.Session()
            self._session.headers.update({
                "Accept": "application/json",
                "User-Agent": "CivicOS/1.0 (election-results)",
            })
        return self._session

    def _throttle(self):
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

    def _get(self, path: str) -> Any:
        """Execute a GET request and return parsed JSON."""
        self._throttle()
        session = self._get_session()
        url = f"{self.base_url}{path}"
        response = session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ---- Statewide Races ----

    def get_statewide_race(self, race_slug: str) -> Dict[str, Any]:
        """Fetch statewide results for a single race.

        Args:
            race_slug: One of STATEWIDE_RACES (e.g., "president", "governor")

        Returns:
            Dict with raceTitle, Reporting, ReportingTime, candidates[]
        """
        return self._get(f"/returns/{race_slug}")

    def get_all_statewide_races(self) -> List[Dict[str, Any]]:
        """Fetch results for all statewide races.

        Returns only races that return data (some may 404 if not on ballot).
        """
        results = []
        for slug in STATEWIDE_RACES:
            try:
                data = self.get_statewide_race(slug)
                results.append({**data, "_endpoint": f"/returns/{slug}"})
            except Exception as e:
                logger.debug(f"Statewide race '{slug}' not available: {e}")
        return results

    # ---- District Races ----

    def get_district_race(
        self,
        race_type: str,
        district: int,
    ) -> Dict[str, Any]:
        """Fetch results for a district race.

        Args:
            race_type: "us-rep", "state-senate", "state-assembly",
                       or "board-of-equalization"
            district: District number

        Returns:
            Dict with raceTitle, Reporting, ReportingTime, candidates[]
        """
        return self._get(f"/returns/{race_type}/district/{district}")

    # ---- Ballot Measures ----

    def get_ballot_measures(self) -> Dict[str, Any]:
        """Fetch all ballot measure results (statewide totals).

        Returns:
            Dict with raceTitle, Reporting, ReportingTime, ballot-measures[]
        """
        return self._get("/returns/ballot-measures")

    def get_ballot_measure(self, prop_number: int) -> Dict[str, Any]:
        """Fetch results for a single proposition.

        Args:
            prop_number: Proposition number

        Returns:
            Dict with measure details
        """
        return self._get(f"/returns/ballot-measures/prop/{prop_number}")

    # ---- County Breakdowns ----

    def get_county_breakdown(
        self,
        race_type: str,
        county: str,
        district: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch county-level breakdown for a race.

        Returns an array: [county_results, districtwide_results].

        Args:
            race_type: Race endpoint (e.g., "president", "us-rep")
            county: County slug (e.g., "marin", "contra-costa")
            district: District number (required for district races)

        Returns:
            List of two dicts: [county_results, statewide_results]
        """
        if district is not None:
            path = f"/returns/{race_type}/district/{district}/county/{county}"
        else:
            path = f"/returns/{race_type}/county/{county}"
        return self._get(path)

    def get_ballot_measures_county(self, county: str) -> Any:
        """Fetch ballot measure results for a specific county.

        Args:
            county: County slug (e.g., "marin")
        """
        return self._get(f"/returns/ballot-measures/county/{county}")

    # ---- Reporting Status ----

    def get_reporting_status(self, election_type: Optional[str] = None) -> Dict[str, Any]:
        """Fetch county reporting status.

        Args:
            election_type: Optional filter ("general", "primary", "state-special")

        Returns:
            Dict keyed by county slug with reporting details
        """
        if election_type:
            return self._get(f"/returns/status/{election_type}")
        return self._get("/returns/status")

    # ---- Health / Validate ----

    def health(self) -> HealthStatus:
        """Check API availability by fetching reporting status."""
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0

        try:
            status = self.get_reporting_status()
            is_available = True
            available_count = len(status)
        except Exception as e:
            errors.append(f"CA SOS API health check failed: {e}")

        check_duration_ms = (time.time() - start_time) * 1000
        now = datetime.now()

        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=now,
            check_duration_ms=round(check_duration_ms, 2),
            errors=errors,
            last_successful=now if is_available else None,
        )

    def validate(self) -> ValidationResult:
        """Validate API is reachable and returning data."""
        start_time = time.time()
        errors: List[str] = []
        api_reachable = False

        try:
            status = self.get_reporting_status()
            if status:
                api_reachable = True
            else:
                errors.append("API returned empty status response")
        except Exception as e:
            errors.append(f"CA SOS API validation failed: {e}")

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=True,
            api_reachable=api_reachable,
            errors=errors,
            warnings=[],
            check_duration_ms=round(check_duration_ms, 2),
            metadata={"base_url": self.base_url},
        )

    # ---- Convenience: Fetch All Available Results ----

    def get_all_results(
        self,
        county: Optional[str] = None,
        districts: Optional[Dict[str, List[int]]] = None,
    ) -> Dict[str, Any]:
        """Fetch all available election results.

        Args:
            county: If set, also fetch county breakdowns for this county
            districts: Dict mapping race_type to list of district numbers
                       e.g., {"us-rep": [2], "state-assembly": [12],
                              "state-senate": [2]}

        Returns:
            Dict with keys: statewide_races, district_races, ballot_measures,
            county_statewide, county_district, county_ballot_measures, status
        """
        result: Dict[str, Any] = {
            "statewide_races": [],
            "district_races": [],
            "ballot_measures": None,
            "county_statewide": [],
            "county_district": [],
            "county_ballot_measures": None,
            "status": None,
        }

        # Statewide races
        result["statewide_races"] = self.get_all_statewide_races()

        # District races
        if districts:
            for race_type, dist_numbers in districts.items():
                for dist_num in dist_numbers:
                    try:
                        data = self.get_district_race(race_type, dist_num)
                        result["district_races"].append({
                            **data,
                            "_endpoint": f"/returns/{race_type}/district/{dist_num}",
                            "_race_type": race_type,
                            "_district": dist_num,
                        })
                    except Exception as e:
                        logger.debug(f"District race {race_type}/{dist_num} not available: {e}")

        # Ballot measures
        try:
            result["ballot_measures"] = self.get_ballot_measures()
        except Exception as e:
            logger.debug(f"Ballot measures not available: {e}")

        # County breakdowns
        if county:
            for race in result["statewide_races"]:
                endpoint = race.get("_endpoint", "")
                slug = endpoint.replace("/returns/", "")
                try:
                    county_data = self.get_county_breakdown(slug, county)
                    result["county_statewide"].append({
                        "_race_slug": slug,
                        "_county": county,
                        "data": county_data,
                    })
                except Exception as e:
                    logger.debug(f"County breakdown {slug}/{county} not available: {e}")

            if districts:
                for race_type, dist_numbers in districts.items():
                    for dist_num in dist_numbers:
                        try:
                            county_data = self.get_county_breakdown(
                                race_type, county, district=dist_num
                            )
                            result["county_district"].append({
                                "_race_type": race_type,
                                "_district": dist_num,
                                "_county": county,
                                "data": county_data,
                            })
                        except Exception as e:
                            logger.debug(
                                f"County district {race_type}/{dist_num}/{county}: {e}"
                            )

            try:
                result["county_ballot_measures"] = self.get_ballot_measures_county(county)
            except Exception as e:
                logger.debug(f"County ballot measures not available: {e}")

        # Status
        try:
            result["status"] = self.get_reporting_status()
        except Exception as e:
            logger.debug(f"Reporting status not available: {e}")

        return result


# ==================== Storage Mappers ====================


@runtime_checkable
class ElectionStorageProtocol(Protocol):
    """Protocol for storage backends that support election operations."""

    def store_elections(
        self,
        jurisdiction_id: str,
        elections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int: ...

    def store_election_contests(
        self,
        election_id: str,
        contests: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int: ...


def _infer_election_type_from_status(status_data: Dict[str, Any]) -> str:
    """Infer election type from the status endpoint response.

    The status keys sometimes contain "general", "primary", etc.
    """
    # If we got the status via a typed endpoint, use that
    # Otherwise fall back to general
    return "general"


def ca_sos_results_to_election(
    reporting_time: Optional[str] = None,
    report_type: Optional[str] = None,
    election_type: str = "general",
) -> Dict[str, Any]:
    """Create an election record for the current CA SOS election.

    Since the API only serves one election at a time with no election ID,
    we derive the ID from the reporting time.

    Args:
        reporting_time: ReportingTime string from any race response
        report_type: "R" (preliminary) or "U" (certified)
        election_type: "general", "primary", or "special"
    """
    # Try to extract a date from ReportingTime (e.g., "December 5, 2025, 1:45 p.m.")
    # Note: ReportingTime is the certification/reporting date, not necessarily the
    # election date.  We store it as a best-effort date since the API provides no
    # explicit election date field.
    election_date = None
    election_year = None
    if reporting_time:
        # Try to parse full date first (e.g., "December 5, 2025, 1:45 p.m.")
        date_match = re.match(
            r"(\w+ \d{1,2}, \d{4})", reporting_time
        )
        if date_match:
            try:
                parsed = datetime.strptime(date_match.group(1), "%B %d, %Y")
                election_date = parsed.date().isoformat()
                election_year = parsed.year
            except ValueError:
                pass
        # Fall back to year extraction
        if election_year is None:
            year_match = re.search(r"20\d{2}", reporting_time)
            if year_match:
                election_year = int(year_match.group())

    # Build a stable election ID
    year_str = str(election_year) if election_year else "current"
    election_id = f"ca-sos-{year_str}-{election_type}"

    status_label = "certified" if report_type == "U" else "preliminary"

    return {
        "id": election_id,
        "name": f"California {election_year or ''} {election_type.title()} Election".strip(),
        "election_date": election_date,
        "election_type": election_type,
        "source": "ca_sos_results",
        "source_url": "https://api.sos.ca.gov",
        "raw_data": {
            "report_type": report_type,
            "reporting_time": reporting_time,
            "status": status_label,
        },
    }


def ca_sos_race_to_contest(
    race_data: Dict[str, Any],
    endpoint: str = "",
) -> Dict[str, Any]:
    """Map a CA SOS candidate race response to contest storage format.

    Args:
        race_data: API response dict with raceTitle, candidates[], etc.
        endpoint: The API endpoint used (for contest type inference)

    Returns:
        Contest dict ready for store_election_contests()
    """
    race_title = race_data.get("raceTitle", "Unknown Race")
    contest_slug = _slugify(race_title)
    contest_id = f"ca-sos-{contest_slug}"

    # Build candidate list
    candidates = []
    for cand in race_data.get("candidates", []):
        name = cand.get("Name", "Unknown")
        candidates.append({
            "id": f"ca-sos-cand-{contest_slug}-{_slugify(name)}",
            "name": name,
            "party": cand.get("Party"),
            "incumbent": bool(cand.get("incumbent")),
            "votes_received": _parse_votes(cand.get("Votes")),
            "vote_percentage": _parse_percent(cand.get("Percent")),
            "is_winner": False,  # API doesn't indicate winner directly
            "source": "ca_sos_results",
        })

    # Determine winner: candidate with highest votes
    if candidates:
        max_votes = max(
            (c["votes_received"] for c in candidates if c["votes_received"] is not None),
            default=None,
        )
        if max_votes is not None and max_votes > 0:
            for c in candidates:
                if c["votes_received"] == max_votes:
                    c["is_winner"] = True
                    break  # Only mark one winner

    # Enrich raw_data with mapped candidates for JSONB persistence
    enriched_raw = {
        **race_data,
        "_endpoint": endpoint,
        "mapped_candidates": candidates,
    }

    return {
        "id": contest_id,
        "title": race_title,
        "contest_type": _map_contest_type_from_endpoint(endpoint),
        "district_name": None,
        "number_elected": 1,
        "candidates": candidates,
        "ballot_measure": None,
        "raw_data": enriched_raw,
    }


def ca_sos_measure_to_contest(
    measure: Dict[str, Any],
) -> Dict[str, Any]:
    """Map a CA SOS ballot measure to contest storage format.

    Args:
        measure: Single measure from ballot-measures response

    Returns:
        Contest dict ready for store_election_contests()
    """
    number = measure.get("Number", "")
    name = measure.get("Name", "Unknown Measure")
    contest_id = f"ca-sos-measure-{number}" if number else f"ca-sos-measure-{_slugify(name)}"

    yes_votes = _parse_votes(measure.get("yesVotes"))
    no_votes = _parse_votes(measure.get("noVotes"))
    yes_pct = _parse_percent(measure.get("yesPercent"))
    no_pct = _parse_percent(measure.get("noPercent"))

    # Determine if passed (yes > no)
    passed = None
    if yes_votes is not None and no_votes is not None:
        passed = yes_votes > no_votes

    ballot_measure = {
        "id": contest_id,
        "title": f"Proposition {number}: {name}" if number else name,
        "description": name,
        "measure_type": "proposition",
        "passed": passed,
        "yes_votes": yes_votes,
        "no_votes": no_votes,
        "yes_percentage": yes_pct,
        "no_percentage": no_pct,
        "source": "ca_sos_results",
    }

    # Build pseudo-candidates for yes/no
    candidates = [
        {
            "id": f"{contest_id}-yes",
            "name": "Yes",
            "votes_received": yes_votes,
            "vote_percentage": yes_pct,
            "is_winner": passed is True,
            "source": "ca_sos_results",
        },
        {
            "id": f"{contest_id}-no",
            "name": "No",
            "votes_received": no_votes,
            "vote_percentage": no_pct,
            "is_winner": passed is False,
            "source": "ca_sos_results",
        },
    ]

    enriched_raw = {
        **measure,
        "mapped_candidates": candidates,
        "mapped_ballot_measure": ballot_measure,
    }

    return {
        "id": contest_id,
        "title": ballot_measure["title"],
        "contest_type": "state_proposition",
        "district_name": None,
        "number_elected": 0,
        "candidates": candidates,
        "ballot_measure": ballot_measure,
        "raw_data": enriched_raw,
    }


# ==================== Extraction to Storage ====================


def extract_ca_sos_results_to_storage(
    client: "CASOSResultsClient",
    storage: ElectionStorageProtocol,
    jurisdiction_id: str = "state-california",
    county: Optional[str] = None,
    districts: Optional[Dict[str, List[int]]] = None,
    election_type: str = "general",
) -> Dict[str, int]:
    """Extract CA SOS election results and store them.

    Args:
        client: CASOSResultsClient instance
        storage: StorageBackend with store_elections + store_election_contests
        jurisdiction_id: Target jurisdiction (default "state-california")
        county: County slug for breakdowns (e.g., "marin")
        districts: District numbers by race type for fetching
        election_type: "general", "primary", or "special"

    Returns:
        Dict with counts: {"elections": N, "contests": M, "candidates": C,
                           "ballot_measures": B}
    """
    total_contests = 0
    total_candidates = 0
    total_measures = 0

    # Fetch all results
    all_data = client.get_all_results(county=county, districts=districts)

    # Determine election metadata from first available race
    reporting_time = None
    report_type = None
    for race in all_data.get("statewide_races", []):
        if race.get("ReportingTime"):
            reporting_time = race["ReportingTime"]
            break

    # Get report type from status
    status_data = all_data.get("status") or {}
    if status_data:
        first_county = next(iter(status_data.values()), {})
        if isinstance(first_county, dict):
            report_type = first_county.get("reportType")

    # Store election
    election = ca_sos_results_to_election(reporting_time, report_type, election_type)
    stored_elections = storage.store_elections(jurisdiction_id, [election])
    election_id = election["id"]

    # Map and store statewide race contests
    statewide_contests = []
    for race in all_data.get("statewide_races", []):
        endpoint = race.get("_endpoint", "")
        contest = ca_sos_race_to_contest(race, endpoint)
        statewide_contests.append(contest)

    if statewide_contests:
        stored = storage.store_election_contests(election_id, statewide_contests)
        total_contests += stored
        total_candidates += sum(len(c.get("candidates", [])) for c in statewide_contests)

    # Map and store district race contests
    district_contests = []
    for race in all_data.get("district_races", []):
        endpoint = race.get("_endpoint", "")
        contest = ca_sos_race_to_contest(race, endpoint)
        district_contests.append(contest)

    if district_contests:
        stored = storage.store_election_contests(election_id, district_contests)
        total_contests += stored
        total_candidates += sum(len(c.get("candidates", [])) for c in district_contests)

    # Map and store ballot measures
    measures_data = all_data.get("ballot_measures") or {}
    measure_list = measures_data.get("ballot-measures", [])
    measure_contests = [ca_sos_measure_to_contest(m) for m in measure_list]

    if measure_contests:
        stored = storage.store_election_contests(election_id, measure_contests)
        total_contests += stored
        total_measures += len(measure_contests)

    logger.info(
        f"CA SOS results: {stored_elections} election, {total_contests} contests, "
        f"{total_candidates} candidates, {total_measures} ballot measures "
        f"for {jurisdiction_id}"
    )

    return {
        "elections": stored_elections,
        "contests": total_contests,
        "candidates": total_candidates,
        "ballot_measures": total_measures,
    }
