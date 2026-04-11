"""
Tests for docling_retrospective_analyzer.py — Docling-backed high-stakes decision extraction.

Covers:
- get_converter (module-level singleton factory)
- _split_markdown_into_items (pure regex logic: lettered, numbered, fallback)
- _extract_from_item (LLM-dependent extraction with mocked LLM provider)
- extract_high_stakes_decisions (top-level orchestration through docling converter)

Strategy: pure regex logic is tested directly. I/O (docling converter, LLM provider)
is mocked at its import location inside the module. The docling library itself is
stubbed at sys.modules before import because it is not a test-time dependency.

To run:
    pytest packages/civicos-services/tests/test_docling_retrospective_analyzer.py -q --override-ini="addopts="
"""

import json
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# docling is a heavy optional runtime dependency. Tests mock the converter
# surface, so stub the module graph here if it is not installed in the test
# environment.
if "docling" not in sys.modules:
    _docling_stub = ModuleType("docling")
    _dc_stub = ModuleType("docling.document_converter")

    class _StubDocumentConverter:
        def __init__(self) -> None:
            pass

        def convert(self, *_args, **_kwargs):  # pragma: no cover - overridden in tests
            raise RuntimeError("stub DocumentConverter.convert must be patched")

    _dc_stub.DocumentConverter = _StubDocumentConverter
    _docling_stub.document_converter = _dc_stub
    sys.modules["docling"] = _docling_stub
    sys.modules["docling.document_converter"] = _dc_stub


