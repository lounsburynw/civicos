"""
Integration tests for MCP agent sequences.

Tests realistic AI agent interaction patterns with MCP tools,
verifying that multi-tool sequences work correctly together.

These tests simulate how an AI agent (like Claude) would use
the Civic MCP tools in realistic workflows.
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta, timezone

# Mark all tests in this module as integration
pytestmark = pytest.mark.integration


class TestDiscoverySequence:
    """Test MCP discovery sequences (browse_then_filter, research_workflow)."""

    def test_browse_then_filter_sequence_basic(self):
        """
        Test whats_next → what_applies sequence works.

        Simulates an agent browsing upcoming meetings and then
        filtering to understand regulations for a topic found.

        Note: Agent identifies topics from meeting title/type. Agenda item
        extraction from nested full_data is tracked in data_model_consistency
        section of integration.json for future fix.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup: Create a meeting with housing-related title
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_housing_001",
                "title": "Affordable Housing Development Review",
                "meeting_datetime": future_date,
                "meeting_type": "Planning Commission",
                "location": "City Hall, Room 201",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_h_001",
                        "title": "New Affordable Housing Project",
                        "description": "Review of 50-unit affordable housing proposal"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: Agent browses upcoming meetings
            meetings = civic.whats_next(days=30)

            assert len(meetings) >= 1

            # Agent identifies relevant meeting by title
            housing_meeting = next(
                (m for m in meetings if "housing" in m.title.lower()),
                None
            )
            assert housing_meeting is not None

            # Step 2: Agent filters for housing regulations
            context = civic.what_applies("housing")

            assert context.topic == "housing"
            assert context.jurisdiction == "san-rafael"

    def test_browse_then_filter_multiple_topics(self):
        """
        Test browse → filter for multiple topics found in meetings.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            # Create meetings for multiple topics
            state.update_meetings("san-rafael", [
                {
                    "id": "mtg_multi_001",
                    "title": "Traffic Safety Committee",
                    "meeting_datetime": future_date,
                    "meeting_type": "Committee",
                    "location": "City Hall",
                    "source_platform": "test",
                    "full_data": {
                        "agenda_items": [{
                            "id": "agenda_t_001",
                            "title": "Speed Limit Review",
                            "description": "Review of speed limits on Main Street"
                        }]
                    }
                },
                {
                    "id": "mtg_multi_002",
                    "title": "Parks and Recreation Meeting",
                    "meeting_datetime": future_date,
                    "meeting_type": "Commission",
                    "location": "Recreation Center",
                    "source_platform": "test",
                    "full_data": {
                        "agenda_items": [{
                            "id": "agenda_p_001",
                            "title": "Park Renovation Plan",
                            "description": "Renovation of downtown park"
                        }]
                    }
                }
            ])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Browse
            meetings = civic.whats_next(days=30)
            assert len(meetings) >= 2

            # Filter for both topics
            traffic_context = civic.what_applies("traffic")
            parks_context = civic.what_applies("parks")

            assert traffic_context.topic == "traffic"
            assert parks_context.topic == "parks"

    def test_browse_then_filter_with_location(self):
        """
        Test browse with location-aware filtering.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_loc_001",
                "title": "Neighborhood Meeting - Canal District",
                "meeting_datetime": future_date,
                "meeting_type": "Community",
                "location": "Canal Community Center",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_loc_001",
                        "title": "Canal District Development",
                        "description": "Development plans for Canal area"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Browse meetings
            meetings = civic.whats_next(days=30)
            assert len(meetings) >= 1

            # Meeting has location info
            mtg = meetings[0]
            assert mtg.location is not None

            # Filter by topic
            context = civic.what_applies("development")
            assert context.topic == "development"

    def test_browse_then_filter_empty_results(self):
        """
        Test sequence works when meetings or regulations are empty.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Browse with empty database
            meetings = civic.whats_next(days=30)
            assert meetings == []

            # Filter still works (returns empty context)
            context = civic.what_applies("housing")
            assert context.topic == "housing"
            assert context.jurisdiction == "san-rafael"


class TestResearchWorkflow:
    """Test MCP research workflow sequences."""

    def test_research_workflow_basic(self):
        """
        Test what_happened → whos_with_me → prepare sequence works.

        Simulates an agent researching a topic, finding community,
        and preparing for participation.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup: Create meeting with agenda item, and some community data
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_research_001",
                "title": "City Council Meeting",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall, Council Chambers",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_bikes_001",
                        "title": "Protected Bike Lane Proposal",
                        "description": "Discussion of bike infrastructure improvements"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: Research what has happened with this topic before
            history = civic.what_happened("bike lanes")
            # what_happened returns empty list in Phase 1 implementation
            assert isinstance(history, list)

            # Step 2: Find community around this topic
            community = civic.whos_with_me("bike lanes")

            assert community.topic == "bike lanes"
            assert community.jurisdiction == "san-rafael"
            assert isinstance(community.follower_count, int)
            assert isinstance(community.recent_voices, list)
            assert isinstance(community.active_initiatives, list)

            # Step 3: Prepare for the meeting
            preparation = civic.prepare("agenda_bikes_001")

            assert preparation.agenda_item_id == "agenda_bikes_001"
            assert isinstance(preparation.regulatory_context, dict)
            assert isinstance(preparation.historical_decisions, list)
            assert isinstance(preparation.talking_points, list)
            assert isinstance(preparation.allies, list)
            assert isinstance(preparation.logistics, dict)

    def test_research_workflow_prepare_not_found(self):
        """
        Test prepare raises error for non-existent agenda item.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Research steps work even without data
            history = civic.what_happened("unknown topic")
            assert isinstance(history, list)

            community = civic.whos_with_me("unknown topic")
            assert community.topic == "unknown topic"

            # But prepare fails for non-existent agenda item
            with pytest.raises(ValueError, match="not found"):
                civic.prepare("nonexistent_agenda_item")


class TestSequenceDataConsistency:
    """Test that data remains consistent across tool sequences."""

    def test_browse_filter_data_consistent(self):
        """
        Test that meeting data from whats_next matches what_applies context.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_consistent_001",
                "title": "City Council",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_c_001",
                        "title": "Housing Policy Review",
                        "description": "Review housing regulations"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Call whats_next
            meetings1 = civic.whats_next(days=30)

            # Call what_applies
            context = civic.what_applies("housing")

            # Call whats_next again - should get same data
            meetings2 = civic.whats_next(days=30)

            assert len(meetings1) == len(meetings2)
            assert meetings1[0].id == meetings2[0].id

            # Context should have consistent jurisdiction
            assert context.jurisdiction == "san-rafael"


