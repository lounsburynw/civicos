#!/usr/bin/env python3
"""
Test hybrid YouTube → Modal workflow to identify bottlenecks.

This script measures each step:
1. Download audio locally (with yt-dlp)
2. Compress audio (16kHz mono for faster upload)
3. Upload to Modal
4. Process with WhisperX on GPU
5. Download results

Usage:
    python scripts/test_hybrid_bottleneck.py --url "https://www.cityofsanrafael.org/meetings/..."

    # Or test with direct YouTube URL
    python scripts/test_hybrid_bottleneck.py --video-id "dQw4w9WgXcQ"
"""

import argparse
import os
import sys
import time
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional
import requests
from bs4 import BeautifulSoup
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def timer(func):
    """Decorator to time function execution."""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        return result, elapsed
    return wrapper


def format_size(bytes_size: int) -> str:
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


def format_time(seconds: float) -> str:
    """Format seconds to human readable."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


@timer
def extract_video_id(meeting_url: str) -> str:
    """Extract YouTube video ID from San Rafael meeting page."""
    print(f"\n🔍 Extracting video ID from: {meeting_url}")

    response = requests.get(meeting_url, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')

    # Try iframe embed
    iframe = soup.find('iframe', src=re.compile(r'youtube\.com/embed/'))
    if iframe:
        video_id = iframe['src'].split('/')[-1].split('?')[0]
        print(f"   ✅ Found video ID: {video_id}")
        return video_id

    # Try regex in page source
    youtube_pattern = r'youtube\.com/(?:watch\?v=|embed/)([a-zA-Z0-9_-]+)'
    match = re.search(youtube_pattern, response.text)
    if match:
        video_id = match.group(1)
        print(f"   ✅ Found video ID: {video_id}")
        return video_id

    raise ValueError(f"No YouTube video found on {meeting_url}")


@timer
def download_audio(video_id: str, output_path: str, cookies_file: Optional[str] = None) -> Dict:
    """Download audio from YouTube using yt-dlp."""
    print(f"\n📥 Downloading audio for video: {video_id}")

    url = f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        'yt-dlp',
        '--format', 'bestaudio/best',
        '--extract-audio',
        '--audio-format', 'mp3',
        '--audio-quality', '128k',
        '--output', output_path.replace('.mp3', ''),
        '--no-warnings',
        '--quiet',
        '--progress',
    ]

    if cookies_file and os.path.exists(cookies_file):
        cmd.extend(['--cookies', cookies_file])
        print(f"   🔑 Using cookies: {cookies_file}")

    cmd.append(url)

    # Run download
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")

    if not os.path.exists(output_path):
        raise RuntimeError(f"Downloaded file not found: {output_path}")

    size = os.path.getsize(output_path)
    print(f"   ✅ Downloaded: {format_size(size)}")

    return {
        'path': output_path,
        'size_bytes': size,
        'size_human': format_size(size)
    }


@timer
def compress_audio(input_path: str, output_path: str) -> Dict:
    """Compress audio to 16kHz mono for faster upload (WhisperX compatible)."""
    print(f"\n🗜️  Compressing audio...")
    print(f"   Input: {format_size(os.path.getsize(input_path))}")

    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-ar', '16000',  # 16kHz sample rate (WhisperX works fine)
        '-ac', '1',       # Mono
        '-y',             # Overwrite
        '-loglevel', 'error',
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)
    compression_ratio = (1 - compressed_size / original_size) * 100

    print(f"   ✅ Compressed: {format_size(compressed_size)} ({compression_ratio:.1f}% smaller)")

    return {
        'path': output_path,
        'size_bytes': compressed_size,
        'size_human': format_size(compressed_size),
        'original_size': original_size,
        'compression_ratio': compression_ratio
    }


@timer
def upload_to_modal(audio_path: str, video_id: str) -> str:
    """
    Prepare audio for Modal (simulated upload timing).

    Note: We actually pass audio bytes directly to Modal function,
    but this step measures the "upload" time by reading the file.
    """
    print(f"\n☁️  Preparing for Modal upload...")
    print(f"   File: {format_size(os.path.getsize(audio_path))}")

    # Read file to simulate upload bandwidth
    with open(audio_path, 'rb') as f:
        audio_data = f.read()

    print(f"   ✅ Ready for Modal: {format_size(len(audio_data))}")
    print(f"   📝 Note: Audio will be passed as bytes to Modal function")

    return audio_path


@timer
def process_on_modal(audio_path: str, video_id: str) -> Dict:
    """Process audio on Modal with WhisperX + diarization."""
    print(f"\n🎙️  Processing on Modal GPU...")

    try:
        import modal

        print(f"   Loading audio file...")
        with open(audio_path, 'rb') as f:
            audio_data = f.read()

        file_size_mb = len(audio_data) / (1024*1024)
        print(f"   Audio size: {file_size_mb:.1f} MB")

        # Import the Modal app
        print(f"   Loading Modal function...")
        from scripts.modal_youtube_testimony import extract_testimony_from_file

        print(f"   Submitting to Modal A10G GPU...")
        print(f"   (This may take 5-15 minutes depending on audio length)")

        # Call Modal function with audio data
        result = extract_testimony_from_file.remote(audio_data, video_id)

        if 'error' in result:
            print(f"   ❌ Processing failed: {result['error']}")
        else:
            print(f"   ✅ Processing complete")
            print(f"      Speakers: {result.get('speakers_count', 0)}")
            print(f"      Utterances: {result.get('utterances_count', 0)}")

        return result

    except ImportError as e:
        print(f"   ⚠️  Modal not configured: {e}")
        print(f"   Run: modal token new")
        return {
            'error': 'Modal not configured',
            'video_id': video_id
        }
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {
            'error': str(e),
            'video_id': video_id
        }


def print_summary(results: Dict):
    """Print detailed bottleneck analysis."""
    print(f"\n{'='*70}")
    print(f"📊 BOTTLENECK ANALYSIS")
    print(f"{'='*70}")

    total_time = sum(r['time'] for r in results.values() if 'time' in r)

    # Sort by time
    sorted_steps = sorted(
        [(k, v['time']) for k, v in results.items() if 'time' in v],
        key=lambda x: x[1],
        reverse=True
    )

    print(f"\n⏱️  Time Breakdown (Total: {format_time(total_time)}):\n")

    for step, duration in sorted_steps:
        percentage = (duration / total_time * 100) if total_time > 0 else 0
        bar_length = int(percentage / 2)  # 50 chars max
        bar = '█' * bar_length + '░' * (50 - bar_length)

        emoji = {
            'extract_video_id': '🔍',
            'download': '📥',
            'compress': '🗜️',
            'upload': '☁️',
            'process': '🎙️'
        }.get(step, '•')

        print(f"  {emoji} {step:20s} {format_time(duration):>8s}  {bar} {percentage:>5.1f}%")

    # File sizes
    print(f"\n📦 File Sizes:\n")
    if 'download' in results:
        print(f"  Original MP3:    {results['download']['data']['size_human']}")
    if 'compress' in results:
        comp = results['compress']['data']
        print(f"  Compressed:      {comp['size_human']} ({comp['compression_ratio']:.1f}% reduction)")

    # Bottleneck identification
    print(f"\n🔴 Primary Bottleneck: {sorted_steps[0][0].upper()}")

    if sorted_steps[0][0] == 'upload':
        upload_time = sorted_steps[0][1]
        upload_size = results.get('compress', results.get('download', {})).get('data', {}).get('size_bytes', 0)
        if upload_size > 0:
            upload_speed_mbps = (upload_size * 8 / 1_000_000) / upload_time
            print(f"  Upload speed: {upload_speed_mbps:.1f} Mbps")
            print(f"\n💡 Optimization: Compress further or use faster internet connection")

    elif sorted_steps[0][0] == 'download':
        print(f"\n💡 Optimization: Download multiple videos in parallel")

    elif sorted_steps[0][0] == 'process':
        print(f"\n💡 Optimization: Processing is GPU-bound (already optimal)")

    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Test hybrid YouTube→Modal bottlenecks")
    parser.add_argument('--url', help='San Rafael meeting URL')
    parser.add_argument('--video-id', help='YouTube video ID (skip URL extraction)')
    parser.add_argument('--cookies', default='~/Downloads/www.youtube.com_cookies.txt',
                       help='YouTube cookies file')
    parser.add_argument('--skip-compression', action='store_true',
                       help='Skip compression step (test uncompressed upload)')
    parser.add_argument('--output-dir', default='data/test_bottleneck',
                       help='Output directory for files')

    args = parser.parse_args()

    if not args.url and not args.video_id:
        parser.error("Must provide either --url or --video-id")

    # Expand paths
    cookies_file = os.path.expanduser(args.cookies)
    if not os.path.exists(cookies_file):
        print(f"⚠️  Cookies file not found: {cookies_file}")
        cookies_file = None

    os.makedirs(args.output_dir, exist_ok=True)

    results = {}

    try:
        # Step 1: Extract video ID (if needed)
        if args.url:
            video_id, elapsed = extract_video_id(args.url)
            results['extract_video_id'] = {'time': elapsed, 'data': {'video_id': video_id}}
        else:
            video_id = args.video_id

        # Step 2: Download audio
        download_path = os.path.join(args.output_dir, f"{video_id}_original.mp3")
        download_data, elapsed = download_audio(video_id, download_path, cookies_file)
        results['download'] = {'time': elapsed, 'data': download_data}

        # Step 3: Compress audio (optional)
        if not args.skip_compression:
            compressed_path = os.path.join(args.output_dir, f"{video_id}_compressed.mp3")
            compress_data, elapsed = compress_audio(download_path, compressed_path)
            results['compress'] = {'time': elapsed, 'data': compress_data}
            audio_for_upload = compressed_path
        else:
            audio_for_upload = download_path

        # Step 4: Upload to Modal
        remote_path, elapsed = upload_to_modal(audio_for_upload, video_id)
        results['upload'] = {'time': elapsed, 'data': {'remote_path': remote_path}}

        # Step 5: Process on Modal
        process_result, elapsed = process_on_modal(audio_for_upload, video_id)
        results['process'] = {'time': elapsed, 'data': process_result}

        # Save results
        results_file = os.path.join(args.output_dir, f"bottleneck_analysis_{video_id}.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        # Print summary
        print_summary(results)

        print(f"✅ Results saved to: {results_file}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
