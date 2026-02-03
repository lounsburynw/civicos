"""
Tests for Context-Aware Agent (Edge Intelligence)

Session 536: Initial test suite

Tests cover:
1. User context parsing
2. Filtering instruction parsing
3. Filtering logic application
4. Location-based relevance
5. Reasoning transparency
6. System prompt injection
7. Full context agent integration
"""

import pytest
from civicos_services.chat.context_agent import (
    ContextAgent,
    UserContextForRequest,
    UserNeighborhood,
    FilteringConstraints,
    parse_filtering_instructions,
    apply_filtering_logic,
    add_location_context,
    generate_personalization_reasoning,
    calculate_distance_km,
)


# ============================================================================
# User Context Parsing Tests
# ============================================================================

class TestUserContextParsing:
    """Tests for UserContextForRequest parsing."""

    def test_minimal_context(self):
        """Minimal context with just jurisdiction."""
        ctx = UserContextForRequest(jurisdiction="city-san-rafael")
        assert ctx.jurisdiction == "city-san-rafael"
        assert ctx.interests == []
        assert ctx.filtering_instructions == ""
        assert ctx.location is None

    def test_full_context(self):
        """Full context with all fields."""
        ctx = UserContextForRequest(
            jurisdiction="city-san-rafael",
            location=UserNeighborhood(
                neighborhood="Terra Linda",
                lat=37.97,
                lng=-122.53
            ),
            interests=["housing", "transportation"],
            filtering_instructions="aggressive on housing, ignore parking",
            notification_email="user@example.com",
            voice_history=["event1", "event2"],
            commitment_history=["commit1"]
        )
        assert ctx.jurisdiction == "city-san-rafael"
        assert ctx.location.neighborhood == "Terra Linda"
        assert ctx.location.lat == 37.97
        assert "housing" in ctx.interests
        assert "transportation" in ctx.interests
        assert ctx.filtering_instructions == "aggressive on housing, ignore parking"
        assert len(ctx.voice_history) == 2
        assert len(ctx.commitment_history) == 1


class TestUserNeighborhood:
    """Tests for UserNeighborhood model."""

    def test_neighborhood_with_coords(self):
        """Neighborhood with full coordinates."""
        loc = UserNeighborhood(neighborhood="Terra Linda", lat=37.97, lng=-122.53)
        assert loc.neighborhood == "Terra Linda"
        assert loc.lat == 37.97
        assert loc.lng == -122.53

    def test_neighborhood_without_coords(self):
        """Neighborhood without coordinates."""
        loc = UserNeighborhood(neighborhood="Downtown")
        assert loc.neighborhood == "Downtown"
        assert loc.lat is None
        assert loc.lng is None


# ============================================================================
# Filtering Instruction Parsing Tests
# ============================================================================

class TestFilteringInstructionParsing:
    """Tests for parse_filtering_instructions()."""

    def test_empty_instructions(self):
        """Empty instructions returns empty constraints."""
        constraints = parse_filtering_instructions("")
        assert constraints.boost_topics == []
        assert constraints.ignore_topics == []

    def test_aggressive_on_topic(self):
        """'aggressive on X' boosts topic X."""
        constraints = parse_filtering_instructions("aggressive on housing")
        assert "housing" in constraints.boost_topics
        assert constraints.ignore_topics == []

    def test_focus_on_topic(self):
        """'focus on X' boosts topic X."""
        constraints = parse_filtering_instructions("focus on transportation")
        assert "transportation" in constraints.boost_topics

    def test_prioritize_topic(self):
        """'prioritize X' boosts topic X."""
        constraints = parse_filtering_instructions("prioritize infrastructure")
        assert "infrastructure" in constraints.boost_topics

    def test_ignore_topic(self):
        """'ignore X' filters out topic X."""
        constraints = parse_filtering_instructions("ignore parking")
        assert "parking" in constraints.ignore_topics
        assert constraints.boost_topics == []

    def test_skip_topic(self):
        """'skip X' filters out topic X."""
        constraints = parse_filtering_instructions("skip zoning")
        assert "zoning" in constraints.ignore_topics

    def test_combined_instructions(self):
        """Combined boost and ignore in same instruction."""
        constraints = parse_filtering_instructions(
            "aggressive on housing, ignore parking, focus on infrastructure"
        )
        assert "housing" in constraints.boost_topics
        assert "infrastructure" in constraints.boost_topics
        assert "parking" in constraints.ignore_topics

    def test_case_insensitive(self):
        """Instructions are case-insensitive."""
        constraints = parse_filtering_instructions("AGGRESSIVE ON HOUSING, IGNORE PARKING")
        assert "housing" in constraints.boost_topics
        assert "parking" in constraints.ignore_topics


# ============================================================================
# Filtering Logic Tests
# ============================================================================

