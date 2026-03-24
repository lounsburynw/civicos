"""
Context Module - what_applies() implementation

Provides regulatory context for topics using storage backends.

Ranking Modes:
- section_first: Rank by individual chunk similarity (default, good for broad queries)
- bill_first: Rank by bill-level max similarity (good for specific bill queries)
- auto: Detect based on query content (uses bill_first if query mentions bill numbers)
"""

import functools
import logging
import re
from typing import Optional, List, Any, Dict, Literal, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from civicos.storage.protocols import StorageBackend
    from civicos.storage.protocols.vector import VectorBackend

# Type alias for ranking mode
RankingMode = Literal["section_first", "bill_first", "auto"]

# Pattern to detect specific bill references in queries
# Matches: SB9, AB 123, HR1234, S. 456, HB 789
BILL_PATTERN = re.compile(r'\b(SB|AB|HR|HB|S\.?)\s*\d+\b', re.IGNORECASE)

# Pattern to detect federal program references in queries
# Matches: CDBG, HOME, LIHTC, ESG, CoC, HUD, FEMA, etc.
PROGRAM_PATTERN = re.compile(
    r'\b(CDBG|HOME|LIHTC|ESG|CoC|HUD|FEMA|USDA|EPA|DOT|HHS|'
    r'Section\s*8|SNAP|TANF|WIC|CHIP|HEAD\s*START|CDFI|'
    r'CARES|ARP|ARPA|IIJA|BIL)\b',
    re.IGNORECASE
)


def _detect_ranking_mode(topic: str) -> Literal["section_first", "bill_first"]:
    """
    Detect appropriate ranking mode based on query content.

    Uses bill_first mode when query mentions specific bill numbers,
    which helps surface the exact bill the user is looking for.

    Args:
        topic: The search query

    Returns:
        "bill_first" if query contains bill numbers, else "section_first"
    """
    if BILL_PATTERN.search(topic):
        return "bill_first"
    return "section_first"


def _extract_bill_numbers(topic: str) -> set:
    """
    Extract bill numbers mentioned in a query for boosting.

    Args:
        topic: The search query

    Returns:
        Set of normalized bill numbers (e.g., {"SB9", "AB123"})
    """
    matches = BILL_PATTERN.findall(topic)
    # BILL_PATTERN captures groups like ('SB', '9') - we need the full match
    # Re-run with a non-capturing pattern to get full matches
    full_matches = re.findall(r'\b((?:SB|AB|HR|HB|S\.?)\s*\d+)\b', topic, re.IGNORECASE)
    # Normalize: remove spaces, uppercase
    return {m.replace(" ", "").replace(".", "").upper() for m in full_matches}


def _extract_program_codes(topic: str) -> set:
    """
    Extract federal program codes mentioned in a query for boosting.

    Args:
        topic: The search query

    Returns:
        Set of normalized program codes (e.g., {"CDBG", "HOME", "LIHTC"})
    """
    matches = PROGRAM_PATTERN.findall(topic)
    # Normalize: remove spaces, uppercase
    return {m.replace(" ", "").upper() for m in matches}


@dataclass
class RegulatoryStack:
    """Regulatory context for a topic."""
    topic: str
    jurisdiction: str
    federal: List[dict] = field(default_factory=list)
    state: List[dict] = field(default_factory=list)
    local: List[dict] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=datetime.now)


# LegiScan status codes and their meanings
STATUS_LABELS = {
    "1": "Introduced",
    "2": "Engrossed",
    "3": "Enrolled",
    "4": "Passed",
    "5": "Vetoed",
    "6": "Failed",
    "Active": "Active",       # Text status from non-LegiScan sources
}

# Status codes that indicate inactive/dead legislation
# Bills with these statuses are excluded by default from semantic search
INACTIVE_STATUS_CODES = {"5", "6"}