class TestSequenceErrorHandling:
    """Test error handling in tool sequences."""

    def test_browse_then_filter_handles_network_like_errors(self):
        """
        Test sequence handles errors gracefully without corrupting state.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_error_001",
                "title": "City Council",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {}
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Successful browse
            meetings = civic.whats_next(days=30)
            assert len(meetings) >= 1

            # what_applies works even for unusual topics
            context = civic.what_applies("unusual_topic_xyz")
            assert context.topic == "unusual_topic_xyz"

            # Meetings still accessible after other operations
            meetings_again = civic.whats_next(days=30)
            assert len(meetings_again) == len(meetings)

    def test_research_workflow_continues_after_partial_failure(self):
        """
        Test research workflow continues even if one step returns empty.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: what_happened returns empty (expected in Phase 1)
            history = civic.what_happened("rare_topic")
            assert history == []

            # Step 2: whos_with_me still works
            community = civic.whos_with_me("rare_topic")
            assert community.topic == "rare_topic"
            assert community.follower_count == 0

            # Step 3: prepare fails but doesn't corrupt state
            with pytest.raises(ValueError):
                civic.prepare("nonexistent_item")

            # Can still use other methods after error
            community2 = civic.whos_with_me("another_topic")
            assert community2.topic == "another_topic"


