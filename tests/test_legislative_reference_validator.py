"""
Tests for Legislative Reference Validator

Ensures factual accuracy of bill/program citations in AI-generated comments.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from legislative_reference_validator import (
    LegislativeReferenceValidator,
    validate_comment_draft
)


def test_valid_references():
    """Test that valid references pass validation."""
    legislative_context = {
        'state_bills': [
            {
                'bill_number': 'AB 1147',
                'title': 'E-bike Safety Act'
            },
            {
                'bill_number': 'SB 9',
                'title': 'HOME Act'
            }
        ],
        'federal_programs': []
    }

    # Comment with correct references
    comment = """Dear Council Members,

I support this e-bike safety initiative. California Assembly Bill 1147 (AB 1147)
provides important framework for e-bike classification and regulation. Additionally,
the HOME Act (SB 9) supports housing density near transit.

Thank you for your consideration."""

    corrected_text, errors = validate_comment_draft(comment, legislative_context)

    # Should pass validation with no errors
    assert len(errors) == 0, f"Expected no errors, got {len(errors)}"
    assert corrected_text == comment, "Text should not be modified"

    print("✅ test_valid_references passed")


def test_typo_correction():
    """Test that typos like 'AB 117' are corrected to 'AB 1147'."""
    legislative_context = {
        'state_bills': [
            {
                'bill_number': 'AB 1147',
                'title': 'E-bike Safety Act'
            }
        ],
        'federal_programs': []
    }

    # Comment with typo (AB 117 instead of AB 1147)
    comment = """Dear Council Members,

I support this e-bike safety initiative. California Assembly Bill 117 (AB 117)
provides important framework for e-bike classification.

Thank you."""

    corrected_text, errors = validate_comment_draft(comment, legislative_context)

    # Should detect and correct the typo (reports once even if multiple instances)
    assert len(errors) >= 1, f"Expected at least 1 error, got {len(errors)}"
    assert errors[0]['type'] == 'typo'
    assert errors[0]['severity'] == 'auto_correctable'
    assert 'AB 117' in errors[0]['found']
    assert 'AB 1147' in errors[0]['expected']

    # Should auto-correct the text
    assert 'AB 1147' in corrected_text, "Text should be corrected to AB 1147"
    assert 'AB 117' not in corrected_text, "Typo should be removed"

    print("✅ test_typo_correction passed")


def test_invalid_reference():
    """Test that completely invalid references are detected."""
    legislative_context = {
        'state_bills': [
            {
                'bill_number': 'AB 1147',
                'title': 'E-bike Safety Act'
            }
        ],
        'federal_programs': []
    }

    # Comment with invalid bill reference
    comment = """Dear Council Members,

I support this initiative. California Assembly Bill 999 (AB 999)
provides important framework.

Thank you."""

    corrected_text, errors = validate_comment_draft(comment, legislative_context)

    # Should detect invalid reference (reports once even if multiple instances)
    assert len(errors) >= 1, f"Expected at least 1 error, got {len(errors)}"
    assert errors[0]['type'] == 'invalid_reference'
    assert errors[0]['severity'] == 'critical'
    assert 'AB 999' in errors[0]['found']

    print("✅ test_invalid_reference passed")


def test_missing_digit_correction():
    """Test correction of missing digits (e.g., 'AB 114' -> 'AB 1147')."""
    legislative_context = {
        'state_bills': [
            {
                'bill_number': 'AB 1147',
                'title': 'E-bike Safety Act'
            }
        ],
        'federal_programs': []
    }

    # Comment with missing digit
    comment = "I support AB 114 which provides important framework."

    corrected_text, errors = validate_comment_draft(comment, legislative_context)

    # Should detect and correct
    assert len(errors) == 1
    assert errors[0]['type'] == 'typo'
    assert 'AB 1147' in corrected_text

    print("✅ test_missing_digit_correction passed")


def test_no_legislative_context():
    """Test that validation is skipped when no legislative context exists."""
    legislative_context = None

    comment = "I support this initiative. AB 999 is great."

    corrected_text, errors = validate_comment_draft(comment, legislative_context)

    # Should skip validation
    assert len(errors) == 0
    assert corrected_text == comment

    print("✅ test_no_legislative_context passed")


def test_case_insensitive_matching():
    """Test that bill matching is case-insensitive."""
    legislative_context = {
        'state_bills': [
            {
                'bill_number': 'AB 1147',
                'title': 'E-bike Safety Act'
            }
        ],
        'federal_programs': []
    }

    # Comment with lowercase bill reference
    comment = "I support ab 1147 which provides important framework."

    corrected_text, errors = validate_comment_draft(comment, legislative_context)

    # Should pass validation (case-insensitive)
    assert len(errors) == 0

    print("✅ test_case_insensitive_matching passed")


def test_multiple_bills():
    """Test validation with multiple bills."""
    legislative_context = {
        'state_bills': [
            {
                'bill_number': 'AB 1147',
                'title': 'E-bike Safety Act'
            },
            {
                'bill_number': 'SB 9',
                'title': 'HOME Act'
            },
            {
                'bill_number': 'AB 2011',
                'title': 'Affordable Housing Act'
            }
        ],
        'federal_programs': []
    }

    # Comment with multiple bills, one typo
    comment = """I support this initiative.

AB 1147 provides e-bike framework.
SB 9 (HOME Act) enables housing.
AB 201 supports affordable housing."""  # Typo: AB 201 instead of AB 2011

    corrected_text, errors = validate_comment_draft(comment, legislative_context)

    # Should detect and correct the typo
    assert len(errors) == 1
    assert 'AB 2011' in errors[0]['expected']
    assert 'AB 2011' in corrected_text

    print("✅ test_multiple_bills passed")


def run_all_tests():
    """Run all validation tests."""
    print("\n" + "="*60)
    print("Legislative Reference Validator Tests")
    print("="*60 + "\n")

    test_valid_references()
    test_typo_correction()
    test_invalid_reference()
    test_missing_digit_correction()
    test_no_legislative_context()
    test_case_insensitive_matching()
    test_multiple_bills()

    print("\n" + "="*60)
    print("✅ All tests passed!")
    print("="*60 + "\n")


if __name__ == '__main__':
    run_all_tests()
