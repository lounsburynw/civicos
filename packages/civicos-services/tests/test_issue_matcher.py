"""
Tests for issue_matcher.py — keyword-based complaint-to-event matching
with temporal scoring, agenda-item expansion, and match statistics.

Pure scoring logic is tested against real inputs with pinned expected values.
File loading is tested against a real tmp_path filesystem (no mocks of the
subject under test).

To run:
    pytest packages/civicos-services/tests/test_issue_matcher.py -q --override-ini="addopts="
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from civicos_services.issues.issue_matcher import (
    HIGH_CONFIDENCE_THRESHOLD,
    ISSUE_TYPE_KEYWORDS,
    MINIMUM_MATCH_SCORE,
    _load_jurisdiction_events,
    _score_event,
    get_match_statistics,
    match_issue_to_events,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_future(days: int) -> str:
    """ISO8601 UTC timestamp `days` from now (with +00:00 offset)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _complaint(description="", issue_type="", jurisdiction_id="city-berkeley"):
    return {
        "description": description,
        "issue_type": issue_type,
        "jurisdiction_id": jurisdiction_id,
    }


def _event(
    title="",
    description="",
    project_type="",
    when=None,
    agenda_expansion=None,
):
    e = {
        "title": title,
        "description": description,
        "project_type": project_type,
    }
    if when is not None:
        e["when"] = when
    if agenda_expansion is not None:
        e["agenda_expansion"] = agenda_expansion
    return e


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_minimum_match_score_is_25(self):
        assert MINIMUM_MATCH_SCORE == 25

    def test_high_confidence_threshold_is_60(self):
        assert HIGH_CONFIDENCE_THRESHOLD == 60

    def test_exact_set_of_issue_type_keys(self):
        assert set(ISSUE_TYPE_KEYWORDS.keys()) == {
            "housing",
            "transportation",
            "environment",
            "infrastructure",
            "public_safety",
            "community",
        }

    def test_housing_keywords_include_core_terms(self):
        housing = ISSUE_TYPE_KEYWORDS["housing"]
        assert "housing" in housing
        assert "zoning" in housing
        assert "permit" in housing
        assert "tenant" in housing


# ---------------------------------------------------------------------------
# _score_event: keyword matching
# ---------------------------------------------------------------------------

