#!/usr/bin/env python3
"""
Phase 1: Topic discovery from 3,563 utterances.

Discovers topics inductively from what residents actually said at San Rafael
City Council meetings (March-October 2024), without predefined categories.

Usage:
    python scripts/phase1_topic_discovery.py
    python scripts/phase1_topic_discovery.py --meeting 2024-04-15  # Single meeting
"""

import argparse
import json
import sqlite3
import re
import sys
from collections import Counter
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from llm_provider import get_model_for_task


DB_PATH = Path(__file__).parent.parent / 'data' / 'civic_participation.db'
OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'pilot'


def get_db_connection():
    """Get database connection."""
    return sqlite3.connect(DB_PATH)


def extract_all_utterances():
    """Extract all utterances from database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            tm.meeting_date,
            tm.youtube_video_id,
            ts.speaker_label,
            ts.name,
            tu.text,
            tu.start_ms,
            tu.sequence
        FROM testimony_utterances tu
        JOIN testimony_speakers ts ON tu.speaker_id = ts.speaker_id
        JOIN testimony_meetings tm ON ts.meeting_id = tm.meeting_id
        ORDER BY tm.meeting_date, tu.start_ms
    """)

    columns = ['meeting_date', 'youtube_video_id', 'speaker_label', 'name', 'text', 'start_ms', 'sequence']
    utterances = [dict(zip(columns, row)) for row in cursor.fetchall()]

    conn.close()
    return utterances


def get_utterances_by_meeting(utterances):
    """Group utterances by meeting date."""
    by_meeting = {}
    for u in utterances:
        date = u['meeting_date']
        if date not in by_meeting:
            by_meeting[date] = []
        by_meeting[date].append(u)
    return by_meeting


