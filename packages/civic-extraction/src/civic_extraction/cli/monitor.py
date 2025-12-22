"""
Monitor CLI for checking pipeline health and detecting missed runs.

Usage:
    civic-extract monitor --check-all
    civic-extract monitor --check-all --format json
    civic-extract monitor --pipeline discover --max-age 30
    civic-extract monitor --pipeline legislative --max-age 240

This command checks checkpoint timestamps to detect when scheduled
pipeline runs are overdue.
"""

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Pipeline configurations with expected intervals
PIPELINE_CONFIG = {
    "discover": {
        "description": "Meeting discovery",
        "checkpoint_pattern": "{jurisdiction_id}.json",
        "timestamp_field": "checkpoint_at",
        "default_max_age_hours": 30,  # Daily at 6am, alert if >30h
        "schedule": "Daily 6:00 AM",
    },
    "youtube": {
        "description": "YouTube video discovery",
        "checkpoint_pattern": "youtube_{jurisdiction_id}.json",
        "timestamp_field": "timestamp",
        "default_max_age_hours": 30,  # Daily at 7am
        "schedule": "Daily 7:00 AM",
    },
    "audio": {
        "description": "Audio download",
        "checkpoint_pattern": "audio_{jurisdiction_id}.json",
        "timestamp_field": "timestamp",
        "default_max_age_hours": 30,  # Daily at 8am
        "schedule": "Daily 8:00 AM",
    },
    "transcribe": {
        "description": "Transcription processing",
        "checkpoint_pattern": "transcribe_{jurisdiction_id}.json",
        "timestamp_field": "timestamp",
        "default_max_age_hours": 30,  # Daily at 9am
        "schedule": "Daily 9:00 AM",
    },
    "seeclickfix": {
        "description": "311 issue refresh",
        "checkpoint_pattern": "seeclickfix_{jurisdiction_id}.json",
        "timestamp_field": "timestamp",
        "default_max_age_hours": 30,  # Daily at 8am
        "schedule": "Daily 8:00 AM",
    },
    "legislative": {
        "description": "Legislative bill discovery",
        "checkpoint_pattern": "legislative_{state}_{topic}.json",
        "timestamp_field": "timestamp",
        "default_max_age_hours": 192,  # Weekly (7d = 168h), alert if >8d
        "schedule": "Weekly Sunday 6:00 AM",
    },
}


@dataclass
class PipelineStatus:
    """Status of a single pipeline checkpoint."""

    pipeline: str
    checkpoint_file: str
    last_run: Optional[datetime]
    age_hours: Optional[float]
    max_age_hours: float
    is_overdue: bool
    status: str  # "healthy", "overdue", "missing", "error"
    message: str

    def to_dict(self) -> dict:
        return {
            "pipeline": self.pipeline,
            "checkpoint_file": self.checkpoint_file,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "age_hours": round(self.age_hours, 1) if self.age_hours else None,
            "max_age_hours": self.max_age_hours,
            "is_overdue": self.is_overdue,
            "status": self.status,
            "message": self.message,
        }


@dataclass
class MonitorReport:
    """Overall monitoring report."""

    checked_at: datetime
    pipelines: list[PipelineStatus]
    healthy_count: int
    overdue_count: int
    missing_count: int
    error_count: int

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at.isoformat(),
            "summary": {
                "healthy": self.healthy_count,
                "overdue": self.overdue_count,
                "missing": self.missing_count,
                "error": self.error_count,
                "total": len(self.pipelines),
            },
            "pipelines": [p.to_dict() for p in self.pipelines],
        }


