"""
Daily usage log rollup — aggregates old platform_usage_logs into
platform_usage_daily, then deletes raw rows older than 90 days.

Keeps the usage_logs table bounded regardless of traffic growth.

Deploy:
    modal deploy scripts/modal_usage_rollup.py

Run manually:
    modal run scripts/modal_usage_rollup.py::rollup_usage_logs
"""

import os
import logging

import modal

logger = logging.getLogger(__name__)

app = modal.App("civicos-usage-rollup")


@app.function(
    secrets=[modal.Secret.from_name("civicos-platform")],
    schedule=modal.Cron("0 3 * * *"),  # Daily at 3 AM UTC
    timeout=300,
)
def rollup_usage_logs():
    """Aggregate usage logs older than 90 days into daily rollups, then purge."""
    import psycopg2

    database_url = os.environ.get("PLATFORM_DATABASE_URL")
    if not database_url:
        logger.error("PLATFORM_DATABASE_URL not set, skipping rollup")
        return {"status": "skipped", "reason": "no database url"}

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            # Step 1: Aggregate logs older than 90 days into daily rollups
            cur.execute("""
                INSERT INTO platform_usage_daily (key_id, endpoint, date, request_count, avg_response_ms, error_count)
                SELECT
                    key_id,
                    endpoint,
                    DATE(timestamp) as date,
                    COUNT(*) as request_count,
                    AVG(response_time_ms)::int as avg_response_ms,
                    COUNT(*) FILTER (WHERE status_code >= 400) as error_count
                FROM platform_usage_logs
                WHERE timestamp < NOW() - INTERVAL '90 days'
                  AND key_id IS NOT NULL
                GROUP BY key_id, endpoint, DATE(timestamp)
                ON CONFLICT (key_id, endpoint, date) DO UPDATE SET
                    request_count = platform_usage_daily.request_count + EXCLUDED.request_count,
                    avg_response_ms = (
                        (platform_usage_daily.avg_response_ms * platform_usage_daily.request_count
                         + EXCLUDED.avg_response_ms * EXCLUDED.request_count)
                        / (platform_usage_daily.request_count + EXCLUDED.request_count)
                    )::int,
                    error_count = platform_usage_daily.error_count + EXCLUDED.error_count
            """)
            aggregated = cur.rowcount
            logger.info("Aggregated %d daily rollup rows", aggregated)

            # Step 2: Delete raw logs older than 90 days
            cur.execute("""
                DELETE FROM platform_usage_logs
                WHERE timestamp < NOW() - INTERVAL '90 days'
            """)
            deleted = cur.rowcount
            logger.info("Deleted %d raw usage log rows older than 90 days", deleted)

        conn.commit()

        result = {
            "status": "completed",
            "aggregated_rows": aggregated,
            "deleted_rows": deleted,
        }
        print(f"Usage rollup complete: {result}")
        return result

    except Exception as e:
        conn.rollback()
        logger.error("Usage rollup failed: %s", e)
        raise
    finally:
        conn.close()
