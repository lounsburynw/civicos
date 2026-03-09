"""Tests for multi-issuer attestation: registry, code redemption, and signer integration."""

import time
from unittest.mock import MagicMock, patch

import pytest

from civicos_relay.storage.memory import InMemoryStorage
from civicos_relay.attestation.service import AttestationService
from civicos_relay.attestation.signer_client import IssuerSignerClient, SignerError
from civicos_relay.voice.crypto import KeyPair, _compute_nostr_event_id


# --- Fixtures ---


def _sign_attestation_request(keypair: KeyPair, code: str) -> tuple[str, int]:
    """Create a kind-24242 signature proving pubkey ownership for code redemption."""
    from coincurve import PrivateKey

    created_at = int(time.time())
    tags = [["action", "attest"], ["code", code]]
    content = f"civicos:attest:v1:{keypair.public_key_hex}:{code}:{created_at}"
    event_id = _compute_nostr_event_id(keypair.public_key_hex, created_at, 24242, tags, content)

    pk = PrivateKey(bytes.fromhex(keypair.private_key_hex))
    sig = pk.sign_schnorr(bytes.fromhex(event_id))
    return sig.hex(), created_at


def _make_attestation_event(issuer_pubkey: str, subject_pubkey: str, jurisdiction: str) -> dict:
    """Create a minimal valid kind-30850 attestation event (for mock signer responses)."""
    created_at = int(time.time())
    tags = [
        ["d", f"attest:{jurisdiction}:{subject_pubkey}"],
        ["p", subject_pubkey],
        ["j", jurisdiction],
        ["type", "physical"],
    ]
    content = f"civicos:attestation:v1:{jurisdiction}:physical:{created_at}"
    event_id = _compute_nostr_event_id(issuer_pubkey, created_at, 30850, tags, content)
    return {
        "id": event_id,
        "pubkey": issuer_pubkey,
        "created_at": created_at,
        "kind": 30850,
        "tags": tags,
        "content": content,
        "sig": "a" * 128,  # Placeholder — real sig verification mocked
    }


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def resident_keypair():
    return KeyPair.generate()


@pytest.fixture
def issuer_keypair():
    return KeyPair.generate()


@pytest.fixture
def mock_signer_client():
    return MagicMock(spec=IssuerSignerClient)


@pytest.fixture
def service(storage, mock_signer_client):
    return AttestationService(
        attestation_storage=storage.attestations,
        issuer_storage=storage.issuers,
        signer_client=mock_signer_client,
    )


# --- Issuer Registration Tests ---


class TestIssuerRegistration:
    def test_register_issuer(self, service, issuer_keypair):
        result = service.register_issuer({
            "issuer_pubkey": issuer_keypair.public_key_hex,
            "jurisdiction": "city-san-rafael",
            "organization": "San Rafael Library",
            "signing_url": "https://signer.library.example.com",
            "bearer_token": "test-secret-token",
            "allowed_types": ["physical"],
        })

        assert result["issuer_id"] == "issuer:city-san-rafael:san-rafael-library"
        assert result["status"] == "pending_verification"

    def test_register_duplicate_fails(self, service, issuer_keypair):
        reg = {
            "issuer_pubkey": issuer_keypair.public_key_hex,
            "jurisdiction": "city-san-rafael",
            "organization": "San Rafael Library",
            "signing_url": "https://signer.library.example.com",
            "bearer_token": "test-secret-token",
        }
        service.register_issuer(reg)

        with pytest.raises(ValueError, match="already registered"):
            service.register_issuer(reg)

    def test_register_invalid_pubkey(self, service):
        with pytest.raises(ValueError, match="pubkey"):
            service.register_issuer({
                "issuer_pubkey": "tooshort",
                "jurisdiction": "city-san-rafael",
                "organization": "Test",
                "signing_url": "https://example.com",
                "bearer_token": "tok",
            })

    def test_list_issuers(self, service, issuer_keypair):
        service.register_issuer({
            "issuer_pubkey": issuer_keypair.public_key_hex,
            "jurisdiction": "city-san-rafael",
            "organization": "Library",
            "signing_url": "https://example.com",
            "bearer_token": "tok",
        })
        issuers = service.list_issuers("city-san-rafael")
        assert len(issuers) == 1
        assert issuers[0]["organization"] == "Library"
        assert "bearer_token" not in issuers[0]  # Sensitive field stripped

    def test_verify_and_revoke_issuer(self, service, issuer_keypair):
        result = service.register_issuer({
            "issuer_pubkey": issuer_keypair.public_key_hex,
            "jurisdiction": "city-san-rafael",
            "organization": "Library",
            "signing_url": "https://example.com",
            "bearer_token": "tok",
        })
        issuer_id = result["issuer_id"]

        assert service.verify_issuer(issuer_id) is True
        assert service.revoke_issuer(issuer_id) is True

        # After revocation, list should be empty
        assert len(service.list_issuers("city-san-rafael")) == 0


