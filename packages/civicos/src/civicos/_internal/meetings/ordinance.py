"""
Ordinance extraction from agenda packet chunks.

Extracts structured data from city council ordinances including
title, type (urgency/regular), WHEREAS clauses, operative sections,
and effective date provisions.
"""

from dataclasses import dataclass, field
from typing import Optional
import re
import json
from pathlib import Path


@dataclass
class OrdinanceSection:
    """A section/division of an ordinance."""

    number: int
    title: str
    text: str

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "text": self.text,
        }


@dataclass
class OrdinanceMetadata:
    """Structured metadata extracted from an ordinance."""

    ordinance_number: Optional[str]
    ordinance_type: str  # "urgency", "uncodified", "regular"
    title: str
    purpose: str  # First paragraph summary
    legal_authority: list[str]  # Government code sections cited
    whereas_clauses: list[str]
    sections: list[OrdinanceSection]
    effective_date_provision: str
    ceqa_determination: Optional[str] = None
    related_resolution: Optional[str] = None
    chunk_indices: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ordinance_number": self.ordinance_number,
            "ordinance_type": self.ordinance_type,
            "title": self.title,
            "purpose": self.purpose,
            "legal_authority": self.legal_authority,
            "whereas_clauses": self.whereas_clauses,
            "sections": [s.to_dict() for s in self.sections],
            "effective_date_provision": self.effective_date_provision,
            "ceqa_determination": self.ceqa_determination,
            "related_resolution": self.related_resolution,
            "chunk_indices": self.chunk_indices,
        }


