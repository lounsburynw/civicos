"""
Municipal Registry - Track platform types, success rates, and API availability
Strategic decision support for scaling Civic Conversational OS data collection

Key Findings:
- San Rafael: Granicus-based, GPT-4o universal parsing WORKS (95% success)
- Legistar API: Requires InSite configuration, not universally accessible
- Strategy: HTML-first with GPT-4o universal parsing, API as enhancement
"""

from datetime import datetime
from typing import Dict, List, Optional
import json

# Municipal Success Registry - Track what works across cities
MUNICIPAL_REGISTRY = {
    "san_rafael": {
        "status": "production",
        "platform": "granicus_based",
        "success_rate": 95,
        "api_access": None,  # No Legistar API confirmed
        "html_parsing": "success",
        "test_urls": [
            "https://cityofsanrafael.org/meetings/planning-commission-september-23-2025/",
            "https://cityofsanrafael.org/meetings/city-council-march-03-2024/"
        ],
        "working_patterns": ["planning-commission", "city-council"],
        "data_format": "structured_html",
        "gpt4o_compatibility": "excellent",
        "last_tested": "2025-09-24",
        "notes": "GPT-4o universal parsing works perfectly, reliable production data"
    },

    "berkeley": {
        "status": "failed_pdf_complexity",
        "platform": "complex_pdf_minutes",
        "success_rate": 0,
        "api_access": None,
        "html_parsing": "failed",
        "failure_reason": "31 files, 8,784 lines overengineered - avoid PDFs",
        "lessons": "Stick to HTML/structured data only, test simple pages only",
        "redemption_criteria": "Find HTML agenda pages (not PDF minutes), <2 hour test budget"
    },

    # Legistar cities from database analysis
    "san_francisco": {
        "status": "legistar_available_but_restricted",
        "platform": "legistar",
        "api_access": "requires_insite_config",
        "html_parsing": "untested",
        "legistar_client": "sanfrancisco",
        "test_urls": ["https://sfgov.legistar.com/"],
        "notes": "In Legistar database but API requires InSite configuration"
    },

    "oakland": {
        "status": "legistar_production_ready",
        "platform": "legistar",
        "success_rate": 95,
        "api_access": "confirmed_working",
        "html_parsing": "not_needed",
        "legistar_client": "oakland",
        "recent_events": 7,
        "data_quality": "structured_json_excellent",
        "cost_per_session": 0.05,
        "test_results": {
            "bodies_endpoint": "✅ Working",
            "events_endpoint": "✅ 7 relevant civic events found",
            "matters_endpoint": "✅ Working",
            "capabilities": "full_api_access_no_insite_required"
        },
        "last_tested": "2025-09-24",
        "notes": "Production-ready API access, significantly cheaper than HTML parsing"
    },

    "santa_rosa": {
        "status": "legistar_discovered_needs_validation",
        "platform": "legistar",
        "api_access": "confirmed_accessible",
        "html_parsing": "not_needed",
        "legistar_client": "santa-rosa",
        "discovery_method": "systematic_client_name_testing",
        "test_results": {
            "bodies_endpoint": "✅ 50 bodies found",
            "events_endpoint": "✅ 1000+ events (needs date filtering validation)",
            "api_response": "working_but_needs_current_event_validation"
        },
        "next_step": "validate_current_meeting_data_quality",
        "priority": 1,
        "notes": "Major discovery - failed HTML but has working Legistar API"
    },

    "sonoma_county": {
        "status": "legistar_discovered_needs_validation",
        "platform": "legistar",
        "api_access": "confirmed_accessible",
        "html_parsing": "not_needed",
        "legistar_client": "sonoma-county",
        "discovery_method": "systematic_client_name_testing",
        "test_results": {
            "bodies_endpoint": "✅ 1 body found",
            "events_endpoint": "✅ 447+ events (needs date filtering validation)",
            "api_response": "working_but_needs_current_event_validation"
        },
        "next_step": "validate_current_meeting_data_quality",
        "priority": 2,
        "notes": "County-level governance data available via API"
    },

    "marin_county": {
        "status": "broken_all_sources_inaccessible",
        "platform": "none",
        "api_access": "not_configured",
        "html_parsing": "failed",
        "legistar_client": "marin",
        "failure_reasons": [
            "Legistar API returns 500 errors (LegistarConnectionString not configured)",
            "Legistar Web1 interface returns 'Invalid parameters!' on all pages",
            "marincounty.gov official site has Cloudflare bot protection (403 Forbidden)"
        ],
        "test_urls": [
            "https://marin.legistar.com/Calendar.aspx (broken)",
            "https://www.marincounty.gov/departments/board/board-supervisors-meetings (blocked)"
        ],
        "notes": "Removed from operational registry - no viable data sources available. All three access methods failed. Would require browser automation (Playwright/Selenium) to bypass Cloudflare on official site.",
        "last_tested": "2025-10-06",
        "redemption_criteria": "Implement Playwright/Selenium for marincounty.gov OR wait for Legistar instance to be properly configured"
    },

    "hayward": {
        "status": "legistar_production_ready",
        "platform": "legistar",
        "api_access": "confirmed_working",
        "html_parsing": "not_needed",
        "legistar_client": "hayward",
        "test_results": {
            "bodies_endpoint": "✅ Working",
            "events_endpoint": "✅ Future events confirmed (Oct 2025)",
            "capabilities": "full_api_access"
        },
        "notes": "Legistar API client - requires 'hayward' not 'city-hayward'"
    },

    "el_cerrito": {
        "status": "civicclerk_production_ready",
        "platform": "civicclerk",
        "success_rate": 95,
        "api_access": "confirmed_working",
        "html_parsing": "not_needed",
        "civicclerk_subdomain": "elcerritoca",
        "jurisdiction_id": "city-el-cerrito",
        "recent_events": 7,
        "data_quality": "structured_api_excellent",
        "cost_per_session": 0.05,
        "contact_email": "cityclerk@elcerrito.gov",
        "test_results": {
            "events_endpoint": "✅ 7 events found (5 with agendas)",
            "agenda_discovery": "✅ API URLs with blob resolution",
            "pdf_parsing": "✅ Tested with Building Code Adoption agenda",
            "capabilities": "full_api_access_structured_json"
        },
        "last_tested": "2025-09-30",
        "notes": "CivicClerk API client provides reliable structured data with agenda PDF access",
        "url": "https://www.elcerrito.gov",
        "calendar_url": "https://www.elcerrito.gov/Calendar.aspx",
        "portal_url": "https://elcerritoca.portal.civicclerk.com",
        "api_url": "https://elcerritoca.api.civicclerk.com/v1"
    },

    "los_altos": {
        "status": "civicclerk_validated",
        "platform": "civicclerk",
        "success_rate": 86,  # Agenda availability from validation
        "api_access": "full",
        "html_parsing": "not_needed",
        "civicclerk_subdomain": "losaltosca",
        "jurisdiction_id": "city-los-altos",
        "test_urls": ["https://losaltosca.portal.civicclerk.com"],
        "data_quality_score": 6,  # From validation (can improve to 8+ with location data)
        "contact_email": "cityclerk@losaltosca.gov",
        "test_results": {
            "events_endpoint": "✅ 15 upcoming meetings found",
            "agenda_availability": "86% (highest of all validated CivicClerk cities)",
            "capabilities": "full_api_access_structured_json"
        },
        "notes": "Highest agenda availability (86%), recommended first deployment after El Cerrito",
        "last_tested": "2025-09-30",
        "gpt4o_compatibility": "excellent",
        "url": "https://www.losaltosca.gov",
        "calendar_url": "https://www.losaltosca.gov/Calendar.aspx",
        "portal_url": "https://losaltosca.portal.civicclerk.com",
        "api_url": "https://losaltosca.api.civicclerk.com/v1"
    }
}

