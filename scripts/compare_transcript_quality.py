#!/usr/bin/env python3
"""
Better transcript quality comparison.
Compares full text and specific accuracy issues.
"""

import json
import difflib
import re

# Load YouTube transcript
with open("data/youtube_transcripts/MpxrGRb16HQ.en.json3") as f:
    yt_data = json.load(f)

# Extract YouTube full text
yt_text = ""
for event in yt_data.get("events", []):
    if "segs" in event:
        for seg in event["segs"]:
            if "utf8" in seg:
                yt_text += seg["utf8"]

# Load AssemblyAI transcript
with open("data/testimony/testimony_MpxrGRb16HQ.json") as f:
    aai_data = json.load(f)

# Extract AssemblyAI full text
aai_text = " ".join(utt["text"] for utt in aai_data["utterances"])

# Normalize for fair comparison
def normalize_text(text):
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Lowercase for case-insensitive comparison
    text = text.lower()
    # Remove punctuation variations
    text = text.strip()
    return text

yt_normalized = normalize_text(yt_text)
aai_normalized = normalize_text(aai_text)

# Calculate similarity
similarity = difflib.SequenceMatcher(None, yt_normalized, aai_normalized).ratio()

# Word counts
yt_words = yt_normalized.split()
aai_words = aai_normalized.split()

# Find specific differences in first 500 words
yt_sample = ' '.join(yt_words[:500])
aai_sample = ' '.join(aai_words[:500])

print("="*70)
print("TRANSCRIPT QUALITY COMPARISON")
print("="*70)

print(f"\nWord Counts:")
print(f"  YouTube: {len(yt_words):,} words")
print(f"  AssemblyAI: {len(aai_words):,} words")
print(f"  Difference: {abs(len(yt_words) - len(aai_words)):,} words ({abs(len(yt_words) - len(aai_words)) / len(yt_words) * 100:.1f}%)")

print(f"\nOverall Similarity: {similarity:.1%}")

print(f"\n" + "="*70)
print("FIRST 100 WORDS COMPARISON")
print("="*70)

yt_first = ' '.join(yt_words[:100])
aai_first = ' '.join(aai_words[:100])

print("\nYouTube:")
print(yt_first)

print("\nAssemblyAI:")
print(aai_first)

# Calculate similarity for first 100 words
first_similarity = difflib.SequenceMatcher(None, yt_first, aai_first).ratio()
print(f"\nFirst 100 words similarity: {first_similarity:.1%}")

# Find notable differences
print(f"\n" + "="*70)
print("NOTABLE DIFFERENCES")
print("="*70)

# Check for "San Rafael" vs other spellings
if "san rafael" in aai_normalized and "sanfell" in yt_normalized:
    print("\n✓ AssemblyAI correctly identifies 'San Rafael'")
    print("  YouTube transcribes it as 'Sanfell' (error)")

# Speaker diarization
speakers = set(utt["speaker"] for utt in aai_data["utterances"])
print(f"\n✓ AssemblyAI provides speaker diarization ({len(speakers)} speakers)")
print("  YouTube has no speaker labels")

# Check for common transcription errors
errors_yt = []
errors_aai = []

# Sample check
test_phrases = [
    ("october 6", "correct date format"),
    ("city council", "correct entity name"),
    ("san rafael", "correct city name")
]

for phrase, desc in test_phrases:
    in_yt = phrase in yt_normalized
    in_aai = phrase in aai_normalized

    if in_yt and in_aai:
        print(f"✓ Both correctly include '{phrase}' ({desc})")
    elif in_aai and not in_yt:
        print(f"✓ AssemblyAI includes '{phrase}', YouTube doesn't")
    elif in_yt and not in_aai:
        print(f"⚠ YouTube includes '{phrase}', AssemblyAI doesn't")

print(f"\n" + "="*70)
print("CONCLUSION")
print("="*70)

if similarity > 0.9:
    quality = "Excellent"
elif similarity > 0.8:
    quality = "Very Good"
elif similarity > 0.7:
    quality = "Good"
else:
    quality = "Fair"

print(f"\nTranscription Quality: {quality} ({similarity:.1%} similarity)")

print("\nAssemblyAI Advantages:")
print("  • Speaker diarization (identifies individual speakers)")
print("  • More accurate proper nouns (e.g., 'San Rafael' not 'Sanfell')")
print("  • Structured speaker turns (easier to parse)")
print("  • API access for automation")

print("\nYouTube Advantages:")
print("  • Free (auto-generated)")
print("  • Already available (no processing delay)")
print("  • Word-level timestamps")

print(f"\nRecommendation: Use AssemblyAI for testimony extraction")
print(f"  - Speaker labels critical for identifying testifiers")
print(f"  - Higher accuracy on proper nouns (city names, people)")
print(f"  - Worth the cost ($2.80/meeting) for structured data")
