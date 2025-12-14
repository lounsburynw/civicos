"""
Staff report extraction from agenda packet chunks.

Extracts structured metadata from city council staff reports including
department, authors, recommendations, and key sections.
"""

from dataclasses import dataclass, field
from typing import Optional
import re
import json
from pathlib import Path


@dataclass
class StaffReportMetadata:
    """Structured metadata extracted from a staff report."""

    agenda_item: str
    meeting_date: str
    department: str
    prepared_by: list[str]
    topic: str
    recommendation: str
    executive_summary: str
    property_address: Optional[str] = None
    property_apns: Optional[list[str]] = None
    financial_amount: Optional[str] = None
    page_start: int = 0
    page_end: int = 0
    total_chunks: int = 0

    def to_dict(self) -> dict:
        return {
            "agenda_item": self.agenda_item,
            "meeting_date": self.meeting_date,
            "department": self.department,
            "prepared_by": self.prepared_by,
            "topic": self.topic,
            "recommendation": self.recommendation,
            "executive_summary": self.executive_summary,
            "property_address": self.property_address,
            "property_apns": self.property_apns,
            "financial_amount": self.financial_amount,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "total_chunks": self.total_chunks,
        }


class StaffReportExtractor:
    """
    Extract structured metadata from staff report chunks.

    San Rafael staff reports have a consistent format:
    - Header: Department, Prepared by, Meeting Date, Agenda Item
    - TOPIC: Brief title
    - SUBJECT: Detailed actions
    - RECOMMENDATION: Staff recommendations
    - EXECUTIVE SUMMARY: Brief overview
    - BACKGROUND: Context and analysis
    """

    # Regex patterns for extracting fields
    PATTERNS = {
        "agenda_item": re.compile(
            r'Agenda\s+Item\s+No[.:]\s*(\d+\.[a-z])',
            re.IGNORECASE
        ),
        "meeting_date": re.compile(
            r'Meeting\s+Date[.:]\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
            re.IGNORECASE
        ),
        "department": re.compile(
            r'Department[.:]\s*([^\n]+)',
            re.IGNORECASE
        ),
        "prepared_by": re.compile(
            r'Prepared\s+by[.:]\s*(.*?)(?=City\s+Manager\s+Approval|TOPIC|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "topic": re.compile(
            r'TOPIC[.:]\s*(.*?)(?=SUBJECT|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "recommendation": re.compile(
            r'RECOMMENDATION[.:]\s*(.*?)(?=EXECUTIVE\s+SUMMARY|BACKGROUND|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "executive_summary": re.compile(
            r'EXECUTIVE\s+SUMMARY[.:]\s*(.*?)(?=BACKGROUND|$)',
            re.IGNORECASE | re.DOTALL
        ),
        "property_address": re.compile(
            r'(?:property\s+(?:located\s+)?at|located\s+at)\s+(\d+[^(,\n]+)',
            re.IGNORECASE
        ),
        "apn": re.compile(
            r'[\d]{3}-[\d]{3}-[\d]{2}',
            re.IGNORECASE
        ),
        "financial_amount": re.compile(
            r'\$[\d,]+(?:\.\d{2})?\s*(?:million|M)?',
            re.IGNORECASE
        ),
    }

    def __init__(self):
        pass

    def extract_from_chunks(
        self,
        chunks: list[dict],
        agenda_item: str,
    ) -> StaffReportMetadata:
        """
        Extract staff report metadata from chunks for a specific agenda item.

        Args:
            chunks: List of chunk dictionaries from AgendaPacketParser
            agenda_item: The agenda item to extract (e.g., "6.a")

        Returns:
            StaffReportMetadata with extracted fields
        """
        # Filter to chunks for this agenda item
        item_chunks = [c for c in chunks if c.get("agenda_item") == agenda_item]

        if not item_chunks:
            raise ValueError(f"No chunks found for agenda item {agenda_item}")

        # Combine first N chunks to get header content
        # Staff report header is typically in first 5-10 chunks
        header_text = "\n".join(c["text"] for c in item_chunks[:10])

        # Extract basic metadata from header
        metadata = self._extract_header_fields(header_text)

        # Add chunk statistics
        metadata["page_start"] = item_chunks[0].get("page_start", 0)
        metadata["page_end"] = item_chunks[0].get("page_end", 0)
        metadata["total_chunks"] = len(item_chunks)

        # Set agenda item explicitly
        metadata["agenda_item"] = agenda_item

        return StaffReportMetadata(**metadata)

    def _extract_header_fields(self, text: str) -> dict:
        """Extract all header fields from combined text."""
        result = {
            "agenda_item": "",
            "meeting_date": "",
            "department": "",
            "prepared_by": [],
            "topic": "",
            "recommendation": "",
            "executive_summary": "",
            "property_address": None,
            "property_apns": None,
            "financial_amount": None,
        }

        # Agenda Item
        if match := self.PATTERNS["agenda_item"].search(text):
            result["agenda_item"] = match.group(1)

        # Meeting Date
        if match := self.PATTERNS["meeting_date"].search(text):
            result["meeting_date"] = match.group(1).strip()

        # Department
        if match := self.PATTERNS["department"].search(text):
            result["department"] = match.group(1).strip()

        # Prepared By (multiple people)
        if match := self.PATTERNS["prepared_by"].search(text):
            raw = match.group(1)
            result["prepared_by"] = self._parse_authors(raw)

        # Topic
        if match := self.PATTERNS["topic"].search(text):
            result["topic"] = self._clean_text(match.group(1))

        # Recommendation
        if match := self.PATTERNS["recommendation"].search(text):
            result["recommendation"] = self._clean_text(match.group(1))

        # Executive Summary
        if match := self.PATTERNS["executive_summary"].search(text):
            result["executive_summary"] = self._clean_text(match.group(1))

        # Property Address
        if match := self.PATTERNS["property_address"].search(text):
            result["property_address"] = match.group(1).strip()

        # APNs (find all unique)
        apns = self.PATTERNS["apn"].findall(text)
        if apns:
            result["property_apns"] = list(dict.fromkeys(apns))  # Unique, preserve order

        # Financial amounts (largest)
        amounts = self.PATTERNS["financial_amount"].findall(text)
        if amounts:
            # Get the largest amount mentioned
            result["financial_amount"] = self._largest_amount(amounts)

        return result

    def _parse_authors(self, raw: str) -> list[str]:
        """Parse author names and titles from prepared_by field."""
        authors = []

        # Clean up whitespace
        raw = re.sub(r'\s+', ' ', raw).strip()

        # Split on common patterns
        # Names often followed by titles/departments
        lines = re.split(r'\n|(?=[A-Z][a-z]+\s+[A-Z][a-z]+,)', raw)

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for "Name, Title" or "Name\nTitle" patterns
            if ',' in line:
                parts = line.split(',', 1)
                name = parts[0].strip()
                if name and len(name) > 2 and not name.isupper():
                    # Looks like a name
                    title = parts[1].strip() if len(parts) > 1 else ""
                    if title:
                        authors.append(f"{name}, {title}")
                    else:
                        authors.append(name)
            elif re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+', line):
                # Standalone name
                authors.append(line.split('\n')[0].strip())

        return authors if authors else ["Unknown"]

    def _clean_text(self, text: str) -> str:
        """Clean extracted text by normalizing whitespace."""
        # Replace bullet characters with dash
        text = text.replace('\uf0a7', '-')
        # Replace multiple whitespace with single space
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove duplicate sentences that occur due to chunk overlap
        text = self._remove_duplicates(text)
        # Truncate if too long
        if len(text) > 2000:
            text = text[:2000] + "..."
        return text

    def _remove_duplicates(self, text: str) -> str:
        """Remove duplicate sentences from text (caused by chunk overlap)."""
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        seen = set()
        result = []
        for sentence in sentences:
            # Normalize for comparison
            normalized = sentence.lower().strip()
            if normalized not in seen and len(normalized) > 10:
                seen.add(normalized)
                result.append(sentence)
        return ' '.join(result)

    def _largest_amount(self, amounts: list[str]) -> str:
        """Find the largest dollar amount from a list."""
        def parse_amount(s: str) -> float:
            # Remove $ and commas
            s = s.replace('$', '').replace(',', '').strip()
            # Handle "million" or "M"
            if 'million' in s.lower() or s.endswith('M'):
                s = re.sub(r'[Mm]illion|M$', '', s)
                return float(s) * 1_000_000
            return float(s)

        try:
            parsed = [(a, parse_amount(a)) for a in amounts]
            return max(parsed, key=lambda x: x[1])[0]
        except (ValueError, IndexError):
            return amounts[0] if amounts else None


def extract_staff_report(
    chunks_file: str | Path,
    agenda_item: str,
    output_file: str | Path | None = None,
) -> dict:
    """
    Convenience function to extract staff report metadata.

    Args:
        chunks_file: Path to JSON file with chunks
        agenda_item: Agenda item to extract (e.g., "6.a")
        output_file: Optional path to write JSON output

    Returns:
        Dictionary with staff report metadata
    """
    chunks_file = Path(chunks_file)

    with open(chunks_file) as f:
        chunks = json.load(f)

    extractor = StaffReportExtractor()
    metadata = extractor.extract_from_chunks(chunks, agenda_item)
    result = metadata.to_dict()

    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

    return result
