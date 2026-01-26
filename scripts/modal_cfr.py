"""
Modal function for Code of Federal Regulations (CFR) ingestion from GovInfo bulk data.

Fetches CFR XML from govinfo.gov and stores sections in the codified_law table
with jurisdiction_id="federal-CFR" for easy filtering and search.

Setup:
    Ensure Modal secrets exist:
    modal secret create civic-db DATABASE_URL="postgresql://..."

Usage:
    # Dry run (fetch and parse only, show stats)
    modal run scripts/modal_cfr.py --dry-run

    # Ingest specific titles (recommended for pilot)
    modal run scripts/modal_cfr.py --titles 24,40,49

    # Ingest all 50 titles (takes ~30 min)
    modal run scripts/modal_cfr.py --all-titles

    # Stats only
    modal run scripts/modal_cfr.py --stats-only

    # Show available titles
    modal run scripts/modal_cfr.py --list-titles

CFR Titles relevant to local government:
    - Title 24: Housing and Urban Development (HUD)
    - Title 40: Protection of Environment (EPA)
    - Title 49: Transportation (DOT)
    - Title 29: Labor (OSHA, workplace regulations)
    - Title 7: Agriculture (USDA programs)
    - Title 10: Energy (DOE)

Data source: https://www.govinfo.gov/bulkdata/CFR/
"""

import modal
import os
import tempfile
from typing import List, Optional

# Define the Modal app
app = modal.App("civic-cfr")

# Build image with dependencies
# Note: langgraph is required because civic/__init__.py imports the full Civic class
# which has LangGraph coordination dependencies
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc", "curl", "unzip")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "httpx>=0.24.0",
        "langgraph>=0.2.0",  # Required by civic package imports
        "beautifulsoup4>=4.12.0",  # Required by civic_extraction
        "requests>=2.28.0",  # Required by civic_extraction
    )
    .add_local_python_source("civicos_config")
    .add_local_python_source("civicos")
    .add_local_python_source("civicos_extraction")
)

# eCFR API configuration (GovInfo bulk data is unreliable)
# Note: eCFR provides current/up-to-date CFR content via REST API
ECFR_API_BASE = "https://www.ecfr.gov/api/versioner/v1"
ECFR_DATE = "2026-01-01"  # Current date for up-to-date content

# Relevant CFR titles for local government (start with these)
LOCAL_GOVT_TITLES = [
    24,  # Housing and Urban Development
    40,  # Protection of Environment (EPA)
    49,  # Transportation (DOT)
]

# All 50 CFR titles (Title 35 is reserved/unused)
ALL_CFR_TITLES = list(range(1, 51))


def get_ecfr_title_url(title_number: int) -> str:
    """Get eCFR API URL for a full title XML."""
    return f"{ECFR_API_BASE}/full/{ECFR_DATE}/title-{title_number}.xml"


def get_title_info() -> List[dict]:
    """Get metadata about all CFR titles from eCFR API."""
    import httpx

    url = f"{ECFR_API_BASE}/titles"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            data = resp.json()
            return data.get("titles", [])
    except Exception:
        return []


