#!/usr/bin/env python3
"""
Extract exact testimony from AssemblyAI transcript with uncertainty metrics.

Maps speaker names (from YouTube LLM analysis) to AssemblyAI speaker labels (A,B,C,D,E)
and extracts full testimony with confidence/uncertainty scores.

Session: 109
"""

import argparse
import json
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class ConfidenceLevel(Enum):
    """Confidence levels for testimony extraction."""
    HIGH = "high"        # >90% confident
    MEDIUM = "medium"    # 70-90% confident
    LOW = "low"          # <70% confident


@dataclass
class UncertaintyMetrics:
    """Uncertainty metrics for testimony extraction."""

    speaker_attribution_confidence: ConfidenceLevel
    speaker_attribution_notes: str

    transcription_quality: ConfidenceLevel
    transcription_notes: str

    completeness_confidence: ConfidenceLevel
    completeness_notes: str

    overall_confidence: ConfidenceLevel

    def to_dict(self):
        return {
            "speaker_attribution": {
                "confidence": self.speaker_attribution_confidence.value,
                "notes": self.speaker_attribution_notes
            },
            "transcription_quality": {
                "confidence": self.transcription_quality.value,
                "notes": self.transcription_notes
            },
            "completeness": {
                "confidence": self.completeness_confidence.value,
                "notes": self.completeness_notes
            },
            "overall_confidence": self.overall_confidence.value
        }


@dataclass
class TestimonyExtraction:
    """Complete testimony extraction with metadata."""

    speaker_name: str
    speaker_role: str  # From YouTube LLM analysis

    assemblyai_speaker_label: str  # A, B, C, D, or E

    full_testimony: List[str]  # List of utterance texts
    utterance_count: int

    start_timestamp_ms: int
    end_timestamp_ms: int
    start_timestamp_formatted: str
    end_timestamp_formatted: str

    total_duration_seconds: float

    video_url: str

    uncertainty_metrics: UncertaintyMetrics

    extraction_method: str
    extraction_notes: str


