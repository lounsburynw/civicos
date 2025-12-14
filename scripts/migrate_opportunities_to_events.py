#!/usr/bin/env python3
"""Migrate opportunities → events in JSON files"""

import json
import os
import shutil
from pathlib import Path

def migrate_file(filepath):
    """Migrate single JSON file"""
    # Backup original
    backup_path = f"{filepath}.backup"
    shutil.copy(filepath, backup_path)

    # Read and migrate
    with open(filepath, 'r') as f:
        data = json.load(f)

    # Rename field
    if 'opportunities' in data:
        data['events'] = data.pop('opportunities')
        migrated = True
    else:
        migrated = False

    # Write back
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    return migrated

def main():
    # Migrate all JSON files in data/events/
    json_files = list(Path('data/events').rglob('*.json'))

    print(f"Found {len(json_files)} JSON files to migrate")

    migrated_count = 0
    for filepath in json_files:
        if migrate_file(str(filepath)):
            migrated_count += 1
            print(f"✅ Migrated: {filepath}")
        else:
            print(f"⏭️  Skipped (no 'opportunities' field): {filepath}")

    print(f"\n✅ Migration complete: {migrated_count}/{len(json_files)} files migrated")
    print(f"📁 Backups saved with .backup extension")

if __name__ == '__main__':
    main()
