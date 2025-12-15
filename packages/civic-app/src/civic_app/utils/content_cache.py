#!/usr/bin/env python3
"""
Session Content Cache - Simple caching for civic content downloads

Implements session-level caching to avoid repeated downloads during development
and testing. Caches content in /tmp/ for the duration of the parsing session.
"""

import os
import hashlib
import tempfile
import requests
from typing import Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SessionContentCache:
    """
    Session-level content cache for PDFs and HTML

    Caches downloaded content in temporary files for the duration of the session.
    Provides network failure resilience and faster iteration during development.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize session cache

        Args:
            cache_dir: Directory for cache files (default: system temp)
        """
        self.cache_dir = cache_dir or tempfile.gettempdir()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.cache_hits = 0
        self.cache_misses = 0

    def get_content(self, url: str, headers: Optional[dict] = None) -> Tuple[bytes, bool]:
        """
        Get content from cache or download if not cached

        Args:
            url: URL to fetch content from
            headers: Optional HTTP headers for request

        Returns:
            Tuple of (content_bytes, was_cached)
        """
        # Generate cache key from URL
        cache_key = self._generate_cache_key(url)
        cache_path = os.path.join(self.cache_dir, f"civic_cache_{self.session_id}_{cache_key}")

        # Check if cached version exists
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    content = f.read()

                # Verify content is valid (not empty or corrupted)
                if len(content) > 100:  # Minimum reasonable size
                    self.cache_hits += 1
                    logger.info(f"📁 Cache hit for {url} ({len(content):,} bytes)")
                    return content, True
                else:
                    # Remove corrupted cache file
                    os.remove(cache_path)
                    logger.warning(f"🗑️ Removed corrupted cache file for {url}")
            except Exception as e:
                logger.warning(f"⚠️ Cache read failed for {url}: {e}")
                # Continue to download fresh content

        # Download content
        try:
            content = self._download_content(url, headers)

            # Cache the downloaded content
            self._save_to_cache(cache_path, content)

            self.cache_misses += 1
            logger.info(f"⬇️ Downloaded and cached {url} ({len(content):,} bytes)")
            return content, False

        except Exception as e:
            logger.error(f"❌ Download failed for {url}: {e}")
            raise

    def _generate_cache_key(self, url: str) -> str:
        """Generate cache key from URL"""
        # Use hash of URL for filename safety
        return hashlib.md5(url.encode()).hexdigest()[:16]

    def _download_content(self, url: str, headers: Optional[dict] = None) -> bytes:
        """Download content from URL"""
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        if headers:
            default_headers.update(headers)

        response = requests.get(url, headers=default_headers, timeout=300)  # 5 minute timeout
        response.raise_for_status()

        return response.content

    def _save_to_cache(self, cache_path: str, content: bytes):
        """Save content to cache file"""
        try:
            with open(cache_path, 'wb') as f:
                f.write(content)
        except Exception as e:
            logger.warning(f"⚠️ Failed to save cache file {cache_path}: {e}")

    def cleanup_session_cache(self):
        """Clean up cache files from this session"""
        try:
            session_pattern = f"civic_cache_{self.session_id}_"
            cache_files = [f for f in os.listdir(self.cache_dir) if f.startswith(session_pattern)]

            total_size = 0
            for cache_file in cache_files:
                cache_path = os.path.join(self.cache_dir, cache_file)
                try:
                    file_size = os.path.getsize(cache_path)
                    total_size += file_size
                    os.remove(cache_path)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to remove cache file {cache_file}: {e}")

            if cache_files:
                logger.info(f"🗑️ Cleaned up {len(cache_files)} cache files ({total_size:,} bytes)")

        except Exception as e:
            logger.warning(f"⚠️ Cache cleanup failed: {e}")

    def get_cache_stats(self) -> dict:
        """Get cache performance statistics"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "session_id": self.session_id,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate_percent": round(hit_rate, 1),
            "total_requests": total_requests
        }

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup cache"""
        stats = self.get_cache_stats()
        logger.info(f"📊 Session cache stats: {stats['cache_hits']} hits, {stats['cache_misses']} misses, {stats['hit_rate_percent']}% hit rate")
        self.cleanup_session_cache()


# Convenience functions for common use cases
def download_with_cache(url: str, headers: Optional[dict] = None, cache: Optional[SessionContentCache] = None) -> bytes:
    """
    Download content with session caching

    Args:
        url: URL to download
        headers: Optional HTTP headers
        cache: Optional existing cache instance (creates new one if None)

    Returns:
        Content bytes
    """
    if cache is None:
        cache = SessionContentCache()

    content, was_cached = cache.get_content(url, headers)
    return content


def test_session_cache():
    """Test session caching functionality"""
    print("🧪 Testing Session Content Cache")
    print("=" * 40)

    # Test URLs (using smaller files for testing)
    test_urls = [
        "https://httpbin.org/bytes/1000",  # 1KB test file
        "https://httpbin.org/bytes/5000",  # 5KB test file
    ]

    with SessionContentCache() as cache:
        for url in test_urls:
            print(f"\n📄 Testing {url}")

            # First request (should miss cache)
            content1, was_cached1 = cache.get_content(url)
            print(f"   First request: {len(content1):,} bytes, cached: {was_cached1}")

            # Second request (should hit cache)
            content2, was_cached2 = cache.get_content(url)
            print(f"   Second request: {len(content2):,} bytes, cached: {was_cached2}")

            # Verify content is identical
            assert content1 == content2, "Cached content should match original"
            assert not was_cached1, "First request should not be cached"
            assert was_cached2, "Second request should be cached"

        # Print final stats
        stats = cache.get_cache_stats()
        print(f"\n📊 Final stats: {stats}")


if __name__ == "__main__":
    test_session_cache()