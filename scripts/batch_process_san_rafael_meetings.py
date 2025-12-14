#!/usr/bin/env python3
"""
Batch process San Rafael meetings from past 12 months.

This script processes multiple City Council meetings through the full testimony
extraction pipeline with progress tracking, error handling, and resume capability.

Usage:
    # Dry-run to see what will be processed
    python scripts/batch_process_san_rafael_meetings.py \
        --manifest data/pilot/san_rafael_12month_manifest.json \
        --dry-run

    # Process all meetings
    python scripts/batch_process_san_rafael_meetings.py \
        --manifest data/pilot/san_rafael_12month_manifest.json

    # Resume from specific date
    python scripts/batch_process_san_rafael_meetings.py \
        --manifest data/pilot/san_rafael_12month_manifest.json \
        --resume-from 2024-08-01

Session: 112
"""

import argparse
import json
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from testimony_extraction_pipeline import TestimonyExtractionPipeline
from testimony_quality_metrics import TestimonyQualityMetrics

# Import speaker estimation
sys.path.insert(0, str(Path(__file__).parent))
from estimate_speakers_llm import estimate_speakers_from_youtube, load_youtube_transcript


def store_testimony_in_database(result: Dict, meeting_id: str, db_path: str = "data/civic_participation.db") -> bool:
    """
    Store testimony extraction results in database.

    Args:
        result: Testimony extraction result from pipeline
        meeting_id: Meeting identifier
        db_path: Path to SQLite database

    Returns:
        True if storage succeeded, False otherwise
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Extract meeting data
        jurisdiction_id = result['jurisdiction_id']
        meeting_date = result['meeting_date']
        youtube_video_id = result['youtube_video_id']
        transcript_id = result['transcript_id']
        speaker_count_estimated = result['speaker_count_estimated']

        # Count actual speakers from AssemblyAI data
        assemblyai_data = result['assemblyai_data']
        utterances = assemblyai_data.get('utterances', [])
        unique_speakers = set(utt['speaker'] for utt in utterances)
        speaker_count_actual = len(unique_speakers)

        # Estimate cost ($3 per meeting for AssemblyAI)
        processing_cost_usd = 3.0
        processed_at = datetime.now().isoformat()

        # Insert meeting
        cursor.execute("""
            INSERT OR REPLACE INTO testimony_meetings (
                meeting_id, jurisdiction_id, meeting_date, youtube_video_id,
                assemblyai_transcript_id, speaker_count_estimated, speaker_count_actual,
                processing_cost_usd, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (meeting_id, jurisdiction_id, meeting_date, youtube_video_id,
              transcript_id, speaker_count_estimated, speaker_count_actual,
              processing_cost_usd, processed_at))

        # Group utterances by speaker
        speaker_utterances = {}
        for utt in utterances:
            speaker = utt['speaker']
            if speaker not in speaker_utterances:
                speaker_utterances[speaker] = []
            speaker_utterances[speaker].append(utt)

        # Insert speakers and utterances
        for speaker_label, speaker_utts in speaker_utterances.items():
            speaker_id = f"{meeting_id}_{speaker_label}"
            name = f"Unknown ({speaker_label})"  # Default name, will be updated by name extraction
            role = "unknown"
            confidence = "low"
            identification_method = "none"
            utterance_count = len(speaker_utts)

            cursor.execute("""
                INSERT OR REPLACE INTO testimony_speakers (
                    speaker_id, meeting_id, speaker_label, name, role,
                    confidence, identification_method, utterance_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (speaker_id, meeting_id, speaker_label, name, role,
                  confidence, identification_method, utterance_count))

            # Insert utterances
            for sequence, utt in enumerate(speaker_utts):
                utterance_id = f"{speaker_id}_{sequence}"
                text = utt['text']
                start_ms = utt['start']
                end_ms = utt['end']
                utt_confidence = utt['confidence']

                cursor.execute("""
                    INSERT OR REPLACE INTO testimony_utterances (
                        utterance_id, speaker_id, text, start_ms, end_ms,
                        confidence, sequence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (utterance_id, speaker_id, text, start_ms, end_ms,
                      utt_confidence, sequence))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"  ✗ Database storage failed: {e}")
        return False


