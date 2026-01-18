"""
CommunityStorage protocol for public feedback and participation.

Handles 311 issues from providers like SeeClickFix, PublicStuff, etc.
Future: voices, initiatives, community organizing data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class CommunityStorage(Protocol):
    """
    Protocol for community feedback and participation storage.

    Currently covers:
    - Issues: 311 complaints from providers (SeeClickFix, PublicStuff)

    Future additions (post-pilot):
    - Voices: Public testimony and community input
    - Initiatives: Citizen-led campaigns and organizing

    This is the smallest sub-protocol but represents a distinct domain
    for community-government interaction data.
    """

    # ========== Issue Methods ==========

    def store_issues(
        self,
        jurisdiction_id: str,
        issues: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store 311 issues with temporal versioning.

        Uses upsert semantics based on (provider, external_id).
        """
        ...

    def get_issues(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        issue_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve 311 issues with optional filtering."""
        ...

    def get_issue_count(
        self,
        jurisdiction_id: str,
        provider: Optional[str] = None,
    ) -> int:
        """Get count of current issues for a jurisdiction."""
        ...