def cluster_topics_llm(utterances, meeting_date=None):
    """Use LLM to discover topics from utterances."""
    # Use 'explain' task type - has explicit fallback chain starting with gpt-4o-mini
    # (avoids free tier rate limits from cost_optimized strategy)
    provider = get_model_for_task('explain')

    # Sample utterances (max 100 for cost efficiency)
    sample_size = min(100, len(utterances))
    sample = utterances[:sample_size]  # Take first N (chronologically ordered)

    # Create sample text
    utterance_text = "\n".join([
        f"[{u['speaker_label']}/{u.get('name', 'Unknown')}]: {u['text'][:500]}"  # Truncate long utterances
        for u in sample
    ])

    meeting_context = f" from the {meeting_date} meeting" if meeting_date else ""

    prompt = f"""Analyze these public testimony utterances{meeting_context} from San Rafael City Council
and identify the main themes/topics discussed.

DO NOT use predefined categories. Discover themes from the content itself.
Focus on substantive policy topics, not procedural/administrative comments.

Utterances:
{utterance_text}

Return a JSON object with this EXACT structure:
{{
  "themes": [
    {{"topic": "theme name", "description": "what it's about", "estimated_utterance_pct": N}},
    ...
  ],
  "total_utterances_analyzed": {sample_size},
  "key_observations": "any notable patterns"
}}

Return ONLY valid JSON, no other text."""

    try:
        response = provider.complete(
            model=provider.default_model if hasattr(provider, 'default_model') else 'gpt-4o-mini',
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        # Parse response
        content = response.get('content', '') if isinstance(response, dict) else str(response)

        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        else:
            return {"error": "No JSON found in response", "raw": content[:500]}

    except Exception as e:
        return {"error": str(e)}


def keyword_frequency(utterances):
    """Count most common keywords across all utterances."""
    # Common stopwords to filter
    stopwords = {
        'that', 'this', 'with', 'have', 'from', 'they', 'been', 'were', 'will',
        'would', 'could', 'should', 'about', 'their', 'there', 'which', 'these',
        'other', 'what', 'when', 'some', 'them', 'than', 'then', 'only', 'your',
        'just', 'more', 'also', 'very', 'like', 'into', 'over', 'such', 'make',
        'many', 'because', 'being', 'through', 'most', 'where', 'those', 'each',
        'before', 'after', 'even', 'want', 'think', 'know', 'going', 'really',
        'people', 'council', 'city', 'thank', 'good', 'tonight', 'here', 'come',
        'time', 'years', 'year', 'said', 'mayor', 'item'  # Common meeting words
    }

    words = []
    for u in utterances:
        text = u['text'].lower()
        # Extract 4+ letter words
        found = re.findall(r'\b[a-z]{4,}\b', text)
        words.extend(found)

    # Filter stopwords
    filtered = [w for w in words if w not in stopwords]

    # Get top 100 terms
    top_100 = Counter(filtered).most_common(100)

    return {
        "total_words": len(words),
        "unique_words": len(set(words)),
        "top_100_keywords": [{"word": w, "count": c} for w, c in top_100]
    }


def meeting_topic_distribution(utterances_by_meeting):
    """Analyze topic distribution across meetings."""
    distribution = {}

    for meeting_date, utterances in utterances_by_meeting.items():
        print(f"  Analyzing {meeting_date} ({len(utterances)} utterances)...")

        # Get topics via LLM
        topics = cluster_topics_llm(utterances, meeting_date)

        # Also get keyword stats
        keywords = keyword_frequency(utterances)

        distribution[meeting_date] = {
            "utterance_count": len(utterances),
            "topics": topics,
            "top_keywords": keywords["top_100_keywords"][:20]  # Top 20 per meeting
        }

    return distribution


def main():
    parser = argparse.ArgumentParser(description='Phase 1: Topic discovery from utterances')
    parser.add_argument('--meeting', help='Analyze single meeting (YYYY-MM-DD)')
    parser.add_argument('--keywords-only', action='store_true', help='Only run keyword frequency analysis')
    args = parser.parse_args()

    print("Phase 1: Topic Discovery from 3,563 Utterances")
    print("=" * 50)

    # Extract all utterances
    print("\n1. Extracting utterances from database...")
    utterances = extract_all_utterances()
    print(f"   Loaded {len(utterances)} utterances")

    # Group by meeting
    by_meeting = get_utterances_by_meeting(utterances)
    print(f"   Across {len(by_meeting)} meetings:")
    for date, utts in sorted(by_meeting.items()):
        print(f"     {date}: {len(utts)} utterances")

    # Task 3: Keyword frequency analysis
    print("\n2. Running keyword frequency analysis...")
    keywords = keyword_frequency(utterances)

    print(f"   Total words: {keywords['total_words']:,}")
    print(f"   Unique words: {keywords['unique_words']:,}")
    print(f"   Top 20 keywords:")
    for kw in keywords['top_100_keywords'][:20]:
        print(f"     {kw['word']}: {kw['count']}")

    # Save keyword results
    keywords_path = OUTPUT_DIR / 'keyword_frequency_top100.json'
    with open(keywords_path, 'w') as f:
        json.dump(keywords, f, indent=2)
    print(f"   Saved to {keywords_path}")

    if args.keywords_only:
        print("\nKeywords-only mode complete.")
        return

    # Task 2: LLM topic clustering
    if args.meeting:
        # Single meeting analysis
        if args.meeting not in by_meeting:
            print(f"Error: Meeting {args.meeting} not found")
            return

        print(f"\n3. Clustering topics for {args.meeting}...")
        topics = cluster_topics_llm(by_meeting[args.meeting], args.meeting)

        output_path = OUTPUT_DIR / f'topic_clustering_{args.meeting}.json'
        with open(output_path, 'w') as f:
            json.dump(topics, f, indent=2)
        print(f"   Saved to {output_path}")

    else:
        # Full analysis - all meetings
        print("\n3. Running LLM topic clustering on high-engagement meetings...")

        # Start with highest engagement meetings
        high_engagement = ['2024-04-15', '2024-08-19', '2024-06-03', '2024-07-15']

        results = {}
        for meeting_date in high_engagement:
            if meeting_date in by_meeting:
                print(f"\n   Processing {meeting_date}...")
                topics = cluster_topics_llm(by_meeting[meeting_date], meeting_date)
                results[meeting_date] = {
                    "utterance_count": len(by_meeting[meeting_date]),
                    "topics": topics
                }

        # Save results
        topics_path = OUTPUT_DIR / 'topic_clustering_results.json'
        with open(topics_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n   Saved clustering results to {topics_path}")

        # Task 4: Meeting-level distribution (all meetings)
        print("\n4. Generating meeting-level topic distribution...")
        distribution = meeting_topic_distribution(by_meeting)

        dist_path = OUTPUT_DIR / 'meeting_topic_distribution.json'
        with open(dist_path, 'w') as f:
            json.dump(distribution, f, indent=2)
        print(f"   Saved to {dist_path}")

    print("\n" + "=" * 50)
    print("Phase 1 Complete!")


if __name__ == '__main__':
    main()
