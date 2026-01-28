"""
LLM-based issue type classification for 311 issues.

Classifies issue title + description into a fixed, jurisdiction-agnostic taxonomy
using Claude Haiku. Designed for both real-time ingestion and batch backfill.

Usage:
    from civicos.issues.classify import classify_issue_type, classify_issue_types_batch

    # Single issue
    issue_type = classify_issue_type("Pothole on Main St", "Large pothole near crosswalk")

    # Batch (more efficient)
    issues = [{"title": "...", "description": "..."}, ...]
    types = classify_issue_types_batch(issues)
"""

import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Jurisdiction-agnostic taxonomy of 311 issue types.
# Keys are stored in the database; values are human-readable descriptions
# sent to the LLM for classification context.
ISSUE_TYPE_TAXONOMY: Dict[str, str] = {
    "pothole": "Potholes, road surface damage, pavement deterioration",
    "traffic_signal": "Traffic signals, stop signs, road signs, lane markings, crosswalk signals",
    "sidewalk": "Sidewalk cracks, damage, trip hazards, ADA accessibility",
    "streetlight": "Streetlight outages, broken lights, lighting issues",
    "stormwater": "Storm drains, flooding, drainage problems, clogged gutters",
    "graffiti": "Graffiti on public or private property, tagging, vandalism",
    "illegal_dumping": "Illegal dumping, litter, abandoned trash, debris",
    "parking": "Parking violations, broken meters, abandoned vehicles, towing",
    "parks": "Parks, playgrounds, recreation facilities, sports fields, benches",
    "trees_vegetation": "Trees, landscaping, overgrown vegetation, medians, roadside plants",
    "street_cleaning": "Street sweeping, road debris, general cleanliness",
    "water_sewer": "Water main breaks, sewer issues, utility infrastructure, manhole covers",
    "noise": "Noise complaints, construction noise, loud music",
    "fire_hazard": "Vegetation fire hazards, fire prevention, campsite hazards",
    "animal_control": "Stray animals, wildlife, animal-related complaints",
    "property_maintenance": "Blight, code violations, unmaintained property, building issues",
    "public_safety": "General safety hazards, dangerous conditions, crime-related",
    "other": "Issues that do not clearly fit any other category",
}

# All valid issue type keys
VALID_ISSUE_TYPES = set(ISSUE_TYPE_TAXONOMY.keys())

_SYSTEM_PROMPT = """You classify 311/municipal issues into standardized types.
Given an issue title and optional description, return ONLY the issue type key from the taxonomy.
Respond with a single word — the type key. No explanation."""

_BATCH_SYSTEM_PROMPT = """You classify 311/municipal issues into standardized types.
Given a JSON array of issues (each with "id", "title", "description"), classify each into one type from the taxonomy.
Return a JSON object mapping each issue id to its type key. No explanation, just valid JSON."""


def _build_taxonomy_text() -> str:
    """Format taxonomy for LLM context."""
    lines = ["Issue type taxonomy:"]
    for key, desc in ISSUE_TYPE_TAXONOMY.items():
        lines.append(f"- {key}: {desc}")
    return "\n".join(lines)


def classify_issue_type(
    title: str,
    description: str = "",
    api_key: Optional[str] = None,
) -> str:
    """
    Classify a single issue into the taxonomy using Claude Haiku.

    Args:
        title: Issue title/summary
        description: Issue description (optional)
        api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)

    Returns:
        Issue type key from ISSUE_TYPE_TAXONOMY (e.g., "pothole", "graffiti")
        Falls back to "other" on error.
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic package not installed, falling back to 'other'")
        return "other"

    client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    taxonomy_text = _build_taxonomy_text()
    user_content = f"{taxonomy_text}\n\nTitle: {title}"
    if description:
        user_content += f"\nDescription: {description[:500]}"

    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=20,
            temperature=0,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        result = response.content[0].text.strip().lower()
        if result in VALID_ISSUE_TYPES:
            return result
        logger.warning(f"LLM returned invalid type '{result}' for '{title[:60]}', using 'other'")
        return "other"
    except Exception as e:
        logger.error(f"Classification failed for '{title[:60]}': {e}")
        return "other"


def classify_issue_types_batch(
    issues: List[Dict[str, str]],
    batch_size: int = 50,
    api_key: Optional[str] = None,
) -> Dict[str, str]:
    """
    Classify multiple issues in batches using Claude Haiku.

    Args:
        issues: List of dicts with "id", "title", and optional "description"
        batch_size: Issues per API call (default: 50)
        api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)

    Returns:
        Dict mapping issue id -> issue type key
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic package not installed, returning all 'other'")
        return {issue["id"]: "other" for issue in issues}

    client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    taxonomy_text = _build_taxonomy_text()
    results: Dict[str, str] = {}

    for i in range(0, len(issues), batch_size):
        batch = issues[i : i + batch_size]
        batch_payload = []
        for issue in batch:
            entry = {
                "id": str(issue["id"]),
                "title": issue.get("title", "")[:200],
            }
            desc = issue.get("description", "")
            if desc:
                entry["description"] = desc[:300]
            batch_payload.append(entry)

        user_content = (
            f"{taxonomy_text}\n\n"
            f"Classify these issues:\n{json.dumps(batch_payload, ensure_ascii=False)}"
        )

        try:
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                temperature=0,
                system=_BATCH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw_text = response.content[0].text.strip()

            # Parse JSON response — handle markdown code fences
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            batch_results = json.loads(raw_text)

            for issue in batch:
                issue_id = str(issue["id"])
                classified = batch_results.get(issue_id, "other").lower()
                if classified in VALID_ISSUE_TYPES:
                    results[issue_id] = classified
                else:
                    logger.warning(
                        f"Invalid type '{classified}' for issue {issue_id}, using 'other'"
                    )
                    results[issue_id] = "other"

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse batch response (batch {i // batch_size + 1}): {e}")
            logger.debug(f"Raw response: {raw_text[:500]}")
            # Fall back to single classification for this batch
            for issue in batch:
                results[str(issue["id"])] = classify_issue_type(
                    issue.get("title", ""),
                    issue.get("description", ""),
                    api_key=api_key,
                )
        except Exception as e:
            logger.error(f"Batch classification failed (batch {i // batch_size + 1}): {e}")
            for issue in batch:
                results[str(issue["id"])] = "other"

        logger.info(
            f"Classified batch {i // batch_size + 1}/{(len(issues) + batch_size - 1) // batch_size} "
            f"({len(results)}/{len(issues)} total)"
        )

    return results
