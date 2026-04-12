"""Integration tests for internal MCP registry endpoints.

These tests verify the internal registry endpoints for CivicOS platform discovery.

To run:
    pytest packages/civicos-services/tests/test_internal_registry.py -v --override-ini="addopts="
"""

import pytest
from unittest.mock import patch, AsyncMock


class TestInternalRegistryUnit:
    """Unit tests for internal registry endpoints."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import create_app

        app = create_app()
        return TestClient(app)

    def test_internal_servers_list(self, client):
        """Test GET /api/mcp/internal/servers returns server list."""
        response = client.get("/api/mcp/internal/servers")
        assert response.status_code == 200

        data = response.json()
        assert "servers" in data
        assert "total_servers" in data
        assert "updated" in data
        assert data["total_servers"] == len(data["servers"])

        # Should have at least San Rafael
        server_ids = [s["jurisdiction_id"] for s in data["servers"]]
        assert "city-san-rafael" in server_ids

    def test_internal_servers_structure(self, client):
        """Test server response has correct structure and values."""
        response = client.get("/api/mcp/internal/servers")
        assert response.status_code == 200

        data = response.json()
        valid_levels = {"federal", "state", "county", "city", "school"}
        for server in data["servers"]:
            # Verify fields have meaningful values, not just existence
            assert server["jurisdiction_id"].count("-") >= 1  # e.g., "city-san-rafael"
            assert server["level"] in valid_levels
            assert len(server["display_name"]) > 0

            # Verify URL structure includes domain and correct suffixes
            assert server["mcp_endpoint"].endswith("/mcp")
            assert server["health_endpoint"].endswith("/health")
            assert "civicosproject.org" in server["mcp_endpoint"]

    def test_internal_server_levels_sorted(self, client):
        """Test servers are sorted by level (federal, state, county, city)."""
        response = client.get("/api/mcp/internal/servers")
        assert response.status_code == 200

        data = response.json()
        levels = [s["level"] for s in data["servers"]]

        # Check that levels appear in correct order
        level_order = {"federal": 0, "state": 1, "county": 2, "city": 3}
        for i in range(len(levels) - 1):
            assert level_order.get(levels[i], 99) <= level_order.get(levels[i + 1], 99)

    def test_internal_server_by_id(self, client):
        """Test GET /api/mcp/internal/servers/{jurisdiction_id}."""
        # First get list to find valid ID
        list_response = client.get("/api/mcp/internal/servers")
        assert list_response.status_code == 200
        servers = list_response.json()["servers"]

        if servers:
            jid = servers[0]["jurisdiction_id"]

            # Mock health check to avoid network calls
            with patch(
                "civicos_services.servers.routers.registry.check_internal_server_health",
                new_callable=AsyncMock
            ) as mock_health:
                from civicos_services.servers.routers.registry import InternalServerHealth
                mock_health.return_value = InternalServerHealth(
                    status="healthy",
                    tools_count=30,
                    tools=["tool1", "tool2"],
                    checked_at="2026-02-03T00:00:00Z",
                    response_time_ms=150,
                )

                response = client.get(f"/api/mcp/internal/servers/{jid}")
                assert response.status_code == 200

                data = response.json()
                assert data["jurisdiction_id"] == jid
                assert data["health"]["status"] == "healthy"
                assert data["health"]["tools_count"] == 30
                assert data["health"]["response_time_ms"] == 150

    def test_internal_server_not_found(self, client):
        """Test 404 for unknown jurisdiction."""
        response = client.get(
            "/api/mcp/internal/servers/city-nonexistent",
            params={"check_health": "false"}
        )
        assert response.status_code == 404

    def test_mcp_endpoint_building(self):
        """Test MCP endpoint URL building logic."""
        from civicos_services.servers.routers.registry import _build_mcp_endpoint

        # City
        assert _build_mcp_endpoint("city-san-rafael") == "https://san-rafael.civicosproject.org/mcp"
        assert _build_mcp_endpoint("city-berkeley") == "https://berkeley.civicosproject.org/mcp"

        # State
        assert _build_mcp_endpoint("state-california") == "https://california.civicosproject.org/mcp"

        # Federal (special case)
        assert _build_mcp_endpoint("country-united-states") == "https://federal.civicosproject.org/mcp"


class TestHealthAggregation:
    """Tests for health aggregation endpoint."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import create_app

        app = create_app()
        return TestClient(app)

    def test_aggregated_health_structure(self, client):
        """Test GET /api/mcp/internal/health response structure."""
        # Mock health checks
        with patch(
            "civicos_services.servers.routers.registry.check_internal_server_health",
            new_callable=AsyncMock
        ) as mock_health:
            from civicos_services.servers.routers.registry import InternalServerHealth
            mock_health.return_value = InternalServerHealth(
                status="healthy",
                tools_count=30,
                tools=["tool1"],
                checked_at="2026-02-03T00:00:00Z",
                response_time_ms=150,
            )

            response = client.get("/api/mcp/internal/health")
            assert response.status_code == 200

            data = response.json()
            # All servers should be healthy (mock returns healthy for all)
            assert data["total_servers"] > 0
            assert data["healthy"] == data["total_servers"]
            assert data["unhealthy"] == 0
            assert data["unknown"] == 0
            assert data["healthy"] + data["unhealthy"] + data["unknown"] == data["total_servers"]
            # Each mock returns tools_count=30
            assert data["total_tools"] == data["total_servers"] * 30
            assert len(data["servers"]) == data["total_servers"]
            assert data["updated"]  # Non-empty timestamp
            # Each server should report healthy with mock values
            for jid, health in data["servers"].items():
                assert health["status"] == "healthy"
                assert health["tools_count"] == 30
                assert health["response_time_ms"] == 150


