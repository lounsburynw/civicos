"""
Derive elected officials from election contest results.

Scans election_contests for winners (is_winner=True) and creates
elected_officials records, keeping only the most recent winner per seat.

Jurisdiction assignment:
  - federal_* contests → country-united-states
  - state_* contests   → state parent (e.g. state-california)
  - local_council with "supervisor" → county parent (e.g. county-marin)
  - local_mayor, local_council, local_school_board → the querying city
  - Contests whose raw_data.division names a different city are skipped
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

# Contest types that represent elected positions (not ballot measures)
ELECTED_POSITION_TYPES = {
    "federal_president",
    "federal_senate",
    "federal_house",
    "state_governor",
    "state_legislature",
    "local_mayor",
    "local_council",
    "local_school_board",
    "judicial",
}


def _load_parent_jurisdictions(jurisdiction_id: str) -> Dict[str, str]:
    """
    Load parent jurisdiction hierarchy from YAML config.

    Returns a dict mapping level → jurisdiction_id, e.g.:
    {"county": "county-marin", "state": "state-california", "federal": "country-united-states"}
    """
    parents: Dict[str, str] = {}
    jurisdictions_dir = Path(__file__).resolve().parents[6] / "data" / "jurisdictions"
    yaml_path = jurisdictions_dir / f"{jurisdiction_id}.yaml"

    if not yaml_path.exists():
        logger.warning(f"No YAML config for {jurisdiction_id}")
        return parents

    try:
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
        for parent_id in config.get("parent_jurisdictions", []):
            if parent_id.startswith("county-"):
                parents["county"] = parent_id
            elif parent_id.startswith("state-"):
                parents["state"] = parent_id
            elif parent_id.startswith("country-"):
                parents["federal"] = parent_id
    except Exception as e:
        logger.warning(f"Failed to load parents for {jurisdiction_id}: {e}")

    return parents


def _resolve_official_jurisdiction(
    contest_type: str,
    contest: Dict[str, Any],
    city_jurisdiction_id: str,
    parent_jurisdictions: Dict[str, str],
) -> Optional[str]:
    """
    Determine the correct jurisdiction_id for an official based on contest type.

    Returns None if the contest belongs to a different city (should be skipped).
    """
    # Check if raw_data.division names a different city
    raw_data = contest.get("raw_data") or {}
    if isinstance(raw_data, str):
        import json
        try:
            raw_data = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            raw_data = {}

    division = raw_data.get("division", {})
    division_name = division.get("displayName", "")
    division_type = division.get("divisionType", {}).get("name", "")

    # If the division is a city that doesn't match ours, skip this contest
    if division_type == "City" and division_name:
        # Normalize: "City of San Rafael" → "san rafael"
        normalized_div = division_name.lower().replace("city of ", "").replace("town of ", "").strip()
        # Extract city name from jurisdiction_id: "city-san-rafael" → "san rafael"
        normalized_jid = city_jurisdiction_id.replace("city-", "").replace("-", " ")
        if normalized_div != normalized_jid:
            return None  # Contest belongs to a different city

    # Map contest_type to jurisdiction level
    if contest_type in ("federal_president", "federal_senate", "federal_house"):
        return parent_jurisdictions.get("federal", city_jurisdiction_id)

    if contest_type in ("state_governor", "state_legislature"):
        return parent_jurisdictions.get("state", city_jurisdiction_id)

    if contest_type == "local_council":
        # County supervisors belong at the county level
        title = contest.get("title", "").lower()
        if "supervisor" in title:
            return parent_jurisdictions.get("county", city_jurisdiction_id)
        return city_jurisdiction_id

    # local_mayor, local_school_board, judicial → city level
    return city_jurisdiction_id


def _expire_misplaced_officials(
    storage: Any,
    city_jurisdiction_id: str,
    seat_winners: Dict[str, Tuple[Dict[str, Any], str]],
) -> int:
    """
    Expire officials stored at the city level whose seats belong to a parent
    jurisdiction (federal, state, county).

    When re-deriving, seats that were previously assigned to the city are now
    correctly routed to parent jurisdictions. This function closes the old
    city-level records so they don't persist alongside the correctly-placed ones.
    """
    relocated_seats = [
        official["seat"]
        for official, _date in seat_winners.values()
        if official["jurisdiction_id"] != city_jurisdiction_id
    ]

    if not relocated_seats:
        return 0

    expired = storage.expire_officials_by_seat(
        city_jurisdiction_id, list(set(relocated_seats))
    )

    if expired:
        logger.info(
            f"Expired {expired} misplaced officials at {city_jurisdiction_id} "
            f"(seats relocated to parent jurisdictions)"
        )

    return expired


def derive_officials_from_contests(
    storage: Any,
    jurisdiction_id: str,
) -> int:
    """
    Derive current elected officials from election contest winners.

    For each seat, finds the most recent election contest with a winner
    and creates an elected_officials record linking to the candidate.

    Officials are assigned to the correct jurisdiction level based on
    contest type (federal → country, state → state, etc.). Contests
    whose raw_data.division names a different city are skipped.

    Args:
        storage: StorageBackend with election + official methods
        jurisdiction_id: e.g. "city-san-rafael"

    Returns:
        Number of officials stored
    """
    elections = storage.get_elections(jurisdiction_id, include_past=True)
    if not elections:
        logger.info(f"No elections found for {jurisdiction_id}")
        return 0

    parent_jurisdictions = _load_parent_jurisdictions(jurisdiction_id)

    # Sort elections by date descending so most recent wins come first
    elections_sorted = sorted(
        elections,
        key=lambda e: e.get("election_date", ""),
        reverse=True,
    )

    # Track best (most recent) winner per (jurisdiction, seat) key
    seat_winners: Dict[str, Tuple[Dict[str, Any], str]] = {}
    skipped_cross_city = 0

    for election in elections_sorted:
        election_id = election["id"]
        election_date = election.get("election_date", "")

        contests = storage.get_election_contests(election_id)
        for contest in contests:
            contest_type = contest.get("contest_type", "")
            if contest_type not in ELECTED_POSITION_TYPES:
                continue

            # Determine the correct jurisdiction for this official
            official_jurisdiction = _resolve_official_jurisdiction(
                contest_type, contest, jurisdiction_id, parent_jurisdictions
            )
            if official_jurisdiction is None:
                skipped_cross_city += 1
                continue

            winners = _extract_winners(contest)
            if not winners:
                continue

            seat = _contest_to_seat(contest)
            if not seat:
                continue

            # Key includes jurisdiction so federal seats don't collide with local
            seat_key = f"{official_jurisdiction}:{seat}"

            # Only keep the first (most recent) winner per seat
            if seat_key in seat_winners:
                continue

            for winner in winners:
                official = _winner_to_official(
                    winner, contest, official_jurisdiction, election_date
                )
                seat_winners[seat_key] = (official, election_date)
                break  # One official per seat

    if skipped_cross_city:
        logger.info(
            f"Skipped {skipped_cross_city} contests belonging to other cities"
        )

    if not seat_winners:
        logger.info(f"No winners found in contests for {jurisdiction_id}")
        return 0

    # Expire misplaced officials: seats at the querying city level that should
    # be at a parent jurisdiction (e.g. federal officials stored at city-san-rafael).
    # This handles re-derivation after a jurisdiction assignment fix.
    _expire_misplaced_officials(storage, jurisdiction_id, seat_winners)

    # Group officials by their actual jurisdiction for separate storage calls
    from collections import defaultdict
    by_jurisdiction: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for official, _date in seat_winners.values():
        jid = official.get("jurisdiction_id", jurisdiction_id)
        by_jurisdiction[jid].append(official)

    total_stored = 0
    for jid, officials in by_jurisdiction.items():
        logger.info(
            f"Storing {len(officials)} officials for {jid} "
            f"(derived from {jurisdiction_id} elections)"
        )
        total_stored += storage.store_elected_officials(jid, officials)

    return total_stored


def _extract_winners(contest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract winner candidates from a contest record."""
    # Candidates live in raw_data.mapped_candidates (Civera and CA SOS format)
    raw_data = contest.get("raw_data") or {}
    if isinstance(raw_data, str):
        import json
        try:
            raw_data = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            return []

    candidates = raw_data.get("mapped_candidates", [])
    if not candidates:
        # Fallback: some formats may store candidates at top level
        candidates = raw_data.get("candidates", [])

    return [c for c in candidates if c.get("is_winner")]


