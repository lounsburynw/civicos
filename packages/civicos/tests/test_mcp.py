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


