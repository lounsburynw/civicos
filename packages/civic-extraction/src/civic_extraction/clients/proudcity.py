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
from typing import Dict, List, Optional, Any

from civic_extraction.clients.base import BaseExtractor, Meeting, HealthStatus

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

    # Default archive paths for common meeting types
    DEFAULT_ARCHIVES = {
        'city_council': '/city-council-meetings/',
        'planning_commission': '/planning-commission-meetings/',
        'fire_commission': '/fire-commission-meetings/',
        'tax_oversight': '/voter-approved-tax-oversight-committee-meetings/',
        'zoning_administrator': '/zoning-administrator-hearings/',
        'council_subcommittees': '/council-subcommittee-meetings/',
    }

    def __init__(
        self,
        base_url: str,
        jurisdiction_id: str,
        archives: Optional[Dict[str, str]] = None
    ):
        """
        Initialize ProudCity client.

        Args:
            base_url: Base URL of the municipal website (e.g., "https://www.cityofsanrafael.org")
            jurisdiction_id: Identifier for the jurisdiction (e.g., "city-san-rafael")
            archives: Optional dict mapping meeting_type to archive path.
                     Defaults to DEFAULT_ARCHIVES.
        """
        super().__init__(jurisdiction_id)
        self.base_url = base_url.rstrip('/')
        self.archives = archives or self.DEFAULT_ARCHIVES

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
        timeout: int = 30
    ) -> Optional[requests.Response]:
        """Make HTTP request with retries and exponential backoff."""
        self._throttle_request()

        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
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
            return {}

        soup = BeautifulSoup(response.content, 'html.parser')
        discovered = {}

        # Find all links ending in -meetings/ or -hearings/
        archive_pattern = re.compile(r'^/([a-z0-9-]+)-(meetings|hearings)/?$')

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')

            # Handle both relative and absolute URLs
            if href.startswith('http'):
                # Extract path from full URL
                if self.base_url in href:
                    href = href.replace(self.base_url, '')
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
            archive_url = f"{self.base_url}{path}"
            events = self._scrape_archive_page(archive_url, meeting_type)
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

    def _scrape_archive_page(
        self,
        archive_url: str,
        meeting_type: str
    ) -> List[Dict[str, Any]]:
        """
        Scrape a meeting archive page.

        Args:
            archive_url: URL of the archive page
            meeting_type: Type identifier for the meetings

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

            # Parse date from slug or text
            date_str = self._extract_date_from_slug(meeting_slug, text)

            if date_str:
                meeting = {
                    'title': text or meeting_slug.replace('-', ' ').title(),
                    'meeting_slug': meeting_slug,
                    'meeting_url': meeting_url.split('#')[0],
                    'date_parsed': date_str,
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
        """
        text = f"{slug} {title}"

        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }

        for month_name, month_num in months.items():
            # Pattern: october-6-2025 or october 6 2025
            pattern = rf'{month_name}[-\s]+(\d{{1,2}})[-\s]+(\d{{4}})'
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
        # Parse date
        meeting_datetime = None
        if event.get('date_parsed'):
            try:
                meeting_datetime = datetime.fromisoformat(event['date_parsed'])
            except ValueError:
                pass

        # Generate ID from slug
        meeting_id = f"proudcity-{self.jurisdiction_id}-{event.get('meeting_slug', 'unknown')}"

        return Meeting(
            id=meeting_id,
            title=event.get('title', 'Meeting'),
            meeting_datetime=meeting_datetime or datetime.now(),
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=event.get('meeting_type'),
            status="scheduled",
            agenda_url=event.get('meeting_url'),
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


# Convenience factory for San Rafael
def create_san_rafael_client() -> ProudCityClient:
    """
    Create a ProudCityClient configured for San Rafael.

    Returns:
        ProudCityClient configured with San Rafael's archive URLs
    """
    return ProudCityClient(
        base_url="https://www.cityofsanrafael.org",
        jurisdiction_id="city-san-rafael"
    )
