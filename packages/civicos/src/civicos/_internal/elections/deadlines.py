"""
California election deadline generator.

Computes standard election deadlines based on election date.
California Elections Code sets fixed offsets from election day for
voter registration, vote-by-mail, and conditional registration.
"""

from datetime import date, timedelta
from typing import List, Optional

from civicos._internal.elections import ElectionDeadline


def generate_ca_deadlines(election_date: date, as_of: Optional[date] = None) -> List[ElectionDeadline]:
    """
    Generate standard California election deadlines relative to election day.

    California deadlines (Elections Code):
    - Voter registration: 15 days before election
    - Conditional registration: available at county office through election day
    - VBM ballots mailed: 29 days before election
    - Early in-person voting: 10 days before election (county-dependent)
    - Election day

    Args:
        election_date: The election date
        as_of: Reference date for is_passed calculation (defaults to today)

    Returns:
        List of ElectionDeadline objects sorted by date
    """
    if as_of is None:
        as_of = date.today()

    deadlines = [
        ElectionDeadline(
            deadline_type="vbm_ballots_mailed",
            deadline_date=election_date - timedelta(days=29),
            description="Vote-by-mail ballots begin mailing to registered voters",
            is_passed=(election_date - timedelta(days=29)) < as_of,
        ),
        ElectionDeadline(
            deadline_type="voter_registration",
            deadline_date=election_date - timedelta(days=15),
            description="Last day to register to vote (online, by mail, or in person)",
            is_passed=(election_date - timedelta(days=15)) < as_of,
        ),
        ElectionDeadline(
            deadline_type="early_voting_start",
            deadline_date=election_date - timedelta(days=10),
            description="Early in-person voting begins at county elections office",
            is_passed=(election_date - timedelta(days=10)) < as_of,
        ),
        ElectionDeadline(
            deadline_type="conditional_registration",
            deadline_date=election_date,
            description=(
                "Conditional voter registration available at county elections "
                "office or vote center through election day"
            ),
            is_passed=election_date < as_of,
        ),
        ElectionDeadline(
            deadline_type="election_day",
            deadline_date=election_date,
            description="Election day — polls open 7:00 AM to 8:00 PM",
            is_passed=election_date < as_of,
        ),
    ]

    return sorted(deadlines, key=lambda d: (d.deadline_date, d.deadline_type))
