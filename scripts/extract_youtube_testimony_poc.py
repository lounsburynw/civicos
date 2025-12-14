#!/usr/bin/env python3
"""
YouTube Testimony Extraction - Proof of Concept

Tests the full pipeline on a single San Rafael meeting:
1. Extract YouTube video ID from meeting page
2. Download audio with yt-dlp
3. Transcribe with AssemblyAI (speaker diarization)
4. Extract testimony structure with LLM
5. Display results (no database insert for POC)

Usage:
    python scripts/extract_youtube_testimony_poc.py \
        "https://www.cityofsanrafael.org/meetings/city-council-october-6-2024/"
"""

import sys
import os
import json
import argparse
import tempfile
import re
from typing import Dict, List, Optional
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import requests
from bs4 import BeautifulSoup


def extract_youtube_video_id(meeting_url: str) -> Optional[str]:
    """
    Extract YouTube video ID from San Rafael meeting page

    Args:
        meeting_url: San Rafael meeting page URL

    Returns:
        YouTube video ID or None
    """
    print(f"🔍 Extracting video ID from {meeting_url}")

    try:
        response = requests.get(meeting_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Method 1: Look for YouTube iframe embed
        iframe = soup.find('iframe', src=re.compile(r'youtube\.com/embed/'))
        if iframe:
            src = iframe['src']
            video_id = src.split('/')[-1].split('?')[0]
            print(f"✅ Found video ID via iframe: {video_id}")
            return video_id

        # Method 2: Look for YouTube player div (data attribute)
        player_div = soup.find('div', {'data-video-id': True})
        if player_div:
            video_id = player_div['data-video-id']
            print(f"✅ Found video ID via data attribute: {video_id}")
            return video_id

        # Method 3: Look in page source for YouTube links
        youtube_pattern = r'youtube\.com/(?:watch\?v=|embed/)([a-zA-Z0-9_-]+)'
        match = re.search(youtube_pattern, response.text)
        if match:
            video_id = match.group(1)
            print(f"✅ Found video ID via regex: {video_id}")
            return video_id

        print("❌ No YouTube video found on page")
        return None

    except Exception as e:
        print(f"❌ Error extracting video ID: {e}")
        return None


def download_youtube_audio(video_id: str, output_dir: str = None) -> Optional[str]:
    """
    Download YouTube video audio as MP3

    Args:
        video_id: YouTube video ID
        output_dir: Directory for output (defaults to temp)

    Returns:
        Path to downloaded MP3 file or None
    """
    print(f"\n📥 Downloading audio for video {video_id}...")

    try:
        import yt_dlp
    except ImportError:
        print("❌ yt-dlp not installed. Run: pip install yt-dlp")
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"

    # Create output path
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    output_path = os.path.join(output_dir, f"{video_id}.mp3")

    # Check if already downloaded
    if os.path.exists(output_path):
        print(f"✅ Audio already exists: {output_path}")
        return output_path

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',  # Lower quality = faster upload to AssemblyAI
        }],
        'outtmpl': output_path.replace('.mp3', ''),
        'quiet': False,
        'no_warnings': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            duration_mins = info.get('duration', 0) // 60

        print(f"✅ Downloaded audio: {output_path}")
        print(f"   Duration: {duration_mins} minutes")
        print(f"   Size: {os.path.getsize(output_path) / (1024*1024):.1f} MB")

        return output_path

    except Exception as e:
        print(f"❌ Download failed: {e}")
        return None


