"""
Video transcript parsing and chunking for RAG.

Converts AssemblyAI diarized transcripts into semantic chunks that preserve
speaker attribution and timestamps for video linking.

Transcript Format (AssemblyAI):
{
    "video_id": "...",
    "utterances": [
        {"speaker": "A", "text": "...", "start": 12345, "end": 12678},
        ...
    ]
}

Chunking Strategy:
- Group consecutive utterances from the same speaker
- Split at speaker changes OR when chunk exceeds max size
- Preserve timestamps (start of first utterance, end of last)
- Support overlap for RAG continuity

Speaker Role Detection:
- LLM-based extraction (preferred): Uses AI to analyze meeting context
- Parse roll call section to identify council members
- Use utterance patterns to infer staff/public roles
- Apply heuristics based on speaker frequency and speech patterns
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, TYPE_CHECKING
import json
import logging
import re

if TYPE_CHECKING:
    from providers.base import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class TranscriptUtterance:
    """A single utterance from a diarized transcript."""
    speaker: str  # Speaker label (A, B, C, ...)
    text: str
    start_ms: int  # Start time in milliseconds
    end_ms: int  # End time in milliseconds

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }


@dataclass
class TranscriptChunk:
    """A chunk of transcript text with speaker and timing metadata."""
    text: str
    speaker: str  # Primary speaker (most text) or "multiple"
    speakers: list[str]  # All speakers in this chunk
    start_ms: int
    end_ms: int
    chunk_index: int
    total_chunks: int
    utterance_count: int  # Number of utterances in this chunk
    metadata: dict = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    @property
    def start_timestamp(self) -> str:
        """Human-readable start time (HH:MM:SS)."""
        total_seconds = self.start_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @property
    def end_timestamp(self) -> str:
        """Human-readable end time (HH:MM:SS)."""
        total_seconds = self.end_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "speaker": self.speaker,
            "speakers": self.speakers,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "utterance_count": self.utterance_count,
            "metadata": self.metadata,
        }

    def to_embedding_text(self) -> str:
        """Generate text for embedding (includes speaker context)."""
        speaker_label = f"[Speaker {self.speaker}]" if self.speaker != "multiple" else "[Multiple speakers]"
        return f"{speaker_label} {self.text}"


@dataclass
class SpeakerInfo:
    """Information about a speaker in the transcript."""
    speaker_id: str  # AssemblyAI speaker label (A, B, C, ...)
    role: str  # council, staff, public, unknown
    name: str | None = None  # Detected name if available
    title: str | None = None  # Mayor, Vice Mayor, Council Member, etc.
    confidence: float = 0.0  # 0.0-1.0 confidence in role assignment
    evidence: list[str] = field(default_factory=list)  # Reasons for assignment

    def to_dict(self) -> dict:
        return {
            "speaker_id": self.speaker_id,
            "role": self.role,
            "name": self.name,
            "title": self.title,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


class SpeakerRoleDetector:
    """
    Detect speaker roles from city council meeting transcripts.

    Uses multiple heuristics:
    1. Roll call parsing - identifies council members by name from roll call
    2. Speech patterns - council members use procedural language
    3. Speaker frequency - council/staff speak more than public
    4. Self-introductions - public speakers often introduce themselves
    """

    # Common titles that indicate council/staff roles
    COUNCIL_TITLES = [
        "mayor",
        "vice mayor",
        "council member",
        "councilmember",
        "councilwoman",
        "councilman",
    ]

    STAFF_TITLES = [
        "city manager",
        "city clerk",
        "city attorney",
        "director",
        "chief",
        "deputy",
        "planner",
        "manager",
    ]

    # Patterns for introducing staff members (speaker A introduces speaker B)
    # Note: These are fallback patterns when LLM detection is not available.
    # LLM-based detection is preferred and more accurate.
    STAFF_INTRODUCTION_PATTERNS = [
        # "I'll turn to the City Manager..."
        (r"i'll turn to the (city manager|city attorney|city clerk)", None),
        # "I'll invite the City Attorney to report..."
        (r"i'll invite the (city manager|city attorney|city clerk)", None),
        # "Deputy City Clerk to call the roll"
        (r"(deputy city clerk|city clerk) to (call|read)", "city clerk"),
        # "Chief [Name] is joining us" (e.g., "Chief Senate is joining us")
        (r"chief\s+(\w+)\s+is joining", "chief"),
    ]

    # Patterns for staff self-identification
    STAFF_SELF_PATTERNS = [
        # "Good evening Mayor, Council members and the community. I wanted to start..."
        # (City Manager often uses this opening)
        (r"good evening,?\s+mayor.*council\s*members?.*community", "city manager", 0.6),
        # "no reportable action was taken in closed session"
        (r"no reportable action.*closed session", "city attorney", 0.8),
        # "Mayor [name], members of the council and the community"
        (r"mayor\s+\w+,?\s+members of the council", "senior staff", 0.5),
    ]

    # Patterns that indicate council/staff speech
    COUNCIL_PATTERNS = [
        r"\bi move\b",
        r"\bi second\b",
        r"\ball in favor\b",
        r"\bmotion passes\b",
        r"\baye\b",
        r"\bnay\b",
        r"\broll call\b",
    ]

    # Patterns that indicate public testimony
    PUBLIC_PATTERNS = [
        r"\bmy name is\b",
        r"\bi ('m|am) a resident\b",
        r"\bi live (in|on|at)\b",
        r"\bthank you (mayor|council|for)\b",
        r"\bgood evening (mayor|council)\b",
    ]

    # Patterns that indicate opening a public comment section
    PUBLIC_COMMENT_OPEN_PATTERNS = [
        r"(?:i'll|i will|let me|we'll)\s+open\s+(?:up\s+)?(?:the\s+)?public\s+comment",
        r"open\s+(?:the\s+)?public\s+(?:comment|hearing)",
        r"welcome\s+public\s+comment",
        r"anyone\s+from\s+the\s+public.*(?:opportunity|comment|speak)",
        r"public\s+comment\s+on\s+(?:this\s+)?(?:item|agenda)",
        r"now\s+is\s+your\s+opportunity",  # Often follows "anyone from the public"
    ]

    # Patterns that indicate closing a public comment section
    PUBLIC_COMMENT_CLOSE_PATTERNS = [
        r"(?:i'll|i will|let me|we'll)\s+close\s+(?:the\s+)?public\s+comment",
        r"close\s+(?:the\s+)?public\s+(?:comment|hearing)",
        r"not\s+(?:seeing|see)\s+(?:any\s+)?(?:other\s+)?public\s+comment.*(?:close|move|bring)",
        r"public\s+comment\s+(?:is\s+)?closed",
    ]

    def __init__(
        self,
        roll_call_window_ms: int = 600_000,  # First 10 minutes (meetings often start with delays)
        min_utterances_for_staff: int = 10,  # Staff typically speak a lot
        llm_provider: "LLMProvider | None" = None,  # Optional LLM for enhanced detection
        roster: "Roster | None" = None,  # Optional roster for known officials
    ):
        self.roll_call_window_ms = roll_call_window_ms
        self.min_utterances_for_staff = min_utterances_for_staff
        self.llm_provider = llm_provider
        self.roster = roster

        # Compile patterns
        self._council_re = [re.compile(p, re.IGNORECASE) for p in self.COUNCIL_PATTERNS]
        self._public_re = [re.compile(p, re.IGNORECASE) for p in self.PUBLIC_PATTERNS]
        self._public_open_re = [re.compile(p, re.IGNORECASE) for p in self.PUBLIC_COMMENT_OPEN_PATTERNS]
        self._public_close_re = [re.compile(p, re.IGNORECASE) for p in self.PUBLIC_COMMENT_CLOSE_PATTERNS]

        # Store detected public comment sections (populated by detect_public_comment_sections)
        self.public_comment_sections: list[tuple[int, int, str]] = []  # (start_idx, end_idx, opener_speaker)

    def detect_roles(
        self,
        utterances: list[TranscriptUtterance],
    ) -> dict[str, SpeakerInfo]:
        """
        Analyze utterances and assign roles to speakers.

        Args:
            utterances: List of transcript utterances

        Returns:
            Dictionary mapping speaker ID to SpeakerInfo
        """
        if not utterances:
            return {}

        # Initialize speaker info for all speakers
        speakers: dict[str, SpeakerInfo] = {}
        for utt in utterances:
            if utt.speaker not in speakers:
                speakers[utt.speaker] = SpeakerInfo(
                    speaker_id=utt.speaker,
                    role="unknown",
                )

        # Count utterances per speaker
        utterance_counts: dict[str, int] = {}
        for utt in utterances:
            utterance_counts[utt.speaker] = utterance_counts.get(utt.speaker, 0) + 1

        # Phase 0 (Optional): Use LLM for enhanced detection
        if self.llm_provider is not None:
            try:
                self._detect_with_llm(utterances, speakers)
            except Exception as e:
                logger.warning(f"LLM detection failed, falling back to patterns: {e}")

        # Phase 1: Parse roll call to identify council members
        self._parse_roll_call(utterances, speakers)

        # Phase 2: Detect staff from introductions and speech patterns
        self._detect_staff_roles(utterances, speakers)

        # Phase 3: Detect from speech patterns
        self._detect_from_patterns(utterances, speakers)

        # Phase 4: Apply frequency heuristics
        self._apply_frequency_heuristics(utterance_counts, speakers)

        # Phase 5: Detect self-introductions for public speakers
        self._detect_self_introductions(utterances, speakers)

        # Phase 6: Detect public comment sections and enhance speaker roles
        self._apply_public_comment_context(utterances, speakers)

        return speakers

    def _apply_public_comment_context(
        self,
        utterances: list[TranscriptUtterance],
        speakers: dict[str, SpeakerInfo],
    ) -> None:
        """
        Use public comment section detection to improve speaker role assignments.

        Speakers who only speak within public comment sections are likely public.
        """
        if not utterances:
            return

        # Detect public comment sections
        sections = self.detect_public_comment_sections(utterances)
        if not sections:
            return

        # Build a set of utterance indices that are within public comment sections
        public_section_indices = set()
        for section in sections:
            for idx in range(section["start_idx"], section["end_idx"] + 1):
                public_section_indices.add(idx)

        # Track which speakers speak exclusively in public comment sections
        speaker_in_public_only: dict[str, bool] = {s: True for s in speakers}
        speaker_public_utterances: dict[str, int] = {s: 0 for s in speakers}

        for i, utt in enumerate(utterances):
            is_in_public = i in public_section_indices
            if is_in_public:
                speaker_public_utterances[utt.speaker] += 1
            else:
                speaker_in_public_only[utt.speaker] = False

        # Update roles for speakers who only speak in public comment sections
        for speaker_id, info in speakers.items():
            if speaker_in_public_only[speaker_id] and speaker_public_utterances[speaker_id] > 0:
                if info.role == "unknown" or (info.role == "public" and info.confidence < 0.8):
                    info.role = "public"
                    info.confidence = max(info.confidence, 0.8)
                    info.evidence.append(
                        f"Spoke exclusively in public comment sections ({speaker_public_utterances[speaker_id]} utterances)"
                    )

    def _detect_with_llm(
        self,
        utterances: list[TranscriptUtterance],
        speakers: dict[str, SpeakerInfo],
    ) -> None:
        """
        Use LLM to detect speaker roles from transcript context.

        This method analyzes the first portion of the meeting where
        introductions typically occur and uses an LLM to identify:
        - Council members (Mayor, Vice Mayor, Council Members)
        - Staff members (City Manager, City Attorney, City Clerk, etc.)
        - The mapping between speaker IDs (A, B, C...) and their roles

        Args:
            utterances: List of transcript utterances
            speakers: Dictionary to update with detected roles
        """
        if not self.llm_provider or not utterances:
            return

        # Take first 30 utterances (where introductions happen)
        sample_utterances = utterances[:30]

        # Format transcript for LLM
        transcript_text = "\n".join(
            f"[Speaker {u.speaker}]: {u.text}"
            for u in sample_utterances
        )

        # Build roster context if available
        roster_context = ""
        if self.roster and self.roster.officials:
            officials_list = []
            for official in self.roster.officials:
                title_str = f" ({official.title})" if official.title else ""
                officials_list.append(f"- {official.name}{title_str} [{official.role}]")
            roster_context = f"""
