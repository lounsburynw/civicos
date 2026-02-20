"""
Database-backed API key management and usage logging.

Connects to the Platform DB (PLATFORM_DATABASE_URL) for key storage,
validation, and request-level usage tracking.

Key format: cvk_live_ + 32 random hex chars (stored as SHA-256 hash).
"""

import hashlib
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

# Tier configuration: rate limits and display names
TIER_CONFIG = {
    "free": {"rate_limit_per_minute": 60, "label": "Free"},
    "journalist": {"rate_limit_per_minute": 120, "label": "Journalist"},
    "organization": {"rate_limit_per_minute": 300, "label": "Organization"},
    "city": {"rate_limit_per_minute": 600, "label": "City"},
    "api": {"rate_limit_per_minute": 1000, "label": "API Access"},
}


@dataclass
class ApiKeyInfo:
    """Information about a validated API key."""

    key_id: str
    name: str
    email: str
    tier: str
    status: str
    rate_limit_per_minute: int
    jurisdictions: list = field(default_factory=list)
    stripe_customer_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.key_id


@dataclass
class UsageStats:
    """Aggregated usage statistics for a key."""

    key_id: str
    total_requests: int
    period_start: str
    period_end: str
    by_endpoint: dict = field(default_factory=dict)
    error_count: int = 0
    avg_response_ms: Optional[int] = None


