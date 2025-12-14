#!/usr/bin/env python3
"""Quick test to check AssemblyAI duration field."""

import os
import assemblyai as aai
from dotenv import load_dotenv

load_dotenv()
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Get the existing transcript
transcript = aai.Transcript.get_by_id("7d4fc04d-3489-40d9-8bbe-c83886ba2d7e")

print(f"audio_duration field: {transcript.audio_duration}")
print(f"audio_duration type: {type(transcript.audio_duration)}")

if transcript.utterances:
    last_utt = transcript.utterances[-1]
    print(f"\nLast utterance end time: {last_utt.end} ms")
    print(f"Expected duration: {last_utt.end / 60000:.2f} minutes")
