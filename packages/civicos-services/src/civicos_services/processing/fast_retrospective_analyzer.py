#!/usr/bin/env python3
"""
Fast Retrospective Analyzer using PyMuPDF4LLM

1,433x faster PDF extraction than Docling (0.12s vs 172s per PDF)
Maintains high quality markdown output for LLM processing.

Session 102: Speed optimization for batch retrospective analysis
"""

import sys
import os
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

import pymupdf4llm
import requests
from .retrospective_analyzer import HighStakesDecision
from ..core.llm_provider import get_model_for_task


class FastRetrospectiveAnalyzer:
    """
    Fast retrospective analyzer using PyMuPDF4LLM for PDF extraction

    Performance improvements:
    - PDF extraction: 0.12s vs 172s (1,433x faster than Docling)
    - Clean markdown output (similar quality)
    - Parallel-processing ready (stateless design)

    Expected runtime for 33 meetings:
    - Serial: ~2 hours (vs 3.5 hours with Docling)
    - Parallel (8 workers): 15-20 minutes
    """

    def __init__(self):
        self.session = requests.Session()

    def extract_high_stakes_decisions(
        self,
        pdf_url: str,
        meeting_date: str,
        meeting_type: str = "city_council",
        min_budget: int = 100000,
        min_stakes_score: int = 6
    ) -> List[HighStakesDecision]:
        """
        Extract high-stakes decisions from a meeting PDF using PyMuPDF4LLM

        Args:
            pdf_url: Direct PDF URL or local file path
            meeting_date: ISO format date (2025-10-06)
            meeting_type: Type of meeting (city_council, planning_commission, etc.)
            min_budget: Minimum budget threshold
            min_stakes_score: Minimum stakes score (1-10)

        Returns:
            List of HighStakesDecision objects
        """
        print(f"   📄 Extracting PDF with PyMuPDF...")

        try:
            # Download PDF if URL, or use local path
            if pdf_url.startswith('http'):
                response = self.session.get(pdf_url, timeout=60)
                response.raise_for_status()

                # Save to temp file
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    tmp.write(response.content)
                    pdf_path = tmp.name
            else:
                pdf_path = pdf_url

            # Convert PDF to markdown (blazing fast!)
            markdown = pymupdf4llm.to_markdown(pdf_path)

            # Clean up temp file if we created one
            if pdf_url.startswith('http'):
                os.unlink(pdf_path)

            print(f"   ✅ Extracted {len(markdown):,} chars of markdown")

            # Split markdown into agenda items
            items = self._split_markdown_into_items(markdown)
            print(f"   📋 Found {len(items)} agenda items")

            # Extract decisions from each item
            all_decisions = []
            for item_ref, item_text in items:
                # Skip tiny items (likely noise)
                if len(item_text.strip()) < 100:
                    continue

                decisions = self._extract_from_item(
                    item_ref,
                    item_text,
                    meeting_date,
                    meeting_type,
                    min_budget,
                    min_stakes_score,
                    pdf_url
                )
                all_decisions.extend(decisions)

            return all_decisions

        except Exception as e:
            print(f"   ❌ Error: {type(e).__name__}: {e}")
            return []

    def _split_markdown_into_items(self, markdown: str) -> List[Tuple[str, str]]:
        """
        Split markdown into agenda items

        Looks for patterns like:
        - a. Item Title
        - b. Another Item
        Or numbered items: 1. Item Title
        """
        items = []

        # Try lettered items first (- a., - b., etc.)
        pattern = r'\n- ([a-z])\.\s+'
        matches = list(re.finditer(pattern, markdown, re.IGNORECASE))

        if not matches:
            # Fallback: Look for numbered items
            pattern = r'\n(\d+)\.\s+[A-Z]'
            matches = list(re.finditer(pattern, markdown))

        if not matches:
            # No items found - return whole document as single item
            return [("full", markdown)]

        for i, match in enumerate(matches):
            item_ref = match.group(1)
            start = match.start()

            # End is start of next item or end of document
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)

            item_text = markdown[start:end]
            items.append((item_ref, item_text))

        return items

    def _extract_from_item(
        self,
        item_ref: str,
        item_text: str,
        meeting_date: str,
        meeting_type: str,
        min_budget: int,
        min_stakes_score: int,
        agenda_url: str
    ) -> List[HighStakesDecision]:
        """Extract high-stakes decision from a single agenda item"""

        # Build prompt for LLM
        prompt = f"""Analyze this agenda item and determine if it represents a high-stakes municipal decision.

AGENDA ITEM {item_ref}:
{item_text[:4000]}  # Limit to 4K chars per item

Extract if this is a high-stakes decision meeting ANY criteria:
1. Budget ≥ ${min_budget:,} (contracts, appropriations, capital projects)
2. Development ≥ 20 units (residential/commercial)
3. Environmental/policy affecting ≥ 1,000 residents
4. Tax/fee changes

CRITICAL BUDGET EXTRACTION RULES:
- Extract ONLY the budget for THIS SPECIFIC AGENDA ITEM
- DO NOT extract the citywide total budget (e.g., "Final Budget for FY 2025-26")
- DO NOT extract investment portfolio values (e.g., "Quarterly Investment Report")
- DO NOT extract budget context (e.g., "discussed in context of $192M city budget")
- If this item is just approving/adopting the overall city budget, set budget_amount to null
- If this is an investment/portfolio report, set budget_amount to null

Examples:
✅ CORRECT: "$31M for Marin Transit Collaboration" → budget_amount: 31000000
✅ CORRECT: "$1.1M Wildfire Prevention Fund" → budget_amount: 1100000
❌ WRONG: "Final Citywide Budget $192M" → budget_amount: null (not a specific appropriation)
❌ WRONG: "Quarterly Investment Report - $109M portfolio" → budget_amount: null (portfolio value, not budget)
❌ WRONG: "Mid-Year Personnel Changes (overall budget $192M)" → budget_amount: null (context, not item budget)

Return JSON:
{{
  "is_high_stakes": true/false,
  "stakes_score": 1-10,
  "title": "Brief title",
  "description": "1-2 sentence summary",
  "decision_type": "budget|development|environmental|policy|tax",
  "budget_amount": number or null,
  "budget_description": "what the budget is for (or null if budget_amount is null)",
  "affected_population_estimate": number or null,
  "geographic_scope": "citywide|district|neighborhood",
  "project_types": ["housing", "transportation", etc.],
  "keywords_for_matching": ["keyword1", "keyword2", ...]
}}

If NOT high-stakes, return: {{"is_high_stakes": false}}
"""

        # Call LLM
        try:
            llm = get_model_for_task("structured_extraction")
            response = llm.chat(
                messages=[{"role": "user", "content": prompt}],
                response_format="json_object"
            )

            import json
            result = json.loads(response)

            if not result.get("is_high_stakes"):
                return []

            if result.get("stakes_score", 0) < min_stakes_score:
                return []

            # Build HighStakesDecision object
            decision = HighStakesDecision(
                item_ref=item_ref,
                title=result.get("title", "Unknown"),
                description=result.get("description", ""),
                meeting_date=meeting_date,
                meeting_type=meeting_type,
                is_high_stakes=True,
                stakes_score=result.get("stakes_score", 6),
                decision_type=result.get("decision_type", "policy"),
                budget_amount=result.get("budget_amount"),
                budget_description=result.get("budget_description", ""),
                project_size_units=None,  # Could extract from result
                project_location=None,
                affected_population_estimate=result.get("affected_population_estimate"),
                geographic_scope=result.get("geographic_scope", "unknown"),
                project_types=result.get("project_types", []),
                keywords_for_matching=result.get("keywords_for_matching", []),
                participation_mechanisms=[],
                agenda_url=agenda_url,
                staff_report_url=None
            )

            return [decision]

        except Exception as e:
            print(f"      ❌ LLM error for item {item_ref}: {e}")
            return []


def test_fast_analyzer():
    """Test the fast analyzer on Oct 6 meeting"""

    analyzer = FastRetrospectiveAnalyzer()

    # Use local test PDF
    pdf_path = "/Users/nicolaslounsbury/projects/civic/data/test_agenda_packet_oct6.pdf"

    print("\n🚀 Testing Fast Retrospective Analyzer (PyMuPDF4LLM)")
    print(f"PDF: {pdf_path}\n")

    import time
    start = time.time()

    decisions = analyzer.extract_high_stakes_decisions(
        pdf_url=pdf_path,
        meeting_date="2025-10-06",
        meeting_type="city_council"
    )

    elapsed = time.time() - start

    print(f"\n✅ Found {len(decisions)} high-stakes decisions in {elapsed:.1f} seconds")

    for decision in decisions:
        print(f"\n   • {decision.title}")
        if decision.budget_amount:
            print(f"     ${decision.budget_amount:,.0f} | Stakes: {decision.stakes_score}/10")
        else:
            print(f"     Stakes: {decision.stakes_score}/10")

    return decisions


if __name__ == "__main__":
    test_fast_analyzer()