# Status filter presets for what_applies()
# Maps filter name to allowed status codes
STATUS_FILTER_PRESETS = {
    "active": {"1", "2", "3", "4", "Active"},  # Exclude vetoed/failed (default)
    "passed": {"4"},                             # Only enacted legislation
    "pending": {"1", "2", "3", "Active"},        # In progress, not yet passed
    "all": {"1", "2", "3", "4", "5", "6", "Active"},  # Include everything
}

# Type alias for legislation status filter
LegislationStatusFilter = Literal["active", "passed", "pending", "all"]


# Map state names/codes to two-letter database codes
STATE_CODE_MAP = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new-hampshire": "NH", "new-jersey": "NJ", "new-mexico": "NM", "new-york": "NY",
    "north-carolina": "NC", "north-dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode-island": "RI", "south-carolina": "SC",
    "south-dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west-virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district-of-columbia": "DC",
    # Two-letter code passthrough
    "al": "AL", "ak": "AK", "az": "AZ", "ar": "AR", "ca": "CA", "co": "CO",
    "ct": "CT", "de": "DE", "fl": "FL", "ga": "GA", "hi": "HI", "id": "ID",
    "il": "IL", "in": "IN", "ia": "IA", "ks": "KS", "ky": "KY", "la": "LA",
    "me": "ME", "md": "MD", "ma": "MA", "mi": "MI", "mn": "MN", "ms": "MS",
    "mo": "MO", "mt": "MT", "ne": "NE", "nv": "NV", "nh": "NH", "nj": "NJ",
    "nm": "NM", "ny": "NY", "nc": "NC", "nd": "ND", "oh": "OH", "ok": "OK",
    "or": "OR", "pa": "PA", "ri": "RI", "sc": "SC", "sd": "SD", "tn": "TN",
    "tx": "TX", "ut": "UT", "vt": "VT", "va": "VA", "wa": "WA", "wv": "WV",
    "wi": "WI", "wy": "WY", "dc": "DC",
}

# Map city jurisdictions to their county (for county code search)
CITY_TO_COUNTY = {
    "city-san-rafael": "county-marin",
    "city-berkeley": "county-alameda",
    "city-oakland": "county-alameda",
}


@functools.lru_cache(maxsize=1)
def _load_jurisdiction_registry() -> dict:
    """Load config/registry.json once and cache for process lifetime."""
    import json as _json
    import os as _os
    here = _os.path.dirname(_os.path.abspath(__file__))
    root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(here))))
    registry_path = _os.path.join(root, "config", "registry.json")
    try:
        with open(registry_path) as f:
            return _json.load(f)
    except (FileNotFoundError, OSError) as e:
        logger.warning(f"Could not load registry.json for state resolution: {e}")
        return {}


def _extract_state_from_jurisdiction(jurisdiction_id: str) -> Optional[str]:
    """Extract state from jurisdiction_id.

    Uses registry parent_jurisdictions to resolve city/county → state.
    Returns None if state cannot be determined (caller should handle).
    """
    if not jurisdiction_id:
        return None

    # state-* jurisdictions: extract directly
    if jurisdiction_id.startswith("state-"):
        return jurisdiction_id[6:]

    # city-*/county-*: look up parent state from registry
    registry = _load_jurisdiction_registry()
    entry = registry.get("jurisdictions", {}).get(jurisdiction_id, {})
    for parent in entry.get("parent_jurisdictions", []):
        if parent.startswith("state-"):
            return parent[6:]

    if entry:
        # Jurisdiction exists in registry but has no state parent — return None
        logger.debug(f"Jurisdiction {jurisdiction_id} has no state parent in registry")
        return None

    # Not in registry at all — log and return None (no silent CA assumption)
    if jurisdiction_id.startswith(("city-", "county-")):
        logger.warning(
            f"Jurisdiction {jurisdiction_id} not found in registry — "
            f"cannot determine state. Add it to config/registry.json."
        )

    return None


