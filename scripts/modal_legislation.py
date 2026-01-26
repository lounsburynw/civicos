"""
Modal function for fetching legislation full text from LegiScan API.

This module provides serverless compute for fetching bill text content that's
missing from the legislation table. It uses LegiScan's getBill and getBillText
APIs to retrieve the actual text of legislation.

Architecture:
    Modal (compute) -> LegiScan API (source) -> Postgres (storage)

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal setup
    3. Create secrets:
       modal secret create civic-db DATABASE_URL="postgresql://..."
       modal secret create civic-legiscan LEGISCAN_API_KEY="..."
    4. Deploy: modal deploy scripts/modal_legislation.py

Usage:
    # Fetch bill text for California
    modal run scripts/modal_legislation.py --jurisdiction state-CA

    # Fetch for US Congress
    modal run scripts/modal_legislation.py --jurisdiction federal-US

    # Limit number of bills (for testing or quota management)
    modal run scripts/modal_legislation.py --jurisdiction state-CA --limit 100

    # Check current stats only
    modal run scripts/modal_legislation.py --stats-only

    # Dry run (fetch but don't store)
    modal run scripts/modal_legislation.py --jurisdiction state-CA --dry-run

API Quota Notes:
    - LegiScan free tier: 30,000 queries/month
    - Per bill: 2 API calls (getBill + getBillText)
    - CA: ~2,839 bills = ~5,700 calls
    - US: ~12,355 bills = ~24,700 calls
    - Total: ~30,400 calls = monthly limit

    Recommendation: Run CA one month, US the next, or prioritize active bills.
"""

import modal

# Define the Modal app
app = modal.App("civic-legislation")

