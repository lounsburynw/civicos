"""
Speaker resolution for transcript chunks.

Resolves generic diarization labels (e.g., "Staff Member 6", "Multiple speakers")
to real names using a 3-tier strategy:

1. Per-meeting label map — correlates role-hinted labels within the same video
2. Jurisdiction roster — config/rosters/*.json with aliases and overrides
3. Display fallbacks — generic labels → human-readable text

Usage:
    from civicos.speakers import resolve_meeting_speakers
    from civicos.roster import Roster

    roster = Roster.load("city-san-rafael")
    enriched = resolve_meeting_speakers(
        video_id="NYkGE9nVLUc",
        raw_labels=["Staff Member 6", "Multiple speakers", "Dave Spiller"],
        vector_backend=vectors,
        roster=roster,
    )
    # enriched == {"Staff Member 6": ("Robert Epstein, City Attorney", False), ...}
"""

import re
from typing import Dict, List, Optional, Tuple


def extract_speaker_from_text(text: str) -> Tuple[Optional[str], bool]:
    """Extract speaker name and public_comment flag from embedded transcript labels.

    Transcript chunks often start with labels like [Belle Cole], [Public Speaker 1],
    [Staff Member 2] when metadata doesn't carry speaker info.

    Returns:
        (speaker_label, is_public_comment)
    """
    m = re.match(r"\[([^\]]+)\]", text)
    if not m:
        return None, False
    label = m.group(1)
    is_public = label.lower().startswith("public speaker")
    return label, is_public


def get_video_id_from_chunk(chunk_id: str) -> str:
    """Extract video ID from a transcript chunk ID.

    Chunk IDs follow pattern: transcript-VIDEO_ID-CHUNK_NUM
    """
    m = re.match(r"transcript-(.+)-(\d+)$", chunk_id)
    return m.group(1) if m else ""


def build_meeting_speaker_map(video_id: str, vector_backend, roster=None) -> Dict[str, str]:
    """Build a speaker resolution map from ALL transcript chunks of a meeting.

    Scans all chunks with the given video_id to find role-hinted labels
    (e.g., "Staff Member 6 (City Attorney)") and builds a mapping from
    bare generic labels to resolved display names using the jurisdiction roster.

    Args:
        video_id: YouTube video ID for the meeting
        vector_backend: VectorBackend with get_chunks_by_prefix()
        roster: Roster instance (from config/rosters/) for official name resolution

    Returns:
        dict mapping raw labels to resolved display names, e.g.:
        {"Staff Member 6": "Robert Epstein, City Attorney",
         "Staff Member 1": "City Manager"}
    """
    if not video_id or not vector_backend:
        return {}

    try:
        chunks = vector_backend.get_chunks_by_prefix(
            id_prefix=f"transcript-{video_id}-",
            corpus_type="transcripts",
            limit=800,
        )

        # Collect all labels from this meeting
        label_counts: Dict[str, int] = {}
        for chunk in chunks:
            m = re.match(r"\[([^\]]+)\]", chunk.content)
            if m:
                label_counts[m.group(1)] = label_counts.get(m.group(1), 0) + 1

        speaker_map: Dict[str, str] = {}
        role_pattern = re.compile(r"^(Staff Member \d+)\s*\(([^)]+)\)$")

        for label in label_counts:
            rm = role_pattern.match(label)
            if rm:
                bare_label = rm.group(1)       # e.g., "Staff Member 6"
                role = rm.group(2).strip()      # e.g., "City Attorney"

                # Use roster to resolve role → real name
                display = role
                if roster:
                    official = roster.find_official(role)
                    if official:
                        display = f"{official.name}, {role}"

                speaker_map[bare_label] = display
                speaker_map[label] = display

        # Also map named labels that include roles (e.g., "Kate Colin (Mayor)")
        name_role_pattern = re.compile(
            r"^([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s*\(([^)]+)\)$"
        )
        for label in label_counts:
            nrm = name_role_pattern.match(label)
            if nrm:
                name = nrm.group(1).strip()
                role = nrm.group(2).strip()
                # Correct misspellings via roster alias matching
                if roster:
                    official = roster.find_official(name)
                    if official:
                        name = official.name
                speaker_map[label] = f"{name}, {role}"

        return speaker_map

    except Exception:
        return {}


def resolve_speaker(raw_label: str, meeting_map: Dict[str, str], roster=None) -> Tuple[Optional[str], bool]:
    """Resolve a raw transcript label to a display name and type.

    Uses a 3-tier resolution strategy:
    1. Per-meeting label map (correlates generic labels within the same video)
    2. Jurisdiction roster (config/rosters/*.json — aliases, overrides)
    3. Display fallbacks (generic → human-readable)

    Returns:
        (display_name, is_public)
    """
    if not raw_label:
        return None, False

    # Tier 1: meeting-specific map
    if raw_label in meeting_map:
        resolved = meeting_map[raw_label]
        is_public = raw_label.lower().startswith("public speaker")
        return resolved, is_public

    low = raw_label.lower()

    # Named person with role: "Kate Colin (Mayor)" -> "Kate Colin, Mayor"
    nrm = re.match(r"^([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s*\(([^)]+)\)$", raw_label)
    if nrm:
        name = nrm.group(1)
        role = nrm.group(2)
        if roster:
            official = roster.find_official(name)
            if official:
                name = official.name
        return f"{name}, {role}", False

    # Named person without role — check roster for enrichment
    if re.match(r"^[A-Z][a-z]+(?: [A-Z][a-z]+)+$", raw_label):
        if roster:
            official = roster.find_official(raw_label)
            if official and official.title:
                return f"{official.name}, {official.title}", False
            elif official:
                return official.name, False
        return raw_label, False

    # Public Speaker N -> "Public commenter"
    if low.startswith("public speaker"):
        return "Public commenter", True

    # Multiple speakers -> "Council discussion"
    if low == "multiple speakers":
        return "Council discussion", False

    # Staff Member N with role hint in parentheses
    sm = re.match(r"^Staff Member \d+\s*\(([^)]+)\)$", raw_label)
    if sm:
        role = sm.group(1).strip()
        if roster:
            official = roster.find_official(role)
            if official:
                return f"{official.name}, {role}", False
        return role, False

    # Bare "Staff Member N"
    if re.match(r"^Staff Member \d+$", raw_label):
        return "Council/Staff", False

    # Speaker A/B/C or Speaker N — generic diarization label
    if re.match(r"^Speaker [A-Z0-9]+$", raw_label):
        return "Council/Staff", False

    # Surname with role hint: "Bushee (Council Member)", "Kurtz (Vice Mayor)"
    sr = re.match(r"^(\w+)\s*\(([^)]+)\)$", raw_label)
    if sr:
        name_part = sr.group(1)
        role = sr.group(2)
        if roster:
            official = roster.find_official(name_part)
            if official:
                return f"{official.name}, {role}", False
        return f"{name_part}, {role}", False

    # Fallback: null or unknown
    if low in ("null", "?", ""):
        return None, False

    # Last chance: check roster for single-name matches (e.g., "Dickinson")
    if roster:
        official = roster.find_official(raw_label)
        if official and official.title:
            return f"{official.name}, {official.title}", False
        elif official:
            return official.name, False

    return raw_label, False
