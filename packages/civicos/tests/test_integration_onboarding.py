"""
Integration tests for the turnkey onboarding pipeline (scripts/onboard.py).

Validates:
1. _quality_report() severity classification (CRITICAL vs WARNING)
2. _get_ingestion_stages() dynamic stage determination
3. CLI flow with mocked Modal/Postgres (exit codes, flag behavior)

Does NOT require DATABASE_URL — all Postgres calls are mocked.

Run: pytest packages/civicos/tests/test_integration_onboarding.py -v --override-ini="addopts="
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Load onboard.py as a module (it's a script, not a package)
PROJECT_ROOT = Path(__file__).parents[3]
_spec = importlib.util.spec_from_file_location(
    "onboard", str(PROJECT_ROOT / "scripts" / "onboard.py")
)
onboard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(onboard)

QualityIssue = onboard.QualityIssue
_quality_report = onboard._quality_report
_get_ingestion_stages = onboard._get_ingestion_stages
_get_data_counts = onboard._get_data_counts
_update_registry = onboard._update_registry
_verify_jurisdiction = onboard._verify_jurisdiction
_estimate_cost = onboard._estimate_cost
_run_batch = onboard._run_batch


# ---------------------------------------------------------------------------
# _quality_report() — severity classification
# ---------------------------------------------------------------------------

class TestQualityReport:
    """Unit tests for _quality_report(): pure function, no I/O."""

    def test_clean_data_no_issues(self):
        """All metrics healthy -> 0 issues, exit would be 0."""
        counts = {"meetings": 10, "chunks": 520, "agenda_items": 30,
                  "decisions": 5, "municipal_code": 100}
        lines, issues = _quality_report(counts, "test")
        assert len(issues) == 0
        assert any("All quality checks passed" in l for l in lines)

    def test_zero_meetings_on_meeting_platform_is_critical(self):
        """meetings=0 when has_meetings=True -> CRITICAL."""
        counts = {"meetings": 0, "chunks": 0, "agenda_items": 0,
                  "decisions": 0, "municipal_code": 0}
        _, issues = _quality_report(counts, has_meetings=True)
        assert len(issues) == 1
        assert issues[0].severity == QualityIssue.CRITICAL
        assert "meetings = 0" in issues[0].message

    def test_zero_meetings_no_meeting_stages_is_ok(self):
        """meetings=0 when has_meetings=False -> no issue (expected)."""
        counts = {"meetings": 0, "chunks": 0, "agenda_items": 0,
                  "decisions": 0, "municipal_code": 0}
        _, issues = _quality_report(counts, has_meetings=False)
        assert len(issues) == 0

    def test_zero_agenda_items_is_critical(self):
        """agenda_items/meeting=0 -> CRITICAL (LLM extraction failed)."""
        counts = {"meetings": 10, "chunks": 100, "agenda_items": 0,
                  "decisions": 0, "municipal_code": 0}
        _, issues = _quality_report(counts)
        critical = [i for i in issues if i.severity == QualityIssue.CRITICAL]
        assert len(critical) == 1
        assert "agenda_items/meeting = 0" in critical[0].message

    def test_zero_chunks_is_warning(self):
        """chunks/meeting=0 -> WARNING (HTML agendas)."""
        counts = {"meetings": 10, "chunks": 0, "agenda_items": 30,
                  "decisions": 5, "municipal_code": 0}
        _, issues = _quality_report(counts)
        warnings = [i for i in issues if i.severity == QualityIssue.WARNING]
        assert len(warnings) == 1
        assert "chunks/meeting = 0" in warnings[0].message

    def test_zero_decisions_is_warning(self):
        """decisions/meeting=0 -> WARNING (minutes not posted)."""
        counts = {"meetings": 10, "chunks": 100, "agenda_items": 30,
                  "decisions": 0, "municipal_code": 0}
        _, issues = _quality_report(counts)
        warnings = [i for i in issues if i.severity == QualityIssue.WARNING]
        assert any("decisions/meeting = 0" in w.message for w in warnings)

    def test_low_decisions_is_warning(self):
        """decisions/meeting < 0.1 -> WARNING (low extraction)."""
        # 10 meetings, 0 decisions would be "= 0", so use a tiny number
        # that yields decisions_per > 0 but < 0.1: e.g. 10 meetings, 0 decisions
        # Actually let's use a case where decisions_per is exactly between 0 and 0.1:
        # meetings=100, decisions=5 -> 0.05
        counts = {"meetings": 100, "chunks": 5200, "agenda_items": 300,
                  "decisions": 5, "municipal_code": 0}
        _, issues = _quality_report(counts)
        warnings = [i for i in issues if i.severity == QualityIssue.WARNING]
        assert any("low" in w.message for w in warnings)

    def test_remediation_references_config_path(self):
        """Remediation text references the extraction config when jid is set."""
        counts = {"meetings": 0, "chunks": 0, "agenda_items": 0,
                  "decisions": 0, "municipal_code": 0}
        _, issues = _quality_report(counts, has_meetings=True, jid="city-testville")
        assert len(issues) >= 1
        assert "data/extraction/city-testville.json" in issues[0].remediation

    def test_report_lines_include_ratios_when_meetings_exist(self):
        """Report output includes ratio lines when meetings > 0."""
        counts = {"meetings": 10, "chunks": 520, "agenda_items": 30,
                  "decisions": 5, "municipal_code": 100}
        lines, _ = _quality_report(counts, "sample")
        text = "\n".join(lines)
        assert "chunks/meeting" in text
        assert "agenda_items/meeting" in text
        assert "decisions/meeting" in text
        assert "baseline" in text

    def test_multiple_issues_classified_separately(self):
        """Multiple issues can coexist with different severities."""
        # 0 agenda items -> CRITICAL, 0 chunks -> WARNING, 0 decisions -> WARNING
        counts = {"meetings": 10, "chunks": 0, "agenda_items": 0,
                  "decisions": 0, "municipal_code": 0}
        _, issues = _quality_report(counts)
        critical = [i for i in issues if i.severity == QualityIssue.CRITICAL]
        warnings = [i for i in issues if i.severity == QualityIssue.WARNING]
        assert len(critical) == 1  # agenda_items
        assert len(warnings) == 2  # chunks + decisions


# ---------------------------------------------------------------------------
# _get_ingestion_stages() — dynamic stage determination
# ---------------------------------------------------------------------------

class TestIngestionStages:
    """Tests for _get_ingestion_stages(): reads config files to determine stages."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project structure with extraction + YAML configs."""
        extraction_dir = tmp_path / "data" / "extraction"
        extraction_dir.mkdir(parents=True)
        jurisdiction_dir = tmp_path / "data" / "jurisdictions"
        jurisdiction_dir.mkdir(parents=True)
        return tmp_path

    def _write_extraction_config(self, temp_project, jid, config):
        path = temp_project / "data" / "extraction" / f"{jid}.json"
        path.write_text(json.dumps(config))

    def _write_jurisdiction_yaml(self, temp_project, jid, config):
        path = temp_project / "data" / "jurisdictions" / f"{jid}.yaml"
        path.write_text(yaml.dump(config))

    def test_legistar_source_includes_meeting_stages(self, temp_project):
        """Legistar (supported) -> meetings, chunks, agenda, decisions."""
        jid = "city-test-legistar"
        self._write_extraction_config(temp_project, jid, {
            "source_type": "legistar",
            "base_url": "https://example.legistar.com",
            "issue_source": "seeclickfix",
        })
        self._write_jurisdiction_yaml(temp_project, jid, {
            "jurisdiction_id": jid,
        })
        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            stages = _get_ingestion_stages(jid)
        assert "meetings" in stages
        assert "chunks" in stages
        assert "agenda" in stages
        assert "decisions" in stages
        assert "vectors" in stages

    def test_unsupported_source_skips_meeting_stages(self, temp_project):
        """Unsupported source_type -> no meeting stages."""
        jid = "city-test-unknown"
        self._write_extraction_config(temp_project, jid, {
            "source_type": "wordpress",
            "issue_source": "seeclickfix",
        })
        self._write_jurisdiction_yaml(temp_project, jid, {
            "jurisdiction_id": jid,
        })
        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            stages = _get_ingestion_stages(jid)
        assert "meetings" not in stages
        assert "chunks" not in stages
        assert "agenda" not in stages
        assert "decisions" not in stages
        # Issues and vectors still included
        assert "issues" in stages
        assert "vectors" in stages

    def test_seeclickfix_issues_included(self, temp_project):
        """seeclickfix issue_source -> issues stage included."""
        jid = "city-test-issues"
        self._write_extraction_config(temp_project, jid, {
            "source_type": "legistar",
            "issue_source": "seeclickfix",
        })
        self._write_jurisdiction_yaml(temp_project, jid, {
            "jurisdiction_id": jid,
        })
        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            stages = _get_ingestion_stages(jid)
        assert "issues" in stages

    def test_unsupported_issue_source_excluded(self, temp_project):
        """Unsupported issue source -> issues stage excluded."""
        jid = "city-test-no-issues"
        self._write_extraction_config(temp_project, jid, {
            "source_type": "legistar",
            "issue_source": "fixitmarin",
        })
        self._write_jurisdiction_yaml(temp_project, jid, {
            "jurisdiction_id": jid,
        })
        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            stages = _get_ingestion_stages(jid)
        assert "issues" not in stages

    def test_municipal_code_included_when_configured(self, temp_project):
        """YAML with ingestion.municipal_code -> municipal stage."""
        jid = "city-test-muni"
        self._write_extraction_config(temp_project, jid, {
            "source_type": "legistar",
            "issue_source": "seeclickfix",
        })
        self._write_jurisdiction_yaml(temp_project, jid, {
            "jurisdiction_id": jid,
            "ingestion": {
                "municipal_code": {
                    "source": "municode",
                    "url": "https://example.com",
                },
            },
        })
        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            stages = _get_ingestion_stages(jid)
        assert "municipal" in stages

    def test_no_municipal_code_when_not_configured(self, temp_project):
        """No ingestion.municipal_code in YAML -> no municipal stage."""
        jid = "city-test-no-muni"
        self._write_extraction_config(temp_project, jid, {
            "source_type": "legistar",
            "issue_source": "seeclickfix",
        })
        self._write_jurisdiction_yaml(temp_project, jid, {
            "jurisdiction_id": jid,
        })
        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            stages = _get_ingestion_stages(jid)
        assert "municipal" not in stages

    def test_vectors_always_included(self, temp_project):
        """vectors stage is always present regardless of config."""
        jid = "city-test-vectors"
        self._write_extraction_config(temp_project, jid, {
            "source_type": "wordpress",
            "issue_source": "none",
        })
        self._write_jurisdiction_yaml(temp_project, jid, {
            "jurisdiction_id": jid,
        })
        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            stages = _get_ingestion_stages(jid)
        assert "vectors" in stages


