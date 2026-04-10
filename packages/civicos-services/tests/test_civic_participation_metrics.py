"""
Tests for civic_participation_metrics.py — CivicMetricsTracker engagement
tracking, conversion metrics, retention analysis, community metrics, and
foundation ROI reporting.

Uses a real SQLite database in a temp directory. Mocks only external I/O
(cost log file reads) where needed.

To run:
    pytest packages/civicos-services/tests/test_civic_participation_metrics.py -q --override-ini="addopts="
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from civicos_services.storage.civic_participation_metrics import (
    CivicActionEvent,
    CivicMetricsTracker,
    CommunityMetrics,
    FoundationROIMetrics,
    UserEngagementSession,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker(tmp_path):
    """CivicMetricsTracker using a temp DB and cost log."""
    t = CivicMetricsTracker.__new__(CivicMetricsTracker)
    t.db_path = str(tmp_path / "test_participation.db")
    t.cost_log_file = str(tmp_path / "cost_monitoring.json")
    t._initialize_database()
    return t


def _make_action(
    id="act-1",
    user_id="user-1",
    event_type="email_draft",
    opportunity_id="opp-1",
    jurisdiction_id="city-san-rafael",
    timestamp=None,
    completion_status="completed",
    metadata=None,
):
    return CivicActionEvent(
        id=id,
        user_id=user_id,
        event_type=event_type,
        opportunity_id=opportunity_id,
        jurisdiction_id=jurisdiction_id,
        timestamp=timestamp or datetime.now().isoformat(),
        completion_status=completion_status,
        metadata=metadata or {},
    )


def _make_session(
    session_id="sess-1",
    user_id="user-1",
    started_at=None,
    ended_at=None,
    pages_viewed=5,
    opportunities_discovered=3,
    actions_initiated=2,
    actions_completed=1,
    user_experience_level="new",
    device_type="desktop",
):
    now = datetime.now()
    return UserEngagementSession(
        session_id=session_id,
        user_id=user_id,
        started_at=started_at or now.isoformat(),
        ended_at=ended_at or (now + timedelta(minutes=15)).isoformat(),
        pages_viewed=pages_viewed,
        opportunities_discovered=opportunities_discovered,
        actions_initiated=actions_initiated,
        actions_completed=actions_completed,
        user_experience_level=user_experience_level,
        device_type=device_type,
    )


# ---------------------------------------------------------------------------
# Database initialization
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    def test_creates_all_tables(self, tracker):
        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "civic_actions" in tables
        assert "engagement_sessions" in tables
        assert "user_profiles" in tables
        assert "community_connections" in tables
        assert "foundation_reports" in tables

    def test_idempotent_initialization(self, tracker):
        """Calling _initialize_database twice does not error."""
        tracker._initialize_database()
        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM civic_actions")
        assert cursor.fetchone()[0] == 0
        conn.close()


# ---------------------------------------------------------------------------
# Tracking civic actions
# ---------------------------------------------------------------------------


class TestTrackCivicAction:
    def test_inserts_action_into_db(self, tracker):
        action = _make_action(id="act-100", user_id="u1", event_type="comment_submit")
        tracker.track_civic_action(action)

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, event_type, completion_status FROM civic_actions")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "act-100"
        assert row[1] == "u1"
        assert row[2] == "comment_submit"
        assert row[3] == "completed"

    def test_stores_metadata_as_json(self, tracker):
        action = _make_action(metadata={"source": "extension", "page": "housing"})
        tracker.track_civic_action(action)

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT metadata FROM civic_actions WHERE id = ?", (action.id,))
        stored = json.loads(cursor.fetchone()[0])
        conn.close()

        assert stored["source"] == "extension"
        assert stored["page"] == "housing"

    def test_creates_user_profile_on_first_action(self, tracker):
        action = _make_action(user_id="new-user")
        tracker.track_civic_action(action)

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, total_actions, experience_level FROM user_profiles WHERE user_id = ?",
            ("new-user",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "new-user"
        assert row[1] == 1
        assert row[2] == "new"

    def test_multiple_actions_increment_total(self, tracker):
        for i in range(4):
            tracker.track_civic_action(
                _make_action(id=f"act-{i}", user_id="u-multi")
            )

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT total_actions, experience_level FROM user_profiles WHERE user_id = ?",
            ("u-multi",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 4
        assert row[1] == "returning"


# ---------------------------------------------------------------------------
# Experience level thresholds
# ---------------------------------------------------------------------------


class TestExperienceLevelProgression:
    def test_new_with_fewer_than_3_actions(self, tracker):
        for i in range(2):
            tracker.track_civic_action(_make_action(id=f"a{i}", user_id="u-new"))

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT experience_level FROM user_profiles WHERE user_id = 'u-new'")
        assert cursor.fetchone()[0] == "new"
        conn.close()

    def test_returning_at_3_actions(self, tracker):
        for i in range(3):
            tracker.track_civic_action(_make_action(id=f"a{i}", user_id="u-ret"))

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT experience_level FROM user_profiles WHERE user_id = 'u-ret'")
        assert cursor.fetchone()[0] == "returning"
        conn.close()

    def test_expert_at_10_actions(self, tracker):
        for i in range(10):
            tracker.track_civic_action(_make_action(id=f"a{i}", user_id="u-exp"))

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT experience_level FROM user_profiles WHERE user_id = 'u-exp'")
        assert cursor.fetchone()[0] == "expert"
        conn.close()

    def test_nine_actions_still_returning(self, tracker):
        for i in range(9):
            tracker.track_civic_action(_make_action(id=f"a{i}", user_id="u-nine"))

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT experience_level FROM user_profiles WHERE user_id = 'u-nine'")
        assert cursor.fetchone()[0] == "returning"
        conn.close()


# ---------------------------------------------------------------------------
# Tracking engagement sessions
# ---------------------------------------------------------------------------


class TestTrackEngagementSession:
    def test_inserts_session(self, tracker):
        session = _make_session(
            session_id="s-1",
            user_id="u1",
            pages_viewed=8,
            opportunities_discovered=4,
            actions_initiated=3,
            actions_completed=2,
        )
        tracker.track_engagement_session(session)

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT session_id, pages_viewed, opportunities_discovered, actions_initiated, actions_completed "
            "FROM engagement_sessions WHERE session_id = ?",
            ("s-1",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "s-1"
        assert row[1] == 8
        assert row[2] == 4
        assert row[3] == 3
        assert row[4] == 2

    def test_upsert_replaces_existing_session(self, tracker):
        tracker.track_engagement_session(_make_session(session_id="s-dup", pages_viewed=3))
        tracker.track_engagement_session(_make_session(session_id="s-dup", pages_viewed=10))

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pages_viewed FROM engagement_sessions WHERE session_id = ?",
            ("s-dup",),
        )
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0][0] == 10


# ---------------------------------------------------------------------------
# Conversion metrics
# ---------------------------------------------------------------------------


class TestConversionMetrics:
    def test_empty_database_returns_zero_rates(self, tracker):
        metrics = tracker.get_conversion_metrics(days_back=30)

        assert metrics["discovery_to_initiation_rate"] == 0.0
        assert metrics["initiation_to_completion_rate"] == 0.0
        assert metrics["overall_conversion_rate"] == 0.0
        assert metrics["total_sessions"] == 0
        assert metrics["unique_users"] == 0

    def test_calculates_conversion_rates(self, tracker):
        # 10 discoveries, 6 initiated, 4 completed
        tracker.track_engagement_session(
            _make_session(
                session_id="s-conv",
                opportunities_discovered=10,
                actions_initiated=6,
                actions_completed=4,
            )
        )
        metrics = tracker.get_conversion_metrics(days_back=30)

        assert metrics["discovery_to_initiation_rate"] == 60.0
        assert metrics["initiation_to_completion_rate"] == pytest.approx(66.666, abs=0.01)
        assert metrics["overall_conversion_rate"] == 40.0
        assert metrics["total_sessions"] == 1
        assert metrics["unique_users"] == 1

    def test_aggregates_multiple_sessions(self, tracker):
        # Session A: 10 discovered, 5 initiated, 3 completed
        tracker.track_engagement_session(
            _make_session(
                session_id="s-a",
                user_id="u1",
                opportunities_discovered=10,
                actions_initiated=5,
                actions_completed=3,
            )
        )
        # Session B: 20 discovered, 10 initiated, 8 completed
        tracker.track_engagement_session(
            _make_session(
                session_id="s-b",
                user_id="u2",
                opportunities_discovered=20,
                actions_initiated=10,
                actions_completed=8,
            )
        )

        metrics = tracker.get_conversion_metrics(days_back=30)

        # Totals: 30 discovered, 15 initiated, 11 completed
        assert metrics["discovery_to_initiation_rate"] == 50.0
        assert metrics["initiation_to_completion_rate"] == pytest.approx(73.333, abs=0.01)
        assert metrics["overall_conversion_rate"] == pytest.approx(36.666, abs=0.01)
        assert metrics["unique_users"] == 2
        assert metrics["total_sessions"] == 2

    def test_zero_discoveries_yields_zero_rates(self, tracker):
        tracker.track_engagement_session(
            _make_session(
                session_id="s-zero",
                opportunities_discovered=0,
                actions_initiated=0,
                actions_completed=0,
            )
        )
        metrics = tracker.get_conversion_metrics(days_back=30)

        assert metrics["discovery_to_initiation_rate"] == 0
        assert metrics["initiation_to_completion_rate"] == 0
        assert metrics["overall_conversion_rate"] == 0
        assert metrics["total_sessions"] == 1

    def test_action_completion_rates_by_type(self, tracker):
        # 2 email_draft: 1 completed, 1 initiated
        tracker.track_civic_action(
            _make_action(id="a1", event_type="email_draft", completion_status="completed")
        )
        tracker.track_civic_action(
            _make_action(id="a2", event_type="email_draft", completion_status="initiated")
        )
        # 1 calendar_add: completed
        tracker.track_civic_action(
            _make_action(id="a3", event_type="calendar_add", completion_status="completed")
        )

        metrics = tracker.get_conversion_metrics(days_back=30)
        rates = metrics["action_completion_rates"]

        assert rates["email_draft"]["total"] == 2
        assert rates["email_draft"]["completed"] == 1
        assert rates["email_draft"]["completion_rate"] == 50.0

        assert rates["calendar_add"]["total"] == 1
        assert rates["calendar_add"]["completed"] == 1
        assert rates["calendar_add"]["completion_rate"] == 100.0

    def test_old_sessions_excluded_by_days_back(self, tracker):
        old_time = (datetime.now() - timedelta(days=60)).isoformat()
        tracker.track_engagement_session(
            _make_session(
                session_id="s-old",
                started_at=old_time,
                opportunities_discovered=10,
                actions_initiated=5,
                actions_completed=3,
            )
        )
        metrics = tracker.get_conversion_metrics(days_back=30)

        assert metrics["total_sessions"] == 0
        assert metrics["unique_users"] == 0


# ---------------------------------------------------------------------------
# Retention analysis
# ---------------------------------------------------------------------------


class TestRetentionAnalysis:
    def test_empty_database_returns_empty_distributions(self, tracker):
        result = tracker.get_user_retention_analysis()

        assert result["experience_distribution"] == {}
        assert result["retention_cohorts"] == []

    def test_experience_distribution_groups_users(self, tracker):
        # Create 2 new users and 1 returning user
        tracker.track_civic_action(_make_action(id="a1", user_id="new-1"))
        tracker.track_civic_action(_make_action(id="a2", user_id="new-2"))

        for i in range(5):
            tracker.track_civic_action(_make_action(id=f"ret-{i}", user_id="ret-1"))

        result = tracker.get_user_retention_analysis()
        dist = result["experience_distribution"]

        assert "new" in dist
        assert dist["new"]["user_count"] == 2
        assert dist["new"]["avg_actions"] == 1.0

        assert "returning" in dist
        assert dist["returning"]["user_count"] == 1
        assert dist["returning"]["avg_actions"] == 5.0


# ---------------------------------------------------------------------------
# Community metrics
# ---------------------------------------------------------------------------


class TestCommunityMetrics:
    def test_empty_database_returns_empty_dicts(self, tracker):
        result = tracker.get_community_metrics()

        assert result["jurisdiction_networks"] == {}
        assert result["jurisdiction_activity"] == {}

    def test_jurisdiction_activity_from_recent_actions(self, tracker):
        tracker.track_civic_action(
            _make_action(id="a1", user_id="u1", jurisdiction_id="city-san-rafael")
        )
        tracker.track_civic_action(
            _make_action(id="a2", user_id="u2", jurisdiction_id="city-san-rafael")
        )
        tracker.track_civic_action(
            _make_action(id="a3", user_id="u1", jurisdiction_id="city-berkeley")
        )

        result = tracker.get_community_metrics()
        activity = result["jurisdiction_activity"]

        assert "city-san-rafael" in activity
        assert activity["city-san-rafael"]["active_users"] == 2
        assert activity["city-san-rafael"]["total_actions"] == 2

        assert "city-berkeley" in activity
        assert activity["city-berkeley"]["active_users"] == 1
        assert activity["city-berkeley"]["total_actions"] == 1

    def test_null_jurisdiction_excluded(self, tracker):
        tracker.track_civic_action(
            _make_action(id="a-null", jurisdiction_id=None)
        )
        result = tracker.get_community_metrics()

        assert result["jurisdiction_activity"] == {}

    def test_community_connections_grouped_by_jurisdiction(self, tracker):
        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO community_connections (id, user_id_1, user_id_2, connection_type, shared_jurisdiction, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("c1", "u1", "u2", "neighbor", "city-san-rafael", "active"),
        )
        cursor.execute(
            "INSERT INTO community_connections (id, user_id_1, user_id_2, connection_type, shared_jurisdiction, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("c2", "u3", "u4", "neighbor", "city-san-rafael", "active"),
        )
        cursor.execute(
            "INSERT INTO community_connections (id, user_id_1, user_id_2, connection_type, shared_jurisdiction, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("c3", "u5", "u6", "neighbor", "city-berkeley", "inactive"),
        )
        conn.commit()
        conn.close()

        result = tracker.get_community_metrics()
        networks = result["jurisdiction_networks"]

        assert "city-san-rafael" in networks
        assert networks["city-san-rafael"]["connections"] == 2
        # Inactive connections are excluded
        assert "city-berkeley" not in networks


# ---------------------------------------------------------------------------
# Cost period calculation
# ---------------------------------------------------------------------------


class TestGetPeriodCosts:
    def test_missing_cost_file_returns_zero(self, tracker):
        cutoff = datetime.now() - timedelta(days=30)
        assert tracker._get_period_costs(cutoff) == 0.0

    def test_invalid_json_returns_zero(self, tracker):
        with open(tracker.cost_log_file, "w") as f:
            f.write("not valid json{{{")

        cutoff = datetime.now() - timedelta(days=30)
        assert tracker._get_period_costs(cutoff) == 0.0

    def test_sums_costs_after_cutoff(self, tracker):
        now = datetime.now()
        entries = [
            {"timestamp": (now - timedelta(days=5)).isoformat(), "estimated_cost": 10.50},
            {"timestamp": (now - timedelta(days=15)).isoformat(), "estimated_cost": 7.25},
            {"timestamp": (now - timedelta(days=45)).isoformat(), "estimated_cost": 100.00},
        ]
        with open(tracker.cost_log_file, "w") as f:
            json.dump(entries, f)

        cutoff = now - timedelta(days=30)
        total = tracker._get_period_costs(cutoff)

        assert total == pytest.approx(17.75, abs=0.01)

    def test_no_costs_after_cutoff_returns_zero(self, tracker):
        now = datetime.now()
        entries = [
            {"timestamp": (now - timedelta(days=60)).isoformat(), "estimated_cost": 50.00},
        ]
        with open(tracker.cost_log_file, "w") as f:
            json.dump(entries, f)

        cutoff = now - timedelta(days=30)
        assert tracker._get_period_costs(cutoff) == 0.0


# ---------------------------------------------------------------------------
# Foundation ROI
# ---------------------------------------------------------------------------


class TestFoundationROI:
    def test_empty_database_returns_zero_metrics(self, tracker):
        roi = tracker.calculate_foundation_roi(30)

        assert roi.civic_actions_completed == 0
        assert roi.total_cost == 0.0
        # cost_per_action uses max(completed_actions, 1) to avoid div-by-zero
        assert roi.cost_per_action == 0.0
        assert roi.user_retention_rate == 0
        assert roi.community_growth_rate == 0.0

    def test_cost_per_action_calculation(self, tracker):
        # Write cost file
        now = datetime.now()
        entries = [
            {"timestamp": (now - timedelta(days=5)).isoformat(), "estimated_cost": 30.0},
        ]
        with open(tracker.cost_log_file, "w") as f:
            json.dump(entries, f)

        # Create 3 completed actions
        for i in range(3):
            tracker.track_civic_action(
                _make_action(id=f"roi-{i}", completion_status="completed")
            )

        roi = tracker.calculate_foundation_roi(30)

        assert roi.civic_actions_completed == 3
        assert roi.total_cost == 30.0
        assert roi.cost_per_action == pytest.approx(10.0, abs=0.01)

    def test_initiated_actions_not_counted(self, tracker):
        tracker.track_civic_action(
            _make_action(id="init-1", completion_status="initiated")
        )
        tracker.track_civic_action(
            _make_action(id="comp-1", completion_status="completed")
        )

        roi = tracker.calculate_foundation_roi(30)

        assert roi.civic_actions_completed == 1

    def test_retention_rate_with_returning_users(self, tracker):
        now = datetime.now()
        old_time = (now - timedelta(days=60)).isoformat()
        new_time = now.isoformat()

        # User who was active before cutoff AND after cutoff = returning
        tracker.track_engagement_session(
            _make_session(session_id="old-s1", user_id="u-return", started_at=old_time)
        )
        tracker.track_engagement_session(
            _make_session(session_id="new-s1", user_id="u-return", started_at=new_time)
        )

        # User who was only active before cutoff = churned
        tracker.track_engagement_session(
            _make_session(session_id="old-s2", user_id="u-churn", started_at=old_time)
        )

        roi = tracker.calculate_foundation_roi(30)

        # 1 returning out of 2 historical users = 50%
        assert roi.user_retention_rate == 50.0

    def test_community_growth_rate(self, tracker):
        now = datetime.now()
        old_time = (now - timedelta(days=60)).isoformat()
        new_time = (now - timedelta(days=5)).isoformat()

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        # 2 old connections
        cursor.execute(
            "INSERT INTO community_connections (id, user_id_1, user_id_2, connection_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("old-1", "u1", "u2", "neighbor", old_time),
        )
        cursor.execute(
            "INSERT INTO community_connections (id, user_id_1, user_id_2, connection_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("old-2", "u3", "u4", "neighbor", old_time),
        )
        # 1 new connection
        cursor.execute(
            "INSERT INTO community_connections (id, user_id_1, user_id_2, connection_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("new-1", "u5", "u6", "neighbor", new_time),
        )
        conn.commit()
        conn.close()

        roi = tracker.calculate_foundation_roi(30)

        # 1 new / 2 old * 100 = 50%
        assert roi.community_growth_rate == 50.0

    def test_reporting_period_string_format(self, tracker):
        roi = tracker.calculate_foundation_roi(30)

        assert "30 days" in roi.reporting_period
        assert datetime.now().strftime("%Y-%m-%d") in roi.reporting_period

    def test_returns_foundation_roi_metrics_dataclass(self, tracker):
        roi = tracker.calculate_foundation_roi(30)

        assert isinstance(roi, FoundationROIMetrics)
        assert roi.civic_participation_increase == roi.civic_actions_completed


# ---------------------------------------------------------------------------
# Foundation report generation
# ---------------------------------------------------------------------------


class TestFoundationReport:
    def test_report_contains_key_sections(self, tracker):
        report = tracker.generate_foundation_report(save_to_file=False)

        assert "FOUNDATION IMPACT REPORT" in report
        assert "FOUNDATION ROI SUMMARY" in report
        assert "CIVIC PARTICIPATION CONVERSION RATES" in report
        assert "USER EXPERIENCE PROGRESSION" in report
        assert "REGIONAL COMMUNITY IMPACT" in report
        assert "FOUNDATION METRICS ACHIEVED" in report

    def test_report_includes_numeric_values(self, tracker):
        # Add data so the report has non-trivial values
        tracker.track_engagement_session(
            _make_session(
                session_id="rpt-s",
                opportunities_discovered=10,
                actions_initiated=5,
                actions_completed=3,
            )
        )
        tracker.track_civic_action(
            _make_action(id="rpt-a", completion_status="completed")
        )

        report = tracker.generate_foundation_report(save_to_file=False)

        # Verify conversion rates appear (not just 0.0)
        assert "Total Sessions: 1" in report
        assert "50.0%" in report  # discovery_to_initiation: 5/10

    def test_save_to_file_creates_report_file(self, tracker, tmp_path):
        # Override the data dir so report goes to tmp
        report_dir = str(tmp_path / "data")
        os.makedirs(report_dir, exist_ok=True)

        with patch("civicos_services.storage.civic_participation_metrics.os.makedirs"):
            with patch(
                "builtins.open",
                side_effect=lambda f, m="r": open(
                    os.path.join(report_dir, os.path.basename(f)), m
                )
                if "foundation_impact_report" in str(f)
                else open(f, m),
            ):
                # Just test that save_to_file=False does NOT attempt to write
                report = tracker.generate_foundation_report(save_to_file=False)
                assert "FOUNDATION IMPACT REPORT" in report

    def test_no_file_written_when_save_disabled(self, tracker, tmp_path):
        report = tracker.generate_foundation_report(save_to_file=False)

        # No report files should exist in tmp
        import glob as g

        found = g.glob(str(tmp_path / "**" / "foundation_impact_report*"), recursive=True)
        assert len(found) == 0
        assert "FOUNDATION IMPACT REPORT" in report

    def test_expert_user_count_in_report(self, tracker):
        for i in range(10):
            tracker.track_civic_action(_make_action(id=f"exp-{i}", user_id="power-user"))

        report = tracker.generate_foundation_report(save_to_file=False)

        assert "1 expert users developed" in report


# ---------------------------------------------------------------------------
# Demo activity generation
# ---------------------------------------------------------------------------


class TestDemoActivity:
    def test_generates_sessions_and_actions(self, tracker):
        tracker.track_demo_activity()

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM engagement_sessions")
        session_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM civic_actions")
        action_count = cursor.fetchone()[0]

        conn.close()

        # 4 users, each gets 1 session
        assert session_count == 4
        # user0: 1, user1: 2, user2: 3, user3: 4 = 10 actions
        assert action_count == 10

    def test_demo_creates_user_profiles(self, tracker):
        tracker.track_demo_activity()

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_profiles")
        profile_count = cursor.fetchone()[0]
        conn.close()

        assert profile_count == 4

    def test_demo_action_types_follow_pattern(self, tracker):
        tracker.track_demo_activity()

        conn = sqlite3.connect(tracker.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT event_type FROM civic_actions ORDER BY event_type")
        types = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "email_draft" in types
        assert "calendar_add" in types
        assert "comment_submit" in types


# ---------------------------------------------------------------------------
# Dataclass sanity
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_civic_action_event_fields(self):
        action = _make_action(
            id="dc-1",
            user_id="u-dc",
            event_type="meeting_attend",
            jurisdiction_id="city-berkeley",
            completion_status="verified",
        )
        assert action.id == "dc-1"
        assert action.user_id == "u-dc"
        assert action.event_type == "meeting_attend"
        assert action.jurisdiction_id == "city-berkeley"
        assert action.completion_status == "verified"

    def test_community_metrics_fields(self):
        cm = CommunityMetrics(
            jurisdiction_id="city-san-rafael",
            active_users_count=25,
            neighbor_connections=10,
            collaborative_actions=5,
            meeting_coordination_events=3,
            comment_collaboration_rate=0.45,
        )
        assert cm.active_users_count == 25
        assert cm.comment_collaboration_rate == 0.45
        assert cm.jurisdiction_id == "city-san-rafael"

    def test_foundation_roi_metrics_fields(self):
        roi = FoundationROIMetrics(
            reporting_period="30 days ending 2026-04-10",
            total_cost=45.50,
            civic_actions_completed=15,
            cost_per_action=3.03,
            user_retention_rate=72.5,
            community_growth_rate=25.0,
            civic_participation_increase=15,
        )
        assert roi.total_cost == 45.50
        assert roi.cost_per_action == 3.03
        assert roi.user_retention_rate == 72.5
