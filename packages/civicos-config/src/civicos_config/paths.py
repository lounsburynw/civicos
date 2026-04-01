"""
Shared path constants for CivicOS packages.

On Modal/CI, paths come from environment variables (CIVICOS_JURISDICTIONS_DIR,
CIVICOS_CONFIG_DIR). Locally, finds the repo root by walking up looking for
phase.json.
"""

import os
from pathlib import Path


def _find_repo_root() -> Path:
    """Walk up from this file to find the repository root (contains phase.json)."""
    current = Path(__file__).resolve().parent
    for _ in range(10):  # safety limit
        if (current / "phase.json").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        "Could not find CivicOS repo root (no phase.json found in parent directories)"
    )


# Use env vars when available (Modal sets these via image.env())
_repo_root = None


def _get_repo_root() -> Path:
    global _repo_root
    if _repo_root is None:
        _repo_root = _find_repo_root()
    return _repo_root


_jurisdictions_env = os.environ.get("CIVICOS_JURISDICTIONS_DIR")
if _jurisdictions_env:
    JURISDICTIONS_DIR = Path(_jurisdictions_env)
else:
    JURISDICTIONS_DIR = _get_repo_root() / "data" / "jurisdictions"

_extraction_env = os.environ.get("CIVICOS_EXTRACTION_DIR")
if _extraction_env:
    EXTRACTION_DIR = Path(_extraction_env)
else:
    EXTRACTION_DIR = _get_repo_root() / "data" / "extraction"
