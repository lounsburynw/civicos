"""
Pattern-based speaker estimation from YouTube transcripts.

Uses regex patterns and heuristics to estimate speaker counts.
Free (no API calls), fast, good for council member detection.
"""

import re
from dataclasses import dataclass, field
from typing import List

from .transcript_loader import load_youtube_transcript


@dataclass
class PatternEstimate:
    """Result from pattern-based speaker estimation."""

    named_speakers: List[str] = field(default_factory=list)
    speaker_changes: int = 0
    min_estimate: int = 5
    max_estimate: int = 50
    confidence: str = "medium"


def _extract_names(text: str) -> set:
    """Extract speaker names from title patterns in transcript text."""
    names = set()

    title_patterns = [
        r"(?:Mayor|Vice Mayor|Council Member|Councilmember)\s+([A-Z][a-z]+)",
    ]

    for pattern in title_patterns:
        matches = re.findall(pattern, text)
        valid = [
            m
            for m in matches
            if m and len(m) > 2 and m not in ("The", "And", "But", "Was", "Will", "Can")
        ]
        names.update(valid)

    # Title-only mentions
    for title in ("City Attorney", "City Manager", "City Clerk"):
        if title in text:
            names.add(title)

    return names


def _count_speaker_changes(text: str) -> int:
    """Count likely speaker transitions via procedural markers."""
    thank_you = len(re.findall(r"\bthank you\b", text, re.IGNORECASE))
    markers = text.count(">>")
    return max(thank_you, markers)


def estimate_from_pattern(transcript_path: str) -> PatternEstimate:
    """
    Estimate speaker count from a YouTube JSON3 transcript using text patterns.

    Args:
        transcript_path: Path to YouTube .json3 file

    Returns:
        PatternEstimate with named speakers and estimated range
    """
    text = load_youtube_transcript(transcript_path)
    names = _extract_names(text)
    changes = _count_speaker_changes(text)

    # Heuristic: "thank you" count / 3 ≈ unique speakers
    estimated_from_changes = max(2, changes // 3)

    named_count = len(names)
    min_est = max(named_count, 5)
    # Use changes as upper signal, but don't cap artificially low
    max_est = max(estimated_from_changes, named_count + 10)

    return PatternEstimate(
        named_speakers=sorted(names),
        speaker_changes=changes,
        min_estimate=min_est,
        max_estimate=max_est,
        confidence="high" if named_count >= 5 else "medium",
    )
