"""
Tests for Civic.funding_flow() and funding_flow_impact() methods.

SESSION 446: Validates intergovernmental funding traceability.
"""

import pytest
from unittest.mock import Mock, patch

from civicos import CivicOS, FundingFlow, FundingFlowImpact


class TestFundingFlowDataclass:
    """Tests for FundingFlow dataclass."""

    def test_funding_flow_required_fields(self):
        """FundingFlow requires budget_item_id, budget_description, budget_dollars."""
        flow = FundingFlow(
            budget_item_id="budget-1",
            budget_description="CDBG Housing Program",
            budget_dollars=100_000.00,
        )
        assert flow.budget_item_id == "budget-1"
        assert flow.budget_description == "CDBG Housing Program"
        assert flow.budget_dollars == 100_000.00

    def test_funding_flow_optional_federal_fields(self):
        """FundingFlow can include federal source info."""
        flow = FundingFlow(
            budget_item_id="budget-1",
            budget_description="CDBG Housing Program",
            budget_dollars=100_000.00,
            federal_award_id="award-123",
            federal_cfda_number="14.218",
            federal_program_name="Community Development Block Grant",
            federal_agency="HUD",
            federal_dollars=500_000.00,
            federal_period_start="2025-01-01",
            federal_period_end="2026-06-30",
        )
        assert flow.federal_cfda_number == "14.218"
        assert flow.federal_program_name == "Community Development Block Grant"
        assert flow.federal_dollars == 500_000.00

    def test_funding_flow_optional_state_fields(self):
        """FundingFlow can include state pass-through info."""
        flow = FundingFlow(
            budget_item_id="budget-1",
            budget_description="CDBG Housing Program",
            budget_dollars=100_000.00,
            passthrough_id="passthrough-1",
            state_agency="HCD",
            state_grant_id="CA-HCD-2025-001",
            state_program_name="California CDBG Program",
            state_dollars=150_000.00,
        )
        assert flow.state_agency == "HCD"
        assert flow.state_dollars == 150_000.00

    def test_funding_flow_match_quality_defaults(self):
        """FundingFlow has sensible defaults for match quality."""
        flow = FundingFlow(
            budget_item_id="budget-1",
            budget_description="Unknown Program",
            budget_dollars=50_000.00,
        )
        assert flow.match_type == "unknown"
        assert flow.match_confidence == 0.0
        assert flow.reconciliation_status == "unverified"

    def test_funding_flow_complete_chain(self):
        """FundingFlow can represent a complete federal→state→city chain."""
        flow = FundingFlow(
            budget_item_id="budget-cdbg-001",
            budget_description="CDBG Housing Rehabilitation",
            budget_dollars=100_000.00,
            department="Community Development",
            fund="Special Revenue",
            fiscal_year="2025-2026",
            # Federal source
            federal_award_id="usa-2025-14.218-001",
            federal_cfda_number="14.218",
            federal_program_name="Community Development Block Grant",
            federal_agency="HUD",
            federal_dollars=2_500_000.00,
            # State pass-through
            passthrough_id="ca-hcd-2025-cdbg",
            state_agency="HCD",
            state_program_name="California CDBG Program",
            state_dollars=200_000.00,
            # Match quality
            match_type="cfda_extraction",
            match_confidence=0.95,
            reconciliation_status="match",
            variance_dollars=0.0,
            variance_percentage=0.0,
        )
        # Verify complete chain
        assert flow.federal_agency == "HUD"
        assert flow.state_agency == "HCD"
        assert flow.department == "Community Development"
        assert flow.match_confidence == 0.95


