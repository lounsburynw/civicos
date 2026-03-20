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


import logging

logger = logging.getLogger(__name__)


def expand_municipal_code_to_chunks(
    sections: list[dict],
    max_chunk_size: int = 1500,
    overlap: int = 100,
) -> list[dict]:
    """
    Expand municipal code sections into semantic chunks for embedding.

    This is the canonical function for chunking municipal code before vector indexing.
    It uses LegalChunker to create appropriately-sized chunks that preserve
    section structure and legal context.

    Args:
        sections: List of municipal code section dicts from storage backend
                  (via get_municipal_code). Each dict should have:
                  - section_number: str
                  - section_name: str (optional)
                  - chapter: str (optional)
                  - full_text or content: str (the section text)
        max_chunk_size: Maximum characters per chunk (default 1500)
        overlap: Character overlap between chunks for context (default 100)

    Returns:
        List of chunk dicts ready for indexing, each containing:
        - id: "mc-{section_number}-{chunk_index}"
        - text: Chunk text with section header context
        - section_number, section_name, chapter, metadata
    """
    chunker = LegalChunker(
        max_chunk_size=max_chunk_size,
        overlap=overlap,
        preserve_sections=True,  # Preserve legal structure
    )

    all_chunks = []

    for section in sections:
        section_number = section.get("section_number", "")
        if not section_number:
            continue

        # Get the full text (use full_text field, fallback to content for compat)
        full_text = section.get("full_text") or section.get("content")
        if not full_text:
            continue

        # Build section header for context
        header_parts = []
        if section_number:
            header_parts.append(f"Section {section_number}")
        if section.get("section_name"):
            header_parts.append(f": {section['section_name']}")
        if section.get("chapter"):
            header_parts.append(f" (Chapter {section['chapter']})")
        section_header = "".join(header_parts)

        # Create source_id for chunk tracking
        # Use section_number (stable across re-fetches) as the canonical ID.
        # Database UUIDs change on every temporal version, which causes duplicate
        # vectors since ON CONFLICT (id) never matches old chunk IDs.
        # section_number is unique within a jurisdiction and stable over time.
        source_id = f"mc-{section_number}"

        # Metadata to preserve across chunks
        base_metadata = {
            "section_number": section_number,
            "section_name": section.get("section_name"),
            "chapter": section.get("chapter"),
            "db_id": section.get("id"),  # Traceback to source row (UUID, changes per fetch)
        }

        # Chunk the section text
        chunks = list(chunker.chunk_document(
            text=full_text,
            source_id=source_id,
            metadata=base_metadata,
        ))

        if not chunks:
            # Section was empty or couldn't be chunked - create single chunk
            logger.warning(f"No chunks generated for section {section_number}")
            continue

        # Convert Chunk objects to indexable dicts
        for chunk in chunks:
            # Include section header in first chunk for context
            if chunk.chunk_index == 0:
                chunk_text = f"{section_header}\n{chunk.text}"
            else:
                # For subsequent chunks, include brief context
                chunk_text = f"[{section_header} continued]\n{chunk.text}"

            chunk_dict = {
                "id": f"{source_id}-{chunk.chunk_index}",
                "text": chunk_text,
                "section_number": section_number,
                "section_name": section.get("section_name"),
                "chapter": section.get("chapter"),
                "chunk_index": chunk.chunk_index,
                "total_chunks": len(chunks),
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "section": chunk.section,  # Internal section detection from LegalChunker
                "metadata": chunk.metadata,
            }
            all_chunks.append(chunk_dict)

        logger.debug(
            f"Chunked municipal code section {section_number}: {len(chunks)} chunks "
            f"from {len(full_text)} chars"
        )

    logger.info(
        f"Expanded {len(sections)} municipal code sections into {len(all_chunks)} chunks"
    )
    return all_chunks


