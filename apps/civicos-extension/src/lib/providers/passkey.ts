/**
 * PasskeyProvider - Easy identity tier.
 *
 * Uses WebAuthn with PRF extension to derive deterministic Nostr keypairs.
 * The user's email + passkey biometric generates the same keypair across devices.
 *
 * Security model:
 * - Private key derived on-demand from passkey PRF output
 * - No key stored on device (derived each time)
 * - Passkeys synced via iCloud/Google (cloud recovery)
 * - Email serves as salt (must be remembered for recovery)
 *
 * Browser support:
 * - Chrome 116+ (full PRF support)
 * - Safari 17+ (macOS Sonoma+)
 * - Firefox: NOT SUPPORTED (no PRF extension)
 */

import { hkdf } from '@noble/hashes/hkdf';
import { sha256 } from '@noble/hashes/sha256';
import {
  getPublicKey,
  publicKeyToHex,
  publicKeyToNpub,
  signNostrEvent,
} from './crypto.js';
import type {
  SigningProvider,
  IdentityTier,
  IdentityInfo,
  CreateIdentityOptions,
  UnlockOptions,
  NostrEvent,
  SigningResult,
} from './types.js';

// WebAuthn credential storage key
const STORAGE_KEY = 'civicos-passkey-identity';

// HKDF parameters for key derivation
const HKDF_INFO = new TextEncoder().encode('civicos-nostr-key-v1');

// Auto-lock timeout (5 minutes)
const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000;

/**
 * Stored passkey identity metadata (not the key itself).
 * The actual keypair is derived on-demand from passkey PRF.
 */
interface StoredPasskeyIdentity {
  version: 1;
  credentialId: string; // Base64-encoded credential ID
  email: string; // Used as salt for HKDF
  publicKey: string; // Hex-encoded Nostr public key
  createdAt: number;
}

/**
 * PasskeyProvider implements the "Easy" identity tier.
 *
 * Flow:
 * 1. User provides email
 * 2. WebAuthn creates passkey with PRF extension
 * 3. PRF output + email -> HKDF -> secp256k1 private key
 * 4. Private key is never stored, only derived when unlocked
 */
export class PasskeyProvider implements SigningProvider {
  readonly tier: IdentityTier = 'easy';
  readonly name = 'Passkey (TouchID/FaceID)';

  private privateKey: Uint8Array | null = null;
  private publicKey: Uint8Array | null = null;
  private unlockTimeout: ReturnType<typeof setTimeout> | null = null;
  private storage: PasskeyStorage;

  constructor(storage?: PasskeyStorage) {
    this.storage = storage ?? new LocalStoragePasskeyStorage();
  }

  async isAvailable(): Promise<boolean> {
    if (
      typeof window === 'undefined' ||
      typeof navigator === 'undefined' ||
      !navigator.credentials ||
      typeof PublicKeyCredential === 'undefined'
    ) {
      return false;
    }

    try {
      if (typeof PublicKeyCredential.isConditionalMediationAvailable === 'function') {
        const conditionalAvailable = await PublicKeyCredential.isConditionalMediationAvailable();
        return conditionalAvailable;
      }
      return false;
    } catch {
      return false;
    }
  }

  async hasIdentity(): Promise<boolean> {
    const stored = await this.storage.load();
    return stored !== null;
  }

  async getIdentity(): Promise<IdentityInfo | null> {
    const stored = await this.storage.load();
    if (!stored) return null;

    return {
      tier: this.tier,
      publicKey: stored.publicKey,
      npub: publicKeyToNpub(stored.publicKey),
      createdAt: stored.createdAt,
    };
  }

  async getPublicKey(): Promise<string | null> {
    if (this.publicKey) {
      return publicKeyToHex(this.publicKey);
    }

    const stored = await this.storage.load();
    return stored?.publicKey ?? null;
  }

  async createIdentity(options: CreateIdentityOptions & { email?: string }): Promise<{
    identity: IdentityInfo;
    mnemonic?: string;
  }> {
    if (options.tier !== 'easy') {
      throw new Error(`PasskeyProvider only supports 'easy' tier, got '${options.tier}'`);
    }

    const email = options.email;
    if (!email) {
      throw new Error('Email is required for Easy mode identity');
    }

    if (!email.includes('@') || email.length < 5) {
      throw new Error('Invalid email format');
    }

    if (await this.hasIdentity()) {
      throw new Error('Identity already exists. Delete it first to create a new one.');
    }

    const { credentialId, privateKey } = await this.createPasskeyWithPRF(email);

    const publicKey = getPublicKey(privateKey);
    const publicKeyHex = publicKeyToHex(publicKey);

    const stored: StoredPasskeyIdentity = {
      version: 1,
      credentialId: credentialId,
      email: email,
      publicKey: publicKeyHex,
      createdAt: Date.now(),
    };

    await this.storage.save(stored);

    this.privateKey = privateKey;
    this.publicKey = publicKey;
    this.setUnlockTimeout(DEFAULT_TIMEOUT_MS);

    return {
      identity: {
        tier: this.tier,
        publicKey: publicKeyHex,
        npub: publicKeyToNpub(publicKeyHex),
        createdAt: stored.createdAt,
      },
    };
  }

  async importIdentity(options: CreateIdentityOptions & { email?: string }): Promise<IdentityInfo> {
    if (options.tier !== 'easy') {
      throw new Error(`PasskeyProvider only supports 'easy' tier, got '${options.tier}'`);
    }

    const email = options.email;
    if (!email) {
      throw new Error('Email is required to recover Easy mode identity');
    }

    if (await this.hasIdentity()) {
      throw new Error('Identity already exists. Delete it first to import.');
    }

    const { credentialId, privateKey } = await this.authenticateWithPRF(email);

    const publicKey = getPublicKey(privateKey);
    const publicKeyHex = publicKeyToHex(publicKey);

    const stored: StoredPasskeyIdentity = {
      version: 1,
      credentialId: credentialId,
      email: email,
      publicKey: publicKeyHex,
      createdAt: Date.now(),
    };

    await this.storage.save(stored);

    this.privateKey = privateKey;
    this.publicKey = publicKey;
    this.setUnlockTimeout(DEFAULT_TIMEOUT_MS);

    return {
      tier: this.tier,
      publicKey: publicKeyHex,
      npub: publicKeyToNpub(publicKeyHex),
      createdAt: stored.createdAt,
    };
  }

  async unlock(options?: UnlockOptions): Promise<boolean> {
    const stored = await this.storage.load();
    if (!stored) {
      throw new Error('No identity found. Create or import one first.');
    }

    try {
      const { privateKey } = await this.authenticateWithPRF(stored.email, stored.credentialId);

      const derivedPubKey = publicKeyToHex(getPublicKey(privateKey));
      if (derivedPubKey !== stored.publicKey) {
        throw new Error('Derived key mismatch. Wrong passkey or email.');
      }

      this.privateKey = privateKey;
      this.publicKey = getPublicKey(privateKey);

      const timeout = options?.timeout ?? DEFAULT_TIMEOUT_MS;
      this.setUnlockTimeout(timeout);

      return true;
    } catch {
      return false;
    }
  }

  isUnlocked(): boolean {
    return this.privateKey !== null;
  }

  lock(): void {
    if (this.privateKey) {
      this.privateKey.fill(0);
      this.privateKey = null;
    }
    this.publicKey = null;

    if (this.unlockTimeout) {
      clearTimeout(this.unlockTimeout);
      this.unlockTimeout = null;
    }
  }

