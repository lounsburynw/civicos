#!/usr/bin/env python3
"""
Validate Registry and Jurisdiction YAML Files

Checks:
1. Jurisdiction YAML required fields and format
2. config/registry.json integrity (domain uniqueness, parent refs, required fields)
3. Cross-file consistency (YAML filename matches jurisdiction_id)

Usage:
    python scripts/validate_registry.py                # Validate everything
    python scripts/validate_registry.py --yaml-only    # Only validate YAML files
    python scripts/validate_registry.py --registry-only # Only validate registry.json
    python scripts/validate_registry.py --files city-san-rafael.yaml  # Specific files

Exit codes:
    0 = all checks pass
    1 = validation errors found
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
JURISDICTIONS_DIR = ROOT / "data" / "jurisdictions"
REGISTRY_JSON = ROOT / "config" / "registry.json"
VALIDATION_RULES = JURISDICTIONS_DIR / "validation_rules.json"


def _load_validation_rules() -> Dict[str, Any]:
    """Load validation rules from data/jurisdictions/validation_rules.json."""
    with open(VALIDATION_RULES) as f:
        return json.load(f)


_rules = _load_validation_rules()

VALID_LEVELS = set(_rules["levels"])
LEVEL_PREFIXES = _rules["level_prefixes"]
VALID_SOURCE_TYPES = set(_rules["source_types"])

# Jurisdiction ID pattern: prefix-slug (lowercase alphanumeric + hyphens)
JURISDICTION_ID_RE = re.compile(r"^(city|county|state|country|school|college|board|bart|region)-[a-z0-9]+(-[a-z0-9]+)*$")

# Registry entry required fields
REGISTRY_REQUIRED_FIELDS = {"domain", "display_name", "modal_app_name", "parent_jurisdictions"}


class ValidationResult:
    """Collects validation errors and warnings."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"\n{len(self.errors)} error(s):")
            for e in self.errors:
                lines.append(f"  ERROR: {e}")
        if self.warnings:
            lines.append(f"\n{len(self.warnings)} warning(s):")
            for w in self.warnings:
                lines.append(f"  WARN: {w}")
        if self.ok and not self.warnings:
            lines.append("\nAll checks passed.")
        return "\n".join(lines)


def validate_yaml_file(path: Path, result: ValidationResult, all_yaml_ids: set) -> Dict[str, Any] | None:
    """Validate a single jurisdiction YAML file."""
    prefix = f"[{path.name}]"

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result.error(f"{prefix} Invalid YAML: {e}")
        return None

    if not isinstance(data, dict):
        result.error(f"{prefix} YAML root must be a mapping, got {type(data).__name__}")
        return None

    # Required fields
    jid = data.get("jurisdiction_id")
    if not jid:
        result.error(f"{prefix} Missing required field: jurisdiction_id")
        return None

    # Filename must match jurisdiction_id
    expected_filename = f"{jid}.yaml"
    if path.name != expected_filename:
        result.error(f"{prefix} Filename '{path.name}' does not match jurisdiction_id '{jid}' (expected '{expected_filename}')")

    # ID format
    if not JURISDICTION_ID_RE.match(jid):
        result.error(f"{prefix} Invalid jurisdiction_id format: '{jid}' (must match {JURISDICTION_ID_RE.pattern})")

    # Duplicate ID
    if jid in all_yaml_ids:
        result.error(f"{prefix} Duplicate jurisdiction_id: '{jid}'")
    all_yaml_ids.add(jid)

    # Level
    level = data.get("level")
    if not level:
        result.error(f"{prefix} Missing required field: level")
    elif level not in VALID_LEVELS:
        result.error(f"{prefix} Invalid level '{level}' (valid: {', '.join(sorted(VALID_LEVELS))})")
    elif jid:
        # Check ID prefix matches level
        expected_prefix = LEVEL_PREFIXES.get(level)
        if expected_prefix and not jid.startswith(f"{expected_prefix}-"):
            result.error(f"{prefix} jurisdiction_id '{jid}' should start with '{expected_prefix}-' for level '{level}'")

    # Display name
    if not data.get("display_name"):
        result.error(f"{prefix} Missing required field: display_name")

    # Parent jurisdictions
    parents = data.get("parent_jurisdictions")
    if parents is None:
        result.error(f"{prefix} Missing required field: parent_jurisdictions")
    elif not isinstance(parents, list):
        result.error(f"{prefix} parent_jurisdictions must be a list")
    else:
        for p in parents:
            if not isinstance(p, str):
                result.error(f"{prefix} parent_jurisdictions entry must be a string, got {type(p).__name__}")
            elif not JURISDICTION_ID_RE.match(p):
                result.error(f"{prefix} Invalid parent jurisdiction ID format: '{p}'")

        # country-united-states should have no parents
        if jid == "country-united-states" and parents:
            result.warn(f"{prefix} Federal jurisdiction has parent_jurisdictions (should be empty)")

    # Data sources (required but can be minimal)
    ds = data.get("data_sources")
    if ds is not None and isinstance(ds, dict):
        meetings = ds.get("meetings")
        if meetings and isinstance(meetings, dict):
            source_type = meetings.get("source_type")
            if source_type and source_type not in VALID_SOURCE_TYPES:
                result.warn(f"{prefix} Unknown meeting source_type: '{source_type}' (known: {', '.join(sorted(VALID_SOURCE_TYPES))})")
            if source_type and not meetings.get("base_url"):
                result.warn(f"{prefix} Meeting source_type '{source_type}' set but no base_url")

    return data


