"""
Tests for civic-extraction clients.
"""

import pytest
from datetime import datetime

from civicos_extraction import LegistarClient, CivicClerkClient, ProudCityClient, Meeting
from civicos_extraction import create_san_rafael_client, create_san_rafael_source
from civicos_extraction import ProudCitySource, ExtractionConfig, DataSource, ValidationResult
from civicos_extraction.clients.base import BaseExtractor, Extractor
from civicos_extraction.clients.usaspending import USAspendingClient
from civicos_extraction.clients.cagrants import CaliforniaGrantsClient
from civicos_extraction.clients.marin_registrar import (
    MarinRegistrarClient,
    create_san_rafael_registrar_client,
    marin_election_to_storage,
)
from civicos_extraction.clients.san_rafael_clerk import (
    SanRafaelClerkClient,
    create_san_rafael_clerk_client,
    san_rafael_candidate_to_storage,
    san_rafael_measure_to_storage,
)


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
        from civicos_extraction.pipeline import Pipeline, StageState

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
        from civicos_extraction.pipeline import Pipeline

        assert Pipeline.STAGES == ["discover", "ingest", "store", "index"]

    def test_pipeline_status_method(self):
        """Test Pipeline.status() returns dashboard-consumable dict."""
        from civicos_extraction.pipeline import Pipeline

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
        from civicos_extraction.pipeline import StageStatus, StageState
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
        from civicos_extraction.pipeline import PipelineResult, StageStatus, StageState
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
        from civicos_extraction.pipeline import Pipeline, StageState

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
        from civicos_extraction.pipeline import StageState

        assert StageState.PENDING.value == "pending"
        assert StageState.RUNNING.value == "running"
        assert StageState.COMPLETED.value == "completed"
        assert StageState.FAILED.value == "failed"
        assert StageState.SKIPPED.value == "skipped"


class TestPipelineWithMockSource:
    """Test Pipeline with a mock DataSource for isolated testing."""

    def test_pipeline_run_with_mock_source(self):
        """Test Pipeline.run() executes all stages with mock source."""
        from civicos_extraction.pipeline import Pipeline, StageState
        from civicos_extraction.clients.base import HealthStatus, Meeting
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
        from civicos_extraction.pipeline import Pipeline
        from civicos_extraction.clients.base import HealthStatus, Meeting
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
        from civicos_extraction.pipeline import Pipeline, StageState

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
        from civicos_extraction.pipeline import Pipeline, StageState
        from civicos_extraction.clients.base import HealthStatus, Meeting
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


