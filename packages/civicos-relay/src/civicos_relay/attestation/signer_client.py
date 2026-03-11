"""HTTP client for calling external issuer signer services."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class SignerError(Exception):
    """Error communicating with an issuer's signer service."""


class IssuerSignerClient:
    """Call an external organization's /sign endpoint to produce attestations."""

    def __init__(self, timeout: float = 5.0):
        self._timeout = timeout

    def sign_attestation(
        self,
        signing_url: str,
        bearer_token: str,
        subject_pubkey: str,
        jurisdiction: str,
        code: str,
        attestation_type: str = "physical",
    ) -> dict:
        """Call an issuer's /sign endpoint. Returns the signed attestation event dict.

        Raises SignerError on any failure (network, auth, validation).
        """
        url = f"{signing_url.rstrip('/')}/sign"
        payload = {
            "subject_pubkey": subject_pubkey,
            "jurisdiction": jurisdiction,
            "attestation_type": attestation_type,
            "code": code,
            "relay_timestamp": int(time.time()),
        }

        try:
            resp = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {bearer_token}"},
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            logger.error(f"Signer timeout: {signing_url}")
            raise SignerError(f"Signer at {signing_url} timed out")
        except httpx.ConnectError:
            logger.error(f"Signer unreachable: {signing_url}")
            raise SignerError(f"Signer at {signing_url} unreachable")

        if resp.status_code == 401:
            raise SignerError("Bearer token rejected by signer")
        if resp.status_code != 200:
            raise SignerError(
                f"Signer returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        event = data.get("attestation_event")
        if not event or not isinstance(event, dict):
            raise SignerError("Signer response missing attestation_event")

        # Basic structure validation
        required = {"id", "pubkey", "created_at", "kind", "tags", "content", "sig"}
        missing = required - set(event.keys())
        if missing:
            raise SignerError(f"Attestation event missing fields: {missing}")

        if event.get("kind") != 30850:
            raise SignerError(f"Unexpected kind: {event.get('kind')}")

        logger.info(
            f"Got attestation from {signing_url} for {subject_pubkey[:16]}..."
        )
        return event

    def check_health(self, signing_url: str) -> dict | None:
        """Call /health to verify a signer is reachable. Returns health dict or None."""
        url = f"{signing_url.rstrip('/')}/health"
        try:
            resp = httpx.get(url, timeout=self._timeout)
            if resp.status_code == 200:
                return resp.json()
        except (httpx.HTTPError, Exception):
            pass
        return None
