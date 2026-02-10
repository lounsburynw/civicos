/**
 * A cryptographic keypair: private key bytes + hex-encoded public key.
 * The key format depends on the protocol adapter (e.g., secp256k1 x-only for Nostr).
 */
export interface KeyPair {
  privateKey: Uint8Array;
  publicKey: string;
}

/**
 * Persistent storage for a private key (hex-encoded).
 * Implement this for your environment (localStorage, keychain, file, etc.).
 */
export interface KeyStore {
  load(): Promise<string | null>;
  save(hex: string): Promise<void>;
}

/**
 * Contract for a protocol adapter. Each federated protocol (Nostr, AT Protocol,
 * ActivityPub) implements this interface with its own key type, event format,
 * and signing algorithm.
 *
 * The Nostr adapter (`loom-core/nostr`) is the reference implementation.
 *
 * To build a new adapter:
 * 1. Create `src/{protocol}/` directory
 * 2. Implement ProtocolAdapter using your protocol's crypto
 * 3. Export from `src/{protocol}/index.ts`
 * 4. Add export path to package.json `exports` map
 */
export interface ProtocolAdapter<TUnsigned, TSigned> {
  createKeyPair(): KeyPair;
  loadKeyPair(store: KeyStore): Promise<KeyPair>;
  signEvent(event: TUnsigned, privateKey: Uint8Array): Promise<TSigned>;
  verifyEvent(event: TSigned): Promise<boolean>;
  signMessage(message: string, privateKey: Uint8Array): Promise<{ messageHash: string; signature: string }>;
  verifyMessage(message: string, signature: string, publicKey: string): Promise<boolean>;
}
