"""CivicOS Signer — portable attestation signing service.

A lightweight, self-contained service that holds an organization's
attestation issuer keypair and signs kind-30850 Nostr events on request.

Designed to be run by any trusted organization (civic groups, libraries,
city offices) that has been granted issuer authority for a jurisdiction.
"""

__version__ = "0.1.0"
