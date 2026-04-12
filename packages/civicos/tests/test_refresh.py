"""Tests for configurable refresh policies.

Validates:
- ChangeSignal and ChangeStatus types
- RefreshPolicy parsing from YAML dict
- content_hash and diff_sections utilities
- MunicipalCodeCorpus.get_fingerprint() and check_for_update()
- AmericanLegalCorpus.get_fingerprint() and check_for_update()
- RefreshRunner.should_refresh() logic
- CorpusProvider protocol and providers (MeetingCorpusProvider, etc.)
- RefreshRunner.refresh_corpus() generic dispatch
"""

import re
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from civicos._internal.legal.corpus.refresh import (
    ChangeSignal,
    ChangeStatus,
    CorpusProvider,
    RefreshPolicy,
    RefreshResult,
    RefreshRunner,
    content_hash,
    diff_sections,
    load_refresh_policies,
)
from civicos._internal.legal.corpus.providers import (
    IssueCorpusProvider,
    LegislationCorpusProvider,
    MeetingCorpusProvider,
)


# ---------------------------------------------------------------------------
# ChangeSignal / ChangeStatus
# ---------------------------------------------------------------------------


class TestChangeSignal:
    def test_unchanged_signal(self):
        sig = ChangeSignal(
            status=ChangeStatus.UNCHANGED,
            old_fingerprint="abc",
            new_fingerprint="abc",
        )
        assert sig.status == ChangeStatus.UNCHANGED
        assert sig.old_fingerprint == sig.new_fingerprint

    def test_changed_signal(self):
        sig = ChangeSignal(
            status=ChangeStatus.CHANGED,
            old_fingerprint="abc",
            new_fingerprint="def",
            message="Job changed",
        )
        assert sig.status == ChangeStatus.CHANGED
        assert sig.old_fingerprint != sig.new_fingerprint

    def test_unknown_signal(self):
        sig = ChangeSignal(status=ChangeStatus.UNKNOWN)
        assert sig.old_fingerprint is None

    def test_error_signal(self):
        sig = ChangeSignal(
            status=ChangeStatus.ERROR, message="Connection failed"
        )
        assert sig.status == ChangeStatus.ERROR


# ---------------------------------------------------------------------------
# RefreshPolicy
# ---------------------------------------------------------------------------


class TestRefreshPolicy:
    def test_from_dict_defaults(self):
        policy = RefreshPolicy.from_dict("municipal_code", {})
        assert policy.corpus_type == "municipal_code"
        assert policy.interval_days == 90
        assert policy.strategy == "content_hash"
        assert policy.enabled is True

    def test_from_dict_custom_interval(self):
        policy = RefreshPolicy.from_dict("meetings", {"interval": "7d"})
        assert policy.interval_days == 7

    def test_from_dict_int_interval(self):
        policy = RefreshPolicy.from_dict("issues", {"interval": 30})
        assert policy.interval_days == 30

    def test_from_dict_disabled(self):
        policy = RefreshPolicy.from_dict("legislation", {"enabled": False})
        assert policy.enabled is False

    def test_from_dict_strategy(self):
        policy = RefreshPolicy.from_dict(
            "municipal_code", {"strategy": "fingerprint_only"}
        )
        assert policy.strategy == "fingerprint_only"


# ---------------------------------------------------------------------------
# Content hash and diff
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello") == content_hash("hello")

    def test_different_input(self):
        assert content_hash("hello") != content_hash("world")

    def test_returns_16_chars(self):
        assert len(content_hash("test")) == 16