def transcribe_with_whisperx(audio_path: str, hf_token: str, device: str = "cpu") -> Optional[Dict]:
    """
    Transcribe audio with WhisperX (Whisper + speaker diarization)

    Args:
        audio_path: Path to MP3 file
        hf_token: Hugging Face token (for pyannote diarization models)
        device: Device to use (cpu, cuda, mps for Apple Silicon)

    Returns:
        Transcript data with utterances or None
    """
    print(f"\n🎙️  Transcribing with WhisperX (local, free!)...")
    print(f"   Audio file: {audio_path}")

    try:
        import whisperx
        import torch
        from pyannote.audio import Pipeline
    except ImportError as e:
        print(f"❌ Required package not installed: {e}")
        print("   Run: pip install whisperx pyannote-audio")
        return None

    # Auto-detect device for MLX backend
    # whisperx-mlx supports full MPS acceleration for both transcription and diarization
    if device == "cpu" and torch.cuda.is_available():
        device = "cuda"
        print("   Device: CUDA GPU")
    elif device == "cpu" and torch.backends.mps.is_available():
        # MLX backend fully supports Apple Silicon MPS
        device = "mps"
        print("   Device: Apple Silicon GPU (MPS) with MLX backend")
    else:
        device = "cpu"
        print("   Device: CPU")

    try:
        # Step 1: Transcribe with Whisper using MLX backend
        print("   Loading Whisper model (large-v3) with MLX backend...")
        model = whisperx.load_model("large-v3", backend="mlx", device=device)

        print("   Transcribing audio...")
        audio = whisperx.load_audio(audio_path)
        result = model.transcribe(audio, batch_size=8)  # MLX-optimized batch size

        print(f"   ✓ Transcription complete")

        # Step 2: Align timestamps
        # Note: wav2vec2 alignment doesn't support MPS with >65K channels, use CPU
        align_device = "cpu" if device == "mps" else device
        print(f"   Aligning word-level timestamps (device: {align_device})...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=align_device)
        result = whisperx.align(result["segments"], model_a, metadata, audio, align_device, return_char_alignments=False)

        print(f"   ✓ Alignment complete")

        # Step 3: Speaker diarization
        # Note: Use pyannote.audio directly (whisperx-mlx doesn't expose DiarizationPipeline)
        # Use CPU for diarization to avoid potential MPS compatibility issues
        print("   Running speaker diarization (using pyannote.audio)...")
        diarize_device = "cpu" if device == "mps" else device
        print(f"   Diarization device: {diarize_device}")

        diarize_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )

        # pyannote expects file path, not audio array
        diarize_segments = diarize_pipeline(audio_path)

        print(f"   ✓ Diarization complete")

        # Step 4: Assign speakers to words
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
                'start': int(segment["start"] * 1000),  # Convert to milliseconds
                'end': int(segment["end"] * 1000),
                'confidence': 1.0  # WhisperX doesn't provide confidence per utterance
            })

        # Calculate total duration
        audio_duration = int(result["segments"][-1]["end"] * 1000) if result["segments"] else 0

        print(f"✅ Transcription complete!")
        print(f"   Total utterances: {len(utterances)}")
        print(f"   Unique speakers: {len(speakers_seen)}")
        print(f"   Duration: {audio_duration / 1000 / 60:.1f} minutes")

        return {
            'transcript_id': f'whisperx_{os.path.basename(audio_path)}',
            'utterances': utterances,
            'speakers_count': len(speakers_seen),
            'audio_duration': audio_duration,
            'method': 'whisperx'
        }

    except Exception as e:
        print(f"❌ Transcription error: {e}")
        import traceback
        traceback.print_exc()
        return None


def transcribe_with_assemblyai(audio_path: str, api_key: str) -> Optional[Dict]:
    """
    Transcribe audio with AssemblyAI speaker diarization (cloud fallback)

    Args:
        audio_path: Path to MP3 file
        api_key: AssemblyAI API key

    Returns:
        Transcript data with utterances or None
    """
    print(f"\n🎙️  Transcribing with AssemblyAI (cloud)...")
    print(f"   Audio file: {audio_path}")

    try:
        import assemblyai as aai
    except ImportError:
        print("❌ assemblyai not installed. Run: pip install assemblyai")
        return None

    aai.settings.api_key = api_key

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        speakers_expected=15,  # City Council meetings typically have 5-15 speakers
        language_code='en'
    )

    transcriber = aai.Transcriber()

    try:
        print("   Uploading audio file...")
        transcript = transcriber.transcribe(audio_path, config)

        print(f"   Transcription status: {transcript.status}")

        if transcript.status == aai.TranscriptStatus.error:
            print(f"❌ Transcription failed: {transcript.error}")
            return None

        # Extract utterances
        utterances = []
        speakers_seen = set()

        for utterance in transcript.utterances:
            utterances.append({
                'speaker': utterance.speaker,
                'text': utterance.text,
                'start': utterance.start,  # milliseconds
                'end': utterance.end,
                'confidence': utterance.confidence
            })
            speakers_seen.add(utterance.speaker)

        print(f"✅ Transcription complete!")
        print(f"   Total utterances: {len(utterances)}")
        print(f"   Unique speakers: {len(speakers_seen)}")
        print(f"   Duration: {transcript.audio_duration / 1000 / 60:.1f} minutes")

        return {
            'transcript_id': transcript.id,
            'utterances': utterances,
            'speakers_count': len(speakers_seen),
            'audio_duration': transcript.audio_duration,
            'method': 'assemblyai'
        }

    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return None


