#!/usr/bin/env python3
"""
Extract YouTube video IDs from San Rafael meeting pages.

Reads San Rafael event JSON files and extracts YouTube video IDs from meeting pages.

Usage:
    python scripts/extract_sanrafael_video_ids.py
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

def get_latest_events_file() -> Path:
    """Find the most recent San Rafael events file."""
    events_dir = Path("data/events")
    files = list(events_dir.glob("events_city-san-rafael_*.json"))

    if not files:
        raise FileNotFoundError("No San Rafael events files found in data/events/")

    # Sort by modification time, get most recent
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return latest


def load_events(file_path: Path) -> List[Dict]:
    """Load events from JSON file."""
    with open(file_path) as f:
        data = json.load(f)
    return data.get("events", [])


def extract_video_id(meeting_url: str) -> str:
    """
    Extract YouTube video ID from a meeting page.

    Args:
        meeting_url: URL of the meeting page

    Returns:
        YouTube video ID or empty string if not found
    """
    try:
        response = requests.get(meeting_url, timeout=10)
        response.raise_for_status()

        html = response.text

        # Method 1: Look for videoId in JavaScript
        match = re.search(r"videoId:\s*['\"]([^'\"]+)['\"]", html)
        if match:
            return match.group(1)

        # Method 2: Look for YouTube embed URL
        match = re.search(r"youtube\.com/embed/([^\"?]+)", html)
        if match:
            return match.group(1)

        # Method 3: Look for YouTube watch URL
        match = re.search(r"youtube\.com/watch\?v=([^\"&]+)", html)
        if match:
            return match.group(1)

        # Method 4: Look for youtu.be short URL
        match = re.search(r"youtu\.be/([^\"?]+)", html)
        if match:
            return match.group(1)

        return ""

    except Exception as e:
        print(f"  ✗ Error fetching {meeting_url}: {e}", file=sys.stderr)
        return ""


def main():
    """Extract video IDs from San Rafael meetings."""
    print("Finding San Rafael events...")

    # Load events from ALL files (to get historical + future)
    events_dir = Path("data/events")
    files = list(events_dir.glob("events_city-san-rafael_*.json"))

    if not files:
        raise FileNotFoundError("No San Rafael events files found in data/events/")

    print(f"Found {len(files)} San Rafael event files")

    # Collect all events, deduplicate by source_url
    all_events = []
    seen_urls = set()

    for file_path in files:
        events = load_events(file_path)
        for event in events:
            source_url = event.get("source_url") or event.get("scraped_from")
            if source_url and source_url not in seen_urls:
                all_events.append(event)
                seen_urls.add(source_url)

    events = all_events
    print(f"Found {len(events)} unique events")

    # Extract video IDs
    results = []
    for event in events:
        source_url = event.get("source_url") or event.get("scraped_from")
        if not source_url:
            continue

        title = event.get("title", "Unknown")
        when = event.get("when", "Unknown")

        print(f"\nChecking: {title} ({when})")
        print(f"  URL: {source_url}")

        video_id = extract_video_id(source_url)

        if video_id:
            print(f"  ✓ Video ID: {video_id}")
            results.append({
                "video_id": video_id,
                "meeting_url": source_url,
                "title": title,
                "date": when,
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}"
            })
        else:
            print(f"  ✗ No video found")

    # Save results
    if results:
        output_file = Path("data/san_rafael_videos.json")
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n{'='*60}")
        print(f"FOUND {len(results)} MEETINGS WITH VIDEOS")
        print(f"{'='*60}")
        print(f"Saved to: {output_file}")
        print(f"\nVideo IDs:")
        for r in results:
            print(f"  {r['video_id']} - {r['title']}")

        # Also create a simple text file for download_youtube_audio.py
        urls_file = Path("data/san_rafael_youtube_urls.txt")
        with open(urls_file, 'w') as f:
            for r in results:
                f.write(f"{r['youtube_url']}\n")
        print(f"\nYouTube URLs saved to: {urls_file}")

    else:
        print("\n✗ No videos found")
        sys.exit(1)


if __name__ == "__main__":
    main()
