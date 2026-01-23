"""
Context Module - what_applies() implementation

Provides regulatory context for topics using storage backends.
"""

from typing import Optional, List, Any, Dict, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

if TYPE_CHECKING:
    from civicos.storage.protocols import StorageBackend
    from civicos.storage.protocols.vector import VectorBackend


@dataclass
class RegulatoryStack:
    """Regulatory context for a topic."""
    topic: str
    jurisdiction: str
    federal: List[dict] = field(default_factory=list)
    state: List[dict] = field(default_factory=list)
    local: List[dict] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=datetime.now)


# Topic mapping - canonical topics to state_key
TOPIC_MAP = {
    "housing": "housing",
    "zoning": "housing",
    "transportation": "transportation",
    "transit": "transportation",
    "environment": "environment",
    "climate": "environment",
    "budget": "budget",
    "finance": "budget",
    "education": "education",
    "schools": "education",
}

# Map state names to database codes
STATE_CODE_MAP = {
    "california": "CA",
    "ca": "CA",
}

# Map city jurisdictions to their county
CITY_TO_COUNTY = {
    "city-san-rafael": "county-marin",
    "city-berkeley": "county-alameda",
    "city-oakland": "county-alameda",
}


def _extract_state_from_jurisdiction(jurisdiction_id: str) -> Optional[str]:
    """Extract state from jurisdiction_id (e.g., 'city-san-rafael' -> 'california')."""
    if not jurisdiction_id:
        return None

    # All current jurisdictions are in California
    # Handle multiple naming conventions:
    # - city-san-rafael (canonical)
    # - san-rafael-ca (alternative)
    # - county-marin
    if jurisdiction_id.startswith(("city-", "county-")):
        return "california"

    # Handle state suffix patterns (e.g., san-rafael-ca)
    if jurisdiction_id.endswith("-ca"):
        return "california"

    # Handle common California city names
    ca_cities = ["san-rafael", "berkeley", "oakland", "hayward", "santa-rosa"]
    for city in ca_cities:
        if city in jurisdiction_id.lower():
            return "california"

    return None


