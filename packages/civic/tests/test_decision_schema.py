"""
Tests for decision schema validation.
"""

import pytest

from civic._internal.meetings.decision_schema import (
    DecisionValidator,
    DecisionValidationResult,
    BatchDecisionValidationResult,
    DECISION_SCHEMA,
)


class TestDecisionSchema:
    """Test the JSON schema definition."""

    def test_schema_has_required_fields(self):
        """Schema should define required fields."""
        assert "required" in DECISION_SCHEMA
        required = DECISION_SCHEMA["required"]
        assert "decision_id" in required
        assert "meeting_date" in required
        assert "agenda_item" in required
        assert "title" in required
        assert "summary" in required
        assert "outcome" in required
        assert "vote" in required

    def test_schema_has_property_definitions(self):
        """Schema should define all Decision properties."""
        properties = DECISION_SCHEMA["properties"]
        expected_props = [
            "decision_id", "meeting_date", "agenda_item", "title", "summary",
            "outcome", "vote", "staff_recommendation", "public_input",
            "legal_instruments", "topics", "source_documents", "extraction_method"
        ]
        for prop in expected_props:
            assert prop in properties, f"Missing property: {prop}"

    def test_outcome_enum_values(self):
        """Outcome should be restricted to valid values."""
        outcome_prop = DECISION_SCHEMA["properties"]["outcome"]
        assert "enum" in outcome_prop
        assert "approved" in outcome_prop["enum"]
        assert "denied" in outcome_prop["enum"]
        assert "continued" in outcome_prop["enum"]
        assert "withdrawn" in outcome_prop["enum"]


