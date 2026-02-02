"""Tests for email delivery service."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from civicos_relay.delivery.email import EmailDelivery, EmailConfig
from civicos_relay.relay.models import (
    Event,
    EventType,
    Subscription,
    MatchCriteria,
    DeliveryConfig,
    DeliveryMethod,
)


@pytest.fixture
def email_config():
    """Create test email configuration."""
    return EmailConfig(
        smtp_host="localhost",
        smtp_port=587,
        from_address="test@civicos.app",
        username=None,
        password=None,
        use_tls=False,
        base_url="https://test.civicos.app",
    )


@pytest.fixture
def email_delivery(email_config):
    """Create email delivery instance."""
    return EmailDelivery(email_config)


@pytest.fixture
def sample_event():
    """Create a sample decision event."""
    return Event(
        type=EventType.DECISION_MADE,
        jurisdiction="city-san-rafael",
        entity="city-san-rafael:decision:2026-01-15:123",
        timestamp=datetime(2026, 1, 15, 14, 30, 0),
        data={
            "title": "Approved ADU Development",
            "description": "City council approved new ADU guidelines.",
            "topics": ["housing", "zoning"],
        },
    )


@pytest.fixture
def sample_subscription():
    """Create a sample subscription."""
    return Subscription(
        id="sub_abc123",
        jurisdiction="city-san-rafael",
        match=MatchCriteria(topics=["housing"]),
        delivery=DeliveryConfig(
            method=DeliveryMethod.EMAIL,
            address="user@example.com",
        ),
    )


class TestEmailDelivery:
    """Tests for EmailDelivery class."""

    def test_deliver_success(self, email_delivery, sample_event, sample_subscription):
        """Successful delivery returns True."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = email_delivery.deliver(sample_event, sample_subscription)

            assert result is True
            mock_server.sendmail.assert_called_once()

    def test_deliver_failure_returns_false(self, email_delivery, sample_event, sample_subscription):
        """Failed delivery returns False."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.side_effect = Exception("SMTP error")

            result = email_delivery.deliver(sample_event, sample_subscription)

            assert result is False

    def test_email_sent_to_correct_address(self, email_delivery, sample_event, sample_subscription):
        """Email is sent to the subscription address."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            email_delivery.deliver(sample_event, sample_subscription)

            call_args = mock_server.sendmail.call_args
            from_addr, to_addr, _ = call_args[0]
            assert to_addr == "user@example.com"
            assert from_addr == "test@civicos.app"

    def test_email_contains_event_title(self, email_delivery, sample_event, sample_subscription):
        """Email body contains the event title."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            email_delivery.deliver(sample_event, sample_subscription)

            call_args = mock_server.sendmail.call_args
            _, _, message = call_args[0]
            assert "Approved ADU Development" in message

    def test_email_contains_jurisdiction(self, email_delivery, sample_event, sample_subscription):
        """Email body contains the jurisdiction name."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            email_delivery.deliver(sample_event, sample_subscription)

            call_args = mock_server.sendmail.call_args
            _, _, message = call_args[0]
            assert "San Rafael" in message

    def test_email_contains_unsubscribe_link(self, email_delivery, sample_event, sample_subscription):
        """Email contains unsubscribe link with subscription ID."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            email_delivery.deliver(sample_event, sample_subscription)

            call_args = mock_server.sendmail.call_args
            _, _, message = call_args[0]
            assert "unsubscribe/sub_abc123" in message

    def test_email_contains_topics(self, email_delivery, sample_event, sample_subscription):
        """Email body contains the topics."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            email_delivery.deliver(sample_event, sample_subscription)

            call_args = mock_server.sendmail.call_args
            _, _, message = call_args[0]
            assert "housing" in message


class TestEmailSubjects:
    """Tests for email subject generation."""

    def test_decision_made_subject(self, email_delivery, sample_subscription):
        """Decision events have correct subject."""
        event = Event(
            type=EventType.DECISION_MADE,
            jurisdiction="city-san-rafael",
            entity="test",
            data={"title": "Test Decision"},
        )

        subject = email_delivery._build_subject(event)

        assert "[San Rafael]" in subject
        assert "Decision Made" in subject
        assert "Test Decision" in subject

    def test_agenda_published_subject(self, email_delivery, sample_subscription):
        """Agenda events have correct subject."""
        event = Event(
            type=EventType.AGENDA_PUBLISHED,
            jurisdiction="city-san-rafael",
            entity="test",
            data={"title": "Council Meeting"},
        )

        subject = email_delivery._build_subject(event)

        assert "Agenda Published" in subject
        assert "Council Meeting" in subject

    def test_meeting_scheduled_subject(self, email_delivery, sample_subscription):
        """Meeting events have correct subject."""
        event = Event(
            type=EventType.MEETING_SCHEDULED,
            jurisdiction="city-san-rafael",
            entity="test",
            data={"title": "Planning Commission"},
        )

        subject = email_delivery._build_subject(event)

        assert "Meeting Scheduled" in subject

    def test_public_comment_opened_subject(self, email_delivery, sample_subscription):
        """Public comment opened events have correct subject."""
        event = Event(
            type=EventType.PUBLIC_COMMENT_OPENED,
            jurisdiction="city-san-rafael",
            entity="test",
            data={"title": "Zoning Amendment"},
        )

        subject = email_delivery._build_subject(event)

        assert "Public Comment Open" in subject

    def test_public_comment_closing_subject(self, email_delivery, sample_subscription):
        """Public comment closing events have correct subject."""
        event = Event(
            type=EventType.PUBLIC_COMMENT_CLOSING,
            jurisdiction="city-san-rafael",
            entity="test",
            data={"title": "Zoning Amendment"},
        )

        subject = email_delivery._build_subject(event)

        assert "Closing Soon" in subject

    def test_voice_threshold_subject(self, email_delivery, sample_subscription):
        """Voice threshold events have correct subject."""
        event = Event(
            type=EventType.VOICE_THRESHOLD_REACHED,
            jurisdiction="city-san-rafael",
            entity="test",
            data={"title": "Crosswalk Initiative"},
        )

        subject = email_delivery._build_subject(event)

        assert "Voice Threshold Reached" in subject

    def test_initiative_created_subject(self, email_delivery, sample_subscription):
        """Initiative created events have correct subject."""
        event = Event(
            type=EventType.INITIATIVE_CREATED,
            jurisdiction="city-san-rafael",
            entity="test",
            data={"title": "New Crosswalk"},
        )

        subject = email_delivery._build_subject(event)

        assert "New Initiative" in subject


