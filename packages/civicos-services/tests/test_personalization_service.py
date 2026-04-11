"""
Tests for PersonalizationService — profile, civic history, behavioral inference.

Uses a real SQLite database (on disk, per-test) with the schema the service
expects. No mocks of the subject under test; only the clock where deterministic
time-based inputs are required.

To run:
    pytest packages/civicos-services/tests/test_personalization_service.py -q --override-ini="addopts="
"""

import json
import math
import sqlite3
import uuid
from datetime import datetime, timedelta

import pytest

from civicos_services.storage.personalization_service import PersonalizationService


# ---------------------------------------------------------------------------
# Schema + fixtures
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    stakes TEXT,
    years_in_area INTEGER,
    district TEXT,
    neighborhood TEXT,
    jurisdiction_id TEXT NOT NULL,
    expertise TEXT,
    civic_interests TEXT,
    topics_following TEXT,
    notification_preferences TEXT,
    privacy_settings TEXT,
    profile_completeness INTEGER DEFAULT 0
);

CREATE TABLE civic_history (
    action_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    metadata TEXT,
    jurisdiction_id TEXT,
    topic TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
def db_path(tmp_path):
    """Create a fresh SQLite DB with the required schema."""
    path = tmp_path / "personalization.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
    return str(path)


@pytest.fixture
def service(db_path):
    return PersonalizationService(db_path=db_path)


def _insert_profile_row(db_path, user_id="user-1", **overrides):
    """Insert a raw row into user_profiles. All JSON fields must be pre-serialized."""
    defaults = {
        "user_id": user_id,
        "display_name": "Alice",
        "avatar_url": "https://example.com/alice.png",
        "stakes": json.dumps(["homeowner", "parent"]),
        "years_in_area": 7,
        "district": "District 3",
        "neighborhood": "Sun Valley",
        "jurisdiction_id": "city-san-rafael",
        "expertise": "Urban planning",
        "civic_interests": json.dumps(["housing", "transit"]),
        "topics_following": json.dumps(["budget"]),
        "notification_preferences": json.dumps({"email": True, "sms": False}),
        "privacy_settings": json.dumps({"profileVisibility": "public"}),
        "profile_completeness": 75,
    }
    defaults.update(overrides)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_profiles (
                user_id, display_name, avatar_url, stakes, years_in_area,
                district, neighborhood, jurisdiction_id, expertise,
                civic_interests, topics_following, notification_preferences,
                privacy_settings, profile_completeness
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                defaults["user_id"],
                defaults["display_name"],
                defaults["avatar_url"],
                defaults["stakes"],
                defaults["years_in_area"],
                defaults["district"],
                defaults["neighborhood"],
                defaults["jurisdiction_id"],
                defaults["expertise"],
                defaults["civic_interests"],
                defaults["topics_following"],
                defaults["notification_preferences"],
                defaults["privacy_settings"],
                defaults["profile_completeness"],
            ),
        )


