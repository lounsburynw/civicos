"""
Daily cost digest for Civic platform operating costs.

Sends a scheduled email summarizing daily operating costs vs budget.
Designed to run at 00:05 UTC daily via GitHub Actions or Modal cron.

Features:
- Daily cost summary with service/category breakdown
- Trend comparison (vs yesterday, 7-day average)
- Budget threshold warnings ($5/day, $50/month)
- HTML and plaintext email support
- Slack webhook fallback

Usage:
    from civic_services.monitoring.daily_cost_digest import (
        DailyCostDigest,
        send_daily_digest,
    )

    # Send digest for today
    digest = DailyCostDigest()
    result = digest.send()

    # Or use convenience function
    result = send_daily_digest()

Environment variables:
    CIVIC_ALERT_EMAILS      - Comma-separated recipient list
    CIVIC_SMTP_SERVER       - SMTP server (default: smtp.gmail.com)
    CIVIC_SMTP_PORT         - SMTP port (default: 587)
    CIVIC_SMTP_USERNAME     - SMTP username
    CIVIC_SMTP_PASSWORD     - SMTP password
    CIVIC_SLACK_WEBHOOK_URL - Slack webhook for fallback
    CIVIC_COST_DIGEST_ENABLED - Set to "false" to disable (default: true)
    CIVIC_DAILY_BUDGET      - Daily budget threshold (default: 5.0)
    CIVIC_MONTHLY_BUDGET    - Monthly budget threshold (default: 50.0)

Session 512: Initial daily cost digest implementation
"""

import json
import logging
import os
import smtplib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


@dataclass
class CostDigestData:
    """Daily cost digest data structure."""
    date: str
    total_cost_usd: float
    by_service: Dict[str, float]
    by_category: Dict[str, float]
    record_count: int
    yesterday_cost_usd: float
    weekly_avg_usd: float
    daily_budget: float
    monthly_budget: float
    monthly_total_usd: float
    budget_status: str  # "healthy", "warning", "critical"
    trend: str  # "up", "down", "flat"
    trend_percent: float