# Target cities for Phase 1 testing
TARGET_CITIES_PHASE1 = {
    "petaluma": {
        "rationale": "Granicus-based like San Rafael - high success probability",
        "expected_platform": "granicus",
        "test_urls": [
            "https://cityofpetaluma.org/meetings/",
            "https://petaluma.granicus.com/ViewPublisher.php?view_id=3"
        ],
        "expected_success": "high",
        "priority": 1
    },

    "mill_valley": {
        "rationale": "Standard Marin County municipal format, likely Granicus",
        "expected_platform": "granicus_or_standard",
        "test_urls": [
            "https://www.cityofmillvalley.gov/278/Watch-Meetings-Online",
            "https://www.cityofmillvalley.gov/159/City-Council"
        ],
        "expected_success": "high",
        "priority": 1
    },

    "novato": {
        "rationale": "Standard municipal website with dedicated agendas/minutes section",
        "expected_platform": "standard_municipal",
        "test_urls": [
            "https://www.novato.org/government/city-council/agendas-minutes-videos"
        ],
        "expected_success": "medium",
        "priority": 2
    },

    "santa_rosa": {
        "rationale": "Larger Sonoma County city, likely has structured data",
        "expected_platform": "unknown",
        "test_urls": [
            "https://srcity.org/AgendaCenter"
        ],
        "expected_success": "medium",
        "priority": 2
    }
}

