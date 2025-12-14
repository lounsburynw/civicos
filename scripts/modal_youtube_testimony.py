#!/usr/bin/env python3
"""
Modal-based YouTube Testimony Extraction - Parallel Cloud Processing

Processes multiple San Rafael city council meetings in parallel on Modal's serverless GPUs.
Cost: ~$5.50 for 25 meetings (A10G GPUs)
Time: ~1 hour with 5x parallelism vs 7-10 hours local

Setup (one-time):
    pip install modal
    modal token new
    modal secret create huggingface HF_TOKEN=your_hf_token_here
    modal secret create youtube-cookies COOKIES_FILE="$(cat ~/Downloads/www.youtube.com_cookies.txt)"

Usage:
    # Test single meeting
    modal run scripts/modal_youtube_testimony.py::test_single

    # Run batch (25 meetings in parallel)
    modal run scripts/modal_youtube_testimony.py::run_batch --urls-file data/san_rafael_meetings.txt

    # Or provide URLs directly
    modal run scripts/modal_youtube_testimony.py::run_batch --urls url1 url2 url3
"""

import modal
import os
import json
import re
import tempfile
from typing import Dict, List, Optional
from datetime import datetime

# Modal app configuration
app = modal.App("civic-testimony-extraction")

# Define Modal image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "ffmpeg",  # Required for audio processing
        "git",     # Required for package installations
    )
    .pip_install(
        "yt-dlp",              # YouTube audio download
        "requests",            # HTTP requests
        "beautifulsoup4",      # HTML parsing
        "torch==2.4.0",        # PyTorch (CUDA-compatible)
        "torchaudio==2.4.0",   # Audio processing
        "pyannote.audio",      # Speaker diarization
        "openai>=1.0.0",       # LLM extraction (optional)
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
    secrets=[
        modal.Secret.from_name("huggingface"),
        modal.Secret.from_name("youtube-cookies"),
    ],
    retries=modal.Retries(
        max_retries=2,
        initial_delay=1.0,
        backoff_coefficient=2.0,
    ),
)
def extract_testimony(meeting_url: str) -> Dict:
    """
    Extract testimony from a single San Rafael city council meeting.

    This function runs on Modal's A10G GPU and processes:
    1. Video ID extraction from meeting page
    2. Audio download with yt-dlp
    3. Transcription with WhisperX (GPU-accelerated)
    4. Speaker diarization with pyannote.audio
    5. Returns structured testimony data

    Args:
        meeting_url: San Rafael meeting page URL (e.g., "https://www.cityofsanrafael.org/meetings/...")

    Returns:
        Dictionary with video_id, speakers_count, utterances, duration, etc.
        On error, returns {"error": "message", "meeting_url": url}
    """
    import requests
    from bs4 import BeautifulSoup
    import yt_dlp
    import whisperx
    import torch
    from pyannote.audio import Pipeline

    hf_token = os.environ["HF_TOKEN"]

    print(f"\n{'='*70}")
    print(f"🎬 Processing: {meeting_url}")
    print(f"{'='*70}")

    # ========== STEP 1: Extract YouTube Video ID ==========
    print("\n🔍 Step 1/4: Extracting video ID...")
    try:
        response = requests.get(meeting_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Try iframe embed
        iframe = soup.find('iframe', src=re.compile(r'youtube\.com/embed/'))
        if iframe:
            video_id = iframe['src'].split('/')[-1].split('?')[0]
        else:
            # Try regex in page source
            youtube_pattern = r'youtube\.com/(?:watch\?v=|embed/)([a-zA-Z0-9_-]+)'
            match = re.search(youtube_pattern, response.text)
            if match:
                video_id = match.group(1)
            else:
                return {"error": "No YouTube video found", "meeting_url": meeting_url}

        print(f"   ✅ Found video ID: {video_id}")

    except Exception as e:
        return {"error": f"Failed to extract video ID: {e}", "meeting_url": meeting_url}

    # ========== STEP 2: Download Audio ==========
    print("\n📥 Step 2/4: Downloading audio...")
    audio_path = f"/tmp/{video_id}.mp3"

    try:
        # Write cookies to temporary file if available
        cookies_content = os.environ.get("COOKIES_FILE")
        cookies_path = None

        if cookies_content:
            cookies_path = "/tmp/youtube_cookies.txt"
            with open(cookies_path, "w") as f:
                f.write(cookies_content)
            print(f"   🔑 Using YouTube cookies for authentication")
        else:
            print(f"   ⚠️  No cookies found - may hit bot detection")

        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'outtmpl': audio_path.replace('.mp3', ''),
            'quiet': True,
            'no_warnings': True,
        }

        # Add cookies if available
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            duration_mins = info.get('duration', 0) // 60

        file_size_mb = os.path.getsize(audio_path) / (1024*1024)
        print(f"   ✅ Downloaded: {duration_mins} min, {file_size_mb:.1f} MB")

    except Exception as e:
        return {"error": f"Audio download failed: {e}", "video_id": video_id}

    # ========== STEP 3: Transcribe with WhisperX ==========
    print("\n🎙️  Step 3/4: Transcribing with WhisperX...")

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

    # ========== STEP 4: Speaker Diarization ==========
    print("\n👥 Step 4/4: Running speaker diarization...")

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

    # ========== Cleanup and Return ==========
    try:
        os.unlink(audio_path)
    except:
        pass

    # Build result
    result_data = {
        "video_id": video_id,
        "meeting_url": meeting_url,
        "speakers_count": len(speakers_seen),
        "utterances_count": len(utterances),
        "utterances": utterances,
        "audio_duration_minutes": duration_mins,
        "language": result["language"],
        "processed_at": datetime.now().isoformat(),
        "processing_device": "modal-a10g-cuda",
    }

    print(f"\n{'='*70}")
    print(f"✅ COMPLETE: {video_id}")
    print(f"   Speakers: {len(speakers_seen)} | Utterances: {len(utterances)} | Duration: {duration_mins} min")
    print(f"{'='*70}\n")

    return result_data


