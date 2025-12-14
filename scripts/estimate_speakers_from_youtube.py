#!/usr/bin/env python3
"""
Estimate number of speakers from YouTube auto-generated transcript.

Uses text patterns to estimate how many unique speakers are in a meeting:
- Names mentioned (council members, staff)
- "Thank you" patterns (speaker changes)
- Conversational markers

This gives us a better prior for AssemblyAI's speaker diarization.

Usage:
    python scripts/estimate_speakers_from_youtube.py \
        --youtube-transcript data/youtube_transcripts/MpxrGRb16HQ.en.json3
"""

import json
import re
import argparse
from collections import Counter
from pathlib import Path


def extract_names_from_text(text: str) -> set:
    """
    Extract likely speaker names from transcript text.

    Looks for patterns like:
    - "Mayor [Name]"
    - "Council Member [Name]"
    - "Vice Mayor [Name]"
    """
    names = set()

    # Pattern for titles + names (case-sensitive to avoid false positives)
    title_patterns = [
        r'(?:Mayor|Vice Mayor|Council Member|Councilmember)\s+([A-Z][a-z]+)',
        r'City Attorney',
        r'City Manager',
        r'City Clerk',
    ]

    for pattern in title_patterns:
        matches = re.findall(pattern, text)
        # Filter out common false positives
        valid_names = [
            name for name in matches
            if name and len(name) > 2 and name not in ['The', 'And', 'But', 'Was', 'Will', 'Can']
        ]
        names.update(valid_names)

    # Also count title-only mentions (City Attorney, etc.)
    if 'City Attorney' in text:
        names.add('City Attorney')
    if 'City Manager' in text:
        names.add('City Manager')
    if 'City Clerk' in text:
        names.add('City Clerk')

    return names


def count_speaker_changes(text: str) -> int:
    """
    Count likely speaker changes using procedural markers.

    In council meetings:
    - "Thank you" often indicates speaker change
    - ">> " markers (YouTube sometimes adds these)
    - Question/answer patterns
    """
    # Count "Thank you" instances (strong speaker change signal)
    thank_you_count = len(re.findall(r'\bthank you\b', text, re.IGNORECASE))

    # Count ">>" markers (YouTube speaker markers)
    marker_count = text.count('>>')

    # Return max of the two (most reliable signal)
    return max(thank_you_count, marker_count)


def estimate_speakers(youtube_transcript_path: str) -> dict:
    """
    Estimate number of speakers from YouTube transcript.

    Returns:
        dict with estimated min/max speakers and confidence
    """
    # Load YouTube transcript
    with open(youtube_transcript_path) as f:
        data = json.load(f)

    # Extract full text
    text = ""
    for event in data.get("events", []):
        if "segs" in event:
            for seg in event.get("segs", []):
                if "utf8" in seg:
                    text += seg["utf8"]

    # Extract names
    names = extract_names_from_text(text)

    # Count speaker changes
    speaker_changes = count_speaker_changes(text)

    # Estimate unique speakers from changes
    # Heuristic: # of "thank you" / 3 = rough speaker count
    # (each speaker says thank you ~3 times on average)
    estimated_from_changes = max(2, speaker_changes // 3)

    # Combine both signals
    # Named speakers are definite, changes give us a range
    min_estimate = max(len(names), 5)  # At minimum, council members
    max_estimate = min(max(estimated_from_changes, len(names) + 5), 10)  # Cap at 10

    return {
        "named_speakers": list(names),
        "named_count": len(names),
        "speaker_changes": speaker_changes,
        "min_estimate": min_estimate,
        "max_estimate": max_estimate,
        "confidence": "high" if len(names) >= 5 else "medium"
    }


def main():
    parser = argparse.ArgumentParser(
        description="Estimate speaker count from YouTube transcript"
    )
    parser.add_argument(
        "--youtube-transcript",
        required=True,
        help="Path to YouTube transcript JSON3 file"
    )
    args = parser.parse_args()

    # Estimate speakers
    result = estimate_speakers(args.youtube_transcript)

    # Print results
    print("="*60)
    print("SPEAKER ESTIMATION FROM YOUTUBE TRANSCRIPT")
    print("="*60)

    print(f"\nNamed Speakers Found ({result['named_count']}):")
    for name in sorted(result['named_speakers']):
        print(f"  • {name}")

    print(f"\nSpeaker Changes Detected: {result['speaker_changes']}")
    print(f"  (Based on 'Thank you' and '>>' markers)")

    print(f"\nEstimated Speaker Range:")
    print(f"  Min: {result['min_estimate']} speakers")
    print(f"  Max: {result['max_estimate']} speakers")
    print(f"  Confidence: {result['confidence']}")

    print("\n" + "="*60)
    print("RECOMMENDATION FOR ASSEMBLYAI")
    print("="*60)
    print(f"\nUse these parameters:")
    print(f"  speaker_options=aai.types.SpeakerOptions(")
    print(f"      min_speakers_expected={result['min_estimate']},")
    print(f"      max_speakers_expected={result['max_estimate']}")
    print(f"  )")

    # Save to JSON for automated processing
    output_path = Path(args.youtube_transcript).with_suffix('.speaker_estimate.json')
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
