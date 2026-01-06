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
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc", "curl", "unzip")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "httpx>=0.24.0",
    )
    .add_local_python_source("civic")
    .add_local_python_source("civic_extraction")
)

# GovInfo CFR bulk data configuration
GOVINFO_BASE_URL = "https://www.govinfo.gov/bulkdata/CFR/2024"
CFR_YEAR = 2024  # Latest complete year

# Relevant CFR titles for local government (start with these)
LOCAL_GOVT_TITLES = [
    24,  # Housing and Urban Development
    40,  # Protection of Environment (EPA)
    49,  # Transportation (DOT)
]

# All 50 CFR titles (Title 35 is reserved/unused)
ALL_CFR_TITLES = list(range(1, 51))


def get_volume_urls(title_number: int) -> List[str]:
    """Get all volume XML URLs for a CFR title."""
    # CFR titles are split into multiple volumes
    # Naming convention: CFR-2024-title{N}-vol{V}.xml
    # First check how many volumes exist by fetching the title index
    import httpx

    index_url = f"{GOVINFO_BASE_URL}/title-{title_number}/"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(index_url)
            if resp.status_code != 200:
                return []

            # Parse the directory listing to find volume files
            content = resp.text
            volumes = []
            import re
            pattern = rf'CFR-{CFR_YEAR}-title{title_number}-vol(\d+)\.xml'
            matches = re.findall(pattern, content)
            for vol_num in sorted(set(matches), key=int):
                url = f"{GOVINFO_BASE_URL}/title-{title_number}/CFR-{CFR_YEAR}-title{title_number}-vol{vol_num}.xml"
                volumes.append(url)
            return volumes
    except Exception:
        return []


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
    Ingest CFR from GovInfo to PostgreSQL.

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

    # List titles mode
    if list_titles:
        print("Fetching available CFR titles...")
        available = []
        with httpx.Client(timeout=30.0) as client:
            for title_num in ALL_CFR_TITLES:
                volumes = get_volume_urls(title_num)
                if volumes:
                    available.append({
                        "title": title_num,
                        "volumes": len(volumes),
                    })
        return {
            "available_titles": len(available),
            "titles": available,
            "local_govt_titles": LOCAL_GOVT_TITLES,
        }

    # Stats only mode
    if stats_only:
        from civic.storage.postgres_backend import PostgresBackend
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
        target_titles = ALL_CFR_TITLES
    elif titles:
        target_titles = titles
    else:
        target_titles = LOCAL_GOVT_TITLES

    print(f"Ingesting CFR titles: {target_titles}")

    # Import parser
    from civic_extraction.cfr import CFRParser

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
    for title_num in target_titles:
        print(f"\n{'='*50}")
        print(f"Processing Title {title_num}")
        print("=" * 50)

        title_sections = []
        title_start = time.time()

        # Get all volumes for this title
        volumes = get_volume_urls(title_num)
        if not volumes:
            print(f"  No volumes found for Title {title_num}")
            results["errors"].append(f"Title {title_num}: no volumes found")
            continue

        print(f"  Found {len(volumes)} volumes")

        # Download and parse each volume
        with httpx.Client(timeout=120.0) as client:
            for vol_url in volumes:
                vol_name = vol_url.split("/")[-1]
                print(f"  Downloading {vol_name}...")

                try:
                    resp = client.get(vol_url)
                    if resp.status_code != 200:
                        print(f"    Error: HTTP {resp.status_code}")
                        results["errors"].append(f"{vol_name}: HTTP {resp.status_code}")
                        continue

                    # Save to temp file and parse
                    with tempfile.NamedTemporaryFile(
                        mode="wb", suffix=".xml", delete=False
                    ) as f:
                        f.write(resp.content)
                        temp_path = f.name

                    try:
                        parser = CFRParser(temp_path)
                        vol_sections = list(parser.parse_sections())
                        print(f"    Parsed {len(vol_sections)} sections")
                        title_sections.extend(vol_sections)
                    finally:
                        os.unlink(temp_path)

                except Exception as e:
                    print(f"    Error: {e}")
                    results["errors"].append(f"{vol_name}: {str(e)}")
                    continue

        # Convert to dicts for storage
        sections_for_storage = []
        for section in title_sections:
            d = section.to_dict()
            # CFR uses part_number instead of chapter for organization
            # Map to codified_law schema
            sections_for_storage.append({
                "citation": d["citation"],
                "title_number": d["title_number"],
                "title_name": d["title_name"],
                "section_number": d["section_number"],
                "heading": d["heading"],
                "text": d["text"],
                "identifier": d["identifier"],
                "status": None,  # CFR sections are current by definition
                "chapter": d.get("chapter"),
                "subchapter": d.get("subchapter"),
                # Store CFR-specific fields in metadata
                "part_number": d.get("part_number"),
                "authority": d.get("authority"),
                "source": d.get("source"),
                "subpart": d.get("subpart"),
            })

        print(f"  Total: {len(sections_for_storage)} sections from Title {title_num}")
        results["sections_parsed"] += len(sections_for_storage)
        results["by_title"][title_num] = {
            "parsed": len(sections_for_storage),
            "volumes": len(volumes),
        }

        if dry_run:
            print("  [DRY RUN] Skipping storage")
            continue

        # Store to PostgreSQL
        if sections_for_storage:
            print(f"  Storing to PostgreSQL...")
            from civic.storage.postgres_backend import PostgresBackend
            db = PostgresBackend(database_url)

            try:
                stored = db.store_codified_law(
                    jurisdiction_id="federal-CFR",
                    sections=sections_for_storage,
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

    total_time = time.time() - start
    results["total_time_s"] = total_time
    results["dry_run"] = dry_run

    # Get final count
    if not dry_run:
        from civic.storage.postgres_backend import PostgresBackend
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
