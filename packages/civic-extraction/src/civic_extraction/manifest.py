"""
Ingestion manifest for tracking extraction runs with provenance.

Provides standardized tracking of:
- What data was processed
- When it was processed
- Checksums for verification
- Success/failure counts
- Source-specific metadata

Usage:
    from civic_extraction.manifest import IngestionManifest, save_manifest

    # Create from pipeline result
    manifest = IngestionManifest.from_pipeline_result(result)

    # Add custom metadata
    manifest.metadata["initiated_by"] = "scheduled_job"

    # Save to file
    save_manifest(manifest)

    # List all manifests for a jurisdiction
    manifests = list_manifests("city-san-rafael")
"""

import hashlib
import json
import logging
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from civic_extraction.pipeline import PipelineResult

logger = logging.getLogger(__name__)


def _get_data_root() -> str:
    """Get data root directory from environment or default."""
    return os.environ.get("CIVIC_DATA_ROOT", "data")


def _get_manifest_dir() -> str:
    """Get manifest directory path."""
    return os.path.join(_get_data_root(), "manifests")


@dataclass
class SourceEntry:
    """
    Tracking for a single data source within an ingestion run.

    Attributes:
        source_id: Unique identifier for the source (e.g., "proudcity-san-rafael")
        source_type: Type of source (e.g., "proudcity", "legistar", "civicclerk")
        records_ingested: Number of records successfully ingested
        records_failed: Number of records that failed validation/processing
        records_skipped: Number of records skipped (already processed)
        checkpoint: Checkpoint state for resume capability
        errors: List of error messages encountered
    """
    source_id: str
    source_type: str
    records_ingested: int = 0
    records_failed: int = 0
    records_skipped: int = 0
    checkpoint: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "records_ingested": self.records_ingested,
            "records_failed": self.records_failed,
            "records_skipped": self.records_skipped,
            "checkpoint": self.checkpoint,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceEntry":
        """Create from dictionary."""
        return cls(
            source_id=data["source_id"],
            source_type=data["source_type"],
            records_ingested=data.get("records_ingested", 0),
            records_failed=data.get("records_failed", 0),
            records_skipped=data.get("records_skipped", 0),
            checkpoint=data.get("checkpoint", {}),
            errors=data.get("errors", []),
        )


@dataclass
class ValidationSummary:
    """
    Summary of validation results for an ingestion run.

    Attributes:
        total_records: Total records processed
        valid_records: Records that passed validation
        invalid_records: Records that failed validation
        validation_errors: List of validation error details
    """
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    validation_errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_records": self.total_records,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "validation_errors": self.validation_errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationSummary":
        """Create from dictionary."""
        return cls(
            total_records=data.get("total_records", 0),
            valid_records=data.get("valid_records", 0),
            invalid_records=data.get("invalid_records", 0),
            validation_errors=data.get("validation_errors", []),
        )