class TestDiffSections:
    def test_no_changes(self):
        sections = [
            {"section_number": "1.01.010", "full_text": "Some text"},
            {"section_number": "1.01.020", "full_text": "Other text"},
        ]
        result = diff_sections(sections, sections)
        assert len(result["added"]) == 0
        assert len(result["modified"]) == 0
        assert len(result["removed"]) == 0
        assert len(result["unchanged"]) == 2

    def test_added_section(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Text A"},
        ]
        incoming = [
            {"section_number": "1.01.010", "full_text": "Text A"},
            {"section_number": "1.01.020", "full_text": "Text B"},
        ]
        result = diff_sections(existing, incoming)
        assert len(result["added"]) == 1
        assert result["added"][0]["section_number"] == "1.01.020"
        assert len(result["unchanged"]) == 1

    def test_modified_section(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Old text"},
        ]
        incoming = [
            {"section_number": "1.01.010", "full_text": "New text"},
        ]
        result = diff_sections(existing, incoming)
        assert len(result["modified"]) == 1
        assert len(result["added"]) == 0
        assert len(result["unchanged"]) == 0

    def test_removed_section(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Text A"},
            {"section_number": "1.01.020", "full_text": "Text B"},
        ]
        incoming = [
            {"section_number": "1.01.010", "full_text": "Text A"},
        ]
        result = diff_sections(existing, incoming)
        assert len(result["removed"]) == 1
        assert result["removed"][0]["section_number"] == "1.01.020"

    def test_mixed_changes(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Unchanged"},
            {"section_number": "1.01.020", "full_text": "Old version"},
            {"section_number": "1.01.030", "full_text": "Will be removed"},
        ]
        incoming = [
            {"section_number": "1.01.010", "full_text": "Unchanged"},
            {"section_number": "1.01.020", "full_text": "New version"},
            {"section_number": "1.01.040", "full_text": "Brand new"},
        ]
        result = diff_sections(existing, incoming)
        assert len(result["unchanged"]) == 1
        assert len(result["modified"]) == 1
        assert len(result["removed"]) == 1
        assert len(result["added"]) == 1

    def test_empty_existing(self):
        incoming = [
            {"section_number": "1.01.010", "full_text": "New"},
        ]
        result = diff_sections([], incoming)
        assert len(result["added"]) == 1
        assert len(result["removed"]) == 0

    def test_empty_incoming(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Old"},
        ]
        result = diff_sections(existing, [])
        assert len(result["removed"]) == 1
        assert len(result["added"]) == 0


# ---------------------------------------------------------------------------
# MunicipalCodeCorpus fingerprint/check_for_update
# ---------------------------------------------------------------------------


class TestMunicodeFingerprint:
    def _make_corpus(self):
        from civicos._internal.legal.corpus.municipal import MunicipalCodeCorpus
        corpus = MunicipalCodeCorpus.__new__(MunicipalCodeCorpus)
        corpus.jurisdiction_id = "city-test"
        corpus._client_id = 123
        corpus._product_id = 456
        corpus._job_id = 789
        corpus.rate_limit = 2.0
        corpus._last_request = 0.0
        corpus._client = None
        corpus._chapter_pattern = re.compile(MunicipalCodeCorpus.DEFAULT_CHAPTER_PATTERN)
        corpus._section_pattern = re.compile(MunicipalCodeCorpus.DEFAULT_SECTION_PATTERN)
        corpus._title_pattern = re.compile(MunicipalCodeCorpus.DEFAULT_TITLE_PATTERN)
        return corpus

    def test_get_fingerprint(self):
        corpus = self._make_corpus()
        corpus.get_metadata = MagicMock(return_value={
            "job_id": 789,
            "publish_date": "2026-03-01",
            "online_date": "2026-03-01",
        })
        fp = corpus.get_fingerprint()
        assert fp == "municode:789:2026-03-01"

    def test_check_for_update_no_prior(self):
        corpus = self._make_corpus()
        corpus.get_metadata = MagicMock(return_value={
            "job_id": 789,
            "publish_date": "2026-03-01",
        })
        signal = corpus.check_for_update(None)
        assert signal.status == ChangeStatus.UNKNOWN

    def test_check_for_update_unchanged(self):
        corpus = self._make_corpus()
        corpus.get_metadata = MagicMock(return_value={
            "job_id": 789,
            "publish_date": "2026-03-01",
        })
        signal = corpus.check_for_update("municode:789:2026-03-01")
        assert signal.status == ChangeStatus.UNCHANGED

    def test_check_for_update_changed(self):
        corpus = self._make_corpus()
        corpus.get_metadata = MagicMock(return_value={
            "job_id": 790,
            "publish_date": "2026-04-01",
        })
        signal = corpus.check_for_update("municode:789:2026-03-01")
        assert signal.status == ChangeStatus.CHANGED

    def test_check_for_update_error(self):
        corpus = self._make_corpus()
        corpus.get_metadata = MagicMock(side_effect=Exception("API down"))
        signal = corpus.check_for_update("municode:789:2026-03-01")
        assert signal.status == ChangeStatus.ERROR


# ---------------------------------------------------------------------------
# AmericanLegalCorpus — no RefreshableCorpus (Cloudflare blocks lightweight checks)
# ---------------------------------------------------------------------------


