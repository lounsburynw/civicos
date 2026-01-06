"""
Code of Federal Regulations (CFR) XML Parser

Parses the official CFR XML from govinfo.gov into structured sections
suitable for storage in codified_law table and RAG queries.

The CFR structure:
- Title (50 titles, e.g., Title 24 - Housing and Urban Development)
  - Subtitle (optional, e.g., Subtitle A - Office of the Secretary)
    - Chapter (by agency, e.g., Chapter I - HUD)
      - Subchapter (optional)
        - Part (regulatory area, e.g., Part 1 - Nondiscrimination)
          - Subpart (optional)
            - Section (the basic unit, e.g., § 1.1)

Usage:
    from civic_extraction.cfr import CFRParser

    parser = CFRParser("data/cfr/CFR-2024-title24-vol1.xml")
    sections = list(parser.parse_sections())

    for section in sections:
        print(f"{section['citation']}: {section['heading']}")
        print(f"  Text: {section['text'][:100]}...")
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, Optional
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class CFRSection:
    """A single section of the Code of Federal Regulations."""

    title_number: int
    title_name: str
    part_number: str
    section_number: str
    heading: str
    text: str
    citation: str  # e.g., "24 CFR 1.1"
    identifier: str  # e.g., "cfr/t24/pt1/s1.1"
    authority: Optional[str] = None  # Legal authority for the regulation
    source: Optional[str] = None  # FR citation for the source
    chapter: Optional[str] = None
    subchapter: Optional[str] = None
    subpart: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class CFRParser:
    """
    Parser for CFR XML files from govinfo.gov bulk data.

    The CFR XML uses a different structure from U.S. Code XML:
    - No namespace (unlike USLM format)
    - Elements: CFRDOC > TITLE > SUBTITLE > PART > SECTION
    - Section numbers in SECTNO (e.g., "§ 1.1")
    - Section headings in SUBJECT
    - Section text in P, FP, and other paragraph elements
    """

    def __init__(self, xml_path: str | Path):
        self.xml_path = Path(xml_path)
        if not self.xml_path.exists():
            raise FileNotFoundError(f"CFR XML not found: {xml_path}")

        self.tree = None
        self.root = None
        self.title_number = None
        self.title_name = None

    def _load(self) -> None:
        """Load and parse the XML file."""
        if self.tree is not None:
            return

        logger.info(f"Loading CFR XML: {self.xml_path}")
        self.tree = ET.parse(self.xml_path)
        self.root = self.tree.getroot()

        # Extract title info from FMTR/TITLEPG or CFRTITLE
        titlepg = self.root.find(".//TITLEPG")
        if titlepg is not None:
            titlenum = titlepg.find("TITLENUM")
            if titlenum is not None and titlenum.text:
                # Extract number from "Title 24"
                match = re.search(r'\d+', titlenum.text)
                if match:
                    self.title_number = int(match.group())

            subject = titlepg.find("SUBJECT")
            if subject is not None and subject.text:
                self.title_name = subject.text.strip()

        logger.info(f"Loaded Title {self.title_number}: {self.title_name}")

    def _get_text(self, elem: ET.Element) -> str:
        """Extract all text content from an element, including nested elements."""
        if elem is None:
            return ""

        texts = []

        # Handle text before first child
        if elem.text:
            texts.append(elem.text.strip())

        # Recursively get text from children
        for child in elem:
            tag = child.tag

            # Skip certain elements
            if tag in ("PRTPAGE", "GPH", "GID", "CITA", "SECAUTH",
                       "SOURCE", "AUTH", "CONTENTS", "SECHD", "EDNOTE",
                       "EFFDNOT", "EFFDATE"):
                # Still need tail text
                if child.tail:
                    texts.append(child.tail.strip())
                continue

            child_text = self._get_text(child)
            if child_text:
                texts.append(child_text)

            # Handle tail text
            if child.tail:
                texts.append(child.tail.strip())

        # Join with space, clean up whitespace
        result = " ".join(texts)
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def _extract_section_text(self, section: ET.Element) -> str:
        """Extract readable text from a section element."""
        parts = []

        for child in section:
            tag = child.tag

            # Skip metadata elements
            if tag in ("SECTNO", "SUBJECT", "CITA", "SECAUTH",
                       "PRTPAGE", "EDNOTE", "EFFDNOT"):
                continue

            # Process content elements
            if tag in ("P", "FP", "EXTRACT", "GPOTABLE", "NOTE",
                       "CONTENTS", "SUBPART", "APPENDIX"):
                text = self._get_text(child)
                if text:
                    parts.append(text)
            else:
                # Try to extract text from unknown elements
                text = self._get_text(child)
                if text:
                    parts.append(text)

        return " ".join(parts)

    def _parse_section_number(self, sectno_text: str) -> str:
        """Parse section number from SECTNO text (e.g., '§ 1.1' -> '1.1')."""
        if not sectno_text:
            return ""
        # Remove § symbol and whitespace
        cleaned = re.sub(r'[§\s]+', '', sectno_text)
        return cleaned

    def _parse_part_number(self, hd_text: str) -> str:
        """Parse part number from HD text (e.g., 'PART 1—NONDISCRIMINATION...' -> '1')."""
        if not hd_text:
            return ""
        match = re.search(r'PART\s+(\d+)', hd_text)
        if match:
            return match.group(1)
        return ""

    def parse_sections(
        self,
        part_filter: Optional[str] = None,
        min_text_length: int = 20,
    ) -> Iterator[CFRSection]:
        """
        Parse all sections from the CFR XML.

        Args:
            part_filter: If set, only return sections from this part number
            min_text_length: Minimum text length to include section

        Yields:
            CFRSection objects for each section
        """
        self._load()

        # Track current context
        current_chapter = None
        current_subchapter = None
        current_part = None
        current_part_name = None
        current_subpart = None
        current_authority = None
        current_source = None

        section_count = 0
        yielded_count = 0

        # Iterate through all elements
        for elem in self.root.iter():
            tag = elem.tag

            # Track chapter context
            if tag == "CHAPTER":
                hd = elem.find("HD")
                if hd is not None:
                    current_chapter = self._get_text(hd)
                current_subchapter = None

            # Track subchapter context
            elif tag == "SUBCHAP":
                hd = elem.find("HD")
                if hd is not None:
                    current_subchapter = self._get_text(hd)

            # Track part context
            elif tag == "PART":
                hd = elem.find("HD")
                if hd is not None:
                    hd_text = self._get_text(hd)
                    current_part = self._parse_part_number(hd_text)
                    # Extract part name (text after the em-dash)
                    if "—" in hd_text:
                        current_part_name = hd_text.split("—", 1)[1].strip()
                    elif "-" in hd_text:
                        current_part_name = hd_text.split("-", 1)[1].strip()
                    else:
                        current_part_name = hd_text

                current_subpart = None

                # Get authority and source from PART
                auth = elem.find(".//AUTH/P")
                if auth is not None:
                    current_authority = self._get_text(auth)

                source = elem.find(".//SOURCE/P")
                if source is not None:
                    current_source = self._get_text(source)

            # Track subpart context
            elif tag == "SUBPART":
                hd = elem.find("HD")
                if hd is not None:
                    current_subpart = self._get_text(hd)

            # Process sections
            elif tag == "SECTION":
                section_count += 1

                # Apply part filter
                if part_filter and current_part != part_filter:
                    continue

                # Get section number
                sectno = elem.find("SECTNO")
                if sectno is None or not sectno.text:
                    continue
                section_number = self._parse_section_number(sectno.text)

                # Get section heading
                subject = elem.find("SUBJECT")
                heading = subject.text.strip() if subject is not None and subject.text else ""

                # Extract section text
                text = self._extract_section_text(elem)

                # Skip if no meaningful text
                if not text or len(text) < min_text_length:
                    continue

                # Build citation: "24 CFR 1.1"
                citation = f"{self.title_number} CFR {section_number}"

                # Build identifier: "cfr/t24/s1.1"
                identifier = f"cfr/t{self.title_number}/s{section_number}"

                yielded_count += 1

                yield CFRSection(
                    title_number=self.title_number,
                    title_name=self.title_name,
                    part_number=current_part or "",
                    section_number=section_number,
                    heading=heading,
                    text=text,
                    citation=citation,
                    identifier=identifier,
                    authority=current_authority,
                    source=current_source,
                    chapter=current_chapter,
                    subchapter=current_subchapter,
                    subpart=current_subpart,
                )

        logger.info(f"Parsed {yielded_count} sections from {section_count} total")

    def get_stats(self) -> dict:
        """Get statistics about the CFR title volume."""
        self._load()

        sections = list(self.parse_sections(min_text_length=0))

        # Group by part
        parts = {}
        for s in sections:
            part = s.part_number or "Unknown"
            if part not in parts:
                parts[part] = 0
            parts[part] += 1

        # Calculate text statistics
        text_lengths = [len(s.text) for s in sections if s.text]
        avg_text_len = sum(text_lengths) / len(text_lengths) if text_lengths else 0

        return {
            "title_number": self.title_number,
            "title_name": self.title_name,
            "total_sections": len(sections),
            "parts": len(parts),
            "sections_by_part": parts,
            "avg_text_length": int(avg_text_len),
            "total_text_chars": sum(text_lengths),
        }


def main():
    """CLI for testing CFR parser."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python cfr.py <xml_file> [--stats] [--part=NUMBER]")
        sys.exit(1)

    xml_path = sys.argv[1]
    show_stats = "--stats" in sys.argv

    part_filter = None
    for arg in sys.argv:
        if arg.startswith("--part="):
            part_filter = arg.split("=", 1)[1]

    parser = CFRParser(xml_path)

    if show_stats:
        stats = parser.get_stats()
        print(f"Title {stats['title_number']}: {stats['title_name']}")
        print(f"Total sections: {stats['total_sections']}")
        print(f"Parts: {stats['parts']}")
        print(f"Avg text length: {stats['avg_text_length']} chars")
        print(f"\nSections by part:")
        for part, count in sorted(stats['sections_by_part'].items(),
                                   key=lambda x: int(x[0]) if x[0].isdigit() else 999):
            print(f"  Part {part}: {count} sections")
    else:
        for i, section in enumerate(parser.parse_sections(part_filter=part_filter)):
            print(f"\n{'='*60}")
            print(f"Citation: {section.citation}")
            print(f"Heading: {section.heading}")
            print(f"Part: {section.part_number}")
            print(f"Text ({len(section.text)} chars): {section.text[:200]}...")

            if i >= 4:  # Show first 5
                print(f"\n... (showing first 5 sections)")
                break


if __name__ == "__main__":
    main()
