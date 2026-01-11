#!/usr/bin/env python3
"""
Civic Engagement MVP - All-in-One Digest Generator

This single file contains everything needed to:
- Scrape city meeting agendas using AI
- Generate engaging email digests
- Send automated weekly summaries
- Manage beta testing
- Generate schema-compliant data for conversational interface

Usage:
  python civic_digest.py scrape "meeting-url" user@email.com
  python civic_digest.py weekly
  python civic_digest.py test
  python civic_digest.py schema "meeting-url"  # NEW: Generate schema-compliant JSON
"""

import os
import sys

# Add src directory to Python path for production imports
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
import re
import json
import time
import smtplib
import schedule
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import openai

# Import schema adapter for conversational interface integration
try:
    from civic_schema_adapter import CivicSchemaAdapter
    SCHEMA_ADAPTER_AVAILABLE = True
except ImportError:
    print("⚠️ Schema adapter not available - schema output disabled")
    SCHEMA_ADAPTER_AVAILABLE = False

# Import agent type system and unified data source manager
try:
    from civic_services.monitoring.automated_civic_refresh import get_jurisdiction_agent_type, CITY_CONFIGS
    from civic_services.monitoring.unified_data_source_manager import UnifiedDataSourceManager
    from civic_services.core.municipal_registry import MUNICIPAL_REGISTRY
    AGENT_REGISTRY_AVAILABLE = True
except ImportError:
    print("⚠️ Agent registry not available - using standard extraction only")
    AGENT_REGISTRY_AVAILABLE = False

# Import CivicClerk API client
try:
    from civicclerk_client import create_client as create_civicclerk_client
    CIVICCLERK_AVAILABLE = True
except ImportError:
    print("⚠️ CivicClerk client not available - using HTML extraction fallback")
    CIVICCLERK_AVAILABLE = False

# Import Granicus API client
try:
    from granicus_client import create_client as create_granicus_client
    GRANICUS_AVAILABLE = True
except ImportError:
    print("⚠️ Granicus client not available - using HTML extraction fallback")
    GRANICUS_AVAILABLE = False

# Import agenda integration system
try:
    from agenda_integration import enhance_events_with_agenda_integration
    AGENDA_INTEGRATION_AVAILABLE = True
except ImportError:
    print("⚠️ Agenda integration not available - basic events only")
    AGENDA_INTEGRATION_AVAILABLE = False

# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class CivicOpportunity:
    """A single civic engagement opportunity"""
    title: str
    when: str  # ISO date string
    engagement_info: str
    impact_summary: str
    source_url: str
    location: str = ""
    deadline: str = ""
    project_type: str = ""
    # Wiki intelligence fields (populated by Round 2 LLM)
    contact_email: str = ""
    contact_name: str = ""
    success_strategy: str = ""
    engagement_tier: str = "email"  # email, comment, attend
    deadline_guidance: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)

# ============================================================================
# CORE CIVIC DIGEST CLASS
# ============================================================================