# ---------------------------------------------------------------------------
# CLI flow — mocked external calls, verifying orchestration logic
# ---------------------------------------------------------------------------

class TestCLIFlow:
    """Integration tests for the CLI main() flow with mocked externals."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Temp project with extraction config and jurisdiction YAML."""
        extraction_dir = tmp_path / "data" / "extraction"
        extraction_dir.mkdir(parents=True)
        jurisdiction_dir = tmp_path / "data" / "jurisdictions"
        jurisdiction_dir.mkdir(parents=True)

        jid = "city-testville"

        # Extraction config
        config = {
            "source_type": "legistar",
            "base_url": "https://testville.legistar.com",
            "issue_source": "seeclickfix",
        }
        (extraction_dir / f"{jid}.json").write_text(json.dumps(config))

        # Jurisdiction YAML
        yaml_config = {
            "jurisdiction_id": jid,
            "name": "Testville",
            "state": "CA",
        }
        (jurisdiction_dir / f"{jid}.yaml").write_text(yaml.dump(yaml_config))

        return tmp_path, jid

    def _run_main(self, argv):
        """Run onboard.main() with given argv, return exit code."""
        with patch.object(sys, "argv", ["onboard.py"] + argv):
            try:
                onboard.main()
                return 0  # main() returned without sys.exit
            except SystemExit as e:
                return e.code if e.code is not None else 0

    def test_skip_ingestion_returns_without_modal(self, temp_project):
        """--skip-ingestion generates configs, never calls Modal."""
        tmp_path, jid = temp_project

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion") as mock_modal, \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 0, "chunks": 0, "agenda_items": 0,
                 "decisions": 0, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
                "--skip-ingestion",
            ])

        assert code == 0
        mock_modal.assert_not_called()

    def test_no_validate_skips_sample_ingestion(self, temp_project):
        """--no-validate skips Phase 2.5, runs full ingestion directly."""
        tmp_path, jid = temp_project
        modal_calls = []

        def track_modal(jid, days_past, dry_run=False, stages="all"):
            modal_calls.append({"jid": jid, "days": days_past})
            return 0

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", side_effect=track_modal), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
                "--no-validate",
            ])

        assert code == 0
        # Only one Modal call (full ingestion at 365 days), no sample
        assert len(modal_calls) == 1
        assert modal_calls[0]["days"] == 365

    def test_validation_gate_blocks_on_critical_issues(self, temp_project):
        """Critical issues in sample -> sys.exit(2)."""
        tmp_path, jid = temp_project

        # Sample ingestion succeeds but returns bad data
        def mock_modal(jid, days_past, dry_run=False, stages="all"):
            return 0

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", side_effect=mock_modal), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 5, "chunks": 50, "agenda_items": 0,
                 "decisions": 0, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
            ])

        assert code == 2

    def test_force_continue_overrides_critical_gate(self, temp_project):
        """--force-continue proceeds past critical issues."""
        tmp_path, jid = temp_project

        modal_calls = []

        def track_modal(jid, days_past, dry_run=False, stages="all"):
            modal_calls.append(days_past)
            return 0

        # First call (sample) returns bad data, but --force-continue overrides.
        # Second call (full) also returns bad data (final report).
        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", side_effect=track_modal), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 5, "chunks": 50, "agenda_items": 0,
                 "decisions": 0, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
                "--force-continue",
            ])

        # Exits 2 from final quality report (issues still exist), but didn't
        # block at Phase 2.5 — both sample AND full ingestion ran.
        assert code == 2
        assert len(modal_calls) == 2  # sample (30 days) + full (365 days)
        assert modal_calls[0] == 30
        assert modal_calls[1] == 365

    def test_successful_run_exits_zero(self, temp_project):
        """Clean data through all phases -> exit 0."""
        tmp_path, jid = temp_project

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", return_value=0), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 100,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
            ])

        assert code == 0

    def test_modal_failure_exits_with_modal_code(self, temp_project):
        """Modal ingestion failure -> sys.exit(rc) with Modal's exit code."""
        tmp_path, jid = temp_project

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", return_value=1), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 0, "chunks": 0, "agenda_items": 0,
                 "decisions": 0, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
                "--no-validate",
            ])

        # Modal returned 1 -> onboard exits with same code
        assert code == 1

    def test_sample_days_flag_controls_sample_size(self, temp_project):
        """--sample-days controls the validation sample window."""
        tmp_path, jid = temp_project

        modal_calls = []

        def track_modal(jid, days_past, dry_run=False, stages="all"):
            modal_calls.append(days_past)
            return 0

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", side_effect=track_modal), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
                "--sample-days", "14",
            ])

        assert code == 0
        # First call is sample (14 days), second is full (365)
        assert modal_calls[0] == 14
        assert modal_calls[1] == 365

    def test_config_generation_called_when_no_configs(self, tmp_path):
        """When no extraction config exists, onboard_jurisdiction() is called."""
        extraction_dir = tmp_path / "data" / "extraction"
        extraction_dir.mkdir(parents=True)
        jurisdiction_dir = tmp_path / "data" / "jurisdictions"
        jurisdiction_dir.mkdir(parents=True)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.jurisdiction_id = "city-newtown"
        mock_result.config_path = str(extraction_dir / "city-newtown.json")
        mock_result.discovered_bodies = {"City Council": "1"}
        mock_result.errors = []

        # Write configs that onboard_jurisdiction would have created
        def fake_onboard(**kwargs):
            (extraction_dir / "city-newtown.json").write_text(json.dumps({
                "source_type": "legistar",
                "issue_source": "seeclickfix",
            }))
            (jurisdiction_dir / "city-newtown.yaml").write_text(yaml.dump({
                "jurisdiction_id": "city-newtown",
            }))
            return mock_result

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch("civicos_extraction.onboard.onboard_jurisdiction", side_effect=fake_onboard) as mock_onboard, \
             patch.object(onboard, "_run_modal_ingestion", return_value=0), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Newtown", "--state", "CA",
                "--skip-ingestion",
            ])

        assert code == 0
        mock_onboard.assert_called_once()

    def test_config_generation_failure_exits_one(self, tmp_path):
        """Failed config generation -> sys.exit(1)."""
        extraction_dir = tmp_path / "data" / "extraction"
        extraction_dir.mkdir(parents=True)
        jurisdiction_dir = tmp_path / "data" / "jurisdictions"
        jurisdiction_dir.mkdir(parents=True)

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.errors = ["Could not detect platform"]

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch("civicos_extraction.onboard.onboard_jurisdiction", return_value=mock_result), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Nowhere", "--state", "CA",
            ])

        assert code == 1