KNOWN OFFICIALS FOR THIS JURISDICTION:
{chr(10).join(officials_list)}

IMPORTANT: Match speakers to these known officials when possible. Use their FULL NAMES as listed above.
For example, if someone calls roll or reads names during public comment, they are likely the City Clerk.
If someone is addressed as "Mayor" or responds to roll call, match them to the Mayor listed above.

"""

        prompt = f"""Analyze this city council meeting transcript excerpt and identify the speaker roles.
{roster_context}
TRANSCRIPT:
{transcript_text}

TASK: Identify which speaker IDs (A, B, C, etc.) correspond to which roles.

Look for:
1. Roll call responses - who says "Present" after their name is called
2. Staff introductions - "I'll turn to the City Manager", "City Attorney to report"
3. Titles mentioned - Mayor, Vice Mayor, Council Member, City Manager, City Attorney, City Clerk
4. Speech patterns - staff often greet "Mayor, Council members and the community"
5. Behavior patterns - who calls roll (Clerk), who presides (Mayor), who gives legal advice (Attorney)

Return a JSON object with this structure:
{{
    "speakers": [
        {{
            "speaker_id": "A",
            "role": "council" | "staff" | "public" | "unknown",
            "title": "Mayor" | "Vice Mayor" | "Council Member" | "City Manager" | "City Attorney" | "City Clerk" | null,
            "name": "full name from roster if matched, or detected name, or null",
            "confidence": 0.0-1.0,
            "evidence": "brief explanation"
        }}
    ]
}}