@dataclass
class IngestionManifest:
    """
    Standardized manifest for tracking extraction/ingestion runs.

    Provides provenance tracking for reproducibility and audit trails:
    - Unique ingestion ID with timestamp
    - Full pipeline result with per-stage metrics
    - Source-level tracking for multi-source runs
    - Validation summary with error details
    - Checksums for data verification
    - Environment metadata

    Attributes:
        ingestion_id: Unique identifier (format: ingest_YYYYMMDD_HHMMSS_jurisdiction)
        timestamp: When the ingestion started
        jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
        run_type: Type of run ("scheduled", "manual", "bootstrap")
        pipeline_stages: Per-stage status from PipelineResult
        total_duration_ms: Total pipeline duration
        success: Whether the ingestion completed successfully
        sources: List of source entries with per-source metrics
        validation: Validation summary
        checksums: Content checksums for verification
        metadata: Additional context (hostname, version, initiator)
    """
    ingestion_id: str
    timestamp: datetime
    jurisdiction_id: str
    run_type: str = "manual"
    pipeline_stages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    success: bool = False
    sources: List[SourceEntry] = field(default_factory=list)
    validation: ValidationSummary = field(default_factory=ValidationSummary)
    checksums: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def generate_id(jurisdiction_id: str, timestamp: Optional[datetime] = None) -> str:
        """Generate a unique ingestion ID."""
        ts = timestamp or datetime.now()
        return f"ingest_{ts.strftime('%Y%m%d_%H%M%S')}_{jurisdiction_id}"

    @classmethod
    def create(
        cls,
        jurisdiction_id: str,
        run_type: str = "manual",
        timestamp: Optional[datetime] = None,
    ) -> "IngestionManifest":
        """
        Create a new manifest with generated ID and default metadata.

        Args:
            jurisdiction_id: Target jurisdiction
            run_type: Type of run ("scheduled", "manual", "bootstrap")
            timestamp: Optional timestamp (defaults to now)

        Returns:
            New IngestionManifest instance
        """
        ts = timestamp or datetime.now()
        return cls(
            ingestion_id=cls.generate_id(jurisdiction_id, ts),
            timestamp=ts,
            jurisdiction_id=jurisdiction_id,
            run_type=run_type,
            metadata={
                "hostname": socket.gethostname(),
                "version": _get_version(),
            },
        )

    @classmethod
    def from_pipeline_result(
        cls,
        result: "PipelineResult",
        run_type: str = "manual",
        source_type: str = "unknown",
    ) -> "IngestionManifest":
        """
        Create manifest from a PipelineResult.

        Args:
            result: Completed pipeline result
            run_type: Type of run
            source_type: Type of data source

        Returns:
            IngestionManifest populated from result
        """
        manifest = cls.create(
            jurisdiction_id=result.jurisdiction_id,
            run_type=run_type,
            timestamp=result.started_at,
        )

        # Copy pipeline stages
        manifest.pipeline_stages = {
            stage: status.to_dict()
            for stage, status in result.stages.items()
        }
        manifest.total_duration_ms = result.total_duration_ms
        manifest.success = result.success

        # Calculate totals from stages
        ingest_stage = result.stages.get("ingest")
        store_stage = result.stages.get("store")

        total_ingested = 0
        total_failed = 0
        errors = []

        if ingest_stage:
            total_ingested = ingest_stage.items_processed
            errors.extend(ingest_stage.errors)
            # Check validation metadata
            if "validation" in ingest_stage.metadata:
                val = ingest_stage.metadata["validation"]
                manifest.validation = ValidationSummary(
                    total_records=val.get("total", 0),
                    valid_records=val.get("valid", 0),
                    invalid_records=val.get("invalid", 0),
                    validation_errors=val.get("errors", []),
                )
                total_failed = val.get("invalid", 0)

        if store_stage:
            errors.extend(store_stage.errors)

        # Create source entry
        source_entry = SourceEntry(
            source_id=result.source_id,
            source_type=source_type,
            records_ingested=total_ingested,
            records_failed=total_failed,
            errors=errors,
        )
        manifest.sources.append(source_entry)

        return manifest

    def add_checksum(self, name: str, content: bytes) -> str:
        """
        Add a SHA-256 checksum for content.

        Args:
            name: Identifier for the content (e.g., "meetings_json")
            content: Raw bytes to checksum

        Returns:
            The computed checksum
        """
        checksum = hashlib.sha256(content).hexdigest()
        self.checksums[name] = checksum
        return checksum

    def add_file_checksum(self, name: str, file_path: str) -> str:
        """
        Add a SHA-256 checksum for a file.

        Args:
            name: Identifier for the file
            file_path: Path to the file

        Returns:
            The computed checksum
        """
        with open(file_path, "rb") as f:
            content = f.read()
        return self.add_checksum(name, content)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ingestion_id": self.ingestion_id,
            "timestamp": self.timestamp.isoformat(),
            "jurisdiction_id": self.jurisdiction_id,
            "run_type": self.run_type,
            "pipeline_stages": self.pipeline_stages,
            "total_duration_ms": self.total_duration_ms,
            "success": self.success,
            "sources": [s.to_dict() for s in self.sources],
            "validation": self.validation.to_dict(),
            "checksums": self.checksums,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IngestionManifest":
        """Create from dictionary."""
        return cls(
            ingestion_id=data["ingestion_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            jurisdiction_id=data["jurisdiction_id"],
            run_type=data.get("run_type", "manual"),
            pipeline_stages=data.get("pipeline_stages", {}),
            total_duration_ms=data.get("total_duration_ms", 0.0),
            success=data.get("success", False),
            sources=[SourceEntry.from_dict(s) for s in data.get("sources", [])],
            validation=ValidationSummary.from_dict(data.get("validation", {})),
            checksums=data.get("checksums", {}),
            metadata=data.get("metadata", {}),
        )

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Ingestion: {self.ingestion_id}",
            f"Jurisdiction: {self.jurisdiction_id}",
            f"Run type: {self.run_type}",
            f"Timestamp: {self.timestamp.isoformat()}",
            f"Duration: {self.total_duration_ms:.1f}ms",
            f"Success: {self.success}",
            "",
            "Sources:",
        ]

        for source in self.sources:
            lines.append(f"  - {source.source_id} ({source.source_type})")
            lines.append(f"    Ingested: {source.records_ingested}")
            if source.records_failed:
                lines.append(f"    Failed: {source.records_failed}")
            if source.records_skipped:
                lines.append(f"    Skipped: {source.records_skipped}")

        if self.validation.total_records:
            lines.extend([
                "",
                "Validation:",
                f"  Total: {self.validation.total_records}",
                f"  Valid: {self.validation.valid_records}",
                f"  Invalid: {self.validation.invalid_records}",
            ])

        if self.checksums:
            lines.extend(["", "Checksums:"])
            for name, checksum in self.checksums.items():
                lines.append(f"  {name}: {checksum[:16]}...")

        return "\n".join(lines)


