/**
 * Chrome extension storage adapters.
 *
 * Uses chrome.storage.local for persistent data that survives
 * service worker restarts. All methods are async.
 */

import type { PasskeyStorage } from './providers/passkey.js';
import type { WalletStorage } from './providers/local-wallet.js';

const PASSKEY_STORAGE_KEY = 'civicos-passkey-identity';
const WALLET_STORAGE_KEY = 'civicos-wallet-identity';

/**
 * Chrome storage adapter for passkey identity metadata.
 * Replaces LocalStoragePasskeyStorage in the extension context.
 */
export class ChromeStoragePasskeyStorage implements PasskeyStorage {
  async save(identity: Parameters<PasskeyStorage['save']>[0]): Promise<void> {
    await chrome.storage.local.set({ [PASSKEY_STORAGE_KEY]: identity });
  }

  async load(): Promise<Awaited<ReturnType<PasskeyStorage['load']>>> {
    const result = await chrome.storage.local.get(PASSKEY_STORAGE_KEY);
    return result[PASSKEY_STORAGE_KEY] ?? null;
  }

  async delete(): Promise<void> {
    await chrome.storage.local.remove(PASSKEY_STORAGE_KEY);
  }
}

/**
 * Chrome storage adapter for encrypted wallet data.
 * Replaces IndexedDBStorage in the extension context.
 */
export class ChromeStorageWalletStorage implements WalletStorage {
  async save(wallet: Parameters<WalletStorage['save']>[0]): Promise<void> {
    await chrome.storage.local.set({ [WALLET_STORAGE_KEY]: wallet });
  }

  async load(): Promise<Awaited<ReturnType<WalletStorage['load']>>> {
    const result = await chrome.storage.local.get(WALLET_STORAGE_KEY);
    return result[WALLET_STORAGE_KEY] ?? null;
  }

  async delete(): Promise<void> {
    await chrome.storage.local.remove(WALLET_STORAGE_KEY);
  }
}
