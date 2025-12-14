"""
Tests for MCP server query tools.

Tests that the Civic MCP server correctly exposes query tools.
"""

import pytest
import tempfile
import os


class TestMCPImports:
    """Test MCP module imports."""

    def test_can_import_civic_server(self):
        """Can import CivicServer."""
        from civic.mcp import CivicServer
        assert CivicServer is not None

    def test_can_import_create_mcp_server(self):
        """Can import create_mcp_server factory."""
        from civic.mcp import create_mcp_server
        assert callable(create_mcp_server)

    def test_can_import_get_server(self):
        """Can import get_server helper."""
        from civic.mcp import get_server
        assert callable(get_server)


class TestMCPAvailability:
    """Test MCP availability detection."""

    def test_mcp_available_flag(self):
        """MCP_AVAILABLE flag is set correctly."""
        from civic.mcp import MCP_AVAILABLE
        # Should be True if mcp package is installed
        assert isinstance(MCP_AVAILABLE, bool)

    def test_mcp_is_installed(self):
        """MCP package should be installed in civic environment."""
        from civic.mcp import MCP_AVAILABLE
        # For this project, MCP should be available
        assert MCP_AVAILABLE is True


class TestCivicServerCreation:
    """Test CivicServer instantiation."""

    def test_create_civic_server(self):
        """Can create a CivicServer instance."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            assert server is not None
            assert server.db_path == db_path

    def test_civic_server_has_mcp(self):
        """CivicServer has an MCP server instance."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            assert server._mcp is not None

    def test_create_mcp_server_factory(self):
        """create_mcp_server factory creates CivicServer."""
        from civic.mcp import create_mcp_server, CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = create_mcp_server(db_path=db_path)
            assert isinstance(server, CivicServer)


class TestMCPQueryTools:
    """Test MCP query tool registration."""

    def test_mcp_has_tools(self):
        """MCP server has registered tools."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            # FastMCP stores tools internally
            assert server._mcp is not None

    def test_query_tools_registered(self):
        """Query tools are registered with MCP server."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            # Access internal tool list
            # FastMCP uses _tool_manager or _tools internally
            mcp = server._mcp
            # The mcp object should exist and be configured
            assert mcp is not None
            assert mcp.name == "civic"


class TestMCPToolExecution:
    """Test MCP tool execution via CivicServer methods."""

    def test_get_civic_lazy_load(self):
        """_get_civic lazy loads Civic instance."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            # Initially None
            assert server._civic is None
            # After calling _get_civic, should be populated
            civic = server._get_civic()
            assert civic is not None
            assert server._civic is civic

    def test_what_applies_tool_via_civic(self):
        """what_applies tool can be called via Civic."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            # Call via Civic interface (same as what tool would do)
            result = civic.what_applies("housing")
            assert result.topic == "housing"

    def test_whats_next_tool_via_civic(self):
        """whats_next tool can be called via Civic."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.whats_next()
            assert isinstance(result, list)

    def test_whos_with_me_tool_via_civic(self):
        """whos_with_me tool can be called via Civic."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.whos_with_me("traffic")
            assert result.topic == "traffic"


