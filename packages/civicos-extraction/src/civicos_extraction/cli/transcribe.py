"""
Transcription command for civic-extract CLI.

Transcribes audio files using AssemblyAI with speaker diarization.

Usage:
    civic-extract transcribe --jurisdiction city-san-rafael
    civic-extract transcribe --jurisdiction city-san-rafael --schedule
    civic-extract transcribe --jurisdiction city-san-rafael --dry-run
    civic-extract transcribe --jurisdiction city-san-rafael --limit 5
    civic-extract transcribe --jurisdiction city-san-rafael --cloud
    civic-extract transcribe --jurisdiction city-san-rafael --cloud --batch

Cloud mode (--cloud):
    - Reads audio files from R2 blob storage
    - Stores transcripts in Postgres (requires DATABASE_URL)
    - Falls back to local storage if cloud unavailable

Batch mode (--batch):
    - Submits all files to AssemblyAI at once
    - AssemblyAI processes them in parallel (up to 32 concurrent)
    - Total time = longest single file (~20-30 min) instead of sum of all
    - Recommended for large batches

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
from typing import Dict, List, Optional, Tuple

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
    # Duration validation fields (SESSION 496)
    youtube_duration_seconds: Optional[int] = None
    duration_valid: Optional[bool] = None
    duration_validation_error: Optional[str] = None


# Duration validation constants (SESSION 496)
DURATION_TOLERANCE_PERCENT = 0.10  # Allow 10% variance for encoding overhead/padding
MIN_DURATION_FOR_VALIDATION = 60  # Don't validate very short clips (<1 min)


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
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store transcripts in cloud storage (requires DATABASE_URL)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Use batch mode for parallel transcription (faster, submits all at once)",
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
            cloud=args.cloud,
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
            cloud=args.cloud,
            batch=args.batch,
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
    logger.info("AssemblyAI configured")
    return True


def find_audio_files(
    jurisdiction_id: str,
    input_dir: str,
    cloud: bool = False,
    meeting_type: Optional[str] = None,
) -> Optional[List]:
    """
    Find audio files for a jurisdiction from local storage or cloud.

    In cloud mode, returns list of video dicts from Postgres.
    In local mode, returns list of Path objects from local filesystem.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        input_dir: Directory containing audio files (local mode)
        cloud: If True, try cloud storage first
        meeting_type: Filter by meeting type (e.g., "planning_commission")

    Returns:
        List of audio file paths (local) or video dicts (cloud), or None if none found
    """
    # Try cloud storage first if enabled
    if cloud or os.environ.get("DATABASE_URL"):
        try:
            from civicos.storage import get_storage_backend, get_blob_storage

            blob = get_blob_storage()
            backend = get_storage_backend()

            # First try: get videos from Postgres and check for audio in R2
            if backend.backend_type == "postgres":
                videos = backend.get_videos(jurisdiction_id, meeting_type=meeting_type)
                if videos:
                    # Filter to videos that have audio in R2
                    audio_videos = []
                    for video in videos:
                        video_id = video.get("id") or video.get("video_id")
                        if video_id:
                            r2_key = f"audio/{jurisdiction_id}/{video_id}.mp3"
                            if blob.exists(r2_key):
                                # Add video_id to the dict for consistency
                                video["video_id"] = video_id
                                audio_videos.append(video)

                    if audio_videos:
                        logger.info(
                            f"Found {len(audio_videos)} audio files in cloud storage (R2)"
                        )
                        return audio_videos

            # Second try: list R2 audio files directly (even without video metadata)
            r2_prefix = f"audio/{jurisdiction_id}/"
            audio_keys = blob.list_keys(r2_prefix)
            if audio_keys:
                audio_videos = []
                for key in audio_keys:
                    if key.endswith(".mp3"):
                        # Extract video_id from key: audio/city-san-rafael/VIDEO_ID.mp3
                        video_id = key.replace(r2_prefix, "").replace(".mp3", "")
                        audio_videos.append({"video_id": video_id})
                if audio_videos:
                    logger.info(
                        f"Found {len(audio_videos)} audio files in R2 (direct listing)"
                    )
                    return audio_videos

            logger.info("No audio files in R2, trying local fallback")
        except ImportError:
            logger.debug("civic.storage not available, using local fallback")
        except Exception as e:
            logger.warning(f"Cloud storage check failed: {e}, using local fallback")

    # Local mode fallback
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


def get_youtube_video_duration(video_id: str) -> Optional[int]:
    """
    Fetch video duration from YouTube Data API.

    SESSION 496: Added for transcript duration validation.
    Uses YouTubeBoardsClient's duration parsing logic for consistency.

    Args:
        video_id: YouTube video ID (e.g., "QLDoO6OvMSA")

    Returns:
        Video duration in seconds, or None if unavailable
    """
    import re as re_module
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.debug("No YouTube API key available for duration validation")
        return None

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        service = build("youtube", "v3", developerKey=api_key)
        request = service.videos().list(part="contentDetails", id=video_id)
        response = request.execute()

        items = response.get("items", [])
        if not items:
            logger.warning(f"Video {video_id} not found on YouTube")
            return None

        duration_str = items[0]["contentDetails"]["duration"]

        # Parse ISO 8601 duration (PT1H30M45S -> seconds)
        match = re_module.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
        if not match:
            logger.warning(f"Could not parse duration format: {duration_str}")
            return None

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        total_seconds = hours * 3600 + minutes * 60 + seconds
        logger.debug(f"YouTube duration for {video_id}: {total_seconds}s ({duration_str})")
        return total_seconds

    except ImportError:
        logger.debug("google-api-python-client not available for duration validation")
        return None
    except HttpError as e:
        logger.warning(f"YouTube API error fetching duration for {video_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error fetching YouTube duration for {video_id}: {e}")
        return None


def validate_transcript_duration(
    video_id: str,
    assemblyai_duration_seconds: float,
    youtube_duration_seconds: Optional[int] = None,
) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Validate transcript duration against YouTube video duration.

    SESSION 496: Detects corrupted audio downloads (playlist/concatenation bugs).

    Args:
        video_id: YouTube video ID
        assemblyai_duration_seconds: Duration reported by AssemblyAI
        youtube_duration_seconds: Pre-fetched YouTube duration (optional, will fetch if None)

    Returns:
        Tuple of (is_valid, error_message, youtube_duration_seconds)
        - is_valid: True if duration is within tolerance, False if mismatch
        - error_message: Description of mismatch if invalid, None if valid
        - youtube_duration_seconds: The YouTube duration used for comparison
    """
    # Skip validation for very short clips
    if assemblyai_duration_seconds < MIN_DURATION_FOR_VALIDATION:
        logger.debug(f"Skipping duration validation for {video_id} (too short: {assemblyai_duration_seconds}s)")
        return True, None, youtube_duration_seconds

    # Fetch YouTube duration if not provided
    if youtube_duration_seconds is None:
        youtube_duration_seconds = get_youtube_video_duration(video_id)

    # Can't validate without YouTube duration
    if youtube_duration_seconds is None:
        logger.debug(f"Cannot validate duration for {video_id} (no YouTube duration available)")
        return True, None, None

    # Calculate tolerance
    max_allowed = youtube_duration_seconds * (1 + DURATION_TOLERANCE_PERCENT)

    # Check for duration exceeding YouTube video
    if assemblyai_duration_seconds > max_allowed:
        excess_seconds = assemblyai_duration_seconds - youtube_duration_seconds
        excess_percent = (excess_seconds / youtube_duration_seconds) * 100
        error_msg = (
            f"Transcript duration ({assemblyai_duration_seconds:.0f}s) exceeds "
            f"YouTube video ({youtube_duration_seconds}s) by {excess_seconds:.0f}s "
            f"({excess_percent:.1f}%). Likely corrupted audio download."
        )
        logger.warning(f"⚠️ Duration mismatch for {video_id}: {error_msg}")
        return False, error_msg, youtube_duration_seconds

    # Duration is within tolerance
    logger.debug(
        f"Duration validated for {video_id}: "
        f"transcript={assemblyai_duration_seconds:.0f}s, youtube={youtube_duration_seconds}s"
    )
    return True, None, youtube_duration_seconds


