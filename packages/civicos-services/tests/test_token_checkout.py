"""
Tests for token_checkout.py — Stripe one-time payment sessions for blinded
token bundles with claim_secret auth and Stripe-backed claim tracking.

External boundary (Stripe SDK) is mocked. All argument building, status
mapping, claim_secret verification, env var lookup, and error branching
runs real.

To run:
    pytest packages/civicos-services/tests/test_token_checkout.py -q --override-ini="addopts="
"""

import hashlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

import civicos_services.core.token_checkout as tc
from civicos_services.core.token_checkout import (
    _configure_stripe,
    _get_session_attr,
    create_token_checkout,
    check_token_checkout_status,
    get_bundle_size,
    mark_claimed,
    _get_success_url,
    _get_cancel_url,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_stripe():
    """Patch the stripe module imported at module level."""
    fake = MagicMock()
    fake.api_key = None
    # Provide the error submodule for specific exception handling
    fake.error = MagicMock()
    fake.error.InvalidRequestError = type("InvalidRequestError", (Exception,), {})
    with patch.object(tc, "stripe", fake):
        yield fake


# ---------------------------------------------------------------------------
# _configure_stripe
# ---------------------------------------------------------------------------


class TestConfigureStripe:
    def test_raises_when_secret_key_missing(self, monkeypatch, fake_stripe):
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY not configured"):
            _configure_stripe()

    def test_raises_when_secret_key_empty(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "")
        with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY not configured"):
            _configure_stripe()

    def test_sets_api_key_on_stripe(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        _configure_stripe()
        assert fake_stripe.api_key == "sk_test_abc"


# ---------------------------------------------------------------------------
# _get_session_attr
# ---------------------------------------------------------------------------


class TestGetSessionAttr:
    def test_dict_access(self):
        session = {"payment_status": "paid", "status": "complete"}
        assert _get_session_attr(session, "payment_status") == "paid"
        assert _get_session_attr(session, "status") == "complete"

    def test_dict_default(self):
        assert _get_session_attr({}, "missing", "fallback") == "fallback"

    def test_object_access(self):
        session = SimpleNamespace(payment_status="unpaid", status="open")
        assert _get_session_attr(session, "payment_status") == "unpaid"
        assert _get_session_attr(session, "status") == "open"

    def test_object_default(self):
        session = SimpleNamespace()
        assert _get_session_attr(session, "missing", "default") == "default"


# ---------------------------------------------------------------------------
# get_bundle_size
# ---------------------------------------------------------------------------


class TestGetBundleSize:
    def test_default_bundle_size(self, monkeypatch):
        monkeypatch.delenv("CIVICOS_TOKEN_BUNDLE_SIZE", raising=False)
        assert get_bundle_size() == 50

    def test_custom_bundle_size(self, monkeypatch):
        monkeypatch.setenv("CIVICOS_TOKEN_BUNDLE_SIZE", "100")
        assert get_bundle_size() == 100


# ---------------------------------------------------------------------------
# URL config
# ---------------------------------------------------------------------------


class TestURLConfig:
    def test_success_url_default(self, monkeypatch):
        monkeypatch.delenv("CIVICOS_TOKEN_SUCCESS_URL", raising=False)
        assert _get_success_url() == "https://civicos.org/tokens/success"

    def test_success_url_from_env(self, monkeypatch):
        monkeypatch.setenv("CIVICOS_TOKEN_SUCCESS_URL", "https://my.app/ok")
        assert _get_success_url() == "https://my.app/ok"

    def test_cancel_url_default(self, monkeypatch):
        monkeypatch.delenv("CIVICOS_TOKEN_CANCEL_URL", raising=False)
        assert _get_cancel_url() == "https://civicos.org/tokens/cancel"

    def test_cancel_url_from_env(self, monkeypatch):
        monkeypatch.setenv("CIVICOS_TOKEN_CANCEL_URL", "https://my.app/no")
        assert _get_cancel_url() == "https://my.app/no"


# ---------------------------------------------------------------------------
# create_token_checkout
# ---------------------------------------------------------------------------


class TestCreateTokenCheckout:
    def test_raises_when_price_not_configured(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.delenv("STRIPE_PRICE_TOKENS", raising=False)
        with pytest.raises(ValueError, match="STRIPE_PRICE_TOKENS"):
            create_token_checkout()

    def test_returns_checkout_url_session_id_and_claim_secret(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://checkout.stripe.com/c/pay/cs_test_tok",
            id="cs_test_tok",
        )
        result = create_token_checkout()
        assert result["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_tok"
        assert result["session_id"] == "cs_test_tok"
        assert result["token_count"] == 50  # default bundle
        assert "claim_secret" in result
        assert len(result["claim_secret"]) > 20  # urlsafe token

    def test_uses_payment_mode_not_subscription(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        result = create_token_checkout()
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["mode"] == "payment"
        assert result["session_id"] == "cs_x"
        assert result["checkout_url"] == "https://x"

    def test_includes_token_metadata_and_claim_hash(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        result = create_token_checkout(count=25)
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["metadata"]["type"] == "token_purchase"
        assert kwargs["metadata"]["token_count"] == "25"
        assert kwargs["metadata"]["claimed"] == "false"
        assert "claim_secret_hash" in kwargs["metadata"]
        # Verify hash matches the returned secret
        expected_hash = hashlib.sha256(result["claim_secret"].encode()).hexdigest()
        assert kwargs["metadata"]["claim_secret_hash"] == expected_hash
        assert result["token_count"] == 25

    def test_custom_count_overrides_bundle_size(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        result = create_token_checkout(count=25)
        assert result["token_count"] == 25

    def test_custom_bundle_size_from_env(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        monkeypatch.setenv("CIVICOS_TOKEN_BUNDLE_SIZE", "100")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        result = create_token_checkout()
        assert result["token_count"] == 100

    def test_passes_env_urls_when_none_provided(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        monkeypatch.setenv("CIVICOS_TOKEN_SUCCESS_URL", "https://env.success")
        monkeypatch.setenv("CIVICOS_TOKEN_CANCEL_URL", "https://env.cancel")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        result = create_token_checkout()
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["success_url"] == "https://env.success"
        assert kwargs["cancel_url"] == "https://env.cancel"
        assert result["session_id"] == "cs_x"

    def test_explicit_urls_override_env(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        monkeypatch.setenv("CIVICOS_TOKEN_SUCCESS_URL", "https://env.success")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        result = create_token_checkout(success_url="https://explicit.success")
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["success_url"] == "https://explicit.success"
        assert result["checkout_url"] == "https://x"


# ---------------------------------------------------------------------------
# check_token_checkout_status
# ---------------------------------------------------------------------------


VALID_SECRET = "test_claim_secret_abc"
VALID_SECRET_HASH = hashlib.sha256(VALID_SECRET.encode()).hexdigest()


class TestCheckTokenCheckoutStatus:
    def _make_session(self, payment_status="unpaid", status="open", metadata=None):
        return SimpleNamespace(
            payment_status=payment_status,
            status=status,
            metadata=metadata or {
                "type": "token_purchase",
                "token_count": "50",
                "claim_secret_hash": VALID_SECRET_HASH,
                "claimed": "false",
            },
        )

    def test_returns_pending_for_unpaid(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session()
        result = check_token_checkout_status("cs_test_123", VALID_SECRET)
        assert result["status"] == "pending"
        assert result["token_count"] == 50
        assert result["claimed"] is False
        assert result["voucher"] is None  # No voucher for pending

    def test_returns_paid_with_voucher_when_configured(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "test_hmac_secret")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            payment_status="paid", status="complete"
        )
        result = check_token_checkout_status("cs_test_voucher", VALID_SECRET)
        assert result["status"] == "paid"
        assert result["voucher"] is not None
        assert "." in result["voucher"]  # payload.signature format

    def test_returns_paid_without_voucher_when_not_configured(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.delenv("VOUCHER_HMAC_SECRET", raising=False)
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            payment_status="paid", status="complete"
        )
        result = check_token_checkout_status("cs_test_no_voucher", VALID_SECRET)
        assert result["status"] == "paid"
        assert result["voucher"] is None

    def test_no_voucher_for_already_claimed(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("VOUCHER_HMAC_SECRET", "test_hmac_secret")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            payment_status="paid", status="complete",
            metadata={
                "type": "token_purchase",
                "token_count": "50",
                "claim_secret_hash": VALID_SECRET_HASH,
                "claimed": "true",
            },
        )
        result = check_token_checkout_status("cs_claimed", VALID_SECRET)
        assert result["claimed"] is True
        assert result["voucher"] is None

    def test_returns_paid_when_payment_status_paid(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            payment_status="paid", status="complete"
        )
        result = check_token_checkout_status("cs_test_paid", VALID_SECRET)
        assert result["status"] == "paid"

    def test_returns_expired_when_session_expired(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            status="expired"
        )
        result = check_token_checkout_status("cs_test_exp", VALID_SECRET)
        assert result["status"] == "expired"

    def test_reads_token_count_from_metadata(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            metadata={
                "type": "token_purchase",
                "token_count": "25",
                "claim_secret_hash": VALID_SECRET_HASH,
                "claimed": "false",
            }
        )
        result = check_token_checkout_status("cs_test_25", VALID_SECRET)
        assert result["token_count"] == 25

    def test_rejects_non_token_purchase_session(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            metadata={"type": "subscription", "tier": "journalist",
                      "claim_secret_hash": VALID_SECRET_HASH}
        )
        with pytest.raises(ValueError, match="not a token purchase"):
            check_token_checkout_status("cs_test_wrong", VALID_SECRET)

    def test_rejects_invalid_claim_secret(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session()
        with pytest.raises(ValueError, match="Invalid claim secret"):
            check_token_checkout_status("cs_test_123", "wrong_secret")

    def test_rejects_empty_claim_secret_hash(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            metadata={
                "type": "token_purchase",
                "token_count": "50",
                "claim_secret_hash": "",
                "claimed": "false",
            }
        )
        with pytest.raises(ValueError, match="Invalid claim secret"):
            check_token_checkout_status("cs_test_empty", VALID_SECRET)

    def test_raises_on_retrieve_failure(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.side_effect = (
            fake_stripe.error.InvalidRequestError("not found")
        )
        with pytest.raises(ValueError, match="Could not retrieve"):
            check_token_checkout_status("cs_test_bad", VALID_SECRET)

    def test_claimed_flag_from_metadata(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            payment_status="paid",
            status="complete",
            metadata={
                "type": "token_purchase",
                "token_count": "50",
                "claim_secret_hash": VALID_SECRET_HASH,
                "claimed": "true",
            },
        )
        result = check_token_checkout_status("cs_claimed", VALID_SECRET)
        assert result["claimed"] is True


# ---------------------------------------------------------------------------
# mark_claimed
# ---------------------------------------------------------------------------


class TestMarkClaimed:
    def test_persists_claimed_flag_in_stripe_metadata(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        result = mark_claimed("cs_mark")
        assert result is None  # void function completes without error
        fake_stripe.checkout.Session.modify.assert_called_once_with(
            "cs_mark", metadata={"claimed": "true"}
        )

    def test_idempotent_across_multiple_calls(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
        result1 = mark_claimed("cs_idem")
        result2 = mark_claimed("cs_idem")
        assert result1 is None
        assert result2 is None
        assert fake_stripe.checkout.Session.modify.call_count == 2
        # Both calls target the same session with the same metadata
        for c in fake_stripe.checkout.Session.modify.call_args_list:
            assert c == call("cs_idem", metadata={"claimed": "true"})