def expand_legislation_to_chunks(
    bills: list[dict],
    max_chunk_size: int = 1500,
    overlap: int = 100,
) -> list[dict]:
    """
    Expand legislation bills into semantic chunks for embedding.

    This is the canonical function for chunking legislation before vector indexing.
    It uses LegalChunker to create appropriately-sized chunks that preserve
    bill structure and legal context.

    Args:
        bills: List of legislation bill dicts from storage backend
               (via get_legislation). Each dict should have:
               - bill_id: str
               - bill_number: str
               - bill_name: str (optional)
               - full_text: str (the bill text to chunk)
               - topic, status, leverage_point, keywords: (optional metadata)
        max_chunk_size: Maximum characters per chunk (default 1500)
        overlap: Character overlap between chunks for context (default 100)

    Returns:
        List of chunk dicts ready for indexing, each containing:
        - id: "leg-{bill_id}-{chunk_index}"
        - text: Chunk text with bill header context
        - bill_id, bill_number, bill_name, topic, status, etc.
    """
    chunker = LegalChunker(
        max_chunk_size=max_chunk_size,
        overlap=overlap,
        preserve_sections=True,  # Preserve legal structure
    )

    all_chunks = []

    for bill in bills:
        bill_id = bill.get("bill_id", "")
        if not bill_id:
            continue

        # Get the full text
        full_text = bill.get("full_text")
        if not full_text:
            # No full_text available - skip this bill for chunking
            # (caller should handle bills without full_text separately)
            continue

        # Build bill header for context
        header_parts = []
        if bill.get("bill_number"):
            header_parts.append(f"Bill {bill['bill_number']}")
        if bill.get("bill_name"):
            header_parts.append(f": {bill['bill_name']}")
        bill_header = "".join(header_parts) if header_parts else f"Bill {bill_id}"

        # Create source_id for chunk tracking
        source_id = f"leg-{bill_id}"

        # Metadata to preserve across chunks
        base_metadata = {
            "bill_id": bill_id,
            "bill_number": bill.get("bill_number"),
            "bill_name": bill.get("bill_name"),
            "topic": bill.get("topic"),
            "status": bill.get("status"),
            "leverage_point": bill.get("leverage_point"),
            "keywords": bill.get("keywords"),
        }

        # Chunk the bill text
        chunks = list(chunker.chunk_document(
            text=full_text,
            source_id=source_id,
            metadata=base_metadata,
        ))

        if not chunks:
            # Bill was empty or couldn't be chunked - create single chunk
            logger.warning(f"No chunks generated for bill {bill_id}")
            continue

        # Convert Chunk objects to indexable dicts
        for chunk in chunks:
            # Include bill header in first chunk for context
            if chunk.chunk_index == 0:
                chunk_text = f"{bill_header}\n{chunk.text}"
            else:
                # For subsequent chunks, include brief context
                chunk_text = f"[{bill_header} continued]\n{chunk.text}"

            chunk_dict = {
                "id": f"{source_id}-{chunk.chunk_index}",
                "text": chunk_text,
                "bill_id": bill_id,
                "bill_number": bill.get("bill_number"),
                "bill_name": bill.get("bill_name"),
                "topic": bill.get("topic"),
                "status": bill.get("status"),
                "leverage_point": bill.get("leverage_point"),
                "keywords": bill.get("keywords"),
                "chunk_index": chunk.chunk_index,
                "total_chunks": len(chunks),
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "section": chunk.section,  # Internal section detection from LegalChunker
                "metadata": chunk.metadata,
            }
            all_chunks.append(chunk_dict)

        logger.debug(
            f"Chunked legislation bill {bill_id}: {len(chunks)} chunks "
            f"from {len(full_text)} chars"
        )

    logger.info(
        f"Expanded {len(bills)} legislation bills into {len(all_chunks)} chunks"
    )
    return all_chunks


