"""Tests for election coverage monitoring.

Validates that check_election_coverage() correctly counts elections, contests,
deadlines, and officials per jurisdiction and flags gaps (zero counts).
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

# Import the function under test from modal_ingest (it's a plain function, not Modal-decorated)
import importlib
import sys
from pathlib import Path

# Add scripts/ to path so we can import the function
SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"


def _load_check_election_coverage():
    """Load check_election_coverage from modal_ingest without triggering Modal decorators."""
    import ast

    source = (SCRIPTS_DIR / "modal_ingest.py").read_text()
    tree = ast.parse(source)

    # Extract just the function source
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "check_election_coverage":
            func_source = ast.get_source_segment(source, node)
            break
    else:
        raise ImportError("check_election_coverage not found in modal_ingest.py")

    # Compile and exec in a namespace
    ns = {}
    exec(compile(func_source, "modal_ingest.py", "exec"), ns)
    return ns["check_election_coverage"]


check_election_coverage = _load_check_election_coverage()


def _make_backend(elections_by_jid=None, contests_by_eid=None,
                  deadlines_by_eid=None, officials_by_jid=None):
    """Create a mock backend with configurable return values."""
    backend = MagicMock()

    elections_by_jid = elections_by_jid or {}
    contests_by_eid = contests_by_eid or {}
    deadlines_by_eid = deadlines_by_eid or {}
    officials_by_jid = officials_by_jid or {}

    def get_elections(jid, include_past=False):
        return elections_by_jid.get(jid, [])

    def get_election_contests(eid, **kwargs):
        return contests_by_eid.get(eid, [])

    def get_election_deadlines(eid, **kwargs):
        return deadlines_by_eid.get(eid, [])

    def get_elected_officials(jid, current_only=True, **kwargs):
        return officials_by_jid.get(jid, [])

    backend.get_elections = MagicMock(side_effect=get_elections)
    backend.get_election_contests = MagicMock(side_effect=get_election_contests)
    backend.get_election_deadlines = MagicMock(side_effect=get_election_deadlines)
    backend.get_elected_officials = MagicMock(side_effect=get_elected_officials)

    return backend


@pytest.fixture
def logger():
    return logging.getLogger("test_coverage")


# ---------------------------------------------------------------------------
# Core coverage logic
# ---------------------------------------------------------------------------


class TestCoverageReport:
    """Tests for the coverage report structure and gap detection."""

    def test_full_coverage_no_gaps(self, logger):
        """Jurisdiction with all data categories populated reports no gaps."""
        backend = _make_backend(
            elections_by_jid={"city-alpha": [{"id": "e1"}, {"id": "e2"}]},
            contests_by_eid={"e1": [{"id": "c1"}], "e2": [{"id": "c2"}]},
            deadlines_by_eid={"e1": [{"id": "d1"}], "e2": [{"id": "d2"}]},
            officials_by_jid={"city-alpha": [{"id": "o1"}, {"id": "o2"}]},
        )
        jurisdictions = {
            "city-alpha": {"election_sources": {"civera_election_stats": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        assert report["jurisdictions_checked"] == 1
        assert report["jurisdictions_with_gaps"] == 0
        detail = report["details"]["city-alpha"]
        assert detail["elections"] == 2
        assert detail["contests"] == 2
        assert detail["deadlines"] == 2
        assert detail["officials"] == 2
        assert detail["gaps"] == []

    def test_zero_elections_flags_all_gaps(self, logger):
        """Zero elections means contests and deadlines are also zero."""
        backend = _make_backend(
            officials_by_jid={"city-beta": [{"id": "o1"}]},
        )
        jurisdictions = {
            "city-beta": {"election_sources": {"ca_sos_results": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        assert report["jurisdictions_with_gaps"] == 1
        detail = report["details"]["city-beta"]
        assert detail["elections"] == 0
        assert detail["contests"] == 0
        assert detail["deadlines"] == 0
        assert detail["officials"] == 1
        assert "elections" in detail["gaps"]
        assert "contests" in detail["gaps"]
        assert "deadlines" in detail["gaps"]
        assert "officials" not in detail["gaps"]

    def test_elections_but_no_officials(self, logger):
        """Elections exist but no officials — flags officials gap only."""
        backend = _make_backend(
            elections_by_jid={"city-gamma": [{"id": "e1"}]},
            contests_by_eid={"e1": [{"id": "c1"}]},
            deadlines_by_eid={"e1": [{"id": "d1"}]},
        )
        jurisdictions = {
            "city-gamma": {"election_sources": {"civera_election_stats": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        assert report["jurisdictions_with_gaps"] == 1
        detail = report["details"]["city-gamma"]
        assert detail["elections"] == 1
        assert detail["officials"] == 0
        assert detail["gaps"] == ["officials"]

    def test_completely_empty_jurisdiction(self, logger):
        """Jurisdiction with election_sources but zero data in all categories."""
        backend = _make_backend()
        jurisdictions = {
            "city-empty": {"election_sources": {"civera_election_stats": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        assert report["jurisdictions_with_gaps"] == 1
        detail = report["details"]["city-empty"]
        assert detail["gaps"] == ["elections", "contests", "deadlines", "officials"]

    def test_partial_contest_coverage(self, logger):
        """Some elections have contests, others don't — total > 0 means no gap."""
        backend = _make_backend(
            elections_by_jid={"city-delta": [{"id": "e1"}, {"id": "e2"}]},
            contests_by_eid={"e1": [{"id": "c1"}]},  # e2 has no contests
            deadlines_by_eid={"e1": [{"id": "d1"}], "e2": [{"id": "d2"}]},
            officials_by_jid={"city-delta": [{"id": "o1"}]},
        )
        jurisdictions = {
            "city-delta": {"election_sources": {"civera_election_stats": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        detail = report["details"]["city-delta"]
        assert detail["contests"] == 1  # Only e1 has contests
        assert "contests" not in detail["gaps"]


# ---------------------------------------------------------------------------
# Filtering and skipping
# ---------------------------------------------------------------------------


class TestCoverageFiltering:
    """Tests for jurisdiction filtering in the coverage report."""

    def test_skip_jurisdictions_without_election_sources(self, logger):
        """Jurisdictions without election_sources are excluded from the report."""
        backend = _make_backend()
        jurisdictions = {
            "city-alpha": {"election_sources": {"civera_election_stats": True}},
            "city-noelection": {"some_other_key": True},
            "city-empty-sources": {"election_sources": {}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        assert report["jurisdictions_checked"] == 1
        assert "city-alpha" in report["details"]
        assert "city-noelection" not in report["details"]
        assert "city-empty-sources" not in report["details"]

    def test_multiple_jurisdictions_mixed_coverage(self, logger):
        """Report correctly counts gaps across multiple jurisdictions."""
        backend = _make_backend(
            elections_by_jid={
                "city-good": [{"id": "e1"}],
                # city-bad has no elections
            },
            contests_by_eid={"e1": [{"id": "c1"}]},
            deadlines_by_eid={"e1": [{"id": "d1"}]},
            officials_by_jid={
                "city-good": [{"id": "o1"}],
                "city-bad": [{"id": "o2"}],
            },
        )
        jurisdictions = {
            "city-good": {"election_sources": {"civera_election_stats": True}},
            "city-bad": {"election_sources": {"ca_sos_results": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        assert report["jurisdictions_checked"] == 2
        assert report["jurisdictions_with_gaps"] == 1
        assert report["details"]["city-good"]["gaps"] == []
        assert "elections" in report["details"]["city-bad"]["gaps"]

    def test_empty_jurisdictions_dict(self, logger):
        """Empty jurisdictions dict produces empty report."""
        backend = _make_backend()

        report = check_election_coverage(backend, {}, logger)

        assert report["jurisdictions_checked"] == 0
        assert report["jurisdictions_with_gaps"] == 0
        assert report["details"] == {}


# ---------------------------------------------------------------------------
# Backend interaction
# ---------------------------------------------------------------------------


class TestCoverageBackendCalls:
    """Tests that the coverage check queries the backend correctly."""

    def test_elections_queried_with_include_past(self, logger):
        """get_elections called with include_past=True to count all historical data."""
        backend = _make_backend()
        jurisdictions = {
            "city-alpha": {"election_sources": {"civera_election_stats": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        backend.get_elections.assert_called_once_with("city-alpha", include_past=True)
        assert report["jurisdictions_checked"] == 1
        assert report["details"]["city-alpha"]["elections"] == 0

    def test_officials_queried_with_current_only_false(self, logger):
        """get_elected_officials called with current_only=False for full count."""
        backend = _make_backend(
            officials_by_jid={"city-alpha": [{"id": "o1"}, {"id": "o2"}]},
        )
        jurisdictions = {
            "city-alpha": {"election_sources": {"civera_election_stats": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        backend.get_elected_officials.assert_called_once_with(
            "city-alpha", current_only=False
        )
        assert report["details"]["city-alpha"]["officials"] == 2

    def test_contests_queried_per_election(self, logger):
        """get_election_contests called once per election."""
        backend = _make_backend(
            elections_by_jid={"city-alpha": [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]},
            contests_by_eid={"e1": [{"id": "c1"}], "e3": [{"id": "c2"}]},
        )
        jurisdictions = {
            "city-alpha": {"election_sources": {"civera_election_stats": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        assert backend.get_election_contests.call_count == 3
        assert report["details"]["city-alpha"]["elections"] == 3
        assert report["details"]["city-alpha"]["contests"] == 2

    def test_election_without_id_skipped(self, logger):
        """Elections missing 'id' field don't trigger contest/deadline queries."""
        backend = _make_backend(
            elections_by_jid={"city-alpha": [{"id": "e1"}, {"name": "no-id"}]},
            contests_by_eid={"e1": [{"id": "c1"}]},
            deadlines_by_eid={"e1": [{"id": "d1"}]},
        )
        jurisdictions = {
            "city-alpha": {"election_sources": {"civera_election_stats": True}},
        }

        report = check_election_coverage(backend, jurisdictions, logger)

        # Only e1 should be queried, not the one missing id
        assert backend.get_election_contests.call_count == 1
        assert backend.get_election_deadlines.call_count == 1
        # Both elections counted, but only e1 contributed contests/deadlines
        assert report["details"]["city-alpha"]["elections"] == 2
        assert report["details"]["city-alpha"]["contests"] == 1
        assert report["details"]["city-alpha"]["deadlines"] == 1
