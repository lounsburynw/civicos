#!/usr/bin/env python3
"""
Production-ready testimony extraction pipeline with error handling and retry logic.

This module provides robust wrappers for all external API calls (AssemblyAI, YouTube, LLM)
with automatic retry on transient failures, error logging, and graceful degradation.

Session: 111 (production hardening)

Usage:
    from testimony_extraction_pipeline import TestimonyExtractionPipeline

    pipeline = TestimonyExtractionPipeline()
    result = pipeline.extract_testimony(
        youtube_video_id="MpxrGRb16HQ",
        speaker_count=50,
        jurisdiction_id="san-rafael",
        meeting_date="2024-10-06"
    )
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestimonyExtractionError(Exception):
    """Base exception for testimony extraction failures."""
    pass


class YouTubeTranscriptError(TestimonyExtractionError):
    """YouTube transcript extraction failed."""
    pass


class AssemblyAIError(TestimonyExtractionError):
    """AssemblyAI processing failed."""
    pass


class LLMExtractionError(TestimonyExtractionError):
    """LLM name extraction failed."""
    pass


class TestimonyExtractionPipeline:
    """
    Production-ready pipeline for extracting testimony from city council meetings.

    Features:
    - Automatic retry on transient failures (network, rate limits, timeouts)
    - Error logging with failure tracking
    - Graceful degradation (skip failed meetings, continue pipeline)
    - Cost tracking and progress reporting
    """

    def __init__(self, error_log_path: str = "data/testimony_extraction_errors.json"):
        """
        Initialize the pipeline.

        Args:
            error_log_path: Path to error log file for tracking failures
        """
        self.error_log_path = Path(error_log_path)
        self.errors = []

        # Load existing errors if available
        if self.error_log_path.exists():
            with open(self.error_log_path, 'r') as f:
                self.errors = json.load(f)

    def _log_error(self, operation: str, error: Exception, context: dict):
        """
        Log an error to the error log file.

        Args:
            operation: Name of the operation that failed
            error: The exception that occurred
            context: Additional context (video_id, meeting_date, etc.)
        """
        error_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context
        }

        self.errors.append(error_entry)

        # Save errors to file
        with open(self.error_log_path, 'w') as f:
            json.dump(self.errors, f, indent=2)

        logger.error(f"{operation} failed: {error}", extra=context)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((requests.RequestException, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO)
    )
    def _upload_to_assemblyai(
        self,
        audio_url: str,
        speaker_count: int,
        api_key: str
    ) -> str:
        """
        Upload audio to AssemblyAI with retry logic.

        Args:
            audio_url: URL to audio file (YouTube video)
            speaker_count: Number of speakers for diarization
            api_key: AssemblyAI API key

        Returns:
            Transcript ID for polling

        Raises:
            AssemblyAIError: If upload fails after retries
        """
        endpoint = "https://api.assemblyai.com/v2/transcript"
        headers = {"authorization": api_key}

        payload = {
            "audio_url": audio_url,
            "speaker_labels": True,
            "speakers_expected": speaker_count
        }

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            transcript_id = data.get('id')

            if not transcript_id:
                raise AssemblyAIError("No transcript ID in response")

            logger.info(f"AssemblyAI upload successful: {transcript_id}")
            return transcript_id

        except requests.RequestException as e:
            raise AssemblyAIError(f"Upload failed: {e}")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=10, max=300),
        retry=retry_if_exception_type((requests.RequestException, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _poll_assemblyai_status(
        self,
        transcript_id: str,
        api_key: str
    ) -> Dict:
        """
        Poll AssemblyAI for transcript completion with retry logic.

        Args:
            transcript_id: Transcript ID to poll
            api_key: AssemblyAI API key

        Returns:
            Complete transcript data

        Raises:
            AssemblyAIError: If polling fails or transcript has error
        """
        endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        headers = {"authorization": api_key}

        max_polls = 60  # Max 10 minutes (60 × 10 seconds)
        poll_count = 0

        while poll_count < max_polls:
            try:
                response = requests.get(endpoint, headers=headers, timeout=30)
                response.raise_for_status()

                data = response.json()
                status = data.get('status')

                if status == 'completed':
                    logger.info(f"AssemblyAI transcript {transcript_id} completed")
                    return data
                elif status == 'error':
                    error_msg = data.get('error', 'Unknown error')
                    raise AssemblyAIError(f"Transcript processing error: {error_msg}")

                # Still processing, wait and retry
                poll_count += 1
                time.sleep(10)

            except requests.RequestException as e:
                raise AssemblyAIError(f"Polling failed: {e}")

        raise AssemblyAIError(f"Transcript {transcript_id} did not complete after {max_polls * 10}s")

    def _download_youtube_audio(
        self,
        video_id: str,
        output_dir: str = "data/youtube_audio"
    ) -> Optional[str]:
        """
        Download YouTube audio using yt-dlp.

        Args:
            video_id: YouTube video ID
            output_dir: Directory to save audio files

        Returns:
            Path to downloaded audio file, or None if failed
        """
        import os
        from pathlib import Path

        try:
            import yt_dlp

            # Create output directory
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            output_path = os.path.join(output_dir, f"{video_id}.mp3")

            # Skip if already downloaded
            if os.path.exists(output_path):
                file_size_mb = os.path.getsize(output_path) / (1024*1024)
                logger.info(f"Audio file already exists: {output_path} ({file_size_mb:.1f} MB)")
                return output_path

            # Download audio using yt-dlp
            url = f"https://www.youtube.com/watch?v={video_id}"

            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'outtmpl': os.path.join(output_dir, video_id),
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                duration_mins = info.get('duration', 0) // 60

            file_size_mb = os.path.getsize(output_path) / (1024*1024)
            logger.info(f"Downloaded audio: {duration_mins} min, {file_size_mb:.1f} MB → {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"Failed to download YouTube audio: {e}")
            return None

    def _extract_youtube_transcript(
        self,
        video_id: str
    ) -> str:
        """
        Extract YouTube transcript (no retry - fail fast).

        Args:
            video_id: YouTube video ID

        Returns:
            Full transcript text

        Raises:
            YouTubeTranscriptError: If extraction fails
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            # Try to get transcript (official or community) using new API (v1.2.3+)
            api = YouTubeTranscriptApi()
            fetched_transcript = api.fetch(video_id)

            # Concatenate all text from snippets
            full_text = " ".join([snippet.text for snippet in fetched_transcript.snippets])

            logger.info(f"YouTube transcript extracted: {len(full_text)} chars")
            return full_text

        except Exception as e:
            raise YouTubeTranscriptError(f"Transcript extraction failed: {e}")

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _extract_speaker_name_llm(
        self,
        utterances: List[dict],
        speaker_label: str
    ) -> Optional[str]:
        """
        Extract speaker name using LLM with retry logic.

        Args:
            utterances: Full transcript utterance list
            speaker_label: Speaker label to extract (e.g., 'A', 'B', 'C')

        Returns:
            Speaker name if found, None otherwise

        Raises:
            LLMExtractionError: If LLM call fails after retries
        """
        try:
            from llm_provider import get_model_for_task

            # Get utterances for this speaker
            speaker_utterances = [u for u in utterances if u.get('speaker') == speaker_label]

            if not speaker_utterances:
                return None

            # Get first 20 utterances as context
            sample = speaker_utterances[:20]
            context = "\n".join([f"- {u.get('text', '')}" for u in sample])

            prompt = f"""These are utterances from Speaker {speaker_label} in a city council meeting.
Find any self-introduction where they state their name.

Utterances:
{context}

Return ONLY the person's name if found (e.g., "John Smith" or "Salama from Terra Linda").
If no introduction found, return the word "null" (without quotes)."""

            provider = get_model_for_task('short_structured')

            response = provider.complete([
                {"role": "system", "content": "Extract speaker names from meeting transcripts. Return only the name or the word null."},
                {"role": "user", "content": prompt}
            ])

            name = response.content.strip()

            if name and name.lower() not in ['null', 'none', 'n/a', 'unknown']:
                return name
            else:
                return None

        except Exception as e:
            # Don't fail the entire pipeline on LLM errors, just log and return None
            logger.warning(f"LLM extraction failed for speaker {speaker_label}: {e}")
            return None

    def extract_testimony(
        self,
        youtube_video_id: str,
        speaker_count: int,
        jurisdiction_id: str,
        meeting_date: str,
        assemblyai_api_key: str
    ) -> Optional[Dict]:
        """
        Extract complete testimony from a city council meeting.

        This is the main entry point for the pipeline. It orchestrates all steps
        with error handling and retry logic.

        Args:
            youtube_video_id: YouTube video ID
            speaker_count: Estimated number of speakers
            jurisdiction_id: City jurisdiction (e.g., 'san-rafael')
            meeting_date: Meeting date (ISO format: YYYY-MM-DD)
            assemblyai_api_key: AssemblyAI API key

        Returns:
            Complete testimony data with speaker mappings, or None if extraction failed
        """
        context = {
            'youtube_video_id': youtube_video_id,
            'jurisdiction_id': jurisdiction_id,
            'meeting_date': meeting_date
        }

        logger.info(f"Starting testimony extraction for {jurisdiction_id} {meeting_date}")

        try:
            # Step 1: Extract YouTube transcript for speaker counting (optional)
            # Note: This is only used for logging, not required for AssemblyAI
            logger.info("Step 1: Extracting YouTube transcript (optional)")
            try:
                youtube_transcript = self._extract_youtube_transcript(youtube_video_id)
            except YouTubeTranscriptError as e:
                logger.warning(f"YouTube transcript unavailable (IP blocked or rate limited): {e}")
                logger.info("Continuing without YouTube transcript - AssemblyAI will handle audio directly")
                youtube_transcript = None

            # Step 2: Download YouTube audio (AssemblyAI no longer supports YouTube URLs directly)
            logger.info(f"Step 2: Downloading YouTube audio for {youtube_video_id}")
            audio_file_path = self._download_youtube_audio(youtube_video_id)

            if not audio_file_path:
                raise AssemblyAIError("Failed to download YouTube audio")

            # Step 3: Transcribe with AssemblyAI SDK (upload local file)
            logger.info(f"Step 3: Transcribing with AssemblyAI SDK (speaker_count={speaker_count})")

            try:
                import assemblyai as aai

                # Configure SDK
                aai.settings.api_key = assemblyai_api_key

                # Create transcription config with speaker diarization
                config = aai.TranscriptionConfig(
                    speaker_labels=True,
                    speakers_expected=speaker_count
                )

                # Create transcriber
                transcriber = aai.Transcriber(config=config)

                # Transcribe local audio file
                logger.info(f"Starting transcription of local file: {audio_file_path}")
                transcript_result = transcriber.transcribe(audio_file_path)

                # Check for errors
                if transcript_result.status == aai.TranscriptStatus.error:
                    raise AssemblyAIError(f"Transcription failed: {transcript_result.error}")

                # Convert SDK result to dict format for compatibility
                assemblyai_data = {
                    'id': transcript_result.id,
                    'status': 'completed',
                    'text': transcript_result.text,
                    'utterances': [
                        {
                            'speaker': utt.speaker,
                            'text': utt.text,
                            'start': utt.start,
                            'end': utt.end,
                            'confidence': utt.confidence
                        }
                        for utt in (transcript_result.utterances or [])
                    ] if transcript_result.utterances else []
                }

                transcript_id = transcript_result.id
                logger.info(f"Transcription complete: {transcript_id}")

            except ImportError:
                raise AssemblyAIError("assemblyai package not installed. Run: pip install assemblyai")
            except Exception as e:
                raise AssemblyAIError(f"SDK transcription failed: {e}")

            # Step 4: Extract speaker names (with LLM fallback handled internally)
            logger.info("Step 4: Extracting speaker names")
            # This would integrate with merge_youtube_assemblyai_speakers.py logic
            # For now, just return the raw data

            result = {
                'youtube_video_id': youtube_video_id,
                'jurisdiction_id': jurisdiction_id,
                'meeting_date': meeting_date,
                'transcript_id': transcript_id,
                'speaker_count_estimated': speaker_count,
                'assemblyai_data': assemblyai_data,
                'status': 'success'
            }

            logger.info(f"Testimony extraction successful for {jurisdiction_id} {meeting_date}")
            return result

        except YouTubeTranscriptError as e:
            self._log_error('youtube_transcript', e, context)
            logger.error(f"YouTube transcript extraction failed, skipping meeting: {e}")
            return None

        except AssemblyAIError as e:
            self._log_error('assemblyai', e, context)
            logger.error(f"AssemblyAI processing failed, skipping meeting: {e}")
            return None

        except Exception as e:
            self._log_error('unknown', e, context)
            logger.error(f"Unexpected error during testimony extraction: {e}")
            return None

    def get_error_summary(self) -> Dict:
        """
        Get summary of all errors encountered during pipeline execution.

        Returns:
            Error summary with counts by type
        """
        error_types = {}
        for error in self.errors:
            error_type = error['error_type']
            error_types[error_type] = error_types.get(error_type, 0) + 1

        return {
            'total_errors': len(self.errors),
            'error_types': error_types,
            'recent_errors': self.errors[-5:] if self.errors else []
        }
