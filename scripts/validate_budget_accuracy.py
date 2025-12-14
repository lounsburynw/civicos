#!/usr/bin/env python3
"""
Budget Accuracy Validator - Hybrid 5-Layer Approach

Session 103: Implements comprehensive validation to prevent 15x budget inflation

Defensive Layers:
1. Pre-LLM Filtering: Exclude obvious noise (investment reports, etc.)
2. Improved Prompting: Enhanced LLM instructions (in analyzer)
3. Two-Pass Validation: Verify high-value budgets with second LLM call
4. Post-Processing Deduplication: Remove duplicate budget entries
5. Summary Validation: Sanity checks and reporting

Usage:
    # Validate and clean existing data
    python scripts/validate_budget_accuracy.py data/pilot/san_rafael_high_stakes_fast.json

    # With two-pass validation (more accurate, costs ~2x)
    python scripts/validate_budget_accuracy.py data/pilot/san_rafael_high_stakes_fast.json --two-pass

    # Generate validation report only (no output file)
    python scripts/validate_budget_accuracy.py data/pilot/san_rafael_high_stakes_fast.json --report-only
"""

import sys
import os
import json
import argparse
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from llm_provider import get_model_for_task


class BudgetAccuracyValidator:
    """
    Hybrid validation system with 5 defensive layers
    """

    # Layer 1: Pre-LLM filtering patterns
    INVESTMENT_PATTERNS = [
        r'investment\s+(report|portfolio)',
        r'quarterly\s+investment',
        r'portfolio\s+(report|review|update)',
        r'asset\s+management\s+report',
        r'chandler\s+asset'
    ]

    # Budget thresholds for flagging
    CITYWIDE_BUDGET_THRESHOLD = 100_000_000  # $100M+ likely citywide
    TWO_PASS_THRESHOLD = 10_000_000  # $10M+ gets second validation
    SAN_RAFAEL_ANNUAL_BUDGET = 192_282_438  # Known FY 2025-26 budget

    def __init__(self, enable_two_pass: bool = False):
        self.enable_two_pass = enable_two_pass
        self.validation_stats = {
            'layer1_filtered': 0,  # Investment reports excluded
            'layer3_validated': 0,  # Two-pass validation applied
            'layer3_rejected': 0,   # Two-pass validation rejected
            'layer4_duplicates': 0, # Deduplication removed
            'layer5_flagged': 0     # Summary validation flagged
        }

    def validate_and_clean(
        self,
        decisions: List[Dict],
        jurisdiction: str = "san-rafael"
    ) -> Tuple[List[Dict], Dict]:
        """
        Apply all validation layers and return cleaned decisions + report

        Returns:
            (cleaned_decisions, validation_report)
        """
        print("\n🔍 BUDGET ACCURACY VALIDATION - Hybrid 5-Layer Approach")
        print("=" * 70)

        # Layer 1: Pre-LLM filtering
        print("\n📋 Layer 1: Pre-LLM Filtering (Rule-Based)")
        decisions = self._layer1_filter_investment_reports(decisions)

        # Layer 2: Improved prompting (happens in analyzer, skip here)
        print("\n📝 Layer 2: Improved Prompting (N/A - in analyzer)")
        print("   ⏭️  Skipped (applies to future extractions)")

        # Layer 3: Two-pass validation (optional, costs 2x)
        if self.enable_two_pass:
            print("\n🔄 Layer 3: Two-Pass Validation (High-Value Items)")
            decisions = self._layer3_two_pass_validation(decisions)
        else:
            print("\n🔄 Layer 3: Two-Pass Validation (DISABLED)")
            print("   💡 Enable with --two-pass flag for highest accuracy")

        # Layer 4: Post-processing deduplication
        print("\n🗑️  Layer 4: Post-Processing Deduplication")
        decisions = self._layer4_deduplicate(decisions)

        # Layer 5: Summary validation
        print("\n✅ Layer 5: Summary Validation & Reporting")
        validation_report = self._layer5_summary_validation(decisions, jurisdiction)

        return decisions, validation_report

    def _layer1_filter_investment_reports(self, decisions: List[Dict]) -> List[Dict]:
        """
        Layer 1: Exclude investment reports, portfolio reports, etc.

        These are asset values, not budget expenditures.
        """
        import re

        filtered = []
        excluded = []

        for decision in decisions:
            title = decision.get('title', '') or ''
            budget_desc = decision.get('budget_description', '') or ''
            combined_text = f"{title} {budget_desc}".lower()

            # Check if matches investment pattern
            is_investment = any(
                re.search(pattern, combined_text, re.IGNORECASE)
                for pattern in self.INVESTMENT_PATTERNS
            )

            if is_investment and decision.get('budget_amount'):
                excluded.append({
                    'title': decision['title'],
                    'amount': decision['budget_amount'],
                    'reason': 'Investment/portfolio report (not budget expenditure)'
                })
                self.validation_stats['layer1_filtered'] += 1
            else:
                filtered.append(decision)

        print(f"   ✅ Filtered {len(excluded)} investment reports")
        if excluded:
            print(f"   📊 Examples:")
            for item in excluded[:3]:
                print(f"      • {item['title']}: ${item['amount']:,}")

        return filtered

    def _layer3_two_pass_validation(self, decisions: List[Dict]) -> List[Dict]:
        """
        Layer 3: Two-pass validation for high-value budgets

        Second LLM call verifies: "Is this a new appropriation or citywide total?"
        """
        validated = []
        llm = get_model_for_task("structured_extraction")

        for decision in decisions:
            budget = decision.get('budget_amount')

            # Only validate high-value items
            if not budget or budget < self.TWO_PASS_THRESHOLD:
                validated.append(decision)
                continue

            # Second pass: Validate attribution
            prompt = f"""You are validating budget extraction accuracy.

DECISION TITLE: {decision['title']}
BUDGET EXTRACTED: ${budget:,}
BUDGET DESCRIPTION: {decision.get('budget_description', 'N/A')}

Question: Is this budget a NEW APPROPRIATION for this specific agenda item, or is it a REFERENCE to the citywide total budget?

Answer with JSON:
{{
  "is_new_appropriation": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation"
}}

Examples:
- "Final Citywide Budget for FY 2025-26" → is_new_appropriation: false (citywide total)
- "$31M for Marin Transit Collaboration" → is_new_appropriation: true (specific project)
- "Mid-Year Personnel Changes" with $192M → is_new_appropriation: false (context pollution)
"""

            try:
                response = llm.chat([{"role": "user", "content": prompt}])
                validation = json.loads(response)

                if validation['is_new_appropriation'] and validation['confidence'] >= 0.7:
                    validated.append(decision)
                    self.validation_stats['layer3_validated'] += 1
                else:
                    print(f"   ❌ Rejected: {decision['title']} (${budget:,})")
                    print(f"      Reason: {validation['reasoning']}")
                    self.validation_stats['layer3_rejected'] += 1

            except Exception as e:
                print(f"   ⚠️  Validation error for {decision['title']}: {e}")
                # On error, keep the item (fail open)
                validated.append(decision)

        print(f"   ✅ Validated {self.validation_stats['layer3_validated']} high-value items")
        print(f"   ❌ Rejected {self.validation_stats['layer3_rejected']} misattributed budgets")

        return validated

    def _layer4_deduplicate(self, decisions: List[Dict]) -> List[Dict]:
        """
        Layer 4: Remove duplicate budget entries + citywide budgets

        Deduplication strategy:
        1. Exclude ANY item >$100M with citywide budget keywords (even singles)
        2. Group by (meeting_date + budget_amount)
        3. If multiple items with same budget same meeting:
           - Check if titles are similar (>80% match) → keep one
           - Otherwise, flag for manual review but keep all
        """
        from difflib import SequenceMatcher

        # First pass: Exclude citywide budgets (even singles)
        citywide_keywords = [
            'citywide budget', 'final budget', 'proposed budget',
            'general fund', 'capital improvement program',
            'mid-year', 'personnel changes', 'budget discussion'
        ]

        filtered_decisions = []
        citywide_excluded = 0

        for decision in decisions:
            budget = decision.get('budget_amount')
            title = decision.get('title', '').lower()

            # Exclude if >$100M AND contains budget keywords
            is_large_citywide = (
                budget and budget > self.CITYWIDE_BUDGET_THRESHOLD and
                any(kw in title for kw in citywide_keywords)
            )

            if is_large_citywide:
                print(f"   🚫 Excluded citywide budget: ${budget:,}")
                print(f"      Title: {decision['title']}")
                citywide_excluded += 1
                self.validation_stats['layer4_duplicates'] += 1
            else:
                filtered_decisions.append(decision)

        if citywide_excluded > 0:
            print(f"   ✅ Excluded {citywide_excluded} citywide budget items\n")

        # Group by meeting + budget (use filtered list)
        budget_groups = defaultdict(list)

        for decision in filtered_decisions:
            budget = decision.get('budget_amount')
            if budget:
                key = (decision.get('meeting_date'), budget)
                budget_groups[key].append(decision)

        # Deduplicate each group
        deduplicated = []
        duplicates_removed = 0

        for (meeting_date, budget), items in budget_groups.items():
            if len(items) == 1:
                deduplicated.extend(items)
                continue

            # Multiple items with same budget same meeting
            # Check title similarity
            def title_similarity(t1: str, t2: str) -> float:
                return SequenceMatcher(None, t1.lower(), t2.lower()).ratio()

            # Enhanced deduplication logic
            # Special case 1: Citywide budget (>$100M + budget keywords)
            is_citywide_budget = (
                budget > self.CITYWIDE_BUDGET_THRESHOLD and
                any(kw in ' '.join(item['title'].lower() for item in items)
                    for kw in ['citywide budget', 'final budget', 'proposed budget', 'capital improvement program'])
            )

            if is_citywide_budget:
                # This is the citywide budget appearing multiple times
                # Keep NONE of them (these are not specific appropriations)
                print(f"   🚫 Excluded citywide budget (appears {len(items)} times): ${budget:,}")
                print(f"      Reason: Overall city budget, not a specific appropriation")
                duplicates_removed += len(items)
                self.validation_stats['layer4_duplicates'] += len(items)
                continue

            # Find the most specific/descriptive title
            # Heuristic: Avoid generic titles like "Final Budget" or "Budget Approval"
            generic_keywords = ['final', 'approval', 'adoption', 'proposed']

            def is_generic(title: str) -> bool:
                return any(kw in title.lower() for kw in generic_keywords)

            # Keep most specific title
            sorted_items = sorted(items, key=lambda x: (is_generic(x['title']), len(x['title'])))
            best_item = sorted_items[-1]  # Longest, least generic

            # Check if all titles are similar (>80%) OR contain common project keywords
            all_similar = all(
                title_similarity(best_item['title'], item['title']) > 0.8
                for item in items
            )

            # Check for common project name (e.g., "Albert Park Library", "Pickleweed Library")
            common_project_keywords = set()
            for item in items:
                words = set(item['title'].lower().split())
                if not common_project_keywords:
                    common_project_keywords = words
                else:
                    common_project_keywords &= words

            has_common_project = len(common_project_keywords) >= 2  # At least 2 shared words

            # Special case: Budget amendments, carry-overs, and fiscal year adjustments
            # These often appear multiple times with similar but not identical titles
            budget_amendment_keywords = ['amendment', 'adjustment', 'carry-over', 'appropriation', 'fiscal year', 'fy']
            all_budget_amendments = all(
                any(kw in item['title'].lower() for kw in budget_amendment_keywords)
                for item in items
            )

            if all_similar or (has_common_project and len(items) >= 3) or (all_budget_amendments and len(items) >= 3):
                # Likely duplicates, keep one
                deduplicated.append(best_item)
                duplicates_removed += len(items) - 1
                self.validation_stats['layer4_duplicates'] += len(items) - 1

                print(f"   🗑️  Deduped {len(items)} items: ${budget:,}")
                print(f"      Kept: {best_item['title']}")
            else:
                # Titles differ significantly, might be different phases
                # Flag for manual review but keep all
                print(f"   ⚠️  Potential duplicates (keeping all for review): ${budget:,}")
                for item in items:
                    print(f"      • {item['title']}")
                deduplicated.extend(items)

        # Add non-budget decisions (from filtered list)
        for decision in filtered_decisions:
            if not decision.get('budget_amount'):
                deduplicated.append(decision)

        print(f"   ✅ Removed {duplicates_removed} clear duplicates")

        return deduplicated

    def _layer5_summary_validation(
        self,
        decisions: List[Dict],
        jurisdiction: str
    ) -> Dict:
        """
        Layer 5: Summary validation and sanity checks

        Generate comprehensive validation report
        """
        budget_decisions = [d for d in decisions if d.get('budget_amount')]
        total_budget = sum(d['budget_amount'] for d in budget_decisions)

        # Sanity checks
        flags = []

        # Flag 1: Total budget exceeds 2x annual budget
        if jurisdiction == "san-rafael":
            if total_budget > 2 * self.SAN_RAFAEL_ANNUAL_BUDGET:
                flags.append({
                    'severity': 'high',
                    'message': f"Total budget ${total_budget:,} exceeds 2x San Rafael annual budget",
                    'expected': f"<${2 * self.SAN_RAFAEL_ANNUAL_BUDGET:,}",
                    'actual': f"${total_budget:,}"
                })

        # Flag 2: Individual items exceeding citywide budget
        large_items = [
            d for d in budget_decisions
            if d['budget_amount'] > self.CITYWIDE_BUDGET_THRESHOLD
        ]

        if large_items:
            flags.append({
                'severity': 'medium',
                'message': f"{len(large_items)} items exceed $100M threshold",
                'items': [
                    {'title': d['title'], 'amount': d['budget_amount']}
                    for d in large_items
                ]
            })

        # Flag 3: Check for remaining duplicates
        amount_counts = defaultdict(int)
        for d in budget_decisions:
            amount_counts[d['budget_amount']] += 1

        frequent_amounts = {amt: count for amt, count in amount_counts.items() if count >= 3}
        if frequent_amounts:
            flags.append({
                'severity': 'low',
                'message': f"{len(frequent_amounts)} budget amounts appear 3+ times",
                'amounts': [
                    {'amount': amt, 'count': count}
                    for amt, count in sorted(frequent_amounts.items(), key=lambda x: -x[1])[:5]
                ]
            })

        # Print validation summary
        print(f"\n   📊 Validation Summary:")
        print(f"      Total decisions: {len(decisions)}")
        print(f"      Budget decisions: {len(budget_decisions)}")
        print(f"      Total budget tracked: ${total_budget:,}")
        print(f"\n   🚩 Flags ({len(flags)} total):")

        for flag in flags:
            severity_icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
            print(f"      {severity_icon[flag['severity']]} {flag['message']}")

        # Build report
        report = {
            'timestamp': datetime.now().isoformat(),
            'jurisdiction': jurisdiction,
            'validation_stats': self.validation_stats,
            'summary': {
                'total_decisions': len(decisions),
                'budget_decisions': len(budget_decisions),
                'total_budget_tracked': total_budget,
                'average_budget': total_budget / len(budget_decisions) if budget_decisions else 0
            },
            'flags': flags,
            'top_budgets': sorted(
                [{'title': d['title'], 'amount': d['budget_amount']} for d in budget_decisions],
                key=lambda x: -x['amount']
            )[:10]
        }

        return report


