"""
Tests for civicos_extraction.cli.decisions module.

Tests the decision extraction CLI: source assessment, transcript formatting,
checkpoint persistence, meeting discovery, and the extraction orchestrator.
External dependencies (storage backends, LLM providers, file system) are mocked
at the I/O boundary; all logic under test runs for real.
"""

import json
import pytest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch, MagicMock

from civicos_extraction.cli.decisions import (
    DecisionResult,
    DecisionCheckpoint,
    ExtractionSource,
    SourceAssessment,
    assess_sources,
    format_transcript_for_extraction,
    checkpoint_path_for_decisions,
    save_checkpoint,
    load_checkpoint,
    decisions_exist,
    find_meetings,
)


# ---------------------------------------------------------------------------
# DecisionResult dataclass
# ---------------------------------------------------------------------------


class TestDecisionResult:
    def test_defaults(self):
        r = DecisionResult(meeting_id="m1", meeting_date="2026-01-15", status="success")
        assert r.decisions_count == 0
        assert r.error is None

    def test_with_decisions_count(self):
        r = DecisionResult(
            meeting_id="m1",
            meeting_date="2026-01-15",
            status="success",
            decisions_count=5,
        )
        assert r.decisions_count == 5
        assert r.status == "success"

    def test_error_result(self):
        r = DecisionResult(
            meeting_id="m1",
            meeting_date="2026-01-15",
            status="error",
            error="LLM timeout",
        )
        assert r.status == "error"
        assert r.error == "LLM timeout"
        assert r.decisions_count == 0


# ---------------------------------------------------------------------------
# DecisionCheckpoint dataclass
# ---------------------------------------------------------------------------


class TestDecisionCheckpoint:
    def test_to_dict_includes_all_fields(self):
        cp = DecisionCheckpoint(
            jurisdiction_id="city-san-rafael",
            last_meeting_id="m42",
            items_processed=10,
            items_extracted=7,
            items_skipped=2,
            items_failed=1,
            total_decisions=15,
            timestamp="2026-04-01T12:00:00",
            succeeded_meeting_ids=["m1", "m2", "m3"],
        )
        d = cp.to_dict()
        assert d["jurisdiction_id"] == "city-san-rafael"
        assert d["last_meeting_id"] == "m42"
        assert d["items_processed"] == 10
        assert d["items_extracted"] == 7
        assert d["items_skipped"] == 2
        assert d["items_failed"] == 1
        assert d["total_decisions"] == 15
        assert d["timestamp"] == "2026-04-01T12:00:00"
        assert d["succeeded_meeting_ids"] == ["m1", "m2", "m3"]

    def test_from_dict_roundtrip(self):
        original = DecisionCheckpoint(
            jurisdiction_id="city-fairfax",
            last_meeting_id="m99",
            items_processed=20,
            items_extracted=15,
            items_skipped=3,
            items_failed=2,
            total_decisions=30,
            timestamp="2026-04-02T08:30:00",
            succeeded_meeting_ids=["m10", "m20"],
        )
        restored = DecisionCheckpoint.from_dict(original.to_dict())
        assert restored.jurisdiction_id == "city-fairfax"
        assert restored.last_meeting_id == "m99"
        assert restored.items_processed == 20
        assert restored.items_extracted == 15
        assert restored.succeeded_meeting_ids == ["m10", "m20"]

    def test_from_dict_missing_succeeded_meeting_ids(self):
        """Old checkpoints without succeeded_meeting_ids should default to []."""
        data = {
            "jurisdiction_id": "city-test",
            "last_meeting_id": "m5",
            "items_processed": 5,
            "items_extracted": 3,
            "items_skipped": 1,
            "items_failed": 1,
            "total_decisions": 8,
            "timestamp": "2026-04-01T00:00:00",
        }
        cp = DecisionCheckpoint.from_dict(data)
        assert cp.succeeded_meeting_ids == []
        assert cp.items_processed == 5

    def test_default_succeeded_meeting_ids_is_none(self):
        cp = DecisionCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_id="m1",
            items_processed=1,
            items_extracted=1,
            items_skipped=0,
            items_failed=0,
            total_decisions=2,
            timestamp="2026-01-01T00:00:00",
        )
        assert cp.succeeded_meeting_ids is None


# ---------------------------------------------------------------------------
# ExtractionSource enum
# ---------------------------------------------------------------------------


class TestExtractionSource:
    def test_values(self):
        assert ExtractionSource.MINUTES.value == "minutes"
        assert ExtractionSource.TRANSCRIPT.value == "transcript"
        assert ExtractionSource.AGENDA.value == "agenda"

    def test_enum_members_count(self):
        assert len(ExtractionSource) == 3


# ---------------------------------------------------------------------------
# assess_sources() — pure logic, no mocks needed
# ---------------------------------------------------------------------------