def get_checkpoint_dir() -> Path:
    """Get the checkpoint directory path."""
    # Navigate from package to project root
    package_dir = Path(__file__).parent.parent.parent.parent.parent.parent
    return package_dir / "data" / "checkpoints"


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse ISO format timestamp from checkpoint."""
    if not timestamp_str:
        return None
    try:
        # Handle with or without microseconds
        if "." in timestamp_str:
            return datetime.fromisoformat(timestamp_str)
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return None


def check_pipeline_status(
    pipeline: str,
    checkpoint_dir: Path,
    jurisdiction_id: str = "city-san-rafael",
    state: str = "california",
    topic: str = "housing",
    max_age_hours: Optional[float] = None,
) -> PipelineStatus:
    """Check the status of a single pipeline."""
    config = PIPELINE_CONFIG.get(pipeline)
    if not config:
        return PipelineStatus(
            pipeline=pipeline,
            checkpoint_file="",
            last_run=None,
            age_hours=None,
            max_age_hours=0,
            is_overdue=False,
            status="error",
            message=f"Unknown pipeline: {pipeline}",
        )

    # Build checkpoint filename
    pattern = config["checkpoint_pattern"]
    if "{jurisdiction_id}" in pattern:
        checkpoint_file = pattern.format(jurisdiction_id=jurisdiction_id)
    elif "{state}" in pattern and "{topic}" in pattern:
        checkpoint_file = pattern.format(state=state, topic=topic)
    else:
        checkpoint_file = pattern

    checkpoint_path = checkpoint_dir / checkpoint_file
    effective_max_age = max_age_hours or config["default_max_age_hours"]

    # Check if checkpoint exists
    if not checkpoint_path.exists():
        return PipelineStatus(
            pipeline=pipeline,
            checkpoint_file=checkpoint_file,
            last_run=None,
            age_hours=None,
            max_age_hours=effective_max_age,
            is_overdue=True,
            status="missing",
            message=f"No checkpoint file found at {checkpoint_file}",
        )

    # Read checkpoint
    try:
        with open(checkpoint_path) as f:
            checkpoint_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return PipelineStatus(
            pipeline=pipeline,
            checkpoint_file=checkpoint_file,
            last_run=None,
            age_hours=None,
            max_age_hours=effective_max_age,
            is_overdue=True,
            status="error",
            message=f"Failed to read checkpoint: {e}",
        )

    # Extract timestamp
    timestamp_field = config["timestamp_field"]
    timestamp_str = checkpoint_data.get(timestamp_field)
    last_run = parse_timestamp(timestamp_str)

    if not last_run:
        return PipelineStatus(
            pipeline=pipeline,
            checkpoint_file=checkpoint_file,
            last_run=None,
            age_hours=None,
            max_age_hours=effective_max_age,
            is_overdue=True,
            status="error",
            message=f"No valid timestamp in field '{timestamp_field}'",
        )

    # Calculate age
    now = datetime.now()
    age = now - last_run
    age_hours = age.total_seconds() / 3600
    is_overdue = age_hours > effective_max_age

    if is_overdue:
        return PipelineStatus(
            pipeline=pipeline,
            checkpoint_file=checkpoint_file,
            last_run=last_run,
            age_hours=age_hours,
            max_age_hours=effective_max_age,
            is_overdue=True,
            status="overdue",
            message=f"Last run {age_hours:.1f}h ago, exceeds {effective_max_age}h threshold",
        )

    return PipelineStatus(
        pipeline=pipeline,
        checkpoint_file=checkpoint_file,
        last_run=last_run,
        age_hours=age_hours,
        max_age_hours=effective_max_age,
        is_overdue=False,
        status="healthy",
        message=f"Last run {age_hours:.1f}h ago ({config['schedule']})",
    )


def check_all_pipelines(
    checkpoint_dir: Path,
    jurisdiction_id: str = "city-san-rafael",
    state: str = "california",
    topic: str = "housing",
    max_age_hours: Optional[float] = None,
) -> MonitorReport:
    """Check all configured pipelines and return a report."""
    statuses = []

    for pipeline in PIPELINE_CONFIG:
        status = check_pipeline_status(
            pipeline=pipeline,
            checkpoint_dir=checkpoint_dir,
            jurisdiction_id=jurisdiction_id,
            state=state,
            topic=topic,
            max_age_hours=max_age_hours,
        )
        statuses.append(status)

    return MonitorReport(
        checked_at=datetime.now(),
        pipelines=statuses,
        healthy_count=sum(1 for s in statuses if s.status == "healthy"),
        overdue_count=sum(1 for s in statuses if s.status == "overdue"),
        missing_count=sum(1 for s in statuses if s.status == "missing"),
        error_count=sum(1 for s in statuses if s.status == "error"),
    )


def format_report_text(report: MonitorReport) -> str:
    """Format report as human-readable text."""
    lines = []
    lines.append("=" * 60)
    lines.append("CIVIC PIPELINE MONITOR")
    lines.append(f"Checked at: {report.checked_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    lines.append("")

    # Summary
    total = len(report.pipelines)
    lines.append(f"Summary: {report.healthy_count}/{total} healthy")
    if report.overdue_count > 0:
        lines.append(f"  WARNING: {report.overdue_count} overdue")
    if report.missing_count > 0:
        lines.append(f"  WARNING: {report.missing_count} missing")
    if report.error_count > 0:
        lines.append(f"  ERROR: {report.error_count} errors")
    lines.append("")

    # Details
    lines.append("-" * 60)
    for status in report.pipelines:
        config = PIPELINE_CONFIG.get(status.pipeline, {})
        desc = config.get("description", status.pipeline)

        if status.status == "healthy":
            icon = "✓"
        elif status.status == "overdue":
            icon = "⚠"
        elif status.status == "missing":
            icon = "✗"
        else:
            icon = "!"

        lines.append(f"{icon} {status.pipeline:12} ({desc})")
        lines.append(f"  {status.message}")
        lines.append("")

    return "\n".join(lines)


def add_monitor_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the monitor subcommand parser."""
    parser = subparsers.add_parser(
        "monitor",
        help="Check pipeline health and detect missed runs",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--check-all",
        action="store_true",
        help="Check all pipelines (default behavior)",
    )

    parser.add_argument(
        "--pipeline",
        choices=list(PIPELINE_CONFIG.keys()),
        help="Check a specific pipeline only",
    )

    parser.add_argument(
        "--jurisdiction",
        default="city-san-rafael",
        help="Jurisdiction ID for jurisdiction-scoped pipelines (default: city-san-rafael)",
    )

    parser.add_argument(
        "--state",
        default="california",
        help="State for legislative pipeline (default: california)",
    )

    parser.add_argument(
        "--topic",
        default="housing",
        help="Topic for legislative pipeline (default: housing)",
    )

    parser.add_argument(
        "--max-age",
        type=float,
        metavar="HOURS",
        help="Override max age threshold in hours (e.g., 24 for daily)",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--exit-on-overdue",
        action="store_true",
        help="Exit with code 1 if any pipeline is overdue (for CI/monitoring)",
    )