class DailyCostDigest:
    """
    Generates and sends daily cost digest emails.

    Uses Civic API to fetch operating cost data and compares against
    budget thresholds. Sends via SMTP with Slack webhook fallback.
    """

    def __init__(
        self,
        jurisdiction_id: str = "city-san-rafael",
        daily_budget: Optional[float] = None,
        monthly_budget: Optional[float] = None,
    ):
        """
        Initialize digest generator.

        Args:
            jurisdiction_id: Jurisdiction to report on
            daily_budget: Daily budget threshold (env: CIVIC_DAILY_BUDGET)
            monthly_budget: Monthly budget threshold (env: CIVIC_MONTHLY_BUDGET)
        """
        self.jurisdiction_id = jurisdiction_id
        self.daily_budget = daily_budget or float(os.getenv("CIVIC_DAILY_BUDGET", "5.0"))
        self.monthly_budget = monthly_budget or float(os.getenv("CIVIC_MONTHLY_BUDGET", "50.0"))

        # Email configuration
        self.alert_emails = os.getenv("CIVIC_ALERT_EMAILS", "").split(",")
        self.alert_emails = [e.strip() for e in self.alert_emails if e.strip()]
        self.smtp_server = os.getenv("CIVIC_SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("CIVIC_SMTP_PORT", "587"))
        self.smtp_username = os.getenv("CIVIC_SMTP_USERNAME", "")
        self.smtp_password = os.getenv("CIVIC_SMTP_PASSWORD", "")

        # Slack configuration
        self.slack_webhook_url = os.getenv("CIVIC_SLACK_WEBHOOK_URL", "")

        # Enabled check
        self.enabled = os.getenv("CIVIC_COST_DIGEST_ENABLED", "true").lower() != "false"

    def collect_data(self) -> CostDigestData:
        """
        Collect cost data from Civic API.

        Returns:
            CostDigestData with today's costs and comparisons
        """
        from dotenv import load_dotenv
        load_dotenv()

        from civic import Civic

        c = Civic(self.jurisdiction_id)

        # Get today's costs
        today_data = c.get_operating_cost_dashboard(period="day")
        today_summary = today_data.get("summary", {})

        # Get weekly data for comparison
        week_data = c.get_operating_cost_dashboard(period="week")
        time_series = week_data.get("time_series", [])

        # Get monthly total
        month_data = c.get_operating_cost_dashboard(period="month")
        monthly_total = month_data.get("summary", {}).get("total_cost_usd", 0)

        # Calculate yesterday's cost and weekly average
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday_cost = 0.0
        week_costs = []

        for day in time_series:
            date = day.get("date", "")
            cost = day.get("total_usd", 0)
            if date and date != today_str:
                week_costs.append(cost)
                # Yesterday is the most recent non-today entry
                if len(week_costs) >= 1:
                    yesterday_cost = week_costs[-1] if week_costs else 0

        # If we have yesterday in the list, it's the last entry before today
        if time_series:
            for day in reversed(time_series):
                if day.get("date") != today_str:
                    yesterday_cost = day.get("total_usd", 0)
                    break

        weekly_avg = sum(week_costs) / max(len(week_costs), 1) if week_costs else 0

        # Current totals
        total_cost = today_summary.get("total_cost_usd", 0)

        # Calculate trend
        if yesterday_cost > 0:
            trend_percent = ((total_cost - yesterday_cost) / yesterday_cost) * 100
        else:
            trend_percent = 0

        if trend_percent > 10:
            trend = "up"
        elif trend_percent < -10:
            trend = "down"
        else:
            trend = "flat"

        # Budget status
        daily_pct = (total_cost / self.daily_budget) * 100 if self.daily_budget > 0 else 0
        monthly_pct = (monthly_total / self.monthly_budget) * 100 if self.monthly_budget > 0 else 0

        if daily_pct >= 100 or monthly_pct >= 95:
            budget_status = "critical"
        elif daily_pct >= 80 or monthly_pct >= 80:
            budget_status = "warning"
        else:
            budget_status = "healthy"

        return CostDigestData(
            date=today_str,
            total_cost_usd=total_cost,
            by_service=today_summary.get("by_service", {}),
            by_category=today_summary.get("by_category", {}),
            record_count=today_summary.get("record_count", 0),
            yesterday_cost_usd=yesterday_cost,
            weekly_avg_usd=weekly_avg,
            daily_budget=self.daily_budget,
            monthly_budget=self.monthly_budget,
            monthly_total_usd=monthly_total,
            budget_status=budget_status,
            trend=trend,
            trend_percent=trend_percent,
        )

    def format_plaintext(self, data: CostDigestData) -> str:
        """Format digest as plaintext email body."""
        # Status indicator
        status_icon = {
            "healthy": "OK",
            "warning": "WARNING",
            "critical": "CRITICAL",
        }.get(data.budget_status, "OK")

        # Trend indicator
        trend_arrow = {
            "up": "^",
            "down": "v",
            "flat": "-",
        }.get(data.trend, "-")

        # Service breakdown
        service_lines = []
        for service, cost in sorted(data.by_service.items(), key=lambda x: -x[1]):
            service_lines.append(f"  {service}: ${cost:.4f}")

        # Category breakdown
        category_lines = []
        for category, cost in sorted(data.by_category.items(), key=lambda x: -x[1]):
            category_lines.append(f"  {category}: ${cost:.4f}")

        body = f"""Civic Platform Daily Cost Digest
================================

Date: {data.date}
Status: {status_icon}

TODAY'S COSTS
-------------
Total: ${data.total_cost_usd:.4f}
Budget: ${data.daily_budget:.2f}/day ({(data.total_cost_usd / data.daily_budget * 100):.1f}% used)
Operations: {data.record_count}

COMPARISON
----------
Yesterday: ${data.yesterday_cost_usd:.4f}
7-day avg: ${data.weekly_avg_usd:.4f}
Trend: {trend_arrow} {abs(data.trend_percent):.1f}%

BY SERVICE
----------
{chr(10).join(service_lines) if service_lines else '  (no data)'}

BY CATEGORY
-----------
{chr(10).join(category_lines) if category_lines else '  (no data)'}

MONTHLY STATUS
--------------
Month-to-date: ${data.monthly_total_usd:.4f}
Monthly budget: ${data.monthly_budget:.2f}
Usage: {(data.monthly_total_usd / data.monthly_budget * 100):.1f}%

---
View dashboard: https://civic-api.fly.dev/admin/cost-status
Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return body

    def format_html(self, data: CostDigestData) -> str:
        """Format digest as HTML email body."""
        # Status styling
        status_colors = {
            "healthy": "#22c55e",
            "warning": "#f59e0b",
            "critical": "#ef4444",
        }
        status_color = status_colors.get(data.budget_status, "#22c55e")
        status_label = data.budget_status.upper()

        # Trend indicator
        trend_icons = {
            "up": "&uarr;",
            "down": "&darr;",
            "flat": "&rarr;",
        }
        trend_icon = trend_icons.get(data.trend, "&rarr;")

        # Service rows
        service_rows = ""
        for service, cost in sorted(data.by_service.items(), key=lambda x: -x[1]):
            pct = (cost / data.total_cost_usd * 100) if data.total_cost_usd > 0 else 0
            service_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{service}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right;">${cost:.4f}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right;">{pct:.1f}%</td>
            </tr>"""

        # Category rows
        category_rows = ""
        for category, cost in sorted(data.by_category.items(), key=lambda x: -x[1]):
            pct = (cost / data.total_cost_usd * 100) if data.total_cost_usd > 0 else 0
            category_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{category}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right;">${cost:.4f}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right;">{pct:.1f}%</td>
            </tr>"""

        daily_pct = (data.total_cost_usd / data.daily_budget * 100) if data.daily_budget > 0 else 0
        monthly_pct = (data.monthly_total_usd / data.monthly_budget * 100) if data.monthly_budget > 0 else 0

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5; color: #1f2937; max-width: 600px; margin: 0 auto; padding: 20px;">

    <div style="background: linear-gradient(135deg, #1e40af, #3b82f6); padding: 24px; border-radius: 8px 8px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 24px;">Civic Daily Cost Digest</h1>
        <p style="color: #bfdbfe; margin: 8px 0 0 0;">{data.date}</p>
    </div>

    <div style="background: white; border: 1px solid #e5e7eb; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">

        <!-- Status Banner -->
        <div style="background: {status_color}; color: white; padding: 12px 16px; border-radius: 6px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 600;">{status_label}</span>
            <span>${data.total_cost_usd:.4f} today</span>
        </div>

        <!-- Summary Cards -->
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px;">
            <div style="background: #f9fafb; padding: 16px; border-radius: 6px; text-align: center;">
                <div style="color: #6b7280; font-size: 12px; text-transform: uppercase;">Today</div>
                <div style="font-size: 20px; font-weight: 600; color: #1f2937;">${data.total_cost_usd:.4f}</div>
                <div style="color: #6b7280; font-size: 12px;">{daily_pct:.1f}% of budget</div>
            </div>
            <div style="background: #f9fafb; padding: 16px; border-radius: 6px; text-align: center;">
                <div style="color: #6b7280; font-size: 12px; text-transform: uppercase;">Yesterday</div>
                <div style="font-size: 20px; font-weight: 600; color: #1f2937;">${data.yesterday_cost_usd:.4f}</div>
                <div style="color: #6b7280; font-size: 12px;">{trend_icon} {abs(data.trend_percent):.1f}%</div>
            </div>
            <div style="background: #f9fafb; padding: 16px; border-radius: 6px; text-align: center;">
                <div style="color: #6b7280; font-size: 12px; text-transform: uppercase;">7-Day Avg</div>
                <div style="font-size: 20px; font-weight: 600; color: #1f2937;">${data.weekly_avg_usd:.4f}</div>
                <div style="color: #6b7280; font-size: 12px;">{data.record_count} ops today</div>
            </div>
        </div>

        <!-- By Service -->
        <h3 style="margin: 0 0 12px 0; font-size: 16px; color: #374151;">By Service</h3>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
            <thead>
                <tr style="background: #f9fafb;">
                    <th style="padding: 8px; text-align: left; border-bottom: 2px solid #e5e7eb;">Service</th>
                    <th style="padding: 8px; text-align: right; border-bottom: 2px solid #e5e7eb;">Cost</th>
                    <th style="padding: 8px; text-align: right; border-bottom: 2px solid #e5e7eb;">%</th>
                </tr>
            </thead>
            <tbody>
                {service_rows if service_rows else '<tr><td colspan="3" style="padding: 8px; text-align: center; color: #6b7280;">No data</td></tr>'}
            </tbody>
        </table>

        <!-- By Category -->
        <h3 style="margin: 0 0 12px 0; font-size: 16px; color: #374151;">By Category</h3>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
            <thead>
                <tr style="background: #f9fafb;">
                    <th style="padding: 8px; text-align: left; border-bottom: 2px solid #e5e7eb;">Category</th>
                    <th style="padding: 8px; text-align: right; border-bottom: 2px solid #e5e7eb;">Cost</th>
                    <th style="padding: 8px; text-align: right; border-bottom: 2px solid #e5e7eb;">%</th>
                </tr>
            </thead>
            <tbody>
                {category_rows if category_rows else '<tr><td colspan="3" style="padding: 8px; text-align: center; color: #6b7280;">No data</td></tr>'}
            </tbody>
        </table>

        <!-- Monthly Progress -->
        <h3 style="margin: 0 0 12px 0; font-size: 16px; color: #374151;">Monthly Progress</h3>
        <div style="background: #f9fafb; padding: 16px; border-radius: 6px; margin-bottom: 24px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                <span>${data.monthly_total_usd:.4f}</span>
                <span>${data.monthly_budget:.2f}</span>
            </div>
            <div style="background: #e5e7eb; height: 8px; border-radius: 4px; overflow: hidden;">
                <div style="background: {status_color}; height: 100%; width: {min(monthly_pct, 100):.1f}%;"></div>
            </div>
            <div style="text-align: center; margin-top: 8px; color: #6b7280; font-size: 14px;">
                {monthly_pct:.1f}% of ${data.monthly_budget:.2f}/month budget
            </div>
        </div>

        <!-- Footer -->
        <div style="border-top: 1px solid #e5e7eb; padding-top: 16px; margin-top: 16px; text-align: center; color: #6b7280; font-size: 12px;">
            <a href="https://civic-api.fly.dev/admin/cost-status" style="color: #3b82f6; text-decoration: none;">View Dashboard</a>
            &nbsp;&bull;&nbsp;
            Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
        </div>

    </div>

</body>
</html>
"""
        return html

    def send_email(self, data: CostDigestData) -> bool:
        """
        Send digest via SMTP email.

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.alert_emails or not self.smtp_username or not self.smtp_password:
            logger.debug("Email not configured (missing SMTP settings)")
            return False

        # Subject with status indicator
        status_emoji = {
            "healthy": "",
            "warning": " - Warning",
            "critical": " - CRITICAL",
        }.get(data.budget_status, "")

        subject = f"Civic Cost Digest: ${data.total_cost_usd:.4f} ({data.date}){status_emoji}"

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.smtp_username
            msg["To"] = ", ".join(self.alert_emails)
            msg["Subject"] = subject

            # Attach both plaintext and HTML
            plaintext = self.format_plaintext(data)
            html = self.format_html(data)

            msg.attach(MIMEText(plaintext, "plain"))
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Cost digest email sent to: {self.alert_emails}")
            return True

        except Exception as e:
            logger.error(f"Failed to send cost digest email: {e}")
            return False

    def send_slack(self, data: CostDigestData) -> bool:
        """
        Send digest via Slack webhook.

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.slack_webhook_url:
            logger.debug("Slack not configured (missing webhook URL)")
            return False

        # Status emoji
        status_emoji = {
            "healthy": ":white_check_mark:",
            "warning": ":warning:",
            "critical": ":rotating_light:",
        }.get(data.budget_status, ":chart_with_upwards_trend:")

        # Trend emoji
        trend_emoji = {
            "up": ":arrow_up:",
            "down": ":arrow_down:",
            "flat": ":arrow_right:",
        }.get(data.trend, ":arrow_right:")

        # Build service breakdown
        service_text = "\n".join(
            f"  `{svc}`: ${cost:.4f}"
            for svc, cost in sorted(data.by_service.items(), key=lambda x: -x[1])[:3]
        ) or "  (no data)"

        daily_pct = (data.total_cost_usd / data.daily_budget * 100) if self.daily_budget > 0 else 0
        monthly_pct = (data.monthly_total_usd / self.monthly_budget * 100) if self.monthly_budget > 0 else 0

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Civic Daily Cost Digest",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Date:*\n{data.date}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{data.budget_status.upper()}"},
                    {"type": "mrkdwn", "text": f"*Today:*\n${data.total_cost_usd:.4f}"},
                    {"type": "mrkdwn", "text": f"*Budget:*\n{daily_pct:.1f}% of ${data.daily_budget:.2f}/day"},
                ],
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Yesterday:*\n${data.yesterday_cost_usd:.4f}"},
                    {"type": "mrkdwn", "text": f"*Trend:*\n{trend_emoji} {abs(data.trend_percent):.1f}%"},
                    {"type": "mrkdwn", "text": f"*7-Day Avg:*\n${data.weekly_avg_usd:.4f}"},
                    {"type": "mrkdwn", "text": f"*Operations:*\n{data.record_count}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top Services:*\n{service_text}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Monthly:* ${data.monthly_total_usd:.4f} / ${data.monthly_budget:.2f} ({monthly_pct:.1f}%)",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<https://civic-api.fly.dev/admin/cost-status|View Dashboard>",
                    }
                ],
            },
        ]

        payload = {
            "blocks": blocks,
            "text": f"Civic Cost Digest: ${data.total_cost_usd:.4f} ({data.date})",
        }

        try:
            req = Request(
                self.slack_webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info("Cost digest sent to Slack")
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
            logger.error(f"Failed to send Slack digest: {e}")
            return False

    def send(self) -> Dict[str, Any]:
        """
        Collect data and send digest via all configured channels.

        Returns:
            Dictionary with result status and details
        """
        if not self.enabled:
            logger.info("Cost digest is disabled (CIVIC_COST_DIGEST_ENABLED=false)")
            return {
                "success": False,
                "reason": "disabled",
                "channels": [],
            }

        # Collect cost data
        try:
            data = self.collect_data()
        except Exception as e:
            logger.error(f"Failed to collect cost data: {e}")
            return {
                "success": False,
                "reason": f"data_collection_failed: {e}",
                "channels": [],
            }

        # Send via available channels
        channels_sent = []

        if self.send_email(data):
            channels_sent.append("email")

        if self.send_slack(data):
            channels_sent.append("slack")

        if not channels_sent:
            # Log-only fallback
            logger.warning(
                f"Cost digest (no channels configured): {data.date} - ${data.total_cost_usd:.4f} "
                f"({data.budget_status})"
            )

        return {
            "success": len(channels_sent) > 0,
            "data": asdict(data),
            "channels": channels_sent,
        }

    def preview(self) -> Dict[str, Any]:
        """
        Generate digest preview without sending.

        Returns:
            Dictionary with data and formatted content
        """
        data = self.collect_data()
        return {
            "data": asdict(data),
            "plaintext": self.format_plaintext(data),
            "html": self.format_html(data),
        }


def send_daily_digest(jurisdiction_id: str = "city-san-rafael") -> Dict[str, Any]:
    """
    Convenience function to send daily cost digest.

    Args:
        jurisdiction_id: Jurisdiction to report on

    Returns:
        Result dictionary with success status and details
    """
    digest = DailyCostDigest(jurisdiction_id=jurisdiction_id)
    return digest.send()


if __name__ == "__main__":
    import sys

    if "--preview" in sys.argv:
        # Preview mode - don't send
        from dotenv import load_dotenv
        load_dotenv()

        digest = DailyCostDigest()
        preview = digest.preview()
        print("=== COST DIGEST PREVIEW ===")
        print(f"Date: {preview['data']['date']}")
        print(f"Status: {preview['data']['budget_status']}")
        print(f"Total: ${preview['data']['total_cost_usd']:.4f}")
        print()
        print("=== PLAINTEXT ===")
        print(preview["plaintext"])
    elif "--send" in sys.argv:
        # Actually send
        from dotenv import load_dotenv
        load_dotenv()

        result = send_daily_digest()
        print(json.dumps(result, indent=2))
    else:
        print("Daily Cost Digest")
        print()
        print("Usage:")
        print("  python daily_cost_digest.py --preview  # Preview without sending")
        print("  python daily_cost_digest.py --send     # Send digest")
        print()
        print("Environment variables:")
        print("  CIVIC_ALERT_EMAILS        - Comma-separated recipients")
        print("  CIVIC_SMTP_SERVER         - SMTP server")
        print("  CIVIC_SMTP_PORT           - SMTP port")
        print("  CIVIC_SMTP_USERNAME       - SMTP username")
        print("  CIVIC_SMTP_PASSWORD       - SMTP password")
        print("  CIVIC_SLACK_WEBHOOK_URL   - Slack webhook URL")
        print("  CIVIC_COST_DIGEST_ENABLED - Set 'false' to disable")
        print("  CIVIC_DAILY_BUDGET        - Daily budget (default: 5.0)")
        print("  CIVIC_MONTHLY_BUDGET      - Monthly budget (default: 50.0)")
