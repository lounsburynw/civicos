"""
Modal function for municipal code fetch from Municode API.

This module provides serverless compute for fetching complete municipal code
sections from the Municode API. It solves the issue where only Title 1 sections
were fetched by re-fetching all titles with full_text content.

Architecture:
    Modal (compute) -> Municode API (source) -> Postgres (storage)

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal setup
    3. Create secret: modal secret create civic-db DATABASE_URL="postgresql://..."
    4. Deploy: modal deploy scripts/modal_municipal_code.py

Usage:
    # Fetch all municipal code sections for San Rafael
    modal run scripts/modal_municipal_code.py

    # Fetch specific jurisdiction
    modal run scripts/modal_municipal_code.py --jurisdiction city-san-rafael

    # Check current stats only
    modal run scripts/modal_municipal_code.py --stats-only

    # Dry run (fetch but don't store)
    modal run scripts/modal_municipal_code.py --dry-run
"""

import modal

# Define the Modal app
app = modal.App("civic-municipal-code")

# Build image with dependencies for Municode API access
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    # System dependencies for psycopg2
    .apt_install("libpq-dev", "gcc")
    # Python dependencies
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "httpx>=0.24.0",  # For Municode API calls
        # civic package dependencies
        "langgraph>=0.2.0",
    )
    # Add local civic packages
    .add_local_python_source("civicos", "civicos_extraction")
)


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,  # 4GB sufficient - streaming iterator, low memory usage
    timeout=7200,  # 2 hours - Municode rate limit means slow fetch
    retries=modal.Retries(
        max_retries=2,
        backoff_coefficient=2.0,
        initial_delay=30.0,  # Longer delay for API rate limits
    ),
)
def fetch_municipal_code(
    jurisdiction: str = "city-san-rafael",
    dry_run: bool = False,
    rate_limit: float = 2.0,
) -> dict:
    """
    Fetch complete municipal code from Municode API and store to Postgres.

    Args:
        jurisdiction: Jurisdiction ID (e.g., "city-san-rafael")
        dry_run: If True, fetch but don't store to database
        rate_limit: Requests per second (default 2.0)

    Returns:
        Dict with fetch results including section counts and timing
    """
    import logging
    import os
    import time
    from dataclasses import asdict

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger(__name__)

    start_time = time.time()

    from civicos._internal.legal.corpus.municipal import MunicipalCodeCorpus
    from civicos.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    logger.info(f"Starting municipal code fetch: jurisdiction={jurisdiction}")
    logger.info(f"Parameters: dry_run={dry_run}, rate_limit={rate_limit}")

    # Initialize corpus with rate limiting
    corpus = MunicipalCodeCorpus(
        jurisdiction_id=jurisdiction,
        rate_limit=rate_limit,
    )

    # Fetch all sections via streaming iterator
    sections = []
    titles_seen = set()
    try:
        logger.info("Fetching sections from Municode API...")
        for section in corpus.stream_sections():
            sections.append(asdict(section))
            titles_seen.add(section.title_number)

            # Progress logging every 100 sections
            if len(sections) % 100 == 0:
                logger.info(f"  Fetched {len(sections)} sections...")

    finally:
        corpus.close()

    fetch_time = time.time() - start_time
    logger.info(f"Fetched {len(sections)} sections from {len(titles_seen)} titles in {fetch_time:.1f}s")

    # Count sections with full_text
    with_text = sum(1 for s in sections if s.get("full_text"))
    logger.info(f"Sections with full_text: {with_text}/{len(sections)} ({with_text/len(sections)*100:.1f}%)")

    # Store to database unless dry run
    stored_count = 0
    if not dry_run:
        logger.info("Storing sections to Postgres...")
        store_start = time.time()

        backend = PostgresBackend(database_url)
        stored_count = backend.store_municipal_code(
            jurisdiction_id=jurisdiction,
            sections=sections,
        )

        store_time = time.time() - store_start
        logger.info(f"Stored {stored_count} sections in {store_time:.1f}s")
    else:
        logger.info("Dry run - skipping database storage")

    # Calculate cost estimate
    elapsed_seconds = time.time() - start_time
    memory_gb = 4  # Configured memory
    gb_seconds = memory_gb * elapsed_seconds
    estimated_cost = gb_seconds * 0.000463  # Modal CPU pricing

    logger.info(f"Total time: {elapsed_seconds:.1f}s")
    logger.info(f"Cost: {elapsed_seconds:.0f}s × {memory_gb}GB = ${estimated_cost:.4f}")

    return {
        "jurisdiction": jurisdiction,
        "sections_fetched": len(sections),
        "sections_with_text": with_text,
        "sections_stored": stored_count,
        "titles_fetched": len(titles_seen),
        "dry_run": dry_run,
        "timing": {
            "fetch_seconds": fetch_time,
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
def get_stats(jurisdiction: str = "city-san-rafael") -> dict:
    """
    Get current municipal code statistics from database.

    Args:
        jurisdiction: Jurisdiction ID

    Returns:
        Dict with section counts and full_text coverage
    """
    import os

    from civicos.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    sections = backend.get_municipal_code(jurisdiction)

    total = len(sections)
    with_text = sum(1 for s in sections if s.get("full_text"))

    # Count by title
    titles = {}
    for s in sections:
        title = s.get("title_number", "unknown")
        if title not in titles:
            titles[title] = {"total": 0, "with_text": 0}
        titles[title]["total"] += 1
        if s.get("full_text"):
            titles[title]["with_text"] += 1

    return {
        "jurisdiction": jurisdiction,
        "total_sections": total,
        "with_full_text": with_text,
        "coverage_pct": f"{with_text/total*100:.1f}%" if total > 0 else "N/A",
        "by_title": titles,
    }


@app.local_entrypoint()
def main(
    jurisdiction: str = "city-san-rafael",
    dry_run: bool = False,
    stats_only: bool = False,
    rate_limit: float = 2.0,
):
    """
    CLI entrypoint for modal run.

    Examples:
        modal run scripts/modal_municipal_code.py
        modal run scripts/modal_municipal_code.py --stats-only
        modal run scripts/modal_municipal_code.py --dry-run
        modal run scripts/modal_municipal_code.py --jurisdiction city-san-rafael
    """
    if stats_only:
        result = get_stats.remote(jurisdiction)
        print("\n" + "=" * 60)
        print(f"Municipal Code Statistics for {jurisdiction}")
        print("=" * 60)
        print(f"Total sections: {result['total_sections']}")
        print(f"With full_text: {result['with_full_text']} ({result['coverage_pct']})")
        print("\nBy Title:")
        for title, counts in sorted(result["by_title"].items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
            status = "✓" if counts["with_text"] == counts["total"] else "○"
            pct = counts["with_text"] / counts["total"] * 100 if counts["total"] > 0 else 0
            print(f"  {status} Title {title:>2}: {counts['with_text']:>4}/{counts['total']:<4} ({pct:.0f}%)")
        print("=" * 60)
        return

    print(f"\nStarting municipal code fetch on Modal...")
    print(f"Jurisdiction: {jurisdiction}")
    print(f"Dry run: {dry_run}")
    print(f"Rate limit: {rate_limit} req/s")
    print("\nThis may take 20-30 minutes due to Municode API rate limits...\n")

    result = fetch_municipal_code.remote(
        jurisdiction=jurisdiction,
        dry_run=dry_run,
        rate_limit=rate_limit,
    )

    print("\n" + "=" * 60)
    print("Municipal Code Fetch Results")
    print("=" * 60)
    print(f"Jurisdiction: {result['jurisdiction']}")
    print(f"Sections fetched: {result['sections_fetched']}")
    print(f"Sections with text: {result['sections_with_text']}")
    print(f"Titles fetched: {result['titles_fetched']}")
    if not result["dry_run"]:
        print(f"Sections stored: {result['sections_stored']}")
    else:
        print("Dry run - nothing stored")
    print(f"\nTiming:")
    print(f"  Fetch: {result['timing']['fetch_seconds']:.1f}s")
    print(f"  Total: {result['timing']['total_seconds']:.1f}s")
    print(f"\nCost:")
    print(f"  Memory: {result['cost']['memory_gb']}GB")
    print(f"  Estimated: ${result['cost']['estimated_cost_usd']:.4f}")
    print("=" * 60)
