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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from civicos_extraction.platform_detection import detect_platform

logger = logging.getLogger(__name__)

# Path to cost_registry.yaml (relative to repo root)
_COST_REGISTRY_PATH = Path(__file__).parents[4] / "docs" / "private" / "operations" / "cost_registry.yaml"


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

    if not _COST_REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Cost registry not found: {_COST_REGISTRY_PATH}")

    with open(_COST_REGISTRY_PATH) as f:
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


def _infer_jurisdiction_id(url: str) -> Optional[str]:
    """Infer a jurisdiction_id from a URL."""
    # Granicus: marin.granicus.com → county-marin (or city-marin)
    match = re.match(r"https?://([^.]+)\.granicus\.com", url)
    if match:
        return match.group(1)

    # General city sites: cityofsanrafael.org → san-rafael
    from civicos_extraction.platform_detection import _extract_client_name

    return _extract_client_name(url)


def _discover_granicus(url: str, jurisdiction_id: str) -> Dict[str, Any]:
    """Run Granicus-specific discovery."""
    from civicos_extraction.clients.granicus import GranicusClient

    match = re.match(r"https?://([^.]+)\.granicus\.com", url)
    domain = match.group(1) if match else ""

    client = GranicusClient(
        granicus_domain=domain,
        jurisdiction_id=jurisdiction_id,
    )

    discovered = client.discover_view_ids()

    # Build ExtractionConfig dict
    config = {
        "source_id": f"granicus-{jurisdiction_id}",
        "source_type": "granicus",
        "jurisdiction_id": jurisdiction_id,
        "base_url": f"https://{domain}.granicus.com",
        "archives": discovered,
        "metadata": {
            "granicus_domain": domain,
            "default_view_id": "1",
        },
    }

    return {
        "config": config,
        "discovered_bodies": discovered,
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


def onboard_jurisdiction(
    url: str,
    jurisdiction_id: Optional[str] = None,
    output_dir: str = "data/extraction",
) -> OnboardResult:
    """
    Onboard a new jurisdiction from a URL.

    Flow:
    1. Detect platform from URL
    2. Run platform-specific discovery
    3. Generate ExtractionConfig JSON
    4. Save to output_dir

    Args:
        url: City/county website or platform URL
        jurisdiction_id: Optional jurisdiction ID. Inferred from URL if not provided.
        output_dir: Directory to save config JSON (default: data/extraction)

    Returns:
        OnboardResult with config, discovered bodies, and next steps
    """
    errors: List[str] = []

    # Infer jurisdiction_id if not provided
    if not jurisdiction_id:
        jurisdiction_id = _infer_jurisdiction_id(url)
        if not jurisdiction_id:
            return OnboardResult(
                success=False,
                errors=["Could not infer jurisdiction_id from URL. Please provide one."],
            )

    # Step 1: Detect platform
    detection = detect_platform(url, jurisdiction_id=jurisdiction_id)
    detection_dict = detection.to_dict()

    if not detection.source_type or detection.confidence < 0.5:
        return OnboardResult(
            success=False,
            jurisdiction_id=jurisdiction_id,
            detection=detection_dict,
            errors=[
                f"No platform detected (confidence: {detection.confidence:.0%}). "
                "Supported platforms: granicus, legistar, civicclerk, proudcity."
            ],
            next_steps=[
                "Check that the URL is correct",
                "If this is a new platform, implement a client in civicos-extraction",
            ],
        )

    # Step 2: Platform-specific discovery
    discovery_result: Optional[Dict[str, Any]] = None
    try:
        if detection.source_type == "granicus":
            discovery_result = _discover_granicus(url, jurisdiction_id)
        elif detection.source_type == "proudcity":
            discovery_result = _discover_proudcity(url, jurisdiction_id)
        else:
            # For legistar/civicclerk, generate basic config
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

    # Step 4: Build next steps
    next_steps = [
        f"Review config at {config_path}",
        f"Create jurisdiction YAML: data/jurisdictions/{jurisdiction_id}.yaml",
        "Run health check: source.health()",
        "Test extraction: source.get_meetings(days_ahead=30)",
    ]

    if not discovered_bodies:
        next_steps.insert(0, "No bodies discovered automatically — add archives manually to config")

    return OnboardResult(
        success=True,
        jurisdiction_id=jurisdiction_id,
        detection=detection_dict,
        config=config,
        config_path=str(config_path),
        discovered_bodies=discovered_bodies,
        next_steps=next_steps,
    )
