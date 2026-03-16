"""
Jurisdiction Onboarding

Unified flow for onboarding a new jurisdiction from just a URL.
Detects the civic platform, runs platform-specific discovery, and
generates an ExtractionConfig JSON file.

Usage:
    from civicos_extraction.onboard import onboard_jurisdiction, estimate_costs

    result = onboard_jurisdiction("https://marin.granicus.com", "county-marin")
    if result.success:
        print(f"Config saved to: {result.config_path}")
        print(f"Discovered bodies: {result.discovered_bodies}")

    # Cost estimation from cost_registry.yaml
    estimate = estimate_costs(meeting_count=20, avg_meeting_hours=2.0)
    print(estimate.format())
"""

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from civicos_extraction.platform_detection import detect_platform

logger = logging.getLogger(__name__)

# Path to cost_registry.yaml (relative to repo root)
# Lazy computation — parents[4] fails on Modal where directory structure differs
def _get_cost_registry_path() -> Path:
    try:
        return Path(__file__).parents[4] / "docs" / "public" / "cost_registry.yaml"
    except IndexError:
        return Path("/dev/null")  # Cost estimation not available on Modal


@dataclass
class CostEstimate:
    """Cost estimate for onboarding a jurisdiction."""

    meeting_count: int
    avg_meeting_hours: float
    tiers_enabled: Dict[str, bool]
    line_items: List[Dict[str, Any]]
    monthly_total_low: float
    monthly_total_high: float
    onetime_backfill: float
    registry_date: str
    user_count: int = 0
    cost_per_query: float = 0.0014
    queries_per_user_month: int = 20
    infrastructure_base: float = 51.0  # 2x Supabase ($50) + DNS ($1)

    def format(self) -> str:
        """Format as human-readable cost summary."""
        lines = [
            f"Cost Estimate ({self.meeting_count} meetings/mo, {self.avg_meeting_hours}hr avg)",
            "=" * 60,
            "",
            "INFRASTRUCTURE (fixed)",
            f"  Supabase (main + relay)        $50.00/mo        (exact)",
            f"  Domain/DNS                      $1.00/mo        (exact)",
            f"  Modal compute                   $0.00/mo        (observed, within $30 free credits)",
            f"  Cloudflare R2                  $0-5.00/mo       (estimated)",
        ]

        lines.append("")
        lines.append("INGESTION (per meeting)")

        for item in self.line_items:
            enabled = "ON" if item["enabled"] else "OFF"
            if item["enabled"]:
                lines.append(
                    f"  [{enabled}] {item['step']:<30} ${item['cost_low']:.2f}-${item['cost_high']:.2f}/mo"
                    f"  ({item['confidence']})"
                )
            else:
                lines.append(f"  [{enabled}] {item['step']:<30} --")

        lines.append("")
        lines.append("USER QUERIES (per user, observed)")
        llm_monthly = self.cost_per_query * self.queries_per_user_month * self.user_count
        lines.append(
            f"  {self.user_count} users * {self.queries_per_user_month} queries/mo"
            f" * ${self.cost_per_query}/query = ${llm_monthly:.2f}/mo"
        )

        lines.append("")
        lines.append("-" * 60)
        total_low = self.infrastructure_base + self.monthly_total_low + llm_monthly
        total_high = self.infrastructure_base + 5 + self.monthly_total_high + llm_monthly  # +5 for R2
        lines.append(
            f"  TOTAL:  ${total_low:.2f} - ${total_high:.2f}/mo"
        )
        if self.onetime_backfill > 0:
            lines.append(f"  One-time backfill: ${self.onetime_backfill:.2f}")
        lines.append(f"  (Prices from cost_registry.yaml, updated {self.registry_date})")
        return "\n".join(lines)


def _load_cost_registry() -> Dict[str, Any]:
    """Load cost_registry.yaml."""
    try:
        import yaml
    except ImportError:
        # Fallback: parse enough YAML-like structure manually
        raise ImportError("PyYAML required for cost estimation: pip install pyyaml")

    path = _get_cost_registry_path()
    if not path.exists():
        raise FileNotFoundError(f"Cost registry not found: {path}")

    with open(path) as f:
        return yaml.safe_load(f)


