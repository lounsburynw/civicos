"""PostgreSQL storage implementations for coordination protocol."""

from datetime import datetime
from typing import Optional

from civicos_relay.voice.models import Voice, Stance
from civicos_relay.relay.models import Subscription, MatchCriteria, DeliveryConfig, DeliveryMethod
from civicos_relay.provenance.models import KeyProvenance


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
        import json
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
                        match=MatchCriteria(**json.loads(row[2])),
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
        import json
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
                        match=MatchCriteria(**json.loads(row[2])),
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
        import json
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
                        jurisdictions=json.loads(row[6]) if row[6] else [],
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
        import json
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
                        jurisdictions=json.loads(row[6]) if row[6] else [],
                    )
                    for row in cur.fetchall()
                ]
        finally:
            self._return_connection(conn)
