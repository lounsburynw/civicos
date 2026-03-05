/**
 * LocalWalletProvider - Private identity tier.
 *
 * Uses BIP-39 mnemonic for key generation and recovery.
 * Keys are encrypted with AES-256-GCM using a password-derived key (PBKDF2).
 * Encrypted keys stored in chrome.storage.local (extension) or IndexedDB (browser).
 *
 * Security model:
 * - Private key never leaves device unencrypted
 * - Password required to unlock (not stored)
 * - 12-word recovery phrase for backup
 * - PBKDF2 with 100k iterations for key stretching
 */

import * as bip39 from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english';
import { HDKey } from '@scure/bip32';
import { bytesToHex, hexToBytes } from '@noble/hashes/utils';
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

// NIP-06 derivation path for Nostr keys
const NOSTR_DERIVATION_PATH = "m/44'/1237'/0'/0/0";

// PBKDF2 parameters
const PBKDF2_ITERATIONS = 100_000;
const SALT_LENGTH = 16;
const IV_LENGTH = 12;

// Storage key
const STORAGE_KEY = 'civicos-wallet-identity';

/**
 * Encrypted wallet data stored persistently.
 */
interface EncryptedWallet {
  version: 1;
  salt: string; // hex
  iv: string; // hex
  encryptedKey: string; // hex (AES-GCM encrypted private key)
  publicKey: string; // hex (for identity lookup without decryption)
  createdAt: number;
}

/**
 * LocalWalletProvider implements the "Private" identity tier.
 *
 * Features:
 * - BIP-39 mnemonic generation and import
 * - NIP-06 key derivation (m/44'/1237'/0'/0/0)
 * - AES-256-GCM encryption with PBKDF2 key derivation
 * - Pluggable storage (chrome.storage.local, IndexedDB, or memory)
 */
export class LocalWalletProvider implements SigningProvider {
  readonly tier: IdentityTier = 'private';
  readonly name = 'Local Wallet (Password Protected)';

  private privateKey: Uint8Array | null = null;
  private publicKey: Uint8Array | null = null;
  private storage: WalletStorage;

  constructor(storage?: WalletStorage) {
    this.storage = storage ?? new IndexedDBStorage();
  }

  async isAvailable(): Promise<boolean> {
    return typeof crypto !== 'undefined' && typeof crypto.subtle !== 'undefined';
  }

  async hasIdentity(): Promise<boolean> {
    const wallet = await this.storage.load();
    return wallet !== null;
  }

  async getIdentity(): Promise<IdentityInfo | null> {
    const wallet = await this.storage.load();
    if (!wallet) return null;

    return {
      tier: this.tier,
      publicKey: wallet.publicKey,
      npub: publicKeyToNpub(wallet.publicKey),
      createdAt: wallet.createdAt,
    };
  }

  async getPublicKey(): Promise<string | null> {
    if (this.publicKey) {
      return publicKeyToHex(this.publicKey);
    }

    const wallet = await this.storage.load();
    return wallet?.publicKey ?? null;
  }

  async createIdentity(options: CreateIdentityOptions): Promise<{
    identity: IdentityInfo;
    mnemonic: string;
  }> {
    if (options.tier !== 'private') {
      throw new Error(`LocalWalletProvider only supports 'private' tier, got '${options.tier}'`);
    }

    if (!options.password) {
      throw new Error('Password is required for private tier identity');
    }

    const mnemonic = bip39.generateMnemonic(wordlist, 128); // 12 words

    const seed = await bip39.mnemonicToSeed(mnemonic);
    const hdKey = HDKey.fromMasterSeed(seed);
    const derived = hdKey.derive(NOSTR_DERIVATION_PATH);

    if (!derived.privateKey) {
      throw new Error('Failed to derive private key');
    }

    const privateKey = derived.privateKey;
    const publicKey = getPublicKey(privateKey);
    const publicKeyHex = publicKeyToHex(publicKey);

    const encryptedWallet = await this.encryptAndStore(privateKey, options.password);

    this.privateKey = privateKey;
    this.publicKey = publicKey;

    return {
      identity: {
        tier: this.tier,
        publicKey: publicKeyHex,
        npub: publicKeyToNpub(publicKeyHex),
        createdAt: encryptedWallet.createdAt,
      },
      mnemonic,
    };
  }

