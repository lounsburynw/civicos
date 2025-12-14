#!/usr/bin/env python3
"""
Find San Rafael City Council meetings by testing URL patterns.

San Rafael City Council typically meets on the 1st and 3rd Monday of each month.
This script generates candidate URLs and checks which ones exist and have videos.

Usage:
    python scripts/find_sanrafael_meetings.py
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
import requests
import time

def get_first_and_third_mondays(year: int, month: int):
    """Get the 1st and 3rd Monday of a given month."""
    # First day of the month
    first_day = datetime(year, month, 1)

    # Find first Monday
    days_until_monday = (7 - first_day.weekday()) % 7
    first_monday = first_day + timedelta(days=days_until_monday)

    # Third Monday is 14 days after first Monday
    third_monday = first_monday + timedelta(days=14)

    dates = []
    if first_monday.month == month:
        dates.append(first_monday)
    if third_monday.month == month:
        dates.append(third_monday)

    return dates


def generate_meeting_urls(months_back: int = 12):
    """Generate candidate meeting URLs for the past N months."""
    urls = []
    today = datetime.now()

    for i in range(months_back + 1):  # Include current month
        date = today - timedelta(days=30 * i)
        year = date.year
        month = date.month

        mondays = get_first_and_third_mondays(year, month)

        for monday in mondays:
            if monday <= today:  # Only past/present meetings
                month_name = monday.strftime("%B").lower()
                day = monday.day
                year = monday.year

                url = f"https://www.cityofsanrafael.org/meetings/city-council-{month_name}-{day}-{year}/"
                urls.append((monday, url))

    # Sort by date (newest first)
    urls.sort(reverse=True, key=lambda x: x[0])
    return urls


def check_meeting_exists(url: str):
    """Check if a meeting page exists."""
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False


def extract_video_id(url: str):
    """Extract YouTube video ID from meeting page."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html = response.text

        # Look for videoId in JavaScript
        match = re.search(r"videoId:\s*['\"]([^'\"]+)['\"]", html)
        if match:
            return match.group(1)

        # Look for YouTube embed URL
        match = re.search(r"youtube\.com/embed/([^\"?]+)", html)
        if match:
            return match.group(1)

        return ""
    except:
        return ""


def main():
    """Find San Rafael City Council meetings with videos."""
    print("Generating candidate meeting URLs for past 12 months...")

    candidate_urls = generate_meeting_urls(12)
    print(f"Generated {len(candidate_urls)} candidate URLs")

    results = []
    print("\nChecking each URL...")

    for date, url in candidate_urls:
        print(f"\n{date.strftime('%Y-%m-%d')} - ", end="", flush=True)

        if not check_meeting_exists(url):
            print("✗ Page not found")
            continue

        print("✓ Page exists - ", end="", flush=True)

        video_id = extract_video_id(url)
        if video_id:
            print(f"✓ Video: {video_id}")
            results.append({
                "video_id": video_id,
                "meeting_url": url,
                "date": date.strftime("%Y-%m-%d"),
                "title": f"City Council - {date.strftime('%B %d, %Y')}",
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}"
            })
        else:
            print("✗ No video")

        # Be nice to the server
        time.sleep(0.5)

    # Save results
    if results:
        output_file = Path("data/san_rafael_council_videos.json")
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n{'='*60}")
        print(f"FOUND {len(results)} CITY COUNCIL MEETINGS WITH VIDEOS")
        print(f"{'='*60}")
        print(f"Saved to: {output_file}")

        print(f"\nMeetings:")
        for r in results:
            print(f"  {r['date']} - {r['video_id']}")

        # Create URLs file for download script
        urls_file = Path("data/san_rafael_council_youtube_urls.txt")
        with open(urls_file, 'w') as f:
            for r in results:
                f.write(f"{r['youtube_url']}\n")

        print(f"\nYouTube URLs saved to: {urls_file}")

    else:
        print("\n✗ No meetings with videos found")
        sys.exit(1)


if __name__ == "__main__":
    main()
