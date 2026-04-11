"""
Tests for issues/issue_detector.py — LLM-based complaint intent detection.

The module has a few layers worth isolating:
- `ComplaintIntent.to_dict` — pure dataclass serialization, no mocks.
- `IssueDetector._safe_json_parse` — pure string parsing with fence stripping.
- `IssueDetector._resolve_jurisdiction` — small logic around the jurisdiction
  registry (patched) and user-context fallback.
- `IssueDetector._extract_complaint_fields` / `detect_complaint` — the LLM
  boundary; the OpenAI client is mocked, the subject under test is not.

To run:
    pytest packages/civicos-services/tests/test_issue_detector.py -q --override-ini="addopts="
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.issues.issue_detector import (
    ComplaintIntent,
    IssueDetector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response(content: str) -> SimpleNamespace:
    """Shape a mock OpenAI chat.completions response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _detector_with_llm(content: str) -> tuple[IssueDetector, MagicMock]:
    """Build an IssueDetector whose OpenAI client returns `content`."""
    with patch("civicos_services.issues.issue_detector.openai.OpenAI") as mock_openai:
        client = MagicMock()
        client.chat.completions.create.return_value = _llm_response(content)
        mock_openai.return_value = client
        detector = IssueDetector(openai_api_key="sk-test-fake")
    return detector, client


def _detector_with_side_effect(side_effect) -> tuple[IssueDetector, MagicMock]:
    with patch("civicos_services.issues.issue_detector.openai.OpenAI") as mock_openai:
        client = MagicMock()
        client.chat.completions.create.side_effect = side_effect
        mock_openai.return_value = client
        detector = IssueDetector(openai_api_key="sk-test-fake")
    return detector, client


# ---------------------------------------------------------------------------
# ComplaintIntent dataclass — pure, no mocks
# ---------------------------------------------------------------------------


class TestComplaintIntent:
    def test_to_dict_contains_all_fields(self):
        intent = ComplaintIntent(
            description="Pothole on 4th Street",
            issue_type="infrastructure",
            jurisdiction_id="city-san-rafael",
            location_mention="San Rafael",
            confidence="high",
        )
        assert intent.to_dict() == {
            "description": "Pothole on 4th Street",
            "issue_type": "infrastructure",
            "jurisdiction_id": "city-san-rafael",
            "location_mention": "San Rafael",
            "confidence": "high",
        }

    def test_defaults_confidence_to_medium(self):
        intent = ComplaintIntent(
            description="Broken streetlight",
            issue_type="infrastructure",
        )
        assert intent.confidence == "medium"
        assert intent.jurisdiction_id is None
        assert intent.location_mention is None

    def test_to_dict_preserves_none_optional_fields(self):
        intent = ComplaintIntent(
            description="desc",
            issue_type="housing",
        )
        d = intent.to_dict()
        assert d["jurisdiction_id"] is None
        assert d["location_mention"] is None
        assert d["confidence"] == "medium"
        # description and issue_type are still present
        assert d["description"] == "desc"
        assert d["issue_type"] == "housing"

    def test_to_dict_has_exactly_five_keys(self):
        intent = ComplaintIntent(description="d", issue_type="community")
        assert set(intent.to_dict().keys()) == {
            "description",
            "issue_type",
            "jurisdiction_id",
            "location_mention",
            "confidence",
        }


# ---------------------------------------------------------------------------
# IssueDetector.__init__
# ---------------------------------------------------------------------------


class TestIssueDetectorInit:
    def test_uses_explicit_api_key_when_provided(self):
        with patch(
            "civicos_services.issues.issue_detector.openai.OpenAI"
        ) as mock_openai:
            IssueDetector(openai_api_key="sk-explicit-key")
        assert mock_openai.call_args.kwargs["api_key"] == "sk-explicit-key"

    def test_falls_back_to_env_var_when_no_key(self):
        with patch(
            "civicos_services.issues.issue_detector.openai.OpenAI"
        ) as mock_openai, patch.dict(
            "os.environ", {"OPENAI_API_KEY": "sk-env-key"}, clear=False
        ):
            IssueDetector()
        assert mock_openai.call_args.kwargs["api_key"] == "sk-env-key"

    def test_explicit_key_preferred_over_env_var(self):
        with patch(
            "civicos_services.issues.issue_detector.openai.OpenAI"
        ) as mock_openai, patch.dict(
            "os.environ", {"OPENAI_API_KEY": "sk-env-key"}, clear=False
        ):
            IssueDetector(openai_api_key="sk-override")
        assert mock_openai.call_args.kwargs["api_key"] == "sk-override"


