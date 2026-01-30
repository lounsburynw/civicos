"""
FinancialStorage protocol for budget and funding data.

Handles budget items, federal awards, state pass-through funds,
budget-funding links, and federal program allocations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class FinancialStorage(Protocol):
    """
    Protocol for financial and funding data storage.

    Covers the intergovernmental funding flow:
    - Budget Items: Municipal/county budget line items
    - Federal Awards: Grants from federal agencies (USAspending)
    - State Pass-Through: Federal funds via state agencies
    - Budget Funding Links: Connect budget items to funding sources
    - Federal Programs: National program definitions and allocations

    All amounts stored in cents for integer precision.
    """

    # ========== Budget Items Methods ==========

    def store_budget_items(
        self,
        jurisdiction_id: str,
        items: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        use_copy: bool = True,
    ) -> int:
        """Store budget line items with temporal versioning."""
        ...

    def get_budget_items(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
        fund: Optional[str] = None,
        department: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve budget items with optional filtering."""
        ...

    def get_budget_summary(
        self,
        jurisdiction_id: str,
        fiscal_year: str,
        group_by: str = "department",
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get aggregated budget summary grouped by department, fund, or program."""
        ...

    def get_budget_items_count(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
    ) -> int:
        """Get count of budget items for a jurisdiction."""
        ...

    # ========== Federal Awards Methods ==========

    def store_federal_awards(
        self,
        jurisdiction_id: str,
        awards: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store federal awards/grants with temporal versioning."""
        ...

    def get_federal_awards(
        self,
        jurisdiction_id: str,
        cfda_number: Optional[str] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve federal awards with optional filtering."""
        ...

    def get_federal_awards_count(self, jurisdiction_id: str) -> int:
        """Get count of current federal awards for a jurisdiction."""
        ...

    # ========== State Pass-Through Methods ==========

    def store_state_passthrough_funds(
        self,
        jurisdiction_id: str,
        passthroughs: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store state pass-through funding records with temporal versioning."""
        ...

    def get_state_passthrough_funds(
        self,
        jurisdiction_id: str,
        state_agency: Optional[str] = None,
        federal_cfda_number: Optional[str] = None,
        federal_award_id: Optional[str] = None,
        federal_fiscal_year: Optional[int] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve state pass-through funding records with optional filtering."""
        ...

    def get_state_passthrough_count(self, jurisdiction_id: str) -> int:
        """Get count of current state pass-through records for a jurisdiction."""
        ...

    # ========== Budget Funding Links Methods ==========

    def store_budget_funding_links(
        self,
        jurisdiction_id: str,
        links: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store links between budget items and their funding sources."""
        ...

    def get_budget_funding_links(
        self,
        jurisdiction_id: str,
        budget_item_id: Optional[str] = None,
        federal_cfda_number: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        match_type: Optional[str] = None,
        confirmed_only: bool = False,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve budget funding links with optional filtering."""
        ...

    def get_budget_funding_links_count(
        self,
        jurisdiction_id: str,
        confirmed_only: bool = False,
    ) -> int:
        """Get count of current budget funding links for a jurisdiction."""
        ...

    def confirm_budget_funding_link(
        self,
        jurisdiction_id: str,
        link_id: str,
        confirmed_by: str,
    ) -> bool:
        """Confirm an AI-suggested budget funding link."""
        ...

    # ========== Federal Programs Methods ==========

    def store_federal_programs(
        self,
        programs: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store federal program definitions with temporal versioning."""
        ...

    def get_federal_programs(
        self,
        program_id: Optional[str] = None,
        topic: Optional[str] = None,
        agency: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve federal program definitions with optional filtering."""
        ...

    def get_federal_programs_count(
        self,
        topic: Optional[str] = None,
    ) -> int:
        """Get count of current federal programs."""
        ...

    def store_federal_program_allocations(
        self,
        jurisdiction_id: str,
        allocations: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store jurisdiction-specific federal program allocations."""
        ...

    def get_federal_program_allocations(
        self,
        jurisdiction_id: str,
        program_id: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve federal program allocations for a jurisdiction."""
        ...

    def get_federal_program_allocations_count(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
    ) -> int:
        """Get count of current federal program allocations for a jurisdiction."""
        ...
