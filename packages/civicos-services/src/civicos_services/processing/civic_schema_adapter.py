#!/usr/bin/env python3
"""
Schema Adapter for Civic Conversational OS
Transforms civic_digest.py output to civic-app-schema.json compliance

Development Context:
- Schema Entities in Focus: Newsletter, CivicOpportunity, Jurisdiction, ContactInfo
- Working Asset: civic_digest.py (1,286 lines, production-ready)
- Implementation Objective: Bridge existing data to schema-compliant structures
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import re

from civicos_config import JurisdictionRegistry


# Schema-compliant data classes based on civic-app-schema.json
@dataclass
class ContactInfo:
    """Government contact information - schema compliant"""
    email: str
    name: str = ""
    title: str = ""
    phone: str = ""
    office: str = ""


@dataclass  
class Jurisdiction:
    """Government entity - schema compliant"""
    id: str
    name: str
    type: str  # city, county, school_district, special_district, state, federal
    website: str = ""
    meeting_calendar_url: str = ""


@dataclass
class WikiEnhancement:
    """AI-enhanced civic intelligence - schema compliant"""
    success_strategy: str
    precedent_examples: List[str] = None
    recommended_approach: str = ""
    related_opportunities: List[str] = None
    
    def __post_init__(self):
        if self.precedent_examples is None:
            self.precedent_examples = []
        if self.related_opportunities is None:
            self.related_opportunities = []


@dataclass
class EngagementInfo:
    """Enhanced engagement structure"""
    webinar_id: Optional[str] = None
    dial_in: Optional[List[str]] = None
    raise_hand_phone: Optional[str] = None
    speaker_time_minutes: Optional[int] = None


@dataclass
class SchemaCivicOpportunity:
    """Enhanced schema-compliant CivicOpportunity with resident-friendly fields"""
    id: str
    title: str  # Shortened, user-friendly title
    original_title: str  # Full agenda title for fidelity
    description: str
    when: str  # ISO date-time
    deadline: Optional[str]  # ISO date-time
    engagement_info: str
    impact_summary: str
    source_url: str
    location: str
    meeting_type: str
    project_type: str
    engagement_tier: str
    jurisdiction: Jurisdiction
    contact_info: ContactInfo
    wiki_enhancement: WikiEnhancement
    created_at: str  # ISO date-time
    scraped_from: str
    # Enhanced fields - no defaults, let agenda content provide values
    action_type: Optional[str] = None  # second_reading, public_hearing, consent, etc.
    when_human: Optional[str] = None  # "Tue Sep 30, 2025 • 6:00 PM PT"
    deadline_reason: Optional[str] = None  # "speaker cards", "written comments"
    agenda_item_number: Optional[int] = None
    engagement: Optional[EngagementInfo] = None
    agenda_page: Optional[int] = None
    timezone: Optional[str] = None


@dataclass
class GenerationMetadata:
    """Newsletter generation metadata - schema compliant"""
    scrape_urls: List[str]
    ai_model_used: str
    wiki_files_loaded: List[str]
    generation_cost: float
    processing_time: float
    unparseable_urls: List[dict] = None  # Optional field for manual references


@dataclass
class NewsletterAnalytics:
    """Newsletter analytics - schema compliant"""
    sent_count: int
    open_rate: float = 0.0
    click_rate: float = 0.0
    action_conversion_rate: float = 0.0


@dataclass
class SchemaNewsletter:
    """Schema-compliant Newsletter matching civic-app-schema.json"""
    id: str
    jurisdiction: Jurisdiction
    events: List[SchemaCivicOpportunity]
    generation_metadata: GenerationMetadata
    html_content: str
    text_content: str
    subject_line: str
    send_date: str  # ISO date-time
    recipients: List[str]
    analytics: NewsletterAnalytics
    created_at: str  # ISO date-time


class CivicSchemaAdapter:
    """
    Transforms civic_digest.py output to civic-app-schema.json compliance
    
    Schema Context:
    - Works backwards from schema definitions to ensure compliance
    - Handles enum standardization and missing field generation
    - Maintains data integrity while bridging format gaps
    """
    
    def __init__(self):
        # Consistent project type taxonomy (civic_digest.py → schema enum)
        self.project_type_mapping = {
            # Primary controlled taxonomy
            "transportation": "transportation",
            "parks": "parks",
            "planning": "planning",
            "governance": "governance",
            "public_safety": "public_safety",
            "health": "health",
            "housing": "housing",
            "environment": "environment",
            "budget": "budget",
            "education": "education",

            # Mapping variations to primary categories
            "traffic": "transportation",
            "transit": "transportation",
            "micromobility": "transportation",
            "mobility": "transportation",
            "paratransit": "transportation",

            "parks/recreation": "parks",
            "recreation": "parks",
            "cultural services": "parks",

            "development": "planning",
            "building/development": "planning",
            "zoning": "planning",
            "development_services": "planning",

            "city services": "governance",
            "public comment": "governance",
            "ordinance": "governance",
            "policy": "governance",

            "public_health": "health",
            "behavioral health": "health",
            "disability services": "health",
            "seniors": "health",

            # Fallback for unmatched items
            "community": "governance"
        }
        
        # Meeting type mapping
        self.meeting_type_mapping = {
            "planning commission": "planning_commission",
            "planning_commission": "planning_commission",  # AI detection format
            "city council": "city_council",
            "city_council": "city_council",  # Handle both formats
            "public hearing": "public_hearing",
            "public_hearing": "public_hearing",  # AI detection format
            "community meeting": "community_meeting",
            "community_meeting": "community_meeting",  # AI detection format
            "committee": "committee",
            "commission": "commission",  # AI detection format
            "board": "board",  # AI detection format
            "school_board": "school_board",  # AI detection format
            "workshop": "workshop"  # AI detection format
        }

    def generate_uuid(self) -> str:
        """Generate UUID for schema entities"""
        return str(uuid.uuid4())

    def get_current_timestamp(self) -> str:
        """Get current ISO timestamp"""
        return datetime.now(timezone.utc).isoformat()

    def _apply_jurisdiction_timezone(self, dt: datetime) -> datetime:
        """
        Apply timezone based on jurisdiction context - generalizable approach.

        This system enables accurate meeting time representation across all US jurisdictions
        by mapping jurisdiction IDs to their appropriate IANA timezone identifiers.

        Usage:
        - Add new cities: "city-name": "America/Timezone"
        - State defaults provide fallback for unmapped cities
        - Graceful UTC fallback for international or unknown jurisdictions

        Example jurisdiction IDs:
        - "city-san-rafael" -> Pacific Time
        - "city-chicago" -> Central Time
        - "city-new-york" -> Eastern Time
        """
        # Get jurisdiction ID from current context
        jurisdiction_id = getattr(self, 'current_jurisdiction_id', 'unknown')
        timezone_name = JurisdictionRegistry.get_timezone(jurisdiction_id, default=None)

        if timezone_name:
            try:
                from zoneinfo import ZoneInfo
                local_tz = ZoneInfo(timezone_name)
                return dt.replace(tzinfo=local_tz)
            except ImportError:
                # Fallback for Python < 3.9
                pass

        # Default fallback: assume UTC
        return dt.replace(tzinfo=timezone.utc)

    def normalize_project_type(self, project_type: str) -> str:
        """Normalize project_type to schema enum"""
        normalized = project_type.lower().strip()
        return self.project_type_mapping.get(normalized, "community")

    def normalize_meeting_type(self, meeting_type: str) -> str:
        """Normalize meeting_type to schema enum"""
        normalized = meeting_type.lower().strip()
        for key, value in self.meeting_type_mapping.items():
            if key in normalized:
                return value
        return "community_meeting"

    def _determine_enhanced_engagement_tier(self, item: dict, title: str, description: str) -> str:
        """
        Enhanced engagement tier determination based on ChatGPT5 feedback.
        Prioritizes Public Hearings and Action Calendar items for Berkeley.
        """
        # Get text to analyze (case-insensitive)
        text = f"{title} {description} {item.get('agenda_section', '')}".lower()

        # PRIORITY 1: Public Hearings (highest engagement tier)
        public_hearing_indicators = [
            'public hearing',
            'planning & development fee schedule',
            'planning and development fee schedule',
            'fee schedule',
            'ordinance adoption',
            'zoning',
            'development proposal'
        ]

        if any(indicator in text for indicator in public_hearing_indicators):
            return "public_hearing"

        # PRIORITY 2: Second Reading & Action Calendar - Civic Action Required
        civic_action_indicators = [
            '[second reading]',
            'second reading',
            'action calendar',
            'new business',
            'police accountability',
            'director of police accountability',
            'oversight',
            'policy direction',
            'communications policy'
        ]

        if any(indicator in text for indicator in civic_action_indicators):
            return "civic_action"

        # Budget and financial items requiring attention
        financial_indicators = [
            'budget',
            'tax',
            'fee',
            'revenue',
            'funding',
            'grant',
            'financial'
        ]

        if any(indicator in text for indicator in financial_indicators):
            return "civic_action"

        # Default for consent calendar and other items
        return "quick_action"

    def extract_jurisdiction_from_meeting(self, meeting_data: Dict) -> Jurisdiction:
        """Create Jurisdiction object from meeting data"""
        # Use jurisdiction_id if provided, otherwise derive from city name
        if 'jurisdiction_id' in meeting_data:
            jurisdiction_id = meeting_data['jurisdiction_id']
            # Extract display name from jurisdiction_id
            if jurisdiction_id.startswith('city-'):
                city_name = jurisdiction_id[5:].replace('-', ' ').title()
            elif jurisdiction_id == 'marin-county':
                city_name = 'Marin County'
            else:
                city_name = jurisdiction_id.replace('-', ' ').title()
        else:
            # Fallback to legacy city-based approach
            city_name = meeting_data.get('city', 'Unknown City')
            jurisdiction_id = f"city-{city_name.lower().replace(' ', '-')}"

        return Jurisdiction(
            id=jurisdiction_id,
            name=city_name,
            type="city",
            website=meeting_data.get('website', ''),
            meeting_calendar_url=meeting_data.get('calendar_url', '')
        )

    def extract_contact_info(self, opportunity_data: Dict, meeting_data: Dict) -> ContactInfo:
        """Create ContactInfo from opportunity and meeting data with better phone handling"""
        import logging
        
        # Try opportunity-level contact first, then meeting-level
        email = (opportunity_data.get('contact_email', '') or 
                meeting_data.get('public_comment_email', ''))
        
        name = opportunity_data.get('contact_name', '')
        
        # Handle phone number - separate actual phone from virtual meeting info
        raw_phone = meeting_data.get('phone', '')
        phone = self._extract_phone_number(raw_phone)
        
        if not email:
            logging.warning(f"No email found for contact info in opportunity: {opportunity_data.get('title', 'Unknown')}")
        
        return ContactInfo(
            email=email,
            name=name,
            title=opportunity_data.get('contact_title', ''),
            phone=phone,
            office=opportunity_data.get('contact_office', '')
        )
    
    def _extract_phone_number(self, raw_phone: str) -> str:
        """Extract actual phone number from mixed virtual meeting info"""
        if not raw_phone:
            return ""
        
        # Look for phone number patterns, ignoring meeting IDs
        phone_patterns = [
            r'(\(\d{3}\)\s*\d{3}-\d{4})',  # (555) 123-4567
            r'(\d{3}-\d{3}-\d{4})',       # 555-123-4567
            r'(\d{10})',                  # 5551234567
            r'(\+1\s*\(\d{3}\)\s*\d{3}-\d{4})',  # +1 (555) 123-4567
        ]
        
        for pattern in phone_patterns:
            match = re.search(pattern, raw_phone)
            if match:
                return match.group(1)
        
        # If no clear phone pattern and it's short, might be a real phone
        if len(raw_phone) <= 20 and 'ID:' not in raw_phone and 'zoom' not in raw_phone.lower():
            return raw_phone
            
        return ""  # Likely virtual meeting info, not a phone number

    def extract_action_type(self, title: str) -> Optional[str]:
        """Extract precise action_type from title structure and content"""
        title_lower = title.lower()

        # Explicit bracketed types (highest priority)
        if '[second reading]' in title_lower:
            return 'second_reading'
        elif '[public hearing]' in title_lower:
            return 'public_hearing'
        elif '[consent]' in title_lower:
            return 'consent'
        elif '[first reading]' in title_lower:
            return 'first_reading'

        # Public comment variations
        elif 'public comment' in title_lower:
            return 'public_comment'

        # Contract and procurement actions
        elif 'contract amendment' in title_lower or 'contract modification' in title_lower:
            return 'contract_amendment'
        elif 'contract' in title_lower and ('award' in title_lower or 'approve' in title_lower):
            return 'contract_award'

        # Financial actions
        elif 'budget' in title_lower and ('adopt' in title_lower or 'approve' in title_lower):
            return 'budget_adoption'
        elif 'grant' in title_lower and ('accept' in title_lower or 'application' in title_lower):
            return 'grant_action'

        # Planning and development
        elif 'ordinance' in title_lower and ('adopt' in title_lower or 'enact' in title_lower):
            return 'ordinance_adoption'
        elif 'resolution' in title_lower:
            return 'resolution'
        elif 'zoning' in title_lower or 'planning' in title_lower:
            return 'planning_action'

        # Referrals and directions
        elif 'referral' in title_lower or 'refer to' in title_lower:
            return 'referral'
        elif 'direction' in title_lower or 'direct' in title_lower:
            return 'policy_direction'

        # Information and reports
        elif 'report' in title_lower or 'presentation' in title_lower or 'update' in title_lower:
            return 'information_item'
        elif 'donation' in title_lower or 'accept' in title_lower:
            return 'acceptance'

        # Default for unclassified items
        else:
            return 'action'

    def _normalize_location(self, location: str) -> str:
        """
        Normalize location format to consistent style.

        Municipality-agnostic approach that standardizes:
        - Separator consistency: "Room - Address" → "Room, Address"
        - Street abbreviation consistency: "St" → "Street", "Ave" → "Avenue"
        - Whitespace normalization
        """
        if not location or location.strip() == '' or location == 'Location not specified':
            return 'Location not specified'

        # Clean and normalize
        location = location.strip()

        # Standardize separators (dash to comma)
        if ' - ' in location:
            location = location.replace(' - ', ', ')

        # Standardize common street abbreviations
        import re
        location = re.sub(r'\bSt\b(?=[\s,])', 'Street', location)
        location = re.sub(r'\bAve\b(?=[\s,])', 'Avenue', location)
        location = re.sub(r'\bBlvd\b(?=[\s,])', 'Boulevard', location)
        location = re.sub(r'\bDr\b(?=[\s,])', 'Drive', location)

        # Clean up extra whitespace and multiple commas
        location = re.sub(r'\s+', ' ', location)
        location = re.sub(r',\s*,', ',', location)

        return location

    def _get_engagement_info(self, title: str, item: Dict, meeting_data: Dict) -> str:
        """
        Consistent engagement_info based on item type.

        Public comment items: Include full Zoom/dial-in block
        Other items: Return null (empty string)
        """
        title_lower = title.lower()

        # Public comment items get full meeting participation info
        if 'public comment' in title_lower:
            # Start with item-specific instructions
            engagement_info = item.get('how_to_participate', '').strip()

            # Fallback to meeting-wide instructions
            if not engagement_info or engagement_info == 'Not specified':
                engagement_info = meeting_data.get('speaker_instructions', '').strip()

            # Include general meeting info if available
            if not engagement_info or engagement_info in ['Not specified', 'Contact local government']:
                # For public comment, try to get basic meeting info
                meeting_info = meeting_data.get('meeting_info', {})
                if isinstance(meeting_info, dict):
                    zoom_info = meeting_info.get('zoom_link') or meeting_info.get('webinar_link')
                    phone_info = meeting_info.get('dial_in_number')

                    if zoom_info or phone_info:
                        parts = []
                        if zoom_info:
                            parts.append(f"Join online: {zoom_info}")
                        if phone_info:
                            parts.append(f"Dial in: {phone_info}")
                        engagement_info = " | ".join(parts)

            # Return engagement_info if we found actionable info, otherwise null
            return engagement_info if engagement_info and engagement_info not in ['Not specified', 'Contact local government'] else ""

        # Non-public comment items: null engagement_info (meeting details not relevant)
        else:
            return ""

    def _clean_title_sponsor_names(self, title: str) -> str:
        """
        Remove sponsor names from titles that shouldn't include them.

        Handles cases where sponsor names like "Lynn Cooper", "Gael Alcock"
        bleed into official agenda item titles inappropriately.
        """
        import re

        # Common pattern: "Name: Actual Title" or "Name Actual Title"
        # Look for: FirstName LastName followed by colon or at start
        sponsor_patterns = [
            r'^[A-Z][a-z]+ [A-Z][a-z]+:\s*',  # "Lynn Cooper: Title"
            r'^[A-Z][a-z]+ [A-Z][a-z]+\s+(?=[A-Z])',  # "Lynn Cooper Title" where Title starts with capital
        ]

        cleaned_title = title
        for pattern in sponsor_patterns:
            cleaned_title = re.sub(pattern, '', cleaned_title).strip()

        # If we removed too much (title becomes too short), return original
        if len(cleaned_title) < 10 and len(title) > len(cleaned_title) + 5:
            return title

        return cleaned_title if cleaned_title else title

    def create_human_readable_time(self, iso_datetime: str) -> Optional[str]:
        """Convert ISO datetime to resident-friendly format with local timezone"""
        try:
            from datetime import datetime
            import pytz

            dt = datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))

            # Get jurisdiction timezone for proper conversion
            jurisdiction_id = getattr(self, 'current_jurisdiction_id', 'unknown')

            # Use JurisdictionRegistry for timezone lookup
            timezone_name, display_name = JurisdictionRegistry.get_timezone_display(jurisdiction_id)

            if JurisdictionRegistry.has_jurisdiction(jurisdiction_id):
                local_tz = pytz.timezone(timezone_name)

                # Convert to local timezone
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                local_dt = dt.astimezone(local_tz)

                time_part = local_dt.strftime('%a %b %d, %Y • %I:%M %p').replace(' 0', ' ')
                return f"{time_part} {display_name}"
            else:
                # Fallback to original logic for unknown jurisdictions
                time_part = dt.strftime('%a %b %d, %Y • %I:%M %p').replace(' 0', ' ')

                if dt.tzinfo:
                    offset = dt.utcoffset()
                    if offset:
                        hours = offset.total_seconds() / 3600
                        if hours == -8 or hours == -7:
                            tz_name = "PT"
                        elif hours == -6 or hours == -5:
                            tz_name = "MT"
                        elif hours == -5 or hours == -4:
                            tz_name = "CT"
                        elif hours == -4 or hours == -3:
                            tz_name = "ET"
                        else:
                            tz_name = f"UTC{int(hours):+d}"
                    else:
                        tz_name = "UTC"
                else:
                    tz_name = "UTC"

                return f"{time_part} {tz_name}"
        except Exception as e:
            print(f"⚠️ Error creating human readable time: {e}")
            return None

    def extract_engagement_structure(self, item: Dict, meeting_data: Dict) -> Optional[EngagementInfo]:
        """Extract structured engagement info from Berkeley agent output"""
        engagement_data = item.get('engagement', meeting_data.get('engagement', {}))
        if not engagement_data:
            return None

        return EngagementInfo(
            webinar_id=engagement_data.get('webinar_id'),
            dial_in=engagement_data.get('dial_in'),
            raise_hand_phone=engagement_data.get('raise_hand_phone'),
            speaker_time_minutes=engagement_data.get('speaker_time_minutes')
        )

    def create_wiki_enhancement(self, opportunity_data: Dict) -> WikiEnhancement:
        """Create WikiEnhancement from opportunity data"""
        success_strategy = (
            opportunity_data.get('success_strategy', '') or
            opportunity_data.get('deadline_guidance', '') or
            "Standard public comment procedures apply"
        )
        
        return WikiEnhancement(
            success_strategy=success_strategy,
            precedent_examples=[],
            recommended_approach=opportunity_data.get('recommended_approach', ''),
            related_opportunities=[]
        )

    def convert_to_iso_datetime(self, date_str: str, default_time: str = "18:00") -> str:
        """Convert various date formats to ISO datetime with proper error handling"""
        import logging
        
        if not date_str or not date_str.strip():
            logging.warning("Empty date string provided, using current timestamp")
            return self.get_current_timestamp()
            
        date_str = date_str.strip()
        
        try:
            # Handle ISO format already (with timezone)
            if 'T' in date_str and ('Z' in date_str or '+' in date_str or '-' in date_str[-6:]):
                # Validate it's actually parseable
                datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return date_str
                
            # Handle "March 15, 2024" or "March 15, 2025" format
            if ',' in date_str and any(month in date_str for month in 
                ['January', 'February', 'March', 'April', 'May', 'June',
                 'July', 'August', 'September', 'October', 'November', 'December']):
                
                # Clean up the date string and check if time is already included
                cleaned_date = ' '.join(date_str.split())  # Remove extra whitespace

                # Handle duplicate date strings like "September 30, 2025 September 30, 2025 6:00 PM"
                parts = cleaned_date.split()
                if len(parts) >= 6:  # Likely duplicate date
                    # Extract month, day, year from first occurrence and time from end
                    if parts[0] in ['January', 'February', 'March', 'April', 'May', 'June',
                                   'July', 'August', 'September', 'October', 'November', 'December']:
                        # Try to find time components at the end
                        time_parts = []
                        for i in range(len(parts)-1, -1, -1):
                            if ':' in parts[i] or parts[i].lower() in ['am', 'pm']:
                                time_parts.insert(0, parts[i])
                            elif len(time_parts) > 0:
                                break
                        if time_parts:
                            cleaned_date = f"{parts[0]} {parts[1]} {parts[2]} {' '.join(time_parts)}"
                        else:
                            cleaned_date = f"{parts[0]} {parts[1]} {parts[2]}"
                
                # If time is already in the string, don't add default_time
                if ':' in cleaned_date:
                    # Handle "September 23, 2025 7:00 pm" format
                    if 'pm' in cleaned_date.lower() or 'am' in cleaned_date.lower():
                        # Parse as "September 23, 2025 7:00 pm"
                        try:
                            dt = datetime.strptime(cleaned_date, "%B %d, %Y %I:%M %p")
                        except ValueError:
                            # Try without comma if format doesn't match
                            cleaned_date_no_comma = cleaned_date.replace(',', '')
                            dt = datetime.strptime(cleaned_date_no_comma, "%B %d %Y %I:%M %p")
                        # Apply jurisdiction-specific timezone
                        dt_with_tz = self._apply_jurisdiction_timezone(dt)
                        return dt_with_tz.isoformat()
                    else:
                        # Parse as "March 15, 2024 18:00"
                        dt = datetime.strptime(cleaned_date, "%B %d, %Y %H:%M")
                else:
                    # Add default time: "March 15, 2024" + "18:00"
                    datetime_str = f"{cleaned_date} {default_time}"
                    dt = datetime.strptime(datetime_str, "%B %d, %Y %H:%M")
                    # Apply jurisdiction-specific timezone
                    dt_with_tz = self._apply_jurisdiction_timezone(dt)
                    return dt_with_tz.isoformat()

                return dt.replace(tzinfo=timezone.utc).isoformat()
            
            # Handle "2024-03-15" format
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                datetime_str = f"{date_str} {default_time}"
                dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
                # Apply jurisdiction-specific timezone
                dt_with_tz = self._apply_jurisdiction_timezone(dt)
                return dt_with_tz.isoformat()

            # Handle "2025-10-09 00:00:00" format (Legistar API format)
            if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', date_str):
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                # Apply jurisdiction-specific timezone
                dt_with_tz = self._apply_jurisdiction_timezone(dt)
                return dt_with_tz.isoformat()
            
            # Handle "03/15/2024" format
            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str):
                datetime_str = f"{date_str} {default_time}"
                dt = datetime.strptime(datetime_str, "%m/%d/%Y %H:%M")
                # Apply jurisdiction-specific timezone
                dt_with_tz = self._apply_jurisdiction_timezone(dt)
                return dt_with_tz.isoformat()
            
            # Handle "March 15" (assume current year)
            if re.match(r'^[A-Za-z]+ \d{1,2}$', date_str):
                current_year = datetime.now().year
                datetime_str = f"{date_str}, {current_year} {default_time}"
                dt = datetime.strptime(datetime_str, "%B %d, %Y %H:%M")
                # Apply jurisdiction-specific timezone
                dt_with_tz = self._apply_jurisdiction_timezone(dt)
                return dt_with_tz.isoformat()
                
            # If we can't parse it, log the issue and use current time
            logging.warning(f"Unable to parse date format: '{date_str}', using current timestamp")
            return self.get_current_timestamp()
            
        except Exception as e:
            logging.error(f"DateTime parsing failed for '{date_str}': {e}")
            return self.get_current_timestamp()

    def html_to_text(self, html_content: str) -> str:
        """Convert HTML newsletter to readable plain text"""
        from html import unescape
        import logging
        
        if not html_content or not html_content.strip():
            return ""
        
        try:
            text = html_content
            
            # Replace block elements with newlines for structure
            text = re.sub(r'</(div|p|h[1-6]|li|tr)>', r'\n', text, flags=re.IGNORECASE)
            text = re.sub(r'<br[^>]*>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'</td>', ' | ', text, flags=re.IGNORECASE)  # Table cells with separators
            
            # Add spacing around headers
            text = re.sub(r'<h[1-6][^>]*>', r'\n\n', text, flags=re.IGNORECASE)
            
            # Handle lists - add bullet points
            text = re.sub(r'<li[^>]*>', r'\n• ', text, flags=re.IGNORECASE)
            
            # Remove remaining HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            
            # Decode HTML entities properly
            text = unescape(text)
            
            # Clean up whitespace while preserving structure
            lines = []
            for line in text.split('\n'):
                cleaned_line = re.sub(r'\s+', ' ', line).strip()
                if cleaned_line:  # Skip empty lines
                    lines.append(cleaned_line)
                elif lines and lines[-1]:  # Add single empty line between sections
                    lines.append('')
            
            # Join lines and remove excessive blank lines
            result = '\n'.join(lines)
            result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)  # Max 2 consecutive newlines
            
            return result.strip()
            
        except Exception as e:
            logging.error(f"HTML to text conversion failed: {e}")
            # Fallback to simple tag removal
            return re.sub(r'<[^>]+>', ' ', html_content).strip()

    def validate_opportunity(self, opportunity: SchemaCivicOpportunity) -> bool:
        """Validate opportunity against schema requirements"""
        import logging
        
        issues = []
        
        if not opportunity.title or not opportunity.title.strip():
            issues.append("Missing title")
        if not opportunity.description or not opportunity.description.strip():
            issues.append("Missing description")
        if not opportunity.jurisdiction.name:
            issues.append("Missing jurisdiction name")
        if not opportunity.contact_info.email:
            issues.append("Missing contact email")
        if not opportunity.engagement_info or not opportunity.engagement_info.strip():
            issues.append("Missing engagement info")
            
        if issues:
            logging.warning(f"Event validation issues for '{opportunity.title}': {', '.join(issues)}")
            return False
            
        return True

    def adapt_civic_opportunity(self, item: Dict, meeting_data: Dict, 
                               jurisdiction: Jurisdiction, source_url: str) -> Optional[SchemaCivicOpportunity]:
        """Convert civic_digest.py item to schema-compliant CivicOpportunity with validation"""
        import logging
        
        try:
            # Extract fields - trust municipality-specific parsers, no fallbacks
            title = item.get('title', 'Civic Event').strip() or 'Civic Event'
            original_title = item.get('original_title', title)  # Fallback to title if not provided

            # Use proper field mapping - different parsers use different field names
            description = item.get('description', '').strip() or item.get('change', '').strip()
            raw_impact = item.get('impact_summary', '').strip() or item.get('impact', '').strip()

            # Validation only: prevent identical content, default to None if invalid
            if description == title:
                description = ""

            # Trust LLM-generated impact_summary, only validate for duplication
            impact_summary = raw_impact
            if impact_summary == title or impact_summary == description:
                impact_summary = ""
            # Public comment metadata consistency: full info for public comment, null for others
            engagement_info = self._get_engagement_info(title, item, meeting_data)
            
            # Handle timing with improved date parsing - prioritize item-specific event_date
            meeting_date = meeting_data.get('date', '')  # Initialize meeting_date for deadline fallback

            if item.get('event_date'):
                # CivicPlus calendar parser provides precise event dates
                when_datetime = item['event_date']
                if not when_datetime.endswith('Z') and '+' not in when_datetime:
                    # Apply timezone if not already specified (convert to datetime first)
                    from datetime import datetime
                    dt = datetime.fromisoformat(when_datetime.replace('Z', '+00:00'))
                    dt_with_tz = self._apply_jurisdiction_timezone(dt)
                    when_datetime = dt_with_tz.isoformat()
            else:
                # Fallback to meeting-level dates
                meeting_time = meeting_data.get('start_time', '18:00')

                # Build full datetime string for better parsing
                if meeting_date and meeting_time:
                    when_datetime = self.convert_to_iso_datetime(f"{meeting_date} {meeting_time}")
                else:
                    when_datetime = self.convert_to_iso_datetime(meeting_date, meeting_time)

            # Handle deadline (try multiple sources)
            deadline_str = (
                item.get('deadline', '') or
                meeting_data.get('public_comment_deadline', '') or
                meeting_date
            )
            deadline_datetime = self.convert_to_iso_datetime(deadline_str, "17:00")
            
            # Normalize enums - prioritize item-specific meeting_type from AI detection
            project_type = self.normalize_project_type(item.get('project_type', 'community'))
            meeting_type = self.normalize_meeting_type(
                item.get('meeting_type', '') or meeting_data.get('meeting_type', '')
            )

            # Determine engagement tier
            engagement_tier = self._determine_enhanced_engagement_tier(item, title, description)
            # Note: Public hearing items keep meeting_type as "city_council" but have engagement_tier "public_hearing"
            
            # Create nested objects with error handling
            contact_info = self.extract_contact_info(item, meeting_data)
            wiki_enhancement = self.create_wiki_enhancement(item)

            # Extract enhanced fields from Berkeley agent output
            action_type = self.extract_action_type(title)
            when_human = self.create_human_readable_time(when_datetime)
            engagement_structure = self.extract_engagement_structure(item, meeting_data)

            # Extract other enhanced fields
            agenda_item_number = item.get('agenda_item_number', item.get('item_number'))
            deadline_reason = item.get('deadline_reason')
            agenda_page = item.get('agenda_page')
            timezone_field = item.get('timezone')

            # Use jurisdiction timezone mapping if not provided by agent
            if not timezone_field:
                jurisdiction_id = jurisdiction.id if jurisdiction else 'unknown'
                timezone_field = JurisdictionRegistry.get_timezone(jurisdiction_id, default=None)

            # Clear deadline if there's no justification (ChatGPT feedback compliance)
            if not deadline_reason or deadline_reason.strip() == "":
                deadline_datetime = None

            # Create opportunity object with enhanced fields
            opportunity = SchemaCivicOpportunity(
                id=self.generate_uuid(),
                title=title,
                original_title=original_title,
                description=description,
                when=when_datetime,
                deadline=deadline_datetime,
                engagement_info=engagement_info,
                impact_summary=impact_summary,
                source_url=source_url,
                location=self._normalize_location(
                    item.get('location', '') or meeting_data.get('location', '') or 'Location not specified'
                ),
                meeting_type=meeting_type,
                project_type=project_type,
                engagement_tier=engagement_tier,
                jurisdiction=jurisdiction,
                contact_info=contact_info,
                wiki_enhancement=wiki_enhancement,
                created_at=self.get_current_timestamp(),
                scraped_from=source_url,
                # Enhanced fields
                action_type=action_type,
                when_human=when_human,
                deadline_reason=deadline_reason,
                agenda_item_number=agenda_item_number,
                engagement=engagement_structure,
                agenda_page=agenda_page,
                timezone=timezone_field
            )
            
            # Validate before returning
            if not self.validate_opportunity(opportunity):
                logging.warning(f"Event failed validation: {title}")
                # Return it anyway but with warnings logged
                
            return opportunity
            
        except Exception as e:
            logging.error(f"Failed to adapt opportunity '{item.get('title', 'Unknown')}': {e}")
            return None

    def adapt_newsletter(self, civic_data: Dict, html_content: str,
                        source_url: str, recipients: List[str] = None) -> Optional[SchemaNewsletter]:
        """Convert civic_digest.py output to schema-compliant Newsletter with validation"""
        import logging

        if recipients is None:
            recipients = []

        try:
            meeting_data = civic_data.get('meeting', {})


            # Set jurisdiction context for timezone handling
            jurisdiction_id = meeting_data.get('jurisdiction_id', 'city-san-rafael')
            self.current_jurisdiction_id = jurisdiction_id
            items_data = civic_data.get('items', [])

            # For CivicPlus calendar events without agenda items, use event_metadata
            event_metadata = civic_data.get('event_metadata')
            if not items_data and event_metadata:
                # Calendar event: use metadata directly instead of treating it as an agenda item
                logging.info(f"Using event_metadata for calendar event: {event_metadata.get('title', 'Unknown')}")

            # Create jurisdiction
            jurisdiction = self.extract_jurisdiction_from_meeting(meeting_data)

            # EVENT-CENTRIC ARCHITECTURE: Create ONE opportunity for the MEETING itself
            # with agenda items as nested expansion (not separate events)

            # For calendar events without agendas, use event_metadata directly (skip LLM)
            if not items_data and event_metadata:
                # Fast path: Use calendar event metadata directly
                meeting_title = event_metadata.get('title', 'City Meeting')
                meeting_type_classification = meeting_data.get('meeting_type', 'public_meeting')
                meeting_description = event_metadata.get('change', event_metadata.get('impact', 'Calendar event'))
                project_type = event_metadata.get('project_type', 'governance')
                speaking_duration_minutes = None

                # Extract datetime from event_metadata if available (for API-based sources like Granicus, CivicClerk, Legistar)
                event_when = event_metadata.get('when')
                if event_when:
                    # Store for later use instead of parsing from meeting_data
                    meeting_data['_event_metadata_when'] = event_when

                logging.info(f"Using calendar event metadata directly: {meeting_title}")
            else:
                # LLM-based meeting metadata extraction for meetings with agenda items
                def extract_meeting_metadata_with_llm(source_url, meeting_data, items_data):
                    """Use LLM to extract accurate meeting title, type, and description"""
                    import openai

                    # Prepare context (limit to first 5 items to control token usage)
                    items_summary = [{"title": item.get("title", ""), "type": item.get("project_type", "")}
                                    for item in items_data[:5]]

                    prompt = f"""Extract meeting information from this civic meeting data.

