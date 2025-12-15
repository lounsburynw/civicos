"""
Tests for SeeClickFix API client

Tests operational complaint fetching and normalization
"""

import unittest
from unittest.mock import Mock, patch
from civic_services.seeclickfix_client import SeeClickFixClient


class TestSeeClickFixClient(unittest.TestCase):
    """Test SeeClickFix API client functionality"""

    def setUp(self):
        self.client = SeeClickFixClient()

    def test_initialization(self):
        """Test client initialization"""
        self.assertEqual(self.client.base_url, "https://seeclickfix.com/api/v2")
        self.assertIn('User-Agent', self.client.session.headers)
        self.assertIn('Accept', self.client.session.headers)

    @patch('civic_services.seeclickfix_client.requests.Session.get')
    def test_get_issues_with_place_url(self, mock_get):
        """Test fetching issues by place_url"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 123,
                'summary': 'Test Issue',
                'description': 'Test description',
                'status': 'Open',
                'lat': 37.96,
                'lng': -122.51,
                'address': '123 Test St',
                'created_at': '2025-11-11T12:00:00-05:00',
                'updated_at': '2025-11-11T12:00:00-05:00',
                'request_type': {
                    'id': 1,
                    'title': 'Pothole',
                    'organization': 'DPW'
                },
                'reporter': {
                    'id': 1,
                    'name': 'Test User',
                    'role': 'Registered User',
                    'avatar': {},
                    'civic_points': 0
                },
                'media': {},
                'html_url': 'https://seeclickfix.com/issues/123',
                'url': 'https://seeclickfix.com/api/v2/issues/123',
                'comment_url': 'https://seeclickfix.com/api/v2/issues/123/comments'
            }
        ]
        mock_get.return_value = mock_response

        result = self.client.get_issues(place_url='san-rafael', per_page=20)

        # Check API was called correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertIn('place_url', call_args[1]['params'])
        self.assertEqual(call_args[1]['params']['place_url'], 'san-rafael')

        # Check response structure
        self.assertIn('issues', result)
        self.assertIn('metadata', result)
        self.assertEqual(len(result['issues']), 1)

        # Check normalization
        issue = result['issues'][0]
        self.assertEqual(issue['id'], 'scf-123')
        self.assertEqual(issue['external_id'], 123)
        self.assertEqual(issue['source'], 'seeclickfix')
        self.assertEqual(issue['issue_type'], 'operational')
        self.assertEqual(issue['title'], 'Test Issue')
        self.assertEqual(issue['status'], 'open')

    @patch('civic_services.seeclickfix_client.requests.Session.get')
    def test_get_issues_with_lat_lng(self, mock_get):
        """Test fetching issues by lat/lng"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        self.client.get_issues(lat=37.96, lng=-122.51, radius=5000)

        # Check API was called with lat/lng/zoom
        call_args = mock_get.call_args
        params = call_args[1]['params']
        self.assertIn('lat', params)
        self.assertIn('lng', params)
        self.assertIn('zoom', params)
        self.assertEqual(params['lat'], 37.96)
        self.assertEqual(params['lng'], -122.51)

    @patch('civic_services.seeclickfix_client.requests.Session.get')
    def test_get_issues_with_status_filter(self, mock_get):
        """Test filtering by status"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        self.client.get_issues(place_url='san-rafael', status='closed')

        # Check status filter was applied
        call_args = mock_get.call_args
        self.assertEqual(call_args[1]['params']['status'], 'closed')

    @patch('civic_services.seeclickfix_client.requests.Session.get')
    def test_get_issues_pagination(self, mock_get):
        """Test pagination parameters"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        self.client.get_issues(place_url='san-rafael', per_page=50, page=2)

        # Check pagination params
        call_args = mock_get.call_args
        params = call_args[1]['params']
        self.assertEqual(params['per_page'], 50)
        self.assertEqual(params['page'], 2)

    @patch('civic_services.seeclickfix_client.requests.Session.get')
    def test_get_issue_by_id(self, mock_get):
        """Test fetching single issue by ID"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 456,
            'summary': 'Single Issue',
            'status': 'Open',
            'lat': 37.96,
            'lng': -122.51,
            'created_at': '2025-11-11T12:00:00-05:00',
            'request_type': {},
            'reporter': {},
            'media': {}
        }
        mock_get.return_value = mock_response

        issue = self.client.get_issue_by_id(456)

        # Check API endpoint
        call_args = mock_get.call_args
        self.assertIn('issues/456', call_args[0][0])

        # Check result
        self.assertIsNotNone(issue)
        self.assertEqual(issue['id'], 'scf-456')
        self.assertEqual(issue['title'], 'Single Issue')

    @patch('civic_services.seeclickfix_client.requests.Session.get')
    def test_error_handling_404(self, mock_get):
        """Test handling of 404 errors"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Not found'
        mock_get.return_value = mock_response

        issue = self.client.get_issue_by_id(999999)

        self.assertIsNone(issue)

    @patch('civic_services.seeclickfix_client.requests.Session.get')
    def test_error_handling_rate_limit(self, mock_get):
        """Test handling of rate limit errors with retry"""
        # First call: 429, second call: 200
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.text = 'Rate limited'

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = []

        mock_get.side_effect = [mock_response_429, mock_response_200]

        result = self.client.get_issues(place_url='san-rafael')

        # Should succeed after retry
        self.assertIn('issues', result)
        self.assertEqual(mock_get.call_count, 2)

    def test_zoom_calculation(self):
        """Test radius to zoom level calculation"""
        # Large radius -> low zoom
        self.assertEqual(self.client._calculate_zoom_from_radius(50000), 10)
        self.assertEqual(self.client._calculate_zoom_from_radius(20000), 11)

        # Medium radius -> medium zoom
        self.assertEqual(self.client._calculate_zoom_from_radius(5000), 13)
        self.assertEqual(self.client._calculate_zoom_from_radius(2000), 14)

        # Small radius -> high zoom
        self.assertEqual(self.client._calculate_zoom_from_radius(1000), 15)
        self.assertEqual(self.client._calculate_zoom_from_radius(500), 16)

    def test_place_url_generation(self):
        """Test place_url generation from city names"""
        self.assertEqual(
            self.client.get_place_url_for_city('San Rafael'),
            'san-rafael'
        )
        self.assertEqual(
            self.client.get_place_url_for_city('New York City'),
            'new-york'
        )
        self.assertEqual(
            self.client.get_place_url_for_city('Oakland'),
            'oakland'
        )

    def test_normalize_issue_complete(self):
        """Test complete issue normalization"""
        raw_issue = {
            'id': 789,
            'summary': 'Pothole on Main St',
            'description': 'Large pothole needs repair',
            'status': 'Acknowledged',
            'lat': 37.96,
            'lng': -122.51,
            'address': '123 Main St',
            'created_at': '2025-11-11T12:00:00-05:00',
            'updated_at': '2025-11-11T13:00:00-05:00',
            'acknowledged_at': '2025-11-11T12:30:00-05:00',
            'closed_at': None,
            'reopened_at': None,
            'rating': 3,
            'comment_count': 5,
            'request_type': {
                'id': 100,
                'title': 'Pothole/Road Condition',
                'organization': 'Department of Public Works'
            },
            'reporter': {
                'id': 555,
                'name': 'Jane Doe',
                'role': 'Registered User',
                'avatar': {'square_100x100': 'https://example.com/avatar.jpg'},
                'civic_points': 42
            },
            'media': {
                'image_full': 'https://example.com/image.jpg',
                'image_square_100x100': 'https://example.com/thumb.jpg',
                'video_url': None
            },
            'html_url': 'https://seeclickfix.com/issues/789',
            'url': 'https://seeclickfix.com/api/v2/issues/789',
            'comment_url': 'https://seeclickfix.com/api/v2/issues/789/comments',
            'point': {
                'type': 'Point',
                'coordinates': [-122.51, 37.96]
            },
            'transitions': {},
            'private_visibility': False
        }

        normalized = self.client._normalize_issue(raw_issue)

        # Core fields
        self.assertEqual(normalized['id'], 'scf-789')
        self.assertEqual(normalized['external_id'], 789)
        self.assertEqual(normalized['source'], 'seeclickfix')
        self.assertEqual(normalized['issue_type'], 'operational')
        self.assertEqual(normalized['title'], 'Pothole on Main St')
        self.assertEqual(normalized['description'], 'Large pothole needs repair')
        self.assertEqual(normalized['status'], 'acknowledged')

        # Location
        self.assertEqual(normalized['location']['address'], '123 Main St')
        self.assertEqual(normalized['location']['lat'], 37.96)
        self.assertEqual(normalized['location']['lng'], -122.51)

        # Category
        self.assertEqual(normalized['category'], 'Pothole/Road Condition')
        self.assertEqual(normalized['category_id'], 100)
        self.assertEqual(normalized['organization'], 'Department of Public Works')

        # Reporter
        self.assertEqual(normalized['reporter']['id'], 555)
        self.assertEqual(normalized['reporter']['name'], 'Jane Doe')
        self.assertEqual(normalized['reporter']['civic_points'], 42)

        # Media
        self.assertEqual(normalized['media']['image_url'], 'https://example.com/image.jpg')

        # Engagement
        self.assertEqual(normalized['rating'], 3)
        self.assertEqual(normalized['comment_count'], 5)

    def test_normalize_issue_minimal(self):
        """Test normalization with minimal required fields"""
        raw_issue = {
            'id': 111,
            'status': 'Open'
        }

        normalized = self.client._normalize_issue(raw_issue)

        # Should handle missing fields gracefully
        self.assertEqual(normalized['id'], 'scf-111')
        self.assertEqual(normalized['title'], '')
        self.assertEqual(normalized['description'], '')
        self.assertEqual(normalized['status'], 'open')
        self.assertEqual(normalized['location']['address'], '')


