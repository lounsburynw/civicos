#!/usr/bin/env python3
"""
Retrospective Decision Analysis System

Specialized extraction and analysis for high-stakes municipal decisions,
optimized for pattern recognition and coordination gap measurement.

Extends agenda_integration.py with retrospective-specific capabilities:
- High-stakes decision identification
- Budget amount extraction
- Impact scope estimation
- Decision metadata enrichment
- Multi-meeting analysis
"""

import json
import html
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import re

from .agenda_integration import AgendaIntegrator, AgendaItem

logger = logging.getLogger(__name__)


class AgendaDownloadError(Exception):
    """Raised when agenda PDF download or text extraction fails."""
    pass


@dataclass
class HighStakesDecision:
    """Enhanced decision metadata for retrospective analysis"""
    # Basic identification
    item_ref: str
    title: str
    description: str
    meeting_date: str
    meeting_type: str  # city_council, planning_commission, tax_oversight, etc.

    # High-stakes classification
    is_high_stakes: bool
    stakes_score: int  # 1-10 scale
    decision_type: str  # budget, development, environmental, policy

    # Impact metadata
    budget_amount: Optional[float]  # Extracted dollar amount
    budget_description: str  # e.g., "supplemental appropriation", "capital project"
    affected_population_estimate: Optional[int]  # Rough estimate
    geographic_scope: str  # citywide, neighborhood, specific_location

    # Project details (for development decisions)
    project_size_units: Optional[int]  # Housing units for development projects
    project_location: Optional[str]

    # Participation metadata
    project_types: List[str]
    keywords_for_matching: List[str]  # For SeeClickFix matching
    participation_mechanisms: List[Dict[str, Any]]

    # Source metadata (original)
    agenda_url: Optional[str]
    staff_report_url: Optional[str]

    # Fields with defaults must follow fields without defaults
    item_type: str = "action"  # action, consent, presentation, hearing, discussion
    extracted_outcome: Optional[str] = None  # LLM-classified outcome
    full_agenda_packet_url: Optional[str] = None  # Full agenda packet PDF
    minutes_url: Optional[str] = None  # Meeting minutes PDF
    testimony_count: Optional[int] = None  # Number of public speakers
    speaker_names: List[str] = None  # Speaker names from minutes
    vote_results: Optional[Dict[str, int]] = None  # {"yes": N, "no": N, "abstain": N}
    passed: Optional[bool] = None  # None = not a vote item; True/False = vote result

    def __post_init__(self):
        """Initialize mutable defaults"""
        if self.speaker_names is None:
            self.speaker_names = []
        if self.vote_results is None:
            self.vote_results = {}

    @property
    def financial_impact_cents(self) -> Optional[int]:
        """
        Convert budget_amount (dollars as float) to cents (integer).

        SESSION 438: Added for precision storage and consistent API.
        Returns None if no budget_amount, otherwise integer cents.
        """
        if self.budget_amount is None:
            return None
        return int(round(self.budget_amount * 100))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        # Add computed property
        result['financial_impact_cents'] = self.financial_impact_cents
        return result


