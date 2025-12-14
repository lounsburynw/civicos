#!/usr/bin/env python3
"""
Test if complaint handler works in the exact same environment as the API server
"""

import sys
sys.path.insert(0, 'src')

# Initialize exactly as the API does
try:
    try:
        from .complaint_handler import handle_message as handle_complaint
    except ImportError:
        from complaint_handler import handle_message as handle_complaint
    COMPLAINT_HANDLER_AVAILABLE = True
    print("✅ COMPLAINT_HANDLER_AVAILABLE = True")
except ImportError as e:
    COMPLAINT_HANDLER_AVAILABLE = False
    print(f"❌ COMPLAINT_HANDLER_AVAILABLE = False: {e}")
    sys.exit(1)

# Test the exact API flow
message = 'My landlord will not fix the heating'
user_id = 'test_user'
city = 'Berkeley'

jurisdiction_map = {
    'Berkeley': 'city-berkeley',
    'Oakland': 'city-oakland',
    'San Rafael': 'city-san-rafael',
    'Santa Rosa': 'city-santa-rosa',
    'Hayward': 'city-hayward',
    'El Cerrito': 'city-el-cerrito'
}
jurisdiction_id = jurisdiction_map.get(city)

user_context = {
    'jurisdiction_id': jurisdiction_id,
    'name': None,
    'email': None
}

print(f"\n🧪 Testing complaint handler (API simulation)")
print(f"   Message: {message}")
print(f"   City: {city}")
print(f"   Jurisdiction: {jurisdiction_id}")
print()

try:
    complaint_response = handle_complaint(
        message=message,
        user_id=user_id or 'anonymous',
        user_context=user_context
    )

    print(f"✅ Handler returned successfully")
    print(f"   Type: {complaint_response['type']}")
    print(f"   In trigger list: {complaint_response['type'] in ['matched', 'no_match', 'missing_jurisdiction']}")

    if complaint_response['type'] in ['matched', 'no_match', 'missing_jurisdiction']:
        print(f"\n✅ WOULD TRIGGER COMPLAINT RESPONSE")
        if complaint_response['type'] == 'matched':
            print(f"   Matches: {len(complaint_response.get('matches', []))}")
            for match in complaint_response.get('matches', []):
                print(f"   - {match['title']}")
    else:
        print(f"\n❌ WOULD FALL THROUGH TO NORMAL CONVERSATION")
        print(f"   Reason: type='{complaint_response['type']}' not in trigger list")

except Exception as e:
    print(f"❌ Exception occurred: {e}")
    import traceback
    traceback.print_exc()