# ---------------------------------------------------------------------------
# _update_registry() — registry.json management
# ---------------------------------------------------------------------------

class TestUpdateRegistry:
    """Tests for _update_registry(): adds jurisdictions to config/registry.json."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Temp project with registry and jurisdiction YAML."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        jurisdiction_dir = tmp_path / "data" / "jurisdictions"
        jurisdiction_dir.mkdir(parents=True)

        # Minimal registry
        registry = {
            "version": "1.0",
            "jurisdictions": {
                "state-california": {
                    "domain": "california.civicosproject.org",
                    "display_name": "California",
                    "parent_jurisdictions": ["country-united-states"],
                },
            },
        }
        (config_dir / "registry.json").write_text(json.dumps(registry, indent=2))

        return tmp_path

    def test_adds_new_jurisdiction_from_yaml(self, temp_project):
        """New jurisdiction with YAML parent info gets added to registry."""
        jid = "city-testville"
        yaml_config = {
            "jurisdiction_id": jid,
            "display_name": "Testville",
            "parent_jurisdictions": ["county-marin", "state-california"],
        }
        (temp_project / "data" / "jurisdictions" / f"{jid}.yaml").write_text(
            yaml.dump(yaml_config)
        )

        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            updated = _update_registry(jid)

        assert updated is True

        with open(temp_project / "config" / "registry.json") as f:
            registry = json.load(f)

        entry = registry["jurisdictions"][jid]
        assert entry["display_name"] == "Testville"
        assert entry["domain"] == "testville.civicosproject.org"
        assert "county-marin" in entry["parent_jurisdictions"]
        assert "state-california" in entry["parent_jurisdictions"]

    def test_skips_existing_jurisdiction(self, temp_project):
        """Already-registered jurisdiction returns False, no duplicate."""
        jid = "state-california"
        (temp_project / "data" / "jurisdictions" / f"{jid}.yaml").write_text(
            yaml.dump({"jurisdiction_id": jid, "display_name": "California"})
        )

        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            updated = _update_registry(jid)

        assert updated is False

    def test_derives_display_name_from_jid(self, temp_project):
        """When YAML has no display_name, derives from jurisdiction ID."""
        jid = "city-mill-valley"
        (temp_project / "data" / "jurisdictions" / f"{jid}.yaml").write_text(
            yaml.dump({"jurisdiction_id": jid})
        )

        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            _update_registry(jid)

        with open(temp_project / "config" / "registry.json") as f:
            registry = json.load(f)

        assert registry["jurisdictions"][jid]["display_name"] == "Mill Valley"

    def test_derives_parents_from_state(self, temp_project):
        """When YAML has financial.state but no parents, derives from state."""
        jid = "city-somewhere"
        (temp_project / "data" / "jurisdictions" / f"{jid}.yaml").write_text(
            yaml.dump({
                "jurisdiction_id": jid,
                "financial": {"state": "CA"},
            })
        )

        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            _update_registry(jid)

        with open(temp_project / "config" / "registry.json") as f:
            registry = json.load(f)

        parents = registry["jurisdictions"][jid]["parent_jurisdictions"]
        assert "state-ca" in parents
        assert "country-united-states" in parents

    def test_no_yaml_returns_false(self, temp_project):
        """No jurisdiction YAML -> returns False, registry unchanged."""
        with patch.object(onboard, "PROJECT_ROOT", temp_project):
            updated = _update_registry("city-nonexistent")

        assert updated is False


# ---------------------------------------------------------------------------
# _verify_jurisdiction() — live API verification
# ---------------------------------------------------------------------------

class TestVerifyJurisdiction:
    """Tests for _verify_jurisdiction(): hits live API (mocked here)."""

    def test_returns_true_on_results(self):
        """API returns results -> True."""
        response_data = json.dumps({"total": 5, "results": []}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert _verify_jurisdiction("city-test") is True

    def test_returns_false_on_zero_results(self):
        """API returns 0 results -> False."""
        response_data = json.dumps({"total": 0, "results": []}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert _verify_jurisdiction("city-test") is False

    def test_returns_false_on_http_error(self):
        """API HTTP error -> False (doesn't crash)."""
        import urllib.error
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError(None, 500, "Error", {}, None)):
            assert _verify_jurisdiction("city-test") is False

    def test_returns_false_on_timeout(self):
        """Network timeout -> False (doesn't crash)."""
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timeout")):
            assert _verify_jurisdiction("city-test") is False