def _contest_to_seat(contest: Dict[str, Any]) -> Optional[str]:
    """
    Map a contest to a normalized seat name.

    Examples:
        federal_house + "U.S. House of Representatives District 2" -> "US House District 2"
        federal_senate + "United States Senator" -> "US Senate"
        state_legislature + "Member of the State Assembly, District 12" -> "State Assembly District 12"
        local_council + "City Council Member" -> "City Council"
        local_mayor + "Mayor" -> "Mayor"
    """
    contest_type = contest.get("contest_type", "")
    title = contest.get("title", "")

    if contest_type == "federal_president":
        return "US President"

    if contest_type == "federal_senate":
        return "US Senate"

    if contest_type == "federal_house":
        district = _extract_district_number(title)
        if district:
            return f"US House District {district}"
        return f"US House - {title}"

    if contest_type == "state_governor":
        return "Governor"

    if contest_type == "state_legislature":
        title_lower = title.lower()
        district = _extract_district_number(title)
        if "senate" in title_lower or "senator" in title_lower:
            if district:
                return f"State Senate District {district}"
            return f"State Senate - {title}"
        if "assembly" in title_lower:
            if district:
                return f"State Assembly District {district}"
            return f"State Assembly - {title}"
        # Board of Equalization or other state legislature
        if district:
            return f"State Legislature District {district}"
        return f"State Legislature - {title}"

    if contest_type == "local_mayor":
        return "Mayor"

    if contest_type == "local_council":
        title_lower = title.lower()
        if "supervisor" in title_lower:
            district = _extract_district_number(title)
            if district:
                return f"County Supervisor District {district}"
            return f"County Supervisor - {title}"
        district = _extract_district_number(title)
        if district:
            return f"City Council District {district}"
        return "City Council"

    if contest_type == "local_school_board":
        return f"School Board - {title}"

    if contest_type == "judicial":
        return f"Judge - {title}"

    return None


