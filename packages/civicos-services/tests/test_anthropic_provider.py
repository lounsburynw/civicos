"""
Tests for anthropic_provider.py — Anthropic Claude LLM provider.

Pure-logic methods (_convert_tools_to_anthropic_format, _convert_message_format,
_convert_tool_choice_to_anthropic_format) are tested with real inputs and pinned
outputs. SDK-touching methods (complete, stream_complete, parse_tool_calls) mock
the anthropic.Anthropic boundary only.

To run:
    pytest packages/civicos-services/tests/test_anthropic_provider.py -q --override-ini="addopts="
"""

from unittest.mock import patch, MagicMock
import pytest

from civicos_services.providers.base import CompletionResponse, ToolCall


# ---------------------------------------------------------------------------
# Helpers — build a provider without hitting the real Anthropic API
# ---------------------------------------------------------------------------

def _make_provider(api_key="fake-key"):
    """Create an AnthropicProvider with a mocked Anthropic client."""
    with patch("civicos_services.providers.anthropic_provider.Anthropic") as mock_client_cls:
        from civicos_services.providers.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(api_key=api_key)
        # Anthropic() was constructed with the api_key
        mock_client_cls.assert_called_once_with(api_key=api_key)
    return provider


def _make_text_block(text):
    """Create a mock content block of type 'text'."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(block_id, name, input_dict):
    """Create a mock content block of type 'tool_use'."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = block_id
    block.name = name
    block.input = input_dict
    return block


def _make_message_response(
    content_blocks=None,
    stop_reason="end_turn",
    input_tokens=10,
    output_tokens=20,
):
    """Build a mock anthropic Message response object."""
    response = MagicMock()
    response.content = content_blocks or [_make_text_block("Hello")]
    response.stop_reason = stop_reason
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


# ---------------------------------------------------------------------------
# Properties and construction
# ---------------------------------------------------------------------------

class TestProperties:
    def test_name_is_anthropic(self):
        provider = _make_provider()
        assert provider.name == "anthropic"

    def test_default_model_is_claude_sonnet_4(self):
        provider = _make_provider()
        assert provider.default_model == "claude-sonnet-4-20250514"

    def test_api_key_stored(self):
        provider = _make_provider(api_key="my-key-123")
        assert provider.api_key == "my-key-123"

    def test_api_key_falls_back_to_env_var(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}, clear=False):
            with patch("civicos_services.providers.anthropic_provider.Anthropic") as mock_cls:
                from civicos_services.providers.anthropic_provider import AnthropicProvider
                provider = AnthropicProvider()
            mock_cls.assert_called_once_with(api_key="env-key")
            assert provider.api_key == "env-key"

    def test_explicit_api_key_overrides_env_var(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}, clear=False):
            with patch("civicos_services.providers.anthropic_provider.Anthropic"):
                from civicos_services.providers.anthropic_provider import AnthropicProvider
                provider = AnthropicProvider(api_key="explicit-key")
            assert provider.api_key == "explicit-key"


# ---------------------------------------------------------------------------
# _convert_tools_to_anthropic_format — pure logic
# ---------------------------------------------------------------------------

