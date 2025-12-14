#!/usr/bin/env python3
"""
Test legislative context enrichment with synthetic housing opportunities.

Validates Phase 1.1 implementation:
- Schema with legislative_context field
- Cache system
- Enrichment algorithm
- API hydration
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from legislative_enrichment import enrich_opportunity, enrich_opportunities_batch
from legislative_context_cache import legislative_cache

# Test opportunities
TEST_OPPORTUNITIES = [
    {
        "id": "test-housing-1",
        "title": "Planning Commission: Duplex Development Standards",
        "description": "Discussion of design standards for new duplex construction under state housing mandates",
        "project_type": "housing",
        "jurisdiction": {
            "id": "city-san-rafael",
            "name": "San Rafael",
            "type": "city"
        },
        "when": "2025-10-15T18:00:00-07:00",
        "impact_summary": "Will determine how new duplexes can be built in residential neighborhoods"
    },
    {
        "id": "test-housing-2",
        "title": "City Council: Affordable Housing Funding Allocation",
        "description": "Annual allocation of CDBG and HOME funds for affordable housing projects",
        "project_type": "housing",
        "jurisdiction": {
            "id": "city-berkeley",
            "name": "Berkeley",
            "type": "city"
        },
        "when": "2025-10-20T19:00:00-07:00",
        "impact_summary": "Determines which affordable housing projects receive federal funding"
    },
    {
        "id": "test-housing-3",
        "title": "Planning Commission: Transit Corridor Zoning Amendment",
        "description": "Proposed amendments to zoning code for transit-oriented affordable housing development",
        "project_type": "housing",
        "jurisdiction": {
            "id": "city-oakland",
            "name": "Oakland",
            "type": "city"
        },
        "when": "2025-10-25T18:30:00-07:00",
        "impact_summary": "Will affect housing density and affordability requirements near transit"
    },
    {
        "id": "test-traffic-1",
        "title": "Traffic Safety Committee: Bike Lane Network Expansion",
        "description": "Review of proposed bike lane network improvements",
        "project_type": "transportation",
        "jurisdiction": {
            "id": "city-san-rafael",
            "name": "San Rafael",
            "type": "city"
        },
        "when": "2025-10-18T17:00:00-07:00",
        "impact_summary": "Will determine bike lane routes through downtown"
    },
    {
        "id": "test-budget-1",
        "title": "Budget Committee: Mid-Year Budget Review",
        "description": "Review of mid-year budget adjustments and funding priorities",
        "project_type": "budget",
        "jurisdiction": {
            "id": "city-berkeley",
            "name": "Berkeley",
            "type": "city"
        },
        "when": "2025-11-01T18:00:00-07:00",
        "impact_summary": "Adjusts funding priorities for remainder of fiscal year"
    }
]


def test_cache_system():
    """Test legislative context cache"""
    print("\n=== Testing Cache System ===")

    # Test cache loading
    data = legislative_cache.get("california", "housing")

    if data:
        print(f"✓ Cache loaded california_housing.json")
        print(f"  - {len(data.get('state_legislation', {}))} state bills")
        print(f"  - {len(data.get('federal_programs', {}))} federal programs")
    else:
        print("✗ Failed to load legislative context")
        return False

    # Test cache stats
    stats = legislative_cache.stats()
    print(f"✓ Cache stats: {stats['cached_contexts']} contexts, {stats['total_size_kb']:.1f}KB")

    return True


def test_enrichment_algorithm():
    """Test opportunity enrichment"""
    print("\n=== Testing Enrichment Algorithm ===")

    results = []

    for opp in TEST_OPPORTUNITIES:
        legislative_context = enrich_opportunity(opp)

        print(f"\n{opp['title']} ({opp['project_type']})")

        if legislative_context:
            print(f"  ✓ Enriched")
            print(f"    - State bills: {legislative_context.get('state_legislation_refs', [])}")
            print(f"    - Federal programs: {legislative_context.get('federal_program_refs', [])}")
            print(f"    - Summary: {legislative_context.get('relevance_summary', '')[:80]}...")
            results.append(True)
        else:
            print(f"  ○ No enrichment (expected for {opp['project_type']})")
            results.append(opp['project_type'] not in ['housing', 'transportation', 'budget'])

    enriched_count = sum(1 for opp, res in zip(TEST_OPPORTUNITIES, results)
                        if res and opp['project_type'] == 'housing')

    print(f"\nSummary: {enriched_count}/3 housing opportunities enriched")

    return enriched_count >= 2  # At least 2 of 3 housing opportunities should enrich


def test_batch_enrichment():
    """Test batch enrichment"""
    print("\n=== Testing Batch Enrichment ===")

    enriched = enrich_opportunities_batch(TEST_OPPORTUNITIES)

    enriched_count = sum(1 for opp in enriched if 'legislative_context' in opp)

    print(f"✓ Batch enriched {enriched_count}/{len(TEST_OPPORTUNITIES)} opportunities")

    return enriched_count >= 2


def test_api_hydration():
    """Test API hydration (simulated)"""
    print("\n=== Testing API Hydration ===")

    # Import hydration logic directly
    sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
    from legislative_context_cache import legislative_cache

    # Enrich opportunity
    opp = TEST_OPPORTUNITIES[0].copy()
    legislative_context = enrich_opportunity(opp)

    if not legislative_context:
        print("✗ Failed to enrich test opportunity")
        return False

    # Simulate hydration (same logic as in civic_api_integrated.py)
    jurisdiction_id = opp['jurisdiction']['id']
    project_type = opp['project_type']

    # Extract state from jurisdiction_id
    state = "california" if jurisdiction_id.startswith(("city-", "county-")) else None

    if not state:
        print("✗ Could not extract state")
        return False

    # Load legislative data
    leg_data = legislative_cache.get(state, project_type)

    if not leg_data:
        print("✗ No legislative data")
        return False

    # Hydrate state legislation
    hydrated = {**legislative_context}
    if "state_legislation_refs" in legislative_context:
        hydrated["state_legislation"] = []
        for ref in legislative_context["state_legislation_refs"]:
            if ref in leg_data.get("state_legislation", {}):
                bill_data = leg_data["state_legislation"][ref]
                hydrated["state_legislation"].append({
                    "id": ref,
                    "bill": bill_data.get("bill"),
                    "status": bill_data.get("status"),
                    "leverage_point": bill_data.get("leverage_point"),
                    "summary": bill_data.get("summary"),
                    "official_url": bill_data.get("official_url")
                })

    if hydrated and 'state_legislation' in hydrated:
        print(f"✓ Hydrated {len(hydrated.get('state_legislation', []))} state bills with full details")

        # Show first bill details
        if hydrated['state_legislation']:
            bill = hydrated['state_legislation'][0]
            print(f"  Example: {bill.get('bill')}")
            print(f"    Leverage: {bill.get('leverage_point', '')[:60]}...")

        return True
    else:
        print("✗ Hydration failed")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Legislative Context Enrichment - Phase 1.1 Tests")
    print("=" * 60)

    tests = [
        ("Cache System", test_cache_system),
        ("Enrichment Algorithm", test_enrichment_algorithm),
        ("Batch Enrichment", test_batch_enrichment),
        ("API Hydration", test_api_hydration)
    ]

    results = []
    for name, test_fn in tests:
        try:
            result = test_fn()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n🎉 All tests passed! Phase 1.1 implementation complete.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
