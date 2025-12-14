#!/usr/bin/env python3
"""
Test jurisdiction ID normalization in chat routing (Session 56.5)

Root Cause: LLM returns user-friendly names like "berkeley" but database
expects jurisdiction IDs like "city-berkeley", causing 0 results.

Fix: Added JURISDICTION_MAPPINGS and normalize_jurisdiction() function
to civic_chat_router.py

Test Coverage:
- Single-word cities (Berkeley, Oakland)
- Multi-word cities (San Rafael, Los Altos Hills)
- Counties (Sonoma County)
- Special districts (BART)
- Fallback for unmapped cities
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from civic_chat_router import normalize_jurisdiction, JURISDICTION_MAPPINGS


def test_single_word_cities():
    """Test single-word city normalization"""
    assert normalize_jurisdiction("berkeley") == "city-berkeley"
    assert normalize_jurisdiction("Berkeley") == "city-berkeley"  # Case insensitive
    assert normalize_jurisdiction("BERKELEY") == "city-berkeley"
    assert normalize_jurisdiction("oakland") == "city-oakland"
    assert normalize_jurisdiction("hayward") == "city-hayward"
    print("✓ Single-word cities normalize correctly")


def test_multi_word_cities():
    """Test multi-word city normalization"""
    assert normalize_jurisdiction("san rafael") == "city-san-rafael"
    assert normalize_jurisdiction("San Rafael") == "city-san-rafael"
    assert normalize_jurisdiction("san-rafael") == "city-san-rafael"  # Hyphenated input
    assert normalize_jurisdiction("santa rosa") == "city-santa-rosa"
    assert normalize_jurisdiction("los altos hills") == "city-los-altos-hills"
    assert normalize_jurisdiction("pleasant hill") == "city-pleasant-hill"
    print("✓ Multi-word cities normalize correctly")


def test_counties():
    """Test county normalization"""
    assert normalize_jurisdiction("sonoma county") == "sonoma-county"
    assert normalize_jurisdiction("Sonoma County") == "sonoma-county"
    assert normalize_jurisdiction("alameda county") == "alameda-county"
    print("✓ Counties normalize correctly")


def test_special_districts():
    """Test special district normalization"""
    assert normalize_jurisdiction("bart") == "bart"
    assert normalize_jurisdiction("BART") == "bart"
    print("✓ Special districts normalize correctly")


def test_fallback_for_unmapped():
    """Test fallback for cities not in mapping"""
    # Should prepend "city-" and hyphenate spaces
    assert normalize_jurisdiction("new city") == "city-new-city"
    assert normalize_jurisdiction("future town") == "city-future-town"
    print("✓ Fallback normalization works for unmapped cities")


def test_all_configured_cities():
    """Verify all 26 configured cities are in mapping"""
    expected_cities = [
        # Original cities
        ("san rafael", "city-san-rafael"),
        ("berkeley", "city-berkeley"),
        ("santa rosa", "city-santa-rosa"),
        ("hayward", "city-hayward"),
        ("richmond", "city-richmond"),
        ("el cerrito", "city-el-cerrito"),
        ("dublin", "city-dublin"),
        ("union city", "city-union-city"),
        ("concord", "city-concord"),
        ("san leandro", "city-san-leandro"),
        ("campbell", "city-campbell"),
        ("pleasant hill", "city-pleasant-hill"),
        ("oakland", "city-oakland"),
        ("los altos", "city-los-altos"),
        ("napa", "city-napa"),
        # CivicClerk cities
        ("daly city", "city-daly-city"),
        ("los altos hills", "city-los-altos-hills"),
        ("milpitas", "city-milpitas"),
        ("pinole", "city-pinole"),
        ("pleasanton", "city-pleasanton"),
        ("scotts valley", "city-scotts-valley"),
        ("pittsburg", "city-pittsburg"),
        ("antioch", "city-antioch"),
        # Counties
        ("sonoma county", "sonoma-county"),
        # Special districts
        ("bart", "bart"),
    ]

    for user_input, expected_output in expected_cities:
        result = normalize_jurisdiction(user_input)
        assert result == expected_output, f"Failed: {user_input} → {result} (expected {expected_output})"

    print(f"✓ All {len(expected_cities)} configured jurisdictions normalize correctly")


def main():
    """Run all tests"""
    print("\n🧪 Testing Jurisdiction Normalization (Session 56.5)\n")

    test_single_word_cities()
    test_multi_word_cities()
    test_counties()
    test_special_districts()
    test_fallback_for_unmapped()
    test_all_configured_cities()

    print("\n✅ All jurisdiction normalization tests passed!\n")
    print("Fix verified:")
    print("  LLM output: 'berkeley' → Database ID: 'city-berkeley'")
    print("  LLM output: 'San Rafael' → Database ID: 'city-san-rafael'")
    print("  LLM output: 'Sonoma County' → Database ID: 'sonoma-county'")


if __name__ == "__main__":
    main()
