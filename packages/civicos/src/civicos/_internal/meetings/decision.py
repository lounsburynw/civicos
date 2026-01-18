"""
City council decision extraction.

Consolidates data from minutes, staff reports, and ordinances into
unified "Decision" records that represent what the council actually decided.

A Decision captures:
- What was decided (outcome, resolution/ordinance numbers)
- How it was decided (vote breakdown, motion/second)
- Why it was decided (staff recommendation, public input)
- What it means (legal authority, effective dates)

This is the key output for what_happened() queries - users want to know
what the council decided, not just what documents exist.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
import json
import re


@dataclass
class VoteTally:
    """Vote breakdown for a decision."""

    ayes: list[str]
    noes: list[str]
    absent: list[str]
    motion_by: Optional[str] = None
    second_by: Optional[str] = None

    @property
    def passed(self) -> bool:
        """Did the motion pass?"""
        return len(self.ayes) > len(self.noes)

    @property
    def unanimous(self) -> bool:
        """Was the vote unanimous (among those present)?"""
        return len(self.noes) == 0 and len(self.ayes) > 0

    @property
    def vote_count(self) -> str:
        """Human-readable vote count (e.g., '4-0')."""
        return f"{len(self.ayes)}-{len(self.noes)}"

    def to_dict(self) -> dict:
        return {
            "ayes": self.ayes,
            "noes": self.noes,
            "absent": self.absent,
            "motion_by": self.motion_by,
            "second_by": self.second_by,
            "passed": self.passed,
            "unanimous": self.unanimous,
            "vote_count": self.vote_count,
        }

    def to_vote_results(self) -> dict[str, str]:
        """
        Convert to vote_results format: {"Name": "yes/no/absent"}.

        This is the format expected by the decisions table vote_results field.
        """
        result = {}
        for name in self.ayes:
            result[name] = "yes"
        for name in self.noes:
            result[name] = "no"
        for name in self.absent:
            result[name] = "absent"
        return result


def extract_roll_call(text: str) -> dict[str, list[str]]:
    """
    Extract roll call vote from meeting minutes text.

    Parses patterns like:
        AYES: Councilmembers: Bushey, Hill, Kertz & Mayor Kate
        NOES: Councilmembers: None
        ABSENT: Councilmembers: Llorens Gulati

    Args:
        text: Decision text or motion text from minutes

    Returns:
        {"ayes": ["Bushey", "Hill", "Kertz", "Kate"],
         "noes": [],
         "absent": ["Llorens Gulati"]}
    """
    result = {"ayes": [], "noes": [], "absent": []}

    # Normalize text: handle line breaks, extra spaces
    text = re.sub(r'\s+', ' ', text)

    # Pattern for AYES section - capture until NOES or end
    ayes_match = re.search(
        r'AYES:?\s*(?:Councilmembers?:?)?\s*(.+?)(?=NOES:|ABSENT:|$)',
        text,
        re.IGNORECASE
    )
    if ayes_match:
        result["ayes"] = _parse_names(ayes_match.group(1))

    # Pattern for NOES section - capture until ABSENT or end
    noes_match = re.search(
        r'NOES:?\s*(?:Councilmembers?:?)?\s*(.+?)(?=ABSENT:|$)',
        text,
        re.IGNORECASE
    )
    if noes_match:
        result["noes"] = _parse_names(noes_match.group(1))

    # Pattern for ABSENT section - capture until end of vote block
    # Stop at: numbered items, "Also Present", "Adopted", "Mayor", next section headers
    absent_match = re.search(
        r'ABSENT:?\s*(?:Councilmembers?:?)?\s*(.+?)(?=\d+\.|Also\s+Present|Adopted|Mayor\s+\w+\s+(?:adjourned|called)|[A-Z][a-z]+\s+moved|$)',
        text,
        re.IGNORECASE
    )
    if absent_match:
        result["absent"] = _parse_names(absent_match.group(1))

    return result


def _parse_names(names_text: str) -> list[str]:
    """
    Parse a comma/ampersand-separated list of names.

    Handles:
        - "Bushey, Hill, Kertz & Mayor Kate" -> ["Bushey", "Hill", "Kertz", "Kate"]
        - "None" -> []
        - "Vice Mayor Llorens Gulati" -> ["Llorens Gulati"]
    """
    if not names_text:
        return []

    # Clean up and check for "None"
    names_text = names_text.strip()
    if names_text.lower() in ("none", "none.", "n/a", ""):
        return []

    # Split on comma, ampersand, and "and"
    # First replace & and "and" with comma
    names_text = re.sub(r'\s*[&]\s*', ', ', names_text)
    names_text = re.sub(r'\s+and\s+', ', ', names_text, flags=re.IGNORECASE)

    names = []
    for part in names_text.split(','):
        part = part.strip()
        if not part or part.lower() in ("none", "none."):
            continue

        # Remove title prefixes
        name = _strip_title(part)
        if name:
            names.append(name)

    return names


def _strip_title(name: str) -> str:
    """
    Strip title prefixes from a name.

    "Mayor Kate" -> "Kate"
    "Vice Mayor Bushey" -> "Bushey"
    "Councilmember Kertz" -> "Kertz"
    "Councilmember Llorens Gulati" -> "Llorens Gulati"
    """
    # Remove common title prefixes
    title_patterns = [
        r'^Vice\s+Mayor\s+',
        r'^Mayor\s+',
        r'^Council\s*member\s+',
        r'^Councilmember\s+',
        r'^CM\s+',
    ]

    for pattern in title_patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)

    return name.strip()


def extract_motion_attribution(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract who made and seconded a motion.

    Parses patterns like:
        "Vice Mayor Bushey moved, and Councilmember Kertz seconded"
        "Councilmember Hill moved and Councilmember Kertz seconded"

    Returns:
        (motion_by, second_by) tuple, e.g., ("Bushey", "Kertz")
    """
    motion_by = None
    second_by = None

    # Pattern for motion maker
    motion_match = re.search(
        r'(?:Vice\s+Mayor|Mayor|Council\s*member|Councilmember|CM)\s+'
        r'(\w+(?:\s+\w+)?)\s+moved',
        text,
        re.IGNORECASE
    )
    if motion_match:
        motion_by = motion_match.group(1).strip()

    # Pattern for seconder
    second_match = re.search(
        r'(?:Vice\s+Mayor|Mayor|Council\s*member|Councilmember|CM)\s+'
        r'(\w+(?:\s+\w+)?)\s+seconded',
        text,
        re.IGNORECASE
    )
    if second_match:
        second_by = second_match.group(1).strip()

    return motion_by, second_by


