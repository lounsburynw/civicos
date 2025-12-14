#!/usr/bin/env python3
"""
LLM-based speaker name extraction for city council meeting transcripts.

This script uses LLM to robustly extract speaker names from their utterances,
handling cases where pattern matching fails or is ambiguous.

Usage:
    python scripts/extract_speaker_names_llm.py --transcript data/testimony/testimony_MpxrGRb16HQ_exact50.json --speaker P
    python scripts/extract_speaker_names_llm.py --transcript data/testimony/testimony_MpxrGRb16HQ_exact50.json --all
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from llm_provider import get_model_for_task


def load_transcript(filepath: str) -> Dict:
    """Load AssemblyAI transcript from JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_speaker_name_llm(utterances: List[dict], speaker_label: str) -> Optional[str]:
    """
    Use LLM to extract speaker name from their utterances.

    Falls back to this when pattern matching fails.
    Cost: ~$0.0001 per speaker with gpt-4o-mini

    Args:
        utterances: Full transcript utterance list
        speaker_label: Speaker label to extract (e.g., 'P', 'AJ', 'T')

    Returns:
        Speaker name if found, None otherwise
    """
    # Get utterances for this speaker
    speaker_utterances = [u for u in utterances if u.get('speaker') == speaker_label]

    if not speaker_utterances:
        print(f"No utterances found for speaker {speaker_label}")
        return None

    # Get first 20 utterances as context (usually enough to find self-introduction)
    sample = speaker_utterances[:20]
    context = "\n".join([f"- {u.get('text', '')}" for u in sample])

    prompt = f"""These are utterances from Speaker {speaker_label} in a city council meeting.
Find any self-introduction where they state their name.

Utterances:
{context}

Return ONLY the person's name if found (e.g., "John Smith" or "Salama from Terra Linda").
If no introduction found, return the word "null" (without quotes).
"""

    # Use gpt-4o-mini for cost efficiency
    provider = get_model_for_task('short_structured')

    try:
        response = provider.complete([
            {"role": "system", "content": "Extract speaker names from meeting transcripts. Return only the name or the word null."},
            {"role": "user", "content": prompt}
        ])

        name = response.content.strip()

        # Handle various null responses
        if name and name.lower() not in ['null', 'none', 'n/a', 'unknown']:
            return name
        else:
            return None

    except Exception as e:
        print(f"Error calling LLM: {e}")
        return None


def get_all_speaker_labels(utterances: List[dict]) -> List[str]:
    """Get unique speaker labels from transcript."""
    speakers = set()
    for u in utterances:
        speaker = u.get('speaker')
        if speaker:
            speakers.add(speaker)
    return sorted(list(speakers))


def main():
    parser = argparse.ArgumentParser(description='Extract speaker names using LLM')
    parser.add_argument('--transcript', required=True, help='Path to AssemblyAI transcript JSON')
    parser.add_argument('--speaker', help='Speaker label to extract (e.g., P, AJ, T)')
    parser.add_argument('--all', action='store_true', help='Extract names for all speakers')
    parser.add_argument('--output', help='Optional output JSON file')

    args = parser.parse_args()

    # Load transcript
    print(f"Loading transcript: {args.transcript}")
    data = load_transcript(args.transcript)
    utterances = data.get('utterances', [])

    if not utterances:
        print("No utterances found in transcript")
        return

    results = {}

    if args.all:
        # Extract names for all speakers
        speakers = get_all_speaker_labels(utterances)
        print(f"Found {len(speakers)} speakers: {', '.join(speakers)}")

        for speaker in speakers:
            print(f"\nExtracting name for Speaker {speaker}...")
            name = extract_speaker_name_llm(utterances, speaker)
            results[speaker] = name

            if name:
                print(f"  ✓ Speaker {speaker}: {name}")
            else:
                print(f"  ✗ Speaker {speaker}: No name found")

    elif args.speaker:
        # Extract name for specific speaker
        print(f"Extracting name for Speaker {args.speaker}...")
        name = extract_speaker_name_llm(utterances, args.speaker)
        results[args.speaker] = name

        if name:
            print(f"\n✓ Speaker {args.speaker}: {name}")
        else:
            print(f"\n✗ Speaker {args.speaker}: No name found")

    else:
        parser.error("Must specify either --speaker or --all")

    # Save results if output file specified
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")

    return results


if __name__ == '__main__':
    main()