class TestAssessSources:
    def test_minutes_preferred_over_transcript_and_agenda(self):
        meeting = {
            "id": "m1",
            "minutes_url": "https://example.com/minutes.pdf",
            "agenda_url": "https://example.com/agenda.pdf",
        }
        video_map = {"m1": "vid-abc"}
        result = assess_sources(meeting, video_map)
        assert result is not None
        assert result.best_source == ExtractionSource.MINUTES
        assert result.has_minutes is True
        assert result.has_transcript is True
        assert result.has_agenda is True
        assert result.meeting_id == "m1"

    def test_transcript_preferred_over_agenda(self):
        meeting = {
            "id": "m2",
            "agenda_url": "https://example.com/agenda.pdf",
        }
        video_map = {"m2": "vid-xyz"}
        result = assess_sources(meeting, video_map)
        assert result is not None
        assert result.best_source == ExtractionSource.TRANSCRIPT
        assert result.has_minutes is False
        assert result.has_transcript is True
        assert result.has_agenda is True
        assert result.transcript_video_id == "vid-xyz"

    def test_agenda_only(self):
        meeting = {"id": "m3", "agenda_url": "https://example.com/agenda.pdf"}
        result = assess_sources(meeting, None)
        assert result is not None
        assert result.best_source == ExtractionSource.AGENDA
        assert result.has_minutes is False
        assert result.has_transcript is False
        assert result.has_agenda is True
        assert result.transcript_video_id is None

    def test_no_sources_returns_none(self):
        meeting = {"id": "m4"}
        result = assess_sources(meeting, None)
        assert result is None

    def test_empty_minutes_url_not_counted(self):
        """Empty string minutes_url should not count as having minutes."""
        meeting = {"id": "m5", "minutes_url": "", "agenda_url": "https://example.com/a.pdf"}
        result = assess_sources(meeting, None)
        assert result is not None
        assert result.best_source == ExtractionSource.AGENDA
        assert result.has_minutes is False

    def test_meeting_id_fallback_to_meeting_id_key(self):
        meeting = {"meeting_id": "alt-id", "agenda_url": "https://example.com/a.pdf"}
        result = assess_sources(meeting, None)
        assert result is not None
        assert result.meeting_id == "alt-id"

    def test_meeting_id_fallback_to_unknown(self):
        meeting = {"agenda_url": "https://example.com/a.pdf"}
        result = assess_sources(meeting, None)
        assert result is not None
        assert result.meeting_id == "unknown"

    def test_video_map_none_means_no_transcript(self):
        meeting = {"id": "m6", "agenda_url": "https://example.com/a.pdf"}
        result = assess_sources(meeting, None)
        assert result.has_transcript is False

    def test_video_map_missing_meeting_means_no_transcript(self):
        meeting = {"id": "m7", "agenda_url": "https://example.com/a.pdf"}
        result = assess_sources(meeting, {"other-meeting": "vid-1"})
        assert result.has_transcript is False
        assert result.best_source == ExtractionSource.AGENDA


# ---------------------------------------------------------------------------
# format_transcript_for_extraction() — pure logic
# ---------------------------------------------------------------------------


class TestFormatTranscriptForExtraction:
    def test_basic_formatting(self):
        data = {
            "transcript": [
                {"speaker": "Mayor", "text": "Meeting is called to order."},
                {"speaker": "Clerk", "text": "Roll call."},
            ]
        }
        result = format_transcript_for_extraction(data)
        assert result == "[Mayor]: Meeting is called to order.\n\n[Clerk]: Roll call."

    def test_consecutive_same_speaker_no_speaker_prefix(self):
        data = {
            "transcript": [
                {"speaker": "Mayor", "text": "First sentence."},
                {"speaker": "Mayor", "text": "Second sentence."},
            ]
        }
        result = format_transcript_for_extraction(data)
        assert result == "[Mayor]: First sentence.\nSecond sentence."

    def test_speaker_change_inserts_blank_line(self):
        data = {
            "transcript": [
                {"speaker": "A", "text": "Hello."},
                {"speaker": "B", "text": "Hi."},
                {"speaker": "A", "text": "Bye."},
            ]
        }
        result = format_transcript_for_extraction(data)
        lines = result.split("\n")
        assert lines[0] == "[A]: Hello."
        assert lines[1] == ""  # blank line between speakers
        assert lines[2] == "[B]: Hi."
        assert lines[3] == ""
        assert lines[4] == "[A]: Bye."

    def test_empty_transcript_returns_none(self):
        result = format_transcript_for_extraction({"transcript": []})
        assert result is None

    def test_missing_transcript_key_returns_none(self):
        result = format_transcript_for_extraction({})
        assert result is None

    def test_whitespace_only_text_skipped(self):
        data = {
            "transcript": [
                {"speaker": "A", "text": "   "},
                {"speaker": "B", "text": "Real content."},
            ]
        }
        result = format_transcript_for_extraction(data)
        assert result == "[B]: Real content."

    def test_all_empty_text_returns_none(self):
        data = {
            "transcript": [
                {"speaker": "A", "text": ""},
                {"speaker": "B", "text": "   "},
            ]
        }
        result = format_transcript_for_extraction(data)
        assert result is None

    def test_missing_speaker_defaults_to_unknown(self):
        data = {
            "transcript": [
                {"text": "Something was said."},
            ]
        }
        result = format_transcript_for_extraction(data)
        assert result == "[Unknown]: Something was said."

    def test_text_is_stripped(self):
        data = {
            "transcript": [
                {"speaker": "Mayor", "text": "  Leading and trailing whitespace.  "},
            ]
        }
        result = format_transcript_for_extraction(data)
        assert result == "[Mayor]: Leading and trailing whitespace."

    def test_single_utterance(self):
        data = {
            "transcript": [
                {"speaker": "Clerk", "text": "Meeting adjourned."},
            ]
        }
        result = format_transcript_for_extraction(data)
        assert result == "[Clerk]: Meeting adjourned."


