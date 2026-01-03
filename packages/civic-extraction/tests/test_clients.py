"""
Tests for civic-extraction clients.
"""

import pytest
from datetime import datetime

from civic_extraction import LegistarClient, CivicClerkClient, ProudCityClient, Meeting
from civic_extraction import create_san_rafael_client, create_san_rafael_source
from civic_extraction import ProudCitySource, ExtractionConfig, DataSource, ValidationResult
from civic_extraction.clients.base import BaseExtractor, Extractor
from civic_extraction.clients.usaspending import USAspendingClient
from civic_extraction.clients.cagrants import CaliforniaGrantsClient


class TestMeetingDataclass:
    """Test the Meeting dataclass."""

    def test_meeting_creation(self):
        """Test basic Meeting creation."""
        meeting = Meeting(
            id="test-001",
            title="City Council Meeting",
            meeting_datetime=datetime(2025, 12, 1, 18, 0),
            jurisdiction_id="city-test"
        )
        assert meeting.id == "test-001"
        assert meeting.title == "City Council Meeting"
        assert meeting.source_platform == "unknown"

    def test_meeting_to_dict(self):
        """Test Meeting serialization."""
        meeting = Meeting(
            id="test-001",
            title="City Council Meeting",
            meeting_datetime=datetime(2025, 12, 1, 18, 0),
            jurisdiction_id="city-test",
            meeting_type="city_council"
        )
        d = meeting.to_dict()
        assert d["id"] == "test-001"
        assert d["meeting_type"] == "city_council"
        assert "2025-12-01" in d["meeting_datetime"]


class TestLegistarClient:
    """Test LegistarClient."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = LegistarClient("berkeley")
        assert client.client_name == "berkeley"
        assert client.jurisdiction_id == "city-berkeley"
        assert client.platform_name == "legistar"

    def test_custom_jurisdiction_id(self):
        """Test custom jurisdiction ID override."""
        client = LegistarClient("berkeley", jurisdiction_id="custom-id")
        assert client.jurisdiction_id == "custom-id"

    def test_infer_meeting_type_council(self):
        """Test meeting type inference for council."""
        client = LegistarClient("berkeley")
        assert client._infer_meeting_type("City Council") == "city_council"
        assert client._infer_meeting_type("CITY COUNCIL Regular Meeting") == "city_council"

    def test_infer_meeting_type_planning(self):
        """Test meeting type inference for planning."""
        client = LegistarClient("berkeley")
        assert client._infer_meeting_type("Planning Commission") == "planning_commission"

    def test_infer_meeting_type_other(self):
        """Test meeting type inference for unknown."""
        client = LegistarClient("berkeley")
        assert client._infer_meeting_type("Special Session") == "other"

    def test_normalize_event(self):
        """Test event normalization."""
        client = LegistarClient("berkeley")
        event = {
            "EventId": 12345,
            "EventBodyName": "City Council",
            "EventDate": "2025-12-01T00:00:00",
            "EventTime": "18:00:00",
            "EventLocation": "City Hall"
        }
        meeting = client.normalize_event(event)
        assert meeting.id == "legistar-berkeley-12345"
        assert meeting.meeting_type == "city_council"
        assert meeting.source_platform == "legistar"


class TestCivicClerkClient:
    """Test CivicClerkClient."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = CivicClerkClient("elcerritoca")
        assert client.subdomain == "elcerritoca"
        assert client.jurisdiction_id == "elcerritoca"
        assert client.platform_name == "civicclerk"

    def test_custom_jurisdiction_id(self):
        """Test custom jurisdiction ID override."""
        client = CivicClerkClient("elcerritoca", jurisdiction_id="city-el-cerrito")
        assert client.jurisdiction_id == "city-el-cerrito"

    def test_infer_meeting_type(self):
        """Test meeting type inference."""
        client = CivicClerkClient("elcerritoca")
        assert client._infer_meeting_type("City Council Meeting") == "city_council"
        assert client._infer_meeting_type("Planning Commission") == "planning_commission"
        assert client._infer_meeting_type("Parks Board") == "board"

    def test_normalize_event(self):
        """Test event normalization."""
        client = CivicClerkClient("elcerritoca", jurisdiction_id="city-el-cerrito")
        event = {
            "id": 789,
            "name": "City Council Regular Meeting",
            "startDateTime": "2025-12-01T18:00:00Z",
            "location": "Council Chambers",
            "publishedFiles": [
                {"name": "Agenda", "url": "https://example.com/agenda.pdf"}
            ]
        }
        meeting = client.normalize_event(event)
        assert meeting.id == "civicclerk-elcerritoca-789"
        assert meeting.meeting_type == "city_council"
        assert meeting.agenda_url == "https://example.com/agenda.pdf"
        assert meeting.jurisdiction_id == "city-el-cerrito"