# ---------------------------------------------------------------------------
# CLI flow — --deploy flag
# ---------------------------------------------------------------------------

class TestCLIDeployFlag:
    """Tests for --deploy flag integration in CLI flow."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Temp project with configs, YAML, and registry."""
        extraction_dir = tmp_path / "data" / "extraction"
        extraction_dir.mkdir(parents=True)
        jurisdiction_dir = tmp_path / "data" / "jurisdictions"
        jurisdiction_dir.mkdir(parents=True)
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        jid = "city-testville"

        # Extraction config
        (extraction_dir / f"{jid}.json").write_text(json.dumps({
            "source_type": "legistar",
            "issue_source": "seeclickfix",
        }))

        # Jurisdiction YAML
        (jurisdiction_dir / f"{jid}.yaml").write_text(yaml.dump({
            "jurisdiction_id": jid,
            "display_name": "Testville",
            "parent_jurisdictions": ["county-test", "state-california"],
        }))

        # Registry
        (config_dir / "registry.json").write_text(json.dumps({
            "version": "1.0",
            "jurisdictions": {},
        }))

        return tmp_path, jid

    def _run_main(self, argv):
        with patch.object(sys, "argv", ["onboard.py"] + argv):
            try:
                onboard.main()
                return 0
            except SystemExit as e:
                return e.code if e.code is not None else 0

    def test_deploy_flag_triggers_modal_deploy(self, temp_project):
        """--deploy triggers _deploy_modal_api() after ingestion."""
        tmp_path, jid = temp_project

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", return_value=0), \
             patch.object(onboard, "_deploy_modal_api", return_value=0) as mock_deploy, \
             patch.object(onboard, "_verify_jurisdiction", return_value=True), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
                "--no-validate", "--deploy",
            ])

        assert code == 0
        mock_deploy.assert_called_once()

    def test_no_deploy_flag_skips_modal_deploy(self, temp_project):
        """Without --deploy, _deploy_modal_api() is never called."""
        tmp_path, jid = temp_project

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", return_value=0), \
             patch.object(onboard, "_deploy_modal_api") as mock_deploy, \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
                "--no-validate",
            ])

        assert code == 0
        mock_deploy.assert_not_called()

    def test_registry_updated_during_deploy(self, temp_project):
        """--deploy adds jurisdiction to registry.json."""
        tmp_path, jid = temp_project

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", return_value=0), \
             patch.object(onboard, "_deploy_modal_api", return_value=0), \
             patch.object(onboard, "_verify_jurisdiction", return_value=True), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"):
            self._run_main([
                "--city", "Testville", "--state", "CA",
                "--no-validate", "--deploy",
            ])

        with open(tmp_path / "config" / "registry.json") as f:
            registry = json.load(f)

        assert jid in registry["jurisdictions"]
        assert registry["jurisdictions"][jid]["display_name"] == "Testville"


