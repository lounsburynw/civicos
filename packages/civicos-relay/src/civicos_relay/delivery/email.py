"""Email delivery for relay events."""

import logging
import os
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from civicos_relay.relay.models import Event, EventType, Subscription

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """Configuration for email delivery."""

    smtp_host: str
    smtp_port: int
    from_address: str
    username: Optional[str] = None
    password: Optional[str] = None
    use_tls: bool = True
    base_url: str = "https://civicos.app"

    @classmethod
    def from_env(cls) -> "EmailConfig":
        """Load configuration from environment variables."""
        return cls(
            smtp_host=os.environ.get("SMTP_HOST", "localhost"),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            from_address=os.environ.get("EMAIL_FROM_ADDRESS", "noreply@civicos.app"),
            username=os.environ.get("SMTP_USER"),
            password=os.environ.get("SMTP_PASSWORD"),
            use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
            base_url=os.environ.get("CIVICOS_BASE_URL", "https://civicos.app"),
        )


class EmailDelivery:
    """
    Delivers civic events via email.

    Implements the EventDelivery protocol from civicos_relay.relay.service.
    """

    def __init__(self, config: EmailConfig):
        """Initialize email delivery with SMTP configuration."""
        self._config = config

    def deliver(self, event: Event, subscription: Subscription) -> bool:
        """
        Deliver an event via email.

        Args:
            event: The civic event to deliver
            subscription: The subscription (contains email address)

        Returns:
            True if delivery succeeded, False otherwise
        """
        try:
            to_address = subscription.delivery.address
            subject = self._build_subject(event)
            html_body = self._build_html_body(event, subscription)
            text_body = self._build_text_body(event, subscription)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self._config.from_address
            msg["To"] = to_address

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            self._send_email(msg, to_address)
            logger.info(f"Email delivered to {to_address} for event {event.type.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to deliver email to {subscription.delivery.address}: {e}")
            return False

    def _send_email(self, msg: MIMEMultipart, to_address: str) -> None:
        """Send email via SMTP."""
        with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as server:
            if self._config.use_tls:
                server.starttls()
            if self._config.username and self._config.password:
                server.login(self._config.username, self._config.password)
            server.sendmail(self._config.from_address, to_address, msg.as_string())

    def _build_subject(self, event: Event) -> str:
        """Build email subject from event."""
        jurisdiction_name = self._format_jurisdiction(event.jurisdiction)
        title = event.data.get("title", "")

        subject_templates = {
            EventType.AGENDA_PUBLISHED: f"[{jurisdiction_name}] Agenda Published: {title}",
            EventType.DECISION_MADE: f"[{jurisdiction_name}] Decision Made: {title}",
            EventType.MEETING_SCHEDULED: f"[{jurisdiction_name}] Meeting Scheduled: {title}",
            EventType.PUBLIC_COMMENT_OPENED: f"[{jurisdiction_name}] Public Comment Open: {title}",
            EventType.PUBLIC_COMMENT_CLOSING: f"[{jurisdiction_name}] Public Comment Closing Soon: {title}",
            EventType.VOICE_THRESHOLD_REACHED: f"[{jurisdiction_name}] Voice Threshold Reached: {title}",
            EventType.INITIATIVE_CREATED: f"[{jurisdiction_name}] New Initiative: {title}",
        }

        return subject_templates.get(
            event.type,
            f"[{jurisdiction_name}] {event.type.value}: {title}"
        )

    def _build_html_body(self, event: Event, subscription: Subscription) -> str:
        """Build HTML email body."""
        jurisdiction_name = self._format_jurisdiction(event.jurisdiction)
        title = event.data.get("title", "Civic Event")
        description = event.data.get("description", "")
        topics = event.data.get("topics", [])
        timestamp = event.timestamp.strftime("%B %d, %Y at %I:%M %p UTC")
        unsubscribe_url = f"{self._config.base_url}/unsubscribe/{subscription.id}"

        # Event-specific content
        extra_content = self._get_event_specific_html(event)

        topics_html = ""
        if topics:
            topics_list = ", ".join(topics)
            topics_html = f'<p style="color: #666; font-size: 14px;">Topics: {topics_list}</p>'

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
        <h1 style="margin: 0 0 10px 0; font-size: 24px; color: #2c3e50;">{title}</h1>
        <p style="margin: 0; color: #666; font-size: 14px;">
            {self._get_event_type_label(event.type)} in {jurisdiction_name}
        </p>
    </div>

    {f'<p style="margin-bottom: 20px;">{description}</p>' if description else ''}

    {extra_content}

    {topics_html}

    <div style="background: #e9ecef; border-radius: 4px; padding: 15px; margin: 20px 0;">
        <p style="margin: 0; font-size: 12px; color: #666;">
            <strong>Event Time:</strong> {timestamp}<br>
            <strong>Entity:</strong> {event.entity}
        </p>
    </div>

    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

    <p style="font-size: 12px; color: #999; margin: 0;">
        You're receiving this because you subscribed to updates for {jurisdiction_name}.
        <a href="{unsubscribe_url}" style="color: #999;">Unsubscribe</a>
    </p>

    <p style="font-size: 12px; color: #999; margin-top: 10px;">
        Powered by <a href="https://civicos.app" style="color: #666;">CivicOS</a>
    </p>
