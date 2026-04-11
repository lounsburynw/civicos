"""
Tests for issues/issue_handler.py — ComplaintHandler end-to-end orchestration.

The handler wires together four collaborators:
- IssueDetector (LLM-based intent detection)
- IssueStorage  (SQLite-backed issue CRUD)
- match_issue_to_events (keyword matcher)
- handle_no_match (fallback response builder)

The test strategy is to mock exactly those external collaborators (patched at
the import site inside the handler module) and exercise the real handler
methods — `handle_user_message`, `_create_and_match`, `_format_match_response`,
`_handle_no_match`, and `_normalize_issue_type` — with specific input/output
assertions.

To run:
    pytest packages/civicos-services/tests/test_issue_handler.py -q --override-ini="addopts="
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.issues.issue_detector import ComplaintIntent
from civicos_services.issues.issue_handler import (
    ComplaintHandler,
    handle_message,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handler(
    detector: MagicMock | None = None,
    storage: MagicMock | None = None,
) -> tuple[ComplaintHandler, MagicMock, MagicMock]:
    """
    Build a ComplaintHandler with both collaborators replaced by mocks.

    We patch `IssueDetector` and `IssueStorage` at the handler's import site
    so that `__init__` uses the mocks without doing any real IO (no OpenAI
    client creation, no SQLite file touched).
    """
    detector = detector or MagicMock()
    storage = storage or MagicMock()
    with patch(
        "civicos_services.issues.issue_handler.IssueDetector",
        return_value=detector,
    ), patch(
        "civicos_services.issues.issue_handler.IssueStorage",
        return_value=storage,
    ):
        handler = ComplaintHandler(openai_api_key="sk-test-fake")
    return handler, detector, storage


def _intent(
    description: str = "Pothole on 4th Street",
    issue_type: str = "infrastructure",
    jurisdiction_id: str | None = "city-san-rafael",
    location_mention: str | None = "San Rafael",
    confidence: str = "high",
) -> ComplaintIntent:
    return ComplaintIntent(
        description=description,
        issue_type=issue_type,
        jurisdiction_id=jurisdiction_id,
        location_mention=location_mention,
        confidence=confidence,
    )


def _issue(
    id: str = "iss-123",
    issue_type: str = "infrastructure",
    jurisdiction_id: str = "city-san-rafael",
    description: str = "Pothole on 4th Street",
) -> dict:
    return {
        "id": id,
        "user_id": "user_001",
        "description": description,
        "issue_type": issue_type,
        "jurisdiction_id": jurisdiction_id,
        "status": "open",
    }


def _event(
    title: str = "City Council Meeting",
    when: str = "2026-04-15 19:00",
    when_human: str | None = "Tuesday, April 15 at 7pm",
    meeting_type: str = "city_council",
) -> dict:
    d = {
        "title": title,
        "when": when,
        "meeting_type": meeting_type,
    }
    if when_human is not None:
        d["when_human"] = when_human
    return d


# ---------------------------------------------------------------------------
# ComplaintHandler.__init__
# ---------------------------------------------------------------------------


class TestComplaintHandlerInit:
    def test_constructs_detector_with_provided_key(self):
        with patch(
            "civicos_services.issues.issue_handler.IssueDetector"
        ) as mock_detector_cls, patch(
            "civicos_services.issues.issue_handler.IssueStorage"
        ) as mock_storage_cls:
            detector_stub = MagicMock(name="detector")
            storage_stub = MagicMock(name="storage")
            mock_detector_cls.return_value = detector_stub
            mock_storage_cls.return_value = storage_stub

            handler = ComplaintHandler(openai_api_key="sk-abc-123")

        assert mock_detector_cls.call_count == 1
        # positional arg OR kwarg — both forms are acceptable; pin positional
        args, kwargs = mock_detector_cls.call_args
        assert args == ("sk-abc-123",) or kwargs == {"openai_api_key": "sk-abc-123"}
        mock_storage_cls.assert_called_once_with()
        # Observable side-effects: the constructed collaborators are stored
        assert handler.detector is detector_stub
        assert handler.storage is storage_stub

    def test_constructs_detector_with_none_key_by_default(self):
        with patch(
            "civicos_services.issues.issue_handler.IssueDetector"
        ) as mock_detector_cls, patch(
            "civicos_services.issues.issue_handler.IssueStorage"
        ):
            handler = ComplaintHandler()
        args, kwargs = mock_detector_cls.call_args
        # The default is None — test checks we passed None (positional or kwarg)
        assert args == (None,) or kwargs == {"openai_api_key": None}
        # The detector attribute should be whatever the (mocked) class returned
        assert handler.detector is mock_detector_cls.return_value

    def test_stores_detector_and_storage_as_attributes(self):
        handler, detector, storage = _make_handler()
        assert handler.detector is detector
        assert handler.storage is storage


# ---------------------------------------------------------------------------
# handle_user_message — top-level flow
# ---------------------------------------------------------------------------


class TestHandleUserMessageNotComplaint:
    def test_returns_not_complaint_shape_when_detector_returns_none(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = None

        result = handler.handle_user_message(
            message="When is the next city council meeting?",
            user_id="user_001",
        )

        assert result == {
            "type": "not_complaint",
            "message": "How can I help you with civic information?",
        }

    def test_not_complaint_does_not_create_issue(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = None

        result = handler.handle_user_message("Where is the library?", "user_001")

        assert storage.create_issue.call_count == 0
        assert storage.get_issue.call_count == 0
        # Pin the resulting shape too so a mutation that turns the
        # early return into the complaint pipeline would also fail
        # this test.
        assert result["type"] == "not_complaint"

    def test_forwards_message_and_context_to_detector(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = None

        ctx = {"jurisdiction_id": "city-berkeley"}
        result = handler.handle_user_message("Hi there friend", "user_001", ctx)

        detector.detect_complaint.assert_called_once_with("Hi there friend", ctx)
        # Also pin the returned shape so a mutation that drops the early
        # return would be caught.
        assert result["type"] == "not_complaint"

    def test_default_user_context_is_none(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = None

        result = handler.handle_user_message("Short question", "user_001")

        detector.detect_complaint.assert_called_once_with("Short question", None)
        assert result["type"] == "not_complaint"


# ---------------------------------------------------------------------------
# handle_user_message — missing jurisdiction branch
# ---------------------------------------------------------------------------


class TestHandleUserMessageMissingJurisdiction:
    def test_missing_jurisdiction_returns_prompt_shape(self):
        handler, detector, storage = _make_handler()
        intent = _intent(jurisdiction_id=None)
        detector.detect_complaint.return_value = intent

        result = handler.handle_user_message("Pothole in some city", "user_001")

        assert result["type"] == "missing_jurisdiction"
        assert result["message"] == (
            "Which city is this issue in? (e.g., Berkeley, Oakland, San Rafael)"
        )

    def test_missing_jurisdiction_includes_intent_dict(self):
        handler, detector, storage = _make_handler()
        intent = _intent(
            description="Massive pothole",
            issue_type="infrastructure",
            jurisdiction_id=None,
            location_mention=None,
            confidence="high",
        )
        detector.detect_complaint.return_value = intent

        result = handler.handle_user_message("Pothole", "user_001")

        assert result["intent"] == {
            "description": "Massive pothole",
            "issue_type": "infrastructure",
            "jurisdiction_id": None,
            "location_mention": None,
            "confidence": "high",
        }

    def test_missing_jurisdiction_does_not_create_issue(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent(jurisdiction_id=None)

        result = handler.handle_user_message("Pothole", "user_001")

        assert storage.create_issue.call_count == 0
        assert result["type"] == "missing_jurisdiction"


# ---------------------------------------------------------------------------
# handle_user_message — matched path
# ---------------------------------------------------------------------------


class TestHandleUserMessageMatched:
    def test_match_path_creates_then_retrieves_issue(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-123"
        storage.get_issue.return_value = _issue(id="iss-123")

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[(_event(title="Council Meeting"), 8.5, "Keyword match")],
        ):
            result = handler.handle_user_message(
                "Pothole on Main in San Rafael", "user_001"
            )

        storage.create_issue.assert_called_once_with(
            user_id="user_001",
            description="Pothole on 4th Street",
            jurisdiction_id="city-san-rafael",
            issue_type="infrastructure",
        )
        storage.get_issue.assert_called_once_with("iss-123")
        # Pin the returned issue_id so a mutation swapping issue_id for
        # something else in the response would fail.
        assert result["issue_id"] == "iss-123"

    def test_match_path_returns_matched_response_type(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-123"
        storage.get_issue.return_value = _issue(id="iss-123")

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[
                (_event(title="City Council", when_human="Apr 15 at 7pm"), 9.2, "keywords match 'pothole'"),
            ],
        ):
            result = handler.handle_user_message("Pothole issue", "user_001")

        assert result["type"] == "matched"
        assert result["issue_id"] == "iss-123"
        assert result["message"] == (
            "Found 1 relevant civic meetings where you can address this issue:"
        )

    def test_match_response_includes_top_three_matches_max(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-456"
        storage.get_issue.return_value = _issue(id="iss-456")

        events = [
            (_event(title=f"Meeting {i}"), float(10 - i), f"reason-{i}") for i in range(5)
        ]

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=events,
        ):
            result = handler.handle_user_message("Pothole", "user_001")

        assert len(result["matches"]) == 3
        assert [m["title"] for m in result["matches"]] == [
            "Meeting 0",
            "Meeting 1",
            "Meeting 2",
        ]
        # But the overall count should reflect the full match count, not the slice
        assert "Found 5 relevant civic meetings" in result["message"]

    def test_match_response_fields_use_event_data(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = _issue(id="iss-1")

        event = _event(
            title="City Council Study Session",
            when="2026-04-15T19:00",
            when_human="Tuesday, April 15 at 7pm",
            meeting_type="city_council",
        )

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[(event, 7.84, "Housing keywords match")],
        ):
            result = handler.handle_user_message("Pothole", "user_001")

        m = result["matches"][0]
        assert m["title"] == "City Council Study Session"
        assert m["when"] == "Tuesday, April 15 at 7pm"
        assert m["meeting_type"] == "city_council"
        assert m["score"] == 7.8  # round(7.84, 1)
        assert m["why_relevant"] == "Housing keywords match"

    def test_match_uses_when_when_when_human_missing(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = _issue(id="iss-1")

        # No when_human — event.get('when_human', event.get('when')) falls through
        event = _event(
            title="Planning Commission",
            when="2026-04-20 18:00",
            when_human=None,
            meeting_type="planning",
        )

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[(event, 5.0, "keywords match")],
        ):
            result = handler.handle_user_message("Pothole", "user_001")

        assert result["matches"][0]["when"] == "2026-04-20 18:00"

    def test_match_meeting_type_defaults_to_unknown(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = _issue(id="iss-1")

        event = {"title": "Mystery Meeting", "when": "2026-04-20"}
        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[(event, 3.0, "some reason")],
        ):
            result = handler.handle_user_message("Pothole", "user_001")

        assert result["matches"][0]["meeting_type"] == "unknown"

    def test_match_score_rounded_to_one_decimal(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = _issue(id="iss-1")

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[
                (_event(), 3.14159, "reason-a"),
                (_event(title="Other"), 2.71828, "reason-b"),
            ],
        ):
            result = handler.handle_user_message("Pothole", "user_001")

        assert result["matches"][0]["score"] == 3.1
        assert result["matches"][1]["score"] == 2.7

    def test_match_response_actions_are_fixed_pair(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = _issue(id="iss-1")

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[(_event(), 5.0, "reason")],
        ):
            result = handler.handle_user_message("Pothole", "user_001")

        assert result["actions"] == [
            {"type": "view_details", "label": "View Meeting Details"},
            {"type": "get_reminders", "label": "Get Reminders"},
        ]

    def test_matcher_called_with_full_issue_dict(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        issue_record = _issue(id="iss-1", description="Pothole on 4th")
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = issue_record

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[(_event(), 5.0, "reason")],
        ) as mock_match:
            result = handler.handle_user_message("Pothole", "user_001")

        mock_match.assert_called_once_with(issue_record)
        # Also pin the downstream matched shape so mutations that swap
        # the argument or drop the call would be detected.
        assert result["type"] == "matched"
        assert result["issue_id"] == "iss-1"


# ---------------------------------------------------------------------------
# handle_user_message — no-match path
# ---------------------------------------------------------------------------


class TestHandleUserMessageNoMatch:
    def test_no_match_returns_no_match_response_type(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-empty"
        storage.get_issue.return_value = _issue(id="iss-empty")

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[],
        ), patch(
            "civicos_services.issues.issue_handler.handle_no_match",
            return_value={
                "message": "We're tracking this — 2 other neighbors reported similar.",
                "similar_count": 2,
                "actions": [{"type": "track", "label": "Track"}],
            },
        ):
            result = handler.handle_user_message("Pothole", "user_001")

        assert result["type"] == "no_match"
        assert result["issue_id"] == "iss-empty"
        assert result["message"] == (
            "We're tracking this — 2 other neighbors reported similar."
        )
        assert result["similar_count"] == 2
        assert result["actions"] == [{"type": "track", "label": "Track"}]

    def test_no_match_defaults_similar_count_when_absent(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-empty"
        storage.get_issue.return_value = _issue(id="iss-empty")

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[],
        ), patch(
            "civicos_services.issues.issue_handler.handle_no_match",
            return_value={"message": "Banked."},
        ):
            result = handler.handle_user_message("Pothole", "user_001")

        assert result["similar_count"] == 0
        assert result["actions"] == []

    def test_no_match_fallback_receives_issue_dict(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        issue_record = _issue(id="iss-1", issue_type="housing")
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = issue_record

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[],
        ), patch(
            "civicos_services.issues.issue_handler.handle_no_match",
            return_value={"message": "ok"},
        ) as mock_fallback:
            result = handler.handle_user_message("Rent is rising", "user_001")

        mock_fallback.assert_called_once_with(issue_record)
        # Pin the response type so a mutation that forgets to call the
        # fallback (and falls through) would fail loudly.
        assert result["type"] == "no_match"
        assert result["message"] == "ok"


# ---------------------------------------------------------------------------
# handle_user_message — storage failure branch
# ---------------------------------------------------------------------------


class TestHandleUserMessageStorageFailure:
    def test_returns_error_when_get_issue_returns_none(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent()
        storage.create_issue.return_value = "iss-ghost"
        storage.get_issue.return_value = None

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events"
        ) as mock_match:
            result = handler.handle_user_message("Pothole", "user_001")

        assert result == {
            "type": "error",
            "message": "Failed to create issue record",
        }
        # Matcher should NOT run if the issue lookup failed
        assert mock_match.call_count == 0


# ---------------------------------------------------------------------------
# _normalize_issue_type — pure logic
# ---------------------------------------------------------------------------


class TestNormalizeIssueType:
    @pytest.mark.parametrize(
        "issue_type",
        [
            "housing",
            "transportation",
            "environment",
            "public_safety",
            "infrastructure",
        ],
    )
    def test_db_schema_types_pass_through_unchanged(self, issue_type):
        handler, _, _ = _make_handler()
        assert handler._normalize_issue_type(issue_type) == issue_type

    def test_community_is_mapped_to_other(self):
        handler, _, _ = _make_handler()
        assert handler._normalize_issue_type("community") == "other"

    def test_unknown_type_passes_through_unchanged(self):
        # The normalizer only rewrites 'community'. Anything else — even
        # an unknown label — is returned verbatim. Pin this behavior.
        handler, _, _ = _make_handler()
        assert handler._normalize_issue_type("wiggle") == "wiggle"

    def test_empty_string_passes_through(self):
        handler, _, _ = _make_handler()
        assert handler._normalize_issue_type("") == ""

    def test_community_case_sensitive_no_uppercase_match(self):
        # The source does `== 'community'` — uppercase 'COMMUNITY' should
        # pass through unchanged, not map to 'other'.
        handler, _, _ = _make_handler()
        assert handler._normalize_issue_type("COMMUNITY") == "COMMUNITY"


# ---------------------------------------------------------------------------
# _normalize_issue_type wired through the pipeline
# ---------------------------------------------------------------------------


class TestNormalizationThroughPipeline:
    def test_community_intent_stored_as_other(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent(issue_type="community")
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = _issue(
            id="iss-1", issue_type="other"
        )

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[],
        ), patch(
            "civicos_services.issues.issue_handler.handle_no_match",
            return_value={"message": "ok"},
        ):
            handler.handle_user_message("Library program request", "user_001")

        # The handler should have translated 'community' → 'other' before storing
        assert storage.create_issue.call_args.kwargs["issue_type"] == "other"

    def test_housing_intent_stored_as_housing(self):
        handler, detector, storage = _make_handler()
        detector.detect_complaint.return_value = _intent(issue_type="housing")
        storage.create_issue.return_value = "iss-1"
        storage.get_issue.return_value = _issue(id="iss-1", issue_type="housing")

        with patch(
            "civicos_services.issues.issue_handler.match_issue_to_events",
            return_value=[],
        ), patch(
            "civicos_services.issues.issue_handler.handle_no_match",
            return_value={"message": "ok"},
        ):
            handler.handle_user_message("Rent hike", "user_001")

        assert storage.create_issue.call_args.kwargs["issue_type"] == "housing"


# ---------------------------------------------------------------------------
# _format_match_response — direct unit tests
# ---------------------------------------------------------------------------


class TestFormatMatchResponseDirect:
    def test_single_match_formatted(self):
        handler, _, _ = _make_handler()
        issue = _issue(id="iss-42")
        matches = [(_event(title="Council", when_human="Thu 7pm"), 6.0, "reason-1")]

        result = handler._format_match_response(issue, matches)

        assert result == {
            "type": "matched",
            "issue_id": "iss-42",
            "message": "Found 1 relevant civic meetings where you can address this issue:",
            "matches": [
                {
                    "title": "Council",
                    "when": "Thu 7pm",
                    "meeting_type": "city_council",
                    "score": 6.0,
                    "why_relevant": "reason-1",
                }
            ],
            "actions": [
                {"type": "view_details", "label": "View Meeting Details"},
                {"type": "get_reminders", "label": "Get Reminders"},
            ],
        }

    def test_exactly_three_matches_are_all_included(self):
        handler, _, _ = _make_handler()
        issue = _issue(id="iss-1")
        matches = [
            (_event(title=f"Meeting {i}"), 5.0, f"reason {i}") for i in range(3)
        ]

        result = handler._format_match_response(issue, matches)

        assert len(result["matches"]) == 3
        assert result["message"] == (
            "Found 3 relevant civic meetings where you can address this issue:"
        )

    def test_empty_matches_list_produces_empty_matches_and_zero_count(self):
        # `_format_match_response` is only called when `matches` is truthy in
        # normal flow, but the method itself should still behave predictably
        # if someone hands it an empty list (defensive contract).
        handler, _, _ = _make_handler()
        issue = _issue(id="iss-1")

        result = handler._format_match_response(issue, [])

        assert result["matches"] == []
        assert result["message"] == (
            "Found 0 relevant civic meetings where you can address this issue:"
        )


# ---------------------------------------------------------------------------
# _handle_no_match — direct unit tests
# ---------------------------------------------------------------------------


class TestHandleNoMatchDirect:
    def test_returns_expected_shape_and_values(self):
        handler, _, _ = _make_handler()
        issue = _issue(id="iss-nm-1")

        with patch(
            "civicos_services.issues.issue_handler.handle_no_match",
            return_value={
                "message": "3 neighbors reported similar",
                "similar_count": 3,
                "actions": [{"type": "organize", "label": "Connect with Neighbors"}],
            },
        ):
            result = handler._handle_no_match(issue)

        assert result == {
            "type": "no_match",
            "issue_id": "iss-nm-1",
            "message": "3 neighbors reported similar",
            "similar_count": 3,
            "actions": [{"type": "organize", "label": "Connect with Neighbors"}],
        }

    def test_defaults_when_fallback_response_lacks_optional_keys(self):
        handler, _, _ = _make_handler()
        issue = _issue(id="iss-nm-2")

        with patch(
            "civicos_services.issues.issue_handler.handle_no_match",
            return_value={"message": "Banked."},
        ):
            result = handler._handle_no_match(issue)

        assert result["similar_count"] == 0
        assert result["actions"] == []
        assert result["message"] == "Banked."
        assert result["issue_id"] == "iss-nm-2"
        assert result["type"] == "no_match"


# ---------------------------------------------------------------------------
# handle_message (module-level convenience)
# ---------------------------------------------------------------------------


class TestHandleMessageConvenience:
    def test_constructs_handler_and_delegates(self):
        with patch(
            "civicos_services.issues.issue_handler.ComplaintHandler"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.handle_user_message.return_value = {
                "type": "not_complaint",
                "message": "How can I help you with civic information?",
            }
            mock_cls.return_value = mock_instance

            result = handle_message(
                message="hello world",
                user_id="user_001",
                user_context={"jurisdiction_id": "city-berkeley"},
            )

        mock_cls.assert_called_once_with()
        mock_instance.handle_user_message.assert_called_once_with(
            "hello world",
            "user_001",
            {"jurisdiction_id": "city-berkeley"},
        )
        assert result == {
            "type": "not_complaint",
            "message": "How can I help you with civic information?",
        }

    def test_default_user_context_is_none(self):
        with patch(
            "civicos_services.issues.issue_handler.ComplaintHandler"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.handle_user_message.return_value = {"type": "not_complaint"}
            mock_cls.return_value = mock_instance

            result = handle_message("hi there friend", "user_001")

        mock_instance.handle_user_message.assert_called_once_with(
            "hi there friend", "user_001", None
        )
        assert result == {"type": "not_complaint"}
