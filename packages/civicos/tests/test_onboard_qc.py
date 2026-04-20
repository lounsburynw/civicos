"""
Tests for onboard_qc — post-ingest quality gates from April 2026 QC walkthrough.

Each check has a failure scenario (seeded with the pattern that tripped us up
during QC) and a clean baseline. Uses SQLiteBackend so tests run without a
Postgres dependency.
"""

import os
import tempfile

import pytest

from civicos.onboard_qc import (
    OnboardQCReport,
    check_agenda_url_coverage,
    check_chunk_closing_ratio,
    check_meeting_type_sanity,
    check_phantom_title_patterns,
    check_same_date_title_duplicates,
    run_onboard_qc,
)
from civicos.storage import SQLiteBackend


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def backend(temp_db):
    return SQLiteBackend(temp_db)


def _meeting(mid, title, dt="2026-04-01T18:00:00", mt="city_council", agenda_url="https://x/a.pdf"):
    return {
        "id": mid,
        "title": title,
        "meeting_datetime": dt,
        "meeting_type": mt,
        "status": "scheduled",
        "source_platform": "test",
        "agenda_url": agenda_url,
    }


def _chunk(meeting_id, agenda_item, idx=0):
    return {
        "meeting_id": meeting_id,
        "agenda_item": agenda_item,
        "agenda_title": f"item {agenda_item}",
        "text": f"chunk {idx} text content",
        "page_start": 1,
        "chunk_index": idx,
        "source_type": "agenda_packet",
    }


class TestAgendaUrlCoverage:
    def test_clean_ingest_passes(self, backend):
        backend.store_meetings("j1", [_meeting("m1", "A"), _meeting("m2", "B")])
        check = check_agenda_url_coverage(backend, "j1")
        assert check.severity == "ok"

    def test_simbli_partial_fails(self, backend):
        """0% agenda_url — the Simbli school pattern."""
        backend.store_meetings(
            "j1",
            [_meeting(f"m{i}", f"t{i}", agenda_url=None) for i in range(10)],
        )
        check = check_agenda_url_coverage(backend, "j1")
        assert check.severity == "fail"
        assert "0%" in check.message or "0/10" in check.message
        assert check.detail["ratio"] == 0.0

    def test_partial_coverage_fails_at_default_threshold(self, backend):
        meetings = [_meeting(f"m{i}", f"t{i}") for i in range(5)]
        meetings += [_meeting(f"n{i}", f"t{i}", agenda_url=None) for i in range(5)]
        backend.store_meetings("j1", meetings)
        check = check_agenda_url_coverage(backend, "j1")
        assert check.severity == "fail"
        assert check.detail["ratio"] == 0.5

    def test_no_meetings_warns(self, backend):
        check = check_agenda_url_coverage(backend, "empty")
        assert check.severity == "warn"


class TestMeetingTypeSanity:
    def test_clean_passes(self, backend):
        backend.store_meetings("j1", [_meeting("m1", "A", mt="city_council")])
        assert check_meeting_type_sanity(backend, "j1").severity == "ok"

    def test_view_N_leakage_fails(self, backend):
        """Berkeley pattern: view_2/view_5 archive keys leaking into meeting_type."""
        backend.store_meetings(
            "j1",
            [
                _meeting("m1", "A", mt="view_2"),
                _meeting("m2", "B", mt="view_5"),
                _meeting("m3", "C", mt="city_council"),
            ],
        )
        check = check_meeting_type_sanity(backend, "j1")
        assert check.severity == "fail"
        assert "view_2" in check.detail["bad_values"]
        assert "view_5" in check.detail["bad_values"]

    def test_null_meeting_type_fails(self, backend):
        """universal.py inference bug: produces null when title lacks a separator."""
        backend.store_meetings(
            "j1",
            [_meeting("m1", "A", mt=None), _meeting("m2", "B", mt="city_council")],
        )
        check = check_meeting_type_sanity(backend, "j1")
        assert check.severity == "fail"
        assert "<null>" in check.detail["bad_values"]


