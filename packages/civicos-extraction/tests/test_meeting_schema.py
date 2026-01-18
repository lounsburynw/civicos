"""
Tests for meeting schema validation.
"""

import pytest
from datetime import datetime, timezone

from civicos_extraction import Meeting, MeetingValidator, BatchValidationResult, MEETING_SCHEMA
from civicos_extraction.meeting_schema import MeetingValidationResult


class TestMeetingSchema:
    """Test the JSON schema definition."""

    def test_schema_has_required_fields(self):
        """Schema should define required fields."""
        assert "required" in MEETING_SCHEMA
        required = MEETING_SCHEMA["required"]
        assert "id" in required
        assert "title" in required
        assert "meeting_datetime" in required
        assert "jurisdiction_id" in required

    def test_schema_has_property_definitions(self):
        """Schema should define all Meeting properties."""
        properties = MEETING_SCHEMA["properties"]
        expected_props = [
            "id", "title", "meeting_datetime", "jurisdiction_id",
            "meeting_type", "status", "location", "virtual_url",
            "agenda_url", "minutes_url", "video_url", "source_platform", "source_url"
        ]
        for prop in expected_props:
            assert prop in properties, f"Missing property: {prop}"


class TestMeetingValidator:
    """Test the MeetingValidator class."""

    def test_validate_valid_meeting_object(self):
        """Valid Meeting object should pass validation."""
        validator = MeetingValidator()
        meeting = Meeting(
            id="test-001",
            title="City Council Meeting",
            meeting_datetime=datetime(2025, 12, 1, 18, 0),
            jurisdiction_id="city-test"
        )
        result = validator.validate_one(meeting)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_valid_meeting_dict(self):
        """Valid meeting dict should pass validation."""
        validator = MeetingValidator()
        meeting_dict = {
            "id": "test-001",
            "title": "City Council Meeting",
            "meeting_datetime": "2025-12-01T18:00:00",
            "jurisdiction_id": "city-test"
        }
        result = validator.validate_one(meeting_dict)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_missing_required_field(self):
        """Meeting missing required field should fail validation."""
        validator = MeetingValidator()
        meeting_dict = {
            "id": "test-001",
            # missing title
            "meeting_datetime": "2025-12-01T18:00:00",
            "jurisdiction_id": "city-test"
        }
        result = validator.validate_one(meeting_dict)
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("title" in err for err in result.errors)

    def test_validate_empty_id(self):
        """Meeting with empty id should fail validation."""
        validator = MeetingValidator()
        meeting_dict = {
            "id": "",
            "title": "City Council Meeting",
            "meeting_datetime": "2025-12-01T18:00:00",
            "jurisdiction_id": "city-test"
        }
        result = validator.validate_one(meeting_dict)
        assert result.is_valid is False
        assert any("id" in err for err in result.errors)

    def test_validate_empty_title(self):
        """Meeting with empty title should fail validation."""
        validator = MeetingValidator()
        meeting_dict = {
            "id": "test-001",
            "title": "",
            "meeting_datetime": "2025-12-01T18:00:00",
            "jurisdiction_id": "city-test"
        }
        result = validator.validate_one(meeting_dict)
        assert result.is_valid is False
        assert any("title" in err for err in result.errors)

    def test_validate_optional_fields_null(self):
        """Optional fields can be null."""
        validator = MeetingValidator()
        meeting_dict = {
            "id": "test-001",
            "title": "City Council Meeting",
            "meeting_datetime": "2025-12-01T18:00:00",
            "jurisdiction_id": "city-test",
            "meeting_type": None,
            "status": None,
            "location": None,
            "virtual_url": None,
            "agenda_url": None,
            "minutes_url": None,
            "video_url": None,
            "source_url": None
        }
        result = validator.validate_one(meeting_dict)
        assert result.is_valid is True

    def test_validate_all_fields_populated(self):
        """Meeting with all fields should pass validation."""
        validator = MeetingValidator()
        meeting = Meeting(
            id="test-001",
            title="City Council Meeting",
            meeting_datetime=datetime(2025, 12, 1, 18, 0),
            jurisdiction_id="city-test",
            meeting_type="city_council",
            status="scheduled",
            location="City Hall",
            virtual_url="https://zoom.us/j/123456",
            agenda_url="https://example.com/agenda.pdf",
            minutes_url="https://example.com/minutes.pdf",
            video_url="https://youtube.com/watch?v=abc123",
            source_platform="legistar",
            source_url="https://legistar.com/meeting/123"
        )
        result = validator.validate_one(meeting)
        assert result.is_valid is True


