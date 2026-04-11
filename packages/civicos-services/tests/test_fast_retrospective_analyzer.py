"""
Tests for fast_retrospective_analyzer.py — PyMuPDF4LLM-backed high-stakes decision extraction.

Covers:
- _split_markdown_into_items (pure regex logic: lettered, numbered, fallback)
- _extract_from_item (LLM-dependent extraction with mocked LLM provider)
- extract_high_stakes_decisions (top-level orchestration, local/URL PDF paths, error handling)

Strategy: pure logic is tested directly; I/O (HTTP, pymupdf4llm, LLM provider)
is mocked at its import location inside the module.

To run:
    pytest packages/civicos-services/tests/test_fast_retrospective_analyzer.py -q --override-ini="addopts="
"""

import json
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# pymupdf4llm is an optional runtime dependency used for PDF -> markdown
# conversion. Tests mock that layer, so stub the module here if it is not
# installed in the test environment.
if "pymupdf4llm" not in sys.modules:
    _stub = ModuleType("pymupdf4llm")
    _stub.to_markdown = lambda *args, **kwargs: ""  # type: ignore[attr-defined]
    sys.modules["pymupdf4llm"] = _stub

from civicos_services.processing.fast_retrospective_analyzer import (  # noqa: E402
    FastRetrospectiveAnalyzer,
)
from civicos_services.processing.retrospective_analyzer import (  # noqa: E402
    HighStakesDecision,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def analyzer():
    """A real FastRetrospectiveAnalyzer — no network calls until session.get is invoked."""
    return FastRetrospectiveAnalyzer()


def _llm_returning(payload: dict) -> MagicMock:
    """Build a mock LLM whose .chat() returns a JSON-encoded payload string."""
    llm = MagicMock()
    llm.chat.return_value = json.dumps(payload)
    return llm


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\nfake pdf bytes"


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
        md = "Header line\n- a. First item text\n- b. Second item text\n- c. Third item text"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 3
        assert [ref for ref, _ in result] == ["a", "b", "c"]

    def test_lettered_item_content_is_isolated_per_item(self, analyzer):
        md = "Header\n- a. Alpha content\n- b. Beta content\n- c. Gamma content"
        result = analyzer._split_markdown_into_items(md)
        # Each item contains its own text but not its neighbours'.
        assert "Alpha" in result[0][1]
        assert "Beta" not in result[0][1]
        assert "Gamma" not in result[0][1]
        assert "Beta" in result[1][1]
        assert "Gamma" not in result[1][1]
        assert "Gamma" in result[2][1]

    def test_last_lettered_item_extends_to_end_of_document(self, analyzer):
        md = "Header\n- a. Alpha\n- b. Final item with tail content trailing"
        result = analyzer._split_markdown_into_items(md)
        assert result[-1][1].endswith("trailing")

    def test_numbered_items_used_as_fallback_when_no_lettered(self, analyzer):
        md = "\n1. First Item Title\n2. Second Item Title\n3. Third Item Title"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 3
        assert [ref for ref, _ in result] == ["1", "2", "3"]

    def test_numbered_pattern_requires_capital_letter_after_period(self, analyzer):
        # Only "2. Also" matches; "1. lowercase" does not because 'l' is lowercase.
        md = "\n1. lowercase skip\n2. Also matches"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 1
        assert result[0][0] == "2"
        assert "Also matches" in result[0][1]

    def test_lettered_pattern_takes_priority_over_numbered(self, analyzer):
        md = "\n- a. Letter item\n1. Number Item"
        result = analyzer._split_markdown_into_items(md)
        # Only lettered items are returned; numbered text becomes part of item a.
        assert len(result) == 1
        assert result[0][0] == "a"
        assert "Number Item" in result[0][1]

    def test_lettered_match_is_case_insensitive(self, analyzer):
        md = "\n- A. Capitalised letter item body content"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 1
        assert result[0][0] == "A"

    def test_single_lettered_item_covers_entire_remainder(self, analyzer):
        md = "Preamble text\n- a. Only item body"
        result = analyzer._split_markdown_into_items(md)
        assert len(result) == 1
        # Start is at '\n- a.' — preamble is dropped.
        assert result[0][1].startswith("\n- a.")
        assert "Only item body" in result[0][1]


# ---------------------------------------------------------------------------
# _extract_from_item — LLM mocked, real JSON parsing and HighStakesDecision build
# ---------------------------------------------------------------------------


LLM_PATCH_TARGET = (
    "civicos_services.processing.fast_retrospective_analyzer.get_model_for_task"
)


class TestExtractFromItemFilters:
    def test_returns_empty_when_llm_reports_not_high_stakes(self, analyzer):
        llm = _llm_returning({"is_high_stakes": False})
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "x" * 500, "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
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
                "a", "text", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert result == []

    def test_returns_empty_when_llm_raises(self, analyzer):
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("upstream API down")
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "text", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert result == []

    def test_returns_empty_when_llm_returns_invalid_json(self, analyzer):
        llm = MagicMock()
        llm.chat.return_value = "this is not json at all"
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "text", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert result == []

    def test_returns_empty_when_stakes_score_missing_and_min_nonzero(self, analyzer):
        # Missing stakes_score defaults to 0 in the filter check -> below any positive min.
        llm = _llm_returning({"is_high_stakes": True, "title": "No Score"})
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "text", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
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
                "a", "text", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert len(result) == 1
        assert result[0].stakes_score == 6


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
                "text",
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

    def test_stakes_score_defaults_to_six_when_missing_but_min_is_zero(self, analyzer):
        # With min_stakes_score=0, a missing stakes_score survives the filter.
        # The build step then defaults to 6.
        llm = _llm_returning({
            "is_high_stakes": True,
            "title": "No score provided",
        })
        with patch(LLM_PATCH_TARGET, return_value=llm):
            result = analyzer._extract_from_item(
                "a", "text", "2025-10-06", "city_council", 100000, 0, "http://x.pdf"
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
                "a", "text", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert len(result) == 1
        assert result[0].budget_amount == 0


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
        # Inspect the actual prompt the analyzer constructed.
        kwargs = llm.chat.call_args.kwargs
        messages = kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        prompt = messages[0]["content"]
        assert "AGENDA ITEM 5.b:" in prompt
        assert "Unique Marker ABC in item body" in prompt
        assert "$250,000" in prompt  # min_budget rendered with thousands separator
        assert kwargs["response_format"] == "json_object"

    def test_prompt_truncates_item_text_to_4000_chars(self, analyzer):
        llm = _llm_returning({"is_high_stakes": False})
        long_text = "X" * 10000
        with patch(LLM_PATCH_TARGET, return_value=llm):
            analyzer._extract_from_item(
                "a", long_text, "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        prompt = llm.chat.call_args.kwargs["messages"][0]["content"]
        # The item text slot contains up to 4000 X's, not 10000.
        assert "X" * 4000 in prompt
        assert "X" * 4001 not in prompt

    def test_uses_structured_extraction_model_task(self, analyzer):
        # The analyzer must request the "structured_extraction" model task
        # (not e.g. "chat" or "summarization") AND still honour the LLM's
        # is_high_stakes verdict for the returned decisions.
        llm = _llm_returning({"is_high_stakes": False})
        with patch(LLM_PATCH_TARGET, return_value=llm) as mock_get_model:
            result = analyzer._extract_from_item(
                "a", "text", "2025-10-06", "city_council", 100000, 6, "http://x.pdf"
            )
        assert mock_get_model.call_args.args == ("structured_extraction",)
        assert mock_get_model.call_count == 1
        # LLM said not high-stakes -> empty result, proving the task string
        # selection flowed through to a real extraction attempt.
        assert result == []
        assert llm.chat.call_count == 1


# ---------------------------------------------------------------------------
# extract_high_stakes_decisions — orchestration
# ---------------------------------------------------------------------------


PYMUPDF_PATCH_TARGET = (
    "civicos_services.processing.fast_retrospective_analyzer.pymupdf4llm.to_markdown"
)


class TestExtractHighStakesDecisionsLocalFile:
    def test_local_path_is_passed_directly_to_pymupdf(self, analyzer, tmp_path):
        pdf_path = tmp_path / "sample.pdf"
        pdf_path.write_bytes(_pdf_bytes())
        with patch(PYMUPDF_PATCH_TARGET, return_value="short markdown body") as mock_md:
            with patch.object(analyzer.session, "get") as mock_get:
                result = analyzer.extract_high_stakes_decisions(
                    pdf_url=str(pdf_path),
                    meeting_date="2025-10-06",
                )
        # No HTTP for local files.
        assert mock_get.call_count == 0
        # Exact local path forwarded (no temp file dance).
        assert mock_md.call_args.args == (str(pdf_path),)
        # Markdown "short markdown body" is a single "full" item, 19 chars, < 100 -> skipped.
        assert result == []

    def test_markdown_conversion_error_returns_empty_list(self, analyzer, tmp_path):
        pdf_path = tmp_path / "corrupt.pdf"
        pdf_path.write_bytes(b"not a real pdf")
        with patch(PYMUPDF_PATCH_TARGET, side_effect=ValueError("corrupt pdf")):
            result = analyzer.extract_high_stakes_decisions(
                pdf_url=str(pdf_path),
                meeting_date="2025-10-06",
            )
        assert result == []

    def test_tiny_items_are_skipped_before_llm_call(self, analyzer, tmp_path):
        pdf_path = tmp_path / "x.pdf"
        pdf_path.write_bytes(_pdf_bytes())
        # Each item body is well under 100 chars when stripped.
        md = "Header\n- a. tiny one\n- b. also small"
        llm = _llm_returning({"is_high_stakes": True, "stakes_score": 9, "title": "X"})
        with patch(PYMUPDF_PATCH_TARGET, return_value=md):
            with patch(LLM_PATCH_TARGET, return_value=llm):
                result = analyzer.extract_high_stakes_decisions(
                    pdf_url=str(pdf_path),
                    meeting_date="2025-10-06",
                )
        assert result == []
        assert llm.chat.call_count == 0

    def test_mix_of_high_stakes_and_low_stakes_items_returns_only_high(
        self, analyzer, tmp_path
    ):
        pdf_path = tmp_path / "x.pdf"
        pdf_path.write_bytes(_pdf_bytes())
        filler = " meaningful body content " * 10  # > 100 chars per item after strip
        md = (
            f"Header\n- a. Alpha{filler}"
            f"\n- b. Beta{filler}"
            f"\n- c. Gamma{filler}"
        )
        llm = MagicMock()
        # First: high; second: not; third: high.
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
        with patch(PYMUPDF_PATCH_TARGET, return_value=md):
            with patch(LLM_PATCH_TARGET, return_value=llm):
                result = analyzer.extract_high_stakes_decisions(
                    pdf_url=str(pdf_path),
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

    def test_default_meeting_type_is_city_council(self, analyzer, tmp_path):
        pdf_path = tmp_path / "x.pdf"
        pdf_path.write_bytes(_pdf_bytes())
        filler = " body content " * 15
        md = f"\n- a. Big item{filler}"
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 7,
            "title": "Some item",
        })
        with patch(PYMUPDF_PATCH_TARGET, return_value=md):
            with patch(LLM_PATCH_TARGET, return_value=llm):
                result = analyzer.extract_high_stakes_decisions(
                    pdf_url=str(pdf_path),
                    meeting_date="2025-10-06",
                    # meeting_type omitted
                )
        assert len(result) == 1
        assert result[0].meeting_type == "city_council"

    def test_min_budget_and_min_stakes_score_override_defaults(self, analyzer, tmp_path):
        pdf_path = tmp_path / "x.pdf"
        pdf_path.write_bytes(_pdf_bytes())
        filler = " body content " * 15
        md = f"\n- a. Item{filler}"
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 4,  # would fail default min=6, passes custom min=3
            "title": "Custom threshold",
        })
        with patch(PYMUPDF_PATCH_TARGET, return_value=md):
            with patch(LLM_PATCH_TARGET, return_value=llm):
                result = analyzer.extract_high_stakes_decisions(
                    pdf_url=str(pdf_path),
                    meeting_date="2025-10-06",
                    min_budget=50000,
                    min_stakes_score=3,
                )
        assert len(result) == 1
        assert result[0].stakes_score == 4
        # And min_budget must have been rendered in the prompt.
        prompt = llm.chat.call_args.kwargs["messages"][0]["content"]
        assert "$50,000" in prompt


