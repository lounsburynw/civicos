"""
Tests for legislative_context_cache.py — lazy-loading TTL cache for legislative context.

The only mocked boundary is time (via monkeypatching `time.time`) when we need
to simulate TTL expiration. The filesystem is real via pytest's `tmp_path`,
so all cache load/merge/invalidate logic runs end-to-end against real JSON files.

Covers:
- __init__ defaults and custom paths
- get() cache miss triggers load from disk
- get() cache hit returns cached value without re-reading
- TTL expiration triggers reload
- State-only, federal-only, and merged state+federal loading
- Missing-file returns None
- Malformed key, corrupted JSON, invalid key format
- invalidate() specific key vs. all
- stats() arithmetic on cached contexts

To run:
    pytest packages/civicos-services/tests/test_legislative_context_cache.py -q --override-ini="addopts="
"""

import json

import pytest

from civicos_services.legislative.legislative_context_cache import (
    LegislativeContextCache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state_file(root, state: str, topic: str, data: dict) -> None:
    """Create data/legislation/state/{state}/{topic}.json under root."""
    target = root / "state" / state / f"{topic}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data))


def _make_federal_file(root, topic: str, data: dict) -> None:
    """Create data/funding/federal/{topic}.json under root."""
    target = root / "federal" / f"{topic}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data))


@pytest.fixture
def cache_dirs(tmp_path):
    """Returns (legislation_dir, funding_dir) under tmp_path."""
    legislation = tmp_path / "legislation"
    funding = tmp_path / "funding"
    legislation.mkdir()
    funding.mkdir()
    return legislation, funding


@pytest.fixture
def make_cache(cache_dirs):
    """Factory for LegislativeContextCache bound to tmp_path."""
    legislation, funding = cache_dirs

    def _factory(ttl_seconds: int = 3600) -> LegislativeContextCache:
        return LegislativeContextCache(
            ttl_seconds=ttl_seconds,
            legislation_path=str(legislation),
            funding_path=str(funding),
        )

    return _factory


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_ttl_is_3600_seconds(self, cache_dirs):
        legislation, funding = cache_dirs
        cache = LegislativeContextCache(
            legislation_path=str(legislation),
            funding_path=str(funding),
        )
        assert cache.ttl == 3600

    def test_custom_ttl_is_stored(self, make_cache):
        cache = make_cache(ttl_seconds=42)
        assert cache.ttl == 42

    def test_cache_starts_empty(self, make_cache):
        cache = make_cache()
        assert cache.cache == {}

    def test_timestamps_start_empty(self, make_cache):
        cache = make_cache()
        assert cache.timestamps == {}

    def test_legislation_path_stored_as_path_object(self, cache_dirs):
        legislation, funding = cache_dirs
        cache = LegislativeContextCache(
            legislation_path=str(legislation),
            funding_path=str(funding),
        )
        # Path object, not str — so `/` composition works in _load
        assert cache.legislation_path == legislation
        assert cache.funding_path == funding

    def test_custom_paths_as_strings_are_converted(self):
        cache = LegislativeContextCache(
            legislation_path="/tmp/legislation_test_nonexistent_xyz",
            funding_path="/tmp/funding_test_nonexistent_xyz",
        )
        assert str(cache.legislation_path) == "/tmp/legislation_test_nonexistent_xyz"
        assert str(cache.funding_path) == "/tmp/funding_test_nonexistent_xyz"


# ---------------------------------------------------------------------------
# get() — cache miss triggers disk load
# ---------------------------------------------------------------------------


class TestGetCacheMiss:
    def test_first_get_loads_state_only_file(self, cache_dirs, make_cache):
        legislation, _ = cache_dirs
        _make_state_file(
            legislation,
            "california",
            "housing",
            {"laws": ["SB-9", "SB-10"], "state": "CA"},
        )
        cache = make_cache()

        result = cache.get("california", "housing")

        assert result == {"laws": ["SB-9", "SB-10"], "state": "CA"}

    def test_first_get_loads_federal_only_file(self, cache_dirs, make_cache):
        _, funding = cache_dirs
        _make_federal_file(
            funding,
            "housing",
            {"programs": {"HUD-CDBG": {"amount": 100}}},
        )
        cache = make_cache()

        result = cache.get("california", "housing")

        # State file absent → merged_data starts at {}, federal programs attached
        assert result == {"federal_programs": {"HUD-CDBG": {"amount": 100}}}

    def test_first_get_merges_state_and_federal_data(self, cache_dirs, make_cache):
        legislation, funding = cache_dirs
        _make_state_file(
            legislation,
            "california",
            "housing",
            {"laws": ["SB-9"], "state": "CA"},
        )
        _make_federal_file(
            funding,
            "housing",
            {"programs": {"HUD-CDBG": {"amount": 100}}},
        )
        cache = make_cache()

        result = cache.get("california", "housing")

        assert result == {
            "laws": ["SB-9"],
            "state": "CA",
            "federal_programs": {"HUD-CDBG": {"amount": 100}},
        }

    def test_missing_both_files_returns_none(self, make_cache):
        cache = make_cache()
        result = cache.get("california", "nonexistent_topic")
        assert result is None

    def test_missing_both_files_caches_none(self, make_cache):
        """Cache stores None so subsequent lookups don't re-hit disk."""
        cache = make_cache()
        cache.get("california", "nonexistent_topic")
        assert cache.cache["california_nonexistent_topic"] is None

    def test_federal_file_without_programs_key_adds_empty_dict(
        self, cache_dirs, make_cache
    ):
        """federal_data.get('programs', {}) → empty when key absent."""
        legislation, funding = cache_dirs
        _make_state_file(legislation, "california", "housing", {"laws": ["SB-9"]})
        _make_federal_file(funding, "housing", {"other_field": "value"})
        cache = make_cache()

        result = cache.get("california", "housing")

        assert result == {
            "laws": ["SB-9"],
            "federal_programs": {},
        }

    def test_state_data_empty_dict_merges_federal(self, cache_dirs, make_cache):
        """Edge case: state file is `{}` (truthy as dict, but empty)."""
        legislation, funding = cache_dirs
        _make_state_file(legislation, "california", "housing", {})
        _make_federal_file(funding, "housing", {"programs": {"X": 1}})
        cache = make_cache()

        result = cache.get("california", "housing")

        assert result == {"federal_programs": {"X": 1}}

    def test_state_data_none_json_null_falls_back_to_empty_dict(
        self, cache_dirs, make_cache
    ):
        """State file contains literal `null` → `state_data or {}` yields {}."""
        legislation, funding = cache_dirs
        (legislation / "state" / "california").mkdir(parents=True)
        (legislation / "state" / "california" / "housing.json").write_text("null")
        _make_federal_file(funding, "housing", {"programs": {"Y": 2}})
        cache = make_cache()

        result = cache.get("california", "housing")

        assert result == {"federal_programs": {"Y": 2}}


# ---------------------------------------------------------------------------
# get() — cache hit (second call within TTL)
# ---------------------------------------------------------------------------


class TestGetCacheHit:
    def test_second_get_does_not_reload_from_disk(self, cache_dirs, make_cache):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"laws": ["v1"]})
        cache = make_cache()

        first = cache.get("california", "housing")
        # Mutate the on-disk file to prove we don't re-read
        _make_state_file(legislation, "california", "housing", {"laws": ["v2"]})
        second = cache.get("california", "housing")

        assert first == {"laws": ["v1"]}
        assert second == {"laws": ["v1"]}

    def test_second_get_does_not_update_timestamp(self, cache_dirs, make_cache):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"laws": ["v1"]})
        cache = make_cache()

        cache.get("california", "housing")
        ts_first = cache.timestamps["california_housing"]
        cache.get("california", "housing")
        ts_second = cache.timestamps["california_housing"]

        assert ts_first == ts_second

    def test_different_keys_are_cached_independently(self, cache_dirs, make_cache):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"laws": ["H1"]})
        _make_state_file(legislation, "california", "transit", {"laws": ["T1"]})
        cache = make_cache()

        h = cache.get("california", "housing")
        t = cache.get("california", "transit")

        assert h == {"laws": ["H1"]}
        assert t == {"laws": ["T1"]}
        assert len(cache.cache) == 2