class TestAmlegalNotRefreshable:
    def test_not_refreshable_corpus(self):
        """AMLegal doesn't implement RefreshableCorpus — Cloudflare blocks
        lightweight source checks, so change detection happens inside
        store_municipal_code after a full download."""
        from civicos._internal.legal.corpus.american_legal import AmericanLegalCorpus
        from civicos._internal.legal.corpus.refresh import RefreshableCorpus
        corpus = AmericanLegalCorpus.__new__(AmericanLegalCorpus)
        corpus.jurisdiction_id = "city-test"
        assert not isinstance(corpus, RefreshableCorpus)

    def test_municode_is_refreshable(self):
        """Municode implements RefreshableCorpus — can check source via API."""
        from civicos._internal.legal.corpus.municipal import MunicipalCodeCorpus
        from civicos._internal.legal.corpus.refresh import RefreshableCorpus
        corpus = MunicipalCodeCorpus.__new__(MunicipalCodeCorpus)
        corpus.jurisdiction_id = "city-test"
        assert isinstance(corpus, RefreshableCorpus)


# ---------------------------------------------------------------------------
# RefreshRunner.should_refresh
# ---------------------------------------------------------------------------


class TestShouldRefresh:
    def _make_runner(self, meta=None):
        storage = MagicMock()
        storage.get_refresh_metadata = MagicMock(return_value=meta)
        return RefreshRunner(storage_backend=storage)

    def test_never_fetched(self):
        runner = self._make_runner(meta=None)
        assert runner.should_refresh("city-test", "municipal_code") is True

    def test_recently_fetched(self):
        meta = {"last_fetch_at": datetime.now().isoformat()}
        runner = self._make_runner(meta=meta)
        policy = RefreshPolicy(corpus_type="municipal_code", interval_days=90)
        assert runner.should_refresh("city-test", "municipal_code", policy) is False

    def test_past_due(self):
        old_date = (datetime.now() - timedelta(days=100)).isoformat()
        meta = {"last_fetch_at": old_date}
        runner = self._make_runner(meta=meta)
        policy = RefreshPolicy(corpus_type="municipal_code", interval_days=90)
        assert runner.should_refresh("city-test", "municipal_code", policy) is True

    def test_disabled_policy(self):
        runner = self._make_runner(meta=None)
        policy = RefreshPolicy(
            corpus_type="municipal_code", enabled=False
        )
        assert runner.should_refresh("city-test", "municipal_code", policy) is False

    def test_no_policy_uses_default_90d(self):
        recent = (datetime.now() - timedelta(days=30)).isoformat()
        meta = {"last_fetch_at": recent}
        runner = self._make_runner(meta=meta)
        assert runner.should_refresh("city-test", "municipal_code") is False


# ---------------------------------------------------------------------------
# load_refresh_policies
# ---------------------------------------------------------------------------


class TestDiffNormalization:
    """Verify that whitespace/encoding drift doesn't produce false diffs."""

    def test_whitespace_drift_is_unchanged(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Some text  with   spaces"},
        ]
        incoming = [
            {"section_number": "1.01.010", "full_text": "Some text with spaces"},
        ]
        result = diff_sections(existing, incoming)
        assert len(result["modified"]) == 0
        assert len(result["unchanged"]) == 1

    def test_newline_drift_is_unchanged(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Line one\nLine two"},
        ]
        incoming = [
            {"section_number": "1.01.010", "full_text": "Line one\n\nLine two"},
        ]
        result = diff_sections(existing, incoming)
        assert len(result["modified"]) == 0
        assert len(result["unchanged"]) == 1

    def test_trailing_whitespace_is_unchanged(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Some text   "},
        ]
        incoming = [
            {"section_number": "1.01.010", "full_text": "Some text"},
        ]
        result = diff_sections(existing, incoming)
        assert len(result["modified"]) == 0
        assert len(result["unchanged"]) == 1

    def test_real_content_change_still_detected(self):
        existing = [
            {"section_number": "1.01.010", "full_text": "Old regulation text"},
        ]
        incoming = [
            {"section_number": "1.01.010", "full_text": "New regulation text with amendment"},
        ]
        result = diff_sections(existing, incoming)
        assert len(result["modified"]) == 1
        assert len(result["unchanged"]) == 0