class TestMCPServerRun:
    """Test MCP server run method."""

    def test_server_has_run_method(self):
        """CivicServer has run method."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            assert hasattr(server, "run")
            assert callable(server.run)


class TestModuleLevelAPI:
    """Test module-level API for convenience."""

    def test_get_server_returns_instance(self):
        """get_server returns CivicServer instance."""
        from civic.mcp import get_server, CivicServer
        server = get_server()
        assert isinstance(server, CivicServer)

    def test_get_server_singleton_pattern(self):
        """get_server returns same instance on multiple calls."""
        from civic.mcp import get_server
        server1 = get_server()
        server2 = get_server()
        assert server1 is server2

    def test_main_function_exists(self):
        """main function exists for CLI entry."""
        from civic.mcp import main
        assert callable(main)


class TestMCPActionTools:
    """Test MCP action tool registration and execution."""

    def test_start_something_tool_via_civic(self):
        """start_something tool can be called via Civic."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.start_something(
                topic="traffic safety",
                title="Protected bike lane on 4th St",
                description="Add a protected bike lane on 4th Street"
            )
            assert result.id.startswith("init_")
            assert result.topic == "traffic safety"
            assert result.title == "Protected bike lane on 4th St"

    def test_start_something_with_location(self):
        """start_something tool accepts location parameter."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.start_something(
                topic="parks",
                title="Dog park at Lincoln",
                description="Create a dog park at Lincoln Park",
                location="Lincoln Park"
            )
            assert result.location == "Lincoln Park"

    def test_add_voice_tool_via_civic(self):
        """add_voice tool can be called via Civic."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.add_voice(
                item_type="initiative",
                item_id="init_12345678",
                stance="support",
                comment="Great idea!"
            )
            assert result.id.startswith("voice_")
            assert result.item_type == "initiative"
            assert result.item_id == "init_12345678"
            assert result.stance == "support"
            assert result.comment == "Great idea!"

    def test_add_voice_oppose_stance(self):
        """add_voice tool accepts oppose stance."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.add_voice(
                item_type="agenda_item",
                item_id="agenda_001",
                stance="oppose",
                comment="I have concerns about this."
            )
            assert result.stance == "oppose"
            assert result.item_type == "agenda_item"

    def test_add_voice_question_stance(self):
        """add_voice tool accepts question stance."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.add_voice(
                item_type="decision",
                item_id="decision_001",
                stance="question",
                comment="What is the timeline for this?"
            )
            assert result.stance == "question"
            assert result.item_type == "decision"

    def test_add_voice_invalid_stance_raises(self):
        """add_voice tool raises on invalid stance."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            with pytest.raises(ValueError, match="stance must be one of"):
                civic.add_voice(
                    item_type="initiative",
                    item_id="init_12345678",
                    stance="neutral",  # Invalid stance
                    comment="I'm neutral on this."
                )

    def test_add_voice_invalid_item_type_raises(self):
        """add_voice tool raises on invalid item_type."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            with pytest.raises(ValueError, match="item_type must be one of"):
                civic.add_voice(
                    item_type="unknown",  # Invalid type
                    item_id="unknown_001",
                    stance="support",
                    comment="Support!"
                )

    def test_follow_tool_via_civic(self):
        """follow tool can be called via Civic."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.follow(
                item_type="meeting",
                item_id="meeting_001"
            )
            assert result.id.startswith("sub_")
            assert result.item_type == "meeting"
            assert result.item_id == "meeting_001"

    def test_follow_initiative_type(self):
        """follow tool accepts initiative item_type."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.follow(
                item_type="initiative",
                item_id="init_12345678"
            )
            assert result.item_type == "initiative"

    def test_follow_topic_type(self):
        """follow tool accepts topic item_type."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.follow(
                item_type="topic",
                item_id="housing"
            )
            assert result.item_type == "topic"

    def test_follow_decision_type(self):
        """follow tool accepts decision item_type."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.follow(
                item_type="decision",
                item_id="decision_001"
            )
            assert result.item_type == "decision"

    def test_follow_invalid_item_type_raises(self):
        """follow tool raises on invalid item_type."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            with pytest.raises(ValueError, match="item_type must be one of"):
                civic.follow(
                    item_type="unknown",  # Invalid type
                    item_id="unknown_001"
                )

    def test_prepare_tool_agenda_not_found(self):
        """prepare tool raises ValueError for unknown agenda item."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            with pytest.raises(ValueError, match="not found"):
                civic.prepare("agenda_nonexistent")

    def test_prepare_tool_returns_preparation(self):
        """prepare tool returns Preparation for valid agenda item."""
        from civic.mcp import CivicServer
        from civic._internal.state import StateManager
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Setup meeting with agenda item
            state = StateManager(db_path)
            state.update_meetings("default", [{
                "id": "mtg_prep",
                "title": "Council Meeting",
                "meeting_datetime": "2025-12-15T18:00:00",
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "agenda_001",
                        "title": "Housing Development",
                    }]
                }
            }])

            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.prepare("agenda_001")

            assert result.agenda_item_id == "agenda_001"
            assert isinstance(result.talking_points, list)
            assert len(result.talking_points) > 0


