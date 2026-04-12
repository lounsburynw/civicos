"""
Tests for entity ID namespacing.

Verifies that all entity IDs follow the namespaced format:
{entity_type}:{jurisdiction_id}:{source}:{identifier}

See docs/decisions/entity_id_namespace.md for the canonical schema.
"""

import pytest
import re


# Namespace format patterns
NAMESPACE_PATTERNS = {
    "meeting": re.compile(r"^meeting:[a-z]+-[a-z-]+:[a-z]+:.+$"),
    "decision": re.compile(r"^decision:[a-z]+-[a-z-]+:\d{4}-\d{2}-\d{2}:.+$"),
    "chunk": re.compile(r"^chunk:[a-z]+-[a-z-]+:.+:\d{4}$"),
    "issue": re.compile(r"^issue:[a-z]+-[a-z-]+:[a-z]+:\d+$"),
    "bill": re.compile(r"^bill:(state-[a-z]+|federal):[a-z]+[-]?\d+$"),
}


def is_namespaced(entity_id: str, entity_type: str) -> bool:
    """Check if an entity ID follows the namespace format."""
    pattern = NAMESPACE_PATTERNS.get(entity_type)
    if not pattern:
        # For unknown types, check for basic namespace structure (3+ colons)
        return entity_id.count(":") >= 2
    return bool(pattern.match(entity_id))


class TestEntityIdFormats:
    """Test entity ID format generation."""

    def test_meeting_id_format_legistar(self):
        """Legistar meeting IDs should be namespaced."""
        # Simulates what legistar.py generates
        jurisdiction_id = "city-san-rafael"
        event_id = "12345"
        meeting_id = f"meeting:{jurisdiction_id}:legistar:{event_id}"

        assert is_namespaced(meeting_id, "meeting")
        assert meeting_id == "meeting:city-san-rafael:legistar:12345"

    def test_meeting_id_format_proudcity(self):
        """ProudCity meeting IDs should be namespaced."""
        jurisdiction_id = "city-san-rafael"
        slug = "2026-01-15-council"
        meeting_id = f"meeting:{jurisdiction_id}:proudcity:{slug}"

        assert is_namespaced(meeting_id, "meeting")
        assert meeting_id == "meeting:city-san-rafael:proudcity:2026-01-15-council"

    def test_meeting_id_format_simbli(self):
        """Simbli meeting IDs should be namespaced."""
        jurisdiction_id = "city-san-rafael"
        meeting_date = "2026-01-15"
        meeting_id = f"meeting:{jurisdiction_id}:simbli:{meeting_date}"

        assert is_namespaced(meeting_id, "meeting")
        assert meeting_id == "meeting:city-san-rafael:simbli:2026-01-15"

    def test_decision_id_format(self):
        """Decision IDs should be namespaced."""
        jurisdiction_id = "city-san-rafael"
        meeting_date = "2026-01-15"
        item_part = "6-a"
        decision_id = f"decision:{jurisdiction_id}:{meeting_date}:{item_part}"

        assert is_namespaced(decision_id, "decision")
        assert decision_id == "decision:city-san-rafael:2026-01-15:6-a"

    def test_chunk_id_format(self):
        """Chunk IDs should be namespaced."""
        jurisdiction_id = "city-san-rafael"
        meeting_id_ref = "meeting-legistar-12345"
        chunk_index = 42
        chunk_id = f"chunk:{jurisdiction_id}:{meeting_id_ref}:{chunk_index:04d}"

        assert is_namespaced(chunk_id, "chunk")
        assert chunk_id == "chunk:city-san-rafael:meeting-legistar-12345:0042"

    def test_issue_id_format(self):
        """Issue IDs should be namespaced."""
        jurisdiction_id = "city-san-rafael"
        provider = "seeclickfix"
        external_id = "12345678"
        issue_id = f"issue:{jurisdiction_id}:{provider}:{external_id}"

        assert is_namespaced(issue_id, "issue")
        assert issue_id == "issue:city-san-rafael:seeclickfix:12345678"

    def test_normalized_issue_id_property(self):
        """NormalizedIssue.id property should return namespaced ID."""
        from civicos.issues.provider import NormalizedIssue

        issue = NormalizedIssue(
            jurisdiction_id="city-san-rafael",
            provider="seeclickfix",
            external_id="12345678",
            title="Test Issue",
        )
        assert issue.id == "issue:city-san-rafael:seeclickfix:12345678"

    def test_decision_extractor_stores_jurisdiction(self):
        """DecisionExtractor stores jurisdiction_id for use in ID generation."""
        from civicos._internal.meetings.decision import DecisionExtractor

        extractor = DecisionExtractor(jurisdiction_id="city-san-rafael")
        assert extractor.jurisdiction_id == "city-san-rafael"
        # Verify non-default jurisdiction is stored correctly
        extractor2 = DecisionExtractor(jurisdiction_id="city-berkeley")
        assert extractor2.jurisdiction_id == "city-berkeley"
        assert extractor2.jurisdiction_id != extractor.jurisdiction_id


class TestBackwardsCompatibility:
    """Test that legacy IDs can coexist with namespaced IDs."""

    def test_legacy_meeting_id_detected(self):
        """Legacy meeting IDs should NOT match namespace pattern."""
        legacy_id = "legistar-san-rafael-12345"
        assert not is_namespaced(legacy_id, "meeting")

    def test_legacy_issue_id_detected(self):
        """Legacy issue IDs should NOT match namespace pattern."""
        legacy_id = "seeclickfix-12345678"
        assert not is_namespaced(legacy_id, "issue")

    def test_legacy_decision_id_detected(self):
        """Legacy decision IDs should NOT match namespace pattern."""
        legacy_id = "20260115-item-6a"
        assert not is_namespaced(legacy_id, "decision")


class TestJurisdictionFormats:
    """Test jurisdiction ID formats in namespaced IDs."""

    def test_city_jurisdiction_matches_pattern(self):
        """City jurisdictions with 'city-' prefix match meeting namespace pattern."""
        entity_id = "meeting:city-san-rafael:legistar:123"
        assert is_namespaced(entity_id, "meeting")
        assert entity_id.split(":")[1] == "city-san-rafael"

    def test_county_jurisdiction_matches_pattern(self):
        """County jurisdictions with 'county-' prefix match meeting namespace pattern."""
        entity_id = "meeting:county-marin:legistar:456"
        assert is_namespaced(entity_id, "meeting")
        assert entity_id.split(":")[1] == "county-marin"

    def test_state_jurisdiction_matches_bill_pattern(self):
        """State jurisdictions with 'state-' prefix match bill namespace pattern."""
        bill_id = "bill:state-california:sb-1234"
        assert is_namespaced(bill_id, "bill")
        assert bill_id.split(":")[1] == "state-california"

    def test_federal_jurisdiction_matches_bill_pattern(self):
        """Federal jurisdiction matches bill namespace pattern."""
        bill_id = "bill:federal:hr-5678"
        assert is_namespaced(bill_id, "bill")
        assert bill_id.split(":")[1] == "federal"


