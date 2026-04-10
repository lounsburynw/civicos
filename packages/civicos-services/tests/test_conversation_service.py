"""
Tests for conversation_service.py — MCP-powered conversational intelligence
for Civic OS. Tests the ConversationService class methods for topic extraction,
goal detection, stance inference, key point extraction, user activity tracking,
conversation context management, and response generation.

Most methods are pure logic (keyword matching, string processing) — tested with
real inputs and specific expected outputs. I/O (filesystem loading) is mocked at
the boundary.

To run:
    pytest packages/civicos-services/tests/test_conversation_service.py -q --override-ini="addopts="
"""

import pytest
from unittest.mock import patch

from civicos_services.utils.conversation_service import ConversationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(opportunities=None):
    """Create a ConversationService with no filesystem I/O and optional test opportunities."""
    with patch.object(ConversationService, "_load_civic_opportunities"):
        svc = ConversationService(enable_mcp=False)
    svc.civic_opportunities = opportunities or []
    return svc


def _make_user_profile(experience="new", interactions=0, visits=1, city="San Rafael"):
    """Create a minimal user profile dict matching the schema expected by the service."""
    return {
        "experience_level": experience,
        "civic_profile": {
            "interactions": interactions,
            "visits": visits,
        },
        "location": {"city": city},
        "last_active": None,
    }


SAMPLE_OPPORTUNITIES = [
    {"id": "opp-1", "title": "Housing Element Update", "tags": ["housing", "zoning"]},
    {"id": "opp-2", "title": "Traffic Calming Study", "tags": ["traffic", "safety"]},
    {"id": "opp-3", "title": "Climate Action Plan", "tags": ["environment", "climate"]},
]


# ---------------------------------------------------------------------------
# _extract_topic
# ---------------------------------------------------------------------------

class TestExtractTopic:
    def setup_method(self):
        self.svc = _make_service()

    def test_planning_keyword_returns_urban_planning(self):
        assert self.svc._extract_topic("What's the zoning plan?") == "urban_planning"

    def test_development_keyword_returns_urban_planning(self):
        assert self.svc._extract_topic("New development on 4th") == "urban_planning"

    def test_budget_keyword_returns_municipal_budget(self):
        assert self.svc._extract_topic("How is the budget allocated?") == "municipal_budget"

    def test_tax_keyword_returns_municipal_budget(self):
        assert self.svc._extract_topic("Local tax increase proposal") == "municipal_budget"

    def test_spending_keyword_returns_municipal_budget(self):
        assert self.svc._extract_topic("Concerned about spending") == "municipal_budget"

    def test_traffic_keyword_returns_transportation(self):
        assert self.svc._extract_topic("Traffic on Lincoln Ave") == "transportation"

    def test_parking_keyword_returns_transportation(self):
        assert self.svc._extract_topic("Parking downtown is terrible") == "transportation"

    def test_transportation_keyword_returns_transportation(self):
        assert self.svc._extract_topic("Public transportation options") == "transportation"

    def test_environment_keyword_returns_environment(self):
        assert self.svc._extract_topic("Environment impact report") == "environment"

    def test_climate_keyword_returns_environment(self):
        assert self.svc._extract_topic("Climate action plan update") == "environment"

    def test_green_keyword_returns_environment(self):
        assert self.svc._extract_topic("Green infrastructure proposal") == "environment"

    def test_unrecognized_message_returns_general_civic(self):
        assert self.svc._extract_topic("What happened last week?") == "general_civic"

    def test_empty_string_returns_general_civic(self):
        assert self.svc._extract_topic("") == "general_civic"

    def test_case_insensitive_detection(self):
        assert self.svc._extract_topic("ZONING CHANGES") == "urban_planning"

    def test_first_match_wins_planning_over_budget(self):
        # "planning" is checked before "budget" in the if-elif chain
        result = self.svc._extract_topic("planning the budget")
        assert result == "urban_planning"


# ---------------------------------------------------------------------------
# _extract_user_goals
# ---------------------------------------------------------------------------

