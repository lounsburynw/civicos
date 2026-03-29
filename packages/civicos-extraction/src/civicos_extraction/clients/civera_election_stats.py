"""
Civera ElectionStats Client — Generalized GraphQL client for county election results.

ElectionStats (by Civera) is used by multiple CA counties to publish historical
election results via a GraphQL API. Each county has its own subdomain but shares
the identical schema and endpoint pattern: POST /api/graphql_pr

Known instances:
    - Marin:  pastelections.marincounty.gov  (tenant: marinca, 46 elections, 2010-2025)
    - Sonoma: electionstats.sonomacounty.ca.gov (tenant: sonomaca, 43 elections, 2009-2024)
    - Yolo:   electionstats.elections.yolocounty.gov (tenant: yoloca, 52 elections, 1997-2025)

Usage:
    client = CiveraElectionStatsClient(
        jurisdiction_id="county-sonoma",
        graphql_url="https://electionstats.sonomacounty.ca.gov/api/graphql_pr",
        county_slug="sonoma",
    )
    elections = client.list_elections()
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from civicos_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


# Registry of known Civera ElectionStats instances in California
CIVERA_INSTANCES: Dict[str, Dict[str, str]] = {
    "marin": {
        "graphql_url": "https://pastelections.marincounty.gov/api/graphql_pr",
        "tenant": "marinca",
        "county_name": "Marin County",
    },
    "sonoma": {
        "graphql_url": "https://electionstats.sonomacounty.ca.gov/api/graphql_pr",
        "tenant": "sonomaca",
        "county_name": "Sonoma County",
    },
    "yolo": {
        "graphql_url": "https://electionstats.elections.yolocounty.gov/api/graphql_pr",
        "tenant": "yoloca",
        "county_name": "Yolo County",
    },
}


# Pseudo-candidate values to filter out from results
_PSEUDO_CANDIDATES = {"TOTAL_VOTES", "TOTAL_BALLOTS", "PSEUDOCANDIDATE", "VOTER_STAT"}


class CiveraElectionStatsClient:
    """
    Generalized GraphQL client for Civera ElectionStats county election results.

    Three-query pattern:
        1. list_elections()     — all elections in a year range
        2. list_contests()      — contests + candidates for one election
        3. get_precinct_data()  — precinct-level vote breakdowns for one contest
    """

    def __init__(
        self,
        jurisdiction_id: str,
        graphql_url: str,
        county_slug: str = "",
        request_delay: float = 0.5,
        timeout: int = 30,
    ):
        self.jurisdiction_id = jurisdiction_id
        self.graphql_url = graphql_url
        self.county_slug = county_slug
        self.request_delay = request_delay
        self.timeout = timeout
        self._session: Optional[Any] = None
        self._last_request_time = 0.0

    @classmethod
    def from_county(
        cls,
        county_slug: str,
        jurisdiction_id: Optional[str] = None,
        **kwargs: Any,
    ) -> "CiveraElectionStatsClient":
        """Create a client for a known county from the CIVERA_INSTANCES registry."""
        instance = CIVERA_INSTANCES.get(county_slug)
        if not instance:
            known = ", ".join(sorted(CIVERA_INSTANCES.keys()))
            raise ValueError(
                f"Unknown Civera county: {county_slug!r}. Known: {known}"
            )
        jid = jurisdiction_id or f"county-{county_slug}"
        return cls(
            jurisdiction_id=jid,
            graphql_url=instance["graphql_url"],
            county_slug=county_slug,
            **kwargs,
        )

    @property
    def platform_name(self) -> str:
        return "civera_election_stats"

    @property
    def source_id(self) -> str:
        return f"civera_election_stats-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "civera_election_stats"

    def _get_session(self):
        import requests as req
        if self._session is None:
            self._session = req.Session()
            self._session.headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json",
            })
        return self._session

    def _throttle(self):
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

    def _graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query and return the data payload."""
        self._throttle()
        session = self._get_session()

        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = session.post(
            self.graphql_url,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()

        if "errors" in result:
            raise RuntimeError(f"GraphQL errors: {result['errors']}")

        return result.get("data", {})

    # ---- Query 1: List Elections ----

    def list_elections(
        self,
        from_year: int = 2010,
        to_year: int = 2026,
    ) -> List[Dict[str, Any]]:
        """
        List all elections in a year range.

        Returns list of dicts with keys: id, name, group, count.
        """
        query = """
        query ListElections($from: Int!, $to: Int!) {
          searchSuggestions(filters: {
            global: { years: { from: $from, to: $to } }
            voterStats: false
            specialElectionsOnly: false
            stages: []
          }) {
            events { id name group count }
          }
        }
        """
        data = self._graphql(query, {"from": from_year, "to": to_year})
        events = data.get("searchSuggestions", {}).get("events", [])
        logger.info(f"Listed {len(events)} elections ({from_year}-{to_year}) from {self.graphql_url}")
        return events

    # ---- Query 2: List Contests for an Election ----

    def list_contests(
        self,
        event_id: int,
        page: int = 1,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List contests and candidates for a single election.

        Paginates automatically. Returns all contests across all pages.
        """
        query = """
        query ListContests($eventId: Int!, $page: Int!, $size: Int!) {
          search(filters: {
            global: { events: [$eventId] }
            contests: { candidates: [], divisions: [], offices: [] }
            ballotQuestions: { text: "", types: [], number: "", divisions: [] }
            voterStats: false
            specialElectionsOnly: false
            stages: []
          }, pagination: { page: $page, size: $size }) {
            results {
              id name
              office { id name }
              division { id displayName divisionType { name } }
              event { id startDate type { name } }
              candidates {
                displayName nVotes pctCandidateVotes
                candidate { pseudocandidate }
                isWinner
                party { name }
              }
              ballotQuestionId
              ballotQuestion { questionText type { name } questionNumber }
              nSeats hasWinners
            }
          }
        }
        """
        all_results: List[Dict[str, Any]] = []
        current_page = page

        while True:
            data = self._graphql(query, {
                "eventId": event_id,
                "page": current_page,
                "size": page_size,
            })
            results = data.get("search", {}).get("results", [])
            if not results:
                break
            all_results.extend(results)
            if len(results) < page_size:
                break
            current_page += 1

        logger.info(f"Listed {len(all_results)} contests for event {event_id}")
        return all_results

    # ---- Query 3: Precinct-Level Data ----

    def get_precinct_data(self, contest_id: int) -> Dict[str, Any]:
        """
        Get precinct-level vote breakdowns for a contest.

        Returns dict with candidates, voteChannels, and divisions (precincts).
        """
        query = """
        query PrecinctData($contestId: Int!) {
          contestGranularData(
            contestId: $contestId
            voteChannels: true
            splitParty: false
          ) {
            candidates {
              candidateId
              candidate { id displayName pseudocandidate }
              nVotes pctCandidateVotes isWinner
              voteChannelId
            }
            voteChannels { id name }
            divisions {
              division { id name displayName divisionTypeName }
              granularRow { candidateId voteChannelId votes pct winner }
              children {
                division { id name displayName divisionTypeName }
                granularRow { candidateId voteChannelId votes pct winner }
              }
            }
          }
        }
        """
        data = self._graphql(query, {"contestId": contest_id})
        return data.get("contestGranularData", {})

    # ---- Health / Validate ----

    def health(self) -> HealthStatus:
        """Check API availability by listing elections."""
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0

        try:
            events = self.list_elections(from_year=2024, to_year=2026)
            is_available = True
            available_count = len(events)
        except Exception as e:
            errors.append(f"GraphQL health check failed: {e}")

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
        """Validate GraphQL endpoint is reachable and returns data."""
        start_time = time.time()
        errors: List[str] = []
        api_reachable = False

        try:
            events = self.list_elections(from_year=2024, to_year=2025)
            if events:
                api_reachable = True
            else:
                errors.append("API returned no elections for 2024-2025 range")
        except Exception as e:
            errors.append(f"GraphQL validation failed: {e}")

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=True,
            api_reachable=api_reachable,
            errors=errors,
            warnings=[],
            check_duration_ms=round(check_duration_ms, 2),
            metadata={"graphql_url": self.graphql_url},
        )

    # ---- Convenience: Fetch all results for an election ----

    def get_election_results(
        self,
        event_id: int,
        division_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch complete election results: contests + candidates, optionally
        filtered to a specific division (e.g., 'City of San Rafael').
        """
        contests_raw = self.list_contests(event_id)

        contests = []
        for c in contests_raw:
            division = c.get("division", {})
            if division_filter:
                div_name = division.get("displayName", "")
                if division_filter.lower() not in div_name.lower():
                    continue

            real_candidates = []
            for cand in c.get("candidates", []):
                pseudo = (cand.get("candidate") or {}).get("pseudocandidate")
                if pseudo in _PSEUDO_CANDIDATES:
                    continue
                real_candidates.append(cand)

            contests.append({
                **c,
                "candidates": real_candidates,
            })

        election_info = {}
        if contests:
            event = contests[0].get("event", {})
            election_info = {
                "id": event.get("id"),
                "start_date": event.get("startDate"),
                "type": (event.get("type") or {}).get("name"),
            }

        return {
            "election_info": election_info,
            "contests": contests,
            "total_contests": len(contests),
        }


# ==================== Storage Mappers ====================


def _infer_election_type_from_name(name: str) -> str:
    """Infer election type from election event name."""
    name_lower = name.lower()
    if "primary" in name_lower:
        return "primary"
    if "special" in name_lower or "parcel tax" in name_lower:
        return "special"
    if "recall" in name_lower:
        return "recall"
    if "runoff" in name_lower:
        return "runoff"
    return "general"


def _parse_election_date(start_date: Optional[str]) -> Optional[str]:
    """Parse ISO date string from GraphQL startDate field."""
    if not start_date:
        return None
    try:
        dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except (ValueError, AttributeError):
        return start_date[:10] if start_date and len(start_date) >= 10 else None


def _map_contest_type(contest: Dict[str, Any]) -> str:
    """Map GraphQL contest to ContestType value.

    Delegates to the shared classify_contest_type() for keyword matching,
    with Civera-specific handling for ballot questions and division types.
    """
    from civicos_extraction.clients.base import classify_contest_type

    office_name = (contest.get("office") or {}).get("name", "")
    division_type = ((contest.get("division") or {}).get("divisionType") or {}).get("name", "").lower()

    # Civera-specific: ballot questions have a dedicated field
    if contest.get("ballotQuestionId"):
        if "school" in division_type or "school" in office_name.lower():
            return "local_measure"
        if "state" in division_type:
            return "state_proposition"
        return "local_measure"

    # Civera-specific: school board detection via division type
    if "school" in division_type and "school" not in office_name.lower():
        return "local_school_board"

    # Delegate to shared keyword matcher
    return classify_contest_type(office_name)


def civera_results_to_election(
    event: Dict[str, Any],
    county_slug: str,
    graphql_url: str,
    election_date: Optional[str] = None,
    election_type_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Map a Civera ElectionStats event to storage format.

    Args:
        event: Event dict from list_elections() (keys: id, name, group, count)
        county_slug: County identifier (e.g., "marin", "sonoma", "yolo")
        graphql_url: Base URL for source_url construction
        election_date: ISO date if known (from contest data)
        election_type_name: Type name from contest event data
    """
    name = event.get("name", "Unknown Election")
    event_id = event.get("id")

    e_type = "general"
    if election_type_name:
        e_type = _infer_election_type_from_name(election_type_name)
    else:
        e_type = _infer_election_type_from_name(name)

    base_url = graphql_url.rsplit("/api/", 1)[0]

    return {
        "id": f"{county_slug}-results-{event_id}",
        "name": name,
        "election_date": election_date,
        "election_type": e_type,
        "source": "civera_election_stats",
        "source_url": f"{base_url}/?e={event_id}",
        "raw_data": event,
    }


def civera_results_to_contest(
    contest: Dict[str, Any],
    county_slug: str,
) -> Dict[str, Any]:
    """
    Map a Civera ElectionStats contest result to storage format.

    Args:
        contest: Contest dict from list_contests() (already pseudo-filtered)
        county_slug: County identifier for ID namespacing
    """
    contest_id = contest.get("id")
    office = contest.get("office") or {}
    division = contest.get("division") or {}
    ballot_q = contest.get("ballotQuestion")

    title = office.get("name") or contest.get("name", "Unknown Contest")
    if ballot_q:
        q_num = ballot_q.get("questionNumber", "")
        q_text = ballot_q.get("questionText", "")
        title = f"Measure {q_num}: {q_text}" if q_num else q_text

    candidates = []
    for cand in contest.get("candidates", []):
        candidates.append({
            "id": f"{county_slug}-cand-{contest_id}-{cand.get('displayName', '').replace(' ', '-').lower()[:40]}",
            "name": cand.get("displayName", "Unknown"),
            "party": (cand.get("party") or {}).get("name"),
            "votes_received": cand.get("nVotes"),
            "vote_percentage": cand.get("pctCandidateVotes"),
            "is_winner": bool(cand.get("isWinner")),
            "source": "civera_election_stats",
        })

    ballot_measure = None
    if ballot_q:
        yes_cand = next((c for c in candidates if c["name"].lower() == "yes"), None)
        no_cand = next((c for c in candidates if c["name"].lower() == "no"), None)
        ballot_measure = {
            "id": f"{county_slug}-measure-{contest_id}",
            "title": title,
            "description": ballot_q.get("questionText", ""),
            "measure_type": (ballot_q.get("type") or {}).get("name", "measure"),
            "full_text": None,
            "full_text_url": None,
            "fiscal_impact": None,
            "arguments_for": [],
            "arguments_against": [],
            "passed": bool(yes_cand and yes_cand.get("is_winner")),
            "yes_votes": yes_cand["votes_received"] if yes_cand else None,
            "no_votes": no_cand["votes_received"] if no_cand else None,
            "yes_percentage": yes_cand["vote_percentage"] if yes_cand else None,
            "no_percentage": no_cand["vote_percentage"] if no_cand else None,
            "source": "civera_election_stats",
        }

    enriched_raw = {
        **contest,
        "mapped_candidates": candidates,
        "mapped_ballot_measure": ballot_measure,
    }

    return {
        "id": f"{county_slug}-contest-{contest_id}",
        "title": title,
        "contest_type": _map_contest_type(contest),
        "district_name": division.get("displayName"),
        "number_elected": contest.get("nSeats", 1),
        "candidates": candidates,
        "ballot_measure": ballot_measure,
        "raw_data": enriched_raw,
    }


def extract_civera_results_to_storage(
    client: CiveraElectionStatsClient,
    storage: Any,
    jurisdiction_id: str,
    county_slug: str,
    from_year: int = 2010,
    to_year: int = 2026,
    division_filter: Optional[str] = None,
) -> Dict[str, int]:
    """
    Extract historical election results from a Civera ElectionStats instance and store them.

    Args:
        client: CiveraElectionStatsClient instance
        storage: StorageBackend with store_elections + store_election_contests
        jurisdiction_id: Target jurisdiction (e.g., "county-sonoma")
        county_slug: County identifier for ID namespacing (e.g., "sonoma")
        from_year: Start year for election range
        to_year: End year for election range
        division_filter: If set, only store contests in this division

    Returns:
        Dict with counts: {"elections": N, "contests": M, "candidates": C}
    """
    events = client.list_elections(from_year=from_year, to_year=to_year)
    if not events:
        logger.info(f"No elections returned from Civera ({client.graphql_url})")
        return {"elections": 0, "contests": 0, "candidates": 0}

    total_elections = 0
    total_contests = 0
    total_candidates = 0

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        results = client.get_election_results(event_id, division_filter=division_filter)
        contests_data = results.get("contests", [])
        election_info = results.get("election_info", {})

        # Skip elections with no matching contests (avoids null date errors
        # when division_filter excludes all contests for this election)
        if not contests_data:
            logger.debug(f"  Skipping '{event.get('name')}': no contests match filter")
            continue

        election_date = _parse_election_date(election_info.get("start_date"))
        election_type_name = election_info.get("type")

        election = civera_results_to_election(
            event, county_slug, client.graphql_url, election_date, election_type_name,
        )

        # When filtering by division, namespace election ID by jurisdiction
        # so each city gets its own election record with its own contests
        if division_filter:
            election["id"] = f"{election['id']}-{jurisdiction_id}"

        stored = storage.store_elections(jurisdiction_id, [election])
        total_elections += stored

        mapped_contests = [civera_results_to_contest(c, county_slug) for c in contests_data]
        contest_count = storage.store_election_contests(election["id"], mapped_contests)
        total_contests += contest_count
        total_candidates += sum(len(c.get("candidates", [])) for c in mapped_contests)

        logger.info(
            f"  Election '{event.get('name')}': {len(contests_data)} contests stored"
        )

    logger.info(
        f"Civera results ({county_slug}): {total_elections} elections, {total_contests} contests, "
        f"{total_candidates} candidates for {jurisdiction_id}"
    )

    return {
        "elections": total_elections,
        "contests": total_contests,
        "candidates": total_candidates,
    }