class TestDecisionValidator:
    """Test the DecisionValidator class."""

    def test_validate_valid_decision_dict(self):
        """Valid decision dict should pass validation."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "20251117-item-6a",
            "meeting_date": "2025-11-17",
            "agenda_item": "6.a",
            "title": "Emergency Shelter Resolution",
            "summary": "Council approved emergency shelter funding.",
            "outcome": "approved",
            "vote": {
                "ayes": ["Smith", "Jones", "Brown"],
                "noes": [],
                "absent": ["Wilson"]
            }
        }
        result = validator.validate_one(decision)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_missing_required_field(self):
        """Decision missing required field should fail validation."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "20251117-item-6a",
            # missing meeting_date
            "agenda_item": "6.a",
            "title": "Emergency Shelter Resolution",
            "summary": "Council approved emergency shelter funding.",
            "outcome": "approved",
            "vote": {"ayes": [], "noes": [], "absent": []}
        }
        result = validator.validate_one(decision)
        assert result.is_valid is False
        assert any("meeting_date" in err for err in result.errors)

    def test_validate_empty_decision_id(self):
        """Decision with empty decision_id should fail validation."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "",
            "meeting_date": "2025-11-17",
            "agenda_item": "6.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "approved",
            "vote": {"ayes": [], "noes": [], "absent": []}
        }
        result = validator.validate_one(decision)
        assert result.is_valid is False
        assert any("decision_id" in err for err in result.errors)

    def test_validate_invalid_meeting_date_format(self):
        """Meeting date must be in YYYY-MM-DD format."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "test-1",
            "meeting_date": "11/17/2025",  # Wrong format
            "agenda_item": "6.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "approved",
            "vote": {"ayes": [], "noes": [], "absent": []}
        }
        result = validator.validate_one(decision)
        assert result.is_valid is False
        assert any("meeting_date" in err for err in result.errors)

    def test_validate_invalid_outcome(self):
        """Outcome must be one of the allowed values."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "test-1",
            "meeting_date": "2025-11-17",
            "agenda_item": "6.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "invalid_outcome",  # Not in enum
            "vote": {"ayes": [], "noes": [], "absent": []}
        }
        result = validator.validate_one(decision)
        assert result.is_valid is False
        assert any("outcome" in err for err in result.errors)

    def test_validate_missing_vote_field(self):
        """Vote object must have required fields."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "test-1",
            "meeting_date": "2025-11-17",
            "agenda_item": "6.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "approved",
            "vote": {"ayes": []}  # Missing noes and absent
        }
        result = validator.validate_one(decision)
        assert result.is_valid is False
        assert any("noes" in err or "absent" in err for err in result.errors)

    def test_validate_all_outcomes(self):
        """All valid outcome values should pass."""
        validator = DecisionValidator()
        valid_outcomes = ["approved", "denied", "continued", "withdrawn", "received", "adopted", "other"]

        for outcome in valid_outcomes:
            decision = {
                "decision_id": "test-1",
                "meeting_date": "2025-11-17",
                "agenda_item": "6.a",
                "title": "Test",
                "summary": "Test summary",
                "outcome": outcome,
                "vote": {"ayes": [], "noes": [], "absent": []}
            }
            result = validator.validate_one(decision)
            assert result.is_valid is True, f"Outcome '{outcome}' should be valid"

    def test_validate_optional_fields(self):
        """Optional fields can be null or absent."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "test-1",
            "meeting_date": "2025-11-17",
            "agenda_item": "6.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "approved",
            "vote": {"ayes": [], "noes": [], "absent": []},
            "staff_recommendation": None,
            "public_input": None,
            "legal_instruments": [],
            "topics": [],
            "source_documents": []
        }
        result = validator.validate_one(decision)
        assert result.is_valid is True


class TestBatchDecisionValidation:
    """Test batch validation functionality."""

    def test_validate_batch_all_valid(self):
        """All valid decisions should pass batch validation."""
        validator = DecisionValidator()
        decisions = [
            {
                "decision_id": f"test-{i}",
                "meeting_date": "2025-11-17",
                "agenda_item": f"{i}.a",
                "title": f"Test {i}",
                "summary": f"Test summary {i}",
                "outcome": "approved",
                "vote": {"ayes": ["A"], "noes": [], "absent": []}
            }
            for i in range(5)
        ]
        result = validator.validate_batch(decisions)
        assert result.is_valid is True
        assert result.total_count == 5
        assert result.valid_count == 5
        assert result.invalid_count == 0
        assert len(result.valid_decisions) == 5

    def test_validate_batch_some_invalid(self):
        """Batch with some invalid decisions should filter them out."""
        validator = DecisionValidator()
        decisions = [
            {
                "decision_id": "valid-1",
                "meeting_date": "2025-11-17",
                "agenda_item": "1.a",
                "title": "Valid",
                "summary": "Valid summary",
                "outcome": "approved",
                "vote": {"ayes": [], "noes": [], "absent": []}
            },
            {
                "decision_id": "",  # Invalid - empty
                "meeting_date": "2025-11-17",
                "agenda_item": "2.a",
                "title": "Invalid",
                "summary": "Invalid summary",
                "outcome": "approved",
                "vote": {"ayes": [], "noes": [], "absent": []}
            },
            {
                "decision_id": "valid-2",
                "meeting_date": "2025-11-18",
                "agenda_item": "3.a",
                "title": "Another Valid",
                "summary": "Another valid summary",
                "outcome": "denied",
                "vote": {"ayes": [], "noes": ["A"], "absent": []}
            },
        ]
        result = validator.validate_batch(decisions)
        assert result.is_valid is False
        assert result.total_count == 3
        assert result.valid_count == 2
        assert result.invalid_count == 1
        assert len(result.valid_decisions) == 2

    def test_validate_batch_empty(self):
        """Empty list should pass validation."""
        validator = DecisionValidator()
        result = validator.validate_batch([])
        assert result.is_valid is True
        assert result.total_count == 0
        assert result.valid_count == 0
        assert result.invalid_count == 0

    def test_validate_batch_no_filter(self):
        """filter_invalid=False should keep all decisions."""
        validator = DecisionValidator()
        decisions = [
            {
                "decision_id": "valid-1",
                "meeting_date": "2025-11-17",
                "agenda_item": "1.a",
                "title": "Valid",
                "summary": "Valid summary",
                "outcome": "approved",
                "vote": {"ayes": [], "noes": [], "absent": []}
            },
            {
                "decision_id": "",  # Invalid
                "meeting_date": "2025-11-17",
                "agenda_item": "2.a",
                "title": "Invalid",
                "summary": "Invalid summary",
                "outcome": "approved",
                "vote": {"ayes": [], "noes": [], "absent": []}
            },
        ]
        result = validator.validate_batch(decisions, filter_invalid=False)
        assert result.invalid_count == 1
        # When filter_invalid=False, valid_decisions contains all
        assert len(result.valid_decisions) == 2


class TestStrictMode:
    """Test strict validation mode."""

    def test_strict_mode_raises_on_invalid(self):
        """Strict mode should raise exception on invalid decision."""
        validator = DecisionValidator(strict=True)
        decision = {
            "decision_id": "",  # Invalid
            "meeting_date": "2025-11-17",
            "agenda_item": "1.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "approved",
            "vote": {"ayes": [], "noes": [], "absent": []}
        }
        with pytest.raises(ValueError) as exc_info:
            validator.validate_batch([decision])
        assert "validation failed" in str(exc_info.value).lower()

    def test_non_strict_mode_no_raise(self):
        """Non-strict mode should not raise on invalid decision."""
        validator = DecisionValidator(strict=False)
        decision = {
            "decision_id": "",  # Invalid
            "meeting_date": "2025-11-17",
            "agenda_item": "1.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "approved",
            "vote": {"ayes": [], "noes": [], "absent": []}
        }
        # Should not raise
        result = validator.validate_batch([decision])
        assert result.invalid_count == 1


class TestValidationResult:
    """Test validation result structures."""

    def test_decision_validation_result_to_dict(self):
        """DecisionValidationResult should serialize to dict."""
        result = DecisionValidationResult(
            decision_id="test-001",
            is_valid=False,
            errors=["decision_id: too short"],
            warnings=["Outcome is 'other'"]
        )
        d = result.to_dict()
        assert d["decision_id"] == "test-001"
        assert d["is_valid"] is False
        assert "decision_id: too short" in d["errors"]
        assert "Outcome is 'other'" in d["warnings"]

    def test_batch_validation_result_to_dict(self):
        """BatchDecisionValidationResult should serialize to dict."""
        result = BatchDecisionValidationResult(
            total_count=10,
            valid_count=8,
            invalid_count=2,
            validation_time_ms=15.5
        )
        d = result.to_dict()
        assert d["total_count"] == 10
        assert d["valid_count"] == 8
        assert d["invalid_count"] == 2
        assert d["is_valid"] is False
        assert d["validation_time_ms"] == 15.5


class TestSemanticValidation:
    """Test semantic validation warnings."""

    def test_warning_for_other_outcome(self):
        """Should warn when outcome is 'other'."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "test-1",
            "meeting_date": "2025-11-17",
            "agenda_item": "1.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "other",
            "vote": {"ayes": [], "noes": [], "absent": []}
        }
        result = validator.validate_one(decision)
        assert result.is_valid is True  # Still valid, just warning
        assert len(result.warnings) > 0
        assert any("other" in w.lower() for w in result.warnings)

    def test_warning_for_passed_without_ayes(self):
        """Should warn when vote passed but no ayes recorded."""
        validator = DecisionValidator()
        decision = {
            "decision_id": "test-1",
            "meeting_date": "2025-11-17",
            "agenda_item": "1.a",
            "title": "Test",
            "summary": "Test summary",
            "outcome": "approved",
            "vote": {"ayes": [], "noes": [], "absent": [], "passed": True}
        }
        result = validator.validate_one(decision)
        assert result.is_valid is True  # Still valid, just warning
        assert len(result.warnings) > 0
        assert any("ayes" in w.lower() for w in result.warnings)
