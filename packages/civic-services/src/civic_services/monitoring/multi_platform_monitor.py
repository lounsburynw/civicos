#!/usr/bin/env python3
"""
Multi-Platform Civic Data Monitoring Dashboard
Tracks costs, quality, and performance across HTML parsing and Legistar API clients
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

# Import both systems
try:
    from legistar_client import create_client as create_legistar_client, KNOWN_LEGISTAR_CLIENTS
except ImportError:
    print("❌ legistar_client not found - API monitoring disabled")
    KNOWN_LEGISTAR_CLIENTS = {}
    create_legistar_client = None

class MultiPlatformMonitor:
    """Unified monitoring for HTML parsing + Legistar API systems"""

    def __init__(self):
        self.cost_file = Path("data/cost_monitoring.json")
        self.multi_platform_file = Path("data/multi_platform_monitoring.json")

    def get_legistar_costs(self) -> Dict:
        """Calculate estimated costs for all Legistar API clients"""
        legistar_costs = {
            'total_clients': 0,
            'working_clients': 0,
            'estimated_monthly_cost': 0.0,
            'cost_per_session': 0.05,  # API calls are cheaper than HTML parsing
            'client_details': []
        }

        if not create_legistar_client:
            return legistar_costs

        print("📊 Checking Legistar API clients...")

        for client_name, config in KNOWN_LEGISTAR_CLIENTS.items():
            legistar_costs['total_clients'] += 1

            try:
                client = create_legistar_client(client_name)
                if client:
                    # Quick capability check
                    capabilities = client.probe_capabilities()
                    if capabilities.get('api_accessible'):
                        legistar_costs['working_clients'] += 1

                        # Get recent events for quality assessment
                        events = client.get_recent_events(days_back=7, days_forward=14)

                        client_detail = {
                            'client_name': client_name,
                            'status': 'working',
                            'current_events': len(events),
                            'estimated_monthly_sessions': 30,  # Once per day
                            'monthly_cost': 30 * legistar_costs['cost_per_session'],
                            'data_quality': 'good' if events else 'no_current_data',
                            'last_checked': datetime.now().isoformat()
                        }

                        legistar_costs['client_details'].append(client_detail)
                        print(f"   ✅ {client_name}: {len(events)} events")
                    else:
                        print(f"   ❌ {client_name}: API not accessible")
                        legistar_costs['client_details'].append({
                            'client_name': client_name,
                            'status': 'failed',
                            'error': 'API not accessible',
                            'last_checked': datetime.now().isoformat()
                        })
            except Exception as e:
                print(f"   ❌ {client_name}: Error - {str(e)[:50]}")
                legistar_costs['client_details'].append({
                    'client_name': client_name,
                    'status': 'error',
                    'error': str(e)[:100],
                    'last_checked': datetime.now().isoformat()
                })

        # Calculate total monthly cost
        legistar_costs['estimated_monthly_cost'] = (
            legistar_costs['working_clients'] * 30 * legistar_costs['cost_per_session']
        )

        return legistar_costs

    def get_html_parsing_costs(self) -> Dict:
        """Analyze HTML parsing costs from existing monitoring"""
        html_costs = {
            'total_sessions': 0,
            'total_cost': 0.0,
            'average_cost_per_session': 0.0,
            'monthly_estimate': 0.0,
            'cities_tracked': set(),
            'last_7_days': []
        }

        if not self.cost_file.exists():
            return html_costs

        try:
            with open(self.cost_file, 'r') as f:
                cost_data = json.load(f)

            # Analyze last 7 days
            week_ago = datetime.now() - timedelta(days=7)

            for entry in cost_data:
                timestamp = datetime.fromisoformat(entry['timestamp'])
                if timestamp >= week_ago:
                    html_costs['last_7_days'].append(entry)
                    html_costs['total_cost'] += entry.get('estimated_cost', 0)
                    html_costs['total_sessions'] += 1
                    html_costs['cities_tracked'].add(entry.get('city_id', 'unknown'))

            if html_costs['total_sessions'] > 0:
                html_costs['average_cost_per_session'] = html_costs['total_cost'] / html_costs['total_sessions']
                # Estimate monthly cost assuming similar usage
                html_costs['monthly_estimate'] = html_costs['average_cost_per_session'] * 30 * len(html_costs['cities_tracked'])

            html_costs['cities_tracked'] = list(html_costs['cities_tracked'])

        except Exception as e:
            print(f"❌ Error reading HTML cost data: {e}")

        return html_costs

    def get_civicplus_costs(self) -> Dict:
        """Analyze CivicPlus CMS costs from recent testing data"""
        civicplus_costs = {
            'total_cities': 0,
            'working_cities': 0,
            'estimated_monthly_cost': 0.0,
            'cost_per_opportunity': 0.048,  # Measured CivicPlus efficiency
            'city_details': [],
            'platform_type': 'civicplus_cms'
        }

        try:
            # Import CivicPlus configuration
            from civic_services.monitoring.automated_civic_refresh import CITY_CONFIGS

            # Count CivicPlus cities from configuration
            civicplus_cities = {city: config for city, config in CITY_CONFIGS.items()
                               if config.get('agent_type') == 'civicplus_cms'}

            civicplus_costs['total_cities'] = len(civicplus_cities)

            print("📊 Checking CivicPlus CMS cities...")

            # Analyze recent cost data for CivicPlus cities
            if self.cost_file.exists():
                with open(self.cost_file, 'r') as f:
                    cost_data = json.load(f)

                # Look for recent CivicPlus-related entries (past 7 days)
                week_ago = datetime.now() - timedelta(days=7)
                civicplus_sessions = []

                for entry in cost_data:
                    timestamp = datetime.fromisoformat(entry['timestamp'])
                    city_id = entry.get('city_id', '')

                    if timestamp >= week_ago and city_id in civicplus_cities:
                        civicplus_sessions.append(entry)

                # Calculate working cities and costs
                active_cities = set()
                total_opportunities = 0
                total_cost = 0.0

                for session in civicplus_sessions:
                    city_id = session.get('city_id')
                    events = session.get('opportunities_generated', 0)
                    cost = session.get('estimated_cost', 0)

                    if events > 0:
                        active_cities.add(city_id)
                        total_opportunities += events
                        total_cost += cost

                civicplus_costs['working_cities'] = len(active_cities)

                # Calculate efficiency metrics
                if total_opportunities > 0:
                    actual_cost_per_opportunity = total_cost / total_opportunities
                    civicplus_costs['cost_per_opportunity'] = actual_cost_per_opportunity

                # Estimate monthly costs based on current CivicPlus efficiency
                # Assume each city generates 3 events per month on average
                opportunities_per_city_per_month = 3
                civicplus_costs['estimated_monthly_cost'] = (
                    civicplus_costs['total_cities'] *
                    opportunities_per_city_per_month *
                    civicplus_costs['cost_per_opportunity']
                )

                # Create city details
                for city, config in civicplus_cities.items():
                    is_active = city in active_cities

                    city_opportunities = sum(
                        s.get('opportunities_generated', 0)
                        for s in civicplus_sessions
                        if s.get('city_id') == city
                    )

                    city_detail = {
                        'city_name': city,
                        'status': 'working' if is_active else 'configured',
                        'recent_opportunities': city_opportunities,
                        'estimated_monthly_sessions': 10,  # ~3 events per session
                        'monthly_cost': opportunities_per_city_per_month * civicplus_costs['cost_per_opportunity'],
                        'efficiency_rating': 'high' if civicplus_costs['cost_per_opportunity'] <= 0.05 else 'medium',
                        'last_checked': datetime.now().isoformat()
                    }

                    civicplus_costs['city_details'].append(city_detail)

                    status_icon = "✅" if is_active else "⚙️"
                    print(f"   {status_icon} {city}: {city_opportunities} events (${city_detail['monthly_cost']:.3f}/month)")

            else:
                print("   ⚠️ No cost monitoring data available for CivicPlus analysis")

        except ImportError:
            print("   ❌ Could not import CivicPlus configuration")
        except Exception as e:
            print(f"   ❌ Error analyzing CivicPlus costs: {str(e)[:50]}")

        return civicplus_costs

    def _generate_cost_comparison(self, legistar_data: Dict, html_data: Dict, civicplus_data: Dict) -> str:
        """Generate cost efficiency comparison across all platforms"""
        legistar_cost = legistar_data['cost_per_session']
        html_cost = html_data['average_cost_per_session'] if html_data['average_cost_per_session'] > 0 else 0.08
        civicplus_cost = civicplus_data['cost_per_opportunity']

        # Find the most efficient platform
        costs = [
            ('Legistar API', legistar_cost),
            ('HTML parsing', html_cost),
            ('CivicPlus CMS', civicplus_cost)
        ]
        costs.sort(key=lambda x: x[1])

        most_efficient = costs[0]
        least_efficient = costs[-1]

        efficiency_ratio = least_efficient[1] / most_efficient[1] if most_efficient[1] > 0 else 0

        return f"{most_efficient[0]} most efficient (${most_efficient[1]:.3f}), {efficiency_ratio:.1f}x better than {least_efficient[0]}"

    def generate_monitoring_report(self) -> Dict:
        """Generate comprehensive monitoring report"""
        print("🚀 MULTI-PLATFORM CIVIC DATA MONITORING")
        print("=" * 60)

        legistar_data = self.get_legistar_costs()
        html_data = self.get_html_parsing_costs()
        civicplus_data = self.get_civicplus_costs()

        total_platforms = (
            legistar_data['working_clients'] +
            len(html_data['cities_tracked']) +
            civicplus_data['working_cities']
        )

        total_monthly_cost = (
            legistar_data['estimated_monthly_cost'] +
            html_data['monthly_estimate'] +
            civicplus_data['estimated_monthly_cost']
        )

        report = {
            'timestamp': datetime.now().isoformat(),
            'legistar_api': legistar_data,
            'html_parsing': html_data,
            'civicplus_cms': civicplus_data,
            'summary': {
                'total_working_platforms': total_platforms,
                'estimated_monthly_cost': total_monthly_cost,
                'cost_breakdown': {
                    'legistar_api': legistar_data['estimated_monthly_cost'],
                    'html_parsing': html_data['monthly_estimate'],
                    'civicplus_cms': civicplus_data['estimated_monthly_cost']
                },
                'platform_efficiency': {
                    'legistar_cost_per_session': legistar_data['cost_per_session'],
                    'html_cost_per_session': html_data['average_cost_per_session'],
                    'civicplus_cost_per_opportunity': civicplus_data['cost_per_opportunity'],
                    'cost_comparison': self._generate_cost_comparison(legistar_data, html_data, civicplus_data)
                }
            }
        }

        # Print summary
        print(f"\n📈 PLATFORM SUMMARY")
        print(f"   • Legistar API clients: {legistar_data['working_clients']} working")
        print(f"   • HTML parsing cities: {len(html_data['cities_tracked'])}")
        print(f"   • CivicPlus CMS cities: {civicplus_data['working_cities']} working / {civicplus_data['total_cities']} configured")
        print(f"   • Total platforms: {report['summary']['total_working_platforms']}")

        print(f"\n💰 COST ANALYSIS")
        print(f"   • Legistar monthly: ${legistar_data['estimated_monthly_cost']:.2f}")
        print(f"   • HTML parsing monthly: ${html_data['monthly_estimate']:.2f}")
        print(f"   • CivicPlus monthly: ${civicplus_data['estimated_monthly_cost']:.2f}")
        print(f"   • Total monthly estimate: ${report['summary']['estimated_monthly_cost']:.2f}")
        print(f"   • {report['summary']['platform_efficiency']['cost_comparison']}")

        print(f"\n🏛️  WORKING PLATFORMS:")
        for client in legistar_data['client_details']:
            if client['status'] == 'working':
                print(f"   • {client['client_name']} (API): {client['current_events']} events")

        for city in html_data['cities_tracked']:
            print(f"   • {city} (HTML): Active")

        for city_detail in civicplus_data['city_details']:
            if city_detail['status'] == 'working':
                print(f"   • {city_detail['city_name']} (CivicPlus): {city_detail['recent_opportunities']} events")

        return report

    def save_monitoring_data(self, report: Dict) -> None:
        """Save monitoring report to file"""
        try:
            # Load existing data
            monitoring_data = []
            if self.multi_platform_file.exists():
                with open(self.multi_platform_file, 'r') as f:
                    monitoring_data = json.load(f)

            # Add new report
            monitoring_data.append(report)

            # Keep only last 30 days
            cutoff = datetime.now() - timedelta(days=30)
            monitoring_data = [
                entry for entry in monitoring_data
                if datetime.fromisoformat(entry['timestamp']) >= cutoff
            ]

            # Save updated data
            os.makedirs(self.multi_platform_file.parent, exist_ok=True)
            with open(self.multi_platform_file, 'w') as f:
                json.dump(monitoring_data, f, indent=2)

            print(f"\n💾 Monitoring data saved to {self.multi_platform_file}")

        except Exception as e:
            print(f"❌ Error saving monitoring data: {e}")

    def check_foundation_budget_compliance(self, report: Dict) -> None:
        """Check if costs are within foundation budget guidelines"""
        monthly_cost = report['summary']['estimated_monthly_cost']

        print(f"\n🏦 FOUNDATION BUDGET COMPLIANCE")
        print("=" * 40)

        # Budget thresholds based on your strategic plan
        budget_thresholds = {
            'pilot': 50.0,      # Phase 1: Under $50/month
            'scaling': 200.0,   # Phase 2: Under $200/month
            'production': 500.0 # Phase 3: Under $500/month
        }

        for phase, threshold in budget_thresholds.items():
            status = "✅" if monthly_cost <= threshold else "⚠️"
            print(f"   {status} {phase.title()} phase: ${monthly_cost:.2f} / ${threshold:.2f}")

        if monthly_cost <= budget_thresholds['pilot']:
            print(f"\n🎯 EXCELLENT: Under pilot budget - ready for foundation grant applications")
        elif monthly_cost <= budget_thresholds['scaling']:
            print(f"\n✅ GOOD: Scaling budget compliant - sustainable for Phase 2")
        else:
            print(f"\n⚠️  HIGH COST: Review platform mix for cost optimization")

def main():
    monitor = MultiPlatformMonitor()
    report = monitor.generate_monitoring_report()
    monitor.save_monitoring_data(report)
    monitor.check_foundation_budget_compliance(report)

    print(f"\n🚀 MONITORING COMPLETE")
    print(f"   Report saved: {monitor.multi_platform_file}")
    print(f"   Next run: Add to automated_civic_refresh.py")

if __name__ == "__main__":
    main()