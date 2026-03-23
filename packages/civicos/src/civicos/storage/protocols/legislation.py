"""
LegislationStorage protocol for legal document storage.

Handles state/federal legislation, municipal codes, codified law (U.S. Code),
and executive orders. Used for what_applies() queries.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class LegislationStorage(Protocol):
    """
    Protocol for legislation and legal document storage.

    Covers legal corpora:
    - Legislation: State and federal bills (CA, US)
    - Municipal Code: Local ordinances (city-specific)
    - Codified Law: U.S. Code and state codes
    - Executive Orders: Presidential directives

    Key variations from ContentStorage:
    - Legislation uses 'state' not 'jurisdiction_id'
    - Executive Orders are national (no jurisdiction)
    - Codified Law uses jurisdiction_id for federal-US, state-CA, etc.
    """

    # ========== Legislation Methods ==========

    def store_legislation(
        self,
        state: str,
        bills: List[Dict[str, Any]],
        topic: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store state/federal legislation with temporal versioning."""
        ...

    def get_legislation(
        self,
        state: str,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve legislation with optional filtering."""
        ...

    def get_legislation_by_bill_id(
        self,
        state: str,
        bill_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get specific legislation by bill_id."""
        ...

    def get_legislation_batch(
        self,
        state: str,
        bill_ids: List[str],
        as_of: Optional[datetime] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Batch fetch multiple legislation bills by bill_id."""
        ...

    def get_legislation_count(self, state: str, topic: Optional[str] = None) -> int:
        """Get count of current legislation for a state."""
        ...

    def update_legislation_text(
        self,
        state: str,
        updates: List[Dict[str, Any]],
    ) -> int:
        """Update full_text for legislation bills."""
        ...

    def update_legislation_topics(
        self,
        state: str,
        updates: List[Dict[str, Any]],
    ) -> int:
        """
        Update topic field for legislation bills.

        Args:
            state: State code (e.g., "CA", "US")
            updates: List of dicts with 'bill_id' and 'topic'

        Returns:
            Number of bills updated
        """
        ...

    def update_legislation_leverage_points(
        self,
        state: str,
        updates: List[Dict[str, Any]],
    ) -> int:
        """
        Update leverage_point field for legislation bills.

        Args:
            state: State code (e.g., "CA", "US")
            updates: List of dicts with 'bill_id' and 'leverage_point'

        Returns:
            Number of bills updated
        """
        ...

    # ========== Municipal Code Methods ==========

    def store_municipal_code(
        self,
        jurisdiction_id: str,
        sections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store municipal code sections with temporal versioning."""
        ...

    def get_municipal_code(
        self,
        jurisdiction_id: str,
        chapter: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve municipal code sections with temporal filtering."""
        ...

    def get_municipal_code_section(
        self,
        jurisdiction_id: str,
        section_number: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get specific municipal code section by section number."""
        ...

    def get_municipal_code_count(self, jurisdiction_id: str) -> int:
        """Get count of current municipal code sections for a jurisdiction."""
        ...

    # ========== Codified Law Methods ==========

    def store_codified_law(
        self,
        jurisdiction_id: str,
        sections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        use_copy: bool = True,
    ) -> int:
        """Store codified law sections (U.S. Code, CA Codes) with temporal versioning."""
        ...

    def get_codified_law(
        self,
        jurisdiction_id: str,
        title_number: Optional[int] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve codified law sections with optional filtering."""
        ...

    def search_codified_law(
        self,
        jurisdiction_id: str,
        query: str,
        title_number: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search codified law sections by topic/keyword."""
        ...

    def get_codified_law_count(
        self,
        jurisdiction_id: str,
        title_number: Optional[int] = None,
        include_inactive: bool = False,
    ) -> int:
        """Get count of current codified law sections for a jurisdiction."""
        ...

    # ========== Executive Orders Methods ==========

    def store_executive_orders(
        self,
        orders: List[Dict[str, Any]],
        use_copy: bool = True,
    ) -> int:
        """Store Executive Orders from Federal Register API."""
        ...

    def get_executive_orders(
        self,
        president: Optional[str] = None,
        eo_number: Optional[int] = None,
        status: Optional[str] = None,
        signing_date_after: Optional[date] = None,
        signing_date_before: Optional[date] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve Executive Orders with optional filtering."""
        ...

    def search_executive_orders(
        self,
        query: str,
        president: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search Executive Orders by topic/keyword."""
        ...

    def get_executive_orders_count(
        self,
        president: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Get count of Executive Orders."""
        ...

    # ========== Federal Rules Methods (Rulemaking / Comment Periods) ==========

    def store_federal_rules(
        self,
        rules: List[Dict[str, Any]],
    ) -> int:
        """Store federal rulemaking documents (proposed rules, final rules, notices)."""
        ...

    def get_federal_rules(
        self,
        document_type: Optional[str] = None,
        comments_open: bool = False,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve federal rules with optional filtering."""
        ...

    def get_open_comment_periods(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get federal rules with open comment periods, sorted by deadline."""
        ...

    def search_federal_rules(
        self,
        query: str,
        document_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search federal rules by topic/keyword using full-text search."""
        ...

    def get_federal_rules_count(
        self,
        document_type: Optional[str] = None,
    ) -> int:
        """Get count of federal rules."""
        ...

    # ========== Legislative Events Methods (Hearings, Votes) ==========

    def store_legislative_events(
        self,
        events: List[Dict[str, Any]],
    ) -> int:
        """Store legislative events (hearings, votes, signings)."""
        ...

    def get_legislative_events(
        self,
        bill_id: Optional[str] = None,
        state: Optional[str] = None,
        event_type: Optional[str] = None,
        upcoming_only: bool = False,
        days_ahead: int = 30,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve legislative events with optional filtering."""
        ...

    def get_upcoming_hearings(
        self,
        state: Optional[str] = None,
        days_ahead: int = 30,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get upcoming legislative hearings."""
        ...

    def get_legislative_events_count(
        self,
        state: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> int:
        """Get count of legislative events."""
        ...

    # ========== Congressional Votes Methods ==========

    def store_congressional_votes(
        self,
        votes: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store congressional vote records with temporal versioning.

        Atomic operation: either all votes are stored or none.
        Uses upsert semantics based on (vote_id, bioguide_id).
        """
        ...

    def get_congressional_votes(
        self,
        bioguide_id: Optional[str] = None,
        bill_id: Optional[str] = None,
        chamber: Optional[str] = None,
        congress: Optional[int] = None,
        vote_date_start: Optional[str] = None,
        vote_date_end: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve congressional votes with optional filtering."""
        ...

    def get_congressional_votes_count(
        self,
        bioguide_id: Optional[str] = None,
        chamber: Optional[str] = None,
    ) -> int:
        """Get count of current congressional votes."""
        ...

    # ========== Congressional Hearings Methods ==========

    def store_congressional_hearings(
        self,
        hearings: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store congressional committee hearings with temporal versioning.

        Atomic operation: either all hearings are stored or none.
        Uses upsert semantics based on (event_id, chamber).
        """
        ...

    def get_congressional_hearings(
        self,
        committee_code: Optional[str] = None,
        chamber: Optional[str] = None,
        hearing_date_start: Optional[str] = None,
        hearing_date_end: Optional[str] = None,
        hearing_type: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve congressional hearings with optional filtering."""
        ...

    def get_congressional_hearings_count(
        self,
        chamber: Optional[str] = None,
    ) -> int:
        """Get count of current congressional hearings."""
        ...
