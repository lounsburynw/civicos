"""Tests for relay acceptance policy (rate limiting and tiered access)."""

import json
import time
import pytest
from unittest.mock import patch
from civicos_relay.server.acceptance import (
    AcceptancePolicy, PolicyResult, InMemoryRateLimiter, DEFAULT_POLICY,
    DEFAULT_ATTESTATION_VALIDITY_SECONDS, load_policy, _merge_policy,
)


class TestPolicyResult:
    def test_accepted_result(self):
        r = PolicyResult(accepted=True, tier="rate_limited", reason="ok")
        d = r.to_dict()
        assert d["accepted"] is True
        assert "options" not in d

    def test_rejected_result_includes_options(self):
        r = PolicyResult(accepted=False, tier="rejected", reason="limit exceeded")
        d = r.to_dict()
        assert d["accepted"] is False
        assert "options" in d
        assert "attestation" in d["options"]
        assert "payment" in d["options"]


class TestInMemoryRateLimiter:
    def test_under_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            assert limiter.check_and_increment("abc", "voice", 5)

    def test_over_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(3):
            limiter.check_and_increment("abc", "voice", 3)
        assert not limiter.check_and_increment("abc", "voice", 3)

    def test_different_event_types_independent(self):
        limiter = InMemoryRateLimiter()
        for _ in range(3):
            limiter.check_and_increment("abc", "voice", 3)
        # Comment limit is separate
        assert limiter.check_and_increment("abc", "comment", 3)

    def test_different_pubkeys_independent(self):
        limiter = InMemoryRateLimiter()
        for _ in range(3):
            limiter.check_and_increment("abc", "voice", 3)
        assert limiter.check_and_increment("def", "voice", 3)


class TestAcceptancePolicy:
    def test_voice_accepted_under_limit(self):
        policy = AcceptancePolicy()
        result = policy.check("voice", "a" * 64)
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_voice_rejected_over_limit(self):
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 3, "pow_difficulty": 3}})
        for _ in range(3):
            result = policy.check("voice", "a" * 64)
            assert result.accepted
        result = policy.check("voice", "a" * 64)
        assert not result.accepted
        assert "rate limit" in result.reason.lower()

    def test_unknown_event_type_rejected(self):
        policy = AcceptancePolicy()
        result = policy.check("unknown_type", "a" * 64)
        assert not result.accepted
        assert "Unknown" in result.reason

    def test_attestation_without_issuer_lookup_falls_through(self):
        """Without issuer_lookup, attestation proof falls through to rate limit."""
        policy = AcceptancePolicy()
        result = policy.check("voice", "a" * 64, attestation_proof={"kind": 30850})
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_payment_stub_always_fails(self):
        """Phase 4 stub: payment proof is always rejected, falls through to rate limit."""
        policy = AcceptancePolicy()
        result = policy.check("voice", "a" * 64, payment_proof={"type": "lightning"})
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_different_pubkeys_have_separate_limits(self):
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 2, "pow_difficulty": 3}})
        for _ in range(2):
            policy.check("voice", "a" * 64)
        # Different pubkey should still have quota
        result = policy.check("voice", "b" * 64)
        assert result.accepted

    def test_pubkey_hash_deterministic(self):
        policy = AcceptancePolicy()
        h1 = policy._hash_pubkey("abc123")
        h2 = policy._hash_pubkey("abc123")
        assert h1 == h2
        assert len(h1) == 16

    def test_default_policy_covers_all_event_types(self):
        expected_types = ["voice", "comment", "initiative", "action_create", "action_commit", "action_complete"]
        for et in expected_types:
            assert et in DEFAULT_POLICY, f"Missing event type: {et}"

    def test_initiative_no_rate_limit_requires_proof(self):
        """Initiative with no pow_difficulty and max_per_day should use rate limit."""
        policy = AcceptancePolicy()
        result = policy.check("initiative", "a" * 64)
        assert result.accepted  # Has max_per_day=5

    def test_pow_verification(self):
        # Event ID with leading zero byte = 8 leading zero bits
        assert AcceptancePolicy._verify_pow("00" + "ff" * 31, 8)
        assert not AcceptancePolicy._verify_pow("ff" * 32, 1)
        assert not AcceptancePolicy._verify_pow(None, 1)
        assert AcceptancePolicy._verify_pow("00" * 32, 256)


