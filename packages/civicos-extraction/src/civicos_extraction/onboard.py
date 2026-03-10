"""
Jurisdiction Onboarding

Unified flow for onboarding a new jurisdiction from just a URL.
Detects the civic platform, runs platform-specific discovery, and
generates an ExtractionConfig JSON file.

Usage:
    from civicos_extraction.onboard import onboard_jurisdiction

    result = onboard_jurisdiction("https://marin.granicus.com", "county-marin")
    if result.success:
        print(f"Config saved to: {result.config_path}")
        print(f"Discovered bodies: {result.discovered_bodies}")
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from civicos_extraction.platform_detection import detect_platform

logger = logging.getLogger(__name__)


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