def main():
    parser = argparse.ArgumentParser(
        description='Validate and clean budget accuracy in retrospective analysis'
    )
    parser.add_argument(
        'input_file',
        help='Input JSON file (e.g., san_rafael_high_stakes_fast.json)'
    )
    parser.add_argument(
        '--output',
        help='Output file for cleaned data (default: input_file with _validated suffix)'
    )
    parser.add_argument(
        '--two-pass',
        action='store_true',
        help='Enable two-pass validation for high-value items (costs ~2x, highest accuracy)'
    )
    parser.add_argument(
        '--report-only',
        action='store_true',
        help='Generate validation report only (no output file)'
    )
    parser.add_argument(
        '--jurisdiction',
        default='san-rafael',
        help='Jurisdiction name for context-specific validation'
    )

    args = parser.parse_args()

    # Load input data
    print(f"📂 Loading: {args.input_file}")
    with open(args.input_file, 'r') as f:
        data = json.load(f)

    decisions = data.get('decisions', [])
    print(f"   Loaded {len(decisions)} decisions")

    # Run validation
    validator = BudgetAccuracyValidator(enable_two_pass=args.two_pass)
    cleaned_decisions, validation_report = validator.validate_and_clean(
        decisions,
        jurisdiction=args.jurisdiction
    )

    # Save cleaned data
    if not args.report_only:
        output_file = args.output or args.input_file.replace('.json', '_validated.json')

        cleaned_data = {
            **data,
            'decisions': cleaned_decisions,
            'validation_report': validation_report
        }

        with open(output_file, 'w') as f:
            json.dump(cleaned_data, f, indent=2)

        print(f"\n💾 Saved cleaned data: {output_file}")
    else:
        print("\n📋 Report-only mode (no output file)")

    # Save validation report
    report_file = args.input_file.replace('.json', '_validation_report.json')
    with open(report_file, 'w') as f:
        json.dump(validation_report, f, indent=2)

    print(f"📊 Saved validation report: {report_file}")

    # Print final metrics
    print("\n" + "=" * 70)
    print("✅ VALIDATION COMPLETE")
    print("=" * 70)
    print(f"Original decisions: {len(decisions)}")
    print(f"Cleaned decisions: {len(cleaned_decisions)}")
    print(f"Removed: {len(decisions) - len(cleaned_decisions)}")
    print(f"\nTotal budget: ${validation_report['summary']['total_budget_tracked']:,}")
    print(f"Budget decisions: {validation_report['summary']['budget_decisions']}")
    print(f"Average budget: ${validation_report['summary']['average_budget']:,.0f}")


if __name__ == '__main__':
    main()