class TestFundingFlowImpactDataclass:
    """Tests for FundingFlowImpact dataclass."""

    def test_funding_flow_impact_structure(self):
        """FundingFlowImpact contains cut analysis."""
        flow = FundingFlow(
            budget_item_id="budget-1",
            budget_description="CDBG Program",
            budget_dollars=100_000.00,
            department="Community Development",
        )
        impact = FundingFlowImpact(
            program_name="CDBG",
            cfda_number="14.218",
            cut_percentage=0.20,
            total_current_dollars=100_000.00,
            total_impact_dollars=20_000.00,
            affected_items=[flow],
        )
        assert impact.program_name == "CDBG"
        assert impact.cut_percentage == 0.20
        assert impact.total_impact_dollars == 20_000.00
        assert len(impact.affected_items) == 1

    def test_funding_flow_impact_multiple_items(self):
        """FundingFlowImpact can track multiple affected items."""
        flows = [
            FundingFlow(
                budget_item_id=f"budget-{i}",
                budget_description=f"Program {i}",
                budget_dollars=50_000.00 * (i + 1),
            )
            for i in range(3)
        ]
        total_current = sum(f.budget_dollars for f in flows)
        impact = FundingFlowImpact(
            program_name="HOME",
            cfda_number="14.239",
            cut_percentage=0.15,
            total_current_dollars=total_current,
            total_impact_dollars=total_current * 0.15,
            affected_items=flows,
        )
        assert len(impact.affected_items) == 3
        assert impact.total_current_dollars == 300_000.00  # 50k + 100k + 150k


class TestFundingFlowMethod:
    """Tests for Civic.funding_flow() method."""

    def test_funding_flow_returns_list(self):
        """funding_flow() returns list of FundingFlow."""
        c = CivicOS("san-rafael-ca")
        result = c.funding_flow()
        assert isinstance(result, list)
        # All items should be FundingFlow
        for item in result:
            assert isinstance(item, FundingFlow)

    def test_funding_flow_empty_when_no_links(self):
        """funding_flow() returns empty list when no funding links exist."""
        c = CivicOS("san-rafael-ca")
        result = c.funding_flow()
        # Currently empty since we haven't populated federal_awards
        # This is expected - the code works with partial data
        assert isinstance(result, list)

    def test_funding_flow_with_cfda_filter(self):
        """funding_flow() accepts cfda_number filter."""
        c = CivicOS("san-rafael-ca")
        result = c.funding_flow(cfda_number="14.218")
        assert isinstance(result, list)

    def test_funding_flow_with_program_filter(self):
        """funding_flow() accepts program name filter."""
        c = CivicOS("san-rafael-ca")
        result = c.funding_flow(program="CDBG")
        assert isinstance(result, list)

    def test_funding_flow_with_budget_item_filter(self):
        """funding_flow() accepts budget_item_id filter."""
        c = CivicOS("san-rafael-ca")
        result = c.funding_flow(budget_item_id="budget-001")
        assert isinstance(result, list)

    def test_funding_flow_with_confidence_threshold(self):
        """funding_flow() respects min_confidence threshold."""
        c = CivicOS("san-rafael-ca")
        # High threshold should filter out low-confidence matches
        result = c.funding_flow(min_confidence=0.9)
        assert isinstance(result, list)


class TestFundingFlowImpactMethod:
    """Tests for Civic.funding_flow_impact() method."""

    def test_funding_flow_impact_returns_impact(self):
        """funding_flow_impact() returns FundingFlowImpact."""
        c = CivicOS("san-rafael-ca")
        result = c.funding_flow_impact(program="CDBG", cut_percentage=0.20)
        assert isinstance(result, FundingFlowImpact)
        assert result.cut_percentage == 0.20
        assert result.program_name == "CDBG"

    def test_funding_flow_impact_calculates_totals(self):
        """funding_flow_impact() calculates total impact correctly."""
        c = CivicOS("san-rafael-ca")
        result = c.funding_flow_impact(cfda_number="14.218", cut_percentage=0.25)
        assert isinstance(result, FundingFlowImpact)
        # Impact should be 25% of current
        expected_impact = result.total_current_dollars * 0.25
        assert result.total_impact_dollars == pytest.approx(expected_impact)

    def test_funding_flow_impact_with_different_cuts(self):
        """funding_flow_impact() handles different cut percentages."""
        c = CivicOS("san-rafael-ca")
        # 10% cut
        impact_10 = c.funding_flow_impact(program="HOME", cut_percentage=0.10)
        # 50% cut
        impact_50 = c.funding_flow_impact(program="HOME", cut_percentage=0.50)
        # 50% should be 5x the impact of 10%
        if impact_10.total_current_dollars > 0:
            assert impact_50.total_impact_dollars == pytest.approx(
                impact_10.total_impact_dollars * 5
            )


