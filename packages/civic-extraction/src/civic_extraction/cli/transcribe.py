"""
Transcription command for civic-extract CLI.

Transcribes audio files using AssemblyAI with speaker diarization.

Usage:
    civic-extract transcribe --jurisdiction city-san-rafael
    civic-extract transcribe --jurisdiction city-san-rafael --schedule
    civic-extract transcribe --jurisdiction city-san-rafael --dry-run
    civic-extract transcribe --jurisdiction city-san-rafael --limit 5

Cost: $0.02/minute ($0.015 transcription + $0.005 diarization)
2-hour meeting = $2.40
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Constants
COST_PER_MINUTE = 0.02  # $0.015 transcription + $0.005 diarization


@dataclass
class TranscribeResult:
    """Result of a transcription."""

    video_id: str
    status: str  # "success", "skipped", "error"
    file_path: Optional[str] = None
    speakers_count: Optional[int] = None
    utterances_count: Optional[int] = None
    duration_minutes: Optional[float] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None


@dataclass
class TranscribeCheckpoint:
    """Checkpoint for transcription progress."""

    jurisdiction_id: str
    last_video_id: str
    items_processed: int
    items_transcribed: int
    items_skipped: int
    items_failed: int
    total_cost_usd: float
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TranscribeCheckpoint":
        return cls(**data)


def add_transcribe_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the transcribe subcommand to the parser."""
    parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe audio files with speaker diarization",
        description="Transcribe audio files using AssemblyAI with speaker diarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--input-dir",
        default="data/youtube_audio",
        help="Directory containing audio files (default: data/youtube_audio)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/testimony",
        help="Directory for transcript files (default: data/testimony)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show files that would be transcribed, don't actually transcribe",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on schedule (daily at 9am) instead of once",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="data/checkpoints",
        help="Directory for checkpoint files (default: data/checkpoints)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of files to transcribe (0 = no limit, default: 0)",
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=5,
        help="Minimum expected speakers for diarization (default: 5)",
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        default=10,
        help="Maximum expected speakers for diarization (default: 10)",
    )


def run_transcribe(args: argparse.Namespace) -> int:
    """Run the transcribe command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.schedule:
        run_scheduled(
            args.jurisdiction,
            args.input_dir,
            args.output_dir,
            args.checkpoint_dir,
            args.min_speakers,
            args.max_speakers,
        )
        return 0  # Never reached (scheduler runs forever)
    else:
        results = run_transcription(
            args.jurisdiction,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
            dry_run=args.dry_run,
            limit=args.limit,
            min_speakers=args.min_speakers,
            max_speakers=args.max_speakers,
        )

        if results is None and not args.dry_run:
            return 1

        return 0


def setup_assemblyai() -> bool:
    """
    Configure AssemblyAI with API key from environment.

    Returns:
        True if configured successfully, False otherwise
    """
    try:
        import assemblyai as aai
    except ImportError:
        logger.error("assemblyai package not found. Run: pip install assemblyai")
        return False

    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        logger.error("ASSEMBLYAI_API_KEY not found in environment")
        logger.error("Add to .env file or set environment variable")
        return False

    aai.settings.api_key = api_key
    logger.info(f"AssemblyAI configured (key: {api_key[:10]}...)")
    return True


def find_audio_files(jurisdiction_id: str, input_dir: str) -> Optional[List[Path]]:
    """
    Find audio files for a jurisdiction.

    First tries to use the manifest from audio command, then falls back
    to finding all .mp3 files in the directory.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        input_dir: Directory containing audio files

    Returns:
        List of audio file paths or None if none found
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        logger.error(f"Input directory not found: {input_dir}")
        logger.error("Run 'civic-extract audio' first to download audio files")
        return None

    # Try to load manifest first (ordered list from audio command)
    manifest_file = input_path / f"{jurisdiction_id.replace('-', '_')}_manifest.json"
    if manifest_file.exists():
        try:
            with open(manifest_file) as f:
                manifest = json.load(f)
            # Extract video IDs from manifest
            audio_files = []
            for item in manifest:
                video_id = item.get("video_id")
                if video_id:
                    audio_path = input_path / f"{video_id}.mp3"
                    if audio_path.exists():
                        audio_files.append(audio_path)
            if audio_files:
                logger.info(f"Loaded {len(audio_files)} files from manifest")
                return audio_files
        except Exception as e:
            logger.warning(f"Error loading manifest: {e}")

    # Fall back to finding all .mp3 files
    audio_files = sorted(input_path.glob("*.mp3"))
    if not audio_files:
        logger.error(f"No audio files found in {input_dir}")
        logger.error("Run 'civic-extract audio' first to download audio files")
        return None

    logger.info(f"Found {len(audio_files)} audio files in {input_dir}")
    return audio_files


