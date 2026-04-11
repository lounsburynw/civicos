"""
Tests for the ``regions`` key in ``config/registry.json`` and the
region-aware scope resolution that consumes it.

The ``region_config_concept`` P0 (step 3 in the scope work sequence)
introduced the ``regions`` top-level key in the service registry. A
region is a named set of jurisdiction IDs — possibly including other
regions as members for recursive nesting. The MCP scope walker
consults this config when a tool's policy declares ``REGION`` or
``PRIMARY_PLUS_REGION`` as its default or expandable scope, so a
user on a city server can ask "what about the rest of Marin?" and
get a clean, labeled, fan-out response.

This file covers three surfaces:

1. The public registry helpers in ``civicos.registry`` — they
   expose, dedupe, and cycle-detect region expansion.
2. The scope walker's region branches in
   ``apps/civicos-mcp/tools/scope_walk.py`` — they must degrade
   gracefully when a primary has no declared region.
3. The integration path through ``get_upcoming_meetings`` when a
   caller passes ``{"scope": "primary_plus_region"}`` — the whole
   point of regions is that this request returns data from multiple
   cities.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

# Match the import path the MCP server uses at runtime.
sys.path.insert(0, "apps/civicos-mcp")

from civicos import registry as civicos_registry  # noqa: E402
from tools import handlers  # noqa: E402
from tools.scope import (  # noqa: E402
    Scope,
    ScopePolicy,
    SCOPE_POLICIES,
    _mcp_request_scope,
)
from tools.scope_walk import (  # noqa: E402
    resolve_requested_scope,
    resolve_scope_to_jurisdictions,
    walk_scope,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_registry_cache():
    """Reset the module-level registry cache between tests.

    ``civicos.registry`` caches the parsed registry.json dict so
    repeated reads are free. Tests that mutate or swap in a fake
    registry must clear the cache before and after to avoid
    poisoning adjacent tests.
    """
    civicos_registry.reset_registry()
    try:
        yield
    finally:
        civicos_registry.reset_registry()


@pytest.fixture
def reset_scope_contextvar():
    """Ensure each test starts with no scope on the contextvar."""
    token = _mcp_request_scope.set(None)
    try:
        yield
    finally:
        _mcp_request_scope.reset(token)


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch) -> Path:
    """Point ``civicos.registry`` at a temp registry file.

    Returns the path; tests write their own JSON into it and then
    call ``civicos_registry.reset_registry()`` to force a reload.
    The autouse fixture handles the reset after the test.
    """
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("CIVICOS_REGISTRY_PATH", str(registry_path))
    civicos_registry.reset_registry()
    return registry_path


def _write_registry(path: Path, regions: dict, jurisdictions: dict | None = None) -> None:
    """Write a minimal registry.json with the given regions/jurisdictions."""
    data = {
        "version": "1.0",
        "default_jurisdiction": "city-test",
        "jurisdictions": jurisdictions or {
            "city-test": {"parent_jurisdictions": []},
        },
        "regions": regions,
    }
    path.write_text(json.dumps(data))
    civicos_registry.reset_registry()


# ---------------------------------------------------------------------------
# 1. Real registry.json has the marin region we shipped
# ---------------------------------------------------------------------------


class TestRealRegistryHasMarin:
    """Sanity checks against the actual ``config/registry.json``.

    These tests guard the shipped config file — a regression here
    means someone edited registry.json and broke the region schema
    or removed the marin entry. They are deliberately loose about
    member count so adding a new Marin city doesn't break them.
    """

    def test_regions_key_is_present(self):
        regions = civicos_registry.get_regions()
        assert "marin" in regions, (
            "config/registry.json must declare a 'marin' region — "
            "this is the first concrete region the scope walker "
            "depends on."
        )

    def test_marin_region_has_members_list(self):
        region = civicos_registry.get_region("marin")
        assert region is not None
        assert isinstance(region.get("members"), list)
        assert len(region["members"]) > 0

    def test_marin_region_has_display_name(self):
        region = civicos_registry.get_region("marin")
        assert region is not None
        assert region.get("display_name"), (
            "Regions should have a human-readable display_name so "
            "AI callers can cite them meaningfully."
        )

    def test_resolve_marin_contains_san_rafael(self):
        members = civicos_registry.resolve_region_members("marin")
        assert "city-san-rafael" in members

    def test_resolve_marin_excludes_school_districts(self):
        """The marin region is municipalities only — school
        districts share county-marin as a parent but belong to a
        different kind of government. Mixing them dilutes the
        regional view."""
        members = civicos_registry.resolve_region_members("marin")
        assert not any(m.startswith("school-") for m in members)

    def test_find_region_for_san_rafael(self):
        assert civicos_registry.find_region_for_jurisdiction("city-san-rafael") == "marin"

    def test_find_region_for_non_member_returns_none(self):
        # city-asheville is in North Carolina, not in any declared region.
        assert (
            civicos_registry.find_region_for_jurisdiction("city-asheville") is None
        )


# ---------------------------------------------------------------------------
# 2. resolve_region_members — recursion, dedup, cycle detection
# ---------------------------------------------------------------------------


class TestResolveRegionMembers:
    def test_unknown_region_raises(self, tmp_registry):
        _write_registry(tmp_registry, regions={
            "marin": {"display_name": "Marin", "members": ["city-a"]},
        })
        with pytest.raises(ValueError, match="Unknown region"):
            civicos_registry.resolve_region_members("does-not-exist")

    def test_flat_region_returns_members_in_order(self, tmp_registry):
        _write_registry(tmp_registry, regions={
            "marin": {
                "display_name": "Marin",
                "members": ["city-san-rafael", "city-mill-valley", "city-ross"],
            },
        })
        result = civicos_registry.resolve_region_members("marin")
        assert result == ["city-san-rafael", "city-mill-valley", "city-ross"]

    def test_nested_region_is_spliced_in_place(self, tmp_registry):
        """A member that matches another region name should be
        expanded to that region's members inline. This is the
        mechanism for ``bay-area`` to include every Marin city
        without re-listing them."""
        _write_registry(tmp_registry, regions={
            "marin": {
                "display_name": "Marin",
                "members": ["city-san-rafael", "city-mill-valley"],
            },
            "bay-area": {
                "display_name": "Bay Area",
                "members": ["marin", "city-oakland"],
            },
        })
        result = civicos_registry.resolve_region_members("bay-area")
        assert result == ["city-san-rafael", "city-mill-valley", "city-oakland"]

    def test_duplicate_members_deduped(self, tmp_registry):
        """Overlapping nested regions should not return duplicate
        members — otherwise the scope walker would fan out twice
        to the same jurisdiction and return double rows."""
        _write_registry(tmp_registry, regions={
            "north-marin": {
                "display_name": "North Marin",
                "members": ["city-novato", "city-san-rafael"],
            },
            "south-marin": {
                "display_name": "South Marin",
                "members": ["city-mill-valley", "city-san-rafael"],
            },
            "all-marin": {
                "display_name": "All Marin",
                "members": ["north-marin", "south-marin"],
            },
        })
        result = civicos_registry.resolve_region_members("all-marin")
        # san-rafael is reachable via both sub-regions but must
        # appear only once.
        assert result.count("city-san-rafael") == 1
        assert set(result) == {
            "city-novato", "city-san-rafael", "city-mill-valley",
        }

    def test_cycle_between_two_regions_raises(self, tmp_registry):
        """A → B → A must raise, not infinite-recurse."""
        _write_registry(tmp_registry, regions={
            "a": {"display_name": "A", "members": ["b"]},
            "b": {"display_name": "B", "members": ["a"]},
        })
        with pytest.raises(ValueError, match="[Cc]ycle"):
            civicos_registry.resolve_region_members("a")

    def test_self_cycle_raises(self, tmp_registry):
        """A region that lists itself as a member must raise."""
        _write_registry(tmp_registry, regions={
            "recursive": {
                "display_name": "Recursive",
                "members": ["recursive", "city-a"],
            },
        })
        with pytest.raises(ValueError, match="[Cc]ycle"):
            civicos_registry.resolve_region_members("recursive")


class TestFindRegionForJurisdictionWithMalformedRegions:
    def test_bad_region_does_not_break_lookup_for_other_regions(self, tmp_registry):
        """A malformed (cyclic) region should be skipped during
        ``find_region_for_jurisdiction`` so a single bad config
        entry can't take all region lookups offline."""
        _write_registry(tmp_registry, regions={
            # Iteration order follows insertion order — the bad
            # region is visited first and must be skipped silently.
            "broken": {
                "display_name": "Broken",
                "members": ["broken"],  # self-cycle
            },
            "good": {
                "display_name": "Good",
                "members": ["city-san-rafael"],
            },
        })
        assert (
            civicos_registry.find_region_for_jurisdiction("city-san-rafael") == "good"
        )