@app.function(
    image=image,
    gpu="A10G",  # Fast, cost-effective
    timeout=1800,  # 30 min max
    secrets=[modal.Secret.from_name("huggingface")],
    retries=modal.Retries(
        max_retries=2,
        initial_delay=1.0,
        backoff_coefficient=2.0,
    ),
)
def extract_testimony_from_file(audio_data: bytes, video_id: str, meeting_url: str = None) -> Dict:
    """
    Extract testimony from pre-downloaded audio file.

    This function accepts audio data directly (for hybrid local→Modal workflow)
    instead of downloading from YouTube. Useful for:
    - Avoiding YouTube's cloud IP blocking
    - Testing with local files
    - Batch processing with pre-downloaded audio

    Args:
        audio_data: Audio file bytes (MP3 format)
        video_id: YouTube video ID (for naming/tracking)
        meeting_url: Optional meeting URL for metadata

    Returns:
        Dictionary with video_id, speakers_count, utterances, duration, etc.
    """
    import whisperx
    import torch
    from pyannote.audio import Pipeline

    hf_token = os.environ["HF_TOKEN"]

    print(f"\n{'='*70}")
    print(f"🎬 Processing uploaded audio: {video_id}")
    print(f"{'='*70}")

    # Write audio data to temporary file
    audio_path = f"/tmp/{video_id}.mp3"
    with open(audio_path, 'wb') as f:
        f.write(audio_data)

    file_size_mb = len(audio_data) / (1024*1024)
    print(f"\n📥 Received audio: {file_size_mb:.1f} MB")

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

        # Calculate duration from audio
        duration_secs = len(audio) / 16000  # WhisperX uses 16kHz
        duration_mins = int(duration_secs // 60)

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

    # ========== Cleanup and Return ==========
    try:
        os.unlink(audio_path)
    except:
        pass

    # Build result
    result_data = {
        "video_id": video_id,
        "meeting_url": meeting_url,
        "speakers_count": len(speakers_seen),
        "utterances_count": len(utterances),
        "utterances": utterances,
        "audio_duration_minutes": duration_mins,
        "language": result["language"],
        "processed_at": datetime.now().isoformat(),
        "processing_device": "modal-a10g-cuda",
        "workflow": "hybrid-upload",
    }

    print(f"\n{'='*70}")
    print(f"✅ COMPLETE: {video_id}")
    print(f"   Speakers: {len(speakers_seen)} | Utterances: {len(utterances)} | Duration: {duration_mins} min")
    print(f"{'='*70}\n")

    return result_data


# LLM extraction function removed - do post-processing locally instead
# This keeps Modal costs low and allows iteration on LLM prompts without re-transcribing


@app.function(
    image=image,
    timeout=300,
)
def extract_testimony_structure_DEPRECATED(transcript_data: Dict) -> Dict:
    """
    Extract structured testimony from diarized transcript using LLM.

    Takes raw speaker labels (A, B, C) and extracts:
    - Speaker names (if mentioned)
    - Organizations represented
    - Positions (support/oppose/neutral)
    - Key quotes
    - Topics discussed

    Args:
        transcript_data: Output from extract_testimony (raw diarized transcript)

    Returns:
        Enriched testimony data with structured records
    """
    import json
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    print("\n🤖 Extracting testimony structure with LLM...")

    # Build prompt from utterances
    utterances = transcript_data.get("utterances", [])
    if not utterances:
        return transcript_data  # No utterances to process

    # Group by speaker for context
    speakers = {}
    for utt in utterances:
        speaker = utt["speaker"]
        if speaker not in speakers:
            speakers[speaker] = []
        speakers[speaker].append(utt["text"])

    # Create transcript text for LLM
    transcript_text = ""
    for speaker, texts in speakers.items():
        full_text = " ".join(texts)
        transcript_text += f"\n{speaker}: {full_text[:500]}..."  # Limit per speaker

    # LLM prompt for extraction
    prompt = f"""Extract structured testimony from this city council meeting transcript.

For each speaker, identify:
1. Speaker name (if mentioned or inferable)
2. Organization (if mentioned)
3. Position (support/oppose/neutral/unclear) on the main topic
4. Key quote (most impactful statement)
5. Main topic they're addressing

Transcript:
{transcript_text[:4000]}  # Limit total context

Return JSON array of testimony records. Example format:
[
  {{
    "speaker_label": "SPEAKER_0",
    "speaker_name": "Jane Smith" or null,
    "organization": "Marin Conservation League" or null,
    "position": "support|oppose|neutral|unclear",
    "topic": "wildfire prevention funding",
    "key_quote": "I strongly support...",
    "confidence": "high|medium|low"
  }}
]

Return ONLY valid JSON, no explanation."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cheap
            messages=[
                {"role": "system", "content": "You are a city council testimony analyzer. Extract structured data from transcripts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        # Parse LLM response
        content = response.choices[0].message.content.strip()

        # Handle markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        testimony_records = json.loads(content)

        print(f"   ✅ Extracted {len(testimony_records)} testimony records")

        # Add to result
        transcript_data["testimony_records"] = testimony_records
        transcript_data["llm_processed"] = True
        transcript_data["llm_model"] = "gpt-4o-mini"

        return transcript_data

    except Exception as e:
        print(f"   ⚠️  LLM extraction failed: {e}")
        print(f"   Returning raw transcript without structure")
        transcript_data["llm_processed"] = False
        transcript_data["llm_error"] = str(e)
        return transcript_data


@app.function(timeout=3600)
def process_batch(meeting_urls: List[str], max_parallel: int = 5) -> List[Dict]:
    """
    Process multiple meetings in parallel.

    Args:
        meeting_urls: List of San Rafael meeting page URLs
        max_parallel: Maximum parallel GPU workers (default 5 = $5.50/hour)

    Returns:
        List of testimony data dictionaries
    """
    print(f"\n{'='*70}")
    print(f"🚀 BATCH PROCESSING: {len(meeting_urls)} meetings")
    print(f"   Parallelism: {max_parallel}x A10G GPUs")
    print(f"   Est. cost: ${len(meeting_urls) * 0.22:.2f}")
    print(f"   Est. time: {(len(meeting_urls) * 12) // max_parallel} min")
    print(f"{'='*70}\n")

    # Modal's .map() automatically parallelizes across multiple GPUs
    # starmap for better progress tracking
    results = list(extract_testimony.starmap([(url,) for url in meeting_urls]))

    # Summary
    success = sum(1 for r in results if "error" not in r)
    print(f"\n{'='*70}")
    print(f"📊 BATCH COMPLETE: {success}/{len(results)} successful")
    print(f"{'='*70}\n")

    return results


# ========== Local Entrypoints ==========

@app.local_entrypoint()
def test_single():
    """
    Test with a single meeting (March 3, 2025 meeting)

    Usage:
        modal run scripts/modal_youtube_testimony.py::test_single
    """
    test_url = "https://www.cityofsanrafael.org/meetings/city-council-march-03-2025/"

    print("Testing single meeting extraction...")
    result = extract_testimony.remote(test_url)

    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    # Save result locally
    output_file = f"data/testimony/testimony_{result['video_id']}.json"
    os.makedirs("data/testimony", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    # Summary
    print(f"\n✅ Saved to: {output_file}")
    print(f"   Speakers: {result.get('speakers_count', 0)}")
    print(f"   Utterances: {result.get('utterances_count', 0)}")
    print(f"   Duration: {result.get('audio_duration_minutes', 0)} min")


@app.local_entrypoint()
def run_batch(urls_file: str = None, urls: List[str] = None):
    """
    Run batch processing of multiple meetings.

    Usage:
        # From file
        modal run scripts/modal_youtube_testimony.py::run_batch --urls-file data/san_rafael_meetings.txt

        # Direct URLs
        modal run scripts/modal_youtube_testimony.py::run_batch --urls url1 url2 url3
    """
    # Load URLs
    if urls_file:
        with open(urls_file) as f:
            meeting_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    elif urls:
        meeting_urls = urls
    else:
        print("❌ Must provide either --urls-file or --urls")
        return

    print(f"Processing {len(meeting_urls)} meetings...")

    # Run batch on Modal
    results = process_batch.remote(meeting_urls)

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
            print(f"❌ Error: {result.get('meeting_url', 'unknown')} - {result['error']}")

    # Final summary
    success_count = sum(1 for r in results if "error" not in r)
    print(f"\n📊 Final: {success_count}/{len(results)} successful, saved to {output_dir}/")