def _make_attestation_proof(
    jurisdiction="city-san-rafael",
    subject_pubkey="a" * 64,
    issuer_pubkey="b" * 64,
    created_at=None,
    event_id=None,
):
    """Helper to create a realistic-looking attestation proof dict."""
    if created_at is None:
        created_at = int(time.time()) - 3600  # 1 hour ago (well within validity)
    if event_id is None:
        event_id = "cc" * 32
    return {
        "id": event_id,
        "pubkey": issuer_pubkey,
        "created_at": created_at,
        "kind": 30850,
        "tags": [
            ["d", f"attest:{jurisdiction}:{subject_pubkey}"],
            ["p", subject_pubkey],
            ["j", jurisdiction],
            ["type", "physical"],
        ],
        "content": f"civicos:attestation:v1:{jurisdiction}:physical:{created_at}",
        "sig": "dd" * 32,
    }


class TestAttestationVerification:
    def test_valid_attestation_accepts_as_attested(self):
        """Valid attestation proof with issuer lookup should accept as tier='attested'."""
        issuer_pubkey = "b" * 64
        lookup = lambda j: [issuer_pubkey] if j == "city-san-rafael" else []
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof()
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=True) as mock_verify:
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"
        mock_verify.assert_called_once_with(proof, "a" * 64, "city-san-rafael", issuer_pubkey)

    def test_attestation_bypasses_exhausted_rate_limit(self):
        """Valid attestation should bypass rate limit even when quota exhausted."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        policy.check("voice", "a" * 64)  # exhaust rate limit
        result = policy.check("voice", "a" * 64)
        assert not result.accepted  # confirm exhausted

        proof = _make_attestation_proof()
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=True):
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"

    def test_no_issuer_lookup_falls_through(self):
        """Without issuer_lookup configured, attestation always falls through."""
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 5, "pow_difficulty": 3}})
        proof = _make_attestation_proof()
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_unknown_jurisdiction_falls_through(self):
        """Attestation for unknown jurisdiction falls through to lower tiers."""
        lookup = lambda j: []  # no issuers
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof(jurisdiction="unknown-city")
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_missing_jurisdiction_tag_falls_through(self):
        """Attestation proof without j-tag falls through to lower tiers."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = {"kind": 30850, "tags": [["p", "a" * 64]], "pubkey": "b" * 64}
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_crypto_verification_failure_falls_through(self):
        """If crypto verification fails, falls through to lower tiers."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof()
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=False):
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"


class TestMultiIssuerAttestation:
    def test_second_issuer_verifies_when_first_fails(self):
        """Attestation from issuer B passes when issuers A and B are both registered."""
        issuer_a = "a1" * 32
        issuer_b = "b2" * 32
        lookup = lambda j: [issuer_a, issuer_b]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof(issuer_pubkey=issuer_b)

        def verify_side_effect(proof, pubkey, jurisdiction, issuer_pubkey):
            return issuer_pubkey == issuer_b

        with patch("civicos_relay.voice.crypto.verify_attestation_proof", side_effect=verify_side_effect) as mock_verify:
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"
        assert mock_verify.call_count == 2

    def test_first_issuer_matches_without_trying_rest(self):
        """When first issuer verifies, remaining issuers are not tried."""
        issuer_a = "a1" * 32
        issuer_b = "b2" * 32
        lookup = lambda j: [issuer_a, issuer_b]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof(issuer_pubkey=issuer_a)
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=True) as mock_verify:
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"
        mock_verify.assert_called_once_with(proof, "a" * 64, "city-san-rafael", issuer_a)

    def test_no_issuer_matches_falls_through(self):
        """When no issuers verify, falls through to lower tiers."""
        lookup = lambda j: ["a1" * 32, "b2" * 32]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof()
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=False):
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_empty_issuer_list_falls_through(self):
        """Empty issuer list is equivalent to no trusted issuers."""
        lookup = lambda j: []
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof()
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_revoked_issuer_excluded_from_lookup(self):
        """Simulates that revoked issuers are excluded by the lookup callable."""
        # Only issuer_b is in the list (issuer_a was revoked and filtered out by lookup)
        issuer_b = "b2" * 32
        lookup = lambda j: [issuer_b]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof(issuer_pubkey=issuer_b)
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=True):
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"


class TestAttestationExpiry:
    def test_fresh_attestation_accepted(self):
        """Attestation created recently (within validity) should be accepted."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof(created_at=int(time.time()) - 3600)  # 1 hour ago
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=True):
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"

    def test_expired_attestation_rejected(self):
        """Attestation older than validity period should be rejected (falls through)."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        # created_at 2 years ago — well past the 1-year default
        two_years_ago = int(time.time()) - (2 * 365 * 24 * 60 * 60)
        proof = _make_attestation_proof(created_at=two_years_ago)
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        # Should fall through to rate limit since attestation is expired
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_expired_attestation_with_exhausted_rate_limit(self):
        """Expired attestation + exhausted rate limit = rejected."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": None}},
            issuer_lookup=lookup,
        )
        policy.check("voice", "a" * 64)  # exhaust rate limit

        two_years_ago = int(time.time()) - (2 * 365 * 24 * 60 * 60)
        proof = _make_attestation_proof(created_at=two_years_ago)
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert not result.accepted

    def test_custom_validity_period(self):
        """Custom validity period is respected."""
        lookup = lambda j: ["b" * 64]
        # 1-hour validity
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
            attestation_validity_seconds=3600,
        )
        # Created 2 hours ago — expired with 1-hour validity
        proof = _make_attestation_proof(created_at=int(time.time()) - 7200)
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"  # fell through

    def test_custom_validity_accepts_within_window(self):
        """Attestation within custom validity window is accepted."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
            attestation_validity_seconds=3600,
        )
        proof = _make_attestation_proof(created_at=int(time.time()) - 1800)  # 30 min ago
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=True):
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"

    def test_missing_created_at_treated_as_expired(self):
        """Attestation with no created_at (defaults to 0) is expired."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        proof = _make_attestation_proof()
        del proof["created_at"]  # remove created_at
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"  # fell through due to epoch 0 + validity < now

    def test_attestation_at_boundary_still_valid(self):
        """Attestation exactly at the validity boundary is still valid."""
        lookup = lambda j: ["b" * 64]
        validity = 3600
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
            attestation_validity_seconds=validity,
        )
        # created_at such that created_at + validity == now (just barely valid)
        proof = _make_attestation_proof(created_at=int(time.time()) - validity + 1)
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=True):
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"


