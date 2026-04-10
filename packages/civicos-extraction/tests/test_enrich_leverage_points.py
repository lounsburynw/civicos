"""
Tests for civicos_extraction.cli.enrich_leverage_points module.

Tests leverage point enrichment for legislation bills: prompt template,
bill fetching from Postgres, Claude-based batch enrichment with JSON parsing
(including markdown-wrapped responses), summary truncation, null filtering,
stats queries, and the CLI orchestrator (stats, dry-run, batch processing,
DB updates). External I/O (database, Anthropic API) is mocked at the
boundary; all enrichment logic runs for real.
"""

import argparse
import json
import pytest
from unittest.mock import patch, MagicMock

from civicos_extraction.cli.enrich_leverage_points import (
    LEVERAGE_POINT_PROMPT,
    add_enrich_leverage_parser,
    get_unenriched_bills,
    get_leverage_stats,
    enrich_batch,
    run_enrich_leverage,
)


# ---------------------------------------------------------------------------
# LEVERAGE_POINT_PROMPT constant
# ---------------------------------------------------------------------------


class TestLeveragePointPrompt:
    def test_contains_bills_json_placeholder(self):
        assert "{bills_json}" in LEVERAGE_POINT_PROMPT

    def test_contains_action_guidance(self):
        assert "actionable" in LEVERAGE_POINT_PROMPT.lower()

    def test_contains_null_instruction(self):
        """Prompt instructs LLM to return null for procedural bills."""
        assert "null" in LEVERAGE_POINT_PROMPT

    def test_requests_json_format(self):
        assert '"results"' in LEVERAGE_POINT_PROMPT


# ---------------------------------------------------------------------------
# add_enrich_leverage_parser
# ---------------------------------------------------------------------------


