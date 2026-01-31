"""
Tests for MCP coordination tools (voice counts, subscriptions, voice casting).

These tools implement a permissionless coordination protocol:
- Users can specify their own relay (or use the default)
- Voices are cryptographically signed
- Two-step voice flow: prepare_voice -> sign locally -> broadcast_voice

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


class TestGetVoiceCountsHandler:
    """Test get_voice_counts handler."""

    def test_handler_exists(self):
        """Verify handler is defined and exported."""
        from tools import handlers
        assert hasattr(handlers, 'get_voice_counts')
        assert callable(handlers.get_voice_counts)

    def test_handler_signature(self):
        """Verify handler has correct signature."""
        from tools.handlers import get_voice_counts
        import inspect
        sig = inspect.signature(get_voice_counts)
        params = list(sig.parameters.keys())
        assert params == ['civic', 'jurisdiction', 'validate_input', 'logger', 'args']

    def test_tool_definition_exists(self):
        """Verify tool definition in registry."""
        from tools.registry import TOOL_DEFINITIONS
        assert 'get_voice_counts' in TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['get_voice_counts']
        assert 'description' in defn
        assert 'inputSchema' in defn
        assert defn['inputSchema']['required'] == ['entity']
        # Should support relay_url parameter
        assert 'relay_url' in defn['inputSchema']['properties']

    def test_handler_returns_error_without_api(self):
        """Handler returns connection error when API not available."""
        from tools.handlers import get_voice_counts

        result = get_voice_counts(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={"entity": "decision:city-san-rafael:2026-01-15:item-5a"},
        )

        # Should fail gracefully when relay not reachable
        assert "Unable to connect" in result or "Error" in result

    def test_custom_relay_url_used(self):
        """Handler uses custom relay URL when provided."""
        from tools.handlers import get_voice_counts

        result = get_voice_counts(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "entity": "decision:city-san-rafael:2026-01-15:item-5a",
                "relay_url": "https://custom-relay.example.org",
            },
        )

        # Should mention the custom relay in error message
        assert "custom-relay.example.org" in result


class TestSubscribeToTopicHandler:
    """Test subscribe_to_topic handler."""

    def test_handler_exists(self):
        """Verify handler is defined and exported."""
        from tools import handlers
        assert hasattr(handlers, 'subscribe_to_topic')
        assert callable(handlers.subscribe_to_topic)

    def test_handler_signature(self):
        """Verify handler has correct signature."""
        from tools.handlers import subscribe_to_topic
        import inspect
        sig = inspect.signature(subscribe_to_topic)
        params = list(sig.parameters.keys())
        assert params == ['civic', 'jurisdiction', 'validate_input', 'logger', 'args']

    def test_tool_definition_exists(self):
        """Verify tool definition in registry."""
        from tools.registry import TOOL_DEFINITIONS
        assert 'subscribe_to_topic' in TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['subscribe_to_topic']
        assert 'description' in defn
        assert 'inputSchema' in defn
        assert set(defn['inputSchema']['required']) == {'topics', 'email'}
        # Should support relay_url parameter
        assert 'relay_url' in defn['inputSchema']['properties']

    def test_invalid_email_returns_error(self):
        """Handler rejects invalid email format."""
        from tools.handlers import subscribe_to_topic

        result = subscribe_to_topic(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={"topics": ["housing"], "email": "not-an-email"},
        )

        assert "Error: Invalid email" in result

    def test_empty_topics_returns_error(self):
        """Handler rejects empty topics list."""
        from tools.handlers import subscribe_to_topic

        result = subscribe_to_topic(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={"topics": [], "email": "user@example.com"},
        )

        assert "Error: Must provide at least one topic" in result

    def test_handler_returns_error_without_api(self):
        """Handler returns connection error when API not available."""
        from tools.handlers import subscribe_to_topic

        result = subscribe_to_topic(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={"topics": ["housing"], "email": "user@example.com"},
        )

        # Should fail gracefully when relay not reachable
        assert "Unable to connect" in result or "Error" in result


class TestPrepareVoiceHandler:
    """Test prepare_voice handler (step 1 of voice casting)."""

    def test_handler_exists(self):
        """Verify handler is defined and exported."""
        from tools import handlers
        assert hasattr(handlers, 'prepare_voice')
        assert callable(handlers.prepare_voice)

    def test_tool_definition_exists(self):
        """Verify tool definition in registry."""
        from tools.registry import TOOL_DEFINITIONS
        assert 'prepare_voice' in TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['prepare_voice']
        assert 'description' in defn
        assert 'inputSchema' in defn
        assert set(defn['inputSchema']['required']) == {'entity', 'stance'}
        # Stance should be enum
        assert defn['inputSchema']['properties']['stance']['enum'] == ['support', 'oppose', 'watching']

    def test_returns_signing_instructions(self):
        """Handler returns message to sign and instructions."""
        from tools.handlers import prepare_voice

        result = prepare_voice(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "entity": "decision:city-san-rafael:2026-01-15:item-5a",
                "stance": "support",
            },
        )

        # Should contain the message to sign
        assert "civicos:voice:v1:" in result
        assert "decision:city-san-rafael:2026-01-15:item-5a" in result
        assert "support" in result
        # Should contain signing instructions
        assert "Sign" in result
        assert "private key" in result.lower()
        # Should mention next step
        assert "broadcast_voice" in result

    def test_invalid_stance_rejected(self):
        """Handler rejects invalid stance values."""
        from tools.handlers import prepare_voice

        result = prepare_voice(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "entity": "decision:city-san-rafael:2026-01-15:item-5a",
                "stance": "invalid_stance",
            },
        )

        assert "Error" in result
        assert "Invalid stance" in result


class TestBroadcastVoiceHandler:
    """Test broadcast_voice handler (step 2 of voice casting)."""

    def test_handler_exists(self):
        """Verify handler is defined and exported."""
        from tools import handlers
        assert hasattr(handlers, 'broadcast_voice')
        assert callable(handlers.broadcast_voice)

    def test_tool_definition_exists(self):
        """Verify tool definition in registry."""
        from tools.registry import TOOL_DEFINITIONS
        assert 'broadcast_voice' in TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['broadcast_voice']
        assert 'description' in defn
        assert 'inputSchema' in defn
        required = set(defn['inputSchema']['required'])
        assert required == {'entity', 'stance', 'public_key', 'signature'}
        # Should support relay_urls array
        assert 'relay_urls' in defn['inputSchema']['properties']
        assert defn['inputSchema']['properties']['relay_urls']['type'] == 'array'

    def test_missing_fields_rejected(self):
        """Handler rejects missing required fields."""
        from tools.handlers import broadcast_voice

        # Missing entity
        result = broadcast_voice(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "stance": "support",
                "public_key": "0x1234",
                "signature": "0xabcd",
            },
        )
        assert "Error" in result and "entity" in result

        # Missing signature
        result = broadcast_voice(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "entity": "decision:test",
                "stance": "support",
                "public_key": "0x1234",
            },
        )
        assert "Error" in result and "signature" in result

    def test_invalid_stance_rejected(self):
        """Handler rejects invalid stance values."""
        from tools.handlers import broadcast_voice

        result = broadcast_voice(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "entity": "decision:test",
                "stance": "invalid",
                "public_key": "0x1234",
                "signature": "0xabcd",
            },
        )

        assert "Error" in result
        assert "Invalid stance" in result

    def test_handler_returns_error_without_relay(self):
        """Handler returns connection error when relay not available."""
        from tools.handlers import broadcast_voice

        result = broadcast_voice(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "entity": "decision:city-san-rafael:2026-01-15:item-5a",
                "stance": "support",
                "public_key": "0x" + "a" * 64,
                "signature": "0x" + "b" * 128,
            },
        )

        # Should report failure to broadcast
        assert "Failed" in result or "unreachable" in result


class TestListRelaysHandler:
    """Test list_relays handler."""

    def test_handler_exists(self):
        """Verify handler is defined and exported."""
        from tools import handlers
        assert hasattr(handlers, 'list_relays')
        assert callable(handlers.list_relays)

    def test_tool_definition_exists(self):
        """Verify tool definition in registry."""
        from tools.registry import TOOL_DEFINITIONS
        assert 'list_relays' in TOOL_DEFINITIONS

        defn = TOOL_DEFINITIONS['list_relays']
        assert 'description' in defn
        # No required parameters
        assert defn['inputSchema']['properties'] == {}

    def test_returns_relay_list(self):
        """Handler returns list of known relays."""
        from tools.handlers import list_relays

        result = list_relays(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={},
        )

        # Should contain relay information
        assert "CivicOS" in result
        assert "relay" in result.lower()
        # Should explain permissionless nature
        assert "permissionless" in result.lower() or "your own" in result.lower()


class TestToolRegistry:
    """Test tool registry has coordination tools."""

    def test_registry_has_38_tools(self):
        """Verify tool count: 30 core + 5 voice + 3 initiative = 38."""
        from tools.registry import TOOL_DEFINITIONS
        assert len(TOOL_DEFINITIONS) == 38

    def test_coordination_tools_in_registry(self):
        """Verify all coordination tools are in registry."""
        from tools.registry import TOOL_DEFINITIONS
        coordination_tools = [
            'get_voice_counts',
            'subscribe_to_topic',
            'prepare_voice',
            'broadcast_voice',
            'list_relays',
        ]
        for tool in coordination_tools:
            assert tool in TOOL_DEFINITIONS, f"Missing tool: {tool}"

    def test_tool_registry_class_works(self):
        """Verify ToolRegistry class can load tools."""
        from tools.registry import ToolRegistry
        registry = ToolRegistry()
        assert len(registry) == 38
        assert registry.get_tool('get_voice_counts') is not None
        assert registry.get_tool('prepare_voice') is not None
        assert registry.get_tool('broadcast_voice') is not None
        assert registry.get_tool('list_relays') is not None


class TestExports:
    """Test module exports."""

    def test_handlers_exported_from_init(self):
        """Verify handlers are exported from tools/__init__.py."""
        from tools import (
            get_voice_counts,
            subscribe_to_topic,
            prepare_voice,
            broadcast_voice,
            list_relays,
        )
        assert callable(get_voice_counts)
        assert callable(subscribe_to_topic)
        assert callable(prepare_voice)
        assert callable(broadcast_voice)
        assert callable(list_relays)

    def test_all_list_includes_coordination_handlers(self):
        """Verify __all__ includes coordination handlers."""
        from tools import __all__
        coordination_handlers = [
            'get_voice_counts',
            'subscribe_to_topic',
            'prepare_voice',
            'broadcast_voice',
            'list_relays',
        ]
        for handler in coordination_handlers:
            assert handler in __all__, f"Missing from __all__: {handler}"


class TestPermissionlessDesign:
    """Test that the design supports permissionless operation."""

    def test_relay_url_is_optional(self):
        """All coordination tools should work without specifying relay_url."""
        from tools.registry import TOOL_DEFINITIONS

        # These tools support relay_url but don't require it
        tools_with_optional_relay = ['get_voice_counts', 'subscribe_to_topic', 'broadcast_voice']
        for tool in tools_with_optional_relay:
            defn = TOOL_DEFINITIONS[tool]
            required = defn['inputSchema'].get('required', [])
            assert 'relay_url' not in required, f"{tool} should not require relay_url"

    def test_prepare_voice_is_offline(self):
        """prepare_voice should work offline (no network call)."""
        from tools.handlers import prepare_voice

        # This should succeed without any network
        result = prepare_voice(
            civic=MockCivic(),
            jurisdiction="city-san-rafael",
            validate_input=mock_validate_input,
            logger=MockLogger(),
            args={
                "entity": "decision:test",
                "stance": "support",
            },
        )

        # Should return signing instructions, not an error
        assert "Error" not in result
        assert "Sign" in result

    def test_known_relays_defined(self):
        """At least one relay should be defined in KNOWN_RELAYS."""
        from tools.handlers import KNOWN_RELAYS

        assert len(KNOWN_RELAYS) >= 1
        # Should have a default relay
        defaults = [r for r in KNOWN_RELAYS if r.get('default')]
        assert len(defaults) == 1, "Exactly one relay should be marked as default"
