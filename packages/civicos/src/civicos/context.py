"""
Context Module - what_applies() implementation

Provides regulatory context for topics using legislative_context_cache.
"""

from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime

# Load environment variables for DATABASE_URL
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


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
    location: str = None
) -> RegulatoryStack:
    """
    Get regulatory stack for a topic.

    Uses legislative_context_cache for state bills and federal programs.

    Args:
        jurisdiction: City/jurisdiction ID
        topic: Topic to search
        location: Optional location for local rules

    Returns:
        RegulatoryStack with federal, state, local context
    """
    federal = []
    state = []
    local = []

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

    try:
        # Import the legislative cache from civicos_services
        from civicos_services.legislative.legislative_context_cache import legislative_cache

        # Load legislative data for this state/topic
        legislative_data = legislative_cache.get(state_name, state_key)

        if legislative_data:
            # Extract state legislation
            state_legislation = legislative_data.get("state_legislation", {})
            for bill_id, bill_data in state_legislation.items():
                state.append({
                    "type": "bill",
                    "id": bill_id,
                    "bill": bill_data.get("bill", bill_id),
                    "title": bill_data.get("title", ""),
                    "leverage_point": bill_data.get("leverage_point", ""),
                    "keywords": bill_data.get("keywords", []),
                })

            # Extract federal programs
            federal_programs = legislative_data.get("federal_programs", {})
            for prog_id, prog_data in federal_programs.items():
                federal.append({
                    "type": "program",
                    "id": prog_id,
                    "program_name": prog_data.get("program_name", prog_id),
                    "agency": prog_data.get("administering_agency", prog_data.get("agency", "")),
                    "leverage_point": prog_data.get("leverage_point", ""),
                    "keywords": prog_data.get("keywords", []),
                })

        if not state:
            state = [{"note": f"No state bills for topic '{state_key}'"}]
        if not federal:
            federal = [{"note": f"No federal programs for topic '{state_key}'"}]

    except ImportError:
        state = [{"note": "legislative_context_cache not available"}]
        federal = [{"note": "legislative_context_cache not available"}]
    except Exception as e:
        state = [{"note": f"Error loading state legislation: {e}"}]
        federal = [{"note": f"Error loading federal programs: {e}"}]

    # Search U.S. Code (codified federal law)
    try:
        import os
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            from civicos.storage.postgres_backend import PostgresBackend
            db = PostgresBackend(database_url)

            # Search codified law for relevant sections
            sections = db.search_codified_law(
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

            # Remove the "no federal" note if we found codified law
            if sections and federal and federal[0].get("note"):
                federal = [f for f in federal if not f.get("note")]

    except Exception:
        pass  # Codified law search not available

    # Search CFR (Code of Federal Regulations)
    try:
        import os
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            from civicos.storage.postgres_backend import PostgresBackend
            db = PostgresBackend(database_url)

            # Search CFR for relevant regulatory sections
            cfr_sections = db.search_codified_law(
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

            # Remove the "no federal" note if we found CFR
            if cfr_sections and federal and federal[0].get("note"):
                federal = [f for f in federal if not f.get("note")]

    except Exception:
        pass  # CFR search not available

    # Search local municipal code (city ordinances) using pgvector
    try:
        import os
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            from civicos.storage.pgvector_backend import PgVectorBackend
            pgvector = PgVectorBackend(database_url, provider_type="fastembed")

            # Search municipal code vectors
            results = pgvector.search(
                query=topic,
                jurisdiction_id=jurisdiction,
                corpus_type="municipal_code",
                top_k=5,
            )

            for result in results:
                # Only include results with reasonable relevance
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

    except ImportError:
        pass  # PgVectorBackend not available
    except Exception:
        pass  # Municipal code search error, continue with county

    # Search county code (applies to cities within the county)
    # Map city jurisdictions to their county
    CITY_TO_COUNTY = {
        "city-san-rafael": "county-marin",
        "city-berkeley": "county-alameda",
        "city-oakland": "county-alameda",
    }

    county_jurisdiction = CITY_TO_COUNTY.get(jurisdiction)
    if county_jurisdiction:
        try:
            import os
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                from civicos.storage.pgvector_backend import PgVectorBackend
                pgvector = PgVectorBackend(database_url, provider_type="fastembed")

                # Search county code vectors
                results = pgvector.search(
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

        except (ImportError, Exception):
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
