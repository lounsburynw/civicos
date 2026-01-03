#!/usr/bin/env python3
"""
Extract intergovernmental funding mapping from ACFR (Annual Comprehensive Financial Report).

An ACFR is the official audited financial statement that cities produce annually.
It contains the authoritative mapping between:
- Federal/state/county grants → city programs
- Revenue sources → expenditure categories
- Fund types → specific uses

This is HOW government officials reconcile funding sources with budget line items.

Usage:
    python scripts/extract_acfr_funding_mapping.py ~/Downloads/san-rafael-acfr-2025.pdf
    python scripts/extract_acfr_funding_mapping.py ~/Downloads/san-rafael-acfr-2025.pdf --output data/acfr/
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Add packages to path (not needed for direct Gemini usage, but kept for potential future use)
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic-services" / "src"))


ACFR_EXTRACTION_PROMPT = """# ACFR Intergovernmental Funding Analysis

You are analyzing an Annual Comprehensive Financial Report (ACFR) for a California city.
Your goal is to extract the official mappings between intergovernmental revenue sources
and the city programs/funds they support.

## Key Sections to Find

1. **Schedule of Expenditures of Federal Awards (SEFA)**
   - Lists all federal grants by CFDA number
   - Shows expenditures for each federal program
   - This is the authoritative federal funding breakdown

2. **Intergovernmental Revenue Notes**
   - Breaks down state, federal, and county revenues
   - Often in "Notes to Financial Statements"

3. **Fund Financial Statements**
   - Shows which revenues flow to which funds
   - General Fund, Special Revenue Funds, Capital Projects, etc.

4. **Grant Revenue Details**
   - Specific grants and their purposes
   - Matching requirements, restrictions

## Output Format

Return a JSON object with this structure:

```json
{
  "jurisdiction": "City of San Rafael",
  "fiscal_year": "2024-2025",
  "acfr_date": "2025-XX-XX",

  "federal_awards": [
    {
      "cfda_number": "20.205",
      "program_name": "Highway Planning and Construction",
      "federal_agency": "Department of Transportation",
      "expenditures_cents": 123456700,
      "city_program": "Public Works - Street Improvements",
      "fund": "Capital Projects Fund",
      "notes": "Passed through Caltrans"
    }
  ],

  "state_revenues": [
    {
      "source": "Motor Vehicle In-Lieu Tax",
      "amount_cents": 450000000,
      "fund": "General Fund",
      "restrictions": "Unrestricted",
      "notes": "Proposition 172"
    }
  ],

  "county_revenues": [
    {
      "source": "Sales Tax Pass-through",
      "amount_cents": 90000000,
      "fund": "General Fund",
      "program": null,
      "notes": "Marin County"
    }
  ],

  "fund_mappings": [
    {
      "fund_name": "Gas Tax Fund",
      "fund_type": "Special Revenue",
      "total_revenue_cents": 880000000,
      "revenue_sources": ["State Gas Tax", "Federal Highway Funds"],
      "restricted_use": "Street maintenance and improvements"
    }
  ],

  "key_reconciliations": [
    {
      "description": "Gas tax revenue in budget vs ACFR",
      "budget_amount_cents": 880000000,
      "acfr_amount_cents": 875000000,
      "difference_explanation": "Timing differences in fund transfers"
    }
  ],

  "extraction_notes": "Findings, caveats, or missing sections"
}
```

## Instructions

1. Focus on INTERGOVERNMENTAL funding - skip local taxes (property, sales from own residents)
2. Convert ALL amounts to cents (multiply dollars by 100)
3. Include CFDA numbers for federal awards when available
4. Note which city fund receives each revenue source
5. Identify any pass-through arrangements (e.g., county passes federal funds)
6. Include page numbers for key findings in notes fields

