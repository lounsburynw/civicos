"""
Tests for complaint fallback strategy (Layer 3.2)

Validation gates:
- Helpful messages generated for all cases
- Civic actions tracked correctly
- Similar complaint discovery working
"""

import pytest
import uuid
from civic_app.issue_fallback import (
    handle_no_match,
    _find_similar_complaints,
    _generate_no_match_message,
    _generate_fallback_actions
)
from civic_app.issue_storage import IssueStorage as ComplaintStorage


class TestComplaintFallback:
    """Test suite for complaint fallback strategy"""

    @pytest.fixture
    def storage(self):
        """Provide storage instance"""
        return ComplaintStorage()

    @pytest.fixture
    def cleanup_test_data(self, storage):
        """Clean up test data after tests"""
        yield
        # Cleanup test complaints
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            conn.execute("DELETE FROM complaints WHERE user_id LIKE 'test-user-%'")
            conn.commit()

    def test_handle_no_match_no_similar(self, storage, cleanup_test_data):
        """Test handling complaint with no similar complaints"""
        # Create a unique complaint
        complaint_id = storage.create_complaint(
            user_id=f"test-user-{uuid.uuid4()}",
            description="Very specific unique problem that nobody else has",
            jurisdiction_id="city-berkeley",
            issue_type="infrastructure"
        )

        complaint = storage.get_complaint(complaint_id)
        response = handle_no_match(complaint)

        # Should return helpful response
        assert "message" in response
        assert "actions" in response
        assert "similar_count" in response
        # Note: similar_count may be > 0 due to previous test data
        assert isinstance(response["similar_count"], int)
        assert "tracking your concern" in response["message"].lower() or "we're tracking" in response["message"].lower()

        # Should have at least one action
        assert len(response["actions"]) >= 1
        assert response["actions"][0]["action_label"] == "Track This Issue"

    def test_handle_no_match_few_similar(self, storage, cleanup_test_data):
        """Test handling complaint with 1-2 similar complaints"""
        # Create 2 similar complaints
        test_user = f"test-user-{uuid.uuid4()}"
        for i in range(2):
            storage.create_complaint(
                user_id=f"test-user-other-{i}",
                description="Housing affordability issue",
                jurisdiction_id="city-berkeley",
                issue_type="housing"
            )

        # Create the test complaint
        complaint_id = storage.create_complaint(
            user_id=test_user,
            description="Need more affordable housing options",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        complaint = storage.get_complaint(complaint_id)
        response = handle_no_match(complaint)

        # Should mention other neighbors
        assert response["similar_count"] >= 1
        assert "other neighbor" in response["message"].lower()
        assert response["community_formation_potential"] == "low"

    def test_handle_no_match_many_similar(self, storage, cleanup_test_data):
        """Test handling complaint with 3+ similar complaints"""
        # Create 4 similar complaints
        test_user = f"test-user-{uuid.uuid4()}"
        for i in range(4):
            storage.create_complaint(
                user_id=f"test-user-other-{i}-{uuid.uuid4()}",
                description="Transportation safety concern",
                jurisdiction_id="city-berkeley",
                issue_type="transportation"
            )

        # Create the test complaint
        complaint_id = storage.create_complaint(
            user_id=test_user,
            description="Dangerous intersection needs improvement",
            jurisdiction_id="city-berkeley",
            issue_type="transportation"
        )

        complaint = storage.get_complaint(complaint_id)
        response = handle_no_match(complaint)

        # Should emphasize community formation
        assert response["similar_count"] >= 3
        assert "neighbors" in response["message"].lower()
        assert "connecting" in response["message"].lower() or "organize" in response["message"].lower()
        assert response["community_formation_potential"] == "high"

        # Should have action to view similar complaints
        action_labels = [a["action_label"] for a in response["actions"]]
        assert any("Similar" in label for label in action_labels)

    def test_find_similar_complaints(self, storage, cleanup_test_data):
        """Test finding similar complaints"""
        # Create several housing complaints
        test_user = f"test-user-{uuid.uuid4()}"
        for i in range(3):
            storage.create_complaint(
                user_id=f"test-user-other-{i}-{uuid.uuid4()}",
                description=f"Housing issue {i}",
                jurisdiction_id="city-berkeley",
                issue_type="housing"
            )

        # Create the test complaint
        complaint_id = storage.create_complaint(
            user_id=test_user,
            description="Another housing issue",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        complaint = storage.get_complaint(complaint_id)
        similar = _find_similar_complaints(complaint, storage)

        # Should find the other housing complaints
        assert len(similar) >= 3

        # Should not include the current complaint
        assert all(c["id"] != complaint_id for c in similar)

        # All should be same jurisdiction and issue type
        assert all(c["jurisdiction_id"] == "city-berkeley" for c in similar)
        assert all(c["issue_type"] == "housing" for c in similar)

    def test_generate_no_match_message_no_similar(self):
        """Test message generation with no similar complaints"""
        complaint = {
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        message = _generate_no_match_message(complaint, similar_count=0)

        assert "housing" in message.lower()
        assert "berkeley" in message.lower()
        assert "tracking your concern" in message.lower()
        assert "notify you" in message.lower()

    def test_generate_no_match_message_one_similar(self):
        """Test message generation with 1 similar complaint"""
        complaint = {
            "issue_type": "transportation",
            "jurisdiction_id": "city-oakland"
        }

        message = _generate_no_match_message(complaint, similar_count=1)

        assert "transportation" in message.lower()
        assert "oakland" in message.lower()
        assert "1 other neighbor" in message.lower()

    def test_generate_no_match_message_many_similar(self):
        """Test message generation with many similar complaints"""
        complaint = {
            "issue_type": "environment",
            "jurisdiction_id": "city-san-rafael"
        }

        message = _generate_no_match_message(complaint, similar_count=5)

        assert "environment" in message.lower()
        assert "san rafael" in message.lower()
        assert "5 neighbors" in message.lower()
        assert "connecting" in message.lower() or "organize" in message.lower()

    def test_generate_fallback_actions_no_similar(self):
        """Test action generation with no similar complaints"""
        complaint = {
            "id": "test-complaint-1",
            "issue_type": "housing"
        }

        actions = _generate_fallback_actions(complaint, similar_complaints=[])

        # Should have at least track action
        assert len(actions) >= 1
        assert actions[0]["action_type"] == "button"
        assert "Track" in actions[0]["action_label"]
        assert actions[0]["mcp_tool"] == "track_issue"

    def test_generate_fallback_actions_many_similar(self):
        """Test action generation with many similar complaints"""
        complaint = {
            "id": "test-complaint-1",
            "issue_type": "housing"
        }

        similar_complaints = [{"id": f"similar-{i}"} for i in range(5)]
        actions = _generate_fallback_actions(complaint, similar_complaints)

        # Should have track action and view similar action
        assert len(actions) >= 2

        action_labels = [a["action_label"] for a in actions]
        assert any("Track" in label for label in action_labels)
        assert any("Similar" in label for label in action_labels)

        # View similar action should show count
        view_similar_action = next(a for a in actions if "Similar" in a["action_label"])
        assert "5" in view_similar_action["action_label"]

    def test_fallback_response_structure(self, storage, cleanup_test_data):
        """Test that fallback response has correct structure"""
        complaint_id = storage.create_complaint(
            user_id=f"test-user-{uuid.uuid4()}",
            description="Test complaint",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        complaint = storage.get_complaint(complaint_id)
        response = handle_no_match(complaint)

        # Check response structure
        assert isinstance(response, dict)
        assert "message" in response
        assert "actions" in response
        assert "similar_count" in response
        assert "community_formation_potential" in response

        # Check types
        assert isinstance(response["message"], str)
        assert isinstance(response["actions"], list)
        assert isinstance(response["similar_count"], int)
        assert response["community_formation_potential"] in ["high", "low"]

        # Check actions structure
        for action in response["actions"]:
            assert "action_type" in action
            assert "action_label" in action
            assert "action_target" in action
            assert "mcp_tool" in action

    def test_no_match_with_missing_fields(self):
        """Test handling complaint with missing optional fields"""
        complaint = {
            "id": "test-complaint-1",
            "description": "Test issue",
            "jurisdiction_id": "city-berkeley",
            "issue_type": "housing",
            "user_id": "test-user",
            "status": "open",
            "created_at": "2025-10-12 00:00:00"
        }

        response = handle_no_match(complaint)

        # Should still work without errors
        assert "message" in response
        assert "actions" in response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
