#!/usr/bin/env python3
"""
Docling-based Retrospective Analyzer

Uses IBM Docling for PDF extraction instead of regex-based splitting.
Replaces brittle regex patterns with AI-powered document understanding.

Session 101: Modernized extraction approach
"""

import sys
import os
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from docling.document_converter import DocumentConverter
from retrospective_analyzer import HighStakesDecision
from llm_provider import get_model_for_task
import requests

# Initialize Docling converter (reuse across calls)
_converter = None

def get_converter():
    """Get or create Docling converter instance"""
    global _converter
    if _converter is None:
        _converter = DocumentConverter()
    return _converter


class DoclingRetrospectiveAnalyzer:
    """
    Retrospective analyzer using Docling for PDF extraction

    Improvements over regex approach:
    - AI-powered layout understanding (no false matches)
    - Preserves document structure (tables, headings)
    - Clean markdown output for LLM processing
    """

    def __init__(self):
        self.converter = get_converter()
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
        Extract high-stakes decisions from a meeting PDF using Docling

        Args:
            pdf_url: Direct PDF URL (must be accessible)
            meeting_date: ISO format date (2025-10-06)
            meeting_type: Type of meeting (city_council, planning_commission, etc.)
            min_budget: Minimum budget threshold
            min_stakes_score: Minimum stakes score (1-10)

        Returns:
            List of HighStakesDecision objects
        """
        print(f"   📄 Converting PDF with Docling...")

        try:
            # Convert PDF to structured markdown
            result = self.converter.convert(pdf_url)
            markdown = result.document.export_to_markdown()

            print(f"   ✅ Converted to {len(markdown):,} chars of markdown")

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

        Much simpler than regex on raw PDF text!
        """
        items = []

        # Find all item markers
        pattern = r'\n- ([a-z])\.\s+'
        matches = list(re.finditer(pattern, markdown, re.IGNORECASE))

        if not matches:
            # Fallback: Look for numbered items
            pattern = r'\n(\d+)\.\s+[A-Z]'
            matches = list(re.finditer(pattern, markdown))

        if not matches:
            # No items found - return whole document
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

Return JSON:
{{
  "is_high_stakes": true/false,
  "stakes_score": 1-10,
  "title": "Brief title",
  "description": "1-2 sentence summary",
  "decision_type": "budget|development|environmental|policy|tax",
  "budget_amount": number or null,
  "budget_description": "what the budget is for",
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


def test_docling_analyzer():
    """Test the Docling analyzer on Oct 6 meeting"""

    analyzer = DoclingRetrospectiveAnalyzer()

    pdf_url = "https://storage.googleapis.com/proudcity/sanrafaelca/2025/10/Agenda-Packet-2025-10-06.pdf"

    print("\n🔍 Testing Docling Retrospective Analyzer")
    print(f"PDF: {pdf_url}\n")

    decisions = analyzer.extract_high_stakes_decisions(
        pdf_url=pdf_url,
        meeting_date="2025-10-06",
        meeting_type="city_council"
    )

    print(f"\n✅ Found {len(decisions)} high-stakes decisions:")
    for d in decisions:
        print(f"\n   Item {d.item_ref}: {d.title}")
        print(f"   Stakes: {d.stakes_score}/10")
        if d.budget_amount:
            print(f"   Budget: ${d.budget_amount:,}")

    return decisions


if __name__ == "__main__":
    decisions = test_docling_analyzer()

    # Save results
    import json
    output = {
        "test_date": datetime.now().isoformat(),
        "decisions": [asdict(d) for d in decisions]
    }

    with open("data/pilot/docling_analyzer_test.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n📄 Results saved to data/pilot/docling_analyzer_test.json")
