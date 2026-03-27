#!/usr/bin/env python3
"""Build statewide school district directory from CA Dept of Education data.

Downloads the CDE public schools/districts file, extracts district-level
entries with websites, probes each for Simbli/BoardDocs platforms, and
generates entries for data/school_districts.json.

Usage:
    python scripts/build_school_directory.py                    # Full run
    python scripts/build_school_directory.py --dry-run          # Preview without writing
    python scripts/build_school_directory.py --county Alameda   # Single county
    python scripts/build_school_directory.py --workers 5        # Fewer parallel workers
"""

import argparse
import csv
import io
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# CDE tab-delimited file with all schools + districts (includes Website field)
CDE_DATA_URL = "https://www.cde.ca.gov/schooldirectory/report?rid=dl1&tp=txt"

REPO_ROOT = Path(__file__).parent.parent
SCHOOL_DISTRICTS_PATH = REPO_ROOT / "data" / "school_districts.json"

REQUEST_TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

SIMBLI_DOMAINS = ["simbli", "eboardsolutions", "agendaonline"]
BOARDDOCS_URL_RE = re.compile(r"https?://go\.boarddocs\.com/([^/]+/[^/]+)")


def download_cde_data() -> List[Dict[str, str]]:
    """Download and parse the CDE public schools/districts tab-delimited file."""
    print("Downloading CDE data file...")
    response = requests.get(CDE_DATA_URL, timeout=120)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text), delimiter="\t")
    rows = list(reader)
    print(f"  Parsed {len(rows)} rows")
    return rows


