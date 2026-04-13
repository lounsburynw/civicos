"""
Tests for voucher.py — HMAC-SHA256 voucher generation for token issuance.

To run:
    pytest packages/civicos-services/tests/test_voucher.py -q --override-ini="addopts="
"""

import base64
import hashlib
import hmac
import time
from unittest.mock import patch

import pytest

import civicos_services.core.voucher as v
from civicos_services.core.voucher import generate_voucher, _get_hmac_secret


class TestGetHmacSecret:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("VOUCHER_HMAC_SECRET", raising=False)
        with pytest.raises(RuntimeError, match="VOUCHER_HMAC_SECRET not configured"):
            _get_hmac_secret()

    def test_raises_when_empty(self, monkeypatch):
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "")
        with pytest.raises(RuntimeError, match="VOUCHER_HMAC_SECRET not configured"):
            _get_hmac_secret()

    def test_returns_encoded_secret(self, monkeypatch):
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "test_secret_123")
        result = _get_hmac_secret()
        assert result == b"test_secret_123"


class TestGenerateVoucher:
    def test_produces_two_part_format(self, monkeypatch):
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "test_secret")
        voucher = generate_voucher("cs_test_abc", 50)
        parts = voucher.split(".")
        assert len(parts) == 2

    def test_payload_contains_session_id_and_count(self, monkeypatch):
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "test_secret")
        voucher = generate_voucher("cs_session_xyz", 25)
        payload_b64 = voucher.split(".")[0]
        payload = base64.urlsafe_b64decode(payload_b64).decode()
        fields = payload.split(":")
        assert fields[0] == "cs_session_xyz"
        assert fields[1] == "25"
        assert int(fields[2]) > int(time.time())  # expires in the future

    def test_expiry_respects_ttl(self, monkeypatch):
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "test_secret")
        before = int(time.time())
        voucher = generate_voucher("cs_test", 10, ttl_seconds=600)
        payload_b64 = voucher.split(".")[0]
        payload = base64.urlsafe_b64decode(payload_b64).decode()
        expires_at = int(payload.split(":")[2])
        # Should be ~600s from now
        assert expires_at >= before + 599
        assert expires_at <= before + 602

    def test_hmac_signature_is_valid(self, monkeypatch):
        secret = "my_hmac_key"
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", secret)
        voucher = generate_voucher("cs_test", 50)
        payload_b64, provided_sig = voucher.split(".")
        payload = base64.urlsafe_b64decode(payload_b64).decode()
        expected_sig = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        assert hmac.compare_digest(provided_sig, expected_sig)

    def test_different_secrets_produce_different_signatures(self, monkeypatch):
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "secret_a")
        v1 = generate_voucher("cs_test", 50)

        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "secret_b")
        v2 = generate_voucher("cs_test", 50)

        sig1 = v1.split(".")[1]
        sig2 = v2.split(".")[1]
        assert sig1 != sig2

    def test_different_sessions_produce_different_payloads(self, monkeypatch):
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "test_secret")
        v1 = generate_voucher("cs_aaa", 50)
        v2 = generate_voucher("cs_bbb", 50)
        p1 = v1.split(".")[0]
        p2 = v2.split(".")[0]
        assert p1 != p2