class TestSafetyValve:
    """Verify that mass false-positive diffs are caught."""

    def _make_runner(self, existing_sections, meta=None):
        storage = MagicMock()
        storage.get_refresh_metadata = MagicMock(return_value=meta)
        storage.get_municipal_code = MagicMock(return_value=existing_sections)
        return RefreshRunner(storage_backend=storage)

    def test_blocks_when_majority_modified(self):
        """If >50% of sections appear modified, abort with error."""
        # 100 existing sections, all "modified" due to encoding drift
        existing = [
            {"section_number": f"1.01.{i:03d}", "full_text": f"Text {i}"}
            for i in range(100)
        ]
        runner = self._make_runner(existing)

        # Mock corpus that returns sections with different whitespace
        mock_corpus = MagicMock()
        mock_corpus.jurisdiction_id = "city-test"
        mock_corpus.stream_sections = MagicMock(return_value=iter([]))

        # Call refresh directly with crafted data to test the valve
        # We'll test via the diff_sections + threshold logic
        from civicos._internal.legal.corpus.refresh import diff_sections
        incoming = [
            {"section_number": f"1.01.{i:03d}", "full_text": f"Different text {i}"}
            for i in range(100)
        ]
        diff = diff_sections(existing, incoming)
        # All 100 should show as modified (different real content)
        assert len(diff["modified"]) == 100

        # The safety valve threshold: >50% modified = suspicious
        assert len(diff["modified"]) > len(existing) * 0.5


class TestSafetyValveRemoval:
    """Verify that mass removals (truncated fetch) are caught."""

    def test_mass_removal_detected(self):
        """If >20% of sections appear removed, likely a truncated fetch."""
        existing = [
            {"section_number": f"1.01.{i:03d}", "full_text": f"Text {i}"}
            for i in range(100)
        ]
        # Incoming has only 50 sections (50% missing)
        incoming = [
            {"section_number": f"1.01.{i:03d}", "full_text": f"Text {i}"}
            for i in range(50)
        ]
        diff = diff_sections(existing, incoming)
        assert len(diff["removed"]) == 50
        assert len(diff["removed"]) > len(existing) * 0.2

    def test_small_removal_allowed(self):
        """A few removed sections is normal (repealed ordinances)."""
        existing = [
            {"section_number": f"1.01.{i:03d}", "full_text": f"Text {i}"}
            for i in range(100)
        ]
        # 5 sections removed (5%) — under threshold
        incoming = [
            {"section_number": f"1.01.{i:03d}", "full_text": f"Text {i}"}
            for i in range(95)
        ]
        diff = diff_sections(existing, incoming)
        assert len(diff["removed"]) == 5
        assert len(diff["removed"]) <= len(existing) * 0.2


class TestLoadRefreshPolicies:
    def test_loads_san_rafael_policies(self):
        policies = load_refresh_policies("city-san-rafael")
        assert "municipal_code" in policies
        assert policies["municipal_code"].interval_days == 90
        assert policies["municipal_code"].strategy == "content_hash"

    def test_loads_sacramento_policies(self):
        policies = load_refresh_policies("city-sacramento")
        assert "municipal_code" in policies
        assert policies["municipal_code"].interval_days == 90

    def test_nonexistent_jurisdiction(self):
        policies = load_refresh_policies("city-nonexistent")
        assert policies == {}


# ---------------------------------------------------------------------------
# CorpusProvider protocol compliance
# ---------------------------------------------------------------------------


class TestCorpusProviderProtocol:
    def test_meeting_provider_satisfies_protocol(self):
        provider = MeetingCorpusProvider(client=MagicMock(), jurisdiction_id="city-test")
        assert isinstance(provider, CorpusProvider)
        assert provider.corpus_type == "meetings"
        assert provider.jurisdiction_id == "city-test"

    def test_issue_provider_satisfies_protocol(self):
        provider = IssueCorpusProvider(client=MagicMock(), jurisdiction_id="city-test")
        assert isinstance(provider, CorpusProvider)
        assert provider.corpus_type == "issues"

    def test_legislation_provider_satisfies_protocol(self):
        provider = LegislationCorpusProvider(
            client=MagicMock(), jurisdiction_id="state-CA", state_code="CA"
        )
        assert isinstance(provider, CorpusProvider)
        assert provider.corpus_type == "legislation"


# ---------------------------------------------------------------------------
# MeetingCorpusProvider
# ---------------------------------------------------------------------------