class TestProudCityClient:
    """Test ProudCityClient."""

    def test_client_initialization(self):
        """Test client creates with correct configuration."""
        client = ProudCityClient(
            base_url="https://www.cityofsanrafael.org",
            jurisdiction_id="city-san-rafael"
        )
        assert client.jurisdiction_id == "city-san-rafael"
        assert client.base_url == "https://www.cityofsanrafael.org"
        assert client.platform_name == "proudcity"

    def test_default_archives(self):
        """Test default archive paths are set."""
        client = ProudCityClient(
            base_url="https://www.example.org",
            jurisdiction_id="city-example"
        )
        assert 'city_council' in client.archives
        assert 'planning_commission' in client.archives
        assert client.archives['city_council'] == '/city-council-meetings/'

    def test_custom_archives(self):
        """Test custom archive paths override defaults."""
        custom_archives = {'special_meetings': '/special/'}
        client = ProudCityClient(
            base_url="https://www.example.org",
            jurisdiction_id="city-example",
            archives=custom_archives
        )
        assert client.archives == custom_archives
        assert 'city_council' not in client.archives

    def test_extract_date_from_slug(self):
        """Test date extraction from meeting slugs."""
        client = ProudCityClient(
            base_url="https://www.example.org",
            jurisdiction_id="city-example"
        )
        # Standard format
        assert client._extract_date_from_slug("city-council-october-6-2025") == "2025-10-06"
        # With suffix
        assert client._extract_date_from_slug("planning-commission-november-4-2025-special-meeting") == "2025-11-04"
        # Invalid
        assert client._extract_date_from_slug("no-date-here") is None

    def test_normalize_event(self):
        """Test event normalization."""
        client = ProudCityClient(
            base_url="https://www.cityofsanrafael.org",
            jurisdiction_id="city-san-rafael"
        )
        event = {
            'title': 'City Council Meeting October 6, 2025',
            'meeting_slug': 'city-council-october-6-2025',
            'meeting_url': 'https://www.cityofsanrafael.org/meetings/city-council-october-6-2025/',
            'date_parsed': '2025-10-06',
            'meeting_type': 'city_council'
        }
        meeting = client.normalize_event(event)
        assert meeting.id == "proudcity-city-san-rafael-city-council-october-6-2025"
        assert meeting.meeting_type == "city_council"
        assert meeting.source_platform == "proudcity"
        assert meeting.jurisdiction_id == "city-san-rafael"

    def test_filter_by_date_range(self):
        """Test date filtering."""
        client = ProudCityClient(
            base_url="https://www.example.org",
            jurisdiction_id="city-example"
        )
        meetings = [
            {'date_parsed': '2025-10-01'},
            {'date_parsed': '2025-10-15'},
            {'date_parsed': '2025-11-01'},
        ]
        filtered = client._filter_by_date_range(meetings, '2025-10-01', '2025-10-31')
        assert len(filtered) == 2
        assert filtered[0]['date_parsed'] == '2025-10-01'
        assert filtered[1]['date_parsed'] == '2025-10-15'

    def test_make_absolute_url(self):
        """Test URL absolutization."""
        client = ProudCityClient(
            base_url="https://www.cityofsanrafael.org",
            jurisdiction_id="city-san-rafael"
        )
        # Already absolute
        assert client._make_absolute_url("https://example.com/file.pdf") == "https://example.com/file.pdf"
        # Relative
        assert client._make_absolute_url("/uploads/file.pdf") == "https://www.cityofsanrafael.org/uploads/file.pdf"


class TestSanRafaelFactory:
    """Test the San Rafael convenience factory."""

    def test_create_san_rafael_client(self):
        """Test convenience factory creates correct client."""
        client = create_san_rafael_client()
        assert client.jurisdiction_id == "city-san-rafael"
        assert client.base_url == "https://www.cityofsanrafael.org"
        assert client.platform_name == "proudcity"


class TestExtractorProtocol:
    """Test the Extractor protocol."""

    def test_legistar_implements_protocol(self):
        """Test LegistarClient implements Extractor protocol."""
        client = LegistarClient("berkeley")
        assert isinstance(client, Extractor)

    def test_civicclerk_implements_protocol(self):
        """Test CivicClerkClient implements Extractor protocol."""
        client = CivicClerkClient("elcerritoca")
        assert isinstance(client, Extractor)

    def test_proudcity_implements_protocol(self):
        """Test ProudCityClient implements Extractor protocol."""
        client = ProudCityClient(
            base_url="https://www.cityofsanrafael.org",
            jurisdiction_id="city-san-rafael"
        )
        assert isinstance(client, Extractor)


