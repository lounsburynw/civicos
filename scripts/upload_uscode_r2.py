#!/usr/bin/env python3
"""Upload U.S. Code XML zips to R2 for fast Modal access."""

import os
import sys
from pathlib import Path

# Load env before imports
from dotenv import load_dotenv
load_dotenv()

from civic.storage.blob import R2Backend

def main():
    # Initialize R2 backend
    r2 = R2Backend.from_env()
    print(f"Connected to R2: {r2.bucket_name}")

    # Upload all zip files
    uscode_dir = Path("data/uscode")
    zips = sorted(uscode_dir.glob("xml_usc*.zip"))
    print(f"Found {len(zips)} zip files to upload")
    print()

    uploaded = 0
    skipped = 0
    total_bytes = 0

    for i, zip_path in enumerate(zips, 1):
        key = f"uscode/119-59/{zip_path.name}"

        # Check if already exists
        if r2.exists(key):
            print(f"[{i}/{len(zips)}] SKIP {zip_path.name} (exists)")
            skipped += 1
            continue

        # Upload
        data = zip_path.read_bytes()
        r2.upload(key, data, content_type="application/zip")
        print(f"[{i}/{len(zips)}] UP {zip_path.name} ({len(data)/1024:.0f}KB)")
        uploaded += 1
        total_bytes += len(data)

    print()
    print(f"=== Upload Complete ===")
    print(f"Uploaded: {uploaded} files ({total_bytes/1024/1024:.1f}MB)")
    print(f"Skipped: {skipped} files")
    print(f"R2 path: r2://{r2.account_id}/{r2.bucket_name}/uscode/119-59/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
