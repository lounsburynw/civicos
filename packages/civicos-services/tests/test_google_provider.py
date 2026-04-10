"""
Tests for google_provider.py — Google Gemini LLM provider.

Pure-logic methods (_normalize_schema_for_gemini, _strip_markdown_fences,
_convert_tools_to_google_format) are tested with real inputs and pinned outputs.
SDK-touching methods (complete, stream_complete, parse_tool_calls) mock the
google.generativeai boundary only.

To run:
    pytest packages/civicos-services/tests/test_google_provider.py -q --override-ini="addopts="
"""

from unittest.mock import patch, MagicMock, PropertyMock
import pytest

from civicos_services.providers.base import CompletionResponse, ToolCall


# ---------------------------------------------------------------------------
# Helpers — build a provider without hitting the real Google API
# ---------------------------------------------------------------------------

def _make_provider(model=None):
    """Create a GoogleProvider with mocked genai.configure (no real API call)."""
    with patch("civicos_services.providers.google_provider.genai") as mock_genai:
        from civicos_services.providers.google_provider import GoogleProvider
        provider = GoogleProvider(api_key="fake-key", model=model)
        mock_genai.configure.assert_called_once_with(api_key="fake-key")
    return provider


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class TestProperties:
    def test_name_returns_google(self):
        provider = _make_provider()
        assert provider.name == "google"

    def test_default_model_is_gemini_flash(self):
        provider = _make_provider()
        assert provider.default_model == "models/gemini-2.0-flash"

    def test_custom_model_overrides_default(self):
        provider = _make_provider(model="gemini-1.5-pro-latest")
        assert provider.default_model == "gemini-1.5-pro-latest"

    def test_api_key_stored(self):
        provider = _make_provider()
        assert provider.api_key == "fake-key"

    def test_api_key_from_env_when_none_passed(self):
        with patch("os.getenv", return_value="env-key"):
            with patch("civicos_services.providers.google_provider.genai"):
                from civicos_services.providers.google_provider import GoogleProvider
                provider = GoogleProvider()
        assert provider.api_key == "env-key"


# ---------------------------------------------------------------------------
# _normalize_schema_for_gemini — pure logic
# ---------------------------------------------------------------------------

class TestNormalizeSchemaForGemini:
    def setup_method(self):
        self.provider = _make_provider()

    def test_array_type_picks_first_non_null(self):
        schema = {"type": ["string", "null"]}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result["type"] == "string"

    def test_array_type_integer_and_null(self):
        schema = {"type": ["integer", "null"]}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result["type"] == "integer"

    def test_array_type_all_null_falls_back_to_string(self):
        schema = {"type": ["null"]}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result["type"] == "string"

    def test_single_type_string_unchanged(self):
        schema = {"type": "string", "description": "A field"}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result["type"] == "string"
        assert result["description"] == "A field"

    def test_removes_additionalProperties(self):
        schema = {"type": "object", "additionalProperties": False}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert "additionalProperties" not in result
        assert result["type"] == "object"

    def test_removes_minItems(self):
        schema = {"type": "array", "minItems": 1}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert "minItems" not in result

    def test_removes_maxItems(self):
        schema = {"type": "array", "maxItems": 10}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert "maxItems" not in result

    def test_nested_properties_normalized(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "age": {"type": "integer"},
            },
        }
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result["properties"]["name"]["type"] == "string"
        assert result["properties"]["age"]["type"] == "integer"

    def test_deeply_nested_array_items_normalized(self):
        schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": ["string", "null"]},
                    "minItems": 0,
                },
            },
        }
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result["properties"]["tags"]["items"]["type"] == "string"
        assert "minItems" not in result["properties"]["tags"]

    def test_does_not_mutate_input(self):
        schema = {"type": ["boolean", "null"], "additionalProperties": True}
        original_type = schema["type"].copy()
        self.provider._normalize_schema_for_gemini(schema)
        assert schema["type"] == original_type
        assert "additionalProperties" in schema

    def test_empty_schema_unchanged(self):
        schema = {}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result == {}

    def test_list_within_schema_items_normalized(self):
        """Schemas containing lists of sub-schemas (e.g., oneOf) are traversed."""
        schema = {
            "oneOf": [
                {"type": ["string", "null"]},
                {"type": "integer"},
            ]
        }
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result["oneOf"][0]["type"] == "string"
        assert result["oneOf"][1]["type"] == "integer"

    def test_multiple_non_null_types_picks_first(self):
        schema = {"type": ["number", "string", "null"]}
        result = self.provider._normalize_schema_for_gemini(schema)
        assert result["type"] == "number"