def extract_vote_tally(text: str) -> VoteTally:
    """
    Extract a complete VoteTally from meeting minutes text.

    Combines roll call extraction with motion attribution.

    Args:
        text: Text containing vote information (e.g., a paragraph from minutes)

    Returns:
        VoteTally with ayes, noes, absent, motion_by, second_by populated
    """
    roll_call = extract_roll_call(text)
    motion_by, second_by = extract_motion_attribution(text)

    return VoteTally(
        ayes=roll_call["ayes"],
        noes=roll_call["noes"],
        absent=roll_call["absent"],
        motion_by=motion_by,
        second_by=second_by,
    )


def normalize_vote_names(
    vote_tally: VoteTally,
    officials: list[dict],
    match_func: Optional[callable] = None,
) -> dict[str, str]:
    """
    Normalize extracted vote names to official records.

    Uses fuzzy matching to map extracted names (e.g., "Bushey")
    to official names (e.g., "Maribeth Bushey").

    Args:
        vote_tally: VoteTally with extracted names
        officials: List of elected official dicts with 'name' and 'name_variations' keys
        match_func: Optional custom matching function(name, official) -> bool

    Returns:
        Dict mapping official names to votes: {"Maribeth Bushey": "yes", ...}
    """
    result = {}

    # Build lookup from variations to official name
    variation_to_official = {}
    for official in officials:
        official_name = official.get("name", "")
        variations = official.get("name_variations", [])

        for var in variations:
            variation_to_official[var.lower()] = official_name

        # Also add the official name itself
        variation_to_official[official_name.lower()] = official_name

        # Add surname only
        surname = official_name.split()[-1] if official_name else ""
        if surname:
            variation_to_official[surname.lower()] = official_name

    # Match each vote
    for name in vote_tally.ayes:
        official = _find_official(name, variation_to_official, officials, match_func)
        if official:
            result[official] = "yes"
        else:
            result[name] = "yes"  # Keep original if no match

    for name in vote_tally.noes:
        official = _find_official(name, variation_to_official, officials, match_func)
        if official:
            result[official] = "no"
        else:
            result[name] = "no"

    for name in vote_tally.absent:
        official = _find_official(name, variation_to_official, officials, match_func)
        if official:
            result[official] = "absent"
        else:
            result[name] = "absent"

    return result


