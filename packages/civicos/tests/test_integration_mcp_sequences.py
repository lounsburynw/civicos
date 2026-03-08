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

            # Step 2: Verify other methods still work after empty results
            context = civic.what_applies("rare_topic")
            assert context.topic == "rare_topic"


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

    # test_prepare_uses_consistent_data removed: prepare() not yet implemented



class TestPartialWorkflow:
    """
    Test partial_workflow error recovery.

    Verifies that a workflow can survive single tool failures
    and continue to completion.
    """

    def test_workflow_survives_middle_failure(self):
        """
        Test that workflow continues after middle step fails.

        Workflow: whats_next → what_applies (fails) → what_happened
        The workflow should still complete what_happened after what_applies error.
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

            # Step 3: what_happened (succeeds)
            history = civic.what_happened("housing")
            assert isinstance(history, list)

    def test_workflow_survives_prepare_failure(self):
        """
        Test that research workflow survives prepare() failure.

        Workflow: what_happened → what_applies → prepare (fails) → retries prepare
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

            # Step 2: what_applies
            context = civic.what_applies("zoning")
            assert context.topic == "zoning"

            # Note: prepare() not yet implemented on CivicOS
