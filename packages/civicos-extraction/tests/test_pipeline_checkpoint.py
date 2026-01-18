"""
Tests for Pipeline checkpoint/resume functionality.

Tests the IngestCheckpoint dataclass and Pipeline resume capability
for long-running extractions.
"""

import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Any

from civicos_extraction import (
    Pipeline,
    PipelineResult,
    StageStatus,
    StageState,
    IngestCheckpoint,
    save_checkpoint,
    load_checkpoint,
    checkpoint_path_for_jurisdiction,
    Meeting,
)


class MockDataSource:
    """Mock data source for testing pipeline."""

    def __init__(self, meetings: List[Meeting]):
        self.meetings = meetings
        self.source_id = "mock-source"

    def health(self):
        """Return mock health status."""
        from civicos_extraction import HealthStatus

        return HealthStatus(
            source_id="mock-source",
            source_type="mock",
            jurisdiction_id="city-test",
            is_available=True,
            available_count=len(self.meetings),
            last_checked=datetime.now(),
            check_duration_ms=1.0,
            errors=[],
        )

    def get_meetings(self, days_ahead: int = 90, days_past: int = 30):
        """Return mock meetings."""
        return self.meetings


def make_meeting(id: str, days_offset: int = 0) -> Meeting:
    """Create a test meeting with given id and date offset."""
    dt = datetime.now() + timedelta(days=days_offset)
    return Meeting(
        id=id,
        title=f"Meeting {id}",
        meeting_datetime=dt,
        jurisdiction_id="city-test",
        source_platform="mock",
    )


class TestIngestCheckpoint:
    """Test IngestCheckpoint dataclass."""

    def test_checkpoint_creation(self):
        """Test basic checkpoint creation."""
        checkpoint = IngestCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_id="meeting-005",
            last_meeting_datetime=datetime(2025, 12, 15, 18, 0),
            items_processed=5,
        )
        assert checkpoint.jurisdiction_id == "city-test"
        assert checkpoint.last_meeting_id == "meeting-005"
        assert checkpoint.items_processed == 5

    def test_checkpoint_to_dict(self):
        """Test checkpoint serialization."""
        checkpoint = IngestCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_id="meeting-005",
            last_meeting_datetime=datetime(2025, 12, 15, 18, 0),
            items_processed=5,
        )
        d = checkpoint.to_dict()
        assert d["jurisdiction_id"] == "city-test"
        assert d["last_meeting_id"] == "meeting-005"
        assert "2025-12-15" in d["last_meeting_datetime"]
        assert d["items_processed"] == 5

    def test_checkpoint_from_dict(self):
        """Test checkpoint deserialization."""
        data = {
            "jurisdiction_id": "city-test",
            "last_meeting_id": "meeting-005",
            "last_meeting_datetime": "2025-12-15T18:00:00",
            "items_processed": 5,
            "checkpoint_at": "2025-12-15T20:00:00",
        }
        checkpoint = IngestCheckpoint.from_dict(data)
        assert checkpoint.jurisdiction_id == "city-test"
        assert checkpoint.last_meeting_id == "meeting-005"
        assert checkpoint.last_meeting_datetime == datetime(2025, 12, 15, 18, 0)

    def test_checkpoint_roundtrip(self):
        """Test checkpoint serialization roundtrip."""
        original = IngestCheckpoint(
            jurisdiction_id="city-san-rafael",
            last_meeting_id="meeting-010",
            last_meeting_datetime=datetime(2025, 12, 20, 19, 30),
            items_processed=10,
        )
        data = original.to_dict()
        restored = IngestCheckpoint.from_dict(data)
        assert restored.jurisdiction_id == original.jurisdiction_id
        assert restored.last_meeting_id == original.last_meeting_id
        assert restored.last_meeting_datetime == original.last_meeting_datetime
        assert restored.items_processed == original.items_processed


class TestCheckpointPersistence:
    """Test checkpoint save/load utilities."""

    def test_save_and_load_checkpoint(self, tmp_path):
        """Test saving and loading checkpoint from file."""
        checkpoint = IngestCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_id="meeting-005",
            last_meeting_datetime=datetime(2025, 12, 15, 18, 0),
            items_processed=5,
        )
        path = str(tmp_path / "checkpoint.json")

        save_checkpoint(checkpoint, path)
        assert Path(path).exists()

        loaded = load_checkpoint(path)
        assert loaded is not None
        assert loaded.jurisdiction_id == checkpoint.jurisdiction_id
        assert loaded.last_meeting_id == checkpoint.last_meeting_id

    def test_load_nonexistent_checkpoint(self, tmp_path):
        """Test loading checkpoint that doesn't exist returns None."""
        path = str(tmp_path / "nonexistent.json")
        loaded = load_checkpoint(path)
        assert loaded is None

    def test_checkpoint_path_for_jurisdiction(self, monkeypatch):
        """Test standard checkpoint path generation."""
        # Ensure we test with default data root
        monkeypatch.delenv("CIVICOS_DATA_ROOT", raising=False)
        path = checkpoint_path_for_jurisdiction("city-san-rafael")
        assert path == "data/checkpoints/city-san-rafael.json"

        # Test with custom base_dir
        path = checkpoint_path_for_jurisdiction("city-test", base_dir="/tmp/checkpoints")
        assert path == "/tmp/checkpoints/city-test.json"

        # Test with environment variable
        monkeypatch.setenv("CIVICOS_DATA_ROOT", "/custom/data")
        path = checkpoint_path_for_jurisdiction("city-test")
        assert path == "/custom/data/checkpoints/city-test.json"

    def test_save_creates_parent_directories(self, tmp_path):
        """Test save_checkpoint creates parent directories."""
        checkpoint = IngestCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_id="meeting-001",
            last_meeting_datetime=datetime.now(),
        )
        path = str(tmp_path / "nested" / "dirs" / "checkpoint.json")

        save_checkpoint(checkpoint, path)
        assert Path(path).exists()


