#!/usr/bin/env python3
"""
Enrich high-stakes decisions with testimony data from meeting minutes

Reads decisions JSON and enriches each with:
- Testimony count (number of public speakers)
- Speaker names
- Vote results
- Whether decision passed
"""

import sys
import os
import json
import argparse
from typing import Dict, List
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from minutes_parser import MinutesParser
from agenda_integration import AgendaIntegrator


def download_pdf_text(pdf_url: str) -> str:
    """Download PDF and extract text"""
    integrator = AgendaIntegrator()

    try:
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()

        text = integrator._extract_pdf_text(response.content)
        return text
    except Exception as e:
        print(f"  ❌ Failed to download {pdf_url}: {e}")
        return None


def enrich_decisions_with_testimony(
    decisions_file: str,
    output_file: str = None,
    dry_run: bool = False
) -> Dict:
    """
    Enrich all decisions with testimony data from minutes

    Args:
        decisions_file: Path to high_stakes_decisions.json
        output_file: Where to save enriched data (defaults to same file)
        dry_run: If True, don't save results (just print)

    Returns:
        Enriched decisions dict
    """
    print("🗣️  TESTIMONY ENRICHMENT")
    print("=" * 70)

    # Load decisions
    with open(decisions_file, 'r') as f:
        data = json.load(f)

    decisions = data['decisions']
    print(f"Loaded {len(decisions)} decisions from {decisions_file}\n")

    # Initialize parser
    parser = MinutesParser()

    # Track stats
    enriched_count = 0
    minutes_available = 0

    # Group decisions by meeting date (to avoid re-downloading same minutes)
    by_meeting = {}
    for decision in decisions:
        meeting_date = decision['meeting_date'].split('T')[0]  # Just date part
        if meeting_date not in by_meeting:
            by_meeting[meeting_date] = []
        by_meeting[meeting_date].append(decision)

    print(f"Processing {len(by_meeting)} unique meetings\n")

    # Process each meeting
    for meeting_date, meeting_decisions in by_meeting.items():
        print(f"📅 {meeting_date}")
        print(f"   {len(meeting_decisions)} decisions")

        # Get minutes URL from first decision (all should have same)
        minutes_url = None
        for d in meeting_decisions:
            # Check _scraped_metadata first
            metadata = d.get('_scraped_metadata', {})
            if metadata.get('minutes_pdf_url'):
                minutes_url = metadata['minutes_pdf_url']
                break

        if not minutes_url:
            print(f"   ⚠️  No minutes URL found\n")
            continue

        minutes_available += len(meeting_decisions)

        # Download minutes
        print(f"   📄 Downloading minutes: {minutes_url}")
        minutes_text = download_pdf_text(minutes_url)

        if not minutes_text:
            print(f"   ⚠️  Failed to extract text from minutes\n")
            continue

        print(f"   ✅ Extracted {len(minutes_text):,} characters")

        # Enrich each decision from this meeting
        for decision in meeting_decisions:
            item_ref = decision['item_ref']
            print(f"   🔍 Extracting testimony for item {item_ref}")

            try:
                testimony_data = parser.extract_testimony_for_item(
                    minutes_text=minutes_text,
                    item_ref=item_ref
                )

                # Update decision
                decision['testimony_count'] = testimony_data.testimony_count
                decision['speaker_names'] = testimony_data.speaker_names
                decision['vote_results'] = testimony_data.vote_results
                decision['passed'] = testimony_data.passed
                decision['minutes_url'] = minutes_url

                enriched_count += 1

                # Print results
                if testimony_data.testimony_count is not None:
                    print(f"      Testimony: {testimony_data.testimony_count} speakers")
                if testimony_data.speaker_names:
                    print(f"      Speakers: {', '.join(testimony_data.speaker_names[:3])}" +
                          (f" (+{len(testimony_data.speaker_names)-3} more)" if len(testimony_data.speaker_names) > 3 else ""))
                if testimony_data.vote_results:
                    print(f"      Vote: {testimony_data.vote_results}")

            except Exception as e:
                print(f"      ❌ Error: {type(e).__name__}: {e}")

        print()

    # Update summary
    data['enrichment_stats'] = {
        'total_decisions': len(decisions),
        'decisions_with_minutes': minutes_available,
        'decisions_enriched': enriched_count,
        'enrichment_rate': f"{enriched_count / len(decisions) * 100:.1f}%"
    }

    # Save results
    if not dry_run:
        output_path = output_file or decisions_file
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ Saved enriched data to {output_path}")
    else:
        print("🔍 DRY RUN - No changes saved")

    print("\n" + "=" * 70)
    print("📊 ENRICHMENT SUMMARY")
    print(f"   Total decisions: {len(decisions)}")
    print(f"   Decisions with minutes available: {minutes_available}")
    print(f"   Decisions enriched: {enriched_count}")
    print(f"   Enrichment rate: {enriched_count / len(decisions) * 100:.1f}%")

    return data


def main():
    parser = argparse.ArgumentParser(
        description='Enrich high-stakes decisions with testimony data from minutes'
    )
    parser.add_argument('decisions_file', help='JSON file with high-stakes decisions')
    parser.add_argument('--output', help='Output file (defaults to same file)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without saving')

    args = parser.parse_args()

    enrich_decisions_with_testimony(
        decisions_file=args.decisions_file,
        output_file=args.output,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
