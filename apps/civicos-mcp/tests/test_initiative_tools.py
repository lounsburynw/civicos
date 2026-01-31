"""
Tests for MCP initiative tools (focal point creation and discovery).

These tools implement a permissionless coordination protocol:
- Users can specify their own relay (or use the default)
- Initiatives are cryptographically signed
- Two-step flow: prepare_initiative -> sign locally -> broadcast_initiative

Tests mock HTTP responses since tools call the REST API.
"""

import pytest
import sys

# Add paths for imports
sys.path.insert(0, "apps/civicos-mcp")


class MockCivic:
    """Mock CivicOS client for handler tests."""
    pass


class MockLogger:
    """Mock logger for handler tests."""
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def debug(self, msg): pass


def mock_validate_input(data):
    """Mock input validator that passes all inputs."""
    return True, data, None


class TestPrepareInitiativeHandler:
    """Test prepare_initiative handler (step 1 of initiative creation)."""

    def test_handler_exists(self):
        """Verify handler is defined and exported."""
        from tools import handlers
        assert hasattr(handlers, 'prepare_initiative')
        assert callable(handlers.prepare_initiative)

    def test_handler_signature(self):
        """Verify handler has correct signature."""
        from tools.handlers import prepare_initiative
        import inspect
        sig = inspect.signature(prepare_initiative)
        params = list(sig.parameters.keys())
        assert params == ['civic', 'jurisdiction', 'validate_input', 'logger', 'args']

    def test_tool_definition_exists(self):
        """Verify tool definition in registry."""
        from tools.registry import TOOL_DEFINITIONS
        assert 'prepare_initiative' in TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['prepare_initiative']
        assert 'description' in defn
        assert 'inputSchema' in defn
        assert set(defn['inputSchema']['required']) == {'topic', 'title', 'description'}
        # Should support optional location
        assert 'location' in defn['inputSchema']['properties']

    def test_returns_signing_instructions(self):
        """Handler returns message to sign and instructions."""
        from tools.handlers import prepare_initiative

        result = prepare_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "traffic safety",
                "title": "Protected bike lane on 4th St",
                "description": "Install protected bike lanes along 4th Street",
            },
        )

        # Should contain the message to sign
        assert "civicos:initiative:v1:" in result
        assert "traffic safety" in result
        assert "Protected bike lane" in result
        # Should contain signing instructions
        assert "Sign" in result
        assert "private key" in result.lower()
        # Should mention next step
        assert "broadcast_initiative" in result

    def test_returns_initiative_id(self):
        """Handler generates deterministic initiative ID."""
        from tools.handlers import prepare_initiative

        result = prepare_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "housing",
                "title": "Test Initiative",
                "description": "Test description",
            },
        )

        # Should contain initiative ID format
        assert "initiative:city-san-rafael:" in result

    def test_missing_fields_rejected(self):
        """Handler rejects missing required fields."""
        from tools.handlers import prepare_initiative

        # Missing topic
        result = prepare_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "title": "Test",
                "description": "Test description",
            },
        )
        assert "Error" in result

        # Missing title
        result = prepare_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "housing",
                "description": "Test description",
            },
        )
        assert "Error" in result

    def test_optional_location_included(self):
        """Handler includes optional location when provided."""
        from tools.handlers import prepare_initiative

        result = prepare_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "traffic safety",
                "title": "Speed bump on Main St",
                "description": "Install speed bumps to slow traffic",
                "location": "Main Street between 1st and 2nd Ave",
            },
        )

        assert "Main Street between 1st and 2nd Ave" in result


