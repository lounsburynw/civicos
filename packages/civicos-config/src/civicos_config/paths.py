"""
Shared path constants for CivicOS packages.

Finds the repository root by walking up from this file looking for
phase.json (always present at repo root). This avoids fragile
Path(__file__).parents[N] patterns that break when files move.
"""

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


REPO_ROOT = _find_repo_root()
JURISDICTIONS_DIR = REPO_ROOT / "data" / "jurisdictions"
