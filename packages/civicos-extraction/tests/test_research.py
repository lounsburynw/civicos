"""
Tests for civicos_extraction.cli.research module.

Tests the research CLI: argument parser setup, command dispatch,
single-query flow, ensemble flow, and ETL cost recording.
External dependencies (search providers, storage backends, LLMs) are mocked
at the I/O boundary; all CLI logic runs for real.
"""

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.cli.research import (
    add_research_parser,
    run_research,
    run_municipal_funding,
    run_municipal_funding_ensemble,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_search_result(content="Test response", citations=None, cost=0.05):
    """Create a mock SearchResult-like object."""
    sr = MagicMock()
    sr.content = content
    sr.citations = citations or ["https://example.com/source1"]
    sr.model = "test-model"
    sr.cost = cost
    return sr


def _make_parsed_data():
    """Create a mock MunicipalFundingPrograms-like object."""
    program = MagicMock()
    program.program_name = "Housing Trust Fund"
    program.description = "Provides funding for affordable housing development"

    measure = MagicMock()
    measure.measure_name = "Measure P"
    measure.status = "passed"

    data = MagicMock()
    data.programs = {"htf-001": program}
    data.ballot_measures = {"measure-p": measure}
    return data


def _make_query_result(query="test query", template_key="htf", cost=0.03):
    """Create a mock QueryResult."""
    qr = MagicMock()
    qr.query = query
    qr.template_key = template_key
    qr.program_type = "housing_trust_fund"
    qr.response = _make_search_result(cost=cost)
    return qr


def _make_args(**overrides):
    """Create a Namespace with typical municipal-funding args."""
    defaults = dict(
        research_command="municipal-funding",
        municipality="San Rafael",
        state="California",
        topic="housing",
        provider=None,
        ensemble=False,
        max_workers=3,
        delay=1.0,
        max_priority=2,
        output=None,
        no_save=True,
        raw_only=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Parser configuration tests
# ---------------------------------------------------------------------------


class TestAddResearchParser:
    def test_parser_registers_research_subcommand(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_research_parser(subparsers)
        # Should be able to parse "research municipal-funding San Rafael California"
        args = parser.parse_args(
            ["research", "municipal-funding", "San Rafael", "California"]
        )
        assert args.municipality == "San Rafael"
        assert args.state == "California"

    def test_parser_defaults(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_research_parser(subparsers)
        args = parser.parse_args(
            ["research", "municipal-funding", "Berkeley", "California"]
        )
        assert args.topic == "housing"
        assert args.provider is None
        assert args.ensemble is False
        assert args.max_workers == 3
        assert args.delay == 1.0
        assert args.max_priority == 2
        assert args.output is None
        assert args.no_save is False
        assert args.raw_only is False

    def test_parser_topic_choices(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_research_parser(subparsers)
        args = parser.parse_args(
            ["research", "municipal-funding", "X", "Y", "--topic", "transportation"]
        )
        assert args.topic == "transportation"

    def test_parser_rejects_invalid_topic(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_research_parser(subparsers)
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["research", "municipal-funding", "X", "Y", "--topic", "invalid"]
            )

    def test_parser_ensemble_flag(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_research_parser(subparsers)
        args = parser.parse_args(
            ["research", "municipal-funding", "X", "Y", "--ensemble"]
        )
        assert args.ensemble is True

    def test_parser_max_priority_choices(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_research_parser(subparsers)
        args = parser.parse_args(
            ["research", "municipal-funding", "X", "Y", "--max-priority", "3"]
        )
        assert args.max_priority == 3

    def test_parser_rejects_invalid_max_priority(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_research_parser(subparsers)
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["research", "municipal-funding", "X", "Y", "--max-priority", "5"]
            )

    def test_parser_output_short_flag(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_research_parser(subparsers)
        args = parser.parse_args(
            ["research", "municipal-funding", "X", "Y", "-o", "/tmp/out.json"]
        )
        assert args.output == "/tmp/out.json"


# ---------------------------------------------------------------------------
# run_research dispatch tests
# ---------------------------------------------------------------------------


class TestRunResearch:
    def test_no_command_returns_1(self, capsys):
        args = argparse.Namespace(research_command=None)
        result = run_research(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "No research command specified" in captured.err
        assert "municipal-funding" in captured.err

    def test_unknown_command_returns_1(self):
        args = argparse.Namespace(research_command="unknown-thing")
        result = run_research(args)
        assert result == 1

    @patch("civicos_extraction.cli.research.run_municipal_funding")
    def test_dispatches_single_query(self, mock_single):
        mock_single.return_value = 0
        args = _make_args(ensemble=False)
        result = run_research(args)
        assert result == 0
        mock_single.assert_called_once_with(args)

    @patch("civicos_extraction.cli.research.run_municipal_funding_ensemble")
    def test_dispatches_ensemble(self, mock_ensemble):
        mock_ensemble.return_value = 0
        args = _make_args(ensemble=True)
        result = run_research(args)
        assert result == 0
        mock_ensemble.assert_called_once_with(args)


# ---------------------------------------------------------------------------
# run_municipal_funding (single query) tests
# ---------------------------------------------------------------------------


class TestRunMunicipalFunding:
    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_single_query_full_flow(self, capsys):
        """Test the full single-query flow with mocked provider and researcher."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        search_result = _make_search_result(
            content="San Rafael Housing Trust Fund provides $2M annually",
            citations=["https://sanrafael.gov/htf", "https://ca.gov/housing"],
            cost=0.048,
        )

        mock_research_result = MagicMock()
        mock_research_result.raw_response = search_result
        mock_research_result.parsed_data = None
        mock_research_result.audit_file = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_research_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(no_save=True)
            exit_code = run_municipal_funding(args)

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "MUNICIPAL FUNDING RESEARCH (single query)" in captured.out
        assert "San Rafael" in captured.out
        assert "California" in captured.out
        assert "housing" in captured.out
        assert "RAW RESPONSE" in captured.out
        assert "$2M annually" in captured.out
        assert "CITATIONS (2 sources)" in captured.out
        assert "METADATA" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_single_query_with_parsed_data_saves_structured(self, capsys):
        """When parsed_data is present and not raw_only, shows programs."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        parsed = _make_parsed_data()

        mock_result = MagicMock()
        mock_result.raw_response = _make_search_result(cost=0.05)
        mock_result.parsed_data = parsed
        mock_result.audit_file = "/tmp/audit.json"

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_result
        mock_researcher_instance.save_structured_data.return_value = "/tmp/output.json"
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(no_save=False, raw_only=False)
            exit_code = run_municipal_funding(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Structured data saved to: /tmp/output.json" in captured.out
        assert "Programs found:" in captured.out
        assert "htf-001" in captured.out
        assert "Housing Trust Fund" in captured.out
        assert "Ballot measures found:" in captured.out
        assert "Measure P" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_single_query_raw_only_skips_save(self, capsys):
        """--raw-only prevents saving structured data even when parsed_data exists."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_result = MagicMock()
        mock_result.raw_response = _make_search_result(cost=0.0)
        mock_result.parsed_data = _make_parsed_data()
        mock_result.audit_file = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(raw_only=True, no_save=False)
            exit_code = run_municipal_funding(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Structured data saved" not in captured.out
        mock_researcher_instance.save_structured_data.assert_not_called()

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_single_query_null_parsed_data_shows_warning(self, capsys):
        """When parsed_data is None, shows parsing incomplete warning."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_result = MagicMock()
        mock_result.raw_response = _make_search_result(cost=0.01)
        mock_result.parsed_data = None
        mock_result.audit_file = "/tmp/audit.json"

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(no_save=False, raw_only=False)
            exit_code = run_municipal_funding(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Parsing incomplete" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_single_query_with_explicit_provider(self, capsys):
        """Passing --provider uses that provider name explicitly."""
        mock_provider = MagicMock()
        mock_provider.name = "custom-provider"

        mock_result = MagicMock()
        mock_result.raw_response = _make_search_result(cost=0.0)
        mock_result.parsed_data = None
        mock_result.audit_file = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ) as mock_gp, patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(provider="custom-provider")
            exit_code = run_municipal_funding(args)

        assert exit_code == 0
        # get_provider should have been called with the explicit provider name
        mock_gp.assert_called_once_with("custom-provider")
        captured = capsys.readouterr()
        assert "custom-provider" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_single_query_no_provider_uses_default(self, capsys):
        """When --provider is None, get_provider is called with no arguments."""
        mock_provider = MagicMock()
        mock_provider.name = "default-provider"

        mock_result = MagicMock()
        mock_result.raw_response = _make_search_result(cost=0.0)
        mock_result.parsed_data = None
        mock_result.audit_file = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ) as mock_gp, patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(provider=None)
            exit_code = run_municipal_funding(args)

        assert exit_code == 0
        mock_gp.assert_called_once_with()

    def test_single_query_import_error_returns_1(self, capsys):
        """ImportError in lazy imports returns 1 with helpful message."""
        with patch.dict("sys.modules", {"civicos_extraction.research": None}):
            args = _make_args()
            exit_code = run_municipal_funding(args)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Missing dependency" in captured.err

    def test_single_query_runtime_error_returns_1(self, capsys):
        """Runtime exceptions return 1 with error message."""
        mock_provider = MagicMock()
        mock_provider.name = "failing-provider"

        with patch(
            "civicos_extraction.research.providers.get_provider",
            side_effect=RuntimeError("API key missing"),
        ):
            args = _make_args()
            exit_code = run_municipal_funding(args)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "API key missing" in captured.err

    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"}, clear=False)
    def test_single_query_records_etl_cost(self, capsys):
        """When cost > 0 and DATABASE_URL set, records ETL cost."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_result = MagicMock()
        mock_result.raw_response = _make_search_result(cost=0.12)
        mock_result.parsed_data = None
        mock_result.audit_file = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_result
        mock_researcher_cls.return_value = mock_researcher_instance

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.store_etl_cost.return_value = 42

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ), patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            args = _make_args(no_save=True)
            exit_code = run_municipal_funding(args)

        assert exit_code == 0
        mock_backend.store_etl_cost.assert_called_once()
        call_kwargs = mock_backend.store_etl_cost.call_args.kwargs
        assert call_kwargs["pipeline"] == "research"
        assert call_kwargs["jurisdiction_id"] == "city-san-rafael"
        assert call_kwargs["items_processed"] == 1
        assert call_kwargs["cost_usd"] == 0.12
        assert "Single research" in call_kwargs["notes"]
        assert "housing" in call_kwargs["notes"]

        captured = capsys.readouterr()
        assert "ETL cost recorded (id=42)" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_single_query_zero_cost_skips_etl_record(self, capsys):
        """When cost is 0, doesn't attempt to record ETL cost."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_result = MagicMock()
        mock_result.raw_response = _make_search_result(cost=0.0)
        mock_result.parsed_data = None
        mock_result.audit_file = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(no_save=True)
            exit_code = run_municipal_funding(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "ETL cost recorded" not in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_jurisdiction_id_derivation(self, capsys):
        """Municipality name converts to jurisdiction_id correctly."""
        mock_provider = MagicMock()
        mock_provider.name = "mock"

        mock_result = MagicMock()
        mock_result.raw_response = _make_search_result(cost=0.01)
        mock_result.parsed_data = None
        mock_result.audit_file = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance.research.return_value = mock_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            # Use a multi-word municipality to verify slug generation
            args = _make_args(municipality="Mill Valley")
            exit_code = run_municipal_funding(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Mill Valley" in captured.out


# ---------------------------------------------------------------------------
# run_municipal_funding_ensemble tests
# ---------------------------------------------------------------------------


class TestRunMunicipalFundingEnsemble:
    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_returns_0_on_success(self, capsys):
        """Ensemble flow runs multiple queries and returns 0."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        qr1 = _make_query_result("query about HTFs", "htf", 0.03)
        qr2 = _make_query_result("query about IH", "inclusionary", 0.04)

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = [qr1, qr2]
        mock_ensemble_result.total_cost = 0.07
        mock_ensemble_result.audit_file = "/tmp/ensemble_audit.json"
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, no_save=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "MUNICIPAL FUNDING RESEARCH (ensemble mode)" in captured.out
        assert "San Rafael" in captured.out
        assert "QUERY RESULTS (2 queries)" in captured.out
        assert "Total queries: 2" in captured.out
        assert "$0.0700" in captured.out
        assert "ensemble_audit.json" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_with_known_programs_shows_config(self, capsys):
        """Municipality config with known programs is displayed."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = ["Housing Trust Fund", "Measure H"]
        mock_config.custom_queries = ["custom query 1"]
        mock_config.query_overrides = {"htf": "override"}

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = []
        mock_ensemble_result.total_cost = 0.0
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, no_save=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Loaded municipality config" in captured.out
        assert "Known programs: 2" in captured.out
        assert "Custom queries: 1" in captured.out
        assert "Query overrides: 1" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_empty_config_no_config_message(self, capsys):
        """Empty config (no known programs/custom queries) doesn't show config section."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = []
        mock_ensemble_result.total_cost = 0.0
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, no_save=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Loaded municipality config" not in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_with_merged_data_saves_output(self, capsys):
        """When merged_data is present, saves and displays programs."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        merged = _make_parsed_data()

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = [_make_query_result()]
        mock_ensemble_result.total_cost = 0.03
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = merged

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_instance.save_ensemble_data.return_value = "/tmp/merged.json"
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, no_save=False, raw_only=False)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Merged data saved to: /tmp/merged.json" in captured.out
        assert "Programs found:" in captured.out
        assert "htf-001" in captured.out
        assert "Housing Trust Fund" in captured.out
        assert "Ballot measures found:" in captured.out
        assert "Measure P" in captured.out
        assert "passed" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_raw_only_skips_save(self, capsys):
        """--raw-only prevents saving merged data."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = [_make_query_result()]
        mock_ensemble_result.total_cost = 0.03
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = _make_parsed_data()

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, raw_only=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Merged data saved" not in captured.out
        mock_researcher_instance.save_ensemble_data.assert_not_called()

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_null_merged_data_shows_warning(self, capsys):
        """When merged_data is None, shows merging incomplete warning."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = [_make_query_result()]
        mock_ensemble_result.total_cost = 0.03
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, no_save=False, raw_only=False)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Merging incomplete" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"}, clear=False)
    def test_ensemble_records_etl_cost(self, capsys):
        """Ensemble records ETL cost with correct query count."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        qr1 = _make_query_result(cost=0.03)
        qr2 = _make_query_result(cost=0.04)
        qr3 = _make_query_result(cost=0.05)

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = [qr1, qr2, qr3]
        mock_ensemble_result.total_cost = 0.12
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.store_etl_cost.return_value = 99

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ), patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            args = _make_args(ensemble=True, no_save=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        mock_backend.store_etl_cost.assert_called_once()
        call_kwargs = mock_backend.store_etl_cost.call_args.kwargs
        assert call_kwargs["pipeline"] == "research"
        assert call_kwargs["jurisdiction_id"] == "city-san-rafael"
        assert call_kwargs["items_processed"] == 3
        assert call_kwargs["cost_usd"] == 0.12
        assert "Ensemble research" in call_kwargs["notes"]
        assert "3 queries" in call_kwargs["notes"]

        captured = capsys.readouterr()
        assert "ETL cost recorded (id=99)" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_zero_queries_skips_etl_record(self, capsys):
        """No queries means no ETL cost recording."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = []
        mock_ensemble_result.total_cost = 0.0
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, no_save=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "ETL cost recorded" not in captured.out

    def test_ensemble_import_error_returns_1(self, capsys):
        """ImportError returns 1 with helpful install message."""
        with patch.dict("sys.modules", {"civicos_extraction.research": None}):
            args = _make_args(ensemble=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Missing dependency" in captured.err
        assert "pyyaml" in captured.err

    def test_ensemble_runtime_error_returns_1(self, capsys):
        """Runtime exceptions return 1 with error message."""
        mock_provider = MagicMock()
        mock_provider.name = "failing-provider"

        with patch(
            "civicos_extraction.research.providers.get_provider",
            side_effect=RuntimeError("Network timeout"),
        ):
            args = _make_args(ensemble=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Network timeout" in captured.err

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_deduplicates_citations(self, capsys):
        """Citations from multiple queries are deduplicated."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        # Two queries with overlapping citations
        qr1 = _make_query_result()
        qr1.response.citations = ["https://a.com", "https://b.com"]
        qr2 = _make_query_result()
        qr2.response.citations = ["https://b.com", "https://c.com"]

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = [qr1, qr2]
        mock_ensemble_result.total_cost = 0.06
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, no_save=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        # Should show 3 unique sources, not 4
        assert "3 unique sources" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_displays_query_previews(self, capsys):
        """Each query result shows truncated query and preview."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        qr = _make_query_result("What housing trust funds exist in San Rafael?", "htf", 0.05)
        qr.response.content = "San Rafael operates several housing programs..." + "x" * 300

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = [qr]
        mock_ensemble_result.total_cost = 0.05
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(ensemble=True, no_save=True)
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Query 1: htf" in captured.out
        assert "$0.0500" in captured.out
        assert "San Rafael operates" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)
    def test_ensemble_passes_config_args_to_research(self, capsys):
        """max_workers, delay, max_priority are forwarded to research_ensemble."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = []
        mock_ensemble_result.total_cost = 0.0
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ):
            args = _make_args(
                ensemble=True,
                max_workers=5,
                delay=2.5,
                max_priority=3,
                no_save=False,
            )
            exit_code = run_municipal_funding_ensemble(args)

        assert exit_code == 0
        mock_researcher_instance.research_ensemble.assert_called_once()
        call_kwargs = mock_researcher_instance.research_ensemble.call_args.kwargs
        assert call_kwargs["max_workers"] == 5
        assert call_kwargs["delay_between_queries"] == 2.5
        assert call_kwargs["max_priority"] == 3
        assert call_kwargs["save_audit"] is True  # no_save=False → save_audit=True

        captured = capsys.readouterr()
        assert "Max workers: 5" in captured.out
        assert "Query delay: 2.5s" in captured.out
        assert "Max priority: 3" in captured.out

    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"}, clear=False)
    def test_ensemble_etl_cost_import_error_graceful(self, capsys):
        """ETL cost recording failure doesn't crash the ensemble flow."""
        mock_provider = MagicMock()
        mock_provider.name = "mock-perplexity"

        mock_config = MagicMock()
        mock_config.known_programs = []
        mock_config.custom_queries = []
        mock_config.query_overrides = {}

        mock_ensemble_result = MagicMock()
        mock_ensemble_result.query_results = [_make_query_result(cost=0.05)]
        mock_ensemble_result.total_cost = 0.05
        mock_ensemble_result.audit_file = None
        mock_ensemble_result.merged_data = None

        mock_researcher_cls = MagicMock()
        mock_researcher_instance = MagicMock()
        mock_researcher_instance._load_municipality_config.return_value = mock_config
        mock_researcher_instance.research_ensemble.return_value = mock_ensemble_result
        mock_researcher_cls.return_value = mock_researcher_instance

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.store_etl_cost.side_effect = Exception("DB connection lost")

        with patch(
            "civicos_extraction.research.providers.get_provider",
            return_value=mock_provider,
        ), patch(
            "civicos_extraction.research.MunicipalFundingResearcher",
            mock_researcher_cls,
        ), patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            args = _make_args(ensemble=True, no_save=True)
            exit_code = run_municipal_funding_ensemble(args)

        # Should still succeed — ETL cost recording is non-critical
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "ETL cost recorded" not in captured.out
