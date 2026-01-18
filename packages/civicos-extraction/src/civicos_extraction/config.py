"""
Jurisdiction configuration loader.

Loads jurisdiction-specific configuration from data/extraction/*.json files.
Each jurisdiction has its own config file with extraction sources, financial
data sources, and federal program relationships.

Usage:
    from civicos_extraction.config import load_jurisdiction_config, get_active_jurisdictions

    # Load single jurisdiction
    config = load_jurisdiction_config("city-san-rafael")
    hud_grantee = config.get("federal_programs", {}).get("hud_grantee")

    # Get all active jurisdictions
    jurisdictions = get_active_jurisdictions()
    for jid, config in jurisdictions.items():
        print(f"{jid}: {config.get('base_url')}")
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default config directory relative to project root
DEFAULT_CONFIG_DIR = "data/extraction"


def _find_project_root() -> Path:
    """Find the project root by looking for known marker files."""
    current = Path(__file__).resolve()

    # Walk up looking for phase.json or .git
    for parent in [current] + list(current.parents):
        if (parent / "phase.json").exists() or (parent / ".git").exists():
            return parent

    # Fallback: assume we're in packages/civic-extraction/src/civic_extraction/
    return current.parent.parent.parent.parent.parent


def get_config_dir() -> Path:
    """Get the jurisdiction config directory path."""
    # Check environment variable first
    if config_dir := os.environ.get("CIVICOS_CONFIG_DIR"):
        return Path(config_dir)

    return _find_project_root() / DEFAULT_CONFIG_DIR


def load_jurisdiction_config(jurisdiction_id: str) -> Dict[str, Any]:
    """
    Load configuration for a specific jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")

    Returns:
        Configuration dict, or empty dict if not found

    Example config structure:
        {
            "jurisdiction_id": "city-san-rafael",
            "base_url": "https://www.cityofsanrafael.org",
            "financial": {"state": "CA", "county": "Marin"},
            "federal_programs": {
                "hud_grantee": "Marin County",
                "hud_relationship": "consortium"
            }
        }
    """
    config_dir = get_config_dir()

    # Try jurisdiction ID directly (e.g., city-san-rafael.json)
    config_file = config_dir / f"{jurisdiction_id}.json"

    # Also try without city- prefix (e.g., san-rafael.json)
    if not config_file.exists() and jurisdiction_id.startswith("city-"):
        alt_name = jurisdiction_id.replace("city-", "", 1)
        config_file = config_dir / f"{alt_name}.json"

    if not config_file.exists():
        logger.warning(f"No config file found for {jurisdiction_id} in {config_dir}")
        return {}

    try:
        with open(config_file) as f:
            config = json.load(f)

        # Ensure jurisdiction_id is set
        if "jurisdiction_id" not in config:
            config["jurisdiction_id"] = jurisdiction_id

        return config

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {config_file}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error loading {config_file}: {e}")
        return {}


def get_active_jurisdictions() -> Dict[str, Dict[str, Any]]:
    """
    Get all active jurisdiction configurations.

    Scans the config directory for *.json files and loads each one.
    Excludes files that don't have a jurisdiction_id or are supplementary
    configs (like school districts).

    Returns:
        Dict mapping jurisdiction_id to config dict
    """
    config_dir = get_config_dir()
    jurisdictions: Dict[str, Dict[str, Any]] = {}

    if not config_dir.exists():
        logger.warning(f"Config directory not found: {config_dir}")
        return jurisdictions

    for config_file in config_dir.glob("*.json"):
        # Skip supplementary configs (e.g., san-rafael-schools.json)
        if "-schools" in config_file.name or "-districts" in config_file.name:
            continue

        try:
            with open(config_file) as f:
                config = json.load(f)

            # Must have jurisdiction_id or be derivable from filename
            jid = config.get("jurisdiction_id")
            if not jid:
                # Derive from filename: san-rafael.json -> city-san-rafael
                name = config_file.stem
                if not name.startswith(("city-", "county-", "state-")):
                    jid = f"city-{name}"
                else:
                    jid = name
                config["jurisdiction_id"] = jid

            jurisdictions[jid] = config

        except Exception as e:
            logger.warning(f"Error loading {config_file}: {e}")

    return jurisdictions


def get_jurisdictions_with_hud_config() -> List[Dict[str, Any]]:
    """
    Get jurisdictions that have HUD federal program configuration.

    Returns list of configs that have federal_programs.hud_grantee defined,
    used by the HUD allocations pipeline.

    Returns:
        List of jurisdiction configs with HUD grantee info
    """
    jurisdictions = get_active_jurisdictions()

    return [
        config for config in jurisdictions.values()
        if config.get("federal_programs", {}).get("hud_grantee")
    ]


def get_hud_grantee(jurisdiction_id: str) -> Optional[str]:
    """
    Get the HUD grantee name for a jurisdiction.

    For cities in consortiums (like San Rafael in Marin County),
    this returns the consortium grantee name, not the city name.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")

    Returns:
        HUD grantee name (e.g., "Marin County"), or None if not configured
    """
    config = load_jurisdiction_config(jurisdiction_id)
    return config.get("federal_programs", {}).get("hud_grantee")


def get_hud_relationship(jurisdiction_id: str) -> Optional[str]:
    """
    Get the HUD relationship type for a jurisdiction.

    Returns:
        "consortium", "direct_entitlement", or None if not configured
    """
    config = load_jurisdiction_config(jurisdiction_id)
    return config.get("federal_programs", {}).get("hud_relationship")
