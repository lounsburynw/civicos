"""
Simbli/eBoard School Board Meeting Scraper Client

Extracts board meeting data from Simbli-hosted school board portals using Playwright.
Simbli uses Incapsula WAF that blocks standard HTTP requests, so we need a real browser.

Usage:
    client = SimbliClient("https://srcs.simbli.com/index.php?AppGroupId=82", "srcs")
    meetings = client.get_meetings()
    agenda = client.get_agenda_pdf(meeting_id)

Designed for San Rafael City Schools (SRCS) but generalizable to other Simbli districts.
"""

import logging
import time
import re
from datetime import datetime, date
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Any, Protocol, runtime_checkable

from civicos_extraction.clients.base import HealthStatus, ValidationResult, Meeting

if TYPE_CHECKING:
    from playwright.sync_api import Page, Browser, BrowserContext

logger = logging.getLogger(__name__)


@dataclass
class SimbliMeeting:
    """
    Meeting extracted from Simbli eBoard.

    Contains metadata and document links for a school board meeting.
    """
    id: str  # Unique identifier (e.g., "srcs-2026-01-15")
    title: str  # Meeting title (e.g., "Regular Board Meeting")
    meeting_datetime: datetime  # Date and time of meeting
    meeting_type: str  # "regular", "special", "study_session", etc.
    agenda_url: Optional[str] = None  # Link to agenda PDF
    minutes_url: Optional[str] = None  # Link to minutes PDF
    attachments: Optional[List[Dict[str, str]]] = None  # [{name, url}]
    location: Optional[str] = None
    source_url: Optional[str] = None  # Page URL this was scraped from
    raw_html: Optional[str] = None  # Raw HTML for debugging
    simbli_mid: Optional[str] = None  # Simbli internal meeting ID for PDF download

    def to_meeting(self, jurisdiction_id: str) -> Meeting:
        """Convert to standard Meeting format."""
        return Meeting(
            id=self.id,
            title=self.title,
            meeting_datetime=self.meeting_datetime,
            jurisdiction_id=jurisdiction_id,
            meeting_type=self.meeting_type,
            status="confirmed",
            location=self.location,
            agenda_url=self.agenda_url,
            minutes_url=self.minutes_url,
            source_platform="simbli",
            source_url=self.source_url,
            raw_data={
                "attachments": self.attachments,
            } if self.attachments else None,
        )


