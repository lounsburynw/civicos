#!/usr/bin/env python3
"""
Minutes Parser - Extract testimony data from meeting minutes PDFs

Extracts structured data from meeting minutes:
- Testimony counts (number of public speakers per agenda item)
- Speaker names
- Vote results (yes/no/abstain)
- Whether decision passed
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json

from ..core.llm_provider import get_model_for_task


@dataclass
class TestimonyData:
    """Structured testimony data extracted from minutes"""
    item_ref: str  # e.g., "5.g"
    testimony_count: Optional[int] = None
    speaker_names: List[str] = None
    vote_results: Optional[Dict[str, int]] = None  # {"yes": N, "no": N, "abstain": N}
    passed: bool = True

    def __post_init__(self):
        if self.speaker_names is None:
            self.speaker_names = []
        if self.vote_results is None:
            self.vote_results = {}


@dataclass
class MeetingAttendees:
    """Meeting attendees extracted from minutes roll call"""
    council_members_present: List[Dict[str, str]] = None  # [{"name": "Kate Colin", "title": "Mayor"}]
    council_members_absent: List[str] = None
    staff_present: List[Dict[str, str]] = None  # [{"name": "Cristine Alilovich", "title": "City Manager"}]

    def __post_init__(self):
        if self.council_members_present is None:
            self.council_members_present = []
        if self.council_members_absent is None:
            self.council_members_absent = []
        if self.staff_present is None:
            self.staff_present = []


class MinutesParser:
    """Parse meeting minutes to extract testimony and vote data"""

    def __init__(self, model: Optional[str] = None):
        """Initialize with LLM model for parsing"""
        # Use Gemini Flash for fast, cheap parsing
        self.model = model or 'gemini-2.0-flash-exp'

    def extract_meeting_attendees(self, minutes_text: str) -> MeetingAttendees:
        """
        Extract meeting attendees from minutes roll call section

        Args:
            minutes_text: Full text of meeting minutes

        Returns:
            MeetingAttendees with council members and staff
        """
        prompt = f"""Extract the meeting attendees from these minutes.

MINUTES TEXT:
{minutes_text[:5000]}

Look for the roll call section at the beginning that lists:
1. **Present**: Council members who attended
2. **Absent**: Council members who were absent
3. **Also Present**: Staff members present

Extract each person with their full name and title/role.

For council members, look for patterns like:
- "Mayor Kate" → {{"name": "Kate [LastName]", "title": "Mayor"}}
- "Vice Mayor Bushey" → {{"name": "[FirstName] Bushey", "title": "Vice Mayor"}}
- "Councilmember Hill" → {{"name": "[FirstName] Hill", "title": "Councilmember"}}

For staff, look for:
- "City Manager [Name]" → {{"name": "[Full Name]", "title": "City Manager"}}
- "City Clerk [Name]" → {{"name": "[Full Name]", "title": "City Clerk"}}
- "City Attorney [Name]" → {{"name": "[Full Name]", "title": "City Attorney"}}

Return ONLY valid JSON in this exact format:
{{
  "council_members_present": [
    {{"name": "Full Name", "title": "Mayor"}},
    {{"name": "Full Name", "title": "Vice Mayor"}},
    {{"name": "Full Name", "title": "Councilmember"}}
  ],
  "council_members_absent": ["Full Name"],
  "staff_present": [
    {{"name": "Full Name", "title": "City Manager"}},
    {{"name": "Full Name", "title": "City Clerk"}}
  ]
}}

If roll call section not found, return empty arrays.
"""

        try:
            # Get LLM provider
            provider = get_model_for_task('short_structured')

            # Get response
            response = provider.complete([
                {"role": "system", "content": "You are a meeting minutes parser. Extract structured data from meeting minutes and return valid JSON only."},
                {"role": "user", "content": prompt}
            ])

            # Parse JSON response
            response_text = response.content.strip()
            if response_text.startswith('```'):
                response_text = re.sub(r'^```(?:json)?\s*\n', '', response_text)
                response_text = re.sub(r'\n```\s*$', '', response_text)

            data = json.loads(response_text)

            return MeetingAttendees(
                council_members_present=data.get('council_members_present', []),
                council_members_absent=data.get('council_members_absent', []),
                staff_present=data.get('staff_present', [])
            )

        except Exception as e:
            print(f"⚠️  Failed to extract meeting attendees: {type(e).__name__}: {e}")
            return MeetingAttendees()

    def extract_testimony_for_item(
        self,
        minutes_text: str,
        item_ref: str
    ) -> TestimonyData:
        """
        Extract testimony data for a specific agenda item from minutes text

        Args:
            minutes_text: Full text of meeting minutes
            item_ref: Agenda item reference (e.g., "5.g", "7.a")

        Returns:
            TestimonyData with extracted information
        """
        # Create extraction prompt
        prompt = f"""Extract testimony and vote data for agenda item {item_ref} from these meeting minutes.

