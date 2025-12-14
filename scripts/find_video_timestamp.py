#!/usr/bin/env python3
"""
Find video timestamp for specific content in YouTube transcript.

Maps transcript chunks or keywords to approximate video timestamps
based on YouTube JSON3 timing data.

Session: 109
"""

import argparse
import json


def find_timestamp_for_chunk(transcript_path: str, target_chunk: int, total_chunks: int, chunk_size: int = 8000) -> dict:
    """
    Find approximate video timestamp for a transcript chunk.

    Args:
        transcript_path: Path to YouTube JSON3 file
        target_chunk: Which chunk to find timestamp for
        total_chunks: Total number of chunks
        chunk_size: Size of each chunk in characters

    Returns:
        Dictionary with start/end timestamps in seconds
    """
    with open(transcript_path) as f:
        data = json.load(f)

    # Calculate character position for target chunk
    target_char_start = (target_chunk - 1) * chunk_size
    target_char_end = target_chunk * chunk_size

    # Extract timeline
    current_char = 0
    start_time = None
    end_time = None

    for event in data.get("events", []):
        # Get timing from event
        event_start = event.get("tStartMs", 0) / 1000  # Convert ms to seconds

        if "segs" in event:
            for seg in event.get("segs", []):
                if "utf8" in seg:
                    seg_len = len(seg["utf8"])

                    # Check if this segment overlaps with target chunk
                    if start_time is None and current_char <= target_char_start < current_char + seg_len:
                        start_time = event_start

                    if end_time is None and current_char <= target_char_end < current_char + seg_len:
                        end_time = event_start

                    current_char += seg_len

                    if start_time and end_time:
                        break

        if start_time and end_time:
            break

    return {
        "chunk": target_chunk,
        "start_time_seconds": start_time or 0,
        "end_time_seconds": end_time or 0,
        "start_time_formatted": format_timestamp(start_time or 0),
        "end_time_formatted": format_timestamp(end_time or 0),
        "youtube_link_start": f"https://www.youtube.com/watch?v=MpxrGRb16HQ&t={int(start_time or 0)}s",
        "youtube_link_end": f"https://www.youtube.com/watch?v=MpxrGRb16HQ&t={int(end_time or 0)}s"
    }


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def search_keyword(transcript_path: str, keyword: str) -> list:
    """
    Search for keyword and return all matching timestamps.

    Args:
        transcript_path: Path to YouTube JSON3 file
        keyword: Keyword to search for (case-insensitive)

    Returns:
        List of matches with timestamps
    """
    with open(transcript_path) as f:
        data = json.load(f)

    matches = []

    for event in data.get("events", []):
        event_time = event.get("tStartMs", 0) / 1000

        if "segs" in event:
            event_text = "".join(seg.get("utf8", "") for seg in event.get("segs", []))

            if keyword.lower() in event_text.lower():
                matches.append({
                    "time_seconds": event_time,
                    "time_formatted": format_timestamp(event_time),
                    "text": event_text.strip()[:200],  # First 200 chars
                    "youtube_link": f"https://www.youtube.com/watch?v=MpxrGRb16HQ&t={int(event_time)}s"
                })

    return matches


def main():
    parser = argparse.ArgumentParser(
        description="Find video timestamp for transcript content"
    )
    parser.add_argument(
        "--youtube-transcript",
        required=True,
        help="Path to YouTube JSON3 transcript file"
    )
    parser.add_argument(
        "--chunk",
        type=int,
        help="Chunk number to find timestamp for"
    )
    parser.add_argument(
        "--total-chunks",
        type=int,
        default=17,
        help="Total number of chunks"
    )
    parser.add_argument(
        "--search",
        help="Search for keyword and show all timestamps"
    )

    args = parser.parse_args()

    if args.chunk:
        # Find timestamp for specific chunk
        result = find_timestamp_for_chunk(
            args.youtube_transcript,
            args.chunk,
            args.total_chunks
        )

        print("\n" + "=" * 70)
        print(f"VIDEO TIMESTAMP FOR CHUNK {result['chunk']}")
        print("=" * 70)
        print(f"\nStart Time: {result['start_time_formatted']} ({result['start_time_seconds']:.0f}s)")
        print(f"End Time: {result['end_time_formatted']} ({result['end_time_seconds']:.0f}s)")
        print(f"\nYouTube Link (start): {result['youtube_link_start']}")
        print(f"YouTube Link (end): {result['youtube_link_end']}")

    elif args.search:
        # Search for keyword
        matches = search_keyword(args.youtube_transcript, args.search)

        print("\n" + "=" * 70)
        print(f"SEARCH RESULTS FOR: '{args.search}'")
        print("=" * 70)
        print(f"\nFound {len(matches)} matches\n")

        for i, match in enumerate(matches[:10], 1):  # Show first 10
            print(f"{i}. Time: {match['time_formatted']}")
            print(f"   Link: {match['youtube_link']}")
            print(f"   Text: {match['text']}")
            print()

        if len(matches) > 10:
            print(f"... and {len(matches) - 10} more matches")

    else:
        print("Error: Must specify either --chunk or --search")


if __name__ == "__main__":
    main()