# ---------------------------------------------------------------------------
# checkpoint_path_for_decisions()
# ---------------------------------------------------------------------------


class TestCheckpointPathForDecisions:
    def test_constructs_correct_path(self, tmp_path):
        result = checkpoint_path_for_decisions("city-san-rafael", str(tmp_path))
        assert result == tmp_path / "decisions_city-san-rafael.json"

    def test_creates_directory_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        result = checkpoint_path_for_decisions("city-test", str(nested))
        assert result == nested / "decisions_city-test.json"
        assert nested.exists()

    def test_different_jurisdictions_different_paths(self, tmp_path):
        p1 = checkpoint_path_for_decisions("city-a", str(tmp_path))
        p2 = checkpoint_path_for_decisions("city-b", str(tmp_path))
        assert p1 != p2
        assert "city-a" in str(p1)
        assert "city-b" in str(p2)


# ---------------------------------------------------------------------------
# save_checkpoint() / load_checkpoint() — file I/O with tmp_path
# ---------------------------------------------------------------------------


class TestCheckpointPersistence:
    def _make_checkpoint(self, **overrides):
        defaults = {
            "jurisdiction_id": "city-test",
            "last_meeting_id": "m10",
            "items_processed": 10,
            "items_extracted": 7,
            "items_skipped": 2,
            "items_failed": 1,
            "total_decisions": 15,
            "timestamp": "2026-04-01T12:00:00",
            "succeeded_meeting_ids": ["m1", "m2"],
        }
        defaults.update(overrides)
        return DecisionCheckpoint(**defaults)

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "cp.json"
        original = self._make_checkpoint()
        save_checkpoint(original, path)

        loaded = load_checkpoint(path)
        assert loaded is not None
        assert loaded.jurisdiction_id == "city-test"
        assert loaded.last_meeting_id == "m10"
        assert loaded.items_processed == 10
        assert loaded.items_extracted == 7
        assert loaded.succeeded_meeting_ids == ["m1", "m2"]

    def test_load_nonexistent_returns_none(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        result = load_checkpoint(path)
        assert result is None

    def test_load_corrupt_file_returns_none(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json {{{")
        result = load_checkpoint(path)
        assert result is None

    def test_save_overwrites_existing(self, tmp_path):
        path = tmp_path / "cp.json"
        save_checkpoint(self._make_checkpoint(items_processed=5), path)
        save_checkpoint(self._make_checkpoint(items_processed=20), path)

        loaded = load_checkpoint(path)
        assert loaded.items_processed == 20

    def test_saved_file_is_valid_json(self, tmp_path):
        path = tmp_path / "cp.json"
        save_checkpoint(self._make_checkpoint(), path)

        raw = json.loads(path.read_text())
        assert raw["jurisdiction_id"] == "city-test"
        assert raw["items_processed"] == 10


# ---------------------------------------------------------------------------
# decisions_exist() — file existence check
# ---------------------------------------------------------------------------


class TestDecisionsExist:
    def test_returns_true_when_file_exists(self, tmp_path):
        meeting_id = "m123"
        (tmp_path / f"decisions_{meeting_id}.json").write_text("[]")
        assert decisions_exist(meeting_id, str(tmp_path)) is True

    def test_returns_false_when_file_missing(self, tmp_path):
        assert decisions_exist("nonexistent", str(tmp_path)) is False

    def test_different_meeting_ids_are_independent(self, tmp_path):
        (tmp_path / "decisions_m1.json").write_text("[]")
        assert decisions_exist("m1", str(tmp_path)) is True
        assert decisions_exist("m2", str(tmp_path)) is False


# ---------------------------------------------------------------------------
# find_meetings() — local mode (mock cloud path to isolate local logic)
# ---------------------------------------------------------------------------


class TestFindMeetingsLocal:
    """Tests for find_meetings() in local file mode."""

    def _patch_no_cloud(self):
        """Patch environment to ensure cloud path is not taken."""
        return patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False)

    def test_returns_none_when_dir_missing(self, tmp_path):
        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path / "nonexistent"), cloud=False)
        assert result is None

    def test_loads_meetings_from_json_list(self, tmp_path):
        meetings = [
            {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://example.com/a1.pdf"},
            {"id": "m2", "meeting_date": "2026-01-02", "agenda_url": "https://example.com/a2.pdf"},
        ]
        (tmp_path / "city_test_meetings.json").write_text(json.dumps(meetings))

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path), cloud=False)

        assert result is not None
        assert len(result) == 2
        assert result[0]["id"] == "m1"
        assert result[1]["id"] == "m2"

    def test_loads_meetings_from_events_dict(self, tmp_path):
        data = {
            "events": [
                {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"},
            ]
        }
        (tmp_path / "city_test_data.json").write_text(json.dumps(data))

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path), cloud=False)

        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "m1"

    def test_filters_meetings_without_agenda_url(self, tmp_path):
        meetings = [
            {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"},
            {"id": "m2", "meeting_date": "2026-01-02"},  # no agenda_url
        ]
        (tmp_path / "city_test_meetings.json").write_text(json.dumps(meetings))

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path), cloud=False)

        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "m1"

    def test_returns_none_when_no_meetings_have_agendas(self, tmp_path):
        meetings = [{"id": "m1", "meeting_date": "2026-01-01"}]
        (tmp_path / "city_test_meetings.json").write_text(json.dumps(meetings))

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path), cloud=False)

        assert result is None

    def test_since_filter(self, tmp_path):
        meetings = [
            {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"},
            {"id": "m2", "meeting_date": "2026-03-01", "agenda_url": "https://b.pdf"},
        ]
        (tmp_path / "city_test_meetings.json").write_text(json.dumps(meetings))

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path), cloud=False, since="2026-02-01")

        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "m2"

    def test_until_filter(self, tmp_path):
        meetings = [
            {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"},
            {"id": "m2", "meeting_date": "2026-03-01", "agenda_url": "https://b.pdf"},
        ]
        (tmp_path / "city_test_meetings.json").write_text(json.dumps(meetings))

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path), cloud=False, until="2026-02-01")

        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "m1"

    def test_since_and_until_combined(self, tmp_path):
        meetings = [
            {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"},
            {"id": "m2", "meeting_date": "2026-02-15", "agenda_url": "https://b.pdf"},
            {"id": "m3", "meeting_date": "2026-04-01", "agenda_url": "https://c.pdf"},
        ]
        (tmp_path / "city_test_meetings.json").write_text(json.dumps(meetings))

        with self._patch_no_cloud():
            result = find_meetings(
                "city-test", str(tmp_path), cloud=False,
                since="2026-02-01", until="2026-03-01",
            )

        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "m2"

    def test_loads_single_meeting_dict(self, tmp_path):
        """A file containing a single meeting dict (not list, not events wrapper)."""
        meeting = {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"}
        (tmp_path / "city_test_single.json").write_text(json.dumps(meeting))

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path), cloud=False)

        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "m1"

    def test_checkpoint_fallback_when_no_meeting_files(self, tmp_path):
        """When no meeting files found, tries checkpoint file."""
        input_dir = tmp_path / "meetings"
        input_dir.mkdir()  # empty dir, no matching files

        checkpoint_dir = Path("data/checkpoints")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_file = checkpoint_dir / "city-test.json"

        checkpoint_data = {
            "events": [
                {"id": "m1", "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"},
                {"id": "m2", "meeting_date": "2026-02-01"},  # no agenda
            ]
        }
        try:
            checkpoint_file.write_text(json.dumps(checkpoint_data))

            with self._patch_no_cloud():
                result = find_meetings("city-test", str(input_dir), cloud=False)

            # Checkpoint fallback must find the meeting with agenda_url
            assert result is not None, "checkpoint fallback should have returned meetings"
            assert len(result) == 1
            assert result[0]["id"] == "m1"
        finally:
            # Clean up checkpoint file we created
            if checkpoint_file.exists():
                checkpoint_file.unlink()

    def test_returns_none_no_files_no_checkpoint(self, tmp_path):
        """No meeting files and no checkpoint file → None."""
        input_dir = tmp_path / "empty_meetings"
        input_dir.mkdir()

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(input_dir), cloud=False)

        assert result is None

    def test_corrupt_meeting_file_is_skipped(self, tmp_path):
        """A corrupt JSON file should be skipped, other files still load."""
        (tmp_path / "city_test_bad.json").write_text("{bad json")
        meetings = [
            {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"},
        ]
        (tmp_path / "city_test_good.json").write_text(json.dumps(meetings))

        with self._patch_no_cloud():
            result = find_meetings("city-test", str(tmp_path), cloud=False)

        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "m1"


# ---------------------------------------------------------------------------
# find_meetings() — cloud mode
# ---------------------------------------------------------------------------


class TestFindMeetingsCloud:
    def test_returns_meetings_from_postgres(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_meetings.return_value = [
            {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"},
            {"id": "m2", "meeting_date": "2026-01-02"},
        ]

        with patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ), patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            # cloud=True forces cloud path
            result = find_meetings("city-test", str(tmp_path), cloud=True)

        assert result is not None
        # Cloud returns ALL meetings (source filtering happens later)
        assert len(result) == 2

    def test_falls_back_to_local_on_import_error(self, tmp_path):
        """When storage import fails, falls back to local file mode."""
        meetings = [
            {"id": "m1", "meeting_date": "2026-01-01", "agenda_url": "https://a.pdf"},
        ]
        (tmp_path / "city_test_meetings.json").write_text(json.dumps(meetings))

        with patch(
            "civicos.storage.get_storage_backend",
            side_effect=ImportError("no module"),
        ), patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = find_meetings("city-test", str(tmp_path), cloud=True)

        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "m1"


# ---------------------------------------------------------------------------
# decisions_exist_in_cloud()
# ---------------------------------------------------------------------------


class TestDecisionsExistInCloud:
    def test_returns_true_when_decisions_found(self):
        from civicos_extraction.cli.decisions import decisions_exist_in_cloud

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_decisions.return_value = [{"id": "d1"}]

        with patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            result = decisions_exist_in_cloud("city-test", "m1")

        assert result is True

    def test_returns_false_when_no_decisions(self):
        from civicos_extraction.cli.decisions import decisions_exist_in_cloud

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_decisions.return_value = []

        with patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            result = decisions_exist_in_cloud("city-test", "m1")

        assert result is False

    def test_returns_false_on_import_error(self):
        from civicos_extraction.cli.decisions import decisions_exist_in_cloud

        with patch(
            "civicos.storage.get_storage_backend",
            side_effect=ImportError("no module"),
        ):
            result = decisions_exist_in_cloud("city-test", "m1")

        assert result is False


# ---------------------------------------------------------------------------
# store_decisions_to_cloud()
# ---------------------------------------------------------------------------


class TestStoreDecisionsToCloud:
    def test_returns_true_on_successful_store(self):
        from civicos_extraction.cli.decisions import store_decisions_to_cloud

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.store_decisions.return_value = 3

        with patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            result = store_decisions_to_cloud("city-test", [{"id": "d1"}, {"id": "d2"}, {"id": "d3"}])

        assert result is True

    def test_returns_false_when_zero_stored(self):
        from civicos_extraction.cli.decisions import store_decisions_to_cloud

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.store_decisions.return_value = 0

        with patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            result = store_decisions_to_cloud("city-test", [{"id": "d1"}])

        assert result is False

    def test_returns_false_on_import_error(self):
        from civicos_extraction.cli.decisions import store_decisions_to_cloud

        with patch(
            "civicos.storage.get_storage_backend",
            side_effect=ImportError("no module"),
        ):
            result = store_decisions_to_cloud("city-test", [{"id": "d1"}])

        assert result is False

    def test_returns_false_on_exception(self):
        from civicos_extraction.cli.decisions import store_decisions_to_cloud

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.store_decisions.side_effect = RuntimeError("connection lost")

        with patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            result = store_decisions_to_cloud("city-test", [{"id": "d1"}])

        assert result is False


# ---------------------------------------------------------------------------
# extract_decisions_from_meeting() — mock LLM + storage, test orchestration
# ---------------------------------------------------------------------------


class TestExtractDecisionsFromMeeting:
    """Test extract_decisions_from_meeting with mocked analyzer and storage."""

    def test_skips_when_local_file_exists(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting_id = "m-existing"
        (tmp_path / f"decisions_{meeting_id}.json").write_text("[]")

        meeting = {"id": meeting_id, "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"}
        result = extract_decisions_from_meeting(
            meeting, str(tmp_path), "city-test",
        )
        assert result.status == "skipped"
        assert result.meeting_id == meeting_id

    def test_returns_no_sources_when_meeting_has_none(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting = {"id": "m-empty", "meeting_date": "2026-01-15"}
        mock_analyzer = MagicMock()

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test",
                analyzer=mock_analyzer,
            )

        assert result.status == "no_sources"
        assert result.meeting_id == "m-empty"

    def test_success_with_zero_decisions(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting = {"id": "m-nodec", "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"}
        mock_analyzer = MagicMock()
        mock_analyzer.extract_high_stakes_decisions.return_value = []

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test",
                analyzer=mock_analyzer,
            )

        assert result.status == "success"
        assert result.decisions_count == 0
        assert result.meeting_id == "m-nodec"

    def test_success_with_decisions_saves_local_file(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting = {"id": "m-dec", "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"}

        # Create a mock decision object
        mock_decision = MagicMock()
        mock_decision.to_dict.return_value = {
            "title": "Approve Housing Plan",
            "description": "Approved new housing plan",
            "budget_amount": 500000,
        }
        mock_decision.item_number = "7.1"
        mock_decision.item_ref = "7.1"
        mock_decision.title = "Approve Housing Plan"
        mock_decision.description = "Approved new housing plan"
        mock_decision.extracted_outcome = "approved"
        mock_decision.item_type = "action"
        mock_decision.passed = True
        mock_decision.vote_results = "5-0"
        mock_decision.project_types = ["housing"]
        mock_decision.keywords_for_matching = ["housing", "plan"]
        mock_decision.agenda_url = "https://a.pdf"
        mock_decision.minutes_url = None
        mock_decision.budget_amount = 500000

        mock_analyzer = MagicMock()
        mock_analyzer.extract_high_stakes_decisions.return_value = [mock_decision]

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test",
                analyzer=mock_analyzer,
            )

        assert result.status == "success"
        assert result.decisions_count == 1
        assert result.meeting_id == "m-dec"

        # Verify local file was created
        saved_path = tmp_path / "decisions_m-dec.json"
        assert saved_path.exists()

        saved_data = json.loads(saved_path.read_text())
        assert len(saved_data) == 1
        assert saved_data[0]["outcome"] == "approved"
        assert saved_data[0]["meeting_id"] == "m-dec"
        assert saved_data[0]["meeting_date"] == "2026-01-15"
        assert "housing" in saved_data[0]["topics"]

    def test_outcome_mapping_presentation_becomes_received(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting = {"id": "m-pres", "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"}

        mock_decision = MagicMock()
        mock_decision.to_dict.return_value = {"title": "Staff Report"}
        mock_decision.item_number = "3.1"
        mock_decision.item_ref = "3.1"
        mock_decision.title = "Staff Report"
        mock_decision.description = "Staff report on parks"
        mock_decision.extracted_outcome = None  # No explicit outcome
        mock_decision.item_type = "presentation"
        mock_decision.passed = None
        mock_decision.vote_results = None
        mock_decision.project_types = []
        mock_decision.keywords_for_matching = []
        mock_decision.agenda_url = None
        mock_decision.minutes_url = None
        mock_decision.budget_amount = None

        mock_analyzer = MagicMock()
        mock_analyzer.extract_high_stakes_decisions.return_value = [mock_decision]

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test",
                analyzer=mock_analyzer,
            )

        assert result.status == "success"
        saved = json.loads((tmp_path / "decisions_m-pres.json").read_text())
        assert saved[0]["outcome"] == "received"

    def test_outcome_mapping_passed_false_becomes_denied(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting = {"id": "m-denied", "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"}

        mock_decision = MagicMock()
        mock_decision.to_dict.return_value = {"title": "Rejected Motion"}
        mock_decision.item_number = "5.1"
        mock_decision.item_ref = "5.1"
        mock_decision.title = "Rejected Motion"
        mock_decision.description = "Motion to rezone"
        mock_decision.extracted_outcome = None
        mock_decision.item_type = "action"
        mock_decision.passed = False
        mock_decision.vote_results = "2-3"
        mock_decision.project_types = []
        mock_decision.keywords_for_matching = []
        mock_decision.agenda_url = None
        mock_decision.minutes_url = None
        mock_decision.budget_amount = None

        mock_analyzer = MagicMock()
        mock_analyzer.extract_high_stakes_decisions.return_value = [mock_decision]

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test",
                analyzer=mock_analyzer,
            )

        assert result.status == "success"
        saved = json.loads((tmp_path / "decisions_m-denied.json").read_text())
        assert saved[0]["outcome"] == "denied"

    def test_outcome_mapping_no_signal_becomes_other(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting = {"id": "m-other", "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"}

        mock_decision = MagicMock()
        mock_decision.to_dict.return_value = {"title": "Misc Item"}
        mock_decision.item_number = "6.1"
        mock_decision.item_ref = "6.1"
        mock_decision.title = "Misc Item"
        mock_decision.description = "Miscellaneous"
        mock_decision.extracted_outcome = None
        mock_decision.item_type = "action"  # not presentation/discussion
        mock_decision.passed = None  # not True/False
        mock_decision.vote_results = None
        mock_decision.project_types = []
        mock_decision.keywords_for_matching = []
        mock_decision.agenda_url = None
        mock_decision.minutes_url = None
        mock_decision.budget_amount = None

        mock_analyzer = MagicMock()
        mock_analyzer.extract_high_stakes_decisions.return_value = [mock_decision]

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test",
                analyzer=mock_analyzer,
            )

        assert result.status == "success"
        saved = json.loads((tmp_path / "decisions_m-other.json").read_text())
        assert saved[0]["outcome"] == "other"

    def test_extraction_error_returns_error_result(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting = {"id": "m-err", "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"}
        mock_analyzer = MagicMock()
        mock_analyzer.extract_high_stakes_decisions.side_effect = RuntimeError("LLM API down")

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test",
                analyzer=mock_analyzer,
            )

        assert result.status == "error"
        assert "LLM API down" in result.error

    def test_meeting_date_extracted_from_meeting_datetime(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        # meeting_datetime instead of meeting_date
        meeting = {
            "id": "m-dt",
            "meeting_datetime": "2026-03-15T18:00:00",
            "agenda_url": "https://a.pdf",
        }
        mock_analyzer = MagicMock()
        mock_analyzer.extract_high_stakes_decisions.return_value = []

        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test",
                analyzer=mock_analyzer,
            )

        assert result.meeting_date == "2026-03-15"

    def test_skips_when_cloud_decisions_exist(self, tmp_path):
        from civicos_extraction.cli.decisions import extract_decisions_from_meeting

        meeting = {"id": "m-cloud", "meeting_date": "2026-01-15", "agenda_url": "https://a.pdf"}

        with patch(
            "civicos_extraction.cli.decisions.decisions_exist_in_cloud",
            return_value=True,
        ), patch.dict("os.environ", {"DATABASE_URL": "postgresql://fake"}, clear=False):
            result = extract_decisions_from_meeting(
                meeting, str(tmp_path), "city-test", cloud=True,
            )

        assert result.status == "skipped"


# ---------------------------------------------------------------------------
# build_meeting_to_video_map()
# ---------------------------------------------------------------------------


class TestBuildMeetingToVideoMap:
    def test_inverts_video_to_meeting_mapping(self):
        from civicos_extraction.cli.decisions import build_meeting_to_video_map

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_video_meeting_mapping.return_value = {
            "vid-1": "m1",
            "vid-2": "m2",
        }

        with patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            result = build_meeting_to_video_map("city-test")

        assert result == {"m1": "vid-1", "m2": "vid-2"}

    def test_returns_empty_on_import_error(self):
        from civicos_extraction.cli.decisions import build_meeting_to_video_map

        with patch(
            "civicos.storage.get_storage_backend",
            side_effect=ImportError("no module"),
        ):
            result = build_meeting_to_video_map("city-test")

        assert result == {}

    def test_returns_empty_on_exception(self):
        from civicos_extraction.cli.decisions import build_meeting_to_video_map

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_video_meeting_mapping.side_effect = RuntimeError("db down")

        with patch(
            "civicos.storage.get_storage_backend",
            return_value=mock_backend,
        ):
            result = build_meeting_to_video_map("city-test")

        assert result == {}


# ---------------------------------------------------------------------------
# _enrich_source_item_ids — Legistar MatterId matching
# ---------------------------------------------------------------------------


class TestEnrichSourceItemIds:
    """Tests for post-extraction matching of LLM decisions to platform IDs."""

    def _make_decision(self, item_number="5.A", item_ref="Item 5.A", source_item_id=None):
        """Create a mock HighStakesDecision with the fields enrichment reads."""
        from types import SimpleNamespace
        return SimpleNamespace(
            item_number=item_number,
            item_ref=item_ref,
            source_item_id=source_item_id,
        )

    def test_non_legistar_meeting_is_noop(self):
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision()
        meeting = {"source_platform": "granicus"}
        _enrich_source_item_ids([decision], meeting)
        assert decision.source_item_id is None

    def test_missing_source_platform_is_noop(self):
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision()
        _enrich_source_item_ids([decision], {})
        assert decision.source_item_id is None

    def test_legistar_match_by_item_number(self):
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision(item_number="5.A")
        meeting = {
            "source_platform": "legistar",
            "raw_data": {"EventId": 999},
            "source_url": "https://testcity.legistar.com/MeetingDetail.aspx?ID=999",
        }

        mock_items = [
            {"event_item_id": 1, "agenda_number": "5.A", "title": "Housing",
             "matter_id": 42, "matter_file": "RES-2026-001"},
            {"event_item_id": 2, "agenda_number": "6.B", "title": "Budget",
             "matter_id": 43, "matter_file": "ORD-2026-002"},
        ]

        with patch(
            "civicos_extraction.clients.legistar.LegistarClient"
        ) as MockClient:
            MockClient.return_value.get_event_items.return_value = mock_items
            _enrich_source_item_ids([decision], meeting)

        assert decision.source_item_id == "42"

    def test_legistar_match_is_case_insensitive(self):
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision(item_number="5.a")
        meeting = {
            "source_platform": "legistar",
            "raw_data": {"EventId": 999},
            "source_url": "https://testcity.legistar.com/MeetingDetail.aspx?ID=999",
        }

        mock_items = [
            {"event_item_id": 1, "agenda_number": "5.A", "title": "Housing",
             "matter_id": 42, "matter_file": ""},
        ]

        with patch(
            "civicos_extraction.clients.legistar.LegistarClient"
        ) as MockClient:
            MockClient.return_value.get_event_items.return_value = mock_items
            _enrich_source_item_ids([decision], meeting)

        assert decision.source_item_id == "42"

    def test_legistar_no_match_leaves_none(self):
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision(item_number="99.Z")
        meeting = {
            "source_platform": "legistar",
            "raw_data": {"EventId": 999},
            "source_url": "https://testcity.legistar.com/MeetingDetail.aspx?ID=999",
        }

        mock_items = [
            {"event_item_id": 1, "agenda_number": "5.A", "title": "Housing",
             "matter_id": 42, "matter_file": ""},
        ]

        with patch(
            "civicos_extraction.clients.legistar.LegistarClient"
        ) as MockClient:
            MockClient.return_value.get_event_items.return_value = mock_items
            _enrich_source_item_ids([decision], meeting)

        assert decision.source_item_id is None

    def test_legistar_fallback_to_item_ref_when_no_item_number(self):
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision(item_number=None, item_ref="5.A")
        meeting = {
            "source_platform": "legistar",
            "raw_data": {"EventId": 999},
            "source_url": "https://testcity.legistar.com/MeetingDetail.aspx?ID=999",
        }

        mock_items = [
            {"event_item_id": 1, "agenda_number": "5.A", "title": "Housing",
             "matter_id": 42, "matter_file": ""},
        ]

        with patch(
            "civicos_extraction.clients.legistar.LegistarClient"
        ) as MockClient:
            MockClient.return_value.get_event_items.return_value = mock_items
            _enrich_source_item_ids([decision], meeting)

        assert decision.source_item_id == "42"

    def test_legistar_event_id_parsed_from_meeting_id(self):
        """When raw_data has no EventId, parse from meeting:{jur}:legistar:{id} format."""
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision(item_number="5.A")
        meeting = {
            "id": "meeting:city-test:legistar:999",
            "source_platform": "legistar",
            "raw_data": {},
            "source_url": "https://testcity.legistar.com/MeetingDetail.aspx?ID=999",
        }

        mock_items = [
            {"event_item_id": 1, "agenda_number": "5.A", "title": "Housing",
             "matter_id": 42, "matter_file": ""},
        ]

        with patch(
            "civicos_extraction.clients.legistar.LegistarClient"
        ) as MockClient:
            MockClient.return_value.get_event_items.return_value = mock_items
            _enrich_source_item_ids([decision], meeting)

        assert decision.source_item_id == "42"

    def test_legistar_api_error_is_graceful(self):
        """API failure doesn't crash — just leaves source_item_id as None."""
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision(item_number="5.A")
        meeting = {
            "source_platform": "legistar",
            "raw_data": {"EventId": 999},
            "source_url": "https://testcity.legistar.com/MeetingDetail.aspx?ID=999",
        }

        with patch(
            "civicos_extraction.clients.legistar.LegistarClient"
        ) as MockClient:
            MockClient.return_value.get_event_items.side_effect = RuntimeError("network error")
            _enrich_source_item_ids([decision], meeting)

        assert decision.source_item_id is None

    def test_legistar_items_without_matter_id_skipped(self):
        """Event items with no MatterId are excluded from the lookup."""
        from civicos_extraction.cli.decisions import _enrich_source_item_ids

        decision = self._make_decision(item_number="5.A")
        meeting = {
            "source_platform": "legistar",
            "raw_data": {"EventId": 999},
            "source_url": "https://testcity.legistar.com/MeetingDetail.aspx?ID=999",
        }

        mock_items = [
            {"event_item_id": 1, "agenda_number": "5.A", "title": "Housing",
             "matter_id": None, "matter_file": ""},
        ]

        with patch(
            "civicos_extraction.clients.legistar.LegistarClient"
        ) as MockClient:
            MockClient.return_value.get_event_items.return_value = mock_items
            _enrich_source_item_ids([decision], meeting)

        assert decision.source_item_id is None