def _find_official(
    name: str,
    variation_lookup: dict[str, str],
    officials: list[dict],
    match_func: Optional[callable],
) -> Optional[str]:
    """Find official name matching extracted name."""
    # Try direct lookup first
    name_lower = name.lower()
    if name_lower in variation_lookup:
        return variation_lookup[name_lower]

    # Try custom match function if provided
    if match_func:
        for official in officials:
            if match_func(name, official):
                return official.get("name")

    # Try partial match on surname
    for var, official_name in variation_lookup.items():
        if name_lower in var or var in name_lower:
            return official_name

    return None


@dataclass
class LegalInstrument:
    """Resolution or ordinance that implements the decision."""

    instrument_type: str  # "resolution", "ordinance", "urgency_ordinance"
    number: Optional[str]  # e.g., "15478"
    title: str
    purpose: str
    legal_authority: list[str]  # e.g., ["Government Code Section 8698"]
    effective_date: Optional[str]

    def to_dict(self) -> dict:
        return {
            "type": self.instrument_type,
            "number": self.number,
            "title": self.title,
            "purpose": self.purpose,
            "legal_authority": self.legal_authority,
            "effective_date": self.effective_date,
        }


@dataclass
class PublicInput:
    """Summary of public input on a decision."""

    speaker_count: int
    speaker_names: list[str]
    # Note: Official minutes don't capture what speakers said,
    # only who spoke. For content, need video transcripts.
    has_video_transcript: bool = False

    def to_dict(self) -> dict:
        return {
            "speaker_count": self.speaker_count,
            "speaker_names": self.speaker_names,
            "has_video_transcript": self.has_video_transcript,
        }


@dataclass
class StaffRecommendation:
    """Staff recommendation that informed the decision."""

    department: str
    authors: list[str]
    recommendation_text: str
    financial_impact: Optional[str]
    property_details: Optional[dict]  # For real estate transactions

    def to_dict(self) -> dict:
        return {
            "department": self.department,
            "authors": self.authors,
            "recommendation": self.recommendation_text,
            "financial_impact": self.financial_impact,
            "property_details": self.property_details,
        }


