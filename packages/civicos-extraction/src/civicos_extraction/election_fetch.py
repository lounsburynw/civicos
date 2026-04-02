"""Shared election fetch logic — callable from onboard and scheduled cron.

This module provides a single entry point for fetching all configured election
data for a jurisdiction. It dispatches to the appropriate extraction clients
based on the election_sources config, with no Modal dependency.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _check_partial_fetch(
    jurisdiction_id: str,
    source_key: str,
    backend: Any,
    new_election_count: int,
    new_contest_count: int,
) -> None:
    """Log a warning if a fetch returned significantly fewer results than stored.

    Election data can legitimately shrink (Clarity purges old elections, SOS
    overwrites per-cycle), so this warns rather than blocks. The warning
    enables operators to investigate unexpected drops via logs.
    """
    try:
        existing_count = backend.get_election_count(jurisdiction_id)
    except Exception:
        return  # Can't check — skip silently

    if existing_count > 0 and new_election_count == 0 and new_contest_count == 0:
        logger.warning(
            f"  [{jurisdiction_id}] {source_key}: fetch returned 0 elections/contests "
            f"but {existing_count} elections already stored. Possible source outage "
            f"or data purge. Stored data is unchanged (upsert-safe).",
        )
    elif existing_count > 2 and new_election_count < existing_count * 0.5:
        logger.warning(
            f"  [{jurisdiction_id}] {source_key}: fetch returned {new_election_count} "
            f"elections vs {existing_count} previously stored (>{50}% drop). "
            f"May indicate partial fetch or source changes.",
        )


# Handler registry — maps election source keys to fetch functions.
# Each handler has signature: (jurisdiction_id, config, backend) -> Dict[str, Any]
# Register new handlers here when implementing a new state's fetch client.
_FETCH_HANDLERS: Dict[str, Any] = {}


def fetch_elections_for_jurisdiction(
    jurisdiction_id: str,
    election_sources: Dict[str, Any],
    database_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch all configured election data for a single jurisdiction.

    Dispatches to registered fetch handlers based on the election_sources
    config dict (from data/extraction/<jid>.json). Sources without a
    registered handler are reported as skipped, not silently ignored.

    Args:
        jurisdiction_id: e.g. "city-san-rafael"
        election_sources: The election_sources dict from the jurisdiction config
        database_url: Postgres connection string. Falls back to DATABASE_URL env var.

    Returns:
        Dict with per-source results. Each source key maps to a dict with
        counts or error info. Never raises — all errors are caught per-source.
    """
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not available — election fetch skipped"}

    if not election_sources:
        return {"skipped": True, "reason": "no election sources configured"}

    from civicos.storage.postgres_backend import PostgresBackend

    backend = PostgresBackend(database_url)
    results: Dict[str, Any] = {}
    start_time = time.time()

    # Dispatch each source to its registered handler
    for source_key, source_config in election_sources.items():
        handler = _FETCH_HANDLERS.get(source_key)
        if handler is not None:
            results[source_key] = handler(jurisdiction_id, source_config, backend)
        else:
            logger.info(
                f"  [{jurisdiction_id}] Election source '{source_key}' detected "
                f"but no fetch client available yet — skipping."
            )
            results[source_key] = {
                "status": "skipped",
                "reason": f"no fetch client for '{source_key}'",
            }

    # --- Elected Officials (always attempted, independent of source handlers) ---
    results["elected_officials"] = _fetch_officials(jurisdiction_id, backend)

    elapsed = time.time() - start_time
    results["elapsed_seconds"] = round(elapsed, 1)
    return results


def _fetch_civera(
    jurisdiction_id: str, config: Any, backend: Any,
) -> Dict[str, Any]:
    """Fetch from Civera ElectionStats GraphQL."""
    try:
        from civicos_extraction.clients.civera_election_stats import (
            CIVERA_INSTANCES,
            CiveraElectionStatsClient,
            extract_civera_results_to_storage,
        )

        if config is True:
            config = {}

        county_slug = config.get("county_slug", "")
        graphql_url = config.get("graphql_url", "")
        from_year = config.get("from_year", 2010)
        division_filter = config.get("division_filter", "")

        if not county_slug:
            county_slug = jurisdiction_id.replace("county-", "").replace("city-", "")
        if not graphql_url:
            instance = CIVERA_INSTANCES.get(county_slug)
            if instance:
                graphql_url = instance["graphql_url"]
            else:
                return {"status": "skipped", "reason": f"county {county_slug!r} not in CIVERA_INSTANCES"}

        logger.info(f"  [{jurisdiction_id}] Fetching elections (Civera, county={county_slug})...")

        client = CiveraElectionStatsClient(
            jurisdiction_id=jurisdiction_id,
            graphql_url=graphql_url,
            county_slug=county_slug,
        )
        validation = client.validate()
        if not validation.is_valid:
            return {"status": "failed", "error": f"Validation failed: {validation.errors}"}

        counts = extract_civera_results_to_storage(
            client=client,
            storage=backend,
            jurisdiction_id=jurisdiction_id,
            county_slug=county_slug,
            from_year=from_year,
            division_filter=division_filter or None,
        )

        _check_partial_fetch(
            jurisdiction_id, "civera_election_stats", backend,
            counts["elections"], counts["contests"],
        )

        backend.update_refresh_metadata(
            jurisdiction_id, "elections", "civera_election_stats",
            items_fetched=counts["elections"] + counts["contests"],
            items_stored=counts["elections"] + counts["contests"],
            status="completed",
        )

        logger.info(f"    Civera: {counts['elections']} elections, {counts['contests']} contests stored")
        return {
            "status": "completed",
            "elections_stored": counts["elections"],
            "contests_stored": counts["contests"],
            "candidates_stored": counts["candidates"],
        }
    except Exception as e:
        logger.warning(f"  [{jurisdiction_id}] Civera fetch failed: {e}")
        return {"status": "failed", "error": str(e)}


