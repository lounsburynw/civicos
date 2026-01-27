"""
Notification dispatch for CivicOS monitoring.

Sends push notifications via ntfy (recommended) or legacy Slack webhooks.

ntfy is a simple, open-source, permissionless push notification service.
No account required. Install the app (iOS/Android), subscribe to your topic,
and receive native push notifications.

    https://ntfy.sh

Setup:
    1. Pick a topic name with some randomness: civicos-admin-<random>
    2. Subscribe in the ntfy app or browser
    3. Set CIVICOS_NTFY_TOPIC in .env or Modal secrets

Configuration (checked in priority order):
    CIVICOS_NTFY_TOPIC  - ntfy topic name (e.g., "civicos-admin-a7f3b2")
    CIVICOS_NTFY_URL    - ntfy server URL (default: https://ntfy.sh)
    CIVICOS_SLACK_WEBHOOK_URL - Legacy Slack webhook (still supported)

If neither is set, notifications are logged only.
"""

import json
import logging
import os
from enum import IntEnum
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Notification priority levels.

    Maps to ntfy priorities (1-5) and Slack message urgency.
    """

    MIN = 1
    LOW = 2
    DEFAULT = 3
    HIGH = 4
    URGENT = 5


def send_notification(
    title: str,
    body: str,
    priority: Priority = Priority.DEFAULT,
    tags: Optional[List[str]] = None,
    click_url: Optional[str] = None,
) -> bool:
    """Send a push notification via the configured backend.

    Tries ntfy first, then Slack, then logs only.

    Args:
        title: Notification title/header.
        body: Plain text message body.
        priority: Urgency level (affects phone notification behavior).
        tags: Optional tags (ntfy emoji shortcodes or labels).
        click_url: Optional URL to open when notification is tapped.

    Returns:
        True if notification was delivered to at least one backend.
    """
    ntfy_topic = os.environ.get("CIVICOS_NTFY_TOPIC", "")
    slack_url = os.environ.get("CIVICOS_SLACK_WEBHOOK_URL", "")

    if ntfy_topic:
        ntfy_server = os.environ.get("CIVICOS_NTFY_URL", "https://ntfy.sh")
        return _send_ntfy(ntfy_server, ntfy_topic, title, body, priority, tags, click_url)

    if slack_url:
        return _send_slack(slack_url, title, body, priority)

    logger.warning(f"Notification (no backend configured): {title}")
    logger.info(body)
    return False


def _send_ntfy(
    server: str,
    topic: str,
    title: str,
    body: str,
    priority: Priority,
    tags: Optional[List[str]],
    click_url: Optional[str],
) -> bool:
    """Send notification via ntfy HTTP API.

    ntfy uses HTTP headers for metadata and the request body for the message.
    See: https://docs.ntfy.sh/publish/
    """
    url = f"{server.rstrip('/')}/{topic}"

    headers = {
        "Title": title,
        "Priority": str(int(priority)),
    }

    if tags:
        headers["Tags"] = ",".join(tags)

    if click_url:
        headers["Click"] = click_url

    try:
        req = Request(
            url,
            data=body.encode("utf-8"),
            headers=headers,
        )
        with urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info(f"Notification sent via ntfy: {title}")
                return True
            else:
                logger.warning(f"ntfy returned status {response.status}")
                return False
    except HTTPError as e:
        logger.error(f"ntfy HTTP error: {e.code} - {e.reason}")
        return False
    except URLError as e:
        logger.error(f"ntfy URL error: {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Failed to send ntfy notification: {e}")
        return False


def _send_slack(
    webhook_url: str,
    title: str,
    body: str,
    priority: Priority,
) -> bool:
    """Send notification via Slack incoming webhook.

    Formats as simple Block Kit message (header + text section).
    Legacy support for existing Slack webhook configurations.
    """
    # Map priority to emoji prefix
    emoji = {
        Priority.URGENT: ":rotating_light:",
        Priority.HIGH: ":warning:",
        Priority.DEFAULT: ":information_source:",
        Priority.LOW: ":large_blue_circle:",
        Priority.MIN: ":white_circle:",
    }.get(priority, "")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {title}" if emoji else title,
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": body[:3000],  # Slack block text limit
            },
        },
    ]

    payload = {"blocks": blocks, "text": f"{title}\n{body[:200]}"}

    try:
        req = Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info(f"Notification sent via Slack: {title}")
                return True
            else:
                logger.warning(f"Slack webhook returned status {response.status}")
                return False
    except HTTPError as e:
        logger.error(f"Slack webhook HTTP error: {e.code} - {e.reason}")
        return False
    except URLError as e:
        logger.error(f"Slack webhook URL error: {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")
        return False