# Build image with dependencies for LegiScan API access
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    # System dependencies for psycopg2
    .apt_install("libpq-dev", "gcc")
    # Python dependencies
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "requests>=2.31.0",  # For LegiScan API calls
        # civic package dependencies
        "langgraph>=0.2.0",
    )
    # Add local civic packages
    .add_local_python_source("civicos", "civicos_extraction", "civicos_services")
)


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-legiscan"),
    ],
    memory=4096,  # 4GB sufficient - text processing, low memory
    timeout=14400,  # 4 hours - many API calls with rate limiting
    retries=modal.Retries(
        max_retries=2,
        backoff_coefficient=2.0,
        initial_delay=60.0,  # Longer delay for API rate limits
    ),
)
def fetch_legislation_text(
    jurisdiction: str = "state-CA",
    limit: int | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
) -> dict:
    """
    Fetch bill text from LegiScan API and store to Postgres.

    Args:
        jurisdiction: Jurisdiction ID (e.g., "state-CA", "federal-US")
        limit: Maximum bills to fetch (None = all)
        dry_run: If True, fetch but don't store to database
        skip_existing: If True, skip bills that already have full_text

    Returns:
        Dict with fetch results including bill counts, API usage, and timing
    """
    import base64
    import logging
    import os
    import re
    import time
    import requests

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger(__name__)

    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    legiscan_key = os.environ.get("LEGISCAN_API_KEY")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    if not legiscan_key:
        raise ValueError("LEGISCAN_API_KEY environment variable not set")

    # Parse jurisdiction
    if jurisdiction.startswith("state-"):
        state_code = jurisdiction.replace("state-", "")
    elif jurisdiction.startswith("federal"):
        state_code = "US"
    else:
        state_code = jurisdiction

    logger.info(f"Starting legislation text fetch: jurisdiction={jurisdiction}, state_code={state_code}")
    logger.info(f"Parameters: limit={limit}, dry_run={dry_run}, skip_existing={skip_existing}")

    # Connect to database
    backend = PostgresBackend(database_url)

    # Get bills that need text
    logger.info("Fetching bills from database...")
    all_bills = backend.get_legislation(state_code)
    logger.info(f"Found {len(all_bills)} total bills for {state_code}")

    # Filter to bills needing text
    if skip_existing:
        bills_needing_text = [b for b in all_bills if not b.get("full_text")]
        logger.info(f"Bills needing full_text: {len(bills_needing_text)}")
    else:
        bills_needing_text = all_bills

    # Apply limit
    if limit:
        bills_needing_text = bills_needing_text[:limit]
        logger.info(f"Limited to {len(bills_needing_text)} bills")

    if not bills_needing_text:
        logger.info("No bills need text fetching")
        return {
            "jurisdiction": jurisdiction,
            "state_code": state_code,
            "bills_processed": 0,
            "bills_with_text": 0,
            "api_calls": 0,
            "dry_run": dry_run,
            "timing": {"total_seconds": time.time() - start_time},
        }

    # LegiScan API helper
    def legiscan_request(operation: str, params: dict) -> dict:
        """Make LegiScan API request with rate limiting."""
        time.sleep(0.5)  # Rate limit: ~2 req/s
        try:
            response = requests.get(
                "https://api.legiscan.com/",
                params={"key": legiscan_key, "op": operation, **params},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"LegiScan API error: {e}")
            return {}

    def html_to_text(html: str) -> str:
        """Convert HTML to plain text."""
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # Process bills
    api_calls = 0
    bills_updated = 0
    bills_failed = 0
    updates = []  # Collect updates for batch storage

    for i, bill in enumerate(bills_needing_text):
        bill_id = bill.get("bill_id")
        legiscan_id = bill.get("legiscan_id")
        bill_number = bill.get("bill_number", "unknown")

        if not legiscan_id:
            logger.warning(f"Bill {bill_id} has no legiscan_id, skipping")
            continue

        logger.info(f"[{i+1}/{len(bills_needing_text)}] Processing {bill_number} (legiscan_id={legiscan_id})")

        # Step 1: Get bill details to find text document
        bill_data = legiscan_request("getBill", {"id": legiscan_id})
        api_calls += 1

        if not bill_data or "bill" not in bill_data:
            logger.warning(f"  No bill data returned")
            bills_failed += 1
            continue

        texts = bill_data["bill"].get("texts", [])
        if not texts:
            logger.warning(f"  No text documents available")
            bills_failed += 1
            continue

        # Get the most recent text version
        latest_text = texts[-1]  # Usually sorted by date
        doc_id = latest_text.get("doc_id")

        if not doc_id:
            logger.warning(f"  No doc_id in text info")
            bills_failed += 1
            continue

        # Step 2: Get bill text content
        text_data = legiscan_request("getBillText", {"id": doc_id})
        api_calls += 1

        if not text_data or "text" not in text_data:
            logger.warning(f"  No text content returned")
            bills_failed += 1
            continue

        doc_b64 = text_data["text"].get("doc", "")
        if not doc_b64:
            logger.warning(f"  Empty document content")
            bills_failed += 1
            continue

        # Decode base64 and convert to plain text
        try:
            doc_html = base64.b64decode(doc_b64).decode("utf-8")
            full_text = html_to_text(doc_html)
            logger.info(f"  Got {len(full_text)} chars of text")
        except Exception as e:
            logger.error(f"  Error decoding text: {e}")
            bills_failed += 1
            continue

        # Collect update
        updates.append({
            "bill_id": bill_id,
            "full_text": full_text,
        })
        bills_updated += 1

        # Progress logging
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed * 60
            logger.info(f"Progress: {i+1}/{len(bills_needing_text)} bills, {api_calls} API calls, {rate:.1f} bills/min")

    # Store updates to database
    if updates and not dry_run:
        logger.info(f"Storing {len(updates)} bill text updates to database...")
        store_start = time.time()

        try:
            stored = backend.update_legislation_text(state_code, updates)
            logger.info(f"Stored {stored} bills in {time.time() - store_start:.1f}s")
        except Exception as e:
            logger.error(f"Error storing updates: {e}")
    elif dry_run:
        logger.info(f"Dry run - would store {len(updates)} bill text updates")

    # Calculate cost estimate
    elapsed_seconds = time.time() - start_time
    memory_gb = 4  # Configured memory
    gb_seconds = memory_gb * elapsed_seconds
    estimated_cost = gb_seconds * 0.000463  # Modal CPU pricing

    logger.info("=" * 60)
    logger.info(f"Legislation Text Fetch Complete")
    logger.info("=" * 60)
    logger.info(f"Jurisdiction: {jurisdiction}")
    logger.info(f"Bills processed: {len(bills_needing_text)}")
    logger.info(f"Bills with text: {bills_updated}")
    logger.info(f"Bills failed: {bills_failed}")
    logger.info(f"API calls used: {api_calls}")
    logger.info(f"Time: {elapsed_seconds:.1f}s")
    logger.info(f"Cost: ${estimated_cost:.4f}")
    logger.info("=" * 60)

    return {
        "jurisdiction": jurisdiction,
        "state_code": state_code,
        "bills_processed": len(bills_needing_text),
        "bills_with_text": bills_updated,
        "bills_failed": bills_failed,
        "api_calls": api_calls,
        "dry_run": dry_run,
        "timing": {
            "total_seconds": elapsed_seconds,
        },
        "cost": {
            "memory_gb": memory_gb,
            "gb_seconds": gb_seconds,
            "estimated_cost_usd": estimated_cost,
        },
    }


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=2048,  # 2GB sufficient for stats query
    timeout=60,
)
def get_stats(jurisdiction: str | None = None) -> dict:
    """
    Get current legislation statistics from database.

    Args:
        jurisdiction: Optional jurisdiction to filter (e.g., "state-CA")

    Returns:
        Dict with bill counts and full_text coverage
    """
    import os

    from civicos.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)

    # Get stats for each state
    states = ["CA", "US"] if not jurisdiction else [
        jurisdiction.replace("state-", "").replace("federal-", "")
    ]

    stats = {}
    for state in states:
        try:
            bills = backend.get_legislation(state)
            total = len(bills)
            with_text = sum(1 for b in bills if b.get("full_text"))

            stats[state] = {
                "total_bills": total,
                "with_full_text": with_text,
                "coverage_pct": f"{with_text/total*100:.1f}%" if total > 0 else "N/A",
                "api_calls_needed": (total - with_text) * 2,  # 2 calls per bill
            }
        except Exception as e:
            stats[state] = {"error": str(e)}

    return stats


