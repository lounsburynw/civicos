"""
Legislative Reference Validator - Ensures factual accuracy of bill/program citations.

Multi-layer safeguard system:
1. Extract bill references from AI-generated text
2. Validate against actual legislative context
3. Auto-correct common typos/abbreviations
4. Return validation report with corrections

Critical for maintaining official confidence in the platform.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class LegislativeReferenceValidator:
    """
    Validates legislative references in AI-generated text against source data.

    Prevents factual errors like "AB 117" when "AB 1147" is correct.
    """

    # Regex patterns for extracting bill references
    PATTERNS = {
        'ca_bill': re.compile(r'\b(AB|SB)\s*(\d+)\b', re.IGNORECASE),  # AB 1147, SB 9
        'federal_program': re.compile(r'\b(Title\s+[IVX]+(?:\s+Part\s+[A-Z])?|CDBG|HUD)\b', re.IGNORECASE),
    }

    def __init__(self, legislative_context: Dict):
        """
        Initialize validator with legislative context from event.

        Args:
            legislative_context: Dict with state_bills and federal_programs
        """
        self.state_bills = legislative_context.get('state_bills', [])
        self.federal_programs = legislative_context.get('federal_programs', [])

        # Build lookup tables for fast validation
        self._build_lookup_tables()

    def _build_lookup_tables(self):
        """Build fast lookup tables for bill numbers and program names."""
        self.valid_bill_numbers = set()
        self.bill_number_to_full = {}

        for bill in self.state_bills:
            bill_number = bill.get('bill_number', '')

            # Extract bill type and number (e.g., "AB 1147" -> type="AB", num="1147")
            match = re.match(r'(AB|SB)\s*(\d+)', bill_number, re.IGNORECASE)
            if match:
                bill_type, bill_num = match.groups()
                normalized = f"{bill_type.upper()} {bill_num}"
                self.valid_bill_numbers.add(normalized)
                self.bill_number_to_full[normalized] = bill

        self.valid_program_names = set()
        for program in self.federal_programs:
            program_name = program.get('program_name', '')
            self.valid_program_names.add(program_name)

    def extract_references(self, text: str) -> Dict[str, List[str]]:
        """
        Extract all legislative references from text.

        Returns:
            Dict with 'ca_bills' and 'federal_programs' lists
        """
        ca_bills = []
        federal_programs = []

        # Extract CA bills
        for match in self.PATTERNS['ca_bill'].finditer(text):
            bill_type, bill_num = match.groups()
            normalized = f"{bill_type.upper()} {bill_num}"
            ca_bills.append({
                'text': match.group(0),
                'normalized': normalized,
                'position': match.span()
            })

        # Extract federal programs
        for match in self.PATTERNS['federal_program'].finditer(text):
            federal_programs.append({
                'text': match.group(0),
                'position': match.span()
            })

        return {
            'ca_bills': ca_bills,
            'federal_programs': federal_programs
        }

    def validate_references(self, text: str) -> Tuple[bool, List[Dict], str]:
        """
        Validate all legislative references in text.

        Returns:
            Tuple of (is_valid, errors_list, corrected_text)
            - is_valid: False if any invalid references found
            - errors_list: List of validation errors with corrections
            - corrected_text: Text with auto-corrections applied
        """
        extracted = self.extract_references(text)
        errors = []
        corrected_text = text

        # Validate CA bills
        for ref in extracted['ca_bills']:
            normalized = ref['normalized']

            if normalized not in self.valid_bill_numbers:
                # Try to find a close match (typo correction)
                correction = self._find_closest_bill(normalized)

                if correction:
                    errors.append({
                        'type': 'typo',
                        'found': ref['text'],
                        'expected': correction,
                        'severity': 'auto_correctable',
                        'message': f"Found '{ref['text']}' but legislative context has '{correction}'"
                    })

                    # Auto-correct the text
                    corrected_text = corrected_text.replace(ref['text'], correction)
                else:
                    errors.append({
                        'type': 'invalid_reference',
                        'found': ref['text'],
                        'expected': None,
                        'severity': 'critical',
                        'message': f"Bill '{ref['text']}' not found in legislative context"
                    })

        is_valid = len([e for e in errors if e['severity'] == 'critical']) == 0

        return is_valid, errors, corrected_text

    def _find_closest_bill(self, normalized: str) -> Optional[str]:
        """
        Find closest matching bill number (for typo correction).

        Example: "AB 117" -> "AB 1147" (missing digit)
        """
        # Extract bill type and number
        match = re.match(r'(AB|SB)\s*(\d+)', normalized, re.IGNORECASE)
        if not match:
            return None

        bill_type, bill_num = match.groups()

        # Look for bills with same type and similar number
        for valid_bill in self.valid_bill_numbers:
            valid_match = re.match(r'(AB|SB)\s*(\d+)', valid_bill, re.IGNORECASE)
            if valid_match:
                valid_type, valid_num = valid_match.groups()

                # Same type?
                if valid_type.upper() == bill_type.upper():
                    # Check if it's a substring match (missing digits)
                    if bill_num in valid_num or valid_num in bill_num:
                        return valid_bill

                    # Check Levenshtein distance for other typos
                    if self._levenshtein_distance(bill_num, valid_num) <= 1:
                        return valid_bill

        return None

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def format_validation_report(self, errors: List[Dict]) -> str:
        """Format validation errors as human-readable report."""
        if not errors:
            return "✅ All legislative references validated successfully"

        lines = ["⚠️  Legislative Reference Validation Report:"]
        for i, error in enumerate(errors, 1):
            lines.append(f"\n{i}. {error['message']}")
            if error['expected']:
                lines.append(f"   → Auto-corrected to: {error['expected']}")

        return "\n".join(lines)


def validate_comment_draft(draft_text: str, legislative_context: Dict) -> Tuple[str, List[Dict]]:
    """
    Convenience function to validate and auto-correct a comment draft.

    Args:
        draft_text: AI-generated comment text
        legislative_context: Legislative context from event

    Returns:
        Tuple of (corrected_text, validation_errors)
    """
    if not legislative_context:
        # No legislative context to validate against
        return draft_text, []

    validator = LegislativeReferenceValidator(legislative_context)
    is_valid, errors, corrected_text = validator.validate_references(draft_text)

    if errors:
        logger.warning(f"Legislative reference validation found {len(errors)} issues")
        logger.warning(validator.format_validation_report(errors))

    return corrected_text, errors