class TestBroadcastInitiativeHandler:
    """Test broadcast_initiative handler (step 2 of initiative creation)."""

    def test_handler_exists(self):
        """Verify handler is defined and exported."""
        from tools import handlers
        assert hasattr(handlers, 'broadcast_initiative')
        assert callable(handlers.broadcast_initiative)

    def test_handler_signature(self):
        """Verify handler has correct signature."""
        from tools.handlers import broadcast_initiative
        import inspect
        sig = inspect.signature(broadcast_initiative)
        params = list(sig.parameters.keys())
        assert params == ['civic', 'jurisdiction', 'validate_input', 'logger', 'args']

    def test_tool_definition_exists(self):
        """Verify tool definition in registry."""
        from tools.registry import TOOL_DEFINITIONS
        assert 'broadcast_initiative' in TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['broadcast_initiative']
        assert 'description' in defn
        assert 'inputSchema' in defn
        required = set(defn['inputSchema']['required'])
        assert required == {'topic', 'title', 'description', 'public_key', 'signature'}
        # Should support relay_urls array
        assert 'relay_urls' in defn['inputSchema']['properties']
        assert defn['inputSchema']['properties']['relay_urls']['type'] == 'array'

    def test_missing_fields_rejected(self):
        """Handler rejects missing required fields."""
        from tools.handlers import broadcast_initiative

        # Missing public_key
        result = broadcast_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "housing",
                "title": "Test",
                "description": "Test description",
                "signature": "0xabcd",
            },
        )
        assert "Error" in result

        # Missing signature
        result = broadcast_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "housing",
                "title": "Test",
                "description": "Test description",
                "public_key": "0x1234",
            },
        )
        assert "Error" in result

    def test_connection_error_handled(self):
        """Handler gracefully handles connection errors."""
        from tools.handlers import broadcast_initiative

        result = broadcast_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "housing",
                "title": "Test Initiative",
                "description": "Test description",
                "public_key": "03" + "a1" * 32,  # Mock public key
                "signature": "30" + "ab" * 35,  # Mock signature
            },
        )

        # Should fail gracefully when relay not reachable
        assert "Failed" in result or "unreachable" in result or "Error" in result

    def test_custom_relay_urls_used(self):
        """Handler uses custom relay URLs when provided."""
        from tools.handlers import broadcast_initiative

        result = broadcast_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "housing",
                "title": "Test Initiative",
                "description": "Test description",
                "public_key": "03" + "a1" * 32,
                "signature": "30" + "ab" * 35,
                "relay_urls": ["https://custom-relay.example.org"],
            },
        )

        # Should mention the custom relay in results
        assert "custom-relay.example.org" in result


class TestListInitiativesHandler:
    """Test list_initiatives handler."""

    def test_handler_exists(self):
        """Verify handler is defined and exported."""
        from tools import handlers
        assert hasattr(handlers, 'list_initiatives')
        assert callable(handlers.list_initiatives)

    def test_handler_signature(self):
        """Verify handler has correct signature."""
        from tools.handlers import list_initiatives
        import inspect
        sig = inspect.signature(list_initiatives)
        params = list(sig.parameters.keys())
        assert params == ['civic', 'jurisdiction', 'validate_input', 'logger', 'args']

    def test_tool_definition_exists(self):
        """Verify tool definition in registry."""
        from tools.registry import TOOL_DEFINITIONS
        assert 'list_initiatives' in TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['list_initiatives']
        assert 'description' in defn
        assert 'inputSchema' in defn
        # No required fields - all filters are optional
        assert 'required' not in defn['inputSchema'] or defn['inputSchema']['required'] == []
        # Should support filters
        props = defn['inputSchema']['properties']
        assert 'topic' in props
        assert 'status' in props
        assert 'relay_url' in props
        assert 'limit' in props
        # Status should be enum
        assert props['status']['enum'] == ['active', 'completed', 'failed']

    def test_connection_error_handled(self):
        """Handler gracefully handles connection errors."""
        from tools.handlers import list_initiatives

        result = list_initiatives(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={},
        )

        # Should fail gracefully when relay not reachable
        assert "Unable to connect" in result or "Error" in result

    def test_custom_relay_url_used(self):
        """Handler uses custom relay URL when provided."""
        from tools.handlers import list_initiatives

        result = list_initiatives(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={"relay_url": "https://custom-relay.example.org"},
        )

        # Should mention the custom relay in error message
        assert "custom-relay.example.org" in result