# --- Code Redemption Tests ---


class TestCodeRedemption:
    def _setup_issuer_and_code(self, storage, service, issuer_keypair):
        """Register an issuer, verify it, and create a code."""
        result = service.register_issuer({
            "issuer_pubkey": issuer_keypair.public_key_hex,
            "jurisdiction": "city-san-rafael",
            "organization": "Library",
            "signing_url": "https://signer.example.com",
            "bearer_token": "test-token",
        })
        issuer_id = result["issuer_id"]
        service.verify_issuer(issuer_id)

        # Add a code linked to this issuer
        storage.attestations.add_code(
            code="SR-2026-02-TEST",
            jurisdiction="city-san-rafael",
            batch_id="batch-001",
        )
        # Link code to issuer (in-memory needs manual linking)
        storage.attestations._codes["SR-2026-02-TEST"]["issuer_id"] = issuer_id

        return issuer_id

    @patch("civicos_relay.attestation.service.verify_attestation_proof", return_value=True)
    def test_redeem_code_success(
        self, mock_verify, storage, service, mock_signer_client,
        resident_keypair, issuer_keypair,
    ):
        issuer_id = self._setup_issuer_and_code(storage, service, issuer_keypair)

        # Mock the signer response
        mock_event = _make_attestation_event(
            issuer_keypair.public_key_hex,
            resident_keypair.public_key_hex,
            "city-san-rafael",
        )
        mock_signer_client.sign_attestation.return_value = mock_event

        # Mock get_code_issuer for in-memory (return the issuer record)
        issuer_record = storage.issuers.get_issuer(issuer_id)
        storage.issuers.get_code_issuer = MagicMock(return_value=issuer_record)

        sig, created_at = _sign_attestation_request(resident_keypair, "SR-2026-02-TEST")

        event = service.redeem_code(
            code="SR-2026-02-TEST",
            subject_pubkey=resident_keypair.public_key_hex,
            signature=sig,
            created_at=created_at,
        )

        assert event["kind"] == 30850
        assert event["pubkey"] == issuer_keypair.public_key_hex

        # Code should now be redeemed
        code_record = storage.attestations.get_code("SR-2026-02-TEST")
        assert code_record["redeemed_by"] == resident_keypair.public_key_hex

        # Attestation should be stored
        att = storage.attestations.get_attestation(
            resident_keypair.public_key_hex, "city-san-rafael"
        )
        assert att is not None

    def test_redeem_invalid_signature(self, storage, service, resident_keypair, issuer_keypair):
        self._setup_issuer_and_code(storage, service, issuer_keypair)

        with pytest.raises(ValueError, match="signature"):
            service.redeem_code(
                code="SR-2026-02-TEST",
                subject_pubkey=resident_keypair.public_key_hex,
                signature="bad" * 42 + "ab",
                created_at=int(time.time()),
            )

    def test_redeem_nonexistent_code(self, service, resident_keypair):
        sig, created_at = _sign_attestation_request(resident_keypair, "FAKE-CODE")
        with pytest.raises(ValueError, match="not found"):
            service.redeem_code(
                code="FAKE-CODE",
                subject_pubkey=resident_keypair.public_key_hex,
                signature=sig,
                created_at=created_at,
            )

    @patch("civicos_relay.attestation.service.verify_attestation_proof", return_value=True)
    def test_redeem_already_redeemed(
        self, mock_verify, storage, service, mock_signer_client,
        resident_keypair, issuer_keypair,
    ):
        issuer_id = self._setup_issuer_and_code(storage, service, issuer_keypair)

        mock_event = _make_attestation_event(
            issuer_keypair.public_key_hex,
            resident_keypair.public_key_hex,
            "city-san-rafael",
        )
        mock_signer_client.sign_attestation.return_value = mock_event

        issuer_record = storage.issuers.get_issuer(issuer_id)
        storage.issuers.get_code_issuer = MagicMock(return_value=issuer_record)

        sig, created_at = _sign_attestation_request(resident_keypair, "SR-2026-02-TEST")
        service.redeem_code(
            code="SR-2026-02-TEST",
            subject_pubkey=resident_keypair.public_key_hex,
            signature=sig,
            created_at=created_at,
        )

        # Second redemption should fail
        sig2, created_at2 = _sign_attestation_request(resident_keypair, "SR-2026-02-TEST")
        with pytest.raises(ValueError, match="already redeemed"):
            service.redeem_code(
                code="SR-2026-02-TEST",
                subject_pubkey=resident_keypair.public_key_hex,
                signature=sig2,
                created_at=created_at2,
            )

    def test_redeem_unverified_issuer(self, storage, service, resident_keypair, issuer_keypair):
        """Code from unverified issuer should be rejected."""
        result = service.register_issuer({
            "issuer_pubkey": issuer_keypair.public_key_hex,
            "jurisdiction": "city-san-rafael",
            "organization": "Unverified Org",
            "signing_url": "https://example.com",
            "bearer_token": "tok",
        })
        issuer_id = result["issuer_id"]
        # Note: NOT calling verify_issuer

        storage.attestations.add_code(
            code="SR-2026-02-UNVER",
            jurisdiction="city-san-rafael",
            batch_id="batch-002",
        )
        storage.attestations._codes["SR-2026-02-UNVER"]["issuer_id"] = issuer_id

        issuer_record = storage.issuers.get_issuer(issuer_id)
        storage.issuers.get_code_issuer = MagicMock(return_value=issuer_record)

        sig, created_at = _sign_attestation_request(resident_keypair, "SR-2026-02-UNVER")
        with pytest.raises(ValueError, match="not verified"):
            service.redeem_code(
                code="SR-2026-02-UNVER",
                subject_pubkey=resident_keypair.public_key_hex,
                signature=sig,
                created_at=created_at,
            )


