"""Tests for TokenIssuer — the blind signature token issuance service.

Covers: nonce session lifecycle, signing, rate limiting (Wagner's attack),
session expiry, batch issuance, and full integration with AcceptancePolicy.
"""

import time

import pytest
from coincurve import PrivateKey

from civicos_relay.server.token_issuer import (
    InvalidSession,
    TokenIssuer,
    TooManyConcurrentSessions,
)
from civicos_relay.storage.memory import InMemorySpentTokenStorage
from civicos_relay.voice.blind import (
    blind,
    compute_token_hash,
    generate_token_message,
    unblind,
    verify_token,
)


# --- Fixtures ---


@pytest.fixture
def issuer_secret():
    """Deterministic issuer secret for reproducible tests."""
    return (99).to_bytes(32, "big")


@pytest.fixture
def issuer(issuer_secret):
    return TokenIssuer(issuer_secret)


@pytest.fixture
def issuer_pubkey(issuer):
    return issuer.public_key


def _full_issue(issuer: TokenIssuer) -> "SpendableToken":
    """Helper: complete a full token issuance via TokenIssuer."""
    from civicos_relay.voice.blind import SpendableToken

    session_id, nonce_point = issuer.create_nonce_session()
    message = generate_token_message()
    challenge, ctx = blind(message, issuer.public_key, nonce_point)
    blind_sig = issuer.sign(session_id, challenge)
    return unblind(blind_sig, ctx, issuer.public_key)


# --- Nonce Session ---


class TestNonceSession:
    def test_create_session_returns_id_and_point(self, issuer):
        session_id, nonce_point = issuer.create_nonce_session()
        assert isinstance(session_id, str)
        assert len(session_id) == 32  # 16 bytes hex
        assert isinstance(nonce_point, bytes)
        assert len(nonce_point) == 33  # compressed pubkey

    def test_sessions_have_unique_ids(self, issuer):
        ids = {issuer.create_nonce_session()[0] for _ in range(5)}
        assert len(ids) == 5

    def test_sessions_have_unique_nonces(self, issuer):
        nonces = {issuer.create_nonce_session()[1] for _ in range(5)}
        assert len(nonces) == 5

    def test_active_session_count(self, issuer):
        assert issuer.active_session_count == 0
        issuer.create_nonce_session()
        assert issuer.active_session_count == 1
        issuer.create_nonce_session()
        assert issuer.active_session_count == 2


# --- Signing ---


class TestSigning:
    def test_sign_produces_valid_token(self, issuer):
        token = _full_issue(issuer)
        assert verify_token(token)

    def test_sign_many_tokens(self, issuer):
        """Issue 5 tokens sequentially — all verify."""
        for _ in range(5):
            token = _full_issue(issuer)
            assert verify_token(token)

    def test_sign_consumes_session(self, issuer):
        session_id, nonce_point = issuer.create_nonce_session()
        msg = generate_token_message()
        challenge, ctx = blind(msg, issuer.public_key, nonce_point)
        issuer.sign(session_id, challenge)

        # Second sign with same session should fail
        with pytest.raises(InvalidSession):
            issuer.sign(session_id, challenge)

    def test_sign_reduces_active_count(self, issuer):
        session_id, _ = issuer.create_nonce_session()
        assert issuer.active_session_count == 1
        msg = generate_token_message()
        challenge, _ = blind(msg, issuer.public_key, _)  # noqa: need nonce_point
        # Re-do properly
        session_id, nonce_point = issuer.create_nonce_session()
        challenge, ctx = blind(msg, issuer.public_key, nonce_point)
        # 2 sessions active (the first orphaned + new one)
        issuer.sign(session_id, challenge)
        # Only the orphaned one remains
        assert issuer.active_session_count == 1

    def test_token_issuer_pubkey_matches(self, issuer):
        token = _full_issue(issuer)
        assert token.issuer_pubkey == issuer.public_key_hex


# --- Rate Limiting (Wagner's Attack Mitigation) ---


