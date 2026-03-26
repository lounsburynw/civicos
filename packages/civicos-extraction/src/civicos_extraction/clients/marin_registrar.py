"""
Marin County Registrar of Voters Scraper Client

Extracts election data from Marin County Elections website using Playwright.
The Marin County site uses Cloudflare protection, so we need a real browser.

Usage:
    client = MarinRegistrarClient("san-rafael")
    elections = client.get_elections()
    schedule = client.get_election_schedule()
"""

import logging
import time
import re
from datetime import datetime, date
from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Any, Protocol, runtime_checkable

from civicos_extraction.clients.base import HealthStatus, ValidationResult

if TYPE_CHECKING:
    from playwright.sync_api import Page, Browser, BrowserContext

logger = logging.getLogger(__name__)


class MarinRegistrarClient:
    """
    Marin County Registrar of Voters client for election data.

    Uses Playwright to scrape the Marin County elections website which
    blocks requests-based access (Cloudflare protection).

    Features:
    - Stealth browser automation to bypass Cloudflare
    - Election schedule extraction
    - Measure information extraction
    - Rate limiting between requests
    """

    BASE_URL = "https://www.marincounty.gov/departments/elections"

    def __init__(
        self,
        jurisdiction_id: str,
        headless: bool = True,
        request_delay: float = 2.0,
    ):
        """
        Initialize Marin Registrar client.

        Args:
            jurisdiction_id: Civic jurisdiction ID (e.g., "san-rafael")
            headless: Run browser in headless mode (default True)
            request_delay: Delay between requests in seconds (default 2.0)
        """
        self.jurisdiction_id = jurisdiction_id
        self.headless = headless
        self.request_delay = request_delay
        self._browser: Optional["Browser"] = None
        self._context: Optional["BrowserContext"] = None
        self._page: Optional["Page"] = None
        self._playwright: Any = None

    @property
    def platform_name(self) -> str:
        return "marin_registrar"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"marin_registrar-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "marin_registrar"

    def _init_browser(self):
        """Initialize Playwright browser with stealth settings."""
        if self._browser is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright is required for MarinRegistrarClient. "
                "Install with: pip install playwright && playwright install chromium"
            )

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        self._page = self._context.new_page()
        # Remove automation detection
        self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

    def _close_browser(self):
        """Close browser and clean up resources."""
        if self._browser:
            self._browser.close()
            self._browser = None
        if hasattr(self, "_playwright") and self._playwright:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self):
        """Context manager entry."""
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self._close_browser()

    def _navigate(
        self,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> bool:
        """
        Navigate to URL with rate limiting and error handling.

        Args:
            url: URL to navigate to
            wait_until: Playwright wait condition

        Returns:
            True if navigation succeeded, False otherwise
        """
        self._init_browser()
        time.sleep(self.request_delay)

        try:
            assert self._page is not None, "Browser not initialized"
            self._page.goto(url, wait_until=wait_until, timeout=30000)
            title = self._page.title()

            if "cloudflare" in title.lower() or "blocked" in title.lower():
                logger.warning(
                    "Blocked by Cloudflare",
                    extra={
                        "url": url,
                        "title": title,
                        "platform": self.platform_name,
                    },
                )
                return False

            return True

        except Exception as e:
            logger.error(
                "Navigation failed",
                extra={
                    "url": url,
                    "error": str(e),
                    "platform": self.platform_name,
                },
            )
            return False

    def _click_and_expand(self, selector: str) -> bool:
        """Click an element to expand it."""
        if self._page is None:
            return False
        try:
            element = self._page.query_selector(selector)
            if element:
                element.click()
                time.sleep(1)  # Wait for animation
                return True
        except Exception as e:
            logger.debug(f"Could not click {selector}: {e}")
        return False

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Performs a lightweight check by attempting to load the elections page.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            self._init_browser()
            if self._navigate(self.BASE_URL) and self._page is not None:
                is_available = True
                # Quick count of election links
                links = self._page.query_selector_all("a")
                election_links = [
                    link for link in links
                    if "election" in (link.get_attribute("href") or "").lower()
                ]
                available_count = len(election_links)
                metadata["page_title"] = self._page.title()

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
        finally:
            self._close_browser()

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
            metadata=metadata,
        )

    def validate(self) -> ValidationResult:
        """Validate source configuration and accessibility."""
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        # Check Playwright is available
        try:
            from playwright.sync_api import sync_playwright as _sync_playwright  # noqa: F401
            del _sync_playwright  # Just checking import availability
        except ImportError:
            errors.append("Playwright not installed. Run: pip install playwright && playwright install chromium")
            config_valid = False

        if config_valid:
            try:
                self._init_browser()
                if self._navigate(self.BASE_URL) and self._page is not None:
                    api_reachable = True
                    metadata["page_title"] = self._page.title()
                else:
                    errors.append("Cannot reach Marin County Elections website (Cloudflare blocked)")
            except Exception as e:
                errors.append(f"Browser initialization failed: {str(e)}")
            finally:
                self._close_browser()

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

    def get_election_schedule(self) -> List[Dict[str, Any]]:
        """
        Fetch election schedule from the elections website.

        Returns:
            List of election dictionaries with date, name, type, and status
        """
        elections = []

        try:
            self._init_browser()
            schedule_url = f"{self.BASE_URL}/election-information/election-schedule"

            if not self._navigate(schedule_url) or self._page is None:
                return elections

            # Click "Open All Panels" to expand the schedule
            self._click_and_expand('text="Open All Panels"')
            time.sleep(1)

            # Get the page content
            main_content = self._page.query_selector("#main-content, main")
            if not main_content:
                return elections

            text = main_content.inner_text()

            # Parse elections from text
            elections = self._parse_election_schedule(text)

        except Exception as e:
            logger.error(
                "Failed to get election schedule",
                extra={"error": str(e), "platform": self.platform_name},
            )
        finally:
            self._close_browser()

        return elections

    def _parse_election_schedule(self, text: str) -> List[Dict[str, Any]]:
        """Parse election schedule from page text."""
        elections = []

        # Pattern: "Month DD, YYYY - Election Type"
        # Examples:
        #   "January 27, 2026 Special Parcel Tax Election"
        #   "June 2, 2026 - Statewide Direct Primary Election"
        #   "November 3, 2026 - General Election"
        pattern = re.compile(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(\d{1,2}),?\s+(\d{4})\s*[-–]?\s*(.*?)(?:Election|election)",
            re.IGNORECASE
        )

        months = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }

        seen_dates = set()

        for match in pattern.finditer(text):
            month_name = match.group(1).lower()
            day = int(match.group(2))
            year = int(match.group(3))
            description = match.group(4).strip()

            try:
                election_date = date(year, months[month_name], day)
            except ValueError:
                continue

            # Skip past elections
            if election_date < date.today():
                continue

            # Avoid duplicates
            date_str = election_date.isoformat()
            if date_str in seen_dates:
                continue
            seen_dates.add(date_str)

            # Infer election type
            desc_lower = description.lower()
            if "primary" in desc_lower:
                election_type = "primary"
            elif "general" in desc_lower:
                election_type = "general"
            elif "special" in desc_lower or "parcel tax" in desc_lower:
                election_type = "special"
            elif "presidential" in desc_lower:
                election_type = "general"
            else:
                election_type = "other"

            # Build election name
            name = f"{description}Election".strip()
            if not name or name == "Election":
                name = f"Marin County {election_date.strftime('%B %d, %Y')} Election"

            # Check if election is scheduled (look for "no election is scheduled")
            status = "scheduled"
            if "no election is scheduled" in text.lower():
                # Check if this date appears near a "no election" message
                date_pattern = election_date.strftime("%B %d, %Y").replace(" 0", " ")
                if date_pattern in text:
                    # Find the context around this date
                    idx = text.find(date_pattern)
                    context = text[idx:idx+200].lower()
                    if "no election is scheduled" in context:
                        status = "possible"

            elections.append({
                "id": f"marin-{date_str}",
                "name": name,
                "election_date": date_str,
                "election_type": election_type,
                "status": status,
                "jurisdiction": "marin_county",
                "source": "marin_registrar",
                "source_url": f"{self.BASE_URL}/election-information/election-schedule",
            })

        return elections

    def get_elections(self) -> List[Dict[str, Any]]:
        """
        Fetch upcoming elections including details.

        Combines schedule information with any election-specific pages.

        Returns:
            List of election dictionaries
        """
        # Get base schedule
        elections = self.get_election_schedule()

        # Filter to only scheduled elections (skip "possible" dates)
        scheduled = [e for e in elections if e.get("status") == "scheduled"]

        return scheduled

    def get_election_page_info(self, election_path: str) -> Optional[Dict[str, Any]]:
        """
        Fetch details from an election-specific page.

        Args:
            election_path: Path to election page (e.g., "/january-27-2026-special-parcel-tax-election")

        Returns:
            Dict with election details or None if not found
        """
        try:
            self._init_browser()
            url = f"{self.BASE_URL}{election_path}"

            if not self._navigate(url) or self._page is None:
                return None

            # Get page content
            main_content = self._page.query_selector("#main-content, main")
            if not main_content:
                return None

            # Click to expand all panels
            self._click_and_expand('text="Open All Panels"')
            time.sleep(1)

            text = main_content.inner_text()

            # Extract key information
            info: Dict[str, Any] = {
                "title": self._page.title(),
                "url": url,
                "raw_text": text[:5000],  # Limit for storage
            }

            # Look for key dates section
            if "key dates" in text.lower():
                info["has_key_dates"] = True

            # Look for measure information
            if "measure" in text.lower():
                info["has_measures"] = True

            return info

        except Exception as e:
            logger.error(
                "Failed to get election page info",
                extra={"error": str(e), "path": election_path},
            )
            return None
        finally:
            self._close_browser()


