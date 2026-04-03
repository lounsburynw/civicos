"""
ProudCity Web Scraper Client

Extracts meeting data from ProudCity/WordPress-powered municipal websites.
ProudCity is a WordPress-based platform used by many California cities including San Rafael.

Usage:
    client = ProudCityClient(
        base_url="https://www.cityofsanrafael.org",
        jurisdiction_id="city-san-rafael"
    )
    events = client.get_events(days_ahead=30, days_past=30)
    meetings = client.get_meetings(days_ahead=30)  # Normalized
"""

import logging
import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from civicos_extraction.clients.base import BaseExtractor, Meeting, HealthStatus, ValidationResult

if TYPE_CHECKING:
    from civicos_extraction.cache import SourceCache

logger = logging.getLogger(__name__)


class ProudCityClient(BaseExtractor):
    """
    ProudCity/WordPress web scraper client.

    Scrapes meeting data from ProudCity-powered municipal websites by parsing
    archive pages and individual meeting pages.

    Features:
    - Scrapes multiple meeting type archives
    - Extracts PDF URLs (agenda packets, minutes)
    - Date filtering
    - Rate limiting
    """

    # Archives are discovered at onboarding time via discover_meeting_types()
    DEFAULT_ARCHIVES: Dict[str, str] = {}

    def __init__(
        self,
        base_url: str,
        jurisdiction_id: str,
        archives: Optional[Dict[str, str]] = None,
        cache: Optional["SourceCache"] = None,
    ):
        """
        Initialize ProudCity client.

        Args:
            base_url: Base URL of the municipal website (e.g., "https://www.cityofsanrafael.org")
            jurisdiction_id: Identifier for the jurisdiction (e.g., "city-san-rafael")
            archives: Optional dict mapping meeting_type to archive path.
                     Defaults to DEFAULT_ARCHIVES.
            cache: Optional SourceCache for caching HTTP responses in blob storage.
                   When provided, responses are cached with 24h TTL by default.
        """
        super().__init__(jurisdiction_id)
        self.base_url = base_url.rstrip('/')
        self.archives = archives or self.DEFAULT_ARCHIVES
        self.cache = cache

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Civic-Engagement-Platform/1.0 (Foundation-funded civic transparency tool)'
        })
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Be polite to servers

    @property
    def platform_name(self) -> str:
        return "proudcity"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"proudcity-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "proudcity"

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Performs a lightweight check by fetching the main meetings page
        and counting configured archive types without full data fetch.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        coverage_percent = None
        metadata: Dict[str, Any] = {}

        try:
            # Quick availability check: hit the main meetings page
            meetings_url = f"{self.base_url}/meetings/"
            response = self._make_request(meetings_url, retries=1, timeout=10)

            if response and response.status_code == 200:
                is_available = True

                # Get inventory counts (lightweight - just archive page scraping)
                inventory = self.get_source_inventory(include_coverage=True)
                available_count = inventory.get('total', 0)

                # Extract coverage info
                coverage = inventory.get('coverage', {})
                coverage_percent = coverage.get('coverage_percent')

                metadata = {
                    'by_type': inventory.get('by_type', {}),
                    'configured_count': coverage.get('configured_count', 0),
                    'discovered_count': coverage.get('discovered_count', 0),
                    'missing_types': coverage.get('missing', []),
                }
            else:
                status = response.status_code if response else 'no response'
                errors.append(f"Failed to reach {meetings_url}: {status}")

        except Exception as e:
            errors.append(f"Health check error: {str(e)}")
            logger.warning(
                "Health check failed",
                extra={
                    "error": str(e),
                    "jurisdiction_id": self.jurisdiction_id,
                    "platform": self.platform_name,
                }
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
            coverage_percent=coverage_percent,
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
        url: str,
        retries: int = 3,
        timeout: int = 30,
        use_cache: bool = True,
        cache_ttl_hours: int = 24,
    ) -> Optional[requests.Response]:
        """
        Make HTTP request with retries, exponential backoff, and optional caching.

        Args:
            url: URL to fetch
            retries: Number of retry attempts
            timeout: Request timeout in seconds
            use_cache: Whether to use cache (default True, requires self.cache)
            cache_ttl_hours: TTL for cached responses (default 24 hours)

        Returns:
            Response object or None if request failed
        """
        # Check cache first (if enabled and cache is configured)
        if use_cache and self.cache is not None:
            cached_content = self.cache.get(url)
            if cached_content is not None:
                logger.debug(
                    "Cache hit",
                    extra={
                        "url": url,
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                # Create a synthetic Response object
                response = requests.Response()
                response.status_code = 200
                response._content = cached_content
                response.url = url
                return response

        self._throttle_request()

        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()

                # Cache successful response (if caching enabled)
                if use_cache and self.cache is not None:
                    content_type = response.headers.get("Content-Type", "").split(";")[0]
                    self.cache.put(
                        url=url,
                        content=response.content,
                        ttl_hours=cache_ttl_hours,
                        content_type=content_type or None,
                    )
                    logger.debug(
                        "Cached response",
                        extra={
                            "url": url,
                            "content_type": content_type,
                            "ttl_hours": cache_ttl_hours,
                            "jurisdiction_id": self.jurisdiction_id,
                            "platform": self.platform_name,
                        }
                    )

                return response
            except requests.exceptions.Timeout as e:
                logger.warning(
                    "Request timeout",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "max_retries": retries,
                        "error_type": "timeout",
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(
                    "Request failed after all retries",
                    extra={
                        "url": url,
                        "total_attempts": retries,
                        "error_type": "timeout",
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                return None
            except requests.exceptions.ConnectionError as e:
                logger.warning(
                    "Connection error",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "max_retries": retries,
                        "error_type": "connection_error",
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(
                    "Request failed after all retries",
                    extra={
                        "url": url,
                        "total_attempts": retries,
                        "error_type": "connection_error",
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                return None
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else None
                logger.warning(
                    "HTTP error",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "max_retries": retries,
                        "error_type": "http_error",
                        "status_code": status_code,
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(
                    "Request failed after all retries",
                    extra={
                        "url": url,
                        "total_attempts": retries,
                        "error_type": "http_error",
                        "status_code": status_code,
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                return None
            except requests.RequestException as e:
                logger.warning(
                    "Request exception",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "max_retries": retries,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(
                    "Request failed after all retries",
                    extra={
                        "url": url,
                        "total_attempts": retries,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                    }
                )
                return None

        return None

    def discover_meeting_types(self) -> Dict[str, str]:
        """
        Discover all available meeting type archives by scraping main /meetings/ page.

        Scrapes the main meetings landing page to find all archive URLs dynamically,
        replacing the need for hardcoded DEFAULT_ARCHIVES.

        Returns:
            Dict mapping meeting_type_key to archive_path:
            {
                'city_council': '/city-council-meetings/',
                'planning_commission': '/planning-commission-meetings/',
                'ada_access_advisory_committee': '/ada-access-advisory-committee-meetings/',
                ...
            }
        """
        meetings_url = f"{self.base_url}/meetings/"
        response = self._make_request(meetings_url)
        if not response:
            logger.warning(
                "Failed to fetch meetings page for discovery",
                extra={
                    "url": meetings_url,
                    "jurisdiction_id": self.jurisdiction_id,
                    "platform": self.platform_name,
                }
            )
            # Try WP REST API before giving up — some ProudCity sites
            # (e.g., Belvedere) have /meetings/ at a non-standard path
            # but still expose meetings via the WordPress REST API.
            return self._discover_via_wp_api()

        soup = BeautifulSoup(response.content, 'html.parser')
        discovered = {}

        # Determine the resolved base URL (may differ from self.base_url after redirect)
        from urllib.parse import urlparse
        resolved_host = urlparse(str(response.url)).netloc

        # Find all links ending in -meetings/ or -hearings/
        archive_pattern = re.compile(r'^/([a-z0-9-]+)-(meetings|hearings|boards|committees|events|agendas|minutes)/?$')

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')

            # Handle both relative and absolute URLs
            if href.startswith('http'):
                # Extract path from full URL — accept both original and redirected domains
                parsed_href = urlparse(href)
                if parsed_href.netloc in (urlparse(self.base_url).netloc, resolved_host):
                    href = parsed_href.path
                else:
                    continue  # External link

            match = archive_pattern.match(href)
            if match:
                type_slug = match.group(1)  # e.g., "city-council"
                suffix = match.group(2)  # "meetings" or "hearings"

                # Convert slug to key: city-council -> city_council
                type_key = type_slug.replace('-', '_')

                # Normalize path with trailing slash
                path = f"/{type_slug}-{suffix}/"

                # Avoid duplicates (some pages have multiple links to same archive)
                if type_key not in discovered:
                    discovered[type_key] = path

        # If HTML scraping found no archive links, try the WP REST API.
        # Some ProudCity sites (e.g., Fairfax) use non-standard archive structures
        # but still expose meetings via the WordPress REST API.
        if not discovered:
            wp_api_result = self._discover_via_wp_api()
            if wp_api_result:
                discovered = wp_api_result

        logger.info(
            "Discovered meeting types",
            extra={
                "count": len(discovered),
                "types": list(discovered.keys()),
                "jurisdiction_id": self.jurisdiction_id,
                "platform": self.platform_name,
            }
        )

        return discovered

    def _discover_via_wp_api(self) -> Dict[str, str]:
        """Try WP REST API to discover meeting post types."""
        # Follow redirects to get the actual domain
        try:
            probe = self.session.get(
                f"{self.base_url}/wp-json/wp/v2/meetings?per_page=1",
                timeout=10,
                allow_redirects=True,
            )
            if probe.status_code == 200:
                data = probe.json()
                total = int(probe.headers.get("X-WP-Total", 0))
                if isinstance(data, list) and (data or total > 0):
                    # Store the resolved base URL for API calls
                    from urllib.parse import urlparse
                    resolved = urlparse(str(probe.url))
                    self._wp_api_base = f"{resolved.scheme}://{resolved.netloc}"
                    logger.info(f"WP REST API found: {total} meetings at {self._wp_api_base}")
                    return {"meetings": "_wp_api"}
        except Exception as e:
            logger.debug(f"WP REST API probe failed: {e}")

        return {}

    def get_source_inventory(self, include_coverage: bool = True) -> Dict[str, Any]:
        """
        Get inventory counts from source without full fetch.

        Scrapes archive pages to count available meetings per type,
        without downloading individual meeting details. Optionally includes
        coverage analysis comparing discovered vs configured meeting types.

        Args:
            include_coverage: If True, also discover all meeting types and
                              calculate coverage (configured vs discovered).

        Returns:
            Dict with counts per meeting type, total, and coverage:
            {
                'total': 85,
                'by_type': {
                    'city_council': 45,
                    'planning_commission': 23,
                    ...
                },
                'timestamp': '2025-01-15T10:30:00Z',
                'coverage': {
                    'configured_count': 6,
                    'discovered_count': 15,
                    'configured': ['city_council', 'planning_commission', ...],
                    'discovered': ['city_council', 'ada_access_advisory_committee', ...],
                    'missing': ['ada_access_advisory_committee', 'library_board', ...],
                    'coverage_percent': 40.0
                }
            }
        """
        inventory = {
            'total': 0,
            'by_type': {},
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        for meeting_type, path in self.archives.items():
            archive_url = f"{self.base_url}{path}"
            events = self._scrape_archive_page(archive_url, meeting_type)
            count = len(events)
            inventory['by_type'][meeting_type] = count
            inventory['total'] += count

        # Add coverage analysis if requested
        if include_coverage:
            discovered = self.discover_meeting_types()
            configured_keys = set(self.archives.keys())
            discovered_keys = set(discovered.keys())
            missing_keys = discovered_keys - configured_keys

            coverage_percent = (
                (len(configured_keys) / len(discovered_keys) * 100)
                if discovered_keys else 100.0
            )

            inventory['coverage'] = {
                'configured_count': len(configured_keys),
                'discovered_count': len(discovered_keys),
                'configured': sorted(configured_keys),
                'discovered': sorted(discovered_keys),
                'missing': sorted(missing_keys),
                'coverage_percent': round(coverage_percent, 1)
            }

            logger.info(
                "Source coverage calculated",
                extra={
                    "configured_count": len(configured_keys),
                    "discovered_count": len(discovered_keys),
                    "missing_count": len(missing_keys),
                    "coverage_percent": coverage_percent,
                    "jurisdiction_id": self.jurisdiction_id,
                    "platform": self.platform_name,
                }
            )

        return inventory

    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get events from all configured archive pages.

        Args:
            days_ahead: Days into the future to include
            days_past: Days into the past to include

        Returns:
            List of event dictionaries in platform-native format
        """
        start_date = (datetime.now() - timedelta(days=days_past)).strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

        all_events = []

        for meeting_type, path in self.archives.items():
            if path == "_wp_api":
                events = self._fetch_via_wp_api(
                    post_type=meeting_type,
                    start_date=start_date,
                    end_date=end_date,
                )
                all_events.extend(events)
            else:
                archive_url = f"{self.base_url}{path}"
                events = self._scrape_archive_page(
                    archive_url, meeting_type,
                    date_range=(start_date, end_date),
                )
                filtered = self._filter_by_date_range(events, start_date, end_date)
                all_events.extend(filtered)

        return all_events

    def get_events_by_type(
        self,
        meeting_type: str,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get events for a specific meeting type.

        Args:
            meeting_type: Type of meeting (must be in archives config)
            days_ahead: Days into the future
            days_past: Days into the past

        Returns:
            List of event dictionaries
        """
        if meeting_type not in self.archives:
            return []

        start_date = (datetime.now() - timedelta(days=days_past)).strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

        archive_url = f"{self.base_url}{self.archives[meeting_type]}"
        events = self._scrape_archive_page(archive_url, meeting_type)
        return self._filter_by_date_range(events, start_date, end_date)

    def _fetch_via_wp_api(
        self,
        post_type: str = "meetings",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch meetings from the WordPress REST API.

        Used for ProudCity sites with non-standard archive structures where
        HTML scraping fails but the WP REST API exposes meeting data.
        """
        from urllib.parse import urlparse

        # Use the resolved base URL if available (handles redirects)
        api_base = getattr(self, "_wp_api_base", self.base_url).rstrip("/")
        endpoint = f"{api_base}/wp-json/wp/v2/{post_type}"

        all_events = []
        page = 1
        per_page = 50
        max_pages = 50  # Safety limit

        while page <= max_pages:
            params: Dict[str, Any] = {"per_page": per_page, "page": page}
            if start_date:
                params["after"] = f"{start_date}T00:00:00"
            if end_date:
                params["before"] = f"{end_date}T23:59:59"

            time.sleep(self.min_request_interval)
            try:
                resp = self.session.get(endpoint, params=params, timeout=15)
                if resp.status_code != 200:
                    break
                posts = resp.json()
                if not posts:
                    break
            except Exception as e:
                logger.warning(f"WP API page {page} failed: {e}")
                break

            for post in posts:
                title_raw = post.get("title", {}).get("rendered", "")
                # Strip HTML entities
                title = re.sub(r"&#\d+;", lambda m: chr(int(m.group(0)[2:-1])), title_raw)
                title = re.sub(r"<[^>]+>", "", title).strip()

                # Parse the meeting date from the title (e.g., "Town Council Meeting: April 2, 2026")
                meeting_date = None
                date_match = re.search(
                    r"(?:January|February|March|April|May|June|July|August|September"
                    r"|October|November|December)\s+\d{1,2},?\s+\d{4}",
                    title,
                )
                if date_match:
                    for fmt in ("%B %d, %Y", "%B %d %Y"):
                        try:
                            meeting_date = datetime.strptime(date_match.group(), fmt).strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue

                if not meeting_date:
                    # Fall back to post publication date
                    meeting_date = post.get("date", "")[:10]

                # Extract body name by removing the date and any surrounding
                # punctuation/separators. This is separator-agnostic — works
                # whether the city uses ":" (Fairfax), "–" (San Rafael),
                # " - ", or any other convention.
                body_name = title
                if date_match:
                    body_name = title[:date_match.start()]
                # Strip trailing separators and whitespace
                body_name = re.sub(r"[\s:–—\-|/,]+$", "", body_name).strip()
                # Strip leading annotations like "(Cancelled)" or "(Special)"
                body_name = re.sub(r"\s*\([^)]*\)\s*$", "", body_name).strip()
                if not body_name:
                    body_name = "Meeting"

                # Build event dict compatible with normalize_event()
                content = post.get("content", {}).get("rendered", "")
                # Find PDF links in content
                pdf_urls = re.findall(r'href=["\']([^"\']+\.pdf)["\']', content, re.I)
                agenda_url = None
                minutes_url = None
                for pdf in pdf_urls:
                    pdf_lower = pdf.lower()
                    if "agenda" in pdf_lower or "packet" in pdf_lower:
                        agenda_url = agenda_url or pdf
                    elif "minute" in pdf_lower:
                        minutes_url = minutes_url or pdf

                # Extract slug from the link URL for unique meeting ID
                link_url = post.get("link", "")
                slug_match = re.search(r"/meetings/([^/]+)/?$", link_url)
                meeting_slug = slug_match.group(1) if slug_match else f"wp-{post.get('id', 'unknown')}"

                # Build event dict compatible with normalize_event()
                # Keys must match what normalize_event() reads:
                #   date_parsed, meeting_slug, title, meeting_type, meeting_url
                event = {
                    "title": title,
                    "date_parsed": meeting_date,
                    "meeting_slug": meeting_slug,
                    "meeting_type": body_name.lower().replace(" ", "_"),
                    "meeting_url": link_url,
                    "agenda_url": agenda_url,
                    "minutes_url": minutes_url,
                    "source": "wp_api",
                    "wp_id": post.get("id"),
                }
                all_events.append(event)

            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1

        logger.info(f"WP API fetched {len(all_events)} meetings from {api_base}")
        return all_events

    def _scrape_archive_page(
        self,
        archive_url: str,
        meeting_type: str,
        fetch_individual_pages: bool = True,
        date_range: Optional[Tuple[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scrape a meeting archive page.

        Args:
            archive_url: URL of the archive page
            meeting_type: Type identifier for the meetings
            fetch_individual_pages: If True, fetch each meeting page to get
                accurate date/time (slower but more accurate). If False, only
                parse dates from URL slugs.
            date_range: Optional (start_date, end_date) as YYYY-MM-DD strings.
                When provided, meetings outside this range (based on slug date)
                are skipped without fetching individual pages, avoiding hundreds
                of unnecessary HTTP requests during incremental refreshes.

        Returns:
            List of meeting dictionaries
        """
        response = self._make_request(archive_url)
        if not response:
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        meetings = []

        # Find all meeting links - ProudCity uses /meetings/ pattern
        meeting_links = soup.find_all('a', href=re.compile(r'/meetings/.*'))

        for link in meeting_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)

            if not href or '/meetings/' not in href:
                continue

            # Build full URL
            if href.startswith('http'):
                meeting_url = href
            else:
                meeting_url = f"{self.base_url}{href}"

            # Extract meeting slug
            match = re.search(r'/meetings/([^/]+)/?', meeting_url)
            if not match:
                continue

            meeting_slug = match.group(1)

            # Parse date from slug or text (fallback)
            slug_date = self._extract_date_from_slug(meeting_slug, text)

            if slug_date:
                # Skip meetings outside date range early (before expensive page fetch)
                if date_range:
                    start_dt, end_dt = date_range
                    if slug_date < start_dt or slug_date > end_dt:
                        continue

                # Fetch individual page to get accurate date/time
                actual_date = slug_date
                meeting_time = None

                if fetch_individual_pages:
                    actual_date, meeting_time = self._extract_date_from_meeting_page(
                        meeting_url.split('#')[0],
                        fallback_date=slug_date
                    )

                meeting = {
                    'title': text or meeting_slug.replace('-', ' ').title(),
                    'meeting_slug': meeting_slug,
                    'meeting_url': meeting_url.split('#')[0],
                    'date_parsed': actual_date,
                    'slug_date': slug_date,  # Keep original for debugging
                    'meeting_time': meeting_time,
                    'meeting_type': meeting_type,
                    'source_archive': archive_url
                }

                # Avoid duplicates
                if not any(m['meeting_slug'] == meeting_slug for m in meetings):
                    meetings.append(meeting)

        return meetings

    def _extract_date_from_slug(
        self,
        slug: str,
        title: str = ''
    ) -> Optional[str]:
        """
        Extract ISO date from meeting slug or title.

        Examples:
        - city-council-october-6-2025 -> 2025-10-06
        - planning-commission-november-4-2025-special-meeting -> 2025-11-04
        - "January 10, 2026" (title with comma) -> 2026-01-10
        """
        text = f"{slug} {title}"

        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }

        for month_name, month_num in months.items():
            # Pattern: october-6-2025 or october 6 2025 or october 6, 2025
            pattern = rf'{month_name}[-\s,]+(\d{{1,2}})[-\s,]+(\d{{4}})'
            match = re.search(pattern, text.lower())
            if match:
                day = int(match.group(1))
                year = int(match.group(2))
                try:
                    date_obj = datetime(year, month_num, day)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    pass

        return None

    def _extract_date_from_meeting_page(
        self,
        meeting_url: str,
        fallback_date: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Fetch individual meeting page and extract actual date/time from content.

        ProudCity pages sometimes have URL slugs with incorrect dates while the
        page content shows the correct date. This method fetches the page and
        parses the displayed date/time.

        Args:
            meeting_url: URL of the individual meeting page
            fallback_date: Date parsed from slug to use if page fetch fails

        Returns:
            Tuple of (ISO date string, time string) e.g. ('2026-01-22', '18:00')
        """
        response = self._make_request(meeting_url)
        if not response:
            return fallback_date, None

        soup = BeautifulSoup(response.content, 'html.parser')

        # Get all text content from the page
        text_content = soup.get_text(separator='\n')

        # Month mappings for both full and abbreviated forms
        months_full = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        months_abbrev = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }

        parsed_date = None
        parsed_time = None

        # Try abbreviated month format first (e.g., "Jan 22 2026")
        # This is typically the actual event date displayed on the page
        for month_abbrev, month_num in months_abbrev.items():
            # Pattern: Jan 22 2026 or Jan 22, 2026
            pattern = rf'\b{month_abbrev}\s+(\d{{1,2}})[,]?\s+(\d{{4}})\b'
            match = re.search(pattern, text_content.lower())
            if match:
                day = int(match.group(1))
                year = int(match.group(2))
                try:
                    date_obj = datetime(year, month_num, day)
                    parsed_date = date_obj.strftime('%Y-%m-%d')
                    break
                except ValueError:
                    pass

        # If no abbreviated match, try full month names
        if not parsed_date:
            for month_name, month_num in months_full.items():
                # Pattern: January 22, 2026 or January 22 2026
                pattern = rf'\b{month_name}\s+(\d{{1,2}})[,]?\s+(\d{{4}})\b'
                match = re.search(pattern, text_content.lower())
                if match:
                    day = int(match.group(1))
                    year = int(match.group(2))
                    try:
                        date_obj = datetime(year, month_num, day)
                        parsed_date = date_obj.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        pass

        # Extract time (e.g., "6:00 pm", "6:00pm", "18:00")
        time_pattern = r'\b(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)?\b'
        time_matches = re.findall(time_pattern, text_content)
        for hour, minute, ampm in time_matches:
            hour = int(hour)
            minute = int(minute)
            if ampm and ampm.lower() == 'pm' and hour != 12:
                hour += 12
            elif ampm and ampm.lower() == 'am' and hour == 12:
                hour = 0
            # Skip times that look like page metadata (very early morning)
            if 6 <= hour <= 22:  # Reasonable meeting hours
                parsed_time = f"{hour:02d}:{minute:02d}"
                break

        # Use fallback if page parsing failed
        if not parsed_date:
            parsed_date = fallback_date

        return parsed_date, parsed_time

    def _filter_by_date_range(
        self,
        meetings: List[Dict[str, Any]],
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """Filter meetings by date range."""
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)

        filtered = []
        for meeting in meetings:
            if meeting.get('date_parsed'):
                try:
                    meeting_dt = datetime.fromisoformat(meeting['date_parsed'])
                    if start_dt <= meeting_dt <= end_dt:
                        filtered.append(meeting)
                except ValueError:
                    pass

        return filtered

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """
        Normalize ProudCity event to Meeting format.

        Args:
            event: Raw event dictionary from scraping

        Returns:
            Normalized Meeting object
        """
        # Parse date and time
        meeting_datetime = None
        if event.get('date_parsed'):
            try:
                date_str = event['date_parsed']
                time_str = event.get('meeting_time')

                if time_str:
                    # Combine date and time
                    meeting_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")
                else:
                    meeting_datetime = datetime.fromisoformat(date_str)
            except ValueError:
                pass

        # Generate namespaced ID from slug
        slug = event.get('meeting_slug', 'unknown')
        meeting_id = f"meeting:{self.jurisdiction_id}:proudcity:{slug}"

        return Meeting(
            id=meeting_id,
            title=event.get('title', 'Meeting'),
            meeting_datetime=meeting_datetime or datetime.now(),
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=event.get('meeting_type'),
            status="scheduled",
            agenda_url=event.get('agenda_url') or event.get('meeting_url'),
            minutes_url=event.get('minutes_url'),
            source_platform="proudcity",
            source_url=event.get('meeting_url'),
            raw_data=event
        )

    def get_meeting_pdfs(self, meeting_url: str) -> Dict[str, Optional[str]]:
        """
        Extract PDF URLs from a meeting page.

        Args:
            meeting_url: URL of the meeting page

        Returns:
            Dict with agenda_packet_url, minutes_url, and individual_items
        """
        result = {
            'agenda_packet_url': None,
            'minutes_url': None,
            'individual_items': []
        }

        response = self._make_request(meeting_url)
        if not response:
            return result

        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract all PDF URLs
        all_pdf_urls = self._extract_all_pdf_urls(soup)

        # Find agenda packet
        agenda_packet_patterns = [
            r'agenda-packet.*\.pdf',
            r'full.*packet.*\.pdf',
            r'complete.*agenda.*\.pdf',
            r'packet.*\d{4}-\d{2}-\d{2}.*\.pdf'
        ]

        for pattern in agenda_packet_patterns:
            for url in all_pdf_urls:
                if re.search(pattern, url, re.I):
                    result['agenda_packet_url'] = url
                    break
            if result['agenda_packet_url']:
                break

        # Try #tab-agenda-packet section
        if not result['agenda_packet_url']:
            agenda_packet_tab = soup.find('div', {'id': 'tab-agenda-packet'})
            if agenda_packet_tab:
                tab_pdfs = self._extract_pdf_urls_from_element(agenda_packet_tab)
                if tab_pdfs:
                    result['agenda_packet_url'] = tab_pdfs[0]

        # Find minutes - try #tab-minutes section first
        minutes_tab = soup.find('div', {'id': 'tab-minutes'})
        if minutes_tab:
            tab_pdfs = self._extract_pdf_urls_from_element(minutes_tab)
            if tab_pdfs:
                result['minutes_url'] = tab_pdfs[0]

        # Fallback: pattern matching for minutes
        if not result['minutes_url']:
            minutes_patterns = [
                r'cc-minutes.*\d{4}-\d{2}-\d{2}.*\.pdf',
                r'minutes-\d{4}-\d{2}-\d{2}.*\.pdf',
                r'\d{8}-cc-minutes.*\.pdf'
            ]

            for pattern in minutes_patterns:
                for url in all_pdf_urls:
                    if re.search(pattern, url, re.I):
                        result['minutes_url'] = url
                        break
                if result['minutes_url']:
                    break

        return result

    def _extract_all_pdf_urls(self, soup: BeautifulSoup) -> List[str]:
        """Extract all PDF URLs from a BeautifulSoup object."""
        pdf_urls = []

        # Links
        for link in soup.find_all('a', href=re.compile(r'\.pdf', re.I)):
            href = link.get('href')
            if href:
                pdf_urls.append(self._make_absolute_url(href))

        # Embeds
        for embed in soup.find_all('embed', src=re.compile(r'\.pdf', re.I)):
            src = embed.get('src')
            if src:
                pdf_urls.append(self._make_absolute_url(src))

        # iframes
        for iframe in soup.find_all('iframe', src=re.compile(r'\.pdf', re.I)):
            src = iframe.get('src')
            if src:
                pdf_urls.append(self._make_absolute_url(src))

        # objects
        for obj in soup.find_all('object', attrs={'data': re.compile(r'\.pdf', re.I)}):
            data = obj.get('data')
            if data:
                pdf_urls.append(self._make_absolute_url(data))

        return pdf_urls

    def _extract_pdf_urls_from_element(self, element) -> List[str]:
        """Extract PDF URLs from a specific HTML element."""
        pdf_urls = []

        for link in element.find_all('a', href=re.compile(r'\.pdf', re.I)):
            href = link.get('href')
            if href:
                pdf_urls.append(self._make_absolute_url(href))

        for embed in element.find_all('embed', src=re.compile(r'\.pdf', re.I)):
            src = embed.get('src')
            if src:
                pdf_urls.append(self._make_absolute_url(src))

        for iframe in element.find_all('iframe', src=re.compile(r'\.pdf', re.I)):
            src = iframe.get('src')
            if src:
                pdf_urls.append(self._make_absolute_url(src))

        for obj in element.find_all('object', attrs={'data': re.compile(r'\.pdf', re.I)}):
            data = obj.get('data')
            if data:
                pdf_urls.append(self._make_absolute_url(data))

        return pdf_urls

    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute."""
        if url.startswith('http'):
            return url
        return f"{self.base_url}{url}"


class ProudCitySource:
    """
    Config-driven wrapper for ProudCityClient implementing DataSource protocol.

    Loads extraction configuration from JSON files and creates a properly
    configured ProudCityClient. Provides config-driven setup for city onboarding.

    Usage:
        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        client = source.client
        health = source.health()

        # With caching:
        from civicos.storage import get_blob_storage
        from civicos_extraction.cache import SourceCache
        blob = get_blob_storage()
        cache = SourceCache(blob) if blob else None
        source = ProudCitySource.from_jurisdiction("city-san-rafael", cache=cache)
    """

    def __init__(self, config: "ExtractionConfig", cache: Optional["SourceCache"] = None):
        """
        Initialize ProudCitySource from an ExtractionConfig.

        Args:
            config: ExtractionConfig loaded from JSON
            cache: Optional SourceCache for caching HTTP responses
        """
        from civicos_extraction.clients.base import ExtractionConfig
        self._config = config
        self._cache = cache
        self._client = ProudCityClient(
            base_url=config.base_url,
            jurisdiction_id=config.jurisdiction_id,
            archives=config.archives if config.archives else None,
            cache=cache,
        )

    @classmethod
    def from_jurisdiction(
        cls, jurisdiction_id: str, cache: Optional["SourceCache"] = None
    ) -> "ProudCitySource":
        """
        Create ProudCitySource from jurisdiction ID, loading config from file.

        Args:
            jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
            cache: Optional SourceCache for caching HTTP responses

        Returns:
            Configured ProudCitySource
        """
        from civicos_extraction.clients.base import ExtractionConfig
        config = ExtractionConfig.from_jurisdiction(jurisdiction_id)
        return cls(config, cache=cache)

    @classmethod
    def from_config_file(
        cls, path: str, cache: Optional["SourceCache"] = None
    ) -> "ProudCitySource":
        """
        Create ProudCitySource from a specific config file path.

        Args:
            path: Path to extraction config JSON file
            cache: Optional SourceCache for caching HTTP responses

        Returns:
            Configured ProudCitySource
        """
        from civicos_extraction.clients.base import ExtractionConfig
        config = ExtractionConfig.from_file(path)
        return cls(config, cache=cache)

    @property
    def client(self) -> ProudCityClient:
        """Get the underlying ProudCityClient."""
        return self._client

    @property
    def config(self) -> "ExtractionConfig":
        """Get the extraction configuration."""
        return self._config

    @property
    def cache(self) -> Optional["SourceCache"]:
        """Get the source cache (if configured)."""
        return self._cache

    def cache_stats(self) -> Optional[dict]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate, entry_count, or None if no cache
        """
        if self._cache is not None:
            return self._cache.stats()
        return None

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return self._client.source_id

    @property
    def source_type(self) -> str:
        """Type of source."""
        return self._client.source_type

    def health(self) -> HealthStatus:
        """Check source availability via underlying client."""
        return self._client.health()

    def validate(self) -> ValidationResult:
        """
        Validate source configuration and API access before running pipeline.

        Preflight check that fails fast with clear error messages for:
        - Missing or invalid config fields
        - Unreachable API endpoints
        - Empty archives without auto_discover enabled

        Returns:
            ValidationResult with is_valid, errors, warnings, and timing
        """
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        # Check required config fields
        if not self._config.base_url:
            errors.append("base_url is required")
            config_valid = False
        elif not self._config.base_url.startswith("https://"):
            errors.append(f"base_url must use HTTPS: {self._config.base_url}")
            config_valid = False

        if not self._config.jurisdiction_id:
            errors.append("jurisdiction_id is required")
            config_valid = False

        if not self._config.source_id:
            errors.append("source_id is required")
            config_valid = False

        # Check that archives are configured or auto_discover is enabled
        if not self._config.archives and not self._config.auto_discover:
            errors.append("archives is empty and auto_discover is not enabled")
            config_valid = False

        # Check API reachability (only if config is valid)
        if config_valid:
            try:
                meetings_url = f"{self._config.base_url}/meetings/"
                response = self._client._make_request(meetings_url, retries=1, timeout=10)
                if response and response.status_code == 200:
                    api_reachable = True
                    metadata["main_page_status"] = 200
                else:
                    status = response.status_code if response else "no response"
                    errors.append(f"Cannot reach {meetings_url}: HTTP {status}")
                    metadata["main_page_status"] = status
            except Exception as e:
                errors.append(f"Cannot reach {self._config.base_url}: {str(e)}")
                metadata["connection_error"] = str(e)

        # Validate archive paths (only if API is reachable and archives configured)
        if api_reachable and self._config.archives:
            archive_checks = {}
            for meeting_type, path in self._config.archives.items():
                if not path.startswith("/"):
                    warnings.append(f"Archive path for {meeting_type} should start with /: {path}")
                try:
                    archive_url = f"{self._config.base_url}{path}"
                    response = self._client._make_request(archive_url, retries=1, timeout=10)
                    if response and response.status_code == 200:
                        archive_checks[meeting_type] = "ok"
                    else:
                        status = response.status_code if response else "no response"
                        warnings.append(f"Archive unreachable: {meeting_type} ({path}) - HTTP {status}")
                        archive_checks[meeting_type] = f"error: {status}"
                except Exception as e:
                    warnings.append(f"Archive check failed: {meeting_type} ({path}) - {str(e)}")
                    archive_checks[meeting_type] = f"error: {str(e)}"
            metadata["archive_checks"] = archive_checks

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

    def get_events(self, days_ahead: int = 90, days_past: int = 0):
        """Extract events from the underlying client."""
        return self._client.get_events(days_ahead=days_ahead, days_past=days_past)

    def get_meetings(self, days_ahead: int = 90, days_past: int = 0):
        """Get normalized meetings from the underlying client."""
        return self._client.get_meetings(days_ahead=days_ahead, days_past=days_past)


# Convenience factory for San Rafael
def create_san_rafael_client(use_config: bool = True) -> ProudCityClient:
    """
    Create a ProudCityClient configured for San Rafael.

    Args:
        use_config: If True (default), load archives from config file.
                   If False, use DEFAULT_ARCHIVES for backward compatibility.

    Returns:
        ProudCityClient configured with San Rafael's archive URLs
    """
    if use_config:
        try:
            source = ProudCitySource.from_jurisdiction("city-san-rafael")
            return source.client
        except FileNotFoundError:
            # Fall back to hardcoded defaults if config not found
            pass

    return ProudCityClient(
        base_url="https://www.cityofsanrafael.org",
        jurisdiction_id="city-san-rafael"
    )


def create_san_rafael_source() -> ProudCitySource:
    """
    Create a config-driven ProudCitySource for San Rafael.

    Returns:
        ProudCitySource with full config access
    """
    return ProudCitySource.from_jurisdiction("city-san-rafael")
