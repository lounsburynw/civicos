"""Tests for LegislativeDiscovery — topic discovery, LLM filtering, context file updates, bill ID normalization."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.legislative.legislative_discovery import LegislativeDiscovery


# ==================== Fixtures ====================


@pytest.fixture
def discovery():
    """LegislativeDiscovery with mocked LegiScan client (no real API calls)."""
    with patch(
        "civicos_extraction.legislative.legislative_discovery.LegiScanClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.get_recent_bills.return_value = []
        instance.get_query_stats.return_value = {
            "queries_this_session": 0,
            "monthly_limit": 30000,
            "estimated_remaining": 30000,
        }
        d = LegislativeDiscovery(legiscan_api_key="test-key")
        yield d


@pytest.fixture
def sample_bills():
    """Three bills as returned by LegiScan search."""
    return [
        {
            "bill_id": 100,
            "bill_number": "SB 9",
            "title": "Housing Density Bonus",
            "description": "Allows additional density for affordable units",
            "status": "Active",
            "status_date": "2026-02-01",
            "last_action": "Referred to Committee",
            "url": "https://legiscan.com/CA/bill/SB9/2025",
        },
        {
            "bill_id": 200,
            "bill_number": "AB 1234",
            "title": "Transit Funding Reauthorization",
            "description": "Allocates state funds for local transit",
            "status": "Active",
            "status_date": "2026-03-01",
            "last_action": "Passed Assembly",
            "url": "https://legiscan.com/CA/bill/AB1234/2025",
        },
        {
            "bill_id": 300,
            "bill_number": "SB 100",
            "title": "Clean Energy Standards",
            "description": "Sets targets for renewable portfolio",
            "status": "Active",
            "status_date": "2026-01-15",
            "last_action": "Enrolled",
            "url": "https://legiscan.com/CA/bill/SB100/2025",
        },
    ]


@pytest.fixture
def llm_filtered_bills():
    """Bills after LLM filtering (subset with leverage points added)."""
    return [
        {
            "bill_id": 100,
            "bill_number": "SB 9",
            "title": "Housing Density Bonus",
            "local_implementation_required": True,
            "leverage_point": "City council sets density bonus percentages for local zones",
            "deadline": "2027-01-01",
        },
    ]


# ==================== _normalize_bill_id ====================


class TestNormalizeBillId:
    """Pure logic — no mocks needed."""

    def test_standard_bill_number(self, discovery):
        assert discovery._normalize_bill_id("SB 9") == "ca-sb-9"

    def test_assembly_bill(self, discovery):
        assert discovery._normalize_bill_id("AB 1234") == "ca-ab-1234"

    def test_dotted_bill_number(self, discovery):
        assert discovery._normalize_bill_id("A.B. 99") == "ca-a-b--99"

    def test_already_lowercase(self, discovery):
        assert discovery._normalize_bill_id("sb 42") == "ca-sb-42"

    def test_mixed_case(self, discovery):
        assert discovery._normalize_bill_id("Sb 10") == "ca-sb-10"

    def test_fallback_bill_id_format(self, discovery):
        assert discovery._normalize_bill_id("bill-999") == "ca-bill-999"

    def test_multiple_spaces(self, discovery):
        result = discovery._normalize_bill_id("SB  9")
        assert result == "ca-sb--9"

    def test_empty_string(self, discovery):
        assert discovery._normalize_bill_id("") == "ca-"


# ==================== discover_topic ====================


class TestDiscoverTopic:
    def test_unknown_topic_raises_valueerror(self, discovery):
        with pytest.raises(ValueError, match="Unknown topic: astrology"):
            discovery.discover_topic(topic="astrology")

    def test_returns_empty_list_when_no_bills_found(self, discovery):
        discovery.legiscan.get_recent_bills.return_value = []
        result = discovery.discover_topic(topic="housing")
        assert result == []

    def test_passes_top_3_keywords_to_legiscan(self, discovery):
        discovery.legiscan.get_recent_bills.return_value = []
        discovery.discover_topic(topic="housing", state="california", days_back=30)
        call_args = discovery.legiscan.get_recent_bills.call_args
        keywords_passed = call_args.kwargs.get("topic_keywords") or call_args[1].get(
            "topic_keywords"
        )
        assert len(keywords_passed) == 3
        assert keywords_passed == ["housing", "affordable housing", "zoning"]

    def test_limits_bills_sent_to_llm_filter(self, discovery, sample_bills):
        """With limit=2, only the first 2 bills should be sent to the LLM filter."""
        discovery.legiscan.get_recent_bills.return_value = sample_bills

        with patch.object(discovery, "_filter_relevant_bills", return_value=[]) as mock_filter:
            discovery.discover_topic(topic="housing", limit=2)
            filtered_input = mock_filter.call_args[0][0]
            assert len(filtered_input) == 2
            assert filtered_input[0]["bill_id"] == 100
            assert filtered_input[1]["bill_id"] == 200

    def test_returns_llm_filtered_results(self, discovery, sample_bills, llm_filtered_bills):
        discovery.legiscan.get_recent_bills.return_value = sample_bills

        with patch.object(
            discovery, "_filter_relevant_bills", return_value=llm_filtered_bills
        ):
            result = discovery.discover_topic(topic="housing")
            assert len(result) == 1
            assert result[0]["bill_number"] == "SB 9"
            assert result[0]["leverage_point"] == "City council sets density bonus percentages for local zones"

    def test_state_parameter_forwarded(self, discovery):
        discovery.legiscan.get_recent_bills.return_value = []
        result = discovery.discover_topic(topic="budget", state="texas")
        call_kwargs = discovery.legiscan.get_recent_bills.call_args.kwargs
        assert call_kwargs["state"] == "texas"
        assert result == []

    def test_days_back_parameter_forwarded(self, discovery):
        discovery.legiscan.get_recent_bills.return_value = []
        result = discovery.discover_topic(topic="budget", days_back=180)
        call_kwargs = discovery.legiscan.get_recent_bills.call_args.kwargs
        assert call_kwargs["days_back"] == 180
        assert result == []


# ==================== _filter_relevant_bills ====================


class TestFilterRelevantBills:
    def test_returns_bills_unfiltered_when_openai_unavailable(self, discovery, sample_bills):
        with patch(
            "civicos_extraction.legislative.legislative_discovery.OPENAI_AVAILABLE", False
        ):
            result = discovery._filter_relevant_bills(sample_bills, "housing")
            assert len(result) == 3
            assert result[0]["bill_id"] == 100
            assert result[2]["bill_id"] == 300

    @patch("civicos_extraction.legislative.legislative_discovery.openai")
    def test_parses_llm_json_array_response(self, mock_openai, discovery, sample_bills):
        """LLM returns a JSON array of relevant bills."""
        llm_response = [
            {"bill_id": 100, "bill_number": "SB 9", "leverage_point": "zoning control"}
        ]
        mock_message = MagicMock()
        mock_message.content = json.dumps(llm_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_openai.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        result = discovery._filter_relevant_bills(sample_bills, "housing")
        assert len(result) == 1
        assert result[0]["bill_number"] == "SB 9"
        assert result[0]["leverage_point"] == "zoning control"

    @patch("civicos_extraction.legislative.legislative_discovery.openai")
    def test_parses_llm_object_with_bills_key(self, mock_openai, discovery, sample_bills):
        """LLM returns {bills: [...]} instead of a bare array."""
        llm_response = {
            "bills": [
                {"bill_id": 200, "bill_number": "AB 1234", "leverage_point": "transit funding"}
            ]
        }
        mock_message = MagicMock()
        mock_message.content = json.dumps(llm_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_openai.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        result = discovery._filter_relevant_bills(sample_bills, "transportation")
        assert len(result) == 1
        assert result[0]["bill_number"] == "AB 1234"

    @patch("civicos_extraction.legislative.legislative_discovery.openai")
    def test_parses_llm_object_with_relevant_bills_key(self, mock_openai, discovery, sample_bills):
        """LLM returns {relevant_bills: [...]} instead of bare array or {bills: [...]}."""
        llm_response = {
            "relevant_bills": [
                {"bill_id": 300, "bill_number": "SB 100", "leverage_point": "clean energy"}
            ]
        }
        mock_message = MagicMock()
        mock_message.content = json.dumps(llm_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_openai.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        result = discovery._filter_relevant_bills(sample_bills, "environment")
        assert len(result) == 1
        assert result[0]["bill_number"] == "SB 100"

    @patch("civicos_extraction.legislative.legislative_discovery.openai")
    def test_returns_empty_list_when_llm_raises(self, mock_openai, discovery, sample_bills):
        """API error should return empty list, not crash."""
        mock_openai.chat.completions.create.side_effect = RuntimeError("API quota exceeded")
        result = discovery._filter_relevant_bills(sample_bills, "housing")
        assert result == []

    @patch("civicos_extraction.legislative.legislative_discovery.openai")
    def test_returns_empty_on_invalid_json(self, mock_openai, discovery, sample_bills):
        """Malformed JSON from LLM should return empty list."""
        mock_message = MagicMock()
        mock_message.content = "this is not json"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_openai.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        result = discovery._filter_relevant_bills(sample_bills, "housing")
        assert result == []

    @patch("civicos_extraction.legislative.legislative_discovery.openai")
    def test_llm_called_with_correct_model(self, mock_openai, discovery, sample_bills):
        """Verify gpt-4o-mini model is used (cost control)."""
        llm_response = []
        mock_message = MagicMock()
        mock_message.content = json.dumps(llm_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_openai.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        discovery._filter_relevant_bills(sample_bills, "housing")
        call_kwargs = mock_openai.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["temperature"] == 0.1

    @patch("civicos_extraction.legislative.legislative_discovery.openai")
    def test_bill_descriptions_truncated_in_prompt(self, mock_openai, discovery):
        """Bills with very long descriptions should be truncated to 200 chars in the LLM prompt."""
        long_bill = {
            "bill_id": 500,
            "bill_number": "AB 999",
            "title": "Long Bill",
            "description": "A" * 500,
            "last_action": "Introduced",
        }
        llm_response = []
        mock_message = MagicMock()
        mock_message.content = json.dumps(llm_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_openai.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        discovery._filter_relevant_bills([long_bill], "housing")

        prompt_text = mock_openai.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        # The description in the prompt should be at most 200 chars
        bills_json_str = prompt_text.split("Bills to analyze:\n")[1]
        bills_in_prompt = json.loads(bills_json_str)
        assert len(bills_in_prompt[0]["description"]) == 200


# ==================== update_legislative_context ====================


class TestUpdateLegislativeContext:
    def test_dry_run_does_not_write_file(self, discovery, llm_filtered_bills, tmp_path):
        context_file = tmp_path / "housing.json"

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            result = discovery.update_legislative_context(
                topic="housing",
                relevant_bills=llm_filtered_bills,
                dry_run=True,
            )
        # File must NOT be created on disk
        assert not context_file.exists()
        # Return value is still a Path
        assert result == context_file

    def test_creates_new_context_file_structure(self, discovery, llm_filtered_bills, tmp_path):
        context_file = tmp_path / "housing.json"

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=llm_filtered_bills,
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        assert written["jurisdiction"] == "california"
        assert written["topic"] == "housing"
        assert "LegiScan API" in written["data_sources"]
        assert "LLM-assisted relevance filtering" in written["data_sources"]
        assert "Manual review" in written["data_sources"]
        assert "ca-sb-9" in written["state_legislation"]

    def test_new_bill_fields_populated_correctly(self, discovery, llm_filtered_bills, tmp_path):
        context_file = tmp_path / "housing.json"

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=llm_filtered_bills,
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        bill_entry = written["state_legislation"]["ca-sb-9"]
        assert bill_entry["bill"] == "Housing Density Bonus"
        assert bill_entry["local_implementation_required"] is True
        assert bill_entry["local_deadline"] == "2027-01-01"
        assert bill_entry["leverage_point"] == "City council sets density bonus percentages for local zones"
        assert bill_entry["_legiscan_id"] == 100

    def test_does_not_overwrite_existing_bills(self, discovery, llm_filtered_bills, tmp_path):
        context_file = tmp_path / "housing.json"
        existing = {
            "jurisdiction": "california",
            "topic": "housing",
            "last_updated": "2026-01-01T00:00:00",
            "data_sources": ["LegiScan API"],
            "state_legislation": {
                "ca-sb-9": {
                    "bill": "Original SB 9 entry",
                    "leverage_point": "Original leverage point",
                }
            },
            "federal_programs": {},
        }
        context_file.write_text(json.dumps(existing))

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=llm_filtered_bills,
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        # Original entry preserved, not overwritten
        assert written["state_legislation"]["ca-sb-9"]["bill"] == "Original SB 9 entry"
        assert written["state_legislation"]["ca-sb-9"]["leverage_point"] == "Original leverage point"

    def test_adds_new_bills_alongside_existing(self, discovery, tmp_path):
        context_file = tmp_path / "housing.json"
        existing = {
            "jurisdiction": "california",
            "topic": "housing",
            "last_updated": "2026-01-01T00:00:00",
            "data_sources": ["LegiScan API"],
            "state_legislation": {
                "ca-sb-9": {"bill": "Existing SB 9"}
            },
            "federal_programs": {},
        }
        context_file.write_text(json.dumps(existing))

        new_bills = [
            {
                "bill_id": 400,
                "bill_number": "AB 500",
                "title": "New Zoning Bill",
                "leverage_point": "Council approves zoning changes",
            },
        ]

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=new_bills,
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        assert "ca-sb-9" in written["state_legislation"]
        assert "ca-ab-500" in written["state_legislation"]
        assert written["state_legislation"]["ca-ab-500"]["bill"] == "New Zoning Bill"

    def test_updates_last_updated_timestamp(self, discovery, llm_filtered_bills, tmp_path):
        context_file = tmp_path / "housing.json"

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=llm_filtered_bills,
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        # Timestamp should be a valid ISO datetime, not the initial placeholder
        from datetime import datetime
        parsed = datetime.fromisoformat(written["last_updated"])
        assert parsed.year >= 2026

    def test_empty_bills_list_creates_file_with_no_legislation(self, discovery, tmp_path):
        context_file = tmp_path / "empty.json"

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=[],
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        assert written["state_legislation"] == {}

    def test_bill_missing_bill_number_uses_bill_id_fallback(self, discovery, tmp_path):
        context_file = tmp_path / "housing.json"
        bills_without_number = [
            {"bill_id": 777, "title": "Mystery Bill", "leverage_point": "Unknown"},
        ]

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=bills_without_number,
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        assert "ca-bill-777" in written["state_legislation"]

    def test_keywords_limited_to_5(self, discovery, tmp_path):
        context_file = tmp_path / "housing.json"
        bills = [
            {"bill_id": 1, "bill_number": "SB 1", "title": "Test"},
        ]

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=bills,
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        keywords = written["state_legislation"]["ca-sb-1"]["keywords"]
        assert len(keywords) <= 5
        # housing has 7 keywords; only first 5 should appear
        assert keywords == ["housing", "affordable housing", "zoning", "density", "ADU"]

    def test_state_parameter_used_in_new_context(self, discovery, tmp_path):
        context_file = tmp_path / "budget.json"

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="budget",
                relevant_bills=[],
                state="texas",
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        assert written["jurisdiction"] == "texas"

    def test_returns_path_object(self, discovery, llm_filtered_bills, tmp_path):
        context_file = tmp_path / "housing.json"

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            result = discovery.update_legislative_context(
                topic="housing",
                relevant_bills=llm_filtered_bills,
                dry_run=False,
            )
        assert result == context_file

    def test_description_truncated_to_200_chars_in_summary(self, discovery, tmp_path):
        context_file = tmp_path / "housing.json"
        bills = [
            {
                "bill_id": 1,
                "bill_number": "SB 1",
                "title": "Test",
                "description": "X" * 500,
            },
        ]

        with patch(
            "civicos_extraction.legislative.legislative_discovery.Path",
            return_value=context_file,
        ):
            discovery.update_legislative_context(
                topic="housing",
                relevant_bills=bills,
                dry_run=False,
            )

        written = json.loads(context_file.read_text())
        assert len(written["state_legislation"]["ca-sb-1"]["summary"]) == 200


# ==================== discover_topic valid topics ====================


class TestValidTopics:
    """Verify all TOPIC_KEYWORDS keys are accepted by discover_topic."""

    @pytest.mark.parametrize("topic", ["housing", "transportation", "environment", "budget", "education"])
    def test_all_defined_topics_are_accepted(self, discovery, topic):
        discovery.legiscan.get_recent_bills.return_value = []
        result = discovery.discover_topic(topic=topic)
        assert result == []