def get_regulatory_context(
    jurisdiction: str,
    topic: str,
    location: str = None,
    storage: Optional["StorageBackend"] = None,
    vectors: Optional["VectorBackend"] = None,
    *,
    ranking_mode: RankingMode = "auto",
    max_results: int = 30,
    min_score: float = 0.4,
    legislation_status: LegislationStatusFilter = "active",
) -> RegulatoryStack:
    """
    Get regulatory stack for a topic.

    Uses storage backend for legislation queries and vector backend for
    semantic search of municipal code.

    Args:
        jurisdiction: City/jurisdiction ID
        topic: Topic to search
        location: Optional location for local rules
        storage: Optional storage backend (passed from CivicOS)
        vectors: Optional vector backend (passed from CivicOS)
        ranking_mode: How to rank legislation results:
            - "section_first": Rank by chunk similarity (default for broad queries)
            - "bill_first": Rank by bill-level max score (good for specific bills)
            - "auto": Detect based on query (uses bill_first if query has bill numbers)
        max_results: Maximum bills to return (default 30)
        min_score: Minimum similarity score to include (default 0.4)
        legislation_status: Filter legislation by status:
            - "active": Exclude vetoed/failed (default)
            - "passed": Only enacted legislation (status 4)
            - "pending": In progress bills (status 1-3)
            - "all": Include everything including vetoed/failed

    Returns:
        RegulatoryStack with federal, state, local context
    """
    federal: List[dict] = []
    state: List[dict] = []
    local: List[dict] = []

    # Extract state from jurisdiction
    state_name = _extract_state_from_jurisdiction(jurisdiction)

    if not state_name:
        return RegulatoryStack(
            topic=topic,
            jurisdiction=jurisdiction,
            federal=[{"note": "Unknown jurisdiction state"}],
            state=[{"note": "Unknown jurisdiction state"}],
            local=[{"note": "Local ordinances not yet supported"}],
        )

    state_code = STATE_CODE_MAP.get(state_name.lower(), state_name.upper())

    # Resolve ranking mode
    effective_mode: Literal["section_first", "bill_first"] = (
        _detect_ranking_mode(topic) if ranking_mode == "auto" else ranking_mode
    )

    # Extract mentioned bill numbers for boosting (in bill_first mode)
    mentioned_bills = _extract_bill_numbers(topic) if effective_mode == "bill_first" else set()

    # Get allowed status codes based on filter
    allowed_statuses = STATUS_FILTER_PRESETS.get(legislation_status, STATUS_FILTER_PRESETS["active"])

    # Semantic search for state legislation
    # Searches vector embeddings of bill text to find relevant legislation
    # Returns bill-level metadata AND relevant section excerpts for LLM context
    CHUNK_TOP_K = 100           # Generous chunk retrieval
    CHUNKS_PER_BILL = 3         # Keep top N relevant sections per bill

    if vectors is not None:
        try:
            # Search legislation chunks by semantic similarity
            legislation_jurisdiction = f"legislation-{state_code}"
            results = vectors.search(
                query=topic,
                jurisdiction_id=legislation_jurisdiction,
                corpus_type="legislation",
                top_k=CHUNK_TOP_K,
            )

            # Group chunks by bill_id, keeping top chunks per bill
            bill_chunks: Dict[str, List[dict]] = defaultdict(list)
            bill_max_scores: Dict[str, float] = {}  # Track max score per bill
            local_impl_bills: set[str] = set()  # Bills requiring local implementation

            for result in results:
                if result.score < min_score:
                    continue
                bill_id = result.metadata.get("bill_id", "")
                if not bill_id:
                    continue

                # Filter by legislation status
                status = str(result.metadata.get("status", ""))
                if status and status not in allowed_statuses:
                    continue

                # Track max score for bill-first ranking
                if bill_id not in bill_max_scores or result.score > bill_max_scores[bill_id]:
                    bill_max_scores[bill_id] = result.score

                # Track bills requiring local implementation (for boosting)
                if result.metadata.get("local_implementation_required"):
                    local_impl_bills.add(bill_id)

                if len(bill_chunks[bill_id]) < CHUNKS_PER_BILL:
                    bill_chunks[bill_id].append({
                        "content": result.content[:300] if result.content else "",
                        "score": round(result.score, 3),
                        "chunk_index": result.metadata.get("chunk_index"),
                    })

            # Determine bill ordering based on ranking mode
            if effective_mode == "bill_first":
                # Sort bills by their max chunk score
                # Boost bills explicitly mentioned in the query (add 0.1 to score)
                def bill_sort_key(bid: str) -> float:
                    base_score = bill_max_scores.get(bid, 0)
                    # Boost bills requiring local implementation (most actionable)
                    if bid in local_impl_bills:
                        base_score += 0.15
                    # Extract bill number from bill_id (e.g., "ca-sb9" -> "SB9")
                    bill_num = bid.split("-")[-1].upper() if "-" in bid else bid.upper()
                    # Boost if this bill was mentioned in the query
                    if bill_num in mentioned_bills:
                        base_score += 0.1  # Boost mentioned bills
                    return base_score

                ordered_bill_ids = sorted(
                    bill_chunks.keys(),
                    key=bill_sort_key,
                    reverse=True
                )[:max_results]
            else:
                # section_first: preserve insertion order (first seen = highest chunk)
                ordered_bill_ids = list(bill_chunks.keys())[:max_results]

            # Batch fetch bill metadata from storage (single query)
            bill_metadata: Dict[str, dict] = {}
            if storage is not None and ordered_bill_ids:
                try:
                    bill_metadata = storage.get_legislation_batch(
                        state=state_code,
                        bill_ids=ordered_bill_ids,
                    )
                except Exception:
                    pass  # Batch fetch not available, continue without metadata

            # Build hierarchical results with tier assignment
            rank = 0
            for bill_id in ordered_bill_ids:
                chunks = bill_chunks[bill_id]
                meta = bill_metadata.get(bill_id, {})
                max_score = bill_max_scores.get(bill_id, 0)

                # Re-filter by current SQL status (vector metadata may be stale)
                bill_status = str(meta.get("status", ""))
                if bill_status and bill_status not in allowed_statuses:
                    continue

                # Assign tier: top 10 are primary, rest are secondary
                tier = "primary" if rank < 10 else "secondary"
                requires_local = bill_id in local_impl_bills or meta.get("local_implementation_required", False)
                state.append({
                    "type": "bill",
                    "id": bill_id,
                    "bill_number": meta.get("bill_number", chunks[0].get("bill_number", "") if chunks else ""),
                    "bill_name": meta.get("bill_name", ""),
                    "status": bill_status,
                    "status_label": STATUS_LABELS.get(bill_status, "Unknown"),
                    "enacted_date": meta.get("enacted_date", ""),
                    "summary": meta.get("summary", ""),
                    "leverage_point": meta.get("leverage_point", ""),
                    "keywords": meta.get("keywords", []),
                    "topic": meta.get("topic", ""),
                    "official_url": meta.get("official_url", ""),
                    "relevance_score": round(max_score, 3),
                    "tier": tier,
                    "requires_local_action": requires_local,
                    "local_deadline": meta.get("local_deadline", "") if requires_local else "",
                    # Hierarchical: include relevant sections for LLM context
                    "relevant_sections": chunks,
                })
                rank += 1
        except Exception:
            pass  # Semantic search not available

    # Fallback: if no vectors available, query storage directly for legislation
    # This provides basic functionality for local dev without vector embeddings
    if not state and storage is not None:
        try:
            # Get legislation from storage (no semantic ranking)
            bills = storage.get_legislation(
                state=state_code,
                status="Active",
                limit=max_results,
            )
            for rank, bill in enumerate(bills):
                tier = "primary" if rank < 10 else "secondary"
                bill_status = str(bill.get("status", ""))
                requires_local = bill.get("local_implementation_required", False)
                state.append({
                    "type": "bill",
                    "id": bill.get("bill_id", ""),
                    "bill_number": bill.get("bill_number", ""),
                    "bill_name": bill.get("bill_name", ""),
                    "status": bill_status,
                    "status_label": STATUS_LABELS.get(bill_status, bill_status or "Unknown"),
                    "enacted_date": bill.get("enacted_date", ""),
                    "summary": bill.get("summary", ""),
                    "leverage_point": bill.get("leverage_point", ""),
                    "keywords": bill.get("keywords", []),
                    "topic": bill.get("topic", ""),
                    "official_url": bill.get("official_url", ""),
                    "relevance_score": 0.5,  # No semantic score available
                    "tier": tier,
                    "requires_local_action": requires_local,
                    "local_deadline": bill.get("local_deadline", "") if requires_local else "",
                })
        except Exception:
            pass  # Storage query failed

    # Sort by relevance score (highest similarity first)
    # For bill_first mode, preserve the ordering (already sorted with boost applied)
    # For section_first mode, sort by raw relevance score
    if effective_mode != "bill_first":
        state = sorted(state, key=lambda x: x.get("relevance_score", 0), reverse=True)

    if not state:
        state = [{"note": f"No state bills found for '{topic}'"}]

    # Search federal legislation using vector backend
    # Similar pattern to state legislation: chunk retrieval → bill grouping → ranking
    FEDERAL_CHUNK_TOP_K = 100  # Generous chunk retrieval
    FEDERAL_CHUNKS_PER_BILL = 3  # Keep top N relevant sections per bill

    if vectors is not None:
        try:
            # Search federal legislation chunks by semantic similarity
            # Federal bills use jurisdiction 'state-US' (vs 'legislation-CA' for state)
            federal_legislation_jurisdiction = "state-US"
            federal_results = vectors.search(
                query=topic,
                jurisdiction_id=federal_legislation_jurisdiction,
                corpus_type="legislation",
                top_k=FEDERAL_CHUNK_TOP_K,
            )

            # Group chunks by bill_id, keeping top chunks per bill
            federal_bill_chunks: Dict[str, List[dict]] = defaultdict(list)
            federal_bill_max_scores: Dict[str, float] = {}
            federal_local_impl_bills: set[str] = set()  # Bills requiring local implementation

            for result in federal_results:
                if result.score < min_score:
                    continue
                bill_id = result.metadata.get("bill_id", "")
                if not bill_id:
                    continue

                # Filter by legislation status
                status = str(result.metadata.get("status", ""))
                if status and status not in allowed_statuses:
                    continue

                # Track max score for bill-first ranking
                if bill_id not in federal_bill_max_scores or result.score > federal_bill_max_scores[bill_id]:
                    federal_bill_max_scores[bill_id] = result.score

                # Track bills requiring local implementation (for boosting)
                if result.metadata.get("local_implementation_required"):
                    federal_local_impl_bills.add(bill_id)

                if len(federal_bill_chunks[bill_id]) < FEDERAL_CHUNKS_PER_BILL:
                    federal_bill_chunks[bill_id].append({
                        "content": result.content[:300] if result.content else "",
                        "score": round(result.score, 3),
                        "chunk_index": result.metadata.get("chunk_index"),
                    })

            # Determine bill ordering based on ranking mode
            # Federal bills use same ID boosting pattern (HR, S. patterns already in BILL_PATTERN)
            if effective_mode == "bill_first":
                def federal_bill_sort_key(bid: str) -> float:
                    base_score = federal_bill_max_scores.get(bid, 0)
                    # Boost bills requiring local implementation (most actionable)
                    if bid in federal_local_impl_bills:
                        base_score += 0.15
                    # Extract bill number from bill_id (e.g., "us-hb1234" -> "HB1234")
                    bill_num = bid.split("-")[-1].upper() if "-" in bid else bid.upper()
                    # Boost if this bill was mentioned in the query
                    if bill_num in mentioned_bills:
                        base_score += 0.1
                    return base_score

                ordered_federal_bill_ids = sorted(
                    federal_bill_chunks.keys(),
                    key=federal_bill_sort_key,
                    reverse=True
                )[:max_results]
            else:
                # section_first: preserve insertion order
                ordered_federal_bill_ids = list(federal_bill_chunks.keys())[:max_results]

            # Batch fetch bill metadata from storage (single query)
            federal_bill_metadata: Dict[str, dict] = {}
            if storage is not None and ordered_federal_bill_ids:
                try:
                    federal_bill_metadata = storage.get_legislation_batch(
                        state="US",
                        bill_ids=ordered_federal_bill_ids,
                    )
                except Exception:
                    pass  # Batch fetch not available

            # Build hierarchical results with tier assignment
            rank = 0
            for bill_id in ordered_federal_bill_ids:
                chunks = federal_bill_chunks[bill_id]
                meta = federal_bill_metadata.get(bill_id, {})
                max_score = federal_bill_max_scores.get(bill_id, 0)

                # Re-filter by current SQL status (vector metadata may be stale)
                bill_status = str(meta.get("status", ""))
                if bill_status and bill_status not in allowed_statuses:
                    continue

                # Assign tier: top 10 are primary, rest are secondary
                tier = "primary" if rank < 10 else "secondary"

                requires_local = bill_id in federal_local_impl_bills or meta.get("local_implementation_required", False)
                federal.append({
                    "type": "federal_bill",
                    "id": bill_id,
                    "bill_number": meta.get("bill_number", chunks[0].get("bill_number", "") if chunks else ""),
                    "bill_name": meta.get("bill_name", ""),
                    "status": bill_status,
                    "status_label": STATUS_LABELS.get(bill_status, "Unknown"),
                    "enacted_date": meta.get("enacted_date", ""),
                    "summary": meta.get("summary", ""),
                    "leverage_point": meta.get("leverage_point", ""),
                    "keywords": meta.get("keywords", []),
                    "topic": meta.get("topic", ""),
                    "official_url": meta.get("official_url", ""),
                    "relevance_score": round(max_score, 3),
                    "tier": tier,
                    "requires_local_action": requires_local,
                    "local_deadline": meta.get("local_deadline", "") if requires_local else "",
                    # Hierarchical: include relevant sections for LLM context
                    "relevant_sections": chunks,
                })
                rank += 1
        except Exception:
            pass  # Federal legislation search not available

    # Search U.S. Code (codified federal law) using storage backend
    if storage is not None:
        try:
            sections = storage.search_codified_law(
                jurisdiction_id="federal-US",
                query=topic,
                limit=5,
            )

            for section in sections:
                federal.append({
                    "type": "codified_law",
                    "citation": section.get("citation", ""),
                    "heading": section.get("heading", ""),
                    "chapter": section.get("chapter", ""),
                    "text_preview": section.get("text_preview", "")[:300],
                    "relevance": round(float(section.get("relevance", 0)), 4),
                })
        except Exception:
            pass  # Codified law search not available

    # Search CFR (Code of Federal Regulations) using storage backend
    if storage is not None:
        try:
            cfr_sections = storage.search_codified_law(
                jurisdiction_id="federal-CFR",
                query=topic,
                limit=5,
            )

            for section in cfr_sections:
                federal.append({
                    "type": "cfr",
                    "citation": section.get("citation", ""),
                    "heading": section.get("heading", ""),
                    "chapter": section.get("chapter", ""),
                    "text_preview": section.get("text_preview", "")[:300],
                    "relevance": round(float(section.get("relevance", 0)), 4),
                })
        except Exception:
            pass  # CFR search not available

    # Search federal programs using vector backend
    # Semantic search for relevant grant programs (CDBG, HOME, LIHTC, etc.)
    PROGRAMS_TOP_K = 20  # Programs are flat (not chunked), smaller top_k
    PROGRAMS_MIN_SCORE = 0.4

    if vectors is not None:
        try:
            # Extract mentioned program codes for boosting
            mentioned_programs = _extract_program_codes(topic)

            # Search federal programs by semantic similarity
            program_results = vectors.search(
                query=topic,
                jurisdiction_id="federal-US",
                corpus_type="programs",
                top_k=PROGRAMS_TOP_K,
            )

            # Rank programs with optional boosting for mentioned program codes
            scored_programs = []
            for result in program_results:
                if result.score < PROGRAMS_MIN_SCORE:
                    continue

                base_score = result.score
                program_name = result.metadata.get("program_name", "")

                # Boost if program code is mentioned in query
                # Check if any mentioned code appears in program name
                boost = 0.0
                for code in mentioned_programs:
                    if code in program_name.upper():
                        boost = 0.1
                        break

                scored_programs.append({
                    "result": result,
                    "sort_score": base_score + boost,
                    "base_score": base_score,
                })

            # Sort by boosted score, then take top results
            scored_programs.sort(key=lambda x: x["sort_score"], reverse=True)

            for rank, item in enumerate(scored_programs[:15]):  # Limit to 15 programs
                result = item["result"]
                tier = "primary" if rank < 10 else "secondary"

                federal.append({
                    "type": "federal_program",
                    "id": result.id,
                    "program_name": result.metadata.get("program_name", ""),
                    "administering_agency": result.metadata.get("administering_agency", ""),
                    "cfda_number": result.metadata.get("cfda_number", ""),
                    "topic": result.metadata.get("topic", ""),
                    "description": result.content[:400] if result.content else "",
                    "eligible_activities": result.metadata.get("eligible_activities", ""),
                    "keywords": result.metadata.get("keywords", []),
                    "relevance_score": round(item["base_score"], 3),
                    "tier": tier,
                })
        except Exception:
            pass  # Federal programs search not available

    if not federal:
        federal = [{"note": f"No federal regulations found for topic '{topic}'"}]

    # Search local municipal code using vector backend
    # Deduplicate by section_number — vector search returns multiple chunks per
    # section, but we only want the highest-scored chunk for each unique section.
    seen_sections: set[str] = set()

    if vectors is not None:
        try:
            results = vectors.search(
                query=topic,
                jurisdiction_id=jurisdiction,
                corpus_type="municipal_code",
                top_k=5,
            )

            for result in results:
                section_num = result.metadata.get("section_number", "")
                if section_num and section_num in seen_sections:
                    continue
                if result.score > 0:
                    if section_num:
                        seen_sections.add(section_num)
                    local.append({
                        "type": "ordinance",
                        "id": result.id,
                        "section_number": section_num,
                        "section_name": result.metadata.get("section_name", ""),
                        "chapter": result.metadata.get("chapter", ""),
                        "text_preview": result.content[:300] if result.content else "",
                        "relevance_score": round(result.score, 3),
                    })
        except Exception:
            pass  # Municipal code search error

    # Search county code (applies to cities within the county)
    county_jurisdiction = CITY_TO_COUNTY.get(jurisdiction)
    if county_jurisdiction and vectors is not None:
        try:
            results = vectors.search(
                query=topic,
                jurisdiction_id=county_jurisdiction,
                corpus_type="municipal_code",
                top_k=5,
            )

            for result in results:
                section_num = result.metadata.get("section_number", "")
                if section_num and section_num in seen_sections:
                    continue
                if result.score > 0:
                    if section_num:
                        seen_sections.add(section_num)
                    local.append({
                        "type": "county_ordinance",
                        "id": result.id,
                        "section_number": section_num,
                        "section_name": result.metadata.get("section_name", ""),
                        "chapter": result.metadata.get("chapter", ""),
                        "text_preview": result.content[:300] if result.content else "",
                        "relevance_score": round(result.score, 3),
                        "jurisdiction": county_jurisdiction,
                    })
        except Exception:
            pass  # County code search not available

    if not local:
        local = [{"note": f"No local ordinances found for topic '{topic}'"}]

    return RegulatoryStack(
        topic=topic,
        jurisdiction=jurisdiction,
        federal=federal,
        state=state,
        local=local,
    )