# ---------------------------------------------------------------------------
# get() — TTL expiration triggers reload
# ---------------------------------------------------------------------------


class TestGetTTLExpiration:
    def test_expired_ttl_reloads_from_disk(
        self, cache_dirs, make_cache, monkeypatch
    ):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        cache = make_cache(ttl_seconds=100)

        # First load at t=1000
        import civicos_services.legislative.legislative_context_cache as mod
        current = [1000.0]
        monkeypatch.setattr(mod.time, "time", lambda: current[0])
        first = cache.get("california", "housing")

        # Rewrite disk, advance clock past TTL
        _make_state_file(legislation, "california", "housing", {"v": 2})
        current[0] = 1000.0 + 101  # 1 second past TTL

        second = cache.get("california", "housing")

        assert first == {"v": 1}
        assert second == {"v": 2}

    def test_exactly_at_ttl_boundary_does_not_reload(
        self, cache_dirs, make_cache, monkeypatch
    ):
        """Check is `> self.ttl`, so exactly == ttl is still fresh."""
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        cache = make_cache(ttl_seconds=100)

        import civicos_services.legislative.legislative_context_cache as mod
        current = [1000.0]
        monkeypatch.setattr(mod.time, "time", lambda: current[0])
        cache.get("california", "housing")

        # Mutate disk, advance to exactly TTL boundary
        _make_state_file(legislation, "california", "housing", {"v": 2})
        current[0] = 1000.0 + 100  # exactly at TTL

        result = cache.get("california", "housing")
        assert result == {"v": 1}  # still cached

    def test_one_past_ttl_boundary_triggers_reload(
        self, cache_dirs, make_cache, monkeypatch
    ):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        cache = make_cache(ttl_seconds=100)

        import civicos_services.legislative.legislative_context_cache as mod
        current = [1000.0]
        monkeypatch.setattr(mod.time, "time", lambda: current[0])
        cache.get("california", "housing")

        _make_state_file(legislation, "california", "housing", {"v": 2})
        current[0] = 1000.0 + 100.001  # just past TTL

        result = cache.get("california", "housing")
        assert result == {"v": 2}

    def test_reload_updates_timestamp(self, cache_dirs, make_cache, monkeypatch):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        cache = make_cache(ttl_seconds=100)

        import civicos_services.legislative.legislative_context_cache as mod
        current = [1000.0]
        monkeypatch.setattr(mod.time, "time", lambda: current[0])
        cache.get("california", "housing")
        first_ts = cache.timestamps["california_housing"]

        current[0] = 2000.0
        cache.get("california", "housing")
        second_ts = cache.timestamps["california_housing"]

        assert second_ts > first_ts
        assert second_ts == 2000.0


