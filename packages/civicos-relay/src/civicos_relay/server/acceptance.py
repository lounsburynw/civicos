"""Relay acceptance policy — tiered access control for write endpoints.

Tiers checked in order:
1. Attestation proof → unlimited (verifies kind-30850 Nostr event from trusted issuer)
2. Payment proof → unlimited (verifies Schnorr blind signature token + double-spend check)
3. Proof-of-work → bypass rate limit (NIP-13, active for voice/comment)
4. Rate limit → per-event-type daily limit
"""

import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Set

from civicos_relay.voice import blind as _blind

logger = logging.getLogger(__name__)

# Type for issuer registry lookup: (jurisdiction) -> list of verified issuer pubkeys
IssuerLookup = Callable[[str], list[str]]


@dataclass
class PolicyResult:
    """Result of an acceptance policy check."""
    accepted: bool
    tier: str  # "attested", "paid", "rate_limited", "rejected"
    reason: str

    def to_dict(self) -> dict:
        """Return 402-compatible response body with upgrade options."""
        result = {
            "accepted": self.accepted,
            "tier": self.tier,
            "reason": self.reason,
        }
        if not self.accepted:
            result["options"] = {
                "attestation": "Present a kind-30850 attestation proof for unlimited writes",
                "payment": "Include a payment proof for unlimited writes",
                "retry": "Wait until tomorrow when your rate limit resets",
            }
        return result


# Default per-event-type policy configuration
# max_per_day: rate limit for unauthenticated writes (None = no rate limit tier)
# pow_difficulty: NIP-13 proof-of-work difficulty (leading zero bits)
DEFAULT_POLICY = {
    "voice": {"max_per_day": 50, "pow_difficulty": 16},
    "comment": {"max_per_day": 20, "pow_difficulty": 16},
    "initiative": {"max_per_day": 5, "pow_difficulty": None},
    "action_create": {"max_per_day": 10, "pow_difficulty": None},
    "action_commit": {"max_per_day": 20, "pow_difficulty": None},
    "action_complete": {"max_per_day": 20, "pow_difficulty": None},
}

# Default attestation validity period: 1 year in seconds
DEFAULT_ATTESTATION_VALIDITY_SECONDS = 365 * 24 * 60 * 60  # 31536000

# Default path to relay policies config file (relative to project root)
_DEFAULT_POLICY_FILE = "config/relay_policies.json"


def load_policy(jurisdiction_id: Optional[str] = None) -> dict:
    """Load relay policy for a jurisdiction using resolution order:

    1. RELAY_POLICY_FILE env var (operator override)
    2. config/relay_policies.json[jurisdiction_id] (per-jurisdiction)
    3. config/relay_policies.json["default"] (file defaults)
    4. DEFAULT_POLICY constant (hardcoded fallback)

    Per-jurisdiction config merges with defaults — a jurisdiction can
    override just "voice.max_per_day" without specifying every event type.
    """
    policy_data = _load_policy_file()
    if policy_data is None:
        return deepcopy(DEFAULT_POLICY)

    # Start with hardcoded defaults
    merged = deepcopy(DEFAULT_POLICY)

    # Layer file defaults
    file_defaults = policy_data.get("default", {})
    _merge_policy(merged, file_defaults)

    # Layer jurisdiction-specific overrides
    if jurisdiction_id and jurisdiction_id in policy_data:
        _merge_policy(merged, policy_data[jurisdiction_id])

    return merged


def _load_policy_file() -> Optional[dict]:
    """Load policy JSON from RELAY_POLICY_FILE or default path."""
    # Check env var override first
    policy_path = os.environ.get("RELAY_POLICY_FILE")
    if policy_path:
        path = Path(policy_path)
        if path.is_file():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load RELAY_POLICY_FILE=%s: %s", policy_path, e)
                return None
        else:
            logger.warning("RELAY_POLICY_FILE=%s not found", policy_path)
            return None

    # Try default path (walk up from this file to find project root)
    # acceptance.py is at packages/civicos-relay/src/civicos_relay/server/acceptance.py
    # project root is 6 levels up
    pkg_dir = Path(__file__).resolve()
    for _ in range(8):
        pkg_dir = pkg_dir.parent
        candidate = pkg_dir / _DEFAULT_POLICY_FILE
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load %s: %s", candidate, e)
                return None

    return None


