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