class TestExtractionConfig:
    """Test ExtractionConfig dataclass and loading."""

    def test_extraction_config_from_jurisdiction(self):
        """Test loading config from jurisdiction ID."""
        config = ExtractionConfig.from_jurisdiction("city-san-rafael")
        assert config.source_id == "proudcity-san-rafael"
        assert config.source_type == "proudcity"
        assert config.jurisdiction_id == "city-san-rafael"
        assert config.base_url == "https://www.cityofsanrafael.org"
        assert config.auto_discover is True
        assert "city_council" in config.archives
        assert "planning_commission" in config.archives

    def test_extraction_config_archives_complete(self):
        """Test San Rafael config has all discovered archives."""
        config = ExtractionConfig.from_jurisdiction("city-san-rafael")
        # Should have 15 discovered meeting types from Session 304
        assert len(config.archives) >= 15
        # Check a few specific types
        assert config.archives.get("city_council") == "/city-council-meetings/"
        assert config.archives.get("ada_access_advisory_committee") == "/ada-access-advisory-committee-meetings/"
        assert config.archives.get("design_review_board") == "/design-review-board-hearings/"

    def test_extraction_config_not_found(self):
        """Test missing config raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ExtractionConfig.from_jurisdiction("city-nonexistent")


class TestProudCitySource:
    """Test ProudCitySource config-driven wrapper."""

    def test_proudcity_source_from_jurisdiction(self):
        """Test creating ProudCitySource from jurisdiction ID."""
        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        assert source.source_id == "proudcity-city-san-rafael"
        assert source.source_type == "proudcity"
        assert source.config.jurisdiction_id == "city-san-rafael"

    def test_proudcity_source_has_client(self):
        """Test ProudCitySource exposes underlying client."""
        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        assert source.client is not None
        assert isinstance(source.client, ProudCityClient)

    def test_proudcity_source_archives_from_config(self):
        """Test ProudCitySource uses archives from config."""
        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        # Client should have 15+ archives from config, not just 6 defaults
        assert len(source.client.archives) >= 15
        assert "ada_access_advisory_committee" in source.client.archives

    def test_proudcity_source_implements_datasource(self):
        """Test ProudCitySource implements DataSource protocol."""
        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        assert isinstance(source, DataSource)

    def test_create_san_rafael_source_factory(self):
        """Test convenience factory for ProudCitySource."""
        source = create_san_rafael_source()
        assert source.source_id == "proudcity-city-san-rafael"
        assert isinstance(source, ProudCitySource)

    def test_create_san_rafael_client_uses_config(self):
        """Test create_san_rafael_client uses config by default."""
        client = create_san_rafael_client()
        # Should have 15+ archives from config, not just 6 defaults
        assert len(client.archives) >= 15


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_creation(self):
        """Test basic ValidationResult creation."""
        result = ValidationResult(
            is_valid=True,
            config_valid=True,
            api_reachable=True,
        )
        assert result.is_valid is True
        assert result.config_valid is True
        assert result.api_reachable is True
        assert result.errors == []
        assert result.warnings == []

    def test_validation_result_with_errors(self):
        """Test ValidationResult with errors."""
        result = ValidationResult(
            is_valid=False,
            config_valid=False,
            api_reachable=False,
            errors=["base_url is required", "jurisdiction_id is required"],
            warnings=["Archive path for city_council should start with /"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
        assert "base_url is required" in result.errors

    def test_validation_result_to_dict(self):
        """Test ValidationResult serialization."""
        result = ValidationResult(
            is_valid=True,
            config_valid=True,
            api_reachable=True,
            check_duration_ms=123.45,
            metadata={"body_count": 5},
        )
        d = result.to_dict()
        assert d["is_valid"] is True
        assert d["config_valid"] is True
        assert d["api_reachable"] is True
        assert d["check_duration_ms"] == 123.45
        assert d["metadata"]["body_count"] == 5
        assert "errors" in d
        assert "warnings" in d


class TestValidateMethods:
    """Test validate() methods on data source clients."""

    def test_legistar_validate_requires_client_name(self):
        """Test LegistarClient.validate() checks client_name."""
        # Create client with empty client_name (shouldn't happen normally)
        client = LegistarClient("")
        result = client.validate()
        assert result.is_valid is False
        assert result.config_valid is False
        assert "client_name is required" in result.errors

    def test_civicclerk_validate_requires_subdomain(self):
        """Test CivicClerkClient.validate() checks subdomain."""
        # Create client with empty subdomain (shouldn't happen normally)
        client = CivicClerkClient("")
        result = client.validate()
        assert result.is_valid is False
        assert result.config_valid is False
        assert "subdomain is required" in result.errors

    def test_proudcity_source_validate_checks_config(self):
        """Test ProudCitySource.validate() checks config fields."""
        # Create config with missing base_url
        config = ExtractionConfig(
            source_id="test-source",
            source_type="proudcity",
            jurisdiction_id="city-test",
            base_url="",  # Empty - should fail
            auto_discover=False,
            archives={},
        )
        source = ProudCitySource(config)
        result = source.validate()
        assert result.is_valid is False
        assert result.config_valid is False
        assert "base_url is required" in result.errors

    def test_proudcity_source_validate_requires_https(self):
        """Test ProudCitySource.validate() requires HTTPS."""
        config = ExtractionConfig(
            source_id="test-source",
            source_type="proudcity",
            jurisdiction_id="city-test",
            base_url="http://example.org",  # HTTP - should fail
            auto_discover=True,
        )
        source = ProudCitySource(config)
        result = source.validate()
        assert result.is_valid is False
        assert "HTTPS" in result.errors[0]

    def test_proudcity_source_validate_requires_archives_or_autodiscover(self):
        """Test ProudCitySource.validate() requires archives or auto_discover."""
        config = ExtractionConfig(
            source_id="test-source",
            source_type="proudcity",
            jurisdiction_id="city-test",
            base_url="https://example.org",
            auto_discover=False,
            archives={},  # Empty and no auto_discover
        )
        source = ProudCitySource(config)
        result = source.validate()
        assert result.is_valid is False
        assert "archives is empty and auto_discover is not enabled" in result.errors

    def test_proudcity_source_validate_timing(self):
        """Test ValidationResult includes timing info."""
        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        result = source.validate()
        # Should have timing info regardless of success/failure
        assert result.check_duration_ms >= 0


class TestPipeline:
    """Test the Pipeline class for ETL orchestration."""

    def test_pipeline_creation(self):
        """Test Pipeline creates with correct initial state."""
        from civic_extraction.pipeline import Pipeline, StageState

        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        pipeline = Pipeline(source, "city-san-rafael")

        assert pipeline.jurisdiction_id == "city-san-rafael"
        assert pipeline.source_id == "proudcity-city-san-rafael"

        # All stages should be pending
        status = pipeline.status()
        assert status["is_running"] is False
        assert status["stages"]["discover"]["state"] == StageState.PENDING.value
        assert status["stages"]["ingest"]["state"] == StageState.PENDING.value
        assert status["stages"]["store"]["state"] == StageState.PENDING.value
        assert status["stages"]["index"]["state"] == StageState.PENDING.value

    def test_pipeline_has_four_stages(self):
        """Test Pipeline has discover, ingest, store, index stages."""
        from civic_extraction.pipeline import Pipeline

        assert Pipeline.STAGES == ["discover", "ingest", "store", "index"]

    def test_pipeline_status_method(self):
        """Test Pipeline.status() returns dashboard-consumable dict."""
        from civic_extraction.pipeline import Pipeline

        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        pipeline = Pipeline(source, "city-san-rafael")

        status = pipeline.status()

        # Required keys
        assert "jurisdiction_id" in status
        assert "source_id" in status
        assert "is_running" in status
        assert "stages" in status

        # All four stages present
        assert "discover" in status["stages"]
        assert "ingest" in status["stages"]
        assert "store" in status["stages"]
        assert "index" in status["stages"]

        # Each stage has required fields
        for stage_name in ["discover", "ingest", "store", "index"]:
            stage = status["stages"][stage_name]
            assert "state" in stage
            assert "items_found" in stage
            assert "items_processed" in stage
            assert "duration_ms" in stage
            assert "errors" in stage

    def test_stage_status_to_dict(self):
        """Test StageStatus.to_dict() serialization."""
        from civic_extraction.pipeline import StageStatus, StageState
        from datetime import datetime

        status = StageStatus(
            state=StageState.COMPLETED,
            items_found=50,
            items_processed=48,
            duration_ms=1234.5,
            errors=["minor error"],
            started_at=datetime(2025, 12, 21, 10, 0, 0),
            completed_at=datetime(2025, 12, 21, 10, 0, 1),
            progress_percent=96.0,
        )

        d = status.to_dict()
        assert d["state"] == "completed"
        assert d["items_found"] == 50
        assert d["items_processed"] == 48
        assert d["duration_ms"] == 1234.5
        assert d["errors"] == ["minor error"]
        assert "2025-12-21" in d["started_at"]
        assert d["progress_percent"] == 96.0

    def test_pipeline_result_to_dict(self):
        """Test PipelineResult.to_dict() serialization."""
        from civic_extraction.pipeline import PipelineResult, StageStatus, StageState
        from datetime import datetime

        result = PipelineResult(
            success=True,
            stages={
                "discover": StageStatus(state=StageState.COMPLETED, items_found=50),
                "ingest": StageStatus(state=StageState.COMPLETED, items_processed=50),
                "index": StageStatus(state=StageState.COMPLETED, items_processed=50),
            },
            total_duration_ms=5000.0,
            started_at=datetime(2025, 12, 21, 10, 0, 0),
            completed_at=datetime(2025, 12, 21, 10, 0, 5),
            jurisdiction_id="city-san-rafael",
            source_id="proudcity-san-rafael",
        )

        d = result.to_dict()
        assert d["success"] is True
        assert d["total_duration_ms"] == 5000.0
        assert d["jurisdiction_id"] == "city-san-rafael"
        assert "discover" in d["stages"]
        assert d["stages"]["discover"]["state"] == "completed"

    def test_pipeline_reset(self):
        """Test Pipeline.reset() clears state."""
        from civic_extraction.pipeline import Pipeline, StageState

        source = ProudCitySource.from_jurisdiction("city-san-rafael")
        pipeline = Pipeline(source, "city-san-rafael")

        # Simulate some state
        pipeline._stages["discover"].state = StageState.COMPLETED
        pipeline._stages["discover"].items_found = 100

        # Reset
        pipeline.reset()

        status = pipeline.status()
        assert status["stages"]["discover"]["state"] == StageState.PENDING.value
        assert status["stages"]["discover"]["items_found"] == 0

    def test_stage_state_enum_values(self):
        """Test StageState enum has expected values."""
        from civic_extraction.pipeline import StageState

        assert StageState.PENDING.value == "pending"
        assert StageState.RUNNING.value == "running"
        assert StageState.COMPLETED.value == "completed"
        assert StageState.FAILED.value == "failed"
        assert StageState.SKIPPED.value == "skipped"


class TestPipelineWithMockSource:
    """Test Pipeline with a mock DataSource for isolated testing."""

    def test_pipeline_run_with_mock_source(self):
        """Test Pipeline.run() executes all stages with mock source."""
        from civic_extraction.pipeline import Pipeline, StageState
        from civic_extraction.clients.base import HealthStatus, Meeting
        from datetime import datetime

        class MockSource:
            """Mock DataSource for testing."""
            source_id = "mock-test"
            source_type = "mock"

            def health(self):
                return HealthStatus(
                    source_id="mock-test",
                    source_type="mock",
                    jurisdiction_id="city-test",
                    is_available=True,
                    available_count=3,
                    last_checked=datetime.now(),
                    check_duration_ms=10.0,
                )

            def get_meetings(self, days_ahead=90, days_past=30):
                return [
                    Meeting(
                        id="mock-1",
                        title="Mock Meeting 1",
                        meeting_datetime=datetime.now(),
                        jurisdiction_id="city-test",
                    ),
                    Meeting(
                        id="mock-2",
                        title="Mock Meeting 2",
                        meeting_datetime=datetime.now(),
                        jurisdiction_id="city-test",
                    ),
                ]

        source = MockSource()
        pipeline = Pipeline(source, "city-test")

        result = pipeline.run(skip_index=True)

        assert result.success is True
        assert result.jurisdiction_id == "city-test"
        assert result.source_id == "mock-test"

        # Discover stage should complete
        assert result.stages["discover"].state == StageState.COMPLETED
        assert result.stages["discover"].items_found == 3

        # Ingest stage should complete
        assert result.stages["ingest"].state == StageState.COMPLETED
        assert result.stages["ingest"].items_processed == 2

        # Index stage should be skipped
        assert result.stages["index"].state == StageState.SKIPPED

    def test_pipeline_callbacks_called(self):
        """Test Pipeline.run() calls callbacks at appropriate times."""
        from civic_extraction.pipeline import Pipeline
        from civic_extraction.clients.base import HealthStatus, Meeting
        from datetime import datetime

        class MockSource:
            source_id = "mock-test"
            source_type = "mock"

            def health(self):
                return HealthStatus(
                    source_id="mock-test",
                    source_type="mock",
                    jurisdiction_id="city-test",
                    is_available=True,
                    available_count=5,
                    last_checked=datetime.now(),
                    check_duration_ms=10.0,
                )

            def get_meetings(self, days_ahead=90, days_past=30):
                return [
                    Meeting(
                        id="mock-1",
                        title="Mock",
                        meeting_datetime=datetime.now(),
                        jurisdiction_id="city-test",
                    ),
                ]

        # Track callback invocations
        started_stages = []
        completed_stages = []

        def on_start(stage):
            started_stages.append(stage)

        def on_complete(stage, status):
            completed_stages.append(stage)

        source = MockSource()
        pipeline = Pipeline(source, "city-test")
        pipeline.run(
            on_stage_start=on_start,
            on_stage_complete=on_complete,
            skip_index=True,
        )

        assert "discover" in started_stages
        assert "ingest" in started_stages
        assert "discover" in completed_stages
        assert "ingest" in completed_stages

    def test_pipeline_handles_discover_failure(self):
        """Test Pipeline handles discover stage failure gracefully."""
        from civic_extraction.pipeline import Pipeline, StageState

        class FailingSource:
            source_id = "failing-test"
            source_type = "mock"

            def health(self):
                raise ConnectionError("Cannot connect to source")

            def get_meetings(self, days_ahead=90, days_past=30):
                return []

        errors_logged = []

        def on_error(stage, exc):
            errors_logged.append((stage, str(exc)))

        source = FailingSource()
        pipeline = Pipeline(source, "city-test")
        result = pipeline.run(on_error=on_error, skip_index=True)

        assert result.success is False
        assert result.stages["discover"].state == StageState.FAILED
        assert "Cannot connect" in result.stages["discover"].errors[0]
        assert result.stages["ingest"].state == StageState.SKIPPED
        assert ("discover", "Cannot connect to source") in errors_logged

    def test_pipeline_with_index_target(self):
        """Test Pipeline.run() with an index target."""
        from civic_extraction.pipeline import Pipeline, StageState
        from civic_extraction.clients.base import HealthStatus, Meeting
        from datetime import datetime

        class MockSource:
            source_id = "mock-test"
            source_type = "mock"

            def health(self):
                return HealthStatus(
                    source_id="mock-test",
                    source_type="mock",
                    jurisdiction_id="city-test",
                    is_available=True,
                    available_count=2,
                    last_checked=datetime.now(),
                    check_duration_ms=10.0,
                )

            def get_meetings(self, days_ahead=90, days_past=30):
                return [
                    Meeting(
                        id="mock-1",
                        title="Mock",
                        meeting_datetime=datetime.now(),
                        jurisdiction_id="city-test",
                    ),
                ]

        class MockIndexTarget:
            indexed_count = 0

            def index_meetings(self, meetings):
                self.indexed_count = len(meetings)
                return len(meetings)

        source = MockSource()
        index_target = MockIndexTarget()
        pipeline = Pipeline(source, "city-test", index_target=index_target)
        result = pipeline.run()

        assert result.success is True
        assert result.stages["index"].state == StageState.COMPLETED
        assert result.stages["index"].items_processed == 1
        assert index_target.indexed_count == 1


class TestUSAspendingClient:
    """Test USAspendingClient for federal award extraction."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = USAspendingClient("san-rafael", recipient_name="San Rafael")
        assert client.jurisdiction_id == "san-rafael"
        assert client.recipient_name == "San Rafael"
        assert client.platform_name == "usaspending"
        assert client.source_id == "usaspending-san-rafael"

    def test_client_with_zip_codes(self):
        """Test client initialization with zip codes."""
        client = USAspendingClient(
            "san-rafael",
            recipient_name="San Rafael",
            zip_codes=["94901", "94903"]
        )
        assert client.zip_codes == ["94901", "94903"]

    def test_award_type_code_groups(self):
        """Test award type code group definitions."""
        # Grants should be 02-05
        assert USAspendingClient.GRANT_TYPE_CODES == ["02", "03", "04", "05"]
        # Direct payments should be 06, 10
        assert USAspendingClient.DIRECT_PAYMENT_CODES == ["06", "10"]

    def test_normalize_award_requires_id(self):
        """Test _normalize_award returns None without award_id."""
        client = USAspendingClient("test")
        result = client._normalize_award({"Award Amount": 1000})
        assert result is None

    def test_normalize_award_requires_amount(self):
        """Test _normalize_award returns None without amount."""
        client = USAspendingClient("test")
        result = client._normalize_award({"generated_internal_id": "test-123"})
        assert result is None

    def test_normalize_award_rejects_negative(self):
        """Test _normalize_award returns None for negative amounts."""
        client = USAspendingClient("test")
        result = client._normalize_award({
            "generated_internal_id": "test-123",
            "Award Amount": -1000
        })
        assert result is None

    def test_normalize_award_converts_to_cents(self):
        """Test _normalize_award converts dollars to cents."""
        client = USAspendingClient("test")
        result = client._normalize_award({
            "generated_internal_id": "test-123",
            "Award Amount": 1234.56
        })
        assert result is not None
        assert result["amount_cents"] == 123456

    def test_normalize_award_maps_fields(self):
        """Test _normalize_award maps API fields correctly."""
        client = USAspendingClient("test")
        result = client._normalize_award({
            "generated_internal_id": "AWARD-123",
            "Award Amount": 5000.00,
            "CFDA Number": "97.056",
            "Recipient Name": "City of Test",
            "Award Type": "PROJECT GRANT (B)",
            "Awarding Agency": "DHS",
            "Funding Agency": "FEMA",
            "Description": "Fire prevention grant",
            "Period of Performance Start Date": "2024-01-01",
            "Period of Performance Current End Date": "2025-12-31",
        })
        assert result is not None
        assert result["award_id"] == "AWARD-123"
        assert result["amount_cents"] == 500000
        assert result["cfda_number"] == "97.056"
        assert result["recipient_name"] == "City of Test"
        assert result["award_type"] == "PROJECT GRANT (B)"
        assert result["awarding_agency"] == "DHS"
        assert result["funding_agency"] == "FEMA"
        assert result["program_name"] == "Fire prevention grant"
        assert result["period_start"] == "2024-01-01"
        assert result["period_end"] == "2025-12-31"


