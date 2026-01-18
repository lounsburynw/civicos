#!/usr/bin/env python3
"""
Civic Data Post-Processor - Universal Accuracy and Consistency Fixes

Applies systematic fixes to extracted civic data to ensure:
- Consistent meeting times and deadlines
- LLM-based project categorization
- Enhanced engagement logistics
- Source URL resolution
- Data validation and deduplication

Jurisdiction-specific configurations loaded from automated_civic_refresh.py
"""

import re
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, urljoin


class CivicDataPostProcessor:
    """Universal post-processor for civic data accuracy and consistency"""

    def __init__(self, openai_client=None):
        self.openai_client = openai_client

        # Standard categories for LLM classification
        self.standard_categories = [
            "accessibility",           # Services for seniors, disabled, paratransit
            "mobility_pricing",        # TNC taxes, micromobility fees, transportation pricing
            "arts_culture",           # Cultural events, art centers, community celebrations
            "homeless_services",      # Drop-in centers, housing support, social services
            "building-development",   # Housing, zoning, planning, development fees
            "transportation",         # Transit, traffic, parking, infrastructure
            "public safety",          # Police, fire, emergency services, health
            "taxes-finance",          # Budget, grants, financial policy
            "parks-recreation",       # Parks, recreation facilities, open space
            "city services"           # General municipal services, administrative
        ]

    def process_civic_data(self, civic_data: Dict, source_url: str, jurisdiction_id: str) -> Dict:
        """Apply all post-processing fixes to civic data"""
        processed_data = civic_data.copy()

        # Load jurisdiction-specific configuration
        jurisdiction_config = self._get_jurisdiction_config(jurisdiction_id)

        # Fix meeting timing and logistics
        processed_data = self._normalize_meeting_timing(processed_data, jurisdiction_config)
        processed_data = self._enhance_meeting_logistics(processed_data, jurisdiction_config)

        # Process items
        if 'items' in processed_data:
            processed_items = []
            for item in processed_data['items']:
                processed_item = self._process_item(item, source_url, jurisdiction_config)
                if processed_item:  # Skip if item fails validation
                    processed_items.append(processed_item)

            # Deduplicate items
            processed_items = self._deduplicate_items(processed_items)
            processed_data['items'] = processed_items

        # Validate overall structure
        processed_data = self._validate_civic_data(processed_data, jurisdiction_config)

        return processed_data

    def _get_jurisdiction_config(self, jurisdiction_id: str) -> Dict:
        """Load jurisdiction-specific configuration"""
        try:
            from civicos_services.monitoring.automated_civic_refresh import CITY_CONFIGS

            # Find config by jurisdiction_id
            for config in CITY_CONFIGS.values():
                if config['jurisdiction_id'] == jurisdiction_id:
                    return config

            print(f"⚠️ No configuration found for jurisdiction: {jurisdiction_id}")
            return self._get_default_config()

        except ImportError:
            print("⚠️ Could not load jurisdiction configs, using defaults")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Default configuration for unknown jurisdictions"""
        return {
            'jurisdiction_id': 'unknown',
            'agent_type': 'standard',
            'contact_email': 'info@city.gov',
            'timezone': 'America/Los_Angeles'
        }

    def _normalize_meeting_timing(self, civic_data: Dict, jurisdiction_config: Dict) -> Dict:
        """Set consistent meeting start times and deadlines based on extracted data"""
        # Extract actual meeting time from the data (not hardcoded)
        meeting_datetime = self._extract_meeting_datetime(civic_data, jurisdiction_config)

        if 'meeting' in civic_data:
            meeting = civic_data['meeting']
            if meeting_datetime:
                meeting['iso_datetime'] = meeting_datetime

        # Set consistent timing for all items using extracted meeting time
        if 'items' in civic_data and meeting_datetime:
            for item in civic_data['items']:
                item['when'] = meeting_datetime
                item['deadline'] = meeting_datetime  # Last chance to speak = meeting start

        return civic_data

    def _extract_meeting_datetime(self, civic_data: Dict, jurisdiction_config: Dict) -> Optional[str]:
        """Extract actual meeting datetime from civic data"""
        meeting = civic_data.get('meeting', {})

        # Try to get from existing iso_datetime
        if 'iso_datetime' in meeting:
            return meeting['iso_datetime']

        # Try to construct from date and start_time
        date_str = meeting.get('date', '')
        time_str = meeting.get('start_time', '')

        if date_str and time_str:
            try:
                # Parse and convert to ISO format with timezone
                from dateutil import parser
                dt = parser.parse(f"{date_str} {time_str}")

                # Apply jurisdiction timezone
                timezone_name = jurisdiction_config.get('timezone', 'America/Los_Angeles')
                # For now, return with default PT timezone
                return dt.strftime('%Y-%m-%dT%H:%M:%S-07:00')
            except:
                pass

        return None

    def _enhance_meeting_logistics(self, civic_data: Dict, jurisdiction_config: Dict) -> Dict:
        """Add jurisdiction-appropriate meeting logistics"""
        if 'meeting' not in civic_data:
            civic_data['meeting'] = {}

        meeting = civic_data['meeting']

        # Set proper meeting type
        meeting['meeting_type'] = 'city_council'  # Correct from community_meeting

        # Add contact info from jurisdiction config
        contact_email = jurisdiction_config.get('contact_email', 'info@city.gov')
        if 'public_comment_email' not in meeting:
            meeting['public_comment_email'] = contact_email

        # Add website and calendar URL from jurisdiction config
        if 'website' not in meeting and jurisdiction_config.get('website'):
            meeting['website'] = jurisdiction_config['website']

        if 'calendar_url' not in meeting and jurisdiction_config.get('meeting_calendar_url'):
            meeting['calendar_url'] = jurisdiction_config['meeting_calendar_url']

        return civic_data

    def _process_item(self, item: Dict, source_url: str, jurisdiction_config: Dict) -> Optional[Dict]:
        """Process individual civic opportunity item"""
        processed_item = item.copy()

        # Fix source URL to point to specific packet
        processed_item['source_url'] = self._resolve_source_url(source_url, item)

        # Apply LLM-based category mapping
        processed_item['project_type'] = self._map_project_category_llm(item)

        # Set engagement tier based on content
        processed_item['engagement_tier'] = self._determine_engagement_tier(item)

        # Enhance contact information
        processed_item = self._enhance_contact_info(processed_item, jurisdiction_config)

        # Validate required fields
        if not self._validate_item(processed_item):
            print(f"⚠️ Item failed validation: {processed_item.get('title', 'Unknown')}")
            return None

        return processed_item

    def _resolve_source_url(self, base_url: str, item: Dict) -> str:
        """Convert index URLs to specific packet URLs when possible"""
        # Generic approach - try to make URLs more specific
        if 'item_number' in item and item['item_number']:
            item_anchor = item['item_number'].lower().replace(' ', '-')
            return f"{base_url}#{item_anchor}"

        return base_url

    def _map_project_category_llm(self, item: Dict) -> str:
        """Use LLM to categorize project type with semantic understanding"""
        title = item.get('title', '')
        change = item.get('change', '')
        impact = item.get('impact', '')
        department = item.get('department', '')

        # Combine context for better categorization
        context = f"Title: {title}"
        if change:
            context += f"\nDescription: {change}"
        if impact:
            context += f"\nImpact: {impact}"
        if department:
            context += f"\nDepartment: {department}"

        if not self.openai_client:
            # Fallback to simple keyword approach if no LLM available
            return self._fallback_categorization(item)

        try:
            prompt = f"""Categorize this civic agenda item into exactly ONE category.

