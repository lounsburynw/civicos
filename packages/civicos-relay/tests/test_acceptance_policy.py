"""Tests for relay acceptance policy (rate limiting and tiered access)."""

import pytest
from civicos_relay.server.acceptance import AcceptancePolicy, PolicyResult, InMemoryRateLimiter, DEFAULT_POLICY


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

    def test_attestation_stub_always_fails(self):
        """Phase 3 stub: attestation proof is always rejected, falls through to rate limit."""
        policy = AcceptancePolicy()
        result = policy.check("voice", "a" * 64, attestation_proof={"kind": 30850})
        # Should still be accepted via rate limit since attestation stub fails
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