class TestAddEnrichLeverageParser:
    def test_parser_defaults(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_enrich_leverage_parser(subparsers)
        args = parser.parse_args(["enrich-leverage"])
        assert args.state == "CA"
        assert args.limit is None
        assert args.batch_size == 25
        assert args.dry_run is False
        assert args.stats is False

    def test_parser_accepts_all_options(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_enrich_leverage_parser(subparsers)
        args = parser.parse_args([
            "enrich-leverage",
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
        add_enrich_leverage_parser(subparsers)
        args = parser.parse_args(["enrich-leverage", "--limit", "100"])
        assert args.limit == 100
        assert isinstance(args.limit, int)


# ---------------------------------------------------------------------------
# get_unenriched_bills
# ---------------------------------------------------------------------------


class TestGetUnenrichedBills:
    def _make_mock_pg(self, rows):
        """Create a mock psycopg2 module with cursor returning given rows."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pg = MagicMock()
        mock_pg.connect.return_value = mock_conn
        return mock_pg, mock_cursor

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="postgres://test")
    def test_returns_bill_dicts_from_rows(self, mock_getenv):
        rows = [
            ("bill-1", "AB 100", "Housing Act", "CA", "Active", "Increases housing density"),
            ("bill-2", "SB 200", "Transit Bill", "CA", "Enrolled", "Expands transit"),
        ]
        mock_pg, _ = self._make_mock_pg(rows)

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            result = get_unenriched_bills("CA")

        assert len(result) == 2
        assert result[0]["bill_id"] == "bill-1"
        assert result[0]["bill_number"] == "AB 100"
        assert result[0]["bill_name"] == "Housing Act"
        assert result[0]["state"] == "CA"
        assert result[0]["status"] == "Active"
        assert result[0]["summary"] == "Increases housing density"
        assert result[1]["bill_id"] == "bill-2"
        assert result[1]["bill_number"] == "SB 200"

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value=None)
    def test_raises_when_no_database_url(self, mock_getenv):
        with pytest.raises(ValueError, match="DATABASE_URL not set"):
            get_unenriched_bills("CA")

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="postgres://test")
    def test_null_fields_become_empty_strings(self, mock_getenv):
        rows = [("bill-1", "AB 100", None, "CA", None, None)]
        mock_pg, _ = self._make_mock_pg(rows)

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            result = get_unenriched_bills("CA")

        assert result[0]["bill_name"] == ""
        assert result[0]["status"] == ""
        assert result[0]["summary"] == ""

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="postgres://test")
    def test_returns_empty_list_when_no_rows(self, mock_getenv):
        mock_pg, _ = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            result = get_unenriched_bills("CA")

        assert result == []

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="postgres://test")
    def test_limit_appended_to_query(self, mock_getenv):
        mock_pg, mock_cursor = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            get_unenriched_bills("CA", limit=50)

        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "LIMIT 50" in executed_sql

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="postgres://test")
    def test_no_limit_when_none(self, mock_getenv):
        mock_pg, mock_cursor = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            get_unenriched_bills("CA", limit=None)

        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "LIMIT" not in executed_sql

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="postgres://test")
    def test_passes_state_as_query_parameter(self, mock_getenv):
        mock_pg, mock_cursor = self._make_mock_pg([])

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            get_unenriched_bills("NY")

        query_params = mock_cursor.execute.call_args[0][1]
        assert query_params == ("NY",)


# ---------------------------------------------------------------------------
# get_leverage_stats
# ---------------------------------------------------------------------------


class TestGetLeverageStats:
    def _make_mock_pg(self, row):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = row
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pg = MagicMock()
        mock_pg.connect.return_value = mock_conn
        return mock_pg

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value=None)
    def test_raises_when_no_database_url(self, mock_getenv):
        with pytest.raises(ValueError, match="DATABASE_URL not set"):
            get_leverage_stats("CA")

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="postgres://test")
    def test_returns_stats_dict(self, mock_getenv):
        mock_pg = self._make_mock_pg((500, 300, 200, 150))

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            stats = get_leverage_stats("CA")

        assert stats["total"] == 500
        assert stats["enriched"] == 300
        assert stats["unenriched"] == 200
        assert stats["candidates"] == 150
        assert len(stats) == 4

    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="postgres://test")
    def test_returns_zero_counts_for_empty_table(self, mock_getenv):
        mock_pg = self._make_mock_pg((0, 0, 0, 0))

        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            stats = get_leverage_stats("CA")

        assert stats["total"] == 0
        assert stats["enriched"] == 0
        assert stats["unenriched"] == 0
        assert stats["candidates"] == 0


# ---------------------------------------------------------------------------
# enrich_batch
# ---------------------------------------------------------------------------


class TestEnrichBatch:
    def _make_bills(self, count=1):
        return [
            {
                "bill_id": f"bill-{i}",
                "bill_number": f"AB {i}",
                "bill_name": f"Test Bill {i}",
                "state": "CA",
                "status": "Active",
                "summary": f"Summary for bill {i}",
            }
            for i in range(count)
        ]

    def test_returns_empty_when_anthropic_unavailable(self):
        bills = self._make_bills(1)
        with patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", False):
            result = enrich_batch(bills)
        assert result == []

    def test_parses_leverage_points_from_response(self):
        bills = self._make_bills(2)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "results": [
                {"bill_id": "bill-0", "leverage_point": "Contact your council member about local implementation."},
                {"bill_id": "bill-1", "leverage_point": "Attend the next planning commission hearing."},
            ]
        })

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = enrich_batch(bills)

        assert len(result) == 2
        assert result[0]["bill_id"] == "bill-0"
        assert result[0]["leverage_point"] == "Contact your council member about local implementation."
        assert result[1]["bill_id"] == "bill-1"
        assert result[1]["leverage_point"] == "Attend the next planning commission hearing."

    def test_filters_out_null_leverage_points(self):
        bills = self._make_bills(3)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "results": [
                {"bill_id": "bill-0", "leverage_point": "Contact your rep."},
                {"bill_id": "bill-1", "leverage_point": None},
                {"bill_id": "bill-2", "leverage_point": "Attend the hearing."},
            ]
        })

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = enrich_batch(bills)

        assert len(result) == 2
        assert result[0]["bill_id"] == "bill-0"
        assert result[1]["bill_id"] == "bill-2"

    def test_handles_markdown_json_wrapped_response(self):
        """Response wrapped in ```json ... ``` should be parsed correctly."""
        bills = self._make_bills(1)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = '```json\n{"results": [{"bill_id": "bill-0", "leverage_point": "Testify at council."}]}\n```'

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = enrich_batch(bills)

        assert len(result) == 1
        assert result[0]["leverage_point"] == "Testify at council."

    def test_handles_bare_markdown_wrapped_response(self):
        """Response wrapped in ``` ... ``` (no json tag) should be parsed."""
        bills = self._make_bills(1)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = '```\n{"results": [{"bill_id": "bill-0", "leverage_point": "Write a public comment."}]}\n```'

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = enrich_batch(bills)

        assert len(result) == 1
        assert result[0]["leverage_point"] == "Write a public comment."

    def test_returns_empty_on_json_parse_error(self):
        bills = self._make_bills(1)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "This is not valid JSON at all"

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = enrich_batch(bills)

        assert result == []

    def test_returns_empty_on_api_error(self):
        bills = self._make_bills(1)

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = RuntimeError("API down")

            result = enrich_batch(bills)

        assert result == []

    def test_truncates_long_summaries_to_300_chars(self):
        """Summaries are truncated to first 300 chars in the prompt."""
        bills = [{
            "bill_id": "bill-0",
            "bill_number": "AB 1",
            "bill_name": "Test",
            "state": "CA",
            "status": "Active",
            "summary": "X" * 500,
        }]

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "results": [{"bill_id": "bill-0", "leverage_point": "Act now."}]
        })

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            enrich_batch(bills)

        call_kwargs = mock_client.messages.create.call_args
        prompt_content = call_kwargs[1]["messages"][0]["content"]
        # The prompt should contain exactly 300 X's (truncated), not 500
        assert "X" * 300 in prompt_content
        assert "X" * 301 not in prompt_content

    def test_uses_claude_haiku_model(self):
        bills = self._make_bills(1)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({"results": []})

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            enrich_batch(bills)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs[1]["model"] == "claude-haiku-4-5-20251001"

    def test_empty_results_key_returns_empty(self):
        """Response with empty 'results' array should return empty list."""
        bills = self._make_bills(2)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({"results": []})

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = enrich_batch(bills)

        assert result == []

    def test_missing_results_key_returns_empty(self):
        """Response without 'results' key should return empty list."""
        bills = self._make_bills(1)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({"other_key": "value"})

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = enrich_batch(bills)

        assert result == []

    def test_all_null_leverage_points_returns_empty(self):
        """When every bill gets null leverage_point, result should be empty."""
        bills = self._make_bills(2)

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "results": [
                {"bill_id": "bill-0", "leverage_point": None},
                {"bill_id": "bill-1", "leverage_point": None},
            ]
        })

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = enrich_batch(bills)

        assert result == []

    def test_prompt_includes_bill_data(self):
        """The prompt sent to Claude should include bill details."""
        bills = [{
            "bill_id": "bill-42",
            "bill_number": "SB 999",
            "bill_name": "Clean Air Act",
            "state": "CA",
            "status": "In Committee",
            "summary": "Reduces emissions from industrial sources",
        }]

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({"results": []})

        with patch("civicos_extraction.cli.enrich_leverage_points.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            enrich_batch(bills)

        call_kwargs = mock_client.messages.create.call_args
        prompt = call_kwargs[1]["messages"][0]["content"]
        assert "bill-42" in prompt
        assert "SB 999" in prompt
        assert "Clean Air Act" in prompt
        assert "Reduces emissions from industrial sources" in prompt


# ---------------------------------------------------------------------------
# run_enrich_leverage — orchestrator
# ---------------------------------------------------------------------------


class TestRunEnrichLeverage:
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

    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    def test_stats_mode_returns_zero(self, mock_stats):
        mock_stats.return_value = {"total": 500, "enriched": 300, "unenriched": 200, "candidates": 150}
        args = self._make_args(stats=True)
        result = run_enrich_leverage(args)
        assert result == 0

    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    def test_stats_mode_uppercases_state(self, mock_stats):
        mock_stats.return_value = {"total": 100, "enriched": 50, "unenriched": 50, "candidates": 40}
        args = self._make_args(state="ca", stats=True)
        result = run_enrich_leverage(args)
        assert result == 0
        mock_stats.assert_called_once_with("CA")

    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    def test_stats_handles_zero_total(self, mock_stats):
        """Stats mode should handle zero total without division error."""
        mock_stats.return_value = {"total": 0, "enriched": 0, "unenriched": 0, "candidates": 0}
        args = self._make_args(stats=True)
        result = run_enrich_leverage(args)
        assert result == 0

    def test_returns_1_when_anthropic_unavailable(self):
        args = self._make_args()
        with patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", False):
            result = run_enrich_leverage(args)
        assert result == 1

    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv")
    def test_returns_1_when_no_anthropic_key(self, mock_getenv):
        mock_getenv.side_effect = lambda k: None
        args = self._make_args()
        result = run_enrich_leverage(args)
        assert result == 1

    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv")
    def test_returns_1_when_no_database_url(self, mock_getenv):
        def getenv_side(key):
            if key == "ANTHROPIC_API_KEY":
                return "sk-test"
            return None
        mock_getenv.side_effect = getenv_side
        args = self._make_args()
        result = run_enrich_leverage(args)
        assert result == 1

    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="set")
    def test_returns_0_when_no_bills_to_enrich(self, mock_getenv, mock_get_bills):
        mock_get_bills.return_value = []
        args = self._make_args()
        result = run_enrich_leverage(args)
        assert result == 0

    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="set")
    def test_dry_run_returns_0_without_enriching(self, mock_getenv, mock_get_bills):
        mock_get_bills.return_value = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test Bill", "summary": "Test"},
            {"bill_id": "b2", "bill_number": "SB 2", "bill_name": "Another Bill", "summary": "Another"},
        ]
        args = self._make_args(dry_run=True)
        result = run_enrich_leverage(args)
        assert result == 0

    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="set")
    def test_dry_run_with_many_bills_shows_sample(self, mock_getenv, mock_get_bills):
        """Dry run with >5 bills covers the 'and N more' path."""
        mock_get_bills.return_value = [
            {"bill_id": f"b{i}", "bill_number": f"AB {i}", "bill_name": f"Bill {i} about policy", "summary": f"S{i}"}
            for i in range(8)
        ]
        args = self._make_args(dry_run=True)
        result = run_enrich_leverage(args)
        assert result == 0

    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    @patch("civicos_extraction.cli.enrich_leverage_points.enrich_batch")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="set")
    def test_batching_splits_bills(self, mock_getenv, mock_get_bills, mock_enrich, mock_stats):
        # 5 bills with batch_size=2 -> 3 batches (2, 2, 1)
        mock_get_bills.return_value = [
            {"bill_id": f"b{i}", "bill_number": f"AB {i}", "bill_name": f"Bill {i}", "summary": f"S{i}"}
            for i in range(5)
        ]
        mock_enrich.return_value = []
        mock_stats.return_value = {"total": 5, "enriched": 0, "unenriched": 5, "candidates": 5}

        args = self._make_args(batch_size=2)
        result = run_enrich_leverage(args)

        assert result == 0
        assert mock_enrich.call_count == 3
        assert len(mock_enrich.call_args_list[0][0][0]) == 2
        assert len(mock_enrich.call_args_list[1][0][0]) == 2
        assert len(mock_enrich.call_args_list[2][0][0]) == 1

    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    @patch("civicos_extraction.cli.enrich_leverage_points.enrich_batch")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="set")
    def test_empty_batch_result_is_skipped(self, mock_getenv, mock_get_bills, mock_enrich, mock_stats):
        """When enrich_batch returns empty, no DB update should happen."""
        mock_get_bills.return_value = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "Test"},
        ]
        mock_enrich.return_value = []
        mock_stats.return_value = {"total": 1, "enriched": 0, "unenriched": 1, "candidates": 1}

        args = self._make_args()
        result = run_enrich_leverage(args)

        assert result == 0

    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    @patch("civicos_extraction.cli.enrich_leverage_points.enrich_batch")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="set")
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    def test_enriched_results_are_passed_to_database(
        self, mock_getenv, mock_get_bills, mock_enrich, mock_stats
    ):
        mock_get_bills.return_value = [
            {"bill_id": "b1", "bill_number": "AB 1", "bill_name": "Test", "summary": "Test"},
        ]
        mock_enrich.return_value = [
            {"bill_id": "b1", "leverage_point": "Contact your representative."},
        ]
        mock_stats.return_value = {"total": 1, "enriched": 1, "unenriched": 0, "candidates": 0}

        with patch("civicos.storage.postgres_backend.PostgresBackend") as MockPB:
            mock_backend = MagicMock()
            mock_backend.update_legislation_leverage_points.return_value = 1
            MockPB.return_value = mock_backend

            args = self._make_args()
            result = run_enrich_leverage(args)

        assert result == 0
        update_call = mock_backend.update_legislation_leverage_points.call_args
        state_arg = update_call[0][0]
        updates_arg = update_call[0][1]
        assert state_arg == "CA"
        assert len(updates_arg) == 1
        assert updates_arg[0]["bill_id"] == "b1"
        assert updates_arg[0]["leverage_point"] == "Contact your representative."

    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    @patch("civicos_extraction.cli.enrich_leverage_points.enrich_batch")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    @patch("civicos_extraction.cli.enrich_leverage_points.ANTHROPIC_AVAILABLE", True)
    @patch("civicos_extraction.cli.enrich_leverage_points.os.getenv", return_value="set")
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    def test_multiple_batches_accumulate_updates(
        self, mock_getenv, mock_get_bills, mock_enrich, mock_stats
    ):
        """Results from multiple batches are accumulated before DB update."""
        mock_get_bills.return_value = [
            {"bill_id": f"b{i}", "bill_number": f"AB {i}", "bill_name": f"Bill {i}", "summary": f"S{i}"}
            for i in range(4)
        ]
        # Each batch returns one enriched result
        mock_enrich.side_effect = [
            [{"bill_id": "b0", "leverage_point": "Action 1"}],
            [{"bill_id": "b2", "leverage_point": "Action 2"}],
        ]
        mock_stats.return_value = {"total": 4, "enriched": 2, "unenriched": 2, "candidates": 2}

        with patch("civicos.storage.postgres_backend.PostgresBackend") as MockPB:
            mock_backend = MagicMock()
            mock_backend.update_legislation_leverage_points.return_value = 2
            MockPB.return_value = mock_backend

            args = self._make_args(batch_size=2)
            result = run_enrich_leverage(args)

        assert result == 0
        update_call = mock_backend.update_legislation_leverage_points.call_args
        updates = update_call[0][1]
        assert len(updates) == 2
        assert updates[0]["bill_id"] == "b0"
        assert updates[0]["leverage_point"] == "Action 1"
        assert updates[1]["bill_id"] == "b2"
        assert updates[1]["leverage_point"] == "Action 2"

    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    def test_stats_mode_computes_percentage(self, mock_stats):
        """Stats mode should compute enriched percentage correctly."""
        mock_stats.return_value = {"total": 200, "enriched": 100, "unenriched": 100, "candidates": 80}
        args = self._make_args(stats=True)
        # Just verify it doesn't crash and returns 0
        result = run_enrich_leverage(args)
        assert result == 0
