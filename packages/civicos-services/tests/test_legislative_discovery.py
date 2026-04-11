"""
Tests for legislative_discovery.py — automated discovery of locally-relevant
state legislation via LegiScan + LLM filtering.

The subject under test has four observable behaviors:
  1. Pure logic (_normalize_bill_id): tested with real inputs and pinned outputs.
  2. discover_topic orchestration: LegiScan client method is patched; the
     topic-validation, keyword-slicing and empty-result paths are exercised
     against the real method.
  3. _filter_relevant_bills: the OpenAI boundary is patched; JSON-parsing,
     shape normalization and exception handling are tested against the real
     method.
  4. update_legislative_context file I/O: uses tmp_path for real file writes
     and asserts the exact structure written/skipped.

To run:
    pytest packages/civicos-services/tests/test_legislative_discovery.py -q --override-ini="addopts="
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.legislative import legislative_discovery as ld_module
from civicos_services.legislative.legislative_discovery import LegislativeDiscovery


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def discovery():
    """A LegislativeDiscovery instance with a MagicMock'd LegiScan client.

    The real LegiScanClient is constructed in __init__, then replaced so the
    subject under test (LegislativeDiscovery methods) runs unmodified while
    network-bound LegiScan calls are intercepted.
    """
    d = LegislativeDiscovery()
    d.legiscan = MagicMock()
    return d


@pytest.fixture
def housing_bills():
    """Three sample bills in LegiScan's wire format."""
    return [
        {
            "bill_id": 1001,
            "bill_number": "SB 9",
            "title": "Lot Split Act",
            "description": "Allows lot splits in single-family zones. " * 10,
            "last_action": "Passed committee",
            "status": "Enacted",
            "status_date": "2025-09-01",
            "url": "https://example.com/sb9",
        },
        {
            "bill_id": 1002,
            "bill_number": "AB 1633",
            "title": "Housing Accountability",
            "description": "Strengthens the Housing Accountability Act.",
            "last_action": "Signed by Governor",
            "status": "Enacted",
            "status_date": "2025-08-15",
            "url": "https://example.com/ab1633",
        },
        {
            "bill_id": 1003,
            "bill_number": "AB 2097",
            "title": "Parking Minimums",
            "description": "Prohibits parking minimums near transit.",
            "last_action": "In committee",
            "status": "Active",
            "status_date": None,
            "url": "https://example.com/ab2097",
        },
    ]


# ---------------------------------------------------------------------------
# _normalize_bill_id — pure logic
# ---------------------------------------------------------------------------

class TestNormalizeBillId:
    def test_space_is_replaced_with_hyphen(self):
        d = LegislativeDiscovery()
        assert d._normalize_bill_id("SB 9") == "ca-sb-9"

    def test_lowercases_letters(self):
        d = LegislativeDiscovery()
        assert d._normalize_bill_id("AB 1633") == "ca-ab-1633"

    def test_dot_is_replaced_with_hyphen(self):
        d = LegislativeDiscovery()
        assert d._normalize_bill_id("H.R. 100") == "ca-h-r--100"

    def test_multi_word_bill_number(self):
        d = LegislativeDiscovery()
        assert d._normalize_bill_id("SJR 5") == "ca-sjr-5"

    def test_already_lowercase_no_space(self):
        d = LegislativeDiscovery()
        assert d._normalize_bill_id("sb9") == "ca-sb9"

    def test_empty_string_yields_ca_prefix_only(self):
        d = LegislativeDiscovery()
        assert d._normalize_bill_id("") == "ca-"


# ---------------------------------------------------------------------------
# discover_topic — orchestration + topic validation
# ---------------------------------------------------------------------------

