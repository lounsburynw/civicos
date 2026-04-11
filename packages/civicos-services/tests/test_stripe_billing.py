"""
Tests for stripe_billing.py — Stripe checkout session creation and webhook
dispatch, including key provisioning on checkout completion, suspension on
subscription cancel, tier updates on subscription change, and payment failure
logging.

External boundaries (the `stripe` SDK, `ApiKeyStore`) are mocked. All dispatch,
argument building, price→tier lookup, fallback, and error branching runs real.

To run:
    pytest packages/civicos-services/tests/test_stripe_billing.py -q --override-ini="addopts="
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import civicos_services.core.stripe_billing as sb
from civicos_services.core.stripe_billing import (
    _get_price_to_tier,
    _get_stripe,
    _handle_checkout_completed,
    _handle_payment_failed,
    _handle_subscription_deleted,
    _handle_subscription_updated,
    create_checkout_session,
    handle_webhook,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_price_to_tier_cache():
    """Reset module-level _PRICE_TO_TIER cache between tests."""
    sb._PRICE_TO_TIER = None
    yield
    sb._PRICE_TO_TIER = None


@pytest.fixture
def fake_stripe():
    """A MagicMock standing in for the stripe SDK with checkout + Webhook namespaces."""
    stripe = MagicMock()
    stripe.api_key = None
    return stripe


@pytest.fixture
def mock_store():
    """Mock ApiKeyStore returned by get_api_key_store()."""
    return MagicMock()


@pytest.fixture
def patched_get_store(mock_store):
    """Patch get_api_key_store in api_keys module (imported lazily inside handlers)."""
    with patch(
        "civicos_services.core.api_keys.get_api_key_store",
        return_value=mock_store,
    ):
        yield mock_store


# ---------------------------------------------------------------------------
# _get_price_to_tier
# ---------------------------------------------------------------------------


class TestGetPriceToTier:
    def test_returns_empty_dict_when_no_env_vars(self, monkeypatch):
        for tier in ("JOURNALIST", "ORGANIZATION", "CITY", "API"):
            monkeypatch.delenv(f"STRIPE_PRICE_{tier}", raising=False)
        assert _get_price_to_tier() == {}

    def test_builds_mapping_for_single_tier(self, monkeypatch):
        for tier in ("JOURNALIST", "ORGANIZATION", "CITY", "API"):
            monkeypatch.delenv(f"STRIPE_PRICE_{tier}", raising=False)
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_j_123")
        result = _get_price_to_tier()
        assert result == {"price_j_123": "journalist"}

    def test_builds_mapping_for_all_four_tiers(self, monkeypatch):
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_j")
        monkeypatch.setenv("STRIPE_PRICE_ORGANIZATION", "price_o")
        monkeypatch.setenv("STRIPE_PRICE_CITY", "price_c")
        monkeypatch.setenv("STRIPE_PRICE_API", "price_a")
        result = _get_price_to_tier()
        assert result == {
            "price_j": "journalist",
            "price_o": "organization",
            "price_c": "city",
            "price_a": "api",
        }

    def test_skips_unset_tiers(self, monkeypatch):
        for tier in ("JOURNALIST", "ORGANIZATION", "CITY", "API"):
            monkeypatch.delenv(f"STRIPE_PRICE_{tier}", raising=False)
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_j")
        monkeypatch.setenv("STRIPE_PRICE_CITY", "price_c")
        result = _get_price_to_tier()
        assert result == {"price_j": "journalist", "price_c": "city"}
        assert "organization" not in result.values()
        assert "api" not in result.values()

    def test_caches_result_across_calls(self, monkeypatch):
        for tier in ("JOURNALIST", "ORGANIZATION", "CITY", "API"):
            monkeypatch.delenv(f"STRIPE_PRICE_{tier}", raising=False)
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_first")
        first = _get_price_to_tier()
        # Change env — cached value should not change
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_second")
        second = _get_price_to_tier()
        assert first is second
        assert second == {"price_first": "journalist"}

    def test_empty_env_var_is_ignored(self, monkeypatch):
        """Empty strings are falsy — should not be added to mapping."""
        for tier in ("JOURNALIST", "ORGANIZATION", "CITY", "API"):
            monkeypatch.delenv(f"STRIPE_PRICE_{tier}", raising=False)
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "")
        monkeypatch.setenv("STRIPE_PRICE_CITY", "price_c")
        result = _get_price_to_tier()
        assert result == {"price_c": "city"}


# ---------------------------------------------------------------------------
# _get_stripe
# ---------------------------------------------------------------------------


class TestGetStripe:
    def test_raises_runtime_error_when_secret_key_missing(self, monkeypatch):
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        # Inject a fake stripe module so `import stripe` succeeds
        fake = MagicMock()
        fake.api_key = None
        monkeypatch.setitem(sys.modules, "stripe", fake)
        with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY not configured"):
            _get_stripe()

    def test_raises_runtime_error_when_secret_key_empty(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "")
        fake = MagicMock()
        fake.api_key = None
        monkeypatch.setitem(sys.modules, "stripe", fake)
        with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY not configured"):
            _get_stripe()

    def test_returns_stripe_with_api_key_set(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xyz")
        fake = MagicMock()
        fake.api_key = None
        monkeypatch.setitem(sys.modules, "stripe", fake)
        result = _get_stripe()
        assert result is fake
        assert result.api_key == "sk_test_xyz"


# ---------------------------------------------------------------------------
# create_checkout_session
# ---------------------------------------------------------------------------


class TestCreateCheckoutSession:
    def test_raises_value_error_for_unconfigured_tier(self, monkeypatch, fake_stripe):
        monkeypatch.delenv("STRIPE_PRICE_JOURNALIST", raising=False)
        with patch.object(sb, "_get_stripe", return_value=fake_stripe):
            with pytest.raises(ValueError, match="No Stripe price configured for tier 'journalist'"):
                create_checkout_session(tier="journalist", email="a@b.com")

    def test_error_message_includes_env_var_hint(self, monkeypatch, fake_stripe):
        monkeypatch.delenv("STRIPE_PRICE_CITY", raising=False)
        with patch.object(sb, "_get_stripe", return_value=fake_stripe):
            with pytest.raises(ValueError, match="STRIPE_PRICE_CITY"):
                create_checkout_session(tier="city", email="a@b.com")

    def test_returns_stripe_session_url(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_j_abc")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            url="https://checkout.stripe.com/c/pay/cs_test_999"
        )
        with patch.object(sb, "_get_stripe", return_value=fake_stripe):
            url = create_checkout_session(tier="journalist", email="reporter@example.com")
        assert url == "https://checkout.stripe.com/c/pay/cs_test_999"

    def test_passes_expected_arguments_to_stripe(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_ORGANIZATION", "price_o_456")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(url="https://x/y")
        with patch.object(sb, "_get_stripe", return_value=fake_stripe):
            create_checkout_session(
                tier="organization",
                email="ops@example.com",
                success_url="https://example.com/ok",
                cancel_url="https://example.com/no",
            )
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["mode"] == "subscription"
        assert kwargs["payment_method_types"] == ["card"]
        assert kwargs["customer_email"] == "ops@example.com"
        assert kwargs["line_items"] == [{"price": "price_o_456", "quantity": 1}]
        assert kwargs["success_url"] == "https://example.com/ok"
        assert kwargs["cancel_url"] == "https://example.com/no"
        assert kwargs["metadata"] == {"tier": "organization"}

    def test_uses_default_success_and_cancel_urls(self, monkeypatch, fake_stripe):
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_j")
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(url="https://x")
        with patch.object(sb, "_get_stripe", return_value=fake_stripe):
            create_checkout_session(tier="journalist", email="a@b.com")
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["success_url"] == "https://civicos.org/billing/success"
        assert kwargs["cancel_url"] == "https://civicos.org/billing/cancel"

    def test_uppercases_tier_when_reading_env_var(self, monkeypatch, fake_stripe):
        """The lookup must use the uppercase form of the tier name."""
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_upper_match")
        # Ensure a lowercase version is NOT set (it wouldn't be anyway)
        monkeypatch.delenv("STRIPE_PRICE_journalist", raising=False)
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(url="https://x")
        with patch.object(sb, "_get_stripe", return_value=fake_stripe):
            create_checkout_session(tier="journalist", email="a@b.com")
        kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["line_items"][0]["price"] == "price_upper_match"


# ---------------------------------------------------------------------------
# handle_webhook — dispatch
# ---------------------------------------------------------------------------


def _make_stripe_with_event(event_type: str, obj: dict) -> MagicMock:
    """Build a fake stripe whose Webhook.construct_event returns the given event."""
    fake = MagicMock()
    fake.Webhook.construct_event.return_value = {
        "type": event_type,
        "data": {"object": obj},
    }
    return fake


class TestHandleWebhook:
    def test_raises_when_webhook_secret_missing(self, monkeypatch):
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        fake_stripe = MagicMock()
        with patch.object(sb, "_get_stripe", return_value=fake_stripe):
            with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET not configured"):
                handle_webhook(b"{}", "sig_xyz")

    def test_passes_payload_signature_and_secret_to_stripe(self, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_deadbeef")
        fake = _make_stripe_with_event("unknown.event", {})
        with patch.object(sb, "_get_stripe", return_value=fake):
            result = handle_webhook(b'{"body": true}', "t=1,v1=abcd")
        # Call-through to stripe SDK uses the exact payload/signature/secret
        fake.Webhook.construct_event.assert_called_once_with(
            b'{"body": true}', "t=1,v1=abcd", "whsec_deadbeef"
        )
        # And the unknown event type is forwarded in the ignored result
        assert result == {"action": "ignored", "event_type": "unknown.event"}

    def test_unknown_event_type_returns_ignored(self, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        fake = _make_stripe_with_event("charge.refunded", {})
        with patch.object(sb, "_get_stripe", return_value=fake):
            result = handle_webhook(b"{}", "sig")
        assert result == {"action": "ignored", "event_type": "charge.refunded"}

    def test_propagates_signature_verification_error(self, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        fake = MagicMock()
        fake.Webhook.construct_event.side_effect = ValueError("Invalid signature")
        with patch.object(sb, "_get_stripe", return_value=fake):
            with pytest.raises(ValueError, match="Invalid signature"):
                handle_webhook(b"{}", "bad_sig")

    def test_dispatches_checkout_completed(self, monkeypatch, patched_get_store):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        patched_get_store.get_key_by_stripe_customer.return_value = None
        patched_get_store.create_key.return_value = ("cvk_dispatch", "cvk_live_dispatch_raw")
        fake = _make_stripe_with_event(
            "checkout.session.completed",
            {
                "customer": "cus_dispatch",
                "customer_email": "user@x.com",
                "subscription": "sub_dispatch",
                "metadata": {"tier": "journalist"},
            },
        )
        with patch.object(sb, "_get_stripe", return_value=fake):
            result = handle_webhook(b"{}", "sig")
        assert result == {
            "action": "key_created",
            "key_id": "cvk_dispatch",
            "tier": "journalist",
            "email": "user@x.com",
        }

    def test_dispatches_subscription_deleted(self, monkeypatch, patched_get_store):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        patched_get_store.get_key_by_stripe_customer.return_value = {"key_id": "cvk_del"}
        fake = _make_stripe_with_event(
            "customer.subscription.deleted", {"customer": "cus_del"}
        )
        with patch.object(sb, "_get_stripe", return_value=fake):
            result = handle_webhook(b"{}", "sig")
        assert result == {"action": "key_suspended", "key_id": "cvk_del"}
        patched_get_store.suspend_key.assert_called_once_with("cvk_del")

    def test_dispatches_subscription_updated(self, monkeypatch, patched_get_store):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        patched_get_store.get_key_by_stripe_customer.return_value = None
        fake = _make_stripe_with_event(
            "customer.subscription.updated", {"customer": "cus_up"}
        )
        with patch.object(sb, "_get_stripe", return_value=fake):
            result = handle_webhook(b"{}", "sig")
        assert result == {"action": "no_key_found", "customer_id": "cus_up"}

    def test_dispatches_payment_failed(self, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        fake = _make_stripe_with_event(
            "invoice.payment_failed",
            {"customer": "cus_fail", "id": "in_001"},
        )
        with patch.object(sb, "_get_stripe", return_value=fake):
            result = handle_webhook(b"{}", "sig")
        assert result == {"action": "payment_failed_logged", "customer_id": "cus_fail"}


# ---------------------------------------------------------------------------
# _handle_checkout_completed
# ---------------------------------------------------------------------------


class TestHandleCheckoutCompleted:
    def test_creates_new_key_when_no_existing_customer(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        patched_get_store.create_key.return_value = ("cvk_new123", "cvk_live_raw")
        session = {
            "customer": "cus_new",
            "customer_email": "alice@example.com",
            "subscription": "sub_new",
            "metadata": {"tier": "organization"},
        }
        result = _handle_checkout_completed(session)
        assert result == {
            "action": "key_created",
            "key_id": "cvk_new123",
            "tier": "organization",
            "email": "alice@example.com",
        }
        patched_get_store.create_key.assert_called_once_with(
            name="alice",
            email="alice@example.com",
            tier="organization",
            stripe_customer_id="cus_new",
            stripe_subscription_id="sub_new",
        )

    def test_reactivates_when_customer_already_has_key(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = {"key_id": "cvk_existing"}
        session = {
            "customer": "cus_existing",
            "customer_email": "bob@example.com",
            "subscription": "sub_updated",
            "metadata": {"tier": "city"},
        }
        result = _handle_checkout_completed(session)
        assert result == {
            "action": "reactivated",
            "key_id": "cvk_existing",
            "tier": "city",
        }
        patched_get_store.update_key_stripe.assert_called_once_with(
            "cvk_existing",
            stripe_subscription_id="sub_updated",
            tier="city",
        )
        patched_get_store._set_status.assert_called_once_with("cvk_existing", "active")
        # New key should NOT be created
        patched_get_store.create_key.assert_not_called()

    def test_falls_back_to_customer_details_email(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        patched_get_store.create_key.return_value = ("cvk_fb", "cvk_live_fb")
        session = {
            "customer": "cus_fb",
            "customer_email": None,
            "customer_details": {"email": "fallback@example.com"},
            "subscription": "sub_fb",
            "metadata": {"tier": "journalist"},
        }
        result = _handle_checkout_completed(session)
        assert result["email"] == "fallback@example.com"
        assert patched_get_store.create_key.call_args.kwargs["email"] == "fallback@example.com"
        assert patched_get_store.create_key.call_args.kwargs["name"] == "fallback"

    def test_defaults_tier_to_journalist_when_metadata_missing(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        patched_get_store.create_key.return_value = ("cvk_def", "cvk_live_def")
        session = {
            "customer": "cus_def",
            "customer_email": "user@example.com",
            "subscription": "sub_def",
            # No metadata key
        }
        result = _handle_checkout_completed(session)
        assert result["tier"] == "journalist"
        assert patched_get_store.create_key.call_args.kwargs["tier"] == "journalist"

    def test_defaults_tier_when_metadata_tier_absent(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        patched_get_store.create_key.return_value = ("cvk_def2", "cvk_live_def2")
        session = {
            "customer": "cus_def2",
            "customer_email": "user@example.com",
            "subscription": "sub_def2",
            "metadata": {"other": "value"},  # missing "tier"
        }
        result = _handle_checkout_completed(session)
        assert result["tier"] == "journalist"

    def test_uses_customer_as_name_when_email_empty(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        patched_get_store.create_key.return_value = ("cvk_empty", "cvk_live_empty")
        session = {
            "customer": "cus_empty",
            "customer_email": "",
            "customer_details": {"email": ""},
            "subscription": "sub_empty",
            "metadata": {"tier": "journalist"},
        }
        _handle_checkout_completed(session)
        # With empty email, name falls back to "Customer"
        assert patched_get_store.create_key.call_args.kwargs["name"] == "Customer"

    def test_derives_name_from_email_prefix(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        patched_get_store.create_key.return_value = ("cvk_prefix", "cvk_live_prefix")
        session = {
            "customer": "cus_prefix",
            "customer_email": "jane.doe@civicos.org",
            "subscription": "sub_prefix",
            "metadata": {"tier": "journalist"},
        }
        _handle_checkout_completed(session)
        assert patched_get_store.create_key.call_args.kwargs["name"] == "jane.doe"

    def test_returns_failure_when_create_key_returns_none(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        patched_get_store.create_key.return_value = None
        session = {
            "customer": "cus_fail",
            "customer_email": "fail@example.com",
            "subscription": "sub_fail",
            "metadata": {"tier": "journalist"},
        }
        result = _handle_checkout_completed(session)
        assert result == {"action": "key_creation_failed", "customer_id": "cus_fail"}


# ---------------------------------------------------------------------------
# _handle_subscription_deleted
# ---------------------------------------------------------------------------


class TestHandleSubscriptionDeleted:
    def test_suspends_existing_key(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = {"key_id": "cvk_sus"}
        result = _handle_subscription_deleted({"customer": "cus_sus"})
        assert result == {"action": "key_suspended", "key_id": "cvk_sus"}
        patched_get_store.suspend_key.assert_called_once_with("cvk_sus")

    def test_returns_no_key_found_when_customer_unknown(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        result = _handle_subscription_deleted({"customer": "cus_ghost"})
        assert result == {"action": "no_key_found", "customer_id": "cus_ghost"}
        patched_get_store.suspend_key.assert_not_called()

    def test_handles_missing_customer_field(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        result = _handle_subscription_deleted({})
        assert result == {"action": "no_key_found", "customer_id": None}


# ---------------------------------------------------------------------------
# _handle_subscription_updated
# ---------------------------------------------------------------------------


class TestHandleSubscriptionUpdated:
    def test_returns_no_key_found_when_customer_unknown(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = None
        result = _handle_subscription_updated({"customer": "cus_ghost"})
        assert result == {"action": "no_key_found", "customer_id": "cus_ghost"}
        patched_get_store.update_key_stripe.assert_not_called()

    def test_updates_tier_when_price_changed(self, monkeypatch, patched_get_store):
        monkeypatch.setenv("STRIPE_PRICE_CITY", "price_city_new")
        patched_get_store.get_key_by_stripe_customer.return_value = {
            "key_id": "cvk_change",
            "tier": "journalist",
        }
        subscription = {
            "customer": "cus_change",
            "items": {"data": [{"price": {"id": "price_city_new"}}]},
        }
        result = _handle_subscription_updated(subscription)
        assert result == {
            "action": "tier_updated",
            "key_id": "cvk_change",
            "new_tier": "city",
        }
        patched_get_store.update_key_stripe.assert_called_once_with(
            "cvk_change", tier="city"
        )

    def test_no_change_when_new_tier_matches_existing(self, monkeypatch, patched_get_store):
        monkeypatch.setenv("STRIPE_PRICE_JOURNALIST", "price_j_same")
        patched_get_store.get_key_by_stripe_customer.return_value = {
            "key_id": "cvk_same",
            "tier": "journalist",
        }
        subscription = {
            "customer": "cus_same",
            "items": {"data": [{"price": {"id": "price_j_same"}}]},
        }
        result = _handle_subscription_updated(subscription)
        assert result == {"action": "no_change", "key_id": "cvk_same"}
        patched_get_store.update_key_stripe.assert_not_called()

    def test_no_change_when_price_not_in_mapping(self, monkeypatch, patched_get_store):
        for tier in ("JOURNALIST", "ORGANIZATION", "CITY", "API"):
            monkeypatch.delenv(f"STRIPE_PRICE_{tier}", raising=False)
        patched_get_store.get_key_by_stripe_customer.return_value = {
            "key_id": "cvk_unk",
            "tier": "journalist",
        }
        subscription = {
            "customer": "cus_unk",
            "items": {"data": [{"price": {"id": "price_unknown_xyz"}}]},
        }
        result = _handle_subscription_updated(subscription)
        assert result == {"action": "no_change", "key_id": "cvk_unk"}
        patched_get_store.update_key_stripe.assert_not_called()

    def test_no_change_when_items_list_empty(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = {
            "key_id": "cvk_empty",
            "tier": "journalist",
        }
        subscription = {"customer": "cus_empty", "items": {"data": []}}
        result = _handle_subscription_updated(subscription)
        assert result == {"action": "no_change", "key_id": "cvk_empty"}
        patched_get_store.update_key_stripe.assert_not_called()

    def test_no_change_when_items_key_missing(self, patched_get_store):
        patched_get_store.get_key_by_stripe_customer.return_value = {
            "key_id": "cvk_none",
            "tier": "journalist",
        }
        subscription = {"customer": "cus_none"}
        result = _handle_subscription_updated(subscription)
        assert result == {"action": "no_change", "key_id": "cvk_none"}

    def test_uses_first_item_for_tier_lookup(self, monkeypatch, patched_get_store):
        """Only the first item in data[] is consulted."""
        monkeypatch.setenv("STRIPE_PRICE_ORGANIZATION", "price_o_first")
        patched_get_store.get_key_by_stripe_customer.return_value = {
            "key_id": "cvk_multi",
            "tier": "journalist",
        }
        subscription = {
            "customer": "cus_multi",
            "items": {
                "data": [
                    {"price": {"id": "price_o_first"}},
                    {"price": {"id": "price_j_second"}},
                ]
            },
        }
        result = _handle_subscription_updated(subscription)
        assert result["new_tier"] == "organization"


# ---------------------------------------------------------------------------
# _handle_payment_failed
# ---------------------------------------------------------------------------


class TestHandlePaymentFailed:
    def test_returns_logged_action_with_customer_id(self):
        invoice = {"customer": "cus_pf", "id": "in_pf_001"}
        result = _handle_payment_failed(invoice)
        assert result == {"action": "payment_failed_logged", "customer_id": "cus_pf"}

    def test_returns_none_customer_when_missing(self):
        result = _handle_payment_failed({"id": "in_only"})
        assert result == {"action": "payment_failed_logged", "customer_id": None}

    def test_logs_warning_with_customer_and_invoice_ids(self, caplog):
        import logging
        caplog.set_level(logging.WARNING, logger="civicos_services.core.stripe_billing")
        _handle_payment_failed({"customer": "cus_log", "id": "in_log_42"})
        # The warning message should mention both IDs so ops can follow up
        assert any("cus_log" in rec.getMessage() for rec in caplog.records)
        assert any("in_log_42" in rec.getMessage() for rec in caplog.records)