class TestConvertToolsToAnthropicFormat:
    def setup_method(self):
        self.provider = _make_provider()

    def test_single_tool_conversion(self):
        tools = [{
            "name": "search_events",
            "description": "Search civic events",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        }]
        result = self.provider._convert_tools_to_anthropic_format(tools)
        assert len(result) == 1
        assert result[0]["name"] == "search_events"
        assert result[0]["description"] == "Search civic events"
        assert result[0]["input_schema"]["type"] == "object"
        assert result[0]["input_schema"]["properties"]["query"]["type"] == "string"

    def test_parameters_renamed_to_input_schema(self):
        parameters = {"type": "object", "properties": {"q": {"type": "string"}}}
        tools = [{
            "name": "tool1",
            "description": "desc",
            "parameters": parameters,
        }]
        result = self.provider._convert_tools_to_anthropic_format(tools)
        # The schema body is moved verbatim from "parameters" to "input_schema"
        assert result[0]["input_schema"] == parameters
        assert "parameters" not in result[0]

    def test_multiple_tools_preserve_order(self):
        tools = [
            {"name": "first", "description": "1st", "parameters": {"type": "object"}},
            {"name": "second", "description": "2nd", "parameters": {"type": "object"}},
            {"name": "third", "description": "3rd", "parameters": {"type": "object"}},
        ]
        result = self.provider._convert_tools_to_anthropic_format(tools)
        assert [t["name"] for t in result] == ["first", "second", "third"]
        assert [t["description"] for t in result] == ["1st", "2nd", "3rd"]

    def test_empty_tools_returns_empty_list(self):
        result = self.provider._convert_tools_to_anthropic_format([])
        assert result == []

    def test_complex_parameters_preserved(self):
        tools = [{
            "name": "complex",
            "description": "Complex tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "nested": {
                        "type": "object",
                        "properties": {"x": {"type": "integer"}},
                    },
                    "list_field": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["nested"],
            },
        }]
        result = self.provider._convert_tools_to_anthropic_format(tools)
        schema = result[0]["input_schema"]
        assert schema["properties"]["nested"]["properties"]["x"]["type"] == "integer"
        assert schema["properties"]["list_field"]["items"]["type"] == "string"
        assert schema["required"] == ["nested"]


# ---------------------------------------------------------------------------
# _convert_message_format — pure logic
# ---------------------------------------------------------------------------

class TestConvertMessageFormat:
    def setup_method(self):
        self.provider = _make_provider()

    def test_simple_user_message_wrapped_as_text_block(self):
        msg = {"role": "user", "content": "Hello"}
        result = self.provider._convert_message_format(msg)
        assert result["role"] == "user"
        assert result["content"] == [{"type": "text", "text": "Hello"}]

    def test_assistant_message_wrapped_as_text_block(self):
        msg = {"role": "assistant", "content": "Hi there"}
        result = self.provider._convert_message_format(msg)
        assert result["role"] == "assistant"
        assert result["content"] == [{"type": "text", "text": "Hi there"}]

    def test_content_already_list_passed_through_unchanged(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "prior text"},
                {"type": "tool_use", "id": "t1", "name": "foo", "input": {}},
            ],
        }
        result = self.provider._convert_message_format(msg)
        assert result is msg  # unchanged reference
        assert result["content"][1]["type"] == "tool_use"

    def test_empty_content_becomes_placeholder(self):
        msg = {"role": "assistant", "content": ""}
        result = self.provider._convert_message_format(msg)
        # Empty string is falsy, so no text block added, falls through to placeholder
        assert result["content"] == "[Function called]"

    def test_missing_content_becomes_placeholder(self):
        msg = {"role": "assistant", "function_call": {"name": "foo", "arguments": "{}"}}
        result = self.provider._convert_message_format(msg)
        assert result["role"] == "assistant"
        assert result["content"] == "[Function called]"

    def test_none_content_becomes_placeholder(self):
        msg = {"role": "assistant", "content": None}
        result = self.provider._convert_message_format(msg)
        assert result["content"] == "[Function called]"

    def test_function_call_metadata_not_included_in_output(self):
        """Session 76 fix: function_call should be dropped, only text kept."""
        msg = {
            "role": "assistant",
            "content": "The answer is 42",
            "function_call": {"name": "calc", "arguments": '{"x": 42}'},
        }
        result = self.provider._convert_message_format(msg)
        assert result["content"] == [{"type": "text", "text": "The answer is 42"}]
        # function_call should not leak into converted message
        assert "function_call" not in result

    def test_role_preserved(self):
        msg = {"role": "user", "content": "hi"}
        result = self.provider._convert_message_format(msg)
        assert result["role"] == "user"


# ---------------------------------------------------------------------------
# _convert_tool_choice_to_anthropic_format — pure logic
# ---------------------------------------------------------------------------

