/**
 * Identity Manager
 *
 * Manages signing providers and provides a unified interface for identity operations.
 * Currently supports:
 * - private: LocalWalletProvider (BIP-39 + password encryption)
 *
 * Future support:
 * - easy: PasskeyProvider (WebAuthn + PRF)
 * - sovereign: NIP07Provider, HardwareWalletProvider, ManualSigningProvider
 */

import type {
  SigningProvider,
  IdentityTier,
  IdentityInfo,
  NostrEvent,
  SigningResult,
  WalletStorage,
} from '../lib/providers/index.js';
import { LocalWalletProvider, IndexedDBStorage, MemoryStorage } from '../lib/providers/index.js';

/**
 * Configuration for the IdentityManager.
 */
export interface IdentityManagerConfig {
  /** Override the default storage for testing */
  storage?: WalletStorage;
}

/**
 * IdentityManager provides a unified interface for identity operations.
 *
 * It manages the appropriate signing provider based on the identity tier
 * and delegates all operations to that provider.
 */
export class IdentityManager {
  private providers: Map<IdentityTier, SigningProvider> = new Map();
  private activeProvider: SigningProvider | null = null;

  constructor(config: IdentityManagerConfig = {}) {
    // Initialize providers
    const storage = config.storage ?? this.createDefaultStorage();
    this.providers.set('private', new LocalWalletProvider(storage));

    // Future providers:
    // this.providers.set('easy', new PasskeyProvider());
    // this.providers.set('sovereign', new NIP07Provider());
  }

  private createDefaultStorage(): WalletStorage {
    // In browser environment, use IndexedDB
    // In Node.js, fall back to MemoryStorage (or filesystem in future)
    if (typeof indexedDB !== 'undefined') {
      return new IndexedDBStorage();
    }
    // For Node.js/testing, use memory storage
    return new MemoryStorage();
  }

  /**
   * Get the currently active provider, if any.
   */
  getActiveProvider(): SigningProvider | null {
    return this.activeProvider;
  }

  /**
   * Get a provider for a specific tier.
   */
  getProvider(tier: IdentityTier): SigningProvider | undefined {
    return this.providers.get(tier);
  }

  /**
   * Check if any identity exists.
   */
  async hasIdentity(): Promise<boolean> {
    for (const provider of this.providers.values()) {
      if (await provider.hasIdentity()) {
        return true;
      }
    }
    return false;
  }

  /**
   * Get the current identity info, checking all providers.
   */
  async getIdentity(): Promise<IdentityInfo | null> {
    // First check active provider
    if (this.activeProvider) {
      const identity = await this.activeProvider.getIdentity();
      if (identity) return identity;
    }

    // Check all providers
    for (const provider of this.providers.values()) {
      const identity = await provider.getIdentity();
      if (identity) {
        this.activeProvider = provider;
        return identity;
      }
    }

    return null;
  }

  /**
   * Create a new identity with the specified tier.
   */
  async createIdentity(
    tier: IdentityTier,
    password: string
  ): Promise<{ identity: IdentityInfo; mnemonic?: string }> {
    const provider = this.providers.get(tier);
    if (!provider) {
      throw new Error(`Unsupported identity tier: ${tier}`);
    }

    const result = await provider.createIdentity({ tier, password });
    this.activeProvider = provider;

    return result;
  }

  /**
   * Import an existing identity from a mnemonic.
   */
  async importIdentity(
    tier: IdentityTier,
    password: string,
    mnemonic: string
  ): Promise<IdentityInfo> {
    const provider = this.providers.get(tier);
    if (!provider) {
      throw new Error(`Unsupported identity tier: ${tier}`);
    }

    const identity = await provider.importIdentity({ tier, password, mnemonic });
    this.activeProvider = provider;

    return identity;
  }

  /**
   * Unlock the active identity.
   */
  async unlock(password: string): Promise<boolean> {
    // Find and activate the provider with an identity
    if (!this.activeProvider) {
      await this.getIdentity(); // This will set activeProvider if found
    }

    if (!this.activeProvider) {
      throw new Error('No identity found. Create or import one first.');
    }

    return this.activeProvider.unlock({ password });
  }

  /**
   * Check if the active identity is unlocked.
   */
  isUnlocked(): boolean {
    return this.activeProvider?.isUnlocked() ?? false;
  }

  /**
   * Lock the active identity.
   */
  lock(): void {
    this.activeProvider?.lock();
  }

  /**
   * Sign a Nostr event with the active identity.
   */
  async signEvent(event: NostrEvent): Promise<SigningResult> {
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

  /**
   * Get the public key of the active identity.
   */
  async getPublicKey(): Promise<string | null> {
    if (!this.activeProvider) {
      await this.getIdentity();
    }
    return this.activeProvider?.getPublicKey() ?? null;
  }

  /**
   * Delete the active identity.
   */
  async deleteIdentity(): Promise<void> {
    if (this.activeProvider) {
      await this.activeProvider.deleteIdentity();
      this.activeProvider = null;
    }
  }

  /**
   * Get available identity tiers.
   */
  getAvailableTiers(): IdentityTier[] {
    return Array.from(this.providers.keys());
  }

  /**
   * Check which tiers are available in the current environment.
   */
  async checkAvailability(): Promise<Map<IdentityTier, boolean>> {
    const availability = new Map<IdentityTier, boolean>();

    for (const [tier, provider] of this.providers.entries()) {
      availability.set(tier, await provider.isAvailable());
    }

    return availability;
  }
}