class TestElectedOfficialsMappers:
    """Test the storage mapper functions for elected officials data."""

    def test_generate_name_variations_basic(self):
        """Test _generate_name_variations with basic name."""
        from civicos_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Jane Smith", "City Council Member")
        assert "Jane Smith" in variations
        assert "Smith" in variations
        assert "J. Smith" in variations
        assert "Councilmember Smith" in variations
        assert "Council Member Smith" in variations

    def test_generate_name_variations_mayor(self):
        """Test _generate_name_variations for Mayor."""
        from civicos_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Kate Colin", "Mayor")
        assert "Kate Colin" in variations
        assert "Colin" in variations
        assert "K. Colin" in variations
        assert "Mayor Colin" in variations

    def test_generate_name_variations_supervisor(self):
        """Test _generate_name_variations for Supervisor."""
        from civicos_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Mary Sackett", "County Supervisor District 1")
        assert "Mary Sackett" in variations
        assert "Sackett" in variations
        assert "M. Sackett" in variations
        assert "Supervisor Sackett" in variations

    def test_generate_name_variations_senator(self):
        """Test _generate_name_variations for Senator."""
        from civicos_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Alex Padilla", "US Senator")
        assert "Alex Padilla" in variations
        assert "Padilla" in variations
        assert "A. Padilla" in variations
        assert "Senator Padilla" in variations

    def test_generate_name_variations_single_name(self):
        """Test _generate_name_variations handles single name gracefully."""
        from civicos_extraction.clients.representatives import _generate_name_variations

        variations = _generate_name_variations("Madonna", "Singer")
        assert "Madonna" in variations
        assert len(variations) == 1  # Only full name, no variations possible

    def test_representative_to_elected_official_full(self):
        """Test representative_to_elected_official with complete data."""
        from civicos_extraction.clients.representatives import (
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
        from civicos_extraction.clients.representatives import (
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
        from civicos_extraction.clients.representatives import (
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
        from civicos_extraction.clients.representatives import (
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
        from civicos_extraction.clients.representatives import (
            RepresentativesClient,
            extract_elected_officials_to_storage,
        )
        from civicos.storage import SQLiteBackend

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
        from civicos_extraction.clients.representatives import (
            RepresentativesClient,
            extract_elected_officials_to_storage,
        )
        from civicos.storage import SQLiteBackend

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
        from civicos_extraction.clients.representatives import (
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
        from civicos_extraction.clients.representatives import (
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
        from civicos_extraction.clients.representatives import (
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


class TestMarinRegistrarClient:
    """Test MarinRegistrarClient for Marin County election data."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = MarinRegistrarClient("san-rafael")
        assert client.jurisdiction_id == "san-rafael"
        assert client.platform_name == "marin_registrar"
        assert client.source_id == "marin_registrar-san-rafael"
        assert client.headless is True
        assert client.request_delay == 2.0

    def test_client_custom_settings(self):
        """Test client with custom settings."""
        client = MarinRegistrarClient(
            "san-rafael",
            headless=False,
            request_delay=1.0
        )
        assert client.headless is False
        assert client.request_delay == 1.0

    def test_create_san_rafael_factory(self):
        """Test convenience factory creates correct client."""
        client = create_san_rafael_registrar_client()
        assert client.jurisdiction_id == "san-rafael"
        assert client.platform_name == "marin_registrar"

    def test_parse_election_schedule_june_primary(self):
        """Test _parse_election_schedule parses June primary correctly."""
        client = MarinRegistrarClient("san-rafael")
        text = """
        June 2, 2026 - Statewide Direct Primary Election
        Go to the June 2, 2026 Statewide Direct Primary Election page for details
        """
        elections = client._parse_election_schedule(text)
        assert len(elections) >= 1
        june_election = [e for e in elections if "2026-06-02" in e["election_date"]]
        assert len(june_election) == 1
        assert june_election[0]["election_type"] == "primary"
        assert "marin-2026-06-02" in june_election[0]["id"]

    def test_parse_election_schedule_november_general(self):
        """Test _parse_election_schedule parses November general correctly."""
        client = MarinRegistrarClient("san-rafael")
        text = """
        November 3, 2026 - General Election
        The Guide for Candidates will be available approximately mid-June 2026.
        """
        elections = client._parse_election_schedule(text)
        assert len(elections) >= 1
        nov_election = [e for e in elections if "2026-11-03" in e["election_date"]]
        assert len(nov_election) == 1
        assert nov_election[0]["election_type"] == "general"

    def test_parse_election_schedule_special(self):
        """Test _parse_election_schedule parses special elections correctly."""
        client = MarinRegistrarClient("san-rafael")
        text = """
        April 14, 2026 - Special Election
        (no election is scheduled at this time)
        """
        elections = client._parse_election_schedule(text)
        assert len(elections) >= 1
        april_election = [e for e in elections if "2026-04-14" in e["election_date"]]
        assert len(april_election) == 1
        assert april_election[0]["election_type"] == "special"
        assert april_election[0]["status"] == "possible"

    def test_parse_election_schedule_skips_past(self):
        """Test _parse_election_schedule skips past elections."""
        client = MarinRegistrarClient("san-rafael")
        text = """
        January 1, 2020 - Old Election
        November 3, 2026 - General Election
        """
        elections = client._parse_election_schedule(text)
        # Should not include the 2020 election
        assert all("2020" not in e["election_date"] for e in elections)

    def test_parse_election_schedule_deduplicates(self):
        """Test _parse_election_schedule deduplicates elections."""
        client = MarinRegistrarClient("san-rafael")
        text = """
        November 3, 2026 - General Election
        November 3, 2026 - General Election page for details
        """
        elections = client._parse_election_schedule(text)
        nov_elections = [e for e in elections if "2026-11-03" in e["election_date"]]
        assert len(nov_elections) == 1

    def test_marin_election_to_storage(self):
        """Test marin_election_to_storage maps fields correctly."""
        election = {
            "id": "marin-2026-06-02",
            "name": "Statewide Direct Primary Election",
            "election_date": "2026-06-02",
            "election_type": "primary",
            "status": "scheduled",
            "source_url": "https://www.marincounty.gov/departments/elections/election-schedule",
        }
        result = marin_election_to_storage(election, "san-rafael")
        assert result["id"] == "marin-2026-06-02"
        assert result["name"] == "Statewide Direct Primary Election"
        assert result["election_date"] == "2026-06-02"
        assert result["election_type"] == "primary"
        assert result["source"] == "marin_registrar"
        assert "raw_data" in result


class TestMarinRegistrarClientIntegration:
    """Integration tests that scrape the real Marin County website."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_health_check(self):
        """Test health check against real website."""
        client = MarinRegistrarClient("san-rafael")
        health = client.health()
        # May be available or blocked by Cloudflare
        assert health.source_id == "marin_registrar-san-rafael"
        assert health.check_duration_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_validate(self):
        """Test validation checks."""
        client = MarinRegistrarClient("san-rafael")
        result = client.validate()
        assert result.config_valid is True  # Playwright should be installed
        assert result.check_duration_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_election_schedule(self):
        """Test fetching election schedule from real website."""
        client = MarinRegistrarClient("san-rafael")
        elections = client.get_election_schedule()
        # Should find at least some elections (may be blocked by Cloudflare)
        if len(elections) > 0:
            assert all("election_date" in e for e in elections)
            assert all("election_type" in e for e in elections)
            assert all("source" in e for e in elections)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_elections_filters_to_scheduled(self):
        """Test get_elections only returns scheduled elections."""
        client = MarinRegistrarClient("san-rafael")
        elections = client.get_elections()
        if len(elections) > 0:
            assert all(e.get("status") == "scheduled" for e in elections)


class TestSanRafaelClerkClient:
    """Test SanRafaelClerkClient for city election data."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = SanRafaelClerkClient()
        assert client.jurisdiction_id == "city-san-rafael"
        assert client.platform_name == "san_rafael_clerk"
        assert client.source_id == "san_rafael_clerk-city-san-rafael"
        assert client.headless is True
        assert client.request_delay == 2.0

    def test_client_custom_settings(self):
        """Test client with custom settings."""
        client = SanRafaelClerkClient(headless=False, request_delay=1.0)
        assert client.headless is False
        assert client.request_delay == 1.0

    def test_create_factory(self):
        """Test convenience factory creates correct client."""
        client = create_san_rafael_clerk_client()
        assert client.jurisdiction_id == "city-san-rafael"
        assert client.platform_name == "san_rafael_clerk"

    def test_district_schedule(self):
        """Test district election schedule constants."""
        assert SanRafaelClerkClient.DISTRICT_SCHEDULE[2024] == ["D1", "D4", "Mayor"]
        assert SanRafaelClerkClient.DISTRICT_SCHEDULE[2026] == ["D2", "D3"]
        assert SanRafaelClerkClient.DISTRICT_SCHEDULE[2028] == ["D1", "D4", "Mayor"]

    def test_get_upcoming_races_2026(self):
        """Test upcoming races for 2026 midterm."""
        client = SanRafaelClerkClient()
        races = client.get_upcoming_races(2026)
        assert len(races) == 2
        offices = [r["office"] for r in races]
        assert "Council District 2" in offices
        assert "Council District 3" in offices
        assert all(r["election_year"] == 2026 for r in races)

    def test_get_upcoming_races_2028(self):
        """Test upcoming races for 2028 presidential year."""
        client = SanRafaelClerkClient()
        races = client.get_upcoming_races(2028)
        assert len(races) == 3
        offices = [r["office"] for r in races]
        assert "Council District 1" in offices
        assert "Council District 4" in offices
        assert "Mayor" in offices

    def test_parse_candidates(self):
        """Test _parse_candidates extracts candidates correctly."""
        client = SanRafaelClerkClient()
        text = """
        Mayoral Candidates

        Kate Colin
        Statement of Qualifications
        Campaign Finance Documents

        Mahmoud Shirazi
        Statement of Qualifications
        Campaign Finance Documents

        Councilmember District 4 Candidates

        Rachel Kertz
        Statement of Qualifications
        """
        candidates = client._parse_candidates(text)
        assert len(candidates) >= 2
        names = [c["name"] for c in candidates]
        assert "Kate Colin" in names or "Mahmoud Shirazi" in names

    def test_parse_measures(self):
        """Test _parse_measures extracts measures correctly."""
        client = SanRafaelClerkClient()
        text = """
        Measure P

        "Shall the measure, to levy an annual special parcel tax..."

        San Rafael voters approved Measure P.
        """
        measures = client._parse_measures(text)
        assert len(measures) >= 1
        assert measures[0]["letter"] == "P"
        assert measures[0]["passed"] is True

    def test_parse_measures_deduplicates(self):
        """Test _parse_measures deduplicates measures."""
        client = SanRafaelClerkClient()
        text = """
        Measure P information
        More about Measure P
        Measure P passed
        """
        measures = client._parse_measures(text)
        assert len(measures) == 1
        assert measures[0]["letter"] == "P"

    def test_san_rafael_candidate_to_storage(self):
        """Test candidate storage mapping."""
        candidate = {
            "name": "Kate Colin",
            "office": "Mayor",
            "source": "san_rafael_clerk",
        }
        result = san_rafael_candidate_to_storage(candidate, "2024-11-05")
        assert "kate-colin" in result["id"]
        assert result["name"] == "Kate Colin"
        assert result["office"] == "Mayor"
        assert result["source"] == "san_rafael_clerk"

    def test_san_rafael_measure_to_storage(self):
        """Test measure storage mapping."""
        measure = {
            "letter": "P",
            "title": "Library and Community Center Tax",
            "passed": True,
            "source": "san_rafael_clerk",
        }
        result = san_rafael_measure_to_storage(measure, "2024-11-05")
        assert "measure-p" in result["id"]
        assert result["letter"] == "P"
        assert result["passed"] is True
        assert result["source"] == "san_rafael_clerk"


class TestSanRafaelClerkClientIntegration:
    """Integration tests that scrape the real San Rafael City Clerk website."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_health_check(self):
        """Test health check against real website."""
        client = SanRafaelClerkClient()
        health = client.health()
        assert health.source_id == "san_rafael_clerk-city-san-rafael"
        assert health.check_duration_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_validate(self):
        """Test validation checks."""
        client = SanRafaelClerkClient()
        result = client.validate()
        assert result.config_valid is True
        assert result.check_duration_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_past_elections(self):
        """Test fetching past elections."""
        client = SanRafaelClerkClient()
        elections = client.get_past_elections()
        if len(elections) > 0:
            assert all("election_date" in e for e in elections)
            assert all("url" in e for e in elections)
            assert all("source" in e for e in elections)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_election_details(self):
        """Test fetching election details."""
        client = SanRafaelClerkClient()
        elections = client.get_past_elections()
        if len(elections) > 0:
            details = client.get_election_details(elections[0]["url"])
            if details:
                assert "candidates" in details
                assert "measures" in details
                assert "url" in details


class TestSimbliClient:
    """Test SimbliClient for school board meeting data."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient(
            board_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            jurisdiction_id="srcs",
        )
        assert client.jurisdiction_id == "srcs"
        assert client.platform_name == "simbli"
        assert client.source_id == "simbli-srcs"
        assert client.headless is True
        assert client.request_delay == 2.0
        assert client.base_url == "https://simbli.eboardsolutions.com"

    def test_client_custom_settings(self):
        """Test client with custom headless and delay settings."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient(
            board_url="https://test.simbli.com/index.php",
            jurisdiction_id="test",
            headless=False,
            request_delay=5.0,
        )
        assert client.headless is False
        assert client.request_delay == 5.0

    def test_infer_meeting_type_regular(self):
        """Test meeting type inference for regular meetings."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://test.simbli.com", "test")
        assert client._infer_meeting_type("Regular Board Meeting") == "regular"
        assert client._infer_meeting_type("Board Meeting") == "regular"

    def test_infer_meeting_type_special(self):
        """Test meeting type inference for special meetings."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://test.simbli.com", "test")
        assert client._infer_meeting_type("Special Board Meeting") == "special"
        assert client._infer_meeting_type("Special Session") == "special"

    def test_infer_meeting_type_study_session(self):
        """Test meeting type inference for study sessions."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://test.simbli.com", "test")
        assert client._infer_meeting_type("Study Session") == "study_session"
        assert client._infer_meeting_type("Board Workshop") == "study_session"

    def test_infer_meeting_type_closed(self):
        """Test meeting type inference for closed sessions."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://test.simbli.com", "test")
        assert client._infer_meeting_type("Closed Session") == "closed_session"
        assert client._infer_meeting_type("Executive Session") == "closed_session"

    def test_generate_meeting_title(self):
        """Test meeting title generation."""
        from civicos_extraction.clients.simbli import SimbliClient
        from datetime import date

        client = SimbliClient("https://test.simbli.com", "test")

        title = client._generate_meeting_title("regular", date(2026, 1, 15))
        assert title == "Regular Board Meeting - January 15, 2026"

        title = client._generate_meeting_title("special", date(2026, 2, 20))
        assert title == "Special Board Meeting - February 20, 2026"

    def test_make_absolute_url_already_absolute(self):
        """Test URL handling for already absolute URLs."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://srcs.simbli.com/index.php", "srcs")
        url = client._make_absolute_url("https://example.com/doc.pdf")
        assert url == "https://example.com/doc.pdf"

    def test_make_absolute_url_relative_with_slash(self):
        """Test URL handling for relative URLs starting with /."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://srcs.simbli.com/index.php", "srcs")
        url = client._make_absolute_url("/docs/agenda.pdf")
        assert url == "https://srcs.simbli.com/docs/agenda.pdf"

    def test_make_absolute_url_relative_without_slash(self):
        """Test URL handling for relative URLs without leading /."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://srcs.simbli.com/index.php", "srcs")
        url = client._make_absolute_url("docs/agenda.pdf")
        assert url == "https://srcs.simbli.com/docs/agenda.pdf"

    def test_find_pdf_link_agenda(self):
        """Test finding agenda PDF links in HTML."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://srcs.simbli.com", "srcs")
        html = '''
        <a href="/docs/agenda_2026_01.pdf">View Agenda</a>
        <a href="/docs/minutes_2026_01.pdf">View Minutes</a>
        '''
        agenda_url = client._find_pdf_link(html, ["agenda", "agnd"])
        assert agenda_url == "https://srcs.simbli.com/docs/agenda_2026_01.pdf"

    def test_find_pdf_link_minutes(self):
        """Test finding minutes PDF links in HTML."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://srcs.simbli.com", "srcs")
        html = '''
        <a href="/docs/agenda_2026_01.pdf">View Agenda</a>
        <a href="/docs/minutes_2026_01.pdf">View Minutes</a>
        '''
        minutes_url = client._find_pdf_link(html, ["minutes", "min"])
        assert minutes_url == "https://srcs.simbli.com/docs/minutes_2026_01.pdf"

    def test_find_pdf_link_not_found(self):
        """Test when no matching PDF link is found."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient("https://srcs.simbli.com", "srcs")
        html = '<a href="/docs/report.pdf">View Report</a>'
        agenda_url = client._find_pdf_link(html, ["agenda", "agnd"])
        assert agenda_url is None

    def test_parse_table_meetings(self):
        """Test parsing meetings from HTML table rows."""
        from civicos_extraction.clients.simbli import SimbliClient
        from datetime import date

        client = SimbliClient("https://srcs.simbli.com", "srcs")

        html = '''
        <table>
        <tr>
            <td>January 15, 2026</td>
            <td>Regular Board Meeting</td>
            <td><a href="/docs/agenda_2026_01.pdf">Agenda</a></td>
        </tr>
        <tr>
            <td>February 19, 2026</td>
            <td>Special Board Meeting</td>
            <td><a href="/docs/agenda_2026_02.pdf">Agenda</a></td>
        </tr>
        </table>
        '''

        meetings = client._parse_table_meetings(html, date(2026, 1, 1), limit=10)

        assert len(meetings) == 2

        assert meetings[0].id == "srcs-2026-01-15"
        assert meetings[0].meeting_type == "regular"
        assert meetings[0].agenda_url == "https://srcs.simbli.com/docs/agenda_2026_01.pdf"

        assert meetings[1].id == "srcs-2026-02-19"
        assert meetings[1].meeting_type == "special"

    def test_parse_table_meetings_filters_old_dates(self):
        """Test that old meetings are filtered out."""
        from civicos_extraction.clients.simbli import SimbliClient
        from datetime import date

        client = SimbliClient("https://srcs.simbli.com", "srcs")

        html = '''
        <table>
        <tr><td>January 15, 2024</td><td>Old Meeting</td></tr>
        <tr><td>January 15, 2026</td><td>New Meeting</td></tr>
        </table>
        '''

        meetings = client._parse_table_meetings(html, date(2025, 1, 1), limit=10)

        # Only the 2026 meeting should be returned
        assert len(meetings) == 1
        assert meetings[0].id == "srcs-2026-01-15"


class TestSimbliMeeting:
    """Test SimbliMeeting dataclass."""

    def test_simbli_meeting_creation(self):
        """Test basic SimbliMeeting creation."""
        from civicos_extraction.clients.simbli import SimbliMeeting
        from datetime import datetime

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
            agenda_url="https://example.com/agenda.pdf",
        )
        assert meeting.id == "srcs-2026-01-15"
        assert meeting.title == "Regular Board Meeting"
        assert meeting.meeting_type == "regular"
        assert meeting.agenda_url == "https://example.com/agenda.pdf"

    def test_simbli_meeting_with_mid(self):
        """Test SimbliMeeting with simbli_mid field."""
        from civicos_extraction.clients.simbli import SimbliMeeting
        from datetime import datetime

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
            simbli_mid="45989",
        )
        assert meeting.simbli_mid == "45989"

    def test_simbli_meeting_mid_defaults_to_none(self):
        """Test simbli_mid defaults to None when not provided."""
        from civicos_extraction.clients.simbli import SimbliMeeting
        from datetime import datetime

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
        )
        assert meeting.simbli_mid is None

    def test_simbli_meeting_to_meeting(self):
        """Test converting SimbliMeeting to standard Meeting format."""
        from civicos_extraction.clients.simbli import SimbliMeeting
        from datetime import datetime

        simbli_meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting - January 15, 2026",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
            agenda_url="https://example.com/agenda.pdf",
            minutes_url="https://example.com/minutes.pdf",
            source_url="https://srcs.simbli.com/index.php",
        )

        meeting = simbli_meeting.to_meeting("srcs")

        assert meeting.id == "srcs-2026-01-15"
        assert meeting.title == "Regular Board Meeting - January 15, 2026"
        assert meeting.jurisdiction_id == "srcs"
        assert meeting.meeting_type == "regular"
        assert meeting.source_platform == "simbli"
        assert meeting.agenda_url == "https://example.com/agenda.pdf"
        assert meeting.minutes_url == "https://example.com/minutes.pdf"


