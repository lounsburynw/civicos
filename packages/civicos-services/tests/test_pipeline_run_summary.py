"""
Tests for pipeline_run_summary.py — pipeline result analysis, anomaly detection,
summary text formatting, and notification dispatch.

Mocks the external notification backend (`send_notification`) but exercises the
real analysis and formatting logic with synthetic pipeline result dicts.

To run:
    pytest packages/civicos-services/tests/test_pipeline_run_summary.py -q --override-ini="addopts="
"""

from unittest.mock import patch

import pytest

from civicos_services.monitoring.notify import Priority
from civicos_services.monitoring.pipeline_run_summary import (
    _analyze_results,
    _build_summary_text,
    _global_stage_metric,
    _stage_metric,
    send_pipeline_summary,
)


# ---------------------------------------------------------------------------
# _analyze_results: per-jurisdiction counting
# ---------------------------------------------------------------------------


class TestAnalyzeResultsPerJurisdiction:
    def test_counts_successful_stages(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 3},
                "videos": {"status": "ok", "videos_discovered": 2},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert analysis["stages_succeeded"] == 2
        assert analysis["stages_failed"] == 0
        assert analysis["failed_stages"] == []

    def test_counts_failed_stages_with_namespaced_name(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 1},
                "videos": {"status": "failed", "error": "timeout"},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert analysis["stages_succeeded"] == 1
        assert analysis["stages_failed"] == 1
        assert analysis["failed_stages"] == [
            {"stage": "city-san-rafael/videos", "error": "timeout"},
        ]

    def test_failed_stage_missing_error_defaults_to_unknown(self):
        results = {
            "city-san-rafael": {
                "videos": {"status": "failed"},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert analysis["failed_stages"][0]["error"] == "unknown"

    def test_non_dict_stage_results_are_skipped(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok"},
                "summary_note": "a string, not a stage dict",
                "error_count": 5,
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert analysis["stages_succeeded"] == 1
        assert analysis["stages_failed"] == 0

    def test_non_dict_top_level_values_skipped(self):
        results = {
            "total_seconds": 42.0,
            "city-san-rafael": {
                "meetings": {"status": "ok"},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert analysis["stages_succeeded"] == 1
        assert "city-san-rafael" in analysis["per_jurisdiction"]
        assert "total_seconds" not in analysis["per_jurisdiction"]

    def test_per_jurisdiction_preserves_stage_details(self):
        stage = {"status": "ok", "meetings_stored": 7, "note": "refreshed"}
        results = {"city-test": {"meetings": stage}}
        analysis = _analyze_results(results, "high_velocity_daily")

        assert analysis["per_jurisdiction"]["city-test"]["meetings"] == stage


# ---------------------------------------------------------------------------
# _analyze_results: global stage handling
# ---------------------------------------------------------------------------


class TestAnalyzeResultsGlobalStages:
    def test_global_stage_success_counted(self):
        results = {
            "legislation_CA": {"status": "ok", "bills_stored": 1000, "new_bills": 15},
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert analysis["stages_succeeded"] == 1
        assert analysis["stages_failed"] == 0
        assert "legislation_CA" in analysis["global_stages"]
        # Global stages are not treated as per-jurisdiction buckets
        assert "legislation_CA" not in analysis["per_jurisdiction"]

    def test_global_stage_failure_uses_unnamespaced_name(self):
        results = {
            "federal_rules": {"status": "failed", "error": "Federal Register 503"},
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert analysis["stages_failed"] == 1
        assert analysis["failed_stages"] == [
            {"stage": "federal_rules", "error": "Federal Register 503"},
        ]

    def test_all_six_global_keys_recognized(self):
        results = {
            "legislation_CA": {"status": "ok"},
            "executive_orders": {"status": "ok"},
            "federal_rules": {"status": "ok"},
            "legislative_events_CA": {"status": "ok"},
            "federal_programs": {"status": "ok"},
            "hud_allocations": {"status": "ok"},
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert analysis["stages_succeeded"] == 6
        assert len(analysis["global_stages"]) == 6
        assert analysis["per_jurisdiction"] == {}


# ---------------------------------------------------------------------------
# _analyze_results: high-velocity anomaly detection
# ---------------------------------------------------------------------------


class TestAnalyzeResultsHighVelocityAnomalies:
    def test_zero_meetings_discovered_flagged(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 0},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert "city-san-rafael: 0 meetings discovered" in analysis["anomalies"]

    def test_failed_meetings_not_flagged_as_zero_anomaly(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "failed", "meetings_stored": 0, "error": "boom"},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        # Failure is reported as a failed stage, not as a "0 meetings" anomaly.
        assert "city-san-rafael: 0 meetings discovered" not in analysis["anomalies"]

    def test_zero_videos_discovered_flagged(self):
        results = {
            "city-san-rafael": {
                "videos": {"status": "ok", "videos_discovered": 0},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert "city-san-rafael: 0 videos discovered" in analysis["anomalies"]

    def test_transcript_duration_issues_flagged_with_count(self):
        results = {
            "city-san-rafael": {
                "transcripts": {"status": "ok", "duration_validation_issues": 3},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert "city-san-rafael: 3 transcript duration validation issues" in analysis["anomalies"]

    def test_zero_transcript_duration_issues_not_flagged(self):
        results = {
            "city-san-rafael": {
                "transcripts": {"status": "ok", "duration_validation_issues": 0},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert analysis["anomalies"] == []

    def test_non_zero_meetings_stored_does_not_trigger_anomaly(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 5},
                "videos": {"status": "ok", "videos_discovered": 2},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert analysis["anomalies"] == []


# ---------------------------------------------------------------------------
# _analyze_results: low-velocity anomaly detection
# ---------------------------------------------------------------------------


class TestAnalyzeResultsLowVelocityAnomalies:
    def test_zero_ca_bills_flagged(self):
        results = {
            "legislation_CA": {"status": "ok", "bills_stored": 0},
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert "CA legislation: 0 bills stored (possible API issue)" in analysis["anomalies"]

    def test_non_zero_ca_bills_not_flagged(self):
        results = {
            "legislation_CA": {"status": "ok", "bills_stored": 500},
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert analysis["anomalies"] == []

    def test_zero_federal_programs_flagged(self):
        results = {
            "federal_programs": {"status": "ok", "programs_stored": 0},
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert "Federal programs: 0 programs stored (possible SAM.gov API issue)" in analysis["anomalies"]

    def test_zero_federal_rules_flagged(self):
        results = {
            "federal_rules": {"status": "ok", "rules_stored": 0},
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert "Federal rules: 0 rules stored (possible Federal Register API issue)" in analysis["anomalies"]

    def test_zero_municipal_code_sections_flagged_per_jurisdiction(self):
        results = {
            "city-san-rafael": {
                "municipal_code": {"status": "ok", "sections_stored": 0},
            },
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert (
            "city-san-rafael: 0 municipal code sections (possible Municode API issue)"
            in analysis["anomalies"]
        )

    def test_low_velocity_ignores_high_velocity_anomalies(self):
        # Zero-meetings is only a high-velocity concern.
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 0},
            },
        }
        analysis = _analyze_results(results, "low_velocity_weekly")

        assert analysis["anomalies"] == []


# ---------------------------------------------------------------------------
# _analyze_results: "all failed" anomaly
# ---------------------------------------------------------------------------


class TestAnalyzeResultsAllFailed:
    def test_all_failed_adds_investigation_anomaly(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "failed", "error": "db down"},
                "videos": {"status": "failed", "error": "db down"},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert "ALL stages failed - investigate immediately" in analysis["anomalies"]

    def test_some_succeeded_no_all_failed_anomaly(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 1},
                "videos": {"status": "failed", "error": "network"},
            },
        }
        analysis = _analyze_results(results, "high_velocity_daily")

        assert "ALL stages failed - investigate immediately" not in analysis["anomalies"]

    def test_empty_results_no_all_failed_anomaly(self):
        analysis = _analyze_results({}, "high_velocity_daily")

        assert analysis["stages_succeeded"] == 0
        assert analysis["stages_failed"] == 0
        assert analysis["anomalies"] == []


# ---------------------------------------------------------------------------
# _stage_metric
# ---------------------------------------------------------------------------


class TestStageMetric:
    def test_meetings_metric(self):
        assert _stage_metric("meetings", {"meetings_stored": 7}) == "7 stored"

    def test_videos_metric(self):
        assert _stage_metric("videos", {"videos_discovered": 12}) == "12 found"

    def test_transcripts_metric(self):
        assert _stage_metric("transcripts", {"transcripts_extracted": 4}) == "4 transcribed"

    def test_chunks_metric(self):
        assert _stage_metric("chunks", {"chunks_extracted": 100}) == "100 chunks"

    def test_agenda_items_metric(self):
        assert _stage_metric("agenda_items", {"items_extracted": 50}) == "50 items"

    def test_decisions_metric(self):
        assert _stage_metric("decisions", {"decisions_extracted": 9}) == "9 decisions"

    def test_issues_metric(self):
        assert _stage_metric("issues", {"issues_stored": 25}) == "25 stored"

    def test_municipal_code_metric(self):
        assert _stage_metric("municipal_code", {"sections_stored": 1000}) == "1000 sections"

    def test_unknown_stage_returns_ok(self):
        assert _stage_metric("unknown_stage", {"some_key": 5}) == "ok"

    def test_known_stage_missing_metric_key_returns_ok(self):
        # meetings stage expects "meetings_stored"; without it we get the default.
        assert _stage_metric("meetings", {"status": "ok"}) == "ok"

    def test_zero_values_still_render(self):
        assert _stage_metric("meetings", {"meetings_stored": 0}) == "0 stored"


# ---------------------------------------------------------------------------
# _global_stage_metric
# ---------------------------------------------------------------------------


class TestGlobalStageMetric:
    def test_legislation_ca_new_and_stored(self):
        assert (
            _global_stage_metric("legislation_CA", {"new_bills": 5, "bills_stored": 100})
            == "5 new, 100 total"
        )

    def test_legislation_ca_missing_keys_default_to_zero(self):
        assert _global_stage_metric("legislation_CA", {}) == "0 new, 0 total"

    def test_executive_orders_metric(self):
        assert _global_stage_metric("executive_orders", {"orders_stored": 3}) == "3 stored"

    def test_federal_rules_metric(self):
        assert _global_stage_metric("federal_rules", {"rules_stored": 42}) == "42 rules"

    def test_legislative_events_ca_metric(self):
        assert (
            _global_stage_metric("legislative_events_CA", {"events_stored": 8})
            == "8 events"
        )

    def test_federal_programs_metric(self):
        assert _global_stage_metric("federal_programs", {"programs_stored": 15}) == "15 programs"

    def test_hud_allocations_metric(self):
        assert (
            _global_stage_metric("hud_allocations", {"total_allocations_stored": 200})
            == "200 allocations"
        )

    def test_unknown_global_stage_returns_empty_string(self):
        assert _global_stage_metric("not_a_real_stage", {"foo": 1}) == ""


# ---------------------------------------------------------------------------
# _build_summary_text
# ---------------------------------------------------------------------------


def _analysis(
    succeeded=0,
    failed=0,
    failed_stages=None,
    anomalies=None,
    per_jurisdiction=None,
    global_stages=None,
):
    return {
        "stages_succeeded": succeeded,
        "stages_failed": failed,
        "failed_stages": failed_stages or [],
        "anomalies": anomalies or [],
        "per_jurisdiction": per_jurisdiction or {},
        "global_stages": global_stages or {},
    }


class TestBuildSummaryText:
    def test_header_contains_stage_ratio(self):
        analysis = _analysis(succeeded=3, failed=1)
        text = _build_summary_text(analysis, "high_velocity_daily", 120.0, 0.0)

        assert "Stages: 3/4 passed" in text

    def test_duration_in_minutes(self):
        analysis = _analysis(succeeded=1)
        text = _build_summary_text(analysis, "high_velocity_daily", 150.0, 0.0)

        # 150s = 2.5 min
        assert "Duration: 2.5 min" in text

    def test_transcription_cost_shown_for_high_velocity_when_positive(self):
        analysis = _analysis(succeeded=1)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 1.37)

        assert "Transcription cost: $1.37" in text

    def test_transcription_cost_omitted_when_zero(self):
        analysis = _analysis(succeeded=1)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        assert "Transcription cost" not in text

    def test_transcription_cost_omitted_for_low_velocity(self):
        analysis = _analysis(succeeded=1)
        text = _build_summary_text(analysis, "low_velocity_weekly", 60.0, 5.00)

        assert "Transcription cost" not in text

    def test_high_velocity_per_jurisdiction_summary_rendered(self):
        per_j = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 4},
                "videos": {"status": "ok", "videos_discovered": 2},
            },
        }
        analysis = _analysis(succeeded=2, per_jurisdiction=per_j)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        assert "city-san-rafael: meetings: 4 stored, videos: 2 found" in text

    def test_high_velocity_failed_stage_shown_as_FAILED(self):
        per_j = {
            "city-san-rafael": {
                "videos": {"status": "failed", "error": "no network"},
            },
        }
        analysis = _analysis(failed=1, per_jurisdiction=per_j)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        assert "city-san-rafael: videos: FAILED" in text

    def test_high_velocity_limits_to_first_5_jurisdictions(self):
        per_j = {
            f"city-{i}": {"meetings": {"status": "ok", "meetings_stored": 1}}
            for i in range(7)
        }
        analysis = _analysis(succeeded=7, per_jurisdiction=per_j)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        # First 5 must appear, last 2 must not.
        for i in range(5):
            assert f"city-{i}:" in text
        assert "city-5:" not in text
        assert "city-6:" not in text

    def test_low_velocity_global_stages_rendered(self):
        globals_ = {
            "legislation_CA": {"status": "ok", "new_bills": 3, "bills_stored": 200},
            "federal_rules": {"status": "ok", "rules_stored": 42},
        }
        analysis = _analysis(succeeded=2, global_stages=globals_)
        text = _build_summary_text(analysis, "low_velocity_weekly", 60.0, 0.0)

        assert "legislation_CA: 3 new, 200 total" in text
        assert "federal_rules: 42 rules" in text

    def test_low_velocity_global_failed_stage_shows_error(self):
        globals_ = {
            "federal_rules": {"status": "failed", "error": "Federal Register returned HTTP 503"},
        }
        analysis = _analysis(failed=1, global_stages=globals_)
        text = _build_summary_text(analysis, "low_velocity_weekly", 60.0, 0.0)

        assert "federal_rules: FAILED - Federal Register returned HTTP 503" in text

    def test_global_stage_failure_error_truncated_to_60_chars(self):
        long_error = "x" * 120
        globals_ = {"federal_rules": {"status": "failed", "error": long_error}}
        analysis = _analysis(failed=1, global_stages=globals_)
        text = _build_summary_text(analysis, "low_velocity_weekly", 60.0, 0.0)

        # Truncated to 60 x's only
        assert "x" * 60 in text
        assert "x" * 61 not in text

    def test_low_velocity_per_jurisdiction_summary_rendered(self):
        per_j = {
            "city-san-rafael": {
                "municipal_code": {"status": "ok", "sections_stored": 500},
            },
        }
        analysis = _analysis(succeeded=1, per_jurisdiction=per_j)
        text = _build_summary_text(analysis, "low_velocity_weekly", 60.0, 0.0)

        assert "city-san-rafael: municipal_code: 500 sections" in text

    def test_failures_section_header_and_content(self):
        failed_stages = [
            {"stage": "city-a/videos", "error": "timeout"},
            {"stage": "city-b/meetings", "error": "db"},
        ]
        analysis = _analysis(failed=2, failed_stages=failed_stages)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        assert "FAILURES:" in text
        assert "  city-a/videos: timeout" in text
        assert "  city-b/meetings: db" in text

    def test_failures_limited_to_first_5(self):
        failed_stages = [
            {"stage": f"city-{i}/videos", "error": "err"} for i in range(8)
        ]
        analysis = _analysis(failed=8, failed_stages=failed_stages)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        for i in range(5):
            assert f"city-{i}/videos" in text
        assert "city-5/videos" not in text
        assert "city-7/videos" not in text

    def test_failure_error_truncated_to_80_chars(self):
        long_err = "a" * 200
        failed_stages = [{"stage": "city-x/videos", "error": long_err}]
        analysis = _analysis(failed=1, failed_stages=failed_stages)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        # Exactly 80 'a' characters in the output line.
        assert "a" * 80 in text
        assert "a" * 81 not in text

    def test_anomalies_section_rendered(self):
        analysis = _analysis(
            succeeded=1,
            anomalies=["city-x: 0 meetings discovered", "city-y: 2 transcript duration validation issues"],
        )
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        assert "ANOMALIES:" in text
        assert "  city-x: 0 meetings discovered" in text
        assert "  city-y: 2 transcript duration validation issues" in text

    def test_anomalies_limited_to_first_5(self):
        anomalies = [f"city-{i}: 0 meetings discovered" for i in range(8)]
        analysis = _analysis(succeeded=8, anomalies=anomalies)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        for i in range(5):
            assert f"city-{i}: 0 meetings discovered" in text
        assert "city-5: 0 meetings discovered" not in text
        assert "city-7: 0 meetings discovered" not in text

    def test_no_failures_or_anomalies_omits_those_sections(self):
        analysis = _analysis(succeeded=2)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        assert "FAILURES:" not in text
        assert "ANOMALIES:" not in text

    def test_time_stamp_format_contains_utc_label(self):
        analysis = _analysis(succeeded=1)
        text = _build_summary_text(analysis, "high_velocity_daily", 60.0, 0.0)

        assert "Time:" in text
        assert "UTC" in text


# ---------------------------------------------------------------------------
# send_pipeline_summary — status, priority, tags, return value
# ---------------------------------------------------------------------------


class TestSendPipelineSummaryStatus:
    def test_all_passed_uses_default_priority_and_check_mark_tag(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 3},
            },
        }
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            out = send_pipeline_summary(results, "high_velocity_daily", 60.0)

        assert mock_send.call_args[1]["priority"] == Priority.DEFAULT
        assert "white_check_mark" in mock_send.call_args[1]["tags"]
        assert "All stages passed" in mock_send.call_args[1]["title"]
        assert out["stages_succeeded"] == 1
        assert out["stages_failed"] == 0
        assert out["failed_stages"] == []
        assert out["anomalies"] == []
        assert out["notification_sent"] is True

    def test_all_failed_uses_urgent_priority_and_red_circle_tag(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "failed", "error": "db"},
                "videos": {"status": "failed", "error": "db"},
            },
        }
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            out = send_pipeline_summary(results, "high_velocity_daily", 60.0)

        assert mock_send.call_args[1]["priority"] == Priority.URGENT
        assert "red_circle" in mock_send.call_args[1]["tags"]
        assert "ALL STAGES FAILED" in mock_send.call_args[1]["title"]
        assert out["stages_failed"] == 2
        assert out["stages_succeeded"] == 0
        assert sorted(out["failed_stages"]) == [
            "city-san-rafael/meetings",
            "city-san-rafael/videos",
        ]

    def test_some_failed_uses_high_priority_and_warning_tag(self):
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 1},
                "videos": {"status": "failed", "error": "timeout"},
            },
        }
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            out = send_pipeline_summary(results, "high_velocity_daily", 60.0)

        assert mock_send.call_args[1]["priority"] == Priority.HIGH
        assert "warning" in mock_send.call_args[1]["tags"]
        assert "1 stage(s) failed" in mock_send.call_args[1]["title"]
        assert out["failed_stages"] == ["city-san-rafael/videos"]

    def test_passed_with_anomalies_uses_high_priority_and_yellow_tag(self):
        # All success, but meetings_stored == 0 triggers an anomaly.
        results = {
            "city-san-rafael": {
                "meetings": {"status": "ok", "meetings_stored": 0},
                "videos": {"status": "ok", "videos_discovered": 2},
            },
        }
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            out = send_pipeline_summary(results, "high_velocity_daily", 60.0)

        assert mock_send.call_args[1]["priority"] == Priority.HIGH
        assert "large_yellow_circle" in mock_send.call_args[1]["tags"]
        assert "Passed with anomalies" in mock_send.call_args[1]["title"]
        assert out["stages_failed"] == 0
        assert out["anomalies"] == ["city-san-rafael: 0 meetings discovered"]

    def test_all_responses_include_pipeline_tag(self):
        results = {"city-x": {"meetings": {"status": "ok", "meetings_stored": 1}}}
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            send_pipeline_summary(results, "high_velocity_daily", 60.0)

        assert "pipeline" in mock_send.call_args[1]["tags"]


# ---------------------------------------------------------------------------
# send_pipeline_summary — title labels and body content
# ---------------------------------------------------------------------------


class TestSendPipelineSummaryMessaging:
    def test_high_velocity_schedule_label(self):
        results = {"city-x": {"meetings": {"status": "ok", "meetings_stored": 1}}}
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            send_pipeline_summary(results, "high_velocity_daily", 60.0)

        assert mock_send.call_args[1]["title"].startswith("Pipeline: Daily High-Velocity - ")

    def test_low_velocity_schedule_label(self):
        results = {"legislation_CA": {"status": "ok", "new_bills": 5, "bills_stored": 100}}
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            send_pipeline_summary(results, "low_velocity_weekly", 60.0)

        assert mock_send.call_args[1]["title"].startswith("Pipeline: Weekly Low-Velocity - ")

    def test_unknown_schedule_uses_raw_label(self):
        results = {"city-x": {"meetings": {"status": "ok", "meetings_stored": 1}}}
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            send_pipeline_summary(results, "adhoc_run", 60.0)

        assert mock_send.call_args[1]["title"].startswith("Pipeline: adhoc_run - ")

    def test_body_contains_stage_counts(self):
        results = {
            "city-a": {"meetings": {"status": "ok", "meetings_stored": 2}},
            "city-b": {"meetings": {"status": "failed", "error": "db"}},
        }
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            send_pipeline_summary(results, "high_velocity_daily", 60.0)

        body = mock_send.call_args[1]["body"]
        assert "Stages: 1/2 passed" in body

    def test_body_contains_transcription_cost_when_high_velocity(self):
        results = {"city-a": {"meetings": {"status": "ok", "meetings_stored": 1}}}
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            send_pipeline_summary(
                results,
                "high_velocity_daily",
                elapsed_seconds=60.0,
                total_transcription_cost=2.50,
            )

        body = mock_send.call_args[1]["body"]
        assert "Transcription cost: $2.50" in body

    def test_click_url_points_to_modal_apps(self):
        results = {"city-x": {"meetings": {"status": "ok", "meetings_stored": 1}}}
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            send_pipeline_summary(results, "high_velocity_daily", 60.0)

        assert mock_send.call_args[1]["click_url"] == "https://modal.com/apps"

    def test_notification_sent_false_propagates(self):
        results = {"city-x": {"meetings": {"status": "ok", "meetings_stored": 1}}}
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=False,
        ):
            out = send_pipeline_summary(results, "high_velocity_daily", 60.0)

        assert out["notification_sent"] is False

    def test_failed_stages_list_in_return_value_contains_only_names(self):
        results = {
            "city-a": {
                "meetings": {"status": "failed", "error": "db"},
                "videos": {"status": "failed", "error": "net"},
            },
        }
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ):
            out = send_pipeline_summary(results, "high_velocity_daily", 60.0)

        # Result exposes just the stage names, not the full error dict.
        assert sorted(out["failed_stages"]) == ["city-a/meetings", "city-a/videos"]

    def test_empty_results_yields_healthy_pass(self):
        with patch(
            "civicos_services.monitoring.pipeline_run_summary.send_notification",
            return_value=True,
        ) as mock_send:
            out = send_pipeline_summary({}, "high_velocity_daily", 60.0)

        assert out["stages_succeeded"] == 0
        assert out["stages_failed"] == 0
        assert out["anomalies"] == []
        # No failures and no anomalies -> "All stages passed" path.
        assert mock_send.call_args[1]["priority"] == Priority.DEFAULT
        assert "All stages passed" in mock_send.call_args[1]["title"]