def expand_codified_law_to_chunks(
    sections: list[dict],
    max_chunk_size: int = 1500,
    overlap: int = 100,
) -> list[dict]:
    """
    Expand codified law sections into semantic chunks for embedding.

    This is the canonical function for chunking codified law before vector indexing.
    It handles U.S. Code, state codes (e.g., California), and CFR (Code of Federal
    Regulations) sections.

    Args:
        sections: List of codified law section dicts from storage backend
                  (via get_codified_law). Each dict should have:
                  - id: Database ID
                  - citation: Full citation (e.g., "42 U.S.C. § 1983")
                  - title_number: int
                  - title_name: str
                  - section_number: str
                  - heading: str (section heading)
                  - text: str (the section text to chunk)
                  - jurisdiction_id: str (e.g., "federal-US", "state-CA", "federal-CFR")
                  - chapter, subchapter: (optional hierarchy)
        max_chunk_size: Maximum characters per chunk (default 1500)
        overlap: Character overlap between chunks for context (default 100)

    Returns:
        List of chunk dicts ready for indexing, each containing:
        - id: "cl-{db_id}-{chunk_index}"
        - text: Chunk text with section header context
        - citation, title_number, title_name, section_number, jurisdiction_id, etc.
    """
    chunker = LegalChunker(
        max_chunk_size=max_chunk_size,
        overlap=overlap,
        preserve_sections=True,
    )

    all_chunks = []

    for section in sections:
        db_id = section.get("id")
        if not db_id:
            continue

        # Get the full text
        full_text = section.get("text")
        if not full_text:
            continue

        # Build section header for context
        # Example: "42 U.S.C. § 1983: Civil action for deprivation of rights"
        header_parts = []
        if section.get("citation"):
            header_parts.append(section["citation"])
        elif section.get("title_number") and section.get("section_number"):
            header_parts.append(f"{section['title_number']} § {section['section_number']}")
        if section.get("heading"):
            header_parts.append(f": {section['heading']}")
        section_header = "".join(header_parts) if header_parts else f"Section {db_id}"

        # Create source_id for chunk tracking
        source_id = f"cl-{db_id}"

        # Metadata to preserve across chunks
        base_metadata = {
            "db_id": db_id,
            "citation": section.get("citation"),
            "title_number": section.get("title_number"),
            "title_name": section.get("title_name"),
            "section_number": section.get("section_number"),
            "heading": section.get("heading"),
            "jurisdiction_id": section.get("jurisdiction_id"),
            "chapter": section.get("chapter"),
            "subchapter": section.get("subchapter"),
            "identifier": section.get("identifier"),
        }

        # Chunk the section text
        chunks = list(chunker.chunk_document(
            text=full_text,
            source_id=source_id,
            metadata=base_metadata,
        ))

        if not chunks:
            logger.warning(f"No chunks generated for codified law section {db_id}")
            continue

        # Convert Chunk objects to indexable dicts
        for chunk in chunks:
            if chunk.chunk_index == 0:
                chunk_text = f"{section_header}\n{chunk.text}"
            else:
                chunk_text = f"[{section_header} continued]\n{chunk.text}"

            chunk_dict = {
                "id": f"{source_id}-{chunk.chunk_index}",
                "text": chunk_text,
                "citation": section.get("citation"),
                "title_number": section.get("title_number"),
                "title_name": section.get("title_name"),
                "section_number": section.get("section_number"),
                "heading": section.get("heading"),
                "jurisdiction_id": section.get("jurisdiction_id"),
                "chapter": section.get("chapter"),
                "subchapter": section.get("subchapter"),
                "chunk_index": chunk.chunk_index,
                "total_chunks": len(chunks),
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "section": chunk.section,
                "metadata": chunk.metadata,
            }
            all_chunks.append(chunk_dict)

        logger.debug(
            f"Chunked codified law section {db_id}: {len(chunks)} chunks "
            f"from {len(full_text)} chars"
        )

    logger.info(
        f"Expanded {len(sections)} codified law sections into {len(all_chunks)} chunks"
    )
    return all_chunks


def expand_executive_orders_to_chunks(
    orders: list[dict],
    max_chunk_size: int = 1500,
    overlap: int = 100,
) -> list[dict]:
    """
    Expand Executive Orders into semantic chunks for embedding.

    This is the canonical function for chunking Executive Orders before vector indexing.

    Args:
        orders: List of EO dicts from storage backend (via get_executive_orders).
                Each dict should have:
                - id: Database ID
                - eo_number: int (e.g., 14067)
                - title: str
                - signing_date: date
                - president: str
                - full_text: str (the order text to chunk)
                - status: str ("active", "revoked", "superseded")
        max_chunk_size: Maximum characters per chunk (default 1500)
        overlap: Character overlap between chunks for context (default 100)

    Returns:
        List of chunk dicts ready for indexing, each containing:
        - id: "eo-{db_id}-{chunk_index}"
        - text: Chunk text with EO header context
        - eo_number, title, president, signing_date, status, etc.
    """
    chunker = LegalChunker(
        max_chunk_size=max_chunk_size,
        overlap=overlap,
        preserve_sections=True,
    )

    all_chunks = []

    for order in orders:
        db_id = order.get("id")
        if not db_id:
            continue

        # Get the full text
        full_text = order.get("full_text")
        if not full_text:
            continue

        # Build EO header for context
        # Example: "Executive Order 14067: Ensuring Responsible Development of Digital Assets"
        eo_number = order.get("eo_number")
        header_parts = []
        if eo_number:
            header_parts.append(f"Executive Order {eo_number}")
        if order.get("title"):
            header_parts.append(f": {order['title']}")
        eo_header = "".join(header_parts) if header_parts else f"Executive Order {db_id}"

        # Create source_id for chunk tracking
        source_id = f"eo-{db_id}"

        # Metadata to preserve across chunks
        base_metadata = {
            "db_id": db_id,
            "eo_number": eo_number,
            "title": order.get("title"),
            "president": order.get("president"),
            "signing_date": order.get("signing_date"),
            "status": order.get("status"),
        }

        # Chunk the order text
        chunks = list(chunker.chunk_document(
            text=full_text,
            source_id=source_id,
            metadata=base_metadata,
        ))

        if not chunks:
            logger.warning(f"No chunks generated for EO {eo_number or db_id}")
            continue

        # Convert Chunk objects to indexable dicts
        for chunk in chunks:
            if chunk.chunk_index == 0:
                chunk_text = f"{eo_header}\n{chunk.text}"
            else:
                chunk_text = f"[{eo_header} continued]\n{chunk.text}"

            chunk_dict = {
                "id": f"{source_id}-{chunk.chunk_index}",
                "text": chunk_text,
                "eo_number": eo_number,
                "title": order.get("title"),
                "president": order.get("president"),
                "signing_date": order.get("signing_date"),
                "status": order.get("status"),
                "chunk_index": chunk.chunk_index,
                "total_chunks": len(chunks),
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "section": chunk.section,
                "metadata": chunk.metadata,
            }
            all_chunks.append(chunk_dict)

        logger.debug(
            f"Chunked EO {eo_number or db_id}: {len(chunks)} chunks "
            f"from {len(full_text)} chars"
        )

    logger.info(
        f"Expanded {len(orders)} Executive Orders into {len(all_chunks)} chunks"
    )
    return all_chunks


