"""CivicOS Signer CLI.

Commands:
    civicos-signer keygen          Generate a new issuer keypair
    civicos-signer serve           Start the signing server
    civicos-signer register        Register this signer with a CivicOS relay
    civicos-signer verify <file>   Verify a signed attestation event
"""

import argparse
import json
import os
import secrets
import sys


def cmd_keygen(args):
    """Generate a new issuer keypair and bearer token."""
    from civicos_signer.crypto import IssuerKeyPair

    keypair = IssuerKeyPair.generate()
    bearer_token = secrets.token_urlsafe(32)

    if args.output == "-":
        out = sys.stdout
    else:
        out = open(args.output, "w")

    env_content = (
        f"# CivicOS Signer Configuration\n"
        f"# Generated for: {args.organization or 'your-organization'}\n"
        f"# Jurisdiction: {args.jurisdiction or 'city-your-city'}\n"
        f"#\n"
        f"# KEEP THIS FILE SECRET. The private key controls your\n"
        f"# organization's attestation authority.\n"
        f"#\n"
        f"CIVICOS_SIGNER_PRIVATE_KEY={keypair.private_key_hex}\n"
        f"CIVICOS_SIGNER_JURISDICTION={args.jurisdiction or 'city-your-city'}\n"
        f"CIVICOS_SIGNER_ORGANIZATION={args.organization or 'Your Organization'}\n"
        f"CIVICOS_SIGNER_BEARER_TOKEN={bearer_token}\n"
        f"CIVICOS_SIGNER_ALLOWED_TYPES={args.allowed_types or 'physical'}\n"
        f"CIVICOS_SIGNER_PORT=8850\n"
    )

    out.write(env_content)
    if out is not sys.stdout:
        out.close()
        os.chmod(args.output, 0o600)
        print(f"Written to {args.output} (permissions: 600)")

    # Always print pubkey to stderr so it's visible even when writing to file
    print(f"\nIssuer public key: {keypair.public_key_hex}", file=sys.stderr)
    print(f"Bearer token: {bearer_token}", file=sys.stderr)
    print(f"\nShare the PUBLIC KEY with CivicOS to register as a trusted issuer.", file=sys.stderr)
    print(f"Share the BEARER TOKEN with CivicOS so their relay can authenticate.", file=sys.stderr)
    print(f"NEVER share the private key.\n", file=sys.stderr)


def cmd_serve(args):
    """Start the signing server."""
    if args.env_file:
        _load_env_file(args.env_file)

    from civicos_signer.server import run_from_env

    run_from_env()


def cmd_register(args):
    """Register this signer with a CivicOS relay."""
    import httpx

    if args.env_file:
        _load_env_file(args.env_file)

    from civicos_signer.crypto import IssuerKeyPair

    private_key = os.environ.get("CIVICOS_SIGNER_PRIVATE_KEY")
    jurisdiction = os.environ.get("CIVICOS_SIGNER_JURISDICTION")
    organization = os.environ.get("CIVICOS_SIGNER_ORGANIZATION")

    if not all([private_key, jurisdiction, organization]):
        print("Error: Set CIVICOS_SIGNER_PRIVATE_KEY, _JURISDICTION, _ORGANIZATION", file=sys.stderr)
        sys.exit(1)

    issuer = IssuerKeyPair.from_private_key(private_key)

    registration = {
        "issuer_pubkey": issuer.public_key_hex,
        "jurisdiction": jurisdiction,
        "organization": organization,
        "signing_url": args.signing_url,
        "allowed_types": os.environ.get("CIVICOS_SIGNER_ALLOWED_TYPES", "physical").split(","),
    }

    if args.dry_run:
        print("Registration payload (dry run):")
        print(json.dumps(registration, indent=2))
        print(f"\nSend this to the CivicOS relay operator for registration.")
        return

    # POST to relay's issuer registration endpoint
    relay_url = args.relay_url.rstrip("/")
    relay_api_key = args.relay_api_key or os.environ.get("CIVICOS_RELAY_API_KEY")
    if not relay_api_key:
        print("Error: --relay-api-key or CIVICOS_RELAY_API_KEY required", file=sys.stderr)
        sys.exit(1)

    resp = httpx.post(
        f"{relay_url}/coordination/issuers/register",
        json=registration,
        headers={"Authorization": f"Bearer {relay_api_key}"},
    )

    if resp.status_code == 200:
        result = resp.json()
        print(f"Registered as trusted issuer for {jurisdiction}")
        print(f"  Issuer ID: {result.get('issuer_id')}")
        print(f"  Pubkey: {issuer.public_key_hex}")
    else:
        print(f"Registration failed: {resp.status_code} — {resp.text}", file=sys.stderr)
        sys.exit(1)