def _get_version() -> str:
    """Get the civic-extraction version."""
    try:
        from importlib.metadata import version
        return version("civic-extraction")
    except Exception:
        return "0.1.0"


def save_manifest(
    manifest: IngestionManifest,
    manifest_dir: Optional[str] = None,
) -> str:
    """
    Save manifest to JSON file.

    Args:
        manifest: The manifest to save
        manifest_dir: Optional custom directory (defaults to data/manifests/)

    Returns:
        Path to saved manifest file
    """
    if manifest_dir is None:
        manifest_dir = _get_manifest_dir()

    # Create jurisdiction subdirectory
    jurisdiction_dir = os.path.join(manifest_dir, manifest.jurisdiction_id)
    os.makedirs(jurisdiction_dir, exist_ok=True)

    # Generate filename from ingestion_id
    filename = f"{manifest.ingestion_id}.json"
    filepath = os.path.join(jurisdiction_dir, filename)

    with open(filepath, "w") as f:
        json.dump(manifest.to_dict(), f, indent=2)

    logger.info(f"Saved manifest to {filepath}")
    return filepath


def load_manifest(filepath: str) -> IngestionManifest:
    """
    Load manifest from JSON file.

    Args:
        filepath: Path to manifest file

    Returns:
        IngestionManifest instance
    """
    with open(filepath) as f:
        data = json.load(f)
    return IngestionManifest.from_dict(data)


