#!/usr/bin/env python3
"""
Re-run AssemblyAI transcription with corrected speaker parameters.

Based on full transcript analysis (Session 109) which found 50 speakers,
we re-run with min=40, max=60 to test if better diarization is possible.

Session: 109
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

try:
    import assemblyai as aai
except ImportError:
    print("Error: assemblyai package not installed")
    print("Install with: pip install assemblyai")
    exit(1)

load_dotenv()


def upload_and_transcribe(
    audio_path: str,
    min_speakers: int = 40,
    max_speakers: int = 60,
    output_path: str = None,
    verbose: bool = False
) -> dict:
    """
    Upload audio to AssemblyAI and transcribe with speaker diarization.

    Args:
        audio_path: Path to audio file
        min_speakers: Minimum expected speakers
        max_speakers: Maximum expected speakers
        output_path: Where to save result JSON
        verbose: Print progress updates

    Returns:
        Transcript data with speakers
    """
    # Configure API
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY not found in environment")

    aai.settings.api_key = api_key

    if verbose:
        print(f"\n{'='*70}")
        print("AssemblyAI Re-run with Updated Speaker Parameters")
        print(f"{'='*70}\n")
        print(f"Audio file: {audio_path}")
        print(f"File size: {os.path.getsize(audio_path) / (1024*1024):.1f} MB")
        print(f"\nSpeaker configuration:")
        print(f"  Min speakers: {min_speakers}")
        print(f"  Max speakers: {max_speakers}")
        print(f"  Previous run: min=5, max=10 → detected 5 speakers")
        print(f"\nUploading...")

    # Configure transcription
    speaker_opts = aai.types.SpeakerOptions(
        min_speakers_expected=min_speakers,
        max_speakers_expected=max_speakers
    )

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        speaker_options=speaker_opts,  # Correct parameter name
        language_code="en"
    )

    # Create transcriber
    transcriber = aai.Transcriber(config=config)

    # Start transcription
    start_time = time.time()
    transcript = transcriber.transcribe(audio_path)

    # Wait for completion
    if verbose:
        print(f"Transcription started: {transcript.id}")
        print("Status: Processing...")

    while transcript.status not in [aai.TranscriptStatus.completed, aai.TranscriptStatus.error]:
        time.sleep(5)
        transcript = transcriber.get_transcript(transcript.id)
        if verbose:
            elapsed = time.time() - start_time
            print(f"  Elapsed: {elapsed:.0f}s - Status: {transcript.status}")

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"Transcription failed: {transcript.error}")

    processing_time = time.time() - start_time

    if verbose:
        print(f"\n✅ Transcription complete!")
        print(f"Processing time: {processing_time:.1f} seconds")

    # Extract data
    speakers_detected = len(set(
        utterance.speaker
        for utterance in transcript.utterances
        if hasattr(utterance, 'speaker')
    ))

    # Calculate cost (AssemblyAI pricing: ~$0.00025/second)
    audio_duration_seconds = transcript.audio_duration / 1000
    cost_usd = audio_duration_seconds * 0.00025

    result = {
        "assemblyai_id": transcript.id,
        "video_id": Path(audio_path).stem,
        "processed_at": datetime.now().isoformat(),
        "processing_service": "assemblyai",
        "processing_time_seconds": processing_time,

        "speaker_config": {
            "min_speakers_expected": min_speakers,
            "max_speakers_expected": max_speakers
        },

        "speakers_count": speakers_detected,
        "utterances_count": len(transcript.utterances),
        "audio_duration_minutes": audio_duration_seconds / 60,
        "cost_usd": round(cost_usd, 2),

        "utterances": [
            {
                "speaker": utterance.speaker,
                "text": utterance.text,
                "start": utterance.start,
                "end": utterance.end
            }
            for utterance in transcript.utterances
        ],

        "language": transcript.language_code,
        "meeting_url": f"https://www.youtube.com/watch?v={Path(audio_path).stem}",

        "metadata": {
            "experiment": "rerun_with_full_transcript_speaker_estimate",
            "original_run_speakers": 5,
            "full_transcript_analysis_speakers": 50,
            "hypothesis": "Better speaker parameters will improve diarization"
        }
    }

    if verbose:
        print(f"\nResults:")
        print(f"  Speakers detected: {speakers_detected}")
        print(f"  Utterances: {len(transcript.utterances)}")
        print(f"  Audio duration: {audio_duration_seconds/60:.1f} minutes")
        print(f"  Cost: ${cost_usd:.2f}")
        print(f"\n{'='*70}")

    # Save output
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        if verbose:
            print(f"\n✅ Saved to: {output_path}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Re-run AssemblyAI with updated speaker parameters"
    )
    parser.add_argument(
        "--audio",
        required=True,
        help="Path to audio file (MP3)"
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=40,
        help="Minimum expected speakers (default: 40)"
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        default=60,
        help="Maximum expected speakers (default: 60)"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for transcript JSON"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress"
    )

    args = parser.parse_args()

    # Run transcription
    result = upload_and_transcribe(
        audio_path=args.audio,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        output_path=args.output,
        verbose=args.verbose
    )

    # Print comparison
    print("\n" + "="*70)
    print("COMPARISON WITH ORIGINAL RUN")
    print("="*70)
    print(f"\nOriginal (min=5, max=10):")
    print(f"  Speakers detected: 5")
    print(f"  Utterances: 217")

    print(f"\nNew (min={args.min_speakers}, max={args.max_speakers}):")
    print(f"  Speakers detected: {result['speakers_count']}")
    print(f"  Utterances: {result['utterances_count']}")

    improvement = result['speakers_count'] - 5
    print(f"\nImprovement: {improvement:+d} speakers ({improvement/5*100:+.0f}%)")

    if result['speakers_count'] > 5:
        print("\n✅ Better diarization! More speakers detected.")
    elif result['speakers_count'] == 5:
        print("\n⚠️  No improvement. Same speaker count as original.")
    else:
        print("\n❌ Worse diarization. Fewer speakers detected.")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