Only include speakers you can identify with confidence >= 0.6.
Return ONLY valid JSON, no additional text."""

        messages = [
            {"role": "user", "content": prompt}
        ]

        # Call LLM with JSON response format
        response = self.llm_provider.chat(
            messages=messages,
            response_format="json_object",
        )

        # Parse response (provider handles markdown fence stripping)
        try:
            result = json.loads(response.strip())
            detected_speakers = result.get("speakers", [])

            for detected in detected_speakers:
                speaker_id = detected.get("speaker_id")
                if not speaker_id or speaker_id not in speakers:
                    continue

                confidence = detected.get("confidence", 0.5)
                if confidence < 0.6:
                    continue

                info = speakers[speaker_id]

                # Only update if LLM detection is more confident
                if confidence > info.confidence:
                    role = detected.get("role", "unknown")
                    if role in ("council", "staff", "public"):
                        info.role = role
                    info.title = detected.get("title")
                    info.name = detected.get("name")
                    info.confidence = confidence
                    evidence = detected.get("evidence", "LLM detection")
                    info.evidence.append(f"LLM: {evidence}")

            logger.info(f"LLM detected {len(detected_speakers)} speaker roles")

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            raise

    def _parse_roll_call(
        self,
        utterances: list[TranscriptUtterance],
        speakers: dict[str, SpeakerInfo],
    ) -> None:
        """
        Parse roll call section to identify council members.

        Roll call pattern:
        1. Someone calls a name with title (e.g., "Vice Mayor Bushy")
        2. That person responds "Present" or similar
        3. The speaker who says "Present" is matched to the title/name
        """
        if not utterances:
            return

        start_ms = utterances[0].start_ms

        # Title patterns for extraction
        title_patterns = [
            (r"(?:vice\s+)?mayor\s+(\w+)", "mayor"),
            (r"council\s*member\s+(\w+)", "council member"),
            (r"councilmember\s+(\w+)", "council member"),
        ]

        # Process utterances in roll call window
        i = 0
        while i < len(utterances):
            utt = utterances[i]

            # Stop after roll call window
            if utt.start_ms - start_ms > self.roll_call_window_ms:
                break

            text_lower = utt.text.lower()

            # Check if this is a roll call name announcement
            for pattern, title_type in title_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    called_name = match.group(1).capitalize()
                    full_title = "Vice Mayor" if "vice mayor" in text_lower else (
                        "Mayor" if title_type == "mayor" else "Council Member"
                    )

                    # Look for "Present" response in next few utterances
                    for j in range(i + 1, min(i + 4, len(utterances))):
                        next_utt = utterances[j]
                        next_text = next_utt.text.lower().strip()

                        # Check for present/here response
                        if next_text in ("present", "present.", "here", "here.", "president", "president."):
                            responder = next_utt.speaker

                            # Update speaker info
                            info = speakers[responder]
                            info.role = "council"
                            info.name = called_name
                            info.title = full_title
                            info.confidence = max(info.confidence, 0.9)
                            info.evidence.append(
                                f"Responded 'present' to roll call for {full_title} {called_name}"
                            )
                            break
                    break

            i += 1

        # Identify the clerk (person calling roll call names)
        # They call multiple council member names in quick succession
        name_callers: dict[str, int] = {}
        for i, utt in enumerate(utterances):
            if utt.start_ms - start_ms > self.roll_call_window_ms:
                break

            text_lower = utt.text.lower()
            for pattern, _ in title_patterns:
                if re.search(pattern, text_lower):
                    name_callers[utt.speaker] = name_callers.get(utt.speaker, 0) + 1

        # Speaker who called 2+ names is likely clerk
        for speaker_id, count in name_callers.items():
            if count >= 2 and speakers[speaker_id].role == "unknown":
                info = speakers[speaker_id]
                info.role = "staff"
                info.title = "City Clerk"
                info.confidence = max(info.confidence, 0.7)
                info.evidence.append(f"Called {count} names during roll call")

    def _detect_staff_roles(
        self,
        utterances: list[TranscriptUtterance],
        speakers: dict[str, SpeakerInfo],
    ) -> None:
        """
        Detect staff roles from introductions and speech patterns.

        Staff detection strategies:
        1. Parse staff introductions (e.g., "I'll turn to the City Manager")
        2. Detect staff self-identification patterns
        3. Look for title+name patterns (e.g., "Deputy City Attorney, Katherine")
        """
        if not utterances:
            return

        # Track pending staff introductions (speaker X introduces role, next speaker Y has that role)
        pending_introductions: list[tuple[str, int]] = []  # (title, utterance_index)

        for i, utt in enumerate(utterances):
            text_lower = utt.text.lower()

            # Check for staff introduction patterns (someone introducing staff)
            for pattern, fixed_title in self.STAFF_INTRODUCTION_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    # Determine the title being introduced
                    if fixed_title:
                        title = fixed_title.title()
                    else:
                        # Extract from pattern match
                        title = match.group(1).title() if match.lastindex else None

                    if title:
                        pending_introductions.append((title, i))

                    # Check for name in same utterance (e.g., "Deputy City Attorney, Katherine Cass Meier")
                    if match.lastindex and match.lastindex >= 2:
                        name = match.group(2)
                        if name and name[0].isupper():
                            # Name found in introduction - assign to next speaker
                            pending_introductions.append((f"{title}:{name}", i))

            # Check if this speaker is the one being introduced
            if pending_introductions and i > 0:
                for title, intro_idx in pending_introductions:
                    # Only process if this is a different speaker than the introducer
                    # and within a reasonable distance (next 3 utterances)
                    if i > intro_idx and i <= intro_idx + 3:
                        prev_speaker = utterances[intro_idx].speaker
                        if utt.speaker != prev_speaker and speakers[utt.speaker].role == "unknown":
                            # Parse title and optional name
                            if ":" in title:
                                role_title, name = title.split(":", 1)
                            else:
                                role_title, name = title, None

                            info = speakers[utt.speaker]
                            info.role = "staff"
                            info.title = role_title
                            if name:
                                info.name = name
                            info.confidence = max(info.confidence, 0.75)
                            info.evidence.append(f"Introduced as {role_title}")

            # Check for staff self-identification patterns
            for pattern, role_title, confidence in self.STAFF_SELF_PATTERNS:
                if re.search(pattern, text_lower):
                    info = speakers[utt.speaker]
                    if info.role == "unknown" or (info.role == "staff" and not info.title):
                        info.role = "staff"
                        if info.title is None:
                            info.title = role_title.title()
                        info.confidence = max(info.confidence, confidence)
                        info.evidence.append(f"Speech pattern matches {role_title}")

            # Check for explicit title+name mentions (e.g., "Chief Senate")
            chief_match = re.search(r"\bchief\s+(\w+)\b", text_lower)
            if chief_match:
                chief_name = chief_match.group(1).capitalize()
                # Don't match "chief of" or similar
                if chief_name.lower() not in ("of", "the", "and", "or", "a"):
                    # Look for this name in speaker utterances
                    for speaker_id, info in speakers.items():
                        if info.role == "unknown":
                            # If this speaker mentions a chief, they might be council/staff
                            pass  # Don't auto-assign, just note for context

            # Check for "City Manager Report" or similar report patterns
            if "city manager report" in text_lower or "manager report" in text_lower:
                # The speaker giving this is likely the city manager
                info = speakers[utt.speaker]
                if info.role == "unknown":
                    # Check if this is a long utterance (reports are usually detailed)
                    if len(utt.text) > 200:
                        info.role = "staff"
                        info.title = "City Manager"
                        info.confidence = max(info.confidence, 0.7)
                        info.evidence.append("Gave City Manager Report")

        # Clear processed introductions
        pending_introductions.clear()

    def _detect_from_patterns(
        self,
        utterances: list[TranscriptUtterance],
        speakers: dict[str, SpeakerInfo],
    ) -> None:
        """Detect roles from speech patterns."""
        # Track pattern matches per speaker
        council_matches: dict[str, list[str]] = {s: [] for s in speakers}
        public_matches: dict[str, list[str]] = {s: [] for s in speakers}

        for utt in utterances:
            text = utt.text

            # Check council patterns
            for pattern in self._council_re:
                if pattern.search(text):
                    council_matches[utt.speaker].append(pattern.pattern)

            # Check public patterns
            for pattern in self._public_re:
                if pattern.search(text):
                    public_matches[utt.speaker].append(pattern.pattern)

        # Apply pattern evidence
        for speaker_id, info in speakers.items():
            council_count = len(council_matches[speaker_id])
            public_count = len(public_matches[speaker_id])

            if council_count > 0 and info.role == "unknown":
                info.evidence.append(
                    f"Used council language {council_count} times"
                )
                # Don't change role yet, just add evidence

            if public_count > 0 and info.role == "unknown":
                info.role = "public"
                info.confidence = max(info.confidence, 0.6)
                info.evidence.append(
                    f"Used public testimony patterns {public_count} times"
                )

    def _apply_frequency_heuristics(
        self,
        utterance_counts: dict[str, int],
        speakers: dict[str, SpeakerInfo],
    ) -> None:
        """Apply frequency-based heuristics."""
        if not utterance_counts:
            return

        # Speakers with many utterances who aren't identified are likely staff
        for speaker_id, count in utterance_counts.items():
            info = speakers[speaker_id]

            if info.role == "unknown" and count >= self.min_utterances_for_staff:
                # High frequency unknown speaker - likely staff
                info.role = "staff"
                info.confidence = max(info.confidence, 0.4)
                info.evidence.append(f"High frequency speaker ({count} utterances)")

            elif info.role == "unknown" and count <= 3:
                # Very low frequency - likely public
                info.role = "public"
                info.confidence = max(info.confidence, 0.3)
                info.evidence.append(f"Low frequency speaker ({count} utterances)")

    def _detect_self_introductions(
        self,
        utterances: list[TranscriptUtterance],
        speakers: dict[str, SpeakerInfo],
    ) -> None:
        """
        Detect names from self-introductions in public testimony.

        Uses LLM for accurate name extraction from varied introduction patterns.
        """
        if not self.llm_provider:
            logger.debug("No LLM provider - skipping public speaker name extraction")
            return

        # Collect utterances from speakers who need name detection
        speakers_needing_names: dict[str, list[str]] = {}
        for utt in utterances:
            info = speakers[utt.speaker]
            if info.role in ("public", "unknown") and info.name is None:
                if utt.speaker not in speakers_needing_names:
                    speakers_needing_names[utt.speaker] = []
                # Only keep first few utterances per speaker (introductions are at start)
                if len(speakers_needing_names[utt.speaker]) < 3:
                    speakers_needing_names[utt.speaker].append(utt.text)

        if not speakers_needing_names:
            return

        # Build prompt for LLM
        utterance_text = "\n".join(
            f"[Speaker {spk}]: {' '.join(texts[:2])}"  # First 2 utterances
            for spk, texts in speakers_needing_names.items()
        )

        prompt = f"""Extract speaker names from these public comment introductions at a city council meeting.

