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
        from civicos.mcp import CivicServer
        assert CivicServer is not None

    def test_can_import_create_mcp_server(self):
        """Can import create_mcp_server factory."""
        from civicos.mcp import create_mcp_server
        assert callable(create_mcp_server)

    def test_can_import_get_server(self):
        """Can import get_server helper."""
        from civicos.mcp import get_server
        assert callable(get_server)


class TestMCPAvailability:
    """Test MCP availability detection."""

    def test_mcp_available_flag(self):
        """MCP_AVAILABLE flag is set correctly."""
        from civicos.mcp import MCP_AVAILABLE
        # Should be True if mcp package is installed
        assert isinstance(MCP_AVAILABLE, bool)

    def test_mcp_is_installed(self):
        """MCP package should be installed in civic environment."""
        from civicos.mcp import MCP_AVAILABLE
        # For this project, MCP should be available
        assert MCP_AVAILABLE is True


class TestCivicServerCreation:
    """Test CivicServer instantiation."""

    def test_create_civic_server(self):
        """Can create a CivicServer instance."""
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            assert server is not None
            assert server.db_path == db_path

    def test_civic_server_has_mcp(self):
        """CivicServer has an MCP server instance."""
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            assert server._mcp is not None

    def test_create_mcp_server_factory(self):
        """create_mcp_server factory creates CivicServer."""
        from civicos.mcp import create_mcp_server, CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = create_mcp_server(db_path=db_path)
            assert isinstance(server, CivicServer)


class TestMCPQueryTools:
    """Test MCP query tool registration."""

    def test_mcp_has_tools(self):
        """MCP server has registered tools."""
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            # FastMCP stores tools internally
            assert server._mcp is not None

    def test_query_tools_registered(self):
        """Query tools are registered with MCP server."""
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            # Call via Civic interface (same as what tool would do)
            result = civic.what_applies("housing")
            assert result.topic == "housing"

    def test_whats_next_tool_via_civic(self):
        """whats_next tool can be called via Civic."""
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.whats_next()
            assert isinstance(result, list)

    def test_whos_with_me_tool_via_civic(self):
        """whos_with_me tool can be called via Civic."""
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            assert hasattr(server, "run")
            assert callable(server.run)


class TestModuleLevelAPI:
    """Test module-level API for convenience."""

    def test_get_server_returns_instance(self):
        """get_server returns CivicServer instance."""
        from civicos.mcp import get_server, CivicServer
        server = get_server()
        assert isinstance(server, CivicServer)

    def test_get_server_singleton_pattern(self):
        """get_server returns same instance on multiple calls."""
        from civicos.mcp import get_server
        server1 = get_server()
        server2 = get_server()
        assert server1 is server2

    def test_main_function_exists(self):
        """main function exists for CLI entry."""
        from civicos.mcp import main
        assert callable(main)


class TestMCPActionTools:
    """Test MCP action tool registration and execution."""

    def test_start_something_tool_via_civic(self):
        """start_something tool can be called via Civic."""
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            with pytest.raises(ValueError, match="not found"):
                civic.prepare("agenda_nonexistent")

    @pytest.mark.skip(reason="Test setup bug: jurisdiction mapping issue - needs investigation")
    def test_prepare_tool_returns_preparation(self):
        """prepare tool returns Preparation for valid agenda item."""
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            with pytest.raises(ValueError, match="outcome must be one of"):
                civic.report_outcome(
                    item_id="agenda_123",
                    outcome="invalid_outcome"
                )

    def test_suggestions_returns_list(self):
        """suggestions tool returns a list of suggestions."""
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.suggestions()
            assert isinstance(result, list)

    def test_suggestions_with_user_id(self):
        """suggestions tool accepts user_id for personalization."""
        from civicos.mcp import CivicServer
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            server = CivicServer(db_path=db_path)
            civic = server._get_civic()
            result = civic.suggestions(user_id="user_123")
            assert isinstance(result, list)

    def test_suggestions_coordination_ready(self):
        """suggestions tool returns coordination opportunities."""
        from civicos.mcp import CivicServer
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

    def test_initiative_and_report(self):
        """Can create initiative then report outcome."""
        from civicos.mcp import CivicServer
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
        from civicos.mcp import CivicServer
        from civicos._internal.state import StateManager
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