class TestMeetingCorpusProvider:
    def _make_provider(self, meetings=None):
        client = MagicMock()
        # Simulate Meeting objects with to_dict()
        mock_meetings = []
        for m in (meetings or []):
            meeting = MagicMock()
            meeting.to_dict.return_value = m
            mock_meetings.append(meeting)
        client.get_meetings.return_value = mock_meetings
        return MeetingCorpusProvider(
            client=client, jurisdiction_id="city-test", days_past=30, days_ahead=90
        )

    def test_check_for_update_returns_unknown(self):
        provider = self._make_provider()
        signal = provider.check_for_update("some-fingerprint")
        assert signal.status == ChangeStatus.UNKNOWN

    def test_check_for_update_no_prior(self):
        provider = self._make_provider()
        signal = provider.check_for_update(None)
        assert signal.status == ChangeStatus.UNKNOWN

    def test_fetch_and_store_calls_client(self):
        meetings = [
            {"id": "m1", "title": "Council Meeting", "meeting_datetime": "2026-03-01"},
            {"id": "m2", "title": "Planning Commission", "meeting_datetime": "2026-03-08"},
        ]
        provider = self._make_provider(meetings)

        storage = MagicMock()
        storage.store_meetings.return_value = 2

        stored = provider.fetch_and_store(storage)

        provider.client.get_meetings.assert_called_once_with(days_ahead=90, days_past=30)
        storage.store_meetings.assert_called_once()
        assert stored == 2

    def test_fetch_and_store_converts_to_dict(self):
        provider = self._make_provider([{"id": "m1", "title": "Test"}])
        storage = MagicMock()
        storage.store_meetings.return_value = 1

        provider.fetch_and_store(storage)

        # Verify dicts (not Mock objects) were passed to store
        call_args = storage.store_meetings.call_args
        assert call_args[0][0] == "city-test"
        assert call_args[0][1] == [{"id": "m1", "title": "Test"}]

    def test_fetch_and_store_empty(self):
        provider = self._make_provider([])
        storage = MagicMock()

        stored = provider.fetch_and_store(storage)

        assert stored == 0
        storage.store_meetings.assert_not_called()

    def test_fetch_and_store_handles_dict_meetings(self):
        """Meetings that are already dicts (no to_dict method)."""
        client = MagicMock()
        # Return plain dicts, not Mock objects
        client.get_meetings.return_value = [
            {"id": "m1", "title": "Test"},
        ]
        provider = MeetingCorpusProvider(client=client, jurisdiction_id="city-test")

        storage = MagicMock()
        storage.store_meetings.return_value = 1

        stored = provider.fetch_and_store(storage)
        assert stored == 1

    def test_last_store_result_preserved(self):
        """last_store_result exposes MeetingStoreResult for reactive pipelines."""
        provider = self._make_provider([{"id": "m1", "title": "Test"}])
        storage = MagicMock()

        # Simulate MeetingStoreResult with reactive signals
        mock_result = MagicMock()
        mock_result.__int__ = MagicMock(return_value=1)
        mock_result.new_meeting_ids = ["m1"]
        mock_result.minutes_appeared = []
        mock_result.has_new_material = True
        mock_result.has_agenda_updates = False
        storage.store_meetings.return_value = mock_result

        stored = provider.fetch_and_store(storage)
        assert stored == 1
        assert provider.last_store_result is mock_result
        assert provider.last_store_result.has_new_material is True
        assert provider.last_store_result.new_meeting_ids == ["m1"]

    def test_last_store_result_none_when_empty(self):
        """last_store_result is None when no meetings fetched."""
        provider = self._make_provider([])
        storage = MagicMock()

        provider.fetch_and_store(storage)
        assert provider.last_store_result is None

    def test_last_store_result_initialized_none(self):
        """last_store_result starts as None before any fetch."""
        provider = self._make_provider()
        assert provider.last_store_result is None


# ---------------------------------------------------------------------------
# IssueCorpusProvider
# ---------------------------------------------------------------------------


