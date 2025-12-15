"""
CivicPlus Regional Discovery for Bay Area Municipal Expansion
Strategic tool for scaling from 4 operational CivicPlus cities to 20+ municipalities

Current Status: 4 CivicPlus cities operational (Richmond, El Cerrito, Dublin, Union City)
Target: Identify 10+ additional CivicPlus municipalities for regional scaling

Key Success Pattern: CivicPlus Calendar.aspx URLs at $0.048/opportunity efficiency
"""

import requests
from typing import Dict, List, Optional
from urllib.parse import urljoin
import re
import sys
import os

# Add src directory to path for CMS detector imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from cms_platform_detector import CMSPlatformDetector, detect_drupal_cities_batch


# Expanded Bay Area CivicPlus Target Cities - High Priority
PRIORITY_CIVICPLUS_TARGETS = {
    # Contra Costa County (high population cluster)
    'antioch': 'https://www.ci.antioch.ca.us/',
    'concord': 'https://www.cityofconcord.org/',
    'pittsburg': 'https://www.ci.pittsburg.ca.us/',
    'martinez': 'https://www.cityofmartinez.org/',
    'brentwood': 'https://www.brentwood.ca.gov/',
    'clayton': 'https://www.claytonca.gov/',
    'pleasant_hill': 'https://www.ci.pleasant-hill.ca.us/',
    'walnut_creek': 'https://www.walnut-creek.org/',

    # Alameda County expansion
    'fremont': 'https://www.fremont.gov/',
    'san_leandro': 'https://www.sanleandro.org/',
    'alameda': 'https://www.alamedaca.gov/',
    'castro_valley': 'https://www.castrovalley.org/',
    'livermore': 'https://www.cityoflivermore.net/',
    'pleasanton': 'https://www.cityofpleasanton.org/',
    'newark': 'https://www.newark.org/',

    # Santa Clara County southern expansion
    'milpitas': 'https://www.ci.milpitas.ca.gov/',
    'campbell': 'https://www.ci.campbell.ca.us/',
    'cupertino': 'https://www.cupertino.org/',
    'saratoga': 'https://www.saratoga.ca.us/',
    'los_gatos': 'https://www.losgatosca.gov/',
    'monte_sereno': 'https://www.montesereno.org/',
    'morgan_hill': 'https://www.morgan-hill.ca.gov/',
    'gilroy': 'https://www.cityofgilroy.org/',

    # San Mateo County
    'foster_city': 'https://www.fostercity.org/',
    'san_carlos': 'https://www.cityofsancarlos.org/',
    'redwood_city': 'https://www.redwoodcity.org/',
    'menlo_park': 'https://www.menlopark.org/',
    'atherton': 'https://www.ci.atherton.ca.us/',
    'belmont': 'https://www.belmont.gov/',
    'burlingame': 'https://www.burlingame.org/',
    'millbrae': 'https://www.ci.millbrae.ca.us/',

    # Solano County expansion
    'vallejo': 'https://www.cityofvallejo.net/',
    'fairfield': 'https://www.fairfield.ca.gov/',
    'suisun_city': 'https://www.suisun.com/',
    'benicia': 'https://www.ci.benicia.ca.us/',
    'vacaville': 'https://www.cityofvacaville.com/',
}

# Secondary targets (smaller municipalities, lower priority)
SECONDARY_CIVICPLUS_TARGETS = {
    # Small Bay Area cities
    'hercules': 'https://www.ci.hercules.ca.us/',
    'pinole': 'https://www.ci.pinole.ca.us/',
    'san_pablo': 'https://www.sanpabloca.gov/',
    'el_sobrante': 'https://www.elsobranteca.gov/',
    'kensington': 'https://www.kensington-ca.gov/',
    'lafayette': 'https://www.lovelafayette.org/',
    'orinda': 'https://www.cityoforinda.org/',
    'moraga': 'https://www.moraga.ca.us/',
    'danville': 'https://www.danville.ca.gov/',
    'san_ramon': 'https://www.sanramon.ca.gov/',

    # Peninsula small cities
    'woodside': 'https://www.townofwoodside.org/',
    'portola_valley': 'https://www.portolavalley.net/',
    'hillsborough': 'https://www.hillsborough.net/',
    'half_moon_bay': 'https://www.hmbcity.com/',
    'pacifica': 'https://www.cityofpacifica.org/',
    'colma': 'https://www.colma.ca.gov/',
    'daly_city': 'https://www.dalycity.org/',
    'south_san_francisco': 'https://www.ssf.net/',

    # South Bay small cities
    'los_altos': 'https://www.losaltosca.gov/',
    'los_altos_hills': 'https://www.losaltoshills.ca.gov/',
    'mountain_view': 'https://www.mountainview.gov/',
    'palo_alto': 'https://www.cityofpaloalto.org/',
}