# ---------------------------------------------------------------------------
# _estimate_cost() — cost extrapolation from sample
# ---------------------------------------------------------------------------

class TestEstimateCost:
    """Tests for _estimate_cost(): extrapolates from sample to full backfill."""

    def test_basic_extrapolation(self):
        """8 meetings in 30 days -> ~97 in 365 days."""
        est = _estimate_cost(sample_meetings=8, sample_days=30, full_days=365)
        assert est["projected_meetings"] == 97  # int(8 * 365/30)
        assert est["total"] > 0

    def test_zero_meetings_zero_cost(self):
        """0 meetings -> meeting cost is 0, still has flat costs."""
        est = _estimate_cost(sample_meetings=0, sample_days=30, full_days=365)
        assert est["projected_meetings"] == 0
        assert est["meeting_cost"] == 0
        assert est["flat_cost"] > 0  # vectors at minimum

    def test_no_meeting_stages(self):
        """has_meetings=False -> 0 projected meetings."""
        est = _estimate_cost(sample_meetings=10, sample_days=30, full_days=365,
                             has_meetings=False)
        assert est["projected_meetings"] == 0

    def test_issues_add_flat_cost(self):
        """has_issues=True adds issue flat cost."""
        with_issues = _estimate_cost(sample_meetings=10, sample_days=30, full_days=365,
                                     has_issues=True)
        without_issues = _estimate_cost(sample_meetings=10, sample_days=30, full_days=365,
                                        has_issues=False)
        assert with_issues["flat_cost"] > without_issues["flat_cost"]

    def test_municipal_adds_flat_cost(self):
        """has_municipal=True adds municipal flat cost."""
        with_muni = _estimate_cost(sample_meetings=10, sample_days=30, full_days=365,
                                   has_municipal=True)
        without_muni = _estimate_cost(sample_meetings=10, sample_days=30, full_days=365,
                                      has_municipal=False)
        assert with_muni["flat_cost"] > without_muni["flat_cost"]

    def test_cost_scales_with_days(self):
        """More days -> proportionally more meetings and cost."""
        short = _estimate_cost(sample_meetings=10, sample_days=30, full_days=90)
        long = _estimate_cost(sample_meetings=10, sample_days=30, full_days=365)
        assert long["projected_meetings"] > short["projected_meetings"]
        assert long["total"] > short["total"]


