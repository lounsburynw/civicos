"""
Legislative Context Cache - Lazy-loading cache with TTL for legislative context.

Features:
- Zero startup time (loads on first request)
- Auto-refresh after TTL expiration (no restart needed)
- Manual invalidation for testing
- Memory efficient (only loads used contexts)
"""

import json
import time
import logging
import os
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class LegislativeContextCache:
    """
    Lazy-loading cache with TTL for legislative context.

    Features:
    - Zero startup time (loads on first request)
    - Auto-refresh after TTL expiration (no restart needed)
    - Manual invalidation for testing
    - Memory efficient (only loads used contexts)
    """

    def __init__(self, ttl_seconds: int = 3600, base_path: str = "data/legislative_context", federal_programs_path: str = "data/federal_programs"):
        self.cache: Dict[str, dict] = {}
        self.timestamps: Dict[str, float] = {}
        self.ttl = ttl_seconds
        self.base_path = Path(base_path)
        self.federal_programs_path = Path(federal_programs_path)

        logger.info(f"Legislative context cache initialized (TTL: {ttl_seconds}s)")

    def get(self, state: str, topic: str) -> Optional[dict]:
        """
        Get legislative context with automatic TTL-based refresh.

        Args:
            state: State identifier (e.g., "california")
            topic: Topic identifier (e.g., "housing")

        Returns:
            Legislative context dict or None if not available
        """
        key = f"{state}_{topic}"
        now = time.time()

        # Cache miss or expired - reload from disk
        if (key not in self.cache or
            now - self.timestamps.get(key, 0) > self.ttl):
            self._load(key)

        return self.cache.get(key)

    def _load(self, key: str) -> None:
        """Load legislative context from disk, merging state legislation and federal programs"""
        state_file_path = self.base_path / f"{key}.json"

        # Extract topic from key (e.g., "california_housing" -> "housing")
        topic = key.split('_', 1)[1] if '_' in key else None
        federal_file_path = self.federal_programs_path / f"{topic}.json" if topic else None

        # Check if either file exists
        if not state_file_path.exists() and not (federal_file_path and federal_file_path.exists()):
            logger.debug(f"No legislative context file for {key}")
            self.cache[key] = None
            return

        try:
            # Load state legislation
            state_data = None
            if state_file_path.exists():
                with open(state_file_path, 'r') as f:
                    state_data = json.load(f)

            # Load federal programs
            federal_data = None
            if federal_file_path and federal_file_path.exists():
                with open(federal_file_path, 'r') as f:
                    federal_data = json.load(f)

            # Merge the data
            merged_data = state_data or {}
            if federal_data:
                # Add federal programs to the merged data
                merged_data['federal_programs'] = federal_data.get('programs', {})

            self.cache[key] = merged_data
            self.timestamps[key] = time.time()

            size_kb = (state_file_path.stat().st_size if state_file_path.exists() else 0) + \
                      (federal_file_path.stat().st_size if federal_file_path and federal_file_path.exists() else 0)
            logger.info(f"Loaded legislative context: {key} ({size_kb} bytes, state+federal)")

        except Exception as e:
            logger.error(f"Failed to load legislative context {key}: {e}")
            self.cache[key] = None

    def invalidate(self, state: Optional[str] = None, topic: Optional[str] = None) -> None:
        """
        Manually invalidate cache (useful for testing/development).

        Args:
            state: Invalidate specific state (or all if None)
            topic: Invalidate specific topic (or all if None)
        """
        if state and topic:
            key = f"{state}_{topic}"
            self.cache.pop(key, None)
            self.timestamps.pop(key, None)
            logger.info(f"Invalidated cache: {key}")
        else:
            self.cache.clear()
            self.timestamps.clear()
            logger.info("Invalidated entire legislative context cache")

    def stats(self) -> dict:
        """Get cache statistics for monitoring"""
        return {
            "cached_contexts": len(self.cache),
            "total_size_kb": sum(
                len(json.dumps(v)) for v in self.cache.values() if v
            ) / 1024,
            "ttl_seconds": self.ttl
        }


# Global singleton instance
# TTL can be configured via environment variable (default: 1 hour)
legislative_cache = LegislativeContextCache(
    ttl_seconds=int(os.getenv('LEGISLATIVE_CACHE_TTL', '3600')),
    base_path=os.getenv('LEGISLATIVE_CONTEXT_PATH', 'data/legislative_context'),
    federal_programs_path=os.getenv('FEDERAL_PROGRAMS_PATH', 'data/federal_programs')
)
