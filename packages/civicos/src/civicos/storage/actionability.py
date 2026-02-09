"""
Agenda item eligibility classification via LLM.

Classifies agenda items along two independent axes:
  stance_eligible:  Has a decision point where support/oppose is meaningful
                    (vote, approval, adoption, permit, resolution)
  comment_eligible: Public input is valuable regardless of whether there's a vote
                    (policy discussions, study sessions, options presentations)

Both false = purely procedural (roll call, adjournment, Open Time for Public Expression)
"""

import json
import os
from typing import Dict, List, Optional, Any

import openai


def classify_agenda_items(
    items: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
) -> List[Dict[str, Any]]:
    """
    Classify agenda items for stance and comment eligibility.

    Args:
        items: List of dicts with at least 'title' key, optionally 'description'
        api_key: OpenAI API key (falls back to OPENAI_API_KEY env var)
        model: Model to use (gpt-4o-mini is cheap and sufficient)

    Returns:
        List of dicts: [{"stance_eligible": bool, "comment_eligible": bool, "reasoning": str}, ...]
        Same order and length as input items.
    """
    if not items:
        return []

    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY required for agenda item classification")

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

    prompt = f"""For each municipal agenda item, determine two independent flags:

1. stance_eligible (boolean): Is there a decision point where taking a position (support/oppose) is meaningful?
   TRUE when: vote, approval, adoption, permit, resolution, ordinance, appeal, contract award, consent calendar items
   FALSE when: no vote or decision — presentations, updates, discussions, study sessions, reports

2. comment_eligible (boolean): Is public input valuable on this item?
   TRUE when: public can meaningfully contribute perspective — policy discussions, study sessions with options, presentations seeking feedback, proposals under review, any item with a decision point
   FALSE when: purely procedural — roll call, adjournment, "Open Time for Public Expression", minutes approval, verbal updates with no discussion, scheduling items

These are INDEPENDENT axes. An item can be:
- stance=true,  comment=true:  Use permit hearing, ordinance adoption, budget appropriation
- stance=false, comment=true:  Housing study session, bikeway options presentation, fiscal sustainability discussion
- stance=false, comment=false: Open Time for Public Expression, roll call, verbal update, adjournment
- stance=true,  comment=true:  (stance=true almost always implies comment=true)

KEY RULES:
- "Open Time for Public Expression" → stance=false, comment=false (no specific topic)
- Consent calendar items → stance=true, comment=true (voted on as a batch)
- Study sessions → stance=false, comment=true (shaping direction, no vote)
- Presentations with options/discussion → stance=false, comment=true
- "Receive and file" → stance=false, comment=false
- Public hearings → stance=true, comment=true
- Goals discussions → stance=false, comment=true
- Verbal updates → stance=false, comment=false
- Co-sponsorship applications → stance=true, comment=true

AGENDA ITEMS:
{items_text}

Return a JSON array with exactly {len(items)} objects, one per item, in the same order:
[
  {{"stance_eligible": true|false, "comment_eligible": true|false, "reasoning": "brief reason"}}
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
            {"stance_eligible": False, "comment_eligible": False, "reasoning": "default (LLM returned too few)"}
        )

    # Normalize booleans
    for r in results:
        r["stance_eligible"] = bool(r.get("stance_eligible", False))
        r["comment_eligible"] = bool(r.get("comment_eligible", False))

    return results


def classify_agenda_items_batch(
    items: List[Dict[str, Any]],
    batch_size: int = 20,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
) -> List[Dict[str, Any]]:
    """
    Classify agenda items in batches (for large backfills).

    Processes items in chunks of batch_size to stay within token limits.
    """
    all_results = []
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        results = classify_agenda_items(batch, api_key=api_key, model=model)
        all_results.extend(results)
    return all_results