def download_youtube_transcript(video_id: str, output_dir: str = "data/youtube_transcripts") -> Optional[str]:
    """
    Download YouTube transcript for speaker estimation.

    Args:
        video_id: YouTube video ID
        output_dir: Directory to save transcript

    Returns:
        Path to downloaded transcript file, or None if failed
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Get transcript using new API (v1.2.3+)
        api = YouTubeTranscriptApi()
        fetched_transcript = api.fetch(video_id)

        # Save in JSON3 format compatible with estimate_speakers_llm.py
        output_path = os.path.join(output_dir, f"{video_id}.en.json3")

        # Convert to JSON3 format
        json3_data = {
            "events": [
                {
                    "segs": [{"utf8": snippet.text + " "}]
                }
                for snippet in fetched_transcript.snippets
            ]
        }

        with open(output_path, 'w') as f:
            json.dump(json3_data, f, indent=2)

        print(f"  ✓ Downloaded YouTube transcript: {output_path}")
        return output_path

    except Exception as e:
        print(f"  ⚠️  Failed to download YouTube transcript: {e}")
        return None


def check_already_processed(meeting_id: str, db_path: str = "data/civic_participation.db") -> bool:
    """
    Check if meeting has already been processed in database.

    Args:
        meeting_id: Meeting identifier (jurisdiction_date_videoID)
        db_path: Path to SQLite database

    Returns:
        True if already processed, False otherwise
    """
    if not os.path.exists(db_path):
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM testimony_meetings WHERE meeting_id = ?",
            (meeting_id,)
        )

        count = cursor.fetchone()[0]
        conn.close()

        return count > 0

    except Exception as e:
        print(f"  ⚠️  Error checking database: {e}")
        return False


def process_meeting(pipeline: TestimonyExtractionPipeline, meeting_data: dict) -> Optional[Dict]:
    """
    Process a single meeting through the full pipeline.

    Args:
        pipeline: TestimonyExtractionPipeline instance
        meeting_data: Meeting metadata dict with date, youtube_id, title

    Returns:
        Result dict if successful, None if failed
    """
    meeting_id = f"san-rafael_{meeting_data['date']}_{meeting_data['youtube_id']}"

    print(f"\n[{meeting_data['date']}] {meeting_data['title']}")
    print(f"  Meeting ID: {meeting_id}")
    print(f"  YouTube: https://www.youtube.com/watch?v={meeting_data['youtube_id']}")

    # Check if already processed
    if check_already_processed(meeting_id):
        print(f"  ✓ Already processed (found in database)")
        return {'status': 'already_processed', 'meeting_id': meeting_id}

    # Step 1-2: Estimate speaker count (use existing transcript if available, otherwise skip)
    print(f"  [1/4] Estimating speaker count...")
    speaker_count = 10  # Default fallback

    # Try to use existing local transcript if available
    transcript_path = f"data/youtube_transcripts/{meeting_data['youtube_id']}.en.json3"
    if os.path.exists(transcript_path):
        try:
            estimate = estimate_speakers_from_youtube(transcript_path, verbose=False)
            speaker_count = estimate.estimated_total_speakers
            print(f"  ✓ Estimated {speaker_count} speakers from local transcript (confidence: {estimate.confidence})")
            if estimate.named_speakers:
                print(f"    Named speakers: {', '.join(estimate.named_speakers[:3])}")
                if len(estimate.named_speakers) > 3:
                    print(f"    ... and {len(estimate.named_speakers) - 3} more")
        except Exception as e:
            print(f"  ⚠️  Speaker estimation failed: {e}")
            print(f"  ℹ️  Using default speaker_count={speaker_count}")
    else:
        print(f"  ℹ️  No local transcript found, using default speaker_count={speaker_count}")

    # Step 2: Extract testimony via AssemblyAI with speaker diarization
    print(f"  [2/3] Extracting testimony (this may take 5-10 minutes)...")

    assemblyai_api_key = os.getenv('ASSEMBLYAI_API_KEY')
    if not assemblyai_api_key:
        print(f"  ✗ ASSEMBLYAI_API_KEY not set")
        return None

    try:
        result = pipeline.extract_testimony(
            youtube_video_id=meeting_data['youtube_id'],
            speaker_count=speaker_count,
            jurisdiction_id='san-rafael',
            meeting_date=meeting_data['date'],
            assemblyai_api_key=assemblyai_api_key
        )

        if not result:
            print(f"  ✗ Extraction failed")
            return None

        print(f"  ✓ Testimony extracted successfully")

        # Store in database
        if store_testimony_in_database(result, meeting_id):
            print(f"  ✓ Stored in database")
        else:
            print(f"  ⚠️  Database storage failed (continuing anyway)")

    except Exception as e:
        print(f"  ✗ Extraction error: {e}")
        return None

    # Step 3: Generate quality report
    print(f"  [3/3] Generating quality report...")
    try:
        metrics = TestimonyQualityMetrics()
        report = metrics.calculate_meeting_metrics(meeting_id)

        if report:
            print(f"  ✓ Quality Report:")
            print(f"    - Total speakers: {report.speakers_total}")
            print(f"    - Identified: {report.speakers_identified} ({report.identification_rate:.1%})")
            print(f"    - Cost: ${report.cost_total:.2f}")
        else:
            print(f"  ⚠️  No quality metrics available (meeting may not be in DB)")

    except Exception as e:
        print(f"  ⚠️  Quality report failed: {e}")

    return {'status': 'success', 'meeting_id': meeting_id, 'result': result}


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Batch process San Rafael meetings')
    parser.add_argument(
        '--manifest',
        required=True,
        help='Path to meeting manifest JSON file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print plan without processing'
    )
    parser.add_argument(
        '--resume-from',
        help='Resume from specific date (YYYY-MM-DD), skipping earlier meetings'
    )

    args = parser.parse_args()

    # Validate manifest file
    if not os.path.exists(args.manifest):
        print(f"Error: Manifest file not found: {args.manifest}")
        sys.exit(1)

    # Load manifest
    with open(args.manifest) as f:
        manifest = json.load(f)

    meetings = manifest.get('meetings', [])

    if not meetings:
        print("Error: No meetings found in manifest")
        sys.exit(1)

    # Filter if resuming
    if args.resume_from:
        meetings = [m for m in meetings if m['date'] >= args.resume_from]
        print(f"Resuming from {args.resume_from}: {len(meetings)} meetings remaining")

    print(f"\n{'='*70}")
    print(f"SAN RAFAEL 12-MONTH TESTIMONY EXTRACTION")
    print(f"{'='*70}")
    print(f"Manifest: {args.manifest}")
    print(f"Period: {manifest['period']['start']} to {manifest['period']['end']}")
    print(f"Meetings to process: {len(meetings)}")
    print(f"Estimated cost: ${len(meetings) * 3:.2f}")

    if args.dry_run:
        print(f"\n{'='*70}")
        print("DRY RUN - Would process:")
        print(f"{'='*70}")
        for i, m in enumerate(meetings, 1):
            meeting_id = f"san-rafael_{m['date']}_{m['youtube_id']}"
            already_done = check_already_processed(meeting_id)
            status = " [SKIP: already processed]" if already_done else ""
            print(f"  {i}. {m['date']}: {m['title']}{status}")
            print(f"     YouTube: https://www.youtube.com/watch?v={m['youtube_id']}")

        print(f"\n{'='*70}")
        print(f"SUMMARY")
        print(f"{'='*70}")
        print(f"Total meetings: {len(meetings)}")
        print(f"Estimated time: {len(meetings) * 7} minutes ({len(meetings) * 7 / 60:.1f} hours)")
        print(f"Estimated cost: ${len(meetings) * 3:.2f}")
        return

    # Initialize pipeline
    print(f"\nInitializing pipeline...")
    pipeline = TestimonyExtractionPipeline()

    # Process each meeting
    results = []
    successful = 0
    failed = 0
    skipped = 0

    start_time = datetime.now()

    for i, meeting in enumerate(meetings, 1):
        print(f"\n{'='*70}")
        print(f"MEETING {i}/{len(meetings)}")
        print(f"{'='*70}")

        result = process_meeting(pipeline, meeting)

        if result:
            if result.get('status') == 'already_processed':
                skipped += 1
                results.append({'meeting': meeting, 'status': 'skipped'})
            else:
                successful += 1
                results.append({'meeting': meeting, 'status': 'success', 'result': result})
        else:
            failed += 1
            results.append({'meeting': meeting, 'status': 'failed'})

    # Calculate elapsed time
    elapsed = datetime.now() - start_time
    elapsed_minutes = elapsed.total_seconds() / 60

    # Summary
    print(f"\n{'='*70}")
    print("BATCH PROCESSING COMPLETE")
    print(f"{'='*70}")
    print(f"Total meetings: {len(meetings)}")
    print(f"Successful: {successful}")
    print(f"Skipped (already processed): {skipped}")
    print(f"Failed: {failed}")
    print(f"Time elapsed: {elapsed_minutes:.1f} minutes")

    if successful > 0:
        avg_time = elapsed_minutes / successful
        print(f"Average time per meeting: {avg_time:.1f} minutes")

    # Show error summary if any failures
    if failed > 0:
        error_summary = pipeline.get_error_summary()
        print(f"\n{'='*70}")
        print("ERROR SUMMARY")
        print(f"{'='*70}")
        print(f"Total errors: {error_summary.get('total_errors', 0)}")

        error_types = error_summary.get('error_types', {})
        if error_types:
            for error_type, count in error_types.items():
                print(f"  - {error_type}: {count}")

        print(f"\nDetailed error log: data/testimony_extraction_errors.json")

    # Next steps
    print(f"\n{'='*70}")
    print("NEXT STEPS")
    print(f"{'='*70}")
    print("1. Generate aggregate quality report:")
    print("   python scripts/testimony_quality_report.py --jurisdiction san-rafael")
    print("\n2. Analyze testimony patterns (SQL queries in next_session_prompt.md)")
    print("\n3. Create foundation proposal data package")


if __name__ == '__main__':
    main()
