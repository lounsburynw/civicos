/**
 * Identity Manager for CivicOS Extension.
 *
 * Manages signing providers with Chrome storage backends.
 * Supports:
 * - easy: PasskeyProvider (WebAuthn + PRF, lowest friction)
 * - private: LocalWalletProvider (BIP-39 + password encryption)
 *
 * Uses chrome.storage.session to persist unlock state across
 * service worker restarts (cleared on browser close).
 */

import type {
  SigningProvider,
  IdentityTier,
  IdentityInfo,
  NostrEvent,
  SigningResult,
  WalletStorage,
  PasskeyStorage,
} from './providers/index.js';
import {
  LocalWalletProvider,
  PasskeyProvider,
  MemoryPasskeyStorage,
  MemoryStorage,
} from './providers/index.js';
import { ChromeStoragePasskeyStorage, ChromeStorageWalletStorage } from './storage.js';

const SESSION_KEY = 'civicos_session_key';

export interface IdentityManagerConfig {
  storage?: WalletStorage;
  passkeyStorage?: PasskeyStorage;
}

export class IdentityManager {
  private providers: Map<IdentityTier, SigningProvider> = new Map();
  private activeProvider: SigningProvider | null = null;

  constructor(config: IdentityManagerConfig = {}) {
    const storage = config.storage ?? this.createDefaultStorage();
    this.providers.set('private', new LocalWalletProvider(storage));

    const passkeyStorage = config.passkeyStorage ?? this.createDefaultPasskeyStorage();
    this.providers.set('easy', new PasskeyProvider(passkeyStorage));
  }

