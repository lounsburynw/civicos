"""
Context-Aware Agent for Edge Intelligence

Stateless agent that applies user context to personalize responses.
Context comes in per-request; agent reasons about relevance and forgets.

Session 536: Initial implementation

Privacy Design:
- User context stored locally (browser localStorage)
- Context transmitted per-request, never stored server-side
- No query logging, no behavior tracking
- Agent applies user's filtering logic, not platform recommendations
- Transparent reasoning: agent explains why it surfaced something

Capabilities:
1. Parse user context from request
2. Apply filtering_instructions as reasoning constraints
3. Use location for geographic relevance ('affects your neighborhood')
4. Reference voice_history and commitment_history
5. Generate transparent reasoning ('I'm showing you this because...')
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
import logging
import re

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models (match TypeScript interfaces from civic.ts)
# ============================================================================

class UserNeighborhood(BaseModel):
    """User's neighborhood location for proximity filtering."""
    neighborhood: str = Field(..., description="e.g., 'Terra Linda'")
    lat: Optional[float] = None
    lng: Optional[float] = None


class UserContextForRequest(BaseModel):
    """
    Serialized user context transmitted with API requests.

    Matches TypeScript UserContextForRequest interface.
    Only includes what the agent needs for filtering - never sensitive data.
    """
    jurisdiction: str = Field(..., description="e.g., 'city-san-rafael'")
    location: Optional[UserNeighborhood] = None
    interests: List[str] = Field(default_factory=list, description="e.g., ['housing', 'transportation']")
    filtering_instructions: str = Field(default="", description="Natural language, e.g., 'aggressive on housing, ignore parking'")
    notification_email: Optional[str] = None
    # History references (Nostr event IDs, not full content)
    voice_history: List[str] = Field(default_factory=list, description="IDs of voice events user created")
    commitment_history: List[str] = Field(default_factory=list, description="IDs of commitments user made")


# ============================================================================
# Filtering Logic
# ============================================================================

@dataclass
class FilteringConstraints:
    """
    Parsed filtering instructions as structured constraints.

    Examples:
    - "aggressive on housing, ignore parking" →
      boost_topics=['housing'], ignore_topics=['parking']
    - "focus on transportation infrastructure" →
      boost_topics=['transportation', 'infrastructure']
    """
    boost_topics: List[str] = field(default_factory=list)
    ignore_topics: List[str] = field(default_factory=list)
    priority_keywords: List[str] = field(default_factory=list)


def parse_filtering_instructions(instructions: str) -> FilteringConstraints:
    """
    Parse natural language filtering instructions into structured constraints.

    Recognizes patterns like:
    - "aggressive on X", "focus on X", "prioritize X" → boost topic X
    - "ignore X", "skip X", "hide X", "no X" → ignore topic X

    Args:
        instructions: Natural language filtering preferences

    Returns:
        FilteringConstraints with parsed boost/ignore topics
    """
    if not instructions:
        return FilteringConstraints()

    instructions_lower = instructions.lower()

    boost_topics = []
    ignore_topics = []

    # Patterns for boosting topics
    boost_patterns = [
        r'aggressive on\s+(\w+)',
        r'focus on\s+(\w+)',
        r'prioritize\s+(\w+)',
        r'interested in\s+(\w+)',
        r'care about\s+(\w+)',
        r'show me\s+(\w+)',
    ]

    # Patterns for ignoring topics
    ignore_patterns = [
        r'ignore\s+(\w+)',
        r'skip\s+(\w+)',
        r'hide\s+(\w+)',
        r'no\s+(\w+)',
        r"don'?t show\s+(\w+)",
        r'filter out\s+(\w+)',
    ]

    for pattern in boost_patterns:
        matches = re.findall(pattern, instructions_lower)
        boost_topics.extend(matches)

    for pattern in ignore_patterns:
        matches = re.findall(pattern, instructions_lower)
        ignore_topics.extend(matches)

    # Deduplicate while preserving order
    boost_topics = list(dict.fromkeys(boost_topics))
    ignore_topics = list(dict.fromkeys(ignore_topics))

    return FilteringConstraints(
        boost_topics=boost_topics,
        ignore_topics=ignore_topics
    )


def apply_filtering_logic(
    constraints: FilteringConstraints,
    results: List[Dict[str, Any]],
    topic_field: str = "topics"
) -> List[Dict[str, Any]]:
    """
    Apply filtering constraints to reorder/filter results.

    Args:
        constraints: Parsed filtering constraints
        results: List of result dicts (meetings, issues, etc.)
        topic_field: Field name containing topics (e.g., 'topics', 'tags')

    Returns:
        Reordered results with boosted items first, ignored items removed
    """
    if not constraints.boost_topics and not constraints.ignore_topics:
        return results

    filtered = []
    boosted = []

    for result in results:
        topics = result.get(topic_field, [])
        if isinstance(topics, str):
            topics = [topics]
        topics_lower = [t.lower() for t in topics]

        # Check if should be ignored
        should_ignore = any(
            ignore_topic in ' '.join(topics_lower)
            for ignore_topic in constraints.ignore_topics
        )
        if should_ignore:
            continue

        # Check if should be boosted
        should_boost = any(
            boost_topic in ' '.join(topics_lower)
            for boost_topic in constraints.boost_topics
        )

        if should_boost:
            boosted.append(result)
        else:
            filtered.append(result)

    # Boosted items first, then regular items
    return boosted + filtered