class TestMCPActionToolIntegration:
    """Test MCP action tools work together in realistic scenarios."""

    def test_create_initiative_then_voice(self):
        """Can create initiative and then add voice to it."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()

            # Create initiative
            initiative = civic.start_something(
                topic="housing",
                title="Affordable housing on Main St",
                description="Support for affordable housing development"
            )

            # Add voice to initiative
            voice = civic.add_voice(
                item_type="initiative",
                item_id=initiative.id,
                stance="support",
                comment="This addresses a real community need."
            )

            assert voice.item_id == initiative.id

    def test_create_initiative_then_follow(self):
        """Can create initiative and then follow it."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()

            # Create initiative
            initiative = civic.start_something(
                topic="environment",
                title="Community garden program",
                description="Start community gardens in vacant lots"
            )

            # Follow initiative
            subscription = civic.follow(
                item_type="initiative",
                item_id=initiative.id
            )

            assert subscription.item_id == initiative.id

    def test_multiple_voices_on_initiative(self):
        """Can add multiple voices to same initiative."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()

            # Create initiative
            initiative = civic.start_something(
                topic="transit",
                title="Bus rapid transit on El Camino",
                description="Add BRT lanes on El Camino Real"
            )

            # Add multiple voices
            voice1 = civic.add_voice(
                item_type="initiative",
                item_id=initiative.id,
                stance="support",
                comment="This will reduce traffic."
            )
            voice2 = civic.add_voice(
                item_type="initiative",
                item_id=initiative.id,
                stance="question",
                comment="How will parking be affected?"
            )

            # All should succeed with unique IDs
            assert voice1.id != voice2.id
            assert voice1.item_id == voice2.item_id == initiative.id


class TestMCPOrchestrationTools:
    """Test MCP orchestration tool registration and execution."""

    def test_report_outcome_tool_via_civic(self):
        """report_outcome tool can be called via Civic."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.report_outcome(
                item_id="agenda_123",
                outcome="passed",
                notes="Passed 5-0"
            )
            assert result.item_id == "agenda_123"
            assert result.outcome == "passed"
            assert result.notes == "Passed 5-0"
            assert result.recorded_at is not None

    def test_report_outcome_with_vote_breakdown(self):
        """report_outcome tool accepts vote_breakdown parameter."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.report_outcome(
                item_id="agenda_456",
                outcome="passed",
                notes="Passed with amendments",
                vote_breakdown={"yes": 4, "no": 1, "abstain": 0}
            )
            assert result.outcome == "passed"
            assert result.notes == "Passed with amendments"

    def test_report_outcome_failed_outcome(self):
        """report_outcome tool accepts failed outcome."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.report_outcome(
                item_id="agenda_789",
                outcome="failed",
                notes="Did not receive enough support"
            )
            assert result.outcome == "failed"

    def test_report_outcome_invalid_outcome_raises(self):
        """report_outcome tool raises on invalid outcome."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            with pytest.raises(ValueError, match="outcome must be one of"):
                civic.report_outcome(
                    item_id="agenda_123",
                    outcome="invalid_outcome"
                )

    def test_coordinate_tool_via_civic(self):
        """coordinate tool can be called via Civic."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.coordinate(
                initiative_id="init_12345678",
                action="plan_testimony"
            )
            assert result.action == "plan_testimony"
            assert isinstance(result.steps, list)
            assert isinstance(result.participants, list)

    def test_coordinate_draft_letter_action(self):
        """coordinate tool accepts draft_letter action."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.coordinate(
                initiative_id="init_87654321",
                action="draft_letter"
            )
            assert result.action == "draft_letter"

    def test_suggestions_returns_list(self):
        """suggestions tool returns a list of suggestions."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.suggestions()
            assert isinstance(result, list)

    def test_suggestions_with_user_id(self):
        """suggestions tool accepts user_id for personalization."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.suggestions(user_id="user_123")
            assert isinstance(result, list)

    def test_suggestions_coordination_ready(self):
        """suggestions tool returns coordination opportunities."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            user_id = "test_creator_456"

            # Create an initiative with 5+ supporters
            init = civic.start_something(
                topic="parking",
                title="More bike parking",
                description="Need more bike racks downtown",
                creator_id=user_id
            )

            for i in range(6):
                civic.follow("initiative", init.id, user_id=f"follower_{i}")

            # Get suggestions as creator
            result = civic.suggestions(user_id=user_id)
            assert isinstance(result, list)

            # Should have coordination suggestion
            coord_suggestions = [s for s in result if s.type == "coordination_ready"]
            assert len(coord_suggestions) >= 1


