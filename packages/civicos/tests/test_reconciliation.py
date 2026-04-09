"""Tests for civicos._internal.meetings.reconciliation — pure logic tests.

Focuses on serialization round-trips, normalization, edge case detection,
and aggregate computation. Does NOT test the full reconciler (which needs
embeddings/storage) — only the self-contained logic.
"""

from civicos._internal.meetings.reconciliation import (
    AgendaItemTag,
    ReconciliationLink,
    ReconciliationResult,
    BatchReconciliationResult,
    Anomaly,
    EdgeCaseHandler,
    normalize_agenda_item,
)


class TestAgendaItemTag:
    """Serialization round-trip and field preservation."""

    def test_to_metadata_str_format(self):
        tag = AgendaItemTag(
            item_number="5.a",
            confidence=0.85,
            tag_type="primary",
            detection_source="structural",
        )
        result = tag.to_metadata_str()
        assert result == "5.a:0.85:primary:structural"

    def test_from_metadata_str_round_trip(self):
        original = AgendaItemTag(
            item_number="5.a",
            confidence=0.85,
            tag_type="primary",
            detection_source="structural",
        )
        serialized = original.to_metadata_str()
        restored = AgendaItemTag.from_metadata_str(serialized)
        assert restored.item_number == "5.a"
        assert abs(restored.confidence - 0.85) < 0.01
        assert restored.tag_type == "primary"
        assert restored.detection_source == "structural"

    def test_from_metadata_str_partial(self):
        """Handles truncated metadata strings gracefully."""
        tag = AgendaItemTag.from_metadata_str("5.a")
        assert tag.item_number == "5.a"
        assert tag.confidence == 0.5  # default
        assert tag.tag_type == "unknown"  # default
        assert tag.detection_source == "stored"  # default

    def test_from_metadata_str_two_parts(self):
        tag = AgendaItemTag.from_metadata_str("5.a:0.90")
        assert tag.item_number == "5.a"
        assert abs(tag.confidence - 0.90) < 0.01
        assert tag.tag_type == "unknown"

    def test_confidence_precision(self):
        """Confidence is formatted to 2 decimal places."""
        tag = AgendaItemTag("3.b", 0.12345, "secondary", "semantic")
        assert "0.12" in tag.to_metadata_str()


class TestNormalizeAgendaItem:
    """Tests for agenda item normalization."""

    def test_lowercase(self):
        assert normalize_agenda_item("5A") == "5.a"

    def test_dash_to_period(self):
        assert normalize_agenda_item("5-a") == "5.a"

    def test_already_normalized(self):
        assert normalize_agenda_item("5.a") == "5.a"

    def test_number_letter_concatenated(self):
        """'5a' should become '5.a'."""
        assert normalize_agenda_item("5a") == "5.a"

    def test_empty_string(self):
        assert normalize_agenda_item("") == ""

    def test_number_only(self):
        assert normalize_agenda_item("5") == "5"

    def test_multi_digit(self):
        assert normalize_agenda_item("12b") == "12.b"

    def test_uppercase_letter(self):
        assert normalize_agenda_item("3B") == "3.b"


class TestEdgeCaseDetector:
    """Tests for EdgeCaseHandler.detect_edge_case."""

    def test_out_of_order(self):
        result = EdgeCaseHandler.detect_edge_case("Let's take item 5 before the next one")
        assert result is not None
        assert result["type"] == "out_of_order"
        assert result["item"] == "5"

    def test_revisit(self):
        result = EdgeCaseHandler.detect_edge_case("Going back to item 3a now")
        assert result is not None
        assert result["type"] == "revisit"
        assert result["item"] == "3.a"

    def test_consent_calendar(self):
        result = EdgeCaseHandler.detect_edge_case("Approve the consent calendar")
        assert result is not None
        assert result["type"] == "consent_calendar"

    def test_pulled_item(self):
        result = EdgeCaseHandler.detect_edge_case("Councilmember Smith pulled item 4b")
        assert result is not None
        assert result["type"] == "pulled_item"
        assert result["item"] == "4.b"

    def test_no_edge_case(self):
        result = EdgeCaseHandler.detect_edge_case("The city manager presented the budget report")
        assert result is None

    def test_case_insensitive(self):
        result = EdgeCaseHandler.detect_edge_case("LET'S TAKE ITEM 7 FIRST")
        assert result is not None
        assert result["type"] == "out_of_order"


