"""
Jurisdiction roster management for speaker detection enhancement.

Rosters contain known officials (council, staff) with their correct names,
titles, and aliases. This enables accurate speaker identification even when
the LLM detection fails or guesses incorrectly.

Roster files live in config/rosters/{jurisdiction_id}.json
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class Official:
    """A known official from the roster."""
    name: str
    role: str  # council, staff, board
    title: Optional[str] = None
    aliases: List[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []

    def matches(self, detected_name: str) -> bool:
        """Check if a detected name matches this official."""
        if not detected_name:
            return False
        detected_lower = detected_name.lower().strip()
        # Check exact name match
        if detected_lower == self.name.lower():
            return True
        # Check aliases
        for alias in self.aliases:
            if detected_lower == alias.lower():
                return True
        return False


class Roster:
    """
    Jurisdiction roster for speaker detection enhancement.

    Usage:
        roster = Roster.load('city-san-rafael')
        enhanced = roster.enhance_speakers(detected_speakers)
    """

    def __init__(
        self,
        jurisdiction_id: str,
        officials: List[Official],
        overrides: Dict[str, Optional[str]] = None,
    ):
        self.jurisdiction_id = jurisdiction_id
        self.officials = officials
        self.overrides = overrides or {}

        # Build alias lookup for fast matching
        self._alias_map: Dict[str, Official] = {}
        for official in officials:
            # Map name and all aliases to the official
            self._alias_map[official.name.lower()] = official
            for alias in official.aliases:
                self._alias_map[alias.lower()] = official

    @classmethod
    def load(cls, jurisdiction_id: str, config_dir: Optional[Path] = None) -> Optional["Roster"]:
        """
        Load roster from config file.

        Args:
            jurisdiction_id: e.g., 'city-san-rafael'
            config_dir: Override config directory (default: project config/rosters/)

        Returns:
            Roster if file exists, None otherwise
        """
        if config_dir is None:
            # Find project root by looking for config/ directory
            # Start from this file's location and walk up
            current = Path(__file__).parent
            for _ in range(5):  # Max 5 levels up
                config_path = current / "config" / "rosters" / f"{jurisdiction_id}.json"
                if config_path.exists():
                    break
                # Also check if we're in a package structure
                project_root = current.parent.parent.parent.parent  # packages/civicos/src/civicos -> project
                config_path = project_root / "config" / "rosters" / f"{jurisdiction_id}.json"
                if config_path.exists():
                    break
                current = current.parent
            else:
                return None
        else:
            config_path = config_dir / f"{jurisdiction_id}.json"

        if not config_path.exists():
            return None

        try:
            with open(config_path, 'r') as f:
                data = json.load(f)

            officials = []
            for entry in data.get("officials", []):
                officials.append(Official(
                    name=entry["name"],
                    role=entry["role"],
                    title=entry.get("title"),
                    aliases=entry.get("aliases", []),
                ))

            overrides = data.get("overrides", {})
            # Remove comment keys
            overrides = {k: v for k, v in overrides.items() if not k.startswith("_")}

            return cls(
                jurisdiction_id=jurisdiction_id,
                officials=officials,
                overrides=overrides,
            )
        except Exception as e:
            print(f"Warning: Failed to load roster for {jurisdiction_id}: {e}")
            return None

    def find_official(self, detected_name: str) -> Optional[Official]:
        """
        Find an official matching the detected name.

        Args:
            detected_name: Name from speaker detection (may be partial/alias)

        Returns:
            Official if found, None otherwise
        """
        if not detected_name:
            return None

        # Check overrides first (corrections for known errors)
        if detected_name in self.overrides:
            corrected = self.overrides[detected_name]
            if corrected is None:
                return None  # Explicitly removed
            detected_name = corrected

        # Look up in alias map
        return self._alias_map.get(detected_name.lower())

    def enhance_speakers(
        self,
        speakers_metadata: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Enhance speaker metadata with roster information.

        For each speaker, if their detected name matches a known official,
        replace with the official's full name and title.

        Args:
            speakers_metadata: Dict from speaker detection
                {"A": {"name": "Kate", "role": "council", "title": "Mayor"}, ...}

        Returns:
            Enhanced speakers_metadata with corrected names/titles
        """
        enhanced = {}

        for speaker_id, info in speakers_metadata.items():
            detected_name = info.get("name")
            new_info = info.copy()

            # Try to match to roster
            official = self.find_official(detected_name)
            if official:
                new_info["name"] = official.name
                new_info["role"] = official.role
                if official.title:
                    new_info["title"] = official.title
                new_info["roster_matched"] = True
            else:
                # Check if this is an override to remove
                if detected_name in self.overrides and self.overrides[detected_name] is None:
                    # Keep the auto-generated name (Public Speaker N, etc.)
                    # but mark as override-removed
                    new_info["roster_override"] = "removed"

            enhanced[speaker_id] = new_info

        return enhanced


def enhance_with_roster(
    jurisdiction_id: str,
    speakers_metadata: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Convenience function to enhance speakers with roster data.

    Args:
        jurisdiction_id: e.g., 'city-san-rafael'
        speakers_metadata: Raw speaker detection output

    Returns:
        Enhanced speakers_metadata (unchanged if no roster found)
    """
    roster = Roster.load(jurisdiction_id)
    if roster:
        return roster.enhance_speakers(speakers_metadata)
    return speakers_metadata
