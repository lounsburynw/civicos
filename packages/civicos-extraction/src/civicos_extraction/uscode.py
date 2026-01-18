"""
U.S. Code XML Parser

Parses the official U.S. Code XML from uscode.house.gov into structured sections
suitable for vector indexing and RAG queries.

Usage:
    from civicos_extraction.uscode import USCodeParser

    parser = USCodeParser("data/uscode/usc42.xml")
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

# USLM XML namespace
USLM_NS = {"uslm": "http://xml.house.gov/schemas/uslm/1.0"}


@dataclass
class USCodeSection:
    """A single section of the U.S. Code."""

    title_number: int
    title_name: str
    section_number: str
    heading: str
    text: str
    citation: str  # e.g., "42 U.S.C. § 1437"
    identifier: str  # e.g., "/us/usc/t42/s1437"
    status: Optional[str] = None  # "repealed", "omitted", or None (active)
    chapter: Optional[str] = None
    subchapter: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def is_active(self) -> bool:
        """Return True if section is active (not repealed/omitted)."""
        return self.status is None


class USCodeParser:
    """
    Parser for U.S. Code XML files from uscode.house.gov.

    The U.S. Code is organized as:
    - Title (e.g., Title 42 - Public Health and Welfare)
      - Chapter
        - Subchapter (optional)
          - Section (the basic unit of law)
            - Subsection
              - Paragraph
                - Subparagraph
                  - Clause
    """

    def __init__(self, xml_path: str | Path):
        self.xml_path = Path(xml_path)
        if not self.xml_path.exists():
            raise FileNotFoundError(f"U.S. Code XML not found: {xml_path}")

        self.tree = None
        self.root = None
        self.title_number = None
        self.title_name = None

    def _load(self) -> None:
        """Load and parse the XML file."""
        if self.tree is not None:
            return

        logger.info(f"Loading U.S. Code XML: {self.xml_path}")
        self.tree = ET.parse(self.xml_path)
        self.root = self.tree.getroot()

        # Extract title info from meta
        meta = self.root.find("uslm:meta", USLM_NS)
        if meta is not None:
            doc_num = meta.find("uslm:docNumber", USLM_NS)
            if doc_num is not None and doc_num.text:
                self.title_number = int(doc_num.text)

        # Get title name from main/title/heading
        main = self.root.find("uslm:main", USLM_NS)
        if main is not None:
            title_elem = main.find("uslm:title", USLM_NS)
            if title_elem is not None:
                heading = title_elem.find("uslm:heading", USLM_NS)
                if heading is not None:
                    self.title_name = self._get_text(heading)

        logger.info(f"Loaded Title {self.title_number}: {self.title_name}")

    def _get_text(self, elem: ET.Element) -> str:
        """Extract all text content from an element, including nested elements."""
        if elem is None:
            return ""

        # Get all text including from child elements
        texts = []

        # Handle text before first child
        if elem.text:
            texts.append(elem.text.strip())

        # Recursively get text from children
        for child in elem:
            # Skip certain elements like notes, toc, etc.
            tag = child.tag.replace(f"{{{USLM_NS['uslm']}}}", "")
            if tag in ("notes", "toc", "sourceCredit", "statutoryNote"):
                continue

            child_text = self._get_text(child)
            if child_text:
                texts.append(child_text)

            # Handle tail text (text after this child, before next sibling)
            if child.tail:
                texts.append(child.tail.strip())

        # Join with space, clean up whitespace
        result = " ".join(texts)
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def _extract_section_text(self, section: ET.Element) -> str:
        """Extract readable text from a section element."""
        # Skip repealed/omitted sections
        status = section.get("status")
        if status in ("repealed", "omitted"):
            return ""

        parts = []

        # Process subsections, paragraphs, content directly
        for child in section:
            tag = child.tag.replace(f"{{{USLM_NS['uslm']}}}", "")

            if tag == "num":
                continue  # Skip section number
            elif tag == "heading":
                continue  # Already captured separately
            elif tag in ("content", "chapeau", "subsection", "paragraph",
                        "subparagraph", "clause", "p"):
                text = self._get_text(child)
                if text:
                    parts.append(text)
            elif tag == "notes":
                continue  # Skip notes
            else:
                # Try to extract text from unknown elements
                text = self._get_text(child)
                if text:
                    parts.append(text)

        return " ".join(parts)

    def parse_sections(
        self,
        include_inactive: bool = False,
        chapter_filter: Optional[str] = None,
    ) -> Iterator[USCodeSection]:
        """
        Parse all sections from the U.S. Code XML.

        Args:
            include_inactive: If True, include repealed/omitted sections
            chapter_filter: If set, only return sections from this chapter

        Yields:
            USCodeSection objects for each section
        """
        self._load()

        main = self.root.find("uslm:main", USLM_NS)
        if main is None:
            logger.error("No main element found in XML")
            return

        title_elem = main.find("uslm:title", USLM_NS)
        if title_elem is None:
            logger.error("No title element found in XML")
            return

        # Track current chapter/subchapter context
        current_chapter = None
        current_subchapter = None

        # Process all elements under title
        section_count = 0
        active_count = 0

        for elem in title_elem.iter():
            tag = elem.tag.replace(f"{{{USLM_NS['uslm']}}}", "")

            if tag == "chapter":
                heading = elem.find("uslm:heading", USLM_NS)
                current_chapter = self._get_text(heading) if heading is not None else None
                current_subchapter = None  # Reset subchapter

            elif tag == "subchapter":
                heading = elem.find("uslm:heading", USLM_NS)
                current_subchapter = self._get_text(heading) if heading is not None else None

            elif tag == "section":
                section_count += 1

                # Get section attributes
                identifier = elem.get("identifier", "")
                status = elem.get("status")

                # Skip inactive unless requested
                if status in ("repealed", "omitted") and not include_inactive:
                    continue

                # Apply chapter filter
                if chapter_filter and current_chapter:
                    if chapter_filter.lower() not in current_chapter.lower():
                        continue

                # Extract section number
                num_elem = elem.find("uslm:num", USLM_NS)
                section_number = num_elem.get("value", "") if num_elem is not None else ""

                # Extract heading
                heading_elem = elem.find("uslm:heading", USLM_NS)
                heading = self._get_text(heading_elem)

                # Extract text content
                text = self._extract_section_text(elem)

                # Skip if no meaningful text
                if not text or len(text) < 20:
                    continue

                # Build citation
                citation = f"{self.title_number} U.S.C. § {section_number}"

                active_count += 1

                yield USCodeSection(
                    title_number=self.title_number,
                    title_name=self.title_name,
                    section_number=section_number,
                    heading=heading,
                    text=text,
                    citation=citation,
                    identifier=identifier,
                    status=status,
                    chapter=current_chapter,
                    subchapter=current_subchapter,
                )

        logger.info(f"Parsed {active_count} active sections from {section_count} total")

    def get_stats(self) -> dict:
        """Get statistics about the U.S. Code title."""
        self._load()

        sections = list(self.parse_sections(include_inactive=True))
        active = [s for s in sections if s.is_active()]

        # Group by chapter
        chapters = {}
        for s in active:
            ch = s.chapter or "Unknown"
            if ch not in chapters:
                chapters[ch] = 0
            chapters[ch] += 1

        return {
            "title_number": self.title_number,
            "title_name": self.title_name,
            "total_sections": len(sections),
            "active_sections": len(active),
            "repealed_sections": len([s for s in sections if s.status == "repealed"]),
            "omitted_sections": len([s for s in sections if s.status == "omitted"]),
            "chapters": len(chapters),
            "sections_by_chapter": chapters,
        }


def main():
    """CLI for testing U.S. Code parser."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python uscode.py <xml_file> [--stats] [--chapter=FILTER]")
        sys.exit(1)

    xml_path = sys.argv[1]
    show_stats = "--stats" in sys.argv

    chapter_filter = None
    for arg in sys.argv:
        if arg.startswith("--chapter="):
            chapter_filter = arg.split("=", 1)[1]

    parser = USCodeParser(xml_path)

    if show_stats:
        stats = parser.get_stats()
        print(f"Title {stats['title_number']}: {stats['title_name']}")
        print(f"Total sections: {stats['total_sections']}")
        print(f"Active sections: {stats['active_sections']}")
        print(f"Repealed: {stats['repealed_sections']}")
        print(f"Omitted: {stats['omitted_sections']}")
        print(f"\nChapters ({stats['chapters']}):")
        for ch, count in sorted(stats['sections_by_chapter'].items(), key=lambda x: -x[1])[:10]:
            print(f"  {ch}: {count} sections")
    else:
        for i, section in enumerate(parser.parse_sections(chapter_filter=chapter_filter)):
            print(f"\n{'='*60}")
            print(f"Citation: {section.citation}")
            print(f"Heading: {section.heading}")
            print(f"Chapter: {section.chapter}")
            print(f"Text ({len(section.text)} chars): {section.text[:200]}...")

            if i >= 4:  # Show first 5
                print(f"\n... (showing first 5 sections)")
                break


if __name__ == "__main__":
    main()
