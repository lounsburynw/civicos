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
 *
 * NOT designed to resist:
 * - Government subpoena of Apple/Google passkey infrastructure
 * - Physical coercion for biometric
 * - State-level adversaries
 *
 * Designed for:
 * - Normal residents in jurisdictions under rule of law
 * - Users who forget passwords
 * - Lowest friction civic participation
 */

import { hkdf } from '@noble/hashes/hkdf';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex } from '@noble/hashes/utils';
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
 * WebAuthn credential creation options.
 * We use these parameters for consistent passkey creation.
 */
interface PasskeyCreationContext {
  email: string;
}

/**
 * PasskeyProvider implements the "Easy" identity tier.
 *
 * Flow:
 * 1. User provides email
 * 2. WebAuthn creates passkey with PRF extension
 * 3. PRF output + email → HKDF → secp256k1 private key
 * 4. Private key is never stored, only derived when unlocked
 *
 * Key derivation:
 * - email → SHA256 → PRF salt (32 bytes)
 * - passkey + PRF salt → PRF → 32 bytes
 * - PRF output → HKDF(SHA256, info="civicos-nostr-key-v1") → private key
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

  /**
   * Check if WebAuthn PRF extension is available.
   */
  async isAvailable(): Promise<boolean> {
    // Check for WebAuthn API
    if (
      typeof window === 'undefined' ||
      typeof navigator === 'undefined' ||
      !navigator.credentials ||
      typeof PublicKeyCredential === 'undefined'
    ) {
      return false;
    }

    // Check for PRF extension support using feature detection
    // This is a heuristic - actual PRF support is verified during credential creation
    try {
      // Check if the browser supports conditional mediation (a proxy for modern WebAuthn)
      if (typeof PublicKeyCredential.isConditionalMediationAvailable === 'function') {
        const conditionalAvailable = await PublicKeyCredential.isConditionalMediationAvailable();
        // Conditional mediation is available in Chrome 108+ and Safari 16+
        // PRF extension requires Chrome 116+ or Safari 17+
        // This is a reasonable heuristic
        return conditionalAvailable;
      }

      // For older browsers, assume PRF is not available
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

  /**
   * Create a new passkey identity.
   *
   * Requires email in options (used as salt for deterministic key derivation).
   * The email must be the same on all devices to recover the same keypair.
   */
  async createIdentity(options: CreateIdentityOptions & { email?: string }): Promise<{
    identity: IdentityInfo;
    mnemonic?: string; // Not used for Easy mode
  }> {
    if (options.tier !== 'easy') {
      throw new Error(`PasskeyProvider only supports 'easy' tier, got '${options.tier}'`);
    }

    const email = options.email;
    if (!email) {
      throw new Error('Email is required for Easy mode identity');
    }

    // Validate email format (basic check)
    if (!email.includes('@') || email.length < 5) {
      throw new Error('Invalid email format');
    }

    // Check if identity already exists
    if (await this.hasIdentity()) {
      throw new Error('Identity already exists. Delete it first to create a new one.');
    }

    // Create the passkey with PRF extension
    const { credentialId, privateKey } = await this.createPasskeyWithPRF(email);

    const publicKey = getPublicKey(privateKey);
    const publicKeyHex = publicKeyToHex(publicKey);

    // Store metadata (NOT the private key)
    const stored: StoredPasskeyIdentity = {
      version: 1,
      credentialId: credentialId,
      email: email,
      publicKey: publicKeyHex,
      createdAt: Date.now(),
    };

    await this.storage.save(stored);

    // Keep unlocked after creation
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
      // No mnemonic for Easy mode - recovery is via passkey sync
    };
  }

  /**
   * Import/recover an existing passkey identity.
   *
   * For Easy mode, this means:
   * 1. User provides same email used during creation
   * 2. User authenticates with synced passkey (same passkey on new device)
   * 3. PRF + email → same keypair
   *
   * This works because:
   * - Passkeys sync across devices via iCloud/Google
   * - Same email + same passkey = same PRF output = same keypair
   */
  async importIdentity(options: CreateIdentityOptions & { email?: string }): Promise<IdentityInfo> {
    if (options.tier !== 'easy') {
      throw new Error(`PasskeyProvider only supports 'easy' tier, got '${options.tier}'`);
    }

    const email = options.email;
    if (!email) {
      throw new Error('Email is required to recover Easy mode identity');
    }

    // Check if identity already exists
    if (await this.hasIdentity()) {
      throw new Error('Identity already exists. Delete it first to import.');
    }

    // Authenticate with existing passkey to derive keypair
    const { credentialId, privateKey } = await this.authenticateWithPRF(email);

    const publicKey = getPublicKey(privateKey);
    const publicKeyHex = publicKeyToHex(publicKey);

    // Store metadata
    const stored: StoredPasskeyIdentity = {
      version: 1,
      credentialId: credentialId,
      email: email,
      publicKey: publicKeyHex,
      createdAt: Date.now(),
    };

    await this.storage.save(stored);

    // Keep unlocked
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

  /**
   * Unlock the identity using passkey (TouchID/FaceID).
   *
   * For Easy mode, no password is needed - just biometric authentication.
   */
  async unlock(options?: UnlockOptions): Promise<boolean> {
    const stored = await this.storage.load();
    if (!stored) {
      throw new Error('No identity found. Create or import one first.');
    }

    try {
      // Authenticate with passkey to derive private key
      const { privateKey } = await this.authenticateWithPRF(stored.email, stored.credentialId);

      // Verify derived public key matches stored public key
      const derivedPubKey = publicKeyToHex(getPublicKey(privateKey));
      if (derivedPubKey !== stored.publicKey) {
        // This should not happen if using the correct passkey + email
        throw new Error('Derived key mismatch. Wrong passkey or email.');
      }

      this.privateKey = privateKey;
      this.publicKey = getPublicKey(privateKey);

      // Set auto-lock timeout
      const timeout = options?.timeout ?? DEFAULT_TIMEOUT_MS;
      this.setUnlockTimeout(timeout);

      return true;
    } catch (err) {
      // Authentication failed (user canceled, wrong passkey, etc.)
      return false;
    }
  }

  isUnlocked(): boolean {
    return this.privateKey !== null;
  }

  lock(): void {
    // Securely clear private key from memory
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

  /**
   * Create a new passkey with PRF extension and derive keypair.
   */
  private async createPasskeyWithPRF(email: string): Promise<{
    credentialId: string;
    privateKey: Uint8Array;
  }> {
    // Compute salt from email (used for PRF)
    const salt = this.computePRFSalt(email);

    // Create WebAuthn credential with PRF extension
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
          { alg: -7, type: 'public-key' }, // ES256
          { alg: -257, type: 'public-key' }, // RS256
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

    // Get PRF output from extension results
    const extensionResults = credential.getClientExtensionResults() as PRFExtensionResults;
    if (!extensionResults.prf?.results?.first) {
      throw new Error('PRF extension not supported or failed');
    }

    const prfOutput = new Uint8Array(extensionResults.prf.results.first);

    // Derive private key using HKDF
    const privateKey = this.derivePrivateKey(prfOutput);

    // Encode credential ID as base64
    const credentialId = this.arrayBufferToBase64(credential.rawId);

    return { credentialId, privateKey };
  }

  /**
   * Authenticate with existing passkey and derive keypair.
   */
  private async authenticateWithPRF(
    email: string,
    credentialId?: string
  ): Promise<{
    credentialId: string;
    privateKey: Uint8Array;
  }> {
    // Compute salt from email
    const salt = this.computePRFSalt(email);

    // Build allowCredentials if we have a specific credential ID
    const allowCredentials: PublicKeyCredentialDescriptor[] | undefined = credentialId
      ? [{ type: 'public-key', id: this.base64ToArrayBuffer(credentialId) }]
      : undefined;

    // Authenticate with passkey
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

    // Get PRF output
    const extensionResults = assertion.getClientExtensionResults() as PRFExtensionResults;
    if (!extensionResults.prf?.results?.first) {
      throw new Error('PRF extension not supported or failed');
    }

    const prfOutput = new Uint8Array(extensionResults.prf.results.first);

    // Derive private key
    const privateKey = this.derivePrivateKey(prfOutput);

    return {
      credentialId: this.arrayBufferToBase64(assertion.rawId),
      privateKey,
    };
  }

  /**
   * Compute PRF salt from email using SHA-256.
   */
  private computePRFSalt(email: string): Uint8Array {
    const emailBytes = new TextEncoder().encode(email.toLowerCase().trim());
    return sha256(emailBytes);
  }

  /**
   * Derive secp256k1 private key from PRF output using HKDF.
   */
  private derivePrivateKey(prfOutput: Uint8Array): Uint8Array {
    // Use HKDF to derive a 32-byte private key
    // Note: No salt needed here since PRF output is already keyed
    return hkdf(sha256, prfOutput, undefined, HKDF_INFO, 32);
  }

  /**
   * Get the RP ID for WebAuthn (domain without protocol).
   */
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

  // Utility methods for base64 encoding/decoding

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
 * Used in browser environments.
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