@app.local_entrypoint()
def main(
    jurisdiction: str = "state-CA",
    limit: int | None = None,
    dry_run: bool = False,
    stats_only: bool = False,
):
    """
    CLI entrypoint for modal run.

    Examples:
        modal run scripts/modal_legislation.py --stats-only
        modal run scripts/modal_legislation.py --jurisdiction state-CA
        modal run scripts/modal_legislation.py --jurisdiction state-CA --limit 100
        modal run scripts/modal_legislation.py --jurisdiction federal-US --dry-run
    """
    if stats_only:
        result = get_stats.remote(None)
        print("\n" + "=" * 60)
        print("Legislation Statistics")
        print("=" * 60)
        for state, s in result.items():
            if "error" in s:
                print(f"  {state}: Error - {s['error']}")
            else:
                status = "+" if s["with_full_text"] == s["total_bills"] and s["total_bills"] > 0 else "o"
                print(f"  {status} {state}: {s['with_full_text']}/{s['total_bills']} ({s['coverage_pct']})")
                print(f"      API calls needed: {s['api_calls_needed']}")
        print("=" * 60)
        print("\nNOTE: LegiScan free tier = 30,000 queries/month")
        print("      2 API calls per bill (getBill + getBillText)")
        print("=" * 60)
        return

    print(f"\nStarting legislation text fetch on Modal...")
    print(f"Jurisdiction: {jurisdiction}")
    if limit:
        print(f"Limit: {limit} bills")
    print(f"Dry run: {dry_run}")
    print("\nThis may take several hours for full datasets...\n")

    result = fetch_legislation_text.remote(
        jurisdiction=jurisdiction,
        limit=limit,
        dry_run=dry_run,
    )

    print("\n" + "=" * 60)
    print("Legislation Text Fetch Results")
    print("=" * 60)
    print(f"Jurisdiction: {result['jurisdiction']}")
    print(f"Bills processed: {result['bills_processed']}")
    print(f"Bills with text: {result['bills_with_text']}")
    print(f"Bills failed: {result.get('bills_failed', 0)}")
    print(f"API calls used: {result['api_calls']}")
    if not result["dry_run"]:
        print(f"Bills stored: {result['bills_with_text']}")
    else:
        print("Dry run - nothing stored")
    print(f"\nTiming:")
    print(f"  Total: {result['timing']['total_seconds']:.1f}s")
    if "cost" in result:
        print(f"\nCost:")
        print(f"  Memory: {result['cost']['memory_gb']}GB")
        print(f"  Estimated: ${result['cost']['estimated_cost_usd']:.4f}")
    print("=" * 60)
