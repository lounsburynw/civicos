"""
Deterministic election cycle resolver for federal and state offices.

Computes the next election date for a given office type + district without
scraping. Federal and state cycles are deterministic — they follow fixed
patterns based on office type, district number, and year.

Local cycles (city council, school board, county supervisor) are NOT
deterministic and must come from registrar data.

California-specific rules:
- Primary: first Tuesday after first Monday in June (even years)
- General: first Tuesday after first Monday in November (even years)
- State Senate: 4-year terms, even districts in 2026/2030, odd in 2028/2032
- Assembly: all 80 seats every 2 years
- Statewide offices: same cycle as governor (every 4 years)
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional


class OfficeType(str, Enum):
    """Office types with deterministic election cycles."""

    US_HOUSE = "us_house"
    US_SENATE = "us_senate"
    STATE_GOVERNOR = "state_governor"
    STATE_ASSEMBLY = "state_assembly"
    STATE_SENATE = "state_senate"
    STATE_EXECUTIVE = "state_executive"  # controller, treasurer, AG, etc.


# US Senate seat classes for California
# Class I (Padilla): 2024, 2030, 2036...
# Class III (Schiff): 2022, 2028, 2034...
CA_SENATE_CLASSES = {
    "class_1": {"base_year": 2024, "cycle": 6},  # Padilla
    "class_3": {"base_year": 2022, "cycle": 6},  # Schiff
}


@dataclass
class ElectionCycle:
    """Info about an office's election cycle."""

    office_type: OfficeType
    district: Optional[int]
    term_years: int
    next_primary: date
    next_general: date
    # Future elections beyond the immediate next
    upcoming_generals: List[date] = field(default_factory=list)


def first_tuesday_after_first_monday(year: int, month: int) -> date:
    """
    Find the first Tuesday after the first Monday of a given month.

    This is the standard US election date formula:
    - November general elections
    - June primaries (California)
    """
    # First day of month
    first_day = date(year, month, 1)
    # Day of week: 0=Monday, 6=Sunday
    dow = first_day.weekday()

    # First Monday: if Jan 1 is Monday (0), it's day 1
    # Otherwise, advance to next Monday
    if dow == 0:  # Monday
        first_monday = 1
    else:
        first_monday = 1 + (7 - dow)

    # First Tuesday after first Monday = first_monday + 1
    return date(year, month, first_monday + 1)


def ca_primary_date(year: int) -> date:
    """California primary election date: first Tue after first Mon in June."""
    return first_tuesday_after_first_monday(year, 6)


def general_election_date(year: int) -> date:
    """General election date: first Tue after first Mon in November."""
    return first_tuesday_after_first_monday(year, 11)


def _next_election_year(base_year: int, cycle: int, as_of_year: int) -> int:
    """Find the next election year at or after as_of_year for a given cycle."""
    # How many cycles since base year?
    if as_of_year <= base_year:
        return base_year
    years_since = as_of_year - base_year
    cycles_passed = years_since // cycle
    next_year = base_year + (cycles_passed * cycle)
    if next_year < as_of_year:
        next_year += cycle
    return next_year


