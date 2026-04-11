"""
Tests for issue_fallback.py — fallback strategy for issues that didn't
match any upcoming events.

The module is split into:
- `_generate_no_match_message` / `_generate_fallback_actions`: pure functions
  — tested with real inputs, no mocks.
- `_find_similar_complaints`: thin wrapper that filters storage results
  — tested with a MagicMock standing in for IssueStorage (external dep).
- `handle_no_match`: orchestrates the above — tested by patching the
  `IssueStorage` class used inside the module.
- `check_banked_complaints_for_new_event`: currently a Phase 1 stub —
  tested for its contract (return shape, jurisdiction gating).

To run:
    pytest packages/civicos-services/tests/test_issue_fallback.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch

import pytest

from civicos_services.issues.issue_fallback import (
    _find_similar_complaints,
    _generate_fallback_actions,
    _generate_no_match_message,
    check_banked_complaints_for_new_event,
    handle_no_match,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(
    id="iss-1",
    issue_type="housing",
    jurisdiction_id="city-san-rafael",
    latitude=None,
    longitude=None,
):
    d = {
        "id": id,
        "issue_type": issue_type,
        "jurisdiction_id": jurisdiction_id,
    }
    if latitude is not None:
        d["latitude"] = latitude
    if longitude is not None:
        d["longitude"] = longitude
    return d


# ---------------------------------------------------------------------------
# _generate_no_match_message: pure function, no mocks
# ---------------------------------------------------------------------------

class TestGenerateNoMatchMessage:
    def test_three_similar_emphasizes_community_formation(self):
        msg = _generate_no_match_message(_issue(issue_type="housing"), 3)
        assert "3 neighbors have reported similar issues" in msg
        assert "Consider connecting to organize" in msg
        assert "San Rafael" in msg
        assert "housing" in msg

    def test_many_similar_includes_count_in_message(self):
        msg = _generate_no_match_message(_issue(issue_type="housing"), 12)
        assert "12 neighbors have reported similar issues" in msg
        assert "Consider connecting to organize" in msg

    def test_exactly_one_similar_uses_singular_grammar(self):
        msg = _generate_no_match_message(_issue(issue_type="potholes"), 1)
        # similar_count == 1 → "1 other neighbors have" per source logic
        assert "1 other neighbors have reported similar issues" in msg
        assert "We're tracking this" in msg
        # Never uses the community formation framing for count < 3
        assert "Consider connecting to organize" not in msg

    def test_two_similar_uses_plural_grammar(self):
        msg = _generate_no_match_message(_issue(issue_type="potholes"), 2)
        # similar_count == 2 → "2 other neighbors have" per source
        assert "2 other neighbors have reported similar issues" in msg
        assert "We're tracking this" in msg
        assert "Consider connecting to organize" not in msg

    def test_zero_similar_promises_notifications(self):
        msg = _generate_no_match_message(_issue(issue_type="housing"), 0)
        assert "we're tracking your concern" in msg
        assert "when other neighbors report similar issues" in msg
        # None of the "similar issues" bookkeeping phrases appear
        assert "other neighbors have reported similar issues" not in msg
        assert "neighbors have reported similar issues" not in msg

    def test_jurisdiction_strips_city_prefix_and_titlecases(self):
        msg = _generate_no_match_message(
            _issue(jurisdiction_id="city-san-rafael"), 0
        )
        assert "San Rafael" in msg
        # Must not leak the raw slug
        assert "city-san-rafael" not in msg

    def test_jurisdiction_without_city_prefix_still_titlecased(self):
        msg = _generate_no_match_message(
            _issue(jurisdiction_id="county-marin"), 0
        )
        assert "County Marin" in msg

    def test_multiword_jurisdiction_titlecased(self):
        msg = _generate_no_match_message(
            _issue(jurisdiction_id="city-mill-valley"), 3
        )
        assert "Mill Valley" in msg
        assert "city-mill-valley" not in msg

    def test_missing_issue_type_defaults_to_this_issue(self):
        issue = {"jurisdiction_id": "city-san-rafael"}
        msg = _generate_no_match_message(issue, 0)
        assert "meetings about this issue" in msg

    def test_missing_jurisdiction_id_renders_empty_name(self):
        issue = {"issue_type": "housing"}
        msg = _generate_no_match_message(issue, 0)
        # Empty jurisdiction → title() of "" is "", so "in ," appears.
        assert "housing in ," in msg

    def test_three_is_the_inclusive_boundary_for_community_framing(self):
        three = _generate_no_match_message(_issue(issue_type="housing"), 3)
        two = _generate_no_match_message(_issue(issue_type="housing"), 2)
        assert "Consider connecting to organize" in three
        assert "Consider connecting to organize" not in two


# ---------------------------------------------------------------------------
# _generate_fallback_actions: pure function
# ---------------------------------------------------------------------------

class TestGenerateFallbackActions:
    def test_always_includes_track_action_first(self):
        actions = _generate_fallback_actions(_issue(), [])
        assert len(actions) == 1
        assert actions[0]["action_type"] == "button"
        assert actions[0]["action_label"] == "Track This Issue"
        assert actions[0]["action_target"] == "track_complaint"
        assert actions[0]["mcp_tool"] == "track_issue"
        assert actions[0]["description"] == "Get notified when meetings are scheduled"

    def test_zero_similar_returns_only_track_action(self):
        actions = _generate_fallback_actions(_issue(), [])
        assert len(actions) == 1
        assert actions[0]["action_label"] == "Track This Issue"

    def test_two_similar_still_returns_only_track_action(self):
        similar = [{"id": "s1"}, {"id": "s2"}]
        actions = _generate_fallback_actions(_issue(), similar)
        # Threshold for view-similar action is 3.
        assert len(actions) == 1
        assert actions[0]["action_label"] == "Track This Issue"

    def test_three_similar_adds_view_similar_action(self):
        similar = [{"id": f"s{i}"} for i in range(3)]
        actions = _generate_fallback_actions(_issue(), similar)
        assert len(actions) == 2
        view = actions[1]
        assert view["action_type"] == "button"
        assert view["action_label"] == "View 3 Similar Complaints"
        assert view["action_target"] == "view_similar"
        assert view["mcp_tool"] == "view_similar_complaints"
        assert view["description"] == "Connect with neighbors on this issue"

    def test_view_similar_label_reflects_exact_count(self):
        similar = [{"id": f"s{i}"} for i in range(7)]
        actions = _generate_fallback_actions(_issue(), similar)
        assert actions[1]["action_label"] == "View 7 Similar Complaints"

    def test_track_action_always_precedes_view_similar(self):
        similar = [{"id": f"s{i}"} for i in range(5)]
        actions = _generate_fallback_actions(_issue(), similar)
        assert actions[0]["action_target"] == "track_complaint"
        assert actions[1]["action_target"] == "view_similar"


# ---------------------------------------------------------------------------
# _find_similar_complaints
# ---------------------------------------------------------------------------

class TestFindSimilarComplaints:
    def test_missing_jurisdiction_returns_empty_list(self):
        storage = MagicMock()
        result = _find_similar_complaints(
            {"issue_type": "housing", "id": "iss-1"}, storage
        )
        assert result == []
        # Storage should not be consulted at all.
        storage.find_similar_complaints.assert_not_called()

    def test_missing_issue_type_returns_empty_list(self):
        storage = MagicMock()
        result = _find_similar_complaints(
            {"jurisdiction_id": "city-san-rafael", "id": "iss-1"}, storage
        )
        assert result == []
        storage.find_similar_complaints.assert_not_called()

    def test_passes_jurisdiction_and_type_to_storage(self):
        storage = MagicMock()
        storage.find_similar_complaints.return_value = []
        result = _find_similar_complaints(
            _issue(issue_type="housing", jurisdiction_id="city-san-rafael"),
            storage,
        )
        storage.find_similar_complaints.assert_called_once_with(
            jurisdiction_id="city-san-rafael",
            issue_type="housing",
            location=None,
        )
        assert result == []

    def test_passes_location_when_both_coordinates_present(self):
        storage = MagicMock()
        storage.find_similar_complaints.return_value = []
        _find_similar_complaints(
            _issue(latitude=37.97, longitude=-122.53),
            storage,
        )
        call_kwargs = storage.find_similar_complaints.call_args.kwargs
        assert call_kwargs["location"] == {
            "latitude": 37.97,
            "longitude": -122.53,
        }

    def test_location_is_none_when_only_latitude_present(self):
        storage = MagicMock()
        storage.find_similar_complaints.return_value = []
        _find_similar_complaints(_issue(latitude=37.97), storage)
        assert storage.find_similar_complaints.call_args.kwargs["location"] is None

    def test_location_is_none_when_only_longitude_present(self):
        storage = MagicMock()
        storage.find_similar_complaints.return_value = []
        _find_similar_complaints(_issue(longitude=-122.53), storage)
        assert storage.find_similar_complaints.call_args.kwargs["location"] is None

    def test_filters_out_current_issue_from_results(self):
        storage = MagicMock()
        storage.find_similar_complaints.return_value = [
            {"id": "iss-1", "issue_type": "housing"},
            {"id": "iss-2", "issue_type": "housing"},
            {"id": "iss-3", "issue_type": "housing"},
        ]
        result = _find_similar_complaints(_issue(id="iss-1"), storage)
        returned_ids = [r["id"] for r in result]
        assert returned_ids == ["iss-2", "iss-3"]

    def test_keeps_all_when_current_issue_not_in_results(self):
        storage = MagicMock()
        storage.find_similar_complaints.return_value = [
            {"id": "iss-42", "issue_type": "housing"},
            {"id": "iss-43", "issue_type": "housing"},
        ]
        result = _find_similar_complaints(_issue(id="iss-1"), storage)
        assert len(result) == 2
        assert [r["id"] for r in result] == ["iss-42", "iss-43"]

    def test_empty_storage_results_returns_empty(self):
        storage = MagicMock()
        storage.find_similar_complaints.return_value = []
        result = _find_similar_complaints(_issue(), storage)
        assert result == []

    def test_zero_coordinates_treated_as_missing_location(self):
        # 0.0 is falsy → source uses `if issue.get("latitude") and ...`
        # so lat/lon of 0 means "no location".
        storage = MagicMock()
        storage.find_similar_complaints.return_value = []
        _find_similar_complaints(
            _issue(latitude=0.0, longitude=0.0),
            storage,
        )
        assert storage.find_similar_complaints.call_args.kwargs["location"] is None


# ---------------------------------------------------------------------------
# handle_no_match: orchestration
# ---------------------------------------------------------------------------

class TestHandleNoMatch:
    def _mock_storage(self, similar=None):
        storage = MagicMock()
        storage.find_similar_complaints.return_value = similar or []
        return storage

    def test_returns_expected_response_shape(self):
        storage = self._mock_storage([])
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(_issue())
        assert set(response.keys()) == {
            "message",
            "actions",
            "similar_count",
            "community_formation_potential",
        }

    def test_similar_count_matches_filtered_list_length(self):
        storage = self._mock_storage(
            [
                {"id": "iss-2"},
                {"id": "iss-3"},
                {"id": "iss-4"},
                {"id": "iss-5"},
            ]
        )
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(_issue(id="iss-1"))
        assert response["similar_count"] == 4

    def test_similar_count_excludes_current_issue(self):
        # Storage returns the current issue in results; it should be filtered.
        storage = self._mock_storage(
            [{"id": "iss-1"}, {"id": "iss-2"}, {"id": "iss-3"}]
        )
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(_issue(id="iss-1"))
        assert response["similar_count"] == 2

    def test_community_formation_potential_high_when_three_similar(self):
        storage = self._mock_storage(
            [{"id": "iss-2"}, {"id": "iss-3"}, {"id": "iss-4"}]
        )
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(_issue(id="iss-1"))
        assert response["community_formation_potential"] == "high"

    def test_community_formation_potential_low_when_two_similar(self):
        storage = self._mock_storage([{"id": "iss-2"}, {"id": "iss-3"}])
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(_issue(id="iss-1"))
        assert response["community_formation_potential"] == "low"

    def test_community_formation_potential_low_when_zero_similar(self):
        storage = self._mock_storage([])
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(_issue(id="iss-1"))
        assert response["community_formation_potential"] == "low"

    def test_message_reflects_community_message_when_three_similar(self):
        storage = self._mock_storage(
            [{"id": "iss-2"}, {"id": "iss-3"}, {"id": "iss-4"}]
        )
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(
                _issue(id="iss-1", issue_type="housing")
            )
        assert "3 neighbors have reported similar issues" in response["message"]
        assert "Consider connecting to organize" in response["message"]

    def test_actions_include_view_similar_when_three_similar(self):
        storage = self._mock_storage(
            [{"id": "iss-2"}, {"id": "iss-3"}, {"id": "iss-4"}]
        )
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(_issue(id="iss-1"))
        labels = [a["action_label"] for a in response["actions"]]
        assert "Track This Issue" in labels
        assert "View 3 Similar Complaints" in labels

    def test_actions_include_only_track_when_no_similar(self):
        storage = self._mock_storage([])
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(_issue(id="iss-1"))
        assert len(response["actions"]) == 1
        assert response["actions"][0]["action_label"] == "Track This Issue"

    def test_forwards_jurisdiction_and_type_to_storage(self):
        storage = self._mock_storage([])
        with patch(
            "civicos_services.issues.issue_fallback.IssueStorage",
            return_value=storage,
        ):
            response = handle_no_match(
                _issue(
                    id="iss-9",
                    issue_type="transportation",
                    jurisdiction_id="city-mill-valley",
                )
            )
        storage.find_similar_complaints.assert_called_once_with(
            jurisdiction_id="city-mill-valley",
            issue_type="transportation",
            location=None,
        )
        # Observable outcome: Mill Valley appears in the message and
        # similar_count matches the (filtered) empty list.
        assert "Mill Valley" in response["message"]
        assert response["similar_count"] == 0


# ---------------------------------------------------------------------------
# check_banked_complaints_for_new_event: Phase 1 stub
# ---------------------------------------------------------------------------

class TestCheckBankedComplaintsForNewEvent:
    def test_missing_jurisdiction_returns_empty_list(self):
        # No jurisdiction at all on the event.
        result = check_banked_complaints_for_new_event({})
        assert result == []

    def test_missing_jurisdiction_id_key_returns_empty_list(self):
        result = check_banked_complaints_for_new_event(
            {"jurisdiction": {}}
        )
        assert result == []

    def test_phase_one_stub_returns_empty_for_valid_event(self):
        # The Phase 1 implementation is a stub that returns [] even when a
        # jurisdiction is present. Pinning this so a future Phase 2
        # implementation must update the test on purpose.
        event = {
            "jurisdiction": {"id": "city-san-rafael"},
            "title": "City Council Meeting",
        }
        result = check_banked_complaints_for_new_event(event)
        assert result == []

    def test_stub_ignores_event_title_and_agenda_content(self):
        # Even with rich agenda content that *would* match a banked issue
        # in a Phase 2 implementation, the Phase 1 stub returns [].
        event = {
            "jurisdiction": {"id": "city-san-rafael"},
            "title": "Housing development discussion",
            "description": "tenant zoning permit",
            "agenda_expansion": {
                "actionable_items": [
                    {"title": "Housing plan", "project_types": ["housing"]}
                ]
            },
        }
        result = check_banked_complaints_for_new_event(event)
        assert result == []