# ---------------------------------------------------------------------------
# Configurable defaults — YAML overrides for days_past/sample_days
# ---------------------------------------------------------------------------

class TestConfigurableDefaults:
    """Tests for YAML-based default overrides."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Temp project with configs and YAML containing ingestion settings."""
        extraction_dir = tmp_path / "data" / "extraction"
        extraction_dir.mkdir(parents=True)
        jurisdiction_dir = tmp_path / "data" / "jurisdictions"
        jurisdiction_dir.mkdir(parents=True)
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        jid = "city-testville"

        (extraction_dir / f"{jid}.json").write_text(json.dumps({
            "source_type": "legistar",
            "issue_source": "seeclickfix",
        }))

        (config_dir / "registry.json").write_text(json.dumps({
            "version": "1.0",
            "jurisdictions": {},
        }))

        return tmp_path, jid

    def _run_main(self, argv):
        with patch.object(sys, "argv", ["onboard.py"] + argv):
            try:
                onboard.main()
                return 0
            except SystemExit as e:
                return e.code if e.code is not None else 0

    def test_yaml_defaults_used_when_no_cli_flags(self, temp_project):
        """YAML ingestion.days_past/sample_days used when CLI flags omitted."""
        tmp_path, jid = temp_project

        (tmp_path / "data" / "jurisdictions" / f"{jid}.yaml").write_text(yaml.dump({
            "jurisdiction_id": jid,
            "ingestion": {"days_past": 180, "sample_days": 14},
        }))

        modal_calls = []

        def track_modal(jid, days_past, dry_run=False, stages="all"):
            modal_calls.append(days_past)
            return 0

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", side_effect=track_modal), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"), \
             patch("builtins.input", return_value="y"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
            ])

        assert code == 0
        # Sample should use YAML sample_days=14, full should use days_past=180
        assert modal_calls[0] == 14
        assert modal_calls[1] == 180

    def test_cli_flags_override_yaml(self, temp_project):
        """CLI --days-past/--sample-days override YAML values."""
        tmp_path, jid = temp_project

        (tmp_path / "data" / "jurisdictions" / f"{jid}.yaml").write_text(yaml.dump({
            "jurisdiction_id": jid,
            "ingestion": {"days_past": 180, "sample_days": 14},
        }))

        modal_calls = []

        def track_modal(jid, days_past, dry_run=False, stages="all"):
            modal_calls.append(days_past)
            return 0

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", side_effect=track_modal), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"), \
             patch("builtins.input", return_value="y"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
                "--days-past", "90", "--sample-days", "7",
            ])

        assert code == 0
        assert modal_calls[0] == 7   # CLI override
        assert modal_calls[1] == 90  # CLI override

    def test_hardcoded_defaults_when_no_yaml_config(self, temp_project):
        """No ingestion section in YAML -> hardcoded defaults (365/30)."""
        tmp_path, jid = temp_project

        (tmp_path / "data" / "jurisdictions" / f"{jid}.yaml").write_text(yaml.dump({
            "jurisdiction_id": jid,
        }))

        modal_calls = []

        def track_modal(jid, days_past, dry_run=False, stages="all"):
            modal_calls.append(days_past)
            return 0

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", side_effect=track_modal), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"), \
             patch("builtins.input", return_value="y"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
            ])

        assert code == 0
        assert modal_calls[0] == 30   # hardcoded SAMPLE_DAYS
        assert modal_calls[1] == 365  # hardcoded DEFAULT_DAYS_PAST


