"""
Per-tool scope policy for the CivicOS MCP server.

This module is the authoritative starting point for how each MCP tool
walks the vertical (city → county → state → federal) and horizontal
(siblings / regions) axes when it runs. Every tool bound in the server
must have an entry here; the binding path asserts coverage at startup.

The policy table mirrors the scope table in
``docs/public/decisions/tool_scope_and_federation.md`` row-for-row.
If a policy changes, update the ADR and this file together.

Runtime integration: ``modal_mcp.py::_wrap_handler`` resolves each
tool call's policy from ``SCOPE_POLICIES`` and publishes it on the
``_mcp_request_scope`` contextvar declared at the bottom of this
file. Tool handlers read that contextvar and call
``tools.scope_walk.walk_scope`` (or
``resolve_scope_to_jurisdictions`` for shallower integrations) to
fan storage queries across the resolved jurisdictions and return
results labeled by source jurisdiction. The contextvar lives here —
alongside the policy types — so that producer (modal_mcp.py) and
consumers (tools/handlers.py) share one binding without importing
each other.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional


class Scope(Enum):
    """
    Named scopes that tools can declare in their policy.

    Horizontal (siblings, region) and vertical (parent chain, state,
    federal) axes are orthogonal, so this enum is not a total order
    — use ``scope_breadth`` when a rank comparison is needed (e.g.
    for the ``max_scope ≥ default_scope`` invariant check).
    """

    # Strict: only the server's primary jurisdiction.
    PRIMARY = "primary"

    # Vertical walk of one step (city + direct parent county, etc.).
    PRIMARY_PLUS_PARENT = "primary_plus_parent"

    # Horizontal walk across siblings sharing a common parent.
    PRIMARY_PLUS_SIBLINGS = "primary_plus_siblings"

    # Full vertical walk up the government hierarchy.
    PRIMARY_PLUS_ALL_PARENTS = "primary_plus_all_parents"

    # Primary + an explicit region (see config/registry.json regions key).
    PRIMARY_PLUS_REGION = "primary_plus_region"

    # The full region as a first-class scope (e.g. bay-area, marin).
    REGION = "region"

    # State-level ceiling.
    STATE = "state"

    # Federal-level ceiling.
    FEDERAL = "federal"


# Breadth ranks used by the ``max_scope >= default_scope`` invariant.
# Higher rank = more inclusive. Ties are allowed: parent-chain and
# sibling expansion are different axes but roughly equivalent in
# "how much data could this return" terms, and the test only needs
# a partial linearisation for sanity checking.
_SCOPE_BREADTH: dict[Scope, int] = {
    Scope.PRIMARY: 1,
    Scope.PRIMARY_PLUS_PARENT: 2,
    Scope.PRIMARY_PLUS_SIBLINGS: 2,
    Scope.PRIMARY_PLUS_ALL_PARENTS: 3,
    Scope.PRIMARY_PLUS_REGION: 3,
    Scope.REGION: 4,
    Scope.STATE: 4,
    Scope.FEDERAL: 5,
}


def scope_breadth(scope: Scope) -> int:
    """Return the breadth rank of a scope (1 = primary, 5 = federal)."""
    return _SCOPE_BREADTH[scope]


ScopeKind = Literal["read", "write", "admin"]


@dataclass(frozen=True)
class ScopePolicy:
    """
    Per-tool scope policy.

    ``default_scope`` runs when the caller passes no scope parameter.
    ``expandable_scope`` is the total scope the caller can opt in to
    (``None`` means the tool refuses widening). ``max_scope`` is the
    ceiling beyond which the tool refuses regardless of caller intent.
    ``kind`` drives the read/write/admin federation boundary.
    """

    default_scope: Scope
    expandable_scope: Scope | None
    max_scope: Scope
    kind: ScopeKind
    notes: str = ""


# ---------------------------------------------------------------------------
# Read-side tools
#
# Read-side tools expand scope along the vertical and horizontal axes with
# results labeled by source jurisdiction. See ADR section "Read-side tools".
# ---------------------------------------------------------------------------

_READ_POLICIES: dict[str, ScopePolicy] = {
    "get_upcoming_meetings": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_SIBLINGS,
        expandable_scope=Scope.PRIMARY_PLUS_REGION,
        max_scope=Scope.REGION,
        kind="read",
        notes="Regional view is the user's natural question",
    ),
    "search_meeting_history": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="History is jurisdiction-specific; cross-pollinating is noise",
    ),
    "search_legislation": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_ALL_PARENTS,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Local + county + state + federal all affect the caller",
    ),
    "search_executive_orders": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Always federal",
    ),
    "search_federal_rules": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Always federal",
    ),
    "get_recent_executive_orders": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Always federal",
    ),
    "get_congressional_votes": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Always federal",
    ),
    "get_congressional_hearings": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Always federal",
    ),
    "get_open_comment_periods": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Federal regulatory comment periods",
    ),
    "search_regulatory_stack": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_ALL_PARENTS,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Stack means: municipal + county + state + federal code",
    ),
    "search_agenda_packets": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Packets are meeting-scoped",
    ),
    "get_public_testimony": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Testimony is attached to specific meetings",
    ),
    "search_budget": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Budgets don't compose across levels",
    ),
    "get_funding_flow": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_PARENT,
        expandable_scope=Scope.PRIMARY_PLUS_ALL_PARENTS,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Intergov transfers are inherently cross-level",
    ),
    "get_federal_expenditures": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Always federal",
    ),
    "get_intergovernmental_revenue": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_PARENT,
        expandable_scope=None,
        max_scope=Scope.STATE,
        kind="read",
        notes="Revenue flows from parents",
    ),
    "query_issue_data": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="311 is scoped to the responding jurisdiction",
    ),
    "get_issue_analytics": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Analytics don't aggregate meaningfully across jurisdictions",
    ),
    "get_issue_trends": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Trend timeseries tied to one 311 system",
    ),
    "geo_search_issues": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Geographic search bounded to one jurisdiction",
    ),
    "get_issue_resolution_stats": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Resolution is by local crews",
    ),
    "detect_trends": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Trend detection is jurisdiction-specific",
    ),
    "get_issue_sample": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Sampling from one jurisdiction",
    ),
    "find_issues_near_address": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Address geocoded to one jurisdiction",
    ),
    "find_repeat_issues": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Repeats only meaningful within one 311 system",
    ),
    "get_seasonal_patterns": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Jurisdiction-specific climate/usage patterns",
    ),
    "compare_zip_codes": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Within-jurisdiction ZIP comparison",
    ),
    "neighborhood_report": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Single-jurisdiction neighborhood summary",
    ),
    "find_similar_issues": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_SIBLINGS,
        expandable_scope=Scope.PRIMARY_PLUS_REGION,
        max_scope=Scope.REGION,
        kind="read",
        notes="'Has Mill Valley dealt with this?' is a real query",
    ),
    "city_pulse": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Health snapshot of one city",
    ),
    "get_voting_record": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Local councilmembers; Congress has its own tool",
    ),
    "get_decision_context": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Context for a specific decision",
    ),
    "decision_detail": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Detail for a specific decision",
    ),
    "get_item_context": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="read",
        notes="Assembled context for one item",
    ),
    "get_leverage_points": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_ALL_PARENTS,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes=(
            "Leverage points live wherever a bill is legislated — state "
            "and federal both count. Matches search_legislation scope; "
            "narrower scopes degenerate to empty because cities/counties "
            "do not hold legislation rows."
        ),
    ),
    "get_bill_detail": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Bill detail (federal congress); state/local have their own",
    ),
    "get_started": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_ALL_PARENTS,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="read",
        notes="Onboarding overview should show the full stack",
    ),
}


# ---------------------------------------------------------------------------
# Write-side tools
#
# Write-side tools are strictly scoped to the primary jurisdiction of the
# server they run on. The two exceptions are ``list_initiatives`` and
# ``list_relays``, which are reads in disguise (safe to expand to siblings),
# and the two federal comment tools, which route to regulations.gov.
# See ADR section "Write-side tools".
# ---------------------------------------------------------------------------

_WRITE_POLICIES: dict[str, ScopePolicy] = {
    "compose_public_comment": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Comments route to a specific clerk/portal",
    ),
    "get_comment_guidelines": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Guidelines are jurisdiction-specific",
    ),
    "get_comment_template": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Templates are jurisdiction-specific",
    ),
    "prepare_for_meeting": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Meeting prep targets a specific agenda",
    ),
    "prepare_voice": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Voices are signed for a specific jurisdiction's relay",
    ),
    "broadcast_voice": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Broadcast routes to the authoritative relay",
    ),
    "prepare_initiative": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Initiatives are jurisdiction-scoped",
    ),
    "broadcast_initiative": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Initiatives routed to the authoritative relay",
    ),
    "list_initiatives": ScopePolicy(
        default_scope=Scope.PRIMARY_PLUS_SIBLINGS,
        expandable_scope=None,
        max_scope=Scope.PRIMARY_PLUS_SIBLINGS,
        kind="write",
        notes="Read operation in disguise — safe to expand",
    ),
    "list_relays": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes=(
            "Relays are not jurisdictional — the handler returns the "
            "same static KNOWN_RELAYS list regardless of scope. Declared "
            "as PRIMARY to reflect reality; fan-out would be a no-op."
        ),
    ),
    "get_voice_counts": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Counts are per-jurisdiction",
    ),
    "subscribe_to_topic": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="write",
        notes="Subscription routes to specific relay",
    ),
    "draft_federal_comment": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="write",
        notes="Routes to regulations.gov, not a local portal",
    ),
    "prepare_federal_comment": ScopePolicy(
        default_scope=Scope.FEDERAL,
        expandable_scope=None,
        max_scope=Scope.FEDERAL,
        kind="write",
        notes="Federal comment preparation",
    ),
}


# ---------------------------------------------------------------------------
# Admin tools
#
# Admin tools are strictly scoped to primary — an operator of the
# San Rafael instance cannot inspect another operator's state through
# their own admin surface.
# ---------------------------------------------------------------------------

_ADMIN_POLICIES: dict[str, ScopePolicy] = {
    "admin_data_status": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="admin",
        notes="Server operator sees their own data",
    ),
    "admin_vector_coverage": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="admin",
        notes="Server operator sees their own indexing",
    ),
    "admin_system_health": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="admin",
        notes="Server health",
    ),
    "admin_cost_dashboard": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="admin",
        notes="Operator cost view",
    ),
    "manage_api_keys": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="admin",
        notes="Operator key management",
    ),
    "query_feedback": ScopePolicy(
        default_scope=Scope.PRIMARY,
        expandable_scope=None,
        max_scope=Scope.PRIMARY,
        kind="admin",
        notes="Operator feedback review",
    ),
}


# ---------------------------------------------------------------------------
# Authoritative table
# ---------------------------------------------------------------------------

SCOPE_POLICIES: dict[str, ScopePolicy] = {
    **_READ_POLICIES,
    **_WRITE_POLICIES,
    **_ADMIN_POLICIES,
}


def get_scope_policy(tool_name: str) -> ScopePolicy:
    """
    Look up the scope policy for a tool by name.

    Raises ``KeyError`` with a clear message if the tool has no policy
    row. New tools must declare their scope before they are bound —
    ``_bind_handlers`` enforces this at server startup.
    """
    try:
        return SCOPE_POLICIES[tool_name]
    except KeyError as exc:
        raise KeyError(
            f"Tool '{tool_name}' has no scope policy. "
            f"Add a ScopePolicy entry in apps/civicos-mcp/tools/scope.py "
            f"and a matching row in docs/public/decisions/tool_scope_and_federation.md "
            f"before binding this tool."
        ) from exc


# ---------------------------------------------------------------------------
# Request-scoped context
# ---------------------------------------------------------------------------

# Contextvar holding the resolved ScopePolicy for the in-flight tool
# call. ``modal_mcp.py::_wrap_handler`` sets this from SCOPE_POLICIES
# before dispatching to the handler; tool handlers read it via
# ``_mcp_request_scope.get()`` to decide whether to walk parents/
# siblings. Default is ``None`` so handlers degrade to primary-only
# behavior when invoked outside the MCP request path (direct calls,
# unit tests).
#
# This lives here — alongside the policy types — so that both
# modal_mcp.py (the producer) and tools/handlers.py (the consumers)
# can import it without creating a cycle between them.
_mcp_request_scope: contextvars.ContextVar[Optional[ScopePolicy]] = (
    contextvars.ContextVar("_mcp_request_scope", default=None)
)