def _extract_district_number(title: str) -> Optional[str]:
    """Extract district number from a contest title."""
    # Match patterns like "District 2", "District 12", "HD 70"
    m = re.search(r"(?:district|dist\.?)\s*(\d+)", title, re.IGNORECASE)
    if m:
        return m.group(1)
    # Match "HD 70" or "SD 35" patterns
    m = re.search(r"\b[HS]D\s*(\d+)\b", title, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _winner_to_official(
    winner: Dict[str, Any],
    contest: Dict[str, Any],
    jurisdiction_id: str,
    election_date: str,
) -> Dict[str, Any]:
    """Convert a winning candidate + contest into an elected_official dict."""
    name = winner.get("name", "Unknown")
    seat = _contest_to_seat(contest) or contest.get("title", "Unknown Seat")
    candidate_id = winner.get("id")

    # Build a stable ID from jurisdiction + seat
    seat_slug = re.sub(r"[^a-z0-9]+", "-", seat.lower()).strip("-")
    official_id = f"official-{jurisdiction_id}-{seat_slug}"

    # Generate name variations for fuzzy matching
    name_variations = _generate_name_variations(name)

    return {
        "id": official_id,
        "name": name,
        "seat": seat,
        "jurisdiction_id": jurisdiction_id,
        "term_start": election_date,
        "term_end": None,
        "name_variations": name_variations,
        "candidate_id": candidate_id,
    }


def _generate_name_variations(name: str) -> List[str]:
    """Generate common name variations for matching."""
    variations = [name]
    parts = name.split()
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        # "J. Smith" style
        variations.append(f"{first[0]}. {last}")
        # Last name only
        variations.append(last)
        # "Smith, Jane" style
        if len(parts) == 2:
            variations.append(f"{last}, {first}")
    return variations