# ---------------------------------------------------------------------------
# detect_complaint — top-level behavior
# ---------------------------------------------------------------------------


class TestDetectComplaintShortCircuits:
    def test_empty_string_returns_none_without_calling_llm(self):
        detector, client = _detector_with_llm("{}")
        result = detector.detect_complaint("")
        assert result is None
        assert client.chat.completions.create.call_count == 0

    def test_none_message_returns_none_without_calling_llm(self):
        detector, client = _detector_with_llm("{}")
        result = detector.detect_complaint(None)
        assert result is None
        assert client.chat.completions.create.call_count == 0

    def test_whitespace_only_message_returns_none(self):
        detector, client = _detector_with_llm("{}")
        result = detector.detect_complaint("   \n\t  ")
        assert result is None
        assert client.chat.completions.create.call_count == 0

    def test_short_message_under_10_chars_returns_none(self):
        detector, client = _detector_with_llm("{}")
        # 9 characters — below the 10-char threshold
        result = detector.detect_complaint("too short")
        assert result is None
        assert client.chat.completions.create.call_count == 0

    def test_message_with_9_stripped_chars_returns_none(self):
        # 9 non-whitespace chars after strip (but 11 with padding).
        # The module checks len(message.strip()) < 10, so this is below.
        detector, client = _detector_with_llm("{}")
        result = detector.detect_complaint("  abcdefghi  ")
        assert result is None
        assert client.chat.completions.create.call_count == 0

    def test_message_with_exactly_10_chars_passes_short_circuit(self):
        # 10 chars: is at the boundary — `< 10` is False, so we should
        # proceed to call the LLM. With is_complaint=false, the LLM path
        # should still resolve to None (not short-circuit None).
        detector, client = _detector_with_llm('{"is_complaint": false}')
        result = detector.detect_complaint("abcdefghij")  # 10 chars
        assert client.chat.completions.create.call_count == 1
        # Confirm the LLM's is_complaint=false response is honored,
        # proving we went through the LLM path (not the short-circuit)
        assert result is None
        # And that the message the LLM received is the 10-char boundary input
        user_msg = client.chat.completions.create.call_args.kwargs["messages"][1][
            "content"
        ]
        assert "abcdefghij" in user_msg


class TestDetectComplaintLLMResult:
    def test_non_complaint_response_returns_none(self):
        detector, _ = _detector_with_llm('{"is_complaint": false}')
        result = detector.detect_complaint("When is the next city council meeting?")
        assert result is None

    def test_llm_returns_none_json_returns_none(self):
        detector, _ = _detector_with_llm("not valid json at all {{{")
        result = detector.detect_complaint("My landlord won't fix the heater")
        assert result is None

    def test_complaint_returns_complaint_intent(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "Heater broken, landlord unresponsive", '
            '"issue_type": "housing", '
            '"location_mention": null, '
            '"confidence": "high"}'
        )
        result = detector.detect_complaint("My landlord won't fix the heater")
        assert isinstance(result, ComplaintIntent)
        assert result.description == "Heater broken, landlord unresponsive"
        assert result.issue_type == "housing"
        assert result.confidence == "high"
        assert result.location_mention is None

    def test_missing_description_falls_back_to_original_message(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, "issue_type": "housing"}'
        )
        original = "My landlord refuses to fix the leak in my ceiling"
        result = detector.detect_complaint(original)
        assert result is not None
        assert result.description == original

    def test_missing_issue_type_defaults_to_community(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, "description": "some problem"}'
        )
        result = detector.detect_complaint("Community center closed again")
        assert result is not None
        assert result.issue_type == "community"

    def test_missing_confidence_defaults_to_medium(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "d", "issue_type": "housing"}'
        )
        result = detector.detect_complaint("My landlord refuses repairs")
        assert result is not None
        assert result.confidence == "medium"

    def test_location_mention_is_preserved_on_intent(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "Homeless encampment growing", '
            '"issue_type": "community", '
            '"location_mention": "Berkeley", '
            '"confidence": "medium"}'
        )
        # No jurisdiction registry entry for Berkeley in most fixtures — we
        # only care that the raw string is preserved on the intent.
        with patch(
            "civicos_services.issues.issue_detector.IssueDetector._resolve_jurisdiction",
            return_value="city-berkeley",
        ):
            result = detector.detect_complaint(
                "There's a growing encampment downtown that needs attention"
            )
        assert result is not None
        assert result.location_mention == "Berkeley"
        assert result.jurisdiction_id == "city-berkeley"

    def test_is_complaint_false_key_returns_none_even_with_description(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": false, "description": "not really a complaint"}'
        )
        result = detector.detect_complaint(
            "What's the zoning code for my neighborhood?"
        )
        assert result is None

    def test_missing_is_complaint_key_returns_none(self):
        # Without `is_complaint` the truthiness check short-circuits to False.
        detector, _ = _detector_with_llm(
            '{"description": "something", "issue_type": "housing"}'
        )
        result = detector.detect_complaint("My heater has been broken for weeks")
        assert result is None

    def test_empty_json_object_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        result = detector.detect_complaint("My heater has been broken for weeks")
        assert result is None

    def test_llm_exception_returns_none(self):
        detector, _ = _detector_with_side_effect(RuntimeError("API down"))
        result = detector.detect_complaint("My landlord is refusing to fix the heat")
        assert result is None


