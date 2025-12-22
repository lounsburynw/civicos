"""
Generalized ETL pipeline for civic data extraction.

Provides a Pipeline class with stages: discover -> ingest -> index,
with status callbacks for dashboard consumption.

Usage:
    from civic_extraction import Pipeline, ProudCitySource

    source = ProudCitySource.from_jurisdiction("city-san-rafael")
    pipeline = Pipeline(source, "city-san-rafael")

    # Run with callbacks
    result = pipeline.run(
        on_stage_complete=lambda stage, status: print(f"{stage}: {status}")
    )

    # Check status at any time
    status = pipeline.status()
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    runtime_checkable,
)
import time


class StageState(str, Enum):
    """State of a pipeline stage."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class IngestCheckpoint:
    """
    Checkpoint for resuming a pipeline from a specific meeting.

    Used to track the last successfully ingested meeting, allowing resume
    after failures without reprocessing already-ingested meetings.

    Attributes:
        jurisdiction_id: The jurisdiction being processed
        last_meeting_id: ID of last successfully ingested meeting
        last_meeting_datetime: Datetime of last ingested meeting (for filtering)
        items_processed: Total items processed so far
        checkpoint_at: When this checkpoint was created
    """
    jurisdiction_id: str
    last_meeting_id: str
    last_meeting_datetime: datetime
    items_processed: int = 0
    checkpoint_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "last_meeting_id": self.last_meeting_id,
            "last_meeting_datetime": self.last_meeting_datetime.isoformat(),
            "items_processed": self.items_processed,
            "checkpoint_at": self.checkpoint_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IngestCheckpoint":
        """Create from dictionary."""
        return cls(
            jurisdiction_id=data["jurisdiction_id"],
            last_meeting_id=data["last_meeting_id"],
            last_meeting_datetime=datetime.fromisoformat(data["last_meeting_datetime"]),
            items_processed=data.get("items_processed", 0),
            checkpoint_at=datetime.fromisoformat(data["checkpoint_at"]),
        )


@dataclass
class StageStatus:
    """
    Status of a single pipeline stage.

    Attributes:
        state: Current state (pending, running, completed, failed, skipped)
        items_found: Number of items discovered/processed in this stage
        items_processed: Number of items successfully processed
        duration_ms: Time spent in this stage (milliseconds)
        errors: List of error messages encountered
        started_at: When the stage started
        completed_at: When the stage completed (or failed)
        progress_percent: Optional progress percentage (0-100)
        metadata: Stage-specific additional data
    """
    state: StageState = StageState.PENDING
    items_found: int = 0
    items_processed: int = 0
    duration_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress_percent: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "state": self.state.value,
            "items_found": self.items_found,
            "items_processed": self.items_processed,
            "duration_ms": self.duration_ms,
            "errors": self.errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress_percent": self.progress_percent,
            "metadata": self.metadata,
        }


@dataclass
class PipelineResult:
    """
    Result of a complete pipeline run.

    Attributes:
        success: Whether all stages completed successfully
        stages: Status of each stage
        total_duration_ms: Total time for all stages
        started_at: When the pipeline started
        completed_at: When the pipeline completed
        jurisdiction_id: The jurisdiction processed
        source_id: The source processed
    """
    success: bool
    stages: Dict[str, StageStatus]
    total_duration_ms: float
    started_at: datetime
    completed_at: datetime
    jurisdiction_id: str
    source_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "total_duration_ms": self.total_duration_ms,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "jurisdiction_id": self.jurisdiction_id,
            "source_id": self.source_id,
        }


# Type aliases for callbacks
StageStartCallback = Callable[[str], None]
StageProgressCallback = Callable[[str, int, int], None]  # stage, current, total
StageCompleteCallback = Callable[[str, StageStatus], None]
ErrorCallback = Callable[[str, Exception], None]
CheckpointCallback = Callable[["IngestCheckpoint"], None]  # called when checkpoint created


@runtime_checkable
class IndexTarget(Protocol):
    """Protocol for indexing targets (e.g., ChromaDB, database)."""

    def index_meetings(self, meetings: List[Any]) -> int:
        """
        Index meetings and return count of items indexed.

        Args:
            meetings: List of normalized Meeting objects

        Returns:
            Number of items successfully indexed
        """
        ...