def get_next_election_date(
    office_type: str,
    district: Optional[int] = None,
    as_of: Optional[date] = None,
    state: str = "CA",
    senate_class: Optional[str] = None,
) -> date:
    """
    Get the next general election date for an office.

    Args:
        office_type: One of OfficeType values or string equivalent
        district: District number (required for house, assembly, state senate)
        as_of: Reference date (defaults to today)
        state: State code (currently only CA supported)
        senate_class: For US Senate, "class_1" or "class_3"

    Returns:
        Next general election date

    Examples:
        >>> get_next_election_date("us_house", district=2)
        date(2026, 11, 3)  # Next even-year November election
        >>> get_next_election_date("us_senate", senate_class="class_3")
        date(2028, 11, 7)  # Schiff's seat, Class III
    """
    if as_of is None:
        as_of = date.today()

    otype = OfficeType(office_type) if isinstance(office_type, str) else office_type

    if otype == OfficeType.US_HOUSE:
        # Every 2 years, all seats
        year = _next_election_year(2024, 2, as_of.year)
        gen = general_election_date(year)
        if gen < as_of:
            gen = general_election_date(year + 2)
        return gen

    elif otype == OfficeType.US_SENATE:
        if senate_class and senate_class in CA_SENATE_CLASSES:
            info = CA_SENATE_CLASSES[senate_class]
            year = _next_election_year(info["base_year"], info["cycle"], as_of.year)
            gen = general_election_date(year)
            if gen < as_of:
                gen = general_election_date(year + info["cycle"])
            return gen
        # Without class info, return next even-year senate election for CA
        # Both classes cycle on even years, just different ones
        class1_year = _next_election_year(2024, 6, as_of.year)
        class3_year = _next_election_year(2022, 6, as_of.year)
        d1 = general_election_date(class1_year)
        d3 = general_election_date(class3_year)
        if d1 < as_of:
            d1 = general_election_date(class1_year + 6)
        if d3 < as_of:
            d3 = general_election_date(class3_year + 6)
        return min(d1, d3)

    elif otype == OfficeType.STATE_GOVERNOR:
        # CA governor: every 4 years (2026, 2030, 2034...)
        year = _next_election_year(2026, 4, as_of.year)
        gen = general_election_date(year)
        if gen < as_of:
            gen = general_election_date(year + 4)
        return gen

    elif otype == OfficeType.STATE_EXECUTIVE:
        # Same cycle as governor
        return get_next_election_date(
            OfficeType.STATE_GOVERNOR, as_of=as_of, state=state
        )

    elif otype == OfficeType.STATE_ASSEMBLY:
        # All 80 seats every 2 years
        year = _next_election_year(2024, 2, as_of.year)
        gen = general_election_date(year)
        if gen < as_of:
            gen = general_election_date(year + 2)
        return gen

    elif otype == OfficeType.STATE_SENATE:
        if district is None:
            raise ValueError("district required for state senate")
        # CA State Senate: 4-year terms
        # After 2020 redistricting, SoS random draw assigned:
        # Even districts (2,4,6...): elected 2022, next 2026, 2030...
        # Odd districts (1,3,5...): elected 2024, next 2028, 2032...
        if district % 2 == 0:  # even
            base = 2026
        else:  # odd
            base = 2028
        year = _next_election_year(base, 4, as_of.year)
        gen = general_election_date(year)
        if gen < as_of:
            gen = general_election_date(year + 4)
        return gen

    raise ValueError(f"Unknown office type: {office_type}")


def get_next_primary_date(
    office_type: str,
    district: Optional[int] = None,
    as_of: Optional[date] = None,
    state: str = "CA",
    senate_class: Optional[str] = None,
) -> Optional[date]:
    """
    Get the next primary election date for an office.

    The primary is in the same year as the general, but in June (CA).
    Returns None if the primary has passed but the general hasn't.
    """
    gen = get_next_election_date(office_type, district, as_of, state, senate_class)
    primary = ca_primary_date(gen.year)
    if as_of and primary < as_of:
        return None  # Primary passed, general upcoming
    return primary


