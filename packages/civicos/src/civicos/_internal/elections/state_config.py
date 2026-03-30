"""
Per-state election configuration.

Captures the election rules that vary by state: primary date formula,
deadline offsets, governor cycle, state senate stagger, statewide offices,
and chamber naming. Used by cycles.py and deadlines.py instead of
hardcoded California constants.

Adding a new state:
1. Create a StateElectionConfig entry in STATE_CONFIGS
2. Research the state's election laws for correct values
3. Add tests in test_election_calendar.py

Usage:
    from civicos._internal.elections.state_config import get_state_config
    config = get_state_config("CA")
    print(config.primary_month)  # 6 (June)
    print(config.registration_deadline_days)  # 15
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class SenateStagger:
    """Describes how state senate seats are staggered across election cycles.

    Most states stagger senate seats by district parity (even/odd).
    The base years indicate when each group was last elected.
    """

    even_districts_base_year: int
    odd_districts_base_year: int
    term_years: int = 4


@dataclass(frozen=True)
class USSenateClass:
    """A US Senate seat class for a specific state."""

    base_year: int  # Most recent election year for this class
    cycle: int = 6  # Always 6 years for US Senate


@dataclass(frozen=True)
class StateElectionConfig:
    """Per-state election rules. One instance per supported state.

    All fields describe deterministic rules from state election law.
    Local election cycles (city council, school board) are NOT included —
    those come from registrar data, not election code.
    """

    # Identity
    state_code: str  # "CA", "TX", "FL"
    state_name: str  # "California", "Texas"

    # Primary date rule
    primary_month: int  # 6 for CA (June), 3 for TX (March)

    # Governor cycle
    governor_base_year: int  # 2026 for CA and TX
    governor_term_years: int = 4

    # State senate stagger
    senate_stagger: Optional[SenateStagger] = None

    # US Senate classes (each state has 2 senators in different classes)
    us_senate_classes: Dict[str, USSenateClass] = field(default_factory=dict)

    # Statewide offices elected on the governor cycle
    statewide_offices: Tuple[str, ...] = ()

    # Lower chamber (Assembly in CA, House in most states)
    lower_chamber_name: str = "House"
    lower_chamber_term_years: int = 2

    # Upper chamber
    upper_chamber_name: str = "Senate"

    # Deadline offsets (days before election day)
    registration_deadline_days: int = 30  # Conservative default
    early_voting_start_days: int = 0  # 0 = no early voting
    vbm_mailing_days: int = 0  # 0 = no universal VBM
    conditional_registration: bool = False  # Same-day/conditional registration

    # Election day details
    polls_open: str = "7:00 AM"
    polls_close: str = "8:00 PM"


# ==================== State Configs ====================

STATE_CONFIGS: Dict[str, StateElectionConfig] = {
    "CA": StateElectionConfig(
        state_code="CA",
        state_name="California",
        primary_month=6,  # June
        governor_base_year=2026,
        governor_term_years=4,
        senate_stagger=SenateStagger(
            even_districts_base_year=2026,
            odd_districts_base_year=2028,
            term_years=4,
        ),
        us_senate_classes={
            "class_1": USSenateClass(base_year=2024),  # Padilla
            "class_3": USSenateClass(base_year=2022),  # Schiff
        },
        statewide_offices=(
            "Governor",
            "Lieutenant Governor",
            "Attorney General",
            "Controller",
            "Treasurer",
        ),
        lower_chamber_name="Assembly",
        lower_chamber_term_years=2,
        upper_chamber_name="Senate",
        registration_deadline_days=15,
        early_voting_start_days=10,
        vbm_mailing_days=29,
        conditional_registration=True,
        polls_open="7:00 AM",
        polls_close="8:00 PM",
    ),
    "TX": StateElectionConfig(
        state_code="TX",
        state_name="Texas",
        primary_month=3,  # March
        governor_base_year=2026,
        governor_term_years=4,
        senate_stagger=SenateStagger(
            even_districts_base_year=2026,  # Odd-numbered districts
            odd_districts_base_year=2028,  # Even-numbered districts
            term_years=4,
        ),
        us_senate_classes={
            "class_1": USSenateClass(base_year=2024),  # Cruz
            "class_2": USSenateClass(base_year=2026),  # Cornyn
        },
        statewide_offices=(
            "Governor",
            "Lieutenant Governor",
            "Attorney General",
            "Comptroller",
            "Land Commissioner",
            "Agriculture Commissioner",
            "Railroad Commissioner",
        ),
        lower_chamber_name="House",
        lower_chamber_term_years=2,
        upper_chamber_name="Senate",
        registration_deadline_days=30,
        early_voting_start_days=17,
        vbm_mailing_days=0,  # No universal VBM
        conditional_registration=False,
        polls_open="7:00 AM",
        polls_close="7:00 PM",
    ),
    "FL": StateElectionConfig(
        state_code="FL",
        state_name="Florida",
        primary_month=8,  # August
        governor_base_year=2026,
        governor_term_years=4,
        senate_stagger=SenateStagger(
            even_districts_base_year=2026,
            odd_districts_base_year=2028,
            term_years=4,
        ),
        us_senate_classes={
            "class_1": USSenateClass(base_year=2024),  # Scott
            "class_3": USSenateClass(base_year=2028),  # Rubio (appointed replacement)
        },
        statewide_offices=(
            "Governor",
            "Lieutenant Governor",
            "Attorney General",
            "Chief Financial Officer",
            "Agriculture Commissioner",
        ),
        lower_chamber_name="House",
        lower_chamber_term_years=2,
        upper_chamber_name="Senate",
        registration_deadline_days=29,
        early_voting_start_days=10,
        vbm_mailing_days=0,  # Request-based VBM
        conditional_registration=False,
        polls_open="7:00 AM",
        polls_close="7:00 PM",
    ),
    "NY": StateElectionConfig(
        state_code="NY",
        state_name="New York",
        primary_month=6,  # June
        governor_base_year=2026,
        governor_term_years=4,
        senate_stagger=SenateStagger(
            even_districts_base_year=2026,
            odd_districts_base_year=2028,
            term_years=2,  # NY state senate is 2-year terms (all seats every 2 years)
        ),
        us_senate_classes={
            "class_1": USSenateClass(base_year=2024),  # Gillibrand
            "class_3": USSenateClass(base_year=2022),  # Schumer
        },
        statewide_offices=(
            "Governor",
            "Lieutenant Governor",
            "Attorney General",
            "Comptroller",
        ),
        lower_chamber_name="Assembly",
        lower_chamber_term_years=2,
        upper_chamber_name="Senate",
        registration_deadline_days=25,
        early_voting_start_days=10,
        vbm_mailing_days=0,  # Request-based
        conditional_registration=False,
        polls_open="6:00 AM",
        polls_close="9:00 PM",
    ),
    "PA": StateElectionConfig(
        state_code="PA",
        state_name="Pennsylvania",
        primary_month=5,  # May (moved from April in 2025)
        governor_base_year=2026,
        governor_term_years=4,
        senate_stagger=SenateStagger(
            even_districts_base_year=2026,
            odd_districts_base_year=2028,
            term_years=4,
        ),
        us_senate_classes={
            "class_1": USSenateClass(base_year=2024),  # Casey/McCormick
            "class_3": USSenateClass(base_year=2022),  # Fetterman
        },
        statewide_offices=(
            "Governor",
            "Lieutenant Governor",
            "Attorney General",
            "Auditor General",
            "Treasurer",
        ),
        lower_chamber_name="House",
        lower_chamber_term_years=2,
        upper_chamber_name="Senate",
        registration_deadline_days=15,
        early_voting_start_days=0,  # No in-person early voting
        vbm_mailing_days=0,  # Request-based mail ballots
        conditional_registration=False,
        polls_open="7:00 AM",
        polls_close="8:00 PM",
    ),
    "IL": StateElectionConfig(
        state_code="IL",
        state_name="Illinois",
        primary_month=3,  # March
        governor_base_year=2026,
        governor_term_years=4,
        senate_stagger=SenateStagger(
            # IL uses a 2-4-4 rotation, not simple even/odd
            even_districts_base_year=2026,
            odd_districts_base_year=2028,
            term_years=4,  # Simplified — IL actually has a complex rotation
        ),
        us_senate_classes={
            "class_2": USSenateClass(base_year=2026),  # Duckworth
            "class_3": USSenateClass(base_year=2022),  # Durbin
        },
        statewide_offices=(
            "Governor",
            "Lieutenant Governor",
            "Attorney General",
            "Secretary of State",
            "Comptroller",
            "Treasurer",
        ),
        lower_chamber_name="House",
        lower_chamber_term_years=2,
        upper_chamber_name="Senate",
        registration_deadline_days=28,
        early_voting_start_days=40,
        vbm_mailing_days=0,  # Request-based
        conditional_registration=True,  # Grace period registration
        polls_open="6:00 AM",
        polls_close="7:00 PM",
    ),
}


def get_state_config(state_code: str) -> StateElectionConfig:
    """Get election configuration for a state.

    Args:
        state_code: Two-letter state code (e.g., "CA", "TX")

    Returns:
        StateElectionConfig for the state

    Raises:
        KeyError: If state is not yet supported
    """
    return STATE_CONFIGS[state_code.upper()]


def supported_states() -> list:
    """Return list of supported state codes."""
    return sorted(STATE_CONFIGS.keys())
