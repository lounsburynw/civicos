"""
Modal function for U.S. Code ingestion to PostgreSQL.

Downloads directly from uscode.house.gov and ingests to Supabase.
Runs in cloud (close to Supabase) - no local upload needed.
Uses PostgreSQL COPY for fast bulk inserts (~10 seconds for 7k sections).

Setup:
    Ensure Modal secret exists:
    modal secret create civic-db DATABASE_URL="postgresql://..."

Usage:
    # Ingest Title 42 (downloads from uscode.house.gov)
    modal run scripts/modal_uscode.py --title 42

    # Dry run (download and parse only)
    modal run scripts/modal_uscode.py --title 42 --dry-run

    # Stats only
    modal run scripts/modal_uscode.py --stats-only
"""

import modal
import os

# Define the Modal app
app = modal.App("civic-uscode")

# Build image with dependencies
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "requests>=2.31.0",  # For downloading from uscode.house.gov
        "httpx>=0.24.0",  # Required by civic.storage imports
    )
    .add_local_python_source("civic")
)


# Inline USCodeParser to avoid package mount issues
# (copied from civic_extraction/uscode.py)
from dataclasses import dataclass, asdict
from typing import Iterator, Optional
import xml.etree.ElementTree as ET
import re

USLM_NS = {"uslm": "http://xml.house.gov/schemas/uslm/1.0"}


@dataclass
class USCodeSection:
    """A single section of the U.S. Code."""
    title_number: int
    title_name: str
    section_number: str
    heading: str
    text: str
    citation: str
    identifier: str
    status: Optional[str] = None
    chapter: Optional[str] = None
    subchapter: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def is_active(self) -> bool:
        return self.status is None


