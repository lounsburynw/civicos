import { schnorr } from '@noble/curves/secp256k1';
import { bytesToHex, hexToBytes, randomBytes } from '@noble/hashes/utils';
import type { KeyPair, KeyStore } from '../types.js';

export function getPublicKeyHex(privateKey: Uint8Array): string {
  return bytesToHex(schnorr.getPublicKey(privateKey));
}

export function createKeyPair(): KeyPair {
  const privateKey = randomBytes(32);
  const publicKey = getPublicKeyHex(privateKey);
  return { privateKey, publicKey };
}

export async function loadKeyPair(store: KeyStore): Promise<KeyPair> {
  const stored = await store.load();
  if (stored) {
    const privateKey = hexToBytes(stored);
    const publicKey = getPublicKeyHex(privateKey);
    return { privateKey, publicKey };
  }
  const keyPair = createKeyPair();
  await store.save(bytesToHex(keyPair.privateKey));
  return keyPair;
}