class TestDetectComplaintJurisdictionResolution:
    def test_uses_user_context_jurisdiction_when_no_location_mention(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "Pothole on Main", '
            '"issue_type": "infrastructure", '
            '"location_mention": null, '
            '"confidence": "high"}'
        )
        result = detector.detect_complaint(
            "There's a huge pothole on my street",
            user_context={"jurisdiction_id": "city-san-rafael"},
        )
        assert result is not None
        assert result.jurisdiction_id == "city-san-rafael"

    def test_location_mention_resolves_via_registry(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "Pothole", '
            '"issue_type": "infrastructure", '
            '"location_mention": "San Rafael", '
            '"confidence": "high"}'
        )
        with patch(
            "civicos_config.jurisdiction.JurisdictionRegistry.get_location_display_name",
            return_value="city-san-rafael",
        ) as mock_registry:
            result = detector.detect_complaint(
                "There's a huge pothole on 4th Street in San Rafael"
            )
        assert result is not None
        assert result.jurisdiction_id == "city-san-rafael"
        assert mock_registry.call_args.args == ("San Rafael",)

    def test_registry_hit_preferred_over_user_context(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "d", '
            '"issue_type": "infrastructure", '
            '"location_mention": "Berkeley", '
            '"confidence": "medium"}'
        )
        with patch(
            "civicos_config.jurisdiction.JurisdictionRegistry.get_location_display_name",
            return_value="city-berkeley",
        ):
            result = detector.detect_complaint(
                "There's a huge pothole on University Ave",
                user_context={"jurisdiction_id": "city-san-rafael"},
            )
        assert result is not None
        assert result.jurisdiction_id == "city-berkeley"

    def test_registry_miss_falls_back_to_user_context(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "d", '
            '"issue_type": "infrastructure", '
            '"location_mention": "Nowhere", '
            '"confidence": "medium"}'
        )
        with patch(
            "civicos_config.jurisdiction.JurisdictionRegistry.get_location_display_name",
            return_value=None,
        ):
            result = detector.detect_complaint(
                "There's a huge pothole somewhere",
                user_context={"jurisdiction_id": "city-san-rafael"},
            )
        assert result is not None
        assert result.jurisdiction_id == "city-san-rafael"

    def test_no_location_no_user_context_returns_none_jurisdiction(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "d", '
            '"issue_type": "infrastructure", '
            '"location_mention": null, '
            '"confidence": "medium"}'
        )
        result = detector.detect_complaint("There's a pothole on my street")
        assert result is not None
        assert result.jurisdiction_id is None


# ---------------------------------------------------------------------------
# _resolve_jurisdiction — unit tests on the private method
# ---------------------------------------------------------------------------


