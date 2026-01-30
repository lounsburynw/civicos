#!/usr/bin/env python3
"""
Backfill speaker metadata for existing transcripts.

Runs LLM-based speaker detection on transcripts that don't have
speakers_metadata, then updates them in PostgreSQL.

Usage:
    # Dry run (see what would be processed)
    python scripts/backfill_speaker_metadata.py --dry-run

    # Process all transcripts
    python scripts/backfill_speaker_metadata.py

    # Process specific jurisdiction
    python scripts/backfill_speaker_metadata.py --jurisdiction city-san-rafael

    # Limit number of transcripts (useful for testing)
    python scripts/backfill_speaker_metadata.py --limit 5

    # Skip LLM (pattern-only detection, free but less accurate)
    python scripts/backfill_speaker_metadata.py --no-llm

Cost: ~$0.0014 per transcript with Gemini Flash (~$0.05 for 35 transcripts)
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/civicos/src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/civicos-services/src"))

from dotenv import load_dotenv
load_dotenv()


def detect_speaker_roles(utterances: List[Dict], use_llm: bool = True) -> Dict[str, Dict]:
    """
    Detect speaker roles and names from transcript utterances.

    Adapted from civicos_extraction.cli.transcribe._detect_speaker_roles
    """
    if not utterances:
        return {}

    try:
        from civicos._internal.meetings.transcript import (
            SpeakerRoleDetector,
            TranscriptUtterance,
        )

        # Convert dict utterances to TranscriptUtterance objects
        transcript_utts = []
        for utt in utterances:
            transcript_utts.append(TranscriptUtterance(
                speaker=utt["speaker"],
                text=utt["text"],
                start_ms=utt.get("start", 0),
                end_ms=utt.get("end", 0),
            ))

        # Get LLM provider if requested
        llm_provider = None
        if use_llm:
            llm_provider = get_llm_provider()

        # Run role detection
        detector = SpeakerRoleDetector(llm_provider=llm_provider)
        speaker_infos = detector.detect_roles(transcript_utts)

        # Convert SpeakerInfo objects to serializable dicts
        # Assign friendly names to unnamed speakers by role
        public_counter = 0
        staff_counter = 0
        unknown_counter = 0

        result = {}
        for speaker_id, info in sorted(speaker_infos.items()):
            name = info.name
            # Assign friendly anonymous identifier if no name detected
            if not name:
                if info.role == "public":
                    public_counter += 1
                    name = f"Public Speaker {public_counter}"
                elif info.role == "staff":
                    staff_counter += 1
                    name = f"Staff Member {staff_counter}"
                elif info.role == "unknown":
                    unknown_counter += 1
                    name = f"Speaker {unknown_counter}"

            result[speaker_id] = {
                "name": name,
                "role": info.role,
                "title": info.title,
                "confidence": info.confidence,
            }
        return result

    except ImportError as e:
        print(f"  Error: Speaker detection unavailable: {e}")
        return {}
    except Exception as e:
        print(f"  Error: Speaker detection failed: {e}")
        return {}


def get_llm_provider():
    """Get LLM provider for speaker detection."""
    import os
    try:
        from civicos_services.core.llm_provider import get_model

        model = os.environ.get("SPEAKER_DETECTION_MODEL", "gemini-2.0-flash-exp")
        return get_model(model)
    except ImportError:
        print("  Warning: civicos_services not available, using pattern-only detection")
        return None
    except Exception as e:
        print(f"  Warning: Failed to initialize LLM provider: {e}")
        return None


def backfill_speaker_metadata(
    jurisdiction: Optional[str] = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
    use_llm: bool = True,
):
    """
    Backfill speaker metadata for transcripts.

    Args:
        jurisdiction: Specific jurisdiction to process (default: all)
        dry_run: If True, only show what would be done
        limit: Maximum number of transcripts to process
        use_llm: If True, use LLM for enhanced detection
    """
    from civicos import CivicOS

    # Default to san-rafael for pilot
    jurisdiction = jurisdiction or "city-san-rafael"

    print(f"Loading transcripts for {jurisdiction}...")
    c = CivicOS(jurisdiction)

    # Verify we're using PostgreSQL
    backend_name = type(c._storage).__name__
    if backend_name != "PostgresBackend":
        print(f"Warning: Using {backend_name}, not PostgresBackend")
        print("Set DATABASE_URL in .env to use PostgreSQL")

    transcripts = c._storage.get_transcripts(jurisdiction)
    print(f"Found {len(transcripts)} total transcripts")

    # Filter to transcripts without speakers_metadata
    to_process = []
    for t in transcripts:
        transcript_data = t.get("transcript", {})
        if not transcript_data.get("speakers_metadata"):
            to_process.append(t)

    print(f"Transcripts needing backfill: {len(to_process)}")

    if limit:
        to_process = to_process[:limit]
        print(f"Limited to {limit} transcripts")

    if not to_process:
        print("Nothing to backfill!")
        return

    # Calculate cost estimate
    total_utterances = sum(
        len(t.get("transcript", {}).get("utterances", []))
        for t in to_process
    )
    estimated_cost = (total_utterances * 50 + len(to_process) * 500) / 1_000_000 * 0.075
    print(f"\nEstimated cost: ${estimated_cost:.4f} ({total_utterances:,} utterances)")

    if dry_run:
        print("\n--- DRY RUN ---")
        for t in to_process:
            video_id = t.get("video_id", "unknown")
            speakers = t.get("speakers_count", 0)
            utterances = t.get("utterances_count", 0)
            print(f"  Would process: {video_id} ({speakers} speakers, {utterances} utterances)")
        print(f"\nTotal: {len(to_process)} transcripts")
        return

    # Process transcripts
    print(f"\nProcessing {len(to_process)} transcripts...")
    success_count = 0
    error_count = 0

    for i, t in enumerate(to_process, 1):
        video_id = t.get("video_id", "unknown")
        transcript_data = t.get("transcript", {})
        utterances = transcript_data.get("utterances", [])

        print(f"\n[{i}/{len(to_process)}] {video_id}")
        print(f"  Speakers: {t.get('speakers_count', 0)}, Utterances: {len(utterances)}")

        if not utterances:
            print("  Skipping: No utterances")
            continue

        # Run speaker detection
        print(f"  Running speaker detection (LLM={use_llm})...")
        speakers_metadata = detect_speaker_roles(utterances, use_llm=use_llm)

        if not speakers_metadata:
            print("  Warning: No speaker metadata returned")
            error_count += 1
            continue

        named_count = sum(
            1 for s in speakers_metadata.values()
            if s.get("name") and not s["name"].startswith(("Public Speaker", "Staff Member", "Speaker "))
        )
        print(f"  Detected: {len(speakers_metadata)} speakers, {named_count} named")

        # Update transcript data
        transcript_data["speakers_metadata"] = speakers_metadata

        # Re-store transcript (upsert semantics)
        try:
            updated_transcript = {
                "video_id": video_id,
                "utterances": utterances,
                "speakers_metadata": speakers_metadata,
                # Preserve other fields
                "cost_usd": transcript_data.get("cost_usd"),
                "language": transcript_data.get("language"),
                "processed_at": transcript_data.get("processed_at"),
                "assemblyai_id": transcript_data.get("assemblyai_id"),
                "speakers_count": transcript_data.get("speakers_count"),
                "utterances_count": transcript_data.get("utterances_count"),
                "processing_service": transcript_data.get("processing_service"),
                "audio_duration_minutes": transcript_data.get("audio_duration_minutes"),
                "processing_time_seconds": transcript_data.get("processing_time_seconds"),
            }

            c._storage.store_transcripts(jurisdiction, [updated_transcript])
            print(f"  Stored successfully")
            success_count += 1

        except Exception as e:
            print(f"  Error storing: {e}")
            error_count += 1

    print(f"\n{'='*50}")
    print(f"Backfill complete!")
    print(f"  Success: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Skipped: {len(to_process) - success_count - error_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill speaker metadata for existing transcripts"
    )
    parser.add_argument(
        "--jurisdiction", "-j",
        help="Jurisdiction to process (default: city-san-rafael)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Maximum number of transcripts to process"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use pattern-only detection (free but less accurate)"
    )

    args = parser.parse_args()

    backfill_speaker_metadata(
        jurisdiction=args.jurisdiction,
        dry_run=args.dry_run,
        limit=args.limit,
        use_llm=not args.no_llm,
    )


if __name__ == "__main__":
    main()