# ---------------------------------------------------------------------------
# _load — key parsing and error handling
# ---------------------------------------------------------------------------


class TestLoadKeyParsing:
    def test_invalid_key_without_underscore_caches_none(self, make_cache):
        cache = make_cache()
        cache._load("nounderscore")
        assert cache.cache["nounderscore"] is None

    def test_invalid_key_does_not_set_timestamp(self, make_cache):
        cache = make_cache()
        cache._load("nounderscore")
        assert "nounderscore" not in cache.timestamps

    def test_key_with_multiple_underscores_splits_on_first(
        self, cache_dirs, make_cache
    ):
        """Key `california_affordable_housing` → state=california, topic=affordable_housing."""
        legislation, _ = cache_dirs
        _make_state_file(
            legislation,
            "california",
            "affordable_housing",
            {"bills": ["AB-1234"]},
        )
        cache = make_cache()

        result = cache.get("california", "affordable_housing")

        assert result == {"bills": ["AB-1234"]}


class TestLoadFileErrors:
    def test_corrupted_state_json_caches_none(self, cache_dirs, make_cache):
        legislation, _ = cache_dirs
        target = legislation / "state" / "california" / "housing.json"
        target.parent.mkdir(parents=True)
        target.write_text("{not valid json")
        cache = make_cache()

        result = cache.get("california", "housing")
        assert result is None
        assert cache.cache["california_housing"] is None

    def test_corrupted_federal_json_caches_none(self, cache_dirs, make_cache):
        _, funding = cache_dirs
        target = funding / "federal" / "housing.json"
        target.parent.mkdir(parents=True)
        target.write_text("{oops")
        cache = make_cache()

        result = cache.get("california", "housing")
        assert result is None

    def test_corrupted_state_file_does_not_set_timestamp(
        self, cache_dirs, make_cache
    ):
        legislation, _ = cache_dirs
        target = legislation / "state" / "california" / "housing.json"
        target.parent.mkdir(parents=True)
        target.write_text("not json")
        cache = make_cache()

        cache.get("california", "housing")
        # Timestamp only set on success path
        assert "california_housing" not in cache.timestamps