class TestAttestationRevocation:
    def test_revoked_attestation_rejected(self):
        """Attestation with a revoked event ID should be rejected."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 5, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        revoked_id = "ee" * 32
        policy.revoke_attestation(revoked_id, reason="compromised key")
        proof = _make_attestation_proof(event_id=revoked_id)
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "rate_limited"  # fell through

    def test_revoked_attestation_with_exhausted_rate_limit(self):
        """Revoked attestation + exhausted rate limit = rejected."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": None}},
            issuer_lookup=lookup,
        )
        policy.check("voice", "a" * 64)  # exhaust rate limit

        revoked_id = "ee" * 32
        policy.revoke_attestation(revoked_id)
        proof = _make_attestation_proof(event_id=revoked_id)
        result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert not result.accepted

    def test_non_revoked_attestation_still_accepted(self):
        """Revoking one attestation doesn't affect others."""
        lookup = lambda j: ["b" * 64]
        policy = AcceptancePolicy(
            config={"voice": {"max_per_day": 1, "pow_difficulty": 3}},
            issuer_lookup=lookup,
        )
        policy.revoke_attestation("ee" * 32)  # revoke a different one
        proof = _make_attestation_proof(event_id="ff" * 32)  # different ID
        with patch("civicos_relay.voice.crypto.verify_attestation_proof", return_value=True):
            result = policy.check("voice", "a" * 64, attestation_proof=proof)
        assert result.accepted
        assert result.tier == "attested"

    def test_is_attestation_revoked(self):
        """is_attestation_revoked returns correct status."""
        policy = AcceptancePolicy()
        assert not policy.is_attestation_revoked("ee" * 32)
        policy.revoke_attestation("ee" * 32)
        assert policy.is_attestation_revoked("ee" * 32)

    def test_revoke_idempotent(self):
        """Revoking the same attestation twice doesn't error."""
        policy = AcceptancePolicy()
        policy.revoke_attestation("ee" * 32)
        policy.revoke_attestation("ee" * 32)  # should not raise
        assert policy.is_attestation_revoked("ee" * 32)

    def test_load_revocations_noop_without_db(self):
        """load_revocations_from_db is a no-op without database."""
        policy = AcceptancePolicy()
        policy.load_revocations_from_db()  # should not raise
        assert len(policy._revoked_attestations) == 0


