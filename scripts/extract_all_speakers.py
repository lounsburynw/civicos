#!/usr/bin/env python3
"""
Extract ALL speaker names from YouTube transcript using pattern matching.

Finds speaker introductions like:
- "My name is John Smith"
- "Good evening, I'm Jane Doe"
- "This is Bob Johnson"

Session: 109
"""

import argparse
import json
import re
from collections import Counter


def extract_speakers_from_transcript(transcript_path: str) -> dict:
    """
    Extract all speaker names from YouTube transcript.

    Args:
        transcript_path: Path to YouTube JSON3 transcript

    Returns:
        Dictionary with named speakers and statistics
    """
    with open(transcript_path) as f:
        data = json.load(f)

    # Extract full text
    text = ""
    for event in data.get("events", []):
        if "segs" in event:
            for seg in event.get("segs", []):
                if "utf8" in seg:
                    text += seg["utf8"]

    # Pattern matching for speaker introductions
    patterns = [
        r"[Mm]y name is ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"[Ii]'m ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"[Tt]his is ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"([A-Z][a-z]+ [A-Z][a-z]+) speaking",
        r"I am ([A-Z][a-z]+ [A-Z][a-z]+)",
        r"resident of ([A-Z][a-z]+)"  # Capture city/neighborhood names too
    ]

    # Also look for titles
    title_patterns = [
        r"(Mayor [A-Z][a-z]+)",
        r"(Vice Mayor [A-Z][a-z]+)",
        r"(Council [Mm]ember [A-Z][a-z]+)",
        r"(City Manager [A-Z][a-z]+)",
        r"(City Attorney [A-Z][a-z]+)",
        r"(Chief [A-Z][a-z]+)",
        r"(Director [A-Z][a-z]+)"
    ]

    all_speakers = []

    # Find name introductions
    for pattern in patterns:
        matches = re.findall(pattern, text)
        all_speakers.extend(matches)

    # Find titled speakers
    for pattern in title_patterns:
        matches = re.findall(pattern, text)
        all_speakers.extend(matches)

    # Count occurrences
    speaker_counts = Counter(all_speakers)

    # Filter out common false positives
    filtered_speakers = {
        name: count
        for name, count in speaker_counts.items()
        if count >= 2 and name not in ["San Rafael", "Dominican", "Terra Linda"]
    }

    return {
        "total_unique_speakers": len(filtered_speakers),
        "speakers": sorted(filtered_speakers.items(), key=lambda x: x[1], reverse=True),
        "all_matches": len(all_speakers)
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract all speaker names from YouTube transcript"
    )
    parser.add_argument(
        "--youtube-transcript",
        required=True,
        help="Path to YouTube JSON3 transcript file"
    )

    args = parser.parse_args()

    # Extract speakers
    result = extract_speakers_from_transcript(args.youtube_transcript)

    print("=" * 60)
    print("Speaker Extraction from YouTube Transcript")
    print("=" * 60)
    print(f"\nTotal Unique Speakers: {result['total_unique_speakers']}")
    print(f"Total Matches Found: {result['all_matches']}")

    print("\nSpeakers (sorted by mention frequency):")
    for name, count in result["speakers"]:
        print(f"  - {name} ({count} mentions)")

    print("\n" + "=" * 60)
    print("Note: Speakers with only 1 mention filtered out as likely false positives")


if __name__ == "__main__":
    main()