UTTERANCES:
{utterance_text}

TASK: For each speaker, identify if they stated their name. Look for patterns like:
- "My name is [Name]"
- "I'm [Name]"
- "Good evening... [Name], [Title/Organization]"
- "[Name] and I live in..."
- "[Name], resident of..."

Return a JSON object:
{{
    "speakers": [
        {{
            "speaker_id": "A",
            "name": "Full Name or null if not stated",
            "confidence": 0.0-1.0,
            "evidence": "brief quote showing the name"
        }}
    ]
}}

Only include speakers where you can identify a name with confidence >= 0.6.
Return ONLY valid JSON."""

        try:
            response = self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                response_format="json_object",
            )

            result = json.loads(response)
            for detected in result.get("speakers", []):
                speaker_id = detected.get("speaker_id")
                name = detected.get("name")
                confidence = detected.get("confidence", 0.5)

                if not speaker_id or speaker_id not in speakers or not name:
                    continue
                if confidence < 0.6:
                    continue

                info = speakers[speaker_id]
                if info.name is None:  # Don't overwrite existing names
                    info.name = name
                    info.role = "public"
                    info.confidence = max(info.confidence, confidence)
                    evidence = detected.get("evidence", "LLM extraction")
                    info.evidence.append(f"LLM: Name extracted - {evidence}")

            logger.info(f"LLM extracted names for {len(result.get('speakers', []))} public speakers")

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"LLM name extraction failed: {e}")

    def detect_public_comment_sections(
        self,
        utterances: list[TranscriptUtterance],
    ) -> list[dict]:
        """
        Detect public comment sections in a meeting transcript.

        A public comment section is bounded by:
        - An "open" marker (e.g., "I'll open up public comment")
        - A "close" marker (e.g., "I'll close the public comment")

        Args:
            utterances: List of transcript utterances

        Returns:
            List of section dictionaries with:
            - start_idx: Index of utterance after the open marker
            - end_idx: Index of utterance before the close marker
            - opener_idx: Index of the opening utterance
            - closer_idx: Index of the closing utterance (or None if implicit)
            - opener_speaker: Speaker who opened the section
            - confidence: Detection confidence (0.0-1.0)
        """
        if not utterances:
            return []

        sections = []
        pending_open: dict | None = None  # Track the most recent open marker

        for i, utt in enumerate(utterances):
            text = utt.text.lower()

            # Check for close markers first (in case same utterance has both)
            is_close = False
            for pattern in self._public_close_re:
                if pattern.search(text):
                    is_close = True
                    break

            # Check for open markers
            is_open = False
            if not is_close:  # Don't open if we're closing
                for pattern in self._public_open_re:
                    if pattern.search(text):
                        is_open = True
                        break

            # Handle close marker
            if is_close and pending_open is not None:
                # Close the current section
                section = {
                    "start_idx": pending_open["start_idx"],
                    "end_idx": i - 1,  # Exclude the close marker itself
                    "opener_idx": pending_open["opener_idx"],
                    "closer_idx": i,
                    "opener_speaker": pending_open["opener_speaker"],
                    "closer_speaker": utt.speaker,
                    "confidence": 0.9,  # High confidence with explicit close
                }
                # Only add if there's content between open and close
                if section["end_idx"] >= section["start_idx"]:
                    sections.append(section)
                pending_open = None

            # Handle open marker (might immediately follow a close)
            if is_open:
                # If there's a pending open without close, close it implicitly
                if pending_open is not None:
                    section = {
                        "start_idx": pending_open["start_idx"],
                        "end_idx": i - 1,  # End at utterance before this open
                        "opener_idx": pending_open["opener_idx"],
                        "closer_idx": None,  # No explicit close
                        "opener_speaker": pending_open["opener_speaker"],
                        "closer_speaker": None,
                        "confidence": 0.6,  # Lower confidence without explicit close
                    }
                    if section["end_idx"] >= section["start_idx"]:
                        sections.append(section)

                # Start tracking new section
                pending_open = {
                    "opener_idx": i,
                    "start_idx": i + 1,  # Section starts after the open marker
                    "opener_speaker": utt.speaker,
                }

        # Handle unclosed section at end of transcript
        if pending_open is not None and pending_open["start_idx"] < len(utterances):
            section = {
                "start_idx": pending_open["start_idx"],
                "end_idx": len(utterances) - 1,  # To end of transcript
                "opener_idx": pending_open["opener_idx"],
                "closer_idx": None,
                "opener_speaker": pending_open["opener_speaker"],
                "closer_speaker": None,
                "confidence": 0.5,  # Lower confidence for unclosed section
            }
            sections.append(section)

        # Store for later use
        self.public_comment_sections = [
            (s["start_idx"], s["end_idx"], s["opener_speaker"])
            for s in sections
        ]

        return sections

    def is_in_public_comment_section(self, utterance_idx: int) -> bool:
        """
        Check if an utterance is within a public comment section.

        Args:
            utterance_idx: Index of the utterance to check

        Returns:
            True if the utterance is within a detected public comment section
        """
        for start_idx, end_idx, _ in self.public_comment_sections:
            if start_idx <= utterance_idx <= end_idx:
                return True
        return False

    def get_public_comment_section(self, utterance_idx: int) -> int | None:
        """
        Get the index of the public comment section containing this utterance.

        Args:
            utterance_idx: Index of the utterance to check

        Returns:
            Section index (0-based) or None if not in a public comment section
        """
        for section_idx, (start_idx, end_idx, _) in enumerate(self.public_comment_sections):
            if start_idx <= utterance_idx <= end_idx:
                return section_idx
        return None


@dataclass
class PublicCommentSection:
    """Represents a detected public comment section in a meeting transcript."""
    section_id: int  # 0-based index of this section in the meeting
    start_idx: int  # First utterance index in the section (after open marker)
    end_idx: int  # Last utterance index in the section (before close marker)
    opener_idx: int  # Index of the utterance that opened the section
    closer_idx: int | None  # Index of the utterance that closed (None if implicit)
    opener_speaker: str  # Speaker who opened the section (usually council/staff)
    closer_speaker: str | None  # Speaker who closed the section
    confidence: float  # Detection confidence (0.0-1.0)
    speaker_count: int = 0  # Number of unique speakers in this section
    utterance_count: int = 0  # Number of utterances in this section

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "opener_idx": self.opener_idx,
            "closer_idx": self.closer_idx,
            "opener_speaker": self.opener_speaker,
            "closer_speaker": self.closer_speaker,
            "confidence": self.confidence,
            "speaker_count": self.speaker_count,
            "utterance_count": self.utterance_count,
        }


class TranscriptChunker:
    """
    Convert diarized transcripts into RAG-ready chunks.

    Chunking strategy:
    1. Group consecutive utterances from the same speaker into "turns"
    2. Combine turns until hitting max_chunk_size
    3. When speaker changes, start new chunk (unless very small)
    4. Preserve timestamps from first to last utterance in chunk
    5. Split very long utterances at sentence boundaries

    This preserves speaker continuity for attribution while creating
    chunks suitable for semantic search.
    """

    def __init__(
        self,
        max_chunk_size: int = 1500,
        min_chunk_size: int = 200,
        chunk_overlap: int = 0,  # Utterance overlap (not character)
    ):
        """
        Initialize chunker.

        Args:
            max_chunk_size: Maximum characters per chunk
            min_chunk_size: Minimum characters before splitting on speaker change
            chunk_overlap: Number of utterances to overlap between chunks (0 = no overlap)
        """
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.chunk_overlap = chunk_overlap

    def _split_long_utterance(self, utt: TranscriptUtterance) -> list[TranscriptUtterance]:
        """
        Split a long utterance into smaller pieces at sentence boundaries.

        Args:
            utt: Utterance to split

        Returns:
            List of smaller utterances (or single-item list if short enough)
        """
        text = utt.text
        if len(text) <= self.max_chunk_size:
            return [utt]

        # Split at sentence boundaries
        result = []
        duration_ms = utt.end_ms - utt.start_ms
        start_idx = 0

        while start_idx < len(text):
            end_idx = start_idx + self.max_chunk_size

            if end_idx >= len(text):
                # Last piece - take remainder
                piece_text = text[start_idx:].strip()
                if piece_text:
                    # Calculate proportional timestamps
                    piece_start_ms = utt.start_ms + int(duration_ms * start_idx / len(text))
                    piece_end_ms = utt.end_ms
                    result.append(TranscriptUtterance(
                        speaker=utt.speaker,
                        text=piece_text,
                        start_ms=piece_start_ms,
                        end_ms=piece_end_ms,
                    ))
                break

            # Look for sentence boundary in the last 300 characters
            search_start = max(start_idx, end_idx - 300)
            search_region = text[search_start:end_idx]

            # Try to break at sentence end
            best_break = -1
            for pattern in ['. ', '.\n', '! ', '? ']:
                pos = search_region.rfind(pattern)
                if pos > best_break:
                    best_break = pos

            if best_break > 50:  # Found good break point
                end_idx = search_start + best_break + 1
            else:
                # Fall back to comma or space
                for pattern in [', ', ' ']:
                    pos = search_region.rfind(pattern)
                    if pos > 50:
                        end_idx = search_start + pos + 1
                        break

            piece_text = text[start_idx:end_idx].strip()
            if piece_text:
                # Calculate proportional timestamps
                piece_start_ms = utt.start_ms + int(duration_ms * start_idx / len(text))
                piece_end_ms = utt.start_ms + int(duration_ms * end_idx / len(text))
                result.append(TranscriptUtterance(
                    speaker=utt.speaker,
                    text=piece_text,
                    start_ms=piece_start_ms,
                    end_ms=piece_end_ms,
                ))

            start_idx = end_idx

        return result if result else [utt]

    def load_transcript(self, path: str | Path) -> list[TranscriptUtterance]:
        """
        Load utterances from an AssemblyAI transcript JSON file.

        Args:
            path: Path to transcript JSON file

        Returns:
            List of TranscriptUtterance objects
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Transcript not found: {path}")

        with open(path) as f:
            data = json.load(f)

        return self.parse_utterances(data)

    def parse_utterances(self, data: dict) -> list[TranscriptUtterance]:
        """
        Parse utterances from transcript data.

        Args:
            data: Transcript dictionary with 'utterances' key

        Returns:
            List of TranscriptUtterance objects
        """
        utterances = []

        for utt in data.get("utterances", []):
            utterances.append(TranscriptUtterance(
                speaker=utt.get("speaker", "?"),
                text=utt.get("text", "").strip(),
                start_ms=utt.get("start", 0),
                end_ms=utt.get("end", 0),
            ))

        return utterances

    def chunk(
        self,
        utterances: list[TranscriptUtterance],
        source_metadata: dict | None = None,
        detect_speaker_roles: bool = True,
        detect_agenda_items: bool = True,
        llm_provider: "LLMProvider | None" = None,
        precomputed_speaker_info: dict | None = None,
    ) -> list[TranscriptChunk]:
        """
        Convert utterances into semantic chunks.

        Args:
            utterances: List of utterances to chunk
            source_metadata: Additional metadata for all chunks
            detect_speaker_roles: If True, detect and include speaker roles
            detect_agenda_items: If True, detect and include agenda item alignment
            llm_provider: Optional LLM provider for enhanced speaker/name detection
            precomputed_speaker_info: Optional pre-computed speaker metadata from
                transcription time (SESSION 530). Format: {"A": {"name": "...", "role": "..."}}

        Returns:
            List of TranscriptChunk objects
        """
        if not utterances:
            return []

        # Use pre-computed speaker info if available, otherwise detect
        speaker_info: dict[str, SpeakerInfo] = {}
        public_comment_sections: list[tuple[int, int, str]] = []

        if precomputed_speaker_info:
            # SESSION 530: Convert pre-computed dict format to SpeakerInfo objects
            for speaker_id, info in precomputed_speaker_info.items():
                speaker_info[speaker_id] = SpeakerInfo(
                    speaker_id=speaker_id,
                    role=info.get("role", "unknown"),
                    name=info.get("name"),
                    title=info.get("title"),
                    confidence=info.get("confidence", 0.8),
                )
        elif detect_speaker_roles:
            detector = SpeakerRoleDetector(llm_provider=llm_provider)
            speaker_info = detector.detect_roles(utterances)
            public_comment_sections = detector.public_comment_sections

        # Detect agenda item spans if requested
        agenda_item_spans: list[AgendaItemSpan] = []
        if detect_agenda_items:
            aligner = AgendaItemAligner()
            agenda_item_spans = aligner.detect_agenda_items(utterances)
            logger.info(f"Detected {len(agenda_item_spans)} agenda item spans")

        chunks = list(self._generate_chunks(
            utterances,
            source_metadata or {},
            speaker_info,
            public_comment_sections,
            agenda_item_spans,
        ))

        # Set total_chunks on each
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks

    def chunk_file(
        self,
        path: str | Path,
        source_metadata: dict | None = None,
        detect_speaker_roles: bool = True,
        detect_agenda_items: bool = True,
        llm_provider: "LLMProvider | None" = None,
    ) -> list[TranscriptChunk]:
        """
        Load and chunk a transcript file.

        Args:
            path: Path to transcript JSON file
            source_metadata: Additional metadata for all chunks
            detect_speaker_roles: If True, detect and include speaker roles
            detect_agenda_items: If True, detect and include agenda item alignment
            llm_provider: Optional LLM provider for enhanced speaker/name detection

        Returns:
            List of TranscriptChunk objects
        """
        path = Path(path)
        utterances = self.load_transcript(path)

        metadata = source_metadata or {}
        metadata.setdefault("source_file", str(path))

        # Extract video_id from filename if present
        if "video_id" not in metadata and path.stem.startswith("testimony_"):
            metadata["video_id"] = path.stem.replace("testimony_", "")

        return self.chunk(
            utterances,
            metadata,
            detect_speaker_roles=detect_speaker_roles,
            detect_agenda_items=detect_agenda_items,
            llm_provider=llm_provider,
        )

    def _generate_chunks(
        self,
        utterances: list[TranscriptUtterance],
        base_metadata: dict,
        speaker_info: dict[str, SpeakerInfo] | None = None,
        public_comment_sections: list[tuple[int, int, str]] | None = None,
        agenda_item_spans: list["AgendaItemSpan"] | None = None,
    ) -> Iterator[TranscriptChunk]:
        """Generate chunks from utterances."""

        if not utterances:
            return

        speaker_info = speaker_info or {}
        public_comment_sections = public_comment_sections or []
        agenda_item_spans = agenda_item_spans or []

        # Build set of utterance indices in public comment sections for quick lookup
        public_comment_indices: dict[int, int] = {}  # utterance_idx -> section_id
        for section_id, (start_idx, end_idx, _) in enumerate(public_comment_sections):
            for idx in range(start_idx, end_idx + 1):
                public_comment_indices[idx] = section_id

        # Build agenda item lookup: utterance_idx -> AgendaItemSpan
        agenda_item_map: dict[int, AgendaItemSpan] = {}
        for span in agenda_item_spans:
            for idx in range(span.start_idx, span.end_idx + 1):
                agenda_item_map[idx] = span

        # Current chunk state
        current_utterances: list[TranscriptUtterance] = []
        current_original_indices: list[int] = []  # Track original utterance indices
        current_text_parts: list[str] = []
        current_length = 0
        chunk_index = 0

        def finalize_chunk() -> TranscriptChunk:
            """Create chunk from accumulated utterances."""
            nonlocal chunk_index

            # Determine primary speaker (most text)
            speaker_chars: dict[str, int] = {}
            for utt in current_utterances:
                speaker_chars[utt.speaker] = speaker_chars.get(utt.speaker, 0) + len(utt.text)

            speakers = list(speaker_chars.keys())
            if len(speakers) == 1:
                primary_speaker = speakers[0]
            else:
                # Most text wins
                primary_speaker = max(speaker_chars, key=speaker_chars.get)
                # If no clear winner, mark as multiple
                total_chars = sum(speaker_chars.values())
                if speaker_chars[primary_speaker] / total_chars < 0.7:
                    primary_speaker = "multiple"

            # Build text with speaker labels when speaker changes
            text_parts = []
            last_speaker = None
            for utt in current_utterances:
                if utt.speaker != last_speaker:
                    text_parts.append(f"[{utt.speaker}] {utt.text}")
                    last_speaker = utt.speaker
                else:
                    text_parts.append(utt.text)

            # Build chunk metadata including speaker info
            chunk_metadata = base_metadata.copy()

            # Add speaker role metadata for primary speaker
            if primary_speaker in speaker_info:
                info = speaker_info[primary_speaker]
                chunk_metadata["speaker_role"] = info.role
                chunk_metadata["speaker_name"] = info.name
                chunk_metadata["speaker_title"] = info.title
                chunk_metadata["role_confidence"] = info.confidence
            elif primary_speaker == "multiple":
                # For multiple speakers, aggregate roles
                roles = set()
                for spk in speakers:
                    if spk in speaker_info:
                        roles.add(speaker_info[spk].role)
                chunk_metadata["speaker_role"] = "multiple"
                chunk_metadata["speaker_roles"] = list(roles) if roles else ["unknown"]

            # Add per-speaker info for all speakers in this chunk
            if speaker_info:
                chunk_metadata["speakers_info"] = {
                    spk: speaker_info[spk].to_dict()
                    for spk in speakers
                    if spk in speaker_info
                }

            # Add public comment metadata
            # Check if any utterances in this chunk are from public comment sections
            section_ids = set()
            for orig_idx in current_original_indices:
                if orig_idx in public_comment_indices:
                    section_ids.add(public_comment_indices[orig_idx])

            if section_ids:
                chunk_metadata["is_public_comment"] = True
                # If all from same section, record the section ID
                if len(section_ids) == 1:
                    chunk_metadata["public_comment_section_id"] = list(section_ids)[0]
                else:
                    # Spans multiple sections (rare)
                    chunk_metadata["public_comment_section_ids"] = sorted(section_ids)
            else:
                chunk_metadata["is_public_comment"] = False

            # Add agenda item metadata
            # Check which agenda item(s) this chunk's utterances belong to
            item_numbers = set()
            for orig_idx in current_original_indices:
                if orig_idx in agenda_item_map:
                    item_numbers.add(agenda_item_map[orig_idx].item_number)

            if item_numbers:
                if len(item_numbers) == 1:
                    chunk_metadata["agenda_item"] = list(item_numbers)[0]
                else:
                    # Rare: chunk spans multiple agenda items (e.g., transition)
                    chunk_metadata["agenda_items"] = sorted(item_numbers)
            # Note: chunks before any detected item have no agenda_item field

            chunk = TranscriptChunk(
                text=" ".join(text_parts),
                speaker=primary_speaker,
                speakers=speakers,
                start_ms=current_utterances[0].start_ms,
                end_ms=current_utterances[-1].end_ms,
                chunk_index=chunk_index,
                total_chunks=0,  # Will be set later
                utterance_count=len(current_utterances),
                metadata=chunk_metadata,
            )
            chunk_index += 1
            return chunk

        # Pre-process: split any very long utterances
        # Track (utterance, original_index) pairs
        processed_utterances: list[tuple[TranscriptUtterance, int]] = []
        for orig_idx, utt in enumerate(utterances):
            if not utt.text.strip():
                continue
            if len(utt.text) > self.max_chunk_size:
                for split_utt in self._split_long_utterance(utt):
                    processed_utterances.append((split_utt, orig_idx))
            else:
                processed_utterances.append((utt, orig_idx))

        for i, (utt, orig_idx) in enumerate(processed_utterances):
            utt_length = len(utt.text) + 1  # +1 for space

            # Check if adding this utterance would exceed max size
            would_exceed = current_length + utt_length > self.max_chunk_size

            # Check for speaker change
            speaker_change = (
                current_utterances and
                utt.speaker != current_utterances[-1].speaker
            )

            # Determine if we should start a new chunk
            should_split = False

            if would_exceed and current_utterances:
                # Size limit reached
                should_split = True
            elif speaker_change and current_length >= self.min_chunk_size:
                # Speaker change and we have enough content
                should_split = True

            if should_split:
                yield finalize_chunk()
                current_utterances = []
                current_original_indices = []
                current_text_parts = []
                current_length = 0

                # Handle overlap (include last N utterances from previous chunk)
                if self.chunk_overlap > 0 and i >= self.chunk_overlap:
                    overlap_start = max(0, i - self.chunk_overlap)
                    for overlap_utt, overlap_orig_idx in processed_utterances[overlap_start:i]:
                        current_utterances.append(overlap_utt)
                        current_original_indices.append(overlap_orig_idx)
                        current_length += len(overlap_utt.text) + 1

            # Add utterance to current chunk
            current_utterances.append(utt)
            current_original_indices.append(orig_idx)
            current_text_parts.append(utt.text)
            current_length += utt_length

        # Don't forget the last chunk
        if current_utterances:
            yield finalize_chunk()


