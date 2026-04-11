"""
Tests for minutes_parser.py — Extract testimony and attendee data from meeting
minutes PDFs.

The LLM-powered extraction methods are tested by mocking the `get_model_for_task`
factory at the module boundary. Pure dataclass defaults and parser configuration
are tested without mocks.

To run:
    pytest packages/civicos-services/tests/test_minutes_parser.py -q --override-ini="addopts="
"""

import json
from unittest.mock import patch, MagicMock

from civicos_services.processing.minutes_parser import (
    MeetingAttendees,
    MinutesParser,
    TestimonyData,
)


# ---------------------------------------------------------------------------
# Helpers — mock the LLM factory boundary
# ---------------------------------------------------------------------------

def _make_provider_response(payload):
    """Build a mock CompletionResponse whose .content is the given string."""
    response = MagicMock()
    response.content = payload
    return response


def _patch_llm(payload=None, side_effect=None):
    """
    Patch `get_model_for_task` so the parser sees a fake provider.

    payload       — single string response for every .complete() call.
    side_effect   — iterable or exception driving successive .complete() calls.

    Returns (patch_context_manager, provider_mock). Caller uses `with p:`.
    """
    provider = MagicMock()
    if side_effect is not None:
        provider.complete.side_effect = side_effect
    else:
        provider.complete.return_value = _make_provider_response(payload or "")
    ctx = patch(
        "civicos_services.processing.minutes_parser.get_model_for_task",
        return_value=provider,
    )
    return ctx, provider


# ---------------------------------------------------------------------------
# TestimonyData — dataclass defaults
# ---------------------------------------------------------------------------

class TestTestimonyDataDefaults:
    def test_speaker_names_defaults_to_empty_list(self):
        td = TestimonyData(item_ref="5.g")
        assert td.speaker_names == []

    def test_vote_results_defaults_to_empty_dict(self):
        td = TestimonyData(item_ref="5.g")
        assert td.vote_results == {}

    def test_passed_defaults_to_true(self):
        td = TestimonyData(item_ref="5.g")
        assert td.passed is True

    def test_testimony_count_defaults_to_none(self):
        td = TestimonyData(item_ref="5.g")
        assert td.testimony_count is None

    def test_item_ref_stored_verbatim(self):
        td = TestimonyData(item_ref="7.a")
        assert td.item_ref == "7.a"

    def test_provided_speaker_names_preserved(self):
        td = TestimonyData(item_ref="5.g", speaker_names=["Alice", "Bob"])
        assert td.speaker_names == ["Alice", "Bob"]

    def test_provided_vote_results_preserved(self):
        td = TestimonyData(
            item_ref="5.g",
            vote_results={"yes": 4, "no": 1, "abstain": 0},
        )
        assert td.vote_results == {"yes": 4, "no": 1, "abstain": 0}

    def test_passed_false_is_preserved(self):
        td = TestimonyData(item_ref="5.g", passed=False)
        assert td.passed is False

    def test_explicit_none_speaker_names_becomes_empty_list(self):
        td = TestimonyData(item_ref="5.g", speaker_names=None)
        assert td.speaker_names == []

    def test_explicit_none_vote_results_becomes_empty_dict(self):
        td = TestimonyData(item_ref="5.g", vote_results=None)
        assert td.vote_results == {}

    def test_default_lists_are_independent_instances(self):
        """Two TestimonyData instances must not share the same list object."""
        a = TestimonyData(item_ref="1")
        b = TestimonyData(item_ref="2")
        a.speaker_names.append("Alice")
        assert b.speaker_names == []


# ---------------------------------------------------------------------------
# MeetingAttendees — dataclass defaults
# ---------------------------------------------------------------------------

