"""
PostgreSQL storage for Nostr events.

Implements NIP-01 compliant event storage with civic-specific optimizations:
- Addressable event replacement (kinds 30000-39999)
- Replaceable event replacement (kinds 10000-19999)
- Voice count aggregation
- Efficient tag-based queries
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from civicos_relay.nostr.models import (
    NostrEvent,
    CivicVoiceEvent,
    parse_event,
)
from civicos_relay.nostr.kinds import (
    CIVIC_VOICE,
    is_addressable,
    is_replaceable,
)


@dataclass
class VoiceCounts:
    """Aggregated voice counts for an entity."""

    entity_id: str
    jurisdiction: str | None
    support_count: int
    oppose_count: int
    watching_count: int
    total_count: int
    last_voice_at: int | None  # Unix timestamp


@dataclass
class StoredEvent:
    """Event with storage metadata."""

    event: NostrEvent
    received_at: datetime


class NostrFilter(Protocol):
    """NIP-01 filter for querying events."""

    ids: list[str] | None
    authors: list[str] | None
    kinds: list[int] | None
    since: int | None
    until: int | None
    limit: int | None
    # Tag filters: #<tag> -> list of values
    # e.g., {"#d": ["entity-id"], "#j": ["city-san-rafael"]}


@dataclass
class EventFilter:
    """Filter for querying Nostr events (NIP-01 compatible)."""

    ids: list[str] | None = None
    authors: list[str] | None = None
    kinds: list[int] | None = None
    since: int | None = None
    until: int | None = None
    limit: int | None = None
    tag_filters: dict[str, list[str]] | None = None  # {"d": ["value"], "j": ["value"]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventFilter":
        """Parse filter from NIP-01 format."""
        tag_filters = {}
        for key, value in data.items():
            if key.startswith("#") and len(key) == 2:
                tag_name = key[1]
                if isinstance(value, list):
                    tag_filters[tag_name] = value

        return cls(
            ids=data.get("ids"),
            authors=data.get("authors"),
            kinds=data.get("kinds"),
            since=data.get("since"),
            until=data.get("until"),
            limit=data.get("limit"),
            tag_filters=tag_filters if tag_filters else None,
        )


class NostrEventStorage:
    """PostgreSQL storage for Nostr events."""

    def __init__(self, connection_url: str):
        self._connection_url = connection_url
        self._pool = None

    def _get_connection(self):
        """Get database connection. Lazy initialization."""
        if self._pool is None:
            import psycopg2.pool

            self._pool = psycopg2.pool.SimpleConnectionPool(
                1, 10, self._connection_url
            )
        return self._pool.getconn()

    def _return_connection(self, conn):
        """Return connection to pool."""
        self._pool.putconn(conn)

    def save_event(self, event: NostrEvent) -> tuple[bool, str]:
        """
        Save a Nostr event.

        Handles:
        - Regular events: Always insert
        - Addressable events (30000-39999): Replace by kind:pubkey:d_tag
        - Replaceable events (10000-19999): Replace by kind:pubkey

        Returns:
            Tuple of (success, message)
            message is "accepted", "replaced", or "rejected:<reason>"
        """
        # Validate event before storing
        if not event.verify():
            return False, "rejected:invalid_signature"

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                kind = event.kind
                tags_json = json.dumps(event.tags)

                if is_addressable(kind):
                    # Addressable: replace by kind:pubkey:d_tag
                    d_tag = event.get_d_tag()
                    if d_tag is None:
                        return False, "rejected:missing_d_tag"

                    # Check if older version exists
                    cur.execute(
                        """
                        SELECT id, created_at FROM nostr_events
                        WHERE kind = %s AND pubkey = %s AND d_tag = %s
                        """,
                        (kind, event.pubkey, d_tag),
                    )
                    existing = cur.fetchone()

                    if existing:
                        existing_id, existing_created_at = existing
                        if existing_created_at >= event.created_at:
                            # Existing is newer or same age, reject
                            return False, "rejected:older_version"

                        # Delete old version
                        cur.execute(
                            "DELETE FROM nostr_events WHERE id = %s",
                            (existing_id,),
                        )

                    # Insert new version
                    cur.execute(
                        """
                        INSERT INTO nostr_events (id, pubkey, created_at, kind, tags, content, sig)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.id,
                            event.pubkey,
                            event.created_at,
                            kind,
                            tags_json,
                            event.content,
                            event.sig,
                        ),
                    )
                    conn.commit()
                    return True, "replaced" if existing else "accepted"

                elif is_replaceable(kind):
                    # Replaceable: replace by kind:pubkey
                    cur.execute(
                        """
                        SELECT id, created_at FROM nostr_events
                        WHERE kind = %s AND pubkey = %s
                        """,
                        (kind, event.pubkey),
                    )
                    existing = cur.fetchone()

                    if existing:
                        existing_id, existing_created_at = existing
                        if existing_created_at >= event.created_at:
                            return False, "rejected:older_version"

                        cur.execute(
                            "DELETE FROM nostr_events WHERE id = %s",
                            (existing_id,),
                        )

                    cur.execute(
                        """
                        INSERT INTO nostr_events (id, pubkey, created_at, kind, tags, content, sig)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.id,
                            event.pubkey,
                            event.created_at,
                            kind,
                            tags_json,
                            event.content,
                            event.sig,
                        ),
                    )
                    conn.commit()
                    return True, "replaced" if existing else "accepted"

                else:
                    # Regular event: check for duplicate, then insert
                    cur.execute(
                        "SELECT id FROM nostr_events WHERE id = %s",
                        (event.id,),
                    )
                    if cur.fetchone():
                        return False, "rejected:duplicate"

                    cur.execute(
                        """
                        INSERT INTO nostr_events (id, pubkey, created_at, kind, tags, content, sig)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.id,
                            event.pubkey,
                            event.created_at,
                            kind,
                            tags_json,
                            event.content,
                            event.sig,
                        ),
                    )
                    conn.commit()
                    return True, "accepted"

        except Exception as e:
            conn.rollback()
            return False, f"rejected:db_error:{str(e)}"
        finally:
            self._return_connection(conn)

    def get_event(self, event_id: str) -> NostrEvent | None:
        """Get event by ID."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, pubkey, created_at, kind, tags, content, sig
                    FROM nostr_events
                    WHERE id = %s
                    """,
                    (event_id,),
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_event(row)
                return None
        finally:
            self._return_connection(conn)

    def query_events(self, filter: EventFilter) -> list[NostrEvent]:
        """
        Query events matching a filter (NIP-01 compatible).

        Supports:
        - ids: List of event IDs
        - authors: List of pubkeys
        - kinds: List of kinds
        - since/until: Time range
        - limit: Max results
        - tag_filters: Tag-based filters (e.g., {"d": ["value"], "j": ["city-sr"]})
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                conditions = []
                params: list[Any] = []

                if filter.ids:
                    conditions.append("id = ANY(%s)")
                    params.append(filter.ids)

                if filter.authors:
                    conditions.append("pubkey = ANY(%s)")
                    params.append(filter.authors)

                if filter.kinds:
                    conditions.append("kind = ANY(%s)")
                    params.append(filter.kinds)

                if filter.since is not None:
                    conditions.append("created_at >= %s")
                    params.append(filter.since)

                if filter.until is not None:
                    conditions.append("created_at <= %s")
                    params.append(filter.until)

                # Handle tag filters
                if filter.tag_filters:
                    for tag_name, values in filter.tag_filters.items():
                        if tag_name == "d":
                            conditions.append("d_tag = ANY(%s)")
                            params.append(values)
                        elif tag_name == "j":
                            conditions.append("j_tag = ANY(%s)")
                            params.append(values)
                        elif tag_name == "stance":
                            conditions.append("stance = ANY(%s)")
                            params.append(values)
                        else:
                            # Generic tag query using JSONB
                            # Match any tag where first element is tag_name and second is in values
                            conditions.append(
                                """
                                EXISTS (
                                    SELECT 1 FROM jsonb_array_elements(tags) AS tag
                                    WHERE tag->>0 = %s AND tag->>1 = ANY(%s)
                                )
                                """
                            )
                            params.extend([tag_name, values])

                # Build query
                where_clause = " AND ".join(conditions) if conditions else "TRUE"
                limit_clause = f"LIMIT {filter.limit}" if filter.limit else ""

                query = f"""
                    SELECT id, pubkey, created_at, kind, tags, content, sig
                    FROM nostr_events
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    {limit_clause}
                """

                cur.execute(query, params)
                return [self._row_to_event(row) for row in cur.fetchall()]

        finally:
            self._return_connection(conn)

    def get_addressable_event(
        self, kind: int, pubkey: str, d_tag: str
    ) -> NostrEvent | None:
        """Get addressable event by kind:pubkey:d_tag."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, pubkey, created_at, kind, tags, content, sig
                    FROM nostr_events
                    WHERE kind = %s AND pubkey = %s AND d_tag = %s
                    """,
                    (kind, pubkey, d_tag),
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_event(row)
                return None
        finally:
            self._return_connection(conn)

    def delete_event(self, event_id: str, pubkey: str) -> bool:
        """
        Delete an event. Only the author can delete.

        Returns True if event was deleted.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM nostr_events
                    WHERE id = %s AND pubkey = %s
                    RETURNING id
                    """,
                    (event_id, pubkey),
                )
                conn.commit()
                return cur.fetchone() is not None
        finally:
            self._return_connection(conn)

    def get_voice_counts(self, entity_id: str) -> VoiceCounts | None:
        """Get aggregated voice counts for an entity."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT entity_id, jurisdiction, support_count, oppose_count,
                           watching_count, total_count, last_voice_at
                    FROM nostr_voice_counts
                    WHERE entity_id = %s
                    """,
                    (entity_id,),
                )
                row = cur.fetchone()
                if row:
                    return VoiceCounts(
                        entity_id=row[0],
                        jurisdiction=row[1],
                        support_count=row[2],
                        oppose_count=row[3],
                        watching_count=row[4],
                        total_count=row[5],
                        last_voice_at=row[6],
                    )
                return None
        finally:
            self._return_connection(conn)

    def refresh_voice_counts(self) -> None:
        """Refresh the voice counts materialized view."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT refresh_voice_counts()")
                conn.commit()
        finally:
            self._return_connection(conn)

    def get_voices_for_entity(self, entity_id: str) -> list[CivicVoiceEvent]:
        """Get all voices for a specific entity."""
        events = self.query_events(
            EventFilter(
                kinds=[CIVIC_VOICE],
                tag_filters={"d": [entity_id]},
            )
        )
        return [
            CivicVoiceEvent(**e.to_dict())
            for e in events
            if e.kind == CIVIC_VOICE
        ]

    def count_events(self, filter: EventFilter | None = None) -> int:
        """Count events matching a filter."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                if filter is None:
                    cur.execute("SELECT COUNT(*) FROM nostr_events")
                else:
                    conditions = []
                    params: list[Any] = []

                    if filter.kinds:
                        conditions.append("kind = ANY(%s)")
                        params.append(filter.kinds)

                    if filter.authors:
                        conditions.append("pubkey = ANY(%s)")
                        params.append(filter.authors)

                    if filter.tag_filters:
                        if "j" in filter.tag_filters:
                            conditions.append("j_tag = ANY(%s)")
                            params.append(filter.tag_filters["j"])

                    where_clause = " AND ".join(conditions) if conditions else "TRUE"
                    cur.execute(
                        f"SELECT COUNT(*) FROM nostr_events WHERE {where_clause}",
                        params,
                    )

                return cur.fetchone()[0]
        finally:
            self._return_connection(conn)

    def _row_to_event(self, row: tuple) -> NostrEvent:
        """Convert database row to NostrEvent."""
        id_, pubkey, created_at, kind, tags, content, sig = row
        # Handle tags that may already be parsed
        if isinstance(tags, str):
            tags = json.loads(tags)
        return parse_event({
            "id": id_,
            "pubkey": pubkey,
            "created_at": created_at,
            "kind": kind,
            "tags": tags,
            "content": content,
            "sig": sig,
        })


class NostrKeyLinkStorage:
    """Storage for key link attestations."""

    def __init__(self, connection_url: str):
        self._connection_url = connection_url
        self._pool = None

    def _get_connection(self):
        if self._pool is None:
            import psycopg2.pool

            self._pool = psycopg2.pool.SimpleConnectionPool(
                1, 10, self._connection_url
            )
        return self._pool.getconn()

    def _return_connection(self, conn):
        self._pool.putconn(conn)

    def save_key_link(
        self, old_key: str, new_key: str, attestation_event_id: str
    ) -> bool:
        """
        Save a key link attestation.

        Returns True if saved successfully, False if old_key already linked.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO nostr_key_links (old_key, new_key, attestation_event_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (old_key) DO NOTHING
                    RETURNING id
                    """,
                    (old_key, new_key, attestation_event_id),
                )
                conn.commit()
                return cur.fetchone() is not None
        finally:
            self._return_connection(conn)

    def get_linked_key(self, old_key: str) -> str | None:
        """Get the new Nostr key linked to an old key."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT new_key FROM nostr_key_links WHERE old_key = %s",
                    (old_key,),
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self._return_connection(conn)

    def get_old_keys(self, new_key: str) -> list[str]:
        """Get all old keys linked to a Nostr key."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT old_key FROM nostr_key_links WHERE new_key = %s",
                    (new_key,),
                )
                return [row[0] for row in cur.fetchall()]
        finally:
            self._return_connection(conn)