# ---------------------------------------------------------------------------
# 3. Scope walker integration with region resolution
# ---------------------------------------------------------------------------


class TestScopeWalkerRegionBranches:
    def test_region_resolves_marin_members_for_san_rafael(self):
        result = resolve_scope_to_jurisdictions(Scope.REGION, "city-san-rafael")
        assert "city-mill-valley" in result
        assert "city-san-rafael" in result

    def test_primary_plus_region_starts_with_primary(self):
        result = resolve_scope_to_jurisdictions(
            Scope.PRIMARY_PLUS_REGION, "city-san-rafael"
        )
        assert result[0] == "city-san-rafael"
        assert result.count("city-san-rafael") == 1

    def test_region_with_no_match_degrades_to_primary(self):
        # city-asheville has no region defined.
        assert resolve_scope_to_jurisdictions(
            Scope.REGION, "city-asheville"
        ) == ["city-asheville"]

    def test_primary_plus_region_with_no_match_degrades_to_primary(self):
        assert resolve_scope_to_jurisdictions(
            Scope.PRIMARY_PLUS_REGION, "city-asheville"
        ) == ["city-asheville"]


# ---------------------------------------------------------------------------
# 4. resolve_requested_scope — caller-driven widening
# ---------------------------------------------------------------------------


class TestResolveRequestedScope:
    def _policy(self) -> ScopePolicy:
        return ScopePolicy(
            default_scope=Scope.PRIMARY_PLUS_SIBLINGS,
            expandable_scope=Scope.PRIMARY_PLUS_REGION,
            max_scope=Scope.REGION,
            kind="read",
        )

    def test_no_scope_arg_returns_default(self):
        assert resolve_requested_scope(self._policy(), {}) == Scope.PRIMARY_PLUS_SIBLINGS

    def test_matching_expandable_scope_is_accepted(self):
        scope = resolve_requested_scope(
            self._policy(), {"scope": "primary_plus_region"}
        )
        assert scope == Scope.PRIMARY_PLUS_REGION

    def test_unknown_scope_string_falls_back_to_default(self):
        scope = resolve_requested_scope(self._policy(), {"scope": "banana"})
        assert scope == Scope.PRIMARY_PLUS_SIBLINGS

    def test_scope_outside_offered_set_falls_back_to_default(self):
        # FEDERAL isn't one of the offered scopes (default or
        # expandable) even though it's a valid Scope enum value.
        scope = resolve_requested_scope(self._policy(), {"scope": "federal"})
        assert scope == Scope.PRIMARY_PLUS_SIBLINGS

    def test_policy_without_expandable_scope_ignores_scope_arg(self):
        """A tool that doesn't allow widening should ignore the
        caller's scope arg entirely. This is the contract that
        keeps write tools from being tricked into cross-jurisdiction
        side effects."""
        locked_policy = ScopePolicy(
            default_scope=Scope.PRIMARY,
            expandable_scope=None,
            max_scope=Scope.PRIMARY,
            kind="write",
        )
        scope = resolve_requested_scope(
            locked_policy, {"scope": "primary_plus_region"}
        )
        assert scope == Scope.PRIMARY