class TestRateLimiting:
    def test_max_concurrent_sessions_enforced(self):
        iss = TokenIssuer(PrivateKey().secret, max_concurrent_sessions=3)
        for _ in range(3):
            iss.create_nonce_session()
        with pytest.raises(TooManyConcurrentSessions):
            iss.create_nonce_session()

    def test_signing_frees_slot(self):
        iss = TokenIssuer(PrivateKey().secret, max_concurrent_sessions=2)
        s1, r1 = iss.create_nonce_session()
        iss.create_nonce_session()  # fills slot 2

        # Can't create a third
        with pytest.raises(TooManyConcurrentSessions):
            iss.create_nonce_session()

        # Sign one to free a slot
        msg = generate_token_message()
        challenge, ctx = blind(msg, iss.public_key, r1)
        iss.sign(s1, challenge)

        # Now we can create another
        iss.create_nonce_session()  # should not raise

    def test_max_concurrent_sessions_default(self, issuer):
        """Default is 5 concurrent sessions."""
        for _ in range(5):
            issuer.create_nonce_session()
        with pytest.raises(TooManyConcurrentSessions):
            issuer.create_nonce_session()


# --- Session Expiry ---


class TestSessionExpiry:
    def test_expired_session_rejected(self):
        iss = TokenIssuer(PrivateKey().secret, session_ttl_seconds=0.01)
        session_id, nonce_point = iss.create_nonce_session()
        time.sleep(0.05)

        msg = generate_token_message()
        challenge, ctx = blind(msg, iss.public_key, nonce_point)
        with pytest.raises(InvalidSession):
            iss.sign(session_id, challenge)

    def test_expired_sessions_free_slots(self):
        iss = TokenIssuer(
            PrivateKey().secret,
            max_concurrent_sessions=2,
            session_ttl_seconds=0.01,
        )
        iss.create_nonce_session()
        iss.create_nonce_session()

        # Full
        with pytest.raises(TooManyConcurrentSessions):
            iss.create_nonce_session()

        time.sleep(0.05)

        # Expired sessions cleaned up, slots available
        iss.create_nonce_session()  # should not raise
        assert iss.active_session_count == 1

    def test_non_expired_session_still_works(self):
        iss = TokenIssuer(PrivateKey().secret, session_ttl_seconds=60.0)
        session_id, nonce_point = iss.create_nonce_session()
        msg = generate_token_message()
        challenge, ctx = blind(msg, iss.public_key, nonce_point)
        blind_sig = iss.sign(session_id, challenge)
        token = unblind(blind_sig, ctx, iss.public_key)
        assert verify_token(token)


# --- Batch Issuance ---


class TestBatchIssuance:
    def test_issue_batch(self):
        iss = TokenIssuer(PrivateKey().secret, max_concurrent_sessions=10)
        sessions = iss.issue_token_batch(5)
        assert len(sessions) == 5
        assert iss.active_session_count == 5

        # Each session produces a valid token
        for session_id, nonce_point in sessions:
            msg = generate_token_message()
            challenge, ctx = blind(msg, iss.public_key, nonce_point)
            blind_sig = iss.sign(session_id, challenge)
            token = unblind(blind_sig, ctx, iss.public_key)
            assert verify_token(token)

    def test_batch_exceeds_limit(self):
        iss = TokenIssuer(PrivateKey().secret, max_concurrent_sessions=3)
        with pytest.raises(TooManyConcurrentSessions):
            iss.issue_token_batch(5)

    def test_batch_with_existing_sessions(self):
        iss = TokenIssuer(PrivateKey().secret, max_concurrent_sessions=5)
        iss.create_nonce_session()
        iss.create_nonce_session()
        # 2 used, 3 available
        sessions = iss.issue_token_batch(3)
        assert len(sessions) == 3
        assert iss.active_session_count == 5

        with pytest.raises(TooManyConcurrentSessions):
            iss.issue_token_batch(1)


# --- Invalid Session ---


class TestInvalidSession:
    def test_unknown_session_id(self, issuer):
        with pytest.raises(InvalidSession):
            issuer.sign("nonexistent", b"\x00" * 32)

    def test_empty_session_id(self, issuer):
        with pytest.raises(InvalidSession):
            issuer.sign("", b"\x00" * 32)