class TestProofOfWork:
    def test_pow_bypasses_rate_limit(self):
        """Valid PoW should accept even when rate limit is exhausted."""
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 1, "pow_difficulty": 3}})
        # Exhaust rate limit
        policy.check("voice", "a" * 64)
        # Without PoW, should be rejected
        result = policy.check("voice", "a" * 64)
        assert not result.accepted
        # With valid PoW (leading zero byte = 8 bits >= 3), should be accepted
        result = policy.check("voice", "a" * 64, event_id="00" + "ff" * 31)
        assert result.accepted
        assert result.tier == "pow"

    def test_invalid_pow_falls_through_to_rate_limit(self):
        """Invalid PoW should fall through to rate limit check."""
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 5, "pow_difficulty": 3}})
        # Invalid PoW (no leading zeros) but under rate limit — should still accept via rate limit
        result = policy.check("voice", "a" * 64, event_id="ff" * 32)
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_pow_not_checked_when_no_difficulty(self):
        """Event types without pow_difficulty should skip PoW check."""
        policy = AcceptancePolicy(config={"initiative": {"max_per_day": 5, "pow_difficulty": None}})
        result = policy.check("initiative", "a" * 64, event_id="00" * 32)
        assert result.accepted
        assert result.tier == "rate_limited"  # Not pow, because pow_difficulty is None

    def test_pow_not_checked_when_no_event_id(self):
        """No event_id provided should skip PoW and fall through to rate limit."""
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 5, "pow_difficulty": 3}})
        result = policy.check("voice", "a" * 64)
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_pow_with_exact_difficulty_match(self):
        """PoW with exactly the required bits should be accepted."""
        # "00" = 8 leading zero bits, difficulty=8 should pass
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 1, "pow_difficulty": 8}})
        policy.check("voice", "a" * 64)  # exhaust rate limit
        result = policy.check("voice", "a" * 64, event_id="00" + "ff" * 31)
        assert result.accepted
        assert result.tier == "pow"

    def test_pow_insufficient_difficulty_rejected(self):
        """PoW below required difficulty should not count as valid PoW."""
        # "00" = 8 leading zero bits, but difficulty=16 requires more
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 1, "pow_difficulty": 16}})
        policy.check("voice", "a" * 64)  # exhaust rate limit
        result = policy.check("voice", "a" * 64, event_id="00" + "ff" * 31)
        assert not result.accepted  # PoW insufficient AND rate limit exhausted