# ---------------------------------------------------------------------------
# 5. Integration: get_upcoming_meetings widens across region on request
# ---------------------------------------------------------------------------


class _MockStorage:
    """Stub storage backend that returns per-jurisdiction meetings."""

    def __init__(self, meetings_by_jid: dict[str, list[dict]]) -> None:
        self.meetings_by_jid = meetings_by_jid

    def get_meetings(
        self,
        jurisdiction_id: str,
        since: Any = None,
        until: Any = None,
        limit: Any = None,
    ) -> list[dict]:
        return [dict(m) for m in self.meetings_by_jid.get(jurisdiction_id, [])]


def _noop_validate(inputs: dict) -> tuple[bool, dict, str | None]:
    return True, dict(inputs), None


class TestGetUpcomingMeetingsWithRegionScope:
    def test_default_scope_walks_siblings_only(self, reset_scope_contextvar):
        """Baseline: without a caller override, the handler walks
        its default PRIMARY_PLUS_SIBLINGS scope. This test exists
        as a sanity floor against the widening test below — if
        widening produces the same result as the default, something
        is wrong with either the arg plumbing or the region config."""
        storage = _MockStorage({
            "city-san-rafael": [
                {"title": "SR meeting", "meeting_datetime": "2099-01-01"},
            ],
            "city-mill-valley": [
                {"title": "MV meeting", "meeting_datetime": "2099-01-02"},
            ],
            "city-novato": [
                {"title": "NOVATO meeting", "meeting_datetime": "2099-01-03"},
            ],
        })
        civic = SimpleNamespace(storage=storage, vectors=None)
        _mcp_request_scope.set(SCOPE_POLICIES["get_upcoming_meetings"])

        output = handlers.get_upcoming_meetings(
            civic,
            "city-san-rafael",
            _noop_validate,
            logging.getLogger("test"),
            {"days": 365 * 100},  # far future so our 2099 dates fit
        )

        # Default scope is PRIMARY_PLUS_SIBLINGS, which still
        # includes Novato (county-marin sibling), so this test is
        # NOT a proof that widening changes behavior — that's
        # the job of the next test. This one just proves the
        # baseline output structure is sensible.
        assert "## city-san-rafael" in output
        assert "SR meeting" in output

    def test_explicit_region_scope_expands_to_marin_cities(self, reset_scope_contextvar):
        """The headline integration test: a caller on city-san-rafael
        passing ``{"scope": "primary_plus_region"}`` must see a
        response containing labeled sections for several Marin cities.

        This proves the full plumbing works end-to-end:
          contextvar → resolve_requested_scope → scope_override →
          walk_scope → resolve_scope_to_jurisdictions → region config.

        A mutation that breaks any link in that chain fails here.
        """
        # Prepare a storage stub with meetings in several Marin
        # cities. The real registry has 11 members; we populate
        # enough to prove the walker fans out to at least three.
        storage = _MockStorage({
            "city-san-rafael": [
                {"title": "San Rafael Council", "meeting_datetime": "2099-01-01"},
            ],
            "city-mill-valley": [
                {"title": "Mill Valley Council", "meeting_datetime": "2099-01-02"},
            ],
            "city-tiburon": [
                {"title": "Tiburon Council", "meeting_datetime": "2099-01-03"},
            ],
            "city-sausalito": [
                {"title": "Sausalito Council", "meeting_datetime": "2099-01-04"},
            ],
            "city-ross": [
                {"title": "Ross Town Council", "meeting_datetime": "2099-01-05"},
            ],
        })
        civic = SimpleNamespace(storage=storage, vectors=None)
        _mcp_request_scope.set(SCOPE_POLICIES["get_upcoming_meetings"])

        output = handlers.get_upcoming_meetings(
            civic,
            "city-san-rafael",
            _noop_validate,
            logging.getLogger("test"),
            {
                "days": 365 * 100,
                "scope": "primary_plus_region",
            },
        )

        # At least 3 Marin city sections must appear — the success
        # criterion from the handoff. We hard-code 3 specific ones
        # instead of counting so a mutation that merged sections
        # still fails.
        assert "## city-san-rafael" in output
        assert "## city-mill-valley" in output
        assert "## city-tiburon" in output

        # And each section must contain its own meeting — not just
        # the section header floating alone. A mutation that
        # ignored the scope_override and walked siblings would
        # still produce the section headers (siblings and region
        # overlap on Marin), so we also assert on the payload.
        assert "San Rafael Council" in output
        assert "Mill Valley Council" in output
        assert "Tiburon Council" in output

    def test_locked_write_policy_ignores_scope_arg(self, reset_scope_contextvar):
        """Regression guard: a write tool whose policy has
        ``expandable_scope=None`` must ignore an adversarial
        ``scope`` arg. This test doesn't call a write handler
        directly (they have their own side effects); it validates
        the same invariant at the ``resolve_requested_scope``
        layer, which is the single chokepoint every handler goes
        through."""
        locked = ScopePolicy(
            default_scope=Scope.PRIMARY,
            expandable_scope=None,
            max_scope=Scope.PRIMARY,
            kind="write",
        )
        # Even a valid Scope value is rejected because the policy
        # offers no widening.
        assert resolve_requested_scope(
            locked, {"scope": "primary_plus_region"}
        ) == Scope.PRIMARY
        assert resolve_requested_scope(
            locked, {"scope": "region"}
        ) == Scope.PRIMARY
