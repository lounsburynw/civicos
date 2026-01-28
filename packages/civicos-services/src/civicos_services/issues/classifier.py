"""
LLM-based issue type classification service for 311 issues.

Classifies issue title + description into a fixed, jurisdiction-agnostic taxonomy
using the LLM provider abstraction. Designed for both real-time ingestion and
batch backfill.

Taxonomy is defined in civicos.issues.classify (core domain).
This module provides the LLM service layer.

Usage:
    from civicos_services.issues.classifier import classify_issue_type, classify_issue_types_batch

    # Single issue
    issue_type = classify_issue_type("Pothole on Main St", "Large pothole near crosswalk")

    # Batch (more efficient)
    issues = [{"id": "1", "title": "...", "description": "..."}, ...]
    types = classify_issue_types_batch(issues)
"""

import json
import logging
from typing import Dict, List

from civicos.issues.classify import VALID_ISSUE_TYPES, _build_taxonomy_text

from ..core.llm_provider import get_provider

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You classify 311/municipal issues into standardized types.
Given an issue title and optional description, return ONLY the issue type key from the taxonomy.
Respond with a single word — the type key. No explanation."""

_BATCH_SYSTEM_PROMPT = """You classify 311/municipal issues into standardized types.
Given a JSON array of issues (each with "id", "title", "description"), classify each into one type from the taxonomy.
Return a JSON object mapping each issue id to its type key. No explanation, just valid JSON."""


def classify_issue_type(
    title: str,
    description: str = "",
) -> str:
    """
    Classify a single issue into the taxonomy using an LLM.

    Args:
        title: Issue title/summary
        description: Issue description (optional)

    Returns:
        Issue type key from ISSUE_TYPE_TAXONOMY (e.g., "pothole", "graffiti")
        Falls back to "other" on error.
    """
    try:
        provider = get_provider('anthropic')
    except Exception:
        logger.warning("LLM provider not available, falling back to 'other'")
        return "other"

    taxonomy_text = _build_taxonomy_text()
    user_content = f"{taxonomy_text}\n\nTitle: {title}"
    if description:
        user_content += f"\nDescription: {description[:500]}"

    try:
        response = provider.complete(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            model="claude-3-5-haiku-20241022",
            max_tokens=20,
            temperature=0,
        )
        result = response.content.strip().lower()
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
) -> Dict[str, str]:
    """
    Classify multiple issues in batches using an LLM.

    Args:
        issues: List of dicts with "id", "title", and optional "description"
        batch_size: Issues per API call (default: 50)

    Returns:
        Dict mapping issue id -> issue type key
    """
    try:
        provider = get_provider('anthropic')
    except Exception:
        logger.warning("LLM provider not available, returning all 'other'")
        return {issue["id"]: "other" for issue in issues}

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
            response = provider.complete(
                messages=[
                    {"role": "system", "content": _BATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                temperature=0,
            )
            raw_text = response.content.strip()

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
            # Fall back to single classification for this batch
            for issue in batch:
                results[str(issue["id"])] = classify_issue_type(
                    issue.get("title", ""),
                    issue.get("description", ""),
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
