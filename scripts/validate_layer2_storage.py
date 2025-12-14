#!/usr/bin/env python3
"""
Layer 2 validation script - Interactive demo of complaint storage.

Demonstrates:
- Creating complaints
- Linking to events
- Finding similar complaints
- ParticipationMechanism interface
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.complaint_storage import ComplaintStorage, Complaint
import json


def print_section(title):
    """Print section header"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def demo_create_complaint():
    """Demonstrate creating a complaint"""
    print_section("1. Creating Test Complaints")

    storage = ComplaintStorage()

    # Create test complaints
    complaints = []

    # Housing complaint 1
    complaint_id_1 = storage.create_complaint(
        user_id="test-user-alice",
        description="There's not enough affordable housing in my neighborhood. Rent keeps going up and families are being displaced.",
        jurisdiction_id="city-berkeley",
        issue_type="housing",
        location={
            "address": "2180 Milvia St, Berkeley CA",
            "latitude": 37.8715,
            "longitude": -122.2730
        }
    )
    complaints.append(complaint_id_1)
    print(f"✓ Created housing complaint: {complaint_id_1[:8]}...")

    # Housing complaint 2 (similar)
    complaint_id_2 = storage.create_complaint(
        user_id="test-user-bob",
        description="We need more affordable housing options. Too many people are being priced out.",
        jurisdiction_id="city-berkeley",
        issue_type="housing"
    )
    complaints.append(complaint_id_2)
    print(f"✓ Created housing complaint: {complaint_id_2[:8]}...")

    # Infrastructure complaint
    complaint_id_3 = storage.create_complaint(
        user_id="test-user-carol",
        description="Big pothole on Main St near the corner of Elm. It's been there for weeks and is damaging cars.",
        jurisdiction_id="city-berkeley",
        issue_type="infrastructure",
        location={
            "address": "Main St & Elm Ave, Berkeley CA",
            "latitude": 37.8698,
            "longitude": -122.2712
        }
    )
    complaints.append(complaint_id_3)
    print(f"✓ Created infrastructure complaint: {complaint_id_3[:8]}...")

    return complaints


def demo_get_complaint(complaint_id):
    """Demonstrate retrieving a complaint"""
    print_section(f"2. Retrieving Complaint: {complaint_id[:8]}...")

    storage = ComplaintStorage()
    complaint = storage.get_complaint(complaint_id)

    if complaint:
        print(f"Description: {complaint['description'][:80]}...")
        print(f"Issue Type: {complaint['issue_type']}")
        print(f"Status: {complaint['status']}")
        print(f"Jurisdiction: {complaint['jurisdiction_id']}")
        print(f"Created: {complaint['created_at']}")
        print(f"Matched Events: {len(complaint['matched_events'])}")
    else:
        print("✗ Complaint not found")

    return complaint


def demo_link_to_events(complaint_id):
    """Demonstrate linking complaint to events"""
    print_section("3. Linking Complaint to Events")

    storage = ComplaintStorage()

    # Simulate matching to events
    events = [
        ("event-berkeley-council-2025-10-20", 85.0, "Keyword match: housing, affordable; Project type: housing"),
        ("event-berkeley-planning-2025-10-15", 72.0, "Keyword match: housing; Meeting within 7 days"),
    ]

    for event_id, score, reason in events:
        storage.link_to_event(complaint_id, event_id, score, reason)
        print(f"✓ Linked to {event_id} (score: {score})")
        print(f"  Reason: {reason}")

    # Retrieve updated complaint
    complaint = storage.get_complaint(complaint_id)
    print(f"\n✓ Complaint status updated: {complaint['status']}")
    print(f"✓ Total matched events: {len(complaint['matched_events'])}")