  async signEvent(event: NostrEvent): Promise<SigningResult> {
    if (!this.privateKey) {
      return {
        success: false,
        error: 'Identity is locked. Call unlock() first.',
      };
    }

    try {
      const signedEvent = await signNostrEvent(event, this.privateKey);
      return {
        success: true,
        event: signedEvent,
      };
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : 'Signing failed',
      };
    }
  }

  async deleteIdentity(): Promise<void> {
    this.lock();
    await this.storage.delete();
  }

  // Private methods

  private async createPasskeyWithPRF(email: string): Promise<{
    credentialId: string;
    privateKey: Uint8Array;
  }> {
    const salt = this.computePRFSalt(email);

    const credential = await navigator.credentials.create({
      publicKey: {
        challenge: crypto.getRandomValues(new Uint8Array(32)),
        rp: {
          name: 'CivicOS',
          id: this.getRpId(),
        },
        user: {
          id: new TextEncoder().encode(email),
          name: email,
          displayName: email.split('@')[0],
        },
        pubKeyCredParams: [
          { alg: -7, type: 'public-key' },
          { alg: -257, type: 'public-key' },
        ],
        authenticatorSelection: {
          authenticatorAttachment: 'platform',
          residentKey: 'required',
          userVerification: 'required',
        },
        extensions: {
          prf: {
            eval: {
              first: salt,
            },
          },
        } as AuthenticationExtensionsClientInputs,
      },
    }) as PublicKeyCredential;

    if (!credential) {
      throw new Error('Failed to create passkey');
    }

    const extensionResults = credential.getClientExtensionResults() as PRFExtensionResults;
    if (!extensionResults.prf?.results?.first) {
      throw new Error('PRF extension not supported or failed');
    }

    const prfOutput = new Uint8Array(extensionResults.prf.results.first);
    const privateKey = this.derivePrivateKey(prfOutput);
    const credentialId = this.arrayBufferToBase64(credential.rawId);

    return { credentialId, privateKey };
  }

  private async authenticateWithPRF(
    email: string,
    credentialId?: string
  ): Promise<{
    credentialId: string;
    privateKey: Uint8Array;
  }> {
    const salt = this.computePRFSalt(email);

    const allowCredentials: PublicKeyCredentialDescriptor[] | undefined = credentialId
      ? [{ type: 'public-key', id: this.base64ToArrayBuffer(credentialId) }]
      : undefined;

    const assertion = await navigator.credentials.get({
      publicKey: {
        challenge: crypto.getRandomValues(new Uint8Array(32)),
        rpId: this.getRpId(),
        allowCredentials: allowCredentials,
        userVerification: 'required',
        extensions: {
          prf: {
            eval: {
              first: salt,
            },
          },
        } as AuthenticationExtensionsClientInputs,
      },
    }) as PublicKeyCredential;

    if (!assertion) {
      throw new Error('Passkey authentication failed');
    }

    const extensionResults = assertion.getClientExtensionResults() as PRFExtensionResults;
    if (!extensionResults.prf?.results?.first) {
      throw new Error('PRF extension not supported or failed');
    }

    const prfOutput = new Uint8Array(extensionResults.prf.results.first);
    const privateKey = this.derivePrivateKey(prfOutput);

    return {
      credentialId: this.arrayBufferToBase64(assertion.rawId),
      privateKey,
    };
  }

  private computePRFSalt(email: string): Uint8Array {
    const emailBytes = new TextEncoder().encode(email.toLowerCase().trim());
    return sha256(emailBytes);
  }

  private derivePrivateKey(prfOutput: Uint8Array): Uint8Array {
    return hkdf(sha256, prfOutput, undefined, HKDF_INFO, 32);
  }

  private getRpId(): string {
    if (typeof window !== 'undefined' && window.location) {
      return window.location.hostname;
    }
    return 'localhost';
  }

  private setUnlockTimeout(ms: number): void {
    if (this.unlockTimeout) {
      clearTimeout(this.unlockTimeout);
    }

    if (ms > 0) {
      this.unlockTimeout = setTimeout(() => {
        this.lock();
      }, ms);
    }
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  private base64ToArrayBuffer(base64: string): ArrayBuffer {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }
}

/**
 * Storage interface for passkey identity metadata.
 */
export interface PasskeyStorage {
  save(identity: StoredPasskeyIdentity): Promise<void>;
  load(): Promise<StoredPasskeyIdentity | null>;
  delete(): Promise<void>;
}

/**
 * LocalStorage-based storage for passkey identity.
 * Used in browser environments (fallback).
 */
export class LocalStoragePasskeyStorage implements PasskeyStorage {
  async save(identity: StoredPasskeyIdentity): Promise<void> {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(identity));
    }
  }

  async load(): Promise<StoredPasskeyIdentity | null> {
    if (typeof localStorage === 'undefined') {
      return null;
    }
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : null;
  }

  async delete(): Promise<void> {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(STORAGE_KEY);
    }
  }
}

/**
 * In-memory storage for testing.
 */
export class MemoryPasskeyStorage implements PasskeyStorage {
  private stored: StoredPasskeyIdentity | null = null;

  async save(identity: StoredPasskeyIdentity): Promise<void> {
    this.stored = identity;
  }

  async load(): Promise<StoredPasskeyIdentity | null> {
    return this.stored;
  }

  async delete(): Promise<void> {
    this.stored = null;
  }
}

// TypeScript type definitions for PRF extension (not in standard lib)

interface PRFExtensionResults {
  prf?: {
    enabled?: boolean;
    results?: {
      first?: ArrayBuffer;
      second?: ArrayBuffer;
    };
  };
}