def _merge_policy(base: dict, overrides: dict) -> None:
    """Deep merge overrides into base policy. Mutates base in place.

    Each event type's config is merged independently, so overriding
    voice.max_per_day doesn't lose voice.pow_difficulty.
    """
    for event_type, event_config in overrides.items():
        if event_type in base and isinstance(base[event_type], dict) and isinstance(event_config, dict):
            base[event_type].update(event_config)
        else:
            base[event_type] = event_config


class InMemoryRateLimiter:
    """Dict-based rate limiter for tests and dev (no database required)."""

    def __init__(self):
        # {(pubkey_hash, event_type, day_str): count}
        self._counts: dict[tuple[str, str, str], int] = defaultdict(int)

    def check_and_increment(self, pubkey_hash: str, event_type: str, max_per_day: int) -> bool:
        """Check rate limit and increment counter. Returns True if under limit."""
        today = date.today().isoformat()
        key = (pubkey_hash, event_type, today)
        if self._counts[key] >= max_per_day:
            return False
        self._counts[key] += 1
        return True

    def cleanup_old(self, keep_days: int = 1):
        """Remove entries older than today (in-memory only keeps today)."""
        today = date.today().isoformat()
        self._counts = defaultdict(
            int,
            {k: v for k, v in self._counts.items() if k[2] == today}
        )