def cmd_generate_codes(args):
    """Generate attestation codes, sign them, and push to relay."""
    import httpx

    if args.env_file:
        _load_env_file(args.env_file)

    from civicos_signer.crypto import IssuerKeyPair, sign_code_batch

    private_key = os.environ.get("CIVICOS_SIGNER_PRIVATE_KEY")
    jurisdiction = os.environ.get("CIVICOS_SIGNER_JURISDICTION")
    if not all([private_key, jurisdiction]):
        print("Error: Set CIVICOS_SIGNER_PRIVATE_KEY, _JURISDICTION", file=sys.stderr)
        sys.exit(1)

    issuer = IssuerKeyPair.from_private_key(private_key)

    # Generate codes
    import random
    import string

    now = __import__("datetime").datetime.utcnow()

    # Jurisdiction -> code prefix
    prefixes = {
        "city-san-rafael": "SR", "city-berkeley": "BK",
        "city-oakland": "OK", "city-richmond": "RC",
    }
    prefix = prefixes.get(jurisdiction)
    if not prefix:
        parts = jurisdiction.replace("city-", "").split("-")
        prefix = "".join(p[0].upper() for p in parts[:2]) if len(parts) > 1 else parts[0][:2].upper()

    codes = set()
    while len(codes) < args.count:
        rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        codes.add(f"{prefix}-{now.year}-{now.month:02d}-{rand}")

    codes_list = sorted(codes)

    # Sign the batch
    batch_event = sign_code_batch(
        issuer=issuer,
        codes=codes_list,
        jurisdiction=jurisdiction,
        batch_id=args.batch,
        expires_at=args.expires,
    )

    if args.dry_run:
        print(f"# Dry run: {len(codes_list)} codes for {jurisdiction} (batch: {args.batch})")
        print(f"# Signed by issuer: {issuer.public_key_hex[:16]}...")
        for code in codes_list:
            print(code)
        return

    # Push to relay
    relay_url = args.relay_url.rstrip("/")
    resp = httpx.post(
        f"{relay_url}/coordination/codes/batch",
        json={"signed_event": batch_event},
        timeout=30.0,
    )

    if resp.status_code == 200:
        result = resp.json()
        print(f"Pushed {result.get('count', len(codes_list))} codes to relay")
        print(f"  Jurisdiction: {jurisdiction}")
        print(f"  Batch: {args.batch}")
        print(f"  Issuer: {issuer.public_key_hex[:16]}...")
        if args.output:
            with open(args.output, "w") as f:
                for code in codes_list:
                    f.write(code + "\n")
            print(f"  Codes written to: {args.output}")
        else:
            for code in codes_list:
                print(code)
    else:
        print(f"Failed: {resp.status_code} — {resp.text}", file=sys.stderr)
        sys.exit(1)


def cmd_verify(args):
    """Verify a signed attestation event from a JSON file."""
    from civicos_signer.crypto import verify_attestation

    with open(args.file) as f:
        event = json.load(f)

    # Extract fields from the event
    tags = event.get("tags", [])
    subject = next((t[1] for t in tags if t[0] == "p"), None)
    jurisdiction = next((t[1] for t in tags if t[0] == "j"), None)
    issuer = event.get("pubkey")

    if not all([subject, jurisdiction, issuer]):
        print("Error: event missing required tags (p, j) or pubkey", file=sys.stderr)
        sys.exit(1)

    valid = verify_attestation(event, subject, jurisdiction, issuer)
    if valid:
        print(f"VALID attestation")
        print(f"  Issuer: {issuer[:16]}...")
        print(f"  Subject: {subject[:16]}...")
        print(f"  Jurisdiction: {jurisdiction}")
        attest_type = next((t[1] for t in tags if t[0] == "type"), "unknown")
        print(f"  Type: {attest_type}")
    else:
        print("INVALID attestation — signature verification failed", file=sys.stderr)
        sys.exit(1)


def _load_env_file(path: str):
    """Minimal .env loader (no dotenv dependency required)."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def main():
    parser = argparse.ArgumentParser(
        prog="civicos-signer",
        description="CivicOS attestation signing service",
    )
    sub = parser.add_subparsers(dest="command")

    # keygen
    kg = sub.add_parser("keygen", help="Generate a new issuer keypair")
    kg.add_argument("-o", "--output", default=".env.signer", help="Output file (default: .env.signer)")
    kg.add_argument("--jurisdiction", help="Jurisdiction code")
    kg.add_argument("--organization", help="Organization name")
    kg.add_argument("--allowed-types", default="physical", help="Comma-separated attestation types")

    # serve
    sv = sub.add_parser("serve", help="Start the signing server")
    sv.add_argument("--env-file", default=".env.signer", help="Env file to load")

    # register
    rg = sub.add_parser("register", help="Register with a CivicOS relay")
    rg.add_argument("--relay-url", required=True, help="CivicOS relay URL")
    rg.add_argument("--signing-url", required=True, help="This signer's public URL")
    rg.add_argument("--relay-api-key", help="Relay admin API key")
    rg.add_argument("--env-file", default=".env.signer", help="Env file to load")
    rg.add_argument("--dry-run", action="store_true", help="Print payload without sending")

    # generate-codes
    gc = sub.add_parser("generate-codes", help="Generate codes, sign, and push to relay")
    gc.add_argument("--count", type=int, required=True, help="Number of codes to generate")
    gc.add_argument("--batch", required=True, help="Batch identifier (e.g., 'mar-2026-event')")
    gc.add_argument("--relay-url", required=True, help="CivicOS relay URL")
    gc.add_argument("--expires", help="Expiration date (ISO format, e.g., 2026-04-01)")
    gc.add_argument("--output", "-o", help="Write codes to file (one per line)")
    gc.add_argument("--env-file", default=".env.signer", help="Env file to load")
    gc.add_argument("--dry-run", action="store_true", help="Generate and sign without pushing")

    # verify
    vf = sub.add_parser("verify", help="Verify a signed attestation event")
    vf.add_argument("file", help="JSON file containing attestation event")

    args = parser.parse_args()
    if args.command == "keygen":
        cmd_keygen(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "register":
        cmd_register(args)
    elif args.command == "generate-codes":
        cmd_generate_codes(args)
    elif args.command == "verify":
        cmd_verify(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
