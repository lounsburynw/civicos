"""
Complaint-to-Event Matching Algorithm

Phase 1: Keyword-based matching with temporal scoring
Reuses pattern from legislative_enrichment.py (0.03ms, $0 cost)
"""

import json
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timezone
from pathlib import Path
from glob import glob

logger = logging.getLogger(__name__)

# Issue type keywords for matching (similar to TOPIC_ENRICHMENT_POLICY)
ISSUE_TYPE_KEYWORDS = {
    "housing": [
        "housing", "rent", "affordable", "eviction", "zoning", "ADU",
        "development", "apartment", "landlord", "tenant", "homeless",
        "building", "construction", "permit", "variance", "land use"
    ],
    "transportation": [
        "transit", "bus", "bike", "pedestrian", "traffic", "road",
        "highway", "parking", "sidewalk", "crosswalk", "speed limit",
        "BART", "bridge", "tunnel", "rail", "transport"
    ],
    "environment": [
        "climate", "pollution", "air quality", "water", "green", "park",
        "tree", "wildfire", "flood", "drought", "emissions", "waste",
        "recycling", "compost", "energy", "solar", "sustainability"
    ],
    "infrastructure": [
        "pothole", "repair", "maintenance", "street light", "sewer",
        "water", "utilities", "roads", "bridge", "pavement", "curb",
        "drainage", "storm drain", "pipes", "infrastructure"
    ],
    "public_safety": [
        "police", "fire", "emergency", "crime", "safety", "911",
        "response", "patrol", "security", "violence", "accident",
        "hazard", "danger", "illegal", "noise"
    ],
    "community": [
        "community", "neighborhood", "local", "resident", "public",
        "meeting", "event", "program", "service", "recreation",
        "library", "school", "education", "health", "senior"
    ]
}

# Match score thresholds
MINIMUM_MATCH_SCORE = 25  # Require at least 25 points to be considered a match
HIGH_CONFIDENCE_THRESHOLD = 60  # Scores above 60 are high-confidence matches


def match_issue_to_events(
    complaint: Dict,
    jurisdiction_id: Optional[str] = None,
    max_matches: int = 5
) -> List[Tuple[Dict, float, str]]:
    """
    Match a complaint to relevant civic events.

    Args:
        complaint: Complaint dict with 'description', 'issue_type', 'jurisdiction_id'
        jurisdiction_id: Optional override for jurisdiction (defaults to complaint's)
        max_matches: Maximum number of matches to return

    Returns:
        List of (event_dict, match_score, match_reason) tuples, sorted by score
    """
    jurisdiction_id = jurisdiction_id or complaint.get("jurisdiction_id")
    if not jurisdiction_id:
        logger.debug("No jurisdiction_id provided for complaint matching")
        return []

    # Load events for this jurisdiction
    events = _load_jurisdiction_events(jurisdiction_id)
    if not events:
        logger.debug(f"No events found for jurisdiction {jurisdiction_id}")
        return []

    # Score each event
    scored_matches = []
    for event in events:
        score, reason = _score_event(complaint, event)

        if score >= MINIMUM_MATCH_SCORE:
            scored_matches.append((event, score, reason))

    # Sort by score (highest first) and limit results
    scored_matches.sort(key=lambda x: x[1], reverse=True)
    matches = scored_matches[:max_matches]

    logger.info(
        f"Matched complaint to {len(matches)} events "
        f"(out of {len(events)} total events)"
    )

    return matches