def estimate_costs(
    meeting_count: int = 10,
    avg_meeting_hours: float = 2.0,
    tiers: Optional[Dict[str, bool]] = None,
    include_backfill: int = 0,
    user_count: int = 10,
    queries_per_user_month: int = 20,
) -> CostEstimate:
    """Estimate monthly costs for a jurisdiction.

    Reads unit prices from docs/private/operations/cost_registry.yaml.

    Args:
        meeting_count: Expected meetings per month.
        avg_meeting_hours: Average meeting duration in hours.
        tiers: Which ingestion steps to enable. Defaults to standard (no transcription).
            Keys: meetings, pdf_chunks, issues, municipal_code, agenda_items,
                  decisions, legislation, transcription, diarization, vector_indexing
        include_backfill: Number of historical meetings to backfill (0 = none).
        user_count: Expected number of active users per month.
        queries_per_user_month: Estimated queries per user per month (default: 20).

    Returns:
        CostEstimate with itemized costs and totals.
    """
    registry = _load_cost_registry()
    registry_date = registry.get("last_updated", "unknown")
    per_meeting = registry.get("per_meeting_costs", {})
    services = registry.get("services", {})

    # Default tiers: standard without transcription
    default_tiers = {
        "meetings": True,
        "pdf_chunks": True,
        "issues": True,
        "municipal_code": True,
        "agenda_items": True,
        "decisions": True,
        "legislation": True,
        "transcription": False,
        "diarization": False,
        "vector_indexing": True,
    }
    enabled = {**default_tiers, **(tiers or {})}
    # Diarization requires transcription
    if enabled.get("diarization") and not enabled.get("transcription"):
        enabled["diarization"] = False

    line_items = []
    total_low = 0.0
    total_high = 0.0

    # Tier 1: Free steps
    for step in ["meetings", "pdf_chunks", "issues", "municipal_code"]:
        line_items.append({
            "tier": 1, "step": step, "enabled": enabled.get(step, False),
            "cost_low": 0.0, "cost_high": 0.0, "confidence": "exact",
        })

    # Tier 2: LLM extraction
    agenda_cost = per_meeting.get("tier_2_llm", {}).get("agenda_extraction", {})
    # Parse cost range like "$0.01-0.05"
    agenda_low, agenda_high = 0.01, 0.05
    decision_low, decision_high = 0.01, 0.10

    agenda_monthly_low = agenda_low * meeting_count if enabled.get("agenda_items") else 0
    agenda_monthly_high = agenda_high * meeting_count if enabled.get("agenda_items") else 0
    line_items.append({
        "tier": 2, "step": "agenda_items", "enabled": enabled.get("agenda_items", False),
        "cost_low": agenda_monthly_low, "cost_high": agenda_monthly_high,
        "confidence": "estimated",
    })
    total_low += agenda_monthly_low
    total_high += agenda_monthly_high

    decision_monthly_low = decision_low * meeting_count if enabled.get("decisions") else 0
    decision_monthly_high = decision_high * meeting_count if enabled.get("decisions") else 0
    line_items.append({
        "tier": 2, "step": "decisions", "enabled": enabled.get("decisions", False),
        "cost_low": decision_monthly_low, "cost_high": decision_monthly_high,
        "confidence": "estimated",
    })
    total_low += decision_monthly_low
    total_high += decision_monthly_high

    line_items.append({
        "tier": 2, "step": "legislation", "enabled": enabled.get("legislation", False),
        "cost_low": 0.0, "cost_high": 0.0, "confidence": "exact",
    })

    # Tier 3: Transcription
    aai = services.get("assemblyai", {}).get("pricing", {})
    transcription_rate = aai.get("universal_3_pro_per_hour", 0.21)
    diarization_rate = aai.get("diarization_addon_per_hour", 0.02)

    hourly_rate = transcription_rate
    if enabled.get("diarization"):
        hourly_rate += diarization_rate

    transcription_monthly = hourly_rate * avg_meeting_hours * meeting_count if enabled.get("transcription") else 0
    line_items.append({
        "tier": 3, "step": "transcription" + (" + diarization" if enabled.get("diarization") else ""),
        "enabled": enabled.get("transcription", False),
        "cost_low": transcription_monthly, "cost_high": transcription_monthly,
        "confidence": "exact",
    })
    total_low += transcription_monthly
    total_high += transcription_monthly

    # Tier 4: Vectors
    vector_low = 0.05 if enabled.get("vector_indexing") else 0
    vector_high = 0.15 if enabled.get("vector_indexing") else 0
    line_items.append({
        "tier": 4, "step": "vector_indexing", "enabled": enabled.get("vector_indexing", False),
        "cost_low": vector_low, "cost_high": vector_high,
        "confidence": "estimated",
    })
    total_low += vector_low
    total_high += vector_high

    # One-time backfill cost
    backfill = 0.0
    if include_backfill > 0:
        # Backfill = Tier 2 + optional Tier 3 per meeting
        backfill += (agenda_low + decision_low) * include_backfill
        if enabled.get("transcription"):
            backfill += hourly_rate * avg_meeting_hours * include_backfill

    # Read observed per-query cost from registry
    per_user = registry.get("per_user_costs", {})
    cost_per_query = per_user.get("observed_cost_per_query", 0.0014)

    return CostEstimate(
        meeting_count=meeting_count,
        avg_meeting_hours=avg_meeting_hours,
        tiers_enabled=enabled,
        line_items=line_items,
        monthly_total_low=total_low,
        monthly_total_high=total_high,
        onetime_backfill=backfill,
        registry_date=registry_date,
        user_count=user_count,
        cost_per_query=cost_per_query,
        queries_per_user_month=queries_per_user_month,
    )


@dataclass
class OnboardResult:
    """Result of jurisdiction onboarding."""

    success: bool
    jurisdiction_id: Optional[str] = None
    detection: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    config_path: Optional[str] = None
    discovered_bodies: Optional[Dict[str, str]] = None
    next_steps: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    validation: Optional[Any] = None  # ValidationReport from validate.py
    pipeline_result: Optional[Any] = None  # PipelineResult from pipeline.py


def _infer_jurisdiction_id(url: str) -> Optional[str]:
    """Infer a jurisdiction_id from a URL."""
    # Granicus: marin.granicus.com → county-marin (or city-marin)
    match = re.match(r"https?://([^.]+)\.granicus\.com", url)
    if match:
        return match.group(1)

    # eScribe: pub-nationalcity.escribemeetings.com → nationalcity
    match = re.match(r"https?://pub-([^.]+)\.escribemeetings\.com", url)
    if match:
        return match.group(1)

    # Simbli: srcs.simbli.com or simbli.eboardsolutions.com?S=... → subdomain
    match = re.match(r"https?://([^.]+)\.simbli\.com", url)
    if match:
        return match.group(1)

    # General city sites: cityofsanrafael.org → san-rafael
    from civicos_extraction.platform_detection import _extract_client_name

    return _extract_client_name(url)


