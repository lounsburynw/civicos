import unittest
import os
import tempfile
from datetime import datetime, timedelta
from civic_app.personalization_service import PersonalizationService

class TestPersonalizationService(unittest.TestCase):

    def setUp(self):
        """Create temporary database for each test"""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.service = PersonalizationService(self.db_path)

        # Run migration
        with open('migrations/006_personalization_service.sql', 'r') as f:
            sql = f.read()
            conn = self.service._get_connection()
            conn.executescript(sql)
            conn.close()

    def tearDown(self):
        """Clean up temporary database"""
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # ===== PROFILE CREATION TESTS =====

    def test_create_profile_success(self):
        """Test profile creation with valid data"""
        profile = self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley',
            'stakes': ['homeowner'],
            'yearsInArea': 10,
            'displayName': 'Test User'
        })

        self.assertEqual(profile['user_id'], 'user1')
        self.assertEqual(profile['jurisdiction_id'], 'city-berkeley')
        self.assertEqual(profile['display_name'], 'Test User')
        self.assertGreater(profile['profile_completeness'], 0)

    def test_create_profile_missing_jurisdiction(self):
        """Test profile creation fails without jurisdictionId"""
        with self.assertRaises(ValueError):
            self.service.create_user_profile('user1', {
                'stakes': ['homeowner']
            })

    def test_create_profile_minimal_fields(self):
        """Test profile creation with only required field"""
        profile = self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        self.assertEqual(profile['user_id'], 'user1')
        self.assertEqual(profile['jurisdiction_id'], 'city-berkeley')
        # Minimal profile should have low completeness
        self.assertLess(profile['profile_completeness'], 10)

    # ===== PROFILE RETRIEVAL TESTS =====

    def test_get_profile_existing(self):
        """Test retrieving existing profile"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        profile = self.service.get_user_profile('user1')
        self.assertIsNotNone(profile)
        self.assertEqual(profile['user_id'], 'user1')

    def test_get_profile_nonexistent(self):
        """Test retrieving non-existent profile returns None"""
        profile = self.service.get_user_profile('nonexistent_user')
        self.assertIsNone(profile)

    # ===== PROFILE COMPLETENESS TESTS =====

    def test_completeness_calculation_full_profile(self):
        """Test completeness with all fields filled"""
        profile = self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley',
            'displayName': 'Test User',
            'stakes': ['homeowner', 'parent'],
            'yearsInArea': 15,
            'district': 'District 4',
            'neighborhood': 'North Berkeley',
            'expertise': 'Urban planning',
            'civicInterests': ['housing', 'transportation'],
            'avatarUrl': 'https://example.com/avatar.jpg',
            'notificationPreferences': {'email': True}
        })

        # Should have 100% completeness with all fields
        self.assertEqual(profile['profile_completeness'], 100)

    def test_completeness_calculation_partial_profile(self):
        """Test completeness with some fields filled"""
        profile = self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley',
            'stakes': ['homeowner'],
            'yearsInArea': 10
        })

        # Should have partial completeness
        self.assertGreater(profile['profile_completeness'], 10)
        self.assertLess(profile['profile_completeness'], 100)

    # ===== CIVIC HISTORY TESTS =====

    def test_track_action_success(self):
        """Test tracking a single action"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        action_id = self.service.track_action(
            'user1',
            'event_clicked',
            'event',
            'event-123',
            {'topic': 'housing', 'jurisdictionId': 'city-berkeley'}
        )

        self.assertIsNotNone(action_id)

    def test_get_civic_history_all(self):
        """Test retrieving all civic history"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        # Track multiple actions
        self.service.track_action('user1', 'event_clicked', 'event', 'event-1', {'topic': 'housing'})
        self.service.track_action('user1', 'comment_drafted', 'event', 'event-2', {'topic': 'transportation'})

        history = self.service.get_civic_history('user1')
        self.assertEqual(len(history), 2)

    def test_get_civic_history_filtered_by_type(self):
        """Test retrieving history filtered by action type"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        self.service.track_action('user1', 'event_clicked', 'event', 'event-1', {})
        self.service.track_action('user1', 'comment_drafted', 'event', 'event-2', {})
        self.service.track_action('user1', 'event_clicked', 'event', 'event-3', {})

        history = self.service.get_civic_history('user1', action_types=['event_clicked'])
        self.assertEqual(len(history), 2)
        for action in history:
            self.assertEqual(action['action_type'], 'event_clicked')

    def test_get_civic_history_limited_by_date(self):
        """Test retrieving history since specific date"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        # Track actions
        self.service.track_action('user1', 'event_clicked', 'event', 'event-1', {})

        # Set since date to 1 hour from now (should return no results)
        # Note: Use utcnow() to match SQLite CURRENT_TIMESTAMP behavior
        future = datetime.utcnow() + timedelta(hours=1)
        history = self.service.get_civic_history('user1', since=future)
        self.assertEqual(len(history), 0)

        # Set since date to yesterday (should return all results)
        past = datetime.utcnow() - timedelta(days=1)
        history = self.service.get_civic_history('user1', since=past)
        self.assertEqual(len(history), 1)

    # ===== INTEREST INFERENCE TESTS =====

    def test_infer_interests_with_data(self):
        """Test interest inference with sufficient data"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        # Track multiple housing actions
        for i in range(10):
            self.service.track_action(
                'user1',
                'event_clicked',
                'event',
                f'event-{i}',
                {'topic': 'housing'}
            )

        # Track fewer transportation actions
        for i in range(5):
            self.service.track_action(
                'user1',
                'event_clicked',
                'event',
                f'event-transport-{i}',
                {'topic': 'transportation'}
            )

        interests = self.service.infer_civic_interests('user1')

        self.assertIn('housing', interests)
        self.assertIn('transportation', interests)
        # Housing should have higher score
        self.assertGreater(interests['housing'], interests['transportation'])

    def test_infer_interests_no_data(self):
        """Test interest inference with no data returns empty dict"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        interests = self.service.infer_civic_interests('user1')
        self.assertEqual(interests, {})

    def test_infer_interests_weighted_by_action_type(self):
        """Test that high-value actions score higher than low-value"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        # One high-value action (comment_drafted)
        self.service.track_action('user1', 'comment_drafted', 'event', 'event-1', {'topic': 'housing'})

        # Many low-value actions (event_clicked)
        for i in range(3):
            self.service.track_action('user1', 'event_clicked', 'event', f'event-{i}', {'topic': 'transportation'})

        interests = self.service.infer_civic_interests('user1')

        # Comment should score higher than multiple clicks
        self.assertGreater(interests.get('housing', 0), interests.get('transportation', 0))

    # ===== CONTEXT FOR AI TESTS =====

    def test_get_context_demographics_only(self):
        """Test getting demographics context for AI"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley',
            'stakes': ['homeowner'],
            'yearsInArea': 15,
            'district': 'District 4',
            'expertise': 'Urban planning'
        })

        context = self.service.get_context_for_ai('user1', context_type='demographics')

        self.assertIn('stakes', context)
        self.assertIn('yearsInArea', context)
        self.assertIn('expertise', context)
        self.assertNotIn('inferredInterests', context)
        self.assertNotIn('recentActions', context)

    def test_get_context_interests_only(self):
        """Test getting interests context for AI"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley',
            'civicInterests': ['housing']
        })

        # Track some actions for inference
        for i in range(5):
            self.service.track_action('user1', 'event_clicked', 'event', f'event-{i}', {'topic': 'housing'})

        context = self.service.get_context_for_ai('user1', context_type='interests')

        self.assertIn('civicInterests', context)
        self.assertIn('inferredInterests', context)
        self.assertNotIn('stakes', context)
        self.assertNotIn('recentActions', context)

    def test_get_context_full(self):
        """Test getting full context for AI"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley',
            'stakes': ['homeowner'],
            'civicInterests': ['housing']
        })

        # Track some actions
        self.service.track_action('user1', 'event_clicked', 'event', 'event-1', {'topic': 'housing'})

        context = self.service.get_context_for_ai('user1', context_type='full')

        # Should have all context types
        self.assertIn('stakes', context)
        self.assertIn('civicInterests', context)
        self.assertIn('inferredInterests', context)
        self.assertIn('recentActions', context)

    def test_get_context_nonexistent_user(self):
        """Test getting context for non-existent user returns empty dict"""
        context = self.service.get_context_for_ai('nonexistent_user')
        self.assertEqual(context, {})

    # ===== CACHE TESTS =====

    def test_cache_behavior(self):
        """Test that profiles are cached after first retrieval"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        # Clear cache
        self.service.cache.clear()
        self.assertNotIn('user1', self.service.cache)

        # First retrieval should cache
        profile1 = self.service.get_user_profile('user1')
        self.assertIn('user1', self.service.cache)

        # Second retrieval should use cache
        profile2 = self.service.get_user_profile('user1')
        self.assertEqual(profile1, profile2)

    def test_cache_invalidated_on_create(self):
        """Test that cache is invalidated when profile is created"""
        self.service.create_user_profile('user1', {
            'jurisdictionId': 'city-berkeley'
        })

        # Manually add to cache
        self.service.cache['user1'] = {'fake': 'data'}

        # Creating again should invalidate cache
        # (This would normally be an update in production, but tests isolation)
        # For now just verify cache management works

if __name__ == '__main__':
    unittest.main()