def _score_event(complaint: Dict, event: Dict) -> Tuple[float, str]:
    """
    Score an event's relevance to a complaint.

    Scoring algorithm:
    - Keyword match: 10 points per keyword
    - Project type match: 20 points
    - Temporal proximity: up to 15 points
    - Description overlap: 10 points

    Returns:
        (score, reason) tuple
    """
    score = 0
    reasons = []

    complaint_text = complaint.get("description", "").lower()
    complaint_issue_type = complaint.get("issue_type", "")

    event_title = event.get("title", "").lower()
    event_description = event.get("description", "").lower()
    event_project_type = event.get("project_type", "")
    event_text = event_title + " " + event_description

    # 1. Keyword matching (10 points per keyword)
    if complaint_issue_type in ISSUE_TYPE_KEYWORDS:
        keywords = ISSUE_TYPE_KEYWORDS[complaint_issue_type]
        keyword_matches = sum(1 for kw in keywords if kw.lower() in event_text)

        if keyword_matches > 0:
            keyword_score = keyword_matches * 10
            score += keyword_score
            reasons.append(f"{keyword_matches} keyword matches")

    # 2. Project type match (20 points)
    if complaint_issue_type == event_project_type:
        score += 20
        reasons.append(f"project type: {event_project_type}")

    # 3. Temporal proximity (up to 15 points)
    # Events happening sooner are more relevant
    if event.get("when"):
        try:
            event_date = datetime.fromisoformat(event["when"].replace('Z', '+00:00'))
            if event_date.tzinfo is None:
                event_date = event_date.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            days_until = (event_date - now).days

            if 0 <= days_until <= 7:
                score += 15
                reasons.append("happening within 1 week")
            elif 7 < days_until <= 30:
                score += 10
                reasons.append("happening within 1 month")
            elif 30 < days_until <= 90:
                score += 5
                reasons.append("happening within 3 months")

        except (ValueError, AttributeError) as e:
            logger.debug(f"Could not parse event date: {e}")

    # 4. Description overlap (10 points for significant overlap)
    # Check if any significant words from complaint appear in event
    complaint_words = set(w for w in complaint_text.split() if len(w) > 4)
    event_words = set(w for w in event_text.split() if len(w) > 4)
    overlap = complaint_words & event_words

    if len(overlap) >= 3:
        score += 10
        reasons.append(f"description overlap: {len(overlap)} words")

    # 5. Agenda item matching (NEW - for committee meetings with specific topics)
    # Check if event has parsed agenda items that match the complaint
    agenda_expansion = event.get("agenda_expansion", {})
    if agenda_expansion and agenda_expansion.get("actionable_items"):
        agenda_items = agenda_expansion["actionable_items"]

        for item in agenda_items:
            item_score = 0
            item_reasons = []

            # Check if agenda item project types match complaint issue type
            item_project_types = item.get("project_types", [])
            if complaint_issue_type in item_project_types:
                item_score += 20
                item_reasons.append(f"agenda item: {item.get('title', 'Unknown')[:40]}")

            # Check keywords in agenda item text
            item_text = (item.get("title", "") + " " + item.get("description", "")).lower()
            if complaint_issue_type in ISSUE_TYPE_KEYWORDS:
                keywords = ISSUE_TYPE_KEYWORDS[complaint_issue_type]
                keyword_matches = sum(1 for kw in keywords if kw.lower() in item_text)

                if keyword_matches > 0:
                    item_score += keyword_matches * 5  # 5 points per keyword in agenda item
                    item_reasons.append(f"{keyword_matches} keywords in agenda")

            # Add best matching agenda item to total score
            if item_score > 0:
                score += item_score
                reasons.extend(item_reasons)
                break  # Only count the best matching agenda item

    # Generate reason string
    reason = ", ".join(reasons) if reasons else "no clear match"

    return score, reason


def _load_jurisdiction_events(jurisdiction_id: str) -> List[Dict]:
    """
    Load all events for a jurisdiction from data/events/*.json files.

    Args:
        jurisdiction_id: e.g., "city-berkeley"

    Returns:
        List of event dicts
    """
    events = []
    events_dir = Path("data/events")

    if not events_dir.exists():
        logger.debug(f"Events directory not found: {events_dir}")
        return []

    # Find all event files for this jurisdiction
    pattern = str(events_dir / f"events_{jurisdiction_id}_*.json")
    event_files = glob(pattern)

    if not event_files:
        logger.debug(f"No event files found for pattern: {pattern}")
        return []

    # Load most recent file
    event_files.sort(reverse=True)
    latest_file = event_files[0]

    try:
        with open(latest_file, 'r') as f:
            data = json.load(f)
            events = data.get("events", [])
            logger.debug(f"Loaded {len(events)} events from {latest_file}")
    except Exception as e:
        logger.error(f"Error loading events from {latest_file}: {e}")

    return events


def get_match_statistics(matches: List[Tuple[Dict, float, str]]) -> Dict:
    """
    Get statistics about match results (for debugging/validation).

    Args:
        matches: List of (event, score, reason) tuples

    Returns:
        Statistics dict
    """
    if not matches:
        return {
            "total_matches": 0,
            "high_confidence": 0,
            "average_score": 0.0
        }

    scores = [score for _, score, _ in matches]

    return {
        "total_matches": len(matches),
        "high_confidence": sum(1 for s in scores if s >= HIGH_CONFIDENCE_THRESHOLD),
        "average_score": sum(scores) / len(scores),
        "max_score": max(scores),
        "min_score": min(scores)
    }
