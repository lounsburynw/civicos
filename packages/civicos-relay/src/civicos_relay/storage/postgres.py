"""PostgreSQL storage implementations for coordination protocol."""

import json
from datetime import datetime
from typing import Optional, Union

from civicos_relay.voice.models import Voice, Stance
from civicos_relay.relay.models import (
    Event,
    EventType,
    Subscription,
    MatchCriteria,
    DeliveryConfig,
    DeliveryMethod,
    Initiative,
    InitiativeStatus,
)
from civicos_relay.provenance.models import KeyProvenance


def _parse_jsonb(value: Union[str, dict, list, None]) -> Union[dict, list, None]:
    """Parse JSONB value that may already be deserialized by psycopg2."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


class PostgresVoiceStorage:
    """PostgreSQL storage for voices."""

    def __init__(self, connection_url: str):
        self._connection_url = connection_url
        # Connection pool initialized on first use
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

    def save_voice(self, voice: Voice) -> None:
        """Store a voice record."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO coordination_voices
                    (entity, stance, public_key, signature, timestamp, revoked)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (public_key, entity)
                    DO UPDATE SET stance = %s, signature = %s, timestamp = %s, revoked = %s
                    """,
                    (
                        voice.entity,
                        voice.stance.value,
                        voice.public_key,
                        voice.signature,
                        voice.timestamp,
                        voice.revoked,
                        voice.stance.value,
                        voice.signature,
                        voice.timestamp,
                        voice.revoked,
                    ),
                )
                conn.commit()
        finally:
            self._return_connection(conn)

    def get_voice(self, public_key: str, entity: str) -> Optional[Voice]:
        """Get existing voice for key+entity pair."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT entity, stance, public_key, signature, timestamp, revoked
                    FROM coordination_voices
                    WHERE public_key = %s AND entity = %s
                    """,
                    (public_key, entity),
                )
                row = cur.fetchone()
                if row:
                    return Voice(
                        entity=row[0],
                        stance=Stance(row[1]),
                        public_key=row[2],
                        signature=row[3],
                        timestamp=row[4],
                        revoked=row[5],
                    )
                return None
        finally:
            self._return_connection(conn)

    def get_voices_for_entity(self, entity: str) -> list[Voice]:
        """Get all voices for an entity."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT entity, stance, public_key, signature, timestamp, revoked
                    FROM coordination_voices
                    WHERE entity = %s AND revoked = FALSE
                    """,
                    (entity,),
                )
                return [
                    Voice(
                        entity=row[0],
                        stance=Stance(row[1]),
                        public_key=row[2],
                        signature=row[3],
                        timestamp=row[4],
                        revoked=row[5],
                    )
                    for row in cur.fetchall()
                ]
        finally:
            self._return_connection(conn)

    def revoke_voice(self, public_key: str, entity: str) -> bool:
        """Revoke a voice. Returns True if voice existed."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE coordination_voices
                    SET revoked = TRUE
                    WHERE public_key = %s AND entity = %s
                    RETURNING entity
                    """,
                    (public_key, entity),
                )
                conn.commit()
                return cur.fetchone() is not None
        finally:
            self._return_connection(conn)


class PostgresSubscriptionStorage:
    """PostgreSQL storage for subscriptions."""

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

    def save_subscription(self, subscription: Subscription) -> None:
        """Store a subscription."""
        import json
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO coordination_subscriptions
                    (id, jurisdiction, match_criteria, delivery_method, delivery_address,
                     created_at, active, public_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                    match_criteria = %s, delivery_method = %s, delivery_address = %s, active = %s
                    """,
                    (
                        subscription.id,
                        subscription.jurisdiction,
                        json.dumps(subscription.match.model_dump()),
                        subscription.delivery.method.value,
                        subscription.delivery.address,
                        subscription.created_at,
                        subscription.active,
                        subscription.public_key,
                        json.dumps(subscription.match.model_dump()),
                        subscription.delivery.method.value,
                        subscription.delivery.address,
                        subscription.active,
                    ),
                )
                conn.commit()
        finally:
            self._return_connection(conn)

    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Get a subscription by ID."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, jurisdiction, match_criteria, delivery_method, delivery_address,
                           created_at, active, public_key
                    FROM coordination_subscriptions
                    WHERE id = %s
                    """,
                    (subscription_id,),
                )
                row = cur.fetchone()
                if row:
                    return Subscription(
                        id=row[0],
                        jurisdiction=row[1],
                        match=MatchCriteria(**_parse_jsonb(row[2])),
                        delivery=DeliveryConfig(
                            method=DeliveryMethod(row[3]), address=row[4]
                        ),
                        created_at=row[5],
                        active=row[6],
                        public_key=row[7],
                    )
                return None
        finally:
            self._return_connection(conn)

    def get_subscriptions_for_jurisdiction(
        self, jurisdiction: str
    ) -> list[Subscription]:
        """Get all active subscriptions for a jurisdiction."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, jurisdiction, match_criteria, delivery_method, delivery_address,
                           created_at, active, public_key
                    FROM coordination_subscriptions
                    WHERE jurisdiction = %s AND active = TRUE
                    """,
                    (jurisdiction,),
                )
                return [
                    Subscription(
                        id=row[0],
                        jurisdiction=row[1],
                        match=MatchCriteria(**_parse_jsonb(row[2])),
                        delivery=DeliveryConfig(
                            method=DeliveryMethod(row[3]), address=row[4]
                        ),
                        created_at=row[5],
                        active=row[6],
                        public_key=row[7],
                    )
                    for row in cur.fetchall()
                ]
        finally:
            self._return_connection(conn)

    def deactivate_subscription(self, subscription_id: str) -> bool:
        """Deactivate a subscription. Returns True if it existed."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE coordination_subscriptions
                    SET active = FALSE
                    WHERE id = %s
                    RETURNING id
                    """,
                    (subscription_id,),
                )
                conn.commit()
                return cur.fetchone() is not None
        finally:
            self._return_connection(conn)


class PostgresProvenanceStorage:
    """PostgreSQL storage for key provenance."""

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

    def get_provenance(self, public_key: str) -> Optional[KeyProvenance]:
        """Get provenance record for a key."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT public_key, created_at, total_voices, entities_touched,
                           first_voice_at, last_voice_at, jurisdictions
                    FROM coordination_provenance
                    WHERE public_key = %s
                    """,
                    (public_key,),
                )
                row = cur.fetchone()
                if row:
                    return KeyProvenance(
                        public_key=row[0],
                        created_at=row[1],
                        total_voices=row[2],
                        entities_touched=row[3],
                        first_voice_at=row[4],
                        last_voice_at=row[5],
                        jurisdictions=_parse_jsonb(row[6]) or [],
                    )
                return None
        finally:
            self._return_connection(conn)

    def save_provenance(self, provenance: KeyProvenance) -> None:
        """Store/update a provenance record."""
        import json
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO coordination_provenance
                    (public_key, created_at, total_voices, entities_touched,
                     first_voice_at, last_voice_at, jurisdictions)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (public_key) DO UPDATE SET
                    total_voices = %s, entities_touched = %s,
                    first_voice_at = %s, last_voice_at = %s, jurisdictions = %s
                    """,
                    (
                        provenance.public_key,
                        provenance.created_at,
                        provenance.total_voices,
                        provenance.entities_touched,
                        provenance.first_voice_at,
                        provenance.last_voice_at,
                        json.dumps(provenance.jurisdictions),
                        provenance.total_voices,
                        provenance.entities_touched,
                        provenance.first_voice_at,
                        provenance.last_voice_at,
                        json.dumps(provenance.jurisdictions),
                    ),
                )
                conn.commit()
        finally:
            self._return_connection(conn)

    def get_provenance_for_entity(self, entity: str) -> list[KeyProvenance]:
        """Get provenance for all keys that voiced on an entity."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.public_key, p.created_at, p.total_voices, p.entities_touched,
                           p.first_voice_at, p.last_voice_at, p.jurisdictions
                    FROM coordination_provenance p
                    JOIN coordination_voices v ON p.public_key = v.public_key
                    WHERE v.entity = %s AND v.revoked = FALSE
                    """,
                    (entity,),
                )
                return [
                    KeyProvenance(
                        public_key=row[0],
                        created_at=row[1],
                        total_voices=row[2],
                        entities_touched=row[3],
                        first_voice_at=row[4],
                        last_voice_at=row[5],
                        jurisdictions=_parse_jsonb(row[6]) or [],
                    )
                    for row in cur.fetchall()
                ]
        finally:
            self._return_connection(conn)


