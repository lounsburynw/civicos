"""
Integration tests for cron wiring: RefreshRunner + CorpusProviders against real Postgres.

Validates the full chain that scheduled_high/low_velocity_refresh() relies on:
1. Provider creation with mock clients (no external API calls)
2. RefreshRunner.refresh_corpus() against real PostgresBackend
3. MeetingStoreResult reactive signals flow through last_store_result
4. Config-based provider dispatch reads jurisdiction YAML correctly

Requires DATABASE_URL in .env (real Postgres). Skipped otherwise.
Uses a test jurisdiction ID and cleans up after each test.

Run: pytest packages/civicos/tests/test_integration_cron_wiring.py -v --override-ini="addopts="
"""

import os
import uuid

import pytest
from unittest.mock import MagicMock

# Load .env for DATABASE_URL
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")

# Skip all tests if no Postgres available
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — need real Postgres for integration tests",
)


@pytest.fixture
def test_jurisdiction():
    """Unique test jurisdiction ID, cleaned up after test."""
    jid = f"city-test-cron-{uuid.uuid4().hex[:8]}"
    yield jid

    # Cleanup: remove any data stored under this jurisdiction
    if DATABASE_URL:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                for table in ["meetings", "issues", "refresh_metadata", "vector_embeddings"]:
                    cur.execute(
                        f"DELETE FROM {table} WHERE jurisdiction_id = %s", (jid,)
                    )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()


@pytest.fixture
def backend():
    """Real PostgresBackend for integration testing."""
    from civicos.storage.postgres_backend import PostgresBackend
    return PostgresBackend(DATABASE_URL)


@pytest.fixture
def runner(backend):
    """RefreshRunner with real storage, mock vectors (no embedding cost)."""
    from civicos._internal.legal.corpus.refresh import RefreshRunner
    mock_vectors = MagicMock()
    mock_vectors.index_from_storage.return_value = 5
    return RefreshRunner(backend, mock_vectors)


# ---------------------------------------------------------------------------
# MeetingCorpusProvider + RefreshRunner integration
# ---------------------------------------------------------------------------


class TestMeetingCronWiring:
    """Full chain: mock client → MeetingCorpusProvider → RefreshRunner → real Postgres."""

    def _mock_client(self, meetings):
        """Create a mock ProudCity-like client returning Meeting-like objects."""
        client = MagicMock()
        mock_meetings = []
        for m in meetings:
            meeting = MagicMock()
            meeting.to_dict.return_value = m
            mock_meetings.append(meeting)
        client.get_meetings.return_value = mock_meetings
        return client

    def test_refresh_stores_and_exposes_reactive_signals(self, runner, backend, test_jurisdiction):
        """Meetings refresh stores data in Postgres and exposes MeetingStoreResult."""
        from civicos._internal.legal.corpus.providers import MeetingCorpusProvider

        meetings = [
            {
                "id": f"{test_jurisdiction}-council-2026-03-22",
                "title": "City Council Meeting",
                "meeting_datetime": "2026-03-22T19:00:00",
                "body_name": "City Council",
                "location": "City Hall",
                "jurisdiction_id": test_jurisdiction,
            },
            {
                "id": f"{test_jurisdiction}-planning-2026-03-25",
                "title": "Planning Commission",
                "meeting_datetime": "2026-03-25T18:00:00",
                "body_name": "Planning Commission",
                "location": "City Hall",
                "jurisdiction_id": test_jurisdiction,
            },
        ]

        client = self._mock_client(meetings)
        provider = MeetingCorpusProvider(
            client=client,
            jurisdiction_id=test_jurisdiction,
            source_name="proudcity",
        )

        result = runner.refresh_corpus(provider, force=True, reindex_vectors=False)

        # RefreshResult should show success
        assert result.status == "updated"
        assert result.sections_added == 2

        # Provider should expose real MeetingStoreResult
        sr = provider.last_store_result
        assert sr is not None
        assert int(sr) == 2

        # First run: all meetings are new
        assert sr.has_new_material is True
        assert len(sr.new_meeting_ids) == 2

        # No minutes/video/agenda on first store
        assert sr.has_minutes_updates is False
        assert sr.has_video_updates is False
        assert sr.has_agenda_updates is False

    def test_reactive_signals_detect_minutes_appearing(self, runner, backend, test_jurisdiction):
        """When minutes_url appears on an existing meeting, has_minutes_updates fires."""
        from civicos._internal.legal.corpus.providers import MeetingCorpusProvider

        meeting_id = f"{test_jurisdiction}-council-2026-03-22"

        # First store: meeting without minutes
        meetings_v1 = [{
            "id": meeting_id,
            "title": "City Council Meeting",
            "meeting_datetime": "2026-03-22T19:00:00",
            "body_name": "City Council",
            "jurisdiction_id": test_jurisdiction,
        }]

        client = self._mock_client(meetings_v1)
        provider = MeetingCorpusProvider(
            client=client, jurisdiction_id=test_jurisdiction, source_name="proudcity",
        )
        runner.refresh_corpus(provider, force=True, reindex_vectors=False)

        # Second store: same meeting, now with minutes_url
        meetings_v2 = [{
            "id": meeting_id,
            "title": "City Council Meeting",
            "meeting_datetime": "2026-03-22T19:00:00",
            "body_name": "City Council",
            "jurisdiction_id": test_jurisdiction,
            "minutes_url": "https://example.com/minutes.pdf",
        }]

        client2 = self._mock_client(meetings_v2)
        provider2 = MeetingCorpusProvider(
            client=client2, jurisdiction_id=test_jurisdiction, source_name="proudcity",
        )
        result2 = runner.refresh_corpus(provider2, force=True, reindex_vectors=False)

        sr = provider2.last_store_result
        assert sr is not None
        assert sr.has_minutes_updates is True
        assert meeting_id in sr.minutes_appeared

    def test_result_dict_matches_cron_expectations(self, runner, backend, test_jurisdiction):
        """The result dict built from last_store_result matches what downstream stages expect."""
        from civicos._internal.legal.corpus.providers import MeetingCorpusProvider

        meetings = [{
            "id": f"{test_jurisdiction}-test-2026-03-22",
            "title": "Test Meeting",
            "meeting_datetime": "2026-03-22T19:00:00",
            "body_name": "Test Body",
            "jurisdiction_id": test_jurisdiction,
        }]

        client = self._mock_client(meetings)
        provider = MeetingCorpusProvider(
            client=client, jurisdiction_id=test_jurisdiction, source_name="proudcity",
        )
        meeting_refresh = runner.refresh_corpus(provider, force=True, reindex_vectors=False)

        # Build the same result dict that the cron function builds
        sr = provider.last_store_result
        meetings_result = {
            "status": meeting_refresh.status,
            "meetings_stored": meeting_refresh.sections_added,
            "new_meeting_ids": getattr(sr, "new_meeting_ids", []) if sr else [],
            "updated_meeting_ids": getattr(sr, "updated_meeting_ids", []) if sr else [],
            "minutes_appeared_ids": getattr(sr, "minutes_appeared", []) if sr else [],
            "video_appeared_ids": getattr(sr, "video_appeared", []) if sr else [],
            "agenda_appeared_ids": getattr(sr, "agenda_appeared", []) if sr else [],
            "has_new_material": getattr(sr, "has_new_material", False) if sr else False,
            "has_minutes_updates": getattr(sr, "has_minutes_updates", False) if sr else False,
            "has_video_updates": getattr(sr, "has_video_updates", False) if sr else False,
            "has_agenda_updates": getattr(sr, "has_agenda_updates", False) if sr else False,
        }

        # Verify the downstream code can read reactive signals
        assert meetings_result["has_new_material"] is True
        assert len(meetings_result["new_meeting_ids"]) == 1
        assert meetings_result["has_minutes_updates"] is False
        assert meetings_result["has_video_updates"] is False

        # The downstream code uses these exact keys
        has_any_change = (
            meetings_result.get("has_new_material", False)
            or meetings_result.get("has_agenda_updates", False)
            or meetings_result.get("has_minutes_updates", False)
            or meetings_result.get("has_video_updates", False)
        )
        assert has_any_change is True


# ---------------------------------------------------------------------------
# IssueCorpusProvider + RefreshRunner integration
# ---------------------------------------------------------------------------


class TestIssueCronWiring:
    """Full chain: mock client → IssueCorpusProvider → RefreshRunner → real Postgres."""

    def test_refresh_stores_issues(self, runner, backend, test_jurisdiction):
        """Issues refresh stores data in Postgres via provider."""
        from civicos._internal.legal.corpus.providers import IssueCorpusProvider

        client = MagicMock()
        client.get_issues.side_effect = [
            {
                "issues": [
                    {
                        "external_id": "12345",
                        "title": "Pothole on Main St",
                        "source": "seeclickfix",
                        "status": "open",
                        "created_at": "2026-03-20T10:00:00",
                        "location": {"address": "123 Main St", "lat": 37.97, "lng": -122.52},
                    },
                ],
                "metadata": {"has_more": False},
            },
        ]

        provider = IssueCorpusProvider(
            client=client, jurisdiction_id=test_jurisdiction,
            source_name="seeclickfix",
        )
        result = runner.refresh_corpus(provider, force=True, reindex_vectors=False)

        assert result.status == "updated"
        assert result.sections_added == 1


# ---------------------------------------------------------------------------
# Config-based provider dispatch
# ---------------------------------------------------------------------------


class TestConfigDispatch:
    """Verify jurisdiction YAML drives provider selection."""

    def test_san_rafael_issues_source(self):
        """San Rafael config specifies seeclickfix as issues source."""
        from civicos.jurisdiction_config import load_jurisdiction_config

        config = load_jurisdiction_config("city-san-rafael")
        assert config.data_sources.issues == "seeclickfix"

    def test_san_rafael_meetings_source(self):
        """San Rafael config specifies proudcity as meetings source."""
        from civicos.jurisdiction_config import load_jurisdiction_config

        config = load_jurisdiction_config("city-san-rafael")
        assert config.data_sources.meetings.source_type == "proudcity"

    def test_missing_issues_source_is_empty(self):
        """Jurisdictions without issues config return empty string."""
        from civicos.jurisdiction_config import load_jurisdiction_config

        # State-level jurisdictions typically don't have issues
        config = load_jurisdiction_config("state-california")
        assert config.data_sources.issues == ""

    def test_dispatch_skips_empty_source(self):
        """Empty issues source means the cron should skip, not crash."""
        from civicos.jurisdiction_config import load_jurisdiction_config

        config = load_jurisdiction_config("state-california")
        issues_source = config.data_sources.issues

        # This is the same check the cron uses
        if not issues_source:
            skipped = True
        else:
            skipped = False

        assert skipped is True


# ---------------------------------------------------------------------------
# Refresh metadata integration
# ---------------------------------------------------------------------------


class TestRefreshMetadata:
    """Verify RefreshRunner updates metadata in real Postgres."""

    def test_metadata_written_after_refresh(self, runner, backend, test_jurisdiction):
        """refresh_corpus() writes refresh metadata to Postgres."""
        from civicos._internal.legal.corpus.providers import MeetingCorpusProvider

        client = MagicMock()
        meeting = MagicMock()
        meeting.to_dict.return_value = {
            "id": f"{test_jurisdiction}-meta-test",
            "title": "Metadata Test Meeting",
            "meeting_datetime": "2026-03-22T19:00:00",
            "body_name": "Test",
            "jurisdiction_id": test_jurisdiction,
        }
        client.get_meetings.return_value = [meeting]

        provider = MeetingCorpusProvider(
            client=client, jurisdiction_id=test_jurisdiction, source_name="test-source",
        )
        runner.refresh_corpus(provider, force=True, reindex_vectors=False)

        # Verify metadata was written
        meta = backend.get_refresh_metadata(test_jurisdiction, "meetings", "test-source")
        assert meta is not None
        assert meta["status"] == "completed"
        assert meta["items_stored"] == 1
        assert meta["last_fetch_at"] is not None


# ---------------------------------------------------------------------------
# Low-velocity cron fan-out (scripts/modal_ingest.py)
# ---------------------------------------------------------------------------