class TestMeetingAttendeesDefaults:
    def test_council_members_present_defaults_to_empty_list(self):
        m = MeetingAttendees()
        assert m.council_members_present == []

    def test_council_members_absent_defaults_to_empty_list(self):
        m = MeetingAttendees()
        assert m.council_members_absent == []

    def test_staff_present_defaults_to_empty_list(self):
        m = MeetingAttendees()
        assert m.staff_present == []

    def test_provided_council_members_present_preserved(self):
        members = [{"name": "Kate Colin", "title": "Mayor"}]
        m = MeetingAttendees(council_members_present=members)
        assert m.council_members_present == members

    def test_explicit_none_council_members_present_becomes_list(self):
        m = MeetingAttendees(council_members_present=None)
        assert m.council_members_present == []

    def test_explicit_none_council_members_absent_becomes_list(self):
        m = MeetingAttendees(council_members_absent=None)
        assert m.council_members_absent == []

    def test_explicit_none_staff_present_becomes_list(self):
        m = MeetingAttendees(staff_present=None)
        assert m.staff_present == []

    def test_default_lists_are_independent_instances(self):
        """Mutable default guard: two instances must not share the same list."""
        a = MeetingAttendees()
        b = MeetingAttendees()
        a.council_members_present.append({"name": "X", "title": "Mayor"})
        assert b.council_members_present == []


# ---------------------------------------------------------------------------
# MinutesParser.__init__
# ---------------------------------------------------------------------------

class TestMinutesParserInit:
    def test_default_model_is_gemini_2_0_flash_exp(self):
        parser = MinutesParser()
        assert parser.model == "gemini-2.0-flash-exp"

    def test_explicit_model_overrides_default(self):
        parser = MinutesParser(model="claude-3-haiku-20240307")
        assert parser.model == "claude-3-haiku-20240307"

    def test_explicit_none_model_falls_back_to_default(self):
        parser = MinutesParser(model=None)
        assert parser.model == "gemini-2.0-flash-exp"

    def test_empty_string_model_falls_back_to_default(self):
        # `model or default` → empty string is falsy, so default wins
        parser = MinutesParser(model="")
        assert parser.model == "gemini-2.0-flash-exp"


# ---------------------------------------------------------------------------
# extract_meeting_attendees
# ---------------------------------------------------------------------------

