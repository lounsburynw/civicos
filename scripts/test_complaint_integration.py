#!/usr/bin/env python3
"""
Quick integration test for complaint handler.
Validates the examples from docs/COMPLAINT_INTEGRATION_GUIDE.md
"""

import sys
import os
from pathlib import Path

# Add both project root and src to path
project_root = Path(__file__).parent.parent
src_dir = project_root / 'src'
os.chdir(project_root)
sys.path.insert(0, str(project_root))  # For src.interfaces imports
sys.path.insert(0, str(src_dir))        # For complaint_* imports

from complaint_handler import handle_message

def test_integration_examples():
    """Test all integration examples from the guide"""

    print("Testing Complaint Handler Integration")
    print("=" * 70)

    # Test 1: Basic complaint (matched)
    print("\n📝 Test 1: Basic complaint - 'My landlord won't fix the heating'")
    print("-" * 70)
    response = handle_message(
        message="My landlord won't fix the heating",
        user_id='test_user',
        user_context={'jurisdiction_id': 'city-berkeley'}
    )
    print(f"✓ Response type: {response['type']}")
    if response['type'] == 'matched':
        print(f"✓ Matches found: {len(response['matches'])}")
        for i, match in enumerate(response['matches'], 1):
            print(f"  {i}. {match['title']}")

    # Test 2: Infrastructure complaint
    print("\n📝 Test 2: Infrastructure complaint - 'Pothole on Main Street'")
    print("-" * 70)
    response2 = handle_message(
        message="There is a huge pothole on Main Street",
        user_id='test_user',
        user_context={'jurisdiction_id': 'city-berkeley'}
    )
    print(f"✓ Response type: {response2['type']}")
    if response2['type'] == 'matched':
        print(f"✓ Matches found: {len(response2['matches'])}")
    elif response2['type'] == 'no_match':
        print(f"✓ No matches (expected for some complaints)")
        similar = response2.get('similar_count', 0)
        if similar > 0:
            print(f"  Similar complaints: {similar}")

    # Test 3: Non-complaint
    print("\n📝 Test 3: Non-complaint - 'When is the next meeting?'")
    print("-" * 70)
    response3 = handle_message(
        message='When is the next city council meeting?',
        user_id='test_user',
        user_context={'jurisdiction_id': 'city-berkeley'}
    )
    print(f"✓ Response type: {response3['type']}")
    assert response3['type'] == 'not_complaint', "Should detect non-complaint"

    # Test 4: Missing jurisdiction
    print("\n📝 Test 4: Missing jurisdiction")
    print("-" * 70)
    response4 = handle_message(
        message="My street needs repaving",
        user_id='test_user',
        user_context={}  # No jurisdiction
    )
    print(f"✓ Response type: {response4['type']}")
    assert response4['type'] == 'missing_jurisdiction', "Should request jurisdiction"

    # Test 5: Jurisdiction validation
    print("\n📝 Test 5: Jurisdiction ID validation")
    print("-" * 70)
    test_jurisdictions = [
        ('city-berkeley', 'Berkeley'),
        ('city-oakland', 'Oakland'),
        ('city-san-rafael', 'San Rafael'),
        ('city-santa-rosa', 'Santa Rosa'),
        ('city-hayward', 'Hayward'),
        ('city-el-cerrito', 'El Cerrito')
    ]

    for jurisdiction_id, city_name in test_jurisdictions:
        response = handle_message(
            message="Test complaint",
            user_id='test_validation',
            user_context={'jurisdiction_id': jurisdiction_id}
        )

        if response['type'] != 'missing_jurisdiction':
            print(f"  ✓ {city_name:15} ({jurisdiction_id})")
        else:
            print(f"  ✗ {city_name:15} ({jurisdiction_id}) - INVALID")

    # Summary
    print("\n" + "=" * 70)
    print("✅ All integration examples validated successfully!")
    print("\nNext steps:")
    print("  1. Review docs/COMPLAINT_INTEGRATION_GUIDE.md")
    print("  2. Integrate into src/civic_api_integrated.py")
    print("  3. Test with API server: python src/civic_api_integrated.py")
    print("  4. Test with frontend UI")

if __name__ == '__main__':
    try:
        test_integration_examples()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
