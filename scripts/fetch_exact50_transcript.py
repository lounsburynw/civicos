#!/usr/bin/env python3
import os
import sys
import json

# Set working directory to project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
import assemblyai as aai

# Load environment
load_dotenv()

# Configure API
api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not api_key:
    print("Error: ASSEMBLYAI_API_KEY not found in environment")
    sys.exit(1)

aai.settings.api_key = api_key

# Fetch transcript
transcript_id = "31f6f930-a768-4a85-8649-43f5823e156a"
print(f"Fetching transcript: {transcript_id}")

transcript = aai.Transcript.get_by_id(transcript_id)

print(f"Status: {transcript.status}")
print(f"Speakers detected: {len(set(u.speaker for u in transcript.utterances if u.speaker))}")

# Convert to JSON format
result = {
    "id": transcript.id,
    "status": str(transcript.status),
    "text": transcript.text,
    "utterances": [
        {
            "text": u.text,
            "start": u.start,
            "end": u.end,
            "confidence": u.confidence,
            "speaker": u.speaker
        }
        for u in transcript.utterances
    ],
    "speakers_expected": {"min": 50, "max": 50}
}

# Save
output_path = "data/testimony/testimony_MpxrGRb16HQ_exact50.json"
with open(output_path, 'w') as f:
    json.dump(result, f, indent=2)

print(f"\n✅ Saved to: {output_path}")
print(f"Total utterances: {len(result['utterances'])}")

# Quick stats
speakers = sorted(set(u['speaker'] for u in result['utterances'] if u['speaker']))
print(f"Unique speakers: {len(speakers)}")
print(f"Speaker labels: {', '.join(speakers)}")
