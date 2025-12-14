"""
City council meeting minutes extraction.

Extracts structured data from official meeting minutes including:
- Attendance (present/absent members)
- Agenda items and actions
- Voting records
- Public comment speakers
- Resolution/Ordinance numbers

Important context: Official minutes are summaries, NOT verbatim transcripts.
They capture WHO spoke but rarely WHAT was said. For full content,
video transcripts are needed.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re
import json

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


@dataclass
class VoteRecord:
    """A recorded vote on an agenda item."""

    motion_by: Optional[str]
    second_by: Optional[str]
    ayes: list[str]
    noes: list[str]
    absent: list[str]
    outcome: str  # "adopted", "approved", "failed", etc.
    resolution_number: Optional[str] = None
    ordinance_number: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "motion_by": self.motion_by,
            "second_by": self.second_by,
            "ayes": self.ayes,
            "noes": self.noes,
            "absent": self.absent,
            "outcome": self.outcome,
            "resolution_number": self.resolution_number,
            "ordinance_number": self.ordinance_number,
        }


@dataclass
class AgendaItemMinutes:
    """Minutes record for a single agenda item."""

    item_number: str  # e.g., "6.a"
    title: str
    description: str
    presenters: list[str]
    public_speakers: list[str]
    votes: list[VoteRecord]
    summary_notes: str  # Any additional notes in minutes

    def to_dict(self) -> dict:
        return {
            "item_number": self.item_number,
            "title": self.title,
            "description": self.description,
            "presenters": self.presenters,
            "public_speakers": self.public_speakers,
            "votes": [v.to_dict() for v in self.votes],
            "summary_notes": self.summary_notes,
        }


@dataclass
class MeetingMinutes:
    """Complete minutes for a city council meeting."""

    meeting_type: str  # "regular", "special"
    meeting_date: str  # ISO date
    meeting_time: str
    location: str

    # Attendance
    present: list[str]
    absent: list[str]
    also_present: list[str]  # Staff

    # Time markers
    called_to_order: Optional[str]
    adjourned: Optional[str]
    recesses: list[str]

    # Content
    items: list[AgendaItemMinutes]

    # Public expression (end of meeting)
    public_expression_speakers: list[str]

    # Metadata
    source_file: Optional[str] = None
    approval_status: str = "pending"  # "pending", "approved"

    def to_dict(self) -> dict:
        return {
            "meeting_type": self.meeting_type,
            "meeting_date": self.meeting_date,
            "meeting_time": self.meeting_time,
            "location": self.location,
            "present": self.present,
            "absent": self.absent,
            "also_present": self.also_present,
            "called_to_order": self.called_to_order,
            "adjourned": self.adjourned,
            "recesses": self.recesses,
            "items": [item.to_dict() for item in self.items],
            "public_expression_speakers": self.public_expression_speakers,
            "source_file": self.source_file,
            "approval_status": self.approval_status,
        }


class MinutesExtractor:
    """
    Extract structured data from city council meeting minutes PDFs.

    San Rafael minutes follow a consistent format:
    - Header with meeting date/time/location
    - Attendance (Present, Absent, Also Present)
    - Consent Calendar items with votes
    - Other Agenda Items with presenter notes and votes
    - Public Hearings with extensive speaker lists
    - Open Time for Public Expression
    - Adjournment
    """

    # Patterns for parsing
    PATTERNS = {
        "meeting_date": re.compile(
            r'SAN\s+RAFAEL\s+CITY\s+COUNCIL.*?([A-Z]+DAY,?\s+[A-Z]+\s+\d+,?\s+\d{4})',
            re.IGNORECASE | re.DOTALL
        ),
        "meeting_type": re.compile(
            r'(REGULAR|SPECIAL)\s+MEETING',
            re.IGNORECASE
        ),
        "meeting_time": re.compile(
            r'(?:MEETING\s+)?AT\s+(\d+:\d+\s*[AP]\.?M\.?)',
            re.IGNORECASE
        ),
        "present": re.compile(
            r'Present:\s*(.*?)(?=Absent:|Also\s+Present:|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "absent": re.compile(
            r'Absent:\s*(.*?)(?=Also\s+Present:|Present:|City\s+Manager|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "also_present": re.compile(
            r'Also\s+Present:\s*(.*?)(?=Mayor|City\s+Council|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "called_to_order": re.compile(
            r'called\s+the\s+meeting\s+to\s+order\s+at\s+(\d+:\d+\s*[ap]\.?m\.?)',
            re.IGNORECASE
        ),
        "adjourned": re.compile(
            r'adjourned\s+the\s+meeting\s+at\s+(\d+:\d+\s*[ap]\.?m\.?)',
            re.IGNORECASE
        ),
        "recess": re.compile(
            r'called\s+a\s+recess\s+at\s+(\d+:\d+\s*[ap]\.?m\.?)',
            re.IGNORECASE
        ),
        "agenda_item": re.compile(
            r'^(\d+)\.\s*([^\n]+)',
            re.MULTILINE
        ),
        "sub_item": re.compile(
            r'^([a-z])\.\s*([^\n]+)',
            re.MULTILINE
        ),
        "speakers": re.compile(
            r'Speakers?:\s*([^\n]+(?:\n[^\n]+)*?)(?=\n\n|Staff\s+responded|Mayor|Vice\s+Mayor|Council)',
            re.IGNORECASE
        ),
        "presenter": re.compile(
            r'(City\s+Manager|City\s+Attorney|City\s+Clerk|Assistant\s+City\s+Manager|Director|Chief|Captain)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+presented',
            re.IGNORECASE
        ),
        "motion": re.compile(
            r'(Vice\s+Mayor\s+\w+|Councilmember\s+\w+|Mayor\s+\w+)\s+moved\s+and\s+'
            r'(Vice\s+Mayor\s+\w+|Councilmember\s+\w+|Mayor\s+\w+)\s+seconded',
            re.IGNORECASE
        ),
        "vote_ayes": re.compile(
            r'AYES:\s*Councilmembers?:\s*([^\n]+)',
            re.IGNORECASE
        ),
        "vote_noes": re.compile(
            r'NOES:\s*Councilmembers?:\s*([^\n]+)',
            re.IGNORECASE
        ),
        "vote_absent": re.compile(
            r'ABSENT:\s*Councilmembers?:\s*([^\n]+)',
            re.IGNORECASE
        ),
        "resolution": re.compile(
            r'(?:Adopted\s+)?Resolution\s+(\d+)',
            re.IGNORECASE
        ),
        "ordinance": re.compile(
            r'(?:Adopted\s+)?(?:Urgency\s+)?Ordinance\s+(\d+)',
            re.IGNORECASE
        ),
    }

    def __init__(self):
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is required for PDF extraction")

    def extract(self, pdf_path: str | Path) -> MeetingMinutes:
        """
        Extract meeting minutes from a PDF.

        Args:
            pdf_path: Path to the minutes PDF

        Returns:
            MeetingMinutes with all extracted data
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"Minutes PDF not found: {pdf_path}")

        # Extract all text
        doc = fitz.open(str(pdf_path))
        try:
            full_text = "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()

        # Parse components
        meeting_date = self._extract_meeting_date(full_text)
        meeting_type = self._extract_meeting_type(full_text)
        meeting_time = self._extract_meeting_time(full_text)
        location = self._extract_location(full_text)

        present, absent, also_present = self._extract_attendance(full_text)
        called_to_order = self._extract_called_to_order(full_text)
        adjourned = self._extract_adjourned(full_text)
        recesses = self._extract_recesses(full_text)

        items = self._extract_agenda_items(full_text)
        public_expression = self._extract_public_expression(full_text)
        approval_status = self._extract_approval_status(full_text)

        return MeetingMinutes(
            meeting_type=meeting_type,
            meeting_date=meeting_date,
            meeting_time=meeting_time,
            location=location,
            present=present,
            absent=absent,
            also_present=also_present,
            called_to_order=called_to_order,
            adjourned=adjourned,
            recesses=recesses,
            items=items,
            public_expression_speakers=public_expression,
            source_file=str(pdf_path),
            approval_status=approval_status,
        )

    def _extract_meeting_date(self, text: str) -> str:
        """Extract meeting date."""
        if match := self.PATTERNS["meeting_date"].search(text):
            return match.group(1).strip()
        return ""

    def _extract_meeting_type(self, text: str) -> str:
        """Extract meeting type (regular/special)."""
        if match := self.PATTERNS["meeting_type"].search(text):
            return match.group(1).lower()
        return "regular"

    def _extract_meeting_time(self, text: str) -> str:
        """Extract meeting start time."""
        if match := self.PATTERNS["meeting_time"].search(text):
            return match.group(1).strip()
        return ""

    def _extract_location(self, text: str) -> str:
        """Extract meeting location."""
        # Look for location after meeting time
        match = re.search(
            r'(?:MEETING.*?\n)([A-Z][^\n]+(?:Chambers|Room|Center)[^\n]*)',
            text,
            re.IGNORECASE
        )
        if match:
            return match.group(1).strip()
        return "San Rafael City Hall"

    def _extract_attendance(self, text: str) -> tuple[list[str], list[str], list[str]]:
        """Extract present, absent, and also present members."""
        present = []
        absent = []
        also_present = []

        # Extract present members
        if match := self.PATTERNS["present"].search(text):
            present = self._parse_names(match.group(1))

        # Extract absent members
        if match := self.PATTERNS["absent"].search(text):
            absent = self._parse_names(match.group(1))

        # Extract staff present
        if match := self.PATTERNS["also_present"].search(text):
            also_present = self._parse_staff_names(match.group(1))

        return present, absent, also_present

    def _parse_names(self, text: str) -> list[str]:
        """Parse a list of council member names."""
        names = []
        # Remove titles and clean
        text = re.sub(r'\s+', ' ', text)

        # Look for names with titles
        patterns = [
            r'Mayor\s+(\w+)',
            r'Vice\s+Mayor\s+(\w+)',
            r'Councilmember\s+(\w+(?:\s+\w+)?)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                name = match.group(1).strip()
                if name.lower() not in ('none', 'absent'):
                    # Preserve title for clarity
                    full_match = match.group(0).strip()
                    if full_match not in names:
                        names.append(full_match)

        return names

    def _parse_staff_names(self, text: str) -> list[str]:
        """Parse staff names with titles."""
        staff = []
        # Pattern for "Title Name"
        pattern = r'(City\s+(?:Manager|Attorney|Clerk)|Assistant\s+City\s+Manager|Director|Chief)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'

        for match in re.finditer(pattern, text, re.IGNORECASE):
            title = match.group(1).strip()
            name = match.group(2).strip()
            staff.append(f"{title} {name}")

        return staff

    def _extract_called_to_order(self, text: str) -> Optional[str]:
        """Extract when meeting was called to order."""
        if match := self.PATTERNS["called_to_order"].search(text):
            return match.group(1).strip()
        return None

    def _extract_adjourned(self, text: str) -> Optional[str]:
        """Extract when meeting was adjourned."""
        if match := self.PATTERNS["adjourned"].search(text):
            return match.group(1).strip()
        return None

    def _extract_recesses(self, text: str) -> list[str]:
        """Extract recess times."""
        recesses = []
        for match in self.PATTERNS["recess"].finditer(text):
            recesses.append(match.group(1).strip())
        return recesses

    def _extract_agenda_items(self, text: str) -> list[AgendaItemMinutes]:
        """
        Extract all agenda items with their details.

        NOTE: This implementation is San Rafael-specific. It assumes:
        - Section headers: CONSENT CALENDAR, OTHER AGENDA ITEMS, PUBLIC HEARINGS
        - Vote format: AYES/NOES/ABSENT: Councilmembers:
        - Speaker lists after "Speakers:" keyword

        For multi-city scaling, see integration.json generalized_extraction section
        for planned LLM-based extraction approach.
        """
        items = []

        # Define major section boundaries (San Rafael format)
        section_markers = [
            (r'CONSENT\s+CALENDAR', 'consent'),
            (r'OTHER\s+AGENDA\s+ITEMS', 'other'),
            (r'PUBLIC\s+HEARINGS?', 'hearing'),
            (r'OPEN\s+TIME\s+FOR\s+PUBLIC\s+EXPRESSION', 'expression'),
            (r'ADJOURNMENT', 'end'),
        ]

        # Find section boundaries (take first match per type to avoid header duplicates)
        boundaries = []
        seen_types = set()
        all_matches = []
        for pattern, section_type in section_markers:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                all_matches.append((match.start(), section_type))

        # Sort by position and deduplicate by type (keeping first occurrence)
        all_matches.sort(key=lambda x: x[0])
        for pos, section_type in all_matches:
            if section_type not in seen_types:
                boundaries.append((pos, section_type))
                seen_types.add(section_type)

        # Process each section
        for i, (start, section_type) in enumerate(boundaries):
            if section_type in ('expression', 'end'):
                continue

            # Find end of this section
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            section_text = text[start:end]

            # Parse items in this section
            section_items = self._parse_section(section_text, section_type)
            items.extend(section_items)

        return items

    def _parse_section(self, section_text: str, section_type: str) -> list[AgendaItemMinutes]:
        """Parse items from a section of the minutes (San Rafael format)."""
        items = []

        # Get the main item number (e.g., 4 for Consent Calendar, 6 for Public Hearings)
        # Look for standalone number followed by period at start of line
        # Pattern: digit followed by period and either space/newline or "Consent/Other/Public"
        main_item_match = re.search(
            r'^\s*(\d)\.\s*(?:Consent|Other|Public|$)',
            section_text,
            re.MULTILINE | re.IGNORECASE
        )
        current_main_item = main_item_match.group(1) if main_item_match else ""

        # Find sub-items - look for pattern: "\na. Title"
        # Exclude single letters that could be roman numerals (i, v, x, l, c, d, m)
        # In San Rafael format, these appear as sub-descriptions (i., ii., iii., iv., v.)
        # Use finditer to get positions, not split (which loses context)
        sub_item_pattern = re.compile(r'\n([a-hj-uw-z])\.\s+([^\n]+)')
        sub_items = list(sub_item_pattern.finditer(section_text))

        for i, match in enumerate(sub_items):
            letter = match.group(1)
            title = match.group(2).strip()
            item_number = f"{current_main_item}.{letter}" if current_main_item else letter

            # Get text for this sub-item (until next sub-item or end)
            start = match.start()
            end = sub_items[i + 1].start() if i + 1 < len(sub_items) else len(section_text)
            sub_text = section_text[start:end]

            # Extract details
            presenters = self._extract_presenters(sub_text)
            speakers = self._extract_speakers(sub_text)
            votes = self._extract_votes(sub_text)
            description = self._extract_description(sub_text, title)
            summary = self._extract_summary_notes(sub_text)

            if title or presenters or speakers or votes:
                items.append(AgendaItemMinutes(
                    item_number=item_number,
                    title=title,
                    description=description,
                    presenters=presenters,
                    public_speakers=speakers,
                    votes=votes,
                    summary_notes=summary,
                ))

        return items

    def _extract_presenters(self, text: str) -> list[str]:
        """Extract staff presenters for an item."""
        presenters = []

        # Pattern: "Title Name presented"
        pattern = r'((?:City\s+)?(?:Manager|Attorney|Clerk|Director|Chief|Captain)(?:\s+\w+)?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+presented'

        for match in re.finditer(pattern, text, re.IGNORECASE):
            title = match.group(1).strip()
            name = match.group(2).strip()
            presenters.append(f"{title} {name}")

        # Also check for "presented the Staff Report along with..."
        pattern2 = r'along\s+with\s+(.*?)(?:\.|\n)'
        if match := re.search(pattern2, text, re.IGNORECASE):
            additional = match.group(1)
            # Parse additional presenters
            for name_match in re.finditer(r"([A-Z][a-z]+(?:'s)?\s+(?:Mental\s+Health\s+)?(?:Liaison\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", additional):
                presenters.append(name_match.group(1).strip())

        return presenters

    def _extract_speakers(self, text: str) -> list[str]:
        """Extract public comment speakers."""
        speakers = []

        if match := self.PATTERNS["speakers"].search(text):
            speaker_text = match.group(1)

            # Clean up: remove trailing "Mayor Kate closed public comment" and similar
            speaker_text = re.sub(
                r'\s*(Mayor|Vice\s+Mayor)\s+\w+\s+(closed|invited).*$',
                '',
                speaker_text,
                flags=re.IGNORECASE
            )

            # Split by comma, accounting for affiliations
            # Handle "Name, Organization" patterns
            raw_speakers = re.split(r',\s*(?=[A-Z])', speaker_text)

            for speaker in raw_speakers:
                speaker = speaker.strip()
                # Skip empty or "there was none"
                if speaker and 'none' not in speaker.lower():
                    # Clean up multi-line entries
                    speaker = re.sub(r'\s+', ' ', speaker)
                    speakers.append(speaker)

        return speakers

    def _extract_votes(self, text: str) -> list[VoteRecord]:
        """Extract voting records from text."""
        votes = []

        # Find motion patterns
        motions = list(self.PATTERNS["motion"].finditer(text))

        for i, motion in enumerate(motions):
            motion_by = motion.group(1).strip()
            second_by = motion.group(2).strip()

            # Find vote block after this motion
            # Pattern: AYES:...NOES:...ABSENT:... followed by resolution/ordinance or next motion
            after_motion = text[motion.end():]

            # Extract the complete vote record (AYES through ABSENT)
            vote_match = re.search(
                r'(AYES:\s*\n?\s*Councilmembers?:\s*\n?\s*[^\n]+\s*'
                r'NOES:\s*\n?\s*Councilmembers?:\s*\n?\s*[^\n]+\s*'
                r'ABSENT:\s*\n?\s*Councilmembers?:\s*\n?\s*[^\n]+)',
                after_motion,
                re.IGNORECASE | re.DOTALL
            )
            vote_text = vote_match.group(1) if vote_match else ""

            if vote_text:
                ayes = self._parse_vote_names(vote_text, "AYES")
                noes = self._parse_vote_names(vote_text, "NOES")
                absent = self._parse_vote_names(vote_text, "ABSENT")

                # Determine outcome
                outcome = "adopted"
                if len(noes) > len(ayes):
                    outcome = "failed"

                # Look for resolution/ordinance number after vote
                resolution = None
                ordinance = None

                # Search in text after the vote
                search_start = motion.end()
                search_end = min(search_start + 500, len(text))
                after_text = text[search_start:search_end]

                if res_match := self.PATTERNS["resolution"].search(after_text):
                    resolution = res_match.group(1)
                if ord_match := self.PATTERNS["ordinance"].search(after_text):
                    ordinance = ord_match.group(1)

                votes.append(VoteRecord(
                    motion_by=motion_by,
                    second_by=second_by,
                    ayes=ayes,
                    noes=noes,
                    absent=absent,
                    outcome=outcome,
                    resolution_number=resolution,
                    ordinance_number=ordinance,
                ))

        return votes

    def _parse_vote_names(self, text: str, vote_type: str) -> list[str]:
        """Parse names from a vote line (handles multiline format)."""
        # Pattern handles newlines between "AYES:" and "Councilmembers:" and names
        pattern = rf'{vote_type}:\s*\n?\s*Councilmembers?:\s*\n?\s*([^\n]+)'
        if match := re.search(pattern, text, re.IGNORECASE):
            names_text = match.group(1).strip()
            if 'none' in names_text.lower():
                return []
            # Split by comma or &
            names = re.split(r'[,&]', names_text)
            return [n.strip() for n in names if n.strip()]
        return []

    def _extract_description(self, text: str, title: str) -> str:
        """Extract item description following the title."""
        # Look for text between title and next major section
        pattern = rf'{re.escape(title[:50])}[^\n]*\n(.*?)(?=presented|Speakers|Mayor|Vice|Council|\n\n)'
        if match := re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return match.group(1).strip()[:500]
        return ""

    def _extract_summary_notes(self, text: str) -> str:
        """Extract any summary notes (what was done with the item)."""
        notes = []

        # Look for outcome phrases
        patterns = [
            r'Approved\s+([^\n]+)',
            r'Adopted\s+([^\n]+)',
            r'Accepted\s+([^\n]+)',
            r'Received\s+and\s+filed',
            r'Introduced\s+the\s+Ordinance',
            r'Waived\s+further\s+reading',
        ]

        for pattern in patterns:
            if match := re.search(pattern, text, re.IGNORECASE):
                notes.append(match.group(0).strip())

        return "; ".join(notes)

    def _extract_public_expression(self, text: str) -> list[str]:
        """Extract speakers from Open Time for Public Expression."""
        speakers = []

        # Find the public expression section
        if match := re.search(
            r'OPEN\s+TIME\s+FOR\s+PUBLIC\s+EXPRESSION(.*?)(?=ADJOURNMENT|$)',
            text,
            re.IGNORECASE | re.DOTALL
        ):
            section = match.group(1)
            # Look for bullet points or speaker lines
            for line in section.split('\n'):
                if line.strip().startswith('•') or 'addressed the City Council' in line:
                    # Extract speaker name
                    if name_match := re.search(r'[•\s]*([A-Z][a-z]+(?:\s+[A-Za-z]+)?)\s+addressed', line):
                        speakers.append(name_match.group(1).strip())
                    elif name_match := re.search(r'[•\s]*Name\s+withheld', line, re.IGNORECASE):
                        speakers.append("Name withheld")

        return speakers

    def _extract_approval_status(self, text: str) -> str:
        """Determine if minutes are approved or pending."""
        if 'subject to approval' in text.lower():
            return "pending"
        return "approved"


def extract_meeting_minutes(
    pdf_path: str | Path,
    output_file: str | Path | None = None,
) -> dict:
    """
    Convenience function to extract meeting minutes.

    Args:
        pdf_path: Path to minutes PDF
        output_file: Optional path to write JSON output

    Returns:
        Dictionary with extracted minutes data
    """
    extractor = MinutesExtractor()
    minutes = extractor.extract(pdf_path)
    result = minutes.to_dict()

    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

    return result
