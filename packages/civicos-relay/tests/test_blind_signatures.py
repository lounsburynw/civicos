"""Tests for Schnorr blind signature primitives.

Covers: roundtrip signing, tamper detection, wrong issuer rejection,
token hash uniqueness, serialization, and batch issuance.
"""

import pytest
from coincurve import PrivateKey

from civicos_relay.voice.blind import (
    N,
    BlindingContext,
    SpendableToken,
    blind,
    compute_token_hash,
    generate_nonce,
    generate_token_message,
    sign_blinded,
    unblind,
    verify_token,
)
from civicos_relay.storage.memory import InMemorySpentTokenStorage


# --- Fixtures ---


@pytest.fixture
def issuer():
    """Deterministic issuer keypair for reproducible tests."""
    secret = (42).to_bytes(32, "big")
    return PrivateKey(secret)


@pytest.fixture
def issuer_pubkey(issuer):
    return issuer.public_key.format(compressed=True)


def _issue_token(issuer, issuer_pubkey, message=None):
    """Helper: full issuance roundtrip returning a SpendableToken."""
    msg = message or generate_token_message()
    nonce_secret, nonce_point = generate_nonce()
    challenge, ctx = blind(msg, issuer_pubkey, nonce_point)
    blind_sig = sign_blinded(challenge, issuer.secret, nonce_secret)
    return unblind(blind_sig, ctx, issuer_pubkey)


# --- Roundtrip ---


