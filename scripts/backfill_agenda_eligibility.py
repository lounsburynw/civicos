#!/usr/bin/env python3
"""
Backfill stance_eligible and comment_eligible for existing agenda items.

Uses the LLM classifier from civicos.storage.actionability to classify
agenda items that have NULL eligibility flags.

Usage:
    # Dry run (show what would change):
    python scripts/backfill_agenda_eligibility.py

    # Apply changes:
    python scripts/backfill_agenda_eligibility.py --apply

    # Limit to specific jurisdiction:
    python scripts/backfill_agenda_eligibility.py --jurisdiction city-san-rafael --apply
"""

import argparse
import sys

from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Backfill agenda item eligibility flags")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry run)")
    parser.add_argument("--jurisdiction", default="city-san-rafael", help="Jurisdiction to backfill")
    parser.add_argument("--batch-size", type=int, default=20, help="Items per LLM call")
    args = parser.parse_args()

    from civicos.storage import get_storage_backend
    from civicos.storage.actionability import classify_agenda_items_batch

    backend = get_storage_backend()
    if backend.backend_type != "postgres":
        print("ERROR: Backfill requires PostgreSQL backend (set DATABASE_URL)")
        sys.exit(1)

    # Get all agenda items for jurisdiction
    all_items = backend.get_agenda_items(jurisdiction_id=args.jurisdiction)
    print(f"Total agenda items for {args.jurisdiction}: {len(all_items)}")

    # Filter to those with NULL eligibility
    items_to_classify = [
        item for item in all_items
        if item.get('stance_eligible') is None or item.get('comment_eligible') is None
    ]
    print(f"Items with NULL eligibility: {len(items_to_classify)}")

    if not items_to_classify:
        print("Nothing to backfill.")
        return

    # Classify in batches
    print(f"\nClassifying {len(items_to_classify)} items in batches of {args.batch_size}...")
    classifications = classify_agenda_items_batch(
        items_to_classify,
        batch_size=args.batch_size,
    )

    # Summarize results
    stance_count = sum(1 for c in classifications if c['stance_eligible'])
    comment_count = sum(1 for c in classifications if c['comment_eligible'])
    neither_count = sum(1 for c in classifications if not c['stance_eligible'] and not c['comment_eligible'])

    print(f"\nClassification results:")
    print(f"  Stance eligible:  {stance_count}")
    print(f"  Comment eligible: {comment_count}")
    print(f"  Neither:          {neither_count}")

    # Show sample
    print(f"\nSample classifications:")
    for item, classification in zip(items_to_classify[:10], classifications[:10]):
        stance = "S" if classification['stance_eligible'] else "-"
        comment = "C" if classification['comment_eligible'] else "-"
        title = (item.get('title') or 'Unknown')[:60]
        reason = classification.get('reasoning', '')[:40]
        print(f"  [{stance}{comment}] {title}")
        if reason:
            print(f"       {reason}")

    if len(items_to_classify) > 10:
        print(f"  ... and {len(items_to_classify) - 10} more")

    if not args.apply:
        print(f"\nDry run complete. Use --apply to update the database.")
        return

    # Apply updates
    print(f"\nApplying {len(items_to_classify)} updates...")
    updated = 0
    failed = 0
    for item, classification in zip(items_to_classify, classifications):
        item_id = item.get('id')
        valid_from = item.get('valid_from')
        if not item_id or not valid_from:
            failed += 1
            continue

        # valid_from may be a datetime object — convert to string
        if hasattr(valid_from, 'isoformat'):
            valid_from = valid_from.isoformat()

        try:
            ok = backend.update_agenda_item_eligibility(
                item_id=item_id,
                valid_from=valid_from,
                stance_eligible=classification['stance_eligible'],
                comment_eligible=classification['comment_eligible'],
            )
            if ok:
                updated += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ERROR updating {item_id}: {e}")
            failed += 1

    print(f"\nDone: {updated} updated, {failed} failed")


if __name__ == "__main__":
    main()