Source URL: {source_url}
Meeting type field: {meeting_data.get('meeting_type', 'Not specified')}
Location: {meeting_data.get('location', 'Not specified')}
Public comment rules: {meeting_data.get('public_comment_rules', 'Not specified')}
Agenda items (first 5): {json.dumps(items_summary, indent=2)}

Return JSON only:
{{
    "title": "Official meeting name (e.g., 'Zoning Administrator Hearing', 'Bicycle and Pedestrian Advisory Committee Meeting')",
    "meeting_type": "classification (choose one): zoning_administrator|planning_commission|city_council|advisory_committee|school_board|board_of_supervisors|public_meeting",
    "description": "Brief description of main agenda topics (50 words max)",
    "primary_focus": "Main category (choose one): zoning|transportation|community_services|education|housing|planning|governance",
    "speaking_duration_minutes": number or null (extract from public comment rules if mentioned, e.g. '3 minutes' = 3)
}}

Be accurate and specific. Use official meeting names from the URL or meeting_type field."""

                    try:
                        response = openai.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content": prompt}],
                            response_format={"type": "json_object"},
                            temperature=0.1,
                            max_tokens=300
                        )

                        result = json.loads(response.choices[0].message.content)
                        logging.info(f"LLM extracted meeting metadata: {result.get('title', 'Unknown')}")
                        return result

                    except Exception as e:
                        logging.warning(f"LLM meeting metadata extraction failed: {e}")
                        # Fallback to basic extraction
                        return {
                            "title": meeting_data.get('meeting_type', 'City Meeting'),
                            "meeting_type": "public_meeting",
                            "description": f"Meeting with {len(items_data)} agenda items",
                            "primary_focus": "governance",
                            "speaking_duration_minutes": None
                        }

                # Extract meeting metadata using LLM
                metadata = extract_meeting_metadata_with_llm(source_url, meeting_data, items_data)
                meeting_title = metadata.get('title', 'City Meeting')
                meeting_type_classification = metadata.get('meeting_type', 'public_meeting')
                meeting_description = metadata.get('description', f"Meeting with {len(items_data)} agenda items")
                project_type = metadata.get('primary_focus', 'governance')
                speaking_duration_minutes = metadata.get('speaking_duration_minutes')

            meeting_date_str = meeting_data.get('date', '')
            meeting_time_str = meeting_data.get('start_time', '')
            meeting_location = meeting_data.get('location', 'Location not specified')

            # Parse meeting datetime
            meeting_datetime = None

            # Priority 1: Use event_metadata when if available (API sources like Granicus, CivicClerk, Legistar)
            if '_event_metadata_when' in meeting_data:
                try:
                    from dateutil import parser
                    meeting_datetime = parser.parse(meeting_data['_event_metadata_when'])
                    # Apply timezone if missing
                    if meeting_datetime.tzinfo is None:
                        jurisdiction_id = jurisdiction.id if jurisdiction else 'unknown'
                        timezone_field = JurisdictionRegistry.get_timezone(jurisdiction_id, default='America/Los_Angeles')
                        import pytz
                        tz = pytz.timezone(timezone_field)
                        meeting_datetime = tz.localize(meeting_datetime)
                    logging.info(f"Using event_metadata datetime: {meeting_datetime}")
                except Exception as e:
                    logging.warning(f"Unable to parse event_metadata datetime: {e}")
                    meeting_datetime = None

            # Priority 2: Parse from meeting_data date/time fields (HTML scraping sources)
            if meeting_datetime is None and meeting_date_str and meeting_time_str:
                try:
                    from dateutil import parser
                    combined = f"{meeting_date_str} {meeting_time_str}"
                    meeting_datetime = parser.parse(combined)
                    # Apply timezone
                    jurisdiction_id = jurisdiction.id if jurisdiction else 'unknown'
                    timezone_field = JurisdictionRegistry.get_timezone(jurisdiction_id, default='America/Los_Angeles')
                    if meeting_datetime.tzinfo is None:
                        import pytz
                        tz = pytz.timezone(timezone_field)
                        meeting_datetime = tz.localize(meeting_datetime)
                except Exception as e:
                    logging.error(f"Unable to parse meeting datetime: {e}")
                    meeting_datetime = None

            # Critical: If no valid datetime found, skip this meeting to prevent invalid data
            if meeting_datetime is None:
                logging.error(f"CRITICAL: No valid meeting datetime found for {meeting_title} - cannot create valid newsletter")
                logging.error(f"  Meeting data: date={meeting_date_str}, time={meeting_time_str}")
                logging.error(f"  Event metadata: {meeting_data.get('_event_metadata_when', 'Not available')}")
                return None  # Return None to signal invalid data rather than create invalid timestamps

            # Create meeting-level participation mechanisms
            participation_mechanisms = []
            if meeting_data.get('public_comment_email'):
                participation_mechanisms.append({
                    'type': 'email',
                    'contact': meeting_data['public_comment_email'],
                    'description': 'Send written comment',
                    'deadline': None,
                    'duration_minutes': None
                })

            # Attend mechanism with LLM-extracted duration
            participation_mechanisms.append({
                'type': 'attend',
                'location': meeting_location,
                'when': meeting_datetime.isoformat(),
                'description': 'Attend meeting for public comment',
                'duration_minutes': speaking_duration_minutes  # From LLM extraction
            })

            # Virtual participation mechanism (separate from attend)
            # Separate URL from meeting ID - livestream is URL, webinar is meeting ID
            virtual_url = meeting_data.get('livestream')  # Only use livestream for URL
            webinar_id = meeting_data.get('webinar') if not meeting_data.get('livestream') else None
            virtual_phone = meeting_data.get('phone')
            meeting_id = meeting_data.get('meeting_id')  # Explicit meeting ID field

            # Parse meeting ID from phone string if not already extracted
            # Common patterns: "1 (669) 444-9171, ID: 840 9897 7308#" or "Meeting ID: 840 9897 7308"
            if virtual_phone and not meeting_id:
                import re
                # Look for ID patterns: "ID: 123 456 7890" or "ID 12345678901" or "ID:123456"
                id_match = re.search(r'(?:ID|id|Meeting ID|meeting id)[:\s]+([0-9\s#]+)', virtual_phone)
                if id_match:
                    # Extract and clean meeting ID (remove spaces and #)
                    meeting_id = id_match.group(1).replace('#', '').strip()
                    # Clean phone number by removing everything after "ID"
                    virtual_phone = re.sub(r',?\s*(?:ID|id|Meeting ID|meeting id)[:\s]+.*$', '', virtual_phone).strip()


            # Phase 2: LLM fallback if no virtual info found but location suggests hybrid
            if not virtual_url and not webinar_id and not virtual_phone:
                # Check if location hints at virtual access
                location_lower = meeting_location.lower() if meeting_location else ''
                if any(keyword in location_lower for keyword in ['virtual', 'zoom', 'online', 'hybrid', 'remote']):
                    # Use LLM to extract virtual access details
                    try:
                        import openai

                        prompt = f"""Extract virtual meeting access information from this meeting data.

