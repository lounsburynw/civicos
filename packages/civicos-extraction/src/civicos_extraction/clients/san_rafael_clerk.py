"""
San Rafael City Clerk Election Data Client

Extracts local election data from the San Rafael City Clerk website:
- City council candidates (district-based since 2020)
- Mayoral candidates (at-large)
- Local ballot measures
- School board races

Usage:
    client = SanRafaelClerkClient()
    candidates = client.get_candidates()
    measures = client.get_measures()
"""

import logging
import time
import re
from datetime import datetime, date
from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Any

from civicos_extraction.clients.base import HealthStatus, ValidationResult

if TYPE_CHECKING:
    from playwright.sync_api import Page, Browser, BrowserContext

logger = logging.getLogger(__name__)


class SanRafaelClerkClient:
    """
    San Rafael City Clerk client for local election data.

    Uses Playwright to scrape the City Clerk's election pages.
    San Rafael uses district-based elections since 2020:
    - 4 council districts (staggered 4-year terms)
    - Mayor elected at-large (4-year term)
    - City Attorney, City Clerk elected separately

    Election cycle:
    - Even years: November general elections
    - Districts 1 & 4: 2024, 2028, ...
    - Districts 2 & 3: 2026, 2030, ...
    - Mayor: 2024, 2028, ...
    """

    BASE_URL = "https://www.cityofsanrafael.org"
    ELECTIONS_URL = f"{BASE_URL}/elections/"

    # District election schedule (which districts are up in which years)
    DISTRICT_SCHEDULE = {
        2024: ["D1", "D4", "Mayor"],
        2026: ["D2", "D3"],
        2028: ["D1", "D4", "Mayor"],
        2030: ["D2", "D3"],
    }

    def __init__(
        self,
        headless: bool = True,
        request_delay: float = 2.0,
    ):
        """
        Initialize San Rafael Clerk client.

        Args:
            headless: Run browser in headless mode (default True)
            request_delay: Delay between requests in seconds (default 2.0)
        """
        self.headless = headless
        self.request_delay = request_delay
        self._browser: Optional["Browser"] = None
        self._context: Optional["BrowserContext"] = None
        self._page: Optional["Page"] = None
        self._playwright: Any = None

    @property
    def jurisdiction_id(self) -> str:
        return "city-san-rafael"

    @property
    def platform_name(self) -> str:
        return "san_rafael_clerk"

    @property
    def source_id(self) -> str:
        return "san_rafael_clerk-city-san-rafael"

    @property
    def source_type(self) -> str:
        return "san_rafael_clerk"

    def _init_browser(self):
        """Initialize Playwright browser with stealth settings."""
        if self._browser is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright is required for SanRafaelClerkClient. "
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
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._close_browser()

    def _navigate(
        self,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "domcontentloaded",
    ) -> bool:
        """Navigate to URL with rate limiting."""
        self._init_browser()
        time.sleep(self.request_delay)

        try:
            assert self._page is not None
            self._page.goto(url, wait_until=wait_until, timeout=45000)
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {url} - {e}")
            return False

    def health(self) -> HealthStatus:
        """Check source availability."""
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            self._init_browser()
            if self._navigate(self.ELECTIONS_URL) and self._page is not None:
                is_available = True
                links = self._page.query_selector_all("a")
                election_links = [
                    link for link in links
                    if "election" in (link.get_attribute("href") or "").lower()
                ]
                available_count = len(election_links)
                metadata["page_title"] = self._page.title()
        except Exception as e:
            errors.append(f"Health check error: {str(e)}")
        finally:
            self._close_browser()

        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=datetime.now(),
            check_duration_ms=round((time.time() - start_time) * 1000, 2),
            errors=errors,
            last_successful=datetime.now() if is_available else None,
            metadata=metadata,
        )

    def validate(self) -> ValidationResult:
        """Validate source configuration."""
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        try:
            from playwright.sync_api import sync_playwright as _sp  # noqa: F401
            del _sp
        except ImportError:
            errors.append("Playwright not installed")
            config_valid = False

        if config_valid:
            try:
                self._init_browser()
                if self._navigate(self.ELECTIONS_URL) and self._page is not None:
                    api_reachable = True
                    metadata["page_title"] = self._page.title()
            except Exception as e:
                errors.append(f"Browser error: {str(e)}")
            finally:
                self._close_browser()

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=round((time.time() - start_time) * 1000, 2),
            metadata=metadata,
        )

    def get_past_elections(self) -> List[Dict[str, Any]]:
        """
        Get list of past elections from the City Clerk site.

        Returns:
            List of election dictionaries with date, URL, and type
        """
        elections = []

        try:
            self._init_browser()
            if not self._navigate(f"{self.BASE_URL}/past-elections/") or self._page is None:
                return elections

            time.sleep(2)

            # Find election links
            links = self._page.query_selector_all("a")
            for link in links:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip()

                # Match patterns like "November 5, 2024 Election"
                match = re.search(
                    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
                    r"(\d{1,2}),?\s+(\d{4})",
                    text
                )
                if match and "election" in text.lower():
                    months = {
                        "january": 1, "february": 2, "march": 3, "april": 4,
                        "may": 5, "june": 6, "july": 7, "august": 8,
                        "september": 9, "october": 10, "november": 11, "december": 12,
                    }
                    month = months[match.group(1).lower()]
                    day = int(match.group(2))
                    year = int(match.group(3))

                    try:
                        election_date = date(year, month, day)
                        elections.append({
                            "name": text,
                            "election_date": election_date.isoformat(),
                            "url": href if href.startswith("http") else f"{self.BASE_URL}{href}",
                            "source": "san_rafael_clerk",
                        })
                    except ValueError:
                        continue

        except Exception as e:
            logger.error(f"Failed to get past elections: {e}")
        finally:
            self._close_browser()

        return elections

    def get_election_details(self, election_url: str) -> Optional[Dict[str, Any]]:
        """
        Get details from a specific election page.

        Args:
            election_url: URL to the election page

        Returns:
            Dict with candidates, measures, and results
        """
        try:
            self._init_browser()
            if not self._navigate(election_url) or self._page is None:
                return None

            time.sleep(2)

            main = self._page.query_selector("#main, main, article, .entry-content")
            if not main:
                return None

            text = main.inner_text()

            details: Dict[str, Any] = {
                "url": election_url,
                "title": self._page.title(),
                "candidates": [],
                "measures": [],
                "raw_text": text[:10000],
            }

            # Parse candidates
            details["candidates"] = self._parse_candidates(text)

            # Parse measures
            details["measures"] = self._parse_measures(text)

            return details

        except Exception as e:
            logger.error(f"Failed to get election details: {e}")
            return None
        finally:
            self._close_browser()

    def _parse_candidates(self, text: str) -> List[Dict[str, Any]]:
        """Parse candidate information from election page text."""
        candidates = []

        # Look for candidate sections
        # Pattern: Office name followed by candidate names
        lines = text.split("\n")
        current_office = None

        for i, line in enumerate(lines):
            line = line.strip()

            # Detect office headers
            if "Mayor" in line and "Candidate" in line:
                current_office = "Mayor"
            elif "Councilmember District" in line:
                match = re.search(r"District\s*(\d)", line)
                if match:
                    current_office = f"Council District {match.group(1)}"
            elif "City Attorney" in line and "Candidate" in line:
                current_office = "City Attorney"
            elif "City Clerk" in line and "Candidate" in line:
                current_office = "City Clerk"
            elif "Governing Board" in line or "Trustee Area" in line:
                match = re.search(r"Area\s*(\d)", line)
                if match:
                    current_office = f"School Board Area {match.group(1)}"

            # Detect candidate names (usually followed by "Statement of Qualifications")
            if current_office and i + 1 < len(lines):
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if "Statement of Qualifications" in next_line or "Campaign Finance" in next_line:
                    # This line is likely a candidate name
                    if line and not any(x in line.lower() for x in ["statement", "campaign", "candidate", "documents"]):
                        candidates.append({
                            "name": line,
                            "office": current_office,
                            "source": "san_rafael_clerk",
                        })

        return candidates

    def _parse_measures(self, text: str) -> List[Dict[str, Any]]:
        """Parse ballot measure information from election page text."""
        measures = []

        # Look for "Measure X" patterns
        measure_pattern = re.compile(
            r"Measure\s+([A-Z])\b",
            re.IGNORECASE
        )

        for match in measure_pattern.finditer(text):
            letter = match.group(1).upper()
            # Try to find the measure title/description nearby
            start = match.start()
            context = text[start:start + 500]

            # Look for quoted text which is often the measure title
            title_match = re.search(r'"([^"]+)"', context)
            title = title_match.group(1) if title_match else f"Measure {letter}"

            # Check if it passed
            passed = None
            if "voters approved" in context.lower():
                passed = True
            elif "voters rejected" in context.lower():
                passed = False

            measures.append({
                "letter": letter,
                "title": title[:200],  # Truncate long titles
                "passed": passed,
                "source": "san_rafael_clerk",
            })

        # Deduplicate
        seen = set()
        unique_measures = []
        for m in measures:
            if m["letter"] not in seen:
                seen.add(m["letter"])
                unique_measures.append(m)

        return unique_measures

    def get_upcoming_races(self, election_year: int = 2026) -> List[Dict[str, Any]]:
        """
        Get upcoming races based on the election schedule.

        San Rafael's district-based elections follow a fixed schedule:
        - Districts 1 & 4 + Mayor: 2024, 2028, ...
        - Districts 2 & 3: 2026, 2030, ...

        Args:
            election_year: Year to get races for (default 2026)

        Returns:
            List of races that will be on the ballot
        """
        races = []

        # Determine which offices are up
        if election_year % 4 == 0:  # Presidential year
            offices = ["Council District 1", "Council District 4", "Mayor"]
        else:  # Midterm year
            offices = ["Council District 2", "Council District 3"]

        for office in offices:
            races.append({
                "office": office,
                "election_year": election_year,
                "election_date": f"{election_year}-11-03",  # First Tuesday after first Monday
                "jurisdiction": "city-san-rafael",
                "source": "san_rafael_clerk",
                "candidates": [],  # Will be populated closer to election
            })

        return races

    def get_district_map_url(self) -> str:
        """Get URL to the district map."""
        return f"{self.BASE_URL}/departments/district-elections/"


def create_san_rafael_clerk_client() -> SanRafaelClerkClient:
    """Create San Rafael Clerk client."""
    return SanRafaelClerkClient()


# ==================== Storage Mappers ====================


def san_rafael_candidate_to_storage(
    candidate: Dict[str, Any],
    election_id: str,
) -> Dict[str, Any]:
    """Map candidate to storage format."""
    return {
        "id": f"sr-{election_id}-{candidate['office'].lower().replace(' ', '-')}-{candidate['name'].lower().replace(' ', '-')}",
        "name": candidate.get("name"),
        "office": candidate.get("office"),
        "election_id": election_id,
        "source": "san_rafael_clerk",
        "raw_data": candidate,
    }


def san_rafael_measure_to_storage(
    measure: Dict[str, Any],
    election_id: str,
) -> Dict[str, Any]:
    """Map ballot measure to storage format."""
    return {
        "id": f"sr-{election_id}-measure-{measure['letter'].lower()}",
        "letter": measure.get("letter"),
        "title": measure.get("title"),
        "passed": measure.get("passed"),
        "election_id": election_id,
        "source": "san_rafael_clerk",
        "raw_data": measure,
    }