class USCodeParser:
    """Parser for U.S. Code XML files."""

    def __init__(self, xml_path: str):
        from pathlib import Path
        self.xml_path = Path(xml_path)
        self.title_number = None
        self.title_name = None
        self._root = None

    def _load(self):
        if self._root is not None:
            return
        self._root = ET.parse(self.xml_path).getroot()
        # Extract title info
        main = self._root.find(".//uslm:main", USLM_NS)
        if main is not None:
            title_elem = main.find("uslm:title", USLM_NS)
            if title_elem is not None:
                self.title_number = int(title_elem.get("identifier", "").split("/")[-1].replace("t", "") or 0)
                heading = title_elem.find("uslm:heading", USLM_NS)
                self.title_name = heading.text if heading is not None else ""

    def _get_text(self, elem) -> str:
        """Recursively get text content, excluding notes."""
        if elem is None:
            return ""
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in ("notes", "sourceCredit", "note"):
                continue
            parts.append(self._get_text(child))
            if child.tail:
                parts.append(child.tail)
        return " ".join(parts)

    def _extract_section_text(self, section) -> str:
        """Extract readable text from a section."""
        parts = []
        for content in section.findall(".//uslm:content", USLM_NS):
            text = self._get_text(content)
            if text.strip():
                parts.append(text.strip())
        for chapeau in section.findall(".//uslm:chapeau", USLM_NS):
            text = self._get_text(chapeau)
            if text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts)

    def parse_sections(self, include_inactive: bool = False, chapter_filter: str = None) -> Iterator[USCodeSection]:
        """Parse and yield sections from the XML."""
        self._load()
        current_chapter = None
        current_subchapter = None

        for elem in self._root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

            if tag == "chapter":
                heading = elem.find("uslm:heading", USLM_NS)
                current_chapter = heading.text if heading is not None else None
                current_subchapter = None

            elif tag == "subchapter":
                heading = elem.find("uslm:heading", USLM_NS)
                current_subchapter = heading.text if heading is not None else None

            elif tag == "section":
                identifier = elem.get("identifier", "")
                status = elem.get("status")

                if not include_inactive and status in ("repealed", "omitted"):
                    continue

                if chapter_filter and current_chapter and chapter_filter.lower() not in current_chapter.lower():
                    continue

                # Get section number and heading
                num_elem = elem.find("uslm:num", USLM_NS)
                section_number = num_elem.get("value", "") if num_elem is not None else ""
                heading_elem = elem.find("uslm:heading", USLM_NS)
                heading = heading_elem.text if heading_elem is not None else ""

                # Build citation
                citation = f"{self.title_number} U.S.C. § {section_number}" if section_number else f"{self.title_number} U.S.C. § "

                # Extract text
                text = self._extract_section_text(elem)

                yield USCodeSection(
                    title_number=self.title_number,
                    title_name=self.title_name,
                    section_number=section_number,
                    heading=heading,
                    text=text,
                    citation=citation,
                    identifier=identifier,
                    status=status,
                    chapter=current_chapter,
                    subchapter=current_subchapter,
                )


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),  # DATABASE_URL
    ],
    memory=4096,
    timeout=3600,  # 1 hour
)
def ingest_uscode(
    title: int = 42,
    jurisdiction_id: str = "federal-US",
    dry_run: bool = False,
    stats_only: bool = False,
) -> dict:
    """
    Ingest U.S. Code sections from uscode.house.gov to PostgreSQL.

    Args:
        title: U.S. Code title number (e.g., 42 for Public Health)
        jurisdiction_id: Target jurisdiction
        dry_run: Parse only, don't store
        stats_only: Show database stats only

    Returns:
        Dict with ingestion results
    """
    import time
    import requests

    # Get database connection
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not set"}

    # Stats only mode
    if stats_only:
        from civic.storage.postgres_backend import PostgresBackend
        db = PostgresBackend(database_url)
        count = db.get_codified_law_count(jurisdiction_id)
        return {
            "jurisdiction_id": jurisdiction_id,
            "sections_in_db": count,
        }

    # Download XML directly from uscode.house.gov
    # URL pattern: releasepoints/us/pl/{pl_major}/{pl_minor}/xml_usc{title}@{pl_major}-{pl_minor}.zip
    # Current as of Jan 2026: Public Law 119-59
    url = f"https://uscode.house.gov/download/releasepoints/us/pl/119/59/xml_usc{title}@119-59.zip"
    print(f"Downloading Title {title} from uscode.house.gov...")
    start = time.time()

    response = requests.get(url, timeout=300)
    response.raise_for_status()

    # Extract XML from ZIP
    import zipfile
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        # Find the XML file in the ZIP
        xml_files = [f for f in zf.namelist() if f.endswith('.xml')]
        if not xml_files:
            return {"error": "No XML file found in ZIP"}
        xml_content = zf.read(xml_files[0])

    download_time = time.time() - start
    print(f"Downloaded {len(xml_content) / 1024 / 1024:.1f}MB in {download_time:.1f}s")

    # Write to temp file for parser
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        f.write(xml_content)
        xml_path = f.name

    # Parse sections using inlined USCodeParser
    print("Parsing U.S. Code XML...")
    parser = USCodeParser(xml_path)

    sections = []
    for section in parser.parse_sections():
        if section.identifier:  # Skip notes/annotations
            sections.append(section.to_dict())

    print(f"Parsed {len(sections)} sections")

    # Clean up temp file
    os.unlink(xml_path)

    if dry_run:
        return {
            "title": title,
            "sections_parsed": len(sections),
            "dry_run": True,
            "sample": sections[0] if sections else None,
        }

    # Store to PostgreSQL
    print("Storing to PostgreSQL using COPY...")
    from civic.storage.postgres_backend import PostgresBackend
    db = PostgresBackend(database_url)

    start = time.time()
    stored = db.store_codified_law(
        jurisdiction_id=jurisdiction_id,
        sections=sections,
        use_copy=True,
    )
    store_time = time.time() - start

    print(f"Stored {stored} sections in {store_time:.1f}s")

    # Get final count
    total = db.get_codified_law_count(jurisdiction_id)

    return {
        "title": title,
        "jurisdiction_id": jurisdiction_id,
        "sections_parsed": len(sections),
        "sections_stored": stored,
        "total_in_db": total,
        "download_time_s": download_time,
        "store_time_s": store_time,
    }


@app.local_entrypoint()
def main(
    title: int = 42,
    jurisdiction_id: str = "federal-US",
    dry_run: bool = False,
    stats_only: bool = False,
):
    """CLI entrypoint for Modal."""
    result = ingest_uscode.remote(
        title=title,
        jurisdiction_id=jurisdiction_id,
        dry_run=dry_run,
        stats_only=stats_only,
    )
    print("\n" + "=" * 50)
    print("RESULT:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    print("=" * 50)
