"""
Tests for civic-extraction clients.
"""

import pytest
from datetime import datetime

from civic_extraction import LegistarClient, CivicClerkClient, ProudCityClient, Meeting
from civic_extraction import create_san_rafael_client, create_san_rafael_source
from civic_extraction import ProudCitySource, ExtractionConfig, DataSource
from civic_extraction.clients.base import BaseExtractor, Extractor


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
        assert status["stages"]["index"]["state"] == StageState.PENDING.value

    def test_pipeline_has_three_stages(self):
        """Test Pipeline has discover, ingest, index stages."""
        from civic_extraction.pipeline import Pipeline

        assert Pipeline.STAGES == ["discover", "ingest", "index"]

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

        # All three stages present
        assert "discover" in status["stages"]
        assert "ingest" in status["stages"]
        assert "index" in status["stages"]

        # Each stage has required fields
        for stage_name in ["discover", "ingest", "index"]:
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
