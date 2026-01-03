"""
Extraction prompt templates for AI-assisted data extraction.

These prompts are designed to be model-agnostic and can be used with
Claude, GPT-4, Gemini, or other LLMs capable of structured extraction.
"""

from .budget_extraction import (
    BudgetExtractionPrompt,
    BudgetExtractionResult,
    BudgetLineItem,
    BudgetTotals,
    build_budget_extraction_prompt,
)

__all__ = [
    "BudgetExtractionPrompt",
    "BudgetExtractionResult",
    "BudgetLineItem",
    "BudgetTotals",
    "build_budget_extraction_prompt",
]
