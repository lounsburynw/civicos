"""
311 issue provider implementations.

Each provider implements the IssueProvider protocol to fetch and normalize
issues from a specific 311 platform.
"""

from typing import Dict, Type

from civic.issues.provider import IssueProvider


# Registry of available providers
_PROVIDERS: Dict[str, Type[IssueProvider]] = {}


def register_provider(name: str, provider_cls: Type[IssueProvider]) -> None:
    """Register a provider implementation."""
    _PROVIDERS[name] = provider_cls


def get_provider(name: str) -> IssueProvider:
    """
    Get a provider instance by name.

    Args:
        name: Provider name ("seeclickfix", "publicstuff", etc.)

    Returns:
        Provider instance

    Raises:
        ValueError: If provider not found
    """
    if name not in _PROVIDERS:
        available = ", ".join(_PROVIDERS.keys()) or "none"
        raise ValueError(f"Unknown provider: {name}. Available: {available}")
    return _PROVIDERS[name]()


def list_providers() -> list[str]:
    """List available provider names."""
    return list(_PROVIDERS.keys())


# Import providers to trigger registration
# Note: SeeclickfixProvider is imported lazily to avoid circular imports
# and because civic-services may not always be installed
