#!/usr/bin/env python3
"""
Backfill item_type and correct outcomes for existing decisions.

Uses an LLM to classify each decision into:
  action, consent, presentation, hearing, discussion

Then corrects outcomes:
  - presentation/discussion → "received"
  - action/consent/hearing keep LLM-assigned outcome

Usage:
    # Dry run (show what would change):
    python scripts/backfill_decision_item_types.py

    # Apply changes:
    python scripts/backfill_decision_item_types.py --apply
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

VALID_ITEM_TYPES = {"action", "consent", "presentation", "hearing", "discussion"}
VALID_OUTCOMES = {"approved", "denied", "continued", "withdrawn", "received", "adopted", "other"}


def classify_decisions_via_llm(decisions: list[dict]) -> dict[str, dict]:
    """
    Classify all decisions in a single LLM call.

    Returns: {decision_id: {"item_type": str, "outcome": str}}
    """
    import openai
    client = openai.OpenAI()

    # Build compact entries for the prompt
    entries = []
    for d in decisions:
        entries.append({
            "id": d.get("id", "unknown"),
            "title": d.get("title", ""),
            "summary": (d.get("summary") or "")[:200],
            "current_outcome": d.get("outcome", "approved"),
        })

    prompt = f"""Classify each municipal agenda item below. For each, return:
- item_type: what kind of agenda item this is
- outcome: what happened

ITEM TYPE VALUES:
- action: Council/commission deliberated and took a formal vote (approval, denial, adoption, authorization)
- consent: Routine item approved in batch without individual discussion
- hearing: Public hearing with formal testimony period (land use, zoning, taxes)
- presentation: Informational report, audit presentation, status update — no vote taken
- discussion: Policy discussion, study session, consideration — council may give direction but no formal action

OUTCOME VALUES:
- For action/consent/hearing: "approved", "denied", "continued", "withdrawn", "adopted"
- For presentation/discussion: "received" (or "continued" if explicitly deferred to future meeting)

KEY SIGNALS:
- "will receive a presentation/report/update" → presentation, received
- "will consider a resolution/ordinance" → action (even though "consider" sounds tentative, this is formal legislative language for voting)
- "Subcommittee will consider" with no resolution → discussion (subcommittees typically recommend, not vote)
- "will discuss" → discussion
- Title starts with "Presentation of" → presentation
- Title contains "Adoption of" / "Ordinance" / "Agreement" / "Declaration" → action

ITEMS TO CLASSIFY:
{json.dumps(entries, indent=2)}

Return JSON: {{"classifications": [{{"id": "...", "item_type": "...", "outcome": "..."}}]}}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are an expert in municipal government proceedings. Classify agenda items accurately based on their title and summary. Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    result = json.loads(response.choices[0].message.content)
    usage = response.usage
    cost = (usage.prompt_tokens * 0.15 + usage.completion_tokens * 0.60) / 1_000_000
    print(f"LLM classification: {usage.prompt_tokens + usage.completion_tokens:,} tokens, ${cost:.4f}")

    # Index by ID
    classifications = {}
    for c in result.get("classifications", []):
        item_type = c.get("item_type", "action")
        outcome = c.get("outcome", "other")
        # Validate
        if item_type not in VALID_ITEM_TYPES:
            item_type = "action"
        if outcome not in VALID_OUTCOMES:
            outcome = "other"
        classifications[c["id"]] = {"item_type": item_type, "outcome": outcome}

    return classifications


def main():
    parser = argparse.ArgumentParser(description="Backfill decision item_types using LLM classification")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--jurisdiction", default="city-san-rafael", help="Jurisdiction ID")
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set. Run: source .env")
        sys.exit(1)

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set.")
        sys.exit(1)

    from civicos.storage import get_storage_backend
    backend = get_storage_backend()

    if backend.backend_type != "postgres":
        print("ERROR: This script requires PostgreSQL backend")
        sys.exit(1)

    # Fetch all current decisions
    decisions = backend.get_decisions(args.jurisdiction)
    print(f"Found {len(decisions)} decisions for {args.jurisdiction}")

    # Classify via LLM
    print("Classifying via LLM...")
    classifications = classify_decisions_via_llm(decisions)

    # Compute changes
    changes = []
    for d in decisions:
        decision_id = d.get("id", "unknown")
        current_item_type = d.get("item_type") or "action"
        current_outcome = d.get("outcome", "approved")

        c = classifications.get(decision_id)
        if not c:
            continue

        new_item_type = c["item_type"]
        new_outcome = c["outcome"]

        if new_item_type != current_item_type or new_outcome != current_outcome:
            changes.append({
                "id": decision_id,
                "title": d.get("title", "")[:80],
                "old_item_type": current_item_type,
                "new_item_type": new_item_type,
                "old_outcome": current_outcome,
                "new_outcome": new_outcome,
            })

    if not changes:
        print("\nNo changes needed. All decisions already classified correctly.")
        return

    # Show changes
    print(f"\n{'=' * 105}")
    print(f"{'Title':<55} {'Type Change':<25} {'Outcome Change':<25}")
    print(f"{'=' * 105}")
    for c in changes:
        type_change = f"{c['old_item_type']} -> {c['new_item_type']}" if c['old_item_type'] != c['new_item_type'] else "(same)"
        outcome_change = f"{c['old_outcome']} -> {c['new_outcome']}" if c['old_outcome'] != c['new_outcome'] else "(same)"
        print(f"{c['title']:<55} {type_change:<25} {outcome_change:<25}")

    print(f"\n{len(changes)} decisions would be updated.")

    if not args.apply:
        print("\nDry run complete. Use --apply to commit changes.")
        return

    # Apply changes
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cursor = conn.cursor()

    updated = 0
    for c in changes:
        cursor.execute("""
            UPDATE decisions
            SET item_type = %s, outcome = %s
            WHERE id = %s AND valid_to IS NULL
        """, (c["new_item_type"], c["new_outcome"], c["id"]))
        updated += cursor.rowcount

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\nApplied {updated} updates successfully.")

    # Verification query
    conn2 = psycopg2.connect(os.environ["DATABASE_URL"])
    cursor2 = conn2.cursor()
    cursor2.execute("""
        SELECT item_type, outcome, count(*)
        FROM decisions
        WHERE jurisdiction_id = %s AND valid_to IS NULL
        GROUP BY item_type, outcome
        ORDER BY item_type, outcome
    """, (args.jurisdiction,))
    print(f"\nVerification (item_type x outcome):")
    print(f"{'item_type':<15} {'outcome':<15} {'count':>5}")
    print("-" * 37)
    for row in cursor2.fetchall():
        print(f"{row[0]:<15} {row[1]:<15} {row[2]:>5}")
    cursor2.close()
    conn2.close()


if __name__ == "__main__":
    main()