def checkpoint_path_for_transcribe(jurisdiction_id: str, checkpoint_dir: str) -> Path:
    """Get checkpoint file path for transcription."""
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"transcribe_{jurisdiction_id}.json"


def save_checkpoint(checkpoint: TranscribeCheckpoint, path: Path) -> None:
    """Save checkpoint to file."""
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: Path) -> Optional[TranscribeCheckpoint]:
    """Load checkpoint from file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return TranscribeCheckpoint.from_dict(data)
    except Exception as e:
        logger.warning(f"Error loading checkpoint: {e}")
        return None


def transcript_exists(video_id: str, output_dir: str) -> bool:
    """Check if transcript already exists for a video."""
    output_path = Path(output_dir) / f"testimony_{video_id}.json"
    return output_path.exists()


def transcribe_audio_file(
    audio_path: Path,
    output_dir: str,
    min_speakers: int = 5,
    max_speakers: int = 10,
) -> TranscribeResult:
    """
    Transcribe an audio file with AssemblyAI.

    Args:
        audio_path: Path to audio file
        output_dir: Directory to save transcript
        min_speakers: Minimum expected speakers
        max_speakers: Maximum expected speakers

    Returns:
        TranscribeResult with status and details
    """
    import time

    try:
        import assemblyai as aai
    except ImportError:
        return TranscribeResult(
            video_id=audio_path.stem,
            status="error",
            error="assemblyai not installed",
        )

    video_id = audio_path.stem

    # Skip if already transcribed
    output_path = Path(output_dir) / f"testimony_{video_id}.json"
    if output_path.exists():
        logger.info(f"  Skipping (already transcribed): {video_id}")
        return TranscribeResult(
            video_id=video_id,
            status="skipped",
            file_path=str(output_path),
        )

    try:
        logger.info(f"  Uploading to AssemblyAI...")

        # Configure transcription with speaker diarization
        speaker_opts = aai.types.SpeakerOptions(
            min_speakers_expected=min_speakers,
            max_speakers_expected=max_speakers,
        )

        config = aai.TranscriptionConfig(
            speaker_labels=True,
            speaker_options=speaker_opts,
            language_code="en",
        )

        # Create transcriber and submit
        transcriber = aai.Transcriber()
        start_time = time.time()

        logger.info(f"  Transcribing (this may take 5-10 minutes)...")
        transcript = transcriber.transcribe(str(audio_path), config=config)

        # Check for errors
        if transcript.status == aai.TranscriptStatus.error:
            raise Exception(f"Transcription failed: {transcript.error}")

        processing_time = time.time() - start_time

        # Calculate duration and cost
        audio_duration_seconds = transcript.audio_duration
        audio_duration_minutes = audio_duration_seconds / 60
        cost_usd = audio_duration_minutes * COST_PER_MINUTE

        # Count unique speakers and build utterances
        speakers = set()
        utterances = []

        if transcript.utterances:
            for utt in transcript.utterances:
                speakers.add(utt.speaker)
                utterances.append({
                    "speaker": utt.speaker,
                    "text": utt.text,
                    "start": utt.start,
                    "end": utt.end,
                })

        # Build result in expected format
        result_data = {
            "video_id": video_id,
            "speakers_count": len(speakers),
            "utterances_count": len(utterances),
            "utterances": utterances,
            "audio_duration_minutes": round(audio_duration_minutes, 2),
            "language": "en",
            "processed_at": datetime.now().isoformat(),
            "processing_service": "assemblyai",
            "assemblyai_id": transcript.id,
            "cost_usd": round(cost_usd, 2),
            "processing_time_seconds": round(processing_time, 2),
        }

        # Save transcript
        os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2)

        logger.info(f"  ✓ Complete: {len(speakers)} speakers, {len(utterances)} utterances")
        logger.info(f"    Duration: {audio_duration_minutes:.1f} min, Cost: ${cost_usd:.2f}")

        return TranscribeResult(
            video_id=video_id,
            status="success",
            file_path=str(output_path),
            speakers_count=len(speakers),
            utterances_count=len(utterances),
            duration_minutes=audio_duration_minutes,
            cost_usd=cost_usd,
        )

    except Exception as e:
        logger.error(f"  Error transcribing {video_id}: {e}")
        return TranscribeResult(
            video_id=video_id,
            status="error",
            error=str(e),
        )


def run_transcription(
    jurisdiction_id: str,
    input_dir: str = "data/youtube_audio",
    output_dir: str = "data/testimony",
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
    limit: int = 0,
    min_speakers: int = 5,
    max_speakers: int = 10,
) -> Optional[List[TranscribeResult]]:
    """
    Run transcription for audio files from a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        input_dir: Directory containing audio files
        output_dir: Directory for transcript files
        checkpoint_dir: Directory for checkpoint files
        dry_run: If True, show what would be transcribed without transcribing
        limit: Maximum files to transcribe (0 = no limit)
        min_speakers: Minimum expected speakers
        max_speakers: Maximum expected speakers

    Returns:
        List of TranscribeResult if successful, None if failed
    """
    logger.info(f"Starting transcription for {jurisdiction_id}")

    # Setup AssemblyAI (skip for dry run)
    if not dry_run:
        if not setup_assemblyai():
            return None

    # Find audio files
    audio_files = find_audio_files(jurisdiction_id, input_dir)
    if not audio_files:
        return None

    # Check for existing checkpoint
    checkpoint_path = checkpoint_path_for_transcribe(jurisdiction_id, checkpoint_dir)
    resume_from = load_checkpoint(checkpoint_path)
    start_index = 0

    if resume_from:
        logger.info(f"Found checkpoint: {resume_from.items_processed} items processed")
        # Find the index to resume from
        for i, audio_file in enumerate(audio_files):
            if audio_file.stem == resume_from.last_video_id:
                start_index = i + 1
                break
        if start_index > 0:
            logger.info(f"Resuming from file {start_index}")

    # Apply limit
    files_to_process = audio_files[start_index:]
    if limit > 0:
        files_to_process = files_to_process[:limit]
        logger.info(f"Limited to {limit} files")

    if dry_run:
        logger.info("Dry-run mode - showing files to transcribe:")
        already_transcribed = 0
        total_to_transcribe = 0

        for i, audio_file in enumerate(files_to_process, start=1):
            video_id = audio_file.stem
            exists = transcript_exists(video_id, output_dir)
            status = "(already transcribed)" if exists else ""

            if exists:
                already_transcribed += 1
            else:
                total_to_transcribe += 1

            logger.info(f"  [{i}/{len(files_to_process)}] {video_id} {status}")

        logger.info(f"Would process {len(files_to_process)} files")
        logger.info(f"Already transcribed: {already_transcribed}")
        logger.info(f"To transcribe: {total_to_transcribe}")
        logger.info(f"Estimated cost: ${total_to_transcribe * 2.40:.2f} (assuming 2-hour meetings)")
        return None

    # Transcribe files
    results = []
    items_processed = start_index
    items_transcribed = 0
    items_skipped = 0
    items_failed = 0
    total_cost = 0.0

    for i, audio_file in enumerate(files_to_process, start=start_index + 1):
        video_id = audio_file.stem
        logger.info(f"[{i}/{len(audio_files)}] {video_id}")

        result = transcribe_audio_file(
            audio_file,
            output_dir,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        results.append(result)

        if result.status == "success":
            items_transcribed += 1
            total_cost += result.cost_usd or 0.0
        elif result.status == "skipped":
            items_skipped += 1
        else:
            items_failed += 1

        items_processed = i

        # Save checkpoint every 3 files (transcription is expensive)
        if i % 3 == 0:
            checkpoint = TranscribeCheckpoint(
                jurisdiction_id=jurisdiction_id,
                last_video_id=video_id,
                items_processed=items_processed,
                items_transcribed=items_transcribed,
                items_skipped=items_skipped,
                items_failed=items_failed,
                total_cost_usd=total_cost,
                timestamp=datetime.now().isoformat(),
            )
            save_checkpoint(checkpoint, checkpoint_path)
            logger.debug(f"Checkpoint saved: {items_processed} processed")

    # Final checkpoint
    if files_to_process:
        last_video_id = files_to_process[-1].stem
        checkpoint = TranscribeCheckpoint(
            jurisdiction_id=jurisdiction_id,
            last_video_id=last_video_id,
            items_processed=items_processed,
            items_transcribed=items_transcribed,
            items_skipped=items_skipped,
            items_failed=items_failed,
            total_cost_usd=total_cost,
            timestamp=datetime.now().isoformat(),
        )
        save_checkpoint(checkpoint, checkpoint_path)

    # Summary
    logger.info("=" * 50)
    logger.info(f"Transcription Complete for {jurisdiction_id}")
    logger.info(f"Processed: {len(results)}")
    logger.info(f"Transcribed: {items_transcribed}")
    logger.info(f"Skipped (already exist): {items_skipped}")
    logger.info(f"Failed: {items_failed}")
    logger.info(f"Total cost: ${total_cost:.2f}")
    logger.info("=" * 50)

    return results


def run_scheduled(
    jurisdiction_id: str,
    input_dir: str,
    output_dir: str,
    checkpoint_dir: str,
    min_speakers: int,
    max_speakers: int,
) -> None:
    """
    Run transcription on a schedule.

    Uses the schedule library to run daily at 9am (after audio at 8am).
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting transcription scheduler for {jurisdiction_id}")
    logger.info("Will run daily at 09:00")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled run starting")
        run_transcription(
            jurisdiction_id,
            input_dir=input_dir,
            output_dir=output_dir,
            checkpoint_dir=checkpoint_dir,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for 9am daily (after audio at 8am)
    schedule.every().day.at("09:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial transcription...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute
