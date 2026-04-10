"""Tests for municipal code CLI command.

Tests the dispatch logic, stats display, config validation,
and fetch-and-store pipeline — mocking only external dependencies
(MunicipalCodeCorpus, PostgresBackend, os.environ).
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.cli.municipal_code import (
    add_municipal_code_parser,
    fetch_and_store_municipal_code,
    run_municipal_code,
    show_stats,
    validate_config,
)

# Lazy imports in the source live at these paths — patch here, not on the CLI module.
_CORPUS_PATH = "civicos._internal.legal.corpus.municipal.MunicipalCodeCorpus"
_IS_AMLEGAL_PATH = "civicos._internal.legal.corpus.municipal._is_amlegal_jurisdiction"
_PG_BACKEND_PATH = "civicos.storage.postgres_backend.PostgresBackend"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


@dataclass
class FakeSection:
    """Mimics the dataclass returned by MunicipalCodeCorpus.stream_sections()."""
    section_number: str
    heading: str
    text: str
    citation: str


def _make_sections(n: int) -> list:
    """Create n FakeSection objects for testing."""
    return [
        FakeSection(
            section_number=f"{i}.01",
            heading=f"Section {i}",
            text=f"Content of section {i} for municipal code.",
            citation=f"Mun. Code § {i}.01",
        )
        for i in range(1, n + 1)
    ]


def _make_args(**overrides) -> argparse.Namespace:
    """Build an argparse.Namespace mimicking CLI args."""
    defaults = dict(
        jurisdiction="city-san-rafael",
        cloud=False,
        dry_run=False,
        stats=False,
        limit=None,
        output_dir="data/municipal_code",
        verbose=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture(autouse=True)
def _clean_database_url(monkeypatch):
    """Remove DATABASE_URL so cloud_mode defaults to args.cloud only."""
    monkeypatch.delenv("DATABASE_URL", raising=False)


# ──────────────────────────────────────────────
# add_municipal_code_parser
# ──────────────────────────────────────────────


class TestAddMunicipalCodeParser:
    def test_registers_subcommand_with_required_jurisdiction(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        args = parser.parse_args(["municipal-code", "--jurisdiction", "city-test"])
        assert args.jurisdiction == "city-test"

    def test_defaults_cloud_to_false(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        args = parser.parse_args(["municipal-code", "--jurisdiction", "city-test"])
        assert args.cloud is False

    def test_cloud_flag_sets_true(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        args = parser.parse_args(["municipal-code", "--jurisdiction", "city-test", "--cloud"])
        assert args.cloud is True

    def test_dry_run_flag_sets_true(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        args = parser.parse_args(["municipal-code", "--jurisdiction", "city-test", "--dry-run"])
        assert args.dry_run is True

    def test_limit_parses_as_int(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        args = parser.parse_args(["municipal-code", "--jurisdiction", "city-test", "--limit", "50"])
        assert args.limit == 50

    def test_limit_defaults_to_none(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        args = parser.parse_args(["municipal-code", "--jurisdiction", "city-test"])
        assert args.limit is None

    def test_output_dir_default(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        args = parser.parse_args(["municipal-code", "--jurisdiction", "city-test"])
        assert args.output_dir == "data/municipal_code"

    def test_output_dir_custom(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        args = parser.parse_args([
            "municipal-code", "--jurisdiction", "city-test",
            "--output-dir", "/tmp/out",
        ])
        assert args.output_dir == "/tmp/out"

    def test_missing_jurisdiction_raises_system_exit(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_municipal_code_parser(subparsers)

        with pytest.raises(SystemExit):
            parser.parse_args(["municipal-code"])


# ──────────────────────────────────────────────
# run_municipal_code dispatch
# ──────────────────────────────────────────────


class TestRunMunicipalCodeDispatch:
    @patch("civicos_extraction.cli.municipal_code.show_stats", return_value=0)
    def test_stats_mode_dispatches_to_show_stats(self, mock_show_stats):
        args = _make_args(stats=True)
        result = run_municipal_code(args)

        assert result == 0
        # cloud_mode = False or None = None (falsy)
        mock_show_stats.assert_called_once_with("city-san-rafael", None)

    @patch("civicos_extraction.cli.municipal_code.validate_config", return_value=0)
    def test_dry_run_dispatches_to_validate_config(self, mock_validate):
        args = _make_args(dry_run=True)
        result = run_municipal_code(args)

        assert result == 0
        mock_validate.assert_called_once_with("city-san-rafael")

    @patch("civicos_extraction.cli.municipal_code.fetch_and_store_municipal_code", return_value=0)
    def test_normal_mode_dispatches_to_fetch_and_store(self, mock_fetch):
        args = _make_args()
        result = run_municipal_code(args)

        assert result == 0
        # cloud_mode = False or None = None (falsy)
        mock_fetch.assert_called_once_with(
            jurisdiction_id="city-san-rafael",
            cloud=None,
            output_dir="data/municipal_code",
            limit=None,
        )

    @patch("civicos_extraction.cli.municipal_code.fetch_and_store_municipal_code", return_value=0)
    def test_cloud_flag_passes_truthy_cloud(self, mock_fetch):
        args = _make_args(cloud=True)
        result = run_municipal_code(args)

        assert result == 0
        assert mock_fetch.call_args.kwargs["cloud"] is True

    @patch("civicos_extraction.cli.municipal_code.fetch_and_store_municipal_code", return_value=0)
    def test_database_url_env_enables_cloud_mode(self, mock_fetch, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        args = _make_args(cloud=False)
        run_municipal_code(args)

        # cloud_mode = args.cloud or os.environ.get("DATABASE_URL")
        assert mock_fetch.call_args.kwargs["cloud"] == "postgres://test"

    @patch("civicos_extraction.cli.municipal_code.show_stats", return_value=0)
    def test_stats_takes_precedence_over_dry_run(self, mock_show_stats):
        args = _make_args(stats=True, dry_run=True)
        result = run_municipal_code(args)

        assert result == 0
        mock_show_stats.assert_called_once()

    @patch("civicos_extraction.cli.municipal_code.fetch_and_store_municipal_code", return_value=0)
    def test_limit_is_forwarded(self, mock_fetch):
        args = _make_args(limit=25)
        run_municipal_code(args)

        assert mock_fetch.call_args.kwargs["limit"] == 25

    @patch("civicos_extraction.cli.municipal_code.fetch_and_store_municipal_code", return_value=1)
    def test_returns_error_code_from_fetch(self, mock_fetch):
        args = _make_args()
        result = run_municipal_code(args)

        assert result == 1


# ──────────────────────────────────────────────
# show_stats
# ──────────────────────────────────────────────


class TestShowStats:
    def test_cloud_mode_without_database_url_returns_1(self):
        result = show_stats("city-test", cloud=True)
        assert result == 1

    @patch(_PG_BACKEND_PATH)
    def test_cloud_mode_returns_0_with_valid_count(self, MockBackend, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        mock_backend = MagicMock()
        MockBackend.return_value = mock_backend
        mock_backend.get_municipal_code_count.return_value = 500

        result = show_stats("city-san-rafael", cloud=True)

        assert result == 0
        mock_backend.get_municipal_code_count.assert_called_once_with("city-san-rafael")

    @patch(_PG_BACKEND_PATH)
    def test_cloud_mode_returns_1_on_backend_error(self, MockBackend, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        MockBackend.side_effect = Exception("Connection refused")

        result = show_stats("city-test", cloud=True)

        assert result == 1

    def test_local_mode_returns_0(self):
        result = show_stats("city-test", cloud=False)
        assert result == 0


# ──────────────────────────────────────────────
# validate_config
# ──────────────────────────────────────────────


class TestValidateConfig:
    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_returns_0_for_valid_municode_jurisdiction(self, MockCorpus, _):
        mock_corpus = MagicMock()
        mock_corpus.JURISDICTION_MAP = {"city-test": {"state": "CA", "name": "Test City"}}
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = validate_config("city-test")

        assert result == 0
        MockCorpus.for_jurisdiction.assert_called_once_with("city-test")

    @patch(_IS_AMLEGAL_PATH, return_value=True)
    @patch(_CORPUS_PATH)
    def test_returns_0_for_amlegal_jurisdiction(self, MockCorpus, _):
        MockCorpus.for_jurisdiction.return_value = MagicMock()

        result = validate_config("city-sacramento")

        assert result == 0

    @patch(_IS_AMLEGAL_PATH)
    def test_returns_1_when_corpus_init_fails(self, mock_is_amlegal):
        mock_is_amlegal.side_effect = Exception("Unknown jurisdiction")

        result = validate_config("city-nonexistent")

        assert result == 1

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_returns_0_even_without_database_url(self, MockCorpus, _):
        MockCorpus.for_jurisdiction.return_value = MagicMock(JURISDICTION_MAP={})
        result = validate_config("city-test")
        assert result == 0


# ──────────────────────────────────────────────
# fetch_and_store_municipal_code
# ──────────────────────────────────────────────


class TestFetchAndStoreMunicipalCode:

    # --- Corpus initialization ---

    @patch(_CORPUS_PATH)
    def test_returns_1_when_corpus_init_fails(self, MockCorpus):
        MockCorpus.for_jurisdiction.side_effect = Exception("No config found")

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-bad",
            cloud=False,
            output_dir="/tmp/test_out",
        )

        assert result == 1

    # --- Streaming sections ---

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_returns_1_when_no_sections_fetched(self, MockCorpus, _):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter([])
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-empty",
            cloud=False,
            output_dir="/tmp/test_out",
        )

        assert result == 1

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_limit_stops_at_specified_count(self, MockCorpus, _, tmp_path):
        sections = _make_sections(10)
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(sections)
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir=str(tmp_path),
            limit=3,
        )

        assert result == 0
        output_file = tmp_path / "municipal_code_city_test.json"
        data = json.loads(output_file.read_text())
        assert data["count"] == 3
        assert len(data["sections"]) == 3

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_partial_fetch_on_error_continues_with_fetched(self, MockCorpus, _, tmp_path):
        def _stream_then_fail():
            yield from _make_sections(2)
            raise ConnectionError("Network error")

        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = _stream_then_fail()
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir=str(tmp_path),
        )

        assert result == 0
        data = json.loads((tmp_path / "municipal_code_city_test.json").read_text())
        assert data["count"] == 2
        assert len(data["sections"]) == 2

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_error_with_zero_fetched_returns_1(self, MockCorpus, _):
        def _immediate_fail():
            raise ConnectionError("Network error")
            yield  # pragma: no cover — makes this a generator

        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = _immediate_fail()
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir="/tmp/test_out",
        )

        assert result == 1

    # --- Local JSON storage ---

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_local_mode_writes_json_with_correct_structure(self, MockCorpus, _, tmp_path):
        sections = _make_sections(3)
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(sections)
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-san-rafael",
            cloud=False,
            output_dir=str(tmp_path),
        )

        assert result == 0
        output_file = tmp_path / "municipal_code_city_san_rafael.json"
        data = json.loads(output_file.read_text())
        assert data["jurisdiction_id"] == "city-san-rafael"
        assert data["count"] == 3
        assert len(data["sections"]) == 3
        first = data["sections"][0]
        assert first["section_number"] == "1.01"
        assert first["heading"] == "Section 1"
        assert first["text"] == "Content of section 1 for municipal code."
        assert first["citation"] == "Mun. Code § 1.01"

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_local_mode_adds_municode_source_tag(self, MockCorpus, _, tmp_path):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(1))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir=str(tmp_path),
        )

        data = json.loads((tmp_path / "municipal_code_city_test.json").read_text())
        assert data["sections"][0]["source"] == "municode"

    @patch(_IS_AMLEGAL_PATH, return_value=True)
    @patch(_CORPUS_PATH)
    def test_amlegal_jurisdiction_gets_amlegal_source_tag(self, MockCorpus, _, tmp_path):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(1))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        fetch_and_store_municipal_code(
            jurisdiction_id="city-sacramento",
            cloud=False,
            output_dir=str(tmp_path),
        )

        data = json.loads((tmp_path / "municipal_code_city_sacramento.json").read_text())
        assert data["sections"][0]["source"] == "amlegal"

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_local_mode_creates_nested_output_dirs(self, MockCorpus, _, tmp_path):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(1))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        nested_dir = str(tmp_path / "a" / "b" / "c")
        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir=nested_dir,
        )

        assert result == 0
        output_file = Path(nested_dir) / "municipal_code_city_test.json"
        data = json.loads(output_file.read_text())
        assert data["count"] == 1

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_output_filename_replaces_hyphens_with_underscores(self, MockCorpus, _, tmp_path):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(1))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-san-rafael",
            cloud=False,
            output_dir=str(tmp_path),
        )

        assert result == 0
        # Hyphens in jurisdiction_id become underscores in filename
        data = json.loads((tmp_path / "municipal_code_city_san_rafael.json").read_text())
        assert data["jurisdiction_id"] == "city-san-rafael"

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_local_output_includes_iso_timestamp(self, MockCorpus, _, tmp_path):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(1))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir=str(tmp_path),
        )

        data = json.loads((tmp_path / "municipal_code_city_test.json").read_text())
        # ISO 8601 datetime: YYYY-MM-DDTHH:MM:SS...
        assert "T" in data["fetched_at"]
        assert data["fetched_at"][:4].isdigit()

    # --- Cloud storage ---

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_cloud_mode_returns_1_without_database_url(self, MockCorpus, _):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(3))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=True,
            output_dir="/tmp/test_out",
        )

        assert result == 1

    @patch(_PG_BACKEND_PATH)
    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_cloud_mode_stores_sections_and_returns_0(self, MockCorpus, _, MockBackend, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        sections = _make_sections(5)
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(sections)
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        mock_backend = MagicMock()
        MockBackend.return_value = mock_backend
        mock_backend.store_municipal_code.return_value = 5

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=True,
            output_dir="/tmp/unused",
        )

        assert result == 0
        call_args = mock_backend.store_municipal_code.call_args
        assert call_args[0][0] == "city-test"
        stored_sections = call_args[0][1]
        assert len(stored_sections) == 5
        assert stored_sections[0]["section_number"] == "1.01"
        assert stored_sections[0]["source"] == "municode"

    @patch(_PG_BACKEND_PATH)
    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_cloud_mode_returns_1_on_storage_error(self, MockCorpus, _, MockBackend, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://test")
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(3))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        mock_backend = MagicMock()
        MockBackend.return_value = mock_backend
        mock_backend.store_municipal_code.side_effect = Exception("Storage error")

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=True,
            output_dir="/tmp/unused",
        )

        assert result == 1

    # --- Limit boundary ---

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_limit_of_1_fetches_exactly_one(self, MockCorpus, _, tmp_path):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(10))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir=str(tmp_path),
            limit=1,
        )

        assert result == 0
        data = json.loads((tmp_path / "municipal_code_city_test.json").read_text())
        assert data["count"] == 1
        assert data["sections"][0]["section_number"] == "1.01"

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_no_limit_fetches_all_sections(self, MockCorpus, _, tmp_path):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(5))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir=str(tmp_path),
            limit=None,
        )

        assert result == 0
        data = json.loads((tmp_path / "municipal_code_city_test.json").read_text())
        assert data["count"] == 5

    @patch(_IS_AMLEGAL_PATH, return_value=False)
    @patch(_CORPUS_PATH)
    def test_limit_larger_than_available_fetches_all(self, MockCorpus, _, tmp_path):
        mock_corpus = MagicMock()
        mock_corpus.stream_sections.return_value = iter(_make_sections(3))
        MockCorpus.for_jurisdiction.return_value = mock_corpus

        result = fetch_and_store_municipal_code(
            jurisdiction_id="city-test",
            cloud=False,
            output_dir=str(tmp_path),
            limit=100,
        )

        assert result == 0
        data = json.loads((tmp_path / "municipal_code_city_test.json").read_text())
        assert data["count"] == 3