class SimbliClient:
    """
    Simbli/eBoard school board meeting client.

    Uses Playwright to scrape Simbli-hosted board portals which
    block requests-based access (Incapsula WAF protection).

    Features:
    - Stealth browser automation to bypass Incapsula WAF
    - Meeting list extraction with date/type parsing
    - Agenda and minutes PDF link extraction
    - Attachment enumeration
    - Rate limiting between requests
    """

    def __init__(
        self,
        board_url: str,
        jurisdiction_id: str,
        headless: bool = True,
        request_delay: float = 2.0,
    ):
        """
        Initialize Simbli client.

        Args:
            board_url: Full URL to Simbli board page
                       (e.g., "https://srcs.simbli.com/index.php?AppGroupId=82")
            jurisdiction_id: Civic jurisdiction ID (e.g., "srcs" for San Rafael City Schools)
            headless: Run browser in headless mode (default True)
            request_delay: Delay between requests in seconds (default 2.0)
        """
        self.board_url = board_url
        self.jurisdiction_id = jurisdiction_id
        self.headless = headless
        self.request_delay = request_delay
        self._browser: Optional["Browser"] = None
        self._context: Optional["BrowserContext"] = None
        self._page: Optional["Page"] = None
        self._playwright: Any = None

        # Extract base URL for constructing absolute URLs
        from urllib.parse import urlparse
        parsed = urlparse(board_url)
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"

    @property
    def platform_name(self) -> str:
        return "simbli"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"simbli-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "simbli"

    def _init_browser(self):
        """Initialize Playwright browser with stealth settings to bypass Incapsula."""
        if self._browser is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright is required for SimbliClient. "
                "Install with: pip install playwright && playwright install chromium"
            )

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        assert self._browser is not None  # Type narrowing
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            # Accept cookies automatically
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        self._page = self._context.new_page()

        # Remove automation detection markers
        self._page.add_init_script("""
            // Remove webdriver property
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

            // Mock chrome object
            window.chrome = { runtime: {} };

            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
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

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        # Args are unused but required by context manager protocol
        _ = (exc_type, exc_val, exc_tb)
        self._close_browser()

    def _navigate(
        self,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "networkidle",
        timeout: int = 60000,
    ) -> bool:
        """
        Navigate to URL with rate limiting and WAF handling.

        Args:
            url: URL to navigate to
            wait_until: Playwright wait condition
            timeout: Navigation timeout in ms (default 60s for Incapsula challenge)

        Returns:
            True if navigation succeeded, False otherwise
        """
        self._init_browser()
        time.sleep(self.request_delay)

        try:
            assert self._page is not None, "Browser not initialized"
            self._page.goto(url, wait_until=wait_until, timeout=timeout)

            # Wait for potential Incapsula challenge to complete
            # Incapsula sometimes shows a "checking your browser" page
            time.sleep(2)

            title = self._page.title()
            page_content = self._page.content()

            # Check for Incapsula/Cloudflare blocking
            block_indicators = [
                "incapsula",
                "cloudflare",
                "blocked",
                "access denied",
                "checking your browser",
                "please wait",
            ]

            title_lower = title.lower()
            content_lower = page_content.lower()[:2000]  # First 2000 chars

            for indicator in block_indicators:
                if indicator in title_lower:
                    logger.warning(
                        f"Potentially blocked by WAF (title contains '{indicator}')",
                        extra={
                            "url": url,
                            "title": title,
                            "platform": self.platform_name,
                        },
                    )
                    # Wait longer for challenge to resolve
                    time.sleep(5)
                    # Check again
                    title = self._page.title()
                    if indicator in title.lower():
                        logger.error(f"WAF block not resolved: {title}")
                        return False

            # Check content for block indicators (but not as strictly)
            if "request unsuccessful" in content_lower or "access denied" in content_lower:
                logger.warning(
                    "Access denied by target site",
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

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Performs a lightweight check by attempting to load the board page.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            self._init_browser()
            if self._navigate(self.board_url) and self._page is not None:
                is_available = True

                # Quick count of meeting links
                # Simbli typically shows meetings in a table or list
                meeting_elements = self._page.query_selector_all(
                    "table tr, .meeting-row, [class*='meeting'], a[href*='Meeting']"
                )
                available_count = len(meeting_elements)
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
            del _sync_playwright
        except ImportError:
            errors.append(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
            config_valid = False

        # Check URL format
        if not self.board_url.startswith("http"):
            errors.append(f"Invalid board_url: {self.board_url}")
            config_valid = False

        if config_valid:
            try:
                self._init_browser()
                if self._navigate(self.board_url) and self._page is not None:
                    api_reachable = True
                    metadata["page_title"] = self._page.title()

                    # Check if we can see any meeting content
                    body_text = self._page.inner_text("body")
                    if "meeting" in body_text.lower() or "board" in body_text.lower():
                        metadata["content_detected"] = True
                    else:
                        warnings.append(
                            "Page loaded but no meeting content detected - "
                            "may be blocked or incorrect URL"
                        )
                else:
                    errors.append(
                        "Cannot reach Simbli board page (WAF blocked or site unavailable)"
                    )
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

    def get_meetings(
        self,
        since: Optional[date] = None,
        limit: int = 50,
    ) -> List[SimbliMeeting]:
        """
        Fetch meetings from the Simbli board page.

        Args:
            since: Only return meetings after this date (default: 1 year ago)
            limit: Maximum number of meetings to return

        Returns:
            List of SimbliMeeting objects
        """
        if since is None:
            since = date(date.today().year - 1, 1, 1)

        meetings: List[SimbliMeeting] = []

        try:
            self._init_browser()

            if not self._navigate(self.board_url) or self._page is None:
                logger.error("Failed to navigate to Simbli board page")
                return meetings

            # Get page content for parsing
            page_content = self._page.content()
            page_text = self._page.inner_text("body")

            # Store page title for debugging
            page_title = self._page.title()
            logger.info(f"Loaded Simbli page: {page_title}")

            # Parse meetings from the page
            meetings = self._parse_meetings_from_page(page_content, page_text, since, limit)

            # Discover MIDs by clicking on meeting rows
            if meetings:
                meetings = self._discover_meeting_mids(meetings)
                mids_found = sum(1 for m in meetings if m.simbli_mid)
                logger.info(f"Discovered {mids_found}/{len(meetings)} meeting MIDs")

            logger.info(
                f"Found {len(meetings)} meetings from Simbli",
                extra={
                    "jurisdiction_id": self.jurisdiction_id,
                    "since": since.isoformat(),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to get meetings from Simbli",
                extra={"error": str(e), "platform": self.platform_name},
            )
        finally:
            self._close_browser()

        return meetings

    def _parse_meetings_from_page(
        self,
        html_content: str,
        text_content: str,
        since: date,
        limit: int,
    ) -> List[SimbliMeeting]:
        """
        Parse meeting data from Simbli page content.

        Simbli pages can have various structures. This method attempts
        to find meeting information through multiple strategies.

        Args:
            html_content: Raw HTML of the page
            text_content: Text content of the page
            since: Only return meetings after this date
            limit: Maximum meetings to return

        Returns:
            List of SimbliMeeting objects
        """
        meetings: List[SimbliMeeting] = []

        # Strategy 1: Look for table rows with meeting data
        # Simbli typically presents meetings in tables
        meetings.extend(
            self._parse_table_meetings(html_content, since, limit - len(meetings))
        )

        # Strategy 2: Look for meeting links with dates in text
        if len(meetings) < limit:
            meetings.extend(
                self._parse_link_meetings(html_content, text_content, since, limit - len(meetings))
            )

        # Deduplicate by meeting ID
        seen_ids = set()
        unique_meetings = []
        for meeting in meetings:
            if meeting.id not in seen_ids:
                seen_ids.add(meeting.id)
                unique_meetings.append(meeting)

        return unique_meetings[:limit]

    def _parse_table_meetings(
        self,
        html_content: str,
        since: date,
        limit: int,
    ) -> List[SimbliMeeting]:
        """Parse meetings from HTML tables."""
        meetings: List[SimbliMeeting] = []

        # Pattern to find table rows with dates
        # Looking for patterns like "January 15, 2026" or "01/15/2026"
        date_pattern = re.compile(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(\d{1,2}),?\s+(\d{4})"
            r"|"
            r"(\d{1,2})/(\d{1,2})/(\d{4})",
            re.IGNORECASE
        )

        months = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }

        # Find all table rows in HTML
        row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)

        for row_match in row_pattern.finditer(html_content):
            if len(meetings) >= limit:
                break

            row_html = row_match.group(1)
            row_text = re.sub(r"<[^>]+>", " ", row_html)  # Strip HTML tags

            # Look for a date in this row
            date_match = date_pattern.search(row_text)
            if not date_match:
                continue

            # Parse the date
            try:
                if date_match.group(1):  # Month name format
                    month = months[date_match.group(1).lower()]
                    day = int(date_match.group(2))
                    year = int(date_match.group(3))
                else:  # MM/DD/YYYY format
                    month = int(date_match.group(4))
                    day = int(date_match.group(5))
                    year = int(date_match.group(6))

                meeting_date = date(year, month, day)
            except (ValueError, TypeError):
                continue

            # Skip meetings before our date threshold
            if meeting_date < since:
                continue

            # Extract meeting type from text
            meeting_type = self._infer_meeting_type(row_text)

            # Look for PDF links (agenda, minutes)
            agenda_url = self._find_pdf_link(row_html, ["agenda", "agnd"])
            minutes_url = self._find_pdf_link(row_html, ["minutes", "min"])

            # Generate meeting title
            title = self._generate_meeting_title(meeting_type, meeting_date)

            meeting = SimbliMeeting(
                id=f"meeting:{self.jurisdiction_id}:simbli:{meeting_date.isoformat()}",
                title=title,
                meeting_datetime=datetime.combine(meeting_date, datetime.min.time()),
                meeting_type=meeting_type,
                agenda_url=agenda_url,
                minutes_url=minutes_url,
                source_url=self.board_url,
                raw_html=row_html[:500] if row_html else None,
            )
            meetings.append(meeting)

        return meetings

    def _parse_link_meetings(
        self,
        html_content: str,
        text_content: str,  # Reserved for future use (e.g., context around links)
        since: date,
        limit: int,
    ) -> List[SimbliMeeting]:
        """Parse meetings from links in the page."""
        _ = text_content  # May be used for context extraction in future
        meetings: List[SimbliMeeting] = []

        # Look for links that contain meeting-related keywords
        link_pattern = re.compile(
            r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
            re.IGNORECASE
        )

        months = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }

        # Date patterns in link text
        date_pattern = re.compile(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(\d{1,2}),?\s+(\d{4})",
            re.IGNORECASE
        )

        seen_dates = set()

        for link_match in link_pattern.finditer(html_content):
            if len(meetings) >= limit:
                break

            href = link_match.group(1)
            link_text = link_match.group(2).strip()

            # Check if this looks like a meeting link
            if not any(kw in link_text.lower() or kw in href.lower()
                       for kw in ["meeting", "board", "session", "agenda", "minutes"]):
                continue

            # Try to extract date from link text
            date_match = date_pattern.search(link_text)
            if not date_match:
                # Try looking for date in href (e.g., "2026-01-15")
                href_date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", href)
                if href_date_match:
                    year = int(href_date_match.group(1))
                    month = int(href_date_match.group(2))
                    day = int(href_date_match.group(3))
                else:
                    continue
            else:
                month = months[date_match.group(1).lower()]
                day = int(date_match.group(2))
                year = int(date_match.group(3))

            try:
                meeting_date = date(year, month, day)
            except ValueError:
                continue

            # Skip duplicates and old meetings
            if meeting_date < since or meeting_date in seen_dates:
                continue
            seen_dates.add(meeting_date)

            # Determine meeting type and document type
            meeting_type = self._infer_meeting_type(link_text)

            # Determine if this is an agenda or minutes link
            agenda_url = None
            minutes_url = None

            if ".pdf" in href.lower():
                full_url = self._make_absolute_url(href)
                if "agenda" in link_text.lower() or "agnd" in href.lower():
                    agenda_url = full_url
                elif "minutes" in link_text.lower() or "min" in href.lower():
                    minutes_url = full_url

            title = self._generate_meeting_title(meeting_type, meeting_date)

            meeting = SimbliMeeting(
                id=f"meeting:{self.jurisdiction_id}:simbli:{meeting_date.isoformat()}",
                title=title,
                meeting_datetime=datetime.combine(meeting_date, datetime.min.time()),
                meeting_type=meeting_type,
                agenda_url=agenda_url,
                minutes_url=minutes_url,
                source_url=self.board_url,
            )
            meetings.append(meeting)

        return meetings

    def _infer_meeting_type(self, text: str) -> str:
        """Infer meeting type from text."""
        text_lower = text.lower()

        if "special" in text_lower:
            return "special"
        elif "study" in text_lower or "workshop" in text_lower:
            return "study_session"
        elif "closed" in text_lower or "executive" in text_lower:
            return "closed_session"
        elif "reorganization" in text_lower:
            return "reorganization"
        elif "emergency" in text_lower:
            return "emergency"
        else:
            return "regular"

    def _generate_meeting_title(self, meeting_type: str, meeting_date: date) -> str:
        """Generate a meeting title from type and date."""
        type_labels = {
            "regular": "Regular Board Meeting",
            "special": "Special Board Meeting",
            "study_session": "Study Session",
            "closed_session": "Closed Session",
            "reorganization": "Reorganization Meeting",
            "emergency": "Emergency Meeting",
        }

        label = type_labels.get(meeting_type, "Board Meeting")
        return f"{label} - {meeting_date.strftime('%B %d, %Y')}"

    def _find_pdf_link(self, html: str, keywords: List[str]) -> Optional[str]:
        """Find a PDF link in HTML that matches given keywords."""
        # Look for href attributes containing .pdf and keywords
        link_pattern = re.compile(
            r'href="([^"]*\.pdf[^"]*)"',
            re.IGNORECASE
        )

        for match in link_pattern.finditer(html):
            href = match.group(1)
            href_lower = href.lower()

            if any(kw in href_lower for kw in keywords):
                return self._make_absolute_url(href)

        return None

    def _make_absolute_url(self, href: str) -> str:
        """Convert relative URL to absolute."""
        if href.startswith("http"):
            return href
        elif href.startswith("/"):
            return f"{self.base_url}{href}"
        else:
            return f"{self.base_url}/{href}"

    def _discover_meeting_mids(
        self,
        meetings: List[SimbliMeeting],
    ) -> List[SimbliMeeting]:
        """
        Discover Simbli MIDs from meeting title link onclick handlers.

        Simbli stores meeting IDs (MIDs) in the onclick attribute of meeting
        title links, in the format: ViewMeeting("district_id","MID",...)
        This method extracts MIDs directly from these attributes without
        needing to click on each meeting.

        Args:
            meetings: List of meetings to populate with MIDs

        Returns:
            Updated list of meetings with simbli_mid populated where found
        """
        if not meetings or self._page is None:
            return meetings

        # Build a lookup by date for matching meetings
        meeting_by_date: Dict[str, SimbliMeeting] = {}
        for meeting in meetings:
            date_str = meeting.meeting_datetime.strftime("%Y-%m-%d")
            meeting_by_date[date_str] = meeting

        try:
            # Find all meeting title links in the table
            # Simbli uses links with onclick="ViewMeeting(...)" in the 2nd column
            meeting_links = self._page.query_selector_all(
                "table tr td:nth-child(2) a[onclick*='ViewMeeting']"
            )

            if not meeting_links:
                # Try alternate selector
                meeting_links = self._page.query_selector_all(
                    "table td a[onclick*='ViewMeeting']"
                )

            logger.info(f"Found {len(meeting_links)} meeting links with onclick handlers")

            for link in meeting_links:
                try:
                    onclick = link.get_attribute("onclick")
                    if not onclick:
                        continue

                    # Extract MID from onclick pattern: ViewMeeting("36030430","45989",...)
                    # The MID is the second parameter
                    mid_match = re.search(r'ViewMeeting\s*\(\s*"[^"]+"\s*,\s*"(\d+)"', onclick)
                    if not mid_match:
                        continue

                    mid = mid_match.group(1)

                    # Get the row containing this link to find the date
                    row = link.evaluate("el => el.closest('tr')")
                    if not row:
                        continue

                    # Find the date cell (first cell with date pattern)
                    row_elem = self._page.query_selector(f"table tr:has(a[onclick*='{mid}'])")
                    if not row_elem:
                        continue

                    date_cell = row_elem.query_selector("td:first-child span")
                    if not date_cell:
                        continue

                    date_text = date_cell.inner_text()

                    # Parse date from format like "12/16/2025 - 06:15 PM"
                    date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_text)
                    if date_match:
                        month = int(date_match.group(1))
                        day = int(date_match.group(2))
                        year = int(date_match.group(3))
                        date_str = f"{year:04d}-{month:02d}-{day:02d}"

                        if date_str in meeting_by_date:
                            meeting_by_date[date_str].simbli_mid = mid
                            logger.debug(f"Found MID {mid} for {date_str}")

                except Exception as e:
                    logger.debug(f"Error processing meeting link: {e}")
                    continue

        except Exception as e:
            logger.warning(f"MID discovery failed: {e}")

        return meetings

    def get_agenda_pdf(self, meeting: SimbliMeeting) -> Optional[bytes]:
        """
        Download agenda PDF for a meeting.

        Tries direct URL first, then falls back to MID-based download
        if simbli_mid is available.

        Args:
            meeting: SimbliMeeting with agenda_url or simbli_mid

        Returns:
            PDF bytes or None if unavailable
        """
        # Try direct URL first
        if meeting.agenda_url:
            pdf = self._download_pdf(meeting.agenda_url)
            if pdf:
                return pdf

        # Fall back to MID-based download
        if meeting.simbli_mid:
            return self.download_agenda_pdf_via_mid(meeting.simbli_mid)

        return None

    def download_agenda_pdf_via_mid(self, mid: str) -> Optional[bytes]:
        """
        Download agenda PDF using the Simbli MID-based workflow.

        Simbli uses a 2-step process to generate PDFs:
        1. Navigate to PrintAgenda.aspx with the MID (establishes session)
        2. Click Print button which triggers API call to PrintAgenda/PrintAgenda
        3. Parse the FileUrl from the JSON response
        4. Download the PDF from FileUrl

        Args:
            mid: Simbli meeting ID (e.g., "45989")

        Returns:
            PDF bytes or None if download fails
        """
        if not mid:
            return None

        try:
            self._init_browser()

            if self._page is None:
                logger.error("Browser not initialized for PDF download")
                return None

            # Extract district ID from board_url (S parameter)
            district_id = "36030430"  # Default for SRCS
            if "S=" in self.board_url:
                match = re.search(r"S=(\d+)", self.board_url)
                if match:
                    district_id = match.group(1)

            # Step 1: Navigate to PrintAgenda page to establish session
            print_url = f"{self.base_url}/SB_Meetings/PrintAgenda.aspx?S={district_id}&MID={mid}"
            logger.info(f"Navigating to PrintAgenda: {print_url}")

            if not self._navigate(print_url, wait_until="networkidle", timeout=30000):
                logger.error(f"Failed to navigate to PrintAgenda for MID {mid}")
                return None

            # Step 2: Click Print button and capture the API response
            print_button = self._page.query_selector("button:has-text('Print')")
            if not print_button:
                print_button = self._page.query_selector("input[value*='Print']")

            if print_button:
                # Click Print button and wait for API response using expect_response
                logger.info("Clicking Print button...")

                try:
                    # Wait for the PrintAgenda API response
                    with self._page.expect_response(
                        lambda r: "PrintAgenda/PrintAgenda?" in r.url and "GetFile" not in r.url,
                        timeout=15000
                    ) as response_info:
                        print_button.click()

                    response = response_info.value
                    logger.info(f"Got PrintAgenda response: {response.status} {response.url[:80]}")

                    # Parse the JSON response to get FileUrl
                    try:
                        import json
                        data = response.json()
                        if data.get("IsPass") and data.get("FileUrl"):
                            file_url = data["FileUrl"]
                            logger.info(f"Got FileUrl: {file_url}")
                            return self._download_pdf_from_url(file_url)
                        else:
                            logger.warning(f"PrintAgenda API returned: IsPass={data.get('IsPass')}")
                    except Exception as e:
                        logger.error(f"Error parsing PrintAgenda response: {e}")

                except Exception as e:
                    logger.error(f"Error waiting for PrintAgenda response: {e}")
            else:
                logger.warning("No Print button found on PrintAgenda page")

            return None

        except Exception as e:
            logger.error(
                "PDF download via MID failed",
                extra={"mid": mid, "error": str(e)},
            )
            return None

    def _download_pdf_from_url(self, file_url: str) -> Optional[bytes]:
        """
        Download PDF from a FileUrl.

        Args:
            file_url: URL path to the PDF (may be relative)

        Returns:
            PDF bytes or None if download fails
        """
        if self._page is None:
            return None

        try:
            # Make URL absolute if needed
            if file_url.startswith("/"):
                full_url = f"{self.base_url}{file_url}"
            else:
                full_url = file_url

            logger.info(f"Downloading PDF from: {full_url}")

            time.sleep(self.request_delay)

            # Download using Playwright's request context
            response = self._page.request.get(full_url)

            if response.ok:
                pdf_bytes = response.body()
                logger.info(f"Downloaded PDF: {len(pdf_bytes)} bytes")
                return pdf_bytes
            else:
                logger.error(f"PDF download failed with status {response.status}")
                return None

        except Exception as e:
            logger.error(f"PDF download from URL failed: {e}")
            return None

    def get_minutes_pdf(self, meeting: SimbliMeeting) -> Optional[bytes]:
        """
        Download minutes PDF for a meeting.

        Args:
            meeting: SimbliMeeting with minutes_url

        Returns:
            PDF bytes or None if unavailable
        """
        if not meeting.minutes_url:
            return None

        return self._download_pdf(meeting.minutes_url)

    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download a PDF file."""
        try:
            self._init_browser()

            if self._page is None:
                return None

            time.sleep(self.request_delay)

            # Use Playwright to download the file
            with self._page.expect_download() as download_info:
                self._page.goto(url)

            download = download_info.value
            path = download.path()

            if path:
                with open(path, "rb") as f:
                    return f.read()

            return None

        except Exception as e:
            logger.error(
                "PDF download failed",
                extra={"url": url, "error": str(e)},
            )
            return None


def create_srcs_simbli_client(headless: bool = True) -> SimbliClient:
    """
    Create Simbli client configured for San Rafael City Schools.

    SRCS uses Simbli hosted at eboardsolutions.com with district ID 36030430.
    URL pattern: https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S={district_id}

    Returns:
        Configured SimbliClient for SRCS
    """
    return SimbliClient(
        board_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
        jurisdiction_id="srcs",
        headless=headless,
    )


# ==================== Storage Mappers ====================


@runtime_checkable
class MeetingStorageProtocol(Protocol):
    """Protocol for storage backends that support meeting operations."""

    def store_meetings(
        self,
        jurisdiction_id: str,
        meetings: List[Dict[str, Any]],
    ) -> int:
        """Store meetings."""
        ...


def simbli_meeting_to_storage(
    meeting: SimbliMeeting,
    jurisdiction_id: str,
) -> Dict[str, Any]:
    """
    Map Simbli meeting to storage format.

    Args:
        meeting: SimbliMeeting from SimbliClient
        jurisdiction_id: Target jurisdiction

    Returns:
        Meeting dict ready for storage
    """
    raw_data: Dict[str, Any] = {}
    if meeting.attachments:
        raw_data["attachments"] = meeting.attachments
    if meeting.simbli_mid:
        raw_data["simbli_mid"] = meeting.simbli_mid

    return {
        "id": meeting.id,
        "title": meeting.title,
        "meeting_datetime": meeting.meeting_datetime.isoformat(),
        "jurisdiction_id": jurisdiction_id,
        "meeting_type": meeting.meeting_type,
        "status": "confirmed",
        "location": meeting.location,
        "agenda_url": meeting.agenda_url,
        "minutes_url": meeting.minutes_url,
        "source_platform": "simbli",
        "source_url": meeting.source_url,
        "raw_data": raw_data if raw_data else None,
    }


def extract_simbli_meetings_to_storage(
    client: SimbliClient,
    storage: MeetingStorageProtocol,
    jurisdiction_id: str,
    since: Optional[date] = None,
) -> int:
    """
    Extract meetings from Simbli and store them.

    Args:
        client: SimbliClient instance
        storage: StorageBackend instance with store_meetings method
        jurisdiction_id: Target jurisdiction
        since: Only extract meetings after this date

    Returns:
        Number of meetings stored
    """
    meetings = client.get_meetings(since=since)
    if not meetings:
        logger.info("No meetings returned from Simbli")
        return 0

    mapped = [simbli_meeting_to_storage(m, jurisdiction_id) for m in meetings]
    count = storage.store_meetings(jurisdiction_id, mapped)
    logger.info(f"Stored {count} meetings for {jurisdiction_id} from Simbli")
    return count
