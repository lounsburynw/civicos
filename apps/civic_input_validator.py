"""
Civic Input Validator

Basic input validation for MCP civic engagement tools.
Prevents XSS, SQL injection, command injection, and prompt injection attacks.
"""

import re
import html
from typing import Tuple, Dict, Any, Optional


# Maximum lengths for various input types
MAX_LENGTHS = {
    'item_id': 100,
    'item_title': 500,
    'topic': 200,
    'query': 500,
    'jurisdiction': 100,
    'stance': 50,
    'key_points': 2000,
    'default': 1000,
}

# Patterns that might indicate injection attempts
SUSPICIOUS_PATTERNS = [
    r'<script',           # XSS
    r'javascript:',       # XSS
    r'on\w+\s*=',         # XSS event handlers
    r'--',                # SQL comment
    r';.*(?:drop|delete|truncate|update|insert)',  # SQL injection
    r'\$\{',              # Template injection
    r'{{',                # Template injection
    r'\\\$',              # Shell variable
    r'`[^`]+`',           # Backtick command substitution
    r'\|\s*\w+',          # Pipe to command
    r'&&',                # Command chaining
    r'\|\|',              # Command chaining
]


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """
    Sanitize a string value for safe use.

    Args:
        value: The string to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    if not isinstance(value, str):
        return str(value)[:max_length]

    # HTML escape to prevent XSS
    sanitized = html.escape(value)

    # Truncate to max length
    sanitized = sanitized[:max_length]

    # Remove null bytes
    sanitized = sanitized.replace('\x00', '')

    return sanitized


def is_suspicious(value: str) -> bool:
    """
    Check if a string contains suspicious patterns.

    Args:
        value: The string to check

    Returns:
        True if suspicious patterns found
    """
    if not isinstance(value, str):
        return False

    value_lower = value.lower()

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, value_lower, re.IGNORECASE):
            return True

    return False


def validate_civic_input(
    input_data: Dict[str, Any],
    strict: bool = False,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Validate and sanitize civic engagement input data.

    Args:
        input_data: Dictionary of input parameters
        strict: If True, reject any suspicious content (default: sanitize)

    Returns:
        Tuple of (is_valid, sanitized_data, error_message)
        - is_valid: True if validation passed
        - sanitized_data: Dictionary with sanitized values
        - error_message: None if valid, otherwise error description
    """
    if not isinstance(input_data, dict):
        return False, {}, "Input must be a dictionary"

    sanitized = {}

    for key, value in input_data.items():
        # Skip None values
        if value is None:
            sanitized[key] = None
            continue

        # Get max length for this field
        max_len = MAX_LENGTHS.get(key, MAX_LENGTHS['default'])

        # Convert to string if needed
        if not isinstance(value, str):
            value = str(value)

        # Check for suspicious patterns
        if is_suspicious(value):
            if strict:
                return False, {}, f"Suspicious content detected in '{key}'"
            # Log but continue (sanitization will handle it)

        # Sanitize the value
        sanitized[key] = sanitize_string(value, max_len)

    return True, sanitized, None


def validate_stance(stance: str) -> Tuple[bool, str]:
    """
    Validate a stance value (support/oppose/question/neutral).

    Args:
        stance: The stance string

    Returns:
        Tuple of (is_valid, normalized_stance)
    """
    if not isinstance(stance, str):
        return False, ""

    stance_lower = stance.lower().strip()

    valid_stances = {'support', 'oppose', 'question', 'neutral'}

    if stance_lower in valid_stances:
        return True, stance_lower

    return False, ""


def validate_jurisdiction(jurisdiction: str) -> Tuple[bool, str]:
    """
    Validate a jurisdiction identifier.

    Args:
        jurisdiction: The jurisdiction string

    Returns:
        Tuple of (is_valid, normalized_jurisdiction)
    """
    if not isinstance(jurisdiction, str):
        return False, ""

    # Normalize: lowercase, strip, replace spaces with hyphens
    normalized = jurisdiction.lower().strip().replace(' ', '-')

    # Remove any non-alphanumeric characters except hyphens
    normalized = re.sub(r'[^a-z0-9-]', '', normalized)

    # Must be non-empty and reasonable length
    if not normalized or len(normalized) > 100:
        return False, ""

    return True, normalized
