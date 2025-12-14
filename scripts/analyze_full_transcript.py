#!/usr/bin/env python3
"""
Full transcript analysis using chunked LLM processing.

Analyzes entire YouTube transcript to extract:
- All speakers (named)
- Public commenters
- Testimony themes
- Wildfire-related discussion

Uses chunking strategy to handle large transcripts within token limits.

Session: 109
"""

import argparse
import json
import os
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()


class SpeakerMention(BaseModel):
    """Individual speaker mention."""
    name: str = Field(description="Speaker's full name or title")
    role: str = Field(description="Role: 'council', 'staff', 'public', 'unknown'")
    context: str = Field(description="Brief context of what they discussed (1 sentence)")


class TranscriptChunkAnalysis(BaseModel):
    """Analysis of a transcript chunk."""
    speakers_mentioned: List[SpeakerMention] = Field(
        description="All speakers mentioned or speaking in this chunk"
    )
    wildfire_discussion: bool = Field(
        description="Does this chunk contain wildfire/fire prevention discussion?"
    )
    public_comment_section: bool = Field(
        description="Is this chunk from a public comment section?"
    )
    key_topics: List[str] = Field(
        description="Main topics discussed (max 3)",
        max_length=3
    )


def load_full_transcript(transcript_path: str) -> str:
    """Load entire YouTube transcript as text."""
    with open(transcript_path) as f:
        data = json.load(f)

    text = ""
    for event in data.get("events", []):
        if "segs" in event:
            for seg in event.get("segs", []):
                if "utf8" in seg:
                    text += seg["utf8"]

    return text


def chunk_text(text: str, chunk_size: int = 8000, overlap: int = 500) -> List[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: Full text to chunk
        chunk_size: Target size of each chunk
        overlap: Overlap between chunks to preserve context

    Returns:
        List of text chunks
    """
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # If not the last chunk, try to break at sentence boundary
        if end < len(text):
            # Look for period + space within last 200 chars
            last_period = text.rfind(". ", end - 200, end)
            if last_period > start:
                end = last_period + 2

        chunks.append(text[start:end])
        start = end - overlap  # Overlap to preserve context

    return chunks


def analyze_chunk(client: OpenAI, chunk: str, chunk_num: int, total_chunks: int) -> TranscriptChunkAnalysis:
    """Analyze a single chunk of transcript."""

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": """You are analyzing city council meeting transcripts. Extract:
1. All speakers (with names/titles and roles)
2. Whether this section discusses wildfire/fire prevention
3. Whether this is a public comment section
4. Main topics discussed

Be thorough - capture both officials and public commenters."""
        }, {
            "role": "user",
            "content": f"""Analyze this segment from a San Rafael City Council meeting (chunk {chunk_num}/{total_chunks}):

{chunk}

Extract all speakers, identify their roles, note if wildfire is discussed, and identify key topics."""
        }],
        response_format=TranscriptChunkAnalysis
    )

    return completion.choices[0].message.parsed


def analyze_full_transcript(transcript_path: str, verbose: bool = False) -> Dict:
    """
    Analyze complete transcript using chunking.

    Returns:
        Complete analysis with all speakers and themes
    """
    if verbose:
        print(f"Loading transcript: {transcript_path}")

    # Load full transcript
    full_text = load_full_transcript(transcript_path)

    if verbose:
        print(f"Total size: {len(full_text):,} characters")

    # Chunk the text
    chunks = chunk_text(full_text, chunk_size=8000, overlap=500)

    if verbose:
        print(f"Split into {len(chunks)} chunks")
        print(f"Analyzing with OpenAI...")

    # Analyze each chunk
    client = OpenAI()
    all_speakers = {}
    wildfire_chunks = []
    public_comment_chunks = []
    all_topics = []

    for i, chunk in enumerate(chunks, 1):
        if verbose and i % 10 == 0:
            print(f"  Processed {i}/{len(chunks)} chunks...")

        try:
            analysis = analyze_chunk(client, chunk, i, len(chunks))

            # Collect speakers
            for speaker in analysis.speakers_mentioned:
                key = speaker.name.lower().strip()
                if key not in all_speakers:
                    all_speakers[key] = {
                        "name": speaker.name,
                        "role": speaker.role,
                        "mentions": 0,
                        "contexts": []
                    }
                all_speakers[key]["mentions"] += 1
                all_speakers[key]["contexts"].append({
                    "chunk": i,
                    "context": speaker.context
                })

            # Track wildfire discussion
            if analysis.wildfire_discussion:
                wildfire_chunks.append(i)

            # Track public comment sections
            if analysis.public_comment_section:
                public_comment_chunks.append(i)

            # Collect topics
            all_topics.extend(analysis.key_topics)

        except Exception as e:
            if verbose:
                print(f"  Warning: Error analyzing chunk {i}: {e}")
            continue

    if verbose:
        print(f"Analysis complete!")

    # Count unique topics
    from collections import Counter
    topic_counts = Counter(all_topics)

    return {
        "total_chunks": len(chunks),
        "total_speakers": len(all_speakers),
        "speakers": all_speakers,
        "wildfire_chunks": wildfire_chunks,
        "public_comment_chunks": public_comment_chunks,
        "top_topics": topic_counts.most_common(10),
        "total_chars_analyzed": len(full_text)
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze full YouTube transcript using chunked LLM processing"
    )
    parser.add_argument(
        "--youtube-transcript",
        required=True,
        help="Path to YouTube JSON3 transcript file"
    )
    parser.add_argument(
        "--output",
        help="Path to save analysis JSON (optional)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress"
    )

    args = parser.parse_args()

    # Run analysis
    result = analyze_full_transcript(args.youtube_transcript, verbose=args.verbose)

    # Print summary
    print("\n" + "=" * 70)
    print("FULL TRANSCRIPT ANALYSIS")
    print("=" * 70)

    print(f"\nTotal Characters Analyzed: {result['total_chars_analyzed']:,}")
    print(f"Total Chunks Processed: {result['total_chunks']}")
    print(f"Total Unique Speakers: {result['total_speakers']}")

    # Speakers by role
    roles = {}
    for speaker_data in result['speakers'].values():
        role = speaker_data['role']
        if role not in roles:
            roles[role] = []
        roles[role].append(speaker_data)

    print(f"\nSpeakers by Role:")
    for role in ['council', 'staff', 'public', 'unknown']:
        if role in roles:
            print(f"\n  {role.upper()} ({len(roles[role])} speakers):")
            for speaker in sorted(roles[role], key=lambda x: x['mentions'], reverse=True):
                print(f"    - {speaker['name']} ({speaker['mentions']} mentions)")

    # Wildfire discussion
    print(f"\nWildfire Discussion:")
    print(f"  Found in {len(result['wildfire_chunks'])} chunks")
    if result['wildfire_chunks']:
        print(f"  Chunk range: {min(result['wildfire_chunks'])}-{max(result['wildfire_chunks'])}")
        print(f"  Approximate location: {(min(result['wildfire_chunks']) / result['total_chunks']) * 100:.1f}% through meeting")

    # Public comment
    print(f"\nPublic Comment Sections:")
    print(f"  Found in {len(result['public_comment_chunks'])} chunks")
    if result['public_comment_chunks']:
        print(f"  Chunk range: {result['public_comment_chunks']}")

    # Top topics
    print(f"\nTop Topics:")
    for topic, count in result['top_topics'][:10]:
        print(f"  - {topic} ({count} mentions)")

    # Save output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n✅ Full analysis saved to: {args.output}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