def _fetch_ca_sos(
    jurisdiction_id: str, config: Any, backend: Any,
) -> Dict[str, Any]:
    """Fetch from CA Secretary of State API."""
    try:
        from civicos_extraction.clients.ca_sos_results import (
            CASOSResultsClient,
            extract_ca_sos_results_to_storage,
        )

        if config is True:
            config = {}

        county = config.get("county", "")
        districts = config.get("districts", {})

        logger.info(f"  [{jurisdiction_id}] Fetching elections (CA SOS, county={county or 'statewide'})...")

        client = CASOSResultsClient(jurisdiction_id=jurisdiction_id)
        validation = client.validate()
        if not validation.is_valid:
            return {"status": "failed", "error": f"Validation failed: {validation.errors}"}

        counts = extract_ca_sos_results_to_storage(
            client=client,
            storage=backend,
            jurisdiction_id=jurisdiction_id,
            county=county or None,
            districts=districts or None,
        )

        _check_partial_fetch(
            jurisdiction_id, "ca_sos_results", backend,
            counts["elections"], counts["contests"],
        )

        backend.update_refresh_metadata(
            jurisdiction_id, "elections", "ca_sos_results",
            items_fetched=counts["contests"],
            items_stored=counts["contests"],
            status="completed",
        )

        logger.info(f"    CA SOS: {counts['contests']} contests stored")
        return {
            "status": "completed",
            "elections_stored": counts["elections"],
            "contests_stored": counts["contests"],
            "candidates_stored": counts["candidates"],
            "ballot_measures_stored": counts["ballot_measures"],
        }
    except Exception as e:
        logger.warning(f"  [{jurisdiction_id}] CA SOS fetch failed: {e}")
        return {"status": "failed", "error": str(e)}


def _fetch_officials(
    jurisdiction_id: str, backend: Any,
) -> Dict[str, Any]:
    """Fetch elected officials (federal, state, local)."""
    try:
        from civicos_extraction.clients.representatives import (
            RepresentativesClient,
            extract_elected_officials_to_storage,
        )

        congress_key = os.environ.get("CONGRESS_GOV_API_KEY") or os.environ.get("FAC_API_KEY")
        legiscan_key = os.environ.get("LEGISCAN_API_KEY")

        # Skip if no API keys available (common in local dev)
        if not congress_key and not legiscan_key:
            logger.info(f"  [{jurisdiction_id}] Skipping officials fetch — no API keys available")
            return {"status": "skipped", "reason": "no API keys (CONGRESS_GOV_API_KEY, LEGISCAN_API_KEY)"}

        logger.info(f"  [{jurisdiction_id}] Fetching elected officials...")

        client = RepresentativesClient(
            jurisdiction_id=jurisdiction_id,
            congress_api_key=congress_key,
            legiscan_api_key=legiscan_key,
        )

        stored = extract_elected_officials_to_storage(
            client=client,
            storage=backend,
            jurisdiction_id=jurisdiction_id,
        )

        logger.info(f"    Officials: {stored} stored")
        return {"status": "completed", "officials_stored": stored}
    except Exception as e:
        logger.warning(f"  [{jurisdiction_id}] Officials fetch failed: {e}")
        return {"status": "failed", "error": str(e)}


def _fetch_clarity(
    jurisdiction_id: str, config: Any, backend: Any,
) -> Dict[str, Any]:
    """Fetch from Clarity Elections ENR."""
    try:
        from civicos_extraction.clients.clarity_elections import (
            ClarityElectionsClient,
            extract_clarity_results_to_storage,
        )

        if config is True:
            config = {}

        county = config.get("county", "")
        url_name = config.get("url_name", "")
        state = config.get("state", "")

        if not county:
            return {"status": "skipped", "reason": "no county configured"}
        if not state:
            return {"status": "skipped", "reason": "no state configured for clarity_elections"}

        logger.info(
            f"  [{jurisdiction_id}] Fetching elections "
            f"(Clarity, county={county})...",
        )

        client = ClarityElectionsClient(
            jurisdiction_id=jurisdiction_id,
            state=state,
            county=county,
            url_name=url_name or None,
        )
        validation = client.validate()
        if not validation.is_valid:
            return {
                "status": "failed",
                "error": f"Validation failed: {validation.errors}",
            }

        counts = extract_clarity_results_to_storage(
            client=client,
            storage=backend,
            jurisdiction_id=jurisdiction_id,
            county_slug=county,
            state=state,
        )

        _check_partial_fetch(
            jurisdiction_id, "clarity_elections", backend,
            counts["elections"], counts["contests"],
        )

        backend.update_refresh_metadata(
            jurisdiction_id,
            "elections",
            "clarity_elections",
            items_fetched=counts["elections"] + counts["contests"],
            items_stored=counts["elections"] + counts["contests"],
            status="completed",
        )

        logger.info(
            f"    Clarity: {counts['elections']} elections, "
            f"{counts['contests']} contests stored",
        )
        return {
            "status": "completed",
            "elections_stored": counts["elections"],
            "contests_stored": counts["contests"],
            "candidates_stored": counts["candidates"],
        }
    except Exception as e:
        logger.warning(f"  [{jurisdiction_id}] Clarity fetch failed: {e}")
        return {"status": "failed", "error": str(e)}


# Register fetch handlers for source keys with working clients.
# Add new entries here when implementing a state's extraction client.
_FETCH_HANDLERS["civera_election_stats"] = _fetch_civera
_FETCH_HANDLERS["ca_sos_results"] = _fetch_ca_sos
_FETCH_HANDLERS["clarity_elections"] = _fetch_clarity
