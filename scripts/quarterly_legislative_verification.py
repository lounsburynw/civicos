#!/usr/bin/env python3
"""
Quarterly Legislative Context Verification Script

Checks legislative context files for:
- Expired local implementation deadlines
- Broken/404 official URLs
- Missing or incomplete metadata
- Stale last_updated timestamps

Usage:
    python scripts/quarterly_legislative_verification.py
    python scripts/quarterly_legislative_verification.py --topic housing
    python scripts/quarterly_legislative_verification.py --fix-urls  # Auto-fix redirects
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import urllib.request
from urllib.error import HTTPError, URLError

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

class LegislativeVerifier:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.state_dir = self.project_root / "data" / "legislative_context"
        self.federal_dir = self.project_root / "data" / "federal_programs"
        self.issues = []
        self.warnings = []

    def verify_all(self, topic: Optional[str] = None, quiet: bool = False) -> Tuple[List[Dict], List[Dict]]:
        """Run all verification checks"""
        if not quiet:
            print("🔍 Legislative Context Verification")
            print("=" * 60)

        # Check state legislation
        if self.state_dir.exists():
            self._verify_directory(self.state_dir, "state", topic, quiet)

        # Check federal programs
        if self.federal_dir.exists():
            self._verify_directory(self.federal_dir, "federal", topic, quiet)

        return self.issues, self.warnings

    def _verify_directory(self, directory: Path, context_type: str, topic_filter: Optional[str] = None, quiet: bool = False):
        """Verify all JSON files in a directory"""
        for filepath in directory.glob("*.json"):
            # Skip audit files, cache files, and verification reports
            if any(skip in filepath.name for skip in ["audit", ".cache", "verification_report", "quarterly_verification"]):
                continue

            # Apply topic filter if specified
            if topic_filter:
                if context_type == "state":
                    # State files: california_housing.json -> housing
                    file_topic = filepath.stem.replace("california_", "")
                else:
                    # Federal files: housing.json -> housing
                    file_topic = filepath.stem

                if file_topic != topic_filter:
                    continue

            if not quiet:
                print(f"\n📄 Checking {filepath.name}...")
            self._verify_file(filepath, context_type)

    def _verify_file(self, filepath: Path, context_type: str):
        """Verify a single legislative context file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self.issues.append({
                "file": filepath.name,
                "type": "json_error",
                "message": f"Invalid JSON: {e}"
            })
            return

        # Check last_updated timestamp
        self._check_staleness(filepath.name, data)

        # Check verification status
        self._check_verification_status(filepath.name, data)

        # Check state legislation
        if context_type == "state" and "state_legislation" in data:
            for bill_id, bill_data in data["state_legislation"].items():
                self._verify_bill(filepath.name, bill_id, bill_data)

        # Check federal programs
        if context_type == "federal" and "programs" in data:
            for program_id, program_data in data["programs"].items():
                self._verify_program(filepath.name, program_id, program_data)

    def _check_staleness(self, filename: str, data: Dict):
        """Check if last_updated is more than 6 months old"""
        if "last_updated" not in data:
            self.issues.append({
                "file": filename,
                "type": "missing_metadata",
                "message": "Missing last_updated timestamp"
            })
            return

        try:
            last_updated = datetime.fromisoformat(data["last_updated"])
            age_days = (datetime.now() - last_updated).days

            if age_days > 180:  # 6 months
                self.warnings.append({
                    "file": filename,
                    "type": "stale_data",
                    "message": f"Last updated {age_days} days ago (>{180} days)",
                    "age_days": age_days
                })
        except ValueError as e:
            self.issues.append({
                "file": filename,
                "type": "invalid_timestamp",
                "message": f"Invalid last_updated format: {e}"
            })

    def _check_verification_status(self, filename: str, data: Dict):
        """Check if data has been verified"""
        status = data.get("verification_status", "")

        if "DRAFT" in status or "NOT VERIFIED" in status:
            self.warnings.append({
                "file": filename,
                "type": "unverified_data",
                "message": f"Verification status: {status}"
            })

    def _verify_bill(self, filename: str, bill_id: str, bill_data: Dict):
        """Verify a state bill entry"""
        # Check for expired deadlines
        if bill_data.get("local_deadline"):
            deadline_str = bill_data["local_deadline"]
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%d")
                if deadline < datetime.now():
                    days_expired = (datetime.now() - deadline).days

                    # Only flag if significantly expired (>1 year)
                    if days_expired > 365:
                        self.warnings.append({
                            "file": filename,
                            "bill_id": bill_id,
                            "type": "expired_deadline",
                            "message": f"{bill_id} deadline expired {days_expired} days ago ({deadline_str})"
                        })
            except ValueError:
                self.issues.append({
                    "file": filename,
                    "bill_id": bill_id,
                    "type": "invalid_deadline",
                    "message": f"Invalid deadline format: {deadline_str}"
                })

        # Check official URL
        if bill_data.get("official_url"):
            self._verify_url(filename, bill_id, bill_data["official_url"], "bill")

        # Check for missing metadata
        required_fields = ["bill", "status", "enacted", "summary", "keywords", "leverage_point"]
        for field in required_fields:
            if not bill_data.get(field):
                self.warnings.append({
                    "file": filename,
                    "bill_id": bill_id,
                    "type": "missing_field",
                    "message": f"Missing or empty field: {field}"
                })

    def _verify_program(self, filename: str, program_id: str, program_data: Dict):
        """Verify a federal program entry"""
        # Check official URL
        if program_data.get("official_url"):
            url = program_data["official_url"]
            # Skip placeholder values
            if url and url not in ["", "information not available"]:
                self._verify_url(filename, program_id, url, "program")

        # Check for incomplete data
        if program_data.get("description") in ["", "information not available"]:
            self.warnings.append({
                "file": filename,
                "program_id": program_id,
                "type": "incomplete_data",
                "message": "Missing program description"
            })

        # Check leverage point
        leverage = program_data.get("leverage_point", "")
        if leverage in ["", "information not available"]:
            self.warnings.append({
                "file": filename,
                "program_id": program_id,
                "type": "missing_leverage_point",
                "message": "Missing or incomplete leverage point"
            })

    def _verify_url(self, filename: str, item_id: str, url: str, item_type: str):
        """Verify that a URL is accessible"""
        try:
            # Set a reasonable timeout
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'CivicBot/1.0 (Legislative Verification)'}
            )
            response = urllib.request.urlopen(req, timeout=10)

            # Check for redirects
            if response.url != url:
                self.warnings.append({
                    "file": filename,
                    f"{item_type}_id": item_id,
                    "type": "url_redirect",
                    "message": f"URL redirects: {url} -> {response.url}"
                })

        except HTTPError as e:
            if e.code == 404:
                self.issues.append({
                    "file": filename,
                    f"{item_type}_id": item_id,
                    "type": "broken_url",
                    "message": f"404 Not Found: {url}"
                })
            else:
                self.warnings.append({
                    "file": filename,
                    f"{item_type}_id": item_id,
                    "type": "url_error",
                    "message": f"HTTP {e.code}: {url}"
                })

        except URLError as e:
            self.warnings.append({
                "file": filename,
                f"{item_type}_id": item_id,
                "type": "url_error",
                "message": f"URL error: {url} ({e.reason})"
            })

        except Exception as e:
            self.warnings.append({
                "file": filename,
                f"{item_type}_id": item_id,
                "type": "url_error",
                "message": f"Error checking {url}: {e}"
            })