class TestSimbliStorageMappers:
    """Test Simbli storage mapper functions."""

    def test_simbli_meeting_to_storage(self):
        """Test storage mapping for Simbli meetings."""
        from civicos_extraction.clients.simbli import SimbliMeeting, simbli_meeting_to_storage
        from datetime import datetime

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
            agenda_url="https://example.com/agenda.pdf",
            source_url="https://srcs.simbli.com",
        )

        result = simbli_meeting_to_storage(meeting, "srcs")

        assert result["id"] == "srcs-2026-01-15"
        assert result["title"] == "Regular Board Meeting"
        assert result["jurisdiction_id"] == "srcs"
        assert result["meeting_type"] == "regular"
        assert result["source_platform"] == "simbli"
        assert result["agenda_url"] == "https://example.com/agenda.pdf"
        assert "2026-01-15" in result["meeting_datetime"]

    def test_simbli_meeting_to_storage_with_mid(self):
        """Test storage mapping includes simbli_mid in raw_data."""
        from civicos_extraction.clients.simbli import SimbliMeeting, simbli_meeting_to_storage
        from datetime import datetime

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
            simbli_mid="45989",
        )

        result = simbli_meeting_to_storage(meeting, "srcs")

        assert result["raw_data"] is not None
        assert result["raw_data"]["simbli_mid"] == "45989"

    def test_simbli_meeting_to_storage_no_mid(self):
        """Test storage mapping without simbli_mid has no raw_data."""
        from civicos_extraction.clients.simbli import SimbliMeeting, simbli_meeting_to_storage
        from datetime import datetime

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
        )

        result = simbli_meeting_to_storage(meeting, "srcs")

        assert result["raw_data"] is None