class OrdinanceExtractor:
    """
    Extract structured data from ordinance chunks.

    San Rafael ordinances have a consistent structure:
    - Title: "AN [URGENCY|UNCODIFIED] ORDINANCE OF THE CITY COUNCIL..."
    - CEQA Determination in title
    - WHEREAS clauses (findings/justification)
    - NOW, THEREFORE... transition
    - DIVISION/SECTION clauses (operative provisions)
    - EFFECTIVE DATE and publication requirements
    """

    # Patterns for ordinance detection and parsing
    PATTERNS = {
        "ordinance_start": re.compile(
            r'ORDINANCE\s+NO\.?\s*(\d+)?[\s\n]*'
            r'AN\s+(URGENCY\s+ORDINANCE|UNCODIFIED\s+ORDINANCE|ORDINANCE)\s+'
            r'OF\s+THE\s+CITY\s+COUNCIL',
            re.IGNORECASE | re.MULTILINE
        ),
        "ordinance_title": re.compile(
            r'AN\s+(URGENCY\s+ORDINANCE|UNCODIFIED\s+ORDINANCE|ORDINANCE)\s+'
            r'OF\s+THE\s+CITY\s+COUNCIL\s+OF\s+THE\s+CITY\s+OF\s+SAN\s+RAFAEL\s*'
            r'(.*?)(?=WHEREAS|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "whereas": re.compile(
            r'WHEREAS,?\s*(.*?)(?=;\s*and\s*(?=WHEREAS)|;\s*(?=NOW)|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "now_therefore": re.compile(
            r'NOW,?\s*THEREFORE,?\s*THE\s+CITY\s+COUNCIL.*?DOES\s+ORDAIN\s+AS\s+FOLLOWS[:\s]*',
            re.IGNORECASE | re.DOTALL
        ),
        "division": re.compile(
            r'DIVISION\s+(\d+)[\.\s]*([^\n]+)?\n(.*?)(?=DIVISION\s+\d+|The\s+foregoing|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "section": re.compile(
            r'SECTION\s+(\d+)[\.\s]*(.*?)(?=SECTION\s+\d+|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "gov_code": re.compile(
            r'Government\s+Code\s+(?:Section[s]?\s+)?(\d+(?:\.\d+)?(?:\s*(?:through|et\.?\s*seq\.?|,\s*|\s+and\s+)\s*\d+(?:\.\d+)?)*)',
            re.IGNORECASE
        ),
        "ceqa": re.compile(
            r'CEQA\s+(?:DETERMINATION|Guideline[s]?)[:\s]*(.*?)(?=;|$)',
            re.IGNORECASE
        ),
        "effective_date": re.compile(
            r'EFFECTIVE\s+DATE[:\s]*(.*?)(?=DIVISION|SECTION|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "resolution_ref": re.compile(
            r'Resolution\s+No\.?\s*(\[?[A-Z0-9]+\]?)',
            re.IGNORECASE
        ),
    }

    def __init__(self):
        pass

    def find_ordinances(self, chunks: list[dict]) -> list[tuple[int, str]]:
        """
        Find all ordinances in the chunks and return their start indices and types.

        Returns:
            List of (chunk_index, ordinance_type) tuples
        """
        ordinances = []

        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "")

            # Look for ordinance start pattern
            if match := self.PATTERNS["ordinance_start"].search(text):
                ord_type_raw = match.group(2).lower()
                if "urgency" in ord_type_raw:
                    ord_type = "urgency"
                elif "uncodified" in ord_type_raw:
                    ord_type = "uncodified"
                else:
                    ord_type = "regular"

                ordinances.append((i, ord_type))

        return ordinances

    def extract_ordinance(
        self,
        chunks: list[dict],
        start_index: int,
        ordinance_type: str = "urgency",
    ) -> OrdinanceMetadata:
        """
        Extract a complete ordinance starting from the given chunk index.

        Args:
            chunks: All chunks from the agenda packet
            start_index: Index of chunk where ordinance begins
            ordinance_type: Type detected ("urgency", "uncodified", "regular")

        Returns:
            OrdinanceMetadata with extracted fields
        """
        # Collect chunks until we hit the next ordinance or end
        ordinance_chunks = []
        chunk_indices = []

        for i in range(start_index, len(chunks)):
            chunk = chunks[i]
            text = chunk.get("text", "")

            # If we find a new ordinance start (not the first chunk), stop
            if i > start_index and self.PATTERNS["ordinance_start"].search(text):
                # Check if this is a different ordinance or just title repeated
                # Look for DIFFERENT ordinance type in the text
                current_type_in_text = False
                if ordinance_type == "urgency" and "URGENCY ORDINANCE" in text.upper():
                    current_type_in_text = True
                elif ordinance_type == "uncodified" and "UNCODIFIED ORDINANCE" in text.upper():
                    current_type_in_text = True

                # If it's a voting record or different ordinance type, stop
                if "The foregoing Ordinance" in text:
                    ordinance_chunks.append(text)
                    chunk_indices.append(i)
                    break
                elif not current_type_in_text:
                    # Different ordinance type found - stop before this chunk
                    break

            ordinance_chunks.append(text)
            chunk_indices.append(i)

            # Stop at voting record / clerk certification (at end of chunk processing)
            if "The foregoing Ordinance No." in text and i > start_index:
                break

        # Combine text for extraction
        full_text = "\n".join(ordinance_chunks)

        # Extract components
        return OrdinanceMetadata(
            ordinance_number=self._extract_ordinance_number(full_text),
            ordinance_type=ordinance_type,
            title=self._extract_title(full_text),
            purpose=self._extract_purpose(full_text),
            legal_authority=self._extract_legal_authority(full_text),
            whereas_clauses=self._extract_whereas_clauses(full_text),
            sections=self._extract_sections(full_text),
            effective_date_provision=self._extract_effective_date(full_text),
            ceqa_determination=self._extract_ceqa(full_text),
            related_resolution=self._extract_resolution_ref(full_text),
            chunk_indices=chunk_indices,
        )

    def _extract_ordinance_number(self, text: str) -> Optional[str]:
        """Extract ordinance number if present."""
        match = re.search(r'ORDINANCE\s+NO\.?\s*(\d+)', text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _extract_title(self, text: str) -> str:
        """Extract the full ordinance title."""
        if match := self.PATTERNS["ordinance_title"].search(text):
            ord_type = match.group(1)
            rest = match.group(2) if match.group(2) else ""
            title = f"AN {ord_type.upper()} OF THE CITY COUNCIL OF THE CITY OF SAN RAFAEL {rest}"
            return self._clean_text(title)
        return ""

    def _extract_purpose(self, text: str) -> str:
        """Extract the primary purpose from the title or first WHEREAS."""
        # Look for purpose keywords in title
        if match := re.search(
            r'(?:ADOPTING|APPROVING|DECLARING|AMENDING)\s+(.*?)(?=;|PURSUANT|CEQA|$)',
            text,
            re.IGNORECASE | re.DOTALL
        ):
            return self._clean_text(match.group(1))[:500]
        return ""

    def _extract_legal_authority(self, text: str) -> list[str]:
        """Extract all Government Code sections cited."""
        matches = self.PATTERNS["gov_code"].findall(text)
        # Deduplicate and clean
        seen = set()
        result = []
        for m in matches:
            cleaned = m.strip()
            if cleaned not in seen:
                seen.add(cleaned)
                result.append(f"Government Code Section {cleaned}")
        return result

    def _extract_whereas_clauses(self, text: str) -> list[str]:
        """Extract all WHEREAS clauses."""
        clauses = []

        # Split on WHEREAS
        parts = re.split(r'WHEREAS,?\s*', text, flags=re.IGNORECASE)

        for part in parts[1:]:  # Skip text before first WHEREAS
            # Extract until "; and" or "NOW, THEREFORE"
            match = re.match(
                r'(.*?)(?:;\s*and\s*$|;\s*$|NOW,?\s*THEREFORE)',
                part,
                re.IGNORECASE | re.DOTALL
            )
            if match:
                clause = self._clean_text(match.group(1))
                if clause and len(clause) > 20:
                    clauses.append(clause)

            # Stop at NOW, THEREFORE
            if re.search(r'NOW,?\s*THEREFORE', part, re.IGNORECASE):
                break

        return clauses

    def _extract_sections(self, text: str) -> list[OrdinanceSection]:
        """Extract DIVISION or SECTION clauses from operative portion of ordinance."""
        sections = []

        # Find the start of operative sections (after NOW, THEREFORE)
        operative_start = re.search(
            r'NOW,?\s*THEREFORE.*?DOES\s+ORDAIN\s+AS\s+FOLLOWS[:\s]*',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if operative_start:
            operative_text = text[operative_start.end():]
        else:
            operative_text = text

        # Look for DIVISION patterns that are actual ordinance divisions
        # (not references like "Division 13 of the Health and Safety Code")
        division_pattern = re.compile(
            r'^DIVISION\s+(\d+)[.\s]+([A-Z][A-Z\s,;]+(?:\([A-Z]+\))?)[.\s]*\n(.*?)(?=^DIVISION\s+\d+|The\s+foregoing|$)',
            re.IGNORECASE | re.MULTILINE | re.DOTALL
        )

        division_matches = list(division_pattern.finditer(operative_text))

        seen_divisions = set()
        if division_matches:
            for match in division_matches:
                num = int(match.group(1))
                title = match.group(2).strip() if match.group(2) else ""
                content = self._clean_text(match.group(3))

                # Clean up title (remove trailing punctuation, whitespace)
                title = re.sub(r'[.\s:]+$', '', title).strip()

                # Skip if title looks like a code reference (e.g., "of the Health and Safety Code")
                if title.lower().startswith('of the') or 'code' in title.lower():
                    continue

                # Skip duplicates (from chunk overlap)
                if num in seen_divisions:
                    continue
                seen_divisions.add(num)

                sections.append(OrdinanceSection(
                    number=num,
                    title=title,
                    text=content[:2000] if content else "",
                ))
        else:
            # Fall back to SECTION patterns
            section_pattern = re.compile(
                r'SECTION\s+(\d+)[.\s]*(.*?)(?=SECTION\s+\d+|$)',
                re.IGNORECASE | re.DOTALL
            )
            section_matches = list(section_pattern.finditer(operative_text))
            for match in section_matches:
                num = int(match.group(1))
                content = self._clean_text(match.group(2))
                sections.append(OrdinanceSection(
                    number=num,
                    title="",
                    text=content[:2000] if content else "",
                ))

        return sections

    def _extract_effective_date(self, text: str) -> str:
        """Extract effective date provision."""
        # Look for EFFECTIVE DATE division - capture until next signature/clerk section
        match = re.search(
            r'DIVISION\s+\d+[.\s]+EFFECTIVE\s+DATE[;\s:]*(?:PUBLICATION)?[.\s]*\n(.*?)(?=______|The\s+foregoing|KATE\s+COLIN|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            return self._clean_text(match.group(1))[:1000]

        # Fallback: look for urgency measure language
        match = re.search(
            r'(?:urgency\s+measure|take\s+effect|immediately\s+upon).*?(?:four-fifths|4/5|vote\s+of\s+the\s+City\s+Council)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            return self._clean_text(match.group(0))[:1000]

        return ""

    def _extract_ceqa(self, text: str) -> Optional[str]:
        """Extract CEQA determination."""
        if match := self.PATTERNS["ceqa"].search(text):
            return self._clean_text(match.group(1))[:300]
        return None

    def _extract_resolution_ref(self, text: str) -> Optional[str]:
        """Extract any referenced resolution number."""
        matches = self.PATTERNS["resolution_ref"].findall(text)
        if matches:
            return matches[0]
        return None

    def _clean_text(self, text: str) -> str:
        """Clean extracted text by normalizing whitespace."""
        # Replace bullet characters
        text = text.replace('\uf0a7', '-')
        # Replace multiple whitespace with single space
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove document reference numbers (e.g., "4915-9294-8600 v1")
        text = re.sub(r'\d{4}-\d{4}-\d{4}\s+v\d+', '', text)
        return text


def extract_shelter_ordinances(
    chunks_file: str | Path,
    output_file: str | Path | None = None,
) -> list[dict]:
    """
    Extract all shelter-related ordinances from agenda packet chunks.

    Args:
        chunks_file: Path to JSON file with chunks
        output_file: Optional path to write JSON output

    Returns:
        List of ordinance dictionaries
    """
    chunks_file = Path(chunks_file)

    with open(chunks_file) as f:
        chunks = json.load(f)

    extractor = OrdinanceExtractor()

    # Find all ordinances
    ordinance_locations = extractor.find_ordinances(chunks)

    # Extract each ordinance
    results = []
    for start_idx, ord_type in ordinance_locations:
        # Only extract shelter-related ordinances
        chunk_text = chunks[start_idx].get("text", "")
        if "homeless shelter" in chunk_text.lower() or "8698" in chunk_text:
            metadata = extractor.extract_ordinance(chunks, start_idx, ord_type)
            results.append(metadata.to_dict())

    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

    return results
