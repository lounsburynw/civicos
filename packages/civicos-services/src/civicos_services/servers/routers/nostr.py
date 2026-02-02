"""
NIP-05 Nostr verification endpoint.

Implements the /.well-known/nostr.json endpoint per NIP-05 specification
to enable human-readable identity verification for CivicOS jurisdictions.

References:
- NIP-05: https://github.com/nostr-protocol/nips/blob/master/05.md

Example:
    GET /.well-known/nostr.json?name=civicos

    Response:
    {
        "names": {"civicos": "abc123..."},
        "relays": {"abc123...": ["wss://relay.civicos.org"]}
    }
"""

import os
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter()


# Configuration via environment variables
# NOSTR_RELAY_PUBKEY: 64-char hex public key for the civicos relay identity
# NOSTR_RELAY_URL: WebSocket URL for the relay (default: wss://relay.civicos.org)
def _get_relay_pubkey() -> Optional[str]:
    """Get relay pubkey from environment, with validation."""
    pubkey = os.environ.get("NOSTR_RELAY_PUBKEY", "").strip()
    if pubkey and len(pubkey) == 64:
        return pubkey
    return None


def _get_relay_url() -> str:
    """Get relay WebSocket URL from environment."""
    return os.environ.get("NOSTR_RELAY_URL", "wss://relay.civicos.org")


# Static mapping of names to pubkeys
# In production, this could be loaded from database or config file
def _get_name_pubkeys() -> dict[str, str]:
    """
    Get mapping of NIP-05 names to pubkeys.

    Currently supports:
    - 'civicos': The main CivicOS relay identity
    - '_': Wildcard for the root domain identity

    Cities can host their own /.well-known/nostr.json on their domains
    (e.g., sanrafael.gov) to verify their official accounts.
    """
    pubkeys = {}
    relay_pubkey = _get_relay_pubkey()

    if relay_pubkey:
        # The civicos identity (e.g., civicos@civicos.org)
        pubkeys["civicos"] = relay_pubkey
        # Wildcard for root domain (e.g., _@civicos.org)
        pubkeys["_"] = relay_pubkey

    return pubkeys


@router.get("/.well-known/nostr.json")
async def nostr_json(name: Optional[str] = Query(None, description="Name to look up")):
    """
    NIP-05 verification endpoint.

    Returns pubkey and relay information for registered names.
    This is a public endpoint - no authentication required.

    Query Parameters:
        name: Optional name to look up. If not provided, returns all names.

    Response:
        NIP-05 compliant JSON with 'names' and 'relays' fields.

    Example:
        GET /.well-known/nostr.json?name=civicos
        -> {"names": {"civicos": "abc..."}, "relays": {"abc...": ["wss://..."]}}
    """
    name_pubkeys = _get_name_pubkeys()
    relay_url = _get_relay_url()

    # If no pubkeys configured, return empty response
    if not name_pubkeys:
        return JSONResponse(
            content={"names": {}, "relays": {}},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "max-age=3600",  # Cache for 1 hour
            },
        )

    # Build response
    names: dict[str, str] = {}
    relays: dict[str, list[str]] = {}

    if name:
        # Specific name lookup
        if name in name_pubkeys:
            pubkey = name_pubkeys[name]
            names[name] = pubkey
            relays[pubkey] = [relay_url]
    else:
        # Return all names
        for n, pubkey in name_pubkeys.items():
            names[n] = pubkey
            if pubkey not in relays:
                relays[pubkey] = [relay_url]

    return JSONResponse(
        content={"names": names, "relays": relays},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "max-age=3600",  # Cache for 1 hour
        },
    )
