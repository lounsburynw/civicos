#!/usr/bin/env python3
"""
Extract San Rafael FY 2025-26 budget data and store in database.

This script uses the budget extraction template from civic_extraction
to parse budget data from the extracted PDF text files.

Usage:
    python scripts/extract_san_rafael_budget.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic-extraction" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic" / "src"))

from civic_extraction.prompts.budget_extraction import (
    BudgetExtractionResult,
    BudgetLineItem,
    BudgetTotals,
    dollars_to_cents,
    cents_to_dollars_str,
)


def extract_general_fund_budget() -> list[BudgetLineItem]:
    """
    Extract General Fund budget items from the parsed data.

    Hand-extracted from FY25-26-General-Fund-Budget.pdf because
    the tabular format is well-structured.
    """
    # Department budgets from FY25-26 Proposed Budget column
    departments = [
        ("Finance", 2_522_312),
        ("Non-Departmental", 7_761_848),
        ("City Manager/City Council", 5_264_286),
        ("City Clerk", 1_029_218),
        ("Digital Service", 2_418_449),
        ("Human Resources", 1_044_641),
        ("City Attorney", 1_353_983),
        ("Community and Economic Development", 6_644_754),
        ("Police", 30_870_956),
        ("Fire", 25_981_329),
        ("Public Works", 16_114_681),
        ("Library", 3_531_973),
    ]

    items = []
    for dept_name, amount in departments:
        items.append(BudgetLineItem(
            fund="General Fund",
            department=dept_name,
            program=None,
            line_item=f"{dept_name} Department",
            budgeted_cents=dollars_to_cents(amount),
            source_page=1,
            notes=None,
        ))

    return items


def extract_other_funds_budget() -> list[BudgetLineItem]:
    """
    Extract Other Funds budget items from the parsed data.

    Hand-extracted from FY25-26-Fund-Summary-Other-Funds.pdf.
    Using "Total Operating Budget" column for appropriations.
    """
    # Special Revenue & Grant Funds
    special_revenue = [
        ("Storm Water Fund", "Special Revenue", 703_992, 1_235_000),  # operating, capital
        ("Gas Tax", "Special Revenue", 1_475_000, 8_764_204),
        ("Child Care", "Special Revenue", 3_516_641, 0),
        ("Paramedic/EMS", "Special Revenue", 10_155_208, 0),
        ("Cannabis", "Special Revenue", 145_375, 0),
        ("Recreation Revolving", "Special Revenue", 5_002_010, 0),
        ("Pt. San Pedro A.D. Maintenance", "Assessment District", 183_186, 0),
        ("Baypoint Lagoons L & L Assessment District", "Assessment District", 34_700, 0),
        ("Loch Lomond CFD #10", "Assessment District", 28_855, 0),
        ("Loch Lomond Marina CFD #2", "Assessment District", 150_030, 0),
        ("Parkland Dedication", "Special Revenue", 375_000, 0),
        ("Measure A Open Space", "Special Revenue", 50_000, 400_000),
        ("Measure C Wildfire Prevention", "Special Revenue", 3_946_920, 0),
        ("Low and Moderate Income Housing Fund", "Special Revenue", 85_770, 0),
    ]

    # Library Funds
    library_funds = [
        ("Library Revolving", "Library", 192_392, 0),
        ("Library Special Assessment Fund", "Library", 1_599_342, 0),
    ]

    # Public Safety Funds
    public_safety = [
        ("Abandoned Vehicle", "Public Safety", 190_505, 0),
        ("Youth Services - Police", "Public Safety", 40_043, 0),
    ]

    # Traffic & Housing Mitigation
    traffic_housing = [
        ("East S.R. Traffic Mitigation", "Traffic Mitigation", 400_000, 0),
    ]

    # Grant Funds
    grants = [
        ("Pickleweed Childcare Grant", "Grant", 704_824, 0),
        ("Public Safety Grants", "Grant", 577_811, 0),
        ("Grant-Other", "Grant", 1_810_565, 0),
    ]

    # Capital Project Funds
    capital = [
        ("Capital Improvement", "Capital Projects", 350_000, 704_000),
        ("Measure E - Public Safety Facilities", "Capital Projects", 0, 880_000),
        ("Measure P - Library Project", "Capital Projects", 125_000, 1_500_000),
    ]

    # Enterprise Fund
    enterprise = [
        ("Parking Services", "Enterprise", 4_118_171, 0),
    ]

    # Internal Service Funds
    internal_service = [
        ("Sewer Maintenance", "Internal Service", 3_773_508, 0),
        ("Vehicle Replacement", "Internal Service", 430_000, 0),
        ("Technology Replacement", "Internal Service", 3_489_856, 0),
        ("Fire Equipment Replacement", "Internal Service", 506_000, 0),
        ("Building Improvement", "Internal Service", 363_000, 2_475_000),
        ("Employee Benefits", "Internal Service", 822_754, 0),
        ("Liability Insurance", "Internal Service", 5_110_857, 0),
        ("Workers Compensation Insurance", "Internal Service", 3_680_586, 0),
        ("Dental Insurance", "Internal Service", 495_000, 0),
        ("Radio Replacement", "Internal Service", 550_000, 0),
        ("Telephone/Internet", "Internal Service", 694_540, 0),
        ("Employee Retirement", "Internal Service", 4_000, 0),
        ("Retiree Health Benefit OPEB", "Internal Service", 3_660_000, 0),
        ("Police Equipment Replacement", "Internal Service", 130_000, 0),
    ]

    items = []
    page = 1  # Page 1 for most funds

    def add_fund_items(fund_list, source_page=1):
        """Add items from a fund list."""
        for item_data in fund_list:
            name, fund_type, operating, capital_amt = item_data

            # Add operating budget if non-zero
            if operating > 0:
                items.append(BudgetLineItem(
                    fund=fund_type,
                    department=None,
                    program=name,
                    line_item=f"{name} - Operating",
                    budgeted_cents=dollars_to_cents(operating),
                    source_page=source_page,
                    notes=None,
                ))

            # Add capital budget if non-zero
            if capital_amt > 0:
                items.append(BudgetLineItem(
                    fund=fund_type,
                    department=None,
                    program=name,
                    line_item=f"{name} - Capital",
                    budgeted_cents=dollars_to_cents(capital_amt),
                    source_page=source_page,
                    notes="Capital budget",
                ))

    # Add all fund items
    add_fund_items(special_revenue, source_page=1)
    add_fund_items(library_funds, source_page=1)
    add_fund_items(public_safety, source_page=1)
    add_fund_items(traffic_housing, source_page=1)
    add_fund_items(grants, source_page=1)
    add_fund_items(capital, source_page=2)
    add_fund_items(enterprise, source_page=2)
    add_fund_items(internal_service, source_page=2)

    return items


def build_extraction_result() -> BudgetExtractionResult:
    """Build complete extraction result from all sources."""

    # Combine all items
    general_fund_items = extract_general_fund_budget()
    other_fund_items = extract_other_funds_budget()
    all_items = general_fund_items + other_fund_items

    # Calculate totals
    general_fund_total = sum(
        item.budgeted_cents for item in all_items
        if item.fund == "General Fund"
    )

    special_revenue_total = sum(
        item.budgeted_cents for item in all_items
        if item.fund in ("Special Revenue", "Assessment District", "Library",
                         "Public Safety", "Traffic Mitigation", "Grant")
    )

    capital_total = sum(
        item.budgeted_cents for item in all_items
        if item.fund == "Capital Projects"
    )

    enterprise_total = sum(
        item.budgeted_cents for item in all_items
        if item.fund == "Enterprise"
    )

    internal_service_total = sum(
        item.budgeted_cents for item in all_items
        if item.fund == "Internal Service"
    )

    # Note: Official total from PDF is $192,282,438 before interfund deductions
    # Net total after deductions is $163,777,889
    all_funds_total = sum(item.budgeted_cents for item in all_items)

    totals = BudgetTotals(
        general_fund_cents=general_fund_total,
        enterprise_funds_cents=enterprise_total,
        capital_projects_cents=capital_total,
        special_funds_cents=special_revenue_total + internal_service_total,
        total_cents=all_funds_total,
    )

    return BudgetExtractionResult(
        jurisdiction_id="city-san-rafael",
        fiscal_year="2025-2026",
        source_url="https://www.cityofsanrafael.org/city-budget/",
        items=all_items,
        totals=totals,
        extraction_notes=(
            "Extracted from FY25-26-General-Fund-Budget.pdf and "
            "FY25-26-Fund-Summary-Other-Funds.pdf. General Fund shows "
            "department-level appropriations. Other funds show fund-level "
            "operating and capital budgets. Internal service funds included "
            "but may overlap with department budgets through cost allocation."
        ),
    )


def main():
    """Main extraction and storage workflow."""
    print("=" * 60)
    print("San Rafael FY 2025-26 Budget Extraction")
    print("=" * 60)

    # Build extraction result
    result = build_extraction_result()

    # Validate
    # Expected total from PDF: $192,282,438 (gross) or $163,777,889 (net)
    # Our extraction excludes some pass-through items, so expect lower
    expected_gross = dollars_to_cents(192_282_438)
    validation = result.validate(expected_total_cents=expected_gross)

    print(f"\nExtracted {len(result.items)} budget line items")
    print(f"Total: {cents_to_dollars_str(validation['actual_total_cents'])}")
    print(f"Expected gross: {cents_to_dollars_str(expected_gross)}")

    # Breakdown by fund type
    fund_totals = {}
    for item in result.items:
        fund_totals[item.fund] = fund_totals.get(item.fund, 0) + item.budgeted_cents

    print("\nBreakdown by fund type:")
    for fund, total in sorted(fund_totals.items(), key=lambda x: -x[1]):
        print(f"  {fund}: {cents_to_dollars_str(total)}")

    # Show validation results
    print(f"\nValidation: {'PASS' if validation['valid'] else 'ISSUES FOUND'}")
    if validation['issues']:
        print("Issues:")
        for issue in validation['issues']:
            print(f"  - {issue}")

    # Save extraction to JSON for inspection
    output_dir = Path("data/budgets/san_rafael")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "FY25-26-extracted.json"
    output_file.write_text(result.to_json(indent=2))
    print(f"\nSaved extraction to {output_file}")

    # Store in database if we have postgres connection
    try:
        from civic.storage.postgres_backend import PostgresBackend
        import os

        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            print("\nStoring in database...")
            backend = PostgresBackend(database_url)

            # Convert items to dict format for storage
            # Each item needs a unique ID for temporal versioning
            items_for_storage = []
            for idx, item in enumerate(result.items):
                # Build unique ID from fund/dept/program/line_item
                id_parts = [
                    result.fiscal_year,
                    item.fund or "unknown",
                    item.department or "none",
                    item.program or "none",
                    item.line_item[:50],  # Truncate long line items
                ]
                item_id = "-".join(p.lower().replace(" ", "_").replace("/", "_") for p in id_parts)

                items_for_storage.append({
                    "id": item_id,
                    "fiscal_year": result.fiscal_year,
                    "fund": item.fund,
                    "department": item.department,
                    "program": item.program,
                    "line_item": item.line_item,
                    "budgeted_cents": item.budgeted_cents,
                    "revised_cents": item.revised_cents,
                    "actual_cents": item.actual_cents,
                    "source_url": result.source_url,
                    "source_page": item.source_page,
                    "notes": item.notes,
                })

            count = backend.store_budget_items(
                jurisdiction_id=result.jurisdiction_id,
                items=items_for_storage,
                as_of=datetime.now(),
            )
            print(f"Stored {count} budget items in database")

            # Verify
            stored_count = backend.get_budget_items_count(
                jurisdiction_id=result.jurisdiction_id,
                fiscal_year=result.fiscal_year,
            )
            print(f"Verified: {stored_count} items in database for FY {result.fiscal_year}")
        else:
            print("\nNo DATABASE_URL set - skipping database storage")
            print("Run with DATABASE_URL to store in Supabase")
    except ImportError as e:
        print(f"\nDatabase storage skipped: {e}")
    except Exception as e:
        print(f"\nDatabase storage error: {e}")

    return result


if __name__ == "__main__":
    result = main()