# ---------------------------------------------------------------------------
# _strip_markdown_fences — pure logic
# ---------------------------------------------------------------------------

class TestStripMarkdownFences:
    def setup_method(self):
        self.provider = _make_provider()

    def test_strips_json_fence(self):
        content = '```json\n{"key": "value"}\n```'
        result = self.provider._strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strips_plain_fence(self):
        content = '```\n{"key": "value"}\n```'
        result = self.provider._strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_no_fence_returns_unchanged(self):
        content = '{"key": "value"}'
        result = self.provider._strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_unclosed_fence_skips_first_line(self):
        content = '```json\n{"key": "value"}'
        result = self.provider._strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_multiline_content_preserved(self):
        content = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = self.provider._strip_markdown_fences(content)
        assert result == '{\n  "a": 1,\n  "b": 2\n}'

    def test_leading_whitespace_stripped_before_check(self):
        content = '  ```json\n{"key": "value"}\n```'
        result = self.provider._strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_empty_content_inside_fences(self):
        content = '```json\n\n```'
        result = self.provider._strip_markdown_fences(content)
        assert result == ''

    def test_fence_with_language_tag_other_than_json(self):
        content = '```python\nprint("hi")\n```'
        result = self.provider._strip_markdown_fences(content)
        assert result == 'print("hi")'


# ---------------------------------------------------------------------------
# _convert_tools_to_google_format — pure logic
# ---------------------------------------------------------------------------

class TestConvertToolsToGoogleFormat:
    def setup_method(self):
        self.provider = _make_provider()

    def test_single_tool_structure(self):
        tools = [{
            "name": "search_events",
            "description": "Search civic events",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
            },
        }]
        result = self.provider._convert_tools_to_google_format(tools)
        assert "function_declarations" in result
        decls = result["function_declarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "search_events"
        assert decls[0]["description"] == "Search civic events"
        assert decls[0]["parameters"]["properties"]["query"]["type"] == "string"

    def test_multiple_tools(self):
        tools = [
            {"name": "tool_a", "description": "A", "parameters": {"type": "object"}},
            {"name": "tool_b", "description": "B", "parameters": {"type": "object"}},
        ]
        result = self.provider._convert_tools_to_google_format(tools)
        names = [d["name"] for d in result["function_declarations"]]
        assert names == ["tool_a", "tool_b"]

    def test_parameters_normalized_during_conversion(self):
        """Array types in parameters should be normalized to single type."""
        tools = [{
            "name": "lookup",
            "description": "Lookup",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": ["integer", "null"]},
                },
                "additionalProperties": False,
            },
        }]
        result = self.provider._convert_tools_to_google_format(tools)
        params = result["function_declarations"][0]["parameters"]
        assert params["properties"]["id"]["type"] == "integer"
        assert "additionalProperties" not in params

    def test_empty_tools_list(self):
        result = self.provider._convert_tools_to_google_format([])
        assert result == {"function_declarations": []}


# ---------------------------------------------------------------------------
# parse_tool_calls — mock response objects
# ---------------------------------------------------------------------------