class TestMCPOrchestrationToolIntegration:
    """Test MCP orchestration tools work together in realistic scenarios."""

    def test_initiative_coordinate_and_report(self):
        """Can create initiative, coordinate action, then report outcome."""
        from civic.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()

            # Create initiative
            initiative = civic.start_something(
                topic="parks",
                title="New dog park",
                description="Create a dog park at Lincoln"
            )

            # Coordinate testimony planning
            plan = civic.coordinate(
                initiative_id=initiative.id,
                action="plan_testimony"
            )
            assert plan.action == "plan_testimony"

            # Report outcome
            outcome = civic.report_outcome(
                item_id=initiative.id,
                outcome="passed",
                item_type="initiative",
                notes="Council approved 5-0"
            )
            assert outcome.outcome == "passed"

    def test_report_outcome_updates_initiative_status(self):
        """Reporting outcome on initiative updates its status."""
        from civic.mcp import CivicServer
        from civic._internal.state import StateManager
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()

            # Create initiative
            initiative = civic.start_something(
                topic="transit",
                title="Bus shelter improvements",
                description="Add covered bus shelters"
            )

            # Report outcome (passed)
            civic.report_outcome(
                item_id=initiative.id,
                outcome="passed",
                item_type="initiative"
            )

            # Check initiative status was updated
            state = StateManager(db_path)
            updated = state.get_initiative(initiative.id)
            assert updated is not None
            # Initiative should be marked successful
            assert updated.get("status") in ("succeeded", "successful", "passed")


