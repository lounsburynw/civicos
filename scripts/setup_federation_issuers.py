#!/usr/bin/env python3
"""Set up attestation issuers for federation test relays.

Generates keypairs, registers issuers, verifies them, and generates test codes.

Usage:
    python3 scripts/setup_federation_issuers.py generate   # Generate keypairs (local only)
    python3 scripts/setup_federation_issuers.py register   # Register issuers on live relays
    python3 scripts/setup_federation_issuers.py codes      # Generate + push test codes
    python3 scripts/setup_federation_issuers.py status     # Check relay status
    python3 scripts/setup_federation_issuers.py full       # Run all steps
"""

import json
import os
import secrets
import sys
import time

# Relays and their jurisdictions
RELAYS = {
    "city-mill-valley": {
        "url": "https://civicos-relay-mill-valley.fly.dev",
        "organization": "Mill Valley Library",
        "platform": "fly",
        "app": "civicos-relay-mill-valley",
    },
    "city-san-anselmo": {
        "url": "https://civicos-relay-san-anselmo.fly.dev",
        "organization": "San Anselmo Town Council",
        "platform": "fly",
        "app": "civicos-relay-san-anselmo",
    },
}

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "federation")


def _ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _config_path(jurisdiction: str) -> str:
    return os.path.join(CONFIG_DIR, f"{jurisdiction}.json")


def cmd_generate():
    """Generate issuer keypairs for each test relay."""
    from civicos_signer.crypto import IssuerKeyPair

    _ensure_config_dir()

    for jurisdiction, relay in RELAYS.items():
        config_file = _config_path(jurisdiction)

        if os.path.exists(config_file):
            existing = json.load(open(config_file))
            print(f"  {jurisdiction}: already exists (pubkey: {existing['issuer_pubkey'][:16]}...)")
            continue

        keypair = IssuerKeyPair.generate()
        bearer_token = secrets.token_urlsafe(32)
        admin_key = secrets.token_urlsafe(32)

        config = {
            "jurisdiction": jurisdiction,
            "organization": relay["organization"],
            "issuer_pubkey": keypair.public_key_hex,
            "private_key_hex": keypair.private_key_hex,
            "bearer_token": bearer_token,
            "admin_key": admin_key,
            "relay_url": relay["url"],
            "signing_url": f"{relay['url']}/signer",  # Placeholder
        }

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        os.chmod(config_file, 0o600)

        print(f"  {jurisdiction}: generated")
        print(f"    Pubkey:      {keypair.public_key_hex[:16]}...")
        print(f"    Admin key:   {admin_key[:16]}...")
        print(f"    Config:      {config_file}")

    # Add config dir to .gitignore if not already
    gitignore_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gitignore")
    if os.path.exists(gitignore_path):
        content = open(gitignore_path).read()
        if "config/federation/" not in content:
            with open(gitignore_path, "a") as f:
                f.write("\n# Federation test issuer configs (contain private keys)\nconfig/federation/\n")
            print("\n  Added config/federation/ to .gitignore")

    print("\nDone. Now set admin keys on relays:")
    for jurisdiction, relay in RELAYS.items():
        config = json.load(open(_config_path(jurisdiction)))
        if relay["platform"] == "fly":
            print(f"  fly secrets set CIVICOS_ADMIN_API_KEY={config['admin_key']} -a {relay['app']}")


def cmd_register():
    """Register issuers on live relays and verify them."""
    import httpx

    for jurisdiction, relay in RELAYS.items():
        config_file = _config_path(jurisdiction)
        if not os.path.exists(config_file):
            print(f"  {jurisdiction}: no config found (run 'generate' first)")
            continue

        config = json.load(open(config_file))
        admin_key = config["admin_key"]
        url = relay["url"].rstrip("/")

        print(f"\n  {jurisdiction} ({url}):")

        # Register issuer
        try:
            resp = httpx.post(
                f"{url}/coordination/issuers/register",
                headers={"Authorization": f"Bearer {admin_key}"},
                json={
                    "issuer_pubkey": config["issuer_pubkey"],
                    "jurisdiction": jurisdiction,
                    "organization": config["organization"],
                    "signing_url": config["signing_url"],
                    "bearer_token": config["bearer_token"],
                    "allowed_types": ["physical"],
                },
                timeout=15.0,
            )

            if resp.status_code == 200:
                result = resp.json()
                print(f"    Registered: {result['issuer_id']}")

                # Verify the issuer
                verify_resp = httpx.post(
                    f"{url}/coordination/admin/issuer/{result['issuer_id']}/verify",
                    headers={"Authorization": f"Bearer {admin_key}"},
                    timeout=15.0,
                )
                if verify_resp.status_code == 200:
                    print(f"    Verified: {result['issuer_id']}")
                else:
                    print(f"    Verify failed: {verify_resp.status_code} — {verify_resp.text}")

            elif resp.status_code == 400 and "already registered" in resp.text:
                print(f"    Already registered")
            else:
                print(f"    Register failed: {resp.status_code} — {resp.text}")

        except httpx.ConnectError as e:
            print(f"    Connection failed: {e}")
        except Exception as e:
            print(f"    Error: {e}")