def _hash_key(raw_key: str) -> str:
    """SHA-256 hash of a raw API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _generate_key() -> tuple[str, str]:
    """Generate a new API key. Returns (key_id, raw_key)."""
    random_part = secrets.token_hex(32)
    raw_key = f"cvk_live_{random_part}"
    key_id = f"cvk_{secrets.token_hex(8)}"
    return key_id, raw_key


class ApiKeyStore:
    """Database-backed API key storage and usage logging.

    Connects to the Platform DB via PLATFORM_DATABASE_URL.
    Falls back gracefully if the database is unavailable.
    """

    def __init__(self, database_url: Optional[str] = None):
        self._database_url = database_url or os.getenv("PLATFORM_DATABASE_URL")
        self._pool: Optional[psycopg2.pool.SimpleConnectionPool] = None

    def _get_pool(self) -> Optional[psycopg2.pool.SimpleConnectionPool]:
        """Lazy-initialize connection pool."""
        if self._pool is not None:
            return self._pool
        if not self._database_url:
            return None
        try:
            self._pool = psycopg2.pool.SimpleConnectionPool(
                1, 5, self._database_url
            )
            return self._pool
        except Exception as e:
            logger.warning("Platform DB connection failed: %s", e)
            return None

    def _get_conn(self):
        pool = self._get_pool()
        if pool is None:
            return None
        try:
            return pool.getconn()
        except Exception as e:
            logger.warning("Platform DB getconn failed: %s", e)
            return None

    def _put_conn(self, conn):
        pool = self._get_pool()
        if pool and conn:
            try:
                pool.putconn(conn)
            except Exception:
                pass

    @property
    def available(self) -> bool:
        """Check if the Platform DB is configured and reachable."""
        return self._get_pool() is not None

    def validate_key(self, raw_key: str) -> Optional[ApiKeyInfo]:
        """Look up a key by its raw value, checking status and expiration.

        Returns ApiKeyInfo if valid, None if not found or invalid.
        """
        conn = self._get_conn()
        if conn is None:
            return None
        try:
            key_hash = _hash_key(raw_key)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT key_id, name, email, tier, status,
                           rate_limit_per_minute, jurisdictions,
                           stripe_customer_id, metadata, expires_at
                    FROM platform_api_keys
                    WHERE key_hash = %s
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                key_id, name, email, tier, status, rate_limit, jurisdictions, \
                    stripe_cust, metadata, expires_at = row

                # Check status
                if status != "active":
                    return None

                # Check expiration
                if expires_at and expires_at < datetime.now(timezone.utc):
                    return None

                return ApiKeyInfo(
                    key_id=key_id,
                    name=name,
                    email=email,
                    tier=tier,
                    status=status,
                    rate_limit_per_minute=rate_limit,
                    jurisdictions=jurisdictions or [],
                    stripe_customer_id=stripe_cust,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.error("validate_key error: %s", e)
            return None
        finally:
            self._put_conn(conn)

    def create_key(
        self,
        name: str,
        email: str,
        tier: str = "free",
        jurisdictions: Optional[List[str]] = None,
        stripe_customer_id: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[tuple[str, str]]:
        """Create a new API key. Returns (key_id, raw_key) or None on failure.

        The raw_key is shown once at creation and never stored.
        """
        conn = self._get_conn()
        if conn is None:
            return None
        try:
            key_id, raw_key = _generate_key()
            key_hash = _hash_key(raw_key)
            rate_limit = TIER_CONFIG.get(tier, TIER_CONFIG["free"])["rate_limit_per_minute"]

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO platform_api_keys
                        (key_id, key_hash, name, email, tier, stripe_customer_id,
                         stripe_subscription_id, jurisdictions, rate_limit_per_minute,
                         expires_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        key_id, key_hash, name, email, tier,
                        stripe_customer_id, stripe_subscription_id,
                        psycopg2.extras.Json(jurisdictions or []),
                        rate_limit, expires_at,
                        psycopg2.extras.Json(metadata or {}),
                    ),
                )
            conn.commit()
            logger.info("Created API key %s for %s (tier=%s)", key_id, email, tier)
            return key_id, raw_key
        except Exception as e:
            logger.error("create_key error: %s", e)
            conn.rollback()
            return None
        finally:
            self._put_conn(conn)

    def update_last_used(self, key_id: str) -> None:
        """Update last_used_at timestamp for a key (fire-and-forget)."""
        conn = self._get_conn()
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE platform_api_keys SET last_used_at = NOW() WHERE key_id = %s",
                    (key_id,),
                )
            conn.commit()
        except Exception as e:
            logger.debug("update_last_used error: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            self._put_conn(conn)

    def log_usage(
        self,
        key_id: Optional[str],
        endpoint: str,
        method: str = "GET",
        status_code: Optional[int] = None,
        response_time_ms: Optional[int] = None,
        jurisdiction: Optional[str] = None,
    ) -> None:
        """Log a single API request. Fire-and-forget, never raises."""
        conn = self._get_conn()
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO platform_usage_logs
                        (key_id, endpoint, method, status_code, response_time_ms, jurisdiction)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (key_id, endpoint, method, status_code, response_time_ms, jurisdiction),
                )
            conn.commit()
        except Exception as e:
            logger.debug("log_usage error: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            self._put_conn(conn)

    def get_usage_stats(
        self, key_id: str, since: Optional[str] = None
    ) -> Optional[UsageStats]:
        """Get aggregated usage stats for a key.

        Args:
            key_id: The API key ID.
            since: ISO date string (e.g. "2026-01-01"). Defaults to last 30 days.
        """
        conn = self._get_conn()
        if conn is None:
            return None
        try:
            if since is None:
                since_clause = "NOW() - INTERVAL '30 days'"
            else:
                since_clause = f"'{since}'::timestamptz"

            with conn.cursor() as cur:
                # Total requests and error count
                cur.execute(
                    f"""
                    SELECT COUNT(*),
                           COUNT(*) FILTER (WHERE status_code >= 400),
                           AVG(response_time_ms)::int
                    FROM platform_usage_logs
                    WHERE key_id = %s AND timestamp >= {since_clause}
                    """,
                    (key_id,),
                )
                total, errors, avg_ms = cur.fetchone()

                # By endpoint
                cur.execute(
                    f"""
                    SELECT endpoint, COUNT(*)
                    FROM platform_usage_logs
                    WHERE key_id = %s AND timestamp >= {since_clause}
                    GROUP BY endpoint ORDER BY COUNT(*) DESC LIMIT 20
                    """,
                    (key_id,),
                )
                by_endpoint = {row[0]: row[1] for row in cur.fetchall()}

                now = datetime.now(timezone.utc).isoformat()
                return UsageStats(
                    key_id=key_id,
                    total_requests=total or 0,
                    period_start=since or "last_30_days",
                    period_end=now,
                    by_endpoint=by_endpoint,
                    error_count=errors or 0,
                    avg_response_ms=avg_ms,
                )
        except Exception as e:
            logger.error("get_usage_stats error: %s", e)
            return None
        finally:
            self._put_conn(conn)

    def list_keys(self) -> list[dict]:
        """List all API keys with basic info (for admin dashboard)."""
        conn = self._get_conn()
        if conn is None:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT key_id, name, email, tier, status,
                           rate_limit_per_minute, created_at, last_used_at,
                           stripe_customer_id, jurisdictions
                    FROM platform_api_keys
                    ORDER BY created_at DESC
                    """
                )
                rows = cur.fetchall()
                return [
                    {
                        "key_id": r[0],
                        "name": r[1],
                        "email": r[2],
                        "tier": r[3],
                        "status": r[4],
                        "rate_limit_per_minute": r[5],
                        "created_at": r[6].isoformat() if r[6] else None,
                        "last_used_at": r[7].isoformat() if r[7] else None,
                        "stripe_customer_id": r[8],
                        "jurisdictions": r[9] or [],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("list_keys error: %s", e)
            return []
        finally:
            self._put_conn(conn)

    def suspend_key(self, key_id: str) -> bool:
        """Suspend an API key (reversible)."""
        return self._set_status(key_id, "suspended")

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key (permanent)."""
        return self._set_status(key_id, "revoked")

    def _set_status(self, key_id: str, status: str) -> bool:
        conn = self._get_conn()
        if conn is None:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE platform_api_keys SET status = %s WHERE key_id = %s",
                    (status, key_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
            if updated:
                logger.info("Set key %s status to %s", key_id, status)
            return updated
        except Exception as e:
            logger.error("_set_status error: %s", e)
            conn.rollback()
            return False
        finally:
            self._put_conn(conn)

    def get_key_by_stripe_customer(self, customer_id: str) -> Optional[dict]:
        """Look up a key by Stripe customer ID."""
        conn = self._get_conn()
        if conn is None:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT key_id, name, email, tier, status
                    FROM platform_api_keys
                    WHERE stripe_customer_id = %s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (customer_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "key_id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "tier": row[3],
                    "status": row[4],
                }
        except Exception as e:
            logger.error("get_key_by_stripe_customer error: %s", e)
            return None
        finally:
            self._put_conn(conn)

    def update_key_stripe(
        self,
        key_id: str,
        stripe_customer_id: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> bool:
        """Update Stripe-related fields on a key."""
        conn = self._get_conn()
        if conn is None:
            return False
        try:
            sets = []
            params = []
            if stripe_customer_id is not None:
                sets.append("stripe_customer_id = %s")
                params.append(stripe_customer_id)
            if stripe_subscription_id is not None:
                sets.append("stripe_subscription_id = %s")
                params.append(stripe_subscription_id)
            if tier is not None:
                sets.append("tier = %s")
                params.append(tier)
                rate_limit = TIER_CONFIG.get(tier, TIER_CONFIG["free"])["rate_limit_per_minute"]
                sets.append("rate_limit_per_minute = %s")
                params.append(rate_limit)
            if not sets:
                return False
            params.append(key_id)
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE platform_api_keys SET {', '.join(sets)} WHERE key_id = %s",
                    params,
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception as e:
            logger.error("update_key_stripe error: %s", e)
            conn.rollback()
            return False
        finally:
            self._put_conn(conn)

    def get_all_usage_summary(self, since: Optional[str] = None) -> list[dict]:
        """Get usage summary grouped by key (for admin dashboard)."""
        conn = self._get_conn()
        if conn is None:
            return []
        try:
            if since is None:
                since_clause = "NOW() - INTERVAL '30 days'"
            else:
                since_clause = f"'{since}'::timestamptz"

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT l.key_id, k.name, k.tier,
                           COUNT(*) as request_count,
                           COUNT(*) FILTER (WHERE l.status_code >= 400) as error_count,
                           AVG(l.response_time_ms)::int as avg_ms
                    FROM platform_usage_logs l
                    LEFT JOIN platform_api_keys k ON l.key_id = k.key_id
                    WHERE l.timestamp >= {since_clause}
                    GROUP BY l.key_id, k.name, k.tier
                    ORDER BY request_count DESC
                    """
                )
                return [
                    {
                        "key_id": r[0],
                        "name": r[1],
                        "tier": r[2],
                        "request_count": r[3],
                        "error_count": r[4],
                        "avg_response_ms": r[5],
                    }
                    for r in cur.fetchall()
                ]
        except Exception as e:
            logger.error("get_all_usage_summary error: %s", e)
            return []
        finally:
            self._put_conn(conn)


# Module-level singleton (lazy-initialized)
_store: Optional[ApiKeyStore] = None


def get_api_key_store() -> ApiKeyStore:
    """Get the module-level ApiKeyStore singleton."""
    global _store
    if _store is None:
        _store = ApiKeyStore()
    return _store
