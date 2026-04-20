#!/usr/bin/env python3
"""
Pre-flight validator for data/extraction/*.json.

Probes declared Granicus archive view_ids for liveness against the source site.
Catches reverts like the county-alameda incident where a working-tree edit
stripped archives back to a stale `board: 1` config.

Usage:
    python scripts/validate_extraction_configs.py                  # all configs
    python scripts/validate_extraction_configs.py city-berkeley    # one
    python scripts/validate_extraction_configs.py --json           # JSON output

Exit codes:
    0 — all declared archives reachable
    1 — one or more dead view_ids / config errors
    2 — could not reach any Granicus site (probably offline — don't fail CI)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

import requests

EXTRACTION_DIR = Path(__file__).resolve().parent.parent / "data" / "extraction"
USER_AGENT = "CivicOS-ConfigValidator/1.0 (+https://civicos.org)"
REQUEST_TIMEOUT_SEC = 20


@dataclass
class ArchiveResult:
    archive_key: str
    view_id: str
    url: str
    ok: bool
    status: Optional[int] = None
    error: Optional[str] = None


@dataclass
class ConfigResult:
    jurisdiction_id: str
    source_type: str
    archives_checked: List[ArchiveResult] = field(default_factory=list)
    skipped_reason: Optional[str] = None

    @property
    def failed_archives(self) -> List[ArchiveResult]:
        return [a for a in self.archives_checked if not a.ok]

    @property
    def reachable(self) -> bool:
        return any(a.ok for a in self.archives_checked)


def _probe_granicus_view(domain: str, view_id: str) -> ArchiveResult:
    url = f"https://{domain}.granicus.com/ViewPublisher.php?view_id={view_id}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SEC)
        if resp.status_code != 200:
            return ArchiveResult("", view_id, url, False, resp.status_code, f"HTTP {resp.status_code}")
        body = resp.text[:16384].lower()
        if "archive" in body or "viewpublisher" in body or "upcoming" in body:
            return ArchiveResult("", view_id, url, True, resp.status_code)
        return ArchiveResult(
            "", view_id, url, False, resp.status_code,
            "HTTP 200 but page doesn't contain ViewPublisher markers",
        )
    except requests.RequestException as e:
        return ArchiveResult("", view_id, url, False, None, f"{type(e).__name__}: {e}")


def validate_config(config_path: Path) -> ConfigResult:
    with open(config_path) as f:
        cfg = json.load(f)

    jurisdiction_id = cfg.get("jurisdiction_id") or config_path.stem
    source_type = cfg.get("source_type", "unknown")

    result = ConfigResult(jurisdiction_id=jurisdiction_id, source_type=source_type)

    if source_type != "granicus":
        result.skipped_reason = f"source_type={source_type} (validator only covers Granicus)"
        return result

    domain = (cfg.get("metadata") or {}).get("granicus_domain")
    if not domain:
        result.skipped_reason = "missing metadata.granicus_domain"
        return result

    archives = cfg.get("archives") or {}
    if not archives:
        result.skipped_reason = "no archives declared"
        return result

    for archive_key, view_id in archives.items():
        probe = _probe_granicus_view(domain, str(view_id))
        probe.archive_key = archive_key
        result.archives_checked.append(probe)
        time.sleep(0.5)

    return result


def _format_human(results: List[ConfigResult]) -> str:
    lines = []
    total_fail = 0
    total_skip = 0
    for r in results:
        if r.skipped_reason:
            lines.append(f"  [skip] {r.jurisdiction_id}: {r.skipped_reason}")
            total_skip += 1
            continue
        if r.failed_archives:
            total_fail += 1
            lines.append(f"  [FAIL] {r.jurisdiction_id} ({r.source_type}):")
            for a in r.failed_archives:
                lines.append(f"    - {a.archive_key} (view_id={a.view_id}): {a.error}")
        else:
            lines.append(
                f"  [ ok ] {r.jurisdiction_id}: "
                f"{len(r.archives_checked)} archive(s) reachable"
            )
    header = (
        f"Extraction config validation: "
        f"{len(results)} configs, {total_fail} failed, {total_skip} skipped"
    )
    return header + "\n" + "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "jurisdictions",
        nargs="*",
        help="Jurisdiction IDs to validate (default: all Granicus configs)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human output")
    args = parser.parse_args()

    if args.jurisdictions:
        config_paths = []
        for jid in args.jurisdictions:
            path = EXTRACTION_DIR / f"{jid}.json"
            if not path.exists():
                print(f"Error: {path} not found", file=sys.stderr)
                return 1
            config_paths.append(path)
    else:
        config_paths = sorted(EXTRACTION_DIR.glob("*.json"))

    results = [validate_config(p) for p in config_paths]

    if args.json:
        print(json.dumps({"results": [asdict(r) for r in results]}, indent=2, default=str))
    else:
        print(_format_human(results))

    granicus_results = [r for r in results if r.source_type == "granicus" and not r.skipped_reason]
    if granicus_results and not any(r.reachable for r in granicus_results):
        print(
            "\nAll Granicus probes failed — network or upstream outage. "
            "Not treating as a config regression.",
            file=sys.stderr,
        )
        return 2

    failed = any(r.failed_archives for r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
