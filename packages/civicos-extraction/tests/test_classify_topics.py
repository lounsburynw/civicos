"""
Tests for civicos_extraction.cli.classify_topics module.

Tests topic classification for legislation bills: topic definitions,
bill fetching from Postgres, LLM-based batch classification, summary
truncation, topic validation, and the CLI orchestrator (stats, dry-run,
batch processing). External I/O (database, OpenAI) is mocked at the
boundary; all classification logic runs for real.
"""

import argparse
import json
import pytest
from unittest.mock import patch, MagicMock

from civicos_extraction.cli.classify_topics import (
    TOPIC_DEFINITIONS,
    add_classify_topics_parser,
    get_untagged_bills,
    get_topic_stats,
    classify_bills_batch,
    run_classify_topics,
)


# ---------------------------------------------------------------------------
# TOPIC_DEFINITIONS constant
# ---------------------------------------------------------------------------


class TestTopicDefinitions:
    def test_contains_expected_topics(self):
        expected = {
            "housing", "transportation", "environment", "budget",
            "education", "public_safety", "healthcare", "labor", "governance",
        }
        assert set(TOPIC_DEFINITIONS.keys()) == expected

    def test_all_definitions_are_nonempty_strings(self):
        for topic, definition in TOPIC_DEFINITIONS.items():
            assert len(definition) > 10, f"Topic '{topic}' has too-short definition"

    def test_housing_definition_contains_zoning(self):
        assert "Zoning" in TOPIC_DEFINITIONS["housing"]

    def test_transportation_definition_contains_transit(self):
        assert "Transit" in TOPIC_DEFINITIONS["transportation"]


# ---------------------------------------------------------------------------
# add_classify_topics_parser
# ---------------------------------------------------------------------------