class TestExtractMeetingAttendees:
    def test_parses_all_three_sections_from_json(self):
        payload = json.dumps({
            "council_members_present": [
                {"name": "Kate Colin", "title": "Mayor"},
                {"name": "Maika Llorens Gulati", "title": "Vice Mayor"},
                {"name": "Rachel Kertz", "title": "Councilmember"},
            ],
            "council_members_absent": ["Eli Hill"],
            "staff_present": [
                {"name": "Cristine Alilovich", "title": "City Manager"},
                {"name": "Lindsay Lara", "title": "City Clerk"},
            ],
        })
        ctx, _ = _patch_llm(payload=payload)
        with ctx:
            result = MinutesParser().extract_meeting_attendees("MINUTES TEXT")

        assert len(result.council_members_present) == 3
        assert result.council_members_present[0] == {"name": "Kate Colin", "title": "Mayor"}
        assert result.council_members_present[1]["name"] == "Maika Llorens Gulati"
        assert result.council_members_present[1]["title"] == "Vice Mayor"
        assert result.council_members_present[2]["title"] == "Councilmember"
        assert result.council_members_absent == ["Eli Hill"]
        assert len(result.staff_present) == 2
        assert result.staff_present[0]["name"] == "Cristine Alilovich"
        assert result.staff_present[0]["title"] == "City Manager"
        assert result.staff_present[1]["title"] == "City Clerk"

    def test_strips_json_markdown_code_fence(self):
        inner = json.dumps({
            "council_members_present": [{"name": "Alice", "title": "Mayor"}],
            "council_members_absent": [],
            "staff_present": [],
        })
        payload = "```json\n" + inner + "\n```"
        ctx, _ = _patch_llm(payload=payload)
        with ctx:
            result = MinutesParser().extract_meeting_attendees("text")

        assert result.council_members_present == [{"name": "Alice", "title": "Mayor"}]

    def test_strips_bare_markdown_code_fence(self):
        inner = json.dumps({
            "council_members_present": [],
            "council_members_absent": ["Bob"],
            "staff_present": [],
        })
        payload = "```\n" + inner + "\n```"
        ctx, _ = _patch_llm(payload=payload)
        with ctx:
            result = MinutesParser().extract_meeting_attendees("text")

        assert result.council_members_absent == ["Bob"]
        assert result.council_members_present == []
        assert result.staff_present == []

    def test_missing_keys_default_to_empty_lists(self):
        ctx, _ = _patch_llm(payload=json.dumps({}))
        with ctx:
            result = MinutesParser().extract_meeting_attendees("text")

        assert result.council_members_present == []
        assert result.council_members_absent == []
        assert result.staff_present == []

    def test_invalid_json_returns_empty_attendees(self):
        ctx, _ = _patch_llm(payload="this is not valid json")
        with ctx:
            result = MinutesParser().extract_meeting_attendees("text")

        assert result.council_members_present == []
        assert result.council_members_absent == []
        assert result.staff_present == []

    def test_provider_exception_returns_empty_attendees(self):
        ctx, _ = _patch_llm(side_effect=RuntimeError("API unreachable"))
        with ctx:
            result = MinutesParser().extract_meeting_attendees("text")

        assert result.council_members_present == []
        assert result.council_members_absent == []
        assert result.staff_present == []

    def test_response_whitespace_is_stripped_before_parsing(self):
        inner = json.dumps({
            "council_members_present": [{"name": "Alice", "title": "Mayor"}],
            "council_members_absent": [],
            "staff_present": [],
        })
        ctx, _ = _patch_llm(payload="   \n\n" + inner + "\n\n  ")
        with ctx:
            result = MinutesParser().extract_meeting_attendees("text")

        assert result.council_members_present == [{"name": "Alice", "title": "Mayor"}]

    def test_minutes_text_truncated_to_5000_chars_in_prompt(self):
        payload = json.dumps({
            "council_members_present": [],
            "council_members_absent": [],
            "staff_present": [],
        })
        big_text = "A" * 10000
        ctx, provider = _patch_llm(payload=payload)
        with ctx:
            MinutesParser().extract_meeting_attendees(big_text)

        sent_messages = provider.complete.call_args[0][0]
        user_prompt = sent_messages[1]["content"]
        # First 5000 "A"s are in the prompt; the 5001st is not.
        assert ("A" * 5000) in user_prompt
        assert ("A" * 5001) not in user_prompt

    def test_short_minutes_text_sent_verbatim(self):
        payload = json.dumps({
            "council_members_present": [],
            "council_members_absent": [],
            "staff_present": [],
        })
        ctx, provider = _patch_llm(payload=payload)
        with ctx:
            MinutesParser().extract_meeting_attendees("SHORT_MINUTES_CONTENT")

        user_prompt = provider.complete.call_args[0][0][1]["content"]
        assert "SHORT_MINUTES_CONTENT" in user_prompt

    def test_system_and_user_messages_sent_in_order(self):
        payload = json.dumps({
            "council_members_present": [],
            "council_members_absent": [],
            "staff_present": [],
        })
        ctx, provider = _patch_llm(payload=payload)
        with ctx:
            MinutesParser().extract_meeting_attendees("text")

        sent_messages = provider.complete.call_args[0][0]
        assert len(sent_messages) == 2
        assert sent_messages[0]["role"] == "system"
        assert sent_messages[1]["role"] == "user"
        assert "valid JSON only" in sent_messages[0]["content"]

    def test_factory_called_with_short_structured_task_type(self):
        payload = json.dumps({
            "council_members_present": [],
            "council_members_absent": [],
            "staff_present": [],
        })
        provider = MagicMock()
        provider.complete.return_value = _make_provider_response(payload)
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ) as mock_factory:
            result = MinutesParser().extract_meeting_attendees("text")

        assert mock_factory.call_args[0][0] == "short_structured"
        # Also verify real behavior (kill the mock-theater mutant):
        assert result.council_members_present == []
        assert result.staff_present == []

    def test_returns_meeting_attendees_type(self):
        ctx, _ = _patch_llm(payload=json.dumps({
            "council_members_present": [{"name": "Kate", "title": "Mayor"}],
            "council_members_absent": [],
            "staff_present": [{"name": "Ann", "title": "City Clerk"}],
        }))
        with ctx:
            result = MinutesParser().extract_meeting_attendees("text")
        # It must be a MeetingAttendees so the caller can use dataclass fields
        assert isinstance(result, MeetingAttendees)
        assert result.council_members_present[0]["name"] == "Kate"
        assert result.staff_present[0]["title"] == "City Clerk"


# ---------------------------------------------------------------------------
# extract_testimony_for_item
# ---------------------------------------------------------------------------