</body>
</html>"""

    def _build_text_body(self, event: Event, subscription: Subscription) -> str:
        """Build plain text email body."""
        jurisdiction_name = self._format_jurisdiction(event.jurisdiction)
        title = event.data.get("title", "Civic Event")
        description = event.data.get("description", "")
        topics = event.data.get("topics", [])
        timestamp = event.timestamp.strftime("%B %d, %Y at %I:%M %p UTC")
        unsubscribe_url = f"{self._config.base_url}/unsubscribe/{subscription.id}"

        extra_content = self._get_event_specific_text(event)

        lines = [
            f"{title}",
            f"{self._get_event_type_label(event.type)} in {jurisdiction_name}",
            "",
        ]

        if description:
            lines.extend([description, ""])

        if extra_content:
            lines.extend([extra_content, ""])

        if topics:
            lines.append(f"Topics: {', '.join(topics)}")
            lines.append("")

        lines.extend([
            f"Event Time: {timestamp}",
            f"Entity: {event.entity}",
            "",
            "---",
            "",
            f"You're receiving this because you subscribed to updates for {jurisdiction_name}.",
            f"Unsubscribe: {unsubscribe_url}",
            "",
            "Powered by CivicOS - https://civicos.app",
        ])

        return "\n".join(lines)

    def _get_event_type_label(self, event_type: EventType) -> str:
        """Get human-readable label for event type."""
        labels = {
            EventType.AGENDA_PUBLISHED: "Agenda Published",
            EventType.DECISION_MADE: "Decision Made",
            EventType.MEETING_SCHEDULED: "Meeting Scheduled",
            EventType.PUBLIC_COMMENT_OPENED: "Public Comment Period Opened",
            EventType.PUBLIC_COMMENT_CLOSING: "Public Comment Period Closing",
            EventType.VOICE_THRESHOLD_REACHED: "Voice Threshold Reached",
            EventType.INITIATIVE_CREATED: "New Initiative Created",
        }
        return labels.get(event_type, event_type.value)

    def _get_event_specific_html(self, event: Event) -> str:
        """Get event-type-specific HTML content."""
        data = event.data

        if event.type == EventType.MEETING_SCHEDULED:
            meeting_date = data.get("meeting_date", "")
            if meeting_date:
                return f'<p style="font-weight: bold;">Meeting Date: {meeting_date}</p>'

        elif event.type == EventType.PUBLIC_COMMENT_OPENED:
            deadline = data.get("deadline", "")
            if deadline:
                return f'<p style="color: #c0392b; font-weight: bold;">Deadline for Comments: {deadline}</p>'

        elif event.type == EventType.PUBLIC_COMMENT_CLOSING:
            deadline = data.get("deadline", "")
            if deadline:
                return f'<p style="color: #c0392b; font-weight: bold;">Comment Period Ends: {deadline}</p>'

        elif event.type == EventType.VOICE_THRESHOLD_REACHED:
            voice_count = data.get("voice_count", 0)
            threshold = data.get("threshold", 0)
            return f'<p style="font-weight: bold;">Voices: {voice_count} (threshold: {threshold})</p>'

        return ""

    def _get_event_specific_text(self, event: Event) -> str:
        """Get event-type-specific plain text content."""
        data = event.data

        if event.type == EventType.MEETING_SCHEDULED:
            meeting_date = data.get("meeting_date", "")
            if meeting_date:
                return f"Meeting Date: {meeting_date}"

        elif event.type in (EventType.PUBLIC_COMMENT_OPENED, EventType.PUBLIC_COMMENT_CLOSING):
            deadline = data.get("deadline", "")
            if deadline:
                label = "Deadline for Comments" if event.type == EventType.PUBLIC_COMMENT_OPENED else "Comment Period Ends"
                return f"{label}: {deadline}"

        elif event.type == EventType.VOICE_THRESHOLD_REACHED:
            voice_count = data.get("voice_count", 0)
            threshold = data.get("threshold", 0)
            return f"Voices: {voice_count} (threshold: {threshold})"

        return ""

    def _format_jurisdiction(self, jurisdiction: str) -> str:
        """Format jurisdiction ID to readable name."""
        # Convert "city-san-rafael" to "San Rafael"
        if jurisdiction.startswith("city-"):
            name = jurisdiction[5:]  # Remove "city-" prefix
            return " ".join(word.title() for word in name.split("-"))
        return jurisdiction.replace("-", " ").title()
