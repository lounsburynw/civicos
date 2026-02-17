import { describe, it, expect } from 'vitest';
import { hexToBytes } from '@noble/hashes/utils';
import { createKeyPair, getPublicKeyHex, loadKeyPair } from './identity.js';
import type { KeyStore } from '../types.js';
import vectors from '../../test-vectors.json';

describe('getPublicKeyHex', () => {
  it('produces known public key for private key 0x01', () => {
    const privateKey = hexToBytes(vectors.privateKey);
    const pubkey = getPublicKeyHex(privateKey);
    expect(pubkey).toBe(vectors.publicKey);
  });
});

describe('createKeyPair', () => {
  it('produces valid format', () => {
    const kp = createKeyPair();
    expect(kp.privateKey).toBeInstanceOf(Uint8Array);
    expect(kp.privateKey.length).toBe(32);
    expect(kp.publicKey).toHaveLength(64);
    expect(kp.publicKey).toMatch(/^[0-9a-f]{64}$/);
  });

  it('produces unique keys each time', () => {
    const kp1 = createKeyPair();
    const kp2 = createKeyPair();
    expect(kp1.publicKey).not.toBe(kp2.publicKey);
  });
});

describe('loadKeyPair', () => {
  it('creates and saves on first call', async () => {
    let saved: string | null = null;
    const store: KeyStore = {
      load: async () => saved,
      save: async (hex: string) => { saved = hex; },
    };

    const kp = await loadKeyPair(store);
    expect(kp.privateKey).toBeInstanceOf(Uint8Array);
    expect(kp.publicKey).toHaveLength(64);
    expect(saved).not.toBeNull();
  });

  it('loads existing key on second call', async () => {
    let saved: string | null = null;
    const store: KeyStore = {
      load: async () => saved,
      save: async (hex: string) => { saved = hex; },
    };

    const kp1 = await loadKeyPair(store);
    const kp2 = await loadKeyPair(store);
    expect(kp1.publicKey).toBe(kp2.publicKey);
  });
});
