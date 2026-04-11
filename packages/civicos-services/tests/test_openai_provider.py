"""
Tests for openai_provider.py — OpenAI GPT-4 LLM provider.

The OpenAI SDK boundary is mocked; provider logic (tool conversion, request
parameter assembly, response normalization, streaming aggregation) is tested
with real inputs and pinned outputs.

To run:
    pytest packages/civicos-services/tests/test_openai_provider.py -q --override-ini="addopts="
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from civicos_services.providers.base import CompletionResponse, ToolCall


# ---------------------------------------------------------------------------
# Helpers — build a provider without hitting the real OpenAI API
# ---------------------------------------------------------------------------

def _make_provider(api_key="fake-key"):
    """Create an OpenAIProvider with a mocked OpenAI client constructor."""
    with patch("civicos_services.providers.openai_provider.OpenAI") as mock_client_cls:
        from civicos_services.providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider(api_key=api_key)
        mock_client_cls.assert_called_once_with(api_key=api_key)
    return provider


def _make_provider_with_client():
    """Create a provider and return (provider, mock_client) for per-test config."""
    with patch("civicos_services.providers.openai_provider.OpenAI") as mock_cls:
        from civicos_services.providers.openai_provider import OpenAIProvider
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        provider = OpenAIProvider(api_key="key")
    return provider, mock_client


def _make_tool_call_obj(tc_id, name, arguments_json):
    """Build a mock OpenAI SDK tool_call object."""
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = arguments_json
    return tc


def _make_choice(
    content="",
    tool_calls=None,
    finish_reason="stop",
):
    """Build a mock OpenAI SDK choice object."""
    message = MagicMock()
    message.content = content
    if tool_calls is None:
        # No tool_calls attribute set; parse_tool_calls checks hasattr
        # MagicMock auto-creates attributes, so we set to None (falsy)
        message.tool_calls = None
    else:
        message.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason
    return choice


def _make_completion_response(
    content="",
    tool_calls=None,
    finish_reason="stop",
    prompt_tokens=10,
    completion_tokens=20,
    total_tokens=30,
):
    """Build a mock OpenAI SDK ChatCompletion response."""
    response = MagicMock()
    response.choices = [_make_choice(content, tool_calls, finish_reason)]
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = total_tokens
    return response


def _make_stream_chunk(content):
    """Build a mock streaming chunk. content=None means no content delta."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = content
    return chunk


# ---------------------------------------------------------------------------
# Construction and properties
# ---------------------------------------------------------------------------