class TestExtractUserGoals:
    def setup_method(self):
        self.svc = _make_service()

    def test_learn_keyword_produces_learn_goal(self):
        goals = self.svc._extract_user_goals("i want to learn about housing")
        assert "learn_about_issue" in goals

    def test_understand_keyword_produces_learn_goal(self):
        goals = self.svc._extract_user_goals("help me understand zoning")
        assert "learn_about_issue" in goals

    def test_participate_keyword_produces_participation_goal(self):
        goals = self.svc._extract_user_goals("how can i participate in the process")
        assert "civic_participation" in goals

    def test_get_involved_phrase_produces_participation_goal(self):
        goals = self.svc._extract_user_goals("i want to get involved")
        assert "civic_participation" in goals

    def test_comment_keyword_produces_comment_goal(self):
        goals = self.svc._extract_user_goals("i want to submit a comment")
        assert "submit_public_comment" in goals

    def test_draft_keyword_produces_comment_goal(self):
        goals = self.svc._extract_user_goals("draft a letter")
        assert "submit_public_comment" in goals

    def test_meeting_keyword_produces_attend_goal(self):
        goals = self.svc._extract_user_goals("when is the next meeting")
        assert "attend_meeting" in goals

    def test_attend_keyword_produces_attend_goal(self):
        goals = self.svc._extract_user_goals("i want to attend the hearing")
        assert "attend_meeting" in goals

    def test_multiple_goals_extracted(self):
        goals = self.svc._extract_user_goals("i want to learn and submit a comment")
        assert "learn_about_issue" in goals
        assert "submit_public_comment" in goals
        assert len(goals) == 2

    def test_no_keywords_produces_empty_list(self):
        goals = self.svc._extract_user_goals("hello there")
        assert goals == []

    def test_empty_string_produces_empty_list(self):
        goals = self.svc._extract_user_goals("")
        assert goals == []


# ---------------------------------------------------------------------------
# _infer_stance
# ---------------------------------------------------------------------------

class TestInferStance:
    def setup_method(self):
        self.svc = _make_service()

    def test_support_keyword(self):
        assert self.svc._infer_stance("I support this proposal") == "support"

    def test_favor_keyword(self):
        assert self.svc._infer_stance("I am in favor of it") == "support"

    def test_like_keyword(self):
        assert self.svc._infer_stance("I like this idea") == "support"

    def test_agree_keyword(self):
        assert self.svc._infer_stance("I agree with the plan") == "support"

    def test_oppose_keyword(self):
        assert self.svc._infer_stance("I oppose the rezoning") == "oppose"

    def test_against_keyword(self):
        assert self.svc._infer_stance("I'm against this change") == "oppose"

    def test_disagree_matches_support_due_to_agree_substring(self):
        # "disagree" contains "agree", which matches "support" first in the if-elif chain
        assert self.svc._infer_stance("I disagree with the proposal") == "support"

    def test_concern_keyword(self):
        assert self.svc._infer_stance("I have a concern about noise") == "oppose"

    def test_question_keyword(self):
        assert self.svc._infer_stance("I question the cost estimate") == "question"

    def test_unclear_keyword(self):
        assert self.svc._infer_stance("The timeline is unclear") == "question"

    def test_more_info_phrase(self):
        assert self.svc._infer_stance("Need more info on impact") == "question"

    def test_neutral_message_returns_none(self):
        assert self.svc._infer_stance("Tell me about the meeting") is None

    def test_empty_message_returns_none(self):
        assert self.svc._infer_stance("") is None

    def test_case_insensitive(self):
        assert self.svc._infer_stance("I SUPPORT this") == "support"

    def test_first_match_wins_support_over_oppose(self):
        # "support" is checked first in the if-elif chain
        result = self.svc._infer_stance("I support it but also have a concern")
        assert result == "support"


# ---------------------------------------------------------------------------
# _extract_key_points
# ---------------------------------------------------------------------------