class TestExtractHighStakesDecisionsUrl:
    def test_http_url_is_downloaded_via_session_with_timeout(self, analyzer):
        response = MagicMock()
        response.content = _pdf_bytes()
        with patch.object(analyzer.session, "get", return_value=response) as mock_get:
            with patch(PYMUPDF_PATCH_TARGET, return_value="short"):
                result = analyzer.extract_high_stakes_decisions(
                    pdf_url="https://example.gov/agenda.pdf",
                    meeting_date="2025-10-06",
                )
        assert mock_get.call_count == 1
        assert mock_get.call_args.args == ("https://example.gov/agenda.pdf",)
        assert mock_get.call_args.kwargs.get("timeout") == 60
        # short markdown yields no items eligible for extraction
        assert result == []

    def test_http_error_returns_empty_list(self, analyzer):
        response = MagicMock()
        response.raise_for_status.side_effect = RuntimeError("503")
        with patch.object(analyzer.session, "get", return_value=response):
            with patch(PYMUPDF_PATCH_TARGET) as mock_md:
                result = analyzer.extract_high_stakes_decisions(
                    pdf_url="https://example.gov/agenda.pdf",
                    meeting_date="2025-10-06",
                )
        # HTTP failure short-circuits before we ever touch the PDF parser.
        assert mock_md.call_count == 0
        assert result == []

    def test_temp_file_is_cleaned_up_after_url_download(self, analyzer):
        response = MagicMock()
        response.content = _pdf_bytes()
        captured_paths: list[str] = []

        def capture_path(path):
            captured_paths.append(path)
            return "short"

        with patch.object(analyzer.session, "get", return_value=response):
            with patch(PYMUPDF_PATCH_TARGET, side_effect=capture_path):
                analyzer.extract_high_stakes_decisions(
                    pdf_url="https://example.gov/agenda.pdf",
                    meeting_date="2025-10-06",
                )
        assert len(captured_paths) == 1
        # Temp path must have been a real file during parsing...
        assert captured_paths[0].endswith(".pdf")
        # ...and cleaned up afterwards.
        assert not os.path.exists(captured_paths[0])

    def test_original_url_is_preserved_as_agenda_url_in_decision(self, analyzer):
        response = MagicMock()
        response.content = _pdf_bytes()
        filler = " body content " * 15
        md = f"\n- a. Item{filler}"
        llm = _llm_returning({
            "is_high_stakes": True,
            "stakes_score": 8,
            "title": "URL test",
        })
        with patch.object(analyzer.session, "get", return_value=response):
            with patch(PYMUPDF_PATCH_TARGET, return_value=md):
                with patch(LLM_PATCH_TARGET, return_value=llm):
                    result = analyzer.extract_high_stakes_decisions(
                        pdf_url="https://example.gov/special-agenda.pdf",
                        meeting_date="2025-10-06",
                    )
        assert len(result) == 1
        assert result[0].agenda_url == "https://example.gov/special-agenda.pdf"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_each_instance_gets_its_own_session(self):
        a = FastRetrospectiveAnalyzer()
        b = FastRetrospectiveAnalyzer()
        assert a.session is not b.session
        # Session exposes the HTTP surface the analyzer depends on.
        assert callable(getattr(a.session, "get", None))
