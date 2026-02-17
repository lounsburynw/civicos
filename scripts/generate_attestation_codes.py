#!/usr/bin/env python3
"""Generate single-use attestation codes for a jurisdiction.

Usage:
    python3 scripts/generate_attestation_codes.py \\
        --jurisdiction city-san-rafael \\
        --count 50 \\
        --batch "feb-2026-event"

Generates codes in format: {PREFIX}-{YYYY}-{MM}-{RANDOM4}
Inserts into coordination_attestation_codes table.
Outputs CSV to stdout for printing.
"""

import argparse
import os
import random
import string
import sys
from datetime import datetime

# Jurisdiction -> code prefix mapping
JURISDICTION_PREFIXES = {
    "city-san-rafael": "SR",
    "city-berkeley": "BK",
    "city-oakland": "OK",
    "city-richmond": "RC",
}


def generate_code(prefix: str, year: int, month: int) -> str:
    """Generate a single attestation code."""
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{year}-{month:02d}-{random_part}"


def main():
    parser = argparse.ArgumentParser(description="Generate attestation codes")
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction code (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of codes to generate",
    )
    parser.add_argument(
        "--batch",
        required=True,
        help="Batch identifier (e.g., 'feb-2026-event')",
    )
    parser.add_argument(
        "--expires",
        help="Expiration date (ISO format, e.g., 2026-03-01)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate codes without inserting into database",
    )
    args = parser.parse_args()

    prefix = JURISDICTION_PREFIXES.get(args.jurisdiction)
    if not prefix:
        # Derive prefix from jurisdiction name
        parts = args.jurisdiction.replace("city-", "").split("-")
        prefix = "".join(p[0].upper() for p in parts[:2]) if len(parts) > 1 else parts[0][:2].upper()
        print(f"# Using derived prefix: {prefix}", file=sys.stderr)

    now = datetime.utcnow()
    codes = set()
    while len(codes) < args.count:
        codes.add(generate_code(prefix, now.year, now.month))

    codes_list = sorted(codes)

    if args.dry_run:
        print(f"# Dry run: {len(codes_list)} codes for {args.jurisdiction} (batch: {args.batch})")
        for code in codes_list:
            print(code)
        return

    # Insert into database
    from dotenv import load_dotenv

    load_dotenv()
    db_url = os.environ.get("RELAY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: RELAY_DATABASE_URL or DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    import psycopg2

    expires_at = args.expires if args.expires else None

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            for code in codes_list:
                cur.execute(
                    """
                    INSERT INTO coordination_attestation_codes
                    (code, jurisdiction, batch_id, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (code) DO NOTHING
                    """,
                    (code, args.jurisdiction, args.batch, expires_at),
                )
            conn.commit()

        print(f"# Inserted {len(codes_list)} codes for {args.jurisdiction} (batch: {args.batch})", file=sys.stderr)
        # Output CSV for printing
        for code in codes_list:
            print(code)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