class TestCreateSrcsSimbliClient:
    """Test SRCS Simbli client factory."""

    def test_create_srcs_simbli_client(self):
        """Test factory function creates correctly configured client."""
        from civicos_extraction.clients.simbli import create_srcs_simbli_client

        client = create_srcs_simbli_client()
        assert client.jurisdiction_id == "srcs"
        assert "simbli.eboardsolutions.com" in client.board_url
        assert "S=36030430" in client.board_url  # SRCS district ID
        assert client.headless is True

    def test_create_srcs_simbli_client_headless_option(self):
        """Test factory function respects headless option."""
        from civicos_extraction.clients.simbli import create_srcs_simbli_client

        client = create_srcs_simbli_client(headless=False)
        assert client.headless is False


class TestSimbliClientValidation:
    """Test SimbliClient validation."""

    def test_validate_requires_valid_url(self):
        """Test validation fails for invalid URL."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient(
            board_url="not-a-url",
            jurisdiction_id="test",
        )
        result = client.validate()
        assert result.is_valid is False
        assert result.config_valid is False
        assert any("Invalid board_url" in err for err in result.errors)


class TestSimbliPdfDownload:
    """Test Simbli PDF download functionality (unit tests)."""

    def test_get_agenda_pdf_with_direct_url_only(self):
        """Test get_agenda_pdf when only agenda_url is available."""
        from civicos_extraction.clients.simbli import SimbliClient, SimbliMeeting
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        client = SimbliClient(
            board_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            jurisdiction_id="srcs",
        )

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
            agenda_url="https://example.com/agenda.pdf",
        )

        # Mock _download_pdf to return fake PDF bytes
        with patch.object(client, "_download_pdf", return_value=b"%PDF-1.4 test content") as mock_download:
            result = client.get_agenda_pdf(meeting)
            assert result == b"%PDF-1.4 test content"
            mock_download.assert_called_once_with("https://example.com/agenda.pdf")

    def test_get_agenda_pdf_falls_back_to_mid(self):
        """Test get_agenda_pdf falls back to MID-based download when URL fails."""
        from civicos_extraction.clients.simbli import SimbliClient, SimbliMeeting
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        client = SimbliClient(
            board_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            jurisdiction_id="srcs",
        )

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
            agenda_url="https://example.com/agenda.pdf",
            simbli_mid="45989",
        )

        # Mock _download_pdf to return None (fail) and download_agenda_pdf_via_mid to succeed
        with patch.object(client, "_download_pdf", return_value=None), \
             patch.object(client, "download_agenda_pdf_via_mid", return_value=b"%PDF-1.4 mid content") as mock_mid:
            result = client.get_agenda_pdf(meeting)
            assert result == b"%PDF-1.4 mid content"
            mock_mid.assert_called_once_with("45989")

    def test_get_agenda_pdf_with_mid_only(self):
        """Test get_agenda_pdf when only simbli_mid is available."""
        from civicos_extraction.clients.simbli import SimbliClient, SimbliMeeting
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        client = SimbliClient(
            board_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            jurisdiction_id="srcs",
        )

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
            simbli_mid="45989",
        )

        with patch.object(client, "download_agenda_pdf_via_mid", return_value=b"%PDF-1.4 mid content") as mock_mid:
            result = client.get_agenda_pdf(meeting)
            assert result == b"%PDF-1.4 mid content"
            mock_mid.assert_called_once_with("45989")

    def test_get_agenda_pdf_returns_none_when_no_url_or_mid(self):
        """Test get_agenda_pdf returns None when neither URL nor MID is available."""
        from civicos_extraction.clients.simbli import SimbliClient, SimbliMeeting
        from datetime import datetime

        client = SimbliClient(
            board_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            jurisdiction_id="srcs",
        )

        meeting = SimbliMeeting(
            id="srcs-2026-01-15",
            title="Regular Board Meeting",
            meeting_datetime=datetime(2026, 1, 15, 18, 0),
            meeting_type="regular",
        )

        result = client.get_agenda_pdf(meeting)
        assert result is None

    def test_download_agenda_pdf_via_mid_returns_none_for_empty_mid(self):
        """Test download_agenda_pdf_via_mid returns None for empty MID."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient(
            board_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            jurisdiction_id="srcs",
        )

        result = client.download_agenda_pdf_via_mid("")
        assert result is None

        result = client.download_agenda_pdf_via_mid(None)
        assert result is None

    def test_download_pdf_from_url_makes_absolute(self):
        """Test _download_pdf_from_url handles relative URLs."""
        from civicos_extraction.clients.simbli import SimbliClient
        from unittest.mock import MagicMock, PropertyMock

        client = SimbliClient(
            board_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            jurisdiction_id="srcs",
        )

        # Mock the browser page with a successful response
        mock_page = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.body.return_value = b"%PDF-1.4 test"
        mock_page.request.get.return_value = mock_response

        client._page = mock_page

        result = client._download_pdf_from_url("/SB_Meetings/test.pdf")

        # Should have made the URL absolute
        mock_page.request.get.assert_called_once()
        call_args = mock_page.request.get.call_args[0][0]
        assert call_args == "https://simbli.eboardsolutions.com/SB_Meetings/test.pdf"
        assert result == b"%PDF-1.4 test"


