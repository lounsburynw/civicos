#!/usr/bin/env python3
"""
Load extracted events JSON into StateManager.

This script converts civic-app-schema events into StateManager format
and populates the civic_state.db database.

Usage:
    python scripts/load_events_to_state.py                    # Load all jurisdictions
    python scripts/load_events_to_state.py --jurisdiction san-rafael  # Load one jurisdiction
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/civic/src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from civic._internal.state import StateManager


def load_events_json(json_path: Path) -> dict:
    """Load events JSON file."""
    with open(json_path) as f:
        return json.load(f)


def convert_event_to_meeting(event: dict) -> dict:
    """
    Convert a civic-app-schema event to StateManager meeting format.

    Args:
        event: Event dict from civic-app-schema

    Returns:
        Meeting dict for StateManager
    """
    # Extract meeting datetime
    meeting_datetime = event.get("when")

    # Get agenda items from agenda_expansion
    agenda_expansion = event.get("agenda_expansion", {})
    agenda_items = []
    if agenda_expansion.get("actionable_items"):
        for item in agenda_expansion["actionable_items"]:
            agenda_items.append({
                "id": f"{event['id']}-{item.get('item_ref', 'unknown')}",
                "item_number": item.get("item_ref"),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "project_type": item.get("project_types", [event.get("project_type")])[0] if item.get("project_types") else event.get("project_type"),
                "legislative_context": item.get("legislative_context"),
            })

    return {
        "id": event.get("id"),
        "title": event.get("title", ""),
        "meeting_datetime": meeting_datetime,
        "meeting_type": event.get("meeting_type"),
        "status": "upcoming" if meeting_datetime else "unknown",
        "location": event.get("location"),
        "virtual_url": next(
            (m.get("url") for m in event.get("participation_mechanisms", [])
             if m.get("type") == "virtual"),
            None
        ),
        "agenda_url": event.get("agenda_url") or (agenda_expansion.get("source_url") if agenda_expansion else None),
        "source_platform": "civic-extraction",
        "source_url": event.get("source_url"),
        "data_quality_score": 1.0 if agenda_items else 0.5,
        "agenda_items": agenda_items,
        # Store full data for reference
        "full_event": event,
    }


def get_latest_events_file(jurisdiction_id: str, data_dir: Path) -> Optional[Path]:
    """Find the latest events file for a jurisdiction."""
    # Normalize jurisdiction_id (e.g., "san-rafael" -> "city-san-rafael")
    if not jurisdiction_id.startswith(("city-", "county-", "bart", "sonoma")):
        jurisdiction_id = f"city-{jurisdiction_id}"

    pattern = f"events_{jurisdiction_id}_*.json"
    files = sorted(data_dir.glob(pattern), reverse=True)

    if files:
        return files[0]
    return None


def load_jurisdiction(
    state_manager: StateManager,
    jurisdiction_id: str,
    data_dir: Path
) -> int:
    """
    Load events for a single jurisdiction into StateManager.

    Args:
        state_manager: StateManager instance
        jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")
        data_dir: Path to data/events directory

    Returns:
        Number of meetings loaded
    """
    # Find latest events file
    events_file = get_latest_events_file(jurisdiction_id, data_dir)
    if not events_file:
        print(f"No events file found for {jurisdiction_id}")
        return 0

    print(f"Loading {events_file.name}...")

    # Load and parse JSON
    data = load_events_json(events_file)
    events = data.get("events", [])

    if not events:
        print(f"  No events found in {events_file.name}")
        return 0

    # Convert events to meetings
    meetings = [convert_event_to_meeting(e) for e in events]

    # Get proper jurisdiction_id from the data
    actual_jurisdiction_id = data.get("jurisdiction", {}).get("id", jurisdiction_id)

    # Load into StateManager
    count = state_manager.update_meetings(
        actual_jurisdiction_id,
        meetings,
        as_of=datetime.now()
    )

    print(f"  Loaded {count} meetings for {actual_jurisdiction_id}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Load events into StateManager")
    parser.add_argument(
        "--jurisdiction", "-j",
        help="Specific jurisdiction to load (e.g., 'san-rafael')"
    )
    parser.add_argument(
        "--db-path",
        default="data/civic_state.db",
        help="Path to StateManager database"
    )
    parser.add_argument(
        "--data-dir",
        default="data/events",
        help="Path to events data directory"
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: Data directory {data_dir} does not exist")
        sys.exit(1)

    # Initialize StateManager
    state_manager = StateManager(args.db_path)

    if args.jurisdiction:
        # Load single jurisdiction
        count = load_jurisdiction(state_manager, args.jurisdiction, data_dir)
        print(f"\nTotal: {count} meetings loaded")
    else:
        # Find all unique jurisdictions from files
        jurisdictions = set()
        for f in data_dir.glob("events_*.json"):
            # Extract jurisdiction from filename: events_city-san-rafael_20251112_220935.json
            parts = f.stem.split("_")
            if len(parts) >= 2:
                jurisdiction_id = parts[1]
                jurisdictions.add(jurisdiction_id)

        total = 0
        for jurisdiction_id in sorted(jurisdictions):
            count = load_jurisdiction(state_manager, jurisdiction_id, data_dir)
            total += count

        print(f"\nTotal: {total} meetings loaded across {len(jurisdictions)} jurisdictions")

    # Show stats
    print("\n--- StateManager Stats ---")
    for j in state_manager.list_jurisdictions():
        stats = state_manager.get_stats(j["jurisdiction_id"])
        print(f"  {j['jurisdiction_id']}: {stats['current_meetings']} meetings")


if __name__ == "__main__":
    main()
