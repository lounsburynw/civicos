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

    def test_region_resolves_via_registry_config(self):
        """Region config landed in step 3 (``region_config_concept``).
        Resolving ``Scope.REGION`` on a primary that belongs to a
        declared region must return the region's members. See
        ``config/registry.json`` regions.marin."""
        result = resolve_scope_to_jurisdictions(
            Scope.REGION, "city-san-rafael"
        )
        # San Rafael is a Marin city, so the region expansion must
        # include at least a few of its peers. The exact member
        # list lives in registry.json; we assert on presence, not
        # on count, so adding a new Marin city doesn't break this test.
        assert "city-mill-valley" in result
        assert "city-san-anselmo" in result
        assert "city-san-rafael" in result  # primary is in its own region
        # School districts share county-marin as a parent but are
        # intentionally excluded from the Marin *cities* region.
        assert not any(jid.startswith("school-") for jid in result), (
            "Marin region should be municipalities only — school "
            "districts share a county parent but are a different "
            "kind of government and don't belong in the city region."
        )

    def test_primary_plus_region_includes_primary_and_region_members(self):
        """``PRIMARY_PLUS_REGION`` must start with the primary and
        then include the region's members, deduped."""
        result = resolve_scope_to_jurisdictions(
            Scope.PRIMARY_PLUS_REGION, "city-san-rafael"
        )
        assert result[0] == "city-san-rafael"
        assert "city-mill-valley" in result
        # Dedup: primary should appear exactly once even though it's
        # also a member of the marin region.
        assert result.count("city-san-rafael") == 1

    def test_region_scope_for_primary_outside_any_region_degrades_to_primary(self):
        """A primary that isn't a member of any declared region
        should degrade gracefully to primary-only — the walker
        must never leave a tool with zero jurisdictions to query."""
        # city-asheville has no region declared in registry.json.
        result = resolve_scope_to_jurisdictions(
            Scope.REGION, "city-asheville"
        )
        assert result == ["city-asheville"]

        result = resolve_scope_to_jurisdictions(
            Scope.PRIMARY_PLUS_REGION, "city-asheville"
        )
        assert result == ["city-asheville"]


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

    def test_region_scope_walks_region_members(self):
        """After ``region_config_concept`` shipped, walking a
        ``REGION`` policy must fan the storage call out across the
        region's members and stamp each row with its jurisdiction.
        The old assertion (``raises NotImplementedError``) was the
        pre-step-3 invariant; this is its replacement."""
        policy = ScopePolicy(
            default_scope=Scope.REGION,
            expandable_scope=None,
            max_scope=Scope.REGION,
            kind="read",
        )

        seen: list[str] = []

        def _call(jid: str) -> list[dict]:
            seen.append(jid)
            return [{"id": f"row-{jid}"}]

        rows = walk_scope(policy, "city-san-rafael", _call)

        # The walker must have visited at least a couple of Marin
        # cities (the exact list is defined in config/registry.json).
        assert "city-mill-valley" in seen
        assert "city-san-rafael" in seen

        # Each returned row is stamped with its source jurisdiction.
        labels = {row["jurisdiction"] for row in rows}
        assert "city-mill-valley" in labels
        assert "city-san-rafael" in labels

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


# ---------------------------------------------------------------------------
# get_leverage_points — vertical expansion for citizen-action bills
# ---------------------------------------------------------------------------