@dataclass
class Decision:
    """
    A unified decision record from a city council meeting.

    This is the primary output for what_happened() queries.
    It combines data from:
    - Minutes (votes, outcomes)
    - Staff reports (recommendations, context)
    - Ordinances/Resolutions (legal instruments)
    """

    # Identity
    decision_id: str  # e.g., "2025-11-17-item-6a"
    meeting_date: str  # ISO format
    agenda_item: str  # e.g., "6.a"

    # What was decided
    title: str
    summary: str  # 1-2 sentence summary
    outcome: str  # "approved", "denied", "continued", "withdrawn"

    # How it was decided
    vote: VoteTally

    # Supporting information
    staff_recommendation: Optional[StaffRecommendation] = None
    public_input: Optional[PublicInput] = None
    legal_instruments: list[LegalInstrument] = field(default_factory=list)

    # Categorization for search
    topics: list[str] = field(default_factory=list)  # e.g., ["housing", "homelessness"]

    # Source references
    source_documents: list[str] = field(default_factory=list)  # Paths to source PDFs/JSONs

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "meeting_date": self.meeting_date,
            "agenda_item": self.agenda_item,
            "title": self.title,
            "summary": self.summary,
            "outcome": self.outcome,
            "vote": self.vote.to_dict(),
            "staff_recommendation": self.staff_recommendation.to_dict() if self.staff_recommendation else None,
            "public_input": self.public_input.to_dict() if self.public_input else None,
            "legal_instruments": [li.to_dict() for li in self.legal_instruments],
            "topics": self.topics,
            "source_documents": self.source_documents,
        }


