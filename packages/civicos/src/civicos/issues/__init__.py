"""
311 issue abstraction layer for Civic.

Provides a portable interface for multiple 311 providers (SeeClickFix, PublicStuff, CitySourced, etc.)
with a unified data model and storage path.

Usage:
    from civicos.issues import IssueProvider, NormalizedIssue, get_provider

    # Get a specific provider
    provider = get_provider("seeclickfix")
    issues = provider.get_issues("san-rafael")

    # Issues are normalized to a common format
    for issue in issues:
        print(f"{issue.title} at {issue.address}")
"""

from .provider import IssueProvider, NormalizedIssue

__all__ = ["IssueProvider", "NormalizedIssue"]