class TestToolsIntrospection:
    """Tests for tools introspection endpoint."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import create_app

        app = create_app()
        return TestClient(app)

    def test_tools_response_structure(self, client):
        """Test GET /api/mcp/internal/tools response structure."""
        # Mock health checks
        with patch(
            "civicos_services.servers.routers.registry.check_internal_server_health",
            new_callable=AsyncMock
        ) as mock_health:
            from civicos_services.servers.routers.registry import InternalServerHealth

            # Return different tools for different servers
            def mock_health_side_effect(jid, endpoint):
                if "san-rafael" in endpoint:
                    return InternalServerHealth(
                        status="healthy",
                        tools_count=2,
                        tools=["search_meetings", "get_budget"],
                        checked_at="2026-02-03T00:00:00Z",
                        response_time_ms=150,
                    )
                elif "california" in endpoint:
                    return InternalServerHealth(
                        status="healthy",
                        tools_count=1,
                        tools=["search_legislation"],
                        checked_at="2026-02-03T00:00:00Z",
                        response_time_ms=200,
                    )
                else:
                    return InternalServerHealth(
                        status="unknown",
                        checked_at="2026-02-03T00:00:00Z",
                    )

            mock_health.side_effect = mock_health_side_effect

            response = client.get("/api/mcp/internal/tools")
            assert response.status_code == 200

            data = response.json()
            assert data["total_tools"] > 0
            assert data["total_tools"] == len(data["tools"])
            assert data["updated"]  # Non-empty timestamp

            # Build lookup for verifying mock-provided tool data
            tool_by_name = {t["name"]: t for t in data["tools"]}

            # Verify specific tools injected by mock
            assert "search_meetings" in tool_by_name
            assert "get_budget" in tool_by_name
            assert "search_legislation" in tool_by_name

            # Verify jurisdiction mapping matches mock side_effect
            sr_tool = tool_by_name["search_meetings"]
            assert any("san-rafael" in jid for jid in sr_tool["available_at"])
            assert "city" in sr_tool["levels"]

            ca_tool = tool_by_name["search_legislation"]
            assert any("california" in jid for jid in ca_tool["available_at"])
            assert "state" in ca_tool["levels"]

            # Each tool should have non-empty availability
            for tool in data["tools"]:
                assert len(tool["name"]) > 0
                assert len(tool["available_at"]) > 0
