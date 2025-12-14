#!/usr/bin/env python3
"""
Populate test user profile with archetypes for comment drafting testing.

Session 41: PersonalizationService Integration
Creates test-user-1 with Green New Dealer, Regional Thinker, and Labor Organizer archetypes.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from personalization_service import PersonalizationService

def populate_test_user():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'civic_participation.db')
    ps = PersonalizationService(db_path)

    user_id = 'test-user-1'

    # Create user profile
    ps.create_user_profile(
        user_id=user_id,
        demographics={
            'residency_years': 1,
            'district': 'District 3',
            'occupation': 'Tech/Data Science'
        }
    )

    # Add archetype scores (Green New Dealer, Regional Thinker, Labor Organizer)
    ps.update_user_interests(user_id, {
        'archetypes': [
            {
                'id': 'green_new_dealer',
                'name': 'Green New Dealer',
                'score': 0.525,
                'description': 'Climate action through government jobs programs and public investment'
            },
            {
                'id': 'regional_thinker',
                'name': 'Regional Thinker',
                'score': 0.515,
                'description': 'Regional coordination, metropolitan perspective, systems thinking'
            },
            {
                'id': 'labor_organizer',
                'name': 'Labor Organizer',
                'score': 0.510,
                'description': 'Worker rights, living wages, unions, labor standards'
            }
        ]
    })

    print(f"✅ Created test user profile: {user_id}")
    print(f"   Top archetypes: Green New Dealer, Regional Thinker, Labor Organizer")

    # Verify
    profile = ps.get_user_profile(user_id)
    print(f"\n📊 Profile loaded successfully:")
    print(f"   User ID: {profile['user_id']}")
    print(f"   Demographics: {profile.get('demographics', {})}")

    if profile.get('top_archetypes'):
        print(f"   Top archetype: {profile['top_archetypes'][0]['name']} (score: {profile['top_archetypes'][0]['score']})")
        print(f"\n🎯 Archetype details:")
        for archetype in profile['top_archetypes'][:3]:
            print(f"   - {archetype['name']}: {archetype['description']}")
    else:
        print("   ⚠️  No archetypes found in profile")

if __name__ == '__main__':
    populate_test_user()
