"""
Tests that the scope policy is actually load-bearing at handler time.

The ``scope_policy_table`` P0 (shipped in commit 51cda249) declared
per-tool scope policies and set them on the ``_mcp_request_scope``
contextvar inside ``_wrap_handler``. This follow-up P0
(``scope_policy_passthrough``) makes the policy change what tool
handlers actually return: handlers resolve the scope to a list of
jurisdictions, fan storage calls across them, and stamp each result
with the jurisdiction it came from.

The headline assertion in this file is the "vertical expansion"
proof: calling ``search_legislation`` on a city primary with the
``PRIMARY_PLUS_ALL_PARENTS`` policy must return bills labeled with
both ``state-california`` and ``country-united-states``. If this
test fails, the promise of the scope policy ADR is not kept and
AI callers can't tell one government level from another.
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest

# Match the import path the MCP server uses at runtime.
sys.path.insert(0, "apps/civicos-mcp")

from tools import handlers  # noqa: E402
from tools.scope import (  # noqa: E402
    Scope,
    ScopePolicy,
    SCOPE_POLICIES,
    _mcp_request_scope,
)
from tools.scope_walk import (  # noqa: E402
    MAX_SCOPE_FANOUT,
    resolve_scope_to_jurisdictions,
    walk_scope,
)


# ---------------------------------------------------------------------------
# Mock scaffolding — minimal stand-ins for the CivicOS client surface
# ---------------------------------------------------------------------------


class _MockStorage:
    """Stub StorageBackend that returns per-state legislation fixtures."""

    def __init__(self, bills_by_state: dict[str, list[dict]]) -> None:
        self._bills_by_state = bills_by_state
        self.meetings_by_jid: dict[str, list[dict]] = {}

    def get_legislation(
        self,
        state: str,
        topic: str | None = None,
        status: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        # Return a copy so the walker's in-place jurisdiction stamping
        # doesn't mutate the fixture across tests.
        return [dict(b) for b in self._bills_by_state.get(state, [])][:limit]

    def get_meetings(
        self,
        jurisdiction_id: str,
        since=None,
        until=None,
        limit: int | None = None,
    ) -> list[dict]:
        return [dict(m) for m in self.meetings_by_jid.get(jurisdiction_id, [])]


class _MockVectorHit:
    def __init__(self, content: str, score: float) -> None:
        self.content = content
        self.score = score


class _MockVectors:
    def __init__(self, hits_by_jid: dict[str, list[_MockVectorHit]]) -> None:
        self._hits_by_jid = hits_by_jid

    def search(
        self,
        query: str,
        jurisdiction_id: str,
        corpus: str,
        top_k: int = 10,
    ) -> list[_MockVectorHit]:
        return list(self._hits_by_jid.get(jurisdiction_id, []))[:top_k]


def _noop_validate(inputs: dict) -> tuple[bool, dict, str | None]:
    return True, dict(inputs), None


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_scope_policy_passthrough")


@pytest.fixture
def legislation_civic() -> SimpleNamespace:
    """Civic stub wired for search_legislation vertical expansion tests."""
    bills_by_state = {
        "CA": [
            {
                "bill_id": "ca-sb100",
                "bill_number": "SB-100",
                "bill_name": "California Clean Energy Act",
                "state": "CA",
                "status": "Passed",
                "topic": "housing",
                "summary": "Statewide housing and energy goals.",
                "keywords": ["housing", "clean energy"],
            }
        ],
        "US": [
            {
                "bill_id": "us-hr1",
                "bill_number": "H.R.1",
                "bill_name": "Federal Housing Act",
                "state": "US",
                "status": "Introduced",
                "topic": "housing",
                "summary": "Federal housing policy framework.",
                "keywords": ["housing"],
            }
        ],
    }
    return SimpleNamespace(storage=_MockStorage(bills_by_state), vectors=None)


@pytest.fixture
def reset_scope_contextvar():
    """Ensure each test starts with no scope on the contextvar."""
    token = _mcp_request_scope.set(None)
    try:
        yield
    finally:
        _mcp_request_scope.reset(token)


# ---------------------------------------------------------------------------
# resolve_scope_to_jurisdictions — pure registry lookups
# ---------------------------------------------------------------------------


class TestResolveScopeToJurisdictions:
    def test_primary_only_returns_single_element(self):
        assert resolve_scope_to_jurisdictions(Scope.PRIMARY, "city-san-rafael") == [
            "city-san-rafael"
        ]

    def test_primary_plus_all_parents_full_chain(self):
        result = resolve_scope_to_jurisdictions(
            Scope.PRIMARY_PLUS_ALL_PARENTS, "city-san-rafael"
        )
        # Must include the primary first, then the vertical chain.
        assert result[0] == "city-san-rafael"
        assert "county-marin" in result
        assert "state-california" in result
        assert "country-united-states" in result

    def test_primary_plus_parent_only_direct_parent(self):
        result = resolve_scope_to_jurisdictions(
            Scope.PRIMARY_PLUS_PARENT, "city-san-rafael"
        )
        assert result == ["city-san-rafael", "county-marin"]

    def test_primary_plus_siblings_includes_other_marin_cities(self):
        result = resolve_scope_to_jurisdictions(
            Scope.PRIMARY_PLUS_SIBLINGS, "city-san-rafael"
        )
        assert result[0] == "city-san-rafael"
        assert "city-mill-valley" in result
        assert "city-san-anselmo" in result

    def test_federal_always_returns_country(self):
        result = resolve_scope_to_jurisdictions(Scope.FEDERAL, "city-san-rafael")
        assert result == ["country-united-states"]

    def test_state_snaps_to_state_ancestor(self):
        result = resolve_scope_to_jurisdictions(Scope.STATE, "city-san-rafael")
        assert result == ["state-california"]

    def test_region_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="region"):
            resolve_scope_to_jurisdictions(Scope.REGION, "city-san-rafael")

    def test_primary_plus_region_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="region"):
            resolve_scope_to_jurisdictions(
                Scope.PRIMARY_PLUS_REGION, "city-san-rafael"
            )


# ---------------------------------------------------------------------------
# walk_scope — fan-out + labeling
# ---------------------------------------------------------------------------


class TestWalkScope:
    def test_stamps_jurisdiction_on_each_row(self):
        policy = ScopePolicy(
            default_scope=Scope.PRIMARY_PLUS_ALL_PARENTS,
            expandable_scope=None,
            max_scope=Scope.FEDERAL,
            kind="read",
        )

        def _call(jid: str) -> list[dict]:
            if jid == "state-california":
                return [{"id": "ca-bill"}]
            if jid == "country-united-states":
                return [{"id": "us-bill"}]
            return []

        rows = walk_scope(policy, "city-san-rafael", _call)
        labels = {row["jurisdiction"] for row in rows}
        assert labels == {"state-california", "country-united-states"}

    def test_preserves_existing_jurisdiction_field(self):
        policy = ScopePolicy(
            default_scope=Scope.PRIMARY,
            expandable_scope=None,
            max_scope=Scope.PRIMARY,
            kind="read",
        )

        def _call(jid: str) -> list[dict]:
            return [{"id": "x", "jurisdiction": "pre-stamped"}]

        rows = walk_scope(policy, "city-san-rafael", _call)
        assert rows[0]["jurisdiction"] == "pre-stamped"

    def test_none_policy_degrades_to_primary(self):
        seen: list[str] = []

        def _call(jid: str) -> list[dict]:
            seen.append(jid)
            return []

        walk_scope(None, "city-san-rafael", _call)
        assert seen == ["city-san-rafael"]

    def test_failing_storage_call_does_not_poison_walk(self):
        policy = ScopePolicy(
            default_scope=Scope.PRIMARY_PLUS_ALL_PARENTS,
            expandable_scope=None,
            max_scope=Scope.FEDERAL,
            kind="read",
        )

        def _call(jid: str) -> list[dict]:
            if jid == "state-california":
                raise RuntimeError("simulated failure")
            return [{"id": f"ok-{jid}"}]

        rows = walk_scope(policy, "city-san-rafael", _call)
        labels = {row["jurisdiction"] for row in rows}
        # California silently dropped; the other jurisdictions still present.
        assert "state-california" not in labels
        assert labels  # non-empty

    def test_region_scope_raises_through_walk(self):
        policy = ScopePolicy(
            default_scope=Scope.REGION,
            expandable_scope=None,
            max_scope=Scope.REGION,
            kind="read",
        )
        with pytest.raises(NotImplementedError):
            walk_scope(policy, "city-san-rafael", lambda _jid: [])

    def test_max_fanout_cap_is_below_total_registry_size(self):
        # Defense-in-depth: a misconfigured policy can't cause the
        # walker to hit every jurisdiction in registry.json.
        assert MAX_SCOPE_FANOUT < 100


# ---------------------------------------------------------------------------
# search_legislation — the vertical-expansion promise from the ADR
# ---------------------------------------------------------------------------


class TestSearchLegislationPassthrough:
    def test_vertical_expansion_labels_state_and_federal(
        self, legislation_civic, logger, reset_scope_contextvar
    ):
        """The headline test: a city caller with PRIMARY_PLUS_ALL_PARENTS
        must see bills labeled with state-california and
        country-united-states — not just a flat unlabeled list."""
        _mcp_request_scope.set(SCOPE_POLICIES["search_legislation"])

        output = handlers.search_legislation(
            legislation_civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"query": "housing"},
        )

        assert "state-california" in output, (
            "CA bills must be labeled with state-california so callers "
            "can tell which government level issued them."
        )
        assert "country-united-states" in output, (
            "Federal bills must be labeled with country-united-states "
            "so callers can tell federal from state."
        )
        # The bills themselves should still render.
        assert "SB-100" in output
        assert "H.R.1" in output

        # Structural assertion: the jurisdiction label must appear
        # on the same header line as its bill. Handler format is
        # ``## <bill_number> (<state>) — <jurisdiction>``, so a
        # mutation that moved labels to a summary section would
        # fail here even though the words still appear in output.
        assert "SB-100 (CA) — state-california" in output, (
            "state-california label must be attached to the SB-100 "
            "header, not floating elsewhere in the response."
        )
        assert "H.R.1 (US) — country-united-states" in output, (
            "country-united-states label must be attached to the "
            "H.R.1 header."
        )

    def test_explicit_state_arg_overrides_scope_walk(
        self, legislation_civic, logger, reset_scope_contextvar
    ):
        """When the caller passes an explicit state= arg, the scope
        walker is bypassed — the caller asked for one state, give
        them one state."""
        _mcp_request_scope.set(SCOPE_POLICIES["search_legislation"])

        output = handlers.search_legislation(
            legislation_civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"query": "housing", "state": "CA"},
        )

        assert "SB-100" in output
        # Federal bill should NOT appear: we explicitly restricted to CA.
        assert "H.R.1" not in output

    def test_no_scope_falls_back_to_default_states(
        self, legislation_civic, logger, reset_scope_contextvar
    ):
        """Direct callers (tests, non-MCP code paths) still get the
        legacy ``_default_legislation_states`` behavior. The legacy
        path does not stamp jurisdiction labels — absence of labels
        is what proves the code went through the fallback path and
        not through walk_scope."""
        # contextvar is None via the reset_scope_contextvar fixture.
        output = handlers.search_legislation(
            legislation_civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"query": "housing"},
        )

        # Both bills render (legacy path uses _default_legislation_states
        # which returns ["CA", "US"] for city-level jurisdictions).
        assert "SB-100" in output
        assert "H.R.1" in output

        # Critical: no jurisdiction labels stamped. If these appear,
        # the handler is on the scope-policy path instead of the
        # fallback — a regression that would mask scope-policy bugs
        # in tests that don't set the contextvar.
        assert "state-california" not in output, (
            "Legacy path must not stamp state-california — its "
            "presence means the scope-policy path ran instead, "
            "making the fallback untestable."
        )
        assert "country-united-states" not in output, (
            "Legacy path must not stamp country-united-states."
        )


# ---------------------------------------------------------------------------
# get_upcoming_meetings — fan-out over sibling cities via get_meetings
# ---------------------------------------------------------------------------


class TestUpcomingMeetingsPassthrough:
    def test_siblings_are_labeled_in_output(self, logger, reset_scope_contextvar):
        """Sibling cities must appear as labeled sections and each
        section must contain its own meetings — a mutation that
        swapped titles between jurisdictions must fail here."""
        storage = _MockStorage(bills_by_state={})
        storage.meetings_by_jid = {
            "city-san-rafael": [
                {"title": "San Rafael Council", "meeting_datetime": "2026-04-14"}
            ],
            "city-mill-valley": [
                {"title": "Mill Valley Council", "meeting_datetime": "2026-04-15"}
            ],
        }
        civic = SimpleNamespace(storage=storage, vectors=None)

        _mcp_request_scope.set(SCOPE_POLICIES["get_upcoming_meetings"])

        output = handlers.get_upcoming_meetings(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"days": 7},
        )

        # Section headers must be present.
        assert "## city-san-rafael" in output
        assert "## city-mill-valley" in output

        # Structural pairing: the San Rafael meeting must appear
        # under the San Rafael section, not under Mill Valley. We
        # slice the output into per-jurisdiction sections and
        # check each contains the right meeting. A mutation that
        # fanned the storage call out to the wrong jurisdiction
        # would fail this even if both strings still appear.
        sr_idx = output.index("## city-san-rafael")
        mv_idx = output.index("## city-mill-valley")
        # San Rafael section is whatever sits between its header
        # and the next section header (or end of string).
        if sr_idx < mv_idx:
            sr_section = output[sr_idx:mv_idx]
            mv_section = output[mv_idx:]
        else:
            mv_section = output[mv_idx:sr_idx]
            sr_section = output[sr_idx:]

        assert "San Rafael Council" in sr_section
        assert "Mill Valley Council" in mv_section
        # And definitely not swapped:
        assert "Mill Valley Council" not in sr_section
        assert "San Rafael Council" not in mv_section


# ---------------------------------------------------------------------------
# find_similar_issues — per-jurisdiction vector.search with labeled sections
# ---------------------------------------------------------------------------


class TestFindSimilarIssuesPassthrough:
    def test_per_jurisdiction_sections_are_emitted(
        self, logger, reset_scope_contextvar
    ):
        hits_by_jid = {
            "city-san-rafael": [_MockVectorHit("pothole on A street", 0.9)],
            "city-mill-valley": [_MockVectorHit("pothole on B street", 0.8)],
        }
        civic = SimpleNamespace(
            storage=_MockStorage(bills_by_state={}),
            vectors=_MockVectors(hits_by_jid),
        )

        _mcp_request_scope.set(SCOPE_POLICIES["find_similar_issues"])

        output = handlers.find_similar_issues(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"topic": "potholes", "limit": 10},
        )

        assert "## city-san-rafael" in output
        assert "## city-mill-valley" in output
        assert "A street" in output
        assert "B street" in output


# ---------------------------------------------------------------------------
# get_started — Governance Stack section from resolved scope
# ---------------------------------------------------------------------------


class TestGetStartedPassthrough:
    def test_governance_stack_lists_parent_jurisdictions(
        self, logger, reset_scope_contextvar, monkeypatch
    ):
        """get_started delegates to city_pulse, then appends the
        governance stack. We stub city_pulse so the test doesn't
        depend on a live CivicOS instance."""
        monkeypatch.setattr(
            handlers, "city_pulse", lambda *args, **kwargs: {}
        )

        civic = SimpleNamespace(storage=None, vectors=None)
        _mcp_request_scope.set(SCOPE_POLICIES["get_started"])

        output = handlers.get_started(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {},
        )

        assert "## Governance Stack" in output
        assert "county-marin" in output
        assert "state-california" in output
        assert "country-united-states" in output