class TestEventSpecificContent:
    """Tests for event-type-specific email content."""

    def test_voice_threshold_shows_counts(self, email_delivery, sample_subscription):
        """Voice threshold events show voice count and threshold."""
        event = Event(
            type=EventType.VOICE_THRESHOLD_REACHED,
            jurisdiction="city-san-rafael",
            entity="test",
            data={
                "title": "Crosswalk Initiative",
                "voice_count": 100,
                "threshold": 100,
            },
        )

        html = email_delivery._build_html_body(event, sample_subscription)

        assert "100" in html
        assert "threshold" in html.lower()

    def test_public_comment_shows_deadline(self, email_delivery, sample_subscription):
        """Public comment events show deadline."""
        event = Event(
            type=EventType.PUBLIC_COMMENT_OPENED,
            jurisdiction="city-san-rafael",
            entity="test",
            data={
                "title": "Zoning Amendment",
                "deadline": "February 10, 2026",
            },
        )

        html = email_delivery._build_html_body(event, sample_subscription)

        assert "February 10, 2026" in html

    def test_meeting_shows_date(self, email_delivery, sample_subscription):
        """Meeting events show meeting date."""
        event = Event(
            type=EventType.MEETING_SCHEDULED,
            jurisdiction="city-san-rafael",
            entity="test",
            data={
                "title": "Planning Commission",
                "meeting_date": "February 10, 2026 at 6:30 PM",
            },
        )

        html = email_delivery._build_html_body(event, sample_subscription)

        assert "February 10, 2026" in html


class TestEmailConfig:
    """Tests for EmailConfig."""

    def test_from_env_defaults(self):
        """Config loads defaults when env vars not set."""
        with patch.dict("os.environ", {}, clear=True):
            config = EmailConfig.from_env()

            assert config.smtp_host == "localhost"
            assert config.smtp_port == 587
            assert config.from_address == "noreply@civicos.app"
            assert config.use_tls is True

    def test_from_env_custom(self):
        """Config loads custom values from env vars."""
        env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "465",
            "EMAIL_FROM_ADDRESS": "civic@example.com",
            "SMTP_USER": "user",
            "SMTP_PASSWORD": "pass",
            "SMTP_USE_TLS": "false",
            "CIVICOS_BASE_URL": "https://example.com",
        }
        with patch.dict("os.environ", env, clear=True):
            config = EmailConfig.from_env()

            assert config.smtp_host == "smtp.example.com"
            assert config.smtp_port == 465
            assert config.from_address == "civic@example.com"
            assert config.username == "user"
            assert config.password == "pass"
            assert config.use_tls is False
            assert config.base_url == "https://example.com"


class TestJurisdictionFormatting:
    """Tests for jurisdiction name formatting."""

    def test_city_prefix_removed(self, email_delivery):
        """City prefix is removed and name is title-cased."""
        result = email_delivery._format_jurisdiction("city-san-rafael")
        assert result == "San Rafael"

    def test_multi_word_city(self, email_delivery):
        """Multi-word city names are formatted correctly."""
        result = email_delivery._format_jurisdiction("city-palo-alto")
        assert result == "Palo Alto"

    def test_no_prefix(self, email_delivery):
        """Jurisdictions without city prefix are handled."""
        result = email_delivery._format_jurisdiction("marin-county")
        assert result == "Marin County"


class TestSMTPAuthentication:
    """Tests for SMTP authentication."""

    def test_tls_enabled(self, sample_event, sample_subscription):
        """TLS is started when enabled."""
        config = EmailConfig(
            smtp_host="localhost",
            smtp_port=587,
            from_address="test@civicos.app",
            use_tls=True,
        )
        delivery = EmailDelivery(config)

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            delivery.deliver(sample_event, sample_subscription)

            mock_server.starttls.assert_called_once()

    def test_login_with_credentials(self, sample_event, sample_subscription):
        """Login is called when credentials are provided."""
        config = EmailConfig(
            smtp_host="localhost",
            smtp_port=587,
            from_address="test@civicos.app",
            username="user",
            password="pass",
            use_tls=False,
        )
        delivery = EmailDelivery(config)

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            delivery.deliver(sample_event, sample_subscription)

            mock_server.login.assert_called_once_with("user", "pass")

    def test_no_login_without_credentials(self, email_delivery, sample_event, sample_subscription):
        """Login is not called when credentials are not provided."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            email_delivery.deliver(sample_event, sample_subscription)

            mock_server.login.assert_not_called()
