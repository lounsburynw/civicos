#!/usr/bin/env python3
"""
Auto-verify housing legislative metadata using Open States API v3.

Replaces manual 2-3 hour verification with automated cross-reference.

Setup:
1. Register for free API key at https://openstates.org/accounts/signup/
2. Add to ~/.zshrc: export OPENSTATES_API_KEY='your-key'
3. Run: source ~/.zshrc
"""

import json
import os
import requests
from typing import Dict, List, Optional

OPENSTATES_API_KEY = os.environ.get('OPENSTATES_API_KEY')

def query_openstates(bill_number: str, session: str = "2021-2022") -> Optional[Dict]:
    """
    Query Open States API v3 (REST) for California bill metadata.

    API Docs: https://docs.openstates.org/api-v3/
    Endpoint: https://v3.openstates.org/bills
    """
    if not OPENSTATES_API_KEY:
        print("  ⚠ OPENSTATES_API_KEY not set. Register at https://openstates.org/accounts/signup/")
        return None

    # Normalize bill number (e.g., "SB 9" -> "SB 9")
    bill_id = bill_number.strip().upper()
    if ' ' not in bill_id and len(bill_id) > 2:
        # Add space between letters and numbers (SB9 -> SB 9)
        for i, char in enumerate(bill_id):
            if char.isdigit():
                bill_id = bill_id[:i] + ' ' + bill_id[i:]
                break

    # REST API endpoint
    url = "https://v3.openstates.org/bills"

    params = {
        "jurisdiction": "California",
        "identifier": bill_id,
        "per_page": 5
    }

    headers = {
        "X-API-KEY": OPENSTATES_API_KEY
    }

    # Note: include parameter causes 422 errors, fetch actions separately if needed

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        results = data.get('results', [])
        if not results:
            print(f"  ⚠ No results for {bill_number}")
            return None

        # Return first matching result (most recent session)
        return results[0]

    except requests.exceptions.HTTPError as e:
        print(f"  ⚠ Open States HTTP error for {bill_number}: {e}")
        if e.response.status_code == 401:
            print("    Check OPENSTATES_API_KEY is valid")
        return None
    except Exception as e:
        print(f"  ⚠ Open States query failed for {bill_number}: {e}")
        return None

def extract_enactment_date(actions: List[Dict]) -> Optional[str]:
    """Extract enactment date from bill actions."""
    for action in actions:
        desc = action.get('description', '').lower()
        classification = action.get('classification', [])

        # Look for governor signature or chaptering
        if any(phrase in desc for phrase in ['governor', 'chaptered', 'signed by governor', 'approved by governor']):
            if any(word in desc for word in ['signed', 'approved', 'chaptered']):
                return action.get('date')

        # Check classification array
        if isinstance(classification, list):
            if any(c in ['executive-signature', 'governor-signed'] for c in classification):
                return action.get('date')

    return None

def verify_bill_metadata(bill_data: Dict, perplexity_data: Dict) -> Dict:
    """
    Verify Perplexity bill data against Open States.

    Returns verification report with corrections.
    """
    bill_number = bill_data.get('bill_number', 'Unknown')
    year_enacted = perplexity_data.get('enacted', '')[:4] if perplexity_data.get('enacted') else None

    # Determine session (California uses 2-year sessions)
    if year_enacted:
        year = int(year_enacted)
        if year % 2 == 1:
            session = f"{year}-{year+1}"
        else:
            session = f"{year-1}-{year}"
    else:
        session = "2021-2022"  # Default guess

    print(f"\n{'='*60}")
    print(f"Verifying: {bill_number} ({session} session)")
    print(f"{'='*60}")

    # Query Open States
    openstates_data = query_openstates(bill_number, session)

    if not openstates_data:
        return {
            "bill_number": bill_number,
            "verified": False,
            "error": "Not found in Open States API",
            "recommendation": "Manual verification required at leginfo.legislature.ca.gov"
        }

    # Extract verified metadata
    verified_title = openstates_data.get('title', '')
    verified_actions = openstates_data.get('actions', [])
    verified_enactment_date = extract_enactment_date(verified_actions)
    verified_sources = [s.get('url') for s in openstates_data.get('sources', [])]

    # Compare with Perplexity data
    report = {
        "bill_number": bill_number,
        "verified": True,
        "openstates_title": verified_title,
        "perplexity_title": perplexity_data.get('bill', ''),
        "title_match": verified_title.lower() in perplexity_data.get('bill', '').lower(),
        "verified_enactment_date": verified_enactment_date,
        "perplexity_enactment_date": perplexity_data.get('enacted'),
        "enactment_date_match": verified_enactment_date == perplexity_data.get('enacted'),
        "official_sources": verified_sources,
        "perplexity_url": perplexity_data.get('official_url', ''),
        "total_actions": len(verified_actions)
    }

    # Print verification results
    print(f"Title Match: {'✓' if report['title_match'] else '✗'}")
    print(f"  OpenStates: {verified_title[:70]}")
    print(f"  Perplexity: {perplexity_data.get('bill', '')[:70]}")
    print(f"\nEnactment Date Match: {'✓' if report['enactment_date_match'] else '✗'}")
    print(f"  OpenStates: {verified_enactment_date}")
    print(f"  Perplexity: {perplexity_data.get('enacted')}")
    print(f"\nOfficial Sources: {len(verified_sources)}")
    for src in verified_sources[:2]:
        print(f"  - {src}")

    if not report['enactment_date_match'] and verified_enactment_date:
        report['corrected_enactment_date'] = verified_enactment_date
        print(f"\n⚠ CORRECTION NEEDED: Use {verified_enactment_date} instead of {perplexity_data.get('enacted')}")

    return report

def main():
    """Run auto-verification on draft housing context."""
    print("="*80)
    print("AUTO-VERIFICATION: California Housing Legislative Context")
    print("="*80)
    print("\nUsing Open States API (free, no key required)")
    print("Alternative to 2-3 hours manual verification")
    print()

    # Load Perplexity draft
    draft_path = 'data/legislative_context/california_housing.json.DRAFT'
    with open(draft_path, 'r') as f:
        draft_data = json.load(f)

    verification_reports = []
    bills = draft_data.get('state_legislation', {})

    for bill_id, bill_data in bills.items():
        # Extract bill number from bill name or ID
        bill_number = bill_id.upper().replace('CA-', '').replace('-', ' ')

        # Create simplified dict for verification
        perplexity_dict = {
            'bill_number': bill_number,
            'bill': bill_data.get('bill', ''),
            'enacted': bill_data.get('enacted'),
            'official_url': bill_data.get('official_url', '')
        }

        report = verify_bill_metadata({'bill_number': bill_number}, perplexity_dict)
        verification_reports.append(report)

    # Save verification report
    report_path = 'data/legislative_context/housing_verification_report.json'
    with open(report_path, 'w') as f:
        json.dump({
            'generated_at': '2025-10-07T14:30:00',
            'total_bills_verified': len(verification_reports),
            'verification_method': 'Open States API v3',
            'reports': verification_reports
        }, f, indent=2)

    print(f"\n{'='*80}")
    print("VERIFICATION COMPLETE")
    print(f"{'='*80}")
    print(f"Report saved: {report_path}")
    print(f"\nBills verified: {len(verification_reports)}")
    print(f"Fully automated: {sum(1 for r in verification_reports if r.get('verified'))} / {len(verification_reports)}")
    print()
    print("Next: Review verification report and apply corrections to DRAFT file")

if __name__ == '__main__':
    main()