class RetrospectiveAnalyzer(AgendaIntegrator):
    """
    Specialized analyzer for retrospective decision analysis

    Extends AgendaIntegrator with:
    - High-stakes focused extraction prompts
    - Budget/impact metadata extraction
    - Multi-meeting batch processing
    - Decision pattern recognition
    """

    def __init__(self, provider, model_name: Optional[str] = None, cost_calculator=None):
        """Initialize with dependency-injected LLM provider.

        Args:
            provider: LLM provider instance (required). Get from civicos_services.core.llm_provider.
                     Recommended: get_model_for_task('long_document') for Gemini 1.5 Pro (2M context)
            model_name: Model name for cost tracking. If not provided, uses provider.default_model.
            cost_calculator: Optional callable for cost tracking.
        """
        # Use Gemini 2.0 Flash for agenda extraction (1M context, no safety filter issues)
        # Note: Gemini 2.5 Pro triggers safety filters on municipal content (Session 391)
        super().__init__(
            provider=provider,
            model_name=model_name,
            cost_calculator=cost_calculator
        )

    def extract_high_stakes_decisions(
        self,
        event: Dict[str, Any],
        min_budget: int = 100000,
        min_stakes_score: int = 6
    ) -> List[HighStakesDecision]:
        """
        Extract high-stakes decisions from meeting with enhanced metadata.

        Uses a two-pass approach for reliability:
        1. Primary LLM extraction
        2. Budget validation scan to detect missed items
        3. Targeted follow-up extraction for gaps

        Args:
            event: Event dict from civic_digest.py
            min_budget: Minimum budget threshold for auto-flagging ($100K default)
            min_stakes_score: Minimum stakes score (1-10 scale, 6+ is high-stakes)

        Returns:
            List of HighStakesDecision objects
        """
        # Get agenda URL (try multiple metadata sources)
        agenda_url = self._get_agenda_url(event)
        if not agenda_url:
            logger.info(f"No agenda URL found for {event.get('title', 'Unknown')}")
            return []

        # Extract meeting type from event title or metadata
        meeting_type = self._infer_meeting_type(event)

        # Download and extract text — raise on failure so callers can
        # distinguish "download broken" from "no high-stakes decisions"
        text_content = self._download_and_extract_agenda(agenda_url, event)
        if not text_content:
            raise AgendaDownloadError(
                f"Failed to download/extract agenda from {agenda_url} "
                f"for {event.get('title', 'Unknown')}"
            )

        # === PASS 1: Primary LLM extraction ===
        high_stakes_items = self._extract_with_high_stakes_prompt(
            text_content, event, meeting_type, min_budget
        )

        # === PASS 2: Budget validation scan ===
        # Scan text for all dollar amounts >= min_budget
        scanned_amounts = self._scan_for_budget_amounts(text_content, min_budget)

        # Detect gaps: amounts in text but not extracted
        gaps = self._detect_extraction_gaps(high_stakes_items, scanned_amounts)

        if gaps:
            print(f"   🔍 Found {len(gaps)} potential missed budget items, running targeted extraction...")
            # === PASS 3: Targeted follow-up for gaps ===
            additional = self._extract_targeted(text_content, gaps, event, meeting_type)
            if additional:
                print(f"   ✅ Recovered {len(additional)} additional decisions")
                high_stakes_items.extend(additional)

        # Filter by stakes score
        return [
            item for item in high_stakes_items
            if item.stakes_score >= min_stakes_score
        ]

    def _get_agenda_url(self, event: Dict[str, Any]) -> Optional[str]:
        """Extract agenda URL from event metadata"""
        # Try multiple sources
        if event.get('agenda_url'):
            return event['agenda_url']

        # Check agenda_expansion
        agenda_expansion = event.get('agenda_expansion', {})
        if agenda_expansion.get('source_url'):
            return agenda_expansion['source_url']

        # Check platform-specific metadata
        legistar_meta = event.get('_legistar_metadata', {})
        if legistar_meta.get('agenda_url'):
            return legistar_meta['agenda_url']

        civicclerk_meta = event.get('_civicclerk_metadata', {})
        if civicclerk_meta.get('agenda_url'):
            return civicclerk_meta['agenda_url']

        # Try participation mechanisms
        for mech in event.get('participation_mechanisms', []):
            if mech.get('type') == 'agenda' and mech.get('url'):
                return mech['url']

        return None

    def _infer_meeting_type(self, event: Dict[str, Any]) -> str:
        """Infer meeting type from event title/metadata"""
        title = event.get('title', '').lower()

        if 'planning' in title:
            return 'planning_commission'
        elif 'tax oversight' in title or 'voter-approved tax' in title:
            return 'tax_oversight'
        elif 'city council' in title or 'council meeting' in title:
            return 'city_council'
        elif 'zoning' in title:
            return 'zoning_administrator'
        elif 'fire commission' in title:
            return 'fire_commission'
        elif 'subcommittee' in title:
            return 'council_subcommittee'
        else:
            return 'unknown'

    def _download_and_extract_agenda(
        self,
        agenda_url: str,
        event: Dict[str, Any]
    ) -> Optional[str]:
        """Download agenda and extract text content.

        Session 390: For HTML meeting pages, find embedded PDF URLs and
        extract text from those instead. PDFs have cleaner agenda content.
        """
        try:
            response = self.session.get(agenda_url, timeout=20, stream=True)
            response.raise_for_status()

            # Check size
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 50_000_000:
                logger.warning(f"Agenda too large: {content_length} bytes for {agenda_url}")
                return None

            # Read content
            content_bytes = b''
            size = 0
            for chunk in response.iter_content(chunk_size=8192):
                size += len(chunk)
                if size > 50_000_000:
                    logger.warning(f"Agenda exceeded size limit for {agenda_url}")
                    return None
                content_bytes += chunk

            # Extract text based on content type
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' in content_type:
                text_content = self._extract_pdf_text(content_bytes)
            elif 'html' in content_type:
                # HTML page - find embedded PDF and extract from that
                text_content = self._extract_pdf_from_html_page(content_bytes, agenda_url)
            else:
                text_content = content_bytes.decode('utf-8', errors='ignore')

            return text_content

        except Exception as e:
            logger.warning(f"Failed to download agenda from {agenda_url}: {type(e).__name__}: {e}")
            return None

    def _extract_pdf_from_html_page(
        self,
        html_bytes: bytes,
        base_url: str
    ) -> Optional[str]:
        """Extract PDF content from an HTML meeting page.

        Municipal meeting pages often embed agenda PDFs in iframes.
        This finds and downloads the actual PDF for text extraction.
        """
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, unquote
            import re

            soup = BeautifulSoup(html_bytes, 'html.parser')

            # Strategy 1: Find PDFs in iframe src (Google Docs viewer pattern)
            # e.g., //docs.google.com/gview?url=https://storage.googleapis.com/.../agenda.pdf
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src', '')
                if 'gview' in src and 'storage.googleapis.com' in src:
                    match = re.search(r'url=(https://[^&]+\.pdf)', src)
                    if match:
                        pdf_url = unquote(match.group(1))
                        # Prefer agenda PDF over packet (packet can be huge)
                        if 'agenda' in pdf_url.lower() and 'packet' not in pdf_url.lower():
                            print(f"   📄 Found agenda PDF: {pdf_url.split('/')[-1]}")
                            return self._download_pdf_content(pdf_url)

            # Strategy 2: Find direct PDF links with "agenda" in filename
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '.pdf' in href.lower() and 'agenda' in href.lower() and 'packet' not in href.lower():
                    pdf_url = urljoin(base_url, href)
                    print(f"   📄 Found agenda PDF link: {pdf_url.split('/')[-1]}")
                    return self._download_pdf_content(pdf_url)

            # Strategy 3: Fall back to agenda packet if no simple agenda found
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src', '')
                if 'gview' in src and 'storage.googleapis.com' in src:
                    match = re.search(r'url=(https://[^&]+\.pdf)', src)
                    if match:
                        pdf_url = unquote(match.group(1))
                        if 'packet' in pdf_url.lower():
                            print(f"   📄 Using agenda packet: {pdf_url.split('/')[-1]}")
                            return self._download_pdf_content(pdf_url)

            # Strategy 4: Fallback to HTML text extraction
            logger.info(f"No PDF found on {base_url}, using HTML text")
            for element in soup(['script', 'style', 'nav', 'header', 'footer']):
                element.decompose()
            return soup.get_text(separator='\n', strip=True)

        except Exception as e:
            logger.warning(f"PDF extraction failed for {base_url}: {type(e).__name__}: {e}")
            return None

    def _download_pdf_content(self, pdf_url: str) -> Optional[str]:
        """Download a PDF and extract its text content."""
        try:
            response = self.session.get(pdf_url, timeout=30)
            response.raise_for_status()
            return self._extract_pdf_text(response.content)
        except Exception as e:
            logger.warning(f"PDF download failed for {pdf_url}: {type(e).__name__}: {e}")
            return None

    def _split_agenda_into_items(self, text_content: str) -> List[Tuple[str, str]]:
        """
        Split agenda text into individual items using regex

        Returns: List of (item_ref, item_text) tuples
        """
        # San Rafael agenda item patterns:
        # - "5.a  " (section.letter format)
        # - "a.  " (just letter at line start - common in consent calendar)
        # - "Item 5.g"
        # Pattern matches:
        # - newline
        # - optional whitespace
        # - optional "item"
        # - optional number + dot
        # - letter (a-z)
        # - dot and/or whitespace
        pattern = r'\n\s*(?:item\s+)?(\d+\.)?([a-z])\.\s+'

        # Find all item positions
        matches = list(re.finditer(pattern, text_content, re.IGNORECASE))

        if not matches:
            # No items found - return whole document as single item
            print("   ⚠️  No agenda items found via regex, processing whole document")
            return [("unknown", text_content)]

        items = []
        for i, match in enumerate(matches):
            # Build item ref from captured groups
            section = match.group(1) or ""  # "5." or empty
            letter = match.group(2)  # "a", "b", "g", etc.
            item_ref = f"{section}{letter}" if section else letter

            start = match.start()

            # End is start of next item, or end of document
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text_content)

            item_text = text_content[start:end]
            items.append((item_ref, item_text))

        return items

    def _extract_with_high_stakes_prompt(
        self,
        text_content: str,
        event: Dict[str, Any],
        meeting_type: str,
        min_budget: int
    ) -> List[HighStakesDecision]:
        """
        Use LLM to extract ALL high-stakes decisions in a single pass.

        Session 390: Removed brittle regex splitting. LLM handles variable
        agenda formats robustly - just like parent class parse_agenda_content().
        """
        # Sanitize inputs
        safe_title = html.escape(str(event.get('title', 'Unknown'))[:200])
        safe_date = html.escape(str(event.get('when_human', 'Unknown'))[:100])
        safe_meeting_type = html.escape(meeting_type)
        # Use generous limit - Gemini 2.5 Pro has 2M context
        safe_text = html.escape(text_content[:150000])

        prompt = f"""Analyze this municipal meeting agenda/packet and extract ALL high-stakes decisions.

Meeting: {safe_title}
Date: {safe_date}
Meeting Type: {safe_meeting_type}

FULL AGENDA TEXT:
{safe_text}

OBJECTIVE: Extract ALL decisions with significant community impact. Return MULTIPLE items if found.

CRITICAL: Any agenda item mentioning a dollar amount >= ${min_budget:,} MUST be extracted.

HIGH-STAKES CRITERIA (flag if ANY apply):
1. Budget decisions >= ${min_budget:,} (THIS IS MANDATORY - DO NOT SKIP):
   - Supplemental appropriations, capital projects, grant allocations, major contracts
   - EXTRACT SPECIFIC DOLLAR AMOUNTS from text
   - If you see "$235,224" or "$152,718" or any 6-figure amount, INCLUDE IT

2. Development decisions:
   - Residential projects >20 units, major commercial developments
   - Zoning amendments affecting multiple parcels
   - EXTRACT PROJECT SIZE (# units) from text

3. Environmental/policy decisions affecting >1,000 residents:
   - Climate action, wildfire/vegetation management, water/infrastructure, service changes

4. Tax/fee decisions:
   - New taxes, tax increases, fee structure changes, special assessment districts

For EACH high-stakes item found, extract:
{{
    "items": [
        {{
            "item_ref": "item number from agenda (e.g., '5.a', 'Item 7', 'Consent-3')",
            "title": "clear, specific title",
            "description": "detailed description (2-3 sentences) - WHO, WHAT, WHY",
            "is_high_stakes": true,
            "stakes_score": 1-10,
            "decision_type": "budget|development|environmental|policy|tax",
            "item_type": "action|consent|presentation|hearing|discussion",
            "outcome": "approved|denied|continued|withdrawn|received|adopted",
            "budget_amount": dollar amount as number or null,
            "budget_description": "what the budget is for" or null,
            "affected_population_estimate": number or null,
            "geographic_scope": "citywide|neighborhood|specific_location",
            "project_size_units": number of housing units or null,
            "project_location": "street address or area" or null,
            "project_types": ["primary_type", "secondary_type"],
            "keywords_for_matching": ["keyword1", "keyword2", ...]
        }}
    ]
}}

DECISION TYPE CLASSIFICATION:
- budget: Appropriations, contracts, grants, capital projects
- development: Housing/commercial construction, zoning changes, land use
- environmental: Climate, wildfire, parks, sustainability, infrastructure
- policy: Service changes, regulations, programs affecting many residents
- tax: New taxes, fee changes, assessment districts

ITEM TYPE CLASSIFICATION:
- action: Council deliberated and took a formal vote (approval, denial, adoption)
- consent: Routine item approved in batch without individual discussion
- hearing: Public hearing with formal testimony period (land use, zoning, taxes)
- presentation: Staff or external informational report, no vote taken
- discussion: Policy discussion, study session — council may give direction but no formal action

OUTCOME RULES:
- action/consent/hearing: "approved", "denied", "continued", "withdrawn", "adopted"
- presentation: "received"
- discussion: "received" (or "continued" if returning to a future meeting)

PROJECT TYPE TAXONOMY:
housing, transportation, environment, budget, education, development, public_safety, community, elections, governance

STAKES SCORE RUBRIC:
- 10: Citywide impact, $1M+ budget, affects all/most residents
- 8-9: Major neighborhood/district impact, $500K-$1M budget
- 6-7: Significant local impact, $100K-$500K budget, affects 1,000+ residents
- 4-5: Moderate impact, <$100K budget, affects 100-1,000 residents
- 1-3: Low impact, minimal budget, affects <100 residents

IMPORTANT:
- Return ALL high-stakes items found (can be 0, 1, 5, or more)
- Include ALL high-stakes items but classify each item's type accurately
- Extract actual NUMBERS from text (budget amounts, unit counts)
- Skip purely procedural items (minutes approval, roll call)
- If NO high-stakes items found, return: {{"items": []}}
- DOUBLE-CHECK: Did you include EVERY item with budget >= ${min_budget:,}?

Return JSON with items array:"""

        try:
            # Use higher token limit for multiple items
            response_text = self._call_llm(prompt, max_tokens=4000)
            result = self._safe_json_parse(response_text)
            if not result or 'items' not in result or not result['items']:
                return []

            # Convert to HighStakesDecision objects
            decisions = []
            meeting_date = event.get('when_iso', event.get('when_human', 'Unknown'))
            agenda_url = self._get_agenda_url(event)

            for item_data in result['items']:
                # Only include if truly high-stakes
                if not item_data.get('is_high_stakes', False):
                    continue

                item_type = item_data.get('item_type', 'action')
                extracted_outcome = item_data.get('outcome')
                if item_type in ('presentation', 'discussion'):
                    passed_value = None
                else:
                    passed_value = extracted_outcome in ('approved', 'adopted') if extracted_outcome else None

                decision = HighStakesDecision(
                    item_ref=item_data.get('item_ref', 'unknown'),
                    title=item_data.get('title', ''),
                    description=item_data.get('description', ''),
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    is_high_stakes=True,
                    stakes_score=item_data.get('stakes_score', 6),
                    decision_type=item_data.get('decision_type', 'policy'),
                    item_type=item_type,
                    extracted_outcome=extracted_outcome,
                    budget_amount=item_data.get('budget_amount'),
                    budget_description=item_data.get('budget_description', ''),
                    affected_population_estimate=item_data.get('affected_population_estimate'),
                    geographic_scope=item_data.get('geographic_scope', 'unknown'),
                    project_size_units=item_data.get('project_size_units'),
                    project_location=item_data.get('project_location'),
                    project_types=item_data.get('project_types', ['governance']),
                    keywords_for_matching=item_data.get('keywords_for_matching', []),
                    participation_mechanisms=event.get('participation_mechanisms', []),
                    agenda_url=agenda_url,
                    staff_report_url=None,
                    passed=passed_value,
                )
                decisions.append(decision)

            return decisions

        except Exception as e:
            # Don't swallow authentication errors — these are non-transient
            # and the meeting should NOT be marked as "extracted"
            if "Auth" in type(e).__name__:
                raise
            logger.warning(f"LLM extraction failed: {type(e).__name__}: {e}")
            return []

    def _scan_for_budget_amounts(
        self,
        text_content: str,
        min_budget: int = 100000
    ) -> List[Tuple[float, str]]:
        """
        Scan text for dollar amounts >= min_budget using regex.

        Returns list of (amount, context) tuples where context is
        surrounding text for identification.
        """
        # Match dollar amounts: $1,234,567 or $1234567 or $1.2M etc
        # Pattern handles: $675,221 | $1,207,200 | $4.4M | $25 million
        patterns = [
            # Standard format: $1,234,567 or $1,234,567.89
            r'\$[\d,]+(?:\.\d{2})?',
            # Millions shorthand: $4.4M, $25M
            r'\$[\d.]+\s*[Mm](?:illion)?',
            # Written out: $25 million
            r'\$[\d.]+\s+million',
        ]

        found_amounts = []

        for pattern in patterns:
            for match in re.finditer(pattern, text_content, re.IGNORECASE):
                amount_str = match.group()

                # Parse the amount
                try:
                    # Remove $ and commas
                    cleaned = amount_str.replace('$', '').replace(',', '').strip()

                    # Handle millions shorthand
                    if 'million' in cleaned.lower() or cleaned.lower().endswith('m'):
                        cleaned = re.sub(r'[Mm](?:illion)?', '', cleaned).strip()
                        amount = float(cleaned) * 1_000_000
                    else:
                        amount = float(cleaned)

                    if amount >= min_budget:
                        # Get surrounding context (100 chars before/after)
                        start = max(0, match.start() - 100)
                        end = min(len(text_content), match.end() + 100)
                        context = text_content[start:end].replace('\n', ' ').strip()

                        found_amounts.append((amount, context))
                except (ValueError, AttributeError):
                    continue

        # Deduplicate by amount (keep first context for each unique amount)
        seen_amounts = set()
        unique_amounts = []
        for amount, context in found_amounts:
            # Round to avoid float precision issues
            rounded = round(amount, 2)
            if rounded not in seen_amounts:
                seen_amounts.add(rounded)
                unique_amounts.append((rounded, context))

        return sorted(unique_amounts, key=lambda x: x[0], reverse=True)

    def _detect_extraction_gaps(
        self,
        extracted_decisions: List[HighStakesDecision],
        scanned_amounts: List[Tuple[float, str]],
        tolerance: float = 0.1
    ) -> List[Tuple[float, str]]:
        """
        Compare extracted budget amounts vs scanned amounts to find gaps.

        Returns list of (amount, context) for amounts found in text but
        not in extracted decisions.
        """
        # Get all extracted budget amounts
        extracted_amounts = set()
        for d in extracted_decisions:
            if d.budget_amount:
                extracted_amounts.add(round(d.budget_amount, 2))

        # Find gaps: amounts in text but not extracted
        gaps = []
        for amount, context in scanned_amounts:
            # Check if this amount (within tolerance) was extracted
            found = False
            for extracted in extracted_amounts:
                # Allow 10% tolerance for rounding differences
                if abs(amount - extracted) / max(amount, 1) < tolerance:
                    found = True
                    break

            if not found:
                gaps.append((amount, context))

        return gaps

    def _extract_targeted(
        self,
        text_content: str,
        missed_amounts: List[Tuple[float, str]],
        event: Dict[str, Any],
        meeting_type: str
    ) -> List[HighStakesDecision]:
        """
        Targeted extraction for specific missed budget items.

        Uses the context around missed amounts to prompt LLM for extraction.
        """
        if not missed_amounts:
            return []

        # Format missed items for prompt
        missed_items_text = "\n".join([
            f"- ${amount:,.0f}: ...{context}..."
            for amount, context in missed_amounts[:5]  # Limit to top 5
        ])

        safe_title = html.escape(str(event.get('title', 'Unknown'))[:200])
        safe_date = html.escape(str(event.get('when_human', 'Unknown'))[:100])

        prompt = f"""The following budget items were found in a municipal agenda but may have been missed in initial extraction.

Meeting: {safe_title}
Date: {safe_date}

MISSED BUDGET ITEMS TO EXTRACT:
{missed_items_text}

For EACH item above, find the corresponding agenda item and extract:
{{
    "items": [
        {{
            "item_ref": "agenda item reference",
            "title": "item title",
            "description": "what this budget is for",
            "is_high_stakes": true,
            "stakes_score": 6-10,
            "decision_type": "budget",
            "item_type": "action|consent|presentation|hearing|discussion",
            "outcome": "approved|denied|continued|withdrawn|received|adopted",
            "budget_amount": dollar amount as number,
            "budget_description": "purpose of budget",
            "project_types": ["relevant", "types"],
            "keywords_for_matching": ["keywords"]
        }}
    ]
}}

ITEM TYPE: action=formal vote, consent=batch approval, hearing=public hearing, presentation=informational report, discussion=study session
OUTCOME: action/consent/hearing use approved/denied/continued/withdrawn/adopted. presentation/discussion use "received".

Return JSON with items array. If an item cannot be found or isn't a decision, omit it."""

        try:
            response_text = self._call_llm(prompt, max_tokens=2000)
            result = self._safe_json_parse(response_text)
            if not result or 'items' not in result:
                return []

            decisions = []
            meeting_date = event.get('when_iso', event.get('when_human', 'Unknown'))
            agenda_url = self._get_agenda_url(event)

            for item_data in result['items']:
                if not item_data.get('is_high_stakes', False):
                    continue

                item_type = item_data.get('item_type', 'action')
                extracted_outcome = item_data.get('outcome')
                if item_type in ('presentation', 'discussion'):
                    passed_value = None
                else:
                    passed_value = extracted_outcome in ('approved', 'adopted') if extracted_outcome else None

                decision = HighStakesDecision(
                    item_ref=item_data.get('item_ref', 'unknown'),
                    title=item_data.get('title', ''),
                    description=item_data.get('description', ''),
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    is_high_stakes=True,
                    stakes_score=item_data.get('stakes_score', 6),
                    decision_type=item_data.get('decision_type', 'budget'),
                    item_type=item_type,
                    extracted_outcome=extracted_outcome,
                    budget_amount=item_data.get('budget_amount'),
                    budget_description=item_data.get('budget_description', ''),
                    affected_population_estimate=item_data.get('affected_population_estimate'),
                    geographic_scope=item_data.get('geographic_scope', 'unknown'),
                    project_size_units=item_data.get('project_size_units'),
                    project_location=item_data.get('project_location'),
                    project_types=item_data.get('project_types', ['budget']),
                    keywords_for_matching=item_data.get('keywords_for_matching', []),
                    participation_mechanisms=event.get('participation_mechanisms', []),
                    agenda_url=agenda_url,
                    staff_report_url=None,
                    passed=passed_value,
                )
                decisions.append(decision)

            return decisions

        except Exception as e:
            if "Auth" in type(e).__name__:
                raise
            logger.warning(f"Targeted extraction failed: {type(e).__name__}: {e}")
            return []

    def _extract_from_item(
        self,
        item_ref: str,
        item_text: str,
        event: Dict[str, Any],
        meeting_type: str,
        min_budget: int
    ) -> List[HighStakesDecision]:
        """Extract high-stakes decision from a single agenda item"""

        # Sanitize inputs (no truncation now!)
        safe_title = html.escape(str(event.get('title', 'Unknown'))[:200])
        safe_date = html.escape(str(event.get('when_human', 'Unknown'))[:100])
        safe_meeting_type = html.escape(meeting_type)
        safe_item_ref = html.escape(item_ref)
        safe_item_text = html.escape(item_text[:50000])  # 50K per item (generous)

        prompt = f"""Analyze this single agenda item to determine if it's a HIGH-STAKES decision.

Meeting: {safe_title}
Date: {safe_date}
Meeting Type: {safe_meeting_type}
Item: {safe_item_ref}

ITEM TEXT:
{safe_item_text}

OBJECTIVE: Extract decisions with significant community impact for coordination gap analysis.

HIGH-STAKES CRITERIA (flag if ANY apply):
1. Budget decisions >${min_budget:,}:
   - Supplemental appropriations
   - Capital projects
   - Grant allocations
   - Major contract approvals
   - EXTRACT SPECIFIC DOLLAR AMOUNTS from text

2. Development decisions:
   - Residential projects >20 units
   - Major commercial developments
   - Zoning amendments affecting multiple parcels
   - EXTRACT PROJECT SIZE (# units) from text

3. Environmental/policy decisions affecting >1,000 residents:
   - Climate action policies
   - Vegetation/wildfire management programs
   - Water/infrastructure projects
   - Service changes

4. Tax/fee decisions:
   - New taxes or tax increases
   - Fee structure changes
   - Special assessment districts

For each high-stakes item, extract:
{{
    "items": [
        {{
            "item_ref": "item number from agenda",
            "title": "clear, specific title",
            "description": "detailed description (2-3 sentences) - include WHO, WHAT, WHY",
            "is_high_stakes": true,
            "stakes_score": 1-10 (1=low impact, 10=citywide major impact),
            "decision_type": "budget|development|environmental|policy|tax",
            "item_type": "action|consent|presentation|hearing|discussion",
            "outcome": "approved|denied|continued|withdrawn|received|adopted",

            "budget_amount": dollar amount as number (e.g., 1108319 for $1.1M) or null,
            "budget_description": "what the budget is for" or null,
            "affected_population_estimate": rough number of residents affected or null,
            "geographic_scope": "citywide|neighborhood|specific_location",

            "project_size_units": number of housing units (development only) or null,
            "project_location": "street address or area name" or null,

            "project_types": ["primary_type", "secondary_type"],
            "keywords_for_matching": ["keyword1", "keyword2", "keyword3"],

            "staff_report_mentioned": true/false,
            "public_hearing": true/false
        }}
    ]
}}

DECISION TYPE CLASSIFICATION:
- budget: Appropriations, contracts, grants, capital projects
- development: Housing/commercial construction, zoning changes, land use
- environmental: Climate, wildfire, parks, sustainability, infrastructure
- policy: Service changes, regulations, programs affecting many residents
- tax: New taxes, fee changes, assessment districts

PROJECT TYPE TAXONOMY (same as existing system):
- housing: residential development, zoning, use permits, land use, affordability
- transportation: transit, roads, bike lanes, parking
- environment: parks, climate, wildfire, vegetation, water quality
- budget: appropriations, taxes, fees, bonds, fiscal planning
- education: schools, libraries, youth programs
- development: commercial development, economic development, business
- public_safety: police, fire operations, emergency services
- community: social services, health, recreation, arts
- elections: voting, ballot measures, districts
- governance: procedural, administrative, appointments

KEYWORDS FOR MATCHING (for SeeClickFix complaint matching):
- Extract 5-10 keywords that residents might use when complaining
- Examples:
  - Budget for wildfire → ["fire", "wildfire", "tree", "vegetation", "hazard"]
  - Housing project on Oak St → ["oak street", "traffic", "parking", "construction", "development"]
  - Stormwater project → ["flooding", "drainage", "stormwater", "water"]

STAKES SCORE RUBRIC:
- 10: Citywide impact, $1M+ budget, affects all/most residents
- 8-9: Major neighborhood/district impact, $500K-$1M budget
- 6-7: Significant local impact, $100K-$500K budget, affects 1,000+ residents
- 4-5: Moderate impact, <$100K budget, affects 100-1,000 residents
- 1-3: Low impact, minimal budget, affects <100 residents

ITEM TYPE CLASSIFICATION:
- action: Council deliberated and took a formal vote (approval, denial, adoption)
- consent: Routine item approved in batch without individual discussion
- hearing: Public hearing with formal testimony period (land use, zoning, taxes)
- presentation: Staff or external informational report, no vote taken
- discussion: Policy discussion, study session — council may give direction but no formal action

OUTCOME RULES:
- action/consent/hearing: "approved", "denied", "continued", "withdrawn", "adopted"
- presentation: "received"
- discussion: "received" (or "continued" if returning to a future meeting)

IMPORTANT:
- Return SINGLE decision for THIS item only
- Include ALL high-stakes items but classify each item's type accurately
- Extract NUMBERS from text (budget amounts, unit counts, population)
- Skip purely procedural items (minutes approval, appointments)
- If NOT high-stakes, return empty items array: {{"items": []}}

Return JSON format:
{{
    "items": [
        {{
            "item_ref": "{safe_item_ref}",
            "title": "...",
            "description": "...",
            "is_high_stakes": true/false,
            "stakes_score": 1-10,
            "decision_type": "budget|development|environmental|policy|tax",
            "budget_amount": number or null,
            "budget_description": "..." or null,
            "affected_population_estimate": number or null,
            "geographic_scope": "citywide|neighborhood|specific_location",
            "project_size_units": number or null,
            "project_location": "..." or null,
            "project_types": ["type1", "type2"],
            "keywords_for_matching": ["keyword1", "keyword2", ...]
        }}
    ]
}}

PROJECT TYPES: housing, transportation, environment, budget, education, development, public_safety, community, elections, governance
"""

        try:
            response_text = self._call_llm(prompt, max_tokens=2000)
            result = self._safe_json_parse(response_text)
            if not result or 'items' not in result or not result['items']:
                return []

            # Convert to HighStakesDecision objects
            decisions = []
            meeting_date = event.get('when_iso', event.get('when_human', 'Unknown'))
            agenda_url = self._get_agenda_url(event)

            for item_data in result['items']:
                # Only include if truly high-stakes
                if not item_data.get('is_high_stakes', False):
                    continue

                item_type = item_data.get('item_type', 'action')
                extracted_outcome = item_data.get('outcome')
                if item_type in ('presentation', 'discussion'):
                    passed_value = None
                else:
                    passed_value = extracted_outcome in ('approved', 'adopted') if extracted_outcome else None

                # Build HighStakesDecision object
                decision = HighStakesDecision(
                    item_ref=item_data.get('item_ref', item_ref),  # Use extracted ref
                    title=item_data.get('title', ''),
                    description=item_data.get('description', ''),
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    is_high_stakes=True,
                    stakes_score=item_data.get('stakes_score', 6),
                    decision_type=item_data.get('decision_type', 'policy'),
                    item_type=item_type,
                    extracted_outcome=extracted_outcome,
                    budget_amount=item_data.get('budget_amount'),
                    budget_description=item_data.get('budget_description', ''),
                    affected_population_estimate=item_data.get('affected_population_estimate'),
                    geographic_scope=item_data.get('geographic_scope', 'unknown'),
                    project_size_units=item_data.get('project_size_units'),
                    project_location=item_data.get('project_location'),
                    project_types=item_data.get('project_types', ['governance']),
                    keywords_for_matching=item_data.get('keywords_for_matching', []),
                    participation_mechanisms=event.get('participation_mechanisms', []),
                    agenda_url=agenda_url,
                    staff_report_url=None,
                    passed=passed_value,
                )

                decisions.append(decision)

            return decisions

        except Exception as e:
            # Silent failure for individual items (too noisy otherwise)
            return []

    def analyze_meeting_batch(
        self,
        events: List[Dict[str, Any]],
        min_budget: int = 100000,
        min_stakes_score: int = 6
    ) -> Dict[str, Any]:
        """
        Analyze batch of meetings for high-stakes decisions

        Returns:
            {
                "meetings_analyzed": count,
                "high_stakes_decisions": [HighStakesDecision, ...],
                "decision_types_breakdown": {...},
                "total_budget_amount": float,
                "by_meeting_type": {...}
            }
        """
        all_decisions = []
        decision_types = {}
        by_meeting_type = {}
        total_budget = 0.0

        for i, event in enumerate(events, 1):
            print(f"\n📋 Analyzing meeting {i}/{len(events)}: {event.get('title', 'Unknown')}")

            decisions = self.extract_high_stakes_decisions(
                event,
                min_budget=min_budget,
                min_stakes_score=min_stakes_score
            )

            if decisions:
                print(f"   ✅ Found {len(decisions)} high-stakes decisions")
                all_decisions.extend(decisions)

                # Aggregate statistics
                for decision in decisions:
                    # Count by decision type
                    dtype = decision.decision_type
                    decision_types[dtype] = decision_types.get(dtype, 0) + 1

                    # Count by meeting type
                    mtype = decision.meeting_type
                    by_meeting_type[mtype] = by_meeting_type.get(mtype, 0) + 1

                    # Sum budgets
                    if decision.budget_amount:
                        total_budget += decision.budget_amount
            else:
                print(f"   ⚠️  No high-stakes decisions found")

        return {
            "meetings_analyzed": len(events),
            "high_stakes_decisions": [d.to_dict() for d in all_decisions],
            "decision_count": len(all_decisions),
            "decision_types_breakdown": decision_types,
            "total_budget_amount": total_budget,
            "by_meeting_type": by_meeting_type,
            "extraction_timestamp": datetime.now().isoformat()
        }


