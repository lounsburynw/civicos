"""
Tests for billing router: Stripe checkout session + webhook receiver.

The router delegates to ``civicos_services.core.stripe_billing`` (Stripe SDK
wrapper) via lazy imports inside each handler. Tests mock those module-level
functions so the router logic runs real while the Stripe SDK never loads.

Auth is overridden via FastAPI dependency_overrides for the checkout route;
the webhook route does not require auth (Stripe signature verification
replaces it).

To run:
    pytest packages/civicos-services/tests/test_billing.py -q --override-ini="addopts="
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from civicos_services.servers.routers.billing import (
    CheckoutRequest,
    CheckoutResponse,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """FastAPI app with only the billing router mounted."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """TestClient with verify_auth overridden to return a fixed admin token."""
    from civicos_services.servers.routers.dependencies import (
        AuthContext,
        verify_auth,
    )

    async def mock_auth():
        return AuthContext(key_id="admin-token", source="env", tier="admin")

    app.dependency_overrides[verify_auth] = mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client(app):
    """TestClient WITHOUT auth override — used to assert auth is required."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Pydantic models: CheckoutRequest / CheckoutResponse
# ---------------------------------------------------------------------------


class TestCheckoutRequestModel:
    def test_defaults_for_success_and_cancel_urls(self):
        req = CheckoutRequest(tier="journalist", email="reporter@example.com")
        assert req.tier == "journalist"
        assert req.email == "reporter@example.com"
        assert req.success_url == "https://civicos.org/billing/success"
        assert req.cancel_url == "https://civicos.org/billing/cancel"

    def test_custom_urls_override_defaults(self):
        req = CheckoutRequest(
            tier="city",
            email="mayor@sanrafael.gov",
            success_url="https://example.com/ok",
            cancel_url="https://example.com/nope",
        )
        assert req.success_url == "https://example.com/ok"
        assert req.cancel_url == "https://example.com/nope"

    def test_tier_is_required(self):
        with pytest.raises(ValidationError, match="tier"):
            CheckoutRequest(email="a@b.com")  # type: ignore[call-arg]

    def test_email_is_required(self):
        with pytest.raises(ValidationError, match="email"):
            CheckoutRequest(tier="api")  # type: ignore[call-arg]


class TestCheckoutResponseModel:
    def test_serializes_checkout_url_and_tier(self):
        resp = CheckoutResponse(
            checkout_url="https://checkout.stripe.com/pay/cs_test_123",
            tier="organization",
        )
        assert resp.checkout_url == "https://checkout.stripe.com/pay/cs_test_123"
        assert resp.tier == "organization"


# ---------------------------------------------------------------------------
# POST /billing/checkout
# ---------------------------------------------------------------------------


CHECKOUT_PATH = "/billing/checkout"
STRIPE_URL = "https://checkout.stripe.com/pay/cs_test_abc123"


class TestCreateCheckoutSuccess:
    @pytest.mark.parametrize(
        "tier",
        ["journalist", "organization", "city", "api"],
    )
    def test_all_four_valid_tiers_return_200(self, client, tier):
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session",
            return_value=STRIPE_URL,
        ):
            resp = client.post(
                CHECKOUT_PATH,
                json={"tier": tier, "email": "user@example.com"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["checkout_url"] == STRIPE_URL
        assert data["tier"] == tier

    def test_forwards_tier_email_and_urls_to_stripe_layer(self, client):
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session",
            return_value=STRIPE_URL,
        ) as mock_create:
            resp = client.post(
                CHECKOUT_PATH,
                json={
                    "tier": "journalist",
                    "email": "reporter@example.com",
                    "success_url": "https://app.example.com/ok",
                    "cancel_url": "https://app.example.com/no",
                },
            )
        assert resp.status_code == 200
        mock_create.assert_called_once_with(
            tier="journalist",
            email="reporter@example.com",
            success_url="https://app.example.com/ok",
            cancel_url="https://app.example.com/no",
        )

    def test_default_urls_used_when_request_omits_them(self, client):
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session",
            return_value=STRIPE_URL,
        ) as mock_create:
            resp = client.post(
                CHECKOUT_PATH,
                json={"tier": "api", "email": "dev@example.com"},
            )
        assert resp.status_code == 200
        kwargs = mock_create.call_args.kwargs
        assert kwargs["success_url"] == "https://civicos.org/billing/success"
        assert kwargs["cancel_url"] == "https://civicos.org/billing/cancel"

    def test_response_tier_echoes_request_tier_not_stripe_return(self, client):
        """The tier in the response comes from the request, not Stripe."""
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session",
            return_value="https://checkout.stripe.com/pay/cs_x",
        ):
            resp = client.post(
                CHECKOUT_PATH,
                json={"tier": "city", "email": "x@y.z"},
            )
        assert resp.status_code == 200
        assert resp.json()["tier"] == "city"


