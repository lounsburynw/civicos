"""
Tests for scripts/validate_registry.py — registry and YAML validation.

Tests the validation logic against both valid and intentionally broken fixtures,
plus validates the real data in data/jurisdictions/ and config/registry.json.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent.parent
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_registry.py"
JURISDICTIONS_DIR = ROOT / "data" / "jurisdictions"
REGISTRY_JSON = ROOT / "config" / "registry.json"

# Import the validation module directly for unit tests
sys.path.insert(0, str(ROOT / "scripts"))
from validate_registry import (
    JURISDICTION_ID_RE,
    ValidationResult,
    validate_registry_json,
    validate_yaml_file,
)


# ---------------------------------------------------------------------------
# Unit tests: ValidationResult
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_empty_result_is_ok(self):
        r = ValidationResult()
        assert r.ok
        assert "passed" in r.summary()

    def test_error_makes_not_ok(self):
        r = ValidationResult()
        r.error("bad thing")
        assert not r.ok
        assert "bad thing" in r.summary()

    def test_warning_still_ok(self):
        r = ValidationResult()
        r.warn("minor issue")
        assert r.ok
        assert "minor issue" in r.summary()


# ---------------------------------------------------------------------------
# Unit tests: jurisdiction ID format
# ---------------------------------------------------------------------------

class TestJurisdictionIdFormat:
    @pytest.mark.parametrize("jid", [
        "city-san-rafael",
        "county-marin",
        "state-california",
        "country-united-states",
        "school-novato",
        "bart-sf",
    ])
    def test_valid_ids(self, jid):
        assert JURISDICTION_ID_RE.match(jid)

    @pytest.mark.parametrize("jid", [
        "San Rafael",           # spaces
        "city_san_rafael",      # underscores
        "city-San-Rafael",      # uppercase
        "san-rafael",           # no prefix
        "city-",                # no slug
        "city--san-rafael",     # double hyphen
        "",                     # empty
    ])
    def test_invalid_ids(self, jid):
        assert not JURISDICTION_ID_RE.match(jid)


# ---------------------------------------------------------------------------
# Unit tests: YAML file validation
# ---------------------------------------------------------------------------

class TestYamlValidation:
    def _write_yaml(self, tmp_path, filename, data):
        path = tmp_path / filename
        path.write_text(yaml.dump(data, default_flow_style=False))
        return path

    def test_valid_yaml(self, tmp_path):
        data = {
            "jurisdiction_id": "city-testville",
            "level": "city",
            "display_name": "Testville",
            "parent_jurisdictions": ["county-test", "state-california", "country-united-states"],
            "data_sources": {
                "meetings": {"source_type": "granicus", "base_url": "https://example.com"},
            },
        }
        path = self._write_yaml(tmp_path, "city-testville.yaml", data)
        result = ValidationResult()
        out = validate_yaml_file(path, result, set())
        assert result.ok, result.summary()
        assert out is not None

    def test_missing_jurisdiction_id(self, tmp_path):
        data = {"level": "city", "display_name": "Test"}
        path = self._write_yaml(tmp_path, "city-test.yaml", data)
        result = ValidationResult()
        validate_yaml_file(path, result, set())
        assert not result.ok
        assert any("jurisdiction_id" in e for e in result.errors)

    def test_missing_level(self, tmp_path):
        data = {
            "jurisdiction_id": "city-test",
            "display_name": "Test",
            "parent_jurisdictions": [],
        }
        path = self._write_yaml(tmp_path, "city-test.yaml", data)
        result = ValidationResult()
        validate_yaml_file(path, result, set())
        assert not result.ok
        assert any("level" in e for e in result.errors)

    def test_missing_display_name(self, tmp_path):
        data = {
            "jurisdiction_id": "city-test",
            "level": "city",
            "parent_jurisdictions": [],
        }
        path = self._write_yaml(tmp_path, "city-test.yaml", data)
        result = ValidationResult()
        validate_yaml_file(path, result, set())
        assert not result.ok
        assert any("display_name" in e for e in result.errors)

    def test_filename_mismatch(self, tmp_path):
        data = {
            "jurisdiction_id": "city-foo",
            "level": "city",
            "display_name": "Foo",
            "parent_jurisdictions": [],
        }
        path = self._write_yaml(tmp_path, "city-bar.yaml", data)
        result = ValidationResult()
        validate_yaml_file(path, result, set())
        assert not result.ok
        assert any("Filename" in e for e in result.errors)

    def test_invalid_level(self, tmp_path):
        data = {
            "jurisdiction_id": "city-test",
            "level": "village",
            "display_name": "Test",
            "parent_jurisdictions": [],
        }
        path = self._write_yaml(tmp_path, "city-test.yaml", data)
        result = ValidationResult()
        validate_yaml_file(path, result, set())
        assert not result.ok
        assert any("Invalid level" in e for e in result.errors)

    def test_level_prefix_mismatch(self, tmp_path):
        data = {
            "jurisdiction_id": "school-test",
            "level": "city",
            "display_name": "Test",
            "parent_jurisdictions": [],
        }
        path = self._write_yaml(tmp_path, "school-test.yaml", data)
        result = ValidationResult()
        validate_yaml_file(path, result, set())
        assert not result.ok
        assert any("should start with" in e for e in result.errors)

    def test_duplicate_id_detected(self, tmp_path):
        data = {
            "jurisdiction_id": "city-dup",
            "level": "city",
            "display_name": "Dup",
            "parent_jurisdictions": [],
        }
        path = self._write_yaml(tmp_path, "city-dup.yaml", data)
        result = ValidationResult()
        seen = {"city-dup"}
        validate_yaml_file(path, result, seen)
        assert not result.ok
        assert any("Duplicate" in e for e in result.errors)

    def test_unknown_source_type_warns(self, tmp_path):
        data = {
            "jurisdiction_id": "city-test",
            "level": "city",
            "display_name": "Test",
            "parent_jurisdictions": [],
            "data_sources": {"meetings": {"source_type": "unknown_platform", "base_url": "https://example.com"}},
        }
        path = self._write_yaml(tmp_path, "city-test.yaml", data)
        result = ValidationResult()
        validate_yaml_file(path, result, set())
        assert result.ok  # warnings don't fail
        assert any("unknown_platform" in w for w in result.warnings)

    def test_invalid_yaml_syntax(self, tmp_path):
        path = tmp_path / "city-bad.yaml"
        path.write_text(":\n  - [invalid\n")
        result = ValidationResult()
        validate_yaml_file(path, result, set())
        assert not result.ok
        assert any("Invalid YAML" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Unit tests: registry.json validation
# ---------------------------------------------------------------------------

class TestRegistryJsonValidation:
    def test_real_registry_loads(self):
        """registry.json in the repo should parse without errors."""
        with open(REGISTRY_JSON) as f:
            data = json.load(f)
        assert "jurisdictions" in data
        assert len(data["jurisdictions"]) > 0

    def test_no_duplicate_domains(self):
        """All domains in registry.json must be unique."""
        with open(REGISTRY_JSON) as f:
            data = json.load(f)
        domains = [
            entry.get("domain")
            for entry in data["jurisdictions"].values()
            if entry.get("domain")
        ]
        assert len(domains) == len(set(domains)), f"Duplicate domains: {[d for d in domains if domains.count(d) > 1]}"

    def test_all_entries_have_required_fields(self):
        """Every jurisdiction entry must have domain, display_name, modal_app_name, parent_jurisdictions."""
        with open(REGISTRY_JSON) as f:
            data = json.load(f)
        for jid, entry in data["jurisdictions"].items():
            for field in ["domain", "display_name", "modal_app_name", "parent_jurisdictions"]:
                assert field in entry, f"{jid} missing '{field}'"

    def test_valid_jurisdiction_id_format(self):
        """All jurisdiction IDs in registry.json must match the expected pattern."""
        with open(REGISTRY_JSON) as f:
            data = json.load(f)
        for jid in data["jurisdictions"]:
            assert JURISDICTION_ID_RE.match(jid), f"Invalid ID: {jid}"


# ---------------------------------------------------------------------------
# Integration test: run the script against real data
# ---------------------------------------------------------------------------

class TestValidateRegistryScript:
    def test_script_runs(self):
        """The validation script should execute without crashing."""
        result = subprocess.run(
            [sys.executable, str(VALIDATE_SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        # Script may exit 1 due to known mismatches, but shouldn't crash
        assert result.returncode in (0, 1)
        assert "Validated" in result.stdout

    def test_script_json_output(self):
        """--json flag should produce valid JSON."""
        result = subprocess.run(
            [sys.executable, str(VALIDATE_SCRIPT), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        # JSON block starts at first '{' in output
        json_start = result.stdout.index("{")
        output = json.loads(result.stdout[json_start:])
        assert "ok" in output
        assert "errors" in output
        assert "warnings" in output

    def test_script_yaml_only(self):
        """--yaml-only should skip registry.json validation."""
        result = subprocess.run(
            [sys.executable, str(VALIDATE_SCRIPT), "--yaml-only"],
            capture_output=True, text=True, timeout=30,
        )
        assert "registry.json" not in result.stdout or "Validated registry.json" not in result.stdout


# ---------------------------------------------------------------------------
# Real data: YAML file integrity
# ---------------------------------------------------------------------------

class TestRealYamlFiles:
    """Validate all YAML files in data/jurisdictions/ against schema rules."""

    @pytest.fixture
    def yaml_files(self):
        return sorted(
            p for p in JURISDICTIONS_DIR.glob("*.yaml")
            if p.name != "schema.yaml"
        )

    def test_all_yamls_have_jurisdiction_id(self, yaml_files):
        for path in yaml_files:
            with open(path) as f:
                data = yaml.safe_load(f)
            assert data and "jurisdiction_id" in data, f"{path.name} missing jurisdiction_id"

    def test_filenames_match_ids(self, yaml_files):
        for path in yaml_files:
            with open(path) as f:
                data = yaml.safe_load(f)
            if data and "jurisdiction_id" in data:
                assert path.name == f"{data['jurisdiction_id']}.yaml", (
                    f"Filename {path.name} != {data['jurisdiction_id']}.yaml"
                )

    def test_all_yamls_have_parent_jurisdictions(self, yaml_files):
        for path in yaml_files:
            with open(path) as f:
                data = yaml.safe_load(f)
            assert "parent_jurisdictions" in data, f"{path.name} missing parent_jurisdictions"

    def test_no_duplicate_jurisdiction_ids(self, yaml_files):
        ids = []
        for path in yaml_files:
            with open(path) as f:
                data = yaml.safe_load(f)
            if data and "jurisdiction_id" in data:
                ids.append(data["jurisdiction_id"])
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[i for i in ids if ids.count(i) > 1]}"