def run_monitor(args: argparse.Namespace) -> int:
    """Run the monitor command."""
    checkpoint_dir = get_checkpoint_dir()

    if not checkpoint_dir.exists():
        logger.error(f"Checkpoint directory not found: {checkpoint_dir}")
        print(f"ERROR: Checkpoint directory not found: {checkpoint_dir}")
        return 1

    # Check specific pipeline or all
    if args.pipeline:
        status = check_pipeline_status(
            pipeline=args.pipeline,
            checkpoint_dir=checkpoint_dir,
            jurisdiction_id=args.jurisdiction,
            state=args.state,
            topic=args.topic,
            max_age_hours=args.max_age,
        )
        report = MonitorReport(
            checked_at=datetime.now(),
            pipelines=[status],
            healthy_count=1 if status.status == "healthy" else 0,
            overdue_count=1 if status.status == "overdue" else 0,
            missing_count=1 if status.status == "missing" else 0,
            error_count=1 if status.status == "error" else 0,
        )
    else:
        report = check_all_pipelines(
            checkpoint_dir=checkpoint_dir,
            jurisdiction_id=args.jurisdiction,
            state=args.state,
            topic=args.topic,
            max_age_hours=args.max_age,
        )

    # Output
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report_text(report))

    # Log alerts for overdue pipelines
    for status in report.pipelines:
        if status.status == "overdue":
            logger.warning(
                f"Pipeline overdue: {status.pipeline} - {status.message}"
            )
        elif status.status == "missing":
            logger.warning(
                f"Pipeline checkpoint missing: {status.pipeline} - {status.message}"
            )
        elif status.status == "error":
            logger.error(
                f"Pipeline check error: {status.pipeline} - {status.message}"
            )

    # Exit code for CI/monitoring
    if args.exit_on_overdue:
        if report.overdue_count > 0 or report.missing_count > 0 or report.error_count > 0:
            return 1

    return 0
