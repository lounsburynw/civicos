"""
Modal function for Executive Orders ingestion from Federal Register API.

Fetches Executive Orders from the Federal Register API and stores them
in the dedicated executive_orders table.

Setup:
    Ensure Modal secrets exist:
    modal secret create civic-db DATABASE_URL="postgresql://..."

Usage:
    # Dry run (fetch and parse only)
    modal run scripts/modal_executive_orders.py --dry-run

    # Ingest all EOs
    modal run scripts/modal_executive_orders.py

    # Stats only
    modal run scripts/modal_executive_orders.py --stats-only

    # Fetch with full text (slower, fetches each EO's text)
    modal run scripts/modal_executive_orders.py --fetch-text

Data source: https://www.federalregister.gov/developers/documentation/api/v1
"""

import modal
import os

# Define the Modal app
app = modal.App("civic-executive-orders")

# Build image with dependencies
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "httpx>=0.24.0",
        "langgraph>=0.2.0",
        "langchain-core>=0.3.0",
    )
    .add_local_python_source("civic")
)

# Federal Register API configuration
FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1"
PER_PAGE = 100  # Max allowed by API


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
    ],
    memory=2048,
    timeout=3600,  # 1 hour
)
def ingest_executive_orders(
    dry_run: bool = False,
    stats_only: bool = False,
    fetch_text: bool = False,
    page_limit: int = 0,  # 0 = all pages
) -> dict:
    """
    Ingest Executive Orders from Federal Register API to PostgreSQL.

    Args:
        dry_run: Parse only, don't store
        stats_only: Show database stats only
        fetch_text: Fetch full text for each EO (slower)
        page_limit: Max pages to fetch (0 = all)

    Returns:
        Dict with ingestion results
    """
    import time
    import httpx
    from html import unescape
    import re

    # Get database connection
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not set"}

    # Stats only mode
    if stats_only:
        from civic.storage.postgres_backend import PostgresBackend
        db = PostgresBackend(database_url)
        count = db.get_executive_orders_count()
        return {
            "executive_orders_in_db": count,
        }

    # Fetch EOs from Federal Register API
    print("Fetching Executive Orders from Federal Register API...")
    start = time.time()

    # Fields to request
    fields = [
        "document_number",
        "title",
        "signing_date",
        "publication_date",
        "executive_order_number",
        "abstract",
        "html_url",
        "pdf_url",
        "raw_text_url",
        "president",
    ]
    fields_param = "&".join(f"fields[]={f}" for f in fields)

    all_orders = []
    page = 1
    total_pages = None

    with httpx.Client(timeout=60.0) as client:
        while True:
            url = (
                f"{FEDERAL_REGISTER_API}/documents.json?"
                f"conditions[presidential_document_type]=executive_order"
                f"&per_page={PER_PAGE}&page={page}&{fields_param}"
            )

            print(f"Fetching page {page}...")
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

            if total_pages is None:
                total_pages = data.get("total_pages", 1)
                print(f"Total: {data.get('count', 0)} EOs across {total_pages} pages")

            results = data.get("results", [])
            if not results:
                break

            all_orders.extend(results)
            print(f"  Got {len(results)} orders (total: {len(all_orders)})")

            # Check if we've reached the limit
            if page_limit > 0 and page >= page_limit:
                print(f"Reached page limit ({page_limit})")
                break

            # Check if there are more pages
            if not data.get("next_page_url"):
                break

            page += 1

    fetch_time = time.time() - start
    print(f"Fetched {len(all_orders)} Executive Orders in {fetch_time:.1f}s")

    # Optionally fetch full text for each order
    if fetch_text:
        print("Fetching full text for each order...")
        text_start = time.time()
        with httpx.Client(timeout=30.0) as client:
            for i, order in enumerate(all_orders):
                if order.get("raw_text_url"):
                    try:
                        resp = client.get(order["raw_text_url"])
                        if resp.status_code == 200:
                            # Clean HTML from text response
                            text = resp.text
                            # Remove HTML tags
                            text = re.sub(r'<[^>]+>', ' ', text)
                            # Unescape HTML entities
                            text = unescape(text)
                            # Normalize whitespace
                            text = re.sub(r'\s+', ' ', text).strip()
                            order["full_text"] = text
                    except Exception as e:
                        print(f"  Error fetching text for {order.get('document_number')}: {e}")

                if (i + 1) % 50 == 0:
                    print(f"  Fetched text for {i + 1}/{len(all_orders)} orders")

        text_time = time.time() - text_start
        print(f"Fetched text in {text_time:.1f}s")

    # Transform to executive_orders format (proper schema)
    orders_for_storage = []
    for order in all_orders:
        # President info
        president = order.get("president", {})
        president_name = president.get("name", "Unknown") if isinstance(president, dict) else "Unknown"
        president_id = president.get("identifier") if isinstance(president, dict) else None

        eo = {
            "eo_number": int(order.get("executive_order_number")) if order.get("executive_order_number") else None,
            "document_number": order.get("document_number"),
            "title": order.get("title", ""),
            "abstract": order.get("abstract"),
            "full_text": order.get("full_text"),  # Will be None unless fetch_text=True
            "president": president_name,
            "president_id": president_id,
            "signing_date": order.get("signing_date"),
            "publication_date": order.get("publication_date"),
            "html_url": order.get("html_url"),
            "pdf_url": order.get("pdf_url"),
            "raw_text_url": order.get("raw_text_url"),
            "status": "active",  # Default status
        }
        orders_for_storage.append(eo)

    print(f"Prepared {len(orders_for_storage)} orders for storage")

    if dry_run:
        # Show sample
        sample = orders_for_storage[0] if orders_for_storage else None
        return {
            "executive_orders_fetched": len(all_orders),
            "orders_prepared": len(orders_for_storage),
            "dry_run": True,
            "sample": sample,
            "fetch_time_s": fetch_time,
        }

    # Store to PostgreSQL using new dedicated method
    print("Storing to PostgreSQL...")
    from civic.storage.postgres_backend import PostgresBackend
    db = PostgresBackend(database_url)

    store_start = time.time()
    stored = db.store_executive_orders(
        orders=orders_for_storage,
        use_copy=True,
    )
    store_time = time.time() - store_start

    print(f"Stored {stored} orders in {store_time:.1f}s")

    # Get final count
    total = db.get_executive_orders_count()

    return {
        "executive_orders_fetched": len(all_orders),
        "orders_stored": stored,
        "total_in_db": total,
        "fetch_time_s": fetch_time,
        "store_time_s": store_time,
    }


@app.local_entrypoint()
def main(
    dry_run: bool = False,
    stats_only: bool = False,
    fetch_text: bool = False,
    page_limit: int = 0,
):
    """CLI entrypoint for Modal."""
    print("=" * 50)
    print("EXECUTIVE ORDERS INGESTION")
    print("=" * 50)

    result = ingest_executive_orders.remote(
        dry_run=dry_run,
        stats_only=stats_only,
        fetch_text=fetch_text,
        page_limit=page_limit,
    )

    print("\n" + "=" * 50)
    print("RESULT:")
    for key, value in result.items():
        if key == "sample" and value:
            print(f"  sample:")
            for k, v in value.items():
                if k == "full_text" and v:
                    print(f"    {k}: {v[:100]}...")
                else:
                    print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")
    print("=" * 50)
