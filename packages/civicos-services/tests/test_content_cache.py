"""
Tests for content_cache.py — session-level caching for civic content downloads.

The only mocked boundary is `requests.get` (HTTP). The filesystem is real via
pytest's `tmp_path`, so all cache read/write/remove logic runs end-to-end.
Covers: init defaults, MD5 cache key derivation, cache miss/hit paths, corrupted
cache recovery (boundary on the 100-byte threshold), header merging, download
error propagation, stats arithmetic, context manager cleanup, and the
`download_with_cache` convenience wrapper.

To run:
    pytest packages/civicos-services/tests/test_content_cache.py -q --override-ini="addopts="
"""

import hashlib
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

import civicos_services.utils.content_cache as cc_mod
from civicos_services.utils.content_cache import (
    SessionContentCache,
    download_with_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(content: bytes, status_code: int = 200) -> MagicMock:
    """Build a mock `requests.Response` with .content and raise_for_status."""
    resp = MagicMock()
    resp.content = content
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code}")
    return resp


def _expected_key(url: str) -> str:
    """Compute the expected 16-char MD5 prefix cache key for a URL."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_cache_dir_is_system_temp(self):
        cache = SessionContentCache()
        assert cache.cache_dir == tempfile.gettempdir()

    def test_custom_cache_dir_is_used(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        assert cache.cache_dir == str(tmp_path)

    def test_empty_string_cache_dir_falls_back_to_temp(self):
        """`cache_dir or tempfile.gettempdir()` treats empty string as falsy."""
        cache = SessionContentCache(cache_dir="")
        assert cache.cache_dir == tempfile.gettempdir()

    def test_session_id_is_timestamp_format(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        # Format: YYYYMMDD_HHMMSS — 15 chars, underscore at index 8
        assert len(cache.session_id) == 15
        assert cache.session_id[8] == "_"
        assert cache.session_id[:8].isdigit()
        assert cache.session_id[9:].isdigit()

    def test_counters_start_at_zero(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        assert cache.cache_hits == 0
        assert cache.cache_misses == 0


# ---------------------------------------------------------------------------
# _generate_cache_key
# ---------------------------------------------------------------------------


class TestGenerateCacheKey:
    def test_returns_first_16_chars_of_md5_hex(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        url = "https://example.com/doc.pdf"
        assert cache._generate_cache_key(url) == hashlib.md5(url.encode()).hexdigest()[:16]

    def test_key_length_is_exactly_16(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        key = cache._generate_cache_key("https://example.com/really/long/url/path")
        assert len(key) == 16

    def test_key_is_lowercase_hex(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        key = cache._generate_cache_key("https://example.com/")
        assert all(c in "0123456789abcdef" for c in key)

    def test_different_urls_produce_different_keys(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        k1 = cache._generate_cache_key("https://a.com/x")
        k2 = cache._generate_cache_key("https://b.com/x")
        assert k1 != k2

    def test_same_url_is_deterministic(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        url = "https://example.com/doc.pdf"
        assert cache._generate_cache_key(url) == cache._generate_cache_key(url)

    def test_empty_url_produces_md5_of_empty_string(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        # md5("") = d41d8cd98f00b204e9800998ecf8427e — first 16: d41d8cd98f00b204
        assert cache._generate_cache_key("") == "d41d8cd98f00b204"


# ---------------------------------------------------------------------------
# _download_content
# ---------------------------------------------------------------------------


class TestDownloadContent:
    def test_returns_response_content_bytes(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        payload = b"hello world " * 20
        resp = _mock_response(payload)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            result = cache._download_content("https://example.com/x")
        assert result == payload

    def test_uses_default_mozilla_user_agent(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            cache._download_content("https://example.com/x")
        headers = mock_get.call_args[1]["headers"]
        assert "Mozilla/5.0" in headers["User-Agent"]
        assert "Chrome" in headers["User-Agent"]

    def test_custom_headers_merge_with_default_ua(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            cache._download_content(
                "https://example.com/x", headers={"X-Custom": "v1"}
            )
        headers = mock_get.call_args[1]["headers"]
        assert headers["X-Custom"] == "v1"
        assert "Mozilla/5.0" in headers["User-Agent"]

    def test_custom_user_agent_overrides_default(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            cache._download_content(
                "https://example.com/x", headers={"User-Agent": "my-bot/1.0"}
            )
        headers = mock_get.call_args[1]["headers"]
        assert headers["User-Agent"] == "my-bot/1.0"

    def test_timeout_is_300_seconds(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            cache._download_content("https://example.com/x")
        assert mock_get.call_args[1]["timeout"] == 300

    def test_url_is_first_positional_arg(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            cache._download_content("https://example.com/target")
        assert mock_get.call_args[0][0] == "https://example.com/target"

    def test_http_4xx_raises_http_error(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"", status_code=404)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            with pytest.raises(requests.HTTPError):
                cache._download_content("https://example.com/x")

    def test_http_5xx_raises_http_error(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"", status_code=500)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            with pytest.raises(requests.HTTPError):
                cache._download_content("https://example.com/x")

    def test_connection_error_propagates(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        with patch.object(
            cc_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            with pytest.raises(requests.ConnectionError):
                cache._download_content("https://example.com/x")

    def test_none_headers_yields_only_default(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            cache._download_content("https://example.com/x", headers=None)
        headers = mock_get.call_args[1]["headers"]
        assert list(headers.keys()) == ["User-Agent"]


# ---------------------------------------------------------------------------
# _save_to_cache
# ---------------------------------------------------------------------------


class TestSaveToCache:
    def test_writes_bytes_to_target_path(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        target = tmp_path / "saved_file"
        cache._save_to_cache(str(target), b"payload content here")
        assert target.read_bytes() == b"payload content here"

    def test_empty_bytes_still_writes_empty_file(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        target = tmp_path / "empty_file"
        cache._save_to_cache(str(target), b"")
        assert target.exists()
        assert target.read_bytes() == b""

    def test_write_failure_is_swallowed_and_no_file_created(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        # Parent directory doesn't exist → OSError — must be swallowed
        bad_path = str(tmp_path / "no_such_dir" / "file")
        cache._save_to_cache(bad_path, b"content")
        assert not os.path.exists(bad_path)

    def test_overwrite_replaces_existing_content(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        target = tmp_path / "saved_file"
        target.write_bytes(b"old")
        cache._save_to_cache(str(target), b"new content " * 20)
        assert target.read_bytes() == b"new content " * 20


# ---------------------------------------------------------------------------
# get_content — cache miss (first call)
# ---------------------------------------------------------------------------


class TestGetContentMiss:
    def test_first_call_returns_content_and_cached_false(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        payload = b"fresh content " * 20
        resp = _mock_response(payload)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            content, was_cached = cache.get_content("https://example.com/x")
        assert content == payload
        assert was_cached is False

    def test_first_call_writes_cache_file_with_downloaded_bytes(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        payload = b"fresh content " * 20
        resp = _mock_response(payload)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            cache.get_content("https://example.com/x")
        files = [
            f for f in os.listdir(tmp_path)
            if f.startswith(f"civic_cache_{cache.session_id}_")
        ]
        assert len(files) == 1
        assert (tmp_path / files[0]).read_bytes() == payload

    def test_first_call_increments_miss_counter(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            cache.get_content("https://example.com/x")
        assert cache.cache_misses == 1
        assert cache.cache_hits == 0

    def test_download_failure_propagates(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        with patch.object(
            cc_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            with pytest.raises(requests.ConnectionError):
                cache.get_content("https://example.com/x")

    def test_download_failure_does_not_increment_counters(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        with patch.object(
            cc_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            with pytest.raises(requests.ConnectionError):
                cache.get_content("https://example.com/x")
        assert cache.cache_misses == 0
        assert cache.cache_hits == 0

    def test_download_failure_leaves_no_cache_file(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        with patch.object(
            cc_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            with pytest.raises(requests.ConnectionError):
                cache.get_content("https://example.com/x")
        files = [f for f in os.listdir(tmp_path) if f.startswith("civic_cache_")]
        assert files == []

    def test_custom_headers_forwarded_to_http_layer(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            cache.get_content("https://example.com/x", headers={"X-Auth": "token"})
        assert mock_get.call_args[1]["headers"]["X-Auth"] == "token"


# ---------------------------------------------------------------------------
# get_content — cache hit (second call)
# ---------------------------------------------------------------------------


class TestGetContentHit:
    def test_second_call_returns_cached_content_without_http(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        payload = b"fresh content " * 20
        resp = _mock_response(payload)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            content1, cached1 = cache.get_content("https://example.com/x")
            content2, cached2 = cache.get_content("https://example.com/x")
        # Only one HTTP call made — second served from disk
        assert mock_get.call_count == 1
        assert content1 == payload
        assert content2 == payload
        assert cached1 is False
        assert cached2 is True

    def test_second_call_increments_hit_counter_not_miss(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            cache.get_content("https://example.com/x")
            cache.get_content("https://example.com/x")
        assert cache.cache_hits == 1
        assert cache.cache_misses == 1

    def test_three_hits_after_one_miss(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            for _ in range(4):
                cache.get_content("https://example.com/x")
        assert cache.cache_misses == 1
        assert cache.cache_hits == 3

    def test_different_urls_do_not_share_cache(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp_a = _mock_response(b"A" * 200)
        resp_b = _mock_response(b"B" * 200)
        with patch.object(
            cc_mod.requests, "get", side_effect=[resp_a, resp_b]
        ):
            ca, cached_a = cache.get_content("https://a.com/")
            cb, cached_b = cache.get_content("https://b.com/")
        assert ca == b"A" * 200
        assert cb == b"B" * 200
        assert cached_a is False
        assert cached_b is False
        assert cache.cache_misses == 2
        assert cache.cache_hits == 0


# ---------------------------------------------------------------------------
# get_content — corrupted cache recovery (100-byte threshold)
# ---------------------------------------------------------------------------


class TestGetContentCorrupted:
    def test_tiny_cache_file_is_redownloaded(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        url = "https://example.com/x"
        cache_path = tmp_path / f"civic_cache_{cache.session_id}_{_expected_key(url)}"
        cache_path.write_bytes(b"tiny")  # < 100 bytes

        fresh = b"fresh content " * 20
        resp = _mock_response(fresh)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            content, was_cached = cache.get_content(url)

        assert content == fresh
        assert was_cached is False
        assert mock_get.call_count == 1
        assert cache.cache_hits == 0
        assert cache.cache_misses == 1

    def test_corrupted_cache_file_is_overwritten_with_fresh(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        url = "https://example.com/x"
        cache_path = tmp_path / f"civic_cache_{cache.session_id}_{_expected_key(url)}"
        cache_path.write_bytes(b"tiny")

        fresh = b"fresh content " * 20
        resp = _mock_response(fresh)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            cache.get_content(url)

        assert cache_path.exists()
        assert cache_path.read_bytes() == fresh

    def test_exactly_100_bytes_is_treated_as_corrupted(self, tmp_path):
        """Boundary: the check is `len > 100`, so 100 bytes fails validation."""
        cache = SessionContentCache(cache_dir=str(tmp_path))
        url = "https://example.com/x"
        cache_path = tmp_path / f"civic_cache_{cache.session_id}_{_expected_key(url)}"
        cache_path.write_bytes(b"x" * 100)

        fresh = b"y" * 500
        resp = _mock_response(fresh)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            content, was_cached = cache.get_content(url)

        assert content == fresh
        assert was_cached is False
        assert mock_get.call_count == 1

    def test_101_bytes_is_valid_cache_hit(self, tmp_path):
        """Boundary: 101 bytes > 100 → valid cache, no HTTP call."""
        cache = SessionContentCache(cache_dir=str(tmp_path))
        url = "https://example.com/x"
        cache_path = tmp_path / f"civic_cache_{cache.session_id}_{_expected_key(url)}"
        payload = b"y" * 101
        cache_path.write_bytes(payload)

        with patch.object(cc_mod.requests, "get") as mock_get:
            content, was_cached = cache.get_content(url)

        assert content == payload
        assert was_cached is True
        assert mock_get.call_count == 0
        assert cache.cache_hits == 1

    def test_empty_cache_file_is_treated_as_corrupted(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        url = "https://example.com/x"
        cache_path = tmp_path / f"civic_cache_{cache.session_id}_{_expected_key(url)}"
        cache_path.write_bytes(b"")

        fresh = b"z" * 500
        resp = _mock_response(fresh)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            content, was_cached = cache.get_content(url)

        assert was_cached is False
        assert content == fresh


# ---------------------------------------------------------------------------
# cleanup_session_cache
# ---------------------------------------------------------------------------


class TestCleanupSessionCache:
    def test_removes_only_this_sessions_files(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        mine1 = tmp_path / f"civic_cache_{cache.session_id}_abc"
        mine2 = tmp_path / f"civic_cache_{cache.session_id}_def"
        mine1.write_bytes(b"data1")
        mine2.write_bytes(b"data2")

        other = tmp_path / "civic_cache_19000101_000000_xyz"
        other.write_bytes(b"other session")
        unrelated = tmp_path / "random.txt"
        unrelated.write_bytes(b"keepme")

        cache.cleanup_session_cache()

        assert not mine1.exists()
        assert not mine2.exists()
        assert other.exists()
        assert other.read_bytes() == b"other session"
        assert unrelated.exists()
        assert unrelated.read_bytes() == b"keepme"

    def test_empty_cache_dir_does_not_raise(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        cache.cleanup_session_cache()
        assert list(tmp_path.iterdir()) == []

    def test_nonexistent_cache_dir_is_handled_gracefully(self, tmp_path):
        """os.listdir on missing dir raises FileNotFoundError — must be caught."""
        missing = tmp_path / "no_such_dir"
        cache = SessionContentCache(cache_dir=str(missing))
        cache.cleanup_session_cache()
        assert not missing.exists()

    def test_removes_all_session_files_in_order(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        for i in range(5):
            (tmp_path / f"civic_cache_{cache.session_id}_file{i}").write_bytes(
                b"x" * 100
            )

        cache.cleanup_session_cache()

        remaining = [f for f in os.listdir(tmp_path) if f.startswith("civic_cache_")]
        assert remaining == []


# ---------------------------------------------------------------------------
# get_cache_stats
# ---------------------------------------------------------------------------


class TestGetCacheStats:
    def test_fresh_cache_stats(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        stats = cache.get_cache_stats()
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["total_requests"] == 0
        assert stats["hit_rate_percent"] == 0
        assert stats["session_id"] == cache.session_id

    def test_three_hits_one_miss_is_seventyfive_percent(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        cache.cache_hits = 3
        cache.cache_misses = 1
        stats = cache.get_cache_stats()
        assert stats["cache_hits"] == 3
        assert stats["cache_misses"] == 1
        assert stats["total_requests"] == 4
        assert stats["hit_rate_percent"] == 75.0

    def test_hit_rate_rounded_to_one_decimal(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        cache.cache_hits = 1
        cache.cache_misses = 2
        stats = cache.get_cache_stats()
        # 1/3 * 100 = 33.3333... → rounded to 33.3
        assert stats["hit_rate_percent"] == 33.3

    def test_all_hits_is_hundred_percent(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        cache.cache_hits = 5
        cache.cache_misses = 0
        stats = cache.get_cache_stats()
        assert stats["hit_rate_percent"] == 100.0
        assert stats["total_requests"] == 5

    def test_all_misses_is_zero_percent(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        cache.cache_hits = 0
        cache.cache_misses = 3
        stats = cache.get_cache_stats()
        assert stats["hit_rate_percent"] == 0.0
        assert stats["total_requests"] == 3

    def test_zero_requests_avoids_division_error(self, tmp_path):
        """Guarded division by zero: empty cache returns 0, not raises."""
        cache = SessionContentCache(cache_dir=str(tmp_path))
        stats = cache.get_cache_stats()
        assert stats["hit_rate_percent"] == 0

    def test_stats_reflect_real_get_content_flow(self, tmp_path):
        """End-to-end: miss then hit, stats match the counter mutations."""
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"x" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            cache.get_content("https://example.com/x")
            cache.get_content("https://example.com/x")
        stats = cache.get_cache_stats()
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert stats["total_requests"] == 2
        assert stats["hit_rate_percent"] == 50.0


# ---------------------------------------------------------------------------
# Context manager interface
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_returns_self(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        with cache as c:
            assert c is cache

    def test_exit_cleans_up_session_files(self, tmp_path):
        with SessionContentCache(cache_dir=str(tmp_path)) as cache:
            resp = _mock_response(b"x" * 200)
            with patch.object(cc_mod.requests, "get", return_value=resp):
                cache.get_content("https://example.com/x")
            inside = [
                f for f in os.listdir(tmp_path)
                if f.startswith(f"civic_cache_{cache.session_id}_")
            ]
            assert len(inside) == 1

        after = [
            f for f in os.listdir(tmp_path)
            if f.startswith(f"civic_cache_{cache.session_id}_")
        ]
        assert after == []

    def test_exit_preserves_other_session_files(self, tmp_path):
        other = tmp_path / "civic_cache_19000101_000000_xyz"
        other.write_bytes(b"other session data")
        with SessionContentCache(cache_dir=str(tmp_path)):
            pass
        assert other.exists()
        assert other.read_bytes() == b"other session data"

    def test_exit_suppresses_no_exception(self, tmp_path):
        """__exit__ must return None/False so exceptions still propagate."""
        with pytest.raises(ValueError, match="boom"):
            with SessionContentCache(cache_dir=str(tmp_path)):
                raise ValueError("boom")


# ---------------------------------------------------------------------------
# download_with_cache convenience wrapper
# ---------------------------------------------------------------------------


class TestDownloadWithCache:
    def test_uses_provided_cache_and_returns_bytes(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        payload = b"z" * 200
        resp = _mock_response(payload)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            content = download_with_cache("https://example.com/x", cache=cache)
        assert content == payload
        assert cache.cache_misses == 1

    def test_return_type_is_bytes_not_tuple(self, tmp_path):
        """Wrapper discards the was_cached flag — should be bare bytes."""
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"z" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            result = download_with_cache("https://example.com/x", cache=cache)
        assert isinstance(result, bytes)
        assert result == b"z" * 200

    def test_second_call_with_same_cache_is_served_from_cache(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        payload = b"z" * 200
        resp = _mock_response(payload)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            result1 = download_with_cache("https://example.com/x", cache=cache)
            result2 = download_with_cache("https://example.com/x", cache=cache)
        assert result1 == payload
        assert result2 == payload
        assert mock_get.call_count == 1
        assert cache.cache_hits == 1

    def test_creates_new_cache_when_none_provided(self, tmp_path, monkeypatch):
        """When cache=None, a fresh SessionContentCache is instantiated."""
        fake_tempfile = SimpleNamespace(gettempdir=lambda: str(tmp_path))
        monkeypatch.setattr(cc_mod, "tempfile", fake_tempfile)

        payload = b"z" * 200
        resp = _mock_response(payload)
        with patch.object(cc_mod.requests, "get", return_value=resp):
            content = download_with_cache("https://example.com/x")

        assert content == payload
        # A cache file should have been written in our redirected temp dir
        files = [f for f in os.listdir(tmp_path) if f.startswith("civic_cache_")]
        assert len(files) == 1

    def test_forwards_headers_to_http_layer(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        resp = _mock_response(b"z" * 200)
        with patch.object(cc_mod.requests, "get", return_value=resp) as mock_get:
            download_with_cache(
                "https://example.com/x",
                headers={"X-Token": "abc"},
                cache=cache,
            )
        assert mock_get.call_args[1]["headers"]["X-Token"] == "abc"

    def test_download_error_propagates_from_wrapper(self, tmp_path):
        cache = SessionContentCache(cache_dir=str(tmp_path))
        with patch.object(
            cc_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            with pytest.raises(requests.ConnectionError):
                download_with_cache("https://example.com/x", cache=cache)
