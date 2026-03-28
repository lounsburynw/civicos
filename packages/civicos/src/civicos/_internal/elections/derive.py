"""
Derive elected officials from election contest results.

Scans election_contests for winners (is_winner=True) and creates
elected_officials records, keeping only the most recent winner per seat.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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


def derive_officials_from_contests(
    storage: Any,
    jurisdiction_id: str,
) -> int:
    """
    Derive current elected officials from election contest winners.

    For each seat, finds the most recent election contest with a winner
    and creates an elected_officials record linking to the candidate.

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

    # Sort elections by date descending so most recent wins come first
    elections_sorted = sorted(
        elections,
        key=lambda e: e.get("election_date", ""),
        reverse=True,
    )

    # Track best (most recent) winner per seat key
    # Key: normalized seat string, Value: (official_dict, election_date)
    seat_winners: Dict[str, Tuple[Dict[str, Any], str]] = {}

    for election in elections_sorted:
        election_id = election["id"]
        election_date = election.get("election_date", "")

        contests = storage.get_election_contests(election_id)
        for contest in contests:
            contest_type = contest.get("contest_type", "")
            if contest_type not in ELECTED_POSITION_TYPES:
                continue

            winners = _extract_winners(contest)
            if not winners:
                continue

            seat = _contest_to_seat(contest)
            if not seat:
                continue

            # Only keep the first (most recent) winner per seat
            if seat in seat_winners:
                continue

            for winner in winners:
                official = _winner_to_official(
                    winner, contest, jurisdiction_id, election_date
                )
                seat_winners[seat] = (official, election_date)
                break  # One official per seat

    if not seat_winners:
        logger.info(f"No winners found in contests for {jurisdiction_id}")
        return 0

    officials = [entry[0] for entry in seat_winners.values()]
    logger.info(
        f"Derived {len(officials)} officials for {jurisdiction_id} "
        f"from {len(elections)} elections"
    )

    return storage.store_elected_officials(jurisdiction_id, officials)


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