class TestAcceptancePolicyToDict:
    def test_402_response_format(self):
        policy = AcceptancePolicy(config={"voice": {"max_per_day": 1, "pow_difficulty": 3}})
        policy.check("voice", "a" * 64)
        result = policy.check("voice", "a" * 64)
        assert not result.accepted
        body = result.to_dict()
        assert body["accepted"] is False
        assert body["tier"] == "rejected"
        assert "retry" in body["options"]


class TestAcceptanceLogging:
    def test_log_acceptance_noop_without_db(self):
        """_log_acceptance is a no-op when DB is not available (in-memory mode)."""
        policy = AcceptancePolicy()
        result = PolicyResult(accepted=True, tier="rate_limited", reason="ok")
        # Should not raise
        policy._log_acceptance("voice", "a" * 64, result)

    def test_log_acceptance_fire_and_forget_on_db_error(self):
        """_log_acceptance swallows exceptions (fire-and-forget pattern)."""
        policy = AcceptancePolicy()
        # Force db_available but with a broken connection factory
        policy._db_available = True
        policy._conn_factory = lambda: (_ for _ in ()).throw(Exception("connection failed"))
        result = PolicyResult(accepted=True, tier="pow", reason="Valid PoW")
        # Should not raise despite DB error
        policy._log_acceptance("voice", "a" * 64, result)

    def test_get_acceptance_stats_without_db(self):
        """get_acceptance_stats returns empty structure when DB is not available."""
        policy = AcceptancePolicy()
        stats = policy.get_acceptance_stats()
        assert stats == {"writes_by_tier": {}, "rejections_by_tier": {}, "daily_breakdown": [], "rate_limit_hits": 0}

    def test_get_acceptance_stats_fire_and_forget_on_db_error(self):
        """get_acceptance_stats returns empty structure on DB errors."""
        policy = AcceptancePolicy()
        policy._db_available = True
        policy._conn_factory = lambda: (_ for _ in ()).throw(Exception("connection failed"))
        stats = policy.get_acceptance_stats()
        assert stats["writes_by_tier"] == {}
        assert stats["rate_limit_hits"] == 0

    def test_cleanup_old_logs_noop_without_db(self):
        """cleanup_old_logs is a no-op when DB is not available."""
        policy = AcceptancePolicy()
        # Should not raise
        policy.cleanup_old_logs()

    def test_cleanup_old_logs_fire_and_forget_on_db_error(self):
        """cleanup_old_logs swallows exceptions."""
        policy = AcceptancePolicy()
        policy._db_available = True
        policy._conn_factory = lambda: (_ for _ in ()).throw(Exception("connection failed"))
        # Should not raise
        policy.cleanup_old_logs()