class TestProperties:
    def test_name_is_openai(self):
        provider = _make_provider()
        assert provider.name == "openai"

    def test_default_model_is_gpt_4o_mini(self):
        provider = _make_provider()
        assert provider.default_model == "gpt-4o-mini"

    def test_explicit_api_key_stored(self):
        provider = _make_provider(api_key="sk-explicit-123")
        assert provider.api_key == "sk-explicit-123"

    def test_api_key_falls_back_to_env_var(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key-456"}, clear=False):
            with patch("civicos_services.providers.openai_provider.OpenAI") as mock_cls:
                from civicos_services.providers.openai_provider import OpenAIProvider
                provider = OpenAIProvider()
            mock_cls.assert_called_once_with(api_key="env-key-456")
            assert provider.api_key == "env-key-456"

    def test_explicit_api_key_overrides_env_var(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}, clear=False):
            with patch("civicos_services.providers.openai_provider.OpenAI"):
                from civicos_services.providers.openai_provider import OpenAIProvider
                provider = OpenAIProvider(api_key="explicit-key")
            assert provider.api_key == "explicit-key"

    def test_none_api_key_and_no_env_var_stays_none(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("civicos_services.providers.openai_provider.OpenAI") as mock_cls:
                from civicos_services.providers.openai_provider import OpenAIProvider
                provider = OpenAIProvider()
            mock_cls.assert_called_once_with(api_key=None)
            assert provider.api_key is None

    def test_openai_client_constructed_with_resolved_key(self):
        """OpenAI() receives the exact resolved api_key and its result becomes provider.client."""
        with patch("civicos_services.providers.openai_provider.OpenAI") as mock_cls:
            sentinel_client = MagicMock()
            mock_cls.return_value = sentinel_client
            from civicos_services.providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-abc")
        # The constructor-returned client is stored on the provider
        assert provider.client is sentinel_client
        # And the resolved key is the one handed to the SDK constructor
        assert mock_cls.call_args.kwargs["api_key"] == "sk-abc"


# ---------------------------------------------------------------------------
# _convert_tools_to_openai_format — pure logic
# ---------------------------------------------------------------------------

class TestConvertToolsToOpenAIFormat:
    def setup_method(self):
        self.provider = _make_provider()

    def test_single_tool_wrapped_with_type_function(self):
        tools = [{
            "name": "search_events",
            "description": "Search civic events",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        }]
        result = self.provider._convert_tools_to_openai_format(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "search_events"
        assert result[0]["function"]["description"] == "Search civic events"
        assert result[0]["function"]["parameters"]["type"] == "object"
        assert result[0]["function"]["parameters"]["properties"]["q"]["type"] == "string"

    def test_parameters_nested_under_function_key(self):
        params = {"type": "object", "properties": {"id": {"type": "integer"}}}
        tools = [{"name": "fetch", "description": "d", "parameters": params}]
        result = self.provider._convert_tools_to_openai_format(tools)

        # Parameters are nested inside "function", not at the top level
        assert "parameters" not in result[0]
        assert result[0]["function"]["parameters"] == params

    def test_multiple_tools_preserve_order(self):
        tools = [
            {"name": "alpha", "description": "a", "parameters": {"type": "object"}},
            {"name": "beta", "description": "b", "parameters": {"type": "object"}},
            {"name": "gamma", "description": "g", "parameters": {"type": "object"}},
        ]
        result = self.provider._convert_tools_to_openai_format(tools)

        assert len(result) == 3
        assert [t["function"]["name"] for t in result] == ["alpha", "beta", "gamma"]
        assert [t["function"]["description"] for t in result] == ["a", "b", "g"]
        # Every entry is tagged as a function
        assert all(t["type"] == "function" for t in result)

    def test_empty_tools_returns_empty_list(self):
        result = self.provider._convert_tools_to_openai_format([])
        assert result == []

    def test_complex_nested_parameters_preserved(self):
        params = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "filters": {
                    "type": "object",
                    "properties": {
                        "date_from": {"type": "string", "format": "date"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                },
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
        }
        tools = [{"name": "complex", "description": "c", "parameters": params}]
        result = self.provider._convert_tools_to_openai_format(tools)

        emitted = result[0]["function"]["parameters"]
        assert emitted["properties"]["filters"]["properties"]["limit"]["maximum"] == 100
        assert emitted["properties"]["filters"]["properties"]["limit"]["minimum"] == 1
        assert emitted["properties"]["tags"]["items"]["type"] == "string"
        assert emitted["required"] == ["query"]


# ---------------------------------------------------------------------------
# parse_tool_calls — response handling
# ---------------------------------------------------------------------------

class TestParseToolCalls:
    def setup_method(self):
        self.provider = _make_provider()

    def test_message_without_tool_calls_attribute_returns_empty(self):
        message = object()  # has no tool_calls attr
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message = message
        result = self.provider.parse_tool_calls(response)
        assert result == []

    def test_message_with_none_tool_calls_returns_empty(self):
        response = _make_completion_response(tool_calls=None)
        result = self.provider.parse_tool_calls(response)
        assert result == []

    def test_message_with_empty_tool_calls_list_returns_empty(self):
        response = _make_completion_response(tool_calls=[])
        result = self.provider.parse_tool_calls(response)
        assert result == []

    def test_single_tool_call_extracted(self):
        tc = _make_tool_call_obj("call_abc", "search", '{"q": "housing"}')
        response = _make_completion_response(tool_calls=[tc])

        result = self.provider.parse_tool_calls(response)

        assert len(result) == 1
        assert result[0].id == "call_abc"
        assert result[0].name == "search"
        assert result[0].arguments == {"q": "housing"}

    def test_multiple_tool_calls_extracted_in_order(self):
        tcs = [
            _make_tool_call_obj("t1", "first", '{"x": 1}'),
            _make_tool_call_obj("t2", "second", '{"y": 2}'),
            _make_tool_call_obj("t3", "third", '{"z": 3}'),
        ]
        response = _make_completion_response(tool_calls=tcs)

        result = self.provider.parse_tool_calls(response)

        assert len(result) == 3
        assert [t.id for t in result] == ["t1", "t2", "t3"]
        assert [t.name for t in result] == ["first", "second", "third"]
        assert result[0].arguments == {"x": 1}
        assert result[1].arguments == {"y": 2}
        assert result[2].arguments == {"z": 3}

    def test_arguments_are_json_parsed_into_dict(self):
        tc = _make_tool_call_obj(
            "c1",
            "lookup",
            '{"name": "parks", "limit": 10, "nested": {"a": true}}',
        )
        response = _make_completion_response(tool_calls=[tc])

        result = self.provider.parse_tool_calls(response)

        assert result[0].arguments == {
            "name": "parks",
            "limit": 10,
            "nested": {"a": True},
        }
        # Arguments must be a dict, not the raw JSON string
        assert isinstance(result[0].arguments, dict)

    def test_empty_json_object_arguments_yields_empty_dict(self):
        tc = _make_tool_call_obj("c1", "noop", "{}")
        response = _make_completion_response(tool_calls=[tc])

        result = self.provider.parse_tool_calls(response)
        assert result[0].arguments == {}

    def test_invalid_json_arguments_raises(self):
        tc = _make_tool_call_obj("c1", "broken", "not-json")
        response = _make_completion_response(tool_calls=[tc])

        with pytest.raises(json.JSONDecodeError):
            self.provider.parse_tool_calls(response)

    def test_returns_tool_call_dataclass_instances(self):
        tc = _make_tool_call_obj("c1", "foo", '{"k": "v"}')
        response = _make_completion_response(tool_calls=[tc])

        result = self.provider.parse_tool_calls(response)
        assert isinstance(result[0], ToolCall)
        # Fields populated from source, not mock defaults
        assert result[0].id == "c1"
        assert result[0].name == "foo"
        assert result[0].arguments == {"k": "v"}


# ---------------------------------------------------------------------------
# complete — response normalization and request assembly
# ---------------------------------------------------------------------------

class TestCompleteResponseShape:
    def setup_method(self):
        self.provider, self.mock_client = _make_provider_with_client()

    def test_returns_completion_response_dataclass(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            content="Hello",
            finish_reason="stop",
            prompt_tokens=3,
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        # Normalized dataclass (not a raw SDK response)
        assert isinstance(result, CompletionResponse)
        # And key fields are populated from the source (not mock defaults)
        assert result.content == "Hello"
        assert result.finish_reason == "stop"
        assert result.usage["prompt_tokens"] == 3

    def test_content_extracted_from_first_choice(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            content="specific reply"
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        assert result.content == "specific reply"

    def test_none_content_becomes_empty_string(self):
        """OpenAI returns None content when only tool_calls are present."""
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            content=None,
            tool_calls=[_make_tool_call_obj("t1", "foo", "{}")],
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        assert result.content == ""

    def test_empty_string_content_preserved(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            content=""
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        assert result.content == ""

    def test_finish_reason_passed_through(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            finish_reason="length"
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        assert result.finish_reason == "length"

    def test_finish_reason_tool_calls_preserved(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            finish_reason="tool_calls",
            tool_calls=[_make_tool_call_obj("t1", "foo", "{}")],
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        assert result.finish_reason == "tool_calls"

    def test_usage_populated_from_response(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            prompt_tokens=42,
            completion_tokens=17,
            total_tokens=59,
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        assert result.usage == {
            "prompt_tokens": 42,
            "completion_tokens": 17,
            "total_tokens": 59,
        }

    def test_raw_response_stored_verbatim(self):
        raw = _make_completion_response(content="x")
        self.mock_client.chat.completions.create.return_value = raw
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        assert result.raw_response is raw

    def test_tool_calls_empty_by_default(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            content="no tools"
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])
        assert result.tool_calls == []

    def test_tool_calls_extracted_and_normalized(self):
        tcs = [
            _make_tool_call_obj("call_1", "search", '{"q": "housing"}'),
            _make_tool_call_obj("call_2", "fetch", '{"id": 99}'),
        ]
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            content=None,
            tool_calls=tcs,
            finish_reason="tool_calls",
        )
        result = self.provider.complete([{"role": "user", "content": "hi"}])

        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].id == "call_1"
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].arguments == {"q": "housing"}
        assert result.tool_calls[1].id == "call_2"
        assert result.tool_calls[1].arguments == {"id": 99}


class TestCompleteRequestAssembly:
    def setup_method(self):
        self.provider, self.mock_client = _make_provider_with_client()
        self.mock_client.chat.completions.create.return_value = _make_completion_response()

    def _call_kwargs(self):
        return self.mock_client.chat.completions.create.call_args[1]

    def test_messages_passed_through_unchanged(self):
        msgs = [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "again"},
        ]
        self.provider.complete(msgs)
        # OpenAI API receives messages array verbatim (no system extraction)
        assert self._call_kwargs()["messages"] == msgs

    def test_default_model_is_gpt_4o_mini(self):
        self.provider.complete([{"role": "user", "content": "hi"}])
        assert self._call_kwargs()["model"] == "gpt-4o-mini"

    def test_custom_model_overrides_default(self):
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            model="gpt-4-turbo",
        )
        assert self._call_kwargs()["model"] == "gpt-4-turbo"

    def test_none_model_falls_back_to_default(self):
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            model=None,
        )
        assert self._call_kwargs()["model"] == "gpt-4o-mini"

    def test_default_temperature_is_0_7(self):
        self.provider.complete([{"role": "user", "content": "hi"}])
        assert self._call_kwargs()["temperature"] == 0.7

    def test_custom_temperature_passed_through(self):
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            temperature=0.2,
        )
        assert self._call_kwargs()["temperature"] == 0.2

    def test_temperature_zero_passed_through(self):
        """Boundary: 0.0 is a valid temperature, must not be filtered out."""
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            temperature=0.0,
        )
        assert self._call_kwargs()["temperature"] == 0.0

    def test_max_tokens_omitted_by_default(self):
        self.provider.complete([{"role": "user", "content": "hi"}])
        assert "max_tokens" not in self._call_kwargs()

    def test_max_tokens_passed_through_when_provided(self):
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            max_tokens=500,
        )
        assert self._call_kwargs()["max_tokens"] == 500

    def test_max_tokens_zero_omitted_due_to_truthiness(self):
        """
        Implementation uses `if max_tokens:`, so 0 is treated as unset.
        This pins the current behavior — future change needs a test update.
        """
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            max_tokens=0,
        )
        assert "max_tokens" not in self._call_kwargs()

    def test_no_tools_omits_tools_param(self):
        self.provider.complete([{"role": "user", "content": "hi"}])
        assert "tools" not in self._call_kwargs()

    def test_empty_tools_list_omits_tools_param(self):
        """Empty list is falsy, should not be sent."""
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            tools=[],
        )
        assert "tools" not in self._call_kwargs()

    def test_tools_converted_to_openai_format_in_request(self):
        tools = [{
            "name": "search",
            "description": "Search stuff",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        }]
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            tools=tools,
        )
        sent_tools = self._call_kwargs()["tools"]
        assert len(sent_tools) == 1
        assert sent_tools[0]["type"] == "function"
        assert sent_tools[0]["function"]["name"] == "search"
        assert sent_tools[0]["function"]["description"] == "Search stuff"
        assert sent_tools[0]["function"]["parameters"]["properties"]["q"]["type"] == "string"

    def test_extra_kwargs_merged_into_request(self):
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            top_p=0.9,
            presence_penalty=0.5,
            seed=42,
        )
        kwargs = self._call_kwargs()
        assert kwargs["top_p"] == 0.9
        assert kwargs["presence_penalty"] == 0.5
        assert kwargs["seed"] == 42

    def test_response_format_kwarg_passed_through(self):
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            response_format={"type": "json_object"},
        )
        assert self._call_kwargs()["response_format"] == {"type": "json_object"}

    def test_kwargs_can_override_base_params(self):
        """kwargs.update() runs last, so user kwargs beat defaults."""
        self.provider.complete(
            [{"role": "user", "content": "hi"}],
            temperature=0.5,  # Named arg sets temperature=0.5
            model="gpt-4",  # Named arg sets model=gpt-4
        )
        kwargs = self._call_kwargs()
        assert kwargs["temperature"] == 0.5
        assert kwargs["model"] == "gpt-4"