class TestRoundtrip:
    def test_basic_roundtrip(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        assert verify_token(token)

    def test_roundtrip_many_tokens(self, issuer, issuer_pubkey):
        """Issue 20 tokens — all must verify."""
        for _ in range(20):
            token = _issue_token(issuer, issuer_pubkey)
            assert verify_token(token)

    def test_different_messages_all_verify(self, issuer, issuer_pubkey):
        messages = [generate_token_message() for _ in range(5)]
        tokens = [_issue_token(issuer, issuer_pubkey, m) for m in messages]
        for t in tokens:
            assert verify_token(t)

    def test_token_fields_populated(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        assert len(bytes.fromhex(token.message)) == 32
        assert len(bytes.fromhex(token.signature)) == 65
        assert token.issuer_pubkey == issuer_pubkey.hex()


# --- Rejection ---


class TestRejection:
    def test_tampered_message(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        bad = SpendableToken(
            message="aa" * 32,
            signature=token.signature,
            issuer_pubkey=token.issuer_pubkey,
        )
        assert not verify_token(bad)

    def test_tampered_signature(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        sig_bytes = bytes.fromhex(token.signature)
        # Flip a byte in the scalar portion
        tampered = sig_bytes[:33] + bytes([sig_bytes[33] ^ 0xFF]) + sig_bytes[34:]
        bad = SpendableToken(
            message=token.message,
            signature=tampered.hex(),
            issuer_pubkey=token.issuer_pubkey,
        )
        assert not verify_token(bad)

    def test_wrong_issuer(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        wrong = PrivateKey()
        bad = SpendableToken(
            message=token.message,
            signature=token.signature,
            issuer_pubkey=wrong.public_key.format(compressed=True).hex(),
        )
        assert not verify_token(bad)

    def test_empty_signature(self):
        bad = SpendableToken(message="aa" * 32, signature="", issuer_pubkey="aa" * 33)
        assert not verify_token(bad)

    def test_short_signature(self, issuer, issuer_pubkey):
        bad = SpendableToken(
            message="aa" * 32,
            signature="bb" * 30,
            issuer_pubkey=issuer_pubkey.hex(),
        )
        assert not verify_token(bad)

    def test_invalid_pubkey(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        bad = SpendableToken(
            message=token.message,
            signature=token.signature,
            issuer_pubkey="00" * 33,
        )
        assert not verify_token(bad)

    def test_zero_scalar_rejected(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        sig_bytes = bytes.fromhex(token.signature)
        # Replace scalar with zero
        bad_sig = sig_bytes[:33] + b"\x00" * 32
        bad = SpendableToken(
            message=token.message,
            signature=bad_sig.hex(),
            issuer_pubkey=token.issuer_pubkey,
        )
        assert not verify_token(bad)

    def test_scalar_ge_n_rejected(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        sig_bytes = bytes.fromhex(token.signature)
        # Replace scalar with N (group order — invalid)
        bad_sig = sig_bytes[:33] + N.to_bytes(32, "big")
        bad = SpendableToken(
            message=token.message,
            signature=bad_sig.hex(),
            issuer_pubkey=token.issuer_pubkey,
        )
        assert not verify_token(bad)


# --- Token Hash ---


class TestTokenHash:
    def test_deterministic(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        assert compute_token_hash(token) == compute_token_hash(token)

    def test_different_tokens_different_hashes(self, issuer, issuer_pubkey):
        t1 = _issue_token(issuer, issuer_pubkey)
        t2 = _issue_token(issuer, issuer_pubkey)
        assert compute_token_hash(t1) != compute_token_hash(t2)

    def test_hash_is_hex_sha256(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        h = compute_token_hash(token)
        assert len(h) == 64
        int(h, 16)  # valid hex


# --- Serialization ---


class TestSerialization:
    def test_to_dict_roundtrip(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        d = token.to_dict()
        restored = SpendableToken.from_dict(d)
        assert restored == token
        assert verify_token(restored)

    def test_to_dict_keys(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        d = token.to_dict()
        assert set(d.keys()) == {"message", "signature", "issuer_pubkey"}


# --- Multiple Issuers ---


class TestMultipleIssuers:
    def test_tokens_from_different_issuers(self):
        """Tokens from different issuers each verify against their own pubkey."""
        issuers = [PrivateKey() for _ in range(3)]
        for iss in issuers:
            pub = iss.public_key.format(compressed=True)
            token = _issue_token(iss, pub)
            assert verify_token(token)

    def test_cross_issuer_rejection(self):
        """A token from issuer A must not verify against issuer B's key."""
        a = PrivateKey()
        b = PrivateKey()
        a_pub = a.public_key.format(compressed=True)
        b_pub = b.public_key.format(compressed=True)

        token_a = _issue_token(a, a_pub)
        assert verify_token(token_a)

        # Swap the issuer pubkey
        swapped = SpendableToken(
            message=token_a.message,
            signature=token_a.signature,
            issuer_pubkey=b_pub.hex(),
        )
        assert not verify_token(swapped)


# --- Edge Cases ---


class TestEdgeCases:
    def test_generate_token_message_uniqueness(self):
        messages = {generate_token_message() for _ in range(100)}
        assert len(messages) == 100

    def test_generate_nonce_uniqueness(self):
        nonces = {generate_nonce()[1] for _ in range(100)}
        assert len(nonces) == 100

    def test_blinding_context_is_frozen(self, issuer, issuer_pubkey):
        msg = generate_token_message()
        _, nonce_point = generate_nonce()
        _, ctx = blind(msg, issuer_pubkey, nonce_point)
        with pytest.raises(AttributeError):
            ctx.alpha = b"\x00" * 32

    def test_spendable_token_is_frozen(self, issuer, issuer_pubkey):
        token = _issue_token(issuer, issuer_pubkey)
        with pytest.raises(AttributeError):
            token.message = "changed"


# --- SpentTokenStorage (InMemory) ---


class TestInMemorySpentTokenStorage:
    def test_mark_unspent_returns_true(self, issuer, issuer_pubkey):
        store = InMemorySpentTokenStorage()
        token = _issue_token(issuer, issuer_pubkey)
        h = compute_token_hash(token)
        assert store.check_and_mark_spent(h) is True

    def test_double_spend_returns_false(self, issuer, issuer_pubkey):
        store = InMemorySpentTokenStorage()
        token = _issue_token(issuer, issuer_pubkey)
        h = compute_token_hash(token)
        assert store.check_and_mark_spent(h) is True
        assert store.check_and_mark_spent(h) is False

    def test_is_spent_before_and_after(self, issuer, issuer_pubkey):
        store = InMemorySpentTokenStorage()
        token = _issue_token(issuer, issuer_pubkey)
        h = compute_token_hash(token)
        assert store.is_spent(h) is False
        store.check_and_mark_spent(h)
        assert store.is_spent(h) is True

    def test_different_tokens_independent(self, issuer, issuer_pubkey):
        store = InMemorySpentTokenStorage()
        t1 = _issue_token(issuer, issuer_pubkey)
        t2 = _issue_token(issuer, issuer_pubkey)
        h1 = compute_token_hash(t1)
        h2 = compute_token_hash(t2)
        assert store.check_and_mark_spent(h1) is True
        assert store.check_and_mark_spent(h2) is True
        assert store.is_spent(h1) is True
        assert store.is_spent(h2) is True

    def test_relay_write_id_stored(self):
        store = InMemorySpentTokenStorage()
        assert store.check_and_mark_spent("abc123", relay_write_id="write-1") is True
        assert store.check_and_mark_spent("abc123", relay_write_id="write-2") is False
        assert store._spent["abc123"] == "write-1"