def extract_districts(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Filter for active district-level entries with websites.

    District entries have CDSCode ending in "0000000" (school portion is zeros).
    """
    districts: Dict[str, Dict[str, str]] = {}

    for row in rows:
        cds = row.get("CDSCode", "")
        if len(cds) < 14 or cds[-7:] != "0000000":
            continue
        if row.get("StatusType", "") != "Active":
            continue

        name = row.get("District", "").strip()
        county = row.get("County", "").strip()
        website = (row.get("WebSite") or row.get("Website") or "").strip()
        if website == "No Data":
            website = ""

        if not name or not county:
            continue

        dist_code = cds[:7]
        if dist_code not in districts:
            districts[dist_code] = {
                "cds_code": cds,
                "name": name,
                "county": county,
                "website": website,
                "doc_type": row.get("DOCType", ""),
            }

    return list(districts.values())


def make_jurisdiction_id(name: str) -> str:
    """Generate a jurisdiction_id slug from a district name.

    Handles both CDE short names ("Miller Creek Elementary") and full names
    ("Miller Creek Elementary School District") by stripping DOC-type
    suffixes to produce a core slug like "school-miller-creek".
    """
    slug = name.lower()

    # Strip suffixes — ordered longest-first so greedy matches win.
    # Covers both full names ("X Elementary School District") and
    # CDE short names ("X Elementary").
    for suffix in [
        # Full name suffixes (with "School District")
        " joint unified school district",
        " unified school district",
        " joint union high school district",
        " union high school district",
        " union elementary school district",
        " joint elementary school district",
        " elementary school district",
        " high school district",
        " school district",
        # CDE short name suffixes (without "School District").
        # NOTE: " union elementary" is intentionally absent — "Union" is part
        # of the district identity (e.g. "Reed Union") and should be kept.
        # " union high" IS stripped because curated IDs drop it (e.g. Tamalpais).
        " joint unified",
        " unified",
        " joint union high",
        " union high",
        " joint elementary",
        " elementary",
        " high",
        # Special types
        " county office of education",
        " county rop",
    ]:
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
            break

    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return f"school-{slug}"


def make_display_name(cde_name: str) -> str:
    """Convert a CDE short name to a display name with 'School District' suffix.

    CDE stores "Miller Creek Elementary"; we want "Miller Creek Elementary School District".
    County Offices of Education keep their name as-is.
    """
    lower = cde_name.lower()
    if "county office of education" in lower or "county rop" in lower:
        return cde_name
    return f"{cde_name} School District"


def _normalize_url(url: str) -> str:
    """Ensure URL has a scheme."""
    if not url:
        return ""
    if not url.startswith("http"):
        return f"https://{url}"
    return url


def probe_website(district: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Probe a district website for Simbli or BoardDocs platform links."""
    website = _normalize_url(district.get("website", ""))
    if not website:
        return None

    try:
        resp = requests.get(
            website,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Scan all links for BoardDocs URLs
        for link in soup.find_all("a", href=True):
            bd_match = BOARDDOCS_URL_RE.search(link["href"])
            if bd_match:
                return _build_boarddocs_entry(district, bd_match.group(1))

        # Scan all links for Simbli/eboardsolutions/agendaonline URLs
        for link in soup.find_all("a", href=True):
            href_lower = link["href"].lower()
            for domain in SIMBLI_DOMAINS:
                if domain in href_lower:
                    return _build_simbli_entry(district, link["href"])

        # Fallback: check raw HTML for platform mentions (some links are JS-generated)
        html_lower = resp.text.lower()
        bd_match = BOARDDOCS_URL_RE.search(resp.text)
        if bd_match:
            return _build_boarddocs_entry(district, bd_match.group(1))

        for domain in SIMBLI_DOMAINS:
            if domain in html_lower:
                return _build_simbli_entry(district, website, text_only=True)

        return None

    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None


def _build_boarddocs_entry(
    district: Dict[str, str], app_path: str
) -> Dict[str, Any]:
    """Build a BoardDocs district entry, probing for committee ID."""
    entry: Dict[str, Any] = {
        "name": make_display_name(district["name"]),
        "jurisdiction_id": make_jurisdiction_id(district["name"]),
        "platform": "boarddocs",
        "board_url": f"https://go.boarddocs.com/{app_path}/Board.nsf",
        "boarddocs_app_path": app_path,
    }

    # Probe for committee ID
    committee_id = _fetch_boarddocs_committee(app_path)
    entry["boarddocs_committee_id"] = committee_id or ""

    return entry


def _fetch_boarddocs_committee(app_path: str) -> Optional[str]:
    """Fetch the first committee ID from a BoardDocs public page."""
    try:
        url = f"https://go.boarddocs.com/{app_path}/Board.nsf/vpublic?open"
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", class_="committee-trigger"):
            cid = link.get("committeeid", "")
            if cid:
                return cid
    except Exception:
        pass
    return None


def _build_simbli_entry(
    district: Dict[str, str], board_url: str, text_only: bool = False
) -> Dict[str, Any]:
    """Build a Simbli district entry."""
    entry: Dict[str, Any] = {
        "name": make_display_name(district["name"]),
        "jurisdiction_id": make_jurisdiction_id(district["name"]),
        "platform": "simbli",
        "board_url": board_url,
        "district_website": _normalize_url(district.get("website", "")),
    }

    # Extract Simbli district ID from URL if present
    sid_match = re.search(r"[?&]S=(\d+)", board_url)
    if sid_match:
        entry["simbli_district_id"] = sid_match.group(1)

    return entry


def process_districts(
    districts: List[Dict[str, str]],
    workers: int = 10,
    county_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Probe all districts in parallel, returning detected entries."""
    if county_filter:
        districts = [
            d for d in districts if d["county"].lower() == county_filter.lower()
        ]

    # Only probe districts that have websites
    with_web = [d for d in districts if d.get("website")]
    print(f"Probing {len(with_web)} districts (of {len(districts)} total) with {workers} workers...")

    results: List[Dict[str, Any]] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe_website, d): d for d in with_web}

        for future in as_completed(futures):
            completed += 1
            if completed % 100 == 0:
                print(f"  Progress: {completed}/{len(futures)} probed, {len(results)} detected...")

            result = future.result()
            if result:
                result["_county"] = futures[future]["county"]
                results.append(result)

    print(f"  Done: {len(results)} districts with Simbli or BoardDocs detected")
    return disambiguate_collisions(results)


_NOISE_WORDS = {"school", "district", "elementary", "unified", "high", "union", "joint", "of", "county", "office", "education"}


def disambiguate_collisions(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add DOC-type suffix to jurisdiction_ids that collide.

    Same-city elementary and high school districts produce the same slug
    (e.g. "San Rafael City Elementary" and "San Rafael City High" both →
    "school-san-rafael-city").  Disambiguate by appending "-elem"/"-high".
    """
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        by_id.setdefault(entry["jurisdiction_id"], []).append(entry)

    for jid, group in by_id.items():
        if len(group) < 2:
            continue
        for entry in group:
            name_lower = entry["name"].lower()
            if "elementary" in name_lower:
                entry["jurisdiction_id"] = f"{jid}-elem"
            elif "high" in name_lower:
                entry["jurisdiction_id"] = f"{jid}-high"

    return entries


def _name_overlaps_existing(new_name: str, existing_entries: List[Dict]) -> bool:
    """Check if a new entry duplicates an existing entry by name similarity.

    Compares "core" words (dropping DOC-type and structural words) to detect
    the same district under different naming conventions, e.g.:
      "Mill Valley Elementary School District" ↔ "Mill Valley School District"

    Uses exact equality (not subset) to avoid false positives like
    "Ross Elementary" ≠ "Ross Valley School District".
    """
    new_words = set(new_name.lower().split()) - _NOISE_WORDS
    if not new_words:
        return False
    for entry in existing_entries:
        existing_words = set(entry.get("name", "").lower().split()) - _NOISE_WORDS
        if new_words == existing_words:
            return True
    return False


def merge_with_existing(
    new_entries: List[Dict[str, Any]], existing_path: Path
) -> Dict[str, Dict[str, list]]:
    """Merge new entries into existing school_districts.json.

    Existing entries (e.g. curated Marin data) are never overwritten.
    """
    existing: Dict[str, Dict[str, list]] = {}
    if existing_path.exists():
        with open(existing_path) as f:
            existing = json.load(f)

    # Index existing entries for dedup (by jurisdiction_id + name overlap).
    # Pre-compute these sets BEFORE the merge loop so that newly added
    # entries don't accidentally block each other (e.g. disambiguated
    # elementary/high pairs from the same city).
    existing_ids: set = set()
    curated_entries_by_county: Dict[str, List[Dict]] = {}
    for state_data in existing.values():
        for county_key, entries in state_data.items():
            for entry in entries:
                existing_ids.add(entry.get("jurisdiction_id"))
            curated_entries_by_county[county_key] = list(entries)

    added = 0
    for entry in new_entries:
        county = entry.pop("_county", "unknown").lower()
        state = "california"

        if entry["jurisdiction_id"] in existing_ids:
            continue

        # Name-overlap dedup against CURATED entries only (pre-computed),
        # not against entries we're adding in this run.
        if _name_overlaps_existing(entry["name"], curated_entries_by_county.get(county, [])):
            continue

        existing.setdefault(state, {}).setdefault(county, []).append(entry)
        existing_ids.add(entry["jurisdiction_id"])
        added += 1

    # Sort counties alphabetically, entries by name within each county
    for state in existing:
        existing[state] = dict(sorted(existing[state].items()))
        for county in existing[state]:
            existing[state][county].sort(key=lambda e: e["name"])

    print(f"  Added {added} new entries (skipped {len(new_entries) - added} duplicates)")
    return existing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build CA school district directory from CDE data"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview results without writing"
    )
    parser.add_argument("--county", help="Filter to a specific county")
    parser.add_argument(
        "--workers", type=int, default=10, help="Parallel workers (default: 10)"
    )
    parser.add_argument("--output", help="Output path (default: data/school_districts.json)")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else SCHOOL_DISTRICTS_PATH

    # Step 1: Download CDE data
    rows = download_cde_data()

    # Step 2: Extract district-level entries
    districts = extract_districts(rows)
    with_web = sum(1 for d in districts if d.get("website"))
    print(f"Found {len(districts)} active districts, {with_web} with websites")

    # Step 3: Probe websites for Simbli/BoardDocs
    detected = process_districts(districts, workers=args.workers, county_filter=args.county)

    if args.dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — would add these entries:")
        print(f"{'='*60}")
        by_county: Dict[str, list] = {}
        for e in detected:
            by_county.setdefault(e.get("_county", "?"), []).append(e)
        for county in sorted(by_county):
            print(f"\n  {county} ({len(by_county[county])} districts):")
            for e in sorted(by_county[county], key=lambda x: x["name"]):
                print(f"    {e['name']} → {e['platform']}")
        return

    # Step 4: Merge with existing data and write
    merged = merge_with_existing(detected, output_path)

    total = sum(len(entries) for sd in merged.values() for entries in sd.values())
    counties = sum(len(sd) for sd in merged.values())

    with open(output_path, "w") as f:
        json.dump(merged, f, indent=2)
        f.write("\n")

    print(f"\nWrote {total} districts across {counties} counties to {output_path}")


if __name__ == "__main__":
    main()
