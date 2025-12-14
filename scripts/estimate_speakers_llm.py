#!/usr/bin/env python3
"""
LLM-based speaker estimation from YouTube transcripts.

Uses OpenAI structured outputs to estimate the number of unique speakers
in a city council meeting from YouTube auto-generated transcripts. This
provides a data-driven prior for AssemblyAI speaker diarization.

Cost: ~$0.001-0.01 per transcript (vs $2.80 for AssemblyAI)
Accuracy: High for named speakers, medium for total count estimation

Usage:
    python scripts/estimate_speakers_llm.py --youtube-transcript data/youtube_transcripts/VIDEO_ID.en.json3
    python scripts/estimate_speakers_llm.py --youtube-transcript data/youtube_transcripts/VIDEO_ID.en.json3 --verbose

    # Batch process all transcripts
    for f in data/youtube_transcripts/*.json3; do
        python scripts/estimate_speakers_llm.py --youtube-transcript "$f"
    done

Session: 108
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()


class SpeakerEstimate(BaseModel):
    """Structured output for speaker estimation."""

    named_speakers: List[str] = Field(
        description="List of speakers explicitly named or with titles (e.g., 'Mayor Kate', 'Council Member Hill')"
    )
    estimated_total_speakers: int = Field(
        description="Best estimate of total unique speakers in the meeting (5-15 typical range)",
        ge=3,
        le=15
    )
    confidence: str = Field(
        description="Confidence level: 'high', 'medium', or 'low'",
        pattern="^(high|medium|low)$"
    )
    reasoning: str = Field(
        description="Brief explanation of how you estimated the speaker count"
    )


def load_youtube_transcript(transcript_path: str, max_chars: int = 4000) -> str:
    """
    Load YouTube JSON3 transcript and extract text.

    Args:
        transcript_path: Path to YouTube .json3 file
        max_chars: Maximum characters to extract (for cost efficiency)

    Returns:
        Extracted transcript text
    """
    with open(transcript_path) as f:
        data = json.load(f)

    # Extract text from YouTube's JSON3 format
    text = ""
    for event in data.get("events", []):
        if "segs" in event:
            for seg in event.get("segs", []):
                if "utf8" in seg:
                    text += seg["utf8"]
                if len(text) >= max_chars:
                    break
        if len(text) >= max_chars:
            break

    return text[:max_chars]


def estimate_speakers_from_youtube(
    youtube_transcript_path: str,
    verbose: bool = False
) -> SpeakerEstimate:
    """
    Use LLM to estimate speakers from YouTube transcript.

    Args:
        youtube_transcript_path: Path to YouTube JSON3 transcript
        verbose: Print detailed progress

    Returns:
        SpeakerEstimate with named speakers and total count
    """
    if verbose:
        print(f"Loading transcript: {youtube_transcript_path}")

    # Load YouTube transcript
    text = load_youtube_transcript(youtube_transcript_path)

    if verbose:
        print(f"Extracted {len(text)} characters")

    # Use LLM with structured outputs
    client = OpenAI()

    if verbose:
        print("Calling OpenAI API for speaker estimation...")

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": "You are analyzing city council meeting transcripts to estimate the number of unique speakers. Look for named speakers (Mayor, Council Members, staff), speaker introductions, and conversational patterns."
        }, {
            "role": "user",
            "content": f"""Analyze this city council meeting transcript and estimate the number of unique speakers:

{text}

Identify:
1. Named speakers (with titles like Mayor, Council Member, etc.)
2. Estimated total unique speakers based on conversational flow
3. Your confidence level

Remember: City councils typically have 5-10 speakers (mayor, council members, staff, public commenters)."""
        }],
        response_format=SpeakerEstimate
    )

    return completion.choices[0].message.parsed


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Estimate speakers from YouTube transcript using LLM"
    )
    parser.add_argument(
        "--youtube-transcript",
        required=True,
        help="Path to YouTube JSON3 transcript file"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress"
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum characters to analyze from transcript (default: 4000)"
    )

    args = parser.parse_args()

    # Validate file exists
    if not os.path.exists(args.youtube_transcript):
        print(f"Error: Transcript file not found: {args.youtube_transcript}")
        sys.exit(1)

    # Estimate speakers
    try:
        # Load with custom max_chars
        if args.verbose:
            print(f"Loading transcript: {args.youtube_transcript}")

        text = load_youtube_transcript(args.youtube_transcript, max_chars=args.max_chars)

        if args.verbose:
            print(f"Extracted {len(text)} characters")
            print("Calling OpenAI API for speaker estimation...")

        # Estimate speakers using extracted text
        client = OpenAI()
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": "You are analyzing city council meeting transcripts to estimate the number of unique speakers. Look for named speakers (Mayor, Council Members, staff), speaker introductions, public commenters, and conversational patterns."
            }, {
                "role": "user",
                "content": f"""Analyze this city council meeting transcript and estimate the number of unique speakers:

{text}

Identify:
1. Named speakers (with titles like Mayor, Council Member, etc.)
2. Staff members or city employees who speak
3. Public commenters (residents who testify)
4. Estimated total unique speakers based on conversational flow

Remember: City councils typically have 5-10 speakers (mayor, council members, staff, public commenters)."""
            }],
            response_format=SpeakerEstimate
        )

        estimate = completion.choices[0].message.parsed

        # Print results
        video_id = Path(args.youtube_transcript).stem.replace('.en', '')

        print(f"\n{'='*60}")
        print(f"Video ID: {video_id}")
        print(f"{'='*60}")
        print(f"\nNamed Speakers ({len(estimate.named_speakers)}):")
        for speaker in estimate.named_speakers:
            print(f"  - {speaker}")

        print(f"\nEstimated Total Speakers: {estimate.estimated_total_speakers}")
        print(f"Confidence: {estimate.confidence}")
        print(f"\nReasoning: {estimate.reasoning}")

        # Print AssemblyAI config suggestion
        print(f"\n{'='*60}")
        print("Suggested AssemblyAI Configuration:")
        print(f"{'='*60}")
        min_speakers = max(len(estimate.named_speakers), 5)
        max_speakers = estimate.estimated_total_speakers

        print(f"""
speaker_opts = aai.types.SpeakerOptions(
    min_speakers_expected={min_speakers},
    max_speakers_expected={max_speakers}
)""")

        # Export as JSON for programmatic use
        if args.verbose:
            print(f"\n{'='*60}")
            print("JSON Output:")
            print(f"{'='*60}")
            print(json.dumps({
                "video_id": video_id,
                "named_speakers": estimate.named_speakers,
                "estimated_total_speakers": estimate.estimated_total_speakers,
                "confidence": estimate.confidence,
                "reasoning": estimate.reasoning,
                "suggested_min_speakers": min_speakers,
                "suggested_max_speakers": max_speakers
            }, indent=2))

    except Exception as e:
        print(f"Error estimating speakers: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
