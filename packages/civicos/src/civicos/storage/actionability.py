"""
Agenda item actionability classification via LLM.

Classifies agenda items as 'actionable', 'informational', or 'mixed' using
structured LLM output. Runs at ingestion time and stores permanently.

Actionable: Has a decision point where public input is meaningful
  (zoning variance, ordinance adoption, permit approval, budget appropriation)
Informational: Updates, presentations, procedural items
  (roll call, public expression, staff reports, minutes approval)
Mixed: Contains both decision and informational components
  (receive report AND approve budget, study session with optional direction)
"""

import json
import os
from typing import Dict, List, Optional, Any

import openai


def classify_actionability(
    items: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
) -> List[Dict[str, str]]:
    """
    Classify agenda items as actionable/informational/mixed.

    Args:
        items: List of dicts with at least 'title' key, optionally 'description'
        api_key: OpenAI API key (falls back to OPENAI_API_KEY env var)
        model: Model to use (gpt-4o-mini is cheap and sufficient)

    Returns:
        List of dicts: [{"actionability": str, "confidence": float, "reasoning": str}, ...]
        Same order and length as input items.
    """
    if not items:
        return []

    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY required for actionability classification")

    client = openai.OpenAI(api_key=api_key)

    # Build item descriptions for the prompt
    item_lines = []
    for i, item in enumerate(items):
        title = item.get("title", "Unknown")
        desc = item.get("description", "")
        line = f"{i+1}. {title}"
        if desc:
            line += f" — {desc[:200]}"
        item_lines.append(line)

    items_text = "\n".join(item_lines)

    prompt = f"""Classify each municipal agenda item as 'actionable', 'informational', or 'mixed'.

DEFINITIONS:
- actionable: Has a decision point (vote, approval, adoption, permit). Public input can influence outcome.
  Examples: zoning variance, ordinance adoption, use permit, budget appropriation, appeal hearing, contract award
- informational: No decision point. Updates, presentations, procedural items, general discussion.
  Examples: "Open Time for Public Expression", staff report, minutes approval, roll call, adjournment, presentation, update, study session (without direction)
- mixed: Contains both a decision component and an informational component.
  Examples: "Receive report and approve budget", study session with optional council direction

KEY RULES:
- "Open Time for Public Expression" is ALWAYS informational (no specific decision point)
- Consent calendar items are actionable (they are voted on as a batch)
- Study sessions are informational UNLESS they include a specific action item
- "Receive and file" items are informational
- Co-sponsorship applications with review/approval are actionable
- Presentations and updates are informational
- Public hearings are actionable

AGENDA ITEMS:
{items_text}

Return a JSON array with exactly {len(items)} objects, one per item, in the same order:
[
  {{"actionability": "actionable"|"informational"|"mixed", "confidence": 0.0-1.0, "reasoning": "brief reason"}}
]

Return ONLY the JSON array, no other text."""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a municipal governance expert. Classify agenda items accurately and concisely. Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=max(2000, len(items) * 80),
    )

    text = response.choices[0].message.content.strip()

    # Strip markdown fencing if present
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    results = json.loads(text)

    # Handle length mismatches gracefully
    if len(results) > len(items):
        results = results[: len(items)]
    while len(results) < len(items):
        results.append(
            {"actionability": "informational", "confidence": 0.0, "reasoning": "default (LLM returned too few)"}
        )

    # Validate values
    valid_values = {"actionable", "informational", "mixed"}
    for r in results:
        if r.get("actionability") not in valid_values:
            r["actionability"] = "informational"  # Safe default
        r["confidence"] = min(1.0, max(0.0, float(r.get("confidence", 0.5))))

    return results


def classify_actionability_batch(
    items: List[Dict[str, Any]],
    batch_size: int = 20,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
) -> List[Dict[str, str]]:
    """
    Classify agenda items in batches (for large backfills).

    Processes items in chunks of batch_size to stay within token limits.
    """
    all_results = []
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        results = classify_actionability(batch, api_key=api_key, model=model)
        all_results.extend(results)
    return all_results
