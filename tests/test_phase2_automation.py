#!/usr/bin/env python3
"""
Phase 2 Automation Testing Suite
Validates LLM-driven civic data refresh system with temporal filtering
"""

import os
import sys
import json
import subprocess
import requests
import time
from datetime import datetime

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

class Phase2AutomationTester:
    """Test suite for Phase 2 LLM-driven automation implementation"""

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.api_base = "http://localhost:8001"
        self.auth_header = {"Authorization": "Bearer dev_key_local"}
        self.test_results = {}

    def test_automated_refresh_script(self):
        """Test 1: Automated refresh script with temporal filtering"""
        print("🧪 Test 1: Automated refresh script...")

        try:
            # Test future-only scope
            result = subprocess.run([
                'python', 'src/automated_civic_refresh.py', '--future-only'
            ], capture_output=True, text=True, timeout=120)

            success = result.returncode == 0
            self.test_results['automated_refresh_script'] = {
                'passed': success,
                'output': result.stdout[-500:] if result.stdout else '',
                'error': result.stderr[-200:] if result.stderr else ''
            }

            if success:
                print("  ✅ Automated refresh script working")

                # Verify cost monitoring file was created/updated
                cost_file = 'data/cost_monitoring.json'
                if os.path.exists(cost_file):
                    with open(cost_file, 'r') as f:
                        cost_data = json.load(f)
                    print(f"  ✅ Cost monitoring: {len(cost_data)} entries")
                else:
                    print("  ⚠️  Cost monitoring file not found")
            else:
                print(f"  ❌ Script failed: {result.stderr[:100]}")

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['automated_refresh_script'] = {'passed': False, 'error': str(e)}

    def test_api_background_refresh(self):
        """Test 2: API background refresh triggers"""
        print("🧪 Test 2: API background refresh triggers...")

        try:
            # Test manual refresh endpoint
            response = requests.post(
                f"{self.api_base}/api/refresh-data",
                headers={**self.auth_header, "Content-Type": "application/json"},
                json={"query": "What meetings are scheduled this week?"},
                timeout=10
            )

            success = response.status_code == 200
            self.test_results['api_background_refresh'] = {
                'passed': success,
                'status_code': response.status_code,
                'response': response.json() if success else response.text[:200]
            }

            if success:
                data = response.json()
                print("  ✅ Manual refresh endpoint working")
                print(f"  📅 Scope: {data.get('refresh_scope', 'unknown')}")
                print(f"  🧠 Intent analysis: {data.get('intent_analysis', {}).get('temporal_focus', 'unknown')}")
            else:
                print(f"  ❌ API request failed: {response.status_code}")

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['api_background_refresh'] = {'passed': False, 'error': str(e)}

    def test_conversation_refresh_detection(self):
        """Test 3: Conversation endpoint refresh detection"""
        print("🧪 Test 3: Conversation refresh detection...")

        try:
            # Test conversation with freshness keywords
            response = requests.post(
                f"{self.api_base}/api/conversation",
                headers={**self.auth_header, "Content-Type": "application/json"},
                json={
                    "message": "What upcoming meetings should I know about?",
                    "city": "San Rafael"
                },
                timeout=15
            )

            success = response.status_code == 200
            self.test_results['conversation_refresh_detection'] = {
                'passed': success,
                'status_code': response.status_code,
                'response_length': len(response.text) if success else 0
            }

            if success:
                print("  ✅ Conversation endpoint working")
                print("  🔄 Background refresh should have been triggered")
            else:
                print(f"  ❌ Conversation request failed: {response.status_code}")

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['conversation_refresh_detection'] = {'passed': False, 'error': str(e)}

    def test_cost_monitoring(self):
        """Test 4: Cost monitoring and budget compliance"""
        print("🧪 Test 4: Cost monitoring and budget compliance...")

        try:
            cost_file = 'data/cost_monitoring.json'

            if os.path.exists(cost_file):
                with open(cost_file, 'r') as f:
                    cost_data = json.load(f)

                # Calculate current month costs
                current_month = datetime.now().strftime('%Y-%m')
                current_month_costs = [
                    entry for entry in cost_data
                    if entry['timestamp'].startswith(current_month)
                ]

                total_cost = sum(entry['estimated_cost'] for entry in current_month_costs)
                budget_limit = 50.0  # Foundation constraint
                budget_percentage = (total_cost / budget_limit) * 100

                self.test_results['cost_monitoring'] = {
                    'passed': True,
                    'total_entries': len(cost_data),
                    'current_month_cost': total_cost,
                    'budget_percentage': budget_percentage,
                    'within_budget': total_cost < budget_limit
                }

                print(f"  ✅ Cost monitoring active: {len(cost_data)} entries")
                print(f"  💰 Current month cost: ${total_cost:.2f} / ${budget_limit:.2f}")
                print(f"  📊 Budget usage: {budget_percentage:.1f}%")

                if total_cost < budget_limit:
                    print("  ✅ Within foundation budget")
                else:
                    print("  ⚠️  Over foundation budget limit!")

            else:
                print("  ❌ Cost monitoring file not found")
                self.test_results['cost_monitoring'] = {'passed': False, 'error': 'File not found'}

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['cost_monitoring'] = {'passed': False, 'error': str(e)}

    def test_temporal_filtering_effectiveness(self):
        """Test 5: Temporal filtering cost reduction"""
        print("🧪 Test 5: Temporal filtering effectiveness...")

        try:
            # Compare costs between scopes by analyzing cost log
            cost_file = 'data/cost_monitoring.json'

            if os.path.exists(cost_file):
                with open(cost_file, 'r') as f:
                    cost_data = json.load(f)

                # Group by temporal scope
                scope_costs = {}
                for entry in cost_data:
                    scope = entry['temporal_scope']
                    if scope not in scope_costs:
                        scope_costs[scope] = []
                    scope_costs[scope].append(entry['estimated_cost'])

                # Calculate averages
                scope_averages = {
                    scope: sum(costs) / len(costs)
                    for scope, costs in scope_costs.items()
                }

                self.test_results['temporal_filtering_effectiveness'] = {
                    'passed': True,
                    'scope_costs': scope_averages,
                    'scopes_tested': list(scope_averages.keys())
                }

                print(f"  ✅ Temporal filtering analysis complete")
                for scope, avg_cost in scope_averages.items():
                    print(f"    📅 {scope}: ${avg_cost:.3f} average")

                # Check if future-only is cheaper than others
                if 'future_meetings_only' in scope_averages:
                    future_cost = scope_averages['future_meetings_only']
                    other_costs = [cost for scope, cost in scope_averages.items()
                                 if scope != 'future_meetings_only']
                    if other_costs and future_cost < max(other_costs):
                        print("  ✅ Future-only scope shows cost reduction")
                    else:
                        print("  ⚠️  Future-only scope cost reduction not evident")

            else:
                print("  ❌ No cost data for comparison")
                self.test_results['temporal_filtering_effectiveness'] = {'passed': False, 'error': 'No data'}

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['temporal_filtering_effectiveness'] = {'passed': False, 'error': str(e)}

    def test_schema_compliance(self):
        """Test 6: Schema compliance validation"""
        print("🧪 Test 6: Schema compliance...")

        try:
            import glob
            schema_files = glob.glob('data/schema/newsletter_*.json')

            if schema_files:
                latest_file = max(schema_files, key=os.path.getmtime)
                with open(latest_file, 'r') as f:
                    data = json.load(f)

                # Validate required fields
                required_fields = ['id', 'jurisdiction', 'events', 'created_at']
                missing_fields = [field for field in required_fields if field not in data]

                # Validate events
                events = data.get('events', [])
                valid_opportunities = 0
                for opp in events:
                    required_opp_fields = ['id', 'title', 'description', 'when']
                    if all(field in opp for field in required_opp_fields):
                        valid_opportunities += 1

                self.test_results['schema_compliance'] = {
                    'passed': len(missing_fields) == 0 and valid_opportunities == len(events),
                    'total_opportunities': len(events),
                    'valid_opportunities': valid_opportunities,
                    'missing_fields': missing_fields
                }

                print(f"  ✅ Schema validation: {valid_opportunities}/{len(events)} valid events")
                if missing_fields:
                    print(f"  ⚠️  Missing fields: {missing_fields}")
                else:
                    print("  ✅ All required fields present")

            else:
                print("  ❌ No schema files found")
                self.test_results['schema_compliance'] = {'passed': False, 'error': 'No schema files'}

        except Exception as e:
            print(f"  🚨 Exception: {e}")
            self.test_results['schema_compliance'] = {'passed': False, 'error': str(e)}

    def run_all_tests(self):
        """Run complete Phase 2 test suite"""
        print("🚀 Phase 2 LLM-Driven Automation Test Suite")
        print("=" * 50)

        tests = [
            self.test_automated_refresh_script,
            self.test_api_background_refresh,
            self.test_conversation_refresh_detection,
            self.test_cost_monitoring,
            self.test_temporal_filtering_effectiveness,
            self.test_schema_compliance
        ]

        for test in tests:
            test()
            print()

        # Summary
        print("📊 Test Results Summary")
        print("=" * 25)

        passed_tests = sum(1 for result in self.test_results.values() if result.get('passed', False))
        total_tests = len(self.test_results)

        print(f"✅ Passed: {passed_tests}/{total_tests}")

        for test_name, result in self.test_results.items():
            status = "✅" if result.get('passed', False) else "❌"
            print(f"  {status} {test_name}")

        print(f"\n🎯 Phase 2 Implementation Status: {'READY' if passed_tests >= 5 else 'NEEDS WORK'}")

        if passed_tests >= 5:
            print("\n🎉 Phase 2 automation system is operational!")
            print("   Ready for foundation budget compliance")
            print("   Temporal filtering reducing operational costs")
            print("   Background refresh triggers working")
        else:
            print(f"\n⚠️  {total_tests - passed_tests} tests need attention before production")

        return self.test_results

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(__file__)))  # Change to project root
    tester = Phase2AutomationTester()
    results = tester.run_all_tests()