def transcribe_audio_file(
    audio_source,
    output_dir: str,
    min_speakers: int = 5,
    max_speakers: int = 10,
    jurisdiction_id: Optional[str] = None,
    cloud: bool = False,
) -> TranscribeResult:
    """
    Transcribe an audio file with AssemblyAI.

    Args:
        audio_source: Path to audio file (Path) or video dict (cloud mode)
        output_dir: Directory to save transcript (local mode)
        min_speakers: Minimum expected speakers
        max_speakers: Maximum expected speakers
        jurisdiction_id: Jurisdiction ID (required for cloud mode)
        cloud: If True, use cloud storage

    Returns:
        TranscribeResult with status and details
    """
    import time
    import tempfile

    try:
        import assemblyai as aai
    except ImportError:
        video_id = audio_source.stem if isinstance(audio_source, Path) else audio_source.get("video_id")
        return TranscribeResult(
            video_id=video_id,
            status="error",
            error="assemblyai not installed",
        )

    # Handle both Path (local) and dict (cloud) inputs
    if isinstance(audio_source, Path):
        video_id = audio_source.stem
        audio_path = audio_source
    else:
        video_id = audio_source.get("video_id") or audio_source.get("id")
        audio_path = None  # Will load from cloud

    cloud_mode = cloud or os.environ.get("DATABASE_URL")

    # Check if already transcribed (local first, then cloud)
    output_path = Path(output_dir) / f"testimony_{video_id}.json"
    if output_path.exists():
        logger.info(f"  Skipping (already transcribed locally): {video_id}")
        return TranscribeResult(
            video_id=video_id,
            status="skipped",
            file_path=str(output_path),
        )

    if cloud_mode and transcript_exists_in_cloud(video_id):
        logger.info(f"  Skipping (already transcribed in cloud): {video_id}")
        return TranscribeResult(
            video_id=video_id,
            status="skipped",
        )

    try:
        # Load audio from cloud if needed
        temp_audio_path = None
        audio_hash = None
        if audio_path is None and cloud_mode and jurisdiction_id:
            audio_data, audio_hash = load_audio_from_cloud(jurisdiction_id, video_id)
            if audio_data is None:
                raise Exception(f"Audio not found in cloud for {video_id}")

            # Write to temp file for AssemblyAI
            temp_audio_path = tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False
            )
            temp_audio_path.write(audio_data)
            temp_audio_path.close()
            audio_path = Path(temp_audio_path.name)

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

        # SESSION 496: Validate transcript duration against YouTube video duration
        duration_valid, validation_error, youtube_duration = validate_transcript_duration(
            video_id, audio_duration_seconds
        )
        if validation_error:
            logger.warning(f"  ⚠️ Duration validation failed: {validation_error}")

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
            "audio_hash": audio_hash,  # SHA-256 of source audio for provenance
            # SESSION 496: Duration validation fields
            "youtube_duration_seconds": youtube_duration,
            "duration_valid": duration_valid,
            "duration_validation_error": validation_error,
        }

        # Store transcript (cloud or local)
        stored_to_cloud = False
        if cloud_mode and jurisdiction_id:
            stored_to_cloud = store_transcript_to_cloud(jurisdiction_id, result_data)

        # Also save to local file if not using cloud, or as fallback
        if not stored_to_cloud:
            os.makedirs(output_dir, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(result_data, f, indent=2)

        # Clean up temp file if we created one
        if temp_audio_path:
            try:
                os.unlink(temp_audio_path.name)
            except Exception:
                pass

        logger.info(f"  ✓ Complete: {len(speakers)} speakers, {len(utterances)} utterances")
        logger.info(f"    Duration: {audio_duration_minutes:.1f} min, Cost: ${cost_usd:.2f}")

        return TranscribeResult(
            video_id=video_id,
            status="success",
            file_path=str(output_path) if not stored_to_cloud else None,
            speakers_count=len(speakers),
            utterances_count=len(utterances),
            duration_minutes=audio_duration_minutes,
            cost_usd=cost_usd,
            # SESSION 496: Duration validation fields
            youtube_duration_seconds=youtube_duration,
            duration_valid=duration_valid,
            duration_validation_error=validation_error,
        )

    except Exception as e:
        logger.error(f"  Error transcribing {video_id}: {e}")
        # Clean up temp file on error
        if temp_audio_path:
            try:
                os.unlink(temp_audio_path.name)
            except Exception:
                pass
        return TranscribeResult(
            video_id=video_id,
            status="error",
            error=str(e),
        )


def transcript_exists_in_cloud(video_id: str) -> bool:
    """Check if transcript exists in cloud storage."""
    try:
        from civicos.storage import get_storage_backend

        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            transcript = backend.get_transcript(video_id)
            return transcript is not None
    except ImportError:
        logger.debug("civic.storage not available for cloud check")
    except Exception as e:
        logger.debug(f"Cloud check failed: {e}")
    return False


def load_audio_from_cloud(
    jurisdiction_id: str, video_id: str
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Load audio file from R2 cloud storage and compute SHA-256 hash.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        video_id: YouTube video ID

    Returns:
        Tuple of (audio_data, audio_hash) or (None, None) if not found.
        The audio_hash is the SHA-256 of the raw audio file for provenance.
    """
    try:
        from civicos.storage import get_blob_storage
        from civicos.storage.integrity import compute_audio_hash

        blob = get_blob_storage()
        r2_key = f"audio/{jurisdiction_id}/{video_id}.mp3"

        if not blob.exists(r2_key):
            logger.debug(f"Audio not found in cloud: {r2_key}")
            return None, None

        audio_data = blob.download(r2_key)
        audio_hash = compute_audio_hash(audio_data)
        logger.info(f"  Loaded audio from cloud: {r2_key} (hash: {audio_hash[:12]}...)")
        return audio_data, audio_hash
    except ImportError:
        logger.debug("civic.storage not available for cloud audio")
    except Exception as e:
        logger.warning(f"Failed to load audio from cloud: {e}")
    return None, None


def store_transcript_to_cloud(
    jurisdiction_id: str, transcript_data: dict
) -> bool:
    """
    Store transcript to cloud storage.

    Args:
        jurisdiction_id: Jurisdiction ID
        transcript_data: Transcript dictionary with video_id, utterances, etc.

    Returns:
        True if stored successfully, False otherwise
    """
    try:
        from civicos.storage import get_storage_backend

        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            count = backend.store_transcripts(jurisdiction_id, [transcript_data])
            if count > 0:
                logger.info(f"  Stored transcript in cloud storage")
                return True
    except ImportError:
        logger.warning("civic.storage not available, keeping local file only")
    except Exception as e:
        logger.warning(f"Cloud storage failed: {e}, keeping local file only")
    return False


def transcribe_batch(
    audio_files: List,
    jurisdiction_id: str,
    output_dir: str,
    min_speakers: int = 5,
    max_speakers: int = 10,
    cloud: bool = False,
) -> List[TranscribeResult]:
    """
    Transcribe multiple audio files in parallel using AssemblyAI's transcribe_group.

    This submits all files at once and polls for completion, significantly reducing
    wall clock time compared to sequential transcription.

    Args:
        audio_files: List of audio files (Path objects or video dicts)
        jurisdiction_id: Jurisdiction ID
        output_dir: Directory for local transcript storage
        min_speakers: Minimum expected speakers
        max_speakers: Maximum expected speakers
        cloud: If True, use cloud storage

    Returns:
        List of TranscribeResult objects
    """
    import time
    import tempfile

    try:
        import assemblyai as aai
    except ImportError:
        logger.error("assemblyai package not found")
        return [
            TranscribeResult(
                video_id=f.stem if isinstance(f, Path) else f.get("video_id"),
                status="error",
                error="assemblyai not installed",
            )
            for f in audio_files
        ]

    cloud_mode = cloud or os.environ.get("DATABASE_URL")
    results = []

    # Step 1: Prepare audio sources and filter already-transcribed
    files_to_transcribe = []
    video_ids_in_order = []  # Track video_ids in submission order
    temp_files = []  # Track temp files for cleanup

    logger.info(f"Preparing {len(audio_files)} files for batch transcription...")

    for audio_file in audio_files:
        # Get video_id
        if isinstance(audio_file, Path):
            video_id = audio_file.stem
            audio_path = audio_file
        else:
            video_id = audio_file.get("video_id") or audio_file.get("id")
            audio_path = None

        # Check if already transcribed
        output_path = Path(output_dir) / f"testimony_{video_id}.json"
        if output_path.exists():
            logger.info(f"  Skipping {video_id} (already transcribed locally)")
            results.append(
                TranscribeResult(video_id=video_id, status="skipped", file_path=str(output_path))
            )
            continue

        if cloud_mode and transcript_exists_in_cloud(video_id):
            logger.info(f"  Skipping {video_id} (already transcribed in cloud)")
            results.append(TranscribeResult(video_id=video_id, status="skipped"))
            continue

        # Load audio from cloud if needed
        if audio_path is None and cloud_mode:
            audio_data, audio_hash = load_audio_from_cloud(jurisdiction_id, video_id)
            if audio_data is None:
                logger.error(f"  Failed to load audio for {video_id}")
                results.append(
                    TranscribeResult(
                        video_id=video_id, status="error", error="Audio not found in cloud"
                    )
                )
                continue

            # Write to temp file
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_file.write(audio_data)
            temp_file.close()
            audio_path = Path(temp_file.name)
            temp_files.append(temp_file.name)

        files_to_transcribe.append(str(audio_path))
        video_ids_in_order.append(video_id)

    if not files_to_transcribe:
        logger.info("No files to transcribe (all already done)")
        return results

    logger.info(f"Submitting {len(files_to_transcribe)} files to AssemblyAI in parallel...")

    # Step 2: Configure and submit batch
    try:
        speaker_opts = aai.types.SpeakerOptions(
            min_speakers_expected=min_speakers,
            max_speakers_expected=max_speakers,
        )

        config = aai.TranscriptionConfig(
            speaker_labels=True,
            speaker_options=speaker_opts,
            language_code="en",
        )

        transcriber = aai.Transcriber()
        start_time = time.time()

        # Submit all files at once - AssemblyAI processes them in parallel
        logger.info("  Submitting batch to AssemblyAI (this submits all files at once)...")
        transcript_group = transcriber.transcribe_group(files_to_transcribe, config=config)

        total_processing_time = time.time() - start_time
        logger.info(f"  Batch complete in {total_processing_time:.1f}s")

        # Step 3: Process results
        # transcribe_group returns transcripts in the same order as submission
        for idx, transcript in enumerate(transcript_group.transcripts):
            if idx >= len(video_ids_in_order):
                logger.warning(f"  More transcripts returned than submitted (idx={idx})")
                continue

            video_id = video_ids_in_order[idx]

            # Check for errors
            if transcript.status == aai.TranscriptStatus.error:
                logger.error(f"  Error transcribing {video_id}: {transcript.error}")
                results.append(
                    TranscribeResult(
                        video_id=video_id, status="error", error=str(transcript.error)
                    )
                )
                continue

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

            # Build result data
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
                "processing_time_seconds": round(total_processing_time / len(files_to_transcribe), 2),
            }

            # Store transcript
            stored_to_cloud = False
            if cloud_mode:
                stored_to_cloud = store_transcript_to_cloud(jurisdiction_id, result_data)

            if not stored_to_cloud:
                os.makedirs(output_dir, exist_ok=True)
                output_path = Path(output_dir) / f"testimony_{video_id}.json"
                with open(output_path, "w") as f:
                    json.dump(result_data, f, indent=2)

            logger.info(f"  ✓ {video_id}: {len(speakers)} speakers, {len(utterances)} utterances, ${cost_usd:.2f}")

            results.append(
                TranscribeResult(
                    video_id=video_id,
                    status="success",
                    file_path=str(output_path) if not stored_to_cloud else None,
                    speakers_count=len(speakers),
                    utterances_count=len(utterances),
                    duration_minutes=audio_duration_minutes,
                    cost_usd=cost_usd,
                )
            )

    except Exception as e:
        logger.error(f"Batch transcription failed: {e}")
        # Mark all remaining as failed
        for video_id in video_ids_in_order:
            if not any(r.video_id == video_id for r in results):
                results.append(
                    TranscribeResult(video_id=video_id, status="error", error=str(e))
                )

    finally:
        # Clean up temp files
        for temp_path in temp_files:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    return results


def run_transcription(
    jurisdiction_id: str,
    input_dir: str = "data/youtube_audio",
    output_dir: str = "data/testimony",
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
    limit: int = 0,
    min_speakers: int = 5,
    max_speakers: int = 10,
    cloud: bool = False,
    batch: bool = False,
    meeting_type: Optional[str] = None,
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
        cloud: If True, use cloud storage (R2 for audio, Postgres for transcripts)
        batch: If True, use batch mode for parallel transcription
        meeting_type: Filter by meeting type (e.g., "planning_commission")

    Returns:
        List of TranscribeResult if successful, None if failed
    """
    logger.info(f"Starting transcription for {jurisdiction_id}")
    if meeting_type:
        logger.info(f"Filtering by meeting_type: {meeting_type}")

    cloud_mode = cloud or os.environ.get("DATABASE_URL")
    if cloud_mode:
        logger.info("Cloud storage mode enabled")

    # Setup AssemblyAI (skip for dry run)
    if not dry_run:
        if not setup_assemblyai():
            return None

    # Find audio files (local or cloud)
    audio_files = find_audio_files(jurisdiction_id, input_dir, cloud=cloud_mode, meeting_type=meeting_type)
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
            file_id = audio_file.stem if isinstance(audio_file, Path) else audio_file.get("video_id")
            if file_id == resume_from.last_video_id:
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
            video_id = audio_file.stem if isinstance(audio_file, Path) else audio_file.get("video_id")
            # Check both local and cloud
            exists = transcript_exists(video_id, output_dir)
            if cloud_mode and not exists:
                exists = transcript_exists_in_cloud(video_id)
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
        if batch:
            logger.info("Batch mode: Files will be submitted in parallel (~20-30 min total)")
        else:
            logger.info("Sequential mode: ~5-10 min per file")
        return None

    # Use batch mode for parallel transcription
    if batch:
        logger.info("=" * 50)
        logger.info("BATCH MODE: Parallel transcription")
        logger.info("=" * 50)

        import time
        batch_start = time.time()

        results = transcribe_batch(
            files_to_process,
            jurisdiction_id,
            output_dir,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            cloud=cloud_mode,
        )

        batch_duration = time.time() - batch_start

        # Calculate totals from results
        items_transcribed = sum(1 for r in results if r.status == "success")
        items_skipped = sum(1 for r in results if r.status == "skipped")
        items_failed = sum(1 for r in results if r.status == "error")
        total_cost = sum(r.cost_usd or 0.0 for r in results if r.status == "success")

        # Store ETL cost record if we transcribed anything
        if items_transcribed > 0 and cloud_mode:
            try:
                from civicos.storage import get_storage_backend

                backend = get_storage_backend()
                if backend.backend_type == "postgres":
                    cost_id = backend.store_etl_cost(
                        pipeline="transcribe",
                        jurisdiction_id=jurisdiction_id,
                        items_processed=items_transcribed,
                        cost_usd=total_cost,
                        duration_seconds=batch_duration,
                        notes=f"Batch transcribed {items_transcribed} videos via AssemblyAI (parallel)",
                    )
                    logger.info(f"ETL cost recorded (id={cost_id}): ${total_cost:.2f}")
            except ImportError:
                logger.debug("civic.storage not available for cost tracking")
            except Exception as e:
                logger.warning(f"Failed to record ETL cost: {e}")

        # Summary
        logger.info("=" * 50)
        logger.info(f"Batch Transcription Complete for {jurisdiction_id}")
        logger.info(f"Total time: {batch_duration:.1f}s ({batch_duration/60:.1f} min)")
        logger.info(f"Transcribed: {items_transcribed}")
        logger.info(f"Skipped (already exist): {items_skipped}")
        logger.info(f"Failed: {items_failed}")
        logger.info(f"Total cost: ${total_cost:.2f}")
        if cloud_mode:
            logger.info("Transcripts stored in: cloud (Postgres)")
        else:
            logger.info(f"Transcripts stored in: {output_dir}")
        logger.info("=" * 50)

        return results

    # Sequential transcription (original behavior)
    results = []
    items_processed = start_index
    items_transcribed = 0
    items_skipped = 0
    items_failed = 0
    total_cost = 0.0

    for i, audio_file in enumerate(files_to_process, start=start_index + 1):
        video_id = audio_file.stem if isinstance(audio_file, Path) else audio_file.get("video_id")
        logger.info(f"[{i}/{len(audio_files)}] {video_id}")

        result = transcribe_audio_file(
            audio_file,
            output_dir,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            jurisdiction_id=jurisdiction_id,
            cloud=cloud_mode,
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
        last_video_id = files_to_process[-1].stem if isinstance(files_to_process[-1], Path) else files_to_process[-1].get("video_id")
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

    # Store ETL cost record if we transcribed anything
    if items_transcribed > 0 and cloud_mode:
        try:
            from civicos.storage import get_storage_backend

            backend = get_storage_backend()
            if backend.backend_type == "postgres":
                # Calculate duration from checkpoint timestamps if available
                duration_seconds = None
                cost_id = backend.store_etl_cost(
                    pipeline="transcribe",
                    jurisdiction_id=jurisdiction_id,
                    items_processed=items_transcribed,
                    cost_usd=total_cost,
                    duration_seconds=duration_seconds,
                    notes=f"Transcribed {items_transcribed} videos via AssemblyAI",
                )
                logger.info(f"ETL cost recorded (id={cost_id}): ${total_cost:.2f}")
        except ImportError:
            logger.debug("civic.storage not available for cost tracking")
        except Exception as e:
            logger.warning(f"Failed to record ETL cost: {e}")

    # Summary
    logger.info("=" * 50)
    logger.info(f"Transcription Complete for {jurisdiction_id}")
    logger.info(f"Processed: {len(results)}")
    logger.info(f"Transcribed: {items_transcribed}")
    logger.info(f"Skipped (already exist): {items_skipped}")
    logger.info(f"Failed: {items_failed}")
    logger.info(f"Total cost: ${total_cost:.2f}")
    if cloud_mode:
        logger.info("Transcripts stored in: cloud (Postgres)")
    else:
        logger.info(f"Transcripts stored in: {output_dir}")
    logger.info("=" * 50)

    return results


def run_scheduled(
    jurisdiction_id: str,
    input_dir: str,
    output_dir: str,
    checkpoint_dir: str,
    min_speakers: int,
    max_speakers: int,
    cloud: bool = False,
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
    if cloud:
        logger.info("Cloud storage mode enabled")

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
            cloud=cloud,
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


def validate_existing_transcripts(
    jurisdiction_id: str,
    update_db: bool = False,
    limit: int = 0,
) -> Dict[str, List[str]]:
    """
    Validate existing transcripts against YouTube video durations.

    SESSION 496: Added for retroactive validation of existing transcripts.
    Detects corrupted audio downloads where transcript duration exceeds video.

    Args:
        jurisdiction_id: Jurisdiction to validate
        update_db: If True, update database with validation results
        limit: Maximum transcripts to validate (0 = all)

    Returns:
        Dict with 'valid', 'invalid', and 'skipped' lists of video IDs
    """
    from dotenv import load_dotenv

    load_dotenv()

    try:
        from civicos.storage import get_storage_backend
    except ImportError:
        logger.error("civic.storage not available for validation")
        return {"valid": [], "invalid": [], "skipped": []}

    backend = get_storage_backend()
    if backend.backend_type != "postgres":
        logger.error("Validation requires PostgreSQL backend")
        return {"valid": [], "invalid": [], "skipped": []}

    # Get existing transcripts
    transcripts = backend.get_transcripts(jurisdiction_id, limit=limit or None)
    if not transcripts:
        logger.info(f"No transcripts found for {jurisdiction_id}")
        return {"valid": [], "invalid": [], "skipped": []}

    results = {"valid": [], "invalid": [], "skipped": []}

    logger.info(f"Validating {len(transcripts)} transcripts for {jurisdiction_id}...")
    logger.info("=" * 60)

    for i, transcript in enumerate(transcripts, 1):
        video_id = transcript.get("video_id")
        duration_seconds = transcript.get("duration_seconds")

        # Skip if already validated
        if transcript.get("duration_valid") is not None:
            logger.debug(f"  [{i}] {video_id}: Already validated, skipping")
            results["skipped"].append(video_id)
            continue

        if not video_id or not duration_seconds:
            logger.debug(f"  [{i}] {video_id}: Missing data, skipping")
            results["skipped"].append(video_id)
            continue

        # Validate
        is_valid, error_msg, youtube_duration = validate_transcript_duration(
            video_id, duration_seconds
        )

        if youtube_duration is None:
            logger.info(f"  [{i}] {video_id}: Could not fetch YouTube duration, skipping")
            results["skipped"].append(video_id)
            continue

        if is_valid:
            logger.info(
                f"  [{i}] {video_id}: ✓ Valid "
                f"(transcript={duration_seconds}s, youtube={youtube_duration}s)"
            )
            results["valid"].append(video_id)
        else:
            logger.warning(
                f"  [{i}] {video_id}: ✗ INVALID - {error_msg}"
            )
            results["invalid"].append(video_id)

        # Update database if requested (using StorageBackend protocol)
        if update_db:
            try:
                backend.update_transcript_validation(
                    jurisdiction_id=jurisdiction_id,
                    video_id=video_id,
                    youtube_duration_seconds=youtube_duration,
                    duration_valid=is_valid,
                    duration_validation_error=error_msg,
                )
            except Exception as e:
                logger.error(f"Failed to update database for {video_id}: {e}")

    # Summary
    logger.info("=" * 60)
    logger.info(f"Validation Summary for {jurisdiction_id}:")
    logger.info(f"  Valid: {len(results['valid'])}")
    logger.info(f"  Invalid: {len(results['invalid'])}")
    logger.info(f"  Skipped: {len(results['skipped'])}")

    if results["invalid"]:
        logger.warning("Invalid transcripts (corrupted audio):")
        for vid in results["invalid"]:
            logger.warning(f"  - {vid}")

    return results


def add_validate_transcripts_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the validate-transcripts subcommand to the parser."""
    parser = subparsers.add_parser(
        "validate-transcripts",
        help="Validate existing transcript durations against YouTube",
        description="Check existing transcripts for duration mismatches (corrupted audio)",
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update database with validation results",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of transcripts to validate (0 = all)",
    )


def run_validate_transcripts(args: argparse.Namespace) -> int:
    """Run the validate-transcripts command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    results = validate_existing_transcripts(
        args.jurisdiction,
        update_db=args.update,
        limit=args.limit,
    )

    if results["invalid"]:
        return 1  # Exit with error if any invalid transcripts found
    return 0
