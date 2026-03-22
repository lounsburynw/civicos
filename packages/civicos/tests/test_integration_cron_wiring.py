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
        assert result.sections_added >= 1


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
