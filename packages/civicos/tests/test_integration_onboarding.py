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
