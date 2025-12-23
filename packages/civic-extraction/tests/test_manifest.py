"""Tests for ingestion manifest functionality."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from civic_extraction.manifest import (
    IngestionManifest,
    SourceEntry,
    ValidationSummary,
    save_manifest,
    load_manifest,
    list_manifests,
    get_latest_manifest,
)
from civic_extraction.pipeline import PipelineResult, StageStatus, StageState


class TestSourceEntry:
    """Tests for SourceEntry dataclass."""

    def test_create_source_entry(self):
        """Test creating a source entry."""
        entry = SourceEntry(
            source_id="proudcity-san-rafael",
            source_type="proudcity",
            records_ingested=50,
            records_failed=2,
        )
        assert entry.source_id == "proudcity-san-rafael"
        assert entry.source_type == "proudcity"
        assert entry.records_ingested == 50
        assert entry.records_failed == 2
        assert entry.records_skipped == 0
        assert entry.errors == []

    def test_source_entry_to_dict(self):
        """Test serializing source entry to dict."""
        entry = SourceEntry(
            source_id="test-source",
            source_type="legistar",
            records_ingested=100,
            errors=["Error 1"],
        )
        data = entry.to_dict()
        assert data["source_id"] == "test-source"
        assert data["source_type"] == "legistar"
        assert data["records_ingested"] == 100
        assert data["errors"] == ["Error 1"]

    def test_source_entry_from_dict(self):
        """Test deserializing source entry from dict."""
        data = {
            "source_id": "test-source",
            "source_type": "civicclerk",
            "records_ingested": 75,
            "records_failed": 5,
            "records_skipped": 10,
            "checkpoint": {"last_id": "123"},
            "errors": ["Warning"],
        }
        entry = SourceEntry.from_dict(data)
        assert entry.source_id == "test-source"
        assert entry.source_type == "civicclerk"
        assert entry.records_ingested == 75
        assert entry.records_failed == 5
        assert entry.records_skipped == 10
        assert entry.checkpoint == {"last_id": "123"}
        assert entry.errors == ["Warning"]


class TestValidationSummary:
    """Tests for ValidationSummary dataclass."""

    def test_create_validation_summary(self):
        """Test creating a validation summary."""
        summary = ValidationSummary(
            total_records=100,
            valid_records=95,
            invalid_records=5,
        )
        assert summary.total_records == 100
        assert summary.valid_records == 95
        assert summary.invalid_records == 5
        assert summary.validation_errors == []

    def test_validation_summary_roundtrip(self):
        """Test serializing and deserializing validation summary."""
        summary = ValidationSummary(
            total_records=50,
            valid_records=48,
            invalid_records=2,
            validation_errors=[
                {"record_id": "m1", "errors": ["missing title"]},
            ],
        )
        data = summary.to_dict()
        restored = ValidationSummary.from_dict(data)
        assert restored.total_records == 50
        assert restored.valid_records == 48
        assert restored.invalid_records == 2
        assert len(restored.validation_errors) == 1


class TestIngestionManifest:
    """Tests for IngestionManifest dataclass."""

    def test_generate_id(self):
        """Test manifest ID generation."""
        ts = datetime(2025, 12, 22, 11, 55, 30)
        manifest_id = IngestionManifest.generate_id("city-san-rafael", ts)
        assert manifest_id == "ingest_20251222_115530_city-san-rafael"

    def test_create_manifest(self):
        """Test creating a manifest with defaults."""
        manifest = IngestionManifest.create(
            jurisdiction_id="city-san-rafael",
            run_type="scheduled",
        )
        assert manifest.jurisdiction_id == "city-san-rafael"
        assert manifest.run_type == "scheduled"
        assert manifest.ingestion_id.startswith("ingest_")
        assert "city-san-rafael" in manifest.ingestion_id
        assert "hostname" in manifest.metadata
        assert "version" in manifest.metadata

    def test_manifest_to_dict(self):
        """Test serializing manifest to dict."""
        manifest = IngestionManifest.create(
            jurisdiction_id="city-berkeley",
            run_type="manual",
        )
        manifest.sources.append(SourceEntry(
            source_id="legistar-berkeley",
            source_type="legistar",
            records_ingested=100,
        ))
        manifest.success = True

        data = manifest.to_dict()
        assert data["jurisdiction_id"] == "city-berkeley"
        assert data["run_type"] == "manual"
        assert data["success"] is True
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source_id"] == "legistar-berkeley"

    def test_manifest_from_dict(self):
        """Test deserializing manifest from dict."""
        data = {
            "ingestion_id": "ingest_20251222_120000_city-test",
            "timestamp": "2025-12-22T12:00:00",
            "jurisdiction_id": "city-test",
            "run_type": "bootstrap",
            "pipeline_stages": {},
            "total_duration_ms": 5000.0,
            "success": True,
            "sources": [
                {
                    "source_id": "test-source",
                    "source_type": "proudcity",
                    "records_ingested": 25,
                    "records_failed": 0,
                    "records_skipped": 0,
                    "checkpoint": {},
                    "errors": [],
                }
            ],
            "validation": {
                "total_records": 25,
                "valid_records": 25,
                "invalid_records": 0,
                "validation_errors": [],
            },
            "checksums": {},
            "metadata": {"hostname": "test-host"},
        }
        manifest = IngestionManifest.from_dict(data)
        assert manifest.ingestion_id == "ingest_20251222_120000_city-test"
        assert manifest.jurisdiction_id == "city-test"
        assert manifest.success is True
        assert len(manifest.sources) == 1
        assert manifest.sources[0].records_ingested == 25

    def test_add_checksum(self):
        """Test adding content checksum."""
        manifest = IngestionManifest.create(jurisdiction_id="city-test")
        content = b"test content for checksum"
        checksum = manifest.add_checksum("test_data", content)

        assert "test_data" in manifest.checksums
        assert manifest.checksums["test_data"] == checksum
        assert len(checksum) == 64  # SHA-256 hex digest

    def test_add_file_checksum(self, tmp_path):
        """Test adding file checksum."""
        manifest = IngestionManifest.create(jurisdiction_id="city-test")

        # Create a test file
        test_file = tmp_path / "test.json"
        test_file.write_text('{"test": "data"}')

        checksum = manifest.add_file_checksum("test_file", str(test_file))
        assert "test_file" in manifest.checksums
        assert len(checksum) == 64

    def test_manifest_summary(self):
        """Test generating human-readable summary."""
        manifest = IngestionManifest.create(
            jurisdiction_id="city-san-rafael",
            run_type="scheduled",
        )
        manifest.success = True
        manifest.total_duration_ms = 5000.0
        manifest.sources.append(SourceEntry(
            source_id="proudcity-san-rafael",
            source_type="proudcity",
            records_ingested=50,
            records_failed=2,
        ))
        manifest.validation = ValidationSummary(
            total_records=52,
            valid_records=50,
            invalid_records=2,
        )

        summary = manifest.summary()
        assert "city-san-rafael" in summary
        assert "scheduled" in summary
        assert "50" in summary  # records ingested
        assert "Validation:" in summary


class TestFromPipelineResult:
    """Tests for creating manifest from PipelineResult."""

    def test_from_pipeline_result_basic(self):
        """Test creating manifest from a basic pipeline result."""
        # Create a mock PipelineResult
        result = PipelineResult(
            success=True,
            stages={
                "discover": StageStatus(
                    state=StageState.COMPLETED,
                    items_found=100,
                    items_processed=100,
                    duration_ms=1000.0,
                ),
                "ingest": StageStatus(
                    state=StageState.COMPLETED,
                    items_found=100,
                    items_processed=95,
                    duration_ms=2000.0,
                    metadata={
                        "validation": {
                            "total": 100,
                            "valid": 95,
                            "invalid": 5,
                            "errors": [],
                        }
                    },
                ),
                "store": StageStatus(
                    state=StageState.COMPLETED,
                    items_found=95,
                    items_processed=95,
                    duration_ms=500.0,
                ),
                "index": StageStatus(
                    state=StageState.COMPLETED,
                    items_found=95,
                    items_processed=95,
                    duration_ms=300.0,
                ),
            },
            total_duration_ms=3800.0,
            started_at=datetime(2025, 12, 22, 12, 0, 0),
            completed_at=datetime(2025, 12, 22, 12, 0, 4),
            jurisdiction_id="city-san-rafael",
            source_id="proudcity-san-rafael",
        )

        manifest = IngestionManifest.from_pipeline_result(
            result, run_type="scheduled", source_type="proudcity"
        )

        assert manifest.jurisdiction_id == "city-san-rafael"
        assert manifest.run_type == "scheduled"
        assert manifest.success is True
        assert manifest.total_duration_ms == 3800.0
        assert len(manifest.sources) == 1
        assert manifest.sources[0].source_id == "proudcity-san-rafael"
        assert manifest.sources[0].source_type == "proudcity"
        assert manifest.sources[0].records_ingested == 95
        assert manifest.validation.total_records == 100
        assert manifest.validation.valid_records == 95
        assert manifest.validation.invalid_records == 5


class TestManifestPersistence:
    """Tests for manifest save/load functionality."""

    def test_save_and_load_manifest(self, tmp_path):
        """Test saving and loading a manifest."""
        manifest = IngestionManifest.create(
            jurisdiction_id="city-test",
            run_type="manual",
        )
        manifest.success = True
        manifest.sources.append(SourceEntry(
            source_id="test-source",
            source_type="test",
            records_ingested=10,
        ))

        # Save manifest
        filepath = save_manifest(manifest, manifest_dir=str(tmp_path))

        # Verify file exists
        assert os.path.exists(filepath)
        assert "city-test" in filepath

        # Load and verify
        loaded = load_manifest(filepath)
        assert loaded.ingestion_id == manifest.ingestion_id
        assert loaded.jurisdiction_id == "city-test"
        assert loaded.success is True
        assert len(loaded.sources) == 1

    def test_list_manifests_empty(self, tmp_path):
        """Test listing manifests when none exist."""
        manifests = list_manifests("city-nonexistent", manifest_dir=str(tmp_path))
        assert manifests == []

    def test_list_manifests_multiple(self, tmp_path):
        """Test listing multiple manifests."""
        # Create several manifests with different timestamps
        for i in range(3):
            ts = datetime(2025, 12, 22, 10 + i, 0, 0)
            manifest = IngestionManifest.create(
                jurisdiction_id="city-test",
                run_type="scheduled",
                timestamp=ts,
            )
            manifest.success = True
            manifest.sources.append(SourceEntry(
                source_id="test-source",
                source_type="test",
                records_ingested=10 * (i + 1),
            ))
            save_manifest(manifest, manifest_dir=str(tmp_path))

        # List and verify
        manifests = list_manifests("city-test", manifest_dir=str(tmp_path))
        assert len(manifests) == 3

        # Should be sorted by timestamp descending (most recent first)
        assert manifests[0]["records_ingested"] == 30  # i=2, most recent
        assert manifests[1]["records_ingested"] == 20  # i=1
        assert manifests[2]["records_ingested"] == 10  # i=0, oldest

    def test_list_manifests_limit(self, tmp_path):
        """Test listing manifests with limit."""
        # Create 5 manifests
        for i in range(5):
            ts = datetime(2025, 12, 22, 10 + i, 0, 0)
            manifest = IngestionManifest.create(
                jurisdiction_id="city-test",
                timestamp=ts,
            )
            manifest.success = True
            save_manifest(manifest, manifest_dir=str(tmp_path))

        # List with limit
        manifests = list_manifests("city-test", manifest_dir=str(tmp_path), limit=3)
        assert len(manifests) == 3

    def test_get_latest_manifest(self, tmp_path):
        """Test getting the latest manifest."""
        # Create manifests
        for i in range(3):
            ts = datetime(2025, 12, 22, 10 + i, 0, 0)
            manifest = IngestionManifest.create(
                jurisdiction_id="city-test",
                run_type=f"run_{i}",
                timestamp=ts,
            )
            manifest.success = True
            manifest.sources.append(SourceEntry(
                source_id="test-source",
                source_type="test",
                records_ingested=10 * (i + 1),
            ))
            save_manifest(manifest, manifest_dir=str(tmp_path))

        # Get latest
        latest = get_latest_manifest("city-test", manifest_dir=str(tmp_path))
        assert latest is not None
        assert latest.run_type == "run_2"  # Most recent
        assert latest.sources[0].records_ingested == 30

    def test_get_latest_manifest_none(self, tmp_path):
        """Test getting latest when no manifests exist."""
        latest = get_latest_manifest("city-nonexistent", manifest_dir=str(tmp_path))
        assert latest is None


class TestManifestCLI:
    """Tests for manifest CLI functionality."""

    def test_cli_import(self):
        """Test that CLI module can be imported."""
        from civic_extraction.cli.manifest_cli import (
            add_manifest_parser,
            run_manifest,
        )
        assert add_manifest_parser is not None
        assert run_manifest is not None