def validate_registry_json(result: ValidationResult) -> Dict[str, Any] | None:
    """Validate config/registry.json."""
    prefix = "[registry.json]"

    if not REGISTRY_JSON.exists():
        result.error(f"{prefix} File not found: {REGISTRY_JSON}")
        return None

    try:
        with open(REGISTRY_JSON) as f:
            registry = json.load(f)
    except json.JSONDecodeError as e:
        result.error(f"{prefix} Invalid JSON: {e}")
        return None

    if not isinstance(registry, dict):
        result.error(f"{prefix} Root must be an object")
        return None

    jurisdictions = registry.get("jurisdictions")
    if not isinstance(jurisdictions, dict):
        result.error(f"{prefix} Missing or invalid 'jurisdictions' field")
        return None

    # Check each jurisdiction entry
    domains_seen: Dict[str, str] = {}
    all_jids = set(jurisdictions.keys())

    for jid, entry in jurisdictions.items():
        entry_prefix = f"[registry.json:{jid}]"

        # ID format
        if not JURISDICTION_ID_RE.match(jid):
            result.error(f"{entry_prefix} Invalid jurisdiction_id format")

        if not isinstance(entry, dict):
            result.error(f"{entry_prefix} Entry must be an object")
            continue

        # Required fields
        for field in REGISTRY_REQUIRED_FIELDS:
            if field not in entry:
                result.error(f"{entry_prefix} Missing required field: {field}")

        # Domain uniqueness
        domain = entry.get("domain")
        if domain:
            if domain in domains_seen:
                result.error(f"{entry_prefix} Duplicate domain '{domain}' (also used by {domains_seen[domain]})")
            domains_seen[domain] = jid

        # Parent jurisdiction references must exist in registry
        parents = entry.get("parent_jurisdictions", [])
        if isinstance(parents, list):
            for p in parents:
                if p not in all_jids:
                    result.warn(f"{entry_prefix} Parent '{p}' not found in registry (may be expected for partial registries)")

    return registry


def validate_cross_consistency(yamls: Dict[str, Dict], registry: Dict[str, Any] | None, result: ValidationResult):
    """Check consistency between YAML files and registry.json."""
    if not registry:
        return

    registry_jids = set(registry.get("jurisdictions", {}).keys())

    for jid, data in yamls.items():
        # YAML with meeting sources should appear in registry
        ds = data.get("data_sources", {}) or {}
        meetings = ds.get("meetings", {}) or {}
        if meetings.get("source_type") and jid not in registry_jids:
            result.warn(f"[cross-check] {jid} has meeting source but is not in registry.json (run generate_registries.py)")

        # Check display_name consistency
        if jid in registry_jids:
            yaml_name = data.get("display_name", "")
            reg_name = registry["jurisdictions"][jid].get("display_name", "")
            if yaml_name and reg_name and yaml_name != reg_name:
                result.error(f"[cross-check] display_name mismatch for {jid}: YAML='{yaml_name}', registry='{reg_name}'")

            # Check parent_jurisdictions consistency
            yaml_parents = data.get("parent_jurisdictions", [])
            reg_parents = registry["jurisdictions"][jid].get("parent_jurisdictions", [])
            if yaml_parents and reg_parents and set(yaml_parents) != set(reg_parents):
                result.error(f"[cross-check] parent_jurisdictions mismatch for {jid}: YAML={yaml_parents}, registry={reg_parents}")


def main():
    parser = argparse.ArgumentParser(description="Validate registry and jurisdiction YAML files")
    parser.add_argument("--yaml-only", action="store_true", help="Only validate YAML files")
    parser.add_argument("--registry-only", action="store_true", help="Only validate registry.json")
    parser.add_argument("--files", nargs="+", help="Specific YAML filenames to validate")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    result = ValidationResult()
    yamls: Dict[str, Dict] = {}
    registry = None

    # Validate YAMLs
    if not args.registry_only:
        yaml_files = []
        if args.files:
            for f in args.files:
                path = JURISDICTIONS_DIR / f if not Path(f).is_absolute() else Path(f)
                if path.exists():
                    yaml_files.append(path)
                else:
                    result.error(f"File not found: {path}")
        else:
            yaml_files = sorted(
                p for p in JURISDICTIONS_DIR.glob("*.yaml")
                if p.name != "schema.yaml"
            )

        all_yaml_ids: set = set()
        for path in yaml_files:
            data = validate_yaml_file(path, result, all_yaml_ids)
            if data and "jurisdiction_id" in data:
                yamls[data["jurisdiction_id"]] = data

        print(f"Validated {len(yaml_files)} YAML file(s)")

    # Validate registry.json
    if not args.yaml_only:
        registry = validate_registry_json(result)
        if registry:
            n = len(registry.get("jurisdictions", {}))
            print(f"Validated registry.json ({n} jurisdiction(s))")

    # Cross-consistency
    if not args.yaml_only and not args.registry_only:
        validate_cross_consistency(yamls, registry, result)

    # Output
    if args.json:
        print(json.dumps({
            "ok": result.ok,
            "errors": result.errors,
            "warnings": result.warnings,
        }, indent=2))
    else:
        print(result.summary())

    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