# ============================================================================
# Location-Based Relevance
# ============================================================================

def calculate_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate approximate distance between two points in km (Haversine)."""
    import math

    R = 6371  # Earth's radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def add_location_context(
    location: Optional[UserNeighborhood],
    results: List[Dict[str, Any]],
    lat_field: str = "lat",
    lng_field: str = "lng"
) -> List[Dict[str, Any]]:
    """
    Annotate results with neighborhood relevance.

    Adds 'affects_your_neighborhood' flag and 'distance_km' for items
    that have location data and are within user's area.

    Args:
        location: User's neighborhood location
        results: List of result dicts with optional lat/lng
        lat_field: Field name for latitude
        lng_field: Field name for longitude

    Returns:
        Results annotated with location relevance
    """
    if not location or not location.lat or not location.lng:
        return results

    NEIGHBORHOOD_RADIUS_KM = 3.0  # ~2 miles

    annotated = []
    for result in results:
        result_copy = result.copy()

        result_lat = result.get(lat_field)
        result_lng = result.get(lng_field)

        if result_lat and result_lng:
            try:
                distance = calculate_distance_km(
                    location.lat, location.lng,
                    float(result_lat), float(result_lng)
                )
                result_copy['distance_km'] = round(distance, 2)
                result_copy['affects_your_neighborhood'] = distance <= NEIGHBORHOOD_RADIUS_KM
            except (ValueError, TypeError):
                pass

        # Also check if neighborhood name is mentioned
        description = result.get('description', '') or result.get('title', '') or ''
        if location.neighborhood.lower() in description.lower():
            result_copy['affects_your_neighborhood'] = True

        annotated.append(result_copy)

    return annotated


# ============================================================================
# Reasoning Transparency
# ============================================================================

def generate_personalization_reasoning(
    user_context: UserContextForRequest,
    action: str,
    parameters: Optional[Dict[str, Any]] = None,
    result_count: int = 0
) -> str:
    """
    Generate transparent reasoning explaining why results are shown.

    The agent should explain its filtering decisions to build trust.

    Args:
        user_context: User's context including interests and location
        action: The action being taken (search_events, etc.)
        parameters: Action parameters
        result_count: Number of results being returned

    Returns:
        Human-readable explanation of personalization
    """
    reasons = []

    # Interest-based reasoning
    if user_context.interests:
        matched_interests = []
        if parameters:
            query = parameters.get('query', '').lower()
            for interest in user_context.interests:
                if interest.lower() in query:
                    matched_interests.append(interest)

        if matched_interests:
            if len(matched_interests) == 1:
                reasons.append(f"matching your interest in {matched_interests[0]}")
            else:
                reasons.append(f"matching your interests in {', '.join(matched_interests)}")

    # Location-based reasoning
    if user_context.location and user_context.location.neighborhood:
        reasons.append(f"relevant to {user_context.location.neighborhood}")

    # Filtering instructions reasoning
    if user_context.filtering_instructions:
        constraints = parse_filtering_instructions(user_context.filtering_instructions)
        if constraints.boost_topics:
            reasons.append(f"prioritizing {', '.join(constraints.boost_topics)} as you requested")
        if constraints.ignore_topics:
            reasons.append(f"filtering out {', '.join(constraints.ignore_topics)}")

    # Voice/commitment history reasoning
    if user_context.voice_history:
        reasons.append("considering your previous civic engagement")

    if not reasons:
        return ""

    # Build natural sentence
    if len(reasons) == 1:
        return f"I'm showing you this because {reasons[0]}."
    else:
        return f"I'm showing you this because {', '.join(reasons[:-1])}, and {reasons[-1]}."


# ============================================================================
# Context Agent Class
# ============================================================================

class ContextAgent:
    """
    Stateless agent for applying user context to chat responses.

    Design principles:
    - Receives context per-request, never stores it
    - Applies user's filtering logic, not platform recommendations
    - Transparent reasoning for all personalization decisions
    - Never auto-signs events; prepares unsigned for user approval

    Usage:
        context = UserContextForRequest(
            jurisdiction="city-san-rafael",
            interests=["housing"],
            filtering_instructions="aggressive on housing, ignore parking"
        )
        agent = ContextAgent(context)
        enhanced_result = agent.apply_context(original_result)
    """

    def __init__(self, user_context: Optional[Dict[str, Any]] = None):
        """
        Initialize with user context.

        Args:
            user_context: Dict matching UserContextForRequest fields
        """
        self.context: Optional[UserContextForRequest] = None
        self.constraints: Optional[FilteringConstraints] = None

        if user_context:
            try:
                self.context = UserContextForRequest(**user_context)
                self.constraints = parse_filtering_instructions(
                    self.context.filtering_instructions
                )
                logger.debug(
                    f"ContextAgent initialized: jurisdiction={self.context.jurisdiction}, "
                    f"interests={self.context.interests}, "
                    f"boost_topics={self.constraints.boost_topics}, "
                    f"ignore_topics={self.constraints.ignore_topics}"
                )
            except Exception as e:
                logger.warning(f"Failed to parse user context: {e}")
                self.context = None
                self.constraints = None

    @property
    def has_context(self) -> bool:
        """Check if valid context is available."""
        return self.context is not None

    def get_system_prompt_injection(self) -> str:
        """
        Generate context-aware system prompt additions.

        Returns string to inject into the LLM system prompt with
        user's personalization preferences.
        """
        if not self.context:
            return ""

        lines = ["## User Personalization Context"]

        # Location
        if self.context.location and self.context.location.neighborhood:
            lines.append(f"- User's neighborhood: {self.context.location.neighborhood}")
            lines.append("- When relevant, mention if something 'affects your neighborhood'")

        # Interests
        if self.context.interests:
            lines.append(f"- User's interests: {', '.join(self.context.interests)}")
            lines.append("- Prioritize information related to these topics")

        # Filtering instructions
        if self.constraints:
            if self.constraints.boost_topics:
                lines.append(f"- BOOST these topics: {', '.join(self.constraints.boost_topics)}")
            if self.constraints.ignore_topics:
                lines.append(f"- FILTER OUT these topics: {', '.join(self.constraints.ignore_topics)}")

        # History context
        if self.context.voice_history:
            lines.append(f"- User has {len(self.context.voice_history)} previous voice contributions")
        if self.context.commitment_history:
            lines.append(f"- User has {len(self.context.commitment_history)} previous commitments")

        lines.append("")
        lines.append("**IMPORTANT**: Explain your reasoning when showing personalized results.")
        lines.append("Use phrases like 'Since you're interested in X...' or 'Given your location in Y...'")

        return "\n".join(lines)

    def filter_results(
        self,
        results: List[Dict[str, Any]],
        topic_field: str = "topics"
    ) -> List[Dict[str, Any]]:
        """
        Apply filtering constraints to a list of results.

        Args:
            results: List of result dicts
            topic_field: Field containing topics/tags

        Returns:
            Filtered and reordered results
        """
        if not self.constraints:
            return results

        return apply_filtering_logic(self.constraints, results, topic_field)

    def annotate_with_location(
        self,
        results: List[Dict[str, Any]],
        lat_field: str = "lat",
        lng_field: str = "lng"
    ) -> List[Dict[str, Any]]:
        """
        Add location-based annotations to results.

        Args:
            results: List of result dicts
            lat_field: Field name for latitude
            lng_field: Field name for longitude

        Returns:
            Results annotated with neighborhood relevance
        """
        if not self.context or not self.context.location:
            return results

        return add_location_context(
            self.context.location, results, lat_field, lng_field
        )

    def get_reasoning(
        self,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        result_count: int = 0
    ) -> str:
        """
        Generate transparent personalization reasoning.

        Args:
            action: The action being performed
            parameters: Action parameters
            result_count: Number of results

        Returns:
            Human-readable explanation
        """
        if not self.context:
            return ""

        return generate_personalization_reasoning(
            self.context, action, parameters, result_count
        )

    def apply_to_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply context-aware enhancements to a chat response.

        This is the main entry point for context application.

        Args:
            response: Original chat router response

        Returns:
            Enhanced response with personalization
        """
        if not self.context:
            return response

        enhanced = response.copy()

        # Add personalization reasoning
        reasoning = self.get_reasoning(
            action=response.get("action", ""),
            parameters=response.get("parameters")
        )
        if reasoning:
            enhanced["personalization_reasoning"] = reasoning

        # If there are results in parameters, filter them
        params = enhanced.get("parameters")
        if params and isinstance(params, dict):
            # Handle different result field names
            for results_field in ["results", "meetings", "issues", "events"]:
                if results_field in params and isinstance(params[results_field], list):
                    # Filter by topics
                    filtered = self.filter_results(params[results_field])
                    # Annotate with location
                    annotated = self.annotate_with_location(filtered)
                    params[results_field] = annotated
                    break

        return enhanced


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    "ContextAgent",
    "UserContextForRequest",
    "UserNeighborhood",
    "FilteringConstraints",
    "parse_filtering_instructions",
    "apply_filtering_logic",
    "add_location_context",
    "generate_personalization_reasoning",
]
