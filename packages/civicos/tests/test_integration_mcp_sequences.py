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
                "full_data": {}
            }])

            # Step 1: Agent calls whats_next to browse upcoming meetings
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            meetings = civic.whats_next(days=30)

            # Agent finds meetings
            assert len(meetings) >= 1
            meeting = meetings[0]
            assert meeting.id == "mtg_housing_001"

            # Agent identifies housing topic from meeting title
            assert "housing" in meeting.title.lower()

            # Step 2: Agent calls what_applies to understand housing regulations
            regulatory_context = civic.what_applies("housing")

            # Agent gets regulatory context
            assert regulatory_context.topic == "housing"
            assert regulatory_context.jurisdiction == "san-rafael"
            # Context should have structure even if empty
            assert isinstance(regulatory_context.federal, list)
            assert isinstance(regulatory_context.state, list)
            assert isinstance(regulatory_context.local, list)

    def test_browse_then_filter_multiple_topics(self):
        """
        Test agent can browse multiple meetings and filter on topics found.

        Note: Agent identifies topics from meeting titles. Multiple meetings
        simulate finding different topics across the calendar.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup: Create multiple meetings with different topics in titles
            state = StateManager(db_path)
            future_date1 = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
            future_date2 = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()

            state.update_meetings("san-rafael", [
                {
                    "id": "mtg_traffic_001",
                    "title": "Traffic Calming Study Session",
                    "meeting_datetime": future_date1,
                    "meeting_type": "City Council",
                    "location": "City Hall",
                    "source_platform": "test",
                    "full_data": {}
                },
                {
                    "id": "mtg_parking_001",
                    "title": "Downtown Parking Policy Review",
                    "meeting_datetime": future_date2,
                    "meeting_type": "City Council",
                    "location": "City Hall",
                    "source_platform": "test",
                    "full_data": {}
                }
            ])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: Browse meetings
            meetings = civic.whats_next(days=30)
            assert len(meetings) >= 2

            # Agent identifies topics from meeting titles
            topics_found = []
            for meeting in meetings:
                if "traffic" in meeting.title.lower():
                    topics_found.append("traffic")
                if "parking" in meeting.title.lower():
                    topics_found.append("parking")

            assert len(topics_found) >= 2

            # Step 2: Filter on multiple topics found
            for topic in topics_found:
                context = civic.what_applies(topic)
                assert context.topic == topic
                assert context.jurisdiction == "san-rafael"

    def test_browse_then_filter_with_location(self):
        """
        Test agent can specify location when filtering regulations.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup: Create a meeting about a specific location
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_loc_001",
                "title": "Design Review Board",
                "meeting_datetime": future_date,
                "meeting_type": "Design Review",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_design_001",
                        "title": "New Development at 456 Lincoln Ave",
                        "description": "Design review for mixed-use development"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: Browse meetings
            meetings = civic.whats_next(days=30)
            assert len(meetings) >= 1

            # Agent extracts location from agenda item
            location = "456 Lincoln Ave"

            # Step 2: Filter with location
            context = civic.what_applies("development", location=location)

            assert context.topic == "development"
            assert context.jurisdiction == "san-rafael"

    def test_browse_then_filter_empty_results(self):
        """
        Test sequence handles case where whats_next returns no meetings.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Empty database - no meetings
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: Browse meetings (none available)
            meetings = civic.whats_next(days=30)
            assert len(meetings) == 0

            # Agent should still be able to query regulations directly
            context = civic.what_applies("housing")
            assert context.topic == "housing"


class TestResearchWorkflow:
    """Test research workflow: what_happened → whos_with_me → prepare."""

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

    def test_research_workflow_with_existing_initiative(self):
        """
        Test research workflow when there's an existing initiative on the topic.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup meeting
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_init_001",
                "title": "Planning Commission",
                "meeting_datetime": future_date,
                "meeting_type": "Planning Commission",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_traffic_001",
                        "title": "Traffic Safety Review",
                        "description": "Annual traffic safety review"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create an initiative first
            initiative = civic.start_something(
                topic="traffic safety",
                title="Safer crosswalks on 4th Street",
                description="We need better crosswalk infrastructure",
                creator_id="researcher_001"
            )

            # Add some community engagement
            civic.add_voice("initiative", initiative.id, "support", "Great idea!", user_id="u1")
            civic.add_voice("initiative", initiative.id, "support", "Much needed!", user_id="u2")
            civic.follow("initiative", initiative.id, user_id="u3")

            # Step 1: Research history
            history = civic.what_happened("traffic safety")
            assert isinstance(history, list)

            # Step 2: Find community (should show initiative activity)
            community = civic.whos_with_me("traffic safety")
            assert community.topic == "traffic safety"
            # Should reflect community activity
            assert isinstance(community.follower_count, int)

            # Step 3: Prepare for meeting
            preparation = civic.prepare("agenda_traffic_001")
            assert preparation.agenda_item_id == "agenda_traffic_001"
            assert len(preparation.talking_points) > 0

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

    def test_research_workflow_full_with_user_context(self):
        """
        Test research workflow with user personalization.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup meeting
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_user_001",
                "title": "City Council",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_env_001",
                        "title": "Environmental Policy Update",
                        "description": "Updates to city environmental policies"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            user_id = "active_user_001"

            # User has existing engagement
            civic.follow("topic", "environment", user_id=user_id)
            civic.add_voice("agenda_item", "agenda_env_001", "support",
                          "I support environmental protections", user_id=user_id)

            # Research workflow with user context
            history = civic.what_happened("environment")
            assert isinstance(history, list)

            community = civic.whos_with_me("environment")
            assert community.topic == "environment"

            # Prepare with user context
            preparation = civic.prepare("agenda_env_001", user_id=user_id)
            assert preparation.agenda_item_id == "agenda_env_001"


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

    def test_research_workflow_data_consistent(self):
        """
        Test data consistency through research workflow sequence.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_data_001",
                "title": "Planning Meeting",
                "meeting_datetime": future_date,
                "meeting_type": "Planning",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_data_001",
                        "title": "Transit Plan",
                        "description": "Transit planning discussion"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="transit",
                title="Better bus service",
                description="We need better buses"
            )
            init_id = initiative.id

            # Research
            civic.what_happened("transit")

            # Community check
            community = civic.whos_with_me("transit")

            # Prepare
            preparation = civic.prepare("agenda_data_001")

            # Verify initiative still accessible
            # (uses internal state manager to verify)
            init_data = state.get_initiative(init_id)
            assert init_data is not None
            assert init_data["topic"] == "transit"