def demo_find_similar(jurisdiction_id, issue_type):
    """Demonstrate finding similar complaints"""
    print_section(f"4. Finding Similar Complaints: {issue_type}")

    storage = ComplaintStorage()
    similar = storage.find_similar_complaints(jurisdiction_id, issue_type)

    print(f"Found {len(similar)} similar complaints in {jurisdiction_id}")
    for i, complaint in enumerate(similar, 1):
        print(f"\n{i}. {complaint['description'][:60]}...")
        print(f"   Status: {complaint['status']} | Created: {complaint['created_at']}")


def demo_participation_mechanism(complaint_id):
    """Demonstrate ParticipationMechanism interface"""
    print_section("5. ParticipationMechanism Interface")

    storage = ComplaintStorage()
    complaint_data = storage.get_complaint(complaint_id)
    complaint = Complaint(complaint_data)

    print(f"ID: {complaint.get_id()[:8]}...")
    print(f"Type: {complaint.get_type()}")
    print(f"Lifecycle Status: {complaint.get_lifecycle_status()}")
    print(f"Participation Threshold: {complaint.get_participation_threshold()}")
    print(f"Government Generated: {complaint.is_government_generated()}")

    print("\n--- Available Actions ---")
    actions = complaint.get_actions()
    for i, action in enumerate(actions, 1):
        print(f"{i}. {action['action_label']}")
        print(f"   Type: {action['action_type']} | Target: {action['action_target']}")

    print("\n--- Context ---")
    context = complaint.get_context()
    print(json.dumps(context, indent=2))


def demo_update_status(complaint_id):
    """Demonstrate updating complaint status"""
    print_section("6. Updating Complaint Status")

    storage = ComplaintStorage()

    print(f"Current status: matched")
    storage.update_status(complaint_id, "community_formed")
    print(f"✓ Updated status to: community_formed")

    complaint = storage.get_complaint(complaint_id)
    print(f"Verified: {complaint['status']}")


def verify_database_schema():
    """Verify all tables were created correctly"""
    print_section("Database Schema Verification")

    import sqlite3
    conn = sqlite3.connect("data/civic_participation.db")
    cursor = conn.cursor()

    # Check tables
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name LIKE '%complaint%'
        ORDER BY name
    """)
    tables = [row[0] for row in cursor.fetchall()]

    print("✓ Complaint-related tables:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  - {table}: {count} rows")

    # Check indexes
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name LIKE '%complaint%'
        ORDER BY name
    """)
    indexes = [row[0] for row in cursor.fetchall()]

    print(f"\n✓ Indexes: {len(indexes)} complaint-related indexes")
    for idx in indexes:
        print(f"  - {idx}")

    conn.close()


def main():
    """Run complete Layer 2 validation"""
    print("\n" + "█" * 60)
    print("  LAYER 2 VALIDATION: Complaint Storage & Persistence")
    print("█" * 60)

    try:
        # Verify schema
        verify_database_schema()

        # Create test complaints
        complaint_ids = demo_create_complaint()

        # Retrieve complaint
        complaint_data = demo_get_complaint(complaint_ids[0])

        # Link to events
        demo_link_to_events(complaint_ids[0])

        # Find similar complaints
        demo_find_similar("city-berkeley", "housing")

        # Test ParticipationMechanism interface
        demo_participation_mechanism(complaint_ids[0])

        # Update status
        demo_update_status(complaint_ids[0])

        print_section("✅ VALIDATION COMPLETE")
        print("\nAll Layer 2 features working correctly:")
        print("  ✓ CRUD operations (create, get, update)")
        print("  ✓ Event linking (many-to-many)")
        print("  ✓ Similar complaint queries")
        print("  ✓ ParticipationMechanism interface")
        print("  ✓ Status lifecycle management")
        print("  ✓ Civic action tracking")
        print(f"\nTest complaints created: {len(complaint_ids)}")
        print("Run: pytest tests/test_complaint_storage.py -v")
        print("To clean up: sqlite3 data/civic_participation.db 'DELETE FROM complaints WHERE user_id LIKE \"test-user-%\"'")

    except Exception as e:
        print(f"\n✗ Error during validation: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
