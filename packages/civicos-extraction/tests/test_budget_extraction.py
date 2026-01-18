"""Tests for budget extraction prompt template."""

import json
import pytest

from civicos_extraction.prompts.budget_extraction import (
    BudgetExtractionPrompt,
    BudgetExtractionResult,
    BudgetLineItem,
    BudgetTotals,
    build_budget_extraction_prompt,
    cents_to_dollars_str,
    dollars_to_cents,
    validate_extraction_response,
)


class TestDollarsCentsConversion:
    """Test dollar/cents conversion utilities."""

    def test_dollars_to_cents_int(self):
        assert dollars_to_cents(100) == 10000
        assert dollars_to_cents(1234567) == 123456700

    def test_dollars_to_cents_float(self):
        assert dollars_to_cents(100.50) == 10050
        assert dollars_to_cents(1234567.89) == 123456789

    def test_dollars_to_cents_string(self):
        assert dollars_to_cents("$1,234,567.89") == 123456789
        assert dollars_to_cents("100.50") == 10050

    def test_dollars_to_cents_millions(self):
        assert dollars_to_cents("1.5M") == 150000000
        assert dollars_to_cents("1.5 million") == 150000000
        assert dollars_to_cents("$28.4M") == 2840000000

    def test_dollars_to_cents_billions(self):
        assert dollars_to_cents("1.2B") == 120000000000
        assert dollars_to_cents("1.2 billion") == 120000000000

    def test_dollars_to_cents_thousands(self):
        assert dollars_to_cents("500K") == 50000000
        assert dollars_to_cents("500k") == 50000000

    def test_cents_to_dollars_str(self):
        assert cents_to_dollars_str(10000) == "$100.00"
        assert cents_to_dollars_str(99999900) == "$999,999"  # Just under $1M
        assert cents_to_dollars_str(150000000) == "$1.5M"
        assert cents_to_dollars_str(2840000000) == "$28.4M"
        assert cents_to_dollars_str(120000000000) == "$1.2B"


class TestBudgetLineItem:
    """Test BudgetLineItem dataclass."""

    def test_to_dict(self):
        item = BudgetLineItem(
            fund="General Fund",
            department="Police",
            program=None,
            line_item="Police Department",
            budgeted_cents=2800000000,
            source_page=45,
        )
        d = item.to_dict()
        assert d["fund"] == "General Fund"
        assert d["department"] == "Police"
        assert d["budgeted_cents"] == 2800000000
        assert d["source_page"] == 45

    def test_from_dict(self):
        data = {
            "fund": "Enterprise - Water",
            "department": None,
            "program": None,
            "line_item": "Water Enterprise Fund",
            "budgeted_cents": 2200000000,
            "source_page": 62,
        }
        item = BudgetLineItem.from_dict(data)
        assert item.fund == "Enterprise - Water"
        assert item.budgeted_cents == 2200000000

    def test_roundtrip(self):
        item = BudgetLineItem(
            fund="General Fund",
            department="Fire",
            program="Prevention",
            line_item="Fire Prevention Program",
            budgeted_cents=500000000,
            revised_cents=520000000,
            actual_cents=None,
            source_page=48,
            notes="Includes grant funding",
        )
        d = item.to_dict()
        item2 = BudgetLineItem.from_dict(d)
        assert item.fund == item2.fund
        assert item.budgeted_cents == item2.budgeted_cents
        assert item.notes == item2.notes