class TestInitiativeToolRegistration:
    """Test that initiative tools are properly registered."""

    def test_all_tools_in_registry(self):
        """All initiative tools should be in the registry."""
        from tools.registry import TOOL_DEFINITIONS

        initiative_tools = [
            'prepare_initiative',
            'broadcast_initiative',
            'list_initiatives',
        ]

        for tool_name in initiative_tools:
            assert tool_name in TOOL_DEFINITIONS, f"Missing: {tool_name}"

    def test_tools_exported_from_init(self):
        """All initiative handlers should be exported from __init__."""
        from tools import (
            prepare_initiative,
            broadcast_initiative,
            list_initiatives,
        )

        assert callable(prepare_initiative)
        assert callable(broadcast_initiative)
        assert callable(list_initiatives)

    def test_tool_count_includes_initiatives(self):
        """Total tool count should include initiative tools."""
        from tools.registry import TOOL_DEFINITIONS

        # 30 core + 5 voice + 3 initiative = 38 total
        assert len(TOOL_DEFINITIONS) >= 38, f"Expected at least 38 tools, got {len(TOOL_DEFINITIONS)}"


class TestTwoStepInitiativeFlow:
    """Test the prepare -> sign -> broadcast flow."""

    def test_prepare_returns_message_format(self):
        """Prepare should return a message in the correct format for signing."""
        from tools.handlers import prepare_initiative

        result = prepare_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "parks",
                "title": "New playground equipment",
                "description": "Install modern playground equipment at Central Park",
            },
        )

        # Message format: civicos:initiative:v1:{id}:{topic}:{title_hash}:{timestamp}
        assert "civicos:initiative:v1:" in result
        # Should contain code block with the message
        assert "```" in result
        # Should contain instructions
        assert "ECDSA" in result or "sign" in result.lower()

    def test_broadcast_requires_crypto_params(self):
        """Broadcast requires public_key and signature."""
        from tools.handlers import broadcast_initiative

        # Without crypto params, should error
        result = broadcast_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "parks",
                "title": "New playground equipment",
                "description": "Install modern playground equipment",
            },
        )

        assert "Error" in result

    def test_prepare_is_offline(self):
        """Prepare should work without network access (offline)."""
        from tools.handlers import prepare_initiative

        # This should succeed even with no network
        result = prepare_initiative(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "topic": "safety",
                "title": "Street lighting",
                "description": "Better lighting on dark streets",
            },
        )

        # Should succeed and return signing instructions
        assert "Error" not in result
        assert "Sign" in result


class TestPermissionlessDesign:
    """Test that initiative tools follow permissionless design principles."""

    def test_no_required_relay_url(self):
        """Relay URL should be optional on all tools."""
        from tools.registry import TOOL_DEFINITIONS

        for tool_name in ['list_initiatives']:
            defn = TOOL_DEFINITIONS[tool_name]
            required = defn['inputSchema'].get('required', [])
            assert 'relay_url' not in required, f"{tool_name} should not require relay_url"

        # broadcast_initiative uses relay_urls (array), also optional
        defn = TOOL_DEFINITIONS['broadcast_initiative']
        required = defn['inputSchema'].get('required', [])
        assert 'relay_urls' not in required

    def test_broadcast_supports_multiple_relays(self):
        """broadcast_initiative should support multiple relay URLs."""
        from tools.registry import TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['broadcast_initiative']
        assert 'relay_urls' in defn['inputSchema']['properties']
        assert defn['inputSchema']['properties']['relay_urls']['type'] == 'array'

    def test_prepare_needs_no_relay(self):
        """prepare_initiative should not have relay_url parameter."""
        from tools.registry import TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['prepare_initiative']
        props = defn['inputSchema']['properties']
        # Prepare is offline, no relay needed
        assert 'relay_url' not in props
        assert 'relay_urls' not in props