MINUTES TEXT:
{minutes_text}

Find the section for item {item_ref} and extract:

1. **Testimony Count**: How many public speakers spoke on this item?
   - Look for phrases like "4 speakers", "public comment from 2 residents", etc.
   - If no public comment section, count is 0

2. **Speaker Names**: List of speaker names
   - Format: ["John Smith", "Jane Doe"]
   - Extract from phrases like "Speaker 1: John Smith", "Jane Doe spoke...", etc.
   - If no names provided, return empty list

3. **Vote Results**: Council vote breakdown
   - Format: {{"yes": 4, "no": 0, "abstain": 0}}
   - Look for "Vote: 4-0", "Motion passed 3-1", "Unanimous approval", etc.
   - If unanimous, usually all yes votes

4. **Passed**: Did the item pass?
   - true if approved/passed/carried
   - false if denied/rejected/failed

Return ONLY valid JSON in this exact format:
{{
  "testimony_count": <number or null>,
  "speaker_names": [<list of names or empty>],
  "vote_results": {{"yes": <num>, "no": <num>, "abstain": <num>}} or null,
  "passed": <true or false>
}}

If item {item_ref} is not found in the minutes, return:
{{
  "testimony_count": null,
  "speaker_names": [],
  "vote_results": null,
  "passed": true
}}
"""

        try:
            # Get LLM provider
            provider = get_model_for_task('short_structured')

            # Get LLM response
            response = provider.complete([
                {"role": "system", "content": "You are a meeting minutes parser. Extract structured data from meeting minutes and return valid JSON only."},
                {"role": "user", "content": prompt}
            ])

            # Parse JSON response
            # Strip markdown code blocks if present
            response_text = response.content.strip()
            if response_text.startswith('```'):
                # Remove ```json and ``` markers
                response_text = re.sub(r'^```(?:json)?\s*\n', '', response_text)
                response_text = re.sub(r'\n```\s*$', '', response_text)

            data = json.loads(response_text)

            return TestimonyData(
                item_ref=item_ref,
                testimony_count=data.get('testimony_count'),
                speaker_names=data.get('speaker_names', []),
                vote_results=data.get('vote_results'),
                passed=data.get('passed', True)
            )

        except Exception as e:
            print(f"      ⚠️  Failed to parse testimony for {item_ref}: {type(e).__name__}: {e}")
            # Return empty data on failure
            return TestimonyData(item_ref=item_ref)

    def extract_all_testimony(
        self,
        minutes_text: str,
        item_refs: List[str]
    ) -> Dict[str, TestimonyData]:
        """
        Extract testimony data for multiple agenda items

        Args:
            minutes_text: Full text of meeting minutes
            item_refs: List of agenda item references (e.g., ["5.g", "7.a"])

        Returns:
            Dict mapping item_ref to TestimonyData
        """
        results = {}

        for item_ref in item_refs:
            testimony = self.extract_testimony_for_item(minutes_text, item_ref)
            results[item_ref] = testimony

        return results


def parse_minutes_pdf(pdf_url: str, item_refs: List[str]) -> Dict[str, TestimonyData]:
    """
    Convenience function to parse testimony from minutes PDF URL

    Args:
        pdf_url: URL to minutes PDF
        item_refs: List of agenda item references

    Returns:
        Dict mapping item_ref to TestimonyData
    """
    from agenda_integration import AgendaIntegrator

    # Use AgendaIntegrator to extract text from PDF
    integrator = AgendaIntegrator()
    pdf_text = integrator.extract_text_from_pdf(pdf_url)

    # Parse testimony
    parser = MinutesParser()
    return parser.extract_all_testimony(pdf_text, item_refs)


if __name__ == "__main__":
    # Test with Oct 6 minutes
    import sys

    if len(sys.argv) < 2:
        print("Usage: python src/minutes_parser.py <minutes_pdf_url> <item_ref1> [item_ref2] ...")
        sys.exit(1)

    pdf_url = sys.argv[1]
    item_refs = sys.argv[2:] if len(sys.argv) > 2 else ["5.g"]

    print(f"Parsing minutes: {pdf_url}")
    print(f"Looking for items: {', '.join(item_refs)}\n")

    results = parse_minutes_pdf(pdf_url, item_refs)

    for item_ref, testimony in results.items():
        print(f"\n{item_ref}:")
        print(f"  Testimony count: {testimony.testimony_count}")
        print(f"  Speakers: {', '.join(testimony.speaker_names) if testimony.speaker_names else 'None'}")
        print(f"  Vote: {testimony.vote_results}")
        print(f"  Passed: {testimony.passed}")
