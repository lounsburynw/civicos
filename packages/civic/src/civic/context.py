"""
Context Module - what_applies() implementation

Provides regulatory context for topics using legislative_context_cache.
"""

from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RegulatoryStack:
    """Regulatory context for a topic."""
    topic: str
    jurisdiction: str
    federal: List[dict] = field(default_factory=list)
    state: List[dict] = field(default_factory=list)
    local: List[dict] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=datetime.now)


# Topic mapping - canonical topics to state_key
TOPIC_MAP = {
    "housing": "housing",
    "zoning": "housing",
    "transportation": "transportation",
    "transit": "transportation",
    "environment": "environment",
    "climate": "environment",
    "budget": "budget",
    "finance": "budget",
    "education": "education",
    "schools": "education",
}


def _extract_state_from_jurisdiction(jurisdiction_id: str) -> Optional[str]:
    """Extract state from jurisdiction_id (e.g., 'city-san-rafael' -> 'california')."""
    if not jurisdiction_id:
        return None

    # All current jurisdictions are in California
    # Handle multiple naming conventions:
    # - city-san-rafael (canonical)
    # - san-rafael-ca (alternative)
    # - county-marin
    if jurisdiction_id.startswith(("city-", "county-")):
        return "california"

    # Handle state suffix patterns (e.g., san-rafael-ca)
    if jurisdiction_id.endswith("-ca"):
        return "california"

    # Handle common California city names
    ca_cities = ["san-rafael", "berkeley", "oakland", "hayward", "santa-rosa"]
    for city in ca_cities:
        if city in jurisdiction_id.lower():
            return "california"

    return None


def get_regulatory_context(
    jurisdiction: str,
    topic: str,
    location: str = None
) -> RegulatoryStack:
    """
    Get regulatory stack for a topic.

    Uses legislative_context_cache for state bills and federal programs.

    Args:
        jurisdiction: City/jurisdiction ID
        topic: Topic to search
        location: Optional location for local rules

    Returns:
        RegulatoryStack with federal, state, local context
    """
    federal = []
    state = []
    local = []

    # Normalize topic to state_key
    topic_lower = topic.lower()
    state_key = TOPIC_MAP.get(topic_lower, topic_lower)

    # Extract state from jurisdiction
    state_name = _extract_state_from_jurisdiction(jurisdiction)

    if not state_name:
        return RegulatoryStack(
            topic=topic,
            jurisdiction=jurisdiction,
            federal=[{"note": "Unknown jurisdiction state"}],
            state=[{"note": "Unknown jurisdiction state"}],
            local=[{"note": "Local ordinances not yet supported"}],
        )

    try:
        # Import the legislative cache from civic_services
        from civic_services.legislative.legislative_context_cache import legislative_cache

        # Load legislative data for this state/topic
        legislative_data = legislative_cache.get(state_name, state_key)

        if legislative_data:
            # Extract state legislation
            state_legislation = legislative_data.get("state_legislation", {})
            for bill_id, bill_data in state_legislation.items():
                state.append({
                    "type": "bill",
                    "id": bill_id,
                    "bill": bill_data.get("bill", bill_id),
                    "title": bill_data.get("title", ""),
                    "leverage_point": bill_data.get("leverage_point", ""),
                    "keywords": bill_data.get("keywords", []),
                })

            # Extract federal programs
            federal_programs = legislative_data.get("federal_programs", {})
            for prog_id, prog_data in federal_programs.items():
                federal.append({
                    "type": "program",
                    "id": prog_id,
                    "program_name": prog_data.get("program_name", prog_id),
                    "agency": prog_data.get("agency", ""),
                    "leverage_point": prog_data.get("leverage_point", ""),
                    "keywords": prog_data.get("keywords", []),
                })

        if not state:
            state = [{"note": f"No state bills for topic '{state_key}'"}]
        if not federal:
            federal = [{"note": f"No federal programs for topic '{state_key}'"}]

    except ImportError:
        state = [{"note": "legislative_context_cache not available"}]
        federal = [{"note": "legislative_context_cache not available"}]
    except Exception as e:
        state = [{"note": f"Error loading state legislation: {e}"}]
        federal = [{"note": f"Error loading federal programs: {e}"}]

    # Search local municipal code
    try:
        from civic._internal.meetings.embeddings import CivicEmbeddings

        embedder = CivicEmbeddings(jurisdiction)

        if embedder.has_municipal_code():
            # Search municipal code for relevant ordinances
            results = embedder.search_municipal_code(topic, top_k=5)

            for result in results:
                # Only include results with reasonable relevance (score > 0)
                if result.score > 0:
                    local.append({
                        "type": "ordinance",
                        "id": result.document_id,
                        "section": result.metadata.get("section", ""),
                        "section_title": result.metadata.get("section_title", ""),
                        "chapter": result.metadata.get("chapter", ""),
                        "chapter_title": result.metadata.get("chapter_title", ""),
                        "title_number": result.metadata.get("title_number", ""),
                        "title_name": result.metadata.get("title_name", ""),
                        "text_preview": result.text[:300] if result.text else "",
                        "relevance_score": round(result.score, 3),
                    })

        if not local:
            local = [{"note": f"No local ordinances found for topic '{topic}'"}]

    except ImportError:
        local = [{"note": "Municipal code search not available"}]
    except Exception as e:
        local = [{"note": f"Error searching municipal code: {e}"}]

    return RegulatoryStack(
        topic=topic,
        jurisdiction=jurisdiction,
        federal=federal,
        state=state,
        local=local,
    )