class TestResolveJurisdiction:
    def test_location_mention_matches_registry(self):
        detector, _ = _detector_with_llm("{}")
        with patch(
            "civicos_config.jurisdiction.JurisdictionRegistry.get_location_display_name",
            return_value="city-oakland",
        ):
            assert detector._resolve_jurisdiction("Oakland", None) == "city-oakland"

    def test_location_mention_misses_registry_no_context_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        with patch(
            "civicos_config.jurisdiction.JurisdictionRegistry.get_location_display_name",
            return_value=None,
        ):
            assert detector._resolve_jurisdiction("Atlantis", None) is None

    def test_location_mention_misses_registry_with_context_returns_context(self):
        detector, _ = _detector_with_llm("{}")
        with patch(
            "civicos_config.jurisdiction.JurisdictionRegistry.get_location_display_name",
            return_value=None,
        ):
            result = detector._resolve_jurisdiction(
                "Atlantis", {"jurisdiction_id": "city-san-rafael"}
            )
        assert result == "city-san-rafael"

    def test_no_location_mention_uses_user_context(self):
        detector, _ = _detector_with_llm("{}")
        # Registry should NOT be consulted — no patch.
        result = detector._resolve_jurisdiction(
            None, {"jurisdiction_id": "city-san-rafael"}
        )
        assert result == "city-san-rafael"

    def test_no_location_mention_no_user_context_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        assert detector._resolve_jurisdiction(None, None) is None

    def test_empty_string_location_is_falsy_and_falls_back_to_context(self):
        detector, _ = _detector_with_llm("{}")
        # Empty string is falsy → skip registry lookup entirely
        result = detector._resolve_jurisdiction(
            "", {"jurisdiction_id": "city-fallback"}
        )
        assert result == "city-fallback"

    def test_user_context_missing_jurisdiction_id_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        assert detector._resolve_jurisdiction(None, {"other_field": "x"}) is None

    def test_user_context_with_none_jurisdiction_id_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        assert (
            detector._resolve_jurisdiction(None, {"jurisdiction_id": None})
            is None
        )

    def test_import_error_on_registry_falls_back_to_user_context(self):
        detector, _ = _detector_with_llm("{}")
        with patch.dict(
            "sys.modules", {"civicos_config.jurisdiction": None}
        ):
            # `None` as a module entry makes `from X import Y` raise ImportError
            result = detector._resolve_jurisdiction(
                "San Rafael", {"jurisdiction_id": "city-san-rafael"}
            )
        assert result == "city-san-rafael"

    def test_import_error_no_context_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        with patch.dict(
            "sys.modules", {"civicos_config.jurisdiction": None}
        ):
            result = detector._resolve_jurisdiction("San Rafael", None)
        assert result is None


# ---------------------------------------------------------------------------
# _safe_json_parse — pure parser
# ---------------------------------------------------------------------------


class TestSafeJsonParse:
    def test_plain_json_object_parses(self):
        detector, _ = _detector_with_llm("{}")
        assert detector._safe_json_parse('{"a": 1, "b": "two"}') == {
            "a": 1,
            "b": "two",
        }

    def test_strips_json_markdown_fence(self):
        detector, _ = _detector_with_llm("{}")
        raw = '```json\n{"is_complaint": true}\n```'
        assert detector._safe_json_parse(raw) == {"is_complaint": True}

    def test_strips_plain_backtick_suffix(self):
        # The module only strips a leading ```json (not bare ```). A plain
        # ``` suffix IS stripped. Pin current behavior.
        detector, _ = _detector_with_llm("{}")
        raw = '{"k": "v"}\n```'
        assert detector._safe_json_parse(raw) == {"k": "v"}

    def test_leading_backtick_only_is_not_stripped(self):
        # Only ```json is stripped as a prefix. A bare ``` prefix would leave
        # the payload unparseable, so the function returns None.
        detector, _ = _detector_with_llm("{}")
        raw = '```\n{"k": "v"}'
        assert detector._safe_json_parse(raw) is None

    def test_json_fenced_both_sides(self):
        detector, _ = _detector_with_llm("{}")
        raw = '```json\n{"is_complaint": false}\n```'
        assert detector._safe_json_parse(raw) == {"is_complaint": False}

    def test_json_fenced_with_surrounding_whitespace(self):
        detector, _ = _detector_with_llm("{}")
        raw = '  \n```json\n{"a": 1}\n```\n  '
        assert detector._safe_json_parse(raw) == {"a": 1}

    def test_malformed_json_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        assert detector._safe_json_parse('{"a": 1, invalid}') is None

    def test_completely_non_json_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        assert detector._safe_json_parse("not json at all") is None

    def test_empty_string_returns_none(self):
        detector, _ = _detector_with_llm("{}")
        assert detector._safe_json_parse("") is None

    def test_parses_json_array(self):
        detector, _ = _detector_with_llm("{}")
        assert detector._safe_json_parse("[1, 2, 3]") == [1, 2, 3]

    def test_parses_nested_object(self):
        detector, _ = _detector_with_llm("{}")
        raw = '{"outer": {"inner": [1, 2]}}'
        assert detector._safe_json_parse(raw) == {"outer": {"inner": [1, 2]}}