class TestSeeClickFixIntegration(unittest.TestCase):
    """Integration tests with real SeeClickFix API"""

    def setUp(self):
        self.client = SeeClickFixClient()

    def test_san_rafael_live_api(self):
        """Test live API call to San Rafael (integration test)"""
        result = self.client.get_issues(place_url='san-rafael', per_page=5)

        # Should get real results
        self.assertIn('issues', result)
        self.assertIn('metadata', result)
        self.assertIsInstance(result['issues'], list)

        # If issues exist, check structure
        if result['issues']:
            issue = result['issues'][0]
            self.assertIn('id', issue)
            self.assertIn('title', issue)
            self.assertIn('status', issue)
            self.assertIn('location', issue)
            self.assertIn('category', issue)
            self.assertTrue(issue['id'].startswith('scf-'))
            self.assertEqual(issue['source'], 'seeclickfix')
            self.assertEqual(issue['issue_type'], 'operational')

    def test_get_issues_summary_live(self):
        """Test summary statistics with real API"""
        summary = self.client.get_issues_summary(place_url='san-rafael')

        # Should get real summary data
        self.assertIn('total_open', summary)
        self.assertIn('total_closed', summary)
        self.assertIn('by_category', summary)
        self.assertIsInstance(summary['total_open'], int)
        self.assertIsInstance(summary['by_category'], dict)

        # San Rafael should have some open issues
        self.assertGreater(summary['total_open'], 0)


if __name__ == '__main__':
    # Run unit tests by default
    unittest.main(argv=[''], verbosity=2, exit=False)