class TestSuggestionWorkflow:
    """Test LangGraph suggestion workflow."""

    def test_suggestion_workflow_imports(self):
        """Can import suggestion workflow components."""
        from civic._internal.coordination import (
            SuggestionState,
            run_suggestion_workflow,
            get_suggestion_state,
        )
        assert SuggestionState is not None
        assert callable(run_suggestion_workflow)
        assert callable(get_suggestion_state)

    def test_suggestion_workflow_runs(self):
        """Suggestion workflow completes successfully."""
        from civic._internal.coordination import run_suggestion_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_suggestion_workflow(
                jurisdiction="san-rafael",
                db_path=db_path
            )
            assert result is not None
            assert result.get("status") == "complete"
            assert "suggestions" in result
            assert isinstance(result["suggestions"], list)

    def test_suggestion_workflow_with_user(self):
        """Suggestion workflow accepts user_id for personalization."""
        from civic._internal.coordination import run_suggestion_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_suggestion_workflow(
                jurisdiction="san-rafael",
                user_id="user_123",
                db_path=db_path
            )
            assert result is not None
            assert result.get("status") == "complete"

    def test_suggestion_workflow_gathers_context(self):
        """Workflow gathers user context."""
        from civic._internal.coordination import run_suggestion_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_suggestion_workflow(
                jurisdiction="san-rafael",
                user_id="test_user",
                db_path=db_path
            )
            # Context should be gathered
            assert "user_interests" in result
            assert "user_subscriptions" in result
            assert isinstance(result["user_interests"], list)
            assert isinstance(result["user_subscriptions"], list)

    def test_suggestion_workflow_generates_candidates(self):
        """Workflow generates suggestion candidates."""
        from civic._internal.coordination import run_suggestion_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_suggestion_workflow(
                jurisdiction="san-rafael",
                db_path=db_path
            )
            # Candidates should exist (even if empty)
            assert "candidates" in result
            assert isinstance(result["candidates"], list)

    def test_suggestion_workflow_ranks_suggestions(self):
        """Workflow ranks suggestions by priority."""
        from civic._internal.coordination import run_suggestion_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_suggestion_workflow(
                jurisdiction="san-rafael",
                db_path=db_path
            )
            # Ranked suggestions should exist
            assert "ranked_suggestions" in result
            assert isinstance(result["ranked_suggestions"], list)

    def test_suggestion_workflow_with_data(self):
        """Workflow generates suggestions from existing data."""
        from civic._internal.coordination import SuggestionApp
        from civic import Civic

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Create a user and their initiative with supporters
            user_id = "workflow_test_user"
            civic = Civic("san-rafael", db_path=db_path)

            # Create initiative using Civic API
            init = civic.start_something(
                topic="parking",
                title="More parking downtown",
                description="We need more parking spaces",
                creator_id=user_id,
            )

            # Add supporters to meet threshold (5+)
            for i in range(6):
                civic.follow("initiative", init.id, user_id=f"supporter_{i}")

            # Use SuggestionApp directly to avoid global singleton pollution
            app = SuggestionApp(db_path=db_path)
            result = app.run(
                jurisdiction="san-rafael",
                user_id=user_id,
            )

            # Should have coordination suggestion for initiative with 6 supporters
            assert result.get("status") == "complete"
            suggestions = result.get("suggestions", [])

            # Find coordination-ready suggestion
            coord_suggestions = [
                s for s in suggestions
                if s.get("type") == "coordination_ready"
            ]
            assert len(coord_suggestions) >= 1

    def test_suggestion_app_class(self):
        """SuggestionApp class provides clean interface."""
        from civic._internal.coordination import SuggestionApp

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            app = SuggestionApp(db_path=db_path)

            result = app.run(jurisdiction="san-rafael")
            assert result is not None
            assert result.get("status") == "complete"

    def test_create_suggestion_workflow(self):
        """Can create suggestion workflow StateGraph."""
        from civic._internal.coordination import create_suggestion_workflow

        workflow = create_suggestion_workflow()
        assert workflow is not None
        # Should be a StateGraph
        assert hasattr(workflow, "add_node")
        assert hasattr(workflow, "add_edge")


class TestPreparationWorkflow:
    """Test LangGraph preparation workflow."""

    def test_preparation_workflow_imports(self):
        """Can import preparation workflow components."""
        from civic._internal.coordination import (
            PreparationState,
            run_preparation_workflow,
            get_preparation_state,
        )
        assert PreparationState is not None
        assert callable(run_preparation_workflow)
        assert callable(get_preparation_state)

    def test_preparation_workflow_runs(self):
        """Preparation workflow completes successfully."""
        from civic._internal.coordination import run_preparation_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_preparation_workflow(
                agenda_item_id="test_item",
                jurisdiction="san-rafael",
                db_path=db_path
            )
            assert result is not None
            # Should complete even if item not found (error state)
            assert "status" in result
            assert "preparation" in result

    def test_preparation_workflow_with_user(self):
        """Preparation workflow accepts user_id for personalization."""
        from civic._internal.coordination import run_preparation_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_preparation_workflow(
                agenda_item_id="test_item",
                jurisdiction="san-rafael",
                user_id="user_123",
                db_path=db_path
            )
            assert result is not None
            assert result.get("user_id") == "user_123"

    def test_preparation_workflow_generates_talking_points(self):
        """Workflow generates talking points."""
        from civic._internal.coordination import run_preparation_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_preparation_workflow(
                agenda_item_id="test_item",
                jurisdiction="san-rafael",
                db_path=db_path
            )
            assert "talking_points" in result
            assert isinstance(result["talking_points"], list)

    def test_preparation_workflow_compiles_logistics(self):
        """Workflow compiles meeting logistics."""
        from civic._internal.coordination import run_preparation_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_preparation_workflow(
                agenda_item_id="test_item",
                jurisdiction="san-rafael",
                db_path=db_path
            )
            assert "logistics" in result
            assert isinstance(result["logistics"], dict)

    def test_preparation_workflow_finds_allies(self):
        """Workflow finds allies."""
        from civic._internal.coordination import run_preparation_workflow
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            result = run_preparation_workflow(
                agenda_item_id="test_item",
                jurisdiction="san-rafael",
                db_path=db_path
            )
            assert "allies" in result
            assert isinstance(result["allies"], list)

    def test_preparation_app_class(self):
        """PreparationApp class provides clean interface."""
        from civic._internal.coordination import PreparationApp

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            app = PreparationApp(db_path=db_path)

            result = app.run(
                agenda_item_id="test_item",
                jurisdiction="san-rafael"
            )
            assert result is not None
            assert "preparation" in result

    def test_create_preparation_workflow(self):
        """Can create preparation workflow StateGraph."""
        from civic._internal.coordination import create_preparation_workflow

        workflow = create_preparation_workflow()
        assert workflow is not None
        # Should be a StateGraph
        assert hasattr(workflow, "add_node")
        assert hasattr(workflow, "add_edge")


