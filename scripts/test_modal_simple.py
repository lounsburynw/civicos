#!/usr/bin/env python3
"""
Simple Modal test - just process the already-downloaded compressed audio.

Usage:
    modal run scripts/test_modal_simple.py
"""

import modal
import os
import json
from datetime import datetime
from typing import Dict

# Modal app configuration
app = modal.App("civic-testimony-test")

# Define Modal image with all dependencies
# Use torch 2.0.0 for better compatibility with pyannote
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "git")
    .pip_install(
        "torch==2.0.0",
        "torchaudio==2.0.0",
        "pyannote.audio==3.1.1",  # Specific version for torch 2.0 compatibility
    )
    .run_commands("pip install git+https://github.com/m-bain/whisperx.git")
)


@app.function(
    image=image,
    gpu="A10G",
    timeout=1800,
    secrets=[modal.Secret.from_name("huggingface")],
)
def process_audio(audio_data: bytes, video_id: str) -> Dict:
    """Process audio with WhisperX + diarization."""
    import whisperx
    import torch
    from pyannote.audio import Pipeline
    import time

    # Fix PyTorch 2.6+ security restriction for pyannote models
    # Monkey-patch torch.load to use weights_only=False (old behavior)
    # This is safe for trusted HuggingFace models
    import functools
    original_torch_load = torch.load

    @functools.wraps(original_torch_load)
    def patched_torch_load(*args, **kwargs):
        # Force weights_only=False to allow loading pyannote models
        kwargs['weights_only'] = False
        return original_torch_load(*args, **kwargs)

    torch.load = patched_torch_load
    print("   Patched torch.load to allow pyannote model loading")

    start_time = time.time()

    hf_token = os.environ["HF_TOKEN"]

    print(f"\n{'='*70}")
    print(f"🎬 Processing: {video_id}")
    print(f"   Audio size: {len(audio_data) / (1024*1024):.1f} MB")
    print(f"{'='*70}")

    # Write audio to temp file
    audio_path = f"/tmp/{video_id}.mp3"
    with open(audio_path, 'wb') as f:
        f.write(audio_data)

    # Load audio
    print("\n🎙️  Loading audio...")
    audio = whisperx.load_audio(audio_path)

    # Device selection
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"   Device: {device}")

    # Transcribe
    print("\n📝 Transcribing with Whisper large-v3...")
    model = whisperx.load_model("large-v3", device=device, compute_type=compute_type)
    result = model.transcribe(audio, batch_size=16)
    print(f"   ✅ Transcription complete ({result['language']})")

    # Align timestamps
    print("\n⏰ Aligning timestamps...")
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

    # Diarization
    print("\n👥 Running speaker diarization...")
    diarize_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token
    )
    diarize_segments = diarize_pipeline(audio_path)
    result = whisperx.assign_word_speakers(diarize_segments, result)

    # Build utterances
    utterances = []
    speakers_seen = set()

    for segment in result["segments"]:
        speaker = segment.get("speaker", "UNKNOWN")
        speakers_seen.add(speaker)

        utterances.append({
            'speaker': speaker,
            'text': segment["text"].strip(),
            'start': int(segment["start"] * 1000),
            'end': int(segment["end"] * 1000),
        })

    duration_mins = int(len(audio) / 16000 // 60)
    processing_time = time.time() - start_time

    print(f"\n✅ Complete!")
    print(f"   Speakers: {len(speakers_seen)}")
    print(f"   Utterances: {len(utterances)}")
    print(f"   Duration: {duration_mins} min")
    print(f"   Processing time: {processing_time:.1f}s")

    # Cleanup
    try:
        os.unlink(audio_path)
    except:
        pass

    return {
        "video_id": video_id,
        "speakers_count": len(speakers_seen),
        "utterances_count": len(utterances),
        "utterances": utterances,
        "audio_duration_minutes": duration_mins,
        "processing_time_seconds": processing_time,
        "language": result["language"],
        "processed_at": datetime.now().isoformat(),
    }


@app.local_entrypoint()
def main():
    """Test with the already-downloaded compressed audio."""
    import time

    video_id = "MpxrGRb16HQ"
    audio_file = f"data/test_bottleneck/{video_id}_compressed.mp3"

    if not os.path.exists(audio_file):
        print(f"❌ Audio file not found: {audio_file}")
        print(f"   Run the download test first:")
        print(f"   python scripts/test_hybrid_bottleneck.py --url <meeting-url>")
        return

    print(f"\n{'='*70}")
    print(f"🚀 MODAL GPU PROCESSING TEST")
    print(f"{'='*70}")
    print(f"   Video ID: {video_id}")
    print(f"   Audio file: {audio_file}")
    print(f"   Size: {os.path.getsize(audio_file) / (1024*1024):.1f} MB")
    print(f"{'='*70}\n")

    # Read audio data
    with open(audio_file, 'rb') as f:
        audio_data = f.read()

    print(f"📤 Uploading {len(audio_data) / (1024*1024):.1f} MB to Modal...")
    upload_start = time.time()

    # Process on Modal
    result = process_audio.remote(audio_data, video_id)

    total_time = time.time() - upload_start

    print(f"\n{'='*70}")
    print(f"📊 RESULTS")
    print(f"{'='*70}")
    print(f"   Total time (upload + processing): {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"   Processing time (GPU only): {result['processing_time_seconds']:.1f}s")
    print(f"   Upload time (estimated): {total_time - result['processing_time_seconds']:.1f}s")
    print(f"   Speakers detected: {result['speakers_count']}")
    print(f"   Utterances: {result['utterances_count']}")
    print(f"   Audio duration: {result['audio_duration_minutes']} minutes")
    print(f"{'='*70}\n")

    # Save result
    output_file = f"data/test_bottleneck/modal_result_{video_id}.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"✅ Full results saved to: {output_file}")
