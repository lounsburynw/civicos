"""
Budget extraction prompt template for AI-assisted municipal budget ETL.

This module provides structured prompts for extracting budget line items
from municipal budget documents (PDFs, text). The prompts are designed
to be model-agnostic and incorporate accuracy rules from production use.

Usage:
    from civicos_extraction.prompts import build_budget_extraction_prompt

    prompt = build_budget_extraction_prompt(
        municipality="San Rafael",
        state="California",
        fiscal_year="2025-2026",
        document_text=pdf_text,  # or use with vision API for raw PDF
    )

    # Send to any LLM (Claude, GPT-4, Gemini, etc.)
    response = llm.complete(prompt)

    # Parse response
    result = BudgetExtractionResult.from_json(response)
"""

from dataclasses import dataclass, field
from typing import Optional
import json
import re

# Import BudgetLineItem from canonical location in clients.base
from civicos_extraction.clients.base import BudgetLineItem


@dataclass
class BudgetTotals:
    """Validation totals for cross-checking extraction accuracy."""

    general_fund_cents: Optional[int] = None
    enterprise_funds_cents: Optional[int] = None
    capital_projects_cents: Optional[int] = None
    special_funds_cents: Optional[int] = None
    total_cents: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "general_fund_cents": self.general_fund_cents,
            "enterprise_funds_cents": self.enterprise_funds_cents,
            "capital_projects_cents": self.capital_projects_cents,
            "special_funds_cents": self.special_funds_cents,
            "total_cents": self.total_cents,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BudgetTotals":
        """Create from dictionary."""
        return cls(
            general_fund_cents=data.get("general_fund_cents"),
            enterprise_funds_cents=data.get("enterprise_funds_cents"),
            capital_projects_cents=data.get("capital_projects_cents"),
            special_funds_cents=data.get("special_funds_cents"),
            total_cents=data.get("total_cents"),
        )


