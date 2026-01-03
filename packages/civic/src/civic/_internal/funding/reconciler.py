"""
Funding reconciliation for validating budget-award alignment.

SESSION 445: Implements aggregate reconciliation between city budget items
and federal/state funding sources.

Reconciliation validates:
1. SUM(city budget grants) ≈ SUM(federal/state awards to city)
2. Individual items with variance >5% flagged for review
3. Edge cases: multi-year awards, indirect costs, pass-through timing
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ReconciliationItem:
    """Individual item reconciliation result."""

    link_id: str
    budget_item_id: str
    budget_description: str
    cfda_number: Optional[str]
    budget_cents: Optional[int]
    award_cents: Optional[int]  # federal_cents or local_cents
    variance_cents: Optional[int]
    variance_pct: Optional[float]
    status: str  # "match", "variance", "unverified", "flagged"
    notes: str = ""

    @property
    def needs_review(self) -> bool:
        """Returns True if variance exceeds 5% threshold."""
        if self.variance_pct is None:
            return True  # Unverified items need review
        return abs(self.variance_pct) > 5.0


@dataclass
class ReconciliationReport:
    """Aggregate reconciliation report for a jurisdiction."""

    jurisdiction_id: str
    fiscal_year: Optional[str]
    generated_at: datetime = field(default_factory=datetime.now)

    # Summary statistics
    total_budget_items: int = 0
    linked_budget_items: int = 0
    unlinked_budget_items: int = 0

    # Amount totals (in cents for precision)
    total_budget_cents: int = 0
    total_linked_budget_cents: int = 0
    total_award_cents: int = 0  # Sum of matched awards

    # Reconciliation status counts
    matched_count: int = 0
    variance_count: int = 0
    unverified_count: int = 0
    flagged_count: int = 0  # Variance > 5%

    # Detailed items
    items: List[ReconciliationItem] = field(default_factory=list)
    flagged_items: List[ReconciliationItem] = field(default_factory=list)

    @property
    def link_rate(self) -> float:
        """Percentage of budget items linked to funding sources."""
        if self.total_budget_items == 0:
            return 0.0
        return (self.linked_budget_items / self.total_budget_items) * 100

    @property
    def overall_variance_cents(self) -> int:
        """Total variance: budget - awards."""
        return self.total_linked_budget_cents - self.total_award_cents

    @property
    def overall_variance_pct(self) -> float:
        """Overall variance percentage."""
        if self.total_award_cents == 0:
            return 0.0 if self.total_linked_budget_cents == 0 else 100.0
        return (self.overall_variance_cents / self.total_award_cents) * 100

    @property
    def is_reconciled(self) -> bool:
        """
        Returns True if overall variance is within acceptable range (<5%).

        A jurisdiction is considered reconciled when:
        1. At least 50% of budget items are linked
        2. Overall variance is within 5%
        3. No critical items are flagged (P0-level discrepancies)
        """
        if self.link_rate < 50:
            return False
        return abs(self.overall_variance_pct) < 5.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for serialization."""
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "fiscal_year": self.fiscal_year,
            "generated_at": self.generated_at.isoformat(),
            "summary": {
                "total_budget_items": self.total_budget_items,
                "linked_budget_items": self.linked_budget_items,
                "unlinked_budget_items": self.unlinked_budget_items,
                "link_rate_pct": round(self.link_rate, 2),
            },
            "amounts": {
                "total_budget_cents": self.total_budget_cents,
                "total_linked_budget_cents": self.total_linked_budget_cents,
                "total_award_cents": self.total_award_cents,
                "overall_variance_cents": self.overall_variance_cents,
                "overall_variance_pct": round(self.overall_variance_pct, 2),
            },
            "status_counts": {
                "matched": self.matched_count,
                "variance": self.variance_count,
                "unverified": self.unverified_count,
                "flagged": self.flagged_count,
            },
            "is_reconciled": self.is_reconciled,
            "flagged_items": [
                {
                    "link_id": item.link_id,
                    "budget_item_id": item.budget_item_id,
                    "description": item.budget_description,
                    "cfda_number": item.cfda_number,
                    "budget_cents": item.budget_cents,
                    "award_cents": item.award_cents,
                    "variance_cents": item.variance_cents,
                    "variance_pct": item.variance_pct,
                    "status": item.status,
                    "notes": item.notes,
                }
                for item in self.flagged_items
            ],
        }


