"""
Tests for issues/classifier.py — LLM-based 311 issue type classification.

The module is a thin service layer around the LLM provider. Its interesting
behavior lives in input construction (title/description truncation, JSON
payload assembly), output validation (taxonomy membership, case normalization,
markdown fence stripping), and error fallback paths. The LLM provider itself
is the external boundary and is mocked.

To run:
    pytest packages/civicos-services/tests/test_classifier.py -q --override-ini="addopts="
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from civicos.issues.classify import VALID_ISSUE_TYPES

from civicos_services.issues.classifier import (
    classify_issue_type,
    classify_issue_types_batch,
)


def _mock_response(content: str) -> SimpleNamespace:
    """Build a mock LLM provider response with a .content attribute."""
    return SimpleNamespace(content=content)


def _mock_provider(content: str) -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = _mock_response(content)
    return provider


# ---------------------------------------------------------------------------
# classify_issue_type — single classification
# ---------------------------------------------------------------------------


class TestClassifyIssueTypeSingle:
    def test_returns_valid_type_from_llm_response(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_type("Pothole on Main St")
        assert result == "pothole"

    def test_strips_whitespace_from_response(self):
        provider = _mock_provider("  graffiti  \n")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_type("Spray paint on wall")
        assert result == "graffiti"

    def test_lowercases_uppercase_response(self):
        provider = _mock_provider("STREETLIGHT")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_type("Light out")
        assert result == "streetlight"

    def test_mixed_case_response_is_normalized(self):
        provider = _mock_provider("Illegal_Dumping")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_type("Mattress dumped")
        assert result == "illegal_dumping"

    def test_invalid_type_falls_back_to_other(self):
        provider = _mock_provider("not_a_real_type")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_type("Something weird")
        assert result == "other"

    def test_empty_response_falls_back_to_other(self):
        # Empty string is not in VALID_ISSUE_TYPES, so becomes "other".
        provider = _mock_provider("")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_type("Ambiguous thing")
        assert result == "other"

    def test_provider_exception_during_complete_returns_other(self):
        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("API down")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_type("Pothole")
        assert result == "other"

    def test_provider_factory_exception_returns_other(self):
        with patch(
            "civicos_services.issues.classifier.get_provider",
            side_effect=RuntimeError("Anthropic provider not enabled"),
        ):
            result = classify_issue_type("Pothole")
        assert result == "other"

    def test_passes_title_in_user_content(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Huge pothole on Elm")

        messages = provider.complete.call_args.kwargs["messages"]
        user_content = messages[1]["content"]
        assert "Title: Huge pothole on Elm" in user_content

    def test_user_content_omits_description_line_when_empty(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Pothole", description="")

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        assert "Description:" not in user_content

    def test_user_content_includes_description_line_when_present(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Pothole", description="Near the crosswalk")

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        assert "Description: Near the crosswalk" in user_content

    def test_description_is_truncated_to_500_chars(self):
        long_desc = "x" * 800
        provider = _mock_provider("other")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Long issue", description=long_desc)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        # Exactly 500 x's should appear after the "Description: " marker.
        truncated = "Description: " + "x" * 500
        assert truncated in user_content
        assert ("Description: " + "x" * 501) not in user_content

    def test_description_exactly_500_chars_is_not_trimmed(self):
        exact_desc = "y" * 500
        provider = _mock_provider("other")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Edge", description=exact_desc)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        assert ("Description: " + "y" * 500) in user_content

    def test_uses_claude_haiku_model(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Pothole")

        kwargs = provider.complete.call_args.kwargs
        assert kwargs["model"] == "claude-3-5-haiku-20241022"

    def test_uses_temperature_zero(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Pothole")

        assert provider.complete.call_args.kwargs["temperature"] == 0

    def test_max_tokens_capped_at_20(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Pothole")

        assert provider.complete.call_args.kwargs["max_tokens"] == 20

    def test_messages_include_system_and_user_role(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Pothole")

        messages = provider.complete.call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_prompt_mentions_single_word_response(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Pothole")

        system_content = provider.complete.call_args.kwargs["messages"][0]["content"]
        assert "single word" in system_content.lower()

    def test_user_content_includes_taxonomy(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_type("Pothole")

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        # Taxonomy text from civicos.issues.classify._build_taxonomy_text
        assert "Issue type taxonomy:" in user_content
        assert "pothole" in user_content
        assert "graffiti" in user_content

    def test_requests_anthropic_provider(self):
        provider = _mock_provider("pothole")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ) as get_provider_mock:
            result = classify_issue_type("Pothole")

        # Pin both the outcome and the provider name. A silent switch to a
        # different provider would change the first positional arg here.
        assert result == "pothole"
        assert get_provider_mock.call_args.args == ("anthropic",)

    def test_every_valid_taxonomy_type_round_trips(self):
        # Guards against regressions in VALID_ISSUE_TYPES membership check.
        for valid_type in VALID_ISSUE_TYPES:
            provider = _mock_provider(valid_type)
            with patch(
                "civicos_services.issues.classifier.get_provider",
                return_value=provider,
            ):
                assert classify_issue_type("Some issue") == valid_type


# ---------------------------------------------------------------------------
# classify_issue_types_batch — batched classification
# ---------------------------------------------------------------------------


class TestClassifyIssueTypesBatch:
    def test_returns_mapping_for_each_issue(self):
        issues = [
            {"id": "1", "title": "Pothole", "description": ""},
            {"id": "2", "title": "Broken light", "description": ""},
        ]
        provider = _mock_provider('{"1": "pothole", "2": "streetlight"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)

        assert result == {"1": "pothole", "2": "streetlight"}

    def test_empty_issues_returns_empty_dict(self):
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=_mock_provider("{}"),
        ):
            result = classify_issue_types_batch([])
        assert result == {}

    def test_empty_issues_does_not_call_provider(self):
        provider = _mock_provider("{}")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch([])
        # With zero issues the for-loop body never runs → no API call and
        # an empty result dict.
        assert provider.complete.call_count == 0
        assert result == {}

    def test_strips_markdown_json_fence_prefix(self):
        issues = [{"id": "42", "title": "Graffiti", "description": ""}]
        provider = _mock_provider('```json\n{"42": "graffiti"}\n```')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"42": "graffiti"}

    def test_strips_bare_backtick_fence(self):
        issues = [{"id": "1", "title": "Pothole", "description": ""}]
        provider = _mock_provider('```\n{"1": "pothole"}\n```')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"1": "pothole"}

    def test_lowercases_uppercase_classification(self):
        issues = [{"id": "1", "title": "Pothole", "description": ""}]
        provider = _mock_provider('{"1": "POTHOLE"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"1": "pothole"}

    def test_invalid_type_maps_to_other(self):
        issues = [{"id": "1", "title": "Thing", "description": ""}]
        provider = _mock_provider('{"1": "not_a_type"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"1": "other"}

    def test_missing_id_in_response_defaults_to_other(self):
        # Provider only returned one of two issues — the missing one should
        # default to "other", not raise KeyError.
        issues = [
            {"id": "1", "title": "Pothole", "description": ""},
            {"id": "2", "title": "Graffiti", "description": ""},
        ]
        provider = _mock_provider('{"1": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"1": "pothole", "2": "other"}

    def test_integer_ids_are_stringified_in_result(self):
        issues = [{"id": 123, "title": "Pothole", "description": ""}]
        provider = _mock_provider('{"123": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"123": "pothole"}
        assert list(result.keys()) == ["123"]

    def test_provider_factory_failure_returns_all_other(self):
        issues = [
            {"id": "a", "title": "Thing1", "description": ""},
            {"id": "b", "title": "Thing2", "description": ""},
            {"id": "c", "title": "Thing3", "description": ""},
        ]
        with patch(
            "civicos_services.issues.classifier.get_provider",
            side_effect=RuntimeError("not available"),
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"a": "other", "b": "other", "c": "other"}

    def test_provider_factory_failure_stringifies_int_ids(self):
        issues = [{"id": 7, "title": "T", "description": ""}]
        with patch(
            "civicos_services.issues.classifier.get_provider",
            side_effect=RuntimeError("no provider"),
        ):
            result = classify_issue_types_batch(issues)
        # The factory-failure path uses issue["id"] directly (not str()).
        # Pin the actual current behavior so a refactor surfaces the choice.
        assert 7 in result
        assert result[7] == "other"

    def test_json_parse_error_falls_back_to_single_classification(self):
        issues = [
            {"id": "1", "title": "Pothole", "description": "desc"},
            {"id": "2", "title": "Graffiti", "description": "desc"},
        ]
        # First call returns garbage, subsequent single classification calls
        # return valid types.
        provider = MagicMock()
        provider.complete.side_effect = [
            _mock_response("not valid json {{"),  # batch call
            _mock_response("pothole"),             # single fallback for id=1
            _mock_response("graffiti"),            # single fallback for id=2
        ]
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)

        assert result == {"1": "pothole", "2": "graffiti"}
        assert provider.complete.call_count == 3

    def test_non_json_batch_exception_returns_other_for_batch(self):
        issues = [
            {"id": "1", "title": "Pothole", "description": ""},
            {"id": "2", "title": "Graffiti", "description": ""},
        ]
        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("timeout")
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"1": "other", "2": "other"}

    def test_respects_batch_size_splitting(self):
        issues = [
            {"id": str(i), "title": f"Issue {i}", "description": ""}
            for i in range(5)
        ]
        provider = MagicMock()
        provider.complete.side_effect = [
            _mock_response(json.dumps({"0": "pothole", "1": "pothole"})),
            _mock_response(json.dumps({"2": "graffiti", "3": "graffiti"})),
            _mock_response(json.dumps({"4": "streetlight"})),
        ]
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues, batch_size=2)

        assert result == {
            "0": "pothole",
            "1": "pothole",
            "2": "graffiti",
            "3": "graffiti",
            "4": "streetlight",
        }
        # 5 issues at batch_size=2 → 3 calls (2+2+1).
        assert provider.complete.call_count == 3

    def test_batch_size_larger_than_input_yields_single_call(self):
        issues = [
            {"id": "1", "title": "A", "description": ""},
            {"id": "2", "title": "B", "description": ""},
        ]
        provider = _mock_provider('{"1": "pothole", "2": "graffiti"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues, batch_size=100)
        assert provider.complete.call_count == 1
        assert result == {"1": "pothole", "2": "graffiti"}

    def test_default_batch_size_is_fifty(self):
        # 51 issues should produce exactly 2 API calls with default batch_size.
        issues = [
            {"id": str(i), "title": f"Issue {i}", "description": ""}
            for i in range(51)
        ]
        first_batch = {str(i): "pothole" for i in range(50)}
        second_batch = {"50": "graffiti"}
        provider = MagicMock()
        provider.complete.side_effect = [
            _mock_response(json.dumps(first_batch)),
            _mock_response(json.dumps(second_batch)),
        ]
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert provider.complete.call_count == 2
        assert result["0"] == "pothole"
        assert result["49"] == "pothole"
        assert result["50"] == "graffiti"

    def test_title_truncated_to_200_chars_in_payload(self):
        long_title = "T" * 400
        issues = [{"id": "1", "title": long_title, "description": ""}]
        provider = _mock_provider('{"1": "other"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        # Extract payload JSON from the user content
        payload_start = user_content.index("[")
        payload = json.loads(user_content[payload_start:])
        assert payload[0]["title"] == "T" * 200

    def test_description_truncated_to_300_chars_in_payload(self):
        long_desc = "D" * 500
        issues = [{"id": "1", "title": "x", "description": long_desc}]
        provider = _mock_provider('{"1": "other"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        payload_start = user_content.index("[")
        payload = json.loads(user_content[payload_start:])
        assert payload[0]["description"] == "D" * 300

    def test_empty_description_omitted_from_payload(self):
        issues = [{"id": "1", "title": "Pothole", "description": ""}]
        provider = _mock_provider('{"1": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        payload_start = user_content.index("[")
        payload = json.loads(user_content[payload_start:])
        assert "description" not in payload[0]
        assert payload[0]["title"] == "Pothole"

    def test_missing_description_key_omitted_from_payload(self):
        issues = [{"id": "1", "title": "Pothole"}]  # no description at all
        provider = _mock_provider('{"1": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        payload_start = user_content.index("[")
        payload = json.loads(user_content[payload_start:])
        assert "description" not in payload[0]

    def test_non_empty_description_included_in_payload(self):
        issues = [
            {"id": "1", "title": "Pothole", "description": "Near school"},
        ]
        provider = _mock_provider('{"1": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        payload_start = user_content.index("[")
        payload = json.loads(user_content[payload_start:])
        assert payload[0]["description"] == "Near school"

    def test_integer_ids_stringified_in_payload(self):
        issues = [{"id": 77, "title": "Pothole", "description": ""}]
        provider = _mock_provider('{"77": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        payload_start = user_content.index("[")
        payload = json.loads(user_content[payload_start:])
        assert payload[0]["id"] == "77"

    def test_uses_batch_system_prompt(self):
        issues = [{"id": "1", "title": "Pothole", "description": ""}]
        provider = _mock_provider('{"1": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)

        system_content = provider.complete.call_args.kwargs["messages"][0]["content"]
        # Batch prompt explicitly asks for JSON object mapping id -> type.
        assert "JSON" in system_content
        assert "id" in system_content

    def test_batch_uses_haiku_model(self):
        issues = [{"id": "1", "title": "Pothole", "description": ""}]
        provider = _mock_provider('{"1": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)
        assert provider.complete.call_args.kwargs["model"] == "claude-3-5-haiku-20241022"

    def test_batch_max_tokens_is_2000(self):
        issues = [{"id": "1", "title": "Pothole", "description": ""}]
        provider = _mock_provider('{"1": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)
        # 2000 is much larger than single (20) to fit a JSON map for 50 issues.
        assert provider.complete.call_args.kwargs["max_tokens"] == 2000

    def test_batch_temperature_is_zero(self):
        issues = [{"id": "1", "title": "Pothole", "description": ""}]
        provider = _mock_provider('{"1": "pothole"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)
        assert provider.complete.call_args.kwargs["temperature"] == 0

    def test_payload_is_json_array(self):
        issues = [
            {"id": "1", "title": "Pothole", "description": ""},
            {"id": "2", "title": "Graffiti", "description": "on wall"},
        ]
        provider = _mock_provider('{"1": "pothole", "2": "graffiti"}')
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            classify_issue_types_batch(issues)

        user_content = provider.complete.call_args.kwargs["messages"][1]["content"]
        payload_start = user_content.index("[")
        payload = json.loads(user_content[payload_start:])
        assert isinstance(payload, list)
        assert len(payload) == 2
        assert payload[0]["id"] == "1"
        assert payload[1]["id"] == "2"
        assert payload[1]["description"] == "on wall"

    def test_partial_batch_response_fills_missing_with_other(self):
        # Batch returns some valid, some invalid, some missing.
        issues = [
            {"id": "a", "title": "x", "description": ""},
            {"id": "b", "title": "y", "description": ""},
            {"id": "c", "title": "z", "description": ""},
        ]
        provider = _mock_provider(
            '{"a": "pothole", "b": "bogus_type"}'
        )  # "c" missing entirely
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues)
        assert result == {"a": "pothole", "b": "other", "c": "other"}

    def test_second_batch_fallback_does_not_affect_first(self):
        # Split across two batches: first succeeds, second fails with JSON error.
        # First batch should still get real types; second falls back to single calls.
        issues = [
            {"id": "1", "title": "Pothole", "description": ""},
            {"id": "2", "title": "Graffiti", "description": ""},
            {"id": "3", "title": "Light", "description": ""},
            {"id": "4", "title": "Sidewalk", "description": ""},
        ]
        provider = MagicMock()
        provider.complete.side_effect = [
            _mock_response('{"1": "pothole", "2": "graffiti"}'),  # batch 1 OK
            _mock_response("invalid }}{ json"),                    # batch 2 bad
            _mock_response("streetlight"),                          # single for id=3
            _mock_response("sidewalk"),                             # single for id=4
        ]
        with patch(
            "civicos_services.issues.classifier.get_provider",
            return_value=provider,
        ):
            result = classify_issue_types_batch(issues, batch_size=2)

        assert result == {
            "1": "pothole",
            "2": "graffiti",
            "3": "streetlight",
            "4": "sidewalk",
        }
