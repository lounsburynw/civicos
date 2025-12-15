#!/usr/bin/env python3
"""
Complaint Handler - End-to-end orchestration for conversational issue workflow

Orchestrates: detect → store → match → respond
"""

from typing import Dict, Any, Optional

# Handle both module and standalone execution
from .issue_detector import IssueDetector
from ..storage.issue_storage import IssueStorage
from .issue_matcher import match_issue_to_events
from .issue_fallback import handle_no_match


class ComplaintHandler:
    """Orchestrate full issue workflow from conversational input"""

    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize handler with detector and storage"""
        self.detector = IssueDetector(openai_api_key)
        self.storage = IssueStorage()

    def handle_user_message(self, message: str, user_id: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main entry point for handling user messages

        Args:
            message: User's conversational message
            user_id: User identifier
            user_context: Optional context (jurisdiction, etc.)

        Returns:
            Response dictionary with matches or fallback
        """
        # Step 1: Detect issue intent
        intent = self.detector.detect_complaint(message, user_context)
        if not intent:
            return {
                'type': 'not_complaint',
                'message': 'How can I help you with civic information?'
            }

        # Step 2: Create and match issue
        return self._create_and_match(intent, user_id)

    def _create_and_match(self, intent, user_id: str) -> Dict[str, Any]:
        """Create issue and match to events"""
        # Validate jurisdiction
        if not intent.jurisdiction_id:
            return {
                'type': 'missing_jurisdiction',
                'message': 'Which city is this issue in? (e.g., Berkeley, Oakland, San Rafael)',
                'intent': intent.to_dict()
            }

        # Map issue type to database schema
        issue_type = self._normalize_issue_type(intent.issue_type)

        # Store issue
        issue_id = self.storage.create_issue(
            user_id=user_id,
            description=intent.description,
            jurisdiction_id=intent.jurisdiction_id,
            issue_type=issue_type
        )

        # Get issue for matching
        issue = self.storage.get_issue(issue_id)
        if not issue:
            return {
                'type': 'error',
                'message': 'Failed to create issue record'
            }

        # Match to events
        matches = match_issue_to_events(issue)

        if matches:
            return self._format_match_response(issue, matches)
        else:
            return self._handle_no_match(issue)

    def _format_match_response(self, issue: Dict[str, Any], matches: list) -> Dict[str, Any]:
        """Format response with matched events"""
        top_matches = matches[:3]  # Show top 3 matches

        events_list = []
        for event, score, reason in top_matches:
            events_list.append({
                'title': event['title'],
                'when': event.get('when_human', event.get('when')),
                'meeting_type': event.get('meeting_type', 'unknown'),
                'score': round(score, 1),
                'why_relevant': reason
            })

        return {
            'type': 'matched',
            'issue_id': issue['id'],
            'message': f"Found {len(matches)} relevant civic meetings where you can address this issue:",
            'matches': events_list,
            'actions': [
                {'type': 'view_details', 'label': 'View Meeting Details'},
                {'type': 'get_reminders', 'label': 'Get Reminders'}
            ]
        }

    def _handle_no_match(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Handle issue with no matches (fallback strategy)"""
        fallback_response = handle_no_match(issue)

        return {
            'type': 'no_match',
            'issue_id': issue['id'],
            'message': fallback_response['message'],
            'similar_count': fallback_response.get('similar_count', 0),
            'actions': fallback_response.get('actions', [])
        }

    def _normalize_issue_type(self, issue_type: str) -> str:
        """
        Normalize issue type to match database schema

        Database accepts: housing, transportation, environment, public_safety, infrastructure, other
        Detector may produce: housing, transportation, environment, public_safety, infrastructure, community
        """
        if issue_type == 'community':
            return 'other'
        return issue_type


def handle_message(message: str, user_id: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convenience function for handling a single message

    Example:
        response = handle_message(
            message="My landlord won't fix the heating",
            user_id="user123",
            user_context={'jurisdiction_id': 'city-berkeley'}
        )
    """
    handler = ComplaintHandler()
    return handler.handle_user_message(message, user_id, user_context)


if __name__ == "__main__":
    """Test issue handler with sample messages"""
    import json

    # Test message
    test_message = "There's a huge pothole on Main Street in Berkeley that needs fixing"
    test_user_id = "test_user_001"

    print("Testing Complaint Handler")
    print(f"Message: {test_message}")
    print()

    response = handle_message(test_message, test_user_id)

    print("Response:")
    print(json.dumps(response, indent=2))
