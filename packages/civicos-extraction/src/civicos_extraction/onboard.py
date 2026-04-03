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

from civicos_config import JURISDICTIONS_DIR
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
    usaspending_candidates: List[Dict[str, Any]] = field(default_factory=list)
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


def _discover_boarddocs(url: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run BoardDocs-specific discovery.

    Extracts app_path from the URL and auto-discovers committee IDs
    from the BoardDocs main page. Works for any BoardDocs instance
    regardless of state or district.

    Args:
        url: BoardDocs URL (e.g., "https://go.boarddocs.com/ca/rova/Board.nsf/Public")
        jurisdiction_id: Target jurisdiction ID

    Returns:
        Dict with 'config' and 'discovered_bodies' keys.
    """
    # Extract app_path from URL
    match = re.match(r"https?://go\.boarddocs\.com/([^/]+/[^/]+)", url)
    if not match:
        raise ValueError(f"Could not extract app_path from BoardDocs URL: {url}")

    app_path = match.group(1)

    # Auto-discover committee IDs from the main page
    from civicos_extraction.clients.boarddocs import BoardDocsClient

    client = BoardDocsClient(
        app_path=app_path,
        jurisdiction_id=jurisdiction_id,
        request_delay=0.5,
    )
    committees = client.discover_committee_ids()

    # Use first committee as default (usually the main governing board)
    committee_id = ""
    if committees:
        first_name = next(iter(committees))
        committee_id = committees[first_name]
        logger.info(f"BoardDocs: auto-selected committee '{first_name}' ({committee_id})")

    config = {
        "source_id": f"boarddocs-{app_path.replace('/', '-')}",
        "source_type": "boarddocs",
        "jurisdiction_id": jurisdiction_id,
        "base_url": f"https://go.boarddocs.com/{app_path}/Board.nsf",
        "archives": {},
        "metadata": {
            "app_path": app_path,
            "committee_id": committee_id,
            "committees": committees,
        },
    }

    return {
        "config": config,
        "discovered_bodies": committees,
    }


def _discover_proudcity(url: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run ProudCity-specific discovery."""
    from civicos_extraction.clients.proudcity import ProudCityClient

    client = ProudCityClient(
        base_url=url,
        jurisdiction_id=jurisdiction_id,
    )

    discovered = client.discover_meeting_types()

    # Use the resolved base URL if the site redirected (e.g., townoffairfax.org -> townoffairfaxca.gov)
    resolved_base = getattr(client, "_wp_api_base", url)

    config = {
        "source_id": f"proudcity-{jurisdiction_id}",
        "source_type": "proudcity",
        "jurisdiction_id": jurisdiction_id,
        "base_url": resolved_base,
        "auto_discover": True,
        "archives": discovered,
    }

    return {
        "config": config,
        "discovered_bodies": discovered,
    }


def _discover_civicplus(
    url: str, jurisdiction_id: str, details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Run CivicPlus-specific discovery.

    Probes Archive.aspx pages to find which AMIDs contain meeting agendas
    vs. minutes, and builds an extraction config.
    """
    import requests as _req

    base_url = url.rstrip("/")
    details = details or {}
    discovered_amids = details.get("discovered_amids", [])

    # If no AMIDs from detection, probe common ones (1-80)
    if not discovered_amids:
        session = _req.Session()
        session.headers["User-Agent"] = "CivicOS-Extraction/1.0"
        for amid in range(1, 81):
            try:
                resp = session.get(
                    f"{base_url}/Archive.aspx?AMID={amid}",
                    timeout=8,
                    allow_redirects=True,
                )
                if resp.status_code == 200 and "ADID=" in resp.text:
                    discovered_amids.append(str(amid))
            except Exception:
                continue

    # For each AMID, fetch the page and determine body name + document type
    archives: Dict[str, str] = {}
    minutes_archives: Dict[str, str] = {}
    session = _req.Session()
    session.headers["User-Agent"] = "CivicOS-Extraction/1.0"

    for amid in discovered_amids:
        try:
            resp = session.get(
                f"{base_url}/Archive.aspx?AMID={amid}",
                timeout=10,
                allow_redirects=True,
            )
            if resp.status_code != 200 or "ADID=" not in resp.text:
                continue

            html = resp.text
            # Extract archive title from the bold span
            title_match = re.search(
                r'<span[^>]*style="font-weight:\s*bold[^"]*"[^>]*class="archive"[^>]*>\s*\n?\s*(.+?)\s*\n?\s*</span>',
                html,
                re.IGNORECASE,
            )
            if not title_match:
                # Try alternative: bold text in the archive header area
                title_match = re.search(
                    r'class="archive">\s*\n\s*([A-Z][^<\n]{3,60})\s*\n',
                    html,
                )

            title = title_match.group(1).strip() if title_match else f"Archive {amid}"

            # Count entries to gauge quality
            entry_count = len(re.findall(r"ADID=\d+", html))

            # Classify: is this a meeting-body archive or non-meeting content?
            title_lower = title.lower()

            # Skip non-meeting archives
            _SKIP_KEYWORDS = {
                "newsletter", "permit", "certificate", "budget",
                "financial", "audit", "resolution", "ordinance",
                "proclamation", "weather", "sales_tax", "revenue",
                "expenditure", "update", "calendar_item",
                "housing_element", "elevation",
            }
            if any(kw in title_lower.replace(" ", "_") for kw in _SKIP_KEYWORDS):
                logger.debug(f"Skipping non-meeting archive AMID={amid}: '{title}'")
                continue

            slug = re.sub(r"[^a-z0-9]+", "_", title_lower).strip("_")
            # Remove suffix words to get body slug
            body_slug = re.sub(
                r"_(agendas?|agenda_packets?|minutes|correspondence|notices|packets?"
                r"|post_agenda_publication_documentation.*|received_after_agenda_publication)$",
                "", slug,
            )

            if "minute" in title_lower:
                minutes_archives[body_slug] = amid
            elif "correspondence" in title_lower or "late_correspondence" in title_lower:
                # Skip correspondence archives — not meetings
                logger.debug(f"Skipping correspondence archive AMID={amid}: '{title}'")
                continue
            elif "agenda" in title_lower or "packet" in title_lower:
                archives[body_slug] = amid
            elif any(
                body_word in title_lower
                for body_word in [
                    "council", "commission", "committee", "board",
                    "fire", "public", "meeting",
                ]
            ):
                # Meeting body without "agenda" in name — include it
                archives[body_slug] = amid
            else:
                logger.debug(f"Skipping unclassified archive AMID={amid}: '{title}'")
                continue

            logger.info(f"CivicPlus AMID={amid}: '{title}' ({entry_count} entries) -> {body_slug}")
            time.sleep(0.3)

        except Exception as e:
            logger.debug(f"CivicPlus AMID={amid} probe failed: {e}")

    config = {
        "source_id": f"civicplus-{jurisdiction_id}",
        "source_type": "civicplus",
        "jurisdiction_id": jurisdiction_id,
        "base_url": base_url,
        "archives": archives,
        "metadata": {
            "minutes_archives": minutes_archives,
            "discovered_amids": discovered_amids,
        },
    }

    return {
        "config": config,
        "discovered_bodies": archives,
    }


def _discover_universal(url: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run universal adapter discovery via Playwright+LLM.

    Renders the page with Playwright (headless + stealth), sends the visible
    text to an LLM, and gets structured meeting data back. This is more robust
    than the CSS selector approach because:
    - Handles JS-rendered content, tabs, dynamic tables
    - No brittle CSS selectors
    - LLM can distinguish government meetings from community events
    - Works on any page structure

    Trade-off: ~$0.001 per extraction (Gemini Flash).
    """
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        raise RuntimeError(
            "Universal adapter requires an LLM API key (OPENAI_API_KEY or GOOGLE_API_KEY). "
            "Set one in .env and retry."
        )

    try:
        from civicos_extraction.clients.playwright_llm import extract_meetings_from_page

        meetings = extract_meetings_from_page(url, jurisdiction_id)
        if not meetings:
            raise RuntimeError(f"Playwright+LLM extraction returned 0 meetings from {url}")

        config = {
            "source_id": f"playwright-llm-{jurisdiction_id}",
            "source_type": "playwright_llm",
            "jurisdiction_id": jurisdiction_id,
            "base_url": url,
            "archives": {},
            "metadata": {
                "extraction_mode": "playwright_llm",
                "meeting_page_url": url,
                "initial_meeting_count": len(meetings),
            },
        }

        return {
            "config": config,
            "discovered_bodies": {},
            "prefetched_meetings": meetings,
        }

    except ImportError:
        raise RuntimeError(
            "Playwright+LLM extraction requires browser automation. "
            "Install: pip install playwright playwright-stealth && playwright install chromium"
        )


def detect_issue_source(city_name: str, jurisdiction_id: str) -> Optional[str]:
    """Probe known 311/issue APIs to detect which provider a city uses.

    Tries each supported provider in order. Returns the provider key
    (e.g. "seeclickfix") or None if no provider is detected.

    This is safe to call during onboarding — it makes at most one lightweight
    API request per provider and does not store anything.
    """
    # --- SeeClickFix probe ---
    try:
        from civicos_extraction.clients.seeclickfix import SeeClickFixClient

        client = SeeClickFixClient()
        place_url = client.get_place_url_for_city(city_name)

        result = client.get_issues(place_url=place_url, per_page=1, status=None)
        issues = result.get("issues", [])
        metadata = result.get("metadata", {})

        # The SeeClickFix API returns a valid empty response for unknown
        # place_urls (entries=0, no error). We must check that there are
        # actual issues to confirm the city is on SeeClickFix.
        if issues:
            logger.info(f"SeeClickFix detected for '{city_name}' (place_url={place_url})")
            return "seeclickfix"
        else:
            logger.debug(f"SeeClickFix returned 0 issues for '{city_name}' (place_url={place_url})")
    except Exception as e:
        logger.debug(f"SeeClickFix probe failed for '{city_name}': {e}")

    # --- GOGov / FixItMarin probe ---
    # GOGov (gogovapps.com) powers FixItMarin for unincorporated Marin County.
    # No public API exists, so we can only detect it — not fetch issues.
    # Instance registry: data/extraction/gogov_instances.json
    try:
        from civicos_extraction.config import get_config_dir
        _gogov_path = Path(get_config_dir()) / "gogov_instances.json"
        if not _gogov_path.exists():
            _gogov_path = Path("data/extraction/gogov_instances.json")
        _gogov_counties = json.loads(_gogov_path.read_text()) if _gogov_path.exists() else {}
    except Exception:
        _gogov_counties = {}
    county_slug = jurisdiction_id.split("-")[-1] if jurisdiction_id.startswith("county-") else None
    if county_slug and county_slug in _gogov_counties:
        logger.info(
            f"GOGov (FixItMarin) detected for '{city_name}' — "
            "no public API available for issue fetching"
        )
        return "gogov"

    logger.info(f"No issue provider detected for '{city_name}'")
    return None


def _infer_division_name(jurisdiction_id: str) -> str:
    """Infer Civera ElectionStats division filter from a jurisdiction ID.

    Returns a substring that matches all relevant divisions in the county
    registrar's data. Uses the bare city/town name (not "City of X") so
    that division names like "San Rafael City Council District 1" are
    captured alongside "City of San Rafael".

    Mapping:
    - city-san-rafael → "San Rafael"   (matches City of San Rafael + council districts)
    - town-san-anselmo → "San Anselmo" (matches Town of San Anselmo + any sub-divisions)
    - county-marin → "Marin County"    (county-level needs the full name for specificity)
    - school-novato → "Novato Unified School District" (looked up from school_districts.json)

    Falls back to title-cased slug for unknown prefixes.
    """
    parts = jurisdiction_id.split("-", 1)
    if len(parts) < 2:
        return jurisdiction_id.replace("-", " ").title()

    level, slug = parts[0], parts[1]
    name = slug.replace("-", " ").title()

    if level in ("city", "town"):
        # Use bare city/town name for broadest matching.
        # "San Rafael" matches both "City of San Rafael" and
        # "San Rafael City Council District 1".
        return name
    elif level == "county":
        return f"{name} County"
    elif level == "school":
        # Try to find the full district name from the lookup table
        try:
            districts = load_school_districts()
            for state_data in districts.values():
                for county_entries in state_data.values():
                    for entry in county_entries:
                        if entry.get("jurisdiction_id") == jurisdiction_id:
                            return entry["name"]
        except Exception:
            pass
        # Fallback: use slug as-is with "School District" suffix
        return f"{name} School District"
    else:
        return name


def detect_districts(
    lat: float, lng: float, state: str = ""
) -> Optional[Dict[str, List[int]]]:
    """Detect legislative districts for a location using the Census Bureau Geocoding API.

    Uses the free, no-auth Census geocoder to resolve coordinates into
    congressional district, state senate district, and state assembly district.

    Args:
        lat: Latitude
        lng: Longitude
        state: Two-letter state abbreviation (used for validation, not required)

    Returns:
        Dict matching the ca_sos_results districts format:
        {"us-rep": [2], "state-senate": [2], "state-assembly": [12]}
        None if the API call fails or no districts found.
    """
    try:
        response = requests.get(
            "https://geocoding.geo.census.gov/geocoder/geographies/coordinates",
            params={
                "x": lng,
                "y": lat,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning(f"Census geocoder failed for ({lat}, {lng}): {e}")
        return None

    geographies = data.get("result", {}).get("geographies", {})

    districts: Dict[str, List[int]] = {}

    # Congressional district (e.g. "119th Congressional Districts")
    for key, items in geographies.items():
        if "congressional" in key.lower() and items:
            # GEOID format: state_fips + district_num (e.g. "0602" = CA district 2)
            geoid = items[0].get("GEOID", "")
            if len(geoid) >= 4:
                district_num = int(geoid[2:])
                if district_num > 0:
                    districts["us-rep"] = [district_num]
            break

    # State senate (upper chamber)
    for key, items in geographies.items():
        if "upper" in key.lower() and items:
            sldu = items[0].get("SLDU", "")
            if sldu:
                district_num = int(sldu)
                if district_num > 0:
                    districts["state-senate"] = [district_num]
            break

    # State assembly (lower chamber)
    for key, items in geographies.items():
        if "lower" in key.lower() and items:
            sldl = items[0].get("SLDL", "")
            if sldl:
                district_num = int(sldl)
                if district_num > 0:
                    districts["state-assembly"] = [district_num]
            break

    if not districts:
        logger.info(f"No legislative districts found for ({lat}, {lng})")
        return None

    logger.info(f"Detected districts for ({lat}, {lng}): {districts}")
    return districts


def detect_election_sources(
    jurisdiction_id: str, state: str, county: str,
    lat: Optional[float] = None, lng: Optional[float] = None,
) -> dict:
    """Detect available election data sources for a jurisdiction.

    Called during onboarding after geocoding provides the county name.
    Dispatches to a state-specific provider (see civicos_extraction.providers).

    Args:
        jurisdiction_id: e.g. "city-san-rafael", "county-marin"
        state: Two-letter state abbreviation (e.g. "CA")
        county: County name from geocoding (e.g. "Marin")
        lat: Latitude from geocoding (enables district detection)
        lng: Longitude from geocoding (enables district detection)

    Returns:
        Dict of election source configs. Example:
        {"ca_sos_results": {"county": "marin", "districts": {"us-rep": [2]}}}
    """
    from civicos_extraction.providers import get_provider

    provider = get_provider(state)
    if provider is None:
        return {}

    # Normalize county name: Google Maps returns "Marin County", we need "marin"
    county_normalized = re.sub(
        r"\s*County$", "", county, flags=re.IGNORECASE,
    ).strip().lower() if county else ""

    return provider.detect_election_sources(
        jurisdiction_id, county_normalized, lat, lng,
    )


def _validate_civera_division_filter(
    graphql_url: str,
    county_slug: str,
    division_filter: str,
) -> bool:
    """Check that a division filter returns at least one contest from Civera.

    Queries the most recent general election to verify the filter matches
    real division names. Returns True if contests found, False otherwise.
    """
    from civicos_extraction.clients.civera_election_stats import CiveraElectionStatsClient

    try:
        client = CiveraElectionStatsClient(
            jurisdiction_id="validation",
            graphql_url=graphql_url,
            county_slug=county_slug,
            request_delay=0,
        )
        # Find the most recent general election
        events = client.list_elections(from_year=2022, to_year=2026)
        generals = [e for e in events if "general" in e.get("name", "").lower()]
        if not generals:
            return True  # Can't validate, assume OK

        results = client.get_election_results(
            generals[0]["id"], division_filter=division_filter,
        )
        contest_count = results.get("total_contests", 0)
        if contest_count > 0:
            logger.info(
                f"Civera validation: '{division_filter}' → {contest_count} contests "
                f"in {generals[0].get('name', '?')}"
            )
        return contest_count > 0

    except Exception as e:
        logger.debug(f"Civera validation failed: {e}")
        return True  # Network error — don't block onboarding


CDE_SCHOOLS_URL = "https://www.cde.ca.gov/schooldirectory/report?rid=dl1&tp=txt"


def detect_school_districts(
    city_name: str,
    county_name: str,
) -> List[str]:
    """Detect school districts serving a city from CA Dept of Education data.

    Downloads the CDE public schools directory (tab-delimited, ~4MB) and
    finds all districts that have at least one active school in the target
    city. This is authoritative — it uses the school's physical address
    city, not boundary approximations.

    Args:
        city_name: City name as it appears in CDE data (e.g., "San Rafael")
        county_name: County name (e.g., "Marin")

    Returns:
        Sorted list of unique district names with schools in the city.
        Empty list if download fails or no matches found.
    """
    try:
        resp = requests.get(CDE_SCHOOLS_URL, timeout=30)
        resp.raise_for_status()

        # Tab-delimited, first row is headers
        lines = resp.text.splitlines()
        if not lines:
            return []

        headers = lines[0].split("\t")
        city_idx = _find_column(headers, "City")
        county_idx = _find_column(headers, "County")
        district_idx = _find_column(headers, "District")
        status_idx = _find_column(headers, "StatusType")

        if any(i is None for i in [city_idx, county_idx, district_idx, status_idx]):
            logger.warning("CDE file missing expected columns")
            return []

        city_lower = city_name.lower()
        county_lower = county_name.lower()
        districts = set()

        for line in lines[1:]:
            fields = line.split("\t")
            if len(fields) <= max(city_idx, county_idx, district_idx, status_idx):
                continue

            if (fields[status_idx].strip().lower() == "active"
                    and fields[county_idx].strip().lower() == county_lower
                    and fields[city_idx].strip().lower() == city_lower):
                district = fields[district_idx].strip()
                if district:
                    districts.add(district)

        result = sorted(districts)
        if result:
            logger.info(f"CDE: {len(result)} school districts in {city_name}, {county_name}: {result}")
        else:
            logger.info(f"CDE: no school districts found for {city_name}, {county_name}")
        return result

    except Exception as e:
        logger.debug(f"CDE school district detection failed: {e}")
        return []


def _find_column(headers: List[str], name: str) -> Optional[int]:
    """Find column index by name (case-insensitive)."""
    name_lower = name.lower()
    for i, h in enumerate(headers):
        if h.strip().lower() == name_lower:
            return i
    return None


def detect_contact_info(
    base_url: str,
    city_name: str,
) -> Dict[str, Optional[str]]:
    """Extract contact info from a city's website.

    Fetches the city website and common contact page paths, then uses
    an LLM to extract structured contact fields from the page content.
    The LLM processes *fetched HTML*, not its training data.

    Args:
        base_url: City website URL (e.g., "https://www.cityofsanrafael.org")
        city_name: City name for context (e.g., "San Rafael")

    Returns:
        Dict with keys: clerk_email, city_hall_address, phone,
        public_comment_deadline, in_person_time_limit.
        Values are None if not found.

    Cost: ~$0.002 per call (OpenAI gpt-4o-mini, ~500 input tokens).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.debug("No OPENAI_API_KEY — skipping contact info detection")
        return _empty_contact_info()

    # Try common contact page paths
    contact_paths = [
        "/contact", "/contact-us", "/city-clerk",
        "/government/city-clerk", "/departments/city-clerk",
        "/city-hall", "/about/contact",
    ]

    # Try contact-specific paths first (more focused), then discover from homepage
    import re as _re_urls
    ua = {"User-Agent": "CivicOS-Onboarding/1.0 (civic data platform)"}

    page_content = None
    best_score = 0

    # Phase 1: try known paths
    for path in contact_paths:
        url = base_url.rstrip("/") + path
        try:
            resp = requests.get(url, timeout=10, headers=ua)
            if len(resp.text) < 500:
                continue
            text_lower = resp.text.lower()
            # Score pages by how much contact-relevant content they have
            score = sum(1 for kw in ["clerk", "@", "phone", "email", "address"]
                        if kw in text_lower)
            if score > best_score:
                best_score = score
                page_content = resp.text
        except Exception:
            continue

    # Phase 2: discover clerk/contact links from homepage
    if best_score < 3:
        try:
            resp = requests.get(base_url, timeout=10, headers=ua)
            if resp.status_code == 200:
                # Find links to clerk or contact pages
                links = _re_urls.findall(
                    r'href=["\']([^"\']*(?:clerk|contact|directory|staff)[^"\']*)["\']',
                    resp.text, flags=_re_urls.IGNORECASE,
                )
                for link in links[:5]:
                    full_url = link if link.startswith("http") else base_url.rstrip("/") + "/" + link.lstrip("/")
                    try:
                        resp2 = requests.get(full_url, timeout=10, headers=ua)
                        text_lower = resp2.text.lower()
                        score = sum(1 for kw in ["clerk", "@", "phone", "email", "address"]
                                    if kw in text_lower)
                        if score > best_score:
                            best_score = score
                            page_content = resp2.text
                            logger.info(f"Found contact page via link discovery: {full_url}")
                    except Exception:
                        continue

                # Fallback: use homepage itself
                if not page_content:
                    page_content = resp.text
        except Exception:
            pass

    if not page_content:
        logger.info(f"No contact page found on {base_url}")
        return _empty_contact_info()

    import re as _re

    # Extract emails and phones from raw HTML (before stripping tags)
    # mailto: links are common and get lost when we strip tags
    raw_emails = _re.findall(r"mailto:([\w.+-]+@[\w.-]+\.\w+)", page_content, _re.IGNORECASE)
    raw_emails += _re.findall(r"[\w.+-]+@[\w.-]+\.(?:org|gov|com|net|us)", page_content)
    raw_emails = sorted(set(raw_emails))

    raw_phones = _re.findall(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", page_content)
    raw_phones = sorted(set(raw_phones))

    # Strip HTML for LLM text
    text = _re.sub(r"<script[^>]*>.*?</script>", "", page_content, flags=_re.DOTALL)
    text = _re.sub(r"<style[^>]*>.*?</style>", "", text, flags=_re.DOTALL)
    text = _re.sub(r"<[^>]+>", " ", text)
    text = _re.sub(r"\s+", " ", text).strip()[:6000]

    # Build pre-extracted data section so LLM has structured signals
    pre_extracted = ""
    if raw_emails:
        pre_extracted += f"Emails found on page: {', '.join(raw_emails[:10])}\n"
    if raw_phones:
        pre_extracted += f"Phones found on page: {', '.join(raw_phones[:10])}\n"

    prompt = (
        f"Extract contact information for {city_name} city government from "
        f"this web page. Return ONLY a JSON object with these keys "
        f"(use null if not found):\n"
        f'{{"clerk_email": "...", "city_hall_address": "...", '
        f'"phone": "...", "public_comment_deadline": "...", '
        f'"in_person_time_limit": "..."}}\n\n'
        f"For clerk_email, prefer the city clerk's email specifically. "
        f"For phone, prefer the main city hall phone number.\n\n"
        f"{pre_extracted}\n"
        f"Page text:\n{text}"
    )

    try:
        import httpx
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 200,
                "response_format": {"type": "json_object"},
            },
            timeout=15,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        result = {
            "clerk_email": parsed.get("clerk_email"),
            "city_hall_address": parsed.get("city_hall_address"),
            "phone": parsed.get("phone"),
            "public_comment_deadline": parsed.get("public_comment_deadline"),
            "in_person_time_limit": parsed.get("in_person_time_limit"),
        }
        logger.info(f"Contact info extracted for {city_name}: {result}")
        return result

    except Exception as e:
        logger.debug(f"Contact info LLM extraction failed: {e}")
        return _empty_contact_info()


def _empty_contact_info() -> Dict[str, Optional[str]]:
    return {
        "clerk_email": None,
        "city_hall_address": None,
        "phone": None,
        "public_comment_deadline": None,
        "in_person_time_limit": None,
    }


def detect_youtube_channel(city_name: str, state: str = "") -> Optional[dict]:
    """Search YouTube for a city's official meeting channel.

    Uses YouTube Data API v3 search.list (costs 100 quota units per call,
    free tier is 10,000/day). Returns dict with channel_id and channel_title,
    or None if no channel found.

    Requires YOUTUBE_API_KEY or GOOGLE_API_KEY in environment.
    Safe to call during onboarding — one API request, no storage.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.debug("No YouTube API key — skipping channel detection")
        return None

    # Build search query: "Mill Valley city council" or "Mill Valley CA city council"
    query = f"{city_name} city council"
    if state:
        query = f"{city_name} {state} city council"

    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "key": api_key,
                "q": query,
                "type": "channel",
                "part": "snippet",
                "maxResults": 5,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            logger.info(f"No YouTube channels found for '{query}'")
            return None

        # Heuristic: pick the best channel matching city + state
        city_lower = city_name.lower()
        state_upper = state.upper().strip() if state else ""
        state_full = _US_STATES.get(state_upper, "").lower()

        # Score each candidate: prefer title containing both city and state
        candidates = []
        for item in items:
            title = item["snippet"]["title"].lower()
            desc = item["snippet"].get("description", "").lower()
            text = f"{title} {desc}"
            if city_lower not in title:
                continue
            score = 1  # city name match
            if state_full and state_full in text:
                score += 10  # full state name match (e.g., "Texas")
            if state_upper.lower() in text.split():
                score += 5  # state abbreviation match (e.g., "TX")
            candidates.append((score, item))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best = candidates[0][1]
            result = {
                "channel_id": best["snippet"]["channelId"],
                "channel_title": best["snippet"]["title"],
            }
            logger.info(f"YouTube channel detected: {result['channel_title']} "
                        f"({result['channel_id']})")
            return result

        # No channel title matched the city name — don't guess
        logger.info(f"No YouTube channel matched '{city_name}' (candidates: "
                     f"{[i['snippet']['title'] for i in items[:3]]})")
        return None

    except Exception as e:
        logger.debug(f"YouTube channel detection failed for '{city_name}': {e}")
        return None


def detect_youtube_playlist(channel_id: str) -> Optional[str]:
    """Find the council meeting playlist on a YouTube channel.

    Lists all playlists for a channel via YouTube Data API v3 and picks
    the one most likely to contain council/board meeting recordings.
    Uses keyword scoring on playlist titles — no LLM needed.

    Args:
        channel_id: YouTube channel ID (from detect_youtube_channel)

    Returns:
        Playlist ID string, or None if no match found.

    Cost: 1 API quota unit (playlists.list). Free tier is 10,000/day.
    Requires YOUTUBE_API_KEY or GOOGLE_API_KEY in environment.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.debug("No YouTube API key — skipping playlist detection")
        return None

    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/playlists",
            params={
                "key": api_key,
                "channelId": channel_id,
                "part": "snippet",
                "maxResults": 50,
            },
            timeout=10,
        )
        resp.raise_for_status()
        playlists = resp.json().get("items", [])

        if not playlists:
            logger.info(f"No playlists found for channel {channel_id}")
            return None

        # Score playlists by keyword relevance
        # Higher score = more likely to be the meeting playlist
        meeting_keywords = {
            "council meeting": 20,
            "city council": 15,
            "town council": 15,
            "board meeting": 10,
            "council session": 10,
            "regular meeting": 8,
            "meeting": 3,
            "council": 5,
            "session": 2,
        }

        best_score = 0
        best_playlist = None

        for pl in playlists:
            title = pl["snippet"]["title"].lower()
            score = 0
            for keyword, weight in meeting_keywords.items():
                if keyword in title:
                    score += weight

            if score > best_score:
                best_score = score
                best_playlist = pl

        if best_playlist and best_score >= 5:
            playlist_id = best_playlist["id"]
            playlist_title = best_playlist["snippet"]["title"]
            logger.info(
                f"YouTube playlist detected: '{playlist_title}' "
                f"({playlist_id}, score={best_score})"
            )
            return playlist_id

        logger.info(f"No meeting playlist found among {len(playlists)} playlists")
        return None

    except Exception as e:
        logger.debug(f"YouTube playlist detection failed: {e}")
        return None


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

        # Extract lat/lng for downstream use (district detection, etc.)
        geometry = result.get("geometry", {})
        location = geometry.get("location", {})

        return {
            "city": parsed.get("city", city_name),
            "county": county_name,
            "state": parsed.get("state", ""),
            "state_abbrev": parsed.get("state_abbrev", state.upper()),
            "zip_code": parsed.get("zip_code", ""),
            "country": country,
            "parent_jurisdictions": parent_jurisdictions,
            "lat": location.get("lat"),
            "lng": location.get("lng"),
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

    # Freshness check: query the most recent event to detect stale platforms.
    # Cities sometimes migrate off Legistar but leave the API running.
    metadata: Dict[str, Any] = {"client_name": client_name, "body_count": len(bodies)}
    warnings: list = []
    try:
        import requests as _req
        r = _req.get(
            f"https://webapi.legistar.com/v1/{client_name}/events?$top=1&$orderby=EventDate+desc",
            timeout=10,
        )
        if r.status_code == 200 and r.json():
            newest = r.json()[0].get("EventDate", "")[:10]
            metadata["newest_event"] = newest
            from datetime import datetime as _dt
            try:
                newest_dt = _dt.strptime(newest, "%Y-%m-%d")
                days_stale = (_dt.now() - newest_dt).days
                metadata["days_since_newest"] = days_stale
                if days_stale > 180:
                    warnings.append(
                        f"Legistar data appears stale — newest event is {newest} "
                        f"({days_stale} days ago). The city may have migrated to a different platform."
                    )
            except ValueError:
                pass
    except Exception:
        pass

    result = {
        "config": {
            "source_id": f"legistar-{client_name}",
            "source_type": "legistar",
            "jurisdiction_id": jurisdiction_id,
            "base_url": f"https://webapi.legistar.com/v1/{client_name}",
            "archives": archives,
            "metadata": metadata,
        },
        "discovered_bodies": archives,
    }
    if warnings:
        result["warnings"] = warnings
    return result


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


def discover_usaspending_candidates(
    display_name: str,
    level: str = "city",
) -> List[Dict[str, Any]]:
    """Search USAspending.gov for recipient candidates matching a jurisdiction.

    Searches broadly by display name, then groups results by unique recipient
    name. Returns all candidates — the caller decides which to keep.

    Government entities are sorted first (by award count), followed by
    non-government entities, so the most likely matches appear at the top.

    Args:
        display_name: Human-readable name (e.g., "San Rafael", "Marin County")
        level: Jurisdiction level ("city", "county", "state")

    Returns:
        List of candidate dicts, each with:
          - recipient_name: str
          - award_count: int
          - total_dollars: float
          - is_government: bool (heuristic)
    """
    import time

    # Strip level suffixes (e.g., "Marin County" -> "Marin")
    clean_name = re.sub(
        r"\s*(City|County|Town|District)$", "", display_name, flags=re.IGNORECASE
    ).strip()

    # Build search terms — the API searches recipient_name as substring
    # Use the bare name to cast a wide net
    search_terms = [clean_name.upper()]

    # Also try the formal "CITY OF X" / "COUNTY OF X" form
    if level == "county":
        search_terms.append(f"COUNTY OF {clean_name.upper()}")
    elif level == "city":
        search_terms.append(f"CITY OF {clean_name.upper()}")

    # Government name patterns (case-insensitive)
    gov_patterns = [
        "CITY OF ", "COUNTY OF ", "TOWN OF ", "VILLAGE OF ",
        "BOROUGH OF ", "TOWNSHIP OF ", "DISTRICT OF ",
        "HOUSING AUTHORITY", "TRANSIT DISTRICT", "WATER DISTRICT",
        "FIRE DISTRICT", "SCHOOL DISTRICT", "PORT AUTHORITY",
        ", CITY OF", ", COUNTY OF", ", TOWN OF",
        "METROPOLITAN", "MUNICIPALITY",
    ]

    try:
        from civicos_extraction.clients.usaspending import USAspendingClient

        # Collect all awards across search terms, deduplicate by award_id
        all_awards: Dict[str, Dict[str, Any]] = {}
        for term in search_terms:
            client = USAspendingClient(
                jurisdiction_id="probe",
                recipient_name=term,
            )
            batch = client.get_awards(max_pages=2)
            for a in batch:
                aid = a.get("award_id")
                if aid and aid not in all_awards:
                    all_awards[aid] = a
            time.sleep(0.5)

        if not all_awards:
            logger.info(f"USAspending: no awards found for '{clean_name}'")
            return []

        # Group by recipient name
        by_name: Dict[str, Dict[str, Any]] = {}
        for award in all_awards.values():
            name = award.get("recipient_name", "").strip()
            if not name:
                continue
            if name not in by_name:
                by_name[name] = {"count": 0, "total_cents": 0}
            by_name[name]["count"] += 1
            by_name[name]["total_cents"] += award.get("amount_cents", 0)

        # Build candidates
        candidates = []
        for name, stats in by_name.items():
            name_upper = name.upper()
            is_gov = any(pat in name_upper for pat in gov_patterns)
            candidates.append({
                "recipient_name": name,
                "award_count": stats["count"],
                "total_dollars": stats["total_cents"] / 100,
                "is_government": is_gov,
            })

        # Sort: government entities first (by award count desc), then non-gov
        candidates.sort(key=lambda c: (not c["is_government"], -c["award_count"]))

        logger.info(
            f"USAspending: found {len(candidates)} candidates for '{clean_name}' "
            f"({sum(1 for c in candidates if c['is_government'])} government)"
        )
        return candidates

    except Exception as e:
        logger.warning(f"USAspending discovery failed: {e}")
        return []


def _default_refresh_policies(level: str) -> Dict[str, Dict[str, str]]:
    """Return sensible default refresh policies based on jurisdiction level."""
    if level in ("city", "county", "town", "district", "council"):
        return {
            "meetings": {"interval": "1d", "strategy": "incremental"},
            "issues": {"interval": "1d", "strategy": "incremental"},
            "municipal_code": {"interval": "90d", "strategy": "content_hash"},
            "legislation": {"interval": "7d", "strategy": "incremental"},
        }
    elif level in ("state", "province"):
        return {
            "legislation": {"interval": "7d", "strategy": "incremental"},
        }
    elif level == "federal":
        return {
            "legislation": {"interval": "7d", "strategy": "incremental"},
        }
    return {}


def _default_governing_body(display_name: str, level: str) -> Dict[str, Optional[str]]:
    """Return placeholder governing body based on jurisdiction level."""
    if level == "city":
        return {
            "name": f"{display_name} City Council",
            "members_title": "Mayor and Council Members",
            "meeting_schedule": None,
            "meeting_location": None,
        }
    elif level == "town":
        return {
            "name": f"{display_name} Town Council",
            "members_title": "Mayor and Council Members",
            "meeting_schedule": None,
            "meeting_location": None,
        }
    elif level == "county":
        return {
            "name": f"{display_name} County Board of Supervisors",
            "members_title": "Supervisors",
            "meeting_schedule": None,
            "meeting_location": None,
        }
    return {
        "name": None,
        "members_title": None,
        "meeting_schedule": None,
        "meeting_location": None,
    }


def _usaspending_from_candidates(
    display_name: str,
    candidates: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Build federal_programs block from USAspending discovery candidates.

    Picks the top government candidate (highest award count) and builds
    search_names + allowed_names from it.
    """
    if not candidates:
        return None

    # Prefer government entities, then by award count
    gov_candidates = [c for c in candidates if c.get("is_government")]
    best = gov_candidates[0] if gov_candidates else candidates[0]

    recipient_name = best.get("recipient_name", display_name.upper())
    search_names = [recipient_name]

    # Add reversed form ("SAN RAFAEL, CITY OF") if it looks like "CITY OF SAN RAFAEL"
    match = re.match(r"^(CITY|COUNTY|TOWN|DISTRICT) OF (.+)$", recipient_name)
    if match:
        search_names.append(f"{match.group(2)}, {match.group(1)} OF")

    return {
        "usaspending": {
            "search_names": search_names,
            "allowed_names": list(search_names),
        },
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
    usaspending_candidates: Optional[List[Dict[str, Any]]] = None,
    contact_info: Optional[Dict[str, Optional[str]]] = None,
    youtube_playlist_id: Optional[str] = None,
    school_districts: Optional[List[str]] = None,
) -> str:
    """Generate complete jurisdiction YAML content from onboarding results.

    Level-aware: produces correct parent chains, financial fields, contact
    info, governing body, refresh policies, modal config, and federal programs
    for cities, counties, states, provinces, councils, and districts
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

    # Build contact_info with all fields (level-aware)
    # Merge auto-detected contact data with defaults
    ci = contact_info or {}
    contact_block: Dict[str, Any] = {
        "clerk_email": ci.get("clerk_email") or contact_email or None,
        "website": website or None,
    }
    if level in ("city", "county", "town", "district", "council"):
        contact_block.update({
            "city_hall_address": ci.get("city_hall_address"),
            "phone": ci.get("phone"),
            "public_comment_deadline": ci.get("public_comment_deadline") or "5:00 PM day of meeting",
            "in_person_time_limit": ci.get("in_person_time_limit") or "3 minutes",
            "public_comment_subject": "Public Comment - [Agenda Item Title]",
        })

    # Build data_sources with all corpus types
    data_sources: Dict[str, Any] = {
        "meetings": meetings_source,
        "issues": None,
        "budget": None,
        "municipal_code": None,
        "transcripts": {
            "source": "youtube" if youtube_playlist_id else None,
            "playlist_id": youtube_playlist_id,
        },
    }
    if level in ("state", "province"):
        data_sources["legislation"] = "leginfo_api"
        data_sources["revenue"] = None
    elif level == "federal":
        data_sources["legislation"] = "congress_api"
        data_sources["expenditures"] = None
        data_sources["funding"] = None

    # Build governing_body (level-aware defaults)
    governing_body = _default_governing_body(display_name, level)

    # Build financial context
    financial: Dict[str, Any] = {
        "state": state_abbrev,
    }
    if level != "county":
        financial["county"] = county_short

    # Build federal_programs from USAspending discovery
    federal_programs: Optional[Dict[str, Any]] = None
    if level in ("city", "county") and usaspending_candidates:
        federal_programs = _usaspending_from_candidates(
            display_name, usaspending_candidates
        )

    # Zip codes list (single zip from geocoding if available)
    zip_codes: List[str] = []
    if zip_code and level not in ("county", "state", "province"):
        zip_codes = [zip_code]

    doc: Dict[str, Any] = {
        "jurisdiction_id": jurisdiction_id,
        "level": level,
        "display_name": display_name,
        "parent_jurisdictions": parents,
        "contact_info": contact_block,
    }

    # Governing body (city/county levels)
    if level in ("city", "county", "town", "district", "council"):
        doc["governing_body"] = governing_body

    # State info (state-level only)
    if level in ("state", "province"):
        doc["state_info"] = {
            "abbreviation": state_abbrev,
            "timezone": None,
            "legislature": None,
            "governor_title": "Governor",
        }

    doc["data_sources"] = data_sources
    doc["financial"] = financial

    if federal_programs:
        doc["federal_programs"] = federal_programs

    if zip_codes:
        doc["zip_codes"] = zip_codes

    doc["ingestion"] = {
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

    doc["refresh"] = _default_refresh_policies(level)

    doc["tools_enabled"] = None
    doc["tool_overrides"] = {}

    doc["modal"] = {
        "min_containers": 0,
        "secrets": ["civicos-env"],
    }

    doc["metadata"] = {
        "created": today,
        "updated": today,
        "notes": "Auto-generated by onboard_jurisdiction().",
    }

    header = f"# {display_name} Configuration\n#\n# Auto-generated by onboard_jurisdiction().\n\n"
    return header + yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# School district lookup
# ---------------------------------------------------------------------------

def _get_school_districts_path() -> Path:
    try:
        return Path(__file__).parents[4] / "data" / "school_districts.json"
    except IndexError:
        return Path("/dev/null")


def load_school_districts(path: Optional[Path] = None) -> Dict[str, Dict[str, list]]:
    """Load the school district lookup table.

    Returns dict keyed by state (lowercase), then county (lowercase),
    each containing a list of district entries.
    """
    p = path or _get_school_districts_path()
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)


def lookup_school_district(
    name: str,
    state: str,
    county: Optional[str] = None,
    districts: Optional[Dict] = None,
) -> Optional[Dict[str, Any]]:
    """Find a school district by name (fuzzy substring match).

    Args:
        name: District name or partial name (e.g. "Novato", "Ross Valley")
        state: State abbreviation or full lowercase name
        county: Optional county to narrow search
        districts: Pre-loaded lookup table (loads from disk if None)

    Returns:
        Matching district entry dict, or None
    """
    if districts is None:
        districts = load_school_districts()

    state_key = _state_abbrev_to_slug(state) if len(state) <= 3 else state.lower()
    state_data = districts.get(state_key, {})
    if not state_data:
        return None

    name_lower = name.lower()

    # Search specific county or all counties in the state
    counties_to_search = (
        [county.lower()] if county else list(state_data.keys())
    )

    for county_key in counties_to_search:
        for entry in state_data.get(county_key, []):
            entry_name = entry.get("name", "").lower()
            # Match on: exact name, jurisdiction_id slug, or substring of name
            if (
                name_lower == entry_name
                or name_lower in entry_name
                or name_lower == entry.get("jurisdiction_id", "").replace("school-", "")
            ):
                return entry

    return None


def lookup_school_districts_by_county(
    state: str,
    county: str,
    districts: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Return all school districts in a given county.

    Args:
        state: State abbreviation or full lowercase name
        county: County name (e.g. "Marin")
        districts: Pre-loaded lookup table (loads from disk if None)

    Returns:
        List of district entry dicts (empty if none found)
    """
    if districts is None:
        districts = load_school_districts()

    state_key = _state_abbrev_to_slug(state) if len(state) <= 3 else state.lower()
    return districts.get(state_key, {}).get(county.lower(), [])


def onboard_jurisdiction(
    url: str,
    jurisdiction_id: Optional[str] = None,
    output_dir: str = "data/extraction",
    city_name: Optional[str] = None,
    state: Optional[str] = None,
    county: Optional[str] = None,
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
    warnings: List[str] = []
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

    # Upfront API key checks — warn before doing network work.
    # LLM calls (Granicus body naming, column maps, universal adapter) need at least
    # one of OPENAI_API_KEY or GOOGLE_API_KEY (Gemini). Without either, Granicus
    # onboarding degrades to generic names and the universal adapter fails entirely.
    _has_llm_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    _google_maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not _has_llm_key:
        _progress("warn", "No OPENAI_API_KEY or GOOGLE_API_KEY — LLM features disabled (body names, column maps, universal adapter)")
        logger.warning("No LLM API key set — Granicus body naming/column mapping will use fallbacks, universal adapter will fail")
    if generate_yaml and not _google_maps_key:
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
            elif platform == "civicplus":
                url = details.get("url", "")
            elif platform == "universal":
                url = details.get("meeting_page_url") or details.get("url", "")
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
        elif platform == "boarddocs":
            try:
                discovery_result = _discover_boarddocs(url, jurisdiction_id)
            except Exception as e:
                errors.append(f"BoardDocs discovery failed: {e}")
        elif platform == "proudcity":
            try:
                discovery_result = _discover_proudcity(url, jurisdiction_id)
            except Exception as e:
                errors.append(f"ProudCity discovery failed: {e}")
        elif platform == "civicplus":
            try:
                discovery_result = _discover_civicplus(url, jurisdiction_id, details)
            except Exception as e:
                errors.append(f"CivicPlus discovery failed: {e}")
        elif platform == "universal":
            try:
                discovery_result = _discover_universal(url, jurisdiction_id)
            except Exception as e:
                errors.append(f"Universal adapter discovery failed: {e}")

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
                    "Supported platforms: granicus, legistar, civicclerk, escribe, simbli, boarddocs, proudcity, civicplus."
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
            elif detection.source_type == "boarddocs":
                discovery_result = _discover_boarddocs(url, jurisdiction_id)
            elif detection.source_type == "proudcity":
                discovery_result = _discover_proudcity(url, jurisdiction_id)
            elif detection.source_type == "civicplus":
                discovery_result = _discover_civicplus(url, jurisdiction_id)
            elif detection.source_type == "universal":
                discovery_result = _discover_universal(url, jurisdiction_id)
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

    # Surface any warnings from platform discovery (e.g., stale Legistar data)
    for w in discovery_result.get("warnings", []):
        warnings.append(w)
        _progress("warn", w)

    # Step 2.5: Detect issue provider (if city_name available and not already set)
    if city_name and not config.get("issue_source"):
        _progress("issues", f"Probing 311/issue providers for '{city_name}'...")
        detected_source = detect_issue_source(city_name, jurisdiction_id)
        if detected_source:
            config["issue_source"] = detected_source
            _progress("issues", f"Detected issue provider: {detected_source}")
        else:
            _progress("issues", "No issue provider detected (will use default)")

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

    # Step 3.6: Detect election sources + districts
    # Use geocoding results if available, fall back to county parameter
    _election_county = (geo_data or {}).get("county") or county
    _election_lat = (geo_data or {}).get("lat")
    _election_lng = (geo_data or {}).get("lng")
    if _election_county and state:
        election_sources = detect_election_sources(
            jurisdiction_id, state, _election_county,
            lat=_election_lat, lng=_election_lng,
        )
        config["election_sources"] = election_sources
        source_names = list(election_sources.keys())
        # Find districts from whichever SOS source was detected
        districts = None
        for _src_key, _src_config in election_sources.items():
            if isinstance(_src_config, dict) and "districts" in _src_config:
                districts = _src_config["districts"]
                break
        if districts:
            _progress("election", f"Detected election sources: {source_names}, districts: {districts}")
        else:
            _progress("election", f"Detected election sources: {source_names}")
        # Warn about sources that have no fetch client yet
        from civicos_extraction.clients import SUPPORTED_ELECTION_SOURCES
        unsupported_sources = [k for k in election_sources if k not in SUPPORTED_ELECTION_SOURCES]
        if unsupported_sources:
            _progress(
                "election",
                f"Note: {unsupported_sources} detected but no fetch client yet. "
                f"Election results won't be fetched for these. "
                f"Federal/state officials (Congress.gov, LegiScan) are not affected.",
            )

    _progress("save", f"Saving config for {jurisdiction_id}...")

    # Persist state code in config — needed by RepresentativesClient for
    # federal/state official lookups (Congress.gov, LegiScan)
    if state and "state" not in config:
        config["state"] = state.upper()

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

    # Step 3.6.1: Fetch election data immediately (so new cities get data on day 1)
    election_sources_config = config.get("election_sources", {})
    if election_sources_config:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            _progress("election_fetch", "Fetching election data (this may take a minute)...")
            try:
                from civicos_extraction.election_fetch import fetch_elections_for_jurisdiction

                fetch_results = fetch_elections_for_jurisdiction(
                    jurisdiction_id, election_sources_config, database_url
                )
                # Summarize what was fetched
                fetched_sources = [
                    src for src, res in fetch_results.items()
                    if isinstance(res, dict) and res.get("status") == "completed"
                ]
                failed_sources = [
                    src for src, res in fetch_results.items()
                    if isinstance(res, dict) and res.get("status") == "failed"
                ]
                elapsed = fetch_results.get("elapsed_seconds", "?")
                if fetched_sources:
                    _progress("election_fetch", f"Election data fetched: {fetched_sources} ({elapsed}s)")
                if failed_sources:
                    _progress("election_fetch", f"Some sources failed (non-blocking): {failed_sources}")
                if not fetched_sources and not failed_sources:
                    _progress("election_fetch", "No election data sources matched — will retry via cron")
            except Exception as e:
                _progress("election_fetch", f"Election fetch skipped (non-blocking): {e}")
                logger.warning(f"Election fetch during onboard failed: {e}")
        else:
            _progress("election_fetch", "Skipping election fetch — no DATABASE_URL (will run via cron)")

    # Step 3.7: Discover USAspending candidates (free API, no key needed)
    usaspending_candidates: List[Dict[str, Any]] = []
    if level in ("city", "county"):
        inferred_display = city_name or re.sub(
            r"^(city|county|town|district|state|province|council)-", "",
            jurisdiction_id
        ).replace("-", " ").title()
        _progress("usaspending", f"Searching USAspending for '{inferred_display}'...")
        usaspending_candidates = discover_usaspending_candidates(inferred_display, level=level)
        if usaspending_candidates:
            gov_count = sum(1 for c in usaspending_candidates if c["is_government"])
            _progress("usaspending", f"Found {len(usaspending_candidates)} candidates ({gov_count} government)")

    # Step 3.8: Detect contact info from city website
    contact_data: Dict[str, Optional[str]] = _empty_contact_info()
    base_url_for_contact = config.get("base_url", url or "")
    inferred_display = city_name or re.sub(
        r"^(city|county|town|district|state|province|council)-", "",
        jurisdiction_id
    ).replace("-", " ").title()
    if base_url_for_contact and level in ("city", "county", "town"):
        _progress("contact", f"Detecting contact info from {base_url_for_contact}...")
        contact_data = detect_contact_info(base_url_for_contact, inferred_display)
        found = [k for k, v in contact_data.items() if v]
        if found:
            _progress("contact", f"Found: {', '.join(found)}")
        else:
            _progress("contact", "No contact info auto-detected (will need manual entry)")

    # Step 3.9: Detect YouTube playlist (if channel was found)
    youtube_channel = detect_youtube_channel(inferred_display, state or "")
    youtube_playlist_id = None
    if youtube_channel:
        _progress("youtube", f"Found YouTube channel: {youtube_channel['channel_title']}")
        youtube_playlist_id = detect_youtube_playlist(youtube_channel["channel_id"])
        if youtube_playlist_id:
            _progress("youtube", f"Found meeting playlist: {youtube_playlist_id}")

    # Step 3.10: Detect school districts (CA only, requires county)
    school_districts: List[str] = []
    county_for_schools = ""
    if geo_data:
        county_for_schools = re.sub(r"\s*County$", "", geo_data.get("county", ""), flags=re.IGNORECASE).strip()
    if county_for_schools and (state or "").upper() == "CA":
        _progress("schools", f"Detecting school districts from CA Dept of Education...")
        school_districts = detect_school_districts(inferred_display, county_for_schools)
        if school_districts:
            _progress("schools", f"Found {len(school_districts)} school districts: {school_districts}")

    # Step 4: Generate jurisdiction YAML (optional)
    yaml_path = None
    if generate_yaml:
        display_name = inferred_display

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
            contact_email=contact_data.get("clerk_email") or "",
            website=config.get("base_url", ""),
            parent_jurisdictions=parent_jurisdictions,
            level=level,
            county=county,
            zip_code=zip_code,
            state_abbrev=state_abbrev,
            country=geo_country,
            usaspending_candidates=usaspending_candidates,
            contact_info=contact_data,
            youtube_playlist_id=youtube_playlist_id,
            school_districts=school_districts,
        )
        JURISDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        yaml_path = JURISDICTIONS_DIR / f"{jurisdiction_id}.yaml"
        try:
            with open(yaml_path, "w") as f:
                f.write(yaml_content)
            logger.info(f"Jurisdiction YAML saved to {yaml_path}")
        except Exception as e:
            errors.append(f"Failed to save YAML: {e}")

        # Validate generated YAML against JurisdictionConfig schema
        if yaml_path and yaml_path.exists():
            try:
                from civicos.jurisdiction_config import (
                    load_jurisdiction_config,
                    validate_jurisdiction_config,
                )
                loaded_config = load_jurisdiction_config(jurisdiction_id)
                validation = validate_jurisdiction_config(loaded_config)
                if not validation.is_valid:
                    for issue in validation.issues:
                        if issue.severity == "error":
                            errors.append(f"YAML validation error: {issue.field} — {issue.message}")
                            _progress("yaml_validate", f"Error: {issue.field} — {issue.message}")
                else:
                    warn_count = sum(1 for i in validation.issues if i.severity == "warning")
                    _progress("yaml_validate", f"YAML valid ({warn_count} warnings)")
                    logger.info(f"Generated YAML passes validation ({warn_count} warnings)")
            except Exception as e:
                logger.warning(f"YAML validation skipped: {e}")
                _progress("yaml_validate", f"Validation skipped: {e}")

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

    # Universal/playwright_llm adapters don't use archives — skip this check
    source_type = config.get("source_type", "")
    if not discovered_bodies and source_type not in ("universal", "playwright_llm"):
        return OnboardResult(
            success=False,
            jurisdiction_id=jurisdiction_id,
            detection=detection_dict,
            config=config,
            config_path=str(config_path),
            discovered_bodies={},
            usaspending_candidates=usaspending_candidates,
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
        usaspending_candidates=usaspending_candidates,
        next_steps=next_steps,
        validation=validation_report,
        pipeline_result=pipeline_result_obj,
    )


# ---------------------------------------------------------------------------
# Election source backfill
# ---------------------------------------------------------------------------

_BACKFILL_SKIP_STEMS = {
    "civera_instances",
    "city-ghost",
    "city-test",
    "city-warn",
}


def _resolve_state_county(
    jurisdiction_id: str,
    config: dict,
    jurisdiction_dir: Path,
    default_state: Optional[str] = None,
    default_county: Optional[str] = None,
) -> tuple:
    """Resolve state and county for a jurisdiction from multiple sources.

    Resolution order:
    1. Jurisdiction YAML financial.state / financial.county
    2. Extraction config financial.state / financial.county
    3. County derived from jurisdiction_id for county-* types
    4. default_state / default_county fallbacks
    """
    state: Optional[str] = None
    county: Optional[str] = None

    # 1. Jurisdiction YAML
    yaml_path = jurisdiction_dir / f"{jurisdiction_id}.yaml"
    if yaml_path.exists():
        try:
            import yaml

            with open(yaml_path) as f:
                jur = yaml.safe_load(f) or {}
            fin = jur.get("financial") or {}
            state = fin.get("state")
            county = fin.get("county")
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to read YAML for {jurisdiction_id}: {e}")

    # 2. Extraction config financial section
    fin = config.get("financial") or {}
    state = state or fin.get("state")
    county = county or fin.get("county")

    # 3. Derive county from jurisdiction_id for county-* types
    if not county and jurisdiction_id.startswith("county-"):
        county = jurisdiction_id.removeprefix("county-").replace("-", " ").title()

    # 4. CLI defaults
    state = state or default_state
    county = county or default_county

    return state, county


def backfill_election_sources(
    config_dir: Optional[Path] = None,
    dry_run: bool = False,
    force: bool = False,
    filter_jurisdiction: Optional[str] = None,
    default_state: Optional[str] = None,
    default_county: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Backfill election_sources for extraction configs that lack them.

    Iterates extraction config JSON files, resolves state/county from
    jurisdiction YAML or config metadata, calls detect_election_sources(),
    and writes the result back into each config.

    Reusable after adding new providers — run with --force to re-detect all.

    Args:
        config_dir: Override extraction config directory.
        dry_run: Log what would change without writing files.
        force: Re-detect even if election_sources already present.
        filter_jurisdiction: Only process this jurisdiction_id.
        default_state: Fallback state code (e.g. "CA") when YAML/config lack it.
        default_county: Fallback county name (e.g. "Marin") when YAML/config lack it.

    Returns:
        List of result dicts: {jurisdiction_id, status, detail}.
    """
    from civicos_extraction.config import get_config_dir

    if config_dir is None:
        config_dir = get_config_dir()

    results: List[Dict[str, Any]] = []

    for config_path in sorted(config_dir.glob("*.json")):
        stem = config_path.stem

        # Skip hidden files, test fixtures, non-jurisdiction configs
        if stem.startswith(".") or stem in _BACKFILL_SKIP_STEMS:
            continue

        try:
            with open(config_path) as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            results.append({"jurisdiction_id": stem, "status": "error", "detail": str(e)})
            continue

        jurisdiction_id = config.get("jurisdiction_id", stem)

        # Skip legacy duplicates (filename doesn't match jurisdiction_id)
        if jurisdiction_id != stem:
            continue

        if filter_jurisdiction and jurisdiction_id != filter_jurisdiction:
            continue

        # Skip if already has election_sources (unless force)
        if "election_sources" in config and not force:
            results.append({
                "jurisdiction_id": jurisdiction_id,
                "status": "skipped",
                "detail": "already has election_sources",
            })
            continue

        # Resolve state and county
        state, county = _resolve_state_county(
            jurisdiction_id, config, JURISDICTIONS_DIR,
            default_state, default_county,
        )

        if not state:
            results.append({
                "jurisdiction_id": jurisdiction_id,
                "status": "skipped",
                "detail": "no state found (create YAML or pass --default-state)",
            })
            continue

        if not county:
            results.append({
                "jurisdiction_id": jurisdiction_id,
                "status": "skipped",
                "detail": f"no county found for state={state} (create YAML or pass --default-county)",
            })
            continue

        # Detect election sources
        try:
            election_sources = detect_election_sources(jurisdiction_id, state, county)
        except Exception as e:
            results.append({
                "jurisdiction_id": jurisdiction_id,
                "status": "error",
                "detail": f"detection failed: {e}",
            })
            continue

        if not election_sources:
            results.append({
                "jurisdiction_id": jurisdiction_id,
                "status": "no_sources",
                "detail": f"no sources detected (state={state}, county={county})",
            })
            continue

        # Write back
        if not dry_run:
            config["election_sources"] = election_sources
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
                f.write("\n")

        action = "would update" if dry_run else "updated"
        source_names = list(election_sources.keys())
        results.append({
            "jurisdiction_id": jurisdiction_id,
            "status": action,
            "detail": f"sources: {source_names}",
        })

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Jurisdiction onboarding utilities")
    subparsers = parser.add_subparsers(dest="command")

    bp = subparsers.add_parser(
        "backfill-elections",
        help="Backfill election_sources in extraction configs",
    )
    bp.add_argument("--dry-run", action="store_true", help="Log changes without writing")
    bp.add_argument("--force", action="store_true", help="Re-detect even if already present")
    bp.add_argument("--jurisdiction", help="Only process this jurisdiction_id")
    bp.add_argument("--default-state", help="Fallback state code (e.g. CA)")
    bp.add_argument("--default-county", help="Fallback county name (e.g. Marin)")

    args = parser.parse_args()

    if args.command == "backfill-elections":
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        results = backfill_election_sources(
            dry_run=args.dry_run,
            force=args.force,
            filter_jurisdiction=args.jurisdiction,
            default_state=args.default_state,
            default_county=args.default_county,
        )

        for r in results:
            icon = {
                "updated": "+", "would update": "~",
                "skipped": ".", "no_sources": "-", "error": "!",
            }.get(r["status"], "?")
            print(f"  {icon} {r['jurisdiction_id']}: {r['detail']}")

        updated = sum(1 for r in results if r["status"] in ("updated", "would update"))
        skipped = sum(1 for r in results if r["status"] == "skipped")
        errors = sum(1 for r in results if r["status"] == "error")
        prefix = "DRY RUN: " if args.dry_run else ""
        print(f"\n{prefix}Updated: {updated}, Skipped: {skipped}, Errors: {errors}")
    else:
        parser.print_help()
