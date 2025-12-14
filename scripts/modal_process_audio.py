#!/usr/bin/env python3
"""
Modal-based Audio Processing - Process pre-downloaded YouTube audio files

This script processes audio files that were downloaded locally (bypassing
YouTube's bot detection) using Modal's GPU infrastructure.

Setup (one-time):
    pip install modal
    modal token new
    modal secret create huggingface HF_TOKEN=your_hf_token_here

Usage:
    # Process all audio files in directory
    modal run scripts/modal_process_audio.py::process_batch --audio-dir data/youtube_audio

    # Process single file
    modal run scripts/modal_process_audio.py::process_single --audio-file data/youtube_audio/rbbh5eOeOtM.mp3
"""

import modal
import os
import json
from typing import Dict
from datetime import datetime
from pathlib import Path

# Modal app configuration
app = modal.App("civic-audio-processing")

# Define Modal volume for audio files
audio_volume = modal.Volume.from_name("civic-audio", create_if_missing=True)

# Define Modal image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "ffmpeg",  # Required for audio processing
        "git",     # Required for package installations
    )
    .pip_install(
        "torch==2.4.0",        # PyTorch (CUDA-compatible)
        "torchaudio==2.4.0",   # Audio processing
        "pyannote.audio",      # Speaker diarization
    )
    # Install whisperx from GitHub (works on CUDA)
    .run_commands(
        "pip install git+https://github.com/m-bain/whisperx.git"
    )
)


@app.function(
    image=image,
    gpu="A10G",  # Fast, cost-effective ($1.10/hour = $0.22/12min meeting)
    timeout=1800,  # 30 min max per meeting
    secrets=[modal.Secret.from_name("huggingface")],
    retries=modal.Retries(
        max_retries=2,
        initial_delay=1.0,
        backoff_coefficient=2.0,
    ),
)
def process_audio_file(audio_data: bytes, video_id: str) -> Dict:
    """
    Process audio data with WhisperX + PyAnnote diarization.

    Args:
        audio_data: Raw audio file bytes
        video_id: Video ID for output naming

    Returns:
        Dictionary with video_id, speakers_count, utterances, duration, etc.
    """
    import whisperx
    import torch
    from pyannote.audio import Pipeline
    import tempfile

    hf_token = os.environ["HF_TOKEN"]

    print(f"\n{'='*70}")
    print(f"🎬 Processing: {video_id}")
    print(f"   Size: {len(audio_data) / 1024 / 1024:.1f} MB")
    print(f"{'='*70}")

    # Write audio data to temporary file
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(audio_data)
        audio_path = tmp.name

    # ========== STEP 1: Transcribe with WhisperX ==========
    print("\n🎙️  Step 1/2: Transcribing with WhisperX...")

    try:
        # Load audio
        audio = whisperx.load_audio(audio_path)

        # Device selection (CUDA on Modal's A10G GPU)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        print(f"   Device: {device} (compute_type: {compute_type})")

        # Transcribe
        print("   Loading Whisper model (large-v3)...")
        model = whisperx.load_model("large-v3", device=device, compute_type=compute_type)

        print("   Transcribing...")
        result = model.transcribe(audio, batch_size=16)  # Larger batch on GPU

        print(f"   ✅ Transcription complete ({result['language']})")

        # Align timestamps
        print("   Aligning word-level timestamps...")
        model_a, metadata = whisperx.load_align_model(
            language_code=result["language"],
            device=device
        )
        result = whisperx.align(
            result["segments"],
            model_a,
            metadata,
            audio,
            device,
            return_char_alignments=False
        )

        print("   ✅ Alignment complete")

    except Exception as e:
        return {"error": f"Transcription failed: {e}", "video_id": video_id}

    # ========== STEP 2: Speaker Diarization ==========
    print("\n👥 Step 2/2: Running speaker diarization...")

    try:
        # Load pyannote diarization pipeline
        diarize_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )

        # Run diarization on audio file
        print("   Processing speaker segments...")
        diarize_segments = diarize_pipeline(audio_path)

        # Assign speakers to transcript words
        print("   Assigning speakers to transcript...")
        result = whisperx.assign_word_speakers(diarize_segments, result)

        # Convert to utterances format
        utterances = []
        speakers_seen = set()

        for segment in result["segments"]:
            speaker = segment.get("speaker", "UNKNOWN")
            speakers_seen.add(speaker)

            utterances.append({
                'speaker': speaker,
                'text': segment["text"].strip(),
                'start': int(segment["start"] * 1000),  # milliseconds
                'end': int(segment["end"] * 1000),
            })

        print(f"   ✅ Diarization complete: {len(speakers_seen)} speakers, {len(utterances)} utterances")

    except Exception as e:
        return {"error": f"Diarization failed: {e}", "video_id": video_id}

    # Build result
    result_data = {
        "video_id": video_id,
        "speakers_count": len(speakers_seen),
        "utterances_count": len(utterances),
        "utterances": utterances,
        "language": result["language"],
        "processed_at": datetime.now().isoformat(),
        "processing_device": "modal-a10g-cuda",
    }

    print(f"\n{'='*70}")
    print(f"✅ COMPLETE: {video_id}")
    print(f"   Speakers: {len(speakers_seen)} | Utterances: {len(utterances)}")
    print(f"{'='*70}\n")

    return result_data


