"""
Meeting schema validation for the ingestion pipeline.

Provides JSON Schema validation for Meeting objects before storage,
catching malformed data early in the pipeline.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import jsonschema
    from jsonschema import Draft7Validator, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    Draft7Validator = None
    ValidationError = Exception

from civic_extraction.clients.base import Meeting

logger = logging.getLogger(__name__)

# JSON Schema for Meeting objects
# Matches the Meeting dataclass in clients/base.py
MEETING_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Meeting",
    "description": "Normalized meeting data from civic platforms",
    "type": "object",
    "required": ["id", "title", "meeting_datetime", "jurisdiction_id"],
    "properties": {
        "id": {
            "type": "string",
            "minLength": 1,
            "description": "Unique identifier for the meeting"
        },
        "title": {
            "type": "string",
            "minLength": 1,
            "description": "Meeting title/name"
        },
        "meeting_datetime": {
            "type": "string",
            "description": "ISO 8601 datetime of the meeting"
        },
        "jurisdiction_id": {
            "type": "string",
            "minLength": 1,
            "description": "Jurisdiction identifier (e.g., 'city-san-rafael')"
        },
        "meeting_type": {
            "type": ["string", "null"],
            "description": "Type of meeting (e.g., 'Regular Meeting', 'Special Meeting')"
        },
        "status": {
            "type": ["string", "null"],
            "description": "Meeting status (e.g., 'Scheduled', 'Cancelled')"
        },
        "location": {
            "type": ["string", "null"],
            "description": "Physical location of the meeting"
        },
        "virtual_url": {
            "type": ["string", "null"],
            "description": "URL for virtual meeting access"
        },
        "agenda_url": {
            "type": ["string", "null"],
            "description": "URL to meeting agenda document"
        },
        "minutes_url": {
            "type": ["string", "null"],
            "description": "URL to meeting minutes document"
        },
        "video_url": {
            "type": ["string", "null"],
            "description": "URL to meeting video recording"
        },
        "source_platform": {
            "type": "string",
            "description": "Platform the meeting was extracted from"
        },
        "source_url": {
            "type": ["string", "null"],
            "description": "Original URL of the meeting on the source platform"
        }
    },
    "additionalProperties": True  # Allow raw_data and other fields
}


@dataclass
class MeetingValidationResult:
    """Result of validating a single meeting."""

    meeting_id: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class BatchValidationResult:
    """Result of validating a batch of meetings."""

    total_count: int
    valid_count: int
    invalid_count: int
    results: List[MeetingValidationResult] = field(default_factory=list)
    # Only store invalid results to save memory
    invalid_results: List[MeetingValidationResult] = field(default_factory=list)
    validation_time_ms: float = 0.0

    @property
    def is_valid(self) -> bool:
        """True if all meetings passed validation."""
        return self.invalid_count == 0

    @property
    def valid_meetings(self) -> List[Any]:
        """List of valid meeting objects (set by validator)."""
        return getattr(self, '_valid_meetings', [])

    @valid_meetings.setter
    def valid_meetings(self, value: List[Any]) -> None:
        self._valid_meetings = value

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


class MeetingValidator:
    """
    Validates Meeting objects against JSON schema.

    Usage:
        validator = MeetingValidator()
        result = validator.validate_batch(meetings)
        if result.is_valid:
            # All meetings valid, proceed with storage
            pass
        else:
            # Some meetings invalid, check result.invalid_results
            for invalid in result.invalid_results:
                logger.warning(f"Invalid meeting {invalid.meeting_id}: {invalid.errors}")
    """

    def __init__(self, strict: bool = False):
        """
        Initialize the validator.

        Args:
            strict: If True, validation failures will raise exceptions.
                   If False (default), invalid meetings are logged and filtered.
        """
        self.strict = strict
        self._schema = MEETING_SCHEMA

        if HAS_JSONSCHEMA:
            self._validator = Draft7Validator(self._schema)
        else:
            self._validator = None
            logger.warning(
                "jsonschema not installed. Meeting validation disabled. "
                "Install with: pip install jsonschema"
            )

    def _meeting_to_dict(self, meeting: Any) -> Dict[str, Any]:
        """Convert a Meeting object to a dictionary for validation."""
        if isinstance(meeting, Meeting):
            return meeting.to_dict()
        elif isinstance(meeting, dict):
            # Handle datetime conversion if needed
            result = dict(meeting)
            if 'meeting_datetime' in result:
                dt = result['meeting_datetime']
                if isinstance(dt, datetime):
                    result['meeting_datetime'] = dt.isoformat()
            return result
        else:
            # Try to convert via to_dict if available
            if hasattr(meeting, 'to_dict'):
                return meeting.to_dict()
            raise ValueError(f"Cannot convert {type(meeting)} to dict for validation")

    def _get_meeting_id(self, meeting: Any) -> str:
        """Extract meeting ID from meeting object."""
        if isinstance(meeting, Meeting):
            return meeting.id
        elif isinstance(meeting, dict):
            return meeting.get('id', 'unknown')
        elif hasattr(meeting, 'id'):
            return meeting.id
        return 'unknown'

    def validate_one(self, meeting: Any) -> MeetingValidationResult:
        """
        Validate a single meeting.

        Args:
            meeting: Meeting object, dict, or anything with to_dict()

        Returns:
            MeetingValidationResult with validation status and errors
        """
        meeting_id = self._get_meeting_id(meeting)

        # If jsonschema not available, pass through
        if not HAS_JSONSCHEMA or self._validator is None:
            return MeetingValidationResult(
                meeting_id=meeting_id,
                is_valid=True,
                warnings=["jsonschema not installed, validation skipped"]
            )

        try:
            meeting_dict = self._meeting_to_dict(meeting)
        except Exception as e:
            return MeetingValidationResult(
                meeting_id=meeting_id,
                is_valid=False,
                errors=[f"Failed to convert meeting to dict: {str(e)}"]
            )

        errors = []
        warnings = []

        # Collect all validation errors
        for error in self._validator.iter_errors(meeting_dict):
            # Format error message with path
            path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
            error_msg = f"{path}: {error.message}"
            errors.append(error_msg)

        # Additional semantic validations (warnings, not errors)
        if meeting_dict.get('title', '').strip() == '':
            # This is already caught by minLength, but just in case
            pass

        # Check for suspiciously old or future meetings (warning only)
        try:
            dt_str = meeting_dict.get('meeting_datetime', '')
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                years_diff = abs((now - dt).days / 365)
                if years_diff > 5:
                    warnings.append(
                        f"Meeting datetime {dt_str} is more than 5 years from now"
                    )
        except Exception:
            # Don't fail validation for datetime parsing issues
            pass

        return MeetingValidationResult(
            meeting_id=meeting_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_batch(
        self,
        meetings: List[Any],
        filter_invalid: bool = True
    ) -> BatchValidationResult:
        """
        Validate a batch of meetings.

        Args:
            meetings: List of Meeting objects or dicts
            filter_invalid: If True, valid_meetings will exclude invalid ones

        Returns:
            BatchValidationResult with counts and invalid meeting details
        """
        import time
        start_time = time.time()

        valid_meetings = []
        invalid_results = []
        valid_count = 0
        invalid_count = 0

        for meeting in meetings:
            result = self.validate_one(meeting)

            if result.is_valid:
                valid_count += 1
                valid_meetings.append(meeting)
            else:
                invalid_count += 1
                invalid_results.append(result)

                # Log validation failure
                meeting_id = result.meeting_id
                errors = "; ".join(result.errors)
                logger.warning(f"Meeting validation failed [{meeting_id}]: {errors}")

                if self.strict:
                    raise ValueError(
                        f"Meeting validation failed for {meeting_id}: {errors}"
                    )

        validation_time_ms = (time.time() - start_time) * 1000

        batch_result = BatchValidationResult(
            total_count=len(meetings),
            valid_count=valid_count,
            invalid_count=invalid_count,
            invalid_results=invalid_results,
            validation_time_ms=validation_time_ms,
        )

        if filter_invalid:
            batch_result.valid_meetings = valid_meetings
        else:
            batch_result.valid_meetings = meetings

        # Log summary
        if invalid_count > 0:
            logger.warning(
                f"Meeting validation: {valid_count}/{len(meetings)} valid, "
                f"{invalid_count} invalid ({validation_time_ms:.1f}ms)"
            )
        else:
            logger.debug(
                f"Meeting validation: all {len(meetings)} valid ({validation_time_ms:.1f}ms)"
            )

        return batch_result