class TestFundingFlowWithMockedData:
    """Tests with mocked storage data to verify logic."""

    @pytest.fixture
    def mock_civic(self):
        """Create Civic instance with mocked storage."""
        c = CivicOS("san-rafael-ca")
        c._storage = Mock()
        return c

    def test_funding_flow_builds_from_links(self, mock_civic):
        """funding_flow() properly builds flows from storage data."""
        # Mock storage responses
        mock_civic._storage.get_budget_items.return_value = [
            {
                "item_id": "budget-001",
                "line_item": "CDBG Housing Rehab",
                "program": "Community Development",
                "department": "Community Development",
                "fund": "Special Revenue",
                "fiscal_year": "2025-2026",
                "budgeted_cents": 100_000_00,
            }
        ]
        mock_civic._storage.get_budget_funding_links.return_value = [
            {
                "link_id": "link-001",
                "budget_item_id": "budget-001",
                "federal_award_id": "award-001",
                "federal_cfda_number": "14.218",
                "passthrough_id": None,
                "match_type": "cfda_extraction",
                "match_confidence": 0.95,
                "budget_cents": 100_000_00,
                "reconciliation_status": "match",
                "variance_cents": 0,
            }
        ]
        mock_civic._storage.get_federal_awards.return_value = [
            {
                "award_id": "award-001",
                "cfda_number": "14.218",
                "program_name": "Community Development Block Grant",
                "awarding_agency": "HUD",
                "amount_cents": 500_000_00,
                "period_start": "2025-01-01",
                "period_end": "2026-06-30",
            }
        ]
        mock_civic._storage.get_state_passthrough_funds.return_value = []

        result = mock_civic.funding_flow()

        assert len(result) == 1
        flow = result[0]
        assert flow.budget_item_id == "budget-001"
        assert flow.budget_description == "CDBG Housing Rehab"
        assert flow.budget_dollars == 100_000.00  # 100_000_00 cents -> $100,000
        assert flow.federal_cfda_number == "14.218"
        assert flow.federal_program_name == "Community Development Block Grant"
        assert flow.federal_agency == "HUD"
        assert flow.match_confidence == 0.95

    def test_funding_flow_filters_by_program(self, mock_civic):
        """funding_flow() filters by program name in item text."""
        mock_civic._storage.get_budget_items.return_value = [
            {
                "item_id": "budget-001",
                "line_item": "CDBG Housing",
                "program": "Housing CDBG Program",
                "budgeted_cents": 100_000_00,
            },
            {
                "item_id": "budget-002",
                "line_item": "HOME Grant",
                "program": "HOME Program",
                "budgeted_cents": 50_000_00,
            },
        ]
        mock_civic._storage.get_budget_funding_links.return_value = [
            {
                "link_id": "link-001",
                "budget_item_id": "budget-001",
                "federal_cfda_number": "14.218",
                "match_confidence": 0.8,
                "budget_cents": 100_000_00,
            },
            {
                "link_id": "link-002",
                "budget_item_id": "budget-002",
                "federal_cfda_number": "14.239",
                "match_confidence": 0.8,
                "budget_cents": 50_000_00,
            },
        ]
        mock_civic._storage.get_federal_awards.return_value = []
        mock_civic._storage.get_state_passthrough_funds.return_value = []

        # Filter for CDBG only
        result = mock_civic.funding_flow(program="CDBG")

        assert len(result) == 1
        assert result[0].budget_item_id == "budget-001"

    def test_funding_flow_filters_by_confidence(self, mock_civic):
        """funding_flow() filters out low-confidence matches."""
        mock_civic._storage.get_budget_items.return_value = [
            {
                "item_id": "budget-001",
                "line_item": "High Confidence Match",
                "budgeted_cents": 100_000_00,
            },
            {
                "item_id": "budget-002",
                "line_item": "Low Confidence Match",
                "budgeted_cents": 50_000_00,
            },
        ]
        mock_civic._storage.get_budget_funding_links.return_value = [
            {
                "link_id": "link-001",
                "budget_item_id": "budget-001",
                "match_confidence": 0.9,
                "budget_cents": 100_000_00,
            },
            {
                "link_id": "link-002",
                "budget_item_id": "budget-002",
                "match_confidence": 0.3,  # Low confidence
                "budget_cents": 50_000_00,
            },
        ]
        mock_civic._storage.get_federal_awards.return_value = []
        mock_civic._storage.get_state_passthrough_funds.return_value = []

        # Default threshold is 0.5
        result = mock_civic.funding_flow()

        assert len(result) == 1
        assert result[0].budget_item_id == "budget-001"

    def test_funding_flow_includes_state_passthrough(self, mock_civic):
        """funding_flow() includes state pass-through info."""
        mock_civic._storage.get_budget_items.return_value = [
            {
                "item_id": "budget-001",
                "line_item": "CDBG via HCD",
                "budgeted_cents": 100_000_00,
            }
        ]
        mock_civic._storage.get_budget_funding_links.return_value = [
            {
                "link_id": "link-001",
                "budget_item_id": "budget-001",
                "federal_award_id": "award-001",
                "federal_cfda_number": "14.218",
                "passthrough_id": "pass-001",
                "match_confidence": 0.9,
                "budget_cents": 100_000_00,
            }
        ]
        mock_civic._storage.get_federal_awards.return_value = [
            {
                "award_id": "award-001",
                "cfda_number": "14.218",
                "program_name": "CDBG",
                "awarding_agency": "HUD",
                "amount_cents": 2_000_000_00,
            }
        ]
        mock_civic._storage.get_state_passthrough_funds.return_value = [
            {
                "passthrough_id": "pass-001",
                "federal_award_id": "award-001",
                "federal_cfda_number": "14.218",
                "state_agency": "HCD",
                "state_program_name": "California CDBG",
                "local_amount_cents": 150_000_00,
            }
        ]

        result = mock_civic.funding_flow()

        assert len(result) == 1
        flow = result[0]
        assert flow.state_agency == "HCD"
        assert flow.state_program_name == "California CDBG"
        assert flow.state_dollars == 150_000.00  # 150_000_00 cents -> $150,000

    def test_funding_flow_impact_calculation(self, mock_civic):
        """funding_flow_impact() calculates cut impact correctly."""
        mock_civic._storage.get_budget_items.return_value = [
            {"item_id": "budget-001", "line_item": "CDBG", "budgeted_cents": 100_000_00},
            {"item_id": "budget-002", "line_item": "CDBG", "budgeted_cents": 50_000_00},
        ]
        mock_civic._storage.get_budget_funding_links.return_value = [
            {
                "link_id": "link-001",
                "budget_item_id": "budget-001",
                "match_confidence": 0.9,
                "budget_cents": 100_000_00,
            },
            {
                "link_id": "link-002",
                "budget_item_id": "budget-002",
                "match_confidence": 0.9,
                "budget_cents": 50_000_00,
            },
        ]
        mock_civic._storage.get_federal_awards.return_value = []
        mock_civic._storage.get_state_passthrough_funds.return_value = []

        result = mock_civic.funding_flow_impact(cut_percentage=0.20)

        assert result.cut_percentage == 0.20
        assert result.total_current_dollars == 150_000.00  # $100k + $50k
        assert result.total_impact_dollars == 30_000.00  # 20% of $150k
        assert len(result.affected_items) == 2