# ---------------------------------------------------------------------------
# invalidate()
# ---------------------------------------------------------------------------


class TestInvalidate:
    def test_specific_state_topic_removes_only_that_key(
        self, cache_dirs, make_cache
    ):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        _make_state_file(legislation, "california", "transit", {"v": 2})
        cache = make_cache()

        cache.get("california", "housing")
        cache.get("california", "transit")
        cache.invalidate(state="california", topic="housing")

        assert "california_housing" not in cache.cache
        assert "california_transit" in cache.cache
        assert cache.cache["california_transit"] == {"v": 2}

    def test_specific_key_also_removes_timestamp(self, cache_dirs, make_cache):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        cache = make_cache()

        cache.get("california", "housing")
        cache.invalidate(state="california", topic="housing")

        assert "california_housing" not in cache.timestamps

    def test_invalidate_all_clears_cache(self, cache_dirs, make_cache):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        _make_state_file(legislation, "texas", "housing", {"v": 2})
        cache = make_cache()

        cache.get("california", "housing")
        cache.get("texas", "housing")
        cache.invalidate()

        assert cache.cache == {}
        assert cache.timestamps == {}

    def test_invalidate_only_state_without_topic_clears_all(
        self, cache_dirs, make_cache
    ):
        """state set, topic None → hits the `else` branch (clear all)."""
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        _make_state_file(legislation, "texas", "housing", {"v": 2})
        cache = make_cache()

        cache.get("california", "housing")
        cache.get("texas", "housing")
        cache.invalidate(state="california")  # topic defaults to None

        # Only the (state AND topic) branch is specific — this hits the else
        assert cache.cache == {}
        assert cache.timestamps == {}

    def test_invalidate_only_topic_without_state_clears_all(
        self, cache_dirs, make_cache
    ):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        cache = make_cache()

        cache.get("california", "housing")
        cache.invalidate(topic="housing")  # state defaults to None

        assert cache.cache == {}

    def test_invalidate_nonexistent_key_does_not_raise(self, make_cache):
        cache = make_cache()
        # pop(..., None) swallows missing keys
        cache.invalidate(state="nonexistent", topic="xxx")
        assert cache.cache == {}

    def test_after_invalidate_next_get_reloads_from_disk(
        self, cache_dirs, make_cache
    ):
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"v": 1})
        cache = make_cache()

        cache.get("california", "housing")
        # Update disk content
        _make_state_file(legislation, "california", "housing", {"v": 2})
        # Invalidate forces a fresh load
        cache.invalidate(state="california", topic="housing")

        result = cache.get("california", "housing")
        assert result == {"v": 2}


# ---------------------------------------------------------------------------
# stats()
# ---------------------------------------------------------------------------