class TestConvertToolChoiceToAnthropicFormat:
    def setup_method(self):
        self.provider = _make_provider()

    def test_string_auto_becomes_auto_type(self):
        result = self.provider._convert_tool_choice_to_anthropic_format("auto")
        assert result == {"type": "auto"}

    def test_string_none_becomes_none_type(self):
        result = self.provider._convert_tool_choice_to_anthropic_format("none")
        assert result == {"type": "none"}

    def test_unknown_string_passed_through(self):
        result = self.provider._convert_tool_choice_to_anthropic_format("unknown")
        assert result == "unknown"

    def test_openai_function_format_converted(self):
        choice = {"type": "function", "function": {"name": "search_events"}}
        result = self.provider._convert_tool_choice_to_anthropic_format(choice)
        assert result == {"type": "tool", "name": "search_events"}

    def test_openai_function_without_name_yields_none_name(self):
        choice = {"type": "function", "function": {}}
        result = self.provider._convert_tool_choice_to_anthropic_format(choice)
        assert result == {"type": "tool", "name": None}

    def test_already_anthropic_format_passed_through(self):
        choice = {"type": "tool", "name": "already_converted"}
        result = self.provider._convert_tool_choice_to_anthropic_format(choice)
        assert result == {"type": "tool", "name": "already_converted"}

    def test_unknown_dict_format_passed_through(self):
        choice = {"type": "something_else", "foo": "bar"}
        result = self.provider._convert_tool_choice_to_anthropic_format(choice)
        assert result == {"type": "something_else", "foo": "bar"}

    def test_non_string_non_dict_passed_through(self):
        # Ints, None, etc. pass through unchanged
        assert self.provider._convert_tool_choice_to_anthropic_format(42) == 42
        assert self.provider._convert_tool_choice_to_anthropic_format(None) is None

    def test_function_type_without_function_key_passed_through(self):
        """Only matches if BOTH type=function AND 'function' key present."""
        choice = {"type": "function"}  # missing 'function' key
        result = self.provider._convert_tool_choice_to_anthropic_format(choice)
        # Since 'function' not in dict, falls through to unknown-format pass-through
        assert result == {"type": "function"}

    def test_tool_type_without_name_key_passed_through(self):
        choice = {"type": "tool"}  # missing 'name' key
        result = self.provider._convert_tool_choice_to_anthropic_format(choice)
        assert result == {"type": "tool"}


# ---------------------------------------------------------------------------
# parse_tool_calls — mock response objects
# ---------------------------------------------------------------------------

class TestParseToolCalls:
    def setup_method(self):
        self.provider = _make_provider()

    def test_no_content_blocks_returns_empty(self):
        response = MagicMock()
        response.content = []
        result = self.provider.parse_tool_calls(response)
        assert result == []

    def test_only_text_blocks_returns_empty(self):
        response = MagicMock()
        response.content = [_make_text_block("Just text, no tools")]
        result = self.provider.parse_tool_calls(response)
        assert result == []

    def test_single_tool_use_block_extracted(self):
        block = _make_tool_use_block("tool_abc", "search", {"q": "housing"})
        response = MagicMock()
        response.content = [block]

        result = self.provider.parse_tool_calls(response)
        assert len(result) == 1
        assert result[0].id == "tool_abc"
        assert result[0].name == "search"
        assert result[0].arguments == {"q": "housing"}

    def test_multiple_tool_use_blocks_extracted_in_order(self):
        response = MagicMock()
        response.content = [
            _make_tool_use_block("t1", "first_tool", {"a": 1}),
            _make_tool_use_block("t2", "second_tool", {"b": 2}),
            _make_tool_use_block("t3", "third_tool", {"c": 3}),
        ]
        result = self.provider.parse_tool_calls(response)
        assert len(result) == 3
        assert [tc.id for tc in result] == ["t1", "t2", "t3"]
        assert [tc.name for tc in result] == ["first_tool", "second_tool", "third_tool"]
        assert result[0].arguments == {"a": 1}
        assert result[2].arguments == {"c": 3}

    def test_mixed_text_and_tool_blocks_filters_to_tools_only(self):
        response = MagicMock()
        response.content = [
            _make_text_block("Let me help"),
            _make_tool_use_block("t1", "search", {"q": "parks"}),
            _make_text_block("After tool"),
            _make_tool_use_block("t2", "fetch", {"id": 42}),
        ]
        result = self.provider.parse_tool_calls(response)
        assert len(result) == 2
        assert result[0].name == "search"
        assert result[0].arguments == {"q": "parks"}
        assert result[1].name == "fetch"
        assert result[1].arguments == {"id": 42}

    def test_returns_tool_call_dataclass_instances(self):
        """Return type is the normalized ToolCall dataclass, not provider-specific."""
        block = _make_tool_use_block("t1", "foo", {"k": "v"})
        response = MagicMock()
        response.content = [block]
        result = self.provider.parse_tool_calls(response)
        assert isinstance(result[0], ToolCall)
        # Also assert fields are populated from the block, not mock defaults
        assert result[0].id == "t1"
        assert result[0].name == "foo"
        assert result[0].arguments == {"k": "v"}