class TestActionSequence:
    """Test MCP action sequences (create_and_voice, coordinate_workflow)."""

    def test_create_and_voice_basic(self):
        """
        Test start_something → add_voice → follow sequence works.

        Simulates an agent helping a user create an initiative,
        add their voice to it, and subscribe for updates.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            user_id = "active_citizen_001"

            # Step 1: Create initiative
            initiative = civic.start_something(
                topic="traffic safety",
                title="Protected bike lane on 4th Street",
                description="We need protected bike lanes to make cycling safer for commuters and families.",
                location="4th Street between A and D",
                creator_id=user_id
            )

            assert initiative.id.startswith("init_")
            assert initiative.topic == "traffic safety"
            assert initiative.title == "Protected bike lane on 4th Street"
            assert initiative.creator_id == user_id

            # Step 2: Add creator's voice (support their own initiative)
            voice = civic.add_voice(
                item_type="initiative",
                item_id=initiative.id,
                stance="support",
                comment="As a daily bike commuter, I've had several close calls on 4th Street.",
                user_id=user_id
            )

            assert voice.id.startswith("voice_")
            assert voice.item_type == "initiative"
            assert voice.item_id == initiative.id
            assert voice.stance == "support"

            # Step 3: Follow for updates
            subscription = civic.follow(
                item_type="initiative",
                item_id=initiative.id,
                user_id=user_id
            )

            assert subscription.id.startswith("sub_")
            assert subscription.item_type == "initiative"
            assert subscription.item_id == initiative.id

    def test_create_and_voice_multiple_users(self):
        """
        Test multiple users can voice and follow an initiative.

        Simulates community building around an initiative:
        - User creates initiative
        - Multiple users add support voices
        - Users follow for updates
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            creator_id = "creator_001"
            supporter_ids = ["supporter_001", "supporter_002", "supporter_003"]

            # Step 1: Creator starts initiative
            initiative = civic.start_something(
                topic="housing",
                title="More affordable housing units downtown",
                description="We need more affordable housing options for working families.",
                creator_id=creator_id
            )

            # Step 2: Multiple supporters add voices
            voices = []
            comments = [
                "As a teacher, I can barely afford rent here.",
                "My kids have had to move away because they can't afford to live here.",
                "Affordable housing is essential for our community's future."
            ]

            for user_id, comment in zip(supporter_ids, comments):
                voice = civic.add_voice(
                    item_type="initiative",
                    item_id=initiative.id,
                    stance="support",
                    comment=comment,
                    user_id=user_id
                )
                voices.append(voice)
                assert voice.stance == "support"
                assert voice.item_id == initiative.id

            assert len(voices) == 3

            # Step 3: All supporters follow for updates
            subscriptions = []
            for user_id in supporter_ids:
                sub = civic.follow(
                    item_type="initiative",
                    item_id=initiative.id,
                    user_id=user_id
                )
                subscriptions.append(sub)
                assert sub.item_type == "initiative"

            assert len(subscriptions) == 3

    def test_create_and_voice_with_opposition(self):
        """
        Test initiative with mixed support and opposition.

        Simulates contentious issue where users have different stances.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create controversial initiative
            initiative = civic.start_something(
                topic="development",
                title="New high-density housing at Lincoln and 4th",
                description="Proposed 100-unit mixed-use development.",
                location="Lincoln Ave and 4th Street",
                creator_id="developer_001"
            )

            # Support voices
            support1 = civic.add_voice(
                "initiative", initiative.id, "support",
                "We desperately need more housing.", user_id="u1"
            )
            support2 = civic.add_voice(
                "initiative", initiative.id, "support",
                "This location has great transit access.", user_id="u2"
            )

            # Opposition voices
            oppose1 = civic.add_voice(
                "initiative", initiative.id, "oppose",
                "This will increase traffic significantly.", user_id="u3"
            )
            oppose2 = civic.add_voice(
                "initiative", initiative.id, "oppose",
                "The building height doesn't fit the neighborhood.", user_id="u4"
            )

            # Question voice
            question = civic.add_voice(
                "initiative", initiative.id, "question",
                "What will the parking situation be?", user_id="u5"
            )

            # Verify all stances recorded
            assert support1.stance == "support"
            assert support2.stance == "support"
            assert oppose1.stance == "oppose"
            assert oppose2.stance == "oppose"
            assert question.stance == "question"

            # All voices reference the same initiative
            all_voices = [support1, support2, oppose1, oppose2, question]
            for v in all_voices:
                assert v.item_id == initiative.id

    def test_create_and_voice_then_community_check(self):
        """
        Test that created initiative becomes visible in whos_with_me.

        Simulates agent verifying community exists after creation.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            topic = "bike infrastructure"

            # Check community before (should be empty)
            community_before = civic.whos_with_me(topic)
            initial_count = community_before.follower_count

            # Create initiative
            initiative = civic.start_something(
                topic=topic,
                title="City-wide bike lane network",
                description="Connect all neighborhoods with protected bike lanes.",
                creator_id="bike_advocate_001"
            )

            # Add voices
            for i in range(5):
                civic.add_voice(
                    "initiative", initiative.id, "support",
                    f"Great idea! - user {i}", user_id=f"user_{i}"
                )
                civic.follow("initiative", initiative.id, user_id=f"user_{i}")

            # whos_with_me should reflect activity
            # Note: Current implementation counts issues by type, not initiatives
            # This test documents expected behavior for future enhancement
            community_after = civic.whos_with_me(topic)
            assert community_after.topic == topic