Now analyze the ACFR document and extract the intergovernmental funding mappings.
"""


def extract_acfr_funding(pdf_path: str, output_dir: str = None) -> dict:
    """
    Extract intergovernmental funding mappings from an ACFR PDF.

    Uses Gemini 2.0 Flash (1M context) for large document analysis with native PDF support.
    """
    import google.generativeai as genai

    pdf_path = Path(pdf_path).expanduser().resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"📄 Loading ACFR: {pdf_path}")
    print(f"   Size: {pdf_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Configure Gemini with API key
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
    genai.configure(api_key=api_key)

    # Use Gemini 2.0 Flash for native PDF support
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    print(f"   Model: gemini-2.0-flash-exp (1M context)")

    print(f"\n🔍 Analyzing ACFR for intergovernmental funding mappings...")
    print(f"   This may take 1-2 minutes for large documents...\n")

    # Upload PDF file for native document processing
    print("   Uploading PDF to Gemini...")
    uploaded_file = genai.upload_file(pdf_path, mime_type="application/pdf")
    print(f"   Upload complete: {uploaded_file.name}")

    # Generate content with PDF and prompt
    response = model.generate_content(
        [uploaded_file, ACFR_EXTRACTION_PROMPT],
        generation_config={
            'temperature': 0.1,  # Low temp for accurate extraction
            'max_output_tokens': 8192,
        }
    )

    # Extract JSON from response
    response_text = response.text

    # Parse JSON (handle markdown code blocks)
    import re
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = response_text

    result = json.loads(json_str)

    # Add metadata
    result["_extraction_metadata"] = {
        "source_file": str(pdf_path),
        "extraction_date": datetime.now().isoformat(),
        "model": "gemini-2.0-flash-exp",
    }

    # Save if output directory specified
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate filename from jurisdiction and fiscal year
        jurisdiction_slug = result.get("jurisdiction", "unknown").lower().replace(" ", "-").replace("city-of-", "")
        fiscal_year = result.get("fiscal_year", "unknown").replace("/", "-")
        output_file = output_path / f"acfr-{jurisdiction_slug}-{fiscal_year}.json"

        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)

        print(f"\n💾 Saved to: {output_file}")

    return result


def print_summary(result: dict):
    """Print a human-readable summary of the extraction."""
    print("\n" + "=" * 70)
    print(f"ACFR FUNDING MAPPING SUMMARY")
    print(f"Jurisdiction: {result.get('jurisdiction', 'Unknown')}")
    print(f"Fiscal Year: {result.get('fiscal_year', 'Unknown')}")
    print("=" * 70)

    # Federal awards
    federal = result.get("federal_awards", [])
    if federal:
        print(f"\n📊 FEDERAL AWARDS ({len(federal)} programs)")
        total_federal = sum(a.get("expenditures_cents", 0) for a in federal)
        print(f"   Total: ${total_federal / 100:,.0f}")
        for award in federal[:5]:  # Show first 5
            cfda = award.get("cfda_number", "N/A")
            name = award.get("program_name", "Unknown")[:50]
            amt = award.get("expenditures_cents", 0) / 100
            print(f"   • {cfda}: {name} (${amt:,.0f})")
        if len(federal) > 5:
            print(f"   ... and {len(federal) - 5} more programs")

    # State revenues
    state = result.get("state_revenues", [])
    if state:
        print(f"\n📊 STATE REVENUES ({len(state)} sources)")
        total_state = sum(s.get("amount_cents", 0) for s in state)
        print(f"   Total: ${total_state / 100:,.0f}")
        for rev in state[:5]:
            source = rev.get("source", "Unknown")[:40]
            amt = rev.get("amount_cents", 0) / 100
            fund = rev.get("fund", "")
            print(f"   • {source}: ${amt:,.0f} → {fund}")
        if len(state) > 5:
            print(f"   ... and {len(state) - 5} more sources")

    # County revenues
    county = result.get("county_revenues", [])
    if county:
        print(f"\n📊 COUNTY REVENUES ({len(county)} sources)")
        total_county = sum(c.get("amount_cents", 0) for c in county)
        print(f"   Total: ${total_county / 100:,.0f}")
        for rev in county:
            source = rev.get("source", "Unknown")[:40]
            amt = rev.get("amount_cents", 0) / 100
            print(f"   • {source}: ${amt:,.0f}")

    # Fund mappings
    funds = result.get("fund_mappings", [])
    if funds:
        print(f"\n📁 FUND MAPPINGS ({len(funds)} funds)")
        for fund in funds[:5]:
            name = fund.get("fund_name", "Unknown")
            sources = ", ".join(fund.get("revenue_sources", [])[:3])
            use = fund.get("restricted_use", "")[:50]
            print(f"   • {name}")
            print(f"     Sources: {sources}")
            if use:
                print(f"     Use: {use}")

    # Key reconciliations
    recons = result.get("key_reconciliations", [])
    if recons:
        print(f"\n🔄 KEY RECONCILIATIONS")
        for rec in recons:
            desc = rec.get("description", "")[:60]
            print(f"   • {desc}")

    # Notes
    if notes := result.get("extraction_notes"):
        print(f"\n📝 NOTES: {notes}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Extract intergovernmental funding mappings from ACFR PDFs"
    )
    parser.add_argument(
        "pdf_path",
        help="Path to ACFR PDF file"
    )
    parser.add_argument(
        "--output", "-o",
        default="data/acfr/",
        help="Output directory for extracted JSON (default: data/acfr/)"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save output, just print summary"
    )

    args = parser.parse_args()

    try:
        result = extract_acfr_funding(
            args.pdf_path,
            output_dir=None if args.no_save else args.output
        )
        print_summary(result)

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse response as JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