# --- Integration: Issue → Spend → Double-Spend ---


class TestIntegrationWithAcceptancePolicy:
    """Full flow: TokenIssuer issues token → AcceptancePolicy verifies + spends."""

    def test_issued_token_accepted_by_policy(self, issuer):
        from civicos_relay.server.acceptance import AcceptancePolicy

        spent_store = InMemorySpentTokenStorage()
        policy = AcceptancePolicy(
            spent_token_storage=spent_store,
            known_token_issuers={issuer.public_key_hex},
        )

        token = _full_issue(issuer)
        result = policy.check(
            event_type="voice",
            public_key="user_pubkey_hex",
            payment_proof=token.to_dict(),
        )
        assert result.accepted
        assert result.tier == "paid"

    def test_double_spend_rejected_by_policy(self, issuer):
        from civicos_relay.server.acceptance import AcceptancePolicy

        spent_store = InMemorySpentTokenStorage()
        policy = AcceptancePolicy(
            spent_token_storage=spent_store,
            known_token_issuers={issuer.public_key_hex},
        )

        token = _full_issue(issuer)
        proof = token.to_dict()

        # First use succeeds
        result1 = policy.check(
            event_type="voice",
            public_key="user_pubkey_hex",
            payment_proof=proof,
        )
        assert result1.accepted

        # Second use (double-spend) — token invalid, falls through to rate limit
        result2 = policy.check(
            event_type="voice",
            public_key="user_pubkey_hex",
            payment_proof=proof,
        )
        assert result2.accepted
        assert result2.tier == "rate_limited"

    def test_unknown_issuer_rejected_by_policy(self):
        """Token from unknown issuer doesn't get paid tier."""
        from civicos_relay.server.acceptance import AcceptancePolicy

        unknown_issuer = TokenIssuer(PrivateKey().secret)
        legitimate_issuer = TokenIssuer(PrivateKey().secret)

        spent_store = InMemorySpentTokenStorage()
        policy = AcceptancePolicy(
            spent_token_storage=spent_store,
            known_token_issuers={legitimate_issuer.public_key_hex},
        )

        token = _full_issue(unknown_issuer)
        result = policy.check(
            event_type="voice",
            public_key="user_pubkey_hex",
            payment_proof=token.to_dict(),
        )
        # Unknown issuer token invalid, falls through to rate limit
        assert result.accepted
        assert result.tier == "rate_limited"

    def test_batch_issue_all_spendable(self, issuer):
        """Issue a batch of tokens and spend them all — each accepted once."""
        from civicos_relay.server.acceptance import AcceptancePolicy

        secret = PrivateKey().secret
        batch_issuer = TokenIssuer(secret, max_concurrent_sessions=10)

        spent_store = InMemorySpentTokenStorage()
        policy = AcceptancePolicy(
            spent_token_storage=spent_store,
            known_token_issuers={batch_issuer.public_key_hex},
        )

        # Issue 5 tokens
        sessions = batch_issuer.issue_token_batch(5)
        tokens = []
        for session_id, nonce_point in sessions:
            msg = generate_token_message()
            challenge, ctx = blind(msg, batch_issuer.public_key, nonce_point)
            blind_sig = batch_issuer.sign(session_id, challenge)
            token = unblind(blind_sig, ctx, batch_issuer.public_key)
            tokens.append(token)

        # Each token spends once
        for i, token in enumerate(tokens):
            result = policy.check(
                event_type="voice",
                public_key=f"user_{i}",
                payment_proof=token.to_dict(),
            )
            assert result.accepted
            assert result.tier == "paid"

        # Re-spending any token — token invalid, falls through to rate limit
        for token in tokens:
            result = policy.check(
                event_type="voice",
                public_key="another_user",
                payment_proof=token.to_dict(),
            )
            assert result.accepted
            assert result.tier == "rate_limited"

    def test_each_token_has_unique_hash(self, issuer):
        """All tokens from the same issuer have distinct hashes."""
        tokens = [_full_issue(issuer) for _ in range(5)]
        hashes = {compute_token_hash(t) for t in tokens}
        assert len(hashes) == 5