class TestExtractKeyPoints:
    def setup_method(self):
        self.svc = _make_service()

    def test_long_sentence_extracted(self):
        msg = "This is a long sentence that exceeds twenty characters."
        result = self.svc._extract_key_points(msg)
        assert result == "This is a long sentence that exceeds twenty characters"

    def test_short_sentences_filtered_out(self):
        msg = "Short. Also short. This sentence is long enough to pass the filter."
        result = self.svc._extract_key_points(msg)
        assert "Short" not in result
        assert "This sentence is long enough to pass the filter" in result

    def test_multiple_long_sentences_joined_with_newlines(self):
        msg = "First long sentence exceeds threshold. Second long sentence also exceeds."
        result = self.svc._extract_key_points(msg)
        assert "First long sentence exceeds threshold" in result
        assert "Second long sentence also exceeds" in result
        assert "\n" in result

    def test_max_three_key_points(self):
        sentences = [f"This is sentence number {i} which is long enough" for i in range(5)]
        msg = ". ".join(sentences) + "."
        result = self.svc._extract_key_points(msg)
        # Count lines — max 3
        lines = result.strip().split("\n")
        assert len(lines) == 3

    def test_all_short_sentences_returns_none(self):
        msg = "Short. Tiny. Ok."
        result = self.svc._extract_key_points(msg)
        assert result is None

    def test_empty_string_returns_none(self):
        result = self.svc._extract_key_points("")
        assert result is None

    def test_exactly_20_chars_excluded(self):
        # A sentence stripped to exactly 20 chars should NOT pass (> 20 required)
        msg = "12345678901234567890."  # 20 chars before period
        result = self.svc._extract_key_points(msg)
        assert result is None

    def test_exactly_21_chars_included(self):
        msg = "123456789012345678901."  # 21 chars before period
        result = self.svc._extract_key_points(msg)
        assert "123456789012345678901" in result


# ---------------------------------------------------------------------------
# _update_user_activity
# ---------------------------------------------------------------------------

class TestUpdateUserActivity:
    def setup_method(self):
        self.svc = _make_service()

    def test_increments_interaction_count(self):
        profile = _make_user_profile(interactions=5, visits=1)
        self.svc._update_user_activity(profile)
        assert profile["civic_profile"]["interactions"] == 6

    def test_sets_last_active_timestamp(self):
        profile = _make_user_profile()
        self.svc._update_user_activity(profile)
        assert profile["last_active"] is not None
        # ISO format contains "T" separator
        assert "T" in profile["last_active"]

    def test_expert_promotion_at_threshold(self):
        # 7 interactions + 1 from update = 8, visits = 3 → expert
        profile = _make_user_profile(experience="returning", interactions=7, visits=3)
        self.svc._update_user_activity(profile)
        assert profile["experience_level"] == "expert"

    def test_returning_promotion_at_threshold(self):
        # visits >= 2 but interactions < 8 → returning
        profile = _make_user_profile(experience="new", interactions=0, visits=2)
        self.svc._update_user_activity(profile)
        assert profile["experience_level"] == "returning"

    def test_no_promotion_below_threshold(self):
        # 1 visit, 0 interactions + 1 = 1 → stays "new"
        profile = _make_user_profile(experience="new", interactions=0, visits=1)
        self.svc._update_user_activity(profile)
        assert profile["experience_level"] == "new"

    def test_expert_requires_both_conditions(self):
        # 8 interactions but only 2 visits → "returning" not "expert"
        profile = _make_user_profile(experience="new", interactions=7, visits=2)
        self.svc._update_user_activity(profile)
        # interactions = 8 but visits = 2 (< 3), so expert condition fails
        # visits >= 2 → returning
        assert profile["experience_level"] == "returning"


# ---------------------------------------------------------------------------
# _create_conversation_context
# ---------------------------------------------------------------------------

