"""
Tests for voucher verification and tracking on the relay side.

To run:
    pytest packages/civicos-relay/tests/test_voucher_verify.py -q --override-ini="addopts="
"""

import base64
import hashlib
import hmac
import time

import pytest

from civicos_relay.server.voucher import verify_voucher, VoucherClaims, VoucherTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SECRET = b"test_secret_key"


def _make_voucher(
    session_id: str = "cs_test",
    token_count: int = 50,
    expires_at: int | None = None,
    secret: bytes = SECRET,
) -> str:
    """Build a valid voucher for testing."""
    if expires_at is None:
        expires_at = int(time.time()) + 300
    payload = f"{session_id}:{token_count}:{expires_at}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


# ---------------------------------------------------------------------------
# verify_voucher
# ---------------------------------------------------------------------------


class TestVerifyVoucher:
    def test_accepts_valid_voucher(self):
        voucher = _make_voucher()
        claims = verify_voucher(voucher, SECRET)
        assert claims.session_id == "cs_test"
        assert claims.token_count == 50
        assert claims.expires_at > int(time.time())

    def test_returns_correct_claims(self):
        voucher = _make_voucher(session_id="cs_abc", token_count=25)
        claims = verify_voucher(voucher, SECRET)
        assert claims.session_id == "cs_abc"
        assert claims.token_count == 25

    def test_rejects_tampered_payload(self):
        voucher = _make_voucher()
        # Tamper with the payload (change first char of base64)
        parts = voucher.split(".")
        tampered_b64 = "X" + parts[0][1:]
        tampered = f"{tampered_b64}.{parts[1]}"
        with pytest.raises(ValueError, match="Invalid voucher signature"):
            verify_voucher(tampered, SECRET)

    def test_rejects_tampered_signature(self):
        voucher = _make_voucher()
        parts = voucher.split(".")
        tampered = f"{parts[0]}.{'0' * 64}"
        with pytest.raises(ValueError, match="Invalid voucher signature"):
            verify_voucher(tampered, SECRET)

    def test_rejects_wrong_secret(self):
        voucher = _make_voucher(secret=b"correct_secret")
        with pytest.raises(ValueError, match="Invalid voucher signature"):
            verify_voucher(voucher, b"wrong_secret")

    def test_rejects_expired_voucher(self):
        voucher = _make_voucher(expires_at=int(time.time()) - 10)
        with pytest.raises(ValueError, match="Voucher expired"):
            verify_voucher(voucher, SECRET)

    def test_rejects_malformed_no_dot(self):
        with pytest.raises(ValueError, match="Malformed voucher"):
            verify_voucher("nodothere", SECRET)

    def test_rejects_malformed_extra_dots(self):
        with pytest.raises(ValueError, match="Malformed voucher"):
            verify_voucher("a.b.c", SECRET)

    def test_rejects_invalid_base64(self):
        with pytest.raises(ValueError, match="Malformed voucher"):
            verify_voucher("!!!invalid!!!.abcdef", SECRET)

    def test_rejects_malformed_payload_fields(self):
        # Payload with wrong number of fields
        payload = "only_one_field"
        payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
        sig = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
        with pytest.raises(ValueError, match="Malformed voucher payload"):
            verify_voucher(f"{payload_b64}.{sig}", SECRET)

    def test_rejects_non_integer_count(self):
        payload = f"cs_test:notanumber:{int(time.time()) + 300}"
        payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
        sig = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
        with pytest.raises(ValueError, match="Malformed voucher payload"):
            verify_voucher(f"{payload_b64}.{sig}", SECRET)


# ---------------------------------------------------------------------------
# VoucherTracker
# ---------------------------------------------------------------------------


class TestVoucherTracker:
    def test_first_call_initializes_counter(self):
        tracker = VoucherTracker()
        assert tracker.try_decrement("cs_a", 3) is True
        assert tracker.remaining("cs_a") == 2

    def test_decrements_to_zero(self):
        tracker = VoucherTracker()
        for _ in range(5):
            assert tracker.try_decrement("cs_b", 5) is True
        assert tracker.remaining("cs_b") == 0

    def test_rejects_after_exhausted(self):
        tracker = VoucherTracker()
        for _ in range(3):
            tracker.try_decrement("cs_c", 3)
        assert tracker.try_decrement("cs_c", 3) is False
        assert tracker.remaining("cs_c") == 0

    def test_sessions_are_isolated(self):
        tracker = VoucherTracker()
        tracker.try_decrement("cs_x", 2)
        tracker.try_decrement("cs_y", 10)
        assert tracker.remaining("cs_x") == 1
        assert tracker.remaining("cs_y") == 9

    def test_unknown_session_remaining_is_zero(self):
        tracker = VoucherTracker()
        assert tracker.remaining("cs_unknown") == 0

    def test_token_count_from_first_call_is_authoritative(self):
        """If try_decrement is called with different counts, first call wins."""
        tracker = VoucherTracker()
        tracker.try_decrement("cs_d", 5)  # Initializes to 5
        tracker.try_decrement("cs_d", 100)  # Ignored — already initialized
        assert tracker.remaining("cs_d") == 3  # 5 - 2 = 3
