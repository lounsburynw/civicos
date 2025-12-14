#!/usr/bin/env python3
"""
Test Docling analyzer on 1-2 San Rafael meetings

Quick validation before running full 33-meeting analysis
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from docling_retrospective_analyzer import DoclingRetrospectiveAnalyzer

# Test with local Oct 6 PDF (wildfire prevention fund case study)
TEST_MEETINGS = [
    {
        "title": "City Council – October 6, 2025 (Wildfire Prevention Fund)",
        "date": "2025-10-06",
        "pdf_url": "/Users/nicolaslounsbury/projects/civic/data/test_agenda_packet_oct6.pdf"
    }
]


def main():
    print("🔍 Testing Docling Retrospective Analyzer")
    print(f"Processing {len(TEST_MEETINGS)} meeting(s)\n")

    analyzer = DoclingRetrospectiveAnalyzer()
    all_decisions = []

    for i, meeting in enumerate(TEST_MEETINGS, 1):
        print(f"\n{'='*70}")
        print(f"Meeting {i}/{len(TEST_MEETINGS)}: {meeting['title']}")
        print(f"{'='*70}")

        try:
            decisions = analyzer.extract_high_stakes_decisions(
                pdf_url=meeting['pdf_url'],
                meeting_date=meeting['date'],
                meeting_type="city_council"
            )

            print(f"\n✅ Found {len(decisions)} high-stakes decisions:")
            for d in decisions:
                print(f"\n   Item {d.item_ref}: {d.title}")
                print(f"   Stakes: {d.stakes_score}/10")
                if d.budget_amount:
                    print(f"   Budget: ${d.budget_amount:,}")
                print(f"   Type: {d.decision_type}")

            all_decisions.extend([{
                "meeting_title": meeting['title'],
                "meeting_date": meeting['date'],
                **d.__dict__
            } for d in decisions])

        except Exception as e:
            print(f"\n❌ Error processing meeting: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    # Save results
    output = {
        "test_date": datetime.now().isoformat(),
        "meetings_processed": len(TEST_MEETINGS),
        "total_decisions": len(all_decisions),
        "decisions": all_decisions
    }

    output_file = "data/pilot/docling_test_results.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*70}")
    print(f"📊 SUMMARY")
    print(f"{'='*70}")
    print(f"Meetings processed: {len(TEST_MEETINGS)}")
    print(f"Total high-stakes decisions: {len(all_decisions)}")
    print(f"\n📄 Results saved to: {output_file}")

    return all_decisions


if __name__ == "__main__":
    decisions = main()
    print("\n✅ Test complete!")