@pytest.fixture
def leverage_civic() -> SimpleNamespace:
    """Civic stub wired for get_leverage_points vertical-expansion tests.

    Each state has a leverage bill and a non-leverage bill so the
    handler's filter-for-leverage logic can be observed. Scope walking
    must pick up the leverage bills from both CA and US and stamp each
    with the source jurisdiction.
    """
    bills_by_state = {
        "CA": [
            {
                "bill_id": "ca-sb22",
                "bill_number": "SB-22",
                "bill_name": "California Tenant Protection",
                "state": "CA",
                "status": "In Committee",
                "topic": "housing",
                "summary": "Eviction moratorium extension.",
                "leverage_point": "Testify at your state senator's town hall",
                "keywords": ["housing"],
            },
            {
                "bill_id": "ca-sb99",
                "bill_number": "SB-99",
                "bill_name": "Procedural Reform",
                "state": "CA",
                "status": "Introduced",
                "topic": "other",
                "summary": "Admin reform, no community angle.",
                "leverage_point": None,  # must be filtered out
                "keywords": [],
            },
        ],
        "US": [
            {
                "bill_id": "us-hr42",
                "bill_number": "H.R.42",
                "bill_name": "Federal Housing Assistance Act",
                "state": "US",
                "status": "In Committee",
                "topic": "housing",
                "summary": "Federal housing subsidy expansion.",
                "leverage_point": "Contact your representative before the committee vote",
                "keywords": ["housing"],
            }
        ],
    }
    return SimpleNamespace(storage=_MockStorage(bills_by_state), vectors=None)


class TestGetLeveragePointsPassthrough:
    def test_vertical_expansion_labels_state_and_federal(
        self, leverage_civic, logger, reset_scope_contextvar
    ):
        """With the scope policy active, a city caller must see
        leverage bills from both CA and the US, each labeled with
        the source jurisdiction in its header — matching the promise
        of search_legislation."""
        _mcp_request_scope.set(SCOPE_POLICIES["get_leverage_points"])

        output = handlers.get_leverage_points(
            leverage_civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"topic": "housing"},
        )

        # Both state and federal leverage bills present.
        assert "SB-22" in output
        assert "H.R.42" in output

        # Structural assertion: jurisdiction label attached to the
        # bill header line. A mutation that moved the label into a
        # summary section would still show both strings elsewhere
        # but fail this pair of assertions.
        assert "SB-22 (CA) — state-california" in output, (
            "state-california label must be stamped on the SB-22 "
            "header by walk_scope, not floating elsewhere."
        )
        assert "H.R.42 (US) — country-united-states" in output, (
            "country-united-states label must be stamped on the "
            "H.R.42 header."
        )

        # The non-leverage bill must not appear — the handler's
        # filter-for-leverage logic is preserved through the walk.
        assert "SB-99" not in output
        assert "Procedural Reform" not in output

    def test_explicit_state_arg_overrides_scope_walk(
        self, leverage_civic, logger, reset_scope_contextvar
    ):
        """An explicit ``state`` arg bypasses scope walking — the
        caller asked for one state, give them one state. Federal
        bill must be absent from the output."""
        _mcp_request_scope.set(SCOPE_POLICIES["get_leverage_points"])

        output = handlers.get_leverage_points(
            leverage_civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"topic": "housing", "state": "CA"},
        )

        assert "SB-22" in output
        assert "H.R.42" not in output, (
            "Explicit state=CA must not return federal bills."
        )

    def test_no_scope_falls_back_to_default_states(
        self, leverage_civic, logger, reset_scope_contextvar
    ):
        """Direct callers (no scope on contextvar) still see the
        legacy ``_default_legislation_states`` behavior: for a city
        primary that's ``["CA", "US"]``. The legacy path does NOT
        stamp jurisdiction labels — absence of labels proves the
        fallback path ran, not walk_scope."""
        output = handlers.get_leverage_points(
            leverage_civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"topic": "housing"},
        )

        # Both bills still render via the legacy CA+US fetch.
        assert "SB-22" in output
        assert "H.R.42" in output

        # Critical: no jurisdiction labels stamped. If these appear,
        # the handler is on the scope-policy path instead of the
        # fallback — a regression that would mask scope-policy bugs
        # in tests that don't set the contextvar.
        assert "state-california" not in output, (
            "Legacy path must not stamp state-california."
        )
        assert "country-united-states" not in output, (
            "Legacy path must not stamp country-united-states."
        )


# ---------------------------------------------------------------------------
# list_initiatives — per-jurisdiction relay fan-out
# ---------------------------------------------------------------------------