def expand_federal_rules_to_chunks(rules: list[dict]) -> list[dict]:
    """
    Expand federal rules into chunks for vector embedding.

    Federal rules (proposed rules, final rules, notices) are typically short enough
    to embed as single chunks. This function builds rich text from available fields
    to maximize search relevance, including fallbacks for rules missing title/abstract.

    Args:
        rules: List of rule dicts from storage backend (via get_federal_rules).
               Expected fields: document_number, title, abstract, agency_names,
               document_type, publication_date, comments_close_on, topics,
               comment_url, html_url.

    Returns:
        List of chunk dicts ready for indexing.
    """
    chunks = []
    skipped = 0

    for rule in rules:
        doc_num = rule.get("document_number") or rule.get("id")
        if not doc_num:
            skipped += 1
            continue

        # Build text from all available fields
        parts = []

        # Agency context
        agencies = rule.get("agency_names") or []
        if isinstance(agencies, str):
            agencies = [agencies]
        if agencies:
            parts.append(f"Agency: {', '.join(agencies)}")

        # Document type context
        doc_type = rule.get("document_type", "")
        type_label = {
            "proposed_rule": "Proposed Rule",
            "final_rule": "Final Rule",
            "notice": "Notice",
        }.get(doc_type, doc_type.replace("_", " ").title() if doc_type else "")
        if type_label:
            parts.append(f"Type: {type_label}")

        # Title and abstract (primary content)
        if rule.get("title"):
            parts.append(rule["title"])
        if rule.get("abstract"):
            parts.append(rule["abstract"])

        # Topics for search relevance
        topics = rule.get("topics") or []
        if isinstance(topics, str):
            topics = [topics]
        if topics:
            parts.append(f"Topics: {', '.join(topics)}")

        # Comment period info
        if rule.get("comments_close_on"):
            parts.append(f"Comments close: {rule['comments_close_on']}")

        # Local relevance context for semantic search
        relevance_reasons = rule.get("relevance_reasons") or []
        if relevance_reasons:
            # Extract human-readable reasons
            readable = []
            for r in relevance_reasons:
                if r.startswith("agency_topic:"):
                    readable.append(r.split(":", 1)[1].replace("_", " "))
                elif r.startswith("geo:"):
                    readable.append(r.split(":", 1)[1])
                elif r.startswith("cfr:"):
                    readable.append(f"CFR Title {r.split(':', 1)[1]}")
            if readable:
                parts.append(f"Local relevance: {', '.join(readable)}")

        text = "\n".join(parts)

        # Fallback: if no title/abstract/topics, use document number as minimal text
        if not text.strip():
            text = f"Federal Register Document {doc_num}"
            if type_label:
                text = f"{type_label}: {text}"

        chunks.append({
            "id": f"rule-{doc_num}",
            "text": text,
            "title": rule.get("title"),
            "document_type": doc_type,
            "publication_date": rule.get("publication_date"),
            "comments_close_on": rule.get("comments_close_on"),
            "metadata": {
                "document_number": doc_num,
                "agency_names": agencies,
                "html_url": rule.get("html_url"),
            },
        })

    if skipped:
        logger.warning(f"Skipped {skipped} rules with no document_number")

    logger.info(
        f"Expanded {len(rules)} federal rules into {len(chunks)} chunks "
        f"({skipped} skipped)"
    )
    return chunks
