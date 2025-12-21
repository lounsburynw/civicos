#!/usr/bin/env python3
"""
Production Monitoring Dashboard for Civic Engagement Platform

Real-time visibility into:
- Cost tracking and budget compliance
- System health and failure rates
- Data freshness across jurisdictions
- Foundation metrics and regional scaling progress

Usage:
    python src/monitoring_dashboard.py --web  # Start web dashboard
    python src/monitoring_dashboard.py --report  # Generate text report
"""

import json
import os
import sys
import glob
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import http.server
import socketserver
import webbrowser
import threading
import time


@dataclass
class JurisdictionStatus:
    """Status tracking for individual jurisdictions"""
    id: str
    name: str
    last_refresh: Optional[str]
    opportunities_count: int
    cost_today: float
    success_rate: float
    is_healthy: bool


@dataclass
class SystemHealth:
    """Overall system health metrics"""
    budget_usage: float
    budget_status: str
    total_jurisdictions: int
    healthy_jurisdictions: int
    today_refresh_count: int
    today_cost: float
    failure_rate_24h: float
    needs_attention: bool


class CivicMonitoringDashboard:
    """Production monitoring dashboard for civic platform operations"""

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.cost_log_file = "data/cost_monitoring.json"
        self.failure_log_file = "data/system_failures.json"
        self.alert_log_file = "data/alert_log.json"
        self.monthly_budget_limit = 50.0

    def get_system_health(self) -> SystemHealth:
        """Generate comprehensive system health overview"""
        budget_data = self._get_budget_status()
        jurisdiction_statuses = self._get_jurisdiction_statuses()
        failure_rate = self._get_failure_rate_24h()

        healthy_count = sum(1 for j in jurisdiction_statuses if j.is_healthy)
        today_cost = sum(j.cost_today for j in jurisdiction_statuses)
        today_refresh_count = len([
            entry for entry in self._get_cost_entries_today()
        ])

        needs_attention = (
            budget_data['budget_percentage'] > 80 or
            failure_rate > 20 or  # More than 20% failure rate
            healthy_count < len(jurisdiction_statuses) * 0.7  # Less than 70% healthy
        )

        return SystemHealth(
            budget_usage=budget_data['budget_percentage'],
            budget_status=budget_data['budget_status'],
            total_jurisdictions=len(jurisdiction_statuses),
            healthy_jurisdictions=healthy_count,
            today_refresh_count=today_refresh_count,
            today_cost=today_cost,
            failure_rate_24h=failure_rate,
            needs_attention=needs_attention
        )

    def _get_budget_status(self) -> Dict:
        """Get current budget status and spending"""
        if not os.path.exists(self.cost_log_file):
            return {
                "total_cost": 0.0,
                "budget_limit": self.monthly_budget_limit,
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
                "budget_limit": self.monthly_budget_limit,
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
        budget_percentage = (total_cost / self.monthly_budget_limit) * 100

        if budget_percentage >= 95:
            budget_status = "over_budget"
        elif budget_percentage >= 85:
            budget_status = "critical_warning"
        elif budget_percentage >= 70:
            budget_status = "warning"
        else:
            budget_status = "under_budget"

        return {
            "total_cost": total_cost,
            "budget_limit": self.monthly_budget_limit,
            "budget_percentage": budget_percentage,
            "entries": current_month_entries,
            "budget_status": budget_status
        }

    def _get_jurisdiction_statuses(self) -> List[JurisdictionStatus]:
        """Get status for all configured jurisdictions"""
        from civic_services.monitoring.automated_civic_refresh import CITY_CONFIGS

        statuses = []
        cost_entries = self._get_cost_entries_today()
        failure_entries = self._get_failure_entries_24h()

        for city_id, config in CITY_CONFIGS.items():
            # Get latest refresh data
            last_refresh, opportunities_count = self._get_latest_data_for_city(city_id)

            # Calculate today's costs for this city
            today_cost = sum(
                entry['estimated_cost'] for entry in cost_entries
                if entry['city_id'] == city_id
            )

            # Calculate success rate (failures vs attempts in last 24h)
            city_failures = [
                f for f in failure_entries
                if city_id in f.get('context', '')
            ]

            city_attempts = len([
                entry for entry in self._get_cost_entries_24h()
                if entry['city_id'] == city_id
            ])

            success_rate = 100.0
            if city_attempts > 0:
                success_rate = ((city_attempts - len(city_failures)) / city_attempts) * 100

            # Determine health status
            is_healthy = (
                last_refresh is not None and
                success_rate >= 80 and
                opportunities_count > 0
            )

            statuses.append(JurisdictionStatus(
                id=city_id,
                name=config.get('jurisdiction_id', city_id).replace('-', ' ').title(),
                last_refresh=last_refresh,
                opportunities_count=opportunities_count,
                cost_today=today_cost,
                success_rate=success_rate,
                is_healthy=is_healthy
            ))

        return statuses

    def _get_latest_data_for_city(self, city_id: str) -> tuple:
        """Get latest data timestamp and opportunity count for a city"""
        try:
            schema_files = glob.glob('data/schema/newsletter_*.json')
            if not schema_files:
                return None, 0

            from civic_services.monitoring.automated_civic_refresh import CITY_CONFIGS
            target_jurisdiction = CITY_CONFIGS[city_id]['jurisdiction_id']

            latest_data = None
            latest_time = None

            for file_path in schema_files:
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)

                    jurisdiction = data.get('jurisdiction', {})
                    if jurisdiction.get('id') == target_jurisdiction:
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        if latest_time is None or file_time > latest_time:
                            latest_time = file_time
                            latest_data = data

                except Exception:
                    continue

            if latest_data:
                opportunities_count = len(latest_data.get('events', []))
                return latest_time.isoformat(), opportunities_count
            else:
                return None, 0

        except Exception:
            return None, 0

    def _get_cost_entries_today(self) -> List[Dict]:
        """Get cost entries for today"""
        return self._get_cost_entries_since(hours=24)

    def _get_cost_entries_24h(self) -> List[Dict]:
        """Get cost entries for last 24 hours"""
        return self._get_cost_entries_since(hours=24)

    def _get_cost_entries_since(self, hours: int) -> List[Dict]:
        """Get cost entries since N hours ago"""
        if not os.path.exists(self.cost_log_file):
            return []

        try:
            with open(self.cost_log_file, 'r') as f:
                cost_log = json.load(f)
        except:
            return []

        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            entry for entry in cost_log
            if datetime.fromisoformat(entry['timestamp']) > cutoff_time
        ]

    def _get_failure_rate_24h(self) -> float:
        """Calculate failure rate over last 24 hours"""
        failure_entries = self._get_failure_entries_24h()
        cost_entries = self._get_cost_entries_24h()

        if len(cost_entries) == 0:
            return 0.0

        return (len(failure_entries) / len(cost_entries)) * 100

    def _get_failure_entries_24h(self) -> List[Dict]:
        """Get failure entries for last 24 hours"""
        if not os.path.exists(self.failure_log_file):
            return []

        try:
            with open(self.failure_log_file, 'r') as f:
                failure_log = json.load(f)
        except:
            return []

        cutoff_time = datetime.now() - timedelta(hours=24)
        return [
            entry for entry in failure_log
            if datetime.fromisoformat(entry['timestamp']) > cutoff_time
        ]

    def generate_text_report(self) -> str:
        """Generate comprehensive text monitoring report"""
        health = self.get_system_health()
        jurisdictions = self._get_jurisdiction_statuses()
        budget_data = self._get_budget_status()

        report = f"""
🚀 CIVIC ENGAGEMENT PLATFORM - MONITORING REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*60}

🎯 SYSTEM HEALTH OVERVIEW
{'🔴 NEEDS ATTENTION' if health.needs_attention else '🟢 HEALTHY'}

📊 Budget Status: {health.budget_status.upper()}
   Monthly Usage: ${budget_data['total_cost']:.2f} / ${health.budget_usage:.1f}%
   Today's Cost: ${health.today_cost:.2f}
   Refresh Operations: {health.today_refresh_count}

🏛️  Regional Coverage: {health.healthy_jurisdictions}/{health.total_jurisdictions} jurisdictions healthy
   Failure Rate (24h): {health.failure_rate_24h:.1f}%

📋 JURISDICTION STATUS
{'-'*30}
"""

        for jurisdiction in jurisdictions:
            status_icon = "🟢" if jurisdiction.is_healthy else "🔴"
            last_refresh_str = "Never" if jurisdiction.last_refresh is None else datetime.fromisoformat(jurisdiction.last_refresh).strftime('%m/%d %H:%M')

            report += f"""
{status_icon} {jurisdiction.name}
   Last Refresh: {last_refresh_str}
   Opportunities: {jurisdiction.opportunities_count}
   Success Rate: {jurisdiction.success_rate:.1f}%
   Today's Cost: ${jurisdiction.cost_today:.2f}
"""

        # Add recent alerts section
        recent_alerts = self._get_recent_alerts()
        if recent_alerts:
            report += f"""
🚨 RECENT ALERTS (Last 7 Days)
{'-'*30}
"""
            for alert in recent_alerts[-5:]:  # Last 5 alerts
                report += f"   {alert['date']}: {alert['type']} - {alert['details']}\n"

        # Add budget projection
        report += self._generate_budget_projection()

        return report

    def _get_recent_alerts(self) -> List[Dict]:
        """Get recent alerts from log"""
        if not os.path.exists(self.alert_log_file):
            return []

        try:
            with open(self.alert_log_file, 'r') as f:
                alerts = json.load(f)
        except:
            return []

        # Filter to last 7 days
        cutoff_time = datetime.now() - timedelta(days=7)
        return [
            alert for alert in alerts
            if datetime.fromisoformat(alert['timestamp']) > cutoff_time
        ]

    def _generate_budget_projection(self) -> str:
        """Generate budget burn rate projection"""
        budget_data = self._get_budget_status()
        current_month_entries = budget_data['entries']

        if not current_month_entries:
            return "\n💰 BUDGET PROJECTION: No data available\n"

        # Calculate daily average
        days_in_month = datetime.now().day
        daily_average = budget_data['total_cost'] / days_in_month

        # Project to end of month
        days_remaining = 31 - days_in_month  # Approximation
        projected_total = budget_data['total_cost'] + (daily_average * days_remaining)

        projection_status = "🟢 ON TRACK"
        if projected_total > budget_data['budget_limit'] * 0.9:
            projection_status = "🟡 APPROACHING LIMIT"
        if projected_total > budget_data['budget_limit']:
            projection_status = "🔴 OVER BUDGET"

        return f"""
💰 BUDGET PROJECTION
{'-'*20}
   Daily Average: ${daily_average:.2f}
   Month Projection: ${projected_total:.2f}
   Status: {projection_status}

📈 FOUNDATION COMPLIANCE: {'PASS' if projected_total < budget_data['budget_limit'] else 'FAIL'}
"""

    def start_web_dashboard(self, port: int = 8002):
        """Start web-based monitoring dashboard"""

        class DashboardHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, dashboard_instance, *args, **kwargs):
                self.dashboard = dashboard_instance
                super().__init__(*args, **kwargs)

            def do_GET(self):
                if self.path == '/api/health':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()

                    health = self.dashboard.get_system_health()
                    jurisdictions = self.dashboard._get_jurisdiction_statuses()

                    response = {
                        'health': health.__dict__,
                        'jurisdictions': [j.__dict__ for j in jurisdictions],
                        'timestamp': datetime.now().isoformat()
                    }

                    self.wfile.write(json.dumps(response, indent=2).encode())
                elif self.path == '/' or self.path == '/dashboard':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()

                    html_content = self._generate_dashboard_html()
                    self.wfile.write(html_content.encode())
                else:
                    super().do_GET()

            def _generate_dashboard_html(self):
                """Generate HTML dashboard content"""
                return """
<!DOCTYPE html>
<html>
<head>
    <title>Civic Platform Monitoring</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .metric-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric-value { font-size: 2em; font-weight: bold; margin-bottom: 10px; }
        .metric-label { color: #666; font-size: 0.9em; }
        .status-good { color: #27ae60; }
        .status-warning { color: #f39c12; }
        .status-error { color: #e74c3c; }
        .jurisdictions { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .jurisdiction { display: flex; justify-content: space-between; align-items: center; padding: 10px; border-bottom: 1px solid #eee; }
        .jurisdiction:last-child { border-bottom: none; }
        .refresh-note { text-align: center; color: #666; margin-top: 20px; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏛️ Civic Engagement Platform - Production Monitor</h1>
            <p>Real-time system health and foundation budget compliance</p>
        </div>

        <div class="metrics">
            <div class="metric-card">
                <div class="metric-value status-good" id="budget-usage">Loading...</div>
                <div class="metric-label">Budget Usage</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="healthy-jurisdictions">Loading...</div>
                <div class="metric-label">Healthy Jurisdictions</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="today-cost">Loading...</div>
                <div class="metric-label">Today's Cost</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="failure-rate">Loading...</div>
                <div class="metric-label">24h Failure Rate</div>
            </div>
        </div>

        <div class="jurisdictions">
            <h3>Regional Jurisdiction Status</h3>
            <div id="jurisdiction-list">Loading...</div>
        </div>

        <div class="refresh-note">
            Auto-refresh every 30 seconds | Last updated: <span id="last-update">Loading...</span>
        </div>
    </div>

    <script>
        async function updateDashboard() {
            try {
                const response = await fetch('/api/health');
                const data = await response.json();

                // Update metrics
                document.getElementById('budget-usage').textContent = data.health.budget_usage.toFixed(1) + '%';
                document.getElementById('healthy-jurisdictions').textContent =
                    data.health.healthy_jurisdictions + '/' + data.health.total_jurisdictions;
                document.getElementById('today-cost').textContent = '$' + data.health.today_cost.toFixed(2);
                document.getElementById('failure-rate').textContent = data.health.failure_rate_24h.toFixed(1) + '%';

                // Update jurisdiction list
                const jurisdictionList = document.getElementById('jurisdiction-list');
                jurisdictionList.innerHTML = data.jurisdictions.map(j =>
                    `<div class="jurisdiction">
                        <span>${j.is_healthy ? '🟢' : '🔴'} ${j.name}</span>
                        <span>${j.opportunities_count} events | ${j.success_rate.toFixed(1)}% success</span>
                    </div>`
                ).join('');

                // Update timestamp
                document.getElementById('last-update').textContent = new Date(data.timestamp).toLocaleString();

                // Update budget usage color
                const budgetElement = document.getElementById('budget-usage');
                budgetElement.className = 'metric-value ' + (
                    data.health.budget_usage > 85 ? 'status-error' :
                    data.health.budget_usage > 70 ? 'status-warning' : 'status-good'
                );

            } catch (error) {
                console.error('Dashboard update failed:', error);
            }
        }

        // Initial load and periodic updates
        updateDashboard();
        setInterval(updateDashboard, 30000);
    </script>
</body>
</html>
                """

        # Create handler with dashboard instance
        handler = lambda *args, **kwargs: DashboardHandler(self, *args, **kwargs)

        print(f"🌐 Starting monitoring dashboard on http://localhost:{port}")
        print("📊 Dashboard features:")
        print("   - Real-time cost and budget tracking")
        print("   - Jurisdiction health monitoring")
        print("   - Failure rate analysis")
        print("   - Foundation compliance status")
        print()

        try:
            with socketserver.TCPServer(("", port), handler) as httpd:
                # Open browser automatically
                def open_browser():
                    time.sleep(1)
                    webbrowser.open(f'http://localhost:{port}')

                browser_thread = threading.Thread(target=open_browser)
                browser_thread.daemon = True
                browser_thread.start()

                print(f"✅ Dashboard running at http://localhost:{port}")
                print("Press Ctrl+C to stop")
                httpd.serve_forever()

        except KeyboardInterrupt:
            print("\n🛑 Dashboard stopped")
        except Exception as e:
            print(f"❌ Dashboard error: {e}")