class CivicDigest:
    """All-in-one civic engagement digest generator"""
    
    def __init__(self):
        # Get credentials from environment
        self.openai_key = os.getenv('OPENAI_API_KEY')
        self.gmail_email = os.getenv('GMAIL_EMAIL')
        self.gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        
        if not all([self.openai_key, self.gmail_email, self.gmail_password]):
            print("❌ Missing environment variables:")
            if not self.openai_key: print("  - OPENAI_API_KEY")
            if not self.gmail_email: print("  - GMAIL_EMAIL") 
            if not self.gmail_password: print("  - GMAIL_APP_PASSWORD")
            print("\nSet up instructions:")
            print("export OPENAI_API_KEY='your-key'")
            print("export GMAIL_EMAIL='your@email.com'")
            print("export GMAIL_APP_PASSWORD='your-16-char-app-password'")
            exit(1)
        
        self.openai_client = openai.OpenAI(api_key=self.openai_key)
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (CivicEngagement/1.0)'})

        # Initialize platform-aware agent registry
        # Future: Agent registry initialization can be added here
        self.agent_registry = None
    
    def scrape_meeting(self, url: str) -> str:
        """Scrape a single meeting URL and generate newsletter directly

        Enhanced with AI-powered URL discovery for calendar pages while maintaining
        backwards compatibility for direct meeting URLs.
        """
        print(f"🔍 Scraping: {url}")

        try:
            # NEW: Platform-aware agentic URL discovery
            discovered_urls = self._discover_meeting_urls_with_agents(url)

            # If multiple URLs discovered, process all and combine
            if len(discovered_urls) > 1:
                print(f"📋 Processing {len(discovered_urls)} discovered meeting URLs")
                all_civic_data = []

                for i, meeting_url in enumerate(discovered_urls):
                    try:
                        print(f"🔄 Processing meeting {i+1}/{len(discovered_urls)}: {meeting_url}")

                        # Generate individual newsletter for each meeting
                        individual_newsletter = self._generate_civic_newsletter(meeting_url)

                        # Store civic data for combination
                        if hasattr(self, '_last_civic_data'):
                            civic_data = self._last_civic_data.copy()
                            civic_data['source_url'] = meeting_url
                            all_civic_data.append(civic_data)

                    except Exception as e:
                        print(f"⚠️ Error processing {meeting_url}: {e}")
                        continue

                # Combine all civic data into a single newsletter
                if all_civic_data:
                    combined_newsletter = self._render_combined_newsletter(all_civic_data, url)
                    print(f"✅ Generated combined newsletter from {len(all_civic_data)} meetings")
                    return combined_newsletter
                else:
                    print(f"⚠️ No meetings successfully processed, falling back to original URL")
                    # Fallback to original single-URL processing
                    newsletter = self._generate_civic_newsletter(url)
                    print(f"✅ Generated civic newsletter")
                    return newsletter

            else:
                # EXISTING: Single URL processing (backwards compatible)
                newsletter = self._generate_civic_newsletter(discovered_urls[0])
                print(f"✅ Generated civic newsletter")
                return newsletter

        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")
            return f"# ✉️ Civic Brief\n*Unable to generate newsletter for this meeting*\n\nError: {str(e)}"
    
    def _generate_civic_newsletter(self, agenda_url: str) -> str:
        """Generate civic newsletter using two-pass Responses API approach"""
        
        try:
            # Step 1: Platform-aware content extraction
            joined_sources = self._extract_meeting_content_with_agents(agenda_url)
            
            # Step 2: Extract structured JSON using Responses API
            civic_data = self._extract_civic_data(joined_sources, agenda_url)

            # Step 2.4: Handle multi-meeting calendar results (CivicPlus calendars)
            if civic_data.get('is_multi_meeting_calendar'):
                print(f"📅 Processing multi-meeting calendar with {len(civic_data.get('meetings', []))} events")
                # Store all meetings for later use, but process first one for newsletter
                self._multi_meeting_data = civic_data.get('meetings', [])
                if self._multi_meeting_data:
                    civic_data = self._multi_meeting_data[0]  # Use first meeting for newsletter rendering
                    print(f"📋 Using first meeting for rendering: {civic_data.get('meeting', {}).get('meeting_type', 'unknown')}")
                else:
                    print(f"⚠️ Multi-meeting calendar has no meetings, falling back to empty data")
                    civic_data = self._get_empty_civic_data()

            # Step 2.5: Apply post-processing for accuracy and consistency
            try:
                from civic_data_postprocessor import CivicDataPostProcessor
                from civic_services.monitoring.automated_civic_refresh import get_jurisdiction_by_url

                jurisdiction_id = get_jurisdiction_by_url(agenda_url)
                processor = CivicDataPostProcessor(self.openai_client)
                civic_data = processor.process_civic_data(civic_data, agenda_url, jurisdiction_id)

                print(f"✅ Applied post-processing for jurisdiction: {jurisdiction_id}")

                # Extract city name from jurisdiction_id for display
                if jurisdiction_id.startswith('city-'):
                    city_name = jurisdiction_id[5:].replace('-', ' ').title()
                elif jurisdiction_id == 'marin-county':
                    city_name = 'Marin County'
                else:
                    city_name = jurisdiction_id.replace('-', ' ').title()

                # Ensure meeting section exists and add jurisdiction info
                if 'meeting' not in civic_data:
                    civic_data['meeting'] = {}
                civic_data['meeting']['jurisdiction_id'] = jurisdiction_id
                civic_data['meeting']['city'] = city_name

                # Also add to top level for backward compatibility
                civic_data['jurisdiction_id'] = jurisdiction_id
                civic_data['city'] = city_name

            except ImportError as e:
                print(f"⚠️ Could not import post-processor or jurisdiction detection: {e}")
                # Fallback to basic jurisdiction detection
                try:
                    from civic_services.monitoring.automated_civic_refresh import get_jurisdiction_by_url
                    jurisdiction_id = get_jurisdiction_by_url(agenda_url)
                    civic_data['jurisdiction_id'] = jurisdiction_id
                except ImportError:
                    print("⚠️ Could not import jurisdiction detection")

            # Step 3: Render newsletter from structured data
            newsletter = self._render_newsletter(civic_data, agenda_url)
            
            # Store civic_data for schema adapter use
            self._last_civic_data = civic_data
            self._last_source_url = agenda_url
            
            return newsletter
            
        except Exception as e:
            print(f"❌ Error generating newsletter: {e}")
            return f"# ✉️ Civic Brief\n*Error generating newsletter*\n\nUnable to process {agenda_url}: {str(e)}"
    
    def _get_extraction_schema(self):
        """JSON schema for structured civic data extraction"""
        return {
            "name": "CivicNewsletter",
            "schema": {
                "type": "object",
                "properties": {
                    "meeting": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"},
                            "date": {"type": "string"},
                            "start_time": {"type": "string"},
                            "location": {"type": "string"},
                            "livestream": {"type": "string"},
                            "webinar": {"type": "string"},
                            "phone": {"type": "string"},
                            "public_comment_email": {"type": "string"},
                            "public_comment_deadline": {"type": "string"},
                            "public_comment_rules": {"type": "string"},
                            "meeting_type": {"type": "string"}
                        },
                        "required": ["date"]
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "change": {"type": "string"},
                                "impact": {"type": "string"},
                                "how_to_participate": {"type": "string"},
                                "location": {"type": "string"},
                                "project_type": {
                                    "type": "string",
                                    "enum": ["housing","transportation","environment","budget","education","development","public_safety","community","elections","governance"]
                                }
                            },
                            "required": ["title","change","impact","how_to_participate","project_type"]
                        }
                    },
                    "recap_rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {"type": "string"},
                                "why_it_matters": {"type": "string"},
                                "act_by": {"type": "string"}
                            },
                            "required": ["topic","why_it_matters","act_by"]
                        }
                    },
                    "bottom_line": {"type": "string"}
                },
                "required": ["meeting","items","recap_rows","bottom_line"],
                "additionalProperties": False
            }
        }
    
    def _scrape_meeting_sources(self, agenda_url: str) -> str:
        """Scrape and extract text from meeting page, agenda packets, and staff reports"""
        try:
            # Get main meeting page
            response = self.session.get(agenda_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract main page text
            main_text = soup.get_text()
            texts = [f"MAIN PAGE:\n{main_text}"]
            
            # Find PDF links for agenda packets and staff reports
            pdf_links = []
            # Also extract meeting page links for URL discovery
            meeting_links = []

            for link in soup.find_all('a', href=True):
                href = link['href']
                link_text = link.get_text().strip()

                # Convert relative URLs to absolute
                if href.startswith('/'):
                    from urllib.parse import urlparse
                    parsed = urlparse(agenda_url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"
                elif not href.startswith('http') and not href.startswith('#'):
                    href = f"{agenda_url}/{href}"

                if href.endswith('.pdf'):
                    pdf_links.append(href)
                elif ('/meetings/' in href or
                      any(keyword in link_text.lower() for keyword in ['committee', 'commission', 'hearing', 'council', 'board']) and
                      any(date_keyword in href.lower() for date_keyword in ['2025', 'october', 'september', 'november'])):
                    # Capture meeting page links with committee/board names and recent dates
                    meeting_links.append(f"{href} ({link_text})")

            # Add meeting links to content for URL discovery
            if meeting_links:
                meeting_links_text = "\n".join([f"MEETING LINK: {link}" for link in meeting_links])
                texts.append(f"DISCOVERED MEETING LINKS:\n{meeting_links_text}")
            
            # Extract text from PDFs (limit to first 5 to avoid token limits)
            for i, pdf_url in enumerate(pdf_links[:5]):
                try:
                    print(f"📄 Processing PDF {i+1}/{min(5, len(pdf_links))}: {pdf_url}")
                    pdf_text = self._extract_pdf_text(pdf_url)
                    if pdf_text:
                        texts.append(f"PDF DOCUMENT {i+1}:\n{pdf_text}")
                except Exception as e:
                    print(f"⚠️ Failed to extract PDF {pdf_url}: {e}")
                    continue
            
            # Join all texts with clear separators
            joined = "\n\n" + "="*50 + "\n\n".join(texts)
            
            # Truncate to safe token limit (approximately 12k tokens = 48k chars)
            return self._truncate_safely(joined, limit_chars=48000)
            
        except Exception as e:
            print(f"❌ Error scraping sources: {e}")
            return f"Unable to scrape meeting sources from {agenda_url}"
    
    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Extract text from PDF URL (basic implementation)"""
        try:
            import PyPDF2
            import io
            
            response = self.session.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            # Limit to first 10 pages to avoid token limits
            for page_num in range(min(10, len(pdf_reader.pages))):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n\n"
            
            return text
            
        except ImportError:
            print("⚠️ PyPDF2 not available - skipping PDF extraction")
            return ""
        except Exception as e:
            print(f"⚠️ PDF extraction failed: {e}")
            return ""

    def _discover_meeting_urls(self, calendar_url: str) -> List[str]:
        """AI-powered discovery of specific meeting URLs from calendar pages

        Maintains backwards compatibility - if discovery fails or finds nothing,
        returns the original URL to preserve existing functionality.
        """
        try:
            print(f"🔍 Discovering meeting URLs from calendar: {calendar_url}")

            # Phase 1: Extract calendar page content using existing scraping logic
            calendar_content = self._scrape_meeting_sources(calendar_url)

            # Phase 2: AI extracts specific meeting URLs
            current_date = datetime.now().strftime('%Y-%m-%d')
            discovery_prompt = f"""
Extract specific meeting page URLs from this calendar/listing page for upcoming meetings.
Focus on meetings in the NEXT 30 DAYS (after {current_date}) - prioritize the most immediate meetings.

Look for:
- Individual meeting pages with agendas or details
- Specific meeting URLs (not general calendar pages)
- Meeting links for dates like 2025-09-22, 2025-09-25, etc.
- "Agenda", "Meeting Details", "View Meeting" type links
- URLs that lead to specific meeting content

PRIORITIZE: Find meetings happening in the next few days/weeks, not months away.

Return ONLY a JSON array of complete URLs that lead to specific meeting pages:
["https://example.gov/meeting1", "https://example.gov/meeting2"]

For Legistar calendars, look for meeting detail links or agenda URLs.
For city council pages, look for specific agenda packet URLs.

If no specific meeting URLs are found, return an empty array: []

Calendar content:
{calendar_content[:8000]}
"""

            # Use existing OpenAI infrastructure with conservative settings
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": discovery_prompt}],
                temperature=0.0,  # Deterministic output
                max_tokens=1000   # Limit response size
            )

            # Parse AI response
            ai_response = response.choices[0].message.content.strip()

            # Handle cases where AI returns text around the JSON
            if ai_response.startswith('[') and ai_response.endswith(']'):
                discovered_urls = json.loads(ai_response)
            else:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\[.*?\]', ai_response, re.DOTALL)
                if json_match:
                    discovered_urls = json.loads(json_match.group())
                else:
                    discovered_urls = []

            # Validate URLs and convert relative to absolute
            valid_urls = []
            seen_base_urls = set()  # Track base URLs without anchors to avoid duplicates
            for url in discovered_urls:
                if isinstance(url, str) and (url.startswith('http') or url.startswith('/')):
                    # Convert relative URLs to absolute
                    if url.startswith('/'):
                        from urllib.parse import urlparse
                        parsed = urlparse(calendar_url)
                        url = f"{parsed.scheme}://{parsed.netloc}{url}"

                    # Strip anchor fragments (#tab-agenda, #tab-agenda-packet, etc.)
                    # These point to the same meeting page, just different tabs
                    # Keep query parameters as they may distinguish different meetings
                    from urllib.parse import urlparse, urlunparse
                    parsed = urlparse(url)
                    base_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ''))

                    # Only add if we haven't seen this base URL before
                    if base_url not in seen_base_urls:
                        valid_urls.append(base_url)
                        seen_base_urls.add(base_url)

            if valid_urls:
                print(f"✅ Discovered {len(valid_urls)} meeting URLs")
                for i, url in enumerate(valid_urls[:3]):  # Show first 3
                    print(f"   {i+1}. {url}")
                if len(valid_urls) > 3:
                    print(f"   ... and {len(valid_urls) - 3} more")
                return valid_urls
            else:
                print(f"⚠️ No specific meeting URLs discovered, falling back to original URL")
                return [calendar_url]

        except Exception as e:
            print(f"⚠️ URL discovery failed: {e}, falling back to original URL")
            return [calendar_url]

    def _discover_meeting_urls_with_agents(self, calendar_url: str) -> List[str]:
        """Platform-aware agentic URL discovery"""
        if not AGENT_REGISTRY_AVAILABLE:
            return self._discover_meeting_urls(calendar_url)

        # Check if this is a Legistar or CivicClerk URL that should use API directly
        agent_type = get_jurisdiction_agent_type(calendar_url)
        if agent_type == "legistar":
            print(f"🏛️ Detected Legistar URL - using direct API access instead of URL discovery")
            return [calendar_url]  # Return original URL for direct API processing
        elif agent_type == "civicclerk":
            print(f"🏛️ Detected CivicClerk URL - using direct API access instead of URL discovery")
            return [calendar_url]  # Return original URL for direct API processing
        elif agent_type == "san_rafael_cms":
            print(f"🏛️ Detected San Rafael URL - using BeautifulSoup table extraction")
            # Use BeautifulSoup to extract meeting URLs from table
            try:
                from bs4 import BeautifulSoup
                import requests
                import re

                response = requests.get(calendar_url, timeout=30)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find the meetings table
                table = soup.find('table', class_='table-striped')
                if table:
                    tbody = table.find('tbody')
                    if tbody:
                        meeting_urls = []
                        rows = tbody.find_all('tr')

                        for row in rows:
                            cells = row.find_all('td')
                            if len(cells) < 2:
                                continue

                            # First cell contains the meeting link
                            meeting_link = cells[0].find('a', href=re.compile(r'/meetings/'))
                            if meeting_link and meeting_link.get('href'):
                                url = meeting_link['href']

                                # Normalize to absolute URL
                                if not url.startswith('http'):
                                    url = f"https://www.cityofsanrafael.org{url}" if url.startswith('/') else f"https://www.cityofsanrafael.org/meetings/{url}"

                                # Strip anchor fragments
                                url = url.split('#')[0]

                                if url not in meeting_urls:
                                    meeting_urls.append(url)

                        if meeting_urls:
                            print(f"✅ BeautifulSoup discovered {len(meeting_urls)} meeting URLs from table")
                            return meeting_urls

            except Exception as e:
                print(f"⚠️ BeautifulSoup URL discovery failed: {e}, falling back to AI discovery")

            # Fall back to AI discovery if BeautifulSoup fails
            return self._discover_meeting_urls(calendar_url)

        # For other platforms, use AI-First discovery
        return self._discover_meeting_urls(calendar_url)

    def _extract_meeting_content_with_agents(self, meeting_url: str) -> str:
        """Future: Platform-aware agentic content extraction (currently uses universal)"""
        # For now, always use existing universal method
        return self._scrape_meeting_sources(meeting_url)

    def _truncate_safely(self, text: str, limit_chars: int = 48000) -> str:
        """Safely truncate text to stay within token limits"""
        if len(text) <= limit_chars:
            return text
        
        # Try to truncate at sentence boundaries
        truncated = text[:limit_chars]
        last_sentence = max(
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?'),
            truncated.rfind('\n\n')
        )
        
        if last_sentence > limit_chars * 0.8:  # Don't lose more than 20%
            truncated = truncated[:last_sentence + 1]
        
        return truncated + "\n\n[... content truncated for length ...]"
    
    def _extract_civic_data_multipass(self, joined_sources: str, source_url: str = "") -> dict:
        """Universal extraction with graceful agent fallback (future: agent registry)"""
        # For now, use standard extraction for all jurisdictions
        # Agent registry can be added later without breaking existing functionality
        print(f"🔄 Using universal extraction for {source_url}")
        return self._extract_civic_data_standard(joined_sources, source_url)


    def _extract_civic_data(self, joined_sources: str, source_url: str = "") -> dict:
        """Main extraction entry point - routes to agent-specific methods when available"""
        if not AGENT_REGISTRY_AVAILABLE or not source_url:
            return self._extract_civic_data_standard(joined_sources, source_url)

        # Get agent type for this URL
        agent_type = get_jurisdiction_agent_type(source_url)
        print(f"🤖 Agent type for {source_url}: {agent_type}")

        # Route to appropriate extraction method based on agent type
        if agent_type == "legistar":
            return self._extract_civic_data_legistar(joined_sources, source_url)
        elif agent_type == "berkeley_cms":
            return self._extract_civic_data_berkeley(joined_sources, source_url)
        elif agent_type == "san_rafael_cms":
            return self._extract_civic_data_san_rafael(joined_sources, source_url)
        elif agent_type == "civicplus_cms":
            return self._extract_civic_data_civicplus(joined_sources, source_url)
        elif agent_type == "civicclerk":
            # Extract CivicClerk subdomain directly from URL (e.g., "dalycityca" from "https://dalycityca.portal.civicclerk.com")
            import re
            subdomain_match = re.match(r'https?://([^.]+)\.(?:portal|api)\.civicclerk\.com', source_url)
            if subdomain_match:
                civicclerk_subdomain = subdomain_match.group(1)
                return self._extract_civic_data_civicclerk(source_url, civicclerk_subdomain)
            else:
                print(f"⚠️ Could not extract CivicClerk subdomain from URL: {source_url}")
                return self._extract_civic_data_standard(joined_sources, source_url)
        elif agent_type == "granicus":
            # Extract jurisdiction key from source_url for Granicus client
            from civic_services.monitoring.automated_civic_refresh import get_jurisdiction_by_url
            jurisdiction_key = get_jurisdiction_by_url(source_url)
            if jurisdiction_key:
                # Remove 'city-' prefix for client lookup
                jurisdiction_key = jurisdiction_key.replace('city-', '').replace('_', '-')
                return self._extract_civic_data_granicus(source_url, jurisdiction_key)
            else:
                print(f"⚠️ No jurisdiction found for Granicus URL: {source_url}")
                return self._extract_civic_data_standard(joined_sources, source_url)
        elif agent_type == "standard":
            return self._extract_civic_data_standard(joined_sources, source_url)
        else:
            # Fallback to standard for unknown agent types
            print(f"⚠️ Unknown agent type '{agent_type}', falling back to standard extraction")
            return self._extract_civic_data_standard(joined_sources, source_url)

    def _extract_civic_data_standard(self, joined_sources: str, source_url: str = "") -> dict:
        """Standard single-pass extraction (original method)"""
        try:
            # Create extraction prompt with clear JSON structure
            extraction_prompt = f"""
Extract civic engagement events from this city meeting content. Return ONLY a JSON object with this exact structure:

{{
  "meeting": {{
    "city": "string",
    "date": "string",
    "start_time": "string",
    "location": "string",
    "livestream": "string (URL for video stream)",
    "webinar": "string (Zoom/Webex meeting URL if different from livestream)",
    "meeting_id": "string (numeric meeting ID like '840 9897 7308', extract from meeting join instructions)",
    "phone": "string (dial-in number WITHOUT meeting ID)",
    "public_comment_email": "string",
    "public_comment_deadline": "string",
    "public_comment_rules": "string",
    "meeting_type": "string"
  }},
  "items": [
    {{
      "title": "string",
      "change": "string",
      "impact": "string",
      "how_to_participate": "string",
      "location": "string",
      "project_type": "housing|transportation|environment|budget|education|development|public_safety|community|elections|governance",
      "event_date": "string (ISO format with specific time if different from main meeting)",
      "event_time": "string (human readable time like '6:00 PM' if different from main meeting)",
      "is_actionable": "boolean (true if public input is explicitly solicited; false for presentations/updates/reports)"
    }}
  ],

Classify project_type using the same taxonomy as agenda integration:
- housing: affordable housing, zoning changes, residential development, inclusionary requirements
- transportation: transit, roads, bike lanes, parking, pedestrian infrastructure
- environment: parks, climate action, sustainability, natural resources, wildfire preparedness
- budget: appropriations, taxes, fees, financial policies, bonds, fiscal planning
- education: schools, libraries, youth programs, educational facilities
- development: commercial development, economic development, urban planning, mixed-use projects
- public_safety: police operations, emergency services, fire department operations
- community: social services, health programs, recreation, arts, accessibility
- elections: voting, ballot measures, electoral districts
- governance: procedural, administrative, appointments, intergovernmental agreements
  "recap_rows": [
    {{
      "topic": "string",
      "why_it_matters": "string", 
      "act_by": "string"
    }}
  ],
  "bottom_line": "string"
}}

COMPREHENSIVE EXTRACTION - SCAN ALL SECTIONS SYSTEMATICALLY:

🔴 PRIORITY 1 - PUBLIC HEARINGS (HIGHEST ENGAGEMENT):
   - Items explicitly marked "Public Hearing" - THESE ARE CRITICAL
   - Planning & Development Fee Schedule changes
   - Ordinance adoptions requiring public testimony
   - Zoning and development proposals

🔴 PRIORITY 2 - ACTION CALENDAR - NEW BUSINESS:
   - Police accountability and oversight items
   - Policy direction items requiring Council action
   - Administrative changes affecting services

📋 CONSENT CALENDAR ITEMS (EXTRACT ALL):
   - Grant funding approvals (behavioral health, workforce, community programs)
   - Service contracts (transportation, technology, accessibility)
   - Community facility improvements and public amenities
   - Public art and cultural initiatives

🕐 MEETING TIME EXTRACTION (CRITICAL):
   - Extract ACTUAL meeting date/time from agenda header or title
   - Look for patterns like "September 30, 2025" and "6:00 PM"
   - DO NOT use current timestamp - use the meeting's scheduled time
   - Include full venue address and hybrid access details

📞 VIRTUAL ACCESS EXTRACTION (CRITICAL):
   - Extract Zoom/Webex meeting IDs separately from phone numbers
   - Phone patterns: "(669) 444-9171" or "1-669-444-9171"
   - Meeting ID patterns: "ID: 840 9897 7308" or "Meeting ID: 84098977308" or "840 9897 7308#"
   - If phone string contains "ID:", parse the ID into "meeting_id" field
   - Store ONLY dial-in number in "phone" field (no IDs or passwords)
   - Examples:
     * "1 (669) 444-9171, ID: 840 9897 7308#" → phone: "1 (669) 444-9171", meeting_id: "840 9897 7308"
     * "Join by phone: (669) 444-9171, Meeting ID 840 9897 7308" → phone: "(669) 444-9171", meeting_id: "840 9897 7308"

🕐 INDIVIDUAL ITEM TIMES (IMPORTANT):
   - If different agenda items have DIFFERENT meeting times (e.g., Zoning at 10:00 AM, Planning at 6:00 PM)
   - Extract the specific time for each item in "event_date" (ISO format) and "event_time" (human readable)
   - If all items are at the same time, leave these fields empty and use the main meeting time
   - Look for patterns like "October 1, 2025, at 10:00 am", "6:00 pm", "7:00 pm" in item descriptions

🎯 ACTIONABILITY DETERMINATION (CRITICAL):
   Set "is_actionable": true ONLY if public input is explicitly solicited:

   ✅ ACTIONABLE (is_actionable: true):
   - Public Hearings (development, zoning, land use)
   - Items requiring Council/Commission VOTE or APPROVAL
   - Policy changes accepting public comment
   - Budget allocations open for input
   - Items with "Public Comment Period" notation

   ❌ NOT ACTIONABLE (is_actionable: false):
   - Staff presentations or updates
   - Informational reports (quarterly updates, status reports)
   - Briefings or educational sessions
   - Committee member announcements
   - Items marked "Information Only" or "Receive and File"
   - Advisory committee presentations without decision requested

   EXAMPLES:
   - "Presentation on Pedestrian Safety" → is_actionable: false (info only)
   - "Public Hearing: Zoning Change for 123 Main St" → is_actionable: true (requires decision)
   - "Update on Bikeshare Program" → is_actionable: false (status report)
   - "Approval of Grant Application" → is_actionable: true (requires vote)

3. PUBLIC ENGAGEMENT OPPORTUNITIES:
   - Planning and zoning hearings
   - Public comment periods (agenda and non-agenda items)
   - Community meetings and workshops
   - Advisory committee meetings

4. COUNCILMEMBER REFERRALS & COMMUNICATIONS:
   - Housing and reparations initiatives
   - Transportation and mobility programs
   - Community services and support programs
   - Neighborhood improvement projects
   - Resident communications and announcements

5. FINANCIAL & CONTRACT ITEMS:
   - Major contracts over $500k
   - Grant approvals (extract ALL grants, not just "major" ones)
   - Facility maintenance and improvements
   - Service delivery contracts

TARGET: Extract 8-15 items per meeting (not just 2-3 major items). Residents care about ALL services, grants, contracts, and community programs.

For public_comment_rules, extract any information about:
- Speaking time limits (e.g. "3 minutes per person", "2-minute limit")
- Public comment procedures (e.g. "Sign up required", "Written comments accepted")
- Special rules (e.g. "Comments on agenda items only")
- If no specific rules found, use "Check meeting agenda for public comment rules"

For meeting_type, identify what type of meeting this is based on the content:
- Look for explicit mentions like "City Council", "Planning Commission", "School Board", etc.
- Extract from the meeting title, page header, or URL
- Common types: "City Council", "Planning Commission", "School Board", "Parks Commission", "Transportation Authority", "Water Board", "Housing Authority"
- If unclear, use a descriptive name based on the content (e.g. "City Council Meeting", "Planning Meeting")

CRITICAL: Extract EVERYTHING that affects residents - grants, services, fees, community events, consent items. Don't filter by perceived importance.

Ignore only: roll call, routine minutes approval, ceremonial proclamations without community benefit
Use "Not specified" for missing information. Be factual and neutral.

SOURCE CONTENT:
{joined_sources[:40000]}
"""

            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a civic data extractor. Return only valid JSON matching the requested structure. Be neutral and factual."},
                    {"role": "user", "content": extraction_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=3500,
            )
            
            # Get the response content and parse JSON
            content = response.choices[0].message.content.strip()
            parsed_data = json.loads(content)

            print(f"✅ Extracted civic data: {len(parsed_data.get('items', []))} items found")

            # Future: Agent-based quality validation can be added here
            # For now, use data as-is from standard extraction

            return parsed_data
            
        except Exception as e:
            print(f"❌ Error extracting civic data: {e}")
            print(f"Response content preview: {content[:200] if 'content' in locals() else 'No content'}")
            # Return minimal structure if extraction fails
            return {
                "meeting": {"date": "Not specified"},
                "items": [],
                "recap_rows": [],
                "bottom_line": "Unable to extract civic engagement events."
            }

    def _extract_civic_data_legistar(self, joined_sources: str, source_url: str = "") -> dict:
        """Legistar-specific extraction using UnifiedDataSourceManager"""
        try:
            if not AGENT_REGISTRY_AVAILABLE:
                print("⚠️ Legistar extraction unavailable, falling back to standard")
                return self._extract_civic_data_standard(joined_sources, source_url)

            print(f"🏛️ Using Legistar-optimized extraction for {source_url}")

            # Try to get jurisdiction config for unified data source manager
            config = None
            for city_id, city_config in CITY_CONFIGS.items():
                for meeting_url in city_config['meeting_urls']:
                    try:
                        url_domain = source_url.split("//")[1].split("/")[0].lower()
                        config_domain = meeting_url.split("//")[1].split("/")[0].lower()
                        if url_domain == config_domain or config_domain in url_domain:
                            # Create DataSourceConfig for this jurisdiction
                            from civic_services.monitoring.unified_data_source_manager import DataSourceConfig
                            # Get Legistar client name from municipal registry (handles underscore → hyphen mapping)
                            legistar_client = MUNICIPAL_REGISTRY.get(city_id, {}).get('legistar_client', city_config['jurisdiction_id'])
                            config = DataSourceConfig(
                                jurisdiction_id=city_config['jurisdiction_id'],
                                jurisdiction_name=city_config['jurisdiction_id'].replace('-', ' ').title(),
                                timezone=city_config.get('timezone', 'America/Los_Angeles'),
                                legistar_available=True,
                                legistar_client_name=legistar_client
                            )
                            break
                    except:
                        continue
                if config:
                    break

            if not config:
                print("⚠️ No jurisdiction config found, falling back to HTML extraction")
                enhanced_sources = joined_sources + """

                LEGISTAR PLATFORM SPECIFIC INSTRUCTIONS:
                - Look for agenda items with precise dates and times
                - Extract meeting ID and agenda packet information
                - Identify public comment procedures specific to Legistar meetings
                - Look for "Action" vs "Information" items (Action items typically allow public comment)
                - Extract any public hearing notices and comment deadlines
                """
                return self._extract_civic_data_standard(enhanced_sources, source_url)

            # Initialize unified data source manager with config
            manager = UnifiedDataSourceManager(config)

            # Try unified data source approach
            try:
                events, source_info, metrics = manager.get_civic_opportunities()
                if events:
                    print(f"✅ Unified data source returned {len(events)} events from {source_info}")
                    # Convert UnifiedDataSourceManager format to civic_digest format
                    result_dict = {'events': events, 'source': source_info, 'metrics': metrics}
                    return self._convert_unified_data_to_civic_format(result_dict, source_url)
            except Exception as e:
                print(f"⚠️ Unified data source failed: {e}, falling back to HTML extraction")

            # Fallback to standard HTML extraction with Legistar-optimized prompts
            legistar_prompt_suffix = """

            LEGISTAR PLATFORM SPECIFIC INSTRUCTIONS:
            - Look for agenda items with precise dates and times
            - Extract meeting ID and agenda packet information
            - Identify public comment procedures specific to Legistar meetings
            - Look for "Action" vs "Information" items (Action items typically allow public comment)
            - Extract any public hearing notices and comment deadlines
            """

            # Modify the extraction to include Legistar-specific context
            enhanced_sources = joined_sources + legistar_prompt_suffix
            return self._extract_civic_data_standard(enhanced_sources, source_url)

        except Exception as e:
            print(f"❌ Legistar extraction failed: {e}")
            return self._extract_civic_data_standard(joined_sources, source_url)

    def _extract_civic_data_civicclerk(self, source_url: str, jurisdiction_key: str) -> dict:
        """CivicClerk API extraction - no HTML scraping needed

        Args:
            source_url: CivicClerk portal URL
            jurisdiction_key: CivicClerk subdomain (e.g., 'elcerritoca', 'milpitasca')
        """
        try:
            if not CIVICCLERK_AVAILABLE:
                print("⚠️ CivicClerk client unavailable, falling back to standard")
                return {"meetings": []}

            print(f"🏛️ Using CivicClerk API extraction for {jurisdiction_key}")

            # Create CivicClerk client directly with subdomain
            from civicclerk_client import CivicClerkClient
            client = CivicClerkClient(jurisdiction_key)
            if not client:
                print(f"⚠️ No CivicClerk client for {jurisdiction_key}")
                return {"meetings": []}

            # Get events from API
            events = client.get_events(days_ahead=90)
            if not events:
                print("⚠️ No events found from CivicClerk API")
                return {"meetings": []}

            print(f"✅ CivicClerk API returned {len(events)} events")

            # Get proper jurisdiction_id from URL (not subdomain)
            # This ensures we use the normalized jurisdiction_id from CITY_CONFIGS
            from civic_services.monitoring.automated_civic_refresh import get_jurisdiction_by_url
            jurisdiction_id = get_jurisdiction_by_url(source_url)

            # Convert to civic schema format
            from civic_services.core.municipal_registry import get_city_info
            # Try both hyphen and underscore variants for registry lookup
            city_info = get_city_info(jurisdiction_key) or get_city_info(jurisdiction_key.replace('-', '_'))

            # Use jurisdiction_id from config if available, otherwise construct from subdomain
            if not jurisdiction_id:
                jurisdiction_id = city_info.get('jurisdiction_id', f'city-{jurisdiction_key}') if city_info else f'city-{jurisdiction_key}'

            jurisdiction = {
                'id': jurisdiction_id,
                'name': jurisdiction_id.replace('city-', '').replace('-', ' ').title() if jurisdiction_id.startswith('city-') else jurisdiction_key.replace('-', ' ').replace('_', ' ').title(),
                'type': 'city',
                'website': city_info.get('url', '') if city_info else '',
                'meeting_calendar_url': city_info.get('portal_url', '') if city_info else ''
            }

            # Convert each event to meeting format (following CivicPlus pattern)
            result = {
                "meetings": [],
                "is_multi_meeting_calendar": True  # Signal multi-meeting processing
            }

            for event in events:
                # Convert CivicClerk event to civic schema
                contact_email = city_info.get('contact_email') if city_info else None
                civic_event = client.convert_to_civic_schema(event, jurisdiction, contact_email)

                # Create meeting wrapper with event_metadata (follows CivicPlus pattern)
                meeting_result = {
                    "meeting": {
                        "city": jurisdiction['name'],
                        "date": civic_event.get('when', ''),
                        "start_time": civic_event.get('when', ''),
                        "location": civic_event.get('location', ''),
                        "livestream": "",
                        "webinar": "",
                        "phone": "",
                        "public_comment_email": "",
                        "public_comment_deadline": "",
                        "public_comment_rules": civic_event.get('engagement_info', 'Check meeting agenda for public comment rules'),
                        "meeting_type": civic_event.get('meeting_type', 'public_meeting'),
                        "website": jurisdiction.get('website', ''),
                        "calendar_url": civic_event.get('source_url', source_url),
                        "jurisdiction_id": jurisdiction['id']
                    },
                    # Store civic_event metadata for opportunity creation
                    "event_metadata": civic_event,
                    # Empty items - CivicClerk events don't have agenda expansion by default
                    "items": [],
                    "recap_rows": [
                        {
                            "topic": civic_event.get('title', 'Civic Event'),
                            "why_it_matters": civic_event.get('impact_summary', 'Civic engagement opportunity')[:100] if civic_event.get('impact_summary') else 'Civic engagement opportunity',
                            "act_by": civic_event.get('when', 'See event date')
                        }
                    ],
                    "bottom_line": f"{civic_event.get('title', 'Civic event')}"
                }
                result["meetings"].append(meeting_result)

            print(f"📋 Converted {len(events)} CivicClerk events to {len(result['meetings'])} separate meeting events")
            return result

        except Exception as e:
            print(f"❌ CivicClerk extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return {"meetings": []}

    def _extract_civic_data_granicus(self, source_url: str, jurisdiction_key: str) -> dict:
        """Granicus ViewPublisher API extraction - structured HTML table parsing"""
        try:
            if not GRANICUS_AVAILABLE:
                print("⚠️ Granicus client unavailable, falling back to standard")
                return {"meetings": []}

            print(f"🏛️ Using Granicus ViewPublisher extraction for {jurisdiction_key}")

            # Get Granicus configuration from city config
            from civic_services.monitoring.automated_civic_refresh import CITY_CONFIGS
            city_config = CITY_CONFIGS.get(jurisdiction_key.replace('-', '_'))
            if not city_config or 'granicus_config' not in city_config:
                print(f"⚠️ No Granicus config for {jurisdiction_key}")
                return {"meetings": []}

            granicus_config = city_config['granicus_config']

            # Create Granicus client
            client = create_granicus_client(
                granicus_config['subdomain'],
                granicus_config['view_id']
            )

            # Get meetings from ViewPublisher
            # Use 30-day lookback to capture meetings from cities that publish sporadically
            meetings = client.get_meetings(days_future=90, days_past=30)
            if not meetings:
                print("⚠️ No meetings found from Granicus ViewPublisher")
                return {"meetings": []}

            print(f"✅ Granicus ViewPublisher returned {len(meetings)} meetings")

            # Convert to civic schema format
            from civic_services.core.municipal_registry import get_city_info
            city_info = get_city_info(jurisdiction_key) or get_city_info(jurisdiction_key.replace('-', '_'))
            jurisdiction = {
                'id': city_config.get('jurisdiction_id', f'city-{jurisdiction_key}'),
                'name': jurisdiction_key.replace('-', ' ').replace('_', ' ').title(),
                'type': 'city',
                'website': city_info.get('url', '') if city_info else '',
                'meeting_calendar_url': source_url
            }

            # Convert each meeting to schema format (following CivicClerk pattern)
            result = {
                "meetings": [],
                "is_multi_meeting_calendar": True  # Signal multi-meeting processing
            }

            for meeting in meetings:
                # Create civic event from Granicus meeting data
                civic_event = {
                    'id': f"granicus_{meeting['title'].lower().replace(' ', '_')}_{meeting['datetime'][:10]}",
                    'title': meeting['title'],
                    'description': f"{meeting['title']} on {meeting['datetime'][:10]}",
                    'when': meeting['datetime'],
                    'location': '',  # Granicus doesn't provide location in table
                    'engagement_info': 'Check agenda for participation details',
                    'impact_summary': f"Civic meeting: {meeting['title']}",
                    'source_url': meeting.get('agenda_url', meeting.get('source_url', source_url)),
                    'meeting_type': 'public_meeting',
                    'jurisdiction': jurisdiction,
                    'project_type': 'governance',
                    # Add Granicus-specific metadata for agenda integration
                    '_granicus_metadata': {
                        'agenda_url': meeting.get('agenda_url'),
                        'packet_url': meeting.get('packet_url'),
                        'platform': 'granicus',
                        'subdomain': granicus_config['subdomain'],
                        'view_id': granicus_config['view_id']
                    },
                    # Add agenda_expansion structure for PDF integration
                    # Note: Prefer agenda_url over packet_url (packets can be very large)
                    'agenda_expansion': {
                        'parsed': False,
                        'actionable_items': [],
                        'raw_agenda_url': meeting.get('agenda_url') or meeting.get('packet_url'),
                        'parsing_method': 'granicus_html_pending'
                    }
                }

                # Create meeting wrapper (follows CivicClerk/CivicPlus pattern)
                meeting_result = {
                    "meeting": {
                        "city": jurisdiction['name'],
                        "date": meeting['datetime'],
                        "start_time": meeting['datetime'],
                        "location": '',
                        "livestream": "",
                        "webinar": "",
                        "phone": "",
                        "public_comment_email": city_config.get('contact_email', ''),
                        "public_comment_deadline": "",
                        "public_comment_rules": "Check meeting agenda for public comment rules",
                        "meeting_type": "public_meeting",
                        "website": jurisdiction.get('website', ''),
                        "calendar_url": source_url,
                        "jurisdiction_id": jurisdiction['id']
                    },
                    # Store civic_event metadata for opportunity creation
                    "event_metadata": civic_event,
                    # Empty items - Granicus events need agenda PDF parsing
                    "items": [],
                    "recap_rows": [
                        {
                            "topic": meeting['title'],
                            "why_it_matters": f"Civic meeting: {meeting['title']}",
                            "act_by": meeting['datetime']
                        }
                    ],
                    "bottom_line": meeting['title']
                }
                result["meetings"].append(meeting_result)

            print(f"📋 Converted {len(meetings)} Granicus meetings to {len(result['meetings'])} separate events")
            return result

        except Exception as e:
            print(f"❌ Granicus extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return {"meetings": []}

    def _extract_civic_data_berkeley(self, joined_sources: str, source_url: str = "") -> dict:
        """
        Berkeley event-level extraction for consistency with other municipal parsers

        NOTE: Agenda-specific parsing logic preserved in berkeley_agenda_parser_legacy.py
        for future downstream development when agenda-item expansion is implemented.
        """
        try:
            print(f"🌉 Using Berkeley event-level extraction for {source_url}")

            # STEP 1: Use BeautifulSoup to extract agenda URLs (100% accurate matching)
            # This prevents LLM from assigning wrong PDFs to meetings
            agenda_url_map = {}
            try:
                from bs4 import BeautifulSoup
                import requests

                # Fetch fresh HTML directly (joined_sources may be truncated)
                response = requests.get(source_url, timeout=30)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find all event accordion items
                event_links = soup.find_all('a', class_='accordion-title')

                for event_link in event_links:
                    event_title = event_link.get_text().strip()

                    # Find the accordion container (parent li or div)
                    accordion_item = event_link.find_parent('li') or event_link.find_parent('div')

                    if accordion_item:
                        # Find PDF links within this specific accordion item
                        pdf_links = accordion_item.find_all('a', href=lambda x: x and '.pdf' in x.lower())

                        if pdf_links:
                            # Use first PDF found (typically the agenda)
                            pdf_url = pdf_links[0]['href']

                            # Normalize to absolute URL
                            if not pdf_url.startswith('http'):
                                pdf_url = f"https://berkeleyca.gov{pdf_url}" if pdf_url.startswith('/') else ''

                            # Store with normalized title for matching
                            normalized_title = event_title.split('\n')[0].strip()  # Remove time suffix
                            agenda_url_map[normalized_title] = pdf_url

                print(f"📋 BeautifulSoup extracted {len(agenda_url_map)} agenda URLs")

            except Exception as bs_error:
                print(f"⚠️ BeautifulSoup extraction failed, will use LLM for URLs: {bs_error}")
                agenda_url_map = {}

            # Extract individual meeting events from Berkeley calendar (consistent with other parsers)
            events_prompt = f"""
            Extract civic meeting EVENTS from this Berkeley government calendar page.
            Focus on extracting individual meetings as events, not agenda items within meetings.

            Return JSON array of meeting events:
            [
              {{
                "title": "Meeting Name (e.g. 'City Council Meeting', 'Planning Commission Meeting')",
                "change": "Brief description of the meeting purpose",
                "impact": "Why this meeting matters to residents",
                "how_to_participate": "How residents can participate (attend, comment, etc.)",
                "location": "Full meeting location",
                "project_type": "community|housing|transportation|governance|environment",
                "meeting_type": "city_council|planning_commission|board|commission",
                "event_date": "REQUIRED: ISO 8601 datetime format ONLY - example: 2025-10-14T18:00:00",
                "event_time": "Time in readable format (e.g., '6:00 PM')",
                "event_category": "civic_meeting",
                "agenda_url": "Full URL to agenda PDF if available (look for PDF links near the event)"
              }}
            ]

            CRITICAL DATETIME REQUIREMENTS:
            - event_date MUST be in ISO 8601 format: "YYYY-MM-DDTHH:MM:SS"
            - Example valid format: "2025-10-14T18:00:00" for October 14, 2025 at 6:00 PM
            - Include both date AND time in the event_date field
            - Do NOT use relative dates like "tomorrow" or "next week"
            - Do NOT output current date if meeting date is unknown

            AGENDA PDF EXTRACTION (CRITICAL - MATCH PDFs TO CORRECT MEETINGS):
            - Look for PDF links IMMEDIATELY FOLLOWING each specific meeting event listing
            - PDFs typically show file size in parentheses (e.g., "(211.05 KB)")
            - PDFs are usually in "/sites/default/files/legislative-body-meeting-agendas/" directory
            - IMPORTANT: Match each PDF to its SPECIFIC meeting - do NOT reuse the same PDF for multiple meetings
            - Example: "Planning Commission Meeting" → look for PDF link directly after this event, NOT after other events
            - Convert relative URLs to absolute: prepend "https://berkeleyca.gov"
            - If no agenda PDF found for a specific meeting, set agenda_url to empty string ""
            - Double-check: each meeting should have a UNIQUE agenda_url (not the same URL as other meetings)

            BERKELEY EVENT EXTRACTION PRIORITIES:
            - Extract meeting events, not individual agenda items
            - Focus on meetings where public can participate
            - Include City Council, Planning Commission, Police Accountability Board meetings
            - Capture meeting date, time, location accurately from the page content
            - Generate meaningful descriptions of meeting purpose
            - Extract agenda PDF URL if available near the meeting event
            - If meeting date cannot be determined, skip that event

            Content: {self._truncate_safely(joined_sources, 35000)}
            """

            events_response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": events_prompt}],
                temperature=0.1
            )

            response_content = events_response.choices[0].message.content.strip()
            print(f"🔍 Berkeley response preview: {response_content[:200]}...")

            # Clean response to extract JSON if wrapped in markdown
            if response_content.startswith("```json"):
                response_content = response_content.replace("```json", "").replace("```", "").strip()
            elif response_content.startswith("```"):
                response_content = response_content.replace("```", "").strip()

            meeting_events = json.loads(response_content)

            # Validate and normalize event datetimes
            validated_events = []
            for event in meeting_events:
                event_date_str = event.get('event_date', '')
                if not event_date_str:
                    logging.warning(f"Berkeley event missing event_date: {event.get('title', 'Unknown')}")
                    continue

                # Parse and validate datetime
                try:
                    from dateutil import parser as date_parser
                    # Try parsing the date
                    if 'T' in event_date_str:
                        # ISO format
                        event_datetime = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
                    else:
                        # Try flexible parsing
                        event_datetime = date_parser.parse(event_date_str)

                    # Apply timezone if missing
                    if event_datetime.tzinfo is None:
                        import pytz
                        tz = pytz.timezone('America/Los_Angeles')
                        event_datetime = tz.localize(event_datetime)

                    # Sanity check the datetime
                    if not self._validate_datetime_sanity(event_datetime, event.get('title', 'Unknown'), "Berkeley"):
                        continue

                    # Update event with normalized datetime
                    event['event_date'] = event_datetime.isoformat()
                    validated_events.append(event)

                except Exception as parse_error:
                    logging.warning(f"Berkeley: Could not parse event_date '{event_date_str}' for '{event.get('title', 'Unknown')}': {parse_error}")
                    continue

            meeting_events = validated_events
            print(f"✅ Validated {len(meeting_events)} Berkeley events with correct datetimes")

            # CORRECT ARCHITECTURE: Return multiple meeting results, one per calendar event
            # This allows each event to become its own opportunity with proper opportunity_id
            # Pattern matches CivicPlus parser (lines 1441-1483)
            result = {
                "is_multi_meeting_calendar": True,  # Signal to caller that this needs special handling
                "meetings": []  # List of individual meeting results
            }

            # Convert each calendar event to a separate meeting result
            for idx, event in enumerate(meeting_events):
                # STEP 2: Override LLM agenda URL with BeautifulSoup-extracted URL (100% accurate)
                meeting_title = event.get('title', '')

                # Try to match with BeautifulSoup-extracted URLs
                agenda_url = None
                if agenda_url_map:
                    # Try exact match first
                    if meeting_title in agenda_url_map:
                        agenda_url = agenda_url_map[meeting_title]
                    else:
                        # Try fuzzy match (meeting title might have slight variations)
                        for bs_title, bs_url in agenda_url_map.items():
                            # Check if titles substantially overlap
                            if meeting_title.lower() in bs_title.lower() or bs_title.lower() in meeting_title.lower():
                                agenda_url = bs_url
                                break

                # Fallback to LLM-extracted URL if BeautifulSoup didn't find it
                if not agenda_url:
                    agenda_url = event.get('agenda_url', '')
                    if agenda_url and not agenda_url.startswith('http'):
                        # Convert relative URL to absolute
                        agenda_url = f"https://berkeleyca.gov{agenda_url}" if agenda_url.startswith('/') else ''

                meeting_result = {
                    "meeting": {
                        "city": "Berkeley",
                        "date": event.get('event_date', ''),
                        "start_time": event.get('event_date', ''),
                        "_event_metadata_when": event.get('event_date', ''),  # Store ISO datetime for schema adapter
                        "location": event.get('location', 'Berkeley City Hall'),
                        "livestream": "",
                        "webinar": "",
                        "phone": "",
                        "public_comment_email": "council@cityofberkeley.info",
                        "public_comment_deadline": "",
                        "public_comment_rules": event.get('how_to_participate', 'Check meeting agenda for public comment rules'),
                        "meeting_type": event.get('meeting_type', 'public_meeting'),
                        "website": "https://berkeleyca.gov",
                        "calendar_url": source_url,
                        "agenda_url": agenda_url,  # Store agenda URL for agenda integration
                        "jurisdiction_id": "city-berkeley"
                    },
                    # Store event metadata for opportunity creation, but NOT as agenda items
                    "event_metadata": event,
                    # Empty items - will be populated by agenda integration if agenda_url exists
                    "items": [],
                    "recap_rows": [
                        {
                            "topic": event.get('title', 'Civic Event'),
                            "why_it_matters": event.get('impact', 'Civic engagement opportunity')[:100],
                            "act_by": event.get('event_date', 'See event date')
                        }
                    ],
                    "bottom_line": f"{event.get('title', 'Civic meeting')}"
                }
                result["meetings"].append(meeting_result)

            print(f"📋 Converted {len(meeting_events)} calendar events to {len(result['meetings'])} separate meeting events")
            return result

        except Exception as e:
            print(f"❌ Berkeley multi-pass extraction failed: {e}, falling back to standard")
            return self._extract_civic_data_standard(joined_sources, source_url)

    def _extract_civic_data_san_rafael(self, joined_sources: str, source_url: str = "") -> dict:
        """
        San Rafael table-based extraction using BeautifulSoup for 100% URL accuracy
        """
        try:
            print(f"🏛️ Using San Rafael table-based extraction for {source_url}")

            # STEP 1: Use BeautifulSoup to extract meeting URLs from table structure
            meeting_urls = []
            try:
                from bs4 import BeautifulSoup
                import requests
                import re

                # Fetch fresh HTML directly (joined_sources may be truncated)
                response = requests.get(source_url, timeout=30)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find ALL meetings tables (city-council-meetings page has 8 tables)
                tables = soup.find_all('table', class_='table-striped')
                for table in tables:
                    tbody = table.find('tbody')
                    if tbody:
                        rows = tbody.find_all('tr')

                        for row in rows:
                            cells = row.find_all('td')
                            if len(cells) < 1:
                                continue

                            # First cell contains the meeting link
                            meeting_link = cells[0].find('a', href=re.compile(r'/meetings/'))
                            if meeting_link and meeting_link.get('href'):
                                url = meeting_link['href']

                                # Normalize to absolute URL
                                if not url.startswith('http'):
                                    url = f"https://www.cityofsanrafael.org{url}" if url.startswith('/') else f"https://www.cityofsanrafael.org/meetings/{url}"

                                # Strip anchor fragments
                                url = url.split('#')[0]

                                if url not in meeting_urls:
                                    meeting_urls.append(url)

                print(f"📋 BeautifulSoup extracted {len(meeting_urls)} meeting URLs from table")

            except Exception as bs_error:
                print(f"⚠️ BeautifulSoup extraction failed, will use standard extraction: {bs_error}")
                return self._extract_civic_data_standard(joined_sources, source_url)

            # If no meetings found, fall back to standard
            if not meeting_urls:
                print(f"⚠️ No meeting URLs found via BeautifulSoup, falling back to standard")
                return self._extract_civic_data_standard(joined_sources, source_url)

            # STEP 2: For each meeting URL, extract event details using AI
            result = {
                "meetings": [],
                "city": "San Rafael",
                "state": "CA"
            }

            for meeting_url in meeting_urls:
                try:
                    # Scrape individual meeting page
                    meeting_content = self._scrape_meeting_sources(meeting_url)

                    # Extract event details
                    event_prompt = f"""
Extract meeting event details from this San Rafael city meeting page.

Return ONLY a JSON object with this structure:
{{
  "title": "Meeting Name",
  "description": "Brief description of the meeting purpose",
  "location": "Full meeting location",
  "event_date": "ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS)",
  "meeting_type": "city_council|planning_commission|zoning_administrator|commission|board",
  "project_type": "housing|transportation|environment|budget|education|development|public_safety|community|elections|governance",
  "how_to_participate": "Instructions for public participation",
  "email": "Contact email address",
  "phone": "Contact phone number"
}}

Classify project_type using the same taxonomy as agenda integration:
- housing: affordable housing, zoning changes, residential development, inclusionary requirements
- transportation: transit, roads, bike lanes, parking, pedestrian infrastructure
- environment: parks, climate action, sustainability, natural resources, wildfire preparedness
- budget: appropriations, taxes, fees, financial policies, bonds, fiscal planning
- education: schools, libraries, youth programs, educational facilities
- development: commercial development, economic development, urban planning, mixed-use projects
- public_safety: police operations, emergency services, fire department operations
- community: social services, health programs, recreation, arts, accessibility
- elections: voting, ballot measures, electoral districts
- governance: procedural, administrative, appointments, intergovernmental agreements

Meeting content:
{self._truncate_safely(meeting_content, 35000)}
"""

                    response = openai.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": event_prompt}],
                        temperature=0.0,
                        max_tokens=1000
                    )

                    ai_response = response.choices[0].message.content.strip()

                    # Parse JSON response
                    if ai_response.startswith('{') and ai_response.endswith('}'):
                        event = json.loads(ai_response)
                    else:
                        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                        if json_match:
                            event = json.loads(json_match.group())
                        else:
                            print(f"⚠️ Could not parse event data for {meeting_url}")
                            continue

                    # Build meeting result
                    meeting_result = {
                        "meeting": {
                            "city": "San Rafael",
                            "date": event.get('event_date', ''),
                            "start_time": event.get('event_date', ''),
                            "_event_metadata_when": event.get('event_date', ''),
                            "location": event.get('location', 'City Hall, 1400 Fifth Ave, San Rafael, CA 94901'),
                            "livestream": "",
                            "webinar": "",
                            "phone": event.get('phone', ''),
                            "public_comment_email": event.get('email', 'planning@cityofsanrafael.org'),
                            "public_comment_deadline": "",
                            "public_comment_rules": event.get('how_to_participate', 'Check meeting agenda for public comment rules'),
                            "meeting_type": event.get('meeting_type', 'public_meeting'),
                            "website": "https://www.cityofsanrafael.org",
                            "calendar_url": source_url,
                            "agenda_url": meeting_url,
                            "jurisdiction_id": "city-san-rafael"
                        },
                        "event_metadata": event,
                        "items": [],
                        "recap_rows": [
                            {
                                "topic": event.get('title', 'Civic Event'),
                                "why_it_matters": event.get('description', 'Civic engagement opportunity')[:100],
                                "act_by": event.get('event_date', 'See event date')
                            }
                        ],
                        "bottom_line": f"{event.get('title', 'Civic meeting')}"
                    }
                    result["meetings"].append(meeting_result)

                except Exception as meeting_error:
                    print(f"⚠️ Failed to extract event from {meeting_url}: {meeting_error}")
                    continue

            print(f"📋 Extracted {len(result['meetings'])} meeting events via San Rafael parser")
            return result

        except Exception as e:
            print(f"❌ San Rafael extraction failed: {e}, falling back to standard")
            return self._extract_civic_data_standard(joined_sources, source_url)

    def _extract_civic_data_civicplus(self, joined_sources: str, source_url: str = "") -> dict:
        """CivicPlus-specific extraction with proper calendar event parsing"""
        try:
            print(f"🏛️ Using CivicPlus calendar parser for {source_url}")

            # Check if this is a calendar page vs individual meeting page
            if "Calendar.aspx" in source_url and "EID=" not in source_url:
                return self._parse_civicplus_calendar(joined_sources, source_url)
            else:
                # Individual meeting page - use enhanced standard extraction
                return self._extract_civic_data_civicplus_meeting(joined_sources, source_url)

        except Exception as e:
            print(f"❌ CivicPlus extraction failed: {e}, falling back to standard")
            return self._extract_civic_data_standard(joined_sources, source_url)

    def _parse_civicplus_calendar(self, html_content: str, source_url: str) -> dict:
        """Parse CivicPlus calendar page to extract individual events with correct dates"""
        try:
            from bs4 import BeautifulSoup
            import re
            import requests
            from urllib.parse import urlparse, parse_qs

            print(f"📅 Parsing CivicPlus calendar page for structured events")

            # For calendar pages, we need raw HTML, not extracted text
            # Fetch current month and next month to capture comprehensive events

            current_date = datetime.now()
            current_month = current_date.month
            current_year = current_date.year

            # Calculate next month
            next_month = current_month + 1
            next_year = current_year
            if next_month > 12:
                next_month = 1
                next_year += 1

            # Generate URLs for current and next month
            parsed_url = urlparse(source_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

            month_urls = [
                f"{base_url}?month={current_month}&year={current_year}",
                f"{base_url}?month={next_month}&year={next_year}"
            ]

            print(f"📄 Fetching calendar for {current_month}/{current_year} and {next_month}/{next_year}")

            all_events = []
            for month_url in month_urls:
                try:
                    response = self.session.get(month_url, timeout=30)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.content, 'html.parser')

                    # Find all schema.org Event items for this month
                    month_events = soup.find_all(attrs={'itemscope': True, 'itemtype': 'http://schema.org/Event'})
                    all_events.extend(month_events)
                    print(f"🔍 Found {len(month_events)} events in {month_url.split('?')[1]}")

                except Exception as e:
                    print(f"⚠️ Error fetching {month_url}: {e}")
                    continue

            events = all_events
            print(f"🔍 Total events found across months: {len(events)}")

            # Extract civic events from events
            civic_items = []
            valid_events = []

            for event in events:
                try:
                    # Extract structured data
                    name_elem = event.find('span', {'itemprop': 'name'})
                    date_elem = event.find('span', {'itemprop': 'startDate'})
                    desc_elem = event.find('p', {'itemprop': 'description'}) or event.find('[itemprop="description"]')
                    location_elem = event.find('span', {'itemprop': 'name'}) # Location name within location scope

                    if not name_elem or not date_elem:
                        continue

                    event_name = name_elem.get_text().strip()
                    # Extract date from hidden startDate element
                    event_date = date_elem.get_text().strip()

                    # Extract description for relevancy check
                    description = ""
                    if desc_elem:
                        description = desc_elem.get_text().strip()

                    # Skip past events and non-civic events (AI-powered relevancy check)
                    if not event_date or not self._is_civic_relevant_event(event_name, description):
                        continue

                    # Parse datetime with flexible parsing
                    event_datetime = None
                    try:
                        if 'T' in event_date:
                            # ISO format: 2025-09-07T10:00:00
                            event_datetime = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                        else:
                            # Try flexible parsing for formats like "September 30, 2025", "09/30/2025 6:00 PM", etc.
                            from dateutil import parser as date_parser
                            event_datetime = date_parser.parse(event_date)
                            # Apply timezone if missing
                            if event_datetime.tzinfo is None:
                                import pytz
                                tz = pytz.timezone('America/Los_Angeles')
                                event_datetime = tz.localize(event_datetime)
                    except Exception as parse_error:
                        logging.warning(f"Could not parse CivicPlus event date '{event_date}' for '{event_name}': {parse_error}")
                        continue

                    # Sanity check: reject dates that don't make sense
                    if not self._validate_datetime_sanity(event_datetime, event_name, "CivicPlus"):
                        continue

                    # Extract location
                    location = "El Cerrito City Hall"  # Default
                    location_container = event.find('span', {'itemprop': 'location'})
                    if location_container:
                        address_elem = location_container.find('span', {'itemprop': 'streetAddress'})
                        name_elem_loc = location_container.find('span', {'itemprop': 'name'}) or location_container.find('div', class_='name')
                        if name_elem_loc:
                            location = name_elem_loc.get_text().strip()
                        if address_elem:
                            address = address_elem.get_text().strip()
                            if address:
                                location = f"{location}, {address}"

                    # Extract description
                    description = "Civic engagement opportunity"
                    if desc_elem:
                        description = desc_elem.get_text().strip()[:200] + "..." if len(desc_elem.get_text()) > 200 else desc_elem.get_text().strip()

                    # Determine engagement type and impact
                    engagement_type, impact = self._categorize_civic_event(event_name, description)

                    # Determine meeting type
                    meeting_type = self._detect_meeting_type(event_name, description)

                    civic_item = {
                        "title": event_name,
                        "change": description,
                        "impact": impact,
                        "how_to_participate": self._get_participation_guidance(event_name),
                        "location": location,
                        "project_type": self._get_project_type(event_name),
                        "meeting_type": meeting_type,  # Add accurate meeting type
                        "event_date": event_datetime.isoformat(),  # Store the actual parsed date
                        "event_time": event_datetime.strftime("%I:%M %p").lstrip('0'),
                        "event_category": engagement_type
                    }

                    civic_items.append(civic_item)
                    valid_events.append({
                        'name': event_name,
                        'date': event_datetime.isoformat(),
                        'location': location
                    })

                except Exception as e:
                    print(f"⚠️ Error parsing event: {e}")
                    continue

            print(f"✅ Successfully parsed {len(civic_items)} civic events with correct dates")

            # Build result in expected format
            if not civic_items:
                return self._get_empty_civic_data()

            # Get city info from existing config
            from civic_services.monitoring.automated_civic_refresh import get_jurisdiction_by_url, CITY_CONFIGS
            from urllib.parse import urlparse

            jurisdiction_id = get_jurisdiction_by_url(source_url)
            city_name = jurisdiction_id.replace('city-', '').replace('-', ' ').title() if jurisdiction_id != 'unknown' else 'Unknown City'

            # Extract base website URL
            parsed_url = urlparse(source_url)
            base_website = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # CORRECT ARCHITECTURE: Return multiple meeting results, one per calendar event
            # This allows each event to become its own opportunity with proper opportunity_id
            result = {
                "is_multi_meeting_calendar": True,  # Signal to caller that this needs special handling
                "meetings": []  # List of individual meeting results
            }

            # Convert each calendar event to a separate meeting result
            for idx, civic_item in enumerate(civic_items):
                meeting_result = {
                    "meeting": {
                        "city": city_name,
                        "date": civic_item.get('event_date', ''),
                        "start_time": civic_item.get('event_date', ''),
                        "location": civic_item.get('location', f'{city_name} City Hall'),
                        "livestream": "",
                        "webinar": "",
                        "phone": "",
                        "public_comment_email": "",
                        "public_comment_deadline": "",
                        "public_comment_rules": civic_item.get('how_to_participate', 'Check meeting agenda for public comment rules'),
                        "meeting_type": civic_item.get('meeting_type', 'public_meeting'),
                        "website": base_website,
                        "calendar_url": source_url,
                        "jurisdiction_id": jurisdiction_id
                    },
                    # Store civic_item metadata for opportunity creation, but NOT as agenda items
                    "event_metadata": civic_item,
                    # Empty items - calendar events don't have agenda expansion by default
                    "items": [],
                    "recap_rows": [
                        {
                            "topic": civic_item.get('title', 'Civic Event'),
                            "why_it_matters": civic_item.get('impact', 'Civic engagement opportunity')[:100],
                            "act_by": civic_item.get('event_date', 'See event date')
                        }
                    ],
                    "bottom_line": f"{civic_item.get('title', 'Civic event')}"
                }
                result["meetings"].append(meeting_result)

            print(f"📋 Converted {len(civic_items)} calendar events to {len(result['meetings'])} separate meeting events")
            return result

        except Exception as e:
            print(f"❌ Calendar parsing failed: {e}, falling back to standard extraction")
            return self._extract_civic_data_standard(html_content, source_url)

    def _validate_datetime_sanity(self, dt: datetime, event_name: str = "", source: str = "") -> bool:
        """
        Validate that a datetime makes sense for a civic meeting

        Returns True if datetime is valid, False if suspicious
        Logs warnings for rejected dates
        """
        if dt is None:
            return False

        try:
            # Get current time in the same timezone as the event
            now = datetime.now(dt.tzinfo if dt.tzinfo else None)
            days_until = (dt - now).days

            # Reject past dates (more than 2 days old - allows for timezone issues and recently published events)
            if days_until < -2:
                logging.warning(f"Rejecting past event ({source}): '{event_name}' on {dt.isoformat()} ({days_until} days ago)")
                return False

            # Reject dates more than 365 days in future (likely parsing error)
            if days_until > 365:
                logging.warning(f"Rejecting far-future event ({source}): '{event_name}' on {dt.isoformat()} ({days_until} days away)")
                return False

            # Valid date range
            return True

        except Exception as e:
            logging.error(f"Error validating datetime for '{event_name}': {e}")
            return False

    def _is_civic_relevant_event(self, event_name: str, description: str = "") -> bool:
        """Use AI to determine if an event is relevant for civic engagement"""
        try:
            relevancy_prompt = f"""
Determine if this event is relevant for civic engagement and community participation.

Event: "{event_name}"
Description: "{description}"

INCLUDE events that are:
- Government meetings (city council, planning commission, boards, committees)
- Public hearings and workshops
- Community volunteer events
- Public service events (blood drives, cleanup days)
- Civic education events
- Public comment events

EXCLUDE events that are:
- Canceled or postponed events
- Private recreational activities (swim practice, fitness classes)
- Holiday closures and facility maintenance
- Private tours without civic decision-making
- Entertainment events without civic purpose

Respond with only "RELEVANT" or "NOT_RELEVANT"
"""

            response = openai.chat.completions.create(
                model="gpt-4o-mini",  # Use fast, cost-effective model
                messages=[{"role": "user", "content": relevancy_prompt}],
                temperature=0.0,  # Deterministic output
                max_tokens=10
            )

            result = response.choices[0].message.content.strip()
            return result == "RELEVANT"

        except Exception as e:
            print(f"⚠️ AI relevancy check failed for '{event_name}': {e}")
            # Fallback to basic keyword check
            civic_keywords = ['meeting', 'commission', 'council', 'volunteer', 'hearing']
            return any(keyword in event_name.lower() for keyword in civic_keywords)

    def _detect_meeting_type(self, event_name: str, description: str) -> str:
        """Use AI to accurately detect the type of meeting"""
        try:
            detection_prompt = f"""
Determine the specific meeting type for this civic event.

Event: "{event_name}"
Description: "{description}"

Choose the most accurate meeting type from these options:
- city_council (City Council meetings)
- planning_commission (Planning Commission meetings)
- school_board (School District meetings)
- commission (Other government commissions: Human Relations, Environmental Quality, etc.)
- committee (Government committees: Safety, Economic Development, etc.)
- board (Government boards: Design Review, Financial Advisory, etc.)
- public_hearing (Formal public hearings)
- community_meeting (Community events, volunteer activities)
- workshop (Educational or informational sessions)

Respond with only the meeting type (e.g., "commission" or "committee")
"""

            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": detection_prompt}],
                temperature=0.0,
                max_tokens=20
            )

            meeting_type = response.choices[0].message.content.strip()

            # Validate response is in expected format
            valid_types = ['city_council', 'planning_commission', 'school_board', 'commission',
                          'committee', 'board', 'public_hearing', 'community_meeting', 'workshop']

            if meeting_type in valid_types:
                return meeting_type
            else:
                return "commission"  # Safe default

        except Exception as e:
            print(f"⚠️ AI meeting type detection failed for '{event_name}': {e}")
            # Fallback based on event name
            event_lower = event_name.lower()
            if 'city council' in event_lower:
                return 'city_council'
            elif 'planning commission' in event_lower:
                return 'planning_commission'
            elif 'commission' in event_lower:
                return 'commission'
            elif 'committee' in event_lower:
                return 'committee'
            elif 'board' in event_lower:
                return 'board'
            else:
                return 'community_meeting'

    def _categorize_civic_event(self, event_name: str, description: str) -> tuple:
        """Categorize event and generate impact statement"""
        event_lower = event_name.lower()

        if any(word in event_lower for word in ['volunteer', 'cleanup', 'park']):
            return ("community_action", "Direct community involvement and environmental improvement")
        elif any(word in event_lower for word in ['meeting', 'commission', 'board', 'council']):
            return ("public_meeting", "Event to influence local government decisions")
        elif any(word in event_lower for word in ['tour', 'open house', 'education']):
            return ("educational", "Increased public awareness and civic knowledge")
        elif any(word in event_lower for word in ['blood drive', 'health', 'service']):
            return ("community_service", "Support for local health and emergency services")
        else:
            return ("general", "Community engagement and civic participation")

    def _get_participation_guidance(self, event_name: str) -> str:
        """Get specific participation guidance based on event type"""
        event_lower = event_name.lower()

        if 'volunteer' in event_lower:
            return "Complete a Volunteer Registration Form before working"
        elif 'tour' in event_lower:
            return "RSVP by email or phone is required"
        elif 'blood drive' in event_lower:
            return "Use Sponsor Code 'ELCERRITO'"
        elif 'cleanup' in event_lower:
            return "Participants should wear long pants and sturdy closed-toed shoes"
        elif any(word in event_lower for word in ['meeting', 'commission', 'board']):
            return "Submit public comment, attend meeting, or contact representatives"
        else:
            return "Contact the city for participation details"

    def _get_project_type(self, event_name: str) -> str:
        """Determine project type based on event name"""
        event_lower = event_name.lower()

        if any(word in event_lower for word in ['park', 'environment', 'cleanup', 'green', 'climate']):
            return "environment"
        elif any(word in event_lower for word in ['housing', 'zoning', 'residential']):
            return "housing"
        elif any(word in event_lower for word in ['planning', 'development', 'design', 'commercial']):
            return "development"
        elif any(word in event_lower for word in ['budget', 'finance', 'tax']):
            return "budget"
        elif any(word in event_lower for word in ['school', 'education', 'library']):
            return "education"
        elif any(word in event_lower for word in ['transit', 'transportation', 'road', 'bike']):
            return "transportation"
        elif any(word in event_lower for word in ['police', 'fire', 'emergency', 'safety']):
            return "public_safety"
        elif any(word in event_lower for word in ['election', 'voting', 'ballot']):
            return "elections"
        elif any(word in event_lower for word in ['community', 'volunteer', 'health', 'social']):
            return "community"
        else:
            return "governance"

    def _extract_civic_data_civicplus_meeting(self, joined_sources: str, source_url: str) -> dict:
        """Extract from individual CivicPlus meeting page with enhanced prompts"""
        civicplus_prompt_suffix = """

        CIVICPLUS INDIVIDUAL MEETING PAGE INSTRUCTIONS:
        - This is a specific meeting page, not a calendar overview
        - Extract actual agenda items and topics for discussion
        - Look for structured meeting content and public comment events
        - Extract specific project details, policy changes, and community impacts
        - Identify the exact meeting type (City Council, Planning Commission, etc.)
        - Extract meeting logistics (time, location, hybrid access info)
        """

        enhanced_sources = joined_sources + civicplus_prompt_suffix
        return self._extract_civic_data_standard(enhanced_sources, source_url)

    def _convert_unified_data_to_civic_format(self, unified_result: dict, source_url: str) -> dict:
        """Convert UnifiedDataSourceManager format to civic_digest multi-meeting format (like CivicClerk)"""
        try:
            events = unified_result.get('events', [])
            if not events:
                return self._get_empty_civic_data()

            # Get jurisdiction info for URLs
            try:
                from civic_services.monitoring.automated_civic_refresh import get_jurisdiction_by_url
                jurisdiction_id = get_jurisdiction_by_url(source_url)
            except ImportError:
                jurisdiction_id = 'unknown'

            # Map jurisdiction_id to known website URLs
            website_mapping = {
                'city-oakland': 'https://www.oaklandca.gov',
                'city-santa-rosa': 'https://srcity.org',
                'sonoma-county': 'https://sonomacounty.ca.gov',
                'city-hayward': 'https://www.hayward-ca.gov',
                'city-napa': 'https://www.cityofnapa.org',
                'bart': 'https://www.bart.gov'
            }

            # Map jurisdiction_id to Legistar client names for calendar URL
            legistar_client_mapping = {
                'city-oakland': 'oakland',
                'city-santa-rosa': 'santa-rosa',
                'sonoma-county': 'sonomacounty',
                'city-hayward': 'hayward',
                'city-napa': 'napa',
                'bart': 'bart'
            }

            # Construct Legistar calendar URL
            legistar_client_name = legistar_client_mapping.get(jurisdiction_id)
            if legistar_client_name:
                calendar_url = f"https://{legistar_client_name}.legistar.com/Calendar.aspx"
            else:
                calendar_url = source_url  # Fallback to source URL

            # Convert each Legistar event to a separate meeting (following CivicClerk pattern)
            result = {
                "meetings": [],
                "is_multi_meeting_calendar": True  # Signal multi-meeting processing
            }

            for event in events:
                # Extract datetime from Legistar API format
                meeting_datetime = event.get('meeting_datetime', '')
                if 'T' in meeting_datetime:
                    meeting_date = meeting_datetime.split('T')[0]
                    meeting_time = meeting_datetime.split('T')[1]
                elif ' ' in meeting_datetime and ':' in meeting_datetime:
                    date_part, time_part = meeting_datetime.split(' ', 1)
                    meeting_date = date_part
                    meeting_time = time_part
                else:
                    meeting_date = meeting_datetime
                    meeting_time = ''

                # Get agenda URL (UnifiedDataSourceManager uses 'agenda_uri', LegistarClient uses 'agenda_url')
                agenda_url = event.get('agenda_uri') or event.get('agenda_url')

                # Extract event_id from composite id (e.g., "legistar_9405" -> "9405")
                composite_id = event.get('id', '')
                if '_' in composite_id:
                    event_id = composite_id.split('_', 1)[1]
                else:
                    event_id = composite_id

                # Create event_metadata with agenda_expansion structure (like CivicClerk)
                event_metadata = {
                    'title': event.get('title', 'Unknown Item'),
                    'when': meeting_datetime,
                    'location': event.get('location', ''),
                    'video_uri': event.get('video_uri') or event.get('video_url', ''),
                    'agenda_url': agenda_url,
                    'agenda_available': bool(agenda_url),
                    'agenda_expansion': {
                        'available': bool(agenda_url),
                        'source_url': agenda_url if agenda_url else '',
                        'parsed': False,  # Will be populated by AgendaIntegrationManager
                        'actionable_items': []
                    },
                    '_legistar_metadata': {
                        'event_id': event_id,
                        'event_guid': event.get('event_guid'),
                        'body_name': event.get('body_name'),
                        'status': event.get('status'),
                        'meeting_type': event.get('meeting_type')
                    }
                }

                # Create meeting wrapper (follows CivicClerk/CivicPlus pattern)
                meeting_result = {
                    "meeting": {
                        "city": event.get('jurisdiction', 'Unknown'),
                        "date": meeting_date,
                        "start_time": meeting_time,
                        "location": event.get('location', ''),
                        "livestream": event.get('video_url', ''),
                        "public_comment_email": '',  # Not provided by Legistar API
                        "public_comment_deadline": '',
                        "meeting_type": event.get('meeting_type', 'City Council'),
                        "website": website_mapping.get(jurisdiction_id, ''),
                        "calendar_url": calendar_url,
                        "jurisdiction_id": jurisdiction_id
                    },
                    # Store event_metadata for agenda integration (critical for agenda extraction!)
                    "event_metadata": event_metadata,
                    # Empty items - Legistar events don't have agenda expansion by default
                    "items": [],
                    "recap_rows": [
                        {
                            "topic": event.get('title', 'Civic Event'),
                            "why_it_matters": f"Civic engagement opportunity - {event.get('status', 'Meeting scheduled')}",
                            "act_by": meeting_date
                        }
                    ],
                    "bottom_line": f"{event.get('title', 'Civic event')} via Legistar API"
                }

                result["meetings"].append(meeting_result)

            print(f"📋 Converted {len(result['meetings'])} Legistar events to multi-meeting format with agenda URLs")
            return result

        except Exception as e:
            print(f"❌ Error converting unified data: {e}")
            return self._get_empty_civic_data()

    def _get_empty_civic_data(self) -> dict:
        """Return empty civic data structure"""
        return {
            "meeting": {"date": "Not specified"},
            "items": [],
            "recap_rows": [],
            "bottom_line": "Unable to extract civic engagement events."
        }





    def _render_newsletter(self, civic_data: dict, source_url: str = "") -> str:
        """Render newsletter markdown from structured civic data"""
        try:
            render_prompt = f"""
Using this JSON data, render the exact newsletter format with these requirements:

Subject: {{MEETING_TYPE}} 

# ✉️ {{CITY MEETING TYPE}}
*Your quick guide to what's on the {{MEETING_TYPE}} agenda — {{MEETING DATE}}*

## 🗣️ How to Participate
- **Meeting:** [{{DAY, DATE}} at {{START TIME}}]({{GOOGLE_CALENDAR_LINK}}) 📅
- **Where:** {{MEETING LOCATION/ADDRESS}}
- **Watch Online:** {{Livestream/Webinar links if provided, else "Not specified."}}
- **Call In:** {{Dial-in if provided, else "Not specified."}}
- **Email Comments:** {{PUBLIC COMMENT EMAIL or "Not specified."}} — **deadline:** {{DEADLINE or "Not specified."}}
- **Attend & Speak:** {{If speaker time limit provided: "Public comment allowed - X minutes per person" else "Check meeting agenda for public comment rules"}}
- **Full Agenda:** [View original meeting agenda]({{SOURCE_URL}})

## 🚨 What's on the Agenda
### {{Plain-English Title}}
- **Change:** {{1–2 sentence factual change summary}}
- **Impact:** {{2–3 sentence impact to daily life; include timing and costs if stated; else "Cost not specified."}}
- **Action:** {{How to participate: in-person (time limit), email + deadline, webinar/phone if provided}}

## ✅ Bottom Line
{{2-3 sentence summary with call-to-action}}

⚡ *Independent and nonpartisan summary. Facts only; no spin.*

JSON DATA:
{json.dumps(civic_data, indent=2)}

SOURCE URL: {source_url}

CRITICAL: For the Google Calendar link, you MUST create the link exactly as shown in the template:
- **Meeting:** [{{DAY, DATE}} at {{START TIME}}]({{GOOGLE_CALENDAR_LINK}}) 📅

The GOOGLE_CALENDAR_LINK should be a properly formatted Google Calendar URL:
https://calendar.google.com/calendar/render?action=TEMPLATE&text=[MEETING_TITLE]&dates=[START_DATETIME]/[END_DATETIME]&location=[LOCATION]&details=[BRIEF_DESCRIPTION]

Where:
- MEETING_TITLE: e.g. "San Rafael Planning Commission Meeting" (URL encoded)
- START_DATETIME: Date/time in format YYYYMMDDTHHMMSS (convert to UTC if possible)
- END_DATETIME: Add 2 hours to start time if not specified
- LOCATION: Meeting address (URL encoded)
- BRIEF_DESCRIPTION: Brief meeting purpose (URL encoded)

IMPORTANT: The meeting date/time text should be clickable and hide the Google Calendar URL completely. Do NOT show the full URL in the text - only use it as the href target.
"""

            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a civic newsletter formatter. Keep it neutral and concise. Do not invent facts. Follow the exact template format provided. CRITICAL: For Google Calendar links, the meeting time should be clickable hypertext that hides the URL - do not show the actual calendar URL in the text."},
                    {"role": "user", "content": render_prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"❌ Error rendering newsletter: {e}")
            # Fallback to basic newsletter
            return self._render_fallback_newsletter(civic_data, source_url)
    
    def _render_fallback_newsletter(self, civic_data: dict, source_url: str = "") -> str:
        """Fallback newsletter renderer if main rendering fails"""
        meeting = civic_data.get("meeting", {})
        items = civic_data.get("items", [])
        
        newsletter = f"# ✉️ {meeting.get('city', 'City')} Civic Brief\n"
        newsletter += f"*Meeting on {meeting.get('date', 'Date not specified')}*\n\n"
        
        newsletter += "## 🗣️ How to Participate\n"
        
        # Create basic Google Calendar link
        meeting_title = f"{meeting.get('city', 'City')} Meeting"
        calendar_link = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={meeting_title.replace(' ', '%20')}"
        
        newsletter += f"- **Meeting:** [{meeting.get('date', 'Not specified')} at {meeting.get('start_time', 'Not specified')}]({calendar_link}) 📅\n"
        newsletter += f"- **Where:** {meeting.get('location', 'Not specified')}\n"
        newsletter += f"- **Watch Online:** {meeting.get('livestream', 'Not specified')}\n"
        newsletter += f"- **Email Comments:** {meeting.get('public_comment_email', 'Not specified')}\n"
        newsletter += f"- **Attend & Speak:** {meeting.get('public_comment_rules', 'Check meeting agenda for public comment rules')}\n"
        if source_url:
            newsletter += f"- **Full Agenda:** [View original meeting agenda]({source_url})\n"
        newsletter += "\n"
        
        newsletter += "## 🚨 What's on the Agenda\n"
        for item in items:
            newsletter += f"### {item.get('title', 'Item')}\n"
            newsletter += f"- **Change:** {item.get('change', 'Not specified')}\n"
            newsletter += f"- **Impact:** {item.get('impact', 'Not specified')}\n"
            newsletter += f"- **Action:** {item.get('how_to_participate', 'Not specified')}\n\n"
        
        newsletter += f"## ✅ Bottom Line\n{civic_data.get('bottom_line', 'Check meeting agenda for details.')}\n\n"
        newsletter += "⚡ *Independent and nonpartisan summary. Facts only; no spin.*"

        return newsletter

    def _render_combined_newsletter(self, all_civic_data: List[dict], calendar_url: str = "") -> str:
        """Render a combined newsletter from multiple meetings discovered from a calendar page"""

        # Extract city name from first meeting or use default
        city_name = "Your City"
        if all_civic_data and all_civic_data[0].get('city'):
            city_name = all_civic_data[0]['city']

        # Count total events across all meetings
        total_items = sum(len(data.get('agenda_items', [])) for data in all_civic_data)
        meeting_count = len(all_civic_data)

        # Newsletter header
        newsletter = f"Subject: Civic Opportunities - {city_name}\n\n"
        newsletter += f"# ✉️ {city_name} Civic Opportunities\n"
        newsletter += f"*Your guide to upcoming civic engagement events — {meeting_count} meetings found*\n\n"

        # How to participate section (generic since multiple meetings)
        newsletter += "## 🗣️ How to Participate\n"
        newsletter += "- **Multiple meetings available** — see individual meeting details below\n"
        newsletter += "- **Email Comments:** Contact information provided for each meeting\n"
        newsletter += "- **Attend & Speak:** Public comment events available\n"
        newsletter += f"- **Source:** [View meeting calendar]({calendar_url})\n\n"

        # Process each meeting
        for i, civic_data in enumerate(all_civic_data):
            meeting_title = civic_data.get('meeting_title', f'Meeting {i+1}')
            meeting_date = civic_data.get('meeting_date', 'Date TBD')
            meeting_url = civic_data.get('source_url', '')

            newsletter += f"## 📅 {meeting_title}\n"
            newsletter += f"**Date:** {meeting_date}\n"
            if meeting_url:
                newsletter += f"**Details:** [View agenda]({meeting_url})\n"
            newsletter += "\n"

            # Add agenda items for this meeting
            items = civic_data.get('agenda_items', [])
            if items:
                newsletter += f"### 🚨 What's on the Agenda\n"
                for item in items[:3]:  # Limit to 3 items per meeting for brevity
                    newsletter += f"#### {item.get('title', 'Item')}\n"
                    newsletter += f"- **Impact:** {item.get('impact', 'Not specified')}\n"
                    newsletter += f"- **Action:** {item.get('how_to_participate', 'Attend meeting for public comment')}\n\n"

                if len(items) > 3:
                    newsletter += f"*... and {len(items) - 3} more agenda items*\n\n"
            else:
                newsletter += "### 🚨 What's on the Agenda\n*Check individual meeting agenda for details*\n\n"

        # Bottom line
        newsletter += f"## ✅ Bottom Line\n"
        newsletter += f"Found {total_items} civic engagement events across {meeting_count} upcoming meetings in {city_name}. "
        newsletter += "Each meeting offers chances for public input on local decisions.\n\n"
        newsletter += "⚡ *Independent and nonpartisan summary. Facts only; no spin.*"

        # Store combined data for schema adapter
        # Combine items from all meetings - handle both 'items' and 'agenda_items' keys
        all_items = []
        for data in all_civic_data:
            items = data.get('items', data.get('agenda_items', []))
            all_items.extend(items)

        combined_data = {
            'city': city_name,
            'meeting_title': f"{city_name} - Multiple Meetings",
            'meeting_date': 'Various dates',
            'agenda_items': all_items,  # For newsletter rendering
            'items': all_items,  # For schema adapter
            'meeting': {
                'city': city_name,
                'date': 'Various dates',
                'meeting_type': 'Multiple Meetings'
            },
            'bottom_line': f"Multiple civic events available across {meeting_count} meetings"
        }
        self._last_civic_data = combined_data
        self._last_source_url = calendar_url

        return newsletter
    
    def generate_digest(self, events: List[CivicOpportunity], city_name: str = "Your City", source_urls: List[str] = None) -> str:
        """Use AI to extract civic events from meeting content"""
        prompt = f"""
        Extract civic engagement events from this city meeting agenda.
        
        Focus on items where residents can:
        - Provide public comment
        - Attend hearings
        - Submit written feedback
        - Influence decisions
        
        Ignore procedural items like "Call to Order", "Roll Call", routine approvals.
        
        For each opportunity, provide:
        1. Title (brief, clear, avoid jargon)
        2. Impact summary (explain in plain English how this affects daily life - commuting, kids, property values, services you use, taxes, etc. Be specific about timelines and concrete impacts)
        3. How to participate (be specific - can you email? When is deadline? What exactly can you influence?)
        4. Location if mentioned
        5. Project type (housing, transportation, environmental, etc.)
        6. Meeting datetime (extract EXACT time and date from content - look for phrases like "7:00 PM", "Tuesday, September 2", etc.)
        7. Meeting location (extract EXACT meeting location from content)
        8. Meeting duration (if specified, otherwise default to 2 hours)
        
        Write impact summaries like you're explaining to a busy parent who has 30 seconds to decide if they care. Focus on:
        - What changes in their daily life?
        - When will changes happen?
        - How much will it cost them?
        - What services they use are affected?
        
        Meeting content:
        {content[:8000]}  # Limit to avoid token limits
        
        Return as JSON array of events, or empty array if none found.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You extract actionable civic engagement events from meeting agendas. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Parse AI response
            if ai_response.startswith('```'):
                ai_response = re.sub(r'^```\w*\n|```$', '', ai_response, flags=re.MULTILINE)
            
            opportunities_data = json.loads(ai_response)
            
            events = []
            for opp_data in opportunities_data:
                events.append(CivicOpportunity(
                    title=opp_data.get('title', 'City Meeting Item'),
                    when=meeting_date,
                    engagement_info=opp_data.get('engagement_info', 'Attend meeting for public comment'),
                    impact_summary=opp_data.get('impact_summary', 'City decision that may affect residents'),
                    source_url=url,
                    location=opp_data.get('location', ''),
                    project_type=opp_data.get('project_type', '')
                ))
            
            return events
            
        except Exception as e:
            print(f"❌ AI extraction failed: {e}")
            return []

    def enhance_with_wiki_intelligence(self, events: List[CivicOpportunity], meeting_url: str) -> List[CivicOpportunity]:
        """Round 2 LLM: Enhance events with wiki intelligence"""
        if not events:
            return events
            
        print(f"🧠 Enhancing {len(events)} events with wiki intelligence...")
        
        # Detect jurisdiction from URL
        jurisdiction = self._detect_jurisdiction(meeting_url)
        wiki_content = self._load_wiki_files(jurisdiction)
        
        if not wiki_content:
            print(f"⚠️  No wiki files found for jurisdiction: {jurisdiction}")
            return events
            
        enhanced_opportunities = []
        for opp in events:
            try:
                enhanced_opp = self._ai_enhance_opportunity(opp, wiki_content)
                enhanced_opportunities.append(enhanced_opp)
                print(f"✅ Enhanced: {opp.title[:50]}... → {enhanced_opp.contact_email}")
            except Exception as e:
                print(f"❌ Wiki enhancement failed for '{opp.title}': {e}")
                enhanced_opportunities.append(opp)  # Use original if enhancement fails
                
        return enhanced_opportunities

    def _detect_jurisdiction(self, url: str) -> str:
        """Detect jurisdiction from meeting URL using centralized configuration.

        Returns the jurisdiction_id (e.g., 'city-san-rafael') or 'unknown'.
        """
        try:
            from civic_config.jurisdiction import JurisdictionRegistry
            # Try domain-based lookup first
            domain = url.split("//")[1].split("/")[0]
            jurisdiction_id = JurisdictionRegistry.get_jurisdiction_id_by_domain(domain)
            if jurisdiction_id:
                return jurisdiction_id
        except (ImportError, IndexError):
            pass

        # Fallback to automated_civic_refresh for URL pattern matching
        try:
            from civic_services.monitoring.automated_civic_refresh import get_jurisdiction_by_url
            return get_jurisdiction_by_url(url)
        except ImportError:
            return "unknown"

    def _load_wiki_files(self, jurisdiction_id: str) -> str:
        """Load relevant wiki files for jurisdiction.

        Args:
            jurisdiction_id: The jurisdiction ID (e.g., 'city-san-rafael')
        """
        try:
            from civic_config.jurisdiction import JurisdictionRegistry
            wiki_paths = JurisdictionRegistry.get_wiki_files(jurisdiction_id)
        except ImportError:
            wiki_paths = ()

        combined_content = ""
        for file_path in wiki_paths:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    combined_content += f"\n\n## {file_path}\n{f.read()}"
            except FileNotFoundError:
                print(f"⚠️  Wiki file not found: {file_path}")
                continue

        return combined_content

    def _ai_enhance_opportunity(self, opp: CivicOpportunity, wiki_content: str) -> CivicOpportunity:
        """Use LLM to inject wiki intelligence into single opportunity"""
        
        prompt = f"""
        ORIGINAL OPPORTUNITY:
        {json.dumps(opp.to_dict(), indent=2)}
        
        WIKI KNOWLEDGE BASE:
        {wiki_content}
        
        Your task: Enhance this civic opportunity with specific contact routing and proven strategies from the wiki.
        
        Analyze the opportunity title/content to determine appropriate departmental contact:
        1. Issue type from project_type and title:
           - Transportation/Infrastructure/Public Works → April Miller, Public Works Director
           - Planning/Development/Building → Micah Hinkle, Community Development Director  
           - General Policy/Budget → Cristine Alilovich, City Manager
           - Parks/Recreation/Library → April Miller, Public Works Director
        2. Use CONSISTENT contact assignment - same issue types should always get same contacts
        3. Proven engagement strategies from wiki success examples
        4. Effort level classification based on complexity
        
        Return the ORIGINAL opportunity data enhanced with these additional fields:
        - contact_email: Appropriate departmental email based on issue type (be consistent!)
        - contact_name: Official's name and title 
        - success_strategy: Specific approach based on wiki Success Data examples (1 sentence)
        - engagement_tier: "email" (5 min), "comment" (30 min), or "attend" (2+ hours)
        - deadline_guidance: When to engage for maximum impact based on wiki timing data
        
        Return ONLY valid JSON with all original fields plus the 5 new enhanced fields.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert at civic engagement strategy. Use the wiki knowledge to provide specific, actionable guidance. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1  # Low temperature for consistent routing
            )
            
            enhanced_data = json.loads(response.choices[0].message.content.strip())
            
            # Create enhanced CivicOpportunity with new data
            return CivicOpportunity(
                title=enhanced_data.get('title', opp.title),
                when=enhanced_data.get('when', opp.when),
                engagement_info=enhanced_data.get('engagement_info', opp.engagement_info),
                impact_summary=enhanced_data.get('impact_summary', opp.impact_summary),
                source_url=enhanced_data.get('source_url', opp.source_url),
                location=enhanced_data.get('location', opp.location),
                deadline=enhanced_data.get('deadline', opp.deadline),
                project_type=enhanced_data.get('project_type', opp.project_type),
                contact_email=enhanced_data.get('contact_email', ''),
                contact_name=enhanced_data.get('contact_name', ''),
                success_strategy=enhanced_data.get('success_strategy', ''),
                engagement_tier=enhanced_data.get('engagement_tier', 'email'),
                deadline_guidance=enhanced_data.get('deadline_guidance', '')
            )
            
        except Exception as e:
            print(f"❌ AI enhancement parsing failed: {e}")
            return opp  # Return original if enhancement fails
    
    def generate_digest(self, events: List[CivicOpportunity], city_name: str = "Your City", source_urls: List[str] = None) -> str:
        """Generate HTML email digest from events"""
        if not events:
            return self._empty_digest(city_name)
        
        # Sort by date and importance
        sorted_opps = sorted(events, key=lambda x: (
            -(100 if (datetime.fromisoformat(x.when.replace('Z', '+00:00')) - datetime.now()).days <= 7 else 0),
            datetime.fromisoformat(x.when.replace('Z', '+00:00'))
        ))
        
        prompt = f"""
        Create an engaging weekly civic digest email for {city_name}.
        
        Opportunities: {json.dumps([opp.to_dict() for opp in sorted_opps], indent=2)}
        
        Source URLs for verification: {source_urls or ["Not provided"]}
        
        Write for busy working parents who are tired after their day job. Use:
        - Conversational, friendly tone (not bureaucratic)  
        - Headlines that grab attention ("Your Commute Could Change" not "Transportation Policy Update")
        - Explain WHY they should care in the first sentence of each section
        - Specific timelines and concrete impacts
        - Clear action steps with deadlines
        - Avoid jargon - if you must use technical terms, explain them

        IMPORTANT: Each opportunity now includes wiki intelligence. Use these fields:
        - contact_email: Direct official email (use this instead of generic "contact city hall")
        - contact_name: Official's name and title  
        - success_strategy: Proven approach from past successes
        - engagement_tier: Display effort level (email=5min, comment=30min, attend=2hrs)
        - deadline_guidance: When to engage for maximum impact

        Structure as clean HTML with:
        - Subject line focusing on action needed, not generic digest
        - Hook intro: "Here's what's happening in [city] that actually affects your daily life"
        - MANDATORY: Immediately after the intro, include a prominent <strong>UPCOMING MEETINGS</strong> section with the actual meeting details (NOT individual events as separate meetings). Show each unique meeting once with: date, time, duration, location
        - For each actual meeting (like "City Council Meeting"), include one "Add to Google Calendar" link using: https://calendar.google.com/calendar/render?action=TEMPLATE&text=[Actual Meeting Name]&dates=[YYYYMMDDTHHMMSS]/[YYYYMMDDTHHMMSS]&details=[Meeting Agenda Summary]&location=[Meeting Location]
        - MANDATORY: After meetings section, include <strong>CITY COUNCIL CONTACTS</strong> section with general council member names and emails for residents who want to reach out directly
        - MANDATORY: Include a <strong>SOURCE</strong> section at the end with a link to the original meeting agenda for verification
        - Each opportunity with: Clean, engaging headline with hook:description format + structured action options below
        
        Structure each opportunity as:
        <strong>[Engaging Hook]: <span style="color: #666666;">[Specific Description]</span></strong>
        (Example: <strong>Your Commute Could Change: <span style="color: #666666;">Electric Bicycle Safety Regulations</span></strong>)
        <strong>Why This Matters:</strong> {{impact_summary}}
        <strong>EMAIL ACTION (5 min):</strong> Email {{contact_name}} at {{contact_email}} by {{deadline_guidance}}
        <strong>ATTEND MEETING:</strong> {{success_strategy}} [Include specific meeting attendance guidance]

        Format requirements:
        - Clearly present both action options: email contact and meeting attendance
        - Make participation sound easy and worthwhile
        - End with encouragement about making a real difference
        
        CRITICAL FORMATTING: Use proper HTML formatting to ensure line breaks render correctly:
        - Use <br> tags for line breaks, NOT just newlines
        - Use <p> tags to wrap paragraphs with proper spacing
        - Use <strong> for bold text instead of **markdown** (NEVER use **text** - always use <strong>text</strong>)
        - Add <br><br> between sections for clear visual separation
        - NO curly braces in headlines - create clean, engaging titles directly
        - Each section (Why This Matters, EMAIL ACTION, ATTEND MEETING) on its own line with <br> tags
        - Meeting details order: date first, then time, duration, location
        - Google Calendar links: Convert meeting datetime to UTC format (YYYYMMDDTHHMMSSZ), calculate end time from duration
        - Example: For "May 15, 2024 7:00 PM, 2 hours, City Hall" → dates=20240516T020000Z/20240516T040000Z
        - Consolidate meetings: Only create one calendar entry per actual meeting (e.g., "City Council Meeting"), not separate entries for each agenda opportunity
        - Title format: Hook in black, colon, description in dark grey (#666666)
        - Example: "Your Commute Could Change: Electric Bicycle Safety Regulations" where "Electric Bicycle Safety Regulations" is grey
        
        Start with "Subject: " line, then HTML content.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Create engaging civic engagement emails that motivate participation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            
            # Split subject and body
            if content.startswith('Subject:'):
                lines = content.split('\n', 1)
                subject = lines[0].replace('Subject:', '').strip()
                subject = f"{city_name} - {subject}"
                html_content = lines[1] if len(lines) > 1 else ""
            else:
                subject = f"Your {city_name} Civic Digest"
                html_content = content
            
            
            # Wrap in proper HTML if needed
            if not html_content.strip().startswith('<html>'):
                html_content = f"""
                <html>
                <head><meta charset="UTF-8"><title>{subject}</title></head>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    {html_content}
                </body>
                </html>
                """
            
            return f"Subject: {subject}\n{html_content}"
            
        except Exception as e:
            print(f"❌ Digest generation failed: {e}")
            return self._fallback_digest(sorted_opps, city_name)
    
    def _empty_digest(self, city_name: str) -> str:
        """Generate digest when no events found"""
        subject = f"No Major Civic Opportunities This Week in {city_name}"
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2>Your {city_name} Civic Digest</h2>
            <p>No major civic engagement events requiring public input were found this week.</p>
            <p>Check back next week for new events to help shape your community!</p>
        </body>
        </html>
        """
        return f"Subject: {subject}\n{html}"
    
    def _fallback_digest(self, events: List[CivicOpportunity], city_name: str) -> str:
        """Simple fallback digest if AI generation fails"""
        subject = f"Your {city_name} Civic Digest"
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2>{subject}</h2>
            <p>Here are this week's civic engagement events:</p>
        """
        
        for i, opp in enumerate(events, 1):
            html += f"""
            <div style="margin: 20px 0; padding: 15px; border-left: 4px solid #0066cc;">
                <h3>{opp.title}</h3>
                <p><strong>Why it matters:</strong> {opp.impact_summary}</p>
                <p><strong>How to participate:</strong> {opp.engagement_info}</p>
            </div>
            """
        
        html += "</body></html>"
        return f"Subject: {subject}\n{html}"
    
    def send_email(self, digest_content: str, recipient: str):
        """Send digest via email"""
        lines = digest_content.split('\n', 1)
        subject = lines[0].replace('Subject:', '').strip() if lines[0].startswith('Subject:') else "Civic Digest"
        html_content = lines[1] if len(lines) > 1 else digest_content
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.gmail_email
        msg['To'] = recipient
        msg.attach(MIMEText(html_content, 'html'))
        
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.gmail_email, self.gmail_password)
            server.sendmail(self.gmail_email, recipient, msg.as_string())
            server.quit()
            print(f"📧 Sent digest to {recipient}")
        except Exception as e:
            print(f"❌ Email failed: {e}")
    
    def save_digest(self, digest_content: str, city_name: str) -> str:
        """Save digest to file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"data/digests/civic_digest_{city_name.lower().replace(' ', '_')}_{timestamp}.html"
        
        os.makedirs("data/digests", exist_ok=True)
        
        with open(filename, 'w') as f:
            f.write(digest_content)
        
        print(f"💾 Saved to {filename}")
        return filename
    
    def scrape_only(self, meeting_urls: List[str], save_json: bool = True) -> List[CivicOpportunity]:
        """Scrape meetings and save JSON data without generating/sending email"""
        all_opportunities = []
        
        for url in meeting_urls:
            events = self.scrape_meeting(url)
            # Round 2 LLM: Enhance with wiki intelligence
            enhanced_opportunities = self.enhance_with_wiki_intelligence(events, url)
            all_opportunities.extend(enhanced_opportunities)
            
            if save_json and events:
                # Save individual meeting data
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                meeting_name = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                filename = f"data/scraped_data/{meeting_name}_{timestamp}.json"
                
                os.makedirs("data/scraped_data", exist_ok=True)
                
                output_data = {
                    "scraped_at": datetime.now().isoformat(),
                    "source_url": url,
                    "count": len(events),
                    "events": [opp.to_dict() for opp in events]
                }
                
                with open(filename, 'w') as f:
                    json.dump(output_data, f, indent=2)
                
                print(f"💾 Saved JSON data to {filename}")
        
        return all_opportunities
    
    def scrape_and_send(self, meeting_urls: List[str], recipient: str, city_name: str = "San Rafael"):
        """Complete pipeline: scrape -> generate -> send"""
        all_newsletters = []
        
        for url in meeting_urls:
            newsletter = self.scrape_meeting(url)
            all_newsletters.append(newsletter)
        
        # Combine newsletters if multiple URLs, otherwise use single newsletter
        if len(all_newsletters) == 1:
            final_newsletter = all_newsletters[0]
        else:
            # For multiple meetings, create a combined newsletter
            final_newsletter = self._combine_newsletters(all_newsletters, city_name)
        
        self.save_newsletter(final_newsletter, city_name)
        self.send_newsletter_email(final_newsletter, city_name, recipient)
        
        return len(all_newsletters)
    
    def _combine_newsletters(self, newsletters: List[str], city_name: str) -> str:
        """Combine multiple newsletters into one"""
        # For simplicity, just concatenate for now - could be enhanced later
        combined = f"# ✉️ {city_name} Civic Brief\n*Combined meeting summary*\n\n"
        for i, newsletter in enumerate(newsletters, 1):
            combined += f"\n## Meeting {i}\n{newsletter}\n---\n"
        return combined
    
    def save_newsletter(self, newsletter: str, city_name: str):
        """Save newsletter to file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"data/newsletters/civic_newsletter_{city_name.lower()}_{timestamp}.md"
        
        os.makedirs("data/newsletters", exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(newsletter)
        
        print(f"💾 Saved newsletter to {filename}")
    
    def send_newsletter_email(self, newsletter: str, city_name: str,  recipient: str):
        """Send newsletter via email"""
        try:
            # Extract subject from newsletter (look for Subject: line first, then # line)
            lines = newsletter.split('\n')
            subject = "Civic Newsletter"
            
            # First, look for explicit Subject: line
            for line in lines:
                if line.startswith('Subject: '):
                    subject = line[9:].strip()  # Remove "Subject: " prefix
                    subject = f"{city_name} - {subject}"
                    break
            else:
                # Fallback to extracting from # header
                for line in lines:
                    if line.startswith('# '):
                        subject = line[2:].strip()
                        break
            
            # Convert markdown to HTML for email
            html_content = self._markdown_to_html(newsletter)
            
            # Use existing email method - format as Subject: + content
            email_content = f"Subject: {subject}\n\n{html_content}"
            self.send_email(email_content, recipient)
            
        except Exception as e:
            print(f"❌ Failed to send newsletter: {e}")
    
    def _markdown_to_html(self, markdown_text: str) -> str:
        """Convert basic markdown to professional HTML newsletter"""
        
        # Parse the markdown content
        lines = markdown_text.split('\n')
        html_content = ""
        current_section = ""
        in_table = False
        table_rows = []
        
        open_divs = []  # Track open divs for proper closing
        
        for line in lines:
            line = line.strip()
            
            # Skip Subject line (used for email header only)
            if line.startswith('Subject: '):
                continue
            
            # Handle headers
            if line.startswith('# '):
                title = line[2:].strip()
                html_content += f'<h1 style="color: #2c3e50; font-size: 28px; font-weight: bold; margin: 30px 0 20px 0; text-align: center;">{title}</h1>\n'
            elif line.startswith('## '):
                # Close any open sections first
                if 'participate_section' in open_divs:
                    html_content += '</div>\n'
                    open_divs.remove('participate_section')
                if 'agenda_item' in open_divs:
                    html_content += '</div>\n'
                    open_divs.remove('agenda_item')
                    
                section_title = line[3:].strip()
                current_section = section_title.lower()
                
                # Different styling based on section
                if '🗣️' in section_title or 'participate' in section_title.lower():
                    html_content += f'<div style="background: #e8f4f8; padding: 20px; border-radius: 8px; margin: 25px 0;">\n<h2 style="color: #2980b9; font-size: 20px; margin: 0 0 15px 0; font-weight: bold;">{section_title}</h2>\n'
                    open_divs.append('participate_section')
                elif '🚨' in section_title or 'agenda' in section_title.lower():
                    html_content += f'<h2 style="color: #e74c3c; font-size: 22px; margin: 30px 0 20px 0; font-weight: bold; border-bottom: 3px solid #e74c3c; padding-bottom: 10px;">{section_title}</h2>\n'
                elif '📋' in section_title or 'recap' in section_title.lower():
                    html_content += f'<h2 style="color: #8e44ad; font-size: 20px; margin: 30px 0 20px 0; font-weight: bold;">{section_title}</h2>\n'
                else:
                    html_content += f'<h2 style="color: #34495e; font-size: 20px; margin: 25px 0 15px 0; font-weight: bold;">{section_title}</h2>\n'
                    
            elif line.startswith('### '):
                if 'agenda_item' in open_divs:
                    html_content += '</div>\n'
                    open_divs.remove('agenda_item')
                    
                item_title = line[4:].strip()
                html_content += f'<div style="background: #f8f9fa; border-left: 4px solid #3498db; padding: 20px; margin: 20px 0; border-radius: 4px;">\n<h3 style="color: #2c3e50; font-size: 18px; margin: 0 0 15px 0; font-weight: bold;">{item_title}</h3>\n'
                open_divs.append('agenda_item')
                
            # Handle table rows
            elif line.startswith('|') and '|' in line:
                if not in_table:
                    in_table = True
                    table_rows = []
                    
                # Skip separator rows
                if not line.startswith('|---'):
                    cells = [cell.strip() for cell in line.split('|')[1:-1]]  # Remove empty first/last
                    table_rows.append(cells)
                    
            # Handle bullet points
            elif line.startswith('- **'):
                # Extract the label and content
                if ':**' in line:
                    label_end = line.find(':**')
                    label = line[3:label_end].strip()
                    content = line[label_end+3:].strip()
                    
                    # Convert markdown links to HTML in the content
                    content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color: #3498db; text-decoration: none;">\1</a>', content)
                    
                    if 'participate' in current_section:
                        html_content += f'<p style="margin: 8px 0; font-size: 16px; line-height: 1.5;"><strong style="color: #2980b9;">{label}:</strong> {content}</p>\n'
                    else:
                        html_content += f'<p style="margin: 12px 0; font-size: 16px; line-height: 1.6;"><strong style="color: #e74c3c;">{label}:</strong> {content}</p>\n'
                else:
                    # Convert markdown links in the entire line
                    line_content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color: #3498db; text-decoration: none;">\1</a>', line[2:])
                    html_content += f'<p style="margin: 10px 0; font-size: 16px; line-height: 1.5;">{line_content}</p>\n'
                    
            # Handle regular lines
            elif line and not line.startswith('⚡') and not line.startswith('*'):
                # Convert markdown links to HTML
                line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color: #3498db; text-decoration: none;">\1</a>', line)
                html_content += f'<p style="margin: 12px 0; font-size: 16px; line-height: 1.6; color: #555;">{line}</p>\n'
                
            # Handle italic footer
            elif line.startswith('⚡') or (line.startswith('*') and line.endswith('*')):
                footer_text = line.replace('⚡', '').replace('*', '').strip()
                html_content += f'<div style="text-align: center; margin: 30px 0; padding: 15px; background: #ecf0f1; border-radius: 6px;"><em style="color: #7f8c8d; font-size: 14px;">{footer_text}</em></div>\n'
                
            # End of table processing
            elif in_table and table_rows:
                html_content += self._create_modern_table(table_rows)
                in_table = False
                table_rows = []
                
        # Handle any remaining table
        if in_table and table_rows:
            html_content += self._create_modern_table(table_rows)
            
        # Close any remaining open divs
        for div_type in open_divs:
            html_content += '</div>\n'
            
        # Wrap in modern, responsive HTML template
        return self._wrap_in_newsletter_template(html_content)
    
    def _create_modern_table(self, table_rows):
        """Create a modern, responsive table"""
        if not table_rows:
            return ""
            
        table_html = '<div style="margin: 20px 0; overflow-x: auto;"><table style="width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden;">'
        
        # Header row
        if table_rows:
            table_html += '<tr style="background: #3498db; color: white;">'
            for cell in table_rows[0]:
                table_html += f'<th style="padding: 15px; text-align: left; font-weight: bold; font-size: 16px;">{cell}</th>'
            table_html += '</tr>'
            
        # Data rows
        for i, row in enumerate(table_rows[1:], 1):
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            table_html += f'<tr style="background: {bg_color};">'
            for cell in row:
                table_html += f'<td style="padding: 15px; border-bottom: 1px solid #e9ecef; font-size: 15px; line-height: 1.4;">{cell}</td>'
            table_html += '</tr>'
            
        table_html += '</table></div>'
        return table_html
    
    def _wrap_in_newsletter_template(self, content):
        """Wrap content in modern, Gmail-compatible newsletter template"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>Civic Newsletter</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">
    <div style="max-width: 100%; margin: 0; padding: 20px 0; background-color: #f4f4f4;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
            
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px 40px; text-align: center;">
                <h1 style="color: white; font-size: 24px; margin: 0; font-weight: 600;">🏛️ Civic Brief</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0; font-size: 16px;">Your guide to local government</p>
            </div>
            
            <!-- Content -->
            <div style="padding: 40px; color: #333333; line-height: 1.6;">
                {content}
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f8f9fa; padding: 25px 40px; text-align: center; border-top: 1px solid #e9ecef;">
                <p style="margin: 0; color: #6c757d; font-size: 14px;">
                    📧 Questions? Reply to this email<br>
                    🔗 <a href="#" style="color: #3498db; text-decoration: none;">View online</a> | 
                    <a href="#" style="color: #3498db; text-decoration: none;">Unsubscribe</a>
                </p>
            </div>
            
        </div>
    </div>
</body>
</html>"""

    def _deduplicate_agenda_items(self, schema_dict):
        """Remove identical agenda items across different meetings to prevent user confusion"""
        events = schema_dict.get('events', [])
        seen_items = {}  # (title, item_ref) -> (meeting_date, meeting_title)
        total_removed = 0

        for opp in events:
            if not opp.get('agenda_expansion', {}).get('parsed'):
                continue

            items = opp['agenda_expansion'].get('actionable_items', [])
            unique_items = []

            for item in items:
                # Create key from title and item reference
                key = (item.get('title', ''), item.get('item_ref', ''))

                if key in seen_items:
                    # This is a duplicate - skip it
                    prev_date, prev_title = seen_items[key]
                    print(f"⚠️ Duplicate agenda item removed:")
                    print(f"   Item: [{item.get('item_ref')}] {item.get('title')}")
                    print(f"   First seen: {prev_title} ({prev_date})")
                    print(f"   Also in: {opp.get('title')} ({opp.get('when_human')})")
                    total_removed += 1
                    continue

                # Track this item and keep it
                seen_items[key] = (opp.get('when_human'), opp.get('title'))
                unique_items.append(item)

            # Update the opportunity with deduplicated items
            opp['agenda_expansion']['actionable_items'] = unique_items

        if total_removed > 0:
            print(f"🔧 Removed {total_removed} duplicate agenda items across meetings")

        return schema_dict

    def _detect_stale_content(self, schema_dict):
        """Flag agenda items with suspiciously old fiscal year references"""
        import re
        from datetime import datetime

        events = schema_dict.get('events', [])
        current_year = datetime.now().year
        total_flagged = 0

        for opp in events:
            if not opp.get('agenda_expansion', {}).get('parsed'):
                continue

            items = opp['agenda_expansion'].get('actionable_items', [])

            for item in items:
                # Look for fiscal year patterns
                text = item.get('title', '') + ' ' + item.get('description', '')
                fy_pattern = r'FY\s*(\d{4})-(\d{2,4})'
                matches = re.findall(fy_pattern, text)

                for match in matches:
                    fy_year = int(match[0])
                    age = current_year - fy_year

                    if age > 2:
                        # Add warning metadata to the item
                        item['_stale_content_warning'] = True
                        item['_warning_reason'] = f"References FY {fy_year}, which is {age} years old"
                        item['_warning_severity'] = 'high' if age > 4 else 'medium'

                        print(f"⚠️ Stale content detected:")
                        print(f"   Item: {item.get('title')}")
                        print(f"   Meeting: {opp.get('when_human')}")
                        print(f"   Warning: References FY {fy_year} ({age} years old)")
                        total_flagged += 1

        if total_flagged > 0:
            print(f"🔧 Flagged {total_flagged} agenda items with stale content warnings")

        return schema_dict

    def _add_location_fallback(self, schema_dict):
        """Add fallback locations for events missing location data"""
        events = schema_dict.get('events', [])
        jurisdiction_fallbacks = {
            'city-el-cerrito': '10890 San Pablo Ave, El Cerrito, CA 94530',
            'city-san-rafael': '1400 Fifth Avenue, San Rafael, CA 94901',
            'city-berkeley': '2134 Martin Luther King Jr Way, Berkeley, CA 94704',
            'city-oakland': '1 Frank H. Ogawa Plaza, Oakland, CA 94612',
            'city-richmond': '450 Civic Center Plaza, Richmond, CA 94804',
            # Add more as needed
        }

        total_fixed = 0

        for opp in events:
            loc_value = opp.get('location', '')
            # Handle None values (defensive programming for API edge cases)
            if loc_value is None:
                loc_value = ''
            loc = loc_value.strip()

            if not loc:
                # Get jurisdiction ID
                jurisdiction_id = opp.get('jurisdiction', {}).get('id')
                fallback_location = jurisdiction_fallbacks.get(jurisdiction_id, 'City Hall')

                # Set location
                opp['location'] = fallback_location

                # Also update participation mechanisms
                for mechanism in opp.get('participation_mechanisms', []):
                    if mechanism.get('type') == 'attend' and not mechanism.get('location'):
                        mechanism['location'] = fallback_location

                print(f"🔧 Added fallback location for: {opp.get('title')}")
                print(f"   When: {opp.get('when_human')}")
                print(f"   Location: {fallback_location}")
                total_fixed += 1

        if total_fixed > 0:
            print(f"🔧 Added fallback locations for {total_fixed} events")

        return schema_dict

    def _enhance_with_participation_mechanisms(self, schema_dict, enable_agenda_parsing=True):
        """Add enhanced participation mechanisms with precise virtual detection to events during generation

        Args:
            schema_dict: Schema-compliant dictionary with events
            enable_agenda_parsing: If False, skip external agenda integration (faster for initial deployment)
        """
        events = schema_dict.get('events', [])
        enhanced_count = 0

        for event in events:
            # Convert raw agenda items to agenda_expansion structure (event-centric architecture)
            if '_raw_agenda_items' in event and event['_raw_agenda_items']:
                raw_items = event['_raw_agenda_items']
                meeting_data = event.get('_meeting_metadata', {})

                # Create agenda_expansion structure with actionable items
                actionable_items = []
                for idx, item in enumerate(raw_items, 1):
                    # Use LLM's is_actionable determination (default to True if not provided for backward compatibility)
                    is_actionable = item.get('is_actionable', True)

                    actionable_item = {
                        'item_ref': str(idx),
                        'opportunity_id': event['id'],  # Reference parent opportunity for participation mechanisms
                        'title': item.get('title', 'Unknown Item'),
                        'description': item.get('change', item.get('impact', '')),
                        'actionable': is_actionable,
                        'actionable_because': item.get('how_to_participate', 'Public comment opportunity available') if is_actionable else 'Informational item - no public input solicited',
                        # NO participation_mechanisms - resolve via opportunity_id to prevent duplication
                        'related_agenda_items': [],
                        'follows_from': None,
                        'addresses_issues': [],
                        'policy_chain': []
                    }

                    # Preserve project_type from raw item (required for legislative enrichment)
                    # Convert to project_types array format to match agenda_integration.py format
                    if 'project_type' in item:
                        project_type_value = item['project_type']
                        if isinstance(project_type_value, str):
                            actionable_item['project_types'] = [project_type_value]
                        else:
                            actionable_item['project_types'] = project_type_value

                    # Store project/subject location separately if different from meeting location
                    item_location = item.get('location')
                    if item_location and item_location != event.get('location'):
                        actionable_item['project_location'] = item_location

                    actionable_items.append(actionable_item)

                # Set agenda_expansion
                event['agenda_expansion'] = {
                    'available': True,
                    'source_url': event.get('source_url'),
                    'parsed': True,
                    'actionable_items': actionable_items
                }

                # Enrich actionable items with legislative context
                # Each agenda item has its own project_type (from LLM classification) that may be enrichable
                # (even if parent event is generic 'governance' type)
                if actionable_items:
                    try:
                        from legislative_enrichment import enrich_opportunities_batch

                        # Add jurisdiction from parent event (required for enrichment)
                        items_with_jurisdiction = []
                        for item in actionable_items:
                            enrichable_item = {**item, 'jurisdiction': event.get('jurisdiction', {})}
                            items_with_jurisdiction.append(enrichable_item)

                        print(f"🏛️  Enriching {len(items_with_jurisdiction)} agenda items with legislative context...")
                        enriched_items = enrich_opportunities_batch(items_with_jurisdiction)

                        # Remove temporary jurisdiction field before saving
                        for item in enriched_items:
                            if 'jurisdiction' in item:
                                del item['jurisdiction']

                        event['agenda_expansion']['actionable_items'] = enriched_items
                    except Exception as e:
                        print(f"⚠️  Agenda item enrichment failed: {e}")

                # Clean up temporary fields
                del event['_raw_agenda_items']
                if '_meeting_metadata' in event:
                    del event['_meeting_metadata']

                print(f"📋 Converted {len(actionable_items)} agenda items to agenda_expansion for event: {event.get('title')}")

            # Use pre-built participation mechanisms if available
            if '_participation_mechanisms' in event:
                event['participation_mechanisms'] = event['_participation_mechanisms']
                del event['_participation_mechanisms']
                print(f"✅ Applied {len(event['participation_mechanisms'])} participation mechanisms (including virtual if available)")

            # Continue with normal participation mechanism enhancement (as fallback)
            elif event.get('contact_info', {}).get('email'):
                # Extract participation from existing data
                email = event['contact_info']['email']
                when = event.get('when', '')
                location = event.get('location', '')

                # Detect virtual options from location string (precise extraction only)
                virtual_option = None
                virtual_link = None
                if location:
                    # Check for explicit virtual indicators
                    virtual_indicators = ['& Virtual', 'Virtual &', 'Virtual', 'Zoom', 'Teams', 'WebEx', 'online']
                    if any(indicator in location for indicator in virtual_indicators):
                        virtual_option = "available"
                        # Extract actual links if present (basic URL detection)
                        import re
                        url_pattern = r'https?://[^\s<>"&]+'
                        urls = re.findall(url_pattern, location)
                        if urls:
                            virtual_link = urls[0]

                # Create enhanced participation structure with reasonable defaults
                if not event.get('participation_mechanisms'):
                    mechanisms = [
                        {
                            "type": "email",
                            "contact": email,
                            "description": "Send written comment",
                            "deadline": None,  # Empty default - populate when known
                            "duration_minutes": None  # Empty default - populate when known
                        },
                        {
                            "type": "attend",
                            "location": location,
                            "when": when,
                            "description": "Attend meeting for public comment",
                            "duration_minutes": None  # Empty default - populate when known
                        }
                    ]

                    # Add virtual details if detected (precise data only)
                    if virtual_option:
                        mechanisms[1]["virtual_option"] = virtual_option
                        if virtual_link:
                            mechanisms[1]["virtual_link"] = virtual_link

                    event['participation_mechanisms'] = mechanisms
                    enhanced_count += 1

                # Add agenda integration framework (empty defaults)
                if not event.get('agenda_available'):
                    event['agenda_available'] = None  # Populate when agenda is actually checked
                if not event.get('agenda_url'):
                    event['agenda_url'] = None  # Populate when agenda URL is known

                # Initialize relationship arrays for graph features (empty defaults)
                if not event.get('related_events'):
                    event['related_events'] = []
                if not event.get('related_projects'):
                    event['related_projects'] = []

        if enhanced_count > 0:
            print(f"🚀 Enhanced {enhanced_count}/{len(events)} events with graph-ready participation mechanisms")

        # Apply agenda integration enhancement if available
        # NOTE: Skip if agenda_expansion already populated internally (event-centric architecture)
        if enable_agenda_parsing and AGENDA_INTEGRATION_AVAILABLE:
            try:
                # Check if any events already have agenda_expansion populated WITH ACTUAL ITEMS
                events_with_real_agendas = sum(1 for e in schema_dict.get('events', [])
                                               if e.get('agenda_expansion', {}).get('parsed') and
                                               len(e.get('agenda_expansion', {}).get('actionable_items', [])) > 0)

                events_needing_agendas = [e for e in schema_dict.get('events', [])
                                          if not e.get('agenda_expansion', {}).get('parsed') or
                                          len(e.get('agenda_expansion', {}).get('actionable_items', [])) == 0]

                if events_needing_agendas:
                    print(f"🔍 Attempting agenda integration for {len(events_needing_agendas)} events without agendas")
                    # Use external enhancement for events without real agendas
                    schema_dict = enhance_events_with_agenda_integration(schema_dict)
                else:
                    print(f"📋 Skipping external agenda integration - {events_with_real_agendas} events already have agenda_expansion")

                # Re-classify agenda items that have non-standard project_types (from PDF extraction)
                # This ensures consistency with agenda integration taxonomy
                events_needing_reclassification = []
                for event in schema_dict.get('events', []):
                    agenda_exp = event.get('agenda_expansion', {})
                    if agenda_exp.get('parsed') and agenda_exp.get('actionable_items'):
                        items = agenda_exp['actionable_items']
                        # Check if any items have old taxonomy values or missing project_types
                        needs_reclass = False
                        for item in items:
                            project_types = item.get('project_types', [])
                            # Check for old taxonomy indicators (hyphens, spaces, underscores)
                            if not project_types or any('-' in pt or ' ' in pt or '_' in pt for pt in project_types):
                                needs_reclass = True
                                break
                        if needs_reclass:
                            events_needing_reclassification.append(event)

                if events_needing_reclassification:
                    print(f"🔄 Re-classifying {len(events_needing_reclassification)} events with non-standard project_types")
                    # Re-run agenda integration on these events to get proper project_types
                    temp_dict = {'events': events_needing_reclassification}
                    reclassified_dict = enhance_events_with_agenda_integration(temp_dict)

                    # Update the original events with reclassified agenda items
                    for i, event in enumerate(schema_dict.get('events', [])):
                        for reclass_event in reclassified_dict.get('events', []):
                            if event.get('id') == reclass_event.get('id'):
                                # Preserve agenda_expansion with updated project_types
                                if reclass_event.get('agenda_expansion', {}).get('actionable_items'):
                                    event['agenda_expansion'] = reclass_event['agenda_expansion']
                                    print(f"✅ Re-classified agenda items for: {event.get('title', 'Unknown')}")
                                break

                # Enrich ALL agenda items with legislative context (regardless of source)
                # Each agenda item has project_type from LLM classification that may be enrichable
                try:
                    from legislative_enrichment import enrich_opportunities_batch
                    total_items_enriched = 0

                    for event in schema_dict.get('events', []):
                        agenda_exp = event.get('agenda_expansion', {})
                        if agenda_exp.get('parsed') and agenda_exp.get('actionable_items'):
                            items = agenda_exp['actionable_items']

                            # Add jurisdiction from parent event (required for enrichment)
                            items_with_jurisdiction = []
                            for item in items:
                                enrichable_item = {**item, 'jurisdiction': event.get('jurisdiction', {})}
                                items_with_jurisdiction.append(enrichable_item)

                            # Enrich items
                            enriched_items = enrich_opportunities_batch(items_with_jurisdiction)

                            # Remove temporary jurisdiction field before saving
                            for item in enriched_items:
                                if 'jurisdiction' in item:
                                    del item['jurisdiction']

                            # Count enriched items
                            enriched_count = sum(1 for item in enriched_items if 'legislative_context' in item)
                            total_items_enriched += enriched_count

                            event['agenda_expansion']['actionable_items'] = enriched_items

                    if total_items_enriched > 0:
                        print(f"🏛️  Enriched {total_items_enriched} agenda items with legislative context")

                except Exception as e:
                    print(f"⚠️  Agenda item enrichment failed: {e}")

            except Exception as e:
                print(f"⚠️ Agenda integration failed: {e}")
        elif not enable_agenda_parsing:
            print(f"⏭️  Skipping agenda parsing (disabled via flag)")

        # Apply data quality improvements
        schema_dict = self._deduplicate_agenda_items(schema_dict)
        schema_dict = self._detect_stale_content(schema_dict)
        schema_dict = self._add_location_fallback(schema_dict)

        # Add legislative context enrichment
        try:
            from legislative_enrichment import enrich_opportunities_batch
            events = schema_dict.get('events', [])
            if events:
                print(f"🏛️  Enriching {len(events)} events with legislative context...")
                enriched_events = enrich_opportunities_batch(events)
                schema_dict['events'] = enriched_events
        except Exception as e:
            print(f"⚠️  Legislative enrichment failed: {e}")

        return schema_dict

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Command line interface"""
    import sys
    
    if len(sys.argv) < 2:
        print("""
🏛️  Civic Engagement MVP - Simple Usage:

📧 Send digest for specific meeting:
  python civic_digest.py scrape "meeting-url" user@email.com

🔍 Scrape data only (no email):
  python civic_digest.py data "meeting-url"

🧪 Test with known working URL:
  python civic_digest.py test [user@email.com]

👨‍💼 Test Joe-friendly version:
  python civic_digest.py joe "meeting-url"

⚙️  Weekly automation (runs Monday 9am):
  python civic_digest.py weekly

📋 Show status:
  python civic_digest.py status

Examples:
  python civic_digest.py scrape "https://cityofsanrafael.org/meetings/city-council-september-2-2025-tuesday/" user@email.com
  python civic_digest.py data "https://cityofsanrafael.org/meetings/city-council-september-2-2025-tuesday/"
        """)
        return
    
    command = sys.argv[1].lower()
    digest = CivicDigest()
    
    if command == "scrape" and len(sys.argv) >= 4:
        meeting_url = sys.argv[2]
        recipient = sys.argv[3]
        
        print(f"🚀 Sending immediate digest for: {meeting_url}")
        count = digest.scrape_and_send([meeting_url], recipient)
        print(f"✅ Complete! Found {count} events")
    
    elif command == "data" and len(sys.argv) >= 3:
        meeting_url = sys.argv[2]
        
        print(f"🔍 Scraping data only for: {meeting_url}")
        events = digest.scrape_only([meeting_url])
        
        if events:
            print(f"✅ Found {len(events)} events:")
            for i, opp in enumerate(events, 1):
                print(f"  {i}. {opp.title[:60]}...")
                print(f"     Impact: {opp.impact_summary[:80]}...")
                print()
        else:
            print("❌ No events found")
        
    elif command == "joe" and len(sys.argv) >= 3:
        meeting_url = sys.argv[2]
        
        print(f"👨‍💼 Testing Joe-friendly version for: {meeting_url}")
        print("    (This uses improved prompts for busy working parents)")
        
        events = digest.scrape_only([meeting_url])
        
        if events:
            print(f"✅ Found {len(events)} events with Joe-friendly descriptions:")
            print()
            for i, opp in enumerate(events, 1):
                print(f"📋 {i}. {opp.title}")
                print(f"   💡 Impact: {opp.impact_summary}")
                print(f"   🎯 Action: {opp.engagement_info}")
                print()
        else:
            print("❌ No events found")
            
    elif command == "test":
        recipient = sys.argv[2] if len(sys.argv) > 2 else digest.gmail_email
        
        # Use known working URL
        test_url = "https://www.cityofsanrafael.org/meetings/planning-commission-may-27-2025/"
        print(f"🧪 Testing with positive control: {test_url}")
        
        count = digest.scrape_and_send([test_url], recipient)
        print(f"✅ Test complete! Found {count} events")
        
    elif command == "weekly":
        print("⏰ Starting weekly automation (Monday 9:00 AM)...")
        print("Press Ctrl+C to stop")
        
        # Default weekly URLs - customize as needed
        weekly_urls = [
            "https://www.cityofsanrafael.org/meetings"
        ]
        
        def send_weekly():
            # In real implementation, would load user list from config
            recipients = [digest.gmail_email]  # Send to self for now
            
            for recipient in recipients:
                try:
                    count = digest.scrape_and_send(weekly_urls, recipient)
                    print(f"📅 Weekly digest sent to {recipient} ({count} events)")
                except Exception as e:
                    print(f"❌ Failed to send to {recipient}: {e}")
        
        schedule.every().monday.at("09:00").do(send_weekly)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n⏹️  Stopping automation")
    
    elif command == "schema":
        if len(sys.argv) < 3:
            print("❌ Please provide meeting URL: python civic_digest.py schema \"meeting-url\" [--skip-agenda-parsing]")
            return

        if not SCHEMA_ADAPTER_AVAILABLE:
            print("❌ Schema adapter not available. Please ensure civic_schema_adapter.py is in the same directory.")
            return

        meeting_url = sys.argv[2]
        # Check for optional flags
        skip_agenda_parsing = '--skip-agenda-parsing' in sys.argv
        enable_agenda_parsing = not skip_agenda_parsing
        disable_archive_fallback = '--disable-archive-fallback' in sys.argv

        if skip_agenda_parsing:
            print(f"🔄 Generating schema-compliant data (events only, no agenda parsing): {meeting_url}")
        else:
            print(f"🔄 Generating schema-compliant data for: {meeting_url}")

        if disable_archive_fallback:
            print("⚠️ Archive fallback disabled - will return no data if live sources fail")

        try:
            # Discover meeting URLs (may return multiple)
            discovered_urls = digest._discover_meeting_urls_with_agents(meeting_url)

            if len(discovered_urls) > 1:
                print(f"📋 Discovered {len(discovered_urls)} meetings - processing independently")

                # Process each meeting independently through complete pipeline
                all_schema_dicts = []
                adapter = CivicSchemaAdapter()

                for i, individual_meeting_url in enumerate(discovered_urls, 1):
                    print(f"\n🔄 Processing meeting {i}/{len(discovered_urls)}: {individual_meeting_url}")

                    try:
                        # Generate civic data for this specific meeting
                        individual_newsletter = digest._generate_civic_newsletter(individual_meeting_url)
                        individual_civic_data = digest._last_civic_data

                        # Convert to schema immediately (preserves meeting context)
                        schema_newsletter = adapter.adapt_newsletter(
                            individual_civic_data,
                            individual_newsletter,
                            individual_meeting_url,  # Correct source URL for this meeting
                            []
                        )

                        # Check if adapter returned None (invalid datetime or other critical failure)
                        if schema_newsletter is None:
                            print(f"⚠️ Skipping meeting {i}: No valid datetime")
                            continue

                        # Convert to dict
                        schema_dict = adapter.to_dict(schema_newsletter)

                        # Enhance with participation mechanisms (including agenda extraction)
                        schema_dict = digest._enhance_with_participation_mechanisms(schema_dict, enable_agenda_parsing)

                        all_schema_dicts.append(schema_dict)

                        print(f"✅ Processed {len(schema_newsletter.events)} events from meeting {i}")

                    except Exception as e:
                        print(f"⚠️ Error processing meeting {i}: {e}")
                        continue

                # Combine all events into single output file
                if all_schema_dicts:
                    # Use first meeting's jurisdiction for file naming
                    jurisdiction_id = all_schema_dicts[0].get('jurisdiction', {}).get('id', 'unknown')
                    jurisdiction_name = all_schema_dicts[0].get('jurisdiction', {}).get('name', 'Unknown')

                    # Combine all events
                    combined_opportunities = []
                    for schema_dict in all_schema_dicts:
                        combined_opportunities.extend(schema_dict.get('events', []))

                    # Create combined output
                    combined_output = {
                        'id': all_schema_dicts[0].get('id'),
                        'jurisdiction': all_schema_dicts[0].get('jurisdiction'),
                        'events': combined_opportunities,
                        'generation_metadata': {
                            'scrape_urls': [meeting_url],
                            'meetings_processed': len(all_schema_dicts),
                            'ai_model_used': 'gpt-4o',
                            'wiki_files_loaded': [],
                            'generation_cost': 0.0,
                            'processing_time': 0.0,
                            'unparseable_urls': None
                        },
                        'html_content': all_schema_dicts[0].get('html_content', ''),
                        'text_content': all_schema_dicts[0].get('text_content', ''),
                        'subject_line': f"Civic Opportunities - {jurisdiction_name}",
                        'send_date': datetime.now().isoformat(),
                        'recipients': [],
                        'analytics': {
                            'sent_count': 0,
                            'open_rate': 0.0,
                            'click_rate': 0.0,
                            'action_conversion_rate': 0.0
                        },
                        'created_at': datetime.now().isoformat()
                    }

                    # Apply data quality improvements to combined output
                    combined_output = digest._deduplicate_agenda_items(combined_output)
                    # Stale detection and location fallback already applied per-event

                    # Save combined output
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_file = f"data/events/events_{jurisdiction_id}_{timestamp}.json"
                    os.makedirs("data/events", exist_ok=True)

                    # Custom JSON encoder to handle datetime objects
                    def datetime_serializer(obj):
                        if isinstance(obj, datetime):
                            return obj.isoformat()
                        raise TypeError(f"Type {type(obj)} not serializable")

                    with open(output_file, 'w') as f:
                        json.dump(combined_output, f, indent=2, default=datetime_serializer)

                    print(f"\n✅ Event-centric data saved to: {output_file}")
                    print(f"📊 Found {len(combined_opportunities)} civic events across {len(all_schema_dicts)} meetings")

                    # Print summary
                    print(f"\n📋 Summary:")
                    print(f"   City: {jurisdiction_name}")
                    print(f"   Meetings: {len(all_schema_dicts)}")
                    print(f"   Opportunities: {len(combined_opportunities)}")
                    for i, opp in enumerate(combined_opportunities, 1):
                        print(f"   {i}. {opp.get('title', 'Unknown')} ({opp.get('project_type', 'unknown')})")
                else:
                    print("❌ No meetings successfully processed")

            else:
                # Single meeting - use original logic
                meeting_url = discovered_urls[0]
                newsletter_content = digest._generate_civic_newsletter(meeting_url)

                # Check if we have the civic data
                if not hasattr(digest, '_last_civic_data'):
                    print("❌ No civic data available. Newsletter generation may have failed.")
                    return

                # Check if this was a multi-meeting calendar result (CivicPlus calendars)
                if hasattr(digest, '_multi_meeting_data') and digest._multi_meeting_data:
                    print(f"📅 Processing multi-meeting calendar with {len(digest._multi_meeting_data)} events")

                    # Process each meeting independently
                    all_schema_dicts = []
                    adapter = CivicSchemaAdapter()

                    for i, meeting_data in enumerate(digest._multi_meeting_data, 1):
                        meeting_type = meeting_data.get('meeting', {}).get('meeting_type', 'unknown')
                        # Get title from event_metadata (calendar events) or items (agenda meetings)
                        event_metadata = meeting_data.get('event_metadata', {})
                        items = meeting_data.get('items', [])
                        meeting_title = event_metadata.get('title') if event_metadata else (items[0].get('title', 'Unknown') if items else 'Unknown Event')
                        print(f"\n🔄 Processing calendar event {i}/{len(digest._multi_meeting_data)}: {meeting_title}")

                        try:
                            # CivicClerk events: event_metadata is already schema-compliant, use directly
                            has_civicclerk_metadata = event_metadata and event_metadata.get('_civicclerk_metadata') if event_metadata else False
                            if has_civicclerk_metadata:
                                # Direct path: event_metadata is already a complete civic schema opportunity
                                import uuid
                                from datetime import timezone
                                jurisdiction = event_metadata.get('jurisdiction', {})
                                schema_dict = {
                                    'id': str(uuid.uuid4()),
                                    'jurisdiction': jurisdiction,
                                    'events': [event_metadata],
                                    'generation_metadata': {
                                        'scrape_urls': [meeting_url],
                                        'ai_model_used': 'civicclerk_api',
                                        'wiki_files_loaded': [],
                                        'generation_cost': 0.0,
                                        'processing_time': 0.0
                                    },
                                    'html_content': f"# {meeting_title}\n\n{meeting_data.get('bottom_line', '')}",
                                    'text_content': f"# {meeting_title}\n\n{meeting_data.get('bottom_line', '')}",
                                    'subject_line': meeting_title,
                                    'send_date': datetime.now(timezone.utc).isoformat(),
                                    'recipients': [],
                                    'analytics': {
                                        'sent_count': 0,
                                        'open_rate': 0.0,
                                        'click_rate': 0.0,
                                        'action_conversion_rate': 0.0
                                    }
                                }
                            else:
                                # Standard path: Use adapter for CivicPlus and other calendar events
                                meeting_newsletter = f"# {meeting_title}\n\n{meeting_data.get('bottom_line', '')}"

                                # Convert to schema
                                schema_newsletter = adapter.adapt_newsletter(
                                    meeting_data,
                                    meeting_newsletter,
                                    meeting_url,
                                    []
                                )

                                # Check if adapter returned None (invalid datetime or other critical failure)
                                if schema_newsletter is None:
                                    print(f"⚠️ Skipping meeting: No valid datetime")
                                    continue

                                # Convert to dict
                                schema_dict = adapter.to_dict(schema_newsletter)

                            # Enhance with participation mechanisms
                            schema_dict = digest._enhance_with_participation_mechanisms(schema_dict, enable_agenda_parsing)

                            all_schema_dicts.append(schema_dict)

                            # Print success message
                            num_opps = len(schema_dict.get('events', []))
                            print(f"✅ Processed {num_opps} events from event {i}")

                        except Exception as e:
                            print(f"⚠️ Error processing calendar event {i}: {e}")
                            import traceback
                            traceback.print_exc()
                            continue

                    # Combine all events into single output
                    if all_schema_dicts:
                        jurisdiction_id = all_schema_dicts[0].get('jurisdiction', {}).get('id', 'unknown')
                        jurisdiction_name = all_schema_dicts[0].get('jurisdiction', {}).get('name', 'Unknown')

                        # Combine all events
                        combined_opportunities = []
                        for schema_dict in all_schema_dicts:
                            combined_opportunities.extend(schema_dict.get('events', []))

                        # Create combined output (before data quality checks)
                        combined_output = {
                            'id': all_schema_dicts[0].get('id'),
                            'jurisdiction': all_schema_dicts[0].get('jurisdiction'),
                            'events': combined_opportunities,
                            'generation_metadata': {
                                'scrape_urls': [meeting_url],
                                'ai_model_used': 'gpt-5-mini',
                                'wiki_files_loaded': [],
                                'generation_cost': 0.0,
                                'processing_time': 0.0,
                                'unparseable_urls': None
                            },
                            'html_content': all_schema_dicts[0].get('html_content', ''),
                            'text_content': all_schema_dicts[0].get('text_content', ''),
                            'subject_line': all_schema_dicts[0].get('subject_line', 'Civic Events'),
                            'send_date': all_schema_dicts[0].get('send_date'),
                            'recipients': [],
                            'analytics': all_schema_dicts[0].get('analytics'),
                            'created_at': all_schema_dicts[0].get('created_at')
                        }

                        # Apply data quality improvements to combined output
                        # Note: These need to run AFTER events are combined, not before
                        combined_output = digest._deduplicate_agenda_items(combined_output)
                        # Stale detection and location fallback were already applied per-event
                        # so we don't need to re-run them here

                        # Save to file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        output_file = f"data/events/events_{jurisdiction_id}_{timestamp}.json"
                        os.makedirs("data/events", exist_ok=True)

                        def datetime_serializer(obj):
                            if isinstance(obj, datetime):
                                return obj.isoformat()
                            raise TypeError(f"Type {type(obj)} not serializable")

                        with open(output_file, 'w') as f:
                            json.dump(combined_output, f, indent=2, default=datetime_serializer)

                        print(f"\n✅ Event-centric data saved to: {output_file}")
                        print(f"📊 Found {len(combined_opportunities)} civic events")

                        # Print summary
                        print(f"\n📋 Summary:")
                        print(f"   City: {jurisdiction_name}")
                        print(f"   Opportunities: {len(combined_opportunities)}")
                        for i, opp in enumerate(combined_opportunities, 1):
                            print(f"   {i}. {opp.get('title', 'Unknown')} ({opp.get('project_type', 'unknown')})")

                        return

                # Standard single-meeting processing
                # Use schema adapter to convert
                adapter = CivicSchemaAdapter()
                schema_newsletter = adapter.adapt_newsletter(
                    digest._last_civic_data,
                    newsletter_content,
                    digest._last_source_url,
                    []  # No recipients for schema output
                )

                # Check if adapter returned None (invalid datetime or other critical failure)
                if schema_newsletter is None:
                    print("❌ Error generating schema data: Meeting has no valid datetime")
                    return

                # Convert to dict and output as JSON
                schema_dict = adapter.to_dict(schema_newsletter)

                # Enhance with participation mechanisms during generation
                schema_dict = digest._enhance_with_participation_mechanisms(schema_dict, enable_agenda_parsing)

                # Save to file with event-centric naming
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # Extract jurisdiction for semantic naming
                jurisdiction_id = schema_dict.get('jurisdiction', {}).get('id', 'unknown')

                # Use event-centric naming: events_{jurisdiction}_{timestamp}.json
                output_file = f"data/events/events_{jurisdiction_id}_{timestamp}.json"
                os.makedirs("data/events", exist_ok=True)

                # Custom JSON encoder to handle datetime objects
                def datetime_serializer(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")

                with open(output_file, 'w') as f:
                    json.dump(schema_dict, f, indent=2, default=datetime_serializer)

                print(f"✅ Event-centric data saved to: {output_file}")
                print(f"📊 Found {len(schema_newsletter.events)} civic events")

                # Also print summary
                print(f"\n📋 Summary:")
                print(f"   City: {schema_newsletter.jurisdiction.name}")
                print(f"   Opportunities: {len(schema_newsletter.events)}")
                for i, opp in enumerate(schema_newsletter.events, 1):
                    print(f"   {i}. {opp.title} ({opp.project_type})")

        except Exception as e:
            print(f"❌ Error generating schema data: {e}")
            import traceback
            traceback.print_exc()
            
    elif command == "status":
        print("📊 Civic Digest Status:")
        print(f"✅ OpenAI API: {'Connected' if digest.openai_key else 'Missing'}")
        print(f"✅ Gmail: {'Connected' if digest.gmail_email else 'Missing'}")
        print(f"✅ Schema Adapter: {'Available' if SCHEMA_ADAPTER_AVAILABLE else 'Missing'}")
        print(f"📧 Email: {digest.gmail_email}")
        print("📁 Output: data/digests/")
        print("📁 Schema: data/schema/")
        
    else:
        print("❌ Unknown command. Use: scrape, data, test, joe, schema, weekly, or status")

if __name__ == "__main__":
    main()