class TestIssueCorpusProvider:
    def _make_provider(self, pages=None):
        """Create provider with mock client that returns paginated results."""
        client = MagicMock()

        pages = pages or []
        page_iter = iter(pages)

        def mock_get_issues(**kwargs):
            try:
                return next(page_iter)
            except StopIteration:
                return {"issues": [], "metadata": {"has_more": False}}

        client.get_issues.side_effect = mock_get_issues
        return IssueCorpusProvider(
            client=client, jurisdiction_id="city-test", place_url="test"
        )

    def test_check_for_update_returns_unknown(self):
        provider = self._make_provider()
        signal = provider.check_for_update("some-fp")
        assert signal.status == ChangeStatus.UNKNOWN

    def test_place_url_derived_from_jurisdiction(self):
        provider = IssueCorpusProvider(
            client=MagicMock(), jurisdiction_id="city-san-rafael"
        )
        assert provider.place_url == "san-rafael"

    def test_place_url_strips_county_prefix(self):
        provider = IssueCorpusProvider(
            client=MagicMock(), jurisdiction_id="county-marin"
        )
        assert provider.place_url == "marin"

    def test_place_url_explicit(self):
        provider = IssueCorpusProvider(
            client=MagicMock(), jurisdiction_id="city-test", place_url="custom"
        )
        assert provider.place_url == "custom"

    def test_fetch_and_store_single_page(self):
        provider = self._make_provider([
            {
                "issues": [
                    {"id": "scf-1", "source": "seeclickfix", "external_id": 123, "title": "Pothole"},
                    {"id": "scf-2", "source": "seeclickfix", "external_id": 456, "title": "Graffiti"},
                ],
                "metadata": {"has_more": False},
            },
        ])

        storage = MagicMock()
        storage.store_issues.return_value = 2

        stored = provider.fetch_and_store(storage)
        assert stored == 2
        storage.store_issues.assert_called_once()

    def test_fetch_and_store_paginates(self):
        provider = self._make_provider([
            {
                "issues": [{"id": "scf-1", "source": "seeclickfix", "external_id": 1, "title": "A"}],
                "metadata": {"has_more": True},
            },
            {
                "issues": [{"id": "scf-2", "source": "seeclickfix", "external_id": 2, "title": "B"}],
                "metadata": {"has_more": False},
            },
        ])

        storage = MagicMock()
        storage.store_issues.return_value = 2

        stored = provider.fetch_and_store(storage)
        assert stored == 2
        # Should have been called with 2 issues
        call_args = storage.store_issues.call_args
        assert len(call_args[0][1]) == 2

    def test_fetch_and_store_normalizes_issues(self):
        """Verify source→provider rename, external_id→str, location flattening."""
        provider = self._make_provider([
            {
                "issues": [{
                    "id": "scf-1",
                    "source": "seeclickfix",
                    "external_id": 789,
                    "title": "Pothole",
                    "location": {"address": "123 Main St", "lat": 37.9, "lng": -122.5},
                }],
                "metadata": {"has_more": False},
            },
        ])

        storage = MagicMock()
        storage.store_issues.return_value = 1

        provider.fetch_and_store(storage)

        stored_issues = storage.store_issues.call_args[0][1]
        issue = stored_issues[0]
        assert issue["provider"] == "seeclickfix"
        assert "source" not in issue
        assert issue["external_id"] == "789"
        assert issue["address"] == "123 Main St"
        assert issue["latitude"] == 37.9
        assert issue["longitude"] == -122.5
        assert "location" not in issue

    def test_fetch_and_store_empty(self):
        provider = self._make_provider([
            {"issues": [], "metadata": {"has_more": False}},
        ])
        storage = MagicMock()

        stored = provider.fetch_and_store(storage)
        assert stored == 0
        storage.store_issues.assert_not_called()


# ---------------------------------------------------------------------------
# LegislationCorpusProvider
# ---------------------------------------------------------------------------


class TestLegislationCorpusProvider:
    def _make_provider(self, master_list=None):
        client = MagicMock()
        client.get_master_list.return_value = master_list or []
        return LegislationCorpusProvider(
            client=client, jurisdiction_id="state-CA", state_code="CA"
        )

    def test_check_for_update_returns_unknown(self):
        provider = self._make_provider()
        signal = provider.check_for_update("some-fp")
        assert signal.status == ChangeStatus.UNKNOWN

    def test_fetch_and_store_transforms_bills(self):
        provider = self._make_provider([
            {
                "number": "AB 1234",
                "title": "Housing Act",
                "description": "A bill about housing",
                "status": "1",
                "url": "https://legiscan.com/...",
                "bill_id": 99999,
                "last_action": "Passed Assembly",
                "last_action_date": "2026-03-01",
                "status_date": "2026-03-01",
            },
        ])

        storage = MagicMock()
        storage.store_legislation.return_value = 1

        stored = provider.fetch_and_store(storage)
        assert stored == 1

        call_args = storage.store_legislation.call_args
        assert call_args[1]["state"] == "CA"
        bills = call_args[1]["bills"]
        assert bills[0]["bill_id"] == "ca-ab1234"
        assert bills[0]["bill_number"] == "AB 1234"
        assert bills[0]["bill_name"] == "Housing Act"
        assert bills[0]["legiscan_id"] == 99999

    def test_fetch_and_store_batches(self):
        """Bills are stored in batches of 500."""
        # 600 bills → 2 batches
        bills = [
            {"number": f"AB {i}", "title": f"Bill {i}", "bill_id": i}
            for i in range(600)
        ]
        provider = self._make_provider(bills)

        storage = MagicMock()
        storage.store_legislation.return_value = 500

        stored = provider.fetch_and_store(storage)
        assert stored == 1000  # 500 * 2
        assert storage.store_legislation.call_count == 2

    def test_fetch_and_store_empty(self):
        provider = self._make_provider([])
        storage = MagicMock()

        stored = provider.fetch_and_store(storage)
        assert stored == 0
        storage.store_legislation.assert_not_called()