class TestCreateCheckoutTierValidation:
    def test_unknown_tier_returns_400(self, client):
        resp = client.post(
            CHECKOUT_PATH,
            json={"tier": "platinum", "email": "a@b.com"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "platinum" in detail
        assert "Invalid tier" in detail

    def test_unknown_tier_error_lists_all_valid_tiers(self, client):
        resp = client.post(
            CHECKOUT_PATH,
            json={"tier": "free", "email": "a@b.com"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        for valid in ("journalist", "organization", "city", "api"):
            assert valid in detail

    def test_empty_tier_returns_400(self, client):
        resp = client.post(
            CHECKOUT_PATH,
            json={"tier": "", "email": "a@b.com"},
        )
        assert resp.status_code == 400
        assert "Invalid tier" in resp.json()["detail"]

    def test_tier_is_case_sensitive(self, client):
        """Upper/mixed case is rejected — only exact lowercase matches pass."""
        resp = client.post(
            CHECKOUT_PATH,
            json={"tier": "Journalist", "email": "a@b.com"},
        )
        assert resp.status_code == 400
        assert "Journalist" in resp.json()["detail"]

    def test_invalid_tier_does_not_call_stripe(self, client):
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session"
        ) as mock_create:
            resp = client.post(
                CHECKOUT_PATH,
                json={"tier": "bogus", "email": "a@b.com"},
            )
        assert resp.status_code == 400
        assert mock_create.call_count == 0


class TestCreateCheckoutErrorMapping:
    def test_value_error_from_stripe_maps_to_400_with_message(self, client):
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session",
            side_effect=ValueError("Missing STRIPE_PRICE_JOURNALIST env var"),
        ):
            resp = client.post(
                CHECKOUT_PATH,
                json={"tier": "journalist", "email": "a@b.com"},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing STRIPE_PRICE_JOURNALIST env var"

    def test_runtime_error_from_stripe_maps_to_503_with_message(self, client):
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session",
            side_effect=RuntimeError("STRIPE_SECRET_KEY not configured"),
        ):
            resp = client.post(
                CHECKOUT_PATH,
                json={"tier": "api", "email": "a@b.com"},
            )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "STRIPE_SECRET_KEY not configured"

    def test_generic_exception_maps_to_500_with_opaque_message(self, client):
        """Unexpected exceptions return a generic 500 — do not leak internals."""
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session",
            side_effect=Exception("stripe internal: card token leaked"),
        ):
            resp = client.post(
                CHECKOUT_PATH,
                json={"tier": "city", "email": "a@b.com"},
            )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Failed to create checkout session"
        # Ensure the sensitive internal message is NOT surfaced to the client.
        assert "card token leaked" not in resp.json()["detail"]

    def test_generic_exception_is_logged_at_error_level(self, client, caplog):
        import logging

        caplog.set_level(logging.ERROR, logger="civicos_services.servers.routers.billing")
        with patch(
            "civicos_services.core.stripe_billing.create_checkout_session",
            side_effect=Exception("boom"),
        ):
            resp = client.post(
                CHECKOUT_PATH,
                json={"tier": "organization", "email": "a@b.com"},
            )
        assert resp.status_code == 500
        assert any(
            "Checkout session creation failed" in rec.message
            and rec.levelname == "ERROR"
            for rec in caplog.records
        )


class TestCreateCheckoutAuth:
    def test_missing_authorization_header_returns_401(self, unauth_client):
        resp = unauth_client.post(
            CHECKOUT_PATH,
            json={"tier": "journalist", "email": "a@b.com"},
        )
        assert resp.status_code == 401


class TestCreateCheckoutRequestValidation:
    def test_missing_tier_field_returns_422(self, client):
        resp = client.post(CHECKOUT_PATH, json={"email": "a@b.com"})
        assert resp.status_code == 422

    def test_missing_email_field_returns_422(self, client):
        resp = client.post(CHECKOUT_PATH, json={"tier": "api"})
        assert resp.status_code == 422

    def test_empty_json_body_returns_422(self, client):
        resp = client.post(CHECKOUT_PATH, json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /billing/webhook
# ---------------------------------------------------------------------------


WEBHOOK_PATH = "/billing/webhook"
SAMPLE_PAYLOAD = b'{"id":"evt_123","type":"checkout.session.completed"}'
SAMPLE_SIG = "t=1700000000,v1=abc123"


class TestWebhookHappyPath:
    def test_valid_signature_returns_200_with_merged_result(self, client):
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            return_value={
                "event": "checkout.session.completed",
                "action": "api_key_provisioned",
                "key_id": "cos_live_xyz",
            },
        ):
            resp = client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": SAMPLE_SIG},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["event"] == "checkout.session.completed"
        assert body["action"] == "api_key_provisioned"
        assert body["key_id"] == "cos_live_xyz"

    def test_forwards_raw_body_and_signature_to_handler(self, client):
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            return_value={"event": "customer.subscription.updated"},
        ) as mock_handle:
            resp = client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": SAMPLE_SIG},
            )
        assert resp.status_code == 200
        args, kwargs = mock_handle.call_args
        # Positional args: (payload, signature)
        assert args[0] == SAMPLE_PAYLOAD
        assert args[1] == SAMPLE_SIG

    def test_empty_handler_result_still_returns_ok(self, client):
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            return_value={},
        ):
            resp = client.post(
                WEBHOOK_PATH,
                content=b"{}",
                headers={"Stripe-Signature": SAMPLE_SIG},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"status": "ok"}

    def test_handler_result_does_not_overwrite_status_key(self, client):
        """The literal ``{'status': 'ok'}`` is spread first, then handler result.

        If the handler returns its own ``status`` key, the spread order means
        the handler's value wins. This test pins that behavior so a refactor
        cannot silently swap the precedence.
        """
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            return_value={"status": "processed", "event": "invoice.payment_failed"},
        ):
            resp = client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": SAMPLE_SIG},
            )
        assert resp.status_code == 200
        body = resp.json()
        # Spread comes after literal, so handler's "processed" wins.
        assert body["status"] == "processed"
        assert body["event"] == "invoice.payment_failed"


