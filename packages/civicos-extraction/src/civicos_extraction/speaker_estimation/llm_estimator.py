"""
LLM-based speaker estimation from YouTube transcripts.

Uses OpenAI structured outputs to estimate the number of unique speakers
in a city council meeting. Provides a data-driven prior for AssemblyAI
speaker diarization.

Cost: ~$0.001-0.01 per transcript (gpt-4o-mini)
"""

import logging
from typing import List

from pydantic import BaseModel, Field

from .transcript_loader import load_youtube_transcript

logger = logging.getLogger(__name__)

# Default character limit for cost efficiency
DEFAULT_MAX_CHARS = 4000


class SpeakerEstimate(BaseModel):
    """Structured output for LLM speaker estimation."""

    named_speakers: List[str] = Field(
        description="List of speakers explicitly named or with titles "
        "(e.g., 'Mayor Kate', 'Council Member Hill')"
    )
    estimated_total_speakers: int = Field(
        description="Best estimate of total unique speakers in the meeting",
        ge=3,
        le=100,
    )
    confidence: str = Field(
        description="Confidence level: 'high', 'medium', or 'low'",
        pattern="^(high|medium|low)$",
    )
    reasoning: str = Field(
        description="Brief explanation of how you estimated the speaker count"
    )


_SYSTEM_PROMPT = (
    "You are analyzing city council meeting transcripts to estimate the number "
    "of unique speakers. Look for named speakers (Mayor, Council Members, staff), "
    "speaker introductions, public commenters, and conversational patterns. "
    "City council meetings with public comment periods can have 20-50+ unique speakers."
)

_USER_PROMPT_TEMPLATE = """Analyze this city council meeting transcript and estimate the number of unique speakers:

{text}

Identify:
1. Named speakers (with titles like Mayor, Council Member, etc.)
2. Staff members or city employees who speak
3. Public commenters (residents who testify)
4. Estimated total unique speakers based on conversational flow

Remember: Meetings with public comment can have 20-50+ speakers. Count all unique voices."""


def estimate_from_llm(
    transcript_path: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> SpeakerEstimate:
    """
    Use LLM to estimate speakers from a YouTube JSON3 transcript.

    Requires OPENAI_API_KEY environment variable.

    Args:
        transcript_path: Path to YouTube JSON3 transcript
        max_chars: Maximum characters to analyze (controls cost)

    Returns:
        SpeakerEstimate with named speakers and total count

    Raises:
        ImportError: If openai package is not installed
        Exception: If API call fails
    """
    from openai import OpenAI

    text = load_youtube_transcript(transcript_path, max_chars=max_chars)
    logger.debug("Loaded %d chars from %s", len(text), transcript_path)

    client = OpenAI()
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT_TEMPLATE.format(text=text)},
        ],
        response_format=SpeakerEstimate,
    )

    return completion.choices[0].message.parsed
