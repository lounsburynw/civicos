"""
Preparation Workflow State Schema

Defines the state object passed between preparation workflow nodes.
"""

from typing import TypedDict, List, Optional


class PreparationState(TypedDict):
    """
    State object passed between preparation workflow nodes.

    Flow: load_item → gather_context → find_allies → generate_talking_points → compile_logistics → format
    """
    # Input context
    agenda_item_id: str
    jurisdiction: str
    user_id: Optional[str]
    db_path: str

    # Item data (loaded)
    agenda_item: Optional[dict]  # The agenda item being prepared for
    meeting: Optional[dict]  # Parent meeting

    # Context (gathered)
    topic: str  # Extracted topic from agenda item
    regulatory_context: dict  # Federal, state, local context
    historical_decisions: List[dict]  # Past decisions on similar topics

    # Allies (discovered)
    allies: List[dict]  # Others who have voiced or follow related items

    # Talking points (generated)
    talking_points: List[str]  # Generated talking points

    # Logistics (compiled)
    logistics: dict  # Meeting time, location, comment procedures

    # Final output
    preparation: dict  # Formatted preparation materials

    # Workflow metadata
    status: str  # loading, gathering, finding_allies, generating, compiling, formatting, complete
    created_at: str
    error: Optional[str]
