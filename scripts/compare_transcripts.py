#!/usr/bin/env python3
"""
Compare YouTube auto-generated transcripts with AssemblyAI transcripts.

Usage:
    python scripts/compare_transcripts.py \
        --youtube data/youtube_transcripts/MpxrGRb16HQ.en.json3 \
        --assemblyai data/testimony/testimony_MpxrGRb16HQ.json
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict
import difflib


def load_youtube_transcript(path: str) -> List[Dict]:
    """Load YouTube JSON3 transcript."""
    with open(path) as f:
        data = json.load(f)

    # JSON3 format has events array
    events = data.get("events", [])

    segments = []
    for event in events:
        # Skip events without segments (e.g., formatting)
        if "segs" not in event:
            continue

        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)

        # Concatenate all text segments
        text = ""
        for seg in event.get("segs", []):
            if "utf8" in seg:
                text += seg["utf8"]

        if text.strip():
            segments.append({
                "start": start_ms,
                "end": start_ms + duration_ms,
                "text": text.strip()
            })

    return segments


def load_assemblyai_transcript(path: str) -> List[Dict]:
    """Load AssemblyAI transcript."""
    with open(path) as f:
        data = json.load(f)

    return data.get("utterances", [])


def get_full_text(segments: List[Dict]) -> str:
    """Extract full text from segments."""
    return " ".join(seg["text"] for seg in segments)


def compare_texts(youtube_text: str, assemblyai_text: str) -> Dict:
    """Compare two transcript texts."""
    # Character-level similarity
    similarity = difflib.SequenceMatcher(None, youtube_text, assemblyai_text).ratio()

    # Word counts
    yt_words = youtube_text.split()
    aai_words = assemblyai_text.split()

    # Sample differences
    diff = list(difflib.unified_diff(
        yt_words[:100],  # First 100 words
        aai_words[:100],
        lineterm='',
        n=0
    ))

    return {
        "similarity_ratio": similarity,
        "youtube_word_count": len(yt_words),
        "assemblyai_word_count": len(aai_words),
        "word_count_diff": len(aai_words) - len(yt_words),
        "sample_diff": diff[:20]  # First 20 diff lines
    }


def analyze_speaker_diarization(assemblyai_segments: List[Dict]) -> Dict:
    """Analyze AssemblyAI speaker diarization."""
    speakers = set()
    speaker_utterances = {}

    for seg in assemblyai_segments:
        speaker = seg.get("speaker", "Unknown")
        speakers.add(speaker)

        if speaker not in speaker_utterances:
            speaker_utterances[speaker] = []
        speaker_utterances[speaker].append(seg)

    # Calculate speaking time per speaker
    speaker_times = {}
    for speaker, utterances in speaker_utterances.items():
        total_time = sum(
            (utt["end"] - utt["start"]) / 1000  # Convert ms to seconds
            for utt in utterances
        )
        speaker_times[speaker] = total_time

    return {
        "speaker_count": len(speakers),
        "speakers": list(speakers),
        "utterances_per_speaker": {
            speaker: len(utts) for speaker, utts in speaker_utterances.items()
        },
        "speaking_time_seconds": speaker_times
    }


def sample_comparison(youtube_segs: List[Dict], assemblyai_segs: List[Dict], num_samples: int = 5) -> List[Dict]:
    """Compare sample segments from both transcripts."""
    samples = []

    # Sample at different timestamps
    total_duration = max(seg["end"] for seg in youtube_segs)
    interval = total_duration / (num_samples + 1)

    for i in range(1, num_samples + 1):
        timestamp = int(i * interval)

        # Find closest YouTube segment
        yt_seg = min(youtube_segs, key=lambda s: abs(s["start"] - timestamp))

        # Find closest AssemblyAI segment
        aai_seg = min(assemblyai_segs, key=lambda s: abs(s["start"] - timestamp))

        samples.append({
            "timestamp_ms": timestamp,
            "timestamp_min": timestamp / 60000,
            "youtube": {
                "text": yt_seg["text"][:200],  # First 200 chars
                "start": yt_seg["start"]
            },
            "assemblyai": {
                "text": aai_seg["text"][:200],
                "speaker": aai_seg.get("speaker", "Unknown"),
                "start": aai_seg["start"]
            }
        })

    return samples


def main():
    parser = argparse.ArgumentParser(description="Compare YouTube and AssemblyAI transcripts")
    parser.add_argument("--youtube", required=True, help="YouTube transcript JSON3 file")
    parser.add_argument("--assemblyai", required=True, help="AssemblyAI transcript JSON file")
    args = parser.parse_args()

    print("Loading transcripts...")
    youtube_segs = load_youtube_transcript(args.youtube)
    assemblyai_segs = load_assemblyai_transcript(args.assemblyai)

    print(f"YouTube segments: {len(youtube_segs)}")
    print(f"AssemblyAI utterances: {len(assemblyai_segs)}")

    # Full text comparison
    print("\n" + "="*60)
    print("TEXT COMPARISON")
    print("="*60)

    yt_text = get_full_text(youtube_segs)
    aai_text = get_full_text(assemblyai_segs)

    text_comp = compare_texts(yt_text, aai_text)

    print(f"Similarity ratio: {text_comp['similarity_ratio']:.2%}")
    print(f"YouTube word count: {text_comp['youtube_word_count']:,}")
    print(f"AssemblyAI word count: {text_comp['assemblyai_word_count']:,}")
    print(f"Word count difference: {text_comp['word_count_diff']:,} ({text_comp['word_count_diff'] / text_comp['youtube_word_count'] * 100:+.1f}%)")

    # Speaker diarization (AssemblyAI only)
    print("\n" + "="*60)
    print("SPEAKER DIARIZATION (AssemblyAI)")
    print("="*60)

    diarization = analyze_speaker_diarization(assemblyai_segs)

    print(f"Detected speakers: {diarization['speaker_count']}")
    for speaker in diarization['speakers']:
        utterances = diarization['utterances_per_speaker'][speaker]
        time_sec = diarization['speaking_time_seconds'][speaker]
        time_min = time_sec / 60
        print(f"  Speaker {speaker}: {utterances} utterances, {time_min:.1f} minutes")

    # Sample comparison
    print("\n" + "="*60)
    print("SAMPLE COMPARISONS (5 random points)")
    print("="*60)

    samples = sample_comparison(youtube_segs, assemblyai_segs, num_samples=5)

    for i, sample in enumerate(samples, 1):
        print(f"\nSample {i} - {sample['timestamp_min']:.1f} minutes")
        print(f"  YouTube: {sample['youtube']['text']}")
        print(f"  AssemblyAI (Speaker {sample['assemblyai']['speaker']}): {sample['assemblyai']['text']}")

        # Calculate similarity for this sample
        similarity = difflib.SequenceMatcher(
            None,
            sample['youtube']['text'],
            sample['assemblyai']['text']
        ).ratio()
        print(f"  Similarity: {similarity:.2%}")

    # Overall assessment
    print("\n" + "="*60)
    print("OVERALL ASSESSMENT")
    print("="*60)

    if text_comp['similarity_ratio'] > 0.9:
        print("✓ Very high accuracy - transcripts are nearly identical")
    elif text_comp['similarity_ratio'] > 0.8:
        print("✓ High accuracy - transcripts are very similar")
    elif text_comp['similarity_ratio'] > 0.7:
        print("⚠ Moderate accuracy - some differences present")
    else:
        print("✗ Low accuracy - significant differences")

    print(f"\nKey advantages of AssemblyAI:")
    print(f"  • Speaker diarization ({diarization['speaker_count']} speakers detected)")
    print(f"  • Structured output with timestamps")
    print(f"  • API access for automation")

    print(f"\nKey advantages of YouTube:")
    print(f"  • Free (auto-generated)")
    print(f"  • More segments ({len(youtube_segs)} vs {len(assemblyai_segs)})")
    print(f"  • Already available (no processing needed)")


if __name__ == "__main__":
    main()