class TestUSAspendingClientIntegration:
    """Integration tests that call the real USAspending.gov API."""

    @pytest.mark.integration
    def test_health_check(self):
        """Test health check against real API."""
        client = USAspendingClient("san-rafael", recipient_name="San Rafael")
        health = client.health()
        assert health.is_available is True
        assert health.source_id == "usaspending-san-rafael"
        assert health.check_duration_ms > 0

    @pytest.mark.integration
    def test_validate(self):
        """Test validation against real API."""
        client = USAspendingClient("san-rafael", recipient_name="San Rafael")
        result = client.validate()
        assert result.is_valid is True
        assert result.api_reachable is True
        assert result.check_duration_ms > 0

    @pytest.mark.integration
    def test_get_awards_returns_data(self):
        """Test fetching real awards from USAspending.gov."""
        client = USAspendingClient("san-rafael", recipient_name="San Rafael")
        awards = client.get_awards(max_pages=1, limit=5)
        assert len(awards) > 0

        # Check first award has required fields
        award = awards[0]
        assert "award_id" in award
        assert "amount_cents" in award
        assert award["amount_cents"] >= 0

    @pytest.mark.integration
    def test_get_awards_by_cfda(self):
        """Test fetching awards filtered by CFDA number."""
        client = USAspendingClient("san-rafael", recipient_name="San Rafael")
        # 21.027 = Coronavirus State and Local Fiscal Recovery Funds
        awards = client.get_awards_by_cfda(["21.027"], max_pages=1, limit=5)

        # All returned awards should have the requested CFDA
        for award in awards:
            assert award.get("cfda_number") == "21.027"


