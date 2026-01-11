"""
Complaint Fallback Strategy for Unmatched Complaints

Phase 1: Issue banking only (track for future matching)
Phase 2: Add clustering, 311 integration
"""

import logging
from typing import Dict, List

from ..storage.issue_storage import IssueStorage

logger = logging.getLogger(__name__)


def handle_no_match(issue: Dict) -> Dict:
    """
    Handle a issue that didn't match any events.

    Phase 1 Strategy:
    - Bank issue in database (status remains 'open')
    - Find similar issues
    - Return user-friendly message with next steps

    Args:
        issue: Complaint dict with full data

    Returns:
        Response dict with:
        - message: User-friendly message
        - actions: Available civic actions
        - similar_count: Number of similar issues
    """
    storage = IssueStorage()

    # Bank issue (already in DB, just query similar)
    similar_complaints = _find_similar_complaints(issue, storage)

    # Generate appropriate message based on community size
    message = _generate_no_match_message(
        issue,
        len(similar_complaints)
    )

    # Generate civic actions
    actions = _generate_fallback_actions(issue, similar_complaints)

    logger.info(
        f"Complaint {issue['id']} banked with {len(similar_complaints)} similar issues"
    )

    return {
        "message": message,
        "actions": actions,
        "similar_count": len(similar_complaints),
        "community_formation_potential": "high" if len(similar_complaints) >= 3 else "low"
    }


def _find_similar_complaints(issue: Dict, storage: IssueStorage) -> List[Dict]:
    """
    Find similar issues for clustering.

    Phase 1: Use IssueStorage.find_similar_complaints()
    Phase 2: Add geographic clustering with Haversine distance
    """
    jurisdiction_id = issue.get("jurisdiction_id")
    issue_type = issue.get("issue_type")

    if not jurisdiction_id or not issue_type:
        return []

    # Get location if available
    location = None
    if issue.get("latitude") and issue.get("longitude"):
        location = {
            "latitude": issue["latitude"],
            "longitude": issue["longitude"]
        }

    similar = storage.find_similar_complaints(
        jurisdiction_id=jurisdiction_id,
        issue_type=issue_type,
        location=location
    )

    # Filter out the current issue from similar list
    similar = [c for c in similar if c.get("id") != issue.get("id")]

    return similar


def _generate_no_match_message(issue: Dict, similar_count: int) -> str:
    """
    Generate user-friendly message based on similar issue count.

    Message strategy:
    - 3+ similar: Emphasize community formation potential
    - 1-2 similar: Mention others tracking, promise notifications
    - 0 similar: Track for future, promise notifications
    """
    issue_type = issue.get("issue_type", "this issue")
    jurisdiction = issue.get("jurisdiction_id", "").replace("city-", "").replace("-", " ").title()

    if similar_count >= 3:
        return (
            f"We didn't find any upcoming meetings about {issue_type} in {jurisdiction}, "
            f"but {similar_count} neighbors have reported similar issues. "
            f"Consider connecting to organize around this concern. "
            f"We'll notify you when relevant meetings are scheduled."
        )
    elif similar_count >= 1:
        return (
            f"We didn't find any upcoming meetings about {issue_type} in {jurisdiction}, "
            f"but {similar_count} other neighbor{'s have' if similar_count == 1 else 's have'} reported similar issues. "
            f"We're tracking this and will notify you when relevant meetings are scheduled."
        )
    else:
        return (
            f"We didn't find any upcoming meetings about {issue_type} in {jurisdiction}, "
            f"but we're tracking your concern. "
            f"We'll notify you when relevant meetings are scheduled or when other neighbors report similar issues."
        )


def _generate_fallback_actions(issue: Dict, similar_complaints: List[Dict]) -> List[Dict]:
    """
    Generate civic actions for unmatched issues.

    Phase 1: Track issue, view similar
    Phase 2: Join discussion group, escalate to proposal
    """
    actions = []

    # Always offer tracking
    actions.append({
        "action_type": "button",
        "action_label": "Track This Issue",
        "action_target": "track_complaint",
        "mcp_tool": "track_issue",
        "description": "Get notified when meetings are scheduled"
    })

    # If there are similar issues, offer to view them
    if len(similar_complaints) >= 3:
        actions.append({
            "action_type": "button",
            "action_label": f"View {len(similar_complaints)} Similar Complaints",
            "action_target": "view_similar",
            "mcp_tool": "view_similar_complaints",
            "description": "Connect with neighbors on this issue"
        })

    return actions


def check_banked_complaints_for_new_event(event: Dict) -> List[str]:
    """
    Re-match banked issues when new events are published.

    Called by event extraction pipeline when new events are added.

    Args:
        event: New event dict

    Returns:
        List of complaint_ids that now match this event
    """
    from .issue_matcher import _score_event, MINIMUM_MATCH_SCORE

    storage = IssueStorage()
    jurisdiction_id = event.get("jurisdiction", {}).get("id")

    if not jurisdiction_id:
        return []

    # Phase 2: Query open (unmatched) issues for re-matching

    logger.debug(f"Checking banked issues for new event in {jurisdiction_id}")

    return []  # Phase 2: Implement re-matching