@dataclass
class BudgetExtractionResult:
    """Complete extraction result from a budget document."""

    jurisdiction_id: str  # "city-san-rafael"
    fiscal_year: str  # "2025-2026"
    source_url: str  # Document URL
    items: list[BudgetLineItem] = field(default_factory=list)
    totals: Optional[BudgetTotals] = None
    extraction_notes: Optional[str] = None  # Any issues or caveats

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "fiscal_year": self.fiscal_year,
            "source_url": self.source_url,
            "items": [item.to_dict() for item in self.items],
            "totals": self.totals.to_dict() if self.totals else None,
            "extraction_notes": self.extraction_notes,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "BudgetExtractionResult":
        """Create from dictionary."""
        return cls(
            jurisdiction_id=data["jurisdiction_id"],
            fiscal_year=data["fiscal_year"],
            source_url=data["source_url"],
            items=[BudgetLineItem.from_dict(item) for item in data.get("items", [])],
            totals=BudgetTotals.from_dict(data["totals"]) if data.get("totals") else None,
            extraction_notes=data.get("extraction_notes"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "BudgetExtractionResult":
        """Parse from JSON string (handles markdown code blocks)."""
        # Strip markdown code blocks if present
        cleaned = json_str.strip()
        if cleaned.startswith("```"):
            # Remove opening ```json or ``` and closing ```
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        data = json.loads(cleaned)
        return cls.from_dict(data)

    def validate(self, expected_total_cents: Optional[int] = None) -> dict:
        """
        Validate extraction against expected totals.

        Returns dict with:
            valid: bool - whether extraction passed validation
            actual_total_cents: int - sum of extracted items
            variance_pct: float - percent difference from expected
            issues: list[str] - any validation issues found
        """
        issues = []

        # Sum all items
        actual_total = sum(item.budgeted_cents for item in self.items)

        # Check against provided totals
        if self.totals and self.totals.total_cents:
            internal_variance = abs(actual_total - self.totals.total_cents) / self.totals.total_cents
            if internal_variance > 0.01:  # >1% variance
                issues.append(
                    f"Items sum ({actual_total}) differs from stated total "
                    f"({self.totals.total_cents}) by {internal_variance * 100:.1f}%"
                )

        # Check against expected (from config)
        variance_pct = None
        if expected_total_cents:
            variance_pct = abs(actual_total - expected_total_cents) / expected_total_cents * 100
            if variance_pct > 1.0:  # >1% variance
                issues.append(
                    f"Extracted total differs from expected by {variance_pct:.1f}%"
                )

        # Check for suspicious items
        for item in self.items:
            if item.budgeted_cents < 0:
                issues.append(f"Negative budget amount: {item.line_item}")
            if item.budgeted_cents > 500_000_000_00:  # >$500M - probably citywide
                issues.append(
                    f"Suspiciously large amount (>${item.budgeted_cents // 100:,}): "
                    f"{item.line_item}"
                )

        return {
            "valid": len(issues) == 0,
            "actual_total_cents": actual_total,
            "variance_pct": variance_pct,
            "issues": issues,
            "item_count": len(self.items),
        }


@dataclass
class BudgetExtractionPrompt:
    """
    Structured prompt for budget extraction.

    This class encapsulates the complete prompt with all accuracy rules
    and can be rendered as a string for any LLM.
    """

    municipality: str
    state: str
    fiscal_year: str
    source_url: str = ""
    document_context: str = ""  # PDF text or description for vision API

    def render(self) -> str:
        """Render the complete prompt string."""
        return build_budget_extraction_prompt(
            municipality=self.municipality,
            state=self.state,
            fiscal_year=self.fiscal_year,
            source_url=self.source_url,
            document_context=self.document_context,
        )

    def __str__(self) -> str:
        return self.render()


# =============================================================================
# Core Prompt Template
# =============================================================================

BUDGET_EXTRACTION_PROMPT_TEMPLATE = """# Municipal Budget Extraction

## Context
You are extracting structured budget data from a municipal budget document.
Extract line-item budget data that can be used to answer questions like
"How much does {municipality} spend on Police?"

## Input
- **Municipality**: {municipality}
- **State**: {state}
- **Fiscal Year**: {fiscal_year}
- **Source**: {source_url}

{document_section}

## Critical Extraction Rules

### DO Extract:
- Individual department budgets (Police, Fire, Parks, etc.)
- Program-level budgets (Homelessness Services, Code Enforcement, etc.)
- Fund-level totals (General Fund, Enterprise Funds, Capital Projects)
- Line items with specific appropriations

### DO NOT Extract:
- Investment portfolio values (e.g., "Quarterly Investment Report: $109M")
- Reserve balances or fund balances (not appropriations)
- Projected revenues (we want expenditures/appropriations only)
- Multi-year totals (extract current fiscal year only)
- Debt service principal (only interest payments are operating costs)

### Amount Handling:
- Convert ALL amounts to **cents** (multiply dollars by 100)
- Example: $28,456,789 becomes 2845678900
- Use integers only, no decimals
- For ranges, use the budgeted/adopted amount, not revised or actual

### Common Errors to Avoid:
1. **Citywide Total Confusion**: If you see the overall city budget total
   mentioned in context, do NOT create a line item for it. Only extract
   department/program breakdowns.

2. **Investment Reports**: Portfolio values like "$109M in investments"
   are NOT budgets - they are asset values. Skip these entirely.

3. **Double-Counting**: If the same amount appears under multiple headings
   (e.g., "Police" and "Public Safety - Police"), extract only once using
   the most specific categorization.

4. **Context Pollution**: If a line item mentions the citywide budget for
   context (e.g., "of the city's $192M budget"), extract only the specific
   amount for that line item, not the $192M.

## Output Schema

Return a JSON object with this exact structure:

```json
{{
  "jurisdiction_id": "city-{municipality_slug}",
  "fiscal_year": "{fiscal_year}",
  "source_url": "{source_url}",
  "items": [
    {{
      "fund": "General Fund",
      "department": "Police",
      "program": null,
      "line_item": "Police Department",
      "budgeted_cents": 2800000000,
      "revised_cents": null,
      "actual_cents": null,
      "source_page": 45,
      "notes": null
    }},
    {{
      "fund": "General Fund",
      "department": "Fire",
      "program": null,
      "line_item": "Fire Department",
      "budgeted_cents": 1800000000,
      "source_page": 47,
      "notes": null
    }},
    {{
      "fund": "Enterprise - Water",
      "department": null,
      "program": null,
      "line_item": "Water Enterprise Fund",
      "budgeted_cents": 2200000000,
      "source_page": 62,
      "notes": "Includes capital improvements"
    }}
  ],
  "totals": {{
    "general_fund_cents": 8000000000,
    "enterprise_funds_cents": 4500000000,
    "capital_projects_cents": 1500000000,
    "special_funds_cents": null,
    "total_cents": 14000000000
  }},
  "extraction_notes": "Extracted from adopted budget summary tables on pages 40-65"
}}
```

## Field Definitions

### Per Item:
- **fund**: The fund category (General Fund, Enterprise, Capital, Special, etc.)
- **department**: City department if applicable (Police, Fire, Community Development)
- **program**: Specific program within department if available
- **line_item**: Full description from budget document
- **budgeted_cents**: Adopted/appropriated amount in cents
- **revised_cents**: Mid-year revised amount if shown (optional)
- **actual_cents**: Actual expenditure if shown (optional)
- **source_page**: Page number in PDF for verification
- **notes**: Any caveats, conditions, or special notes

### Totals (for validation):
- **general_fund_cents**: Sum of General Fund items
- **enterprise_funds_cents**: Sum of Enterprise Fund items (Water, Sewer, Parking, etc.)
- **capital_projects_cents**: Sum of Capital Projects/CIP items
- **special_funds_cents**: Sum of Special Revenue Funds
- **total_cents**: Grand total of all funds

## Guidelines

1. Extract at the most detailed level available (programs > departments > funds)
2. Use fund/department names **exactly as shown** in the document
3. Include **page numbers** for every item when visible
4. Add **notes** for items with caveats (grants, restricted funds, one-time)
5. Include **totals** section for validation against known totals
6. If unsure about a categorization, use the most conservative interpretation

## Example Extraction Patterns

| Document Text | fund | department | budgeted_cents |
|---------------|------|------------|----------------|
| "Police Department: $28,456,789" | General Fund | Police | 2845678900 |
| "Water Enterprise: $22M" | Enterprise - Water | null | 2200000000 |
| "Parks & Recreation: $4.2 million" | General Fund | Parks & Recreation | 420000000 |
| "Homelessness Services Program: $1,100,000" | General Fund | Community Development | 110000000 |

Now extract all budget line items from the document.
"""


def build_budget_extraction_prompt(
    municipality: str,
    state: str,
    fiscal_year: str,
    source_url: str = "",
    document_context: str = "",
) -> str:
    """
    Build a complete budget extraction prompt.

    Args:
        municipality: City name (e.g., "San Rafael")
        state: State name (e.g., "California")
        fiscal_year: Fiscal year (e.g., "2025-2026")
        source_url: URL of the budget document
        document_context: Extracted text from PDF or instruction for vision API

    Returns:
        Complete prompt string ready to send to an LLM
    """
    # Create slug for jurisdiction_id
    municipality_slug = municipality.lower().replace(" ", "-")

    # Build document section
    if document_context:
        document_section = f"""## Document Content

{document_context}
"""
    else:
        document_section = """## Document
[Attached PDF - extract budget line items from all pages]
"""

    return BUDGET_EXTRACTION_PROMPT_TEMPLATE.format(
        municipality=municipality,
        municipality_slug=municipality_slug,
        state=state,
        fiscal_year=fiscal_year,
        source_url=source_url or "[document URL]",
        document_section=document_section,
    )


# =============================================================================
# Convenience Functions
# =============================================================================


def validate_extraction_response(response_json: str, expected_total_cents: Optional[int] = None) -> dict:
    """
    Validate an extraction response against expected totals.

    Args:
        response_json: JSON string from LLM response
        expected_total_cents: Known total budget in cents for validation

    Returns:
        Validation result dict with 'valid', 'issues', 'actual_total_cents'
    """
    try:
        result = BudgetExtractionResult.from_json(response_json)
        return result.validate(expected_total_cents)
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "issues": [f"Invalid JSON: {e}"],
            "actual_total_cents": 0,
            "item_count": 0,
        }
    except KeyError as e:
        return {
            "valid": False,
            "issues": [f"Missing required field: {e}"],
            "actual_total_cents": 0,
            "item_count": 0,
        }


def dollars_to_cents(amount: float | int | str) -> int:
    """
    Convert dollar amount to cents.

    Handles various input formats:
    - 1234567.89 -> 123456789
    - "$1,234,567.89" -> 123456789
    - "1.2M" -> 120000000
    - "1.2 million" -> 120000000
    """
    if isinstance(amount, int):
        return amount * 100

    if isinstance(amount, float):
        return int(round(amount * 100))

    # String handling
    text = str(amount).strip().replace(",", "").replace("$", "")

    # Handle millions/billions shorthand
    text_lower = text.lower()
    multiplier = 1
    if "billion" in text_lower or text_lower.endswith("b"):
        multiplier = 1_000_000_000
        text = re.sub(r"[bB](?:illion)?", "", text)
    elif "million" in text_lower or text_lower.endswith("m"):
        multiplier = 1_000_000
        text = re.sub(r"[mM](?:illion)?", "", text)
    elif "thousand" in text_lower or text_lower.endswith("k"):
        multiplier = 1_000
        text = re.sub(r"[kK](?:thousand)?", "", text)

    # Parse the number
    text = text.strip()
    if not text:
        return 0

    try:
        dollars = float(text) * multiplier
        return int(round(dollars * 100))
    except ValueError:
        return 0


def cents_to_dollars_str(cents: int) -> str:
    """Format cents as dollar string with commas."""
    dollars = cents / 100
    if dollars >= 1_000_000_000:
        return f"${dollars / 1_000_000_000:.1f}B"
    elif dollars >= 1_000_000:
        return f"${dollars / 1_000_000:.1f}M"
    elif dollars >= 1_000:
        return f"${dollars:,.0f}"
    else:
        return f"${dollars:.2f}"