class TestParseToolCalls:
    def setup_method(self):
        self.provider = _make_provider()

    def test_no_candidates_returns_empty(self):
        response = MagicMock()
        response.candidates = []
        result = self.provider.parse_tool_calls(response)
        assert result == []

    def test_candidate_without_parts_returns_empty(self):
        candidate = MagicMock()
        candidate.content = MagicMock(spec=[])  # no 'parts' attribute
        response = MagicMock()
        response.candidates = [candidate]
        result = self.provider.parse_tool_calls(response)
        assert result == []

    def test_extracts_single_function_call(self):
        fc = MagicMock()
        fc.name = "search_events"
        fc.args = {"query": "housing", "limit": 10}

        part = MagicMock()
        part.function_call = fc

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.candidates = [candidate]

        result = self.provider.parse_tool_calls(response)
        assert len(result) == 1
        assert result[0].name == "search_events"
        assert result[0].id == "search_events"
        assert result[0].arguments == {"query": "housing", "limit": 10}

    def test_extracts_multiple_function_calls(self):
        def make_fc(name, args):
            fc = MagicMock()
            fc.name = name
            fc.args = args
            part = MagicMock()
            part.function_call = fc
            return part

        candidate = MagicMock()
        candidate.content.parts = [
            make_fc("search", {"q": "housing"}),
            make_fc("filter", {"topic": "zoning"}),
        ]

        response = MagicMock()
        response.candidates = [candidate]

        result = self.provider.parse_tool_calls(response)
        assert len(result) == 2
        assert result[0].name == "search"
        assert result[0].arguments == {"q": "housing"}
        assert result[1].name == "filter"
        assert result[1].arguments == {"topic": "zoning"}

    def test_part_without_function_call_skipped(self):
        text_part = MagicMock()
        text_part.function_call = None
        del text_part.function_call  # no attribute at all — hasattr returns False

        fc = MagicMock()
        fc.name = "search"
        fc.args = {"q": "test"}
        fc_part = MagicMock()
        fc_part.function_call = fc

        candidate = MagicMock()
        candidate.content.parts = [text_part, fc_part]

        response = MagicMock()
        response.candidates = [candidate]

        result = self.provider.parse_tool_calls(response)
        assert len(result) == 1
        assert result[0].name == "search"

    def test_empty_args_yields_empty_dict(self):
        fc = MagicMock()
        fc.name = "no_args_tool"
        fc.args = None

        part = MagicMock()
        part.function_call = fc

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.candidates = [candidate]

        result = self.provider.parse_tool_calls(response)
        assert result[0].arguments == {}


# ---------------------------------------------------------------------------
# complete — SDK integration via mock
# ---------------------------------------------------------------------------

def _mock_response(text="Hello", prompt_tokens=10, completion_tokens=5, total_tokens=15,
                   finish_reason="STOP", candidates=True, text_raises=False):
    """Build a mock GenerateContentResponse."""
    response = MagicMock()
    if text_raises:
        type(response).text = PropertyMock(side_effect=ValueError("function call"))
    else:
        response.text = text
    response.usage_metadata.prompt_token_count = prompt_tokens
    response.usage_metadata.candidates_token_count = completion_tokens
    response.usage_metadata.total_token_count = total_tokens
    if candidates:
        candidate = MagicMock()
        candidate.finish_reason = finish_reason
        candidate.content.parts = []
        response.candidates = [candidate]
    else:
        response.candidates = []
    return response


