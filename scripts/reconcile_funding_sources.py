#!/usr/bin/env python3
"""
Reconcile budget line items with ACFR actuals and external funding sources.

This script attempts to answer: "Where does this budget line item's money come from?"

Usage:
    python scripts/reconcile_funding_sources.py
    python scripts/reconcile_funding_sources.py --budget data/budgets/san_rafael/FY25-26-extracted.json
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# =============================================================================
# STEP 1: Define what we're trying to match
# =============================================================================

@dataclass
class FundingMapping:
    """A mapping between a budget item and its funding source."""
    budget_item: str
    budget_amount_cents: int
    matched_source: Optional[str]
    source_type: str  # 'federal', 'state', 'county', 'local', 'unknown'
    confidence: str   # 'high', 'medium', 'low'
    acfr_fund: Optional[str]
    acfr_amount_cents: Optional[int]
    notes: str


# =============================================================================
# STEP 2: Keyword-based matching rules
# =============================================================================

# These are patterns that help us identify funding sources from budget line item names
FUNDING_PATTERNS = {
    # HIGH CONFIDENCE - explicit mentions
    'federal': [
        r'federal',
        r'cfda',
        r'fema',
        r'hud\b',
        r'dot\b',
        r'fhwa',
        r'cdbg',
        r'arpa',
        r'american rescue',
    ],
    'state': [
        r'state\b',
        r'prop\s*\d+',
        r'proposition',
        r'gas\s*tax',
        r'caltrans',
        r'sb\s*\d+',
        r'ab\s*\d+',
        r'motor vehicle',
        r'vehicle license',
    ],
    'county': [
        r'county',
        r'marin',
    ],

    # MEDIUM CONFIDENCE - generic grant language
    'grant_generic': [
        r'grant',
        r'subvention',
        r'allocation',
        r'reimbursement',
    ],
}

# Known mappings between budget fund names and ACFR funds
FUND_MAPPINGS = {
    'gas tax': 'Gas Tax Fund',
    'traffic mitigation': 'Traffic and Housing Mitigation Fund',
    'housing mitigation': 'Traffic and Housing Mitigation Fund',
    'general fund': 'General Fund',
    'capital projects': 'Essential Facilities Capital Projects Fund',
}


def classify_funding_source(line_item: str, fund: str) -> tuple[str, str]:
    """
    Classify a budget line item by its likely funding source.

    Returns:
        (source_type, confidence)
    """
    text = f"{line_item} {fund}".lower()

    # Check federal patterns first
    for pattern in FUNDING_PATTERNS['federal']:
        if re.search(pattern, text, re.IGNORECASE):
            return ('federal', 'high')

    # Check state patterns
    for pattern in FUNDING_PATTERNS['state']:
        if re.search(pattern, text, re.IGNORECASE):
            return ('state', 'high')

    # Check county patterns
    for pattern in FUNDING_PATTERNS['county']:
        if re.search(pattern, text, re.IGNORECASE):
            return ('county', 'high')

    # Check generic grant patterns
    for pattern in FUNDING_PATTERNS['grant_generic']:
        if re.search(pattern, text, re.IGNORECASE):
            return ('intergovernmental', 'medium')

    # Default to local/unknown
    return ('local', 'low')


def match_to_acfr_fund(line_item: str, fund: str) -> Optional[str]:
    """Try to match a budget item to an ACFR fund."""
    text = f"{line_item} {fund}".lower()

    for keyword, acfr_fund in FUND_MAPPINGS.items():
        if keyword in text:
            return acfr_fund

    return None


def reconcile_budget_with_acfr(budget_path: str, acfr_path: str) -> list[FundingMapping]:
    """
    Reconcile budget line items with ACFR data.

    Args:
        budget_path: Path to budget JSON
        acfr_path: Path to ACFR JSON

    Returns:
        List of FundingMapping objects
    """
    # Load data
    with open(budget_path) as f:
        budget = json.load(f)

    with open(acfr_path) as f:
        acfr = json.load(f)

    # Build ACFR lookup
    acfr_funds = {f['fund_name']: f for f in acfr.get('fund_mappings', [])}

    mappings = []

    for item in budget['items']:
        line_item = item['line_item']
        fund = item.get('fund', '')
        amount = item['budgeted_cents']

        # Skip small items and non-intergovernmental
        source_type, confidence = classify_funding_source(line_item, fund)

        # Try to match to ACFR fund
        acfr_fund_name = match_to_acfr_fund(line_item, fund)
        acfr_fund = acfr_funds.get(acfr_fund_name) if acfr_fund_name else None

        # Build notes
        notes = []
        if 'grant' in line_item.lower():
            notes.append("Contains 'grant' keyword")
        if acfr_fund:
            notes.append(f"Matched to ACFR fund: {acfr_fund_name}")

        mappings.append(FundingMapping(
            budget_item=line_item,
            budget_amount_cents=amount,
            matched_source=acfr_fund_name or source_type,
            source_type=source_type,
            confidence=confidence,
            acfr_fund=acfr_fund_name,
            acfr_amount_cents=acfr_fund['total_revenue_cents'] if acfr_fund else None,
            notes='; '.join(notes) if notes else 'No specific match found'
        ))

    return mappings


def print_reconciliation_report(mappings: list[FundingMapping]):
    """Print a human-readable reconciliation report."""

    print("\n" + "=" * 80)
    print("BUDGET → FUNDING SOURCE RECONCILIATION REPORT")
    print("=" * 80)

    # Group by source type
    by_source = {}
    for m in mappings:
        by_source.setdefault(m.source_type, []).append(m)

    for source_type in ['federal', 'state', 'county', 'intergovernmental', 'local']:
        items = by_source.get(source_type, [])
        if not items:
            continue

        # Only show items with grants or significant intergovernmental
        relevant = [i for i in items if
                    'grant' in i.budget_item.lower() or
                    i.source_type in ('federal', 'state', 'county', 'intergovernmental')]

        if not relevant:
            continue

        total = sum(i.budget_amount_cents for i in relevant)

        print(f"\n{'─' * 80}")
        print(f"📌 {source_type.upper()} FUNDING (Total: ${total/100:,.0f})")
        print(f"{'─' * 80}")

        # Sort by amount descending
        for m in sorted(relevant, key=lambda x: -x.budget_amount_cents)[:10]:
            amt = m.budget_amount_cents / 100
            conf_emoji = {'high': '🟢', 'medium': '🟡', 'low': '🔴'}[m.confidence]
            print(f"\n   {m.budget_item[:50]}")
            print(f"   Budget: ${amt:>12,.0f}  Confidence: {conf_emoji} {m.confidence}")
            if m.acfr_fund:
                acfr_amt = m.acfr_amount_cents / 100 if m.acfr_amount_cents else 0
                print(f"   ACFR Fund: {m.acfr_fund} (${acfr_amt:,.0f})")
            print(f"   Notes: {m.notes}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY BY FUNDING SOURCE")
    print("=" * 80)

    for source_type in ['federal', 'state', 'county', 'intergovernmental']:
        items = by_source.get(source_type, [])
        if items:
            total = sum(i.budget_amount_cents for i in items)
            high_conf = sum(1 for i in items if i.confidence == 'high')
            print(f"   {source_type:20} ${total/100:>12,.0f}  ({high_conf}/{len(items)} high confidence)")

    print("\n" + "=" * 80)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Reconcile budget with ACFR funding sources")
    parser.add_argument('--budget', default='data/budgets/san_rafael/FY25-26-extracted.json')
    parser.add_argument('--acfr', default='data/acfr/acfr-san-rafael-2024-2025.json')
    args = parser.parse_args()

    print("🔍 Loading budget and ACFR data...")
    mappings = reconcile_budget_with_acfr(args.budget, args.acfr)
    print_reconciliation_report(mappings)


if __name__ == '__main__':
    main()
