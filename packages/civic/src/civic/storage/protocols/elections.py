"""
ElectionStorage protocol for election-related data.

Handles elections, contests, deadlines, and elected officials.
Data sources: Google Civic API, county registrars.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ElectionStorage(Protocol):
    """
    Protocol for election and official storage.

    Covers the election lifecycle:
    - Elections: Upcoming and past elections (federal, state, local)
    - Deadlines: Registration, voting period dates
    - Contests: Races and ballot measures
    - Officials: Elected representatives with voting records

    Officials link elections (candidates) to decisions (votes),
    enabling queries like "How did Councilmember X vote on housing?"
    """

    # ========== Election Methods ==========

    def store_elections(
        self,
        jurisdiction_id: str,
        elections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store elections with temporal versioning."""
        ...

    def get_elections(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        include_past: bool = False,
        election_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve elections with optional filtering."""
        ...

    def get_election_count(self, jurisdiction_id: str) -> int:
        """Get count of current elections for a jurisdiction."""
        ...

    # ========== Deadline Methods ==========

    def store_election_deadlines(
        self,
        election_id: str,
        deadlines: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store election deadlines with temporal versioning."""
        ...

    def get_election_deadlines(
        self,
        election_id: str,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve deadlines for an election."""
        ...

    # ========== Contest Methods ==========

    def store_election_contests(
        self,
        election_id: str,
        contests: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store election contests with temporal versioning."""
        ...

    def get_election_contests(
        self,
        election_id: str,
        contest_type: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve contests for an election."""
        ...

    # ========== Elected Officials Methods ==========

    def store_elected_officials(
        self,
        jurisdiction_id: str,
        officials: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store elected officials with temporal versioning."""
        ...

    def get_elected_officials(
        self,
        jurisdiction_id: str,
        current_only: bool = True,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve elected officials."""
        ...

    def get_official_by_name(
        self,
        jurisdiction_id: str,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """Find official by name (fuzzy match on name_variations)."""
        ...
