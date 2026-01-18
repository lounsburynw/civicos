"""
Tests for action modules.

Tests initiatives, voices, subscriptions, and preparation modules.
"""

import pytest
import tempfile
import os


class TestInitiativesModule:
    """Test initiatives.py (start_something)."""

    def test_start_initiative_import(self):
        """Can import start_initiative."""
        from civicos.actions.initiatives import start_initiative, Initiative
        assert callable(start_initiative)

    def test_start_initiative_creates_initiative(self):
        """start_initiative creates and persists initiative."""
        from civicos.actions.initiatives import start_initiative, Initiative

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="traffic",
                title="Protected bike lane on 4th St",
                description="Near-misses every week at this intersection",
                creator_id="user_123",
                location="4th St & B St",
                db_path=db_path,
            )

            assert isinstance(initiative, Initiative)
            assert initiative.id.startswith("init_")
            assert initiative.topic == "traffic"
            assert initiative.title == "Protected bike lane on 4th St"
            assert initiative.description == "Near-misses every week at this intersection"
            assert initiative.creator_id == "user_123"
            assert initiative.jurisdiction == "san-rafael-ca"
            assert initiative.location == "4th St & B St"
            assert initiative.status == "active"

    def test_start_initiative_default_creator(self):
        """start_initiative uses anonymous as default creator."""
        from civicos.actions.initiatives import start_initiative

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="housing",
                title="Affordable housing downtown",
                description="We need more affordable units",
                db_path=db_path,
            )

            assert initiative.creator_id == "anonymous"

    def test_start_initiative_persists_to_database(self):
        """start_initiative persists initiative to database."""
        from civicos.actions.initiatives import start_initiative
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="traffic",
                title="Protected bike lane",
                description="Near-misses every week",
                db_path=db_path,
            )

            # Verify persisted
            state = StateManager(db_path)
            result = state.get_initiative(initiative.id)

            assert result is not None
            assert result["id"] == initiative.id
            assert result["topic"] == "traffic"
            assert result["title"] == "Protected bike lane"


class TestVoicesModule:
    """Test voices.py (add_voice)."""

    def test_add_voice_import(self):
        """Can import add_voice."""
        from civicos.actions.voices import add_voice, Voice
        assert callable(add_voice)

    def test_add_voice_validates_stance(self):
        """add_voice validates stance parameter."""
        from civicos.actions.voices import add_voice
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            with pytest.raises(ValueError):
                add_voice("agenda_item", "item_123", "invalid_stance", "Comment", db_path=db_path)

    def test_add_voice_validates_item_type(self):
        """add_voice validates item_type parameter."""
        from civicos.actions.voices import add_voice
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            with pytest.raises(ValueError):
                add_voice("invalid_type", "item_123", "support", "Comment", db_path=db_path)

    def test_add_voice_creates_voice(self):
        """add_voice creates and persists voice."""
        from civicos.actions.voices import add_voice, Voice

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            voice = add_voice(
                item_type="initiative",
                item_id="init_abc123",
                stance="support",
                comment="This is a great idea!",
                user_id="user_456",
                db_path=db_path,
            )

            assert isinstance(voice, Voice)
            assert voice.id.startswith("voice_")
            assert voice.item_type == "initiative"
            assert voice.item_id == "init_abc123"
            assert voice.stance == "support"
            assert voice.comment == "This is a great idea!"
            assert voice.user_id == "user_456"

    def test_add_voice_default_user(self):
        """add_voice uses anonymous as default user."""
        from civicos.actions.voices import add_voice

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            voice = add_voice(
                item_type="agenda_item",
                item_id="item_789",
                stance="oppose",
                comment="I have concerns about this.",
                db_path=db_path,
            )

            assert voice.user_id == "anonymous"

    def test_add_voice_persists_to_database(self):
        """add_voice persists voice to database."""
        from civicos.actions.voices import add_voice
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            voice = add_voice(
                item_type="decision",
                item_id="dec_123",
                stance="question",
                comment="Can you clarify the timeline?",
                db_path=db_path,
            )

            # Verify persisted
            state = StateManager(db_path)
            result = state.get_voice(voice.id)

            assert result is not None
            assert result["id"] == voice.id
            assert result["item_type"] == "decision"
            assert result["stance"] == "question"
            assert result["comment"] == "Can you clarify the timeline?"

    def test_add_voice_all_stances(self):
        """add_voice accepts all valid stances."""
        from civicos.actions.voices import add_voice

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            for stance in ["support", "oppose", "question"]:
                voice = add_voice(
                    item_type="initiative",
                    item_id="init_test",
                    stance=stance,
                    comment=f"Testing {stance}",
                    db_path=db_path,
                )
                assert voice.stance == stance

    def test_add_voice_all_item_types(self):
        """add_voice accepts all valid item types."""
        from civicos.actions.voices import add_voice

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            for item_type in ["initiative", "agenda_item", "decision"]:
                voice = add_voice(
                    item_type=item_type,
                    item_id=f"{item_type}_123",
                    stance="support",
                    comment=f"Testing {item_type}",
                    db_path=db_path,
                )
                assert voice.item_type == item_type


