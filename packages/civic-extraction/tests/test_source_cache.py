"""
Tests for SourceCache.

Tests the caching layer for raw scraped content in blob storage.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from civic_extraction.cache import SourceCache, CachedSession, CachedResponse


class TestSourceCache:
    """Tests for SourceCache class."""

    def test_cache_key_generates_hash(self):
        """Cache key should be deterministic hash of URL."""
        mock_storage = MagicMock()
        cache = SourceCache(mock_storage)

        url = "https://example.com/page.html"
        key = cache.cache_key(url)

        # Should follow format: source-cache/{hash}
        assert key.startswith("source-cache/")
        assert len(key) == len("source-cache/") + 16  # 16 char hash

        # Same URL should produce same key
        assert cache.cache_key(url) == key

        # Different URL should produce different key
        assert cache.cache_key("https://other.com/page.html") != key

    def test_get_returns_none_when_not_cached(self):
        """get() should return None for uncached URLs."""
        mock_storage = MagicMock()
        mock_storage.exists.return_value = False

        cache = SourceCache(mock_storage)
        result = cache.get("https://example.com/page.html")

        assert result is None
        assert cache._misses == 1
        assert cache._hits == 0

    def test_get_returns_content_when_cached_and_not_expired(self):
        """get() should return content for valid cached entries."""
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.download.return_value = b"cached content"

        # Mock metadata with future expiration
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_storage._metadata = {
            "source-cache/1234567890123456": {
                "expires_at": future.isoformat()
            }
        }

        cache = SourceCache(mock_storage)
        result = cache.get("https://example.com/page.html")

        assert result == b"cached content"
        assert cache._hits == 1
        assert cache._misses == 0

    def test_get_returns_none_when_expired(self):
        """get() should return None and delete expired entries."""
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True

        # Create cache first to get actual cache key for the URL
        cache = SourceCache(mock_storage)
        url = "https://example.com/page.html"
        actual_key = cache.cache_key(url)

        # Mock metadata with past expiration using actual cache key
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_storage._metadata = {
            actual_key: {
                "expires_at": past.isoformat()
            }
        }
        # Remove s3 attribute to force local backend path
        del mock_storage.s3

        result = cache.get(url)

        assert result is None
        assert cache._misses == 1
        # Should have tried to delete expired entry
        mock_storage.delete.assert_called_once()

    def test_put_stores_content_with_metadata(self):
        """put() should store content with TTL metadata."""
        mock_storage = MagicMock()
        cache = SourceCache(mock_storage)

        url = "https://example.com/page.html"
        content = b"<html>test</html>"

        key = cache.put(url, content, ttl_hours=24, content_type="text/html")

        # Should have called upload with correct parameters
        mock_storage.upload.assert_called_once()
        call_args = mock_storage.upload.call_args

        assert call_args.kwargs["key"] == key
        assert call_args.kwargs["data"] == content
        assert call_args.kwargs["content_type"] == "text/html"

        # Metadata should include url, cached_at, expires_at
        metadata = call_args.kwargs["metadata"]
        assert metadata["url"] == url
        assert "cached_at" in metadata
        assert "expires_at" in metadata

    def test_invalidate_deletes_cached_entry(self):
        """invalidate() should delete cached entry."""
        mock_storage = MagicMock()
        mock_storage.delete.return_value = True

        cache = SourceCache(mock_storage)
        result = cache.invalidate("https://example.com/page.html")

        assert result is True
        mock_storage.delete.assert_called_once()

    def test_clear_removes_all_cached_entries(self):
        """clear() should remove all entries with source-cache prefix."""
        mock_storage = MagicMock()
        mock_storage.list_keys.return_value = [
            "source-cache/abc123",
            "source-cache/def456",
            "source-cache/ghi789",
        ]
        mock_storage.delete.return_value = True

        cache = SourceCache(mock_storage)
        count = cache.clear()

        assert count == 3
        assert mock_storage.delete.call_count == 3

    def test_stats_returns_hit_rate_and_counts(self):
        """stats() should return cache statistics."""
        mock_storage = MagicMock()
        mock_storage.list_keys.return_value = ["source-cache/abc123"]
        mock_storage.exists.return_value = False

        cache = SourceCache(mock_storage)

        # Generate some hits and misses
        cache._hits = 7
        cache._misses = 3

        stats = cache.stats()

        assert stats["hits"] == 7
        assert stats["misses"] == 3
        assert stats["hit_rate"] == 70.0
        assert stats["entry_count"] == 1

    def test_stats_handles_zero_requests(self):
        """stats() should handle zero total requests."""
        mock_storage = MagicMock()
        mock_storage.list_keys.return_value = []

        cache = SourceCache(mock_storage)
        stats = cache.stats()

        assert stats["hit_rate"] == 0.0


class TestCachedResponse:
    """Tests for CachedResponse dataclass."""

    def test_text_property_decodes_utf8(self):
        """text property should decode content as UTF-8."""
        response = CachedResponse(
            content=b"Hello, World!",
            status_code=200,
            from_cache=True,
            url="https://example.com",
        )

        assert response.text == "Hello, World!"

    def test_text_property_handles_invalid_utf8(self):
        """text property should handle invalid UTF-8 gracefully."""
        response = CachedResponse(
            content=b"\xff\xfe invalid",
            status_code=200,
            from_cache=True,
            url="https://example.com",
        )

        # Should not raise, uses errors='replace'
        text = response.text
        assert isinstance(text, str)


class TestCachedSession:
    """Tests for CachedSession class."""

    def test_get_returns_cached_content_on_hit(self):
        """get() should return cached content without making HTTP request."""
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.download.return_value = b"cached content"
        mock_storage._metadata = {
            "source-cache/1234567890123456": {
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            }
        }

        cache = SourceCache(mock_storage)
        session = CachedSession(cache, ttl_hours=24)

        response = session.get("https://example.com/page.html")

        assert response is not None
        assert response.content == b"cached content"
        assert response.from_cache is True
        assert response.status_code == 200

    @patch("requests.Session.get")
    def test_get_fetches_and_caches_on_miss(self, mock_requests_get):
        """get() should fetch from source and cache on miss."""
        mock_storage = MagicMock()
        mock_storage.exists.return_value = False

        # Mock HTTP response
        mock_http_response = MagicMock()
        mock_http_response.content = b"fresh content"
        mock_http_response.status_code = 200
        mock_http_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_requests_get.return_value = mock_http_response

        cache = SourceCache(mock_storage)
        session = CachedSession(cache, ttl_hours=24)
        session._min_interval = 0  # Disable rate limiting for test

        response = session.get("https://example.com/page.html")

        assert response is not None
        assert response.content == b"fresh content"
        assert response.from_cache is False

        # Should have cached the response
        mock_storage.upload.assert_called_once()

    @patch("requests.Session.get")
    def test_get_bypasses_cache_on_force_refresh(self, mock_requests_get):
        """get() with force_refresh should bypass cache."""
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.download.return_value = b"cached content"
        mock_storage._metadata = {
            "source-cache/1234567890123456": {
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            }
        }

        # Mock HTTP response
        mock_http_response = MagicMock()
        mock_http_response.content = b"fresh content"
        mock_http_response.status_code = 200
        mock_http_response.headers = {"Content-Type": "text/html"}
        mock_requests_get.return_value = mock_http_response

        cache = SourceCache(mock_storage)
        session = CachedSession(cache, ttl_hours=24)
        session._min_interval = 0  # Disable rate limiting

        response = session.get("https://example.com/page.html", force_refresh=True)

        assert response is not None
        assert response.content == b"fresh content"
        assert response.from_cache is False


class TestSourceCacheWithR2Backend:
    """Integration-style tests for SourceCache with R2-like backend."""

    def test_get_metadata_for_r2_backend(self):
        """_get_metadata should use S3 head_object for R2 backend."""
        mock_storage = MagicMock()
        mock_storage.s3 = MagicMock()
        mock_storage.bucket_name = "test-bucket"
        mock_storage.s3.head_object.return_value = {
            "Metadata": {
                "url": "https://example.com",
                "expires_at": "2025-01-01T00:00:00+00:00",
            }
        }

        cache = SourceCache(mock_storage)
        metadata = cache._get_metadata("source-cache/test")

        mock_storage.s3.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="source-cache/test"
        )
        assert metadata["url"] == "https://example.com"

    def test_get_metadata_for_local_backend(self):
        """_get_metadata should use internal dict for local backend."""
        mock_storage = MagicMock()
        mock_storage._metadata = {
            "source-cache/test": {
                "url": "https://example.com",
                "expires_at": "2025-01-01T00:00:00+00:00",
            }
        }
        # Remove s3 attribute to simulate local backend
        del mock_storage.s3

        cache = SourceCache(mock_storage)
        metadata = cache._get_metadata("source-cache/test")

        assert metadata["url"] == "https://example.com"


class TestProudCityClientCacheIntegration:
    """Tests for ProudCityClient cache integration."""

    def test_proudcity_client_accepts_cache_parameter(self):
        """ProudCityClient should accept optional cache parameter."""
        from civic_extraction.clients.proudcity import ProudCityClient

        mock_cache = MagicMock()
        client = ProudCityClient(
            base_url="https://example.com",
            jurisdiction_id="test",
            cache=mock_cache,
        )

        assert client.cache is mock_cache

    def test_proudcity_source_passes_cache_to_client(self):
        """ProudCitySource should pass cache to underlying client."""
        from civic_extraction.clients.proudcity import ProudCitySource
        from civic_extraction.clients.base import ExtractionConfig

        mock_cache = MagicMock()
        config = ExtractionConfig(
            jurisdiction_id="test",
            source_id="proudcity-test",
            source_type="proudcity",
            base_url="https://example.com",
            archives={"test": "/test/"},
        )

        source = ProudCitySource(config, cache=mock_cache)

        assert source.cache is mock_cache
        assert source.client.cache is mock_cache

    def test_cache_stats_returns_none_without_cache(self):
        """cache_stats() should return None when no cache configured."""
        from civic_extraction.clients.proudcity import ProudCitySource
        from civic_extraction.clients.base import ExtractionConfig

        config = ExtractionConfig(
            jurisdiction_id="test",
            source_id="proudcity-test",
            source_type="proudcity",
            base_url="https://example.com",
            archives={"test": "/test/"},
        )

        source = ProudCitySource(config)

        assert source.cache_stats() is None

    def test_cache_stats_returns_stats_with_cache(self):
        """cache_stats() should return stats when cache configured."""
        from civic_extraction.clients.proudcity import ProudCitySource
        from civic_extraction.clients.base import ExtractionConfig

        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "hits": 10,
            "misses": 5,
            "hit_rate": 66.7,
            "entry_count": 3,
        }

        config = ExtractionConfig(
            jurisdiction_id="test",
            source_id="proudcity-test",
            source_type="proudcity",
            base_url="https://example.com",
            archives={"test": "/test/"},
        )

        source = ProudCitySource(config, cache=mock_cache)
        stats = source.cache_stats()

        assert stats["hits"] == 10
        assert stats["hit_rate"] == 66.7