class TestExtractTestimonyForItem:
    def test_parses_all_fields_from_json(self):
        payload = json.dumps({
            "testimony_count": 4,
            "speaker_names": ["Alice Jones", "Bob Smith", "Carol Davis", "Dave Wilson"],
            "vote_results": {"yes": 4, "no": 1, "abstain": 0},
            "passed": True,
        })
        ctx, _ = _patch_llm(payload=payload)
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "5.g")

        assert result.item_ref == "5.g"
        assert result.testimony_count == 4
        assert result.speaker_names == [
            "Alice Jones", "Bob Smith", "Carol Davis", "Dave Wilson",
        ]
        assert result.vote_results == {"yes": 4, "no": 1, "abstain": 0}
        assert result.passed is True

    def test_passed_false_propagated_to_result(self):
        payload = json.dumps({
            "testimony_count": 0,
            "speaker_names": [],
            "vote_results": {"yes": 1, "no": 4, "abstain": 0},
            "passed": False,
        })
        ctx, _ = _patch_llm(payload=payload)
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "7.b")

        assert result.passed is False
        assert result.vote_results == {"yes": 1, "no": 4, "abstain": 0}
        assert result.testimony_count == 0

    def test_null_testimony_count_preserved_as_none(self):
        payload = json.dumps({
            "testimony_count": None,
            "speaker_names": [],
            "vote_results": None,
            "passed": True,
        })
        ctx, _ = _patch_llm(payload=payload)
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "5.g")

        assert result.testimony_count is None
        # vote_results==None → dataclass post_init coerces to empty dict
        assert result.vote_results == {}

    def test_strips_json_markdown_fence(self):
        inner = json.dumps({
            "testimony_count": 2,
            "speaker_names": ["A", "B"],
            "vote_results": {"yes": 5, "no": 0, "abstain": 0},
            "passed": True,
        })
        ctx, _ = _patch_llm(payload="```json\n" + inner + "\n```")
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "5.g")

        assert result.testimony_count == 2
        assert result.speaker_names == ["A", "B"]
        assert result.vote_results == {"yes": 5, "no": 0, "abstain": 0}

    def test_strips_bare_markdown_fence(self):
        inner = json.dumps({
            "testimony_count": 1,
            "speaker_names": ["Solo"],
            "vote_results": {"yes": 3, "no": 2, "abstain": 0},
            "passed": True,
        })
        ctx, _ = _patch_llm(payload="```\n" + inner + "\n```")
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "5.g")

        assert result.testimony_count == 1
        assert result.speaker_names == ["Solo"]
        assert result.vote_results["yes"] == 3
        assert result.vote_results["no"] == 2

    def test_response_whitespace_stripped_before_parsing(self):
        inner = json.dumps({
            "testimony_count": 3,
            "speaker_names": ["X", "Y", "Z"],
            "vote_results": {"yes": 5, "no": 0, "abstain": 0},
            "passed": True,
        })
        ctx, _ = _patch_llm(payload="\n  " + inner + "  \n")
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "5.g")

        assert result.testimony_count == 3
        assert result.speaker_names == ["X", "Y", "Z"]

    def test_missing_fields_use_defaults(self):
        ctx, _ = _patch_llm(payload=json.dumps({}))
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "9.a")

        assert result.item_ref == "9.a"
        assert result.testimony_count is None
        assert result.speaker_names == []
        # vote_results missing → get(..., default=None) → __post_init__ → {}
        assert result.vote_results == {}
        assert result.passed is True  # explicit .get('passed', True)

    def test_item_ref_preserved_on_json_parse_error(self):
        ctx, _ = _patch_llm(payload="this is not json {{")
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "12.x")

        assert result.item_ref == "12.x"
        assert result.testimony_count is None
        assert result.speaker_names == []
        assert result.vote_results == {}
        assert result.passed is True

    def test_item_ref_preserved_on_provider_exception(self):
        ctx, _ = _patch_llm(side_effect=ConnectionError("boom"))
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "3.c")

        assert result.item_ref == "3.c"
        assert result.testimony_count is None
        assert result.speaker_names == []
        assert result.vote_results == {}
        assert result.passed is True

    def test_item_ref_included_in_user_prompt(self):
        payload = json.dumps({
            "testimony_count": 0,
            "speaker_names": [],
            "vote_results": None,
            "passed": True,
        })
        ctx, provider = _patch_llm(payload=payload)
        with ctx:
            MinutesParser().extract_testimony_for_item("MINUTES_TEXT", "5.g")

        user_prompt = provider.complete.call_args[0][0][1]["content"]
        assert "5.g" in user_prompt
        assert "MINUTES_TEXT" in user_prompt

    def test_full_minutes_text_sent_not_truncated(self):
        """Unlike extract_meeting_attendees (5000-char cap), item extraction
        sends the full minutes text."""
        payload = json.dumps({
            "testimony_count": 0,
            "speaker_names": [],
            "vote_results": None,
            "passed": True,
        })
        big_text = "B" * 10000
        ctx, provider = _patch_llm(payload=payload)
        with ctx:
            MinutesParser().extract_testimony_for_item(big_text, "5.g")

        user_prompt = provider.complete.call_args[0][0][1]["content"]
        assert ("B" * 10000) in user_prompt

    def test_unanimous_yes_vote(self):
        payload = json.dumps({
            "testimony_count": 6,
            "speaker_names": ["P1", "P2", "P3", "P4", "P5", "P6"],
            "vote_results": {"yes": 5, "no": 0, "abstain": 0},
            "passed": True,
        })
        ctx, _ = _patch_llm(payload=payload)
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "5.g")

        assert result.testimony_count == 6
        assert len(result.speaker_names) == 6
        assert result.speaker_names[0] == "P1"
        assert result.speaker_names[-1] == "P6"
        assert result.vote_results["yes"] == 5
        assert result.vote_results["no"] == 0
        assert result.vote_results["abstain"] == 0

    def test_returns_testimony_data_type(self):
        payload = json.dumps({
            "testimony_count": 1,
            "speaker_names": ["Solo"],
            "vote_results": {"yes": 3, "no": 0, "abstain": 0},
            "passed": True,
        })
        ctx, _ = _patch_llm(payload=payload)
        with ctx:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "1.a")
        assert isinstance(result, TestimonyData)
        assert result.item_ref == "1.a"
        assert result.testimony_count == 1

    def test_factory_called_with_short_structured_task_type(self):
        payload = json.dumps({
            "testimony_count": 0,
            "speaker_names": [],
            "vote_results": None,
            "passed": True,
        })
        provider = MagicMock()
        provider.complete.return_value = _make_provider_response(payload)
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ) as mock_factory:
            result = MinutesParser().extract_testimony_for_item("MINUTES", "5.g")

        assert mock_factory.call_args[0][0] == "short_structured"
        # Real-behavior assertion — kill mock-theater mutants
        assert result.item_ref == "5.g"
        assert result.testimony_count == 0