# Platform strategies based on analysis
PLATFORM_STRATEGIES = {
    "granicus": {
        "approach": "html_parsing_gpt4o",
        "success_indicators": ["planning-commission", "city-council", "structured agenda pages"],
        "tools": ["civic_digest.py with GPT-4o universal parsing"],
        "expected_success_rate": 85
    },

    "legistar": {
        "approach": "html_first_api_future",
        "success_indicators": ["*.legistar.com domains", "structured meeting data"],
        "tools": ["HTML parsing first, API exploration as enhancement"],
        "expected_success_rate": 70,
        "notes": "API requires InSite config, focus on HTML parsing"
    },

    "standard_municipal": {
        "approach": "html_parsing_gpt4o",
        "success_indicators": ["agenda/minutes sections", "meeting list pages"],
        "tools": ["civic_digest.py with GPT-4o universal parsing"],
        "expected_success_rate": 60
    },

    "pdf_heavy": {
        "approach": "avoid",
        "success_indicators": ["PDF-only minutes", "complex document structures"],
        "tools": ["Skip entirely - Berkeley lesson learned"],
        "expected_success_rate": 5,
        "notes": "Do not pursue PDF-heavy municipalities"
    }
}

# Strategic decision framework
SCALING_STRATEGY = {
    "phase_1_approach": "html_first_gpt4o_universal",
    "api_integration": "enhancement_not_requirement",
    "complexity_budget": 500,  # Max lines per platform scraper
    "success_threshold": 3,    # Need 3+ working cities to continue scaling
    "fallback_strategy": "always_maintain_gpt4o_universal_parsing"
}

def get_city_info(city_name: str) -> Optional[Dict]:
    """Get registry information for a city"""
    return MUNICIPAL_REGISTRY.get(city_name.lower())

def add_test_result(city_name: str, test_result: Dict):
    """Add test results to registry"""
    city_key = city_name.lower()
    if city_key not in MUNICIPAL_REGISTRY:
        MUNICIPAL_REGISTRY[city_key] = {}

    MUNICIPAL_REGISTRY[city_key].update(test_result)
    MUNICIPAL_REGISTRY[city_key]['last_tested'] = datetime.now().strftime('%Y-%m-%d')

def get_working_cities() -> List[str]:
    """Get list of cities with successful implementations"""
    return [city for city, info in MUNICIPAL_REGISTRY.items()
            if info.get('status') == 'production' or info.get('success_rate', 0) > 70]

def get_priority_targets() -> List[str]:
    """Get next cities to test, ordered by priority"""
    return sorted(TARGET_CITIES_PHASE1.keys(),
                 key=lambda x: TARGET_CITIES_PHASE1[x]['priority'])

def make_strategic_decision() -> str:
    """Make scaling strategy decision based on current data"""
    working_cities = get_working_cities()
    legistar_count = sum(1 for info in MUNICIPAL_REGISTRY.values()
                        if info.get('platform') == 'legistar')

    if len(working_cities) >= 3:
        return "scale_html_approach"
    elif legistar_count >= 3:
        return "explore_api_first"
    else:
        return "continue_testing"

if __name__ == "__main__":
    print("🏛️ MUNICIPAL REGISTRY STATUS")
    print(f"Working cities: {len(get_working_cities())}")
    print(f"Priority targets: {get_priority_targets()}")
    print(f"Strategic decision: {make_strategic_decision()}")