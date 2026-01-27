"""
Pipeline run summary notifications for scheduled ingestion pipelines.

Sends a Slack webhook notification at the end of each pipeline run with:
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
    CIVICOS_SLACK_WEBHOOK_URL - Slack incoming webhook URL
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


def _build_slack_blocks(
    analysis: Dict[str, Any],
    schedule: str,
    elapsed_seconds: float,
    total_transcription_cost: float,
) -> Tuple[List[Dict[str, Any]], str]:
    """Build Slack Block Kit message from analysis.

    Returns:
        Tuple of (blocks list, fallback text string).
    """
    succeeded = analysis["stages_succeeded"]
    failed = analysis["stages_failed"]
    total = succeeded + failed
    failed_stages = analysis["failed_stages"]
    anomalies = analysis["anomalies"]

    # Overall status
    if failed == 0 and not anomalies:
        status_emoji = ":white_check_mark:"
        status_text = "All stages passed"
    elif failed > 0 and succeeded == 0:
        status_emoji = ":red_circle:"
        status_text = "ALL STAGES FAILED"
    elif failed > 0:
        status_emoji = ":warning:"
        status_text = f"{failed} stage(s) failed"
    else:
        status_emoji = ":large_yellow_circle:"
        status_text = "Passed with anomalies"

    schedule_label = {
        "high_velocity_daily": "Daily High-Velocity Refresh",
        "low_velocity_weekly": "Weekly Low-Velocity Refresh",
    }.get(schedule, schedule)

    elapsed_min = elapsed_seconds / 60

    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{status_emoji} Pipeline: {schedule_label}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Status:*\n{status_text}"},
                {"type": "mrkdwn", "text": f"*Stages:*\n{succeeded}/{total} passed"},
                {"type": "mrkdwn", "text": f"*Duration:*\n{elapsed_min:.1f} min"},
                {"type": "mrkdwn", "text": f"*Time:*\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"},
            ],
        },
    ]

    # Transcription cost (high-velocity only)
    if schedule == "high_velocity_daily" and total_transcription_cost > 0:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Transcription Cost:*\n${total_transcription_cost:.2f}"},
            ],
        })

    # Per-jurisdiction summary for high-velocity
    if schedule == "high_velocity_daily" and analysis["per_jurisdiction"]:
        jid_lines = []
        for jid, stages in analysis["per_jurisdiction"].items():
            stage_statuses = []
            for stage_name, stage_result in stages.items():
                if stage_result.get("status") == "failed":
                    stage_statuses.append(f"`{stage_name}` :x:")
                else:
                    # Extract key metric
                    metric = _stage_metric(stage_name, stage_result)
                    stage_statuses.append(f"`{stage_name}` {metric}")
            jid_lines.append(f"*{jid}:* " + ", ".join(stage_statuses))

        if jid_lines:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(jid_lines[:5]),  # Limit to 5 jurisdictions
                },
            })

    # Global stages for low-velocity
    if schedule == "low_velocity_weekly" and analysis["global_stages"]:
        global_lines = []
        for stage_name, result in analysis["global_stages"].items():
            if result.get("status") == "failed":
                global_lines.append(f"`{stage_name}` :x: {result.get('error', '')[:60]}")
            else:
                metric = _global_stage_metric(stage_name, result)
                global_lines.append(f"`{stage_name}` :white_check_mark: {metric}")
        if global_lines:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Global stages:*\n" + "\n".join(global_lines),
                },
            })

    # Failed stages detail
    if failed_stages:
        error_lines = [
            f":x: `{fs['stage']}`: {fs['error'][:80]}"
            for fs in failed_stages[:5]
        ]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Failed stages:*\n" + "\n".join(error_lines),
            },
        })

    # Anomalies
    if anomalies:
        anomaly_lines = [f":warning: {a}" for a in anomalies[:5]]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Anomalies:*\n" + "\n".join(anomaly_lines),
            },
        })

    # Footer
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "CivicOS Pipeline | <https://modal.com/apps|Modal Dashboard>",
            }
        ],
    })

    fallback = f"Pipeline {schedule_label}: {status_text} ({succeeded}/{total} stages, {elapsed_min:.1f}min)"
    return blocks, fallback


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
    return ":white_check_mark:"


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


def _send_slack(webhook_url: str, blocks: List[Dict], fallback_text: str) -> bool:
    """Send Slack Block Kit message via webhook.

    Returns:
        True if sent successfully, False otherwise.
    """
    payload = {"blocks": blocks, "text": fallback_text}

    try:
        req = Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info("Pipeline summary sent to Slack")
                return True
            else:
                logger.warning(f"Slack webhook returned status {response.status}")
                return False
    except HTTPError as e:
        logger.error(f"Slack webhook HTTP error: {e.code} - {e.reason}")
        return False
    except URLError as e:
        logger.error(f"Slack webhook URL error: {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Failed to send pipeline summary to Slack: {e}")
        return False


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
        webhook_url: Slack webhook URL override (default: from env).

    Returns:
        Dictionary with success status and analysis summary.
    """
    url = webhook_url or os.environ.get("CIVICOS_SLACK_WEBHOOK_URL", "")

    analysis = _analyze_results(results, schedule)
    blocks, fallback = _build_slack_blocks(
        analysis, schedule, elapsed_seconds, total_transcription_cost,
    )

    sent = False
    if url:
        sent = _send_slack(url, blocks, fallback)
    else:
        logger.warning(
            f"Pipeline summary (no webhook configured): "
            f"{analysis['stages_succeeded']}/{analysis['stages_succeeded'] + analysis['stages_failed']} "
            f"stages passed, {len(analysis['anomalies'])} anomalies"
        )

    return {
        "notification_sent": sent,
        "stages_succeeded": analysis["stages_succeeded"],
        "stages_failed": analysis["stages_failed"],
        "anomalies": analysis["anomalies"],
        "failed_stages": [fs["stage"] for fs in analysis["failed_stages"]],
    }
