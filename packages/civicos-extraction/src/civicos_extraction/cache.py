"""
Source caching for raw scraped content.

Caches HTML pages, PDFs, and API responses in blob storage to reduce
repeat requests during development and pipeline reruns.

Usage:
    from civicos.storage import get_blob_storage
    from civicos_extraction.cache import SourceCache

    blob = get_blob_storage()  # Returns R2Backend if BLOB_STORAGE_URL set
    cache = SourceCache(blob)

    # Check cache first
    content = cache.get("https://example.com/page.html")
    if content is None:
        # Fetch and cache
        response = requests.get("https://example.com/page.html")
        cache.put("https://example.com/page.html", response.content, ttl_hours=24)
        content = response.content
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from civicos.storage import BlobStorage

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cached content with metadata."""

    content: bytes
    url: str
    cached_at: datetime
    expires_at: datetime
    content_type: Optional[str] = None


class SourceCache:
    """
    Cache raw scraped content in blob storage.

    Stores HTML pages, PDFs, and API responses with TTL-based expiration.
    Uses URL hash as the cache key to avoid path length issues.

    Key format: source-cache/{url_hash[:16]}

    Metadata stored with each cached object:
    - url: Original URL
    - cached_at: ISO timestamp when cached
    - expires_at: ISO timestamp when cache expires
    - content_type: MIME type (if known)
    """

    PREFIX = "source-cache"

    def __init__(self, blob_storage: "BlobStorage"):
        """
        Initialize source cache.

        Args:
            blob_storage: BlobStorage backend (LocalBlobBackend, R2Backend)
        """
        self.storage = blob_storage
        self._hits = 0
        self._misses = 0

    def cache_key(self, url: str) -> str:
        """
        Generate cache key from URL.

        Uses SHA256 hash truncated to 16 chars for compactness
        while maintaining uniqueness for practical purposes.

        Args:
            url: Source URL

        Returns:
            Cache key in format: source-cache/{hash}
        """
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        return f"{self.PREFIX}/{url_hash}"

    def get(self, url: str) -> Optional[bytes]:
        """
        Get cached content for URL if not expired.

        Args:
            url: Source URL

        Returns:
            Cached content bytes, or None if not cached or expired
        """
        key = self.cache_key(url)

        if not self.storage.exists(key):
            self._misses += 1
            logger.debug(f"Cache miss (not found): {url[:80]}")
            return None

        # Get metadata to check expiration
        try:
            metadata = self._get_metadata(key)
        except Exception as e:
            logger.warning(f"Failed to get cache metadata for {key}: {e}")
            self._misses += 1
            return None

        # Check expiration
        expires_at_str = metadata.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if now > expires_at:
                    logger.debug(f"Cache miss (expired): {url[:80]}")
                    self._misses += 1
                    # Optionally delete expired entry
                    self.storage.delete(key)
                    return None
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid expires_at metadata: {expires_at_str}: {e}")

        # Cache hit - download content
        try:
            content = self.storage.download(key)
            self._hits += 1
            logger.debug(f"Cache hit: {url[:80]}")
            return content
        except KeyError:
            self._misses += 1
            return None
        except Exception as e:
            logger.warning(f"Failed to download cached content for {key}: {e}")
            self._misses += 1
            return None

    def put(
        self,
        url: str,
        content: bytes,
        ttl_hours: int = 24,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Cache content for URL with TTL.

        Args:
            url: Source URL
            content: Content bytes to cache
            ttl_hours: Time-to-live in hours (default 24)
            content_type: MIME type (e.g., "text/html", "application/pdf")

        Returns:
            Cache key where content was stored
        """
        key = self.cache_key(url)

        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(
            now.timestamp() + (ttl_hours * 3600), tz=timezone.utc
        )

        metadata = {
            "url": url,
            "cached_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        if content_type:
            metadata["content_type"] = content_type

        self.storage.upload(
            key=key,
            data=content,
            content_type=content_type,
            metadata=metadata,
        )

        logger.debug(
            f"Cached: {url[:80]} -> {key} (expires in {ttl_hours}h)"
        )
        return key

    def invalidate(self, url: str) -> bool:
        """
        Remove cached content for URL.

        Args:
            url: Source URL

        Returns:
            True if deleted, False if not found
        """
        key = self.cache_key(url)
        deleted = self.storage.delete(key)
        if deleted:
            logger.debug(f"Invalidated cache: {url[:80]}")
        return deleted

    def clear(self) -> int:
        """
        Clear all cached content.

        Returns:
            Number of entries deleted
        """
        keys = self.storage.list_keys(prefix=self.PREFIX)
        count = 0
        for key in keys:
            if self.storage.delete(key):
                count += 1
        logger.info(f"Cleared {count} cache entries")
        return count

    def stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate, and entry_count
        """
        keys = self.storage.list_keys(prefix=self.PREFIX)
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 1),
            "entry_count": len(keys),
        }

    def _get_metadata(self, key: str) -> dict:
        """
        Get metadata for a cached object.

        Implementation varies by backend:
        - R2Backend: Use S3 head_object
        - LocalBlobBackend: Use internal _metadata dict

        Args:
            key: Cache key

        Returns:
            Metadata dict
        """
        # For R2Backend, use head_object
        if hasattr(self.storage, "s3") and hasattr(self.storage, "bucket_name"):
            response = self.storage.s3.head_object(
                Bucket=self.storage.bucket_name, Key=key
            )
            return response.get("Metadata", {})

        # For LocalBlobBackend, check internal metadata dict
        if hasattr(self.storage, "_metadata"):
            return self.storage._metadata.get(key, {})

        return {}