def analyze_jurisdiction_retrospective(
    jurisdiction_id: str,
    start_date: str,
    end_date: str,
    output_file: Optional[str] = None,
    min_budget: int = 100000,
    min_stakes_score: int = 6
) -> Dict[str, Any]:
    """
    Analyze all meetings for a jurisdiction in date range

    Args:
        jurisdiction_id: e.g., "san-rafael"
        start_date: ISO date string "2024-11-01"
        end_date: ISO date string "2025-11-01"
        output_file: Optional path to save results
        min_budget: Minimum budget threshold
        min_stakes_score: Minimum stakes score (1-10)

    Returns:
        Analysis results dict
    """
    import glob
    from datetime import datetime

    # Find all event files for jurisdiction
    pattern = f"data/events/events_{jurisdiction_id}_*.json"
    event_files = glob.glob(pattern)

    if not event_files:
        print(f"⚠️  No event files found for {jurisdiction_id}")
        return {"error": "No event files found"}

    # Load and filter events by date range
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)

    all_events = []
    for event_file in event_files:
        with open(event_file, 'r') as f:
            data = json.load(f)
            events = data.get('events', [])

            # Filter by date range
            for event in events:
                event_date_str = event.get('when_iso', '')
                if event_date_str:
                    try:
                        event_date = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
                        if start_dt <= event_date <= end_dt:
                            all_events.append(event)
                    except:
                        pass

    print(f"\n📊 Found {len(all_events)} meetings for {jurisdiction_id} between {start_date} and {end_date}")

    if not all_events:
        return {"error": "No meetings in date range"}

    # Run retrospective analysis
    analyzer = RetrospectiveAnalyzer()
    results = analyzer.analyze_meeting_batch(
        all_events,
        min_budget=min_budget,
        min_stakes_score=min_stakes_score
    )

    # Add metadata
    results['jurisdiction_id'] = jurisdiction_id
    results['date_range'] = {
        "start": start_date,
        "end": end_date
    }

    # Save if output file specified
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n✅ Results saved to {output_file}")

    return results