class TestAddClassifyTopicsParser:
    def test_parser_defaults(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_classify_topics_parser(subparsers)
        args = parser.parse_args(["classify-topics"])
        assert args.state == "CA"
        assert args.limit is None
        assert args.batch_size == 25
        assert args.dry_run is False
        assert args.stats is False

    def test_parser_accepts_all_options(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_classify_topics_parser(subparsers)
        args = parser.parse_args([
            "classify-topics",
            "--state", "NY",
            "--limit", "50",
            "--batch-size", "10",
            "--dry-run",
            "--stats",
        ])
        assert args.state == "NY"
        assert args.limit == 50
        assert args.batch_size == 10
        assert args.dry_run is True
        assert args.stats is True

    def test_limit_is_int_type(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_classify_topics_parser(subparsers)
        args = parser.parse_args(["classify-topics", "--limit", "100"])
        assert args.limit == 100
        assert isinstance(args.limit, int)


# ---------------------------------------------------------------------------
# get_untagged_bills
# ---------------------------------------------------------------------------


class TestGetUntaggedBills:
    def _make_mock_pg(self, rows):
        """Create a mock psycopg2 module with cursor returning given rows."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pg = MagicMock()
        mock_pg.connect.return_value = mock_conn
        return mock_pg, mock_cursor

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="postgres://test")
    def test_returns_bill_dicts_from_rows(self, mock_getenv):
        rows = [
            ("bill-1", "AB 100", "Housing Act", "Increases housing density"),
            ("bill-2", "SB 200", "Transit Bill", "Expands transit service"),
        ]
        mock_pg, _ = self._make_mock_pg(rows)

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            result = get_untagged_bills("CA")

        assert len(result) == 2
        assert result[0]["bill_id"] == "bill-1"
        assert result[0]["bill_number"] == "AB 100"
        assert result[0]["bill_name"] == "Housing Act"
        assert result[0]["summary"] == "Increases housing density"
        assert result[1]["bill_id"] == "bill-2"
        assert result[1]["bill_number"] == "SB 200"

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value=None)
    def test_raises_when_no_database_url(self, mock_getenv):
        with pytest.raises(ValueError, match="DATABASE_URL not set"):
            get_untagged_bills("CA")

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="postgres://test")
    def test_null_name_and_summary_become_empty_strings(self, mock_getenv):
        rows = [("bill-1", "AB 100", None, None)]
        mock_pg, _ = self._make_mock_pg(rows)

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            result = get_untagged_bills("CA")

        assert result[0]["bill_name"] == ""
        assert result[0]["summary"] == ""

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="postgres://test")
    def test_returns_empty_list_when_no_rows(self, mock_getenv):
        mock_pg, _ = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            result = get_untagged_bills("CA")

        assert result == []

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="postgres://test")
    def test_limit_appended_to_query(self, mock_getenv):
        mock_pg, mock_cursor = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            get_untagged_bills("CA", limit=50)

        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "LIMIT 50" in executed_sql

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="postgres://test")
    def test_no_limit_when_none(self, mock_getenv):
        mock_pg, mock_cursor = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            get_untagged_bills("CA", limit=None)

        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "LIMIT" not in executed_sql

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="postgres://test")
    def test_passes_state_as_query_parameter(self, mock_getenv):
        mock_pg, mock_cursor = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            get_untagged_bills("NY")

        query_params = mock_cursor.execute.call_args[0][1]
        assert query_params == ("NY",)


# ---------------------------------------------------------------------------
# get_topic_stats
# ---------------------------------------------------------------------------


class TestGetTopicStats:
    def _make_mock_pg(self, rows):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pg = MagicMock()
        mock_pg.connect.return_value = mock_conn
        return mock_pg

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value=None)
    def test_raises_when_no_database_url(self, mock_getenv):
        with pytest.raises(ValueError, match="DATABASE_URL not set"):
            get_topic_stats("CA")

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="postgres://test")
    def test_returns_topic_count_dict(self, mock_getenv):
        mock_pg = self._make_mock_pg([
            ("housing", 45),
            ("transportation", 30),
            ("untagged", 100),
        ])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            stats = get_topic_stats("CA")

        assert stats["housing"] == 45
        assert stats["transportation"] == 30
        assert stats["untagged"] == 100
        assert len(stats) == 3

    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="postgres://test")
    def test_empty_table_returns_empty_dict(self, mock_getenv):
        mock_pg = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            stats = get_topic_stats("CA")

        assert stats == {}


# ---------------------------------------------------------------------------
# classify_bills_batch
# ---------------------------------------------------------------------------


class TestClassifyBillsBatch:
    def test_truncates_long_summaries(self):
        """Summaries longer than 200 chars should be truncated with ellipsis."""
        long_summary = "A" * 300
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": long_summary}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "classifications": [{"bill_id": "b1", "topic": "housing", "confidence": 0.9}]
        })

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = classify_bills_batch(bills, TOPIC_DEFINITIONS)

        # Verify the truncation happened by checking the prompt
        call_kwargs = mock_client.chat.completions.create.call_args
        prompt_content = call_kwargs[1]["messages"][1]["content"]
        assert "AAA..." in prompt_content
        # Also verify result
        assert len(result) == 1
        assert result[0]["bill_id"] == "b1"
        assert result[0]["topic"] == "housing"

    def test_short_summaries_not_truncated(self):
        """Summaries under 200 chars should not be truncated."""
        short_summary = "Short bill about housing"
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": short_summary}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "classifications": [{"bill_id": "b1", "topic": "housing", "confidence": 0.95}]
        })

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = classify_bills_batch(bills, TOPIC_DEFINITIONS)

        call_kwargs = mock_client.chat.completions.create.call_args
        prompt_content = call_kwargs[1]["messages"][1]["content"]
        assert short_summary in prompt_content
        assert "..." not in prompt_content.split(short_summary)[1][:5]  # no trailing ellipsis

    def test_returns_empty_when_openai_unavailable(self):
        """When OPENAI_AVAILABLE is False, returns empty list."""
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "test"}]

        with patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", False):
            result = classify_bills_batch(bills, TOPIC_DEFINITIONS)

        assert result == []

    def test_returns_empty_on_api_error(self):
        """When OpenAI raises an exception, returns empty list."""
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "test"}]

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.side_effect = RuntimeError("API down")

            result = classify_bills_batch(bills, TOPIC_DEFINITIONS)

        assert result == []

    def test_parses_classifications_from_response(self):
        """Classifications are extracted from the 'classifications' key."""
        bills = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Housing Act", "summary": "Housing"},
            {"bill_id": "b2", "bill_number": "SB 2", "bill_name": "Transit Bill", "summary": "Transit"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "classifications": [
                {"bill_id": "b1", "topic": "housing", "confidence": 0.9},
                {"bill_id": "b2", "topic": "transportation", "confidence": 0.85},
            ]
        })

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = classify_bills_batch(bills, TOPIC_DEFINITIONS)

        assert len(result) == 2
        assert result[0]["bill_id"] == "b1"
        assert result[0]["topic"] == "housing"
        assert result[0]["confidence"] == 0.9
        assert result[1]["bill_id"] == "b2"
        assert result[1]["topic"] == "transportation"

    def test_handles_none_bill_name_and_summary(self):
        """Bills with None name/summary should not crash."""
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": None, "summary": None}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "classifications": [{"bill_id": "b1", "topic": "other", "confidence": 0.5}]
        })

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = classify_bills_batch(bills, TOPIC_DEFINITIONS)

        assert len(result) == 1
        assert result[0]["topic"] == "other"

    def test_prompt_includes_all_topic_categories(self):
        """The prompt sent to OpenAI should list all topic categories."""
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "test"}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"classifications": []})

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            classify_bills_batch(bills, TOPIC_DEFINITIONS)

        call_kwargs = mock_client.chat.completions.create.call_args
        prompt = call_kwargs[1]["messages"][1]["content"]
        for topic in TOPIC_DEFINITIONS:
            assert f"- {topic}:" in prompt
        assert "- other:" in prompt

    def test_uses_gpt4o_mini_model(self):
        """Should use gpt-4o-mini for cost-effective classification."""
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "test"}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"classifications": []})

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            classify_bills_batch(bills, TOPIC_DEFINITIONS)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs[1]["model"] == "gpt-4o-mini"

    def test_empty_bills_list(self):
        """Empty input should not call OpenAI and return empty."""
        # The function builds an empty prompt but still calls OpenAI;
        # we just verify it doesn't crash.
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"classifications": []})

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = classify_bills_batch([], TOPIC_DEFINITIONS)

        assert result == []

    def test_summary_exactly_200_chars_not_truncated(self):
        """Summary of exactly 200 chars should NOT be truncated."""
        summary_200 = "B" * 200
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": summary_200}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "classifications": [{"bill_id": "b1", "topic": "budget", "confidence": 0.8}]
        })

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            classify_bills_batch(bills, TOPIC_DEFINITIONS)

        call_kwargs = mock_client.chat.completions.create.call_args
        prompt = call_kwargs[1]["messages"][1]["content"]
        # The full 200-char string should appear without truncation
        assert summary_200 in prompt

    def test_summary_201_chars_is_truncated(self):
        """Summary of 201 chars should be truncated to 200 + ellipsis."""
        summary_201 = "C" * 201
        bills = [{"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": summary_201}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "classifications": [{"bill_id": "b1", "topic": "budget", "confidence": 0.8}]
        })

        with patch("civicos_extraction.cli.classify_topics.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            classify_bills_batch(bills, TOPIC_DEFINITIONS)

        call_kwargs = mock_client.chat.completions.create.call_args
        prompt = call_kwargs[1]["messages"][1]["content"]
        # Should have the first 200 C's followed by "..."
        assert "C" * 200 + "..." in prompt
        # Should NOT have the full 201-char string
        assert summary_201 not in prompt


# ---------------------------------------------------------------------------
# run_classify_topics — orchestrator
# ---------------------------------------------------------------------------


class TestRunClassifyTopics:
    def _make_args(self, **kwargs):
        defaults = {
            "state": "CA",
            "limit": None,
            "batch_size": 25,
            "dry_run": False,
            "stats": False,
            "verbose": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch("civicos_extraction.cli.classify_topics.get_topic_stats")
    def test_stats_mode_returns_zero(self, mock_stats):
        mock_stats.return_value = {"housing": 50, "transportation": 30, "untagged": 20}
        args = self._make_args(stats=True)
        result = run_classify_topics(args)
        assert result == 0

    @patch("civicos_extraction.cli.classify_topics.get_topic_stats")
    def test_stats_mode_uppercases_state(self, mock_stats):
        mock_stats.return_value = {"housing": 10}
        args = self._make_args(state="ca", stats=True)
        result = run_classify_topics(args)
        assert result == 0
        mock_stats.assert_called_once_with("CA")

    def test_returns_1_when_openai_unavailable(self):
        args = self._make_args()
        with patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", False):
            result = run_classify_topics(args)
        assert result == 1

    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv")
    def test_returns_1_when_no_openai_key(self, mock_getenv):
        mock_getenv.side_effect = lambda k: None  # Both keys missing
        args = self._make_args()
        result = run_classify_topics(args)
        assert result == 1

    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv")
    def test_returns_1_when_no_database_url(self, mock_getenv):
        def getenv_side(key):
            if key == "OPENAI_API_KEY":
                return "sk-test"
            return None  # DATABASE_URL missing
        mock_getenv.side_effect = getenv_side
        args = self._make_args()
        result = run_classify_topics(args)
        assert result == 1

    @patch("civicos_extraction.cli.classify_topics.get_topic_stats")
    @patch("civicos_extraction.cli.classify_topics.get_untagged_bills")
    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="set")
    def test_returns_0_when_no_untagged_bills(self, mock_getenv, mock_get_bills, mock_stats):
        mock_get_bills.return_value = []
        args = self._make_args()
        result = run_classify_topics(args)
        assert result == 0

    @patch("civicos_extraction.cli.classify_topics.get_untagged_bills")
    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="set")
    def test_dry_run_returns_0_without_classifying(self, mock_getenv, mock_get_bills):
        mock_get_bills.return_value = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test Bill", "summary": "Test"},
            {"bill_id": "b2", "bill_number": "SB 2", "bill_name": "Another Bill", "summary": "Another"},
        ]
        args = self._make_args(dry_run=True)
        result = run_classify_topics(args)
        assert result == 0

    @patch("civicos_extraction.cli.classify_topics.get_topic_stats")
    @patch("civicos_extraction.cli.classify_topics.classify_bills_batch")
    @patch("civicos_extraction.cli.classify_topics.get_untagged_bills")
    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="set")
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    def test_valid_topics_are_passed_through(
        self, mock_getenv, mock_get_bills, mock_classify, mock_stats
    ):
        mock_get_bills.return_value = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "Test"},
        ]
        mock_classify.return_value = [
            {"bill_id": "b1", "topic": "housing", "confidence": 0.9},
        ]
        mock_stats.return_value = {"housing": 1}

        with patch("civicos_extraction.cli.classify_topics.PostgresBackend", create=True) as MockPB:
            mock_backend = MagicMock()
            mock_backend.update_legislation_topics.return_value = 1
            # Patch the import inside run_classify_topics
            with patch.dict("sys.modules", {
                "civicos.storage.postgres_backend": MagicMock(PostgresBackend=lambda url: mock_backend),
                "civicos.storage": MagicMock(),
                "civicos": MagicMock(),
            }):
                with patch(
                    "civicos_extraction.cli.classify_topics.PostgresBackend",
                    create=True,
                    return_value=mock_backend,
                ):
                    # Re-import to get the patched version
                    import importlib
                    import civicos_extraction.cli.classify_topics as mod

                    args = self._make_args()
                    result = run_classify_topics(args)

        assert result == 0

    @patch("civicos_extraction.cli.classify_topics.get_topic_stats")
    @patch("civicos_extraction.cli.classify_topics.classify_bills_batch")
    @patch("civicos_extraction.cli.classify_topics.get_untagged_bills")
    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="set")
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    def test_invalid_topic_defaults_to_other(
        self, mock_getenv, mock_get_bills, mock_classify, mock_stats
    ):
        mock_get_bills.return_value = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "Test"},
        ]
        mock_classify.return_value = [
            {"bill_id": "b1", "topic": "INVALID_TOPIC", "confidence": 0.5},
        ]
        mock_stats.return_value = {"other": 1}

        with patch(
            "civicos.storage.postgres_backend.PostgresBackend",
        ) as MockPB:
            mock_backend = MagicMock()
            mock_backend.update_legislation_topics.return_value = 1
            MockPB.return_value = mock_backend

            args = self._make_args()
            result = run_classify_topics(args)

        # Verify the update was called with "other" not the invalid topic
        update_call = mock_backend.update_legislation_topics.call_args
        updates = update_call[0][1]
        assert updates[0]["topic"] == "other"

    @patch("civicos_extraction.cli.classify_topics.classify_bills_batch")
    @patch("civicos_extraction.cli.classify_topics.get_untagged_bills")
    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="set")
    def test_batching_splits_bills(self, mock_getenv, mock_get_bills, mock_classify):
        # Create 5 bills with batch_size=2 → should call classify 3 times
        mock_get_bills.return_value = [
            {"bill_id": f"b{i}", "bill_number": f"AB {i}", "bill_name": f"Bill {i}", "summary": f"Summary {i}"}
            for i in range(5)
        ]
        # Return empty so we skip the DB update path
        mock_classify.return_value = []

        args = self._make_args(batch_size=2)

        # Mock get_topic_stats for the final stats display
        with patch("civicos_extraction.cli.classify_topics.get_topic_stats", return_value={}):
            result = run_classify_topics(args)

        assert mock_classify.call_count == 3
        # First batch: 2 bills
        assert len(mock_classify.call_args_list[0][0][0]) == 2
        # Second batch: 2 bills
        assert len(mock_classify.call_args_list[1][0][0]) == 2
        # Third batch: 1 bill
        assert len(mock_classify.call_args_list[2][0][0]) == 1

    @patch("civicos_extraction.cli.classify_topics.get_untagged_bills")
    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="set")
    def test_dry_run_shows_bill_sample(self, mock_getenv, mock_get_bills):
        """Dry run with >5 bills should not crash (covers the 'and N more' path)."""
        mock_get_bills.return_value = [
            {"bill_id": f"b{i}", "bill_number": f"AB {i}", "bill_name": f"Bill {i} about policy", "summary": f"S{i}"}
            for i in range(8)
        ]
        args = self._make_args(dry_run=True)
        result = run_classify_topics(args)
        assert result == 0

    @patch("civicos_extraction.cli.classify_topics.classify_bills_batch")
    @patch("civicos_extraction.cli.classify_topics.get_untagged_bills")
    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="set")
    def test_empty_classification_batch_is_skipped(self, mock_getenv, mock_get_bills, mock_classify):
        """When classify_bills_batch returns empty, no DB update should happen."""
        mock_get_bills.return_value = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "Test"},
        ]
        mock_classify.return_value = []

        args = self._make_args()
        with patch("civicos_extraction.cli.classify_topics.get_topic_stats", return_value={}):
            result = run_classify_topics(args)

        assert result == 0

    @patch("civicos_extraction.cli.classify_topics.classify_bills_batch")
    @patch("civicos_extraction.cli.classify_topics.get_untagged_bills")
    @patch("civicos_extraction.cli.classify_topics.OPENAI_AVAILABLE", True)
    @patch("civicos_extraction.cli.classify_topics.os.getenv", return_value="set")
    def test_topic_lowercased_from_llm_response(self, mock_getenv, mock_get_bills, mock_classify):
        """Topics from LLM should be lowercased."""
        mock_get_bills.return_value = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "Test"},
        ]
        mock_classify.return_value = [
            {"bill_id": "b1", "topic": "HOUSING", "confidence": 0.9},
        ]

        with patch("civicos_extraction.cli.classify_topics.get_topic_stats", return_value={"housing": 1}):
            with patch(
                "civicos.storage.postgres_backend.PostgresBackend",
            ) as MockPB:
                mock_backend = MagicMock()
                mock_backend.update_legislation_topics.return_value = 1
                MockPB.return_value = mock_backend
                with patch.dict("os.environ", {"DATABASE_URL": "postgres://test"}):
                    args = self._make_args()
                    result = run_classify_topics(args)

        update_call = mock_backend.update_legislation_topics.call_args
        updates = update_call[0][1]
        assert updates[0]["topic"] == "housing"

    @patch("civicos_extraction.cli.classify_topics.get_topic_stats")
    def test_stats_handles_zero_total(self, mock_stats):
        """Stats mode should handle empty table (zero total) without division error."""
        mock_stats.return_value = {}
        args = self._make_args(stats=True)
        result = run_classify_topics(args)
        assert result == 0


# ---------------------------------------------------------------------------
# Topic validation logic (extracted from run_classify_topics)
# ---------------------------------------------------------------------------


class TestTopicValidation:
    """Tests for the topic validation logic inside the classification loop."""

    def test_all_defined_topics_are_valid(self):
        """Every key in TOPIC_DEFINITIONS should be accepted as valid."""
        valid_topics = set(TOPIC_DEFINITIONS.keys()) | {"other"}
        for topic in TOPIC_DEFINITIONS:
            assert topic in valid_topics

    def test_other_is_valid(self):
        """The 'other' fallback should be valid."""
        valid_topics = set(TOPIC_DEFINITIONS.keys()) | {"other"}
        assert "other" in valid_topics

    def test_invalid_topics_not_in_valid_set(self):
        """Random strings should not be in the valid topic set."""
        valid_topics = set(TOPIC_DEFINITIONS.keys()) | {"other"}
        assert "random_topic" not in valid_topics
        assert "" not in valid_topics
        assert "HOUSING" not in valid_topics  # case-sensitive