# ---------------------------------------------------------------------------
# complete — full SDK integration via mock
# ---------------------------------------------------------------------------

class TestComplete:
    def setup_method(self):
        # Build provider + keep a handle on the mock client for per-test config
        with patch("civicos_services.providers.anthropic_provider.Anthropic") as mock_cls:
            from civicos_services.providers.anthropic_provider import AnthropicProvider
            self.mock_client = MagicMock()
            mock_cls.return_value = self.mock_client
            self.provider = AnthropicProvider(api_key="key")

    def test_returns_completion_response_with_text(self):
        self.mock_client.messages.create.return_value = _make_message_response(
            content_blocks=[_make_text_block("Hi there")],
            input_tokens=5,
            output_tokens=3,
        )

        result = self.provider.complete([{"role": "user", "content": "Hello"}])

        assert isinstance(result, CompletionResponse)
        assert result.content == "Hi there"
        assert result.usage["prompt_tokens"] == 5
        assert result.usage["completion_tokens"] == 3
        assert result.usage["total_tokens"] == 8

    def test_concatenates_multiple_text_blocks(self):
        self.mock_client.messages.create.return_value = _make_message_response(
            content_blocks=[
                _make_text_block("Part one. "),
                _make_text_block("Part two."),
            ],
        )
        result = self.provider.complete([{"role": "user", "content": "Hi"}])
        assert result.content == "Part one. Part two."

    def test_ignores_tool_use_blocks_in_content_string(self):
        self.mock_client.messages.create.return_value = _make_message_response(
            content_blocks=[
                _make_text_block("Using a tool: "),
                _make_tool_use_block("t1", "search", {"q": "x"}),
                _make_text_block(" done"),
            ],
        )
        result = self.provider.complete([{"role": "user", "content": "Hi"}])
        # Text extraction skips tool_use blocks entirely
        assert result.content == "Using a tool:  done"

    def test_tool_calls_extracted_into_response(self):
        self.mock_client.messages.create.return_value = _make_message_response(
            content_blocks=[
                _make_text_block("calling tool"),
                _make_tool_use_block("toolu_1", "search", {"query": "housing"}),
            ],
        )
        result = self.provider.complete([{"role": "user", "content": "Hi"}])
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "toolu_1"
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].arguments == {"query": "housing"}

    def test_finish_reason_from_stop_reason(self):
        self.mock_client.messages.create.return_value = _make_message_response(
            stop_reason="tool_use",
        )
        result = self.provider.complete([{"role": "user", "content": "Hi"}])
        assert result.finish_reason == "tool_use"

    def test_single_system_message_passed_as_system_param(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete([
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
        ])

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are helpful"

    def test_multiple_system_messages_concatenated_with_double_newline(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete([
            {"role": "system", "content": "First system"},
            {"role": "system", "content": "Second system"},
            {"role": "user", "content": "Hi"},
        ])

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "First system\n\nSecond system"

    def test_no_system_message_omits_system_param(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete([{"role": "user", "content": "Hi"}])

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert "system" not in call_kwargs

    def test_system_messages_excluded_from_messages_array(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete([
            {"role": "system", "content": "system text"},
            {"role": "user", "content": "user text"},
        ])

        call_kwargs = self.mock_client.messages.create.call_args[1]
        sent_messages = call_kwargs["messages"]
        # Only the user message should remain in messages array
        assert len(sent_messages) == 1
        assert sent_messages[0]["role"] == "user"

    def test_user_message_content_converted_to_text_blocks(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete([{"role": "user", "content": "Hello"}])

        call_kwargs = self.mock_client.messages.create.call_args[1]
        sent_msg = call_kwargs["messages"][0]
        assert sent_msg["content"] == [{"type": "text", "text": "Hello"}]

    def test_default_model_used_when_not_specified(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete([{"role": "user", "content": "Hi"}])

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"

    def test_custom_model_overrides_default(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete(
            [{"role": "user", "content": "Hi"}],
            model="claude-3-opus-20240229",
        )

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-opus-20240229"

    def test_temperature_passed_through(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete(
            [{"role": "user", "content": "Hi"}],
            temperature=0.1,
        )

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.1

    def test_default_temperature_is_0_7(self):
        self.mock_client.messages.create.return_value = _make_message_response()
        self.provider.complete([{"role": "user", "content": "Hi"}])
        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7

    def test_max_tokens_passed_through(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete(
            [{"role": "user", "content": "Hi"}],
            max_tokens=500,
        )

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 500

    def test_default_max_tokens_is_2000(self):
        self.mock_client.messages.create.return_value = _make_message_response()
        self.provider.complete([{"role": "user", "content": "Hi"}])
        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 2000

    def test_tools_converted_to_anthropic_format_in_request(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        tools = [{
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
        }]
        self.provider.complete([{"role": "user", "content": "Weather?"}], tools=tools)

        call_kwargs = self.mock_client.messages.create.call_args[1]
        sent_tools = call_kwargs["tools"]
        assert len(sent_tools) == 1
        assert sent_tools[0]["name"] == "get_weather"
        assert "input_schema" in sent_tools[0]
        assert "parameters" not in sent_tools[0]

    def test_no_tools_omits_tools_param(self):
        self.mock_client.messages.create.return_value = _make_message_response()
        self.provider.complete([{"role": "user", "content": "Hi"}])
        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert "tools" not in call_kwargs

    def test_openai_tool_choice_converted_to_anthropic_format(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete(
            [{"role": "user", "content": "Hi"}],
            tool_choice={"type": "function", "function": {"name": "search"}},
        )

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "search"}

    def test_tool_choice_auto_string_converted(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete(
            [{"role": "user", "content": "Hi"}],
            tool_choice="auto",
        )

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["tool_choice"] == {"type": "auto"}

    def test_extra_kwargs_merged_into_request(self):
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete(
            [{"role": "user", "content": "Hi"}],
            top_p=0.9,
        )

        call_kwargs = self.mock_client.messages.create.call_args[1]
        assert call_kwargs["top_p"] == 0.9

    def test_raw_response_stored_in_completion(self):
        mock_resp = _make_message_response()
        self.mock_client.messages.create.return_value = mock_resp
        result = self.provider.complete([{"role": "user", "content": "Hi"}])
        assert result.raw_response is mock_resp

    def test_assistant_history_message_converted(self):
        """A conversation with an assistant turn should convert both roles."""
        self.mock_client.messages.create.return_value = _make_message_response()

        self.provider.complete([
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello back"},
            {"role": "user", "content": "Second"},
        ])

        call_kwargs = self.mock_client.messages.create.call_args[1]
        sent = call_kwargs["messages"]
        assert len(sent) == 3
        assert sent[0]["role"] == "user"
        assert sent[1]["role"] == "assistant"
        assert sent[1]["content"] == [{"type": "text", "text": "Hello back"}]
        assert sent[2]["role"] == "user"

    def test_empty_text_content_preserved_in_response(self):
        self.mock_client.messages.create.return_value = _make_message_response(
            content_blocks=[_make_text_block("")],
        )
        result = self.provider.complete([{"role": "user", "content": "Hi"}])
        assert result.content == ""

    def test_total_tokens_is_sum_of_input_and_output(self):
        self.mock_client.messages.create.return_value = _make_message_response(
            input_tokens=100,
            output_tokens=250,
        )
        result = self.provider.complete([{"role": "user", "content": "Hi"}])
        assert result.usage["total_tokens"] == 350


# ---------------------------------------------------------------------------
# stream_complete — SDK integration via mock
# ---------------------------------------------------------------------------

class _FakeStreamContext:
    """Mimics anthropic.messages.stream() context manager."""

    def __init__(self, text_chunks):
        self._chunks = text_chunks

    def __enter__(self):
        stream = MagicMock()
        stream.text_stream = iter(self._chunks)
        return stream

    def __exit__(self, exc_type, exc, tb):
        return False


class TestStreamComplete:
    def setup_method(self):
        with patch("civicos_services.providers.anthropic_provider.Anthropic") as mock_cls:
            from civicos_services.providers.anthropic_provider import AnthropicProvider
            self.mock_client = MagicMock()
            mock_cls.return_value = self.mock_client
            self.provider = AnthropicProvider(api_key="key")

    def test_yields_all_chunks_in_order(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(
            ["Hello ", "world", "!"]
        )
        chunks = list(self.provider.stream_complete(
            [{"role": "user", "content": "Hi"}]
        ))
        assert chunks == ["Hello ", "world", "!"]

    def test_empty_stream_yields_nothing(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext([])
        chunks = list(self.provider.stream_complete(
            [{"role": "user", "content": "Hi"}]
        ))
        assert chunks == []

    def test_stream_passes_stream_true(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete([{"role": "user", "content": "Hi"}]))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert call_kwargs["stream"] is True

    def test_stream_default_model_used(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete([{"role": "user", "content": "Hi"}]))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"

    def test_stream_custom_model_override(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete(
            [{"role": "user", "content": "Hi"}],
            model="claude-3-haiku-20240307",
        ))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert call_kwargs["model"] == "claude-3-haiku-20240307"

    def test_stream_temperature_and_max_tokens(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete(
            [{"role": "user", "content": "Hi"}],
            temperature=0.2,
            max_tokens=1500,
        ))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert call_kwargs["temperature"] == 0.2
        assert call_kwargs["max_tokens"] == 1500

    def test_stream_system_message_extracted(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete([
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "Hi"},
        ]))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert call_kwargs["system"] == "Be concise"
        # System message stripped from messages array
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"

    def test_stream_no_system_omits_system_param(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete([{"role": "user", "content": "Hi"}]))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert "system" not in call_kwargs

    def test_stream_last_system_wins_when_multiple(self):
        """stream_complete uses simple overwrite (unlike complete which concatenates)."""
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete([
            {"role": "system", "content": "first"},
            {"role": "system", "content": "second"},
            {"role": "user", "content": "Hi"},
        ]))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert call_kwargs["system"] == "second"

    def test_stream_tools_converted(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        parameters = {"type": "object", "properties": {"q": {"type": "string"}}}
        tools = [{
            "name": "search",
            "description": "Search",
            "parameters": parameters,
        }]
        list(self.provider.stream_complete(
            [{"role": "user", "content": "Hi"}],
            tools=tools,
        ))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        sent_tools = call_kwargs["tools"]
        assert sent_tools[0]["name"] == "search"
        assert sent_tools[0]["description"] == "Search"
        assert sent_tools[0]["input_schema"] == parameters
        assert "parameters" not in sent_tools[0]

    def test_stream_tool_choice_converted(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete(
            [{"role": "user", "content": "Hi"}],
            tool_choice={"type": "function", "function": {"name": "search"}},
        ))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "search"}

    def test_stream_extra_kwargs_merged(self):
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        list(self.provider.stream_complete(
            [{"role": "user", "content": "Hi"}],
            top_k=40,
        ))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        assert call_kwargs["top_k"] == 40

    def test_stream_messages_passed_without_conversion(self):
        """stream_complete does NOT run _convert_message_format on user messages."""
        self.mock_client.messages.stream.return_value = _FakeStreamContext(["x"])
        original_msg = {"role": "user", "content": "raw string"}
        list(self.provider.stream_complete([original_msg]))

        call_kwargs = self.mock_client.messages.stream.call_args[1]
        # Plain string content is passed through (not wrapped in text blocks)
        assert call_kwargs["messages"][0]["content"] == "raw string"