from civicos_services.processing import docling_retrospective_analyzer as dra  # noqa: E402
from civicos_services.processing.docling_retrospective_analyzer import (  # noqa: E402
    DoclingRetrospectiveAnalyzer,
)
from civicos_services.processing.retrospective_analyzer import (  # noqa: E402
    HighStakesDecision,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


LLM_PATCH_TARGET = (
    "civicos_services.processing.docling_retrospective_analyzer.get_model_for_task"
)


def _llm_returning(payload: dict) -> MagicMock:
    """Build a mock LLM whose .chat() returns a JSON-encoded payload string."""
    llm = MagicMock()
    llm.chat.return_value = json.dumps(payload)
    return llm


def _docling_result_with_markdown(markdown: str) -> MagicMock:
    """Mimic docling's convert() return value: result.document.export_to_markdown()."""
    result = MagicMock()
    result.document.export_to_markdown.return_value = markdown
    return result


@pytest.fixture
def analyzer(monkeypatch):
    """
    A DoclingRetrospectiveAnalyzer whose underlying converter is a MagicMock.

    We install the mock onto the module's singleton slot so __init__ picks it
    up via get_converter() without constructing a real DocumentConverter.
    """
    mock_converter = MagicMock()
    monkeypatch.setattr(dra, "_converter", mock_converter)
    return DoclingRetrospectiveAnalyzer()


# ---------------------------------------------------------------------------
# get_converter — singleton caching
# ---------------------------------------------------------------------------


class TestGetConverter:
    def test_returns_same_instance_on_repeat_calls(self, monkeypatch):
        # Force a fresh lazy init.
        monkeypatch.setattr(dra, "_converter", None)
        first = dra.get_converter()
        second = dra.get_converter()
        assert first is second

    def test_cached_instance_is_reused_across_analyzer_constructions(self, monkeypatch):
        sentinel = MagicMock(name="cached-converter")
        monkeypatch.setattr(dra, "_converter", sentinel)
        a = DoclingRetrospectiveAnalyzer()
        b = DoclingRetrospectiveAnalyzer()
        assert a.converter is sentinel
        assert b.converter is sentinel
        assert a.converter is b.converter

    def test_lazy_init_constructs_converter_only_once(self, monkeypatch):
        monkeypatch.setattr(dra, "_converter", None)
        construct_calls = {"n": 0}

        class OneShot:
            def __init__(self):
                construct_calls["n"] += 1

        monkeypatch.setattr(dra, "DocumentConverter", OneShot)
        first = dra.get_converter()
        second = dra.get_converter()
        assert construct_calls["n"] == 1
        assert first is second


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_init_attaches_module_converter(self, monkeypatch):
        marker = MagicMock(name="my-converter")
        monkeypatch.setattr(dra, "_converter", marker)
        a = DoclingRetrospectiveAnalyzer()
        assert a.converter is marker

    def test_each_instance_gets_its_own_session(self, monkeypatch):
        monkeypatch.setattr(dra, "_converter", MagicMock())
        a = DoclingRetrospectiveAnalyzer()
        b = DoclingRetrospectiveAnalyzer()
        assert a.session is not b.session
        # Session must expose the HTTP surface downstream callers could reach for.
        assert callable(getattr(a.session, "get", None))


# ---------------------------------------------------------------------------
# _split_markdown_into_items — pure regex logic, no mocks needed
# ---------------------------------------------------------------------------


class TestSplitMarkdownIntoItems:
    def test_empty_string_returns_single_full_item(self, analyzer):
        result = analyzer._split_markdown_into_items("")
        assert result == [("full", "")]

    def test_plain_text_with_no_items_returns_single_full_item(self, analyzer):
        md = "Just regular body text with no agenda structure"
        result = analyzer._split_markdown_into_items(md)
        assert result == [("full", md)]

    def test_lettered_items_are_split_into_separate_entries(self, analyzer):
        md = "Header line\n- a. First item\n- b. Second item\n- c. Third item"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 3
        assert [ref for ref, _ in result] == ["a", "b", "c"]

    def test_lettered_item_content_is_isolated_per_item(self, analyzer):
        md = "Header\n- a. Alpha content\n- b. Beta content\n- c. Gamma content"
        result = analyzer._split_markdown_into_items(md)
        assert "Alpha" in result[0][1]
        assert "Beta" not in result[0][1]
        assert "Gamma" not in result[0][1]
        assert "Beta" in result[1][1]
        assert "Gamma" not in result[1][1]
        assert "Gamma" in result[2][1]

    def test_last_lettered_item_extends_to_end_of_document(self, analyzer):
        md = "Header\n- a. Alpha\n- b. Final item with tail trailing"
        result = analyzer._split_markdown_into_items(md)
        assert result[-1][1].endswith("trailing")

    def test_numbered_items_used_as_fallback_when_no_lettered(self, analyzer):
        md = "\n1. First Item Title\n2. Second Item Title\n3. Third Item Title"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 3
        assert [ref for ref, _ in result] == ["1", "2", "3"]

    def test_numbered_pattern_requires_capital_letter_after_period(self, analyzer):
        # "1. lowercase" is skipped; "2. Also" matches because 'A' is capital.
        md = "\n1. lowercase skip\n2. Also matches"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 1
        assert result[0][0] == "2"
        assert "Also matches" in result[0][1]

    def test_lettered_pattern_takes_priority_over_numbered(self, analyzer):
        md = "\n- a. Letter item\n1. Number Item"
        result = analyzer._split_markdown_into_items(md)
        # Only lettered items come back; numbered text becomes part of item a.
        assert len(result) == 1
        assert result[0][0] == "a"
        assert "Number Item" in result[0][1]

    def test_lettered_match_is_case_insensitive(self, analyzer):
        md = "\n- A. Capitalised letter item body"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 1
        assert result[0][0] == "A"

    def test_single_lettered_item_drops_preamble(self, analyzer):
        md = "Preamble text\n- a. Only item body"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 1
        # Start offset is at '\n- a.' so the preamble is not included.
        assert result[0][1].startswith("\n- a.")
        assert "Preamble" not in result[0][1]
        assert "Only item body" in result[0][1]

    def test_two_numbered_items_split_cleanly(self, analyzer):
        md = "\n1. First Title body one\n2. Second Title body two"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 2
        assert result[0][0] == "1"
        assert result[1][0] == "2"
        assert "body one" in result[0][1]
        assert "body two" in result[1][1]
        assert "body two" not in result[0][1]


# ---------------------------------------------------------------------------
# _extract_from_item — LLM mocked, real JSON parsing and HighStakesDecision build
# ---------------------------------------------------------------------------


class TestExtractFromItemFilters:
    def test_returns_empty_when_llm_reports_not_high_stakes(self, analyzer):
        llm = _llm_returning({"is_high_stakes": False})
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert result == []

    def test_returns_empty_when_stakes_score_below_min_threshold(self, analyzer):
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 5,
            "title": "Low stakes",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert result == []

    def test_returns_empty_when_llm_raises(self, analyzer):
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("upstream API down")
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert result == []

    def test_returns_empty_when_llm_returns_invalid_json(self, analyzer):
        llm = MagicMock()
        llm.chat.return_value = "not valid json at all"
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert result == []

    def test_returns_empty_when_stakes_score_missing_and_min_nonzero(self, analyzer):
        # Missing stakes_score defaults to 0 in the filter check -> below any positive min.
        llm = _llm_returning({"is_high_stakes": True, "title": "No Score"})
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert result == []

    def test_passes_at_exact_min_stakes_threshold(self, analyzer):
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 6,  # exactly min_stakes_score
            "title": "Threshold item",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert len(result) == 1
        assert result[0].stakes_score == 6
        assert result[0].title == "Threshold item"

    def test_stakes_score_one_below_threshold_is_filtered(self, analyzer):
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 6,
            "title": "Just under",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 7, "http://x.pdf"
            )
        assert result == []