class TestBatchValidation:
    """Test batch validation functionality."""

    def test_validate_batch_all_valid(self):
        """All valid meetings should pass batch validation."""
        validator = MeetingValidator()
        meetings = [
            Meeting(
                id=f"test-{i}",
                title=f"Meeting {i}",
                meeting_datetime=datetime(2025, 12, i + 1, 18, 0),
                jurisdiction_id="city-test"
            )
            for i in range(5)
        ]
        result = validator.validate_batch(meetings)
        assert result.is_valid is True
        assert result.total_count == 5
        assert result.valid_count == 5
        assert result.invalid_count == 0
        assert len(result.valid_meetings) == 5

    def test_validate_batch_some_invalid(self):
        """Batch with some invalid meetings should filter them out."""
        validator = MeetingValidator()
        meetings = [
            Meeting(
                id="test-1",
                title="Valid Meeting",
                meeting_datetime=datetime(2025, 12, 1, 18, 0),
                jurisdiction_id="city-test"
            ),
            # Invalid: empty id
            {"id": "", "title": "Invalid Meeting", "meeting_datetime": "2025-12-02T18:00:00", "jurisdiction_id": "city-test"},
            Meeting(
                id="test-3",
                title="Another Valid Meeting",
                meeting_datetime=datetime(2025, 12, 3, 18, 0),
                jurisdiction_id="city-test"
            ),
        ]
        result = validator.validate_batch(meetings)
        assert result.is_valid is False
        assert result.total_count == 3
        assert result.valid_count == 2
        assert result.invalid_count == 1
        assert len(result.valid_meetings) == 2

    def test_validate_batch_all_invalid(self):
        """All invalid meetings should result in empty valid list."""
        validator = MeetingValidator()
        meetings = [
            {"id": "", "title": "Bad 1", "meeting_datetime": "2025-12-01T18:00:00", "jurisdiction_id": "city-test"},
            {"id": "", "title": "Bad 2", "meeting_datetime": "2025-12-02T18:00:00", "jurisdiction_id": "city-test"},
        ]
        result = validator.validate_batch(meetings)
        assert result.is_valid is False
        assert result.total_count == 2
        assert result.valid_count == 0
        assert result.invalid_count == 2
        assert len(result.valid_meetings) == 0

    def test_validate_batch_empty(self):
        """Empty list should pass validation."""
        validator = MeetingValidator()
        result = validator.validate_batch([])
        assert result.is_valid is True
        assert result.total_count == 0
        assert result.valid_count == 0
        assert result.invalid_count == 0

    def test_validate_batch_no_filter(self):
        """filter_invalid=False should keep all meetings."""
        validator = MeetingValidator()
        meetings = [
            Meeting(
                id="test-1",
                title="Valid Meeting",
                meeting_datetime=datetime(2025, 12, 1, 18, 0),
                jurisdiction_id="city-test"
            ),
            {"id": "", "title": "Invalid Meeting", "meeting_datetime": "2025-12-02T18:00:00", "jurisdiction_id": "city-test"},
        ]
        result = validator.validate_batch(meetings, filter_invalid=False)
        assert result.invalid_count == 1
        # When filter_invalid=False, valid_meetings contains all
        assert len(result.valid_meetings) == 2


class TestStrictMode:
    """Test strict validation mode."""

    def test_strict_mode_raises_on_invalid(self):
        """Strict mode should raise exception on invalid meeting."""
        validator = MeetingValidator(strict=True)
        meeting_dict = {
            "id": "",  # Invalid
            "title": "Meeting",
            "meeting_datetime": "2025-12-01T18:00:00",
            "jurisdiction_id": "city-test"
        }
        with pytest.raises(ValueError) as exc_info:
            validator.validate_batch([meeting_dict])
        assert "validation failed" in str(exc_info.value).lower()

    def test_non_strict_mode_no_raise(self):
        """Non-strict mode should not raise on invalid meeting."""
        validator = MeetingValidator(strict=False)
        meeting_dict = {
            "id": "",  # Invalid
            "title": "Meeting",
            "meeting_datetime": "2025-12-01T18:00:00",
            "jurisdiction_id": "city-test"
        }
        # Should not raise
        result = validator.validate_batch([meeting_dict])
        assert result.invalid_count == 1


class TestValidationResult:
    """Test validation result structures."""

    def test_meeting_validation_result_to_dict(self):
        """MeetingValidationResult should serialize to dict."""
        result = MeetingValidationResult(
            meeting_id="test-001",
            is_valid=False,
            errors=["id: too short"],
            warnings=["Old meeting date"]
        )
        d = result.to_dict()
        assert d["meeting_id"] == "test-001"
        assert d["is_valid"] is False
        assert "id: too short" in d["errors"]
        assert "Old meeting date" in d["warnings"]

    def test_batch_validation_result_to_dict(self):
        """BatchValidationResult should serialize to dict."""
        result = BatchValidationResult(
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


class TestDatetimeHandling:
    """Test datetime handling in validation."""

    def test_datetime_object_converted(self):
        """Datetime objects should be converted to ISO strings."""
        validator = MeetingValidator()
        meeting_dict = {
            "id": "test-001",
            "title": "Meeting",
            "meeting_datetime": datetime(2025, 12, 1, 18, 0),
            "jurisdiction_id": "city-test"
        }
        result = validator.validate_one(meeting_dict)
        assert result.is_valid is True

    def test_iso_string_accepted(self):
        """ISO format strings should be accepted."""
        validator = MeetingValidator()
        meeting_dict = {
            "id": "test-001",
            "title": "Meeting",
            "meeting_datetime": "2025-12-01T18:00:00Z",
            "jurisdiction_id": "city-test"
        }
        result = validator.validate_one(meeting_dict)
        assert result.is_valid is True

    def test_timezone_aware_datetime(self):
        """Timezone-aware datetimes should be handled."""
        validator = MeetingValidator()
        meeting = Meeting(
            id="test-001",
            title="Meeting",
            meeting_datetime=datetime(2025, 12, 1, 18, 0, tzinfo=timezone.utc),
            jurisdiction_id="city-test"
        )
        result = validator.validate_one(meeting)
        assert result.is_valid is True