def chunk_transcript(
    transcript_path: str | Path,
    output_path: str | Path | None = None,
    max_chunk_size: int = 1500,
) -> list[dict]:
    """
    Convenience function to chunk a transcript file.

    Args:
        transcript_path: Path to AssemblyAI transcript JSON
        output_path: Optional path to write chunked output
        max_chunk_size: Maximum chunk size in characters

    Returns:
        List of chunk dictionaries
    """
    chunker = TranscriptChunker(max_chunk_size=max_chunk_size)
    chunks = chunker.chunk_file(transcript_path)
    result = [c.to_dict() for c in chunks]

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)

    return result


@dataclass
class AgendaItemSpan:
    """Represents a detected agenda item discussion span in the transcript."""
    item_number: str  # e.g., "4.a", "5A", "6"
    start_idx: int  # First utterance index
    end_idx: int  # Last utterance index
    start_ms: int  # Start timestamp in milliseconds
    end_ms: int  # End timestamp in milliseconds
    marker_idx: int  # Index of the utterance announcing this item
    marker_text: str  # Text that triggered detection
    confidence: float  # Detection confidence (0.0-1.0)

    @property
    def start_timestamp(self) -> str:
        """Human-readable start time (HH:MM:SS)."""
        total_seconds = self.start_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @property
    def end_timestamp(self) -> str:
        """Human-readable end time (HH:MM:SS)."""
        total_seconds = self.end_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict:
        return {
            "item_number": self.item_number,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "marker_idx": self.marker_idx,
            "marker_text": self.marker_text,
            "confidence": self.confidence,
        }