@app.function(timeout=7200)  # 2 hour timeout for batch
def process_batch_files(audio_files: list) -> list:
    """
    Process multiple audio files in parallel.

    Args:
        audio_files: List of dicts with 'audio_data' (bytes) and 'video_id' (str)
    """

    print(f"\n{'='*70}")
    print(f"🚀 BATCH PROCESSING: {len(audio_files)} files")
    print(f"   Parallelism: Up to 10x A10G GPUs")
    print(f"   Est. cost: ${len(audio_files) * 0.22:.2f}")
    print(f"   Est. time: {(len(audio_files) * 12) // 10} min (with 10x parallel)")
    print(f"{'='*70}\n")

    # Process in parallel using starmap
    results = list(process_audio_file.starmap(
        [(f['audio_data'], f['video_id']) for f in audio_files]
    ))

    # Summary
    success = sum(1 for r in results if "error" not in r)
    print(f"\n{'='*70}")
    print(f"📊 BATCH COMPLETE: {success}/{len(results)} successful")
    print(f"{'='*70}\n")

    return results


# ========== Local Entrypoints ==========

@app.local_entrypoint()
def process_single(audio_file: str):
    """
    Process a single audio file.

    Usage:
        modal run scripts/modal_process_audio.py::process_single --audio-file data/youtube_audio/rbbh5eOeOtM.mp3
    """
    import os.path
    import sys

    print("📤 Local entrypoint started...")
    sys.stdout.flush()

    if not os.path.exists(audio_file):
        print(f"❌ Error: File not found: {audio_file}")
        return

    video_id = Path(audio_file).stem

    print(f"📤 Uploading audio file to Modal...")
    print(f"   File: {audio_file}")
    sys.stdout.flush()

    # Read audio file
    print("   Reading file into memory...")
    sys.stdout.flush()
    with open(audio_file, "rb") as f:
        audio_data = f.read()

    print(f"   Size: {len(audio_data) / 1024 / 1024:.1f} MB")
    print(f"   Starting GPU processing...")
    sys.stdout.flush()

    # Process on Modal GPU
    result = process_audio_file.remote(audio_data, video_id)

    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    # Save result locally
    output_file = f"data/testimony/testimony_{result['video_id']}.json"
    os.makedirs("data/testimony", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✅ Saved to: {output_file}")
    print(f"   Speakers: {result.get('speakers_count', 0)}")
    print(f"   Utterances: {result.get('utterances_count', 0)}")


@app.local_entrypoint()
def process_batch(audio_dir: str = "data/youtube_audio"):
    """
    Process all audio files in a directory.

    Usage:
        modal run scripts/modal_process_audio.py::process_batch --audio-dir data/youtube_audio
    """
    import glob

    # Find all audio files
    audio_files = glob.glob(os.path.join(audio_dir, "*.mp3"))

    if not audio_files:
        print(f"❌ No audio files found in {audio_dir}")
        return

    print(f"✅ Found {len(audio_files)} audio files")
    print(f"📤 Reading audio files...")

    # Read all audio files into memory
    files_to_process = []
    for audio_file in audio_files:
        video_id = Path(audio_file).stem
        with open(audio_file, "rb") as f:
            audio_data = f.read()
        files_to_process.append({
            "audio_data": audio_data,
            "video_id": video_id
        })
        print(f"   {video_id}: {len(audio_data) / 1024 / 1024:.1f} MB")

    print(f"\n🚀 Starting batch processing on Modal...")

    # Process on Modal
    results = process_batch_files.remote(files_to_process)

    # Save results locally
    output_dir = "data/testimony"
    os.makedirs(output_dir, exist_ok=True)

    for result in results:
        if "error" not in result:
            output_file = f"{output_dir}/testimony_{result['video_id']}.json"
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2)
            print(f"✅ Saved: {output_file}")
        else:
            print(f"❌ Error: {result.get('video_id', 'unknown')} - {result['error']}")

    # Final summary
    success_count = sum(1 for r in results if "error" not in r)
    print(f"\n📊 Final: {success_count}/{len(results)} successful, saved to {output_dir}/")