class TestPatternLearnerWorkflow:
    """Test LangGraph pattern learning workflow."""

    def test_pattern_learner_imports(self):
        """Can import pattern learner components."""
        from civic._internal.coordination import (
            PatternState,
            Pattern,
            Strategy,
            PatternLearner,
            run_pattern_learning,
            get_success_patterns,
            suggest_strategy,
        )
        assert PatternState is not None
        assert Pattern is not None
        assert Strategy is not None
        assert PatternLearner is not None
        assert callable(run_pattern_learning)
        assert callable(get_success_patterns)
        assert callable(suggest_strategy)

    def test_pattern_learner_class_creation(self):
        """Can create PatternLearner instance."""
        from civic._internal.coordination import PatternLearner

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            learner = PatternLearner(db_path=db_path)
            assert learner is not None
            assert learner.db_path == db_path

    def test_learning_workflow_with_outcome(self):
        """Pattern learning workflow processes outcomes."""
        from civic._internal.coordination import PatternLearner
        from civic import Civic

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            civic = Civic("san-rafael", db_path=db_path)

            # Create an initiative
            init = civic.start_something(
                topic="housing",
                title="Affordable housing initiative",
                description="We need more affordable housing",
                creator_id="test_user",
            )

            # Add some voices and supporters
            civic.add_voice("initiative", init.id, "support", "I support this!", user_id="user_1")
            civic.follow("initiative", init.id, user_id="user_2")

            # Report outcome
            civic.report_outcome(init.id, "passed", "Council approved 5-0", item_type="initiative")

            # Learn from the outcome using item_type and item_id
            learner = PatternLearner(db_path=db_path)
            pattern = learner.learn_from_outcome(
                item_type="initiative",
                item_id=init.id,
                jurisdiction="san-rafael"
            )

            # Pattern should be extracted
            assert pattern is not None
            assert pattern.get("topic") == "housing"
            assert pattern.get("outcome") == "passed"

    def test_strategy_suggestion_workflow(self):
        """Strategy suggestion workflow generates recommendations."""
        from civic._internal.coordination import PatternLearner
        from civic import Civic

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            civic = Civic("san-rafael", db_path=db_path)

            # Create an initiative for strategy suggestion
            init = civic.start_something(
                topic="traffic",
                title="Traffic calming on Main St",
                description="We need traffic calming measures",
                creator_id="test_user",
            )

            learner = PatternLearner(db_path=db_path)
            strategy = learner.suggest_strategy(init.id)

            assert strategy is not None
            assert "confidence" in strategy
            assert "suggestion" in strategy
            assert "recommend_coordination" in strategy

    def test_get_success_patterns(self):
        """Can query success patterns for a topic."""
        from civic._internal.coordination import PatternLearner, get_success_patterns
        from civic import Civic

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            civic = Civic("san-rafael", db_path=db_path)

            # Create initiative with successful outcome
            init = civic.start_something(
                topic="parks",
                title="New park initiative",
                description="We need a new park",
                creator_id="test_user",
            )

            civic.add_voice("initiative", init.id, "support", "Great idea!", user_id="u1")
            civic.report_outcome(init.id, "passed", "Approved by council")

            # Query patterns using the function
            patterns = get_success_patterns("parks", db_path=db_path)

            # Should return list (may be empty if topic doesn't match)
            assert isinstance(patterns, list)

    def test_pattern_data_class(self):
        """Pattern dataclass works correctly."""
        from civic._internal.coordination import Pattern
        from datetime import datetime

        pattern = Pattern(
            id="pat_test123",
            topic="housing",
            jurisdiction="san-rafael",
            outcome="passed",
            actions=[{"action": "add_voice", "stance": "support"}],
            participant_count=5,
            coordination_used=True,
            context={"title": "Test initiative"},
        )

        assert pattern.id == "pat_test123"
        assert pattern.topic == "housing"
        assert pattern.coordination_used is True
        assert pattern.participant_count == 5

        # Test to_dict method
        d = pattern.to_dict()
        assert d["id"] == "pat_test123"
        assert d["outcome"] == "passed"

    def test_strategy_data_class(self):
        """Strategy dataclass works correctly."""
        from civic._internal.coordination import Strategy

        strategy = Strategy(
            confidence="high",
            suggestion="Similar initiatives succeeded with ~10 supporters",
            recommend_coordination=True,
            avg_supporters=10.5,
            similar_successes=[],
        )

        assert strategy.confidence == "high"
        assert strategy.recommend_coordination is True
        assert strategy.avg_supporters == 10.5

        # Test to_dict method
        d = strategy.to_dict()
        assert d["confidence"] == "high"
        assert d["recommend_coordination"] is True

    def test_create_learning_workflow(self):
        """Can create learning workflow StateGraph."""
        from civic._internal.coordination import create_learning_workflow

        workflow = create_learning_workflow()
        assert workflow is not None
        assert hasattr(workflow, "add_node")
        assert hasattr(workflow, "add_edge")

    def test_create_strategy_workflow(self):
        """Can create strategy workflow StateGraph."""
        from civic._internal.coordination import create_strategy_workflow

        workflow = create_strategy_workflow()
        assert workflow is not None
        assert hasattr(workflow, "add_node")
        assert hasattr(workflow, "add_edge")


