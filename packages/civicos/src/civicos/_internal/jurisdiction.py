"""
Jurisdiction ID Normalization Utilities

Provides centralized handling of jurisdiction IDs across the Civic platform.

Canonical format: "city-{name}" or "county-{name}"
Examples:
    - "city-san-rafael"
    - "county-marin"

This module normalizes various input formats to the canonical form:
    - "san-rafael" -> "city-san-rafael"
    - "san-rafael-ca" -> "city-san-rafael"
    - "city-san-rafael" -> "city-san-rafael" (idempotent)

Strict validation: Unknown jurisdiction IDs raise JurisdictionError.
"""

from typing import Optional
import re


class JurisdictionError(Exception):
    """Raised when an invalid or unknown jurisdiction ID is provided."""
    pass


# Known jurisdiction mappings for common short forms.
# All aliases MUST map to jurisdiction IDs that exist in JurisdictionRegistry.
# Format: short_form -> canonical_form
#
# Note: The normalize_jurisdiction() function also handles:
# - Automatic city- prefix (e.g., "oakland" -> "city-oakland")
# - Underscore-to-hyphen conversion (e.g., "san_rafael" -> "san-rafael")
# - State suffix stripping (e.g., "oakland-ca" -> "city-oakland")
#
# Explicit aliases are needed for:
# - Cases where the short form differs from the canonical name
# - Cases requiring special handling (e.g., "sonoma" -> "sonoma-county")
_JURISDICTION_ALIASES = {
    # San Rafael (pilot city)
    "san-rafael": "city-san-rafael",
    "san-rafael-ca": "city-san-rafael",
    "sanrafael": "city-san-rafael",

    # San Rafael City Schools (pilot school district)
    "srcs": "school-san-rafael",
    "san-rafael-schools": "school-san-rafael",
    "san-rafael-city-schools": "school-san-rafael",

    # Berkeley
    "berkeley": "city-berkeley",
    "berkeley-ca": "city-berkeley",

    # Mill Valley (federation test)
    "mill-valley": "city-mill-valley",
    "mill-valley-ca": "city-mill-valley",
    "millvalley": "city-mill-valley",

    # San Anselmo (federation test)
    "san-anselmo": "city-san-anselmo",
    "san-anselmo-ca": "city-san-anselmo",
    "sananselmo": "city-san-anselmo",

    # Marin County
    "marin": "county-marin",
    "marin-county": "county-marin",  # Legacy suffix form

    # Sonoma County
    "sonoma": "county-sonoma",
    "sonoma-ca": "county-sonoma",
    "sonoma-county": "county-sonoma",  # Legacy suffix form

    # BART (no city- prefix)
    "sf-bart": "bart",
    "bay-area-rapid-transit": "bart",

    # Cities with multi-word names (explicit for clarity)
    "los-altos": "city-los-altos",
    "los-altos-hills": "city-los-altos-hills",
    "el-cerrito": "city-el-cerrito",
    "daly-city": "city-daly-city",
    "union-city": "city-union-city",
    "san-leandro": "city-san-leandro",
    "santa-rosa": "city-santa-rosa",
    "pleasant-hill": "city-pleasant-hill",
    "scotts-valley": "city-scotts-valley",

    # Novato (auto-generated)
    "novato": "city-novato",
    "novato-ca": "city-novato",

    # Sacramento (auto-generated)
    "sacramento": "city-sacramento",
    "sacramento-ca": "city-sacramento",

    # Alameda County (auto-generated)
    "alameda": "county-alameda",
    "alameda-ca": "county-alameda",
}

# Display names for jurisdictions (override generated names)
# Only needed when the auto-generated name is incorrect or awkward.
# The display_jurisdiction() function generates names by:
# - Stripping "city-" prefix and title-casing
# - Adding " County" suffix for "county-" prefix
_DISPLAY_NAMES = {
    "city-san-rafael": "San Rafael",
    "school-san-rafael": "San Rafael City Schools",
    "city-berkeley": "Berkeley",
    "city-el-cerrito": "El Cerrito",
    "city-los-altos": "Los Altos",
    "city-los-altos-hills": "Los Altos Hills",
    "city-daly-city": "Daly City",
    "city-union-city": "Union City",
    "city-san-leandro": "San Leandro",
    "city-santa-rosa": "Santa Rosa",
    "city-pleasant-hill": "Pleasant Hill",
    "city-scotts-valley": "Scotts Valley",
    "county-sonoma": "Sonoma County",
    "county-marin": "Marin County",
    "bart": "BART",
    "city-novato": "Novato",
    "city-sacramento": "Sacramento",
    "county-alameda": "Alameda County",
}