# ---------------------------------------------------------------------------
# extract_all_testimony
# ---------------------------------------------------------------------------

class TestExtractAllTestimony:
    def test_returns_dict_keyed_by_item_ref(self):
        payloads = [
            json.dumps({
                "testimony_count": 2,
                "speaker_names": ["A", "B"],
                "vote_results": {"yes": 5, "no": 0, "abstain": 0},
                "passed": True,
            }),
            json.dumps({
                "testimony_count": 0,
                "speaker_names": [],
                "vote_results": {"yes": 3, "no": 2, "abstain": 0},
                "passed": False,
            }),
        ]
        provider = MagicMock()
        provider.complete.side_effect = [_make_provider_response(p) for p in payloads]
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ):
            result = MinutesParser().extract_all_testimony("MINUTES", ["5.g", "7.a"])

        assert set(result.keys()) == {"5.g", "7.a"}
        assert result["5.g"].testimony_count == 2
        assert result["5.g"].speaker_names == ["A", "B"]
        assert result["5.g"].passed is True
        assert result["5.g"].vote_results == {"yes": 5, "no": 0, "abstain": 0}
        assert result["7.a"].testimony_count == 0
        assert result["7.a"].speaker_names == []
        assert result["7.a"].passed is False
        assert result["7.a"].vote_results == {"yes": 3, "no": 2, "abstain": 0}

    def test_empty_item_refs_returns_empty_dict(self):
        provider = MagicMock()
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ):
            result = MinutesParser().extract_all_testimony("MINUTES", [])

        assert result == {}
        # Empty list → parser never invokes the LLM
        assert provider.complete.call_count == 0

    def test_invokes_llm_once_per_item(self):
        payload = json.dumps({
            "testimony_count": 0,
            "speaker_names": [],
            "vote_results": None,
            "passed": True,
        })
        provider = MagicMock()
        provider.complete.side_effect = [
            _make_provider_response(payload) for _ in range(3)
        ]
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ):
            result = MinutesParser().extract_all_testimony(
                "MINUTES", ["1.a", "2.b", "3.c"]
            )

        assert provider.complete.call_count == 3
        assert set(result.keys()) == {"1.a", "2.b", "3.c"}
        # Real-behavior assertion: each entry was built with the right ref
        assert result["1.a"].item_ref == "1.a"
        assert result["2.b"].item_ref == "2.b"
        assert result["3.c"].item_ref == "3.c"

    def test_each_result_item_ref_matches_request(self):
        payload = json.dumps({
            "testimony_count": 1,
            "speaker_names": ["X"],
            "vote_results": {"yes": 4, "no": 1, "abstain": 0},
            "passed": True,
        })
        provider = MagicMock()
        provider.complete.side_effect = [
            _make_provider_response(payload) for _ in range(2)
        ]
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ):
            result = MinutesParser().extract_all_testimony("MINUTES", ["5.g", "7.a"])

        assert result["5.g"].item_ref == "5.g"
        assert result["7.a"].item_ref == "7.a"

    def test_one_failure_does_not_abort_remaining_items(self):
        """Failure on item 1 → empty data for that item, item 2 still succeeds."""
        good_payload = json.dumps({
            "testimony_count": 3,
            "speaker_names": ["A", "B", "C"],
            "vote_results": {"yes": 5, "no": 0, "abstain": 0},
            "passed": True,
        })
        provider = MagicMock()
        provider.complete.side_effect = [
            RuntimeError("boom"),
            _make_provider_response(good_payload),
        ]
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ):
            result = MinutesParser().extract_all_testimony("MINUTES", ["1.a", "2.b"])

        assert set(result.keys()) == {"1.a", "2.b"}
        # Failed item: empty data but item_ref is preserved
        assert result["1.a"].item_ref == "1.a"
        assert result["1.a"].testimony_count is None
        assert result["1.a"].speaker_names == []
        assert result["1.a"].vote_results == {}
        # Succeeded item: full data
        assert result["2.b"].testimony_count == 3
        assert result["2.b"].speaker_names == ["A", "B", "C"]
        assert result["2.b"].vote_results == {"yes": 5, "no": 0, "abstain": 0}

    def test_preserves_insertion_order_in_result_dict(self):
        payload = json.dumps({
            "testimony_count": 0,
            "speaker_names": [],
            "vote_results": None,
            "passed": True,
        })
        provider = MagicMock()
        provider.complete.side_effect = [
            _make_provider_response(payload) for _ in range(4)
        ]
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ):
            result = MinutesParser().extract_all_testimony(
                "MINUTES", ["4.d", "1.a", "3.c", "2.b"]
            )

        assert list(result.keys()) == ["4.d", "1.a", "3.c", "2.b"]

    def test_duplicate_item_refs_collapse_into_single_key(self):
        """The result dict is keyed by item_ref, so duplicates merge; the
        final value for a repeated key comes from the last successful call."""
        payloads = [
            json.dumps({
                "testimony_count": 1,
                "speaker_names": ["First"],
                "vote_results": {"yes": 3, "no": 0, "abstain": 0},
                "passed": True,
            }),
            json.dumps({
                "testimony_count": 2,
                "speaker_names": ["Second"],
                "vote_results": {"yes": 4, "no": 1, "abstain": 0},
                "passed": False,
            }),
        ]
        provider = MagicMock()
        provider.complete.side_effect = [
            _make_provider_response(p) for p in payloads
        ]
        with patch(
            "civicos_services.processing.minutes_parser.get_model_for_task",
            return_value=provider,
        ):
            result = MinutesParser().extract_all_testimony("MINUTES", ["5.g", "5.g"])

        assert list(result.keys()) == ["5.g"]
        # Second call overwrites the first entry under the same key
        assert result["5.g"].speaker_names == ["Second"]
        assert result["5.g"].testimony_count == 2
        assert result["5.g"].passed is False
        assert provider.complete.call_count == 2