class AgendaItemAligner:
    """
    Detect agenda item transitions in meeting transcripts.

    Analyzes transcript utterances to identify when discussion moves between
    agenda items by detecting transition phrases like:
    - "Our next agenda item is 5A..."
    - "The next item..."
    - "Item 6.a..."
    - "Consent calendar items 4A through 4G"

    This enables linking transcript chunks to specific agenda items for
    better retrieval and video navigation.
    """

    # Patterns for detecting agenda item announcements
    # These are compiled regex patterns for performance
    _ITEM_PATTERNS = [
        # "item 5A" or "item 5.a" or "item 5-a" or "items 4A through 4G"
        # Note: only match letter suffix if immediately after number (no space)
        re.compile(
            r'\b(?:agenda\s+)?items?\s+(\d+(?:[.-]?[a-zA-Z])?)\b',
            re.IGNORECASE
        ),
        # "next agenda item is 5A"
        re.compile(
            r'(?:next|following)\s+(?:agenda\s+)?item\s+(?:is\s+)?(\d+(?:[.-]?[a-zA-Z])?)\b',
            re.IGNORECASE
        ),
        # "consent calendar" or "consent agenda"
        re.compile(r'\b(consent\s+(?:calendar|agenda))\b', re.IGNORECASE),
        # "public hearing" as distinct section
        re.compile(r'\b(public\s+hearing)\b', re.IGNORECASE),
        # "new business" or "old business"
        re.compile(r'\b((?:new|old|unfinished)\s+business)\b', re.IGNORECASE),
    ]

    # Patterns for transition phrases that indicate item changes
    _TRANSITION_PATTERNS = [
        re.compile(r'(?:our\s+)?next\s+(?:agenda\s+)?item', re.IGNORECASE),
        re.compile(r'move\s+(?:on\s+)?to\s+(?:the\s+)?(?:next\s+)?item', re.IGNORECASE),
        re.compile(r'that\s+(?:motion\s+)?carries.*(?:next|following)', re.IGNORECASE),
        re.compile(r'moving\s+(?:on\s+)?to', re.IGNORECASE),
    ]

    def __init__(self):
        """Initialize the aligner."""
        self.detected_spans: list[AgendaItemSpan] = []

    def detect_agenda_items(
        self,
        utterances: list[TranscriptUtterance],
    ) -> list[AgendaItemSpan]:
        """
        Detect agenda item transitions in transcript utterances.

        Args:
            utterances: List of transcript utterances with timestamps

        Returns:
            List of AgendaItemSpan objects representing detected item discussions
        """
        if not utterances:
            return []

        detected_markers: list[dict] = []
        current_item: str | None = None

        for i, utt in enumerate(utterances):
            text = utt.text

            # Check if this is a transition context (indicates actual item change)
            is_transition = any(
                p.search(text) for p in self._TRANSITION_PATTERNS
            )

            # Check for item number patterns
            for pattern in self._ITEM_PATTERNS:
                match = pattern.search(text)
                if match:
                    item_number = self._normalize_item_number(match.group(1))

                    # Only create a new marker if:
                    # 1. This is a transition phrase (high confidence item change)
                    # 2. OR this is a different item number than current
                    # 3. OR this is the first item detected
                    if is_transition or item_number != current_item or current_item is None:
                        confidence = 0.9 if is_transition else 0.7

                        detected_markers.append({
                            "idx": i,
                            "item_number": item_number,
                            "text": text[:200],  # Truncate for storage
                            "start_ms": utt.start_ms,
                            "confidence": confidence,
                        })
                        current_item = item_number
                    break  # Only detect first item in each utterance

        # Convert markers to spans (each span ends when next begins)
        spans = []
        for i, marker in enumerate(detected_markers):
            # Span starts at marker utterance
            start_idx = marker["idx"]
            start_ms = marker["start_ms"]

            # Span ends at next marker (or end of transcript)
            if i + 1 < len(detected_markers):
                end_idx = detected_markers[i + 1]["idx"] - 1
                end_ms = utterances[end_idx].end_ms
            else:
                end_idx = len(utterances) - 1
                end_ms = utterances[end_idx].end_ms

            # Only create span if it has content
            if end_idx >= start_idx:
                span = AgendaItemSpan(
                    item_number=marker["item_number"],
                    start_idx=start_idx,
                    end_idx=end_idx,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    marker_idx=marker["idx"],
                    marker_text=marker["text"],
                    confidence=marker["confidence"],
                )
                spans.append(span)

        self.detected_spans = spans
        return spans

    def _normalize_item_number(self, raw: str) -> str:
        """
        Normalize item number to consistent format.

        Converts variants like "5A", "5.a", "5-a" to "5.a" format.
        Handles special items like "consent calendar" -> "consent".

        Args:
            raw: Raw matched item number string

        Returns:
            Normalized item number
        """
        raw = raw.strip().lower()

        # Handle special section names
        if "consent" in raw:
            return "consent"
        if "public hearing" in raw:
            return "public_hearing"
        if "business" in raw:
            return raw.replace(" ", "_")

        # Normalize numbered items: "5A" or "5.a" or "5-a" -> "5.a"
        # Remove spaces and dashes
        normalized = re.sub(r'[\s-]+', '', raw)

        # If format is "5a", insert dot -> "5.a"
        match = re.match(r'^(\d+)([a-z])$', normalized)
        if match:
            return f"{match.group(1)}.{match.group(2)}"

        return normalized

    def get_item_for_utterance(self, utterance_idx: int) -> str | None:
        """
        Get the agenda item number for a given utterance index.

        Args:
            utterance_idx: Index of the utterance

        Returns:
            Item number string or None if not within a detected span
        """
        for span in self.detected_spans:
            if span.start_idx <= utterance_idx <= span.end_idx:
                return span.item_number
        return None

    def get_span_for_utterance(self, utterance_idx: int) -> AgendaItemSpan | None:
        """
        Get the full AgendaItemSpan for a given utterance index.

        Args:
            utterance_idx: Index of the utterance

        Returns:
            AgendaItemSpan or None if not within a detected span
        """
        for span in self.detected_spans:
            if span.start_idx <= utterance_idx <= span.end_idx:
                return span
        return None


