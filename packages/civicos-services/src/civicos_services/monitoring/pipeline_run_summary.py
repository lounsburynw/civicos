"""
Pipeline run summary notifications for scheduled ingestion pipelines.

Sends a push notification at the end of each pipeline run with:
- Per-stage success/failure counts
- Transcription costs
- Straggler retries and anomalies
- Elapsed time

Designed to be called from Modal scheduled functions
(scheduled_high_velocity_refresh, scheduled_low_velocity_refresh).

Usage:
    from civicos_services.monitoring.pipeline_run_summary import send_pipeline_summary

    # At the end of a scheduled pipeline function:
    send_pipeline_summary(
        results=results,
        schedule="high_velocity_daily",
        elapsed_seconds=elapsed,
        total_transcription_cost=0.50,
    )

Environment variables:
    CIVICOS_NTFY_TOPIC - ntfy topic for push notifications (recommended)
    CIVICOS_SLACK_WEBHOOK_URL - Legacy Slack webhook (still supported)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .notify import Priority, send_notification

logger = logging.getLogger(__name__)


def _analyze_results(
    results: Dict[str, Any],
    schedule: str,
) -> Dict[str, Any]:
    """Analyze pipeline results dict and extract summary metrics.

    Args:
        results: The results dict from a scheduled pipeline function.
        schedule: "high_velocity_daily" or "low_velocity_weekly".

    Returns:
        Dictionary with stages_succeeded, stages_failed, failed_stages,
        anomalies, per_jurisdiction, and global_stages.
    """
    stages_succeeded = 0
    stages_failed = 0
    failed_stages: List[Dict[str, str]] = []
    anomalies: List[str] = []
    per_jurisdiction: Dict[str, Dict[str, str]] = {}
    global_stages: Dict[str, Dict[str, Any]] = {}

    # Known global stage keys (not jurisdiction IDs)
    global_keys = {
        "legislation_CA", "executive_orders", "federal_programs",
        "hud_allocations",
    }

    for key, value in results.items():
        if not isinstance(value, dict):
            continue

        if key in global_keys:
            # Global stage (not per-jurisdiction)
            if value.get("status") == "failed":
                stages_failed += 1
                failed_stages.append({
                    "stage": key,
                    "error": value.get("error", "unknown"),
                })
            else:
                stages_succeeded += 1
            global_stages[key] = value
        else:
            # Per-jurisdiction results
            jid = key
            per_jurisdiction[jid] = {}
            for stage, stage_result in value.items():
                if not isinstance(stage_result, dict):
                    continue
                if stage_result.get("status") == "failed":
                    stages_failed += 1
                    failed_stages.append({
                        "stage": f"{jid}/{stage}",
                        "error": stage_result.get("error", "unknown"),
                    })
                else:
                    stages_succeeded += 1
                per_jurisdiction[jid][stage] = stage_result

    # Detect anomalies
    if schedule == "high_velocity_daily":
        for jid, stages in per_jurisdiction.items():
            meetings = stages.get("meetings", {})
            if meetings and meetings.get("meetings_stored", 0) == 0 and meetings.get("status") != "failed":
                anomalies.append(f"{jid}: 0 meetings discovered")

            videos = stages.get("videos", {})
            if videos and videos.get("videos_discovered", 0) == 0 and videos.get("status") != "failed":
                anomalies.append(f"{jid}: 0 videos discovered")

            transcripts = stages.get("transcripts", {})
            if transcripts and transcripts.get("duration_validation_issues", 0) > 0:
                n = transcripts["duration_validation_issues"]
                anomalies.append(f"{jid}: {n} transcript duration validation issues")

    if schedule == "low_velocity_weekly":
        leg = global_stages.get("legislation_CA", {})
        if leg and leg.get("bills_stored", 0) == 0 and leg.get("status") != "failed":
            anomalies.append("CA legislation: 0 bills stored (possible API issue)")

    # All stages failed is itself an anomaly
    if stages_succeeded == 0 and stages_failed > 0:
        anomalies.append("ALL stages failed - investigate immediately")

    return {
        "stages_succeeded": stages_succeeded,
        "stages_failed": stages_failed,
        "failed_stages": failed_stages,
        "anomalies": anomalies,
        "per_jurisdiction": per_jurisdiction,
        "global_stages": global_stages,
    }


def _stage_metric(stage_name: str, result: Dict[str, Any]) -> str:
    """Extract a concise metric string from a stage result."""
    metrics = {
        "meetings": ("meetings_stored", "stored"),
        "issues": ("issues_stored", "stored"),
        "videos": ("videos_discovered", "found"),
        "transcripts": ("transcripts_extracted", "transcribed"),
        "chunks": ("chunks_extracted", "chunks"),
        "agenda_items": ("items_extracted", "items"),
        "decisions": ("decisions_extracted", "decisions"),
        "municipal_code": ("sections_stored", "sections"),
    }
    key, label = metrics.get(stage_name, (None, None))
    if key and key in result:
        return f"{result[key]} {label}"
    return "ok"


def _global_stage_metric(stage_name: str, result: Dict[str, Any]) -> str:
    """Extract a concise metric string from a global stage result."""
    if stage_name == "legislation_CA":
        new = result.get("new_bills", 0)
        stored = result.get("bills_stored", 0)
        return f"{new} new, {stored} total"
    elif stage_name == "executive_orders":
        return f"{result.get('orders_stored', 0)} stored"
    elif stage_name == "federal_programs":
        return f"{result.get('programs_stored', 0)} programs"
    elif stage_name == "hud_allocations":
        return f"{result.get('total_allocations_stored', 0)} allocations"
    return ""


def _build_summary_text(
    analysis: Dict[str, Any],
    schedule: str,
    elapsed_seconds: float,
    total_transcription_cost: float,
) -> str:
    """Build plain text notification body from analysis."""
    succeeded = analysis["stages_succeeded"]
    failed = analysis["stages_failed"]
    total = succeeded + failed
    failed_stages = analysis["failed_stages"]
    anomalies = analysis["anomalies"]

    elapsed_min = elapsed_seconds / 60
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"Stages: {succeeded}/{total} passed",
        f"Duration: {elapsed_min:.1f} min",
        f"Time: {now_utc}",
    ]

    if schedule == "high_velocity_daily" and total_transcription_cost > 0:
        lines.append(f"Transcription cost: ${total_transcription_cost:.2f}")

    # Per-jurisdiction summary for high-velocity
    if schedule == "high_velocity_daily" and analysis["per_jurisdiction"]:
        lines.append("")
        for jid, stages in list(analysis["per_jurisdiction"].items())[:5]:
            stage_parts = []
            for stage_name, stage_result in stages.items():
                if stage_result.get("status") == "failed":
                    stage_parts.append(f"{stage_name}: FAILED")
                else:
                    metric = _stage_metric(stage_name, stage_result)
                    stage_parts.append(f"{stage_name}: {metric}")
            lines.append(f"{jid}: {', '.join(stage_parts)}")

    # Global stages for low-velocity
    if schedule == "low_velocity_weekly" and analysis["global_stages"]:
        lines.append("")
        for stage_name, result in analysis["global_stages"].items():
            if result.get("status") == "failed":
                lines.append(f"{stage_name}: FAILED - {result.get('error', '')[:60]}")
            else:
                metric = _global_stage_metric(stage_name, result)
                lines.append(f"{stage_name}: {metric}")

    # Failed stages detail
    if failed_stages:
        lines.append("")
        lines.append("FAILURES:")
        for fs in failed_stages[:5]:
            lines.append(f"  {fs['stage']}: {fs['error'][:80]}")

    # Anomalies
    if anomalies:
        lines.append("")
        lines.append("ANOMALIES:")
        for a in anomalies[:5]:
            lines.append(f"  {a}")

    return "\n".join(lines)


def send_pipeline_summary(
    results: Dict[str, Any],
    schedule: str,
    elapsed_seconds: float,
    total_transcription_cost: float = 0.0,
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyze pipeline results and send summary notification.

    Args:
        results: The results dict from a scheduled pipeline function.
        schedule: "high_velocity_daily" or "low_velocity_weekly".
        elapsed_seconds: Total pipeline runtime in seconds.
        total_transcription_cost: Total transcription cost in USD (high-velocity).
        webhook_url: Deprecated. Use CIVICOS_NTFY_TOPIC or CIVICOS_SLACK_WEBHOOK_URL env vars.

    Returns:
        Dictionary with success status and analysis summary.
    """
    analysis = _analyze_results(results, schedule)

    succeeded = analysis["stages_succeeded"]
    failed = analysis["stages_failed"]
    total = succeeded + failed
    anomalies = analysis["anomalies"]

    # Determine status and notification priority
    if failed == 0 and not anomalies:
        status_text = "All stages passed"
        priority = Priority.DEFAULT
        tags = ["white_check_mark", "pipeline"]
    elif failed > 0 and succeeded == 0:
        status_text = "ALL STAGES FAILED"
        priority = Priority.URGENT
        tags = ["red_circle", "pipeline"]
    elif failed > 0:
        status_text = f"{failed} stage(s) failed"
        priority = Priority.HIGH
        tags = ["warning", "pipeline"]
    else:
        status_text = "Passed with anomalies"
        priority = Priority.HIGH
        tags = ["large_yellow_circle", "pipeline"]

    schedule_label = {
        "high_velocity_daily": "Daily High-Velocity",
        "low_velocity_weekly": "Weekly Low-Velocity",
    }.get(schedule, schedule)

    title = f"Pipeline: {schedule_label} - {status_text}"
    body = _build_summary_text(analysis, schedule, elapsed_seconds, total_transcription_cost)

    # Send via generic notification dispatch
    # Legacy webhook_url param is ignored - use env vars instead
    sent = send_notification(
        title=title,
        body=body,
        priority=priority,
        tags=tags,
        click_url="https://modal.com/apps",
    )

    return {
        "notification_sent": sent,
        "stages_succeeded": analysis["stages_succeeded"],
        "stages_failed": analysis["stages_failed"],
        "anomalies": analysis["anomalies"],
        "failed_stages": [fs["stage"] for fs in analysis["failed_stages"]],
    }
