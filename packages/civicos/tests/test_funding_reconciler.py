"""
Tests for FundingReconciler and reconciliation logic.

SESSION 445: Validates budget-award reconciliation.
"""

import pytest
from datetime import datetime

from civicos._internal.funding import (
    FundingReconciler,
    ReconciliationItem,
    ReconciliationReport,
    reconcile_funding,
)


class TestReconciliationItem:
    """Tests for ReconciliationItem dataclass."""

    def test_needs_review_when_variance_high(self):
        """Items with variance >5% need review."""
        item = ReconciliationItem(
            link_id="link-1",
            budget_item_id="budget-1",
            budget_description="CDBG Grant",
            cfda_number="14.218",
            budget_cents=100_000_00,  # $100,000
            award_cents=90_000_00,  # $90,000
            variance_cents=10_000_00,  # $10,000
            variance_pct=11.11,
            status="variance",
        )
        assert item.needs_review is True

    def test_no_review_when_variance_low(self):
        """Items with variance <5% don't need review."""
        item = ReconciliationItem(
            link_id="link-1",
            budget_item_id="budget-1",
            budget_description="Transit Grant",
            cfda_number="20.507",
            budget_cents=100_000_00,
            award_cents=98_000_00,
            variance_cents=2_000_00,
            variance_pct=2.04,
            status="variance",
        )
        assert item.needs_review is False

    def test_needs_review_when_unverified(self):
        """Unverified items (missing amounts) need review."""
        item = ReconciliationItem(
            link_id="link-1",
            budget_item_id="budget-1",
            budget_description="Unknown Grant",
            cfda_number=None,
            budget_cents=100_000_00,
            award_cents=None,
            variance_cents=None,
            variance_pct=None,
            status="unverified",
        )
        assert item.needs_review is True


class TestReconciliationReport:
    """Tests for ReconciliationReport dataclass."""

    def test_link_rate_calculation(self):
        """Link rate is calculated correctly."""
        report = ReconciliationReport(
            jurisdiction_id="san-rafael",
            fiscal_year="2025-2026",
            total_budget_items=100,
            linked_budget_items=75,
            unlinked_budget_items=25,
        )
        assert report.link_rate == 75.0

    def test_link_rate_zero_items(self):
        """Link rate handles zero budget items."""
        report = ReconciliationReport(
            jurisdiction_id="san-rafael",
            fiscal_year="2025-2026",
            total_budget_items=0,
            linked_budget_items=0,
        )
        assert report.link_rate == 0.0

    def test_overall_variance_calculation(self):
        """Overall variance is budget - awards."""
        report = ReconciliationReport(
            jurisdiction_id="san-rafael",
            fiscal_year="2025-2026",
            total_linked_budget_cents=1_000_000_00,  # $1,000,000
            total_award_cents=950_000_00,  # $950,000
        )
        assert report.overall_variance_cents == 50_000_00  # $50,000
        assert report.overall_variance_pct == pytest.approx(5.26, rel=0.01)

    def test_is_reconciled_when_under_threshold(self):
        """Reconciled when variance <5% and link rate >50%."""
        report = ReconciliationReport(
            jurisdiction_id="san-rafael",
            fiscal_year="2025-2026",
            total_budget_items=100,
            linked_budget_items=80,
            total_linked_budget_cents=1_000_000_00,
            total_award_cents=980_000_00,  # 2% variance
        )
        assert report.is_reconciled is True

    def test_not_reconciled_when_variance_high(self):
        """Not reconciled when variance >5%."""
        report = ReconciliationReport(
            jurisdiction_id="san-rafael",
            fiscal_year="2025-2026",
            total_budget_items=100,
            linked_budget_items=80,
            total_linked_budget_cents=1_000_000_00,
            total_award_cents=900_000_00,  # 11% variance
        )
        assert report.is_reconciled is False

    def test_not_reconciled_when_link_rate_low(self):
        """Not reconciled when link rate <50%."""
        report = ReconciliationReport(
            jurisdiction_id="san-rafael",
            fiscal_year="2025-2026",
            total_budget_items=100,
            linked_budget_items=40,  # Only 40%
            total_linked_budget_cents=400_000_00,
            total_award_cents=395_000_00,  # Low variance but low link rate
        )
        assert report.is_reconciled is False

    def test_to_dict_structure(self):
        """to_dict returns expected structure."""
        report = ReconciliationReport(
            jurisdiction_id="san-rafael",
            fiscal_year="2025-2026",
            total_budget_items=10,
            linked_budget_items=8,
            unlinked_budget_items=2,
            total_budget_cents=1_000_00,
            total_linked_budget_cents=800_00,
            total_award_cents=780_00,
            matched_count=5,
            variance_count=2,
            unverified_count=1,
            flagged_count=1,
        )
        d = report.to_dict()

        assert d["jurisdiction_id"] == "san-rafael"
        assert d["fiscal_year"] == "2025-2026"
        assert "summary" in d
        assert d["summary"]["total_budget_items"] == 10
        assert d["summary"]["link_rate_pct"] == 80.0
        assert "amounts" in d
        assert d["amounts"]["overall_variance_cents"] == 20_00
        assert "status_counts" in d
        assert d["status_counts"]["matched"] == 5