class TestPipelineResume:
    """Test Pipeline resume from checkpoint."""

    def test_pipeline_without_checkpoint(self):
        """Test normal pipeline run without checkpoint."""
        meetings = [
            make_meeting("m1", days_offset=-5),
            make_meeting("m2", days_offset=-3),
            make_meeting("m3", days_offset=-1),
        ]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test")

        result = pipeline.run(skip_index=True)

        assert result.success
        assert result.stages["ingest"].items_processed == 3
        assert result.stages["ingest"].items_found == 3

    def test_pipeline_resume_from_checkpoint(self):
        """Test pipeline resumes from checkpoint, skipping earlier meetings."""
        # Create 5 meetings
        meetings = [
            make_meeting("m1", days_offset=-10),
            make_meeting("m2", days_offset=-8),
            make_meeting("m3", days_offset=-6),  # checkpoint is after this
            make_meeting("m4", days_offset=-4),
            make_meeting("m5", days_offset=-2),
        ]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test")

        # Create checkpoint at m3
        checkpoint = IngestCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_id="m3",
            last_meeting_datetime=meetings[2].meeting_datetime,
            items_processed=3,
        )

        result = pipeline.run(skip_index=True, resume_from=checkpoint)

        assert result.success
        # Should only process m4 and m5 (after checkpoint)
        assert result.stages["ingest"].items_processed == 2
        assert result.stages["ingest"].items_found == 5
        assert result.stages["ingest"].metadata["skipped_count"] == 3
        assert "resumed_from" in result.stages["ingest"].metadata

    def test_pipeline_checkpoint_callback(self):
        """Test checkpoint callback is called after ingest."""
        meetings = [
            make_meeting("m1", days_offset=-3),
            make_meeting("m2", days_offset=-1),
        ]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test")

        captured_checkpoint = []

        def on_checkpoint(cp: IngestCheckpoint):
            captured_checkpoint.append(cp)

        result = pipeline.run(skip_index=True, on_checkpoint=on_checkpoint)

        assert result.success
        assert len(captured_checkpoint) == 1
        assert captured_checkpoint[0].last_meeting_id == "m2"
        assert captured_checkpoint[0].items_processed == 2

    def test_pipeline_resume_exact_match_excluded(self):
        """Test that exact checkpoint meeting is excluded."""
        meetings = [
            make_meeting("m1", days_offset=-5),
            make_meeting("m2", days_offset=-3),
        ]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test")

        # Checkpoint at exactly m2 - should skip m2, no meetings left
        checkpoint = IngestCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_id="m2",
            last_meeting_datetime=meetings[1].meeting_datetime,
            items_processed=2,
        )

        result = pipeline.run(skip_index=True, resume_from=checkpoint)

        assert result.success
        # Both meetings are at or before checkpoint
        assert result.stages["ingest"].items_processed == 0
        assert result.stages["ingest"].items_found == 2
        assert result.stages["ingest"].metadata["skipped_count"] == 2

    def test_pipeline_resume_with_same_datetime_different_id(self):
        """Test meetings with same datetime but different ID are handled."""
        base_dt = datetime(2025, 12, 15, 18, 0)
        meetings = [
            Meeting(
                id="m1",
                title="Meeting 1",
                meeting_datetime=base_dt,
                jurisdiction_id="city-test",
            ),
            Meeting(
                id="m2",
                title="Meeting 2",
                meeting_datetime=base_dt,  # Same datetime as m1
                jurisdiction_id="city-test",
            ),
        ]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test")

        # Checkpoint at m1 - should include m2 (same time, different ID)
        checkpoint = IngestCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_id="m1",
            last_meeting_datetime=base_dt,
            items_processed=1,
        )

        result = pipeline.run(skip_index=True, resume_from=checkpoint)

        assert result.success
        # Should process m2 (same time but different ID)
        assert result.stages["ingest"].items_processed == 1
        assert pipeline._ingested_meetings[0].id == "m2"


