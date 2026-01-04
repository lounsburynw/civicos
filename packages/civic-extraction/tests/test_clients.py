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
from civic_extraction.clients.google_civic import GoogleCivicClient, create_san_rafael_civic_client


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

    def test_extraction_config_financial_section(self):
        """Test loading financial config from JSON."""
        config = ExtractionConfig.from_jurisdiction("city-san-rafael")
        assert config.financial is not None
        assert config.financial.state == "CA"
        assert config.financial.county == "Marin"
        assert config.financial.fiscal_year_start_month == 7

    def test_financial_config_to_dict(self):
        """Test FinancialConfig serialization."""
        config = ExtractionConfig.from_jurisdiction("city-san-rafael")
        assert config.financial is not None
        d = config.financial.to_dict()
        assert d["state"] == "CA"
        assert d["county"] == "Marin"
        # fiscal_year_start_month == 7 is default, so not included
        assert "fiscal_year_start_month" not in d


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


class TestGoogleCivicClient:
    """Test GoogleCivicClient for election and representative data."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = GoogleCivicClient("san-rafael", api_key="test-key")
        assert client.jurisdiction_id == "san-rafael"
        assert client.api_key == "test-key"
        assert client.platform_name == "google_civic"
        assert client.source_id == "google_civic-san-rafael"

    def test_client_env_api_key(self, monkeypatch):
        """Test client uses environment variable for API key."""
        monkeypatch.setenv("GOOGLE_CIVIC_API_KEY", "env-key")
        client = GoogleCivicClient("san-rafael")
        assert client.api_key == "env-key"

    def test_client_falls_back_to_google_api_key(self, monkeypatch):
        """Test client falls back to GOOGLE_API_KEY env var."""
        monkeypatch.delenv("GOOGLE_CIVIC_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
        client = GoogleCivicClient("san-rafael")
        assert client.api_key == "google-key"

    def test_normalize_election(self):
        """Test _normalize_election maps API response correctly."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        raw = {
            "id": "5000",
            "name": "VIP Test Election",
            "electionDay": "2025-11-04",
            "ocdDivisionId": "ocd-division/country:us"
        }
        result = client._normalize_election(raw)
        assert result["id"] == "5000"
        assert result["name"] == "VIP Test Election"
        assert result["election_date"].isoformat() == "2025-11-04"
        assert result["source"] == "google_civic"

    def test_normalize_election_invalid_date(self):
        """Test _normalize_election handles invalid date gracefully."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        raw = {"id": "123", "name": "Test", "electionDay": "invalid-date"}
        result = client._normalize_election(raw)
        assert result["election_date"] is None
        assert result["election_day_raw"] == "invalid-date"

    def test_map_contest_type_president(self):
        """Test _map_contest_type identifies presidential race."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"office": "President of the United States", "level": ["country"]}
        assert client._map_contest_type(contest) == "federal_president"

    def test_map_contest_type_senate(self):
        """Test _map_contest_type identifies senate race."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"office": "U.S. Senate", "level": ["country"]}
        assert client._map_contest_type(contest) == "federal_senate"

    def test_map_contest_type_house(self):
        """Test _map_contest_type identifies house race."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"office": "U.S. Representative", "level": ["country"]}
        assert client._map_contest_type(contest) == "federal_house"

    def test_map_contest_type_governor(self):
        """Test _map_contest_type identifies governor race."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"office": "Governor", "level": ["administrativeArea1"]}
        assert client._map_contest_type(contest) == "state_governor"

    def test_map_contest_type_council(self):
        """Test _map_contest_type identifies city council race."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"office": "City Council", "level": ["locality"]}
        assert client._map_contest_type(contest) == "local_council"

    def test_map_contest_type_mayor(self):
        """Test _map_contest_type identifies mayor race."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"office": "Mayor", "level": ["locality"]}
        assert client._map_contest_type(contest) == "local_mayor"

    def test_map_contest_type_referendum(self):
        """Test _map_contest_type identifies ballot measure."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"type": "Referendum", "referendumTitle": "Measure A", "level": ["local"]}
        assert client._map_contest_type(contest) == "local_measure"

    def test_map_contest_type_judicial(self):
        """Test _map_contest_type identifies judicial race."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"office": "Superior Court Judge", "level": ["administrativeArea2"]}
        assert client._map_contest_type(contest) == "judicial"

    def test_map_contest_type_school_board(self):
        """Test _map_contest_type identifies school board race."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        contest = {"office": "School Board Member", "level": ["locality"]}
        assert client._map_contest_type(contest) == "local_school_board"

    def test_normalize_voter_info_polling_locations(self):
        """Test _normalize_voter_info extracts polling locations."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        raw = {
            "election": {"id": "1", "name": "Test", "electionDay": "2025-11-04"},
            "pollingLocations": [{
                "address": {
                    "locationName": "City Hall",
                    "line1": "1400 Fifth Ave",
                    "city": "San Rafael",
                    "state": "CA",
                    "zip": "94901"
                },
                "pollingHours": "7am-8pm"
            }],
            "earlyVoteSites": [],
            "dropOffLocations": [],
            "contests": []
        }
        result = client._normalize_voter_info(raw)
        assert len(result["polling_locations"]) == 1
        assert result["polling_locations"][0]["name"] == "City Hall"
        assert result["polling_locations"][0]["is_early_voting"] is False

    def test_normalize_voter_info_early_voting(self):
        """Test _normalize_voter_info marks early voting sites."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        raw = {
            "election": {"id": "1", "name": "Test", "electionDay": "2025-11-04"},
            "pollingLocations": [],
            "earlyVoteSites": [{
                "address": {
                    "locationName": "Civic Center",
                    "line1": "100 Main St",
                    "city": "San Rafael",
                    "state": "CA",
                    "zip": "94901"
                }
            }],
            "dropOffLocations": [],
            "contests": []
        }
        result = client._normalize_voter_info(raw)
        assert len(result["polling_locations"]) == 1
        assert result["polling_locations"][0]["is_early_voting"] is True

    def test_normalize_voter_info_dropbox(self):
        """Test _normalize_voter_info marks drop-off locations."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        raw = {
            "election": {"id": "1", "name": "Test", "electionDay": "2025-11-04"},
            "pollingLocations": [],
            "earlyVoteSites": [],
            "dropOffLocations": [{
                "address": {
                    "locationName": "Library",
                    "line1": "200 Oak St",
                    "city": "San Rafael",
                    "state": "CA",
                    "zip": "94901"
                }
            }],
            "contests": []
        }
        result = client._normalize_voter_info(raw)
        assert len(result["polling_locations"]) == 1
        assert result["polling_locations"][0]["is_dropbox"] is True

    def test_normalize_voter_info_contests(self):
        """Test _normalize_voter_info extracts contests."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        raw = {
            "election": {"id": "1", "name": "Test", "electionDay": "2025-11-04"},
            "pollingLocations": [],
            "earlyVoteSites": [],
            "dropOffLocations": [],
            "contests": [{
                "office": "City Council",
                "district": {"name": "District 1"},
                "numberElected": 1,
                "candidates": [
                    {"name": "John Doe", "party": "Democratic", "candidateUrl": "https://example.com"},
                    {"name": "Jane Smith", "party": "Republican"}
                ]
            }]
        }
        result = client._normalize_voter_info(raw)
        assert len(result["contests"]) == 1
        contest = result["contests"][0]
        assert contest["title"] == "City Council"
        assert contest["district_name"] == "District 1"
        assert len(contest["candidates"]) == 2
        assert contest["candidates"][0]["name"] == "John Doe"
        assert contest["candidates"][0]["party"] == "Democratic"

    def test_normalize_voter_info_ballot_measure(self):
        """Test _normalize_voter_info extracts ballot measures."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        raw = {
            "election": {"id": "1", "name": "Test", "electionDay": "2025-11-04"},
            "pollingLocations": [],
            "earlyVoteSites": [],
            "dropOffLocations": [],
            "contests": [{
                "type": "Referendum",
                "referendumTitle": "Measure A",
                "referendumText": "Shall the city increase sales tax by 0.5%?",
                "referendumUrl": "https://example.com/measure-a"
            }]
        }
        result = client._normalize_voter_info(raw)
        assert len(result["contests"]) == 1
        contest = result["contests"][0]
        assert contest["title"] == "Measure A"
        assert contest["ballot_measure"] is not None
        assert contest["ballot_measure"]["title"] == "Measure A"
        assert "sales tax" in contest["ballot_measure"]["description"]

    def test_normalize_representatives(self):
        """Test _normalize_representatives extracts officials."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        raw = {
            "normalizedInput": {"city": "San Rafael", "state": "CA"},
            "divisions": {
                "ocd-division/country:us/state:ca/place:san_rafael": {"name": "San Rafael"}
            },
            "offices": [{
                "name": "Mayor",
                "divisionId": "ocd-division/country:us/state:ca/place:san_rafael",
                "levels": ["locality"],
                "roles": ["headOfGovernment"],
                "officialIndices": [0]
            }],
            "officials": [{
                "name": "Kate Colin",
                "party": "Nonpartisan",
                "phones": ["(415) 485-3070"],
                "urls": ["https://www.cityofsanrafael.org"],
                "photoUrl": "https://example.com/photo.jpg"
            }]
        }
        result = client._normalize_representatives(raw)
        assert len(result["officials"]) == 1
        official = result["officials"][0]
        assert official["name"] == "Kate Colin"
        assert official["seat"] == "Mayor"
        assert official["party"] == "Nonpartisan"
        assert "(415) 485-3070" in official["phones"]

    def test_health_no_api_key(self, monkeypatch):
        """Test health check returns error without API key."""
        monkeypatch.delenv("GOOGLE_CIVIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        client = GoogleCivicClient("san-rafael", api_key=None)
        health = client.health()
        assert health.is_available is False
        assert any("API key" in e for e in health.errors)

    def test_validate_no_api_key(self, monkeypatch):
        """Test validation returns error without API key."""
        monkeypatch.delenv("GOOGLE_CIVIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        client = GoogleCivicClient("san-rafael", api_key=None)
        result = client.validate()
        assert result.is_valid is False
        assert result.config_valid is False
        assert any("API key" in e for e in result.errors)

    def test_validate_short_api_key(self):
        """Test validation catches short API key."""
        client = GoogleCivicClient("san-rafael", api_key="short")
        result = client.validate()
        assert result.is_valid is False
        assert any("invalid" in e.lower() for e in result.errors)

    def test_create_san_rafael_factory(self):
        """Test convenience factory creates correct client."""
        client = create_san_rafael_civic_client()
        assert client.jurisdiction_id == "san-rafael"
        assert client.platform_name == "google_civic"

    def test_get_representatives_requires_address_or_division(self):
        """Test get_representatives requires either address or ocd_division_id."""
        client = GoogleCivicClient("san-rafael", api_key="test")
        with pytest.raises(ValueError, match="Either address or ocd_division_id required"):
            client.get_representatives()


class TestGoogleCivicMappers:
    """Test the storage mapper functions for Google Civic data."""

    def test_infer_election_type_primary(self):
        """Test _infer_election_type detects primary elections."""
        from civic_extraction.clients.google_civic import _infer_election_type
        assert _infer_election_type("California Primary Election") == "primary"
        assert _infer_election_type("2026 Primary") == "primary"

    def test_infer_election_type_runoff(self):
        """Test _infer_election_type detects runoff elections."""
        from civic_extraction.clients.google_civic import _infer_election_type
        assert _infer_election_type("Georgia Senate Runoff") == "runoff"

    def test_infer_election_type_special(self):
        """Test _infer_election_type detects special elections."""
        from civic_extraction.clients.google_civic import _infer_election_type
        assert _infer_election_type("Special Election") == "special"

    def test_infer_election_type_recall(self):
        """Test _infer_election_type detects recall elections."""
        from civic_extraction.clients.google_civic import _infer_election_type
        assert _infer_election_type("California Governor Recall") == "recall"

    def test_infer_election_type_general(self):
        """Test _infer_election_type defaults to general."""
        from civic_extraction.clients.google_civic import _infer_election_type
        assert _infer_election_type("California General Election") == "general"
        assert _infer_election_type("2026 Presidential Election") == "general"
        assert _infer_election_type("Unknown Election Type") == "general"

    def test_google_civic_to_election_normalized(self):
        """Test google_civic_to_election with normalized input."""
        from datetime import date
        from civic_extraction.clients.google_civic import google_civic_to_election

        normalized = {
            "id": "5000",
            "name": "California Primary Election",
            "election_date": date(2026, 3, 3),
            "ocd_division_id": "ocd-division/country:us/state:ca",
            "source": "google_civic",
            "raw_data": {"id": "5000", "name": "California Primary Election"}
        }
        result = google_civic_to_election(normalized, "san-rafael")
        assert result["id"] == "5000"
        assert result["name"] == "California Primary Election"
        assert result["election_date"] == "2026-03-03"
        assert result["election_type"] == "primary"
        assert result["source"] == "google_civic"
        assert result["ocd_division_id"] == "ocd-division/country:us/state:ca"

    def test_google_civic_to_election_raw(self):
        """Test google_civic_to_election with raw API response."""
        from civic_extraction.clients.google_civic import google_civic_to_election

        raw = {
            "id": "6000",
            "name": "2026 General Election",
            "electionDay": "2026-11-03",
            "ocdDivisionId": "ocd-division/country:us"
        }
        result = google_civic_to_election(raw, "san-rafael")
        assert result["id"] == "6000"
        assert result["name"] == "2026 General Election"
        assert result["election_date"] == "2026-11-03"
        assert result["election_type"] == "general"
        assert result["ocd_division_id"] == "ocd-division/country:us"

    def test_google_civic_to_election_generates_id(self):
        """Test google_civic_to_election generates ID when missing."""
        from civic_extraction.clients.google_civic import google_civic_to_election

        raw = {
            "name": "Special Election",
            "electionDay": "2026-06-01"
        }
        result = google_civic_to_election(raw, "san-rafael")
        assert result["id"].startswith("gc-2026-06-01")
        assert result["election_type"] == "special"

    def test_google_civic_to_voter_info(self):
        """Test google_civic_to_voter_info maps correctly."""
        from datetime import date
        from civic_extraction.clients.google_civic import google_civic_to_voter_info

        voter_info = {
            "election": {
                "id": "5000",
                "name": "Primary Election",
                "election_date": date(2026, 3, 3)
            },
            "contests": [
                {
                    "id": "contest-1",
                    "title": "U.S. Senate",
                    "contest_type": "federal_senate",
                    "district_name": "California",
                    "candidates": [{"name": "Candidate A"}]
                }
            ],
            "polling_locations": [
                {"name": "City Hall", "address": "123 Main St"}
            ],
            "normalized_address": {"city": "San Rafael"}
        }
        result = google_civic_to_voter_info(voter_info, "san-rafael")
        assert result["election"]["id"] == "5000"
        assert result["election"]["election_type"] == "primary"
        assert len(result["contests"]) == 1
        assert result["contests"][0]["title"] == "U.S. Senate"
        assert len(result["polling_locations"]) == 1


class TestGoogleCivicClientIntegration:
    """Integration tests that call the real Google Civic API."""

    @pytest.mark.integration
    def test_health_check(self, monkeypatch):
        """Test health check against real API."""
        import os
        api_key = os.environ.get("GOOGLE_CIVIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("No Google Civic API key configured")

        client = GoogleCivicClient("san-rafael", api_key=api_key)
        health = client.health()
        assert health.is_available is True
        assert health.source_id == "google_civic-san-rafael"
        assert health.check_duration_ms > 0

    @pytest.mark.integration
    def test_validate(self):
        """Test validation against real API."""
        import os
        api_key = os.environ.get("GOOGLE_CIVIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("No Google Civic API key configured")

        client = GoogleCivicClient("san-rafael", api_key=api_key)
        result = client.validate()
        assert result.is_valid is True
        assert result.api_reachable is True
        assert result.check_duration_ms > 0

    @pytest.mark.integration
    def test_get_elections(self):
        """Test fetching elections from real API."""
        import os
        api_key = os.environ.get("GOOGLE_CIVIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("No Google Civic API key configured")

        client = GoogleCivicClient("san-rafael", api_key=api_key)
        elections = client.get_elections()
        # API always returns at least the "VIP Test Election" (id=2000)
        assert len(elections) >= 1
        assert all("id" in e for e in elections)
        assert all("name" in e for e in elections)

    @pytest.mark.integration
    def test_get_representatives(self):
        """Test fetching representatives from real API."""
        import os
        api_key = os.environ.get("GOOGLE_CIVIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("No Google Civic API key configured")

        client = GoogleCivicClient("san-rafael", api_key=api_key)
        result = client.get_representatives(address="San Rafael, CA")
        assert result is not None
        assert "officials" in result
        assert len(result["officials"]) > 0
        # Should include some federal, state, and local officials
        assert any("President" in o["seat"] or "Governor" in o["seat"] or "Mayor" in o["seat"]
                   for o in result["officials"])


class TestElectedOfficialsMappers:
    """Test the storage mapper functions for elected officials data."""

    def test_generate_name_variations_basic(self):
        """Test _generate_name_variations with basic name."""
        from civic_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Jane Smith", "City Council Member")
        assert "Jane Smith" in variations
        assert "Smith" in variations
        assert "J. Smith" in variations
        assert "Councilmember Smith" in variations
        assert "Council Member Smith" in variations

    def test_generate_name_variations_mayor(self):
        """Test _generate_name_variations for Mayor."""
        from civic_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Kate Colin", "Mayor")
        assert "Kate Colin" in variations
        assert "Colin" in variations
        assert "K. Colin" in variations
        assert "Mayor Colin" in variations

    def test_generate_name_variations_supervisor(self):
        """Test _generate_name_variations for Supervisor."""
        from civic_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Mary Sackett", "County Supervisor District 1")
        assert "Mary Sackett" in variations
        assert "Sackett" in variations
        assert "M. Sackett" in variations
        assert "Supervisor Sackett" in variations

    def test_generate_name_variations_senator(self):
        """Test _generate_name_variations for Senator."""
        from civic_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Alex Padilla", "US Senator")
        assert "Alex Padilla" in variations
        assert "Padilla" in variations
        assert "A. Padilla" in variations
        assert "Senator Padilla" in variations

    def test_generate_name_variations_single_name(self):
        """Test _generate_name_variations handles single name gracefully."""
        from civic_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Madonna", "Singer")
        assert "Madonna" in variations
        assert len(variations) == 1  # Only full name, no variations possible

    def test_representative_to_elected_official_full(self):
        """Test representative_to_elected_official with complete data."""
        from civic_extraction.clients.representatives import (
            Representative,
            representative_to_elected_official,
        )

        rep = Representative(
            id="local-sr-mayor",
            name="Kate Colin",
            office="Mayor",
            level="local",
            party="Democratic",
            term_start="2024-01-01",
            term_end="2027-12-31",
            source="local",
        )
        result = representative_to_elected_official(rep, "san-rafael")
        assert result["id"] == "local-sr-mayor"
        assert result["name"] == "Kate Colin"
        assert result["seat"] == "Mayor"
        assert result["term_start"] == "2024-01-01"
        assert result["term_end"] == "2027-12-31"
        assert "Mayor Colin" in result["name_variations"]
        assert result["candidate_id"] is None

    def test_representative_to_elected_official_year_only(self):
        """Test representative_to_elected_official with year-only term dates."""
        from civic_extraction.clients.representatives import (
            Representative,
            representative_to_elected_official,
        )

        rep = Representative(
            id="congress-abc123",
            name="Jared Huffman",
            office="US House Representative",
            level="federal",
            party="Democratic",
            term_start="2023",
            term_end="2025",
            source="congress_gov",
        )
        result = representative_to_elected_official(rep, "san-rafael")
        assert result["term_start"] == "2023-01-01"
        assert result["term_end"] == "2025-12-31"

    def test_representative_to_elected_official_no_dates(self):
        """Test representative_to_elected_official with no term dates."""
        from civic_extraction.clients.representatives import (
            Representative,
            representative_to_elected_official,
        )
        from datetime import datetime

        rep = Representative(
            id="openstates-xyz",
            name="Test Person",
            office="State Assembly Member",
            level="state",
            source="open_states",
        )
        result = representative_to_elected_official(rep, "san-rafael")
        # Should use current date for term_start
        assert result["term_start"] == datetime.now().strftime("%Y-%m-%d")
        assert result["term_end"] is None  # Current official

    def test_representative_to_elected_official_council_variations(self):
        """Test that council members get proper name variations."""
        from civic_extraction.clients.representatives import (
            Representative,
            representative_to_elected_official,
        )

        rep = Representative(
            id="local-sr-council-1",
            name="Maribeth Bushey",
            office="City Council Member District 1",
            level="local",
            source="local",
        )
        result = representative_to_elected_official(rep, "san-rafael")
        # Should have both forms of council member title
        assert "Councilmember Bushey" in result["name_variations"]
        assert "Council Member Bushey" in result["name_variations"]
        assert "M. Bushey" in result["name_variations"]


class TestElectedOfficialsStorageIntegration:
    """Integration tests for elected officials storage with SQLite."""

    @pytest.mark.integration
    def test_extract_and_store_local_officials(self, tmp_path):
        """Test extracting local officials and storing in SQLite."""
        from civic_extraction.clients.representatives import (
            RepresentativesClient,
            extract_elected_officials_to_storage,
        )
        from civic.storage import SQLiteBackend

        # Create temporary SQLite database (tables auto-created on first use)
        db_path = tmp_path / "civic_test.db"
        storage = SQLiteBackend(str(db_path))

        # Create client with just local officials (no API keys needed)
        client = RepresentativesClient(jurisdiction_id="san-rafael")

        # Extract local officials only
        count = extract_elected_officials_to_storage(
            client=client,
            storage=storage,
            jurisdiction_id="san-rafael",
            include_federal=False,
            include_state=False,
            include_local=True,
        )

        # Should have stored local officials (Mayor, Council, etc.)
        assert count >= 4, f"Expected at least 4 local officials, got {count}"

        # Retrieve and verify
        officials = storage.get_elected_officials("san-rafael", current_only=True)
        assert len(officials) >= 4

        # Check that Mayor is present
        names = [o["name"] for o in officials]
        assert any("Colin" in name or "Kate" in name for name in names), \
            f"Expected Mayor Kate Colin in officials, got: {names}"

        # Check name variations were stored
        for official in officials:
            assert "name_variations" in official
            assert isinstance(official["name_variations"], list)
            assert len(official["name_variations"]) >= 1

    @pytest.mark.integration
    def test_get_official_by_name(self, tmp_path):
        """Test fuzzy name matching after storing officials."""
        from civic_extraction.clients.representatives import (
            RepresentativesClient,
            extract_elected_officials_to_storage,
        )
        from civic.storage import SQLiteBackend

        # Create temporary SQLite database (tables auto-created on first use)
        db_path = tmp_path / "civic_test.db"
        storage = SQLiteBackend(str(db_path))

        # Create client and extract
        client = RepresentativesClient(jurisdiction_id="san-rafael")
        extract_elected_officials_to_storage(
            client=client,
            storage=storage,
            jurisdiction_id="san-rafael",
            include_federal=False,
            include_state=False,
            include_local=True,
        )

        # Test fuzzy matching on name variations
        # This is important for roll call parsing
        mayor = storage.get_official_by_name("san-rafael", "Mayor Colin")
        if mayor:
            assert "Colin" in mayor["name"]


class TestElectedOfficialsExtraction:
    """Test the extract_elected_officials_to_storage function."""

    def test_extract_elected_officials_empty(self):
        """Test extraction with no representatives."""
        from unittest.mock import Mock
        from civic_extraction.clients.representatives import (
            RepresentativesClient,
            extract_elected_officials_to_storage,
        )

        mock_client = Mock(spec=RepresentativesClient)
        mock_client.get_representatives.return_value = []
        mock_storage = Mock()

        count = extract_elected_officials_to_storage(
            mock_client, mock_storage, "san-rafael"
        )
        assert count == 0
        mock_storage.store_elected_officials.assert_not_called()

    def test_extract_elected_officials_with_data(self):
        """Test extraction stores officials correctly."""
        from unittest.mock import Mock
        from civic_extraction.clients.representatives import (
            Representative,
            RepresentativesClient,
            extract_elected_officials_to_storage,
        )

        mock_client = Mock(spec=RepresentativesClient)
        mock_client.get_representatives.return_value = [
            Representative(
                id="local-sr-mayor",
                name="Kate Colin",
                office="Mayor",
                level="local",
                source="local",
            ),
            Representative(
                id="local-sr-council-1",
                name="Maribeth Bushey",
                office="City Council Member",
                level="local",
                source="local",
            ),
        ]
        mock_storage = Mock()
        mock_storage.store_elected_officials.return_value = 2

        count = extract_elected_officials_to_storage(
            mock_client, mock_storage, "san-rafael"
        )
        assert count == 2
        mock_storage.store_elected_officials.assert_called_once()
        # Check the officials passed to storage
        call_args = mock_storage.store_elected_officials.call_args
        assert call_args[0][0] == "san-rafael"
        officials = call_args[0][1]
        assert len(officials) == 2
        assert officials[0]["name"] == "Kate Colin"
        assert officials[1]["name"] == "Maribeth Bushey"

    def test_extract_elected_officials_level_filtering(self):
        """Test extraction respects level filtering."""
        from unittest.mock import Mock
        from civic_extraction.clients.representatives import (
            RepresentativesClient,
            extract_elected_officials_to_storage,
        )

        mock_client = Mock(spec=RepresentativesClient)
        mock_client.get_representatives.return_value = []
        mock_storage = Mock()

        extract_elected_officials_to_storage(
            mock_client,
            mock_storage,
            "san-rafael",
            include_federal=False,
            include_state=True,
            include_local=True,
        )
        # Check that get_representatives was called with correct filters
        mock_client.get_representatives.assert_called_once_with(
            include_federal=False,
            include_state=True,
            include_local=True,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
