"""Attestation service — orchestrates code redemption with external signers."""

import json
import logging
from datetime import datetime, timezone

from civicos_relay.attestation.signer_client import IssuerSignerClient, SignerError
from civicos_relay.voice.crypto import verify_attestation_request, verify_attestation_proof, verify_code_batch

logger = logging.getLogger(__name__)


class AttestationService:
    """Coordinates code redemption across issuer registry, code storage, and external signers."""

    def __init__(self, attestation_storage, issuer_storage, signer_client: IssuerSignerClient | None = None):
        self._attestations = attestation_storage
        self._issuers = issuer_storage
        self._signer = signer_client or IssuerSignerClient()

    def redeem_code(
        self,
        code: str,
        subject_pubkey: str,
        signature: str,
        created_at: int,
    ) -> dict:
        """Redeem an attestation code via the code's issuer.

        Flow:
        1. Verify subject's signature (proves pubkey ownership)
        2. Look up code
        3. Check not redeemed, not expired
        4. Find issuer for this code
        5. Call issuer's /sign endpoint
        6. Verify the returned attestation
        7. Atomically redeem code + store attestation

        Returns the signed attestation event dict.
        Raises ValueError for client errors, SignerError for signer failures.
        """
        # 1. Verify pubkey ownership
        if not verify_attestation_request(subject_pubkey, signature, code, created_at):
            raise ValueError("Invalid signature — cannot prove pubkey ownership")

        # 2. Look up code
        code_record = self._attestations.get_code(code)
        if not code_record:
            raise ValueError("Code not found")

        # 3. Check not redeemed
        if code_record.get("redeemed_by") is not None:
            raise ValueError("Code already redeemed")

        # 3b. Check not expired
        expires_at = code_record.get("expires_at")
        if expires_at and expires_at < datetime.now(timezone.utc):
            raise ValueError("Code expired")

        jurisdiction = code_record["jurisdiction"]

        # 4. Find issuer
        issuer = self._issuers.get_code_issuer(code)
        if not issuer:
            raise ValueError("Code has no registered issuer")
        if not issuer.get("verified"):
            raise ValueError("Code issuer is not verified")
        if issuer.get("revoked"):
            raise ValueError("Code issuer has been revoked")

        # 5. Call external signer
        bearer_token = issuer["bearer_token"]
        attestation_event = self._signer.sign_attestation(
            signing_url=issuer["signing_url"],
            bearer_token=bearer_token,
            subject_pubkey=subject_pubkey,
            jurisdiction=jurisdiction,
            code=code,
        )

        # 6. Verify the attestation we got back
        if not verify_attestation_proof(
            attestation_event, subject_pubkey, jurisdiction, issuer["issuer_pubkey"]
        ):
            raise SignerError("Signer returned invalid attestation — verification failed")

        # 7. Atomically redeem code
        if not self._attestations.redeem_code(code, subject_pubkey):
            raise ValueError("Code already redeemed (race condition)")

        # 7b. Store attestation
        self._attestations.save_attestation({
            "id": f"attest:{jurisdiction}:{subject_pubkey}",
            "public_key": subject_pubkey,
            "jurisdiction": jurisdiction,
            "attestation_type": "physical",
            "code_used": code,
            "nostr_event": attestation_event,
        })

        logger.info(
            f"Code redeemed: {code[:8]}... by {subject_pubkey[:16]}... "
            f"via issuer {issuer['organization']}"
        )
        return attestation_event

    def accept_code_batch(self, signed_event: dict) -> dict:
        """Accept a batch of issuer-signed attestation codes.

        The signed_event is a kind-30851 Nostr event containing:
        - pubkey: issuer's public key (proves who generated these codes)
        - tags: jurisdiction, batch_id, count, optional expiry
        - content: JSON array of code strings
        - sig: Schnorr signature proving the issuer authorized these codes

        Returns: {count, batch_id, jurisdiction}
        Raises ValueError for validation failures.
        """
        # 1. Extract issuer pubkey and find their registration
        issuer_pubkey = signed_event.get("pubkey")
        if not issuer_pubkey:
            raise ValueError("Missing issuer pubkey in signed event")

        tags = signed_event.get("tags", [])
        jurisdiction = next((t[1] for t in tags if len(t) >= 2 and t[0] == "j"), None)
        if not jurisdiction:
            raise ValueError("Missing jurisdiction tag in signed event")

        issuer = self._issuers.get_issuer_by_pubkey(issuer_pubkey, jurisdiction)
        if not issuer:
            raise ValueError(f"No registered issuer with pubkey {issuer_pubkey[:16]}... for {jurisdiction}")
        if not issuer.get("verified"):
            raise ValueError("Issuer is not verified")
        if issuer.get("revoked"):
            raise ValueError("Issuer has been revoked")

        # 2. Verify the signature (proves this issuer actually generated these codes)
        if not verify_code_batch(signed_event, issuer_pubkey):
            raise ValueError("Invalid signature on code batch event")

        # 3. Extract codes and metadata from verified event
        try:
            codes = json.loads(signed_event["content"])
        except (json.JSONDecodeError, KeyError):
            raise ValueError("Invalid code list in event content")

        if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
            raise ValueError("Content must be a JSON array of code strings")

        batch_id = next((t[1] for t in tags if len(t) >= 2 and t[0] == "batch"), None)
        if not batch_id:
            raise ValueError("Missing batch tag in signed event")

        expires_at = next((t[1] for t in tags if len(t) >= 2 and t[0] == "expires"), None)

        # 4. Store codes linked to this issuer
        added = self._attestations.add_codes_batch(
            codes=codes,
            jurisdiction=jurisdiction,
            batch_id=batch_id,
            issuer_id=issuer["issuer_id"],
            expires_at=expires_at,
        )

        logger.info(
            f"Code batch accepted: {added}/{len(codes)} codes for {jurisdiction} "
            f"(batch: {batch_id}) from issuer {issuer['organization']}"
        )

        return {
            "count": added,
            "total_submitted": len(codes),
            "batch_id": batch_id,
            "jurisdiction": jurisdiction,
            "issuer_id": issuer["issuer_id"],
        }

    def register_issuer(self, registration: dict) -> dict:
        """Register a new issuer with the relay.

        Args:
            registration: {issuer_pubkey, jurisdiction, organization,
                          signing_url, bearer_token, allowed_types}

        Returns: {issuer_id, status}
        """
        jurisdiction = registration["jurisdiction"]
        organization = registration["organization"]
        issuer_pubkey = registration["issuer_pubkey"]

        # Validate pubkey format
        if len(issuer_pubkey) != 64:
            raise ValueError("Invalid issuer pubkey length (must be 64 hex chars)")
        try:
            bytes.fromhex(issuer_pubkey)
        except ValueError:
            raise ValueError("Invalid issuer pubkey hex encoding")

        # Check for duplicate
        existing = self._issuers.get_issuer_by_pubkey(issuer_pubkey, jurisdiction)
        if existing and not existing.get("revoked"):
            raise ValueError(
                f"Issuer already registered for {jurisdiction}: {existing['issuer_id']}"
            )

        # Generate issuer_id
        org_slug = organization.lower().replace(" ", "-").replace("_", "-")
        issuer_id = f"issuer:{jurisdiction}:{org_slug}"

        issuer_record = {
            "issuer_id": issuer_id,
            "jurisdiction": jurisdiction,
            "issuer_pubkey": issuer_pubkey,
            "organization": organization,
            "signing_url": registration["signing_url"],
            "bearer_token": registration["bearer_token"],
            "allowed_types": registration.get("allowed_types", ["physical"]),
            "verified": False,
        }

        self._issuers.register_issuer(issuer_record)

        logger.info(
            f"Issuer registered: {issuer_id} ({organization}) "
            f"for {jurisdiction} — pending verification"
        )
        return {
            "issuer_id": issuer_id,
            "status": "pending_verification",
            "organization": organization,
            "jurisdiction": jurisdiction,
        }

    def list_issuers(self, jurisdiction: str) -> list[dict]:
        """List all non-revoked issuers for a jurisdiction."""
        issuers = self._issuers.get_issuers_for_jurisdiction(jurisdiction)
        # Strip sensitive fields (bearer_token)
        safe_keys = {
            "issuer_id", "jurisdiction", "issuer_pubkey", "organization",
            "signing_url", "allowed_types", "verified",
        }
        return [{k: v for k, v in i.items() if k in safe_keys} for i in issuers]

    def verify_issuer(self, issuer_id: str) -> bool:
        """Admin: mark issuer as verified."""
        return self._issuers.verify_issuer(issuer_id)

    def revoke_issuer(self, issuer_id: str) -> bool:
        """Admin: revoke an issuer."""
        return self._issuers.revoke_issuer(issuer_id)
