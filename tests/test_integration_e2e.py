#!/usr/bin/env python3
"""
End-to-End Integration Test for Newsletter → Schema → API → Frontend Workflow

Tests Priority 1 + TECHNICAL_DEBT issue #5 (Integration Testing)
Validates the complete data pipeline:
src/civic_digest.py → src/civic_schema_adapter.py → API → Conversational Interface
"""

import json
import time
import sys
import os
from pathlib import Path
import requests
import tempfile
import threading
from http.server import HTTPServer
import signal

# Import our components - handle new directory structure
try:
    # Add src directory to path for imports
    sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
    from civic_digest import main as digest_main
    from civic_schema_adapter import CivicSchemaAdapter
    from civic_api_integrated import AuthenticatedCivicAPIHandler, run_authenticated_server
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Make sure all civic components are available in src/ directory")
    sys.exit(1)

class EndToEndIntegrationTest:
    """End-to-end integration test for the complete civic pipeline"""
    
    def __init__(self):
        self.test_results = {
            'tests_run': 0,
            'tests_passed': 0,
            'tests_failed': 0,
            'failures': []
        }
        self.api_server = None
        self.server_thread = None
        self.test_port = 8081  # Different port to avoid conflicts
        
    def log(self, message, level='INFO'):
        """Standardized logging"""
        timestamp = time.strftime('%H:%M:%S')
        prefix = '✅' if level == 'PASS' else '❌' if level == 'FAIL' else '📝'
        print(f"{prefix} [{timestamp}] {message}")
    
    def assert_test(self, condition, test_name, error_message=""):
        """Assert with test tracking"""
        self.test_results['tests_run'] += 1
        if condition:
            self.test_results['tests_passed'] += 1
            self.log(f"PASS: {test_name}", 'PASS')
            return True
        else:
            self.test_results['tests_failed'] += 1
            self.test_results['failures'].append(f"{test_name}: {error_message}")
            self.log(f"FAIL: {test_name} - {error_message}", 'FAIL')
            return False
    
    def start_test_api_server(self):
        """Start API server in background thread for testing"""
        def run_server():
            try:
                self.api_server = HTTPServer(('localhost', self.test_port), AuthenticatedCivicAPIHandler)
                self.api_server.serve_forever()
            except Exception as e:
                self.log(f"Server error: {e}", 'FAIL')
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        time.sleep(2)  # Give server time to start
    
    def stop_test_api_server(self):
        """Stop the test API server"""
        if self.api_server:
            self.api_server.shutdown()
            self.api_server = None
        if self.server_thread:
            self.server_thread.join(timeout=1)
    
    def test_step_1_digest_generation(self):
        """Test Step 1: civic_digest.py generates schema-compliant data"""
        self.log("Testing Step 1: Newsletter data generation")
        
        # Clean slate - remove any existing schema files
        schema_dir = Path('data/schema')
        if schema_dir.exists():
            for file in schema_dir.glob('newsletter_*.json'):
                file.unlink()
        
        # Test civic_digest module directly (secure implementation)
        try:
            import civic_digest
            
            # Create digest instance
            digest = civic_digest.CivicDigest()
            
            # Use known working URL (same as test command)
            test_url = "https://www.cityofsanrafael.org/meetings/planning-commission-may-27-2025/"
            
            # Run the scraping test
            events = digest.scrape_meeting(test_url)
            
            success = self.assert_test(
                len(events) > 0,
                "civic_digest module runs successfully",
                f"Found {len(events)} events"
            )
            
            if not success:
                return False
                
        except Exception as e:
            self.assert_test(False, "civic_digest module completes without errors", f"Error: {str(e)}")
            return False
        
        # Check that schema files were generated
        schema_files = list(schema_dir.glob('newsletter_*.json')) if schema_dir.exists() else []
        success = self.assert_test(
            len(schema_files) > 0,
            "Schema-compliant JSON files generated",
            f"No files found in {schema_dir}"
        )
        
        if not success:
            return False
            
        # Validate schema compliance
        try:
            with open(schema_files[0], 'r') as f:
                newsletter_data = json.load(f)
            
            required_fields = ['metadata', 'content']
            for field in required_fields:
                self.assert_test(
                    field in newsletter_data,
                    f"Schema file contains required field: {field}",
                    f"Missing field: {field}"
                )
            
            # Check content structure
            if 'content' in newsletter_data and 'items' in newsletter_data['content']:
                items = newsletter_data['content']['items']
                if len(items) > 0:
                    item_fields = ['title', 'change', 'impact', 'how_to_participate']
                    for field in item_fields:
                        self.assert_test(
                            field in items[0],
                            f"Newsletter items contain field: {field}",
                            f"Missing item field: {field}"
                        )
        
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self.assert_test(False, "Schema file is valid JSON", str(e))
            return False
        
        return True
    
    def test_step_2_api_integration(self):
        """Test Step 2: API serves schema-compliant data with authentication"""
        self.log("Testing Step 2: API integration with authentication")
        
        # Start test API server
        self.start_test_api_server()
        
        try:
            # Test health endpoint (no auth required)
            health_response = requests.get(f'http://localhost:{self.test_port}/health', timeout=10)
            self.assert_test(
                health_response.status_code == 200,
                "Health endpoint responds successfully",
                f"Status: {health_response.status_code}"
            )
            
            # Test events endpoint without auth (should fail)
            unauth_response = requests.get(f'http://localhost:{self.test_port}/api/events', timeout=10)
            self.assert_test(
                unauth_response.status_code == 401,
                "Unauthenticated requests are rejected",
                f"Status: {unauth_response.status_code}"
            )
            
            # Test events endpoint with auth (should succeed)
            auth_headers = {'Authorization': 'Bearer civic_web_key'}
            auth_response = requests.get(
                f'http://localhost:{self.test_port}/api/events',
                headers=auth_headers,
                timeout=10
            )
            
            success = self.assert_test(
                auth_response.status_code == 200,
                "Authenticated API request succeeds",
                f"Status: {auth_response.status_code}, Response: {auth_response.text[:200]}"
            )
            
            if success:
                try:
                    api_data = auth_response.json()
                    
                    # Validate API response structure
                    self.assert_test(
                        'events' in api_data,
                        "API response contains events array",
                        "Missing events field"
                    )
                    
                    self.assert_test(
                        'metadata' in api_data,
                        "API response contains metadata",
                        "Missing metadata field"
                    )
                    
                    # Check if we have real data vs demo data
                    events = api_data.get('events', [])
                    if len(events) > 0:
                        first_opp = events[0]
                        required_opp_fields = ['opportunity_id', 'title', 'description', 'location']
                        for field in required_opp_fields:
                            self.assert_test(
                                field in first_opp,
                                f"Event contains field: {field}",
                                f"Missing opportunity field: {field}"
                            )
                    
                    # Check metadata for integration status
                    metadata = api_data.get('metadata', {})
                    self.assert_test(
                        'integration_status' in metadata,
                        "API includes integration status",
                        "Missing integration_status in metadata"
                    )
                
                except json.JSONDecodeError:
                    self.assert_test(False, "API response is valid JSON", "JSON decode error")
        
        except requests.RequestException as e:
            self.assert_test(False, "API server is accessible", str(e))
            return False
        finally:
            self.stop_test_api_server()
        
        return True
    
    def test_step_3_frontend_integration(self):
        """Test Step 3: Frontend can load data from authenticated API"""
        self.log("Testing Step 3: Frontend integration")
        
        # Check that the HTML file includes authentication headers
        html_file = Path('apps/civic-mcp/civic-conversational-OS.html')
        if not html_file.exists():
            self.assert_test(False, "Frontend HTML file exists", f"File not found: {html_file}")
            return False
        
        with open(html_file, 'r') as f:
            html_content = f.read()
        
        # Check for authentication integration
        auth_checks = [
            ('Authorization header in fetch', "'Authorization': 'Bearer civic_web_key'" in html_content),
            ('Error handling for auth failure', 'response.ok' in html_content or 'response.status' in html_content),
            ('Integration status function', 'showIntegrationStatus' in html_content),
            ('Fallback to demo data', 'getDemoOpportunities' in html_content)
        ]
        
        for check_name, condition in auth_checks:
            self.assert_test(condition, check_name, "Integration code not found")
        
        return True
    
    def test_step_4_complete_pipeline(self):
        """Test Step 4: Complete pipeline from digest to frontend-ready data"""
        self.log("Testing Step 4: Complete pipeline validation")
        
        # Start API server for pipeline test
        self.start_test_api_server()
        
        try:
            # Make authenticated API call
            auth_headers = {'Authorization': 'Bearer civic_web_key'}
            response = requests.get(
                f'http://localhost:{self.test_port}/api/events',
                headers=auth_headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Pipeline validation checks
                pipeline_checks = [
                    ('Data source identified', 'source_file' in data.get('metadata', {})),
                    ('City information available', data.get('metadata', {}).get('city') is not None),
                    ('Integration status marked', data.get('metadata', {}).get('integration_status') == 'schema_compliant'),
                    ('Opportunities have IDs', all('opportunity_id' in opp for opp in data.get('events', []))),
                    ('Participation methods extracted', all('participation_methods' in opp for opp in data.get('events', [])))
                ]
                
                for check_name, condition in pipeline_checks:
                    self.assert_test(condition, check_name, "Pipeline validation failed")
                
                # Log pipeline statistics
                events = data.get('events', [])
                metadata = data.get('metadata', {})
                self.log(f"📊 Pipeline Results: {len(events)} events from {metadata.get('city', 'unknown')}")
                
            else:
                self.assert_test(False, "Complete pipeline produces valid data", f"API status: {response.status_code}")
                
        except Exception as e:
            self.assert_test(False, "Complete pipeline executes without errors", str(e))
        finally:
            self.stop_test_api_server()
        
        return True
    
    def run_all_tests(self):
        """Run complete end-to-end integration test suite"""
        self.log("🚀 Starting End-to-End Integration Test Suite")
        self.log("Testing: civic_digest.py → civic_schema_adapter.py → API → Frontend")
        print("-" * 80)
        
        # Run test steps in sequence
        test_steps = [
            ("Step 1: Newsletter Generation", self.test_step_1_digest_generation),
            ("Step 2: API Integration", self.test_step_2_api_integration),
            ("Step 3: Frontend Integration", self.test_step_3_frontend_integration),
            ("Step 4: Complete Pipeline", self.test_step_4_complete_pipeline)
        ]
        
        for step_name, test_function in test_steps:
            self.log(f"\n🔄 {step_name}")
            try:
                test_function()
            except Exception as e:
                self.log(f"Test step failed with exception: {e}", 'FAIL')
                self.test_results['tests_failed'] += 1
                self.test_results['failures'].append(f"{step_name}: {e}")
        
        # Print final results
        print("\n" + "=" * 80)
        self.log("🏁 Integration Test Results")
        print(f"Tests Run: {self.test_results['tests_run']}")
        print(f"✅ Passed: {self.test_results['tests_passed']}")
        print(f"❌ Failed: {self.test_results['tests_failed']}")
        
        if self.test_results['failures']:
            print(f"\n❌ Failures:")
            for failure in self.test_results['failures']:
                print(f"  - {failure}")
        
        success_rate = (self.test_results['tests_passed'] / self.test_results['tests_run'] * 100) if self.test_results['tests_run'] > 0 else 0
        print(f"\n📊 Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print("🎉 Integration pipeline is working well!")
        elif success_rate >= 70:
            print("⚠️  Integration pipeline has some issues but core functionality works")
        else:
            print("🚨 Integration pipeline needs significant work")
        
        return success_rate >= 90

def main():
    """Main test runner"""
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("End-to-End Integration Test for Civic Conversational OS")
        print("Tests the complete pipeline: newsletter → schema → API → frontend")
        print("\nUsage:")
        print("  python tests/test_integration_e2e.py")
        print("  python tests/test_integration_e2e.py --help")
        return
    
    test_runner = EndToEndIntegrationTest()
    success = test_runner.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()