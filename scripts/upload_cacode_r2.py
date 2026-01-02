#!/usr/bin/env python3
"""Upload California Codes data to R2 for fast Modal access.

Download the data first:
    curl -L https://downloads.leginfo.legislature.ca.gov/pubinfo_2025.zip -o pubinfo_2025.zip

Then run this script (with civic-env activated):
    python scripts/upload_cacode_r2.py
"""

import os
import sys
from pathlib import Path

# Load env before imports
from dotenv import load_dotenv
load_dotenv()

from civic.storage.blob import R2Backend


def main():
    # Check for local file
    zip_path = Path("pubinfo_2025.zip")
    if not zip_path.exists():
        print("ERROR: pubinfo_2025.zip not found in current directory")
        print()
        print("Download it first:")
        print("  curl -L https://downloads.leginfo.legislature.ca.gov/pubinfo_2025.zip -o pubinfo_2025.zip")
        return 1

    # Initialize R2 backend
    r2 = R2Backend.from_env()
    print(f"Connected to R2: {r2.bucket_name}")

    # Upload
    key = "cacode/2025/pubinfo_2025.zip"

    # Check if already exists
    if r2.exists(key):
        print(f"File already exists at {key}")
        size = len(r2.download(key))
        print(f"Existing size: {size / 1024 / 1024:.1f}MB")
        response = input("Overwrite? [y/N] ")
        if response.lower() != "y":
            print("Skipped.")
            return 0

    # Upload
    print(f"Uploading {zip_path.name}...")
    data = zip_path.read_bytes()
    print(f"Size: {len(data) / 1024 / 1024:.1f}MB")

    r2.upload(key, data, content_type="application/zip")
    print(f"Uploaded to: r2://{r2.account_id}/{r2.bucket_name}/{key}")
    print()
    print("Now run ingestion with:")
    print("  modal run scripts/modal_cacode.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