class Pipeline:
    """
    Generalized ETL pipeline with stages: discover -> ingest -> index.

    Each stage:
    - discover: Check what data is available from the source
    - ingest: Fetch and normalize data from the source
    - index: Store data for search (ChromaDB, database)

    Status callbacks allow real-time progress monitoring for dashboards.

    Usage:
        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        pipeline = Pipeline(source, "city-san-rafael")

        # With callbacks
        result = pipeline.run(
            on_stage_start=lambda s: print(f"Starting {s}"),
            on_stage_complete=lambda s, status: print(f"{s}: {status.items_processed} items")
        )

        # Get current status at any time
        status = pipeline.status()
    """

    STAGES = ["discover", "ingest", "index"]

    def __init__(
        self,
        source: Any,  # DataSource protocol
        jurisdiction_id: str,
        index_target: Optional[IndexTarget] = None,
    ):
        """
        Initialize pipeline for a data source.

        Args:
            source: DataSource implementation (e.g., ProudCitySource)
            jurisdiction_id: Jurisdiction being processed (e.g., "city-san-rafael")
            index_target: Optional target for indexing (defaults to no-op)
        """
        self.source = source
        self.jurisdiction_id = jurisdiction_id
        self.index_target = index_target

        # Initialize stage statuses
        self._stages: Dict[str, StageStatus] = {
            stage: StageStatus() for stage in self.STAGES
        }

        # Pipeline-level state
        self._started_at: Optional[datetime] = None
        self._completed_at: Optional[datetime] = None
        self._is_running = False

        # Store ingested data between stages
        self._discovered_count: int = 0
        self._ingested_meetings: List[Any] = []

    @property
    def source_id(self) -> str:
        """Get source identifier."""
        return getattr(self.source, "source_id", "unknown")

    def status(self) -> Dict[str, Any]:
        """
        Get current pipeline status.

        Returns a dictionary suitable for dashboard consumption:
        {
            "jurisdiction_id": "city-san-rafael",
            "source_id": "proudcity-san-rafael",
            "is_running": false,
            "started_at": "2025-12-21T10:00:00",
            "stages": {
                "discover": { "state": "completed", "items_found": 50, ... },
                "ingest": { "state": "running", "items_processed": 25, ... },
                "index": { "state": "pending", ... }
            }
        }
        """
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "source_id": self.source_id,
            "is_running": self._is_running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "completed_at": self._completed_at.isoformat() if self._completed_at else None,
            "stages": {
                stage: self._stages[stage].to_dict()
                for stage in self.STAGES
            },
        }

    def run(
        self,
        on_stage_start: Optional[StageStartCallback] = None,
        on_stage_progress: Optional[StageProgressCallback] = None,
        on_stage_complete: Optional[StageCompleteCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        on_checkpoint: Optional[CheckpointCallback] = None,
        days_ahead: int = 90,
        days_past: int = 30,
        skip_index: bool = False,
        resume_from: Optional[IngestCheckpoint] = None,
    ) -> PipelineResult:
        """
        Run the complete pipeline: discover -> ingest -> index.

        Args:
            on_stage_start: Called when each stage begins
            on_stage_progress: Called with progress updates (stage, current, total)
            on_stage_complete: Called when each stage completes
            on_error: Called when an error occurs
            on_checkpoint: Called after ingest completes with checkpoint for resume
            days_ahead: Days into future for event fetching
            days_past: Days into past for event fetching
            skip_index: If True, skip the index stage
            resume_from: Checkpoint to resume from (skip meetings before checkpoint)

        Returns:
            PipelineResult with status of all stages
        """
        self._started_at = datetime.now()
        self._is_running = True
        pipeline_start = time.time()

        success = True

        try:
            # Stage 1: Discover
            self._run_discover(
                on_stage_start, on_stage_progress, on_stage_complete, on_error,
                days_ahead, days_past
            )
            if self._stages["discover"].state == StageState.FAILED:
                success = False

            # Stage 2: Ingest
            if self._stages["discover"].state == StageState.COMPLETED:
                self._run_ingest(
                    on_stage_start, on_stage_progress, on_stage_complete, on_error,
                    on_checkpoint, days_ahead, days_past, resume_from
                )
                if self._stages["ingest"].state == StageState.FAILED:
                    success = False
            else:
                self._stages["ingest"].state = StageState.SKIPPED

            # Stage 3: Index
            if skip_index:
                self._stages["index"].state = StageState.SKIPPED
            elif self._stages["ingest"].state == StageState.COMPLETED:
                self._run_index(
                    on_stage_start, on_stage_progress, on_stage_complete, on_error
                )
                if self._stages["index"].state == StageState.FAILED:
                    success = False
            else:
                self._stages["index"].state = StageState.SKIPPED

        except Exception as e:
            success = False
            if on_error:
                on_error("pipeline", e)

        self._completed_at = datetime.now()
        self._is_running = False
        total_duration = (time.time() - pipeline_start) * 1000

        return PipelineResult(
            success=success,
            stages=dict(self._stages),
            total_duration_ms=total_duration,
            started_at=self._started_at,
            completed_at=self._completed_at,
            jurisdiction_id=self.jurisdiction_id,
            source_id=self.source_id,
        )

    def _run_discover(
        self,
        on_stage_start: Optional[StageStartCallback],
        on_stage_progress: Optional[StageProgressCallback],
        on_stage_complete: Optional[StageCompleteCallback],
        on_error: Optional[ErrorCallback],
        days_ahead: int,
        days_past: int,
    ) -> None:
        """Run the discover stage: check what data is available."""
        stage = "discover"
        status = self._stages[stage]
        status.state = StageState.RUNNING
        status.started_at = datetime.now()
        start_time = time.time()

        if on_stage_start:
            on_stage_start(stage)

        try:
            # Use health check to get available count without full fetch
            health = self.source.health()
            self._discovered_count = health.available_count

            status.items_found = self._discovered_count
            status.items_processed = self._discovered_count
            status.state = StageState.COMPLETED
            status.progress_percent = 100.0
            status.metadata["health"] = health.to_dict()

            if health.errors:
                status.errors.extend(health.errors)

        except Exception as e:
            status.state = StageState.FAILED
            status.errors.append(str(e))
            if on_error:
                on_error(stage, e)

        status.completed_at = datetime.now()
        status.duration_ms = (time.time() - start_time) * 1000

        if on_stage_complete:
            on_stage_complete(stage, status)

    def _run_ingest(
        self,
        on_stage_start: Optional[StageStartCallback],
        on_stage_progress: Optional[StageProgressCallback],
        on_stage_complete: Optional[StageCompleteCallback],
        on_error: Optional[ErrorCallback],
        on_checkpoint: Optional[CheckpointCallback],
        days_ahead: int,
        days_past: int,
        resume_from: Optional[IngestCheckpoint],
    ) -> None:
        """Run the ingest stage: fetch and normalize data."""
        stage = "ingest"
        status = self._stages[stage]
        status.state = StageState.RUNNING
        status.started_at = datetime.now()
        start_time = time.time()

        if on_stage_start:
            on_stage_start(stage)

        try:
            # Fetch and normalize meetings
            meetings = self.source.get_meetings(
                days_ahead=days_ahead,
                days_past=days_past
            )

            total_found = len(meetings)
            skipped_count = 0

            # Filter out meetings before checkpoint if resuming
            if resume_from is not None:
                original_count = len(meetings)
                meetings = [
                    m for m in meetings
                    if self._meeting_after_checkpoint(m, resume_from)
                ]
                skipped_count = original_count - len(meetings)
                status.metadata["resumed_from"] = resume_from.to_dict()
                status.metadata["skipped_count"] = skipped_count

            self._ingested_meetings = meetings
            status.items_found = total_found
            status.items_processed = len(meetings)
            status.state = StageState.COMPLETED
            status.progress_percent = 100.0

            # Report progress if callback provided
            if on_stage_progress and len(meetings) > 0:
                on_stage_progress(stage, len(meetings), total_found)

            # Create checkpoint for resume capability
            if meetings and on_checkpoint:
                last_meeting = meetings[-1]
                checkpoint = IngestCheckpoint(
                    jurisdiction_id=self.jurisdiction_id,
                    last_meeting_id=self._get_meeting_id(last_meeting),
                    last_meeting_datetime=self._get_meeting_datetime(last_meeting),
                    items_processed=len(meetings) + skipped_count,
                )
                on_checkpoint(checkpoint)

        except Exception as e:
            status.state = StageState.FAILED
            status.errors.append(str(e))
            if on_error:
                on_error(stage, e)

        status.completed_at = datetime.now()
        status.duration_ms = (time.time() - start_time) * 1000

        if on_stage_complete:
            on_stage_complete(stage, status)

    def _meeting_after_checkpoint(
        self,
        meeting: Any,
        checkpoint: IngestCheckpoint,
    ) -> bool:
        """Check if a meeting is after the checkpoint (should be processed)."""
        meeting_dt = self._get_meeting_datetime(meeting)
        meeting_id = self._get_meeting_id(meeting)

        # If same datetime, check if ID is different (avoid reprocessing same meeting)
        if meeting_dt == checkpoint.last_meeting_datetime:
            return meeting_id != checkpoint.last_meeting_id

        # Process meetings strictly after checkpoint
        return meeting_dt > checkpoint.last_meeting_datetime

    def _get_meeting_id(self, meeting: Any) -> str:
        """Extract meeting ID from meeting object."""
        if hasattr(meeting, "id"):
            return meeting.id
        if isinstance(meeting, dict):
            return meeting.get("id", "")
        return ""

    def _get_meeting_datetime(self, meeting: Any) -> datetime:
        """Extract meeting datetime from meeting object."""
        if hasattr(meeting, "meeting_datetime"):
            return meeting.meeting_datetime
        if isinstance(meeting, dict):
            dt = meeting.get("meeting_datetime")
            if isinstance(dt, str):
                return datetime.fromisoformat(dt)
            return dt or datetime.min
        return datetime.min

    def _run_index(
        self,
        on_stage_start: Optional[StageStartCallback],
        on_stage_progress: Optional[StageProgressCallback],
        on_stage_complete: Optional[StageCompleteCallback],
        on_error: Optional[ErrorCallback],
    ) -> None:
        """Run the index stage: store data for search."""
        stage = "index"
        status = self._stages[stage]
        status.state = StageState.RUNNING
        status.started_at = datetime.now()
        start_time = time.time()

        if on_stage_start:
            on_stage_start(stage)

        try:
            if self.index_target is None:
                # No index target - mark as completed with note
                status.items_found = len(self._ingested_meetings)
                status.items_processed = 0
                status.state = StageState.COMPLETED
                status.progress_percent = 100.0
                status.metadata["note"] = "No index target configured"
            else:
                # Index the meetings
                indexed_count = self.index_target.index_meetings(
                    self._ingested_meetings
                )
                status.items_found = len(self._ingested_meetings)
                status.items_processed = indexed_count
                status.state = StageState.COMPLETED
                status.progress_percent = 100.0

                if on_stage_progress:
                    on_stage_progress(stage, indexed_count, len(self._ingested_meetings))

        except Exception as e:
            status.state = StageState.FAILED
            status.errors.append(str(e))
            if on_error:
                on_error(stage, e)

        status.completed_at = datetime.now()
        status.duration_ms = (time.time() - start_time) * 1000

        if on_stage_complete:
            on_stage_complete(stage, status)

    def reset(self) -> None:
        """Reset pipeline state for re-run."""
        self._stages = {stage: StageStatus() for stage in self.STAGES}
        self._started_at = None
        self._completed_at = None
        self._is_running = False
        self._discovered_count = 0
        self._ingested_meetings = []


def save_checkpoint(checkpoint: IngestCheckpoint, path: str) -> None:
    """
    Save checkpoint to JSON file.

    Args:
        checkpoint: The checkpoint to save
        path: File path for checkpoint JSON
    """
    import json
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: str) -> Optional[IngestCheckpoint]:
    """
    Load checkpoint from JSON file.

    Args:
        path: File path to checkpoint JSON

    Returns:
        IngestCheckpoint if file exists, None otherwise
    """
    import json
    from pathlib import Path

    if not Path(path).exists():
        return None

    with open(path) as f:
        data = json.load(f)

    return IngestCheckpoint.from_dict(data)


def checkpoint_path_for_jurisdiction(
    jurisdiction_id: str,
    base_dir: str = "data/checkpoints"
) -> str:
    """
    Get standard checkpoint file path for a jurisdiction.

    Args:
        jurisdiction_id: The jurisdiction (e.g., "city-san-rafael")
        base_dir: Base directory for checkpoint files

    Returns:
        Path like "data/checkpoints/city-san-rafael.json"
    """
    return f"{base_dir}/{jurisdiction_id}.json"