def create_san_rafael_registrar_client() -> MarinRegistrarClient:
    """
    Create Marin Registrar client configured for San Rafael.

    Returns:
        Configured MarinRegistrarClient
    """
    return MarinRegistrarClient(
        jurisdiction_id="san-rafael",
    )


# =============================================================================
# Marin Registrar Election Results Client (GraphQL / ElectionStats by Civera)
# =============================================================================

# Pseudocandidate values returned by the API for summary/metadata rows
_PSEUDO_CANDIDATES = {"TOTAL_VOTES", "TOTAL_BALLOTS", "PSEUDOCANDIDATE", "VOTER_STAT"}


class MarinRegistrarResultsClient:
    """
    GraphQL client for Marin County historical election results.

    Queries the ElectionStats platform (by Civera) at pastelections.marincounty.gov.
    No authentication required. Covers 46 elections from June 2010 to present.

    Three-query pattern:
        1. list_elections()     — all elections in a year range
        2. list_contests()      — contests + candidates for one election
        3. get_precinct_data()  — precinct-level vote breakdowns for one contest
    """

    GRAPHQL_URL = "https://pastelections.marincounty.gov/api/graphql_pr"

    def __init__(
        self,
        jurisdiction_id: str = "city-san-rafael",
        request_delay: float = 0.5,
        timeout: int = 30,
    ):
        self.jurisdiction_id = jurisdiction_id
        self.request_delay = request_delay
        self.timeout = timeout
        self._session: Optional[Any] = None
        self._last_request_time = 0.0

    @property
    def platform_name(self) -> str:
        return "marin_registrar_results"

    @property
    def source_id(self) -> str:
        return f"marin_registrar_results-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "marin_registrar_results"

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
            self.GRAPHQL_URL,
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
        logger.info(f"Listed {len(events)} elections ({from_year}-{to_year})")
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
            config_valid=True,  # No config needed (no auth)
            api_reachable=api_reachable,
            errors=errors,
            warnings=[],
            check_duration_ms=round(check_duration_ms, 2),
            metadata={"graphql_url": self.GRAPHQL_URL},
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

        Args:
            event_id: Election event ID from list_elections()
            division_filter: If set, only return contests in this division

        Returns:
            Dict with 'contests' list and 'election_info' dict
        """
        contests_raw = self.list_contests(event_id)

        contests = []
        for c in contests_raw:
            # Apply division filter if requested
            division = c.get("division", {})
            if division_filter:
                div_name = division.get("displayName", "")
                if division_filter.lower() not in div_name.lower():
                    continue

            # Filter out pseudo-candidates
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

        # Extract election info from first contest
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


@runtime_checkable
class ElectionStorageProtocol(Protocol):
    """Protocol for storage backends that support election operations."""

    def store_elections(
        self,
        jurisdiction_id: str,
        elections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store elections with temporal versioning."""
        ...

    def store_election_contests(
        self,
        election_id: str,
        contests: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store election contests with temporal versioning."""
        ...


def marin_election_to_storage(
    election: Dict[str, Any],
    jurisdiction_id: str,  # noqa: ARG001 - kept for consistency with other mappers
) -> Dict[str, Any]:
    """
    Map Marin Registrar election to storage format.

    Args:
        election: Election from MarinRegistrarClient
        jurisdiction_id: Target jurisdiction (e.g., "san-rafael")

    Returns:
        Election dict ready for StorageBackend.store_elections()
    """
    _ = jurisdiction_id  # Explicitly mark as intentionally unused
    return {
        "id": election.get("id"),
        "name": election.get("name"),
        "election_date": election.get("election_date"),
        "election_type": election.get("election_type", "other"),
        "source": "marin_registrar",
        "source_url": election.get("source_url"),
        "status": election.get("status", "scheduled"),
        "raw_data": election,
    }


def _infer_election_type_from_name(name: str) -> str:
    """Infer election type from Marin election event name."""
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
        # GraphQL returns ISO format like "2024-11-05T00:00:00"
        dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except (ValueError, AttributeError):
        return start_date[:10] if start_date and len(start_date) >= 10 else None


def _map_contest_type(contest: Dict[str, Any]) -> str:
    """Map GraphQL contest to ContestType value."""
    office_name = (contest.get("office") or {}).get("name", "").lower()
    division_type = ((contest.get("division") or {}).get("divisionType") or {}).get("name", "").lower()

    # Ballot measure
    if contest.get("ballotQuestionId"):
        if "school" in division_type or "school" in office_name:
            return "local_measure"
        if "state" in division_type:
            return "state_proposition"
        return "local_measure"

    # Federal
    if "president" in office_name:
        return "federal_president"
    if "senator" in office_name and "state" not in office_name:
        return "federal_senate"
    if "representative" in office_name or "congress" in office_name:
        return "federal_house"

    # State
    if "governor" in office_name:
        return "state_governor"
    if "assembly" in office_name or "state senator" in office_name:
        return "state_legislature"

    # Local
    if "mayor" in office_name:
        return "local_mayor"
    if "council" in office_name or "supervisor" in office_name:
        return "local_council"
    if "school" in office_name or "school" in division_type:
        return "local_school_board"
    if "judge" in office_name or "justice" in office_name:
        return "judicial"

    return "other"


def marin_results_to_election(
    event: Dict[str, Any],
    election_date: Optional[str] = None,
    election_type_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Map a Marin GraphQL election event to storage format.

    Args:
        event: Event dict from list_elections() (keys: id, name, group, count)
        election_date: ISO date if known (from contest data)
        election_type_name: Type name from contest event data

    Returns:
        Election dict ready for StorageBackend.store_elections()
    """
    name = event.get("name", "Unknown Election")
    event_id = event.get("id")

    e_type = "general"
    if election_type_name:
        e_type = _infer_election_type_from_name(election_type_name)
    else:
        e_type = _infer_election_type_from_name(name)

    return {
        "id": f"marin-results-{event_id}",
        "name": name,
        "election_date": election_date,
        "election_type": e_type,
        "source": "marin_registrar_results",
        "source_url": f"https://pastelections.marincounty.gov/?e={event_id}",
        "raw_data": event,
    }


def marin_results_to_contest(contest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map a Marin GraphQL contest result to storage format.

    Args:
        contest: Contest dict from list_contests() (already pseudo-filtered)

    Returns:
        Contest dict ready for StorageBackend.store_election_contests()
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

    # Build candidate list
    candidates = []
    for cand in contest.get("candidates", []):
        candidates.append({
            "id": f"marin-cand-{contest_id}-{cand.get('displayName', '').replace(' ', '-').lower()[:40]}",
            "name": cand.get("displayName", "Unknown"),
            "party": (cand.get("party") or {}).get("name"),
            "votes_received": cand.get("nVotes"),
            "vote_percentage": cand.get("pctCandidateVotes"),
            "is_winner": bool(cand.get("isWinner")),
            "source": "marin_registrar_results",
        })

    # Ballot measure data
    ballot_measure = None
    if ballot_q:
        yes_cand = next((c for c in candidates if c["name"].lower() == "yes"), None)
        no_cand = next((c for c in candidates if c["name"].lower() == "no"), None)
        ballot_measure = {
            "id": f"marin-measure-{contest_id}",
            "title": title,
            "description": ballot_q.get("questionText", ""),
            "measure_type": (ballot_q.get("type") or {}).get("name", "measure"),
            "passed": bool(yes_cand and yes_cand.get("is_winner")),
            "yes_votes": yes_cand["votes_received"] if yes_cand else None,
            "no_votes": no_cand["votes_received"] if no_cand else None,
            "yes_percentage": yes_cand["vote_percentage"] if yes_cand else None,
            "no_percentage": no_cand["vote_percentage"] if no_cand else None,
            "source": "marin_registrar_results",
        }

    # Embed mapped candidates and ballot_measure into raw_data so they persist
    # in the JSONB column (store_election_contests only stores raw_data, not
    # top-level candidates/ballot_measure keys)
    enriched_raw = {
        **contest,
        "mapped_candidates": candidates,
        "mapped_ballot_measure": ballot_measure,
    }

    return {
        "id": f"marin-contest-{contest_id}",
        "title": title,
        "contest_type": _map_contest_type(contest),
        "district_name": division.get("displayName"),
        "number_elected": contest.get("nSeats", 1),
        "candidates": candidates,
        "ballot_measure": ballot_measure,
        "raw_data": enriched_raw,
    }


def extract_marin_results_to_storage(
    client: "MarinRegistrarResultsClient",
    storage: ElectionStorageProtocol,
    jurisdiction_id: str,
    from_year: int = 2010,
    to_year: int = 2026,
    division_filter: Optional[str] = None,
) -> Dict[str, int]:
    """
    Extract historical election results from Marin GraphQL API and store them.

    Args:
        client: MarinRegistrarResultsClient instance
        storage: StorageBackend with store_elections + store_election_contests
        jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
        from_year: Start year for election range
        to_year: End year for election range
        division_filter: If set, only store contests in this division
                         (e.g., "City of San Rafael")

    Returns:
        Dict with counts: {"elections": N, "contests": M, "candidates": C}
    """
    events = client.list_elections(from_year=from_year, to_year=to_year)
    if not events:
        logger.info("No elections returned from Marin Registrar GraphQL API")
        return {"elections": 0, "contests": 0, "candidates": 0}

    total_elections = 0
    total_contests = 0
    total_candidates = 0

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        # Fetch contests for this election
        results = client.get_election_results(event_id, division_filter=division_filter)
        contests_data = results.get("contests", [])
        election_info = results.get("election_info", {})

        # Determine election date from contest data
        election_date = _parse_election_date(election_info.get("start_date"))
        election_type_name = election_info.get("type")

        # Store election
        election = marin_results_to_election(event, election_date, election_type_name)
        stored = storage.store_elections(jurisdiction_id, [election])
        total_elections += stored

        # Map and store contests
        if contests_data:
            mapped_contests = [marin_results_to_contest(c) for c in contests_data]
            contest_count = storage.store_election_contests(election["id"], mapped_contests)
            total_contests += contest_count
            total_candidates += sum(len(c.get("candidates", [])) for c in mapped_contests)

        logger.info(
            f"  Election '{event.get('name')}': {len(contests_data)} contests stored"
        )

    logger.info(
        f"Marin results: {total_elections} elections, {total_contests} contests, "
        f"{total_candidates} candidates for {jurisdiction_id}"
    )

    return {
        "elections": total_elections,
        "contests": total_contests,
        "candidates": total_candidates,
    }


def extract_marin_elections_to_storage(
    client: MarinRegistrarClient,
    storage: ElectionStorageProtocol,
    jurisdiction_id: str,
) -> int:
    """
    Extract elections from Marin Registrar and store them.

    Args:
        client: MarinRegistrarClient instance
        storage: StorageBackend instance with store_elections method
        jurisdiction_id: Target jurisdiction (e.g., "san-rafael")

    Returns:
        Number of elections stored
    """
    elections = client.get_elections()
    if not elections:
        logger.info("No elections returned from Marin Registrar")
        return 0

    mapped = [marin_election_to_storage(e, jurisdiction_id) for e in elections]
    count = storage.store_elections(jurisdiction_id, mapped)
    logger.info(f"Stored {count} elections for {jurisdiction_id} from Marin Registrar")
    return count