def detect_civicplus_calendar_urls(base_url: str) -> List[str]:
    """
    Detect CivicPlus Calendar.aspx URLs for a municipality

    Returns:
        List of found Calendar.aspx URLs
    """
    potential_urls = [
        f"{base_url.rstrip('/')}/Calendar.aspx",
        f"{base_url.rstrip('/')}/calendar.aspx",
        f"{base_url.rstrip('/')}/calendar/",
        f"{base_url.rstrip('/')}/events/",
        f"{base_url.rstrip('/')}/meetings/"
    ]

    found_urls = []
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (compatible; CivicBot/1.0; +civic@example.com)'
    })

    for url in potential_urls:
        try:
            response = session.get(url, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                # Check for CivicPlus indicators in the content
                content = response.text.lower()
                if 'calendar.aspx' in content or 'eventdetails' in content or 'civicplus' in content:
                    found_urls.append(url)
                    print(f"  ✅ Found CivicPlus calendar: {url}")
                    break  # Found working URL, no need to test others
        except Exception as e:
            continue

    return found_urls


def batch_civicplus_discovery(city_targets: Dict[str, str], priority_level: str = "primary") -> Dict[str, Dict]:
    """
    Batch discovery of CivicPlus municipalities with calendar URL detection

    Args:
        city_targets: Dict of city_name -> base_url
        priority_level: "primary" or "secondary" for logging

    Returns:
        Dict of discovered CivicPlus cities with platform details
    """
    print(f"\n🔍 DISCOVERING {priority_level.upper()} CIVICPLUS TARGETS")
    print(f"Testing {len(city_targets)} municipalities...")
    print("="*60)

    detector = CMSPlatformDetector()
    civicplus_discoveries = {}

    for city_name, base_url in city_targets.items():
        try:
            print(f"\n📍 Testing {city_name.replace('_', ' ').title()}: {base_url}")

            # Detect platform type
            detection = detector.detect_cms_platform(base_url)

            if detection['platform'] == 'civicplus' and detection['confidence'] > 0.8:
                print(f"🎯 CIVICPLUS CONFIRMED: {city_name} (confidence: {detection['confidence']:.2f})")

                # Find Calendar.aspx URLs
                calendar_urls = detect_civicplus_calendar_urls(base_url)

                if calendar_urls:
                    # Calculate population tier for priority scoring
                    population_tier = 1 if city_name in ['fremont', 'concord', 'antioch', 'vallejo'] else 2

                    civicplus_discoveries[city_name] = {
                        'base_url': base_url,
                        'platform': 'civicplus',
                        'confidence': detection['confidence'],
                        'calendar_urls': calendar_urls,
                        'status': 'ready_for_deployment',
                        'population_tier': population_tier,
                        'cost_efficiency_prediction': 0.048,  # Based on current CivicPlus performance
                        'implementation_priority': population_tier,
                        'agent_type': 'civicplus_cms'
                    }
                    print(f"  🚀 DEPLOYMENT READY: {len(calendar_urls)} calendar URLs found")
                else:
                    print(f"  ⚠️ CivicPlus detected but no calendar URLs found")
            else:
                platform_name = detection['platform'].upper() if detection['platform'] != 'error' else 'DETECTION FAILED'
                print(f"  📋 {platform_name} (confidence: {detection['confidence']:.2f})")

        except Exception as e:
            print(f"  ❌ ERROR testing {city_name}: {str(e)}")
            continue

    return civicplus_discoveries


def generate_deployment_plan(discoveries: Dict[str, Dict]) -> Dict[str, any]:
    """Generate deployment plan for discovered CivicPlus cities"""

    tier_1_cities = [city for city, data in discoveries.items() if data['population_tier'] == 1]
    tier_2_cities = [city for city, data in discoveries.items() if data['population_tier'] == 2]

    total_opportunities_estimated = len(discoveries) * 3  # Estimate 3 events per city
    monthly_cost_estimate = total_opportunities_estimated * 0.048

    return {
        'total_discoveries': len(discoveries),
        'tier_1_cities': tier_1_cities,  # High population targets
        'tier_2_cities': tier_2_cities,  # Smaller municipalities
        'deployment_phases': {
            'phase_1': tier_1_cities[:5],  # Deploy 5 high-pop cities first
            'phase_2': tier_2_cities[:10],  # Then 10 smaller cities
            'phase_3': list(discoveries.keys())[15:]  # Remaining cities
        },
        'cost_analysis': {
            'estimated_monthly_cost': round(monthly_cost_estimate, 2),
            'cost_per_city': 0.048 * 3,  # ~$0.14/city/month
            'roi_vs_standard': f"{(0.15 - 0.048) / 0.15 * 100:.0f}% cost reduction vs standard parsing"
        },
        'implementation_timeline': {
            'week_1': 'Deploy top 3 tier-1 cities',
            'week_2': 'Validate cost efficiency, deploy next 2 tier-1',
            'week_3': 'Begin tier-2 deployment if phase 1 successful',
            'month_2': 'Complete regional CivicPlus coverage'
        }
    }


def update_automated_civic_refresh(discoveries: Dict[str, Dict]) -> List[str]:
    """Generate configuration entries for automated_civic_refresh.py"""

    config_entries = []

    for city_name, data in discoveries.items():
        if data['status'] == 'ready_for_deployment':
            config_entry = f'''    "{city_name}": {{
        "jurisdiction_id": "city-{city_name.replace('_', '-')}",
        "agent_type": "civicplus_cms",  # CivicPlus platform specialized extraction
        "meeting_urls": {data['calendar_urls']},
        "contact_email": "clerk@{city_name.replace('_', '')}.gov",  # Standard pattern - verify
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": {data['cost_efficiency_prediction']}  # CivicPlus target efficiency
    }},'''
            config_entries.append(config_entry)

    return config_entries


def main():
    """Main discovery and deployment planning workflow"""

    print("🏛️ CIVICPLUS REGIONAL SCALING DISCOVERY")
    print("="*60)
    print(f"Current operational: 4 CivicPlus cities (Richmond, El Cerrito, Dublin, Union City)")
    print(f"Target: Scale to 20+ municipalities for foundation grant applications")
    print(f"Cost efficiency: $0.048/opportunity (68% better than $0.15 standard)")

    # Discover primary targets (high population)
    primary_discoveries = batch_civicplus_discovery(PRIORITY_CIVICPLUS_TARGETS, "primary")

    # Discover secondary targets if primary is successful
    secondary_discoveries = {}
    if len(primary_discoveries) >= 3:
        print(f"\n✅ Primary discovery successful ({len(primary_discoveries)} cities)")
        print("Proceeding with secondary target discovery...")
        secondary_discoveries = batch_civicplus_discovery(SECONDARY_CIVICPLUS_TARGETS, "secondary")

    # Combine all discoveries
    all_discoveries = {**primary_discoveries, **secondary_discoveries}

    # Generate deployment plan
    deployment_plan = generate_deployment_plan(all_discoveries)

    # Output results
    print("\n" + "="*60)
    print("📊 CIVICPLUS REGIONAL SCALING RESULTS")
    print("="*60)

    print(f"\n🎯 TOTAL CIVICPLUS DISCOVERIES: {deployment_plan['total_discoveries']}")
    print(f"📈 Tier 1 Cities (High Population): {', '.join([city.replace('_', ' ').title() for city in deployment_plan['tier_1_cities']])}")
    print(f"🏘️ Tier 2 Cities (Regional Coverage): {', '.join([city.replace('_', ' ').title() for city in deployment_plan['tier_2_cities']])}")

    print(f"\n💰 COST ANALYSIS:")
    for key, value in deployment_plan['cost_analysis'].items():
        print(f"  • {key.replace('_', ' ').title()}: {value}")

    print(f"\n🚀 DEPLOYMENT PHASES:")
    for phase, cities in deployment_plan['deployment_phases'].items():
        if cities:
            cities_formatted = ', '.join([city.replace('_', ' ').title() for city in cities])
            print(f"  • {phase.replace('_', ' ').title()}: {cities_formatted}")

    print(f"\n⏰ IMPLEMENTATION TIMELINE:")
    for week, task in deployment_plan['implementation_timeline'].items():
        print(f"  • {week.replace('_', ' ').title()}: {task}")

    # Generate configuration for automated_civic_refresh.py
    if all_discoveries:
        print(f"\n🔧 AUTOMATED_CIVIC_REFRESH.PY CONFIGURATION ENTRIES:")
        print("(Add these to CITY_CONFIGS in automated_civic_refresh.py)")
        config_entries = update_automated_civic_refresh(all_discoveries)
        for entry in config_entries[:5]:  # Show first 5 entries
            print(entry)

        if len(config_entries) > 5:
            print(f"... and {len(config_entries) - 5} more entries")

    return all_discoveries, deployment_plan


if __name__ == "__main__":
    discoveries, plan = main()