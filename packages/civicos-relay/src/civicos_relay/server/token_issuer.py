"""Token issuance service for privacy-preserving blind signature tokens.

Implements the issuer side of the Schnorr blind signature protocol:
  1. User requests a nonce session → issuer returns (session_id, R)
  2. User sends blinded challenge → issuer returns blind signature, session consumed

The issuer holds a private key separate from the relay's identity key.
This separation is the privacy boundary: the issuer sees payment identity
but cannot link tokens to relay writes.

Wagner's attack mitigation: concurrent signing sessions are capped at
max_concurrent_sessions (default 5). Each session is single-use and expires
after session_ttl_seconds.
"""

import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from coincurve import PrivateKey

from civicos_relay.voice.blind import (
    generate_nonce,
    sign_blinded,
)

logger = logging.getLogger(__name__)


class TooManyConcurrentSessions(Exception):
    """Raised when the concurrent session limit is reached (Wagner's attack mitigation)."""


class InvalidSession(Exception):
    """Raised when a session ID is unknown or expired."""


@dataclass
class _NonceSession:
    """Internal state for an active signing session."""

    nonce_secret: bytes  # 32-byte scalar k
    nonce_point: bytes  # 33-byte compressed R = k·G
    created_at: float


class TokenIssuer:
    """Issues blind signature tokens using the Schnorr blind signing protocol.

    Usage:
        issuer = TokenIssuer(issuer_secret=secret_bytes)

        # Step 1: user requests nonce
        session_id, nonce_point = issuer.create_nonce_session()

        # Step 2: user blinds message with nonce_point, sends blinded challenge
        blind_sig = issuer.sign(session_id, blinded_challenge)

        # User unblinds locally → SpendableToken
    """

    def __init__(
        self,
        issuer_secret: bytes,
        max_concurrent_sessions: int = 5,
        session_ttl_seconds: float = 300.0,
    ):
        """Initialize the token issuer.

        Args:
            issuer_secret: 32-byte private key for the issuer identity.
            max_concurrent_sessions: Max active nonce sessions at once.
                Limits Wagner's attack surface. Default 5.
            session_ttl_seconds: Seconds before an unused session expires.
                Default 300 (5 minutes).
        """
        self._secret = issuer_secret
        self._private_key = PrivateKey(issuer_secret)
        self._pubkey = self._private_key.public_key.format(compressed=True)
        self._max_concurrent = max_concurrent_sessions
        self._session_ttl = session_ttl_seconds
        self._sessions: dict[str, _NonceSession] = {}

    @property
    def public_key(self) -> bytes:
        """Issuer's compressed public key (33 bytes)."""
        return self._pubkey

    @property
    def public_key_hex(self) -> str:
        """Issuer's compressed public key as hex string."""
        return self._pubkey.hex()

    @property
    def active_session_count(self) -> int:
        """Number of currently active (non-expired) signing sessions."""
        self._cleanup_expired()
        return len(self._sessions)

    def create_nonce_session(self) -> tuple[str, bytes]:
        """Start a new signing session by generating a nonce.

        Returns:
            (session_id, nonce_point): The session_id is an opaque handle
            the user must present when calling sign(). The nonce_point R
            (33 bytes compressed) is used by the user to blind their message.

        Raises:
            TooManyConcurrentSessions: If the concurrent session limit is
                reached. The caller should retry after a session completes
                or expires.
        """
        self._cleanup_expired()

        if len(self._sessions) >= self._max_concurrent:
            raise TooManyConcurrentSessions(
                f"Max {self._max_concurrent} concurrent sessions reached. "
                f"Wait for an existing session to complete or expire."
            )

        nonce_secret, nonce_point = generate_nonce()
        session_id = secrets.token_hex(16)

        self._sessions[session_id] = _NonceSession(
            nonce_secret=nonce_secret,
            nonce_point=nonce_point,
            created_at=time.monotonic(),
        )

        logger.debug(
            "Created nonce session %s (%d/%d active)",
            session_id[:8],
            len(self._sessions),
            self._max_concurrent,
        )

        return session_id, nonce_point

    def sign(self, session_id: str, blinded_challenge: bytes) -> bytes:
        """Sign a blinded challenge, consuming the session.

        Each session is single-use: calling sign() removes the session
        regardless of success. This prevents nonce reuse.

        Args:
            session_id: Handle from create_nonce_session().
            blinded_challenge: 32-byte blinded challenge from the user.

        Returns:
            32-byte blind signature scalar.

        Raises:
            InvalidSession: If the session_id is unknown or expired.
        """
        self._cleanup_expired()

        session = self._sessions.pop(session_id, None)
        if session is None:
            raise InvalidSession(
                f"Session {session_id[:8]}... not found or expired"
            )

        blind_sig = sign_blinded(
            blinded_challenge, self._secret, session.nonce_secret
        )

        logger.debug(
            "Signed blinded challenge for session %s (%d sessions remaining)",
            session_id[:8],
            len(self._sessions),
        )

        return blind_sig

    def issue_token_batch(
        self, count: int
    ) -> list[tuple[str, bytes]]:
        """Create multiple nonce sessions at once for batch issuance.

        Convenience method for issuing token packages (e.g., 10, 50, 100).
        Each session still requires a separate sign() call.

        Args:
            count: Number of nonce sessions to create.

        Returns:
            List of (session_id, nonce_point) tuples.

        Raises:
            TooManyConcurrentSessions: If adding count sessions would
                exceed the concurrent limit.
        """
        self._cleanup_expired()

        if len(self._sessions) + count > self._max_concurrent:
            available = self._max_concurrent - len(self._sessions)
            raise TooManyConcurrentSessions(
                f"Cannot create {count} sessions: "
                f"{available} of {self._max_concurrent} slots available"
            )

        sessions = []
        for _ in range(count):
            session_id, nonce_point = self.create_nonce_session()
            sessions.append((session_id, nonce_point))

        return sessions

    def _cleanup_expired(self) -> None:
        """Remove sessions that have exceeded the TTL."""
        now = time.monotonic()
        expired = [
            sid
            for sid, session in self._sessions.items()
            if now - session.created_at > self._session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
            logger.debug("Expired nonce session %s", sid[:8])
