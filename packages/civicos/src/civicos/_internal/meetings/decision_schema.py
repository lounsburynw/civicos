"""
Decision schema validation for the indexing pipeline.

Provides JSON Schema validation for Decision objects before vector indexing,
catching malformed data early in the pipeline.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

try:
    import jsonschema
    from jsonschema import Draft7Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    Draft7Validator = None

logger = logging.getLogger(__name__)

# JSON Schema for Decision objects
# Matches the Decision dataclass in decision.py
DECISION_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Decision",
    "description": "City council decision record",
    "type": "object",
    "required": ["decision_id", "meeting_date", "agenda_item", "title", "summary", "outcome", "vote"],
    "properties": {
        "decision_id": {
            "type": "string",
            "minLength": 1,
            "description": "Unique identifier (e.g., '20251117-item-6a')"
        },
        "meeting_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
            "description": "ISO format date (YYYY-MM-DD)"
        },
        "agenda_item": {
            "type": "string",
            "minLength": 1,
            "description": "Agenda item reference (e.g., '6.a')"
        },
        "title": {
            "type": "string",
            "minLength": 1,
            "description": "Decision title"
        },
        "summary": {
            "type": "string",
            "minLength": 1,
            "description": "1-2 sentence summary of the decision"
        },
        "outcome": {
            "type": "string",
            "enum": ["approved", "denied", "continued", "withdrawn", "received", "adopted", "other"],
            "description": "Decision outcome"
        },
        "vote": {
            "type": "object",
            "required": ["ayes", "noes", "absent"],
            "properties": {
                "ayes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Council members voting yes"
                },
                "noes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Council members voting no"
                },
                "absent": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absent council members"
                },
                "motion_by": {
                    "type": ["string", "null"],
                    "description": "Who made the motion"
                },
                "second_by": {
                    "type": ["string", "null"],
                    "description": "Who seconded the motion"
                },
                "passed": {
                    "type": "boolean",
                    "description": "Whether the motion passed"
                },
                "unanimous": {
                    "type": "boolean",
                    "description": "Whether the vote was unanimous"
                },
                "vote_count": {
                    "type": "string",
                    "description": "Human-readable vote count (e.g., '4-0')"
                }
            }
        },
        "staff_recommendation": {
            "type": ["object", "null"],
            "description": "Staff recommendation details"
        },
        "public_input": {
            "type": ["object", "null"],
            "description": "Public input summary"
        },
        "legal_instruments": {
            "type": "array",
            "items": {"type": "object"},
            "description": "Resolutions/ordinances implementing the decision"
        },
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Topic categories (e.g., ['housing', 'homelessness'])"
        },
        "source_documents": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Paths to source PDFs/JSONs"
        },
        "extraction_method": {
            "type": "string",
            "description": "How the decision was extracted (llm, simple, etc.)"
        },
        "financial_impact_cents": {
            "type": ["integer", "null"],
            "description": "Financial impact in cents (e.g., 15000000 = $150,000). SESSION 438."
        }
    },
    "additionalProperties": True
}


@dataclass
class DecisionValidationResult:
    """Result of validating a single decision."""

    decision_id: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class BatchDecisionValidationResult:
    """Result of validating a batch of decisions."""

    total_count: int
    valid_count: int
    invalid_count: int
    invalid_results: List[DecisionValidationResult] = field(default_factory=list)
    validation_time_ms: float = 0.0

    @property
    def is_valid(self) -> bool:
        """True if all decisions passed validation."""
        return self.invalid_count == 0

    @property
    def valid_decisions(self) -> List[Any]:
        """List of valid decision objects (set by validator)."""
        return getattr(self, '_valid_decisions', [])

    @valid_decisions.setter
    def valid_decisions(self, value: List[Any]) -> None:
        self._valid_decisions = value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_count": self.total_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "is_valid": self.is_valid,
            "validation_time_ms": self.validation_time_ms,
            "invalid_results": [r.to_dict() for r in self.invalid_results],
        }


class DecisionValidator:
    """
    Validates Decision objects against JSON schema.

    Usage:
        validator = DecisionValidator()
        result = validator.validate_batch(decisions)
        if result.is_valid:
            # All decisions valid, proceed with indexing
            pass
        else:
            # Some decisions invalid, check result.invalid_results
            for invalid in result.invalid_results:
                logger.warning(f"Invalid decision {invalid.decision_id}: {invalid.errors}")
    """

    def __init__(self, strict: bool = False):
        """
        Initialize the validator.

        Args:
            strict: If True, validation failures will raise exceptions.
                   If False (default), invalid decisions are logged and filtered.
        """
        self.strict = strict
        self._schema = DECISION_SCHEMA

        if HAS_JSONSCHEMA:
            self._validator = Draft7Validator(self._schema)
        else:
            self._validator = None
            logger.warning(
                "jsonschema not installed. Decision validation disabled. "
                "Install with: pip install jsonschema"
            )

    def _get_decision_id(self, decision: Any) -> str:
        """Extract decision ID from decision object."""
        if isinstance(decision, dict):
            return decision.get('decision_id', 'unknown')
        elif hasattr(decision, 'decision_id'):
            return decision.decision_id
        return 'unknown'

    def _decision_to_dict(self, decision: Any) -> Dict[str, Any]:
        """Convert a Decision object to a dictionary for validation."""
        if isinstance(decision, dict):
            return decision
        elif hasattr(decision, 'to_dict'):
            return decision.to_dict()
        else:
            raise ValueError(f"Cannot convert {type(decision)} to dict for validation")

    def validate_one(self, decision: Any) -> DecisionValidationResult:
        """
        Validate a single decision.

        Args:
            decision: Decision object or dict

        Returns:
            DecisionValidationResult with validation status and errors
        """
        decision_id = self._get_decision_id(decision)

        # If jsonschema not available, pass through
        if not HAS_JSONSCHEMA or self._validator is None:
            return DecisionValidationResult(
                decision_id=decision_id,
                is_valid=True,
                warnings=["jsonschema not installed, validation skipped"]
            )

        try:
            decision_dict = self._decision_to_dict(decision)
        except Exception as e:
            return DecisionValidationResult(
                decision_id=decision_id,
                is_valid=False,
                errors=[f"Failed to convert decision to dict: {str(e)}"]
            )

        errors = []
        warnings = []

        # Collect all validation errors
        for error in self._validator.iter_errors(decision_dict):
            # Format error message with path
            path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
            error_msg = f"{path}: {error.message}"
            errors.append(error_msg)

        # Additional semantic validations (warnings)
        outcome = decision_dict.get('outcome', '')
        if outcome == 'other':
            warnings.append("Outcome is 'other' - consider using a more specific value")

        vote = decision_dict.get('vote', {})
        if vote.get('passed') and len(vote.get('ayes', [])) == 0:
            warnings.append("Vote passed but no 'ayes' recorded")

        return DecisionValidationResult(
            decision_id=decision_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_batch(
        self,
        decisions: List[Any],
        filter_invalid: bool = True
    ) -> BatchDecisionValidationResult:
        """
        Validate a batch of decisions.

        Args:
            decisions: List of Decision objects or dicts
            filter_invalid: If True, valid_decisions will exclude invalid ones

        Returns:
            BatchDecisionValidationResult with counts and invalid decision details
        """
        import time
        start_time = time.time()

        valid_decisions = []
        invalid_results = []
        valid_count = 0
        invalid_count = 0

        for decision in decisions:
            result = self.validate_one(decision)

            if result.is_valid:
                valid_count += 1
                valid_decisions.append(decision)
            else:
                invalid_count += 1
                invalid_results.append(result)

                # Log validation failure
                decision_id = result.decision_id
                errors = "; ".join(result.errors)
                logger.warning(f"Decision validation failed [{decision_id}]: {errors}")

                if self.strict:
                    raise ValueError(
                        f"Decision validation failed for {decision_id}: {errors}"
                    )

        validation_time_ms = (time.time() - start_time) * 1000

        batch_result = BatchDecisionValidationResult(
            total_count=len(decisions),
            valid_count=valid_count,
            invalid_count=invalid_count,
            invalid_results=invalid_results,
            validation_time_ms=validation_time_ms,
        )

        if filter_invalid:
            batch_result.valid_decisions = valid_decisions
        else:
            batch_result.valid_decisions = decisions

        # Log summary
        if invalid_count > 0:
            logger.warning(
                f"Decision validation: {valid_count}/{len(decisions)} valid, "
                f"{invalid_count} invalid ({validation_time_ms:.1f}ms)"
            )
        else:
            logger.debug(
                f"Decision validation: all {len(decisions)} valid ({validation_time_ms:.1f}ms)"
            )

        return batch_result