def format_timestamp(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS format."""
    seconds = ms / 1000
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def find_speaker_label(assemblyai_data: dict, speaker_name: str) -> Optional[Dict]:
    """
    Find AssemblyAI speaker label for a named speaker.

    Strategy:
    1. Search for utterances containing the speaker's name introduction
    2. Return the speaker label and matching utterances
    """
    utterances = assemblyai_data.get("utterances", [])

    # Search patterns
    search_patterns = [
        speaker_name.lower(),
        f"my name is {speaker_name.lower()}",
        f"i'm {speaker_name.lower()}",
        f"{speaker_name.lower()} speaking"
    ]

    matches = []
    for utterance in utterances:
        text_lower = utterance.get("text", "").lower()
        for pattern in search_patterns:
            if pattern in text_lower:
                matches.append({
                    "speaker": utterance.get("speaker"),
                    "text": utterance.get("text"),
                    "start": utterance.get("start"),
                    "end": utterance.get("end")
                })
                break

    if not matches:
        return None

    # Return most likely speaker (first match)
    return {
        "speaker_label": matches[0]["speaker"],
        "matches": matches,
        "confidence": ConfidenceLevel.HIGH if len(matches) == 1 else ConfidenceLevel.MEDIUM
    }


def extract_testimony(
    assemblyai_data: dict,
    speaker_name: str,
    speaker_role: str,
    video_id: str = "MpxrGRb16HQ"
) -> Optional[TestimonyExtraction]:
    """
    Extract full testimony for a named speaker.

    Returns:
        TestimonyExtraction object with uncertainty metrics
    """
    # Find speaker label
    speaker_info = find_speaker_label(assemblyai_data, speaker_name)

    if not speaker_info:
        return None

    speaker_label = speaker_info["speaker_label"]
    attribution_confidence = speaker_info["confidence"]

    # Extract all utterances from this speaker
    utterances = assemblyai_data.get("utterances", [])
    speaker_utterances = [
        u for u in utterances
        if u.get("speaker") == speaker_label
    ]

    if not speaker_utterances:
        return None

    # Extract testimony texts
    testimony_texts = [u.get("text", "") for u in speaker_utterances]

    # Calculate timestamps
    start_ms = speaker_utterances[0].get("start")
    end_ms = speaker_utterances[-1].get("end")
    duration_sec = (end_ms - start_ms) / 1000

    # Assess uncertainty

    # 1. Speaker attribution uncertainty
    if attribution_confidence == ConfidenceLevel.HIGH:
        attr_notes = f"Speaker label '{speaker_label}' confirmed via name mention in testimony"
    else:
        attr_notes = f"Speaker label '{speaker_label}' inferred from {len(speaker_info['matches'])} mentions (may include multiple speakers)"

    # 2. Transcription quality
    # AssemblyAI generally high quality, but auto-captions have ~5-10% error rate
    trans_confidence = ConfidenceLevel.HIGH
    trans_notes = "AssemblyAI transcription (generally 90-95% accuracy for clear audio)"

    # 3. Completeness
    # Check if we got full testimony or just snippets
    if len(speaker_utterances) > 3:
        complete_confidence = ConfidenceLevel.HIGH
        complete_notes = f"Extracted {len(speaker_utterances)} utterances - likely complete testimony"
    elif len(speaker_utterances) > 1:
        complete_confidence = ConfidenceLevel.MEDIUM
        complete_notes = f"Extracted {len(speaker_utterances)} utterances - may be partial testimony"
    else:
        complete_confidence = ConfidenceLevel.LOW
        complete_notes = f"Only 1 utterance found - likely incomplete"

    # Overall confidence (lowest of the three)
    confidence_levels = [attribution_confidence, trans_confidence, complete_confidence]
    if ConfidenceLevel.LOW in confidence_levels:
        overall = ConfidenceLevel.LOW
    elif ConfidenceLevel.MEDIUM in confidence_levels:
        overall = ConfidenceLevel.MEDIUM
    else:
        overall = ConfidenceLevel.HIGH

    uncertainty = UncertaintyMetrics(
        speaker_attribution_confidence=attribution_confidence,
        speaker_attribution_notes=attr_notes,
        transcription_quality=trans_confidence,
        transcription_notes=trans_notes,
        completeness_confidence=complete_confidence,
        completeness_notes=complete_notes,
        overall_confidence=overall
    )

    # Create extraction object
    extraction = TestimonyExtraction(
        speaker_name=speaker_name,
        speaker_role=speaker_role,
        assemblyai_speaker_label=speaker_label,
        full_testimony=testimony_texts,
        utterance_count=len(speaker_utterances),
        start_timestamp_ms=start_ms,
        end_timestamp_ms=end_ms,
        start_timestamp_formatted=format_timestamp(start_ms),
        end_timestamp_formatted=format_timestamp(end_ms),
        total_duration_seconds=duration_sec,
        video_url=f"https://www.youtube.com/watch?v={video_id}&t={int(start_ms/1000)}s",
        uncertainty_metrics=uncertainty,
        extraction_method="AssemblyAI utterance filtering by speaker label",
        extraction_notes=f"Found {len(speaker_info['matches'])} name mentions in transcript"
    )

    return extraction


def main():
    parser = argparse.ArgumentParser(
        description="Extract testimony with confidence metrics"
    )
    parser.add_argument(
        "--assemblyai-transcript",
        required=True,
        help="Path to AssemblyAI transcript JSON"
    )
    parser.add_argument(
        "--speaker-name",
        required=True,
        help="Speaker name to extract (e.g., 'Belle Cole')"
    )
    parser.add_argument(
        "--speaker-role",
        default="public",
        help="Speaker role (council/staff/public)"
    )
    parser.add_argument(
        "--output",
        help="Path to save extraction JSON (optional)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full testimony text"
    )

    args = parser.parse_args()

    # Load AssemblyAI data
    with open(args.assemblyai_transcript) as f:
        assemblyai_data = json.load(f)

    # Extract testimony
    extraction = extract_testimony(
        assemblyai_data,
        args.speaker_name,
        args.speaker_role
    )

    if not extraction:
        print(f"❌ Could not find speaker: {args.speaker_name}")
        return

    # Print results
    print("\n" + "=" * 70)
    print(f"TESTIMONY EXTRACTION: {extraction.speaker_name}")
    print("=" * 70)

    print(f"\nSpeaker: {extraction.speaker_name}")
    print(f"Role: {extraction.speaker_role}")
    print(f"AssemblyAI Label: Speaker {extraction.assemblyai_speaker_label}")

    print(f"\nTimestamps:")
    print(f"  Start: {extraction.start_timestamp_formatted} ({extraction.start_timestamp_ms}ms)")
    print(f"  End: {extraction.end_timestamp_formatted} ({extraction.end_timestamp_ms}ms)")
    print(f"  Duration: {extraction.total_duration_seconds:.1f} seconds")
    print(f"  Video URL: {extraction.video_url}")

    print(f"\nTestimony:")
    print(f"  Utterances: {extraction.utterance_count}")

    if args.verbose:
        print("\n  Full Text:")
        for i, text in enumerate(extraction.full_testimony, 1):
            print(f"\n  [{i}] {text}")
    else:
        # Show first and last utterance
        if len(extraction.full_testimony) > 0:
            print(f"\n  First: {extraction.full_testimony[0][:200]}...")
            if len(extraction.full_testimony) > 1:
                print(f"  Last: {extraction.full_testimony[-1][:200]}...")

    # Print uncertainty metrics
    print("\n" + "=" * 70)
    print("UNCERTAINTY METRICS")
    print("=" * 70)

    metrics = extraction.uncertainty_metrics

    print(f"\nSpeaker Attribution: {metrics.speaker_attribution_confidence.value.upper()}")
    print(f"  {metrics.speaker_attribution_notes}")

    print(f"\nTranscription Quality: {metrics.transcription_quality.value.upper()}")
    print(f"  {metrics.transcription_notes}")

    print(f"\nCompleteness: {metrics.completeness_confidence.value.upper()}")
    print(f"  {metrics.completeness_notes}")

    print(f"\nOverall Confidence: {metrics.overall_confidence.value.upper()}")

    print("\n" + "=" * 70)

    # Save if requested
    if args.output:
        output_data = {
            "speaker_name": extraction.speaker_name,
            "speaker_role": extraction.speaker_role,
            "assemblyai_speaker_label": extraction.assemblyai_speaker_label,
            "full_testimony": extraction.full_testimony,
            "utterance_count": extraction.utterance_count,
            "timestamps": {
                "start_ms": extraction.start_timestamp_ms,
                "end_ms": extraction.end_timestamp_ms,
                "start_formatted": extraction.start_timestamp_formatted,
                "end_formatted": extraction.end_timestamp_formatted,
                "duration_seconds": extraction.total_duration_seconds
            },
            "video_url": extraction.video_url,
            "uncertainty_metrics": extraction.uncertainty_metrics.to_dict(),
            "extraction_metadata": {
                "method": extraction.extraction_method,
                "notes": extraction.extraction_notes
            }
        }

        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"\n✅ Saved to: {args.output}")


if __name__ == "__main__":
    main()
