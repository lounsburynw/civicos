"""
Tests for berkeley_agenda_parser_legacy.py — Berkeley-specific multi-pass
agenda extraction using the OpenAI chat completions API.

Strategy: the ``openai_client`` is an external dependency injected through
the constructor, so we mock it directly (not the subject under test). All
logic inside ``extract_agenda_items`` and ``_truncate_safely`` runs for real
against the mocked chat responses.

To run:
    pytest packages/civicos-services/tests/test_berkeley_agenda_parser_legacy.py -q --override-ini="addopts="
"""

import json
from unittest.mock import MagicMock

import pytest

from civicos_services.processing.berkeley_agenda_parser_legacy import (
    BerkeleyAgendaParser,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chat_response(content: str) -> MagicMock:
    """Mimic the shape openai returns from chat.completions.create()."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def _make_client(structure_payload: str, events_payload: str) -> MagicMock:
    """
    Build a fake OpenAI client whose two successive chat completion calls
    return ``structure_payload`` and then ``events_payload``.
    """
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _chat_response(structure_payload),
        _chat_response(events_payload),
    ]
    return client


_DEFAULT_STRUCTURE = {
    "meeting": {
        "city": "Berkeley",
        "date": "2026-03-15",
        "start_time": "6:00 PM",
        "location": "Council Chambers",
        "livestream": "https://berkeley.gov/live",
        "public_comment_email": "clerk@berkeley.gov",
        "public_comment_deadline": "2026-03-14 5:00 PM",
        "meeting_type": "Regular",
    },
    "agenda_sections": [
        {"section_title": "Consent", "section_type": "consent", "item_count": 5},
        {"section_title": "Action", "section_type": "action", "item_count": 3},
    ],
}


def _default_events(n: int) -> list:
    """Generate ``n`` deterministic event dicts for use in tests."""
    return [
        {
            "title": f"Event {i}",
            "change": f"Change {i}",
            "impact": f"Impact {i}",
            "how_to_participate": f"How {i}",
            "project_type": "housing",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_stores_openai_client_verbatim(self):
        sentinel = MagicMock(name="openai_client")
        parser = BerkeleyAgendaParser(sentinel)
        assert parser.openai_client is sentinel

    def test_two_instances_hold_distinct_clients(self):
        a = BerkeleyAgendaParser(MagicMock(name="client_a"))
        b = BerkeleyAgendaParser(MagicMock(name="client_b"))
        assert a.openai_client is not b.openai_client


# ---------------------------------------------------------------------------
# _truncate_safely — pure logic, no mocks
# ---------------------------------------------------------------------------


class TestTruncateSafely:
    def _parser(self):
        return BerkeleyAgendaParser(MagicMock())

    def test_text_shorter_than_max_returned_unchanged(self):
        result = self._parser()._truncate_safely("hello world", 1000)
        assert result == "hello world"

    def test_text_exactly_max_length_returned_unchanged(self):
        # Boundary: len(text) <= max_length -> return as-is
        text = "a" * 100
        result = self._parser()._truncate_safely(text, 100)
        assert result == text
        assert len(result) == 100

    def test_empty_string_returns_empty_string(self):
        result = self._parser()._truncate_safely("", 50)
        assert result == ""

    def test_truncates_at_word_boundary_within_last_20_percent(self):
        # max_length=100, word boundary at position 90 (> 80), so cut there.
        text = ("a" * 90) + " " + ("b" * 100)
        result = self._parser()._truncate_safely(text, 100)
        assert len(result) == 90
        assert result == "a" * 90

    def test_truncates_hard_when_space_is_outside_last_20_percent(self):
        # Space at position 50 (<= 80) → fall back to hard truncate at 100.
        text = ("a" * 50) + " " + ("b" * 200)
        result = self._parser()._truncate_safely(text, 100)
        assert len(result) == 100
        # First 50 chars are 'a', the space is at 50, then 49 'b's fill it up.
        assert result[:50] == "a" * 50
        assert result[50] == " "
        assert result[51:] == "b" * 49

    def test_truncates_hard_when_no_space_in_text(self):
        text = "a" * 200
        result = self._parser()._truncate_safely(text, 100)
        assert result == "a" * 100
        assert len(result) == 100

    def test_word_boundary_exactly_at_threshold_is_not_taken(self):
        # max_length=100, 0.8*100=80. Condition is ``last_space > 80`` (strict).
        # A space at exactly 80 should NOT trigger the word-boundary branch.
        text = ("a" * 80) + " " + ("b" * 200)
        result = self._parser()._truncate_safely(text, 100)
        assert len(result) == 100
        assert result[:80] == "a" * 80
        assert result[80] == " "

    def test_word_boundary_one_past_threshold_is_taken(self):
        # max_length=100, space at position 81 (> 80) → truncate at 81.
        text = ("a" * 81) + " " + ("b" * 200)
        result = self._parser()._truncate_safely(text, 100)
        assert len(result) == 81
        assert result == "a" * 81

    def test_longer_inputs_use_last_space_in_window(self):
        # Two spaces: position 10 (outside window), position 95 (inside window).
        # The function uses rfind → last space → 95.
        text = ("a" * 10) + " " + ("b" * 84) + " " + ("c" * 100)
        result = self._parser()._truncate_safely(text, 100)
        assert len(result) == 95
        assert result[10] == " "
        assert result[95:] == ""


# ---------------------------------------------------------------------------
# extract_agenda_items — happy paths
# ---------------------------------------------------------------------------


class TestExtractAgendaItemsHappyPath:
    def test_returns_meeting_dict_from_structure_pass(self):
        events = _default_events(2)
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items(
            "meeting content", "https://example.com"
        )

        assert result["meeting"]["city"] == "Berkeley"
        assert result["meeting"]["date"] == "2026-03-15"
        assert result["meeting"]["start_time"] == "6:00 PM"
        assert result["meeting"]["location"] == "Council Chambers"
        assert result["meeting"]["public_comment_email"] == "clerk@berkeley.gov"
        assert result["meeting"]["meeting_type"] == "Regular"

    def test_items_field_is_the_events_from_second_pass(self):
        events = _default_events(4)
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert result["items"] == events
        assert len(result["items"]) == 4
        assert result["items"][0]["title"] == "Event 0"
        assert result["items"][3]["title"] == "Event 3"

    def test_bottom_line_contains_event_count(self):
        events = _default_events(7)
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert result["bottom_line"] == (
            "Berkeley City Council meeting with 7 key events for civic engagement."
        )

    def test_bottom_line_with_zero_events(self):
        client = _make_client(json.dumps(_DEFAULT_STRUCTURE), json.dumps([]))
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert result["bottom_line"] == (
            "Berkeley City Council meeting with 0 key events for civic engagement."
        )
        # No events → no recap rows generated.
        assert result["recap_rows"] == []

    def test_returns_all_four_top_level_keys(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert set(result.keys()) == {"meeting", "items", "recap_rows", "bottom_line"}


# ---------------------------------------------------------------------------
# extract_agenda_items — recap_rows construction
# ---------------------------------------------------------------------------


class TestRecapRows:
    def test_recap_uses_top_3_events_when_more_than_3(self):
        events = _default_events(5)
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert len(result["recap_rows"]) == 3
        assert result["recap_rows"][0]["topic"] == "Event 0"
        assert result["recap_rows"][1]["topic"] == "Event 1"
        assert result["recap_rows"][2]["topic"] == "Event 2"

    def test_recap_uses_all_events_when_exactly_3(self):
        events = _default_events(3)
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert len(result["recap_rows"]) == 3
        topics = [r["topic"] for r in result["recap_rows"]]
        assert topics == ["Event 0", "Event 1", "Event 2"]

    def test_recap_uses_all_events_when_fewer_than_3(self):
        events = _default_events(1)
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert len(result["recap_rows"]) == 1
        assert result["recap_rows"][0]["topic"] == "Event 0"

    def test_recap_why_it_matters_is_impact_prefix_with_ellipsis(self):
        events = [
            {
                "title": "Short Impact Title",
                "impact": "brief",
                "change": "",
                "how_to_participate": "",
                "project_type": "",
            }
        ]
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        # Impact is 5 chars, truncation is [:100] + "..." → "brief..."
        assert result["recap_rows"][0]["why_it_matters"] == "brief..."

    def test_recap_why_it_matters_truncates_long_impact_to_100_chars_plus_ellipsis(self):
        long_impact = "x" * 250
        events = [
            {
                "title": "Long Impact",
                "impact": long_impact,
                "change": "",
                "how_to_participate": "",
                "project_type": "",
            }
        ]
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        why = result["recap_rows"][0]["why_it_matters"]
        assert why == ("x" * 100) + "..."
        assert len(why) == 103

    def test_recap_act_by_uses_meeting_date_from_structure(self):
        events = _default_events(2)
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(events),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        for row in result["recap_rows"]:
            assert row["act_by"] == "2026-03-15"

    def test_recap_act_by_falls_back_to_literal_when_no_meeting_date(self):
        structure = {"meeting": {}}  # no date key
        events = _default_events(1)
        client = _make_client(json.dumps(structure), json.dumps(events))
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert result["recap_rows"][0]["act_by"] == "Meeting date"

    def test_recap_act_by_falls_back_when_meeting_key_missing(self):
        # No "meeting" key at all in structure response.
        structure = {"agenda_sections": []}
        events = _default_events(1)
        client = _make_client(json.dumps(structure), json.dumps(events))
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert result["meeting"] == {}
        assert result["recap_rows"][0]["act_by"] == "Meeting date"

    def test_recap_topic_defaults_to_empty_string_when_event_lacks_title(self):
        events = [{"impact": "some impact"}]  # no 'title'
        client = _make_client(json.dumps(_DEFAULT_STRUCTURE), json.dumps(events))
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        assert result["recap_rows"][0]["topic"] == ""
        assert result["recap_rows"][0]["why_it_matters"] == "some impact..."

    def test_recap_why_it_matters_defaults_to_ellipsis_when_event_lacks_impact(self):
        events = [{"title": "No impact event"}]  # no 'impact'
        client = _make_client(json.dumps(_DEFAULT_STRUCTURE), json.dumps(events))
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        # "".__getitem__(slice(100)) == "" → "" + "..." → "..."
        assert result["recap_rows"][0]["why_it_matters"] == "..."


# ---------------------------------------------------------------------------
# extract_agenda_items — LLM call shape
# ---------------------------------------------------------------------------


class TestLLMCallShape:
    def test_calls_chat_completions_exactly_twice(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        # Both passes ran...
        assert client.chat.completions.create.call_count == 2
        # ...and the second pass's payload flowed into the final result.
        assert result["meeting"]["city"] == "Berkeley"
        assert result["items"][0]["title"] == "Event 0"
        assert len(result["items"]) == 1

    def test_both_passes_use_gpt_4o_model(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        calls = client.chat.completions.create.call_args_list
        assert calls[0].kwargs["model"] == "gpt-4o"
        assert calls[1].kwargs["model"] == "gpt-4o"

    def test_both_passes_use_low_temperature(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        calls = client.chat.completions.create.call_args_list
        assert calls[0].kwargs["temperature"] == 0.1
        assert calls[1].kwargs["temperature"] == 0.1

    def test_structure_pass_truncates_content_to_20000_chars(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        big_text = "S" * 50000
        BerkeleyAgendaParser(client).extract_agenda_items(big_text, "")

        structure_prompt = client.chat.completions.create.call_args_list[0].kwargs[
            "messages"
        ][0]["content"]
        # 20000 'S' chars are present, 20001 are not.
        assert ("S" * 20000) in structure_prompt
        assert ("S" * 20001) not in structure_prompt

    def test_opportunities_pass_truncates_content_to_35000_chars(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        big_text = "O" * 50000
        BerkeleyAgendaParser(client).extract_agenda_items(big_text, "")

        opportunities_prompt = client.chat.completions.create.call_args_list[1].kwargs[
            "messages"
        ][0]["content"]
        assert ("O" * 35000) in opportunities_prompt
        assert ("O" * 35001) not in opportunities_prompt

    def test_short_content_sent_verbatim_to_both_passes(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        BerkeleyAgendaParser(client).extract_agenda_items("UNIQUE_TOKEN_XYZ", "")

        calls = client.chat.completions.create.call_args_list
        assert "UNIQUE_TOKEN_XYZ" in calls[0].kwargs["messages"][0]["content"]
        assert "UNIQUE_TOKEN_XYZ" in calls[1].kwargs["messages"][0]["content"]

    def test_structure_prompt_contains_berkeley_structure_keys(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        structure_prompt = client.chat.completions.create.call_args_list[0].kwargs[
            "messages"
        ][0]["content"]
        # The pass-1 prompt asks only for meeting metadata + agenda_sections.
        assert "agenda_sections" in structure_prompt
        assert "meeting_type" in structure_prompt
        assert "public_comment_email" in structure_prompt

    def test_opportunities_prompt_lists_berkeley_priorities(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        opportunities_prompt = client.chat.completions.create.call_args_list[1].kwargs[
            "messages"
        ][0]["content"]
        # The pass-2 prompt ships Berkeley-specific priority instructions.
        assert "BERKELEY PRIORITIES" in opportunities_prompt
        assert "Housing and development" in opportunities_prompt
        assert "Climate action" in opportunities_prompt

    def test_each_pass_sends_single_user_message(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        BerkeleyAgendaParser(client).extract_agenda_items("text", "")

        for call in client.chat.completions.create.call_args_list:
            messages = call.kwargs["messages"]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"


# ---------------------------------------------------------------------------
# extract_agenda_items — error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_propagates_llm_exception_from_structure_pass(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("API down")
        parser = BerkeleyAgendaParser(client)

        with pytest.raises(RuntimeError, match="API down"):
            parser.extract_agenda_items("text", "")

    def test_propagates_llm_exception_from_opportunities_pass(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            _chat_response(json.dumps(_DEFAULT_STRUCTURE)),
            ConnectionError("opportunities failed"),
        ]
        parser = BerkeleyAgendaParser(client)

        with pytest.raises(ConnectionError, match="opportunities failed"):
            parser.extract_agenda_items("text", "")

    def test_propagates_json_decode_error_on_structure_response(self):
        client = _make_client(
            "this is not valid json {{{",
            json.dumps(_default_events(1)),
        )
        parser = BerkeleyAgendaParser(client)

        with pytest.raises(json.JSONDecodeError):
            parser.extract_agenda_items("text", "")

    def test_propagates_json_decode_error_on_opportunities_response(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            "not json either",
        )
        parser = BerkeleyAgendaParser(client)

        with pytest.raises(json.JSONDecodeError):
            parser.extract_agenda_items("text", "")

    def test_structure_error_aborts_before_opportunities_call(self):
        """If the first LLM call fails, the second one is never issued."""
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            RuntimeError("first pass failed"),
        ]
        parser = BerkeleyAgendaParser(client)

        with pytest.raises(RuntimeError):
            parser.extract_agenda_items("text", "")
        assert client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# extract_agenda_items — source_url defaults and logging behavior
# ---------------------------------------------------------------------------


class TestSourceUrlHandling:
    def test_source_url_defaults_to_empty_string(self):
        # Omitting source_url must not raise — the parameter has a default.
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(2)),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items("text")

        assert len(result["items"]) == 2
        assert result["meeting"]["city"] == "Berkeley"

    def test_accepts_non_empty_source_url_and_still_returns_result(self):
        client = _make_client(
            json.dumps(_DEFAULT_STRUCTURE),
            json.dumps(_default_events(1)),
        )
        result = BerkeleyAgendaParser(client).extract_agenda_items(
            "text", "https://berkeley.gov/agenda.pdf"
        )

        assert result["items"][0]["title"] == "Event 0"