def parse_ecfr_xml(xml_content: bytes, title_number: int) -> List[dict]:
    """
    Parse eCFR XML format into section dicts.

    eCFR uses: ECFR > DIV1(TITLE) > DIV2(SUBTITLE) > DIV5(PART) > DIV8(SECTION)
    Each DIV has TYPE and N attributes.
    """
    import xml.etree.ElementTree as ET
    import re

    def get_text(elem) -> str:
        """Extract all text content from element recursively."""
        if elem is None:
            return ""
        texts = []
        if elem.text:
            texts.append(elem.text.strip())
        for child in elem:
            # Skip auth/source metadata
            if child.tag in ("SECAUTH", "SOURCE", "AUTH", "CITA", "FIG"):
                if child.tail:
                    texts.append(child.tail.strip())
                continue
            child_text = get_text(child)
            if child_text:
                texts.append(child_text)
            if child.tail:
                texts.append(child.tail.strip())
        result = " ".join(texts)
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    root = ET.fromstring(xml_content)
    sections = []

    # Get title info from DIV1
    title_div = root.find(".//DIV1[@TYPE='TITLE']")
    if title_div is None:
        return []

    title_head = title_div.find("HEAD")
    title_name = title_head.text if title_head is not None else f"Title {title_number}"
    # Clean title name: "Title 24—Housing and Urban Development" -> "Housing and Urban Development"
    if "—" in title_name:
        title_name = title_name.split("—", 1)[1].strip()

    # Find all sections (DIV8 with TYPE='SECTION')
    for section_elem in root.iter():
        if section_elem.tag != "DIV8":
            continue
        if section_elem.get("TYPE") != "SECTION":
            continue

        # Get section number from N attribute
        section_number = section_elem.get("N", "")
        if not section_number:
            continue

        # Get heading from HEAD element (e.g., "§ 1.1   Purpose.")
        head_elem = section_elem.find("HEAD")
        heading_raw = head_elem.text if head_elem is not None else ""
        # Clean heading: "§ 1.1   Purpose." -> "Purpose."
        heading = re.sub(r'^§\s*[\d.]+\s*', '', heading_raw).strip()

        # Extract text from P, FP elements
        text_parts = []
        for child in section_elem:
            if child.tag in ("P", "FP", "EXTRACT", "NOTE"):
                text = get_text(child)
                if text:
                    text_parts.append(text)
        text = " ".join(text_parts)

        # Skip sections with minimal text
        if len(text) < 20:
            continue

        # Find parent PART (DIV5)
        part_number = ""
        part_name = ""
        parent = section_elem
        while parent is not None:
            if parent.tag == "DIV5" and parent.get("TYPE") == "PART":
                part_number = parent.get("N", "")
                part_head = parent.find("HEAD")
                if part_head is not None:
                    part_name = part_head.text or ""
                break
            # Go up - find parent by iterating
            parent = None  # Can't traverse up in ElementTree, but we already have N

        # Build citation: "24 CFR 1.1"
        citation = f"{title_number} CFR {section_number}"

        # Build identifier
        identifier = f"cfr/t{title_number}/s{section_number}"

        sections.append({
            "citation": citation,
            "title_number": title_number,
            "title_name": title_name,
            "section_number": section_number,
            "heading": heading,
            "text": text,
            "identifier": identifier,
            "status": None,
            "chapter": None,
            "subchapter": None,
            "part_number": part_number,
            "authority": None,
            "source": None,
            "subpart": None,
        })

    return sections


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
    ],
    memory=4096,
    timeout=7200,  # 2 hours for full ingestion
)
def ingest_cfr(
    titles: Optional[List[int]] = None,
    all_titles: bool = False,
    dry_run: bool = False,
    stats_only: bool = False,
    list_titles: bool = False,
) -> dict:
    """
    Ingest CFR from eCFR API to PostgreSQL.

    Args:
        titles: List of title numbers to ingest (e.g., [24, 40, 49])
        all_titles: If True, ingest all 50 CFR titles
        dry_run: Parse only, don't store
        stats_only: Show database stats only
        list_titles: Show available titles and exit

    Returns:
        Dict with ingestion results
    """
    import time
    import httpx

    # Get database connection
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not set"}

    # List titles mode - fetch from eCFR API
    if list_titles:
        print("Fetching available CFR titles from eCFR API...")
        titles_info = get_title_info()
        available = [
            {"number": t["number"], "name": t["name"], "reserved": t.get("reserved", False)}
            for t in titles_info
            if not t.get("reserved", False)
        ]
        return {
            "available_titles": len(available),
            "titles": available,
            "local_govt_titles": LOCAL_GOVT_TITLES,
        }

    # Stats only mode
    if stats_only:
        from civicos.storage.postgres_backend import PostgresBackend
        db = PostgresBackend(database_url)

        # Get counts for federal-CFR jurisdiction
        count = db.get_codified_law_count("federal-CFR", include_inactive=False)

        # Get by title breakdown using raw query
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT title_number, COUNT(*) as cnt
            FROM codified_law
            WHERE jurisdiction_id = 'federal-CFR'
              AND valid_to IS NULL
            GROUP BY title_number
            ORDER BY title_number
        """)
        by_title = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.close()

        return {
            "cfr_sections_in_db": count,
            "sections_by_title": by_title,
        }

    # Determine which titles to ingest
    if all_titles:
        target_titles = [t for t in ALL_CFR_TITLES if t != 35]  # Skip reserved Title 35
    elif titles:
        target_titles = titles
    else:
        target_titles = LOCAL_GOVT_TITLES

    print(f"Ingesting CFR titles from eCFR API: {target_titles}")

    # Track results
    results = {
        "titles_processed": 0,
        "sections_parsed": 0,
        "sections_stored": 0,
        "by_title": {},
        "errors": [],
    }

    start = time.time()

    # Process each title
    with httpx.Client(timeout=180.0) as client:  # Longer timeout for large titles
        for title_num in target_titles:
            print(f"\n{'='*50}")
            print(f"Processing Title {title_num}")
            print("=" * 50)

            title_start = time.time()
            url = get_ecfr_title_url(title_num)

            print(f"  Downloading from eCFR API...")
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    print(f"  Error: HTTP {resp.status_code}")
                    results["errors"].append(f"Title {title_num}: HTTP {resp.status_code}")
                    continue

                print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

                # Parse the XML
                sections = parse_ecfr_xml(resp.content, title_num)
                print(f"  Parsed {len(sections)} sections")

                results["sections_parsed"] += len(sections)
                results["by_title"][title_num] = {"parsed": len(sections)}

                if dry_run:
                    print("  [DRY RUN] Skipping storage")
                    results["titles_processed"] += 1
                    continue

                # Store to PostgreSQL
                if sections:
                    print(f"  Storing to PostgreSQL...")
                    from civicos.storage.postgres_backend import PostgresBackend
                    db = PostgresBackend(database_url)

                    try:
                        stored = db.store_codified_law(
                            jurisdiction_id="federal-CFR",
                            sections=sections,
                            use_copy=True,
                        )
                        print(f"  Stored {stored} sections")
                        results["sections_stored"] += stored
                        results["by_title"][title_num]["stored"] = stored
                    except Exception as e:
                        print(f"  Storage error: {e}")
                        results["errors"].append(f"Title {title_num} storage: {str(e)}")

                results["titles_processed"] += 1
                title_time = time.time() - title_start
                print(f"  Completed in {title_time:.1f}s")

            except Exception as e:
                print(f"  Error: {e}")
                results["errors"].append(f"Title {title_num}: {str(e)}")
                continue

    total_time = time.time() - start
    results["total_time_s"] = total_time
    results["dry_run"] = dry_run

    # Get final count
    if not dry_run:
        from civicos.storage.postgres_backend import PostgresBackend
        db = PostgresBackend(database_url)
        results["total_in_db"] = db.get_codified_law_count(
            "federal-CFR", include_inactive=False
        )

    return results


@app.local_entrypoint()
def main(
    titles: str = "",
    all_titles: bool = False,
    dry_run: bool = False,
    stats_only: bool = False,
    list_titles: bool = False,
):
    """CLI entrypoint for Modal."""
    print("=" * 50)
    print("CFR INGESTION")
    print("=" * 50)

    # Parse titles if provided
    title_list = None
    if titles:
        title_list = [int(t.strip()) for t in titles.split(",") if t.strip()]

    result = ingest_cfr.remote(
        titles=title_list,
        all_titles=all_titles,
        dry_run=dry_run,
        stats_only=stats_only,
        list_titles=list_titles,
    )

    print("\n" + "=" * 50)
    print("RESULT:")
    for key, value in result.items():
        if key == "by_title" and isinstance(value, dict):
            print(f"  {key}:")
            for title_num, stats in value.items():
                print(f"    Title {title_num}: {stats}")
        elif key == "titles" and isinstance(value, list):
            print(f"  Available titles: {len(value)}")
            for t in value[:10]:  # Show first 10
                print(f"    Title {t['title']}: {t['volumes']} volumes")
            if len(value) > 10:
                print(f"    ... and {len(value) - 10} more")
        elif key == "errors" and isinstance(value, list) and value:
            print(f"  {key}:")
            for err in value:
                print(f"    - {err}")
        else:
            print(f"  {key}: {value}")
    print("=" * 50)