# --- Signer Client Tests ---


class TestSignerClient:
    def test_sign_attestation_validates_response(self):
        client = IssuerSignerClient()

        # Mock httpx.post to return a valid response
        with patch("civicos_relay.attestation.signer_client.httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "attestation_event": {
                    "id": "a" * 64,
                    "pubkey": "b" * 64,
                    "created_at": int(time.time()),
                    "kind": 30850,
                    "tags": [],
                    "content": "test",
                    "sig": "c" * 128,
                }
            }
            mock_post.return_value = mock_resp

            event = client.sign_attestation(
                signing_url="https://signer.example.com",
                bearer_token="test-token",
                subject_pubkey="d" * 64,
                jurisdiction="city-san-rafael",
                code="SR-2026-02-TEST",
            )
            assert event["kind"] == 30850

    def test_sign_attestation_rejects_wrong_kind(self):
        client = IssuerSignerClient()

        with patch("civicos_relay.attestation.signer_client.httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "attestation_event": {
                    "id": "a" * 64,
                    "pubkey": "b" * 64,
                    "created_at": int(time.time()),
                    "kind": 1,  # Wrong kind
                    "tags": [],
                    "content": "test",
                    "sig": "c" * 128,
                }
            }
            mock_post.return_value = mock_resp

            with pytest.raises(SignerError, match="kind"):
                client.sign_attestation(
                    signing_url="https://signer.example.com",
                    bearer_token="test-token",
                    subject_pubkey="d" * 64,
                    jurisdiction="city-san-rafael",
                    code="SR-2026-02-TEST",
                )

    def test_sign_attestation_handles_401(self):
        client = IssuerSignerClient()

        with patch("civicos_relay.attestation.signer_client.httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_post.return_value = mock_resp

            with pytest.raises(SignerError, match="token rejected"):
                client.sign_attestation(
                    signing_url="https://signer.example.com",
                    bearer_token="bad-token",
                    subject_pubkey="d" * 64,
                    jurisdiction="city-san-rafael",
                    code="SR-2026-02-TEST",
                )

    def test_sign_attestation_handles_timeout(self):
        client = IssuerSignerClient()

        import httpx
        with patch(
            "civicos_relay.attestation.signer_client.httpx.post",
            side_effect=httpx.TimeoutException("timeout"),
        ):
            with pytest.raises(SignerError, match="timed out"):
                client.sign_attestation(
                    signing_url="https://signer.example.com",
                    bearer_token="token",
                    subject_pubkey="d" * 64,
                    jurisdiction="city-san-rafael",
                    code="SR-2026-02-TEST",
                )

    def test_check_health(self):
        client = IssuerSignerClient()

        with patch("civicos_relay.attestation.signer_client.httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "status": "ok",
                "issuer_pubkey": "a" * 64,
            }
            mock_get.return_value = mock_resp

            result = client.check_health("https://signer.example.com")
            assert result["status"] == "ok"

    def test_check_health_unreachable(self):
        client = IssuerSignerClient()

        import httpx
        with patch(
            "civicos_relay.attestation.signer_client.httpx.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            assert client.check_health("https://bad.example.com") is None


# --- Code Batch Tests ---


def _register_verified_issuer(service, issuer_keypair, jurisdiction="city-san-rafael"):
    """Helper: register and verify an issuer."""
    result = service.register_issuer({
        "issuer_pubkey": issuer_keypair.public_key_hex,
        "jurisdiction": jurisdiction,
        "organization": "Test Org",
        "signing_url": "https://signer.example.com",
        "bearer_token": "test-token",
        "allowed_types": ["physical"],
    })
    service.verify_issuer(result["issuer_id"])
    return result["issuer_id"]


class TestCodeBatch:
    def test_accept_signed_batch(self, service, issuer_keypair):
        """Issuer-signed code batch is accepted and stored."""
        from civicos_signer.crypto import IssuerKeyPair, sign_code_batch

        issuer_id = _register_verified_issuer(service, issuer_keypair)

        signer_kp = IssuerKeyPair(
            public_key_hex=issuer_keypair.public_key_hex,
            private_key_hex=issuer_keypair.private_key_hex,
        )
        codes = ["SR-2026-03-AAAA", "SR-2026-03-BBBB", "SR-2026-03-CCCC"]
        event = sign_code_batch(signer_kp, codes, "city-san-rafael", "test-batch")

        result = service.accept_code_batch(event)
        assert result["count"] == 3
        assert result["batch_id"] == "test-batch"
        assert result["issuer_id"] == issuer_id

    def test_reject_unregistered_issuer(self, service):
        """Codes from unknown issuer are rejected."""
        from civicos_signer.crypto import IssuerKeyPair, sign_code_batch

        rogue = IssuerKeyPair.generate()
        codes = ["SR-2026-03-ROGUE"]
        event = sign_code_batch(rogue, codes, "city-san-rafael", "rogue-batch")

        with pytest.raises(ValueError, match="No registered issuer"):
            service.accept_code_batch(event)

    def test_reject_unverified_issuer(self, service, issuer_keypair):
        """Codes from unverified issuer are rejected."""
        from civicos_signer.crypto import IssuerKeyPair, sign_code_batch

        # Register but don't verify
        service.register_issuer({
            "issuer_pubkey": issuer_keypair.public_key_hex,
            "jurisdiction": "city-san-rafael",
            "organization": "Unverified Org",
            "signing_url": "https://signer.example.com",
            "bearer_token": "test-token",
        })

        signer_kp = IssuerKeyPair(
            public_key_hex=issuer_keypair.public_key_hex,
            private_key_hex=issuer_keypair.private_key_hex,
        )
        event = sign_code_batch(signer_kp, ["SR-2026-03-TEST"], "city-san-rafael", "batch")

        with pytest.raises(ValueError, match="not verified"):
            service.accept_code_batch(event)

    def test_reject_tampered_codes(self, service, issuer_keypair):
        """Codes tampered after signing are rejected."""
        from civicos_signer.crypto import IssuerKeyPair, sign_code_batch
        import json

        _register_verified_issuer(service, issuer_keypair)

        signer_kp = IssuerKeyPair(
            public_key_hex=issuer_keypair.public_key_hex,
            private_key_hex=issuer_keypair.private_key_hex,
        )
        event = sign_code_batch(signer_kp, ["SR-2026-03-REAL"], "city-san-rafael", "batch")

        # Tamper: add an extra code
        event["content"] = json.dumps(["SR-2026-03-REAL", "SR-2026-03-FAKE"])

        with pytest.raises(ValueError, match="Invalid signature"):
            service.accept_code_batch(event)

    def test_duplicate_codes_skipped(self, service, issuer_keypair):
        """Submitting the same codes twice doesn't create duplicates."""
        from civicos_signer.crypto import IssuerKeyPair, sign_code_batch

        _register_verified_issuer(service, issuer_keypair)

        signer_kp = IssuerKeyPair(
            public_key_hex=issuer_keypair.public_key_hex,
            private_key_hex=issuer_keypair.private_key_hex,
        )
        codes = ["SR-2026-03-DUP1", "SR-2026-03-DUP2"]

        event1 = sign_code_batch(signer_kp, codes, "city-san-rafael", "batch-1")
        result1 = service.accept_code_batch(event1)
        assert result1["count"] == 2

        event2 = sign_code_batch(signer_kp, codes, "city-san-rafael", "batch-2")
        result2 = service.accept_code_batch(event2)
        assert result2["count"] == 0

    def test_codes_redeemable_after_batch(self, service, storage, issuer_keypair, resident_keypair, mock_signer_client):
        """Codes from a batch can be redeemed through the normal flow."""
        from civicos_signer.crypto import IssuerKeyPair, sign_code_batch

        issuer_id = _register_verified_issuer(service, issuer_keypair)

        signer_kp = IssuerKeyPair(
            public_key_hex=issuer_keypair.public_key_hex,
            private_key_hex=issuer_keypair.private_key_hex,
        )
        event = sign_code_batch(signer_kp, ["SR-2026-03-REDM"], "city-san-rafael", "batch")
        service.accept_code_batch(event)

        # Now the code should be findable
        code_record = storage.attestations.get_code("SR-2026-03-REDM")
        assert code_record is not None
        assert code_record["jurisdiction"] == "city-san-rafael"
        assert code_record["issuer_id"] == issuer_id