if __name__ == "__main__":
    """Test retrospective analysis on San Rafael"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python retrospective_analyzer.py <jurisdiction_id> [start_date] [end_date] [output_file]")
        print("Example: python retrospective_analyzer.py san-rafael 2024-11-01 2025-11-01 data/pilot/san_rafael_decisions.json")
        sys.exit(1)

    jurisdiction = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-11-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2025-11-01"
    output = sys.argv[4] if len(sys.argv) > 4 else f"data/pilot/{jurisdiction}_high_stakes_decisions.json"

    results = analyze_jurisdiction_retrospective(
        jurisdiction_id=jurisdiction,
        start_date=start,
        end_date=end,
        output_file=output
    )

    # Print summary
    if 'error' not in results:
        print(f"\n📊 ANALYSIS SUMMARY")
        print(f"   Meetings analyzed: {results['meetings_analyzed']}")
        print(f"   High-stakes decisions: {results['decision_count']}")
        print(f"   Total budget: ${results['total_budget_amount']:,.0f}")
        print(f"\n   By decision type:")
        for dtype, count in results['decision_types_breakdown'].items():
            print(f"     - {dtype}: {count}")
        print(f"\n   By meeting type:")
        for mtype, count in results['by_meeting_type'].items():
            print(f"     - {mtype}: {count}")
