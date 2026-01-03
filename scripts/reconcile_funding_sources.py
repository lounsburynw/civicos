#!/usr/bin/env python3
"""
Reconcile budget line items with ACFR actuals and external funding sources.

This script attempts to answer: "Where does this budget line item's money come from?"

Usage:
    python scripts/reconcile_funding_sources.py
    python scripts/reconcile_funding_sources.py --budget data/budgets/san_rafael/FY25-26-extracted.json
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional

# Add packages to path for manifest imports
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic-extraction" / "src"))

from civic_extraction.manifest import IngestionManifest, SourceEntry, save_manifest

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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "budget_item": self.budget_item,
            "budget_amount_cents": self.budget_amount_cents,
            "matched_source": self.matched_source,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "acfr_fund": self.acfr_fund,
            "acfr_amount_cents": self.acfr_amount_cents,
            "notes": self.notes,
        }


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


# =============================================================================
# STEP 5: JSON output and manifest integration
# =============================================================================


def create_reconciliation_report(
    mappings: list[FundingMapping],
    budget_data: dict,
    acfr_data: dict,
) -> dict[str, Any]:
    """
    Create a structured reconciliation report for JSON output.

    Args:
        mappings: List of FundingMapping objects from reconciliation
        budget_data: Original budget JSON data
        acfr_data: Original ACFR JSON data

    Returns:
        Dictionary suitable for JSON serialization
    """
    # Group by source type and calculate summaries
    by_source: dict[str, list[FundingMapping]] = {}
    for m in mappings:
        by_source.setdefault(m.source_type, []).append(m)

    summary_by_source = {}
    for source_type, items in by_source.items():
        total_cents = sum(i.budget_amount_cents for i in items)
        high_confidence = sum(1 for i in items if i.confidence == "high")
        summary_by_source[source_type] = {
            "count": len(items),
            "amount_cents": total_cents,
            "high_confidence_count": high_confidence,
        }

    # Count matched vs unmatched
    matched_items = [m for m in mappings if m.acfr_fund is not None]
    unmatched_items = [m for m in mappings if m.acfr_fund is None]

    return {
        "jurisdiction_id": budget_data.get("jurisdiction_id", "unknown"),
        "budget_fiscal_year": budget_data.get("fiscal_year", "unknown"),
        "acfr_fiscal_year": acfr_data.get("fiscal_year", "unknown"),
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_items": len(mappings),
            "matched_items": len(matched_items),
            "unmatched_items": len(unmatched_items),
            "by_source_type": summary_by_source,
        },
        "items": [m.to_dict() for m in mappings],
    }


def save_reconciliation_with_manifest(
    budget_path: str,
    acfr_path: str,
    output_dir: str = "data/reconciliation",
    jurisdiction_id: Optional[str] = None,
) -> tuple[dict[str, Any], str, str]:
    """
    Run reconciliation, save report JSON, and create manifest for provenance tracking.

    Args:
        budget_path: Path to budget JSON
        acfr_path: Path to ACFR JSON
        output_dir: Directory to save reconciliation outputs
        jurisdiction_id: Override jurisdiction ID (defaults to budget file's value)

    Returns:
        Tuple of (report_dict, report_path, manifest_path)
    """
    # Load data for report metadata
    with open(budget_path) as f:
        budget_data = json.load(f)
    with open(acfr_path) as f:
        acfr_data = json.load(f)

    # Resolve jurisdiction
    jid = jurisdiction_id or budget_data.get("jurisdiction_id", "unknown")

    # Run reconciliation
    mappings = reconcile_budget_with_acfr(budget_path, acfr_path)

    # Create structured report
    report = create_reconciliation_report(mappings, budget_data, acfr_data)

    # Create manifest for provenance
    manifest = IngestionManifest.create(
        jurisdiction_id=jid,
        run_type="manual",
    )

    # Add source entry for reconciliation
    records_matched = report["summary"]["matched_items"]
    records_unmatched = report["summary"]["unmatched_items"]
    manifest.sources.append(
        SourceEntry(
            source_id="budget-acfr-reconciliation",
            source_type="reconciliation",
            records_ingested=records_matched,
            records_failed=0,
            records_skipped=records_unmatched,
        )
    )

    # Add file checksums for input provenance
    manifest.add_file_checksum("budget", budget_path)
    manifest.add_file_checksum("acfr", acfr_path)

    # Add metadata about the reconciliation
    manifest.metadata["budget_file"] = budget_path
    manifest.metadata["acfr_file"] = acfr_path
    manifest.metadata["budget_fiscal_year"] = report["budget_fiscal_year"]
    manifest.metadata["acfr_fiscal_year"] = report["acfr_fiscal_year"]
    manifest.metadata["reconciliation_algorithm"] = "keyword_pattern_v1"

    # Mark as success
    manifest.success = True

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Add report checksum before saving
    report_json = json.dumps(report, indent=2)
    manifest.add_checksum("report", report_json.encode("utf-8"))

    # Add manifest ID to report for cross-reference
    report["manifest_id"] = manifest.ingestion_id

    # Save report
    report_filename = f"reconciliation-{manifest.ingestion_id}.json"
    report_path = os.path.join(output_dir, report_filename)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Save manifest to manifest directory
    manifest_dir = os.path.join(output_dir, "manifests")
    manifest_path = save_manifest(manifest, manifest_dir)

    return report, report_path, manifest_path


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Reconcile budget with ACFR funding sources",
        epilog="""
Examples:
  # Print human-readable report only
  python scripts/reconcile_funding_sources.py

  # Save JSON report with manifest (default output dir: data/reconciliation/)
  python scripts/reconcile_funding_sources.py --save

  # Save to custom output directory
  python scripts/reconcile_funding_sources.py --save --output /tmp/reconciliation

  # Save JSON report without manifest (for debugging)
  python scripts/reconcile_funding_sources.py --save --no-manifest
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--budget', default='data/budgets/san_rafael/FY25-26-extracted.json',
                        help='Path to budget JSON file')
    parser.add_argument('--acfr', default='data/acfr/acfr-san-rafael-2024-2025.json',
                        help='Path to ACFR JSON file')
    parser.add_argument('--save', action='store_true',
                        help='Save JSON report and manifest (default: print human-readable only)')
    parser.add_argument('--output', default='data/reconciliation',
                        help='Output directory for JSON report and manifest')
    parser.add_argument('--no-manifest', action='store_true',
                        help='Skip manifest creation (only valid with --save)')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress human-readable output (only valid with --save)')
    args = parser.parse_args()

    print("🔍 Loading budget and ACFR data...")

    if args.save:
        if args.no_manifest:
            # Save JSON report only, no manifest
            with open(args.budget) as f:
                budget_data = json.load(f)
            with open(args.acfr) as f:
                acfr_data = json.load(f)

            mappings = reconcile_budget_with_acfr(args.budget, args.acfr)
            report = create_reconciliation_report(mappings, budget_data, acfr_data)

            os.makedirs(args.output, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(args.output, f"reconciliation-{timestamp}.json")
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)

            print(f"✅ Report saved to: {report_path}")
        else:
            # Save with manifest (full provenance tracking)
            report, report_path, manifest_path = save_reconciliation_with_manifest(
                args.budget,
                args.acfr,
                args.output,
            )
            print(f"✅ Report saved to: {report_path}")
            print(f"✅ Manifest saved to: {manifest_path}")
            print(f"   Manifest ID: {report['manifest_id']}")

        if not args.quiet:
            # Also print human-readable report
            mappings = reconcile_budget_with_acfr(args.budget, args.acfr)
            print_reconciliation_report(mappings)
    else:
        # Original behavior: print human-readable report only
        mappings = reconcile_budget_with_acfr(args.budget, args.acfr)
        print_reconciliation_report(mappings)


if __name__ == '__main__':
    main()
