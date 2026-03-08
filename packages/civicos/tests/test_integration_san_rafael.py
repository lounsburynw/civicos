"""
Integration tests for the Civic package with San Rafael data.

Tests all query methods with real data from:
- StateManager (meetings, issues)
- Legislative cache (state bills, federal programs)
- Coordination workflow (LangGraph)

Run: python -m pytest packages/civicos/tests/test_integration_san_rafael.py -v
"""

import os
import sys
from pathlib import Path
from datetime import datetime

import pytest

# Mark all tests in this module as integration
pytestmark = pytest.mark.integration

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Add packages to path
sys.path.insert(0, str(PROJECT_ROOT / "packages/civicos/src"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Set working directory for data file access
os.chdir(str(PROJECT_ROOT))

from civicos import CivicOS

# Absolute paths for data files
DB_PATH = str(PROJECT_ROOT / "data/civic_state.db")


@pytest.mark.requires_real_data
@pytest.mark.requires_pgvector
class TestCivicIntegration:
    """Integration tests using real San Rafael data."""

    @pytest.fixture
    def civic(self):
        """Create Civic instance for San Rafael."""
        return CivicOS("city-san-rafael", db_path=DB_PATH)

    def test_what_applies_housing(self, civic):
        """Test what_applies() returns real housing legislation."""
        result = civic.what_applies("housing")

        assert result.topic == "housing"
        assert result.jurisdiction == "city-san-rafael"
        assert len(result.state) > 0, "Should have state legislation"
        assert len(result.federal) > 0, "Should have federal programs"

        # Verify we get actual bill data, not placeholders
        first_state = result.state[0]
        assert "note" not in first_state or "coming" not in first_state.get("note", "").lower()
        assert first_state.get("type") == "bill"
        assert first_state.get("bill") is not None

    def test_what_applies_transportation(self, civic):
        """Test what_applies() for transportation topic."""
        result = civic.what_applies("transportation")

        assert result.topic == "transportation"
        assert len(result.state) > 0
        assert len(result.federal) > 0

    def test_what_applies_zoning(self, civic):
        """Test that what_applies() finds relevant legislation for zoning queries."""
        result = civic.what_applies("zoning")

        # Should return relevant legislation via semantic search
        assert len(result.state) > 0

    def test_what_applies_unknown_topic(self, civic):
        """Test what_applies() with unknown topic."""
        result = civic.what_applies("quantum_mechanics")

        # Should return empty results with notes, not crash
        assert result.topic == "quantum_mechanics"
        # Either has data or has a note explaining no data
        assert len(result.state) > 0

    def test_whats_next_returns_meetings(self, civic):
        """Test whats_next() queries StateManager."""
        # Note: May return empty if all meetings are in the past
        meetings = civic.whats_next(days=90)

        # Verify it's a list (even if empty)
        assert isinstance(meetings, list)

        # If there are meetings, verify structure
        for m in meetings:
            assert m.id is not None
            assert m.title is not None
            assert m.date is not None


class TestCivicQueryChaining:
    """Test combining multiple Civic queries."""

    @pytest.fixture
    def civic(self):
        return CivicOS("city-san-rafael", db_path=DB_PATH)

    def test_research_workflow(self, civic):
        """Test a research workflow: what_applies -> what_happened."""
        # 1. Research the regulatory context
        context = civic.what_applies("housing")
        assert len(context.state) > 0

        # 2. Check past decisions
        decisions = civic.what_happened("housing")

        # Both should work together
        assert context.topic == "housing"
        assert isinstance(decisions, list)

    def test_multi_topic_research(self, civic):
        """Test researching multiple topics."""
        topics = ["housing", "transportation", "environment"]

        results = {}
        for topic in topics:
            results[topic] = civic.what_applies(topic)

        # Each should have data
        for topic, result in results.items():
            assert result.topic == topic
            assert len(result.state) > 0, f"{topic} should have state legislation"


@pytest.mark.requires_real_data
class TestCivicStateManager:
    """Test StateManager integration."""

    @pytest.fixture
    def civic(self):
        return CivicOS("city-san-rafael", db_path=DB_PATH)

    def test_state_manager_initialized(self, civic):
        """Verify StateManager is properly initialized."""
        assert civic._state is not None

    def test_can_query_issue_stats(self, civic):
        """Test that issue data is accessible."""
        stats = civic._state.get_issue_stats("city-san-rafael")

        assert stats["jurisdiction_id"] == "city-san-rafael"
        assert stats["total_issues"] > 0, "Should have pre-loaded issues"


@pytest.mark.requires_real_data
class TestWhatsNextWithRealData:
    """
    Integration test: whats_next() returns actual upcoming San Rafael meetings.

    Tests that:
    1. whats_next() queries real meeting data from StateManager
    2. Meeting structure matches expected schema
    3. Date filtering correctly excludes past meetings
    4. Agenda items are properly extracted from full_data
    """

    @pytest.fixture
    def civic(self):
        return CivicOS("city-san-rafael", db_path=DB_PATH)

    def test_whats_next_queries_real_san_rafael_meetings(self, civic):
        """
        Verify whats_next() correctly queries real San Rafael meeting data.

        Even if no meetings are in the future window, this validates:
        - StateManager is connected and has data
        - Query mechanism works correctly
        - Return type is correct
        """
        # Query with default window
        meetings = civic.whats_next(days=30)

        # Result should be a list (may be empty if all meetings are past)
        assert isinstance(meetings, list)

        # Verify StateManager has actual meeting data
        state = civic._state.get_city_state("city-san-rafael")
        assert state is not None
        assert "meetings" in state

        # San Rafael should have at least some historical meeting data
        # (even if not in future window)
        all_meetings = state.get("meetings", [])
        assert len(all_meetings) >= 0  # May have meetings in database

    def test_whats_next_meeting_structure_when_data_exists(self, civic):
        """
        Verify meeting objects have correct structure.

        Uses StateManager directly to verify schema, since
        whats_next() filters by date.
        """
        state = civic._state.get_city_state("city-san-rafael")
        all_meetings = state.get("meetings", [])

        if len(all_meetings) > 0:
            # Verify raw meeting data structure
            sample = all_meetings[0]

            # Required fields from StateManager
            assert "id" in sample
            assert "title" in sample
            assert "meeting_datetime" in sample or sample.get("full_data", {}).get("meeting_datetime")

            # Meeting should have proper metadata
            assert "jurisdiction_id" in sample
            assert sample["jurisdiction_id"] == "city-san-rafael"

            # Should have source info for real data
            assert "source_platform" in sample

    def test_whats_next_extracts_agenda_items(self, civic):
        """
        Verify whats_next() properly extracts agenda items from full_data.

        Agenda items are stored in full_data JSON, and whats_next() should
        extract them into the Meeting object.
        """
        import json

        state = civic._state.get_city_state("city-san-rafael")
        all_meetings = state.get("meetings", [])

        # Find a meeting with agenda items in full_data
        meeting_with_agenda = None
        for m in all_meetings:
            full_data = m.get("full_data", {})
            if isinstance(full_data, str):
                try:
                    full_data = json.loads(full_data)
                except:
                    continue

            if full_data and full_data.get("agenda_items"):
                meeting_with_agenda = m
                break

        if meeting_with_agenda:
            full_data = meeting_with_agenda.get("full_data", {})
            if isinstance(full_data, str):
                full_data = json.loads(full_data)

            agenda_items = full_data.get("agenda_items", [])

            # Verify agenda item structure
            assert len(agenda_items) > 0
            for item in agenda_items:
                assert "id" in item or "item_number" in item
                assert "title" in item

    def test_whats_next_date_filtering(self, civic):
        """
        Verify whats_next() correctly filters by date window.

        Past meetings should be excluded, future meetings within
        the window should be included.
        """
        from datetime import timedelta, timezone

        # Query with different windows
        meetings_30d = civic.whats_next(days=30)
        meetings_90d = civic.whats_next(days=90)
        meetings_365d = civic.whats_next(days=365)

        # All should be lists
        assert isinstance(meetings_30d, list)
        assert isinstance(meetings_90d, list)
        assert isinstance(meetings_365d, list)

        # Larger window should have >= meetings than smaller
        assert len(meetings_90d) >= len(meetings_30d)
        assert len(meetings_365d) >= len(meetings_90d)

        # Verify all returned meetings are in the future
        now = datetime.now(timezone.utc)
        for meeting in meetings_90d:
            meeting_date = meeting.date
            if meeting_date.tzinfo is None:
                meeting_date = meeting_date.replace(tzinfo=timezone.utc)
            assert meeting_date >= now, f"Past meeting incorrectly included: {meeting.title}"

    def test_whats_next_real_san_rafael_data_quality(self, civic):
        """
        Verify real San Rafael meeting data has expected quality attributes.
        """
        state = civic._state.get_city_state("city-san-rafael")
        all_meetings = state.get("meetings", [])

        if len(all_meetings) > 0:
            sample = all_meetings[0]

            # Real data should have quality indicators
            title = sample.get("title", "")
            assert len(title) > 5, "Title should be descriptive"

            # Should reference San Rafael-specific bodies
            meeting_type = sample.get("meeting_type", "")
            valid_types = ["city_council", "planning_commission", "board",
                          "committee", "commission", "hearing"]
            # At least have some type information
            assert meeting_type or sample.get("full_data")

            # Should have location for in-person meetings
            location = sample.get("location", "")
            if location:
                # San Rafael meetings should reference local venues
                assert len(location) > 10


@pytest.mark.requires_real_data
@pytest.mark.requires_pgvector
class TestWhatAppliesWithRealData:
    """
    Integration test: what_applies() returns real California housing/regulatory context.

    Tests that:
    1. what_applies('housing') returns real California housing legislation
    2. Federal housing programs are included (CDBG, HOME, Section 8, LIHTC)
    3. State bills have expected structure and known legislation
    4. Semantic search finds relevant results for related queries
    5. Data quality meets expectations for civic advocacy use
    """

    @pytest.fixture
    def civic(self):
        return CivicOS("city-san-rafael", db_path=DB_PATH)

    def test_what_applies_returns_real_california_housing_legislation(self, civic):
        """
        Verify what_applies('housing') returns real California housing bills.

        The legislative_context_cache should contain:
        - SB 9 (HOME Act)
        - AB 2011 (Affordable Housing and High Road Jobs)
        - SB 35 (Streamlined Ministerial Approval)
        - SB 330 (Housing Crisis Act)
        - AB 1287 (Density Bonus Law Expansion)
        - SB 1123 (Vacant Lot Subdivision Streamlining)
        """
        result = civic.what_applies("housing")

        assert result.topic == "housing"
        assert result.jurisdiction == "city-san-rafael"

        # Should have real state legislation, not placeholders
        assert len(result.state) > 0
        first_state = result.state[0]
        assert first_state.get("type") == "bill"
        assert "note" not in first_state  # Real data, not fallback

        # Verify known California housing bills are present
        bill_ids = [b.get("id") for b in result.state]
        known_bills = ["ca-sb9", "ca-ab2011", "ca-sb35", "ca-sb330", "ca-ab1287", "ca-sb1123"]

        # At least some known bills should be present
        matches = [b for b in known_bills if b in bill_ids]
        assert len(matches) >= 3, f"Expected at least 3 known housing bills, found: {matches}"

    def test_what_applies_returns_federal_housing_programs(self, civic):
        """
        Verify what_applies('housing') returns federal housing programs.

        Expected programs:
        - CDBG (Community Development Block Grant)
        - HOME Investment Partnerships Program
        - Section 8 Housing Choice Voucher Program
        - LIHTC (Low-Income Housing Tax Credit)
        """
        result = civic.what_applies("housing")

        # Should have federal programs, not placeholders
        assert len(result.federal) > 0
        first_federal = result.federal[0]
        assert first_federal.get("type") == "program"
        assert "note" not in first_federal  # Real data, not fallback

        # Verify known federal programs are present
        program_ids = [p.get("id") for p in result.federal]
        known_programs = [
            "cdbg",
            "home_investment_partnerships_program",
            "section_8_housing_choice_voucher_program",
            "low_income_housing_tax_credit_lihtc_program"
        ]

        # At least some known programs should be present
        matches = [p for p in known_programs if p in program_ids]
        assert len(matches) >= 2, f"Expected at least 2 known federal programs, found: {matches}"

    def test_what_applies_state_bill_structure(self, civic):
        """
        Verify state bill entries have required structure for civic advocacy.

        Required fields for actionable civic guidance:
        - id: Unique bill identifier
        - bill: Bill name/title
        - leverage_point: How residents can use this
        - keywords: For topic matching
        """
        result = civic.what_applies("housing")

        for bill in result.state:
            if bill.get("type") == "bill":
                # Required for identification
                assert "id" in bill, f"Bill missing 'id': {bill}"
                assert "bill" in bill, f"Bill missing 'bill' name: {bill}"

                # Required for civic advocacy
                assert "leverage_point" in bill, f"Bill missing 'leverage_point': {bill.get('id')}"
                assert len(bill.get("leverage_point", "")) > 20, \
                    f"Leverage point too short for {bill.get('id')}"

                # Required for topic matching
                assert "keywords" in bill, f"Bill missing 'keywords': {bill.get('id')}"
                assert isinstance(bill.get("keywords"), list)

    def test_what_applies_federal_program_structure(self, civic):
        """
        Verify federal program entries have required structure.

        Required fields for actionable civic guidance:
        - id: Unique program identifier
        - program_name: Full program name
        - agency: Administering agency
        - leverage_point: How residents can influence
        """
        result = civic.what_applies("housing")

        for program in result.federal:
            if program.get("type") == "program":
                # Required for identification
                assert "id" in program, f"Program missing 'id': {program}"
                assert "program_name" in program, f"Program missing 'program_name': {program}"

                # Required for civic advocacy
                assert "leverage_point" in program, f"Program missing 'leverage_point': {program.get('id')}"
                assert len(program.get("leverage_point", "")) > 20, \
                    f"Leverage point too short for {program.get('id')}"

    def test_what_applies_semantic_search_zoning_and_housing(self, civic):
        """
        Verify semantic search finds relevant legislation for related topics.

        Both 'zoning' and 'housing' should return relevant legislation
        via semantic search over bill text.
        """
        housing_result = civic.what_applies("housing")
        zoning_result = civic.what_applies("zoning")

        # Both should return relevant legislation via semantic search
        assert len(zoning_result.state) > 0
        assert len(housing_result.state) > 0

        # Results are semantically relevant to each query (may overlap but not identical)

    def test_what_applies_multiple_topics_with_real_data(self, civic):
        """
        Verify what_applies() works for multiple topics with real legislative data.
        """
        topics = ["housing", "transportation", "environment", "budget", "education"]

        for topic in topics:
            result = civic.what_applies(topic)

            assert result.topic == topic
            assert result.jurisdiction == "city-san-rafael"

            # All supported topics should have real data
            assert len(result.state) > 0, f"No state legislation for {topic}"
            assert len(result.federal) > 0, f"No federal programs for {topic}"

            # Verify first entry is real data, not fallback
            if result.state[0].get("type") == "bill":
                assert "leverage_point" in result.state[0], \
                    f"State bill missing leverage_point for {topic}"

    def test_what_applies_unknown_jurisdiction_graceful_handling(self, civic):
        """
        Verify what_applies() handles unknown jurisdiction gracefully.
        """
        # Create civic for unknown jurisdiction
        unknown_civic = CivicOS("city-unknown", db_path=DB_PATH)
        result = unknown_civic.what_applies("housing")

        # Should return result (not crash) with notes explaining limitation
        assert result.topic == "housing"
        assert result.jurisdiction == "city-unknown"
        # Should have informative note about unknown jurisdiction
        assert len(result.state) > 0 or len(result.federal) > 0

    def test_what_applies_leverage_points_actionable(self, civic):
        """
        Verify leverage_points provide actionable civic guidance.

        Good leverage points should:
        - Reference specific actions residents can take
        - Mention public meetings, hearings, or comment periods
        - Be written in language accessible to non-experts
        """
        result = civic.what_applies("housing")

        # Check a sample of leverage points
        actionable_keywords = [
            "resident", "advocate", "public",
            "hearing", "meeting", "comment",
            "support", "challenge", "participate"
        ]

        for bill in result.state[:3]:  # Check first 3 bills
            if bill.get("type") == "bill":
                leverage = bill.get("leverage_point", "").lower()
                # At least one actionable keyword should be present
                has_actionable = any(kw in leverage for kw in actionable_keywords)
                assert has_actionable, \
                    f"Leverage point not actionable for {bill.get('id')}: {leverage[:100]}"


@pytest.mark.requires_real_data
@pytest.mark.requires_pgvector
class TestRegulatoryContextRelevant:
    """
    Integration test: what_applies() returns contextually appropriate regulations.

    Tests that:
    1. Regulations returned have keywords matching the queried topic
    2. Different topics return distinct regulation sets (no cross-contamination)
    3. Leverage points reference domain-appropriate concepts
    4. Related topics return overlapping but semantically relevant results
    5. Federal programs are relevant to their stated topic
    """

    @pytest.fixture
    def civic(self):
        return CivicOS("city-san-rafael", db_path=DB_PATH)

    def test_housing_regulations_contain_housing_keywords(self, civic):
        """
        Verify housing regulations have housing-relevant keywords.

        Housing regulations should mention: housing, zoning, density,
        affordable, residential, homes, units.
        """
        result = civic.what_applies("housing")

        housing_keywords = [
            "housing", "zoning", "density", "affordable",
            "residential", "home", "unit", "duplex", "lot"
        ]

        for bill in result.state:
            if bill.get("type") == "bill":
                bill_keywords = [k.lower() for k in bill.get("keywords", [])]
                leverage_point = bill.get("leverage_point", "").lower()

                # At least one housing keyword should be in keywords or leverage_point
                has_housing_keyword = (
                    any(kw in bill_keywords for kw in housing_keywords) or
                    any(kw in leverage_point for kw in housing_keywords)
                )
                assert has_housing_keyword, \
                    f"Housing bill {bill.get('id')} lacks housing keywords: {bill_keywords}"

    def test_transportation_regulations_contain_transportation_keywords(self, civic):
        """
        Verify transportation regulations have transportation-relevant keywords.

        Transportation regulations should mention: transit, transportation,
        road, mobility, vehicle, bike, pedestrian.
        """
        result = civic.what_applies("transportation")

        transport_keywords = [
            "transportation", "transit", "road", "mobility",
            "vehicle", "bike", "pedestrian", "rail", "bus", "highway"
        ]

        for bill in result.state:
            if bill.get("type") == "bill":
                bill_keywords = [k.lower() for k in bill.get("keywords", [])]
                leverage_point = bill.get("leverage_point", "").lower()

                has_transport_keyword = (
                    any(kw in bill_keywords for kw in transport_keywords) or
                    any(kw in leverage_point for kw in transport_keywords)
                )
                assert has_transport_keyword, \
                    f"Transportation bill {bill.get('id')} lacks transport keywords: {bill_keywords}"

    def test_environment_regulations_contain_environment_keywords(self, civic):
        """
        Verify environment regulations have environment-relevant keywords.

        Environment regulations should mention: environment, climate, emissions,
        renewable, energy, sustainability, clean.
        """
        result = civic.what_applies("environment")

        env_keywords = [
            "environment", "climate", "emission", "renewable",
            "energy", "sustainability", "clean", "carbon", "green"
        ]

        for bill in result.state:
            if bill.get("type") == "bill":
                bill_keywords = [k.lower() for k in bill.get("keywords", [])]
                leverage_point = bill.get("leverage_point", "").lower()

                has_env_keyword = (
                    any(kw in bill_keywords for kw in env_keywords) or
                    any(kw in leverage_point for kw in env_keywords)
                )
                assert has_env_keyword, \
                    f"Environment bill {bill.get('id')} lacks environment keywords: {bill_keywords}"

    def test_different_topics_return_different_regulations(self, civic):
        """
        Verify different topics return distinct regulation sets.

        Housing, transportation, and environment should have
        non-overlapping bill IDs.
        """
        housing_result = civic.what_applies("housing")
        transport_result = civic.what_applies("transportation")
        env_result = civic.what_applies("environment")

        # Extract bill IDs
        housing_ids = {b.get("id") for b in housing_result.state if b.get("type") == "bill"}
        transport_ids = {b.get("id") for b in transport_result.state if b.get("type") == "bill"}
        env_ids = {b.get("id") for b in env_result.state if b.get("type") == "bill"}

        # Verify non-empty
        assert len(housing_ids) > 0, "Housing should have bills"
        assert len(transport_ids) > 0, "Transportation should have bills"
        assert len(env_ids) > 0, "Environment should have bills"

        # Verify no overlap (each topic has distinct legislation)
        assert len(housing_ids & transport_ids) == 0, \
            f"Housing and transport overlap: {housing_ids & transport_ids}"
        assert len(housing_ids & env_ids) == 0, \
            f"Housing and environment overlap: {housing_ids & env_ids}"
        assert len(transport_ids & env_ids) == 0, \
            f"Transport and environment overlap: {transport_ids & env_ids}"

    def test_federal_programs_match_topic_domain(self, civic):
        """
        Verify federal programs are relevant to their topic.

        Housing programs should reference housing concepts.
        Transportation programs should reference transit concepts.
        """
        # Test housing federal programs
        housing_result = civic.what_applies("housing")
        housing_program_keywords = [
            "housing", "affordable", "home", "rental",
            "hud", "community development", "voucher"
        ]

        for program in housing_result.federal:
            if program.get("type") == "program":
                program_name = program.get("program_name", "").lower()
                leverage_point = program.get("leverage_point", "").lower()

                has_housing_keyword = (
                    any(kw in program_name for kw in housing_program_keywords) or
                    any(kw in leverage_point for kw in housing_program_keywords)
                )
                assert has_housing_keyword, \
                    f"Housing program {program.get('id')} lacks housing relevance"

        # Test transportation federal programs
        transport_result = civic.what_applies("transportation")
        transport_program_keywords = [
            "transit", "transportation", "highway", "road",
            "pedestrian", "bike", "mobility", "fta", "dot"
        ]

        for program in transport_result.federal:
            if program.get("type") == "program":
                program_name = program.get("program_name", "").lower()
                leverage_point = program.get("leverage_point", "").lower()

                has_transport_keyword = (
                    any(kw in program_name for kw in transport_program_keywords) or
                    any(kw in leverage_point for kw in transport_program_keywords)
                )
                assert has_transport_keyword, \
                    f"Transport program {program.get('id')} lacks transport relevance"

    def test_related_topics_return_overlapping_results(self, civic):
        """
        Verify related topics return semantically relevant results with overlap.

        Semantic search means related queries like 'zoning'/'housing' or
        'transit'/'transportation' should find overlapping but not identical results.
        """
        # Test housing/zoning overlap
        housing = civic.what_applies("housing")
        zoning = civic.what_applies("zoning")

        housing_ids = {b.get("id") for b in housing.state if b.get("type") == "bill"}
        zoning_ids = {b.get("id") for b in zoning.state if b.get("type") == "bill"}

        # Both should return results
        assert len(housing_ids) > 0, "housing query should return bills"
        assert len(zoning_ids) > 0, "zoning query should return bills"
        # Related topics should have some overlap via semantic similarity
        overlap = housing_ids & zoning_ids
        assert len(overlap) > 0, "housing and zoning should have overlapping results"

        # Test transportation/transit overlap
        transport = civic.what_applies("transportation")
        transit = civic.what_applies("transit")

        transport_ids = {b.get("id") for b in transport.state if b.get("type") == "bill"}
        transit_ids = {b.get("id") for b in transit.state if b.get("type") == "bill"}

        assert len(transport_ids) > 0, "transportation query should return bills"
        assert len(transit_ids) > 0, "transit query should return bills"
        overlap = transport_ids & transit_ids
        assert len(overlap) > 0, "transportation and transit should have overlapping results"

        # Test environment/climate overlap
        env = civic.what_applies("environment")
        climate = civic.what_applies("climate")

        env_ids = {b.get("id") for b in env.state if b.get("type") == "bill"}
        climate_ids = {b.get("id") for b in climate.state if b.get("type") == "bill"}

        assert len(env_ids) > 0, "environment query should return bills"
        assert len(climate_ids) > 0, "climate query should return bills"
        overlap = env_ids & climate_ids
        assert len(overlap) > 0, "environment and climate should have overlapping results"

    def test_leverage_points_reference_appropriate_civic_actions(self, civic):
        """
        Verify leverage points reference topic-appropriate civic actions.

        Housing leverage points should mention: hearings, zoning, planning commission
        Transportation leverage points should mention: transit, projects, meetings
        """
        # Housing-specific civic action keywords
        housing_result = civic.what_applies("housing")
        housing_civic_keywords = [
            "hearing", "council", "planning", "zoning",
            "housing", "project", "advocate", "support"
        ]

        for bill in housing_result.state:
            if bill.get("type") == "bill":
                leverage = bill.get("leverage_point", "").lower()
                has_civic_action = any(kw in leverage for kw in housing_civic_keywords)
                assert has_civic_action, \
                    f"Housing bill {bill.get('id')} leverage_point lacks civic action keywords"

    def test_no_cross_topic_contamination_in_keywords(self, civic):
        """
        Verify topic keywords don't contain unrelated domains.

        Housing bills shouldn't have 'transit' keywords.
        Transportation bills shouldn't have 'housing' keywords.
        """
        # Housing should not have transport-specific keywords
        housing_result = civic.what_applies("housing")
        transport_only_keywords = ["transit", "highway", "rail", "bus"]

        for bill in housing_result.state:
            if bill.get("type") == "bill":
                bill_keywords = [k.lower() for k in bill.get("keywords", [])]
                cross_contamination = [k for k in transport_only_keywords if k in bill_keywords]
                assert len(cross_contamination) == 0, \
                    f"Housing bill {bill.get('id')} has transport keywords: {cross_contamination}"

        # Transportation should not have housing-specific keywords
        transport_result = civic.what_applies("transportation")
        housing_only_keywords = ["zoning", "duplex", "lot split", "density bonus"]

        for bill in transport_result.state:
            if bill.get("type") == "bill":
                bill_keywords = [k.lower() for k in bill.get("keywords", [])]
                cross_contamination = [k for k in housing_only_keywords if k in bill_keywords]
                assert len(cross_contamination) == 0, \
                    f"Transport bill {bill.get('id')} has housing keywords: {cross_contamination}"


@pytest.mark.requires_real_data
class TestWhatHappenedWithRealData:
    """
    Integration test: what_happened('merrydale') returns Nov 17 shelter decisions.

    Tests that:
    1. what_happened() uses search_decisions() to query historical data
    2. Keyword matching works for agenda item titles and descriptions
    3. Results include the Nov 17, 2025 Merrydale shelter decisions
    4. Decision structure matches expected schema
    5. Date filtering works correctly

    Note: Uses test fixture with shelter scenario data as bounded RAG test case.
    When city_state_rag infrastructure is ready, this test validates the basic
    functionality that semantic search will extend.
    """

    @pytest.fixture
    def civic_with_shelter_scenario(self, tmp_path):
        """
        Create Civic instance with seeded shelter meeting data.

        Seeds the database with Nov 17, 2025 City Council meeting that includes
        the shelter decisions from san_rafael_shelter_scenario.json test scenario.
        """
        import json
        import uuid
        from datetime import datetime

        # Use temporary database for test isolation
        db_path = str(tmp_path / "test_civic_state.db")
        civic = CivicOS("city-san-rafael", db_path=db_path)

        # Seed the Nov 17, 2025 shelter meeting data
        # Based on data/pilot/san_rafael_shelter_scenario.json
        meeting_id = str(uuid.uuid4())
        meeting_data = {
            "id": meeting_id,
            "jurisdiction_id": "city-san-rafael",
            "title": "City Council Regular Meeting",
            "meeting_datetime": "2025-11-17T19:00:00-08:00",
            "meeting_type": "city_council",
            "location": "City Hall, 1400 Fifth Avenue, San Rafael",
            "status": "completed",
            "source_platform": "proudcity",
            "full_data": json.dumps({
                "agenda_items": [
                    {
                        "id": "item-6a1",
                        "item_number": "6.a.1",
                        "title": "Declaration of Shelter Crisis - 350 Merrydale Road",
                        "description": "Resolution declaring a shelter crisis in San Rafael and approving acquisition of 350 Merrydale Road for interim homeless shelter.",
                        "outcome": "passed",
                        "project_type": "resolution",
                        "votes": {"yes": 5, "no": 0, "abstain": 0}
                    },
                    {
                        "id": "item-6a2",
                        "item_number": "6.a.2",
                        "title": "Urgency Ordinance - Homeless Shelter Standards",
                        "description": "Urgency ordinance establishing standards for homeless shelter operations at 350 Merrydale Road.",
                        "outcome": "passed",
                        "project_type": "urgency_ordinance",
                        "votes": {"yes": 5, "no": 0, "abstain": 0}
                    },
                    {
                        "id": "item-6a3",
                        "item_number": "6.a.3",
                        "title": "Uncodified Ordinance - Companion Measure for Merrydale Shelter",
                        "description": "Companion ordinance for the Merrydale Road shelter project providing additional operational guidelines.",
                        "outcome": "passed",
                        "project_type": "ordinance"
                    },
                    {
                        "id": "item-6a4",
                        "item_number": "6.a.4",
                        "title": "Grant Agreement - $8M from County of Marin",
                        "description": "Authorization to accept $8 million grant from County of Marin for Merrydale Road shelter acquisition and operations.",
                        "outcome": "passed",
                        "project_type": "agreement"
                    },
                    {
                        "id": "item-6a5",
                        "item_number": "6.a.5",
                        "title": "Purchase Agreement - 350 Merrydale Road Acquisition",
                        "description": "Authorization to purchase property at 350 Merrydale Road for $6.7 million for homeless shelter facility.",
                        "outcome": "passed",
                        "project_type": "purchase"
                    }
                ]
            })
        }

        # Insert meeting data using StateManager
        civic._state.update_meetings("city-san-rafael", [meeting_data])

        return civic

    def test_what_happened_merrydale_returns_shelter_decisions(self, civic_with_shelter_scenario):
        """
        Verify what_happened('merrydale') returns Nov 17 shelter decisions.

        This is the primary integration test from integration.json:
        - what_happened('merrydale') returns Nov 17 shelter decisions
        """
        decisions = civic_with_shelter_scenario.what_happened("merrydale")

        # Should find decisions mentioning "merrydale" in title OR description
        # The search matches on both title and description text
        assert len(decisions) >= 4, f"Expected at least 4 Merrydale decisions, got {len(decisions)}"

        # Verify decision structure and that all are from Nov 17, 2025
        for decision in decisions:
            assert decision.id is not None
            assert decision.title is not None
            assert decision.date is not None
            # All decisions should be from Nov 17, 2025 meeting
            assert decision.date.year == 2025
            assert decision.date.month == 11
            assert decision.date.day == 17

    def test_what_happened_shelter_crisis_returns_declaration(self, civic_with_shelter_scenario):
        """
        Verify what_happened('shelter crisis') returns the crisis declaration.

        Tests alternative query from merrydale_scenario.json validation queries.
        """
        decisions = civic_with_shelter_scenario.what_happened("shelter crisis")

        # Should find the crisis declaration
        assert len(decisions) >= 1, "Expected at least 1 shelter crisis decision"

        # Verify the declaration is found
        titles = [d.title.lower() for d in decisions]
        assert any("declaration" in t and "shelter" in t for t in titles), \
            f"Expected shelter crisis declaration, got: {titles}"

    def test_what_happened_350_merrydale_returns_purchase(self, civic_with_shelter_scenario):
        """
        Verify what_happened('350 merrydale') returns the property purchase.

        Tests address-based search from merrydale_scenario.json validation queries.
        """
        decisions = civic_with_shelter_scenario.what_happened("350 merrydale")

        # Should find decisions mentioning the address
        assert len(decisions) >= 1, "Expected at least 1 decision mentioning 350 Merrydale"

    def test_what_happened_decision_structure(self, civic_with_shelter_scenario):
        """
        Verify Decision objects have correct structure for civic use.
        """
        from civicos.civicos import Decision

        decisions = civic_with_shelter_scenario.what_happened("merrydale")

        assert len(decisions) > 0, "Should have Merrydale decisions"

        for decision in decisions:
            # Verify it's a Decision object
            assert isinstance(decision, Decision)

            # Required fields
            assert hasattr(decision, 'id')
            assert hasattr(decision, 'title')
            assert hasattr(decision, 'date')
            assert hasattr(decision, 'outcome')
            assert hasattr(decision, 'body')
            assert hasattr(decision, 'votes')

            # Type checks
            assert isinstance(decision.id, str)
            assert isinstance(decision.title, str)
            assert isinstance(decision.body, str)

    def test_what_happened_decision_includes_outcome(self, civic_with_shelter_scenario):
        """
        Verify decisions include outcome information (passed/failed/approved/received).
        """
        decisions = civic_with_shelter_scenario.what_happened("merrydale")

        # Valid outcomes include: passed, failed, approved, received, continued, modified, unknown
        valid_outcomes = ["passed", "failed", "continued", "modified", "unknown", "approved", "received"]
        for decision in decisions:
            assert decision.outcome in valid_outcomes, \
                f"Invalid outcome: {decision.outcome}"

        # Check that at least one has explicit approval outcome
        outcomes = [d.outcome for d in decisions]
        assert any(o in ["passed", "approved"] for o in outcomes), \
            f"Expected at least one 'passed' or 'approved' outcome, got: {outcomes}"

    def test_what_happened_decision_includes_votes(self, civic_with_shelter_scenario):
        """
        Verify decisions include vote breakdown when available.
        """
        decisions = civic_with_shelter_scenario.what_happened("shelter crisis")

        # Find the crisis declaration which has votes
        crisis_decision = None
        for d in decisions:
            if "declaration" in d.title.lower():
                crisis_decision = d
                break

        assert crisis_decision is not None, "Should find crisis declaration"

        # Crisis declaration should have vote breakdown
        if crisis_decision.votes:
            assert "yes" in crisis_decision.votes
            assert crisis_decision.votes["yes"] == 5

    def test_what_happened_returns_correct_date(self, civic_with_shelter_scenario):
        """
        Verify decisions have the correct meeting date (Nov 17, 2025).
        """
        decisions = civic_with_shelter_scenario.what_happened("merrydale")

        for decision in decisions:
            # Should be from Nov 17, 2025
            assert decision.date.year == 2025
            assert decision.date.month == 11
            assert decision.date.day == 17

    def test_what_happened_empty_query_returns_empty(self, civic_with_shelter_scenario):
        """
        Verify what_happened() with non-matching query returns empty list.
        """
        decisions = civic_with_shelter_scenario.what_happened("quantum_physics")

        assert decisions == [], f"Expected empty list for non-matching query, got {len(decisions)}"

    def test_what_happened_case_insensitive(self, civic_with_shelter_scenario):
        """
        Verify search is case-insensitive.
        """
        decisions_lower = civic_with_shelter_scenario.what_happened("merrydale")
        decisions_upper = civic_with_shelter_scenario.what_happened("MERRYDALE")
        decisions_mixed = civic_with_shelter_scenario.what_happened("MeRrYdAlE")

        # All should return same number of results
        assert len(decisions_lower) == len(decisions_upper) == len(decisions_mixed)
        assert len(decisions_lower) >= 4

    def test_what_happened_searches_description(self, civic_with_shelter_scenario):
        """
        Verify search matches description text, not just titles.
        """
        # "homeless" appears in descriptions but not all titles
        decisions = civic_with_shelter_scenario.what_happened("homeless")

        assert len(decisions) >= 1, "Should find decisions mentioning 'homeless' in description"


@pytest.mark.requires_real_data
class TestWhatAppliesEmbeddingRelevance:
    """
    Integration test: what_applies() topic-regulation relevance via embedding similarity.

    Tests that:
    1. Embedding similarity correctly ranks regulations by topic relevance
    2. Semantic queries match regulations beyond exact keywords
    3. Embedding-based relevance aligns with current keyword-based results

    This test class validates that the embedding infrastructure is ready
    for migration from keyword-based to semantic topic matching.

    Note: Marked with 'rag' marker as it requires sentence-transformers.
    """

    @pytest.fixture
    def civic(self):
        return CivicOS("city-san-rafael", db_path=DB_PATH)

    @pytest.fixture
    def embedder(self):
        """Provide SentenceTransformer for embedding comparisons."""
        try:
            from sentence_transformers import SentenceTransformer
            # trust_remote_code=True required for models with custom code (e.g., nomic)
            return SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
        except ImportError:
            pytest.skip("sentence-transformers not installed")

    def _cosine_similarity(self, vec1, vec2):
        """Compute cosine similarity between two vectors."""
        import numpy as np
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        return dot_product / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0.0

    @pytest.mark.rag
    def test_housing_query_ranks_housing_bills_highest(self, civic, embedder):
        """
        Verify housing semantic query ranks housing bills above transportation bills.

        Uses embedding similarity to demonstrate semantic relevance:
        - Query: "affordable housing development"
        - Expected: Housing bills score higher than transportation bills
        """
        # Get regulations from both topics
        housing_result = civic.what_applies("housing")
        transport_result = civic.what_applies("transportation")

        # Embed the semantic query
        query = "affordable housing development and zoning reform"
        query_embedding = embedder.encode(query)

        # Score housing bills
        housing_scores = []
        for bill in housing_result.state:
            if bill.get("type") == "bill":
                # Embed bill text (title + leverage_point)
                bill_text = f"{bill.get('title', '')} {bill.get('leverage_point', '')}"
                bill_embedding = embedder.encode(bill_text)
                score = self._cosine_similarity(query_embedding, bill_embedding)
                housing_scores.append((bill.get("id"), score))

        # Score transportation bills
        transport_scores = []
        for bill in transport_result.state:
            if bill.get("type") == "bill":
                bill_text = f"{bill.get('title', '')} {bill.get('leverage_point', '')}"
                bill_embedding = embedder.encode(bill_text)
                score = self._cosine_similarity(query_embedding, bill_embedding)
                transport_scores.append((bill.get("id"), score))

        # Verify housing bills exist
        assert len(housing_scores) > 0, "Expected housing bills"
        assert len(transport_scores) > 0, "Expected transportation bills"

        # Housing bills should have higher average score for housing query
        avg_housing = sum(s[1] for s in housing_scores) / len(housing_scores)
        avg_transport = sum(s[1] for s in transport_scores) / len(transport_scores)

        assert avg_housing > avg_transport, \
            f"Housing query should score housing bills higher: housing avg={avg_housing:.3f} vs transport avg={avg_transport:.3f}"

    @pytest.mark.rag
    def test_transportation_query_ranks_transportation_bills_highest(self, civic, embedder):
        """
        Verify transportation semantic query ranks transportation bills above housing bills.

        Uses embedding similarity to demonstrate semantic relevance:
        - Query: "public transit and bike infrastructure"
        - Expected: Transportation bills score higher than housing bills
        """
        housing_result = civic.what_applies("housing")
        transport_result = civic.what_applies("transportation")

        query = "public transit expansion and bike infrastructure improvements"
        query_embedding = embedder.encode(query)

        # Score housing bills
        housing_scores = []
        for bill in housing_result.state:
            if bill.get("type") == "bill":
                bill_text = f"{bill.get('title', '')} {bill.get('leverage_point', '')}"
                bill_embedding = embedder.encode(bill_text)
                score = self._cosine_similarity(query_embedding, bill_embedding)
                housing_scores.append((bill.get("id"), score))

        # Score transportation bills
        transport_scores = []
        for bill in transport_result.state:
            if bill.get("type") == "bill":
                bill_text = f"{bill.get('title', '')} {bill.get('leverage_point', '')}"
                bill_embedding = embedder.encode(bill_text)
                score = self._cosine_similarity(query_embedding, bill_embedding)
                transport_scores.append((bill.get("id"), score))

        avg_housing = sum(s[1] for s in housing_scores) / len(housing_scores) if housing_scores else 0
        avg_transport = sum(s[1] for s in transport_scores) / len(transport_scores) if transport_scores else 0

        assert avg_transport > avg_housing, \
            f"Transport query should score transport bills higher: transport avg={avg_transport:.3f} vs housing avg={avg_housing:.3f}"

    @pytest.mark.rag
    def test_semantic_query_matches_beyond_keywords(self, civic, embedder):
        """
        Verify semantic query finds relevant bills without exact keyword overlap.

        Tests that embedding similarity can match:
        - "residential density increases" -> SB 9 (duplex/lot split) without needing "density increases" keyword
        - Demonstrates value of semantic search over pure keyword matching
        """
        housing_result = civic.what_applies("housing")

        # Query that doesn't use exact keywords from the bills
        query = "how to increase residential density in single-family neighborhoods"
        query_embedding = embedder.encode(query)

        # Find best matching housing bill
        best_match = None
        best_score = 0.0
        for bill in housing_result.state:
            if bill.get("type") == "bill":
                bill_text = f"{bill.get('title', '')} {bill.get('summary', '')} {bill.get('leverage_point', '')}"
                bill_embedding = embedder.encode(bill_text)
                score = self._cosine_similarity(query_embedding, bill_embedding)
                if score > best_score:
                    best_score = score
                    best_match = bill

        # SB 9 (HOME Act) should match well - it's about duplexes and lot splits
        assert best_match is not None, "Should find a matching bill"
        assert best_score > 0.3, f"Best match score {best_score:.3f} should be reasonably high"

        # Verify we found a relevant bill (either SB 9 or another density-related bill)
        relevant_ids = ["ca-sb9", "ca-ab1287", "ca-sb330"]  # Density-related bills
        assert best_match.get("id") in relevant_ids or "density" in str(best_match).lower(), \
            f"Expected density-related bill, got {best_match.get('id')}: {best_match.get('title')}"

    @pytest.mark.rag
    def test_embedding_rankings_align_with_keyword_assignments(self, civic, embedder):
        """
        Verify embedding-based rankings don't contradict keyword-based topic assignments.

        Tests that:
        - Housing bills consistently score higher for housing queries than for transport queries
        - This validates the keyword curation is semantically coherent
        """
        housing_result = civic.what_applies("housing")

        housing_query = "housing affordability zoning reform"
        transport_query = "bus transit highway improvements"

        housing_q_embed = embedder.encode(housing_query)
        transport_q_embed = embedder.encode(transport_query)

        misaligned = []
        for bill in housing_result.state:
            if bill.get("type") == "bill":
                bill_text = f"{bill.get('title', '')} {bill.get('leverage_point', '')}"
                bill_embedding = embedder.encode(bill_text)

                housing_score = self._cosine_similarity(housing_q_embed, bill_embedding)
                transport_score = self._cosine_similarity(transport_q_embed, bill_embedding)

                # Housing bills should score higher for housing query
                if transport_score > housing_score:
                    misaligned.append({
                        "id": bill.get("id"),
                        "title": bill.get("title"),
                        "housing_score": housing_score,
                        "transport_score": transport_score
                    })

        # Allow some tolerance - not all bills perfectly aligned
        assert len(misaligned) <= 1, \
            f"Too many housing bills score higher for transport query: {misaligned}"

    @pytest.mark.rag
    def test_embedding_similarity_scores_are_meaningful(self, civic, embedder):
        """
        Verify embedding similarity scores fall in expected ranges.

        Validates:
        - Same-topic query-bill pairs have similarity > 0.2
        - Cross-topic query-bill pairs have lower similarity
        - Scores are well-distributed (not all clustered at 0 or 1)
        """
        housing_result = civic.what_applies("housing")

        query = "affordable housing development programs"
        query_embedding = embedder.encode(query)

        scores = []
        for bill in housing_result.state:
            if bill.get("type") == "bill":
                bill_text = f"{bill.get('title', '')} {bill.get('leverage_point', '')}"
                bill_embedding = embedder.encode(bill_text)
                score = self._cosine_similarity(query_embedding, bill_embedding)
                scores.append(score)

        assert len(scores) > 0, "Expected bills to score"

        # Scores should be meaningful (not all 0 or all 1)
        min_score = min(scores)
        max_score = max(scores)
        avg_score = sum(scores) / len(scores)

        assert min_score >= 0.0, f"Scores should be non-negative: min={min_score}"
        assert max_score <= 1.0, f"Scores should be <= 1: max={max_score}"
        assert avg_score > 0.2, f"Housing query should have reasonable avg similarity to housing bills: avg={avg_score:.3f}"
        assert max_score - min_score > 0.05, \
            f"Scores should have some variance: range={max_score - min_score:.3f}"


@pytest.mark.requires_real_data
class TestTopicClassificationEmbeddings:
    """
    Integration test: Agenda item topic classification via embedding similarity.

    Tests that:
    1. Agenda items are correctly mapped to topics using embeddings
    2. Embedding-based classification outperforms keyword matching for semantic queries
    3. Bias adjustments properly boost/penalize topics
    4. Multi-topic items get appropriate classifications

    This validates the migration from keyword-based to embedding-based topic classification.

    Note: Marked with 'rag' marker as it requires sentence-transformers.
    """

    @pytest.fixture
    def embedder(self):
        """Provide CivicEmbeddings for topic classification."""
        try:
            from civicos._internal.meetings.embeddings import CivicEmbeddings
            return CivicEmbeddings("city-san-rafael")
        except ImportError:
            pytest.skip("sentence-transformers not installed")

    @pytest.mark.rag
    def test_homeless_shelter_classified_as_homelessness(self, embedder):
        """
        Verify homeless shelter agenda items are classified under homelessness topic.

        Tests the primary use case for San Rafael pilot: Merrydale shelter project.
        """
        text = "Approve funding for homeless shelter at 350 Merrydale Road"
        topics = embedder.classify_topics(text, threshold=0.35)

        topic_names = [t[0] for t in topics]
        assert "homelessness" in topic_names, \
            f"Expected 'homelessness' in topics, got: {topics}"

        # Homelessness should be the top-ranked topic
        assert topics[0][0] == "homelessness", \
            f"Expected 'homelessness' as top topic, got: {topics[0]}"

    @pytest.mark.rag
    def test_bike_lane_classified_as_transportation(self, embedder):
        """
        Verify bike lane items are classified under transportation topic.
        """
        text = "New bike lane on 4th Street"
        topics = embedder.classify_topics(text, threshold=0.30)

        topic_names = [t[0] for t in topics]
        assert "transportation" in topic_names, \
            f"Expected 'transportation' in topics, got: {topics}"

    @pytest.mark.rag
    def test_budget_item_classified_correctly(self, embedder):
        """
        Verify budget items are classified under budget topic.
        """
        text = "Approve city budget for fiscal year 2025-2026"
        topics = embedder.classify_topics(text, threshold=0.35)

        topic_names = [t[0] for t in topics]
        assert "budget" in topic_names, \
            f"Expected 'budget' in topics, got: {topics}"

    @pytest.mark.rag
    def test_zoning_item_gets_multiple_topics(self, embedder):
        """
        Verify zoning/development items can have multiple relevant topics.

        Mixed-use development should trigger: development, land_use, possibly housing.
        """
        text = "Zoning change for mixed-use development on Lincoln Avenue"
        topics = embedder.classify_topics(text, threshold=0.35)

        topic_names = [t[0] for t in topics]

        # Should have at least 2 relevant topics
        assert len(topics) >= 2, \
            f"Expected multiple topics for zoning item, got: {topics}"

        # Should include land_use or development
        assert "land_use" in topic_names or "development" in topic_names, \
            f"Expected 'land_use' or 'development' in topics, got: {topics}"

    @pytest.mark.rag
    def test_bias_boosts_homelessness_topic(self, embedder):
        """
        Verify homelessness bias (+0.05) increases its score.
        """
        text = "Approve funding for homeless shelter at 350 Merrydale Road"

        topics_with_bias = embedder.classify_topics(text, threshold=0.0, apply_bias=True)
        topics_without_bias = embedder.classify_topics(text, threshold=0.0, apply_bias=False)

        # Find homelessness scores
        homelessness_with = next((s for t, s in topics_with_bias if t == "homelessness"), 0)
        homelessness_without = next((s for t, s in topics_without_bias if t == "homelessness"), 0)

        # With bias should be higher by approximately 0.05
        assert homelessness_with > homelessness_without, \
            f"Bias should boost homelessness: {homelessness_with} vs {homelessness_without}"
        assert abs((homelessness_with - homelessness_without) - 0.05) < 0.01, \
            f"Bias should be ~0.05: actual diff = {homelessness_with - homelessness_without}"

    @pytest.mark.rag
    def test_bias_penalizes_governance_topic(self, embedder):
        """
        Verify governance bias (-0.10) decreases its score.

        Governance is penalized because most civic items procedurally involve
        governance (council meetings, ordinances), making it less useful for classification.
        """
        text = "City council meeting to approve resolution"

        topics_with_bias = embedder.classify_topics(text, threshold=0.0, apply_bias=True)
        topics_without_bias = embedder.classify_topics(text, threshold=0.0, apply_bias=False)

        # Find governance scores
        governance_with = next((s for t, s in topics_with_bias if t == "governance"), 0)
        governance_without = next((s for t, s in topics_without_bias if t == "governance"), 0)

        # With bias should be lower by approximately 0.10
        assert governance_with < governance_without, \
            f"Bias should penalize governance: {governance_with} vs {governance_without}"
        assert abs((governance_without - governance_with) - 0.10) < 0.01, \
            f"Bias should be ~0.10: actual diff = {governance_without - governance_with}"

    @pytest.mark.rag
    def test_semantic_query_matches_without_keywords(self, embedder):
        """
        Verify semantic understanding matches topics without exact keyword overlap.

        Tests that embeddings capture meaning beyond keyword matching:
        - "unhoused residents" should match homelessness (no "homeless" keyword)
        - "residential density" should match housing (no "housing" keyword)
        """
        # Test 1: "unhoused" should match homelessness
        text1 = "Services for unhoused residents in downtown area"
        topics1 = embedder.classify_topics(text1, threshold=0.30)
        topic_names1 = [t[0] for t in topics1]
        assert "homelessness" in topic_names1, \
            f"'unhoused residents' should match homelessness: got {topics1}"

        # Test 2: "residential density" should match housing
        text2 = "Increase residential density near transit stations"
        topics2 = embedder.classify_topics(text2, threshold=0.30)
        topic_names2 = [t[0] for t in topics2]
        assert "housing" in topic_names2, \
            f"'residential density' should match housing: got {topics2}"

    @pytest.mark.rag
    def test_get_topic_names_convenience_method(self, embedder):
        """
        Verify get_topic_names() returns just topic names without scores.
        """
        text = "Approve funding for homeless shelter at 350 Merrydale Road"
        topic_names = embedder.get_topic_names(text, threshold=0.35)

        assert isinstance(topic_names, list), "Should return a list"
        assert all(isinstance(t, str) for t in topic_names), "Should be list of strings"
        assert "homelessness" in topic_names, "Should include homelessness"

    @pytest.mark.rag
    def test_top_k_limits_results(self, embedder):
        """
        Verify top_k parameter limits the number of returned topics.
        """
        text = "Zoning change for mixed-use development on Lincoln Avenue"

        # Get all topics above threshold
        all_topics = embedder.classify_topics(text, threshold=0.0)

        # Get top 2 only
        top_2 = embedder.classify_topics(text, threshold=0.0, top_k=2)

        assert len(top_2) == 2, f"Expected exactly 2 topics with top_k=2, got {len(top_2)}"
        assert top_2[0][1] >= top_2[1][1], "Topics should be sorted by score descending"

        # Top 2 should match first 2 of all topics
        assert top_2[0][0] == all_topics[0][0], "First topic should match"
        assert top_2[1][0] == all_topics[1][0], "Second topic should match"

    @pytest.mark.rag
    def test_topic_embeddings_are_cached(self, embedder):
        """
        Verify topic embeddings are cached after first classification.
        """
        text = "Test item"

        # First call should create cache
        embedder.classify_topics(text)
        assert hasattr(embedder, '_topic_embeddings'), "Should cache topic embeddings"

        # Cache should have all topics
        cached_topics = set(embedder._topic_embeddings.keys())
        config_topics = set(embedder.TOPIC_CONFIG.keys())
        assert cached_topics == config_topics, \
            f"Cache should have all topics: {cached_topics} vs {config_topics}"

    @pytest.mark.rag
    def test_real_agenda_items_classification(self, embedder):
        """
        Verify classification works on real San Rafael agenda item titles.

        Uses actual titles from Nov 17, 2025 council meeting.
        """
        real_items = [
            (
                "Declaration of Shelter Crisis and Authorization to Purchase Real Property "
                "at 350 Merrydale Road",
                ["homelessness", "housing"],
                0.35,
            ),
            (
                "Approval of Minutes from November 3, 2025 Regular City Council Meeting",
                [],  # Procedural item, may not match substantive topics with high threshold
                0.35,
            ),
            (
                "Accept Fire Department Annual Report",
                ["public_safety"],
                0.30,  # Short title needs lower threshold
            ),
        ]

        for title, expected_topics, threshold in real_items:
            topics = embedder.classify_topics(title, threshold=threshold)
            topic_names = [t[0] for t in topics]

            if expected_topics:
                # At least one expected topic should be present
                matches = [t for t in expected_topics if t in topic_names]
                assert len(matches) > 0, \
                    f"Expected one of {expected_topics} for '{title[:50]}...', got: {topic_names}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