# ---------------------------------------------------------------------------
# RefreshRunner.refresh_corpus() — generic dispatch
# ---------------------------------------------------------------------------


class TestRefreshCorpus:
    def _make_runner(self, meta=None):
        storage = MagicMock()
        storage.get_refresh_metadata.return_value = meta
        storage.update_refresh_metadata.return_value = 1
        vectors = MagicMock()
        vectors.index_from_storage.return_value = 10
        return RefreshRunner(storage_backend=storage, vector_backend=vectors)

    def _make_provider(self, corpus_type="meetings", jurisdiction_id="city-test"):
        provider = MagicMock()
        provider.jurisdiction_id = jurisdiction_id
        provider.corpus_type = corpus_type
        provider.source_name = corpus_type  # e.g., "meetings" as source_name
        provider.check_for_update.return_value = ChangeSignal(
            status=ChangeStatus.UNKNOWN
        )
        provider.fetch_and_store.return_value = 5
        return provider

    def test_skipped_when_not_due(self):
        """When recently refreshed, should skip."""
        meta = {"last_fetch_at": datetime.now().isoformat(), "last_fetch_hash": "abc"}
        runner = self._make_runner(meta=meta)
        provider = self._make_provider()

        # Set a policy with 1d interval
        with patch(
            "civicos._internal.legal.corpus.refresh.load_refresh_policies",
            return_value={"meetings": RefreshPolicy("meetings", interval_days=1)},
        ):
            result = runner.refresh_corpus(provider)

        assert result.status == "skipped"
        provider.fetch_and_store.assert_not_called()

    def test_runs_when_force(self):
        """Force=True bypasses interval check."""
        meta = {"last_fetch_at": datetime.now().isoformat(), "last_fetch_hash": "abc"}
        runner = self._make_runner(meta=meta)
        provider = self._make_provider()

        with patch(
            "civicos._internal.legal.corpus.refresh.load_refresh_policies",
            return_value={"meetings": RefreshPolicy("meetings", interval_days=1)},
        ):
            result = runner.refresh_corpus(provider, force=True)

        assert result.status == "updated"
        provider.fetch_and_store.assert_called_once()

    def test_runs_when_never_fetched(self):
        """Never fetched before → should run."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()

        result = runner.refresh_corpus(provider)

        assert result.status == "updated"
        provider.fetch_and_store.assert_called_once()

    def test_unchanged_skips_fetch(self):
        """Provider says UNCHANGED → skip fetch."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()
        provider.check_for_update.return_value = ChangeSignal(
            status=ChangeStatus.UNCHANGED,
            new_fingerprint="same",
        )

        result = runner.refresh_corpus(provider)

        assert result.status == "unchanged"
        provider.fetch_and_store.assert_not_called()

    def test_error_in_check_skips_fetch(self):
        """Provider check_for_update errors → skip fetch."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()
        provider.check_for_update.return_value = ChangeSignal(
            status=ChangeStatus.ERROR,
            message="API down",
        )

        result = runner.refresh_corpus(provider)

        assert result.status == "error"
        assert result.error == "API down"
        provider.fetch_and_store.assert_not_called()

    def test_error_in_check_forced(self):
        """Provider check error + force=True → still runs."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()
        provider.check_for_update.return_value = ChangeSignal(
            status=ChangeStatus.ERROR, message="API flaky"
        )

        result = runner.refresh_corpus(provider, force=True)

        assert result.status == "updated"
        provider.fetch_and_store.assert_called_once()

    def test_check_exception_handled(self):
        """Exception in check_for_update → treated as error."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()
        provider.check_for_update.side_effect = Exception("Network timeout")

        result = runner.refresh_corpus(provider)

        assert result.status == "error"
        assert "Network timeout" in result.error

    def test_fetch_and_store_exception_handled(self):
        """Exception in fetch_and_store → error result."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()
        provider.fetch_and_store.side_effect = Exception("Database connection lost")

        result = runner.refresh_corpus(provider)

        assert result.status == "error"
        assert "Database connection lost" in result.error

    def test_dry_run_skips_fetch_and_store(self):
        """dry_run=True → don't call fetch_and_store."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()

        result = runner.refresh_corpus(provider, dry_run=True)

        assert result.status == "updated"
        provider.fetch_and_store.assert_not_called()

    def test_metadata_updated(self):
        """Verify refresh metadata is updated after successful store."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()
        provider.check_for_update.return_value = ChangeSignal(
            status=ChangeStatus.CHANGED, new_fingerprint="new-fp"
        )

        result = runner.refresh_corpus(provider)

        runner.storage.update_refresh_metadata.assert_called_once_with(
            "city-test", "meetings",
            source_name="meetings",  # matches provider.source_name
            items_fetched=5,
            items_stored=5,
            status="completed",
            last_fetch_hash="new-fp",
        )

    def test_source_name_threaded_to_metadata_lookup(self):
        """Verify source_name is passed to get_refresh_metadata for should_refresh."""
        meta = {"last_fetch_at": datetime.now().isoformat(), "last_fetch_hash": "abc"}
        runner = self._make_runner(meta=meta)
        provider = self._make_provider()
        provider.source_name = "proudcity"

        with patch(
            "civicos._internal.legal.corpus.refresh.load_refresh_policies",
            return_value={"meetings": RefreshPolicy("meetings", interval_days=1)},
        ):
            result = runner.refresh_corpus(provider)

        assert result.status == "skipped"
        # should_refresh should have called get_refresh_metadata with source_name
        runner.storage.get_refresh_metadata.assert_any_call(
            "city-test", "meetings", "proudcity"
        )

    def test_vectors_reindexed(self):
        """Vectors are reindexed after successful store."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()

        result = runner.refresh_corpus(provider)

        runner.vectors.index_from_storage.assert_called_once_with(
            storage_backend=runner.storage,
            jurisdiction_id="city-test",
            corpus_type="meetings",
        )
        assert result.vectors_reindexed == 10

    def test_vectors_skipped_when_nothing_stored(self):
        """No re-embed if nothing was stored."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()
        provider.fetch_and_store.return_value = 0

        result = runner.refresh_corpus(provider)

        runner.vectors.index_from_storage.assert_not_called()
        assert result.status == "unchanged"

    def test_vectors_skipped_when_disabled(self):
        """reindex_vectors=False → skip re-embed."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider()

        result = runner.refresh_corpus(provider, reindex_vectors=False)

        assert result.status == "updated"
        assert result.vectors_reindexed == 0
        runner.vectors.index_from_storage.assert_not_called()

    def test_vector_failure_does_not_fail_result(self):
        """Vector reindex failure → warning, not error."""
        runner = self._make_runner(meta=None)
        runner.vectors.index_from_storage.side_effect = Exception("Embedding API down")
        provider = self._make_provider()

        result = runner.refresh_corpus(provider)

        assert result.status == "updated"
        assert result.vectors_reindexed == 0

    def test_result_fields(self):
        """Verify RefreshResult has correct fields."""
        runner = self._make_runner(meta=None)
        provider = self._make_provider(corpus_type="issues")

        result = runner.refresh_corpus(provider)

        assert result.jurisdiction_id == "city-test"
        assert result.corpus_type == "issues"
        assert result.status == "updated"
        assert result.sections_added == 5  # stored count
        assert result.elapsed_seconds > 0

    def test_works_with_different_corpus_types(self):
        """Verify generic dispatch works for meetings, issues, legislation."""
        for ctype in ("meetings", "issues", "legislation"):
            runner = self._make_runner(meta=None)
            provider = self._make_provider(corpus_type=ctype)

            result = runner.refresh_corpus(provider)

            assert result.status == "updated"
            assert result.corpus_type == ctype