class TestFilteringLogic:
    """Tests for apply_filtering_logic()."""

    @pytest.fixture
    def sample_results(self):
        """Sample results for filtering tests."""
        return [
            {"title": "Housing Meeting", "topics": ["housing", "development"]},
            {"title": "Parking Reform", "topics": ["parking", "transportation"]},
            {"title": "Budget Review", "topics": ["budget", "finance"]},
            {"title": "Transit Study", "topics": ["transportation", "infrastructure"]},
        ]

    def test_no_constraints(self, sample_results):
        """No constraints returns results unchanged."""
        constraints = FilteringConstraints()
        filtered = apply_filtering_logic(constraints, sample_results)
        assert len(filtered) == 4

    def test_boost_moves_to_front(self, sample_results):
        """Boosted topics move to front of results."""
        constraints = FilteringConstraints(boost_topics=["transportation"])
        filtered = apply_filtering_logic(constraints, sample_results)
        # Transportation results should be first
        assert filtered[0]["title"] == "Parking Reform"
        assert filtered[1]["title"] == "Transit Study"

    def test_ignore_removes_results(self, sample_results):
        """Ignored topics are removed from results."""
        constraints = FilteringConstraints(ignore_topics=["parking"])
        filtered = apply_filtering_logic(constraints, sample_results)
        assert len(filtered) == 3
        assert not any("Parking" in r["title"] for r in filtered)

    def test_boost_and_ignore_combined(self, sample_results):
        """Boost and ignore work together."""
        constraints = FilteringConstraints(
            boost_topics=["housing"],
            ignore_topics=["budget"]
        )
        filtered = apply_filtering_logic(constraints, sample_results)
        # Housing boosted to front, budget removed
        assert filtered[0]["title"] == "Housing Meeting"
        assert len(filtered) == 3
        assert not any("Budget" in r["title"] for r in filtered)

    def test_string_topics_handled(self):
        """Results with string topics (not list) are handled."""
        results = [
            {"title": "Meeting 1", "topics": "housing"},
            {"title": "Meeting 2", "topics": "transportation"},
        ]
        constraints = FilteringConstraints(boost_topics=["housing"])
        filtered = apply_filtering_logic(constraints, results)
        assert filtered[0]["title"] == "Meeting 1"


# ============================================================================
# Location Context Tests
# ============================================================================

class TestLocationContext:
    """Tests for add_location_context()."""

    @pytest.fixture
    def user_location(self):
        """User's location for tests."""
        return UserNeighborhood(
            neighborhood="Terra Linda",
            lat=37.97,
            lng=-122.53
        )

    @pytest.fixture
    def results_with_locations(self):
        """Results with location data."""
        return [
            {"title": "Issue 1", "lat": 37.97, "lng": -122.53},  # Same location
            {"title": "Issue 2", "lat": 37.98, "lng": -122.54},  # ~1km away
            {"title": "Issue 3", "lat": 38.50, "lng": -122.00},  # Far away
            {"title": "Issue 4"},  # No location
        ]

    def test_no_user_location(self, results_with_locations):
        """No user location returns results unchanged."""
        annotated = add_location_context(None, results_with_locations)
        assert annotated == results_with_locations

    def test_annotates_nearby_items(self, user_location, results_with_locations):
        """Items near user get affects_your_neighborhood flag."""
        annotated = add_location_context(user_location, results_with_locations)

        # Issue 1 is at same location
        assert annotated[0].get("affects_your_neighborhood") is True
        assert annotated[0].get("distance_km") == 0.0

        # Issue 2 is nearby
        assert annotated[1].get("affects_your_neighborhood") is True
        assert annotated[1].get("distance_km") < 3.0

        # Issue 3 is far away
        assert annotated[2].get("affects_your_neighborhood") is False

    def test_neighborhood_name_matching(self, user_location):
        """Items mentioning neighborhood name get flagged."""
        results = [
            {"title": "Issue in Terra Linda area", "description": "Problem near Terra Linda"},
            {"title": "Issue elsewhere", "description": "Downtown problem"},
        ]
        annotated = add_location_context(user_location, results)
        assert annotated[0].get("affects_your_neighborhood") is True

    def test_no_coords_returns_unchanged(self):
        """Location without coords returns results unchanged (no distance calc possible)."""
        location = UserNeighborhood(neighborhood="Downtown")
        results = [
            {"title": "Downtown issue", "description": "Downtown area problem"},
        ]
        annotated = add_location_context(location, results)
        # Without coordinates, we can't calculate distance, so results are unchanged
        # Neighborhood name matching requires coordinates to be present
        assert annotated == results


