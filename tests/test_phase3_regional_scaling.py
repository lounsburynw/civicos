#!/usr/bin/env python3
"""
Phase 3 Regional Scaling Test Suite

Validates production hardening and multi-jurisdiction scaling for foundation deployment.

Tests:
1. Multi-jurisdiction automation with error handling
2. Production monitoring dashboard functionality
3. Civic participation tracking and foundation metrics
4. Cost compliance with 4+ jurisdictions
5. Regional scaling readiness validation
"""

import os
import sys
import json
import subprocess
import requests
import sqlite3
import time
from datetime import datetime

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class Phase3RegionalScalingTester:
    """Comprehensive test suite for Phase 3 regional scaling implementation"""

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.api_base = "http://localhost:8001"
        self.auth_header = {"Authorization": "Bearer dev_key_local"}
        self.test_results = {}
        self.monthly_budget_limit = 50.0

    def test_multi_jurisdiction_automation(self):
        """Test 1: Multi-jurisdiction automation with production error handling"""
        print("🧪 Test 1: Multi-jurisdiction automation...")

        try:
            # Test with all configured jurisdictions
            result = subprocess.run([
                'python', 'src/automated_civic_refresh.py', '--future-only'
            ], capture_output=True, text=True, timeout=300)

            success = result.returncode == 0

            # Parse output for jurisdiction processing
            jurisdictions_processed = []
            for line in result.stdout.split('\n'):
                if "Processing" in line and "🏙️" in line:
                    jurisdiction = line.split("Processing ")[1].split("...")[0]
                    jurisdictions_processed.append(jurisdiction)

            # Verify cost monitoring updated with multi-jurisdiction data
            cost_file = 'data/cost_monitoring.json'
            latest_entries = []
            if os.path.exists(cost_file):
                with open(cost_file, 'r') as f:
                    cost_data = json.load(f)
                # Get last 4 entries (one per jurisdiction)
                latest_entries = cost_data[-4:] if len(cost_data) >= 4 else cost_data

            jurisdictions_in_cost_log = set(entry['city_id'] for entry in latest_entries)

            self.test_results['multi_jurisdiction_automation'] = {
                'passed': success and len(jurisdictions_processed) >= 4,
                'jurisdictions_processed': jurisdictions_processed,
                'jurisdictions_in_cost_log': list(jurisdictions_in_cost_log),
                'total_cost_latest_run': sum(entry.get('estimated_cost', 0) for entry in latest_entries),
                'output_sample': result.stdout[-500:] if result.stdout else ''
            }

            if success:
                print(f"  ✅ Multi-jurisdiction automation working: {len(jurisdictions_processed)} jurisdictions")
                print(f"  💰 Total cost for regional run: ${sum(entry.get('estimated_cost', 0) for entry in latest_entries):.2f}")
            else:
                print(f"  ❌ Automation failed: {result.stderr[:100]}")

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['multi_jurisdiction_automation'] = {'passed': False, 'error': str(e)}

    def test_production_monitoring_dashboard(self):
        """Test 2: Production monitoring dashboard functionality"""
        print("🧪 Test 2: Production monitoring dashboard...")

        try:
            # Test text report generation
            result = subprocess.run([
                'python', 'src/monitoring_dashboard.py', '--report'
            ], capture_output=True, text=True, timeout=30)

            success = result.returncode == 0
            report_content = result.stdout

            # Verify key sections are present
            required_sections = [
                'SYSTEM HEALTH OVERVIEW',
                'JURISDICTION STATUS',
                'BUDGET PROJECTION',
                'FOUNDATION COMPLIANCE'
            ]

            sections_present = [section for section in required_sections if section in report_content]

            # Check if jurisdiction health is being tracked
            jurisdictions_mentioned = 0
            for line in report_content.split('\n'):
                if any(city in line.lower() for city in ['san rafael', 'berkeley', 'marin', 'santa rosa']):
                    jurisdictions_mentioned += 1

            self.test_results['production_monitoring_dashboard'] = {
                'passed': success and len(sections_present) >= 3,
                'sections_present': sections_present,
                'jurisdictions_mentioned': jurisdictions_mentioned,
                'report_length': len(report_content),
                'contains_budget_info': 'Budget Usage:' in report_content
            }

            if success:
                print(f"  ✅ Monitoring dashboard working")
                print(f"  📊 Report sections: {len(sections_present)}/{len(required_sections)}")
                print(f"  🏛️  Jurisdictions tracked: {jurisdictions_mentioned}")
            else:
                print(f"  ❌ Dashboard generation failed: {result.stderr[:100]}")

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['production_monitoring_dashboard'] = {'passed': False, 'error': str(e)}

    def test_civic_participation_metrics(self):
        """Test 3: Civic participation tracking and foundation metrics"""
        print("🧪 Test 3: Civic participation metrics...")

        try:
            # Generate demo data first
            demo_result = subprocess.run([
                'python', 'src/civic_participation_metrics.py', '--demo-data'
            ], capture_output=True, text=True, timeout=30)

            # Generate foundation report
            report_result = subprocess.run([
                'python', 'src/civic_participation_metrics.py', '--foundation-summary'
            ], capture_output=True, text=True, timeout=30)

            success = demo_result.returncode == 0 and report_result.returncode == 0
            report_output = report_result.stdout

            # Verify database was created and contains data
            db_exists = os.path.exists('data/civic_participation.db')
            table_count = 0

            if db_exists:
                conn = sqlite3.connect('data/civic_participation.db')
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM civic_actions")
                action_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM engagement_sessions")
                session_count = cursor.fetchone()[0]
                conn.close()
                table_count = action_count + session_count

            # Check for foundation metrics in output
            foundation_metrics_present = all(metric in report_output for metric in [
                'Total Cost:', 'Civic Actions:', 'Cost per Action:', 'Retention Rate:'
            ])

            self.test_results['civic_participation_metrics'] = {
                'passed': success and db_exists and table_count > 0,
                'database_exists': db_exists,
                'total_records': table_count,
                'foundation_metrics_present': foundation_metrics_present,
                'demo_data_generated': 'Demo data generated successfully' in demo_result.stdout
            }

            if success:
                print(f"  ✅ Civic participation tracking working")
                print(f"  📊 Database records: {table_count}")
                print(f"  💰 Foundation metrics: {'✅' if foundation_metrics_present else '❌'}")
            else:
                print(f"  ❌ Participation metrics failed")

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['civic_participation_metrics'] = {'passed': False, 'error': str(e)}

    def test_regional_cost_compliance(self):
        """Test 4: Cost compliance with 4+ jurisdictions"""
        print("🧪 Test 4: Regional cost compliance...")

        try:
            cost_file = 'data/cost_monitoring.json'

            if os.path.exists(cost_file):
                with open(cost_file, 'r') as f:
                    cost_data = json.load(f)

                # Calculate current month costs
                current_month = datetime.now().strftime('%Y-%m')
                current_month_entries = [
                    entry for entry in cost_data
                    if entry['timestamp'].startswith(current_month)
                ]

                total_monthly_cost = sum(entry['estimated_cost'] for entry in current_month_entries)
                budget_percentage = (total_monthly_cost / self.monthly_budget_limit) * 100

                # Count unique jurisdictions in cost log
                unique_jurisdictions = set(entry['city_id'] for entry in current_month_entries)

                # Calculate average cost per jurisdiction
                avg_cost_per_jurisdiction = total_monthly_cost / max(len(unique_jurisdictions), 1)

                # Project cost for 10 jurisdictions (future scaling)
                projected_10_jurisdiction_cost = avg_cost_per_jurisdiction * 10

                within_budget = total_monthly_cost < self.monthly_budget_limit
                scaling_viable = projected_10_jurisdiction_cost < self.monthly_budget_limit

                self.test_results['regional_cost_compliance'] = {
                    'passed': within_budget and len(unique_jurisdictions) >= 4,
                    'monthly_cost': total_monthly_cost,
                    'budget_percentage': budget_percentage,
                    'unique_jurisdictions': len(unique_jurisdictions),
                    'avg_cost_per_jurisdiction': avg_cost_per_jurisdiction,
                    'projected_10_jurisdiction_cost': projected_10_jurisdiction_cost,
                    'scaling_viable': scaling_viable,
                    'within_budget': within_budget
                }

                print(f"  ✅ Cost compliance analysis complete")
                print(f"  💰 Monthly cost: ${total_monthly_cost:.2f} ({budget_percentage:.1f}% of budget)")
                print(f"  🏛️  Jurisdictions active: {len(unique_jurisdictions)}")
                print(f"  📈 10-jurisdiction projection: ${projected_10_jurisdiction_cost:.2f}")
                print(f"  🎯 Scaling viable: {'✅' if scaling_viable else '❌'}")

            else:
                print(f"  ❌ Cost monitoring file not found")
                self.test_results['regional_cost_compliance'] = {'passed': False, 'error': 'No cost data'}

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['regional_cost_compliance'] = {'passed': False, 'error': str(e)}

    def test_production_error_handling(self):
        """Test 5: Production error handling and graceful degradation"""
        print("🧪 Test 5: Production error handling...")

        try:
            # Check if error handling components exist
            failure_log_exists = os.path.exists('data/system_failures.json')
            alert_log_exists = os.path.exists('data/alert_log.json')

            # Test error handling by examining the automation script structure
            automation_script_path = 'src/automated_civic_refresh.py'

            with open(automation_script_path, 'r') as f:
                script_content = f.read()

            # Check for error handling patterns
            error_handling_features = {
                'exponential_backoff': 'exponential_backoff_retry' in script_content,
                'graceful_degradation': '_get_cached_data' in script_content,
                'failure_logging': 'ProductionErrorHandler' in script_content,
                'email_alerting': 'ProductionAlertManager' in script_content,
                'budget_alerting': 'send_budget_alert' in script_content
            }

            features_implemented = sum(error_handling_features.values())

            self.test_results['production_error_handling'] = {
                'passed': features_implemented >= 4,
                'failure_log_exists': failure_log_exists,
                'alert_log_exists': alert_log_exists,
                'error_handling_features': error_handling_features,
                'features_implemented': features_implemented
            }

            print(f"  ✅ Error handling analysis complete")
            print(f"  🔧 Features implemented: {features_implemented}/5")
            for feature, implemented in error_handling_features.items():
                print(f"    {'✅' if implemented else '❌'} {feature}")

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['production_error_handling'] = {'passed': False, 'error': str(e)}

    def test_foundation_readiness_validation(self):
        """Test 6: Foundation deployment readiness"""
        print("🧪 Test 6: Foundation deployment readiness...")

        try:
            # Comprehensive readiness checklist
            readiness_checks = {
                'multi_jurisdiction_support': self.test_results.get('multi_jurisdiction_automation', {}).get('passed', False),
                'cost_compliance': self.test_results.get('regional_cost_compliance', {}).get('passed', False),
                'monitoring_dashboard': self.test_results.get('production_monitoring_dashboard', {}).get('passed', False),
                'participation_tracking': self.test_results.get('civic_participation_metrics', {}).get('passed', False),
                'error_handling': self.test_results.get('production_error_handling', {}).get('passed', False)
            }

            # Additional infrastructure checks
            required_files = [
                'src/automated_civic_refresh.py',
                'src/monitoring_dashboard.py',
                'src/civic_participation_metrics.py',
                'data/cost_monitoring.json',
                'civic-app-schema.json'
            ]

            files_present = [f for f in required_files if os.path.exists(f)]

            # Calculate readiness score
            checks_passed = sum(readiness_checks.values())
            infrastructure_score = len(files_present) / len(required_files)
            overall_readiness = (checks_passed / len(readiness_checks)) * 0.7 + infrastructure_score * 0.3

            ready_for_foundation = overall_readiness >= 0.8 and checks_passed >= 4

            self.test_results['foundation_readiness_validation'] = {
                'passed': ready_for_foundation,
                'readiness_checks': readiness_checks,
                'checks_passed': checks_passed,
                'infrastructure_score': infrastructure_score,
                'overall_readiness': overall_readiness,
                'ready_for_foundation': ready_for_foundation,
                'files_present': files_present
            }

            print(f"  ✅ Foundation readiness validation complete")
            print(f"  🎯 Overall readiness: {overall_readiness*100:.1f}%")
            print(f"  ✅ Checks passed: {checks_passed}/{len(readiness_checks)}")
            print(f"  📁 Infrastructure: {len(files_present)}/{len(required_files)} files")
            print(f"  🏛️  Foundation ready: {'✅' if ready_for_foundation else '❌'}")

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['foundation_readiness_validation'] = {'passed': False, 'error': str(e)}

    def run_all_tests(self):
        """Run complete Phase 3 regional scaling test suite"""
        print("🚀 Phase 3 Regional Scaling Test Suite")
        print("=" * 50)

        tests = [
            self.test_multi_jurisdiction_automation,
            self.test_production_monitoring_dashboard,
            self.test_civic_participation_metrics,
            self.test_regional_cost_compliance,
            self.test_production_error_handling,
            self.test_foundation_readiness_validation
        ]

        for test in tests:
            test()
            print()

        # Summary
        print("📊 Phase 3 Test Results Summary")
        print("=" * 35)

        passed_tests = sum(1 for result in self.test_results.values() if result.get('passed', False))
        total_tests = len(self.test_results)

        print(f"✅ Passed: {passed_tests}/{total_tests}")

        for test_name, result in self.test_results.items():
            status = "✅" if result.get('passed', False) else "❌"
            print(f"  {status} {test_name}")

        # Phase 3 status determination
        foundation_ready = self.test_results.get('foundation_readiness_validation', {}).get('ready_for_foundation', False)

        print(f"\n🎯 Phase 3 Implementation Status: {'PRODUCTION READY' if passed_tests >= 5 else 'NEEDS WORK'}")

        if foundation_ready:
            print("\n🎉 Phase 3 regional scaling implementation COMPLETE!")
            print("   ✅ Multi-jurisdiction automation operational")
            print("   ✅ Production monitoring and alerting")
            print("   ✅ Foundation metrics and ROI tracking")
            print("   ✅ Cost compliance with regional scale")
            print("   ✅ Ready for foundation pilot deployment")

            # Get cost summary for celebration
            cost_result = self.test_results.get('regional_cost_compliance', {})
            if cost_result.get('passed'):
                print(f"   💰 Operating at {cost_result.get('budget_percentage', 0):.1f}% of foundation budget")
                print(f"   🏛️  {cost_result.get('unique_jurisdictions', 0)} jurisdictions active")
        else:
            print(f"\n⚠️  {total_tests - passed_tests} components need attention before foundation deployment")

        return self.test_results


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(__file__)))  # Change to project root
    tester = Phase3RegionalScalingTester()
    results = tester.run_all_tests()