class TestPipelineCheckpointIntegration:
    """Integration tests for checkpoint save/resume flow."""

    def test_full_checkpoint_save_resume_flow(self, tmp_path):
        """Test complete flow: run, save checkpoint, resume."""
        meetings = [
            make_meeting("m1", days_offset=-10),
            make_meeting("m2", days_offset=-8),
            make_meeting("m3", days_offset=-6),
            make_meeting("m4", days_offset=-4),
            make_meeting("m5", days_offset=-2),
        ]
        source = MockDataSource(meetings)
        checkpoint_path = str(tmp_path / "checkpoint.json")

        # First run - capture checkpoint
        pipeline1 = Pipeline(source, "city-test")
        checkpoint_holder = []

        result1 = pipeline1.run(
            skip_index=True,
            on_checkpoint=lambda cp: checkpoint_holder.append(cp),
        )
        assert result1.success
        assert len(checkpoint_holder) == 1

        # Save checkpoint
        save_checkpoint(checkpoint_holder[0], checkpoint_path)

        # Simulate failure and resume
        loaded = load_checkpoint(checkpoint_path)
        assert loaded is not None

        # Resume run
        pipeline2 = Pipeline(source, "city-test")
        result2 = pipeline2.run(skip_index=True, resume_from=loaded)

        assert result2.success
        # All meetings are at or before checkpoint, so 0 new
        assert result2.stages["ingest"].items_processed == 0
        assert result2.stages["ingest"].metadata["skipped_count"] == 5


class TestPipelineValidation:
    """Test Pipeline validation on ingest."""

    def test_pipeline_validates_meetings_by_default(self):
        """Pipeline should validate meetings before storage by default."""
        meetings = [
            make_meeting("m1", days_offset=-3),
            make_meeting("m2", days_offset=-1),
        ]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test")

        result = pipeline.run(skip_index=True)

        assert result.success
        # Validation should have run
        assert "validation" in result.stages["store"].metadata
        validation = result.stages["store"].metadata["validation"]
        assert validation["total"] == 2
        assert validation["valid"] == 2
        assert validation["invalid"] == 0

    def test_pipeline_filters_invalid_meetings(self):
        """Pipeline should filter out invalid meetings from storage."""
        valid_meeting = make_meeting("m1", days_offset=-3)
        # Create invalid meeting with empty id (will fail validation)
        invalid_meeting = Meeting(
            id="",  # Empty id - invalid
            title="Invalid Meeting",
            meeting_datetime=datetime.now(),
            jurisdiction_id="city-test",
        )
        meetings = [valid_meeting, invalid_meeting]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test")

        result = pipeline.run(skip_index=True)

        # Pipeline still succeeds, but invalid meeting is filtered
        assert result.success
        validation = result.stages["store"].metadata["validation"]
        assert validation["total"] == 2
        assert validation["valid"] == 1
        assert validation["invalid"] == 1
        # Errors should be logged
        assert len(result.stages["store"].errors) >= 1
        assert any("invalid meeting" in e.lower() for e in result.stages["store"].errors)

    def test_pipeline_validation_can_be_disabled(self):
        """Pipeline validation can be disabled via validate_on_ingest=False."""
        valid_meeting = make_meeting("m1", days_offset=-3)
        invalid_meeting = Meeting(
            id="",  # Empty id - would fail validation
            title="Would Be Invalid",
            meeting_datetime=datetime.now(),
            jurisdiction_id="city-test",
        )
        meetings = [valid_meeting, invalid_meeting]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test", validate_on_ingest=False)

        result = pipeline.run(skip_index=True)

        # No validation metadata when disabled
        assert "validation" not in result.stages["store"].metadata
        # Both meetings should be stored (no filtering)
        assert result.stages["store"].items_processed == 2

    def test_pipeline_all_invalid_meetings_still_succeeds(self):
        """Pipeline should succeed even if all meetings are invalid."""
        invalid_meetings = [
            Meeting(id="", title="Invalid 1", meeting_datetime=datetime.now(), jurisdiction_id="city-test"),
            Meeting(id="", title="Invalid 2", meeting_datetime=datetime.now(), jurisdiction_id="city-test"),
        ]
        source = MockDataSource(invalid_meetings)
        pipeline = Pipeline(source, "city-test")

        result = pipeline.run(skip_index=True)

        # Pipeline succeeds but stores 0 meetings
        assert result.success
        validation = result.stages["store"].metadata["validation"]
        assert validation["valid"] == 0
        assert validation["invalid"] == 2
        assert result.stages["store"].items_processed == 0

    def test_pipeline_validation_time_recorded(self):
        """Pipeline should record validation time in metadata."""
        meetings = [make_meeting("m1", days_offset=-1)]
        source = MockDataSource(meetings)
        pipeline = Pipeline(source, "city-test")

        result = pipeline.run(skip_index=True)

        assert result.success
        validation = result.stages["store"].metadata["validation"]
        assert "validation_time_ms" in validation
        assert validation["validation_time_ms"] >= 0