class AcceptancePolicy:
    """Acceptance policy enforcer for relay write endpoints.

    Checks writes against a tiered policy:
    1. Attestation proof → unlimited (verifies kind-30850 signed by trusted issuer)
    2. Payment proof → unlimited (verifies Schnorr blind signature + double-spend check)
    3. Proof-of-work → bypass rate limit (NIP-13 leading zero bits)
    4. Rate limit → per-event-type daily limit
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        connection_url: Optional[str] = None,
        issuer_lookup: Optional[IssuerLookup] = None,
        attestation_validity_seconds: int = DEFAULT_ATTESTATION_VALIDITY_SECONDS,
        jurisdiction_id: Optional[str] = None,
        spent_token_storage=None,
        known_token_issuers: Optional[Set[str]] = None,
    ):
        self._config = config or load_policy(jurisdiction_id)
        self._jurisdiction_id = jurisdiction_id
        self._connection_url = connection_url
        self._db_available = False
        self._issuer_lookup = issuer_lookup
        self._attestation_validity_seconds = attestation_validity_seconds
        self._revoked_attestations: set[str] = set()
        self._spent_token_storage = spent_token_storage
        self._known_token_issuers: set[str] = set(known_token_issuers) if known_token_issuers else set()

        if connection_url:
            try:
                import psycopg2
                self._conn_factory = lambda: psycopg2.connect(connection_url)
                self._db_available = True
                logger.info("AcceptancePolicy: using PostgreSQL rate limiting")
            except ImportError:
                logger.warning("psycopg2 not available, falling back to in-memory rate limiter")

        if not self._db_available:
            self._memory_limiter = InMemoryRateLimiter()
            logger.info("AcceptancePolicy: using in-memory rate limiting")

    def _hash_pubkey(self, public_key: str) -> str:
        """SHA-256 of public key, truncated to 16 hex chars."""
        return hashlib.sha256(public_key.encode()).hexdigest()[:16]

    def check(
        self,
        event_type: str,
        public_key: str,
        attestation_proof: Optional[dict] = None,
        payment_proof: Optional[dict] = None,
        event_id: Optional[str] = None,
    ) -> PolicyResult:
        """Check if a write should be accepted.

        Returns PolicyResult with accepted=True and the tier that granted access,
        or accepted=False with reason for rejection.
        """
        config = self._config.get(event_type)
        if config is None:
            # Unknown event type — reject
            return PolicyResult(accepted=False, tier="rejected", reason=f"Unknown event type: {event_type}")

        # Tier 1: Attestation proof (kind-30850 from trusted issuer)
        if attestation_proof is not None:
            if self._verify_attestation(attestation_proof, public_key):
                return PolicyResult(accepted=True, tier="attested", reason="Valid attestation proof")

        # Tier 2: Payment proof (Schnorr blind signature token)
        if payment_proof is not None:
            if self._verify_payment(payment_proof):
                return PolicyResult(accepted=True, tier="paid", reason="Valid payment proof")

        # Tier 3: Proof-of-work (bypasses rate limit if valid)
        pow_difficulty = config.get("pow_difficulty")
        if pow_difficulty is not None and event_id is not None:
            if self._verify_pow(event_id, pow_difficulty):
                return PolicyResult(accepted=True, tier="pow", reason=f"Valid proof-of-work ({pow_difficulty} bits)")

        # Tier 4: Rate limit
        max_per_day = config.get("max_per_day")
        if max_per_day is not None:
            pubkey_hash = self._hash_pubkey(public_key)
            if self._check_rate_limit(pubkey_hash, event_type, max_per_day):
                return PolicyResult(accepted=True, tier="rate_limited", reason=f"Under daily limit ({max_per_day}/day)")
            else:
                return PolicyResult(
                    accepted=False,
                    tier="rejected",
                    reason=f"Daily rate limit exceeded ({max_per_day}/day for {event_type})",
                )

        # No rate limit configured and no proof provided — reject
        return PolicyResult(
            accepted=False,
            tier="rejected",
            reason=f"Event type '{event_type}' requires attestation or payment proof",
        )

    def _verify_attestation(self, proof: dict, public_key: str) -> bool:
        """Verify kind-30850 attestation proof from a trusted jurisdiction issuer.

        Checks (in order):
        1. Revocation — reject if attestation event ID is in blocklist
        2. Expiry — reject if created_at + validity_period < now
        3. Jurisdiction lookup — find trusted issuers
        4. Crypto verification — try each issuer until one verifies
        """
        if self._issuer_lookup is None:
            return False

        try:
            # Check revocation blocklist
            attestation_id = proof.get("id")
            if attestation_id and attestation_id in self._revoked_attestations:
                logger.debug("Attestation %s is revoked", attestation_id)
                return False

            # Check expiry
            created_at = proof.get("created_at", 0)
            if created_at + self._attestation_validity_seconds < int(time.time()):
                logger.debug("Attestation expired: created_at=%d, validity=%d",
                             created_at, self._attestation_validity_seconds)
                return False

            # Extract jurisdiction from proof's j-tag
            tags = proof.get("tags", [])
            jurisdiction = next(
                (t[1] for t in tags if len(t) >= 2 and t[0] == "j"), None
            )
            if not jurisdiction:
                logger.debug("Attestation proof missing jurisdiction tag")
                return False

            # Look up all trusted issuers for this jurisdiction
            issuer_pubkeys = self._issuer_lookup(jurisdiction)
            if not issuer_pubkeys:
                logger.debug("No trusted issuers for jurisdiction: %s", jurisdiction)
                return False

            # Try each issuer — attestation is valid if any one matches
            from civicos_relay.voice.crypto import verify_attestation_proof
            for issuer_pubkey in issuer_pubkeys:
                if verify_attestation_proof(proof, public_key, jurisdiction, issuer_pubkey):
                    return True
            return False
        except Exception:
            logger.warning("Attestation verification failed", exc_info=True)
            return False

    def revoke_attestation(self, attestation_event_id: str, reason: str = ""):
        """Add an attestation event ID to the revocation blocklist."""
        self._revoked_attestations.add(attestation_event_id)
        logger.info("Revoked attestation %s: %s", attestation_event_id, reason or "no reason")
        if self._db_available:
            self._persist_revocation(attestation_event_id, reason)

    def is_attestation_revoked(self, attestation_event_id: str) -> bool:
        """Check if an attestation event ID has been revoked."""
        return attestation_event_id in self._revoked_attestations

    def load_revocations_from_db(self):
        """Load revocation blocklist from database into memory."""
        if not self._db_available:
            return
        try:
            conn = self._conn_factory()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT event_id FROM coordination_attestation_revocations")
                    for row in cur.fetchall():
                        self._revoked_attestations.add(row[0])
                    logger.info("Loaded %d attestation revocations from DB",
                                len(self._revoked_attestations))
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to load revocations from DB: %s", e)

    def _persist_revocation(self, attestation_event_id: str, reason: str):
        """Persist a revocation to the database."""
        try:
            conn = self._conn_factory()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO coordination_attestation_revocations (event_id, reason)
                        VALUES (%s, %s)
                        ON CONFLICT (event_id) DO NOTHING
                        """,
                        (attestation_event_id, reason),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to persist revocation: %s", e)

    def _verify_payment(self, proof: dict) -> bool:
        """Verify a Schnorr blind signature payment token.

        Checks (in order):
        1. Storage — reject if no spent_token_storage configured (graceful fallback)
        2. Parse — reject if proof dict is missing required fields
        3. Issuer — reject if issuer_pubkey not in known_token_issuers
        4. Signature — reject if Schnorr signature is invalid
        5. Double-spend — atomically mark token as spent; reject if already spent
        """
        if self._spent_token_storage is None:
            return False

        try:
            token = _blind.SpendableToken.from_dict(proof)

            # Check issuer is trusted
            if self._known_token_issuers and token.issuer_pubkey not in self._known_token_issuers:
                logger.debug("Token issuer %s not in known issuers", token.issuer_pubkey[:16])
                return False

            # Verify Schnorr signature
            if not _blind.verify_token(token):
                logger.debug("Token signature verification failed")
                return False

            # Atomic double-spend check: mark spent BEFORE accepting the write
            token_hash = _blind.compute_token_hash(token)
            if not self._spent_token_storage.check_and_mark_spent(token_hash):
                logger.debug("Token already spent: %s", token_hash[:16])
                return False

            return True
        except (KeyError, ValueError, TypeError) as e:
            logger.debug("Payment proof parsing failed: %s", e)
            return False
        except Exception:
            logger.warning("Payment verification failed", exc_info=True)
            return False

    def _check_rate_limit(self, pubkey_hash: str, event_type: str, max_per_day: int) -> bool:
        """Check and increment rate limit counter. Returns True if under limit."""
        if self._db_available:
            return self._check_rate_limit_db(pubkey_hash, event_type, max_per_day)
        return self._memory_limiter.check_and_increment(pubkey_hash, event_type, max_per_day)

    def _check_rate_limit_db(self, pubkey_hash: str, event_type: str, max_per_day: int) -> bool:
        """PostgreSQL rate limit check with upsert counter."""
        try:
            conn = self._conn_factory()
            try:
                with conn.cursor() as cur:
                    # Upsert: increment counter, return new count
                    cur.execute(
                        """
                        INSERT INTO coordination_rate_limits (public_key_hash, event_type, day, count)
                        VALUES (%s, %s, CURRENT_DATE, 1)
                        ON CONFLICT (public_key_hash, event_type, day)
                        DO UPDATE SET count = coordination_rate_limits.count + 1
                        RETURNING count
                        """,
                        (pubkey_hash, event_type),
                    )
                    new_count = cur.fetchone()[0]
                    conn.commit()

                    if new_count > max_per_day:
                        # Over limit — roll back the increment
                        cur.execute(
                            """
                            UPDATE coordination_rate_limits
                            SET count = count - 1
                            WHERE public_key_hash = %s AND event_type = %s AND day = CURRENT_DATE
                            """,
                            (pubkey_hash, event_type),
                        )
                        conn.commit()
                        return False
                    return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("Rate limit DB check failed: %s", e)
            # Fail closed on DB errors — fall back to in-memory limiter
            return self._memory_limiter.check_and_increment(pubkey_hash, event_type, max_per_day)

    def _log_acceptance(self, event_type: str, public_key: str, result: "PolicyResult"):
        """Log acceptance decision for monitoring. Fire-and-forget, never raises."""
        if not self._db_available:
            return
        pubkey_hash = self._hash_pubkey(public_key)
        try:
            conn = self._conn_factory()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO coordination_acceptance_logs
                            (event_type, acceptance_tier, accepted, reason, public_key_hash)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (event_type, result.tier, result.accepted, result.reason, pubkey_hash),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug("Failed to log acceptance decision: %s", e)

    def get_acceptance_stats(self, days: int = 7) -> dict:
        """Query acceptance stats for monitoring dashboard.

        Returns dict with:
          - writes_by_tier: {tier: count} for accepted writes
          - rejections_by_tier: {tier: count} for rejected writes
          - daily_breakdown: [{date, tier, accepted, count}]
          - rate_limit_hits: total rejected-due-to-rate-limit count
        """
        if not self._db_available:
            return {"writes_by_tier": {}, "rejections_by_tier": {}, "daily_breakdown": [], "rate_limit_hits": 0}

        since = datetime.now(timezone.utc) - timedelta(days=days)
        try:
            conn = self._conn_factory()
            try:
                with conn.cursor() as cur:
                    # Tier breakdown
                    cur.execute(
                        """
                        SELECT acceptance_tier, accepted, COUNT(*)
                        FROM coordination_acceptance_logs
                        WHERE timestamp >= %s
                        GROUP BY acceptance_tier, accepted
                        """,
                        (since,),
                    )
                    writes_by_tier = {}
                    rejections_by_tier = {}
                    for tier, accepted, count in cur.fetchall():
                        if accepted:
                            writes_by_tier[tier] = count
                        else:
                            rejections_by_tier[tier] = count

                    # Count rejections with rate limit in reason
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM coordination_acceptance_logs
                        WHERE timestamp >= %s AND NOT accepted AND reason LIKE %s
                        """,
                        (since, "%rate limit%"),
                    )
                    rate_limit_hits = cur.fetchone()[0]

                    # Daily breakdown
                    cur.execute(
                        """
                        SELECT DATE(timestamp) as day, acceptance_tier, accepted, COUNT(*)
                        FROM coordination_acceptance_logs
                        WHERE timestamp >= %s
                        GROUP BY day, acceptance_tier, accepted
                        ORDER BY day
                        """,
                        (since,),
                    )
                    daily_breakdown = [
                        {"date": str(row[0]), "tier": row[1], "accepted": row[2], "count": row[3]}
                        for row in cur.fetchall()
                    ]

                    return {
                        "writes_by_tier": writes_by_tier,
                        "rejections_by_tier": rejections_by_tier,
                        "daily_breakdown": daily_breakdown,
                        "rate_limit_hits": rate_limit_hits,
                    }
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to query acceptance stats: %s", e)
            return {"writes_by_tier": {}, "rejections_by_tier": {}, "daily_breakdown": [], "rate_limit_hits": 0}

    def cleanup_old_logs(self, days: int = 30):
        """Delete acceptance logs older than N days."""
        if not self._db_available:
            return
        try:
            conn = self._conn_factory()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM coordination_acceptance_logs WHERE timestamp < NOW() - MAKE_INTERVAL(days => %s)",
                        (days,),
                    )
                    deleted = cur.rowcount
                    conn.commit()
                    if deleted > 0:
                        logger.info("Cleaned up %d old acceptance log rows", deleted)
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Acceptance log cleanup failed: %s", e)

    def _record_metadata(self, public_key: str, entity: str, tier: str):
        """Record write metadata for analytics."""
        if not self._db_available:
            return
        pubkey_hash = self._hash_pubkey(public_key)
        try:
            conn = self._conn_factory()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO coordination_write_metadata (public_key_hash, entity, acceptance_tier)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (public_key_hash, entity)
                        DO UPDATE SET acceptance_tier = EXCLUDED.acceptance_tier, accepted_at = NOW()
                        """,
                        (pubkey_hash, entity, tier),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to record write metadata: %s", e)

    def cleanup_old_limits(self, days: int = 7):
        """Delete rate limit rows older than N days."""
        if self._db_available:
            try:
                conn = self._conn_factory()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM coordination_rate_limits WHERE day < CURRENT_DATE - %s",
                            (days,),
                        )
                        deleted = cur.rowcount
                        conn.commit()
                        if deleted > 0:
                            logger.info("Cleaned up %d old rate limit rows", deleted)
                finally:
                    conn.close()
            except Exception as e:
                logger.warning("Rate limit cleanup failed: %s", e)
        else:
            self._memory_limiter.cleanup_old()

    @staticmethod
    def _verify_pow(event_id: Optional[str], difficulty: int) -> bool:
        """Check NIP-13 proof-of-work (leading zero bits)."""
        if not event_id:
            return False
        try:
            event_bytes = bytes.fromhex(event_id)
            # Count leading zero bits
            leading_zeros = 0
            for byte in event_bytes:
                if byte == 0:
                    leading_zeros += 8
                else:
                    leading_zeros += (8 - byte.bit_length())
                    break
            return leading_zeros >= difficulty
        except (ValueError, TypeError):
            return False