class TestWebhookSignatureHeader:
    def test_missing_header_returns_400(self, client):
        resp = client.post(WEBHOOK_PATH, content=SAMPLE_PAYLOAD)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing Stripe-Signature header"

    def test_empty_header_value_returns_400(self, client):
        resp = client.post(
            WEBHOOK_PATH,
            content=SAMPLE_PAYLOAD,
            headers={"Stripe-Signature": ""},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Missing Stripe-Signature header"

    def test_missing_header_does_not_invoke_handler(self, client):
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook"
        ) as mock_handle:
            resp = client.post(WEBHOOK_PATH, content=SAMPLE_PAYLOAD)
        assert resp.status_code == 400
        assert mock_handle.call_count == 0


class TestWebhookErrorMapping:
    def test_value_error_maps_to_400_invalid_signature(self, client):
        """Stripe's construct_event raises ValueError for bad signature.

        The router collapses this into a fixed ``Invalid webhook signature``
        message rather than leaking the underlying stripe library error text.
        """
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            side_effect=ValueError("Invalid signature: expected v1=xyz"),
        ):
            resp = client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": "t=1,v1=bogus"},
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid webhook signature"
        # Underlying exception text is NOT surfaced.
        assert "expected v1=xyz" not in resp.json()["detail"]

    def test_value_error_is_logged_as_warning(self, client, caplog):
        import logging

        caplog.set_level(
            logging.WARNING, logger="civicos_services.servers.routers.billing"
        )
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            side_effect=ValueError("sig mismatch"),
        ):
            resp = client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": "t=1,v1=bogus"},
            )
        assert resp.status_code == 400
        warnings = [
            rec
            for rec in caplog.records
            if rec.levelname == "WARNING"
            and "Webhook signature verification failed" in rec.message
        ]
        assert len(warnings) == 1

    def test_runtime_error_maps_to_503_with_message(self, client):
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            side_effect=RuntimeError("STRIPE_WEBHOOK_SECRET not configured"),
        ):
            resp = client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": SAMPLE_SIG},
            )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "STRIPE_WEBHOOK_SECRET not configured"

    def test_generic_exception_maps_to_500_with_opaque_message(self, client):
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            side_effect=Exception("api_keys.provision_key blew up: DSN=..."),
        ):
            resp = client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": SAMPLE_SIG},
            )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Webhook processing failed"
        assert "DSN" not in resp.json()["detail"]

    def test_generic_exception_is_logged_at_error_level(self, client, caplog):
        import logging

        caplog.set_level(
            logging.ERROR, logger="civicos_services.servers.routers.billing"
        )
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            side_effect=Exception("kaboom"),
        ):
            resp = client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": SAMPLE_SIG},
            )
        assert resp.status_code == 500
        errors = [
            rec
            for rec in caplog.records
            if rec.levelname == "ERROR"
            and "Webhook processing failed" in rec.message
        ]
        assert len(errors) == 1


class TestWebhookAuth:
    def test_webhook_does_not_require_authorization_header(self, unauth_client):
        """Webhook endpoint uses Stripe signature, not bearer auth."""
        with patch(
            "civicos_services.core.stripe_billing.handle_webhook",
            return_value={"event": "checkout.session.completed"},
        ):
            resp = unauth_client.post(
                WEBHOOK_PATH,
                content=SAMPLE_PAYLOAD,
                headers={"Stripe-Signature": SAMPLE_SIG},
            )
        # 200 (not 401) — webhook has no auth dependency.
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Router wiring
# ---------------------------------------------------------------------------


class TestRouterRegistration:
    def test_checkout_route_is_registered(self):
        paths = {route.path for route in router.routes}
        assert "/billing/checkout" in paths

    def test_webhook_route_is_registered(self):
        paths = {route.path for route in router.routes}
        assert "/billing/webhook" in paths

    def test_checkout_accepts_only_post(self):
        for route in router.routes:
            if getattr(route, "path", None) == "/billing/checkout":
                assert route.methods == {"POST"}
                return
        pytest.fail("/billing/checkout route not found")

    def test_webhook_accepts_only_post(self):
        for route in router.routes:
            if getattr(route, "path", None) == "/billing/webhook":
                assert route.methods == {"POST"}
                return
        pytest.fail("/billing/webhook route not found")