# ---------------------------------------------------------------------------
# CLI flow — --yes flag and cost estimate prompt
# ---------------------------------------------------------------------------

class TestCostEstimatePrompt:
    """Tests for cost estimate and --yes flag in CLI flow."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        extraction_dir = tmp_path / "data" / "extraction"
        extraction_dir.mkdir(parents=True)
        jurisdiction_dir = tmp_path / "data" / "jurisdictions"
        jurisdiction_dir.mkdir(parents=True)
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        jid = "city-testville"

        (extraction_dir / f"{jid}.json").write_text(json.dumps({
            "source_type": "legistar",
            "issue_source": "seeclickfix",
        }))
        (jurisdiction_dir / f"{jid}.yaml").write_text(yaml.dump({
            "jurisdiction_id": jid,
        }))
        (config_dir / "registry.json").write_text(json.dumps({
            "version": "1.0",
            "jurisdictions": {},
        }))

        return tmp_path, jid

    def _run_main(self, argv):
        with patch.object(sys, "argv", ["onboard.py"] + argv):
            try:
                onboard.main()
                return 0
            except SystemExit as e:
                return e.code if e.code is not None else 0

    def test_yes_flag_skips_prompt(self, temp_project):
        """--yes auto-confirms, no input() call."""
        tmp_path, jid = temp_project

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", return_value=0), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"), \
             patch("builtins.input") as mock_input:
            code = self._run_main([
                "--city", "Testville", "--state", "CA", "--yes",
            ])

        assert code == 0
        mock_input.assert_not_called()

    def test_user_declines_aborts(self, temp_project):
        """User answers 'n' at cost prompt -> exit 0 (clean abort)."""
        tmp_path, jid = temp_project

        modal_calls = []

        def track_modal(jid, days_past, dry_run=False, stages="all"):
            modal_calls.append(days_past)
            return 0

        with patch.object(onboard, "PROJECT_ROOT", tmp_path), \
             patch.object(onboard, "_run_modal_ingestion", side_effect=track_modal), \
             patch.object(onboard, "_get_data_counts", return_value={
                 "meetings": 10, "chunks": 520, "agenda_items": 30,
                 "decisions": 5, "municipal_code": 0,
             }), \
             patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake"}), \
             patch("dotenv.load_dotenv"), \
             patch("builtins.input", return_value="n"):
            code = self._run_main([
                "--city", "Testville", "--state", "CA",
            ])

        assert code == 0
        # Only sample ingestion ran (30 days), full was aborted
        assert len(modal_calls) == 1
        assert modal_calls[0] == 30


# ---------------------------------------------------------------------------
# _run_batch() — batch onboarding
# ---------------------------------------------------------------------------

class TestBatchMode:
    """Tests for batch onboarding via --cities flag."""

    def test_batch_runs_subprocess_per_city(self):
        """Each city in the batch gets its own subprocess invocation."""
        calls = []

        def fake_run(cmd, cwd=None):
            # Extract the --city value from the command
            city_idx = cmd.index("--city") + 1
            calls.append(cmd[city_idx])
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            rc = _run_batch(["Alpha", "Beta", "Gamma"], ["--state", "CA", "--yes"])

        assert rc == 0
        assert calls == ["Alpha", "Beta", "Gamma"]

    def test_batch_reports_failures(self):
        """Failed cities reported in summary, returns 1."""
        call_count = [0]

        def fake_run(cmd, cwd=None):
            call_count[0] += 1
            # Second city fails
            rc = 2 if call_count[0] == 2 else 0
            return MagicMock(returncode=rc)

        with patch("subprocess.run", side_effect=fake_run):
            rc = _run_batch(["Alpha", "Beta", "Gamma"], ["--state", "CA"])

        assert rc == 1  # at least one failure

    def test_batch_all_succeed_returns_zero(self):
        """All cities succeed -> return 0."""
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            rc = _run_batch(["Alpha", "Beta"], ["--state", "CA"])

        assert rc == 0

    def test_batch_passes_shared_flags(self):
        """Shared flags (--state, --county, --yes) passed to each subprocess."""
        last_cmd = [None]

        def fake_run(cmd, cwd=None):
            last_cmd[0] = cmd
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            _run_batch(["TestCity"], ["--state", "CA", "--county", "Marin", "--yes"])

        cmd = last_cmd[0]
        assert "--state" in cmd
        assert "CA" in cmd
        assert "--county" in cmd
        assert "Marin" in cmd
        assert "--yes" in cmd

    def test_cli_cities_flag_triggers_batch(self):
        """--cities flag in CLI triggers batch mode."""
        with patch.object(onboard, "_run_batch", return_value=0) as mock_batch:
            with patch.object(sys, "argv", [
                "onboard.py", "--cities", "Alpha,Beta", "--state", "CA", "--yes"
            ]):
                try:
                    onboard.main()
                except SystemExit:
                    pass

        mock_batch.assert_called_once()
        cities = mock_batch.call_args[0][0]
        assert cities == ["Alpha", "Beta"]


# ---------------------------------------------------------------------------
# detect_youtube_channel() — YouTube channel auto-detection
# ---------------------------------------------------------------------------

class TestDetectYoutubeChannel:
    """Tests for detect_youtube_channel() from civicos_extraction.onboard."""

    def _get_detect_fn(self):
        from civicos_extraction.onboard import detect_youtube_channel
        return detect_youtube_channel

    def test_returns_channel_on_match(self):
        """API returns channel matching city name -> returns channel info."""
        detect = self._get_detect_fn()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [{
                "snippet": {
                    "channelId": "UC123abc",
                    "title": "City of Testville",
                },
            }],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response), \
             patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key"}):
            result = detect("Testville", "CA")

        assert result is not None
        assert result["channel_id"] == "UC123abc"
        assert result["channel_title"] == "City of Testville"

    def test_returns_none_without_api_key(self):
        """No API key -> returns None, no API call."""
        detect = self._get_detect_fn()
        with patch.dict(os.environ, {}, clear=True), \
             patch("requests.get") as mock_get:
            # Remove keys if they exist
            os.environ.pop("YOUTUBE_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            result = detect("Testville")

        assert result is None
        mock_get.assert_not_called()

    def test_returns_none_on_empty_results(self):
        """API returns 0 channels -> returns None."""
        detect = self._get_detect_fn()
        mock_response = MagicMock()
        mock_response.json.return_value = {"items": []}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response), \
             patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key"}):
            result = detect("Testville")

        assert result is None

    def test_returns_none_on_api_error(self):
        """API error -> returns None (doesn't crash)."""
        detect = self._get_detect_fn()
        with patch("requests.get", side_effect=Exception("API error")), \
             patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key"}):
            result = detect("Testville")

        assert result is None

    def test_prefers_channel_matching_city_name(self):
        """When multiple channels returned, prefers one with city name in title."""
        detect = self._get_detect_fn()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {"snippet": {"channelId": "UC_wrong", "title": "Random Government Channel"}},
                {"snippet": {"channelId": "UC_right", "title": "Testville City Council"}},
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response), \
             patch.dict(os.environ, {"YOUTUBE_API_KEY": "fake-key"}):
            result = detect("Testville")

        assert result["channel_id"] == "UC_right"
