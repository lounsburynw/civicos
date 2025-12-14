"""
Legislative Context Enrichment - Enriches civic opportunities with federal/state context.

Multi-dimensional context enrichment following criticality framework:
1. Community context (exponential value via network formation)
2. Financial context (concrete stakes)
3. Legislative context (policy legitimacy)
4. Temporal context (urgency)
5. Geographic context (personalization)

STOP at 3 pieces to avoid information overload.
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone
import re

try:
    from src.legislative_context_cache import legislative_cache
except ModuleNotFoundError:
    from legislative_context_cache import legislative_cache

logger = logging.getLogger(__name__)

# Topic enrichment policy - which topics get legislative context
TOPIC_ENRICHMENT_POLICY = {
    "housing": {"enrich": True, "state_key": "housing"},
    "zoning": {"enrich": True, "state_key": "housing"},  # Zoning is housing-related
    "transportation": {"enrich": True, "state_key": "transportation"},
    "transit": {"enrich": True, "state_key": "transportation"},  # Transit is transportation-related
    "environment": {"enrich": True, "state_key": "environment"},
    "climate": {"enrich": True, "state_key": "environment"},  # Climate is environment-related
    "budget": {"enrich": True, "state_key": "budget"},
    "finance": {"enrich": True, "state_key": "budget"},  # Finance is budget-related
    "education": {"enrich": True, "state_key": "education"},
    "schools": {"enrich": True, "state_key": "education"},  # Schools is education-related
    "development": {"enrich": False},  # Too broad
    "public_safety": {"enrich": False},  # Rarely state-mandated
    "community": {"enrich": False}  # Too broad
}


def enrich_opportunity(opportunity: dict) -> Optional[dict]:
    """
    Enrich a single civic opportunity with legislative context.

    Returns legislative_context object if relevant, None otherwise.
    Focuses only on legislative dimension (other dimensions like community,
    financial, temporal handled elsewhere).

    Args:
        opportunity: CivicEvent dict from schema

    Returns:
        legislative_context dict matching schema, or None
    """
    # Handle both old (string) and new (array) project_type/project_types format
    project_types = opportunity.get("project_types", opportunity.get("project_type", []))
    if isinstance(project_types, str):
        project_types = [project_types]

    jurisdiction_id = opportunity.get("jurisdiction", {}).get("id", "")

    # Check if ANY of the project types should be enriched
    # Use the first enrichable type for legislative data lookup
    enrichable_type = None
    for ptype in project_types:
        enrichment_policy = TOPIC_ENRICHMENT_POLICY.get(ptype, {})
        if enrichment_policy.get("enrich", False):
            enrichable_type = ptype
            break

    if not enrichable_type:
        logger.debug(f"Skipping legislative enrichment for {project_types} (policy: no enrichable types)")
        return None

    # Extract state from jurisdiction_id (e.g., "city-berkeley" -> "california")
    state = extract_state_from_jurisdiction(jurisdiction_id)
    if not state:
        logger.debug(f"Could not extract state from jurisdiction {jurisdiction_id}")
        return None

    # Load legislative context from cache using the enrichable type
    enrichment_policy = TOPIC_ENRICHMENT_POLICY.get(enrichable_type, {})
    topic = enrichment_policy.get("state_key", enrichable_type)
    legislative_data = legislative_cache.get(state, topic)

    if not legislative_data:
        logger.debug(f"No legislative context available for {state}/{topic}")
        return None

    # Find most relevant bills and programs
    relevant_bills = find_relevant_bills(legislative_data, opportunity)
    relevant_programs = find_relevant_programs(legislative_data, opportunity)

    if not relevant_bills and not relevant_programs:
        logger.debug(f"No relevant legislative context for opportunity {opportunity.get('id')}")
        return None

    # Build legislative_context object
    legislative_context = {
        "state_legislation_refs": [bill["id"] for bill in relevant_bills],
        "federal_program_refs": [prog["id"] for prog in relevant_programs],
        "relevance_summary": generate_relevance_summary(
            relevant_bills,
            relevant_programs,
            opportunity
        )
    }

    logger.info(
        f"Enriched opportunity {opportunity.get('id')} with "
        f"{len(relevant_bills)} bills, {len(relevant_programs)} programs"
    )

    return legislative_context


def find_relevant_bills(legislative_data: dict, opportunity: dict) -> List[dict]:
    """
    Find state bills relevant to this opportunity.

    Selection criteria:
    1. Keyword match with opportunity title/description
    2. Local implementation required
    3. Clear local control point
    4. Timing relevance (not expired)

    Returns up to 2 most relevant bills.
    """
    state_legislation = legislative_data.get("state_legislation", {})
    if not state_legislation:
        return []

    opportunity_text = (
        opportunity.get("title", "") + " " +
        opportunity.get("description", "") + " " +
        opportunity.get("impact_summary", "")
    ).lower()

    scored_bills = []

    for bill_id, bill_data in state_legislation.items():
        score = 0

        # Keyword matching
        keywords = bill_data.get("keywords", [])
        keyword_matches = sum(1 for kw in keywords if kw.lower() in opportunity_text)
        score += keyword_matches * 10

        # Local implementation bonus
        if bill_data.get("local_implementation_required"):
            score += 20

        # Clear local control point
        if bill_data.get("leverage_point") and len(bill_data["leverage_point"]) < 150:
            score += 15

        # Timing relevance
        if passes_timing_test(bill_data):
            score += 10

        if score > 0:
            scored_bills.append({
                "id": bill_id,
                "score": score,
                **bill_data
            })

    # Sort by score and return top 2
    scored_bills.sort(key=lambda x: x["score"], reverse=True)
    return scored_bills[:2]


def find_relevant_programs(legislative_data: dict, opportunity: dict) -> List[dict]:
    """
    Find federal programs relevant to this opportunity.

    Selection criteria:
    1. Keyword match with opportunity
    2. Clear local control point (leverage_point)
    3. Topic match (housing programs for housing events)

    Returns up to 2 most relevant programs.
    """
    federal_programs = legislative_data.get("federal_programs", {})
    if not federal_programs:
        return []

    opportunity_text = (
        opportunity.get("title", "") + " " +
        opportunity.get("description", "") + " " +
        opportunity.get("impact_summary", "")
    ).lower()

    scored_programs = []

    for program_id, program_data in federal_programs.items():
        score = 0

        # Keyword matching
        keywords = program_data.get("keywords", [])
        keyword_matches = sum(1 for kw in keywords if kw.lower() in opportunity_text)
        score += keyword_matches * 10

        # Clear local control point (use leverage_point field)
        if program_data.get("leverage_point") or program_data.get("local_control_point"):
            score += 15

        # Topic match bonus - if this is a housing event and program is housing-related
        # Give a baseline score so programs can be suggested even without keyword matches
        project_type = opportunity.get("project_type", "")
        if project_type in ["housing", "zoning"] and any(
            kw in ["affordable housing", "housing", "community development"]
            for kw in keywords
        ):
            score += 20  # High score for topic match

        if score > 0:
            scored_programs.append({
                "id": program_id,
                "score": score,
                **program_data
            })

    # Sort by score and return top 2
    scored_programs.sort(key=lambda x: x["score"], reverse=True)
    return scored_programs[:2]


def passes_timing_test(bill_data: dict) -> bool:
    """Check if bill is still timing-relevant (not expired)"""
    deadline = bill_data.get("local_deadline")
    if not deadline:
        return True  # No deadline = always relevant

    # Skip timing test for "Ongoing" and "Pending" deadlines
    if deadline in ["Ongoing", "Pending", "Pending enactment"]:
        return True

    try:
        # Parse deadline and make timezone-aware if needed
        deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
        if deadline_dt.tzinfo is None:
            # Assume UTC if no timezone specified
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)

        return deadline_dt > datetime.now(timezone.utc)
    except (ValueError, AttributeError):
        return True  # Parse error = assume relevant


def extract_state_from_jurisdiction(jurisdiction_id: str) -> Optional[str]:
    """
    Extract state from jurisdiction_id.

    Examples:
        "city-berkeley" -> "california"
        "city-san-rafael" -> "california"
        "county-marin" -> "california"

    For now, hardcoded to California (foundation's initial region).
    TODO: Add state detection when expanding beyond California.
    """
    # All current jurisdictions are in California
    if jurisdiction_id and jurisdiction_id.startswith(("city-", "county-")):
        return "california"

    return None


def generate_relevance_summary(
    bills: List[dict],
    programs: List[dict],
    opportunity: dict
) -> str:
    """
    Generate 1-2 sentence AI relevance summary.

    Format: "This [meeting/hearing] relates to [state bill] which [local leverage point].
    [City] controls [specific decision]."

    For now, using template-based generation. In Month 2, replace with LLM.
    """
    if not bills and not programs:
        return ""

    summaries = []

    # Bill summary
    if bills:
        top_bill = bills[0]
        bill_name = top_bill.get("bill", "state legislation")
        leverage = top_bill.get("leverage_point", "local implementation")
        summaries.append(f"Related to {bill_name}: {leverage}")

    # Program summary
    if programs:
        top_program = programs[0]
        program_name = top_program.get("program_name", "federal program")
        control = top_program.get("leverage_point") or top_program.get("local_control_point", "local funding decisions")
        # Shorten control point if too long
        if len(control) > 80:
            control = control[:77] + "..."
        summaries.append(f"{program_name}: {control}")

    return " ".join(summaries[:2])  # Max 2 sentences


def enrich_opportunities_batch(opportunities: List[dict]) -> List[dict]:
    """
    Enrich multiple opportunities in batch.

    Adds legislative_context field to each opportunity dict.
    Returns modified opportunities (does not mutate originals).
    """
    enriched = []
    stats = {"enriched": 0, "skipped": 0, "errors": 0}

    for opp in opportunities:
        try:
            legislative_context = enrich_opportunity(opp)

            if legislative_context:
                enriched_opp = {**opp, "legislative_context": legislative_context}
                enriched.append(enriched_opp)
                stats["enriched"] += 1
            else:
                enriched.append(opp)
                stats["skipped"] += 1

        except Exception as e:
            logger.error(f"Error enriching opportunity {opp.get('id')}: {e}")
            enriched.append(opp)
            stats["errors"] += 1

    logger.info(
        f"Batch enrichment complete: {stats['enriched']} enriched, "
        f"{stats['skipped']} skipped, {stats['errors']} errors"
    )

    return enriched
