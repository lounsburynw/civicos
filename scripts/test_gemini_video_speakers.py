#!/usr/bin/env python3
"""
Test Gemini 2.0 Flash multimodal video analysis for speaker counting.

Uses Gemini to visually identify speakers in YouTube city council videos.
This provides a "positive control" for validating audio-only diarization.

Session: 108
"""

import os
import sys
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

def test_gemini_youtube_speakers(youtube_url: str, sample_duration: str = "full"):
    """
    Test Gemini's ability to count speakers from YouTube video.

    Args:
        youtube_url: YouTube video URL
        sample_duration: "full", "first_30min", or "public_comment"
    """
    # Configure Gemini
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in environment")
        sys.exit(1)

    genai.configure(api_key=api_key)

    # Use Gemini 2.0 Flash for video
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

    print("=" * 70)
    print("GEMINI 2.0 FLASH - VIDEO SPEAKER ANALYSIS")
    print("=" * 70)
    print(f"\nVideo URL: {youtube_url}")
    print(f"Sample duration: {sample_duration}")

    # Craft prompt based on sample duration
    if sample_duration == "full":
        prompt = """Analyze this entire city council meeting video and count the unique speakers.

Focus on:
1. Council members (Mayor, Vice Mayor, Council Members) - usually seated at the dais
2. City staff (City Attorney, City Manager, Department heads) - usually at staff table
3. Public commenters - people who come to the podium to speak

For each unique speaker you identify, provide:
- Role/position (if discernible from context)
- Physical description (clothing, appearance to help identify them)
- Approximate speaking time or number of times they spoke

Give me:
1. Total count of unique speakers
2. Breakdown by category (council, staff, public)
3. List of each speaker with description

This is critical for a civic engagement case study, so accuracy is essential."""

    elif sample_duration == "first_30min":
        prompt = """Analyze the first 30 minutes of this city council meeting video and identify the council members and staff.

Count and describe:
1. Mayor (usually leads the meeting)
2. Council members (seated at dais)
3. City staff (attorney, manager, etc.)

For each person, provide a brief physical description."""

    elif sample_duration == "public_comment":
        prompt = """Focus on the PUBLIC COMMENT period of this city council meeting (usually 1-2 hours into the meeting).

Count every unique person who comes to the podium to speak during public comment.

For each public commenter:
- Physical description (to distinguish them)
- Topic they spoke about (if discernible)
- Approximate timestamp when they spoke

This is for analyzing public testimony on wildfire prevention funding."""

    print("\n" + "=" * 70)
    print("Sending to Gemini 2.0 Flash...")
    print("=" * 70)
    print(f"\nPrompt: {prompt[:200]}...")

    try:
        # Note: Gemini API might not support direct YouTube URLs
        # We may need to use a different approach

        # Attempt 1: Direct YouTube URL
        print("\nAttempting to send YouTube URL directly to Gemini...")
        response = model.generate_content([prompt, youtube_url])

        print("\n" + "=" * 70)
        print("GEMINI RESPONSE:")
        print("=" * 70)
        print(response.text)

        return response.text

    except Exception as e:
        print(f"\nError: {e}")
        print("\nNote: Gemini may not support direct YouTube URLs.")
        print("Alternative approaches:")
        print("1. Download video and upload to Gemini Files API")
        print("2. Extract frames and analyze images")
        print("3. Use Google Cloud Video Intelligence API instead")
        return None


if __name__ == "__main__":
    # Oct 6 2024 San Rafael City Council - Wildfire Fund Case Study
    youtube_url = "https://www.youtube.com/watch?v=MpxrGRb16HQ"

    print("\n" + "=" * 70)
    print("POSITIVE CONTROL TEST: Gemini Video Analysis")
    print("=" * 70)
    print("\nThis test will validate speaker counts for the Oct 6 wildfire")
    print("testimony case study using visual (multimodal) analysis.")
    print("")
    print("If successful, we'll know the TRUE number of speakers to")
    print("compare against WhisperX and AssemblyAI audio diarization.")

    # Test 1: Try full video (may fail due to length)
    print("\n\nTest 1: Full video analysis")
    print("-" * 70)
    result = test_gemini_youtube_speakers(youtube_url, "full")

    if result is None:
        print("\n\nFull video failed. Trying first 30 minutes...")
        print("-" * 70)
        result = test_gemini_youtube_speakers(youtube_url, "first_30min")
