#!/usr/bin/env python3
"""
Agenda Integration System - Transform events to actionable civic intelligence

LLM-powered agenda discovery and actionability assessment that converts
meeting announcements into specific events with agenda items.
"""

import os
import re
import json
import requests
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
import openai
import html
from urllib.parse import quote

# Import structured API clients for robust data sources
try:
    from legistar_client import create_client as create_legistar_client
    LEGISTAR_AVAILABLE = True
except ImportError:
    LEGISTAR_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

@dataclass
class AgendaItem:
    """Individual agenda item with actionability assessment"""
    item_ref: str
    title: str
    description: str = ""
    actionable: bool = False
    actionable_reason: str = ""
    project_types: List[str] = None  # Classified by LLM during extraction (primary type first)
    participation_mechanisms: List[Dict[str, Any]] = None
    related_agenda_items: List[str] = None
    follows_from: Optional[str] = None
    addresses_issues: List[str] = None
    policy_chain: List[str] = None

    def __post_init__(self):
        if self.participation_mechanisms is None:
            self.participation_mechanisms = []
        if self.project_types is None:
            self.project_types = ['governance']
        if self.related_agenda_items is None:
            self.related_agenda_items = []
        if self.addresses_issues is None:
            self.addresses_issues = []
        if self.policy_chain is None:
            self.policy_chain = []