{context}

Categories:
- accessibility: Services for seniors, disabled, paratransit, wheelchair access
- mobility_pricing: Transportation taxes, TNC fees, micromobility pricing, parking fees
- arts_culture: Cultural events, art centers, community celebrations, cultural facilities
- homeless_services: Drop-in centers, housing support, social services for unhoused
- building-development: Housing, zoning, planning, development fees, construction
- transportation: Transit, traffic, parking, transportation infrastructure
- public safety: Police, fire, emergency services, public health, disease intervention
- taxes-finance: Budget, grants, financial policy, revenue, fiscal matters
- parks-recreation: Parks, recreation facilities, open space, community facilities
- city services: General municipal services, administrative, governance, communications

Return only the category name (no explanation)."""

            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Cost-efficient for simple classification
                messages=[
                    {"role": "system", "content": "You are a civic policy categorization expert. Categorize agenda items accurately and concisely."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistent categorization
                max_tokens=20    # Just need the category name
            )

            category = response.choices[0].message.content.strip().lower()

            # Validate category is in our standard list
            if category in self.standard_categories:
                return category
            else:
                print(f"⚠️ LLM returned invalid category '{category}' for '{title}', using fallback")
                return self._fallback_categorization(item)

        except Exception as e:
            print(f"⚠️ LLM categorization failed for '{title}': {e}, using fallback")
            return self._fallback_categorization(item)

    def _fallback_categorization(self, item: Dict) -> str:
        """Fallback categorization when LLM is unavailable"""
        title_lower = item.get('title', '').lower()
        description_lower = item.get('change', '').lower() + ' ' + item.get('impact', '').lower()
        combined_text = title_lower + ' ' + description_lower

        # Simple keyword matching as backup
        if any(word in combined_text for word in ['gogo', 'easy does it', 'wheelchair', 'seniors', 'disabled', 'paratransit']):
            return 'accessibility'
        elif any(word in combined_text for word in ['tnc', 'transportation network', 'micromobility', 'tax']):
            return 'mobility_pricing'
        elif any(word in combined_text for word in ['art', 'cultural', 'community dinner']):
            return 'arts_culture'
        elif any(word in combined_text for word in ['drop-in', 'homeless', 'rest']):
            return 'homeless_services'
        elif any(word in combined_text for word in ['housing', 'development', 'zoning', 'planning', 'fee schedule']):
            return 'building-development'
        elif any(word in combined_text for word in ['transportation', 'traffic', 'parking']):
            return 'transportation'
        elif any(word in combined_text for word in ['health', 'behavioral', 'medical', 'disease', 'police']):
            return 'public safety'
        elif any(word in combined_text for word in ['grant', 'funding', 'budget', 'revenue']):
            return 'taxes-finance'
        elif any(word in combined_text for word in ['parks', 'recreation', 'facility', 'marina']):
            return 'parks-recreation'
        else:
            return 'city services'

    def _determine_engagement_tier(self, item: Dict) -> str:
        """Determine engagement tier based on item characteristics"""
        if item.get('public_hearing', False):
            return 'public_hearing'

        title = item.get('title', '').lower()

        # High-impact policy items
        if any(word in title for word in ['ordinance', 'resolution', 'policy']):
            return 'civic_action'

        # Quick consent items
        if item.get('section', '').lower() == 'consent calendar':
            return 'quick_action'

        # Default for other action items
        return 'civic_action'

    def _enhance_contact_info(self, item: Dict, jurisdiction_config: Dict) -> Dict:
        """Add appropriate contact information"""
        # Always include general contact from jurisdiction config
        item['contact_email'] = jurisdiction_config.get('contact_email', 'info@city.gov')

        return item

    def _validate_item(self, item: Dict) -> bool:
        """Validate that item has required fields"""
        required_fields = ['title']

        for field in required_fields:
            if not item.get(field):
                return False

        return True

    def _deduplicate_items(self, items: List[Dict]) -> List[Dict]:
        """Remove duplicate items and flag near-duplicates"""
        seen_items = set()
        deduplicated = []

        for item in items:
            title = item.get('title', '').strip()
            title_normalized = re.sub(r'\s+', ' ', title.lower())

            # Include date in duplicate detection to allow same meeting on different dates
            # Try multiple possible date fields in order of preference
            date = item.get('date', '').strip()  # Most common date field
            if not date:
                date = item.get('when', '').strip()  # Schema datetime field
            if not date:
                date = item.get('meeting_datetime', '').strip()  # Legistar format
            if not date:
                date = item.get('event_date', '').strip()  # Alternative
            if not date:
                date = 'no_date'  # fallback for items without date

            # Extract just the date part if it's a full datetime
            if 'T' in date:
                date = date.split('T')[0]  # Extract YYYY-MM-DD part

            # Create unique key from title + date
            unique_key = f"{title_normalized}|{date}"

            if unique_key not in seen_items:
                seen_items.add(unique_key)
                deduplicated.append(item)
            else:
                print(f"🔄 Duplicate item removed: {title} (same date)")

        return deduplicated

    def _validate_civic_data(self, civic_data: Dict, jurisdiction_config: Dict) -> Dict:
        """Final validation of the complete civic data structure"""
        # Add metadata about processing
        civic_data['processing_metadata'] = {
            'post_processed': True,
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'jurisdiction_id': jurisdiction_config.get('jurisdiction_id', 'unknown'),
            'llm_categorization': self.openai_client is not None,
            'version': '1.0'
        }

        return civic_data


def test_post_processor():
    """Test the post-processor with sample data"""
    sample_data = {
        "meeting": {
            "city": "Berkeley",
            "date": "September 30, 2025",
            "start_time": "6:00 PM",
            "meeting_type": "community_meeting"  # Wrong type
        },
        "items": [
            {
                "title": "Contract Amendment: Go Go Technologies, Inc.",
                "change": "Transportation service contract for seniors and disabled residents",
                "impact": "Improved accessibility and mobility for vulnerable populations",
                "project_type": "community"
            },
            {
                "title": "Berkeley Art Center's Fall 2025 Community Dinner",
                "change": "Relinquishment of Budget Office Funds for cultural event",
                "impact": "Support for local arts community and cultural programming",
                "project_type": "community"
            },
            {
                "title": "Transportation Network Company User Tax",
                "change": "Implementation of TNC tax policy",
                "impact": "Revenue generation from ride-sharing services",
                "project_type": "community"
            }
        ]
    }

    # Test without LLM (fallback)
    processor = CivicDataPostProcessor()
    result = processor.process_civic_data(sample_data, "https://berkeleyca.gov/agendas", "city-berkeley")

    print("📊 Post-processing test results (fallback):")
    print(f"Meeting type: {result['meeting']['meeting_type']}")
    print(f"GoGo category: {result['items'][0]['project_type']}")
    print(f"Arts category: {result['items'][1]['project_type']}")
    print(f"TNC category: {result['items'][2]['project_type']}")
    print(f"Contact: {result['items'][0]['contact_email']}")


if __name__ == "__main__":
    test_post_processor()