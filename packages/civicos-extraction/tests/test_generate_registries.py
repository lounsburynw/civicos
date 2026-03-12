"""
Tests for scripts/generate_registries.py

Verifies that registry generation correctly reads YAMLs and produces
expected output for each of the 3 target files.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))
from generate_registries import (
    _city_key,
    _generate_aliases,
    _generate_registry_entry,
    load_jurisdiction_yamls,
    patch_registry_json,
)


class TestCityKey:
    def test_city_prefix(self):
        assert _city_key("city-san-anselmo") == "san_anselmo"

    def test_county_prefix(self):
        assert _city_key("county-marin") == "marin"

    def test_hyphens_to_underscores(self):
        assert _city_key("city-mill-valley") == "mill_valley"


class TestGenerateAliases:
    def test_san_anselmo_aliases(self):
        yaml_data = {"jurisdiction_id": "city-san-anselmo", "display_name": "San Anselmo"}
        aliases = _generate_aliases(yaml_data)
        alias_text = "\n".join(aliases)
        assert '"san-anselmo": "city-san-anselmo"' in alias_text
        assert '"san-anselmo-ca": "city-san-anselmo"' in alias_text
        assert '"sananselmo": "city-san-anselmo"' in alias_text

    def test_single_word_city(self):
        yaml_data = {"jurisdiction_id": "city-dublin", "display_name": "Dublin"}
        aliases = _generate_aliases(yaml_data)
        alias_text = "\n".join(aliases)
        assert '"dublin": "city-dublin"' in alias_text
        assert '"dublin-ca": "city-dublin"' in alias_text


class TestGenerateRegistryEntry:
    def test_granicus_entry(self):
        yaml_data = {
            "jurisdiction_id": "city-san-anselmo",
            "display_name": "San Anselmo",
            "level": "town",
            "data_sources": {
                "meetings": {
                    "source_type": "granicus",
                    "base_url": "https://sananselmo-ca.granicus.com",
                    "metadata": {
                        "granicus_domain": "sananselmo-ca",
                        "default_view_id": "8",
                    },
                }
            },
            "contact_info": {
                "clerk_email": "townclerk@townofsananselmo.org",
                "website": "https://www.townofsananselmo.org",
            },
        }
        entry = _generate_registry_entry(yaml_data)
        assert '"san_anselmo": JurisdictionConfig(' in entry
        assert 'agent_type="granicus"' in entry
        assert 'view_id=8' in entry
        assert 'subdomain="sananselmo-ca"' in entry
        assert 'Town Hall' in entry  # level=town


class TestPatchRegistryJson:
    def test_adds_new_jurisdiction(self, tmp_path):
        registry_json = tmp_path / "registry.json"
        registry_json.write_text(json.dumps({
            "jurisdictions": {"city-existing": {"display_name": "Existing"}},
        }))

        yamls = [{
            "jurisdiction_id": "city-new-city",
            "display_name": "New City",
            "parent_jurisdictions": ["state-california"],
        }]

        import generate_registries
        orig = generate_registries.REGISTRY_JSON
        generate_registries.REGISTRY_JSON = registry_json
        try:
            changed = patch_registry_json(yamls)
            assert changed is True
            data = json.loads(registry_json.read_text())
            assert "city-new-city" in data["jurisdictions"]
            assert data["jurisdictions"]["city-new-city"]["display_name"] == "New City"
        finally:
            generate_registries.REGISTRY_JSON = orig

    def test_skips_existing_jurisdiction(self, tmp_path):
        registry_json = tmp_path / "registry.json"
        registry_json.write_text(json.dumps({
            "jurisdictions": {"city-existing": {"display_name": "Existing"}},
        }))

        yamls = [{"jurisdiction_id": "city-existing", "display_name": "Existing"}]

        import generate_registries
        orig = generate_registries.REGISTRY_JSON
        generate_registries.REGISTRY_JSON = registry_json
        try:
            changed = patch_registry_json(yamls)
            assert changed is False
        finally:
            generate_registries.REGISTRY_JSON = orig


class TestLoadJurisdictionYamls:
    def test_loads_specific_yaml(self):
        yamls = load_jurisdiction_yamls("city-san-anselmo")
        assert len(yamls) == 1
        assert yamls[0]["jurisdiction_id"] == "city-san-anselmo"

    def test_loads_all_yamls(self):
        yamls = load_jurisdiction_yamls()
        # Should have at least Mill Valley and San Anselmo
        ids = [y["jurisdiction_id"] for y in yamls]
        assert "city-mill-valley" in ids
        assert "city-san-anselmo" in ids