class TestStats:
    def test_empty_cache_has_zero_contexts(self, make_cache):
        cache = make_cache()
        stats = cache.stats()
        assert stats["cached_contexts"] == 0

    def test_empty_cache_has_zero_size(self, make_cache):
        cache = make_cache()
        stats = cache.stats()
        assert stats["total_size_kb"] == 0

    def test_stats_reports_configured_ttl(self, make_cache):
        cache = make_cache(ttl_seconds=7200)
        stats = cache.stats()
        assert stats["ttl_seconds"] == 7200

    def test_cached_contexts_count_includes_none_entries(
        self, cache_dirs, make_cache
    ):
        """Missing files cache None — still counted as a "cached context"."""
        legislation, _ = cache_dirs
        _make_state_file(legislation, "california", "housing", {"laws": ["SB-9"]})
        cache = make_cache()

        cache.get("california", "housing")
        cache.get("california", "missing_topic")  # caches None

        stats = cache.stats()
        assert stats["cached_contexts"] == 2

    def test_total_size_kb_computes_json_bytes_over_1024(
        self, cache_dirs, make_cache
    ):
        legislation, _ = cache_dirs
        payload = {"laws": ["A", "B", "C"]}
        _make_state_file(legislation, "california", "housing", payload)
        cache = make_cache()

        cache.get("california", "housing")

        # json.dumps({"laws": ["A", "B", "C"]}) = '{"laws": ["A", "B", "C"]}' = 24 chars
        expected_size = len(json.dumps(payload)) / 1024
        stats = cache.stats()
        assert stats["total_size_kb"] == expected_size

    def test_total_size_skips_none_entries(self, cache_dirs, make_cache):
        """Sum comprehension has `if v` guard — None entries contribute 0."""
        legislation, _ = cache_dirs
        payload = {"x": 1}
        _make_state_file(legislation, "california", "housing", payload)
        cache = make_cache()

        cache.get("california", "housing")
        cache.get("california", "missing")  # stores None

        stats = cache.stats()
        # Only the non-None value counts
        assert stats["total_size_kb"] == len(json.dumps(payload)) / 1024

    def test_size_sums_multiple_cached_contexts(self, cache_dirs, make_cache):
        legislation, _ = cache_dirs
        p1 = {"laws": ["SB-9"]}
        p2 = {"bills": ["AB-1"]}
        _make_state_file(legislation, "california", "housing", p1)
        _make_state_file(legislation, "texas", "transit", p2)
        cache = make_cache()

        cache.get("california", "housing")
        cache.get("texas", "transit")

        stats = cache.stats()
        # The stored merged dict has no federal_programs key since none exists
        # So cache contents equal the original dicts verbatim
        expected = (len(json.dumps(p1)) + len(json.dumps(p2))) / 1024
        assert stats["total_size_kb"] == expected


# ---------------------------------------------------------------------------
# Integration — end-to-end flow
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_flow_miss_hit_invalidate_reload(self, cache_dirs, make_cache):
        legislation, funding = cache_dirs
        _make_state_file(legislation, "california", "housing", {"laws": ["SB-9"]})
        _make_federal_file(
            funding, "housing", {"programs": {"HUD": {"amount": 100}}}
        )
        cache = make_cache()

        # 1. Miss → load + merge
        first = cache.get("california", "housing")
        assert first == {
            "laws": ["SB-9"],
            "federal_programs": {"HUD": {"amount": 100}},
        }
        assert cache.stats()["cached_contexts"] == 1

        # 2. Hit → same result, one entry
        second = cache.get("california", "housing")
        assert second == first

        # 3. Update disk, invalidate, reload
        _make_state_file(legislation, "california", "housing", {"laws": ["SB-10"]})
        cache.invalidate(state="california", topic="housing")
        assert cache.stats()["cached_contexts"] == 0

        third = cache.get("california", "housing")
        assert third == {
            "laws": ["SB-10"],
            "federal_programs": {"HUD": {"amount": 100}},
        }