def expand_transcripts_to_chunks(
    transcripts: list[dict],
    max_chunk_size: int = 1500,
    min_chunk_size: int = 200,
) -> list[dict]:
    """
    Expand transcripts into semantic chunks for embedding.

    This is the canonical function for chunking transcripts before vector indexing.
    It uses TranscriptChunker to create appropriately-sized chunks that preserve
    speaker attribution and timestamps.

    Args:
        transcripts: List of transcript dicts from storage backend (via get_transcripts)
        max_chunk_size: Maximum characters per chunk (default 1500)
        min_chunk_size: Minimum chars before splitting on speaker change

    Returns:
        List of chunk dicts ready for indexing, each containing:
        - id: "transcript-{video_id}-{chunk_index}"
        - text: Chunk text with speaker context
        - video_id, speaker, timestamps, metadata
    """
    chunker = TranscriptChunker(
        max_chunk_size=max_chunk_size,
        min_chunk_size=min_chunk_size,
        chunk_overlap=1,
    )

    all_chunks = []

    for transcript in transcripts:
        video_id = transcript.get("video_id", "")
        if not video_id:
            continue

        # Get utterances from transcript JSONB field
        transcript_data = transcript.get("transcript", {})
        if isinstance(transcript_data, str):
            try:
                transcript_data = json.loads(transcript_data)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse transcript JSON for {video_id}")
                continue

        utterances_data = transcript_data.get("utterances", [])
        if not utterances_data:
            logger.warning(f"No utterances found in transcript {video_id}")
            continue

        # SESSION 530: Check for pre-computed speakers_metadata (from transcription time)
        speakers_metadata = transcript_data.get("speakers_metadata", {})

        # Parse utterances and chunk
        utterances = chunker.parse_utterances({"utterances": utterances_data})
        if not utterances:
            continue

        # Chunk with speaker role detection
        # Skip detection if we have pre-computed speakers_metadata
        chunks = chunker.chunk(
            utterances,
            detect_speaker_roles=not speakers_metadata,  # Skip if pre-computed
            detect_agenda_items=False,
            precomputed_speaker_info=speakers_metadata,  # Pass pre-computed data
        )

        # Convert to indexable format matching ChromaDB/pgvector schema
        for chunk in chunks:
            chunk_metadata = chunk.metadata or {}
            chunk_dict = {
                "id": f"transcript-{video_id}-{chunk.chunk_index}",
                "text": chunk.to_embedding_text(),
                "video_id": video_id,
                "speaker": chunk.speaker,
                "speakers": chunk.speakers,
                "start_ms": chunk.start_ms,
                "end_ms": chunk.end_ms,
                "start_timestamp": chunk.start_timestamp,
                "end_timestamp": chunk.end_timestamp,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "utterance_count": chunk.utterance_count,
                # Speaker role metadata
                "speaker_role": chunk_metadata.get("speaker_role"),
                "speaker_name": chunk_metadata.get("speaker_name"),
                "role_confidence": chunk_metadata.get("role_confidence"),
                "is_public_comment": chunk_metadata.get("is_public_comment", False),
            }
            all_chunks.append(chunk_dict)

        logger.debug(
            f"Chunked transcript {video_id}: {len(chunks)} chunks "
            f"from {len(utterances)} utterances"
        )

    logger.info(
        f"Expanded {len(transcripts)} transcripts into {len(all_chunks)} chunks"
    )
    return all_chunks
