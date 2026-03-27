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

# Backward-compatible alias: MarinRegistrarResultsClient wraps the generalized
# CiveraElectionStatsClient with Marin-specific defaults.
from civicos_extraction.clients.civera_election_stats import (  # noqa: E402
    CiveraElectionStatsClient,
    CIVERA_INSTANCES,
    civera_results_to_election as _civera_results_to_election,
    civera_results_to_contest as _civera_results_to_contest,
    extract_civera_results_to_storage,
    _infer_election_type_from_name,
    _parse_election_date,
    _map_contest_type,
)


class MarinRegistrarResultsClient(CiveraElectionStatsClient):
    """Backward-compatible wrapper — Marin-specific defaults for CiveraElectionStatsClient."""

    DEFAULT_GRAPHQL_URL = CIVERA_INSTANCES["marin"]["graphql_url"]

    def __init__(
        self,
        jurisdiction_id: str = "city-san-rafael",
        graphql_url: Optional[str] = None,
        request_delay: float = 0.5,
        timeout: int = 30,
    ):
        super().__init__(
            jurisdiction_id=jurisdiction_id,
            graphql_url=graphql_url or self.DEFAULT_GRAPHQL_URL,
            county_slug="marin",
            request_delay=request_delay,
            timeout=timeout,
        )

    @property
    def platform_name(self) -> str:
        return "marin_registrar_results"

    @property
    def source_id(self) -> str:
        return f"marin_registrar_results-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "marin_registrar_results"


# ==================== Storage Mappers (backward-compatible) ====================


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
    jurisdiction_id: str,
) -> Dict[str, Any]:
    """Map Marin Registrar election to storage format (from web scraper, not GraphQL)."""
    _ = jurisdiction_id
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


def marin_results_to_election(
    event: Dict[str, Any],
    election_date: Optional[str] = None,
    election_type_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Backward-compatible wrapper — delegates to civera_results_to_election with marin defaults."""
    return _civera_results_to_election(
        event, "marin", CIVERA_INSTANCES["marin"]["graphql_url"],
        election_date, election_type_name,
    )


def marin_results_to_contest(contest: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible wrapper — delegates to civera_results_to_contest with marin defaults."""
    return _civera_results_to_contest(contest, "marin")


def extract_marin_results_to_storage(
    client: "MarinRegistrarResultsClient",
    storage: ElectionStorageProtocol,
    jurisdiction_id: str,
    from_year: int = 2010,
    to_year: int = 2026,
    division_filter: Optional[str] = None,
) -> Dict[str, int]:
    """Backward-compatible wrapper — delegates to extract_civera_results_to_storage."""
    return extract_civera_results_to_storage(
        client=client,
        storage=storage,
        jurisdiction_id=jurisdiction_id,
        county_slug="marin",
        from_year=from_year,
        to_year=to_year,
        division_filter=division_filter,
    )


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