class AgendaIntegrator:
    """Multi-tier robust agenda discovery and actionability assessment"""

    def __init__(
        self,
        model: Optional[str] = None,
        task_type: str = 'long_document'
    ):
        """Initialize with configurable model selection (model-first architecture)

        Args:
            model: Model name (e.g., 'gpt-4o-mini', 'gemini-2.0-flash-exp')
                   If provided, uses this specific model
            task_type: Task type for model selection if model not provided (default: 'long_document')
                      'long_document' = Gemini 1.5 Pro with 2M context for large agenda packets
                      'draft' = quality-first (gpt-4o-mini) for complex civic reasoning
                      'research' = cost-optimized for simple tasks
        """
        # Priority 1: Use explicit model if provided
        if model:
            from civic_services.core.llm_provider import get_model
            self.provider = get_model(model)
        # Priority 2: Resolve from task_type
        else:
            from civic_services.core.llm_provider import get_model_for_task
            self.provider = get_model_for_task(task_type)

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Civic-Engagement-Platform/1.0 (Foundation-funded civic transparency tool)'
        })

        # Initialize structured API clients for robustness
        self.legistar_clients = {}
        self.civicclerk_jurisdictions = {}
        self._init_structured_clients()

    def _init_structured_clients(self):
        """Initialize structured API clients for maximum robustness"""
        if LEGISTAR_AVAILABLE:
            # Pre-configure known working Legistar clients
            legistar_cities = ['oakland', 'santa-rosa', 'hayward', 'napa']
            for city in legistar_cities:
                try:
                    self.legistar_clients[city] = create_legistar_client(city)
                except Exception:
                    pass  # Graceful failure for individual clients

        # Pre-configure known CivicClerk jurisdictions
        # Maps jurisdiction_id -> civicclerk subdomain
        self.civicclerk_jurisdictions = {
            'city-el-cerrito': 'elcerritoca',
            'city-los-altos': 'losaltosca',  # NEW: Top deployment candidate (86% agenda availability)
            # Add more CivicClerk cities as discovered
        }

    def discover_agenda_url(self, event: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """
        Multi-tier robust agenda discovery with structured API priority

        Tier 1: Structured APIs (most robust)
        Tier 2: LLM-powered discovery (most flexible)
        Tier 3: Pattern matching fallback (safety net)

        Returns:
            (agenda_url, agenda_available) tuple
        """
        # Tier 1: Try structured API sources first (most robust)
        agenda_url, agenda_available = self._try_structured_api_discovery(event)
        if agenda_available:
            print(f"📋 Structured API agenda found: {agenda_url[:100]}...")
            return agenda_url, agenda_available

        # Tier 2: LLM-powered discovery for maximum flexibility
        agenda_url, agenda_available = self._try_llm_discovery(event)
        if agenda_available:
            print(f"📋 LLM-discovered agenda found: {agenda_url[:100]}...")
            return agenda_url, agenda_available

        # Tier 3: Pattern matching fallback for safety net
        agenda_url, agenda_available = self._try_pattern_fallback(event)
        if agenda_available:
            print(f"📋 Pattern-matched agenda found: {agenda_url[:100]}...")
            return agenda_url, agenda_available

        return None, False

    def _try_structured_api_discovery(self, event: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Tier 1: Try structured API sources (Legistar, CivicPlus AgendaCenter, etc.)"""
        try:
            source_url = event.get('source_url', '')
            jurisdiction_id = event.get('jurisdiction', {}).get('id', '')

            # Priority 1: Check for Legistar metadata (most reliable)
            if '_legistar_metadata' in event:
                return self._discover_from_legistar_api(event)

            # Priority 2: Check for Granicus metadata
            if '_granicus_metadata' in event:
                return self._discover_from_granicus(event)

            # Priority 3: Check for CivicClerk metadata
            if '_civicclerk_metadata' in event:
                return self._discover_from_civicclerk(event)

            # Priority 4: Check source URL patterns
            if 'legistar.granicus.com' in source_url or 'legistar' in source_url.lower():
                return self._discover_from_legistar_api(event)

            # Priority 4: Check for CivicClerk jurisdictions
            if jurisdiction_id in self.civicclerk_jurisdictions:
                return self._discover_from_civicclerk(event)

            # Priority 5: Check for CivicPlus Calendar.aspx (try AgendaCenter)
            if 'Calendar.aspx' in source_url:
                agenda_url, agenda_available = self._discover_from_civicplus_agendacenter(event)
                if agenda_available:
                    return agenda_url, agenda_available

            # Priority 6: Check for other structured sources by jurisdiction
            if jurisdiction_id in self.legistar_clients:
                return self._discover_from_legistar_api(event)

            return None, False

        except Exception as e:
            print(f"⚠️ Structured API discovery failed: {type(e).__name__}")
            return None, False

    def _discover_from_legistar_api(self, event: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Discover agenda from Legistar API metadata"""
        try:
            # Check if event has _legistar_metadata with agenda URL
            legistar_metadata = event.get('_legistar_metadata', {})
            if not legistar_metadata:
                return None, False

            # Directly check if event already has agenda_url at top level (from convert_to_civic_format)
            agenda_url = event.get('agenda_url')
            if agenda_url:
                print(f"📋 Found Legistar agenda URL from event metadata: {agenda_url[:80]}...")
                return agenda_url, True

            # Fallback: check agenda_expansion structure
            agenda_expansion = event.get('agenda_expansion', {})
            source_url = agenda_expansion.get('source_url')
            if source_url:
                print(f"📋 Found Legistar agenda URL from agenda_expansion: {source_url[:80]}...")
                return source_url, True

            print(f"⚠️ Legistar metadata present but no agenda URL found")
            return None, False

        except Exception as e:
            print(f"⚠️ Legistar discovery failed: {type(e).__name__}")
            return None, False

    def _discover_from_granicus(self, event: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Discover agenda from Granicus ViewPublisher metadata"""
        try:
            # Check if event has _granicus_metadata with agenda URL
            granicus_metadata = event.get('_granicus_metadata', {})
            if not granicus_metadata:
                return None, False

            # Priority 1: Use agenda_url (AgendaViewer) - structured HTML
            agenda_url = granicus_metadata.get('agenda_url')
            if agenda_url:
                print(f"📋 Found Granicus agenda_url (AgendaViewer): {agenda_url[:80]}...")
                return agenda_url, True

            # Priority 2: Use packet_url (PDF) with size warning
            packet_url = granicus_metadata.get('packet_url')
            if packet_url:
                print(f"📋 Found Granicus packet_url (PDF): {packet_url[:80]}...")
                print(f"⚠️  Note: Packet PDFs may be very large and include non-agenda documents")
                return packet_url, True

            # Priority 3: Check top-level agenda_url field (fallback)
            top_level_agenda = event.get('agenda_url')
            if top_level_agenda:
                print(f"📋 Found Granicus agenda URL from event metadata: {top_level_agenda[:80]}...")
                return top_level_agenda, True

            print(f"⚠️ Granicus metadata present but no agenda URL found")
            return None, False

        except Exception as e:
            print(f"⚠️ Granicus discovery failed: {type(e).__name__}")
            return None, False

    def _discover_from_civicplus_agendacenter(self, event: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Discover agenda from CivicPlus Archive pages by meeting type and date"""
        try:
            from datetime import datetime
            from urllib.parse import urlparse, urljoin
            import re

            source_url = event.get('source_url', '')
            event_date = event.get('when', '')
            meeting_type = event.get('meeting_type', '')
            title = event.get('title', '')

            # Skip non-governmental meetings (community events, tours, etc.)
            skip_types = ['community_meeting', 'community_services', 'environment']
            if meeting_type in skip_types and not any(keyword in title.lower() for keyword in ['commission', 'council', 'board']):
                print(f"⏭️  Skipping agenda search for community event: {title}")
                return None, False

            # Extract base URL
            parsed = urlparse(source_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"

            print(f"🏛️ Checking CivicPlus Archives for: {title}")

            # Parse event date
            event_datetime = None
            if event_date:
                try:
                    if isinstance(event_date, str):
                        from dateutil import parser
                        event_datetime = parser.parse(event_date)
                    else:
                        event_datetime = event_date
                except Exception as e:
                    print(f"⚠️ Could not parse event date: {e}")
                    return None, False

            if not event_datetime:
                print(f"⚠️ No valid event date for archive search")
                return None, False

            # Map meeting types to Archive AMID (Archive Meeting ID)
            amid_map = {
                'planning_commission': '45',
                'city_council': '41',
                'arts_culture_commission': '40',
                'board': None,  # Generic, needs keyword matching
                'commission': None,
                'committee': None,
            }

            # Try to get AMID from meeting type
            amid = amid_map.get(meeting_type)

            # If no direct mapping, try to find AMID from /698/Agendas-Minutes page
            if not amid:
                agendas_page = f"{base_url}/698/Agendas-Minutes"
                try:
                    response = self.session.get(agendas_page, timeout=10)
                    if response.status_code == 200:
                        if not BEAUTIFULSOUP_AVAILABLE:
                            return None, False

                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.content, 'html.parser')

                        # Find archive links that match the meeting keywords
                        meeting_keywords = self._get_meeting_keywords(meeting_type, title)
                        for link in soup.find_all('a', href=True):
                            if 'Archive.aspx?AMID=' in link['href']:
                                link_text = link.get_text().lower()
                                if any(keyword in link_text for keyword in meeting_keywords):
                                    # Extract AMID parameter
                                    match = re.search(r'AMID=(\d+)', link['href'])
                                    if match:
                                        amid = match.group(1)
                                        print(f"📌 Found matching archive: AMID={amid}")
                                        break
                except Exception as e:
                    print(f"⚠️ Could not fetch agendas page: {e}")

            if not amid:
                print(f"⚠️ No archive ID found for {meeting_type}")
                return None, False

            # Fetch the archive listing page
            archive_url = f"{base_url}/Archive.aspx?AMID={amid}"
            print(f"📅 Searching archive: {event_datetime.strftime('%B %d, %Y')}")

            response = self.session.get(archive_url, timeout=15)
            response.raise_for_status()

            if not BEAUTIFULSOUP_AVAILABLE:
                return None, False

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find agenda links with dates (Archive.aspx?ADID=XXXX)
            # Match by date proximity (within 7 days)
            best_match = None
            best_date_diff = float('inf')

            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'Archive.aspx?ADID=' not in href:
                    continue

                link_text = link.get_text().strip()

                # Try to parse date from link text
                try:
                    # Common formats: "September 17, 2025", "Sep 17, 2025", etc.
                    from dateutil import parser as date_parser
                    link_date = date_parser.parse(link_text, fuzzy=True)

                    # Calculate date difference
                    date_diff = abs((link_date - event_datetime).days)

                    # Keep best match within 7 days
                    if date_diff < best_date_diff and date_diff <= 7:
                        best_date_diff = date_diff
                        best_match = (href, link_text, date_diff)

                except Exception:
                    continue

            if best_match:
                href, link_text, date_diff = best_match
                full_url = urljoin(base_url, href) if not href.startswith('http') else href
                print(f"📋 Found agenda: {link_text} ({date_diff} days difference)")
                return full_url, True

            print(f"⚠️ No matching agenda found in archive")
            return None, False

        except Exception as e:
            print(f"⚠️ CivicPlus archive discovery failed: {type(e).__name__}: {e}")
            return None, False

    def _discover_from_civicclerk(self, event: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Discover agenda from CivicClerk API (Granicus product)"""
        try:
            from datetime import datetime, timedelta
            from urllib.parse import urlparse

            source_url = event.get('source_url', '')
            event_date = event.get('when', '')
            title = event.get('title', '')
            jurisdiction_id = event.get('jurisdiction', {}).get('id', '')

            # Get CivicClerk subdomain from registry
            jurisdiction = self.civicclerk_jurisdictions.get(jurisdiction_id)
            if not jurisdiction:
                print(f"⚠️ No CivicClerk mapping for jurisdiction: {jurisdiction_id}")
                return None, False

            print(f"🏛️ Checking CivicClerk API for: {title}")

            # Parse event date
            event_datetime = None
            if event_date:
                try:
                    if isinstance(event_date, str):
                        from dateutil import parser
                        event_datetime = parser.parse(event_date)
                    else:
                        event_datetime = event_date
                except Exception as e:
                    print(f"⚠️ Could not parse event date: {e}")
                    return None, False

            if not event_datetime:
                print(f"⚠️ No valid event date for CivicClerk search")
                return None, False

            # CivicClerk API endpoint
            api_base = f"https://{jurisdiction}.api.civicclerk.com/v1"
            portal_base = f"https://{jurisdiction}.portal.civicclerk.com"

            # Query events with agendas around the event date (±3 days)
            start_date = (event_datetime - timedelta(days=3)).strftime('%Y-%m-%dT00:00:00.000Z')
            end_date = (event_datetime + timedelta(days=3)).strftime('%Y-%m-%dT23:59:59.999Z')

            # Build API URL with proper OData filter (must be URL encoded)
            from urllib.parse import quote
            filter_str = f"startDateTime ge {start_date} and startDateTime le {end_date}"
            orderby_str = "startDateTime asc"
            # Note: Can't use hasAgenda filter or $expand as they don't return publishedFiles
            api_url = f"{api_base}/Events?$filter={quote(filter_str)}&$orderby={quote(orderby_str)}"

            print(f"📡 CivicClerk API URL: {api_url}")

            response = self.session.get(api_url, headers={'Accept': 'application/json'}, timeout=15)
            response.raise_for_status()

            # Debug: print response if not JSON
            try:
                data = response.json()
            except Exception as json_err:
                print(f"⚠️ API returned non-JSON response (status {response.status_code}): {response.text[:200]}")
                raise
            events = data.get('value', [])

            if not events:
                print(f"⚠️ No events with agendas found in CivicClerk API")
                return None, False

            print(f"📋 Found {len(events)} events in date range")

            # Find best matching event by title similarity and date proximity
            best_match = None
            best_score = 0

            for api_event in events:
                # Skip events without agendas
                if not api_event.get('hasAgenda'):
                    continue

                event_id = api_event.get('id')
                event_name = api_event.get('eventName', '')

                # Fetch individual event details to get publishedFiles
                # (list endpoint doesn't include publishedFiles)
                event_detail_url = f"{api_base}/Events/{event_id}"
                try:
                    detail_response = self.session.get(event_detail_url, headers={'Accept': 'application/json'}, timeout=10)
                    detail_response.raise_for_status()
                    event_detail = detail_response.json()
                    published_files = event_detail.get('publishedFiles', [])
                except Exception as e:
                    print(f"  ⚠️ Could not fetch details for event {event_id}: {e}")
                    continue

                # Find agenda or notice files (both can contain actionable items)
                # Prefer Agenda, but accept Notice if no Agenda available
                agenda_file = None
                for file_type in ['Agenda', 'Notice', 'Packet']:  # Priority order
                    agenda_file = next((f for f in published_files if f.get('type') == file_type), None)
                    if agenda_file:
                        break

                if not agenda_file:
                    print(f"  ⏭️ Skipping '{event_name}' - no agenda/notice/packet files in publishedFiles")
                    continue

                file_id = agenda_file.get('fileId')
                api_url = agenda_file.get('url')  # Direct API URL to PDF
                file_type = agenda_file.get('type', 'Unknown')
                if not file_id or not api_url:
                    print(f"  ⏭️ Skipping '{event_name}' - missing fileId or url in {file_type} file")
                    continue

                print(f"  📄 Using {file_type} file (ID: {file_id})")

                # Calculate match score (simple word overlap)
                title_words = set(title.lower().split())
                event_words = set(event_name.lower().split())
                overlap = len(title_words & event_words)
                score = overlap / max(len(title_words), 1)

                # Calculate date difference
                api_event_date = datetime.fromisoformat(api_event.get('startDateTime').replace('Z', '+00:00'))
                date_diff = abs((api_event_date - event_datetime).days)

                # Boost score if exact date match
                if date_diff == 0:
                    score += 2.0
                elif date_diff <= 1:
                    score += 0.5

                if score > best_score:
                    best_score = score
                    best_match = {
                        'event_id': event_id,
                        'file_id': file_id,
                        'api_url': api_url,
                        'event_name': event_name,
                        'score': score,
                        'date_diff': date_diff
                    }

            if best_match and best_match['score'] >= 0.3:  # Require minimum 30% match
                # Return the API URL which provides access to the actual PDF
                # Format: https://elcerritoca.api.civicclerk.com/v1/Meetings/GetMeetingFile(fileId=X,plainText=false)
                agenda_url = best_match['api_url']
                print(f"📋 Found CivicClerk agenda: {best_match['event_name']} (score: {best_match['score']:.2f})")
                print(f"    API URL: {agenda_url}")
                return agenda_url, True

            print(f"⚠️ No matching agenda found in CivicClerk (best score: {best_score:.2f})")
            return None, False

        except Exception as e:
            print(f"⚠️ CivicClerk discovery failed: {type(e).__name__}: {e}")
            return None, False

    def _get_meeting_keywords(self, meeting_type: str, title: str) -> list:
        """Get keywords for matching meeting agendas"""
        keywords = []

        # Add title words (>3 chars)
        if title:
            keywords.extend([word.lower() for word in title.split() if len(word) > 3])

        # Add meeting type specific keywords
        type_keywords = {
            'planning_commission': ['planning', 'commission'],
            'city_council': ['council', 'city'],
            'board': ['board'],
            'advisory_committee': ['committee', 'advisory'],
            'zoning_administrator': ['zoning'],
        }

        if meeting_type in type_keywords:
            keywords.extend(type_keywords[meeting_type])

        return list(set(keywords))  # Remove duplicates

    def _try_llm_discovery(self, event: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Tier 2: LLM-powered agenda discovery (original implementation)"""
        source_url = event.get('source_url', '')
        if not source_url:
            return None, False

        try:
            # Validate and fetch the source page with size limits
            if not self._is_safe_url(source_url):
                print(f"⚠️ Unsafe URL detected: {source_url}")
                return None, False

            response = self.session.get(source_url, timeout=15, stream=True)
            response.raise_for_status()

            # Check content size before downloading
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 5_000_000:  # 5MB limit
                print(f"⚠️ Content too large: {content_length} bytes")
                return None, False

            # Read content with size limit
            content = ''
            size = 0
            for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
                size += len(chunk)
                if size > 5_000_000:  # 5MB limit
                    print(f"⚠️ Content exceeded size limit during download")
                    return None, False
                content += chunk

            # Use LLM to analyze page for agenda URLs (with input sanitization)
            safe_url = html.escape(source_url)
            safe_title = html.escape(str(event.get('title', 'Unknown'))[:200])  # Limit length
            safe_date = html.escape(str(event.get('when_human', 'Unknown'))[:100])  # Limit length
            safe_content = html.escape(content[:8000])  # Sanitize and limit content

            prompt = f"""Analyze this municipal meeting webpage to find agenda links.

URL: {safe_url}
Event: {safe_title}
Date: {safe_date}

HTML Content (first 8000 chars):
{safe_content}

Find agenda documents or links with these characteristics:
1. PDF files with "agenda" in filename/text (including Google Cloud Storage URLs)
2. Links labeled "agenda", "packet", "meeting materials"
3. Legistar/Granicus agenda viewer links
4. Direct agenda document references
5. Municipal naming patterns like "ZA-Hearing-Agenda", "Council-Agenda", "Meeting-Packet"

Look specifically for:
- PDF URLs containing storage.googleapis.com, amazonaws.com, or municipal servers
- Embedded document viewers or iframe sources
- Download links for agenda packets or materials

Respond in JSON format:
{{
    "agenda_url": "full URL to agenda document/page or null",
    "agenda_available": true/false,
    "confidence": "high/medium/low",
    "agenda_type": "pdf/webpage/legistar_viewer/unknown",
    "reasoning": "brief explanation of finding"
}}

Be conservative - only return URLs that clearly contain agenda content."""

            response_text = self._call_llm(prompt, max_tokens=300)
            result = self._safe_json_parse(response_text)
            if not result:
                return None, False

            agenda_url = result.get('agenda_url')
            if agenda_url and not agenda_url.startswith('http'):
                # Convert relative URLs to absolute with validation
                try:
                    agenda_url = urljoin(source_url, agenda_url)
                    if not self._is_safe_url(agenda_url):
                        print(f"⚠️ Unsafe resolved URL: {agenda_url}")
                        return None, False
                except Exception:
                    return None, False

            agenda_available = bool(agenda_url and result.get('agenda_available', False))

            return agenda_url, agenda_available

        except Exception as e:
            print(f"⚠️ LLM discovery failed: {type(e).__name__}")
            return None, False

    def _try_pattern_fallback(self, event: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Tier 3: Pattern matching fallback for maximum robustness"""
        source_url = event.get('source_url', '')
        if not source_url or not BEAUTIFULSOUP_AVAILABLE:
            return None, False

        try:
            # Validate and fetch the source page
            if not self._is_safe_url(source_url):
                return None, False

            response = self.session.get(source_url, timeout=15)
            response.raise_for_status()

            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            # Robust pattern matching for agenda URLs
            agenda_candidates = []

            # Pattern 1: Direct agenda links
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text().strip().lower()

                score = 0

                # High-value patterns
                if 'agenda' in text and len(text) < 50:  # Avoid long descriptions
                    score += 10
                if 'packet' in text and len(text) < 50:
                    score += 8
                if '#tab-agenda' in href or '#agenda' in href:
                    score += 12  # Municipal agenda tabs
                if '.pdf' in href.lower() and 'agenda' in text:
                    score += 15  # Direct agenda PDFs

                # Enhanced PDF pattern matching
                if '.pdf' in href.lower():
                    if 'agenda' in href.lower() or 'packet' in href.lower():
                        score += 18  # Strong PDF agenda indicators
                    if any(pattern in href.lower() for pattern in ['za-hearing', 'council-agenda', 'meeting-packet']):
                        score += 12  # Municipal naming patterns

                # Medium-value patterns
                event_title_words = event.get('title', '').lower().split()
                if any(word in text for word in event_title_words if len(word) > 3):
                    score += 5

                # Bonus for specific meeting pages
                if 'meeting' in href and ('2025' in href or '10-' in href or 'october' in href):
                    score += 3

                if score >= 10:  # Conservative threshold
                    # Convert to absolute URL
                    if not href.startswith('http'):
                        href = urljoin(source_url, href)

                    if self._is_safe_url(href):
                        agenda_candidates.append((score, href, text[:50]))

            # Return highest scoring candidate
            if agenda_candidates:
                agenda_candidates.sort(reverse=True, key=lambda x: x[0])
                best_score, best_url, best_text = agenda_candidates[0]
                print(f"📋 Pattern fallback found: '{best_text}' (score: {best_score})")

                # If we found a tab/fragment URL, try to extract PDFs from within it
                if '#tab' in best_url or '#agenda' in best_url:
                    pdf_url = self._extract_pdf_from_tab_page(best_url)
                    if pdf_url:
                        print(f"📋 Extracted PDF from tab: {pdf_url}")
                        return pdf_url, True

                return best_url, True

            return None, False

        except Exception as e:
            print(f"⚠️ Pattern fallback failed: {type(e).__name__}")
            return None, False

    def _extract_pdf_from_tab_page(self, tab_url: str) -> Optional[str]:
        """Extract PDF URLs from municipal tab pages that embed documents"""
        try:
            if not self._is_safe_url(tab_url) or not BEAUTIFULSOUP_AVAILABLE:
                return None

            # Remove fragment and fetch the base page
            base_url = tab_url.split('#')[0]
            response = self.session.get(base_url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for PDF URLs with high agenda likelihood
            pdf_candidates = []

            # Check all links for PDF patterns
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text().strip().lower()

                if '.pdf' in href.lower():
                    score = 0

                    # Strong agenda indicators in URL
                    if 'agenda' in href.lower():
                        score += 20
                    if 'packet' in href.lower():
                        score += 15
                    if any(pattern in href.lower() for pattern in ['za-hearing', 'council-agenda', 'meeting-packet']):
                        score += 15

                    # Strong agenda indicators in text
                    if 'agenda' in text:
                        score += 10
                    if 'packet' in text:
                        score += 8

                    # Cloud storage patterns (Google, AWS)
                    if 'storage.googleapis.com' in href or 'amazonaws.com' in href:
                        score += 5

                    # Date patterns (current year/month)
                    if '2025' in href and ('09' in href or '10' in href or 'october' in href):
                        score += 5

                    if score >= 15:  # Conservative threshold for PDFs
                        # Convert to absolute URL
                        if not href.startswith('http'):
                            href = urljoin(base_url, href)

                        if self._is_safe_url(href):
                            pdf_candidates.append((score, href, text[:50]))

            # Return highest scoring PDF
            if pdf_candidates:
                pdf_candidates.sort(reverse=True, key=lambda x: x[0])
                best_score, best_pdf_url, best_text = pdf_candidates[0]
                print(f"📄 Found PDF: '{best_text}' (score: {best_score})")
                return best_pdf_url

            return None

        except Exception as e:
            print(f"⚠️ PDF extraction from tab failed: {type(e).__name__}")
            return None

    def _resolve_civicclerk_blob_url(self, api_url: str) -> Optional[str]:
        """
        Resolve CivicClerk API URL to actual blob storage URL

        CivicClerk API returns JSON like: {"blobUri": "https://civicclerk.blob.core.windows.net/..."}
        """
        try:
            response = self.session.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            blob_uri = data.get('blobUri')
            if blob_uri:
                print(f"📄 Resolved CivicClerk blob URL")
                return blob_uri
            else:
                print(f"⚠️ No blobUri in CivicClerk API response")
                return None
        except Exception as e:
            print(f"⚠️ Failed to resolve CivicClerk blob URL: {type(e).__name__}: {e}")
            return None

    def parse_agenda_content(self, agenda_url: str, event: Dict[str, Any]) -> List[AgendaItem]:
        """
        Parse agenda content and extract actionable items

        Returns list of AgendaItem objects with actionability assessment
        """
        if not agenda_url:
            return []

        try:
            # Validate and fetch agenda content with size limits
            if not self._is_safe_url(agenda_url):
                print(f"⚠️ Unsafe agenda URL: {agenda_url}")
                return []

            # Special handling for CivicClerk API URLs
            # These return JSON with a blobUri field pointing to the actual PDF
            if 'api.civicclerk.com' in agenda_url and 'GetMeetingFile' in agenda_url:
                agenda_url = self._resolve_civicclerk_blob_url(agenda_url)
                if not agenda_url:
                    print(f"⚠️ Could not resolve CivicClerk blob URL")
                    return []

            # Try normal request first
            try:
                response = self.session.get(agenda_url, timeout=20, stream=True)
                response.raise_for_status()
            except requests.exceptions.SSLError as ssl_err:
                # Handle Granicus S3 redirect SSL certificate mismatch
                # (AgendaViewer redirects to granicus_production_attachments.s3.amazonaws.com)
                if 'granicus' in agenda_url.lower() or 's3.amazonaws.com' in str(ssl_err):
                    print(f"⚠️ SSL error on Granicus redirect, retrying with verify=False...")
                    response = self.session.get(agenda_url, timeout=20, stream=True, verify=False)
                    response.raise_for_status()
                else:
                    raise

            # Check content size
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 50_000_000:  # 50MB limit for large agenda packets
                print(f"⚠️ Agenda content too large: {content_length} bytes")
                return []

            # Read with size limit
            content_bytes = b''
            size = 0
            for chunk in response.iter_content(chunk_size=8192):
                size += len(chunk)
                if size > 50_000_000:  # 50MB limit for large packets with attachments
                    print(f"⚠️ Agenda content exceeded size limit")
                    return []
                content_bytes += chunk

            # Determine content type and extract text safely
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' in content_type:
                text_content = self._extract_pdf_text(content_bytes)
            else:
                try:
                    text_content = content_bytes.decode('utf-8', errors='ignore')[:12000]
                except Exception:
                    text_content = str(content_bytes)[:12000]

            # Check for meeting cancellations FIRST (highest priority)
            is_cancelled, cancellation_reason = self._detect_cancellation(text_content, event)
            if is_cancelled:
                print(f"⚠️  Meeting CANCELLED: {cancellation_reason}")
                self._last_parse_error = f"Meeting cancelled: {cancellation_reason}"
                # Return special "cancelled" marker instead of empty list
                return [AgendaItem(
                    item_ref="CANCELLATION_NOTICE",
                    title="Meeting Cancelled",
                    description=cancellation_reason,
                    actionable=False,
                    actionable_reason="This meeting has been cancelled and will not occur"
                )]

            # Validate agenda content freshness before processing
            is_stale, stale_reason = self._validate_agenda_freshness(text_content, event)
            stale_severity = 'high' if is_stale else None

            # For highly stale content (>4 years), reject completely
            if is_stale and ('5 years' in stale_reason or '6 years' in stale_reason or '7 years' in stale_reason):
                print(f"⚠️ Highly stale agenda detected ({stale_reason}) - skipping parse")
                self._last_parse_error = f"Stale content: {stale_reason}"
                return []
            elif is_stale:
                # For moderately stale (3-4 years), warn but still attempt parse
                print(f"⚠️ Potentially stale agenda ({stale_reason}) - parsing with warning")
                stale_severity = 'medium'

            # Use LLM for conservative actionability assessment (with input sanitization)
            safe_title = html.escape(str(event.get('title', 'Unknown'))[:200])
            safe_date = html.escape(str(event.get('when_human', 'Unknown'))[:100])
            contact_info = event.get('contact_info', {})
            safe_contact = html.escape(str(contact_info.get('email', 'Unknown'))[:100])
            safe_agenda_content = html.escape(text_content[:200000])  # Increased to 200K for Gemini 1.5 Pro's 2M context

            prompt = f"""Parse this agenda content to find actionable civic events.

Meeting: {safe_title}
Date: {safe_date}
Contact: {safe_contact}

Agenda Content:
{safe_agenda_content}

Extract items where residents can meaningfully participate or should be aware:
- Public hearings with comment periods
- Items explicitly requesting public input
- Policy decisions (housing, development, land use, budget, services)
- Consent calendar items involving public resources, property, or services
- Items with clear participation deadlines

For each actionable item, provide:
{{
    "items": [
        {{
            "item_ref": "item number/letter from agenda",
            "title": "clear, specific title",
            "description": "what this item involves (1 sentence)",
            "actionable": true,
            "actionable_reason": "WHY residents can participate or should be aware",
            "project_types": ["primary_type", "secondary_type"],
            "participation_deadline": "extracted deadline or null",
            "public_comment_info": "how to participate or null"
        }}
    ]
}}

Classify project_types as array (primary type first, then relevant secondary types):
- housing: affordable housing, zoning changes, residential development, inclusionary requirements, use permits, land use decisions, variance requests, conditional use permits, site plan approvals
- transportation: transit, roads, bike lanes, parking, pedestrian infrastructure
- environment: parks, climate action, sustainability, natural resources, wildfire preparedness, vegetation management, environmental regulations, air/water quality
- budget: appropriations, taxes, fees, financial policies, bonds, fiscal planning
- education: schools, libraries, youth programs, educational facilities
- development: commercial development, economic development, business districts (NOT land use/zoning - see housing)
- public_safety: police operations, emergency services (NOT environmental/wildfire policy - see environment)
- community: social services, health programs, recreation, arts, accessibility
- elections: voting, ballot measures, electoral districts, voter registration, campaign finance
- governance: procedural, administrative (non-electoral), appointments, intergovernmental agreements

IMPORTANT DISTINCTIONS:
- Wildfire preparedness/vegetation codes/fire safety regulations → environment (NOT public_safety)
- Fire department budget/staffing/equipment → public_safety
- Use permits/variances/conditional use permits → housing (primary), may include community/development as secondary
- Land use changes/zoning amendments/site plans → housing (primary), development (secondary)
- Commercial business licensing (non-land-use) → development
- Climate-related infrastructure → environment (primary), may include transportation/budget as secondary
- Items can have 1-3 types; most relevant first

Include consent calendar items related to:
- Property/land acquisitions or sales
- Public service contracts (health, housing, infrastructure)
- Budget appropriations >$100K
- Zoning, planning, or development decisions
- Environmental or agricultural policies

Skip only purely procedural items (meeting minutes approval, internal appointments)."""

            response_text = self._call_llm(prompt, max_tokens=2000)
            result = self._safe_json_parse(response_text)
            if not result:
                return []

            agenda_items = []
            for item_data in result.get('items', []):
                # Handle both old (string) and new (array) project_type format
                project_types = item_data.get('project_types', item_data.get('project_type', ['governance']))
                if isinstance(project_types, str):
                    project_types = [project_types]

                item = AgendaItem(
                    item_ref=item_data.get('item_ref', ''),
                    title=item_data.get('title', ''),
                    description=item_data.get('description', ''),
                    actionable=item_data.get('actionable', False),
                    actionable_reason=item_data.get('actionable_reason', ''),
                    project_types=project_types
                )

                # Add participation mechanisms if specific info available
                if item_data.get('public_comment_info') or item_data.get('participation_deadline'):
                    base_mechanisms = event.get('participation_mechanisms', [])
                    enhanced_mechanisms = []

                    for mech in base_mechanisms:
                        enhanced_mech = mech.copy()
                        if mech.get('type') == 'email' and item_data.get('participation_deadline'):
                            enhanced_mech['deadline'] = item_data['participation_deadline']
                        enhanced_mechanisms.append(enhanced_mech)

                    item.participation_mechanisms = enhanced_mechanisms

                agenda_items.append(item)

            # Mark items with stale content warning if detected
            if stale_severity and agenda_items:
                for item in agenda_items:
                    # Store warning in item metadata (will be serialized to JSON)
                    if not hasattr(item, '_metadata'):
                        item._metadata = {}
                    item._metadata['stale_warning'] = {
                        'severity': stale_severity,
                        'reason': stale_reason
                    }

            return agenda_items

        except Exception as e:
            print(f"⚠️ Agenda parsing failed: {type(e).__name__}")
            return []

    def enhance_event_with_agenda(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Complete agenda integration pipeline for a single event

        Returns enhanced event with agenda_expansion populated
        """
        enhanced_event = event.copy()

        # Step 1: Discover agenda URL if not already known
        if not enhanced_event.get('agenda_url'):
            agenda_url, agenda_available = self.discover_agenda_url(event)
            enhanced_event['agenda_url'] = agenda_url
            enhanced_event['agenda_available'] = agenda_available
        else:
            agenda_url = enhanced_event['agenda_url']
            agenda_available = enhanced_event.get('agenda_available', True)

        # Step 2: Parse agenda if available
        agenda_items = []
        if agenda_available and agenda_url:
            agenda_items = self.parse_agenda_content(agenda_url, event)

        # Step 3: Check for cancellation notices FIRST
        is_cancelled = False
        cancellation_notice = None

        if agenda_items and len(agenda_items) == 1:
            item = agenda_items[0]
            if item.item_ref == "CANCELLATION_NOTICE":
                is_cancelled = True
                cancellation_notice = {
                    'cancelled': True,
                    'reason': item.description,
                    'detected_at': 'agenda_parsing'
                }

        # Step 4: Populate agenda_expansion structure with quality metadata
        agenda_expansion = {
            'available': agenda_available,
            'source_url': agenda_url,
            'parsed': bool(agenda_items),
            'actionable_items': [
                {
                    'item_ref': item.item_ref,
                    'title': item.title,
                    'description': item.description,
                    'actionable': item.actionable,
                    'actionable_because': item.actionable_reason,
                    'project_types': item.project_types,
                    'related_agenda_items': item.related_agenda_items,
                    'follows_from': item.follows_from,
                    'addresses_issues': item.addresses_issues,
                    'policy_chain': item.policy_chain
                }
                for item in agenda_items if item.actionable and item.item_ref != "CANCELLATION_NOTICE"
            ]
        }

        # Add cancellation notice if detected
        if is_cancelled:
            agenda_expansion['cancellation_notice'] = cancellation_notice
            # Override engagement info to warn users
            enhanced_event['engagement_info'] = f"⚠️ MEETING CANCELLED - {cancellation_notice['reason']}"
            enhanced_event['status'] = 'cancelled'

        # Add diagnostic info for transparency when agendas are missing
        if not agenda_available:
            agenda_expansion['unavailable_reason'] = 'No published agenda found'
        elif agenda_available and not agenda_items:
            # Agenda exists but no items parsed - explain why
            if hasattr(self, '_last_parse_error'):
                agenda_expansion['parse_failure_reason'] = self._last_parse_error
            else:
                agenda_expansion['parse_failure_reason'] = 'Agenda may be placeholder/not yet finalized'

        enhanced_event['agenda_expansion'] = agenda_expansion

        return enhanced_event

    def _extract_pdf_text(self, pdf_content: bytes) -> str:
        """Extract text from PDF content with smart preamble skipping"""
        try:
            import PyPDF2
            from io import BytesIO

            pdf_file = BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            # Extract first 50 pages to handle large agenda packets with attachments
            # Using Gemini 1.5 Pro with 2M context, we can process much more content
            full_text = ""
            for page in pdf_reader.pages[:50]:
                full_text += page.extract_text() + "\n"

            # Try to intelligently skip preamble and jump to agenda items
            # Many agendas have bilingual intros or lengthy procedural text
            consent_start = full_text.find("CONSENT CALENDAR")
            regular_start = full_text.find("REGULAR CALENDAR")

            # Find the earliest calendar section
            agenda_start = -1
            if consent_start != -1 and regular_start != -1:
                agenda_start = min(consent_start, regular_start)
            elif consent_start != -1:
                agenda_start = consent_start
            elif regular_start != -1:
                agenda_start = regular_start

            if agenda_start > 0:
                # Include some context before the calendar section
                # Increased limit to 200K chars for Gemini 1.5 Pro's 2M token context
                start_pos = max(0, agenda_start - 500)
                return full_text[start_pos:start_pos + 200000]
            else:
                # No clear calendar section found, return first 200k chars
                # This handles agendas with different formats
                return full_text[:200000]

        except ImportError:
            # Fallback: just return a message about PDF content
            return f"[PDF content detected but PyPDF2 not available for text extraction. Content length: {len(pdf_content)} bytes]"
        except Exception as e:
            return f"[PDF text extraction failed: {type(e).__name__}]"

    def _validate_agenda_freshness(self, text_content: str, event: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate that agenda content matches the meeting date and isn't stale

        Returns (is_stale: bool, reason: str)
        """
        try:
            from datetime import datetime

            # Get meeting date
            meeting_date_str = event.get('when', '')
            if not meeting_date_str:
                return False, ""  # Can't validate without date

            try:
                meeting_date = datetime.fromisoformat(meeting_date_str.replace('Z', '+00:00'))
                meeting_year = meeting_date.year
                meeting_month = meeting_date.month
            except:
                return False, ""  # Can't parse date

            # Check for fiscal year references that are too old
            fy_pattern = r'FY\s*(\d{4})(?:-(\d{2,4}))?'
            import re
            fy_matches = re.findall(fy_pattern, text_content, re.IGNORECASE)

            for match in fy_matches:
                fy_year = int(match[0])
                years_old = meeting_year - fy_year

                # Flag if fiscal year is more than 2 years old
                if years_old > 2:
                    return True, f"References FY {fy_year}, which is {years_old} years old (meeting is in {meeting_year})"

            # Check for explicit year mentions in titles/headers that suggest wrong meeting
            # Look for "JUNE 2020" or "MEETING: 2019" patterns in headers (first 1000 chars)
            # More specific patterns to avoid false positives on building codes, etc.
            header_text = text_content[:1000].upper()

            # Look for month + year combinations in headers (strong indicator of wrong meeting)
            month_year_pattern = r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d+,?\s+(20\d{2})'
            month_year_matches = re.findall(month_year_pattern, header_text)

            for match in month_year_matches:
                year_in_header = int(match[1])
                years_old = meeting_year - year_in_header

                if years_old > 2:
                    return True, f"Header references {match[0]} {year_in_header}, which is {years_old} years old"

            return False, ""

        except Exception as e:
            # Don't fail the whole process on validation errors
            print(f"⚠️ Freshness validation error: {type(e).__name__}")
            return False, ""

    def _detect_cancellation(self, text_content: str, event: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Detect if a meeting has been cancelled based on agenda content

        Returns (is_cancelled: bool, cancellation_reason: str)
        """
        try:
            # Check first 1000 characters for cancellation indicators
            header_text = text_content[:1000].upper()

            # Cancellation keywords - must be prominent (in title/header)
            cancellation_patterns = [
                r'CANCEL+ED',  # CANCELLED, CANCELED
                r'MEETING\s+(?:HAS\s+BEEN\s+)?CANCEL+ED',
                r'CANCEL+ED\s+(?:AGENDA|MEETING)',
                r'NOTICE\s+OF\s+CANCEL+ATION',
                r'POSTPONED',
                r'RESCHEDULED',
                r'NO\s+MEETING'
            ]

            # Check for cancellation patterns
            import re
            for pattern in cancellation_patterns:
                match = re.search(pattern, header_text)
                if match:
                    # Extract cancellation reason from context (next 200 chars after match)
                    match_pos = match.start()
                    context = text_content[match_pos:match_pos+300]

                    # Clean up the context for user-friendly display
                    reason_lines = [line.strip() for line in context.split('\n') if line.strip()]
                    cancellation_reason = ' '.join(reason_lines[:3])  # First 3 lines

                    return True, cancellation_reason

            return False, ""

        except Exception as e:
            # Don't fail the whole process on cancellation detection errors
            print(f"⚠️ Cancellation detection error: {type(e).__name__}")
            return False, ""

    def _call_llm(self, prompt: str, max_tokens: int = 1500) -> str:
        """Call LLM via provider abstraction with error handling"""
        try:
            messages = [
                {"role": "system", "content": "You are a civic engagement expert specializing in municipal agenda analysis. Provide accurate, conservative assessments of public participation events."},
                {"role": "user", "content": prompt}
            ]

            response = self.provider.complete(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1  # Low temperature for consistent parsing
            )

            return response.content.strip()
        except Exception as e:
            print(f"⚠️ LLM call failed: {type(e).__name__}")
            raise

    def _is_safe_url(self, url: str) -> bool:
        """Validate URL safety"""
        try:
            parsed = urlparse(url)
            # Only allow http/https
            if parsed.scheme not in ['http', 'https']:
                return False
            # Block localhost, private IPs, etc.
            if parsed.hostname in ['localhost', '127.0.0.1', '0.0.0.0']:
                return False
            if parsed.hostname and parsed.hostname.startswith('192.168.'):
                return False
            if parsed.hostname and parsed.hostname.startswith('10.'):
                return False
            return True
        except Exception:
            return False

    def _safe_json_parse(self, text: str) -> Optional[Dict[str, Any]]:
        """Safely parse JSON with validation"""
        try:
            # Remove any markdown formatting
            text = text.strip()
            if text.startswith('```json'):
                text = text[7:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()

            # Parse JSON
            result = json.loads(text)

            # Validate structure
            if not isinstance(result, dict):
                return None

            # Validate expected fields have safe types
            for key, value in result.items():
                if isinstance(value, str) and len(value) > 2000:  # Limit string lengths
                    result[key] = value[:2000]

            return result
        except Exception:
            return None


def enhance_events_with_agenda_integration(events_data: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Enhance all events in a dataset with agenda integration

    Main entry point for agenda integration pipeline
    """
    integrator = AgendaIntegrator(api_key)
    enhanced_data = events_data.copy()

    enhanced_count = 0
    for event in enhanced_data.get('events', []):
        try:
            enhanced_event = integrator.enhance_event_with_agenda(event)
            event.update(enhanced_event)

            # Count if we found actionable agenda items
            agenda_expansion = event.get('agenda_expansion', {})
            if agenda_expansion.get('actionable_items'):
                enhanced_count += 1

        except Exception as e:
            print(f"⚠️ Failed to enhance event {event.get('id', 'unknown')}: {type(e).__name__}")
            # Ensure basic structure exists even if enhancement fails
            event.setdefault('agenda_expansion', {
                'available': False,
                'source_url': None,
                'parsed': False,
                'actionable_items': []
            })

    if enhanced_count > 0:
        print(f"📋 Enhanced {enhanced_count} events with actionable agenda items")

    return enhanced_data


if __name__ == "__main__":
    """Test agenda integration with sample event data"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python agenda_integration.py <events_json_file>")
        sys.exit(1)

    events_file = sys.argv[1]
    with open(events_file, 'r') as f:
        events_data = json.load(f)

    enhanced_data = enhance_events_with_agenda_integration(events_data)

    # Output enhanced data
    output_file = events_file.replace('.json', '_agenda_enhanced.json')
    with open(output_file, 'w') as f:
        json.dump(enhanced_data, f, indent=2)

    print(f"✅ Enhanced events saved to {output_file}")