class TestSubscriptionsModule:
    """Test subscriptions.py (follow)."""

    def test_follow_item_import(self):
        """Can import follow_item."""
        from civicos.actions.subscriptions import follow_item, Subscription
        assert callable(follow_item)

    def test_follow_item_validates_item_type(self):
        """follow_item validates item_type parameter."""
        from civicos.actions.subscriptions import follow_item
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            with pytest.raises(ValueError):
                follow_item("invalid_type", "item_123", db_path=db_path)

    def test_follow_item_creates_subscription(self):
        """follow_item creates and persists subscription."""
        from civicos.actions.subscriptions import follow_item, Subscription

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            sub = follow_item(
                item_type="meeting",
                item_id="mtg_abc123",
                user_id="user_789",
                db_path=db_path,
            )

            assert isinstance(sub, Subscription)
            assert sub.id.startswith("sub_")
            assert sub.item_type == "meeting"
            assert sub.item_id == "mtg_abc123"
            assert sub.user_id == "user_789"

    def test_follow_item_default_user(self):
        """follow_item uses anonymous as default user."""
        from civicos.actions.subscriptions import follow_item

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            sub = follow_item(
                item_type="initiative",
                item_id="init_456",
                db_path=db_path,
            )

            assert sub.user_id == "anonymous"

    def test_follow_item_persists_to_database(self):
        """follow_item persists subscription to database."""
        from civicos.actions.subscriptions import follow_item
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            sub = follow_item(
                item_type="topic",
                item_id="housing",
                user_id="user_123",
                db_path=db_path,
            )

            # Verify persisted
            state = StateManager(db_path)
            result = state.get_subscription(sub.id)

            assert result is not None
            assert result["id"] == sub.id
            assert result["item_type"] == "topic"
            assert result["item_id"] == "housing"
            assert result["user_id"] == "user_123"

    def test_follow_item_all_item_types(self):
        """follow_item accepts all valid item types."""
        from civicos.actions.subscriptions import follow_item

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            for item_type in ["meeting", "initiative", "topic", "decision"]:
                sub = follow_item(
                    item_type=item_type,
                    item_id=f"{item_type}_123",
                    db_path=db_path,
                )
                assert sub.item_type == item_type

    def test_follow_item_with_notification_prefs(self):
        """follow_item stores notification preferences."""
        from civicos.actions.subscriptions import follow_item

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            prefs = {"email": True, "sms": False}
            sub = follow_item(
                item_type="meeting",
                item_id="mtg_xyz",
                notification_prefs=prefs,
                db_path=db_path,
            )

            assert sub.notification_prefs == prefs

    def test_unfollow_item(self):
        """unfollow_item removes subscription."""
        from civicos.actions.subscriptions import follow_item, unfollow_item
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Create subscription
            sub = follow_item(
                item_type="meeting",
                item_id="mtg_to_unfollow",
                db_path=db_path,
            )

            # Verify exists
            state = StateManager(db_path)
            assert state.get_subscription(sub.id) is not None

            # Unfollow
            result = unfollow_item(sub.id, db_path=db_path)
            assert result is True

            # Verify deleted
            assert state.get_subscription(sub.id) is None

    def test_unfollow_nonexistent(self):
        """unfollow_item returns False for nonexistent subscription."""
        from civicos.actions.subscriptions import unfollow_item

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            result = unfollow_item("sub_nonexistent", db_path=db_path)
            assert result is False


