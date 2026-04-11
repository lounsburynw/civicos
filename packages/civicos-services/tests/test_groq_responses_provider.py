"""
Tests for groq_responses_provider.py — Groq Responses API provider.

Pure-logic methods (_convert_response_format, _extract_content) are tested
with real inputs and pinned outputs. HTTP-touching methods (complete,
stream_complete) mock requests.post only; GroqResponsesProvider itself is
never mocked.

To run:
    pytest packages/civicos-services/tests/test_groq_responses_provider.py \
        -q --override-ini="addopts="
"""

import os
from unittest.mock import patch, MagicMock

import pytest

from civicos_services.providers.base import CompletionResponse, ToolCall
from civicos_services.providers.groq_responses_provider import GroqResponsesProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_http_response(
    status_code=200,
    json_data=None,
    text="",
):
    """Build a mock requests.Response with the fields complete() reads."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


def _make_api_result(
    content_text="Hello world",
    status="completed",
    model="openai/gpt-oss-20b",
    input_tokens=12,
    output_tokens=7,
    total_tokens=19,
    output=None,
    usage=None,
):
    """Build a Groq Responses API JSON payload."""
    if output is None:
        output = [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": content_text},
                ],
            }
        ]
    if usage is None:
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
    return {
        "status": status,
        "model": model,
        "output": output,
        "usage": usage,
    }


def _clean_env():
    """Ensure GROQ_API_KEY is not set so constructor default is deterministic."""
    patcher = patch.dict(os.environ, {}, clear=False)
    patcher.start()
    os.environ.pop("GROQ_API_KEY", None)
    return patcher


# ---------------------------------------------------------------------------
# Construction & properties
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_explicit_api_key_stored(self):
        p = GroqResponsesProvider(api_key="my-key-123")
        assert p.api_key == "my-key-123"

    def test_api_key_falls_back_to_env_var(self):
        patcher = _clean_env()
        try:
            os.environ["GROQ_API_KEY"] = "env-key-xyz"
            p = GroqResponsesProvider()
            assert p.api_key == "env-key-xyz"
        finally:
            patcher.stop()

    def test_explicit_api_key_overrides_env_var(self):
        patcher = _clean_env()
        try:
            os.environ["GROQ_API_KEY"] = "env-key"
            p = GroqResponsesProvider(api_key="explicit-key")
            assert p.api_key == "explicit-key"
        finally:
            patcher.stop()

    def test_no_api_key_anywhere_is_none(self):
        patcher = _clean_env()
        try:
            p = GroqResponsesProvider()
            assert p.api_key is None
        finally:
            patcher.stop()

    def test_default_base_url_is_groq_v1(self):
        p = GroqResponsesProvider(api_key="k")
        assert p.base_url == "https://api.groq.com/openai/v1"

    def test_default_model_is_gpt_oss_20b(self):
        p = GroqResponsesProvider(api_key="k")
        assert p.default_model == "openai/gpt-oss-20b"

    def test_custom_model_override(self):
        p = GroqResponsesProvider(api_key="k", model="openai/gpt-oss-120b")
        assert p.default_model == "openai/gpt-oss-120b"

    def test_name_is_groq_responses(self):
        p = GroqResponsesProvider(api_key="k")
        assert p.name == "groq-responses"


# ---------------------------------------------------------------------------
# _convert_response_format — pure logic
# ---------------------------------------------------------------------------

class TestConvertResponseFormat:
    def setup_method(self):
        self.provider = GroqResponsesProvider(api_key="k")

    def test_json_schema_conversion_pulls_name_and_schema(self):
        rf = {
            "type": "json_schema",
            "json_schema": {
                "name": "navigation",
                "schema": {"type": "object", "properties": {"url": {"type": "string"}}},
            },
        }
        result = self.provider._convert_response_format(rf)
        assert result == {
            "format": {
                "type": "json_schema",
                "name": "navigation",
                "schema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                },
            }
        }

    def test_json_schema_missing_name_defaults_to_response(self):
        rf = {
            "type": "json_schema",
            "json_schema": {
                "schema": {"type": "object"},
            },
        }
        result = self.provider._convert_response_format(rf)
        assert result["format"]["name"] == "response"
        assert result["format"]["type"] == "json_schema"
        assert result["format"]["schema"] == {"type": "object"}

    def test_json_schema_missing_schema_defaults_to_empty_dict(self):
        rf = {
            "type": "json_schema",
            "json_schema": {"name": "thing"},
        }
        result = self.provider._convert_response_format(rf)
        assert result["format"]["schema"] == {}
        assert result["format"]["name"] == "thing"

    def test_json_schema_missing_json_schema_key_uses_all_defaults(self):
        rf = {"type": "json_schema"}
        result = self.provider._convert_response_format(rf)
        assert result == {
            "format": {
                "type": "json_schema",
                "name": "response",
                "schema": {},
            }
        }

    def test_json_object_conversion(self):
        rf = {"type": "json_object"}
        result = self.provider._convert_response_format(rf)
        assert result == {"format": {"type": "json_object"}}

    def test_unknown_type_falls_back_to_text(self):
        rf = {"type": "something_else"}
        result = self.provider._convert_response_format(rf)
        assert result == {"format": {"type": "text"}}

    def test_missing_type_falls_back_to_text(self):
        rf = {"foo": "bar"}
        result = self.provider._convert_response_format(rf)
        assert result == {"format": {"type": "text"}}

    def test_empty_dict_falls_back_to_text(self):
        result = self.provider._convert_response_format({})
        assert result == {"format": {"type": "text"}}

    def test_complex_nested_schema_preserved_verbatim(self):
        nested = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                        "required": ["id"],
                    },
                },
            },
            "required": ["items"],
        }
        rf = {
            "type": "json_schema",
            "json_schema": {"name": "list_resp", "schema": nested},
        }
        result = self.provider._convert_response_format(rf)
        assert result["format"]["schema"] == nested
        # Verify it's the same dict content (not transformed)
        assert result["format"]["schema"]["properties"]["items"]["items"][
            "properties"
        ]["id"]["type"] == "integer"


# ---------------------------------------------------------------------------
# _extract_content — pure logic
# ---------------------------------------------------------------------------

class TestExtractContent:
    def setup_method(self):
        self.provider = GroqResponsesProvider(api_key="k")

    def test_extracts_text_from_message_output(self):
        result = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "the answer"},
                    ],
                }
            ]
        }
        assert self.provider._extract_content(result) == "the answer"

    def test_returns_first_output_text_encountered(self):
        """Iteration stops at the first output_text block."""
        result = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "first"},
                        {"type": "output_text", "text": "second"},
                    ],
                }
            ]
        }
        assert self.provider._extract_content(result) == "first"

    def test_skips_non_message_types_and_finds_message(self):
        result = {
            "output": [
                {"type": "reasoning", "summary": "thinking..."},
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "done thinking"},
                    ],
                },
            ]
        }
        assert self.provider._extract_content(result) == "done thinking"

    def test_skips_non_output_text_content_types(self):
        result = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "refusal", "text": "nope"},
                        {"type": "output_text", "text": "yes"},
                    ],
                }
            ]
        }
        assert self.provider._extract_content(result) == "yes"

    def test_empty_output_returns_empty_string(self):
        assert self.provider._extract_content({"output": []}) == ""

    def test_missing_output_key_returns_empty_string(self):
        assert self.provider._extract_content({}) == ""

    def test_message_with_no_content_returns_empty_string(self):
        result = {"output": [{"type": "message"}]}
        assert self.provider._extract_content(result) == ""

    def test_message_with_empty_content_array_returns_empty_string(self):
        result = {"output": [{"type": "message", "content": []}]}
        assert self.provider._extract_content(result) == ""

    def test_output_text_missing_text_field_returns_empty_string(self):
        result = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text"}],
                }
            ]
        }
        assert self.provider._extract_content(result) == ""

    def test_only_reasoning_output_returns_empty_string(self):
        """No message output at all means empty string (fallback)."""
        result = {
            "output": [
                {"type": "reasoning", "summary": "thinking..."},
            ]
        }
        assert self.provider._extract_content(result) == ""

    def test_explicit_empty_text_preserved(self):
        result = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": ""}],
                }
            ]
        }
        assert self.provider._extract_content(result) == ""


# ---------------------------------------------------------------------------
# parse_tool_calls — always empty for this provider
# ---------------------------------------------------------------------------

class TestParseToolCalls:
    def setup_method(self):
        self.provider = GroqResponsesProvider(api_key="k")

    def test_returns_empty_list_for_none(self):
        assert self.provider.parse_tool_calls(None) == []

    def test_returns_empty_list_for_dict_response(self):
        assert self.provider.parse_tool_calls({"output": []}) == []

    def test_returns_empty_list_for_populated_response(self):
        # Even when the response has content, this provider never reports tool calls
        result = _make_api_result(content_text="hi")
        assert self.provider.parse_tool_calls(result) == []


# ---------------------------------------------------------------------------
# complete — HTTP boundary mocked via requests.post
# ---------------------------------------------------------------------------

class TestComplete:
    def setup_method(self):
        self.provider = GroqResponsesProvider(api_key="test-key")

    def _patch_post(self, response):
        return patch(
            "civicos_services.providers.groq_responses_provider.requests.post",
            return_value=response,
        )

    def test_returns_completion_response_with_content(self):
        api_result = _make_api_result(content_text="Hi there")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hello"}])

        assert isinstance(result, CompletionResponse)
        assert result.content == "Hi there"

    def test_usage_tokens_mapped_from_groq_field_names(self):
        api_result = _make_api_result(
            input_tokens=123,
            output_tokens=45,
            total_tokens=168,
        )
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.usage["prompt_tokens"] == 123
        assert result.usage["completion_tokens"] == 45
        assert result.usage["total_tokens"] == 168

    def test_missing_usage_defaults_to_zero(self):
        api_result = _make_api_result()
        api_result["usage"] = {}
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.usage["prompt_tokens"] == 0
        assert result.usage["completion_tokens"] == 0
        assert result.usage["total_tokens"] == 0

    def test_missing_usage_key_entirely_defaults_to_zero(self):
        api_result = _make_api_result()
        api_result.pop("usage")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.usage["prompt_tokens"] == 0
        assert result.usage["completion_tokens"] == 0
        assert result.usage["total_tokens"] == 0

    def test_finish_reason_from_status_field(self):
        api_result = _make_api_result(status="incomplete")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.finish_reason == "incomplete"

    def test_finish_reason_defaults_to_completed_when_status_missing(self):
        api_result = _make_api_result()
        api_result.pop("status")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.finish_reason == "completed"

    def test_tool_calls_always_empty(self):
        """Responses API provider intentionally does not return tool_calls."""
        api_result = _make_api_result()
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.tool_calls == []

    def test_provider_name_propagated(self):
        api_result = _make_api_result()
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.provider_name == "groq-responses"

    def test_model_from_response_populates_model_field(self):
        api_result = _make_api_result(model="openai/gpt-oss-20b-0925")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.model == "openai/gpt-oss-20b-0925"

    def test_missing_model_in_response_falls_back_to_default(self):
        api_result = _make_api_result()
        api_result.pop("model")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.model == "openai/gpt-oss-20b"

    def test_raw_response_is_parsed_json(self):
        api_result = _make_api_result(content_text="raw")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.raw_response == api_result

    def test_request_posts_to_responses_endpoint(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete([{"role": "user", "content": "Hi"}])

        called_url = mock_post.call_args[0][0]
        assert called_url == "https://api.groq.com/openai/v1/responses"

    def test_request_sends_bearer_authorization_header(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete([{"role": "user", "content": "Hi"}])

        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"

    def test_request_uses_30_second_timeout(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete([{"role": "user", "content": "Hi"}])

        assert mock_post.call_args.kwargs["timeout"] == 30

    def test_request_body_uses_input_key_not_messages(self):
        """Responses API uses 'input' instead of 'messages' — critical fidelity."""
        http_resp = _make_http_response(json_data=_make_api_result())
        messages = [{"role": "user", "content": "Hi"}]
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete(messages)

        body = mock_post.call_args.kwargs["json"]
        assert body["input"] == messages
        assert "messages" not in body

    def test_request_body_default_model(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete([{"role": "user", "content": "Hi"}])

        body = mock_post.call_args.kwargs["json"]
        assert body["model"] == "openai/gpt-oss-20b"

    def test_request_body_custom_model_overrides_default(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete(
                [{"role": "user", "content": "Hi"}],
                model="openai/gpt-oss-120b",
            )

        body = mock_post.call_args.kwargs["json"]
        assert body["model"] == "openai/gpt-oss-120b"

    def test_request_body_default_temperature_is_0_7(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete([{"role": "user", "content": "Hi"}])

        body = mock_post.call_args.kwargs["json"]
        assert body["temperature"] == 0.7

    def test_request_body_custom_temperature_passed_through(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete(
                [{"role": "user", "content": "Hi"}],
                temperature=0.2,
            )

        body = mock_post.call_args.kwargs["json"]
        assert body["temperature"] == 0.2

    def test_request_body_max_tokens_maps_to_max_output_tokens(self):
        """Responses API uses 'max_output_tokens', not 'max_tokens'."""
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete(
                [{"role": "user", "content": "Hi"}],
                max_tokens=500,
            )

        body = mock_post.call_args.kwargs["json"]
        assert body["max_output_tokens"] == 500
        assert "max_tokens" not in body

    def test_request_body_default_max_tokens_is_2000(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete([{"role": "user", "content": "Hi"}])

        body = mock_post.call_args.kwargs["json"]
        assert body["max_output_tokens"] == 2000

    def test_request_body_max_tokens_zero_omits_field(self):
        """0 is falsy — max_output_tokens is not set when max_tokens=0."""
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete(
                [{"role": "user", "content": "Hi"}],
                max_tokens=0,
            )

        body = mock_post.call_args.kwargs["json"]
        assert "max_output_tokens" not in body

    def test_request_body_response_format_converted_to_text_key(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete(
                [{"role": "user", "content": "Hi"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "nav",
                        "schema": {"type": "object"},
                    },
                },
            )

        body = mock_post.call_args.kwargs["json"]
        assert body["text"] == {
            "format": {
                "type": "json_schema",
                "name": "nav",
                "schema": {"type": "object"},
            }
        }

    def test_request_body_no_response_format_omits_text_key(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete([{"role": "user", "content": "Hi"}])

        body = mock_post.call_args.kwargs["json"]
        assert "text" not in body

    def test_request_body_never_includes_reasoning_by_default(self):
        """Reasoning is opt-in via kwargs only — see source comment."""
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete([{"role": "user", "content": "Hi"}])

        body = mock_post.call_args.kwargs["json"]
        assert "reasoning" not in body

    def test_request_body_extra_kwargs_merged(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete(
                [{"role": "user", "content": "Hi"}],
                top_p=0.9,
                reasoning={"effort": "low"},
            )

        body = mock_post.call_args.kwargs["json"]
        assert body["top_p"] == 0.9
        assert body["reasoning"] == {"effort": "low"}

    def test_tools_argument_is_not_sent_in_request_body(self):
        """Responses API path explicitly does not pass 'tools' through."""
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.complete(
                [{"role": "user", "content": "Hi"}],
                tools=[{"name": "search", "description": "s", "parameters": {}}],
            )

        body = mock_post.call_args.kwargs["json"]
        assert "tools" not in body

    def test_non_200_status_raises_with_code_and_body(self):
        http_resp = _make_http_response(
            status_code=429,
            text="rate limited",
        )
        with self._patch_post(http_resp):
            with pytest.raises(Exception, match="429") as exc_info:
                self.provider.complete([{"role": "user", "content": "Hi"}])

        # Ensure the error message surfaces the response body too
        assert "rate limited" in str(exc_info.value)
        assert "Groq Responses API error" in str(exc_info.value)

    def test_500_status_raises(self):
        http_resp = _make_http_response(
            status_code=500,
            text="internal error",
        )
        with self._patch_post(http_resp):
            with pytest.raises(Exception, match="500"):
                self.provider.complete([{"role": "user", "content": "Hi"}])

    def test_empty_output_yields_empty_content_no_error(self):
        api_result = _make_api_result(output=[])
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.complete([{"role": "user", "content": "Hi"}])

        assert result.content == ""
        # Usage should still come through from the api_result
        assert result.usage["prompt_tokens"] == 12


# ---------------------------------------------------------------------------
# stream_complete — falls back to non-streaming
# ---------------------------------------------------------------------------

class TestStreamComplete:
    def setup_method(self):
        self.provider = GroqResponsesProvider(api_key="test-key")

    def _patch_post(self, response):
        return patch(
            "civicos_services.providers.groq_responses_provider.requests.post",
            return_value=response,
        )

    def test_yields_single_chunk_with_full_content(self):
        api_result = _make_api_result(content_text="the whole thing at once")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            chunks = list(self.provider.stream_complete(
                [{"role": "user", "content": "Hi"}]
            ))

        assert chunks == ["the whole thing at once"]

    def test_yields_empty_string_when_content_empty(self):
        api_result = _make_api_result(content_text="")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            chunks = list(self.provider.stream_complete(
                [{"role": "user", "content": "Hi"}]
            ))

        assert chunks == [""]

    def test_stream_propagates_temperature(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            list(self.provider.stream_complete(
                [{"role": "user", "content": "Hi"}],
                temperature=0.1,
            ))

        body = mock_post.call_args.kwargs["json"]
        assert body["temperature"] == 0.1

    def test_stream_propagates_custom_model(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            list(self.provider.stream_complete(
                [{"role": "user", "content": "Hi"}],
                model="openai/gpt-oss-120b",
            ))

        body = mock_post.call_args.kwargs["json"]
        assert body["model"] == "openai/gpt-oss-120b"

    def test_stream_propagates_max_tokens(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            list(self.provider.stream_complete(
                [{"role": "user", "content": "Hi"}],
                max_tokens=100,
            ))

        body = mock_post.call_args.kwargs["json"]
        assert body["max_output_tokens"] == 100

    def test_stream_propagates_extra_kwargs(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            list(self.provider.stream_complete(
                [{"role": "user", "content": "Hi"}],
                top_p=0.8,
            ))

        body = mock_post.call_args.kwargs["json"]
        assert body["top_p"] == 0.8

    def test_stream_raises_on_http_error(self):
        http_resp = _make_http_response(status_code=401, text="unauthorized")
        with self._patch_post(http_resp):
            with pytest.raises(Exception, match="401"):
                list(self.provider.stream_complete(
                    [{"role": "user", "content": "Hi"}]
                ))


# ---------------------------------------------------------------------------
# Integration: chat() convenience wrapper from base class
# ---------------------------------------------------------------------------

class TestChatWrapper:
    """chat() is a base-class convenience — verify it works end-to-end."""

    def setup_method(self):
        self.provider = GroqResponsesProvider(api_key="test-key")

    def _patch_post(self, response):
        return patch(
            "civicos_services.providers.groq_responses_provider.requests.post",
            return_value=response,
        )

    def test_chat_returns_content_string(self):
        api_result = _make_api_result(content_text="just the text")
        http_resp = _make_http_response(json_data=api_result)
        with self._patch_post(http_resp):
            result = self.provider.chat([{"role": "user", "content": "Hi"}])

        assert result == "just the text"

    def test_chat_json_object_shorthand_converted_to_response_format(self):
        http_resp = _make_http_response(json_data=_make_api_result())
        with self._patch_post(http_resp) as mock_post:
            self.provider.chat(
                [{"role": "user", "content": "Hi"}],
                response_format="json_object",
            )

        body = mock_post.call_args.kwargs["json"]
        assert body["text"] == {"format": {"type": "json_object"}}