def print_results(issues: List[Dict], warnings: List[Dict]):
    """Print verification results"""
    print("\n" + "=" * 60)

    if issues:
        print(f"\n❌ {len(issues)} ISSUES FOUND:")
        for issue in issues:
            file = issue.get("file", "unknown")
            bill_id = issue.get("bill_id") or issue.get("program_id", "")
            msg = issue.get("message", "")
            print(f"  • [{file}] {bill_id}: {msg}")

    if warnings:
        print(f"\n⚠️  {len(warnings)} WARNINGS:")
        for warning in warnings:
            file = warning.get("file", "unknown")
            bill_id = warning.get("bill_id") or warning.get("program_id", "")
            msg = warning.get("message", "")
            print(f"  • [{file}] {bill_id}: {msg}")

    if not issues and not warnings:
        print("\n✅ All checks passed!")

    print("\n" + "=" * 60)

    # Print summary
    total = len(issues) + len(warnings)
    if total > 0:
        print(f"\nTotal: {len(issues)} issues, {len(warnings)} warnings")
        print("\nNext steps:")
        print("1. Review broken URLs and update to current versions")
        print("2. Check for superseding legislation for expired bills")
        print("3. Update stale data (>6 months old)")
        print("4. Complete any missing metadata")
    else:
        print("\n✅ Legislative context is up to date!")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Verify legislative context files")
    parser.add_argument("--topic", help="Only check specific topic (e.g., housing, transportation)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    verifier = LegislativeVerifier()
    issues, warnings = verifier.verify_all(topic=args.topic, quiet=args.json)

    if args.json:
        print(json.dumps({
            "issues": issues,
            "warnings": warnings,
            "total_issues": len(issues),
            "total_warnings": len(warnings)
        }, indent=2))
    else:
        print_results(issues, warnings)

    # Exit with error code if critical issues found
    sys.exit(1 if issues else 0)

if __name__ == "__main__":
    main()
