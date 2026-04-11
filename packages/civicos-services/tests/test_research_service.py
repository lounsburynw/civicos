"""
Tests for ResearchService — cache-first factual retrieval from JSON files.

The LLM provider is mocked (external dependency) but all file-search,
relevance-scoring, and context-building logic runs for real against a
temp data directory populated with fixture JSON files.

Run:
    pytest packages/civicos-services/tests/test_research_service.py -q --override-ini="addopts="
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.storage.research_service import ResearchService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_provider(response_text="Answer: test\n\nSources: test.json\n\nConfidence: high"):
    """Build a MagicMock LLM provider whose .complete() returns a fixed content."""
    provider = MagicMock()
    response = MagicMock()
    response.content = response_text
    provider.complete.return_value = response
    return provider


@pytest.fixture
def mock_provider():
    return _make_mock_provider()


@pytest.fixture
def data_dir(tmp_path_factory):
    """
    A fresh data directory for each test.

    Uses tmp_path_factory.mktemp() instead of the default tmp_path fixture to
    avoid the test-function name being embedded in the path — _search_federal_programs
    filters out any filepath containing "audit", so having "audit" in a test name
    (via tmp_path) would silently break federal-program tests.
    """
    return tmp_path_factory.mktemp("researchsvc")


@pytest.fixture
def service(data_dir, mock_provider):
    with patch(
        "civicos_services.storage.research_service.get_provider_for_task",
        return_value=mock_provider,
    ):
        return ResearchService(data_dir=str(data_dir))


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_stores_data_dir_exactly_as_passed(self, data_dir, mock_provider):
        with patch(
            "civicos_services.storage.research_service.get_provider_for_task",
            return_value=mock_provider,
        ):
            svc = ResearchService(data_dir=str(data_dir))
        assert svc.data_dir == str(data_dir)

    def test_default_data_dir_is_literal_data(self, mock_provider):
        with patch(
            "civicos_services.storage.research_service.get_provider_for_task",
            return_value=mock_provider,
        ):
            svc = ResearchService()
        assert svc.data_dir == "data"

    def test_provider_is_research_tier(self, data_dir):
        """Constructor selects the 'research' task type (Gemini Flash tier)."""
        mock_prov = _make_mock_provider()
        with patch(
            "civicos_services.storage.research_service.get_provider_for_task",
            return_value=mock_prov,
        ) as mock_get:
            svc = ResearchService(data_dir=str(data_dir))
        # Observable side effect: provider attribute is set to the selected provider.
        assert svc.provider is mock_prov
        # And it was fetched with the 'research' task type, not some other tier.
        mock_get.assert_called_once_with("research")


# ---------------------------------------------------------------------------
# _is_relevant
# ---------------------------------------------------------------------------


class TestIsRelevant:
    def test_matches_keyword_in_data_body(self, service):
        assert service._is_relevant(
            "What is the housing plan?",
            {"topic": "housing allocation"},
            "/data/foo.json",
        ) is True

    def test_matches_keyword_in_filepath_only(self, service):
        # Keyword 'housing' is in the filepath, not in the data.
        # (Note: _is_relevant doesn't strip punctuation, so "housing?" would
        # stay literal — use a bare token.)
        assert service._is_relevant(
            "tell me about housing",
            {"unrelated": "value"},
            "/data/overrides/housing-plan.json",
        ) is True

    def test_keywords_of_length_three_or_less_are_ignored(self, service):
        # 'the' (3) and 'cat' (3) are both filtered out. 'cat' exists in data
        # but must not trigger a match because it is not a keyword.
        assert service._is_relevant(
            "is the cat here",
            {"subject": "cat"},
            "/data/f.json",
        ) is False

    def test_keyword_of_length_four_is_honored(self, service):
        # 'park' is exactly 4 chars → len > 3 → should count as a keyword.
        assert service._is_relevant(
            "park status",
            {"name": "central park"},
            "/data/f.json",
        ) is True

    def test_match_is_case_insensitive_against_data(self, service):
        assert service._is_relevant(
            "HOUSING plan",
            {"subject": "Housing Allocation"},
            "/data/f.json",
        ) is True

    def test_returns_false_when_no_keyword_matches(self, service):
        assert service._is_relevant(
            "budget summary",
            {"topic": "water rates"},
            "/data/f.json",
        ) is False

    def test_returns_false_for_empty_question(self, service):
        # No tokens → no keywords → no matches.
        assert service._is_relevant("", {"data": "anything"}, "/data/f.json") is False

    def test_single_matching_keyword_suffices(self, service):
        # 'budget' should not match, but 'housing' should.
        assert service._is_relevant(
            "housing budget",
            {"topic": "housing only, nothing about money"},
            "/data/f.json",
        ) is True


# ---------------------------------------------------------------------------
# _search_jurisdiction_overrides
# ---------------------------------------------------------------------------


class TestSearchJurisdictionOverrides:
    def test_finds_matching_file_by_data_content(self, service, data_dir):
        target = data_dir / "jurisdiction_overrides" / "san-rafael.json"
        _write_json(target, {"allocation": "CDBG housing grant"})

        results = service._search_jurisdiction_overrides("housing grant")

        assert len(results) == 1
        assert results[0]["source"] == str(target)
        assert results[0]["data"] == {"allocation": "CDBG housing grant"}

    def test_skips_file_with_no_keyword_match(self, service, data_dir):
        _write_json(
            data_dir / "jurisdiction_overrides" / "other.json",
            {"irrelevant": "nothing to see"},
        )
        assert service._search_jurisdiction_overrides("housing allocation") == []

    def test_returns_empty_list_when_directory_missing(self, service):
        # No jurisdiction_overrides directory has been created.
        assert service._search_jurisdiction_overrides("anything") == []

    def test_skips_unparseable_json_and_keeps_valid_files(self, service, data_dir):
        bad = data_dir / "jurisdiction_overrides" / "broken.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("not valid json {")

        good = data_dir / "jurisdiction_overrides" / "good.json"
        _write_json(good, {"topic": "housing matters"})

        results = service._search_jurisdiction_overrides("housing")

        assert len(results) == 1
        assert results[0]["source"] == str(good)
        assert results[0]["data"] == {"topic": "housing matters"}

    def test_returns_all_matching_files(self, service, data_dir):
        _write_json(
            data_dir / "jurisdiction_overrides" / "a.json",
            {"topic": "housing first"},
        )
        _write_json(
            data_dir / "jurisdiction_overrides" / "b.json",
            {"topic": "housing second"},
        )
        results = service._search_jurisdiction_overrides("housing")
        sources = sorted(r["source"] for r in results)
        assert len(results) == 2
        assert sources[0].endswith("a.json")
        assert sources[1].endswith("b.json")


# ---------------------------------------------------------------------------
# _search_legislative_context
# ---------------------------------------------------------------------------


class TestSearchLegislativeContext:
    def test_finds_california_prefixed_file(self, service, data_dir):
        target = data_dir / "legislative_context" / "california_ab_101.json"
        _write_json(target, {"title": "Housing density", "status": "passed"})

        results = service._search_legislative_context("housing density")

        assert len(results) == 1
        assert results[0]["source"] == str(target)
        assert results[0]["data"]["title"] == "Housing density"
        assert results[0]["data"]["status"] == "passed"

    def test_ignores_files_without_california_prefix(self, service, data_dir):
        # Glob pattern is california_*.json — a federal_* file must be skipped
        # even if its contents would otherwise match the question.
        _write_json(
            data_dir / "legislative_context" / "federal_hr_1.json",
            {"title": "housing relevant content"},
        )
        assert service._search_legislative_context("housing") == []

    def test_returns_empty_when_no_file_is_relevant(self, service, data_dir):
        _write_json(
            data_dir / "legislative_context" / "california_ab_1.json",
            {"title": "water rights"},
        )
        assert service._search_legislative_context("transportation policy") == []


# ---------------------------------------------------------------------------
# _search_federal_programs
# ---------------------------------------------------------------------------


class TestSearchFederalPrograms:
    def test_skips_files_with_audit_substring_in_name(self, service, data_dir):
        _write_json(
            data_dir / "federal_programs" / "cdbg_audit.json",
            {"funding": "housing programs"},
        )
        assert service._search_federal_programs("housing programs") == []

    def test_returns_non_audit_files(self, service, data_dir):
        target = data_dir / "federal_programs" / "cdbg.json"
        _write_json(target, {"funding": "housing programs"})

        results = service._search_federal_programs("housing programs")

        assert len(results) == 1
        assert results[0]["source"] == str(target)
        assert results[0]["data"] == {"funding": "housing programs"}

    def test_mixes_audit_and_normal_files(self, service, data_dir):
        _write_json(
            data_dir / "federal_programs" / "section8.json",
            {"program": "housing choice"},
        )
        _write_json(
            data_dir / "federal_programs" / "section8_audit.json",
            {"program": "housing choice"},
        )
        results = service._search_federal_programs("housing choice")
        assert len(results) == 1
        assert "audit" not in results[0]["source"]
        assert results[0]["source"].endswith("section8.json")


# ---------------------------------------------------------------------------
# _search_events
# ---------------------------------------------------------------------------


class TestSearchEvents:
    def test_limits_events_per_file_to_first_three(self, service, data_dir):
        events = [
            {"title": "housing meeting 1"},
            {"title": "housing meeting 2"},
            {"title": "housing meeting 3"},
            {"title": "housing meeting 4"},
            {"title": "housing meeting 5"},
        ]
        _write_json(data_dir / "events" / "events_2025.json", events)

        results = service._search_events("housing")

        assert len(results) == 1
        assert len(results[0]["data"]) == 3
        assert results[0]["data"][0]["title"] == "housing meeting 1"
        assert results[0]["data"][1]["title"] == "housing meeting 2"
        assert results[0]["data"][2]["title"] == "housing meeting 3"

    def test_limits_result_files_to_three(self, service, data_dir):
        for i in range(5):
            _write_json(
                data_dir / "events" / f"events_{i}.json",
                [{"title": "housing related"}],
            )
        results = service._search_events("housing")
        assert len(results) == 3

    def test_preserves_non_list_data_unchanged(self, service, data_dir):
        _write_json(
            data_dir / "events" / "events_single.json",
            {"title": "housing gala"},
        )
        results = service._search_events("housing")
        assert len(results) == 1
        assert results[0]["data"] == {"title": "housing gala"}

    def test_ignores_non_matching_event_files(self, service, data_dir):
        _write_json(
            data_dir / "events" / "events_budget.json",
            [{"title": "water rates hearing"}],
        )
        assert service._search_events("housing plan") == []

    def test_glob_pattern_requires_events_prefix(self, service, data_dir):
        # File without the events_ prefix must not be picked up.
        _write_json(
            data_dir / "events" / "not_prefixed.json",
            [{"title": "housing related"}],
        )
        assert service._search_events("housing") == []


# ---------------------------------------------------------------------------
# _search_data — scope routing
# ---------------------------------------------------------------------------


class TestSearchDataScopes:
    def _seed_all_corpora(self, data_dir):
        _write_json(
            data_dir / "jurisdiction_overrides" / "x.json",
            {"topic": "housing"},
        )
        _write_json(
            data_dir / "legislative_context" / "california_1.json",
            {"title": "housing bill"},
        )
        _write_json(
            data_dir / "federal_programs" / "cdbg.json",
            {"program": "housing fund"},
        )
        _write_json(
            data_dir / "events" / "events_1.json",
            [{"title": "housing hearing"}],
        )

    def test_all_scope_returns_every_category(self, service, data_dir):
        self._seed_all_corpora(data_dir)
        data = service._search_data("housing", "all")
        assert set(data.keys()) == {"allocations", "bills", "programs", "events"}
        assert len(data["allocations"]) == 1
        assert len(data["bills"]) == 1
        assert len(data["programs"]) == 1
        assert len(data["events"]) == 1

    def test_allocations_scope_only_searches_overrides(self, service, data_dir):
        self._seed_all_corpora(data_dir)
        data = service._search_data("housing", "allocations")
        assert list(data.keys()) == ["allocations"]
        assert len(data["allocations"]) == 1

    def test_legislative_scope_returns_bills_and_programs_only(self, service, data_dir):
        self._seed_all_corpora(data_dir)
        data = service._search_data("housing", "legislative")
        assert set(data.keys()) == {"bills", "programs"}
        assert len(data["bills"]) == 1
        assert len(data["programs"]) == 1

    def test_events_scope_only_searches_events(self, service, data_dir):
        self._seed_all_corpora(data_dir)
        data = service._search_data("housing", "events")
        assert list(data.keys()) == ["events"]
        assert len(data["events"]) == 1

    def test_unknown_scope_returns_empty_dict(self, service, data_dir):
        self._seed_all_corpora(data_dir)
        data = service._search_data("housing", "nonsense")
        assert data == {}


# ---------------------------------------------------------------------------
# _build_context
# ---------------------------------------------------------------------------


class TestBuildContext:
    def test_returns_empty_string_for_empty_data(self, service):
        assert service._build_context({}) == ""

    def test_skips_categories_with_empty_item_lists(self, service):
        assert service._build_context({"bills": [], "events": []}) == ""

    def test_includes_category_title_and_source(self, service):
        data = {
            "bills": [{"source": "ca.json", "data": {"title": "AB 101"}}],
        }
        ctx = service._build_context(data)
        assert "## Bills" in ctx
        assert "Source: ca.json" in ctx
        assert "AB 101" in ctx

    def test_limits_items_per_category_to_first_three(self, service):
        data = {
            "bills": [
                {"source": f"f{i}.json", "data": {"n": i}} for i in range(5)
            ]
        }
        ctx = service._build_context(data)
        # First three survive, the rest are dropped.
        assert "f0.json" in ctx
        assert "f1.json" in ctx
        assert "f2.json" in ctx
        assert "f3.json" not in ctx
        assert "f4.json" not in ctx

    def test_truncates_serialized_data_longer_than_2000_chars(self, service):
        big_value = "X" * 3000  # Serialized JSON will exceed 2000 chars.
        data = {
            "bills": [
                {"source": "big.json", "data": {"text": big_value}},
            ]
        }
        ctx = service._build_context(data)
        assert "... (truncated)" in ctx
        # Fewer X's made it into the context than were in the original payload.
        assert ctx.count("X") < 3000
        # But some did make it through.
        assert ctx.count("X") >= 1000

    def test_does_not_truncate_short_data(self, service):
        data = {
            "bills": [{"source": "small.json", "data": {"x": "tiny"}}],
        }
        ctx = service._build_context(data)
        assert "... (truncated)" not in ctx
        assert "tiny" in ctx


# ---------------------------------------------------------------------------
# _extract_sources
# ---------------------------------------------------------------------------


class TestExtractSources:
    def test_returns_empty_list_for_empty_data(self, service):
        assert service._extract_sources({}) == []

    def test_deduplicates_identical_sources(self, service):
        data = {
            "bills": [
                {"source": "a.json", "data": {}},
                {"source": "a.json", "data": {}},
            ],
        }
        assert service._extract_sources(data) == ["a.json"]

    def test_flattens_across_categories(self, service):
        data = {
            "bills": [{"source": "b.json", "data": {}}],
            "events": [{"source": "e.json", "data": {}}],
        }
        sources = service._extract_sources(data)
        assert sorted(sources) == ["b.json", "e.json"]

    def test_preserves_distinct_cross_category_sources_even_if_similar(self, service):
        data = {
            "bills": [
                {"source": "p1.json", "data": {}},
                {"source": "p2.json", "data": {}},
            ],
            "events": [
                {"source": "p1.json", "data": {}},  # duplicate of bills entry
                {"source": "p3.json", "data": {}},
            ],
        }
        sources = service._extract_sources(data)
        assert sorted(sources) == ["p1.json", "p2.json", "p3.json"]


# ---------------------------------------------------------------------------
# _format_answer
# ---------------------------------------------------------------------------


class TestFormatAnswer:
    def test_returns_none_confidence_when_no_data(self, service, mock_provider):
        result = service._format_answer("anything", {})
        assert result["text"] == "I don't have that information in the cached data."
        assert result["sources"] == []
        assert result["confidence"] == "none"
        # Empty-context shortcut must not call the LLM.
        mock_provider.complete.assert_not_called()

    def test_returns_none_confidence_when_all_categories_empty(self, service, mock_provider):
        result = service._format_answer("q", {"bills": [], "events": []})
        assert result["confidence"] == "none"
        assert result["sources"] == []
        assert result["text"] == "I don't have that information in the cached data."
        mock_provider.complete.assert_not_called()

    def test_parses_high_confidence_from_response(self, service, mock_provider):
        mock_provider.complete.return_value.content = "Answer: x\nConfidence: high"
        data = {"bills": [{"source": "ca.json", "data": {"title": "housing bill"}}]}
        result = service._format_answer("housing", data)
        assert result["confidence"] == "high"

    def test_parses_low_confidence_from_response(self, service, mock_provider):
        mock_provider.complete.return_value.content = "Answer: x\nConfidence: low"
        data = {"bills": [{"source": "ca.json", "data": {"title": "housing bill"}}]}
        result = service._format_answer("housing", data)
        assert result["confidence"] == "low"

    def test_defaults_to_medium_when_confidence_keyword_absent(self, service, mock_provider):
        mock_provider.complete.return_value.content = "Some bare answer text"
        data = {"bills": [{"source": "ca.json", "data": {"title": "housing bill"}}]}
        result = service._format_answer("housing", data)
        assert result["confidence"] == "medium"

    def test_confidence_parsing_is_case_insensitive(self, service, mock_provider):
        mock_provider.complete.return_value.content = "ANSWER\nCONFIDENCE: HIGH"
        data = {"bills": [{"source": "ca.json", "data": {"title": "housing bill"}}]}
        result = service._format_answer("housing", data)
        assert result["confidence"] == "high"

    def test_high_takes_precedence_over_low_when_both_mentioned(self, service, mock_provider):
        # Code checks 'high' first, then 'low' in elif — so if both appear,
        # 'high' wins. Pin this behavior.
        mock_provider.complete.return_value.content = (
            "Analysis: confidence: high for topic A, confidence: low for topic B"
        )
        data = {"bills": [{"source": "ca.json", "data": {"title": "housing bill"}}]}
        result = service._format_answer("housing", data)
        assert result["confidence"] == "high"

    def test_returns_provider_content_verbatim_as_text(self, service, mock_provider):
        mock_provider.complete.return_value.content = "Custom answer content"
        data = {"bills": [{"source": "ca.json", "data": {"title": "housing bill"}}]}
        result = service._format_answer("housing", data)
        assert result["text"] == "Custom answer content"

    def test_sources_are_deduped_union_of_data(self, service, mock_provider):
        data = {
            "bills": [{"source": "ca.json", "data": {"title": "housing bill"}}],
            "events": [{"source": "ev.json", "data": {"title": "housing meeting"}}],
        }
        result = service._format_answer("housing", data)
        assert sorted(result["sources"]) == ["ca.json", "ev.json"]

    def test_provider_prompt_includes_question_and_context(self, service, mock_provider):
        data = {
            "bills": [{"source": "ca.json", "data": {"title": "AB 101 Housing Bond"}}]
        }
        service._format_answer("housing bond status", data)

        messages = mock_provider.complete.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "civic research assistant" in messages[0]["content"].lower()

        user_content = messages[1]["content"]
        assert "housing bond status" in user_content
        assert "AB 101 Housing Bond" in user_content
        assert "ca.json" in user_content


# ---------------------------------------------------------------------------
# query — top-level integration (real file I/O + mocked LLM)
# ---------------------------------------------------------------------------


class TestQuery:
    def test_includes_search_scope_in_response(self, service, mock_provider):
        mock_provider.complete.return_value.content = "Answer\nConfidence: high"
        result = service.query("housing", "all")
        assert result["search_scope"] == "all"

    def test_no_data_returns_none_confidence_without_llm_call(
        self, service, mock_provider
    ):
        result = service.query("nothing here", "all")
        assert result["confidence"] == "none"
        assert result["sources"] == []
        assert result["answer"] == "I don't have that information in the cached data."
        # LLM must not be invoked when there is nothing to summarize.
        mock_provider.complete.assert_not_called()

    def test_returns_llm_content_and_sources_on_match(
        self, service, data_dir, mock_provider
    ):
        target = data_dir / "legislative_context" / "california_ab_1.json"
        _write_json(target, {"title": "AB 1 - housing bond", "status": "passed"})
        mock_provider.complete.return_value.content = (
            "Answer: AB 1 passed\nConfidence: high"
        )

        result = service.query("housing bond", "legislative")

        assert result["answer"] == "Answer: AB 1 passed\nConfidence: high"
        assert result["confidence"] == "high"
        assert result["search_scope"] == "legislative"
        assert result["sources"] == [str(target)]

    def test_allocations_scope_does_not_see_legislative_files(
        self, service, data_dir, mock_provider
    ):
        # Seed a legislative file that would otherwise match the question.
        _write_json(
            data_dir / "legislative_context" / "california_ab_1.json",
            {"title": "housing bond"},
        )
        # But no jurisdiction_overrides files exist.
        result = service.query("housing bond", "allocations")
        assert result["confidence"] == "none"
        assert result["sources"] == []
        assert result["answer"] == "I don't have that information in the cached data."
        mock_provider.complete.assert_not_called()

    def test_default_scope_is_all(self, service, mock_provider):
        mock_provider.complete.return_value.content = "x"
        result = service.query("housing")
        assert result["search_scope"] == "all"

    def test_four_keys_returned_always(self, service, data_dir, mock_provider):
        _write_json(
            data_dir / "events" / "events_1.json",
            [{"title": "housing hearing"}],
        )
        mock_provider.complete.return_value.content = "Answer: ok\nConfidence: medium"
        result = service.query("housing", "events")
        assert set(result.keys()) == {"answer", "sources", "confidence", "search_scope"}
        assert result["answer"] == "Answer: ok\nConfidence: medium"
        assert result["confidence"] == "medium"
        assert result["search_scope"] == "events"