def get_election_cycle(
    office_type: str,
    district: Optional[int] = None,
    as_of: Optional[date] = None,
    state: str = "CA",
    senate_class: Optional[str] = None,
    horizon_years: int = 8,
) -> ElectionCycle:
    """
    Get full cycle info for an office: term length, next elections, future dates.

    Args:
        office_type: Office type string
        district: District number
        as_of: Reference date
        state: State code
        senate_class: For US Senate
        horizon_years: How many years ahead to compute

    Returns:
        ElectionCycle with next primary, general, and future generals
    """
    if as_of is None:
        as_of = date.today()

    otype = OfficeType(office_type) if isinstance(office_type, str) else office_type

    # Determine term length
    term_map = {
        OfficeType.US_HOUSE: 2,
        OfficeType.US_SENATE: 6,
        OfficeType.STATE_GOVERNOR: 4,
        OfficeType.STATE_EXECUTIVE: 4,
        OfficeType.STATE_ASSEMBLY: 2,
        OfficeType.STATE_SENATE: 4,
    }
    term_years = term_map[otype]

    next_gen = get_next_election_date(office_type, district, as_of, state, senate_class)
    next_pri = ca_primary_date(next_gen.year)
    if next_pri < as_of:
        next_pri = ca_primary_date(next_gen.year + term_years)

    # Compute upcoming generals within horizon
    upcoming = []
    cursor = next_gen
    end_date = date(as_of.year + horizon_years, 12, 31)
    while cursor <= end_date:
        upcoming.append(cursor)
        cursor = general_election_date(cursor.year + term_years)

    return ElectionCycle(
        office_type=otype,
        district=district,
        term_years=term_years,
        next_primary=next_pri,
        next_general=next_gen,
        upcoming_generals=upcoming,
    )


def get_contests_for_jurisdiction(
    districts: dict,
    election_year: int,
    as_of: Optional[date] = None,
) -> List[dict]:
    """
    Determine which contests appear on the ballot for a jurisdiction in a given
    election year, based on the jurisdiction's district assignments.

    Args:
        districts: Dict mapping office key to district numbers,
                   e.g. {"us-rep": [2], "state-assembly": [12], "state-senate": [2]}
        election_year: The election year to check
        as_of: Reference date (defaults to Jan 1 of election_year)

    Returns:
        List of contest dicts with office_type, district, contest_type, title
    """
    if as_of is None:
        as_of = date(election_year, 1, 1)

    contests = []

    # Map extraction config keys to (OfficeType, ContestType string)
    key_map = {
        "us-rep": (OfficeType.US_HOUSE, "federal_house"),
        "state-assembly": (OfficeType.STATE_ASSEMBLY, "state_legislature"),
        "state-senate": (OfficeType.STATE_SENATE, "state_legislature"),
    }

    for key, (office_type, contest_type) in key_map.items():
        if key not in districts:
            continue
        for dist in districts[key]:
            gen = get_next_election_date(
                office_type, district=dist, as_of=as_of
            )
            if gen.year == election_year:
                title_map = {
                    "us-rep": f"US House District {dist}",
                    "state-assembly": f"State Assembly District {dist}",
                    "state-senate": f"State Senate District {dist}",
                }
                contests.append({
                    "office_type": office_type.value,
                    "contest_type": contest_type,
                    "district": dist,
                    "title": title_map[key],
                })

    # Statewide offices — always on even years matching governor cycle
    statewide_gen = get_next_election_date(OfficeType.STATE_GOVERNOR, as_of=as_of)
    if statewide_gen.year == election_year:
        for title in [
            "Governor",
            "Lieutenant Governor",
            "Attorney General",
            "Controller",
            "Treasurer",
        ]:
            contests.append({
                "office_type": OfficeType.STATE_EXECUTIVE.value
                if title != "Governor"
                else OfficeType.STATE_GOVERNOR.value,
                "contest_type": "state_governor"
                if title == "Governor"
                else "state_executive",
                "district": None,
                "title": title,
            })

    # US House is every 2 years — already handled above
    # US Senate — check both classes
    for cls_name, cls_info in CA_SENATE_CLASSES.items():
        gen = get_next_election_date(
            OfficeType.US_SENATE, senate_class=cls_name, as_of=as_of
        )
        if gen.year == election_year:
            contests.append({
                "office_type": OfficeType.US_SENATE.value,
                "contest_type": "federal_senate",
                "district": None,
                "title": f"US Senate ({cls_name.replace('_', ' ').title()})",
                "senate_class": cls_name,
            })

    return contests
