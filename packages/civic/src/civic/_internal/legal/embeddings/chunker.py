"""
Legal-aware document chunking.

Legal documents have specific structure (sections, subsections, amendments)
that should be preserved during chunking for better retrieval.

Strategies:
1. Section-based: Split on legal section markers (SEC., SECTION, (a), (1))
2. Semantic: Use heading detection + paragraph boundaries
3. Hybrid: Section-based with size limits and overlap
"""

from dataclasses import dataclass
from typing import Iterator
import re


@dataclass
class Chunk:
    """A chunk of legal text with metadata."""
    text: str
    source_id: str  # Bill ID or document ID
    section: str  # Section identifier
    chunk_index: int
    start_char: int
    end_char: int
    metadata: dict


class LegalChunker:
    """
    Splits legal documents into chunks for embedding.

    Preserves legal structure by detecting:
    - Section headers (SEC. 1., SECTION 1234)
    - Subsections ((a), (b), (1), (2))
    - Amendment markers
    - Definitions sections
    """

    # Patterns for legal section detection
    SECTION_PATTERNS = [
        r"(?:SEC(?:TION)?\.?\s*)(\d+(?:\.\d+)*)",  # SEC. 1, SECTION 1.2
        r"(?:Article\s+)([IVXLC]+|\d+)",  # Article IV, Article 5
        r"(?:Chapter\s+)(\d+(?:\.\d+)*)",  # Chapter 1, Chapter 1.5
    ]

    SUBSECTION_PATTERN = r"^\s*\(([a-z]|\d+)\)"  # (a), (1)

    def __init__(
        self,
        max_chunk_size: int = 1000,
        overlap: int = 100,
        preserve_sections: bool = True,
    ):
        """
        Initialize chunker.

        Args:
            max_chunk_size: Maximum characters per chunk
            overlap: Character overlap between chunks
            preserve_sections: Try to keep sections together
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.preserve_sections = preserve_sections

    def chunk_document(
        self,
        text: str,
        source_id: str,
        metadata: dict | None = None,
    ) -> Iterator[Chunk]:
        """
        Split a legal document into chunks.

        Args:
            text: Full document text
            source_id: Document identifier (e.g., bill ID)
            metadata: Additional metadata to include

        Yields:
            Chunk objects
        """
        metadata = metadata or {}

        if self.preserve_sections:
            yield from self._chunk_by_sections(text, source_id, metadata)
        else:
            yield from self._chunk_by_size(text, source_id, metadata)

    def _chunk_by_sections(
        self,
        text: str,
        source_id: str,
        metadata: dict,
    ) -> Iterator[Chunk]:
        """Split on section boundaries, then by size if needed."""
        sections = self._detect_sections(text)

        chunk_index = 0
        for section_name, section_text, start_pos in sections:
            # If section is small enough, yield as single chunk
            if len(section_text) <= self.max_chunk_size:
                yield Chunk(
                    text=section_text,
                    source_id=source_id,
                    section=section_name,
                    chunk_index=chunk_index,
                    start_char=start_pos,
                    end_char=start_pos + len(section_text),
                    metadata=metadata,
                )
                chunk_index += 1
            else:
                # Split large sections with overlap
                for sub_chunk in self._chunk_by_size(
                    section_text, source_id, metadata, section_name, start_pos
                ):
                    sub_chunk.chunk_index = chunk_index
                    yield sub_chunk
                    chunk_index += 1

    def _chunk_by_size(
        self,
        text: str,
        source_id: str,
        metadata: dict,
        section: str = "unknown",
        base_offset: int = 0,
    ) -> Iterator[Chunk]:
        """Simple size-based chunking with overlap."""
        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + self.max_chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence end within last 100 chars
                search_region = text[max(start, end - 100):end]
                sentence_end = max(
                    search_region.rfind(". "),
                    search_region.rfind(".\n"),
                )
                if sentence_end > 0:
                    end = max(start, end - 100) + sentence_end + 1

            chunk_text = text[start:end].strip()

            if chunk_text:
                yield Chunk(
                    text=chunk_text,
                    source_id=source_id,
                    section=section,
                    chunk_index=chunk_index,
                    start_char=base_offset + start,
                    end_char=base_offset + end,
                    metadata=metadata,
                )
                chunk_index += 1

            start = end - self.overlap

    def _detect_sections(self, text: str) -> list[tuple[str, str, int]]:
        """
        Detect section boundaries in legal text.

        Returns:
            List of (section_name, section_text, start_position)
        """
        sections = []
        current_section = "preamble"
        current_start = 0
        current_text = []

        for line_start, line in self._iter_lines_with_pos(text):
            # Check for section header
            new_section = self._detect_section_header(line)

            if new_section and current_text:
                # Save previous section
                section_text = "\n".join(current_text)
                sections.append((current_section, section_text, current_start))

                # Start new section
                current_section = new_section
                current_start = line_start
                current_text = [line]
            else:
                current_text.append(line)

        # Don't forget last section
        if current_text:
            section_text = "\n".join(current_text)
            sections.append((current_section, section_text, current_start))

        return sections

    def _detect_section_header(self, line: str) -> str | None:
        """Check if line is a section header."""
        for pattern in self.SECTION_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return f"section_{match.group(1)}"
        return None

    def _iter_lines_with_pos(self, text: str) -> Iterator[tuple[int, str]]:
        """Iterate over lines with their starting positions."""
        pos = 0
        for line in text.split("\n"):
            yield pos, line
            pos += len(line) + 1