class TestScoreEventKeywordMatching:
    def test_no_keyword_hits_returns_zero(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Budget meeting", description="fiscal year")
        score, reason = _score_event(complaint, event)
        assert score == 0
        assert reason == "no clear match"

    def test_single_keyword_match_scores_10(self):
        # "permit" is a housing keyword; nothing else in title matches.
        complaint = _complaint(issue_type="housing")
        event = _event(title="discussion about permit")
        score, reason = _score_event(complaint, event)
        assert score == 10
        assert "1 keyword matches" in reason

    def test_three_distinct_keywords_score_30(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="housing zoning permit")
        score, reason = _score_event(complaint, event)
        assert score == 30
        assert "3 keyword matches" in reason

    def test_two_keyword_matches_fall_below_minimum_threshold(self):
        # Demonstrates why the 25-point MINIMUM_MATCH_SCORE exists.
        complaint = _complaint(issue_type="housing")
        event = _event(title="housing permit")  # 2 keywords = 20
        score, _ = _score_event(complaint, event)
        assert score == 20
        assert score < MINIMUM_MATCH_SCORE

    def test_keywords_counted_in_description_not_just_title(self):
        # Event description should be searched alongside the title.
        complaint = _complaint(issue_type="transportation")
        event = _event(
            title="Public hearing",
            description="bus parking traffic on sidewalk",
        )
        # bus, parking, traffic, sidewalk = 4 hits → 40
        score, _ = _score_event(complaint, event)
        assert score == 40

    def test_keyword_matching_is_case_insensitive(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="HOUSING ZONING PERMIT")
        score, _ = _score_event(complaint, event)
        assert score == 30

    def test_unknown_issue_type_produces_no_keyword_bonus(self):
        complaint = _complaint(issue_type="not-a-real-type")
        event = _event(title="housing zoning permit")
        score, _ = _score_event(complaint, event)
        assert score == 0

    def test_environment_keywords_scored(self):
        # Regression for per-category keyword lists beyond housing.
        complaint = _complaint(issue_type="environment")
        event = _event(title="tree pollution wildfire")
        score, _ = _score_event(complaint, event)
        assert score == 30


# ---------------------------------------------------------------------------
# _score_event: project type matching
# ---------------------------------------------------------------------------

class TestScoreEventProjectType:
    def test_matching_project_type_adds_20(self):
        complaint = _complaint(issue_type="environment")
        event = _event(title="Generic meeting", project_type="environment")
        score, reason = _score_event(complaint, event)
        assert score == 20
        assert "project type: environment" in reason

    def test_non_matching_project_type_adds_nothing(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", project_type="transportation")
        score, _ = _score_event(complaint, event)
        assert score == 0

    def test_missing_project_type_on_event_skips_bonus(self):
        # Complaint has a real issue type, event has no project_type at all.
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting")  # project_type="" default
        score, reason = _score_event(complaint, event)
        assert score == 0
        assert "project type" not in reason


# ---------------------------------------------------------------------------
# _score_event: temporal proximity
# ---------------------------------------------------------------------------

class TestScoreEventTemporal:
    def test_event_within_one_week_adds_15(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", when=_iso_future(3))
        score, reason = _score_event(complaint, event)
        assert score == 15
        assert "within 1 week" in reason

    def test_event_within_one_month_adds_10(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", when=_iso_future(20))
        score, reason = _score_event(complaint, event)
        assert score == 10
        assert "within 1 month" in reason

    def test_event_within_three_months_adds_5(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", when=_iso_future(60))
        score, reason = _score_event(complaint, event)
        assert score == 5
        assert "within 3 months" in reason

    def test_event_beyond_three_months_adds_no_temporal_bonus(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", when=_iso_future(200))
        score, reason = _score_event(complaint, event)
        assert score == 0
        assert "month" not in reason
        assert "week" not in reason

    def test_past_event_adds_no_temporal_bonus(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", when=_iso_future(-5))
        score, _ = _score_event(complaint, event)
        assert score == 0

    def test_invalid_date_string_is_tolerated_no_crash(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", when="not-a-date")
        score, reason = _score_event(complaint, event)
        assert score == 0
        assert reason == "no clear match"

    def test_z_suffix_datetime_parsed_as_utc(self):
        future = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
        z_date = future.strftime("%Y-%m-%dT%H:%M:%SZ")
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", when=z_date)
        score, reason = _score_event(complaint, event)
        assert score == 15
        assert "within 1 week" in reason

    def test_naive_datetime_treated_as_utc(self):
        future = datetime.now(timezone.utc) + timedelta(days=3)
        naive_str = future.strftime("%Y-%m-%dT%H:%M:%S")  # no tz info
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting", when=naive_str)
        score, _ = _score_event(complaint, event)
        assert score == 15

    def test_missing_when_field_adds_no_temporal_bonus(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic meeting")  # no when
        score, reason = _score_event(complaint, event)
        assert score == 0
        assert reason == "no clear match"


# ---------------------------------------------------------------------------
# _score_event: description overlap
# ---------------------------------------------------------------------------

class TestScoreEventDescriptionOverlap:
    def test_three_long_word_overlap_adds_10(self):
        complaint = _complaint(
            description="concerns nearby playground sidewalks",
            issue_type="unknown-type",  # no keyword matches
        )
        event = _event(
            title="concerns",
            description="nearby playground sidewalks",
        )
        score, reason = _score_event(complaint, event)
        assert score == 10
        assert "description overlap: 4 words" in reason

    def test_two_long_word_overlap_adds_nothing(self):
        complaint = _complaint(
            description="concerns nearby location",
            issue_type="unknown-type",
        )
        event = _event(title="concerns", description="nearby other")
        score, reason = _score_event(complaint, event)
        # Only 2 long words in common ("concerns", "nearby") → no bonus.
        assert score == 0
        assert "overlap" not in reason

    def test_short_words_under_five_chars_ignored(self):
        # Every word is <=4 chars, so complaint_words is empty and no overlap.
        complaint = _complaint(
            description="a an the at in on",
            issue_type="unknown-type",
        )
        event = _event(title="a an the", description="at in on")
        score, _ = _score_event(complaint, event)
        assert score == 0

    def test_five_char_word_counted_as_long_word(self):
        # Boundary check: "len(w) > 4" means 5+ chars qualify.
        complaint = _complaint(
            description="roads bikes parks water trees",
            issue_type="unknown-type",
        )
        event = _event(description="roads bikes parks water trees")
        score, reason = _score_event(complaint, event)
        assert score == 10
        assert "description overlap" in reason


# ---------------------------------------------------------------------------
# _score_event: agenda-item expansion
# ---------------------------------------------------------------------------

class TestScoreEventAgendaItems:
    def test_agenda_item_project_type_match_adds_20(self):
        complaint = _complaint(issue_type="environment")
        event = _event(
            title="Committee meeting",  # no keyword hits
            agenda_expansion={
                "actionable_items": [
                    {
                        "title": "xyz abc",
                        "description": "",
                        "project_types": ["environment"],
                    }
                ]
            },
        )
        score, reason = _score_event(complaint, event)
        assert score == 20
        assert "agenda item" in reason

    def test_agenda_item_keywords_scored_at_5_each(self):
        complaint = _complaint(issue_type="transportation")
        event = _event(
            title="Committee meeting",
            agenda_expansion={
                "actionable_items": [
                    {
                        "title": "bus parking discussion",
                        "description": "traffic flow",
                        "project_types": [],
                    }
                ]
            },
        )
        # "bus parking discussion traffic flow" matches bus, parking,
        # traffic = 3 hits → 3 × 5 = 15 points.
        score, reason = _score_event(complaint, event)
        assert score == 15
        assert "3 keywords in agenda" in reason

    def test_only_first_matching_agenda_item_counted(self):
        # The function breaks after the first non-zero-scoring agenda item.
        complaint = _complaint(issue_type="housing")
        event = _event(
            title="Meeting",
            agenda_expansion={
                "actionable_items": [
                    {
                        "title": "housing development permit",
                        "description": "",
                        "project_types": ["housing"],
                    },
                    {
                        "title": "zoning variance tenant building",
                        "description": "",
                        "project_types": ["housing"],
                    },
                ]
            },
        )
        # First item: project_types match (+20) +
        #   3 keywords in "housing development permit" (3×5=15) = 35.
        # Second item ignored due to break.
        score, _ = _score_event(complaint, event)
        assert score == 35

    def test_empty_actionable_items_list_skipped(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic", agenda_expansion={"actionable_items": []})
        score, reason = _score_event(complaint, event)
        assert score == 0
        assert reason == "no clear match"

    def test_missing_agenda_expansion_skipped(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="Generic")
        score, _ = _score_event(complaint, event)
        assert score == 0

    def test_agenda_item_with_no_project_match_and_no_keywords_zero(self):
        complaint = _complaint(issue_type="housing")
        event = _event(
            title="Generic",
            agenda_expansion={
                "actionable_items": [
                    {
                        "title": "fiscal year report",
                        "description": "budget review",
                        "project_types": ["finance"],
                    }
                ]
            },
        )
        score, _ = _score_event(complaint, event)
        assert score == 0


# ---------------------------------------------------------------------------
# _score_event: combined scoring
# ---------------------------------------------------------------------------

class TestScoreEventCombined:
    def test_all_scoring_components_stack(self):
        complaint = _complaint(
            description="housing development permit building",
            issue_type="housing",
        )
        event = _event(
            title="housing development permit building",
            description="",
            project_type="housing",
            when=_iso_future(3),
        )
        # Keywords: housing, development, permit, building → 4 × 10 = 40
        # Project type: housing == housing → +20
        # Temporal: within 1 week → +15
        # Description overlap: 4 long words shared → +10
        # Total: 85
        score, reason = _score_event(complaint, event)
        assert score == 85
        assert "4 keyword matches" in reason
        assert "project type: housing" in reason
        assert "within 1 week" in reason
        assert "description overlap" in reason

    def test_reason_parts_joined_with_commas(self):
        complaint = _complaint(issue_type="housing")
        event = _event(title="housing zoning permit", project_type="housing")
        score, reason = _score_event(complaint, event)
        # 3 keywords (30) + project type (20) = 50
        assert score == 50
        assert reason.count(",") == 1  # two reason parts → one comma


# ---------------------------------------------------------------------------
# match_issue_to_events: integration against a real tmp_path filesystem
# ---------------------------------------------------------------------------

class TestMatchIssueToEvents:
    @staticmethod
    def _write_events(tmp_path, jurisdiction_id, events_list, suffix="2026-04-01"):
        events_dir = tmp_path / "data" / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        f = events_dir / f"events_{jurisdiction_id}_{suffix}.json"
        f.write_text(json.dumps({"events": events_list}))
        return f

    def test_missing_jurisdiction_returns_empty_list(self):
        complaint = {"description": "housing", "issue_type": "housing"}
        result = match_issue_to_events(complaint)
        assert result == []

    def test_no_events_directory_returns_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        complaint = _complaint(issue_type="housing")
        result = match_issue_to_events(complaint)
        assert result == []

    def test_only_scores_at_or_above_threshold_are_returned(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        events = [
            _event(title="housing permit"),  # 20 — below threshold
            _event(title="housing zoning permit"),  # 30 — above threshold
        ]
        self._write_events(tmp_path, "city-berkeley", events)
        complaint = _complaint(
            issue_type="housing", jurisdiction_id="city-berkeley"
        )
        result = match_issue_to_events(complaint)
        assert len(result) == 1
        assert result[0][0]["title"] == "housing zoning permit"
        assert result[0][1] == 30

    def test_results_sorted_by_score_descending(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        events = [
            _event(title="housing zoning permit"),  # 30
            _event(title="housing zoning permit building tenant"),  # 50
            _event(title="housing zoning permit building"),  # 40
        ]
        self._write_events(tmp_path, "city-berkeley", events)
        complaint = _complaint(
            issue_type="housing", jurisdiction_id="city-berkeley"
        )
        result = match_issue_to_events(complaint)
        scores = [r[1] for r in result]
        assert scores == [50, 40, 30]

    def test_max_matches_limit_is_applied(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        events = [_event(title="housing zoning permit") for _ in range(5)]
        self._write_events(tmp_path, "city-berkeley", events)
        complaint = _complaint(
            issue_type="housing", jurisdiction_id="city-berkeley"
        )
        result = match_issue_to_events(complaint, max_matches=2)
        assert len(result) == 2
        assert all(r[1] == 30 for r in result)

    def test_explicit_jurisdiction_override_beats_complaint_field(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        events = [_event(title="housing zoning permit")]
        self._write_events(tmp_path, "city-oakland", events)
        # Complaint says berkeley, override says oakland → oakland file used.
        complaint = _complaint(
            issue_type="housing", jurisdiction_id="city-berkeley"
        )
        result = match_issue_to_events(
            complaint, jurisdiction_id="city-oakland"
        )
        assert len(result) == 1
        assert result[0][1] == 30

    def test_no_matches_above_threshold_returns_empty(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        events = [
            _event(title="housing permit"),  # 2 kw = 20 < 25
            _event(title="only one permit"),  # 1 kw = 10 < 25
        ]
        self._write_events(tmp_path, "city-berkeley", events)
        complaint = _complaint(
            issue_type="housing", jurisdiction_id="city-berkeley"
        )
        result = match_issue_to_events(complaint)
        assert result == []

    def test_returned_tuple_contains_event_score_and_reason(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        self._write_events(
            tmp_path,
            "city-berkeley",
            [_event(title="housing zoning permit", project_type="environment")],
        )
        complaint = _complaint(
            issue_type="housing", jurisdiction_id="city-berkeley"
        )
        result = match_issue_to_events(complaint)
        assert len(result) == 1
        event_out, score, reason = result[0]
        assert event_out["title"] == "housing zoning permit"
        assert event_out["project_type"] == "environment"
        assert score == 30
        assert "3 keyword matches" in reason


# ---------------------------------------------------------------------------
# _load_jurisdiction_events
# ---------------------------------------------------------------------------

class TestLoadJurisdictionEvents:
    def test_missing_events_directory_returns_empty(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        # No data/events directory created.
        result = _load_jurisdiction_events("city-berkeley")
        assert result == []

    def test_no_matching_files_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        events_dir = tmp_path / "data" / "events"
        events_dir.mkdir(parents=True)
        # Only an unrelated jurisdiction file exists.
        (events_dir / "events_city-oakland_2026-04-01.json").write_text(
            json.dumps({"events": [{"title": "Oakland meeting"}]})
        )
        result = _load_jurisdiction_events("city-berkeley")
        assert result == []

    def test_loads_events_from_matching_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        events_dir = tmp_path / "data" / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "events_city-berkeley_2026-04-01.json").write_text(
            json.dumps(
                {"events": [{"title": "Meeting A"}, {"title": "Meeting B"}]}
            )
        )
        result = _load_jurisdiction_events("city-berkeley")
        assert len(result) == 2
        assert result[0]["title"] == "Meeting A"
        assert result[1]["title"] == "Meeting B"

    def test_loads_most_recent_file_when_multiple_exist(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        events_dir = tmp_path / "data" / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "events_city-berkeley_2026-03-01.json").write_text(
            json.dumps({"events": [{"title": "OLD"}]})
        )
        (events_dir / "events_city-berkeley_2026-04-01.json").write_text(
            json.dumps({"events": [{"title": "NEW"}]})
        )
        result = _load_jurisdiction_events("city-berkeley")
        # Reverse-sorted filenames → 2026-04-01 is chosen.
        assert len(result) == 1
        assert result[0]["title"] == "NEW"

    def test_malformed_json_returns_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        events_dir = tmp_path / "data" / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "events_city-berkeley_2026-04-01.json").write_text(
            "{ not valid json"
        )
        result = _load_jurisdiction_events("city-berkeley")
        assert result == []

    def test_file_without_events_key_returns_empty_list(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        events_dir = tmp_path / "data" / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "events_city-berkeley_2026-04-01.json").write_text(
            json.dumps({"unrelated_key": "value"})
        )
        result = _load_jurisdiction_events("city-berkeley")
        assert result == []

    def test_empty_events_list_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        events_dir = tmp_path / "data" / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "events_city-berkeley_2026-04-01.json").write_text(
            json.dumps({"events": []})
        )
        result = _load_jurisdiction_events("city-berkeley")
        assert result == []

    def test_jurisdiction_id_filter_is_exact(self, tmp_path, monkeypatch):
        # A file for "city-berkeley-heights" must not match "city-berkeley"
        # because the pattern is events_{id}_*.json with the underscore anchor.
        monkeypatch.chdir(tmp_path)
        events_dir = tmp_path / "data" / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "events_city-berkeley-heights_2026-04-01.json").write_text(
            json.dumps({"events": [{"title": "Heights meeting"}]})
        )
        result = _load_jurisdiction_events("city-berkeley")
        assert result == []


# ---------------------------------------------------------------------------
# get_match_statistics
# ---------------------------------------------------------------------------

class TestGetMatchStatistics:
    def test_empty_matches_returns_zero_stats(self):
        stats = get_match_statistics([])
        assert stats == {
            "total_matches": 0,
            "high_confidence": 0,
            "average_score": 0.0,
        }

    def test_empty_matches_omits_min_max_keys(self):
        stats = get_match_statistics([])
        assert "max_score" not in stats
        assert "min_score" not in stats

    def test_single_high_confidence_match(self):
        matches = [({"title": "A"}, 70.0, "reason")]
        stats = get_match_statistics(matches)
        assert stats["total_matches"] == 1
        assert stats["high_confidence"] == 1
        assert stats["average_score"] == 70.0
        assert stats["max_score"] == 70.0
        assert stats["min_score"] == 70.0

    def test_single_low_confidence_match(self):
        matches = [({"title": "A"}, 30.0, "reason")]
        stats = get_match_statistics(matches)
        assert stats["total_matches"] == 1
        assert stats["high_confidence"] == 0
        assert stats["average_score"] == 30.0
        assert stats["max_score"] == 30.0
        assert stats["min_score"] == 30.0

    def test_mixed_scores_compute_average_max_min(self):
        matches = [
            ({}, 40.0, "r"),
            ({}, 70.0, "r"),
            ({}, 30.0, "r"),
        ]
        stats = get_match_statistics(matches)
        assert stats["total_matches"] == 3
        assert stats["high_confidence"] == 1  # only 70 >= 60
        assert stats["average_score"] == pytest.approx(140.0 / 3, rel=1e-6)
        assert stats["max_score"] == 70.0
        assert stats["min_score"] == 30.0

    def test_high_confidence_threshold_is_inclusive(self):
        # A score of exactly HIGH_CONFIDENCE_THRESHOLD counts as high-confidence.
        matches = [({}, float(HIGH_CONFIDENCE_THRESHOLD), "r")]
        stats = get_match_statistics(matches)
        assert stats["high_confidence"] == 1

    def test_just_below_threshold_is_not_high_confidence(self):
        matches = [({}, float(HIGH_CONFIDENCE_THRESHOLD) - 0.1, "r")]
        stats = get_match_statistics(matches)
        assert stats["high_confidence"] == 0

    def test_all_high_confidence_counts_all(self):
        matches = [
            ({}, 60.0, "r"),
            ({}, 75.0, "r"),
            ({}, 100.0, "r"),
        ]
        stats = get_match_statistics(matches)
        assert stats["total_matches"] == 3
        assert stats["high_confidence"] == 3
        assert stats["max_score"] == 100.0
        assert stats["min_score"] == 60.0