class TestDistanceCalculation:
    """Tests for calculate_distance_km()."""

    def test_same_point(self):
        """Same point has zero distance."""
        distance = calculate_distance_km(37.97, -122.53, 37.97, -122.53)
        assert distance == 0.0

    def test_known_distance(self):
        """Verify against known distance (San Rafael to San Francisco ~20km)."""
        # San Rafael
        lat1, lng1 = 37.97, -122.53
        # San Francisco
        lat2, lng2 = 37.77, -122.42
        distance = calculate_distance_km(lat1, lng1, lat2, lng2)
        # Should be approximately 20-25 km
        assert 20 < distance < 30


# ============================================================================
# Reasoning Transparency Tests
# ============================================================================

class TestReasoningTransparency:
    """Tests for generate_personalization_reasoning()."""

    def test_no_context_no_reasoning(self):
        """No context returns empty reasoning."""
        ctx = UserContextForRequest(jurisdiction="city-san-rafael")
        reasoning = generate_personalization_reasoning(ctx, "search_events")
        assert reasoning == ""

    def test_interest_matching(self):
        """Matched interests included in reasoning."""
        ctx = UserContextForRequest(
            jurisdiction="city-san-rafael",
            interests=["housing", "transportation"]
        )
        reasoning = generate_personalization_reasoning(
            ctx, "search_events",
            parameters={"query": "housing developments"}
        )
        assert "housing" in reasoning.lower()
        assert "interest" in reasoning.lower()

    def test_location_reasoning(self):
        """Location included in reasoning."""
        ctx = UserContextForRequest(
            jurisdiction="city-san-rafael",
            location=UserNeighborhood(neighborhood="Terra Linda"),
            interests=[]
        )
        reasoning = generate_personalization_reasoning(ctx, "search_events")
        assert "Terra Linda" in reasoning

    def test_filtering_instructions_reasoning(self):
        """Filtering instructions included in reasoning."""
        ctx = UserContextForRequest(
            jurisdiction="city-san-rafael",
            filtering_instructions="aggressive on housing, ignore parking"
        )
        reasoning = generate_personalization_reasoning(ctx, "search_events")
        assert "housing" in reasoning.lower()
        assert "parking" in reasoning.lower()

    def test_combined_reasoning(self):
        """Multiple context elements combined in reasoning."""
        ctx = UserContextForRequest(
            jurisdiction="city-san-rafael",
            location=UserNeighborhood(neighborhood="Terra Linda"),
            interests=["housing"],
            filtering_instructions="focus on development"
        )
        reasoning = generate_personalization_reasoning(
            ctx, "search_events",
            parameters={"query": "housing meetings"}
        )
        # Should mention multiple factors
        assert len(reasoning) > 50  # Non-trivial reasoning


# ============================================================================
# Context Agent Class Tests
# ============================================================================

class TestContextAgent:
    """Tests for ContextAgent class."""

    @pytest.fixture
    def sample_context(self):
        """Sample user context for tests."""
        return {
            "jurisdiction": "city-san-rafael",
            "location": {
                "neighborhood": "Terra Linda",
                "lat": 37.97,
                "lng": -122.53
            },
            "interests": ["housing", "transportation"],
            "filtering_instructions": "aggressive on housing, ignore parking"
        }

    def test_init_with_valid_context(self, sample_context):
        """Agent initializes correctly with valid context."""
        agent = ContextAgent(sample_context)
        assert agent.has_context is True
        assert agent.context.jurisdiction == "city-san-rafael"
        assert "housing" in agent.constraints.boost_topics
        assert "parking" in agent.constraints.ignore_topics

    def test_init_with_none(self):
        """Agent handles None context gracefully."""
        agent = ContextAgent(None)
        assert agent.has_context is False
        assert agent.context is None

    def test_init_with_invalid_context(self):
        """Agent handles invalid context gracefully."""
        agent = ContextAgent({"invalid": "data"})
        assert agent.has_context is False

    def test_system_prompt_injection(self, sample_context):
        """Agent generates system prompt injection."""
        agent = ContextAgent(sample_context)
        prompt = agent.get_system_prompt_injection()

        assert "Terra Linda" in prompt
        assert "housing" in prompt
        assert "transportation" in prompt
        assert "BOOST" in prompt
        assert "FILTER OUT" in prompt

    def test_system_prompt_empty_when_no_context(self):
        """No context returns empty prompt injection."""
        agent = ContextAgent(None)
        prompt = agent.get_system_prompt_injection()
        assert prompt == ""

    def test_filter_results(self, sample_context):
        """Agent filters results based on constraints."""
        agent = ContextAgent(sample_context)
        results = [
            {"title": "Housing Meeting", "topics": ["housing"]},
            {"title": "Parking Rules", "topics": ["parking"]},
            {"title": "Budget", "topics": ["finance"]},
        ]
        filtered = agent.filter_results(results)

        # Housing boosted to front
        assert filtered[0]["title"] == "Housing Meeting"
        # Parking removed
        assert len(filtered) == 2
        assert not any("Parking" in r["title"] for r in filtered)

    def test_annotate_with_location(self, sample_context):
        """Agent adds location annotations."""
        agent = ContextAgent(sample_context)
        results = [
            {"title": "Issue 1", "lat": 37.97, "lng": -122.53},
        ]
        annotated = agent.annotate_with_location(results)
        assert annotated[0].get("affects_your_neighborhood") is True

    def test_get_reasoning(self, sample_context):
        """Agent generates personalization reasoning."""
        agent = ContextAgent(sample_context)
        reasoning = agent.get_reasoning(
            action="search_events",
            parameters={"query": "housing meetings"}
        )
        assert len(reasoning) > 0
        assert "housing" in reasoning.lower()

    def test_apply_to_response(self, sample_context):
        """Agent applies full context to response."""
        agent = ContextAgent(sample_context)
        response = {
            "action": "search_events",
            "parameters": {
                "query": "housing meetings",
                "results": [
                    {"title": "Housing Meeting", "topics": ["housing"]},
                    {"title": "Parking Rules", "topics": ["parking"]},
                ]
            },
            "mode": "navigation"
        }
        enhanced = agent.apply_to_response(response)

        # Should have personalization reasoning
        assert "personalization_reasoning" in enhanced
        # Should have filtered results (parking removed)
        assert len(enhanced["parameters"]["results"]) == 1
        assert enhanced["parameters"]["results"][0]["title"] == "Housing Meeting"


