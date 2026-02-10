# loom-core

Federated protocol signing framework. Protocol-agnostic interfaces with pluggable adapters.

## Architecture

```
loom-core/src/
  types.ts              ← Protocol-agnostic: KeyPair, KeyStore, ProtocolAdapter
  hash.ts               ← Protocol-agnostic: SHA-256 utility
  index.ts              ← Top-level exports (interfaces + hash only)
  nostr/                ← Nostr adapter (secp256k1 Schnorr / NIP-01)
    identity.ts         ← Key generation (secp256k1)
    event.ts            ← NIP-01 event signing
    message.ts          ← Plain message signing
    types.ts            ← UnsignedEvent, SignedEvent
    index.ts            ← Nostr exports
```

**The top level contains no crypto implementations.** It defines interfaces (`KeyPair`, `KeyStore`, `ProtocolAdapter`) and a generic SHA-256 utility. All signing, key generation, and verification live inside protocol-specific adapters.

## Import Paths

```typescript
// Protocol-agnostic interfaces + utilities
import { sha256Hex, type KeyPair, type KeyStore, type ProtocolAdapter } from 'loom-core';

// Nostr adapter (secp256k1 Schnorr signatures)
import { loadKeyPair, signEvent, signMessage } from 'loom-core/nostr';
```

## ProtocolAdapter Contract

Every adapter implements this interface (defined in `types.ts`):

```typescript
interface ProtocolAdapter<TUnsigned, TSigned> {
  createKeyPair(): KeyPair;
  loadKeyPair(store: KeyStore): Promise<KeyPair>;
  signEvent(event: TUnsigned, privateKey: Uint8Array): Promise<TSigned>;
  verifyEvent(event: TSigned): Promise<boolean>;
  signMessage(message: string, privateKey: Uint8Array): Promise<MessageSig>;
  verifyMessage(message: string, signature: string, publicKey: string): Promise<boolean>;
}
```

The Nostr adapter implements this with `TUnsigned = UnsignedEvent`, `TSigned = SignedEvent`.

## Building a New Adapter

To add support for a new protocol (e.g., AT Protocol):

1. Create `src/atproto/` directory
2. Implement `ProtocolAdapter<YourUnsigned, YourSigned>` using the protocol's crypto
3. Export all functions from `src/atproto/index.ts`
4. Add `"./atproto": "./dist/atproto/index.js"` to `package.json` exports
5. Consumers import from `loom-core/atproto`

The top-level interfaces (`KeyPair`, `KeyStore`) are shared across all adapters. The `sha256Hex` utility is available to any adapter that needs it.

## Nostr Adapter Details

- **Curve**: secp256k1 (BIP-340 Schnorr signatures via `@noble/secp256k1`)
- **Event format**: NIP-01 (`[0, pubkey, created_at, kind, tags, content]`)
- **Event ID**: SHA-256 of serialized event
- **Message signing**: SHA-256 hash → Schnorr sign hash bytes
- **Verification**: Matches Python backend `verify_signature()` in `civicos_relay/voice/crypto.py`