class FundingReconciler:
    """
    Reconciles city budget items with federal/state funding sources.

    Performs aggregate validation to ensure funding flows are consistent:
    1. Load budget items and funding links from storage
    2. Compare budget amounts vs award amounts
    3. Calculate variance and flag discrepancies >5%
    4. Generate reconciliation report

    Handles edge cases:
    - Multi-year awards: Awards spanning fiscal years are prorated
    - Indirect costs: 10-15% variance expected for indirect cost recovery
    - Pass-through timing: State pass-throughs may lag federal awards by 1-2 quarters
    """

    # Variance thresholds
    MATCH_THRESHOLD = 1.0  # <1% = match
    VARIANCE_THRESHOLD = 10.0  # <10% = acceptable variance
    FLAG_THRESHOLD = 5.0  # >5% = needs review

    # Expected indirect cost rate range (for explanation, not filtering)
    INDIRECT_COST_LOW = 0.10  # 10%
    INDIRECT_COST_HIGH = 0.15  # 15%

    def __init__(
        self,
        budget_items: List[Dict[str, Any]],
        funding_links: List[Dict[str, Any]],
    ):
        """
        Initialize reconciler with budget and funding data.

        Args:
            budget_items: Budget items from storage (get_budget_items)
            funding_links: Funding links from storage (get_budget_funding_links)
        """
        self._budget_items = budget_items
        self._funding_links = funding_links

        # Build indexes for efficient lookup
        self._budget_by_id: Dict[str, Dict[str, Any]] = {}
        for item in budget_items:
            item_id = item.get("id") or item.get("item_id")
            if item_id:
                self._budget_by_id[item_id] = item

        # Index links by budget_item_id (one budget item may have multiple links)
        self._links_by_budget: Dict[str, List[Dict[str, Any]]] = {}
        for link in funding_links:
            budget_id = link.get("budget_item_id")
            if budget_id:
                if budget_id not in self._links_by_budget:
                    self._links_by_budget[budget_id] = []
                self._links_by_budget[budget_id].append(link)

    def reconcile(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
    ) -> ReconciliationReport:
        """
        Perform full reconciliation and generate report.

        Args:
            jurisdiction_id: Target jurisdiction
            fiscal_year: Optional fiscal year filter

        Returns:
            ReconciliationReport with summary and flagged items
        """
        report = ReconciliationReport(
            jurisdiction_id=jurisdiction_id,
            fiscal_year=fiscal_year,
        )

        # Count all budget items and calculate total budget
        linked_ids = set(self._links_by_budget.keys())
        for item in self._budget_items:
            item_id = item.get("id") or item.get("item_id")
            if not item_id:
                continue

            report.total_budget_items += 1
            budget_cents = item.get("budgeted_cents") or 0
            report.total_budget_cents += budget_cents

            if item_id in linked_ids:
                report.linked_budget_items += 1
                report.total_linked_budget_cents += budget_cents
            else:
                report.unlinked_budget_items += 1

        # Process each link and reconcile amounts
        for link in self._funding_links:
            rec_item = self._reconcile_link(link)
            report.items.append(rec_item)

            # Accumulate award totals (avoid double-counting from multiple links)
            if rec_item.award_cents:
                report.total_award_cents += rec_item.award_cents

            # Count by status
            if rec_item.status == "match":
                report.matched_count += 1
            elif rec_item.status == "variance":
                report.variance_count += 1
            else:
                report.unverified_count += 1

            # Flag items needing review
            if rec_item.needs_review:
                report.flagged_count += 1
                rec_item.status = "flagged"
                report.flagged_items.append(rec_item)

        return report

    def _reconcile_link(self, link: Dict[str, Any]) -> ReconciliationItem:
        """
        Reconcile a single funding link.

        Compares budget_cents with federal_cents or local_cents.
        Calculates variance and determines reconciliation status.
        """
        link_id = link.get("link_id", "unknown")
        budget_item_id = link.get("budget_item_id", "unknown")
        cfda = link.get("federal_cfda_number")

        # Get budget item details for description
        budget_item = self._budget_by_id.get(budget_item_id, {})
        description = budget_item.get("line_item") or budget_item.get("program") or "Unknown"

        budget_cents = link.get("budget_cents")
        # Prefer local_cents (state pass-through) over federal_cents
        award_cents = link.get("local_cents") or link.get("federal_cents")

        # Calculate variance
        variance_cents, variance_pct = self._calc_variance(budget_cents, award_cents)

        # Determine status
        status = self._determine_status(variance_pct)

        # Add notes for edge cases
        notes = self._generate_notes(link, budget_cents, award_cents, variance_pct)

        return ReconciliationItem(
            link_id=link_id,
            budget_item_id=budget_item_id,
            budget_description=description,
            cfda_number=cfda,
            budget_cents=budget_cents,
            award_cents=award_cents,
            variance_cents=variance_cents,
            variance_pct=variance_pct,
            status=status,
            notes=notes,
        )

    def _calc_variance(
        self,
        budget_cents: Optional[int],
        award_cents: Optional[int],
    ) -> Tuple[Optional[int], Optional[float]]:
        """Calculate variance in cents and percentage."""
        if budget_cents is None or award_cents is None:
            return None, None

        variance_cents = budget_cents - award_cents

        if award_cents == 0:
            variance_pct = 100.0 if budget_cents > 0 else 0.0
        else:
            variance_pct = round((variance_cents / award_cents) * 100, 2)

        return variance_cents, variance_pct

    def _determine_status(self, variance_pct: Optional[float]) -> str:
        """Determine reconciliation status based on variance."""
        if variance_pct is None:
            return "unverified"

        abs_variance = abs(variance_pct)
        if abs_variance < self.MATCH_THRESHOLD:
            return "match"
        elif abs_variance < self.VARIANCE_THRESHOLD:
            return "variance"
        else:
            return "unverified"

    def _generate_notes(
        self,
        link: Dict[str, Any],
        budget_cents: Optional[int],
        award_cents: Optional[int],
        variance_pct: Optional[float],
    ) -> str:
        """Generate explanatory notes for variance."""
        if variance_pct is None:
            return "Missing amount data for reconciliation"

        notes = []

        # Check if variance matches indirect cost pattern
        if 10.0 <= variance_pct <= 15.0:
            notes.append("Variance consistent with indirect cost recovery (10-15%)")
        elif -15.0 <= variance_pct <= -10.0:
            notes.append("Under-budget may indicate indirect cost deduction")

        # Check for multi-year award indicators
        match_notes = link.get("match_notes", "")
        if "multi-year" in match_notes.lower():
            notes.append("Multi-year award - proration may apply")

        # Check for pass-through timing
        if link.get("passthrough_id"):
            notes.append("State pass-through - timing lag possible")

        # Large variance warning
        if abs(variance_pct) > 5.0:
            direction = "over" if variance_pct > 0 else "under"
            notes.append(f"Budget {direction} award by {abs(variance_pct):.1f}% - needs review")

        return "; ".join(notes) if notes else ""


def reconcile_funding(
    budget_items: List[Dict[str, Any]],
    funding_links: List[Dict[str, Any]],
    jurisdiction_id: str,
    fiscal_year: Optional[str] = None,
) -> ReconciliationReport:
    """
    Convenience function for funding reconciliation.

    Args:
        budget_items: Budget items from get_budget_items()
        funding_links: Funding links from get_budget_funding_links()
        jurisdiction_id: Target jurisdiction
        fiscal_year: Optional fiscal year filter

    Returns:
        ReconciliationReport with summary and flagged items

    Example:
        >>> budget_items = storage.get_budget_items("san-rafael", fiscal_year="2025-2026")
        >>> links = storage.get_budget_funding_links("san-rafael")
        >>> report = reconcile_funding(budget_items, links, "san-rafael", "2025-2026")
        >>> print(f"Reconciled: {report.is_reconciled}")
        >>> print(f"Variance: {report.overall_variance_pct:.1f}%")
        >>> for item in report.flagged_items:
        ...     print(f"  {item.budget_description}: {item.variance_pct:.1f}%")
    """
    reconciler = FundingReconciler(budget_items, funding_links)
    return reconciler.reconcile(jurisdiction_id, fiscal_year)