# ============================================================================
# Integration Tests
# ============================================================================

class TestContextAgentIntegration:
    """Integration tests for context agent with chat router patterns."""

    def test_full_flow_with_context(self):
        """Test full flow: context → agent → filtered response."""
        # Simulate user context from frontend
        user_context = {
            "jurisdiction": "city-san-rafael",
            "location": {
                "neighborhood": "Terra Linda",
                "lat": 37.97,
                "lng": -122.53
            },
            "interests": ["housing", "public-safety"],
            "filtering_instructions": "focus on housing, skip parking issues"
        }

        # Create agent
        agent = ContextAgent(user_context)
        assert agent.has_context

        # Simulate chat router response
        router_response = {
            "action": "search_events",
            "parameters": {
                "query": "upcoming meetings",
                "results": [
                    {
                        "title": "Housing Commission",
                        "topics": ["housing", "development"],
                        "lat": 37.97,
                        "lng": -122.53
                    },
                    {
                        "title": "Parking Authority",
                        "topics": ["parking", "transportation"],
                        "lat": 37.95,
                        "lng": -122.51
                    },
                    {
                        "title": "City Council",
                        "topics": ["governance", "budget"],
                        "lat": 37.97,
                        "lng": -122.53
                    }
                ]
            },
            "mode": "navigation"
        }

        # Apply context
        enhanced = agent.apply_to_response(router_response)

        # Verify filtering
        results = enhanced["parameters"]["results"]
        assert len(results) == 2  # Parking filtered out
        assert results[0]["title"] == "Housing Commission"  # Housing boosted

        # Verify location annotations
        assert results[0].get("affects_your_neighborhood") is True

        # Verify reasoning
        assert "personalization_reasoning" in enhanced
        assert len(enhanced["personalization_reasoning"]) > 0

    def test_context_from_dict_matches_frontend(self):
        """Ensure Python models match TypeScript UserContextForRequest."""
        # This is the exact structure sent from frontend
        frontend_context = {
            "jurisdiction": "city-san-rafael",
            "location": {
                "neighborhood": "Terra Linda",
                "lat": 37.97,
                "lng": -122.53
            },
            "interests": ["housing", "transportation"],
            "filtering_instructions": "aggressive on housing, ignore parking",
            "notification_email": "user@example.com"
        }

        # Should parse without error
        ctx = UserContextForRequest(**frontend_context)
        assert ctx.jurisdiction == "city-san-rafael"
        assert ctx.location.neighborhood == "Terra Linda"
        assert "housing" in ctx.interests
        assert ctx.notification_email == "user@example.com"

    def test_voice_history_reference(self):
        """Context includes voice history references (Nostr event IDs)."""
        ctx = UserContextForRequest(
            jurisdiction="city-san-rafael",
            voice_history=["note1abc123", "note1def456"],
            commitment_history=["note1commit789"]
        )
        assert len(ctx.voice_history) == 2
        assert len(ctx.commitment_history) == 1

        # Agent should acknowledge history in prompt
        agent = ContextAgent(ctx.model_dump())
        prompt = agent.get_system_prompt_injection()
        assert "previous voice contributions" in prompt.lower() or "2 previous" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