  private createDefaultStorage(): WalletStorage {
    // In Chrome extension context, use chrome.storage.local
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      return new ChromeStorageWalletStorage();
    }
    // Fallback for testing
    return new MemoryStorage();
  }

  private createDefaultPasskeyStorage(): PasskeyStorage {
    // In Chrome extension context, use chrome.storage.local
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      return new ChromeStoragePasskeyStorage();
    }
    // Fallback for testing
    return new MemoryPasskeyStorage();
  }

  // === Session persistence (survives service worker restarts) ===

  private async saveSession(privateKeyHex: string, tier: IdentityTier): Promise<void> {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage?.session) {
        await chrome.storage.session.set({ [SESSION_KEY]: { key: privateKeyHex, tier } });
      }
    } catch {
      // Session storage not available (e.g., testing)
    }
  }

  private async clearSession(): Promise<void> {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage?.session) {
        await chrome.storage.session.remove(SESSION_KEY);
      }
    } catch {
      // Ignore
    }
  }

  private async restoreFromSession(): Promise<boolean> {
    try {
      if (typeof chrome === 'undefined' || !chrome.storage?.session) return false;

      const result = await chrome.storage.session.get(SESSION_KEY);
      const session = result[SESSION_KEY] as { key: string; tier: IdentityTier } | undefined;
      if (!session?.key || !session?.tier) return false;

      const provider = this.providers.get(session.tier);
      if (!provider) return false;

      // Restore the private key into the provider
      const { hexToBytes } = await import('@noble/hashes/utils');
      const { getPublicKey } = await import('./providers/crypto.js');
      const privateKey = hexToBytes(session.key);

      // Inject the key directly — both providers store it the same way
      (provider as unknown as { privateKey: Uint8Array | null }).privateKey = privateKey;
      (provider as unknown as { publicKey: Uint8Array | null }).publicKey = getPublicKey(privateKey);

      this.activeProvider = provider;
      return true;
    } catch {
      return false;
    }
  }

  // === Public API ===

  getActiveProvider(): SigningProvider | null {
    return this.activeProvider;
  }

  getProvider(tier: IdentityTier): SigningProvider | undefined {
    return this.providers.get(tier);
  }

  async hasIdentity(): Promise<boolean> {
    for (const provider of this.providers.values()) {
      if (await provider.hasIdentity()) {
        return true;
      }
    }
    return false;
  }

  async getIdentity(): Promise<IdentityInfo | null> {
    if (this.activeProvider) {
      const identity = await this.activeProvider.getIdentity();
      if (identity) return identity;
    }

    for (const provider of this.providers.values()) {
      const identity = await provider.getIdentity();
      if (identity) {
        this.activeProvider = provider;
        return identity;
      }
    }

    return null;
  }

  async createIdentity(
    tier: IdentityTier,
    passwordOrEmail: string
  ): Promise<{ identity: IdentityInfo; mnemonic?: string }> {
    const provider = this.providers.get(tier);
    if (!provider) {
      throw new Error(`Unsupported identity tier: ${tier}`);
    }

    const options =
      tier === 'easy'
        ? { tier, email: passwordOrEmail }
        : { tier, password: passwordOrEmail };

    const result = await provider.createIdentity(options);
    this.activeProvider = provider;

    // Save session for service worker restart resilience
    const pk = (provider as unknown as { privateKey: Uint8Array | null }).privateKey;
    if (pk) {
      const { bytesToHex } = await import('@noble/hashes/utils');
      await this.saveSession(bytesToHex(pk), tier);
    }

    return result;
  }

  async importIdentity(
    tier: IdentityTier,
    passwordOrEmail: string,
    mnemonic?: string
  ): Promise<IdentityInfo> {
    const provider = this.providers.get(tier);
    if (!provider) {
      throw new Error(`Unsupported identity tier: ${tier}`);
    }

    const options =
      tier === 'easy'
        ? { tier, email: passwordOrEmail }
        : { tier, password: passwordOrEmail, mnemonic };

    const identity = await provider.importIdentity(options);
    this.activeProvider = provider;

    return identity;
  }

  async unlock(password: string): Promise<boolean> {
    if (!this.activeProvider) {
      await this.getIdentity();
    }

    if (!this.activeProvider) {
      throw new Error('No identity found. Create or import one first.');
    }

    const unlocked = await this.activeProvider.unlock({ password });

    if (unlocked) {
      // Persist key to session storage so it survives service worker restarts
      const pk = (this.activeProvider as unknown as { privateKey: Uint8Array | null }).privateKey;
      if (pk) {
        const { bytesToHex } = await import('@noble/hashes/utils');
        const identity = await this.activeProvider.getIdentity();
        await this.saveSession(bytesToHex(pk), identity?.tier ?? 'private');
      }
    }

    return unlocked;
  }

  isUnlocked(): boolean {
    return this.activeProvider?.isUnlocked() ?? false;
  }

  lock(): void {
    this.activeProvider?.lock();
    this.clearSession();
  }

  async signEvent(event: NostrEvent): Promise<SigningResult> {
    // Restore provider if service worker restarted
    if (!this.activeProvider) {
      await this.getIdentity();
    }

    // Restore unlock state from session if needed
    if (this.activeProvider && !this.activeProvider.isUnlocked()) {
      await this.restoreFromSession();
    }

    if (!this.activeProvider) {
      return {
        success: false,
        error: 'No active identity. Create or import one first.',
      };
    }

    if (!this.activeProvider.isUnlocked()) {
      return {
        success: false,
        error: 'Identity is locked. Unlock it first.',
      };
    }

    return this.activeProvider.signEvent(event);
  }

  async getPublicKey(): Promise<string | null> {
    if (!this.activeProvider) {
      await this.getIdentity();
    }
    return this.activeProvider?.getPublicKey() ?? null;
  }

  async deleteIdentity(): Promise<void> {
    if (this.activeProvider) {
      await this.activeProvider.deleteIdentity();
      this.activeProvider = null;
    }
    await this.clearSession();
  }

  getAvailableTiers(): IdentityTier[] {
    return Array.from(this.providers.keys());
  }

  async checkAvailability(): Promise<Map<IdentityTier, boolean>> {
    const availability = new Map<IdentityTier, boolean>();

    for (const [tier, provider] of this.providers.entries()) {
      availability.set(tier, await provider.isAvailable());
    }

    return availability;
  }
}
