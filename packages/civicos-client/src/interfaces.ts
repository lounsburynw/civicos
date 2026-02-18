/**
 * Platform-agnostic storage adapter for caching and preferences.
 *
 * Implementations: ChromeStorageAdapter (extension), localStorage adapter (web), etc.
 */
export interface StorageAdapter {
  get<T = unknown>(key: string): Promise<T | null>;
  set(key: string, value: unknown): Promise<void>;
  remove(key: string): Promise<void>;
}

/**
 * Unsigned Nostr-style civic event before signing.
 * Pubkey/id/sig are absent — the Signer fills them in.
 */
export interface UnsignedCivicEvent {
  kind: number;
  tags: string[][];
  content: string;
  created_at: number;
}

/**
 * Fully signed civic event ready for relay submission.
 */
export interface SignedCivicEvent extends UnsignedCivicEvent {
  id: string;
  pubkey: string;
  sig: string;
}

/**
 * Platform-agnostic signing interface for authenticated civic operations.
 *
 * Implementations: ExtensionSigner (Chrome background), DirectSigner (loom-core), etc.
 */
export interface Signer {
  getPublicKey(): Promise<string>;
  signEvent(event: UnsignedCivicEvent): Promise<SignedCivicEvent>;
}
