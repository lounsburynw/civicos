"""
California Legislature corpus fetcher.

Fetches bill data from leginfo.legislature.ca.gov for indexing and search.

Data Source:
    California's Open Data Portal provides bill data via the Legislative Open Data
    API. Bills are available in multiple formats including HTML and XML.

    API Base: https://leginfo.legislature.ca.gov/faces/billSearchClient.xhtml
    Open Data: https://data.ca.gov/dataset/california-legislation

Architecture:
    1. Session discovery - enumerate available legislative sessions
    2. Bill enumeration - get all bills for a session
    3. Bill detail fetching - get full text and metadata
    4. Rate limiting - respect API limits

Usage:
    corpus = CaliforniaCorpus()

    # Fetch current session
    bills = await corpus.fetch_session("2023-2024")

    # Fetch specific bill
    bill = await corpus.fetch_bill("AB-1234", session="2023-2024")

    # Stream bills for indexing
    async for bill in corpus.stream_bills("2023-2024"):
        process(bill)
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Optional
from enum import Enum

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None


class BillType(Enum):
    """California bill types."""
    AB = "Assembly Bill"
    SB = "Senate Bill"
    ACA = "Assembly Constitutional Amendment"
    SCA = "Senate Constitutional Amendment"
    ACR = "Assembly Concurrent Resolution"
    SCR = "Senate Concurrent Resolution"
    AJR = "Assembly Joint Resolution"
    SJR = "Senate Joint Resolution"
    AR = "Assembly Resolution"
    SR = "Senate Resolution"


class BillStatus(Enum):
    """Bill lifecycle status."""
    INTRODUCED = "introduced"
    IN_COMMITTEE = "in_committee"
    PASSED_HOUSE = "passed_house"
    PASSED_BOTH = "passed_both"
    ENROLLED = "enrolled"
    SIGNED = "signed"
    VETOED = "vetoed"
    CHAPTERED = "chaptered"
    DEAD = "dead"


@dataclass
class BillMetadata:
    """Metadata for a California bill."""
    bill_id: str  # e.g., "AB-1234"
    session: str  # e.g., "2023-2024"
    title: str
    author: str
    coauthors: list[str] = field(default_factory=list)
    bill_type: BillType = BillType.AB
    status: BillStatus = BillStatus.INTRODUCED
    introduced_date: Optional[datetime] = None
    last_amended_date: Optional[datetime] = None
    subject: Optional[str] = None
    digest: Optional[str] = None  # Short summary
    topics: list[str] = field(default_factory=list)
    url: Optional[str] = None


@dataclass
class BillDocument:
    """Full bill document with text content."""
    metadata: BillMetadata
    full_text: str  # Full bill text (may be HTML or plain)
    sections: list[dict] = field(default_factory=list)  # Parsed sections
    amendments: list[dict] = field(default_factory=list)  # Amendment history
    fetched_at: datetime = field(default_factory=datetime.now)


class CaliforniaCorpus:
    """
    Fetches California legislation from leginfo.legislature.ca.gov.

    NOTE: This is scaffold code for future implementation. For the pilot,
    California legislation is pre-loaded into PostgreSQL. The methods below
    provide basic functionality but are not fully implemented.

    The California Legislature provides bill data through their public website.
    This class handles:
    - Session enumeration
    - Bill listing and pagination
    - Full text retrieval
    - Rate limiting to respect server limits

    Args:
        rate_limit: Requests per second (default: 2)
        timeout: Request timeout in seconds (default: 30)
        cache_dir: Optional local cache directory
    """

    BASE_URL = "https://leginfo.legislature.ca.gov"
    SEARCH_URL = f"{BASE_URL}/faces/billSearchClient.xhtml"
    BILL_URL = f"{BASE_URL}/faces/billNavClient.xhtml"

    # Known sessions (updated periodically)
    SESSIONS = [
        "2023-2024",
        "2021-2022",
        "2019-2020",
        "2017-2018",
        "2015-2016",
    ]

    def __init__(
        self,
        rate_limit: float = 2.0,
        timeout: float = 30.0,
        cache_dir: Optional[str] = None,
    ):
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for corpus fetching. "
                "Install with: pip install civicos-legal"
            )

        self.rate_limit = rate_limit
        self.timeout = timeout
        self.cache_dir = cache_dir
        self._last_request = 0.0
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "CaliforniaCorpus":
        """Context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "User-Agent": "CivicPlatform/1.0 (civicos-legal; research)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request
        min_interval = 1.0 / self.rate_limit

        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)

        self._last_request = asyncio.get_event_loop().time()

    def _parse_bill_id(self, bill_id: str) -> tuple[str, str]:
        """
        Parse bill ID into type and number.

        Args:
            bill_id: Bill identifier like "AB-1234" or "SB 123"

        Returns:
            Tuple of (bill_type, number) e.g., ("AB", "1234")
        """
        # Normalize format
        bill_id = bill_id.upper().replace(" ", "-").replace("_", "-")

        # Extract type and number
        match = re.match(r"([A-Z]+)-?(\d+)", bill_id)
        if not match:
            raise ValueError(f"Invalid bill ID format: {bill_id}")

        return match.group(1), match.group(2)

    async def get_sessions(self) -> list[str]:
        """
        Get available legislative sessions.

        Returns:
            List of session identifiers (e.g., ["2023-2024", "2021-2022"])
        """
        # Returns known sessions (dynamic discovery not implemented)
        return self.SESSIONS.copy()

    async def fetch_bill(
        self,
        bill_id: str,
        session: str = "2023-2024",
    ) -> Optional[BillDocument]:
        """
        Fetch a specific bill by ID.

        Args:
            bill_id: Bill identifier (e.g., "AB-1234", "SB 567")
            session: Legislative session (e.g., "2023-2024")

        Returns:
            BillDocument with full text and metadata, or None if not found
        """
        if not self._client:
            raise RuntimeError("Use async context manager: async with CaliforniaCorpus()")

        await self._rate_limit()

        bill_type, number = self._parse_bill_id(bill_id)

        # Construct URL
        url = f"{self.BILL_URL}?bill_id={session}0{bill_type}{number}"

        try:
            response = await self._client.get(url)
            response.raise_for_status()

            # Parse HTML response
            html = response.text

            # Extract metadata and text (basic regex parsing)
            metadata = BillMetadata(
                bill_id=f"{bill_type}-{number}",
                session=session,
                title=self._extract_title(html),
                author=self._extract_author(html),
                url=str(response.url),
            )

            return BillDocument(
                metadata=metadata,
                full_text=self._extract_bill_text(html),
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def fetch_session(
        self,
        session: str = "2023-2024",
        bill_types: Optional[list[BillType]] = None,
    ) -> list[BillDocument]:
        """
        Fetch all bills for a legislative session.

        Args:
            session: Legislative session (e.g., "2023-2024")
            bill_types: Filter by bill types (default: AB and SB only)

        Returns:
            List of BillDocument objects
        """
        bills = []
        async for bill in self.stream_bills(session, bill_types):
            bills.append(bill)
        return bills

    async def stream_bills(
        self,
        session: str = "2023-2024",
        bill_types: Optional[list[BillType]] = None,
    ) -> AsyncIterator[BillDocument]:
        """
        Stream bills from a session for memory-efficient processing.

        Args:
            session: Legislative session
            bill_types: Filter by bill types

        Yields:
            BillDocument objects
        """
        if bill_types is None:
            bill_types = [BillType.AB, BillType.SB]

        # Get bill list
        bill_ids = await self._enumerate_bills(session, bill_types)

        for bill_id in bill_ids:
            bill = await self.fetch_bill(bill_id, session)
            if bill:
                yield bill

    async def _enumerate_bills(
        self,
        session: str,
        bill_types: list[BillType],
    ) -> list[str]:
        """
        Enumerate all bill IDs for a session.

        Returns list of bill IDs like ["AB-1", "AB-2", ..., "SB-1", ...]
        """
        if not self._client:
            raise RuntimeError("Use async context manager")

        # Bill enumeration not implemented (scaffold)
        return []

    def _extract_title(self, html: str) -> str:
        """Extract bill title from HTML (basic regex)."""
        match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
        return match.group(1) if match else "Unknown"

    def _extract_author(self, html: str) -> str:
        """Extract bill author from HTML (not implemented)."""
        _ = html  # Unused in scaffold
        return "Unknown"

    def _extract_bill_text(self, html: str) -> str:
        """Extract bill text content from HTML (naive tag stripping)."""
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


# Convenience function for one-off fetches
async def fetch_california_bill(
    bill_id: str,
    session: str = "2023-2024",
) -> Optional[BillDocument]:
    """
    Convenience function to fetch a single California bill.

    Args:
        bill_id: Bill identifier (e.g., "AB-1234")
        session: Legislative session

    Returns:
        BillDocument or None
    """
    async with CaliforniaCorpus() as corpus:
        return await corpus.fetch_bill(bill_id, session)