class TestLowVelocityCronFanOut:
    """Per-jurisdiction helper behavior for `scheduled_low_velocity_refresh`.

    Guards against regressions in `_refresh_jurisdiction_low_velocity` — the
    container that the top-level cron spawns once per jurisdiction. The spawn
    fan-out in the caller follows the same pattern as `batch_onboard` /
    `onboard_jurisdiction` (proven in production); what is novel here is the
    per-jurisdiction aggregation, stage skip gating, and failure isolation.
    """

    @pytest.fixture(scope="class")
    def modal_ingest(self):
        import sys
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[3]
        scripts_dir = project_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import modal_ingest
        return modal_ingest

    def _stage_patches(self, modal_ingest, *, mc=None, agenda=None, decisions=None):
        """Context manager producing patches for the three .local() stage calls."""
        from contextlib import ExitStack
        from unittest.mock import patch

        stack = ExitStack()
        mc_mock = stack.enter_context(patch.object(modal_ingest.fetch_municipal_code, "local"))
        agenda_mock = stack.enter_context(patch.object(modal_ingest.extract_agenda_items, "local"))
        decisions_mock = stack.enter_context(patch.object(modal_ingest.extract_decisions, "local"))

        if mc is not None:
            mc_mock.return_value = mc if not isinstance(mc, Exception) else None
            if isinstance(mc, Exception):
                mc_mock.side_effect = mc
        if agenda is not None:
            agenda_mock.return_value = agenda if not isinstance(agenda, Exception) else None
            if isinstance(agenda, Exception):
                agenda_mock.side_effect = agenda
        if decisions is not None:
            decisions_mock.return_value = decisions if not isinstance(decisions, Exception) else None
            if isinstance(decisions, Exception):
                decisions_mock.side_effect = decisions
        return stack, (mc_mock, agenda_mock, decisions_mock)

    def _patch_jurisdiction_config(self, municipal_code_source):
        from unittest.mock import MagicMock, patch

        cfg = MagicMock()
        cfg.data_sources.municipal_code = municipal_code_source
        return patch("civicos.jurisdiction_config.load_jurisdiction_config", return_value=cfg)

    def test_all_three_stages_aggregated_in_order(self, modal_ingest):
        """Happy path: municipal_code + agenda_items + decisions all succeed and land in results."""
        mc_return = {"sections_stored": 42, "auto_index": True, "vector_result": {"total_indexed": 10}}
        agenda_return = {"items_extracted": 7, "actionable_items": 4, "auto_index": True, "vector_result": {"total_indexed": 5}}
        decisions_return = {"decisions_extracted": 3, "meetings_extracted": 5, "auto_index": True, "vector_result": {"total_indexed": 2}}

        stack, (mc_mock, agenda_mock, decisions_mock) = self._stage_patches(
            modal_ingest, mc=mc_return, agenda=agenda_return, decisions=decisions_return,
        )
        with stack, self._patch_jurisdiction_config("municode"):
            out = modal_ingest._refresh_jurisdiction_low_velocity.local(jurisdiction="city-test-fanout")

        assert out["jurisdiction"] == "city-test-fanout"
        assert out["results"]["municipal_code"] == mc_return
        assert out["results"]["agenda_items"] == agenda_return
        assert out["results"]["decisions"] == decisions_return
        mc_mock.assert_called_once_with(jurisdiction="city-test-fanout", dry_run=False, auto_index=True)
        agenda_mock.assert_called_once_with(jurisdiction="city-test-fanout", dry_run=False, auto_index=True)
        decisions_mock.assert_called_once_with(jurisdiction="city-test-fanout", dry_run=False, auto_index=True)

    def test_per_stage_failure_does_not_block_other_stages(self, modal_ingest):
        """A single stage raising must not stop the subsequent stages from running."""
        decisions_return = {"decisions_extracted": 1, "meetings_extracted": 1, "auto_index": False}

        stack, (_, agenda_mock, decisions_mock) = self._stage_patches(
            modal_ingest,
            mc=RuntimeError("municode 500"),
            agenda=ValueError("agenda PDF unreachable"),
            decisions=decisions_return,
        )
        with stack, self._patch_jurisdiction_config("municode"):
            out = modal_ingest._refresh_jurisdiction_low_velocity.local(jurisdiction="city-test-partial")

        assert out["results"]["municipal_code"]["status"] == "failed"
        assert "municode 500" in out["results"]["municipal_code"]["error"]
        assert out["results"]["agenda_items"]["status"] == "failed"
        assert "agenda PDF unreachable" in out["results"]["agenda_items"]["error"]
        # Decisions ran even though upstream stages failed AND was called with the
        # full jurisdiction kwargs — the downstream stage must see the same invocation
        # shape regardless of earlier failures.
        assert out["results"]["decisions"] == decisions_return
        agenda_mock.assert_called_once_with(jurisdiction="city-test-partial", dry_run=False, auto_index=True)
        decisions_mock.assert_called_once_with(jurisdiction="city-test-partial", dry_run=False, auto_index=True)

    def test_municipal_code_skipped_when_not_configured(self, modal_ingest):
        """Jurisdictions without a Municode source record a `skipped` status, no fetch call.

        Also verifies the skip doesn't leak into downstream stages — agenda_items and
        decisions must still run and their return values land in the aggregate.
        """
        agenda_return = {"items_extracted": 0, "actionable_items": 0, "auto_index": False}
        decisions_return = {"decisions_extracted": 0, "meetings_extracted": 0, "auto_index": False}
        stack, (mc_mock, agenda_mock, decisions_mock) = self._stage_patches(
            modal_ingest,
            agenda=agenda_return,
            decisions=decisions_return,
        )
        with stack, self._patch_jurisdiction_config(None):
            out = modal_ingest._refresh_jurisdiction_low_velocity.local(jurisdiction="city-test-nomc")

        assert out["results"]["municipal_code"] == {"status": "skipped", "reason": "not_configured"}
        assert out["results"]["agenda_items"] == agenda_return
        assert out["results"]["decisions"] == decisions_return
        mc_mock.assert_not_called()
        agenda_mock.assert_called_once_with(jurisdiction="city-test-nomc", dry_run=False, auto_index=True)
        decisions_mock.assert_called_once_with(jurisdiction="city-test-nomc", dry_run=False, auto_index=True)