class TestFundingReconciler:
    """Tests for FundingReconciler class."""

    def test_reconcile_matched_items(self):
        """Budget items matching awards are reconciled."""
        budget_items = [
            {"id": "bi-1", "line_item": "CDBG Grant", "budgeted_cents": 100_000_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "federal_cfda_number": "14.218",
                "budget_cents": 100_000_00,
                "federal_cents": 100_000_00,
            },
        ]

        reconciler = FundingReconciler(budget_items, funding_links)
        report = reconciler.reconcile("san-rafael", "2025-2026")

        assert report.total_budget_items == 1
        assert report.linked_budget_items == 1
        assert report.matched_count == 1
        assert report.flagged_count == 0

    def test_reconcile_variance_items(self):
        """Items with variance <10% are tracked."""
        budget_items = [
            {"id": "bi-1", "line_item": "Transit Grant", "budgeted_cents": 100_000_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "federal_cfda_number": "20.507",
                "budget_cents": 100_000_00,
                "federal_cents": 93_000_00,  # 7.5% variance
            },
        ]

        reconciler = FundingReconciler(budget_items, funding_links)
        report = reconciler.reconcile("san-rafael")

        assert report.variance_count == 1
        assert report.flagged_count == 1  # >5% flagged

    def test_reconcile_unverified_items(self):
        """Items without award amounts are unverified."""
        budget_items = [
            {"id": "bi-1", "line_item": "Unknown Grant", "budgeted_cents": 50_000_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "federal_cfda_number": "97.039",
                "budget_cents": 50_000_00,
                # No federal_cents or local_cents
            },
        ]

        reconciler = FundingReconciler(budget_items, funding_links)
        report = reconciler.reconcile("san-rafael")

        assert report.unverified_count == 1
        assert report.flagged_count == 1

    def test_reconcile_prefers_local_cents(self):
        """State pass-through (local_cents) is preferred over federal_cents."""
        budget_items = [
            {"id": "bi-1", "line_item": "State Pass-through", "budgeted_cents": 100_000_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "passthrough_id": "pt-1",
                "budget_cents": 100_000_00,
                "federal_cents": 120_000_00,  # Different from local
                "local_cents": 100_000_00,  # Matches budget
            },
        ]

        reconciler = FundingReconciler(budget_items, funding_links)
        report = reconciler.reconcile("san-rafael")

        assert report.matched_count == 1
        assert len(report.items) == 1
        assert report.items[0].award_cents == 100_000_00

    def test_reconcile_aggregate_totals(self):
        """Aggregate totals are calculated correctly."""
        budget_items = [
            {"id": "bi-1", "line_item": "Grant 1", "budgeted_cents": 100_000_00},
            {"id": "bi-2", "line_item": "Grant 2", "budgeted_cents": 200_000_00},
            {"id": "bi-3", "line_item": "Unlinked", "budgeted_cents": 50_000_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "budget_cents": 100_000_00,
                "federal_cents": 100_000_00,
            },
            {
                "link_id": "link-2",
                "budget_item_id": "bi-2",
                "budget_cents": 200_000_00,
                "federal_cents": 190_000_00,  # 5.26% variance
            },
        ]

        reconciler = FundingReconciler(budget_items, funding_links)
        report = reconciler.reconcile("san-rafael")

        assert report.total_budget_items == 3
        assert report.linked_budget_items == 2
        assert report.unlinked_budget_items == 1
        assert report.total_budget_cents == 350_000_00
        assert report.total_linked_budget_cents == 300_000_00
        assert report.total_award_cents == 290_000_00


class TestReconcileFundingFunction:
    """Tests for convenience function."""

    def test_reconcile_funding_convenience(self):
        """reconcile_funding() provides same results as class."""
        budget_items = [
            {"id": "bi-1", "line_item": "CDBG", "budgeted_cents": 100_000_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "federal_cfda_number": "14.218",
                "budget_cents": 100_000_00,
                "federal_cents": 100_000_00,
            },
        ]

        report = reconcile_funding(
            budget_items, funding_links, "san-rafael", "2025-2026"
        )

        assert isinstance(report, ReconciliationReport)
        assert report.jurisdiction_id == "san-rafael"
        assert report.fiscal_year == "2025-2026"
        assert report.is_reconciled is True


class TestEdgeCases:
    """Tests for edge case handling."""

    def test_indirect_cost_variance_noted(self):
        """Variance in 10-15% range suggests indirect costs."""
        budget_items = [
            {"id": "bi-1", "line_item": "Grant with IDC", "budgeted_cents": 112_000_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "budget_cents": 112_000_00,
                "federal_cents": 100_000_00,  # 12% variance
            },
        ]

        reconciler = FundingReconciler(budget_items, funding_links)
        report = reconciler.reconcile("san-rafael")

        assert len(report.items) == 1
        assert "indirect cost" in report.items[0].notes.lower()

    def test_passthrough_timing_noted(self):
        """State pass-throughs get timing note."""
        budget_items = [
            {"id": "bi-1", "line_item": "State Grant", "budgeted_cents": 100_000_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "passthrough_id": "pt-1",
                "budget_cents": 100_000_00,
                "local_cents": 90_000_00,  # >5% variance
            },
        ]

        reconciler = FundingReconciler(budget_items, funding_links)
        report = reconciler.reconcile("san-rafael")

        assert len(report.items) == 1
        assert "pass-through" in report.items[0].notes.lower()

    def test_empty_budget_items(self):
        """Empty budget items returns empty report."""
        report = reconcile_funding([], [], "san-rafael")

        assert report.total_budget_items == 0
        assert report.is_reconciled is False

    def test_budget_item_id_variations(self):
        """Handles both 'id' and 'item_id' fields."""
        budget_items = [
            {"item_id": "bi-1", "line_item": "Grant", "budgeted_cents": 100_00},
        ]
        funding_links = [
            {
                "link_id": "link-1",
                "budget_item_id": "bi-1",
                "budget_cents": 100_00,
                "federal_cents": 100_00,
            },
        ]

        report = reconcile_funding(budget_items, funding_links, "san-rafael")

        assert report.total_budget_items == 1
        assert report.linked_budget_items == 1
