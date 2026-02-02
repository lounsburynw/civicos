# Key Migration Guide

Migrate your CivicOS identity to Nostr while preserving your civic provenance.

## Overview

CivicOS now uses Nostr for civic coordination. If you have an existing CivicOS account with voice history, this guide helps you migrate to a Nostr key while keeping your provenance (key age, voice count, attestations).

## What You'll Need

1. **Your old CivicOS key** — The SECP256R1 keypair from your original CivicOS account
2. **A Nostr client** — Any client that supports key management:
   - **iOS**: Damus, Primal
   - **Android**: Amethyst, Primal
   - **Web**: Primal, Snort
   - **Browser extension**: nos2x, Alby

## Step 1: Generate Your Nostr Key

In your chosen Nostr client:

1. Create a new account (or use existing Nostr key if you have one)
2. Note your **public key** (npub format or hex)
3. Keep your **private key** secure (nsec format)

**Example public key formats:**
```
npub:  npub1abc123def456...
hex:   a1b2c3d4e5f6...64 characters
```

## Step 2: Connect to CivicOS Relay

Add the CivicOS relay to your Nostr client:

```
wss://relay.civicos.org
```

Most clients have a "Relays" section in settings where you can add new relay URLs.

## Step 3: Sign the Link Message

You need to sign a specific message with your **old** CivicOS key to prove ownership.

**Message format:**
```
civicos:link:v1:<your-new-nostr-pubkey-hex>
```

**Example:**
```
civicos:link:v1:a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890
```

### Using the Migration Tool

```bash
# If you have your old key file
python -m civicos_relay.tools.migrate \
  --old-key ~/.civicos/key.pem \
  --new-pubkey a1b2c3d4e5f6...
```

The tool outputs:
- The link message
- Your old key's signature (hex format)
- Instructions for the next step

### Manual Signing

If you prefer to sign manually:

```python
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

# Load your old key
with open("old_key.pem", "rb") as f:
    old_private_key = serialization.load_pem_private_key(f.read(), password=None)

# Sign the message
new_pubkey_hex = "a1b2c3d4..."  # Your Nostr pubkey
message = f"civicos:link:v1:{new_pubkey_hex}"
signature = old_private_key.sign(message.encode(), ec.ECDSA(hashes.SHA256()))
signature_hex = signature.hex()
```

## Step 4: Publish Key Link Attestation

Publish a kind 1802 event to the CivicOS relay with both signatures:

```json
{
  "kind": 1802,
  "pubkey": "<your-new-nostr-pubkey>",
  "created_at": 1738464000,
  "tags": [
    ["old-key", "<your-old-civicos-pubkey-hex>"],
    ["old-sig", "<signature-from-step-3>"]
  ],
  "content": "Key migration attestation: I control both keys",
  "sig": "<nostr-signature>"
}
```

### Using Nostr Client

Most Nostr clients don't have built-in support for custom event kinds. Options:

1. **CivicOS Migration Page** (recommended)
   - Visit `civicos.org/migrate`
   - Paste your old signature
   - Sign with Nostr client

2. **nostr-tools (JavaScript)**
   ```javascript
   import { getEventHash, signEvent } from 'nostr-tools'

   const event = {
     kind: 1802,
     pubkey: yourNostrPubkey,
     created_at: Math.floor(Date.now() / 1000),
     tags: [
       ['old-key', oldCivicosKeyHex],
       ['old-sig', oldKeySignatureHex]
     ],
     content: 'Key migration attestation: I control both keys'
   }

   event.id = getEventHash(event)
   event.sig = signEvent(event, yourNostrPrivateKey)

   // Send to relay
   ws.send(JSON.stringify(['EVENT', event]))
   ```

## Step 5: Verify Migration

After publishing, verify your provenance transferred:

```bash
# Query your provenance
wscat -c wss://relay.civicos.org
> ["REQ", "my-provenance", {"kinds": [10800], "authors": ["<your-nostr-pubkey>"]}]
```

Expected response includes:
- `first-voice`: Your original first voice date
- `total-voices`: Combined voice count
- `attestation`: Any physical/device attestations

## What Transfers

| Data | Transfers | Notes |
|------|-----------|-------|
| Voice count | Yes | Total voices from old key |
| Key age (first-voice date) | Yes | Original account creation |
| Attestations | Yes | Physical, device attestations |
| Voice history | Yes | All past voices attributed to linked identity |
| Private data | No | Subscriptions must be recreated |

## After Migration

Once migrated:

1. **Use your Nostr key** for all new civic activity
2. **Your old key is linked** — provenance queries return combined history
3. **Old REST API** still works but is deprecated (use WebSocket)

## Troubleshooting

### "Invalid old key signature"

- Verify you signed the exact message: `civicos:link:v1:<pubkey>`
- Ensure the pubkey in the message matches your Nostr key exactly (64 hex chars)
- Check signature is hex-encoded

### "Old key already linked"

Each old key can only link to one Nostr key. If you've already migrated:
- Use the Nostr key you previously linked
- Contact support if you've lost access

### "Invalid Nostr event signature"

- Ensure your Nostr client is signing the event correctly
- Verify the event structure matches kind 1802 spec

## Security Notes

- **Never share your private keys** (old or new)
- **The link is permanent** — once linked, keys cannot be unlinked
- **Old key can be retired** after successful migration
- **Backup your Nostr nsec** — losing it means losing your civic identity

## Support

- **Documentation**: `docs/critical/NOSTR_CIVIC_NIPS.md`
- **Issues**: github.com/civicos/civicos/issues
- **Email**: support@civicos.org
