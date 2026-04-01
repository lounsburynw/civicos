"""Tests for election cron enrollment validation.

Validates that get_active_jurisdictions() correctly enrolls all jurisdiction
types (city, county, school, college, state) and excludes non-jurisdiction
files like civera_instances.json and supplementary configs (-schools, -districts).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from civicos_extraction.config import get_active_jurisdictions


# ---------------------------------------------------------------------------
# Live data tests — run against the real data/extraction/ directory
# ---------------------------------------------------------------------------


class TestLiveEnrollment:
    """Tests against the real extraction config directory."""

    def test_all_prefix_types_present(self):
        """Every expected jurisdiction prefix type appears in the result."""
        j = get_active_jurisdictions()
        prefixes = {jid.split("-")[0] for jid in j}
        for expected in ("city", "county", "school", "college", "state"):
            assert expected in prefixes, f"Missing prefix type: {expected}"

    def test_civera_instances_excluded(self):
        """civera_instances.json (no jurisdiction_id) must not appear."""
        j = get_active_jurisdictions()
        assert "city-civera_instances" not in j
        # Also ensure no key contains 'civera_instances'
        for jid in j:
            assert "civera_instances" not in jid

    def test_supplementary_files_excluded(self):
        """Files with -schools or -districts in name are skipped."""
        j = get_active_jurisdictions()
        # san-rafael-schools.json should not produce a jurisdiction entry
        for jid in j:
            assert "-schools" not in jid
            assert "-districts" not in jid

    def test_all_election_sources_enrolled(self):
        """Every config file with election_sources is included in results."""
        from civicos_extraction.config import get_config_dir

        config_dir = get_config_dir()
        missing = []

        for config_file in config_dir.glob("*.json"):
            if "-schools" in config_file.name or "-districts" in config_file.name:
                continue
            try:
                with open(config_file) as f:
                    config = json.load(f)
                jid = config.get("jurisdiction_id")
                if not jid:
                    continue
                if config.get("election_sources"):
                    j = get_active_jurisdictions()
                    if jid not in j:
                        missing.append(jid)
                    elif not j[jid].get("election_sources"):
                        missing.append(f"{jid} (election_sources lost in merge)")
            except Exception:
                pass

        assert not missing, f"Jurisdictions with election_sources not enrolled: {missing}"

    def test_duplicate_configs_merged(self):
        """When two files share a jurisdiction_id, their configs are merged."""
        j = get_active_jurisdictions()
        # city-san-rafael has configs in both san-rafael.json and city-san-rafael.json
        sr = j.get("city-san-rafael", {})
        # san-rafael.json has 'financial', city-san-rafael.json has 'election_sources'
        assert "election_sources" in sr, "election_sources missing (merge failure)"
        assert "financial" in sr or "federal_programs" in sr, (
            "financial data missing (merge failure)"
        )

    def test_no_duplicate_jurisdiction_ids(self):
        """Each jurisdiction_id appears exactly once in results (merging handled)."""
        j = get_active_jurisdictions()
        # This is inherently true since it's a dict, but verify all values are dicts
        for jid, config in j.items():
            assert isinstance(config, dict), f"{jid} config is not a dict"
            assert config.get("jurisdiction_id") == jid


# ---------------------------------------------------------------------------
# Isolated tests — use temp directory to test enrollment mechanics
# ---------------------------------------------------------------------------


class TestEnrollmentMechanics:
    """Tests with controlled config directories to verify enrollment logic."""

    @pytest.fixture
    def config_dir(self, tmp_path):
        """Create a temp config directory with test jurisdiction files."""
        configs = {
            "city-alpha.json": {
                "jurisdiction_id": "city-alpha",
                "source_type": "legistar",
                "election_sources": {"civera_election_stats": {}},
            },
            "county-beta.json": {
                "jurisdiction_id": "county-beta",
                "source_type": "legistar",
                "election_sources": {"ca_sos_results": {}},
            },
            "school-gamma.json": {
                "jurisdiction_id": "school-gamma",
                "source_type": "boarddocs",
                "election_sources": {"civera_election_stats": {}},
            },
            "college-delta.json": {
                "jurisdiction_id": "college-delta",
                "source_type": "boarddocs",
            },
            "state-epsilon.json": {
                "jurisdiction_id": "state-epsilon",
                "source_type": "custom",
            },
            # Non-jurisdiction files that should be excluded
            "registry.json": {
                "_comment": "Not a jurisdiction",
                "instances": {"foo": {}},
            },
            "alpha-schools.json": {
                "jurisdiction_id": "city-alpha",
                "school_boards": ["board-1"],
            },
        }
        for name, data in configs.items():
            (tmp_path / name).write_text(json.dumps(data))
        return tmp_path

    def test_auto_enrollment(self, config_dir):
        """All files with jurisdiction_id are enrolled."""
        with patch("civicos_extraction.config.get_config_dir", return_value=config_dir):
            j = get_active_jurisdictions()

        assert "city-alpha" in j
        assert "county-beta" in j
        assert "school-gamma" in j
        assert "college-delta" in j
        assert "state-epsilon" in j
        assert len(j) == 5

    def test_registry_excluded(self, config_dir):
        """Files without jurisdiction_id are excluded."""
        with patch("civicos_extraction.config.get_config_dir", return_value=config_dir):
            j = get_active_jurisdictions()

        # registry.json has no jurisdiction_id
        for jid in j:
            assert "registry" not in jid

    def test_supplementary_excluded(self, config_dir):
        """Files with -schools in name are excluded even with jurisdiction_id."""
        with patch("civicos_extraction.config.get_config_dir", return_value=config_dir):
            j = get_active_jurisdictions()

        # alpha-schools.json should be skipped
        assert len(j) == 5  # Only the 5 real jurisdictions

    def test_new_jurisdiction_auto_enrolls(self, config_dir):
        """Adding a new config file with election_sources auto-enrolls it."""
        new_config = {
            "jurisdiction_id": "city-zeta",
            "source_type": "legistar",
            "election_sources": {"civera_election_stats": {}},
        }
        (config_dir / "city-zeta.json").write_text(json.dumps(new_config))

        with patch("civicos_extraction.config.get_config_dir", return_value=config_dir):
            j = get_active_jurisdictions()

        assert "city-zeta" in j
        assert j["city-zeta"].get("election_sources")

    def test_merge_duplicate_jurisdiction_ids(self, config_dir):
        """Two files with the same jurisdiction_id are merged."""
        # Add a second file for city-alpha with different keys
        extra = {
            "jurisdiction_id": "city-alpha",
            "financial": {"budget_url": "https://example.com"},
        }
        (config_dir / "alpha.json").write_text(json.dumps(extra))

        with patch("civicos_extraction.config.get_config_dir", return_value=config_dir):
            j = get_active_jurisdictions()

        alpha = j["city-alpha"]
        # Should have keys from both files
        assert "election_sources" in alpha, "election_sources lost in merge"
        assert "financial" in alpha, "financial lost in merge"