def cmd_codes():
    """Generate test attestation codes and push to relays."""
    import httpx
    from civicos_signer.crypto import IssuerKeyPair, sign_code_batch

    for jurisdiction, relay in RELAYS.items():
        config_file = _config_path(jurisdiction)
        if not os.path.exists(config_file):
            print(f"  {jurisdiction}: no config found")
            continue

        config = json.load(open(config_file))
        admin_key = config["admin_key"]
        url = relay["url"].rstrip("/")

        # Generate 10 test codes
        prefix = jurisdiction.split("-")[1][:2].upper()
        codes = [f"{prefix}-2026-03-{secrets.token_hex(2).upper()}" for _ in range(10)]

        # Sign with issuer key
        keypair = IssuerKeyPair.from_private_key(config["private_key_hex"])
        batch_id = f"test-{int(time.time())}"
        signed_event = sign_code_batch(keypair, codes, jurisdiction, batch_id)

        print(f"\n  {jurisdiction} ({url}):")
        print(f"    Batch: {batch_id} ({len(codes)} codes)")

        try:
            resp = httpx.post(
                f"{url}/coordination/codes/batch",
                headers={"Authorization": f"Bearer {admin_key}"},
                json={"signed_event": signed_event},
                timeout=15.0,
            )

            if resp.status_code == 200:
                result = resp.json()
                print(f"    Accepted: {result['count']}/{result['total_submitted']} codes")
                print(f"    Sample codes: {codes[:3]}")
            else:
                print(f"    Failed: {resp.status_code} — {resp.text}")

        except Exception as e:
            print(f"    Error: {e}")


def cmd_status():
    """Check relay health and issuer status."""
    import httpx

    for jurisdiction, relay in RELAYS.items():
        url = relay["url"].rstrip("/")
        print(f"\n  {jurisdiction} ({url}):")

        try:
            # Health check
            health = httpx.get(f"{url}/health", timeout=10.0)
            print(f"    Health: {health.json().get('status', 'unknown')}")

            # Issuers
            issuers = httpx.get(f"{url}/coordination/issuers/{jurisdiction}", timeout=10.0)
            if issuers.status_code == 200:
                issuer_list = issuers.json().get("issuers", [])
                print(f"    Issuers: {len(issuer_list)}")
                for i in issuer_list:
                    print(f"      - {i.get('organization')} (verified: {i.get('verified')})")
            elif issuers.status_code == 404:
                print(f"    Issuers: endpoint not found (deploy new code first)")
            else:
                print(f"    Issuers: {issuers.status_code}")

            # Attestation stats
            stats = httpx.get(f"{url}/coordination/attestation/stats/{jurisdiction}", timeout=10.0)
            if stats.status_code == 200:
                s = stats.json()
                print(f"    Codes issued: {s.get('total_codes_issued', 0)}")
                print(f"    Codes redeemed: {s.get('total_codes_redeemed', 0)}")
                print(f"    Total attested: {s.get('total_attested', 0)}")

        except httpx.ConnectError:
            print(f"    OFFLINE")
        except Exception as e:
            print(f"    Error: {e}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    print(f"=== Federation Issuer Setup: {cmd} ===\n")

    if cmd == "generate":
        cmd_generate()
    elif cmd == "register":
        cmd_register()
    elif cmd == "codes":
        cmd_codes()
    elif cmd == "status":
        cmd_status()
    elif cmd == "full":
        cmd_generate()
        print("\n--- Deploy new code to relays before continuing ---")
        print("Set admin keys, then run: python3 scripts/setup_federation_issuers.py register")
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
