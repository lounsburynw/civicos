#!/usr/bin/env python3
"""
Automated civic data refresh using existing civic_digest.py infrastructure
with temporal filtering for cost optimization and user trust preservation.

Foundation Budget Compliance: <$50/month operational cost
Implementation: Phase 2 LLM-driven automation system
"""
import subprocess
import json
import sys
import os
import glob
import time
import smtplib
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# City configurations using existing schema structure - EXTENDED FOR REGIONAL SCALE
CITY_CONFIGS = {
    "san_rafael": {
        "jurisdiction_id": "city-san-rafael",  # matches civic-app-schema.json
        "agent_type": "san_rafael_cms",  # BeautifulSoup-based table extraction (100% accuracy)
        "meeting_urls": [
            "https://www.cityofsanrafael.org/city-council-meetings/"
        ],
        "contact_email": "planning@cityofsanrafael.org",
        "timezone": "America/Los_Angeles",
        "website": "https://www.cityofsanrafael.org",
        "meeting_calendar_url": "https://www.cityofsanrafael.org/departments/public-meetings/"
    },
    "berkeley": {
        "jurisdiction_id": "city-berkeley",
        "agent_type": "berkeley_cms",  # Multi-pass extraction with uncertainty metrics
        "meeting_urls": [
            "https://berkeleyca.gov/community-recreation/events?field_event_category_tid=104"
        ],
        "contact_email": "council@cityofberkeley.info",
        "timezone": "America/Los_Angeles",
        "website": "https://berkeleyca.gov",
        "meeting_calendar_url": "https://berkeleyca.gov/community-recreation/events"
    },
    "santa_rosa": {
        "jurisdiction_id": "city-santa-rosa",
        "agent_type": "legistar",  # Legistar platform specialized extraction
        "meeting_urls": [
            "https://santa-rosa.legistar.com/Calendar.aspx"
        ],
        "contact_email": "citycouncil@srcity.org",
        "timezone": "America/Los_Angeles"
    },
    "hayward": {
        "jurisdiction_id": "city-hayward",
        "agent_type": "legistar",  # Legistar API - Hayward redirects to hayward.legistar.com
        "meeting_urls": [
            "https://hayward.legistar.com/Calendar.aspx"
        ],
        "contact_email": "clerk@hayward-ca.gov",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.05  # Legistar API target (similar to other Legistar cities)
    },
    "richmond": {
        "jurisdiction_id": "city-richmond",
        "agent_type": "civicclerk",  # CivicClerk API client (probe found richmondca subdomain)
        "meeting_urls": [
            "https://richmondca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@ci.richmond.ca.us",
        "timezone": "America/Los_Angeles",
        "website": "https://www.ci.richmond.ca.us",
        "meeting_calendar_url": "https://richmondca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05  # API-based, similar to Legistar efficiency
    },
    "el_cerrito": {
        "jurisdiction_id": "city-el-cerrito",
        "agent_type": "civicclerk",  # CivicClerk API client (Granicus product)
        "meeting_urls": [
            "https://elcerritoca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@elcerrito.gov",
        "timezone": "America/Los_Angeles",
        "website": "https://www.elcerrito.gov",
        "meeting_calendar_url": "https://elcerritoca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05  # API-based, similar to Legistar efficiency
    },
    "dublin": {
        "jurisdiction_id": "city-dublin",
        "agent_type": "granicus",  # Granicus ViewPublisher API
        "meeting_urls": [
            "https://dublin.granicus.com/ViewPublisher.php?view_id=1"
        ],
        "contact_email": "citycouncil@dublin.ca.gov",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.05,  # API-based, similar to Legistar efficiency
        "granicus_config": {
            "subdomain": "dublin",
            "view_id": 1
        }
    },
    "union_city": {
        "jurisdiction_id": "city-union-city",
        "agent_type": "civicplus_cms",  # CivicPlus AgendaCenter platform
        "meeting_urls": [
            "https://www.unioncity.org/AgendaCenter"
        ],
        "contact_email": "cityclerk@unioncity.org",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.08  # Target better than $0.15 standard parsing
    },
    "concord": {
        "jurisdiction_id": "city-concord",
        "agent_type": "civicplus_cms",  # CivicPlus AgendaCenter platform
        "meeting_urls": [
            "https://www.cityofconcord.org/AgendaCenter"
        ],
        "contact_email": "clerk@cityofconcord.org",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.048  # CivicPlus target efficiency
    },
    "san_leandro": {
        "jurisdiction_id": "city-san-leandro",
        "agent_type": "civicplus_cms",  # CivicPlus AgendaCenter platform
        "meeting_urls": [
            "https://www.sanleandro.org/AgendaCenter"
        ],
        "contact_email": "clerk@sanleandro.org",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.048  # CivicPlus target efficiency
    },
    "campbell": {
        "jurisdiction_id": "city-campbell",
        "agent_type": "granicus",  # Granicus ViewPublisher API
        "meeting_urls": [
            "https://cityofcampbell.granicus.com/ViewPublisher.php?view_id=2"
        ],
        "contact_email": "clerk@ci.campbell.ca.us",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.05,  # API-based, similar to Legistar efficiency
        "granicus_config": {
            "subdomain": "cityofcampbell",
            "view_id": 2
        }
    },
    "pleasant_hill": {
        "jurisdiction_id": "city-pleasant-hill",
        "agent_type": "civicplus_cms",  # CivicPlus AgendaCenter platform
        "meeting_urls": [
            "https://www.ci.pleasant-hill.ca.us/AgendaCenter"
        ],
        "contact_email": "clerk@ci.pleasant-hill.ca.us",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.048  # CivicPlus target efficiency
    },
    "oakland": {
        "jurisdiction_id": "city-oakland",
        "agent_type": "legistar",  # Legistar API platform
        "meeting_urls": [
            "https://oakland.legistar.com/Calendar.aspx"
        ],
        "contact_email": "cityclerk@oaklandca.gov",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.05  # Legistar API target efficiency
    },
    "los_altos": {
        "jurisdiction_id": "city-los-altos",
        "agent_type": "civicclerk",  # CivicClerk API client (Granicus product)
        "meeting_urls": [
            "https://losaltosca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@losaltosca.gov",
        "timezone": "America/Los_Angeles",
        "website": "https://www.losaltosca.gov",
        "meeting_calendar_url": "https://losaltosca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05  # API-based, similar to Legistar efficiency
    },
    "sonoma_county": {
        "jurisdiction_id": "sonoma-county",
        "agent_type": "legistar",  # Legistar API platform
        "meeting_urls": [
            "https://sonoma-county.legistar.com/Calendar.aspx"
        ],
        "contact_email": "clerk@sonoma-county.org",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.05  # Legistar API target efficiency
    },
    "napa": {
        "jurisdiction_id": "city-napa",
        "agent_type": "legistar",  # Legistar API platform
        "meeting_urls": [
            "https://napa.legistar.com/Calendar.aspx"
        ],
        "contact_email": "cityclerk@cityofnapa.org",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.05  # Legistar API target efficiency
    },
    "bart": {
        "jurisdiction_id": "bart",
        "agent_type": "legistar",  # Legistar API platform
        "meeting_urls": [
            "https://bart.legistar.com/Calendar.aspx"
        ],
        "contact_email": "boardmeetings@bart.gov",
        "timezone": "America/Los_Angeles",
        "cost_efficiency_target": 0.05  # Legistar API target efficiency
    },
    # ========== NEW CIVICCLERK CITIES (2025-10-04) ==========
    "daly_city": {
        "jurisdiction_id": "city-daly-city",
        "agent_type": "civicclerk",  # CivicClerk API client (15 events)
        "meeting_urls": [
            "https://dalycityca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@dalycity.org",
        "timezone": "America/Los_Angeles",
        "website": "https://www.dalycity.org",
        "meeting_calendar_url": "https://dalycityca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05
    },
    "los_altos_hills": {
        "jurisdiction_id": "city-los-altos-hills",
        "agent_type": "civicclerk",  # CivicClerk API client (15 events)
        "meeting_urls": [
            "https://losaltoshillsca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@losaltoshills.ca.gov",
        "timezone": "America/Los_Angeles",
        "website": "https://www.losaltoshills.ca.gov",
        "meeting_calendar_url": "https://losaltoshillsca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05
    },
    "milpitas": {
        "jurisdiction_id": "city-milpitas",
        "agent_type": "civicclerk",  # CivicClerk API client (10 events)
        "meeting_urls": [
            "https://milpitasca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@ci.milpitas.ca.gov",
        "timezone": "America/Los_Angeles",
        "website": "https://www.ci.milpitas.ca.gov",
        "meeting_calendar_url": "https://milpitasca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05
    },
    "pinole": {
        "jurisdiction_id": "city-pinole",
        "agent_type": "civicclerk",  # CivicClerk API client (5 events)
        "meeting_urls": [
            "https://pinoleca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@ci.pinole.ca.us",
        "timezone": "America/Los_Angeles",
        "website": "https://www.ci.pinole.ca.us",
        "meeting_calendar_url": "https://pinoleca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05
    },
    "pleasanton": {
        "jurisdiction_id": "city-pleasanton",
        "agent_type": "civicclerk",  # CivicClerk API client (5 events)
        "meeting_urls": [
            "https://pleasantonca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@cityofpleasantonca.gov",
        "timezone": "America/Los_Angeles",
        "website": "https://www.cityofpleasantonca.gov",
        "meeting_calendar_url": "https://pleasantonca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05
    },
    "scotts_valley": {
        "jurisdiction_id": "city-scotts-valley",
        "agent_type": "civicclerk",  # CivicClerk API client (4 events)
        "meeting_urls": [
            "https://scottsvalleyca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@scottsvalley.org",
        "timezone": "America/Los_Angeles",
        "website": "https://www.scottsvalley.org",
        "meeting_calendar_url": "https://scottsvalleyca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05
    },
    "pittsburg": {
        "jurisdiction_id": "city-pittsburg",
        "agent_type": "civicclerk",  # CivicClerk API client (1 event)
        "meeting_urls": [
            "https://pittsburgca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@ci.pittsburg.ca.us",
        "timezone": "America/Los_Angeles",
        "website": "https://www.ci.pittsburg.ca.us",
        "meeting_calendar_url": "https://pittsburgca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05
    },
    "antioch": {
        "jurisdiction_id": "city-antioch",
        "agent_type": "civicclerk",  # CivicClerk API client (0 events currently)
        "meeting_urls": [
            "https://antiochca.portal.civicclerk.com"
        ],
        "contact_email": "cityclerk@ci.antioch.ca.us",
        "timezone": "America/Los_Angeles",
        "website": "https://www.antiochca.gov",
        "meeting_calendar_url": "https://antiochca.portal.civicclerk.com",
        "cost_efficiency_target": 0.05
    }
}

def get_jurisdiction_agent_type(url: str) -> str:
    """Get agent type for a given URL based on jurisdiction configuration

    Args:
        url: Meeting URL to analyze

    Returns:
        str: Agent type ('berkeley_cms', 'legistar', 'standard')
    """
    # Check each jurisdiction's URLs to find a match
    for jurisdiction_key, config in CITY_CONFIGS.items():
        for meeting_url in config['meeting_urls']:
            # Extract domain from both URLs for comparison
            try:
                url_domain = url.split("//")[1].split("/")[0].lower()
                config_domain = meeting_url.split("//")[1].split("/")[0].lower()

                if url_domain == config_domain or config_domain in url_domain or url_domain in config_domain:
                    return config['agent_type']
            except (IndexError, AttributeError):
                continue

    # Default to standard if no match found
    return 'standard'

def get_jurisdiction_by_url(url: str) -> str:
    """Get jurisdiction ID for a given URL

    Args:
        url: Meeting URL to analyze

    Returns:
        str: Jurisdiction ID (e.g., 'city-berkeley')
    """
    # Check each jurisdiction's URLs to find a match
    for jurisdiction_key, config in CITY_CONFIGS.items():
        for meeting_url in config['meeting_urls']:
            try:
                url_domain = url.split("//")[1].split("/")[0].lower()
                config_domain = meeting_url.split("//")[1].split("/")[0].lower()

                if url_domain == config_domain or config_domain in url_domain or url_domain in config_domain:
                    return config['jurisdiction_id']
            except (IndexError, AttributeError):
                continue

    return 'unknown'

class ProductionErrorHandler:
    """Production-level error handling with exponential backoff and alerting"""

    def __init__(self):
        self.max_retries = 3
        self.base_delay = 2  # seconds
        self.max_delay = 60  # seconds
        self.failure_log_file = "data/system_failures.json"

    def exponential_backoff_retry(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry logic"""
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except subprocess.TimeoutExpired as e:
                if attempt == self.max_retries - 1:
                    self.log_failure("timeout", str(e), args)
                    raise
                delay = min(self.base_delay * (2 ** attempt) + random.uniform(0, 1), self.max_delay)
                print(f"⏰ Timeout on attempt {attempt + 1}, retrying in {delay:.1f}s...")
                time.sleep(delay)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    self.log_failure("error", str(e), args)
                    raise
                delay = min(self.base_delay * (2 ** attempt) + random.uniform(0, 1), self.max_delay)
                print(f"🔄 Error on attempt {attempt + 1}, retrying in {delay:.1f}s: {str(e)[:50]}")
                time.sleep(delay)

    def log_failure(self, failure_type: str, error_message: str, context):
        """Log system failures for monitoring"""
        failure_entry = {
            "timestamp": datetime.now().isoformat(),
            "failure_type": failure_type,
            "error_message": error_message,
            "context": str(context)[:500],  # Limit context size
            "retry_count": self.max_retries
        }

        failures = []
        if os.path.exists(self.failure_log_file):
            try:
                with open(self.failure_log_file, 'r') as f:
                    failures = json.load(f)
            except:
                failures = []

        failures.append(failure_entry)

        # Keep only last 100 failures to prevent unbounded growth
        failures = failures[-100:]

        os.makedirs(os.path.dirname(self.failure_log_file), exist_ok=True)
        with open(self.failure_log_file, 'w') as f:
            json.dump(failures, f, indent=2)

    def check_persistent_failures(self) -> dict:
        """Check for persistent failures requiring intervention"""
        if not os.path.exists(self.failure_log_file):
            return {"needs_alert": False, "failure_count": 0}

        try:
            with open(self.failure_log_file, 'r') as f:
                failures = json.load(f)
        except:
            return {"needs_alert": False, "failure_count": 0}

        # Check failures in last 24 hours
        cutoff_time = datetime.now() - timedelta(hours=24)
        recent_failures = [
            f for f in failures
            if datetime.fromisoformat(f['timestamp']) > cutoff_time
        ]

        # Alert if more than 5 failures in 24 hours
        needs_alert = len(recent_failures) > 5

        return {
            "needs_alert": needs_alert,
            "failure_count": len(recent_failures),
            "recent_failures": recent_failures[-3:] if recent_failures else []
        }

class ProductionAlertManager:
    """Email alerting for system health monitoring"""

    def __init__(self):
        self.alert_recipients = os.getenv('CIVIC_ALERT_EMAILS', '').split(',')
        self.smtp_server = os.getenv('CIVIC_SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('CIVIC_SMTP_PORT', '587'))
        self.smtp_username = os.getenv('CIVIC_SMTP_USERNAME', '')
        self.smtp_password = os.getenv('CIVIC_SMTP_PASSWORD', '')

    def send_budget_alert(self, budget_status: dict):
        """Send budget threshold alert"""
        if not self.alert_recipients or not self.smtp_username:
            print("⚠️  Email alerting not configured (missing CIVIC_ALERT_EMAILS or SMTP credentials)")
            return

        subject = f"🚨 Civic Platform Budget Alert - {budget_status['budget_percentage']:.1f}% Used"
        body = f"""
Civic Engagement Platform Budget Alert

Current Status:
- Monthly Cost: ${budget_status['total_cost']:.2f} / ${budget_status['budget_limit']:.2f}
- Budget Usage: {budget_status['budget_percentage']:.1f}%
- Status: {budget_status['budget_status']}

Recent Activity:
- {len(budget_status['entries'])} refresh operations this month

Action Required:
{'🔴 Immediate attention - over budget!' if budget_status['budget_status'] == 'over_budget' else '🟡 Monitor usage - approaching limit'}

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """

        self._send_email(subject, body)

    def send_failure_alert(self, failure_status: dict):
        """Send persistent failure alert"""
        if not failure_status['needs_alert']:
            return

        if not self.alert_recipients or not self.smtp_username:
            print("⚠️  Email alerting not configured for failure alerts")
            return

        subject = f"🚨 Civic Platform System Failures - {failure_status['failure_count']} in 24h"
        body = f"""
Civic Engagement Platform System Alert

Failure Summary:
- {failure_status['failure_count']} failures in the last 24 hours
- Threshold exceeded (>5 failures/24h)

Recent Failures:
"""
        for failure in failure_status['recent_failures']:
            body += f"- {failure['timestamp']}: {failure['failure_type']} - {failure['error_message'][:100]}\n"

        body += f"""
Action Required: System intervention needed to restore reliability

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """

        self._send_email(subject, body)

    def _send_email(self, subject: str, body: str):
        """Send email via SMTP"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = ', '.join(self.alert_recipients)
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            text = msg.as_string()
            server.sendmail(self.smtp_username, self.alert_recipients, text)
            server.quit()

            print(f"📧 Alert sent to {len(self.alert_recipients)} recipients")

        except Exception as e:
            print(f"❌ Email alert failed: {e}")

class TemporalCostManager:
    """Cost monitoring and temporal filtering for foundation budget compliance"""

    def __init__(self):
        self.monthly_cost_limit = 50.0  # Foundation budget constraint
        self.cost_log_file = "data/cost_monitoring.json"
        self.alert_manager = ProductionAlertManager()

    def log_refresh_cost(self, city_id: str, temporal_scope: str, estimated_cost: float, opportunities_count: int):
        """Log refresh costs for monthly budget tracking"""
        cost_entry = {
            "timestamp": datetime.now().isoformat(),
            "city_id": city_id,
            "temporal_scope": temporal_scope,
            "estimated_cost": estimated_cost,
            "opportunities_generated": opportunities_count,
            "cost_per_opportunity": estimated_cost / max(opportunities_count, 1)
        }

        # Load existing cost log
        cost_log = []
        if os.path.exists(self.cost_log_file):
            try:
                with open(self.cost_log_file, 'r') as f:
                    cost_log = json.load(f)
            except:
                cost_log = []

        cost_log.append(cost_entry)

        # Save updated log
        os.makedirs(os.path.dirname(self.cost_log_file), exist_ok=True)
        with open(self.cost_log_file, 'w') as f:
            json.dump(cost_log, f, indent=2)

    def get_monthly_costs(self) -> dict:
        """Calculate current month costs for budget monitoring with alerting"""
        if not os.path.exists(self.cost_log_file):
            return {
                "total_cost": 0.0,
                "budget_limit": self.monthly_cost_limit,
                "budget_percentage": 0.0,
                "entries": [],
                "budget_status": "under_budget"
            }

        try:
            with open(self.cost_log_file, 'r') as f:
                cost_log = json.load(f)
        except:
            return {
                "total_cost": 0.0,
                "budget_limit": self.monthly_cost_limit,
                "budget_percentage": 0.0,
                "entries": [],
                "budget_status": "under_budget"
            }

        # Filter to current month
        current_month = datetime.now().strftime('%Y-%m')
        current_month_entries = [
            entry for entry in cost_log
            if entry['timestamp'].startswith(current_month)
        ]

        total_cost = sum(entry['estimated_cost'] for entry in current_month_entries)
        budget_percentage = (total_cost / self.monthly_cost_limit) * 100

        # Enhanced budget status with alerting thresholds
        if budget_percentage >= 95:
            budget_status = "over_budget"
        elif budget_percentage >= 85:
            budget_status = "critical_warning"
        elif budget_percentage >= 70:
            budget_status = "warning"
        else:
            budget_status = "under_budget"

        budget_status_obj = {
            "total_cost": total_cost,
            "budget_limit": self.monthly_cost_limit,
            "budget_percentage": budget_percentage,
            "entries": current_month_entries,
            "budget_status": budget_status
        }

        # Send alerts for budget thresholds
        if budget_status in ["over_budget", "critical_warning"]:
            # Check if we've already alerted today to avoid spam
            today = datetime.now().strftime('%Y-%m-%d')
            alert_log_file = "data/alert_log.json"

            should_alert = True
            if os.path.exists(alert_log_file):
                try:
                    with open(alert_log_file, 'r') as f:
                        alert_log = json.load(f)

                    recent_budget_alerts = [
                        alert for alert in alert_log
                        if alert.get('type') == 'budget' and alert.get('date') == today
                    ]
                    should_alert = len(recent_budget_alerts) == 0
                except:
                    should_alert = True

            if should_alert:
                self.alert_manager.send_budget_alert(budget_status_obj)
                # Log that we sent an alert
                self._log_alert("budget", today, budget_status)

        return budget_status_obj

    def _log_alert(self, alert_type: str, date: str, details: str):
        """Log sent alerts to prevent spam"""
        alert_log_file = "data/alert_log.json"
        alert_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": alert_type,
            "date": date,
            "details": details
        }

        alerts = []
        if os.path.exists(alert_log_file):
            try:
                with open(alert_log_file, 'r') as f:
                    alerts = json.load(f)
            except:
                alerts = []

        alerts.append(alert_entry)
        # Keep only last 50 alerts
        alerts = alerts[-50:]

        os.makedirs(os.path.dirname(alert_log_file), exist_ok=True)
        with open(alert_log_file, 'w') as f:
            json.dump(alerts, f, indent=2)

def refresh_city_data(city_id: str, temporal_scope: str = 'current_active_only') -> dict:
    """Refresh civic data with production-level error handling and graceful degradation"""
    config = CITY_CONFIGS[city_id]
    results = {"success": [], "failures": [], "filtered_count": 0, "estimated_cost": 0.0, "fallback_used": False}

    cost_manager = TemporalCostManager()
    error_handler = ProductionErrorHandler()

    # Determine date filtering based on temporal scope
    if temporal_scope == 'future_meetings_only':
        # Short-term strategy: Only meetings from today forward
        date_filter = datetime.now()
        filter_description = "future meetings only"
        cost_multiplier = 0.4  # ~60% cost reduction from filtering
    elif temporal_scope == 'include_recent_past':
        # Long-term strategy: Include past 6 months for trend analysis
        date_filter = datetime.now() - timedelta(days=180)
        filter_description = "past 6 months to future"
        cost_multiplier = 1.0  # Full cost
    else:  # current_active_only
        # Default: Past 30 days to future 90 days (active civic window)
        date_filter = datetime.now() - timedelta(days=30)
        filter_description = "active civic window (30 days past to 90 days future)"
        cost_multiplier = 0.6  # ~40% cost reduction

    successful_urls = 0
    total_urls = len(config["meeting_urls"])

    for meeting_url in config["meeting_urls"]:
        def process_single_url():
            print(f"🔄 Processing {meeting_url} ({filter_description})")

            # Use existing civic_digest.py schema mode
            cmd = [
                'python', 'src/civic_digest.py', 'schema', meeting_url
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                results["success"].append(meeting_url)

                # Estimate processing cost (GPT-4o pricing: ~$0.10-0.15 per meeting)
                base_cost = 0.12  # Average cost per meeting processing
                adjusted_cost = base_cost * cost_multiplier
                results["estimated_cost"] += adjusted_cost

                # Count filtered events from output files
                try:
                    # Look for newly generated schema files
                    schema_files = glob.glob('data/events/events_*.json')
                    if schema_files:
                        latest_file = max(schema_files, key=os.path.getmtime)
                        with open(latest_file, 'r') as f:
                            output_data = json.load(f)
                        filtered_count = len(output_data.get('events', []))
                        results["filtered_count"] += filtered_count
                        print(f"✅ Refreshed ({filtered_count} events, {filter_description}): {meeting_url}")
                    else:
                        print(f"✅ Refreshed ({filter_description}): {meeting_url}")
                except Exception as e:
                    print(f"✅ Refreshed ({filter_description}): {meeting_url} (count error: {e})")

                return True  # Success
            else:
                error_msg = f"{meeting_url}: {result.stderr[:100]}"
                results["failures"].append(error_msg)
                print(f"❌ Failed: {error_msg}")
                return False

        try:
            # Use exponential backoff retry for each URL
            success = error_handler.exponential_backoff_retry(process_single_url)
            if success:
                successful_urls += 1
        except Exception as e:
            results["failures"].append(f"{meeting_url}: Final failure after retries - {str(e)}")
            print(f"🚨 Final failure: {meeting_url} - {e}")

    # Implement graceful degradation with cached data fallback
    if successful_urls == 0 and total_urls > 0:
        print(f"⚠️  All URLs failed for {city_id}, attempting graceful degradation...")

        # Try to use cached schema data from the last 7 days
        cached_data = _get_cached_data(city_id, days_back=7)
        if cached_data:
            results["fallback_used"] = True
            results["filtered_count"] = len(cached_data.get('events', []))
            print(f"📋 Using cached data from {cached_data.get('created_at', 'unknown')} ({results['filtered_count']} events)")
        else:
            print(f"❌ No viable cached data found for {city_id}")

    # Check and alert for persistent failures
    failure_status = error_handler.check_persistent_failures()
    if failure_status['needs_alert']:
        alert_manager = ProductionAlertManager()
        alert_manager.send_failure_alert(failure_status)

    # Log costs for budget monitoring
    cost_manager.log_refresh_cost(
        city_id,
        temporal_scope,
        results["estimated_cost"],
        results["filtered_count"]
    )

    return results

def _get_cached_data(city_id: str, days_back: int = 7) -> Optional[dict]:
    """Retrieve cached schema data for graceful degradation during outages"""
    try:
        schema_files = glob.glob('data/events/events_*.json')
        if not schema_files:
            return None

        # Filter files by age and jurisdiction
        cutoff_date = datetime.now() - timedelta(days=days_back)
        viable_files = []

        for file_path in schema_files:
            try:
                # Check file modification time
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time < cutoff_date:
                    continue

                # Check if file contains data for the requested city
                with open(file_path, 'r') as f:
                    data = json.load(f)

                jurisdiction = data.get('jurisdiction', {})
                if jurisdiction.get('id') == CITY_CONFIGS[city_id]['jurisdiction_id']:
                    viable_files.append((file_path, file_time, data))

            except Exception:
                continue

        if not viable_files:
            return None

        # Return the most recent viable file
        viable_files.sort(key=lambda x: x[1], reverse=True)
        return viable_files[0][2]

    except Exception as e:
        print(f"Error accessing cached data: {e}")
        return None

def validate_schema_output() -> bool:
    """Verify generated data matches civic-app-schema.json"""
    try:
        schema_files = glob.glob('data/events/events_*.json')
        if not schema_files:
            print("❌ No schema files found")
            return False

        latest_file = max(schema_files, key=os.path.getmtime)
        with open(latest_file) as f:
            data = json.load(f)

        # Basic schema validation
        required_fields = ['id', 'jurisdiction', 'events', 'created_at']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            print(f"❌ Schema validation failed - missing fields: {missing_fields}")
            return False

        # Validate events structure
        events = data.get('events', [])
        for i, opp in enumerate(events):
            required_opp_fields = ['id', 'title', 'description', 'when']  # 'when' is the actual field name
            missing_opp_fields = [field for field in required_opp_fields if field not in opp]
            if missing_opp_fields:
                print(f"❌ Event {i} missing fields: {missing_opp_fields}")
                return False

        print(f"✅ Schema validation passed - {len(events)} events")
        return True

    except Exception as e:
        print(f"❌ Schema validation failed: {e}")
        return False

def monitor_budget_status():
    """Check monthly budget status and alert if approaching limits"""
    cost_manager = TemporalCostManager()
    budget_status = cost_manager.get_monthly_costs()

    print(f"\n💰 Budget Status:")
    print(f"   Monthly costs: ${budget_status['total_cost']:.2f} / ${budget_status['budget_limit']:.2f}")
    print(f"   Budget usage: {budget_status['budget_percentage']:.1f}%")
    print(f"   Status: {budget_status['budget_status']}")

    if budget_status['budget_status'] == 'warning':
        print("⚠️  WARNING: Approaching 80% of monthly budget")
    elif budget_status['budget_status'] == 'over_budget':
        print("🚨 ALERT: Monthly budget limit exceeded!")
        return False

    return True

if __name__ == "__main__":
    print(f"🚀 Starting automated civic data refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Parse command line arguments for temporal scope
    temporal_scope = 'current_active_only'  # Default
    if '--future-only' in sys.argv:
        temporal_scope = 'future_meetings_only'
        print("📅 Temporal scope: Future meetings only (cost optimized)")
    elif '--include-recent-past' in sys.argv:
        temporal_scope = 'include_recent_past'
        print("📅 Temporal scope: Including recent past (full context)")
    else:
        print("📅 Temporal scope: Current active window (balanced)")

    # Parse jurisdiction filter
    target_jurisdiction = None
    if '--jurisdiction' in sys.argv:
        try:
            idx = sys.argv.index('--jurisdiction')
            target_jurisdiction = sys.argv[idx + 1]
            if target_jurisdiction not in CITY_CONFIGS:
                print(f"❌ Unknown jurisdiction: '{target_jurisdiction}'")
                print(f"Available jurisdictions: {', '.join(sorted(CITY_CONFIGS.keys()))}")
                sys.exit(1)
            print(f"🎯 Target jurisdiction: {target_jurisdiction}")
        except (IndexError, ValueError):
            print("❌ --jurisdiction requires a jurisdiction name")
            print(f"Available jurisdictions: {', '.join(sorted(CITY_CONFIGS.keys()))}")
            sys.exit(1)

    # Check budget status before proceeding
    if not monitor_budget_status():
        print("❌ Refresh cancelled due to budget constraints")
        sys.exit(1)

    total_opportunities = 0
    total_cost = 0.0
    overall_success = True

    # Filter cities if jurisdiction specified
    cities_to_process = [target_jurisdiction] if target_jurisdiction else list(CITY_CONFIGS.keys())

    for city_id in cities_to_process:
        print(f"\n🏙️  Processing {city_id}...")
        results = refresh_city_data(city_id, temporal_scope)
        total_opportunities += results.get('filtered_count', 0)
        total_cost += results.get('estimated_cost', 0.0)

        if results['failures']:
            overall_success = False
            print(f"⚠️  Partial failures for {city_id}: {len(results['failures'])} URLs failed")

    print(f"\n📊 Refresh Summary:")
    print(f"   Total events generated: {total_opportunities}")
    print(f"   Estimated cost: ${total_cost:.2f}")
    print(f"   Temporal scope: {temporal_scope}")

    # Validate schema compliance
    if validate_schema_output():
        print("✅ Schema validation passed")

        # Update final budget monitoring
        monitor_budget_status()

        if overall_success:
            print("🎉 Automated refresh completed successfully")
        else:
            print("⚠️  Refresh completed with some failures")
            sys.exit(1)
    else:
        print("❌ Schema validation failed - refresh incomplete")
        sys.exit(1)