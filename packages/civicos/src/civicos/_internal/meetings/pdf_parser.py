"""
Agenda packet PDF parsing for RAG.

Parses city council agenda packet PDFs into structured chunks organized by agenda item.
Uses PDF bookmarks/TOC when available, falls back to pattern matching.

Designed for San Rafael agenda packets but generalizable to other cities.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
import re
import json

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


@dataclass
class AgendaChunk:
    """A chunk of agenda packet text with metadata."""
    text: str
    agenda_item: str  # e.g., "6.a"
    agenda_title: str  # e.g., "Declaration of Shelter Crisis..."
    page_start: int
    page_end: int
    chunk_index: int  # Index within this agenda item
    total_chunks: int  # Total chunks for this item
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "agenda_item": self.agenda_item,
            "agenda_title": self.agenda_title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "metadata": self.metadata,
        }


@dataclass
class AgendaSection:
    """A section of the agenda packet (one agenda item)."""
    item_number: str  # e.g., "6.a"
    title: str
    page_start: int
    page_end: int
    text: str


class AgendaPacketParser:
    """
    Parse city council agenda packet PDFs.

    Extracts text organized by agenda item using PDF bookmarks
    or pattern matching as fallback.
    """

    # Pattern for agenda item markers in text.
    # Matches the San Rafael / ProudCity format "Agenda Item No. 6.a".
    AGENDA_ITEM_PATTERN = re.compile(
        r'Agenda\s+Item\s+No[.:]\s*(\d+[a-z.]*)',
        re.IGNORECASE
    )

    # Secondary pattern for numbered-bullet agendas used by Alameda County,
    # San Francisco, Berkeley, and many other jurisdictions where items look
    # like "1. CONSENT CALENDAR" or "2. Social Services Agency - Approve...".
    # Requires at start of line, 1-3 digits followed by "." and whitespace,
    # then a capital letter starting a 4-80 char title. The \d{1,3} bound
    # prevents matching contract numbers ("25668") or addresses ("1221 Oak").
    # Validated on Alameda Apr 7 2026 agenda: 79 matches across 24 pages
    # where the primary pattern finds 0.
    AGENDA_ITEM_NUMBERED_PATTERN = re.compile(
        r'(?:^|\n)[ \t]*(\d{1,3})\.\s+(?:\*)?([A-Z][A-Za-z0-9 ,.\-&/\'\"]{4,80})',
        re.MULTILINE
    )

    def __init__(
        self,
        max_chunk_size: int = 1500,
        chunk_overlap: int = 200,
    ):
        """
        Initialize parser.

        Args:
            max_chunk_size: Maximum characters per chunk for RAG
            chunk_overlap: Character overlap between chunks
        """
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is required for PDF parsing")

        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap

    def parse(self, pdf_path: str | Path) -> list[AgendaSection]:
        """
        Parse agenda packet PDF into sections by agenda item.

        Args:
            pdf_path: Path to the agenda packet PDF

        Returns:
            List of AgendaSection objects
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(str(pdf_path))

        try:
            # Get table of contents / bookmarks
            toc = doc.get_toc()

            if toc:
                sections = self._parse_with_toc(doc, toc)
            else:
                sections = self._parse_with_patterns(doc)

            return sections
        finally:
            doc.close()

    def parse_to_chunks(
        self,
        pdf_path: str | Path,
        source_metadata: dict | None = None,
    ) -> list[AgendaChunk]:
        """
        Parse PDF and return RAG-ready chunks.

        Args:
            pdf_path: Path to the agenda packet PDF
            source_metadata: Additional metadata for all chunks

        Returns:
            List of AgendaChunk objects suitable for embedding
        """
        sections = self.parse(pdf_path)
        chunks = []

        source_metadata = source_metadata or {}
        source_metadata.setdefault("source_file", str(pdf_path))

        for section in sections:
            section_chunks = list(self._chunk_section(section, source_metadata))

            # Set total_chunks on each chunk
            for chunk in section_chunks:
                chunk.total_chunks = len(section_chunks)

            chunks.extend(section_chunks)

        return chunks

    def _parse_with_toc(self, doc, toc: list) -> list[AgendaSection]:
        """Parse using PDF table of contents/bookmarks."""
        sections = []
        total_pages = len(doc)

        for i, (level, title, page_num) in enumerate(toc):
            # Determine page range
            page_start = page_num
            if i + 1 < len(toc):
                page_end = toc[i + 1][2] - 1
            else:
                page_end = total_pages

            # Extract item number from title
            item_number = self._extract_item_number(title)
            if not item_number:
                # Use position-based identifier
                item_number = f"toc_{i}"

            # Extract text for this section
            text = self._extract_pages_text(doc, page_start, page_end)

            sections.append(AgendaSection(
                item_number=item_number,
                title=title,
                page_start=page_start,
                page_end=page_end,
                text=text,
            ))

        return sections

    def _parse_with_patterns(self, doc) -> list[AgendaSection]:
        """Parse using text pattern matching when no TOC available."""
        sections = []
        current_item = None
        current_title = ""
        current_start = 1
        current_text = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            # Look for agenda item markers.
            # Try the San Rafael / ProudCity format first; fall back to the
            # numbered-bullet format used by Alameda / SF / Berkeley / many
            # other jurisdictions. Take the earliest match on the page so a
            # page containing e.g. "5. Item Title" and then a reference to
            # "Agenda Item No. 3" later picks up the structural header first.
            primary = self.AGENDA_ITEM_PATTERN.search(text)
            secondary = self.AGENDA_ITEM_NUMBERED_PATTERN.search(text)
            if primary and secondary:
                match = primary if primary.start() <= secondary.start() else secondary
            else:
                match = primary or secondary
            if match:
                # Save previous section
                if current_item or current_text:
                    sections.append(AgendaSection(
                        item_number=current_item or "preamble",
                        title=current_title or "Agenda Preamble",
                        page_start=current_start,
                        page_end=page_num,  # Previous page
                        text="\n".join(current_text),
                    ))

                # Start new section
                current_item = match.group(1)
                current_title = self._extract_title_around_match(text, match)
                current_start = page_num + 1
                current_text = [text]
            else:
                current_text.append(text)

        # Don't forget the trailing section.
        # If no marker matched anywhere, item_number stays None — label as
        # "unparsed" rather than the misleading "closing", which historically
        # led to ~30K chunks across the DB being tagged as if they were in
        # the closing section when they were actually the entire packet.
        if current_text:
            sections.append(AgendaSection(
                item_number=current_item or "unparsed",
                title=current_title or "Unparsed Section",
                page_start=current_start,
                page_end=len(doc),
                text="\n".join(current_text),
            ))

        return sections

    def _extract_pages_text(self, doc, start_page: int, end_page: int) -> str:
        """Extract text from a range of pages (1-indexed)."""
        texts = []
        for page_num in range(start_page - 1, end_page):  # Convert to 0-indexed
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                texts.append(page.get_text())
        return "\n\n".join(texts)

    def _extract_item_number(self, title: str) -> str | None:
        """Extract agenda item number from title string."""
        # Pattern for item numbers like "4.a", "5.b.i", "6.a"
        patterns = [
            r'(\d+\.[a-z](?:\.[ivx]+)?)',  # 4.a, 4.a.i
            r'(\d+[a-z])',  # 4a, 5b
            r'(?:Item\s*)(\d+)',  # Item 4
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).lower()

        return None

    def _extract_title_around_match(self, text: str, match) -> str:
        """Extract title text around an agenda item match."""
        start = match.end()
        # Look for next line or first 200 chars
        end = text.find('\n', start)
        if end == -1 or end - start > 200:
            end = start + 200

        title = text[start:end].strip()
        # Clean up common prefixes
        title = re.sub(r'^[:\s]+', '', title)
        return title[:150]  # Limit length

    def _chunk_section(
        self,
        section: AgendaSection,
        base_metadata: dict,
    ) -> Iterator[AgendaChunk]:
        """Split a section into RAG-friendly chunks."""
        text = section.text

        if not text.strip():
            return

        chunk_index = 0
        start = 0

        while start < len(text):
            end = start + self.max_chunk_size

            # Try to break at paragraph boundary
            if end < len(text):
                # Look for double newline (paragraph break) in last 300 chars
                search_start = max(start, end - 300)
                search_region = text[search_start:end]

                para_break = search_region.rfind('\n\n')
                if para_break > 100:  # Found a good break point
                    end = search_start + para_break
                else:
                    # Fall back to sentence boundary
                    sentence_end = max(
                        search_region.rfind('. '),
                        search_region.rfind('.\n'),
                    )
                    if sentence_end > 50:
                        end = search_start + sentence_end + 1

            chunk_text = text[start:end].strip()

            if chunk_text:
                yield AgendaChunk(
                    text=chunk_text,
                    agenda_item=section.item_number,
                    agenda_title=section.title,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    chunk_index=chunk_index,
                    total_chunks=0,  # Will be set after all chunks generated
                    metadata=base_metadata.copy(),
                )
                chunk_index += 1

            start = end - self.chunk_overlap
            if start < 0:
                start = 0
            if end >= len(text):
                break


def parse_agenda_packet(
    pdf_path: str | Path,
    output_json: str | Path | None = None,
    max_chunk_size: int = 1500,
) -> list[dict]:
    """
    Convenience function to parse an agenda packet PDF.

    Args:
        pdf_path: Path to PDF file
        output_json: Optional path to write JSON output
        max_chunk_size: Maximum chunk size for RAG

    Returns:
        List of chunk dictionaries
    """
    parser = AgendaPacketParser(max_chunk_size=max_chunk_size)
    chunks = parser.parse_to_chunks(pdf_path)

    result = [chunk.to_dict() for chunk in chunks]

    if output_json:
        output_json = Path(output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, 'w') as f:
            json.dump(result, f, indent=2)

    return result
