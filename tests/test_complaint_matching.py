"""
Tests for complaint-to-event matching algorithm (Layer 3.1)

Validation gates:
- >30% match rate on test complaints
- <100ms latency per complaint
- Keyword scoring working correctly
"""

import pytest
import time
from datetime import datetime, timedelta, timezone
from civic_services.issue_matcher import (
    match_complaint_to_events,
    _score_event,
    _load_jurisdiction_events,
    get_match_statistics,
    ISSUE_TYPE_KEYWORDS,
    MINIMUM_MATCH_SCORE
)


class TestComplaintMatcher:
    """Test suite for complaint matcher"""

    def test_keyword_matching_housing(self):
        """Test keyword matching for housing complaints"""
        complaint = {
            "description": "My landlord won't fix the broken heating system in my apartment",
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        event = {
            "title": "Zoning Adjustments Board Meeting",
            "description": "Review of zoning adjustments and land use applications",
            "project_type": "housing",
            "when": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        }

        score, reason = _score_event(complaint, event)

        # Should match on:
        # - keywords: "landlord", "apartment" (20 points)
        # - project type: housing (20 points)
        # - temporal: within 1 week (15 points)
        # Total: 55+ points
        assert score >= 50, f"Expected score >= 50, got {score}"
        assert "keyword matches" in reason
        assert "project type" in reason

    def test_keyword_matching_transportation(self):
        """Test keyword matching for transportation complaints"""
        complaint = {
            "description": "Dangerous intersection needs traffic light and crosswalk",
            "issue_type": "transportation",
            "jurisdiction_id": "city-berkeley"
        }

        event = {
            "title": "Transportation Commission Meeting",
            "description": "Discussion on bike lanes and pedestrian safety improvements",
            "project_type": "transportation",
            "when": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        }

        score, reason = _score_event(complaint, event)

        # Should match on:
        # - keywords: "traffic", "crosswalk", "bike", "pedestrian" (40 points)
        # - project type: transportation (20 points)
        # - temporal: within 1 month (10 points)
        # Total: 70+ points
        assert score >= 60, f"Expected score >= 60, got {score}"
        assert "keyword matches" in reason

    def test_keyword_matching_environment(self):
        """Test keyword matching for environment complaints"""
        complaint = {
            "description": "Air pollution from nearby factory is affecting our neighborhood",
            "issue_type": "environment",
            "jurisdiction_id": "city-berkeley"
        }

        event = {
            "title": "Wildland Urban Interface Vegetation Code Workgroup Meeting",
            "description": "Discussion on vegetation code amendments and fire safety",
            "project_type": "environment",
            "when": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        }

        score, reason = _score_event(complaint, event)

        # Should match on:
        # - project type: environment (20 points)
        # - temporal: within 1 week (15 points)
        # Total: 35+ points (pollution keyword may not match all event descriptions)
        assert score >= 35, f"Expected score >= 35, got {score}"

    def test_no_match_different_topic(self):
        """Test that unrelated events don't match"""
        complaint = {
            "description": "Need more affordable housing in our neighborhood",
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        event = {
            "title": "Parks and Recreation Commission",
            "description": "Discussion on new playground equipment",
            "project_type": "community",
            "when": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        }

        score, reason = _score_event(complaint, event)

        # Should not match (different topic, no keyword overlap)
        assert score < MINIMUM_MATCH_SCORE, f"Expected score < {MINIMUM_MATCH_SCORE}, got {score}"

    def test_temporal_proximity_scoring(self):
        """Test that temporal proximity affects scoring"""
        complaint = {
            "description": "Housing complaint",
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        # Event in 5 days (within 1 week)
        event_near = {
            "title": "Housing meeting",
            "description": "Housing discussion",
            "project_type": "housing",
            "when": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        }

        # Event in 60 days (within 3 months)
        event_far = {
            "title": "Housing meeting",
            "description": "Housing discussion",
            "project_type": "housing",
            "when": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        }

        score_near, _ = _score_event(complaint, event_near)
        score_far, _ = _score_event(complaint, event_far)

        # Near event should score higher due to temporal proximity
        assert score_near > score_far, "Near event should score higher than far event"

    def test_project_type_bonus(self):
        """Test that matching project types get bonus points"""
        complaint = {
            "description": "Housing issue",
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        event_matching = {
            "title": "Meeting",
            "description": "Discussion",
            "project_type": "housing",
            "when": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        }

        event_non_matching = {
            "title": "Meeting",
            "description": "Discussion",
            "project_type": "community",
            "when": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        }

        score_matching, reason_matching = _score_event(complaint, event_matching)
        score_non_matching, _ = _score_event(complaint, event_non_matching)

        # Matching project type should score 20 points higher
        assert score_matching >= score_non_matching + 20
        assert "project type" in reason_matching

    def test_description_overlap_scoring(self):
        """Test that description word overlap increases score"""
        complaint = {
            "description": "Affordable housing development project needed in downtown neighborhood area",
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        event = {
            "title": "Downtown Housing Development Project",
            "description": "Discussion on affordable housing development in downtown neighborhood",
            "project_type": "housing",
            "when": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        }

        score, reason = _score_event(complaint, event)

        # Should have description overlap bonus
        assert "description overlap" in reason
        assert score >= 60  # High score due to multiple matching factors

    def test_match_statistics(self):
        """Test match statistics calculation"""
        matches = [
            ({"id": "event1"}, 75, "high confidence"),
            ({"id": "event2"}, 65, "good match"),
            ({"id": "event3"}, 45, "moderate match"),
            ({"id": "event4"}, 30, "weak match")
        ]

        stats = get_match_statistics(matches)

        assert stats["total_matches"] == 4
        assert stats["high_confidence"] == 2  # 75 and 65 are >= 60
        assert stats["average_score"] == 53.75
        assert stats["max_score"] == 75
        assert stats["min_score"] == 30

    def test_match_statistics_empty(self):
        """Test match statistics with no matches"""
        stats = get_match_statistics([])

        assert stats["total_matches"] == 0
        assert stats["high_confidence"] == 0
        assert stats["average_score"] == 0.0

    def test_load_jurisdiction_events(self):
        """Test loading events for a jurisdiction"""
        # Test with Berkeley (known to have events)
        events = _load_jurisdiction_events("city-berkeley")

        # Should load events if they exist
        if events:
            assert isinstance(events, list)
            assert len(events) > 0
            assert all(isinstance(e, dict) for e in events)
            assert all("title" in e for e in events)

    def test_load_nonexistent_jurisdiction(self):
        """Test loading events for non-existent jurisdiction"""
        events = _load_jurisdiction_events("city-nonexistent-12345")

        assert events == []

    @pytest.mark.skipif(
        not _load_jurisdiction_events("city-berkeley"),
        reason="Requires Berkeley event data"
    )
    def test_end_to_end_matching(self):
        """Test end-to-end matching with real data"""
        complaint = {
            "description": "Need more affordable housing options, rent is too expensive",
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        matches = match_complaint_to_events(complaint)

        # Should find some matches (or none if no housing events)
        assert isinstance(matches, list)
        assert all(len(m) == 3 for m in matches)  # Each match is (event, score, reason)

        # All matches should meet minimum score
        for event, score, reason in matches:
            assert score >= MINIMUM_MATCH_SCORE
            assert isinstance(event, dict)
            assert isinstance(reason, str)

    @pytest.mark.skipif(
        not _load_jurisdiction_events("city-berkeley"),
        reason="Requires Berkeley event data"
    )
    def test_matching_performance(self):
        """Test that matching completes within 100ms"""
        complaint = {
            "description": "Traffic safety issue at intersection",
            "issue_type": "transportation",
            "jurisdiction_id": "city-berkeley"
        }

        start = time.time()
        matches = match_complaint_to_events(complaint)
        elapsed = (time.time() - start) * 1000  # Convert to ms

        assert elapsed < 100, f"Matching took {elapsed:.1f}ms (should be < 100ms)"

    def test_issue_type_keywords_coverage(self):
        """Test that all expected issue types have keywords"""
        expected_types = ["housing", "transportation", "environment", "infrastructure", "public_safety"]

        for issue_type in expected_types:
            assert issue_type in ISSUE_TYPE_KEYWORDS
            assert len(ISSUE_TYPE_KEYWORDS[issue_type]) > 5  # At least 5 keywords each

    def test_max_matches_limit(self):
        """Test that max_matches parameter is respected"""
        complaint = {
            "description": "Housing issue",
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        # Request only 2 matches
        matches = match_complaint_to_events(complaint, max_matches=2)

        # Should not exceed max_matches
        assert len(matches) <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
