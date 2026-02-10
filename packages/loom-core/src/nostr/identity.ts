import { schnorr, etc } from '@noble/secp256k1';
import type { KeyPair, KeyStore } from '../types.js';

export function getPublicKeyHex(privateKey: Uint8Array): string {
  return etc.bytesToHex(schnorr.getPublicKey(privateKey));
}

export function createKeyPair(): KeyPair {
  const privateKey = etc.randomBytes(32);
  const publicKey = getPublicKeyHex(privateKey);
  return { privateKey, publicKey };
}

export async function loadKeyPair(store: KeyStore): Promise<KeyPair> {
  const stored = await store.load();
  if (stored) {
    const privateKey = etc.hexToBytes(stored);
    const publicKey = getPublicKeyHex(privateKey);
    return { privateKey, publicKey };
  }
  const keyPair = createKeyPair();
  await store.save(etc.bytesToHex(keyPair.privateKey));
  return keyPair;
}