class TestSimbliClientIntegration:
    """Integration tests that scrape the real SRCS Simbli site."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_health_check(self):
        """Test health check against real Simbli website."""
        from civicos_extraction.clients.simbli import create_srcs_simbli_client

        client = create_srcs_simbli_client()
        health = client.health()
        assert health.source_id == "simbli-srcs"
        assert health.check_duration_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_validate(self):
        """Test validation against real Simbli website."""
        from civicos_extraction.clients.simbli import create_srcs_simbli_client

        client = create_srcs_simbli_client()
        result = client.validate()
        assert result.config_valid is True
        assert result.check_duration_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_meetings(self):
        """Test fetching meetings from real Simbli website."""
        from civicos_extraction.clients.simbli import create_srcs_simbli_client
        from datetime import date

        client = create_srcs_simbli_client()
        meetings = client.get_meetings(since=date(2024, 1, 1), limit=10)

        # May return 0 meetings if WAF blocks, which is acceptable for health check
        if len(meetings) > 0:
            assert all(m.id.startswith("srcs-") for m in meetings)
            assert all(m.meeting_type in ["regular", "special", "study_session", "closed_session", "reorganization", "emergency"] for m in meetings)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_meetings_discovers_mids(self):
        """Test that MID discovery populates simbli_mid field."""
        from civicos_extraction.clients.simbli import create_srcs_simbli_client
        from datetime import date

        client = create_srcs_simbli_client()
        meetings = client.get_meetings(since=date(2024, 1, 1), limit=5)

        # If we got meetings, at least some should have MIDs discovered
        if len(meetings) > 0:
            mids_found = [m for m in meetings if m.simbli_mid is not None]
            # Log results for debugging
            print(f"Found {len(mids_found)}/{len(meetings)} meetings with MIDs")
            for m in mids_found:
                print(f"  - {m.id}: MID={m.simbli_mid}")

            # At least one meeting should have an MID discovered
            # (may not be all due to timing/JS loading issues)
            assert len(mids_found) >= 1, "Expected at least one meeting to have simbli_mid populated"

            # Verify MIDs are valid numeric strings
            for m in mids_found:
                assert m.simbli_mid.isdigit(), f"Expected numeric MID, got: {m.simbli_mid}"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_download_agenda_pdf_via_mid(self):
        """Test downloading an agenda PDF using the MID workflow."""
        from civicos_extraction.clients.simbli import create_srcs_simbli_client
        from datetime import date

        client = create_srcs_simbli_client()

        # First get meetings to find one with an MID
        meetings = client.get_meetings(since=date(2024, 1, 1), limit=5)
        meetings_with_mid = [m for m in meetings if m.simbli_mid is not None]

        if len(meetings_with_mid) == 0:
            pytest.skip("No meetings with MIDs found - cannot test PDF download")

        # Try to download the agenda PDF for the first meeting with MID
        meeting = meetings_with_mid[0]
        print(f"Attempting to download agenda for {meeting.id} (MID={meeting.simbli_mid})")

        with client:  # Use context manager for browser lifecycle
            pdf_bytes = client.download_agenda_pdf_via_mid(meeting.simbli_mid)

        if pdf_bytes is None:
            # PDF download may fail if the agenda isn't available yet
            # This is acceptable for newer meetings
            print(f"PDF download returned None for MID {meeting.simbli_mid}")
            pytest.skip("PDF not available for this meeting")

        # Verify we got valid PDF bytes
        assert len(pdf_bytes) > 1000, f"PDF seems too small: {len(pdf_bytes)} bytes"
        assert pdf_bytes[:4] == b"%PDF", f"Content doesn't look like a PDF: {pdf_bytes[:20]}"
        print(f"Successfully downloaded {len(pdf_bytes)} bytes of PDF for {meeting.id}")


class TestSAMAssistanceClient:
    """Test SAMAssistanceClient for federal program definitions."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        assert client.jurisdiction_id == "federal-US"
        assert client.platform_name == "sam_assistance"
        assert client.source_id == "sam_assistance-federal-US"

    def test_client_custom_cache_dir(self):
        """Test client initialization with custom cache dir."""
        import tempfile
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = SAMAssistanceClient(cache_dir=tmpdir)
            assert client.cache_dir == tmpdir

    def test_agency_abbreviation_mappings(self):
        """Test agency abbreviation extraction."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()

        # Test common agency mappings
        assert client._get_agency_abbrev("DEPARTMENT OF HOUSING AND URBAN DEVELOPMENT") == "HUD"
        assert client._get_agency_abbrev("ENVIRONMENTAL PROTECTION AGENCY") == "EPA"
        assert client._get_agency_abbrev("DEPARTMENT OF TRANSPORTATION") == "DOT"
        # Sub-agencies like FTA are mapped to parent department DOT
        # (SAM CSV format lists sub-agency first, then parent)
        assert client._get_agency_abbrev("FEDERAL TRANSIT ADMINISTRATION, DEPARTMENT OF TRANSPORTATION") == "FTA"
        # Direct FTA reference
        assert client._get_agency_abbrev("FEDERAL TRANSIT ADMINISTRATION") == "FTA"

    def test_infer_topic_from_aln(self):
        """Test topic inference from ALN prefix."""
        from civicos_extraction.clients.sam_assistance import (
            infer_topic,
            AssistanceListing,
        )

        # Housing (HUD - prefix 14)
        housing_listing = AssistanceListing(
            aln="14.218",
            program_name="CDBG",
            agency="HUD",
            agency_abbrev="HUD",
            objectives="",
            assistance_types="",
            uses_restrictions="",
            applicant_eligibility="",
            beneficiary_eligibility="",
            website="",
            sam_url="",
        )
        assert infer_topic(housing_listing) == "housing"

        # Transportation (DOT - prefix 20)
        transport_listing = AssistanceListing(
            aln="20.507",
            program_name="Urbanized Area Formula",
            agency="DOT",
            agency_abbrev="DOT",
            objectives="",
            assistance_types="",
            uses_restrictions="",
            applicant_eligibility="",
            beneficiary_eligibility="",
            website="",
            sam_url="",
        )
        assert infer_topic(transport_listing) == "transportation"

    def test_extract_keywords(self):
        """Test keyword extraction from listing."""
        from civicos_extraction.clients.sam_assistance import (
            extract_keywords,
            AssistanceListing,
        )

        listing = AssistanceListing(
            aln="14.218",
            program_name="Community Development Block Grant",
            popular_name="CDBG",
            agency="HUD",
            agency_abbrev="HUD",
            objectives="Develop viable urban communities",
            assistance_types="",
            uses_restrictions="",
            applicant_eligibility="",
            beneficiary_eligibility="",
            website="",
            sam_url="",
        )

        keywords = extract_keywords(listing)
        assert "community" in keywords
        assert "development" in keywords
        assert "block" in keywords
        assert "grant" in keywords
        assert "hud" in keywords
        # Common stopwords should be filtered out
        assert "the" not in keywords
        assert "of" not in keywords

    def test_sam_program_to_storage(self):
        """Test conversion to storage format."""
        from civicos_extraction.clients.sam_assistance import (
            sam_program_to_storage,
            AssistanceListing,
        )

        listing = AssistanceListing(
            aln="14.218",
            program_name="Community Development Block Grant",
            popular_name="CDBG",
            agency="DEPARTMENT OF HOUSING AND URBAN DEVELOPMENT",
            agency_abbrev="HUD",
            objectives="Develop viable urban communities through housing and economic development.",
            assistance_types="Formula Grants",
            uses_restrictions="Eligible activities include housing rehabilitation; public facilities improvements.",
            applicant_eligibility="States, metropolitan cities, urban counties.",
            beneficiary_eligibility="Low and moderate income persons.",
            website="https://www.hud.gov/cdbg",
            sam_url="https://sam.gov/fal/abc123",
            published_date="Jan 01, 2024",
        )

        storage = sam_program_to_storage(listing)

        assert storage["program_id"] == "sam_14_218"
        assert storage["program_name"] == "Community Development Block Grant"
        assert storage["administering_agency"] == "HUD"
        assert storage["cfda_number"] == "14.218"
        assert storage["topic"] == "housing"
        assert storage["official_url"] == "https://www.hud.gov/cdbg"
        assert "keywords" in storage
        assert "source" in storage
        assert storage["source"] == "sam_assistance_listings"
        # Check eligible activities extracted
        assert len(storage["eligible_activities"]) > 0

    def test_assistance_listing_to_dict(self):
        """Test AssistanceListing serialization."""
        from civicos_extraction.clients.sam_assistance import AssistanceListing

        listing = AssistanceListing(
            aln="14.218",
            program_name="CDBG",
            agency="HUD",
            agency_abbrev="HUD",
            objectives="Test objectives",
            assistance_types="Grants",
            uses_restrictions="Test uses",
            applicant_eligibility="Test applicant",
            beneficiary_eligibility="Test beneficiary",
            website="https://test.gov",
            sam_url="https://sam.gov/test",
        )

        d = listing.to_dict()
        assert d["aln"] == "14.218"
        assert d["program_name"] == "CDBG"
        assert d["agency_abbrev"] == "HUD"


class TestSAMAssistanceClientIntegration:
    """Integration tests that call the real SAM.gov data."""

    @pytest.mark.integration
    def test_health_check(self):
        """Test health check against real SAM.gov."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        health = client.health()
        assert health.is_available is True
        assert health.source_id == "sam_assistance-federal-US"
        assert health.check_duration_ms > 0

    @pytest.mark.integration
    def test_validate(self):
        """Test validation against real SAM.gov."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        result = client.validate()
        assert result.is_valid is True
        assert result.api_reachable is True
        assert result.check_duration_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_program_cdbg(self):
        """Test fetching CDBG program by ALN."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        cdbg = client.get_program("14.218")

        assert cdbg is not None
        assert cdbg.aln == "14.218"
        assert "Community Development Block Grant" in cdbg.program_name
        assert cdbg.agency_abbrev == "HUD"
        assert len(cdbg.objectives) > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_programs_by_agency(self):
        """Test searching programs by agency."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        hud_programs = client.search_programs(agency="HUD", limit=10)

        assert len(hud_programs) > 0
        for program in hud_programs:
            assert program.agency_abbrev == "HUD"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_programs_by_keyword(self):
        """Test searching programs by keyword."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        housing_programs = client.search_programs(keyword="housing", limit=10)

        assert len(housing_programs) > 0
        # At least one should have "housing" in name or objectives
        found_housing = False
        for program in housing_programs:
            if "housing" in program.program_name.lower() or "housing" in program.objectives.lower():
                found_housing = True
                break
        assert found_housing, "Expected at least one program with 'housing' in name or objectives"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_programs_by_aln_prefix(self):
        """Test searching programs by ALN prefix."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        # ALN prefix 14 = HUD
        hud_programs = client.search_programs(aln_prefix="14", limit=10)

        assert len(hud_programs) > 0
        for program in hud_programs:
            assert program.aln.startswith("14")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_program_count(self):
        """Test getting total program count."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        count = client.get_program_count()

        # Should have thousands of programs
        assert count > 1000

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_available_agencies(self):
        """Test getting agency list with counts."""
        from civicos_extraction.clients.sam_assistance import SAMAssistanceClient

        client = SAMAssistanceClient()
        agencies = client.get_available_agencies()

        assert len(agencies) > 10
        # Should have major agencies
        assert "HUD" in agencies or "HHS" in agencies
        # Counts should be positive
        for count in agencies.values():
            assert count > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
