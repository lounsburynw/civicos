#!/usr/bin/env python3
"""
Download YouTube audio from San Rafael meetings for Modal processing.

This script runs locally with your browser cookies to bypass YouTube's
cloud IP detection. Downloaded files are then uploaded to Modal for
GPU-accelerated processing.

Usage:
    # Download all meetings
    python scripts/download_youtube_audio.py --urls-file data/san_rafael_meetings.txt

    # Download specific URLs
    python scripts/download_youtube_audio.py --urls url1 url2 url3

    # Use custom cookies file
    python scripts/download_youtube_audio.py --urls-file meetings.txt --cookies ~/Downloads/youtube_cookies.txt
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict
import yt_dlp
import requests
from bs4 import BeautifulSoup
import re


def extract_video_id(meeting_url: str) -> str:
    """Extract YouTube video ID from San Rafael meeting page."""
    try:
        response = requests.get(meeting_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Try iframe embed
        iframe = soup.find('iframe', src=re.compile(r'youtube\.com/embed/'))
        if iframe:
            video_id = iframe['src'].split('/')[-1].split('?')[0]
            return video_id

        # Try regex in page source
        youtube_pattern = r'youtube\.com/(?:watch\?v=|embed/)([a-zA-Z0-9_-]+)'
        match = re.search(youtube_pattern, response.text)
        if match:
            return match.group(1)

        raise ValueError(f"No YouTube video found on {meeting_url}")

    except Exception as e:
        raise ValueError(f"Failed to extract video ID from {meeting_url}: {e}")


def download_audio(video_id: str, output_dir: str, cookies_file: str = None) -> Dict:
    """Download audio from YouTube video."""

    output_path = os.path.join(output_dir, f"{video_id}.mp3")

    # Skip if already downloaded
    if os.path.exists(output_path):
        file_size_mb = os.path.getsize(output_path) / (1024*1024)
        print(f"   ⏭️  Already exists: {video_id}.mp3 ({file_size_mb:.1f} MB)")
        return {
            "video_id": video_id,
            "status": "skipped",
            "file_path": output_path,
            "file_size_mb": file_size_mb
        }

    try:
        url = f"https://www.youtube.com/watch?v={video_id}"

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'outtmpl': os.path.join(output_dir, video_id),
            'quiet': False,
            'no_warnings': False,
        }

        # Add cookies if provided
        if cookies_file and os.path.exists(cookies_file):
            ydl_opts['cookiefile'] = cookies_file
            print(f"   🔑 Using cookies from: {cookies_file}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            duration_mins = info.get('duration', 0) // 60

        file_size_mb = os.path.getsize(output_path) / (1024*1024)
        print(f"   ✅ Downloaded: {duration_mins} min, {file_size_mb:.1f} MB")

        return {
            "video_id": video_id,
            "status": "success",
            "file_path": output_path,
            "file_size_mb": file_size_mb,
            "duration_minutes": duration_mins
        }

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {
            "video_id": video_id,
            "status": "error",
            "error": str(e)
        }


def main():
    parser = argparse.ArgumentParser(description="Download YouTube audio for Modal processing")
    parser.add_argument('--urls-file', help='File with meeting URLs (one per line)')
    parser.add_argument('--urls', nargs='+', help='Meeting URLs')
    parser.add_argument('--cookies', default='~/Downloads/www.youtube.com_cookies.txt',
                       help='Path to YouTube cookies file (default: ~/Downloads/www.youtube.com_cookies.txt)')
    parser.add_argument('--output-dir', default='data/youtube_audio',
                       help='Output directory for audio files (default: data/youtube_audio)')

    args = parser.parse_args()

    # Load URLs
    if args.urls_file:
        with open(args.urls_file) as f:
            meeting_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    elif args.urls:
        meeting_urls = args.urls
    else:
        print("❌ Must provide either --urls-file or --urls")
        sys.exit(1)

    # Expand cookies path
    cookies_file = os.path.expanduser(args.cookies)
    if not os.path.exists(cookies_file):
        print(f"⚠️  Warning: Cookies file not found at {cookies_file}")
        print("   Downloads may fail due to YouTube bot detection")
        cookies_file = None
    else:
        print(f"✅ Found cookies file: {cookies_file}")

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"📥 DOWNLOADING AUDIO: {len(meeting_urls)} meetings")
    print(f"   Output: {args.output_dir}")
    print(f"   Cookies: {cookies_file or 'None (may fail)'}")
    print(f"{'='*70}\n")

    results = []

    for i, meeting_url in enumerate(meeting_urls, 1):
        print(f"\n[{i}/{len(meeting_urls)}] Processing: {meeting_url}")

        # Extract video ID
        try:
            print("   🔍 Extracting video ID...")
            video_id = extract_video_id(meeting_url)
            print(f"   ✅ Found video ID: {video_id}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({
                "meeting_url": meeting_url,
                "status": "error",
                "error": str(e)
            })
            continue

        # Download audio
        print("   📥 Downloading audio...")
        result = download_audio(video_id, args.output_dir, cookies_file)
        result['meeting_url'] = meeting_url
        results.append(result)

    # Summary
    success = sum(1 for r in results if r['status'] == 'success')
    skipped = sum(1 for r in results if r['status'] == 'skipped')
    errors = sum(1 for r in results if r['status'] == 'error')

    print(f"\n{'='*70}")
    print(f"📊 DOWNLOAD COMPLETE")
    print(f"   Success: {success}")
    print(f"   Skipped: {skipped}")
    print(f"   Errors: {errors}")
    print(f"   Total: {len(results)}")
    print(f"{'='*70}\n")

    # Save manifest
    manifest_path = os.path.join(args.output_dir, 'download_manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"✅ Manifest saved: {manifest_path}")

    if errors > 0:
        print("\n⚠️  Some downloads failed. Check the manifest for details.")
        sys.exit(1)


if __name__ == '__main__':
    main()