class CachedSession:
    """
    Requests-like session with automatic caching.

    Drop-in replacement for requests.Session that checks cache before
    making HTTP requests and caches successful responses.

    Usage:
        cache = SourceCache(blob_storage)
        session = CachedSession(cache, ttl_hours=24)

        # First request: fetches and caches
        response = session.get("https://example.com/page.html")

        # Second request: returns cached content
        response = session.get("https://example.com/page.html")
    """

    def __init__(
        self,
        cache: SourceCache,
        ttl_hours: int = 24,
        user_agent: str = "Civic-Engagement-Platform/1.0 (Foundation-funded civic transparency tool)",
    ):
        """
        Initialize cached session.

        Args:
            cache: SourceCache instance
            ttl_hours: Default TTL for cached responses
            user_agent: User-Agent header for HTTP requests
        """
        import requests

        self.cache = cache
        self.ttl_hours = ttl_hours

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._last_request_time = 0.0
        self._min_interval = 1.0  # Rate limiting

    def get(
        self,
        url: str,
        ttl_hours: Optional[int] = None,
        timeout: int = 30,
        force_refresh: bool = False,
    ) -> Optional["CachedResponse"]:
        """
        GET request with caching.

        Args:
            url: URL to fetch
            ttl_hours: TTL override (uses session default if not specified)
            timeout: Request timeout in seconds
            force_refresh: If True, bypass cache and fetch fresh

        Returns:
            CachedResponse with content and metadata, or None if request failed
        """
        ttl = ttl_hours if ttl_hours is not None else self.ttl_hours

        # Check cache first (unless force refresh)
        if not force_refresh:
            cached = self.cache.get(url)
            if cached is not None:
                return CachedResponse(
                    content=cached,
                    status_code=200,
                    from_cache=True,
                    url=url,
                )

        # Rate limiting
        self._throttle()

        # Fetch from source
        try:
            response = self._session.get(url, timeout=timeout)
            response.raise_for_status()

            # Cache successful response
            content_type = response.headers.get("Content-Type", "").split(";")[0]
            self.cache.put(
                url=url,
                content=response.content,
                ttl_hours=ttl,
                content_type=content_type or None,
            )

            return CachedResponse(
                content=response.content,
                status_code=response.status_code,
                from_cache=False,
                url=url,
            )
        except Exception as e:
            logger.warning(f"Request failed for {url}: {e}")
            return None

    def _throttle(self):
        """Rate limiting between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()


@dataclass
class CachedResponse:
    """Response object for cached or fresh requests."""

    content: bytes
    status_code: int
    from_cache: bool
    url: str

    @property
    def text(self) -> str:
        """Decode content as UTF-8 text."""
        return self.content.decode("utf-8", errors="replace")