class TestDiscoverTopic:
    def test_unknown_topic_raises_value_error(self, discovery):
        with pytest.raises(ValueError, match="Unknown topic: nonsense"):
            discovery.discover_topic("nonsense")

    def test_error_message_lists_valid_topics(self, discovery):
        with pytest.raises(ValueError) as exc_info:
            discovery.discover_topic("crypto")
        msg = str(exc_info.value)
        assert "housing" in msg
        assert "education" in msg

    def test_empty_legiscan_response_returns_empty_list(self, discovery):
        discovery.legiscan.get_recent_bills.return_value = []
        result = discovery.discover_topic("housing")
        assert result == []

    def test_legiscan_none_response_returns_empty_list(self, discovery):
        discovery.legiscan.get_recent_bills.return_value = None
        result = discovery.discover_topic("housing")
        assert result == []

    def test_legiscan_called_with_top_three_keywords(self, discovery, housing_bills):
        discovery.legiscan.get_recent_bills.return_value = housing_bills
        # Flip OPENAI_AVAILABLE off so the real _filter_relevant_bills takes
        # its early-return branch. Avoids mocking internals of the subject.
        with patch.object(ld_module, "OPENAI_AVAILABLE", False):
            discovery.discover_topic("housing", state="california", days_back=30)

        kwargs = discovery.legiscan.get_recent_bills.call_args.kwargs
        assert kwargs["state"] == "california"
        assert kwargs["days_back"] == 30
        # Housing TOPIC_KEYWORDS = ["housing", "affordable housing", "zoning", ...]
        # The source slices [:3], so we should see exactly the first three.
        assert kwargs["topic_keywords"] == ["housing", "affordable housing", "zoning"]

    def test_discover_topic_respects_limit_when_slicing_for_filter(self, discovery, housing_bills):
        discovery.legiscan.get_recent_bills.return_value = housing_bills  # 3 bills
        # With OpenAI unavailable, _filter_relevant_bills returns bills unchanged,
        # so the final result reflects the [:limit] slice applied before filtering.
        with patch.object(ld_module, "OPENAI_AVAILABLE", False):
            result = discovery.discover_topic("housing", limit=2)

        assert len(result) == 2
        assert result[0]["bill_id"] == 1001
        assert result[1]["bill_id"] == 1002

    def test_discover_topic_returns_filter_output(self, discovery, housing_bills):
        discovery.legiscan.get_recent_bills.return_value = housing_bills
        # Use the real _filter_relevant_bills with a stubbed OpenAI response.
        relevant = [{"bill_id": 1001, "bill_number": "SB 9", "leverage_point": "lot splits"}]
        fake = _fake_openai_response(json.dumps(relevant))
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake):
            result = discovery.discover_topic("housing")
        assert result == relevant

    def test_discover_topic_passes_transportation_keywords(self, discovery, housing_bills):
        discovery.legiscan.get_recent_bills.return_value = housing_bills
        with patch.object(ld_module, "OPENAI_AVAILABLE", False):
            discovery.discover_topic("transportation")
        # transportation TOPIC_KEYWORDS[:3] = ["transportation", "transit", "bicycle"]
        assert discovery.legiscan.get_recent_bills.call_args.kwargs["topic_keywords"] == [
            "transportation", "transit", "bicycle"
        ]


# ---------------------------------------------------------------------------
# _filter_relevant_bills — LLM boundary behavior
# ---------------------------------------------------------------------------