class TestComplete:
    def test_single_user_message(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(
                text="Hi there", prompt_tokens=5, completion_tokens=3, total_tokens=8
            )

            result = provider.complete([{"role": "user", "content": "Hello"}])

            assert result.content == "Hi there"
            assert result.usage["prompt_tokens"] == 5
            assert result.usage["completion_tokens"] == 3
            assert result.usage["total_tokens"] == 8
            mock_model.generate_content.assert_called_once_with("Hello")

    def test_system_message_extracted_as_instruction(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text="ok")

            provider.complete([
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hi"},
            ])

            call_kwargs = mock_genai.GenerativeModel.call_args[1]
            assert call_kwargs["system_instruction"] == "You are helpful"

    def test_assistant_role_mapped_to_model(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            chat = MagicMock()
            mock_model.start_chat.return_value = chat
            chat.send_message.return_value = _mock_response(text="reply")

            provider.complete([
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
                {"role": "user", "content": "More"},
            ])

            # Should start chat with history; second msg (assistant) mapped to 'model'
            history = mock_model.start_chat.call_args[1]["history"]
            assert history[0]["role"] == "user"
            assert history[1]["role"] == "model"
            assert history[1]["parts"] == ["Hi!"]

    def test_empty_messages_calls_generate_content_with_empty_string(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text="")

            result = provider.complete([])
            mock_model.generate_content.assert_called_once_with("")
            assert result.content == ""

    def test_response_format_json_object_string(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text='{"a":1}')

            provider.complete(
                [{"role": "user", "content": "json please"}],
                response_format="json_object",
            )

            gen_config = mock_genai.GenerativeModel.call_args[1]["generation_config"]
            assert gen_config["response_mime_type"] == "application/json"

    def test_response_format_json_object_dict(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text='{"a":1}')

            provider.complete(
                [{"role": "user", "content": "json please"}],
                response_format={"type": "json_object"},
            )

            gen_config = mock_genai.GenerativeModel.call_args[1]["generation_config"]
            assert gen_config["response_mime_type"] == "application/json"

    def test_response_format_json_schema_includes_schema(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text='{"x":1}')

            test_schema = {
                "type": "object",
                "properties": {"x": {"type": ["integer", "null"]}},
            }
            provider.complete(
                [{"role": "user", "content": "structured"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "test", "schema": test_schema},
                },
            )

            gen_config = mock_genai.GenerativeModel.call_args[1]["generation_config"]
            assert gen_config["response_mime_type"] == "application/json"
            # Schema should be normalized (array type → single)
            assert gen_config["response_schema"]["properties"]["x"]["type"] == "integer"

    def test_markdown_fences_stripped_for_json_response(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(
                text='```json\n{"result": true}\n```'
            )

            result = provider.complete(
                [{"role": "user", "content": "json"}],
                response_format="json_object",
            )
            assert result.content == '{"result": true}'

    def test_non_json_response_not_stripped(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(
                text='```python\nprint("hi")\n```'
            )

            result = provider.complete([{"role": "user", "content": "code"}])
            # Not expects_json, so fences should remain
            assert result.content == '```python\nprint("hi")\n```'

    def test_value_error_from_text_yields_empty_content(self):
        """When response has function calls, .text raises ValueError."""
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text_raises=True)

            result = provider.complete([{"role": "user", "content": "call a tool"}])
            assert result.content == ""

    def test_custom_model_passed_to_generative_model(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text="ok")

            provider.complete(
                [{"role": "user", "content": "Hi"}],
                model="gemini-1.5-pro-latest",
            )

            call_kwargs = mock_genai.GenerativeModel.call_args[1]
            assert call_kwargs["model_name"] == "gemini-1.5-pro-latest"

    def test_temperature_and_max_tokens_in_config(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text="ok")

            provider.complete(
                [{"role": "user", "content": "Hi"}],
                temperature=0.3,
                max_tokens=500,
            )

            gen_config = mock_genai.GenerativeModel.call_args[1]["generation_config"]
            assert gen_config["temperature"] == 0.3
            assert gen_config["max_output_tokens"] == 500

    def test_tools_converted_and_passed(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text="")

            tools = [{
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
            }]
            provider.complete([{"role": "user", "content": "Weather?"}], tools=tools)

            call_kwargs = mock_genai.GenerativeModel.call_args[1]
            tool_arg = call_kwargs["tools"][0]
            assert tool_arg["function_declarations"][0]["name"] == "get_weather"

    def test_no_candidates_yields_unknown_finish_reason(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text="ok", candidates=False)

            result = provider.complete([{"role": "user", "content": "Hi"}])
            assert result.finish_reason == "unknown"

    def test_finish_reason_from_candidate(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(
                text="ok", finish_reason="MAX_TOKENS"
            )

            result = provider.complete([{"role": "user", "content": "Hi"}])
            assert result.finish_reason == "MAX_TOKENS"

    def test_no_usage_metadata_yields_zeros(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            resp = MagicMock(spec=["text", "candidates"])
            resp.text = "ok"
            candidate = MagicMock()
            candidate.finish_reason = "STOP"
            candidate.content.parts = []
            resp.candidates = [candidate]
            mock_model.generate_content.return_value = resp

            result = provider.complete([{"role": "user", "content": "Hi"}])
            assert result.usage["prompt_tokens"] == 0
            assert result.usage["completion_tokens"] == 0
            assert result.usage["total_tokens"] == 0

    def test_multi_message_uses_chat(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            chat = MagicMock()
            mock_model.start_chat.return_value = chat
            chat.send_message.return_value = _mock_response(text="reply")

            result = provider.complete([
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ])

            # Last message sent via send_message, rest as history
            chat.send_message.assert_called_once_with("three")
            assert result.content == "reply"

    def test_system_instruction_not_set_when_no_system_message(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = _mock_response(text="ok")

            provider.complete([{"role": "user", "content": "Hi"}])

            call_kwargs = mock_genai.GenerativeModel.call_args[1]
            assert "system_instruction" not in call_kwargs


# ---------------------------------------------------------------------------
# stream_complete — SDK integration via mock
# ---------------------------------------------------------------------------

class TestStreamComplete:
    def test_single_message_streams_chunks(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            chunk1 = MagicMock()
            chunk1.text = "Hello "
            chunk2 = MagicMock()
            chunk2.text = "world"

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = iter([chunk1, chunk2])

            chunks = list(provider.stream_complete(
                [{"role": "user", "content": "Hi"}]
            ))

            assert chunks == ["Hello ", "world"]
            mock_model.generate_content.assert_called_once_with("Hi", stream=True)

    def test_multi_message_uses_chat_streaming(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            chunk = MagicMock()
            chunk.text = "response"

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            chat = MagicMock()
            mock_model.start_chat.return_value = chat
            chat.send_message.return_value = iter([chunk])

            chunks = list(provider.stream_complete([
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "second"},
                {"role": "user", "content": "third"},
            ]))

            assert chunks == ["response"]
            chat.send_message.assert_called_once_with("third", stream=True)

    def test_stream_skips_empty_text_chunks(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            chunk1 = MagicMock()
            chunk1.text = "data"
            chunk2 = MagicMock()
            chunk2.text = ""  # falsy
            chunk3 = MagicMock()
            chunk3.text = "more"

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = iter([chunk1, chunk2, chunk3])

            chunks = list(provider.stream_complete(
                [{"role": "user", "content": "Hi"}]
            ))

            assert chunks == ["data", "more"]

    def test_stream_system_message_extracted(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            chunk = MagicMock()
            chunk.text = "ok"

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = iter([chunk])

            list(provider.stream_complete([
                {"role": "system", "content": "Be concise"},
                {"role": "user", "content": "Hi"},
            ]))

            call_kwargs = mock_genai.GenerativeModel.call_args[1]
            assert call_kwargs["system_instruction"] == "Be concise"

    def test_stream_json_format_sets_mime_type(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            chunk = MagicMock()
            chunk.text = '{"a":1}'

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = iter([chunk])

            list(provider.stream_complete(
                [{"role": "user", "content": "json"}],
                response_format="json_object",
            ))

            gen_config = mock_genai.GenerativeModel.call_args[1]["generation_config"]
            assert gen_config["response_mime_type"] == "application/json"

    def test_stream_json_schema_normalizes_and_passes(self):
        with patch("civicos_services.providers.google_provider.genai") as mock_genai:
            from civicos_services.providers.google_provider import GoogleProvider
            provider = GoogleProvider(api_key="key")

            chunk = MagicMock()
            chunk.text = '{}'

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = iter([chunk])

            list(provider.stream_complete(
                [{"role": "user", "content": "structured"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "test",
                        "schema": {
                            "type": "object",
                            "properties": {"val": {"type": ["number", "null"]}},
                        },
                    },
                },
            ))

            gen_config = mock_genai.GenerativeModel.call_args[1]["generation_config"]
            assert gen_config["response_mime_type"] == "application/json"
            assert gen_config["response_schema"]["properties"]["val"]["type"] == "number"
