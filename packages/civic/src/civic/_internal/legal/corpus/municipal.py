"""
Municipal code corpus via Municode API.

Fetches municipal code from Municode's public API, providing clean structured
access to ordinances without brittle PDF parsing.

San Rafael Municipal Code structure:
- Title X: Broad category (e.g., "Title 1 - GENERAL PROVISIONS")
- Chapter X.YY: Specific topic (e.g., "Chapter 1.04 - ADOPTION OF CODE")
- Section X.YY.ZZZ: Individual provision (e.g., "1.04.010 - Title.")

API Reference: https://sr.ht/~partytax/unofficial-municode-api-documentation/
"""

import re
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterator, Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass
class MunicipalCodeSection:
    """A single section from the municipal code."""
    section_number: str  # e.g., "1.04.010"
    section_title: str  # e.g., "Title."
    full_text: str  # Plain text content (HTML stripped)
    chapter: str  # e.g., "1.04"
    chapter_title: str  # e.g., "ADOPTION OF CODE"
    title_number: str  # e.g., "1"
    title_name: str  # e.g., "GENERAL PROVISIONS"
    node_id: str  # Municode node ID for reference
    ordinance_history: Optional[str] = None  # e.g., "(Ord. 1235 § 1, 1976)"


# Municode client lookup cache
_CLIENT_CACHE: dict[str, dict] = {}