class DecisionExtractor:
    """
    Extracts unified Decision records from meeting documents.

    Combines data from:
    - Minutes JSON (nov17_minutes.json)
    - Staff report JSON (item_6a_staff_report.json)
    - Ordinances JSON (shelter_ordinances.json)

    This consolidator synthesizes structured data that was already
    extracted by specialized extractors (MinutesExtractor, StaffReportExtractor,
    OrdinanceExtractor).
    """

    def __init__(self):
        # Topic keywords for auto-categorization
        self.topic_keywords = {
            "housing": ["housing", "affordable", "development", "units", "apartment"],
            "homelessness": ["shelter", "homeless", "unsheltered", "encampment", "crisis"],
            "transportation": ["transit", "bicycle", "pedestrian", "traffic", "highway"],
            "environment": ["environmental", "climate", "sustainability", "green"],
            "public_safety": ["police", "fire", "safety", "emergency"],
            "budget": ["budget", "fiscal", "financial", "appropriation", "funding"],
            "land_use": ["zoning", "planning", "land use", "general plan"],
        }

    def extract_from_corpus(
        self,
        corpus_dir: str | Path,
        meeting_date: str,
    ) -> list[Decision]:
        """
        Extract all decisions from a meeting corpus directory.

        Args:
            corpus_dir: Directory containing extracted JSON files
            meeting_date: ISO format date (e.g., "2025-11-17")

        Returns:
            List of Decision objects
        """
        corpus_dir = Path(corpus_dir)
        decisions = []

        # Load minutes (required)
        minutes_file = corpus_dir / f"{meeting_date.replace('-', '')[:4]}{meeting_date[5:7]}{meeting_date[8:10]}_minutes.json"
        # Try alternate naming patterns
        if not minutes_file.exists():
            # Try "nov17_minutes.json" pattern
            for f in corpus_dir.glob("*_minutes.json"):
                minutes_file = f
                break

        if not minutes_file.exists():
            raise FileNotFoundError(f"No minutes file found in {corpus_dir}")

        with open(minutes_file) as f:
            minutes_data = json.load(f)

        # Load optional staff report
        staff_report_data = None
        for sr_file in corpus_dir.glob("*_staff_report.json"):
            with open(sr_file) as f:
                staff_report_data = json.load(f)
            break  # Use first found

        # Load optional ordinances
        ordinances_data = []
        for ord_file in corpus_dir.glob("*_ordinances.json"):
            with open(ord_file) as f:
                ordinances_data = json.load(f)
            break

        # Process each agenda item with votes
        for item in minutes_data.get("items", []):
            if not item.get("votes"):
                # Items without votes are just received/filed, not decisions
                if not item.get("summary_notes"):
                    continue

            decision = self._create_decision(
                item=item,
                meeting_date=meeting_date,
                minutes_data=minutes_data,
                staff_report_data=staff_report_data,
                ordinances_data=ordinances_data,
                corpus_dir=corpus_dir,
            )
            if decision:
                decisions.append(decision)

        return decisions

    def _create_decision(
        self,
        item: dict,
        meeting_date: str,
        minutes_data: dict,
        staff_report_data: dict | None,
        ordinances_data: list[dict],
        corpus_dir: Path,
    ) -> Optional[Decision]:
        """Create a Decision from an agenda item."""

        item_number = item.get("item_number", "")
        title = item.get("title", "")

        # Skip if no meaningful content
        if not title and not item.get("summary_notes"):
            return None

        # Generate decision ID
        date_part = meeting_date.replace("-", "")
        item_part = item_number.replace(".", "-") if item_number else "unknown"
        decision_id = f"{date_part}-item-{item_part}"

        # Determine outcome
        votes = item.get("votes", [])
        summary_notes = item.get("summary_notes", "")

        if votes:
            # Use the last vote's outcome (most likely the final action)
            last_vote = votes[-1]
            ayes_count = len(last_vote.get("ayes", []))
            noes_count = len(last_vote.get("noes", []))
            outcome = "approved" if ayes_count > noes_count else "denied"
        elif "approved" in summary_notes.lower() or "adopted" in summary_notes.lower():
            outcome = "approved"
        elif "received and filed" in summary_notes.lower():
            outcome = "received"
        elif "continued" in summary_notes.lower():
            outcome = "continued"
        else:
            outcome = "approved"  # Default for consent items

        # Create vote tally (use first vote if multiple)
        vote_tally = None
        if votes:
            first_vote = votes[0]
            vote_tally = VoteTally(
                ayes=first_vote.get("ayes", []),
                noes=first_vote.get("noes", []),
                absent=first_vote.get("absent", []),
                motion_by=first_vote.get("motion_by"),
                second_by=first_vote.get("second_by"),
            )
        else:
            # Consent item - typically unanimous without recorded motion
            vote_tally = VoteTally(
                ayes=self._get_present_members(minutes_data),
                noes=[],
                absent=self._get_absent_members(minutes_data),
            )

        # Staff recommendation (if this item matches the staff report)
        staff_rec = None
        if staff_report_data:
            sr_item = staff_report_data.get("agenda_item", "")
            if sr_item == item_number or sr_item in item_number:
                staff_rec = StaffRecommendation(
                    department=staff_report_data.get("department", ""),
                    authors=staff_report_data.get("prepared_by", []),
                    recommendation_text=staff_report_data.get("recommendation", ""),
                    financial_impact=staff_report_data.get("financial_amount"),
                    property_details={
                        "address": staff_report_data.get("property_address"),
                        "apns": staff_report_data.get("property_apns"),
                    } if staff_report_data.get("property_address") else None,
                )

        # Public input
        speakers = item.get("public_speakers", [])
        public_input = None
        if speakers:
            public_input = PublicInput(
                speaker_count=len(speakers),
                speaker_names=speakers,
                has_video_transcript=False,  # Would need to check
            )

        # Legal instruments (match ordinances to this item)
        legal_instruments = []

        # Add resolution if present
        for vote in votes:
            if res_num := vote.get("resolution_number"):
                legal_instruments.append(LegalInstrument(
                    instrument_type="resolution",
                    number=res_num,
                    title=title,
                    purpose=summary_notes,
                    legal_authority=[],
                    effective_date=None,
                ))
            if ord_num := vote.get("ordinance_number"):
                legal_instruments.append(LegalInstrument(
                    instrument_type="ordinance",
                    number=ord_num,
                    title=title,
                    purpose=summary_notes,
                    legal_authority=[],
                    effective_date=None,
                ))

        # Match extracted ordinances to this item (requires strong topic match)
        # Only match ordinances to items that are clearly about the same topic
        item_text = (title + " " + item.get("description", "")).lower()
        for ord_data in ordinances_data:
            ord_purpose = ord_data.get("purpose", "").lower()
            ord_title = ord_data.get("title", "").lower()

            # Require strong match: purpose keywords must appear in item text
            # Skip generic words like "ordinance", "city", "san rafael"
            purpose_keywords = [w for w in ord_purpose.split() if len(w) > 4 and w not in ("ordinance", "council", "rafael")]

            # Need at least 2 matching keywords to link ordinance to item
            match_count = sum(1 for kw in purpose_keywords if kw in item_text)
            if match_count >= 2 or "shelter" in item_text and "shelter" in ord_title:
                legal_instruments.append(LegalInstrument(
                    instrument_type=ord_data.get("ordinance_type", "ordinance"),
                    number=ord_data.get("ordinance_number"),
                    title=ord_data.get("title", ""),
                    purpose=ord_data.get("purpose", ""),
                    legal_authority=ord_data.get("legal_authority", []),
                    effective_date=ord_data.get("effective_date_provision", "")[:200] if ord_data.get("effective_date_provision") else None,
                ))

        # Auto-categorize topics
        topics = self._extract_topics(title + " " + item.get("description", ""))

        # Generate summary
        summary = self._generate_summary(title, outcome, vote_tally, staff_rec)

        # Source documents
        sources = [str(corpus_dir / f.name) for f in corpus_dir.glob("*.json")]

        return Decision(
            decision_id=decision_id,
            meeting_date=meeting_date,
            agenda_item=item_number,
            title=title,
            summary=summary,
            outcome=outcome,
            vote=vote_tally,
            staff_recommendation=staff_rec,
            public_input=public_input,
            legal_instruments=legal_instruments,
            topics=topics,
            source_documents=sources,
        )

    def _get_present_members(self, minutes_data: dict) -> list[str]:
        """Extract present member names from minutes."""
        present = minutes_data.get("present", [])
        # Extract just surnames for consistency with vote records
        names = []
        for p in present:
            # "Mayor Kate" -> "Kate", "Councilmember Kertz" -> "Kertz"
            parts = p.split()
            if len(parts) >= 2:
                names.append(parts[-1])
            else:
                names.append(p)
        return names

    def _get_absent_members(self, minutes_data: dict) -> list[str]:
        """Extract absent member names from minutes."""
        absent = minutes_data.get("absent", [])
        names = []
        for a in absent:
            parts = a.split()
            if len(parts) >= 2:
                names.append(parts[-1])
            else:
                names.append(a)
        return names

    def _extract_topics(self, text: str) -> list[str]:
        """Extract topic categories from text."""
        topics = []
        text_lower = text.lower()

        for topic, keywords in self.topic_keywords.items():
            if any(kw in text_lower for kw in keywords):
                topics.append(topic)

        return topics

    def _generate_summary(
        self,
        title: str,
        outcome: str,
        vote: VoteTally,
        staff_rec: Optional[StaffRecommendation],
    ) -> str:
        """Generate a human-readable summary of the decision."""

        # Base summary from title
        title_clean = title.strip()
        if len(title_clean) > 100:
            title_clean = title_clean[:100] + "..."

        # Vote description
        if vote.unanimous:
            vote_desc = f"Unanimously {outcome}"
        else:
            vote_desc = f"{outcome.capitalize()} ({vote.vote_count})"

        # Financial impact if significant
        if staff_rec and staff_rec.financial_impact:
            return f"{vote_desc}: {title_clean}. Financial impact: {staff_rec.financial_impact}."

        return f"{vote_desc}: {title_clean}."


def extract_decisions(
    corpus_dir: str | Path,
    meeting_date: str,
    output_file: str | Path | None = None,
) -> list[dict]:
    """
    Convenience function to extract decisions from a meeting corpus.

    Args:
        corpus_dir: Directory containing minutes, staff reports, ordinances
        meeting_date: ISO format date (e.g., "2025-11-17")
        output_file: Optional path to write JSON output

    Returns:
        List of decision dictionaries
    """
    extractor = DecisionExtractor()
    decisions = extractor.extract_from_corpus(corpus_dir, meeting_date)
    result = [d.to_dict() for d in decisions]

    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

    return result