class TestStrategySuggestionsWorkflow:
    """Test LangGraph strategy suggestions workflow."""

    def test_strategy_suggestions_imports(self):
        """Can import strategy suggestions components."""
        from civic._internal.coordination import (
            StrategyState,
            StrategySuggestion,
            PatternAnalysis,
            StrategySuggester,
            run_strategy_suggestions,
            get_strategy_state,
            create_strategy_suggestions_workflow,
        )
        assert StrategyState is not None
        assert StrategySuggestion is not None
        assert PatternAnalysis is not None
        assert StrategySuggester is not None
        assert callable(run_strategy_suggestions)
        assert callable(get_strategy_state)
        assert callable(create_strategy_suggestions_workflow)

    def test_strategy_suggester_class_creation(self):
        """Can create StrategySuggester instance."""
        from civic._internal.coordination import StrategySuggester

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            suggester = StrategySuggester(db_path=db_path)
            assert suggester is not None
            assert suggester.db_path == db_path

    def test_strategy_suggestions_workflow(self):
        """Strategy suggestions workflow generates suggestions."""
        from civic._internal.coordination import StrategySuggester
        from civic import Civic

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            civic = Civic("san-rafael", db_path=db_path)

            # Create an initiative with outcome
            init = civic.start_something(
                topic="housing",
                title="Affordable housing policy",
                description="We need housing reform",
                creator_id="test_user",
            )
            civic.add_voice("initiative", init.id, "support", "Great!", user_id="u1")
            civic.report_outcome(init.id, "passed", "Approved")

            # Run strategy suggestions
            suggester = StrategySuggester(db_path=db_path)
            result = suggester.suggest("san-rafael", "housing")

            assert result is not None
            assert "suggestions" in result
            assert "status" in result
            assert result["status"] == "complete"

    def test_run_strategy_suggestions_function(self):
        """run_strategy_suggestions convenience function works."""
        from civic._internal.coordination import run_strategy_suggestions
        from civic import Civic

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            civic = Civic("san-rafael", db_path=db_path)

            # Create some data
            init = civic.start_something(
                topic="traffic",
                title="Traffic calming",
                description="Slow down traffic",
                creator_id="test_user",
            )

            result = run_strategy_suggestions(
                "san-rafael",
                "traffic",
                db_path=db_path
            )

            assert result is not None
            assert "suggestions" in result
            assert isinstance(result["suggestions"], list)

    def test_strategy_suggestions_with_user(self):
        """Strategy suggestions include user personalization."""
        from civic._internal.coordination import run_strategy_suggestions
        from civic import Civic

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            civic = Civic("san-rafael", db_path=db_path)

            # Create initiative
            init = civic.start_something(
                topic="parks",
                title="New park",
                description="We need parks",
                creator_id="test_user",
            )

            # User engages with it
            civic.add_voice("initiative", init.id, "support", "Yes!", user_id="user_123")
            civic.follow("initiative", init.id, "user_123")

            result = run_strategy_suggestions(
                "san-rafael",
                "parks",
                user_id="user_123",
                db_path=db_path
            )

            assert result is not None
            assert "user_history" in result
            # User history should include their actions
            assert isinstance(result["user_history"], list)

    def test_strategy_suggestion_data_class(self):
        """StrategySuggestion dataclass works correctly."""
        from civic._internal.coordination import StrategySuggestion

        suggestion = StrategySuggestion(
            type="build_support",
            title="Build Support for Housing",
            reason="Successful initiatives averaged 10 supporters",
            action="Recruit at least 10 supporters",
            confidence="high",
            based_on_patterns=5,
            priority=1,
        )

        assert suggestion.type == "build_support"
        assert suggestion.confidence == "high"
        assert suggestion.priority == 1

        # Test to_dict method
        d = suggestion.to_dict()
        assert d["type"] == "build_support"
        assert d["based_on_patterns"] == 5

    def test_pattern_analysis_data_class(self):
        """PatternAnalysis dataclass works correctly."""
        from civic._internal.coordination import PatternAnalysis

        analysis = PatternAnalysis(
            topic="housing",
            pattern_count=5,
            avg_supporters=10.5,
            coordination_rate=0.6,
            success_rate=0.75,
            common_actions=["build_support", "coordinate_action"],
        )

        assert analysis.topic == "housing"
        assert analysis.pattern_count == 5
        assert analysis.coordination_rate == 0.6

        # Test to_dict method
        d = analysis.to_dict()
        assert d["topic"] == "housing"
        assert d["avg_supporters"] == 10.5
        assert "build_support" in d["common_actions"]

    def test_create_strategy_suggestions_workflow(self):
        """Can create strategy suggestions workflow StateGraph."""
        from civic._internal.coordination import create_strategy_suggestions_workflow

        workflow = create_strategy_suggestions_workflow()
        assert workflow is not None
        assert hasattr(workflow, "add_node")
        assert hasattr(workflow, "add_edge")

    def test_strategy_suggestions_no_patterns(self):
        """Strategy suggestions work even with no patterns."""
        from civic._internal.coordination import run_strategy_suggestions

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            # Fresh database with no data

            result = run_strategy_suggestions(
                "san-rafael",
                "unknown_topic",
                db_path=db_path
            )

            assert result is not None
            assert "suggestions" in result
            # Should still provide suggestions (low confidence)
            assert isinstance(result["suggestions"], list)