def extract_testimony_structure(
    utterances: List[Dict],
    meeting_date: str,
    meeting_title: str
) -> List[Dict]:
    """
    Use LLM to extract testimony structure from transcript

    Args:
        utterances: Raw transcript utterances
        meeting_date: ISO date
        meeting_title: Meeting title

    Returns:
        List of testimony records
    """
    print(f"\n🤖 Extracting testimony structure with LLM...")

    from llm_provider import get_model_for_task

    # Build transcript text with timestamps
    transcript_lines = []
    for u in utterances[:500]:  # Limit to first 500 utterances for POC
        minutes = u['start'] // 60000
        seconds = (u['start'] // 1000) % 60
        transcript_lines.append(
            f"[{minutes}:{seconds:02d}] Speaker {u['speaker']}: {u['text']}"
        )

    transcript_text = "\n".join(transcript_lines)

    prompt = f"""
You are analyzing a City Council meeting transcript to extract public testimony during the public comment period.

Meeting: {meeting_title}
Date: {meeting_date}

Transcript (with timestamps and speaker labels):
{transcript_text}

Task: Extract testimony records for each speaker who testified during public comment.

For each speaker who testifies, identify:
1. speaker_label: The speaker ID from transcript (e.g., "A", "B", "C")
2. speaker_name: Their name if they introduce themselves, otherwise "Speaker [label]"
3. topic: What they're speaking about
4. position: support/oppose/neutral/comment/question
5. organization: Organization they represent (if mentioned)
6. key_quote: One representative sentence (exact quote from transcript)
7. timestamp_start: Timestamp when they started speaking (format: MM:SS)

Focus on the PUBLIC COMMENT section. Ignore:
- Council members speaking
- Staff presentations
- Procedural discussions

Return a JSON array of testimony records. Only include actual public testimony.
"""

    try:
        model = get_model_for_task('agenda_parsing')

        print(f"   Using model: {model.name}")
        print(f"   Transcript length: {len(transcript_text)} chars")

        response = model.generate(
            prompt,
            temperature=0.3,
            max_tokens=4000
        )

        # Parse JSON response
        if isinstance(response, str):
            # Try to extract JSON from response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                testimony_records = json.loads(json_match.group(0))
            else:
                print(f"⚠️  Could not parse JSON from LLM response")
                return []
        else:
            testimony_records = response

        print(f"✅ Extracted {len(testimony_records)} testimony records")

        return testimony_records

    except Exception as e:
        print(f"❌ LLM extraction error: {e}")
        return []


def display_results(
    video_id: str,
    transcript_data: Dict,
    testimony_records: List[Dict]
):
    """
    Display extraction results

    Args:
        video_id: YouTube video ID
        transcript_data: Raw transcript data
        testimony_records: Extracted testimony
    """
    print("\n" + "=" * 70)
    print("📊 EXTRACTION RESULTS")
    print("=" * 70)

    print(f"\n🎥 Video: https://www.youtube.com/watch?v={video_id}")
    print(f"⏱️  Duration: {transcript_data['audio_duration'] / 1000 / 60:.1f} minutes")
    print(f"🗣️  Speakers detected: {transcript_data['speakers_count']}")
    print(f"💬 Utterances: {len(transcript_data['utterances'])}")

    print(f"\n📋 TESTIMONY EXTRACTED: {len(testimony_records)} speakers")
    print("-" * 70)

    if testimony_records:
        for i, record in enumerate(testimony_records, 1):
            print(f"\n{i}. {record.get('speaker_name', 'Unknown')}")
            print(f"   Label: Speaker {record.get('speaker_label', '?')}")
            print(f"   Topic: {record.get('topic', 'N/A')}")
            print(f"   Position: {record.get('position', 'N/A')}")
            if record.get('organization'):
                print(f"   Organization: {record['organization']}")
            if record.get('timestamp_start'):
                print(f"   Time: {record['timestamp_start']}")
            if record.get('key_quote'):
                quote = record['key_quote']
                if len(quote) > 100:
                    quote = quote[:97] + "..."
                print(f"   Quote: \"{quote}\"")
    else:
        print("⚠️  No testimony extracted (may need manual review)")


def main():
    parser = argparse.ArgumentParser(
        description='Extract testimony from San Rafael YouTube meeting video (POC)'
    )
    parser.add_argument('meeting_url', help='San Rafael meeting page URL')
    parser.add_argument('--method', choices=['whisperx', 'assemblyai', 'auto'], default='auto',
                        help='Transcription method (default: auto - tries WhisperX first)')
    parser.add_argument('--hf-token', help='Hugging Face token for WhisperX (or set HF_TOKEN env var)')
    parser.add_argument('--api-key', help='AssemblyAI API key (or set ASSEMBLYAI_API_KEY env var)')
    parser.add_argument('--output-dir', help='Directory for downloaded audio files')
    parser.add_argument('--device', default='cpu', choices=['cpu', 'cuda', 'mps'],
                        help='Device for WhisperX (auto-detects Apple Silicon)')
    parser.add_argument('--skip-download', action='store_true',
                        help='Skip download if audio already exists')

    args = parser.parse_args()

    print("🎬 YOUTUBE TESTIMONY EXTRACTION - POC")
    print("=" * 70)

    # Determine transcription method
    hf_token = args.hf_token or os.getenv('HF_TOKEN')
    assemblyai_key = args.api_key or os.getenv('ASSEMBLYAI_API_KEY')

    if args.method == 'auto':
        if hf_token:
            method = 'whisperx'
            print("\n📌 Using WhisperX (local, free) - HF token detected")
        elif assemblyai_key:
            method = 'assemblyai'
            print("\n📌 Using AssemblyAI (cloud) - API key detected")
        else:
            print("❌ No credentials found!")
            print("\nFor WhisperX (free, recommended):")
            print("  1. Get HF token: https://huggingface.co/settings/tokens")
            print("  2. Accept terms: pyannote/segmentation, pyannote/speaker-diarization-3.1")
            print("  3. Set: export HF_TOKEN=your_token")
            print("\nFor AssemblyAI (cloud, $50 free credits):")
            print("  1. Sign up: https://www.assemblyai.com/")
            print("  2. Set: export ASSEMBLYAI_API_KEY=your_key")
            return 1
    else:
        method = args.method
        if method == 'whisperx' and not hf_token:
            print("❌ WhisperX requires HF token!")
            print("Get token: https://huggingface.co/settings/tokens")
            return 1
        if method == 'assemblyai' and not assemblyai_key:
            print("❌ AssemblyAI requires API key!")
            print("Sign up: https://www.assemblyai.com/")
            return 1

    # Step 1: Extract video ID
    video_id = extract_youtube_video_id(args.meeting_url)
    if not video_id:
        return 1

    # Step 2: Download audio
    audio_path = download_youtube_audio(video_id, args.output_dir)
    if not audio_path:
        return 1

    # Step 3: Transcribe
    if method == 'whisperx':
        transcript_data = transcribe_with_whisperx(audio_path, hf_token, args.device)
    else:
        transcript_data = transcribe_with_assemblyai(audio_path, assemblyai_key)

    if not transcript_data:
        return 1

    # Step 4: Extract testimony structure
    # Parse meeting info from URL
    meeting_slug = args.meeting_url.rstrip('/').split('/')[-1]
    meeting_date = "2024-10-06"  # TODO: Parse from slug
    meeting_title = meeting_slug.replace('-', ' ').title()

    testimony_records = extract_testimony_structure(
        transcript_data['utterances'],
        meeting_date,
        meeting_title
    )

    # Step 5: Display results
    display_results(video_id, transcript_data, testimony_records)

    # Save results to JSON
    output_file = f"data/pilot/youtube_testimony_{video_id}.json"
    os.makedirs('data/pilot', exist_ok=True)

    results = {
        'video_id': video_id,
        'meeting_url': args.meeting_url,
        'meeting_date': meeting_date,
        'transcript_id': transcript_data['transcript_id'],
        'speakers_count': transcript_data['speakers_count'],
        'audio_duration_minutes': transcript_data['audio_duration'] / 1000 / 60,
        'testimony_records': testimony_records,
        'extracted_at': datetime.now().isoformat()
    }

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ POC COMPLETE!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
