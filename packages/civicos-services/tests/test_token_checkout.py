"""
Tests for token_checkout.py — Stripe one-time payment sessions for blinded
token bundles.

External boundary (Stripe SDK) is mocked. All argument building, status
mapping, double-claim guard, env var lookup, and error branching runs real.

To run:
    pytest packages/civicos-services/tests/test_token_checkout.py -q --override-ini="addopts="
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import civicos_services.core.token_checkout as tc
from civicos_services.core.token_checkout import (
    _get_stripe,
    create_token_checkout,
    check_token_checkout_status,
    get_bundle_size,
    mark_claimed,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_claimed_sessions():
    """Clear the in-memory claimed sessions set between tests."""
    tc._claimed_sessions.clear()
    yield
    tc._claimed_sessions.clear()


@pytest.fixture
def fake_stripe():
    """A MagicMock standing in for the stripe SDK."""
    stripe = MagicMock()
    stripe.api_key = None
    return stripe


# ---------------------------------------------------------------------------
# _get_stripe
# ---------------------------------------------------------------------------


class TestGetStripe:
    def test_raises_when_secret_key_missing(self, monkeypatch):
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        fake = MagicMock()
        fake.api_key = None
        monkeypatch.setitem(sys.modules, "stripe", fake)
        with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY not configured"):
            _get_stripe()

    def test_returns_stripe_with_key_set(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        fake = MagicMock()
        fake.api_key = None
        monkeypatch.setitem(sys.modules, "stripe", fake)
        result = _get_stripe()
        assert result is fake
        assert result.api_key == "sk_test_abc"


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
# create_token_checkout
# ---------------------------------------------------------------------------


class TestCreateTokenCheckout:
    def test_raises_when_price_not_configured(self, monkeypatch, fake_stripe):
        monkeypatch.delenv("STRIPE_PRICE_TOKENS", raising=False)
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            with pytest.raises(ValueError, match="STRIPE_PRICE_TOKENS"):
                create_token_checkout()

    def test_returns_checkout_url_and_session_id(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://checkout.stripe.com/c/pay/cs_test_tok",
            id="cs_test_tok",
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            result = create_token_checkout()
        assert result["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_tok"
        assert result["session_id"] == "cs_test_tok"
        assert result["token_count"] == 50  # default bundle

    def test_uses_payment_mode_not_subscription(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            create_token_checkout()
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["mode"] == "payment"

    def test_includes_token_metadata(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            create_token_checkout(count=25)
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["metadata"]["type"] == "token_purchase"
        assert kwargs["metadata"]["token_count"] == "25"

    def test_custom_count_overrides_bundle_size(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            result = create_token_checkout(count=25)
        assert result["token_count"] == 25

    def test_custom_bundle_size_from_env(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        monkeypatch.setenv("CIVICOS_TOKEN_BUNDLE_SIZE", "100")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            result = create_token_checkout()  # no explicit count
        assert result["token_count"] == 100

    def test_passes_success_and_cancel_urls(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_TOKENS", "price_tok_123")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://x", id="cs_x"
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            create_token_checkout(
                success_url="https://my.app/ok",
                cancel_url="https://my.app/no",
            )
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["success_url"] == "https://my.app/ok"
        assert kwargs["cancel_url"] == "https://my.app/no"


# ---------------------------------------------------------------------------
# check_token_checkout_status
# ---------------------------------------------------------------------------


class TestCheckTokenCheckoutStatus:
    def _make_session(self, payment_status="unpaid", status="open", metadata=None):
        return SimpleNamespace(
            payment_status=payment_status,
            status=status,
            metadata=metadata or {"type": "token_purchase", "token_count": "50"},
        )

    def test_returns_pending_for_unpaid(self, monkeypatch, fake_stripe):
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session()
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            result = check_token_checkout_status("cs_test_123")
        assert result["status"] == "pending"
        assert result["token_count"] == 50
        assert result["claimed"] is False

    def test_returns_paid_when_payment_status_paid(self, monkeypatch, fake_stripe):
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            payment_status="paid", status="complete"
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            result = check_token_checkout_status("cs_test_paid")
        assert result["status"] == "paid"

    def test_returns_expired_when_session_expired(self, monkeypatch, fake_stripe):
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            status="expired"
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            result = check_token_checkout_status("cs_test_exp")
        assert result["status"] == "expired"

    def test_reads_token_count_from_metadata(self, monkeypatch, fake_stripe):
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            metadata={"type": "token_purchase", "token_count": "25"}
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            result = check_token_checkout_status("cs_test_25")
        assert result["token_count"] == 25

    def test_rejects_non_token_purchase_session(self, monkeypatch, fake_stripe):
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            metadata={"type": "subscription", "tier": "journalist"}
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            with pytest.raises(ValueError, match="not a token purchase"):
                check_token_checkout_status("cs_test_wrong")

    def test_raises_on_retrieve_failure(self, monkeypatch, fake_stripe):
        fake_stripe.checkout.Session.retrieve.side_effect = Exception("network error")
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            with pytest.raises(ValueError, match="Could not retrieve"):
                check_token_checkout_status("cs_test_bad")

    def test_claimed_flag_reflects_claimed_sessions(self, monkeypatch, fake_stripe):
        fake_stripe.checkout.Session.retrieve.return_value = self._make_session(
            payment_status="paid", status="complete"
        )
        with patch.object(tc, "_get_stripe", return_value=fake_stripe):
            # Not yet claimed
            result1 = check_token_checkout_status("cs_claim_test")
            assert result1["claimed"] is False

            # Mark claimed
            mark_claimed("cs_claim_test")

            # Now claimed
            result2 = check_token_checkout_status("cs_claim_test")
            assert result2["claimed"] is True


# ---------------------------------------------------------------------------
# mark_claimed
# ---------------------------------------------------------------------------


class TestMarkClaimed:
    def test_adds_session_to_claimed_set(self):
        assert "cs_new" not in tc._claimed_sessions
        mark_claimed("cs_new")
        assert "cs_new" in tc._claimed_sessions

    def test_idempotent(self):
        mark_claimed("cs_idem")
        mark_claimed("cs_idem")
        assert "cs_idem" in tc._claimed_sessions