def normalize_jurisdiction(jurisdiction_id: str, strict: bool = True) -> str:
    """
    Normalize jurisdiction ID to canonical format.

    Converts various input formats to canonical "city-{name}" or "county-{name}".
    With strict=True (default), raises JurisdictionError for unknown jurisdictions.

    Args:
        jurisdiction_id: Input jurisdiction ID in any supported format
        strict: If True, raise JurisdictionError for unknown IDs (default: True)

    Returns:
        Canonical jurisdiction ID

    Raises:
        JurisdictionError: If strict=True and jurisdiction is not in the registry

    Examples:
        >>> normalize_jurisdiction("san-rafael")
        'city-san-rafael'
        >>> normalize_jurisdiction("san-rafael-ca")
        'city-san-rafael'
        >>> normalize_jurisdiction("city-san-rafael")
        'city-san-rafael'
        >>> normalize_jurisdiction("bogus-city")
        JurisdictionError: Unknown jurisdiction ID: 'bogus-city'
    """
    # Import from civicos_config (shared package)
    from civicos_config import JurisdictionRegistry

    if not jurisdiction_id:
        return jurisdiction_id

    # Normalize to lowercase and convert underscores to hyphens
    # This allows both "san_rafael" and "san-rafael" to work
    normalized = jurisdiction_id.lower().strip().replace("_", "-")

    # Already canonical format - validate against registry
    # Includes: city-, county-, state-, country- prefixes
    if normalized.startswith(("city-", "county-", "state-", "country-")):
        if JurisdictionRegistry.has_jurisdiction(normalized):
            return normalized
        # Special case: federal/state/country IDs may not be in the city registry
        # but are valid hierarchical identifiers. Allow them through since they
        # have a valid prefix format. This enables multi-level MCP servers
        # (federal, state, city) to all use the same normalization.
        if normalized.startswith(("state-", "country-")):
            return normalized
        # Only raise for city/county that aren't registered
        if strict:
            raise JurisdictionError(
                f"Unknown jurisdiction ID: '{jurisdiction_id}'. "
                f"Valid IDs: {', '.join(sorted(JurisdictionRegistry.all_jurisdiction_ids())[:5])}..."
            )
        return normalized

    # Check known aliases
    if normalized in _JURISDICTION_ALIASES:
        return _JURISDICTION_ALIASES[normalized]

    # Try to infer canonical form
    # Remove state suffix (e.g., "-ca")
    if re.match(r".*-[a-z]{2}$", normalized):
        base = normalized[:-3]  # Remove "-ca" etc.
        if base in _JURISDICTION_ALIASES:
            return _JURISDICTION_ALIASES[base]
        # Try with city- prefix
        candidate = f"city-{base}"
        if JurisdictionRegistry.has_jurisdiction(candidate):
            return candidate

    # Try with city- prefix as last resort
    candidate = f"city-{normalized}"
    if JurisdictionRegistry.has_jurisdiction(candidate):
        return candidate

    # Try suffix-based inference: "yolo-county" → "county-yolo", "kentfield-school" → "school-kentfield"
    for suffix in ("-county", "-school", "-college"):
        if normalized.endswith(suffix):
            prefix = suffix.lstrip("-")
            base = normalized[: -len(suffix)]
            candidate = f"{prefix}-{base}"
            if JurisdictionRegistry.has_jurisdiction(candidate):
                return candidate

    # Check for special jurisdiction IDs without prefix (e.g., "bart", "sonoma-county")
    if JurisdictionRegistry.has_jurisdiction(normalized):
        return normalized

    # Strict mode: reject unknown jurisdictions
    if strict:
        raise JurisdictionError(
            f"Unknown jurisdiction ID: '{jurisdiction_id}'. "
            f"Valid IDs: {', '.join(sorted(JurisdictionRegistry.all_jurisdiction_ids())[:5])}..."
        )

    # Non-strict mode: return with city- prefix (legacy behavior)
    return f"city-{normalized}"


def display_jurisdiction(jurisdiction_id: str) -> str:
    """
    Convert canonical jurisdiction ID to user-friendly display name.

    Args:
        jurisdiction_id: Canonical jurisdiction ID

    Returns:
        Human-readable jurisdiction name

    Examples:
        >>> display_jurisdiction("city-san-rafael")
        'San Rafael'
        >>> display_jurisdiction("county-marin")
        'Marin County'
    """
    canonical = normalize_jurisdiction(jurisdiction_id)

    if canonical in _DISPLAY_NAMES:
        return _DISPLAY_NAMES[canonical]

    # Generate display name from canonical form
    if canonical.startswith("city-"):
        name = canonical[5:]  # Remove "city-"
        return name.replace("-", " ").title()
    elif canonical.startswith("county-"):
        name = canonical[7:]  # Remove "county-"
        return f"{name.replace('-', ' ').title()} County"

    return jurisdiction_id.replace("-", " ").title()


def extract_state(jurisdiction_id: str) -> Optional[str]:
    """
    Extract state from jurisdiction ID.

    Args:
        jurisdiction_id: Jurisdiction ID in any format

    Returns:
        Full state name or None if not determinable

    Examples:
        >>> extract_state("san-rafael-ca")
        'california'
        >>> extract_state("city-san-rafael")
        'california'
    """
    normalized = jurisdiction_id.lower().strip()

    # Check explicit state suffix
    if normalized.endswith("-ca"):
        return "california"

    # Known California jurisdictions
    canonical = normalize_jurisdiction(normalized)
    if canonical in _JURISDICTION_ALIASES.values():
        # All currently supported jurisdictions are in California
        return "california"

    # Check city-/county- prefix (assume California for now)
    if canonical.startswith(("city-", "county-")):
        return "california"

    return None


def is_valid_jurisdiction(jurisdiction_id: str) -> bool:
    """
    Validate that a jurisdiction ID is in a recognizable format.

    Args:
        jurisdiction_id: Jurisdiction ID to validate

    Returns:
        True if format is valid, False otherwise
    """
    if not jurisdiction_id:
        return False

    normalized = jurisdiction_id.lower().strip()

    # Known aliases are valid
    if normalized in _JURISDICTION_ALIASES:
        return True

    # Canonical format is valid
    if normalized.startswith(("city-", "county-")):
        return True

    # Format with state suffix is valid
    if re.match(r"^[a-z-]+-[a-z]{2}$", normalized):
        return True

    return False