Meeting location: {meeting_location}
Public comment rules: {meeting_data.get('public_comment_rules', '')}

Return JSON only:
{{
    "has_virtual_access": true/false,
    "platform": "zoom|webex|microsoft_teams|livestream|phone|null",
    "url": "full URL if found, or null",
    "phone": "dial-in number if found, or null"
}}

Only return has_virtual_access=true if you find ACTUAL virtual access details. Be conservative."""

                        response = openai.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content": prompt}],
                            response_format={"type": "json_object"},
                            temperature=0.1,
                            max_tokens=200
                        )

                        result = json.loads(response.choices[0].message.content)

                        if result.get('has_virtual_access'):
                            virtual_url = result.get('url')
                            virtual_phone = result.get('phone')
                            if result.get('platform'):
                                platform = result['platform']
                            logging.info(f"LLM extracted virtual access: {result.get('platform')}")

                    except Exception as e:
                        logging.warning(f"LLM virtual access extraction failed: {e}")

            if virtual_url or webinar_id or virtual_phone:
                # Determine platform type
                platform = 'phone'  # Default if only phone
                if meeting_data.get('livestream'):
                    platform = 'livestream'
                elif webinar_id:
                    platform = 'zoom'  # Meeting IDs are typically Zoom
                elif virtual_url:
                    url_lower = virtual_url.lower()
                    if 'zoom' in url_lower:
                        platform = 'zoom'
                    elif 'teams' in url_lower:
                        platform = 'microsoft_teams'
                    elif 'webex' in url_lower:
                        platform = 'webex'

                virtual_mechanism = {
                    'type': 'virtual',
                    'platform': platform,
                    'description': 'Join meeting virtually',
                    'when': meeting_datetime.isoformat(),
                    'duration_minutes': speaking_duration_minutes
                }

                if virtual_url:
                    virtual_mechanism['url'] = virtual_url
                if webinar_id:
                    virtual_mechanism['meeting_id'] = webinar_id
                elif meeting_id:  # Use parsed meeting_id if no webinar_id
                    virtual_mechanism['meeting_id'] = meeting_id
                if virtual_phone:
                    virtual_mechanism['phone'] = virtual_phone

                participation_mechanisms.append(virtual_mechanism)

            # Create contact info from meeting data
            contact_info = ContactInfo(
                email=meeting_data.get('public_comment_email'),
                name=None,
                title=None,
                phone=meeting_data.get('phone'),
                office=None
            )

            # Create the meeting opportunity (event-centric)
            meeting_opportunity = SchemaCivicOpportunity(
                id=self.generate_uuid(),
                title=meeting_title,  # From LLM extraction
                original_title=meeting_title,
                description=meeting_description,  # From LLM extraction
                when=meeting_datetime,
                deadline=None,
                engagement_info=meeting_data.get('public_comment_rules'),
                impact_summary=meeting_description,  # Use LLM-generated description
                source_url=source_url,
                location=meeting_location,
                meeting_type=meeting_type_classification,  # From LLM extraction
                project_type=project_type,  # From LLM extraction
                engagement_tier='meeting',
                jurisdiction=jurisdiction,
                contact_info=contact_info,
                wiki_enhancement=WikiEnhancement(
                    success_strategy="Standard public comment procedures apply",
                    precedent_examples=[],
                    recommended_approach=None,
                    related_opportunities=[]
                ),
                created_at=self.get_current_timestamp(),
                scraped_from=source_url,
                action_type='meeting',
                when_human=meeting_datetime.strftime('%a %b %d, %Y • %I:%M %p %Z'),
                deadline_reason=None,
                agenda_item_number=None,
                engagement=None,
                agenda_page=None,
                timezone=JurisdictionRegistry.get_timezone(jurisdiction_id, default='America/Los_Angeles')
            )

            # Store events as single meeting event
            events = [meeting_opportunity]

            # Store raw items data for agenda expansion processing
            # This will be converted to agenda_expansion.actionable_items by enhancement pipeline
            if items_data:
                # Temporarily store items in a special field for processing
                meeting_opportunity._raw_agenda_items = items_data
                meeting_opportunity._meeting_metadata = meeting_data

            # Preserve agenda metadata from meeting_data and event_metadata
            # Priority: meeting_data (newer architecture) > event_metadata (legacy)
            if meeting_data and 'agenda_url' in meeting_data:
                meeting_opportunity.agenda_url = meeting_data['agenda_url']

            # Preserve agenda metadata from event_metadata (for Legistar/CivicClerk/Granicus calendar events)
            if event_metadata:
                # Preserve agenda URL and expansion structure (fallback)
                if 'agenda_url' in event_metadata and not hasattr(meeting_opportunity, 'agenda_url'):
                    meeting_opportunity.agenda_url = event_metadata['agenda_url']
                if 'agenda_expansion' in event_metadata:
                    meeting_opportunity.agenda_expansion = event_metadata['agenda_expansion']
                # Preserve platform-specific metadata for agenda integration
                if '_legistar_metadata' in event_metadata:
                    meeting_opportunity._legistar_metadata = event_metadata['_legistar_metadata']
                if '_civicclerk_metadata' in event_metadata:
                    meeting_opportunity._civicclerk_metadata = event_metadata['_civicclerk_metadata']
                if '_granicus_metadata' in event_metadata:
                    meeting_opportunity._granicus_metadata = event_metadata['_granicus_metadata']

            # Store participation mechanisms for enhancement pipeline
            meeting_opportunity._participation_mechanisms = participation_mechanisms
            
            # Extract subject line from HTML with better parsing
            subject_line = self._extract_subject_line(html_content, jurisdiction.name)
            
            # Get unparseable URLs from city config
            unparseable_urls = self._get_unparseable_urls_for_jurisdiction(jurisdiction_id)

            # Create metadata
            generation_metadata = GenerationMetadata(
                scrape_urls=[source_url],
                ai_model_used="gpt-5-mini",
                wiki_files_loaded=[],
                generation_cost=0.0,  # Could be calculated
                processing_time=0.0,   # Could be measured
                unparseable_urls=unparseable_urls
            )
            
            # Create analytics
            analytics = NewsletterAnalytics(sent_count=len(recipients))
            
            newsletter = SchemaNewsletter(
                id=self.generate_uuid(),
                jurisdiction=jurisdiction,
                events=events,
                generation_metadata=generation_metadata,
                html_content=html_content,
                text_content=self.html_to_text(html_content),
                subject_line=subject_line,
                send_date=self.get_current_timestamp(),
                recipients=recipients,
                analytics=analytics,
                created_at=self.get_current_timestamp()
            )
            
            logging.info(f"Successfully adapted newsletter: {len(events)} events, "
                        f"jurisdiction: {jurisdiction.name}")
            
            return newsletter
            
        except Exception as e:
            logging.error(f"Failed to adapt newsletter: {e}")
            return None
    
    def _extract_subject_line(self, html_content: str, jurisdiction_name: str) -> str:
        """Extract subject line from HTML with fallbacks"""
        if not html_content:
            return f"{jurisdiction_name} Civic Update"
        
        # Try multiple subject line patterns
        patterns = [
            r'Subject:\s*(.+)',
            r'<title[^>]*>([^<]+)</title>',
            r'# (.+)',  # Markdown header
            r'<h1[^>]*>([^<]+)</h1>'  # HTML h1
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                subject = match.group(1).strip()
                if subject and len(subject) > 5:  # Reasonable subject length
                    return subject
        
        # Fallback to jurisdiction-based subject
        return f"{jurisdiction_name} Civic Update"

    def _get_unparseable_urls_for_jurisdiction(self, jurisdiction_id: str) -> Optional[List[dict]]:
        """Get unparseable URLs for a jurisdiction from city config"""
        try:
            # Import at module level to avoid import issues
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            from civicos_services.monitoring.automated_civic_refresh import CITY_CONFIGS

            # Find city config by jurisdiction_id
            for city_key, config in CITY_CONFIGS.items():
                if config.get('jurisdiction_id') == jurisdiction_id:
                    manual_refs = config.get('manual_references', [])
                    if manual_refs:
                        # Format for user-facing display
                        unparseable_urls = []
                        for ref in manual_refs:
                            unparseable_urls.append({
                                "url": ref["url"],
                                "reason": ref["reason"],
                                "user_guidance": f"Visit link for {ref['description']}"
                            })
                        return unparseable_urls
            return None
        except Exception as e:
            # Debug: print the exception
            import logging
            logging.warning(f"Could not load unparseable URLs for {jurisdiction_id}: {e}")
            return None

    def to_dict(self, obj) -> Dict:
        """Convert dataclass to dictionary for JSON serialization"""
        if hasattr(obj, '__dict__'):
            result = {}
            for key, value in obj.__dict__.items():
                if hasattr(value, '__dict__'):
                    result[key] = self.to_dict(value)
                elif isinstance(value, list):
                    result[key] = [self.to_dict(item) if hasattr(item, '__dict__') else item
                                  for item in value]
                else:
                    # Convert empty strings to null for JSON compliance
                    # Handle None values from optional fields
                    if value == "" or value is None:
                        result[key] = None
                    else:
                        result[key] = value
            return result
        return obj


# Integration function for existing civic_digest.py
def integrate_with_civic_digest():
    """
    Integration point for civic_digest.py
    Add this to civic_digest.py to get schema-compliant output
    """
    adapter = CivicSchemaAdapter()
    
    # Example usage:
    # schema_newsletter = adapter.adapt_newsletter(civic_data, html_content, source_url)
    # schema_dict = adapter.to_dict(schema_newsletter)
    # 
    # Now you have schema-compliant data that can be:
    # 1. Validated against civic-app-schema.json
    # 2. Used in conversational interface
    # 3. Stored in database with consistent structure
    # 4. Passed to LLM co-pilots with full context
    
    return adapter


if __name__ == "__main__":
    # Test the adapter with sample data
    adapter = CivicSchemaAdapter()
    
    # Sample civic_digest.py data structure
    sample_data = {
        "meeting": {
            "city": "San Rafael",
            "date": "March 15, 2024",
            "start_time": "18:00",
            "location": "Council Chambers",
            "public_comment_email": "clerk@cityofsanrafael.org",
            "meeting_type": "Planning Commission"
        },
        "items": [
            {
                "title": "Oak Street Housing Development",
                "change": "New 50-unit apartment complex",
                "impact": "Increased housing supply but potential traffic concerns",
                "how_to_participate": "Email comments by March 12 or attend meeting",
                "project_type": "housing",
                "location": "123 Oak Street"
            }
        ],
        "bottom_line": "One housing project up for review"
    }
    
    sample_html = """
    Subject: Planning Commission Meeting - March 15, 2024
    # ✉️ San Rafael Planning Commission
    <p>Your guide to what's on the agenda...</p>
    """
    
    # Convert to schema-compliant format
    newsletter = adapter.adapt_newsletter(
        sample_data, 
        sample_html, 
        "https://example.com/meeting", 
        ["test@example.com"]
    )
    
    # Output as JSON for testing
    schema_dict = adapter.to_dict(newsletter)
    print(json.dumps(schema_dict, indent=2))