class TestPreparationModule:
    """Test preparation.py (prepare)."""

    def test_prepare_for_meeting_import(self):
        """Can import prepare_for_meeting."""
        from civicos.actions.preparation import prepare_for_meeting, Preparation
        assert callable(prepare_for_meeting)

    def test_prepare_for_meeting_agenda_item_not_found(self):
        """prepare_for_meeting raises ValueError for unknown agenda item."""
        from civicos.actions.preparation import prepare_for_meeting
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            with pytest.raises(ValueError, match="not found"):
                prepare_for_meeting("item_nonexistent", "san-rafael-ca", db_path=db_path)

    def test_prepare_for_meeting_with_agenda_item(self):
        """prepare_for_meeting returns Preparation for valid agenda item."""
        from civicos.actions.preparation import prepare_for_meeting, Preparation
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            state = StateManager(db_path)

            # Create a meeting with an agenda item
            state.update_meetings("san-rafael-ca", [{
                "id": "mtg_001",
                "title": "City Council Meeting",
                "meeting_datetime": "2025-12-15T18:00:00",
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "item_001",
                        "title": "Housing Development Proposal",
                        "project_type": "housing",
                    }]
                }
            }])

            result = prepare_for_meeting("item_001", "san-rafael-ca", db_path=db_path)

            assert isinstance(result, Preparation)
            assert result.agenda_item_id == "item_001"
            assert isinstance(result.regulatory_context, dict)
            assert isinstance(result.talking_points, list)
            assert len(result.talking_points) > 0
            assert isinstance(result.logistics, dict)
            assert result.logistics.get("meeting_title") == "City Council Meeting"

    def test_prepare_generates_talking_points(self):
        """prepare_for_meeting generates relevant talking points."""
        from civicos.actions.preparation import prepare_for_meeting
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            state = StateManager(db_path)

            state.update_meetings("city-berkeley", [{
                "id": "mtg_002",
                "title": "Planning Commission",
                "meeting_datetime": "2025-12-20T19:00:00",
                "meeting_type": "Planning",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "item_002",
                        "title": "Transit Oriented Development",
                    }]
                }
            }])

            result = prepare_for_meeting("item_002", "city-berkeley", db_path=db_path)

            # Should have talking points
            assert len(result.talking_points) >= 2
            # First point should reference the item title
            assert "Transit Oriented Development" in result.talking_points[0]

    def test_prepare_compiles_logistics(self):
        """prepare_for_meeting compiles meeting logistics."""
        from civicos.actions.preparation import prepare_for_meeting
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            state = StateManager(db_path)

            state.update_meetings("san-rafael-ca", [{
                "id": "mtg_003",
                "title": "City Council",
                "meeting_datetime": "2025-12-18T18:30:00",
                "meeting_type": "City Council",
                "location": "1400 Fifth Ave, City Hall",
                "virtual_url": "https://zoom.us/j/12345",
                "agenda_url": "https://city.gov/agenda.pdf",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "item_003",
                        "title": "Budget Amendment",
                    }]
                }
            }])

            result = prepare_for_meeting("item_003", "san-rafael-ca", db_path=db_path)

            assert result.logistics["location"] == "1400 Fifth Ave, City Hall"
            assert result.logistics["virtual_url"] == "https://zoom.us/j/12345"
            assert result.logistics["agenda_url"] == "https://city.gov/agenda.pdf"
            assert "tips" in result.logistics
            # City Council meeting should have specific tips
            assert any("sign up" in tip.lower() for tip in result.logistics["tips"])

    def test_prepare_finds_allies(self):
        """prepare_for_meeting finds allies who have voiced on the item."""
        from civicos.actions.preparation import prepare_for_meeting
        from civicos._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            state = StateManager(db_path)

            # Create meeting with agenda item
            state.update_meetings("san-rafael-ca", [{
                "id": "mtg_004",
                "title": "City Council",
                "meeting_datetime": "2025-12-22T18:00:00",
                "meeting_type": "City Council",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "item_004",
                        "title": "Climate Action Plan",
                    }]
                }
            }])

            # Add some voices on the agenda item
            state.create_voice("voice_001", "agenda_item", "item_004", "support", "I support this!", "user_alice")
            state.create_voice("voice_002", "agenda_item", "item_004", "support", "Great plan!", "user_bob")

            result = prepare_for_meeting("item_004", "san-rafael-ca", db_path=db_path)

            # Should find the allies
            assert len(result.allies) >= 2
            ally_users = [a["user_id"] for a in result.allies]
            assert "user_alice" in ally_users
            assert "user_bob" in ally_users

    def test_prepare_extracts_topic_from_title(self):
        """prepare_for_meeting extracts topic from agenda item title."""
        from civicos.actions.preparation import _extract_topic_from_item

        # Housing keywords
        assert _extract_topic_from_item({"title": "Affordable Housing Project"}) == "housing"
        assert _extract_topic_from_item({"title": "Zoning Amendment"}) == "housing"

        # Transportation keywords
        assert _extract_topic_from_item({"title": "Bike Lane Installation"}) == "transportation"
        assert _extract_topic_from_item({"title": "Traffic Calming Study"}) == "transportation"

        # Environment keywords
        assert _extract_topic_from_item({"title": "Climate Action Plan"}) == "environment"

        # Uses project_type if available
        assert _extract_topic_from_item({"title": "Some Item", "project_type": "education"}) == "education"

        # Falls back to general
        assert _extract_topic_from_item({"title": "Miscellaneous Business"}) == "general"
