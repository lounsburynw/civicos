"""
Modal function for U.S. Code ingestion to PostgreSQL.

Downloads from R2 (pre-cached from uscode.house.gov) and ingests to Supabase.
Runs in cloud (close to Supabase) - fast R2 CDN access.
Uses PostgreSQL COPY for fast bulk inserts (~10 seconds for 7k sections).

Setup:
    Ensure Modal secrets exist:
    modal secret create civic-db DATABASE_URL="postgresql://..."
    modal secret create civic-r2 \
        R2_ACCOUNT_ID="..." \
        R2_ACCESS_KEY_ID="..." \
        R2_SECRET_ACCESS_KEY="..." \
        R2_BUCKET_NAME="civic-pilot"

Usage:
    # Ingest Title 42 (from R2)
    modal run scripts/modal_uscode.py --title 42

    # Ingest ALL titles
    modal run scripts/modal_uscode.py --all

    # Dry run (download and parse only)
    modal run scripts/modal_uscode.py --title 42 --dry-run

    # Stats only
    modal run scripts/modal_uscode.py --stats-only

Release Point: PL 119-59 (current as of Jan 2026)
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
        "boto3>=1.26.0",  # For R2/S3 access
        "httpx>=0.24.0",  # Required by civic.storage imports
        "langgraph>=0.2.0",  # Required by civic package init
        "langchain-core>=0.3.0",  # Required by langgraph
    )
    .add_local_python_source("civicos")
)

# Release point metadata (for provenance tracking)
RELEASE_POINT = "119-59"
R2_PREFIX = f"uscode/{RELEASE_POINT}"

# All U.S. Code title numbers including appendices
# Appendices (5a, 11a, 18a, 28a) handled by updated parser
ALL_TITLES = [
    "01", "02", "03", "04", "05", "05a", "06", "07", "08", "09",
    "10", "11", "11a", "12", "13", "14", "15", "16", "17", "18", "18a",
    "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "28a",
    "29", "30", "31", "32", "33", "34", "35", "36", "37", "38",
    "39", "40", "41", "42", "43", "44", "45", "46", "47", "48",
    "49", "50", "51", "52", "54",
]


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

        # Extract title info - handle both main titles and appendices
        main = self._root.find(".//uslm:main", USLM_NS)
        if main is not None:
            title_elem = main.find("uslm:title", USLM_NS)
            if title_elem is not None:
                self.title_number = int(title_elem.get("identifier", "").split("/")[-1].replace("t", "") or 0)
                heading = title_elem.find("uslm:heading", USLM_NS)
                self.title_name = heading.text if heading is not None else ""
                self.is_appendix = False
                return

        # Fallback for appendices: use docNumber from metadata
        # Appendices have structure: <meta><docNumber>18a</docNumber></meta>
        doc_number_elem = self._root.find(".//uslm:docNumber", USLM_NS)
        if doc_number_elem is not None and doc_number_elem.text:
            doc_number = doc_number_elem.text  # e.g., "18a", "5a"
            # Extract numeric part: "18a" -> 18
            self.title_number = int(re.match(r"(\d+)", doc_number).group(1))
            # Get title name from dc:title in metadata
            dc_title = self._root.find(".//{http://purl.org/dc/elements/1.1/}title")
            self.title_name = dc_title.text if dc_title is not None else f"Title {doc_number}"
            self.is_appendix = True
            self.appendix_suffix = doc_number[-1] if doc_number[-1].isalpha() else ""  # "a"
        else:
            # Last resort fallback
            self.title_number = 0
            self.title_name = "Unknown"
            self.is_appendix = False

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

                # Build citation - use "App." for appendices
                if getattr(self, 'is_appendix', False):
                    citation = f"{self.title_number} U.S.C. App. § {section_number}" if section_number else f"{self.title_number} U.S.C. App. § "
                else:
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
        modal.Secret.from_name("civic-blob"),  # R2 credentials (BLOB_STORAGE_URL, R2_*)
    ],
    memory=4096,
    timeout=3600,  # 1 hour
)
def ingest_uscode(
    title: str = "42",
    jurisdiction_id: str = "federal-US",
    dry_run: bool = False,
    stats_only: bool = False,
) -> dict:
    """
    Ingest U.S. Code sections from R2 to PostgreSQL.

    Args:
        title: U.S. Code title number as string (e.g., "42", "05a")
        jurisdiction_id: Target jurisdiction
        dry_run: Parse only, don't store
        stats_only: Show database stats only

    Returns:
        Dict with ingestion results
    """
    import time
    import boto3

    # Get database connection
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not set"}

    # Stats only mode
    if stats_only:
        from civicos.storage.postgres_backend import PostgresBackend
        db = PostgresBackend(database_url)
        count = db.get_codified_law_count(jurisdiction_id)
        return {
            "jurisdiction_id": jurisdiction_id,
            "sections_in_db": count,
        }

    # Format title number for filename (e.g., "5" -> "05", "5a" -> "05a")
    if title.isdigit():
        title_formatted = title.zfill(2)
    else:
        # Handle appendices like "5a" -> "05a"
        title_formatted = title[:-1].zfill(2) + title[-1]

    # Download from R2 (pre-cached, fast CDN)
    print(f"Downloading Title {title} from R2...")
    start = time.time()

    # Parse BLOB_STORAGE_URL (r2://account_id/bucket_name)
    blob_url = os.environ.get("BLOB_STORAGE_URL", "")
    if not blob_url.startswith("r2://"):
        return {"error": f"Invalid BLOB_STORAGE_URL: {blob_url}"}
    parts = blob_url.replace("r2://", "").split("/", 1)
    if len(parts) != 2:
        return {"error": f"Invalid BLOB_STORAGE_URL format: {blob_url}"}
    account_id, bucket = parts

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )

    key = f"{R2_PREFIX}/xml_usc{title_formatted}.zip"

    response = s3.get_object(Bucket=bucket, Key=key)
    zip_content = response["Body"].read()

    # Extract XML from ZIP
    import zipfile
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(zip_content)) as zf:
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

    # Deduplicate by identifier (XML has subsections with same parent identifier)
    seen_identifiers = set()
    sections = []
    for section in parser.parse_sections():
        if section.identifier and section.identifier not in seen_identifiers:
            seen_identifiers.add(section.identifier)
            sections.append(section.to_dict())

    print(f"Parsed {len(sections)} unique sections")

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
    from civicos.storage.postgres_backend import PostgresBackend
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
        "release_point": RELEASE_POINT,
        "sections_parsed": len(sections),
        "sections_stored": stored,
        "total_in_db": total,
        "download_time_s": download_time,
        "store_time_s": store_time,
    }


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-blob"),
    ],
    memory=4096,
    timeout=14400,  # 4 hours for all titles
)
def ingest_all_titles(
    jurisdiction_id: str = "federal-US",
    dry_run: bool = False,
    clear: bool = False,
    start_from: str = "",
) -> dict:
    """Ingest all U.S. Code titles sequentially."""
    # Optionally clear existing data first
    if clear and not dry_run:
        import psycopg2
        database_url = os.environ.get("DATABASE_URL")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM codified_law WHERE jurisdiction_id = %s",
            (jurisdiction_id,)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        print(f"Cleared {deleted} existing sections for {jurisdiction_id}")

    # Determine which titles to process
    titles_to_process = ALL_TITLES
    if start_from:
        try:
            start_idx = ALL_TITLES.index(start_from)
            titles_to_process = ALL_TITLES[start_idx:]
            print(f"Starting from Title {start_from} ({len(titles_to_process)} titles remaining)")
        except ValueError:
            print(f"Warning: Title {start_from} not found, processing all")

    results = []
    total_sections = 0
    total_stored = 0

    for title in titles_to_process:
        print(f"\n{'='*50}")
        print(f"Processing Title {title}...")
        result = ingest_uscode.local(
            title=title,
            jurisdiction_id=jurisdiction_id,
            dry_run=dry_run,
        )
        results.append(result)
        if "sections_parsed" in result:
            total_sections += result["sections_parsed"]
        if "sections_stored" in result:
            total_stored += result["sections_stored"]

    return {
        "jurisdiction_id": jurisdiction_id,
        "release_point": RELEASE_POINT,
        "titles_processed": len(results),
        "total_sections_parsed": total_sections,
        "total_sections_stored": total_stored,
        "dry_run": dry_run,
    }


@app.local_entrypoint()
def main(
    title: str = "42",
    jurisdiction_id: str = "federal-US",
    dry_run: bool = False,
    stats_only: bool = False,
    all: bool = False,
    clear: bool = False,
    start_from: str = "",
):
    """CLI entrypoint for Modal."""
    if all:
        print(f"Ingesting ALL {len(ALL_TITLES)} U.S. Code titles...")
        if clear:
            print("Will clear existing data first...")
        if start_from:
            print(f"Starting from Title {start_from}")
        result = ingest_all_titles.remote(
            jurisdiction_id=jurisdiction_id,
            dry_run=dry_run,
            clear=clear,
            start_from=start_from,
        )
    else:
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
