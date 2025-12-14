#!/usr/bin/env python3
"""
Tests for complaint handler - end-to-end workflow validation (Layer 4)

Validates: detect → store → match → respond pipeline
"""

import pytest
import sys
import os
import sqlite3

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from complaint_handler import ComplaintHandler, handle_message
from complaint_storage import ComplaintStorage


@pytest.fixture
def handler():
    """Create handler instance"""
    return ComplaintHandler()


@pytest.fixture
def clean_test_db():
    """Create a clean test database"""
    # Use in-memory database for tests
    storage = ComplaintStorage(':memory:')
    yield storage
    # Cleanup happens automatically with in-memory DB


class TestComplaintHandler:
    """Test end-to-end complaint handling workflow"""

    def test_handle_valid_complaint_with_matches(self, handler):
        """Should detect, store, and match complaint to events"""
        message = "My landlord won't fix the heating in my Berkeley apartment"
        user_id = "test_user_001"
        user_context = {'jurisdiction_id': 'city-berkeley'}

        response = handler.handle_user_message(message, user_id, user_context)

        # Should create a matched response
        assert response['type'] in ['matched', 'no_match'], f"Unexpected type: {response['type']}"
        assert 'complaint_id' in response
        assert 'message' in response

        print(f"\nResponse type: {response['type']}")
        print(f"Message: {response['message']}")

        if response['type'] == 'matched':
            assert 'matches' in response
            assert len(response['matches']) > 0
            print(f"Found {len(response['matches'])} matches")
            for match in response['matches']:
                print(f"  - {match['title'][:50]}...")
        else:
            print("No matches found (fallback strategy)")

    def test_handle_non_complaint(self, handler):
        """Should recognize non-complaints"""
        message = "When is the next city council meeting?"
        user_id = "test_user_002"

        response = handler.handle_user_message(message, user_id)

        assert response['type'] == 'not_complaint'
        assert 'message' in response
        print(f"\nNon-complaint response: {response['message']}")

    def test_handle_complaint_without_jurisdiction(self, handler):
        """Should request jurisdiction if not detected"""
        message = "There's a pothole on Main Street"  # No city mentioned
        user_id = "test_user_003"

        response = handler.handle_user_message(message, user_id)

        # Should either match (if jurisdiction inferred) or ask for jurisdiction
        assert response['type'] in ['missing_jurisdiction', 'matched', 'no_match']
        print(f"\nResponse type: {response['type']}")
        print(f"Message: {response['message']}")

    def test_handle_complaint_with_user_context(self, handler):
        """Should use user context for jurisdiction"""
        message = "The library has been closed for weeks"  # No city mentioned
        user_id = "test_user_004"
        user_context = {'jurisdiction_id': 'city-hayward'}

        response = handler.handle_user_message(message, user_id, user_context)

        assert response['type'] in ['matched', 'no_match']
        assert 'complaint_id' in response
        print(f"\nWith context - type: {response['type']}")

    def test_convenience_function(self):
        """Test the convenience handle_message function"""
        message = "Bike lane is blocked by parked cars in Oakland"
        user_id = "test_user_005"

        response = handle_message(message, user_id)

        assert 'type' in response
        assert 'message' in response
        print(f"\nConvenience function response: {response['type']}")

    def test_match_response_format(self, handler):
        """Validate match response structure"""
        message = "Need affordable housing in Berkeley"
        user_id = "test_user_006"
        user_context = {'jurisdiction_id': 'city-berkeley'}

        response = handler.handle_user_message(message, user_id, user_context)

        if response['type'] == 'matched':
            # Validate response structure
            assert 'complaint_id' in response
            assert 'matches' in response
            assert isinstance(response['matches'], list)

            if response['matches']:
                match = response['matches'][0]
                assert 'title' in match
                assert 'when' in match
                assert 'score' in match
                assert 'why_relevant' in match
                print(f"\nMatch structure validated")
                print(f"Top match: {match['title'][:50]}...")
                print(f"Score: {match['score']}")

    def test_no_match_response_format(self, handler):
        """Validate no-match response structure (fallback)"""
        # Use an uncommon issue type to reduce match likelihood
        message = "The zoning regulations are confusing in Richmond"
        user_id = "test_user_007"
        user_context = {'jurisdiction_id': 'city-richmond'}

        response = handler.handle_user_message(message, user_id, user_context)

        # Should get some response
        assert response['type'] in ['matched', 'no_match']
        assert 'message' in response

        if response['type'] == 'no_match':
            # Validate fallback structure
            assert 'complaint_id' in response
            assert 'similar_count' in response
            assert 'actions' in response
            print(f"\nNo-match structure validated")
            print(f"Similar complaints: {response['similar_count']}")


class TestEndToEndWorkflow:
    """Test complete workflow scenarios"""

    def test_multiple_users_same_issue(self, handler):
        """Test community formation scenario"""
        issue = "Excessive noise from construction in San Rafael"
        user_ids = ['user_a', 'user_b', 'user_c']

        responses = []
        for user_id in user_ids:
            response = handler.handle_user_message(issue, user_id)
            responses.append(response)
            print(f"\nUser {user_id}: {response['type']}")

        # All should create complaints
        assert all(r['type'] in ['matched', 'no_match'] for r in responses)
        assert all('complaint_id' in r for r in responses)

        # Complaint IDs should be different
        complaint_ids = [r['complaint_id'] for r in responses]
        assert len(set(complaint_ids)) == len(complaint_ids), "Duplicate complaint IDs"

    def test_workflow_with_storage_persistence(self):
        """Test that complaints persist in storage"""
        handler = ComplaintHandler()
        message = "Park is full of trash in Berkeley"
        user_id = "test_user_persist"
        user_context = {'jurisdiction_id': 'city-berkeley'}

        response = handler.handle_user_message(message, user_id, user_context)

        if 'complaint_id' in response:
            complaint_id = response['complaint_id']

            # Verify it's in storage
            complaint = handler.storage.get_complaint(complaint_id)
            assert complaint is not None
            assert complaint['user_id'] == user_id
            assert complaint['jurisdiction_id'] == 'city-berkeley'
            assert complaint['issue_type'] in ['environment', 'community']
            print(f"\nComplaint persisted: {complaint['id']}")
            print(f"Issue type: {complaint['issue_type']}")


if __name__ == '__main__':
    # Run with pytest
    pytest.main([__file__, '-v', '-s'])