def main():
    """Main entry point for monitoring dashboard"""
    dashboard = CivicMonitoringDashboard()

    if '--web' in sys.argv:
        port = 8002
        if '--port' in sys.argv:
            port_index = sys.argv.index('--port') + 1
            if port_index < len(sys.argv):
                port = int(sys.argv[port_index])
        dashboard.start_web_dashboard(port)

    elif '--report' in sys.argv:
        report = dashboard.generate_text_report()
        print(report)

        # Optionally save report to file
        if '--save' in sys.argv:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = f"data/monitoring_report_{timestamp}.txt"
            os.makedirs(os.path.dirname(report_file), exist_ok=True)
            with open(report_file, 'w') as f:
                f.write(report)
            print(f"\n📄 Report saved to {report_file}")

    else:
        print("Civic Platform Production Monitoring")
        print()
        print("Usage:")
        print("  python src/monitoring_dashboard.py --web          # Start web dashboard")
        print("  python src/monitoring_dashboard.py --web --port 8080  # Custom port")
        print("  python src/monitoring_dashboard.py --report       # Generate text report")
        print("  python src/monitoring_dashboard.py --report --save    # Save report to file")
        print()

        # Show quick health check
        health = dashboard.get_system_health()
        status_icon = "🔴" if health.needs_attention else "🟢"
        print(f"Quick Health Check: {status_icon}")
        print(f"  Budget Usage: {health.budget_usage:.1f}%")
        print(f"  Healthy Jurisdictions: {health.healthy_jurisdictions}/{health.total_jurisdictions}")
        print(f"  24h Failure Rate: {health.failure_rate_24h:.1f}%")


if __name__ == "__main__":
    main()