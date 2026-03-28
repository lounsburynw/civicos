#!/usr/bin/env python3
"""
Seed election calendar data for pilot jurisdictions.

Creates elections with contests and deadlines for:
- 2026 CA Primary (June 2)
- 2026 General (November 3)

Uses the deterministic cycle resolver to determine which races appear
on each jurisdiction's ballot based on their district assignments.

Usage:
    python3 scripts/seed_election_calendar.py [--dry-run]
"""

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Ensure project packages are importable
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civicos" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civicos-extraction" / "src"))

from dotenv import load_dotenv

load_dotenv()

from civicos import CivicOS
from civicos._internal.elections import Election, ElectionType, Contest, ContestType
from civicos._internal.elections.cycles import (
    ca_primary_date,
    general_election_date,
    get_contests_for_jurisdiction,
)
from civicos._internal.elections.deadlines import generate_ca_deadlines

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Pilot jurisdictions and their district configs
PILOT_JURISDICTIONS = [
    "city-san-rafael",
    "city-mill-valley",
    "city-san-anselmo",
]


def load_districts(jurisdiction_id: str) -> dict:
    """Load district assignments from extraction config."""
    config_path = Path(__file__).parent.parent / "data" / "extraction" / f"{jurisdiction_id}.json"
    with open(config_path) as f:
        config = json.load(f)

    # Districts are under election_sources.ca_sos_results.districts
    # or at the top level for some configs
    election_sources = config.get("election_sources", {})
    ca_sos = election_sources.get("ca_sos_results", {})
    return ca_sos.get("districts", {})


CONTEST_TYPE_MAP = {
    "federal_house": ContestType.FEDERAL_HOUSE,
    "federal_senate": ContestType.FEDERAL_SENATE,
    "state_governor": ContestType.STATE_GOVERNOR,
    "state_legislature": ContestType.STATE_LEGISLATURE,
    "state_executive": ContestType.STATE_EXECUTIVE,
}


def make_election_id(jurisdiction_id: str, election_date: date, election_type: str) -> str:
    """Generate a deterministic election ID."""
    return f"cycle-{jurisdiction_id}-{election_date.isoformat()}-{election_type}"


def build_election(
    jurisdiction_id: str,
    election_date: date,
    election_type: ElectionType,
    name: str,
    districts: dict,
) -> Election:
    """Build an Election object with contests and deadlines from cycle data."""

    election_id = make_election_id(jurisdiction_id, election_date, election_type.value)

    # Get contests for this jurisdiction's districts
    year = election_date.year
    contest_dicts = get_contests_for_jurisdiction(districts, year)

    contests = []
    for i, cd in enumerate(contest_dicts):
        ct_str = cd["contest_type"]
        ct = CONTEST_TYPE_MAP.get(ct_str, ContestType.OTHER)
        contest = Contest(
            id=f"{election_id}-contest-{i}",
            title=cd["title"],
            contest_type=ct,
            district_name=cd["title"] if cd.get("district") else None,
            source="election_cycle",
        )
        contests.append(contest)

    # Generate deadlines
    deadlines = generate_ca_deadlines(election_date)

    return Election(
        id=election_id,
        jurisdiction_id=jurisdiction_id,
        name=name,
        election_date=election_date,
        election_type=election_type,
        deadlines=deadlines,
        contests=contests,
        source="election_cycle",
        source_url="https://www.sos.ca.gov/elections",
        last_updated=datetime.now(),
    )


def seed_deadlines_for_existing(storage, jurisdiction_id: str):
    """Add deadlines to existing elections that lack them."""
    elections = storage.get_elections(jurisdiction_id, include_past=False)
    updated = 0

    for e in elections:
        election_id = e["id"]
        election_date = e.get("election_date")
        if not election_date:
            continue

        # Check if deadlines already exist
        existing_deadlines = storage.get_election_deadlines(election_id)
        if existing_deadlines:
            continue

        # Parse date
        if isinstance(election_date, str):
            election_date = date.fromisoformat(election_date)
        elif isinstance(election_date, datetime):
            election_date = election_date.date()

        deadlines = generate_ca_deadlines(election_date)
        deadline_dicts = [
            {
                "deadline_type": d.deadline_type,
                "deadline_date": d.deadline_date.isoformat(),
                "description": d.description,
            }
            for d in deadlines
        ]

        count = storage.store_election_deadlines(election_id, deadline_dicts)
        if count > 0:
            logger.info(f"  Added {count} deadlines to {e.get('name', election_id)}")
            updated += 1

    return updated


