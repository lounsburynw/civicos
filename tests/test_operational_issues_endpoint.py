"""
Integration tests for operational issues API endpoint

Tests the /api/operational-issues/{jurisdiction_id} endpoint
"""

import unittest
import requests
import json
import os
import time
import subprocess
import signal


class TestOperationalIssuesEndpoint(unittest.TestCase):
    """Test operational issues API endpoint"""

    @classmethod
    def setUpClass(cls):
        """Start API server for integration tests"""
        cls.api_key = "test_api_key_123"
        os.environ['CIVIC_WEB_KEY'] = cls.api_key
        cls.base_url = "http://localhost:8001"
        cls.headers = {"Authorization": f"Bearer {cls.api_key}"}

        # Start server in background
        cls.server_process = subprocess.Popen(
            ['python', 'src/civic_api_integrated.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy()
        )

        # Wait for server to start
        time.sleep(3)

        # Verify server is running
        max_retries = 10
        for i in range(max_retries):
            try:
                response = requests.get(f"{cls.base_url}/api/jurisdictions", headers=cls.headers, timeout=2)
                if response.status_code == 200:
                    print(f"✅ Server started successfully")
                    break
            except requests.exceptions.RequestException:
                if i == max_retries - 1:
                    raise Exception("Failed to start API server")
                time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        """Stop API server"""
        if hasattr(cls, 'server_process'):
            cls.server_process.terminate()
            cls.server_process.wait(timeout=5)
            print("✅ Server stopped")

    def test_get_operational_issues_san_rafael(self):
        """Test fetching operational issues for San Rafael"""
        response = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael",
            headers=self.headers,
            params={'per_page': 5}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure
        self.assertIn('issues', data)
        self.assertIn('metadata', data)

        # Check metadata
        metadata = data['metadata']
        self.assertEqual(metadata['source'], 'seeclickfix')
        self.assertEqual(metadata['jurisdiction'], 'city-san-rafael')
        self.assertEqual(metadata['issue_type'], 'operational')
        self.assertIn('page', metadata)
        self.assertIn('per_page', metadata)

        # Check issues structure
        issues = data['issues']
        self.assertIsInstance(issues, list)
        self.assertGreater(len(issues), 0, "Should have at least one issue")

        # Check first issue structure
        if issues:
            issue = issues[0]
            self.assertIn('id', issue)
            self.assertTrue(issue['id'].startswith('scf-'))
            self.assertEqual(issue['source'], 'seeclickfix')
            self.assertEqual(issue['issue_type'], 'operational')
            self.assertIn('title', issue)
            self.assertIn('status', issue)
            self.assertIn('location', issue)
            self.assertIn('category', issue)
            self.assertIn('created_at', issue)

            # Check location structure
            location = issue['location']
            self.assertIn('address', location)
            self.assertIn('lat', location)
            self.assertIn('lng', location)

    def test_pagination(self):
        """Test pagination parameters"""
        # Page 1
        response1 = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael",
            headers=self.headers,
            params={'per_page': 2, 'page': 1}
        )

        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()
        self.assertEqual(data1['metadata']['page'], 1)
        self.assertEqual(len(data1['issues']), 2)

        # Page 2
        response2 = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael",
            headers=self.headers,
            params={'per_page': 2, 'page': 2}
        )

        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2['metadata']['page'], 2)

        # Issues should be different
        if data1['issues'] and data2['issues']:
            self.assertNotEqual(data1['issues'][0]['id'], data2['issues'][0]['id'])

    def test_status_filter_open(self):
        """Test filtering by open status"""
        response = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael",
            headers=self.headers,
            params={'status': 'open', 'per_page': 10}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # All issues should be open
        for issue in data['issues']:
            self.assertEqual(issue['status'], 'open')

    def test_status_filter_closed(self):
        """Test filtering by closed status"""
        response = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael",
            headers=self.headers,
            params={'status': 'closed', 'per_page': 10}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # All issues should be closed (if any exist)
        for issue in data['issues']:
            self.assertEqual(issue['status'], 'closed')

    def test_invalid_parameters(self):
        """Test handling of invalid parameters"""
        # Invalid per_page (should clamp to max)
        response = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael",
            headers=self.headers,
            params={'per_page': 200}  # Over max of 100
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLessEqual(len(data['issues']), 100)

        # Invalid page (should default to 1)
        response = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael",
            headers=self.headers,
            params={'page': 0}  # Should be clamped to 1
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['metadata']['page'], 1)

    def test_authentication_required(self):
        """Test that authentication is required"""
        response = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael"
            # No headers
        )

        self.assertEqual(response.status_code, 401)

    def test_different_jurisdiction(self):
        """Test with different jurisdiction"""
        # Oakland should also be accessible if SeeClickFix supports it
        response = requests.get(
            f"{self.base_url}/api/operational-issues/city-oakland",
            headers=self.headers,
            params={'per_page': 5}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['metadata']['jurisdiction'], 'city-oakland')

    def test_issue_categories(self):
        """Test that issues have proper categories"""
        response = requests.get(
            f"{self.base_url}/api/operational-issues/city-san-rafael",
            headers=self.headers,
            params={'per_page': 20}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that we have various categories
        categories = set()
        for issue in data['issues']:
            if issue['category']:
                categories.add(issue['category'])

        # San Rafael should have multiple operational issue types
        self.assertGreater(len(categories), 0, "Should have at least one category")

        # Common San Rafael categories (based on sample data)
        expected_categories = [
            'Pothole',
            'Stormwater',
            'Illegal Dumping',
            'Street Sign',
            'Trees'
        ]

        # At least one expected category should be present
        has_expected = any(
            any(expected.lower() in cat.lower() for expected in expected_categories)
            for cat in categories
        )
        self.assertTrue(has_expected, f"Should have at least one expected category. Got: {categories}")


class TestOperationalIssuesUnit(unittest.TestCase):
    """Unit tests for operational issues logic (no server required)"""

    def test_jurisdiction_id_to_place_url(self):
        """Test jurisdiction_id mapping to place_url"""
        # The endpoint should strip 'city-' prefix
        test_cases = [
            ('city-san-rafael', 'san-rafael'),
            ('city-oakland', 'oakland'),
            ('city-berkeley', 'berkeley'),
        ]

        for jurisdiction_id, expected_place_url in test_cases:
            place_url = jurisdiction_id.replace('city-', '')
            self.assertEqual(place_url, expected_place_url)


if __name__ == '__main__':
    # Run integration tests by default
    # To run only unit tests: python -m pytest tests/test_operational_issues_endpoint.py::TestOperationalIssuesUnit
    unittest.main(verbosity=2)