class TestBudgetExtractionResult:
    """Test BudgetExtractionResult dataclass."""

    @pytest.fixture
    def sample_result(self):
        return BudgetExtractionResult(
            jurisdiction_id="city-san-rafael",
            fiscal_year="2025-2026",
            source_url="https://example.com/budget.pdf",
            items=[
                BudgetLineItem(
                    fund="General Fund",
                    department="Police",
                    program=None,
                    line_item="Police Department",
                    budgeted_cents=2800000000,
                ),
                BudgetLineItem(
                    fund="General Fund",
                    department="Fire",
                    program=None,
                    line_item="Fire Department",
                    budgeted_cents=1800000000,
                ),
                BudgetLineItem(
                    fund="Enterprise - Water",
                    department=None,
                    program=None,
                    line_item="Water Enterprise Fund",
                    budgeted_cents=2200000000,
                ),
            ],
            totals=BudgetTotals(
                general_fund_cents=4600000000,
                enterprise_funds_cents=2200000000,
                total_cents=6800000000,
            ),
        )

    def test_to_json(self, sample_result):
        json_str = sample_result.to_json()
        data = json.loads(json_str)
        assert data["jurisdiction_id"] == "city-san-rafael"
        assert len(data["items"]) == 3
        assert data["totals"]["total_cents"] == 6800000000

    def test_from_json(self, sample_result):
        json_str = sample_result.to_json()
        result2 = BudgetExtractionResult.from_json(json_str)
        assert result2.jurisdiction_id == sample_result.jurisdiction_id
        assert len(result2.items) == len(sample_result.items)
        assert result2.totals.total_cents == sample_result.totals.total_cents

    def test_from_json_with_markdown(self, sample_result):
        """Test parsing JSON wrapped in markdown code blocks."""
        json_str = f"```json\n{sample_result.to_json()}\n```"
        result2 = BudgetExtractionResult.from_json(json_str)
        assert result2.jurisdiction_id == sample_result.jurisdiction_id

    def test_validate_passes(self, sample_result):
        """Test validation passes when totals match."""
        validation = sample_result.validate(expected_total_cents=6800000000)
        assert validation["valid"] is True
        assert validation["item_count"] == 3
        assert len(validation["issues"]) == 0

    def test_validate_fails_variance(self, sample_result):
        """Test validation fails when totals don't match."""
        # Expected is 10x actual - should fail
        validation = sample_result.validate(expected_total_cents=68000000000)
        assert validation["valid"] is False
        assert len(validation["issues"]) > 0
        assert "differs from expected" in validation["issues"][0]

    def test_validate_flags_negative(self):
        """Test validation flags negative amounts."""
        result = BudgetExtractionResult(
            jurisdiction_id="city-test",
            fiscal_year="2025-2026",
            source_url="test.pdf",
            items=[
                BudgetLineItem(
                    fund="General Fund",
                    department="Police",
                    program=None,
                    line_item="Police Refund",
                    budgeted_cents=-100000,  # Negative!
                ),
            ],
        )
        validation = result.validate()
        assert validation["valid"] is False
        assert any("Negative" in issue for issue in validation["issues"])

    def test_validate_flags_suspiciously_large(self):
        """Test validation flags suspiciously large amounts (citywide budget leak)."""
        result = BudgetExtractionResult(
            jurisdiction_id="city-test",
            fiscal_year="2025-2026",
            source_url="test.pdf",
            items=[
                BudgetLineItem(
                    fund="General Fund",
                    department=None,
                    program=None,
                    line_item="Total City Budget",
                    budgeted_cents=192000000000,  # $1.92B - suspiciously large for line item
                ),
            ],
        )
        validation = result.validate()
        assert validation["valid"] is False
        assert any("Suspiciously large" in issue for issue in validation["issues"])


class TestBuildBudgetExtractionPrompt:
    """Test prompt building function."""

    def test_basic_prompt(self):
        prompt = build_budget_extraction_prompt(
            municipality="San Rafael",
            state="California",
            fiscal_year="2025-2026",
        )
        assert "San Rafael" in prompt
        assert "California" in prompt
        assert "2025-2026" in prompt
        assert "city-san-rafael" in prompt

    def test_prompt_includes_accuracy_rules(self):
        prompt = build_budget_extraction_prompt(
            municipality="San Rafael",
            state="California",
            fiscal_year="2025-2026",
        )
        # Check that Layer 2 accuracy rules are included
        assert "DO NOT Extract" in prompt
        assert "Investment portfolio" in prompt
        assert "citywide" in prompt.lower()
        assert "cents" in prompt

    def test_prompt_includes_document_context(self):
        prompt = build_budget_extraction_prompt(
            municipality="San Rafael",
            state="California",
            fiscal_year="2025-2026",
            document_context="Page 45: Police Department $28,456,789",
        )
        assert "Page 45: Police Department" in prompt

    def test_prompt_class(self):
        prompt_obj = BudgetExtractionPrompt(
            municipality="San Rafael",
            state="California",
            fiscal_year="2025-2026",
            source_url="https://example.com/budget.pdf",
        )
        prompt_str = prompt_obj.render()
        assert "San Rafael" in prompt_str
        assert "https://example.com/budget.pdf" in prompt_str


class TestValidateExtractionResponse:
    """Test the validation helper function."""

    def test_validate_valid_json(self):
        response = json.dumps({
            "jurisdiction_id": "city-san-rafael",
            "fiscal_year": "2025-2026",
            "source_url": "test.pdf",
            "items": [
                {
                    "fund": "General Fund",
                    "department": "Police",
                    "line_item": "Police",
                    "budgeted_cents": 2800000000,
                }
            ],
            "totals": {"total_cents": 2800000000},
        })
        validation = validate_extraction_response(response, expected_total_cents=2800000000)
        assert validation["valid"] is True

    def test_validate_invalid_json(self):
        validation = validate_extraction_response("not valid json")
        assert validation["valid"] is False
        assert "Invalid JSON" in validation["issues"][0]

    def test_validate_missing_field(self):
        response = json.dumps({"fiscal_year": "2025-2026"})  # Missing jurisdiction_id
        validation = validate_extraction_response(response)
        assert validation["valid"] is False
        assert "Missing required field" in validation["issues"][0]


class TestPromptOutputSchema:
    """Test that prompt includes valid JSON schema examples."""

    def test_prompt_json_example_is_valid(self):
        """Verify the JSON examples in the prompt are syntactically correct."""
        prompt = build_budget_extraction_prompt(
            municipality="Test",
            state="California",
            fiscal_year="2025-2026",
        )
        # Find JSON blocks in the prompt
        import re
        json_blocks = re.findall(r'```json\s*(\{[^`]+\})\s*```', prompt, re.DOTALL)
        assert len(json_blocks) > 0, "Prompt should contain JSON examples"

        for block in json_blocks:
            # Should parse without error
            data = json.loads(block)
            assert "jurisdiction_id" in data or "fund" in data