class TestLoadPolicy:
    """Tests for config-driven rate limit policy loading."""

    def test_no_file_returns_defaults(self, tmp_path):
        """Without any policy file, load_policy returns DEFAULT_POLICY."""
        with patch.dict("os.environ", {"RELAY_POLICY_FILE": str(tmp_path / "nonexistent.json")}, clear=False):
            policy = load_policy()
        assert policy == DEFAULT_POLICY

    def test_env_var_override(self, tmp_path):
        """RELAY_POLICY_FILE env var takes precedence."""
        policy_file = tmp_path / "custom.json"
        policy_file.write_text(json.dumps({
            "default": {
                "voice": {"max_per_day": 999}
            }
        }))
        with patch.dict("os.environ", {"RELAY_POLICY_FILE": str(policy_file)}, clear=False):
            policy = load_policy()
        assert policy["voice"]["max_per_day"] == 999
        # pow_difficulty should be inherited from DEFAULT_POLICY
        assert policy["voice"]["pow_difficulty"] == DEFAULT_POLICY["voice"]["pow_difficulty"]

    def test_jurisdiction_specific_override(self, tmp_path):
        """Per-jurisdiction config overrides defaults."""
        policy_file = tmp_path / "policies.json"
        policy_file.write_text(json.dumps({
            "default": {
                "voice": {"max_per_day": 50, "pow_difficulty": 16}
            },
            "city-berkeley": {
                "voice": {"max_per_day": 200}
            }
        }))
        with patch.dict("os.environ", {"RELAY_POLICY_FILE": str(policy_file)}, clear=False):
            policy = load_policy("city-berkeley")
        assert policy["voice"]["max_per_day"] == 200
        assert policy["voice"]["pow_difficulty"] == 16

    def test_unknown_jurisdiction_uses_defaults(self, tmp_path):
        """Unknown jurisdiction falls through to file defaults."""
        policy_file = tmp_path / "policies.json"
        policy_file.write_text(json.dumps({
            "default": {
                "voice": {"max_per_day": 75}
            },
            "city-berkeley": {
                "voice": {"max_per_day": 200}
            }
        }))
        with patch.dict("os.environ", {"RELAY_POLICY_FILE": str(policy_file)}, clear=False):
            policy = load_policy("city-unknown")
        assert policy["voice"]["max_per_day"] == 75

    def test_partial_override_preserves_other_event_types(self, tmp_path):
        """Overriding one event type preserves others from defaults."""
        policy_file = tmp_path / "policies.json"
        policy_file.write_text(json.dumps({
            "default": {
                "voice": {"max_per_day": 100}
            }
        }))
        with patch.dict("os.environ", {"RELAY_POLICY_FILE": str(policy_file)}, clear=False):
            policy = load_policy()
        # Comment should still have DEFAULT_POLICY values
        assert policy["comment"] == DEFAULT_POLICY["comment"]

    def test_invalid_json_falls_back_to_defaults(self, tmp_path):
        """Invalid JSON in policy file falls back to DEFAULT_POLICY."""
        policy_file = tmp_path / "bad.json"
        policy_file.write_text("not json{{{")
        with patch.dict("os.environ", {"RELAY_POLICY_FILE": str(policy_file)}, clear=False):
            policy = load_policy()
        assert policy == DEFAULT_POLICY

    def test_acceptance_policy_uses_jurisdiction_id(self, tmp_path):
        """AcceptancePolicy constructor respects jurisdiction_id parameter."""
        policy_file = tmp_path / "policies.json"
        policy_file.write_text(json.dumps({
            "default": {},
            "city-berkeley": {
                "voice": {"max_per_day": 200, "pow_difficulty": 12}
            }
        }))
        with patch.dict("os.environ", {"RELAY_POLICY_FILE": str(policy_file)}, clear=False):
            policy = AcceptancePolicy(jurisdiction_id="city-berkeley")
        assert policy._config["voice"]["max_per_day"] == 200
        assert policy._config["voice"]["pow_difficulty"] == 12


class TestMergePolicy:
    """Tests for policy merge logic."""

    def test_merge_updates_existing_key(self):
        base = {"voice": {"max_per_day": 50, "pow_difficulty": 16}}
        _merge_policy(base, {"voice": {"max_per_day": 100}})
        assert base["voice"]["max_per_day"] == 100
        assert base["voice"]["pow_difficulty"] == 16

    def test_merge_adds_new_event_type(self):
        base = {"voice": {"max_per_day": 50}}
        _merge_policy(base, {"petition": {"max_per_day": 5}})
        assert base["petition"]["max_per_day"] == 5
        assert base["voice"]["max_per_day"] == 50

    def test_merge_does_not_modify_source(self):
        from copy import deepcopy
        original = {"voice": {"max_per_day": 50, "pow_difficulty": 16}}
        base = deepcopy(original)
        overrides = {"voice": {"max_per_day": 100}}
        _merge_policy(base, overrides)
        # Overrides dict should be unchanged
        assert overrides == {"voice": {"max_per_day": 100}}