def list_manifests(
    jurisdiction_id: str,
    manifest_dir: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    List manifests for a jurisdiction, most recent first.

    Args:
        jurisdiction_id: Target jurisdiction
        manifest_dir: Optional custom directory
        limit: Maximum number of manifests to return

    Returns:
        List of manifest summaries (id, timestamp, success, records)
    """
    if manifest_dir is None:
        manifest_dir = _get_manifest_dir()

    jurisdiction_dir = os.path.join(manifest_dir, jurisdiction_id)

    if not os.path.exists(jurisdiction_dir):
        return []

    manifests = []
    for filename in os.listdir(jurisdiction_dir):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(jurisdiction_dir, filename)
        try:
            manifest = load_manifest(filepath)
            total_records = sum(s.records_ingested for s in manifest.sources)
            manifests.append({
                "ingestion_id": manifest.ingestion_id,
                "timestamp": manifest.timestamp.isoformat(),
                "success": manifest.success,
                "records_ingested": total_records,
                "run_type": manifest.run_type,
                "filepath": filepath,
            })
        except Exception as e:
            logger.warning(f"Failed to load manifest {filepath}: {e}")

    # Sort by timestamp descending
    manifests.sort(key=lambda m: m["timestamp"], reverse=True)

    return manifests[:limit]


def get_latest_manifest(
    jurisdiction_id: str,
    manifest_dir: Optional[str] = None,
) -> Optional[IngestionManifest]:
    """
    Get the most recent manifest for a jurisdiction.

    Args:
        jurisdiction_id: Target jurisdiction
        manifest_dir: Optional custom directory

    Returns:
        Most recent IngestionManifest or None
    """
    manifests = list_manifests(jurisdiction_id, manifest_dir, limit=1)
    if not manifests:
        return None
    return load_manifest(manifests[0]["filepath"])


@dataclass
class AuditEntry:
    """
    Aggregated extraction metrics for a single platform/source type.

    Attributes:
        source_type: Platform type (e.g., "proudcity", "legistar", "seeclickfix")
        run_count: Total number of extraction runs
        success_count: Number of successful runs
        failure_count: Number of failed runs
        total_records: Total records processed across all runs
        last_run: Timestamp of most recent run
        first_run: Timestamp of first run
        avg_records_per_run: Average records per run
    """
    source_type: str
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_records: int = 0
    last_run: Optional[datetime] = None
    first_run: Optional[datetime] = None
    avg_records_per_run: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.run_count == 0:
            return 0.0
        return (self.success_count / self.run_count) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_type": self.source_type,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 1),
            "total_records": self.total_records,
            "avg_records_per_run": round(self.avg_records_per_run, 1),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "first_run": self.first_run.isoformat() if self.first_run else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEntry":
        """Create from dictionary."""
        return cls(
            source_type=data["source_type"],
            run_count=data.get("run_count", 0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            total_records=data.get("total_records", 0),
            last_run=datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None,
            first_run=datetime.fromisoformat(data["first_run"]) if data.get("first_run") else None,
            avg_records_per_run=data.get("avg_records_per_run", 0.0),
        )


@dataclass
class AuditLog:
    """
    Extraction audit log aggregating metrics across platforms.

    Provides an audit trail for extraction runs:
    - Per-platform success/failure tracking
    - Aggregated record counts
    - Run frequency and timing

    Usage:
        audit = AuditLog.from_manifests(jurisdiction_id="city-san-rafael")
        print(audit.summary())
    """
    jurisdiction_id: str
    generated_at: datetime = field(default_factory=datetime.now)
    entries: Dict[str, AuditEntry] = field(default_factory=dict)
    total_runs: int = 0
    total_records: int = 0

    @classmethod
    def from_manifests(
        cls,
        jurisdiction_id: str,
        manifest_dir: Optional[str] = None,
        limit: int = 100,
    ) -> "AuditLog":
        """
        Build audit log from manifest history.

        Args:
            jurisdiction_id: Target jurisdiction
            manifest_dir: Optional custom directory
            limit: Maximum manifests to process

        Returns:
            AuditLog with aggregated metrics per platform
        """
        audit = cls(jurisdiction_id=jurisdiction_id)

        manifest_summaries = list_manifests(jurisdiction_id, manifest_dir, limit=limit)

        for summary in manifest_summaries:
            try:
                manifest = load_manifest(summary["filepath"])
                audit._add_manifest(manifest)
            except Exception as e:
                logger.warning(f"Failed to process manifest {summary['filepath']}: {e}")

        # Calculate averages
        for entry in audit.entries.values():
            if entry.run_count > 0:
                entry.avg_records_per_run = entry.total_records / entry.run_count

        return audit

    def _add_manifest(self, manifest: IngestionManifest) -> None:
        """Add a manifest to the audit log."""
        self.total_runs += 1

        for source in manifest.sources:
            source_type = source.source_type

            if source_type not in self.entries:
                self.entries[source_type] = AuditEntry(source_type=source_type)

            entry = self.entries[source_type]
            entry.run_count += 1

            if manifest.success:
                entry.success_count += 1
            else:
                entry.failure_count += 1

            entry.total_records += source.records_ingested
            self.total_records += source.records_ingested

            # Track run timestamps
            if entry.last_run is None or manifest.timestamp > entry.last_run:
                entry.last_run = manifest.timestamp
            if entry.first_run is None or manifest.timestamp < entry.first_run:
                entry.first_run = manifest.timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "generated_at": self.generated_at.isoformat(),
            "total_runs": self.total_runs,
            "total_records": self.total_records,
            "platforms": {k: v.to_dict() for k, v in self.entries.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLog":
        """Create from dictionary."""
        audit = cls(
            jurisdiction_id=data["jurisdiction_id"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
            total_runs=data.get("total_runs", 0),
            total_records=data.get("total_records", 0),
        )
        for source_type, entry_data in data.get("platforms", {}).items():
            audit.entries[source_type] = AuditEntry.from_dict(entry_data)
        return audit

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=" * 60,
            "EXTRACTION AUDIT LOG",
            "=" * 60,
            f"Jurisdiction: {self.jurisdiction_id}",
            f"Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total runs: {self.total_runs}",
            f"Total records: {self.total_records:,}",
            "",
            "-" * 60,
            f"{'Platform':<20} {'Runs':<8} {'Success':<10} {'Records':<12} {'Last Run':<15}",
            "-" * 60,
        ]

        for source_type in sorted(self.entries.keys()):
            entry = self.entries[source_type]
            success_str = f"{entry.success_rate:.0f}%"
            last_run_str = entry.last_run.strftime("%Y-%m-%d") if entry.last_run else "N/A"
            lines.append(
                f"{source_type:<20} {entry.run_count:<8} {success_str:<10} "
                f"{entry.total_records:<12,} {last_run_str:<15}"
            )

        lines.extend(["-" * 60, ""])
        return "\n".join(lines)