def _discover_granicus(url: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run Granicus-specific discovery, including LLM column map and body name generation."""
    from civicos_extraction.clients.granicus import GranicusClient

    match = re.match(r"https?://([^.]+)\.granicus\.com", url)
    domain = match.group(1) if match else ""

    client = GranicusClient(
        granicus_domain=domain,
        jurisdiction_id=jurisdiction_id,
    )

    # Step 1: Probe view_ids to find pages with meeting data
    raw_views = client.discover_view_ids()

    # Step 2: Use LLM to assign body names (one-time, ~$0.0001)
    body_name_provenance = None
    try:
        naming_result = client.generate_body_names(raw_views)
        discovered = naming_result["archives"]
        body_name_provenance = naming_result.get("provenance")
        logger.info(f"Body names generated via LLM: {discovered}")
    except Exception as e:
        logger.warning(f"LLM body name generation failed, using view_N fallback: {e}")
        discovered = {f"view_{vid}": vid for vid in raw_views}

    # Determine best default view_id from discovery
    default_view_id = "1"
    if discovered:
        default_view_id = next(iter(discovered.values()))

    # Step 3: Generate column map via LLM (one-time, ~$0.0001)
    column_map = None
    column_map_provenance = None
    try:
        mapping_result = client.generate_column_map(view_id=default_view_id)
        column_map = mapping_result["column_map"]
        column_map_provenance = mapping_result.get("provenance")
        logger.info(f"Column map generated: {column_map}")
    except Exception as e:
        logger.warning(f"Column map generation failed (will use header detection): {e}")

    # Build ExtractionConfig dict
    metadata: Dict[str, Any] = {
        "granicus_domain": domain,
        "default_view_id": default_view_id,
    }
    if column_map:
        metadata["column_map"] = column_map
    if column_map_provenance:
        metadata["column_map_provenance"] = column_map_provenance
    if body_name_provenance:
        metadata["body_name_provenance"] = body_name_provenance

    config = {
        "source_id": f"granicus-{jurisdiction_id}",
        "source_type": "granicus",
        "jurisdiction_id": jurisdiction_id,
        "base_url": f"https://{domain}.granicus.com",
        "archives": discovered,
        "metadata": metadata,
    }

    return {
        "config": config,
        "discovered_bodies": discovered,
    }


def _discover_escribe(url: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run eScribe-specific discovery."""
    from civicos_extraction.clients.escribe import EScribeClient

    # Extract instance name from URL: pub-{instance}.escribemeetings.com
    match = re.match(r"https?://pub-([^.]+)\.escribemeetings\.com", url)
    instance_name = match.group(1) if match else ""

    client = EScribeClient(
        instance_name=instance_name,
        jurisdiction_id=jurisdiction_id,
    )

    # Discover meeting types
    archives = {}
    try:
        meeting_types = client.get_meeting_types()
        for mt in meeting_types:
            slug = re.sub(r"[^a-z0-9]+", "_", mt.lower()).strip("_")
            archives[slug] = mt
    except Exception as e:
        logger.warning(f"eScribe meeting type discovery failed: {e}")

    config = {
        "source_id": f"escribe-{jurisdiction_id}",
        "source_type": "escribe",
        "jurisdiction_id": jurisdiction_id,
        "base_url": url,
        "archives": archives,
        "metadata": {"instance_name": instance_name},
    }

    return {
        "config": config,
        "discovered_bodies": archives,
    }


def _discover_simbli(url: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run Simbli-specific discovery.

    Simbli uses Playwright for extraction, so discovery is lightweight —
    we just confirm the URL is valid and build config.
    """
    config = {
        "source_id": f"simbli-{jurisdiction_id}",
        "source_type": "simbli",
        "jurisdiction_id": jurisdiction_id,
        "base_url": url,
        "archives": {},
        "metadata": {"board_url": url},
    }

    return {
        "config": config,
        "discovered_bodies": {},
    }


def _discover_proudcity(url: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run ProudCity-specific discovery."""
    from civicos_extraction.clients.proudcity import ProudCityClient

    client = ProudCityClient(
        base_url=url,
        jurisdiction_id=jurisdiction_id,
    )

    discovered = client.discover_meeting_types()

    config = {
        "source_id": f"proudcity-{jurisdiction_id}",
        "source_type": "proudcity",
        "jurisdiction_id": jurisdiction_id,
        "base_url": url,
        "auto_discover": True,
        "archives": discovered,
    }

    return {
        "config": config,
        "discovered_bodies": discovered,
    }


# US state abbreviation → full name mapping for parent_jurisdictions slugs
_US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

_CANADIAN_PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia", "NT": "Northwest Territories",
    "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island",
    "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon",
}


_UK_NATIONS = {
    "ENG": "England", "SCT": "Scotland", "WLS": "Wales", "NIR": "Northern Ireland",
}


def _state_abbrev_to_slug(abbrev: str) -> str:
    """Convert state/province/nation abbreviation to jurisdiction slug (e.g., 'CA' -> 'california', 'ON' -> 'ontario', 'ENG' -> 'england')."""
    upper = abbrev.upper()
    name = _US_STATES.get(upper, "")
    if not name:
        name = _CANADIAN_PROVINCES.get(upper, "")
    if not name:
        name = _UK_NATIONS.get(upper, "")
    if not name:
        # Unknown code: return lowercased as-is (usable slug)
        return abbrev.lower().replace(" ", "-")
    return name.lower().replace(" ", "-")


def geocode_city(
    city_name: str,
    state: str = "",
    api_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Geocode a city to get county, zip code, and state confirmation.

    Uses Google Maps Geocoding API. Requires GOOGLE_MAPS_API_KEY env var
    or explicit api_key parameter.

    Args:
        city_name: City name (e.g., "Berkeley")
        state: State name or abbreviation (e.g., "CA", "California")
        api_key: Google Maps API key (falls back to env var)

    Returns:
        Dict with: city, county, state, zip_code, parent_jurisdictions
        None if geocoding fails or no API key
    """
    key = api_key or os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        logger.warning("No GOOGLE_MAPS_API_KEY — skipping geocoding enrichment")
        return None

    try:
        params = {
            "address": f"{city_name}, {state}",
            "key": key,
        }
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning(f"Geocoding failed for '{city_name}, {state}': {data.get('status')}")
            return None

        result = data["results"][0]
        components = result.get("address_components", [])

        parsed: Dict[str, str] = {}
        for comp in components:
            types = comp["types"]
            if "locality" in types:
                parsed["city"] = comp["long_name"]
            elif "administrative_area_level_2" in types:
                parsed["county"] = comp["long_name"]
            elif "administrative_area_level_1" in types:
                parsed["state"] = comp["long_name"]
                parsed["state_abbrev"] = comp["short_name"]
            elif "postal_code" in types:
                parsed["zip_code"] = comp["short_name"]
            elif "country" in types:
                parsed["country"] = comp["long_name"]
                parsed["country_code"] = comp["short_name"]

        # Build parent_jurisdictions based on country
        country = parsed.get("country", "")
        if not country:
            # No country in response — infer from state abbreviation
            if parsed.get("state_abbrev", "").upper() in _CANADIAN_PROVINCES:
                country = "Canada"
            else:
                country = "United States"  # safe default for this product's scope
        country_slug = country.strip().lower().replace(" ", "-")
        county_name = parsed.get("county", "")
        parent_jurisdictions = []

        if country == "United States":
            # US: county → state → country
            if county_name:
                county_slug = re.sub(r"\s*County$", "", county_name).strip().lower()
                county_slug = re.sub(r"\s+", "-", county_slug)
                parent_jurisdictions.append(f"county-{county_slug}")
            state_name = parsed.get("state", "")
            if state_name:
                state_slug = state_name.strip().lower().replace(" ", "-")
                parent_jurisdictions.append(f"state-{state_slug}")
            parent_jurisdictions.append("country-united-states")
        elif country == "Canada":
            # Canada: province → country
            state_name = parsed.get("state", "")
            if state_name:
                province_slug = state_name.strip().lower().replace(" ", "-")
                parent_jurisdictions.append(f"province-{province_slug}")
            parent_jurisdictions.append("country-canada")
        elif country == "United Kingdom":
            # UK: flat (councils don't have county/state hierarchy)
            parent_jurisdictions.append("country-united-kingdom")
        else:
            # Other countries: just country
            parent_jurisdictions.append(f"country-{country_slug}")

        return {
            "city": parsed.get("city", city_name),
            "county": county_name,
            "state": parsed.get("state", ""),
            "state_abbrev": parsed.get("state_abbrev", state.upper()),
            "zip_code": parsed.get("zip_code", ""),
            "country": country,
            "parent_jurisdictions": parent_jurisdictions,
        }

    except requests.RequestException as e:
        logger.warning(f"Geocoding request failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Geocoding error: {e}")
        return None


def _discover_legistar(client_name: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run Legistar-specific body discovery using the API."""
    from civicos_extraction.clients.legistar import LegistarClient

    client = LegistarClient(client_name=client_name, jurisdiction_id=jurisdiction_id)
    bodies = client.get_bodies()
    archives = {}
    for body in bodies:
        name = body.get("BodyName", "")
        body_id = str(body.get("BodyId", ""))
        if name and body_id:
            key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            archives[key] = body_id

    return {
        "config": {
            "source_id": f"legistar-{client_name}",
            "source_type": "legistar",
            "jurisdiction_id": jurisdiction_id,
            "base_url": f"https://webapi.legistar.com/v1/{client_name}",
            "archives": archives,
            "metadata": {"client_name": client_name, "body_count": len(bodies)},
        },
        "discovered_bodies": archives,
    }


def _discover_civicclerk(subdomain: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run CivicClerk-specific board discovery using the API."""
    from civicos_extraction.clients.civicclerk import CivicClerkClient

    client = CivicClerkClient(subdomain=subdomain, jurisdiction_id=jurisdiction_id)
    boards = client.get_boards()
    archives = {}
    for board in boards:
        name = board.get("BoardName", "")
        board_id = str(board.get("BoardId", ""))
        if name and board_id:
            key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            archives[key] = board_id

    return {
        "config": {
            "source_id": f"civicclerk-{subdomain}",
            "source_type": "civicclerk",
            "jurisdiction_id": jurisdiction_id,
            "base_url": f"https://{subdomain}.api.civicclerk.com/v1",
            "archives": archives,
            "metadata": {"subdomain": subdomain, "board_count": len(boards)},
        },
        "discovered_bodies": archives,
    }


def _generate_jurisdiction_yaml(
    jurisdiction_id: str,
    display_name: str,
    config: Dict[str, Any],
    contact_email: str = "",
    website: str = "",
    parent_jurisdictions: Optional[List[str]] = None,
    level: str = "city",
    county: str = "",
    zip_code: str = "",
    state_abbrev: str = "CA",
    country: str = "United States",
) -> str:
    """Generate jurisdiction YAML content from onboarding results.

    Level-aware: produces correct parent chains, financial fields, and contact
    info for cities, counties, states, provinces, councils, and districts
    across US, Canada, UK, and other countries — without caller cleanup.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML required for YAML generation: pip install pyyaml")

    from datetime import date

    source_type = config.get("source_type", "standard")
    base_url = config.get("base_url", "")
    metadata = config.get("metadata", {})
    archives = config.get("archives", {})

    # Build parent_jurisdictions with level- and country-awareness
    # - Filter self-references (e.g., county-alameda shouldn't be its own parent)
    # - Build sensible fallback chain based on level and country
    country_slug = country.strip().lower().replace(" ", "-") if country else "united-states"
    state_slug = _state_abbrev_to_slug(state_abbrev)

    # Country-aware state/province prefix
    if country == "Canada":
        region_prefix = "province"
    else:
        region_prefix = "state"

    if parent_jurisdictions:
        parents = [p for p in parent_jurisdictions if p != jurisdiction_id]
    elif level in ("state", "province"):
        parents = [f"country-{country_slug}"]
    elif level in ("county", "city", "town", "district", "council"):
        region_part = [f"{region_prefix}-{state_slug}"] if state_slug else []
        parents = region_part + [f"country-{country_slug}"]
    else:
        parents = [f"country-{country_slug}"]

    # County name for financial section — level-aware
    # For counties, this field is redundant (the jurisdiction IS the county), so omit it
    if level == "county":
        county_short = None
    else:
        county_short = re.sub(r"\s*County$", "", county).strip() if county else None

    # Zip code is meaningless for counties/states/provinces (they span many)
    if level in ("county", "state", "province"):
        zip_code = ""

    # Build meetings data source
    meetings_source: Dict[str, Any] = {
        "source_type": source_type,
        "base_url": base_url,
    }
    if archives:
        meetings_source["archives"] = archives
    if metadata:
        # Strip provenance/debug keys — YAML is for config, not extraction debug data
        clean_metadata = {
            k: v for k, v in metadata.items()
            if not k.endswith("_provenance")
        }
        if clean_metadata:
            meetings_source["metadata"] = clean_metadata

    today = date.today().isoformat()

    doc: Dict[str, Any] = {
        "jurisdiction_id": jurisdiction_id,
        "level": level,
        "display_name": display_name,
        "parent_jurisdictions": parents,
        "contact_info": {
            "clerk_email": contact_email or None,
            "website": website,
            "zip_code": zip_code,
        },
        "data_sources": {
            "meetings": meetings_source,
            "issues": None,
            "municipal_code": None,
        },
        "financial": {
            "state": state_abbrev,
            "county": county_short,
        },
        "ingestion": {
            "meetings": True,
            "pdf_chunks": True,
            "issues": False,
            "municipal_code": False,
            "agenda_items": True,
            "decisions": True,
            "legislation": True,
            "transcription": False,
            "diarization": False,
            "vector_indexing": True,
        },
        "metadata": {
            "created": today,
            "updated": today,
            "notes": "Auto-generated by onboard_jurisdiction().",
        },
    }

    header = f"# {display_name} Configuration\n#\n# Auto-generated by onboard_jurisdiction().\n\n"
    return header + yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)


def onboard_jurisdiction(
    url: str,
    jurisdiction_id: Optional[str] = None,
    output_dir: str = "data/extraction",
    city_name: Optional[str] = None,
    state: Optional[str] = None,
    level: str = "city",
    generate_yaml: bool = False,
    generate_registries: bool = False,
    validate: int = 1,
    run_pipeline: bool = False,
    index_vectors: bool = False,
    load_legislation: bool = False,
    load_municipal_code: bool = False,
    extract_chunks: bool = False,
    extract_agenda_items: bool = False,
    load_issues: bool = False,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> OnboardResult:
    """
    Onboard a new jurisdiction from a URL or city name.

    Flow:
    1. If city_name given (no URL), auto-discover Granicus subdomain
    2. Detect platform from URL
    3. Run platform-specific discovery
    4. Generate ExtractionConfig JSON
    5. Save to output_dir
    6. Optionally generate jurisdiction YAML and patch registries
    7. Optionally run extraction pipeline

    Args:
        url: City/county website or platform URL (can be empty if city_name given)
        jurisdiction_id: Optional jurisdiction ID. Inferred from URL/city_name if not provided.
        output_dir: Directory to save config JSON (default: data/extraction)
        city_name: City name for auto-discovery (e.g., "San Anselmo")
        state: Two-letter state/province code (required when city_name is provided)
        level: Jurisdiction level for ID prefix (default: "city")
        generate_yaml: If True, generate jurisdiction YAML file
        generate_registries: If True, run registry generation after YAML creation
        run_pipeline: If True, run extraction pipeline after config generation
        on_progress: Optional callback(step, message) for progress reporting

    Returns:
        OnboardResult with config, discovered bodies, and next steps
    """
    errors: List[str] = []
    pre_discovered: Optional[Dict[str, Any]] = None

    def _progress(step: str, message: str) -> None:
        if on_progress:
            on_progress(step, message)

    # Validate: state is required when city_name is provided
    if city_name and not state:
        return OnboardResult(
            success=False,
            errors=["state is required when city_name is provided (e.g., state='CA')"],
        )

    # Upfront API key checks — warn before doing network work
    _openai_key = os.environ.get("OPENAI_API_KEY")
    _google_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not _openai_key:
        _progress("warn", "No OPENAI_API_KEY — body names will be generic (view_N) and column maps skipped")
        logger.warning("No OPENAI_API_KEY set — LLM body naming and column mapping will use fallbacks")
    if generate_yaml and not _google_key:
        _progress("warn", "No GOOGLE_MAPS_API_KEY — YAML will have empty hierarchy (no geocoding)")
        logger.warning("No GOOGLE_MAPS_API_KEY set — jurisdiction YAML will lack geocoded hierarchy")

    # Step 0: If city_name given without URL, auto-discover platform
    if city_name and not url:
        from civicos_extraction.platform_detection import (
            discover_platform as _discover_platform_fn,
        )

        _progress("detect", f"Auto-discovering platform for '{city_name}, {state.upper()}'...")
        logger.info(f"Auto-discovering platform for '{city_name}, {state.upper()}'...")
        discovery = _discover_platform_fn(city_name, state=state)
        if discovery:
            platform = discovery["platform"]
            details = discovery["details"]
            logger.info(f"Platform discovered: {platform} ({discovery['confidence']:.0%})")
            pre_discovered = discovery

            # Build URL from discovery results
            if platform == "granicus":
                url = details["url"]
            elif platform == "legistar":
                client = details["client_name"]
                url = f"https://webapi.legistar.com/v1/{client}/bodies"
            elif platform == "civicclerk":
                subdomain = details["subdomain"]
                url = f"https://{subdomain}.api.civicclerk.com/v1/Boards"
            elif platform == "escribe":
                url = details.get("url", "")
            elif platform == "simbli":
                url = details.get("board_url", "")
            elif platform == "proudcity":
                url = details.get("url", "")
        else:
            return OnboardResult(
                success=False,
                errors=[
                    f"Could not auto-discover platform for '{city_name}, {state.upper()}'. "
                    "Try providing a direct URL instead."
                ],
            )

    _progress("discover", f"Platform detected, running discovery...")

    # Infer jurisdiction_id if not provided
    if not jurisdiction_id:
        if city_name:
            # Build from city_name: "San Anselmo" -> "city-san-anselmo"
            # Strip level-word suffixes to avoid "county-alameda-county"
            clean_name = re.sub(r"\s+(City|County|Town|District|State|Province|Council)$", "", city_name.strip(), flags=re.IGNORECASE)
            slug = re.sub(r"\s+", "-", clean_name.strip().lower())
            jurisdiction_id = f"{level}-{slug}"
        else:
            inferred = _infer_jurisdiction_id(url)
            # Prefix with level if the inferred ID doesn't already have one
            if inferred and not re.match(r"^(city|county|town|district|state|province|council)-", inferred):
                # Strip trailing level words from domain slugs: "traviscounty" -> "travis"
                clean = re.sub(r"(city|county|town|district|state|province|council)$", "", inferred, flags=re.IGNORECASE).rstrip("-")
                jurisdiction_id = f"{level}-{clean}" if clean else f"{level}-{inferred}"
            else:
                jurisdiction_id = inferred
            if not jurisdiction_id:
                return OnboardResult(
                    success=False,
                    errors=["Could not infer jurisdiction_id from URL. Please provide one."],
                )

    # Step 1 & 2: Platform detection + discovery
    # If Step 0 already discovered the platform, build config directly.
    # Otherwise, detect from URL and run platform-specific discovery.
    discovery_result: Optional[Dict[str, Any]] = None
    detection_dict: Dict[str, Any] = {}

    if pre_discovered:
        platform = pre_discovered["platform"]
        details = pre_discovered["details"]
        confidence = pre_discovered["confidence"]

        detection_dict = {
            "source_type": platform,
            "source_id": f"{platform}-{jurisdiction_id}",
            "platform_name": platform.capitalize(),
            "confidence": confidence,
            "metadata": details,
        }

        if platform == "granicus":
            try:
                discovery_result = _discover_granicus(url, jurisdiction_id)
            except Exception as e:
                errors.append(f"Granicus discovery failed: {e}")
        elif platform == "legistar":
            client_name = details["client_name"]
            try:
                discovery_result = _discover_legistar(client_name, jurisdiction_id)
            except Exception as e:
                errors.append(f"Legistar body discovery failed: {e}")
                discovery_result = {
                    "config": {
                        "source_id": f"legistar-{client_name}",
                        "source_type": "legistar",
                        "jurisdiction_id": jurisdiction_id,
                        "base_url": f"https://webapi.legistar.com/v1/{client_name}",
                        "archives": {},
                        "metadata": {"client_name": client_name, "body_count": details.get("body_count", 0)},
                    },
                    "discovered_bodies": {},
                }
        elif platform == "civicclerk":
            subdomain = details["subdomain"]
            try:
                discovery_result = _discover_civicclerk(subdomain, jurisdiction_id)
            except Exception as e:
                errors.append(f"CivicClerk board discovery failed: {e}")
                discovery_result = {
                    "config": {
                        "source_id": f"civicclerk-{subdomain}",
                        "source_type": "civicclerk",
                        "jurisdiction_id": jurisdiction_id,
                        "base_url": f"https://{subdomain}.api.civicclerk.com/v1",
                        "archives": {},
                        "metadata": {"subdomain": subdomain, "board_count": details.get("board_count", 0)},
                    },
                    "discovered_bodies": {},
                }
        elif platform == "escribe":
            try:
                discovery_result = _discover_escribe(url, jurisdiction_id)
            except Exception as e:
                errors.append(f"eScribe discovery failed: {e}")
        elif platform == "simbli":
            try:
                discovery_result = _discover_simbli(url, jurisdiction_id)
            except Exception as e:
                errors.append(f"Simbli discovery failed: {e}")
        elif platform == "proudcity":
            try:
                discovery_result = _discover_proudcity(url, jurisdiction_id)
            except Exception as e:
                errors.append(f"ProudCity discovery failed: {e}")

        if not discovery_result:
            return OnboardResult(
                success=False,
                jurisdiction_id=jurisdiction_id,
                detection=detection_dict,
                errors=errors or [f"Failed to build config for {platform}"],
            )
    else:
        # URL-based flow: detect platform, then run discovery
        detection = detect_platform(url, jurisdiction_id=jurisdiction_id)
        detection_dict = detection.to_dict()

        if not detection.source_type or detection.confidence < 0.5:
            return OnboardResult(
                success=False,
                jurisdiction_id=jurisdiction_id,
                detection=detection_dict,
                errors=[
                    f"No platform detected (confidence: {detection.confidence:.0%}). "
                    "Supported platforms: granicus, legistar, civicclerk, escribe, simbli, proudcity."
                ],
                next_steps=[
                    "Check that the URL is correct",
                    "If this is a new platform, implement a client in civicos-extraction",
                ],
            )

        try:
            if detection.source_type == "granicus":
                discovery_result = _discover_granicus(url, jurisdiction_id)
            elif detection.source_type == "escribe":
                discovery_result = _discover_escribe(url, jurisdiction_id)
            elif detection.source_type == "simbli":
                discovery_result = _discover_simbli(url, jurisdiction_id)
            elif detection.source_type == "proudcity":
                discovery_result = _discover_proudcity(url, jurisdiction_id)
            else:
                discovery_result = {
                    "config": {
                        "source_id": f"{detection.source_type}-{jurisdiction_id}",
                        "source_type": detection.source_type,
                        "jurisdiction_id": jurisdiction_id,
                        "base_url": url,
                        "archives": {},
                        "metadata": detection.metadata,
                    },
                    "discovered_bodies": {},
                }
        except Exception as e:
            errors.append(f"Discovery failed: {e}")
            return OnboardResult(
                success=False,
                jurisdiction_id=jurisdiction_id,
                detection=detection_dict,
                errors=errors,
            )

    config = discovery_result["config"]
    discovered_bodies = discovery_result.get("discovered_bodies", {})

    _progress("save", f"Saving config for {jurisdiction_id}...")

    # Step 3: Save config
    from civicos_extraction.config import get_config_dir

    config_dir = Path(output_dir) if output_dir != "data/extraction" else get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / f"{jurisdiction_id}.json"
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
    except Exception as e:
        errors.append(f"Failed to save config: {e}")
        return OnboardResult(
            success=False,
            jurisdiction_id=jurisdiction_id,
            detection=detection_dict,
            config=config,
            errors=errors,
        )

    # Step 3.5: Geocoding enrichment (if city_name available)
    geo_data: Optional[Dict[str, Any]] = None
    if city_name:
        _progress("geocode", f"Geocoding {city_name}...")
        geo_data = geocode_city(city_name, state=state)
        if geo_data:
            logger.info(
                f"Geocoded: {geo_data.get('city')} → "
                f"{geo_data.get('county', 'unknown county')}, "
                f"zip {geo_data.get('zip_code', '?')}"
            )

    # Step 4: Generate jurisdiction YAML (optional)
    yaml_path = None
    if generate_yaml:
        # Strip any level prefix (city-, county-, state-, etc.) from jurisdiction_id for display
        display_name = city_name or re.sub(r"^(city|county|town|district|state|province|council)-", "", jurisdiction_id).replace("-", " ").title()

        # Use geocoding data if available
        parent_jurisdictions = None
        county = ""
        zip_code = ""
        geo_country = "United States"
        state_abbrev = state.upper() if state else ""
        if geo_data:
            parent_jurisdictions = geo_data.get("parent_jurisdictions")
            county = geo_data.get("county", "")
            zip_code = geo_data.get("zip_code", "")
            state_abbrev = geo_data.get("state_abbrev", state_abbrev)
            geo_country = geo_data.get("country", geo_country)

        yaml_content = _generate_jurisdiction_yaml(
            jurisdiction_id=jurisdiction_id,
            display_name=display_name,
            config=config,
            website=config.get("base_url", ""),
            parent_jurisdictions=parent_jurisdictions,
            level=level,
            county=county,
            zip_code=zip_code,
            state_abbrev=state_abbrev,
            country=geo_country,
        )
        yaml_dir = Path(__file__).parents[4] / "data" / "jurisdictions"
        yaml_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = yaml_dir / f"{jurisdiction_id}.yaml"
        try:
            with open(yaml_path, "w") as f:
                f.write(yaml_content)
            logger.info(f"Jurisdiction YAML saved to {yaml_path}")
        except Exception as e:
            errors.append(f"Failed to save YAML: {e}")

    # Step 5: Patch registries (optional)
    if generate_registries and yaml_path and yaml_path.exists():
        try:
            import subprocess
            script = Path(__file__).parents[4] / "scripts" / "generate_registries.py"
            result = subprocess.run(
                [sys.executable, str(script), "--yaml", jurisdiction_id],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"Registries updated:\n{result.stdout}")
            else:
                errors.append(f"Registry generation failed: {result.stderr}")
        except Exception as e:
            errors.append(f"Registry generation error: {e}")

    # Step 6: Build next steps
    next_steps = [
        f"Review config at {config_path}",
    ]

    if yaml_path:
        next_steps.append(f"Review YAML at {yaml_path}")
    else:
        next_steps.append(f"Create jurisdiction YAML: data/jurisdictions/{jurisdiction_id}.yaml")

    if not generate_registries:
        next_steps.append("Run: python scripts/generate_registries.py")

    next_steps.extend([
        f"Run extraction: civic-extract discover --jurisdiction {jurisdiction_id}",
        f"Run pipeline: civic-extract onboard --url <url> -j {jurisdiction_id} --run-pipeline",
        f"Index vectors: civic-extract onboard --url <url> -j {jurisdiction_id} --run-pipeline --index-vectors",
    ])

    if not discovered_bodies:
        errors.append("No meeting bodies discovered. Config will have empty archives.")
        return OnboardResult(
            success=False,
            jurisdiction_id=jurisdiction_id,
            detection=detection_dict,
            config=config,
            config_path=str(config_path),
            discovered_bodies={},
            errors=errors,
            next_steps=[
                "Add archives manually to config before extraction",
                "Try a different URL or platform",
                f"Config saved at {config_path} (needs manual archives)",
            ],
        )

    # Step 7: Optional validation pipeline
    validation_report = None
    if validate > 0:
        _progress("validate", f"Running tier-{validate} validation...")
        try:
            from civicos_extraction.validate import validate_jurisdiction as _validate
            validation_report = _validate(jurisdiction_id, tier=validate, config=config)
            logger.info(f"Validation complete: highest tier passed = {validation_report.highest_tier_passed}")
        except Exception as e:
            errors.append(f"Validation failed: {e}")

    # Step 8: Optional pipeline run
    pipeline_result_obj = None
    if run_pipeline:
        _progress("pipeline", f"Running extraction pipeline for {jurisdiction_id}...")
        try:
            from civicos_extraction.clients.base import ExtractionConfig
            from civicos_extraction.clients.factory import create_source
            from civicos_extraction.pipeline import Pipeline

            extraction_config = ExtractionConfig.from_file(str(config_path))
            source = create_source(extraction_config)

            # Create storage backend
            from dotenv import load_dotenv as _load_dotenv
            _load_dotenv()
            database_url = os.environ.get("DATABASE_URL")
            if database_url:
                from civicos.storage.postgres_backend import PostgresBackend
                storage = PostgresBackend(database_url)
            else:
                from civicos.storage.sqlite_backend import SQLiteBackend
                storage = SQLiteBackend()

            pipeline = Pipeline(source=source, jurisdiction_id=jurisdiction_id, storage_target=storage)
            pipeline_result_obj = pipeline.run(days_ahead=90, days_past=30)
            logger.info(f"Pipeline complete: success={pipeline_result_obj.success}")

            # Update next steps to reflect pipeline ran
            next_steps = [
                f"Config saved at {config_path}",
                f"Pipeline ran: {'success' if pipeline_result_obj.success else 'failed'}",
                "Check data: civic-extract data-status --jurisdiction " + jurisdiction_id,
            ]
        except Exception as e:
            errors.append(f"Pipeline failed: {e}")

    # Step 9: Optional vector indexing
    vector_indexed = False
    if index_vectors:
        _progress("vectors", f"Indexing vectors for {jurisdiction_id}...")
        try:
            from civicos_extraction.cli.vectors import run_vector_indexing

            results = run_vector_indexing(
                jurisdiction_id=jurisdiction_id,
                corpus_type="all",
                provider_type="fastembed",
            )
            if results:
                total = sum(r.documents_indexed for r in results)
                vector_indexed = True
                logger.info(f"Vector indexing complete: {total} embeddings created")
                next_steps.append(f"Vectors indexed: {total} embeddings across all corpora")
            else:
                errors.append("Vector indexing returned no results")
        except Exception as e:
            errors.append(f"Vector indexing failed: {e}")

    # Step 10: Optional legislation loading
    if load_legislation:
        # Derive state code from function param or geocoding
        leg_state = state.upper() if state else ""
        if not leg_state:
            logger.warning("Cannot load legislation — no state provided")
        elif not os.environ.get("LEGISCAN_API_KEY"):
            logger.warning("Cannot load legislation — LEGISCAN_API_KEY not set")
            next_steps.append("Set LEGISCAN_API_KEY and run: civic-extract legislative --state " + leg_state.lower() + " --topic all --bulk --cloud")
        else:
            _progress("legislation", f"Loading {leg_state} legislation from LegiScan...")
            try:
                from civicos_extraction.cli.legislative import bulk_ingest_legislation
                result_code = bulk_ingest_legislation(state=leg_state.lower(), dry_run=False)
                if result_code == 0:
                    logger.info(f"Legislation loaded for {leg_state}")
                    next_steps.append(f"Legislation loaded for {leg_state}")
                else:
                    errors.append(f"Legislation loading returned exit code {result_code}")
            except Exception as e:
                errors.append(f"Legislation loading failed: {e}")

    # Step 11: Optional municipal code loading
    if load_municipal_code:
        _progress("municipal_code", f"Loading municipal code for {jurisdiction_id}...")
        try:
            from civicos._internal.legal.corpus.municipal import MunicipalCodeCorpus
            from civicos.storage import get_storage_backend

            corpus = MunicipalCodeCorpus.for_jurisdiction(jurisdiction_id)
            sections = list(corpus.stream_sections())
            if sections:
                backend = get_storage_backend()
                backend.store_municipal_code(jurisdiction_id, sections)
                logger.info(f"Municipal code loaded: {len(sections)} sections")
                next_steps.append(f"Municipal code loaded: {len(sections)} sections")
            else:
                errors.append("Municipal code: no sections found on Municode")
        except Exception as e:
            errors.append(f"Municipal code loading failed: {e}")

    # Step 12: Optional chunk extraction (PDF parsing, free)
    if extract_chunks and run_pipeline:
        _progress("chunks", f"Extracting PDF chunks for {jurisdiction_id}...")
        try:
            from civicos_extraction.cli.chunks import run_chunk_extraction

            chunk_results = run_chunk_extraction(
                jurisdiction_id=jurisdiction_id,
                cloud=bool(os.environ.get("DATABASE_URL")),
            )
            if chunk_results:
                total_chunks = sum(r.chunks_count for r in chunk_results if r.status == "success")
                logger.info(f"Chunk extraction complete: {total_chunks} chunks from {len(chunk_results)} meetings")
                next_steps.append(f"Chunks extracted: {total_chunks} chunks")
            else:
                logger.info("No meetings with agendas found for chunk extraction")
        except Exception as e:
            errors.append(f"Chunk extraction failed: {e}")

    # Step 13: Optional agenda item extraction (LLM-powered)
    if extract_agenda_items and run_pipeline:
        _progress("agenda_items", f"Extracting agenda items for {jurisdiction_id}...")
        try:
            from civicos_extraction.cli.agenda import run_agenda_extraction

            agenda_results = run_agenda_extraction(
                jurisdiction_id=jurisdiction_id,
                cloud=bool(os.environ.get("DATABASE_URL")),
            )
            if agenda_results:
                total_items = sum(r.items_count for r in agenda_results if r.status == "success")
                logger.info(f"Agenda extraction complete: {total_items} items from {len(agenda_results)} meetings")
                next_steps.append(f"Agenda items extracted: {total_items} items")
            else:
                logger.info("No meetings found for agenda item extraction")
        except Exception as e:
            errors.append(f"Agenda item extraction failed: {e}")

    # Step 14: Optional 311 issues loading (best-effort)
    if load_issues:
        _progress("issues", f"Loading 311 issues for {jurisdiction_id} (best-effort)...")
        try:
            from civicos_extraction.cli.issues import derive_place_url, fetch_and_store_issues

            place_url = derive_place_url(jurisdiction_id)
            cloud = bool(os.environ.get("DATABASE_URL"))

            result_code = fetch_and_store_issues(
                jurisdiction_id=jurisdiction_id,
                provider="seeclickfix",
                place_url=place_url,
                status=None,
                max_pages=50,
                per_page=100,
                cloud=cloud,
                output_dir="data/pilot",
            )
            if result_code == 0:
                logger.info(f"311 issues loaded for {jurisdiction_id}")
                next_steps.append("311 issues loaded (SeeClickFix)")
            else:
                logger.warning(f"No 311 issues found for {jurisdiction_id} — this is normal if the city doesn't use SeeClickFix")
        except Exception as e:
            # Best-effort: log warning, don't fail onboarding
            logger.warning(f"311 issues loading skipped: {e} — this is normal if the city doesn't use SeeClickFix")

    # If pipeline ran but vectors weren't indexed, remind user
    if run_pipeline and not index_vectors and not vector_indexed:
        next_steps.append(
            f"Index vectors: civic-extract onboard --url <url> -j {jurisdiction_id} --index-vectors"
        )
        next_steps.append(
            "Without vectors, what_happened() and semantic search won't work"
        )

    # Post-onboard data status report
    if run_pipeline:
        _progress("status", "Generating data status report...")
        try:
            from dotenv import load_dotenv as _ld
            _ld()
            from civicos import CivicOS
            from civicos.diagnostics import DataStatus, format_data_status

            c = CivicOS(jurisdiction_id)
            status = DataStatus(c.storage, c._vectors, jurisdiction_id)
            report = status.summary()

            # Print summary
            logger.info("")
            logger.info("=" * 62)
            logger.info(f"  DATA STATUS: {jurisdiction_id}")
            logger.info("=" * 62)
            for corpus_type, count in sorted(report.corpus_counts.items()):
                if count.storage_count > 0:
                    logger.info(f"  {count.display_name:<20} {count.storage_count:>8} docs")
            logger.info(f"  {'─' * 30}")
            logger.info(f"  {'Total':.<20} {report.total_storage_docs:>8} docs")
            if report.total_vector_docs > 0:
                logger.info(f"  {'Vectors':.<20} {report.total_vector_docs:>8} embeddings")
            logger.info("")

            # Surface what's missing with guidance
            missing = []
            if report.corpus_counts.get("decisions", None) and report.corpus_counts["decisions"].storage_count == 0:
                missing.append("decisions (run weekly LLM extraction after meetings accumulate)")
            if report.corpus_counts.get("transcripts", None) and report.corpus_counts["transcripts"].storage_count == 0:
                missing.append("transcripts (opt-in, ~$0.23/hr via /ingest-audio)")
            if missing:
                logger.info("  Expected missing data:")
                for m in missing:
                    logger.info(f"    - {m}")
                logger.info("")
            logger.info("=" * 62)
        except Exception as e:
            logger.warning(f"Data status report skipped: {e}")

    # Deployment next-steps guidance
    if run_pipeline:
        next_steps.append(f"To enable scheduled refresh: modal deploy scripts/modal_ingest.py")
        next_steps.append(f"To update extension registry: cd apps/civicos-registry && npx wrangler deploy")

    return OnboardResult(
        success=True,
        jurisdiction_id=jurisdiction_id,
        detection=detection_dict,
        config=config,
        config_path=str(config_path),
        discovered_bodies=discovered_bodies,
        next_steps=next_steps,
        validation=validation_report,
        pipeline_result=pipeline_result_obj,
    )