def _insert_action_row(
    db_path,
    user_id="user-1",
    action_type="bill_viewed",
    topic=None,
    created_at=None,
    action_id=None,
    metadata=None,
    entity_type="bill",
    entity_id="bill-1",
    jurisdiction_id="city-san-rafael",
):
    """Insert a raw civic_history row with an explicit created_at."""
    action_id = action_id or str(uuid.uuid4())
    if metadata is None and topic is not None:
        metadata = {"topic": topic, "jurisdictionId": jurisdiction_id}
    metadata_json = json.dumps(metadata) if metadata else None
    with sqlite3.connect(db_path) as conn:
        if created_at is None:
            conn.execute(
                """
                INSERT INTO civic_history (
                    action_id, user_id, action_type, entity_type, entity_id,
                    metadata, jurisdiction_id, topic
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    user_id,
                    action_type,
                    entity_type,
                    entity_id,
                    metadata_json,
                    jurisdiction_id,
                    topic,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO civic_history (
                    action_id, user_id, action_type, entity_type, entity_id,
                    metadata, jurisdiction_id, topic, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    user_id,
                    action_type,
                    entity_type,
                    entity_id,
                    metadata_json,
                    jurisdiction_id,
                    topic,
                    created_at,
                ),
            )
    return action_id


# ---------------------------------------------------------------------------
# __init__ and _get_connection
# ---------------------------------------------------------------------------


class TestInit:
    def test_stores_db_path_and_initializes_empty_cache(self, db_path):
        svc = PersonalizationService(db_path=db_path)
        assert svc.db_path == db_path
        assert svc.cache == {}

    def test_get_connection_uses_row_factory(self, service):
        conn = service._get_connection()
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# get_user_profile
# ---------------------------------------------------------------------------


class TestGetUserProfile:
    def test_returns_none_when_user_missing(self, service):
        assert service.get_user_profile("ghost") is None

    def test_returns_profile_with_parsed_json_fields(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1")
        profile = service.get_user_profile("user-1")
        assert profile is not None
        assert profile["user_id"] == "user-1"
        assert profile["display_name"] == "Alice"
        assert profile["jurisdiction_id"] == "city-san-rafael"
        assert profile["years_in_area"] == 7
        assert profile["profile_completeness"] == 75
        # JSON fields decoded
        assert profile["stakes"] == ["homeowner", "parent"]
        assert profile["civic_interests"] == ["housing", "transit"]
        assert profile["topics_following"] == ["budget"]
        assert profile["notification_preferences"] == {"email": True, "sms": False}
        assert profile["privacy_settings"] == {"profileVisibility": "public"}

    def test_empty_json_fields_default_to_empty_containers(self, service, db_path):
        _insert_profile_row(
            db_path,
            user_id="user-2",
            stakes=None,
            civic_interests=None,
            topics_following=None,
            notification_preferences=None,
            privacy_settings=None,
        )
        profile = service.get_user_profile("user-2")
        assert profile["stakes"] == []
        assert profile["civic_interests"] == []
        assert profile["topics_following"] == []
        assert profile["notification_preferences"] == {}
        assert profile["privacy_settings"] == {}

    def test_caches_result_for_subsequent_calls(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1", display_name="Alice")
        first = service.get_user_profile("user-1")
        assert first["display_name"] == "Alice"
        assert "user-1" in service.cache

        # Mutate the DB directly — a cached call should still return the old value.
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE user_profiles SET display_name = ? WHERE user_id = ?",
                ("Bob", "user-1"),
            )
        second = service.get_user_profile("user-1")
        assert second["display_name"] == "Alice"
        assert second is first  # same cached object

    def test_cache_miss_when_different_user_id(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1", display_name="Alice")
        _insert_profile_row(db_path, user_id="user-2", display_name="Bob")
        assert service.get_user_profile("user-1")["display_name"] == "Alice"
        assert service.get_user_profile("user-2")["display_name"] == "Bob"
        assert set(service.cache.keys()) == {"user-1", "user-2"}


# ---------------------------------------------------------------------------
# create_user_profile
# ---------------------------------------------------------------------------


class TestCreateUserProfile:
    def test_raises_when_jurisdiction_id_missing(self, service):
        with pytest.raises(ValueError, match="jurisdictionId is required"):
            service.create_user_profile("user-1", {"displayName": "Alice"})

    def test_persists_all_scalar_fields(self, service, db_path):
        profile = service.create_user_profile(
            "user-1",
            {
                "jurisdictionId": "city-san-rafael",
                "displayName": "Alice",
                "avatarUrl": "https://example.com/a.png",
                "yearsInArea": 5,
                "district": "D2",
                "neighborhood": "Gerstle Park",
                "expertise": "Transit planning",
            },
        )
        assert profile["user_id"] == "user-1"
        assert profile["display_name"] == "Alice"
        assert profile["avatar_url"] == "https://example.com/a.png"
        assert profile["years_in_area"] == 5
        assert profile["district"] == "D2"
        assert profile["neighborhood"] == "Gerstle Park"
        assert profile["jurisdiction_id"] == "city-san-rafael"
        assert profile["expertise"] == "Transit planning"

    def test_serializes_list_and_dict_fields_to_json(self, service, db_path):
        service.create_user_profile(
            "user-1",
            {
                "jurisdictionId": "city-san-rafael",
                "stakes": ["renter"],
                "civicInterests": ["housing"],
                "topicsFollowing": ["budget", "parks"],
                "notificationPreferences": {"email": True},
            },
        )
        # Read raw row to verify JSON was stored as strings.
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM user_profiles WHERE user_id = 'user-1'").fetchone())
        assert json.loads(row["stakes"]) == ["renter"]
        assert json.loads(row["civic_interests"]) == ["housing"]
        assert json.loads(row["topics_following"]) == ["budget", "parks"]
        assert json.loads(row["notification_preferences"]) == {"email": True}

    def test_defaults_privacy_settings_when_omitted(self, service, db_path):
        service.create_user_profile("user-1", {"jurisdictionId": "city-san-rafael"})
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT privacy_settings FROM user_profiles WHERE user_id = 'user-1'"
            ).fetchone()
        settings = json.loads(row[0])
        assert settings == {
            "profileVisibility": "public",
            "showCivicHistory": True,
            "allowBehavioralInference": True,
        }

    def test_honors_caller_privacy_settings(self, service, db_path):
        custom = {"profileVisibility": "private", "showCivicHistory": False}
        service.create_user_profile(
            "user-1",
            {"jurisdictionId": "city-san-rafael", "privacySettings": custom},
        )
        profile = service.get_user_profile("user-1")
        assert profile["privacy_settings"] == custom

    def test_defaults_empty_collections_for_missing_fields(self, service, db_path):
        service.create_user_profile("user-1", {"jurisdictionId": "city-san-rafael"})
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM user_profiles WHERE user_id = 'user-1'").fetchone())
        assert json.loads(row["stakes"]) == []
        assert json.loads(row["civic_interests"]) == []
        assert json.loads(row["topics_following"]) == []
        assert json.loads(row["notification_preferences"]) == {}

    def test_stores_computed_completeness(self, service, db_path):
        service.create_user_profile(
            "user-1",
            {
                "jurisdictionId": "city-san-rafael",
                "displayName": "Alice",  # 5
                "stakes": ["renter"],  # 15
                "yearsInArea": 3,  # 10
            },
        )
        profile = service.get_user_profile("user-1")
        assert profile["profile_completeness"] == 30

    def test_invalidates_stale_cache_entry_on_create(self, service, db_path):
        # Pre-seed the cache with a stale entry.
        service.cache["user-1"] = {"stale": True}
        service.create_user_profile(
            "user-1", {"jurisdictionId": "city-san-rafael", "displayName": "Alice"}
        )
        # After create, get_user_profile is called internally and the cache entry
        # reflects the freshly-inserted row, not the stale placeholder.
        assert service.cache["user-1"]["display_name"] == "Alice"
        assert "stale" not in service.cache["user-1"]

    def test_returns_fresh_profile_object(self, service):
        result = service.create_user_profile(
            "user-1",
            {"jurisdictionId": "city-san-rafael", "displayName": "Alice"},
        )
        assert result["display_name"] == "Alice"
        assert result["jurisdiction_id"] == "city-san-rafael"
        assert result["stakes"] == []
        assert result["civic_interests"] == []


# ---------------------------------------------------------------------------
# _calculate_completeness
# ---------------------------------------------------------------------------


class TestCalculateCompleteness:
    def test_empty_profile_scores_zero(self, service):
        assert service._calculate_completeness({}) == 0

    def test_full_profile_scores_one_hundred(self, service):
        score = service._calculate_completeness(
            {
                "displayName": "Alice",
                "stakes": ["renter"],
                "yearsInArea": 5,
                "district": "D3",
                "neighborhood": "Sun Valley",
                "expertise": "Transit",
                "civicInterests": ["housing"],
                "avatarUrl": "https://example.com/a.png",
                "notificationPreferences": {"email": True},
            }
        )
        assert score == 100

    def test_empty_list_does_not_count(self, service):
        assert service._calculate_completeness({"stakes": []}) == 0
        assert service._calculate_completeness({"civicInterests": []}) == 0

    def test_empty_dict_does_not_count(self, service):
        assert service._calculate_completeness({"notificationPreferences": {}}) == 0

    def test_zero_years_is_falsy_and_excluded(self, service):
        """yearsInArea=0 is falsy, so the branch does not add weight."""
        assert service._calculate_completeness({"yearsInArea": 0}) == 0

    def test_weights_sum_for_partial_profile(self, service):
        score = service._calculate_completeness(
            {
                "displayName": "A",  # 5
                "expertise": "Planning",  # 15
                "civicInterests": ["housing", "transit"],  # 20
            }
        )
        assert score == 40

    def test_each_field_has_expected_individual_weight(self, service):
        # Pin each field's individual contribution so mutations of weight ints fail.
        assert service._calculate_completeness({"displayName": "A"}) == 5
        assert service._calculate_completeness({"stakes": ["x"]}) == 15
        assert service._calculate_completeness({"yearsInArea": 1}) == 10
        assert service._calculate_completeness({"district": "D3"}) == 10
        assert service._calculate_completeness({"neighborhood": "N"}) == 10
        assert service._calculate_completeness({"expertise": "E"}) == 15
        assert service._calculate_completeness({"civicInterests": ["x"]}) == 20
        assert service._calculate_completeness({"avatarUrl": "url"}) == 5
        assert service._calculate_completeness({"notificationPreferences": {"email": True}}) == 10


# ---------------------------------------------------------------------------
# track_action
# ---------------------------------------------------------------------------


class TestTrackAction:
    def test_returns_uuid_formatted_string(self, service):
        action_id = service.track_action(
            user_id="user-1",
            action_type="bill_viewed",
            entity_type="bill",
            entity_id="bill-1",
        )
        # Valid UUID string — will raise if not parseable
        parsed = uuid.UUID(action_id)
        assert str(parsed) == action_id

    def test_stores_action_in_database(self, service, db_path):
        action_id = service.track_action(
            user_id="user-1",
            action_type="comment_drafted",
            entity_type="meeting",
            entity_id="mtg-99",
            metadata={"topic": "housing", "jurisdictionId": "city-san-rafael"},
        )
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM civic_history WHERE action_id = ?", (action_id,)).fetchone())
        assert row["user_id"] == "user-1"
        assert row["action_type"] == "comment_drafted"
        assert row["entity_type"] == "meeting"
        assert row["entity_id"] == "mtg-99"
        assert row["jurisdiction_id"] == "city-san-rafael"
        assert row["topic"] == "housing"
        assert json.loads(row["metadata"]) == {"topic": "housing", "jurisdictionId": "city-san-rafael"}

    def test_metadata_none_stores_null_topic_and_jurisdiction(self, service, db_path):
        action_id = service.track_action(
            user_id="user-1",
            action_type="bill_viewed",
            entity_type="bill",
            entity_id="bill-1",
        )
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM civic_history WHERE action_id = ?", (action_id,)).fetchone())
        assert row["metadata"] is None
        assert row["topic"] is None
        assert row["jurisdiction_id"] is None

    def test_metadata_without_topic_leaves_topic_null(self, service, db_path):
        action_id = service.track_action(
            user_id="user-1",
            action_type="bill_viewed",
            entity_type="bill",
            entity_id="bill-1",
            metadata={"jurisdictionId": "city-san-rafael", "source": "extension"},
        )
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT topic, jurisdiction_id, metadata FROM civic_history WHERE action_id = ?", (action_id,)).fetchone())
        assert row["topic"] is None
        assert row["jurisdiction_id"] == "city-san-rafael"
        assert json.loads(row["metadata"])["source"] == "extension"

    def test_each_call_returns_unique_action_id(self, service):
        id_a = service.track_action("user-1", "bill_viewed", "bill", "b-1")
        id_b = service.track_action("user-1", "bill_viewed", "bill", "b-1")
        assert id_a != id_b


# ---------------------------------------------------------------------------
# get_civic_history
# ---------------------------------------------------------------------------


class TestGetCivicHistory:
    def test_returns_empty_list_when_no_actions(self, service):
        assert service.get_civic_history("user-1") == []

    def test_returns_only_requested_user_actions(self, service, db_path):
        _insert_action_row(db_path, user_id="user-1", action_type="bill_viewed")
        _insert_action_row(db_path, user_id="user-2", action_type="bill_viewed")
        actions = service.get_civic_history("user-1")
        assert len(actions) == 1
        assert actions[0]["user_id"] == "user-1"

    def test_parses_metadata_json(self, service, db_path):
        _insert_action_row(
            db_path,
            user_id="user-1",
            action_type="comment_drafted",
            metadata={"topic": "housing", "note": "strong support"},
        )
        actions = service.get_civic_history("user-1")
        assert actions[0]["metadata"] == {"topic": "housing", "note": "strong support"}

    def test_null_metadata_becomes_empty_dict(self, service, db_path):
        _insert_action_row(db_path, user_id="user-1", action_type="bill_viewed")
        actions = service.get_civic_history("user-1")
        assert actions[0]["metadata"] == {}

    def test_filters_by_action_types(self, service, db_path):
        _insert_action_row(db_path, user_id="user-1", action_type="bill_viewed", created_at="2026-03-01 10:00:00")
        _insert_action_row(db_path, user_id="user-1", action_type="comment_drafted", created_at="2026-03-02 10:00:00")
        _insert_action_row(db_path, user_id="user-1", action_type="meeting_attended", created_at="2026-03-03 10:00:00")

        filtered = service.get_civic_history("user-1", action_types=["comment_drafted", "meeting_attended"])
        types = sorted(a["action_type"] for a in filtered)
        assert types == ["comment_drafted", "meeting_attended"]

    def test_filters_by_since_datetime(self, service, db_path):
        _insert_action_row(db_path, user_id="user-1", action_type="a1", created_at="2026-01-01 00:00:00")
        _insert_action_row(db_path, user_id="user-1", action_type="a2", created_at="2026-02-01 00:00:00")
        _insert_action_row(db_path, user_id="user-1", action_type="a3", created_at="2026-03-01 00:00:00")

        since = datetime(2026, 1, 15, 0, 0, 0)
        results = service.get_civic_history("user-1", since=since)
        types = sorted(r["action_type"] for r in results)
        assert types == ["a2", "a3"]

    def test_since_is_strict_greater_than(self, service, db_path):
        _insert_action_row(db_path, user_id="user-1", action_type="boundary", created_at="2026-02-01 00:00:00")
        since = datetime(2026, 2, 1, 0, 0, 0)
        results = service.get_civic_history("user-1", since=since)
        # Equal timestamps are excluded (uses '>', not '>=')
        assert results == []

    def test_ordering_is_most_recent_first(self, service, db_path):
        _insert_action_row(db_path, user_id="user-1", action_type="oldest", created_at="2026-01-01 00:00:00")
        _insert_action_row(db_path, user_id="user-1", action_type="newest", created_at="2026-03-01 00:00:00")
        _insert_action_row(db_path, user_id="user-1", action_type="middle", created_at="2026-02-01 00:00:00")

        results = service.get_civic_history("user-1")
        assert [r["action_type"] for r in results] == ["newest", "middle", "oldest"]

    def test_respects_limit(self, service, db_path):
        for i in range(10):
            _insert_action_row(
                db_path,
                user_id="user-1",
                action_type=f"a{i}",
                created_at=f"2026-01-{i + 1:02d} 00:00:00",
            )
        results = service.get_civic_history("user-1", limit=3)
        assert len(results) == 3
        # Should be the 3 most recent
        assert [r["action_type"] for r in results] == ["a9", "a8", "a7"]

    def test_default_limit_is_one_hundred(self, service, db_path):
        # Insert 150 rows and verify default limit caps at 100
        for i in range(150):
            _insert_action_row(
                db_path,
                user_id="user-1",
                action_type="bulk",
                action_id=str(uuid.uuid4()),
                created_at=f"2026-01-01 00:{i // 60:02d}:{i % 60:02d}",
            )
        results = service.get_civic_history("user-1")
        assert len(results) == 100

    def test_combined_filters(self, service, db_path):
        _insert_action_row(db_path, user_id="user-1", action_type="bill_viewed", created_at="2026-01-01 00:00:00")
        _insert_action_row(db_path, user_id="user-1", action_type="bill_viewed", created_at="2026-03-01 00:00:00")
        _insert_action_row(db_path, user_id="user-1", action_type="meeting_viewed", created_at="2026-03-01 00:00:00")

        results = service.get_civic_history(
            "user-1",
            action_types=["bill_viewed"],
            since=datetime(2026, 2, 1, 0, 0, 0),
        )
        assert len(results) == 1
        assert results[0]["action_type"] == "bill_viewed"
        assert results[0]["created_at"] == "2026-03-01 00:00:00"


# ---------------------------------------------------------------------------
# infer_civic_interests
# ---------------------------------------------------------------------------


class TestInferCivicInterests:
    def test_returns_empty_when_no_actions(self, service):
        assert service.infer_civic_interests("user-1") == {}

    def test_returns_empty_when_actions_have_no_topic(self, service, db_path):
        _insert_action_row(db_path, user_id="user-1", action_type="bill_viewed", metadata={"other": "x"})
        result = service.infer_civic_interests("user-1")
        assert result == {}

    def test_single_topic_normalizes_to_one(self, service, db_path):
        now = datetime.now()
        _insert_action_row(
            db_path,
            user_id="user-1",
            action_type="comment_drafted",
            topic="housing",
            created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        result = service.infer_civic_interests("user-1")
        assert result == {"housing": 1.0}

    def test_highest_weighted_topic_normalizes_to_one(self, service, db_path):
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        # comment_drafted weight=10, bill_viewed weight=4
        _insert_action_row(db_path, user_id="user-1", action_type="comment_drafted", topic="housing", created_at=ts)
        _insert_action_row(db_path, user_id="user-1", action_type="bill_viewed", topic="transit", created_at=ts)

        result = service.infer_civic_interests("user-1")
        assert result["housing"] == pytest.approx(1.0, abs=1e-6)
        # transit = 4 / 10 = 0.4 (with ~0 time decay since now)
        assert result["transit"] == pytest.approx(0.4, abs=1e-3)

    def test_time_decay_applied_with_thirty_day_half_life(self, service, db_path):
        """An action 30 days old should score exp(-1) ≈ 0.368 relative to a fresh one."""
        now = datetime.now()
        recent = now.strftime("%Y-%m-%d %H:%M:%S")
        old = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

        # Same weight (both meeting_viewed = 2), different ages
        _insert_action_row(db_path, user_id="user-1", action_type="meeting_viewed", topic="fresh", created_at=recent)
        _insert_action_row(db_path, user_id="user-1", action_type="meeting_viewed", topic="aged", created_at=old)

        result = service.infer_civic_interests("user-1")
        assert result["fresh"] == pytest.approx(1.0, abs=1e-6)
        # aged/fresh ratio ≈ exp(-30/30) = exp(-1) ≈ 0.3679
        assert result["aged"] == pytest.approx(math.exp(-1), abs=1e-3)

    def test_filters_topics_below_noise_threshold(self, service, db_path):
        """Topics with normalized score < 0.1 are dropped."""
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")

        # comment_drafted weight=10 for 'housing' → 10.0
        _insert_action_row(db_path, user_id="user-1", action_type="comment_drafted", topic="housing", created_at=ts)
        # event_clicked weight=2 × old(75 days) decay exp(-2.5)≈0.082 → ~0.164
        # That's > 0.1, still kept. So instead use a topic whose weight × decay < 1.0
        # Event_clicked weight=2, ~85 days old: exp(-85/30)≈0.059 → 2*0.059=0.118 → 0.0118 normalized. Dropped.
        old = (now - timedelta(days=85)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_action_row(db_path, user_id="user-1", action_type="event_clicked", topic="ephemeral", created_at=old)

        result = service.infer_civic_interests("user-1")
        assert "housing" in result
        assert "ephemeral" not in result

    def test_aggregates_multiple_actions_for_same_topic(self, service, db_path):
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        # Three comment_drafted for housing (weight=10 each) vs one comment_drafted for transit.
        for _ in range(3):
            _insert_action_row(
                db_path,
                user_id="user-1",
                action_type="comment_drafted",
                topic="housing",
                created_at=ts,
                action_id=str(uuid.uuid4()),
            )
        _insert_action_row(db_path, user_id="user-1", action_type="comment_drafted", topic="transit", created_at=ts)

        result = service.infer_civic_interests("user-1")
        # housing = 30, transit = 10, normalized: housing=1.0, transit=10/30≈0.333
        assert result["housing"] == pytest.approx(1.0, abs=1e-6)
        assert result["transit"] == pytest.approx(1 / 3, abs=1e-3)

    def test_only_considers_last_ninety_days(self, service, db_path):
        """Actions older than 90 days are excluded by the since filter."""
        now = datetime.now()
        recent_ts = now.strftime("%Y-%m-%d %H:%M:%S")
        ancient_ts = (now - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")

        _insert_action_row(db_path, user_id="user-1", action_type="comment_drafted", topic="recent_topic", created_at=recent_ts)
        _insert_action_row(db_path, user_id="user-1", action_type="comment_drafted", topic="old_topic", created_at=ancient_ts)

        result = service.infer_civic_interests("user-1")
        assert "recent_topic" in result
        assert "old_topic" not in result

    def test_unknown_action_type_gets_default_weight(self, service, db_path):
        """Unknown action types default to weight 1 (still contribute)."""
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        _insert_action_row(db_path, user_id="user-1", action_type="custom_mystery_action", topic="niche", created_at=ts)
        result = service.infer_civic_interests("user-1")
        # Single action → normalized to 1.0 regardless of its underlying weight
        assert result == {"niche": 1.0}


# ---------------------------------------------------------------------------
# get_context_for_ai
# ---------------------------------------------------------------------------


class TestGetContextForAi:
    def test_returns_empty_dict_when_user_missing(self, service):
        assert service.get_context_for_ai("ghost") == {}

    def test_demographics_only_includes_demographic_fields(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1")
        ctx = service.get_context_for_ai("user-1", context_type="demographics")
        assert ctx["stakes"] == ["homeowner", "parent"]
        assert ctx["yearsInArea"] == 7
        assert ctx["district"] == "District 3"
        assert ctx["neighborhood"] == "Sun Valley"
        assert ctx["expertise"] == "Urban planning"
        # Demographics context should NOT include interest or history keys
        assert "civicInterests" not in ctx
        assert "inferredInterests" not in ctx
        assert "recentActions" not in ctx

    def test_interests_only_includes_interest_fields(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1")
        # Add an action whose topic will be inferred
        now = datetime.now()
        _insert_action_row(
            db_path,
            user_id="user-1",
            action_type="comment_drafted",
            topic="housing",
            created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        )

        ctx = service.get_context_for_ai("user-1", context_type="interests")
        assert ctx["civicInterests"] == ["housing", "transit"]
        assert ctx["inferredInterests"] == {"housing": 1.0}
        assert "stakes" not in ctx
        assert "recentActions" not in ctx

    def test_history_only_includes_recent_actions(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1")
        _insert_action_row(
            db_path,
            user_id="user-1",
            action_type="bill_viewed",
            topic="housing",
            created_at="2026-03-01 10:00:00",
        )
        ctx = service.get_context_for_ai("user-1", context_type="history")
        assert "recentActions" in ctx
        assert len(ctx["recentActions"]) == 1
        assert ctx["recentActions"][0] == {
            "type": "bill_viewed",
            "topic": "housing",
            "date": "2026-03-01 10:00:00",
        }
        assert "stakes" not in ctx
        assert "civicInterests" not in ctx

    def test_history_caps_at_ten_recent_actions(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1")
        for i in range(15):
            _insert_action_row(
                db_path,
                user_id="user-1",
                action_type="bill_viewed",
                action_id=str(uuid.uuid4()),
                created_at=f"2026-01-{i + 1:02d} 00:00:00",
            )
        ctx = service.get_context_for_ai("user-1", context_type="history")
        assert len(ctx["recentActions"]) == 10

    def test_full_context_includes_all_sections(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1")
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        _insert_action_row(db_path, user_id="user-1", action_type="comment_drafted", topic="housing", created_at=ts)

        ctx = service.get_context_for_ai("user-1", context_type="full")
        # Demographics
        assert ctx["stakes"] == ["homeowner", "parent"]
        assert ctx["yearsInArea"] == 7
        assert ctx["district"] == "District 3"
        assert ctx["neighborhood"] == "Sun Valley"
        assert ctx["expertise"] == "Urban planning"
        # Interests
        assert ctx["civicInterests"] == ["housing", "transit"]
        assert ctx["inferredInterests"] == {"housing": 1.0}
        # History
        assert len(ctx["recentActions"]) == 1
        assert ctx["recentActions"][0]["type"] == "comment_drafted"
        assert ctx["recentActions"][0]["topic"] == "housing"

    def test_default_context_type_is_full(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1")
        ctx = service.get_context_for_ai("user-1")
        # Default is 'full' — all three section groups present
        assert "stakes" in ctx
        assert "civicInterests" in ctx
        assert "recentActions" in ctx

    def test_recent_action_without_topic_yields_none_topic(self, service, db_path):
        _insert_profile_row(db_path, user_id="user-1")
        _insert_action_row(
            db_path,
            user_id="user-1",
            action_type="bill_viewed",
            metadata=None,
            created_at="2026-03-01 10:00:00",
        )
        ctx = service.get_context_for_ai("user-1", context_type="history")
        assert ctx["recentActions"][0]["topic"] is None
        assert ctx["recentActions"][0]["type"] == "bill_viewed"

    def test_unknown_context_type_returns_empty_context(self, service, db_path):
        """Unknown context_type matches no branches, yielding an empty dict for a present user."""
        _insert_profile_row(db_path, user_id="user-1")
        ctx = service.get_context_for_ai("user-1", context_type="mystery")
        assert ctx == {}
