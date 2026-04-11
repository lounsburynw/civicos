"""
Tests for the NIP-05 Nostr verification endpoint.

Tests cover the helper functions that read environment variables
(_get_relay_pubkey, _get_relay_url, _get_name_pubkeys) and the
/.well-known/nostr.json FastAPI route.

External dependency (os.environ) is controlled via monkeypatch;
the router itself is exercised through FastAPI's TestClient so
request parsing, query params, and JSONResponse headers are real.

To run:
    pytest packages/civicos-services/tests/test_nostr.py -q --override-ini="addopts="
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from civicos_services.servers.routers.nostr import (
    _get_name_pubkeys,
    _get_relay_pubkey,
    _get_relay_url,
    router,
)


# A valid 64-char hex pubkey — used throughout the tests as the "configured" identity.
VALID_PUBKEY = "a" * 64
OTHER_PUBKEY = "b" * 64
DEFAULT_RELAY_URL = "wss://relay.civicos.org"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch):
    """Unset Nostr env vars so each test starts from a known state."""
    monkeypatch.delenv("NOSTR_RELAY_PUBKEY", raising=False)
    monkeypatch.delenv("NOSTR_RELAY_URL", raising=False)
    return monkeypatch


@pytest.fixture
def client():
    """TestClient wrapping a FastAPI app with the Nostr router mounted."""
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# _get_relay_pubkey
# ---------------------------------------------------------------------------


def test_get_relay_pubkey_returns_none_when_unset(clean_env):
    assert _get_relay_pubkey() is None


def test_get_relay_pubkey_returns_none_when_empty_string(clean_env):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", "")
    assert _get_relay_pubkey() is None


def test_get_relay_pubkey_returns_none_when_whitespace_only(clean_env):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", "   ")
    assert _get_relay_pubkey() is None


def test_get_relay_pubkey_returns_none_when_too_short(clean_env):
    # 63 chars — off by one — must be rejected
    clean_env.setenv("NOSTR_RELAY_PUBKEY", "a" * 63)
    assert _get_relay_pubkey() is None


def test_get_relay_pubkey_returns_none_when_too_long(clean_env):
    # 65 chars — off by one — must be rejected
    clean_env.setenv("NOSTR_RELAY_PUBKEY", "a" * 65)
    assert _get_relay_pubkey() is None


def test_get_relay_pubkey_returns_value_when_length_is_exactly_64(clean_env):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    assert _get_relay_pubkey() == VALID_PUBKEY


def test_get_relay_pubkey_strips_surrounding_whitespace(clean_env):
    # A pubkey with leading/trailing whitespace should be accepted
    # after stripping — and the stripped value must be returned.
    clean_env.setenv("NOSTR_RELAY_PUBKEY", f"  {VALID_PUBKEY}  ")
    assert _get_relay_pubkey() == VALID_PUBKEY


def test_get_relay_pubkey_rejects_padded_pubkey_that_is_too_long(clean_env):
    # A 64-char pubkey padded with whitespace beyond strip bounds is valid;
    # but a value that is 64 chars *including* padding becomes <64 after strip
    # and must be rejected.
    clean_env.setenv("NOSTR_RELAY_PUBKEY", " " + "a" * 62 + " ")  # 64 chars, 62 after strip
    assert _get_relay_pubkey() is None


# ---------------------------------------------------------------------------
# _get_relay_url
# ---------------------------------------------------------------------------


def test_get_relay_url_returns_default_when_unset(clean_env):
    assert _get_relay_url() == DEFAULT_RELAY_URL


def test_get_relay_url_returns_env_value_when_set(clean_env):
    clean_env.setenv("NOSTR_RELAY_URL", "wss://relay.example.org")
    assert _get_relay_url() == "wss://relay.example.org"


def test_get_relay_url_returns_empty_string_when_explicitly_empty(clean_env):
    # Empty string is not stripped or replaced — environment overrides default.
    clean_env.setenv("NOSTR_RELAY_URL", "")
    assert _get_relay_url() == ""


# ---------------------------------------------------------------------------
# _get_name_pubkeys
# ---------------------------------------------------------------------------


def test_get_name_pubkeys_returns_empty_when_no_pubkey_configured(clean_env):
    assert _get_name_pubkeys() == {}


def test_get_name_pubkeys_maps_civicos_and_wildcard_to_pubkey(clean_env):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    result = _get_name_pubkeys()
    assert result == {"civicos": VALID_PUBKEY, "_": VALID_PUBKEY}


def test_get_name_pubkeys_returns_empty_when_pubkey_invalid(clean_env):
    # Invalid pubkey should produce no mapping, not a partial one.
    clean_env.setenv("NOSTR_RELAY_PUBKEY", "tooshort")
    assert _get_name_pubkeys() == {}


# ---------------------------------------------------------------------------
# GET /.well-known/nostr.json — no pubkey configured
# ---------------------------------------------------------------------------


def test_endpoint_returns_empty_mapping_when_no_pubkey_configured(clean_env, client):
    resp = client.get("/.well-known/nostr.json")
    assert resp.status_code == 200
    assert resp.json() == {"names": {}, "relays": {}}


def test_endpoint_sets_cors_and_cache_headers_when_empty(clean_env, client):
    resp = client.get("/.well-known/nostr.json")
    assert resp.headers["access-control-allow-origin"] == "*"
    assert resp.headers["cache-control"] == "max-age=3600"


def test_endpoint_returns_empty_mapping_when_name_requested_without_pubkey(clean_env, client):
    # Even with a specific name, empty config returns empty both maps.
    resp = client.get("/.well-known/nostr.json?name=civicos")
    assert resp.status_code == 200
    assert resp.json() == {"names": {}, "relays": {}}


# ---------------------------------------------------------------------------
# GET /.well-known/nostr.json — pubkey configured, no name query param
# ---------------------------------------------------------------------------


def test_endpoint_returns_all_names_when_no_query(clean_env, client):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["names"] == {"civicos": VALID_PUBKEY, "_": VALID_PUBKEY}
    # Both names share the same pubkey, so relays dict has ONE entry.
    assert body["relays"] == {VALID_PUBKEY: [DEFAULT_RELAY_URL]}


def test_endpoint_deduplicates_relay_entries_for_shared_pubkey(clean_env, client):
    """Names sharing a pubkey must not produce duplicate relay list entries."""
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json")
    body = resp.json()
    # Exactly one pubkey key, and exactly one relay URL in its list.
    assert len(body["relays"]) == 1
    assert body["relays"][VALID_PUBKEY] == [DEFAULT_RELAY_URL]


def test_endpoint_uses_custom_relay_url_from_env(clean_env, client):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    clean_env.setenv("NOSTR_RELAY_URL", "wss://relay.example.org")
    resp = client.get("/.well-known/nostr.json")
    body = resp.json()
    assert body["relays"] == {VALID_PUBKEY: ["wss://relay.example.org"]}


# ---------------------------------------------------------------------------
# GET /.well-known/nostr.json — specific name lookup
# ---------------------------------------------------------------------------


def test_endpoint_returns_only_requested_name_when_query_matches(clean_env, client):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json?name=civicos")
    body = resp.json()
    assert body["names"] == {"civicos": VALID_PUBKEY}
    assert body["relays"] == {VALID_PUBKEY: [DEFAULT_RELAY_URL]}
    assert "_" not in body["names"]


def test_endpoint_returns_wildcard_name_when_requested(clean_env, client):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json?name=_")
    body = resp.json()
    assert body["names"] == {"_": VALID_PUBKEY}
    assert body["relays"] == {VALID_PUBKEY: [DEFAULT_RELAY_URL]}


def test_endpoint_returns_empty_when_name_not_registered(clean_env, client):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json?name=unknown")
    assert resp.status_code == 200
    # Name did not match; both maps must be empty (not the full mapping).
    assert resp.json() == {"names": {}, "relays": {}}


def test_endpoint_name_lookup_is_case_sensitive(clean_env, client):
    """'CivicOS' should not match the registered lowercase 'civicos'."""
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json?name=CivicOS")
    assert resp.json() == {"names": {}, "relays": {}}


def test_endpoint_empty_name_query_returns_all_names(clean_env, client):
    """An empty name param is falsy; the endpoint treats it the same as no query
    and returns the full mapping rather than a specific lookup for ''."""
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json?name=")
    body = resp.json()
    assert body["names"] == {"civicos": VALID_PUBKEY, "_": VALID_PUBKEY}
    assert body["relays"] == {VALID_PUBKEY: [DEFAULT_RELAY_URL]}


# ---------------------------------------------------------------------------
# Headers are always present on successful responses
# ---------------------------------------------------------------------------


def test_endpoint_sets_cors_header_when_populated(clean_env, client):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json?name=civicos")
    assert resp.headers["access-control-allow-origin"] == "*"


def test_endpoint_sets_cache_header_when_populated(clean_env, client):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json?name=civicos")
    assert resp.headers["cache-control"] == "max-age=3600"


# ---------------------------------------------------------------------------
# Response shape integrity
# ---------------------------------------------------------------------------


def test_endpoint_response_has_exactly_two_top_level_keys(clean_env, client):
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json")
    body = resp.json()
    assert set(body.keys()) == {"names", "relays"}


def test_endpoint_relay_values_are_lists(clean_env, client):
    """Per NIP-05, 'relays' values must be arrays of WebSocket URLs."""
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json")
    body = resp.json()
    assert body["relays"][VALID_PUBKEY] == [DEFAULT_RELAY_URL]
    assert len(body["relays"][VALID_PUBKEY]) == 1


def test_endpoint_name_value_matches_pubkey_exactly(clean_env, client):
    """The 'names' value must equal the configured pubkey byte-for-byte."""
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    resp = client.get("/.well-known/nostr.json?name=civicos")
    body = resp.json()
    assert body["names"]["civicos"] == VALID_PUBKEY
    # And the relay map is keyed by that same pubkey.
    assert VALID_PUBKEY in body["relays"]


def test_endpoint_pubkey_rotation_reflects_new_value(clean_env, client):
    """Changing the env var between calls must produce a new response."""
    clean_env.setenv("NOSTR_RELAY_PUBKEY", VALID_PUBKEY)
    first = client.get("/.well-known/nostr.json?name=civicos").json()
    assert first["names"]["civicos"] == VALID_PUBKEY

    clean_env.setenv("NOSTR_RELAY_PUBKEY", OTHER_PUBKEY)
    second = client.get("/.well-known/nostr.json?name=civicos").json()
    assert second["names"]["civicos"] == OTHER_PUBKEY
    assert OTHER_PUBKEY in second["relays"]
    assert VALID_PUBKEY not in second["relays"]
