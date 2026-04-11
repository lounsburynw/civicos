"""
Tests for legislative_reference_validator.py — factual-accuracy safeguard for
bill/program citations in AI-generated comment drafts.

The module is pure logic (regex, set lookup, Levenshtein) so no mocking is
required. Every test pins concrete expected values against concrete inputs.

To run:
    pytest packages/civicos-services/tests/test_legislative_reference_validator.py -q --override-ini="addopts="
"""

import pytest

from civicos_services.legislative.legislative_reference_validator import (
    LegislativeReferenceValidator,
    validate_comment_draft,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Bill numbers chosen to avoid accidental substring collisions:
#   - "1147" does not contain "9", "35", or "2011" and vice versa.
#   - "9" and "35" are unambiguously distinct from "1147".
SIMPLE_CONTEXT = {
    "state_bills": [
        {"bill_number": "AB 1147", "title": "Housing Density"},
        {"bill_number": "SB 9", "title": "Lot Splits"},
        {"bill_number": "SB 35", "title": "Streamlined Approval"},
    ],
    "federal_programs": [
        {"program_name": "CDBG"},
        {"program_name": "Title IX"},
    ],
}


_SENTINEL = object()


def make_validator(context=_SENTINEL):
    if context is _SENTINEL:
        context = SIMPLE_CONTEXT
    return LegislativeReferenceValidator(context)


# ---------------------------------------------------------------------------
# __init__ / _build_lookup_tables
# ---------------------------------------------------------------------------

class TestBuildLookupTables:
    def test_normalizes_bill_numbers_with_single_space(self):
        v = make_validator()
        assert v.valid_bill_numbers == {"AB 1147", "SB 9", "SB 35"}

    def test_maps_normalized_bill_to_full_record(self):
        v = make_validator()
        assert v.bill_number_to_full["AB 1147"]["title"] == "Housing Density"
        assert v.bill_number_to_full["SB 9"]["title"] == "Lot Splits"

    def test_collapses_extra_whitespace_in_source_bill(self):
        v = make_validator({"state_bills": [{"bill_number": "AB   2011"}]})
        assert v.valid_bill_numbers == {"AB 2011"}

    def test_lowercase_bill_type_is_uppercased(self):
        v = make_validator({"state_bills": [{"bill_number": "ab 1147"}]})
        assert "AB 1147" in v.valid_bill_numbers
        assert "ab 1147" not in v.valid_bill_numbers

    def test_bill_without_space_is_normalized(self):
        v = make_validator({"state_bills": [{"bill_number": "SB9"}]})
        assert v.valid_bill_numbers == {"SB 9"}

    def test_bill_with_unknown_prefix_is_skipped(self):
        v = make_validator({"state_bills": [{"bill_number": "HR 1"}]})
        assert v.valid_bill_numbers == set()

    def test_bill_with_empty_number_is_skipped(self):
        v = make_validator({"state_bills": [{"bill_number": ""}]})
        assert v.valid_bill_numbers == set()

    def test_missing_bill_number_key_is_skipped(self):
        v = make_validator({"state_bills": [{"title": "orphan"}]})
        assert v.valid_bill_numbers == set()

    def test_federal_programs_stored_verbatim(self):
        v = make_validator()
        assert v.valid_program_names == {"CDBG", "Title IX"}

    def test_empty_context_yields_empty_lookups(self):
        v = make_validator({})
        assert v.valid_bill_numbers == set()
        assert v.valid_program_names == set()
        assert v.state_bills == []
        assert v.federal_programs == []

    def test_none_style_context_missing_keys(self):
        v = make_validator({"state_bills": []})
        assert v.valid_bill_numbers == set()
        assert v.valid_program_names == set()


# ---------------------------------------------------------------------------
# extract_references
# ---------------------------------------------------------------------------

class TestExtractReferences:
    def test_extracts_single_ca_bill_with_space(self):
        v = make_validator()
        out = v.extract_references("Please support AB 1147 today.")
        assert len(out["ca_bills"]) == 1
        assert out["ca_bills"][0]["text"] == "AB 1147"
        assert out["ca_bills"][0]["normalized"] == "AB 1147"
        assert out["ca_bills"][0]["position"] == (15, 22)

    def test_extracts_ca_bill_without_space(self):
        v = make_validator()
        out = v.extract_references("SB9 requires implementation.")
        assert len(out["ca_bills"]) == 1
        assert out["ca_bills"][0]["text"] == "SB9"
        assert out["ca_bills"][0]["normalized"] == "SB 9"

    def test_lowercase_bill_is_normalized_uppercase(self):
        v = make_validator()
        out = v.extract_references("the ab 1147 bill")
        assert out["ca_bills"][0]["text"] == "ab 1147"
        assert out["ca_bills"][0]["normalized"] == "AB 1147"

    def test_extracts_multiple_bills_in_order(self):
        v = make_validator()
        out = v.extract_references("Relates to AB 1147, SB 9, and SB 35.")
        normalized = [b["normalized"] for b in out["ca_bills"]]
        assert normalized == ["AB 1147", "SB 9", "SB 35"]

    def test_no_match_when_prefix_is_embedded_in_word(self):
        v = make_validator()
        out = v.extract_references("nabbed the flag")
        assert out["ca_bills"] == []

    def test_ignores_non_bill_letter_prefix(self):
        v = make_validator()
        out = v.extract_references("HR 3 is federal, not state")
        assert out["ca_bills"] == []

    def test_extracts_cdbg_federal_program(self):
        v = make_validator()
        out = v.extract_references("Funded via CDBG grants.")
        assert len(out["federal_programs"]) == 1
        assert out["federal_programs"][0]["text"] == "CDBG"
        assert out["federal_programs"][0]["position"] == (11, 15)

    def test_extracts_title_with_roman_numeral(self):
        v = make_validator()
        out = v.extract_references("Compliance with Title IX requirements.")
        assert len(out["federal_programs"]) == 1
        assert out["federal_programs"][0]["text"] == "Title IX"

    def test_extracts_title_with_part_suffix(self):
        v = make_validator()
        out = v.extract_references("Section covers Title XVIII Part A claims.")
        assert len(out["federal_programs"]) == 1
        assert out["federal_programs"][0]["text"] == "Title XVIII Part A"

    def test_extracts_hud_program(self):
        v = make_validator()
        out = v.extract_references("HUD provides oversight.")
        assert len(out["federal_programs"]) == 1
        assert out["federal_programs"][0]["text"] == "HUD"

    def test_lowercase_title_matches_via_ignorecase_flag(self):
        # federal_program pattern compiles with re.IGNORECASE, so lowercase
        # forms are matched and surfaced verbatim (no case normalization).
        v = make_validator()
        out = v.extract_references("the title ix program")
        assert len(out["federal_programs"]) == 1
        assert out["federal_programs"][0]["text"] == "title ix"

    def test_empty_text_returns_empty_lists(self):
        v = make_validator()
        out = v.extract_references("")
        assert out == {"ca_bills": [], "federal_programs": []}

    def test_text_with_no_references_returns_empty_lists(self):
        v = make_validator()
        out = v.extract_references("This is a comment about parks and trails.")
        assert out["ca_bills"] == []
        assert out["federal_programs"] == []

    def test_extract_does_not_consult_lookup_tables(self):
        # extract_references is pure regex — it surfaces AB 9999 even if the
        # validator wasn't told about it.
        v = make_validator({"state_bills": []})
        out = v.extract_references("See AB 9999.")
        assert out["ca_bills"][0]["normalized"] == "AB 9999"


# ---------------------------------------------------------------------------
# validate_references
# ---------------------------------------------------------------------------

class TestValidateReferences:
    def test_valid_bill_produces_no_errors(self):
        v = make_validator()
        is_valid, errors, corrected = v.validate_references("We support AB 1147.")
        assert is_valid is True
        assert errors == []
        assert corrected == "We support AB 1147."

    def test_clean_text_with_no_bills_is_valid(self):
        v = make_validator()
        is_valid, errors, corrected = v.validate_references("A comment about parks.")
        assert is_valid is True
        assert errors == []
        assert corrected == "A comment about parks."

    def test_typo_is_flagged_auto_correctable_and_text_corrected(self):
        # "AB 114" → substring "114" in "1147" → corrected to "AB 1147".
        v = make_validator()
        is_valid, errors, corrected = v.validate_references("We back AB 114 strongly.")
        assert is_valid is True  # auto-correctable, not critical
        assert len(errors) == 1
        err = errors[0]
        assert err["type"] == "typo"
        assert err["severity"] == "auto_correctable"
        assert err["found"] == "AB 114"
        assert err["expected"] == "AB 1147"
        assert "AB 114" in err["message"]
        assert "AB 1147" in err["message"]
        assert corrected == "We back AB 1147 strongly."

    def test_levenshtein_typo_correction(self):
        # "AB 1148" vs "AB 1147" — single substitution, distance 1,
        # substring check fails ("1148" not in "1147" and vice versa).
        v = make_validator()
        is_valid, errors, corrected = v.validate_references("Reference AB 1148 here.")
        assert is_valid is True
        assert len(errors) == 1
        assert errors[0]["expected"] == "AB 1147"
        assert errors[0]["severity"] == "auto_correctable"
        assert corrected == "Reference AB 1147 here."

    def test_unknown_bill_is_critical_and_invalidates(self):
        v = make_validator()
        is_valid, errors, corrected = v.validate_references("Citing AB 9999.")
        assert is_valid is False
        assert len(errors) == 1
        err = errors[0]
        assert err["type"] == "invalid_reference"
        assert err["severity"] == "critical"
        assert err["found"] == "AB 9999"
        assert err["expected"] is None
        assert "AB 9999" in err["message"]
        # No correction applied for critical failures.
        assert corrected == "Citing AB 9999."

    def test_mixed_valid_and_critical_errors(self):
        v = make_validator()
        is_valid, errors, corrected = v.validate_references(
            "We support AB 1147 but oppose AB 9999."
        )
        assert is_valid is False  # because of the critical error
        assert len(errors) == 1
        assert errors[0]["found"] == "AB 9999"
        assert errors[0]["severity"] == "critical"
        # AB 1147 stays untouched; AB 9999 stays untouched.
        assert corrected == "We support AB 1147 but oppose AB 9999."

    def test_mixed_typo_and_critical(self):
        v = make_validator()
        is_valid, errors, corrected = v.validate_references(
            "Support AB 114 but oppose AB 9999."
        )
        assert is_valid is False  # critical error dominates
        types = sorted(e["type"] for e in errors)
        assert types == ["invalid_reference", "typo"]
        # The typo is still auto-corrected in text even though is_valid=False.
        assert "AB 1147" in corrected
        assert "AB 9999" in corrected

    def test_is_valid_true_when_only_typos(self):
        v = make_validator()
        is_valid, errors, _ = v.validate_references("Support AB 114.")
        assert is_valid is True
        assert all(e["severity"] == "auto_correctable" for e in errors)

    def test_bill_type_mismatch_not_corrected(self):
        # "AB 9" exists as SB 9 only — different type means no correction.
        v = make_validator()
        is_valid, errors, corrected = v.validate_references("See AB 9 please.")
        assert is_valid is False
        assert errors[0]["type"] == "invalid_reference"
        assert errors[0]["expected"] is None
        assert corrected == "See AB 9 please."


# ---------------------------------------------------------------------------
# _find_closest_bill
# ---------------------------------------------------------------------------

class TestFindClosestBill:
    def test_substring_match_missing_trailing_digit(self):
        v = make_validator()
        assert v._find_closest_bill("AB 114") == "AB 1147"

    def test_substring_match_when_input_contains_valid(self):
        # "11475" contains "1147" — the longer input still matches.
        v = make_validator()
        assert v._find_closest_bill("AB 11475") == "AB 1147"

    def test_levenshtein_single_substitution_match(self):
        v = make_validator()
        assert v._find_closest_bill("AB 1148") == "AB 1147"

    def test_no_match_for_unrelated_bill(self):
        v = make_validator()
        assert v._find_closest_bill("AB 2222") is None

    def test_different_type_returns_none(self):
        # SB 9 exists, but asked about AB 9 — distance is 0 on the number,
        # but the type check rejects cross-type matches.
        v = make_validator()
        assert v._find_closest_bill("AB 9") is None

    def test_unparseable_input_returns_none(self):
        v = make_validator()
        assert v._find_closest_bill("not a bill") is None

    def test_empty_lookup_table_returns_none(self):
        v = make_validator({"state_bills": []})
        assert v._find_closest_bill("AB 1147") is None


# ---------------------------------------------------------------------------
# _levenshtein_distance
# ---------------------------------------------------------------------------

class TestLevenshteinDistance:
    def setup_method(self):
        self.v = make_validator({})  # empty context — we only use the method

    def test_identical_strings_return_zero(self):
        assert self.v._levenshtein_distance("abc", "abc") == 0

    def test_empty_strings_return_zero(self):
        assert self.v._levenshtein_distance("", "") == 0

    def test_one_empty_returns_other_length(self):
        assert self.v._levenshtein_distance("abc", "") == 3
        assert self.v._levenshtein_distance("", "abc") == 3

    def test_single_substitution(self):
        assert self.v._levenshtein_distance("1148", "1147") == 1

    def test_single_insertion(self):
        assert self.v._levenshtein_distance("117", "1147") == 1

    def test_single_deletion(self):
        assert self.v._levenshtein_distance("11478", "1147") == 1

    def test_two_edits(self):
        # "kitten" vs "sitten" vs "sittin" — two substitutions.
        assert self.v._levenshtein_distance("kitten", "sittin") == 2

    def test_classic_kitten_sitting(self):
        assert self.v._levenshtein_distance("kitten", "sitting") == 3

    def test_symmetry(self):
        a = self.v._levenshtein_distance("abc", "abcd")
        b = self.v._levenshtein_distance("abcd", "abc")
        assert a == b == 1


# ---------------------------------------------------------------------------
# format_validation_report
# ---------------------------------------------------------------------------

class TestFormatValidationReport:
    def test_empty_errors_returns_success_marker(self):
        v = make_validator()
        report = v.format_validation_report([])
        assert report == "✅ All legislative references validated successfully"

    def test_typo_error_includes_auto_correction_line(self):
        v = make_validator()
        errors = [
            {
                "type": "typo",
                "found": "AB 114",
                "expected": "AB 1147",
                "severity": "auto_correctable",
                "message": "Found 'AB 114' but legislative context has 'AB 1147'",
            }
        ]
        report = v.format_validation_report(errors)
        assert "⚠️" in report
        assert "Legislative Reference Validation Report" in report
        assert "1. Found 'AB 114' but legislative context has 'AB 1147'" in report
        assert "→ Auto-corrected to: AB 1147" in report

    def test_critical_error_omits_correction_line(self):
        v = make_validator()
        errors = [
            {
                "type": "invalid_reference",
                "found": "AB 9999",
                "expected": None,
                "severity": "critical",
                "message": "Bill 'AB 9999' not found in legislative context",
            }
        ]
        report = v.format_validation_report(errors)
        assert "Bill 'AB 9999' not found" in report
        assert "Auto-corrected" not in report

    def test_multiple_errors_are_numbered_sequentially(self):
        v = make_validator()
        errors = [
            {
                "type": "typo",
                "found": "AB 114",
                "expected": "AB 1147",
                "severity": "auto_correctable",
                "message": "Found 'AB 114' but legislative context has 'AB 1147'",
            },
            {
                "type": "invalid_reference",
                "found": "AB 9999",
                "expected": None,
                "severity": "critical",
                "message": "Bill 'AB 9999' not found in legislative context",
            },
        ]
        report = v.format_validation_report(errors)
        assert "1. Found 'AB 114'" in report
        assert "2. Bill 'AB 9999' not found" in report


# ---------------------------------------------------------------------------
# validate_comment_draft (module-level convenience)
# ---------------------------------------------------------------------------

class TestValidateCommentDraft:
    def test_empty_context_returns_text_unchanged_and_no_errors(self):
        text = "Support AB 1147 and SB 9."
        corrected, errors = validate_comment_draft(text, {})
        assert corrected == text
        assert errors == []

    def test_none_context_returns_text_unchanged_and_no_errors(self):
        text = "Support AB 1147."
        corrected, errors = validate_comment_draft(text, None)
        assert corrected == text
        assert errors == []

    def test_clean_draft_returns_unchanged(self):
        text = "We support AB 1147 and SB 9."
        corrected, errors = validate_comment_draft(text, SIMPLE_CONTEXT)
        assert corrected == text
        assert errors == []

    def test_typo_in_draft_is_auto_corrected(self):
        corrected, errors = validate_comment_draft(
            "We support AB 114 in this hearing.", SIMPLE_CONTEXT
        )
        assert corrected == "We support AB 1147 in this hearing."
        assert len(errors) == 1
        assert errors[0]["type"] == "typo"
        assert errors[0]["expected"] == "AB 1147"

    def test_unknown_bill_in_draft_is_reported_critical(self):
        corrected, errors = validate_comment_draft(
            "Citing AB 9999 for support.", SIMPLE_CONTEXT
        )
        # Text is unchanged for critical errors.
        assert corrected == "Citing AB 9999 for support."
        assert len(errors) == 1
        assert errors[0]["severity"] == "critical"
        assert errors[0]["found"] == "AB 9999"

    def test_logs_warning_when_errors_found(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING,
                             logger="civicos_services.legislative.legislative_reference_validator"):
            validate_comment_draft("Citing AB 9999.", SIMPLE_CONTEXT)
        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "found 1 issues" in messages

    def test_no_warning_logged_for_clean_draft(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING,
                             logger="civicos_services.legislative.legislative_reference_validator"):
            validate_comment_draft("We support AB 1147.", SIMPLE_CONTEXT)
        assert caplog.records == []