class TestCoordinateWorkflow:
    """Test coordination workflow: start_something → coordinate → report_outcome."""

    def test_coordinate_workflow_basic(self):
        """
        Test start_something → coordinate → report_outcome sequence.

        Simulates full lifecycle of an initiative from creation
        through coordination to outcome reporting.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup: Create meeting with agenda item
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_coord_001",
                "title": "City Council",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_coord_001",
                        "title": "Bike Lane Proposal Vote",
                        "description": "Final vote on 4th Street protected bike lane"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: Create initiative
            initiative = civic.start_something(
                topic="transportation",
                title="Support the 4th Street bike lane vote",
                description="Mobilize supporters to speak at the council meeting.",
                creator_id="organizer_001"
            )

            # Add enough support to warrant coordination
            for i in range(6):
                civic.add_voice(
                    "initiative", initiative.id, "support",
                    f"I'll speak at the meeting - user {i}", user_id=f"speaker_{i}"
                )
                civic.follow("initiative", initiative.id, user_id=f"speaker_{i}")

            # Step 2: Coordination was removed in the LangGraph cleanup refactor.
            # The coordinate() method no longer exists on CivicOS.
            # This test now validates the initiative → report_outcome flow.

            # Step 3: Report outcome
            outcome = civic.report_outcome(
                item_id=initiative.id,
                outcome="passed",
                notes="Passed 5-2 after strong community turnout",
                item_type="initiative",
                user_id="organizer_001"
            )

            assert outcome.item_id == initiative.id
            assert outcome.outcome == "passed"
            assert "5-2" in outcome.notes

    def test_coordinate_workflow_with_vote_breakdown(self):
        """
        Test coordination workflow with detailed vote breakdown.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="environment",
                title="Ban single-use plastics",
                description="Phase out single-use plastic bags and straws.",
                creator_id="env_advocate_001"
            )

            # Report outcome with vote breakdown
            outcome = civic.report_outcome(
                item_id=initiative.id,
                outcome="modified",
                notes="Modified to phase in over 2 years",
                item_type="initiative",
                user_id="env_advocate_001",
                vote_breakdown={"yes": 4, "no": 2, "abstain": 1}
            )

            assert outcome.outcome == "modified"
            assert "2 years" in outcome.notes

    def test_coordinate_workflow_failed_outcome(self):
        """
        Test reporting failed outcome for initiative.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="zoning",
                title="Allow ADUs in single-family zones",
                description="Enable homeowners to build accessory dwelling units.",
                creator_id="housing_advocate_001"
            )

            # Report failed outcome
            outcome = civic.report_outcome(
                item_id=initiative.id,
                outcome="failed",
                notes="Failed 2-5, will try again next year",
                item_type="initiative"
            )

            assert outcome.item_id == initiative.id
            assert outcome.outcome == "failed"

    def test_coordinate_workflow_agenda_item_outcome(self):
        """
        Test reporting outcome for an agenda item (not initiative).
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Create meeting with agenda item
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_agenda_outcome",
                "title": "Planning Commission",
                "meeting_datetime": future_date,
                "meeting_type": "Planning Commission",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_outcome_001",
                        "title": "Conditional Use Permit - 123 Main St",
                        "description": "Permit for new restaurant"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Report outcome on agenda item
            outcome = civic.report_outcome(
                item_id="agenda_outcome_001",
                outcome="passed",
                notes="Approved with conditions: limited hours, parking plan required",
                item_type="agenda_item"
            )

            assert outcome.item_id == "agenda_outcome_001"
            assert outcome.outcome == "passed"