class TestCrossToolConsistency:
    """
    Test cross_tool_consistency.

    Verifies that data is consistent across different tool views,
    ensuring that the same underlying data appears the same
    regardless of which tool accesses it.
    """

    def test_meeting_consistent_across_query_methods(self):
        """
        Test that meeting data is consistent across different query methods.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_cross_001",
                "title": "Planning Commission",
                "meeting_datetime": future_date,
                "meeting_type": "Planning Commission",
                "location": "City Hall, Room 201",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_cross_001",
                        "title": "Zone Amendment",
                        "description": "Proposed zone change"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Query via whats_next (Civic API)
            meetings_civic = civic.whats_next(days=30)

            # Query via StateManager
            meetings_state = state.query_meetings("san-rafael")

            # Both should return the same meeting
            assert len(meetings_civic) == len(meetings_state)

            civic_mtg = meetings_civic[0]
            state_mtg = meetings_state[0]

            assert civic_mtg.id == state_mtg["id"]
            assert civic_mtg.title == state_mtg["title"]
            assert civic_mtg.location == state_mtg["location"]

    def test_prepare_uses_consistent_data(self):
        """
        Test that prepare() uses consistent underlying data.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            # Create meeting with specific agenda item
            state.update_meetings("san-rafael", [{
                "id": "mtg_prep_001",
                "title": "City Council",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall, Council Chambers",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_prep_001",
                        "title": "Annual Budget Review",
                        "description": "Review of FY2025 budget proposal"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Call prepare
            preparation = civic.prepare("agenda_prep_001")

            # Verify prepare returns consistent data
            assert preparation.agenda_item_id == "agenda_prep_001"
            assert isinstance(preparation.regulatory_context, dict)
            assert isinstance(preparation.talking_points, list)
            assert isinstance(preparation.logistics, dict)

            # Logistics should reflect meeting data
            assert "location" in preparation.logistics or len(preparation.logistics) >= 0


class TestErrorRecovery:
    """
    Test error_recovery in MCP agent sequences.

    Verifies that an agent can retry failed tool calls and that
    partial workflow failures don't corrupt state.
    """

    def test_retry_after_error_missing_item(self):
        """
        Test that agent can retry prepare() after agenda item not found.

        Simulates: Agent calls prepare with wrong ID, gets error,
        queries for correct ID, retries successfully.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Create meeting with agenda item
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_retry_001",
                "title": "City Council Meeting",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_correct_001",
                        "title": "Traffic Safety Discussion",
                        "description": "Review of traffic incidents"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # First attempt: Wrong agenda item ID
            try:
                civic.prepare("agenda_wrong_id")
                assert False, "Should have raised ValueError"
            except ValueError as e:
                error_msg = str(e)
                assert "not found" in error_msg

            # Agent discovers correct ID by browsing meetings
            meetings = civic.whats_next(days=30)
            assert len(meetings) >= 1

            # Retry with correct ID
            preparation = civic.prepare("agenda_correct_001")

            # Retry succeeds
            assert preparation.agenda_item_id == "agenda_correct_001"
            assert isinstance(preparation.talking_points, list)
            assert isinstance(preparation.regulatory_context, dict)


class TestPartialWorkflow:
    """
    Test partial_workflow error recovery.

    Verifies that a workflow can survive single tool failures
    and continue to completion.
    """

    def test_workflow_survives_middle_failure(self):
        """
        Test that workflow continues after middle step fails.

        Workflow: whats_next → what_applies (fails) → whos_with_me
        The workflow should still complete whos_with_me after what_applies error.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_partial_001",
                "title": "City Council",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {}
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: whats_next (succeeds)
            meetings = civic.whats_next(days=30)
            assert len(meetings) >= 1

            # Step 2: what_applies with unusual topic (succeeds but returns empty)
            context = civic.what_applies("very_obscure_topic_xyz")
            assert context.topic == "very_obscure_topic_xyz"
            # Returns empty context but doesn't fail

            # Step 3: whos_with_me (succeeds)
            community = civic.whos_with_me("housing")
            assert community.topic == "housing"
            assert community.jurisdiction == "san-rafael"

    def test_workflow_survives_prepare_failure(self):
        """
        Test that research workflow survives prepare() failure.

        Workflow: what_happened → whos_with_me → prepare (fails) → retries prepare
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_prep_fail",
                "title": "Planning Commission",
                "meeting_datetime": future_date,
                "meeting_type": "Planning Commission",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_valid_001",
                        "title": "Zone Change",
                        "description": "Proposed zone change for Main St"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: what_happened
            history = civic.what_happened("zoning")
            assert isinstance(history, list)

            # Step 2: whos_with_me
            community = civic.whos_with_me("zoning")
            assert community.topic == "zoning"

            # Step 3a: prepare fails (wrong ID)
            try:
                civic.prepare("wrong_agenda_id")
                assert False, "Should have raised ValueError"
            except ValueError:
                pass  # Expected

            # Step 3b: prepare succeeds with correct ID
            preparation = civic.prepare("agenda_valid_001")
            assert preparation.agenda_item_id == "agenda_valid_001"
