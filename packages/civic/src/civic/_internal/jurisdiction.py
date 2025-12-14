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
"""

from typing import Optional
import re


# Known jurisdiction mappings (extend as needed)
# Format: short_form -> canonical_form
_JURISDICTION_ALIASES = {
    "san-rafael": "city-san-rafael",
    "san-rafael-ca": "city-san-rafael",
    "berkeley": "city-berkeley",
    "berkeley-ca": "city-berkeley",
    "marin": "county-marin",
    "marin-ca": "county-marin",
}

# Display names for jurisdictions
_DISPLAY_NAMES = {
    "city-san-rafael": "San Rafael",
    "city-berkeley": "Berkeley",
    "county-marin": "Marin County",
}


def normalize_jurisdiction(jurisdiction_id: str) -> str:
    """
    Normalize jurisdiction ID to canonical format.

    Converts various input formats to canonical "city-{name}" or "county-{name}".

    Args:
        jurisdiction_id: Input jurisdiction ID in any supported format

    Returns:
        Canonical jurisdiction ID

    Examples:
        >>> normalize_jurisdiction("san-rafael")
        'city-san-rafael'
        >>> normalize_jurisdiction("san-rafael-ca")
        'city-san-rafael'
        >>> normalize_jurisdiction("city-san-rafael")
        'city-san-rafael'
    """
    if not jurisdiction_id:
        return jurisdiction_id

    # Normalize to lowercase
    normalized = jurisdiction_id.lower().strip()

    # Already canonical format
    if normalized.startswith(("city-", "county-")):
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
        # Default to city if not found
        return f"city-{base}"

    # Default to city prefix for unknown formats
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