def get_regulatory_context(
    jurisdiction: str,
    topic: str,
    location: str = None,
    storage: Optional["StorageBackend"] = None,
    vectors: Optional["VectorBackend"] = None,
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

    Returns:
        RegulatoryStack with federal, state, local context
    """
    federal: List[dict] = []
    state: List[dict] = []
    local: List[dict] = []

    # Normalize topic to state_key
    topic_lower = topic.lower()
    state_key = TOPIC_MAP.get(topic_lower, topic_lower)

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

    # Hybrid state legislation search:
    # 1. Exact topic match first (fast, precise for tagged bills)
    # 2. If few results, semantic vector search (discovers untagged bills)
    # 3. Include relevance scores so consuming LLM can filter based on user's actual question
    seen_bill_ids: set = set()

    if storage is not None:
        try:
            # Phase 1: Exact topic match
            bills = storage.get_legislation(
                state=state_code,
                topic=state_key,
                status="Active",
                limit=10,
            )

            for bill in bills:
                bill_id = bill.get("bill_id", "")
                seen_bill_ids.add(bill_id)
                state.append({
                    "type": "bill",
                    "id": bill_id,
                    "bill_number": bill.get("bill_number", ""),
                    "bill_name": bill.get("bill_name", ""),
                    "status": bill.get("status", ""),
                    "enacted_date": bill.get("enacted_date", ""),
                    "summary": bill.get("summary", ""),
                    "leverage_point": bill.get("leverage_point", ""),
                    "keywords": bill.get("keywords", []),
                    "official_url": bill.get("official_url", ""),
                    "match_type": "exact_topic",
                    "relevance_score": 1.0,  # Exact matches get perfect score
                })
        except Exception as e:
            state = [{"note": f"Error loading state legislation: {e}"}]

    # Phase 2: Hierarchical semantic search if exact match found few results
    # Returns both bill-level metadata AND relevant section excerpts
    # Use generous TopK with score floor - let consuming LLM filter based on context
    SEMANTIC_THRESHOLD = 5      # Trigger semantic search if < 5 exact matches
    CHUNK_TOP_K = 100           # Generous chunk retrieval
    CHUNKS_PER_BILL = 3         # Keep top N relevant sections per bill
    MAX_BILLS = 30              # Max bills to return
    SEMANTIC_SCORE_FLOOR = 0.4  # Minimum similarity to include

    if vectors is not None and len(state) < SEMANTIC_THRESHOLD:
        try:
            # Search legislation chunks
            legislation_jurisdiction = f"legislation-{state_code}"
            results = vectors.search(
                query=topic,
                jurisdiction_id=legislation_jurisdiction,
                corpus_type="legislation",
                top_k=CHUNK_TOP_K,
            )

            # Group chunks by bill_id, keeping top chunks per bill
            bill_chunks: Dict[str, List[dict]] = defaultdict(list)
            for result in results:
                if result.score < SEMANTIC_SCORE_FLOOR:
                    continue
                bill_id = result.metadata.get("bill_id", "")
                if not bill_id or bill_id in seen_bill_ids:
                    continue
                if len(bill_chunks[bill_id]) < CHUNKS_PER_BILL:
                    bill_chunks[bill_id].append({
                        "content": result.content[:300] if result.content else "",
                        "score": round(result.score, 3),
                        "chunk_index": result.metadata.get("chunk_index"),
                    })

            # Batch fetch bill metadata from storage (single query)
            bill_metadata: Dict[str, dict] = {}
            if storage is not None and bill_chunks:
                try:
                    bill_ids_to_fetch = list(bill_chunks.keys())[:MAX_BILLS]
                    bill_metadata = storage.get_legislation_batch(
                        state=state_code,
                        bill_ids=bill_ids_to_fetch,
                    )
                except Exception:
                    pass  # Batch fetch not available, continue without metadata

            # Build hierarchical results
            for bill_id, chunks in list(bill_chunks.items())[:MAX_BILLS]:
                seen_bill_ids.add(bill_id)
                meta = bill_metadata.get(bill_id, {})
                max_score = max(c["score"] for c in chunks) if chunks else 0

                state.append({
                    "type": "bill",
                    "id": bill_id,
                    "bill_number": meta.get("bill_number", chunks[0].get("bill_number", "") if chunks else ""),
                    "bill_name": meta.get("bill_name", ""),
                    "status": meta.get("status", ""),
                    "enacted_date": meta.get("enacted_date", ""),
                    "summary": meta.get("summary", ""),
                    "leverage_point": meta.get("leverage_point", ""),
                    "keywords": meta.get("keywords", []),
                    "official_url": meta.get("official_url", ""),
                    "match_type": "semantic",
                    "relevance_score": max_score,
                    # Hierarchical: include relevant sections for LLM context
                    "relevant_sections": chunks,
                })
        except Exception:
            pass  # Semantic search not available, continue with exact matches

    # Sort by relevance score (exact matches first, then by semantic similarity)
    state = sorted(state, key=lambda x: x.get("relevance_score", 0), reverse=True)

    if not state:
        state = [{"note": f"No state bills found for '{topic}' (checked exact topic match and semantic search)"}]

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

    if not federal:
        federal = [{"note": f"No federal regulations found for topic '{topic}'"}]

    # Search local municipal code using vector backend
    if vectors is not None:
        try:
            results = vectors.search(
                query=topic,
                jurisdiction_id=jurisdiction,
                corpus_type="municipal_code",
                top_k=5,
            )

            for result in results:
                if result.score > 0:
                    local.append({
                        "type": "ordinance",
                        "id": result.id,
                        "section_number": result.metadata.get("section_number", ""),
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
                if result.score > 0:
                    local.append({
                        "type": "county_ordinance",
                        "id": result.id,
                        "section_number": result.metadata.get("section_number", ""),
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
