"""Load and extract text from YouTube JSON3 transcripts."""

import json
from pathlib import Path
from typing import Optional, Union


def load_youtube_transcript(
    source: Union[str, Path],
    max_chars: Optional[int] = None,
) -> str:
    """
    Load YouTube JSON3 transcript and extract text.

    Args:
        source: Path to YouTube .json3 file, or raw JSON string
        max_chars: Maximum characters to extract (None = unlimited)

    Returns:
        Extracted transcript text
    """
    path = Path(source)
    with open(path) as f:
        data = json.load(f)

    text = ""
    for event in data.get("events", []):
        if "segs" in event:
            for seg in event["segs"]:
                if "utf8" in seg:
                    text += seg["utf8"]
                if max_chars and len(text) >= max_chars:
                    break
        if max_chars and len(text) >= max_chars:
            break

    return text[:max_chars] if max_chars else text
