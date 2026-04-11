"""
Tests for the per-tool scope policy table.

The policy table in ``apps/civicos-mcp/tools/scope.py`` is the
authoritative mirror of the scope table in the ADR at
``docs/public/decisions/tool_scope_and_federation.md``. These tests
exist to catch three classes of regression:

1. Coverage — every tool actually bound by ``modal_mcp.py::_bind_handlers``
   has a ``SCOPE_POLICIES`` row.
2. Invariants — ``max_scope ≥ default_scope ≥ primary``, expandable
   scopes sit between default and max, and each scope kind obeys
   its classification rules (write-side routes to primary or
   federal, admin tools never expand, federal-only tools stay at
   federal).
3. ADR ↔ code divergence — the ADR lists the policy in markdown and
   the test exercises a spot-check against it. If the ADR gets edited
   without touching the code (or vice versa), these tests should
   flag it.

If a new tool is added to ``handler_map``, add a ``SCOPE_POLICIES``
entry and a matching ADR row — the coverage test here will fail
otherwise, and ``_bind_handlers`` will raise at server startup.
"""

import sys

import pytest

# Match the import path the server uses at runtime so ``from tools.scope``
# resolves consistently here and in modal_mcp.py.
sys.path.insert(0, "apps/civicos-mcp")

from tools.scope import (  # noqa: E402
    SCOPE_POLICIES,
    Scope,
    ScopePolicy,
    get_scope_policy,
    scope_breadth,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _handler_map_tool_names() -> set[str]:
    """
    Return the set of tool names bound in ``modal_mcp.py::_bind_handlers``.

    Parses ``handler_map`` directly instead of importing modal_mcp, which
    would pull in Modal's runtime machinery.
    """
    import ast
    import pathlib

    source = pathlib.Path("apps/civicos-mcp/modal_mcp.py").read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t for t in node.targets if isinstance(t, ast.Name)]
        if not any(t.id == "handler_map" for t in targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        names: set[str] = set()
        for key in node.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                names.add(key.value)
        if names:
            return names

    raise RuntimeError("Could not locate handler_map dict in modal_mcp.py")


READ_KINDS = {"read"}
WRITE_KINDS = {"write"}
ADMIN_KINDS = {"admin"}

PRIMARY_ONLY_SCOPES = {Scope.PRIMARY}
FEDERAL_ONLY_SCOPES = {Scope.FEDERAL}


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


class TestScopePolicyCoverage:
    """Every bound tool must declare a scope policy."""

    def test_handler_map_parses(self):
        """
        Sanity check that the parser finds handler_map and pulls the
        right keys out of it. Pins a handful of load-bearing tools from
        different sections of the map so a parser regression that silently
        drops dict keys (or grabs the wrong dict) gets caught here rather
        than cascading into the coverage test.
        """
        names = _handler_map_tool_names()
        expected_samples = {
            "search_legislation",       # cross-level read
            "get_upcoming_meetings",    # horizontal-expanding read
            "compose_public_comment",   # strict-primary write
            "broadcast_voice",          # relay write
            "admin_data_status",        # admin
            "get_issue_trends",         # late-added read (ADR-backfilled)
        }
        missing = expected_samples - names
        assert not missing, (
            f"handler_map parse is missing expected tools: {sorted(missing)}. "
            "Either the parser is broken or handler_map has drifted."
        )

    def test_every_bound_tool_has_policy(self):
        """Every tool in handler_map must have a SCOPE_POLICIES entry."""
        bound = _handler_map_tool_names()
        missing = sorted(bound - SCOPE_POLICIES.keys())
        assert not missing, (
            f"Tools bound without a scope policy: {missing}. "
            "Add rows to apps/civicos-mcp/tools/scope.py and the ADR."
        )

    def test_no_orphan_policies(self):
        """Every SCOPE_POLICIES entry must correspond to a bound tool."""
        bound = _handler_map_tool_names()
        orphans = sorted(SCOPE_POLICIES.keys() - bound)
        assert not orphans, (
            f"SCOPE_POLICIES has rows for unbound tools: {orphans}. "
            "Remove them from tools/scope.py or add them to handler_map."
        )

    def test_get_scope_policy_raises_on_unknown(self):
        """Unknown tool names must fail loudly, not return None."""
        with pytest.raises(KeyError, match="has no scope policy"):
            get_scope_policy("definitely_not_a_real_tool")


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


class TestScopePolicyInvariants:
    """Structural invariants every row must satisfy."""

    @pytest.mark.parametrize("tool_name,policy", sorted(SCOPE_POLICIES.items()))
    def test_kind_is_recognised(self, tool_name: str, policy: ScopePolicy):
        assert policy.kind in READ_KINDS | WRITE_KINDS | ADMIN_KINDS, (
            f"{tool_name}: unrecognised kind={policy.kind!r}"
        )

    @pytest.mark.parametrize("tool_name,policy", sorted(SCOPE_POLICIES.items()))
    def test_max_scope_at_least_as_broad_as_default(
        self, tool_name: str, policy: ScopePolicy
    ):
        default_rank = scope_breadth(policy.default_scope)
        max_rank = scope_breadth(policy.max_scope)
        assert max_rank >= default_rank, (
            f"{tool_name}: max_scope={policy.max_scope.name} "
            f"(rank {max_rank}) is narrower than "
            f"default_scope={policy.default_scope.name} (rank {default_rank})"
        )

    @pytest.mark.parametrize("tool_name,policy", sorted(SCOPE_POLICIES.items()))
    def test_expandable_sits_between_default_and_max(
        self, tool_name: str, policy: ScopePolicy
    ):
        if policy.expandable_scope is None:
            return
        default_rank = scope_breadth(policy.default_scope)
        expandable_rank = scope_breadth(policy.expandable_scope)
        max_rank = scope_breadth(policy.max_scope)
        assert default_rank <= expandable_rank <= max_rank, (
            f"{tool_name}: expandable_scope={policy.expandable_scope.name} "
            f"(rank {expandable_rank}) must sit between "
            f"default={policy.default_scope.name} (rank {default_rank}) "
            f"and max={policy.max_scope.name} (rank {max_rank})"
        )


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------


# Write-side exceptions that the ADR explicitly flags as "read in disguise"
# and therefore allowed to expand to siblings. All other write tools must
# be strictly primary or federal.
WRITE_SIBLING_EXEMPT = {"list_initiatives", "list_relays"}

# Write-side tools that target the federal regulations.gov portal instead
# of a local clerk/relay.
FEDERAL_WRITE_TOOLS = {"draft_federal_comment", "prepare_federal_comment"}

# Federal-only read tools per the ADR.
FEDERAL_READ_TOOLS = {
    "search_executive_orders",
    "search_federal_rules",
    "get_recent_executive_orders",
    "get_congressional_votes",
    "get_congressional_hearings",
    "get_open_comment_periods",
    "get_federal_expenditures",
    "get_bill_detail",
}


class TestWriteSideClassification:
    """Write-side tools are strictly scoped per the ADR."""

    def test_write_tools_are_strictly_primary_or_federal(self):
        """
        Non-exempt write tools must have default == max == PRIMARY,
        federal write tools must have default == max == FEDERAL, and
        sibling-exempt list_* tools are the only horizontal wideners.
        """
        offenders = []
        for name, policy in SCOPE_POLICIES.items():
            if policy.kind != "write":
                continue
            if name in WRITE_SIBLING_EXEMPT:
                if policy.default_scope != Scope.PRIMARY_PLUS_SIBLINGS:
                    offenders.append(
                        f"{name}: sibling-exempt write tool must default to "
                        f"PRIMARY_PLUS_SIBLINGS, got {policy.default_scope.name}"
                    )
                if policy.max_scope != Scope.PRIMARY_PLUS_SIBLINGS:
                    offenders.append(
                        f"{name}: sibling-exempt write tool must cap at "
                        f"PRIMARY_PLUS_SIBLINGS, got {policy.max_scope.name}"
                    )
                continue
            if name in FEDERAL_WRITE_TOOLS:
                if policy.default_scope != Scope.FEDERAL:
                    offenders.append(
                        f"{name}: federal write tool must default to FEDERAL"
                    )
                if policy.max_scope != Scope.FEDERAL:
                    offenders.append(
                        f"{name}: federal write tool must cap at FEDERAL"
                    )
                continue
            # Regular write tool: PRIMARY only.
            if policy.default_scope != Scope.PRIMARY:
                offenders.append(
                    f"{name}: write tool must default to PRIMARY, "
                    f"got {policy.default_scope.name}"
                )
            if policy.max_scope != Scope.PRIMARY:
                offenders.append(
                    f"{name}: write tool must cap at PRIMARY, "
                    f"got {policy.max_scope.name}"
                )
        assert not offenders, "Write-side classification violations:\n" + "\n".join(
            offenders
        )

    def test_write_tools_never_widen_beyond_max(self):
        """No write tool may declare an expandable scope outside its cap."""
        for name, policy in SCOPE_POLICIES.items():
            if policy.kind != "write":
                continue
            if policy.expandable_scope is None:
                continue
            assert scope_breadth(policy.expandable_scope) <= scope_breadth(
                policy.max_scope
            ), (
                f"{name}: write tool expandable_scope="
                f"{policy.expandable_scope.name} exceeds "
                f"max_scope={policy.max_scope.name}"
            )


class TestAdminClassification:
    """Admin tools must never expand beyond PRIMARY."""

    def test_admin_tools_are_primary_only(self):
        for name, policy in SCOPE_POLICIES.items():
            if policy.kind != "admin":
                continue
            assert policy.default_scope == Scope.PRIMARY, (
                f"{name}: admin tool must default to PRIMARY, "
                f"got {policy.default_scope.name}"
            )
            assert policy.max_scope == Scope.PRIMARY, (
                f"{name}: admin tool must cap at PRIMARY, "
                f"got {policy.max_scope.name}"
            )
            assert policy.expandable_scope is None, (
                f"{name}: admin tool must not declare expandable_scope"
            )


class TestFederalReadClassification:
    """Federal-only read tools stay anchored to federal."""

    def test_federal_read_tools_default_to_federal(self):
        for name in FEDERAL_READ_TOOLS:
            policy = SCOPE_POLICIES[name]
            assert policy.default_scope == Scope.FEDERAL, (
                f"{name}: federal read tool must default to FEDERAL, "
                f"got {policy.default_scope.name}"
            )
            assert policy.kind == "read"


# ---------------------------------------------------------------------------
# Spot checks against the ADR
# ---------------------------------------------------------------------------


class TestAdrSpotChecks:
    """
    A handful of rows are pinned here so a silent ADR edit that drops
    or moves them blows up loudly. These aren't exhaustive — the ADR
    file itself is the source of truth — but catching divergence on
    the four most load-bearing rows is worth a few explicit assertions.
    """

    def test_get_upcoming_meetings_horizontal_expansion(self):
        policy = SCOPE_POLICIES["get_upcoming_meetings"]
        assert policy.default_scope == Scope.PRIMARY_PLUS_SIBLINGS
        assert policy.expandable_scope == Scope.PRIMARY_PLUS_REGION
        assert policy.max_scope == Scope.REGION
        assert policy.kind == "read"

    def test_search_legislation_vertical_walk(self):
        policy = SCOPE_POLICIES["search_legislation"]
        assert policy.default_scope == Scope.PRIMARY_PLUS_ALL_PARENTS
        assert policy.max_scope == Scope.FEDERAL
        assert policy.kind == "read"

    def test_compose_public_comment_strict_primary(self):
        policy = SCOPE_POLICIES["compose_public_comment"]
        assert policy.default_scope == Scope.PRIMARY
        assert policy.max_scope == Scope.PRIMARY
        assert policy.expandable_scope is None
        assert policy.kind == "write"

    def test_list_initiatives_read_in_disguise(self):
        policy = SCOPE_POLICIES["list_initiatives"]
        assert policy.default_scope == Scope.PRIMARY_PLUS_SIBLINGS
        assert policy.max_scope == Scope.PRIMARY_PLUS_SIBLINGS
        assert policy.kind == "write"
