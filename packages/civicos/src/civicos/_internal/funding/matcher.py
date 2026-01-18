"""
Funding source matcher for linking budget items to federal/state funding sources.

SESSION 444: Budget-funding source linking implementation.

This module provides:
- CFDA number extraction from budget item text (program name, notes)
- Program name text matching between budget items and federal/state programs
- Match confidence scoring
- Link generation for storage in budget_funding_source_links table

CFDA numbers (Catalog of Federal Domestic Assistance) are the primary identifier
for federal programs. Example: 14.218 is Community Development Block Grant (CDBG).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
import hashlib


@dataclass
class Match:
    """Represents a potential match between a budget item and funding source."""
    budget_item_id: str
    federal_award_id: Optional[str] = None
    federal_cfda_number: Optional[str] = None
    passthrough_id: Optional[str] = None
    state_grant_id: Optional[str] = None
    match_type: str = "unknown"
    match_confidence: float = 0.0
    match_source: str = "unknown"
    match_notes: str = ""
    budget_cents: Optional[int] = None
    federal_cents: Optional[int] = None
    local_cents: Optional[int] = None

    def to_link(self, jurisdiction_id: str) -> Dict[str, Any]:
        """Convert match to a link dictionary for storage."""
        # Generate deterministic link_id from components
        components = f"{jurisdiction_id}:{self.budget_item_id}:{self.federal_cfda_number or ''}:{self.passthrough_id or ''}"
        link_id = hashlib.md5(components.encode()).hexdigest()[:16]

        return {
            "link_id": f"link-{link_id}",
            "budget_item_id": self.budget_item_id,
            "federal_award_id": self.federal_award_id,
            "federal_cfda_number": self.federal_cfda_number,
            "passthrough_id": self.passthrough_id,
            "state_grant_id": self.state_grant_id,
            "match_type": self.match_type,
            "match_confidence": self.match_confidence,
            "match_source": self.match_source,
            "match_notes": self.match_notes,
            "budget_cents": self.budget_cents,
            "federal_cents": self.federal_cents,
            "local_cents": self.local_cents,
            "reconciliation_status": self._calc_reconciliation(),
            "variance_cents": self._calc_variance_cents(),
            "variance_percentage": self._calc_variance_pct(),
        }

    def _calc_reconciliation(self) -> str:
        """Calculate reconciliation status based on amounts."""
        if self.budget_cents is None:
            return "unverified"

        compare_cents = self.local_cents or self.federal_cents
        if compare_cents is None:
            return "unverified"

        variance_pct = abs(self.budget_cents - compare_cents) / compare_cents * 100 if compare_cents > 0 else 0

        if variance_pct < 1.0:
            return "match"
        elif variance_pct < 10.0:
            return "variance"
        else:
            return "unverified"

    def _calc_variance_cents(self) -> Optional[int]:
        """Calculate variance in cents."""
        if self.budget_cents is None:
            return None
        compare_cents = self.local_cents or self.federal_cents
        if compare_cents is None:
            return None
        return self.budget_cents - compare_cents

    def _calc_variance_pct(self) -> Optional[float]:
        """Calculate variance percentage, capped at +/-999.99 for database storage."""
        compare_cents = self.local_cents or self.federal_cents
        if compare_cents is None or compare_cents == 0:
            return None
        variance = self._calc_variance_cents()
        if variance is None:
            return None
        pct = round((variance / compare_cents) * 100, 2)
        # Cap to database NUMERIC(5,2) limit
        return max(-999.99, min(999.99, pct))


# Common CFDA patterns in budget text
# CFDA numbers are format: XX.XXX (2 digits, period, 3 digits)
CFDA_PATTERN = re.compile(r'\b(\d{2}\.\d{3})\b')

# Common program name to CFDA mappings
# These are the most common federal programs for local governments
PROGRAM_CFDA_MAP: Dict[str, str] = {
    # HUD Programs (14.xxx)
    "cdbg": "14.218",
    "community development block grant": "14.218",
    "home": "14.239",
    "home investment partnership": "14.239",
    "section 8": "14.871",
    "housing choice voucher": "14.871",
    "emergency solutions grant": "14.231",
    "esg": "14.231",
    "continuum of care": "14.267",
    "coc": "14.267",

    # DOT Programs (20.xxx)
    "highway planning": "20.205",
    "stbg": "20.205",  # Surface Transportation Block Grant
    "cmaq": "20.507",  # Congestion Mitigation and Air Quality
    "transit": "20.507",
    "federal transit administration": "20.507",

    # EPA Programs (66.xxx)
    "clean water state revolving fund": "66.458",
    "drinking water state revolving fund": "66.468",

    # FEMA Programs (97.xxx)
    "hazard mitigation": "97.039",
    "fire prevention": "97.044",
    "staffing for adequate fire": "97.083",
    "safer": "97.083",
    "assistance to firefighters": "97.044",
    "afg": "97.044",
    "bric": "97.047",
    "building resilient infrastructure": "97.047",

    # DOJ Programs (16.xxx)
    "cops": "16.710",
    "community oriented policing": "16.710",
    "jag": "16.738",
    "justice assistance grant": "16.738",
    "byrne jag": "16.738",

    # HHS Programs (93.xxx)
    "head start": "93.600",
    "community services block grant": "93.569",
    "csbg": "93.569",
    "low income home energy": "93.568",
    "liheap": "93.568",
}


def extract_cfda_numbers(text: str) -> List[str]:
    """
    Extract CFDA numbers from text.

    Args:
        text: Text to search (budget line item, program name, notes)

    Returns:
        List of CFDA numbers found (format: "XX.XXX")

    Examples:
        >>> extract_cfda_numbers("CDBG Grant (14.218)")
        ['14.218']
        >>> extract_cfda_numbers("Highway grants 20.205 and transit 20.507")
        ['20.205', '20.507']
    """
    if not text:
        return []
    return CFDA_PATTERN.findall(text)


def _match_program_name(text: str) -> Optional[str]:
    """
    Match program name keywords to CFDA numbers.

    Args:
        text: Text to search for program keywords

    Returns:
        CFDA number if program keyword found, None otherwise
    """
    if not text:
        return None

    text_lower = text.lower()
    for keyword, cfda in PROGRAM_CFDA_MAP.items():
        if keyword in text_lower:
            return cfda
    return None


class FundingMatcher:
    """
    Matches budget items to federal/state funding sources.

    This class implements a multi-stage matching strategy:
    1. Exact CFDA match (highest confidence) - CFDA number in budget item text
    2. Program name match - Known program names mapped to CFDA
    3. State grant ID match - State grant identifier in budget notes
    4. Text similarity (lowest confidence) - Fuzzy matching of descriptions

    The matcher generates Match objects that can be converted to links
    for storage in the budget_funding_source_links table.
    """

    def __init__(
        self,
        federal_awards: Optional[List[Dict[str, Any]]] = None,
        state_passthroughs: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize the matcher with federal and state funding data.

        Args:
            federal_awards: List of federal award dicts from storage
            state_passthroughs: List of state passthrough dicts from storage
        """
        self._federal_awards = federal_awards or []
        self._state_passthroughs = state_passthroughs or []

        # Build lookup indexes
        self._federal_by_cfda: Dict[str, List[Dict[str, Any]]] = {}
        for award in self._federal_awards:
            cfda = award.get("cfda_number")
            if cfda:
                if cfda not in self._federal_by_cfda:
                    self._federal_by_cfda[cfda] = []
                self._federal_by_cfda[cfda].append(award)

        self._passthrough_by_cfda: Dict[str, List[Dict[str, Any]]] = {}
        self._passthrough_by_grant_id: Dict[str, Dict[str, Any]] = {}
        for pt in self._state_passthroughs:
            cfda = pt.get("federal_cfda_number")
            if cfda:
                if cfda not in self._passthrough_by_cfda:
                    self._passthrough_by_cfda[cfda] = []
                self._passthrough_by_cfda[cfda].append(pt)

            grant_id = pt.get("state_grant_id")
            if grant_id:
                self._passthrough_by_grant_id[grant_id] = pt

    def match_budget_item(self, budget_item: Dict[str, Any]) -> List[Match]:
        """
        Find funding source matches for a budget item.

        Uses multi-stage matching:
        1. Extract CFDA from budget text (confidence: 0.95)
        2. Match program name to known CFDA (confidence: 0.80)
        3. Match state grant ID (confidence: 0.85)

        Args:
            budget_item: Budget item dict with keys:
                - id or item_id: Unique identifier
                - program: Program name
                - line_item: Line item description
                - notes: Additional notes
                - budgeted_cents: Amount in cents

        Returns:
            List of Match objects, sorted by confidence descending
        """
        matches: List[Match] = []

        # Prefer item_id (semantic identifier) over id (row number)
        item_id = budget_item.get("item_id") or budget_item.get("id")
        if not item_id:
            return matches

        budget_cents = budget_item.get("budgeted_cents")

        # Combine searchable text
        search_text = " ".join([
            budget_item.get("program") or "",
            budget_item.get("line_item") or "",
            budget_item.get("notes") or "",
        ])

        # Stage 1: Extract CFDA numbers directly from text
        cfda_numbers = extract_cfda_numbers(search_text)
        for cfda in cfda_numbers:
            match = self._match_cfda(item_id, cfda, budget_cents, confidence=0.95)
            if match:
                match.match_notes = f"CFDA {cfda} extracted from budget text"
                matches.append(match)

        # Stage 2: Match program names to known CFDA
        matched_cfda = _match_program_name(search_text)
        if matched_cfda and matched_cfda not in cfda_numbers:
            match = self._match_cfda(item_id, matched_cfda, budget_cents, confidence=0.80)
            if match:
                # Find which keyword matched
                text_lower = search_text.lower()
                for keyword, cfda in PROGRAM_CFDA_MAP.items():
                    if cfda == matched_cfda and keyword in text_lower:
                        match.match_notes = f"Program keyword '{keyword}' matched to CFDA {cfda}"
                        break
                matches.append(match)

        # Stage 3: Look for state grant IDs in notes
        notes = budget_item.get("notes") or ""
        for grant_id, passthrough in self._passthrough_by_grant_id.items():
            if grant_id.lower() in notes.lower():
                match = Match(
                    budget_item_id=item_id,
                    passthrough_id=passthrough.get("passthrough_id"),
                    state_grant_id=grant_id,
                    federal_cfda_number=passthrough.get("federal_cfda_number"),
                    match_type="state_grant_id",
                    match_confidence=0.85,
                    match_source="text_extraction",
                    match_notes=f"State grant ID '{grant_id}' found in budget notes",
                    budget_cents=budget_cents,
                    local_cents=passthrough.get("local_amount_cents"),
                    federal_cents=passthrough.get("federal_amount_cents"),
                )
                matches.append(match)

        # Sort by confidence descending
        matches.sort(key=lambda m: m.match_confidence, reverse=True)
        return matches

    def _match_cfda(
        self,
        item_id: str,
        cfda: str,
        budget_cents: Optional[int],
        confidence: float,
    ) -> Optional[Match]:
        """
        Create a match for a CFDA number.

        Looks up federal awards and state passthroughs for the CFDA.
        Prioritizes state passthrough if available (more specific to local gov).
        """
        # Check state passthroughs first (more specific)
        passthroughs = self._passthrough_by_cfda.get(cfda, [])
        if passthroughs:
            pt = passthroughs[0]  # Use first match
            return Match(
                budget_item_id=item_id,
                passthrough_id=pt.get("passthrough_id"),
                federal_cfda_number=cfda,
                state_grant_id=pt.get("state_grant_id"),
                match_type="cfda_passthrough",
                match_confidence=confidence,
                match_source="cfda_extraction",
                budget_cents=budget_cents,
                local_cents=pt.get("local_amount_cents"),
                federal_cents=pt.get("federal_amount_cents"),
            )

        # Fall back to federal awards
        awards = self._federal_by_cfda.get(cfda, [])
        if awards:
            award = awards[0]  # Use first match
            return Match(
                budget_item_id=item_id,
                federal_award_id=award.get("award_id"),
                federal_cfda_number=cfda,
                match_type="cfda_federal",
                match_confidence=confidence,
                match_source="cfda_extraction",
                budget_cents=budget_cents,
                federal_cents=award.get("amount_cents"),
            )

        # No award/passthrough data, but we found a CFDA
        return Match(
            budget_item_id=item_id,
            federal_cfda_number=cfda,
            match_type="cfda_only",
            match_confidence=confidence * 0.9,  # Slightly lower without award data
            match_source="cfda_extraction",
            budget_cents=budget_cents,
        )

    def match_all(
        self,
        budget_items: List[Dict[str, Any]],
        min_confidence: float = 0.5,
    ) -> List[Match]:
        """
        Match all budget items to funding sources.

        Args:
            budget_items: List of budget item dicts
            min_confidence: Minimum confidence threshold (default 0.5)

        Returns:
            List of all matches above the confidence threshold
        """
        all_matches: List[Match] = []
        for item in budget_items:
            matches = self.match_budget_item(item)
            for match in matches:
                if match.match_confidence >= min_confidence:
                    all_matches.append(match)
        return all_matches

    def generate_links(
        self,
        budget_items: List[Dict[str, Any]],
        jurisdiction_id: str,
        min_confidence: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Generate link dictionaries ready for storage.

        Args:
            budget_items: List of budget item dicts
            jurisdiction_id: Target jurisdiction
            min_confidence: Minimum confidence threshold

        Returns:
            List of link dicts ready for store_budget_funding_links()
        """
        matches = self.match_all(budget_items, min_confidence)
        return [match.to_link(jurisdiction_id) for match in matches]
