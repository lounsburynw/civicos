#!/usr/bin/env python3
"""
Generate Registry Files from Jurisdiction YAMLs

Reads data/jurisdictions/*.yaml and patches:
1. config/registry.json — service routing
2. packages/civicos-config/src/civicos_config/jurisdiction.py — JurisdictionRegistry
3. packages/civicos/src/civicos/_internal/jurisdiction.py — aliases + display names

Usage:
    python scripts/generate_registries.py                    # Patch all registries
    python scripts/generate_registries.py --check            # Dry-run, report what would change
    python scripts/generate_registries.py --yaml city-foo    # Patch from specific YAML only
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
JURISDICTIONS_DIR = ROOT / "data" / "jurisdictions"
REGISTRY_JSON = ROOT / "config" / "registry.json"
JURISDICTION_PY = ROOT / "packages" / "civicos-config" / "src" / "civicos_config" / "jurisdiction.py"
ALIASES_PY = ROOT / "packages" / "civicos" / "src" / "civicos" / "_internal" / "jurisdiction.py"

# Marker comments used to delimit auto-generated sections in Python files
GENERATED_BEGIN = "# --- BEGIN AUTO-GENERATED FROM YAML ---"
GENERATED_END = "# --- END AUTO-GENERATED FROM YAML ---"


def load_jurisdiction_yamls(specific: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load jurisdiction YAML files."""
    yamls = []
    if specific:
        path = JURISDICTIONS_DIR / f"{specific}.yaml"
        if not path.exists():
            print(f"YAML not found: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path) as f:
            yamls.append(yaml.safe_load(f))
    else:
        for path in sorted(JURISDICTIONS_DIR.glob("*.yaml")):
            if path.name == "schema.yaml":
                continue
            with open(path) as f:
                data = yaml.safe_load(f)
                if data and "jurisdiction_id" in data:
                    # Only process jurisdictions with meeting data sources
                    meetings = (data.get("data_sources") or {}).get("meetings")
                    if meetings and meetings.get("source_type"):
                        yamls.append(data)
    return yamls


def patch_registry_json(yamls: List[Dict[str, Any]], check: bool = False) -> bool:
    """Patch config/registry.json with jurisdiction entries from YAMLs."""
    with open(REGISTRY_JSON) as f:
        registry = json.load(f)

    changed = False
    for y in yamls:
        jid = y["jurisdiction_id"]
        # Skip if already present
        if jid in registry.get("jurisdictions", {}):
            continue

        display = y.get("display_name", jid)
        # Derive domain slug from jurisdiction_id: city-mill-valley -> mill-valley
        slug = jid.replace("city-", "").replace("county-", "").replace("state-", "")
        entry = {
            "domain": f"{slug}.civicosproject.org",
            "display_name": display,
            "modal_app_name": f"civicos-{slug}",
            "parent_jurisdictions": y.get("parent_jurisdictions", []),
        }
        registry.setdefault("jurisdictions", {})[jid] = entry
        changed = True
        print(f"  registry.json: + {jid}")

    if changed and not check:
        with open(REGISTRY_JSON, "w") as f:
            json.dump(registry, f, indent=2)
            f.write("\n")
    return changed


def _city_key(jurisdiction_id: str) -> str:
    """Convert jurisdiction_id to registry key: city-san-anselmo -> san_anselmo."""
    return (
        jurisdiction_id
        .replace("city-", "")
        .replace("county-", "")
        .replace("state-", "")
        .replace("-", "_")
    )


def _generate_registry_entry(y: Dict[str, Any]) -> str:
    """Generate a Python JurisdictionConfig entry from YAML data."""
    jid = y["jurisdiction_id"]
    key = _city_key(jid)
    display = y.get("display_name", "")
    meetings = y.get("data_sources", {}).get("meetings", {}) or {}
    source_type = meetings.get("source_type", "standard")
    base_url = meetings.get("base_url", "")
    metadata = meetings.get("metadata", {}) or {}
    contact = y.get("contact_info", {}) or {}
    governing = y.get("governing_body", {}) or {}

    # Build meeting URL
    view_id = metadata.get("default_view_id", "1")
    if source_type == "granicus" and base_url:
        meeting_url = f"{base_url}/ViewPublisher.php?view_id={view_id}"
    else:
        meeting_url = base_url or contact.get("website", "")

    # Determine hall name
    level = y.get("level", "city")
    hall_name = f"{display} {'Town' if level == 'town' else 'City'} Hall"

    # Extract domain from website
    website = contact.get("website", "")
    domains = []
    if website:
        domain = re.sub(r"https?://(?:www\.)?", "", website).rstrip("/")
        if domain:
            domains.append(domain)

    lines = [
        f'    "{key}": JurisdictionConfig(',
        f'        jurisdiction_id="{jid}",',
        f'        agent_type="{source_type}",',
        f'        meeting_urls=["{meeting_url}"],',
        f'        contact_email="{contact.get("clerk_email", "")}",',
        f'        timezone="America/Los_Angeles",',
        f'        website="{website}",',
        f'        meeting_calendar_url="{meeting_url}",',
        f'        display_name="{display}",',
        f'        hall_name="{hall_name}",',
    ]

    if domains:
        domains_str = ", ".join(f'"{d}"' for d in domains)
        lines.append(f'        domains=({domains_str},),')

    if source_type == "granicus":
        granicus_domain = metadata.get("granicus_domain", "")
        lines.append(
            f'        granicus_config=GranicusConfig(subdomain="{granicus_domain}", view_id={int(view_id)}),'
        )

    lines.append("    ),")
    return "\n".join(lines)


def patch_jurisdiction_py(yamls: List[Dict[str, Any]], check: bool = False) -> bool:
    """Patch jurisdiction.py with JurisdictionConfig entries from YAMLs."""
    content = JURISDICTION_PY.read_text()

    # Find existing keys in _REGISTRY
    existing_keys = set(re.findall(r'"(\w+)":\s*JurisdictionConfig\(', content))

    entries_to_add = []
    for y in yamls:
        key = _city_key(y["jurisdiction_id"])
        if key not in existing_keys:
            entries_to_add.append(y)

    if not entries_to_add:
        return False

    # Find the end of _REGISTRY dict to insert before it
    # Look for the closing brace of _REGISTRY = { ... }
    # We insert before the last "}" that closes the dict
    # Find the pattern: last entry followed by closing }
    generated_code = []
    for y in entries_to_add:
        key = _city_key(y["jurisdiction_id"])
        display = y.get("display_name", key.replace("_", " ").title())
        generated_code.append(f"\n    # ---------- {display} (auto-generated from YAML) ----------")
        generated_code.append(_generate_registry_entry(y))
        print(f"  jurisdiction.py: + {key}")

    # Insert before the closing "}" of _REGISTRY
    # Find "}\n\n# Build reverse lookup" pattern
    insert_marker = "}\n\n# Build reverse lookup"
    if insert_marker not in content:
        print("  WARNING: Could not find insertion point in jurisdiction.py", file=sys.stderr)
        return False

    new_entries = "\n".join(generated_code)
    new_content = content.replace(insert_marker, f"{new_entries}\n{insert_marker}")

    if not check:
        JURISDICTION_PY.write_text(new_content)
    return True


def _generate_aliases(y: Dict[str, Any]) -> List[str]:
    """Generate alias entries for a jurisdiction."""
    jid = y["jurisdiction_id"]
    display = y.get("display_name", "")

    # Generate slug variations
    slug_hyphen = jid.replace("city-", "").replace("county-", "")  # e.g., "san-anselmo"
    slug_no_sep = slug_hyphen.replace("-", "")  # e.g., "sananselmo"

    aliases = [
        f'    "{slug_hyphen}": "{jid}",',
        f'    "{slug_hyphen}-ca": "{jid}",',
    ]
    if slug_no_sep != slug_hyphen:
        aliases.append(f'    "{slug_no_sep}": "{jid}",')

    return aliases


def patch_aliases_py(yamls: List[Dict[str, Any]], check: bool = False) -> bool:
    """Patch _internal/jurisdiction.py with aliases and display names from YAMLs."""
    content = ALIASES_PY.read_text()

    # Find existing aliases
    existing_aliases = set(re.findall(r'"([^"]+)":\s*"(?:city|county|state|school|bart)-', content))

    aliases_to_add = []
    display_to_add = []

    for y in yamls:
        jid = y["jurisdiction_id"]
        display = y.get("display_name", "")
        slug_hyphen = jid.replace("city-", "").replace("county-", "")

        if slug_hyphen not in existing_aliases:
            aliases_to_add.append(y)
            print(f"  aliases.py: + aliases for {jid}")

        if display and jid not in content:
            display_to_add.append(y)

    changed = False

    # Add aliases before the closing "}" of _JURISDICTION_ALIASES
    if aliases_to_add:
        # Find the end of _JURISDICTION_ALIASES dict
        alias_end_pattern = re.compile(
            r'("(?:pleasant-hill|scotts-valley|[^"]+)":\s*"city-[^"]+",\s*\n)(})', re.MULTILINE
        )
        # Simpler: find the line with the last alias before "}"
        # Look for pattern: closing of _JURISDICTION_ALIASES
        # Find "}\n\n# Display names"
        alias_marker = "}\n\n# Display names"
        if alias_marker in content:
            new_alias_lines = []
            for y in aliases_to_add:
                jid = y["jurisdiction_id"]
                display = y.get("display_name", "")
                new_alias_lines.append(f"\n    # {display} (auto-generated)")
                new_alias_lines.extend(_generate_aliases(y))

            alias_block = "\n".join(new_alias_lines)
            content = content.replace(alias_marker, f"{alias_block}\n{alias_marker}")
            changed = True

    # Add display names before the closing "}" of _DISPLAY_NAMES
    if display_to_add:
        # Find end of _DISPLAY_NAMES dict
        display_marker = '}\n\n\ndef normalize_jurisdiction'
        if display_marker in content:
            new_display_lines = []
            for y in display_to_add:
                jid = y["jurisdiction_id"]
                display = y.get("display_name", "")
                if display:
                    new_display_lines.append(f'    "{jid}": "{display}",')

            display_block = "\n".join(new_display_lines)
            content = content.replace(display_marker, f"{display_block}\n{display_marker}")
            changed = True

    if changed and not check:
        ALIASES_PY.write_text(content)
    return changed


def main():
    parser = argparse.ArgumentParser(description="Generate registry files from jurisdiction YAMLs")
    parser.add_argument("--check", action="store_true", help="Dry-run, report what would change")
    parser.add_argument("--yaml", type=str, help="Process specific YAML only (e.g., city-foo)")
    args = parser.parse_args()

    yamls = load_jurisdiction_yamls(args.yaml)
    if not yamls:
        print("No jurisdiction YAMLs found.")
        return

    print(f"Processing {len(yamls)} jurisdiction YAML(s)...")
    if args.check:
        print("(dry run — no files will be modified)")

    any_changed = False
    any_changed |= patch_registry_json(yamls, args.check)
    any_changed |= patch_jurisdiction_py(yamls, args.check)
    any_changed |= patch_aliases_py(yamls, args.check)

    if any_changed:
        action = "would be" if args.check else "were"
        print(f"\nRegistries {action} updated.")
    else:
        print("\nAll registries already up to date.")


if __name__ == "__main__":
    main()
