#!/usr/bin/env python3
"""
Validate cross-county query behavior with real data.

Answers 5 spec questions by calling execute_search() directly (no server needed).
Requires DATABASE_URL set in .env for PostgreSQL access.

Usage:
    source civicos-env/bin/activate
    python scripts/validate_cross_county.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Load env before any civicos imports
from dotenv import load_dotenv
load_dotenv()

from civicos import CivicOS
from civicos_services.query.models import SearchRequest
from civicos_services.query.verbs import execute_search


def format_results(response, label: str) -> dict:
    """Extract key fields from a SearchResponse for reporting."""
    by_jid = {}
    if response.jurisdiction_results:
        for jid, results in response.jurisdiction_results.items():
            by_jid[jid] = [
                {
                    "title": r.title[:80],
                    "relevance": r.relevance,
                    "type": r.type,
                    "date": r.date,
                }
                for r in results[:5]
            ]
    else:
        by_jid["single"] = [
            {
                "title": r.title[:80],
                "relevance": r.relevance,
                "type": r.type,
                "date": r.date,
            }
            for r in response.results[:5]
        ]

    return {
        "label": label,
        "total_results": response.meta.total_results,
        "query_time_ms": response.meta.query_time_ms,
        "jurisdictions_searched": list(by_jid.keys()),
        "results_by_jurisdiction": by_jid,
    }


async def run_validation():
    """Run all 5 validation queries."""
    civic = CivicOS("city-san-rafael")
    base_jid = "city-san-rafael"

    report = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "questions": []}

    # Q1: Are sibling results useful? (housing decisions, siblings only)
    q1_req = SearchRequest(
        query="housing",
        corpus=["decisions"],
        include_siblings=True,
        limit=20,
    )
    q1_resp = await execute_search(q1_req, civic, base_jid)
    report["questions"].append(
        format_results(q1_resp, "Q1: Sibling housing decisions — are results useful?")
    )

    # Q2: Policy vs operational distinction (water, decisions + issues, siblings)
    q2_req = SearchRequest(
        query="water",
        corpus=["decisions", "issues"],
        include_siblings=True,
        limit=20,
    )
    q2_resp = await execute_search(q2_req, civic, base_jid)
    report["questions"].append(
        format_results(q2_resp, "Q2: Water decisions+issues with siblings — policy vs operational")
    )

    # Q3: Cross-county relevance scores (housing decisions, siblings + Berkeley)
    q3_req = SearchRequest(
        query="housing",
        corpus=["decisions"],
        include_siblings=True,
        also_include=["city-berkeley"],
        limit=20,
    )
    q3_resp = await execute_search(q3_req, civic, base_jid)
    report["questions"].append(
        format_results(q3_resp, "Q3: Housing decisions — siblings + Berkeley cross-county")
    )

    # Q4: Right default for siblings? (housing zoning, with vs without siblings)
    q4a_req = SearchRequest(
        query="housing zoning",
        corpus=["decisions"],
        limit=10,
    )
    q4a_resp = await execute_search(q4a_req, civic, base_jid)

    q4b_req = SearchRequest(
        query="housing zoning",
        corpus=["decisions"],
        include_siblings=True,
        limit=10,
    )
    q4b_resp = await execute_search(q4b_req, civic, base_jid)

    report["questions"].append({
        "label": "Q4: Housing zoning — with vs without siblings",
        "without_siblings": format_results(q4a_resp, "without siblings"),
        "with_siblings": format_results(q4b_resp, "with siblings"),
    })

    # Q5: Cross-county without explicit request? (rent control, decisions + muni_code)
    q5a_req = SearchRequest(
        query="rent control",
        corpus=["decisions", "municipal_code"],
        limit=10,
    )
    q5a_resp = await execute_search(q5a_req, civic, base_jid)

    q5b_req = SearchRequest(
        query="rent control",
        corpus=["decisions", "municipal_code"],
        also_include=["city-berkeley"],
        limit=10,
    )
    q5b_resp = await execute_search(q5b_req, civic, base_jid)

    report["questions"].append({
        "label": "Q5: Rent control — without vs with Berkeley",
        "without_berkeley": format_results(q5a_resp, "San Rafael only"),
        "with_berkeley": format_results(q5b_resp, "with Berkeley via also_include"),
    })

    return report


def main():
    report = asyncio.run(run_validation())

    # Print to stdout
    output = json.dumps(report, indent=2, default=str)
    print(output)

    # Also save to file
    out_path = Path("data/validation/cross_county_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output)
    print(f"\nReport saved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