# ---------------------------------------------------------------------------
# _call_llm — parameters sent to OpenAI
# ---------------------------------------------------------------------------


class TestCallLLMParameters:
    def test_uses_gpt_4o_mini_model(self):
        detector, client = _detector_with_llm('{"is_complaint": false}')
        detector.detect_complaint("This is a test message for the LLM call")
        assert client.chat.completions.create.call_args.kwargs["model"] == "gpt-4o-mini"

    def test_uses_temperature_point_one(self):
        detector, client = _detector_with_llm('{"is_complaint": false}')
        detector.detect_complaint("This is a test message for the LLM call")
        assert (
            client.chat.completions.create.call_args.kwargs["temperature"] == 0.1
        )

    def test_max_tokens_defaults_to_300_via_extract(self):
        detector, client = _detector_with_llm('{"is_complaint": false}')
        detector.detect_complaint("This is a test message for the LLM call")
        assert client.chat.completions.create.call_args.kwargs["max_tokens"] == 300

    def test_messages_have_system_and_user_roles(self):
        detector, client = _detector_with_llm('{"is_complaint": false}')
        detector.detect_complaint("This is a test message for the LLM call")
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_prompt_mentions_civic_and_json(self):
        detector, client = _detector_with_llm('{"is_complaint": false}')
        detector.detect_complaint("This is a test message for the LLM call")
        system_content = client.chat.completions.create.call_args.kwargs[
            "messages"
        ][0]["content"]
        assert "civic" in system_content.lower()
        assert "JSON" in system_content

    def test_user_prompt_embeds_the_message(self):
        detector, client = _detector_with_llm('{"is_complaint": false}')
        detector.detect_complaint("My landlord won't fix the broken heater")
        user_content = client.chat.completions.create.call_args.kwargs[
            "messages"
        ][1]["content"]
        assert "My landlord won't fix the broken heater" in user_content

    def test_response_content_is_stripped(self):
        # Trailing whitespace in the LLM response should still parse cleanly.
        detector, _ = _detector_with_llm(
            '   {"is_complaint": true, '
            '"description": "Pothole on Elm", '
            '"issue_type": "infrastructure"}   \n'
        )
        result = detector.detect_complaint(
            "There's a huge pothole on Elm Street"
        )
        assert result is not None
        assert result.description == "Pothole on Elm"
        assert result.issue_type == "infrastructure"


# ---------------------------------------------------------------------------
# Smoke test for _extract_complaint_fields exception path
# ---------------------------------------------------------------------------


class TestExtractComplaintFieldsErrors:
    def test_llm_api_error_returns_none_extract(self):
        detector, _ = _detector_with_side_effect(RuntimeError("timeout"))
        # Direct call to the private method to pin the path
        result = detector._extract_complaint_fields("some prompt text")
        assert result is None

    def test_llm_returns_garbage_extract_returns_none(self):
        detector, _ = _detector_with_llm("this is not json at all")
        result = detector._extract_complaint_fields("some prompt text")
        assert result is None

    def test_llm_returns_valid_complaint_extract(self):
        detector, _ = _detector_with_llm(
            '{"is_complaint": true, '
            '"description": "Rent hike notice", '
            '"issue_type": "housing", '
            '"location_mention": null, '
            '"confidence": "high"}'
        )
        result = detector._extract_complaint_fields("My landlord raised my rent")
        assert result == {
            "is_complaint": True,
            "description": "Rent hike notice",
            "issue_type": "housing",
            "location_mention": None,
            "confidence": "high",
        }
