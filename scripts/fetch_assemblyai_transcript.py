#!/usr/bin/env python3
"""
Fetch completed AssemblyAI transcript by ID.
"""

import argparse
import json
import os
from datetime import datetime
from dotenv import load_dotenv

try:
    import assemblyai as aai
except ImportError:
    print("Error: assemblyai package not installed")
    exit(1)

load_dotenv()


def fetch_transcript(transcript_id: str, output_path: str = None, verbose: bool = False):
    """Fetch transcript by ID and save to JSON."""

    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY not found")

    aai.settings.api_key = api_key

    if verbose:
        print(f"Fetching transcript: {transcript_id}")

    # Fetch transcript
    transcriber = aai.Transcriber()
    transcript = transcriber.get_transcript(transcript_id)

    if verbose:
        print(f"Status: {transcript.status}")

    # Extract speaker count
    speakers_detected = len(set(
        utterance.speaker
        for utterance in transcript.utterances
        if hasattr(utterance, 'speaker') and utterance.speaker
    ))

    # Calculate cost
    audio_duration_seconds = transcript.audio_duration / 1000
    cost_usd = audio_duration_seconds * 0.00025

    # Build result
    result = {
        "assemblyai_id": transcript.id,
        "processed_at": datetime.now().isoformat(),
        "processing_service": "assemblyai",

        "speaker_config": {
            "min_speakers_expected": 40,
            "max_speakers_expected": 60
        },

        "speakers_count": speakers_detected,
        "utterances_count": len(transcript.utterances),
        "audio_duration_minutes": audio_duration_seconds / 60,
        "cost_usd": round(cost_usd, 2),

        "utterances": [
            {
                "speaker": utterance.speaker,
                "text": utterance.text,
                "start": utterance.start,
                "end": utterance.end
            }
            for utterance in transcript.utterances
        ],

        "video_id": "MpxrGRb16HQ",
        "meeting_url": "https://www.youtube.com/watch?v=MpxrGRb16HQ"
    }

    if verbose:
        print(f"\nResults:")
        print(f"  Speakers detected: {speakers_detected}")
        print(f"  Utterances: {len(transcript.utterances)}")
        print(f"  Duration: {audio_duration_seconds/60:.1f} minutes")
        print(f"  Cost: ${cost_usd:.2f}")

    # Save
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        if verbose:
            print(f"\n✅ Saved to: {output_path}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    result = fetch_transcript(args.transcript_id, args.output, args.verbose)

    print(f"\n{'='*70}")
    print("COMPARISON WITH ORIGINAL")
    print(f"{'='*70}")
    print(f"\nOriginal (min=5, max=10): 5 speakers, 217 utterances")
    print(f"New (min=40, max=60): {result['speakers_count']} speakers, {result['utterances_count']} utterances")

    improvement = result['speakers_count'] - 5
    print(f"\nImprovement: {improvement:+d} speakers ({improvement/5*100:+.0f}%)")