class TestChunkClosingRatio:
    def test_healthy_ratio_passes(self, backend):
        backend.store_meetings("j1", [_meeting("m1", "A")])
        chunks = [_chunk("m1", f"item_{i}", idx=i) for i in range(10)]
        chunks.append(_chunk("m1", "closing", idx=10))
        backend.store_chunks("j1", chunks)
        check = check_chunk_closing_ratio(backend, "j1")
        assert check.severity == "ok"

    def test_closing_dominance_warns(self, backend):
        """Alameda pattern: regex missed numbered items, everything fell to 'closing'."""
        backend.store_meetings("j1", [_meeting("m1", "A")])
        backend.store_chunks(
            "j1",
            [_chunk("m1", "closing", idx=i) for i in range(10)]
            + [_chunk("m1", "item_1", idx=10)],
        )
        check = check_chunk_closing_ratio(backend, "j1")
        assert check.severity == "warn"
        assert check.detail["closing"] == 10
        assert check.detail["total"] == 11

    def test_no_chunks_ok(self, backend):
        check = check_chunk_closing_ratio(backend, "empty")
        assert check.severity == "ok"


class TestSameDateTitleDuplicates:
    def test_clean_passes(self, backend):
        backend.store_meetings(
            "j1",
            [
                _meeting("m1", "City Council Meeting", dt="2026-04-01T18:00:00"),
                _meeting("m2", "Planning Commission", dt="2026-04-02T18:00:00"),
            ],
        )
        assert check_same_date_title_duplicates(backend, "j1").severity == "ok"

    def test_upcoming_vs_archive_variant_warns(self, backend):
        """Berkeley pattern: default view shows short title, archive shows long title."""
        backend.store_meetings(
            "j1",
            [
                _meeting("m1", "City Council Meeting", dt="2026-04-01T18:00:00"),
                _meeting("m2", "Regular City Council Meeting 6:00 p.m.", dt="2026-04-01T18:00:00"),
            ],
        )
        check = check_same_date_title_duplicates(backend, "j1")
        assert check.severity == "warn"
        assert check.detail["total_pairs"] == 1

    def test_unrelated_same_date_meetings_pass(self, backend):
        """Two genuinely different bodies meeting the same evening."""
        backend.store_meetings(
            "j1",
            [
                _meeting("m1", "City Council Meeting", dt="2026-04-01T18:00:00"),
                _meeting("m2", "Parks and Recreation Commission", dt="2026-04-01T19:30:00"),
            ],
        )
        assert check_same_date_title_duplicates(backend, "j1").severity == "ok"


class TestPhantomTitlePatterns:
    def test_clean_passes(self, backend):
        backend.store_meetings("j1", [_meeting("m1", "City Council Meeting")])
        assert check_phantom_title_patterns(backend, "j1").severity == "ok"

    def test_spanish_audio_files_detected(self, backend):
        """Marin pattern — filtered in granicus.py now, but defense-in-depth."""
        backend.store_meetings("j1", [_meeting("m1", "Spanish Audio Files")])
        check = check_phantom_title_patterns(backend, "j1")
        assert check.severity == "warn"
        assert check.detail["total"] == 1

    def test_system_test_detected(self, backend):
        """Alameda pattern — also filtered but worth detecting."""
        backend.store_meetings("j1", [_meeting("m1", "System Test")])
        assert check_phantom_title_patterns(backend, "j1").severity == "warn"


class TestRunOnboardQC:
    def test_returns_report_with_all_checks(self, backend):
        backend.store_meetings("j1", [_meeting("m1", "A")])
        report = run_onboard_qc(backend, "j1")
        assert isinstance(report, OnboardQCReport)
        assert report.jurisdiction_id == "j1"
        names = {c.name for c in report.checks}
        assert names == {
            "agenda_url_coverage",
            "meeting_type_sanity",
            "chunk_closing_ratio",
            "same_date_title_duplicates",
            "phantom_title_patterns",
        }

    def test_has_failures_reflects_fail_checks(self, backend):
        backend.store_meetings(
            "j1",
            [_meeting(f"m{i}", f"t{i}", agenda_url=None) for i in range(5)],
        )
        report = run_onboard_qc(backend, "j1")
        assert report.has_failures is True

    def test_format_is_readable(self, backend):
        backend.store_meetings("j1", [_meeting("m1", "A")])
        report = run_onboard_qc(backend, "j1")
        text = report.format()
        assert "j1" in text
        assert "agenda_url_coverage" in text

    def test_to_dict_serializable(self, backend):
        backend.store_meetings("j1", [_meeting("m1", "A")])
        d = run_onboard_qc(backend, "j1").to_dict()
        import json
        json.dumps(d)
