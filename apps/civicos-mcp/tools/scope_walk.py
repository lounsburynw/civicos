"""
Resolve a scope policy to a list of jurisdictions and fan a storage
call out across them, stamping each returned row with the jurisdiction
it came from.

This is the consumer side of the scope work sequence. The policy
table in ``tools/scope.py`` declares *what* each MCP tool's scope
should be; this module turns that declaration into the concrete
list of jurisdictions to query and the labeled union of results.

The goal is twofold:

1. Tool handlers that want to walk parents/siblings can do so without
   open-coding the registry lookup each time.
2. Every row returned to an AI caller carries a ``jurisdiction`` field
   so the caller can tell which government level produced it
   ("San Rafael said X, Marin County said Y, California said Z").

Region scopes (``PRIMARY_PLUS_REGION`` / ``REGION``) ship in step 3
of the scope work sequence (``region_config_concept``). Until then,
this module raises ``NotImplementedError`` if a tool's policy
evaluates to one of them. The binding assertion in ``modal_mcp.py``
does not prevent a policy from declaring a region default today
(none currently do), so the guard here is defensive.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from tools.scope import Scope, ScopePolicy

logger = logging.getLogger(__name__)


# Cap on how many jurisdictions a single scope walk is allowed to
# expand to. Sibling expansion on a county parent can easily hit
# double digits (Marin alone has 11 cities); this is a belt-and-
# suspenders limit so a misconfigured policy can't fan out to every
# registered jurisdiction.
MAX_SCOPE_FANOUT = 25


def _load_registry_entries() -> Dict[str, Dict[str, Any]]:
    """
    Return ``registry.json``'s ``jurisdictions`` dict, or an empty
    dict if the registry can't be loaded.

    Uses ``civicos.registry.get_registry`` — the public API — so
    this module and downstream callers see the same cached parse
    of ``config/registry.json``. If loading fails the walker
    degrades to primary-only behavior (safer than raising and
    taking the tool offline).
    """
    try:
        from civicos.registry import get_registry
        registry = get_registry()
    except Exception:  # pragma: no cover - defensive, exercised via test
        logger.warning("scope_walk: could not load registry.json")
        return {}
    return registry.get("jurisdictions", {}) or {}


def resolve_scope_to_jurisdictions(
    scope: Scope,
    primary_jurisdiction: str,
) -> List[str]:
    """
    Expand a ``Scope`` enum value into the concrete list of
    jurisdiction IDs the tool should query.

    The returned list always has ``primary_jurisdiction`` as its
    first element when the scope includes the primary (every scope
    except ``STATE`` and ``FEDERAL``, which snap up to a specific
    level). The list is deduplicated in-order.

    Raises:
        NotImplementedError: For ``PRIMARY_PLUS_REGION`` / ``REGION``.
            Region config lands in step 3 (``region_config_concept``).
    """
    if scope in (Scope.PRIMARY_PLUS_REGION, Scope.REGION):
        raise NotImplementedError(
            f"Scope {scope.value} requires region config "
            "(ships in step 3: region_config_concept)"
        )

    entries = _load_registry_entries()
    entry = entries.get(primary_jurisdiction, {}) or {}
    parents: List[str] = list(entry.get("parent_jurisdictions", []) or [])

    if scope == Scope.PRIMARY:
        return [primary_jurisdiction]

    if scope == Scope.PRIMARY_PLUS_PARENT:
        # Direct parent only — first entry in the parent chain.
        if parents:
            return _dedupe([primary_jurisdiction, parents[0]])
        return [primary_jurisdiction]

    if scope == Scope.PRIMARY_PLUS_ALL_PARENTS:
        return _dedupe([primary_jurisdiction, *parents])

    if scope == Scope.PRIMARY_PLUS_SIBLINGS:
        # Cities that share a common county parent with the primary.
        siblings = _find_siblings(primary_jurisdiction, parents, entries)
        return _dedupe([primary_jurisdiction, *siblings])

    if scope == Scope.STATE:
        # Snap to the state-level ancestor. If the primary has no
        # state parent (e.g. state-california itself), return it.
        for p in parents:
            if p.startswith("state-"):
                return [p]
        if primary_jurisdiction.startswith("state-"):
            return [primary_jurisdiction]
        return [primary_jurisdiction]  # no state ancestor — degrade gracefully

    if scope == Scope.FEDERAL:
        return ["country-united-states"]

    raise ValueError(f"Unhandled scope: {scope!r}")  # pragma: no cover


def _find_siblings(
    primary: str,
    parents: List[str],
    entries: Dict[str, Dict[str, Any]],
) -> List[str]:
    """Jurisdictions that share any county parent with ``primary``."""
    county_parents = {p for p in parents if p.startswith("county-")}
    if not county_parents:
        return []

    siblings: List[str] = []
    for jid, entry in entries.items():
        if jid == primary:
            continue
        other_parents = entry.get("parent_jurisdictions", []) or []
        if any(p in county_parents for p in other_parents):
            siblings.append(jid)
    return siblings


def _dedupe(items: List[str]) -> List[str]:
    """Deduplicate a list preserving first-occurrence order."""
    seen: set = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def walk_scope(
    policy: Optional[ScopePolicy],
    primary_jurisdiction: str,
    storage_call: Callable[[str], List[Dict[str, Any]]],
    *,
    label_key: str = "jurisdiction",
) -> List[Dict[str, Any]]:
    """
    Fan a storage call out across the jurisdictions resolved from
    ``policy.default_scope`` and stamp each returned row with the
    jurisdiction it came from.

    Args:
        policy: The tool's scope policy. If ``None`` (e.g. the
            contextvar was never set), walk falls back to primary-
            only — safer than raising in production.
        primary_jurisdiction: The server's primary jurisdiction ID
            (e.g. ``"city-san-rafael"``).
        storage_call: Closure that takes a jurisdiction ID and
            returns a list of row dicts. The closure is responsible
            for any per-jurisdiction filtering, state-code mapping,
            or early-out for jurisdictions that don't hold the
            relevant data (e.g. cities don't hold state legislation).
        label_key: The dict key to stamp with the source
            jurisdiction. Defaults to ``"jurisdiction"``. Existing
            values under this key are preserved (the walker does not
            overwrite them).

    Returns:
        Deduplicated list of result dicts (order preserved).
        Each row has ``label_key`` set to its source jurisdiction.

    Raises:
        NotImplementedError: If the resolved scope requires region
            config (see ``resolve_scope_to_jurisdictions``).
    """
    scope = policy.default_scope if policy else Scope.PRIMARY
    targets = resolve_scope_to_jurisdictions(scope, primary_jurisdiction)

    if len(targets) > MAX_SCOPE_FANOUT:
        logger.warning(
            "scope_walk: fanout capped at %d for %s (scope=%s, resolved=%d)",
            MAX_SCOPE_FANOUT,
            primary_jurisdiction,
            scope.value,
            len(targets),
        )
        targets = targets[:MAX_SCOPE_FANOUT]

    results: List[Dict[str, Any]] = []
    for jid in targets:
        try:
            rows = storage_call(jid) or []
        except Exception as e:
            # One failing jurisdiction shouldn't poison the whole walk.
            # Log and continue — the caller will still see results from
            # the other jurisdictions and can detect a gap via the
            # jurisdiction labels.
            logger.warning(
                "scope_walk: storage_call failed for %s: %s", jid, e
            )
            continue

        for row in rows:
            if not isinstance(row, dict):
                # Defensive: the walker is typed for dict rows but a
                # handler may pass objects. Skip silently rather than
                # crash — the handler's own typing will catch it.
                continue
            if label_key not in row:
                row[label_key] = jid
            results.append(row)

    return results