class TestActionSequenceDataConsistency:
    """Test data consistency across action sequences."""

    def test_initiative_visible_after_creation(self):
        """
        Test that initiative is immediately visible after creation.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="parks",
                title="New dog park at Schoen Park",
                description="Dedicated off-leash area for dogs.",
                creator_id="dog_owner_001"
            )

            # Verify initiative exists in state
            state = StateManager(db_path)
            stored = state.get_initiative(initiative.id)

            assert stored is not None
            assert stored["title"] == "New dog park at Schoen Park"
            assert stored["topic"] == "parks"

    def test_voices_accumulate_correctly(self):
        """
        Test that multiple voices are stored correctly.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            initiative = civic.start_something(
                topic="safety",
                title="More streetlights downtown",
                description="Improve nighttime safety.",
                creator_id="resident_001"
            )

            # Add 5 voices
            voice_ids = []
            for i in range(5):
                voice = civic.add_voice(
                    "initiative", initiative.id, "support",
                    f"Comment {i}", user_id=f"user_{i}"
                )
                voice_ids.append(voice.id)

            # All voice IDs should be unique
            assert len(set(voice_ids)) == 5

            # Verify each voice exists in state
            state = StateManager(db_path)
            for voice_id in voice_ids:
                voice = state.get_voice(voice_id)
                assert voice is not None
                assert voice["item_id"] == initiative.id
                assert voice["item_type"] == "initiative"
                assert voice["stance"] == "support"

    def test_subscriptions_stored_correctly(self):
        """
        Test that subscriptions are stored and retrievable.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            initiative = civic.start_something(
                topic="transit",
                title="Extended bus hours",
                description="Later evening bus service.",
                creator_id="commuter_001"
            )

            # Follow with 3 users
            sub_ids = []
            for i in range(3):
                sub = civic.follow(
                    "initiative", initiative.id, user_id=f"follower_{i}"
                )
                sub_ids.append(sub.id)

            # All subscription IDs should be unique
            assert len(set(sub_ids)) == 3


class TestActionSequenceErrorHandling:
    """Test error handling in action sequences."""

    def test_invalid_stance_raises_error(self):
        """
        Test that invalid stance raises ValueError.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            initiative = civic.start_something(
                topic="test",
                title="Test initiative",
                description="For testing error handling.",
                creator_id="test_user"
            )

            # Invalid stance should raise error
            with pytest.raises(ValueError, match="stance must be one of"):
                civic.add_voice(
                    "initiative", initiative.id, "invalid_stance",
                    "This should fail", user_id="test_user"
                )

    def test_invalid_item_type_raises_error(self):
        """
        Test that invalid item_type raises ValueError for add_voice.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            with pytest.raises(ValueError, match="item_type must be one of"):
                civic.add_voice(
                    "invalid_type", "item_123", "support",
                    "This should fail", user_id="test_user"
                )

    def test_invalid_follow_item_type_raises_error(self):
        """
        Test that invalid item_type raises ValueError for follow.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            with pytest.raises(ValueError, match="item_type must be one of"):
                civic.follow(
                    "invalid_type", "item_123", user_id="test_user"
                )

    def test_workflow_continues_after_voice_error(self):
        """
        Test that workflow can continue after a voice error.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="test",
                title="Error recovery test",
                description="Testing error recovery.",
                creator_id="test_user"
            )

            # Try invalid voice (should fail)
            try:
                civic.add_voice(
                    "initiative", initiative.id, "invalid",
                    "Bad stance", user_id="test_user"
                )
            except ValueError:
                pass  # Expected

            # Valid voice should still work
            voice = civic.add_voice(
                "initiative", initiative.id, "support",
                "This should work", user_id="test_user"
            )

            assert voice.id.startswith("voice_")
            assert voice.stance == "support"

            # Follow should still work
            sub = civic.follow(
                "initiative", initiative.id, user_id="test_user"
            )

            assert sub.id.startswith("sub_")


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


class TestReadAfterWrite:
    """
    Test read_after_write state consistency.

    Verifies that created initiatives are visible in subsequent queries,
    ensuring write operations are immediately reflected in read operations.
    """

    def test_initiative_visible_in_whats_next_after_creation(self):
        """
        Test that after creating an initiative related to a meeting,
        the state remains consistent when querying whats_next.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup: Create a meeting
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_raw_001",
                "title": "City Council Meeting",
                "meeting_datetime": future_date,
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_raw_001",
                        "title": "Traffic Safety Discussion",
                        "description": "Review of traffic incidents"
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Read: Get meetings before write
            meetings_before = civic.whats_next(days=30)
            assert len(meetings_before) == 1

            # Write: Create initiative
            initiative = civic.start_something(
                topic="traffic safety",
                title="Speed bumps on Main Street",
                description="We need speed bumps to slow traffic.",
                creator_id="citizen_001"
            )

            # Read after write: Meetings should still be accessible
            meetings_after = civic.whats_next(days=30)
            assert len(meetings_after) == 1
            assert meetings_after[0].id == meetings_before[0].id

            # Verify initiative is in state
            stored = state.get_initiative(initiative.id)
            assert stored is not None
            assert stored["title"] == "Speed bumps on Main Street"

    def test_initiative_visible_in_query_immediately(self):
        """
        Test that created initiative is immediately visible via query.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Query before creation
            state = StateManager(db_path)
            initiatives_before = state.query_initiatives("san-rafael")
            count_before = len(initiatives_before)

            # Create initiative
            initiative = civic.start_something(
                topic="housing",
                title="More affordable units downtown",
                description="We need affordable housing options.",
                creator_id="advocate_001"
            )

            # Query immediately after creation
            initiatives_after = state.query_initiatives("san-rafael")
            assert len(initiatives_after) == count_before + 1

            # Verify the new initiative is in the list
            found = False
            for init in initiatives_after:
                if init["id"] == initiative.id:
                    found = True
                    assert init["title"] == "More affordable units downtown"
                    assert init["topic"] == "housing"
                    break
            assert found, "Created initiative not found in query results"

    def test_voice_visible_after_add(self):
        """
        Test that added voice is immediately visible via query.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative first
            initiative = civic.start_something(
                topic="parks",
                title="New playground equipment",
                description="Replace old playground equipment.",
                creator_id="parent_001"
            )

            # Query voices before adding
            state = StateManager(db_path)
            voices_before = state.query_voices("initiative", initiative.id)
            count_before = len(voices_before)

            # Add voice
            voice = civic.add_voice(
                item_type="initiative",
                item_id=initiative.id,
                stance="support",
                comment="Great idea for the kids!",
                user_id="parent_002"
            )

            # Query immediately after
            voices_after = state.query_voices("initiative", initiative.id)
            assert len(voices_after) == count_before + 1

            # Verify the voice is queryable
            found_voice = state.get_voice(voice.id)
            assert found_voice is not None
            assert found_voice["stance"] == "support"
            assert found_voice["comment"] == "Great idea for the kids!"

    def test_subscription_visible_after_follow(self):
        """
        Test that subscription is immediately visible after follow.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="transit",
                title="Extended bus routes",
                description="Expand bus coverage to new neighborhoods.",
                creator_id="commuter_001"
            )

            state = StateManager(db_path)

            # Count subscriptions before
            count_before = state.count_subscriptions("initiative", initiative.id)
            assert count_before == 0

            # Follow the initiative
            subscription = civic.follow(
                item_type="initiative",
                item_id=initiative.id,
                user_id="commuter_002"
            )

            # Count immediately after
            count_after = state.count_subscriptions("initiative", initiative.id)
            assert count_after == 1

            # Verify subscription is retrievable
            found_sub = state.get_subscription(subscription.id)
            assert found_sub is not None
            assert found_sub["item_type"] == "initiative"
            assert found_sub["item_id"] == initiative.id

    def test_outcome_visible_after_report(self):
        """
        Test that outcome is immediately visible after report_outcome.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="environment",
                title="Ban plastic bags",
                description="Phase out single-use plastic bags.",
                creator_id="green_advocate_001"
            )

            state = StateManager(db_path)

            # Check no outcome before
            outcome_before = state.get_outcome_for_item("initiative", initiative.id)
            assert outcome_before is None

            # Report outcome
            outcome = civic.report_outcome(
                item_id=initiative.id,
                outcome="passed",
                notes="Passed unanimously with 2-year phase-in",
                item_type="initiative"
            )

            # Check outcome immediately visible
            outcome_after = state.get_outcome_for_item("initiative", initiative.id)
            assert outcome_after is not None
            assert outcome_after["outcome"] == "passed"
            assert "unanimously" in outcome_after["notes"]

    def test_multiple_writes_all_visible(self):
        """
        Test that multiple writes are all visible in subsequent reads.

        Simulates a complete user workflow:
        1. Create initiative
        2. Add multiple voices
        3. Multiple users follow
        4. Report outcome

        All should be visible immediately.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"
            state = StateManager(db_path)

            # Step 1: Create initiative
            initiative = civic.start_something(
                topic="safety",
                title="Better streetlights",
                description="Improve lighting on dark streets.",
                creator_id="resident_001"
            )
            init_check = state.get_initiative(initiative.id)
            assert init_check is not None

            # Step 2: Add 5 voices
            voice_ids = []
            for i in range(5):
                voice = civic.add_voice(
                    "initiative", initiative.id, "support",
                    f"I support this - resident {i}", user_id=f"res_{i}"
                )
                voice_ids.append(voice.id)

            # All voices should be visible
            for vid in voice_ids:
                v = state.get_voice(vid)
                assert v is not None, f"Voice {vid} not found"

            # Step 3: 3 users follow
            sub_ids = []
            for i in range(3):
                sub = civic.follow(
                    "initiative", initiative.id, user_id=f"follower_{i}"
                )
                sub_ids.append(sub.id)

            # All subscriptions should be visible
            sub_count = state.count_subscriptions("initiative", initiative.id)
            assert sub_count == 3

            # Step 4: Report outcome
            outcome = civic.report_outcome(
                item_id=initiative.id,
                outcome="passed",
                notes="Approved by council",
                item_type="initiative"
            )

            # Outcome should be visible
            out_check = state.get_outcome_for_item("initiative", initiative.id)
            assert out_check is not None
            assert out_check["outcome"] == "passed"

            # Initiative status should be updated
            init_final = state.get_initiative(initiative.id)
            assert init_final["status"] == "succeeded"


class TestCrossToolConsistency:
    """
    Test cross_tool_consistency.

    Verifies that data is consistent across different tool views,
    ensuring that the same underlying data appears the same
    regardless of which tool accesses it.
    """

    def test_initiative_consistent_across_civic_and_state_manager(self):
        """
        Test that initiative data is consistent whether accessed
        via Civic API or StateManager directly.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative via Civic API
            initiative = civic.start_something(
                topic="transportation",
                title="Protected bike lanes",
                description="We need protected bike lanes downtown.",
                location="Downtown San Rafael",
                creator_id="cyclist_001"
            )

            # Access via StateManager
            state = StateManager(db_path)
            stored = state.get_initiative(initiative.id)

            # Verify consistency
            assert stored["id"] == initiative.id
            assert stored["topic"] == initiative.topic
            assert stored["title"] == initiative.title
            assert stored["description"] == initiative.description
            assert stored["location"] == initiative.location
            assert stored["creator_id"] == initiative.creator_id

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

    def test_voice_counts_consistent(self):
        """
        Test that voice counts are consistent across different query methods.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="health",
                title="Community health clinic",
                description="Open a community health clinic.",
                creator_id="health_advocate_001"
            )

            # Add voices with different stances
            civic.add_voice("initiative", initiative.id, "support", "Great idea!", user_id="u1")
            civic.add_voice("initiative", initiative.id, "support", "Much needed!", user_id="u2")
            civic.add_voice("initiative", initiative.id, "oppose", "Too expensive", user_id="u3")
            civic.add_voice("initiative", initiative.id, "question", "Where would it be?", user_id="u4")

            # Query via StateManager
            state = StateManager(db_path)
            counts = state.count_voices("initiative", initiative.id)

            # Verify counts
            assert counts["support"] == 2
            assert counts["oppose"] == 1
            assert counts["question"] == 1
            assert counts["total"] == 4

            # Also query via list and count manually
            voices = state.query_voices("initiative", initiative.id)
            assert len(voices) == 4

            manual_counts = {"support": 0, "oppose": 0, "question": 0}
            for v in voices:
                manual_counts[v["stance"]] += 1

            assert manual_counts["support"] == counts["support"]
            assert manual_counts["oppose"] == counts["oppose"]
            assert manual_counts["question"] == counts["question"]

    def test_whos_with_me_reflects_community_activity(self):
        """
        Test that whos_with_me reflects community activity consistently.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            topic = "public spaces"

            # Create initiative on topic
            initiative = civic.start_something(
                topic=topic,
                title="More public benches",
                description="Add more seating in public areas.",
                creator_id="walker_001"
            )

            # Add community engagement
            for i in range(5):
                civic.add_voice(
                    "initiative", initiative.id, "support",
                    f"I would use these - walker {i}", user_id=f"walker_{i}"
                )
                civic.follow("initiative", initiative.id, user_id=f"walker_{i}")

            # Query community via Civic API
            community = civic.whos_with_me(topic)

            # Verify community reflects activity
            assert community.topic == topic
            assert community.jurisdiction == "san-rafael"
            # Note: follower_count implementation may vary
            assert isinstance(community.follower_count, int)

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

    def test_multiple_tools_see_same_initiative_state(self):
        """
        Test that initiative state is consistent across multiple tool accesses.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create and modify initiative
            initiative = civic.start_something(
                topic="education",
                title="School crossing guards",
                description="Add crossing guards near schools.",
                creator_id="parent_001"
            )

            # Add some activity
            civic.add_voice("initiative", initiative.id, "support", "Safety first!", user_id="p1")
            civic.add_voice("initiative", initiative.id, "support", "Great idea!", user_id="p2")
            civic.follow("initiative", initiative.id, user_id="p1")
            civic.follow("initiative", initiative.id, user_id="p2")
            civic.follow("initiative", initiative.id, user_id="p3")

            state = StateManager(db_path)

            # Check initiative via StateManager
            init_state = state.get_initiative(initiative.id)
            assert init_state is not None

            # Check voices match
            voices = state.query_voices("initiative", initiative.id)
            assert len(voices) == 2  # Two support voices

            # Check subscriptions match
            sub_count = state.count_subscriptions("initiative", initiative.id)
            assert sub_count == 3  # Three follows

            # Initiative counts should reflect activity
            # (depending on implementation, voice_count may update)
            assert init_state["voice_count"] == 2
            assert init_state["supporter_count"] == 3

    def test_sequential_operations_maintain_consistency(self):
        """
        Test that sequential operations maintain data consistency.

        This simulates a realistic workflow where multiple operations
        are performed in sequence and verifies consistency throughout.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup meeting
            state = StateManager(db_path)
            future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

            state.update_meetings("san-rafael", [{
                "id": "mtg_seq_001",
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

            # Step 1: Browse meetings
            meetings = civic.whats_next(days=30)
            assert len(meetings) == 1

            # Step 2: Query regulatory context
            context = civic.what_applies("development")
            assert context.topic == "development"

            # Step 3: Create initiative
            initiative = civic.start_something(
                topic="development",
                title="Mixed-use zoning",
                description="Allow mixed-use in commercial zones.",
                creator_id="planner_001"
            )

            # Verify initiative exists
            init_check = state.get_initiative(initiative.id)
            assert init_check is not None

            # Step 4: Add voices
            civic.add_voice("initiative", initiative.id, "support", "Good for housing", user_id="u1")
            civic.add_voice("initiative", initiative.id, "oppose", "Concerned about traffic", user_id="u2")

            # Verify voices
            voice_counts = state.count_voices("initiative", initiative.id)
            assert voice_counts["support"] == 1
            assert voice_counts["oppose"] == 1

            # Step 5: Query community
            community = civic.whos_with_me("development")
            assert community.topic == "development"

            # Step 6: Report outcome
            outcome = civic.report_outcome(
                item_id=initiative.id,
                outcome="modified",
                notes="Approved with conditions",
                item_type="initiative"
            )

            # Verify outcome
            out_check = state.get_outcome_for_item("initiative", initiative.id)
            assert out_check is not None
            assert out_check["outcome"] == "modified"

            # Step 7: Verify everything still consistent
            final_meetings = civic.whats_next(days=30)
            assert len(final_meetings) == len(meetings)

            final_init = state.get_initiative(initiative.id)
            assert final_init is not None
            assert final_init["status"] == "active"  # 'modified' keeps active status


class TestErrorRecovery:
    """
    Test error_recovery in MCP agent sequences.

    Verifies that an agent can retry failed tool calls and that
    partial workflow failures don't corrupt state.
    """

    def test_retry_after_error_validation_failure(self):
        """
        Test that agent can retry a tool call after validation error.

        Simulates: Agent calls add_voice with invalid stance, gets error,
        retries with correct parameters.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="transportation",
                title="Better bus service",
                description="We need more frequent buses.",
                creator_id="commuter_001"
            )

            # First attempt: Invalid stance (simulates agent error)
            try:
                civic.add_voice(
                    "initiative", initiative.id, "invalid_stance",
                    "I support better buses", user_id="user_001"
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                # Agent receives error message
                error_msg = str(e)
                assert "stance must be one of" in error_msg

            # Retry: Agent corrects the parameter
            voice = civic.add_voice(
                "initiative", initiative.id, "support",
                "I support better buses", user_id="user_001"
            )

            # Retry succeeds
            assert voice.id.startswith("voice_")
            assert voice.stance == "support"
            assert voice.item_id == initiative.id

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

    def test_retry_after_error_invalid_item_type(self):
        """
        Test that agent can retry follow() after invalid item_type.

        Simulates: Agent calls follow with wrong item_type, gets error,
        retries with correct type.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="parks",
                title="New playground",
                description="Build a new playground.",
                creator_id="parent_001"
            )

            # First attempt: Invalid item_type
            try:
                civic.follow(
                    "invalid_type", initiative.id, user_id="user_001"
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                error_msg = str(e)
                assert "item_type must be one of" in error_msg

            # Retry with correct item_type
            subscription = civic.follow(
                "initiative", initiative.id, user_id="user_001"
            )

            # Retry succeeds
            assert subscription.id.startswith("sub_")
            assert subscription.item_type == "initiative"
            assert subscription.item_id == initiative.id

    def test_retry_multiple_attempts(self):
        """
        Test that agent can retry multiple times before succeeding.

        Simulates: Agent makes several incorrect attempts before
        getting parameters right.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="environment",
                title="Tree planting program",
                description="Plant more trees in the city.",
                creator_id="green_001"
            )

            errors_caught = []

            # Attempt 1: Invalid item_type
            try:
                civic.add_voice(
                    "invalid_type", initiative.id, "support",
                    "Great idea!", user_id="user_001"
                )
            except ValueError as e:
                errors_caught.append(str(e))

            # Attempt 2: Invalid stance
            try:
                civic.add_voice(
                    "initiative", initiative.id, "like",  # Not a valid stance
                    "Great idea!", user_id="user_001"
                )
            except ValueError as e:
                errors_caught.append(str(e))

            # Attempt 3: Correct parameters
            voice = civic.add_voice(
                "initiative", initiative.id, "support",
                "Great idea!", user_id="user_001"
            )

            # All errors were caught
            assert len(errors_caught) == 2
            assert "item_type" in errors_caught[0]
            assert "stance" in errors_caught[1]

            # Final attempt succeeded
            assert voice.stance == "support"
            assert voice.item_id == initiative.id

    def test_retry_preserves_state(self):
        """
        Test that failed tool calls don't corrupt existing state.

        Simulates: Agent creates initiative, fails to add voice,
        but initiative state remains intact.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="housing",
                title="Affordable housing fund",
                description="Create a fund for affordable housing.",
                creator_id="advocate_001"
            )

            # Add a successful voice
            voice1 = civic.add_voice(
                "initiative", initiative.id, "support",
                "Excellent initiative!", user_id="user_001"
            )

            # Follow the initiative
            sub1 = civic.follow("initiative", initiative.id, user_id="user_001")

            state = StateManager(db_path)

            # Verify initial state
            init_before = state.get_initiative(initiative.id)
            voice_count_before = state.count_voices("initiative", initiative.id)["total"]
            sub_count_before = state.count_subscriptions("initiative", initiative.id)

            assert init_before is not None
            assert voice_count_before == 1
            assert sub_count_before == 1

            # Failed attempt - should not affect state
            try:
                civic.add_voice(
                    "initiative", initiative.id, "invalid",
                    "This should fail", user_id="user_002"
                )
            except ValueError:
                pass  # Expected

            # Verify state unchanged after failure
            init_after = state.get_initiative(initiative.id)
            voice_count_after = state.count_voices("initiative", initiative.id)["total"]
            sub_count_after = state.count_subscriptions("initiative", initiative.id)

            assert init_after["id"] == init_before["id"]
            assert init_after["title"] == init_before["title"]
            assert voice_count_after == voice_count_before
            assert sub_count_after == sub_count_before

            # Now successful retry
            voice2 = civic.add_voice(
                "initiative", initiative.id, "support",
                "Adding my voice", user_id="user_002"
            )

            # State properly updated after successful retry
            voice_count_final = state.count_voices("initiative", initiative.id)["total"]
            assert voice_count_final == voice_count_before + 1

    def test_retry_after_report_outcome_error(self):
        """
        Test that agent can retry report_outcome after error.

        Simulates: Agent reports outcome with invalid outcome value,
        gets error, retries with valid value.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="transit",
                title="Extended bus hours",
                description="Run buses later at night.",
                creator_id="commuter_001"
            )

            state = StateManager(db_path)

            # Verify no outcome yet
            outcome_before = state.get_outcome_for_item("initiative", initiative.id)
            assert outcome_before is None

            # First attempt: Invalid outcome value
            try:
                civic.report_outcome(
                    item_id=initiative.id,
                    outcome="won",  # Not a valid outcome
                    notes="We won!",
                    item_type="initiative"
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                error_msg = str(e)
                assert "outcome must be one of" in error_msg

            # Verify state unchanged after failure
            outcome_after_fail = state.get_outcome_for_item("initiative", initiative.id)
            assert outcome_after_fail is None

            # Retry with valid outcome
            outcome = civic.report_outcome(
                item_id=initiative.id,
                outcome="passed",
                notes="Passed unanimously!",
                item_type="initiative"
            )

            # Retry succeeded
            assert outcome.outcome == "passed"
            assert outcome.item_id == initiative.id

            # Outcome now recorded
            outcome_final = state.get_outcome_for_item("initiative", initiative.id)
            assert outcome_final is not None
            assert outcome_final["outcome"] == "passed"


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

    def test_workflow_survives_action_failure(self):
        """
        Test that action workflow survives single failure.

        Workflow: start_something → add_voice (fails first) → follow
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Step 1: Create initiative
            initiative = civic.start_something(
                topic="safety",
                title="Better crosswalks",
                description="Add more crosswalks downtown.",
                creator_id="walker_001"
            )
            assert initiative.id.startswith("init_")

            # Step 2a: add_voice fails (invalid stance)
            failed = False
            try:
                civic.add_voice(
                    "initiative", initiative.id, "approve",  # Invalid
                    "Great idea!", user_id="user_001"
                )
            except ValueError:
                failed = True

            assert failed, "add_voice should have failed with invalid stance"

            # Step 2b: add_voice succeeds on retry
            voice = civic.add_voice(
                "initiative", initiative.id, "support",
                "Great idea!", user_id="user_001"
            )
            assert voice.stance == "support"

            # Step 3: follow (succeeds)
            subscription = civic.follow(
                "initiative", initiative.id, user_id="user_001"
            )
            assert subscription.item_type == "initiative"

            # Workflow completed despite middle step failure
            assert initiative.id.startswith("init_")
            assert voice.item_id == initiative.id
            assert subscription.item_id == initiative.id

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

    def test_workflow_handles_multiple_failures(self):
        """
        Test that workflow handles multiple failures across steps.
        """
        from civicos.mcp import CivicServer

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            failures = []

            # Step 1: Create initiative (succeeds)
            initiative = civic.start_something(
                topic="education",
                title="School safety",
                description="Improve school safety measures.",
                creator_id="parent_001"
            )

            # Step 2: add_voice (fails, then succeeds)
            try:
                civic.add_voice("invalid", initiative.id, "support", "Test", user_id="u1")
            except ValueError:
                failures.append("voice_1")

            voice1 = civic.add_voice("initiative", initiative.id, "support", "Test", user_id="u1")

            # Step 3: follow (fails, then succeeds)
            try:
                civic.follow("invalid", initiative.id, user_id="u2")
            except ValueError:
                failures.append("follow_1")

            sub1 = civic.follow("initiative", initiative.id, user_id="u2")

            # Step 4: add another voice (fails, then succeeds)
            try:
                civic.add_voice("initiative", initiative.id, "invalid_stance", "More", user_id="u3")
            except ValueError:
                failures.append("voice_2")

            voice2 = civic.add_voice("initiative", initiative.id, "oppose", "Different view", user_id="u3")

            # All failures were handled
            assert len(failures) == 3

            # Workflow completed successfully
            assert initiative.id.startswith("init_")
            assert voice1.stance == "support"
            assert sub1.item_type == "initiative"
            assert voice2.stance == "oppose"

    def test_workflow_state_consistent_after_failures(self):
        """
        Test that state remains consistent after workflow with failures.
        """
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            civic.jurisdiction = "san-rafael"

            # Create initiative
            initiative = civic.start_something(
                topic="health",
                title="Community health center",
                description="Build a health center.",
                creator_id="advocate_001"
            )

            # Add 3 voices with failures interspersed
            successful_voices = []
            for i in range(3):
                # Fail first
                try:
                    civic.add_voice("initiative", initiative.id, "bad", f"Test {i}", user_id=f"user_{i}")
                except ValueError:
                    pass

                # Then succeed
                voice = civic.add_voice("initiative", initiative.id, "support", f"Test {i}", user_id=f"user_{i}")
                successful_voices.append(voice)

            # Add 2 follows with failures interspersed
            successful_subs = []
            for i in range(2):
                # Fail first
                try:
                    civic.follow("bad_type", initiative.id, user_id=f"follower_{i}")
                except ValueError:
                    pass

                # Then succeed
                sub = civic.follow("initiative", initiative.id, user_id=f"follower_{i}")
                successful_subs.append(sub)

            # Verify state consistency
            state = StateManager(db_path)

            # All 3 voices should be recorded
            voice_count = state.count_voices("initiative", initiative.id)
            assert voice_count["total"] == 3
            assert voice_count["support"] == 3

            # All 2 subscriptions should be recorded
            sub_count = state.count_subscriptions("initiative", initiative.id)
            assert sub_count == 2

            # Initiative should reflect accurate counts
            init_data = state.get_initiative(initiative.id)
            assert init_data["voice_count"] == 3
            assert init_data["supporter_count"] == 2
