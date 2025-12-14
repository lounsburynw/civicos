#!/usr/bin/env python3
"""
AssemblyAI Batch Upload Script

Uploads audio files to AssemblyAI for transcription with speaker diarization.
Supports both single file and batch processing.

Usage:
    # Single file
    python scripts/assemblyai_batch_upload.py \
        --audio-file data/test_bottleneck/MpxrGRb16HQ_compressed.mp3 \
        --video-id MpxrGRb16HQ \
        --meeting-url "https://www.cityofsanrafael.org/meetings/city-council-october-6-2025/"

    # Batch processing
    python scripts/assemblyai_batch_upload.py \
        --audio-dir data/youtube_audio \
        --output-dir data/testimony \
        --max-concurrent 5

Cost: $0.02/minute (transcription $0.015 + diarization $0.005)
2-hour meeting = $2.40
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import time

try:
    import assemblyai as aai
except ImportError:
    print("Error: assemblyai package not found. Install with: pip install assemblyai")
    sys.exit(1)

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
COST_PER_MINUTE = 0.02  # $0.015 transcription + $0.005 diarization
DEFAULT_OUTPUT_DIR = "data/testimony"


def setup_assemblyai() -> None:
    """Configure AssemblyAI with API key from environment."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        print("Error: ASSEMBLYAI_API_KEY not found in environment")
        print("Add to .env file or set environment variable")
        sys.exit(1)

    aai.settings.api_key = api_key
    print(f"✓ AssemblyAI configured (key: {api_key[:10]}...)")


def transcribe_audio(
    audio_path: str,
    video_id: Optional[str] = None,
    meeting_url: Optional[str] = None,
    verbose: bool = True
) -> Dict:
    """
    Transcribe audio file with speaker diarization.

    Args:
        audio_path: Path to audio file (MP3, WAV, etc.)
        video_id: YouTube video ID (for metadata)
        meeting_url: Meeting URL (for metadata)
        verbose: Print progress messages

    Returns:
        Dict with transcription results in expected format
    """
    if verbose:
        print(f"\nProcessing: {audio_path}")
        print(f"  Video ID: {video_id}")
        print(f"  Meeting URL: {meeting_url}")

    # Configure transcription with speaker diarization
    # Use min/max range to guide clustering algorithm without over-constraining
    speaker_opts = aai.types.SpeakerOptions(
        min_speakers_expected=5,   # Minimum: mayor + council members
        max_speakers_expected=10   # Maximum: council + staff + public commenters
    )

    config = aai.TranscriptionConfig(
        speaker_labels=True,  # Enable speaker diarization
        speaker_options=speaker_opts,  # Provide range for clustering algorithm
        language_code="en"
    )

    # Create transcriber and submit
    transcriber = aai.Transcriber()

    if verbose:
        print(f"  Uploading to AssemblyAI...")

    start_time = time.time()
    transcript = transcriber.transcribe(audio_path, config=config)

    # Wait for completion (SDK handles polling)
    if verbose:
        print(f"  Transcribing (this may take 5-10 minutes)...")

    # Check for errors
    if transcript.status == aai.TranscriptStatus.error:
        raise Exception(f"Transcription failed: {transcript.error}")

    processing_time = time.time() - start_time

    # Calculate duration and cost
    audio_duration_seconds = transcript.audio_duration  # seconds (not milliseconds!)
    audio_duration_minutes = audio_duration_seconds / 60
    cost_usd = audio_duration_minutes * COST_PER_MINUTE

    # Count unique speakers
    speakers = set()
    utterances = []

    if transcript.utterances:
        for utt in transcript.utterances:
            speakers.add(utt.speaker)
            utterances.append({
                "speaker": utt.speaker,
                "text": utt.text,
                "start": utt.start,  # milliseconds
                "end": utt.end
            })

    # Build result in expected format
    result = {
        "video_id": video_id or Path(audio_path).stem,
        "meeting_url": meeting_url or "",
        "speakers_count": len(speakers),
        "utterances_count": len(utterances),
        "utterances": utterances,
        "audio_duration_minutes": round(audio_duration_minutes, 2),
        "language": "en",
        "processed_at": datetime.now().isoformat(),
        "processing_service": "assemblyai",
        "assemblyai_id": transcript.id,
        "cost_usd": round(cost_usd, 2),
        "processing_time_seconds": round(processing_time, 2)
    }

    if verbose:
        print(f"  ✓ Complete!")
        print(f"    Duration: {audio_duration_minutes:.1f} minutes")
        print(f"    Speakers: {len(speakers)}")
        print(f"    Utterances: {len(utterances)}")
        print(f"    Cost: ${cost_usd:.2f}")
        print(f"    Processing time: {processing_time:.1f} seconds")

    return result


