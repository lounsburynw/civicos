#!/usr/bin/env python3
"""
Frontend-Backend Integration Tests
Inspired by real debugging challenges during UX testing

Tests the issues we encountered:
1. API URL configuration for file:// protocol
2. MCP availability check and response parsing  
3. Conversation API response structure validation
4. Authentication key handling across protocols
5. CORS configuration for localhost development

Run with: python tests/test_frontend_integration.py
"""

import json
import requests
import time
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

# Import config to get proper API endpoint
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from config import CivicConfig

class FrontendIntegrationTester:
    """Test suite for frontend-backend integration issues"""
    
    def __init__(self):
        # Use config system to get proper API endpoint
        config = CivicConfig()
        self.api_base_url = config.get_api_endpoint()
        self.api_key = os.getenv('CIVICOS_WEB_KEY', 'dev_key_local')
        self.test_results = []
        
    def log_test(self, test_name: str, passed: bool, message: str = ""):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.test_results.append({
            'test': test_name,
            'passed': passed,
            'message': message
        })
        print(f"{status}: {test_name}")
        if message:
            print(f"    {message}")
        print()

    def test_api_server_health(self) -> bool:
        """Test 1: Verify API server is running and healthy"""
        try:
            response = requests.get(
                f"{self.api_base_url}/health",
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=5
            )
            
            if response.status_code != 200:
                self.log_test("API Server Health", False, f"Expected 200, got {response.status_code}")
                return False
                
            data = response.json()
            required_fields = ['status', 'integration_status']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                self.log_test("API Server Health", False, f"Missing fields: {missing_fields}")
                return False
                
            self.log_test("API Server Health", True, f"Status: {data['status']}")
            return True
            
        except Exception as e:
            self.log_test("API Server Health", False, f"Connection error: {str(e)}")
            return False

    def test_mcp_availability_response(self) -> bool:
        """Test 2: MCP availability check response structure (Issue: mcpEnabled was undefined)"""
        try:
            response = requests.get(
                f"{self.api_base_url}/health",
                headers={'Authorization': f'Bearer {self.api_key}'}
            )
            
            data = response.json()
            
            # Check the exact path the frontend uses
            mcp_enabled = data.get('integration_status', {}).get('mcp_enabled')
            
            if mcp_enabled is None:
                self.log_test("MCP Availability Response", False, 
                            "integration_status.mcp_enabled is missing - frontend will show 'undefined'")
                return False
                
            if not isinstance(mcp_enabled, bool):
                self.log_test("MCP Availability Response", False,
                            f"mcp_enabled should be boolean, got {type(mcp_enabled)}")
                return False
                
            self.log_test("MCP Availability Response", True, f"mcp_enabled: {mcp_enabled}")
            return True
            
        except Exception as e:
            self.log_test("MCP Availability Response", False, str(e))
            return False

    def test_conversation_api_response_structure(self) -> bool:
        """Test 3: Conversation API response structure (Issue: data.message.content vs data.response)"""
        try:
            test_message = "Test message for response structure validation"
            response = requests.post(
                f"{self.api_base_url}/api/conversation",
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'message': test_message,
                    'city': 'San Rafael',
                    'state': 'California'
                }
            )
            
            if response.status_code != 200:
                self.log_test("Conversation API Response Structure", False,
                            f"API error: {response.status_code}")
                return False
                
            data = response.json()
            
            # Check for the field the frontend expects
            if 'response' not in data:
                self.log_test("Conversation API Response Structure", False,
                            "Missing 'response' field - frontend expects data.response")
                return False
                
            # Check that response is not empty
            if not data['response'] or not isinstance(data['response'], str):
                self.log_test("Conversation API Response Structure", False,
                            f"Invalid response field: {data.get('response')}")
                return False
                
            # Verify other expected fields
            expected_fields = ['conversation_id', 'timestamp']
            missing_fields = [field for field in expected_fields if field not in data]
            
            if missing_fields:
                self.log_test("Conversation API Response Structure", False,
                            f"Missing expected fields: {missing_fields}")
                return False
                
            self.log_test("Conversation API Response Structure", True,
                        f"Response length: {len(data['response'])} chars")
            return True
            
        except Exception as e:
            self.log_test("Conversation API Response Structure", False, str(e))
            return False

    def test_api_authentication_consistency(self) -> bool:
        """Test 4: API key authentication across all endpoints"""
        endpoints = [
            ('/api/events', 'GET'),
            ('/api/conversation', 'POST'),
            ('/health', 'GET'),
            ('/api/status', 'GET')
        ]
        
        all_passed = True
        
        for endpoint, method in endpoints:
            try:
                if method == 'GET':
                    response = requests.get(
                        f"{self.api_base_url}{endpoint}",
                        headers={'Authorization': f'Bearer {self.api_key}'}
                    )
                else:  # POST
                    response = requests.post(
                        f"{self.api_base_url}{endpoint}",
                        headers={
                            'Authorization': f'Bearer {self.api_key}',
                            'Content-Type': 'application/json'
                        },
                        json={'message': 'test', 'city': 'Test City'}
                    )
                
                if response.status_code == 401:
                    self.log_test(f"Auth - {endpoint}", False,
                                f"Authentication failed with key: {self.api_key[:8]}...")
                    all_passed = False
                elif response.status_code >= 400:
                    self.log_test(f"Auth - {endpoint}", False,
                                f"Unexpected error: {response.status_code}")
                    all_passed = False
                else:
                    self.log_test(f"Auth - {endpoint}", True,
                                f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Auth - {endpoint}", False, str(e))
                all_passed = False
                
        return all_passed

    def test_cors_headers(self) -> bool:
        """Test 5: CORS headers for file:// protocol access"""
        try:
            # Simulate browser preflight request
            response = requests.options(
                f"{self.api_base_url}/api/events",
                headers={
                    'Origin': 'null',  # file:// protocol sends null origin
                    'Access-Control-Request-Method': 'GET',
                    'Access-Control-Request-Headers': 'authorization,content-type'
                }
            )
            
            if response.status_code != 200:
                self.log_test("CORS Headers", False, f"Preflight failed: {response.status_code}")
                return False
                
            cors_headers = {
                'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
                'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
                'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers')
            }
            
            # Check that CORS headers are present
            missing_headers = [k for k, v in cors_headers.items() if not v]
            if missing_headers:
                self.log_test("CORS Headers", False, f"Missing CORS headers: {missing_headers}")
                return False
                
            self.log_test("CORS Headers", True, f"All CORS headers present")
            return True
            
        except Exception as e:
            self.log_test("CORS Headers", False, str(e))
            return False

    def test_data_pipeline_integration(self) -> bool:
        """Test 6: End-to-end data pipeline (civic_digest -> schema -> API)"""
        try:
            # Check if schema data exists
            schema_dir = Path('data/schema')
            if not schema_dir.exists():
                self.log_test("Data Pipeline Integration", False,
                            "data/schema directory not found - run civic_digest.py first")
                return False
                
            json_files = list(schema_dir.glob('newsletter_*.json'))
            if not json_files:
                self.log_test("Data Pipeline Integration", False,
                            "No schema data files found - run civic_digest.py schema first")
                return False
                
            # Test that API serves this data
            response = requests.get(
                f"{self.api_base_url}/api/events",
                headers={'Authorization': f'Bearer {self.api_key}'}
            )
            
            data = response.json()
            events = data.get('events', [])
            
            if not events:
                self.log_test("Data Pipeline Integration", False,
                            "API returns no events despite schema data existing")
                return False
                
            # Verify opportunity structure
            first_opp = events[0]
            required_fields = ['opportunity_id', 'title', 'description', 'participation_methods']
            missing_fields = [field for field in required_fields if field not in first_opp]
            
            if missing_fields:
                self.log_test("Data Pipeline Integration", False,
                            f"Event missing fields: {missing_fields}")
                return False
                
            self.log_test("Data Pipeline Integration", True,
                        f"Pipeline working: {len(events)} events loaded")
            return True
            
        except Exception as e:
            self.log_test("Data Pipeline Integration", False, str(e))
            return False

    def test_conversation_context_injection(self) -> bool:
        """Test 7: AI conversation includes civic context"""
        try:
            # Test with a civic-related question
            response = requests.post(
                f"{self.api_base_url}/api/conversation",
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'message': 'What civic events are available?',
                    'city': 'San Rafael',
                    'state': 'California'
                }
            )
            
            data = response.json()
            ai_response = data.get('response', '').lower()
            
            # Check if response includes civic context
            civic_keywords = ['san rafael', 'opportunity', 'meeting', 'participate', 'city', 'civic']
            found_keywords = [kw for kw in civic_keywords if kw in ai_response]
            
            if len(found_keywords) < 2:
                self.log_test("Conversation Context Injection", False,
                            f"AI response lacks civic context. Found keywords: {found_keywords}")
                return False
                
            # Check for specific events mentioned
            opportunities_response = requests.get(
                f"{self.api_base_url}/api/events",
                headers={'Authorization': f'Bearer {self.api_key}'}
            )
            
            if opportunities_response.status_code == 200:
                opportunities_data = opportunities_response.json()
                opportunity_titles = [opp.get('title', '') for opp in opportunities_data.get('events', [])]
                
                # Check if any opportunity titles are mentioned in AI response
                mentioned_opportunities = [title for title in opportunity_titles 
                                        if any(word.lower() in ai_response for word in title.split())]
                
                if mentioned_opportunities:
                    self.log_test("Conversation Context Injection", True,
                                f"AI mentions: {mentioned_opportunities[0][:50]}...")
                else:
                    self.log_test("Conversation Context Injection", True,
                                "AI provides civic context (keywords found)")
            else:
                self.log_test("Conversation Context Injection", True,
                            "AI provides civic context (keywords found)")
                
            return True
            
        except Exception as e:
            self.log_test("Conversation Context Injection", False, str(e))
            return False

    def run_all_tests(self) -> bool:
        """Run all integration tests"""
        print("🧪 Frontend-Backend Integration Tests")
        print("=" * 50)
        print()
        
        # Run tests in order of dependency
        tests = [
            self.test_api_server_health,
            self.test_mcp_availability_response,
            self.test_api_authentication_consistency,
            self.test_cors_headers,
            self.test_data_pipeline_integration,
            self.test_conversation_api_response_structure,
            self.test_conversation_context_injection
        ]
        
        all_passed = True
        for test in tests:
            result = test()
            if not result:
                all_passed = False
        
        # Summary
        print("=" * 50)
        passed_count = sum(1 for result in self.test_results if result['passed'])
        total_count = len(self.test_results)
        
        if all_passed:
            print(f"🎉 ALL TESTS PASSED ({passed_count}/{total_count})")
            print("Frontend-backend integration is working correctly!")
        else:
            print(f"⚠️  SOME TESTS FAILED ({passed_count}/{total_count})")
            print("Check failed tests above for integration issues.")
            
        return all_passed

def main():
    """Run the integration test suite"""
    print("Starting frontend-backend integration tests...")
    # Use config to show the correct port
    config = CivicConfig()
    api_endpoint = config.get_api_endpoint()
    print(f"Make sure src/civic_api_integrated.py is running on {api_endpoint}")
    print()
    
    tester = FrontendIntegrationTester()
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()