# ---------------------------------------------------------------------------
# stream_complete — streaming
# ---------------------------------------------------------------------------

class TestStreamComplete:
    def setup_method(self):
        self.provider, self.mock_client = _make_provider_with_client()

    def _call_kwargs(self):
        return self.mock_client.chat.completions.create.call_args[1]

    def test_yields_content_chunks_in_order(self):
        self.mock_client.chat.completions.create.return_value = iter([
            _make_stream_chunk("Hello "),
            _make_stream_chunk("world"),
            _make_stream_chunk("!"),
        ])
        chunks = list(self.provider.stream_complete(
            [{"role": "user", "content": "hi"}]
        ))
        assert chunks == ["Hello ", "world", "!"]

    def test_empty_stream_yields_nothing(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        chunks = list(self.provider.stream_complete(
            [{"role": "user", "content": "hi"}]
        ))
        assert chunks == []

    def test_chunks_with_none_content_are_skipped(self):
        """Delta-only chunks (e.g. role delta) have content=None."""
        self.mock_client.chat.completions.create.return_value = iter([
            _make_stream_chunk(None),  # role delta, no content
            _make_stream_chunk("real "),
            _make_stream_chunk(None),  # another empty
            _make_stream_chunk("content"),
        ])
        chunks = list(self.provider.stream_complete(
            [{"role": "user", "content": "hi"}]
        ))
        assert chunks == ["real ", "content"]

    def test_empty_string_chunks_are_skipped(self):
        """Empty string is falsy in `if chunk.delta.content:` — implementation skips."""
        self.mock_client.chat.completions.create.return_value = iter([
            _make_stream_chunk(""),
            _make_stream_chunk("actual"),
            _make_stream_chunk(""),
        ])
        chunks = list(self.provider.stream_complete(
            [{"role": "user", "content": "hi"}]
        ))
        assert chunks == ["actual"]

    def test_stream_true_passed_to_api(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        list(self.provider.stream_complete([{"role": "user", "content": "hi"}]))
        assert self._call_kwargs()["stream"] is True

    def test_stream_default_model_used(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        list(self.provider.stream_complete([{"role": "user", "content": "hi"}]))
        assert self._call_kwargs()["model"] == "gpt-4o-mini"

    def test_stream_custom_model_overrides_default(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        list(self.provider.stream_complete(
            [{"role": "user", "content": "hi"}],
            model="gpt-4-turbo",
        ))
        assert self._call_kwargs()["model"] == "gpt-4-turbo"

    def test_stream_default_temperature_is_0_7(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        list(self.provider.stream_complete([{"role": "user", "content": "hi"}]))
        assert self._call_kwargs()["temperature"] == 0.7

    def test_stream_custom_temperature_passed_through(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        list(self.provider.stream_complete(
            [{"role": "user", "content": "hi"}],
            temperature=0.1,
        ))
        assert self._call_kwargs()["temperature"] == 0.1

    def test_stream_messages_passed_verbatim(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        msgs = [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ]
        list(self.provider.stream_complete(msgs))
        assert self._call_kwargs()["messages"] == msgs

    def test_stream_no_tools_omits_tools_param(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        list(self.provider.stream_complete([{"role": "user", "content": "hi"}]))
        assert "tools" not in self._call_kwargs()

    def test_stream_tools_converted_to_openai_format(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        tools = [{
            "name": "search",
            "description": "Search",
            "parameters": {"type": "object"},
        }]
        list(self.provider.stream_complete(
            [{"role": "user", "content": "hi"}],
            tools=tools,
        ))
        sent_tools = self._call_kwargs()["tools"]
        assert len(sent_tools) == 1
        assert sent_tools[0]["type"] == "function"
        assert sent_tools[0]["function"]["name"] == "search"

    def test_stream_extra_kwargs_merged(self):
        self.mock_client.chat.completions.create.return_value = iter([])
        list(self.provider.stream_complete(
            [{"role": "user", "content": "hi"}],
            top_p=0.5,
            seed=7,
        ))
        kwargs = self._call_kwargs()
        assert kwargs["top_p"] == 0.5
        assert kwargs["seed"] == 7

    def test_stream_iteration_is_lazy(self):
        """The SDK stream should be consumed only while the generator is iterated."""
        chunks_yielded = []

        def source():
            for c in ["a", "b", "c"]:
                chunks_yielded.append(c)
                yield _make_stream_chunk(c)

        self.mock_client.chat.completions.create.return_value = source()
        gen = self.provider.stream_complete([{"role": "user", "content": "hi"}])

        # Nothing consumed yet
        assert chunks_yielded == []

        first = next(gen)
        assert first == "a"
        assert chunks_yielded == ["a"]

        second = next(gen)
        assert second == "b"
        assert chunks_yielded == ["a", "b"]


# ---------------------------------------------------------------------------
# chat convenience wrapper (inherited from LLMProvider base)
# ---------------------------------------------------------------------------

class TestChatConvenienceWrapper:
    """Base class chat() wraps complete() and returns just .content."""

    def setup_method(self):
        self.provider, self.mock_client = _make_provider_with_client()

    def test_chat_returns_content_string(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            content="the answer"
        )
        result = self.provider.chat([{"role": "user", "content": "?"}])
        assert result == "the answer"

    def test_chat_json_response_format_shorthand_converted(self):
        self.mock_client.chat.completions.create.return_value = _make_completion_response(
            content='{"ok": true}'
        )
        self.provider.chat(
            [{"role": "user", "content": "?"}],
            response_format="json_object",
        )
        call_kwargs = self.mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}
