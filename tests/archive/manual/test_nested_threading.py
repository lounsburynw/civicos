#!/usr/bin/env python3
"""
Test script for nested threading functionality.

Tests:
1. Create messages with parent_message_id
2. Verify reply_count updates
3. Retrieve nested message structure
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from complaint_storage import CommunityStorage
import json

def main():
    storage = CommunityStorage()

    print("=== Testing Nested Threading ===\n")

    # Test setup: Create a test thread
    print("1. Creating test follow and thread...")
    test_user = "test_user_123"
    test_focal_type = "event"
    test_focal_id = "test_event_456"

    follow_info = storage.create_follow(
        user_id=test_user,
        focal_type=test_focal_type,
        focal_id=test_focal_id,
        jurisdiction_id="test-city"
    )
    thread_id = follow_info['thread_id']
    print(f"   ✓ Created thread: {thread_id}")
    print(f"   ✓ Follower count: {follow_info['follower_count']}\n")

    # Test 1: Create top-level message
    print("2. Creating top-level message...")
    msg1 = storage.create_message(
        thread_id=thread_id,
        user_id=test_user,
        content="This is the first message"
    )
    print(f"   ✓ Message ID: {msg1['message_id']}")
    print(f"   ✓ Parent ID: {msg1['parent_message_id']}")
    print(f"   ✓ Reply count: {msg1['reply_count']}\n")

    # Test 2: Create first-level reply
    print("3. Creating first-level reply...")
    msg2 = storage.create_message(
        thread_id=thread_id,
        user_id="test_user_789",
        content="This is a reply to the first message",
        parent_message_id=msg1['message_id']
    )
    print(f"   ✓ Message ID: {msg2['message_id']}")
    print(f"   ✓ Parent ID: {msg2['parent_message_id']}")
    print(f"   ✓ Reply count: {msg2['reply_count']}\n")

    # Test 3: Create second-level reply
    print("4. Creating second-level reply...")
    msg3 = storage.create_message(
        thread_id=thread_id,
        user_id=test_user,
        content="This is a reply to the reply",
        parent_message_id=msg2['message_id']
    )
    print(f"   ✓ Message ID: {msg3['message_id']}")
    print(f"   ✓ Parent ID: {msg3['parent_message_id']}")
    print(f"   ✓ Reply count: {msg3['reply_count']}\n")

    # Test 4: Create another first-level reply
    print("5. Creating another first-level reply...")
    msg4 = storage.create_message(
        thread_id=thread_id,
        user_id="test_user_999",
        content="This is another reply to the first message",
        parent_message_id=msg1['message_id']
    )
    print(f"   ✓ Message ID: {msg4['message_id']}")
    print(f"   ✓ Parent ID: {msg4['parent_message_id']}\n")

    # Test 5: Retrieve nested structure
    print("6. Retrieving nested message structure...")
    nested_messages = storage.get_thread_messages_nested(thread_id)
    print(f"   ✓ Top-level messages: {len(nested_messages)}")
    print(f"\n   Nested structure:")
    print_nested(nested_messages, indent=3)

    # Test 6: Verify reply_count updated
    print("\n7. Verifying reply counts...")
    flat_messages = storage.get_thread_messages(thread_id)
    for msg in flat_messages:
        if msg['message_id'] == msg1['message_id']:
            print(f"   ✓ Message 1 reply_count: {msg['reply_count']} (expected: 2)")
            assert msg['reply_count'] == 2, "Message 1 should have 2 replies"
        elif msg['message_id'] == msg2['message_id']:
            print(f"   ✓ Message 2 reply_count: {msg['reply_count']} (expected: 1)")
            assert msg['reply_count'] == 1, "Message 2 should have 1 reply"

    print("\n=== All tests passed! ===\n")

def print_nested(messages, indent=0):
    """Pretty print nested message structure"""
    for msg in messages:
        prefix = " " * indent + "→ "
        user = msg['user_id'].split('_')[-1]  # Get last part of user ID
        content = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
        replies_text = f" [{msg['reply_count']} replies]" if msg['reply_count'] > 0 else ""
        print(f"{prefix}{user}: {content}{replies_text}")

        if msg.get('replies'):
            print_nested(msg['replies'], indent + 2)

if __name__ == '__main__':
    main()
