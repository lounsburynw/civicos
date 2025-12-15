#!/usr/bin/env python3
"""
Berkeley Agenda-Specific Parser - Legacy Implementation

PRESERVED FOR FUTURE DEVELOPMENT: This contains the sophisticated agenda-item level
parsing logic that was developed specifically for Berkeley's meeting documents.

STATUS: Cached for downstream development when agenda-item expansion is needed
CONTEXT: Temporarily replaced with event-level parsing for consistency with other municipalities

FUTURE USE CASES:
- Agenda-item expansion system across all platforms
- Deep-dive meeting analysis
- Detailed civic engagement events within specific meetings
- Meeting preparation tools for activists

TECHNICAL NOTES:
- Multi-pass extraction approach to handle 15+ agenda items without truncation
- Berkeley-specific priorities and categorization
- Sophisticated prompt engineering for agenda parsing
"""

import json
import os
from typing import Dict, List, Optional
from openai import OpenAI

class BerkeleyAgendaParser:
    """
    Berkeley-specific agenda parsing with multi-pass extraction

    This parser was designed to handle Berkeley's high-density meeting agendas
    with 15+ agenda items per meeting, using a two-pass approach to avoid
    truncation and maintain extraction quality.
    """

    def __init__(self, openai_client: OpenAI):
        self.openai_client = openai_client

    def extract_agenda_items(self, joined_sources: str, source_url: str = "") -> dict:
        """
        Berkeley multi-pass extraction for agenda-level events

        ORIGINAL IMPLEMENTATION: This extracts individual agenda items
        within meetings, providing granular civic engagement events.

        Args:
            joined_sources: Combined text content from meeting documents
            source_url: Source URL for context

        Returns:
            dict: Standard civic digest format with agenda-level items
        """
        try:
            print(f"🌉 Using Berkeley agenda-level extraction for {source_url}")

            # Berkeley often has 15+ agenda items, so we use multi-pass to avoid truncation
            # Pass 1: Extract meeting metadata and overall structure
            structure_prompt = f"""
            Extract the meeting structure and metadata ONLY. Return JSON with this structure:
            {{
              "meeting": {{
                "city": "string",
                "date": "string",
                "start_time": "string",
                "location": "string",
                "livestream": "string",
                "public_comment_email": "string",
                "public_comment_deadline": "string",
                "meeting_type": "string"
              }},
              "agenda_sections": [
                {{
                  "section_title": "string",
                  "section_type": "string (consent|action|public_hearing|information)",
                  "item_count": "number"
                }}
              ]
            }}

            Content: {self._truncate_safely(joined_sources, 20000)}
            """

            structure_response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": structure_prompt}],
                temperature=0.1
            )

            structure_data = json.loads(structure_response.choices[0].message.content)

            # Pass 2: Extract detailed civic events from key sections
            opportunities_prompt = f"""
            Extract DETAILED civic engagement events from this Berkeley City Council content.
            Focus on high-impact items that residents can meaningfully engage with.

            Return JSON array of events:
            [
              {{
                "title": "string",
                "change": "string",
                "impact": "string",
                "how_to_participate": "string",
                "project_type": "string"
              }}
            ]

            BERKELEY PRIORITIES:
            - Housing and development proposals (always high priority)
            - Public safety and police accountability items
            - Climate action and environmental justice
            - Transportation and mobility projects
            - Community services and programs
            - Budget and fiscal policy changes

            Content: {self._truncate_safely(joined_sources, 35000)}
            """

            opportunities_response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": opportunities_prompt}],
                temperature=0.1
            )

            events = json.loads(opportunities_response.choices[0].message.content)

            # Combine structure and events into standard format
            result = {
                "meeting": structure_data.get("meeting", {}),
                "items": events,
                "recap_rows": [],  # Generate recap from events
                "bottom_line": f"Berkeley City Council meeting with {len(events)} key events for civic engagement."
            }

            # Generate recap rows from top events
            if events:
                for opp in events[:3]:  # Top 3 for recap
                    result["recap_rows"].append({
                        "topic": opp.get("title", ""),
                        "why_it_matters": opp.get("impact", "")[:100] + "...",
                        "act_by": structure_data.get("meeting", {}).get("date", "Meeting date")
                    })

            print(f"✅ Berkeley agenda-level extracted {len(events)} events")
            return result

        except Exception as e:
            print(f"❌ Berkeley agenda-level extraction failed: {e}")
            raise e

    def _truncate_safely(self, text: str, max_length: int) -> str:
        """Safely truncate text to avoid token limits"""
        if len(text) <= max_length:
            return text

        # Try to truncate at word boundary
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.8:  # If we can find a space in the last 20%
            return truncated[:last_space]
        return truncated

# FUTURE INTEGRATION EXAMPLE:
"""
When agenda-item expansion is ready for implementation across all platforms:

1. Import this class in civic_digest.py:
   from berkeley_agenda_parser_legacy import BerkeleyAgendaParser

2. Add agenda expansion method to CivicDigest class:
   def expand_meeting_agenda(self, meeting_url: str, meeting_metadata: dict) -> List[dict]:
       if "berkeley" in meeting_url.lower():
           parser = BerkeleyAgendaParser(self.openai_client)
           return parser.extract_agenda_items(meeting_content, meeting_url)
       # Add other municipality-specific agenda parsers here

3. Call from conversational interface when user requests detailed agenda view:
   agenda_items = civic_digest.expand_meeting_agenda(meeting_url, meeting_data)
"""