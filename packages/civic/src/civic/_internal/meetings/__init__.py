"""
Meeting document processing for RAG.

This module handles parsing and chunking of city council meeting materials
(agenda packets, minutes, staff reports) for retrieval-augmented generation.
"""

from .pdf_parser import AgendaPacketParser, AgendaChunk, AgendaSection, parse_agenda_packet
from .staff_report import StaffReportExtractor, StaffReportMetadata, extract_staff_report
from .ordinance import (
    OrdinanceExtractor,
    OrdinanceMetadata,
    OrdinanceSection,
    extract_shelter_ordinances,
)
from .minutes import (
    MinutesExtractor,
    MeetingMinutes,
    AgendaItemMinutes,
    VoteRecord,
    extract_meeting_minutes,
)
from .decision import (
    DecisionExtractor,
    Decision,
    VoteTally,
    LegalInstrument,
    PublicInput,
    StaffRecommendation,
    extract_decisions,
    # Roll call extraction
    extract_roll_call,
    extract_vote_tally,
    extract_motion_attribution,
    normalize_vote_names,
)
from .embeddings import (
    # New jurisdiction-based API
    CivicEmbeddings,
    SearchResult,
    build_civic_index,
    search_civic,
    # Deprecated aliases for backward compatibility
    MerrydaleEmbeddings,
    build_merrydale_index,
    search_merrydale,
)

__all__ = [
    "AgendaPacketParser",
    "AgendaChunk",
    "AgendaSection",
    "parse_agenda_packet",
    "StaffReportExtractor",
    "StaffReportMetadata",
    "extract_staff_report",
    "OrdinanceExtractor",
    "OrdinanceMetadata",
    "OrdinanceSection",
    "extract_shelter_ordinances",
    "MinutesExtractor",
    "MeetingMinutes",
    "AgendaItemMinutes",
    "VoteRecord",
    "extract_meeting_minutes",
    "DecisionExtractor",
    "Decision",
    "VoteTally",
    "LegalInstrument",
    "PublicInput",
    "StaffRecommendation",
    "extract_decisions",
    # Roll call extraction
    "extract_roll_call",
    "extract_vote_tally",
    "extract_motion_attribution",
    "normalize_vote_names",
    # New jurisdiction-based API
    "CivicEmbeddings",
    "SearchResult",
    "build_civic_index",
    "search_civic",
    # Deprecated aliases for backward compatibility
    "MerrydaleEmbeddings",
    "build_merrydale_index",
    "search_merrydale",
]