def _fake_openai_response(content: str):
    """Build a stand-in for openai.chat.completions.create() return value."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class TestFilterRelevantBills:
    def test_returns_unfiltered_bills_when_openai_unavailable(self, discovery, housing_bills):
        with patch.object(ld_module, "OPENAI_AVAILABLE", False):
            result = discovery._filter_relevant_bills(housing_bills, "housing")
        assert result == housing_bills

    def test_parses_raw_json_array_response(self, discovery, housing_bills):
        relevant = [
            {"bill_id": 1001, "bill_number": "SB 9",
             "leverage_point": "City adopts lot split ordinance."}
        ]
        fake_response = _fake_openai_response(json.dumps(relevant))
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake_response) as mock_create:
            result = discovery._filter_relevant_bills(housing_bills, "housing")

        assert result == relevant
        # Verify the LLM was invoked with gpt-4o-mini and JSON response format.
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["response_format"] == {"type": "json_object"}
        assert call_kwargs["temperature"] == 0.1

    def test_parses_object_with_bills_key(self, discovery, housing_bills):
        relevant = [{"bill_id": 1002, "bill_number": "AB 1633", "leverage_point": "HAA"}]
        fake_response = _fake_openai_response(json.dumps({"bills": relevant}))
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake_response):
            result = discovery._filter_relevant_bills(housing_bills, "housing")
        assert result == relevant

    def test_parses_object_with_relevant_bills_key(self, discovery, housing_bills):
        relevant = [{"bill_id": 1003, "bill_number": "AB 2097"}]
        fake_response = _fake_openai_response(
            json.dumps({"relevant_bills": relevant})
        )
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake_response):
            result = discovery._filter_relevant_bills(housing_bills, "housing")
        assert result == relevant

    def test_empty_dict_response_returns_empty_list(self, discovery, housing_bills):
        fake_response = _fake_openai_response(json.dumps({}))
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake_response):
            result = discovery._filter_relevant_bills(housing_bills, "housing")
        assert result == []

    def test_openai_exception_returns_empty_list(self, discovery, housing_bills):
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          side_effect=RuntimeError("rate limited")):
            result = discovery._filter_relevant_bills(housing_bills, "housing")
        assert result == []

    def test_invalid_json_returns_empty_list(self, discovery, housing_bills):
        fake_response = _fake_openai_response("not valid json{")
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake_response):
            result = discovery._filter_relevant_bills(housing_bills, "housing")
        assert result == []

    def test_prompt_includes_topic_name(self, discovery, housing_bills):
        fake_response = _fake_openai_response(json.dumps([]))
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake_response) as mock_create:
            discovery._filter_relevant_bills(housing_bills[:1], "environment")
        user_msg = mock_create.call_args.kwargs["messages"][1]["content"]
        assert "environment" in user_msg
        assert "SB 9" in user_msg  # bill_number from housing_bills[0]

    def test_prompt_truncates_description_to_two_hundred_chars(self, discovery):
        bill = {
            "bill_id": 42,
            "bill_number": "AB 42",
            "title": "Test Bill",
            "description": "x" * 500,
            "last_action": "",
        }
        fake_response = _fake_openai_response(json.dumps([]))
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake_response) as mock_create:
            discovery._filter_relevant_bills([bill], "housing")
        user_msg = mock_create.call_args.kwargs["messages"][1]["content"]
        # The prompt embeds the truncated description — exactly 200 x's, not 500.
        assert "x" * 200 in user_msg
        assert "x" * 201 not in user_msg

    def test_prompt_handles_none_description(self, discovery):
        bill = {
            "bill_id": 42,
            "bill_number": "AB 42",
            "title": "Test",
            "description": None,
            "last_action": None,
        }
        fake_response = _fake_openai_response(json.dumps([]))
        with patch.object(ld_module, "OPENAI_AVAILABLE", True), \
             patch.object(ld_module.openai.chat.completions, "create",
                          return_value=fake_response):
            # Should not raise — None is coerced to "" in the prompt builder.
            result = discovery._filter_relevant_bills([bill], "housing")
        assert result == []


# ---------------------------------------------------------------------------
# update_legislative_context — file I/O
# ---------------------------------------------------------------------------

class TestUpdateLegislativeContext:
    def test_dry_run_does_not_write_file(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bills = [{
            "bill_id": 1001,
            "bill_number": "SB 9",
            "title": "Lot Split",
            "description": "desc",
            "leverage_point": "Council decides",
        }]
        path = discovery.update_legislative_context("housing", bills, dry_run=True)
        assert path == Path("data/legislation/state/california/housing.json")
        assert not path.exists()

    def test_writes_new_context_file_with_pinned_structure(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bills = [{
            "bill_id": 1001,
            "bill_number": "SB 9",
            "title": "Lot Split",
            "description": "Allows lot splits in single-family zones.",
            "status": "Enacted",
            "status_date": "2025-09-01",
            "local_implementation_required": True,
            "deadline": "2026-01-01",
            "leverage_point": "Council adopts ordinance.",
            "url": "https://example.com/sb9",
        }]

        path = discovery.update_legislative_context("housing", bills, dry_run=False)

        assert path.exists()
        with open(path) as f:
            data = json.load(f)

        assert data["jurisdiction"] == "california"
        assert data["topic"] == "housing"
        assert data["data_sources"] == [
            "LegiScan API",
            "LLM-assisted relevance filtering",
            "Manual review",
        ]
        assert "ca-sb-9" in data["state_legislation"]
        entry = data["state_legislation"]["ca-sb-9"]
        assert entry["bill"] == "Lot Split"
        assert entry["status"] == "Enacted"
        assert entry["enacted"] == "2025-09-01"
        assert entry["local_implementation_required"] is True
        assert entry["local_deadline"] == "2026-01-01"
        assert entry["leverage_point"] == "Council adopts ordinance."
        assert entry["official_url"] == "https://example.com/sb9"
        assert entry["summary"] == "Allows lot splits in single-family zones."
        assert entry["_legiscan_id"] == 1001
        # Housing keywords truncated to 5.
        assert entry["keywords"] == [
            "housing", "affordable housing", "zoning", "density", "ADU"
        ]

    def test_summary_truncated_to_two_hundred_characters(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bills = [{
            "bill_id": 1,
            "bill_number": "SB 1",
            "title": "T",
            "description": "y" * 500,
        }]
        path = discovery.update_legislative_context("housing", bills, dry_run=False)
        with open(path) as f:
            data = json.load(f)
        assert data["state_legislation"]["ca-sb-1"]["summary"] == "y" * 200

    def test_existing_bill_key_is_not_overwritten(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing_path = tmp_path / "data/legislation/state/california/housing.json"
        existing_path.parent.mkdir(parents=True, exist_ok=True)
        existing_path.write_text(json.dumps({
            "jurisdiction": "california",
            "topic": "housing",
            "last_updated": "2025-01-01T00:00:00",
            "data_sources": ["manual"],
            "state_legislation": {
                "ca-sb-9": {
                    "bill": "Original SB 9 (do not overwrite)",
                    "leverage_point": "original",
                }
            },
            "federal_programs": {},
        }))

        incoming = [{
            "bill_id": 99,
            "bill_number": "SB 9",
            "title": "Should Not Clobber",
            "leverage_point": "new value",
        }]
        discovery.update_legislative_context("housing", incoming, dry_run=False)

        with open(existing_path) as f:
            data = json.load(f)
        # Key was present -> the original entry is preserved untouched.
        assert data["state_legislation"]["ca-sb-9"]["bill"] == "Original SB 9 (do not overwrite)"
        assert data["state_legislation"]["ca-sb-9"]["leverage_point"] == "original"

    def test_new_bill_added_alongside_existing(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing_path = tmp_path / "data/legislation/state/california/housing.json"
        existing_path.parent.mkdir(parents=True, exist_ok=True)
        existing_path.write_text(json.dumps({
            "jurisdiction": "california",
            "topic": "housing",
            "last_updated": "2025-01-01T00:00:00",
            "data_sources": [],
            "state_legislation": {"ca-sb-9": {"bill": "Existing"}},
            "federal_programs": {},
        }))

        incoming = [{
            "bill_id": 42,
            "bill_number": "AB 2097",
            "title": "Parking Minimums",
            "leverage_point": "City decides parking rules",
        }]
        discovery.update_legislative_context("housing", incoming, dry_run=False)

        with open(existing_path) as f:
            data = json.load(f)
        assert set(data["state_legislation"].keys()) == {"ca-sb-9", "ca-ab-2097"}
        assert data["state_legislation"]["ca-ab-2097"]["bill"] == "Parking Minimums"

    def test_defaults_when_bill_fields_missing(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bills = [{
            "bill_id": 7,
            "bill_number": "SB 7",
            # No title, status, leverage_point, etc.
            "description": "short desc",
        }]
        path = discovery.update_legislative_context("housing", bills, dry_run=False)
        with open(path) as f:
            data = json.load(f)
        entry = data["state_legislation"]["ca-sb-7"]
        # Falls back to bill_number when title missing.
        assert entry["bill"] == "SB 7"
        # Default status.
        assert entry["status"] == "Active"
        # Default local_implementation_required is True.
        assert entry["local_implementation_required"] is True
        # Default leverage_point.
        assert entry["leverage_point"] == "Local implementation details TBD"
        # Default official_url is empty string.
        assert entry["official_url"] == ""

    def test_bill_without_bill_number_uses_id_fallback_key(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bills = [{
            "bill_id": 555,
            "title": "Mystery Bill",
            "description": "no bill_number field",
        }]
        path = discovery.update_legislative_context("housing", bills, dry_run=False)
        with open(path) as f:
            data = json.load(f)
        # Fallback key is "bill-<bill_id>" then normalized.
        assert "ca-bill-555" in data["state_legislation"]

    def test_non_default_state_writes_to_state_specific_path(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bills = [{
            "bill_id": 1,
            "bill_number": "H 1",
            "title": "Texas Bill",
            "description": "desc",
        }]
        path = discovery.update_legislative_context(
            "housing", bills, state="texas", dry_run=False
        )
        assert path == Path("data/legislation/state/texas/housing.json")
        with open(path) as f:
            data = json.load(f)
        assert data["jurisdiction"] == "texas"

    def test_empty_bills_list_still_creates_file_skeleton(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = discovery.update_legislative_context("housing", [], dry_run=False)
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert data["state_legislation"] == {}
        assert data["federal_programs"] == {}
        assert data["topic"] == "housing"

    def test_empty_bills_on_existing_file_preserves_entries(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing_path = tmp_path / "data/legislation/state/california/housing.json"
        existing_path.parent.mkdir(parents=True, exist_ok=True)
        prior = {
            "jurisdiction": "california",
            "topic": "housing",
            "last_updated": "2025-01-01T00:00:00",
            "data_sources": ["existing"],
            "state_legislation": {"ca-sb-1": {"bill": "Keep me"}},
            "federal_programs": {"HUD-CDBG": {"program": "Block grant"}},
        }
        existing_path.write_text(json.dumps(prior))

        discovery.update_legislative_context("housing", [], dry_run=False)

        with open(existing_path) as f:
            data = json.load(f)
        assert data["state_legislation"] == {"ca-sb-1": {"bill": "Keep me"}}
        assert data["federal_programs"] == {"HUD-CDBG": {"program": "Block grant"}}

    def test_last_updated_is_refreshed_on_write(self, discovery, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing_path = tmp_path / "data/legislation/state/california/housing.json"
        existing_path.parent.mkdir(parents=True, exist_ok=True)
        existing_path.write_text(json.dumps({
            "jurisdiction": "california",
            "topic": "housing",
            "last_updated": "2020-01-01T00:00:00",
            "data_sources": [],
            "state_legislation": {},
            "federal_programs": {},
        }))

        discovery.update_legislative_context("housing", [], dry_run=False)

        with open(existing_path) as f:
            data = json.load(f)
        # The stale 2020 timestamp should have been replaced.
        assert data["last_updated"] != "2020-01-01T00:00:00"
        assert data["last_updated"].startswith("20")  # ISO timestamp