class TestListInitiativesPassthrough:
    def test_siblings_are_queried_and_labeled(
        self, logger, reset_scope_contextvar, monkeypatch
    ):
        """With the PRIMARY_PLUS_SIBLINGS policy active, the handler
        must fan the relay call out across the resolved sibling
        cities, group the results under per-jurisdiction section
        headers, and include each sibling's initiatives under its
        own header. The mock relay returns different initiatives per
        jurisdiction so a mutation that swapped jurisdictions would
        fail the structural pairing check."""
        # Per-jurisdiction canned responses from the "relay".
        responses_by_jid: dict[str, list[dict]] = {
            "city-san-rafael": [
                {
                    "id": "init:san-rafael:001",
                    "title": "San Rafael crosswalk",
                    "topic": "traffic safety",
                    "status": "active",
                    "voice_count": 3,
                    "public_key": "aaaa" * 16,
                    "timestamp": "2026-04-01T00:00:00Z",
                    "description": "Crosswalk on 4th street",
                }
            ],
            "city-mill-valley": [
                {
                    "id": "init:mill-valley:001",
                    "title": "Mill Valley bike lane",
                    "topic": "transportation",
                    "status": "active",
                    "voice_count": 7,
                    "public_key": "bbbb" * 16,
                    "timestamp": "2026-04-02T00:00:00Z",
                    "description": "Protected bike lane on Miller Ave",
                }
            ],
        }

        # Track which jurisdictions the relay was asked about so we
        # can assert the walker actually fanned out — seeing both
        # initiatives in the output would be consistent with a
        # mocked-at-a-higher-level shortcut, but inspecting the
        # jids visited is the stricter structural proof.
        queried_jids: list[str] = []

        class _FakeResponse:
            def __init__(self, data: list[dict]) -> None:
                self._data = data
                self.status_code = 200
                self.text = ""

            def json(self) -> list[dict]:
                return self._data

        class _FakeClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> None:
                return None

            def get(self, url: str, params=None) -> _FakeResponse:
                # URL format: {relay}/coordination/initiatives/{jid}
                jid = url.rstrip("/").rsplit("/", 1)[-1]
                queried_jids.append(jid)
                return _FakeResponse(responses_by_jid.get(jid, []))

        # Patch httpx.Client for this test.
        import httpx
        monkeypatch.setattr(httpx, "Client", _FakeClient)

        civic = SimpleNamespace(storage=None, vectors=None)
        _mcp_request_scope.set(SCOPE_POLICIES["list_initiatives"])

        output = handlers.list_initiatives(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {},
        )

        # Walker must have visited BOTH the primary and at least one
        # sibling. The exact sibling set comes from registry.json, so
        # we assert presence rather than exact membership.
        assert "city-san-rafael" in queried_jids
        assert "city-mill-valley" in queried_jids, (
            f"Walker should fan out to siblings; queried={queried_jids}"
        )

        # Both initiatives render.
        assert "San Rafael crosswalk" in output
        assert "Mill Valley bike lane" in output

        # Section headers stamped by walk_scope — prove the
        # per-jurisdiction grouping is intact.
        assert "## city-san-rafael" in output
        assert "## city-mill-valley" in output

        # Structural pairing: San Rafael's initiative must sit
        # under San Rafael's section, Mill Valley's under Mill
        # Valley's. A mutation that swapped fan-out targets would
        # show both strings but fail this pairing.
        sr_idx = output.index("## city-san-rafael")
        mv_idx = output.index("## city-mill-valley")
        if sr_idx < mv_idx:
            sr_section = output[sr_idx:mv_idx]
            mv_section = output[mv_idx:]
        else:
            mv_section = output[mv_idx:sr_idx]
            sr_section = output[sr_idx:]

        assert "San Rafael crosswalk" in sr_section
        assert "Mill Valley bike lane" in mv_section
        assert "Mill Valley bike lane" not in sr_section
        assert "San Rafael crosswalk" not in mv_section

    def test_unreachable_sibling_does_not_poison_walk(
        self, logger, reset_scope_contextvar, monkeypatch
    ):
        """If one sibling's relay call fails (connect error / 500),
        the other siblings' results must still render. This is the
        ``_fetch_initiatives_for_jurisdiction`` contract: swallow
        per-jurisdiction errors and return an empty list so
        ``walk_scope`` can keep walking."""
        import httpx

        class _FakeResponse:
            def __init__(self, data: list[dict], status: int = 200) -> None:
                self._data = data
                self.status_code = status
                self.text = "simulated"

            def json(self) -> list[dict]:
                return self._data

        class _FakeClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> None:
                return None

            def get(self, url: str, params=None):
                jid = url.rstrip("/").rsplit("/", 1)[-1]
                if jid == "city-san-rafael":
                    return _FakeResponse([
                        {
                            "id": "init:san-rafael:alive",
                            "title": "Still alive initiative",
                            "topic": "t",
                            "status": "active",
                            "voice_count": 1,
                            "public_key": "c" * 64,
                            "timestamp": "2026-04-01T00:00:00Z",
                            "description": "x",
                        }
                    ])
                if jid == "city-mill-valley":
                    raise httpx.ConnectError("simulated outage")
                return _FakeResponse([])

        monkeypatch.setattr(httpx, "Client", _FakeClient)

        civic = SimpleNamespace(storage=None, vectors=None)
        _mcp_request_scope.set(SCOPE_POLICIES["list_initiatives"])

        output = handlers.list_initiatives(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {},
        )

        # The surviving initiative must render.
        assert "Still alive initiative" in output
        # The handler must not propagate the ConnectError as the
        # top-level response — a transient sibling failure must not
        # take the whole tool offline.
        assert "simulated outage" not in output
        assert "Error listing initiatives" not in output

    def test_no_scope_falls_back_to_single_jurisdiction_query(
        self, logger, reset_scope_contextvar, monkeypatch
    ):
        """Direct callers (no scope on contextvar) see the legacy
        single-jurisdiction output shape. The response header is
        ``# Initiatives in {jurisdiction}`` — not the multi-section
        ``(and siblings)`` variant — which proves the legacy path
        ran instead of walk_scope."""
        import httpx

        queried_jids: list[str] = []

        class _FakeResponse:
            def __init__(self, data: list[dict]) -> None:
                self._data = data
                self.status_code = 200
                self.text = ""

            def json(self) -> list[dict]:
                return self._data

        class _FakeClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> None:
                return None

            def get(self, url: str, params=None) -> _FakeResponse:
                jid = url.rstrip("/").rsplit("/", 1)[-1]
                queried_jids.append(jid)
                return _FakeResponse([
                    {
                        "id": "init:001",
                        "title": "Legacy initiative",
                        "topic": "t",
                        "status": "active",
                        "voice_count": 0,
                        "public_key": "a" * 64,
                        "timestamp": "2026-04-01T00:00:00Z",
                        "description": "x",
                    }
                ])

        monkeypatch.setattr(httpx, "Client", _FakeClient)

        civic = SimpleNamespace(storage=None, vectors=None)
        # No contextvar set → policy is None → legacy path.

        output = handlers.list_initiatives(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {},
        )

        # Only the primary was queried — no sibling fan-out.
        assert queried_jids == ["city-san-rafael"]

        # Output is the legacy shape ("# Initiatives in {jid}", not
        # "(and siblings)"), so the walker code path was NOT taken.
        assert "# Initiatives in city-san-rafael" in output
        assert "(and siblings)" not in output
        assert "Legacy initiative" in output


