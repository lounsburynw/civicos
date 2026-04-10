"""
Tests for the pipeline monitor CLI module.

Tests parse_timestamp, PipelineStatus, MonitorReport, check_pipeline_status,
check_all_pipelines, format_report_text, and run_monitor.
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from civicos_extraction.cli.monitor import (
    PIPELINE_CONFIG,
    MonitorReport,
    PipelineStatus,
    check_all_pipelines,
    check_pipeline_status,
    format_report_text,
    parse_timestamp,
    run_monitor,
)


# ---------------------------------------------------------------------------
# parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_parses_iso_timestamp_without_microseconds(self):
        result = parse_timestamp("2026-04-01T10:30:00")
        assert result == datetime(2026, 4, 1, 10, 30, 0)

    def test_parses_iso_timestamp_with_microseconds(self):
        result = parse_timestamp("2026-04-01T10:30:00.123456")
        assert result == datetime(2026, 4, 1, 10, 30, 0, 123456)

    def test_returns_none_for_empty_string(self):
        assert parse_timestamp("") is None

    def test_returns_none_for_invalid_format(self):
        assert parse_timestamp("not-a-date") is None

    def test_returns_none_for_none_input(self):
        assert parse_timestamp(None) is None

    def test_parses_date_only_iso(self):
        result = parse_timestamp("2026-04-01")
        assert result == datetime(2026, 4, 1)


# ---------------------------------------------------------------------------
# PipelineStatus.to_dict
# ---------------------------------------------------------------------------


class TestPipelineStatusToDict:
    def test_to_dict_with_all_fields(self):
        ts = datetime(2026, 4, 1, 10, 0, 0)
        status = PipelineStatus(
            pipeline="discover",
            checkpoint_file="city-san-rafael.json",
            last_run=ts,
            age_hours=5.456,
            max_age_hours=30,
            is_overdue=False,
            status="healthy",
            message="Last run 5.5h ago (Daily 6:00 AM)",
        )
        d = status.to_dict()
        assert d["pipeline"] == "discover"
        assert d["checkpoint_file"] == "city-san-rafael.json"
        assert d["last_run"] == "2026-04-01T10:00:00"
        assert d["age_hours"] == 5.5  # rounded to 1 decimal
        assert d["max_age_hours"] == 30
        assert d["is_overdue"] is False
        assert d["status"] == "healthy"
        assert d["message"] == "Last run 5.5h ago (Daily 6:00 AM)"

    def test_to_dict_with_none_fields(self):
        status = PipelineStatus(
            pipeline="discover",
            checkpoint_file="",
            last_run=None,
            age_hours=None,
            max_age_hours=0,
            is_overdue=False,
            status="error",
            message="Unknown pipeline",
        )
        d = status.to_dict()
        assert d["last_run"] is None
        assert d["age_hours"] is None

    def test_age_hours_rounding(self):
        status = PipelineStatus(
            pipeline="x",
            checkpoint_file="x.json",
            last_run=datetime.now(),
            age_hours=12.349,
            max_age_hours=30,
            is_overdue=False,
            status="healthy",
            message="ok",
        )
        assert status.to_dict()["age_hours"] == 12.3


# ---------------------------------------------------------------------------
# MonitorReport.to_dict
# ---------------------------------------------------------------------------


class TestMonitorReportToDict:
    def test_to_dict_summary_counts(self):
        pipelines = [
            PipelineStatus("a", "a.json", None, None, 30, False, "healthy", "ok"),
            PipelineStatus("b", "b.json", None, None, 30, True, "overdue", "late"),
            PipelineStatus("c", "c.json", None, None, 30, True, "missing", "gone"),
        ]
        ts = datetime(2026, 4, 1, 12, 0, 0)
        report = MonitorReport(
            checked_at=ts,
            pipelines=pipelines,
            healthy_count=1,
            overdue_count=1,
            missing_count=1,
            error_count=0,
        )
        d = report.to_dict()
        assert d["checked_at"] == "2026-04-01T12:00:00"
        assert d["summary"]["healthy"] == 1
        assert d["summary"]["overdue"] == 1
        assert d["summary"]["missing"] == 1
        assert d["summary"]["error"] == 0
        assert d["summary"]["total"] == 3
        assert len(d["pipelines"]) == 3
        assert d["pipelines"][0]["pipeline"] == "a"


# ---------------------------------------------------------------------------
# check_pipeline_status
# ---------------------------------------------------------------------------


class TestCheckPipelineStatus:
    def test_unknown_pipeline_returns_error(self, tmp_path):
        status = check_pipeline_status("nonexistent", tmp_path)
        assert status.status == "error"
        assert status.pipeline == "nonexistent"
        assert status.checkpoint_file == ""
        assert "Unknown pipeline" in status.message

    def test_missing_checkpoint_file_returns_missing(self, tmp_path):
        status = check_pipeline_status("discover", tmp_path, jurisdiction_id="city-test")
        assert status.status == "missing"
        assert status.is_overdue is True
        assert status.checkpoint_file == "city-test.json"
        assert status.last_run is None
        assert "No checkpoint file found" in status.message

    def test_corrupt_json_returns_error(self, tmp_path):
        cp_file = tmp_path / "city-test.json"
        cp_file.write_text("not valid json {{{")
        status = check_pipeline_status("discover", tmp_path, jurisdiction_id="city-test")
        assert status.status == "error"
        assert status.is_overdue is True
        assert "Failed to read checkpoint" in status.message

    def test_missing_timestamp_field_returns_error(self, tmp_path):
        cp_file = tmp_path / "city-test.json"
        cp_file.write_text(json.dumps({"some_other_field": "value"}))
        status = check_pipeline_status("discover", tmp_path, jurisdiction_id="city-test")
        assert status.status == "error"
        assert "No valid timestamp" in status.message
        assert "checkpoint_at" in status.message  # the expected field name

    def test_invalid_timestamp_value_returns_error(self, tmp_path):
        cp_file = tmp_path / "city-test.json"
        cp_file.write_text(json.dumps({"checkpoint_at": "garbage"}))
        status = check_pipeline_status("discover", tmp_path, jurisdiction_id="city-test")
        assert status.status == "error"
        assert "No valid timestamp" in status.message

    def test_healthy_pipeline_recent_checkpoint(self, tmp_path):
        recent_ts = (datetime.now() - timedelta(hours=2)).isoformat()
        cp_file = tmp_path / "city-test.json"
        cp_file.write_text(json.dumps({"checkpoint_at": recent_ts}))

        status = check_pipeline_status("discover", tmp_path, jurisdiction_id="city-test")
        assert status.status == "healthy"
        assert status.is_overdue is False
        assert status.age_hours is not None
        assert status.age_hours < 30  # within default_max_age_hours
        assert status.max_age_hours == 30
        assert "Daily 6:00 AM" in status.message

    def test_overdue_pipeline_old_checkpoint(self, tmp_path):
        old_ts = (datetime.now() - timedelta(hours=48)).isoformat()
        cp_file = tmp_path / "city-test.json"
        cp_file.write_text(json.dumps({"checkpoint_at": old_ts}))

        status = check_pipeline_status("discover", tmp_path, jurisdiction_id="city-test")
        assert status.status == "overdue"
        assert status.is_overdue is True
        assert status.age_hours > 30
        assert "exceeds" in status.message
        assert "30" in status.message  # threshold mentioned

    def test_custom_max_age_overrides_default(self, tmp_path):
        # Checkpoint is 5 hours old, default max is 30, custom max is 3
        ts = (datetime.now() - timedelta(hours=5)).isoformat()
        cp_file = tmp_path / "city-test.json"
        cp_file.write_text(json.dumps({"checkpoint_at": ts}))

        status = check_pipeline_status(
            "discover", tmp_path, jurisdiction_id="city-test", max_age_hours=3
        )
        assert status.status == "overdue"
        assert status.max_age_hours == 3

    def test_custom_max_age_healthy(self, tmp_path):
        # Checkpoint is 5 hours old, custom max is 10 → healthy
        ts = (datetime.now() - timedelta(hours=5)).isoformat()
        cp_file = tmp_path / "city-test.json"
        cp_file.write_text(json.dumps({"checkpoint_at": ts}))

        status = check_pipeline_status(
            "discover", tmp_path, jurisdiction_id="city-test", max_age_hours=10
        )
        assert status.status == "healthy"
        assert status.max_age_hours == 10

    def test_youtube_pipeline_checkpoint_pattern(self, tmp_path):
        ts = (datetime.now() - timedelta(hours=1)).isoformat()
        cp_file = tmp_path / "youtube_city-test.json"
        cp_file.write_text(json.dumps({"timestamp": ts}))

        status = check_pipeline_status("youtube", tmp_path, jurisdiction_id="city-test")
        assert status.status == "healthy"
        assert status.checkpoint_file == "youtube_city-test.json"

    def test_legislative_pipeline_uses_state_and_topic(self, tmp_path):
        ts = (datetime.now() - timedelta(hours=10)).isoformat()
        cp_file = tmp_path / "legislative_california_housing.json"
        cp_file.write_text(json.dumps({"timestamp": ts}))

        status = check_pipeline_status(
            "legislative",
            tmp_path,
            state="california",
            topic="housing",
        )
        assert status.status == "healthy"
        assert status.checkpoint_file == "legislative_california_housing.json"
        assert status.max_age_hours == 192  # default for legislative

    def test_overdue_boundary_exactly_at_max_age(self, tmp_path):
        """A pipeline exactly at the max age threshold is NOT overdue (> not >=)."""
        # Make checkpoint exactly 30 hours old — this is NOT overdue
        # because the check uses > (strictly greater than)
        # We can't test exact boundary due to timing, so test just under
        ts = (datetime.now() - timedelta(hours=29, minutes=59)).isoformat()
        cp_file = tmp_path / "city-test.json"
        cp_file.write_text(json.dumps({"checkpoint_at": ts}))

        status = check_pipeline_status("discover", tmp_path, jurisdiction_id="city-test")
        assert status.status == "healthy"
        assert status.is_overdue is False

    def test_seeclickfix_pipeline_pattern(self, tmp_path):
        ts = (datetime.now() - timedelta(hours=2)).isoformat()
        cp_file = tmp_path / "seeclickfix_city-test.json"
        cp_file.write_text(json.dumps({"timestamp": ts}))

        status = check_pipeline_status("seeclickfix", tmp_path, jurisdiction_id="city-test")
        assert status.status == "healthy"
        assert status.checkpoint_file == "seeclickfix_city-test.json"

    def test_audio_pipeline_pattern(self, tmp_path):
        ts = (datetime.now() - timedelta(hours=2)).isoformat()
        cp_file = tmp_path / "audio_city-test.json"
        cp_file.write_text(json.dumps({"timestamp": ts}))

        status = check_pipeline_status("audio", tmp_path, jurisdiction_id="city-test")
        assert status.status == "healthy"
        assert status.checkpoint_file == "audio_city-test.json"

    def test_transcribe_pipeline_pattern(self, tmp_path):
        ts = (datetime.now() - timedelta(hours=2)).isoformat()
        cp_file = tmp_path / "transcribe_city-test.json"
        cp_file.write_text(json.dumps({"timestamp": ts}))

        status = check_pipeline_status("transcribe", tmp_path, jurisdiction_id="city-test")
        assert status.status == "healthy"
        assert status.checkpoint_file == "transcribe_city-test.json"


# ---------------------------------------------------------------------------
# check_all_pipelines
# ---------------------------------------------------------------------------


class TestCheckAllPipelines:
    def test_all_pipelines_missing(self, tmp_path):
        report = check_all_pipelines(tmp_path)
        assert len(report.pipelines) == len(PIPELINE_CONFIG)
        assert report.missing_count == len(PIPELINE_CONFIG)
        assert report.healthy_count == 0
        assert report.overdue_count == 0
        assert report.error_count == 0

    def test_mixed_statuses(self, tmp_path):
        # Create only the discover checkpoint (healthy)
        ts = (datetime.now() - timedelta(hours=2)).isoformat()
        cp_file = tmp_path / "city-san-rafael.json"
        cp_file.write_text(json.dumps({"checkpoint_at": ts}))

        report = check_all_pipelines(tmp_path)
        assert report.healthy_count == 1
        # Remaining pipelines are missing
        assert report.missing_count == len(PIPELINE_CONFIG) - 1
        assert len(report.pipelines) == len(PIPELINE_CONFIG)

    def test_custom_max_age_applied_to_all(self, tmp_path):
        # Create a discover checkpoint 5 hours old; with max_age=3, it's overdue
        ts = (datetime.now() - timedelta(hours=5)).isoformat()
        cp_file = tmp_path / "city-san-rafael.json"
        cp_file.write_text(json.dumps({"checkpoint_at": ts}))

        report = check_all_pipelines(tmp_path, max_age_hours=3)
        discover_status = next(p for p in report.pipelines if p.pipeline == "discover")
        assert discover_status.status == "overdue"
        assert discover_status.max_age_hours == 3

    def test_passes_jurisdiction_to_pipelines(self, tmp_path):
        ts = (datetime.now() - timedelta(hours=1)).isoformat()
        # Use a custom jurisdiction
        cp_file = tmp_path / "city-mill-valley.json"
        cp_file.write_text(json.dumps({"checkpoint_at": ts}))

        report = check_all_pipelines(tmp_path, jurisdiction_id="city-mill-valley")
        discover_status = next(p for p in report.pipelines if p.pipeline == "discover")
        assert discover_status.status == "healthy"
        assert discover_status.checkpoint_file == "city-mill-valley.json"


# ---------------------------------------------------------------------------
# format_report_text
# ---------------------------------------------------------------------------


class TestFormatReportText:
    def _make_report(self, statuses, checked_at=None):
        ts = checked_at or datetime(2026, 4, 1, 12, 0, 0)
        return MonitorReport(
            checked_at=ts,
            pipelines=statuses,
            healthy_count=sum(1 for s in statuses if s.status == "healthy"),
            overdue_count=sum(1 for s in statuses if s.status == "overdue"),
            missing_count=sum(1 for s in statuses if s.status == "missing"),
            error_count=sum(1 for s in statuses if s.status == "error"),
        )

    def test_header_contains_title_and_timestamp(self):
        report = self._make_report([])
        text = format_report_text(report)
        assert "CIVIC PIPELINE MONITOR" in text
        assert "2026-04-01 12:00:00" in text

    def test_summary_shows_healthy_count(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, 2.0, 30, False, "healthy", "ok"),
            PipelineStatus("youtube", "y.json", None, 2.0, 30, False, "healthy", "ok"),
        ]
        report = self._make_report(statuses)
        text = format_report_text(report)
        assert "2/2 healthy" in text

    def test_overdue_warning_shown(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, 50.0, 30, True, "overdue", "late"),
        ]
        report = self._make_report(statuses)
        text = format_report_text(report)
        assert "WARNING: 1 overdue" in text

    def test_missing_warning_shown(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, None, 30, True, "missing", "gone"),
        ]
        report = self._make_report(statuses)
        text = format_report_text(report)
        assert "WARNING: 1 missing" in text

    def test_error_count_shown(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, None, 30, False, "error", "bad"),
        ]
        report = self._make_report(statuses)
        text = format_report_text(report)
        assert "ERROR: 1 errors" in text

    def test_healthy_icon(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, 2.0, 30, False, "healthy", "ok"),
        ]
        text = format_report_text(self._make_report(statuses))
        # The healthy icon is a checkmark
        assert "\u2713" in text  # ✓

    def test_overdue_icon(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, 50.0, 30, True, "overdue", "late"),
        ]
        text = format_report_text(self._make_report(statuses))
        assert "\u26a0" in text  # ⚠

    def test_missing_icon(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, None, 30, True, "missing", "no file"),
        ]
        text = format_report_text(self._make_report(statuses))
        assert "\u2717" in text  # ✗

    def test_error_icon(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, None, 30, False, "error", "bad"),
        ]
        text = format_report_text(self._make_report(statuses))
        assert "!" in text

    def test_pipeline_description_from_config(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, 2.0, 30, False, "healthy", "ok"),
        ]
        text = format_report_text(self._make_report(statuses))
        assert "Meeting discovery" in text

    def test_message_included_in_output(self):
        msg = "Last run 5.5h ago (Daily 6:00 AM)"
        statuses = [
            PipelineStatus("discover", "x.json", None, 5.5, 30, False, "healthy", msg),
        ]
        text = format_report_text(self._make_report(statuses))
        assert msg in text

    def test_no_warnings_when_all_healthy(self):
        statuses = [
            PipelineStatus("discover", "x.json", None, 2.0, 30, False, "healthy", "ok"),
        ]
        text = format_report_text(self._make_report(statuses))
        assert "WARNING" not in text
        assert "ERROR" not in text


# ---------------------------------------------------------------------------
# run_monitor
# ---------------------------------------------------------------------------


class TestRunMonitor:
    def _make_args(self, **kwargs):
        defaults = {
            "check_all": True,
            "pipeline": None,
            "jurisdiction": "city-san-rafael",
            "state": "california",
            "topic": "housing",
            "max_age": None,
            "format": "text",
            "exit_on_overdue": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_returns_1_when_checkpoint_dir_missing(self, monkeypatch):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: Path("/nonexistent/path"),
        )
        args = self._make_args()
        result = run_monitor(args)
        assert result == 1

    def test_returns_0_for_healthy_pipelines(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: tmp_path,
        )
        # Create a recent checkpoint for discover
        ts = (datetime.now() - timedelta(hours=1)).isoformat()
        (tmp_path / "city-san-rafael.json").write_text(json.dumps({"checkpoint_at": ts}))

        args = self._make_args()
        result = run_monitor(args)
        assert result == 0

    def test_exit_on_overdue_returns_1_when_overdue(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: tmp_path,
        )
        # No checkpoint files → all missing → exit_on_overdue triggers
        args = self._make_args(exit_on_overdue=True)
        result = run_monitor(args)
        assert result == 1

    def test_exit_on_overdue_returns_0_when_all_healthy(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: tmp_path,
        )
        # Create recent checkpoints for ALL pipelines
        ts = (datetime.now() - timedelta(hours=1)).isoformat()
        for pipeline, config in PIPELINE_CONFIG.items():
            pattern = config["checkpoint_pattern"]
            if "{jurisdiction_id}" in pattern:
                fname = pattern.format(jurisdiction_id="city-san-rafael")
            elif "{state}" in pattern and "{topic}" in pattern:
                fname = pattern.format(state="california", topic="housing")
            else:
                fname = pattern
            (tmp_path / fname).write_text(
                json.dumps({config["timestamp_field"]: ts})
            )

        args = self._make_args(exit_on_overdue=True)
        result = run_monitor(args)
        assert result == 0

    def test_json_format_outputs_valid_json(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: tmp_path,
        )
        ts = (datetime.now() - timedelta(hours=1)).isoformat()
        (tmp_path / "city-san-rafael.json").write_text(json.dumps({"checkpoint_at": ts}))

        args = self._make_args(format="json")
        run_monitor(args)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "summary" in parsed
        assert "pipelines" in parsed
        assert parsed["summary"]["total"] == len(PIPELINE_CONFIG)

    def test_text_format_outputs_report(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: tmp_path,
        )
        args = self._make_args(format="text")
        run_monitor(args)

        captured = capsys.readouterr()
        assert "CIVIC PIPELINE MONITOR" in captured.out

    def test_specific_pipeline_mode(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: tmp_path,
        )
        ts = (datetime.now() - timedelta(hours=1)).isoformat()
        (tmp_path / "city-san-rafael.json").write_text(json.dumps({"checkpoint_at": ts}))

        args = self._make_args(pipeline="discover", format="json")
        result = run_monitor(args)

        assert result == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        # Only one pipeline in the report
        assert parsed["summary"]["total"] == 1
        assert parsed["pipelines"][0]["pipeline"] == "discover"
        assert parsed["pipelines"][0]["status"] == "healthy"

    def test_specific_pipeline_missing_returns_correct_status(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: tmp_path,
        )
        args = self._make_args(pipeline="youtube", format="json", exit_on_overdue=True)
        result = run_monitor(args)

        assert result == 1
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["summary"]["missing"] == 1
        assert parsed["pipelines"][0]["status"] == "missing"

    def test_custom_jurisdiction_propagated(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            "civicos_extraction.cli.monitor.get_checkpoint_dir",
            lambda: tmp_path,
        )
        ts = (datetime.now() - timedelta(hours=1)).isoformat()
        (tmp_path / "city-mill-valley.json").write_text(json.dumps({"checkpoint_at": ts}))

        args = self._make_args(
            pipeline="discover",
            jurisdiction="city-mill-valley",
            format="json",
        )
        run_monitor(args)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["pipelines"][0]["checkpoint_file"] == "city-mill-valley.json"
        assert parsed["pipelines"][0]["status"] == "healthy"


# ---------------------------------------------------------------------------
# PIPELINE_CONFIG structure
# ---------------------------------------------------------------------------


class TestPipelineConfig:
    def test_all_pipelines_have_required_fields(self):
        required = {
            "description",
            "checkpoint_pattern",
            "timestamp_field",
            "default_max_age_hours",
            "schedule",
        }
        for name, config in PIPELINE_CONFIG.items():
            missing = required - set(config.keys())
            assert missing == set(), f"Pipeline '{name}' missing fields: {missing}"

    def test_pipeline_count(self):
        assert len(PIPELINE_CONFIG) == 6

    def test_discover_default_max_age(self):
        assert PIPELINE_CONFIG["discover"]["default_max_age_hours"] == 30

    def test_legislative_default_max_age(self):
        assert PIPELINE_CONFIG["legislative"]["default_max_age_hours"] == 192