def save_result(result: Dict, output_dir: str, filename: Optional[str] = None) -> str:
    """
    Save transcription result to JSON file.

    Args:
        result: Transcription result dict
        output_dir: Directory to save to
        filename: Optional custom filename (defaults to testimony_{video_id}.json)

    Returns:
        Path to saved file
    """
    os.makedirs(output_dir, exist_ok=True)

    if not filename:
        video_id = result.get("video_id", "unknown")
        filename = f"testimony_{video_id}.json"

    output_path = os.path.join(output_dir, filename)

    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"  Saved: {output_path}")
    return output_path


def extract_video_id_from_filename(filename: str) -> str:
    """
    Extract YouTube video ID from filename.

    Examples:
        MpxrGRb16HQ_compressed.mp3 -> MpxrGRb16HQ
        MpxrGRb16HQ_original.mp3 -> MpxrGRb16HQ
        abc123.mp3 -> abc123
    """
    # Remove extension
    name = Path(filename).stem

    # Remove common suffixes
    for suffix in ["_compressed", "_original", "_audio"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    return name


def process_single_file(
    audio_file: str,
    video_id: Optional[str] = None,
    meeting_url: Optional[str] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    verbose: bool = True
) -> Dict:
    """Process a single audio file."""

    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    # Auto-extract video ID from filename if not provided
    if not video_id:
        video_id = extract_video_id_from_filename(audio_file)
        if verbose:
            print(f"Auto-detected video ID: {video_id}")

    # Transcribe
    result = transcribe_audio(audio_file, video_id, meeting_url, verbose=verbose)

    # Save
    output_path = save_result(result, output_dir)

    return result


def process_batch(
    audio_dir: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    max_concurrent: int = 5,
    verbose: bool = True
) -> List[Dict]:
    """
    Process all audio files in a directory.

    Note: AssemblyAI SDK doesn't support true concurrent uploads,
    but processes them sequentially with progress tracking.

    Args:
        audio_dir: Directory containing audio files
        output_dir: Directory to save results
        max_concurrent: Not used (sequential processing)
        verbose: Print progress

    Returns:
        List of transcription results
    """
    if not os.path.exists(audio_dir):
        raise FileNotFoundError(f"Audio directory not found: {audio_dir}")

    # Find all audio files
    audio_files = []
    for ext in [".mp3", ".wav", ".m4a", ".flac"]:
        audio_files.extend(Path(audio_dir).glob(f"*{ext}"))

    if not audio_files:
        print(f"No audio files found in {audio_dir}")
        return []

    print(f"\nFound {len(audio_files)} audio files to process")
    print(f"Output directory: {output_dir}")
    print(f"Estimated cost: ${len(audio_files) * 2.40:.2f} (assuming 2-hour meetings)")
    print()

    results = []
    total_cost = 0.0

    for i, audio_file in enumerate(audio_files, 1):
        print(f"\n[{i}/{len(audio_files)}] Processing {audio_file.name}")

        try:
            result = process_single_file(
                str(audio_file),
                output_dir=output_dir,
                verbose=verbose
            )
            results.append(result)
            total_cost += result.get("cost_usd", 0)

        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue

    # Print summary
    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 60)
    print(f"Files processed: {len(results)}/{len(audio_files)}")
    print(f"Total speakers: {sum(r.get('speakers_count', 0) for r in results)}")
    print(f"Total utterances: {sum(r.get('utterances_count', 0) for r in results)}")
    print(f"Total duration: {sum(r.get('audio_duration_minutes', 0) for r in results):.1f} minutes")
    print(f"Total cost: ${total_cost:.2f}")
    print("=" * 60)

    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Upload audio files to AssemblyAI for transcription with speaker diarization"
    )

    # Single file mode
    parser.add_argument(
        "--audio-file",
        help="Single audio file to process"
    )
    parser.add_argument(
        "--video-id",
        help="YouTube video ID (auto-detected from filename if not provided)"
    )
    parser.add_argument(
        "--meeting-url",
        help="Meeting URL for metadata"
    )

    # Batch mode
    parser.add_argument(
        "--audio-dir",
        help="Directory containing audio files for batch processing"
    )

    # Common options
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for JSON results (default: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent uploads (default: 5, currently not used - sequential processing)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.audio_file and not args.audio_dir:
        parser.error("Must specify either --audio-file or --audio-dir")

    if args.audio_file and args.audio_dir:
        parser.error("Cannot specify both --audio-file and --audio-dir")

    # Setup AssemblyAI
    setup_assemblyai()

    # Process
    try:
        if args.audio_file:
            # Single file mode
            process_single_file(
                args.audio_file,
                video_id=args.video_id,
                meeting_url=args.meeting_url,
                output_dir=args.output_dir,
                verbose=not args.quiet
            )
        else:
            # Batch mode
            process_batch(
                args.audio_dir,
                output_dir=args.output_dir,
                max_concurrent=args.max_concurrent,
                verbose=not args.quiet
            )

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