# ---------------------------------------------------------------------------
# list_relays — policy demoted to PRIMARY; fan-out is a no-op
# ---------------------------------------------------------------------------


class TestListRelaysScope:
    def test_policy_is_primary_only(self):
        """list_relays returns a jurisdiction-agnostic static list
        (KNOWN_RELAYS), so its scope policy must declare PRIMARY,
        not PRIMARY_PLUS_SIBLINGS. This assertion exists to catch
        a regression where someone 're-expands' the policy without
        actually implementing sibling fan-out — a silent no-op
        that would mislead callers about the tool's real reach."""
        policy = SCOPE_POLICIES["list_relays"]
        assert policy.default_scope == Scope.PRIMARY
        assert policy.max_scope == Scope.PRIMARY
        assert policy.expandable_scope is None


# ---------------------------------------------------------------------------
# get_funding_flow — vertical expansion through walk_scope
# ---------------------------------------------------------------------------


class _FakeFundingFlow:
    """Minimal stand-in for a FundingFlow dataclass."""

    def __init__(self, budget_description, department, budget_dollars, federal_program_name=None):
        self.budget_description = budget_description
        self.department = department
        self.budget_dollars = budget_dollars
        self.federal_program_name = federal_program_name


class TestGetFundingFlowPassthrough:
    def test_vertical_expansion_fans_out_to_parent(
        self, logger, reset_scope_contextvar
    ):
        """With PRIMARY_PLUS_PARENT default, the handler must call
        funding_flow for both the primary and its direct parent,
        and the output must contain labeled sections for each."""
        calls: list[str] = []

        def _mock_funding_flow(program=None, cfda_number=None, jurisdiction_id=None, **kw):
            calls.append(jurisdiction_id)
            if jurisdiction_id == "city-san-rafael":
                return [
                    _FakeFundingFlow("CDBG Housing", "Community Dev", 500_000, "CDBG")
                ]
            elif jurisdiction_id == "county-marin":
                return [
                    _FakeFundingFlow("County Transit Grant", "Public Works", 200_000, "FTA")
                ]
            return []

        civic = SimpleNamespace(
            storage=_MockStorage(bills_by_state={}),
            vectors=None,
            funding_flow=_mock_funding_flow,
        )

        _mcp_request_scope.set(SCOPE_POLICIES["get_funding_flow"])

        output = handlers.get_funding_flow(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {},
        )

        # Both jurisdictions must be queried (exactly 2 calls).
        assert len(calls) == 2
        assert "city-san-rafael" in calls
        assert "county-marin" in calls

        # Output must contain labeled sections.
        assert "## city-san-rafael" in output
        assert "## county-marin" in output

        # Content must appear under the correct section.
        sr_idx = output.index("## city-san-rafael")
        cm_idx = output.index("## county-marin")
        if sr_idx < cm_idx:
            sr_section = output[sr_idx:cm_idx]
            cm_section = output[cm_idx:]
        else:
            cm_section = output[cm_idx:sr_idx]
            sr_section = output[sr_idx:]

        assert "CDBG Housing" in sr_section
        assert "County Transit Grant" in cm_section
        assert "County Transit Grant" not in sr_section
        assert "CDBG Housing" not in cm_section

    def test_legacy_path_without_scope_policy(self, logger, reset_scope_contextvar):
        """When no scope policy is set, the handler must fall through
        to the legacy path calling civic.funding_flow() without
        jurisdiction_id."""
        def _mock_funding_flow(program=None, cfda_number=None, **kw):
            return [_FakeFundingFlow("Legacy Grant", "Admin", 100_000)]

        civic = SimpleNamespace(
            storage=_MockStorage(bills_by_state={}),
            vectors=None,
            funding_flow=_mock_funding_flow,
        )

        # No scope set — contextvar is None from reset fixture.
        output = handlers.get_funding_flow(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"program": "test"},
        )

        assert "Legacy Grant" in output
        # No jurisdiction sections in legacy mode.
        assert "## city-san-rafael" not in output