class TestCaliforniaGrantsClient:
    """Test CaliforniaGrantsClient for CA state grant extraction."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = CaliforniaGrantsClient("san-rafael", city_name="San Rafael")
        assert client.jurisdiction_id == "san-rafael"
        assert client.city_name == "San Rafael"
        assert client.platform_name == "cagrants"
        assert client.source_id == "cagrants-san-rafael"

    def test_client_with_county(self):
        """Test client initialization with county."""
        client = CaliforniaGrantsClient(
            "san-rafael",
            city_name="San Rafael",
            county="Marin"
        )
        assert client.county == "Marin"

    def test_parse_amount_dollar_string(self):
        """Test _parse_amount parses dollar strings."""
        client = CaliforniaGrantsClient("test")
        assert client._parse_amount("$30,000,000") == 3_000_000_000  # cents
        assert client._parse_amount("$1,234.56") == 123456

    def test_parse_amount_plain_number(self):
        """Test _parse_amount parses plain numbers."""
        client = CaliforniaGrantsClient("test")
        assert client._parse_amount("5000") == 500000  # cents
        assert client._parse_amount("1000000") == 100_000_000

    def test_parse_amount_million_notation(self):
        """Test _parse_amount handles 'million' notation."""
        client = CaliforniaGrantsClient("test")
        assert client._parse_amount("$1.5 million") == 150_000_000  # cents
        assert client._parse_amount("30 million") == 3_000_000_000

    def test_parse_amount_range(self):
        """Test _parse_amount takes lower bound of range."""
        client = CaliforniaGrantsClient("test")
        # Takes $100,000 from range
        assert client._parse_amount("$100,000 - $500,000") == 10_000_000

    def test_parse_amount_empty(self):
        """Test _parse_amount returns None for empty."""
        client = CaliforniaGrantsClient("test")
        assert client._parse_amount("") is None
        assert client._parse_amount(None) is None

    def test_parse_date_iso_format(self):
        """Test _parse_date handles ISO format."""
        client = CaliforniaGrantsClient("test")
        assert client._parse_date("2025-01-15") == "2025-01-15"
        assert client._parse_date("2025-01-15T10:30:00") == "2025-01-15"

    def test_parse_date_us_format(self):
        """Test _parse_date handles US date format."""
        client = CaliforniaGrantsClient("test")
        assert client._parse_date("01/15/2025") == "2025-01-15"
        assert client._parse_date("12/31/2024 23:59:59") == "2024-12-31"

    def test_parse_date_empty(self):
        """Test _parse_date returns None for empty."""
        client = CaliforniaGrantsClient("test")
        assert client._parse_date("") is None
        assert client._parse_date(None) is None

    def test_normalize_grant_requires_id(self):
        """Test _normalize_grant returns None without grant ID."""
        client = CaliforniaGrantsClient("test")
        result = client._normalize_grant({"EstAvailFunds": "$1,000,000"})
        assert result is None

    def test_normalize_grant_maps_fields(self):
        """Test _normalize_grant maps API fields correctly."""
        client = CaliforniaGrantsClient("test")
        result = client._normalize_grant({
            "PortalID": "12345",
            "GrantID": "HCD-2025-001",
            "AgencyDept": "California Department of Housing and Community Development",
            "Title": "Local Early Action Planning (LEAP) Grants",
            "EstAvailFunds": "$30,000,000",
            "FundingSource": "State and Federal",
            "OpenDate": "2025-01-01",
            "ApplicationDeadline": "2025-03-31",
            "Status": "Active",
            "Type": "Grant",
            "Categories": "Housing",
            "ApplicantType": "Public Agency",
            "Geography": "Statewide",
            "Purpose": "Support local planning for housing development",
            "GrantURL": "https://www.hcd.ca.gov/leap",
        })
        assert result is not None
        assert result["passthrough_id"] == "ca-12345"
        assert result["state_grant_id"] == "HCD-2025-001"
        assert result["state_agency"] == "California Department of Housing and Community Development"
        assert result["state_program_name"] == "Local Early Action Planning (LEAP) Grants"
        assert result["local_amount_cents"] == 3_000_000_000  # $30M in cents
        assert result["federal_amount_cents"] == 3_000_000_000  # Has "Federal" in source
        assert result["period_start"] == "2025-01-01"
        assert result["period_end"] == "2025-03-31"
        assert result["source_url"] == "https://www.hcd.ca.gov/leap"
        assert result["metadata"]["status"] == "Active"
        assert result["metadata"]["categories"] == "Housing"

    def test_normalize_grant_fiscal_year_calculation(self):
        """Test _normalize_grant calculates CA fiscal year correctly."""
        client = CaliforniaGrantsClient("test")

        # July-December -> same calendar year is FY
        result = client._normalize_grant({
            "PortalID": "1",
            "OpenDate": "2025-07-15",  # July 2025 -> FY 2025
        })
        assert result["state_fiscal_year"] == 2025

        # January-June -> previous calendar year is FY
        result = client._normalize_grant({
            "PortalID": "2",
            "OpenDate": "2025-03-15",  # March 2025 -> FY 2024
        })
        assert result["state_fiscal_year"] == 2024

    def test_local_govt_categories(self):
        """Test LOCAL_GOVT_CATEGORIES contains expected categories."""
        assert "Housing" in CaliforniaGrantsClient.LOCAL_GOVT_CATEGORIES
        assert "Transportation" in CaliforniaGrantsClient.LOCAL_GOVT_CATEGORIES
        assert "Health & Human Services" in CaliforniaGrantsClient.LOCAL_GOVT_CATEGORIES


class TestCaliforniaGrantsClientIntegration:
    """Integration tests that call the real data.ca.gov CKAN API."""

    @pytest.mark.integration
    def test_health_check(self):
        """Test health check against real API."""
        client = CaliforniaGrantsClient("san-rafael", city_name="San Rafael")
        health = client.health()
        assert health.is_available is True
        assert health.source_id == "cagrants-san-rafael"
        assert health.check_duration_ms > 0
        assert health.available_count > 0  # Should have grants in the portal

    @pytest.mark.integration
    def test_validate(self):
        """Test validation against real API."""
        client = CaliforniaGrantsClient("san-rafael", city_name="San Rafael")
        result = client.validate()
        assert result.is_valid is True
        assert result.api_reachable is True
        assert result.check_duration_ms > 0
        assert result.metadata.get("total_grants", 0) > 0

    @pytest.mark.integration
    def test_get_grants_returns_data(self):
        """Test fetching real grants from data.ca.gov."""
        client = CaliforniaGrantsClient("san-rafael", city_name="San Rafael")
        grants = client.get_grants(limit=10, max_records=10)
        assert len(grants) > 0

        # Check first grant has required fields
        grant = grants[0]
        assert "passthrough_id" in grant
        assert "state_agency" in grant
        assert "local_amount_cents" in grant

    @pytest.mark.integration
    def test_get_grants_for_local_government(self):
        """Test fetching grants available to public agencies."""
        client = CaliforniaGrantsClient("san-rafael")
        grants = client.get_grants_for_local_government(
            status="Active",
            limit=10,
            max_records=10
        )

        # All returned grants should allow public agency applicants
        for grant in grants:
            applicant_types = grant.get("metadata", {}).get("applicant_types", "")
            assert "Public Agency" in applicant_types or applicant_types == ""

    @pytest.mark.integration
    def test_get_housing_grants(self):
        """Test fetching housing-related grants."""
        client = CaliforniaGrantsClient("san-rafael")
        grants = client.get_housing_grants(limit=10, max_records=10)

        # All returned grants should be in Housing category
        for grant in grants:
            categories = grant.get("metadata", {}).get("categories", "")
            assert "Housing" in categories or categories == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