  async importIdentity(options: CreateIdentityOptions): Promise<IdentityInfo> {
    if (options.tier !== 'private') {
      throw new Error(`LocalWalletProvider only supports 'private' tier, got '${options.tier}'`);
    }

    if (!options.password) {
      throw new Error('Password is required for private tier identity');
    }

    if (!options.mnemonic) {
      throw new Error('Mnemonic is required to import identity');
    }

    if (!bip39.validateMnemonic(options.mnemonic, wordlist)) {
      throw new Error('Invalid mnemonic phrase');
    }

    const seed = await bip39.mnemonicToSeed(options.mnemonic);
    const hdKey = HDKey.fromMasterSeed(seed);
    const derived = hdKey.derive(NOSTR_DERIVATION_PATH);

    if (!derived.privateKey) {
      throw new Error('Failed to derive private key');
    }

    const privateKey = derived.privateKey;
    const publicKey = getPublicKey(privateKey);
    const publicKeyHex = publicKeyToHex(publicKey);

    const encryptedWallet = await this.encryptAndStore(privateKey, options.password);

    this.privateKey = privateKey;
    this.publicKey = publicKey;

    return {
      tier: this.tier,
      publicKey: publicKeyHex,
      npub: publicKeyToNpub(publicKeyHex),
      createdAt: encryptedWallet.createdAt,
    };
  }

  async unlock(options?: UnlockOptions): Promise<boolean> {
    if (!options?.password) {
      throw new Error('Password is required to unlock');
    }

    const wallet = await this.storage.load();
    if (!wallet) {
      throw new Error('No identity found. Create or import one first.');
    }

    try {
      const privateKey = await this.decryptPrivateKey(wallet, options.password);

      this.privateKey = privateKey;
      this.publicKey = getPublicKey(privateKey);

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
  }

  async signEvent(event: NostrEvent): Promise<SigningResult> {
    if (!this.privateKey) {
      return {
        success: false,
        error: 'Wallet is locked. Call unlock() first.',
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

  private async encryptAndStore(
    privateKey: Uint8Array,
    password: string
  ): Promise<EncryptedWallet> {
    const salt = crypto.getRandomValues(new Uint8Array(SALT_LENGTH));
    const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));

    const passwordKey = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(password),
      'PBKDF2',
      false,
      ['deriveKey']
    );

    const encryptionKey = await crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt,
        iterations: PBKDF2_ITERATIONS,
        hash: 'SHA-256',
      },
      passwordKey,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt']
    );

    const encryptedData = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: iv as BufferSource },
      encryptionKey,
      privateKey as BufferSource
    );

    const wallet: EncryptedWallet = {
      version: 1,
      salt: bytesToHex(salt),
      iv: bytesToHex(iv),
      encryptedKey: bytesToHex(new Uint8Array(encryptedData)),
      publicKey: publicKeyToHex(getPublicKey(privateKey)),
      createdAt: Date.now(),
    };

    await this.storage.save(wallet);
    return wallet;
  }

  private async decryptPrivateKey(
    wallet: EncryptedWallet,
    password: string
  ): Promise<Uint8Array> {
    const salt = hexToBytes(wallet.salt);
    const iv = hexToBytes(wallet.iv);
    const encryptedData = hexToBytes(wallet.encryptedKey);

    const passwordKey = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(password),
      'PBKDF2',
      false,
      ['deriveKey']
    );

    const encryptionKey = await crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: salt as BufferSource,
        iterations: PBKDF2_ITERATIONS,
        hash: 'SHA-256',
      },
      passwordKey,
      { name: 'AES-GCM', length: 256 },
      false,
      ['decrypt']
    );

    const decryptedData = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: iv as BufferSource },
      encryptionKey,
      encryptedData as BufferSource
    );

    return new Uint8Array(decryptedData);
  }
}

/**
 * Storage interface for wallet data.
 */
export interface WalletStorage {
  save(wallet: EncryptedWallet): Promise<void>;
  load(): Promise<EncryptedWallet | null>;
  delete(): Promise<void>;
}

/**
 * IndexedDB storage implementation for browsers (fallback).
 */
export class IndexedDBStorage implements WalletStorage {
  private dbName = 'civicos-extension';
  private storeName = 'identity';

  private async getDB(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, 1);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);

      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName);
        }
      };
    });
  }

  async save(wallet: EncryptedWallet): Promise<void> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, 'readwrite');
      const store = tx.objectStore(this.storeName);
      const request = store.put(wallet, STORAGE_KEY);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve();
    });
  }

  async load(): Promise<EncryptedWallet | null> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, 'readonly');
      const store = tx.objectStore(this.storeName);
      const request = store.get(STORAGE_KEY);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result ?? null);
    });
  }

  async delete(): Promise<void> {
    const db = await this.getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, 'readwrite');
      const store = tx.objectStore(this.storeName);
      const request = store.delete(STORAGE_KEY);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve();
    });
  }
}

/**
 * In-memory storage for testing.
 */
export class MemoryStorage implements WalletStorage {
  private wallet: EncryptedWallet | null = null;

  async save(wallet: EncryptedWallet): Promise<void> {
    this.wallet = wallet;
  }

  async load(): Promise<EncryptedWallet | null> {
    return this.wallet;
  }

  async delete(): Promise<void> {
    this.wallet = null;
  }
}