class PostgresInitiativeStorage:
    """PostgreSQL storage for initiatives."""

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

    def save_initiative(self, initiative: Initiative) -> None:
        """Store an initiative."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO coordination_initiatives
                    (id, jurisdiction, topic, title, description, location,
                     public_key, signature, timestamp, status, voice_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                    status = %s, voice_count = %s
                    """,
                    (
                        initiative.id,
                        initiative.jurisdiction,
                        initiative.topic,
                        initiative.title,
                        initiative.description,
                        initiative.location,
                        initiative.public_key,
                        initiative.signature,
                        initiative.timestamp,
                        initiative.status.value,
                        initiative.voice_count,
                        initiative.status.value,
                        initiative.voice_count,
                    ),
                )
                conn.commit()
        finally:
            self._return_connection(conn)

    def get_initiative(self, initiative_id: str) -> Optional[Initiative]:
        """Get an initiative by ID."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, jurisdiction, topic, title, description, location,
                           public_key, signature, timestamp, status, voice_count
                    FROM coordination_initiatives
                    WHERE id = %s
                    """,
                    (initiative_id,),
                )
                row = cur.fetchone()
                if row:
                    return Initiative(
                        id=row[0],
                        jurisdiction=row[1],
                        topic=row[2],
                        title=row[3],
                        description=row[4],
                        location=row[5],
                        public_key=row[6],
                        signature=row[7],
                        timestamp=row[8],
                        status=InitiativeStatus(row[9]),
                        voice_count=row[10],
                    )
                return None
        finally:
            self._return_connection(conn)

    def get_initiatives_for_jurisdiction(
        self,
        jurisdiction: str,
        topic: Optional[str] = None,
        status: Optional[InitiativeStatus] = None,
        limit: int = 100,
    ) -> list[Initiative]:
        """Get initiatives for a jurisdiction with optional filters."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT id, jurisdiction, topic, title, description, location,
                           public_key, signature, timestamp, status, voice_count
                    FROM coordination_initiatives
                    WHERE jurisdiction = %s
                """
                params: list = [jurisdiction]

                if topic:
                    query += " AND topic = %s"
                    params.append(topic)

                if status:
                    query += " AND status = %s"
                    params.append(status.value)

                query += " ORDER BY voice_count DESC, timestamp DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                return [
                    Initiative(
                        id=row[0],
                        jurisdiction=row[1],
                        topic=row[2],
                        title=row[3],
                        description=row[4],
                        location=row[5],
                        public_key=row[6],
                        signature=row[7],
                        timestamp=row[8],
                        status=InitiativeStatus(row[9]),
                        voice_count=row[10],
                    )
                    for row in cur.fetchall()
                ]
        finally:
            self._return_connection(conn)

    def update_voice_count(self, initiative_id: str, count: int) -> bool:
        """Update the voice count for an initiative. Returns True if it existed."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE coordination_initiatives
                    SET voice_count = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (count, initiative_id),
                )
                conn.commit()
                return cur.fetchone() is not None
        finally:
            self._return_connection(conn)

    def update_status(
        self, initiative_id: str, status: InitiativeStatus, public_key: str
    ) -> bool:
        """Update initiative status. Only creator (matching public_key) can update."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE coordination_initiatives
                    SET status = %s
                    WHERE id = %s AND public_key = %s
                    RETURNING id
                    """,
                    (status.value, initiative_id, public_key),
                )
                conn.commit()
                return cur.fetchone() is not None
        finally:
            self._return_connection(conn)


class PostgresSyncStorage:
    """PostgreSQL storage for sync state and voice import/export."""

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

    def get_sync_cursor(self, peer_url: str) -> Optional[str]:
        """Get last sync cursor for a peer."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT cursor FROM coordination_sync_cursors
                    WHERE peer_url = %s
                    """,
                    (peer_url,),
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self._return_connection(conn)

    def set_sync_cursor(self, peer_url: str, cursor: str) -> None:
        """Update sync cursor for a peer."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO coordination_sync_cursors (peer_url, cursor, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (peer_url) DO UPDATE SET cursor = %s, updated_at = NOW()
                    """,
                    (peer_url, cursor, cursor),
                )
                conn.commit()
        finally:
            self._return_connection(conn)

    def get_voices_since(
        self, since: datetime, namespace: Optional[str], limit: int
    ) -> tuple[list[Voice], Optional[str]]:
        """Get voices for export. Returns (voices, next_cursor)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                if namespace:
                    # Filter by namespace prefix (e.g., "city-san-rafael:*" matches "city-san-rafael:decision:123")
                    namespace_prefix = namespace.rstrip("*")
                    cur.execute(
                        """
                        SELECT entity, stance, public_key, signature, timestamp, revoked
                        FROM coordination_voices
                        WHERE timestamp > %s AND entity LIKE %s
                        ORDER BY timestamp ASC
                        LIMIT %s
                        """,
                        (since, namespace_prefix + "%", limit + 1),
                    )
                else:
                    cur.execute(
                        """
                        SELECT entity, stance, public_key, signature, timestamp, revoked
                        FROM coordination_voices
                        WHERE timestamp > %s
                        ORDER BY timestamp ASC
                        LIMIT %s
                        """,
                        (since, limit + 1),
                    )

                rows = cur.fetchall()
                voices = [
                    Voice(
                        entity=row[0],
                        stance=Stance(row[1]),
                        public_key=row[2],
                        signature=row[3],
                        timestamp=row[4],
                        revoked=row[5],
                    )
                    for row in rows[:limit]
                ]

                # If we got more than limit, there's a next page
                if len(rows) > limit:
                    next_cursor = voices[-1].timestamp.isoformat()
                    return voices, next_cursor
                return voices, None
        finally:
            self._return_connection(conn)

    def import_voice(self, voice: Voice) -> str:
        """Import a voice. Returns 'accepted', 'rejected', or 'duplicate'."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Check if voice already exists
                cur.execute(
                    """
                    SELECT timestamp FROM coordination_voices
                    WHERE public_key = %s AND entity = %s
                    """,
                    (voice.public_key, voice.entity),
                )
                existing = cur.fetchone()

                if existing:
                    existing_ts = existing[0]
                    if existing_ts >= voice.timestamp:
                        return "duplicate"

                # Insert or update voice
                cur.execute(
                    """
                    INSERT INTO coordination_voices
                    (entity, stance, public_key, signature, timestamp, revoked)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (public_key, entity)
                    DO UPDATE SET stance = %s, signature = %s, timestamp = %s, revoked = %s
                    """,
                    (
                        voice.entity,
                        voice.stance.value,
                        voice.public_key,
                        voice.signature,
                        voice.timestamp,
                        voice.revoked,
                        voice.stance.value,
                        voice.signature,
                        voice.timestamp,
                        voice.revoked,
                    ),
                )
                conn.commit()
                return "accepted"
        finally:
            self._return_connection(conn)


class PostgresEventStorage:
    """PostgreSQL storage for coordination events."""

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

    def save_event(self, event: Event) -> int:
        """Store an event. Returns the event ID."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO coordination_events_log
                    (event_type, jurisdiction, entity, timestamp, data)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        event.type.value,
                        event.jurisdiction,
                        event.entity,
                        event.timestamp,
                        json.dumps(event.data),
                    ),
                )
                event_id = cur.fetchone()[0]
                conn.commit()
                return event_id
        finally:
            self._return_connection(conn)

    def update_delivery_counts(
        self, event_id: int, attempted: int, succeeded: int
    ) -> None:
        """Update delivery counts for an event."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE coordination_events_log
                    SET deliveries_attempted = %s, deliveries_succeeded = %s
                    WHERE id = %s
                    """,
                    (attempted, succeeded, event_id),
                )
                conn.commit()
        finally:
            self._return_connection(conn)

    def get_events_since(
        self, since: datetime, namespace: Optional[str], limit: int
    ) -> tuple[list[Event], Optional[str]]:
        """Get events for export. Returns (events, next_cursor)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                if namespace:
                    namespace_prefix = namespace.rstrip("*")
                    cur.execute(
                        """
                        SELECT event_type, jurisdiction, entity, timestamp, data
                        FROM coordination_events_log
                        WHERE timestamp > %s AND jurisdiction LIKE %s
                        ORDER BY timestamp ASC
                        LIMIT %s
                        """,
                        (since, namespace_prefix + "%", limit + 1),
                    )
                else:
                    cur.execute(
                        """
                        SELECT event_type, jurisdiction, entity, timestamp, data
                        FROM coordination_events_log
                        WHERE timestamp > %s
                        ORDER BY timestamp ASC
                        LIMIT %s
                        """,
                        (since, limit + 1),
                    )

                rows = cur.fetchall()
                events = [
                    Event(
                        type=EventType(row[0]),
                        jurisdiction=row[1],
                        entity=row[2],
                        timestamp=row[3],
                        data=_parse_jsonb(row[4]) or {},
                    )
                    for row in rows[:limit]
                ]

                if len(rows) > limit:
                    next_cursor = events[-1].timestamp.isoformat()
                    return events, next_cursor
                return events, None
        finally:
            self._return_connection(conn)

    def import_event(self, event: Event) -> str:
        """Import an event. Returns 'accepted', 'rejected', or 'duplicate'."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Check for duplicates based on type+entity+timestamp
                cur.execute(
                    """
                    SELECT id FROM coordination_events_log
                    WHERE event_type = %s AND entity = %s AND timestamp = %s
                    """,
                    (event.type.value, event.entity, event.timestamp),
                )
                if cur.fetchone():
                    return "duplicate"

                # Insert the event
                cur.execute(
                    """
                    INSERT INTO coordination_events_log
                    (event_type, jurisdiction, entity, timestamp, data)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        event.type.value,
                        event.jurisdiction,
                        event.entity,
                        event.timestamp,
                        json.dumps(event.data),
                    ),
                )
                conn.commit()
                return "accepted"
        finally:
            self._return_connection(conn)