def seed_jurisdiction(storage, jurisdiction_id: str, dry_run: bool = False):
    """Seed election calendar for a single jurisdiction."""
    logger.info(f"\n{'='*50}")
    logger.info(f"Jurisdiction: {jurisdiction_id}")
    logger.info(f"{'='*50}")

    districts = load_districts(jurisdiction_id)
    if not districts:
        logger.warning(f"  No district data found, skipping")
        return

    logger.info(f"  Districts: {districts}")

    # Elections to seed
    elections_to_create = [
        (
            ca_primary_date(2026),
            ElectionType.PRIMARY,
            "2026 California Primary Election",
        ),
        (
            general_election_date(2026),
            ElectionType.GENERAL,
            "2026 California General Election",
        ),
    ]

    # Check existing elections
    existing = storage.get_elections(jurisdiction_id, include_past=False)
    existing_dates = {}
    for e in existing:
        ed = e.get("election_date")
        if isinstance(ed, str):
            ed = date.fromisoformat(ed)
        elif isinstance(ed, datetime):
            ed = ed.date()
        key = (ed, e.get("election_type"))
        existing_dates[key] = e

    for election_date, election_type, name in elections_to_create:
        key = (election_date, election_type.value)

        if key in existing_dates:
            e = existing_dates[key]
            logger.info(f"  EXISTS: {e['name']} ({e['id']}) — skipping election creation")
        else:
            election = build_election(
                jurisdiction_id, election_date, election_type, name, districts
            )
            logger.info(
                f"  CREATE: {name} ({election_date}) — "
                f"{len(election.contests)} contests, {len(election.deadlines)} deadlines"
            )
            for c in election.contests:
                logger.info(f"    Contest: {c.title} ({c.contest_type.value})")

            if not dry_run:
                # Store election
                edict = election.to_dict()
                # Ensure raw_data is a JSON string (empty dicts are falsy,
                # bypassing the storage serialization guard)
                if isinstance(edict.get("raw_data"), dict):
                    edict["raw_data"] = json.dumps(edict["raw_data"])
                storage.store_elections(
                    jurisdiction_id, [edict]
                )

                # Store contests
                contest_dicts = [
                    {
                        "id": c.id,
                        "title": c.title,
                        "contest_type": c.contest_type.value,
                        "district_name": c.district_name,
                        "raw_data": json.dumps({"source": "election_cycle"}),
                    }
                    for c in election.contests
                ]
                storage.store_election_contests(election.id, contest_dicts)

                # Store deadlines
                deadline_dicts = [
                    {
                        "deadline_type": d.deadline_type,
                        "deadline_date": d.deadline_date.isoformat(),
                        "description": d.description,
                    }
                    for d in election.deadlines
                ]
                storage.store_election_deadlines(election.id, deadline_dicts)

                logger.info(f"    Stored successfully")

    # Add deadlines to any existing elections that lack them
    logger.info(f"\n  Checking existing elections for missing deadlines...")
    updated = seed_deadlines_for_existing(storage, jurisdiction_id)
    if updated == 0:
        logger.info(f"  All existing elections already have deadlines")


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("DRY RUN — no data will be written\n")

    # Use first jurisdiction to get storage backend
    c = CivicOS(PILOT_JURISDICTIONS[0])
    storage = c.storage
    logger.info(f"Storage backend: {type(storage).__name__}")

    for jid in PILOT_JURISDICTIONS:
        seed_jurisdiction(storage, jid, dry_run=dry_run)

    logger.info(f"\n{'='*50}")
    logger.info("SUMMARY")
    logger.info(f"{'='*50}")
    for jid in PILOT_JURISDICTIONS:
        elections = storage.get_elections(jid, include_past=False)
        logger.info(f"\n{jid}: {len(elections)} upcoming elections")
        for e in elections:
            deadlines = storage.get_election_deadlines(e["id"])
            contests = storage.get_election_contests(e["id"])
            logger.info(
                f"  {e['name']} ({e['election_date']}) — "
                f"{len(contests)} contests, {len(deadlines)} deadlines"
            )


if __name__ == "__main__":
    main()