# ---------------------------------------------------------------------------
# get_intergovernmental_revenue — vertical expansion through walk_scope
# ---------------------------------------------------------------------------


class _FakeRevenueSummary:
    """Minimal stand-in for IntergovernmentalRevenueSummary."""

    def __init__(self, entity_name, fiscal_year, total, federal, state, county, undetermined=0, details=None):
        self.entity_name = entity_name
        self.fiscal_year = fiscal_year
        self.total_dollars = total
        self.federal_total_dollars = federal
        self.state_total_dollars = state
        self.county_total_dollars = county
        self.undetermined_total_dollars = undetermined
        self.details = details or []


class _FakeRevenueDetail:
    """Minimal stand-in for IntergovernmentalRevenue."""

    def __init__(self, line_description, amount_dollars, source, category=None):
        self.line_description = line_description
        self.amount_dollars = amount_dollars
        self.source = source
        self.category = category


class TestGetIntergovernmentalRevenuePassthrough:
    def test_vertical_expansion_fans_out_to_parent(
        self, logger, reset_scope_contextvar
    ):
        """With PRIMARY_PLUS_PARENT default, the handler must call
        intergovernmental_revenue for both the primary and its direct
        parent, and the output must contain labeled sections for each."""
        calls: list[str] = []

        def _mock_revenue(fiscal_year=None, source=None, jurisdiction_id=None):
            calls.append(jurisdiction_id)
            if jurisdiction_id == "city-san-rafael":
                return _FakeRevenueSummary(
                    "San Rafael", 2024, 8_000_000, 171_000, 7_000_000, 829_000,
                    details=[_FakeRevenueDetail("Gas Tax", 3_000_000, "state")],
                )
            elif jurisdiction_id == "county-marin":
                return _FakeRevenueSummary(
                    "Marin County", 2024, 50_000_000, 5_000_000, 40_000_000, 5_000_000,
                    details=[_FakeRevenueDetail("Realignment", 10_000_000, "state")],
                )
            return _FakeRevenueSummary("Unknown", 2024, 0, 0, 0, 0)

        civic = SimpleNamespace(
            storage=_MockStorage(bills_by_state={}),
            vectors=None,
            intergovernmental_revenue=_mock_revenue,
        )

        _mcp_request_scope.set(SCOPE_POLICIES["get_intergovernmental_revenue"])

        output = handlers.get_intergovernmental_revenue(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {},
        )

        # Both jurisdictions must be queried (exactly 2 calls).
        assert len(calls) == 2
        assert "city-san-rafael" in calls
        assert "county-marin" in calls

        # Output must contain both entities.
        assert "San Rafael" in output
        assert "Marin County" in output

        # Content must appear under the correct section.
        assert "Gas Tax" in output
        assert "Realignment" in output

        # Structural check: Gas Tax is San Rafael's, Realignment is Marin's.
        sr_idx = output.index("San Rafael")
        mc_idx = output.index("Marin County")
        if sr_idx < mc_idx:
            sr_section = output[sr_idx:mc_idx]
            mc_section = output[mc_idx:]
        else:
            mc_section = output[mc_idx:sr_idx]
            sr_section = output[sr_idx:]

        assert "Gas Tax" in sr_section
        assert "Realignment" in mc_section
        assert "Realignment" not in sr_section
        assert "Gas Tax" not in mc_section

    def test_legacy_path_without_scope_policy(self, logger, reset_scope_contextvar):
        """When no scope policy is set, the handler must fall through
        to the legacy path calling civic.intergovernmental_revenue()
        without jurisdiction_id."""
        def _mock_revenue(fiscal_year=None, source=None, **kw):
            return _FakeRevenueSummary(
                "San Rafael", 2024, 8_000_000, 171_000, 7_000_000, 829_000,
            )

        civic = SimpleNamespace(
            storage=_MockStorage(bills_by_state={}),
            vectors=None,
            intergovernmental_revenue=_mock_revenue,
        )

        # No scope set — contextvar is None from reset fixture.
        output = handlers.get_intergovernmental_revenue(
            civic,
            "city-san-rafael",
            _noop_validate,
            logger,
            {"fiscal_year": 2024},
        )

        assert "San Rafael" in output
        assert "$8,000,000" in output