class TestReconciliationLinkToDict:
    """Tests for ReconciliationLink serialization."""

    def test_to_dict_fields(self):
        link = ReconciliationLink(
            decision_id="d-123",
            chunk_ids=["c-1", "c-2"],
            confidence=0.85,
            link_type="consensus",
            structural_score=0.9,
            semantic_score=0.8,
            agreement_bonus=0.2,
            is_consent_calendar=True,
            meeting_date="2024-10-06",
            agenda_item="5.a",
            decision_title="Housing Policy",
        )
        d = link.to_dict()
        assert d["decision_id"] == "d-123"
        assert d["chunk_ids"] == ["c-1", "c-2"]
        assert d["confidence"] == 0.85
        assert d["link_type"] == "consensus"
        assert d["structural_score"] == 0.9
        assert d["semantic_score"] == 0.8
        assert d["is_consent_calendar"] is True
        assert d["decision_title"] == "Housing Policy"


class TestBatchReconciliationAggregates:
    """Tests for compute_aggregates on BatchReconciliationResult."""

    def test_empty_results(self):
        report = BatchReconciliationResult(jurisdiction_id="city-test")
        report.compute_aggregates()
        assert report.total_decisions == 0
        assert report.total_links == 0

    def test_single_meeting_aggregates(self):
        link_high = ReconciliationLink(
            decision_id="d-1", chunk_ids=["c-1"], confidence=0.9,
            link_type="consensus",
        )
        link_low = ReconciliationLink(
            decision_id="d-2", chunk_ids=["c-2", "c-3"], confidence=0.4,
            link_type="structural_only",
        )
        result = ReconciliationResult(
            meeting_date="2024-10-06",
            meeting_id="m-1",
            links=[link_high, link_low],
            consensus_links=1,
            structural_only_links=1,
            decisions_count=3,
            chunks_count=5,
            coverage_decisions=0.67,
        )
        report = BatchReconciliationResult(
            jurisdiction_id="city-test",
            meeting_results=[result],
        )
        report.compute_aggregates()

        assert report.total_decisions == 3
        assert report.total_chunks == 5
        assert report.total_links == 2
        assert report.total_consensus == 1
        assert report.total_structural_only == 1
        assert report.high_confidence_links == 1  # 0.9 >= 0.8
        assert report.low_confidence_links == 1   # 0.4 < 0.5
        assert report.meetings_partial == 1  # 0.67 coverage (> 0, < 0.9)

    def test_fully_reconciled_meeting(self):
        link = ReconciliationLink(
            decision_id="d-1", chunk_ids=["c-1"], confidence=0.95,
            link_type="consensus",
        )
        result = ReconciliationResult(
            meeting_date="2024-10-06",
            meeting_id="m-1",
            links=[link],
            decisions_count=1,
            chunks_count=1,
            coverage_decisions=0.95,
        )
        report = BatchReconciliationResult(
            jurisdiction_id="city-test",
            meeting_results=[result],
        )
        report.compute_aggregates()
        assert report.meetings_fully_reconciled == 1
        assert report.meetings_partial == 0
        assert report.overall_decision_coverage == 1.0  # 1 linked / 1 total

    def test_failed_meeting(self):
        result = ReconciliationResult(
            meeting_date="2024-10-06",
            meeting_id="m-1",
            links=[],
            decisions_count=5,
            chunks_count=10,
            coverage_decisions=0.0,
        )
        report = BatchReconciliationResult(
            jurisdiction_id="city-test",
            meeting_results=[result],
        )
        report.compute_aggregates()
        assert report.meetings_failed == 1
        assert report.overall_decision_coverage == 0.0


class TestAnomalyToDict:
    """Tests for Anomaly serialization."""

    def test_to_dict_includes_all_fields(self):
        a = Anomaly(
            anomaly_type="signal_disagreement",
            description="Structural says 5.a, semantic says 7.b",
            decision_id="d-123",
            chunk_ids=["c-1"],
            severity="warning",
            structural_item="5.a",
            semantic_item="7.b",
        )
        d = a.to_dict()
        assert d["anomaly_type"] == "signal_disagreement"
        assert d["severity"] == "warning"
        assert d["structural_item"] == "5.a"
        assert d["semantic_item"] == "7.b"
        assert d["chunk_ids"] == ["c-1"]
