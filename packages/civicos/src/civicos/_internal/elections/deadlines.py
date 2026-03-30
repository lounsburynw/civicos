"""
Election deadline generator.

Computes standard election deadlines based on election date and state
configuration. Each state's election code sets different offsets for
voter registration, vote-by-mail, early voting, etc.

State-specific offsets are configured in state_config.py. This module
provides the generic generation logic.
"""

from datetime import date, timedelta
from typing import List, Optional

from civicos._internal.elections import ElectionDeadline
from civicos._internal.elections.state_config import get_state_config


def generate_deadlines(
    election_date: date,
    state_code: str = "CA",
    as_of: Optional[date] = None,
) -> List[ElectionDeadline]:
    """
    Generate election deadlines for a state, using configured offsets.

    Args:
        election_date: The election date
        state_code: Two-letter state code (e.g., "CA", "TX")
        as_of: Reference date for is_passed calculation (defaults to today)

    Returns:
        List of ElectionDeadline objects sorted by date
    """
    if as_of is None:
        as_of = date.today()

    config = get_state_config(state_code)
    deadlines = []

    # VBM ballots mailing (if the state has universal VBM)
    if config.vbm_mailing_days > 0:
        vbm_date = election_date - timedelta(days=config.vbm_mailing_days)
        deadlines.append(ElectionDeadline(
            deadline_type="vbm_ballots_mailed",
            deadline_date=vbm_date,
            description="Vote-by-mail ballots begin mailing to registered voters",
            is_passed=vbm_date < as_of,
        ))

    # Voter registration deadline
    reg_date = election_date - timedelta(days=config.registration_deadline_days)
    deadlines.append(ElectionDeadline(
        deadline_type="voter_registration",
        deadline_date=reg_date,
        description="Last day to register to vote (online, by mail, or in person)",
        is_passed=reg_date < as_of,
    ))

    # Early voting start (if the state has early voting)
    if config.early_voting_start_days > 0:
        early_date = election_date - timedelta(days=config.early_voting_start_days)
        deadlines.append(ElectionDeadline(
            deadline_type="early_voting_start",
            deadline_date=early_date,
            description="Early in-person voting begins",
            is_passed=early_date < as_of,
        ))

    # Conditional/same-day registration (if available)
    if config.conditional_registration:
        deadlines.append(ElectionDeadline(
            deadline_type="conditional_registration",
            deadline_date=election_date,
            description=(
                "Conditional voter registration available at county elections "
                "office or vote center through election day"
            ),
            is_passed=election_date < as_of,
        ))

    # Election day
    deadlines.append(ElectionDeadline(
        deadline_type="election_day",
        deadline_date=election_date,
        description=f"Election day — polls open {config.polls_open} to {config.polls_close}",
        is_passed=election_date < as_of,
    ))

    return sorted(deadlines, key=lambda d: (d.deadline_date, d.deadline_type))


def generate_ca_deadlines(election_date: date, as_of: Optional[date] = None) -> List[ElectionDeadline]:
    """
    Generate standard California election deadlines.

    Backward-compatible wrapper around generate_deadlines().
    """
    return generate_deadlines(election_date, state_code="CA", as_of=as_of)