class TestExtractFromItemBuild:
    def test_populates_all_decision_fields_from_llm_response(self, analyzer):
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 8,
            "title": "Affordable Housing Appropriation",
            "description": "Funding for 50 units of affordable housing",
            "decision_type": "development",
            "budget_amount": 5_000_000,
            "budget_description": "construction contract award",
            "affected_population_estimate": 2000,
            "geographic_scope": "district",
            "project_types": ["housing", "development"],
            "keywords_for_matching": ["affordable", "housing", "50 units"],
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "5.a",
                "agenda item text",
                "2025-10-06",
                "city_council",
                100000,
                6,
                "http://agenda.pdf",
            )

        assert len(result) == 1
        d = result[0]
        assert isinstance(d, HighStakesDecision)
        assert d.item_ref == "5.a"
        assert d.title == "Affordable Housing Appropriation"
        assert d.description == "Funding for 50 units of affordable housing"
        assert d.meeting_date == "2025-10-06"
        assert d.meeting_type == "city_council"
        assert d.is_high_stakes is True
        assert d.stakes_score == 8
        assert d.decision_type == "development"
        assert d.budget_amount == 5_000_000
        assert d.budget_description == "construction contract award"
        assert d.affected_population_estimate == 2000
        assert d.geographic_scope == "district"
        assert d.project_types == ["housing", "development"]
        assert d.keywords_for_matching == ["affordable", "housing", "50 units"]
        assert d.agenda_url == "http://agenda.pdf"
        assert d.staff_report_url is None
        assert d.project_size_units is None
        assert d.project_location is None
        assert d.participation_mechanisms == []

    def test_uses_documented_defaults_when_optional_fields_missing(self, analyzer):
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 7,
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "b",
                "body",
                "2025-11-01",
                "planning_commission",
                100000,
                6,
                "http://x.pdf",
            )
        assert len(result) == 1
        d = result[0]
        assert d.title == "Unknown"
        assert d.description == ""
        assert d.decision_type == "policy"
        assert d.budget_amount is None
        assert d.budget_description == ""
        assert d.affected_population_estimate is None
        assert d.geographic_scope == "unknown"
        assert d.project_types == []
        assert d.keywords_for_matching == []
        assert d.meeting_type == "planning_commission"

    def test_stakes_score_defaults_to_six_when_missing_and_min_is_zero(self, analyzer):
        # With min_stakes_score=0, a missing stakes_score survives the filter.
        # The build step then defaults to 6 via result.get("stakes_score", 6).
        llm = _llm_returning({
            "is_high_stakes": True,
            "title": "No score provided",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 0, "http://x.pdf"
            )
        assert len(result) == 1
        assert result[0].stakes_score == 6

    def test_budget_amount_of_zero_is_preserved_distinct_from_none(self, analyzer):
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 7,
            "budget_amount": 0,
            "title": "Zero cost item",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert len(result) == 1
        assert result[0].budget_amount == 0

    def test_explicit_none_budget_amount_preserved_as_none(self, analyzer):
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 7,
            "budget_amount": None,
            "title": "No budget",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert len(result) == 1
        assert result[0].budget_amount is None


class TestExtractFromItemPrompt:
    def test_prompt_embeds_item_ref_text_and_budget_threshold(self, analyzer):
        llm = _llm_returning({"is_high_stakes": False})
        with patch(LLM_PATCH_TARGET, return_value=llm):
            analyzer._extract_from_item(
                "5.b",
                "Unique Marker ABC in item body",
                "2025-10-06",
                "city_council",
                250000,
                6,
                "http://x.pdf",
            )
        kwargs = llm.chat.call_args.kwargs
        messages = kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        prompt = messages[0]["content"]
        assert "AGENDA ITEM 5.b:" in prompt
        assert "Unique Marker ABC in item body" in prompt
        # min_budget rendered with thousands separator
        assert "$250,000" in prompt
        assert kwargs["response_format"] == "json_object"

    def test_prompt_truncates_item_text_to_4000_chars(self, analyzer):
        llm = _llm_returning({"is_high_stakes": False})
        long_text = "X" * 10000
        with patch(LLM_PATCH_TARGET, return_value=llm):
            analyzer._extract_from_item(
                "a", long_text, "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        prompt = llm.chat.call_args.kwargs["messages"][0]["content"]
        # The slotted item text is at most 4000 X's, not 10000.
        assert "X" * 4000 in prompt
        assert "X" * 4001 not in prompt

    def test_uses_structured_extraction_model_task(self, analyzer):
        llm = _llm_returning({"is_high_stakes": False})
        with patch(LLM_PATCH_TARGET, return_value=llm) as mock_get_model:
            result = analyzer._extract_from_item(
                "a", "body", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert mock_get_model.call_args.args == ("structured_extraction",)
        assert mock_get_model.call_count == 1
        assert result == []
        assert llm.chat.call_count == 1


# ---------------------------------------------------------------------------
# extract_high_stakes_decisions — orchestration through docling
# ---------------------------------------------------------------------------


class TestExtractHighStakesDecisions:
    def test_converter_error_returns_empty_list(self, analyzer):
        analyzer.converter.convert.side_effect = RuntimeError("docling failed")
        result = analyzer.extract_high_stakes_decisions(
            pdf_url="https://example.gov/agenda.pdf",
            meeting_date="2025-10-06",
        )
        assert result == []

    def test_export_error_returns_empty_list(self, analyzer):
        bad_result = MagicMock()
        bad_result.document.export_to_markdown.side_effect = ValueError("no doc")
        analyzer.converter.convert.return_value = bad_result
        result = analyzer.extract_high_stakes_decisions(
            pdf_url="https://example.gov/agenda.pdf",
            meeting_date="2025-10-06",
        )
        assert result == []

    def test_pdf_url_is_passed_directly_to_docling_converter(self, analyzer):
        analyzer.converter.convert.return_value = _docling_result_with_markdown("short")
        result = analyzer.extract_high_stakes_decisions(
            pdf_url="https://example.gov/agenda.pdf",
            meeting_date="2025-10-06",
        )
        assert analyzer.converter.convert.call_count == 1
        assert analyzer.converter.convert.call_args.args == (
            "https://example.gov/agenda.pdf",
        )
        # Short markdown yields no extractable items, so the orchestrator
        # should return an empty list — not propagate docling output raw.
        assert result == []

    def test_short_markdown_yields_no_items_eligible_for_extraction(self, analyzer):
        analyzer.converter.convert.return_value = _docling_result_with_markdown(
            "tiny body"
        )
        # With no item markers the fallback is [("full", "tiny body")].
        # The stripped length is < 100 chars, so no LLM call is made.
        with patch(LLM_PATCH_TARGET) as mock_get_model:
            result = analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/agenda.pdf",
                meeting_date="2025-10-06",
            )
        assert result == []
        assert mock_get_model.call_count == 0

    def test_tiny_split_items_are_skipped_before_llm_call(self, analyzer):
        # Each item body is well under 100 chars after strip.
        md = "Header\n- a. tiny one\n- b. also small"
        analyzer.converter.convert.return_value = _docling_result_with_markdown(md)
        llm = _llm_returning({"is_high_stakes": True, "stakes_score": 9, "title": "X"})
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/agenda.pdf",
                meeting_date="2025-10-06",
            )
        assert result == []
        assert llm.chat.call_count == 0

    def test_mix_of_high_and_low_stakes_items_returns_only_high(self, analyzer):
        filler = " meaningful body content " * 10  # > 100 chars per item after strip
        md = (
            f"Header\n- a. Alpha{filler}"
            f"\n- b. Beta{filler}"
            f"\n- c. Gamma{filler}"
        )
        analyzer.converter.convert.return_value = _docling_result_with_markdown(md)
        llm = MagicMock()
        llm.chat.side_effect = [
            json.dumps({
                "is_high_stakes": True,
                "stakes_score": 8,
                "title": "Alpha Decision",
                "budget_amount": 1_000_000,
            }),
            json.dumps({"is_high_stakes": False}),
            json.dumps({
                "is_high_stakes": True,
                "stakes_score": 9,
                "title": "Gamma Decision",
                "budget_amount": 2_500_000,
            }),
        ]
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/agenda.pdf",
                meeting_date="2025-11-15",
                meeting_type="planning_commission",
            )
        assert llm.chat.call_count == 3
        assert len(result) == 2
        assert result[0].title == "Alpha Decision"
        assert result[0].item_ref == "a"
        assert result[0].budget_amount == 1_000_000
        assert result[0].meeting_date == "2025-11-15"
        assert result[0].meeting_type == "planning_commission"
        assert result[1].title == "Gamma Decision"
        assert result[1].item_ref == "c"
        assert result[1].budget_amount == 2_500_000

    def test_default_meeting_type_is_city_council(self, analyzer):
        filler = " body content " * 15
        md = f"\n- a. Big item{filler}"
        analyzer.converter.convert.return_value = _docling_result_with_markdown(md)
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 7,
            "title": "Some item",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/agenda.pdf",
                meeting_date="2025-10-06",
                # meeting_type omitted
            )
        assert len(result) == 1
        assert result[0].meeting_type == "city_council"

    def test_default_min_budget_is_100000(self, analyzer):
        filler = " body content " * 15
        md = f"\n- a. Item{filler}"
        analyzer.converter.convert.return_value = _docling_result_with_markdown(md)
        llm = _llm_returning({"is_high_stakes": False})
        with patch(LLM_PATCH_TARGET, return_value=llm):
            analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/agenda.pdf",
                meeting_date="2025-10-06",
                # min_budget omitted
            )
        prompt = llm.chat.call_args.kwargs["messages"][0]["content"]
        assert "$100,000" in prompt

    def test_default_min_stakes_score_is_six(self, analyzer):
        filler = " body content " * 15
        md = f"\n- a. Item{filler}"
        analyzer.converter.convert.return_value = _docling_result_with_markdown(md)
        # score=5 is below the documented default min of 6 -> should be filtered.
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 5,
            "title": "Five",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/agenda.pdf",
                meeting_date="2025-10-06",
            )
        assert result == []

    def test_min_budget_and_min_stakes_score_overrides_honored(self, analyzer):
        filler = " body content " * 15
        md = f"\n- a. Item{filler}"
        analyzer.converter.convert.return_value = _docling_result_with_markdown(md)
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 4,  # would fail default min=6, passes custom min=3
            "title": "Custom threshold",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/agenda.pdf",
                meeting_date="2025-10-06",
                min_budget=50000,
                min_stakes_score=3,
            )
        assert len(result) == 1
        assert result[0].stakes_score == 4
        prompt = llm.chat.call_args.kwargs["messages"][0]["content"]
        assert "$50,000" in prompt

    def test_original_pdf_url_preserved_as_agenda_url_in_decision(self, analyzer):
        filler = " body content " * 15
        md = f"\n- a. Item{filler}"
        analyzer.converter.convert.return_value = _docling_result_with_markdown(md)
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 8,
            "title": "URL carries through",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/special-agenda.pdf",
                meeting_date="2025-10-06",
            )
        assert len(result) == 1
        assert result[0].agenda_url == "https://example.gov/special-agenda.pdf"

    def test_per_item_llm_failure_does_not_abort_remaining_items(self, analyzer):
        filler = " meaningful body content " * 10
        md = f"Header\n- a. Alpha{filler}\n- b. Beta{filler}"
        analyzer.converter.convert.return_value = _docling_result_with_markdown(md)
        llm = MagicMock()
        llm.chat.side_effect = [
            RuntimeError("LLM flakey"),
            json.dumps({
                "is_high_stakes": True,
                "stakes_score": 8,
                "title": "Beta survives",
            }),
        ]
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer.extract_high_stakes_decisions(
                pdf_url="https://example.gov/agenda.pdf",
                meeting_date="2025-10-06",
            )
        assert llm.chat.call_count == 2
        assert len(result) == 1
        assert result[0].title == "Beta survives"
        assert result[0].item_ref == "b"
