"""
Federal programs corpus fetcher.

Fetches federal program data from HUD, EPA, DOT and other agencies.

Data Sources:
    - HUD: Community Development Block Grants, HOME, Housing Choice Vouchers
    - EPA: Clean Air Act programs, brownfield grants
    - DOT: Transportation funding programs

Note: This is a placeholder. The current civic-enrichment package uses
static JSON files for federal programs. This module will enable dynamic
fetching from federal APIs when available.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class FederalProgram:
    """Federal program metadata."""
    program_id: str
    name: str
    agency: str
    description: str
    funding_type: str  # "grant", "loan", "tax_credit"
    eligible_applicants: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    url: Optional[str] = None
    cfda_number: Optional[str] = None  # Catalog of Federal Domestic Assistance


class FederalCorpus:
    """
    Fetches federal program information.

    Currently supports static loading from JSON files.
    Future: API integration with USASpending.gov, Grants.gov.
    """

    def __init__(self, data_path: Optional[str] = None):
        """
        Initialize federal corpus.

        Args:
            data_path: Path to federal programs JSON files
        """
        self.data_path = data_path
        self._programs: dict[str, FederalProgram] = {}

    def load_from_json(self, path: str) -> int:
        """
        Load programs from JSON file.

        Args:
            path: Path to JSON file

        Returns:
            Number of programs loaded
        """
        import json

        with open(path) as f:
            data = json.load(f)

        programs = data.get("programs", [])
        for p in programs:
            program = FederalProgram(
                program_id=p.get("id", ""),
                name=p.get("name", ""),
                agency=p.get("agency", ""),
                description=p.get("description", ""),
                funding_type=p.get("funding_type", "grant"),
                eligible_applicants=p.get("eligible_applicants", []),
                topics=p.get("topics", []),
                url=p.get("url"),
                cfda_number=p.get("cfda_number"),
            )
            self._programs[program.program_id] = program

        return len(programs)

    def get_program(self, program_id: str) -> Optional[FederalProgram]:
        """Get a specific program by ID."""
        return self._programs.get(program_id)

    def search_by_topic(self, topic: str) -> list[FederalProgram]:
        """Find programs matching a topic."""
        topic_lower = topic.lower()
        return [
            p for p in self._programs.values()
            if any(topic_lower in t.lower() for t in p.topics)
        ]

    def all_programs(self) -> list[FederalProgram]:
        """Get all loaded programs."""
        return list(self._programs.values())