class MunicipalCodeCorpus:
    """
    Fetch municipal code from Municode API.

    Uses Municode's public API to retrieve structured municipal code data.
    Much more reliable than PDF parsing.

    Args:
        jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")
        client_id: Municode client ID (auto-discovered if not provided)
        product_id: Municode product ID (auto-discovered if not provided)
        rate_limit: Requests per second (default: 2)
    """

    BASE_URL = "https://api.municode.com"

    # Known jurisdiction mappings
    # product_name defaults to "Code of Ordinances" if not specified
    JURISDICTION_MAP = {
        "city-san-rafael": {"state": "CA", "name": "San Rafael"},
        "city-berkeley": {"state": "CA", "name": "Berkeley"},
        "city-oakland": {"state": "CA", "name": "Oakland"},
        "county-marin": {"state": "CA", "name": "Marin County", "product_name": "Municipal Code"},
    }

    def __init__(
        self,
        jurisdiction_id: str = "city-san-rafael",
        client_id: Optional[int] = None,
        product_id: Optional[int] = None,
        rate_limit: float = 2.0,
    ):
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for Municode API access. "
                "Install with: pip install httpx"
            )

        self.jurisdiction_id = jurisdiction_id
        self._client_id = client_id
        self._product_id = product_id
        self._job_id: Optional[int] = None
        self.rate_limit = rate_limit
        self._last_request = 0.0
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    def _rate_limit(self):
        """Apply rate limiting."""
        elapsed = time.time() - self._last_request
        min_interval = 1.0 / self.rate_limit
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request = time.time()

    def _fetch(self, endpoint: str, params: dict = None) -> dict:
        """Fetch from Municode API with rate limiting."""
        self._rate_limit()
        client = self._get_client()
        url = f"{self.BASE_URL}/{endpoint}"
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _discover_client(self) -> tuple[int, int, int]:
        """Discover client_id, product_id, and job_id for jurisdiction."""
        if self._client_id and self._product_id and self._job_id:
            return self._client_id, self._product_id, self._job_id

        # Look up jurisdiction info
        if self.jurisdiction_id not in self.JURISDICTION_MAP:
            raise ValueError(
                f"Unknown jurisdiction: {self.jurisdiction_id}. "
                f"Known: {list(self.JURISDICTION_MAP.keys())}"
            )

        jur_info = self.JURISDICTION_MAP[self.jurisdiction_id]
        state = jur_info["state"]
        name = jur_info["name"]
        product_name = jur_info.get("product_name", "Code of Ordinances")

        # Check cache
        cache_key = f"{state}_{name}"
        if cache_key in _CLIENT_CACHE:
            cached = _CLIENT_CACHE[cache_key]
            return cached["client_id"], cached["product_id"], cached["job_id"]

        # Fetch clients for state
        clients = self._fetch("Clients/stateAbbr", {"stateAbbr": state})

        # Find matching client
        client_id = None
        for c in clients:
            if c["ClientName"].lower() == name.lower():
                client_id = c["ClientID"]
                break

        if not client_id:
            raise ValueError(f"Client not found in Municode: {name}, {state}")

        # Get product info
        product = self._fetch(
            "Products/name",
            {"clientId": client_id, "productName": product_name},
        )
        product_id = product["ProductID"]

        # Get latest job
        job = self._fetch(f"Jobs/latest/{product_id}")
        job_id = job["Id"]

        # Cache results
        _CLIENT_CACHE[cache_key] = {
            "client_id": client_id,
            "product_id": product_id,
            "job_id": job_id,
        }

        self._client_id = client_id
        self._product_id = product_id
        self._job_id = job_id

        return client_id, product_id, job_id

    def get_metadata(self) -> dict:
        """Get code metadata."""
        client_id, product_id, job_id = self._discover_client()
        job = self._fetch(f"Jobs/latest/{product_id}")

        return {
            "jurisdiction_id": self.jurisdiction_id,
            "client_id": client_id,
            "product_id": product_id,
            "job_id": job_id,
            "job_name": job.get("Name"),
            "publish_date": job.get("PublishDate"),
            "online_date": job.get("OnlineDate"),
            "banner_text": job.get("BannerText"),
            "source": "municode.com API",
        }

    def get_toc(self) -> list[dict]:
        """Get table of contents (top-level titles)."""
        _, product_id, job_id = self._discover_client()
        return self._fetch(
            "codesToc/children",
            {"jobId": job_id, "productId": product_id},
        )

    def _html_to_text(self, html: Optional[str]) -> str:
        """Convert HTML content to plain text."""
        if not html:
            return ""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        # Decode HTML entities
        text = unescape(text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_ordinance_history(self, html: Optional[str]) -> Optional[str]:
        """Extract ordinance history from HTML content."""
        if not html:
            return None
        match = re.search(r'class="historynote[^"]*"[^>]*>([^<]+)', html)
        if match:
            return match.group(1).strip()
        return None

    def stream_sections(
        self,
        title_ids: Optional[list[str]] = None,
    ) -> Iterator[MunicipalCodeSection]:
        """
        Stream code sections from Municode API.

        Args:
            title_ids: Optional list of title node IDs to fetch.
                      If None, fetches all titles.

        Yields:
            MunicipalCodeSection for each code section
        """
        _, product_id, job_id = self._discover_client()

        # Get top-level TOC
        toc = self.get_toc()

        # Filter to actual title nodes (skip charter, tables, etc.)
        titles = [
            node for node in toc
            if node["Heading"].startswith("Title ")
            and node.get("HasChildren", False)
        ]

        if title_ids:
            titles = [t for t in titles if t["Id"] in title_ids]

        for title_node in titles:
            title_id = title_node["Id"]
            title_heading = title_node["Heading"]

            # Parse title number and name
            title_match = re.match(r'Title\s+(\d+)\s*-\s*(.+)', title_heading)
            if title_match:
                title_number = title_match.group(1)
                title_name = title_match.group(2).strip()
            else:
                title_number = ""
                title_name = title_heading

            # Fetch all content for this title (includes chapters and sections)
            content = self._fetch(
                "CodesContent",
                {"jobId": job_id, "productId": product_id, "nodeId": title_id},
            )

            docs = content.get("Docs", [])

            # Track current chapter context
            current_chapter = ""
            current_chapter_title = ""

            for doc in docs:
                doc_id = doc.get("Id", "")
                heading = doc.get("Title", "")
                html_content = doc.get("Content", "")

                # Chapter detection (pattern-based, works at any depth)
                # Matches "Chapter X.YY - Title" or "Chapter XX.YY - Title"
                chapter_match = re.match(
                    r'Chapter\s+(\d+\.\d+)\s*-\s*(.+)', heading
                )
                if chapter_match:
                    current_chapter = chapter_match.group(1)
                    current_chapter_title = chapter_match.group(2).strip()
                    continue

                # Section detection (pattern-based, works at any depth)
                # Matches "X.YY.ZZZ - Title" or "XX.YY.ZZZ - Title"
                section_match = re.match(
                    r'(\d+\.\d+\.\d+)\s*-\s*(.+)', heading
                )
                if section_match:
                    section_number = section_match.group(1)
                    section_title = section_match.group(2).strip()

                    # Extract text and ordinance history
                    full_text = self._html_to_text(html_content)
                    ordinance_history = self._extract_ordinance_history(
                        html_content
                    )

                    yield MunicipalCodeSection(
                        section_number=section_number,
                        section_title=section_title,
                        full_text=full_text,
                        chapter=current_chapter,
                        chapter_title=current_chapter_title,
                        title_number=title_number,
                        title_name=title_name,
                        node_id=doc_id,
                        ordinance_history=ordinance_history,
                    )

    def get_sections_list(
        self,
        title_ids: Optional[list[str]] = None,
    ) -> list[MunicipalCodeSection]:
        """Get all sections as a list."""
        return list(self.stream_sections(title_ids))

    def to_documents(
        self,
        title_ids: Optional[list[str]] = None,
    ) -> Iterator[dict]:
        """
        Convert sections to document format for indexing.

        Yields documents matching VECTOR_RAG_SCHEMA.md municipal_code spec:
        - id: {jurisdiction_id}-muni-{section}
        - text: Formatted for embedding
        - metadata: Flat types only (string, int, float, bool)
        """
        for section in self.stream_sections(title_ids):
            # Build document ID per schema
            # city-san-rafael-muni-1-04-010
            section_parts = section.section_number.replace('.', '-')
            doc_id = f"{self.jurisdiction_id}-muni-{section_parts}"

            # Build text representation per schema
            text = f"""Chapter: {section.chapter} - {section.chapter_title}
Section: {section.section_number}
Title: {section.section_title}
Full Text: {section.full_text}"""

            # Build metadata (flat types only)
            metadata = {
                "muni_code_id": doc_id,
                "chapter": section.chapter,
                "section": section.section_number,
                "chapter_title": section.chapter_title[:500],
                "section_title": section.section_title[:200],
                "jurisdiction_id": self.jurisdiction_id,
                "title_number": section.title_number,
                "title_name": section.title_name,
                "hierarchy_level": 2,  # Section level
                "node_id": section.node_id,
            }

            if section.ordinance_history:
                metadata["ordinance_history"] = section.ordinance_history[:200]

            yield {
                "id": doc_id,
                "text": text,
                "metadata": metadata,
            }

    def close(self):
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


def parse_municipal_code(
    jurisdiction_id: str = "city-san-rafael",
    title_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Convenience function to fetch municipal code.

    Args:
        jurisdiction_id: Jurisdiction identifier
        title_ids: Optional list of title node IDs to fetch

    Returns:
        List of document dicts ready for indexing
    """
    corpus = MunicipalCodeCorpus(jurisdiction_id)
    try:
        return list(corpus.to_documents(title_ids))
    finally:
        corpus.close()


# Keep old name for backwards compatibility
def parse_municipal_code_pdf(
    pdf_path: str | Path,
    jurisdiction_id: str = "city-san-rafael",
) -> list[dict]:
    """
    Legacy function - now uses Municode API instead of PDF.

    Args:
        pdf_path: Ignored (kept for API compatibility)
        jurisdiction_id: Jurisdiction identifier

    Returns:
        List of document dicts ready for indexing
    """
    return parse_municipal_code(jurisdiction_id)
