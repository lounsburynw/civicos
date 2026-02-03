/**
 * Signing providers for client-side Nostr identity management.
 *
 * Three identity tiers:
 * - Easy (PasskeyProvider): WebAuthn + PRF, lowest friction
 * - Private (LocalWalletProvider): BIP-39 + password, medium friction
 * - Sovereign (NIP07Provider, etc.): Full self-custody, highest security
 */

// Types
export type {
  IdentityTier,
  NostrEvent,
  SignedNostrEvent,
  SigningResult,
  IdentityInfo,
  CreateIdentityOptions,
  UnlockOptions,
  SigningProvider,
} from './types.js';

export {
  CivicEventKinds,
  createVoiceContent,
  createVoiceTags,
  createCommitmentContent,
  createCommitmentTags,
  createCompletionContent,
  createCompletionTags,
} from './types.js';

// Crypto utilities
export {
  generatePrivateKey,
  getPublicKey,
  publicKeyToHex,
  privateKeyToHex,
  hexToPrivateKey,
  computeEventId,
  schnorrSign,
  schnorrVerify,
  signNostrEvent,
  verifyNostrEvent,
  publicKeyToNpub,
  npubToPublicKey,
  privateKeyToNsec,
  nsecToPrivateKey,
} from './crypto.js';

// Providers
export {
  LocalWalletProvider,
  IndexedDBStorage,
  MemoryStorage,
  type WalletStorage,
} from './local-wallet.js';

export {
  PasskeyProvider,
  LocalStoragePasskeyStorage,
  MemoryPasskeyStorage,
  type PasskeyStorage,
} from './passkey.js';

// Future exports (not yet implemented):
// export { NIP07Provider } from './nip07.js';
// export { HardwareWalletProvider } from './hardware.js';
// export { ManualSigningProvider } from './manual.js';
