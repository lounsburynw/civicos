"""
Speaker estimation for city council meeting transcription.

Estimates the number of unique speakers from YouTube auto-generated
transcripts, providing data-driven parameters for AssemblyAI diarization.

The validated approach (Sessions 108-109) uses exact-count diarization
(min=N, max=N) to prevent fatal under-segmentation. Over-segmentation
is recoverable; under-segmentation is not.

Usage:
    from civicos_extraction.speaker_estimation import estimate_speakers

    result = estimate_speakers("/path/to/transcript.json3")
    # result.speaker_count  -> int (e.g., 42)
    # result.confidence     -> "high" | "medium" | "low"
    # result.method         -> "llm" | "pattern" | "default"
"""

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Conservative defaults when estimation is unavailable
DEFAULT_MIN_SPEAKERS = 15
DEFAULT_MAX_SPEAKERS = 50


@dataclass
class EstimationResult:
    """Result from the speaker estimation pipeline."""

    speaker_count: int
    confidence: str  # "high", "medium", "low"
    method: str  # "llm", "pattern", "default"
    named_speakers: List[str] = field(default_factory=list)
    reasoning: str = ""


def estimate_speakers(
    transcript_path: Optional[str] = None,
    use_llm: bool = True,
    max_chars: int = 4000,
) -> EstimationResult:
    """
    Estimate the number of speakers in a council meeting.

    Tries estimation strategies in order:
    1. LLM-based estimation (if use_llm=True and OPENAI_API_KEY available)
    2. Pattern-based estimation (free, fast)
    3. Conservative defaults (min=15, max=50)

    For exact-count diarization, use result.speaker_count as both
    min_speakers and max_speakers in AssemblyAI config.

    Args:
        transcript_path: Path to YouTube JSON3 transcript file.
            If None, returns defaults immediately.
        use_llm: Whether to attempt LLM estimation (costs ~$0.001-0.01)
        max_chars: Max characters for LLM analysis (controls cost)

    Returns:
        EstimationResult with speaker_count and metadata
    """
    if transcript_path is None:
        logger.info("No transcript path provided, using defaults")
        return EstimationResult(
            speaker_count=DEFAULT_MAX_SPEAKERS,
            confidence="low",
            method="default",
            reasoning="No transcript available for estimation",
        )

    # Strategy 1: LLM estimation (most accurate)
    if use_llm:
        try:
            from .llm_estimator import estimate_from_llm

            llm_result = estimate_from_llm(transcript_path, max_chars=max_chars)
            count = llm_result.estimated_total_speakers
            # Sanity bounds
            count = max(3, min(count, 100))
            logger.info(
                "LLM estimation: %d speakers (%s confidence)",
                count,
                llm_result.confidence,
            )
            return EstimationResult(
                speaker_count=count,
                confidence=llm_result.confidence,
                method="llm",
                named_speakers=llm_result.named_speakers,
                reasoning=llm_result.reasoning,
            )
        except ImportError:
            logger.debug("openai not installed, skipping LLM estimation")
        except Exception as e:
            logger.warning("LLM estimation failed: %s", e)

    # Strategy 2: Pattern estimation (free)
    try:
        from .pattern_estimator import estimate_from_pattern

        pattern_result = estimate_from_pattern(transcript_path)
        # Use the max estimate as the speaker count (over-segment rather than under)
        count = pattern_result.max_estimate
        count = max(3, min(count, 100))
        logger.info(
            "Pattern estimation: %d speakers (%s confidence)",
            count,
            pattern_result.confidence,
        )
        return EstimationResult(
            speaker_count=count,
            confidence=pattern_result.confidence,
            method="pattern",
            named_speakers=pattern_result.named_speakers,
            reasoning=f"Pattern: {len(pattern_result.named_speakers)} named, "
            f"{pattern_result.speaker_changes} speaker changes detected",
        )
    except Exception as e:
        logger.warning("Pattern estimation failed: %s", e)

    # Strategy 3: Conservative defaults
    logger.info("All estimation methods failed, using defaults")
    return EstimationResult(
        speaker_count=DEFAULT_MAX_SPEAKERS,
        confidence="low",
        method="default",
        reasoning="Estimation failed, using conservative defaults",
    )


def _fetch_youtube_captions(video_id: str) -> Optional[str]:
    """
    Fetch YouTube auto-captions and save to a temp JSON3 file.

    Returns path to temp file, or None if captions unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.debug("youtube_transcript_api not installed")
        return None

    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id)

        # Convert to JSON3 format (compatible with estimation scripts)
        json3_data = {
            "events": [
                {"segs": [{"utf8": snippet.text + " "}]}
                for snippet in fetched.snippets
            ]
        }

        # Write to temp file
        tmp = tempfile.NamedTemporaryFile(
            suffix=".json3", prefix=f"yt_{video_id}_", delete=False, mode="w"
        )
        json.dump(json3_data, tmp)
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.debug("Failed to fetch YouTube captions for %s: %s", video_id, e)
        return None


def estimate_speakers_for_video(
    video_id: str,
    use_llm: bool = True,
    max_chars: int = 4000,
) -> EstimationResult:
    """
    Estimate speakers for a YouTube video by fetching its captions.

    Convenience function for pipeline integration. Fetches YouTube
    auto-captions, runs estimation, and cleans up the temp file.

    Args:
        video_id: YouTube video ID (e.g., "MpxrGRb16HQ")
        use_llm: Whether to attempt LLM estimation
        max_chars: Max characters for LLM analysis

    Returns:
        EstimationResult with speaker_count and metadata
    """
    caption_path = _fetch_youtube_captions(video_id)
    if caption_path is None:
        logger.info("No captions available for %s, using defaults", video_id)
        return EstimationResult(
            speaker_count=DEFAULT_MAX_SPEAKERS,
            confidence="low",
            method="default",
            reasoning=f"YouTube captions unavailable for {video_id}",
        )

    try:
        return estimate_speakers(
            transcript_path=caption_path,
            use_llm=use_llm,
            max_chars=max_chars,
        )
    finally:
        # Clean up temp file
        try:
            Path(caption_path).unlink()
        except OSError:
            pass
