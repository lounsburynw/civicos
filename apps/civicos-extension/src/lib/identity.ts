/**
 * Identity Manager for CivicOS Extension.
 *
 * Manages signing providers with Chrome storage backends.
 * Supports:
 * - easy: PasskeyProvider (WebAuthn + PRF, lowest friction)
 * - private: LocalWalletProvider (BIP-39 + password encryption)
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

    return this.activeProvider.unlock({ password });
  }

  isUnlocked(): boolean {
    return this.activeProvider?.isUnlocked() ?? false;
  }

  lock(): void {
    this.activeProvider?.lock();
  }

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