class TestCreateConversationContext:
    def setup_method(self):
        self.svc = _make_service(SAMPLE_OPPORTUNITIES)

    def test_housing_issue_detected(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("concerned about housing", profile)
        assert "housing" in ctx["civic_issues_mentioned"]

    def test_traffic_issue_detected_via_parking(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("parking is terrible downtown", profile)
        assert "traffic" in ctx["civic_issues_mentioned"]

    def test_environment_issue_detected(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("climate change action needed", profile)
        assert "environment" in ctx["civic_issues_mentioned"]

    def test_budget_issue_detected_via_tax(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("property tax increase", profile)
        assert "budget" in ctx["civic_issues_mentioned"]

    def test_education_issue_detected_via_school(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("school funding cuts", profile)
        assert "education" in ctx["civic_issues_mentioned"]

    def test_multiple_issues_detected(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("housing near the school zone", profile)
        assert "housing" in ctx["civic_issues_mentioned"]
        assert "education" in ctx["civic_issues_mentioned"]

    def test_no_issues_detected_for_generic_message(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("hello there", profile)
        assert ctx["civic_issues_mentioned"] == []

    def test_topic_set_from_message(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("new development downtown", profile)
        assert ctx["current_topic"] == "urban_planning"

    def test_user_goals_set(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("I want to learn about housing", profile)
        assert "learn_about_issue" in ctx["user_goals"]

    def test_related_opportunities_found(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("concerned about housing", profile)
        assert "opp-1" in ctx["related_opportunities"]

    def test_conversation_phase_starts_at_engagement(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("hello", profile)
        assert ctx["conversation_phase"] == "engagement"

    def test_message_count_starts_at_one(self):
        profile = _make_user_profile()
        ctx = self.svc._create_conversation_context("anything", profile)
        assert ctx["message_count"] == 1


# ---------------------------------------------------------------------------
# _update_conversation_context
# ---------------------------------------------------------------------------

class TestUpdateConversationContext:
    def setup_method(self):
        self.svc = _make_service()

    def _base_context(self):
        return {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": [],
            "conversation_phase": "engagement",
            "message_count": 1,
        }

    def test_message_count_incremented(self):
        ctx = self._base_context()
        updated = self.svc._update_conversation_context(ctx, "hello")
        assert updated["message_count"] == 2

    def test_message_count_increments_from_missing_key(self):
        ctx = self._base_context()
        del ctx["message_count"]
        updated = self.svc._update_conversation_context(ctx, "hello")
        assert updated["message_count"] == 1  # 0 + 1

    def test_topic_updated_on_new_message(self):
        ctx = self._base_context()
        updated = self.svc._update_conversation_context(ctx, "tell me about traffic")
        assert updated["current_topic"] == "transportation"

    def test_phase_transitions_to_action_planning_on_yes(self):
        ctx = self._base_context()
        updated = self.svc._update_conversation_context(ctx, "yes, tell me more")
        assert updated["conversation_phase"] == "action_planning"

    def test_phase_transitions_to_action_planning_on_interested(self):
        ctx = self._base_context()
        updated = self.svc._update_conversation_context(ctx, "I'm interested")
        assert updated["conversation_phase"] == "action_planning"

    def test_phase_transitions_to_civic_action_on_draft(self):
        ctx = self._base_context()
        updated = self.svc._update_conversation_context(ctx, "help me draft a comment")
        assert updated["conversation_phase"] == "civic_action"

    def test_phase_transitions_to_civic_action_on_submit(self):
        ctx = self._base_context()
        updated = self.svc._update_conversation_context(ctx, "I want to submit")
        assert updated["conversation_phase"] == "civic_action"

    def test_phase_unchanged_for_neutral_message(self):
        ctx = self._base_context()
        updated = self.svc._update_conversation_context(ctx, "hello there")
        assert updated["conversation_phase"] == "engagement"

    def test_action_planning_checked_before_civic_action(self):
        # "yes" triggers action_planning; "draft" triggers civic_action
        # action_planning is checked first in the if-elif chain
        ctx = self._base_context()
        updated = self.svc._update_conversation_context(ctx, "yes draft it")
        assert updated["conversation_phase"] == "action_planning"


# ---------------------------------------------------------------------------
# _find_related_opportunities
# ---------------------------------------------------------------------------

class TestFindRelatedOpportunities:
    def setup_method(self):
        self.svc = _make_service(SAMPLE_OPPORTUNITIES)

    def test_housing_issue_matches_housing_opportunity(self):
        related = self.svc._find_related_opportunities(["housing"])
        assert "opp-1" in related

    def test_traffic_issue_matches_traffic_opportunity(self):
        related = self.svc._find_related_opportunities(["traffic"])
        assert "opp-2" in related

    def test_environment_issue_matches_climate_opportunity(self):
        related = self.svc._find_related_opportunities(["environment"])
        assert "opp-3" in related

    def test_no_issues_returns_empty(self):
        related = self.svc._find_related_opportunities([])
        assert related == []

    def test_unmatched_issue_returns_empty(self):
        related = self.svc._find_related_opportunities(["sewage"])
        assert related == []

    def test_max_three_results(self):
        # Add more than 3 matching opportunities
        many_opps = [
            {"id": f"opp-{i}", "title": f"Housing project {i}", "tags": ["housing"]}
            for i in range(5)
        ]
        self.svc.civic_opportunities = many_opps
        related = self.svc._find_related_opportunities(["housing"])
        assert len(related) == 3

    def test_matches_by_tag(self):
        self.svc.civic_opportunities = [
            {"id": "tagged", "title": "Something Else", "tags": ["housing"]},
        ]
        related = self.svc._find_related_opportunities(["housing"])
        assert "tagged" in related

    def test_matches_by_title(self):
        self.svc.civic_opportunities = [
            {"id": "titled", "title": "Housing Discussion", "tags": []},
        ]
        related = self.svc._find_related_opportunities(["housing"])
        assert "titled" in related


# ---------------------------------------------------------------------------
# _get_opportunity_by_id
# ---------------------------------------------------------------------------

class TestGetOpportunityById:
    def setup_method(self):
        self.svc = _make_service(SAMPLE_OPPORTUNITIES)

    def test_existing_id_returns_opportunity(self):
        opp = self.svc._get_opportunity_by_id("opp-1")
        assert opp["title"] == "Housing Element Update"

    def test_nonexistent_id_returns_none(self):
        opp = self.svc._get_opportunity_by_id("opp-999")
        assert opp is None

    def test_empty_opportunities_returns_none(self):
        self.svc.civic_opportunities = []
        opp = self.svc._get_opportunity_by_id("opp-1")
        assert opp is None


# ---------------------------------------------------------------------------
# _generate_error_response
# ---------------------------------------------------------------------------

class TestGenerateErrorResponse:
    def setup_method(self):
        self.svc = _make_service()

    def test_error_response_has_correct_role(self):
        resp = self.svc._generate_error_response()
        assert resp["message"]["role"] == "assistant"

    def test_error_response_has_error_metadata(self):
        resp = self.svc._generate_error_response()
        assert resp["message"]["metadata"]["response_type"] == "error"

    def test_error_response_has_retry_action(self):
        resp = self.svc._generate_error_response()
        assert len(resp["actions"]) == 1
        assert resp["actions"][0]["action_type"] == "quick_start"
        assert resp["actions"][0]["label"] == "Try Again"

    def test_error_response_has_empty_context(self):
        resp = self.svc._generate_error_response()
        assert resp["conversation_context"] == {}

    def test_error_response_content_mentions_try_again(self):
        resp = self.svc._generate_error_response()
        assert "try again" in resp["message"]["content"].lower()


# ---------------------------------------------------------------------------
# _generate_static_response
# ---------------------------------------------------------------------------

class TestGenerateStaticResponse:
    def setup_method(self):
        self.svc = _make_service(SAMPLE_OPPORTUNITIES)

    def _ctx(self, related=None):
        return {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": related or [],
            "conversation_phase": "engagement",
            "message_count": 1,
        }

    def test_greeting_response_mentions_city(self):
        profile = _make_user_profile(city="Berkeley")
        resp = self.svc._generate_static_response("hello", profile, self._ctx())
        assert "Berkeley" in resp["message"]["content"]

    def test_help_response_mentions_capabilities(self):
        profile = _make_user_profile()
        resp = self.svc._generate_static_response("what can you do", profile, self._ctx())
        assert "civic events" in resp["message"]["content"]
        assert "public comments" in resp["message"]["content"]

    def test_related_opportunity_mentioned_in_content(self):
        profile = _make_user_profile()
        ctx = self._ctx(related=["opp-1"])
        resp = self.svc._generate_static_response("housing plans", profile, ctx)
        assert "Housing Element Update" in resp["message"]["content"]

    def test_new_user_gets_quick_start_action(self):
        profile = _make_user_profile(experience="new")
        resp = self.svc._generate_static_response("hello", profile, self._ctx())
        assert len(resp["actions"]) == 1
        assert resp["actions"][0]["action_type"] == "quick_start"
        assert resp["actions"][0]["label"] == "Show Me Opportunities"

    def test_expert_user_gets_draft_and_impact_actions(self):
        profile = _make_user_profile(experience="expert")
        resp = self.svc._generate_static_response("hello", profile, self._ctx())
        assert len(resp["actions"]) == 2
        action_types = [a["action_type"] for a in resp["actions"]]
        assert "draft_comment" in action_types
        assert "view_impact" in action_types

    def test_expert_impact_action_has_experience_gate(self):
        profile = _make_user_profile(experience="expert")
        resp = self.svc._generate_static_response("hello", profile, self._ctx())
        impact_action = [a for a in resp["actions"] if a["action_type"] == "view_impact"][0]
        assert impact_action["experience_gate"] == "expert"

    def test_returning_user_gets_no_actions(self):
        profile = _make_user_profile(experience="returning")
        resp = self.svc._generate_static_response("hello", profile, self._ctx())
        assert resp["actions"] == []

    def test_response_metadata_is_static_fallback(self):
        profile = _make_user_profile()
        resp = self.svc._generate_static_response("hi", profile, self._ctx())
        assert resp["message"]["metadata"]["response_type"] == "static_fallback"

    def test_default_response_for_unrecognized_input(self):
        profile = _make_user_profile()
        resp = self.svc._generate_static_response("xyz123", profile, self._ctx())
        assert "participate" in resp["message"]["content"].lower()

    def test_missing_city_falls_back_to_your_city(self):
        profile = _make_user_profile()
        profile["location"] = {}
        resp = self.svc._generate_static_response("hi", profile, self._ctx())
        assert "your city" in resp["message"]["content"]


# ---------------------------------------------------------------------------
# _generate_contextual_response
# ---------------------------------------------------------------------------

class TestGenerateContextualResponse:
    def setup_method(self):
        self.svc = _make_service(SAMPLE_OPPORTUNITIES)

    def test_action_planning_phase_with_opportunity_lists_actions(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "housing",
            "civic_issues_mentioned": ["housing"],
            "user_goals": [],
            "related_opportunities": ["opp-1"],
            "conversation_phase": "action_planning",
            "message_count": 2,
        }
        resp = self.svc._generate_contextual_response("yes", profile, ctx)
        assert "participate" in resp["message"]["content"].lower()
        assert "Housing Element Update" in resp["message"]["content"]
        assert len(resp["actions"]) == 2
        assert resp["actions"][0]["mcp_tool"] == "compose_public_comment"
        assert resp["actions"][1]["mcp_tool"] == "get_comment_guidelines"

    def test_action_planning_without_opportunity_uses_fallback_title(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": ["nonexistent-id"],
            "conversation_phase": "action_planning",
            "message_count": 2,
        }
        resp = self.svc._generate_contextual_response("yes", profile, ctx)
        assert "this opportunity" in resp["message"]["content"]
        # Fallback parameters in the action
        assert resp["actions"][0]["mcp_parameters"]["item_id"] == "general"

    def test_engagement_phase_with_issues_mentions_them(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "housing",
            "civic_issues_mentioned": ["housing", "traffic"],
            "user_goals": [],
            "related_opportunities": ["opp-1"],
            "conversation_phase": "engagement",
            "message_count": 1,
        }
        resp = self.svc._generate_contextual_response("housing and traffic", profile, ctx)
        assert "housing" in resp["message"]["content"]
        assert "traffic" in resp["message"]["content"]
        assert "1 related civic events" in resp["message"]["content"]

    def test_engagement_phase_without_issues_gives_generic(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": [],
            "conversation_phase": "engagement",
            "message_count": 1,
        }
        resp = self.svc._generate_contextual_response("hello", profile, ctx)
        assert "engage" in resp["message"]["content"].lower()
        assert resp["actions"][0]["action_type"] == "quick_start"

    def test_contextual_response_metadata_type(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": [],
            "conversation_phase": "engagement",
            "message_count": 1,
        }
        resp = self.svc._generate_contextual_response("hello", profile, ctx)
        assert resp["message"]["metadata"]["response_type"] == "contextual"


# ---------------------------------------------------------------------------
# _generate_mcp_response — comment drafting path
# ---------------------------------------------------------------------------

class TestGenerateMcpResponseComment:
    def setup_method(self):
        self.svc = _make_service(SAMPLE_OPPORTUNITIES)
        self.svc.enable_mcp = True

    def test_draft_keyword_triggers_comment_drafting(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "housing",
            "civic_issues_mentioned": ["housing"],
            "user_goals": [],
            "related_opportunities": ["opp-1"],
            "conversation_phase": "civic_action",
            "message_count": 2,
        }
        resp = self.svc._generate_mcp_response(
            "draft a comment supporting housing", profile, ctx
        )
        assert "drafted a public comment" in resp["message"]["content"]
        assert resp["message"]["metadata"]["mcp_tool_used"] == "compose_public_comment"
        assert len(resp["actions"]) == 2
        assert resp["actions"][0]["mcp_tool"] == "get_comment_guidelines"

    def test_comment_drafting_requires_related_opportunities(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": [],  # No opportunities
            "conversation_phase": "engagement",
            "message_count": 1,
        }
        resp = self.svc._generate_mcp_response("draft a comment", profile, ctx)
        # Falls through to contextual response (no opportunity)
        assert resp["message"]["metadata"]["response_type"] == "contextual"


# ---------------------------------------------------------------------------
# _generate_mcp_response — guidelines path
# ---------------------------------------------------------------------------

class TestGenerateMcpResponseGuidelines:
    def setup_method(self):
        self.svc = _make_service()
        self.svc.enable_mcp = True

    def test_guidelines_keyword_returns_guidelines(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": [],
            "conversation_phase": "engagement",
            "message_count": 1,
        }
        resp = self.svc._generate_mcp_response("what are the guidelines", profile, ctx)
        assert "submission guidelines" in resp["message"]["content"]
        assert resp["message"]["metadata"]["mcp_tool_used"] == "get_comment_guidelines"
        assert resp["actions"] == []

    def test_how_to_submit_triggers_guidelines(self):
        profile = _make_user_profile()
        ctx = {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": [],
            "conversation_phase": "engagement",
            "message_count": 1,
        }
        resp = self.svc._generate_mcp_response("how to submit a comment", profile, ctx)
        assert "submission guidelines" in resp["message"]["content"]


# ---------------------------------------------------------------------------
# handle_conversation — integration
# ---------------------------------------------------------------------------

class TestHandleConversation:
    def setup_method(self):
        self.svc = _make_service(SAMPLE_OPPORTUNITIES)

    def test_creates_context_when_none_provided(self):
        profile = _make_user_profile()
        result = self.svc.handle_conversation("interested in housing", profile)
        assert "conversation_context" in result
        assert result["conversation_context"]["message_count"] == 1
        assert "housing" in result["conversation_context"]["civic_issues_mentioned"]

    def test_updates_existing_context(self):
        profile = _make_user_profile()
        existing_ctx = {
            "current_topic": "general_civic",
            "civic_issues_mentioned": [],
            "user_goals": [],
            "related_opportunities": [],
            "conversation_phase": "engagement",
            "message_count": 3,
        }
        result = self.svc.handle_conversation("tell me about traffic", profile, existing_ctx)
        assert result["conversation_context"]["message_count"] == 4
        assert result["conversation_context"]["current_topic"] == "transportation"

    def test_increments_user_interactions(self):
        profile = _make_user_profile(interactions=5)
        self.svc.handle_conversation("hello", profile)
        assert profile["civic_profile"]["interactions"] == 6

    def test_response_has_message_and_actions(self):
        profile = _make_user_profile()
        result = self.svc.handle_conversation("hello", profile)
        assert "message" in result
        assert "actions" in result
        assert result["message"]["role"] == "assistant"

    def test_error_handling_returns_error_response(self):
        profile = _make_user_profile()
        # Cause an error by giving a profile without civic_profile key
        bad_profile = {"experience_level": "new"}
        result = self.svc.handle_conversation("hello", bad_profile)
        assert result["message"]["metadata"]["response_type"] == "error"
        assert "conversation_context" in result

    def test_mcp_enabled_uses_mcp_response(self):
        self.svc.enable_mcp = True
        profile = _make_user_profile()
        result = self.svc.handle_conversation("what are the guidelines", profile)
        assert "submission guidelines" in result["message"]["content"]

    def test_mcp_disabled_uses_static_response(self):
        self.svc.enable_mcp = False
        profile = _make_user_profile()
        result = self.svc.handle_conversation("hello", profile)
        assert result["message"]["metadata"]["response_type"] == "static_fallback"


# ---------------------------------------------------------------------------
# Fallback functions (module-level)
# ---------------------------------------------------------------------------

class TestFallbackComposePubComment:
    """Test the fallback compose_public_comment when MCP is not available."""

    def test_includes_item_title(self):
        from civicos_services.utils.conversation_service import compose_public_comment
        result = compose_public_comment("id-1", "Housing Plan 2025")
        assert "Housing Plan 2025" in result

    def test_includes_stance(self):
        from civicos_services.utils.conversation_service import compose_public_comment
        result = compose_public_comment("id-1", "Bike Lane", resident_stance="support")
        assert "I support" in result

    def test_default_stance_when_none(self):
        from civicos_services.utils.conversation_service import compose_public_comment
        result = compose_public_comment("id-1", "Bike Lane", resident_stance=None)
        assert "I am commenting on" in result

    def test_includes_key_points_when_provided(self):
        from civicos_services.utils.conversation_service import compose_public_comment
        result = compose_public_comment("id-1", "Park", key_points="Safety concerns for children")
        assert "Safety concerns for children" in result

    def test_default_key_points_when_none(self):
        from civicos_services.utils.conversation_service import compose_public_comment
        result = compose_public_comment("id-1", "Park", key_points=None)
        assert "careful consideration" in result

    def test_has_letter_format(self):
        from civicos_services.utils.conversation_service import compose_public_comment
        result = compose_public_comment("id-1", "Test")
        assert "Dear Council Members" in result
        assert "Sincerely" in result
        assert "Concerned Resident" in result


class TestFallbackGetCommentGuidelines:
    """Test the fallback get_comment_guidelines when MCP is not available."""

    def test_returns_guidelines_text(self):
        from civicos_services.utils.conversation_service import get_comment_guidelines
        result = get_comment_guidelines("san-rafael")
        assert "Public Comment Guidelines" in result

    def test_includes_email_address(self):
        from civicos_services.utils.conversation_service import get_comment_guidelines
        result = get_comment_guidelines()
        assert "clerk@cityofsanrafael.org" in result

    def test_includes_deadline_info(self):
        from civicos_services.utils.conversation_service import get_comment_guidelines
        result = get_comment_guidelines()
        assert "5:00 PM" in result

    def test_includes_time_limit(self):
        from civicos_services.utils.conversation_service import get_comment_guidelines
        result = get_comment_guidelines()
        assert "3 minutes" in result


# ---------------------------------------------------------------------------
# _load_civic_opportunities (filesystem boundary)
# ---------------------------------------------------------------------------

class TestLoadCivicOpportunities:
    def test_no_schema_dir_loads_nothing(self):
        """When the schema directory doesn't exist, no opportunities are loaded."""
        with patch.object(ConversationService, "_load_civic_opportunities"):
            svc = ConversationService(enable_mcp=False)
        svc.civic_opportunities = []
        # Now call the real method — it will look for a dir that doesn't exist
        svc._load_civic_opportunities()
        assert svc.civic_opportunities == []


# ---------------------------------------------------------------------------
# ConversationService init
# ---------------------------------------------------------------------------

class TestConversationServiceInit:
    def test_enable_mcp_flag_stored(self):
        svc = _make_service()
        assert svc.enable_mcp is False

    def test_enable_mcp_true(self):
        with patch.object(ConversationService, "_load_civic_opportunities"):
            svc = ConversationService(enable_mcp=True)
        assert svc.enable_mcp is True

    def test_empty_opportunities_on_init(self):
        svc = _make_service()
        assert svc.civic_opportunities == []

    def test_empty_user_profiles_on_init(self):
        svc = _make_service()
        assert svc.user_profiles == {}
